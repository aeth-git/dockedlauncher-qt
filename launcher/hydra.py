"""Hydra defense system: bulletproof process survival.

Strategy:
1. Clone pythonw.exe to %APPDATA%/DockedLauncher/launcher_core.exe so our
   processes appear in Task Manager as "launcher_core.exe" - common scripts
   running `taskkill /f /im python*.exe` will not find us.
2. Twin-watchdog heartbeat: two processes write heartbeat timestamps to
   separate files. Each monitors the other. If one dies, the survivor
   relaunches it within ~1 second. To kill the app permanently you'd need
   to kill both simultaneously (near-impossible from a single command),
   AND know the exact custom executable name.
3. Respect user intent: the X button writes a quit.flag file that both
   processes honor.

Enterprise-safe: no admin, no registry, no DLL injection, no services.
"""
import os
import shutil
import subprocess
import sys
import time

from .constants import CONFIG_DIR
from .logger import get_logger

_log = get_logger("hydra")

CORE_EXE = os.path.join(CONFIG_DIR, "launcher_core.exe")
WATCHDOG_HEARTBEAT = os.path.join(CONFIG_DIR, "watchdog.heartbeat")
APP_HEARTBEAT = os.path.join(CONFIG_DIR, "app.heartbeat")
QUIT_FLAG = os.path.join(CONFIG_DIR, "quit.flag")

HEARTBEAT_INTERVAL = 0.5    # seconds
HEARTBEAT_STALE = 3.0       # if a peer's heartbeat is this old, relaunch it
RESPAWN_COOLDOWN = 2.0      # wait after relaunching a peer


def ensure_core_exe():
    """Copy pythonw.exe to launcher_core.exe in AppData if not present or stale."""
    os.makedirs(CONFIG_DIR, exist_ok=True)

    src = sys.executable
    # Prefer pythonw.exe (no console) over python.exe
    if src.lower().endswith("python.exe"):
        pw = src[:-10] + "pythonw.exe"
        if os.path.isfile(pw):
            src = pw

    # Rebuild if missing or source is newer (e.g., Python upgrade)
    needs_copy = True
    if os.path.isfile(CORE_EXE):
        try:
            if os.path.getmtime(CORE_EXE) >= os.path.getmtime(src):
                needs_copy = False
        except OSError:
            pass

    if needs_copy:
        try:
            shutil.copy2(src, CORE_EXE)
            _log.info("Copied %s -> %s", src, CORE_EXE)
        except Exception as e:
            _log.warning("Could not clone Python executable: %s", e)
            return src  # fall back to original

    return CORE_EXE


def user_quit():
    return os.path.isfile(QUIT_FLAG)


def clear_quit_flag():
    try:
        if os.path.isfile(QUIT_FLAG):
            os.remove(QUIT_FLAG)
    except OSError:
        pass


def write_heartbeat(path):
    """Atomic heartbeat write."""
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(str(time.time()))
        os.replace(tmp, path)
    except OSError:
        pass


def read_heartbeat(path):
    """Return last heartbeat timestamp, or 0 if missing/corrupt."""
    try:
        with open(path) as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        return 0.0


def peer_alive(heartbeat_path):
    """True if peer's heartbeat is fresh."""
    last = read_heartbeat(heartbeat_path)
    return (time.time() - last) < HEARTBEAT_STALE


def spawn_detached(cmd):
    """Launch a fully detached process (no console, no parent link).

    Uses CREATE_BREAKAWAY_FROM_JOB + DETACHED_PROCESS so killing our process
    tree (e.g. via 'taskkill /T') won't cascade to the child.
    """
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000
    CREATE_NO_WINDOW = 0x08000000

    flags = (DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
             | CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW)
    try:
        return subprocess.Popen(
            cmd,
            creationflags=flags,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        # Some flags not supported on certain Windows builds - retry without BREAKAWAY
        try:
            return subprocess.Popen(
                cmd,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            _log.error("spawn_detached failed: %s", e)
            return None


def launch_hydra(extra_args=None):
    """Launch BOTH the app and the guardian watchdog as sibling detached processes.

    Returns (app_proc, watchdog_proc) or (None, None) on failure.
    Both processes are independent of this launcher process.
    """
    exe = ensure_core_exe()
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # App process
    app_cmd = [exe, "-m", "launcher", "--no-watchdog", "--role", "app"]
    if extra_args:
        app_cmd.extend(extra_args)

    # Watchdog process
    wd_cmd = [exe, "-m", "launcher", "--role", "watchdog"]
    if extra_args:
        wd_cmd.extend(extra_args)

    clear_quit_flag()

    # Launch app first, then watchdog
    app_proc = spawn_detached(app_cmd)
    time.sleep(0.3)
    wd_proc = spawn_detached(wd_cmd)

    _log.info("Hydra launched: app=%s watchdog=%s",
              app_proc.pid if app_proc else None,
              wd_proc.pid if wd_proc else None)

    return app_proc, wd_proc


def app_heartbeat_loop():
    """App-side heartbeat: writes our timestamp, relaunches watchdog if peer is stale.

    Called from a QTimer in the app process every 500ms.
    """
    if user_quit():
        return

    write_heartbeat(APP_HEARTBEAT)

    if not peer_alive(WATCHDOG_HEARTBEAT):
        _log.warning("Watchdog heartbeat stale - relaunching watchdog")
        exe = ensure_core_exe()
        wd_cmd = [exe, "-m", "launcher", "--role", "watchdog"]
        spawn_detached(wd_cmd)
        write_heartbeat(WATCHDOG_HEARTBEAT)  # grace period


def watchdog_main(extra_args=None):
    """Guardian watchdog - runs as sibling of the app, relaunches app if it dies.

    Writes own heartbeat, monitors app heartbeat. Exits only on quit.flag.
    """
    _log.info("Watchdog started (PID %d)", os.getpid())

    last_spawn = 0
    while True:
        # User explicitly quit?
        if user_quit():
            _log.info("User quit flag detected - watchdog exiting")
            return

        # Write heartbeat
        write_heartbeat(WATCHDOG_HEARTBEAT)

        # Check app
        if not peer_alive(APP_HEARTBEAT):
            now = time.time()
            if now - last_spawn > RESPAWN_COOLDOWN:
                _log.warning("App heartbeat stale - relaunching app")
                exe = ensure_core_exe()
                app_cmd = [exe, "-m", "launcher", "--no-watchdog", "--role", "app"]
                if extra_args:
                    app_cmd.extend(extra_args)
                spawn_detached(app_cmd)
                write_heartbeat(APP_HEARTBEAT)  # grace period
                last_spawn = now

        time.sleep(HEARTBEAT_INTERVAL)
