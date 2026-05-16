"""Viber parser — Contacts.data + Inbox.data (SQLite despite .data extension)."""
from typing import List

from ..base import BaseParser, ParserError
from ..utils import unix_ts, probe_tables
from ...logger import get_logger

_log = get_logger("parsers.viber")

_BUNDLE = "com.viber"
_CONTACTS_DB = "Documents/Contacts.data"
_MESSAGES_DB = "Documents/Inbox.data"

_CONTACTS_SQL = """
    SELECT
        ZCONTACT_ID     AS contact_id,
        ZDISPLAY_NAME   AS name,
        ZPHONE_NORMALIZED AS phone
    FROM ZVIBERCONTACT
"""

_MESSAGES_SQL = """
    SELECT
        ZMESSAGE_ID                 AS id,
        ZTEXT                       AS body,
        ZTIMESTAMP                  AS raw_ts,
        ZCONVERSATION_ID            AS conv_id,
        ZSENDER_VIBER_ID            AS sender_id,
        ZDIRECTION                  AS direction
    FROM ZVIBERMESSAGE
    ORDER BY ZTIMESTAMP DESC
"""


class ViberParser(BaseParser):
    def parse(self) -> List[dict]:
        domain = f"AppDomain-{_BUNDLE}"

        # Load contacts
        contact_map: dict = {}
        try:
            conn = self._get_db(domain, _CONTACTS_DB)
            try:
                tables = probe_tables(conn)
                if "ZVIBERCONTACT" in tables:
                    for r in conn.execute(_CONTACTS_SQL).fetchall():
                        contact_map[str(r["contact_id"])] = (
                            r["name"] or r["phone"] or str(r["contact_id"])
                        )
            finally:
                conn.close()
        except (FileNotFoundError, ParserError):
            pass

        try:
            conn = self._get_db(domain, _MESSAGES_DB)
        except FileNotFoundError:
            raise ParserError("Viber: Inbox.data not found in this backup")
        try:
            tables = probe_tables(conn)
            if "ZVIBERMESSAGE" not in tables:
                raise ParserError("Viber: ZVIBERMESSAGE table not found (schema changed)")
            rows = conn.execute(_MESSAGES_SQL).fetchall()
            _log.info("Viber: %d messages", len(rows))
            return [{
                "id": r["id"],
                "timestamp": unix_ts(r["raw_ts"]),
                "body": r["body"] or "",
                "contact": contact_map.get(str(r["sender_id"]), str(r["sender_id"] or "")),
                "chat": str(r["conv_id"] or ""),
                "direction": "Sent" if r["direction"] == 1 else "Received",
                "app": "Viber",
            } for r in rows]
        finally:
            conn.close()
