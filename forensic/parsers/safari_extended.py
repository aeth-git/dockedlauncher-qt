"""Extended Safari parsers: Cloud Tabs, Downloads, Bookmarks."""
import plistlib
from os.path import basename
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, unix_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.safari_extended")

_CLOUD_TABS_DB = ("HomeDomain", "Library/Safari/CloudTabs.db")
_DOWNLOADS_PLIST = ("HomeDomain", "Library/Safari/Downloads.plist")
_BOOKMARKS_DB = ("HomeDomain", "Library/Safari/Bookmarks.db")

# Candidate table names for cloud tabs (varies by iOS version)
_CLOUD_TAB_TABLES = ("cloud_tabs", "tabs", "synced_tabs")


class SafariCloudTabsParser(BaseParser):
    """Parse Safari iCloud tabs from CloudTabs.db."""

    def parse(self) -> List[dict]:
        try:
            conn = self._get_db(*_CLOUD_TABS_DB)
        except FileNotFoundError:
            raise ParserError("Safari CloudTabs.db not found in this backup")
        try:
            tables = probe_tables(conn)
            table = None
            for candidate in _CLOUD_TAB_TABLES:
                if candidate in tables:
                    table = candidate
                    break
            if table is None:
                raise ParserError(
                    f"Safari CloudTabs.db: no recognised tab table "
                    f"(found: {tables})"
                )

            # Probe columns so we handle schema variations gracefully
            cur = conn.execute(f"PRAGMA table_info({table})")
            cols = {row[1] for row in cur.fetchall()}

            # Build SELECT dynamically based on available columns
            device_col = next(
                (c for c in ("device_name", "device", "source_name") if c in cols),
                None,
            )
            title_col = next((c for c in ("title",) if c in cols), None)
            url_col = next((c for c in ("url",) if c in cols), None)
            pos_col = next(
                (c for c in ("position", "position_index", "tab_order") if c in cols),
                None,
            )
            ts_col = next(
                (
                    c
                    for c in (
                        "created_at",
                        "creation_time",
                        "last_modified",
                        "date_closed",
                        "timestamp",
                    )
                    if c in cols
                ),
                None,
            )

            select_parts = []
            for alias, col in [
                ("device_name", device_col),
                ("title", title_col),
                ("url", url_col),
                ("position", pos_col),
                ("raw_ts", ts_col),
            ]:
                if col:
                    select_parts.append(f"{col} AS {alias}")
                else:
                    select_parts.append(f"NULL AS {alias}")

            sql = f"SELECT {', '.join(select_parts)} FROM {table}"
            rows = conn.execute(sql).fetchall()
            _log.info("Fetched %d cloud tab rows from %s", len(rows), table)
            records = []
            for r in rows:
                records.append(
                    {
                        "device_name": r["device_name"] or "",
                        "title": r["title"] or "",
                        "url": r["url"] or "",
                        "created": apple_ts(r["raw_ts"]),
                        "position": r["position"] if r["position"] is not None else "",
                    }
                )
            return records
        finally:
            conn.close()


class SafariDownloadsParser(BaseParser):
    """Parse Safari downloads from Downloads.plist."""

    def parse(self) -> List[dict]:
        path = self._source.get_file(*_DOWNLOADS_PLIST)
        if path is None:
            raise ParserError("Safari Downloads.plist not found in this backup")
        try:
            with open(path, "rb") as f:
                data = plistlib.load(f)
        except Exception as e:
            raise ParserError(f"Cannot read Downloads.plist: {e}") from e

        # The plist may be a list of dicts or a dict with a list inside
        if isinstance(data, dict):
            entries = data.get("DownloadItems", data.get("items", []))
        elif isinstance(data, list):
            entries = data
        else:
            entries = []

        records = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            url = entry.get("DownloadEntryURL", "")
            path_val = entry.get("DownloadEntryPath", "")
            filename = basename(path_val) if path_val else ""
            bytes_received = entry.get("DownloadEntryProgressBytesSoFar", 0)
            total_bytes = entry.get("DownloadEntryProgressTotalToLoad", 0)
            date_finished = entry.get("DownloadEntryDateFinishedKey")

            # Determine status
            if total_bytes and bytes_received >= total_bytes:
                status = "Complete"
            elif date_finished is not None:
                status = "Complete"
            else:
                status = "In Progress"

            # Convert date_finished: it may be a datetime object (plistlib
            # auto-converts date tags) or a float Apple timestamp
            downloaded_at = None
            if date_finished is not None:
                import datetime as _dt
                if isinstance(date_finished, _dt.datetime):
                    downloaded_at = date_finished.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    downloaded_at = apple_ts(date_finished)

            records.append(
                {
                    "url": url,
                    "filename": filename,
                    "bytes_received": bytes_received,
                    "total_bytes": total_bytes,
                    "downloaded_at": downloaded_at,
                    "status": status,
                }
            )

        _log.info("Parsed %d Safari download entries", len(records))
        return records


class SafariBookmarksParser(BaseParser):
    """Parse Safari bookmarks from Bookmarks.db."""

    def parse(self) -> List[dict]:
        try:
            conn = self._get_db(*_BOOKMARKS_DB)
        except FileNotFoundError:
            raise ParserError("Safari Bookmarks.db not found in this backup")
        try:
            tables = probe_tables(conn)
            if "bookmarks" not in tables:
                raise ParserError(
                    "Safari Bookmarks.db: 'bookmarks' table not found"
                )

            # Probe columns to handle schema variations
            cur = conn.execute("PRAGMA table_info(bookmarks)")
            cols = {row[1] for row in cur.fetchall()}

            has_url = "url" in cols
            has_type = "type" in cols
            has_parent = "parent" in cols

            ts_col = next(
                (c for c in ("added", "date_added", "created_at") if c in cols),
                None,
            )

            # Self-join to get parent folder name
            if has_parent:
                url_expr = "b.url" if has_url else "NULL"
                type_expr = "b.type" if has_type else "NULL"
                ts_expr = f"b.{ts_col}" if ts_col else "NULL"
                sql = f"""
                    SELECT
                        b.id        AS id,
                        b.title     AS title,
                        {url_expr}  AS url,
                        {type_expr} AS type,
                        p.title     AS folder,
                        {ts_expr}   AS raw_ts
                    FROM bookmarks b
                    LEFT JOIN bookmarks p ON b.parent = p.id
                    ORDER BY b.id
                """
            else:
                url_expr = "b.url" if has_url else "NULL"
                type_expr = "b.type" if has_type else "NULL"
                ts_expr = f"b.{ts_col}" if ts_col else "NULL"
                sql = f"""
                    SELECT
                        b.id        AS id,
                        b.title     AS title,
                        {url_expr}  AS url,
                        {type_expr} AS type,
                        NULL        AS folder,
                        {ts_expr}   AS raw_ts
                    FROM bookmarks b
                    ORDER BY b.id
                """

            rows = conn.execute(sql).fetchall()
            _log.info("Fetched %d bookmark rows", len(rows))
            records = []
            for r in rows:
                btype = r["type"]
                if btype == 1:
                    type_label = "Folder"
                elif btype == 2:
                    type_label = "Bookmark"
                else:
                    type_label = "Bookmark"
                records.append(
                    {
                        "title": r["title"] or "",
                        "url": r["url"] or "",
                        "folder": r["folder"] or "",
                        "type_label": type_label,
                        "added": apple_ts(r["raw_ts"]),
                    }
                )
            return records
        finally:
            conn.close()
