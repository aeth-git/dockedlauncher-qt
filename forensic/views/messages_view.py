"""Messages tab — conversation list (left) + bubble thread (right) + app sub-tabs."""
import os
import subprocess
import sys
from typing import List, Optional

from PyQt5.QtCore import Qt, QSize, QRect, QPoint
from PyQt5.QtGui import QColor, QPainter, QFont, QPainterPath, QFontMetrics
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTabBar, QListWidget, QListWidgetItem,
    QScrollArea, QLabel, QLineEdit, QSplitter, QPushButton, QSizePolicy,
    QStackedWidget,
)

from .base_view import SEARCH_QSS, BTN_QSS, TOOLBAR_QSS
from ..constants import (
    PAPER, PAPER_SOFT, HAIRLINE, INK, INK_MUTED, INK_SOFT, RED, RED_BUBBLE,
    FONT_FAMILY, FONT_SIZE_DATA, FONT_SIZE_LABEL, CONV_LIST_W, BUBBLE_RADIUS,
    BUBBLE_MAX_W,
)
from ..case_log import CaseLog
from ..logger import get_logger
from ..parsers.thirdparty.snapchat import METADATA_NOTICE

_log = get_logger("views.messages")

_SUB_TABS = [
    ("SMS / iMessage", "sms"),
    ("WhatsApp",       "whatsapp"),
    ("Telegram",       "telegram"),
    ("Signal",         "signal"),
    ("Messenger",      "messenger"),
    ("Instagram",      "instagram"),
    ("Snapchat",       "snapchat"),
]

SUB_TAB_BAR_QSS = f"""
QTabBar {{
    background: {PAPER};
    border-bottom: 1px solid {HAIRLINE};
}}
QTabBar::tab {{
    background: {PAPER};
    color: {INK_MUTED};
    font-family: {FONT_FAMILY};
    font-size: 11px;
    padding: 6px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {INK};
    border-bottom: 2px solid {RED};
}}
QTabBar::tab:hover:!selected {{
    color: {INK_SOFT};
    background: {PAPER_SOFT};
}}
"""

LIST_QSS = f"""
QListWidget {{
    border: none;
    background: {PAPER};
    font-family: {FONT_FAMILY};
    font-size: 11px;
    outline: none;
}}
QListWidget::item {{
    padding: 10px 12px;
    border-bottom: 1px solid {HAIRLINE};
}}
QListWidget::item:selected {{
    background: {PAPER_SOFT};
    color: {INK};
}}
QScrollBar:vertical {{
    width: 6px; background: {PAPER}; border: none;
}}
QScrollBar::handle:vertical {{
    background: {HAIRLINE}; border-radius: 3px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


class _BubbleWidget(QWidget):
    """Renders a single chat bubble via QPainter — no HTML injection."""

    def __init__(self, record: dict, parent=None):
        super().__init__(parent)
        self._record = record
        self._is_sent = str(record.get("direction", "")).lower() == "sent"
        self._body = str(record.get("body", ""))
        self._time = str(record.get("timestamp", ""))
        self._attachments = record.get("attachments", [])
        font = QFont(FONT_FAMILY.split(",")[0].strip(), FONT_SIZE_DATA)
        fm = QFontMetrics(font)
        # Calculate required height
        max_w = min(BUBBLE_MAX_W, 500) - 32
        br = fm.boundingRect(0, 0, max_w, 10000, Qt.TextWordWrap, self._body)
        time_h = fm.height()
        attach_h = len(self._attachments) * (fm.height() + 4)
        total_h = br.height() + 16 + time_h + 8 + attach_h + 12
        self.setMinimumHeight(max(44, total_h))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        font = QFont(FONT_FAMILY.split(",")[0].strip(), FONT_SIZE_DATA)
        p.setFont(font)
        fm = QFontMetrics(font)

        max_text_w = min(BUBBLE_MAX_W - 32, w - 80)
        br = fm.boundingRect(0, 0, max_text_w, 10000, Qt.TextWordWrap, self._body)
        bubble_w = min(br.width() + 32, w - 60)
        bubble_h = br.height() + 28

        margin = 16
        if self._is_sent:
            x = w - bubble_w - margin
            bg = QColor(RED_BUBBLE)
            border_color = QColor("#f5c0c0")
        else:
            x = margin
            bg = QColor(PAPER_SOFT)
            border_color = QColor(HAIRLINE)

        # Draw bubble
        path = QPainterPath()
        path.addRoundedRect(x, 8, bubble_w, bubble_h, BUBBLE_RADIUS, BUBBLE_RADIUS)
        p.fillPath(path, bg)
        p.setPen(border_color)
        p.drawPath(path)

        # Draw body text
        p.setPen(QColor(INK))
        text_rect = QRect(x + 12, 8 + 10, bubble_w - 24, bubble_h - 20)
        p.drawText(text_rect, Qt.TextWordWrap, self._body if self._body else "(no text)")

        # Draw timestamp below bubble
        ts_y = 8 + bubble_h + 4
        p.setPen(QColor(INK_MUTED))
        small_font = QFont(FONT_FAMILY.split(",")[0].strip(), FONT_SIZE_LABEL)
        p.setFont(small_font)
        if self._is_sent:
            p.drawText(x, ts_y, bubble_w, fm.height(), Qt.AlignRight, self._time)
        else:
            p.drawText(x, ts_y, bubble_w, fm.height(), Qt.AlignLeft, self._time)

        p.end()


class _ConvThreadWidget(QScrollArea):
    """Scrollable list of bubble widgets for a conversation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet(f"QScrollArea {{ border:none; background:{PAPER}; }}")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._container = QWidget()
        self._container.setStyleSheet(f"background:{PAPER};")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(0)
        self._layout.addStretch()
        self.setWidget(self._container)

    def clear(self):
        while self._layout.count() > 1:  # keep the stretch
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_records(self, records: List[dict]):
        self.clear()
        for i, rec in enumerate(records):
            bubble = _BubbleWidget(rec)
            self._layout.insertWidget(i, bubble)
        # Scroll to bottom
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class _ConvItem(QListWidgetItem):
    """Conversation list item: contact + preview + time."""

    def __init__(self, contact: str, preview: str, ts: str, records: List[dict]):
        display = f"{contact or '(unknown)'}\n{preview[:60] if preview else ''}  {ts or ''}"
        super().__init__(display)
        self.contact = contact
        self.records = records


class _MessagingPane(QWidget):
    """Left: conversation list. Right: thread. For one messaging app."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_records: List[dict] = []
        self._search_text = ""
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)

        # Left: conversation list
        left = QWidget()
        left.setFixedWidth(CONV_LIST_W)
        left.setStyleSheet(f"background:{PAPER}; border-right:1px solid {HAIRLINE};")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        self._conv_list = QListWidget()
        self._conv_list.setStyleSheet(LIST_QSS)
        self._conv_list.currentItemChanged.connect(self._on_conv_selected)
        ll.addWidget(self._conv_list, 1)
        splitter.addWidget(left)

        # Right: thread
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        self._empty_label = QLabel("Select a conversation")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; font-size:13px;"
        )

        self._thread = _ConvThreadWidget()

        self._stack = QStackedWidget()
        self._stack.addWidget(self._empty_label)   # 0
        self._stack.addWidget(self._thread)          # 1
        rl.addWidget(self._stack, 1)
        splitter.addWidget(right)

        splitter.setSizes([CONV_LIST_W, 800])
        layout.addWidget(splitter)

    def load_records(self, records: List[dict]):
        self._all_records = records
        self._rebuild_conv_list(records)

    def _rebuild_conv_list(self, records: List[dict]):
        self._conv_list.clear()

        # Group by chat or contact
        groups: dict = {}
        for r in records:
            key = r.get("chat") or r.get("contact") or "(unknown)"
            groups.setdefault(key, []).append(r)

        for key, recs in groups.items():
            # Most recent first
            latest = recs[0]
            preview = str(latest.get("body", ""))[:80]
            ts = str(latest.get("timestamp", ""))
            item = _ConvItem(key, preview, ts, recs)
            self._conv_list.addItem(item)

    def _on_conv_selected(self, current, previous):
        if not current or not isinstance(current, _ConvItem):
            self._stack.setCurrentIndex(0)
            return
        self._thread.load_records(current.records)
        self._stack.setCurrentIndex(1)

    def filter(self, text: str):
        q = text.lower()
        for i in range(self._conv_list.count()):
            item = self._conv_list.item(i)
            item.setHidden(bool(q and q not in item.text().lower()))


class _ErrorPane(QWidget):
    """Shows a structured error with title + detail."""

    def __init__(self, title: str, detail: str = "", notice: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 40, 40, 40)

        icon = QLabel("⚠")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"color:{INK_MUTED}; font-size:32px;")
        layout.addWidget(icon)

        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"color:{INK}; font-family:{FONT_FAMILY}; font-size:13px; font-weight:600; margin-top:8px;"
        )
        layout.addWidget(title_lbl)

        if detail:
            detail_lbl = QLabel(detail)
            detail_lbl.setAlignment(Qt.AlignCenter)
            detail_lbl.setWordWrap(True)
            detail_lbl.setStyleSheet(
                f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; font-size:11px; margin-top:6px;"
            )
            layout.addWidget(detail_lbl)

        if notice:
            notice_lbl = QLabel(notice)
            notice_lbl.setAlignment(Qt.AlignCenter)
            notice_lbl.setWordWrap(True)
            notice_lbl.setStyleSheet(
                f"color:{RED}; font-family:{FONT_FAMILY}; font-size:10px; margin-top:12px; padding:8px;"
                f"background:{RED_BUBBLE}; border:1px solid #f5c0c0;"
            )
            layout.addWidget(notice_lbl)


class MessagesView(QWidget):
    """Messages tab: app sub-selector + conversation pane."""

    TAB_NAME = "Messages"

    def __init__(self, case_log: CaseLog = None, parent=None):
        super().__init__(parent)
        self._case_log = case_log
        self._panes: dict = {}        # key → QWidget (messaging pane or error pane)
        self._record_counts: dict = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Search bar
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet(f"background:{PAPER}; border-bottom:1px solid {HAIRLINE};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 0, 16, 0)
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search messages…")
        self._search_box.setStyleSheet(SEARCH_QSS)
        self._search_box.setFixedHeight(28)
        self._search_box.textChanged.connect(self._on_search)
        self._search_box.setClearButtonEnabled(True)
        self._count_label = QLabel("—")
        self._count_label.setStyleSheet(
            f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; font-size:{FONT_SIZE_LABEL}px;"
        )
        self._count_label.setFixedWidth(90)
        self._count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self._search_box, 1)
        row.addWidget(self._count_label)
        layout.addWidget(bar)

        # App sub-tab bar
        self._tab_bar = QTabBar()
        self._tab_bar.setStyleSheet(SUB_TAB_BAR_QSS)
        self._tab_bar.setExpanding(False)
        for label, key in _SUB_TABS:
            self._tab_bar.addTab(label)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tab_bar)

        # Stacked content — one pane per sub-tab
        self._stack = QStackedWidget()
        for _, key in _SUB_TABS:
            placeholder = _ErrorPane(
                "No source loaded",
                "Open a source above to begin analysis."
            )
            self._panes[key] = placeholder
            self._stack.addWidget(placeholder)
        layout.addWidget(self._stack, 1)

    def load_app_records(self, key: str, records: Optional[List[dict]],
                         error: str = "", detail: str = ""):
        """Called by the worker for each messaging app."""
        idx = next((i for i, (_, k) in enumerate(_SUB_TABS) if k == key), -1)
        if idx < 0:
            return

        old_pane = self._panes.get(key)
        if old_pane:
            self._stack.removeWidget(old_pane)
            old_pane.deleteLater()

        if error:
            notice = METADATA_NOTICE if key == "snapchat" else ""
            pane = _ErrorPane(error, detail, notice)
        elif records is not None:
            pane = _MessagingPane()
            pane.load_records(records)
            self._record_counts[key] = len(records)
        else:
            pane = _ErrorPane("No data", "No records found for this app.")

        self._panes[key] = pane
        self._stack.insertWidget(idx, pane)
        # Re-select current tab pane
        if self._tab_bar.currentIndex() == idx:
            self._stack.setCurrentWidget(pane)

        self._update_count()

    def _on_tab_changed(self, index: int):
        key = _SUB_TABS[index][1]
        pane = self._panes.get(key)
        if pane:
            self._stack.setCurrentWidget(pane)
        self._update_count()

    def _on_search(self, text: str):
        idx = self._tab_bar.currentIndex()
        key = _SUB_TABS[idx][1]
        pane = self._panes.get(key)
        if isinstance(pane, _MessagingPane):
            pane.filter(text)

    def _update_count(self):
        idx = self._tab_bar.currentIndex()
        key = _SUB_TABS[idx][1]
        n = self._record_counts.get(key)
        if n is not None:
            self._count_label.setText(f"{n:,} record{'s' if n != 1 else ''}")
        else:
            self._count_label.setText("—")

    def set_loading(self, key: str, loading: bool):
        if loading:
            idx = next((i for i, (_, k) in enumerate(_SUB_TABS) if k == key), -1)
            if idx < 0:
                return
            old = self._panes.get(key)
            if old:
                self._stack.removeWidget(old)
                old.deleteLater()
            pane = _ErrorPane("Loading…", "")
            self._panes[key] = pane
            self._stack.insertWidget(idx, pane)
