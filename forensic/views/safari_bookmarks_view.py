"""Safari Bookmarks view."""
from .base_view import BaseTabView


class SafariBookmarksView(BaseTabView):
    TAB_NAME = "Bookmarks"
    COLUMNS = [
        ("title",      "Title"),
        ("url",        "URL"),
        ("folder",     "Folder"),
        ("type_label", "Type"),
        ("added",      "Added"),
    ]
