"""Apple Mail view."""
from .base_view import BaseTabView


class MailView(BaseTabView):
    TAB_NAME = "Mail"
    COLUMNS = [
        ("received",  "Received"),
        ("sender",    "Sender"),
        ("subject",   "Subject"),
        ("mailbox",   "Mailbox"),
        ("read",      "Read"),
        ("flagged",   "Flagged"),
    ]
