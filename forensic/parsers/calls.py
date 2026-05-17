"""Call history parser — CallHistory.storedata (Core Data SQLite)."""
from typing import List

from .base import BaseParser
from .utils import apple_ts, fmt_duration
from ..constants import CALL_DB
from ..logger import get_logger

_log = get_logger("parsers.calls")

# Core Data table name is always ZCALLRECORD — hardcoded (never varies).
_SQL = """
    SELECT
        Z_PK                            AS id,
        ZADDRESS                        AS number,
        COALESCE(ZNAME, '')             AS name,
        ZDATE                           AS raw_date,
        ROUND(COALESCE(ZDURATION, 0))   AS duration_sec,
        COALESCE(ZORIGINATED, 0)        AS originated,
        COALESCE(ZANSWERED, 0)          AS answered,
        COALESCE(ZCALLTYPE, 1)          AS call_type,
        COALESCE(ZSERVICE_PROVIDER, '') AS provider
    FROM ZCALLRECORD
    ORDER BY ZDATE DESC
"""

_CALL_TYPES = {1: "Phone", 8: "FaceTime Audio", 16: "FaceTime Video"}


class CallParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = self._get_db(*CALL_DB)
        try:
            cur = conn.execute(_SQL)
            rows = cur.fetchall()
            _log.info("Fetched %d call rows", len(rows))
            records = []
            for row in rows:
                # ZDATE is Apple-epoch seconds (Core Data — never nanoseconds)
                ts = apple_ts(row["raw_date"])
                dur = int(row["duration_sec"] or 0)
                dur_fmt = fmt_duration(dur)
                records.append({
                    "id": row["id"],
                    "timestamp": ts,
                    "number": row["number"] or "",
                    "name": row["name"],
                    "direction": "Outgoing" if row["originated"] else "Incoming",
                    "status": "Answered" if row["answered"] else "Missed",
                    "call_type": _CALL_TYPES.get(int(row["call_type"] or 1), "Unknown"),
                    "duration": dur_fmt,
                    "provider": row["provider"],
                })
            return records
        finally:
            conn.close()
