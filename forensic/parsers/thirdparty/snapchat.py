"""Snapchat parser — metadata only.
Snapchat stores content server-side; local DB has delivery metadata.
"""
import sqlite3
from typing import List

from ..base import BaseParser, ParserError
from ..utils import unix_ts, probe_tables
from ...constants import BUNDLE_SNAPCHAT
from ...logger import get_logger

_log = get_logger("parsers.snapchat")

_DOMAIN = f"AppDomain-{BUNDLE_SNAPCHAT}"
_DB_CANDIDATES = [
    "Documents/main.db",
    "Library/Application Support/Snapchat/arroyo.db",
    "Documents/snapchat.db",
]

METADATA_NOTICE = (
    "Snapchat stores content server-side. "
    "This view shows local delivery metadata only — not message content."
)


class SnapchatParser(BaseParser):
    def parse(self) -> List[dict]:
        conn, rel = self._find_db()
        if conn is None:
            raise FileNotFoundError(
                "No Snapchat database found. "
                f"Looked for: {', '.join(_DB_CANDIDATES)}"
            )
        try:
            tables = set(probe_tables(conn))
            _log.info("Snapchat tables: %s", sorted(tables))
            snap_table = next(
                (t for t in ("snap", "conversation_message", "snap_record", "message")
                 if t in tables), None
            )
            if not snap_table:
                raise ParserError("SCHEMA_UNKNOWN")

            cols_cur = conn.execute(f"PRAGMA table_info({snap_table})")
            col_names = {row[1] for row in cols_cur.fetchall()}
            ts_col = next((c for c in ("timestamp", "created_at", "sent_at", "date") if c in col_names), None)
            sender_col = next((c for c in ("sender_id", "from_user_id", "user_id") if c in col_names), None)
            type_col = next((c for c in ("media_type", "snap_type", "type") if c in col_names), None)

            parts = []
            parts.append(f"{ts_col} AS raw_ts" if ts_col else "NULL AS raw_ts")
            parts.append(f"COALESCE({sender_col}, '') AS sender" if sender_col else "'' AS sender")
            parts.append(f"COALESCE({type_col}, '') AS snap_type" if type_col else "'' AS snap_type")
            order = f"ORDER BY {ts_col} DESC" if ts_col else ""
            rows = conn.execute(f"SELECT {', '.join(parts)} FROM {snap_table} {order}").fetchall()
            _log.info("Fetched %d Snapchat records", len(rows))
            return [
                {
                    "timestamp": unix_ts(r[0]),
                    "contact": r[1],
                    "chat": "",
                    "direction": "",
                    "service": "Snapchat",
                    "body": f"[{r[2]}]" if r[2] else "[snap]",
                    "attachments": [],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def _find_db(self):
        for rel in _DB_CANDIDATES:
            path = self._source.get_file(_DOMAIN, rel)
            if path:
                uri = f"file:{path}?mode=ro"
                try:
                    conn = sqlite3.connect(uri, uri=True)
                    conn.execute("SELECT count(*) FROM sqlite_master")
                    return conn, rel
                except Exception:
                    continue
        return None, None
