"""Apps tab view."""
from .base_view import BaseTabView

_COLUMNS = [
    ("name",      "App Name"),
    ("bundle_id", "Bundle ID"),
    ("version",   "Version"),
    ("author",    "Developer"),
    ("genre",     "Category"),
]


class AppsView(BaseTabView):
    TAB_NAME = "Apps"
    COLUMNS = _COLUMNS
