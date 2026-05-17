"""Generic raw SQLite database browser — used for unknown/encrypted schemas."""
import sqlite3
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QTableView, QLabel, QSplitter,
)

from .base_view import BaseTabView, _RecordModel, TABLE_QSS
from ..logger import get_logger

_log = get_logger("views.raw_db")
from ..constants import (
    PAPER, HAIRLINE, INK, INK_MUTED, FONT_FAMILY, FONT_SIZE_DATA, FONT_SIZE_LABEL,
)


class RawDbView(QWidget):
    """Shows table list on the left, raw rows on the right."""

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._build_ui()
        self._load_tables()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)

        # Left: table list
        left = QWidget()
        left.setFixedWidth(200)
        left.setStyleSheet(f"background:{PAPER}; border-right:1px solid {HAIRLINE};")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("TABLES")
        lbl.setStyleSheet(
            f"color:{INK_MUTED}; font:{FONT_SIZE_LABEL}px '{FONT_FAMILY.split(',')[0].strip()}';"
            f" padding:10px 12px 6px; font-weight:600; letter-spacing:1px;"
        )
        self._table_list = QListWidget()
        self._table_list.setStyleSheet(
            f"QListWidget {{ border:none; background:{PAPER}; "
            f"font-family:{FONT_FAMILY}; font-size:{FONT_SIZE_DATA}px; }}"
            f"QListWidget::item {{ padding:8px 12px; border-bottom:1px solid {HAIRLINE}; }}"
            f"QListWidget::item:selected {{ background:#f2f2f2; color:{INK}; }}"
        )
        self._table_list.currentTextChanged.connect(self._load_rows)
        ll.addWidget(lbl)
        ll.addWidget(self._table_list, 1)
        splitter.addWidget(left)

        # Right: raw table rows
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self._rows_table = QTableView()
        self._rows_table.setShowGrid(False)
        self._rows_table.setAlternatingRowColors(True)
        self._rows_table.setEditTriggers(QTableView.NoEditTriggers)
        self._rows_table.setStyleSheet(TABLE_QSS)
        self._rows_table.verticalHeader().setVisible(False)
        rl.addWidget(self._rows_table, 1)
        splitter.addWidget(right)

        splitter.setSizes([200, 800])
        layout.addWidget(splitter)

    def _load_tables(self):
        try:
            uri = f"file:{self._db_path}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True)
            cur = self._conn.execute(
                "SELECT name, (SELECT count(*) FROM sqlite_master s2 WHERE s2.name=m.name) "
                "FROM sqlite_master m WHERE type='table' ORDER BY name"
            )
            for row in cur.fetchall():
                name = row[0]
                count_cur = self._conn.execute(f"SELECT count(*) FROM [{name}]")
                count = count_cur.fetchone()[0]
                item = QListWidgetItem(f"{name}  ({count:,})")
                item.setData(Qt.UserRole, name)
                self._table_list.addItem(item)
        except Exception as e:
            lbl = QLabel(f"Cannot open database:\n{e}")
            lbl.setStyleSheet(f"color:{INK_MUTED}; padding:20px; font-family:{FONT_FAMILY};")
            self.layout().addWidget(lbl)

    def _load_rows(self, table_name_with_count: str):
        item = self._table_list.currentItem()
        if not item:
            return
        table = item.data(Qt.UserRole)
        if not table or not self._conn:
            return
        try:
            cur = self._conn.execute(f"SELECT * FROM [{table}] LIMIT 5000")
            col_names = [d[0] for d in cur.description]
            rows = cur.fetchall()
            columns = [(c, c) for c in col_names]
            records = []
            for row in rows:
                r = {}
                for i, col in enumerate(col_names):
                    val = row[i]
                    if isinstance(val, bytes):
                        r[col] = f"<binary {len(val)} bytes>"
                    else:
                        r[col] = val
                records.append(r)
            model = _RecordModel(records, columns)
            self._rows_table.setModel(model)
            self._rows_table.horizontalHeader().setStretchLastSection(True)
            self._rows_table.resizeColumnsToContents()
        except Exception as e:
            _log.debug("raw_db row load failed for table %r: %s", table, e)

    def closeEvent(self, event):
        if self._conn:
            self._conn.close()
        super().closeEvent(event)
