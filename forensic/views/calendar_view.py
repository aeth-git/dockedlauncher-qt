"""Calendar events view."""
from .base_view import BaseTabView


class CalendarView(BaseTabView):
    TAB_NAME = "Calendar"
    COLUMNS = [
        ("start",     "Start"),
        ("end",       "End"),
        ("title",     "Event"),
        ("location",  "Location"),
        ("calendar",  "Calendar"),
        ("all_day",   "All Day"),
        ("recurring", "Recurring"),
    ]
