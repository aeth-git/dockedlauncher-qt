"""Tests for ileapp_runner — iLEAPP integration helpers."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))


class TestFindReportHtml:
    def test_returns_none_when_empty(self, tmp_path):
        from forensic.ileapp_runner import find_report_html
        assert find_report_html(tmp_path) is None

    def test_returns_newest_index(self, tmp_path):
        from forensic.ileapp_runner import find_report_html
        import os, time

        old = tmp_path / "iLEAPP_Reports_1" / "index.html"
        new = tmp_path / "iLEAPP_Reports_2" / "index.html"
        old.parent.mkdir(parents=True)
        new.parent.mkdir(parents=True)
        old.write_text("old")
        time.sleep(0.05)
        new.write_text("new")
        # Force newer mtime in case test runs too fast on some filesystems
        os.utime(new, (time.time() + 1, time.time() + 1))

        found = find_report_html(tmp_path)
        assert found == new


class TestBuildArgv:
    def test_raises_when_ileapp_missing(self, tmp_path, monkeypatch):
        import forensic.ileapp_runner as r
        monkeypatch.setattr(r, "find_ileapp_cmd", lambda: None)
        with pytest.raises(FileNotFoundError):
            r.build_argv(tmp_path, tmp_path / "out")

    def test_builds_expected_args(self, tmp_path, monkeypatch):
        import forensic.ileapp_runner as r
        monkeypatch.setattr(r, "find_ileapp_cmd", lambda: ["ileapp"])
        argv = r.build_argv(tmp_path / "in", tmp_path / "out")
        assert argv[0] == "ileapp"
        assert "-t" in argv and "fs" in argv
        assert "-i" in argv and str(tmp_path / "in") in argv
        assert "-o" in argv and str(tmp_path / "out") in argv


class TestFindIleappCmd:
    def test_env_var_file(self, tmp_path, monkeypatch):
        import forensic.ileapp_runner as r
        # Force the higher-priority lookups to fail
        monkeypatch.setattr(r.shutil, "which", lambda _: None)
        monkeypatch.setattr(
            r.subprocess, "run",
            lambda *a, **k: (_ for _ in ()).throw(OSError("no module")),
        )
        fake = tmp_path / "ileapp.py"
        fake.write_text("# stub")
        monkeypatch.setenv("ILEAPP_PATH", str(fake))
        cmd = r.find_ileapp_cmd()
        assert cmd is not None
        assert cmd[-1] == str(fake)

    def test_env_var_directory(self, tmp_path, monkeypatch):
        import forensic.ileapp_runner as r
        monkeypatch.setattr(r.shutil, "which", lambda _: None)
        monkeypatch.setattr(
            r.subprocess, "run",
            lambda *a, **k: (_ for _ in ()).throw(OSError("no module")),
        )
        (tmp_path / "ileapp.py").write_text("# stub")
        monkeypatch.setenv("ILEAPP_PATH", str(tmp_path))
        cmd = r.find_ileapp_cmd()
        assert cmd is not None
        assert cmd[-1].endswith("ileapp.py")

    def test_returns_none_when_nothing_found(self, monkeypatch):
        import forensic.ileapp_runner as r
        monkeypatch.setattr(r.shutil, "which", lambda _: None)
        monkeypatch.setattr(
            r.subprocess, "run",
            lambda *a, **k: (_ for _ in ()).throw(OSError("no module")),
        )
        monkeypatch.delenv("ILEAPP_PATH", raising=False)
        assert r.find_ileapp_cmd() is None
