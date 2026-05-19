"""Abstract DataSource — all source types implement this interface."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Tuple


class DataSource(ABC):
    """Resolves domain+relativePath pairs to readable local file paths."""

    source_type: str = "unknown"

    @abstractmethod
    def open(self) -> None:
        """Mount/open the source. Raises IOError or PermissionError on failure."""

    @abstractmethod
    def close(self) -> None:
        """Release all held resources."""

    @abstractmethod
    def get_file(self, domain: str, relative_path: str) -> Optional[Path]:
        """Return a local Path for (domain, relative_path), or None if absent.

        The returned path is guaranteed readable and unmodified.
        """

    @abstractmethod
    def list_files(self, domain: str, prefix: str) -> List[Tuple[str, Path]]:
        """Return [(relativePath, localPath), ...] for files under domain/prefix."""

    def get_device_info(self) -> dict:
        """Return dict with keys: name, imei, ios_version, serial, udid."""
        return {}

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()
