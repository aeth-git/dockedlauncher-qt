"""Comprehensive tests for HomeKitParser and SafariBinaryCookiesParser."""
import hashlib
import os
import plistlib
import sqlite3
import struct
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APPLE_EPOCH = 978307200
MAGIC = b"cook"


# ── Backup fixture helpers ────────────────────────────────────────────────────

def _make_backup(tmp_path, *triples):
    """Create a minimal iTunes backup directory with the given (domain, rel, content) triples."""
    from forensic.sources.backup import BackupSource

    file_map = {}
    for domain, rel, content in triples:
        fid = hashlib.sha1(f"{domain}-{rel}".encode()).hexdigest()
        (tmp_path / fid[:2]).mkdir(exist_ok=True)
        (tmp_path / fid[:2] / fid).write_bytes(content)
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

    (tmp_path / "Manifest.plist").write_bytes(plistlib.dumps({"IsEncrypted": False}))
    (tmp_path / "Info.plist").write_bytes(
        plistlib.dumps({"Device Name": "Test iPhone", "Product Version": "16.3.1"})
    )

    src = BackupSource(str(tmp_path))
    src.open()
    return src


# ── DB / binary cookie builders ───────────────────────────────────────────────

def _make_homekit_db() -> bytes:
    """Return bytes of a synthetic HomeKit SQLite DB with 2 accessories."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ZHOME (Z_PK INTEGER PRIMARY KEY, ZNAME TEXT, ZUUID TEXT);
        CREATE TABLE ZROOM (Z_PK INTEGER PRIMARY KEY, ZHOME INTEGER, ZNAME TEXT);
        CREATE TABLE ZACCESSORY (
            Z_PK INTEGER PRIMARY KEY,
            ZHOME INTEGER,
            ZROOM INTEGER,
            ZNAME TEXT,
            ZMANUFACTURER TEXT,
            ZMODEL TEXT,
            ZFIRMWAREREVISION TEXT,
            ZCATEGORY INTEGER,
            ZREACHABLE INTEGER
        );
    """)
    conn.execute("INSERT INTO ZHOME VALUES (1,'My Home','home-uuid-1')")
    conn.execute("INSERT INTO ZROOM VALUES (1,1,'Living Room')")
    conn.execute("INSERT INTO ZROOM VALUES (2,1,'Bedroom')")
    conn.execute(
        "INSERT INTO ZACCESSORY VALUES (1,1,1,'Hue Lamp','Philips','Hue White','1.2.3',5,1)"
    )
    conn.execute(
        "INSERT INTO ZACCESSORY VALUES (2,1,2,'Thermostat','Ecobee','EB-STATE6-01','4.8.7.145',9,1)"
    )
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_homekit_db_alt_name() -> bytes:
    """HomeKit DB where the accessory table is named differently (schema variant)."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ZHOME (Z_PK INTEGER PRIMARY KEY, ZNAME TEXT);
        CREATE TABLE ZROOM (Z_PK INTEGER PRIMARY KEY, ZHOME INTEGER, ZNAME TEXT);
        CREATE TABLE ZACCESSORY_V2 (
            Z_PK INTEGER PRIMARY KEY,
            ZHOME INTEGER,
            ZROOM INTEGER,
            ZNAME TEXT,
            ZMANUFACTURER TEXT,
            ZMODEL TEXT,
            ZFIRMWAREREVISION TEXT,
            ZCATEGORY INTEGER,
            ZREACHABLE INTEGER
        );
    """)
    conn.execute("INSERT INTO ZACCESSORY_V2 VALUES (1,1,1,'Lamp','Brand','M1','1.0',5,1)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_binarycookies(
    num_cookies: int = 1,
    domain: str = "example.com",
    name: str = "session",
    value: str = "abc123",
    path: str = "/",
    flags: int = 1,          # secure
    expiry_unix: float = 1_655_287_200.0,
) -> bytes:
    """Build a minimal valid Cookies.binarycookies binary with the requested cookies."""
    # Timestamps as Apple-epoch doubles
    expiry_apple = expiry_unix - APPLE_EPOCH
    created_apple = expiry_apple - 86400.0

    url_b   = domain.encode() + b"\x00"
    name_b  = name.encode()   + b"\x00"
    path_b  = path.encode()   + b"\x00"
    value_b = value.encode()  + b"\x00"

    # String offsets relative to cookie record start
    base      = 56          # fixed header size
    url_off   = base
    name_off  = url_off   + len(url_b)
    path_off  = name_off  + len(name_b)
    value_off = path_off  + len(path_b)
    cookie_size = value_off + len(value_b)

    def _make_cookie_record():
        rec  = struct.pack("<I", cookie_size)   # [0]  cookie size
        rec += struct.pack("<I", 0)              # [4]  unknown
        rec += struct.pack("<I", flags)          # [8]  flags
        rec += struct.pack("<I", 0)              # [12] unknown
        rec += struct.pack("<I", url_off)        # [16] url offset
        rec += struct.pack("<I", name_off)       # [20] name offset
        rec += struct.pack("<I", path_off)       # [24] path offset
        rec += struct.pack("<I", value_off)      # [28] value offset
        rec += b"\x00" * 8                       # [32] end marker / padding
        rec += struct.pack("<d", expiry_apple)   # [40] expiry (Apple epoch)
        rec += struct.pack("<d", created_apple)  # [48] created (Apple epoch)
        rec += url_b + name_b + path_b + value_b
        return rec

    cookie_record = _make_cookie_record()

    # Page layout:
    #   4 bytes page magic
    #   4 bytes cookie count (little-endian)
    #   (num_cookies * 4 bytes) cookie offsets (little-endian)
    #   (num_cookies * cookie record)
    page_header_size = 4 + 4 + num_cookies * 4
    first_cookie_off = page_header_size

    page  = b"\x00\x00\x01\x00"                          # page magic
    page += struct.pack("<I", num_cookies)                # cookie count
    for i in range(num_cookies):
        page += struct.pack("<I", first_cookie_off + i * len(cookie_record))
    for _ in range(num_cookies):
        page += cookie_record

    # File layout:
    #   4 bytes "cook"
    #   4 bytes page count (big-endian)
    #   (num_pages * 4 bytes) page sizes (big-endian)
    #   page data
    #   4 bytes trailing footer
    result  = MAGIC
    result += struct.pack(">I", 1)           # 1 page
    result += struct.pack(">I", len(page))   # page size
    result += page
    result += b"\x00\x00\x00\x00"           # footer
    return result


def _make_binarycookies_multi_page() -> bytes:
    """Build a binarycookies file with 2 pages and 1 cookie each."""
    def _one_page(domain_b: bytes) -> bytes:
        url_b   = domain_b + b"\x00"
        name_b  = b"tok\x00"
        path_b  = b"/\x00"
        value_b = b"val\x00"
        base      = 56
        url_off   = base
        name_off  = url_off   + len(url_b)
        path_off  = name_off  + len(name_b)
        value_off = path_off  + len(path_b)
        cookie_size = value_off + len(value_b)
        expiry_apple  = 1_655_287_200.0 - APPLE_EPOCH
        created_apple = expiry_apple - 86400.0
        rec  = struct.pack("<I", cookie_size)
        rec += struct.pack("<I", 0)
        rec += struct.pack("<I", 0)   # no flags
        rec += struct.pack("<I", 0)
        rec += struct.pack("<I", url_off)
        rec += struct.pack("<I", name_off)
        rec += struct.pack("<I", path_off)
        rec += struct.pack("<I", value_off)
        rec += b"\x00" * 8
        rec += struct.pack("<d", expiry_apple)
        rec += struct.pack("<d", created_apple)
        rec += url_b + name_b + path_b + value_b

        page  = b"\x00\x00\x01\x00"
        page += struct.pack("<I", 1)            # 1 cookie
        page += struct.pack("<I", 4 + 4 + 4)   # offset after header
        page += rec
        return page

    page1 = _one_page(b"alpha.com")
    page2 = _one_page(b"beta.com")

    result  = MAGIC
    result += struct.pack(">I", 2)
    result += struct.pack(">I", len(page1))
    result += struct.pack(">I", len(page2))
    result += page1
    result += page2
    result += b"\x00\x00\x00\x00"
    return result


# ══════════════════════════════════════════════════════════════════════════════
# HomeKitParser tests
# ══════════════════════════════════════════════════════════════════════════════

class TestHomeKitParser:
    """Tests for forensic.parsers.homekit.HomeKitParser."""

    # -- happy-path fixtures --------------------------------------------------

    @pytest.fixture
    def hk_source(self, tmp_path):
        db_bytes = _make_homekit_db()
        return _make_backup(
            tmp_path,
            ("AppDomain-com.apple.homed", "Library/HomeKit/datastore.sqlite", db_bytes),
        )

    @pytest.fixture
    def hk_store_source(self, tmp_path):
        """Use the fallback DB path (store.sqlite)."""
        db_bytes = _make_homekit_db()
        return _make_backup(
            tmp_path,
            ("AppDomain-com.apple.homed", "Library/HomeKit/store.sqlite", db_bytes),
        )

    # -- tests ----------------------------------------------------------------

    def test_returns_two_accessories(self, hk_source):
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_source).parse()
        assert len(records) == 2

    def test_required_fields_present(self, hk_source):
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_source).parse()
        required = {
            "home_name", "room_name", "accessory_name",
            "manufacturer", "model", "firmware", "category", "is_reachable",
        }
        for r in records:
            assert required.issubset(r.keys()), f"Missing fields: {required - r.keys()}"

    def test_home_name_populated(self, hk_source):
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_source).parse()
        homes = {r["home_name"] for r in records}
        assert "My Home" in homes

    def test_room_names_populated(self, hk_source):
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_source).parse()
        rooms = {r["room_name"] for r in records}
        assert "Living Room" in rooms
        assert "Bedroom" in rooms

    def test_accessory_names_correct(self, hk_source):
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_source).parse()
        names = {r["accessory_name"] for r in records}
        assert "Hue Lamp" in names
        assert "Thermostat" in names

    def test_manufacturer_populated(self, hk_source):
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_source).parse()
        lamp = next(r for r in records if r["accessory_name"] == "Hue Lamp")
        assert lamp["manufacturer"] == "Philips"

    def test_model_populated(self, hk_source):
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_source).parse()
        lamp = next(r for r in records if r["accessory_name"] == "Hue Lamp")
        assert lamp["model"] == "Hue White"

    def test_firmware_populated(self, hk_source):
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_source).parse()
        lamp = next(r for r in records if r["accessory_name"] == "Hue Lamp")
        assert lamp["firmware"] == "1.2.3"

    def test_category_populated(self, hk_source):
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_source).parse()
        lamp = next(r for r in records if r["accessory_name"] == "Hue Lamp")
        assert lamp["category"] == 5

    def test_is_reachable_bool(self, hk_source):
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_source).parse()
        for r in records:
            assert isinstance(r["is_reachable"], (bool, type(None)))
        assert all(r["is_reachable"] is True for r in records)

    def test_fallback_to_store_sqlite(self, hk_store_source):
        """Parser should succeed even when only store.sqlite is present."""
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_store_source).parse()
        assert len(records) == 2

    def test_no_db_raises_parser_error(self, tmp_path):
        from forensic.parsers.homekit import HomeKitParser
        from forensic.parsers.base import ParserError
        src = _make_backup(tmp_path)   # empty backup — no HomeKit DB
        with pytest.raises(ParserError):
            HomeKitParser(src).parse()

    def test_thermostat_details(self, hk_source):
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_source).parse()
        t = next(r for r in records if r["accessory_name"] == "Thermostat")
        assert t["manufacturer"] == "Ecobee"
        assert t["model"] == "EB-STATE6-01"
        assert t["firmware"] == "4.8.7.145"
        assert t["category"] == 9

    def test_ordering_by_home_room_name(self, hk_source):
        """Results should come back ordered by home / room / accessory name."""
        from forensic.parsers.homekit import HomeKitParser
        records = HomeKitParser(hk_source).parse()
        # Bedroom < Living Room alphabetically → Thermostat first
        assert records[0]["room_name"] == "Bedroom"
        assert records[1]["room_name"] == "Living Room"

    def test_alt_table_name_still_returns_records(self, tmp_path):
        """When the table is named differently the parser degrades gracefully."""
        from forensic.parsers.homekit import HomeKitParser
        db_bytes = _make_homekit_db_alt_name()
        src = _make_backup(
            tmp_path,
            ("AppDomain-com.apple.homed", "Library/HomeKit/datastore.sqlite", db_bytes),
        )
        records = HomeKitParser(src).parse()
        assert len(records) == 1
        assert records[0]["accessory_name"] == "Lamp"


# ══════════════════════════════════════════════════════════════════════════════
# SafariBinaryCookiesParser tests
# ══════════════════════════════════════════════════════════════════════════════

class TestSafariCookiesParser:
    """Tests for forensic.parsers.safari_cookies.SafariBinaryCookiesParser."""

    # -- happy-path fixtures --------------------------------------------------

    @pytest.fixture
    def cookies_source(self, tmp_path):
        cookie_bytes = _make_binarycookies()
        return _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Cookies/Cookies.binarycookies", cookie_bytes),
        )

    @pytest.fixture
    def two_page_source(self, tmp_path):
        cookie_bytes = _make_binarycookies_multi_page()
        return _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Cookies/Cookies.binarycookies", cookie_bytes),
        )

    # -- tests ----------------------------------------------------------------

    def test_returns_one_cookie(self, cookies_source):
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(cookies_source).parse()
        assert len(records) == 1

    def test_required_fields_present(self, cookies_source):
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(cookies_source).parse()
        required = {
            "url", "name", "path", "value", "domain",
            "expires", "created", "is_secure", "is_http_only", "flags",
        }
        for r in records:
            assert required.issubset(r.keys()), f"Missing fields: {required - r.keys()}"

    def test_domain_populated(self, cookies_source):
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(cookies_source).parse()
        assert records[0]["domain"] == "example.com"

    def test_name_populated(self, cookies_source):
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(cookies_source).parse()
        assert records[0]["name"] == "session"

    def test_value_populated(self, cookies_source):
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(cookies_source).parse()
        assert records[0]["value"] == "abc123"

    def test_path_populated(self, cookies_source):
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(cookies_source).parse()
        assert records[0]["path"] == "/"

    def test_is_secure_flag_set(self, cookies_source):
        """Default fixture uses flags=1 (secure)."""
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(cookies_source).parse()
        assert records[0]["is_secure"] is True

    def test_is_http_only_flag_not_set(self, cookies_source):
        """Default fixture uses flags=1, bit-2 (HttpOnly) is not set."""
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(cookies_source).parse()
        assert records[0]["is_http_only"] is False

    def test_http_only_flag(self, tmp_path):
        """flags=4 → HttpOnly set, Secure not set."""
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Cookies/Cookies.binarycookies",
             _make_binarycookies(flags=4)),
        )
        records = SafariBinaryCookiesParser(src).parse()
        assert records[0]["is_http_only"] is True
        assert records[0]["is_secure"] is False

    def test_expires_timestamp_present(self, cookies_source):
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(cookies_source).parse()
        assert records[0]["expires"] is not None
        # Should be a formatted date string
        assert len(records[0]["expires"]) == 19
        assert records[0]["expires"][4] == "-"

    def test_created_timestamp_present(self, cookies_source):
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(cookies_source).parse()
        assert records[0]["created"] is not None
        assert len(records[0]["created"]) == 19

    def test_expires_is_year_2022(self, cookies_source):
        """Expiry unix=1655287200 → 2022-06-15."""
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(cookies_source).parse()
        assert records[0]["expires"].startswith("2022-06-15")

    def test_multi_page_returns_two_cookies(self, two_page_source):
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(two_page_source).parse()
        assert len(records) == 2

    def test_multi_page_domains_distinct(self, two_page_source):
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(two_page_source).parse()
        domains = {r["domain"] for r in records}
        assert "alpha.com" in domains
        assert "beta.com" in domains

    def test_sorted_by_domain(self, two_page_source):
        """Results should be sorted by domain."""
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        records = SafariBinaryCookiesParser(two_page_source).parse()
        domains = [r["domain"] for r in records]
        assert domains == sorted(domains)

    def test_missing_file_raises_parser_error(self, tmp_path):
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        from forensic.parsers.base import ParserError
        src = _make_backup(tmp_path)   # empty backup
        with pytest.raises(ParserError, match="Cookies.binarycookies"):
            SafariBinaryCookiesParser(src).parse()

    def test_bad_magic_returns_empty(self, tmp_path):
        """A file with wrong magic bytes should be treated as empty/corrupt."""
        from forensic.parsers.safari_cookies import _parse_binarycookies
        data = b"JUNK" + b"\x00" * 100
        result = _parse_binarycookies(data)
        assert result == []

    def test_truncated_data_returns_empty(self, tmp_path):
        """Truncated file (< 8 bytes) should return empty list, not crash."""
        from forensic.parsers.safari_cookies import _parse_binarycookies
        assert _parse_binarycookies(b"cook") == []

    def test_value_capped_at_200_chars(self, tmp_path):
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        long_value = "x" * 500
        cookie_bytes = _make_binarycookies(value=long_value)
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Cookies/Cookies.binarycookies", cookie_bytes),
        )
        records = SafariBinaryCookiesParser(src).parse()
        assert len(records[0]["value"]) <= 200

    def test_domain_strips_leading_dot(self, tmp_path):
        """Domain field should strip a leading dot from the URL field."""
        from forensic.parsers.safari_cookies import SafariBinaryCookiesParser
        cookie_bytes = _make_binarycookies(domain=".example.com")
        src = _make_backup(
            tmp_path,
            ("HomeDomain", "Library/Cookies/Cookies.binarycookies", cookie_bytes),
        )
        records = SafariBinaryCookiesParser(src).parse()
        assert not records[0]["domain"].startswith(".")


# ══════════════════════════════════════════════════════════════════════════════
# View smoke tests (no Qt display required)
# ══════════════════════════════════════════════════════════════════════════════

class TestHomeKitView:
    @pytest.fixture(autouse=True)
    def setup(self):
        from PyQt5.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication(sys.argv)

    def test_tab_name(self):
        from forensic.views.homekit_view import HomeKitView
        assert HomeKitView.TAB_NAME == "HomeKit"

    def test_columns_defined(self):
        from forensic.views.homekit_view import HomeKitView
        keys = [k for k, _ in HomeKitView.COLUMNS]
        assert "home_name" in keys
        assert "accessory_name" in keys
        assert "manufacturer" in keys

    def test_load_records(self):
        from forensic.views.homekit_view import HomeKitView
        view = HomeKitView()
        view.load_records([
            {
                "home_name": "Home", "room_name": "Room",
                "accessory_name": "Lamp", "manufacturer": "Philips",
                "model": "Hue", "category": 5, "is_reachable": True, "firmware": "1.0",
            }
        ])
        assert view._count_label.text() == "1 record"

    def test_column_count(self):
        from forensic.views.homekit_view import HomeKitView
        assert len(HomeKitView.COLUMNS) == 8


class TestSafariCookiesView:
    @pytest.fixture(autouse=True)
    def setup(self):
        from PyQt5.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication(sys.argv)

    def test_tab_name(self):
        from forensic.views.safari_cookies_view import SafariBinaryCookiesView
        assert SafariBinaryCookiesView.TAB_NAME == "Cookies"

    def test_columns_defined(self):
        from forensic.views.safari_cookies_view import SafariBinaryCookiesView
        keys = [k for k, _ in SafariBinaryCookiesView.COLUMNS]
        assert "domain" in keys
        assert "name" in keys
        assert "is_secure" in keys

    def test_load_records(self):
        from forensic.views.safari_cookies_view import SafariBinaryCookiesView
        view = SafariBinaryCookiesView()
        view.load_records([
            {
                "domain": "example.com", "name": "sess", "value": "abc",
                "path": "/", "expires": "2022-06-15 10:00:00",
                "created": "2022-06-14 10:00:00", "is_secure": True, "is_http_only": False,
            }
        ])
        assert view._count_label.text() == "1 record"

    def test_column_count(self):
        from forensic.views.safari_cookies_view import SafariBinaryCookiesView
        assert len(SafariBinaryCookiesView.COLUMNS) == 8
