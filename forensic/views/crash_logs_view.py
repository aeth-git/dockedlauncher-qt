"""Crash Logs tab view."""
from .base_view import BaseTabView


class CrashLogsView(BaseTabView):
    TAB_NAME = "Crash Logs"
    COLUMNS = [
        ("timestamp",      "Time"),
        ("process",        "Process"),
        ("bundle_id",      "Bundle ID"),
        ("exception_type", "Exception"),
        ("signal",         "Signal"),
        ("reason",         "Reason"),
        ("ios_version",    "iOS"),
        ("file_name",      "File"),
    ]
