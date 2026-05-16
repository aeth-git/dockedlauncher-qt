"""Bluetooth paired/scanned devices view."""
from .base_view import BaseTabView


class BluetoothView(BaseTabView):
    TAB_NAME = "Bluetooth"
    COLUMNS = [
        ("address",      "MAC Address"),
        ("name",         "Device Name"),
        ("device_type",  "Type"),
        ("paired",       "Paired"),
        ("last_seen",    "Last Seen"),
        ("source",       "Source"),
    ]
