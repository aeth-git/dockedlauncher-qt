"""Known WiFi networks parser — com.apple.wifi.known-networks.plist."""
import plistlib
from typing import List

from .base import BaseParser, ParserError
from ..logger import get_logger

_log = get_logger("parsers.wifi")

_WIFI_PREFS = ("SystemPreferencesDomain",
               "Library/Preferences/com.apple.wifi.plist")
_WIFI_KNOWN = ("SystemPreferencesDomain",
               "Library/Preferences/SystemConfiguration/com.apple.wifi.known-networks.plist")


class WiFiParser(BaseParser):
    def parse(self) -> List[dict]:
        path = self._source.get_file(*_WIFI_KNOWN)
        if path is None:
            path = self._source.get_file(*_WIFI_PREFS)
        if path is None:
            raise ParserError("WiFi preferences not found in this backup")
        try:
            with open(path, "rb") as f:
                data = plistlib.load(f)
        except Exception as e:
            raise ParserError(f"Cannot parse WiFi plist: {e}")

        records = []
        # Two possible formats: flat list or nested dict
        networks = data.get("List of known networks", data)
        if isinstance(networks, dict):
            for ssid, info in networks.items():
                if isinstance(info, dict):
                    records.append(self._net_record(ssid, info))
        elif isinstance(networks, list):
            for net in networks:
                if isinstance(net, dict):
                    ssid = net.get("SSID_STR") or net.get("SSID", "")
                    records.append(self._net_record(ssid, net))

        _log.info("WiFi: %d known networks", len(records))
        return records

    @staticmethod
    def _net_record(ssid: str, info: dict) -> dict:
        bssid = info.get("BSSID") or info.get("lastBSSID") or ""
        security = info.get("SecurityType") or info.get("80211D_IE", {}).get("SSID_STR", "")
        added = info.get("AddedAt") or ""
        last_joined = info.get("lastJoined") or info.get("lastConnected") or ""
        return {
            "ssid": ssid if isinstance(ssid, str) else ssid.decode("utf-8", errors="replace"),
            "bssid": bssid,
            "security": str(security) if security else "",
            "added": str(added) if added else "",
            "last_joined": str(last_joined) if last_joined else "",
            "roaming": info.get("TemporarilyDisabled", False),
        }
