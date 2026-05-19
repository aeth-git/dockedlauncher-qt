"""TCC app permissions view."""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from .base_view import BaseTabView, _RecordModel


class _TCCModel(_RecordModel):
    def data(self, index, role=Qt.DisplayRole):
        result = super().data(index, role)
        if role == Qt.ForegroundRole:
            row = self._records[index.row()]
            perm = row.get("permission", "")
            from ..constants import RED, INK_MUTED, INK
            if perm == "Denied":
                return QColor(INK_MUTED)
            if perm == "Allowed":
                return QColor(INK)
        return result


class TCCView(BaseTabView):
    TAB_NAME = "Permissions"
    COLUMNS = [
        ("service",       "Permission"),
        ("bundle_id",     "App Bundle ID"),
        ("permission",    "Status"),
        ("last_modified", "Last Changed"),
        ("reason",        "Reason"),
    ]
