"""Skype parser — main.db SQLite database."""
from typing import List

from ..base import BaseParser, ParserError
from ..utils import unix_ts, probe_tables
from ...logger import get_logger

_log = get_logger("parsers.skype")

_BUNDLE = "com.skype.skype"
_SKYPE_DB = "Documents/main.db"

_MESSAGES_SQL = """
    SELECT
        m.id                AS id,
        m.body_xml          AS body,
        m.timestamp         AS raw_ts,
        m.author            AS author,
        m.from_dispname     AS sender_name,
        m.convo_id          AS convo_id,
        c.displayname       AS chat_name,
        m.type              AS msg_type
    FROM Messages m
    LEFT JOIN Conversations c ON m.convo_id = c.id
    WHERE m.type IN (61, 60)   -- regular messages and rich text
    ORDER BY m.timestamp DESC
"""

_CONTACTS_SQL = """
    SELECT
        skypename   AS username,
        displayname AS name
    FROM Contacts
"""


class SkypeParser(BaseParser):
    def parse(self) -> List[dict]:
        domain = f"AppDomain-{_BUNDLE}"
        try:
            conn = self._get_db(domain, _SKYPE_DB)
        except FileNotFoundError:
            raise ParserError("Skype: main.db not found in this backup")
        try:
            tables = probe_tables(conn)
            if "Messages" not in tables:
                raise ParserError("Skype: Messages table not found (schema changed)")

            contact_map: dict = {}
            if "Contacts" in tables:
                for r in conn.execute(_CONTACTS_SQL).fetchall():
                    contact_map[r["username"]] = r["name"] or r["username"]

            rows = conn.execute(_MESSAGES_SQL).fetchall()
            _log.info("Skype: %d messages", len(rows))
            return [{
                "id": r["id"],
                "timestamp": unix_ts(r["raw_ts"]),
                "body": _strip_xml_tags(r["body"] or ""),
                "contact": r["sender_name"] or contact_map.get(r["author"], r["author"] or ""),
                "chat": r["chat_name"] or str(r["convo_id"] or ""),
                "direction": "",
                "app": "Skype",
            } for r in rows]
        finally:
            conn.close()


def _strip_xml_tags(text: str) -> str:
    """Remove XML/HTML tags from Skype's body_xml field."""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()
