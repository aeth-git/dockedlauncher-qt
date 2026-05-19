"""Comprehensive tests for PowerLogParser and AggregatedDictParser."""
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


def _make_powerlog_db() -> bytes:
    """Return bytes of a synthetic PLSQL PowerLog database (PLProcessMonitor_Foreground)."""
    tmp = tempfile.mktemp(suffix=".PLSQL")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE PLProcessMonitor_Foreground ("
        "timestamp REAL, bundleID TEXT, foregroundTime REAL, "
        "BackgroundTime REAL, batteryLevel REAL)"
    )
    t = 1655287200 - APPLE_EPOCH  # 2022-06-15 10:00:00 UTC in Apple epoch
    conn.execute(
        "INSERT INTO PLProcessMonitor_Foreground VALUES (?,?,?,?,?)",
        (t, "com.apple.mobilesafari", 3600000, 0, 0.85),
    )
    conn.execute(
        "INSERT INTO PLProcessMonitor_Foreground VALUES (?,?,?,?,?)",
        (t + 3600, "com.apple.MobileSMS", 1800000, 0, 0.72),
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_battery_agent_db() -> bytes:
    """Return bytes of a synthetic PLSQL file with PLBatteryAgent_EventBackward_BatteryUI."""
    tmp = tempfile.mktemp(suffix=".PLSQL")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE PLBatteryAgent_EventBackward_BatteryUI ("
        "timestamp REAL, Level REAL, IsCharging INTEGER)"
    )
    t = 1655287200 - APPLE_EPOCH
    conn.execute(
        "INSERT INTO PLBatteryAgent_EventBackward_BatteryUI VALUES (?,?,?)",
        (t, 0.85, 0),
    )
    conn.execute(
        "INSERT INTO PLBatteryAgent_EventBackward_BatteryUI VALUES (?,?,?)",
        (t + 3600, 0.90, 1),
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_aggdict_db_layout1() -> bytes:
    """Return bytes of an AggDict DB using Layout 1 (measurements table, iOS 12-14)."""
    tmp = tempfile.mktemp(suffix=".sqlitedb")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE measurements "
        "(key TEXT, startDate REAL, endDate REAL, value TEXT, unit TEXT)"
    )
    t = 1655287200 - APPLE_EPOCH
    conn.execute(
        "INSERT INTO measurements VALUES (?,?,?,?,?)",
        ("com.apple.smsmessages.sentCount", t, t + 86400, 42, "count"),
    )
    conn.execute(
        "INSERT INTO measurements VALUES (?,?,?,?,?)",
        ("com.apple.CoreLocation.usage", t, t + 86400, 1234.5, "seconds"),
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_aggdict_db_layout2() -> bytes:
    """Return bytes of an AggDict DB using Layout 2 (key_store+value_store, iOS 15+)."""
    tmp = tempfile.mktemp(suffix=".sqlitedb")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE key_store (id INTEGER PRIMARY KEY, key TEXT);
        CREATE TABLE value_store (
            id INTEGER PRIMARY KEY,
            key_id INTEGER,
            start_date REAL,
            end_date REAL,
            double_value REAL,
            string_value TEXT
        );
    """)
    t = 1655287200 - APPLE_EPOCH
    conn.execute("INSERT INTO key_store VALUES (1, 'com.apple.battery.level')")
    conn.execute("INSERT INTO key_store VALUES (2, 'com.apple.network.requests')")
    conn.execute(
        "INSERT INTO value_store VALUES (1, 1, ?, ?, 0.75, NULL)", (t, t + 3600)
    )
    conn.execute(
        "INSERT INTO value_store VALUES (2, 2, ?, ?, NULL, 'high')", (t, t + 86400)
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


# ── PowerLogParser tests ────────────────────────────────────────────────────

class TestPowerLogParser:

    def test_returns_records_from_plsql_file(self, tmp_path):
        """Parser should return records when a valid PLSQL file is present."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/CurrentPower.PLSQL", _make_powerlog_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            assert len(records) >= 1
        finally:
            src.close()

    def test_correct_number_of_records(self, tmp_path):
        """Two rows inserted → at least 2 records returned."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/CurrentPower.PLSQL", _make_powerlog_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_bundle_id_field_populated(self, tmp_path):
        """Bundle IDs from PLProcessMonitor_Foreground should appear in records."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/CurrentPower.PLSQL", _make_powerlog_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            bundle_ids = {r["bundle_id"] for r in records}
            assert "com.apple.mobilesafari" in bundle_ids
            assert "com.apple.MobileSMS" in bundle_ids
        finally:
            src.close()

    def test_foreground_time_populated(self, tmp_path):
        """foreground_time_ms should be non-None for PLProcessMonitor records."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/CurrentPower.PLSQL", _make_powerlog_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            safari = next(r for r in records if r.get("bundle_id") == "com.apple.mobilesafari")
            assert safari["foreground_time_ms"] == 3600000
        finally:
            src.close()

    def test_battery_level_populated(self, tmp_path):
        """batteryLevel column should be mapped to battery_level field."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/CurrentPower.PLSQL", _make_powerlog_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            safari = next(r for r in records if r.get("bundle_id") == "com.apple.mobilesafari")
            assert safari["battery_level"] == pytest.approx(0.85)
        finally:
            src.close()

    def test_timestamp_formatted(self, tmp_path):
        """Timestamps should be converted from Apple epoch to ISO format."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/CurrentPower.PLSQL", _make_powerlog_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            for r in records:
                assert r["timestamp"] is not None
                assert "2022-06-15" in r["timestamp"]
        finally:
            src.close()

    def test_source_table_field_set(self, tmp_path):
        """source_table should identify which PowerLog table the record came from."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/CurrentPower.PLSQL", _make_powerlog_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            for r in records:
                assert r["source_table"] == "PLProcessMonitor_Foreground"
        finally:
            src.close()

    def test_source_file_field_set(self, tmp_path):
        """source_file should contain the relative path of the PLSQL file."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/CurrentPower.PLSQL", _make_powerlog_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            for r in records:
                assert "BatteryLife" in r["source_file"]
        finally:
            src.close()

    def test_required_fields_present(self, tmp_path):
        """All expected output keys must be present in every record."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/CurrentPower.PLSQL", _make_powerlog_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            required = {
                "timestamp", "bundle_id", "foreground_time_ms",
                "battery_level", "charging_state", "source_table", "source_file",
            }
            for r in records:
                assert required.issubset(r.keys()), f"Missing: {required - r.keys()}"
        finally:
            src.close()

    def test_sqlite_extension_also_accepted(self, tmp_path):
        """Files ending in .sqlite should also be processed."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/log.sqlite", _make_powerlog_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            assert len(records) >= 1
        finally:
            src.close()

    def test_battery_agent_table_parsed(self, tmp_path):
        """PLBatteryAgent_EventBackward_BatteryUI should be parsed when present."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/battery.PLSQL", _make_battery_agent_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            assert len(records) >= 1
            assert any(
                r["source_table"] == "PLBatteryAgent_EventBackward_BatteryUI"
                for r in records
            )
        finally:
            src.close()

    def test_battery_agent_charging_state(self, tmp_path):
        """Charging field should be populated from PLBatteryAgent table."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/battery.PLSQL", _make_battery_agent_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            # Second inserted row had IsCharging=1
            charging_records = [r for r in records if r.get("charging_state") == 1]
            assert len(charging_records) >= 1
        finally:
            src.close()

    def test_no_powerlog_files_raises_parser_error(self, tmp_path):
        """When no BatteryLife files exist, ParserError should be raised."""
        from forensic.parsers.powerlog import PowerLogParser
        from forensic.parsers.base import ParserError

        # Create backup with no BatteryLife files
        conn = sqlite3.connect(str(tmp_path / "Manifest.db"))
        conn.execute(
            "CREATE TABLE Files "
            "(fileID TEXT, domain TEXT, relativePath TEXT, flags INTEGER, file BLOB)"
        )
        conn.commit()
        conn.close()
        (tmp_path / "Manifest.plist").write_bytes(plistlib.dumps({"IsEncrypted": False}))
        (tmp_path / "Info.plist").write_bytes(plistlib.dumps({"Device Name": "Test"}))

        from forensic.sources.backup import BackupSource
        src = BackupSource(str(tmp_path))
        src.open()
        try:
            with pytest.raises(ParserError, match="PowerLog not found"):
                PowerLogParser(src).parse()
        finally:
            src.close()

    def test_multiple_plsql_files_combined(self, tmp_path):
        """Records from multiple PLSQL files should all be returned."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/a.PLSQL", _make_powerlog_db()),
            ("HomeDomain", "Library/BatteryLife/b.PLSQL", _make_powerlog_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            # 2 rows per file × 2 files = 4 total
            assert len(records) == 4
        finally:
            src.close()

    def test_file_with_no_known_tables_returns_inventory_record(self, tmp_path):
        """A valid SQLite with no known PowerLog tables should return an inventory record."""
        from forensic.parsers.powerlog import PowerLogParser

        # Build a SQLite file with an unrelated table
        tmp_db = tempfile.mktemp(suffix=".PLSQL")
        conn_tmp = sqlite3.connect(tmp_db)
        conn_tmp.execute("CREATE TABLE SomeOtherTable (id INTEGER)")
        conn_tmp.commit()
        conn_tmp.close()
        db_bytes = Path(tmp_db).read_bytes()
        os.unlink(tmp_db)

        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/BatteryLife/unknown.PLSQL", db_bytes),
        )
        try:
            records = PowerLogParser(src).parse()
            # Should return inventory record(s) with record_count=0
            assert len(records) >= 1
            assert any(r.get("record_count") == 0 for r in records)
        finally:
            src.close()

    def test_rootdomain_candidate_also_scanned(self, tmp_path):
        """Parser should scan RootDomain/Library/BatteryLife/ as well."""
        from forensic.parsers.powerlog import PowerLogParser

        src = _make_backup(
            tmp_path,
            ("RootDomain", "Library/BatteryLife/root.PLSQL", _make_powerlog_db()),
        )
        try:
            records = PowerLogParser(src).parse()
            assert len(records) >= 1
        finally:
            src.close()

    def test_error_message_mentions_filesystem(self, tmp_path):
        """ParserError message should mention filesystem extraction."""
        from forensic.parsers.powerlog import PowerLogParser
        from forensic.parsers.base import ParserError

        conn = sqlite3.connect(str(tmp_path / "Manifest.db"))
        conn.execute(
            "CREATE TABLE Files "
            "(fileID TEXT, domain TEXT, relativePath TEXT, flags INTEGER, file BLOB)"
        )
        conn.commit()
        conn.close()
        (tmp_path / "Manifest.plist").write_bytes(plistlib.dumps({"IsEncrypted": False}))
        (tmp_path / "Info.plist").write_bytes(plistlib.dumps({}))

        from forensic.sources.backup import BackupSource
        src = BackupSource(str(tmp_path))
        src.open()
        try:
            with pytest.raises(ParserError) as exc_info:
                PowerLogParser(src).parse()
            assert "filesystem" in str(exc_info.value).lower() or "jailbroken" in str(exc_info.value).lower()
        finally:
            src.close()


# ── AggregatedDictParser tests ──────────────────────────────────────────────

class TestAggregatedDictParser:

    def test_layout1_returns_records(self, tmp_path):
        """Layout 1 (measurements table) should return records."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout1(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_layout1_metric_key_populated(self, tmp_path):
        """Metric keys from measurements table should appear in records."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout1(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            keys = {r["metric_key"] for r in records}
            assert "com.apple.smsmessages.sentCount" in keys
            assert "com.apple.CoreLocation.usage" in keys
        finally:
            src.close()

    def test_layout1_value_populated(self, tmp_path):
        """Value field should contain the measurement value."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout1(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            sms_rec = next(
                r for r in records if r["metric_key"] == "com.apple.smsmessages.sentCount"
            )
            assert "42" in sms_rec["value"]
        finally:
            src.close()

    def test_layout1_unit_appended_to_value(self, tmp_path):
        """Unit column should be appended to the value string."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout1(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            sms_rec = next(
                r for r in records if r["metric_key"] == "com.apple.smsmessages.sentCount"
            )
            assert "count" in sms_rec["value"]
        finally:
            src.close()

    def test_layout1_dates_formatted(self, tmp_path):
        """start_date and end_date should be converted to ISO format strings."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout1(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            for r in records:
                assert r["start_date"] is not None
                assert "2022-06-15" in r["start_date"]
        finally:
            src.close()

    def test_layout2_returns_records(self, tmp_path):
        """Layout 2 (key_store + value_store) should return records."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout2(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_layout2_key_resolved(self, tmp_path):
        """Keys from key_store should be joined into records."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout2(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            keys = {r["metric_key"] for r in records}
            assert "com.apple.battery.level" in keys
        finally:
            src.close()

    def test_layout2_double_value_used(self, tmp_path):
        """double_value column should populate the value field when present."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout2(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            batt = next(r for r in records if r["metric_key"] == "com.apple.battery.level")
            assert "0.75" in batt["value"]
        finally:
            src.close()

    def test_layout2_string_value_used(self, tmp_path):
        """string_value column should populate value when double_value is NULL."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout2(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            net = next(r for r in records if r["metric_key"] == "com.apple.network.requests")
            assert net["value"] == "high"
        finally:
            src.close()

    def test_layout2_dates_formatted(self, tmp_path):
        """Dates in Layout 2 should also be converted to ISO strings."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout2(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            for r in records:
                assert r["start_date"] is not None
                assert "2022-06-15" in r["start_date"]
        finally:
            src.close()

    def test_db_not_found_raises_parser_error(self, tmp_path):
        """ParserError should be raised when ADDataStore.sqlitedb is absent."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser
        from forensic.parsers.base import ParserError

        # Empty backup — no AggDict DB
        conn = sqlite3.connect(str(tmp_path / "Manifest.db"))
        conn.execute(
            "CREATE TABLE Files "
            "(fileID TEXT, domain TEXT, relativePath TEXT, flags INTEGER, file BLOB)"
        )
        conn.commit()
        conn.close()
        (tmp_path / "Manifest.plist").write_bytes(plistlib.dumps({"IsEncrypted": False}))
        (tmp_path / "Info.plist").write_bytes(plistlib.dumps({"Device Name": "Test"}))

        from forensic.sources.backup import BackupSource
        src = BackupSource(str(tmp_path))
        src.open()
        try:
            with pytest.raises(ParserError):
                AggregatedDictParser(src).parse()
        finally:
            src.close()

    def test_required_fields_present_layout1(self, tmp_path):
        """All expected keys should be present in Layout 1 records."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout1(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            required = {"metric_key", "value", "start_date", "end_date"}
            for r in records:
                assert required.issubset(r.keys()), f"Missing: {required - r.keys()}"
        finally:
            src.close()

    def test_required_fields_present_layout2(self, tmp_path):
        """All expected keys should be present in Layout 2 records."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout2(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            required = {"metric_key", "value", "start_date", "end_date"}
            for r in records:
                assert required.issubset(r.keys()), f"Missing: {required - r.keys()}"
        finally:
            src.close()

    def test_end_date_populated_layout1(self, tmp_path):
        """end_date should be a valid ISO timestamp in Layout 1."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout1(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            for r in records:
                assert r["end_date"] is not None
                assert "2022-06-16" in r["end_date"]
        finally:
            src.close()

    def test_end_date_populated_layout2(self, tmp_path):
        """end_date should be a valid ISO timestamp in Layout 2."""
        from forensic.parsers.aggregated_dict import AggregatedDictParser

        src = _make_backup(
            tmp_path,
            (
                "HomeDomain",
                "Library/AggregateDictionary/ADDataStore.sqlitedb",
                _make_aggdict_db_layout2(),
            ),
        )
        try:
            records = AggregatedDictParser(src).parse()
            for r in records:
                assert r["end_date"] is not None
        finally:
            src.close()


# ── View tests ───────────────────────────────────────────────────────────────

class TestPowerLogView:
    def test_tab_name(self):
        from forensic.views.powerlog_view import PowerLogView
        assert PowerLogView.TAB_NAME == "PowerLog"

    def test_columns_defined(self):
        from forensic.views.powerlog_view import PowerLogView
        column_keys = [k for k, _ in PowerLogView.COLUMNS]
        assert "timestamp" in column_keys
        assert "bundle_id" in column_keys
        assert "foreground_time_ms" in column_keys
        assert "battery_level" in column_keys
        assert "charging_state" in column_keys
        assert "source_table" in column_keys

    def test_column_count(self):
        from forensic.views.powerlog_view import PowerLogView
        assert len(PowerLogView.COLUMNS) == 6

    def test_column_headers_are_strings(self):
        from forensic.views.powerlog_view import PowerLogView
        for key, header in PowerLogView.COLUMNS:
            assert isinstance(key, str)
            assert isinstance(header, str)
            assert len(header) > 0


class TestAggDictView:
    def test_tab_name(self):
        from forensic.views.agg_dict_view import AggregatedDictView
        assert AggregatedDictView.TAB_NAME == "Agg. Metrics"

    def test_columns_defined(self):
        from forensic.views.agg_dict_view import AggregatedDictView
        column_keys = [k for k, _ in AggregatedDictView.COLUMNS]
        assert "start_date" in column_keys
        assert "end_date" in column_keys
        assert "metric_key" in column_keys
        assert "value" in column_keys

    def test_column_count(self):
        from forensic.views.agg_dict_view import AggregatedDictView
        assert len(AggregatedDictView.COLUMNS) == 4

    def test_column_headers_are_strings(self):
        from forensic.views.agg_dict_view import AggregatedDictView
        for key, header in AggregatedDictView.COLUMNS:
            assert isinstance(key, str)
            assert isinstance(header, str)
            assert len(header) > 0
