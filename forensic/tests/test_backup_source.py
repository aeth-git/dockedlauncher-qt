"""End-to-end tests for BackupSource."""
import hashlib
import plistlib
import sqlite3
from pathlib import Path

import pytest
from forensic.sources.backup import BackupSource


class TestBackupSourceOpen:
    def test_opens_valid_backup(self, backup_root):
        src = BackupSource(str(backup_root))
        src.open()
        assert len(src._file_map) > 0
        src.close()

    def test_file_map_contains_sms(self, backup_root):
        src = BackupSource(str(backup_root))
        src.open()
        assert ("HomeDomain", "Library/SMS/sms.db") in src._file_map
        src.close()

    def test_file_map_contains_calls(self, backup_root):
        src = BackupSource(str(backup_root))
        src.open()
        assert ("HomeDomain", "Library/CallHistoryDB/CallHistory.storedata") in src._file_map
        src.close()

    def test_file_map_contains_contacts(self, backup_root):
        src = BackupSource(str(backup_root))
        src.open()
        assert ("HomeDomain", "Library/AddressBook/AddressBook.sqlitedb") in src._file_map
        src.close()

    def test_manifest_hash_recorded(self, backup_root):
        src = BackupSource(str(backup_root))
        src.open()
        h = src.manifest_hash()
        assert h is not None
        assert len(h) == 64   # SHA256 hex
        src.close()

    def test_raises_on_missing_manifest(self, tmp_path):
        src = BackupSource(str(tmp_path))
        with pytest.raises(IOError):
            src.open()

    def test_auto_detects_uuid_subdir(self, tmp_path, backup_root):
        """If user picks parent Backup/ dir, source should find the UUID subdir."""
        import shutil
        parent = tmp_path / "MobileSync" / "Backup"
        parent.mkdir(parents=True)
        uuid_dir = parent / "00000000-0000-0000-0000-000000000001"
        shutil.copytree(backup_root, uuid_dir)
        src = BackupSource(str(parent))
        src.open()
        assert len(src._file_map) > 0
        src.close()

    def test_encrypted_backup_raises_permission_error(self, tmp_path):
        # Build a minimal backup with IsEncrypted=True
        (tmp_path / "Manifest.plist").write_bytes(
            plistlib.dumps({"IsEncrypted": True})
        )
        conn = sqlite3.connect(str(tmp_path / "Manifest.db"))
        conn.execute("CREATE TABLE Files (fileID TEXT, domain TEXT, relativePath TEXT, flags INTEGER, file BLOB)")
        conn.commit()
        conn.close()
        src = BackupSource(str(tmp_path))
        with pytest.raises(PermissionError):
            src.open()


class TestBackupSourceGetFile:
    def test_get_sms_db_returns_path(self, backup_source):
        path = backup_source.get_file("HomeDomain", "Library/SMS/sms.db")
        assert path is not None
        assert path.exists()

    def test_get_missing_file_returns_none(self, backup_source):
        result = backup_source.get_file("HomeDomain", "Library/SMS/nonexistent.db")
        assert result is None

    def test_get_wrong_domain_returns_none(self, backup_source):
        result = backup_source.get_file("WrongDomain", "Library/SMS/sms.db")
        assert result is None

    def test_returned_path_is_readable_sqlite(self, backup_source):
        path = backup_source.get_file("HomeDomain", "Library/SMS/sms.db")
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        conn.close()
        assert "message" in tables

    def test_physical_path_has_correct_prefix(self, backup_source, backup_root):
        path = backup_source.get_file("HomeDomain", "Library/SMS/sms.db")
        # File ID first 2 chars should be the subdirectory name
        assert path.parent.parent == backup_root
        assert len(path.parent.name) == 2


class TestBackupSourceListFiles:
    def test_list_dcim_files(self, backup_source):
        files = backup_source.list_files("CameraRollDomain", "Media/DCIM")
        assert len(files) == 3  # 2 jpg + 1 mov

    def test_list_files_returns_tuples(self, backup_source):
        files = backup_source.list_files("CameraRollDomain", "Media/DCIM")
        for rel, path in files:
            assert isinstance(rel, str)
            assert isinstance(path, Path)
            assert path.exists()

    def test_list_files_prefix_filter(self, backup_source):
        files = backup_source.list_files("HomeDomain", "Library/SMS")
        assert all("Library/SMS" in r for r, _ in files)

    def test_list_files_wrong_domain_empty(self, backup_source):
        files = backup_source.list_files("NoSuchDomain", "")
        assert files == []


class TestBackupSourceDeviceInfo:
    def test_device_info_name(self, backup_source):
        info = backup_source.get_device_info()
        assert info["name"] == "Test iPhone"

    def test_device_info_imei(self, backup_source):
        info = backup_source.get_device_info()
        assert info["imei"] == "123456789012345"

    def test_device_info_ios_version(self, backup_source):
        info = backup_source.get_device_info()
        assert info["ios_version"] == "16.3.1"

    def test_device_info_serial(self, backup_source):
        info = backup_source.get_device_info()
        assert info["serial"] == "ABCDEF123456"


class TestBackupSourceAppDomains:
    def test_list_app_domains_includes_whatsapp(self, backup_source):
        domains = backup_source.list_app_domains()
        assert "net.whatsapp.WhatsApp" in domains

    def test_list_app_domains_includes_telegram(self, backup_source):
        domains = backup_source.list_app_domains()
        assert "ph.telegra.Telegraph" in domains

    def test_context_manager(self, backup_root):
        with BackupSource(str(backup_root)) as src:
            assert len(src._file_map) > 0
        # After exit, file_map is cleared
        assert len(src._file_map) == 0
