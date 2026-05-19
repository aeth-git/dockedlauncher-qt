"""Crash log parser — reads .ips (JSON) and .crash (text) files from backup."""
import json
import re
from pathlib import Path
from typing import List, Optional

from .base import BaseParser, ParserError
from ..logger import get_logger

_log = get_logger("parsers.crash_logs")

_CRASH_PREFIXES = [
    ("HomeDomain",  "Library/Logs/CrashReporter/"),
    ("HomeDomain",  "Library/Logs/DiagnosticReports/"),
    ("RootDomain",  "Library/Logs/CrashReporter/"),
]

_MAX_FILES = 1000

# Patterns for legacy .crash text format
_RE_PROCESS   = re.compile(r"^Process:\s+(.+?)\s+\[", re.MULTILINE)
_RE_BUNDLE    = re.compile(r"^Bundle Identifier:\s+(.+)", re.MULTILINE)
_RE_EXCEPTION = re.compile(r"^Exception Type:\s+(.+)", re.MULTILINE)
_RE_DATETIME  = re.compile(r"^Date/Time:\s+(.+)", re.MULTILINE)
_RE_OS        = re.compile(r"^OS Version:\s+(.+)", re.MULTILINE)


class CrashLogParser(BaseParser):
    def parse(self) -> List[dict]:
        paths: List[tuple] = []  # (rel_path, phys_path)
        for domain, prefix in _CRASH_PREFIXES:
            for rel, phys in self._source.list_files(domain, prefix):
                if rel.endswith(".ips") or rel.endswith(".crash"):
                    paths.append((rel, phys))
                    if len(paths) >= _MAX_FILES:
                        break
            if len(paths) >= _MAX_FILES:
                break

        if not paths:
            raise ParserError("No crash logs found in this backup")

        records = []
        for rel_path, phys_path in paths:
            file_name = Path(rel_path).name
            try:
                if rel_path.endswith(".ips"):
                    rec = self._parse_ips(phys_path, file_name)
                else:
                    rec = self._parse_crash(phys_path, file_name)
                records.append(rec)
            except Exception as exc:
                _log.debug("Skipping %s: %s", file_name, exc)

        _log.info("CrashLogs: %d records from %d files", len(records), len(paths))
        return records

    # ── IPS (modern JSON) ────────────────────────────────────────────────────

    @staticmethod
    def _parse_ips(path: Path, file_name: str) -> dict:
        text = path.read_text(encoding="utf-8", errors="replace")
        # Some .ips files have a header line before the JSON block
        # Try the whole text first; if that fails, skip the first line
        data: dict = {}
        for attempt in (text, "\n".join(text.splitlines()[1:])):
            try:
                data = json.loads(attempt)
                break
            except json.JSONDecodeError:
                continue
        if not data:
            # Last resort: try to find a JSON object in the text
            brace = text.find("{")
            if brace != -1:
                data = json.loads(text[brace:])

        timestamp   = data.get("timestamp", "")
        ios_version = data.get("os_version", "")
        process     = data.get("procName", "") or data.get("coalitionName", "")
        bundle_id   = data.get("bundleID", "") or data.get("coalitionName", "")

        exception_type = ""
        signal         = ""
        reason         = ""

        exc_block = data.get("exception", {})
        if isinstance(exc_block, dict):
            exception_type = exc_block.get("type", "")
            reason         = exc_block.get("codes", "")

        term_block = data.get("termination", {})
        if isinstance(term_block, dict):
            signal = term_block.get("indicator", "") or str(term_block.get("code", ""))
            if not exception_type:
                exception_type = term_block.get("namespace", "")
            if not reason:
                reason = term_block.get("indicator", "")

        return {
            "timestamp":      str(timestamp),
            "process":        str(process),
            "bundle_id":      str(bundle_id),
            "exception_type": str(exception_type),
            "signal":         str(signal),
            "reason":         str(reason),
            "ios_version":    str(ios_version),
            "file_name":      file_name,
        }

    # ── CRASH (legacy text) ──────────────────────────────────────────────────

    @staticmethod
    def _parse_crash(path: Path, file_name: str) -> dict:
        text = path.read_text(encoding="utf-8", errors="replace")

        def _first(pattern) -> str:
            m = pattern.search(text)
            return m.group(1).strip() if m else ""

        raw_exc   = _first(_RE_EXCEPTION)   # e.g. "EXC_BAD_ACCESS (SIGSEGV)"
        exc_match = re.match(r"(\S+)\s*\(([^)]+)\)", raw_exc)
        if exc_match:
            exception_type = exc_match.group(1)
            signal         = exc_match.group(2)
        else:
            exception_type = raw_exc
            signal         = ""

        return {
            "timestamp":      _first(_RE_DATETIME),
            "process":        _first(_RE_PROCESS),
            "bundle_id":      _first(_RE_BUNDLE),
            "exception_type": exception_type,
            "signal":         signal,
            "reason":         "",
            "ios_version":    _first(_RE_OS),
            "file_name":      file_name,
        }
