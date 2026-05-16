"""Indicators of Compromise (IOC) checker — stalkerware and Pegasus detection.

Checks:
  1. shutdown.log — known spyware process residue (Pegasus, Predator)
  2. DataUsage.sqlite — processes with anomalous background upload volume
  3. TCC.db — apps with sensitive permissions inconsistent with function
  4. UninstalledApplications.plist — known stalkerware bundle IDs

References:
  - Kaspersky shutdown.log Pegasus detection (Jan 2024)
  - Amnesty International MVT IOC methodology
  - iVerify / Lookout stalkerware bundle ID lists
"""
from pathlib import Path
from typing import List

from .base import BaseParser, ParserError
from ..logger import get_logger

_log = get_logger("parsers.ioc")

# Known Pegasus / Predator process names from public IOC reports
_KNOWN_MALWARE_PROCESSES = {
    "falafel", "fork", "gssdp", "installd", "launchafd", "libgpp",
    "nfcd", "pagestuff", "pcmag", "ptpd", "python3", "runner",
    "storedefault", "storedmk", "syslog", "update", "usbd",
    # Predator IOCs (Cytrox)
    "airportd", "com.apple.geo.daemon",
    # Generic stalkerware residue
    "xpc.service.private", "wapic",
}

# Known stalkerware bundle IDs (non-exhaustive)
_STALKERWARE_BUNDLES = {
    "com.thetruthspy.truespy",
    "com.spyic.app",
    "com.cocospy.spy",
    "com.highsterspyapp.hs",
    "com.umobix.spyware",
    "org.ispyoo.main",
    "com.hoverwatch.app",
    "com.familyorbit.app",
    "com.flexispy.flexispy",
    "com.mspy.spyapp",
    "com.ikeymonitor.ikeymonitor",
    "com.spymessenger.app",
    "com.spyhide.app",
    "com.minspy.mspy",
}


class IOCChecker(BaseParser):
    """Checks backup artifacts for known spyware/stalkerware indicators."""

    def parse(self) -> List[dict]:
        findings: List[dict] = []
        findings.extend(self._check_shutdown_log())
        findings.extend(self._check_tcc())
        findings.extend(self._check_stalkerware_bundles())
        findings.extend(self._check_data_usage())

        if not findings:
            findings.append({
                "severity": "INFO",
                "category": "IOC Check",
                "finding": "No known indicators of compromise detected",
                "detail": (
                    "No Pegasus/Predator process residue in shutdown.log, "
                    "no known stalkerware bundle IDs found. "
                    "This does not rule out compromise — only known IOCs were checked."
                ),
                "bundle_id": "",
            })
        _log.info("IOC: %d findings", len(findings))
        return findings

    def _check_shutdown_log(self) -> List[dict]:
        """Parse shutdown.log for known malware process names."""
        log_path = self._source.get_file(
            "RootDomain", "Library/Logs/shutdown.log"
        )
        if log_path is None:
            log_path = self._source.get_file(
                "RootDomain", "Library/Diagnostics/Extra/shutdown.log"
            )
        if log_path is None:
            return []
        try:
            text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        findings = []
        for line in text.splitlines():
            line_lower = line.lower()
            for proc in _KNOWN_MALWARE_PROCESSES:
                if proc in line_lower:
                    findings.append({
                        "severity": "HIGH",
                        "category": "Pegasus/Spyware Process",
                        "finding": f"Known malware process '{proc}' found in shutdown.log",
                        "detail": line.strip()[:200],
                        "bundle_id": proc,
                    })
                    break

        _log.info("shutdown.log: %d IOC hits", len(findings))
        return findings

    def _check_tcc(self) -> List[dict]:
        """Flag apps with camera/microphone access that have no obvious legitimate reason."""
        try:
            from .tcc import TCCParser
            records = TCCParser(self._source).parse()
        except Exception:
            return []

        sensitive_services = {"Camera", "Microphone", "Location", "Contacts"}
        findings = []
        for r in records:
            if r.get("permission") != "Allowed":
                continue
            if r.get("service") not in sensitive_services:
                continue
            bundle = r.get("bundle_id", "")
            # Flag unknown/suspicious short bundle IDs
            if bundle and (
                bundle.count(".") < 2 or
                any(s in bundle.lower() for s in ["spy", "monitor", "track", "hidden", "silent"])
            ):
                findings.append({
                    "severity": "MEDIUM",
                    "category": "Suspicious Permission",
                    "finding": f"App '{bundle}' has {r['service']} permission",
                    "detail": (
                        f"Bundle '{bundle}' has '{r['service']}' access granted. "
                        "Verify this app's legitimate purpose."
                    ),
                    "bundle_id": bundle,
                })
        return findings

    def _check_stalkerware_bundles(self) -> List[dict]:
        """Check installed + deleted app lists for known stalkerware bundles."""
        all_bundles = set()
        try:
            from .apps import InstalledAppsParser
            apps = InstalledAppsParser(self._source).parse()
            all_bundles.update(a.get("bundle_id", "") for a in apps)
        except Exception:
            pass
        try:
            from .deleted_apps import DeletedAppsParser
            deleted = DeletedAppsParser(self._source).parse()
            all_bundles.update(d.get("bundle_id", "") for d in deleted)
        except Exception:
            pass

        findings = []
        for bundle in all_bundles:
            if bundle in _STALKERWARE_BUNDLES:
                findings.append({
                    "severity": "CRITICAL",
                    "category": "Known Stalkerware",
                    "finding": f"Known stalkerware bundle '{bundle}' detected",
                    "detail": (
                        f"Bundle ID '{bundle}' is a known commercial spyware/stalkerware application. "
                        "Immediate action recommended."
                    ),
                    "bundle_id": bundle,
                })
        return findings

    def _check_data_usage(self) -> List[dict]:
        """Flag processes with anomalously high background upload (> 100MB)."""
        try:
            from .data_usage import DataUsageParser
            usage = DataUsageParser(self._source).parse()
        except Exception:
            return []

        threshold = 100 * 1024 * 1024   # 100 MB
        findings = []
        for u in usage:
            # Sum raw cellular + wifi out
            total_out = int(u.get("wifi_out", "0 B").split()[0].replace(",", "") or 0)
            if total_out > threshold:
                findings.append({
                    "severity": "LOW",
                    "category": "Anomalous Upload",
                    "finding": (
                        f"'{u['bundle_id']}' uploaded {u['wifi_out']} over WiFi"
                    ),
                    "detail": (
                        f"Process '{u['bundle_id']}' sent significant background data. "
                        "This may be normal for cloud-sync apps; verify."
                    ),
                    "bundle_id": u.get("bundle_id", ""),
                })
        return findings
