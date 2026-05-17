"""Safari Downloads view."""
from .base_view import BaseTabView


class SafariDownloadsView(BaseTabView):
    TAB_NAME = "Downloads"
    COLUMNS = [
        ("url",           "URL"),
        ("filename",      "Filename"),
        ("bytes_received","Received"),
        ("total_bytes",   "Total"),
        ("downloaded_at", "Downloaded At"),
        ("status",        "Status"),
    ]
