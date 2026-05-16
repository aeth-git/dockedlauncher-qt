"""Bluetooth devices parser — paired and detected BLE/classic devices.

Sources:
  plist: SystemPreferencesDomain / Library/Preferences/com.apple.MobileBluetooth.devices.plist
         (classic Bluetooth paired devices with LastSeenTime)
  SQLite: HomeDomain / Library/Caches/BTLEmap.sqlitedb  (BLE scan results, if present)
"""
import plistlib
from typing import List

from .base import BaseParser, ParserError
from ..logger import get_logger

_log = get_logger("parsers.bluetooth")

_BT_PLIST = ("SystemPreferencesDomain",
             "Library/Preferences/com.apple.MobileBluetooth.devices.plist")

_BLE_DB_CANDIDATES = [
    ("HomeDomain", "Library/Caches/BTLEmap.sqlitedb"),
]


class BluetoothParser(BaseParser):
    def parse(self) -> List[dict]:
        records = []
        records.extend(self._parse_plist())
        records.extend(self._parse_ble_db())
        if not records:
            raise ParserError("Bluetooth data not found in this backup")
        records.sort(key=lambda r: r.get("last_seen") or "", reverse=True)
        return records

    def _parse_plist(self) -> List[dict]:
        path = self._source.get_file(*_BT_PLIST)
        if path is None:
            return []
        try:
            with open(path, "rb") as f:
                data = plistlib.load(f)
        except Exception as e:
            _log.debug("BT plist error: %s", e)
            return []
        records = []
        for addr, info in data.items():
            if not isinstance(info, dict):
                continue
            records.append({
                "address": addr,
                "name": info.get("Name", ""),
                "device_type": info.get("ClassOfDevice", "") or info.get("BTDeviceType", ""),
                "paired": True,
                "last_seen": str(info.get("LastSeenTime", "") or ""),
                "source": "paired",
            })
        _log.info("Bluetooth plist: %d paired devices", len(records))
        return records

    def _parse_ble_db(self) -> List[dict]:
        for domain, rel in _BLE_DB_CANDIDATES:
            try:
                conn = self._get_db(domain, rel)
            except (FileNotFoundError, ParserError):
                continue
            try:
                # Schema varies; extract what we can
                from .utils import probe_tables
                tables = probe_tables(conn)
                records = []
                if "devices" in tables:
                    for row in conn.execute(
                        "SELECT address, name, timestamp FROM devices ORDER BY timestamp DESC"
                    ).fetchall():
                        records.append({
                            "address": row[0] or "",
                            "name": row[1] or "",
                            "device_type": "BLE",
                            "paired": False,
                            "last_seen": str(row[2] or ""),
                            "source": "scanned",
                        })
                _log.info("BLE DB: %d devices", len(records))
                return records
            finally:
                conn.close()
        return []
