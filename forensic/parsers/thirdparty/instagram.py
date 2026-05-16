"""Instagram parser — schema varies by version, raw DB browser fallback."""
import sqlite3
from typing import List

from ..base import BaseParser, ParserError
from ..utils import unix_ts, probe_tables
from ...constants import BUNDLE_INSTAGRAM
from ...logger import get_logger

_log = get_logger("parsers.instagram")

_DOMAIN = f"AppDomain-{BUNDLE_INSTAGRAM}"
_DB_CANDIDATES = [
    "Documents/instagram.db",
    "Library/Caches/instagram.db",
    "Documents/direct.db",
]


class InstagramParser(BaseParser):
    def parse(self) -> List[dict]:
        conn, rel = self._find_db()
        if conn is None:
            raise FileNotFoundError(
                "No Instagram database found. "
                f"Looked for: {', '.join(_DB_CANDIDATES)}"
            )
        try:
            tables = set(probe_tables(conn))
            _log.info("Instagram tables: %s", sorted(tables))
            msg_table = next(
                (t for t in ("direct_messages", "messages", "inbox_items", "threads")
                 if t in tables), None
            )
            if not msg_table:
                raise ParserError("SCHEMA_UNKNOWN")

            cols_cur = conn.execute(f"PRAGMA table_info({msg_table})")
            col_names = {row[1] for row in cols_cur.fetchall()}
            body_col = next((c for c in ("text", "body", "message", "content") if c in col_names), None)
            ts_col = next((c for c in ("timestamp", "created_at", "date") if c in col_names), None)
            sender_col = next((c for c in ("sender_id", "user_id", "author_id") if c in col_names), None)
            thread_col = next((c for c in ("thread_id", "conversation_id") if c in col_names), None)

            if not body_col:
                raise ParserError("SCHEMA_UNKNOWN")

            parts = [f"COALESCE({body_col}, '') AS body"]
            parts.append(f"{ts_col} AS raw_ts" if ts_col else "NULL AS raw_ts")
            parts.append(f"{sender_col} AS sender" if sender_col else "NULL AS sender")
            parts.append(f"{thread_col} AS thread" if thread_col else "NULL AS thread")
            order = f"ORDER BY {ts_col} DESC" if ts_col else ""
            rows = conn.execute(f"SELECT {', '.join(parts)} FROM {msg_table} {order}").fetchall()
            _log.info("Fetched %d Instagram messages", len(rows))
            return [
                {
                    "timestamp": unix_ts(r[1]),
                    "contact": str(r[2]) if r[2] else "",
                    "chat": str(r[3]) if r[3] else "",
                    "direction": "",
                    "service": "Instagram",
                    "body": r[0],
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
