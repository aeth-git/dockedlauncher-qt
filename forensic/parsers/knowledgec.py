"""KnowledgeC.db parser — iOS pattern-of-life: app usage, media, device state.

knowledgeC.db is in regular iTunes backups at:
  HomeDomain / Library/CoreDuet/Knowledge/knowledgeC.db

ZOBJECT.ZSTREAMNAME values decoded here:
  /app/usage          - foreground app sessions (start/end + bundle ID)
  /app/inFocus        - active foreground focus events
  /app/activity       - in-app NSUserActivity / Handoff
  /media/nowPlaying   - music/podcast/video now playing
  /device/isLocked    - lock/unlock events
  /device/isPluggedIn - charging events
  /display/isBacklit  - screen on/off
"""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.knowledgec")

_KNOWLEDGEC_DB = ("HomeDomain", "Library/CoreDuet/Knowledge/knowledgeC.db")

_SQL = """
    SELECT
        o.ZSTREAMNAME          AS stream,
        o.ZSTARTDATE           AS start_raw,
        o.ZENDDATE             AS end_raw,
        o.ZVALUEINTEGER        AS val_int,
        o.ZVALUESTRING         AS val_str,
        o.ZVALUEDOUBLE         AS val_dbl,
        m.ZDKAPPINSTALLMETADATAKEY__BUNDLEID        AS bundle_id,
        m.ZDKNOWPLAYINGMETADATAKEY__TITLE           AS media_title,
        m.ZDKNOWPLAYINGMETADATAKEY__ARTIST          AS media_artist,
        m.ZDKNOWPLAYINGMETADATAKEY__ALBUM           AS media_album,
        m.ZDKNOWPLAYINGMETADATAKEY__UNIQUEID        AS media_app
    FROM ZOBJECT o
    LEFT JOIN ZSTRUCTUREDMETADATA m ON o.ZSTRUCTUREDMETADATA = m.Z_PK
    ORDER BY o.ZSTARTDATE DESC
    LIMIT 100000
"""

# Human-readable stream name mapping
_STREAM_LABELS = {
    "/app/usage":              "App Usage",
    "/app/inFocus":            "App Focus",
    "/app/activity":           "App Activity",
    "/media/nowPlaying":       "Now Playing",
    "/device/isLocked":        "Device Locked",
    "/device/isPluggedIn":     "Charging",
    "/device/isAdapterWireless": "Wireless Charging",
    "/display/isBacklit":      "Screen On",
    "/settings/doNotDisturb":  "Do Not Disturb",
    "/safari/history":         "Safari (KnowledgeC)",
    "/app/webUsage":           "Web Usage",
}


class KnowledgeCParser(BaseParser):
    def parse(self) -> List[dict]:
        try:
            conn = self._get_db(*_KNOWLEDGEC_DB)
        except FileNotFoundError:
            raise ParserError("KnowledgeC.db not found in this backup")
        try:
            tables = probe_tables(conn)
            if "ZOBJECT" not in tables:
                raise ParserError("KnowledgeC.db: ZOBJECT table missing")
            rows = conn.execute(_SQL).fetchall()
            _log.info("KnowledgeC: %d events", len(rows))
            records = []
            for r in rows:
                stream = r["stream"] or ""
                label = _STREAM_LABELS.get(stream, stream.split("/")[-1] if stream else "")
                # Determine value: prefer bundle_id for app streams, val_str otherwise
                value = (r["bundle_id"] or r["val_str"] or
                         str(r["val_int"] or r["val_dbl"] or ""))
                # Duration
                start_ts = apple_ts(r["start_raw"])
                end_ts = apple_ts(r["end_raw"])
                dur = ""
                if r["start_raw"] is not None and r["end_raw"] is not None:
                    try:
                        d = int((float(r["end_raw"]) - float(r["start_raw"])))
                        if d > 0:
                            dur = f"{d // 60}m {d % 60}s" if d >= 60 else f"{d}s"
                    except (TypeError, ValueError):
                        pass
                records.append({
                    "timestamp": start_ts,
                    "end_time": end_ts,
                    "duration": dur,
                    "stream": stream,
                    "event_type": label,
                    "value": value,
                    "media_title": r["media_title"] or "",
                    "media_artist": r["media_artist"] or "",
                    "media_album": r["media_album"] or "",
                })
            return records
        finally:
            conn.close()
