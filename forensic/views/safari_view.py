"""Safari browser history view."""
from .base_view import BaseTabView


class SafariView(BaseTabView):
    TAB_NAME = "Safari"
    COLUMNS = [
        ("timestamp",   "Date / Time"),
        ("title",       "Page Title"),
        ("url",         "URL"),
        ("visit_count", "Visits"),
    ]
