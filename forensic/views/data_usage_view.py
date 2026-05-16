"""Per-app data usage view."""
from .base_view import BaseTabView


class DataUsageView(BaseTabView):
    TAB_NAME = "Data Usage"
    COLUMNS = [
        ("bundle_id",  "App Bundle ID"),
        ("total",      "Total"),
        ("wifi_in",    "WiFi ↓"),
        ("wifi_out",   "WiFi ↑"),
        ("cell_in",    "Cell ↓"),
        ("cell_out",   "Cell ↑"),
        ("last_seen",  "Last Seen"),
    ]
