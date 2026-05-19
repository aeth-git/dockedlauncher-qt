"""Contacts parser — AddressBook.sqlitedb"""
from typing import List

from .base import BaseParser
from ..constants import CONTACTS_DB, AB_PROP_PHONE, AB_PROP_EMAIL, AB_LABEL_MAP
from ..logger import get_logger

_log = get_logger("parsers.contacts")

_PERSONS_SQL = """
    SELECT ROWID, First, Last, Middle, Organization, Department
    FROM ABPerson
    ORDER BY Last, First
"""

_MV_SQL = """
    SELECT record_id, property, value, label
    FROM ABMultiValue
    WHERE property IN (?, ?)
"""


class ContactsParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = self._get_db(*CONTACTS_DB)
        try:
            persons = {}
            for row in conn.execute(_PERSONS_SQL).fetchall():
                persons[row[0]] = {
                    "id": row[0],
                    "first": row[1] or "",
                    "last": row[2] or "",
                    "middle": row[3] or "",
                    "org": row[4] or "",
                    "dept": row[5] or "",
                    "phones": [],
                    "emails": [],
                }

            for row in conn.execute(_MV_SQL, (AB_PROP_PHONE, AB_PROP_EMAIL)).fetchall():
                record_id, prop, value, label_int = row
                if record_id not in persons:
                    continue
                label = AB_LABEL_MAP.get(label_int, str(label_int) if label_int else "")
                entry = {"value": value or "", "label": label}
                if prop == AB_PROP_PHONE:
                    persons[record_id]["phones"].append(entry)
                elif prop == AB_PROP_EMAIL:
                    persons[record_id]["emails"].append(entry)

            result = list(persons.values())
            _log.info("Parsed %d contacts", len(result))
            return result
        finally:
            conn.close()
