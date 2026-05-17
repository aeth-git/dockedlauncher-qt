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


class SafariParser(BaseParser):
    def parse(self) -> List[dict]:
        return self._parse_history()

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

