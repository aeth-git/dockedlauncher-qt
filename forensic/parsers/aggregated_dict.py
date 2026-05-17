"""AggregatedDictParser — iOS AggregateDictionary metrics store.

Handles two layouts:
  Layout 1 (iOS 12-14): 'measurements' table
  Layout 2 (iOS 15+):   'key_store' + 'value_store' tables
"""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.aggregated_dict")

_AGGDICT_DB = ("HomeDomain", "Library/AggregateDictionary/ADDataStore.sqlitedb")

_SQL_LAYOUT1 = """
    SELECT key, startDate, endDate, value, unit
    FROM measurements
    ORDER BY startDate DESC
    LIMIT 10000
"""

_SQL_LAYOUT2 = """
    SELECT k.key, v.start_date, v.end_date, v.double_value, v.string_value
    FROM value_store v
    LEFT JOIN key_store k ON v.key_id = k.id
    ORDER BY v.start_date DESC
    LIMIT 10000
"""


class AggregatedDictParser(BaseParser):
    """Parse iOS AggregatedDictionary database for system metrics."""

    def parse(self) -> List[dict]:
        try:
            conn = self._get_db(*_AGGDICT_DB)
        except FileNotFoundError:
            raise ParserError(
                "ADDataStore.sqlitedb not found — "
                "requires HomeDomain/Library/AggregateDictionary/"
            )

        try:
            tables = probe_tables(conn)
            _log.info("AggDict tables: %s", tables)

            records: List[dict] = []

            if "measurements" in tables:
                # Layout 1: iOS 12-14
                rows = conn.execute(_SQL_LAYOUT1).fetchall()
                _log.info("AggDict Layout 1: %d rows", len(rows))
                for row in rows:
                    key, start_date, end_date, value, unit = row
                    display_value = str(value) if value is not None else ""
                    if unit:
                        display_value = f"{display_value} {unit}".strip()
                    records.append({
                        "metric_key": key or "",
                        "value": display_value,
                        "start_date": apple_ts(start_date),
                        "end_date": apple_ts(end_date),
                    })

            elif "key_store" in tables and "value_store" in tables:
                # Layout 2: iOS 15+
                rows = conn.execute(_SQL_LAYOUT2).fetchall()
                _log.info("AggDict Layout 2: %d rows", len(rows))
                for row in rows:
                    key, start_date, end_date, double_val, string_val = row
                    if string_val is not None:
                        value = str(string_val)
                    elif double_val is not None:
                        value = str(double_val)
                    else:
                        value = ""
                    records.append({
                        "metric_key": key or "",
                        "value": value,
                        "start_date": apple_ts(start_date),
                        "end_date": apple_ts(end_date),
                    })

            else:
                _log.warning("AggDict: no recognised table layout. Tables: %s", tables)
                # Return inventory record so caller knows we found the file
                records.append({
                    "metric_key": "(unknown schema)",
                    "value": f"tables={tables}",
                    "start_date": None,
                    "end_date": None,
                })

            return records
        finally:
            conn.close()
