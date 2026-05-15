"""Signal parser — signal.sqlite.

Two eras:
  Pre-2021 (YapDatabase): standard SQLite, tables 'threads' + 'interactions'.
  Post-2021 (GRDB/SQLCipher): database is encrypted. Requires sqlcipher3.

We detect which era by attempting a standard sqlite3 open.
If it fails with DatabaseError, we report the encryption status clearly.
"""
import sqlite3
from typing import List

from ..base import BaseParser, ParserError
from ..utils import unix_ts, probe_tables
from ...constants import BUNDLE_SIGNAL
from ...logger import get_logger

_log = get_logger("parsers.signal")

_DOMAIN = f"AppDomain-{BUNDLE_SIGNAL}"
_DB_REL = "Documents/signal.sqlite"


class SignalParser(BaseParser):
    def parse(self) -> List[dict]:
        path = self._get_db_path(_DOMAIN, _DB_REL)
        if path is None:
            raise FileNotFoundError(f"Signal database not found: {_DOMAIN}/{_DB_REL}")

        # Try standard (unencrypted) open first
        uri = f"file:{path}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
            conn.execute("SELECT count(*) FROM sqlite_master")
        except sqlite3.DatabaseError:
            raise ParserError(
                "Signal database is encrypted (post-2021 GRDB/SQLCipher format).\n\n"
                "Decryption requires the Signal master key, which is only accessible "
                "from a jailbroken device. This version of the tool supports "
                "pre-2021 (YapDatabase) Signal backups only."
            )

        try:
            tables = set(probe_tables(conn))
            _log.info("Signal tables: %s", sorted(tables))

            # YapDatabase-era schema
            if "model_IncomingMessage" in tables or "model_OutgoingMessage" in tables:
                return self._parse_grdb_era(conn)
            elif "interactions" in tables:
                return self._parse_yap_era(conn)
            else:
                raise ParserError(
                    f"Unrecognised Signal schema. Tables found: {sorted(tables)}"
                )
        finally:
            conn.close()

    def _parse_yap_era(self, conn) -> List[dict]:
        """YapDatabase era — 'interactions' table."""
        cols_cur = conn.execute("PRAGMA table_info(interactions)")
        col_names = {row[1] for row in cols_cur.fetchall()}
        body_col = next((c for c in ("body", "text", "content") if c in col_names), None)
        date_col = next((c for c in ("timestamp", "date", "receivedAt") if c in col_names), None)

        if not body_col:
            raise ParserError(f"Cannot identify body column in interactions. Cols: {col_names}")

        parts = [f"COALESCE({body_col}, '') AS body"]
        parts.append(f"{date_col} AS raw_ts" if date_col else "NULL AS raw_ts")
        order = f"ORDER BY {date_col} DESC" if date_col else ""
        sql = f"SELECT {', '.join(parts)} FROM interactions {order}"
        rows = conn.execute(sql).fetchall()
        _log.info("Fetched %d Signal messages (YapDB era)", len(rows))
        return [
            {
                "timestamp": unix_ts(r[1]),
                "contact": "",
                "chat": "",
                "direction": "",
                "service": "Signal",
                "body": r[0],
                "attachments": [],
            }
            for r in rows
        ]

    def _parse_grdb_era(self, conn) -> List[dict]:
        """GRDB era — model_IncomingMessage / model_OutgoingMessage tables."""
        records = []
        for table, direction in [("model_IncomingMessage", "Received"),
                                   ("model_OutgoingMessage", "Sent")]:
            cols_cur = conn.execute(f"PRAGMA table_info({table})")
            col_names = {row[1] for row in cols_cur.fetchall()}
            body_col = next((c for c in ("body", "text") if c in col_names), None)
            ts_col = next((c for c in ("timestamp", "receivedAt", "sentAt") if c in col_names), None)
            if not body_col:
                continue
            parts = [f"COALESCE({body_col}, '') AS body"]
            parts.append(f"{ts_col} AS raw_ts" if ts_col else "NULL AS raw_ts")
            order = f"ORDER BY {ts_col} DESC" if ts_col else ""
            rows = conn.execute(f"SELECT {', '.join(parts)} FROM {table} {order}").fetchall()
            for r in rows:
                records.append({
                    "timestamp": unix_ts(r[1]),
                    "contact": "",
                    "chat": "",
                    "direction": direction,
                    "service": "Signal",
                    "body": r[0],
                    "attachments": [],
                })
        _log.info("Fetched %d Signal messages (GRDB era)", len(records))
        return sorted(records, key=lambda x: x["timestamp"] or "", reverse=True)
