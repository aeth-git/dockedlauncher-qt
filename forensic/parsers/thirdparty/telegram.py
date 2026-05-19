"""Telegram parser — cache.db (NOT account.db).
Schema is probed at runtime because it changes between Telegram versions.
Timestamp: Unix epoch seconds (not Apple epoch).
"""
from typing import List

from ..base import BaseParser, ParserError
from ..utils import unix_ts, probe_tables
from ...constants import BUNDLE_TELEGRAM
from ...logger import get_logger

_log = get_logger("parsers.telegram")

_DOMAIN = f"AppDomain-{BUNDLE_TELEGRAM}"
_DB_REL = "Documents/cache.db"

# Known table names (probed at runtime)
_MSG_TABLES = {"messages_table", "t_messages", "messages"}
_USER_TABLES = {"users_table", "t_users", "users"}
_CHAT_TABLES = {"chats_table", "t_chats", "chats"}


class TelegramParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = self._get_db(_DOMAIN, _DB_REL)
        try:
            tables = set(probe_tables(conn))
            msg_table = next((t for t in _MSG_TABLES if t in tables), None)
            user_table = next((t for t in _USER_TABLES if t in tables), None)

            if not msg_table:
                raise ParserError(
                    f"No recognised messages table found. Available: {sorted(tables)}"
                )

            _log.info("Telegram tables: msg=%s user=%s", msg_table, user_table)

            # Probe message table columns
            cols_cur = conn.execute(f"PRAGMA table_info({msg_table})")
            col_names = {row[1] for row in cols_cur.fetchall()}

            date_col = next((c for c in ("date", "message_date", "timestamp") if c in col_names), None)
            text_col = next((c for c in ("message", "text", "content", "body") if c in col_names), None)
            from_col = next((c for c in ("from_id", "sender_id", "uid") if c in col_names), None)
            chat_col = next((c for c in ("to_id", "chat_id", "peer_id") if c in col_names), None)

            if not text_col:
                raise ParserError(f"Cannot identify text column in {msg_table}. Columns: {col_names}")

            select_parts = [f"COALESCE({text_col}, '') AS body"]
            if date_col:
                select_parts.append(f"{date_col} AS raw_date")
            else:
                select_parts.append("NULL AS raw_date")
            if from_col:
                select_parts.append(f"{from_col} AS sender_id")
            else:
                select_parts.append("NULL AS sender_id")
            if chat_col:
                select_parts.append(f"{chat_col} AS chat_id")
            else:
                select_parts.append("NULL AS chat_id")

            order = f"ORDER BY {date_col} DESC" if date_col else ""
            sql = f"SELECT {', '.join(select_parts)} FROM {msg_table} {order}"
            rows = conn.execute(sql).fetchall()
            _log.info("Fetched %d Telegram messages", len(rows))

            return [
                {
                    "timestamp": unix_ts(r[1]),
                    "contact": str(r[2]) if r[2] else "",
                    "chat": str(r[3]) if r[3] else "",
                    "direction": "",
                    "service": "Telegram",
                    "body": r[0] or "",
                    "attachments": [],
                }
                for r in rows
            ]
        finally:
            conn.close()
