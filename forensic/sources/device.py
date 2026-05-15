"""Live iPhone USB source via pymobiledevice3."""
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from .base import DataSource
from ..logger import get_logger

_log = get_logger("sources.device")


def _pymobile_available() -> bool:
    try:
        import pymobiledevice3  # noqa: F401
        return True
    except ImportError:
        return False


def list_connected_devices() -> List[dict]:
    """Return [{udid, name}, ...] for connected USB devices."""
    if not _pymobile_available():
        return []
    try:
        from pymobiledevice3.usbmux import list_devices
        devices = list_devices()
        return [{"udid": str(d.serial), "name": getattr(d, "label", str(d.serial))}
                for d in devices]
    except Exception as e:
        _log.error("Failed to list devices: %s", e)
        return []


class DeviceSource(DataSource):
    """Connects to a live iPhone over USB. Requires pymobiledevice3."""

    source_type = "live_device"

    def __init__(self, udid: Optional[str] = None):
        self._udid = udid
        self._lockdown = None
        self._temp_dir = Path(tempfile.mkdtemp(prefix="iforensic_live_"))
        self._device_info: dict = {}

    def open(self) -> None:
        if not _pymobile_available():
            raise ImportError(
                "pymobiledevice3 is not installed. "
                "Run: pip install pymobiledevice3"
            )
        from pymobiledevice3.lockdown import create_using_usbmux
        try:
            self._lockdown = create_using_usbmux(serial=self._udid)
        except Exception as e:
            msg = str(e)
            if "NotPaired" in msg or "pairing" in msg.lower():
                raise PermissionError(
                    "Device not trusted. Unlock your iPhone and tap 'Trust' "
                    "when the trust prompt appears, then try again."
                )
            raise IOError(f"Could not connect to device: {e}")

        vals = self._lockdown.all_values or {}
        self._device_info = {
            "name": vals.get("DeviceName", "iPhone"),
            "imei": vals.get("InternationalMobileEquipmentIdentity", ""),
            "ios_version": vals.get("ProductVersion", ""),
            "serial": vals.get("SerialNumber", ""),
            "udid": vals.get("UniqueDeviceID", self._udid or ""),
        }
        _log.info("Connected to device: %s iOS %s",
                  self._device_info["name"], self._device_info["ios_version"])

    def get_file(self, domain: str, relative_path: str) -> Optional[Path]:
        """Pull a file via AFC (media domain) or return None for protected domains."""
        if domain == "CameraRollDomain" or domain.startswith("AppDomain-"):
            return self._afc_pull(relative_path)
        # System DBs (SMS, Contacts, Calls) are not accessible via AFC on non-jailbroken
        _log.warning(
            "System domain %s is not accessible via AFC on non-jailbroken devices. "
            "Use 'Create Backup' to access this data.", domain
        )
        return None

    def _afc_pull(self, path: str) -> Optional[Path]:
        from pymobiledevice3.services.afc import AfcService
        try:
            with AfcService(self._lockdown) as afc:
                data = afc.get_file_contents(path)
            dest = self._temp_dir / Path(path).name
            dest.write_bytes(data)
            return dest
        except Exception as e:
            _log.debug("AFC pull failed for %s: %s", path, e)
            return None

    def list_files(self, domain: str, prefix: str) -> List[Tuple[str, Path]]:
        if domain != "CameraRollDomain":
            return []
        from pymobiledevice3.services.afc import AfcService
        results = []
        try:
            with AfcService(self._lockdown) as afc:
                self._afc_walk(afc, f"/{prefix}", prefix, results)
        except Exception as e:
            _log.error("AFC list failed: %s", e)
        return results

    def _afc_walk(self, afc, afc_path: str, rel_base: str,
                  out: List[Tuple[str, Path]]) -> None:
        try:
            entries = afc.listdir(afc_path)
        except Exception:
            return
        for entry in entries:
            child_afc = f"{afc_path}/{entry}"
            child_rel = f"{rel_base}/{entry}"
            try:
                info = afc.stat(child_afc)
                if info.get("st_ifmt") == "S_IFDIR":
                    self._afc_walk(afc, child_afc, child_rel, out)
                else:
                    local = self._temp_dir / child_rel.replace("/", "_")
                    data = afc.get_file_contents(child_afc)
                    local.write_bytes(data)
                    out.append((child_rel, local))
            except Exception:
                continue

    def get_device_info(self) -> dict:
        return self._device_info

    def close(self) -> None:
        if self._lockdown:
            try:
                self._lockdown.close()
            except Exception:
                pass
            self._lockdown = None
        shutil.rmtree(self._temp_dir, ignore_errors=True)
