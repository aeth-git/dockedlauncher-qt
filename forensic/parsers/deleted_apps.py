"""Deleted app history — previously installed apps removed from the device.

Sources:
  plist: HomeDomain / Library/MobileInstallation/UninstalledApplications.plist
         (bundle IDs of deleted apps)
  SQLite: SystemPreferencesDomain / Library/FrontBoard/applicationstate.db
         (gaps between known bundle IDs vs active containers → residual data)
"""
import plistlib
from typing import List

from .base import BaseParser, ParserError
from .utils import probe_tables
from ..logger import get_logger

_log = get_logger("parsers.deleted_apps")

_UNINSTALLED_PLIST = ("HomeDomain",
                      "Library/MobileInstallation/UninstalledApplications.plist")

_FRONTBOARD_DB = ("HomeDomain", "Library/FrontBoard/applicationstate.db")


class DeletedAppsParser(BaseParser):
    def parse(self) -> List[dict]:
        records = []
        records.extend(self._parse_uninstalled_plist())
        records.extend(self._parse_frontboard())
        if not records:
            raise ParserError("Deleted app history not found in this backup")
        return records

    def _parse_uninstalled_plist(self) -> List[dict]:
        path = self._source.get_file(*_UNINSTALLED_PLIST)
        if path is None:
            return []
        try:
            with open(path, "rb") as f:
                data = plistlib.load(f)
        except Exception as e:
            _log.debug("UninstalledApplications plist error: %s", e)
            return []

        records = []
        if isinstance(data, dict):
            for bundle_id, info in data.items():
                uninstall_date = ""
                if isinstance(info, dict):
                    uninstall_date = str(info.get("UninstallDate", "") or
                                        info.get("date", "") or "")
                records.append({
                    "bundle_id": bundle_id,
                    "source": "UninstalledApplications.plist",
                    "uninstalled_at": uninstall_date,
                    "app_name": "",
                })
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    records.append({
                        "bundle_id": item,
                        "source": "UninstalledApplications.plist",
                        "uninstalled_at": "",
                        "app_name": "",
                    })
        _log.info("Uninstalled apps plist: %d entries", len(records))
        return records

    def _parse_frontboard(self) -> List[dict]:
        try:
            conn = self._get_db(*_FRONTBOARD_DB)
        except (FileNotFoundError, ParserError):
            return []
        try:
            tables = probe_tables(conn)
            if "application_identifier_tab" not in tables:
                return []
            # Get bundle IDs mapped in FrontBoard (includes tombstones for deleted apps)
            rows = conn.execute(
                "SELECT bundle_identifier, application_state "
                "FROM application_identifier_tab "
                "ORDER BY bundle_identifier"
            ).fetchall()
            records = []
            for r in rows:
                # State 4 or similar can indicate terminated/removed container
                state = r[1] if r[1] is not None else -1
                records.append({
                    "bundle_id": r[0] or "",
                    "source": "FrontBoard/applicationstate.db",
                    "uninstalled_at": "",
                    "app_name": "",
                    "container_state": state,
                })
            _log.info("FrontBoard: %d app entries", len(records))
            return records
        finally:
            conn.close()
