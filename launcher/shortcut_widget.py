"""Shortcut item with animated hover, drag-off-to-remove, and custom painting."""
import os

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QMenu
from PyQt5.QtCore import Qt, QPoint, QMimeData, QSize, pyqtSignal, pyqtProperty, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QDrag, QPixmap, QPainter, QFont, QColor, QCursor, QPen, QPainterPath

from .icon_provider import get_pixmap
from . import constants as C
from .constants import (
    ICON_SIZE, SHORTCUT_ITEM_HEIGHT, ACCENT_COLOR,
    TEXT_PRIMARY, TEXT_SECONDARY, HOVER_FADE_MS,
    FONT_FAMILY, FONT_SIZE_ITEM, GLASS_BG_SOLID,
)
from .scaling import s


class ShortcutItem(QWidget):
    """Single shortcut: icon + label with smooth animated hover."""

    removed = pyqtSignal(int)
    moved = pyqtSignal(int, int)
    launched = pyqtSignal(str)

    def __init__(self, index, path, name, parent=None):
        super().__init__(parent)
        self.index = index
        self.path = path
        self.name = name
        self._bg_alpha = 0.0
        self._drag_start = None

        icon_sz = s(C.ICON_SIZE)
        self.setFixedHeight(s(C.SHORTCUT_ITEM_HEIGHT))
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        # Hover animation - snappy transition
        self._hover_anim = QPropertyAnimation(self, b"bgAlpha")
        self._hover_anim.setDuration(80)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(s(10), s(4), s(10), s(4))
        layout.setSpacing(s(10))

        # Icon from cached 256x256 pixmap, scaled down with smooth transform
        source_pixmap = get_pixmap(path)
        icon_label = QLabel()
        # Use devicePixelRatio for retina sharpness: render at 2x, display at icon_sz
        dpr = 2.0
        hi_res_sz = int(icon_sz * dpr)
        scaled = source_pixmap.scaled(
            QSize(hi_res_sz, hi_res_sz),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        icon_label.setPixmap(scaled)
        icon_label.setFixedSize(icon_sz, icon_sz)
        icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(icon_label)

        # Name label - bright white, readable, scaled font
        name_label = QLabel(name)
        name_label.setStyleSheet(
            "QLabel {{ color: #ffffff; background: transparent; "
            "font-family: {}; font-size: {}px; font-weight: 500; }}".format(FONT_FAMILY, s(11))
        )
        name_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(name_label, 1)

    # ---- Animated hover via custom property ----

    def _get_bg_alpha(self):
        return self._bg_alpha

    def _set_bg_alpha(self, value):
        self._bg_alpha = value
        self.update()

    bgAlpha = pyqtProperty(float, _get_bg_alpha, _set_bg_alpha)

    def paintEvent(self, event):
        """Custom paint: rounded rect with animated alpha for hover."""
        if self._bg_alpha > 0.005:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            # Accent color at variable alpha
            alpha = int(self._bg_alpha * 50)
            color = QColor(59, 130, 246, alpha)
            painter.setBrush(color)
            # Subtle border at higher alpha
            if self._bg_alpha > 0.3:
                border_alpha = int(self._bg_alpha * 30)
                painter.setPen(QPen(QColor(59, 130, 246, border_alpha), 1))
            else:
                painter.setPen(Qt.NoPen)
            rect = self.rect().adjusted(2, 1, -2, -1)
            painter.drawRoundedRect(rect, 8, 8)
            painter.end()

    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._bg_alpha)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()

    def leaveEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._bg_alpha)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()

    # ---- Click / Drag ----

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()

    def mouseMoveEvent(self, event):
        if self._drag_start is None:
            return
        if (event.pos() - self._drag_start).manhattanLength() < 8:
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self.path)
        drag.setMimeData(mime)

        # Ghost pixmap
        ghost = QPixmap(180, 32)
        ghost.fill(QColor(0, 0, 0, 0))
        painter = QPainter(ghost)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(30, 41, 59, 220))
        painter.setPen(QPen(QColor(59, 130, 246, 100), 1))
        painter.drawRoundedRect(ghost.rect().adjusted(1, 1, -1, -1), 6, 6)
        painter.setPen(QColor(TEXT_PRIMARY))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(ghost.rect().adjusted(10, 0, -10, 0), Qt.AlignVCenter, self.name)
        painter.end()
        drag.setPixmap(ghost)
        drag.setHotSpot(QPoint(90, 16))

        drag.exec_(Qt.MoveAction)

        cursor_pos = QCursor.pos()
        main_win = self.window()
        if main_win and not main_win.geometry().contains(cursor_pos):
            self.removed.emit(self.index)

        self._drag_start = None

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_start is not None:
            self.launched.emit(self.path)
        self._drag_start = None

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu {{ background-color: {}; color: {}; border: 1px solid rgba(148,163,184,0.2); border-radius: 6px; padding: 4px; }}"
            "QMenu::item:selected {{ background-color: rgba(59,130,246,0.3); border-radius: 4px; }}".format(
                GLASS_BG_SOLID, TEXT_PRIMARY
            )
        )
        move_up = menu.addAction("Move Up")
        move_down = menu.addAction("Move Down")
        menu.addSeparator()
        remove = menu.addAction("Remove")

        action = menu.exec_(event.globalPos())
        if action == move_up:
            self.moved.emit(self.index, -1)
        elif action == move_down:
            self.moved.emit(self.index, 1)
        elif action == remove:
            self.removed.emit(self.index)
