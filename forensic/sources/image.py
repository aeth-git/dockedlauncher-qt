"""Forensic image source — raw filesystem folder, zip, or tar archive."""
import os
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

from .base import DataSource
from .backup import BackupSource
from ..constants import DOMAIN_FS_MAP
from ..logger import get_logger

_log = get_logger("sources.image")


class ImageSource(DataSource):
    """Supports two formats:
      1. iTunes-format directory (contains Manifest.db) — delegates to BackupSource.
      2. Raw filesystem dump (contains private/ at root) — direct path mapping.
    Archives (.zip, .tar, .tar.gz, etc.) are extracted to a temp dir first.
    """

    source_type = "forensic_image"

    def __init__(self, path: str):
        self._input = Path(path)
        self._root: Optional[Path] = None
        self._temp_dir: Optional[Path] = None
        self._delegate: Optional[BackupSource] = None

    def open(self) -> None:
        if self._input.is_dir():
            self._root = self._input
        else:
            self._extract()

        # Determine format
        if (self._root / "Manifest.db").exists():
            _log.info("Detected iTunes backup format at %s", self._root)
            self._delegate = BackupSource(str(self._root))
            self._delegate.open()
        elif (self._root / "private").exists():
            _log.info("Detected raw filesystem dump at %s", self._root)
        else:
            # Try to find backup root inside
            for child in self._root.rglob("Manifest.db"):
                _log.info("Found iTunes backup at %s", child.parent)
                self._delegate = BackupSource(str(child.parent))
                self._delegate.open()
                break
            if not self._delegate:
                _log.warning("Unrecognised image format at %s — attempting raw mode", self._root)

    def _extract(self) -> None:
        self._temp_dir = Path(tempfile.mkdtemp(prefix="iforensic_img_"))
        name = self._input.name.lower()
        _log.info("Extracting archive %s to %s", self._input, self._temp_dir)
        try:
            if name.endswith(".zip"):
                with zipfile.ZipFile(self._input, "r") as z:
                    self._safe_extractall_zip(z, self._temp_dir)
            elif any(name.endswith(s) for s in (".tar", ".tar.gz", ".tgz",
                                                  ".tar.bz2", ".tbz2",
                                                  ".tar.xz", ".txz")):
                with tarfile.open(self._input) as t:
                    self._safe_extractall_tar(t, self._temp_dir)
            else:
                raise IOError(
                    f"Unsupported archive format: {self._input.suffix}. "
                    "Supported: directory, .zip, .tar, .tar.gz, .tar.bz2, .tar.xz"
                )
        except Exception as e:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            raise IOError(f"Failed to extract archive: {e}") from e
        self._root = self._temp_dir

    @staticmethod
    def _safe_extractall_zip(zf: zipfile.ZipFile, dest: Path) -> None:
        dest_resolved = dest.resolve()
        for member in zf.namelist():
            target = (dest / member).resolve()
            if not str(target).startswith(str(dest_resolved) + os.sep) and target != dest_resolved:
                raise IOError(f"Path traversal detected in archive: {member}")
        zf.extractall(dest)

    @staticmethod
    def _safe_extractall_tar(tf: tarfile.TarFile, dest: Path) -> None:
        dest_resolved = dest.resolve()
        for member in tf.getmembers():
            target = (dest / member.name).resolve()
            if not str(target).startswith(str(dest_resolved) + os.sep) and target != dest_resolved:
                raise IOError(f"Path traversal detected in archive: {member.name}")
        tf.extractall(dest)

    def get_file(self, domain: str, relative_path: str) -> Optional[Path]:
        if self._delegate:
            return self._delegate.get_file(domain, relative_path)
        # Raw filesystem mode
        prefix = DOMAIN_FS_MAP.get(domain, "")
        candidate = self._root / prefix / relative_path
        if candidate.exists():
            return candidate
        # Fallback: search recursively for the filename
        filename = Path(relative_path).name
        for match in self._root.rglob(filename):
            _log.debug("Resolved %s via search: %s", relative_path, match)
            return match
        return None

    def list_files(self, domain: str, prefix: str) -> List[Tuple[str, Path]]:
        if self._delegate:
            return self._delegate.list_files(domain, prefix)
        fs_prefix = DOMAIN_FS_MAP.get(domain, "")
        search_root = self._root / fs_prefix / prefix
        results = []
        if search_root.exists():
            for p in search_root.rglob("*"):
                if p.is_file():
                    rel = str(p.relative_to(self._root / fs_prefix))
                    results.append((rel, p))
        return results

    def get_device_info(self) -> dict:
        if self._delegate:
            return self._delegate.get_device_info()
        return {}

    def close(self) -> None:
        if self._delegate:
            self._delegate.close()
        if self._temp_dir:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
