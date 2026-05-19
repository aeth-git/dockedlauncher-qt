"""Safari iCloud Tabs view."""
from .base_view import BaseTabView


class SafariCloudTabsView(BaseTabView):
    TAB_NAME = "Cloud Tabs"
    COLUMNS = [
        ("device_name", "Device"),
        ("title",       "Title"),
        ("url",         "URL"),
        ("created",     "Created"),
        ("position",    "Pos"),
    ]
