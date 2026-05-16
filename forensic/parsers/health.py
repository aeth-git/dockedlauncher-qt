"""Health database parser — healthdb_secure.sqlite (encrypted backup or filesystem).

Path: HomeDomain / Library/Health/healthdb_secure.sqlite
Accessible via: encrypted iTunes backup, or filesystem extraction.
Plain (unencrypted) iTunes backup does NOT include Health data.

Table: samples — health metrics by data_type.
Common data_type values (partial list):
  7   = Steps
  9   = Distance Walking/Running
  12  = Flights Climbed
  13  = Active Energy Burned
  19  = Heart Rate
  37  = Sleep Analysis
  77  = Resting Heart Rate
  105 = Walking Heart Rate Average
  132 = Blood Oxygen (SpO2)
  133 = ECG
"""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.health")

_HEALTH_DBS = [
    ("HomeDomain", "Library/Health/healthdb_secure.sqlite"),
    ("HomeDomain", "Library/Health/healthdb.sqlite"),
]

_SAMPLES_SQL = """
    SELECT
        s.data_type         AS data_type,
        s.start_date        AS start_raw,
        s.end_date          AS end_raw,
        s.value             AS value,
        d.local_name        AS type_name,
        s.source_id         AS source_id,
        src.name            AS source_name
    FROM samples s
    LEFT JOIN data_type d ON s.data_type = d.ROWID
    LEFT JOIN sources src ON s.source_id = src.ROWID
    ORDER BY s.start_date DESC
    LIMIT 50000
"""

_WORKOUTS_SQL = """
    SELECT
        workout_activity_type   AS activity_type,
        start_date              AS start_raw,
        end_date                AS end_raw,
        duration                AS duration_sec,
        total_distance          AS distance,
        total_energy_burned     AS calories
    FROM workouts
    ORDER BY start_date DESC
    LIMIT 5000
"""

_KNOWN_TYPES = {
    7: "Steps",
    9: "Distance Walking/Running",
    12: "Flights Climbed",
    13: "Active Energy Burned",
    19: "Heart Rate",
    37: "Sleep Analysis",
    55: "Mindful Session",
    70: "Dietary Protein",
    72: "Dietary Sugar",
    77: "Resting Heart Rate",
    105: "Walking Heart Rate Average",
    107: "VO2 Max",
    108: "High Heart Rate Notification",
    114: "Blood Pressure Systolic",
    115: "Blood Pressure Diastolic",
    131: "Respiratory Rate",
    132: "Blood Oxygen (SpO2)",
    133: "ECG",
}


class HealthParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = None
        for domain, rel in _HEALTH_DBS:
            try:
                conn = self._get_db(domain, rel)
                break
            except (FileNotFoundError, ParserError) as e:
                if "encrypted" in str(e).lower():
                    raise ParserError(
                        "Health database is encrypted. "
                        "Use an encrypted iTunes backup (with known password) "
                        "or a filesystem extraction to access Health data."
                    )
                continue
        if conn is None:
            raise ParserError(
                "Health database not found. "
                "Health data is only available via encrypted iTunes backup "
                "or filesystem extraction."
            )
        try:
            tables = probe_tables(conn)
            records = []

            if "samples" in tables:
                for r in conn.execute(_SAMPLES_SQL).fetchall():
                    dt = r["data_type"] or 0
                    type_name = r["type_name"] or _KNOWN_TYPES.get(dt, f"Type {dt}")
                    records.append({
                        "data_type": type_name,
                        "timestamp": apple_ts(r["start_raw"]),
                        "end_time": apple_ts(r["end_raw"]),
                        "value": str(r["value"] or ""),
                        "source": r["source_name"] or str(r["source_id"] or ""),
                        "category": "Sample",
                    })

            if "workouts" in tables:
                for r in conn.execute(_WORKOUTS_SQL).fetchall():
                    dur = int(r["duration_sec"] or 0)
                    records.append({
                        "data_type": f"Workout: {r['activity_type'] or 'Unknown'}",
                        "timestamp": apple_ts(r["start_raw"]),
                        "end_time": apple_ts(r["end_raw"]),
                        "value": (f"{dur // 60}m {dur % 60}s, "
                                  f"{r['calories'] or 0:.0f} kcal, "
                                  f"{r['distance'] or 0:.2f} m"),
                        "source": "",
                        "category": "Workout",
                    })

            _log.info("Health: %d records", len(records))
            return records
        finally:
            conn.close()
