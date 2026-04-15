"""Watchdog launcher - restarts DockedLauncher if it exits unexpectedly."""
import subprocess
import sys
import os
import time

from .logger import setup_logging, get_logger

MAX_RESTARTS = 5
RESTART_WINDOW_SEC = 60
RESTART_DELAY_SEC = 2


def watchdog_main(extra_args=None):
    """Run the app as a child process, restart on non-zero exit."""
    setup_logging()
    _log = get_logger("watchdog")

    cmd = [sys.executable, "-m", "launcher", "--no-watchdog"]
    if extra_args:
        cmd.extend(extra_args)

    restart_count = 0
    last_start = 0

    _log.info("Watchdog starting, command: %s", " ".join(cmd))

    while True:
        now = time.time()

        # Reset counter if process was stable for RESTART_WINDOW_SEC
        if now - last_start > RESTART_WINDOW_SEC:
            restart_count = 0

        last_start = now

        try:
            proc = subprocess.Popen(
                cmd,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            _log.info("Launched child PID %d", proc.pid)
            exit_code = proc.wait()
        except Exception as e:
            _log.error("Failed to launch child: %s", e)
            exit_code = 1

        if exit_code == 0:
            _log.info("Child exited cleanly (code 0), watchdog shutting down")
            break

        restart_count += 1
        _log.warning("Child exited with code %d (restart %d/%d)", exit_code, restart_count, MAX_RESTARTS)

        if restart_count >= MAX_RESTARTS:
            _log.error("Max restarts (%d) exceeded within %ds window, giving up", MAX_RESTARTS, RESTART_WINDOW_SEC)
            break

        _log.info("Restarting in %ds...", RESTART_DELAY_SEC)
        time.sleep(RESTART_DELAY_SEC)
