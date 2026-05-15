"""iTunes/Finder backup source reader."""
import hashlib
import os
import plistlib
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .base import DataSource
from ..logger import get_logger

_log = get_logger("sources.backup")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return "unavailable"


class BackupSource(DataSource):
    """Reads an iTunes/Finder backup directory (unencrypted or decryptable)."""

    source_type = "itunes_backup"

    def __init__(self, backup_path: str):
        self._root = Path(backup_path)
        # If user pointed at a parent Backup/ dir, auto-detect
        if not (self._root / "Manifest.db").exists():
            self._root = self._find_backup_root(self._root)
        self._file_map: Dict[Tuple[str, str], str] = {}
        self._manifest_hash_before: Optional[str] = None
        self._manifest_hash_after: Optional[str] = None

    def _find_backup_root(self, parent: Path) -> Path:
        """Scan subdirectories for one containing Manifest.db."""
        for child in sorted(parent.iterdir()):
            if child.is_dir() and (child / "Manifest.db").exists():
                _log.info("Auto-detected backup at %s", child)
                return child
        raise IOError(f"No iTunes backup found in {parent}")

    def open(self) -> None:
        manifest_plist_path = self._root / "Manifest.plist"
        if manifest_plist_path.exists():
            with open(manifest_plist_path, "rb") as f:
                manifest_plist = plistlib.load(f)
            if manifest_plist.get("IsEncrypted", False):
                self._handle_encrypted(manifest_plist)
                return

        manifest_db = self._root / "Manifest.db"
        if not manifest_db.exists():
            raise IOError(f"Manifest.db not found in {self._root}")

        self._manifest_hash_before = _sha256(manifest_db)
        _log.info("Manifest.db SHA256 (before): %s", self._manifest_hash_before)

        conn = sqlite3.connect(f"file:{manifest_db}?mode=ro", uri=True)
        try:
            cur = conn.execute("SELECT fileID, domain, relativePath FROM Files")
            for file_id, domain, rel_path in cur.fetchall():
                if domain and rel_path and file_id:
                    self._file_map[(domain, rel_path)] = file_id
        finally:
            conn.close()

        self._manifest_hash_after = _sha256(manifest_db)
        if self._manifest_hash_before != self._manifest_hash_after:
            _log.warning("Manifest.db hash changed after read — WAL checkpoint occurred")

        _log.info("Loaded %d file entries from backup at %s", len(self._file_map), self._root)

    def _handle_encrypted(self, manifest_plist: dict) -> None:
        try:
            from iphone_backup_decrypt import EncryptedBackup  # noqa: F401
        except ImportError:
            raise PermissionError(
                "Backup is encrypted. Install 'iphone-backup-decrypt' to open it, "
                "or decrypt via iTunes/Finder first."
            )
        raise PermissionError(
            "Backup is encrypted. Use the password prompt — encrypted backup "
            "decryption will be wired into the UI layer."
        )

    def get_file(self, domain: str, relative_path: str) -> Optional[Path]:
        file_id = self._file_map.get((domain, relative_path))
        if not file_id:
            return None
        physical = self._root / file_id[:2] / file_id
        return physical if physical.exists() else None

    def list_files(self, domain: str, prefix: str) -> List[Tuple[str, Path]]:
        results = []
        for (dom, rel), file_id in self._file_map.items():
            if dom == domain and rel.startswith(prefix):
                physical = self._root / file_id[:2] / file_id
                if physical.exists():
                    results.append((rel, physical))
        return results

    def list_app_domains(self) -> List[str]:
        """Return all AppDomain-* bundle IDs found in this backup."""
        bundles = set()
        for (domain, _) in self._file_map:
            if domain.startswith("AppDomain-"):
                bundles.add(domain[len("AppDomain-"):])
        return sorted(bundles)

    def get_device_info(self) -> dict:
        info_path = self._root / "Info.plist"
        if not info_path.exists():
            return {}
        try:
            with open(info_path, "rb") as f:
                data = plistlib.load(f)
            return {
                "name": data.get("Device Name", ""),
                "imei": data.get("IMEI", ""),
                "ios_version": data.get("Product Version", ""),
                "serial": data.get("Serial Number", ""),
                "udid": data.get("Unique Identifier", ""),
            }
        except Exception as e:
            _log.error("Failed to read Info.plist: %s", e)
            return {}

    def manifest_hash(self) -> Optional[str]:
        return self._manifest_hash_before

    def close(self) -> None:
        self._file_map.clear()
