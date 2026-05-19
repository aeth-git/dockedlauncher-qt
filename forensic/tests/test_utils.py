"""Tests for parser utility functions."""
import pytest
from forensic.parsers.utils import apple_ts, unix_ts, keyed_archive_str

APPLE_EPOCH = 978307200


class TestAppleTs:
    def test_nanoseconds_ios13(self):
        # 2022-06-15 10:00:00 UTC = unix 1655287200
        # Apple NS = (1655287200 - 978307200) * 1e9
        apple_ns = (1655287200 - APPLE_EPOCH) * 1_000_000_000
        result = apple_ts(apple_ns)
        assert result == "2022-06-15 10:00:00"

    def test_seconds_ios12(self):
        # Same date but stored as seconds (iOS ≤12 style)
        apple_s = 1655287200 - APPLE_EPOCH
        result = apple_ts(apple_s)
        assert result == "2022-06-15 10:00:00"

    def test_none_returns_none(self):
        assert apple_ts(None) is None

    def test_threshold_boundary(self):
        # Value exactly at 1e10 treated as seconds (not ns), result must be non-None
        result = apple_ts(1e10)
        assert result is not None

    def test_core_data_seconds_not_divided(self):
        # ZCALLRECORD.ZDATE: seconds since Apple epoch (e.g. 677361600 ≈ 2022-06-15)
        apple_s = float(1655287200 - APPLE_EPOCH)
        result = apple_ts(apple_s)
        assert "2022-06-15" in result

    def test_zero_is_apple_epoch(self):
        result = apple_ts(0)
        assert result == "2001-01-01 00:00:00"

    def test_invalid_returns_none(self):
        assert apple_ts("not-a-number") is None


class TestUnixTs:
    def test_seconds(self):
        result = unix_ts(1655287200)
        assert result == "2022-06-15 10:00:00"

    def test_milliseconds(self):
        result = unix_ts(1655287200_000)
        assert result == "2022-06-15 10:00:00"

    def test_none_returns_none(self):
        assert unix_ts(None) is None

    def test_telegram_epoch_seconds(self):
        # Telegram stores plain Unix epoch seconds
        result = unix_ts(1655287200)
        assert "2022-06-15" in result

    def test_signal_epoch_milliseconds(self):
        result = unix_ts(1655287200000)
        assert "2022-06-15" in result


class TestCaseLogInjection:
    def test_hash_mismatch_newline_does_not_inject(self, tmp_path, monkeypatch):
        import forensic.case_log as cl_mod
        from forensic.case_log import CaseLog

        monkeypatch.setattr(cl_mod, "LOG_DIR", str(tmp_path))
        log = CaseLog()
        # Embed a \n to attempt a forged standalone log entry
        log.log_hash_mismatch(
            "path/to/backup\nFAKE LOG ENTRY | forged=true",
            "aaaa",
            "bbbb"
        )
        log_files = list(tmp_path.glob("case_*.log"))
        assert len(log_files) == 1
        lines = log_files[0].read_text(encoding="utf-8").splitlines()
        # Exactly one HASH MISMATCH entry — the injected \n was collapsed to a space
        assert sum(1 for l in lines if "HASH MISMATCH" in l) == 1
        # "FAKE LOG ENTRY" must not appear on a standalone line (only on the HASH MISMATCH line)
        standalone = [l for l in lines if "FAKE LOG ENTRY" in l and "HASH MISMATCH" not in l]
        assert standalone == []

    def test_sanitize_strips_control_chars(self, tmp_path, monkeypatch):
        import forensic.case_log as cl_mod
        from forensic.case_log import CaseLog

        monkeypatch.setattr(cl_mod, "LOG_DIR", str(tmp_path))
        log = CaseLog()
        # \x00 and \x1b (ESC) are stripped; only \n/\r survive as spaces
        log.log_source_opened("path\x00with\x1bnulls")
        log_files = list(tmp_path.glob("case_*.log"))
        content = log_files[0].read_text(encoding="utf-8")
        assert "\x00" not in content
        assert "\x1b" not in content


class TestKeyedArchiveStr:
    def test_empty_bytes_returns_empty(self):
        assert keyed_archive_str(b"") == ""

    def test_none_equivalent(self):
        assert keyed_archive_str(b"") == ""

    def test_invalid_plist_returns_empty(self):
        assert keyed_archive_str(b"not a plist") == ""

    def test_extracts_ns_string(self):
        import plistlib
        archive = {
            "$version": 100000,
            "$archiver": "NSKeyedArchiver",
            "$top": {"root": plistlib.UID(1)},
            "$objects": [
                "$null",
                {"NS.string": "Hello world", "$class": plistlib.UID(2)},
                {"$classname": "NSAttributedString", "$classes": ["NSAttributedString"]},
            ],
        }
        blob = plistlib.dumps(archive, fmt=plistlib.FMT_BINARY)
        result = keyed_archive_str(blob)
        assert result == "Hello world"
