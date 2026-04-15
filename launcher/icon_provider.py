"""High-resolution icon extraction with persistent QPixmap LRU cache."""
import ctypes
import ctypes.wintypes
import os
import subprocess
from collections import OrderedDict

from PyQt5.QtWidgets import QFileIconProvider
from PyQt5.QtCore import QFileInfo, QSize
from PyQt5.QtGui import QIcon, QPixmap, QColor
from PyQt5.QtWinExtras import QtWin

from .constants import ICON_SIZE, ACCENT_COLOR
from .logger import get_logger

_log = get_logger("icon_provider")
_provider = QFileIconProvider()

# LRU cache storing QPixmap (actual pixel data, survives widget deletion)
_MAX_CACHE = 200
_pixmap_cache = OrderedDict()

# Windows Shell constants
SHGFI_SYSICONINDEX = 0x4000
SHIL_JUMBO = 4
SHIL_EXTRALARGE = 2
IID_IImageList = b'\x26\x59\xEB\x46\x2E\x58\x17\x40\x9F\xDF\xE8\x99\x8D\xAA\x09\x50'


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", ctypes.wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", ctypes.wintypes.DWORD),
        ("szDisplayName", ctypes.c_wchar * 260),
        ("szTypeName", ctypes.c_wchar * 80),
    ]


def get_pixmap(filepath, size=256):
    """Get a cached 256x256 QPixmap for the given file. LRU eviction at 200 entries."""
    key = os.path.normcase(filepath)
    if key in _pixmap_cache:
        _pixmap_cache.move_to_end(key)
        return _pixmap_cache[key]

    pixmap = _extract_pixmap(filepath, size)
    _pixmap_cache[key] = pixmap
    if len(_pixmap_cache) > _MAX_CACHE:
        evicted_key, _ = _pixmap_cache.popitem(last=False)
        _log.debug("Cache evicted: %s", evicted_key)
    return pixmap


def get_icon(filepath, size=ICON_SIZE):
    """Get a QIcon (wraps cached pixmap). Backward compatible."""
    return QIcon(get_pixmap(filepath))


def clear_cache():
    _pixmap_cache.clear()


def _extract_pixmap(filepath, size):
    """Extract highest resolution icon and return as QPixmap."""
    if not os.path.exists(filepath):
        return _default_pixmap(size)

    # Try jumbo shell icon (256x256)
    pixmap = _extract_jumbo_pixmap(filepath)
    if pixmap and not pixmap.isNull() and pixmap.width() > 1:
        return pixmap

    # Try QFileIconProvider
    icon = _provider.icon(QFileInfo(filepath))
    if not icon.isNull():
        pm = icon.pixmap(QSize(size, size))
        if not _is_blank_pixmap(pm):
            return pm

    # For .lnk: resolve target and retry
    if filepath.lower().endswith(".lnk"):
        target = _resolve_lnk_target(filepath)
        if target and os.path.exists(target):
            pixmap = _extract_jumbo_pixmap(target)
            if pixmap and not pixmap.isNull() and pixmap.width() > 1:
                return pixmap
            icon = _provider.icon(QFileInfo(target))
            if not icon.isNull():
                pm = icon.pixmap(QSize(size, size))
                if not _is_blank_pixmap(pm):
                    return pm

    return _default_pixmap(size)


def _extract_jumbo_pixmap(filepath):
    """Extract jumbo icon via SHGetImageList + QtWin.fromHICON → QPixmap."""
    try:
        shell32 = ctypes.windll.shell32
        comctl32 = ctypes.windll.comctl32
        user32 = ctypes.windll.user32

        sfi = SHFILEINFOW()
        result = shell32.SHGetFileInfoW(
            filepath, 0, ctypes.byref(sfi), ctypes.sizeof(sfi), SHGFI_SYSICONINDEX
        )
        if not result:
            return None

        icon_index = sfi.iIcon

        for shil_type in (SHIL_JUMBO, SHIL_EXTRALARGE):
            image_list = ctypes.c_void_p()
            hr = shell32.SHGetImageList(shil_type, IID_IImageList, ctypes.byref(image_list))
            if hr != 0 or not image_list.value:
                continue

            hicon = comctl32.ImageList_GetIcon(image_list, icon_index, 0x1)
            if not hicon:
                continue

            try:
                pixmap = QtWin.fromHICON(hicon)
                user32.DestroyIcon(hicon)
                if not pixmap.isNull() and not _is_blank_pixmap(pixmap):
                    return pixmap
            except Exception:
                user32.DestroyIcon(hicon)
                continue

        return None
    except Exception as e:
        _log.warning("Jumbo icon extraction failed for %s: %s", filepath, e)
        return None


def _is_blank_pixmap(pixmap):
    """Check if a pixmap is blank by sampling pixels."""
    if pixmap.isNull():
        return True
    img = pixmap.toImage()
    if img.isNull():
        return True
    colors = set()
    w, h = img.width(), img.height()
    step = max(1, min(w, h) // 8)
    for x in range(0, w, step):
        for y in range(0, h, step):
            colors.add(img.pixel(x, y))
            if len(colors) > 2:
                return False
    return True


def _resolve_lnk_target(lnk_path):
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(New-Object -ComObject WScript.Shell).CreateShortcut('{}').TargetPath".format(lnk_path)],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() or None
    except subprocess.TimeoutExpired:
        _log.warning("Timeout resolving .lnk target: %s", lnk_path)
        return None
    except Exception as e:
        _log.warning("Failed to resolve .lnk target %s: %s", lnk_path, e)
        return None


def _default_pixmap(size=256):
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(ACCENT_COLOR))
    return pixmap
