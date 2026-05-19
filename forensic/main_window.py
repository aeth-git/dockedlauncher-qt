"""ForensicWindow — the main application window."""
import os
import sys
from typing import List, Optional

from PyQt5.QtCore import (
    Qt, QObject, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve,
    QTimer,
)
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QKeySequence
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTabBar, QStackedWidget, QStatusBar, QFileDialog, QMessageBox,
    QInputDialog, QApplication, QFrame, QShortcut, QSizePolicy, QProgressDialog,
)

from .constants import (
    PAPER, HAIRLINE, INK, INK_MUTED, INK_SOFT, RED, RED_LIGHT, FONT_FAMILY,
    FONT_SIZE_TITLE, FONT_SIZE_DATA, FONT_SIZE_LABEL,
    WINDOW_MIN_W, WINDOW_MIN_H, WINDOW_DEFAULT_W, WINDOW_DEFAULT_H,
    SOURCE_BAR_H, DEVICE_INFO_BAR_H,
)
from .case_log import CaseLog
from .logger import get_logger
from .sources.base import DataSource
from .views.messages_view import MessagesView
from .views.calls_view import CallsView
from .views.contacts_view import ContactsView
from .views.photos_view import PhotosView
from .views.apps_view import AppsView
from .views.safari_view import SafariView
from .views.notes_view import NotesView
from .views.calendar_view import CalendarView
from .views.voicemail_view import VoicemailView
from .views.location_view import LocationView
from .views.wifi_view import WiFiView
from .views.mail_view import MailView
from .views.screentime_view import ScreenTimeView
from .views.timeline_view import TimelineView
from .views.report_view import ReportView
from .views.knowledgec_view import KnowledgeCView
from .views.interactionc_view import InteractionCView
from .views.tcc_view import TCCView
from .views.data_usage_view import DataUsageView
from .views.accounts_view import AccountsView
from .views.wallet_view import WalletView
from .views.reminders_view import RemindersView
from .views.bluetooth_view import BluetoothView
from .views.deleted_apps_view import DeletedAppsView
from .views.sms_recovery_view import SMSRecoveryView
from .views.biome_view import BiomeView
from .views.health_view import HealthView
from .views.ioc_view import IOCView
from .views.safari_cloud_tabs_view import SafariCloudTabsView
from .views.safari_downloads_view import SafariDownloadsView
from .views.safari_bookmarks_view import SafariBookmarksView
from .views.safari_cookies_view import SafariBinaryCookiesView
from .views.siri_view import SiriView
from .views.app_store_view import AppStoreView
from .views.spotlight_view import SpotlightView
from .views.location_cloud_view import LocationCloudView
from .views.crash_logs_view import CrashLogsView
from .views.springboard_view import SpringBoardView
from .views.homekit_view import HomeKitView
from .views.powerlog_view import PowerLogView
from .views.agg_dict_view import AggregatedDictView

_log = get_logger("main_window")

MAIN_TAB_QSS = f"""
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {HAIRLINE};
}}
QTabBar::tab {{
    background: {PAPER};
    color: {INK_MUTED};
    font-family: {FONT_FAMILY};
    font-size: 11px;
    padding: 10px 24px;
    border: none;
    border-bottom: 2px solid transparent;
    min-width: 80px;
}}
QTabBar::tab:selected {{
    color: {INK};
    border-bottom: 2px solid {RED};
}}
QTabBar::tab:hover:!selected {{
    color: {INK_SOFT};
    background: #f2f2f2;
}}
QTabBar {{
    background: {PAPER};
    border-bottom: 1px solid {HAIRLINE};
}}
"""

CARD_QSS_BASE = f"""
QFrame {{
    background: {PAPER};
    border: 1px solid {HAIRLINE};
}}
QFrame:hover {{
    background: #f2f2f2;
    border-color: {INK};
}}
"""

CARD_QSS_ACTIVE = f"""
QFrame {{
    background: {RED_LIGHT};
    border: 1px solid {RED};
}}
"""


# ── Worker ────────────────────────────────────────────────────────────────────

class _Worker(QObject):
    """Runs a parser.parse() in a background thread. Carries a session token."""
    finished = pyqtSignal(int, list)    # (token, records)
    error    = pyqtSignal(int, str, str) # (token, title, detail)

    def __init__(self, token: int, parser_cls, source: DataSource):
        super().__init__()
        self._token = token
        self._parser_cls = parser_cls
        self._source = source

    def run(self):
        # SQLite connections must be created in the thread that uses them
        try:
            parser = self._parser_cls(self._source)
            records = parser.parse()
            self.finished.emit(self._token, records)
        except Exception as e:
            title = type(e).__name__
            detail = str(e)
            _log.warning("Parser %s failed: %s", self._parser_cls.__name__, e)
            self.error.emit(self._token, title, detail)


class _ExtractWorker(QObject):
    """Runs BackupExtractor.extract() in a background thread."""
    progress = pyqtSignal(int, int, str)   # (done, total, current_path)
    finished = pyqtSignal(int, int, int, list)  # (total, copied, skipped, errors)
    error    = pyqtSignal(str)

    def __init__(self, extractor):
        super().__init__()
        self._extractor = extractor
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            result = self._extractor.extract(
                progress_cb=lambda done, total, path: self.progress.emit(done, total, path),
                cancelled_cb=lambda: self._cancelled,
            )
            self.finished.emit(result.total, result.copied, result.skipped, result.errors)
        except Exception as e:
            self.error.emit(str(e))


def _start_worker(token, parser_cls, source, on_done, on_error):
    """Create a QObject worker, move it to a QThread, wire signals, start."""
    thread = QThread()
    worker = _Worker(token, parser_cls, source)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(lambda tok, recs: on_done(tok, recs))
    worker.error.connect(lambda tok, t, d: on_error(tok, t, d))
    worker.finished.connect(thread.quit)
    worker.error.connect(thread.quit)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker


# ── Source Card ───────────────────────────────────────────────────────────────

class _SourceCard(QFrame):
    """Large clickable card for source selection."""

    def __init__(self, icon_char: str, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 110)
        self.setStyleSheet(CARD_QSS_BASE)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        icon_lbl = QLabel(icon_char)
        icon_lbl.setAlignment(Qt.AlignLeft)
        icon_lbl.setStyleSheet(
            f"color:{INK}; font-size:20px; border:none; background:transparent;"
        )
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color:{INK}; font-family:{FONT_FAMILY}; font-size:13px; "
            f"font-weight:600; border:none; background:transparent;"
        )
        sub_lbl = QLabel(subtitle)
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet(
            f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; font-size:10px; "
            f"border:none; background:transparent;"
        )

        layout.addWidget(icon_lbl)
        layout.addWidget(title_lbl)
        layout.addWidget(sub_lbl)

    def set_active(self, active: bool):
        self.setStyleSheet(CARD_QSS_ACTIVE if active else CARD_QSS_BASE)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked()

    def clicked(self):
        pass   # overridden by lambda in ForensicWindow


# ── Splash (source selection) ─────────────────────────────────────────────────

class _SplashWidget(QWidget):
    """Full-window splash shown before any source is loaded."""

    def __init__(self, on_backup, on_device, on_image, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{PAPER};")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(32)

        # Logo
        logo = QLabel("iForensic")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(
            f"color:{INK}; font-family:{FONT_FAMILY}; font-size:22px; font-weight:300;"
        )
        sub = QLabel("iPhone Forensic Analyzer")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(
            f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; font-size:12px;"
        )
        layout.addWidget(logo)
        layout.addWidget(sub)

        # Cards row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        cards_row.setAlignment(Qt.AlignCenter)

        self._card_backup = _SourceCard("▤", "iTunes Backup",
                                         "Open a backup folder from\niTunes or Finder")
        self._card_device = _SourceCard("◈", "Live Device",
                                         "Connect an iPhone\nover USB")
        self._card_image  = _SourceCard("⊞", "Forensic Image",
                                         "Open a folder, .zip,\nor .tar archive")

        self._card_backup.clicked = on_backup
        self._card_device.clicked = on_device
        self._card_image.clicked  = on_image

        cards_row.addWidget(self._card_backup)
        cards_row.addWidget(self._card_device)
        cards_row.addWidget(self._card_image)

        cards_widget = QWidget()
        cards_widget.setLayout(cards_row)
        layout.addWidget(cards_widget)

        hint = QLabel("Double-click a card to open a source")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(
            f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; font-size:10px;"
        )
        layout.addWidget(hint)


# ── Slim source bar (shown after load) ───────────────────────────────────────

class _SlimBar(QWidget):
    """Thin 52px bar showing active source + device info + action buttons."""

    def __init__(self, on_change, on_extract, parent=None):
        super().__init__(parent)
        self.setFixedHeight(SOURCE_BAR_H)
        self.setStyleSheet(
            f"background:{PAPER}; border-bottom:1px solid {HAIRLINE};"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 0, 16, 0)

        # Logo mark
        mark = QLabel()
        mark.setFixedSize(12, 12)
        mark.setStyleSheet(f"background:{RED};")

        name = QLabel("iForensic")
        name.setStyleSheet(
            f"color:{INK}; font-family:{FONT_FAMILY}; font-size:13px; font-weight:600;"
        )

        sep = QLabel("·")
        sep.setStyleSheet(f"color:{RED}; font-size:14px; margin:0 4px;")

        self._source_label = QLabel("No source")
        self._source_label.setStyleSheet(
            f"color:{INK_SOFT}; font-family:{FONT_FAMILY}; font-size:11px;"
        )

        self._device_label = QLabel()
        self._device_label.setStyleSheet(
            f"color:{INK_MUTED}; font-family:{FONT_FAMILY}; font-size:10px;"
        )
        self._device_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        _btn_qss = (
            f"QPushButton {{ background:{PAPER}; color:{INK}; border:1px solid {HAIRLINE};"
            f" font-family:{FONT_FAMILY}; font-size:10px; padding:0 10px; }}"
            f"QPushButton:hover {{ border-color:{INK}; }}"
        )

        extract_btn = QPushButton("Full Filesystem Extraction")
        extract_btn.setFixedHeight(26)
        extract_btn.setStyleSheet(_btn_qss)
        extract_btn.setCursor(Qt.PointingHandCursor)
        extract_btn.clicked.connect(on_extract)

        change_btn = QPushButton("Change Source")
        change_btn.setFixedHeight(26)
        change_btn.setStyleSheet(_btn_qss)
        change_btn.setCursor(Qt.PointingHandCursor)
        change_btn.clicked.connect(on_change)

        row.addWidget(mark)
        row.addSpacing(8)
        row.addWidget(name)
        row.addWidget(sep)
        row.addWidget(self._source_label)
        row.addSpacing(16)
        row.addWidget(self._device_label, 1)
        row.addWidget(extract_btn)
        row.addSpacing(6)
        row.addWidget(change_btn)

    def set_source(self, source_label: str, device_info: dict):
        self._source_label.setText(source_label)
        parts = []
        if device_info.get("name"):
            parts.append(device_info["name"])
        if device_info.get("ios_version"):
            parts.append(f"iOS {device_info['ios_version']}")
        if device_info.get("serial"):
            parts.append(f"SN: {device_info['serial']}")
        if device_info.get("imei"):
            parts.append(f"IMEI: {device_info['imei']}")
        self._device_label.setText("  ·  ".join(parts))


# ── Main Window ───────────────────────────────────────────────────────────────

class ForensicWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("iForensic — iPhone Forensic Analyzer")
        self.setMinimumSize(WINDOW_MIN_W, WINDOW_MIN_H)
        self.resize(WINDOW_DEFAULT_W, WINDOW_DEFAULT_H)
        self.setStyleSheet(f"QMainWindow {{ background:{PAPER}; }}")

        self._case_log = CaseLog()
        self._source: Optional[DataSource] = None
        self._session_token = 0
        self._active_threads: List[QThread] = []

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background:{PAPER};")
        self.setCentralWidget(central)

        self._root_layout = QVBoxLayout(central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        # Stacked: splash (0) vs loaded (1)
        self._top_stack = QStackedWidget()

        self._splash = _SplashWidget(
            on_backup=self._select_backup,
            on_device=self._select_device,
            on_image=self._select_image,
        )
        self._slim_bar = _SlimBar(on_change=self._go_splash, on_extract=self._select_extract)
        self._slim_bar.hide()  # hidden until source loaded

        self._root_layout.addWidget(self._slim_bar)

        # Content stack: splash vs tabs
        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(self._splash)          # 0

        self._tabs_widget = self._build_tabs()
        self._content_stack.addWidget(self._tabs_widget)      # 1

        self._root_layout.addWidget(self._content_stack, 1)

        # Status bar
        self._status = QStatusBar()
        self._status.setStyleSheet(
            f"QStatusBar {{ background:{PAPER}; color:{INK_MUTED}; "
            f"font-family:{FONT_FAMILY}; font-size:10px; border-top:1px solid {HAIRLINE}; }}"
        )
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — open a source to begin.")

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setStyleSheet(MAIN_TAB_QSS)
        tabs.setDocumentMode(True)

        self._msg_view        = MessagesView(case_log=self._case_log)
        self._calls_view      = CallsView(case_log=self._case_log)
        self._contacts_view   = ContactsView(case_log=self._case_log)
        self._photos_view     = PhotosView(case_log=self._case_log)
        self._apps_view       = AppsView(case_log=self._case_log)
        self._safari_view     = SafariView(case_log=self._case_log)
        self._notes_view      = NotesView(case_log=self._case_log)
        self._calendar_view   = CalendarView(case_log=self._case_log)
        self._voicemail_view  = VoicemailView(case_log=self._case_log)
        self._location_view   = LocationView(case_log=self._case_log)
        self._wifi_view       = WiFiView(case_log=self._case_log)
        self._mail_view       = MailView(case_log=self._case_log)
        self._screentime_view = ScreenTimeView(case_log=self._case_log)
        self._timeline_view      = TimelineView(case_log=self._case_log)
        self._knowledgec_view    = KnowledgeCView(case_log=self._case_log)
        self._interactionc_view  = InteractionCView(case_log=self._case_log)
        self._tcc_view           = TCCView(case_log=self._case_log)
        self._data_usage_view    = DataUsageView(case_log=self._case_log)
        self._accounts_view      = AccountsView(case_log=self._case_log)
        self._wallet_view        = WalletView(case_log=self._case_log)
        self._reminders_view     = RemindersView(case_log=self._case_log)
        self._bluetooth_view     = BluetoothView(case_log=self._case_log)
        self._deleted_apps_view  = DeletedAppsView(case_log=self._case_log)
        self._sms_recovery_view  = SMSRecoveryView(case_log=self._case_log)
        self._biome_view         = BiomeView(case_log=self._case_log)
        self._health_view        = HealthView(case_log=self._case_log)
        self._ioc_view           = IOCView(case_log=self._case_log)
        self._safari_tabs_view   = SafariCloudTabsView(case_log=self._case_log)
        self._safari_dl_view     = SafariDownloadsView(case_log=self._case_log)
        self._safari_bm_view     = SafariBookmarksView(case_log=self._case_log)
        self._safari_cookies_view = SafariBinaryCookiesView(case_log=self._case_log)
        self._siri_view          = SiriView(case_log=self._case_log)
        self._app_store_view     = AppStoreView(case_log=self._case_log)
        self._spotlight_view     = SpotlightView(case_log=self._case_log)
        self._location_cloud_view = LocationCloudView(case_log=self._case_log)
        self._crash_logs_view    = CrashLogsView(case_log=self._case_log)
        self._springboard_view   = SpringBoardView(case_log=self._case_log)
        self._homekit_view       = HomeKitView(case_log=self._case_log)
        self._powerlog_view      = PowerLogView(case_log=self._case_log)
        self._agg_dict_view      = AggregatedDictView(case_log=self._case_log)
        self._report_view        = ReportView()

        tabs.addTab(self._ioc_view,          "Security")
        tabs.addTab(self._timeline_view,     "Timeline")
        tabs.addTab(self._msg_view,          "Messages")
        tabs.addTab(self._calls_view,        "Calls")
        tabs.addTab(self._voicemail_view,    "Voicemail")
        tabs.addTab(self._contacts_view,     "Contacts")
        tabs.addTab(self._photos_view,       "Photos")
        tabs.addTab(self._safari_view,       "Safari")
        tabs.addTab(self._mail_view,         "Mail")
        tabs.addTab(self._notes_view,        "Notes")
        tabs.addTab(self._calendar_view,     "Calendar")
        tabs.addTab(self._reminders_view,    "Reminders")
        tabs.addTab(self._location_view,     "Location")
        tabs.addTab(self._wifi_view,         "WiFi")
        tabs.addTab(self._screentime_view,   "Screen Time")
        tabs.addTab(self._knowledgec_view,   "KnowledgeC")
        tabs.addTab(self._interactionc_view, "Interactions")
        tabs.addTab(self._biome_view,        "Biome")
        tabs.addTab(self._health_view,       "Health")
        tabs.addTab(self._tcc_view,          "Permissions")
        tabs.addTab(self._data_usage_view,   "Data Usage")
        tabs.addTab(self._accounts_view,     "Accounts")
        tabs.addTab(self._wallet_view,       "Wallet")
        tabs.addTab(self._bluetooth_view,    "Bluetooth")
        tabs.addTab(self._deleted_apps_view, "Deleted Apps")
        tabs.addTab(self._sms_recovery_view, "SMS Recovery")
        tabs.addTab(self._apps_view,         "Apps")
        tabs.addTab(self._safari_tabs_view,  "Cloud Tabs")
        tabs.addTab(self._safari_dl_view,    "Downloads")
        tabs.addTab(self._safari_bm_view,    "Bookmarks")
        tabs.addTab(self._safari_cookies_view, "Cookies")
        tabs.addTab(self._siri_view,         "Siri")
        tabs.addTab(self._app_store_view,    "App Store")
        tabs.addTab(self._spotlight_view,    "Spotlight")
        tabs.addTab(self._location_cloud_view, "Sig. Locations")
        tabs.addTab(self._crash_logs_view,   "Crash Logs")
        tabs.addTab(self._springboard_view,  "Home Screen")
        tabs.addTab(self._homekit_view,      "HomeKit")
        tabs.addTab(self._powerlog_view,     "PowerLog")
        tabs.addTab(self._agg_dict_view,     "Agg. Metrics")
        tabs.addTab(self._report_view,       "Report")

        return tabs

    # ── Source selection ──────────────────────────────────────────────────────

    def _go_splash(self):
        self._cancel_all_workers()
        if self._source:
            self._source.close()
            self._source = None
        self._slim_bar.hide()
        self._content_stack.setCurrentIndex(0)
        self._status.showMessage("Ready — open a source to begin.")

    def _select_backup(self):
        default = _default_backup_dir()
        path = QFileDialog.getExistingDirectory(
            self, "Select iTunes/Finder Backup Folder", default
        )
        if not path:
            return
        self._open_source("backup", path)

    def _select_device(self):
        try:
            from .sources.device import list_connected_devices
        except ImportError:
            QMessageBox.warning(
                self, "pymobiledevice3 not installed",
                "Install it with:\n  pip install pymobiledevice3"
            )
            return
        devices = list_connected_devices()
        if not devices:
            QMessageBox.information(
                self, "No Device Found",
                "No iPhone detected over USB.\n\n"
                "Make sure the iPhone is connected, unlocked, and you have "
                "tapped 'Trust' on the device."
            )
            return
        self._open_source("device", devices[0]["udid"])

    def _select_image(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Forensic Image Folder", os.path.expanduser("~")
        )
        if not path:
            # Also try file dialog for archives
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Forensic Image Archive",
                os.path.expanduser("~"),
                "Archives (*.zip *.tar *.tar.gz *.tgz *.tar.bz2 *.tar.xz)"
            )
        if not path:
            return
        self._open_source("image", path)

    def _select_extract(self):
        if not self._source:
            return

        from .extractor import BackupExtractor, _backup_parts
        root, file_map = _backup_parts(self._source)
        if root is None:
            QMessageBox.warning(
                self, "Not Supported",
                "Full extraction is not available for live-device sources.\n"
                "Use a backup or forensic image instead."
            )
            return

        dest = QFileDialog.getExistingDirectory(
            self, "Select Output Directory for Extracted Files",
            os.path.expanduser("~")
        )
        if not dest:
            return

        extractor = BackupExtractor(self._source, dest, self._case_log)

        progress = QProgressDialog("Preparing extraction…", "Cancel", 0, 0, self)
        progress.setWindowTitle("Extracting Files")
        progress.setMinimumDuration(0)
        progress.setMinimumWidth(420)
        progress.setValue(0)

        thread = QThread()
        worker = _ExtractWorker(extractor)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def _on_progress(done, total, path):
            progress.setMaximum(total)
            progress.setValue(done)
            short = path[-55:] if len(path) > 55 else path
            progress.setLabelText(f"Extracting {done:,} / {total:,} files\n{short}")

        def _on_finished(total, copied, skipped, errors):
            progress.close()
            thread.quit()
            self._status.showMessage(
                f"Extraction complete — {copied:,} files written to {dest}"
            )
            msg = (
                f"Extraction complete.\n\n"
                f"Files copied:   {copied:,}\n"
                f"Files skipped:  {skipped:,}\n"
                f"Errors:         {len(errors)}\n\n"
                f"Output:\n{dest}"
            )
            if errors:
                shown = errors[:5]
                msg += "\n\nFirst error(s):\n" + "\n".join(shown)
                if len(errors) > 5:
                    msg += f"\n… and {len(errors) - 5} more"
            QMessageBox.information(self, "Extraction Complete", msg)

        def _on_error(msg):
            progress.close()
            thread.quit()
            QMessageBox.critical(self, "Extraction Failed", msg)

        worker.progress.connect(_on_progress)
        worker.finished.connect(_on_finished)
        worker.error.connect(_on_error)
        progress.canceled.connect(worker.cancel)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        progress.exec_()

    def _open_source(self, source_type: str, path: str):
        self._cancel_all_workers()
        if self._source:
            self._source.close()
            self._source = None

        self._status.showMessage("Opening source…")

        from .sources.backup import BackupSource, EncryptedBackupNeedsPassword
        try:
            if source_type == "backup":
                src = BackupSource(path)
                label = "iTunes Backup"
            elif source_type == "device":
                from .sources.device import DeviceSource
                src = DeviceSource(path)
                label = "Live Device"
            else:
                from .sources.image import ImageSource
                src = ImageSource(path)
                label = "Forensic Image"

            try:
                src.open()
            except EncryptedBackupNeedsPassword:
                from PyQt5.QtWidgets import QLineEdit
                while True:
                    pwd, ok = QInputDialog.getText(
                        self, "Encrypted Backup",
                        "This backup is encrypted. Enter the backup password:",
                        QLineEdit.Password,
                    )
                    if not ok or not pwd:
                        return
                    src = BackupSource(path, password=pwd)
                    try:
                        src.open()
                        break
                    except PermissionError as pe:
                        retry = QMessageBox.question(
                            self, "Decryption Failed",
                            f"{pe}\n\nTry a different password?",
                            QMessageBox.Yes | QMessageBox.No,
                        )
                        if retry != QMessageBox.Yes:
                            return
        except PermissionError as e:
            QMessageBox.critical(self, "Permission Denied", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Failed to Open Source", str(e))
            self._status.showMessage(f"Error: {e}")
            return

        self._source = src
        device_info = src.get_device_info()

        # Log to case log
        mhash = src.manifest_hash() if hasattr(src, "manifest_hash") else None
        if mhash:
            self._case_log.log_source_opened(path, mhash)
        else:
            self._case_log.log_source_opened(path)

        # Wire report view
        self._report_view.set_source(path, device_info, mhash)

        # Show slim bar + switch to tabs
        self._slim_bar.set_source(label, device_info)
        self._slim_bar.show()
        self._content_stack.setCurrentIndex(1)

        # Start loading all parsers
        self._load_all_parsers()

    # ── Parser loading ────────────────────────────────────────────────────────

    def _load_all_parsers(self):
        self._session_token += 1
        token = self._session_token

        self._total_count = 0
        self._loaded_count = 0
        self._status.showMessage("Loading data…")

        # ── Apple system parsers ─────────────────────────────────────────────
        from .parsers.messages  import SMSParser
        from .parsers.calls     import CallParser
        from .parsers.contacts  import ContactsParser
        from .parsers.photos    import PhotoIndexer
        from .parsers.apps      import InstalledAppsParser
        from .parsers.safari    import SafariParser
        from .parsers.notes     import NotesParser
        from .parsers.calendar  import CalendarParser
        from .parsers.voicemail import VoicemailParser
        from .parsers.location  import LocationParser
        from .parsers.wifi      import WiFiParser
        from .parsers.mail      import MailParser
        from .parsers.screentime import ScreenTimeParser

        def _tl(etype, recs):
            self._timeline_view.feed_records(etype, etype.capitalize(), recs)

        def _report(name, recs):
            self._report_view.add_section(name, recs)

        self._launch(token, SMSParser,
                     lambda recs: (self._msg_view.load_app_records("sms", recs),
                                   _tl("sms", recs), _report("SMS / iMessage", recs)),
                     lambda t, d: self._msg_view.load_app_records("sms", None, t, d))

        self._launch(token, CallParser,
                     lambda recs: (self._calls_view.load_records(recs),
                                   _tl("call", recs), _report("Call History", recs)),
                     lambda t, d: self._calls_view.show_error(t, d))

        self._launch(token, ContactsParser,
                     lambda recs: (self._contacts_view.load_records(recs),
                                   _report("Contacts", recs)),
                     lambda t, d: self._contacts_view.show_error(t, d))

        self._launch(token, PhotoIndexer,
                     lambda recs: (self._photos_view.load_records(recs),
                                   _tl("photo", recs), _report("Photos", recs)),
                     lambda t, d: None)

        self._launch(token, InstalledAppsParser,
                     lambda recs: (self._apps_view.load_records(recs),
                                   _report("Installed Apps", recs)),
                     lambda t, d: self._apps_view.show_error(t, d))

        self._launch(token, SafariParser,
                     lambda recs: (self._safari_view.load_records(recs),
                                   _tl("safari", recs), _report("Safari History", recs)),
                     lambda t, d: self._safari_view.show_error(t, d))

        self._launch(token, NotesParser,
                     lambda recs: (self._notes_view.load_records(recs),
                                   _tl("note", recs), _report("Notes", recs)),
                     lambda t, d: self._notes_view.show_error(t, d))

        self._launch(token, CalendarParser,
                     lambda recs: (self._calendar_view.load_records(recs),
                                   _tl("calendar", recs), _report("Calendar Events", recs)),
                     lambda t, d: self._calendar_view.show_error(t, d))

        self._launch(token, VoicemailParser,
                     lambda recs: (self._voicemail_view.load_records(recs),
                                   _tl("voicemail", recs), _report("Voicemail", recs)),
                     lambda t, d: self._voicemail_view.show_error(t, d))

        self._launch(token, LocationParser,
                     lambda recs: (self._location_view.load_records(recs),
                                   _tl("location", recs), _report("Location History", recs)),
                     lambda t, d: self._location_view.show_error(t, d))

        self._launch(token, WiFiParser,
                     lambda recs: (self._wifi_view.load_records(recs),
                                   _report("Known WiFi Networks", recs)),
                     lambda t, d: self._wifi_view.show_error(t, d))

        self._launch(token, MailParser,
                     lambda recs: (self._mail_view.load_records(recs),
                                   _tl("mail", recs), _report("Mail", recs)),
                     lambda t, d: self._mail_view.show_error(t, d))

        self._launch(token, ScreenTimeParser,
                     lambda recs: (self._screentime_view.load_records(recs),
                                   _report("Screen Time", recs)),
                     lambda t, d: self._screentime_view.show_error(t, d))

        # ── Third-party messaging ────────────────────────────────────────────
        from .parsers.thirdparty.whatsapp  import WhatsAppParser
        from .parsers.thirdparty.telegram  import TelegramParser
        from .parsers.thirdparty.signal    import SignalParser
        from .parsers.thirdparty.messenger import MessengerParser
        from .parsers.thirdparty.instagram import InstagramParser
        from .parsers.thirdparty.snapchat  import SnapchatParser
        from .parsers.thirdparty.viber     import ViberParser
        from .parsers.thirdparty.line      import LINEParser
        from .parsers.thirdparty.wechat    import WeChatParser
        from .parsers.thirdparty.discord   import DiscordParser
        from .parsers.thirdparty.skype     import SkypeParser

        for key, label, parser_cls in [
            ("whatsapp",  "WhatsApp",  WhatsAppParser),
            ("telegram",  "Telegram",  TelegramParser),
            ("signal",    "Signal",    SignalParser),
            ("messenger", "Messenger", MessengerParser),
            ("instagram", "Instagram", InstagramParser),
            ("snapchat",  "Snapchat",  SnapchatParser),
            ("viber",     "Viber",     ViberParser),
            ("line",      "LINE",      LINEParser),
            ("wechat",    "WeChat",    WeChatParser),
            ("discord",   "Discord",   DiscordParser),
            ("skype",     "Skype",     SkypeParser),
        ]:
            k, lbl = key, label

            def _done(recs, k=k, lbl=lbl):
                self._msg_view.load_app_records(k, recs)
                _tl(k, recs)
                _report(lbl, recs)

            def _err(t, d, k=k):
                self._msg_view.load_app_records(k, None, t, d)

            self._launch(token, parser_cls, _done, _err)

        # ── Kik (third-party messaging sub-tab) ─────────────────────────────
        from .parsers.thirdparty.kik import KikParser

        def _kik_done(recs):
            self._msg_view.load_app_records("kik", recs)
            _tl("kik", recs)
            _report("Kik", recs)

        self._launch(token, KikParser, _kik_done,
                     lambda t, d: self._msg_view.load_app_records("kik", None, t, d))

        # ── Pattern-of-life & device state ──────────────────────────────────
        from .parsers.knowledgec   import KnowledgeCParser
        from .parsers.interactionc import InteractionCParser
        from .parsers.biome        import BiomeParser

        self._launch(token, KnowledgeCParser,
                     lambda recs: (self._knowledgec_view.load_records(recs),
                                   _tl("knowledgec", recs),
                                   _report("KnowledgeC (Pattern of Life)", recs)),
                     lambda t, d: self._knowledgec_view.show_error(t, d))

        self._launch(token, InteractionCParser,
                     lambda recs: (self._interactionc_view.load_records(recs),
                                   _tl("interaction", recs),
                                   _report("Interactions (InteractionC)", recs)),
                     lambda t, d: self._interactionc_view.show_error(t, d))

        self._launch(token, BiomeParser,
                     lambda recs: (self._biome_view.load_records(recs),
                                   _report("Biome Streams", recs)),
                     lambda t, d: self._biome_view.show_error(t, d))

        # ── Privacy & security ───────────────────────────────────────────────
        from .parsers.tcc        import TCCParser
        from .parsers.data_usage import DataUsageParser
        from .parsers.ioc_checker import IOCChecker

        self._launch(token, TCCParser,
                     lambda recs: (self._tcc_view.load_records(recs),
                                   _report("App Permissions (TCC)", recs)),
                     lambda t, d: self._tcc_view.show_error(t, d))

        self._launch(token, DataUsageParser,
                     lambda recs: (self._data_usage_view.load_records(recs),
                                   _report("Data Usage", recs)),
                     lambda t, d: self._data_usage_view.show_error(t, d))

        self._launch(token, IOCChecker,
                     lambda recs: (self._ioc_view.load_records(recs),
                                   _report("Security / IOC", recs)),
                     lambda t, d: self._ioc_view.show_error(t, d))

        # ── Accounts, wallet, health ─────────────────────────────────────────
        from .parsers.accounts import AccountsParser
        from .parsers.wallet   import WalletParser
        from .parsers.health   import HealthParser
        from .parsers.reminders import RemindersParser

        self._launch(token, AccountsParser,
                     lambda recs: (self._accounts_view.load_records(recs),
                                   _report("Accounts", recs)),
                     lambda t, d: self._accounts_view.show_error(t, d))

        self._launch(token, WalletParser,
                     lambda recs: (self._wallet_view.load_records(recs),
                                   _tl("wallet", recs),
                                   _report("Apple Wallet", recs)),
                     lambda t, d: self._wallet_view.show_error(t, d))

        self._launch(token, HealthParser,
                     lambda recs: (self._health_view.load_records(recs),
                                   _report("Health", recs)),
                     lambda t, d: self._health_view.show_error(t, d))

        self._launch(token, RemindersParser,
                     lambda recs: (self._reminders_view.load_records(recs),
                                   _tl("reminder", recs),
                                   _report("Reminders", recs)),
                     lambda t, d: self._reminders_view.show_error(t, d))

        # ── Bluetooth, deleted apps, SMS recovery ────────────────────────────
        from .parsers.bluetooth    import BluetoothParser
        from .parsers.deleted_apps import DeletedAppsParser
        from .parsers.sms_recovery import SMSRecoveryParser

        self._launch(token, BluetoothParser,
                     lambda recs: (self._bluetooth_view.load_records(recs),
                                   _report("Bluetooth Devices", recs)),
                     lambda t, d: self._bluetooth_view.show_error(t, d))

        self._launch(token, DeletedAppsParser,
                     lambda recs: (self._deleted_apps_view.load_records(recs),
                                   _report("Deleted Apps", recs)),
                     lambda t, d: self._deleted_apps_view.show_error(t, d))

        self._launch(token, SMSRecoveryParser,
                     lambda recs: (self._sms_recovery_view.load_records(recs),
                                   _report("SMS Deletion Events", recs)),
                     lambda t, d: self._sms_recovery_view.show_error(t, d))

        # ── Safari extended ──────────────────────────────────────────────────
        from .parsers.safari_extended import (
            SafariCloudTabsParser, SafariDownloadsParser, SafariBookmarksParser,
        )
        from .parsers.safari_cookies import SafariBinaryCookiesParser

        self._launch(token, SafariCloudTabsParser,
                     lambda recs: (self._safari_tabs_view.load_records(recs),
                                   _report("Safari Cloud Tabs", recs)),
                     lambda t, d: self._safari_tabs_view.show_error(t, d))

        self._launch(token, SafariDownloadsParser,
                     lambda recs: (self._safari_dl_view.load_records(recs),
                                   _report("Safari Downloads", recs)),
                     lambda t, d: self._safari_dl_view.show_error(t, d))

        self._launch(token, SafariBookmarksParser,
                     lambda recs: (self._safari_bm_view.load_records(recs),
                                   _report("Safari Bookmarks", recs)),
                     lambda t, d: self._safari_bm_view.show_error(t, d))

        self._launch(token, SafariBinaryCookiesParser,
                     lambda recs: (self._safari_cookies_view.load_records(recs),
                                   _report("Safari Cookies", recs)),
                     lambda t, d: self._safari_cookies_view.show_error(t, d))

        # ── Siri + App Store ─────────────────────────────────────────────────
        from .parsers.siri_analytics import SiriAnalyticsParser
        from .parsers.app_store      import AppStorePurchasesParser

        self._launch(token, SiriAnalyticsParser,
                     lambda recs: (self._siri_view.load_records(recs),
                                   _report("Siri Analytics", recs)),
                     lambda t, d: self._siri_view.show_error(t, d))

        self._launch(token, AppStorePurchasesParser,
                     lambda recs: (self._app_store_view.load_records(recs),
                                   _report("App Store Purchases", recs)),
                     lambda t, d: self._app_store_view.show_error(t, d))

        # ── Spotlight + significant locations ────────────────────────────────
        from .parsers.spotlight       import SpotlightParser
        from .parsers.location_cloud  import LocationCloudParser

        self._launch(token, SpotlightParser,
                     lambda recs: (self._spotlight_view.load_records(recs),
                                   _report("Spotlight Index", recs)),
                     lambda t, d: self._spotlight_view.show_error(t, d))

        self._launch(token, LocationCloudParser,
                     lambda recs: (self._location_cloud_view.load_records(recs),
                                   _tl("location_cloud", recs),
                                   _report("Significant Locations", recs)),
                     lambda t, d: self._location_cloud_view.show_error(t, d))

        # ── Crash logs + SpringBoard ─────────────────────────────────────────
        from .parsers.crash_logs  import CrashLogParser
        from .parsers.springboard import SpringBoardParser

        self._launch(token, CrashLogParser,
                     lambda recs: (self._crash_logs_view.load_records(recs),
                                   _report("Crash Logs", recs)),
                     lambda t, d: self._crash_logs_view.show_error(t, d))

        self._launch(token, SpringBoardParser,
                     lambda recs: (self._springboard_view.load_records(recs),
                                   _report("Home Screen Layout", recs)),
                     lambda t, d: self._springboard_view.show_error(t, d))

        # ── HomeKit + PowerLog + Aggregated Metrics ──────────────────────────
        from .parsers.homekit          import HomeKitParser
        from .parsers.powerlog         import PowerLogParser
        from .parsers.aggregated_dict  import AggregatedDictParser

        self._launch(token, HomeKitParser,
                     lambda recs: (self._homekit_view.load_records(recs),
                                   _report("HomeKit Devices", recs)),
                     lambda t, d: self._homekit_view.show_error(t, d))

        self._launch(token, PowerLogParser,
                     lambda recs: (self._powerlog_view.load_records(recs),
                                   _report("PowerLog", recs)),
                     lambda t, d: self._powerlog_view.show_error(t, d))

        self._launch(token, AggregatedDictParser,
                     lambda recs: (self._agg_dict_view.load_records(recs),
                                   _report("Aggregated Metrics", recs)),
                     lambda t, d: self._agg_dict_view.show_error(t, d))

    def _launch(self, token, parser_cls, on_done, on_error):
        self._total_count += 1
        src = self._source

        def _done(tok, recs):
            if tok != self._session_token:
                return    # stale result — discard
            on_done(recs)
            self._tick_progress()

        def _err(tok, title, detail):
            if tok != self._session_token:
                return
            on_error(title, detail)
            self._tick_progress()

        thread, worker = _start_worker(token, parser_cls, src, _done, _err)
        self._active_threads.append(thread)

    def _tick_progress(self):
        self._loaded_count = getattr(self, "_loaded_count", 0) + 1
        total = getattr(self, "_total_count", 12)
        if self._loaded_count >= total:
            self._status.showMessage(
                f"Loaded — {self._loaded_count} parsers complete."
            )
        else:
            self._status.showMessage(
                f"Loading… {self._loaded_count} / {total}"
            )

    def _cancel_all_workers(self):
        self._session_token += 1   # invalidates all in-flight results
        for t in self._active_threads:
            t.quit()
            t.wait(300)
        self._active_threads.clear()

    def closeEvent(self, event):
        self._cancel_all_workers()
        if self._source:
            self._source.close()
        super().closeEvent(event)


def _default_backup_dir() -> str:
    if sys.platform == "win32":
        return os.path.join(
            os.environ.get("APPDATA", ""),
            "Apple Computer", "MobileSync", "Backup"
        )
    elif sys.platform == "darwin":
        return os.path.expanduser(
            "~/Library/Application Support/MobileSync/Backup"
        )
    return os.path.expanduser("~")
