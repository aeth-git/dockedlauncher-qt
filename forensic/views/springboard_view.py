"""Home Screen (SpringBoard) tab view."""
from .base_view import BaseTabView


class SpringBoardView(BaseTabView):
    TAB_NAME = "Home Screen"
    COLUMNS = [
        ("bundle_id",  "Bundle ID"),
        ("section",    "Section"),
        ("page_index", "Page"),
        ("position",   "Position"),
        ("is_hidden",  "Hidden"),
    ]
