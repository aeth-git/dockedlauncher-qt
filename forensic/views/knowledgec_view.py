"""KnowledgeC pattern-of-life view."""
from .base_view import BaseTabView


class KnowledgeCView(BaseTabView):
    TAB_NAME = "KnowledgeC"
    COLUMNS = [
        ("timestamp",   "Start"),
        ("end_time",    "End"),
        ("duration",    "Duration"),
        ("event_type",  "Event"),
        ("value",       "App / Value"),
        ("media_title", "Media Title"),
        ("media_artist","Artist"),
    ]
