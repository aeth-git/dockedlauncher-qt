"""App Store purchases parser — itunesstored2.sqlitedb."""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.app_store")

_DB = ("HomeDomain", "Library/com.apple.iTunesStore/itunesstored2.sqlitedb")

# Table priority order — first match wins
_CANDIDATE_TABLES = [
    "purchased_software_map",
    "store_item",
    "app_library_entry",
    "software",
    "items",
]

# Keywords that indicate a purchase/app table when scanning unknown schemas
_APP_KEYWORDS = ("purchased", "software", "app", "item", "store")


def _col_names(conn, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


class AppStorePurchasesParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = self._get_db(*_DB)
        try:
            tables = probe_tables(conn)
            _log.info("AppStore tables: %s", tables)

            # Try known tables in priority order
            for tbl in _CANDIDATE_TABLES:
                if tbl in tables:
                    records = self._parse_table(conn, tbl)
                    _log.info("AppStore (%s): %d records", tbl, len(records))
                    return records

            # Fall back: look for any table whose name contains an app keyword
            for tbl in tables:
                tbl_lower = tbl.lower()
                if any(kw in tbl_lower for kw in _APP_KEYWORDS):
                    records = self._parse_table(conn, tbl)
                    _log.info("AppStore fallback (%s): %d records", tbl, len(records))
                    return records

            raise ParserError(
                f"No known App Store table found. Tables present: {tables}"
            )
        finally:
            conn.close()

    def _parse_table(self, conn, table: str) -> List[dict]:
        cols = _col_names(conn, table)
        col_set = set(cols)

        # Map column names to our standard output fields
        name_col = _first(col_set, ["software_name", "name", "app_name", "title", "itemName"])
        bundle_col = _first(col_set, ["bundle_id", "bundleID", "bundle_identifier"])
        date_col = _first(col_set, ["purchased_date", "purchase_date", "purchaseDate",
                                    "date_purchased", "date", "timestamp"])
        version_col = _first(col_set, ["installed_version_string", "version",
                                       "versionString", "app_version"])
        price_col = _first(col_set, ["price", "amount"])
        item_col = _first(col_set, ["adam_id", "item_id", "itemID", "adamId", "id"])

        # Build SELECT — only include columns that exist
        select_parts = []
        select_parts.append(f"{name_col} AS app_name" if name_col else "NULL AS app_name")
        select_parts.append(f"{bundle_col} AS bundle_id" if bundle_col else "NULL AS bundle_id")
        select_parts.append(f"{date_col} AS purchase_date" if date_col else "NULL AS purchase_date")
        select_parts.append(f"{version_col} AS version" if version_col else "NULL AS version")
        select_parts.append(f"{price_col} AS price" if price_col else "NULL AS price")
        select_parts.append(f"{item_col} AS item_id" if item_col else "NULL AS item_id")

        order_clause = f"ORDER BY {date_col} DESC" if date_col else ""
        sql = f"SELECT {', '.join(select_parts)} FROM {table} {order_clause} LIMIT 5000"

        rows = conn.execute(sql).fetchall()
        records = []
        for row in rows:
            records.append({
                "app_name": row[0] or "",
                "bundle_id": row[1] or "",
                "purchase_date": apple_ts(row[2]) if row[2] is not None else None,
                "version": row[3] or "",
                "price": _fmt_price(row[4]),
                "item_id": str(row[5]) if row[5] is not None else "",
            })
        return records


def _first(col_set: set, candidates: list):
    """Return the first candidate column name that exists in col_set, or None."""
    for c in candidates:
        if c in col_set:
            return c
    return None


def _fmt_price(val) -> str:
    if val is None:
        return ""
    try:
        f = float(val)
        if f == 0.0:
            return "Free"
        return f"${f:.2f}"
    except (TypeError, ValueError):
        return str(val)
