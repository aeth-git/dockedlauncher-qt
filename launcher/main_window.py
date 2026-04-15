"""DockedLauncher - glassmorphism panel with acrylic blur, glow tab, drop shadow."""
import ctypes
import ctypes.wintypes
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFileDialog, QApplication, QGraphicsDropShadowEffect,
)
from PyQt5.QtCore import (
    Qt, QTimer, QPoint, QRect, QPropertyAnimation, QEasingCurve,
    pyqtProperty,
)
from PyQt5.QtGui import (
    QFont, QCursor, QColor, QPainter, QLinearGradient, QPen,
)

from .config import load_config, save_config
from . import constants as C
from .constants import (
    LEFT, RIGHT, TOP, BOTTOM,
    ACCENT_COLOR, ACCENT_LIGHT, HEADER_COLOR, HEADER_COLOR_SOLID,
    GLASS_BG, GLASS_BG_SOLID, GLASS_BORDER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    HOVER_POLL_MS, LEAVE_POLLS_TO_COLLAPSE,
    ANIMATION_DURATION_MS, SNAP_ANIMATION_MS,
    TAB_GLOW_PULSE_MS, SHADOW_BLUR, SHADOW_COLOR_RGBA, SHADOW_OFFSET,
    EDGE_ARROWS, DEFAULT_OPACITY,
    FONT_FAMILY, FONT_SIZE_TITLE, FONT_SIZE_BUTTON,
)
from . import dock_engine as de
from .shortcut_widget import ShortcutItem
from .animations import slide_widget, cancel_animation, pulse_loop
from .scaling import s
from .logger import get_logger

_log = get_logger("main_window")


# ---- Glow Tab ----

class GlowTab(QWidget):
    """Thin glowing tab with pulsing shadow effect."""

    def __init__(self, edge, parent=None):
        super().__init__(parent)
        self._edge = edge
        self.setAutoFillBackground(False)

    def set_edge(self, edge):
        self._edge = edge
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Bright gradient for high visibility
        if self._edge in (LEFT, RIGHT):
            grad = QLinearGradient(0, 0, 0, self.height())
        else:
            grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(ACCENT_LIGHT))
        grad.setColorAt(0.5, QColor(ACCENT_COLOR))
        grad.setColorAt(1.0, QColor(ACCENT_LIGHT))

        painter.setBrush(grad)
        # Bright white border so tab is easy to spot against any background
        painter.setPen(QPen(QColor(255, 255, 255, 220), 2))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 4, 4)
        painter.end()


# ---- Main Window ----

class DockedLauncher(QWidget):
    """Glassmorphism launcher: glow tab → acrylic panel on hover."""

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
        self._acrylic_enabled = False

        # Window flags
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowOpacity(self.config.get("opacity", DEFAULT_OPACITY))
        self.setAcceptDrops(True)

        # Build UI
        self._build_tab()
        self._build_panel()

        # Start collapsed
        self._collapse_to_tab()

        # Hover poll
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._check_hover)
        self._poll_timer.start(HOVER_POLL_MS)

    # ---- Acrylic Blur ----

    def _enable_acrylic_blur(self):
        """Enable Windows 10/11 acrylic blur behind the window."""
        try:
            class ACCENT_POLICY(ctypes.Structure):
                _fields_ = [
                    ("AccentState", ctypes.c_int),
                    ("AccentFlags", ctypes.c_int),
                    ("GradientColor", ctypes.c_uint),
                    ("AnimationId", ctypes.c_int),
                ]

            class WINCOMPATTRDATA(ctypes.Structure):
                _fields_ = [
                    ("Attribute", ctypes.c_int),
                    ("Data", ctypes.POINTER(ACCENT_POLICY)),
                    ("SizeOfData", ctypes.c_size_t),
                ]

            accent = ACCENT_POLICY()
            accent.AccentState = 4  # ACCENT_ENABLE_ACRYLICBLURBEHIND
            accent.AccentFlags = 2
            accent.GradientColor = 0xCC0F172A  # ~80% opacity dark slate (AABBGGRR)

            data = WINCOMPATTRDATA()
            data.Attribute = 19  # WCA_ACCENT_POLICY
            data.Data = ctypes.pointer(accent)
            data.SizeOfData = ctypes.sizeof(accent)

            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowCompositionAttributeW(hwnd, ctypes.byref(data))
            self._acrylic_enabled = True
            _log.info("Acrylic blur enabled")
        except Exception as e:
            self._acrylic_enabled = False
            _log.info("Acrylic blur not available: %s", e)

    def showEvent(self, event):
        """Enable acrylic after window is shown (HWND must exist)."""
        super().showEvent(event)
        if not self._acrylic_enabled:
            self._enable_acrylic_blur()
        # Keep WA_TranslucentBackground=True always. Child widgets (tab, panel)
        # paint their own solid backgrounds, so this just gives us rounded corners.

    # ---- UI Construction ----

    def _build_tab(self):
        self._tab_widget = GlowTab(self._edge, parent=self)

    def _build_panel(self):
        self._panel_widget = QWidget(self)
        self._panel_widget.setObjectName("panelRoot")
        self._panel_widget.setAutoFillBackground(True)
        # Solid opaque background; bright white border painted separately in paintEvent

        panel_layout = QVBoxLayout(self._panel_widget)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Header
        self._header = QWidget()
        self._header.setFixedHeight(s(C.HEADER_HEIGHT))
        self._header.setStyleSheet("background-color: {};".format(HEADER_COLOR_SOLID))
        self._header.setAutoFillBackground(True)
        self._header.setCursor(Qt.OpenHandCursor)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        title = QLabel("LAUNCHER")
        title.setStyleSheet(
            "color: {}; font-family: {}; font-weight: 600; font-size: {}px; "
            "letter-spacing: 2px; background: transparent;".format(
                TEXT_MUTED, FONT_FAMILY, FONT_SIZE_TITLE
            )
        )
        header_layout.addWidget(title)
        panel_layout.addWidget(self._header)

        # Separator line
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: {};".format(GLASS_BORDER))
        panel_layout.addWidget(sep)

        # Scroll area - explicit dark background
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(
            "QScrollArea {{ border: none; background-color: {0}; }}"
            "QScrollArea > QWidget > QWidget {{ background-color: {0}; }}"
            "QScrollBar:vertical {{ background: {0}; width: 6px; margin: 2px; border: none; }}"
            "QScrollBar::handle:vertical {{ background: rgba(148,163,184,0.4); border-radius: 3px; min-height: 20px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; background: transparent; }}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: {0}; }}".format(GLASS_BG_SOLID)
        )
        self._shortcut_container = QWidget()
        self._shortcut_container.setStyleSheet(
            "background-color: {};".format(GLASS_BG_SOLID)
        )
        self._shortcut_container.setAutoFillBackground(True)
        self._shortcut_layout = QVBoxLayout(self._shortcut_container)
        self._shortcut_layout.setContentsMargins(6, 6, 6, 6)
        self._shortcut_layout.setSpacing(2)
        self._shortcut_layout.addStretch()
        self._scroll.setWidget(self._shortcut_container)
        panel_layout.addWidget(self._scroll, 1)

        # Bottom separator
        sep2 = QWidget()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background-color: {};".format(GLASS_BORDER))
        panel_layout.addWidget(sep2)

        # Bottom bar - solid dark
        bottom = QWidget()
        bottom.setFixedHeight(s(C.BOTTOM_BAR_HEIGHT))
        bottom.setStyleSheet("background-color: {};".format(GLASS_BG_SOLID))
        bottom.setAutoFillBackground(True)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(8, 4, 8, 4)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(26, 22)
        add_btn.setStyleSheet(self._button_style())
        add_btn.setFont(QFont(FONT_FAMILY, FONT_SIZE_BUTTON, QFont.Bold))
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_click)
        bottom_layout.addWidget(add_btn)

        bottom_layout.addStretch()

        settings_btn = QPushButton("\u2699")
        settings_btn.setFixedSize(26, 22)
        settings_btn.setStyleSheet(self._button_style())
        settings_btn.setFont(QFont(FONT_FAMILY, FONT_SIZE_BUTTON))
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.clicked.connect(self._on_settings_click)
        bottom_layout.addWidget(settings_btn)

        panel_layout.addWidget(bottom)

        self._populate_shortcuts()

    def _button_style(self):
        return (
            "QPushButton {{ background: transparent; color: {1}; "
            "border: 1px solid {2}; border-radius: 4px; padding: 1px; }}"
            "QPushButton:hover {{ background: rgba(59,130,246,0.25); color: white; "
            "border-color: {0}; }}"
        ).format(ACCENT_COLOR, TEXT_SECONDARY, GLASS_BORDER)

    def paintEvent(self, event):
        """Paint the glassmorphism background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._is_expanded:
            # Panel background
            if self._acrylic_enabled:
                bg = QColor(15, 23, 42, 225)
            else:
                bg = QColor(15, 23, 42, 255)
            painter.setBrush(bg)
            # Bright white border around entire expanded panel
            painter.setPen(QPen(QColor(255, 255, 255, 230), 2))
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 10, 10)

        painter.end()

    # ---- Shortcut List ----

    def _populate_shortcuts(self):
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
        if not os.path.exists(path):
            _log.warning("Shortcut target not found: %s", path)
            return
        try:
            os.startfile(path)
        except OSError as e:
            _log.error("Failed to launch %s: %s", path, e)

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
        screens = de.get_screens()
        idx = max(0, min(self._mon_idx, len(screens) - 1))
        return screens[idx][1]

    def _collapse_to_tab(self, animate=True):
        screen = self._get_screen_rect()
        offset = self.config.get("edge_offset", 0.5)
        target = de.get_tab_rect(self._edge, offset, screen)

        if not animate or not self._is_expanded:
            self._panel_widget.hide()
            self._tab_widget.show()
            self._tab_widget.set_edge(self._edge)
            self.setGeometry(target)
            self._tab_widget.setGeometry(0, 0, target.width(), target.height())
            self._is_expanded = False
            return

        # Animate shrink; show tab on top during animation
        self._tab_widget.set_edge(self._edge)
        self._tab_widget.setGeometry(0, 0, target.width(), target.height())
        self._tab_widget.show()
        self._tab_widget.raise_()
        self._is_animating = True
        self._is_expanded = False

        def on_done():
            self._panel_widget.hide()
            self._is_animating = False

        self._panel_widget.lower()
        self._animate_to(target, duration=140, on_done=on_done)

    def _expand_to_panel(self):
        self._leave_count = 0
        screen = self._get_screen_rect()
        offset = self.config.get("edge_offset", 0.5)
        num = len(self.config.get("shortcuts", []))
        target = de.get_panel_rect(self._edge, offset, num, screen)

        # Pre-size and show the panel widget so its content appears immediately
        self._panel_widget.setGeometry(0, 0, target.width(), target.height())
        self._panel_widget.show()
        self._tab_widget.hide()
        self._is_animating = True

        def on_done():
            self._is_animating = False
            self._is_expanded = True
            self.update()

        self._animate_to(target, duration=160, on_done=on_done)
        # Mark expanded immediately so hover poll doesn't re-trigger
        self._is_expanded = True

    def _animate_to(self, target_rect, duration=160, on_done=None):
        """Smooth fast geometry animation."""
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(duration)
        anim.setStartValue(self.geometry())
        anim.setEndValue(target_rect)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        # Keep panel widget sized to current animated geometry
        anim.valueChanged.connect(lambda r: self._panel_widget.setGeometry(0, 0, r.width(), r.height()) if self._panel_widget.isVisible() else None)
        if on_done:
            anim.finished.connect(on_done)
        self._geom_anim = anim
        anim.start()

    def _resize_panel(self):
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

    # ---- Drag to Reposition ----

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_expanded:
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

        center = self.geometry().center()
        screens = de.get_screens()
        edge, mon_idx, offset = de.find_nearest_edge(center, screens)

        self._edge = edge
        self._mon_idx = mon_idx
        self.config["dock_edge"] = edge
        self.config["monitor"] = mon_idx
        self.config["edge_offset"] = round(offset, 3)
        save_config(self.config)

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
        # Reuse if already open
        if getattr(self, '_settings_dialog', None) and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        # Keep a reference on self so Python doesn't GC the window
        self._settings_dialog = SettingsDialog(self.config, parent=None)
        self._settings_dialog.settings_changed.connect(self._apply_settings)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _apply_settings(self, new_config):
        self.config = new_config
        save_config(self.config)
        self.setWindowOpacity(self.config.get("opacity", DEFAULT_OPACITY))

        new_edge = self.config.get("dock_edge", LEFT)
        if new_edge != self._edge:
            self._edge = new_edge
            if self._is_expanded:
                self._expand_to_panel()
            else:
                self._collapse_to_tab()
