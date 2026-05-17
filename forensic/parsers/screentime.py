"""Screen Time app usage parser — CoreData SQLite databases."""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables, fmt_duration
from ..logger import get_logger

_log = get_logger("parsers.screentime")

# Screen Time stores data across multiple paths; probe them in order
_SCREENTIME_DBS = [
    ("HomeDomain", "Library/Application Support/com.apple.remotemanagementd/RMAdminData"),
    ("HomeDomain", "Library/Application Support/com.apple.screentime/Local/RMAdminData"),
]

_USAGE_SQL = """
    SELECT
        ZBUNDLEIDENTIFIER       AS bundle_id,
        ZLAUNCHCOUNT            AS launches,
        ZUSAGETIME              AS usage_sec,
        ZFIRSTUSE               AS first_raw,
        ZLASTUSE                AS last_raw
    FROM ZUSAGETIMEDITEM
    ORDER BY ZUSAGETIME DESC
"""


class ScreenTimeParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = None
        for domain, rel in _SCREENTIME_DBS:
            try:
                conn = self._get_db(domain, rel)
                break
            except (FileNotFoundError, ParserError):
                continue
        if conn is None:
            raise ParserError("Screen Time database not found in this backup")
        try:
            tables = probe_tables(conn)
            records = []
            if "ZUSAGETIMEDITEM" in tables:
                for r in conn.execute(_USAGE_SQL).fetchall():
                    sec = int(r["usage_sec"] or 0)
                    records.append({
                        "bundle_id": r["bundle_id"] or "",
                        "launches": r["launches"] or 0,
                        "usage_sec": sec,
                        "usage_fmt": fmt_duration(sec),
                        "first_use": apple_ts(r["first_raw"]),
                        "last_use": apple_ts(r["last_raw"]),
                    })
            _log.info("Screen Time: %d app usage records", len(records))
            return records
        finally:
            conn.close()

