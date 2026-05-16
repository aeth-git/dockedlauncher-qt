"""Screen Time app usage view."""
from .base_view import BaseTabView


class ScreenTimeView(BaseTabView):
    TAB_NAME = "Screen Time"
    COLUMNS = [
        ("usage_fmt",  "Total Usage"),
        ("bundle_id",  "App Bundle ID"),
        ("launches",   "Launches"),
        ("last_use",   "Last Used"),
        ("first_use",  "First Used"),
    ]
