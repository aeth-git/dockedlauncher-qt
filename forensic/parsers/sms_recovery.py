"""SMS deletion detection — identifies gaps in sms.db ROWID sequence.

A contiguous sequence of ROWIDs with no gaps indicates intact data.
Missing ROWIDs indicate deleted messages. This does NOT recover content —
it detects that deletions occurred and approximately when (bracketed by
adjacent message timestamps).

Also scans for WAL file presence alongside the database (uncommitted records).
"""
from pathlib import Path
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts
from ..constants import SMS_DB
from ..logger import get_logger

_log = get_logger("parsers.sms_recovery")


class SMSRecoveryParser(BaseParser):
    """Returns a list of detected deletion events (ROWID gaps in sms.db)."""

    def parse(self) -> List[dict]:
        db_path = self._source.get_file(*SMS_DB)
        if db_path is None:
            raise ParserError("sms.db not found in this backup")

        # Check for WAL file alongside
        wal_path = Path(str(db_path) + "-wal")
        shm_path = Path(str(db_path) + "-shm")
        wal_present = wal_path.exists() and wal_path.stat().st_size > 0

        try:
            conn = self._get_db(*SMS_DB)
        except Exception as e:
            raise ParserError(f"Cannot open sms.db: {e}")

        try:
            rows = conn.execute(
                "SELECT ROWID, date FROM message ORDER BY ROWID ASC"
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return []

        records = []
        prev_id = rows[0][0]
        prev_ts = rows[0][1]

        for rowid, ts in rows[1:]:
            gap = rowid - prev_id - 1
            if gap > 0:
                records.append({
                    "type": "Gap (deleted messages)",
                    "gap_start_rowid": prev_id + 1,
                    "gap_end_rowid": rowid - 1,
                    "deleted_count": gap,
                    "after_timestamp": apple_ts(prev_ts),
                    "before_timestamp": apple_ts(ts),
                    "detail": f"{gap} message{'s' if gap > 1 else ''} deleted "
                              f"between ROWID {prev_id} and {rowid}",
                })
            prev_id = rowid
            prev_ts = ts

        # WAL anomaly record
        if wal_present:
            records.insert(0, {
                "type": "WAL file present",
                "gap_start_rowid": 0,
                "gap_end_rowid": 0,
                "deleted_count": 0,
                "after_timestamp": "",
                "before_timestamp": "",
                "detail": f"sms.db-wal exists ({wal_path.stat().st_size:,} bytes) — "
                          "uncommitted records may not be visible through standard SQLite API",
            })

        total_msgs = len(rows)
        total_gaps = sum(r["deleted_count"] for r in records
                         if r["type"] == "Gap (deleted messages)")
        _log.info(
            "SMS recovery: %d messages present, ~%d deleted (gaps), WAL=%s",
            total_msgs, total_gaps, wal_present
        )

        if not records:
            records.append({
                "type": "No deletions detected",
                "gap_start_rowid": rows[0][0],
                "gap_end_rowid": rows[-1][0],
                "deleted_count": 0,
                "after_timestamp": apple_ts(rows[0][1]),
                "before_timestamp": apple_ts(rows[-1][1]),
                "detail": (f"ROWID sequence is contiguous ({total_msgs} messages). "
                           "No deletion artifacts detected."),
            })
        return records
