"""Unit tests for launcher.config load/save/validate.

Tests monkeypatch the module-level CONFIG_DIR/CONFIG_FILE so they operate
on a pytest tmp_path rather than on the real %APPDATA%/DockedLauncher dir.
"""
import json
import os

import pytest

from launcher import config as cfg
from launcher.constants import (
    DEFAULT_SETTINGS, EDGES, LEFT, RIGHT,
    THEME_DARK, THEME_LIGHT, MIN_OPACITY, MAX_OPACITY,
)


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect CONFIG_DIR/CONFIG_FILE to a tmp dir for the test."""
    config_dir = tmp_path / "DockedLauncher"
    config_file = config_dir / "config.json"
    monkeypatch.setattr(cfg, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(cfg, "CONFIG_FILE", str(config_file))
    return config_dir, config_file


# ---- get_config_dir ----

def test_get_config_dir_creates_missing_directory(tmp_config):
    config_dir, _ = tmp_config
    assert not config_dir.exists()
    result = cfg.get_config_dir()
    assert os.path.isdir(result)
    assert result == str(config_dir)


def test_get_config_dir_idempotent(tmp_config):
    config_dir, _ = tmp_config
    cfg.get_config_dir()
    cfg.get_config_dir()
    assert config_dir.is_dir()


# ---- load_config ----

def test_load_config_returns_defaults_when_file_missing(tmp_config):
    config = cfg.load_config()
    for key, value in DEFAULT_SETTINGS.items():
        assert config[key] == value


def test_load_config_merges_saved_over_defaults(tmp_config):
    _, config_file = tmp_config
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps({"dock_edge": RIGHT, "monitor": 2}))
    config = cfg.load_config()
    assert config["dock_edge"] == RIGHT
    assert config["monitor"] == 2
    # untouched keys still come from defaults
    assert config["theme"] == DEFAULT_SETTINGS["theme"]


def test_load_config_recovers_from_corrupt_json(tmp_config):
    config_dir, config_file = tmp_config
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text("{ this is not valid json")
    config = cfg.load_config()
    # Falls back to defaults cleanly
    assert config["dock_edge"] == DEFAULT_SETTINGS["dock_edge"]
    # Corrupt file is backed up, not deleted
    backups = list(config_dir.glob("config.json.corrupt.*"))
    assert len(backups) == 1


# ---- save_config ----

def test_save_then_load_roundtrip(tmp_config):
    data = dict(DEFAULT_SETTINGS)
    data["dock_edge"] = RIGHT
    data["monitor"] = 1
    data["edge_offset"] = 0.25
    cfg.save_config(data)
    loaded = cfg.load_config()
    assert loaded["dock_edge"] == RIGHT
    assert loaded["monitor"] == 1
    assert loaded["edge_offset"] == 0.25


def test_save_config_atomic_rename(tmp_config):
    """save_config should write via a .tmp file then rename — no .tmp leftover."""
    config_dir, config_file = tmp_config
    cfg.save_config(dict(DEFAULT_SETTINGS))
    leftovers = list(config_dir.glob("*.tmp"))
    assert leftovers == []
    assert config_file.is_file()


# ---- _validate_config: dock_edge ----

def test_validate_rejects_unknown_edge(tmp_config):
    result = cfg._validate_config({"dock_edge": "diagonal"})
    assert result["dock_edge"] == DEFAULT_SETTINGS["dock_edge"]


def test_validate_accepts_every_valid_edge(tmp_config):
    for edge in EDGES:
        result = cfg._validate_config({"dock_edge": edge})
        assert result["dock_edge"] == edge


# ---- _validate_config: monitor ----

def test_validate_coerces_negative_monitor_to_zero(tmp_config):
    assert cfg._validate_config({"monitor": -1})["monitor"] == 0


def test_validate_coerces_non_int_monitor_to_zero(tmp_config):
    assert cfg._validate_config({"monitor": "one"})["monitor"] == 0
    assert cfg._validate_config({"monitor": 1.5})["monitor"] == 0


# ---- _validate_config: opacity ----

def test_validate_clamps_opacity_above_max(tmp_config):
    assert cfg._validate_config({"opacity": 5.0})["opacity"] == MAX_OPACITY


def test_validate_clamps_opacity_below_min(tmp_config):
    assert cfg._validate_config({"opacity": 0.0})["opacity"] == MIN_OPACITY


def test_validate_opacity_rejects_non_numeric(tmp_config):
    result = cfg._validate_config({"opacity": "half"})
    assert result["opacity"] == DEFAULT_SETTINGS["opacity"]


# ---- _validate_config: edge_offset ----

def test_validate_clamps_edge_offset_range(tmp_config):
    assert cfg._validate_config({"edge_offset": -0.3})["edge_offset"] == 0.0
    assert cfg._validate_config({"edge_offset": 1.7})["edge_offset"] == 1.0


def test_validate_edge_offset_non_numeric_defaults_to_half(tmp_config):
    result = cfg._validate_config({"edge_offset": None})
    assert result["edge_offset"] == 0.5


# ---- _validate_config: theme ----

def test_validate_rejects_unknown_theme(tmp_config):
    assert cfg._validate_config({"theme": "solarized"})["theme"] == THEME_DARK


def test_validate_accepts_light_and_dark(tmp_config):
    assert cfg._validate_config({"theme": THEME_LIGHT})["theme"] == THEME_LIGHT
    assert cfg._validate_config({"theme": THEME_DARK})["theme"] == THEME_DARK


# ---- _validate_config: auto_start ----

def test_validate_auto_start_non_bool_defaults_true(tmp_config):
    assert cfg._validate_config({"auto_start": "yes"})["auto_start"] is True
    assert cfg._validate_config({"auto_start": 1})["auto_start"] is True


def test_validate_auto_start_preserves_bool(tmp_config):
    assert cfg._validate_config({"auto_start": False})["auto_start"] is False
    assert cfg._validate_config({"auto_start": True})["auto_start"] is True


# ---- _validate_config: shortcuts ----

def test_validate_shortcuts_non_list_becomes_empty(tmp_config):
    assert cfg._validate_config({"shortcuts": "notalist"})["shortcuts"] == []


def test_validate_shortcuts_filters_malformed_entries(tmp_config):
    shortcuts = [
        {"path": "C:/a.exe", "name": "A"},          # kept
        {"path": "C:/b.exe"},                        # missing name
        {"name": "C"},                               # missing path
        "nope",                                      # not a dict
        {"path": "C:/d.exe", "name": "D", "x": 1},   # kept (extra keys OK)
    ]
    result = cfg._validate_config({"shortcuts": shortcuts})
    names = [s["name"] for s in result["shortcuts"]]
    assert names == ["A", "D"]
