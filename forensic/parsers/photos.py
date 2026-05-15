"""Photo indexer — walks DCIM directory."""
from pathlib import Path
from typing import List

from .base import BaseParser
from ..constants import DCIM_DOMAIN, DCIM_PREFIX
from ..logger import get_logger

_log = get_logger("parsers.photos")

IMAGE_EXTS = {".jpg", ".jpeg", ".heic", ".png", ".gif", ".bmp", ".tiff", ".tif"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".3gp"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS


class PhotoIndexer(BaseParser):
    def parse(self) -> List[dict]:
        files = self._source.list_files(DCIM_DOMAIN, DCIM_PREFIX)
        results = []
        for rel_path, local_path in files:
            ext = Path(rel_path).suffix.lower()
            if ext not in MEDIA_EXTS:
                continue
            try:
                size = local_path.stat().st_size
            except OSError:
                size = 0
            results.append({
                "rel_path": rel_path,
                "local_path": str(local_path),
                "filename": Path(rel_path).name,
                "size_bytes": size,
                "size": _fmt_size(size),
                "is_video": ext in VIDEO_EXTS,
                "ext": ext,
            })
        _log.info("Indexed %d media files", len(results))
        return results


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
