"""DockedLauncher entry point - single process, zero tricks, guaranteed to work.

No subprocess spawning, no executable cloning, no detached processes,
no Windows composition API, no anti-EDR games. Just a plain Qt app.
"""
import argparse
import atexit
import ctypes
import signal
import sys
import os

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from .config import load_config, save_config
from .constants import EDGES, LEFT
from .startup import enable_auto_start, is_auto_start_enabled
from .logger import setup_logging, get_logger

_mutex_handle = None
_log = None


def _acquire_mutex():
    """Prevent duplicate instances."""
    k = ctypes.windll.kernel32
    h = k.CreateMutexW(None, False, "Global\\DockedLauncher_SingleInstance")
    if k.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        k.CloseHandle(h)
        return None
    return h


def _release_mutex():
    global _mutex_handle
    if _mutex_handle:
        ctypes.windll.kernel32.CloseHandle(_mutex_handle)
        _mutex_handle = None


def _on_signal(signum, frame):
    if _log:
        _log.info("Signal %d received - quitting", signum)
    app = QApplication.instance()
    if app:
        app.quit()


def _sanitize_config_for_screens(config, screens):
    """Ensure saved monitor/edge_offset won't place the tab off-screen.

    If the saved monitor index doesn't exist, reset to 0. If edge_offset is
    outside [0, 1], clamp it. This is the last-line-of-defense against the
    user cloning the repo and having stale config from another machine.
    """
    mon = config.get("monitor", 0)
    if not isinstance(mon, int) or mon < 0 or mon >= len(screens):
        config["monitor"] = 0
    off = config.get("edge_offset", 0.5)
    try:
        off = float(off)
    except (TypeError, ValueError):
        off = 0.5
    config["edge_offset"] = max(0.0, min(1.0, off))
    if config.get("dock_edge") not in EDGES:
        config["dock_edge"] = LEFT
    return config


def main():
    global _mutex_handle, _log

    parser = argparse.ArgumentParser(description="DockedLauncher")
    parser.add_argument("--edge", choices=EDGES, default=None)
    parser.add_argument("--monitor", type=int, default=None)
    parser.add_argument("--reset", action="store_true",
                        help="Reset saved position to defaults (recovery mode)")
    args = parser.parse_args()

    setup_logging()
    _log = get_logger("main")
    _log.info("DockedLauncher starting (PID %d)", os.getpid())

    # Single-instance enforcement
    _mutex_handle = _acquire_mutex()
    if _mutex_handle is None:
        _log.info("Another instance is already running, exiting")
        return 0
    atexit.register(_release_mutex)

    # Ctrl+C / taskkill graceful exit
    signal.signal(signal.SIGTERM, _on_signal)
    try:
        signal.signal(signal.SIGINT, _on_signal)
    except ValueError:
        pass  # already handled

    # High-DPI - must be set BEFORE QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # --- Config with sanity check against actual screens ---
    config = load_config()
    if args.reset:
        config["dock_edge"] = LEFT
        config["edge_offset"] = 0.5
        config["monitor"] = 0
        _log.info("Reset mode: using default position")
    if args.edge:
        config["dock_edge"] = args.edge
    if args.monitor is not None:
        config["monitor"] = args.monitor

    screens = app.screens()
    config = _sanitize_config_for_screens(config, screens)

    if config.get("auto_start", True) and not is_auto_start_enabled():
        enable_auto_start()

    save_config(config)

    # --- Build and show the window ---
    try:
        from .main_window import DockedLauncher
        launcher = DockedLauncher(config=config)
        launcher.show()
    except Exception:
        _log.exception("Failed to construct main window")
        _release_mutex()
        return 1

    _log.info("DockedLauncher running on %d screen(s)", len(screens))
    exit_code = app.exec_()
    _log.info("DockedLauncher exiting (code %d)", exit_code)

    try:
        save_config(launcher.config)
    except Exception:
        _log.exception("Failed to save config on exit")

    _release_mutex()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
