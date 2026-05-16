"""Apple Mail parser — Envelope Index SQLite database."""
from typing import List

from .base import BaseParser, ParserError
from .utils import unix_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.mail")

# The Envelope Index DB is in MailData; version number (V2–V10) varies
_MAIL_DB_CANDIDATES = [
    ("HomeDomain", f"Library/Mail/V{v}/MailData/Envelope Index")
    for v in range(10, 1, -1)
]

_MESSAGES_SQL = """
    SELECT
        m.ROWID             AS id,
        m.subject           AS subject,
        m.sender            AS sender,
        m.date_sent         AS raw_sent,
        m.date_received     AS raw_received,
        m.read              AS read,
        m.flagged           AS flagged,
        m.mailbox           AS mailbox_id,
        ma.url              AS mailbox_url
    FROM messages m
    LEFT JOIN mailboxes ma ON m.mailbox = ma.ROWID
    ORDER BY m.date_received DESC
    LIMIT 50000
"""


class MailParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = None
        for domain, rel in _MAIL_DB_CANDIDATES:
            try:
                conn = self._get_db(domain, rel)
                break
            except (FileNotFoundError, ParserError):
                continue
        if conn is None:
            raise ParserError("Apple Mail Envelope Index not found in this backup")
        try:
            tables = probe_tables(conn)
            if "messages" not in tables:
                raise ParserError("Mail Envelope Index: messages table missing")
            rows = conn.execute(_MESSAGES_SQL).fetchall()
            _log.info("Mail: fetched %d messages", len(rows))
            return [{
                "id": r["id"],
                "subject": r["subject"] or "(No Subject)",
                "sender": r["sender"] or "",
                "sent": unix_ts(r["raw_sent"]),
                "received": unix_ts(r["raw_received"]),
                "read": bool(r["read"]),
                "flagged": bool(r["flagged"]),
                "mailbox": r["mailbox_url"] or str(r["mailbox_id"] or ""),
            } for r in rows]
        finally:
            conn.close()
