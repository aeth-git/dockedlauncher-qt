"""Apple Wallet transactions and passes view."""
from .base_view import BaseTabView


class WalletView(BaseTabView):
    TAB_NAME = "Wallet"
    COLUMNS = [
        ("timestamp",   "Date / Time"),
        ("type",        "Type"),
        ("merchant",    "Merchant / Org"),
        ("amount",      "Amount"),
        ("card",        "Card"),
        ("lat",         "Latitude"),
        ("lon",         "Longitude"),
        ("description", "Description"),
    ]
