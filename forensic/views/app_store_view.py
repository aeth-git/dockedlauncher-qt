"""App Store purchases tab view."""
from .base_view import BaseTabView


class AppStoreView(BaseTabView):
    TAB_NAME = "App Store"
    COLUMNS = [
        ("purchase_date", "Purchased"),
        ("app_name",      "App Name"),
        ("bundle_id",     "Bundle ID"),
        ("version",       "Version"),
        ("price",         "Price"),
        ("item_id",       "Item ID"),
    ]
