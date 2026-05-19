"""HomeKit accessories tab view."""
from .base_view import BaseTabView


class HomeKitView(BaseTabView):
    TAB_NAME = "HomeKit"
    COLUMNS = [
        ("home_name",      "Home"),
        ("room_name",      "Room"),
        ("accessory_name", "Accessory"),
        ("manufacturer",   "Manufacturer"),
        ("model",          "Model"),
        ("category",       "Category"),
        ("is_reachable",   "Reachable"),
        ("firmware",       "Firmware"),
    ]
