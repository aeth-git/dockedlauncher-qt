"""Configuration manager - load/save settings to %APPDATA%/DockedLauncher/."""
import json
import os
import copy

from .constants import CONFIG_DIR, CONFIG_FILE, DEFAULT_SETTINGS


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
        except (json.JSONDecodeError, IOError):
            pass
    return config


def save_config(config):
    get_config_dir()
    tmp_path = CONFIG_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        os.rename(tmp_path, CONFIG_FILE)
    except IOError:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
