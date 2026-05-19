"""Voicemail records view."""
from .base_view import BaseTabView


class VoicemailView(BaseTabView):
    TAB_NAME = "Voicemail"
    COLUMNS = [
        ("timestamp",  "Date / Time"),
        ("sender",     "Caller"),
        ("callback",   "Callback #"),
        ("duration",   "Duration"),
        ("trashed",    "Deleted"),
    ]
