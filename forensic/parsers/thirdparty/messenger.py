"""Facebook Messenger parser.

Pre-Lightspeed (~pre-2020): standard readable SQLite.
Post-Lightspeed (~2020+): message columns contain encrypted blobs.
We detect which era by sampling message content.
"""
import sqlite3
from typing import List

from ..base import BaseParser, ParserError
from ..utils import unix_ts, probe_tables
from ...constants import BUNDLE_MESSENGER
from ...logger import get_logger

_log = get_logger("parsers.messenger")

_DOMAIN = f"AppDomain-{BUNDLE_MESSENGER}"
# DB path varies by Messenger version
_DB_CANDIDATES = [
    "Documents/msys/lightspeed-1/lightspeed.db",
    "Documents/msys/lightspeed-2/lightspeed.db",
    "Documents/msys/threads-40.db",
    "Documents/messenger.db",
    "Library/Caches/messenger.db",
]


class MessengerParser(BaseParser):
    def parse(self) -> List[dict]:
        conn, db_path = self._find_db()
        if conn is None:
            raise FileNotFoundError(
                "No Messenger database found. "
                f"Looked for: {', '.join(_DB_CANDIDATES)}"
            )
        try:
            return self._parse_db(conn, db_path)
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

    def _parse_db(self, conn, db_path: str) -> List[dict]:
        tables = set(probe_tables(conn))
        _log.info("Messenger tables at %s: %s", db_path, sorted(tables))

        # Try to find a messages table
        msg_table = next(
            (t for t in ("messages", "message", "table_messages", "lightspeed_message")
             if t in tables), None
        )
        if not msg_table:
            raise ParserError(
                "LIGHTSPEED_ENCRYPTED",
                # Signal to the view layer that a raw browser should be shown
            )

        cols_cur = conn.execute(f"PRAGMA table_info({msg_table})")
        col_names = {row[1] for row in cols_cur.fetchall()}
        body_col = next((c for c in ("body", "text", "message_text", "content") if c in col_names), None)
        ts_col = next((c for c in ("timestamp_ms", "timestamp", "created_at", "date") if c in col_names), None)
        sender_col = next((c for c in ("sender_id", "from_id", "author_id") if c in col_names), None)

        if not body_col:
            raise ParserError("LIGHTSPEED_ENCRYPTED")

        # Sample a few rows to check for encrypted content
        sample = conn.execute(f"SELECT {body_col} FROM {msg_table} LIMIT 5").fetchall()
        for (val,) in sample:
            if isinstance(val, bytes):
                raise ParserError("LIGHTSPEED_ENCRYPTED")

        parts = [f"COALESCE({body_col}, '') AS body"]
        parts.append(f"{ts_col} AS raw_ts" if ts_col else "NULL AS raw_ts")
        parts.append(f"{sender_col} AS sender" if sender_col else "NULL AS sender")
        order = f"ORDER BY {ts_col} DESC" if ts_col else ""
        rows = conn.execute(f"SELECT {', '.join(parts)} FROM {msg_table} {order}").fetchall()
        _log.info("Fetched %d Messenger messages", len(rows))
        return [
            {
                "timestamp": unix_ts(r[1]),
                "contact": str(r[2]) if r[2] else "",
                "chat": "",
                "direction": "",
                "service": "Messenger",
                "body": r[0],
                "attachments": [],
            }
            for r in rows
        ]
