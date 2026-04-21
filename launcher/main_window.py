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
    QPixmap,
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
    """Swiss minimal tab with UX-first visibility.

    Design principles applied:
      * High chromatic contrast: Swiss red fill reads on any desktop background
      * Figure-ground separation: 1px white hairline on the three outer sides
        guarantees a visible edge against both light and dark wallpapers
      * Affordance signifier: a white chevron points toward the panel, giving
        the tab pull-handle language (the classic drawer metaphor)
      * Hit target: 14 x 80 is still restrained but comfortably findable
      * Hover feedback: red darkens slightly before the panel begins to expand,
        giving a tactile confirmation the cursor is on a control
    The name "GlowTab" is preserved for compatibility but there is no glow.
    """

    # Chevron is pre-rendered once per edge and cached in a QPixmap so that
    # repeated repaints (hover polling, panel animations) blit identical pixels
    # every frame - eliminates sub-pixel AA flicker on the vector arrow.
    _CHEVRON_BOX = 16  # oversized canvas; chevron is drawn centered inside

    def __init__(self, edge, parent=None):
        super().__init__(parent)
        self._edge = edge
        self._hovered = False
        self._chevron_pix = None
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip("DockedLauncher — hover to open, drag to move")

    def set_edge(self, edge):
        if edge != self._edge:
            self._edge = edge
            self._chevron_pix = None  # invalidate cache for new direction
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def _build_chevron_pixmap(self):
        """Render the chevron once to a transparent pixmap.

        Using device-pixel-ratio keeps it crisp on 4K at 150%. Blitting this
        cached pixmap each paint guarantees identical pixels every frame.
        """
        from .constants import PAPER
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        box = self._CHEVRON_BOX
        pix = QPixmap(int(box * dpr), int(box * dpr))
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.transparent)

        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(PAPER), 1.5, Qt.SolidLine,
                      Qt.RoundCap, Qt.RoundJoin))
        cx = cy = box / 2.0
        path = QPainterPath()
        if self._edge == LEFT:
            path.moveTo(cx - 2.0, cy - 3.5)
            path.lineTo(cx + 2.0, cy)
            path.lineTo(cx - 2.0, cy + 3.5)
        elif self._edge == RIGHT:
            path.moveTo(cx + 2.0, cy - 3.5)
            path.lineTo(cx - 2.0, cy)
            path.lineTo(cx + 2.0, cy + 3.5)
        elif self._edge == TOP:
            path.moveTo(cx - 3.5, cy - 2.0)
            path.lineTo(cx, cy + 2.0)
            path.lineTo(cx + 3.5, cy - 2.0)
        else:  # BOTTOM
            path.moveTo(cx - 3.5, cy + 2.0)
            path.lineTo(cx, cy - 2.0)
            path.lineTo(cx + 3.5, cy + 2.0)
        p.drawPath(path)
        p.end()
        return pix

    def paintEvent(self, event):
        from .constants import PAPER, RED
        painter = QPainter(self)
        rect = self.rect()
        w, h = rect.width(), rect.height()

        # --- Fill: bold Swiss red (single hero accent) ---
        tab_color = QColor(RED)
        if self._hovered:
            tab_color = tab_color.darker(115)  # subtle tactile feedback
        painter.setRenderHint(QPainter.Antialiasing, False)  # crisp fill edges
        painter.fillRect(rect, tab_color)

        # --- 1px white hairline on the three outer sides ---
        painter.setPen(QPen(QColor(PAPER), 1))
        if self._edge == LEFT:
            painter.drawLine(0, 0, 0, h - 1)
            painter.drawLine(0, 0, w - 1, 0)
            painter.drawLine(0, h - 1, w - 1, h - 1)
        elif self._edge == RIGHT:
            painter.drawLine(w - 1, 0, w - 1, h - 1)
            painter.drawLine(0, 0, w - 1, 0)
            painter.drawLine(0, h - 1, w - 1, h - 1)
        elif self._edge == TOP:
            painter.drawLine(0, 0, w - 1, 0)
            painter.drawLine(0, 0, 0, h - 1)
            painter.drawLine(w - 1, 0, w - 1, h - 1)
        else:  # BOTTOM
            painter.drawLine(0, h - 1, w - 1, h - 1)
            painter.drawLine(0, 0, 0, h - 1)
            painter.drawLine(w - 1, 0, w - 1, h - 1)

        # --- Pre-rendered chevron blit (stable, no AA flicker) ---
        if self._chevron_pix is None:
            self._chevron_pix = self._build_chevron_pixmap()
        box = self._CHEVRON_BOX
        x = (w - box) // 2
        y = (h - box) // 2
        painter.drawPixmap(x, y, self._chevron_pix)

        painter.end()


# ---- Swiss Minimal Bottom Bar ----

class _BottomBar(QWidget):
    """Clean toolbar: white background, one hairline border, text buttons."""

    def __init__(self, on_add, on_settings, parent=None):
        super().__init__(parent)
        from .constants import PAPER, INK, INK_MUTED, HOVER, HAIRLINE, FONT_FAMILY

        self.setAutoFillBackground(True)
        self.setStyleSheet("background-color: {};".format(PAPER))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        btn_style = (
            "QPushButton {{ background: transparent; color: {ink}; "
            "border: 1px solid {line}; border-radius: 0; "
            "font-family: {font}; font-size: 13px; }}"
            "QPushButton:hover {{ background: {hover}; color: {ink}; border-color: {ink}; }}"
        ).format(ink=INK, line=HAIRLINE, hover=HOVER, font=FONT_FAMILY)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(24, 24)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(btn_style)
        add_btn.clicked.connect(on_add)
        layout.addWidget(add_btn)

        layout.addStretch()

        settings_btn = QPushButton("\u2699")
        settings_btn.setFixedSize(24, 24)
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.setStyleSheet(btn_style)
        settings_btn.clicked.connect(on_settings)
        layout.addWidget(settings_btn)

    def paintEvent(self, event):
        from .constants import PAPER, HAIRLINE
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(PAPER))
        # One hairline separator at top
        painter.setPen(QPen(QColor(HAIRLINE), 1))
        painter.drawLine(0, 0, w, 0)
        painter.end()


# ---- Swiss Minimal Header Bar ----

class _HeaderBar(QWidget):
    """Clean header: white bg, 'Launcher' text left, X close right, hairline below."""

    def __init__(self, on_close, parent=None):
        super().__init__(parent)
        from .constants import PAPER, INK, INK_MUTED, HOVER, RED, FONT_FAMILY
        self._on_close = on_close

        self.setAutoFillBackground(True)
        self.setStyleSheet("background-color: {};".format(PAPER))

        self._close_btn = QPushButton("\u2715", self)
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setToolTip("Close DockedLauncher")
        self._close_btn.setStyleSheet(
            "QPushButton {{ background: transparent; color: {muted}; "
            "border: none; font-family: {font}; font-size: 13px; }}"
            "QPushButton:hover {{ color: {red}; }}".format(
                muted=INK_MUTED, font=FONT_FAMILY, red=RED)
        )
        self._close_btn.clicked.connect(on_close)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._close_btn.move(self.width() - 26, (self.height() - 20) // 2)

    def paintEvent(self, event):
        from .constants import PAPER, INK, INK_SOFT, HAIRLINE, RED, FONT_FAMILY
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()

        # Solid white background
        painter.fillRect(0, 0, w, h, QColor(PAPER))

        # Small red accent square (Swiss signature move)
        painter.fillRect(12, h // 2 - 3, 6, 6, QColor(RED))

        # Title text (lowercase for humility, Swiss grotesque style)
        painter.setPen(QColor(INK))
        painter.setFont(QFont(FONT_FAMILY.split(",")[0].strip(), 10, QFont.DemiBold))
        painter.drawText(24, h // 2 + 4, "Launcher")

        # Single hairline at bottom
        painter.setPen(QPen(QColor(HAIRLINE), 1))
        painter.drawLine(0, h - 1, w, h - 1)

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
        self.setStyleSheet("DockedLauncher { background-color: #ffffff; }")
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

        # Global hotkey (Ctrl+Alt+Space by default). Fire-and-forget: if the
        # combination is already owned by another app we log and move on —
        # the launcher remains fully usable via hover.
        self._hotkey_mgr = None
        self._install_global_hotkey()

        # Safety net: 500ms after init, verify tab is actually on a screen.
        # If not, snap to left-edge center of primary screen. Protects against
        # stale config landing the tab off-screen on a different machine.
        QTimer.singleShot(500, self._verify_on_screen)

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
        # Swiss minimal scroll area: white background, thin gray scrollbar
        from .constants import PAPER, PAPER_SOFT, HAIRLINE, INK_MUTED
        paper = PAPER
        self._scroll.setStyleSheet(
            "QScrollArea {{ border: none; background-color: {paper}; }}"
            "QScrollArea > QWidget > QWidget {{ background-color: {paper}; }}"
            "QScrollBar:vertical {{ background: {paper}; width: 4px; margin: 2px; border: none; }}"
            "QScrollBar::handle:vertical {{ background: {line}; border-radius: 0; min-height: 20px; }}"
            "QScrollBar::handle:vertical:hover {{ background: {muted}; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: {paper}; }}".format(
                paper=paper, line=HAIRLINE, muted=INK_MUTED
            )
        )
        from .shortcut_widget import ShortcutContainer
        self._shortcut_container = ShortcutContainer()
        self._shortcut_container.setStyleSheet("background-color: {};".format(paper))
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
        """Paint the minimal Swiss background: solid white with 1px hairline border."""
        from .constants import PAPER, HAIRLINE
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        if self._is_expanded:
            rect = self.rect()
            gp = self._glow_pad
            panel_rect = rect.adjusted(gp, gp, -gp, -gp)

            # Solid white background - no gradient
            painter.fillRect(panel_rect, QColor(PAPER))

            # 1px hairline border around the entire panel
            painter.setPen(QPen(QColor(HAIRLINE), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(panel_rect.adjusted(0, 0, -1, -1))

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
        if self._hotkey_mgr is not None:
            self._hotkey_mgr.unregister_all()
        QApplication.quit()

    # ---- Global Hotkey ----

    _HOTKEY_ID_TOGGLE = 1

    def _install_global_hotkey(self):
        from .hotkey import HotkeyManager, MOD_CONTROL, MOD_ALT, VK_SPACE
        app = QApplication.instance()
        if app is None:
            return
        self._hotkey_mgr = HotkeyManager(app, self._on_global_hotkey)
        # Ctrl+Alt+Space: Alt+Space is reserved by Windows (system menu), but
        # adding Ctrl disambiguates and is unlikely to collide with app-level
        # shortcuts.
        self._hotkey_mgr.register(
            self._HOTKEY_ID_TOGGLE, MOD_CONTROL | MOD_ALT, VK_SPACE
        )

    def _on_global_hotkey(self, hotkey_id):
        if hotkey_id != self._HOTKEY_ID_TOGGLE:
            return
        if self._is_animating:
            return
        if self._is_expanded:
            self._collapse_to_tab()
        else:
            self._expand_to_panel()

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
