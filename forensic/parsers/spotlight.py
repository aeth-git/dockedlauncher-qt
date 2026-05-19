"""Spotlight CoreSpotlight parser — Store.db."""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.spotlight")

_DB = ("HomeDomain", "Library/Spotlight/CoreSpotlight/Store.db")

# Known table names to probe, in priority order
_KNOWN_TABLES = [
    "spotlightItems",
    "metadata",
    "index_attributes",
    "PLSpotlightEntry",
    "z_spotlight_item",
]

# Column name fragments to look for (lowercased)
_TITLE_HINTS = ("title", "name")
_URL_HINTS = ("url", "path")
_CREATED_HINTS = ("created",)
_MODIFIED_HINTS = ("modified",)
_CONTENT_TYPE_HINTS = ("content_type", "contenttype", "type")
_DOMAIN_HINTS = ("domain",)


def _pick_col(cols: set, hints: tuple):
    """Return the first column name (case-insensitive) that matches any hint."""
    cols_lower = {c.lower(): c for c in cols}
    for hint in hints:
        if hint in cols_lower:
            return cols_lower[hint]
    return None


class SpotlightParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = self._get_db(*_DB)
        try:
            tables = probe_tables(conn)
            found_table = None
            for candidate in _KNOWN_TABLES:
                if candidate in tables:
                    found_table = candidate
                    break

            if found_table is None:
                raise ParserError(
                    f"Spotlight: no known tables found. Tables: {tables}"
                )

            _log.info("Spotlight: using table %r from %s", found_table, tables)

            # Discover actual columns via PRAGMA
            col_rows = conn.execute(
                f"PRAGMA table_info({found_table})"
            ).fetchall()
            cols = {r[1] for r in col_rows}   # r[1] is column name

            title_col = _pick_col(cols, _TITLE_HINTS)
            url_col = _pick_col(cols, _URL_HINTS)
            created_col = _pick_col(cols, _CREATED_HINTS)
            modified_col = _pick_col(cols, _MODIFIED_HINTS)
            content_type_col = _pick_col(cols, _CONTENT_TYPE_HINTS)
            domain_col = _pick_col(cols, _DOMAIN_HINTS)

            # Build SELECT clause dynamically
            select_parts = []
            if title_col:
                select_parts.append(f"{title_col} AS _title")
            else:
                select_parts.append("NULL AS _title")

            if url_col:
                select_parts.append(f"{url_col} AS _url")
            else:
                select_parts.append("NULL AS _url")

            if created_col:
                select_parts.append(f"{created_col} AS _created")
            else:
                select_parts.append("NULL AS _created")

            if modified_col:
                select_parts.append(f"{modified_col} AS _modified")
            else:
                select_parts.append("NULL AS _modified")

            if content_type_col:
                select_parts.append(f"{content_type_col} AS _content_type")
            else:
                select_parts.append("NULL AS _content_type")

            if domain_col:
                select_parts.append(f"{domain_col} AS _domain")
            else:
                select_parts.append("NULL AS _domain")

            sql = (
                f"SELECT {', '.join(select_parts)} "
                f"FROM {found_table} "
                f"LIMIT 10000"
            )
            rows = conn.execute(sql).fetchall()
            _log.info("Spotlight: %d rows from %r", len(rows), found_table)

            records = []
            for row in rows:
                records.append({
                    "title": row[0] or "",
                    "url": row[1] or "",
                    "created": apple_ts(row[2]),
                    "modified": apple_ts(row[3]),
                    "content_type": row[4] or "",
                    "domain": row[5] or "",
                })
            return records
        finally:
            conn.close()
