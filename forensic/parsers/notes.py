"""Apple Notes parser — NoteStore.sqlite (group container backup)."""
import zlib
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.notes")

# In iTunes backups, group containers are stored under AppDomain-group.*
_NOTES_DB = ("AppDomain-group.com.apple.notes", "NoteStore.sqlite")

_NOTES_SQL = """
    SELECT
        n.Z_PK                          AS id,
        n.ZTITLE1                       AS title,
        n.ZCREATIONDATE1                AS created_raw,
        n.ZMODIFICATIONDATE1            AS modified_raw,
        n.ZSNIPPET                      AS snippet,
        n.ZISPASSWORDPROTECTED          AS locked,
        d.ZDATA                         AS body_data
    FROM ZICCLOUDSYNCINGOBJECT n
    LEFT JOIN ZICNOTEDATA d ON d.ZNOTE = n.Z_PK
    WHERE n.ZTITLE1 IS NOT NULL OR n.ZSNIPPET IS NOT NULL
    ORDER BY n.ZMODIFICATIONDATE1 DESC
"""


def _decode_note_body(data: bytes) -> str:
    """Attempt to extract plaintext from note body blob (zlib-compressed protobuf)."""
    if not data:
        return ""
    try:
        raw = zlib.decompress(data, wbits=-15)
        # Filter printable ASCII from the protobuf binary
        text = "".join(
            chr(b) for b in raw if 0x20 <= b < 0x7F or b in (0x0A, 0x09)
        )
        return text[:4096].strip()
    except Exception:
        return ""


class NotesParser(BaseParser):
    def parse(self) -> List[dict]:
        try:
            conn = self._get_db(*_NOTES_DB)
        except FileNotFoundError:
            raise ParserError("Apple Notes database not found in this backup")
        try:
            tables = probe_tables(conn)
            if "ZICCLOUDSYNCINGOBJECT" not in tables:
                raise ParserError("Notes: unexpected schema (ZICCLOUDSYNCINGOBJECT missing)")
            rows = conn.execute(_NOTES_SQL).fetchall()
            _log.info("Fetched %d note rows", len(rows))
            records = []
            for r in rows:
                body = ""
                if r["body_data"]:
                    body = _decode_note_body(bytes(r["body_data"]))
                records.append({
                    "id": r["id"],
                    "title": r["title"] or "(Untitled)",
                    "snippet": r["snippet"] or "",
                    "body": body,
                    "created": apple_ts(r["created_raw"]),
                    "modified": apple_ts(r["modified_raw"]),
                    "locked": bool(r["locked"]),
                })
            return records
        finally:
            conn.close()
