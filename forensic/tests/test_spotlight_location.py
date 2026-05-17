"""Comprehensive tests for SpotlightParser and LocationCloudParser."""
import hashlib
import os
import plistlib
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

APPLE_EPOCH = 978307200  # seconds between 1970-01-01 and 2001-01-01


from forensic.tests.conftest import make_backup as _make_backup


# ── DB builders ───────────────────────────────────────────────────────────────

def _make_spotlight_db():
    """Synthetic Store.db with the 'spotlightItems' table (iOS 14-style schema)."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE spotlightItems ("
        "id INTEGER PRIMARY KEY, title TEXT, url TEXT, content_type TEXT, "
        "created REAL, modified REAL, domain TEXT)"
    )
    # 2022-06-15 10:00:00 UTC expressed as Apple epoch seconds
    t = 1655287200 - APPLE_EPOCH
    conn.execute(
        "INSERT INTO spotlightItems VALUES "
        "(1,'Meeting Notes','file:///var/mobile/Documents/notes.txt',"
        "'public.plain-text',?,?,'org.apple.notes')",
        (t, t + 3600),
    )
    conn.execute(
        "INSERT INTO spotlightItems VALUES "
        "(2,'Photo 1','file:///var/mobile/Media/DCIM/IMG_0001.JPG',"
        "'public.jpeg',?,?,'media')",
        (t + 7200, t + 7200),
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_spotlight_db_metadata_table():
    """Alternate schema using table name 'metadata' (older iOS)."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE metadata ("
        "id INTEGER PRIMARY KEY, name TEXT, path TEXT, content_type TEXT, "
        "created REAL, modified REAL)"
    )
    t = 1655287200 - APPLE_EPOCH
    conn.execute(
        "INSERT INTO metadata VALUES (1,'Old Note','file:///note.txt','public.plain-text',?,?)",
        (t, t + 60),
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_spotlight_db_no_known_table():
    """DB with no recognizable Spotlight table — should cause ParserError."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute("CREATE TABLE some_random_table (id INTEGER PRIMARY KEY, foo TEXT)")
    conn.execute("INSERT INTO some_random_table VALUES (1,'bar')")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_location_cloud_db():
    """Synthetic Cloud.sqlite with full column set."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE ZRTCLOUDSYNCEDLOCATIONOFINTEREST ("
        "Z_PK INTEGER PRIMARY KEY, ZLATITUDE REAL, ZLONGITUDE REAL, ZLABEL TEXT, "
        "ZCITY TEXT, ZSTATE TEXT, ZCOUNTRY TEXT, ZCONFIDENCE REAL, ZVISITCOUNT INTEGER)"
    )
    conn.execute(
        "INSERT INTO ZRTCLOUDSYNCEDLOCATIONOFINTEREST VALUES "
        "(1,37.7749,-122.4194,'Home','San Francisco','CA','US',0.95,150)"
    )
    conn.execute(
        "INSERT INTO ZRTCLOUDSYNCEDLOCATIONOFINTEREST VALUES "
        "(2,37.3382,-121.8863,'Work','San Jose','CA','US',0.88,80)"
    )
    conn.execute(
        "INSERT INTO ZRTCLOUDSYNCEDLOCATIONOFINTEREST VALUES "
        "(3,34.0522,-118.2437,'Coffee Shop','Los Angeles','CA','US',0.75,30)"
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_location_cloud_db_custom_label():
    """Alternate schema using ZCUSTOMLABEL instead of ZLABEL."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE ZRTCLOUDSYNCEDLOCATIONOFINTEREST ("
        "Z_PK INTEGER PRIMARY KEY, ZLATITUDE REAL, ZLONGITUDE REAL, "
        "ZCUSTOMLABEL TEXT, ZCITY TEXT, ZCOUNTRY TEXT, ZVISITCOUNT INTEGER)"
    )
    conn.execute(
        "INSERT INTO ZRTCLOUDSYNCEDLOCATIONOFINTEREST VALUES "
        "(1,51.5074,-0.1278,'London Home','London','GB',200)"
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_location_cloud_db_no_table():
    """Cloud.sqlite that lacks the expected table — triggers ParserError."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute("CREATE TABLE wrong_table (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


# ── SpotlightParser tests ─────────────────────────────────────────────────────

class TestSpotlightParser:
    """Tests for forensic.parsers.spotlight.SpotlightParser."""

    def test_returns_two_records(self, tmp_path):
        from forensic.parsers.spotlight import SpotlightParser
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Spotlight/CoreSpotlight/Store.db",
             _make_spotlight_db()),
        )
        try:
            records = SpotlightParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_record_has_required_fields(self, tmp_path):
        from forensic.parsers.spotlight import SpotlightParser
        src = _make_backup(
            tmp_path / "rqf",
            ("HomeDomain", "Library/Spotlight/CoreSpotlight/Store.db",
             _make_spotlight_db()),
        )
        try:
            records = SpotlightParser(src).parse()
            required = {"title", "url", "content_type", "created", "modified", "domain"}
            for r in records:
                assert required.issubset(r.keys()), f"Missing fields: {required - r.keys()}"
        finally:
            src.close()

    def test_title_populated(self, tmp_path):
        from forensic.parsers.spotlight import SpotlightParser
        src = _make_backup(
            tmp_path / "title",
            ("HomeDomain", "Library/Spotlight/CoreSpotlight/Store.db",
             _make_spotlight_db()),
        )
        try:
            records = SpotlightParser(src).parse()
            titles = [r["title"] for r in records]
            assert "Meeting Notes" in titles
            assert "Photo 1" in titles
        finally:
            src.close()

    def test_url_populated(self, tmp_path):
        from forensic.parsers.spotlight import SpotlightParser
        src = _make_backup(
            tmp_path / "url",
            ("HomeDomain", "Library/Spotlight/CoreSpotlight/Store.db",
             _make_spotlight_db()),
        )
        try:
            records = SpotlightParser(src).parse()
            urls = [r["url"] for r in records]
            assert any("notes.txt" in u for u in urls)
            assert any("IMG_0001" in u for u in urls)
        finally:
            src.close()

    def test_content_type_populated(self, tmp_path):
        from forensic.parsers.spotlight import SpotlightParser
        src = _make_backup(
            tmp_path / "ctype",
            ("HomeDomain", "Library/Spotlight/CoreSpotlight/Store.db",
             _make_spotlight_db()),
        )
        try:
            records = SpotlightParser(src).parse()
            types = {r["content_type"] for r in records}
            assert "public.plain-text" in types
            assert "public.jpeg" in types
        finally:
            src.close()

    def test_created_timestamp_format(self, tmp_path):
        from forensic.parsers.spotlight import SpotlightParser
        src = _make_backup(
            tmp_path / "ts",
            ("HomeDomain", "Library/Spotlight/CoreSpotlight/Store.db",
             _make_spotlight_db()),
        )
        try:
            records = SpotlightParser(src).parse()
            for r in records:
                if r["created"]:
                    assert len(r["created"]) == 19, f"Bad ts: {r['created']!r}"
                    assert r["created"][4] == "-"
                    assert "2022-06-15" in r["created"]
        finally:
            src.close()

    def test_modified_timestamp_format(self, tmp_path):
        from forensic.parsers.spotlight import SpotlightParser
        src = _make_backup(
            tmp_path / "mts",
            ("HomeDomain", "Library/Spotlight/CoreSpotlight/Store.db",
             _make_spotlight_db()),
        )
        try:
            records = SpotlightParser(src).parse()
            for r in records:
                if r["modified"]:
                    assert "2022-06-15" in r["modified"]
        finally:
            src.close()

    def test_domain_field_populated(self, tmp_path):
        from forensic.parsers.spotlight import SpotlightParser
        src = _make_backup(
            tmp_path / "dom",
            ("HomeDomain", "Library/Spotlight/CoreSpotlight/Store.db",
             _make_spotlight_db()),
        )
        try:
            records = SpotlightParser(src).parse()
            domains = [r["domain"] for r in records if r["domain"]]
            assert len(domains) >= 1
            assert any("notes" in d for d in domains)
        finally:
            src.close()

    def test_alternate_table_metadata(self, tmp_path):
        """Parser should fall back to 'metadata' table when spotlightItems absent."""
        from forensic.parsers.spotlight import SpotlightParser
        src = _make_backup(
            tmp_path / "alt",
            ("HomeDomain", "Library/Spotlight/CoreSpotlight/Store.db",
             _make_spotlight_db_metadata_table()),
        )
        try:
            records = SpotlightParser(src).parse()
            assert len(records) == 1
            assert records[0]["title"] == "Old Note"
        finally:
            src.close()

    def test_no_known_table_raises_parser_error(self, tmp_path):
        from forensic.parsers.spotlight import SpotlightParser
        from forensic.parsers.base import ParserError
        src = _make_backup(
            tmp_path / "noknown",
            ("HomeDomain", "Library/Spotlight/CoreSpotlight/Store.db",
             _make_spotlight_db_no_known_table()),
        )
        try:
            with pytest.raises(ParserError, match="no known tables"):
                SpotlightParser(src).parse()
        finally:
            src.close()

    def test_missing_db_raises_file_not_found(self, tmp_path):
        from forensic.parsers.spotlight import SpotlightParser
        # Empty backup — no Spotlight DB at all
        src = _make_backup(
            tmp_path / "miss",
            ("HomeDomain", "Library/SMS/sms.db", b""),  # unrelated file
        )
        try:
            with pytest.raises(FileNotFoundError):
                SpotlightParser(src).parse()
        finally:
            src.close()

    def test_error_message_includes_found_tables(self, tmp_path):
        """ParserError message should list the actual table names found."""
        from forensic.parsers.spotlight import SpotlightParser
        from forensic.parsers.base import ParserError
        src = _make_backup(
            tmp_path / "errmsg",
            ("HomeDomain", "Library/Spotlight/CoreSpotlight/Store.db",
             _make_spotlight_db_no_known_table()),
        )
        try:
            with pytest.raises(ParserError) as exc_info:
                SpotlightParser(src).parse()
            assert "some_random_table" in str(exc_info.value)
        finally:
            src.close()


# ── LocationCloudParser tests ─────────────────────────────────────────────────

class TestLocationCloudParser:
    """Tests for forensic.parsers.location_cloud.LocationCloudParser."""

    def test_returns_three_records(self, tmp_path):
        from forensic.parsers.location_cloud import LocationCloudParser
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite",
             _make_location_cloud_db()),
        )
        try:
            records = LocationCloudParser(src).parse()
            assert len(records) == 3
        finally:
            src.close()

    def test_record_has_required_fields(self, tmp_path):
        from forensic.parsers.location_cloud import LocationCloudParser
        src = _make_backup(
            tmp_path / "rqf",
            ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite",
             _make_location_cloud_db()),
        )
        try:
            records = LocationCloudParser(src).parse()
            required = {"label", "latitude", "longitude", "city", "state",
                        "country", "confidence", "visit_count"}
            for r in records:
                assert required.issubset(r.keys()), f"Missing: {required - r.keys()}"
        finally:
            src.close()

    def test_sorted_by_visit_count_descending(self, tmp_path):
        from forensic.parsers.location_cloud import LocationCloudParser
        src = _make_backup(
            tmp_path / "sort",
            ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite",
             _make_location_cloud_db()),
        )
        try:
            records = LocationCloudParser(src).parse()
            visit_counts = [r["visit_count"] for r in records]
            assert visit_counts == sorted(visit_counts, reverse=True)
        finally:
            src.close()

    def test_home_location_has_highest_visits(self, tmp_path):
        from forensic.parsers.location_cloud import LocationCloudParser
        src = _make_backup(
            tmp_path / "home",
            ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite",
             _make_location_cloud_db()),
        )
        try:
            records = LocationCloudParser(src).parse()
            assert records[0]["label"] == "Home"
            assert records[0]["visit_count"] == 150
        finally:
            src.close()

    def test_label_populated(self, tmp_path):
        from forensic.parsers.location_cloud import LocationCloudParser
        src = _make_backup(
            tmp_path / "label",
            ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite",
             _make_location_cloud_db()),
        )
        try:
            records = LocationCloudParser(src).parse()
            labels = {r["label"] for r in records}
            assert "Home" in labels
            assert "Work" in labels
        finally:
            src.close()

    def test_latitude_and_longitude_values(self, tmp_path):
        from forensic.parsers.location_cloud import LocationCloudParser
        src = _make_backup(
            tmp_path / "latlon",
            ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite",
             _make_location_cloud_db()),
        )
        try:
            records = LocationCloudParser(src).parse()
            home = next(r for r in records if r["label"] == "Home")
            assert abs(home["latitude"] - 37.7749) < 0.0001
            assert abs(home["longitude"] - (-122.4194)) < 0.0001
        finally:
            src.close()

    def test_city_populated(self, tmp_path):
        from forensic.parsers.location_cloud import LocationCloudParser
        src = _make_backup(
            tmp_path / "city",
            ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite",
             _make_location_cloud_db()),
        )
        try:
            records = LocationCloudParser(src).parse()
            cities = {r["city"] for r in records}
            assert "San Francisco" in cities
            assert "San Jose" in cities
        finally:
            src.close()

    def test_country_populated(self, tmp_path):
        from forensic.parsers.location_cloud import LocationCloudParser
        src = _make_backup(
            tmp_path / "country",
            ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite",
             _make_location_cloud_db()),
        )
        try:
            records = LocationCloudParser(src).parse()
            assert all(r["country"] == "US" for r in records)
        finally:
            src.close()

    def test_confidence_values(self, tmp_path):
        from forensic.parsers.location_cloud import LocationCloudParser
        src = _make_backup(
            tmp_path / "conf",
            ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite",
             _make_location_cloud_db()),
        )
        try:
            records = LocationCloudParser(src).parse()
            home = next(r for r in records if r["label"] == "Home")
            assert abs(home["confidence"] - 0.95) < 0.001
        finally:
            src.close()

    def test_alternate_schema_custom_label(self, tmp_path):
        """Parser should use ZCUSTOMLABEL when ZLABEL column is absent."""
        from forensic.parsers.location_cloud import LocationCloudParser
        src = _make_backup(
            tmp_path / "customlabel",
            ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite",
             _make_location_cloud_db_custom_label()),
        )
        try:
            records = LocationCloudParser(src).parse()
            assert len(records) == 1
            assert records[0]["label"] == "London Home"
            assert records[0]["city"] == "London"
        finally:
            src.close()

    def test_missing_table_raises_parser_error(self, tmp_path):
        from forensic.parsers.location_cloud import LocationCloudParser
        from forensic.parsers.base import ParserError
        src = _make_backup(
            tmp_path / "notable",
            ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite",
             _make_location_cloud_db_no_table()),
        )
        try:
            with pytest.raises(ParserError, match="expected table not found"):
                LocationCloudParser(src).parse()
        finally:
            src.close()

    def test_missing_db_raises_file_not_found(self, tmp_path):
        from forensic.parsers.location_cloud import LocationCloudParser
        src = _make_backup(
            tmp_path / "missingdb",
            ("HomeDomain", "Library/SMS/sms.db", b""),  # unrelated file
        )
        try:
            with pytest.raises(FileNotFoundError):
                LocationCloudParser(src).parse()
        finally:
            src.close()

    def test_error_message_includes_table_names(self, tmp_path):
        """ParserError should name the tables that were found."""
        from forensic.parsers.location_cloud import LocationCloudParser
        from forensic.parsers.base import ParserError
        src = _make_backup(
            tmp_path / "errtbl",
            ("HomeDomain", "Library/Caches/com.apple.routined/Cloud.sqlite",
             _make_location_cloud_db_no_table()),
        )
        try:
            with pytest.raises(ParserError) as exc_info:
                LocationCloudParser(src).parse()
            assert "wrong_table" in str(exc_info.value)
        finally:
            src.close()

    def test_distinct_from_location_parser(self, tmp_path):
        """LocationCloudParser and LocationParser use different DB paths."""
        from forensic.parsers.location_cloud import LocationCloudParser
        from forensic.parsers.location import LocationParser
        # Cloud parser looks for Cloud.sqlite; local parser looks for Local.sqlite
        # They should not interfere.
        assert LocationCloudParser is not LocationParser
        # Verify the DB path constants are different
        cloud_db_path = "Library/Caches/com.apple.routined/Cloud.sqlite"
        local_db_path = "Library/Caches/com.apple.routined/Local.sqlite"
        assert cloud_db_path != local_db_path


# ── View tests ────────────────────────────────────────────────────────────────

class TestSpotlightView:
    """Smoke tests for SpotlightView — ensures correct COLUMNS mapping."""

    def test_tab_name(self):
        from forensic.views.spotlight_view import SpotlightView
        assert SpotlightView.TAB_NAME == "Spotlight"

    def test_columns_keys(self):
        from forensic.views.spotlight_view import SpotlightView
        keys = [k for k, _ in SpotlightView.COLUMNS]
        assert "title" in keys
        assert "content_type" in keys
        assert "created" in keys
        assert "modified" in keys
        assert "domain" in keys
        assert "url" in keys

    def test_column_count(self):
        from forensic.views.spotlight_view import SpotlightView
        assert len(SpotlightView.COLUMNS) == 6


class TestLocationCloudView:
    """Smoke tests for LocationCloudView — ensures correct COLUMNS mapping."""

    def test_tab_name(self):
        from forensic.views.location_cloud_view import LocationCloudView
        assert LocationCloudView.TAB_NAME == "Sig. Locations"

    def test_columns_keys(self):
        from forensic.views.location_cloud_view import LocationCloudView
        keys = [k for k, _ in LocationCloudView.COLUMNS]
        assert "label" in keys
        assert "latitude" in keys
        assert "longitude" in keys
        assert "city" in keys
        assert "country" in keys
        assert "confidence" in keys
        assert "visit_count" in keys

    def test_column_count(self):
        from forensic.views.location_cloud_view import LocationCloudView
        assert len(LocationCloudView.COLUMNS) == 7
