"""Report generation view — produces court-ready HTML/PDF exports."""
import os
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QFileDialog, QMessageBox, QFrame,
)

from .base_view import BTN_QSS
from ..constants import (
    PAPER, HAIRLINE, INK, INK_MUTED, INK_SOFT, FONT_FAMILY,
    FONT_SIZE_DATA, FONT_SIZE_LABEL,
)
from ..logger import get_logger

_log = get_logger("views.report")

_FIELD_QSS = f"""
QLineEdit, QTextEdit {{
    border: 1px solid {HAIRLINE};
    padding: 5px 10px;
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_DATA}px;
    background: {PAPER};
    color: {INK};
}}
QLineEdit:focus, QTextEdit:focus {{
    border-color: {INK};
    outline: none;
}}
"""


class ReportView(QWidget):
    TAB_NAME = "Report"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sections: Dict[str, List[dict]] = {}
        self._device_info: dict = {}
        self._source_path: str = ""
        self._manifest_hash: Optional[str] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignTop)

        # Title
        title = QLabel("Examination Report")
        title.setStyleSheet(
            f"color:{INK}; font-family:{FONT_FAMILY}; font-size:16px; font-weight:300;"
        )
        layout.addWidget(title)

        sub = QLabel("Generate a court-ready HTML or PDF report of all parsed evidence.")
        sub.setStyleSheet(
            f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; font-size:{FONT_SIZE_DATA}px;"
        )
        layout.addWidget(sub)

        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{HAIRLINE};")
        layout.addWidget(sep)

        # Fields
        def _field(label: str, widget: QWidget) -> QHBoxLayout:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(140)
            lbl.setStyleSheet(
                f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; "
                f"font-size:{FONT_SIZE_LABEL}px; font-weight:600; text-transform:uppercase;"
            )
            row.addWidget(lbl)
            row.addWidget(widget)
            return row

        self._case_num = QLineEdit()
        self._case_num.setPlaceholderText("Case number / reference")
        self._case_num.setStyleSheet(_FIELD_QSS)

        self._examiner = QLineEdit()
        self._examiner.setPlaceholderText(
            os.environ.get("USER", os.environ.get("USERNAME", ""))
        )
        self._examiner.setStyleSheet(_FIELD_QSS)

        self._notes = QTextEdit()
        self._notes.setPlaceholderText("Examiner notes, chain of custody observations…")
        self._notes.setFixedHeight(100)
        self._notes.setStyleSheet(_FIELD_QSS)

        layout.addLayout(_field("Case Number", self._case_num))
        layout.addLayout(_field("Examiner", self._examiner))
        layout.addLayout(_field("Notes", self._notes))

        layout.addSpacing(16)

        # Status
        self._status_label = QLabel("Load a source to enable report generation.")
        self._status_label.setStyleSheet(
            f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; font-size:{FONT_SIZE_DATA}px;"
        )
        layout.addWidget(self._status_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._html_btn = QPushButton("Export HTML Report")
        self._html_btn.setFixedHeight(32)
        self._html_btn.setStyleSheet(BTN_QSS)
        self._html_btn.setCursor(Qt.PointingHandCursor)
        self._html_btn.setEnabled(False)
        self._html_btn.clicked.connect(lambda: self._export("html"))
        btn_row.addWidget(self._html_btn)

        self._pdf_btn = QPushButton("Export PDF Report")
        self._pdf_btn.setFixedHeight(32)
        self._pdf_btn.setStyleSheet(BTN_QSS)
        self._pdf_btn.setCursor(Qt.PointingHandCursor)
        self._pdf_btn.setEnabled(False)
        self._pdf_btn.clicked.connect(lambda: self._export("pdf"))
        btn_row.addWidget(self._pdf_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()

    def set_source(self, source_path: str, device_info: dict, manifest_hash: Optional[str]):
        self._source_path = source_path
        self._device_info = device_info
        self._manifest_hash = manifest_hash
        self._html_btn.setEnabled(True)
        self._pdf_btn.setEnabled(True)
        self._status_label.setText(
            f"Source loaded: {os.path.basename(source_path)}  "
            f"({len(self._sections)} section(s) available)"
        )

    def add_section(self, name: str, records: List[dict]):
        if records:
            self._sections[name] = records
            self._status_label.setText(
                f"Source loaded — {len(self._sections)} section(s) ready"
            )

    def _export(self, fmt: str):
        from ..report import export_html, export_pdf
        filter_str = "HTML Files (*.html)" if fmt == "html" else "PDF Files (*.pdf)"
        default = f"iforensic_report.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, "Save Report", default, filter_str)
        if not path:
            return
        kwargs = dict(
            device_info=self._device_info,
            source_path=self._source_path,
            manifest_hash=self._manifest_hash,
            sections=self._sections,
            examiner=self._examiner.text().strip(),
            case_number=self._case_num.text().strip(),
            notes=self._notes.toPlainText().strip(),
        )
        try:
            if fmt == "html":
                export_html(path, **kwargs)
            else:
                export_pdf(path, **kwargs)
            QMessageBox.information(self, "Report Saved",
                                    f"Report saved to:\n{path}")
        except Exception as e:
            _log.error("Report export failed: %s", e)
            QMessageBox.critical(self, "Export Failed", str(e))
