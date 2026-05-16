"""Biome stream directory walker (iOS 16+).

Biome replaces KnowledgeC for pattern-of-life data.
Files are stored as SEGB (protobuf) under:
  HomeDomain / Library/Biome/streams/restricted/<StreamName>/local/<UUID>
  HomeDomain / Library/Biome/streams/public/<StreamName>/local/<UUID>

Full SEGB protobuf decoding requires blackboxprotobuf (optional dep).
This parser provides:
  - Stream inventory: which streams exist + file sizes + modification times
  - Basic SEGB record count (reads record offsets from header without decoding content)

Install blackboxprotobuf for richer decoding:
  pip install blackboxprotobuf
"""
import struct
from pathlib import Path
from typing import List

from .base import BaseParser, ParserError
from ..logger import get_logger

_log = get_logger("parsers.biome")

_BIOME_PREFIX = "Library/Biome/streams/"

# Stream name → human label
_STREAM_LABELS = {
    "_DKEvent.App.Install":         "App Installs",
    "_DKEvent.App.inFocus":         "App Focus",
    "NowPlaying":                   "Now Playing (Media)",
    "Notification":                 "Notifications",
    "AppIntent":                    "Siri / Shortcuts Intents",
    "_DKEvent.Safari.History":      "Safari (Biome)",
    "_DKEvent.Carplay.IsConnected": "CarPlay",
    "_DKEvent.Device.Plugged.In":   "Charging",
    "_DKEvent.Wifi.Connected":      "WiFi Connected",
    "_DKEvent.Bluetooth":           "Bluetooth",
    "_DKEvent.BatteryPercentage":   "Battery %",
    "_DKEvent.Display.Backlit":     "Screen On",
    "_DKEvent.Mode.AirplaneMode":   "Airplane Mode",
    "_DKEvent.Inferred.Motion":     "Motion (Walking/Driving)",
    "_DKEvent.SiriUI":              "Siri Activations",
    "_DKEvent.DK.Keybag":           "Keybag Lock State",
    "UserActivityMetadata":         "User Activity (NSUserActivity)",
    "_DKEvent.Sync":                "iCloud Sync",
    "_DKEvent.Device.Hardware":     "Device Hardware Events",
}


def _count_segb_records(data: bytes) -> int:
    """Count records in a SEGB file by reading the fixed-size entry headers.

    SEGB record layout (per community reverse engineering):
      Offset 0: 8 bytes — Apple epoch timestamp (double, big-endian)
      Offset 8: 4 bytes — protobuf payload length (uint32, little-endian)
      Then: protobuf payload + alignment padding to 8-byte boundary
    File ends with 4-byte magic "SEGB" (0x42 0x47 0x45 0x53).
    """
    if len(data) < 12:
        return 0
    # Verify SEGB magic at end
    if data[-4:] != b"SEGB":
        return 0
    count = 0
    pos = 0
    limit = len(data) - 4
    try:
        while pos + 12 <= limit:
            payload_len = struct.unpack_from("<I", data, pos + 8)[0]
            record_len = 8 + 4 + payload_len
            # Align to 8 bytes
            record_len = (record_len + 7) & ~7
            if record_len == 0 or pos + record_len > limit:
                break
            count += 1
            pos += record_len
    except (struct.error, OverflowError):
        pass
    return count


class BiomeParser(BaseParser):
    def parse(self) -> List[dict]:
        stream_files = self._source.list_files("HomeDomain", _BIOME_PREFIX)
        if not stream_files:
            raise ParserError(
                "Biome streams not found in this backup. "
                "Biome requires a filesystem extraction (iOS 16+) or an "
                "encrypted iTunes backup on iOS 16+"
            )

        # Build stream inventory
        stream_inventory: dict = {}
        for rel_path, phys_path in stream_files:
            # rel_path is the full domain-relative path, e.g.:
            #   Library/Biome/streams/restricted/<StreamName>/local/<UUID>
            # Strip the known prefix to get the remainder.
            suffix = rel_path[len(_BIOME_PREFIX):]
            parts = suffix.split("/")
            if not parts or not parts[0]:
                continue
            # Handle both tiered (restricted/<Name>/...) and flat (<Name>/...) layouts
            if parts[0] in ("restricted", "public") and len(parts) >= 2:
                stream_name = parts[1]
            else:
                stream_name = parts[0]
            if stream_name not in stream_inventory:
                stream_inventory[stream_name] = {
                    "stream_name": stream_name,
                    "label": _STREAM_LABELS.get(stream_name, stream_name),
                    "file_count": 0,
                    "total_size_bytes": 0,
                    "record_count": 0,
                }
            inv = stream_inventory[stream_name]
            inv["file_count"] += 1
            try:
                size = phys_path.stat().st_size
                inv["total_size_bytes"] += size
                if size < 10 * 1024 * 1024:   # only parse files < 10MB for speed
                    data = phys_path.read_bytes()
                    inv["record_count"] += _count_segb_records(data)
            except OSError:
                pass

        records = []
        for inv in sorted(stream_inventory.values(),
                           key=lambda x: x["total_size_bytes"], reverse=True):
            size_kb = inv["total_size_bytes"] // 1024
            records.append({
                "label": inv["label"],
                "stream_name": inv["stream_name"],
                "files": inv["file_count"],
                "total_size": f"{size_kb:,} KB" if size_kb < 1024
                              else f"{size_kb // 1024:,} MB",
                "record_count": inv["record_count"],
                "decode_status": "Basic (protobuf not decoded)",
            })

        _log.info("Biome: %d streams found", len(records))
        return records
