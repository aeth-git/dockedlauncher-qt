"""SMS deletion detection / recovery view."""
from .base_view import BaseTabView


class SMSRecoveryView(BaseTabView):
    TAB_NAME = "SMS Recovery"
    COLUMNS = [
        ("type",               "Event Type"),
        ("deleted_count",      "Messages Deleted"),
        ("after_timestamp",    "After (Message Before)"),
        ("before_timestamp",   "Before (Message After)"),
        ("gap_start_rowid",    "Gap Start ROWID"),
        ("gap_end_rowid",      "Gap End ROWID"),
        ("detail",             "Detail"),
    ]
