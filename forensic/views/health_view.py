"""Health data view."""
from .base_view import BaseTabView


class HealthView(BaseTabView):
    TAB_NAME = "Health"
    COLUMNS = [
        ("timestamp",  "Date / Time"),
        ("data_type",  "Metric"),
        ("value",      "Value"),
        ("source",     "Source"),
        ("category",   "Category"),
    ]
