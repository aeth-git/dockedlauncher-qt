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
    """Paints an app icon crisply, optionally dimmed for missing targets."""

    def __init__(self, path, size, parent=None, dimmed=False):
        super().__init__(parent)
        self._size = size
        self._dimmed = dimmed
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
        """Swiss flat: no shadow, no effect, just the icon rendered crisply.
        Dimmed items (missing targets) paint at 35% opacity."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if self._dimmed:
            painter.setOpacity(0.35)

        sz = self._size
        crisp = self._pix.scaled(
            QSize(sz, sz), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
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
        from .constants import PAPER, HOVER, INK, INK_MUTED, HAIRLINE
        self.index = index
        self.path = path
        self.name = name
        self._hovered = False
        self._drag_start = None
        # Target-existence is checked once at construct time; _populate_shortcuts
        # re-creates items on add/remove, so the state stays fresh for the
        # common case without per-paint filesystem calls.
        self._missing = bool(path) and not os.path.exists(path)

        if self._missing:
            self.setToolTip("Target not found:\n{}".format(path))
        elif path:
            self.setToolTip(path)

        icon_sz = s(C.ICON_SIZE)
        self.setFixedHeight(s(C.SHORTCUT_ITEM_HEIGHT))
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(s(14), s(6), s(14), s(6))
        layout.setSpacing(s(12))

        icon_holder = _IconCanvas(path, icon_sz, self, dimmed=self._missing)
        icon_holder.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(icon_holder)

        # Name label - black ink on white, Helvetica. Muted when target missing.
        label_color = INK_MUTED if self._missing else INK
        name_label = QLabel(name)
        name_label.setStyleSheet(
            "QLabel {{ color: {ink}; background: transparent; "
            "font-family: {font}; font-size: {sz}px; font-weight: 400; }}".format(
                ink=label_color, font=FONT_FAMILY, sz=s(12))
        )
        name_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(name_label, 1)

    def paintEvent(self, event):
        """Swiss minimal hover: solid gray background on hover, hairline divider
        drawn between items (skipped on the last item to avoid doubling with
        the bottom toolbar's own top hairline)."""
        from .constants import PAPER, HOVER, HAIRLINE
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        rect = self.rect()
        bg = QColor(HOVER) if self._hovered else QColor(PAPER)
        painter.fillRect(rect, bg)
        if not self._is_last_item():
            painter.setPen(QPen(QColor(HAIRLINE), 1))
            painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        painter.end()

    def _is_last_item(self):
        parent_layout = self.parent().layout() if self.parent() else None
        if parent_layout is None:
            return False
        last = None
        for i in range(parent_layout.count()):
            w = parent_layout.itemAt(i).widget()
            if isinstance(w, ShortcutItem):
                last = w
        return last is self

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

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

        # Ghost pixmap - Swiss style: white card, black text, thin border
        from .constants import PAPER, INK, HAIRLINE
        ghost = QPixmap(180, 32)
        ghost.fill(QColor(0, 0, 0, 0))
        painter = QPainter(ghost)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setBrush(QColor(PAPER))
        painter.setPen(QPen(QColor(INK), 1))
        painter.drawRect(ghost.rect().adjusted(0, 0, -1, -1))
        painter.setPen(QColor(INK))
        painter.setFont(QFont(FONT_FAMILY.split(",")[0].strip(), 10))
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
        from .constants import PAPER, INK, HOVER, HAIRLINE
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu {{ background-color: {paper}; color: {ink}; "
            "border: 1px solid {line}; border-radius: 0; padding: 4px; "
            "font-family: {font}; font-size: 11px; }}"
            "QMenu::item {{ padding: 4px 14px; }}"
            "QMenu::item:selected {{ background-color: {hover}; }}"
            "QMenu::separator {{ height: 1px; background: {line}; margin: 4px 0; }}".format(
                paper=PAPER, ink=INK, line=HAIRLINE, hover=HOVER, font=FONT_FAMILY
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
            from .constants import RED
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, False)
            # Swiss red drop indicator: sharp, bold, no decoration
            painter.setPen(QPen(QColor(RED), 2))
            y = int(self._drop_line_y)
            painter.drawLine(8, y, self.width() - 8, y)
            painter.end()
