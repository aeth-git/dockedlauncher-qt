"""Installed apps parser."""
import plistlib
from typing import List

from .base import BaseParser
from ..sources.backup import BackupSource
from ..logger import get_logger

_log = get_logger("parsers.apps")


class InstalledAppsParser(BaseParser):
    def parse(self) -> List[dict]:
        source = self._source
        # Delegate to backup-specific or filesystem-specific approach
        if isinstance(source, BackupSource):
            return self._from_backup(source)
        try:
            # Live device
            return self._from_device()
        except Exception:
            pass
        return self._from_filesystem()

    def _from_backup(self, source: BackupSource) -> List[dict]:
        bundles = source.list_app_domains()
        apps = {}
        for bundle_id in bundles:
            apps[bundle_id] = {
                "bundle_id": bundle_id,
                "name": bundle_id,
                "version": "",
                "author": "",
                "genre": "",
            }
            meta_path = source.get_file(f"AppDomain-{bundle_id}", "iTunesMetadata.plist")
            if meta_path:
                try:
                    with open(meta_path, "rb") as f:
                        meta = plistlib.load(f)
                    apps[bundle_id].update({
                        "name": meta.get("itemName", bundle_id),
                        "version": meta.get("bundleShortVersionString", ""),
                        "author": meta.get("artistName", ""),
                        "genre": meta.get("genre", ""),
                    })
                except Exception as e:
                    _log.debug("Failed to read iTunesMetadata for %s: %s", bundle_id, e)
        result = sorted(apps.values(), key=lambda x: x["name"].lower())
        _log.info("Found %d installed apps", len(result))
        return result

    def _from_device(self) -> List[dict]:
        from pymobiledevice3.services.installation_proxy import InstallationProxyService
        lockdown = getattr(self._source, "_lockdown", None)
        if not lockdown:
            raise RuntimeError("No active lockdown session")
        with InstallationProxyService(lockdown) as proxy:
            raw = proxy.get_apps(application_type="User")
        result = []
        for bundle_id, info in raw.items():
            result.append({
                "bundle_id": bundle_id,
                "name": info.get("CFBundleDisplayName", bundle_id),
                "version": info.get("CFBundleShortVersionString", ""),
                "author": "",
                "genre": "",
            })
        return sorted(result, key=lambda x: x["name"].lower())

    def _from_filesystem(self) -> List[dict]:
        apps = []
        files = self._source.list_files(
            "AppDomain", "private/var/containers/Bundle/Application"
        )
        seen = set()
        for rel, local in files:
            if local.name == "Info.plist":
                try:
                    with open(local, "rb") as f:
                        info = plistlib.load(f)
                    bid = info.get("CFBundleIdentifier", "")
                    if bid and bid not in seen:
                        seen.add(bid)
                        apps.append({
                            "bundle_id": bid,
                            "name": info.get("CFBundleDisplayName",
                                            info.get("CFBundleName", bid)),
                            "version": info.get("CFBundleShortVersionString", ""),
                            "author": "",
                            "genre": "",
                        })
                except Exception:
                    pass
        return sorted(apps, key=lambda x: x["name"].lower())
