"""LINE messenger parser — naver_line (SQLite database)."""
from typing import List

from ..base import BaseParser, ParserError
from ..utils import unix_ts, probe_tables
from ...logger import get_logger

_log = get_logger("parsers.line")

_BUNDLE = "jp.naver.line"
_LINE_DB = "Documents/naver_line"

_CONTACTS_SQL = """
    SELECT
        mid         AS mid,
        m_name      AS name
    FROM contact
"""

_MESSAGES_SQL = """
    SELECT
        id              AS id,
        chat_id         AS chat_id,
        from_mid        AS sender_mid,
        content         AS body,
        deliver_time    AS raw_ts,
        type            AS msg_type
    FROM chat_history
    ORDER BY deliver_time DESC
"""


class LINEParser(BaseParser):
    def parse(self) -> List[dict]:
        domain = f"AppDomain-{_BUNDLE}"
        try:
            conn = self._get_db(domain, _LINE_DB)
        except FileNotFoundError:
            raise ParserError("LINE: naver_line database not found in this backup")
        try:
            tables = probe_tables(conn)
            if "chat_history" not in tables:
                raise ParserError("LINE: chat_history table not found (schema changed)")

            # Build contact map
            contact_map: dict = {}
            if "contact" in tables:
                for r in conn.execute(_CONTACTS_SQL).fetchall():
                    contact_map[r["mid"]] = r["name"] or r["mid"]

            rows = conn.execute(_MESSAGES_SQL).fetchall()
            _log.info("LINE: %d messages", len(rows))
            return [{
                "id": r["id"],
                "timestamp": unix_ts(r["raw_ts"]),
                "body": r["body"] or "",
                "contact": contact_map.get(r["sender_mid"], r["sender_mid"] or ""),
                "chat": str(r["chat_id"] or ""),
                "direction": "Sent" if r["sender_mid"] == "u0" else "Received",
                "app": "LINE",
            } for r in rows]
        finally:
            conn.close()
