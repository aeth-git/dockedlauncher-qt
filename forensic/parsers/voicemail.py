"""Voicemail parser — voicemail.db."""
from typing import List

from .base import BaseParser, ParserError
from .utils import unix_ts, probe_tables, fmt_duration
from ..logger import get_logger

_log = get_logger("parsers.voicemail")

_VOICEMAIL_DB = ("HomeDomain", "Library/Voicemail/voicemail.db")

_SQL = """
    SELECT
        ROWID                               AS id,
        remote_uid                          AS uid,
        date                                AS raw_date,
        sender                              AS sender,
        callback_num                        AS callback,
        duration                            AS duration_sec,
        COALESCE(trashed_date, 0)           AS trashed_date,
        flags                               AS flags
    FROM voicemail
    ORDER BY date DESC
"""


class VoicemailParser(BaseParser):
    def parse(self) -> List[dict]:
        try:
            conn = self._get_db(*_VOICEMAIL_DB)
        except FileNotFoundError:
            raise ParserError("Voicemail database not found in this backup")
        try:
            tables = probe_tables(conn)
            if "voicemail" not in tables:
                raise ParserError("voicemail.db: voicemail table missing")
            rows = conn.execute(_SQL).fetchall()
            _log.info("Fetched %d voicemail rows", len(rows))
            records = []
            for r in rows:
                dur = int(r["duration_sec"] or 0)
                dur_fmt = fmt_duration(dur)
                records.append({
                    "id": r["id"],
                    "timestamp": unix_ts(r["raw_date"]),
                    "sender": r["sender"] or "",
                    "callback": r["callback"] or "",
                    "duration": dur_fmt,
                    "duration_sec": dur,
                    "trashed": r["trashed_date"] > 0,
                    "flags": r["flags"] or 0,
                })
            return records
        finally:
            conn.close()
