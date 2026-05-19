"""Spotlight CoreSpotlight search-index view."""
from .base_view import BaseTabView


class SpotlightView(BaseTabView):
    TAB_NAME = "Spotlight"
    COLUMNS = [
        ("title",        "Title"),
        ("content_type", "Type"),
        ("created",      "Created"),
        ("modified",     "Modified"),
        ("domain",       "Domain"),
        ("url",          "URL / Path"),
    ]
