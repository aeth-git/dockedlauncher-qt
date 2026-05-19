"""Location history view — table + OpenStreetMap link."""
import webbrowser
from typing import List

from PyQt5.QtCore import Qt, QSortFilterProxyModel
from PyQt5.QtWidgets import QPushButton, QHBoxLayout, QWidget

from .base_view import BaseTabView, BTN_QSS, TOOLBAR_QSS
from ..constants import PAPER, HAIRLINE, FONT_FAMILY, FONT_SIZE_DATA


class LocationView(BaseTabView):
    TAB_NAME = "Location"
    COLUMNS = [
        ("timestamp",  "Date / Time"),
        ("type",       "Source"),
        ("lat",        "Latitude"),
        ("lon",        "Longitude"),
        ("accuracy",   "Accuracy (m)"),
        ("label",      "Network / Place"),
        ("detail",     "Detail"),
    ]

    def _make_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(40)
        bar.setStyleSheet(TOOLBAR_QSS)
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 0, 16, 0)
        row.addStretch()

        map_btn = QPushButton("Open in Maps")
        map_btn.setFixedSize(110, 26)
        map_btn.setStyleSheet(BTN_QSS)
        map_btn.setCursor(Qt.PointingHandCursor)
        map_btn.setToolTip("Open selected point in OpenStreetMap")
        map_btn.clicked.connect(self._open_in_osm)
        row.addWidget(map_btn)

        self._export_btn = QPushButton("Export CSV")
        self._export_btn.setFixedSize(90, 26)
        self._export_btn.setStyleSheet(BTN_QSS)
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export)
        row.addWidget(self._export_btn)
        return bar

    def _open_in_osm(self):
        idx = self._table.currentIndex()
        if not idx.isValid():
            return
        proxy = self._table.model()
        src_row = proxy.mapToSource(idx).row() if hasattr(proxy, "mapToSource") else idx.row()
        if not self._model:
            return
        rec = self._model.get_record(src_row)
        lat = rec.get("lat")
        lon = rec.get("lon")
        if lat is not None and lon is not None:
            url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=15"
            webbrowser.open(url)
