"""WhatsApp parser — ChatStorage.sqlite.
Schema note: ZWACONTACT was removed in WhatsApp ~2022.
We probe for it and fall back to JID-based contact resolution.
"""
import sqlite3
from typing import List

from ..base import BaseParser, ParserError
from ..utils import apple_ts, probe_tables
from ...constants import BUNDLE_WHATSAPP
from ...logger import get_logger

_log = get_logger("parsers.whatsapp")

_DB_REL = "Documents/ChatStorage.sqlite"
_DOMAIN = f"AppDomain-{BUNDLE_WHATSAPP}"

_SQL_WITH_CONTACT = """
    SELECT
        m.ZTEXT              AS body,
        m.ZMESSAGEDATE       AS raw_date,
        m.ZISFROMME          AS sent,
        c.ZCONTACTJID        AS chat_jid,
        COALESCE(ct.ZPUSHNAME, m.ZFROMJID, c.ZCONTACTJID) AS contact
    FROM ZWAMESSAGE m
    LEFT JOIN ZWACHATSESSION c  ON m.ZCHATSESSION = c.Z_PK
    LEFT JOIN ZWACONTACT ct     ON m.ZFROMJID = ct.ZCONTACTJID
    ORDER BY m.ZMESSAGEDATE DESC
"""

_SQL_NO_CONTACT = """
    SELECT
        m.ZTEXT              AS body,
        m.ZMESSAGEDATE       AS raw_date,
        m.ZISFROMME          AS sent,
        c.ZCONTACTJID        AS chat_jid,
        COALESCE(m.ZFROMJID, c.ZCONTACTJID, '') AS contact
    FROM ZWAMESSAGE m
    LEFT JOIN ZWACHATSESSION c ON m.ZCHATSESSION = c.Z_PK
    ORDER BY m.ZMESSAGEDATE DESC
"""


class WhatsAppParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = self._get_db(_DOMAIN, _DB_REL)
        try:
            tables = probe_tables(conn)
            has_contact_table = "ZWACONTACT" in tables
            sql = _SQL_WITH_CONTACT if has_contact_table else _SQL_NO_CONTACT
            _log.info("WhatsApp schema: ZWACONTACT=%s", has_contact_table)
            rows = conn.execute(sql).fetchall()
            _log.info("Fetched %d WhatsApp messages", len(rows))
            return [
                {
                    "timestamp": apple_ts(r[1]),
                    "contact": r[4] or "",
                    "chat": r[3] or "",
                    "direction": "Sent" if r[2] else "Received",
                    "service": "WhatsApp",
                    "body": r[0] or "",
                    "attachments": [],
                }
                for r in rows
            ]
        finally:
            conn.close()
