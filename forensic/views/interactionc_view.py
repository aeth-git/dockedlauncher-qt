"""InteractionC cross-app interaction log view."""
from .base_view import BaseTabView


class InteractionCView(BaseTabView):
    TAB_NAME = "Interactions"
    COLUMNS = [
        ("timestamp",  "Date / Time"),
        ("direction",  "Direction"),
        ("contact",    "Contact"),
        ("app",        "App"),
        ("has_attachment", "Attachment"),
    ]
