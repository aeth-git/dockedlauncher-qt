"""Comprehensive tests for SiriAnalyticsParser and AppStorePurchasesParser."""
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

from forensic.tests.conftest import make_backup as _make_backup


# ── DB builders ───────────────────────────────────────────────────────────────

def _make_siri_ios12_db() -> bytes:
    """iOS 12-14 style: SiriSession + SiriRequest tables."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE SiriSession "
        "(id INTEGER PRIMARY KEY, startDate REAL, endDate REAL, duration_ms INTEGER)"
    )
    conn.execute(
        "CREATE TABLE SiriRequest "
        "(id INTEGER PRIMARY KEY, session_id INTEGER, intent TEXT, "
        "bundleID TEXT, latency_ms INTEGER)"
    )
    t = 1655287200 - APPLE_EPOCH  # 2022-06-15 10:00:00 UTC in Apple epoch
    conn.execute("INSERT INTO SiriSession VALUES (1,?,?,500)", (t, t + 0.5))
    conn.execute(
        "INSERT INTO SiriRequest VALUES (1,1,'INSendMessageIntent','com.apple.MobileSMS',120)"
    )
    conn.execute(
        "INSERT INTO SiriRequest VALUES (2,1,'INSetAlarmClockIntent','com.apple.mobiletimer',95)"
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_siri_ios15_db() -> bytes:
    """iOS 15+ style: AppPrediction table only."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE AppPrediction "
        "(bundleId TEXT, rank INTEGER, timestamp REAL)"
    )
    t = 1655287200 - APPLE_EPOCH
    conn.execute("INSERT INTO AppPrediction VALUES ('com.apple.Maps',1,?)", (t,))
    conn.execute("INSERT INTO AppPrediction VALUES ('com.apple.Music',2,?)", (t + 3600,))
    conn.execute("INSERT INTO AppPrediction VALUES ('com.example.app',3,?)", (t + 7200,))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_siri_shortcut_db() -> bytes:
    """Backup schema variant: SiriShortcut table."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE SiriShortcut "
        "(id INTEGER PRIMARY KEY, shortcutTitle TEXT, bundleID TEXT)"
    )
    conn.execute("INSERT INTO SiriShortcut VALUES (1,'Call Home','com.apple.mobilephone')")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_siri_unknown_db() -> bytes:
    """DB with no known Siri tables — should trigger ParserError."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute("CREATE TABLE FooBar (x INTEGER)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_app_store_db() -> bytes:
    """Standard purchased_software_map schema."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE purchased_software_map ("
        "adam_id INTEGER PRIMARY KEY, software_name TEXT, bundle_id TEXT, "
        "purchased_date REAL, price REAL, installed_version_string TEXT)"
    )
    t = 1655287200 - APPLE_EPOCH
    conn.execute(
        "INSERT INTO purchased_software_map VALUES (12345,'MyApp','com.example.myapp',?,0.99,'2.1.0')",
        (t,),
    )
    conn.execute(
        "INSERT INTO purchased_software_map VALUES (67890,'FreeApp','com.free.app',?,0.0,'1.0')",
        (t + 86400,),
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_app_store_items_db() -> bytes:
    """Alternate schema: generic 'items' table."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE items ("
        "id INTEGER PRIMARY KEY, name TEXT, bundle_id TEXT, date REAL, price REAL)"
    )
    t = 1655287200 - APPLE_EPOCH
    conn.execute("INSERT INTO items VALUES (1,'AppOne','com.one.app',?,1.99)", (t,))
    conn.execute("INSERT INTO items VALUES (2,'AppTwo','com.two.app',?,0.0)", (t + 3600,))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_app_store_store_item_db() -> bytes:
    """Alternate schema: store_item table."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE store_item ("
        "item_id INTEGER PRIMARY KEY, app_name TEXT, bundle_identifier TEXT, "
        "purchase_date REAL, price REAL, version TEXT)"
    )
    t = 1655287200 - APPLE_EPOCH
    conn.execute(
        "INSERT INTO store_item VALUES (999,'StoreApp','com.store.app',?,2.99,'3.0')",
        (t,),
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_app_store_no_known_table_db() -> bytes:
    """DB with no recognizable table — should raise ParserError."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute("CREATE TABLE metadata (key TEXT, value TEXT)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


# ── Constants ─────────────────────────────────────────────────────────────────

_SIRI_DOMAIN = "HomeDomain"
_SIRI_PATH = "Library/Assistant/SiriAnalytics.db"
_APPSTORE_DOMAIN = "HomeDomain"
_APPSTORE_PATH = "Library/com.apple.iTunesStore/itunesstored2.sqlitedb"


# ── SiriAnalyticsParser tests ─────────────────────────────────────────────────

class TestSiriAnalyticsParserIOS12:
    """Tests for iOS 12-14 schema (SiriSession + SiriRequest)."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from forensic.parsers.siri_analytics import SiriAnalyticsParser
        self.src = _make_backup(
            tmp_path, (_SIRI_DOMAIN, _SIRI_PATH, _make_siri_ios12_db())
        )
        self.records = SiriAnalyticsParser(self.src).parse()
        yield
        self.src.close()

    def test_returns_two_records(self):
        assert len(self.records) == 2

    def test_required_fields_present(self):
        required = {"timestamp", "intent", "app_bundle_id", "latency_ms", "session_id"}
        for r in self.records:
            assert required.issubset(r.keys()), f"Missing: {required - r.keys()}"

    def test_timestamp_format(self):
        for r in self.records:
            assert r["timestamp"] is not None
            assert len(r["timestamp"]) == 19
            assert r["timestamp"].startswith("2022-06-15")

    def test_intent_values(self):
        intents = {r["intent"] for r in self.records}
        assert "INSendMessageIntent" in intents
        assert "INSetAlarmClockIntent" in intents

    def test_bundle_ids_populated(self):
        bundles = {r["app_bundle_id"] for r in self.records}
        assert "com.apple.MobileSMS" in bundles
        assert "com.apple.mobiletimer" in bundles

    def test_latency_ms_values(self):
        latencies = {r["latency_ms"] for r in self.records}
        assert 120 in latencies
        assert 95 in latencies

    def test_session_id_populated(self):
        for r in self.records:
            assert r["session_id"] == 1


class TestSiriAnalyticsParserIOS15:
    """Tests for iOS 15+ schema (AppPrediction)."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from forensic.parsers.siri_analytics import SiriAnalyticsParser
        self.src = _make_backup(
            tmp_path, (_SIRI_DOMAIN, _SIRI_PATH, _make_siri_ios15_db())
        )
        self.records = SiriAnalyticsParser(self.src).parse()
        yield
        self.src.close()

    def test_returns_three_records(self):
        assert len(self.records) == 3

    def test_required_fields_present(self):
        required = {"timestamp", "intent", "app_bundle_id", "latency_ms", "session_id"}
        for r in self.records:
            assert required.issubset(r.keys())

    def test_bundle_ids_populated(self):
        bundles = {r["app_bundle_id"] for r in self.records}
        assert "com.apple.Maps" in bundles
        assert "com.apple.Music" in bundles
        assert "com.example.app" in bundles

    def test_intent_contains_rank(self):
        for r in self.records:
            assert "AppPrediction" in r["intent"]
            assert "rank=" in r["intent"]

    def test_timestamps_populated(self):
        for r in self.records:
            assert r["timestamp"] is not None
            assert r["timestamp"].startswith("2022-06-15")

    def test_latency_is_none_for_ios15(self):
        for r in self.records:
            assert r["latency_ms"] is None


class TestSiriAnalyticsParserNotFound:
    """Parser raises FileNotFoundError when DB is absent."""

    def test_missing_db_raises_file_not_found(self, tmp_path):
        from forensic.parsers.siri_analytics import SiriAnalyticsParser
        # Empty backup — no Siri DB
        src = _make_backup(tmp_path)
        try:
            with pytest.raises(FileNotFoundError):
                SiriAnalyticsParser(src).parse()
        finally:
            src.close()


class TestSiriAnalyticsParserUnknownSchema:
    """Parser raises ParserError when no known table is found."""

    def test_unknown_schema_raises_parser_error(self, tmp_path):
        from forensic.parsers.siri_analytics import SiriAnalyticsParser
        from forensic.parsers.base import ParserError
        src = _make_backup(
            tmp_path, (_SIRI_DOMAIN, _SIRI_PATH, _make_siri_unknown_db())
        )
        try:
            with pytest.raises(ParserError, match="No known Siri table"):
                SiriAnalyticsParser(src).parse()
        finally:
            src.close()

    def test_error_message_includes_table_names(self, tmp_path):
        from forensic.parsers.siri_analytics import SiriAnalyticsParser
        from forensic.parsers.base import ParserError
        src = _make_backup(
            tmp_path, (_SIRI_DOMAIN, _SIRI_PATH, _make_siri_unknown_db())
        )
        try:
            with pytest.raises(ParserError) as exc_info:
                SiriAnalyticsParser(src).parse()
            assert "FooBar" in str(exc_info.value)
        finally:
            src.close()


class TestSiriAnalyticsParserShortcutVariant:
    """SiriShortcut table fallback."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from forensic.parsers.siri_analytics import SiriAnalyticsParser
        self.src = _make_backup(
            tmp_path, (_SIRI_DOMAIN, _SIRI_PATH, _make_siri_shortcut_db())
        )
        self.records = SiriAnalyticsParser(self.src).parse()
        yield
        self.src.close()

    def test_returns_one_record(self):
        assert len(self.records) == 1

    def test_required_fields_present(self):
        required = {"timestamp", "intent", "app_bundle_id", "latency_ms", "session_id"}
        for r in self.records:
            assert required.issubset(r.keys())

    def test_bundle_id_populated(self):
        assert self.records[0]["app_bundle_id"] == "com.apple.mobilephone"

    def test_intent_populated(self):
        assert self.records[0]["intent"] == "Call Home"


# ── AppStorePurchasesParser tests ─────────────────────────────────────────────

class TestAppStorePurchasesParserStandard:
    """Tests against the common purchased_software_map schema."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from forensic.parsers.app_store import AppStorePurchasesParser
        self.src = _make_backup(
            tmp_path, (_APPSTORE_DOMAIN, _APPSTORE_PATH, _make_app_store_db())
        )
        self.records = AppStorePurchasesParser(self.src).parse()
        yield
        self.src.close()

    def test_returns_two_records(self):
        assert len(self.records) == 2

    def test_required_fields_present(self):
        required = {"app_name", "bundle_id", "purchase_date", "version", "price", "item_id"}
        for r in self.records:
            assert required.issubset(r.keys()), f"Missing: {required - r.keys()}"

    def test_app_names_populated(self):
        names = {r["app_name"] for r in self.records}
        assert "MyApp" in names
        assert "FreeApp" in names

    def test_bundle_ids_populated(self):
        bundles = {r["bundle_id"] for r in self.records}
        assert "com.example.myapp" in bundles
        assert "com.free.app" in bundles

    def test_purchase_date_format(self):
        for r in self.records:
            assert r["purchase_date"] is not None
            assert r["purchase_date"].startswith("2022-06-1")

    def test_price_formatting(self):
        prices = {r["price"] for r in self.records}
        # Paid app: $0.99
        assert "$0.99" in prices
        # Free app: "Free"
        assert "Free" in prices

    def test_version_populated(self):
        versions = {r["version"] for r in self.records}
        assert "2.1.0" in versions
        assert "1.0" in versions

    def test_item_id_populated(self):
        ids = {r["item_id"] for r in self.records}
        assert "12345" in ids
        assert "67890" in ids

    def test_sorted_by_purchase_date_desc(self):
        # FreeApp purchased one day after MyApp — should appear first
        assert self.records[0]["app_name"] == "FreeApp"
        assert self.records[1]["app_name"] == "MyApp"


class TestAppStorePurchasesParserItemsTable:
    """Alternate schema: generic 'items' table."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from forensic.parsers.app_store import AppStorePurchasesParser
        self.src = _make_backup(
            tmp_path, (_APPSTORE_DOMAIN, _APPSTORE_PATH, _make_app_store_items_db())
        )
        self.records = AppStorePurchasesParser(self.src).parse()
        yield
        self.src.close()

    def test_returns_two_records(self):
        assert len(self.records) == 2

    def test_required_fields_present(self):
        required = {"app_name", "bundle_id", "purchase_date", "version", "price", "item_id"}
        for r in self.records:
            assert required.issubset(r.keys())

    def test_app_names_found(self):
        names = {r["app_name"] for r in self.records}
        assert "AppOne" in names
        assert "AppTwo" in names

    def test_bundle_ids_found(self):
        bundles = {r["bundle_id"] for r in self.records}
        assert "com.one.app" in bundles
        assert "com.two.app" in bundles

    def test_timestamps_populated(self):
        for r in self.records:
            assert r["purchase_date"] is not None


class TestAppStorePurchasesParserStoreItemTable:
    """Alternate schema: store_item table."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from forensic.parsers.app_store import AppStorePurchasesParser
        self.src = _make_backup(
            tmp_path, (_APPSTORE_DOMAIN, _APPSTORE_PATH, _make_app_store_store_item_db())
        )
        self.records = AppStorePurchasesParser(self.src).parse()
        yield
        self.src.close()

    def test_returns_one_record(self):
        assert len(self.records) == 1

    def test_required_fields_present(self):
        required = {"app_name", "bundle_id", "purchase_date", "version", "price", "item_id"}
        for r in self.records:
            assert required.issubset(r.keys())

    def test_app_name_found(self):
        assert self.records[0]["app_name"] == "StoreApp"

    def test_version_found(self):
        assert self.records[0]["version"] == "3.0"

    def test_price_formatted(self):
        assert self.records[0]["price"] == "$2.99"


class TestAppStorePurchasesParserNotFound:
    """Parser raises FileNotFoundError when DB is absent."""

    def test_missing_db_raises_file_not_found(self, tmp_path):
        from forensic.parsers.app_store import AppStorePurchasesParser
        src = _make_backup(tmp_path)
        try:
            with pytest.raises(FileNotFoundError):
                AppStorePurchasesParser(src).parse()
        finally:
            src.close()


class TestAppStorePurchasesParserNoKnownTable:
    """Parser raises ParserError when no recognizable table exists."""

    def test_unknown_schema_raises_parser_error(self, tmp_path):
        from forensic.parsers.app_store import AppStorePurchasesParser
        from forensic.parsers.base import ParserError
        src = _make_backup(
            tmp_path,
            (_APPSTORE_DOMAIN, _APPSTORE_PATH, _make_app_store_no_known_table_db()),
        )
        try:
            with pytest.raises(ParserError, match="No known App Store table"):
                AppStorePurchasesParser(src).parse()
        finally:
            src.close()

    def test_error_message_includes_table_names(self, tmp_path):
        from forensic.parsers.app_store import AppStorePurchasesParser
        from forensic.parsers.base import ParserError
        src = _make_backup(
            tmp_path,
            (_APPSTORE_DOMAIN, _APPSTORE_PATH, _make_app_store_no_known_table_db()),
        )
        try:
            with pytest.raises(ParserError) as exc_info:
                AppStorePurchasesParser(src).parse()
            assert "metadata" in str(exc_info.value)
        finally:
            src.close()


# ── View tests ────────────────────────────────────────────────────────────────

class TestSiriView:
    """Smoke-test SiriView instantiation and column spec."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from forensic.views.siri_view import SiriView
        self.view = SiriView()
        yield
        self.view.close()

    def test_tab_name(self):
        assert self.view.TAB_NAME == "Siri"

    def test_column_keys(self):
        keys = [k for k, _ in self.view.COLUMNS]
        assert "timestamp" in keys
        assert "intent" in keys
        assert "app_bundle_id" in keys
        assert "latency_ms" in keys
        assert "session_id" in keys

    def test_column_count(self):
        assert len(self.view.COLUMNS) == 5

    def test_load_records(self):
        self.view.load_records([
            {"timestamp": "2022-06-15 10:00:00", "intent": "INSendMessageIntent",
             "app_bundle_id": "com.apple.MobileSMS", "latency_ms": 120, "session_id": 1},
        ])
        assert len(self.view._all_records) == 1

    def test_column_headers(self):
        headers = [h for _, h in self.view.COLUMNS]
        assert "Time" in headers
        assert "Intent" in headers
        assert "App Bundle ID" in headers
        assert "Latency (ms)" in headers
        assert "Session" in headers


class TestAppStoreView:
    """Smoke-test AppStoreView instantiation and column spec."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from forensic.views.app_store_view import AppStoreView
        self.view = AppStoreView()
        yield
        self.view.close()

    def test_tab_name(self):
        assert self.view.TAB_NAME == "App Store"

    def test_column_keys(self):
        keys = [k for k, _ in self.view.COLUMNS]
        assert "purchase_date" in keys
        assert "app_name" in keys
        assert "bundle_id" in keys
        assert "version" in keys
        assert "price" in keys
        assert "item_id" in keys

    def test_column_count(self):
        assert len(self.view.COLUMNS) == 6

    def test_load_records(self):
        self.view.load_records([
            {"purchase_date": "2022-06-15 10:00:00", "app_name": "MyApp",
             "bundle_id": "com.example.myapp", "version": "2.1.0",
             "price": "$0.99", "item_id": "12345"},
        ])
        assert len(self.view._all_records) == 1

    def test_column_headers(self):
        headers = [h for _, h in self.view.COLUMNS]
        assert "Purchased" in headers
        assert "App Name" in headers
        assert "Bundle ID" in headers
        assert "Version" in headers
        assert "Price" in headers
        assert "Item ID" in headers
