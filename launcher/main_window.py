"""DockedLauncher - glassmorphism panel with acrylic blur, glow tab, drop shadow."""
import ctypes
import ctypes.wintypes
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFileDialog, QApplication, QGraphicsDropShadowEffect,
)
from PyQt5.QtCore import (
    Qt, QTimer, QPoint, QPointF, QRect, QRectF, QPropertyAnimation, QEasingCurve,
    pyqtProperty,
)
from PyQt5.QtGui import (
    QFont, QCursor, QColor, QPainter, QLinearGradient, QPen, QPainterPath,
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
    """Animated pill-shaped tab with chrome gradient, pulsing energy core, and scan line."""

    def __init__(self, edge, parent=None):
        super().__init__(parent)
        self._edge = edge
        self._t = 0.0
        self.setAutoFillBackground(False)

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(40)  # ~25fps

    def _tick(self):
        self._t += 0.05
        if self.isVisible():
            self.update()

    def set_edge(self, edge):
        self._edge = edge
        self.update()

    def paintEvent(self, event):
        import math
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect()
        w, h = rect.width(), rect.height()
        is_vertical = self._edge in (LEFT, RIGHT)

        # ---- Bright vibrant base body ----
        if is_vertical:
            base = QLinearGradient(0, 0, w, 0)
        else:
            base = QLinearGradient(0, 0, 0, h)
        # Much more saturated and vibrant - electric cyan/blue
        base.setColorAt(0.0, QColor(20, 80, 180))
        base.setColorAt(0.3, QColor(30, 140, 255))
        base.setColorAt(0.5, QColor(120, 220, 255))   # near-white core
        base.setColorAt(0.7, QColor(30, 140, 255))
        base.setColorAt(1.0, QColor(20, 80, 180))
        painter.setBrush(base)
        painter.setPen(Qt.NoPen)

        radius = min(w, h) / 2.0
        painter.drawRoundedRect(rect, radius, radius)

        # ---- DRAMATIC pulsing core - strong bright flash ----
        # Combine slow base pulse with occasional attention flash
        slow = 0.5 + 0.5 * math.sin(self._t * 2.5)
        # Sharp flash every ~2.5s to grab attention
        flash_phase = math.fmod(self._t, 2.5)
        flash = max(0, 1.0 - flash_phase * 2.0) ** 3  # sharp decay 0->1 over 0.5s
        pulse = min(1.0, slow * 0.5 + flash)

        # Full-body brightness overlay
        painter.setBrush(QColor(255, 255, 255, int(80 * pulse)))
        painter.drawRoundedRect(rect, radius, radius)

        # ---- Traveling bright highlight band ----
        band_t = math.fmod(self._t * 0.6, 1.0)
        if is_vertical:
            pos = h * band_t
            hi = QLinearGradient(0, pos - 12, 0, pos + 12)
        else:
            pos = w * band_t
            hi = QLinearGradient(pos - 12, 0, pos + 12, 0)
        hi.setColorAt(0.0, QColor(255, 255, 255, 0))
        hi.setColorAt(0.5, QColor(255, 255, 255, 220))
        hi.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(hi)
        painter.drawRoundedRect(rect, radius, radius)

        # ---- Strong white border ring (high-contrast) ----
        border_pulse = 0.7 + 0.3 * math.sin(self._t * 3.0)
        painter.setPen(QPen(QColor(255, 255, 255, int(255 * border_pulse)), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius - 1, radius - 1)

        # ---- Second inner ring for extra definition ----
        painter.setPen(QPen(QColor(180, 230, 255, 160), 1))
        painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), max(1, radius - 3), max(1, radius - 3))

        # ---- Chevron indicator (points inward toward docked edge) ----
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        cx, cy = w / 2, h / 2
        ch = min(w, h) * 0.22
        if self._edge == LEFT:
            # ">" pointing right
            path = QPainterPath()
            path.moveTo(cx - ch * 0.4, cy - ch)
            path.lineTo(cx + ch * 0.4, cy)
            path.lineTo(cx - ch * 0.4, cy + ch)
        elif self._edge == RIGHT:
            # "<" pointing left
            path = QPainterPath()
            path.moveTo(cx + ch * 0.4, cy - ch)
            path.lineTo(cx - ch * 0.4, cy)
            path.lineTo(cx + ch * 0.4, cy + ch)
        elif self._edge == TOP:
            # V pointing down
            path = QPainterPath()
            path.moveTo(cx - ch, cy - ch * 0.4)
            path.lineTo(cx, cy + ch * 0.4)
            path.lineTo(cx + ch, cy - ch * 0.4)
        else:
            # ^ pointing up
            path = QPainterPath()
            path.moveTo(cx - ch, cy + ch * 0.4)
            path.lineTo(cx, cy - ch * 0.4)
            path.lineTo(cx + ch, cy + ch * 0.4)
        painter.drawPath(path)

        painter.end()


# ---- Sci-Fi Bottom Bar ----

class _BottomBar(QWidget):
    """Custom-painted bottom toolbar with sci-fi styling."""

    def __init__(self, on_add, on_settings, parent=None):
        super().__init__(parent)
        self._t = 0.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(28, 22)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(
            "QPushButton { background: rgba(60,160,255,0.1); color: rgba(140,200,255,0.8); "
            "border: 1px solid rgba(60,160,255,0.3); border-radius: 4px; "
            "font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: rgba(60,160,255,0.3); color: white; "
            "border-color: rgba(100,180,255,0.6); }"
        )
        add_btn.clicked.connect(on_add)
        layout.addWidget(add_btn)

        layout.addStretch()

        settings_btn = QPushButton("\u2699")
        settings_btn.setFixedSize(28, 22)
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.setStyleSheet(
            "QPushButton { background: rgba(60,160,255,0.1); color: rgba(140,200,255,0.8); "
            "border: 1px solid rgba(60,160,255,0.3); border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background: rgba(60,160,255,0.3); color: white; "
            "border-color: rgba(100,180,255,0.6); }"
        )
        settings_btn.clicked.connect(on_settings)
        layout.addWidget(settings_btn)

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(40)

    def _tick(self):
        self._t += 0.04
        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        import math
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Dark gradient background
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(15, 25, 45))
        grad.setColorAt(0.5, QColor(20, 32, 52))
        grad.setColorAt(1.0, QColor(25, 40, 65))
        painter.fillRect(0, 0, w, h, grad)

        # Top separator: energy line
        pulse = 0.6 + 0.4 * math.sin(self._t * 2.8 + 1)
        a = int(60 * pulse)
        line_grad = QLinearGradient(0, 0, w, 0)
        line_grad.setColorAt(0.0, QColor(60, 160, 255, 0))
        line_grad.setColorAt(0.3, QColor(60, 160, 255, a))
        line_grad.setColorAt(0.5, QColor(180, 220, 255, int(a * 1.3)))
        line_grad.setColorAt(0.7, QColor(60, 160, 255, a))
        line_grad.setColorAt(1.0, QColor(60, 160, 255, 0))
        painter.setPen(QPen(line_grad, 1))
        painter.drawLine(0, 0, w, 0)

        # Bottom highlight
        painter.setPen(QPen(QColor(100, 170, 255, 30), 1))
        painter.drawLine(0, h - 1, w, h - 1)

        painter.end()


# ---- Sci-Fi Header Bar ----

class _HeaderBar(QWidget):
    """Custom-painted header with chrome gradient, animated scan line, and glow title."""

    def __init__(self, on_close, parent=None):
        super().__init__(parent)
        self._on_close = on_close
        self._t = 0.0  # animation time

        # Close button overlaid on top
        self._close_btn = QPushButton("\u2715", self)
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setToolTip("Close DockedLauncher")
        self._close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: rgba(255,255,255,0.5); "
            "border: none; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { color: #ff4444; }"
        )
        self._close_btn.clicked.connect(on_close)

        # Animation timer
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(40)  # ~25fps

    def _tick(self):
        self._t += 0.04
        if self.isVisible():
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position close button at top-right
        self._close_btn.move(self.width() - 24, (self.height() - 20) // 2)

    def paintEvent(self, event):
        import math
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Chrome gradient background
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(35, 50, 75))
        grad.setColorAt(0.4, QColor(25, 38, 60))
        grad.setColorAt(0.6, QColor(20, 32, 52))
        grad.setColorAt(1.0, QColor(15, 25, 45))
        painter.fillRect(0, 0, w, h, grad)

        # Top highlight edge (thin bright line)
        painter.setPen(QPen(QColor(120, 180, 255, 60), 1))
        painter.drawLine(0, 0, w, 0)

        # Animated horizontal scan line (sweeps left to right, repeats)
        scan_x = (self._t * 80) % (w + 60) - 30
        scan_grad = QLinearGradient(scan_x - 30, 0, scan_x + 30, 0)
        scan_grad.setColorAt(0.0, QColor(80, 180, 255, 0))
        scan_grad.setColorAt(0.5, QColor(80, 180, 255, 50))
        scan_grad.setColorAt(1.0, QColor(80, 180, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(scan_grad)
        painter.drawRect(0, 0, w, h)

        # Bottom separator: glowing energy line
        pulse = 0.6 + 0.4 * math.sin(self._t * 3)
        line_grad = QLinearGradient(0, 0, w, 0)
        a = int(80 * pulse)
        line_grad.setColorAt(0.0, QColor(60, 160, 255, 0))
        line_grad.setColorAt(0.3, QColor(60, 160, 255, a))
        line_grad.setColorAt(0.5, QColor(180, 220, 255, int(a * 1.5)))
        line_grad.setColorAt(0.7, QColor(60, 160, 255, a))
        line_grad.setColorAt(1.0, QColor(60, 160, 255, 0))
        painter.setPen(QPen(line_grad, 1.5))
        painter.drawLine(0, h - 1, w, h - 1)

        # Title text: "LAUNCHER" with glow
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        text_x = 12
        text_y = h // 2 + 4

        # Text glow (drawn slightly larger behind)
        glow_a = int(40 * pulse)
        painter.setPen(QColor(80, 180, 255, glow_a))
        for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            painter.drawText(text_x + ox, text_y + oy, "L A U N C H E R")

        # Main text
        text_grad = QLinearGradient(text_x, 0, text_x + 120, 0)
        text_grad.setColorAt(0.0, QColor(140, 180, 220))
        text_grad.setColorAt(0.5, QColor(200, 220, 255))
        text_grad.setColorAt(1.0, QColor(140, 180, 220))
        painter.setPen(QPen(text_grad, 1))
        painter.drawText(text_x, text_y, "L A U N C H E R")

        # Small decorative dots (status indicators)
        for i, dx in enumerate([w - 50, w - 58, w - 66]):
            dot_pulse = 0.5 + 0.5 * math.sin(self._t * 2.5 + i * 1.2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(60, 200, 120, int(160 * dot_pulse)))
            painter.drawEllipse(QPointF(dx, h // 2), 2, 2)

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
        self._glow_pad = 0  # no external glow padding in v3
        self._clamp_val = 0.0

        # Window flags - no translucent background (too fragile on some systems)
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet("DockedLauncher { background-color: #0f172a; }")
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

        # Tendril animation timer (~30fps repaint when expanded)
        self._tendril_timer = QTimer(self)
        self._tendril_timer.timeout.connect(self._tendril_tick)
        self._tendril_timer.start(33)

        # Safety net: 500ms after init, verify tab is actually on a screen.
        # If not, snap to left-edge center of primary screen. Protects against
        # stale config landing the tab off-screen on a different machine.
        QTimer.singleShot(500, self._verify_on_screen)

    def _tendril_tick(self):
        if self._is_expanded:
            self.update()

    def _verify_on_screen(self):
        """If our geometry is not inside any available screen, reset to safe defaults."""
        geo = self.geometry()
        app = QApplication.instance()
        if not app:
            return
        screens = app.screens()
        if not screens:
            return
        # Check if our center point is inside any screen's available geometry
        center = geo.center()
        for s in screens:
            if s.availableGeometry().contains(center):
                return  # We're visible somewhere, fine
        # Off-screen. Snap to primary screen, left edge, center.
        _log.warning("Tab off-screen - recovering to primary left-center")
        self._edge = LEFT
        self._mon_idx = 0
        self.config["dock_edge"] = LEFT
        self.config["monitor"] = 0
        self.config["edge_offset"] = 0.5
        save_config(self.config)
        self._collapse_to_tab()

    # ---- Acrylic Blur ----

    # ---- Clamp bracket animation property ----

    def _get_clamp(self):
        return self._clamp_val

    def _set_clamp(self, v):
        self._clamp_val = v
        self.update()

    _clamp_progress = pyqtProperty(float, _get_clamp, _set_clamp)

    def _animate_clamps(self, target, duration=300):
        anim = QPropertyAnimation(self, b"_clamp_progress")
        anim.setDuration(duration)
        anim.setStartValue(self._clamp_val)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutBack if target > 0.5 else QEasingCurve.InCubic)
        self._clamp_anim = anim  # prevent GC
        anim.start()

    # Acrylic blur removed in v3 - Windows API call can be flagged by EDR and
    # fails silently on many systems. Solid glass background is used instead.

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

        # Header - custom painted sci-fi bar
        self._header = _HeaderBar(self._on_close_click)
        self._header.setFixedHeight(s(C.HEADER_HEIGHT) + 4)
        self._header.setCursor(Qt.OpenHandCursor)
        panel_layout.addWidget(self._header)

        # Scroll area - explicit dark background
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Sci-fi styled scroll area with dark glass background and glowing scrollbar
        dark = "#0d1626"
        self._scroll.setStyleSheet(
            "QScrollArea {{ border: none; background-color: {0}; }}"
            "QScrollArea > QWidget > QWidget {{ background-color: {0}; }}"
            "QScrollBar:vertical {{ background: {0}; width: 5px; margin: 2px; border: none; }}"
            "QScrollBar::handle:vertical {{ background: rgba(80,170,255,0.35); border-radius: 2px; min-height: 20px; }}"
            "QScrollBar::handle:vertical:hover {{ background: rgba(80,170,255,0.6); }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: {0}; }}".format(dark)
        )
        from .shortcut_widget import ShortcutContainer
        self._shortcut_container = ShortcutContainer()
        self._shortcut_container.setStyleSheet("background-color: {};".format(dark))
        self._shortcut_container.setAutoFillBackground(True)
        self._shortcut_container.reorder.connect(self._reorder_to)
        self._shortcut_layout = QVBoxLayout(self._shortcut_container)
        self._shortcut_layout.setContentsMargins(6, 6, 6, 6)
        self._shortcut_layout.setSpacing(2)
        self._shortcut_layout.addStretch()
        self._scroll.setWidget(self._shortcut_container)
        panel_layout.addWidget(self._scroll, 1)

        # Bottom bar - sci-fi styled (has its own top energy line)
        bottom = _BottomBar(self._on_add_click, self._on_settings_click)
        bottom.setFixedHeight(s(C.BOTTOM_BAR_HEIGHT) + 2)
        panel_layout.addWidget(bottom)

        self._populate_shortcuts()

    def paintEvent(self, event):
        """Paint the glassmorphism background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._is_expanded:
            rect = self.rect()

            from PyQt5.QtCore import QPointF, QRectF

            gp = self._glow_pad
            panel_rect = rect.adjusted(gp, gp, -gp, -gp)
            pr = QRectF(panel_rect)

            # Panel background with glass gradient (top lighter, bottom deeper)
            bg_grad = QLinearGradient(panel_rect.topLeft(), panel_rect.bottomLeft())
            bg_grad.setColorAt(0.0, QColor(22, 34, 58, 255))
            bg_grad.setColorAt(0.5, QColor(15, 23, 42, 255))
            bg_grad.setColorAt(1.0, QColor(12, 20, 38, 255))
            painter.setBrush(bg_grad)
            painter.setPen(QPen(QColor(120, 170, 220, 80), 1))
            painter.drawRoundedRect(panel_rect, 10, 10)

            # Glass reflection highlight along the top edge (inside the panel)
            reflect_rect = QRectF(panel_rect.left() + 8, panel_rect.top() + 1,
                                  panel_rect.width() - 16, 18)
            reflect_grad = QLinearGradient(reflect_rect.topLeft(), reflect_rect.bottomLeft())
            reflect_grad.setColorAt(0.0, QColor(255, 255, 255, 35))
            reflect_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(reflect_grad)
            painter.drawRoundedRect(reflect_rect, 6, 6)

            # ---- Living energy tethers reaching toward docked wall ----
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

    def _reorder_to(self, from_index, to_index):
        """Move a shortcut from one position to another (drag-reorder)."""
        shortcuts = self.config.get("shortcuts", [])
        if not (0 <= from_index < len(shortcuts)):
            return
        to_index = max(0, min(to_index, len(shortcuts) - 1))
        if from_index == to_index:
            return
        item = shortcuts.pop(from_index)
        shortcuts.insert(to_index, item)
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

        # Retract clamps first, then animate shrink
        self._animate_clamps(0.0, duration=150)
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

        # Expand window by glow_pad on each side so glow renders outside the panel
        gp = self._glow_pad
        target.adjust(-gp, -gp, gp, gp)

        # Panel widget sits inside the glow padding
        self._panel_widget.setGeometry(gp, gp, target.width() - 2 * gp, target.height() - 2 * gp)
        self._panel_widget.show()
        self._tab_widget.hide()
        self._is_animating = True

        def on_done():
            self._is_animating = False
            self._is_expanded = True
            self.update()
            # Clamps engage after panel arrives (like latches clicking shut)
            self._animate_clamps(1.0, duration=350)

        self._animate_to(target, duration=160, on_done=on_done)
        self._is_expanded = True

    def _animate_to(self, target_rect, duration=160, on_done=None):
        """Smooth fast geometry animation."""
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(duration)
        anim.setStartValue(self.geometry())
        anim.setEndValue(target_rect)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        # Keep panel widget inside the glow padding during animation
        gp = self._glow_pad
        def _sync_panel(r):
            if self._panel_widget.isVisible():
                self._panel_widget.setGeometry(gp, gp, r.width() - 2 * gp, r.height() - 2 * gp)
        anim.valueChanged.connect(_sync_panel)
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
        gp = self._glow_pad
        rect.adjust(-gp, -gp, gp, gp)
        self.setGeometry(rect)
        self._panel_widget.setGeometry(gp, gp, rect.width() - 2 * gp, rect.height() - 2 * gp)

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
            # Map the click position into the panel widget's coordinate space
            panel_pos = self._panel_widget.mapFromParent(event.pos())
            header_geo = self._header.geometry()
            if header_geo.contains(panel_pos):
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

    def _on_close_click(self):
        """User explicitly closed the app. Write quit flag so watchdog exits too."""
        import os, sys
        from .constants import CONFIG_DIR
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(os.path.join(CONFIG_DIR, "quit.flag"), "w") as f:
                f.write("user")
        except Exception:
            pass
        QApplication.quit()

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
