"""Animation helpers: slide, fade, pulse."""
from PyQt5.QtCore import QPropertyAnimation, QRect, QEasingCurve


def slide_widget(widget, start_rect, end_rect, duration_ms=300, callback=None):
    """Animate a widget's geometry from start_rect to end_rect."""
    anim = QPropertyAnimation(widget, b"geometry")
    anim.setDuration(duration_ms)
    anim.setStartValue(start_rect)
    anim.setEndValue(end_rect)
    anim.setEasingCurve(QEasingCurve.InOutCubic)
    if callback:
        anim.finished.connect(callback)
    widget._current_anim = anim
    anim.start()
    return anim


def cancel_animation(widget):
    """Stop any running animation on the widget."""
    anim = getattr(widget, '_current_anim', None)
    if anim and anim.state() == QPropertyAnimation.Running:
        anim.stop()
    widget._current_anim = None


def fade_property(widget, prop_name, start, end, duration_ms=150, callback=None):
    """Animate any numeric property (opacity, alpha, blur radius)."""
    anim = QPropertyAnimation(widget, prop_name.encode() if isinstance(prop_name, str) else prop_name)
    anim.setDuration(duration_ms)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.InOutQuad)
    if callback:
        anim.finished.connect(callback)
    if not hasattr(widget, '_anims'):
        widget._anims = []
    widget._anims.append(anim)
    anim.finished.connect(lambda: widget._anims.remove(anim) if anim in getattr(widget, '_anims', []) else None)
    anim.start()
    return anim


def pulse_loop(effect, prop_name, low, high, duration_ms=3000):
    """Create an infinitely looping pulse animation."""
    anim = QPropertyAnimation(effect, prop_name.encode() if isinstance(prop_name, str) else prop_name)
    anim.setDuration(duration_ms)
    anim.setKeyValueAt(0.0, low)
    anim.setKeyValueAt(0.5, high)
    anim.setKeyValueAt(1.0, low)
    anim.setEasingCurve(QEasingCurve.InOutSine)
    anim.setLoopCount(-1)
    effect._pulse_anim = anim
    anim.start()
    return anim
