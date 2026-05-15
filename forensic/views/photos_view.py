"""Photos tab view — fixed-column grid with background thumbnail loading."""
import io
import os
import queue as _queue_mod
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QPixmap, QImage, QColor, QPainter, QFont, QIcon
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QFrame, QSizePolicy,
)

from ..constants import (
    PAPER, HAIRLINE, INK, INK_MUTED, RED, FONT_FAMILY,
    FONT_SIZE_DATA, FONT_SIZE_LABEL, THUMB_CELL, THUMB_IMG,
)
from ..case_log import CaseLog
from ..logger import get_logger
from .base_view import SEARCH_QSS, BTN_QSS, TOOLBAR_QSS

_log = get_logger("views.photos")

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    _HEIC_OK = True
except ImportError:
    _HEIC_OK = False


class _ThumbnailLoader:
    """Loads thumbnails in a daemon thread; delivers results via QTimer drain loop.

    Using threading.Thread(daemon=True) instead of QThread avoids the C++
    destructor crash that occurs when Python GC collects a QThread wrapper
    while the OS thread is still running.
    """

    _SENTINEL = object()

    def __init__(self, records: List[dict], size: int):
        self._records = records
        self._size = size
        self._cancelled = threading.Event()
        self._q: _queue_mod.Queue = _queue_mod.Queue()
        self._callback: Optional[Callable] = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._timer = QTimer()
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._drain)

    def start(self, callback: Callable):
        self._callback = callback
        self._timer.start()
        self._thread.start()

    def cancel(self):
        self._cancelled.set()
        self._callback = None
        self._timer.stop()
        # Drain so the worker thread can put() and exit without blocking
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except _queue_mod.Empty:
                break

    def _run(self):
        for i, rec in enumerate(self._records):
            if self._cancelled.is_set():
                break
            path = rec.get("local_path", "")
            ext = rec.get("ext", "").lower()
            try:
                img = self._load_one(path, ext)
            except Exception as e:
                _log.debug("Thumbnail failed for %s: %s", path, e)
                img = _make_placeholder(self._size, ext)
            self._q.put((i, img))
        self._q.put(self._SENTINEL)

    def _drain(self):
        cb = self._callback
        if cb is None:
            return
        try:
            while True:
                item = self._q.get_nowait()
                if item is self._SENTINEL:
                    self._timer.stop()
                    return
                i, img = item
                cb(i, img)
        except _queue_mod.Empty:
            pass

    def _load_one(self, path: str, ext: str) -> QImage:
        if ext == ".heic" and not _HEIC_OK:
            return _make_placeholder(self._size, ".heic")
        if ext in (".mov", ".mp4", ".m4v", ".avi", ".3gp"):
            return _make_video_placeholder(self._size)
        try:
            from PIL import Image
            with Image.open(path) as img:
                img = img.convert("RGB")
                img.thumbnail((self._size, self._size), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
            qimg = QImage()
            qimg.loadFromData(buf.getvalue())
            return qimg
        except ImportError:
            pass
        # Qt native fallback — QImage is safe to create in any thread
        qimg = QImage(path)
        if qimg.isNull():
            return _make_placeholder(self._size, ext)
        return qimg.scaled(self._size, self._size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _make_placeholder(size: int, ext: str) -> QImage:
    img = QImage(size, size, QImage.Format_RGB32)
    img.fill(QColor("#f0f0f0"))
    p = QPainter(img)
    p.setPen(QColor(INK_MUTED))
    p.setFont(QFont(FONT_FAMILY.split(",")[0].strip(), 9))
    label = "HEIC\n(install pillow-heif)" if ext == ".heic" else ext.upper()
    p.drawText(img.rect(), Qt.AlignCenter, label)
    p.end()
    return img


def _make_video_placeholder(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_RGB32)
    img.fill(QColor("#1a1a1a"))
    p = QPainter(img)
    p.setPen(QColor("#ffffff"))
    p.setFont(QFont(FONT_FAMILY.split(",")[0].strip(), 28))
    p.drawText(img.rect(), Qt.AlignCenter, "▶")
    p.end()
    return img


class _ThumbCell(QWidget):
    """Single photo cell: image + filename label."""

    def __init__(self, record: dict, cell_size: int, img_size: int, parent=None):
        super().__init__(parent)
        self._record = record
        self._img_size = img_size
        self.setFixedSize(cell_size, cell_size + 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{record['filename']}\n{record.get('size', '')}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(2)

        self._img_label = QLabel()
        self._img_label.setFixedSize(img_size, img_size)
        self._img_label.setAlignment(Qt.AlignCenter)
        self._img_label.setStyleSheet(f"background:#f0f0f0;")

        name_label = QLabel(record["filename"])
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet(
            f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; font-size:9px;"
        )
        name_label.setWordWrap(False)

        layout.addWidget(self._img_label)
        layout.addWidget(name_label)

    def set_pixmap(self, pix: QPixmap):
        scaled = pix.scaled(
            self._img_size, self._img_size,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._img_label.setPixmap(scaled)

    def mouseDoubleClickEvent(self, event):
        path = self._record.get("local_path", "")
        if path and os.path.exists(path):
            _open_file(path)


def _open_file(path: str):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        _log.error("Failed to open %s: %s", path, e)


class PhotosView(QWidget):
    """Photos grid view with background thumbnail loading."""

    TAB_NAME = "Photos"

    def __init__(self, case_log: CaseLog = None, parent=None):
        super().__init__(parent)
        self._all_records: List[dict] = []
        self._filtered: List[dict] = []
        self._cells: List[_ThumbCell] = []
        self._loader: _ThumbnailLoader = None
        self._case_log = case_log
        self._export_btn: QPushButton = None
        self._count_label: QLabel = None
        self._search_box: QLineEdit = None
        self._grid_widget: QWidget = None
        self._grid_layout: QGridLayout = None
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
        self._search_box.setPlaceholderText("Search photos…")
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

        # Scroll area with grid
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"QScrollArea {{ border:none; background:{PAPER}; }}")
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet(f"background:{PAPER};")
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(16, 16, 16, 16)
        self._grid_layout.setSpacing(8)
        self._scroll.setWidget(self._grid_widget)
        layout.addWidget(self._scroll, 1)

        # Toolbar
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet(TOOLBAR_QSS)
        trow = QHBoxLayout(toolbar)
        trow.setContentsMargins(16, 0, 16, 0)
        trow.addStretch()
        self._export_btn = QPushButton("Export List")
        self._export_btn.setFixedSize(90, 26)
        self._export_btn.setStyleSheet(BTN_QSS)
        self._export_btn.setCursor(Qt.PointingHandCursor)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export)
        trow.addWidget(self._export_btn)
        layout.addWidget(toolbar)

    def _stop_loader(self):
        if self._loader is not None:
            self._loader.cancel()
            self._loader = None

    def closeEvent(self, event):
        self._stop_loader()
        super().closeEvent(event)

    def load_records(self, records: List[dict]):
        self._all_records = records
        self._filtered = records
        self._rebuild_grid(records)
        n = len(records)
        self._count_label.setText(f"{n:,} file{'s' if n != 1 else ''}")
        self._export_btn.setEnabled(bool(records))

    def set_loading(self, loading: bool):
        self._export_btn.setEnabled(not loading)
        if loading:
            self._count_label.setText("Loading…")

    def _rebuild_grid(self, records: List[dict]):
        self._stop_loader()

        # Clear old cells
        for cell in self._cells:
            cell.deleteLater()
        self._cells.clear()
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not records:
            return

        # Calculate columns from current width
        available = max(self._scroll.width() - 32, THUMB_CELL)
        cols = max(1, available // (THUMB_CELL + 8))

        for i, rec in enumerate(records):
            cell = _ThumbCell(rec, THUMB_CELL, THUMB_IMG)
            self._cells.append(cell)
            self._grid_layout.addWidget(cell, i // cols, i % cols)

        # Start background thumbnail loading
        self._loader = _ThumbnailLoader(records, THUMB_IMG)
        self._loader.start(self._on_thumb_ready)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._filtered:
            # Reflow grid on resize
            QTimer.singleShot(100, lambda: self._rebuild_grid(self._filtered))

    def _on_thumb_ready(self, index: int, img: QImage):
        if 0 <= index < len(self._cells):
            self._cells[index].set_pixmap(QPixmap.fromImage(img))

    def _on_search(self, text: str):
        q = text.strip().lower()
        if not q:
            self._filtered = self._all_records
        else:
            self._filtered = [
                r for r in self._all_records
                if q in r.get("filename", "").lower()
            ]
        self._rebuild_grid(self._filtered)
        n = len(self._filtered)
        self._count_label.setText(f"{n:,} file{'s' if n != 1 else ''}")

    def _on_export(self):
        import csv as _csv
        if not self._filtered:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Photo List", "photos.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        keys = ["filename", "size", "local_path", "rel_path"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = _csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self._filtered)
        if self._case_log:
            self._case_log.log_export(path, len(self._filtered))
