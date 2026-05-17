"""Safari binary cookies parser — reads Cookies.binarycookies from HomeDomain."""
import struct
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts
from ..logger import get_logger

_log = get_logger("parsers.safari_cookies")

_COOKIES_FILE = ("HomeDomain", "Library/Cookies/Cookies.binarycookies")

MAGIC = b"cook"

# Maximum sanity limits
_MAX_PAGES = 10_000
_MAX_COOKIES_PER_PAGE = 10_000
_LIMIT = 10_000


def _parse_binarycookies(data: bytes) -> List[dict]:
    """Parse a Cookies.binarycookies binary blob and return a list of cookie dicts."""
    if len(data) < 8 or data[:4] != MAGIC:
        return []

    num_pages = struct.unpack(">I", data[4:8])[0]
    if num_pages > _MAX_PAGES:
        _log.warning("binarycookies: suspiciously many pages (%d), aborting", num_pages)
        return []

    # Read page-size array (big-endian uint32s immediately after the header)
    page_sizes = []
    for i in range(num_pages):
        offset = 8 + i * 4
        if offset + 4 > len(data):
            break
        size = struct.unpack(">I", data[offset:offset + 4])[0]
        page_sizes.append(size)

    cookies: List[dict] = []
    page_offset = 8 + num_pages * 4

    for page_size in page_sizes:
        if page_offset + page_size > len(data):
            break
        page = data[page_offset: page_offset + page_size]
        page_offset += page_size

        if len(page) < 8 or page[:4] != b"\x00\x00\x01\x00":
            continue

        num_cookies = struct.unpack("<I", page[4:8])[0]
        if num_cookies > _MAX_COOKIES_PER_PAGE:
            continue

        for i in range(num_cookies):
            co_offset = 8 + i * 4
            if co_offset + 4 > len(page):
                break
            co = struct.unpack("<I", page[co_offset: co_offset + 4])[0]
            if co + 56 > len(page):
                continue
            try:
                flags     = struct.unpack("<I", page[co + 8:  co + 12])[0]
                url_off   = struct.unpack("<I", page[co + 16: co + 20])[0]
                name_off  = struct.unpack("<I", page[co + 20: co + 24])[0]
                path_off  = struct.unpack("<I", page[co + 24: co + 28])[0]
                value_off = struct.unpack("<I", page[co + 28: co + 32])[0]
                expiry    = struct.unpack("<d", page[co + 40: co + 48])[0]
                created   = struct.unpack("<d", page[co + 48: co + 56])[0]

                def read_str(off: int) -> str:
                    s = page[co + off:]
                    end = s.find(b"\x00")
                    return s[:end if end >= 0 else 64].decode("utf-8", errors="replace")

                url   = read_str(url_off)
                name  = read_str(name_off)
                path  = read_str(path_off)
                value = read_str(value_off)[:200]

                cookies.append({
                    "url":          url,
                    "name":         name,
                    "path":         path,
                    "value":        value,
                    "domain":       url.lstrip("."),
                    "expires":      apple_ts(expiry)  if expiry  > 0 else None,
                    "created":      apple_ts(created) if created > 0 else None,
                    "is_secure":    bool(flags & 1),
                    "is_http_only": bool(flags & 4),
                    "flags":        flags,
                })
            except (struct.error, IndexError):
                continue

    return cookies


class SafariBinaryCookiesParser(BaseParser):
    def parse(self) -> List[dict]:
        path = self._source.get_file(*_COOKIES_FILE)
        if path is None:
            raise ParserError("Safari Cookies.binarycookies not found in this backup")

        data = path.read_bytes()
        _log.info("binarycookies: read %d bytes", len(data))

        cookies = _parse_binarycookies(data)
        _log.info("binarycookies: parsed %d cookies", len(cookies))

        # Sort by domain then limit
        cookies.sort(key=lambda c: (c.get("domain") or "", c.get("name") or ""))
        return cookies[:_LIMIT]
