"""Entry point for DockedLauncher (PyQt5) with watchdog, mutex, and signal handling."""
import argparse
import atexit
import ctypes
import signal
import sys
import os

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from .config import load_config, save_config
from .constants import EDGES
from .startup import enable_auto_start, is_auto_start_enabled
from .logger import setup_logging, get_logger

_mutex_handle = None
_log = None


def _acquire_mutex():
    """Create a named mutex for single-instance enforcement. Returns handle or None."""
    kernel32 = ctypes.windll.kernel32
    mutex_name = "Global\\DockedLauncher_SingleInstance"
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return None
    return handle


def _release_mutex():
    global _mutex_handle
    if _mutex_handle:
        ctypes.windll.kernel32.CloseHandle(_mutex_handle)
        _mutex_handle = None


def _on_signal(signum, frame):
    """Handle SIGTERM/SIGINT gracefully."""
    if _log:
        _log.info("Received signal %d, shutting down", signum)
    app = QApplication.instance()
    if app:
        app.quit()


def main():
    global _mutex_handle, _log

    # Parse args first to check for --no-watchdog
    parser = argparse.ArgumentParser(description="DockedLauncher")
    parser.add_argument("--edge", choices=EDGES, default=None)
    parser.add_argument("--monitor", type=int, default=None)
    parser.add_argument("--no-watchdog", action="store_true",
                        help="Run directly without watchdog (used internally)")
    args = parser.parse_args()

    # If not --no-watchdog, launch via watchdog instead
    if not args.no_watchdog:
        from .watchdog import watchdog_main
        extra = []
        if args.edge:
            extra.extend(["--edge", args.edge])
        if args.monitor is not None:
            extra.extend(["--monitor", str(args.monitor)])
        watchdog_main(extra)
        return

    # ---- Direct app launch (called by watchdog with --no-watchdog) ----

    setup_logging()
    _log = get_logger("main")
    _log.info("DockedLauncher starting")

    # Single-instance check
    _mutex_handle = _acquire_mutex()
    if _mutex_handle is None:
        _log.info("Another instance is already running, exiting")
        sys.exit(0)
    atexit.register(_release_mutex)

    # Signal handlers
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    # High-DPI scaling BEFORE QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    config = load_config()
    if args.edge:
        config["dock_edge"] = args.edge
    if args.monitor is not None:
        config["monitor"] = args.monitor

    if config.get("auto_start", True) and not is_auto_start_enabled():
        enable_auto_start()

    save_config(config)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from .main_window import DockedLauncher
    launcher = DockedLauncher(config=config)
    launcher.show()

    _log.info("DockedLauncher running (PID %d)", os.getpid())

    exit_code = app.exec_()

    _log.info("DockedLauncher shutting down (code %d)", exit_code)
    save_config(launcher.config)
    _release_mutex()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
