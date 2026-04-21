"""Windows global hotkey registration via WinAPI RegisterHotKey.

A single HotkeyManager registers hotkeys with the current thread (hWnd=0)
and installs a QAbstractNativeEventFilter that catches WM_HOTKEY messages
from Qt's message pump and dispatches them to the registered callback.

Thread-bound hotkeys fire regardless of which window has focus system-wide,
so the launcher can be summoned from anywhere.
"""
import ctypes
import ctypes.wintypes

from PyQt5.QtCore import QAbstractNativeEventFilter

from .logger import get_logger

_log = get_logger("hotkey")

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_SPACE = 0x20


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        # event_type is bytes on PyQt5: b'windows_generic_MSG' (or '...dispatcher_MSG')
        et = event_type if isinstance(event_type, str) else event_type.decode(errors="ignore")
        if "windows_" in et and "_MSG" in et:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                try:
                    self._callback(int(msg.wParam))
                except Exception as e:
                    _log.warning("Hotkey callback failed: %s", e)
        return False, 0


class HotkeyManager:
    """Register/unregister Windows global hotkeys for the Qt main thread."""

    def __init__(self, app, callback):
        """app: QApplication instance. callback: fn(hotkey_id:int) -> None."""
        self._app = app
        self._filter = _HotkeyFilter(callback)
        self._app.installNativeEventFilter(self._filter)
        self._registered = []  # list of hotkey ids we own

    def register(self, hotkey_id, mods, vk):
        """Register one hotkey. Returns True on success, False if already taken."""
        user32 = ctypes.windll.user32
        ok = user32.RegisterHotKey(None, hotkey_id, mods | MOD_NOREPEAT, vk)
        if ok:
            self._registered.append(hotkey_id)
            _log.info("Registered hotkey id=%d mods=0x%x vk=0x%x", hotkey_id, mods, vk)
            return True
        _log.warning("RegisterHotKey failed (id=%d, mods=0x%x, vk=0x%x) — "
                     "another app may own this combination", hotkey_id, mods, vk)
        return False

    def unregister_all(self):
        user32 = ctypes.windll.user32
        for hid in self._registered:
            user32.UnregisterHotKey(None, hid)
        self._registered.clear()
        if self._app is not None:
            self._app.removeNativeEventFilter(self._filter)
