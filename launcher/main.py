"""Entry point for DockedLauncher with Hydra defense system."""
import argparse
import atexit
import ctypes
import signal
import sys
import os

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QTimer

from .config import load_config, save_config
from .constants import EDGES
from .startup import enable_auto_start, is_auto_start_enabled
from .logger import setup_logging, get_logger

_mutex_handle = None
_log = None


def _acquire_mutex(name_suffix=""):
    """Windows named mutex for single-instance enforcement."""
    kernel32 = ctypes.windll.kernel32
    mutex_name = "Global\\DockedLauncher_SingleInstance" + name_suffix
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
    if _log:
        _log.info("Received signal %d, shutting down", signum)
    app = QApplication.instance()
    if app:
        app.quit()


def main():
    global _mutex_handle, _log

    parser = argparse.ArgumentParser(description="DockedLauncher")
    parser.add_argument("--edge", choices=EDGES, default=None)
    parser.add_argument("--monitor", type=int, default=None)
    parser.add_argument("--no-watchdog", action="store_true",
                        help="Run directly without watchdog (internal)")
    parser.add_argument("--role", choices=["app", "watchdog", "launcher"],
                        default="launcher",
                        help="Process role in Hydra defense system")
    args = parser.parse_args()

    setup_logging()
    _log = get_logger("main")

    extra_args = []
    if args.edge:
        extra_args.extend(["--edge", args.edge])
    if args.monitor is not None:
        extra_args.extend(["--monitor", str(args.monitor)])

    # --- Role: launcher (default entry point) ---
    # Bootstraps the Hydra, then exits. This is what the user runs.
    if args.role == "launcher":
        from .hydra import launch_hydra
        _log.info("Launcher bootstrap starting Hydra")
        launch_hydra(extra_args)
        # Stay briefly so children can inherit + detach cleanly
        import time as _t
        _t.sleep(0.5)
        return

    # --- Role: watchdog ---
    if args.role == "watchdog":
        # Only one watchdog at a time
        _mutex_handle = _acquire_mutex("_Watchdog")
        if _mutex_handle is None:
            _log.info("Watchdog already running, exiting")
            return
        atexit.register(_release_mutex)

        from .hydra import watchdog_main
        try:
            watchdog_main(extra_args)
        finally:
            _release_mutex()
        return

    # --- Role: app (default when --no-watchdog is passed) ---
    _log.info("DockedLauncher app starting")

    _mutex_handle = _acquire_mutex("_App")
    if _mutex_handle is None:
        _log.info("Another app instance is already running, exiting")
        sys.exit(0)
    atexit.register(_release_mutex)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

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

    # Heartbeat timer - writes our heartbeat + checks watchdog peer
    from .hydra import app_heartbeat_loop
    heartbeat_timer = QTimer()
    heartbeat_timer.timeout.connect(app_heartbeat_loop)
    heartbeat_timer.start(500)  # every 500ms

    _log.info("DockedLauncher app running (PID %d)", os.getpid())

    exit_code = app.exec_()

    _log.info("DockedLauncher app shutting down (code %d)", exit_code)
    save_config(launcher.config)
    _release_mutex()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
