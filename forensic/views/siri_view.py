"""Siri Analytics tab view."""
from .base_view import BaseTabView


class SiriView(BaseTabView):
    TAB_NAME = "Siri"
    COLUMNS = [
        ("timestamp",     "Time"),
        ("intent",        "Intent"),
        ("app_bundle_id", "App Bundle ID"),
        ("latency_ms",    "Latency (ms)"),
        ("session_id",    "Session"),
    ]
