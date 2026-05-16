"""Deleted / previously installed apps view."""
from .base_view import BaseTabView


class DeletedAppsView(BaseTabView):
    TAB_NAME = "Deleted Apps"
    COLUMNS = [
        ("bundle_id",      "Bundle ID"),
        ("app_name",       "App Name"),
        ("uninstalled_at", "Uninstalled"),
        ("source",         "Source"),
    ]
