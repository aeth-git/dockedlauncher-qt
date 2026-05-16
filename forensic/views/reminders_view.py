"""Apple Reminders view."""
from .base_view import BaseTabView


class RemindersView(BaseTabView):
    TAB_NAME = "Reminders"
    COLUMNS = [
        ("modified",      "Modified"),
        ("due",           "Due"),
        ("title",         "Title"),
        ("completed",     "Done"),
        ("completed_at",  "Completed"),
        ("notes",         "Notes"),
    ]
