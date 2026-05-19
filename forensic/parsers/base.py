"""Base parser — SQLite connection helper and ABC."""
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from ..sources.base import DataSource
from ..logger import get_logger

_log = get_logger("parsers.base")


class ParserError(Exception):
    """Raised when a parser cannot read its database."""
    pass


class BaseParser(ABC):
    def __init__(self, source: DataSource):
        self._source = source

    @abstractmethod
    def parse(self) -> List[dict]:
        """Return list of record dicts. Called from a worker thread."""

    def _get_db(self, domain: str, rel_path: str) -> sqlite3.Connection:
        """Open a read-only SQLite connection to (domain, rel_path).
        Creates the connection inside the calling thread (sqlite3 thread safety).
        """
        path = self._source.get_file(domain, rel_path)
        if path is None:
            raise FileNotFoundError(f"Database not found: {domain}/{rel_path}")
        uri = f"file:{path}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.DatabaseError as e:
            raise ParserError(f"Cannot open {rel_path}: {e}") from e

    def _get_db_path(self, domain: str, rel_path: str) -> Optional[Path]:
        return self._source.get_file(domain, rel_path)
