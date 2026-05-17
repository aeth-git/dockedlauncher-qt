"""Unified Timeline — aggregates all parsed events into one chronological view."""
import csv
from typing import List

from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PyQt5.QtGui import QColor, QFont, QKeySequence
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QPushButton, QFileDialog, QTableView,
    QShortcut, QAbstractItemView,
)

from .base_view import SEARCH_QSS, TABLE_QSS, TOOLBAR_QSS, BTN_QSS
from ..constants import (
    PAPER, HAIRLINE, INK, INK_MUTED, FONT_FAMILY,
    FONT_SIZE_DATA, FONT_SIZE_LABEL, ROW_H,
)
from ..case_log import CaseLog

# Event type → colour accent (left-border style per row)
_TYPE_COLOR = {
    "sms":          "#2196F3",
    "call":         "#4CAF50",
    "contact":      "#9C27B0",
    "voicemail":    "#FF9800",
    "safari":       "#00BCD4",
    "mail":         "#607D8B",
    "note":         "#FFC107",
    "calendar":     "#F44336",
    "location":     "#795548",
    "wifi":         "#009688",
    "photo":        "#E91E63",
    "whatsapp":     "#4CAF50",
    "telegram":     "#2196F3",
    "signal":       "#3F51B5",
    "messenger":    "#1565C0",
    "instagram":    "#C2185B",
    "snapchat":     "#FFEB3B",
    "viber":        "#7B1FA2",
    "line":         "#388E3C",
    "wechat":       "#2E7D32",
    "discord":      "#5C6BC0",
    "skype":        "#01579B",
}

_COLUMNS = [
    ("timestamp", "Date / Time"),
    ("event_type", "Type"),
    ("source_app", "Source"),
    ("contact",   "Contact / From"),
    ("summary",   "Summary"),
]


class _TimelineModel(QAbstractTableModel):
    def __init__(self, records: List[dict], parent=None):
        super().__init__(parent)
        self._records = records

    def rowCount(self, parent=QModelIndex()):
        return len(self._records)

    def columnCount(self, parent=QModelIndex()):
        return len(_COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._records[index.row()]
        key, _ = _COLUMNS[index.column()]

        if role == Qt.DisplayRole:
            return str(row.get(key, "") or "")

        if role == Qt.SizeHintRole:
            from PyQt5.QtCore import QSize
            return QSize(0, ROW_H)

        if role == Qt.ForegroundRole:
            return QColor(INK)

        if role == Qt.BackgroundRole:
            etype = row.get("event_type", "")
            color = _TYPE_COLOR.get(etype, "#888888")
            if index.column() == 1:   # type column slight tint
                c = QColor(color)
                c.setAlpha(30)
                return c
            return None

        if role == Qt.FontRole:
            return QFont(FONT_FAMILY.split(",")[0].strip(), FONT_SIZE_DATA)

        if role == Qt.UserRole:
            return row

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _COLUMNS[section][1].upper()
        return None

    def get_record(self, row: int) -> dict:
        return self._records[row] if 0 <= row < len(self._records) else {}


class TimelineView(QWidget):
    """Unified chronological timeline of all forensic events."""

    TAB_NAME = "Timeline"

    def __init__(self, case_log: CaseLog = None, parent=None):
        super().__init__(parent)
        self._all_events: List[dict] = []
        self._filtered: List[dict] = []
        self._model: _TimelineModel = None
        self._case_log = case_log
        self._type_filters: set = set()
        self._export_btn = None
        self._count_label = None
        self._search_box = None
        self._table = None
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
        self._search_box.setPlaceholderText("Search all events…")
        self._search_box.setStyleSheet(SEARCH_QSS)
        self._search_box.setFixedHeight(28)
        self._search_box.textChanged.connect(self._apply_filter)
        self._search_box.setClearButtonEnabled(True)
        self._count_label = QLabel("—")
        self._count_label.setStyleSheet(
            f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; font-size:{FONT_SIZE_LABEL}px;"
        )
        self._count_label.setFixedWidth(100)
        self._count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self._search_box, 1)
        row.addWidget(self._count_label)
        layout.addWidget(bar)

        # Table
        self._table = QTableView()
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.setWordWrap(False)
        self._table.setStyleSheet(TABLE_QSS)
        self._table.horizontalHeader().setHighlightSections(False)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(ROW_H)
        layout.addWidget(self._table, 1)

        # Toolbar
        tb = QWidget()
        tb.setObjectName("toolbar")
        tb.setFixedHeight(40)
        tb.setStyleSheet(TOOLBAR_QSS)
        trow = QHBoxLayout(tb)
        trow.setContentsMargins(16, 0, 16, 0)
        trow.addStretch()
        self._export_btn = QPushButton("Export CSV")
        self._export_btn.setFixedSize(90, 26)
        self._export_btn.setStyleSheet(BTN_QSS)
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export)
        trow.addWidget(self._export_btn)
        layout.addWidget(tb)

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+F"), self,
                  activated=lambda: self._search_box.setFocus())
        QShortcut(QKeySequence("Escape"), self,
                  activated=lambda: self._search_box.clear())
        QShortcut(QKeySequence("Ctrl+E"), self,
                  activated=self._on_export)

    def feed_records(self, event_type: str, source_app: str, records: List[dict]):
        """Called once per parser result. Converts records to timeline events."""
        for rec in records:
            ts = rec.get("timestamp") or rec.get("sent") or rec.get("received") or \
                 rec.get("start") or rec.get("modified") or ""
            contact = (rec.get("contact") or rec.get("sender") or
                       rec.get("number") or rec.get("name") or "")
            summary = _make_summary(event_type, rec)
            self._all_events.append({
                "timestamp": ts,
                "event_type": event_type,
                "source_app": source_app,
                "contact": contact,
                "summary": summary,
                "_raw": rec,
            })

        # Re-sort and re-display
        self._all_events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
        self._apply_filter()
        self._export_btn.setEnabled(bool(self._all_events))

    def _apply_filter(self):
        q = self._search_box.text().strip().lower() if self._search_box else ""
        if not q:
            self._filtered = self._all_events
        else:
            self._filtered = [
                e for e in self._all_events
                if any(q in str(v).lower() for v in e.values() if v != e.get("_raw"))
            ]
        self._model = _TimelineModel(self._filtered)
        proxy = QSortFilterProxyModel()
        proxy.setSourceModel(self._model)
        self._table.setModel(proxy)
        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(True)
        self._table.resizeColumnsToContents()
        n = len(self._filtered)
        self._count_label.setText(f"{n:,} event{'s' if n != 1 else ''}")

    def _on_export(self):
        if not self._filtered:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Timeline", "timeline.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        keys = ["timestamp", "event_type", "source_app", "contact", "summary"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self._filtered)
        if self._case_log:
            self._case_log.log_export(path, len(self._filtered))


def _make_summary(event_type: str, rec: dict) -> str:
    """Create a one-line human-readable summary for the event."""
    if event_type == "sms":
        direction = "→" if rec.get("sent") else "←"
        body = (rec.get("body") or "")[:80]
        return f"{direction} {body}"
    if event_type == "call":
        status = rec.get("status", "")
        dur = rec.get("duration", "")
        return f"{status} {rec.get('call_type', '')} {dur}".strip()
    if event_type == "safari":
        return rec.get("url", "")[:100]
    if event_type == "mail":
        return f"From: {rec.get('sender', '')} — {rec.get('subject', '')}"[:100]
    if event_type == "note":
        return rec.get("snippet") or rec.get("title", "")
    if event_type == "calendar":
        return f"{rec.get('title', '')} @ {rec.get('location', '')}".strip(" @")
    if event_type == "location":
        return f"{rec.get('type', '')} {rec.get('label', '')} ({rec.get('lat', '')}, {rec.get('lon', '')})".strip()
    if event_type == "photo":
        return rec.get("filename", "")
    if event_type == "voicemail":
        return f"From {rec.get('sender', '')} — {rec.get('duration', '')}"
    # Messaging apps: show body
    body = rec.get("body") or rec.get("text") or ""
    direction = rec.get("direction", "")
    arrow = "→" if direction == "Sent" else "←" if direction == "Received" else ""
    return f"{arrow} {body}"[:100].strip()
