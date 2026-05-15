"""Contacts tab view — flattens phone/email lists for display."""
from typing import List

from .base_view import BaseTabView, _RecordModel
from ..constants import FONT_FAMILY, FONT_SIZE_DATA

_COLUMNS = [
    ("last",   "Last"),
    ("first",  "First"),
    ("middle", "Middle"),
    ("org",    "Organization"),
    ("phones", "Phone Numbers"),
    ("emails", "Email Addresses"),
]


def _flatten_contact(r: dict) -> dict:
    phones = r.get("phones", [])
    emails = r.get("emails", [])
    return {
        "last":   r.get("last", ""),
        "first":  r.get("first", ""),
        "middle": r.get("middle", ""),
        "org":    r.get("org", ""),
        "phones": "; ".join(
            f"{e['value']} ({e['label']})" if e.get("label") else e["value"]
            for e in phones
        ),
        "emails": "; ".join(
            f"{e['value']} ({e['label']})" if e.get("label") else e["value"]
            for e in emails
        ),
    }


class ContactsView(BaseTabView):
    TAB_NAME = "Contacts"
    COLUMNS = _COLUMNS

    def load_records(self, records: List[dict]):
        flat = [_flatten_contact(r) for r in records]
        super().load_records(flat)
