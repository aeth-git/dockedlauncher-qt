"""Chain of custody log — append-only, separate from the app event log."""
import hashlib
import logging
import os
from datetime import datetime

from .constants import LOG_DIR


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return "unavailable"


class CaseLog:
    def __init__(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(LOG_DIR, f"case_{ts}.log")
        self._log = logging.getLogger(f"CaseLog_{ts}")
        self._log.setLevel(logging.INFO)
        self._log.propagate = False
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self._log.addHandler(fh)
        try:
            user = os.getlogin()
        except OSError:
            user = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
        self._log.info(f"SESSION START | tool=iForensic | user={user}")

    @staticmethod
    def _sanitize(value: str) -> str:
        """Strip newline characters to prevent log injection."""
        return str(value).replace('\n', ' ').replace('\r', ' ')

    def log_source_opened(self, path: str, sha256: str = None):
        if sha256 is None and os.path.isfile(path):
            sha256 = _sha256(path)
        path_safe = self._sanitize(path)
        self._log.info(f"SOURCE OPENED | path={path_safe} | sha256={sha256}")

    def log_file_accessed(self, domain: str, rel_path: str, local_path: str):
        sha256 = _sha256(local_path) if os.path.isfile(local_path) else "n/a"
        domain_safe = self._sanitize(domain)
        rel_path_safe = self._sanitize(rel_path)
        self._log.info(f"FILE ACCESSED | domain={domain_safe} | path={rel_path_safe} | sha256={sha256}")

    def log_export(self, destination: str, record_count: int):
        sha256 = _sha256(destination) if os.path.isfile(destination) else "n/a"
        destination_safe = self._sanitize(destination)
        self._log.info(f"EXPORT | destination={destination_safe} | records={record_count} | sha256={sha256}")

    def log_hash_mismatch(self, path: str, before: str, after: str):
        self._log.warning(f"HASH MISMATCH | path={path} | before={before} | after={after}")

    def log_error(self, context: str, error: str):
        self._log.error(f"ERROR | context={context} | error={error}")
