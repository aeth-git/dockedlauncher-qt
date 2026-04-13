"""High-resolution icon extraction using Windows Shell + Qt."""
import ctypes
import ctypes.wintypes
import os
import subprocess

from PyQt5.QtWidgets import QFileIconProvider, QApplication
from PyQt5.QtCore import QFileInfo, QSize
from PyQt5.QtGui import QIcon, QPixmap, QImage, QColor
from PyQt5.QtWinExtras import QtWin

from .constants import ICON_SIZE

_provider = QFileIconProvider()
_cache = {}

# Windows Shell constants for jumbo icons
SHGFI_SYSICONINDEX = 0x4000
SHGFI_ICON = 0x100
SHIL_JUMBO = 4       # 256x256
SHIL_EXTRALARGE = 2  # 48x48
IID_IImageList = b'\x26\x59\xEB\x46\x2E\x58\x17\x40\x9F\xDF\xE8\x99\x8D\xAA\x09\x50'


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", ctypes.wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", ctypes.wintypes.DWORD),
        ("szDisplayName", ctypes.c_wchar * 260),
        ("szTypeName", ctypes.c_wchar * 80),
    ]


def get_icon(filepath, size=ICON_SIZE):
    """Get a QIcon for the given file path. Returns jumbo (256x256) when available."""
    key = os.path.normcase(filepath)
    if key in _cache:
        return _cache[key]
    icon = _extract_icon(filepath, size)
    _cache[key] = icon
    return icon


def clear_cache():
    _cache.clear()


def _extract_icon(filepath, size):
    """Extract highest resolution icon available."""
    if not os.path.exists(filepath):
        return _default_icon(size)

    # Try jumbo shell icon (256x256) via SHGetImageList
    icon = _extract_jumbo_shell_icon(filepath)
    if icon and not icon.isNull():
        return icon

    # Try QFileIconProvider
    icon = _provider.icon(QFileInfo(filepath))
    if not icon.isNull() and not _is_blank_icon(icon, size):
        return icon

    # For .lnk: resolve target and retry both methods
    if filepath.lower().endswith(".lnk"):
        target = _resolve_lnk_target(filepath)
        if target and os.path.exists(target):
            icon = _extract_jumbo_shell_icon(target)
            if icon and not icon.isNull():
                return icon
            icon = _provider.icon(QFileInfo(target))
            if not icon.isNull() and not _is_blank_icon(icon, size):
                return icon

    return _default_icon(size)


def _extract_jumbo_shell_icon(filepath):
    """Extract a 256x256 jumbo icon using Windows SHGetImageList."""
    try:
        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        comctl32 = ctypes.windll.comctl32

        # Get system icon index
        sfi = SHFILEINFOW()
        result = shell32.SHGetFileInfoW(
            filepath, 0, ctypes.byref(sfi), ctypes.sizeof(sfi),
            SHGFI_SYSICONINDEX
        )
        if not result:
            return None

        icon_index = sfi.iIcon

        # Try jumbo (256x256), then extra-large (48x48)
        for shil_type in (SHIL_JUMBO, SHIL_EXTRALARGE):
            image_list = ctypes.c_void_p()
            hr = shell32.SHGetImageList(
                shil_type, IID_IImageList, ctypes.byref(image_list)
            )
            if hr != 0 or not image_list.value:
                continue

            hicon = comctl32.ImageList_GetIcon(image_list, icon_index, 0x1)  # ILD_TRANSPARENT
            if not hicon:
                continue

            qicon = _hicon_to_qicon(hicon, user32, gdi32)
            user32.DestroyIcon(hicon)
            if qicon and not qicon.isNull() and not _is_blank_icon(qicon, 48):
                return qicon

        return None
    except Exception:
        return None


def _hicon_to_qicon(hicon, user32, gdi32):
    """Convert a Windows HICON to a QIcon using QtWin.fromHICON."""
    try:
        pixmap = QtWin.fromHICON(hicon)
        if pixmap.isNull():
            return None
        return QIcon(pixmap)
    except Exception:
        return None


def _is_blank_icon(icon, size):
    """Check if an icon is blank by sampling pixels."""
    pixmap = icon.pixmap(QSize(size, size))
    if pixmap.isNull():
        return True
    img = pixmap.toImage()
    if img.isNull():
        return True
    colors = set()
    step = max(1, size // 8)
    for x in range(0, min(size, img.width()), step):
        for y in range(0, min(size, img.height()), step):
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
        target = result.stdout.strip()
        return target if target else None
    except Exception:
        return None


def _default_icon(size):
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#1f6aa5"))
    return QIcon(pixmap)
