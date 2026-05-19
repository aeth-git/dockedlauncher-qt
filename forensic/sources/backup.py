"""iTunes/Finder backup source reader."""
import hashlib
import os
import plistlib
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .base import DataSource
from ..logger import get_logger

_log = get_logger("sources.backup")


class EncryptedBackupNeedsPassword(PermissionError):
    """Raised when an encrypted backup is opened without a password."""


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

    def __init__(self, backup_path: str, password: Optional[str] = None):
        self._root = Path(backup_path)
        self._password = password
        self._file_map: Dict[Tuple[str, str], str] = {}
        self._manifest_hash_before: Optional[str] = None
        self._manifest_hash_after: Optional[str] = None
        # Encryption state — populated only for encrypted backups
        self._enc_backup = None
        self._decrypted_dir: Optional[Path] = None
        self._decrypted_files: set = set()  # (domain, rel) already extracted

    def _find_backup_root(self, parent: Path) -> Path:
        """Scan subdirectories for one containing Manifest.db."""
        for child in sorted(parent.iterdir()):
            if child.is_dir() and (child / "Manifest.db").exists():
                _log.info("Auto-detected backup at %s", child)
                return child
        raise IOError(f"No iTunes backup found in {parent}")

    def open(self) -> None:
        # Auto-detect UUID subdir if Manifest.db isn't directly under root
        if not (self._root / "Manifest.db").exists():
            self._root = self._find_backup_root(self._root)

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
            from iphone_backup_decrypt import EncryptedBackup
        except ImportError:
            raise PermissionError(
                "Backup is encrypted. Install 'iphone-backup-decrypt' to open it, "
                "or decrypt via iTunes/Finder first."
            )

        if not self._password:
            raise EncryptedBackupNeedsPassword(
                "Backup is encrypted. A password is required to open it."
            )

        try:
            self._enc_backup = EncryptedBackup(
                backup_directory=str(self._root),
                passphrase=self._password,
            )
            self._enc_backup.test_decryption()
        except Exception as e:
            self._enc_backup = None
            raise PermissionError(f"Decryption failed: {e}")

        self._decrypted_dir = Path(tempfile.mkdtemp(prefix="iforensic_dec_"))
        decrypted_manifest = self._decrypted_dir / "Manifest.db"
        self._enc_backup.save_manifest_file(output_filename=str(decrypted_manifest))

        self._manifest_hash_before = _sha256(decrypted_manifest)
        _log.info("Decrypted Manifest.db SHA256: %s", self._manifest_hash_before)

        conn = sqlite3.connect(f"file:{decrypted_manifest}?mode=ro", uri=True)
        try:
            cur = conn.execute("SELECT fileID, domain, relativePath FROM Files")
            for file_id, domain, rel_path in cur.fetchall():
                if domain and rel_path and file_id:
                    self._file_map[(domain, rel_path)] = file_id
        finally:
            conn.close()

        _log.info(
            "Loaded %d encrypted file entries from backup at %s",
            len(self._file_map), self._root,
        )

    def _decrypt_to_temp(self, domain: str, rel: str, file_id: str) -> Optional[Path]:
        """Decrypt a single file into the temp dir, return its path. Cached."""
        key = (domain, rel)
        out = self._decrypted_dir / file_id[:2] / file_id
        if key in self._decrypted_files and out.exists():
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._enc_backup.extract_file(
                relative_path=rel,
                domain_like=domain,
                output_filename=str(out),
            )
            self._decrypted_files.add(key)
            return out if out.exists() else None
        except Exception as e:
            _log.warning("Decrypt failed for %s/%s: %s", domain, rel, e)
            return None

    def get_file(self, domain: str, relative_path: str) -> Optional[Path]:
        file_id = self._file_map.get((domain, relative_path))
        if not file_id:
            return None
        if self._enc_backup is not None:
            return self._decrypt_to_temp(domain, relative_path, file_id)
        physical = self._root / file_id[:2] / file_id
        return physical if physical.exists() else None

    def list_files(self, domain: str, prefix: str) -> List[Tuple[str, Path]]:
        results = []
        for (dom, rel), file_id in self._file_map.items():
            if dom == domain and rel.startswith(prefix):
                if self._enc_backup is not None:
                    p = self._decrypt_to_temp(dom, rel, file_id)
                    if p is not None:
                        results.append((rel, p))
                else:
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
        self._enc_backup = None
        if self._decrypted_dir and self._decrypted_dir.exists():
            try:
                shutil.rmtree(self._decrypted_dir, ignore_errors=True)
            finally:
                self._decrypted_dir = None
        self._decrypted_files.clear()
