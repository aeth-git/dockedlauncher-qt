"""Location history parser — consolidated.db + routined Local.sqlite."""
from typing import List

from .base import BaseParser, ParserError
from .utils import unix_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.location")

# Cell tower and WiFi location history
_CONSOLIDATED_DB = ("RootDomain", "Library/Caches/locationd/consolidated.db")
# Significant/frequent locations from routined
_ROUTINED_DB = ("HomeDomain", "Library/Caches/com.apple.routined/Local.sqlite")

_WIFI_SQL = """
    SELECT
        Timestamp   AS raw_ts,
        Latitude    AS lat,
        Longitude   AS lon,
        HorizontalAccuracy AS accuracy,
        BSSID       AS bssid,
        SSID        AS ssid
    FROM WifiLocation
    ORDER BY Timestamp DESC
    LIMIT 10000
"""

_CELL_SQL = """
    SELECT
        Timestamp           AS raw_ts,
        Latitude            AS lat,
        Longitude           AS lon,
        HorizontalAccuracy  AS accuracy,
        MCC                 AS mcc,
        MNC                 AS mnc,
        LAC                 AS lac,
        CID                 AS cid
    FROM CellLocation
    ORDER BY Timestamp DESC
    LIMIT 10000
"""

_SIGNIFICANT_SQL = """
    SELECT
        ZDATE           AS raw_ts,
        ZLATITUDE       AS lat,
        ZLONGITUDE      AS lon,
        ZNAME           AS place_name,
        ZCOUNTRY        AS country,
        ZCITY           AS city
    FROM ZRTLEARNEDLOCATIONOFINTEREST
    ORDER BY ZDATE DESC
"""


class LocationParser(BaseParser):
    def parse(self) -> List[dict]:
        records = []
        records.extend(self._parse_consolidated())
        records.extend(self._parse_routined())
        # Sort combined results by timestamp descending
        records.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
        return records

    def _parse_consolidated(self) -> List[dict]:
        try:
            conn = self._get_db(*_CONSOLIDATED_DB)
        except (FileNotFoundError, ParserError):
            return []
        try:
            tables = probe_tables(conn)
            records = []

            if "WifiLocation" in tables:
                for r in conn.execute(_WIFI_SQL).fetchall():
                    records.append({
                        "type": "wifi",
                        "timestamp": unix_ts(r["raw_ts"]),
                        "lat": r["lat"],
                        "lon": r["lon"],
                        "accuracy": r["accuracy"],
                        "label": r["ssid"] or r["bssid"] or "",
                        "detail": f"BSSID: {r['bssid'] or ''}",
                    })

            if "CellLocation" in tables:
                for r in conn.execute(_CELL_SQL).fetchall():
                    records.append({
                        "type": "cell",
                        "timestamp": unix_ts(r["raw_ts"]),
                        "lat": r["lat"],
                        "lon": r["lon"],
                        "accuracy": r["accuracy"],
                        "label": f"MCC{r['mcc']}-MNC{r['mnc']}",
                        "detail": f"LAC:{r['lac']} CID:{r['cid']}",
                    })

            _log.info("Location: %d consolidated records", len(records))
            return records
        finally:
            conn.close()

    def _parse_routined(self) -> List[dict]:
        try:
            conn = self._get_db(*_ROUTINED_DB)
        except (FileNotFoundError, ParserError):
            return []
        try:
            tables = probe_tables(conn)
            if "ZRTLEARNEDLOCATIONOFINTEREST" not in tables:
                return []
            rows = conn.execute(_SIGNIFICANT_SQL).fetchall()
            _log.info("Location: %d significant places", len(rows))
            return [{
                "type": "significant",
                "timestamp": unix_ts(r["raw_ts"]),
                "lat": r["lat"],
                "lon": r["lon"],
                "accuracy": 50,
                "label": r["place_name"] or r["city"] or "",
                "detail": ", ".join(
                    p for p in [r["city"], r["country"]] if p
                ),
            } for r in rows]
        finally:
            conn.close()
