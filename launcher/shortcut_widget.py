"""Individual shortcut item widget with hover, click, drag-off-to-remove."""
import os

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QMenu, QApplication
from PyQt5.QtCore import Qt, QPoint, QMimeData, QSize, pyqtSignal
from PyQt5.QtGui import QDrag, QPixmap, QPainter, QFont, QColor, QCursor

from .icon_provider import get_icon
from .constants import ICON_SIZE, SHORTCUT_ITEM_HEIGHT, HOVER_COLOR, DARK_ITEM_BG, ACCENT_COLOR, TEXT_PRIMARY, DARK_BORDER


class ShortcutItem(QWidget):
    """A single shortcut entry: icon + label with interactions."""

    removed = pyqtSignal(int)       # emitted with index when removed
    moved = pyqtSignal(int, int)    # emitted with (index, direction) for reorder
    launched = pyqtSignal(str)      # emitted with path when clicked

    def __init__(self, index, path, name, parent=None):
        super().__init__(parent)
        self.index = index
        self.path = path
        self.name = name

        self.setFixedHeight(SHORTCUT_ITEM_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self._default_style = "ShortcutItem, ShortcutItem * {{ background-color: transparent; border-radius: 6px; }}"
        self._hover_style = "ShortcutItem, ShortcutItem * {{ background-color: {}; border-radius: 6px; }}".format(HOVER_COLOR)
        self.setStyleSheet(self._default_style)

        self._drag_start = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Icon - get largest available, then scale down to fit with smooth transform
        icon = get_icon(path, ICON_SIZE)
        icon_label = QLabel()
        # Request large pixmap for best quality source
        pixmap = icon.pixmap(QSize(256, 256))
        # Scale to display size with smooth filtering
        scaled = pixmap.scaled(
            QSize(ICON_SIZE, ICON_SIZE),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        icon_label.setPixmap(scaled)
        icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        icon_label.setScaledContents(False)
        layout.addWidget(icon_label)

        # Name
        name_label = QLabel(name)
        name_label.setStyleSheet("color: {};".format(TEXT_PRIMARY))
        name_label.setFont(QFont("Segoe UI", 8))
        layout.addWidget(name_label, 1)

    def enterEvent(self, event):
        self.setStyleSheet(self._hover_style)

    def leaveEvent(self, event):
        self.setStyleSheet(self._default_style)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()

    def mouseMoveEvent(self, event):
        if self._drag_start is None:
            return
        if (event.pos() - self._drag_start).manhattanLength() < 8:
            return

        # Start drag-off-to-remove
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self.path)
        drag.setMimeData(mime)

        # Create ghost pixmap
        ghost = QPixmap(160, 30)
        ghost.fill(QColor(DARK_ITEM_BG))
        painter = QPainter(ghost)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(ghost.rect(), Qt.AlignCenter, self.name)
        painter.end()
        drag.setPixmap(ghost)
        drag.setHotSpot(QPoint(80, 15))

        result = drag.exec_(Qt.MoveAction)

        # If drag ended outside the main window, remove this shortcut
        cursor_pos = QCursor.pos()
        main_win = self.window()
        if main_win:
            win_rect = main_win.geometry()
            if not win_rect.contains(cursor_pos):
                self.removed.emit(self.index)

        self._drag_start = None

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_start is not None:
            # Normal click (no drag) - launch
            self.launched.emit(self.path)
        self._drag_start = None

    def contextMenuEvent(self, event):
        menu = QMenu(self)
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

    def update_theme(self, is_dark):
        bg = DARK_ITEM_BG if is_dark else "#e8e8e8"
        hover = HOVER_COLOR if is_dark else "#a0c4e8"
        text_color = "white" if is_dark else "black"
        self._default_style = "background-color: {}; border-radius: 6px;".format(bg)
        self._hover_style = "background-color: {}; border-radius: 6px;".format(hover)
        self.setStyleSheet(self._default_style)
        for label in self.findChildren(QLabel):
            if not label.pixmap():
                label.setStyleSheet("color: {}; background: transparent;".format(text_color))
