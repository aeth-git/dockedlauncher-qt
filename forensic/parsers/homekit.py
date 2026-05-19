"""HomeKit accessories parser — reads from homed CoreData SQLite store."""
from typing import List

from .base import BaseParser, ParserError
from .utils import probe_tables
from ..logger import get_logger

_log = get_logger("parsers.homekit")

_DB_CANDIDATES = [
    ("AppDomain-com.apple.homed", "Library/HomeKit/datastore.sqlite"),
    ("AppDomain-com.apple.homed", "Library/HomeKit/store.sqlite"),
]

_ACCESSORY_SQL = """
SELECT
    h.ZNAME AS home_name,
    r.ZNAME AS room_name,
    a.ZNAME AS accessory_name,
    a.ZMANUFACTURER AS manufacturer,
    a.ZMODEL AS model,
    a.ZFIRMWAREREVISION AS firmware,
    a.ZCATEGORY AS category,
    a.ZREACHABLE AS is_reachable
FROM ZACCESSORY a
LEFT JOIN ZHOME h ON a.ZHOME = h.Z_PK
LEFT JOIN ZROOM r ON a.ZROOM = r.Z_PK
ORDER BY h.ZNAME, r.ZNAME, a.ZNAME
"""


class HomeKitParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = self._open_db()
        try:
            return self._parse_accessories(conn)
        finally:
            conn.close()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _open_db(self):
        """Try each DB candidate in order; raise ParserError if none found."""
        for domain, rel in _DB_CANDIDATES:
            try:
                conn = self._get_db(domain, rel)
                _log.info("HomeKit DB opened: %s/%s", domain, rel)
                return conn
            except (FileNotFoundError, ParserError):
                continue
        raise ParserError("No HomeKit database found in this backup")

    def _parse_accessories(self, conn) -> List[dict]:
        tables = probe_tables(conn)
        _log.debug("HomeKit tables: %s", tables)

        # Check for ZACCESSORY (CoreData standard name)
        accessory_table = None
        if "ZACCESSORY" in tables:
            accessory_table = "ZACCESSORY"
        else:
            # Fall back to any table with "ACCESSORY" in the name
            for t in tables:
                if "accessory" in t.lower():
                    accessory_table = t
                    break

        if accessory_table is None:
            _log.warning("ZACCESSORY table not found; tables=%s", tables)
            return []

        # Run the structured query only if all three join tables exist
        has_home = "ZHOME" in tables
        has_room = "ZROOM" in tables

        if accessory_table == "ZACCESSORY" and has_home and has_room:
            rows = conn.execute(_ACCESSORY_SQL).fetchall()
        else:
            # Degrade gracefully — pull only from the accessory table itself
            cols = self._column_names(conn, accessory_table)
            sel_name = "ZNAME" if "ZNAME" in cols else (cols[0] if cols else "rowid")
            rows_raw = conn.execute(
                f"SELECT {sel_name} FROM {accessory_table}"
            ).fetchall()
            return [{
                "home_name": None,
                "room_name": None,
                "accessory_name": str(r[0]) if r[0] else None,
                "manufacturer": None,
                "model": None,
                "firmware": None,
                "category": None,
                "is_reachable": None,
            } for r in rows_raw]

        records = []
        for row in rows:
            records.append({
                "home_name":      row["home_name"],
                "room_name":      row["room_name"],
                "accessory_name": row["accessory_name"],
                "manufacturer":   row["manufacturer"],
                "model":          row["model"],
                "firmware":       row["firmware"],
                "category":       row["category"],
                "is_reachable":   bool(row["is_reachable"]) if row["is_reachable"] is not None else None,
            })

        _log.info("HomeKit: %d accessories parsed", len(records))
        return records

    @staticmethod
    def _column_names(conn, table: str) -> List[str]:
        cur = conn.execute(f"PRAGMA table_info({table})")
        return [r[1] for r in cur.fetchall()]
