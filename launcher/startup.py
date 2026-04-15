"""Windows Startup folder integration - no registry edits."""
import os
import sys

from .constants import APP_NAME
from .logger import get_logger

_log = get_logger("startup")


def get_startup_folder():
    return os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )


def _bat_path():
    return os.path.join(get_startup_folder(), APP_NAME + ".bat")


def _get_launch_command():
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python = sys.executable
    if python.endswith("python.exe"):
        pythonw = python.replace("python.exe", "pythonw.exe")
        if os.path.isfile(pythonw):
            python = pythonw
    return '"{}" -m launcher'.format(python), script_dir


def enable_auto_start():
    cmd, work_dir = _get_launch_command()
    bat = _bat_path()
    try:
        with open(bat, "w", encoding="utf-8") as f:
            f.write("@echo off\r\n")
            f.write('cd /d "{}"\r\n'.format(work_dir))
            f.write("start /b {} \r\n".format(cmd))
        _log.info("Auto-start enabled: %s", bat)
        return True
    except IOError as e:
        _log.error("Failed to enable auto-start: %s", e)
        return False


def disable_auto_start():
    bat = _bat_path()
    if os.path.isfile(bat):
        try:
            os.remove(bat)
            return True
        except IOError:
            return False
    return True


def is_auto_start_enabled():
    return os.path.isfile(_bat_path())
