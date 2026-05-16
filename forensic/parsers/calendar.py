"""Apple Calendar parser — Calendar.sqlitedb."""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.calendar")

_CALENDAR_DB = ("HomeDomain", "Library/Calendar/Calendar.sqlitedb")

_EVENTS_SQL = """
    SELECT
        ci.ROWID                        AS id,
        ci.summary                      AS title,
        ci.location                     AS location,
        ci.description                  AS notes,
        ci.start_date                   AS start_raw,
        ci.end_date                     AS end_raw,
        ci.all_day                      AS all_day,
        ci.has_recurrences              AS recurring,
        c.title                         AS calendar_name,
        c.color                         AS calendar_color
    FROM CalendarItem ci
    LEFT JOIN Calendar c ON ci.calendar_id = c.ROWID
    ORDER BY ci.start_date DESC
"""

_ALARMS_SQL = """
    SELECT
        a.ROWID                         AS id,
        a.calendaritem_owner_id         AS event_id,
        a.trigger_interval              AS offset_sec,
        a.trigger_date                  AS trigger_raw
    FROM Alarm a
"""


class CalendarParser(BaseParser):
    def parse(self) -> List[dict]:
        try:
            conn = self._get_db(*_CALENDAR_DB)
        except FileNotFoundError:
            raise ParserError("Calendar database not found in this backup")
        try:
            tables = probe_tables(conn)
            if "CalendarItem" not in tables:
                raise ParserError("Calendar.sqlitedb: CalendarItem table missing")

            # Build alarm offset map
            alarm_map: dict = {}
            if "Alarm" in tables:
                for row in conn.execute(_ALARMS_SQL).fetchall():
                    alarm_map.setdefault(row["event_id"], []).append(row["offset_sec"])

            rows = conn.execute(_EVENTS_SQL).fetchall()
            _log.info("Fetched %d calendar events", len(rows))
            records = []
            for r in rows:
                records.append({
                    "id": r["id"],
                    "title": r["title"] or "(No Title)",
                    "location": r["location"] or "",
                    "notes": r["notes"] or "",
                    "start": apple_ts(r["start_raw"]),
                    "end": apple_ts(r["end_raw"]),
                    "all_day": bool(r["all_day"]),
                    "recurring": bool(r["recurring"]),
                    "calendar": r["calendar_name"] or "",
                    "alarms": alarm_map.get(r["id"], []),
                })
            return records
        finally:
            conn.close()
