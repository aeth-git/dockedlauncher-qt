"""IOC / Security findings view — color-coded by severity."""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from .base_view import BaseTabView, _RecordModel, TABLE_QSS, TOOLBAR_QSS, BTN_QSS
from ..constants import RED, INK, INK_MUTED, PAPER, HAIRLINE, FONT_FAMILY, FONT_SIZE_DATA

_SEVERITY_COLORS = {
    "CRITICAL": "#e30613",   # RED
    "HIGH":     "#ff6b35",   # orange-red
    "MEDIUM":   "#f7c325",   # amber
    "LOW":      "#4a90d9",   # blue
    "INFO":     "#8a8a8a",   # muted
}


class _IOCModel(_RecordModel):
    def data(self, index, role=Qt.DisplayRole):
        result = super().data(index, role)
        if role == Qt.ForegroundRole:
            row = self._records[index.row()]
            sev = row.get("severity", "INFO")
            color = _SEVERITY_COLORS.get(sev, INK_MUTED)
            return QColor(color)
        return result


class IOCView(BaseTabView):
    TAB_NAME = "Security"
    COLUMNS = [
        ("severity",   "Severity"),
        ("category",   "Category"),
        ("finding",    "Finding"),
        ("bundle_id",  "Bundle ID"),
        ("detail",     "Detail"),
    ]

    def _populate(self, records):
        from .base_view import QSortFilterProxyModel
        self._model = _IOCModel(records, self.COLUMNS)
        proxy = QSortFilterProxyModel()
        proxy.setSourceModel(self._model)
        self._table.setModel(proxy)
        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(True)
        self._table.resizeColumnsToContents()
