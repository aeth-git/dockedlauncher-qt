"""Safari browser history and bookmarks parser."""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.safari")

_SAFARI_HISTORY_DB = ("HomeDomain", "Library/Safari/History.db")

_HISTORY_SQL = """
    SELECT
        hv.id               AS id,
        hi.url              AS url,
        hv.title            AS title,
        hv.visit_time       AS raw_ts,
        hv.load_successful  AS ok,
        hi.visit_count      AS visit_count
    FROM history_visits hv
    JOIN history_items hi ON hv.history_item = hi.id
    ORDER BY hv.visit_time DESC
"""

_BOOKMARKS_DB = ("HomeDomain", "Library/Safari/Bookmarks.db")

_BOOKMARKS_SQL = """
    SELECT
        b.id            AS id,
        b.title         AS title,
        u.url           AS url,
        b.special_id    AS folder
    FROM bookmarks b
    LEFT JOIN bookmark_urls u ON b.id = u.bookmark_id
    WHERE b.type = 1
    ORDER BY b.id
"""


class SafariParser(BaseParser):
    def parse(self) -> List[dict]:
        records = []
        records.extend(self._parse_history())
        return records

    def _parse_history(self) -> List[dict]:
        try:
            conn = self._get_db(*_SAFARI_HISTORY_DB)
        except FileNotFoundError:
            raise ParserError("Safari History.db not found in this backup")
        try:
            tables = probe_tables(conn)
            if "history_visits" not in tables or "history_items" not in tables:
                raise ParserError("Safari History.db: unexpected schema")
            rows = conn.execute(_HISTORY_SQL).fetchall()
            _log.info("Fetched %d Safari history rows", len(rows))
            return [{
                "id": r["id"],
                "type": "history",
                "timestamp": apple_ts(r["raw_ts"]),
                "url": r["url"] or "",
                "title": r["title"] or "",
                "visit_count": r["visit_count"] or 1,
                "load_ok": bool(r["ok"]),
            } for r in rows]
        finally:
            conn.close()

    def parse_bookmarks(self) -> List[dict]:
        try:
            conn = self._get_db(*_BOOKMARKS_DB)
        except (FileNotFoundError, ParserError):
            return []
        try:
            tables = probe_tables(conn)
            if "bookmarks" not in tables:
                return []
            rows = conn.execute(_BOOKMARKS_SQL).fetchall()
            return [{
                "id": r["id"],
                "type": "bookmark",
                "title": r["title"] or "",
                "url": r["url"] or "",
                "folder": r["folder"] or 0,
            } for r in rows]
        finally:
            conn.close()
