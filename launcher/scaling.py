"""UI scaling: bigger on lower-resolution screens for retina sharpness."""
from PyQt5.QtWidgets import QApplication

_cached_scale = None


def ui_scale():
    """Return UI scale factor based on screen height in logical pixels.

    Reference: 1440 logical pixels tall -> 1.0x scale.
    Smaller screens scale up, larger scale down within clamp range.
    """
    global _cached_scale
    if _cached_scale is not None:
        return _cached_scale

    app = QApplication.instance()
    if app is None:
        return 1.0

    screen = app.primaryScreen()
    if screen is None:
        return 1.0

    h = screen.availableGeometry().height()
    ref_h = 1440.0
    scale = ref_h / max(h, 1)
    # Clamp so we don't get absurdly large or small widgets
    _cached_scale = max(0.85, min(1.6, scale))
    return _cached_scale


def s(value):
    """Scale a numeric value by the UI scale factor, returning int."""
    return int(round(value * ui_scale()))
