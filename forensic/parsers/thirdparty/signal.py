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
        # --- Build thread_id → phone_number map from 'threads' table (if present) ---
        thread_map: dict = {}
        tables = set(probe_tables(conn))
        if "threads" in tables:
            t_cols_cur = conn.execute("PRAGMA table_info(threads)")
            t_col_names = {row[1] for row in t_cols_cur.fetchall()}
            id_col = next(
                (c for c in ("uniqueId", "threadId", "id") if c in t_col_names), None
            )
            phone_col = next(
                (c for c in ("contactPhoneNumber", "phoneNumber", "address") if c in t_col_names),
                None,
            )
            if id_col and phone_col:
                for tid, phone in conn.execute(
                    f"SELECT {id_col}, {phone_col} FROM threads"
                ).fetchall():
                    if tid is not None:
                        thread_map[str(tid)] = phone or ""
                _log.info("Loaded %d thread entries (YapDB era)", len(thread_map))

        # --- Probe interactions columns ---
        cols_cur = conn.execute("PRAGMA table_info(interactions)")
        col_names = {row[1] for row in cols_cur.fetchall()}
        body_col = next((c for c in ("body", "text", "content") if c in col_names), None)
        date_col = next((c for c in ("timestamp", "date", "receivedAt") if c in col_names), None)
        thread_ref_col = next(
            (c for c in ("threadUniqueId", "thread_id", "conversationId") if c in col_names),
            None,
        )
        type_col = next(
            (c for c in ("recordType", "messageType", "type") if c in col_names), None
        )

        if not body_col:
            raise ParserError(f"Cannot identify body column in interactions. Cols: {col_names}")

        # YapDB recordType: 101 = incoming (Received), 102 = outgoing (Sent).
        # Older versions: 0 = Received, 1 = Sent.
        _YAP_DIRECTION = {
            101: "Received",
            102: "Sent",
            0: "Received",
            1: "Sent",
        }

        select_parts = [f"COALESCE({body_col}, '') AS body"]
        select_parts.append(f"{date_col} AS raw_ts" if date_col else "NULL AS raw_ts")
        select_parts.append(f"{thread_ref_col} AS thread_ref" if thread_ref_col else "NULL AS thread_ref")
        select_parts.append(f"{type_col} AS record_type" if type_col else "NULL AS record_type")

        order = f"ORDER BY {date_col} DESC" if date_col else ""
        sql = f"SELECT {', '.join(select_parts)} FROM interactions {order}"
        rows = conn.execute(sql).fetchall()
        _log.info("Fetched %d Signal messages (YapDB era)", len(rows))

        result = []
        for r in rows:
            body, raw_ts, thread_ref, record_type = r[0], r[1], r[2], r[3]
            contact = thread_map.get(str(thread_ref), "") if thread_ref is not None else ""
            direction = _YAP_DIRECTION.get(record_type, "") if record_type is not None else ""
            result.append(
                {
                    "timestamp": unix_ts(raw_ts),
                    "contact": contact,
                    "chat": contact,
                    "direction": direction,
                    "service": "Signal",
                    "body": body,
                    "attachments": [],
                }
            )
        return result

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
            # Probe for contact/author phone number (incoming messages only)
            contact_col = next(
                (c for c in ("authorPhoneNumber", "authorId", "sourcePhoneNumber") if c in col_names),
                None,
            ) if direction == "Received" else None

            parts = [f"COALESCE({body_col}, '') AS body"]
            parts.append(f"{ts_col} AS raw_ts" if ts_col else "NULL AS raw_ts")
            parts.append(f"{contact_col} AS contact_val" if contact_col else "NULL AS contact_val")
            order = f"ORDER BY {ts_col} DESC" if ts_col else ""
            rows = conn.execute(f"SELECT {', '.join(parts)} FROM {table} {order}").fetchall()
            for r in rows:
                contact = r[2] or "" if r[2] is not None else ""
                records.append({
                    "timestamp": unix_ts(r[1]),
                    "contact": contact,
                    "chat": contact,
                    "direction": direction,
                    "service": "Signal",
                    "body": r[0],
                    "attachments": [],
                })
        _log.info("Fetched %d Signal messages (GRDB era)", len(records))
        return sorted(records, key=lambda x: x["timestamp"] or "", reverse=True)
