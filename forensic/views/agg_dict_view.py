"""AggregatedDictView — display AggregatedDictionary system metrics."""
from .base_view import BaseTabView


class AggregatedDictView(BaseTabView):
    """Tab view for AggregatedDictParser output."""

    TAB_NAME = "Agg. Metrics"
    COLUMNS = [
        ("start_date",  "Start"),
        ("end_date",    "End"),
        ("metric_key",  "Metric Key"),
        ("value",       "Value"),
    ]
