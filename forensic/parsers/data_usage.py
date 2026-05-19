"""DataUsage.sqlite — per-app Wi-Fi and cellular data counters.

Path: WirelessDomain / Library/Databases/DataUsage.sqlite
Tables: ZPROCESS (bundle name), ZPROCUID (byte counters per process per period).
"""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.data_usage")

_DATA_USAGE_DB = ("WirelessDomain", "Library/Databases/DataUsage.sqlite")

_SQL = """
    SELECT
        p.ZBUNDLENAME       AS bundle_id,
        u.ZWIFIIN           AS wifi_in,
        u.ZWIFIOUT          AS wifi_out,
        u.ZWIRELESSWANIN    AS cell_in,
        u.ZWIRELESSWANOUT   AS cell_out,
        u.ZTIMESTAMP        AS raw_ts
    FROM ZPROCUID u
    LEFT JOIN ZPROCESS p ON u.ZPROCESS = p.Z_PK
    ORDER BY u.ZTIMESTAMP DESC
    LIMIT 50000
"""


def _fmt_bytes(n) -> str:
    if n is None:
        return "0 B"
    n = int(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n} {unit}"
        n //= 1024
    return f"{n} TB"


class DataUsageParser(BaseParser):
    def parse(self) -> List[dict]:
        try:
            conn = self._get_db(*_DATA_USAGE_DB)
        except FileNotFoundError:
            raise ParserError("DataUsage.sqlite not found in this backup")
        try:
            tables = probe_tables(conn)
            if "ZPROCUID" not in tables:
                raise ParserError("DataUsage.sqlite: ZPROCUID table missing")
            rows = conn.execute(_SQL).fetchall()
            _log.info("DataUsage: %d rows", len(rows))

            # Aggregate by bundle_id
            agg: dict = {}
            for r in rows:
                bid = r["bundle_id"] or "(system)"
                if bid not in agg:
                    agg[bid] = {
                        "bundle_id": bid,
                        "wifi_in": 0, "wifi_out": 0,
                        "cell_in": 0, "cell_out": 0,
                        "last_seen": r["raw_ts"],
                    }
                a = agg[bid]
                a["wifi_in"]  += int(r["wifi_in"]  or 0)
                a["wifi_out"] += int(r["wifi_out"] or 0)
                a["cell_in"]  += int(r["cell_in"]  or 0)
                a["cell_out"] += int(r["cell_out"] or 0)
                if r["raw_ts"] and (a["last_seen"] is None or r["raw_ts"] > a["last_seen"]):
                    a["last_seen"] = r["raw_ts"]

            records = []
            for a in agg.values():
                total = a["wifi_in"] + a["wifi_out"] + a["cell_in"] + a["cell_out"]
                records.append({
                    "bundle_id": a["bundle_id"],
                    "wifi_in": _fmt_bytes(a["wifi_in"]),
                    "wifi_out": _fmt_bytes(a["wifi_out"]),
                    "cell_in": _fmt_bytes(a["cell_in"]),
                    "cell_out": _fmt_bytes(a["cell_out"]),
                    "total": _fmt_bytes(total),
                    "total_bytes": total,
                    "last_seen": apple_ts(a["last_seen"]),
                })
            records.sort(key=lambda r: r["total_bytes"], reverse=True)
            return records
        finally:
            conn.close()
