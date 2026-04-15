"""Configuration manager with validation and corruption recovery."""
import json
import os
import copy
import shutil
from datetime import datetime

from .constants import (
    CONFIG_DIR, CONFIG_FILE, DEFAULT_SETTINGS, EDGES,
    THEME_DARK, THEME_LIGHT, MIN_OPACITY, MAX_OPACITY,
)
from .logger import get_logger

_log = get_logger("config")


def get_config_dir():
    if not os.path.isdir(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)
    return CONFIG_DIR


def load_config():
    get_config_dir()
    config = copy.deepcopy(DEFAULT_SETTINGS)
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            config.update(saved)
        except json.JSONDecodeError as e:
            _log.error("Corrupt config file: %s", e)
            backup = CONFIG_FILE + ".corrupt." + datetime.now().strftime("%Y%m%d%H%M%S")
            try:
                shutil.copy2(CONFIG_FILE, backup)
                _log.info("Backed up corrupt config to %s", backup)
            except IOError:
                pass
        except IOError as e:
            _log.error("Failed to read config: %s", e)
    return _validate_config(config)


def save_config(config):
    get_config_dir()
    tmp_path = CONFIG_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        os.rename(tmp_path, CONFIG_FILE)
    except IOError as e:
        _log.error("Failed to save config: %s", e)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _validate_config(config):
    """Clamp values to valid ranges, fix types, ensure schema correctness."""
    if config.get("dock_edge") not in EDGES:
        config["dock_edge"] = DEFAULT_SETTINGS["dock_edge"]

    mon = config.get("monitor", 0)
    if not isinstance(mon, int) or mon < 0:
        config["monitor"] = 0

    opacity = config.get("opacity", DEFAULT_SETTINGS["opacity"])
    if not isinstance(opacity, (int, float)):
        opacity = DEFAULT_SETTINGS["opacity"]
    config["opacity"] = max(MIN_OPACITY, min(MAX_OPACITY, float(opacity)))

    offset = config.get("edge_offset", 0.5)
    if not isinstance(offset, (int, float)):
        offset = 0.5
    config["edge_offset"] = max(0.0, min(1.0, float(offset)))

    if config.get("theme") not in (THEME_DARK, THEME_LIGHT):
        config["theme"] = THEME_DARK

    if not isinstance(config.get("auto_start"), bool):
        config["auto_start"] = True

    shortcuts = config.get("shortcuts", [])
    if not isinstance(shortcuts, list):
        shortcuts = []
    config["shortcuts"] = [
        sc for sc in shortcuts
        if isinstance(sc, dict) and "path" in sc and "name" in sc
    ]

    return config
