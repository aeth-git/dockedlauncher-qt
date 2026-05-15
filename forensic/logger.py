"""Structured rotating-file logger for app events."""
import logging
import os
from logging.handlers import RotatingFileHandler

from .constants import LOG_DIR, APP_NAME

_configured = False


def setup_logging(level=logging.INFO):
    global _configured
    if _configured:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, "app.log")

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s.%(funcName)s] %(message)s"
    )

    fh = RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=3)
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(fmt)

    root = logging.getLogger(APP_NAME)
    root.setLevel(level)
    root.addHandler(fh)
    root.addHandler(sh)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{APP_NAME}.{name}")
