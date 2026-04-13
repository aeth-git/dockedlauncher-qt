"""QPropertyAnimation helpers for smooth slide transitions."""
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
    # Store reference on widget to prevent garbage collection
    widget._current_anim = anim
    anim.start()
    return anim


def cancel_animation(widget):
    """Stop any running animation on the widget."""
    anim = getattr(widget, '_current_anim', None)
    if anim and anim.state() == QPropertyAnimation.Running:
        anim.stop()
    widget._current_anim = None
