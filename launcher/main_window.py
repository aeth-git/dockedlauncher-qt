"""Main DockedLauncher window - collapses to tab, expands to panel on hover."""
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFileDialog, QApplication,
)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect
from PyQt5.QtGui import QFont, QCursor, QColor

from .config import load_config, save_config
from .constants import (
    LEFT, RIGHT, TOP, BOTTOM,
    PANEL_WIDTH, HEADER_HEIGHT, BOTTOM_BAR_HEIGHT,
    ACCENT_COLOR, HEADER_COLOR, DARK_BG, DARK_BORDER, LIGHT_BG,
    TEXT_PRIMARY, TEXT_SECONDARY,
    HOVER_POLL_MS, LEAVE_POLLS_TO_COLLAPSE,
    ANIMATION_DURATION_MS, SNAP_ANIMATION_MS,
    EDGE_ARROWS, DEFAULT_OPACITY,
)
from . import dock_engine as de
from .shortcut_widget import ShortcutItem
from .animations import slide_widget, cancel_animation


class DockedLauncher(QWidget):
    """Single frameless window: tab when collapsed, full panel when expanded."""

    def __init__(self, config=None):
        super().__init__()
        self.config = config if config is not None else load_config()
        self._edge = self.config.get("dock_edge", LEFT)
        self._mon_idx = self.config.get("monitor", 0)
        self._is_expanded = False
        self._is_animating = False
        self._leave_count = 0
        self._drag_start = None
        self._is_dragging = False

        # Window flags
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool  # keeps off taskbar
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        self.setStyleSheet("DockedLauncher {{ background-color: {}; border: 1px solid {}; border-radius: 8px; }}".format(DARK_BG, DARK_BORDER))
        self.setWindowOpacity(self.config.get("opacity", DEFAULT_OPACITY))
        self.setAcceptDrops(True)

        # Build UI
        self._build_tab()
        self._build_panel()

        # Start collapsed
        self._collapse_to_tab()

        # Hover poll timer
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._check_hover)
        self._poll_timer.start(HOVER_POLL_MS)

    # ---- UI Construction ----

    def _build_tab(self):
        """Build the collapsed tab widget (arrow indicator)."""
        self._tab_widget = QWidget(self)
        self._tab_widget.setStyleSheet(
            "background-color: {}; border-radius: 4px;".format(ACCENT_COLOR))
        tab_layout = QVBoxLayout(self._tab_widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        self._tab_arrow = QLabel(EDGE_ARROWS.get(self._edge, "\u25B6"))
        self._tab_arrow.setAlignment(Qt.AlignCenter)
        self._tab_arrow.setStyleSheet("color: white; font-size: 8px; font-weight: bold; background: transparent;")
        tab_layout.addWidget(self._tab_arrow)

    def _build_panel(self):
        """Build the expanded panel with header, shortcuts, and bottom bar."""
        self._panel_widget = QWidget(self)
        self._panel_widget.setStyleSheet("background-color: {}; border-radius: 8px;".format(DARK_BG))
        panel_layout = QVBoxLayout(self._panel_widget)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Header (drag handle)
        self._header = QWidget()
        self._header.setFixedHeight(HEADER_HEIGHT)
        self._header.setStyleSheet("background-color: {}; border-top-left-radius: 8px; border-top-right-radius: 8px; border-bottom: 1px solid {};".format(HEADER_COLOR, DARK_BORDER))
        self._header.setCursor(Qt.OpenHandCursor)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(6, 0, 6, 0)
        title = QLabel("Launcher")
        title.setStyleSheet("color: {}; font-weight: 600; font-size: 9px; background: transparent; letter-spacing: 1px;".format(TEXT_SECONDARY))
        header_layout.addWidget(title)
        panel_layout.addWidget(self._header)

        # Scroll area for shortcuts
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._shortcut_container = QWidget()
        self._shortcut_layout = QVBoxLayout(self._shortcut_container)
        self._shortcut_layout.setContentsMargins(4, 4, 4, 4)
        self._shortcut_layout.setSpacing(2)
        self._shortcut_layout.addStretch()
        self._scroll.setWidget(self._shortcut_container)
        panel_layout.addWidget(self._scroll, 1)

        # Bottom bar
        bottom = QWidget()
        bottom.setFixedHeight(BOTTOM_BAR_HEIGHT)
        bottom.setStyleSheet("background-color: {}; border-top: 1px solid {}; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;".format(HEADER_COLOR, DARK_BORDER))
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(4, 4, 4, 4)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(24, 20)
        add_btn.setStyleSheet(self._button_style())
        add_btn.setFont(QFont("Segoe UI", 10, QFont.Bold))
        add_btn.clicked.connect(self._on_add_click)
        bottom_layout.addWidget(add_btn)

        bottom_layout.addStretch()

        settings_btn = QPushButton("\u2699")
        settings_btn.setFixedSize(24, 20)
        settings_btn.setStyleSheet(self._button_style())
        settings_btn.setFont(QFont("Segoe UI", 10))
        settings_btn.clicked.connect(self._on_settings_click)
        bottom_layout.addWidget(settings_btn)

        panel_layout.addWidget(bottom)

        # Populate shortcuts
        self._populate_shortcuts()

    def _button_style(self):
        return (
            "QPushButton {{ background-color: transparent; color: {1}; border: 1px solid {2}; border-radius: 4px; }}"
            "QPushButton:hover {{ background-color: {0}; color: white; border-color: {0}; }}"
        ).format(ACCENT_COLOR, TEXT_SECONDARY, DARK_BORDER)

    # ---- Shortcut List ----

    def _populate_shortcuts(self):
        """Rebuild shortcut widgets from config."""
        # Clear existing (except stretch)
        while self._shortcut_layout.count() > 1:
            item = self._shortcut_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        shortcuts = self.config.get("shortcuts", [])
        for i, sc in enumerate(shortcuts):
            widget = ShortcutItem(i, sc.get("path", ""), sc.get("name", ""), parent=self._shortcut_container)
            widget.removed.connect(self._remove_shortcut)
            widget.moved.connect(self._move_shortcut)
            widget.launched.connect(self._launch_shortcut)
            self._shortcut_layout.insertWidget(i, widget)

    def _remove_shortcut(self, index):
        shortcuts = self.config.get("shortcuts", [])
        if 0 <= index < len(shortcuts):
            shortcuts.pop(index)
            save_config(self.config)
            self._populate_shortcuts()
            if self._is_expanded:
                self._resize_panel()

    def _move_shortcut(self, index, direction):
        shortcuts = self.config.get("shortcuts", [])
        new_index = index + direction
        if 0 <= index < len(shortcuts) and 0 <= new_index < len(shortcuts):
            shortcuts[index], shortcuts[new_index] = shortcuts[new_index], shortcuts[index]
            save_config(self.config)
            self._populate_shortcuts()

    def _launch_shortcut(self, path):
        try:
            os.startfile(path)
        except OSError:
            pass

    def _on_add_click(self):
        filetypes = "Shortcuts & Executables (*.lnk *.bat *.exe *.cmd *.url);;All files (*.*)"
        filepath, _ = QFileDialog.getOpenFileName(self, "Add Shortcut", "", filetypes)
        if filepath:
            self._add_shortcut(filepath)

    def _add_shortcut(self, filepath):
        filepath = os.path.abspath(filepath)
        name = os.path.splitext(os.path.basename(filepath))[0]
        shortcuts = self.config.get("shortcuts", [])
        for s in shortcuts:
            if os.path.normcase(s["path"]) == os.path.normcase(filepath):
                return
        shortcuts.append({"path": filepath, "name": name})
        save_config(self.config)
        self._populate_shortcuts()
        if self._is_expanded:
            self._resize_panel()

    # ---- Tab / Panel States ----

    def _get_screen_rect(self):
        """Get the available geometry for the current monitor."""
        screens = de.get_screens()
        idx = min(self._mon_idx, len(screens) - 1)
        return screens[idx][1]

    def _collapse_to_tab(self):
        """Shrink to small tab at the docked edge."""
        self._panel_widget.hide()
        self._tab_widget.show()
        self._tab_arrow.setText(EDGE_ARROWS.get(self._edge, "\u25B6"))

        screen = self._get_screen_rect()
        offset = self.config.get("edge_offset", 0.5)
        rect = de.get_tab_rect(self._edge, offset, screen)
        self.setGeometry(rect)
        self._tab_widget.setGeometry(0, 0, rect.width(), rect.height())
        self._is_expanded = False

    def _expand_to_panel(self):
        """Grow to full panel at the docked edge."""
        self._is_expanded = True
        self._leave_count = 0

        self._tab_widget.hide()
        self._panel_widget.show()

        screen = self._get_screen_rect()
        offset = self.config.get("edge_offset", 0.5)
        num = len(self.config.get("shortcuts", []))
        rect = de.get_panel_rect(self._edge, offset, num, screen)
        self.setGeometry(rect)
        self._panel_widget.setGeometry(0, 0, rect.width(), rect.height())

    def _resize_panel(self):
        """Resize the expanded panel to fit current shortcuts."""
        if not self._is_expanded:
            return
        screen = self._get_screen_rect()
        offset = self.config.get("edge_offset", 0.5)
        num = len(self.config.get("shortcuts", []))
        rect = de.get_panel_rect(self._edge, offset, num, screen)
        self.setGeometry(rect)
        self._panel_widget.setGeometry(0, 0, rect.width(), rect.height())

    # ---- Hover Polling ----

    def _check_hover(self):
        if self._is_dragging or self._is_animating:
            self._leave_count = 0
            return

        cursor = QCursor.pos()
        geo = self.geometry()
        margin = 15
        expanded_geo = QRect(
            geo.x() - margin, geo.y() - margin,
            geo.width() + 2 * margin, geo.height() + 2 * margin
        )

        if not self._is_expanded and expanded_geo.contains(cursor):
            self._leave_count = 0
            self._expand_to_panel()
        elif self._is_expanded and not expanded_geo.contains(cursor):
            self._leave_count += 1
            if self._leave_count >= LEAVE_POLLS_TO_COLLAPSE:
                self._leave_count = 0
                self._collapse_to_tab()
        else:
            self._leave_count = 0

    # ---- Drag to Reposition (header) ----

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_expanded:
            # Check if click is on the header area
            header_geo = self._header.geometry()
            if header_geo.contains(event.pos()):
                self._drag_start = event.globalPos() - self.frameGeometry().topLeft()
                self._is_dragging = True
                self._header.setCursor(Qt.ClosedHandCursor)
                cancel_animation(self)

    def mouseMoveEvent(self, event):
        if self._is_dragging and self._drag_start is not None:
            self.move(event.globalPos() - self._drag_start)

    def mouseReleaseEvent(self, event):
        if not self._is_dragging:
            return
        self._is_dragging = False
        self._header.setCursor(Qt.OpenHandCursor)

        # Find nearest edge
        center = self.geometry().center()
        screens = de.get_screens()
        edge, mon_idx, offset = de.find_nearest_edge(center, screens)

        self._edge = edge
        self._mon_idx = mon_idx
        self.config["dock_edge"] = edge
        self.config["monitor"] = mon_idx
        self.config["edge_offset"] = round(offset, 3)
        save_config(self.config)

        # Animate snap to edge, then collapse
        screen = self._get_screen_rect()
        num = len(self.config.get("shortcuts", []))
        target_rect = de.get_panel_rect(edge, offset, num, screen)

        self._is_animating = True

        def after_snap():
            self._is_animating = False
            self._collapse_to_tab()

        slide_widget(self, self.geometry(), target_rect, SNAP_ANIMATION_MS, after_snap)

    # ---- Drag-and-Drop from Explorer ----

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            filepath = url.toLocalFile()
            if filepath and os.path.exists(filepath):
                self._add_shortcut(filepath)

    # ---- Settings ----

    def _on_settings_click(self):
        from .settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.config, parent=self)
        dialog.settings_changed.connect(self._apply_settings)
        dialog.exec_()

    def _apply_settings(self, new_config):
        self.config = new_config
        save_config(self.config)
        self.setWindowOpacity(self.config.get("opacity", DEFAULT_OPACITY))
        self._apply_theme()

        new_edge = self.config.get("dock_edge", LEFT)
        if new_edge != self._edge:
            self._edge = new_edge
            if self._is_expanded:
                self._expand_to_panel()
            else:
                self._collapse_to_tab()

    def _apply_theme(self):
        is_dark = self.config.get("theme", "dark") == "dark"
        bg = DARK_BG if is_dark else LIGHT_BG
        self._panel_widget.setStyleSheet("background-color: {};".format(bg))
        # Update shortcut items
        for i in range(self._shortcut_layout.count() - 1):  # -1 for stretch
            item = self._shortcut_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), ShortcutItem):
                item.widget().update_theme(is_dark)
