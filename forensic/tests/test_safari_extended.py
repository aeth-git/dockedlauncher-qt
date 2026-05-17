"""Comprehensive tests for SafariCloudTabsParser, SafariDownloadsParser,
SafariBookmarksParser and their corresponding views."""
import hashlib
import os
import plistlib
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

APPLE_EPOCH = 978307200


# ── Helpers ──────────────────────────────────────────────────────────────────

from forensic.tests.conftest import make_backup as _make_backup


def _make_empty_backup(tmp_path):
    """Backup with no files at all."""
    return _make_backup(tmp_path)


# ── DB / plist builders ──────────────────────────────────────────────────────

def _make_cloud_tabs_db():
    """Two cloud_tabs rows with Apple-epoch timestamps."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE cloud_tabs "
        "(uuid TEXT, device_name TEXT, title TEXT, url TEXT, "
        "position INTEGER, created_at REAL)"
    )
    t1 = 1655287200 - APPLE_EPOCH  # 2022-06-15 10:00:00 UTC
    conn.execute(
        "INSERT INTO cloud_tabs VALUES (?,?,?,?,?,?)",
        ("uuid1", "MacBook Pro", "Example", "https://example.com", 0, t1),
    )
    conn.execute(
        "INSERT INTO cloud_tabs VALUES (?,?,?,?,?,?)",
        ("uuid2", "iPad", "News", "https://news.com", 1, t1 + 3600),
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_cloud_tabs_db_empty():
    """cloud_tabs table present but empty."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE cloud_tabs "
        "(uuid TEXT, device_name TEXT, title TEXT, url TEXT, "
        "position INTEGER, created_at REAL)"
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_cloud_tabs_db_alt_table():
    """Uses 'tabs' as table name instead of 'cloud_tabs'."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE tabs "
        "(uuid TEXT, device_name TEXT, title TEXT, url TEXT, "
        "position INTEGER, created_at REAL)"
    )
    t1 = 1655287200 - APPLE_EPOCH
    conn.execute(
        "INSERT INTO tabs VALUES (?,?,?,?,?,?)",
        ("uuid3", "iPhone", "Alt Tab", "https://alt.com", 0, t1),
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_cloud_tabs_db_no_recognised_table():
    """Has only an unrecognised table name."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute("CREATE TABLE unknown_table (id INTEGER)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_downloads_plist():
    """Two download entries — one complete, one in progress."""
    return plistlib.dumps(
        [
            {
                "DownloadEntryURL": "https://example.com/file.zip",
                "DownloadEntryPath": "/var/mobile/Downloads/file.zip",
                "DownloadEntryProgressBytesSoFar": 1024000,
                "DownloadEntryProgressTotalToLoad": 1024000,
            },
            {
                "DownloadEntryURL": "https://example.com/doc.pdf",
                "DownloadEntryPath": "/var/mobile/Downloads/doc.pdf",
                "DownloadEntryProgressBytesSoFar": 5000,
                "DownloadEntryProgressTotalToLoad": 100000,
            },
        ]
    )


def _make_downloads_plist_empty_list():
    return plistlib.dumps([])


def _make_downloads_plist_dict_wrapper():
    """Plist wrapped in a dict with DownloadItems key."""
    return plistlib.dumps(
        {
            "DownloadItems": [
                {
                    "DownloadEntryURL": "https://example.com/img.png",
                    "DownloadEntryPath": "/var/mobile/Downloads/img.png",
                    "DownloadEntryProgressBytesSoFar": 512,
                    "DownloadEntryProgressTotalToLoad": 512,
                }
            ]
        }
    )


def _make_downloads_plist_missing_keys():
    """Entry with minimal / missing optional keys."""
    return plistlib.dumps(
        [
            {
                "DownloadEntryURL": "https://example.com/bare.txt",
                # No path, no bytes info
            }
        ]
    )


def _make_bookmarks_db():
    """Folder (id=1) + two bookmark children (id=2,3)."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE bookmarks "
        "(id INTEGER PRIMARY KEY, title TEXT, url TEXT, type INTEGER, parent INTEGER)"
    )
    conn.execute("INSERT INTO bookmarks VALUES (1,'Favorites',NULL,1,0)")
    conn.execute(
        "INSERT INTO bookmarks VALUES (2,'Example','https://example.com',2,1)"
    )
    conn.execute(
        "INSERT INTO bookmarks VALUES (3,'News','https://news.com',2,1)"
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_bookmarks_db_empty():
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE bookmarks "
        "(id INTEGER PRIMARY KEY, title TEXT, url TEXT, type INTEGER, parent INTEGER)"
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_bookmarks_db_no_table():
    """DB that has no 'bookmarks' table."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute("CREATE TABLE something_else (id INTEGER)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


# ── SafariCloudTabsParser ─────────────────────────────────────────────────────

class TestSafariCloudTabsParser:
    from forensic.parsers.base import ParserError

    def test_returns_two_records(self, tmp_path):
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Safari/CloudTabs.db", _make_cloud_tabs_db()),
        )
        from forensic.parsers.safari_extended import SafariCloudTabsParser
        records = SafariCloudTabsParser(src).parse()
        assert len(records) == 2

    def test_required_fields_present(self, tmp_path):
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Safari/CloudTabs.db", _make_cloud_tabs_db()),
        )
        from forensic.parsers.safari_extended import SafariCloudTabsParser
        records = SafariCloudTabsParser(src).parse()
        required = {"device_name", "title", "url", "created", "position"}
        for r in records:
            assert required.issubset(r.keys()), f"Missing: {required - r.keys()}"

    def test_device_name_correct(self, tmp_path):
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Safari/CloudTabs.db", _make_cloud_tabs_db()),
        )
        from forensic.parsers.safari_extended import SafariCloudTabsParser
        records = SafariCloudTabsParser(src).parse()
        device_names = {r["device_name"] for r in records}
        assert "MacBook Pro" in device_names
        assert "iPad" in device_names

    def test_url_and_title_correct(self, tmp_path):
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Safari/CloudTabs.db", _make_cloud_tabs_db()),
        )
        from forensic.parsers.safari_extended import SafariCloudTabsParser
        records = SafariCloudTabsParser(src).parse()
        example = next(r for r in records if r["device_name"] == "MacBook Pro")
        assert example["url"] == "https://example.com"
        assert example["title"] == "Example"

    def test_timestamp_format(self, tmp_path):
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Safari/CloudTabs.db", _make_cloud_tabs_db()),
        )
        from forensic.parsers.safari_extended import SafariCloudTabsParser
        records = SafariCloudTabsParser(src).parse()
        for r in records:
            if r["created"] is not None:
                assert len(r["created"]) == 19
                assert r["created"][4] == "-"
                assert "2022-06-15" in r["created"]

    def test_not_found_raises_parser_error(self, tmp_path):
        src = _make_empty_backup(tmp_path)
        from forensic.parsers.safari_extended import SafariCloudTabsParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError, match="CloudTabs.db not found"):
            SafariCloudTabsParser(src).parse()

    def test_empty_table_returns_empty_list(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/CloudTabs.db",
                _make_cloud_tabs_db_empty(),
            ),
        )
        from forensic.parsers.safari_extended import SafariCloudTabsParser
        records = SafariCloudTabsParser(src).parse()
        assert records == []

    def test_alt_table_name_tabs(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/CloudTabs.db",
                _make_cloud_tabs_db_alt_table(),
            ),
        )
        from forensic.parsers.safari_extended import SafariCloudTabsParser
        records = SafariCloudTabsParser(src).parse()
        assert len(records) == 1
        assert records[0]["device_name"] == "iPhone"
        assert records[0]["url"] == "https://alt.com"

    def test_no_recognised_table_raises_parser_error(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/CloudTabs.db",
                _make_cloud_tabs_db_no_recognised_table(),
            ),
        )
        from forensic.parsers.safari_extended import SafariCloudTabsParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            SafariCloudTabsParser(src).parse()

    def test_position_values(self, tmp_path):
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Safari/CloudTabs.db", _make_cloud_tabs_db()),
        )
        from forensic.parsers.safari_extended import SafariCloudTabsParser
        records = SafariCloudTabsParser(src).parse()
        positions = {r["position"] for r in records}
        assert 0 in positions
        assert 1 in positions


# ── SafariDownloadsParser ─────────────────────────────────────────────────────

class TestSafariDownloadsParser:

    def test_returns_two_records(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Downloads.plist",
                _make_downloads_plist(),
            ),
        )
        from forensic.parsers.safari_extended import SafariDownloadsParser
        records = SafariDownloadsParser(src).parse()
        assert len(records) == 2

    def test_required_fields_present(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Downloads.plist",
                _make_downloads_plist(),
            ),
        )
        from forensic.parsers.safari_extended import SafariDownloadsParser
        records = SafariDownloadsParser(src).parse()
        required = {"url", "filename", "bytes_received", "total_bytes", "downloaded_at", "status"}
        for r in records:
            assert required.issubset(r.keys()), f"Missing: {required - r.keys()}"

    def test_complete_status_detected(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Downloads.plist",
                _make_downloads_plist(),
            ),
        )
        from forensic.parsers.safari_extended import SafariDownloadsParser
        records = SafariDownloadsParser(src).parse()
        complete = [r for r in records if r["status"] == "Complete"]
        assert len(complete) == 1
        assert complete[0]["filename"] == "file.zip"

    def test_in_progress_status_detected(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Downloads.plist",
                _make_downloads_plist(),
            ),
        )
        from forensic.parsers.safari_extended import SafariDownloadsParser
        records = SafariDownloadsParser(src).parse()
        in_prog = [r for r in records if r["status"] == "In Progress"]
        assert len(in_prog) == 1
        assert in_prog[0]["filename"] == "doc.pdf"

    def test_filename_extracted_from_path(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Downloads.plist",
                _make_downloads_plist(),
            ),
        )
        from forensic.parsers.safari_extended import SafariDownloadsParser
        records = SafariDownloadsParser(src).parse()
        filenames = {r["filename"] for r in records}
        assert "file.zip" in filenames
        assert "doc.pdf" in filenames

    def test_url_correct(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Downloads.plist",
                _make_downloads_plist(),
            ),
        )
        from forensic.parsers.safari_extended import SafariDownloadsParser
        records = SafariDownloadsParser(src).parse()
        urls = {r["url"] for r in records}
        assert "https://example.com/file.zip" in urls

    def test_not_found_raises_parser_error(self, tmp_path):
        src = _make_empty_backup(tmp_path)
        from forensic.parsers.safari_extended import SafariDownloadsParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError, match="Downloads.plist not found"):
            SafariDownloadsParser(src).parse()

    def test_empty_list_returns_empty(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Downloads.plist",
                _make_downloads_plist_empty_list(),
            ),
        )
        from forensic.parsers.safari_extended import SafariDownloadsParser
        records = SafariDownloadsParser(src).parse()
        assert records == []

    def test_dict_wrapper_plist(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Downloads.plist",
                _make_downloads_plist_dict_wrapper(),
            ),
        )
        from forensic.parsers.safari_extended import SafariDownloadsParser
        records = SafariDownloadsParser(src).parse()
        assert len(records) == 1
        assert records[0]["filename"] == "img.png"
        assert records[0]["status"] == "Complete"

    def test_missing_keys_handled_gracefully(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Downloads.plist",
                _make_downloads_plist_missing_keys(),
            ),
        )
        from forensic.parsers.safari_extended import SafariDownloadsParser
        records = SafariDownloadsParser(src).parse()
        assert len(records) == 1
        r = records[0]
        assert r["url"] == "https://example.com/bare.txt"
        assert r["filename"] == ""
        assert r["bytes_received"] == 0
        assert r["total_bytes"] == 0

    def test_bytes_values_correct(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Downloads.plist",
                _make_downloads_plist(),
            ),
        )
        from forensic.parsers.safari_extended import SafariDownloadsParser
        records = SafariDownloadsParser(src).parse()
        zip_rec = next(r for r in records if r["filename"] == "file.zip")
        assert zip_rec["bytes_received"] == 1024000
        assert zip_rec["total_bytes"] == 1024000


# ── SafariBookmarksParser ─────────────────────────────────────────────────────

class TestSafariBookmarksParser:

    def test_returns_three_records(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Bookmarks.db",
                _make_bookmarks_db(),
            ),
        )
        from forensic.parsers.safari_extended import SafariBookmarksParser
        records = SafariBookmarksParser(src).parse()
        assert len(records) == 3

    def test_required_fields_present(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Bookmarks.db",
                _make_bookmarks_db(),
            ),
        )
        from forensic.parsers.safari_extended import SafariBookmarksParser
        records = SafariBookmarksParser(src).parse()
        required = {"title", "url", "folder", "type_label", "added"}
        for r in records:
            assert required.issubset(r.keys()), f"Missing: {required - r.keys()}"

    def test_folder_type_label(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Bookmarks.db",
                _make_bookmarks_db(),
            ),
        )
        from forensic.parsers.safari_extended import SafariBookmarksParser
        records = SafariBookmarksParser(src).parse()
        folders = [r for r in records if r["type_label"] == "Folder"]
        assert len(folders) == 1
        assert folders[0]["title"] == "Favorites"

    def test_bookmark_type_label(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Bookmarks.db",
                _make_bookmarks_db(),
            ),
        )
        from forensic.parsers.safari_extended import SafariBookmarksParser
        records = SafariBookmarksParser(src).parse()
        bookmarks = [r for r in records if r["type_label"] == "Bookmark"]
        assert len(bookmarks) == 2

    def test_folder_name_resolved_via_self_join(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Bookmarks.db",
                _make_bookmarks_db(),
            ),
        )
        from forensic.parsers.safari_extended import SafariBookmarksParser
        records = SafariBookmarksParser(src).parse()
        example = next(r for r in records if r["title"] == "Example")
        assert example["folder"] == "Favorites"
        news = next(r for r in records if r["title"] == "News")
        assert news["folder"] == "Favorites"

    def test_url_correct(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Bookmarks.db",
                _make_bookmarks_db(),
            ),
        )
        from forensic.parsers.safari_extended import SafariBookmarksParser
        records = SafariBookmarksParser(src).parse()
        example = next(r for r in records if r["title"] == "Example")
        assert example["url"] == "https://example.com"

    def test_not_found_raises_parser_error(self, tmp_path):
        src = _make_empty_backup(tmp_path)
        from forensic.parsers.safari_extended import SafariBookmarksParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError, match="Bookmarks.db not found"):
            SafariBookmarksParser(src).parse()

    def test_empty_table_returns_empty_list(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Bookmarks.db",
                _make_bookmarks_db_empty(),
            ),
        )
        from forensic.parsers.safari_extended import SafariBookmarksParser
        records = SafariBookmarksParser(src).parse()
        assert records == []

    def test_missing_bookmarks_table_raises(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Bookmarks.db",
                _make_bookmarks_db_no_table(),
            ),
        )
        from forensic.parsers.safari_extended import SafariBookmarksParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError, match="'bookmarks' table not found"):
            SafariBookmarksParser(src).parse()

    def test_folder_url_is_empty_string(self, tmp_path):
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Bookmarks.db",
                _make_bookmarks_db(),
            ),
        )
        from forensic.parsers.safari_extended import SafariBookmarksParser
        records = SafariBookmarksParser(src).parse()
        folder_rec = next(r for r in records if r["type_label"] == "Folder")
        # Folder row has NULL url; parser should return ""
        assert folder_rec["url"] == ""

    def test_added_is_none_when_no_ts_column(self, tmp_path):
        """Bookmarks DB without added/date_added column → added is None."""
        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/Safari/Bookmarks.db",
                _make_bookmarks_db(),  # no ts column in fixture
            ),
        )
        from forensic.parsers.safari_extended import SafariBookmarksParser
        records = SafariBookmarksParser(src).parse()
        # Fixture has no timestamp column → all added values are None
        for r in records:
            assert r["added"] is None


# ── View tests ────────────────────────────────────────────────────────────────

class TestSafariCloudTabsView:
    def test_tab_name(self):
        from forensic.views.safari_cloud_tabs_view import SafariCloudTabsView
        assert SafariCloudTabsView.TAB_NAME == "Cloud Tabs"

    def test_columns_defined(self):
        from forensic.views.safari_cloud_tabs_view import SafariCloudTabsView
        keys = [c[0] for c in SafariCloudTabsView.COLUMNS]
        assert "device_name" in keys
        assert "title" in keys
        assert "url" in keys
        assert "created" in keys
        assert "position" in keys

    def test_column_count(self):
        from forensic.views.safari_cloud_tabs_view import SafariCloudTabsView
        assert len(SafariCloudTabsView.COLUMNS) == 5

    def test_inherits_base_tab_view(self):
        from forensic.views.safari_cloud_tabs_view import SafariCloudTabsView
        from forensic.views.base_view import BaseTabView
        assert issubclass(SafariCloudTabsView, BaseTabView)


class TestSafariDownloadsView:
    def test_tab_name(self):
        from forensic.views.safari_downloads_view import SafariDownloadsView
        assert SafariDownloadsView.TAB_NAME == "Downloads"

    def test_columns_defined(self):
        from forensic.views.safari_downloads_view import SafariDownloadsView
        keys = [c[0] for c in SafariDownloadsView.COLUMNS]
        assert "url" in keys
        assert "filename" in keys
        assert "bytes_received" in keys
        assert "total_bytes" in keys
        assert "downloaded_at" in keys
        assert "status" in keys

    def test_column_count(self):
        from forensic.views.safari_downloads_view import SafariDownloadsView
        assert len(SafariDownloadsView.COLUMNS) == 6

    def test_inherits_base_tab_view(self):
        from forensic.views.safari_downloads_view import SafariDownloadsView
        from forensic.views.base_view import BaseTabView
        assert issubclass(SafariDownloadsView, BaseTabView)


class TestSafariBookmarksView:
    def test_tab_name(self):
        from forensic.views.safari_bookmarks_view import SafariBookmarksView
        assert SafariBookmarksView.TAB_NAME == "Bookmarks"

    def test_columns_defined(self):
        from forensic.views.safari_bookmarks_view import SafariBookmarksView
        keys = [c[0] for c in SafariBookmarksView.COLUMNS]
        assert "title" in keys
        assert "url" in keys
        assert "folder" in keys
        assert "type_label" in keys
        assert "added" in keys

    def test_column_count(self):
        from forensic.views.safari_bookmarks_view import SafariBookmarksView
        assert len(SafariBookmarksView.COLUMNS) == 5

    def test_inherits_base_tab_view(self):
        from forensic.views.safari_bookmarks_view import SafariBookmarksView
        from forensic.views.base_view import BaseTabView
        assert issubclass(SafariBookmarksView, BaseTabView)
