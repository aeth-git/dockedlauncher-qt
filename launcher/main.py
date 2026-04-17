"""Entry point for DockedLauncher.

Default mode: runs the app directly in-process (simple, works everywhere).
Opt-in Hydra mode via --hydra flag for process-kill resilience on machines
that allow it (may be blocked by corporate EDR/antivirus).
"""
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


def _run_app(args):
    """Run the Qt app in-process. The simple, reliable path."""
    global _mutex_handle, _log
    _log.info("DockedLauncher app starting (PID %d)", os.getpid())

    _mutex_handle = _acquire_mutex("_App")
    if _mutex_handle is None:
        _log.info("Another instance is already running, exiting")
        return 0
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

    _log.info("DockedLauncher app running")
    exit_code = app.exec_()
    _log.info("DockedLauncher shutting down (code %d)", exit_code)

    save_config(launcher.config)
    _release_mutex()
    return exit_code


def main():
    global _log

    parser = argparse.ArgumentParser(description="DockedLauncher")
    parser.add_argument("--edge", choices=EDGES, default=None)
    parser.add_argument("--monitor", type=int, default=None)
    parser.add_argument("--hydra", action="store_true",
                        help="Use Hydra twin-watchdog defense (may be blocked by EDR)")
    parser.add_argument("--role", choices=["app", "watchdog", "launcher"],
                        default=None, help=argparse.SUPPRESS)  # internal
    parser.add_argument("--no-watchdog", action="store_true",
                        help=argparse.SUPPRESS)  # internal legacy
    args = parser.parse_args()

    setup_logging()
    _log = get_logger("main")

    # Simple mode (default): just run the app directly. No subprocess magic.
    # This works on any machine and won't trigger EDR/antivirus heuristics.
    if not args.hydra and not args.role:
        sys.exit(_run_app(args))
        return

    # Hydra opt-in path
    extra_args = []
    if args.edge:
        extra_args.extend(["--edge", args.edge])
    if args.monitor is not None:
        extra_args.extend(["--monitor", str(args.monitor)])

    if args.role is None:
        # User passed --hydra to bootstrap
        from .hydra import launch_hydra
        _log.info("Hydra mode: bootstrap starting twin processes")
        try:
            launch_hydra(extra_args)
            import time as _t
            _t.sleep(0.5)
        except Exception as e:
            _log.error("Hydra failed (%s); falling back to simple mode", e)
            sys.exit(_run_app(args))
        return

    if args.role == "watchdog":
        from .hydra import watchdog_main
        _mutex_handle = _acquire_mutex("_Watchdog")
        if _mutex_handle is None:
            _log.info("Watchdog already running, exiting")
            return
        atexit.register(_release_mutex)
        try:
            watchdog_main(extra_args)
        finally:
            _release_mutex()
        return

    # args.role == "app" (spawned by Hydra)
    sys.exit(_run_app(args))


if __name__ == "__main__":
    main()
