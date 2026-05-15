"""Headless PyQt5 view tests — data loading, search, state transitions."""
import os
import sys
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

# One QApplication for the whole session
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# ── CallsView ─────────────────────────────────────────────────────────────

class TestCallsView:
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from forensic.views.calls_view import CallsView
        self.view = CallsView()
        self.sample = [
            {"id": 1, "timestamp": "2022-06-15 10:00:00", "number": "+15551234567",
             "name": "Alice", "direction": "Outgoing", "status": "Answered",
             "call_type": "Phone", "duration": "2m 15s", "provider": "carrier"},
            {"id": 2, "timestamp": "2022-06-15 11:00:00", "number": "+15559876543",
             "name": "", "direction": "Incoming", "status": "Missed",
             "call_type": "Phone", "duration": "0s", "provider": ""},
            {"id": 3, "timestamp": "2022-06-15 12:00:00", "number": "+15550001111",
             "name": "", "direction": "Incoming", "status": "Answered",
             "call_type": "FaceTime Audio", "duration": "1m 2s", "provider": "FaceTime"},
        ]

    def test_load_records_sets_count(self):
        self.view.load_records(self.sample)
        assert "3" in self.view._count_label.text()

    def test_export_enabled_after_load(self):
        self.view.load_records(self.sample)
        assert self.view._export_btn.isEnabled()

    def test_export_disabled_before_load(self):
        from forensic.views.calls_view import CallsView
        fresh = CallsView()
        assert not fresh._export_btn.isEnabled()

    def test_search_filters_by_name(self):
        self.view.load_records(self.sample)
        self.view._search_box.setText("Alice")
        assert "1" in self.view._count_label.text()

    def test_search_filters_by_number(self):
        self.view.load_records(self.sample)
        self.view._search_box.setText("+15559876543")
        assert "1" in self.view._count_label.text()

    def test_search_case_insensitive(self):
        self.view.load_records(self.sample)
        self.view._search_box.setText("alice")
        assert "1" in self.view._count_label.text()

    def test_search_clear_restores_all(self):
        self.view.load_records(self.sample)
        self.view._search_box.setText("Alice")
        self.view._search_box.clear()
        assert "3" in self.view._count_label.text()

    def test_search_no_results(self):
        self.view.load_records(self.sample)
        self.view._search_box.setText("zzz_no_match")
        assert "0" in self.view._count_label.text()

    def test_show_error_disables_export(self):
        self.view.load_records(self.sample)
        self.view.show_error("Database not found", "sms.db missing")
        assert not self.view._export_btn.isEnabled()

    def test_load_empty_records(self):
        self.view.load_records([])
        assert "0" in self.view._count_label.text()
        assert not self.view._export_btn.isEnabled()

    def test_table_model_row_count(self):
        self.view.load_records(self.sample)
        self.view._search_box.clear()
        # Model is behind a proxy; check via table
        model = self.view._table.model()
        assert model is not None
        assert model.rowCount() == 3

    def test_columns_defined(self):
        from forensic.views.calls_view import _COLUMNS
        keys = [k for k, _ in _COLUMNS]
        assert "timestamp" in keys
        assert "status" in keys
        assert "duration" in keys


# ── ContactsView ──────────────────────────────────────────────────────────

class TestContactsView:
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from forensic.views.contacts_view import ContactsView
        self.view = ContactsView()
        self.sample = [
            {"id": 1, "first": "Alice", "last": "Smith", "middle": "",
             "org": "Acme Corp", "dept": "",
             "phones": [{"value": "+15551234567", "label": "mobile"}],
             "emails": [{"value": "alice@example.com", "label": "work"}]},
            {"id": 2, "first": "Bob", "last": "Jones", "middle": "",
             "org": "", "dept": "",
             "phones": [{"value": "+15559876543", "label": "home"}],
             "emails": []},
        ]

    def test_load_records_count(self):
        self.view.load_records(self.sample)
        assert "2" in self.view._count_label.text()

    def test_search_by_first_name(self):
        self.view.load_records(self.sample)
        self.view._search_box.setText("Alice")
        assert "1" in self.view._count_label.text()

    def test_search_by_phone(self):
        self.view.load_records(self.sample)
        self.view._search_box.setText("+15559876543")
        assert "1" in self.view._count_label.text()

    def test_phones_joined_in_display(self):
        self.view.load_records(self.sample)
        # After load, _all_records should have joined phones
        assert "+15551234567" in self.view._all_records[0].get("phones", "")


# ── AppsView ──────────────────────────────────────────────────────────────

class TestAppsView:
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from forensic.views.apps_view import AppsView
        self.view = AppsView()
        self.sample = [
            {"bundle_id": "net.whatsapp.WhatsApp", "name": "WhatsApp",
             "version": "22.5.1", "author": "WhatsApp Inc.", "genre": "Social"},
            {"bundle_id": "com.apple.Music", "name": "Music",
             "version": "1.0", "author": "Apple", "genre": "Music"},
        ]

    def test_load_and_count(self):
        self.view.load_records(self.sample)
        assert "2" in self.view._count_label.text()

    def test_search_by_bundle(self):
        self.view.load_records(self.sample)
        self.view._search_box.setText("whatsapp")
        assert "1" in self.view._count_label.text()


# ── MessagesView ──────────────────────────────────────────────────────────

class TestMessagesView:
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from forensic.views.messages_view import MessagesView
        self.view = MessagesView()
        self.sms_records = [
            {"timestamp": "2022-06-15 10:00:00", "contact": "+15551234567",
             "chat": "+15551234567", "direction": "Received",
             "service": "iMessage", "body": "Hello!", "attachments": []},
            {"timestamp": "2022-06-15 10:01:00", "contact": "+15551234567",
             "chat": "+15551234567", "direction": "Sent",
             "service": "iMessage", "body": "Hi back", "attachments": []},
        ]

    def test_load_sms_records(self):
        self.view.load_app_records("sms", self.sms_records)
        assert self.view._record_counts.get("sms") == 2

    def test_error_state_does_not_crash(self):
        self.view.load_app_records("signal", None,
                                   "Signal database is encrypted",
                                   "Post-2021 Signal requires SQLCipher")

    def test_not_found_error_does_not_crash(self):
        self.view.load_app_records("whatsapp", None,
                                   "App not found",
                                   "WhatsApp is not installed in this backup")

    def test_snapchat_loads(self):
        snaps = [
            {"timestamp": "2022-06-15 10:00:00", "contact": "alice",
             "chat": "", "direction": "", "service": "Snapchat",
             "body": "[IMAGE]", "attachments": []},
        ]
        self.view.load_app_records("snapchat", snaps)
        assert self.view._record_counts.get("snapchat") == 1

    def test_multiple_apps_independent(self):
        self.view.load_app_records("sms", self.sms_records)
        wa_records = [
            {"timestamp": "2022-06-15 11:00:00", "contact": "Alice",
             "chat": "chat1", "direction": "Received",
             "service": "WhatsApp", "body": "WA msg", "attachments": []},
        ]
        self.view.load_app_records("whatsapp", wa_records)
        assert self.view._record_counts["sms"] == 2
        assert self.view._record_counts["whatsapp"] == 1


# ── PhotosView ────────────────────────────────────────────────────────────

class TestPhotosView:
    @pytest.fixture(autouse=True)
    def setup(self, qapp, backup_root):
        from forensic.views.photos_view import PhotosView
        self.view = PhotosView()
        # Use real photo paths from the backup
        from forensic.sources.backup import BackupSource
        from forensic.parsers.photos import PhotoIndexer
        src = BackupSource(str(backup_root))
        src.open()
        self.records = PhotoIndexer(src).parse()
        src.close()
        yield
        self.view._stop_loader()
        self.view.close()

    def test_load_records_count(self):
        self.view.load_records(self.records)
        assert "3" in self.view._count_label.text()

    def test_cells_created(self):
        self.view.load_records(self.records)
        assert len(self.view._cells) == 3

    def test_export_enabled_after_load(self):
        self.view.load_records(self.records)
        assert self.view._export_btn.isEnabled()

    def test_search_by_filename(self):
        self.view.load_records(self.records)
        self.view._search_box.setText("IMG_0001")
        assert "1" in self.view._count_label.text()

    def test_search_clear_restores(self):
        self.view.load_records(self.records)
        self.view._search_box.setText("IMG_0001")
        self.view._search_box.clear()
        assert "3" in self.view._count_label.text()

    def test_video_cell_created(self):
        self.view.load_records(self.records)
        video_records = [r for r in self.records if r["is_video"]]
        assert len(video_records) == 1


# ── CSV Export ────────────────────────────────────────────────────────────

class TestCsvExport:
    def test_calls_csv_export(self, qapp, tmp_path):
        from forensic.views.calls_view import CallsView
        view = CallsView()
        records = [
            {"id": 1, "timestamp": "2022-06-15 10:00:00", "number": "+15551234567",
             "name": "Alice", "direction": "Outgoing", "status": "Answered",
             "call_type": "Phone", "duration": "2m 15s", "provider": "carrier"},
        ]
        view.load_records(records)
        out = tmp_path / "calls.csv"

        # Monkeypatch QFileDialog to return our path
        from unittest.mock import patch
        with patch("forensic.views.base_view.QFileDialog.getSaveFileName",
                   return_value=(str(out), "CSV Files (*.csv)")):
            view._on_export()

        assert out.exists()
        content = out.read_text(encoding="utf-8-sig")
        assert "Alice" in content
        assert "timestamp" in content

    def test_contacts_csv_flattens_lists(self, qapp, tmp_path):
        from forensic.views.contacts_view import ContactsView
        view = ContactsView()
        records = [
            {"id": 1, "first": "Alice", "last": "Smith", "middle": "",
             "org": "Acme", "dept": "",
             "phones": [{"value": "+15551234567", "label": "mobile"}],
             "emails": [{"value": "alice@example.com", "label": "work"}]},
        ]
        view.load_records(records)
        out = tmp_path / "contacts.csv"
        from unittest.mock import patch
        with patch("forensic.views.base_view.QFileDialog.getSaveFileName",
                   return_value=(str(out), "CSV Files (*.csv)")):
            view._on_export()

        content = out.read_text(encoding="utf-8-sig")
        assert "+15551234567" in content
        assert "alice@example.com" in content


# ── Full pipeline integration ─────────────────────────────────────────────

class TestFullPipeline:
    """Source → Parser → View end-to-end."""

    def test_sms_pipeline(self, qapp, backup_source):
        from forensic.parsers.messages import SMSParser
        from forensic.views.messages_view import MessagesView
        records = SMSParser(backup_source).parse()
        view = MessagesView()
        view.load_app_records("sms", records)
        assert view._record_counts["sms"] == 3

    def test_calls_pipeline(self, qapp, backup_source):
        from forensic.parsers.calls import CallParser
        from forensic.views.calls_view import CallsView
        records = CallParser(backup_source).parse()
        view = CallsView()
        view.load_records(records)
        assert "3" in view._count_label.text()

    def test_contacts_pipeline(self, qapp, backup_source):
        from forensic.parsers.contacts import ContactsParser
        from forensic.views.contacts_view import ContactsView
        records = ContactsParser(backup_source).parse()
        view = ContactsView()
        view.load_records(records)
        assert "2" in view._count_label.text()

    def test_whatsapp_pipeline(self, qapp, backup_source):
        from forensic.parsers.thirdparty.whatsapp import WhatsAppParser
        from forensic.views.messages_view import MessagesView
        records = WhatsAppParser(backup_source).parse()
        view = MessagesView()
        view.load_app_records("whatsapp", records)
        assert view._record_counts["whatsapp"] == 2

    def test_telegram_pipeline(self, qapp, backup_source):
        from forensic.parsers.thirdparty.telegram import TelegramParser
        from forensic.views.messages_view import MessagesView
        records = TelegramParser(backup_source).parse()
        view = MessagesView()
        view.load_app_records("telegram", records)
        assert view._record_counts["telegram"] == 2

    def test_photos_pipeline(self, qapp, backup_source):
        from forensic.parsers.photos import PhotoIndexer
        from forensic.views.photos_view import PhotosView
        records = PhotoIndexer(backup_source).parse()
        view = PhotosView()
        view.load_records(records)
        assert len(view._cells) == 3

    def test_all_parsers_via_zip(self, qapp, backup_root, tmp_path):
        """Zip archive source → all parsers → correct counts."""
        import zipfile
        from forensic.sources.image import ImageSource
        zip_path = tmp_path / "backup.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            for f in backup_root.rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(backup_root))

        from forensic.parsers.messages import SMSParser
        from forensic.parsers.calls import CallParser
        from forensic.parsers.contacts import ContactsParser
        from forensic.parsers.photos import PhotoIndexer

        src = ImageSource(str(zip_path))
        src.open()
        assert len(SMSParser(src).parse()) == 3
        assert len(CallParser(src).parse()) == 3
        assert len(ContactsParser(src).parse()) == 2
        assert len(PhotoIndexer(src).parse()) == 3
        src.close()
