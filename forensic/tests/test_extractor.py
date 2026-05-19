"""Tests for BackupExtractor — full filesystem extraction."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))


class TestBackupExtractor:
    def test_extracts_all_files(self, backup_source, tmp_path):
        from forensic.extractor import BackupExtractor
        result = BackupExtractor(backup_source, tmp_path / "out").extract()
        assert result.copied > 0
        assert result.errors == []

    def test_output_preserves_domain_path(self, backup_source, tmp_path):
        from forensic.extractor import BackupExtractor
        out = tmp_path / "out"
        BackupExtractor(backup_source, out).extract()
        sms = out / "HomeDomain" / "Library" / "SMS" / "sms.db"
        assert sms.exists() and sms.stat().st_size > 0

    def test_camera_roll_preserved(self, backup_source, tmp_path):
        from forensic.extractor import BackupExtractor
        out = tmp_path / "out"
        BackupExtractor(backup_source, out).extract()
        dcim = out / "CameraRollDomain" / "Media" / "DCIM"
        assert dcim.is_dir()
        assert len(list(dcim.rglob("*"))) > 0

    def test_total_equals_copied_plus_skipped(self, backup_source, tmp_path):
        from forensic.extractor import BackupExtractor
        result = BackupExtractor(backup_source, tmp_path / "out").extract()
        assert result.total == result.copied + result.skipped + len(result.errors)

    def test_domain_filter_excludes_other_domains(self, backup_source, tmp_path):
        from forensic.extractor import BackupExtractor
        out = tmp_path / "out"
        result = BackupExtractor(backup_source, out).extract(domains=["HomeDomain"])
        assert result.copied > 0
        assert not (out / "CameraRollDomain").exists()
        assert not (out / "AppDomain-net.whatsapp.WhatsApp").exists()

    def test_domain_filter_only_home_domain(self, backup_source, tmp_path):
        from forensic.extractor import BackupExtractor
        out = tmp_path / "out"
        BackupExtractor(backup_source, out).extract(domains=["HomeDomain"])
        # HomeDomain files are present
        assert (out / "HomeDomain").is_dir()

    def test_progress_callback_receives_all_ticks(self, backup_source, tmp_path):
        from forensic.extractor import BackupExtractor
        calls = []
        BackupExtractor(backup_source, tmp_path / "out").extract(
            progress_cb=lambda done, total, path: calls.append((done, total))
        )
        assert len(calls) > 0
        # last tick: done == total
        assert calls[-1][0] == calls[-1][1]

    def test_progress_done_is_monotonically_increasing(self, backup_source, tmp_path):
        from forensic.extractor import BackupExtractor
        dones = []
        BackupExtractor(backup_source, tmp_path / "out").extract(
            progress_cb=lambda done, total, path: dones.append(done)
        )
        assert dones == sorted(dones)
        assert dones[0] >= 1

    def test_cancellation_stops_early(self, backup_source, tmp_path):
        from forensic.extractor import BackupExtractor
        limit = 3
        call_count = [0]

        def cancelled():
            call_count[0] += 1
            return call_count[0] > limit

        result = BackupExtractor(backup_source, tmp_path / "out").extract(
            cancelled_cb=cancelled
        )
        assert result.copied <= limit

    def test_case_log_records_export(self, backup_source, tmp_path, monkeypatch):
        import forensic.case_log as cl_mod
        from forensic.case_log import CaseLog
        from forensic.extractor import BackupExtractor

        log_dir = tmp_path / "logs"
        monkeypatch.setattr(cl_mod, "LOG_DIR", str(log_dir))
        case_log = CaseLog()

        BackupExtractor(backup_source, tmp_path / "out", case_log=case_log).extract()

        content = log_dir.glob("case_*.log").__next__().read_text(encoding="utf-8")
        assert "EXPORT" in content
        assert str(tmp_path / "out") in content

    def test_duplicate_extraction_overwrites_cleanly(self, backup_source, tmp_path):
        from forensic.extractor import BackupExtractor
        out = tmp_path / "out"
        r1 = BackupExtractor(backup_source, out).extract()
        r2 = BackupExtractor(backup_source, out).extract()
        assert r1.copied == r2.copied

    def test_empty_domain_list_extracts_nothing(self, backup_source, tmp_path):
        from forensic.extractor import BackupExtractor
        out = tmp_path / "out"
        result = BackupExtractor(backup_source, out).extract(domains=[])
        assert result.copied == 0
        assert result.total == 0


class TestImageSourceExtraction:
    """BackupExtractor works when given an ImageSource wrapping a backup zip."""

    def test_zip_source_extraction(self, backup_root, tmp_path):
        import zipfile
        from forensic.sources.image import ImageSource
        from forensic.extractor import BackupExtractor

        zip_path = tmp_path / "backup.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for f in backup_root.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(backup_root))

        src = ImageSource(str(zip_path))
        src.open()
        try:
            out = tmp_path / "extracted"
            result = BackupExtractor(src, out).extract()
            assert result.copied > 0
            assert (out / "HomeDomain" / "Library" / "SMS" / "sms.db").exists()
        finally:
            src.close()


class TestUnsupportedSource:
    def test_unsupported_source_returns_error(self, tmp_path):
        from forensic.extractor import BackupExtractor
        from forensic.sources.base import DataSource
        from pathlib import Path
        from typing import List, Optional, Tuple

        class _DummySource(DataSource):
            source_type = "dummy"
            def open(self): pass
            def close(self): pass
            def get_file(self, d, r): return None
            def list_files(self, d, p): return []

        result = BackupExtractor(_DummySource(), tmp_path / "out").extract()
        assert result.copied == 0
        assert len(result.errors) == 1
        assert "not support" in result.errors[0]
