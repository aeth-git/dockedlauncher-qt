"""Watchdog - restarts DockedLauncher on crash or external kill.

Stops only when: user clicks X (quit.flag file), max rapid restarts hit,
or watchdog itself is killed. For total process-kill resilience, pair
with a Windows Task Scheduler entry (see install_task_scheduler()).
"""
import subprocess
import sys
import os
import time

from .logger import setup_logging, get_logger
from .constants import CONFIG_DIR

RAPID_RESTART_THRESHOLD = 10   # if restarting more than this in the window, give up
RAPID_RESTART_WINDOW = 30      # seconds
RESTART_DELAY_SEC = 2
QUIT_FLAG = os.path.join(CONFIG_DIR, "quit.flag")


def _user_quit():
    """True if user clicked X (quit.flag exists)."""
    return os.path.isfile(QUIT_FLAG)


def _clear_quit_flag():
    try:
        if os.path.isfile(QUIT_FLAG):
            os.remove(QUIT_FLAG)
    except OSError:
        pass


def watchdog_main(extra_args=None):
    """Run the app as a child process, restart until user explicitly quits."""
    setup_logging()
    _log = get_logger("watchdog")

    # Clear any stale quit flag from a previous session
    _clear_quit_flag()

    cmd = [sys.executable, "-m", "launcher", "--no-watchdog"]
    if extra_args:
        cmd.extend(extra_args)

    recent_restarts = []  # timestamps of recent restarts

    _log.info("Watchdog starting, command: %s", " ".join(cmd))

    while True:
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

        # User explicitly quit via X button?
        if _user_quit():
            _log.info("User quit flag present, watchdog shutting down")
            _clear_quit_flag()
            break

        # Clean exit without quit flag: still restart (process may have died
        # from signals that triggered app.quit without our X handler)
        _log.warning("Child exited with code %d; restarting (no user quit flag)", exit_code)

        # Track restart frequency to detect crash loops
        now = time.time()
        recent_restarts.append(now)
        recent_restarts = [t for t in recent_restarts if now - t <= RAPID_RESTART_WINDOW]
        if len(recent_restarts) > RAPID_RESTART_THRESHOLD:
            _log.error(
                "Too many restarts (%d in %ds window) - probable crash loop. Backing off 5 min.",
                len(recent_restarts), RAPID_RESTART_WINDOW,
            )
            time.sleep(300)
            recent_restarts.clear()
            continue

        time.sleep(RESTART_DELAY_SEC)


def install_task_scheduler():
    """Register a Windows Task Scheduler entry for maximum survival.

    Runs on logon, restarts on failure, survives taskkill on python.exe
    because Task Scheduler itself is a system service.
    """
    import ctypes
    exe = sys.executable
    if exe.endswith("python.exe"):
        pw = exe.replace("python.exe", "pythonw.exe")
        if os.path.isfile(pw):
            exe = pw
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    xml = r'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Actions>
    <Exec>
      <Command>''' + exe + r'''</Command>
      <Arguments>-m launcher</Arguments>
      <WorkingDirectory>''' + script_dir + r'''</WorkingDirectory>
    </Exec>
  </Actions>
</Task>'''

    tmp_xml = os.path.join(CONFIG_DIR, "_task.xml")
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(tmp_xml, "w", encoding="utf-16") as f:
        f.write(xml)

    try:
        result = subprocess.run(
            ["schtasks", "/Create", "/TN", "DockedLauncher", "/XML", tmp_xml, "/F"],
            capture_output=True, text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return result.returncode == 0
    finally:
        try:
            os.remove(tmp_xml)
        except OSError:
            pass


def uninstall_task_scheduler():
    try:
        subprocess.run(
            ["schtasks", "/Delete", "/TN", "DockedLauncher", "/F"],
            capture_output=True, text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return True
    except Exception:
        return False
