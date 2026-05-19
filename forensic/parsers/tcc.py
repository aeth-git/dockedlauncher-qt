"""TCC.db — Transparency, Consent and Control: per-app permission grants/denials.

Two locations:
  HomeDomain / Library/TCC/TCC.db         (user-space)
  RootDomain  / Library/Logs/Accessibility/TCC.db  (system-space, filesystem only)

Table: access
Columns: service, client (bundle ID), client_type, auth_value, auth_reason, last_modified.

auth_value: 0=Denied, 1=Unknown, 2=Allowed, 3=Limited
"""
from typing import List

from .base import BaseParser, ParserError
from .utils import unix_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.tcc")

_TCC_DBS = [
    ("HomeDomain", "Library/TCC/TCC.db"),
    ("RootDomain", "Library/Logs/Accessibility/TCC.db"),
]

_SQL = """
    SELECT
        service         AS service,
        client          AS bundle_id,
        client_type     AS client_type,
        auth_value      AS auth_value,
        auth_reason     AS auth_reason,
        last_modified   AS last_modified
    FROM access
    ORDER BY last_modified DESC
"""

_AUTH = {0: "Denied", 1: "Unknown", 2: "Allowed", 3: "Limited"}

# Human-readable service names
_SERVICE_LABELS = {
    "kTCCServiceCamera":        "Camera",
    "kTCCServiceMicrophone":    "Microphone",
    "kTCCServiceLocation":      "Location",
    "kTCCServicePhotos":        "Photos",
    "kTCCServiceAddressBook":   "Contacts",
    "kTCCServiceCalendar":      "Calendar",
    "kTCCServiceReminders":     "Reminders",
    "kTCCServiceMotion":        "Motion & Fitness",
    "kTCCServiceBluetoothAlways": "Bluetooth",
    "kTCCServiceMediaLibrary":  "Media Library",
    "kTCCServiceUserTracking":  "Tracking (IDFA)",
    "kTCCServiceSpeechRecognition": "Speech Recognition",
    "kTCCServiceFaceID":        "Face ID",
    "kTCCServiceHealth":        "Health",
    "kTCCServiceHomeKit":       "HomeKit",
    "kTCCServiceNearbyInteraction": "Nearby Interaction",
}


class TCCParser(BaseParser):
    def parse(self) -> List[dict]:
        all_records = []
        found = False
        for domain, rel in _TCC_DBS:
            try:
                conn = self._get_db(domain, rel)
            except (FileNotFoundError, ParserError):
                continue
            found = True
            try:
                tables = probe_tables(conn)
                if "access" not in tables:
                    continue
                rows = conn.execute(_SQL).fetchall()
                _log.info("TCC (%s): %d rows", rel, len(rows))
                for r in rows:
                    service = r["service"] or ""
                    all_records.append({
                        "service": _SERVICE_LABELS.get(service, service.replace("kTCCService", "")),
                        "service_raw": service,
                        "bundle_id": r["bundle_id"] or "",
                        "permission": _AUTH.get(r["auth_value"], str(r["auth_value"] or "")),
                        "reason": str(r["auth_reason"] or ""),
                        "last_modified": unix_ts(r["last_modified"]),
                    })
            finally:
                conn.close()
        if not found:
            raise ParserError("TCC.db not found in this backup")
        # Deduplicate by (bundle_id, service)
        seen = set()
        unique = []
        for rec in all_records:
            key = (rec["bundle_id"], rec["service_raw"])
            if key not in seen:
                seen.add(key)
                unique.append(rec)
        return sorted(unique, key=lambda r: r.get("last_modified") or "", reverse=True)
