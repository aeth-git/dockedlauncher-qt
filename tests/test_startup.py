"""Unit tests for launcher.startup (Windows Startup folder integration).

All tests operate on a pytest tmp_path by monkeypatching get_startup_folder,
so no real Startup folder is ever touched.
"""
import os

import pytest

from launcher import startup
from launcher.constants import APP_NAME


@pytest.fixture
def fake_startup(tmp_path, monkeypatch):
    monkeypatch.setattr(startup, "get_startup_folder", lambda: str(tmp_path))
    return tmp_path


# ---- get_startup_folder ----

def test_get_startup_folder_uses_appdata(monkeypatch):
    monkeypatch.setenv("APPDATA", r"C:\Users\Test\AppData\Roaming")
    folder = startup.get_startup_folder()
    assert folder.endswith(os.path.join(
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    ))
    assert folder.startswith(r"C:\Users\Test\AppData\Roaming")


# ---- enable_auto_start ----

def test_enable_creates_bat_file(fake_startup):
    assert startup.enable_auto_start() is True
    bat = fake_startup / (APP_NAME + ".bat")
    assert bat.is_file()


def test_enabled_bat_invokes_launcher_module(fake_startup):
    startup.enable_auto_start()
    bat = fake_startup / (APP_NAME + ".bat")
    contents = bat.read_text(encoding="utf-8")
    assert "-m launcher" in contents
    assert "@echo off" in contents
    # Should cd into the project's root dir, not stay in %CD%
    assert "cd /d" in contents


def test_enable_overwrites_existing_bat(fake_startup):
    bat = fake_startup / (APP_NAME + ".bat")
    bat.write_text("old content", encoding="utf-8")
    assert startup.enable_auto_start() is True
    assert "-m launcher" in bat.read_text(encoding="utf-8")


def test_enable_returns_false_if_write_fails(fake_startup, monkeypatch):
    """If the write raises IOError, enable_auto_start returns False."""
    def boom(*a, **k):
        raise IOError("disk full")
    monkeypatch.setattr("builtins.open", boom)
    assert startup.enable_auto_start() is False


# ---- disable_auto_start ----

def test_disable_removes_bat(fake_startup):
    startup.enable_auto_start()
    bat = fake_startup / (APP_NAME + ".bat")
    assert bat.is_file()
    assert startup.disable_auto_start() is True
    assert not bat.exists()


def test_disable_is_idempotent_when_no_bat(fake_startup):
    """Disabling when already disabled is a no-op success."""
    assert startup.disable_auto_start() is True


# ---- is_auto_start_enabled ----

def test_is_enabled_reflects_bat_presence(fake_startup):
    assert startup.is_auto_start_enabled() is False
    startup.enable_auto_start()
    assert startup.is_auto_start_enabled() is True
    startup.disable_auto_start()
    assert startup.is_auto_start_enabled() is False


# ---- _get_launch_command ----

def test_launch_command_prefers_pythonw_when_available(tmp_path, monkeypatch):
    """When python.exe is the current interpreter and a pythonw.exe sits beside
    it, _get_launch_command should swap to pythonw.exe (console-less)."""
    fake_python = tmp_path / "python.exe"
    fake_pythonw = tmp_path / "pythonw.exe"
    fake_python.write_text("")
    fake_pythonw.write_text("")
    monkeypatch.setattr(startup.sys, "executable", str(fake_python))
    cmd, work_dir = startup._get_launch_command()
    assert "pythonw.exe" in cmd
    assert "-m launcher" in cmd


def test_launch_command_falls_back_to_python_exe(tmp_path, monkeypatch):
    """If pythonw.exe is missing next to python.exe, keep python.exe."""
    fake_python = tmp_path / "python.exe"
    fake_python.write_text("")
    monkeypatch.setattr(startup.sys, "executable", str(fake_python))
    cmd, _ = startup._get_launch_command()
    assert "python.exe" in cmd
    assert "pythonw.exe" not in cmd
