"""Discord parser — local SQLite cache (limited data, mainly guilds/channels)."""
from typing import List

from ..base import BaseParser, ParserError
from ..utils import unix_ts, probe_tables
from ...logger import get_logger

_log = get_logger("parsers.discord")

_BUNDLE = "com.hammerandchisel.discord"
_DB_CANDIDATES = [
    "Documents/discord.db",
    "Library/Application Support/HockeyApp/discord.db",
]

_MESSAGES_SQL = """
    SELECT
        id              AS id,
        content         AS body,
        timestamp       AS raw_ts,
        author_id       AS author_id,
        channel_id      AS channel_id
    FROM messages
    ORDER BY timestamp DESC
"""

_USERS_SQL = "SELECT id AS user_id, username AS name FROM users"
_CHANNELS_SQL = "SELECT id AS channel_id, name AS channel_name FROM channels"


class DiscordParser(BaseParser):
    def parse(self) -> List[dict]:
        domain = f"AppDomain-{_BUNDLE}"
        conn = None
        for rel in _DB_CANDIDATES:
            try:
                conn = self._get_db(domain, rel)
                break
            except (FileNotFoundError, ParserError):
                continue
        if conn is None:
            raise ParserError("Discord: local database not found in this backup. "
                              "Discord stores most data server-side; the local cache "
                              "is minimal and version-dependent.")
        try:
            tables = probe_tables(conn)
            if "messages" not in tables:
                raise ParserError(
                    "Discord: messages table not found. "
                    "The local cache for this backup version does not include message history."
                )

            user_map: dict = {}
            if "users" in tables:
                for r in conn.execute(_USERS_SQL).fetchall():
                    user_map[str(r["user_id"])] = r["name"] or str(r["user_id"])

            channel_map: dict = {}
            if "channels" in tables:
                for r in conn.execute(_CHANNELS_SQL).fetchall():
                    channel_map[str(r["channel_id"])] = r["channel_name"] or str(r["channel_id"])

            rows = conn.execute(_MESSAGES_SQL).fetchall()
            _log.info("Discord: %d messages", len(rows))
            return [{
                "id": r["id"],
                "timestamp": unix_ts(r["raw_ts"]) if r["raw_ts"] else None,
                "body": r["body"] or "",
                "contact": user_map.get(str(r["author_id"]), str(r["author_id"] or "")),
                "chat": channel_map.get(str(r["channel_id"]), str(r["channel_id"] or "")),
                "direction": "",
                "app": "Discord",
            } for r in rows]
        finally:
            conn.close()
