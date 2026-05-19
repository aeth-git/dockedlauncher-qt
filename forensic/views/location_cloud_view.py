"""Significant cloud-synced locations view (Cloud.sqlite routined)."""
from .base_view import BaseTabView


class LocationCloudView(BaseTabView):
    TAB_NAME = "Sig. Locations"
    COLUMNS = [
        ("label",       "Label"),
        ("latitude",    "Latitude"),
        ("longitude",   "Longitude"),
        ("city",        "City"),
        ("country",     "Country"),
        ("confidence",  "Confidence"),
        ("visit_count", "Visits"),
    ]
