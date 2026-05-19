"""iLEAPP integration — run iLEAPP against an extracted backup tree.

iLEAPP is an open-source iOS Logs, Events, And Plists Parser that runs ~200
artifact parsers against a filesystem dump and produces an HTML report.

The user must install it separately (we don't bundle it):
  pip install ileapp
or clone https://github.com/abrignoni/iLEAPP and run ileapp.py directly.

This module just finds the right invocation, runs it, and locates the
resulting index.html.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


DEFAULT_CLONE_DIR = Path.home() / "iLEAPP"
ILEAPP_GIT_URL = "https://github.com/abrignoni/iLEAPP.git"


def find_ileapp_cmd() -> Optional[List[str]]:
    """Return the argv prefix to invoke iLEAPP, or None if it can't be found.

    Tries in order:
      1. The `ileapp` console script on PATH
      2. `python -m ileapp` (if the package was pip-installed)
      3. `ILEAPP_PATH` env var pointing at a clone of iLEAPP/ileapp.py
      4. Default clone location: ~/iLEAPP/ileapp.py
      5. Sibling clone: ./iLEAPP/ileapp.py (relative to cwd)
    """
    exe = shutil.which("ileapp")
    if exe:
        return [exe]

    try:
        r = subprocess.run(
            [sys.executable, "-m", "ileapp", "--help"],
            capture_output=True, timeout=10,
        )
        if r.returncode == 0 or b"usage" in r.stdout.lower() + r.stderr.lower():
            return [sys.executable, "-m", "ileapp"]
    except (subprocess.SubprocessError, OSError):
        pass

    env_path = os.environ.get("ILEAPP_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return [sys.executable, str(p)]
        if p.is_dir() and (p / "ileapp.py").is_file():
            return [sys.executable, str(p / "ileapp.py")]

    for candidate in (DEFAULT_CLONE_DIR / "ileapp.py",
                       Path.cwd() / "iLEAPP" / "ileapp.py"):
        if candidate.is_file():
            return [sys.executable, str(candidate)]

    return None


def auto_install(progress_cb=None) -> Path:
    """Clone iLEAPP into ~/iLEAPP and pip-install its requirements.

    Returns the path to ileapp.py on success. Raises on failure.
    progress_cb: optional callable(str) for status messages.
    """
    def report(msg):
        if progress_cb:
            progress_cb(msg)

    if not shutil.which("git"):
        raise RuntimeError(
            "git is not on PATH. Install Git for Windows from "
            "https://git-scm.com/download/win, then retry."
        )

    target = DEFAULT_CLONE_DIR
    if not (target / "ileapp.py").is_file():
        report(f"Cloning iLEAPP into {target}…")
        subprocess.run(
            ["git", "clone", "--depth", "1", ILEAPP_GIT_URL, str(target)],
            check=True,
        )
    else:
        report(f"iLEAPP already present at {target}")

    req = target / "requirements.txt"
    if req.is_file():
        report("Installing iLEAPP requirements (pip)…")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req)],
            check=True,
        )

    script = target / "ileapp.py"
    if not script.is_file():
        raise RuntimeError(f"Clone succeeded but {script} missing")
    return script


def find_report_html(output_dir: Path) -> Optional[Path]:
    """iLEAPP writes to {output_dir}/iLEAPP_Reports_<timestamp>/index.html.
    Return the newest index.html under output_dir, or None."""
    candidates = list(output_dir.rglob("index.html"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def build_argv(extraction_dir: Path, output_dir: Path) -> List[str]:
    """Build the iLEAPP argv for analyzing an extracted backup tree.

    -t fs   = filesystem dump (matches the {root}/{domain}/{rel} layout)
    -i      = input directory
    -o      = output directory (report will land in a timestamped subdir)
    """
    cmd = find_ileapp_cmd()
    if cmd is None:
        raise FileNotFoundError(
            "iLEAPP not found. Install via 'pip install ileapp' or set "
            "ILEAPP_PATH to your ileapp.py."
        )
    return cmd + ["-t", "fs", "-i", str(extraction_dir), "-o", str(output_dir)]
