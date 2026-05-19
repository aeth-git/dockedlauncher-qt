"""Known WiFi networks view."""
from .base_view import BaseTabView


class WiFiView(BaseTabView):
    TAB_NAME = "WiFi"
    COLUMNS = [
        ("ssid",        "Network Name (SSID)"),
        ("bssid",       "BSSID"),
        ("security",    "Security"),
        ("last_joined", "Last Joined"),
        ("added",       "Added"),
    ]
