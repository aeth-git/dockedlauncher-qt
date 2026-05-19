"""SMS/iMessage parser — sms.db"""
from typing import List

from .base import BaseParser
from .utils import apple_ts, keyed_archive_str
from ..constants import SMS_DB
from ..logger import get_logger

_log = get_logger("parsers.messages")

_SQL = """
    SELECT
        m.ROWID                 AS id,
        COALESCE(h.id, '')      AS contact,
        COALESCE(m.text, '')    AS body_text,
        m.attributedBody        AS body_blob,
        m.is_from_me            AS sent,
        COALESCE(m.service, '') AS service,
        m.cache_has_attachments AS has_attachments,
        m.date                  AS raw_date,
        COALESCE(c.chat_identifier, '') AS chat
    FROM message m
    LEFT JOIN handle h          ON m.handle_id = h.ROWID
    LEFT JOIN chat_message_join cmj ON m.ROWID  = cmj.message_id
    LEFT JOIN chat c            ON cmj.chat_id   = c.ROWID
    ORDER BY m.date DESC
"""

_ATTACH_SQL = """
    SELECT a.filename, a.mime_type
    FROM attachment a
    JOIN message_attachment_join maj ON a.ROWID = maj.attachment_id
    WHERE maj.message_id = ?
"""


class SMSParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = self._get_db(*SMS_DB)
        try:
            records = []
            cur = conn.execute(_SQL)
            rows = cur.fetchall()
            _log.info("Fetched %d message rows", len(rows))
            for row in rows:
                body = row["body_text"]
                if not body and row["body_blob"]:
                    body = keyed_archive_str(bytes(row["body_blob"]))

                attachments = []
                if row["has_attachments"]:
                    try:
                        a_cur = conn.execute(_ATTACH_SQL, (row["id"],))
                        attachments = [
                            {"filename": r[0] or "", "mime_type": r[1] or ""}
                            for r in a_cur.fetchall()
                        ]
                    except Exception:
                        pass

                records.append({
                    "id": row["id"],
                    "timestamp": apple_ts(row["raw_date"]),
                    "contact": row["contact"],
                    "chat": row["chat"],
                    "direction": "Sent" if row["sent"] else "Received",
                    "service": row["service"],
                    "body": body,
                    "attachments": attachments,
                })
            return records
        finally:
            conn.close()
