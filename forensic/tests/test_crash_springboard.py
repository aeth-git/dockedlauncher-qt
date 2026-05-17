"""Comprehensive tests for CrashLogParser and SpringBoardParser."""
import hashlib
import json
import os
import plistlib
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# Make sure the package root is importable
sys.path.insert(0, str(Path(__file__).parents[3]))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ── Backup factory ─────────────────────────────────────────────────────────

def _make_backup(tmp_path, *triples):
    """Build a minimal iTunes backup directory from (domain, rel_path, content) triples.

    Returns an open BackupSource.
    """
    from forensic.sources.backup import BackupSource

    file_map = {}
    for domain, rel, content in triples:
        fid = hashlib.sha1(f"{domain}-{rel}".encode()).hexdigest()
        (tmp_path / fid[:2]).mkdir(exist_ok=True)
        data = content if isinstance(content, bytes) else content.encode()
        (tmp_path / fid[:2] / fid).write_bytes(data)
        file_map[(domain, rel)] = fid

    conn = sqlite3.connect(str(tmp_path / "Manifest.db"))
    conn.execute(
        "CREATE TABLE Files "
        "(fileID TEXT, domain TEXT, relativePath TEXT, flags INTEGER, file BLOB)"
    )
    for (dom, rel), fid in file_map.items():
        conn.execute("INSERT INTO Files VALUES (?,?,?,?,?)", (fid, dom, rel, 1, None))
    conn.commit()
    conn.close()

    (tmp_path / "Manifest.plist").write_bytes(
        plistlib.dumps({"IsEncrypted": False})
    )
    (tmp_path / "Info.plist").write_bytes(
        plistlib.dumps({"Device Name": "Test iPhone", "Product Version": "16.3.1"})
    )

    src = BackupSource(str(tmp_path))
    src.open()
    return src


# ── Sample data builders ───────────────────────────────────────────────────

def _make_ips_content():
    return json.dumps({
        "bug_type": "309",
        "timestamp": "2023-06-15 10:00:00.00 +0000",
        "os_version": "iPhone OS 16.3.1 (20D47)",
        "incident_identifier": "ABC123",
        "procName": "Safari",
        "bundleID": "com.apple.mobilesafari",
        "exception": {"type": "EXC_BAD_ACCESS", "codes": "0x1"},
        "termination": {"namespace": "SIGNAL", "code": 11, "indicator": "SIGSEGV"},
    })


def _make_crash_content():
    return (
        "Process:         MyApp [1234]\n"
        "Bundle Identifier: com.example.myapp\n"
        "Exception Type:  EXC_BAD_ACCESS (SIGSEGV)\n"
        "Date/Time:       2023-06-15 09:00:00.000 -0700\n"
        "OS Version:      iPhone OS 16.3.1 (20D47)\n"
    )


def _make_iconstate_plist():
    return plistlib.dumps({
        "iconLists": [
            ["com.apple.Camera", {"displayIdentifier": "com.apple.Photos"}, "com.apple.Maps"],
            ["com.example.myapp", "com.another.app"],
        ],
        "buttonBar": ["com.apple.MobileSMS", "com.apple.mobilephone"],
        "hiddenIconLists": [["com.hidden.app"]],
    })


# ── CrashLogParser tests ───────────────────────────────────────────────────

class TestCrashLogParserIPS:
    """Tests for modern JSON .ips crash files."""

    @pytest.fixture()
    def src(self, tmp_path):
        content = _make_ips_content()
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Logs/CrashReporter/Safari-2023-06-15.ips", content),
        )
        yield src
        src.close()

    def test_returns_one_record(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert len(records) == 1

    def test_required_fields_present(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        required = {"timestamp", "process", "bundle_id", "exception_type",
                    "signal", "reason", "ios_version", "file_name"}
        for r in records:
            assert required.issubset(r.keys()), f"Missing: {required - r.keys()}"

    def test_process_name(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert records[0]["process"] == "Safari"

    def test_bundle_id(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert records[0]["bundle_id"] == "com.apple.mobilesafari"

    def test_exception_type(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert records[0]["exception_type"] == "EXC_BAD_ACCESS"

    def test_signal_extracted(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert "SIGSEGV" in records[0]["signal"] or "11" in records[0]["signal"]

    def test_ios_version(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert "16.3.1" in records[0]["ios_version"]

    def test_file_name(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert records[0]["file_name"].endswith(".ips")

    def test_timestamp_present(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert "2023-06-15" in records[0]["timestamp"]


class TestCrashLogParserCrash:
    """Tests for legacy text .crash files."""

    @pytest.fixture()
    def src(self, tmp_path):
        content = _make_crash_content()
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Logs/DiagnosticReports/MyApp-2023-06-15.crash", content),
        )
        yield src
        src.close()

    def test_returns_one_record(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert len(records) == 1

    def test_required_fields_present(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        required = {"timestamp", "process", "bundle_id", "exception_type",
                    "signal", "reason", "ios_version", "file_name"}
        for r in records:
            assert required.issubset(r.keys())

    def test_process_name(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert records[0]["process"] == "MyApp"

    def test_bundle_id(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert records[0]["bundle_id"] == "com.example.myapp"

    def test_exception_type(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert records[0]["exception_type"] == "EXC_BAD_ACCESS"

    def test_signal_from_parenthetical(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert records[0]["signal"] == "SIGSEGV"

    def test_timestamp_present(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert "2023-06-15" in records[0]["timestamp"]

    def test_ios_version(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert "16.3.1" in records[0]["ios_version"]

    def test_file_name_ends_with_crash(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert records[0]["file_name"].endswith(".crash")


class TestCrashLogParserMixed:
    """Tests for mixed .ips + .crash + multiple domains."""

    @pytest.fixture()
    def src(self, tmp_path):
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Logs/CrashReporter/Safari.ips",
             _make_ips_content()),
            ("HomeDomain", "Library/Logs/DiagnosticReports/MyApp.crash",
             _make_crash_content()),
            # A file that should be ignored (wrong extension)
            ("HomeDomain", "Library/Logs/CrashReporter/readme.txt",
             "ignore me"),
        )
        yield src
        src.close()

    def test_returns_two_records(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        assert len(records) == 2

    def test_both_file_types_present(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        extensions = {r["file_name"].rsplit(".", 1)[-1] for r in records}
        assert "ips" in extensions
        assert "crash" in extensions

    def test_txt_file_excluded(self, src):
        from forensic.parsers.crash_logs import CrashLogParser
        records = CrashLogParser(src).parse()
        file_names = [r["file_name"] for r in records]
        assert not any(fn.endswith(".txt") for fn in file_names)


class TestCrashLogParserEdgeCases:
    """Edge-case and error tests."""

    def test_no_crash_files_raises_parser_error(self, tmp_path):
        from forensic.parsers.crash_logs import CrashLogParser
        from forensic.parsers.base import ParserError
        # Backup with no crash files at all
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Preferences/com.apple.foo.plist", b"data"),
        )
        try:
            with pytest.raises(ParserError, match="No crash logs found"):
                CrashLogParser(src).parse()
        finally:
            src.close()

    def test_root_domain_prefix_scanned(self, tmp_path):
        from forensic.parsers.crash_logs import CrashLogParser
        src = _make_backup(
            tmp_path,
            ("RootDomain", "Library/Logs/CrashReporter/kernel.crash",
             _make_crash_content()),
        )
        try:
            records = CrashLogParser(src).parse()
            assert len(records) == 1
        finally:
            src.close()

    def test_all_string_fields(self, tmp_path):
        """Every field in the returned dict must be a str (not None or int)."""
        from forensic.parsers.crash_logs import CrashLogParser
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Logs/CrashReporter/test.ips",
             _make_ips_content()),
        )
        try:
            records = CrashLogParser(src).parse()
            for r in records:
                for key, val in r.items():
                    assert isinstance(val, str), \
                        f"Field '{key}' is {type(val).__name__}, expected str"
        finally:
            src.close()

    def test_ips_without_exception_block(self, tmp_path):
        """IPS file missing the 'exception' key should not crash the parser."""
        from forensic.parsers.crash_logs import CrashLogParser
        minimal_ips = json.dumps({
            "bug_type": "309",
            "timestamp": "2023-01-01 00:00:00.00 +0000",
            "os_version": "iPhone OS 16.0 (20A362)",
            "procName": "SpringBoard",
            "bundleID": "com.apple.springboard",
            "termination": {"namespace": "SIGNAL", "code": 9, "indicator": "SIGKILL"},
        })
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Logs/CrashReporter/SpringBoard.ips", minimal_ips),
        )
        try:
            records = CrashLogParser(src).parse()
            assert len(records) == 1
            assert records[0]["process"] == "SpringBoard"
        finally:
            src.close()

    def test_crash_without_bundle_identifier(self, tmp_path):
        """Legacy .crash without Bundle Identifier line should still parse."""
        from forensic.parsers.crash_logs import CrashLogParser
        content = (
            "Process:         OtherApp [999]\n"
            "Exception Type:  EXC_CRASH (SIGABRT)\n"
            "Date/Time:       2023-01-01 12:00:00.000 +0000\n"
            "OS Version:      iPhone OS 15.7 (19H115)\n"
        )
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Logs/DiagnosticReports/OtherApp.crash", content),
        )
        try:
            records = CrashLogParser(src).parse()
            assert len(records) == 1
            assert records[0]["process"] == "OtherApp"
            assert records[0]["bundle_id"] == ""
        finally:
            src.close()


# ── SpringBoardParser tests ────────────────────────────────────────────────

class TestSpringBoardParserBasic:
    """Basic parsing tests using the sample IconState.plist."""

    @pytest.fixture()
    def src(self, tmp_path):
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/SpringBoard/IconState.plist",
             _make_iconstate_plist()),
        )
        yield src
        src.close()

    def test_returns_records(self, src):
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        assert len(records) > 0

    def test_required_fields_present(self, src):
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        required = {"bundle_id", "page_index", "position", "is_hidden", "section"}
        for r in records:
            assert required.issubset(r.keys()), f"Missing: {required - r.keys()}"

    def test_homescreen_icons_count(self, src):
        """Page 0 has 3 icons, page 1 has 2 → 5 homescreen entries."""
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        homescreen = [r for r in records if r["section"] == "homescreen"]
        assert len(homescreen) == 5

    def test_dock_icons_count(self, src):
        """buttonBar has 2 entries."""
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        dock = [r for r in records if r["section"] == "dock"]
        assert len(dock) == 2

    def test_hidden_icons_count(self, src):
        """hiddenIconLists has 1 entry."""
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        hidden = [r for r in records if r["section"] == "hidden"]
        assert len(hidden) == 1

    def test_string_form_bundle_id(self, src):
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        bundle_ids = {r["bundle_id"] for r in records}
        assert "com.apple.Camera" in bundle_ids

    def test_dict_form_bundle_id(self, src):
        """{'displayIdentifier': 'com.apple.Photos'} should be extracted."""
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        bundle_ids = {r["bundle_id"] for r in records}
        assert "com.apple.Photos" in bundle_ids

    def test_dock_is_not_hidden(self, src):
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        dock = [r for r in records if r["section"] == "dock"]
        assert all(not r["is_hidden"] for r in dock)

    def test_hidden_section_is_hidden_flag(self, src):
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        hidden = [r for r in records if r["section"] == "hidden"]
        assert all(r["is_hidden"] for r in hidden)

    def test_homescreen_is_not_hidden(self, src):
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        homescreen = [r for r in records if r["section"] == "homescreen"]
        assert all(not r["is_hidden"] for r in homescreen)

    def test_page_index_populated_for_homescreen(self, src):
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        homescreen = [r for r in records if r["section"] == "homescreen"]
        pages = {r["page_index"] for r in homescreen}
        assert 0 in pages
        assert 1 in pages

    def test_position_populated(self, src):
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        for r in records:
            assert isinstance(r["position"], int)
            assert r["position"] >= 0

    def test_hidden_bundle_id(self, src):
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        hidden = [r for r in records if r["section"] == "hidden"]
        assert hidden[0]["bundle_id"] == "com.hidden.app"

    def test_total_record_count(self, src):
        """5 homescreen + 2 dock + 1 hidden = 8 total."""
        from forensic.parsers.springboard import SpringBoardParser
        records = SpringBoardParser(src).parse()
        assert len(records) == 8


class TestSpringBoardParserEdgeCases:
    """Edge cases and error handling."""

    def test_missing_plist_raises_parser_error(self, tmp_path):
        from forensic.parsers.springboard import SpringBoardParser
        from forensic.parsers.base import ParserError
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Preferences/com.apple.foo.plist", b"x"),
        )
        try:
            with pytest.raises(ParserError):
                SpringBoardParser(src).parse()
        finally:
            src.close()

    def test_no_hidden_icon_lists_key(self, tmp_path):
        """Plist without hiddenIconLists should work fine."""
        from forensic.parsers.springboard import SpringBoardParser
        plist_bytes = plistlib.dumps({
            "iconLists": [["com.apple.Camera"]],
            "buttonBar": ["com.apple.MobileSMS"],
        })
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/SpringBoard/IconState.plist", plist_bytes),
        )
        try:
            records = SpringBoardParser(src).parse()
            hidden = [r for r in records if r["section"] == "hidden"]
            assert len(hidden) == 0
        finally:
            src.close()

    def test_empty_icon_lists(self, tmp_path):
        """Empty iconLists should return only dock entries."""
        from forensic.parsers.springboard import SpringBoardParser
        plist_bytes = plistlib.dumps({
            "iconLists": [],
            "buttonBar": ["com.apple.MobileSMS"],
        })
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/SpringBoard/IconState.plist", plist_bytes),
        )
        try:
            records = SpringBoardParser(src).parse()
            sections = {r["section"] for r in records}
            assert sections == {"dock"}
        finally:
            src.close()

    def test_no_button_bar_key(self, tmp_path):
        """Plist without buttonBar should work fine."""
        from forensic.parsers.springboard import SpringBoardParser
        plist_bytes = plistlib.dumps({
            "iconLists": [["com.apple.Camera"]],
        })
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/SpringBoard/IconState.plist", plist_bytes),
        )
        try:
            records = SpringBoardParser(src).parse()
            dock = [r for r in records if r["section"] == "dock"]
            assert len(dock) == 0
        finally:
            src.close()

    def test_section_values_are_valid(self, tmp_path):
        from forensic.parsers.springboard import SpringBoardParser
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/SpringBoard/IconState.plist",
             _make_iconstate_plist()),
        )
        try:
            records = SpringBoardParser(src).parse()
            valid_sections = {"homescreen", "dock", "hidden"}
            for r in records:
                assert r["section"] in valid_sections, \
                    f"Unexpected section: {r['section']}"
        finally:
            src.close()

    def test_is_hidden_is_bool(self, tmp_path):
        from forensic.parsers.springboard import SpringBoardParser
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/SpringBoard/IconState.plist",
             _make_iconstate_plist()),
        )
        try:
            records = SpringBoardParser(src).parse()
            for r in records:
                assert isinstance(r["is_hidden"], bool), \
                    f"is_hidden is {type(r['is_hidden']).__name__}, expected bool"
        finally:
            src.close()


# ── View smoke tests ───────────────────────────────────────────────────────

class TestCrashLogsView:
    @pytest.fixture(autouse=True)
    def setup(self):
        import sys
        from PyQt5.QtWidgets import QApplication
        self._app = QApplication.instance() or QApplication(sys.argv)
        from forensic.views.crash_logs_view import CrashLogsView
        self.view = CrashLogsView()
        yield
        self.view.close()

    def test_tab_name(self):
        from forensic.views.crash_logs_view import CrashLogsView
        assert CrashLogsView.TAB_NAME == "Crash Logs"

    def test_columns_defined(self):
        from forensic.views.crash_logs_view import CrashLogsView
        keys = [col[0] for col in CrashLogsView.COLUMNS]
        assert "timestamp" in keys
        assert "process" in keys
        assert "bundle_id" in keys
        assert "exception_type" in keys
        assert "signal" in keys
        assert "ios_version" in keys
        assert "file_name" in keys

    def test_load_records(self):
        from forensic.views.crash_logs_view import CrashLogsView
        recs = [
            {"timestamp": "2023-06-15 10:00:00", "process": "Safari",
             "bundle_id": "com.apple.mobilesafari", "exception_type": "EXC_BAD_ACCESS",
             "signal": "SIGSEGV", "reason": "0x1", "ios_version": "16.3.1",
             "file_name": "Safari.ips"},
        ]
        self.view.load_records(recs)
        assert self.view._model is not None
        assert self.view._model.rowCount() == 1

    def test_show_empty(self):
        self.view.show_empty("No data")
        assert self.view._model.rowCount() == 0

    def test_column_count_matches_columns(self):
        from forensic.views.crash_logs_view import CrashLogsView
        recs = [{"timestamp": "", "process": "", "bundle_id": "",
                 "exception_type": "", "signal": "", "reason": "",
                 "ios_version": "", "file_name": ""}]
        self.view.load_records(recs)
        assert self.view._model.columnCount() == len(CrashLogsView.COLUMNS)


class TestSpringBoardView:
    @pytest.fixture(autouse=True)
    def setup(self):
        import sys
        from PyQt5.QtWidgets import QApplication
        self._app = QApplication.instance() or QApplication(sys.argv)
        from forensic.views.springboard_view import SpringBoardView
        self.view = SpringBoardView()
        yield
        self.view.close()

    def test_tab_name(self):
        from forensic.views.springboard_view import SpringBoardView
        assert SpringBoardView.TAB_NAME == "Home Screen"

    def test_columns_defined(self):
        from forensic.views.springboard_view import SpringBoardView
        keys = [col[0] for col in SpringBoardView.COLUMNS]
        assert "bundle_id" in keys
        assert "section" in keys
        assert "page_index" in keys
        assert "position" in keys
        assert "is_hidden" in keys

    def test_load_records(self):
        recs = [
            {"bundle_id": "com.apple.Camera", "section": "homescreen",
             "page_index": 0, "position": 0, "is_hidden": False},
        ]
        self.view.load_records(recs)
        assert self.view._model.rowCount() == 1

    def test_show_empty(self):
        self.view.show_empty("No data")
        assert self.view._model.rowCount() == 0

    def test_column_count_matches_columns(self):
        from forensic.views.springboard_view import SpringBoardView
        recs = [{"bundle_id": "", "section": "", "page_index": 0,
                 "position": 0, "is_hidden": False}]
        self.view.load_records(recs)
        assert self.view._model.columnCount() == len(SpringBoardView.COLUMNS)
