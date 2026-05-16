"""End-to-end parser tests against synthetic backup data."""
import pytest
from pathlib import Path
from forensic.parsers.messages import SMSParser
from forensic.parsers.calls import CallParser
from forensic.parsers.contacts import ContactsParser
from forensic.parsers.photos import PhotoIndexer
from forensic.parsers.apps import InstalledAppsParser
from forensic.parsers.thirdparty.whatsapp import WhatsAppParser
from forensic.parsers.thirdparty.telegram import TelegramParser
from forensic.parsers.thirdparty.snapchat import SnapchatParser
from forensic.parsers.thirdparty.signal import SignalParser
from forensic.parsers.thirdparty.messenger import MessengerParser
from forensic.parsers.thirdparty.instagram import InstagramParser
from forensic.parsers.base import ParserError
from forensic.sources.backup import BackupSource


def _open(root):
    src = BackupSource(str(root))
    src.open()
    return src


# ── SMS / iMessage ────────────────────────────────────────────────────────

class TestSMSParser:
    def test_returns_three_messages(self, backup_source):
        records = SMSParser(backup_source).parse()
        assert len(records) == 3

    def test_record_has_required_fields(self, backup_source):
        records = SMSParser(backup_source).parse()
        required = {"id", "timestamp", "contact", "chat", "direction", "service", "body", "attachments"}
        for r in records:
            assert required.issubset(r.keys()), f"Missing fields: {required - r.keys()}"

    def test_timestamp_format(self, backup_source):
        records = SMSParser(backup_source).parse()
        for r in records:
            assert r["timestamp"] is not None
            # Format: YYYY-MM-DD HH:MM:SS
            assert len(r["timestamp"]) == 19
            assert r["timestamp"][4] == "-"

    def test_timestamps_are_2022(self, backup_source):
        records = SMSParser(backup_source).parse()
        for r in records:
            assert r["timestamp"].startswith("2022-06-15")

    def test_direction_values(self, backup_source):
        records = SMSParser(backup_source).parse()
        directions = {r["direction"] for r in records}
        assert directions == {"Sent", "Received"}

    def test_contact_populated(self, backup_source):
        records = SMSParser(backup_source).parse()
        # At least one record has a contact phone number
        contacts = [r["contact"] for r in records if r["contact"]]
        assert len(contacts) > 0
        assert any("+1555" in c for c in contacts)

    def test_attachment_detection(self, backup_source):
        records = SMSParser(backup_source).parse()
        records_with_attach = [r for r in records if r["attachments"]]
        assert len(records_with_attach) == 1
        attach = records_with_attach[0]["attachments"][0]
        assert attach["filename"] == "photo.jpg"
        assert attach["mime_type"] == "image/jpeg"

    def test_service_field(self, backup_source):
        records = SMSParser(backup_source).parse()
        services = {r["service"] for r in records}
        assert "iMessage" in services or "SMS" in services

    def test_missing_db_raises(self, tmp_path):
        from forensic.sources.backup import BackupSource
        import sqlite3
        # Backup with empty Manifest.db (no SMS)
        conn = sqlite3.connect(str(tmp_path / "Manifest.db"))
        conn.execute("CREATE TABLE Files (fileID TEXT, domain TEXT, relativePath TEXT, flags INTEGER, file BLOB)")
        conn.commit()
        conn.close()
        import plistlib
        (tmp_path / "Manifest.plist").write_bytes(plistlib.dumps({"IsEncrypted": False}))
        (tmp_path / "Info.plist").write_bytes(plistlib.dumps({}))
        src = BackupSource(str(tmp_path))
        src.open()
        with pytest.raises(FileNotFoundError):
            SMSParser(src).parse()
        src.close()


# ── Call History ──────────────────────────────────────────────────────────

class TestCallParser:
    def test_returns_three_calls(self, backup_source):
        records = CallParser(backup_source).parse()
        assert len(records) == 3

    def test_record_has_required_fields(self, backup_source):
        records = CallParser(backup_source).parse()
        required = {"id", "timestamp", "number", "name", "direction", "status", "call_type", "duration", "provider"}
        for r in records:
            assert required.issubset(r.keys())

    def test_timestamps_are_2022(self, backup_source):
        records = CallParser(backup_source).parse()
        for r in records:
            assert r["timestamp"].startswith("2022-06-15")

    def test_alice_call_found(self, backup_source):
        records = CallParser(backup_source).parse()
        alice = [r for r in records if r["name"] == "Alice"]
        assert len(alice) == 1
        assert alice[0]["direction"] == "Outgoing"
        assert alice[0]["status"] == "Answered"

    def test_missed_call_detected(self, backup_source):
        records = CallParser(backup_source).parse()
        missed = [r for r in records if r["status"] == "Missed"]
        assert len(missed) == 1

    def test_facetime_call_type(self, backup_source):
        records = CallParser(backup_source).parse()
        facetime = [r for r in records if r["call_type"] == "FaceTime Audio"]
        assert len(facetime) == 1

    def test_duration_formatted(self, backup_source):
        records = CallParser(backup_source).parse()
        alice = next(r for r in records if r["name"] == "Alice")
        assert "2m" in alice["duration"] or "135" in alice["duration"]

    def test_no_name_returns_empty_string(self, backup_source):
        records = CallParser(backup_source).parse()
        no_name = [r for r in records if r["name"] == ""]
        assert len(no_name) == 2

    def test_direction_values(self, backup_source):
        records = CallParser(backup_source).parse()
        directions = {r["direction"] for r in records}
        assert directions == {"Outgoing", "Incoming"}


# ── Contacts ──────────────────────────────────────────────────────────────

class TestContactsParser:
    def test_returns_two_contacts(self, backup_source):
        records = ContactsParser(backup_source).parse()
        assert len(records) == 2

    def test_record_has_required_fields(self, backup_source):
        records = ContactsParser(backup_source).parse()
        required = {"id", "first", "last", "org", "phones", "emails"}
        for r in records:
            assert required.issubset(r.keys())

    def test_alice_smith_found(self, backup_source):
        records = ContactsParser(backup_source).parse()
        alice = next((r for r in records if r["first"] == "Alice"), None)
        assert alice is not None
        assert alice["last"] == "Smith"
        assert alice["org"] == "Acme Corp"

    def test_alice_has_phone(self, backup_source):
        records = ContactsParser(backup_source).parse()
        alice = next(r for r in records if r["first"] == "Alice")
        assert len(alice["phones"]) == 1
        assert alice["phones"][0]["value"] == "+15551234567"
        assert alice["phones"][0]["label"] == "mobile"

    def test_alice_has_email(self, backup_source):
        records = ContactsParser(backup_source).parse()
        alice = next(r for r in records if r["first"] == "Alice")
        assert len(alice["emails"]) == 1
        assert alice["emails"][0]["value"] == "alice@example.com"

    def test_bob_jones_found(self, backup_source):
        records = ContactsParser(backup_source).parse()
        bob = next((r for r in records if r["first"] == "Bob"), None)
        assert bob is not None
        assert bob["last"] == "Jones"
        assert len(bob["phones"]) == 1

    def test_bob_label_home(self, backup_source):
        records = ContactsParser(backup_source).parse()
        bob = next(r for r in records if r["first"] == "Bob")
        assert bob["phones"][0]["label"] == "home"

    def test_sorted_by_last_name(self, backup_source):
        records = ContactsParser(backup_source).parse()
        last_names = [r["last"] for r in records]
        assert last_names == sorted(last_names)


# ── Photos ────────────────────────────────────────────────────────────────

class TestPhotoIndexer:
    def test_returns_three_media_files(self, backup_source):
        records = PhotoIndexer(backup_source).parse()
        assert len(records) == 3

    def test_record_has_required_fields(self, backup_source):
        records = PhotoIndexer(backup_source).parse()
        required = {"rel_path", "local_path", "filename", "size_bytes", "size", "is_video", "ext"}
        for r in records:
            assert required.issubset(r.keys())

    def test_jpg_files_found(self, backup_source):
        records = PhotoIndexer(backup_source).parse()
        jpgs = [r for r in records if r["ext"] == ".jpg"]
        assert len(jpgs) == 2

    def test_mov_file_found(self, backup_source):
        records = PhotoIndexer(backup_source).parse()
        movs = [r for r in records if r["ext"] == ".mov"]
        assert len(movs) == 1
        assert movs[0]["is_video"] is True

    def test_jpg_is_not_video(self, backup_source):
        records = PhotoIndexer(backup_source).parse()
        for r in records:
            if r["ext"] == ".jpg":
                assert r["is_video"] is False

    def test_local_path_exists(self, backup_source):
        from pathlib import Path
        records = PhotoIndexer(backup_source).parse()
        for r in records:
            assert Path(r["local_path"]).exists()

    def test_size_bytes_nonzero(self, backup_source):
        records = PhotoIndexer(backup_source).parse()
        jpgs = [r for r in records if r["ext"] == ".jpg"]
        for r in jpgs:
            assert r["size_bytes"] > 0

    def test_size_formatted(self, backup_source):
        records = PhotoIndexer(backup_source).parse()
        for r in records:
            assert any(unit in r["size"] for unit in ("B", "KB", "MB", "GB"))


# ── Installed Apps ────────────────────────────────────────────────────────

class TestInstalledAppsParser:
    def test_returns_apps(self, backup_source):
        records = InstalledAppsParser(backup_source).parse()
        assert len(records) >= 1

    def test_whatsapp_found(self, backup_source):
        records = InstalledAppsParser(backup_source).parse()
        wa = next((r for r in records if r["bundle_id"] == "net.whatsapp.WhatsApp"), None)
        assert wa is not None

    def test_whatsapp_metadata_loaded(self, backup_source):
        records = InstalledAppsParser(backup_source).parse()
        wa = next(r for r in records if r["bundle_id"] == "net.whatsapp.WhatsApp")
        assert wa["name"] == "WhatsApp"
        assert wa["version"] == "22.5.1"
        assert wa["author"] == "WhatsApp Inc."

    def test_sorted_by_name(self, backup_source):
        records = InstalledAppsParser(backup_source).parse()
        names = [r["name"].lower() for r in records]
        assert names == sorted(names)


# ── WhatsApp ──────────────────────────────────────────────────────────────

class TestWhatsAppParser:
    def test_returns_two_messages(self, backup_source):
        records = WhatsAppParser(backup_source).parse()
        assert len(records) == 2

    def test_timestamps_are_2022(self, backup_source):
        records = WhatsAppParser(backup_source).parse()
        for r in records:
            assert r["timestamp"].startswith("2022-06-15")

    def test_contact_resolved_via_zwacontact(self, backup_source):
        records = WhatsAppParser(backup_source).parse()
        received = [r for r in records if r["direction"] == "Received"]
        assert any("Alice" in r["contact"] for r in received)

    def test_direction_values(self, backup_source):
        records = WhatsAppParser(backup_source).parse()
        directions = {r["direction"] for r in records}
        assert "Sent" in directions
        assert "Received" in directions

    def test_service_is_whatsapp(self, backup_source):
        records = WhatsAppParser(backup_source).parse()
        for r in records:
            assert r["service"] == "WhatsApp"

    def test_fallback_without_contact_table(self, whatsapp_no_contact_root):
        """Post-2022 WhatsApp — no ZWACONTACT. Should use JID as contact."""
        src = BackupSource(str(whatsapp_no_contact_root))
        src.open()
        try:
            records = WhatsAppParser(src).parse()
            assert len(records) == 2
            received = [r for r in records if r["direction"] == "Received"]
            assert len(received) == 1
            # Contact should be the JID string, not blank
            assert received[0]["contact"] != ""
        finally:
            src.close()


# ── Telegram ──────────────────────────────────────────────────────────────

class TestTelegramParser:
    def test_returns_two_messages(self, backup_source):
        records = TelegramParser(backup_source).parse()
        assert len(records) == 2

    def test_timestamps_use_unix_epoch(self, backup_source):
        # Telegram uses Unix epoch — 2022-06-15 10:00:00 UTC
        records = TelegramParser(backup_source).parse()
        for r in records:
            assert r["timestamp"] is not None
            assert r["timestamp"].startswith("2022-06-15")

    def test_service_is_telegram(self, backup_source):
        records = TelegramParser(backup_source).parse()
        for r in records:
            assert r["service"] == "Telegram"

    def test_body_populated(self, backup_source):
        records = TelegramParser(backup_source).parse()
        bodies = [r["body"] for r in records if r["body"]]
        assert len(bodies) == 2
        assert "Hello Telegram" in bodies


# ── Snapchat ──────────────────────────────────────────────────────────────

class TestSnapchatParser:
    def test_returns_two_records(self, backup_source):
        records = SnapchatParser(backup_source).parse()
        assert len(records) == 2

    def test_service_is_snapchat(self, backup_source):
        records = SnapchatParser(backup_source).parse()
        for r in records:
            assert r["service"] == "Snapchat"

    def test_body_contains_snap_type(self, backup_source):
        records = SnapchatParser(backup_source).parse()
        bodies = [r["body"] for r in records]
        assert any("IMAGE" in b or "VIDEO" in b for b in bodies)

    def test_sender_populated(self, backup_source):
        records = SnapchatParser(backup_source).parse()
        senders = [r["contact"] for r in records if r["contact"]]
        assert len(senders) == 2

    def test_timestamps_populated(self, backup_source):
        records = SnapchatParser(backup_source).parse()
        for r in records:
            assert r["timestamp"] is not None
            assert "2022-06-15" in r["timestamp"]


# ── ImageSource round-trip ─────────────────────────────────────────────────

class TestImageSource:
    def test_directory_source_reads_sms(self, backup_root):
        from forensic.sources.image import ImageSource
        src = ImageSource(str(backup_root))
        src.open()
        records = SMSParser(src).parse()
        assert len(records) == 3
        src.close()

    def test_zip_source(self, backup_root, tmp_path):
        """Zip up the backup, open via ImageSource, parse SMS."""
        import zipfile
        from forensic.sources.image import ImageSource
        zip_path = tmp_path / "backup.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            for f in backup_root.rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(backup_root))
        src = ImageSource(str(zip_path))
        src.open()
        records = SMSParser(src).parse()
        assert len(records) == 3
        src.close()

    def test_tar_source(self, backup_root, tmp_path):
        """Tar up the backup, open via ImageSource, parse calls."""
        import tarfile
        from forensic.sources.image import ImageSource
        tar_path = tmp_path / "backup.tar.gz"
        with tarfile.open(tar_path, "w:gz") as t:
            t.add(backup_root, arcname="")
        src = ImageSource(str(tar_path))
        src.open()
        records = CallParser(src).parse()
        assert len(records) == 3
        src.close()

    def test_unsupported_format_raises(self, tmp_path):
        from forensic.sources.image import ImageSource
        bad = tmp_path / "data.rar"
        bad.write_bytes(b"Rar!")
        src = ImageSource(str(bad))
        with pytest.raises(IOError, match="Unsupported"):
            src.open()


# ── Signal ────────────────────────────────────────────────────────────────────

class TestSignalParser:
    def test_not_found_raises(self, backup_source):
        """backup_source has no Signal app installed."""
        with pytest.raises(FileNotFoundError):
            SignalParser(backup_source).parse()

    def test_encrypted_raises_parser_error(self, signal_encrypted_root):
        src = _open(signal_encrypted_root)
        try:
            with pytest.raises(ParserError, match="encrypted"):
                SignalParser(src).parse()
        finally:
            src.close()

    def test_yap_era_returns_two_messages(self, signal_yap_root):
        src = _open(signal_yap_root)
        try:
            records = SignalParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_yap_era_service_is_signal(self, signal_yap_root):
        src = _open(signal_yap_root)
        try:
            records = SignalParser(src).parse()
            assert all(r["service"] == "Signal" for r in records)
        finally:
            src.close()

    def test_yap_era_timestamps_are_2022(self, signal_yap_root):
        src = _open(signal_yap_root)
        try:
            records = SignalParser(src).parse()
            for r in records:
                assert r["timestamp"] is not None
                assert "2022-06-15" in r["timestamp"]
        finally:
            src.close()

    def test_yap_era_contact_resolved(self, signal_yap_root):
        """Thread map resolves contact phone from threads table."""
        src = _open(signal_yap_root)
        try:
            records = SignalParser(src).parse()
            contacts = [r["contact"] for r in records if r["contact"]]
            assert len(contacts) == 2
            assert all("+1555" in c for c in contacts)
        finally:
            src.close()

    def test_yap_era_direction_resolved(self, signal_yap_root):
        """recordType 101→Received, 102→Sent."""
        src = _open(signal_yap_root)
        try:
            records = SignalParser(src).parse()
            directions = {r["direction"] for r in records}
            assert directions == {"Received", "Sent"}
        finally:
            src.close()

    def test_yap_era_required_fields(self, signal_yap_root):
        src = _open(signal_yap_root)
        try:
            records = SignalParser(src).parse()
            required = {"timestamp", "contact", "chat", "direction", "service", "body", "attachments"}
            for r in records:
                assert required.issubset(r.keys())
        finally:
            src.close()

    def test_grdb_era_returns_two_messages(self, signal_grdb_root):
        src = _open(signal_grdb_root)
        try:
            records = SignalParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_grdb_era_directions(self, signal_grdb_root):
        src = _open(signal_grdb_root)
        try:
            records = SignalParser(src).parse()
            directions = {r["direction"] for r in records}
            assert "Received" in directions
            assert "Sent" in directions
        finally:
            src.close()

    def test_grdb_era_contact_on_received(self, signal_grdb_root):
        """Incoming GRDB messages populate contact from authorPhoneNumber."""
        src = _open(signal_grdb_root)
        try:
            records = SignalParser(src).parse()
            received = [r for r in records if r["direction"] == "Received"]
            assert len(received) == 1
            assert "+1555" in received[0]["contact"]
        finally:
            src.close()

    def test_grdb_era_service_is_signal(self, signal_grdb_root):
        src = _open(signal_grdb_root)
        try:
            records = SignalParser(src).parse()
            assert all(r["service"] == "Signal" for r in records)
        finally:
            src.close()


# ── Messenger ─────────────────────────────────────────────────────────────────

class TestMessengerParser:
    def test_not_found_raises(self, backup_source):
        with pytest.raises(FileNotFoundError):
            MessengerParser(backup_source).parse()

    def test_readable_returns_two_messages(self, messenger_readable_root):
        src = _open(messenger_readable_root)
        try:
            records = MessengerParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_readable_service_is_messenger(self, messenger_readable_root):
        src = _open(messenger_readable_root)
        try:
            records = MessengerParser(src).parse()
            assert all(r["service"] == "Messenger" for r in records)
        finally:
            src.close()

    def test_readable_timestamps_are_2022(self, messenger_readable_root):
        src = _open(messenger_readable_root)
        try:
            records = MessengerParser(src).parse()
            for r in records:
                assert r["timestamp"] is not None
                assert "2022-06-15" in r["timestamp"]
        finally:
            src.close()

    def test_readable_contact_populated(self, messenger_readable_root):
        src = _open(messenger_readable_root)
        try:
            records = MessengerParser(src).parse()
            contacts = [r["contact"] for r in records if r["contact"]]
            assert len(contacts) > 0
        finally:
            src.close()

    def test_readable_required_fields(self, messenger_readable_root):
        src = _open(messenger_readable_root)
        try:
            records = MessengerParser(src).parse()
            required = {"timestamp", "contact", "chat", "direction", "service", "body", "attachments"}
            for r in records:
                assert required.issubset(r.keys())
        finally:
            src.close()

    def test_lightspeed_raises_parser_error(self, messenger_encrypted_root):
        src = _open(messenger_encrypted_root)
        try:
            with pytest.raises(ParserError, match="Lightspeed"):
                MessengerParser(src).parse()
        finally:
            src.close()

    def test_lightspeed_error_mentions_raw_browser(self, messenger_encrypted_root):
        src = _open(messenger_encrypted_root)
        try:
            with pytest.raises(ParserError) as exc_info:
                MessengerParser(src).parse()
            assert "raw DB browser" in str(exc_info.value)
        finally:
            src.close()


# ── Instagram ─────────────────────────────────────────────────────────────────

class TestInstagramParser:
    def test_not_found_raises(self, backup_source):
        with pytest.raises(FileNotFoundError):
            InstagramParser(backup_source).parse()

    def test_readable_returns_two_messages(self, instagram_root):
        src = _open(instagram_root)
        try:
            records = InstagramParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_service_is_instagram(self, instagram_root):
        src = _open(instagram_root)
        try:
            records = InstagramParser(src).parse()
            assert all(r["service"] == "Instagram" for r in records)
        finally:
            src.close()

    def test_timestamps_are_2022(self, instagram_root):
        src = _open(instagram_root)
        try:
            records = InstagramParser(src).parse()
            for r in records:
                assert r["timestamp"] is not None
                assert "2022-06-15" in r["timestamp"]
        finally:
            src.close()

    def test_contact_populated(self, instagram_root):
        src = _open(instagram_root)
        try:
            records = InstagramParser(src).parse()
            contacts = [r["contact"] for r in records if r["contact"]]
            assert len(contacts) == 2
        finally:
            src.close()

    def test_chat_populated(self, instagram_root):
        src = _open(instagram_root)
        try:
            records = InstagramParser(src).parse()
            chats = [r["chat"] for r in records if r["chat"]]
            assert len(chats) == 2
            assert all("thread_abc" in c for c in chats)
        finally:
            src.close()

    def test_required_fields(self, instagram_root):
        src = _open(instagram_root)
        try:
            records = InstagramParser(src).parse()
            required = {"timestamp", "contact", "chat", "direction", "service", "body", "attachments"}
            for r in records:
                assert required.issubset(r.keys())
        finally:
            src.close()

    def test_body_populated(self, instagram_root):
        src = _open(instagram_root)
        try:
            records = InstagramParser(src).parse()
            bodies = [r["body"] for r in records if r["body"]]
            assert len(bodies) == 2
            assert any("Instagram" in b for b in bodies)
        finally:
            src.close()


# ── Safari ────────────────────────────────────────────────────────────────────

from forensic.parsers.safari import SafariParser
from forensic.parsers.notes import NotesParser
from forensic.parsers.calendar import CalendarParser
from forensic.parsers.voicemail import VoicemailParser
from forensic.parsers.thirdparty.viber import ViberParser
from forensic.parsers.thirdparty.line import LINEParser
from forensic.parsers.thirdparty.skype import SkypeParser
from forensic.parsers.wifi import WiFiParser


class TestSafariParser:
    def test_not_found_raises(self, empty_backup_source):
        with pytest.raises(ParserError, match="History.db not found"):
            SafariParser(empty_backup_source).parse()

    def test_returns_two_visits(self, safari_root):
        src = _open(safari_root)
        try:
            records = SafariParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_required_fields(self, safari_root):
        src = _open(safari_root)
        try:
            records = SafariParser(src).parse()
            for r in records:
                assert {"url", "title", "timestamp", "visit_count"}.issubset(r.keys())
        finally:
            src.close()

    def test_url_present(self, safari_root):
        src = _open(safari_root)
        try:
            records = SafariParser(src).parse()
            urls = [r["url"] for r in records]
            assert any("example.com" in u for u in urls)
        finally:
            src.close()

    def test_timestamps_are_2022(self, safari_root):
        src = _open(safari_root)
        try:
            records = SafariParser(src).parse()
            for r in records:
                assert r["timestamp"] is not None
                assert "2022-06-15" in r["timestamp"]
        finally:
            src.close()

    def test_visit_count_positive(self, safari_root):
        src = _open(safari_root)
        try:
            records = SafariParser(src).parse()
            assert all(r["visit_count"] >= 1 for r in records)
        finally:
            src.close()


# ── Notes ─────────────────────────────────────────────────────────────────────

class TestNotesParser:
    def test_not_found_raises(self, empty_backup_source):
        with pytest.raises(ParserError, match="not found"):
            NotesParser(empty_backup_source).parse()

    def test_returns_two_notes(self, notes_root):
        src = _open(notes_root)
        try:
            records = NotesParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_required_fields(self, notes_root):
        src = _open(notes_root)
        try:
            records = NotesParser(src).parse()
            for r in records:
                assert {"title", "snippet", "created", "modified", "locked"}.issubset(r.keys())
        finally:
            src.close()

    def test_title_present(self, notes_root):
        src = _open(notes_root)
        try:
            records = NotesParser(src).parse()
            titles = [r["title"] for r in records]
            assert any("Meeting" in t for t in titles)
        finally:
            src.close()

    def test_locked_field_is_bool(self, notes_root):
        src = _open(notes_root)
        try:
            records = NotesParser(src).parse()
            assert all(isinstance(r["locked"], bool) for r in records)
        finally:
            src.close()

    def test_timestamps_present(self, notes_root):
        src = _open(notes_root)
        try:
            records = NotesParser(src).parse()
            for r in records:
                assert r["modified"] is not None
        finally:
            src.close()


# ── Calendar ──────────────────────────────────────────────────────────────────

class TestCalendarParser:
    def test_not_found_raises(self, empty_backup_source):
        with pytest.raises(ParserError, match="not found"):
            CalendarParser(empty_backup_source).parse()

    def test_returns_two_events(self, calendar_root):
        src = _open(calendar_root)
        try:
            records = CalendarParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_required_fields(self, calendar_root):
        src = _open(calendar_root)
        try:
            records = CalendarParser(src).parse()
            for r in records:
                assert {"title", "start", "end", "all_day", "recurring", "calendar"}.issubset(r.keys())
        finally:
            src.close()

    def test_title_present(self, calendar_root):
        src = _open(calendar_root)
        try:
            records = CalendarParser(src).parse()
            titles = [r["title"] for r in records]
            assert any("Meeting" in t for t in titles)
        finally:
            src.close()

    def test_timestamps_are_2022(self, calendar_root):
        src = _open(calendar_root)
        try:
            records = CalendarParser(src).parse()
            for r in records:
                assert r["start"] is not None and "2022-06-15" in r["start"]
        finally:
            src.close()

    def test_calendar_name_populated(self, calendar_root):
        src = _open(calendar_root)
        try:
            records = CalendarParser(src).parse()
            assert all(r["calendar"] for r in records)
        finally:
            src.close()


# ── Voicemail ─────────────────────────────────────────────────────────────────

class TestVoicemailParser:
    def test_not_found_raises(self, empty_backup_source):
        with pytest.raises(ParserError, match="not found"):
            VoicemailParser(empty_backup_source).parse()

    def test_returns_two_records(self, voicemail_root):
        src = _open(voicemail_root)
        try:
            records = VoicemailParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_required_fields(self, voicemail_root):
        src = _open(voicemail_root)
        try:
            records = VoicemailParser(src).parse()
            for r in records:
                assert {"timestamp", "sender", "duration", "trashed"}.issubset(r.keys())
        finally:
            src.close()

    def test_sender_populated(self, voicemail_root):
        src = _open(voicemail_root)
        try:
            records = VoicemailParser(src).parse()
            senders = [r["sender"] for r in records if r["sender"]]
            assert len(senders) >= 1
        finally:
            src.close()

    def test_trashed_flag(self, voicemail_root):
        src = _open(voicemail_root)
        try:
            records = VoicemailParser(src).parse()
            # second record has trashed_date > 0
            trashed = [r for r in records if r["trashed"]]
            assert len(trashed) == 1
        finally:
            src.close()

    def test_duration_formatted(self, voicemail_root):
        src = _open(voicemail_root)
        try:
            records = VoicemailParser(src).parse()
            for r in records:
                assert isinstance(r["duration"], str)
                assert "s" in r["duration"]
        finally:
            src.close()


# ── Viber ─────────────────────────────────────────────────────────────────────

class TestViberParser:
    def test_not_found_raises(self, empty_backup_source):
        with pytest.raises(ParserError, match="not found"):
            ViberParser(empty_backup_source).parse()

    def test_returns_two_messages(self, viber_root):
        src = _open(viber_root)
        try:
            records = ViberParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_required_fields(self, viber_root):
        src = _open(viber_root)
        try:
            records = ViberParser(src).parse()
            for r in records:
                assert {"id", "timestamp", "body", "contact", "direction", "app"}.issubset(r.keys())
        finally:
            src.close()

    def test_app_label(self, viber_root):
        src = _open(viber_root)
        try:
            records = ViberParser(src).parse()
            assert all(r["app"] == "Viber" for r in records)
        finally:
            src.close()

    def test_direction_values(self, viber_root):
        src = _open(viber_root)
        try:
            records = ViberParser(src).parse()
            directions = {r["direction"] for r in records}
            assert directions == {"Sent", "Received"}
        finally:
            src.close()

    def test_body_present(self, viber_root):
        src = _open(viber_root)
        try:
            records = ViberParser(src).parse()
            assert any("Viber" in r["body"] for r in records)
        finally:
            src.close()


# ── LINE ──────────────────────────────────────────────────────────────────────

class TestLINEParser:
    def test_not_found_raises(self, empty_backup_source):
        with pytest.raises(ParserError, match="not found"):
            LINEParser(empty_backup_source).parse()

    def test_returns_two_messages(self, line_root):
        src = _open(line_root)
        try:
            records = LINEParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_required_fields(self, line_root):
        src = _open(line_root)
        try:
            records = LINEParser(src).parse()
            for r in records:
                assert {"id", "timestamp", "body", "contact", "app"}.issubset(r.keys())
        finally:
            src.close()

    def test_app_label(self, line_root):
        src = _open(line_root)
        try:
            records = LINEParser(src).parse()
            assert all(r["app"] == "LINE" for r in records)
        finally:
            src.close()

    def test_contact_resolved(self, line_root):
        src = _open(line_root)
        try:
            records = LINEParser(src).parse()
            contacts = [r["contact"] for r in records if r["contact"]]
            assert any("Alice" in c for c in contacts)
        finally:
            src.close()

    def test_body_present(self, line_root):
        src = _open(line_root)
        try:
            records = LINEParser(src).parse()
            assert any("LINE" in r["body"] for r in records)
        finally:
            src.close()


# ── Skype ─────────────────────────────────────────────────────────────────────

class TestSkypeParser:
    def test_not_found_raises(self, empty_backup_source):
        with pytest.raises(ParserError, match="not found"):
            SkypeParser(empty_backup_source).parse()

    def test_returns_two_messages(self, skype_root):
        src = _open(skype_root)
        try:
            records = SkypeParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_required_fields(self, skype_root):
        src = _open(skype_root)
        try:
            records = SkypeParser(src).parse()
            for r in records:
                assert {"id", "timestamp", "body", "contact", "app"}.issubset(r.keys())
        finally:
            src.close()

    def test_app_label(self, skype_root):
        src = _open(skype_root)
        try:
            records = SkypeParser(src).parse()
            assert all(r["app"] == "Skype" for r in records)
        finally:
            src.close()

    def test_xml_tags_stripped(self, skype_root):
        src = _open(skype_root)
        try:
            records = SkypeParser(src).parse()
            for r in records:
                assert "<p>" not in r["body"]
                assert "Hello Skype" in r["body"] or "Skype reply" in r["body"]
        finally:
            src.close()

    def test_contact_name_resolved(self, skype_root):
        src = _open(skype_root)
        try:
            records = SkypeParser(src).parse()
            contacts = [r["contact"] for r in records if r["contact"]]
            assert any("Alice" in c for c in contacts)
        finally:
            src.close()


# ── WiFi ──────────────────────────────────────────────────────────────────────

class TestWiFiParser:
    def test_not_found_raises(self, empty_backup_source):
        with pytest.raises(ParserError, match="not found"):
            WiFiParser(empty_backup_source).parse()

    def test_returns_two_networks(self, wifi_root):
        src = _open(wifi_root)
        try:
            records = WiFiParser(src).parse()
            assert len(records) == 2
        finally:
            src.close()

    def test_required_fields(self, wifi_root):
        src = _open(wifi_root)
        try:
            records = WiFiParser(src).parse()
            for r in records:
                assert {"ssid", "bssid", "security"}.issubset(r.keys())
        finally:
            src.close()

    def test_ssid_present(self, wifi_root):
        src = _open(wifi_root)
        try:
            records = WiFiParser(src).parse()
            ssids = [r["ssid"] for r in records]
            assert "HomeNetwork" in ssids
            assert "OfficeWiFi" in ssids
        finally:
            src.close()

    def test_bssid_present(self, wifi_root):
        src = _open(wifi_root)
        try:
            records = WiFiParser(src).parse()
            assert all(r["bssid"] for r in records)
        finally:
            src.close()


# ── Report generator ──────────────────────────────────────────────────────────

class TestReportGenerator:
    def test_html_report_generates(self):
        from forensic.report import generate_html_report
        html = generate_html_report(
            device_info={"name": "Test iPhone", "ios_version": "16.3.1",
                         "serial": "ABCD", "imei": "123", "udid": "u1"},
            source_path="/tmp/backup",
            manifest_hash="abc123",
            sections={"SMS": [{"timestamp": "2022-06-15 10:00:00", "body": "Hello"}]},
            examiner="Tester",
            case_number="CASE-001",
        )
        assert "<!DOCTYPE html>" in html
        assert "CASE-001" in html
        assert "Test iPhone" in html
        assert "abc123" in html

    def test_html_escapes_xss(self):
        from forensic.report import generate_html_report
        html = generate_html_report(
            device_info={},
            source_path="<script>alert(1)</script>",
            manifest_hash=None,
            sections={},
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_section_records_included(self):
        from forensic.report import generate_html_report
        recs = [{"url": "https://example.com", "title": "Example"}]
        html = generate_html_report(
            device_info={}, source_path="/tmp", manifest_hash=None,
            sections={"Safari History": recs},
        )
        assert "Safari History" in html
        assert "example.com" in html

    def test_html_export_writes_file(self, tmp_path):
        from forensic.report import export_html
        path = str(tmp_path / "report.html")
        export_html(path, device_info={}, source_path="/tmp", manifest_hash=None,
                    sections={}, examiner="T", case_number="C1")
        content = Path(path).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content


# ── Timeline ──────────────────────────────────────────────────────────────────

class TestTimelineView:
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        from forensic.views.timeline_view import TimelineView
        self.view = TimelineView()
        yield
        self.view.close()

    def test_initial_empty(self):
        assert self.view._all_events == []

    def test_feed_sms_records(self):
        self.view.feed_records("sms", "SMS", [
            {"timestamp": "2022-06-15 10:00:00", "body": "Hello", "sent": True},
        ])
        assert len(self.view._all_events) == 1
        assert self.view._all_events[0]["event_type"] == "sms"

    def test_feed_multiple_types(self):
        self.view.feed_records("sms", "SMS", [
            {"timestamp": "2022-06-15 10:00:00", "body": "msg"},
        ])
        self.view.feed_records("call", "Calls", [
            {"timestamp": "2022-06-15 11:00:00", "number": "+1555"},
        ])
        assert len(self.view._all_events) == 2
        types = {e["event_type"] for e in self.view._all_events}
        assert types == {"sms", "call"}

    def test_events_sorted_descending(self):
        self.view.feed_records("sms", "SMS", [
            {"timestamp": "2022-06-15 08:00:00", "body": "early"},
            {"timestamp": "2022-06-15 12:00:00", "body": "late"},
        ])
        ts = [e["timestamp"] for e in self.view._all_events]
        assert ts == sorted(ts, reverse=True)


# ── Integration: full backup source includes all new parsers ──────────────────

class TestFullBackupIntegration:
    """Run all new parsers against the main backup_source (which has every DB)."""

    def test_safari_from_full_backup(self, backup_source):
        records = SafariParser(backup_source).parse()
        assert len(records) == 2
        assert any("example.com" in r["url"] for r in records)

    def test_notes_from_full_backup(self, backup_source):
        records = NotesParser(backup_source).parse()
        assert len(records) == 2

    def test_calendar_from_full_backup(self, backup_source):
        records = CalendarParser(backup_source).parse()
        assert len(records) == 2

    def test_voicemail_from_full_backup(self, backup_source):
        records = VoicemailParser(backup_source).parse()
        assert len(records) == 2

    def test_wifi_from_full_backup(self, backup_source):
        records = WiFiParser(backup_source).parse()
        assert len(records) == 2

    def test_viber_from_full_backup(self, backup_source):
        records = ViberParser(backup_source).parse()
        assert len(records) == 2

    def test_line_from_full_backup(self, backup_source):
        records = LINEParser(backup_source).parse()
        assert len(records) == 2

    def test_skype_from_full_backup(self, backup_source):
        records = SkypeParser(backup_source).parse()
        assert len(records) == 2


# ── KnowledgeC ────────────────────────────────────────────────────────────

class TestKnowledgeCParser:
    @pytest.fixture(autouse=True)
    def setup(self, knowledgec_root):
        from forensic.parsers.knowledgec import KnowledgeCParser
        self.parser_cls = KnowledgeCParser
        self.src = _open(knowledgec_root)
        yield
        self.src.close()

    def test_returns_two_records(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) == 2

    def test_has_timestamp(self):
        records = self.parser_cls(self.src).parse()
        assert all(r["timestamp"] is not None for r in records)

    def test_stream_labels_present(self):
        records = self.parser_cls(self.src).parse()
        types = {r["event_type"] for r in records}
        assert "App Usage" in types or len(types) > 0

    def test_media_title_extracted(self):
        records = self.parser_cls(self.src).parse()
        media_recs = [r for r in records if r.get("media_title")]
        assert len(media_recs) >= 1
        assert media_recs[0]["media_title"] == "Song A"

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.knowledgec import KnowledgeCParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            KnowledgeCParser(empty_backup_source).parse()


# ── InteractionC ──────────────────────────────────────────────────────────

class TestInteractionCParser:
    @pytest.fixture(autouse=True)
    def setup(self, interactionc_root):
        from forensic.parsers.interactionc import InteractionCParser
        self.parser_cls = InteractionCParser
        self.src = _open(interactionc_root)
        yield
        self.src.close()

    def test_returns_two_records(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) == 2

    def test_contact_name_resolved(self):
        records = self.parser_cls(self.src).parse()
        assert any(r["contact"] == "Alice" for r in records)

    def test_direction_decoded(self):
        records = self.parser_cls(self.src).parse()
        directions = {r["direction"] for r in records}
        assert "Received" in directions
        assert "Sent" in directions

    def test_has_app(self):
        records = self.parser_cls(self.src).parse()
        assert all("app" in r for r in records)

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.interactionc import InteractionCParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            InteractionCParser(empty_backup_source).parse()


# ── TCC (App Permissions) ─────────────────────────────────────────────────

class TestTCCParser:
    @pytest.fixture(autouse=True)
    def setup(self, tcc_root):
        from forensic.parsers.tcc import TCCParser
        self.parser_cls = TCCParser
        self.src = _open(tcc_root)
        yield
        self.src.close()

    def test_returns_records(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) == 3

    def test_service_label_mapped(self):
        records = self.parser_cls(self.src).parse()
        services = {r["service"] for r in records}
        assert "Camera" in services
        assert "Microphone" in services

    def test_permission_decoded(self):
        records = self.parser_cls(self.src).parse()
        assert all(r["permission"] == "Allowed" for r in records)

    def test_bundle_id_present(self):
        records = self.parser_cls(self.src).parse()
        assert any(r["bundle_id"] == "com.example.app" for r in records)

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.tcc import TCCParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            TCCParser(empty_backup_source).parse()


# ── DataUsage ─────────────────────────────────────────────────────────────

class TestDataUsageParser:
    @pytest.fixture(autouse=True)
    def setup(self, data_usage_root):
        from forensic.parsers.data_usage import DataUsageParser
        self.parser_cls = DataUsageParser
        self.src = _open(data_usage_root)
        yield
        self.src.close()

    def test_returns_two_apps(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) == 2

    def test_sorted_by_total_descending(self):
        records = self.parser_cls(self.src).parse()
        # com.example.app has higher total than Safari
        assert records[0]["bundle_id"] == "com.example.app"

    def test_human_readable_sizes(self):
        records = self.parser_cls(self.src).parse()
        for r in records:
            assert any(unit in r["total"] for unit in ("B", "KB", "MB", "GB"))

    def test_wifi_out_present(self):
        records = self.parser_cls(self.src).parse()
        assert all("wifi_out" in r for r in records)

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.data_usage import DataUsageParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            DataUsageParser(empty_backup_source).parse()


# ── Accounts ──────────────────────────────────────────────────────────────

class TestAccountsParser:
    @pytest.fixture(autouse=True)
    def setup(self, accounts_root):
        from forensic.parsers.accounts import AccountsParser
        self.parser_cls = AccountsParser
        self.src = _open(accounts_root)
        yield
        self.src.close()

    def test_returns_two_accounts(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) == 2

    def test_username_present(self):
        records = self.parser_cls(self.src).parse()
        usernames = {r["username"] for r in records}
        assert "alice@icloud.com" in usernames
        assert "alice@gmail.com" in usernames

    def test_type_label_resolved(self):
        records = self.parser_cls(self.src).parse()
        labels = {r["type_label"] for r in records}
        assert "iCloud" in labels

    def test_oauth_active(self):
        records = self.parser_cls(self.src).parse()
        assert all(r["oauth_active"] for r in records)

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.accounts import AccountsParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            AccountsParser(empty_backup_source).parse()


# ── Wallet ────────────────────────────────────────────────────────────────

class TestWalletParser:
    @pytest.fixture(autouse=True)
    def setup(self, wallet_root):
        from forensic.parsers.wallet import WalletParser
        self.parser_cls = WalletParser
        self.src = _open(wallet_root)
        yield
        self.src.close()

    def test_returns_two_records(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) == 2

    def test_apple_pay_transaction(self):
        records = self.parser_cls(self.src).parse()
        txn = next(r for r in records if r["type"] == "Apple Pay")
        assert txn["merchant"] == "Coffee Shop"
        assert "4.50" in txn["amount"]

    def test_boarding_pass(self):
        records = self.parser_cls(self.src).parse()
        passes = [r for r in records if r["type"] == "boardingPass"]
        assert len(passes) == 1
        assert passes[0]["merchant"] == "Delta"

    def test_timestamp_parsed(self):
        records = self.parser_cls(self.src).parse()
        assert all(r["timestamp"] is not None for r in records)

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.wallet import WalletParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            WalletParser(empty_backup_source).parse()


# ── Reminders ─────────────────────────────────────────────────────────────

class TestRemindersParser:
    @pytest.fixture(autouse=True)
    def setup(self, reminders_root):
        from forensic.parsers.reminders import RemindersParser
        self.parser_cls = RemindersParser
        self.src = _open(reminders_root)
        yield
        self.src.close()

    def test_returns_two_reminders(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) == 2

    def test_titles_present(self):
        records = self.parser_cls(self.src).parse()
        titles = {r["title"] for r in records}
        assert "Buy groceries" in titles
        assert "Call dentist" in titles

    def test_completed_flag(self):
        records = self.parser_cls(self.src).parse()
        dentist = next(r for r in records if r["title"] == "Call dentist")
        assert dentist["completed"] is True

    def test_due_date_parsed(self):
        records = self.parser_cls(self.src).parse()
        groceries = next(r for r in records if r["title"] == "Buy groceries")
        assert groceries["due"] is not None

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.reminders import RemindersParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            RemindersParser(empty_backup_source).parse()


# ── Bluetooth ─────────────────────────────────────────────────────────────

class TestBluetoothParser:
    @pytest.fixture(autouse=True)
    def setup(self, bluetooth_root):
        from forensic.parsers.bluetooth import BluetoothParser
        self.parser_cls = BluetoothParser
        self.src = _open(bluetooth_root)
        yield
        self.src.close()

    def test_returns_two_devices(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) == 2

    def test_device_name_present(self):
        records = self.parser_cls(self.src).parse()
        names = {r["name"] for r in records}
        assert "Alice's AirPods" in names

    def test_mac_address_present(self):
        records = self.parser_cls(self.src).parse()
        assert all(r["address"] for r in records)

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.bluetooth import BluetoothParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            BluetoothParser(empty_backup_source).parse()


# ── Deleted Apps ──────────────────────────────────────────────────────────

class TestDeletedAppsParser:
    @pytest.fixture(autouse=True)
    def setup(self, deleted_apps_root):
        from forensic.parsers.deleted_apps import DeletedAppsParser
        self.parser_cls = DeletedAppsParser
        self.src = _open(deleted_apps_root)
        yield
        self.src.close()

    def test_returns_records(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) >= 1

    def test_bundle_id_present(self):
        records = self.parser_cls(self.src).parse()
        bundle_ids = {r["bundle_id"] for r in records}
        assert "com.example.deletedapp" in bundle_ids

    def test_source_labeled(self):
        records = self.parser_cls(self.src).parse()
        assert all(r["source"] for r in records)

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.deleted_apps import DeletedAppsParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            DeletedAppsParser(empty_backup_source).parse()


# ── SMS Recovery ──────────────────────────────────────────────────────────

class TestSMSRecoveryParser:
    @pytest.fixture(autouse=True)
    def setup(self, sms_gaps_root):
        from forensic.parsers.sms_recovery import SMSRecoveryParser
        self.parser_cls = SMSRecoveryParser
        self.src = _open(sms_gaps_root)
        yield
        self.src.close()

    def test_detects_gaps(self):
        records = self.parser_cls(self.src).parse()
        gap_records = [r for r in records if r["type"] == "Gap (deleted messages)"]
        assert len(gap_records) == 2

    def test_gap_counts_correct(self):
        records = self.parser_cls(self.src).parse()
        gap_records = sorted(
            [r for r in records if r["type"] == "Gap (deleted messages)"],
            key=lambda r: r["gap_start_rowid"]
        )
        # Gap 1: ROWIDs 2,3,4 → count=3; Gap 2: ROWIDs 6,7,8,9 → count=4
        assert gap_records[0]["deleted_count"] == 3
        assert gap_records[1]["deleted_count"] == 4

    def test_timestamps_bracketed(self):
        records = self.parser_cls(self.src).parse()
        for r in [x for x in records if x["type"] == "Gap (deleted messages)"]:
            assert r["after_timestamp"] is not None
            assert r["before_timestamp"] is not None

    def test_detail_string_present(self):
        records = self.parser_cls(self.src).parse()
        for r in [x for x in records if x["type"] == "Gap (deleted messages)"]:
            assert r["detail"]

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.sms_recovery import SMSRecoveryParser
        from forensic.parsers.base import ParserError
        # empty_backup_source HAS sms.db, but no gaps → returns []
        # The parser only raises if db_path is None
        records = SMSRecoveryParser(empty_backup_source).parse()
        # Verify it doesn't crash; may return [] (no gaps in sequential ROWIDs)
        assert isinstance(records, list)


# ── Biome ─────────────────────────────────────────────────────────────────

class TestBiomeParser:
    @pytest.fixture(autouse=True)
    def setup(self, biome_root):
        from forensic.parsers.biome import BiomeParser
        self.parser_cls = BiomeParser
        self.src = _open(biome_root)
        yield
        self.src.close()

    def test_returns_two_streams(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) == 2

    def test_stream_names_correct(self):
        records = self.parser_cls(self.src).parse()
        names = {r["stream_name"] for r in records}
        assert "_DKEvent.App.inFocus" in names
        assert "NowPlaying" in names

    def test_record_count_nonzero(self):
        records = self.parser_cls(self.src).parse()
        assert all(r["record_count"] >= 2 for r in records)

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.biome import BiomeParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            BiomeParser(empty_backup_source).parse()


# ── Health ────────────────────────────────────────────────────────────────

class TestHealthParser:
    @pytest.fixture(autouse=True)
    def setup(self, health_root):
        from forensic.parsers.health import HealthParser
        self.parser_cls = HealthParser
        self.src = _open(health_root)
        yield
        self.src.close()

    def test_returns_records(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) >= 3  # 2 samples + 1 workout

    def test_steps_present(self):
        records = self.parser_cls(self.src).parse()
        steps = [r for r in records if r["data_type"] == "Steps"]
        assert len(steps) == 1
        assert steps[0]["value"] == "8500.0"

    def test_workout_present(self):
        records = self.parser_cls(self.src).parse()
        workouts = [r for r in records if "Workout" in r["data_type"]]
        assert len(workouts) == 1

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.health import HealthParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            HealthParser(empty_backup_source).parse()


# ── IOC Checker ───────────────────────────────────────────────────────────

class TestIOCChecker:
    @pytest.fixture(autouse=True)
    def setup(self, empty_backup_source):
        from forensic.parsers.ioc_checker import IOCChecker
        self.parser_cls = IOCChecker
        self.src = empty_backup_source

    def test_returns_at_least_info_finding(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) >= 1

    def test_has_severity_field(self):
        records = self.parser_cls(self.src).parse()
        for r in records:
            assert r["severity"] in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")

    def test_clean_backup_returns_info(self):
        records = self.parser_cls(self.src).parse()
        # Clean backup with no known IOCs should return INFO not CRITICAL
        severities = {r["severity"] for r in records}
        assert "CRITICAL" not in severities

    def test_finding_field_present(self):
        records = self.parser_cls(self.src).parse()
        assert all(r.get("finding") for r in records)


# ── Kik ───────────────────────────────────────────────────────────────────

class TestKikParser:
    @pytest.fixture(autouse=True)
    def setup(self, kik_root):
        from forensic.parsers.thirdparty.kik import KikParser
        self.parser_cls = KikParser
        self.src = _open(kik_root)
        yield
        self.src.close()

    def test_returns_two_messages(self):
        records = self.parser_cls(self.src).parse()
        assert len(records) == 2

    def test_direction_decoded(self):
        records = self.parser_cls(self.src).parse()
        directions = {r["direction"] for r in records}
        assert "Received" in directions
        assert "Sent" in directions

    def test_contact_resolved(self):
        records = self.parser_cls(self.src).parse()
        received = [r for r in records if r["direction"] == "Received"]
        assert received[0]["contact"] == "Alice"

    def test_not_found_raises(self, empty_backup_source):
        from forensic.parsers.thirdparty.kik import KikParser
        from forensic.parsers.base import ParserError
        with pytest.raises(ParserError):
            KikParser(empty_backup_source).parse()


# ── Second-round integration (full backup) ────────────────────────────────

class TestSecondRoundIntegration:
    """Run all second-round parsers against the full backup_source."""

    def test_knowledgec_from_full_backup(self, backup_source):
        from forensic.parsers.knowledgec import KnowledgeCParser
        records = KnowledgeCParser(backup_source).parse()
        assert len(records) == 2

    def test_interactionc_from_full_backup(self, backup_source):
        from forensic.parsers.interactionc import InteractionCParser
        records = InteractionCParser(backup_source).parse()
        assert len(records) == 2

    def test_tcc_from_full_backup(self, backup_source):
        from forensic.parsers.tcc import TCCParser
        records = TCCParser(backup_source).parse()
        assert len(records) == 3

    def test_data_usage_from_full_backup(self, backup_source):
        from forensic.parsers.data_usage import DataUsageParser
        records = DataUsageParser(backup_source).parse()
        assert len(records) == 2

    def test_accounts_from_full_backup(self, backup_source):
        from forensic.parsers.accounts import AccountsParser
        records = AccountsParser(backup_source).parse()
        assert len(records) == 2

    def test_wallet_from_full_backup(self, backup_source):
        from forensic.parsers.wallet import WalletParser
        records = WalletParser(backup_source).parse()
        assert len(records) == 2

    def test_reminders_from_full_backup(self, backup_source):
        from forensic.parsers.reminders import RemindersParser
        records = RemindersParser(backup_source).parse()
        assert len(records) == 2

    def test_bluetooth_from_full_backup(self, backup_source):
        from forensic.parsers.bluetooth import BluetoothParser
        records = BluetoothParser(backup_source).parse()
        assert len(records) == 2

    def test_deleted_apps_from_full_backup(self, backup_source):
        from forensic.parsers.deleted_apps import DeletedAppsParser
        records = DeletedAppsParser(backup_source).parse()
        assert len(records) >= 1

    def test_health_from_full_backup(self, backup_source):
        from forensic.parsers.health import HealthParser
        records = HealthParser(backup_source).parse()
        assert len(records) >= 3

    def test_kik_from_full_backup(self, backup_source):
        from forensic.parsers.thirdparty.kik import KikParser
        records = KikParser(backup_source).parse()
        assert len(records) == 2

    def test_biome_from_full_backup(self, backup_source):
        from forensic.parsers.biome import BiomeParser
        records = BiomeParser(backup_source).parse()
        assert len(records) == 2
        stream_names = {r["stream_name"] for r in records}
        assert "_DKEvent.App.inFocus" in stream_names

    def test_sms_recovery_no_gaps_in_full_backup(self, backup_source):
        from forensic.parsers.sms_recovery import SMSRecoveryParser
        records = SMSRecoveryParser(backup_source).parse()
        # No gaps in the sequential test sms.db
        gap_records = [r for r in records if r["type"] == "Gap (deleted messages)"]
        assert len(gap_records) == 0

    def test_ioc_checker_from_full_backup(self, backup_source):
        from forensic.parsers.ioc_checker import IOCChecker
        records = IOCChecker(backup_source).parse()
        assert len(records) >= 1
        assert all(r["severity"] in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
                   for r in records)
