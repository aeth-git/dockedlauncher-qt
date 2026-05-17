"""SpringBoard home screen layout parser — reads IconState.plist."""
import plistlib
from typing import List

from .base import BaseParser, ParserError
from ..logger import get_logger

_log = get_logger("parsers.springboard")

_ICONSTATE = ("HomeDomain", "Library/SpringBoard/IconState.plist")


class SpringBoardParser(BaseParser):
    def parse(self) -> List[dict]:
        path = self._source.get_file(*_ICONSTATE)
        if path is None:
            raise ParserError("IconState.plist not found in this backup")

        try:
            with open(path, "rb") as f:
                data = plistlib.load(f)
        except Exception as e:
            raise ParserError(f"Cannot parse IconState.plist: {e}") from e

        records: List[dict] = []

        # Home screen pages
        icon_lists = data.get("iconLists", [])
        for page_index, page in enumerate(icon_lists):
            if not isinstance(page, list):
                continue
            for position, item in enumerate(page):
                bundle_id = self._extract_bundle_id(item)
                if bundle_id:
                    records.append({
                        "bundle_id":  bundle_id,
                        "page_index": page_index,
                        "position":   position,
                        "is_hidden":  False,
                        "section":    "homescreen",
                    })

        # Dock
        button_bar = data.get("buttonBar", [])
        for position, item in enumerate(button_bar):
            bundle_id = self._extract_bundle_id(item)
            if bundle_id:
                records.append({
                    "bundle_id":  bundle_id,
                    "page_index": -1,
                    "position":   position,
                    "is_hidden":  False,
                    "section":    "dock",
                })

        # iOS 18 hidden apps
        hidden_lists = data.get("hiddenIconLists", [])
        for page_index, page in enumerate(hidden_lists):
            if not isinstance(page, list):
                continue
            for position, item in enumerate(page):
                bundle_id = self._extract_bundle_id(item)
                if bundle_id:
                    records.append({
                        "bundle_id":  bundle_id,
                        "page_index": page_index,
                        "position":   position,
                        "is_hidden":  True,
                        "section":    "hidden",
                    })

        _log.info("SpringBoard: %d icon entries", len(records))
        return records

    @staticmethod
    def _extract_bundle_id(item) -> str:
        """Return bundle ID from either string form or dict form."""
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            return item.get("displayIdentifier", "")
        return ""
