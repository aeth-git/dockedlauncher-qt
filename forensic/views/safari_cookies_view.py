"""Safari binary cookies tab view."""
from .base_view import BaseTabView


class SafariBinaryCookiesView(BaseTabView):
    TAB_NAME = "Cookies"
    COLUMNS = [
        ("domain",       "Domain"),
        ("name",         "Cookie Name"),
        ("value",        "Value"),
        ("path",         "Path"),
        ("expires",      "Expires"),
        ("created",      "Created"),
        ("is_secure",    "Secure"),
        ("is_http_only", "HttpOnly"),
    ]
