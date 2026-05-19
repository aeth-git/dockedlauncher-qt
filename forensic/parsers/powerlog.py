"""PowerLogParser — battery and app foreground time from PLSQL files.

PLSQL files are standard SQLite databases with a different extension,
located under Library/BatteryLife/ in various domains.
"""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.powerlog")

_POWERLOG_CANDIDATES = [
    ("RootDomain", "Library/BatteryLife/"),
    ("HomeDomain", "Library/BatteryLife/"),
    ("AppDomain-com.apple.powerlogd", "Library/BatteryLife/"),
]

_KNOWN_TABLES = {
    "PLProcessMonitor_Foreground",
    "PLBatteryAgent_EventBackward_BatteryUI",
    "PLSpringBoardActivity",
    "PLAccountingOperator_EventNone_Triggered_BatteryUI",
}

_VALID_EXTENSIONS = {".plsql", ".sqlite"}


def _is_valid_extension(rel_path: str) -> bool:
    lower = rel_path.lower()
    return any(lower.endswith(ext) for ext in _VALID_EXTENSIONS)


def _get_column_names(conn, table: str) -> List[str]:
    """Return column names for a table via PRAGMA table_info."""
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def _parse_process_monitor(conn, source_file: str) -> List[dict]:
    """Parse PLProcessMonitor_Foreground rows."""
    cols = _get_column_names(conn, "PLProcessMonitor_Foreground")
    col_set = set(c.lower() for c in cols)

    # Detect bundle_id column name
    bundle_col = None
    for candidate in ("bundleID", "BundleID", "bundle_id"):
        if candidate.lower() in col_set:
            bundle_col = candidate
            break
    if bundle_col is None:
        # Try to find any column containing 'bundle'
        for c in cols:
            if "bundle" in c.lower():
                bundle_col = c
                break

    rows = conn.execute(
        "SELECT * FROM PLProcessMonitor_Foreground ORDER BY timestamp DESC LIMIT 5000"
    ).fetchall()

    records = []
    for row in rows:
        d = dict(zip(cols, tuple(row)))
        ts_raw = d.get("timestamp")
        bundle_id = ""
        if bundle_col and bundle_col in d:
            bundle_id = d[bundle_col] or ""
        elif bundle_col:
            # case-insensitive fallback
            for k, v in d.items():
                if k.lower() == bundle_col.lower():
                    bundle_id = v or ""
                    break

        fg_time = d.get("foregroundTime") or d.get("ForegroundTime") or d.get("foreground_time")
        battery = d.get("batteryLevel") or d.get("BatteryLevel") or d.get("battery_level")

        records.append({
            "timestamp": apple_ts(ts_raw),
            "bundle_id": bundle_id,
            "foreground_time_ms": fg_time,
            "battery_level": battery,
            "charging_state": None,
            "source_table": "PLProcessMonitor_Foreground",
            "source_file": source_file,
        })
    return records


def _parse_battery_agent(conn, source_file: str) -> List[dict]:
    """Parse PLBatteryAgent_EventBackward_BatteryUI rows."""
    try:
        rows = conn.execute(
            "SELECT timestamp, Level as battery_level, IsCharging as charging "
            "FROM PLBatteryAgent_EventBackward_BatteryUI "
            "ORDER BY timestamp DESC LIMIT 5000"
        ).fetchall()
    except Exception:
        # Column names may differ — fall back to SELECT *
        cols = _get_column_names(conn, "PLBatteryAgent_EventBackward_BatteryUI")
        all_rows = conn.execute(
            "SELECT * FROM PLBatteryAgent_EventBackward_BatteryUI "
            "ORDER BY timestamp DESC LIMIT 5000"
        ).fetchall()
        col_lower = {c.lower(): c for c in cols}
        rows_dicts = [dict(zip(cols, tuple(r))) for r in all_rows]
        records = []
        for d in rows_dicts:
            level_key = col_lower.get("level") or col_lower.get("battery_level")
            charging_key = col_lower.get("ischarging") or col_lower.get("charging")
            records.append({
                "timestamp": apple_ts(d.get("timestamp")),
                "bundle_id": "",
                "foreground_time_ms": None,
                "battery_level": d.get(level_key) if level_key else None,
                "charging_state": d.get(charging_key) if charging_key else None,
                "source_table": "PLBatteryAgent_EventBackward_BatteryUI",
                "source_file": source_file,
            })
        return records

    records = []
    for row in rows:
        records.append({
            "timestamp": apple_ts(row[0]),
            "bundle_id": "",
            "foreground_time_ms": None,
            "battery_level": row[1],
            "charging_state": row[2],
            "source_table": "PLBatteryAgent_EventBackward_BatteryUI",
            "source_file": source_file,
        })
    return records


def _parse_springboard(conn, source_file: str) -> List[dict]:
    """Parse PLSpringBoardActivity rows."""
    cols = _get_column_names(conn, "PLSpringBoardActivity")
    rows = conn.execute(
        "SELECT * FROM PLSpringBoardActivity ORDER BY timestamp DESC LIMIT 5000"
    ).fetchall()
    records = []
    for row in rows:
        d = dict(zip(cols, tuple(row)))
        records.append({
            "timestamp": apple_ts(d.get("timestamp")),
            "bundle_id": d.get("bundleID") or d.get("BundleID") or "",
            "foreground_time_ms": None,
            "battery_level": d.get("batteryLevel") or d.get("BatteryLevel"),
            "charging_state": None,
            "source_table": "PLSpringBoardActivity",
            "source_file": source_file,
        })
    return records


def _parse_accounting(conn, source_file: str) -> List[dict]:
    """Parse PLAccountingOperator_EventNone_Triggered_BatteryUI rows."""
    cols = _get_column_names(conn, "PLAccountingOperator_EventNone_Triggered_BatteryUI")
    rows = conn.execute(
        "SELECT * FROM PLAccountingOperator_EventNone_Triggered_BatteryUI "
        "ORDER BY timestamp DESC LIMIT 5000"
    ).fetchall()
    records = []
    for row in rows:
        d = dict(zip(cols, tuple(row)))
        records.append({
            "timestamp": apple_ts(d.get("timestamp")),
            "bundle_id": d.get("bundleID") or d.get("BundleID") or "",
            "foreground_time_ms": None,
            "battery_level": d.get("batteryLevel") or d.get("BatteryLevel"),
            "charging_state": None,
            "source_table": "PLAccountingOperator_EventNone_Triggered_BatteryUI",
            "source_file": source_file,
        })
    return records


_TABLE_PARSERS = {
    "PLProcessMonitor_Foreground": _parse_process_monitor,
    "PLBatteryAgent_EventBackward_BatteryUI": _parse_battery_agent,
    "PLSpringBoardActivity": _parse_springboard,
    "PLAccountingOperator_EventNone_Triggered_BatteryUI": _parse_accounting,
}


class PowerLogParser(BaseParser):
    """Parse iOS PowerLog PLSQL files for battery and app foreground data."""

    def parse(self) -> List[dict]:
        # Collect all candidate (domain, rel_path) pairs
        candidates = []
        for domain, prefix in _POWERLOG_CANDIDATES:
            try:
                files = self._source.list_files(domain, prefix)
                for rel_path, _phys in files:
                    if _is_valid_extension(rel_path):
                        candidates.append((domain, rel_path))
            except Exception as exc:
                _log.debug("list_files(%s, %s) failed: %s", domain, prefix, exc)

        if not candidates:
            raise ParserError(
                "PowerLog not found — requires filesystem extraction or jailbroken device"
            )

        all_records: List[dict] = []
        any_known_table = False

        for domain, rel_path in candidates:
            try:
                conn = self._get_db(domain, rel_path)
            except Exception as exc:
                _log.warning("Cannot open PowerLog %s/%s: %s", domain, rel_path, exc)
                continue

            try:
                tables = probe_tables(conn)
                known = _KNOWN_TABLES & set(tables)

                if not known:
                    # File found but no known tables — inventory record
                    all_records.append({
                        "timestamp": None,
                        "bundle_id": None,
                        "foreground_time_ms": None,
                        "battery_level": None,
                        "charging_state": None,
                        "source_table": None,
                        "source_file": rel_path,
                        "stream_name": rel_path,
                        "record_count": 0,
                    })
                    continue

                any_known_table = True
                for table_name in known:
                    parser_fn = _TABLE_PARSERS.get(table_name)
                    if parser_fn is None:
                        continue
                    try:
                        recs = parser_fn(conn, rel_path)
                        all_records.extend(recs)
                        _log.info("PowerLog %s [%s]: %d records", rel_path, table_name, len(recs))
                    except Exception as exc:
                        _log.warning("Error parsing %s in %s: %s", table_name, rel_path, exc)
            finally:
                conn.close()

        return all_records
