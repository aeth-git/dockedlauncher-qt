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


class _IconCanvas(QWidget):
    """Paints an app icon crisply with a subtle drop-shadow for depth."""

    def __init__(self, path, size, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        # Render source at high-DPI (3x) then scale down for retina sharpness
        src = get_pixmap(path)
        target = int(size * 3)
        if not src.isNull():
            self._pix = src.scaled(
                QSize(target, target),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        else:
            self._pix = QPixmap(size, size)
            self._pix.fill(Qt.transparent)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        sz = self._size
        # Draw soft shadow slightly below and behind the icon (2 layers)
        shadow_pix = self._pix.scaled(
            QSize(sz, sz), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        # Create a tinted black silhouette for shadow
        shadow_img = shadow_pix.toImage()
        for layer, (ox, oy, alpha) in enumerate([(0, 2, 30), (0, 1, 50)]):
            sh = QPixmap(shadow_pix.size())
            sh.fill(Qt.transparent)
            sp = QPainter(sh)
            sp.setRenderHint(QPainter.SmoothPixmapTransform, True)
            sp.drawPixmap(0, 0, shadow_pix)
            sp.setCompositionMode(QPainter.CompositionMode_SourceIn)
            sp.fillRect(sh.rect(), QColor(0, 0, 0, alpha))
            sp.end()
            painter.drawPixmap(ox, oy, sh)

        # Draw the actual icon crisply on top
        crisp = self._pix.scaled(
            QSize(sz, sz), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        # Center in case aspect ratio changed
        dx = (sz - crisp.width()) // 2
        dy = (sz - crisp.height()) // 2
        painter.drawPixmap(dx, dy, crisp)
        painter.end()


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

        # Icon: painted icon with subtle drop shadow and hi-res rendering
        icon_holder = _IconCanvas(path, icon_sz, self)
        icon_holder.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(icon_holder)

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

    MIME_TYPE = "application/x-dockedlauncher-shortcut"

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
        # Custom mime type carries the source index for reorder detection
        mime.setData(self.MIME_TYPE, str(self.index).encode())
        mime.setText(self.path)  # fallback for external drops
        drag.setMimeData(mime)

        # Ghost pixmap
        ghost = QPixmap(180, 32)
        ghost.fill(QColor(0, 0, 0, 0))
        painter = QPainter(ghost)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(30, 41, 59, 220))
        painter.setPen(QPen(QColor(59, 130, 246, 180), 1))
        painter.drawRoundedRect(ghost.rect().adjusted(1, 1, -1, -1), 6, 6)
        painter.setPen(QColor(TEXT_PRIMARY))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(ghost.rect().adjusted(10, 0, -10, 0), Qt.AlignVCenter, self.name)
        painter.end()
        drag.setPixmap(ghost)
        drag.setHotSpot(QPoint(90, 16))

        # Accept MoveAction (reorder) or IgnoreAction (drop outside)
        result = drag.exec_(Qt.MoveAction)

        # If drop was accepted internally (reorder), container emits the signal.
        # If drop was NOT accepted and cursor is outside main window, remove.
        if result == Qt.IgnoreAction:
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


class ShortcutContainer(QWidget):
    """Container that accepts ShortcutItem drops for reordering with live indicator."""

    reorder = pyqtSignal(int, int)  # (from_index, to_index)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._drop_line_y = None  # where to draw the drop indicator

    def _compute_target_index(self, y):
        """Return the insert index for a drop at the given y within this container."""
        children = [
            self.layout().itemAt(i).widget()
            for i in range(self.layout().count())
            if self.layout().itemAt(i).widget() is not None
            and isinstance(self.layout().itemAt(i).widget(), ShortcutItem)
        ]
        for i, item in enumerate(children):
            item_y = item.y() + item.height() / 2
            if y < item_y:
                return i, item.y()
        # After all items - insert at end
        if children:
            last = children[-1]
            return len(children), last.y() + last.height()
        return 0, 0

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(ShortcutItem.MIME_TYPE):
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(ShortcutItem.MIME_TYPE):
            _, line_y = self._compute_target_index(event.pos().y())
            if line_y != self._drop_line_y:
                self._drop_line_y = line_y
                self.update()
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._drop_line_y = None
        self.update()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(ShortcutItem.MIME_TYPE):
            event.ignore()
            return
        try:
            from_index = int(bytes(event.mimeData().data(ShortcutItem.MIME_TYPE)).decode())
        except (ValueError, TypeError):
            event.ignore()
            return

        target_index, _ = self._compute_target_index(event.pos().y())
        # If dragging down past self, list shortens by 1 after remove -> adjust
        if target_index > from_index:
            target_index -= 1

        self._drop_line_y = None
        self.update()

        if target_index != from_index:
            self.reorder.emit(from_index, target_index)
        event.setDropAction(Qt.MoveAction)
        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_line_y is not None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            # Bright drop indicator line
            pen = QPen(QColor(120, 200, 255, 220), 2)
            painter.setPen(pen)
            y = int(self._drop_line_y)
            painter.drawLine(8, y, self.width() - 8, y)
            # End caps (small circles)
            painter.setBrush(QColor(180, 220, 255, 220))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPoint(8, y), 3, 3)
            painter.drawEllipse(QPoint(self.width() - 8, y), 3, 3)
            painter.end()
