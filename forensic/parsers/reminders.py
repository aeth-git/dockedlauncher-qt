"""Reminders parser — scans all Container_v1/Stores/*.sqlite files.

Path: HomeDomain / Library/Reminders/Container_v1/Stores/Data-<GUID>.sqlite
Table: ZREMCDOBJECT — ZTITLE1, ZDUEDATE, ZCREATIONDATE, ZLASTMODIFIEDDATE,
       ZCOMPLETED, ZCOMPLETEDDATE, ZNOTES
"""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.reminders")

_REMINDERS_PREFIX = "Library/Reminders/Container_v1/Stores/"

_SQL = """
    SELECT
        Z_PK                AS id,
        ZTITLE1             AS title,
        ZNOTES              AS notes,
        ZCREATIONDATE       AS created_raw,
        ZLASTMODIFIEDDATE   AS modified_raw,
        ZDUEDATE            AS due_raw,
        ZCOMPLETED          AS completed,
        ZCOMPLETEDDATE      AS completed_raw
    FROM ZREMCDOBJECT
    WHERE ZTITLE1 IS NOT NULL
    ORDER BY ZLASTMODIFIEDDATE DESC
"""


class RemindersParser(BaseParser):
    def parse(self) -> List[dict]:
        db_files = self._source.list_files("HomeDomain", _REMINDERS_PREFIX)
        db_files = [(rel, path) for rel, path in db_files if rel.endswith(".sqlite")]

        if not db_files:
            raise ParserError("Reminders: no reminder stores found in this backup")

        all_records: List[dict] = []
        for rel_path, _ in db_files:
            try:
                conn = self._get_db("HomeDomain", rel_path)
            except Exception:
                continue
            try:
                tables = probe_tables(conn)
                if "ZREMCDOBJECT" not in tables:
                    continue
                for r in conn.execute(_SQL).fetchall():
                    all_records.append({
                        "id": r["id"],
                        "title": r["title"] or "(No Title)",
                        "notes": r["notes"] or "",
                        "due": apple_ts(r["due_raw"]),
                        "created": apple_ts(r["created_raw"]),
                        "modified": apple_ts(r["modified_raw"]),
                        "completed": bool(r["completed"]),
                        "completed_at": apple_ts(r["completed_raw"]),
                    })
            finally:
                conn.close()

        _log.info("Reminders: %d items", len(all_records))
        all_records.sort(key=lambda r: r.get("modified") or "", reverse=True)
        return all_records
