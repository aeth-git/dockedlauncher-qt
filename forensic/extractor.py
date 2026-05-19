"""Full filesystem extraction — reconstructs directory layout from a backup source.

iTunes backup layout on disk:
  {root}/{file_id[:2]}/{file_id}   (hashed, no extension)

Extracted output layout:
  {dest}/HomeDomain/Library/SMS/sms.db
  {dest}/CameraRollDomain/Media/DCIM/100APPLE/IMG_0001.JPG
  ...

Raw filesystem dumps (ImageSource without a delegate) are copied
preserving their existing directory structure.
"""
import shutil
from pathlib import Path
from typing import Callable, List, Optional

from .logger import get_logger

_log = get_logger("extractor")


class ExtractionResult:
    __slots__ = ("total", "copied", "skipped", "errors")

    def __init__(self):
        self.total   = 0
        self.copied  = 0
        self.skipped = 0
        self.errors: List[str] = []


def _backup_parts(source):
    """Return (backup_root: Path, file_map: dict | None) for any source type.

    Returns (None, None) if the source does not support file-map extraction.
    file_map is None for raw filesystem dumps (copy the whole tree instead).
    """
    from .sources.backup import BackupSource
    from .sources.image import ImageSource

    if isinstance(source, BackupSource):
        return source._root, source._file_map

    if isinstance(source, ImageSource):
        if source._delegate is not None:
            return source._delegate._root, source._delegate._file_map
        if source._root is not None:
            return source._root, None          # raw filesystem dump

    return None, None


class BackupExtractor:
    """Extracts every file from a backup source to a readable directory tree."""

    def __init__(self, source, dest: Path, case_log=None):
        self._source   = source
        self._dest     = Path(dest)
        self._case_log = case_log

    def extract(
        self,
        domains: Optional[List[str]] = None,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
        cancelled_cb: Optional[Callable[[], bool]] = None,
    ) -> ExtractionResult:
        """Copy files to self._dest, rebuilding the original path structure.

        Args:
            domains:      If set, only extract files from these domain names.
            progress_cb:  Called as (done, total, current_rel_path) each iteration.
            cancelled_cb: If it returns True the extraction stops cleanly.

        Returns an ExtractionResult with counts and any error messages.
        """
        backup_root, file_map = _backup_parts(self._source)
        result = ExtractionResult()

        if backup_root is None:
            result.errors.append(
                "This source type does not support full file extraction."
            )
            return result

        if file_map is None:
            return self._extract_raw(backup_root, progress_cb, cancelled_cb)

        items = [
            ((domain, rel), fid)
            for (domain, rel), fid in file_map.items()
            if domains is None or domain in domains
        ]
        result.total = len(items)

        for i, ((domain, rel), file_id) in enumerate(items):
            if cancelled_cb and cancelled_cb():
                _log.info("Extraction cancelled after %d/%d files",
                          result.copied, result.total)
                break

            src = backup_root / file_id[:2] / file_id
            if not src.exists():
                result.skipped += 1
                if progress_cb:
                    progress_cb(i + 1, result.total, f"[missing] {domain}/{rel}")
                continue

            dest = self._dest / domain / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dest)
                result.copied += 1
            except OSError as e:
                result.errors.append(f"{domain}/{rel}: {e}")

            if progress_cb:
                progress_cb(i + 1, result.total, f"{domain}/{rel}")

        self._log_result(result)
        return result

    def _extract_raw(self, root: Path, progress_cb, cancelled_cb) -> ExtractionResult:
        """Copy a raw filesystem dump, preserving its directory structure."""
        result = ExtractionResult()
        all_files = [p for p in root.rglob("*") if p.is_file()]
        result.total = len(all_files)

        for i, src in enumerate(all_files):
            if cancelled_cb and cancelled_cb():
                break
            rel = src.relative_to(root)
            dest = self._dest / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dest)
                result.copied += 1
            except OSError as e:
                result.errors.append(str(e))
            if progress_cb:
                progress_cb(i + 1, result.total, str(rel))

        self._log_result(result)
        return result

    def _log_result(self, result: ExtractionResult) -> None:
        _log.info(
            "Extraction complete — copied %d, skipped %d, errors %d",
            result.copied, result.skipped, len(result.errors),
        )
        if self._case_log:
            self._case_log.log_export(str(self._dest), result.copied)
