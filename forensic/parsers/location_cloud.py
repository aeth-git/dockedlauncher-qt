"""LocationCloud parser — Cloud.sqlite significant locations (distinct from LocationParser).

LocationParser reads:
  - consolidated.db (cell/WiFi raw tracks)
  - Local.sqlite routined (learned locations of interest)

This parser reads:
  - Cloud.sqlite routined (cloud-synced significant locations of interest)
"""
from typing import List

from .base import BaseParser, ParserError
from .utils import probe_tables
from ..logger import get_logger

_log = get_logger("parsers.location_cloud")

_DB = ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite")
_TABLE = "ZRTCLOUDSYNCEDLOCATIONOFINTEREST"


class LocationCloudParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = self._get_db(*_DB)
        try:
            tables = probe_tables(conn)
            if _TABLE not in tables:
                raise ParserError(
                    f"Cloud.sqlite: expected table not found. Tables: {tables}"
                )

            # Discover actual columns — iOS version varies
            col_rows = conn.execute(
                f"PRAGMA table_info({_TABLE})"
            ).fetchall()
            cols = {r[1] for r in col_rows}

            lat_col = "ZLATITUDE" if "ZLATITUDE" in cols else None
            lon_col = "ZLONGITUDE" if "ZLONGITUDE" in cols else None
            # Label: prefer ZLABEL, fall back to ZCUSTOMLABEL
            label_col = (
                "ZLABEL" if "ZLABEL" in cols
                else "ZCUSTOMLABEL" if "ZCUSTOMLABEL" in cols
                else None
            )
            city_col = "ZCITY" if "ZCITY" in cols else None
            state_col = "ZSTATE" if "ZSTATE" in cols else None
            country_col = "ZCOUNTRY" if "ZCOUNTRY" in cols else None
            confidence_col = "ZCONFIDENCE" if "ZCONFIDENCE" in cols else None
            visit_count_col = "ZVISITCOUNT" if "ZVISITCOUNT" in cols else None

            # Determine ORDER BY
            if visit_count_col:
                order_by = f"{visit_count_col} DESC"
            elif label_col:
                order_by = f"{label_col} ASC"
            else:
                order_by = "1"

            def _sel(col, alias):
                return f"{col} AS {alias}" if col else f"NULL AS {alias}"

            select_clause = ", ".join([
                _sel(label_col, "_label"),
                _sel(lat_col, "_lat"),
                _sel(lon_col, "_lon"),
                _sel(city_col, "_city"),
                _sel(state_col, "_state"),
                _sel(country_col, "_country"),
                _sel(confidence_col, "_confidence"),
                _sel(visit_count_col, "_visit_count"),
            ])

            sql = (
                f"SELECT {select_clause} "
                f"FROM {_TABLE} "
                f"ORDER BY {order_by}"
            )
            rows = conn.execute(sql).fetchall()
            _log.info("LocationCloud: %d significant cloud locations", len(rows))

            records = []
            for row in rows:
                records.append({
                    "label": row[0] or "",
                    "latitude": row[1],
                    "longitude": row[2],
                    "city": row[3] or "",
                    "state": row[4] or "",
                    "country": row[5] or "",
                    "confidence": row[6],
                    "visit_count": row[7],
                })
            return records
        finally:
            conn.close()
