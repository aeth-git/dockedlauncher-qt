"""PowerLogView — display battery and app foreground time records."""
from .base_view import BaseTabView


class PowerLogView(BaseTabView):
    """Tab view for PowerLog parser output."""

    TAB_NAME = "PowerLog"
    COLUMNS = [
        ("timestamp",         "Time"),
        ("bundle_id",         "Bundle ID"),
        ("foreground_time_ms", "Foreground (ms)"),
        ("battery_level",     "Battery %"),
        ("charging_state",    "Charging"),
        ("source_table",      "Source"),
    ]
