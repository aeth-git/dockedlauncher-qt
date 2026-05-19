"""Calls tab view — missed calls highlighted in red."""
from PyQt5.QtCore import Qt, QModelIndex
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from .base_view import BaseTabView, _RecordModel
from ..constants import RED, INK

_COLUMNS = [
    ("timestamp", "Date / Time"),
    ("number",    "Number"),
    ("name",      "Name"),
    ("direction", "Direction"),
    ("status",    "Status"),
    ("call_type", "Type"),
    ("duration",  "Duration"),
    ("provider",  "Provider"),
]


class _CallDelegate(QStyledItemDelegate):
    """Colour missed call rows in red."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        status_col = next((i for i, (k, _) in enumerate(_COLUMNS) if k == "status"), -1)
        if index.column() == status_col:
            val = index.data(Qt.DisplayRole) or ""
            if val == "Missed":
                option.palette.setColor(option.palette.Text, QColor(RED))


class CallsView(BaseTabView):
    TAB_NAME = "Calls"
    COLUMNS = _COLUMNS

    def _build_content(self):
        widget = super()._build_content()
        self._table.setItemDelegate(_CallDelegate(self._table))
        return widget
