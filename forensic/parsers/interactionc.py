"""InteractionC.db — cross-app interaction log (calls, messages, emails from all apps).

Path: HomeDomain / Library/CoreDuet/People/interactionC.db
~1 month retention. Correlates contact data across apps in one place.
"""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.interactionc")

_INTERACTION_DB = ("HomeDomain", "Library/CoreDuet/People/interactionC.db")

_SQL = """
    SELECT
        i.Z_PK                          AS id,
        i.ZSTARTDATE                    AS start_raw,
        i.ZENDDATE                      AS end_raw,
        i.ZDIRECTION                    AS direction,
        i.ZBUNDLEID                     AS bundle_id,
        i.ZISRESPONSE                   AS is_response,
        c.ZDISPLAYNAME                  AS contact_name,
        c.ZPERSONID                     AS person_id,
        a.ZATTACHMENT                   AS attachment_type
    FROM ZINTERACTIONS i
    LEFT JOIN ZCONTACTS c ON i.ZCONTACT = c.Z_PK
    LEFT JOIN ZATTACHMENTS a ON a.ZINTERACTION = i.Z_PK
    ORDER BY i.ZSTARTDATE DESC
    LIMIT 50000
"""

_DIRECTION = {0: "Received", 1: "Sent", 2: "Missed"}


class InteractionCParser(BaseParser):
    def parse(self) -> List[dict]:
        try:
            conn = self._get_db(*_INTERACTION_DB)
        except FileNotFoundError:
            raise ParserError("InteractionC.db not found in this backup")
        try:
            tables = probe_tables(conn)
            if "ZINTERACTIONS" not in tables:
                raise ParserError("InteractionC.db: ZINTERACTIONS table missing")
            rows = conn.execute(_SQL).fetchall()
            _log.info("InteractionC: %d interactions", len(rows))
            return [{
                "id": r["id"],
                "timestamp": apple_ts(r["start_raw"]),
                "end_time": apple_ts(r["end_raw"]),
                "direction": _DIRECTION.get(r["direction"], str(r["direction"] or "")),
                "contact": r["contact_name"] or str(r["person_id"] or ""),
                "app": r["bundle_id"] or "",
                "has_attachment": bool(r["attachment_type"]),
                "is_response": bool(r["is_response"]),
            } for r in rows]
        finally:
            conn.close()
