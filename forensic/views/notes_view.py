"""Apple Notes view."""
from .base_view import BaseTabView


class NotesView(BaseTabView):
    TAB_NAME = "Notes"
    COLUMNS = [
        ("modified",  "Modified"),
        ("created",   "Created"),
        ("title",     "Title"),
        ("snippet",   "Preview"),
        ("locked",    "Locked"),
    ]
