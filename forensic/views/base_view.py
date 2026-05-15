"""BaseTabView — Swiss minimal chrome: search bar + content + CSV export."""
import csv
import os
from typing import List

from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PyQt5.QtGui import QColor, QFont, QKeySequence
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QPushButton, QFileDialog, QTableView, QHeaderView,
    QShortcut, QAbstractItemView, QSizePolicy, QAction, QMenu,
)

from ..constants import (
    PAPER, PAPER_SOFT, INK, INK_SOFT, INK_MUTED, HAIRLINE, HOVER, RED,
    FONT_FAMILY, FONT_SIZE_DATA, FONT_SIZE_LABEL, ROW_H, HEADER_H,
)
from ..case_log import CaseLog
from ..logger import get_logger

_log = get_logger("views.base")

# Shared QSS snippets
TABLE_QSS = f"""
QTableView {{
    border: none;
    background: {PAPER};
    alternate-background-color: {PAPER_SOFT};
    color: {INK};
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_DATA}px;
    selection-background-color: {HOVER};
    selection-color: {INK};
    gridline-color: transparent;
    outline: none;
}}
QHeaderView::section {{
    background: {PAPER};
    color: {INK_MUTED};
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_LABEL}px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 0 10px;
    border: none;
    border-bottom: 1px solid {HAIRLINE};
    text-align: left;
}}
QTableView::item {{
    padding: 0 10px;
    border-bottom: 1px solid {HAIRLINE};
}}
QTableView::item:selected {{
    background: {HOVER};
    color: {INK};
}}
QScrollBar:vertical {{
    background: {PAPER};
    width: 6px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {HAIRLINE};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""

SEARCH_QSS = f"""
QLineEdit {{
    border: 1px solid {HAIRLINE};
    border-radius: 0;
    padding: 4px 10px;
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_DATA}px;
    background: {PAPER};
    color: {INK};
}}
QLineEdit:focus {{
    border-color: {INK};
    outline: none;
}}
"""

TOOLBAR_QSS = f"""
QWidget#toolbar {{
    background: {PAPER};
    border-top: 1px solid {HAIRLINE};
}}
"""

BTN_QSS = f"""
QPushButton {{
    background: {PAPER};
    color: {INK};
    border: 1px solid {HAIRLINE};
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_DATA}px;
    padding: 4px 14px;
}}
QPushButton:hover {{ background: {HOVER}; border-color: {INK}; }}
QPushButton:disabled {{ color: {INK_MUTED}; border-color: {HAIRLINE}; }}
"""


class _RecordModel(QAbstractTableModel):
    """Flat read-only table model for list[dict] records."""

    def __init__(self, records: List[dict], columns: List[tuple], parent=None):
        super().__init__(parent)
        self._records = records
        self._columns = columns   # [(key, display_name), ...]

    def rowCount(self, parent=QModelIndex()):
        return len(self._records)

    def columnCount(self, parent=QModelIndex()):
        return len(self._columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._records[index.row()]
        key, _ = self._columns[index.column()]
        val = row.get(key, "")

        if role == Qt.DisplayRole:
            if isinstance(val, list):
                return ", ".join(str(v) for v in val)
            return str(val) if val is not None else ""

        if role == Qt.SizeHintRole:
            from PyQt5.QtCore import QSize
            return QSize(0, ROW_H)

        if role == Qt.FontRole:
            f = QFont(FONT_FAMILY.split(",")[0].strip(), FONT_SIZE_DATA)
            return f

        if role == Qt.ForegroundRole:
            # Missed calls / received markers in muted ink
            return QColor(INK)

        if role == Qt.UserRole:
            return row   # full record for context menus

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._columns[section][1].upper()
        return None

    def get_record(self, row: int) -> dict:
        if 0 <= row < len(self._records):
            return self._records[row]
        return {}


class BaseTabView(QWidget):
    """Swiss minimal tab: search bar + table content + export toolbar."""

    TAB_NAME = ""
    COLUMNS: List[tuple] = []   # [(key, header), ...]

    def __init__(self, case_log: CaseLog = None, parent=None):
        super().__init__(parent)
        self._all_records: List[dict] = []
        self._filtered: List[dict] = []
        self._case_log = case_log
        self._export_btn: QPushButton = None
        self._count_label: QLabel = None
        self._search_box: QLineEdit = None
        self._table: QTableView = None
        self._model: _RecordModel = None
        self._build_chrome()
        self._install_shortcuts()
        self.show_empty("Open a source above to begin analysis.")

    # ── Chrome construction ──────────────────────────────────────────────────

    def _build_chrome(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._make_search_bar())
        content = self._build_content()
        layout.addWidget(content, 1)
        layout.addWidget(self._make_toolbar())

    def _make_search_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet(f"background:{PAPER}; border-bottom:1px solid {HAIRLINE};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 0, 16, 0)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText(f"Search {self.TAB_NAME}…")
        self._search_box.setStyleSheet(SEARCH_QSS)
        self._search_box.setFixedHeight(28)
        self._search_box.textChanged.connect(self._on_search)
        self._search_box.setClearButtonEnabled(True)

        self._count_label = QLabel("—")
        self._count_label.setStyleSheet(
            f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; font-size:{FONT_SIZE_LABEL}px;"
        )
        self._count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._count_label.setFixedWidth(90)

        row.addWidget(self._search_box, 1)
        row.addWidget(self._count_label)
        return bar

    def _make_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(40)
        bar.setStyleSheet(TOOLBAR_QSS)
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 0, 16, 0)
        row.addStretch()

        self._export_btn = QPushButton("Export CSV")
        self._export_btn.setFixedSize(90, 26)
        self._export_btn.setStyleSheet(BTN_QSS)
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.setToolTip("Export visible rows to CSV (Ctrl+E)")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export)
        row.addWidget(self._export_btn)
        return bar

    def _build_content(self) -> QWidget:
        """Default content: a QTableView. Subclasses may override."""
        self._table = QTableView()
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.setWordWrap(False)
        self._table.setStyleSheet(TABLE_QSS)
        self._table.horizontalHeader().setHighlightSections(False)
        self._table.horizontalHeader().setDefaultSectionSize(140)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(ROW_H)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        return self._table

    def _install_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+F"), self,
                  activated=lambda: self._search_box.setFocus())
        QShortcut(QKeySequence("Ctrl+E"), self,
                  activated=self._on_export)
        QShortcut(QKeySequence("Escape"), self,
                  activated=lambda: self._search_box.clear())

    # ── Public API ───────────────────────────────────────────────────────────

    def load_records(self, records: List[dict]):
        self._all_records = records
        self._filtered = records
        self._populate(records)
        count = len(records)
        self._count_label.setText(f"{count:,} record{'s' if count != 1 else ''}")
        self._export_btn.setEnabled(bool(records))

    def set_loading(self, loading: bool):
        self._export_btn.setEnabled(not loading)
        if loading:
            self._count_label.setText("Loading…")

    def show_empty(self, message: str):
        self._count_label.setText("—")
        self._export_btn.setEnabled(False)
        if self._table:
            self._model = _RecordModel([], self.COLUMNS)
            self._table.setModel(self._model)

    def show_error(self, title: str, detail: str = ""):
        self._count_label.setText("Error")
        self._export_btn.setEnabled(False)
        if self._table:
            self._model = _RecordModel([], self.COLUMNS)
            self._table.setModel(self._model)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _populate(self, records: List[dict]):
        if self._table is None:
            return
        self._model = _RecordModel(records, self.COLUMNS)
        proxy = QSortFilterProxyModel()
        proxy.setSourceModel(self._model)
        self._table.setModel(proxy)
        hdr = self._table.horizontalHeader()
        if self.COLUMNS:
            hdr.setStretchLastSection(True)
        self._table.resizeColumnsToContents()

    def _on_search(self, text: str):
        q = text.strip().lower()
        if not q:
            self._filtered = self._all_records
        else:
            self._filtered = [
                r for r in self._all_records
                if any(q in str(v).lower() for v in r.values())
            ]
        self._populate(self._filtered)
        count = len(self._filtered)
        self._count_label.setText(f"{count:,} record{'s' if count != 1 else ''}")

    def _on_export(self):
        if not self._filtered:
            return
        default_name = f"{self.TAB_NAME.lower().replace(' ', '_')}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {self.TAB_NAME}", default_name, "CSV Files (*.csv)"
        )
        if not path:
            return
        flat_records = [self._flatten(r) for r in self._filtered]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=flat_records[0].keys())
            writer.writeheader()
            writer.writerows(flat_records)
        if self._case_log:
            self._case_log.log_export(path, len(flat_records))
        _log.info("Exported %d records to %s", len(flat_records), path)

    def _flatten(self, record: dict) -> dict:
        """Flatten nested lists to comma-joined strings for CSV."""
        out = {}
        for k, v in record.items():
            if isinstance(v, list):
                out[k] = "; ".join(
                    str(item.get("value", item)) if isinstance(item, dict) else str(item)
                    for item in v
                )
            else:
                out[k] = v
        return out

    def _on_context_menu(self, pos):
        index = self._table.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{PAPER}; border:1px solid {HAIRLINE}; "
            f"font-family:{FONT_FAMILY}; font-size:{FONT_SIZE_DATA}px; }}"
            f"QMenu::item {{ padding:6px 16px; color:{INK}; }}"
            f"QMenu::item:selected {{ background:{HOVER}; }}"
        )

        copy_cell = menu.addAction("Copy Cell")
        copy_row = menu.addAction("Copy Row as JSON")
        menu.addSeparator()
        export_sel = menu.addAction("Export Selection to CSV")

        action = menu.exec_(self._table.viewport().mapToGlobal(pos))
        if not action:
            return

        from PyQt5.QtWidgets import QApplication
        import json

        if action == copy_cell:
            val = index.data(Qt.DisplayRole) or ""
            QApplication.clipboard().setText(str(val))
        elif action == copy_row:
            proxy = self._table.model()
            src_row = proxy.mapToSource(index).row() if hasattr(proxy, "mapToSource") else index.row()
            if self._model:
                record = self._model.get_record(src_row)
                QApplication.clipboard().setText(json.dumps(record, ensure_ascii=False, indent=2))
        elif action == export_sel:
            selected = self._table.selectedIndexes()
            rows_seen = set()
            records = []
            proxy = self._table.model()
            for idx in selected:
                src_row = proxy.mapToSource(idx).row() if hasattr(proxy, "mapToSource") else idx.row()
                if src_row not in rows_seen and self._model:
                    rows_seen.add(src_row)
                    records.append(self._model.get_record(src_row))
            if records:
                path, _ = QFileDialog.getSaveFileName(
                    self, "Export Selection", "selection.csv", "CSV Files (*.csv)"
                )
                if path:
                    flat = [self._flatten(r) for r in records]
                    with open(path, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.DictWriter(f, fieldnames=flat[0].keys())
                        writer.writeheader()
                        writer.writerows(flat)
