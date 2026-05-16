"""Kik Messenger parser — kik.sqlite (AppGroup container)."""
from typing import List

from ..base import BaseParser, ParserError
from ..utils import unix_ts, probe_tables
from ...logger import get_logger

_log = get_logger("parsers.kik")

_BUNDLE = "com.kik.chat"

# Kik stores its DB in an AppGroup container; the backup path can vary.
# iLEAPP uses AppGroup- prefix; in backups the container is registered under group.kik.chat
_DB_CANDIDATES = [
    "kik.sqlite",
    "Documents/kik.sqlite",
]

_CONTACTS_SQL = "SELECT BJID AS jid, DISPLAY_NAME AS name FROM ZKIKPERSON"

_MESSAGES_SQL = """
    SELECT
        Z_PK            AS id,
        BODY            AS body,
        TIMESTAMP       AS raw_ts,
        SENDER_JID      AS sender_jid,
        CONVO_ID        AS convo_id,
        WAS_ME          AS was_me
    FROM ZKIKMESSAGE
    ORDER BY TIMESTAMP DESC
"""


class KikParser(BaseParser):
    def parse(self) -> List[dict]:
        domain = f"AppDomain-{_BUNDLE}"
        conn = None
        for rel in _DB_CANDIDATES:
            try:
                conn = self._get_db(domain, rel)
                break
            except (FileNotFoundError, ParserError):
                continue

        # Also try AppGroup
        if conn is None:
            for rel in _DB_CANDIDATES:
                try:
                    conn = self._get_db(f"AppDomain-group.{_BUNDLE}", rel)
                    break
                except (FileNotFoundError, ParserError):
                    continue

        if conn is None:
            raise ParserError("Kik: kik.sqlite not found in this backup")

        try:
            tables = probe_tables(conn)
            if "ZKIKMESSAGE" not in tables:
                raise ParserError("Kik: ZKIKMESSAGE table not found (schema changed)")

            contact_map: dict = {}
            if "ZKIKPERSON" in tables:
                try:
                    for r in conn.execute(_CONTACTS_SQL).fetchall():
                        contact_map[r["jid"]] = r["name"] or r["jid"]
                except Exception:
                    pass

            rows = conn.execute(_MESSAGES_SQL).fetchall()
            _log.info("Kik: %d messages", len(rows))
            return [{
                "id": r["id"],
                "timestamp": unix_ts(r["raw_ts"]),
                "body": r["body"] or "",
                "contact": contact_map.get(r["sender_jid"], r["sender_jid"] or ""),
                "chat": str(r["convo_id"] or ""),
                "direction": "Sent" if r["was_me"] else "Received",
                "app": "Kik",
            } for r in rows]
        finally:
            conn.close()
