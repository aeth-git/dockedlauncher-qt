"""Shared parser utilities — timestamp conversion, plist helpers."""
import datetime
import plistlib
from typing import Optional

APPLE_EPOCH = 978307200  # seconds from Unix epoch (1970) to Apple epoch (2001-01-01)


def apple_ts(val) -> Optional[str]:
    """Convert Apple timestamp to ISO datetime string.
    Handles both seconds (Core Data) and nanoseconds (iOS 13+ sms.db).
    Step 1: if nanoseconds (val > 1e10), divide by 1e9 to get Apple-epoch seconds.
    Step 2: add APPLE_EPOCH to get Unix-epoch seconds.
    """
    if val is None:
        return None
    try:
        val = float(val)
        if val > 1e10:          # nanoseconds
            val = val / 1_000_000_000
        unix = APPLE_EPOCH + val
        return datetime.datetime.fromtimestamp(unix, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return None


def unix_ts(val) -> Optional[str]:
    """Convert Unix timestamp (seconds or milliseconds) to ISO datetime string.
    Used by Telegram (seconds) and Signal (milliseconds).
    """
    if val is None:
        return None
    try:
        val = float(val)
        if val > 1e10:          # milliseconds
            val = val / 1000
        return datetime.datetime.fromtimestamp(val, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return None


def keyed_archive_str(blob: bytes) -> str:
    """Extract NS.string from an NSKeyedArchiver binary plist blob.
    Used for message.attributedBody in sms.db when message.text is NULL.
    """
    if not blob:
        return ""
    try:
        archive = plistlib.loads(blob)
        objects = archive.get("$objects", [])
        for obj in objects:
            if isinstance(obj, dict) and "NS.string" in obj:
                return str(obj["NS.string"])
        # Fallback: find first non-null string
        for obj in objects:
            if isinstance(obj, str) and obj and obj != "$null":
                return obj
    except Exception:
        pass
    return ""


def probe_tables(conn) -> list:
    """Return list of table names in a SQLite database."""
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [row[0] for row in cur.fetchall()]


def fmt_duration(sec: int) -> str:
    """Format a duration in seconds as a human-readable string (e.g. '3m 5s' or '45s')."""
    sec = int(sec or 0)
    return f"{sec // 60}m {sec % 60}s" if sec >= 60 else f"{sec}s"
