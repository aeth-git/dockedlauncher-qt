"""Structured logging with rotating file handler."""
import logging
import os
from logging.handlers import RotatingFileHandler

from .constants import CONFIG_DIR

LOG_FILE = os.path.join(CONFIG_DIR, "app.log")
LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s.%(funcName)s] %(message)s"
LOG_MAX_BYTES = 2 * 1024 * 1024  # 2MB
LOG_BACKUP_COUNT = 3


def setup_logging(level=logging.INFO):
    """Configure application logging. Call once from main.py."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    root = logging.getLogger("DockedLauncher")
    root.setLevel(level)

    if not root.handlers:
        # File handler with rotation
        fh = RotatingFileHandler(
            LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter(LOG_FORMAT))
        fh.setLevel(level)
        root.addHandler(fh)

        # Stderr for development
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter(LOG_FORMAT))
        sh.setLevel(logging.WARNING)
        root.addHandler(sh)


def get_logger(name):
    """Get a child logger under the DockedLauncher namespace."""
    return logging.getLogger("DockedLauncher.{}".format(name))
