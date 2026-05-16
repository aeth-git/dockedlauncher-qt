"""Shared fixtures: synthetic iTunes backup with all iOS database schemas."""
import hashlib
import os
import plistlib
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Dict

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app

# ── Helpers ────────────────────────────────────────────────────────────────

def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _place_file(backup_root: Path, domain: str, rel_path: str,
                content: bytes, file_map: Dict) -> str:
    """Write content to the hashed backup location, register in file_map."""
    combined = f"{domain}-{rel_path}".encode()
    file_id = _sha1(combined)
    dest = backup_root / file_id[:2] / file_id
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    file_map[(domain, rel_path)] = file_id
    return file_id


def _build_manifest_db(backup_root: Path, file_map: Dict) -> None:
    manifest_db = backup_root / "Manifest.db"
    conn = sqlite3.connect(str(manifest_db))
    conn.execute(
        "CREATE TABLE Files (fileID TEXT PRIMARY KEY, domain TEXT, relativePath TEXT, "
        "flags INTEGER, file BLOB)"
    )
    for (domain, rel_path), file_id in file_map.items():
        conn.execute(
            "INSERT INTO Files VALUES (?,?,?,?,?)",
            (file_id, domain, rel_path, 1, None)
        )
    conn.commit()
    conn.close()


# ── iOS database builders ─────────────────────────────────────────────────

APPLE_EPOCH = 978307200

def _make_sms_db() -> bytes:
    """Return bytes of a synthetic sms.db with 3 messages."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE handle (
            ROWID INTEGER PRIMARY KEY,
            id TEXT,
            service TEXT,
            uncanonicalized_id TEXT
        );
        CREATE TABLE chat (
            ROWID INTEGER PRIMARY KEY,
            guid TEXT,
            chat_identifier TEXT,
            display_name TEXT,
            service_name TEXT
        );
        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY,
            guid TEXT,
            text TEXT,
            attributedBody BLOB,
            handle_id INTEGER,
            is_from_me INTEGER,
            date INTEGER,
            service TEXT,
            cache_has_attachments INTEGER DEFAULT 0
        );
        CREATE TABLE chat_message_join (
            chat_id INTEGER,
            message_id INTEGER,
            PRIMARY KEY (chat_id, message_id)
        );
        CREATE TABLE attachment (
            ROWID INTEGER PRIMARY KEY,
            guid TEXT,
            filename TEXT,
            mime_type TEXT
        );
        CREATE TABLE message_attachment_join (
            message_id INTEGER,
            attachment_id INTEGER,
            PRIMARY KEY (message_id, attachment_id)
        );
    """)
    conn.execute("INSERT INTO handle VALUES (1, '+15551234567', 'iMessage', NULL)")
    conn.execute("INSERT INTO handle VALUES (2, '+15559876543', 'SMS', NULL)")
    conn.execute("INSERT INTO chat VALUES (1, 'chat-guid-1', '+15551234567', NULL, 'iMessage')")
    # iOS 13+ nanosecond timestamps: (2022-06-15 10:00:00 UTC - 2001-01-01) * 1e9
    ts_ns_1 = int((1655287200 - APPLE_EPOCH) * 1_000_000_000)
    ts_ns_2 = int((1655290800 - APPLE_EPOCH) * 1_000_000_000)
    ts_ns_3 = int((1655294400 - APPLE_EPOCH) * 1_000_000_000)
    conn.execute("INSERT INTO message VALUES (1,NULL,'Hello from them',NULL,1,0,?,  'iMessage',0)", (ts_ns_1,))
    conn.execute("INSERT INTO message VALUES (2,NULL,'Hey back',       NULL,1,1,?,  'iMessage',0)", (ts_ns_2,))
    conn.execute("INSERT INTO message VALUES (3,NULL,NULL,             NULL,2,0,?,  'SMS',1)",      (ts_ns_3,))
    conn.execute("INSERT INTO chat_message_join VALUES (1,1)")
    conn.execute("INSERT INTO chat_message_join VALUES (1,2)")
    conn.execute("INSERT INTO chat_message_join VALUES (1,3)")
    conn.execute("INSERT INTO attachment VALUES (1,'att-guid','photo.jpg','image/jpeg')")
    conn.execute("INSERT INTO message_attachment_join VALUES (3,1)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_call_db() -> bytes:
    """Return bytes of a synthetic CallHistory.storedata with 3 calls."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ZCALLRECORD (
            Z_PK INTEGER PRIMARY KEY,
            ZDATE REAL,
            ZDURATION REAL,
            ZADDRESS TEXT,
            ZNAME TEXT,
            ZORIGINATED INTEGER,
            ZANSWERED INTEGER,
            ZCALLTYPE INTEGER,
            ZSERVICE_PROVIDER TEXT
        );
    """)
    # ZDATE is Apple epoch seconds (float) for Core Data
    t1 = 1655287200 - APPLE_EPOCH  # 2022-06-15 10:00:00 UTC
    t2 = 1655290800 - APPLE_EPOCH
    t3 = 1655294400 - APPLE_EPOCH
    conn.execute("INSERT INTO ZCALLRECORD VALUES (1,?,135.0,'+15551234567','Alice',1,1,1,'carrier')", (t1,))
    conn.execute("INSERT INTO ZCALLRECORD VALUES (2,?,0.0,  '+15559876543',NULL,   0,0,1,'')",        (t2,))
    conn.execute("INSERT INTO ZCALLRECORD VALUES (3,?,62.0, '+15550001111',NULL,   0,1,8,'FaceTime')",(t3,))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_contacts_db() -> bytes:
    """Return bytes of a synthetic AddressBook.sqlitedb with 2 contacts."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ABPerson (
            ROWID INTEGER PRIMARY KEY,
            First TEXT, Last TEXT, Middle TEXT,
            Organization TEXT, Department TEXT
        );
        CREATE TABLE ABMultiValue (
            ROWID INTEGER PRIMARY KEY,
            record_id INTEGER,
            property INTEGER,
            value TEXT,
            label INTEGER
        );
    """)
    conn.execute("INSERT INTO ABPerson VALUES (1,'Alice','Smith',NULL,'Acme Corp',NULL)")
    conn.execute("INSERT INTO ABPerson VALUES (2,'Bob',  'Jones',NULL,NULL,NULL)")
    # property 3 = phone, property 4 = email; label 4 = mobile, 1 = home
    conn.execute("INSERT INTO ABMultiValue VALUES (1,1,3,'+15551234567',4)")
    conn.execute("INSERT INTO ABMultiValue VALUES (2,1,4,'alice@example.com',2)")
    conn.execute("INSERT INTO ABMultiValue VALUES (3,2,3,'+15559876543',1)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_whatsapp_db(include_contact_table: bool = True) -> bytes:
    """Return bytes of a synthetic ChatStorage.sqlite."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    schema = """
        CREATE TABLE ZWACHATSESSION (
            Z_PK INTEGER PRIMARY KEY,
            ZCONTACTJID TEXT
        );
        CREATE TABLE ZWAMESSAGE (
            Z_PK INTEGER PRIMARY KEY,
            ZTEXT TEXT,
            ZMESSAGEDATE REAL,
            ZISFROMME INTEGER,
            ZCHATSESSION INTEGER,
            ZFROMJID TEXT
        );
    """
    if include_contact_table:
        schema += """
        CREATE TABLE ZWACONTACT (
            Z_PK INTEGER PRIMARY KEY,
            ZCONTACTJID TEXT,
            ZPUSHNAME TEXT
        );
        """
    conn.executescript(schema)
    conn.execute("INSERT INTO ZWACHATSESSION VALUES (1,'15551234567@s.whatsapp.net')")
    t1 = 1655287200 - APPLE_EPOCH
    t2 = 1655290800 - APPLE_EPOCH
    conn.execute("INSERT INTO ZWAMESSAGE VALUES (1,'Hey!',?,0,1,'15551234567@s.whatsapp.net')", (t1,))
    conn.execute("INSERT INTO ZWAMESSAGE VALUES (2,'Sup',?,1,1,NULL)", (t2,))
    if include_contact_table:
        conn.execute("INSERT INTO ZWACONTACT VALUES (1,'15551234567@s.whatsapp.net','Alice')")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_telegram_db() -> bytes:
    """Return bytes of a synthetic Telegram cache.db."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE messages_table (
            mid INTEGER PRIMARY KEY,
            message TEXT,
            date INTEGER,
            from_id INTEGER,
            to_id INTEGER
        );
        CREATE TABLE users_table (
            uid INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT
        );
    """)
    # Telegram uses Unix epoch seconds
    conn.execute("INSERT INTO users_table VALUES (42,'Alice',NULL)")
    conn.execute("INSERT INTO messages_table VALUES (1,'Hello Telegram',1655287200,42,100)")
    conn.execute("INSERT INTO messages_table VALUES (2,'Reply here',    1655290800,0, 100)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_snapchat_db() -> bytes:
    """Return bytes of a synthetic Snapchat main.db (metadata only)."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE snap (
            id INTEGER PRIMARY KEY,
            sender_id TEXT,
            timestamp INTEGER,
            media_type TEXT
        );
    """)
    conn.execute("INSERT INTO snap VALUES (1,'alice',1655287200,'IMAGE')")
    conn.execute("INSERT INTO snap VALUES (2,'bob',  1655290800,'VIDEO')")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_info_plist() -> bytes:
    data = {
        "Device Name": "Test iPhone",
        "IMEI": "123456789012345",
        "Product Version": "16.3.1",
        "Serial Number": "ABCDEF123456",
        "Unique Identifier": "00000000-0000-0000-0000-000000000001",
    }
    return plistlib.dumps(data)


def _make_manifest_plist(encrypted: bool = False) -> bytes:
    data = {
        "IsEncrypted": encrypted,
        "Version": "10.0",
    }
    return plistlib.dumps(data)


# ── Main fixture ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def backup_root(tmp_path_factory) -> Path:
    """Builds a complete synthetic iTunes backup directory."""
    root = tmp_path_factory.mktemp("backup")
    file_map: Dict = {}

    # Standard iOS DBs
    _place_file(root, "HomeDomain", "Library/SMS/sms.db", _make_sms_db(), file_map)
    _place_file(root, "HomeDomain", "Library/CallHistoryDB/CallHistory.storedata",
                _make_call_db(), file_map)
    _place_file(root, "HomeDomain", "Library/AddressBook/AddressBook.sqlitedb",
                _make_contacts_db(), file_map)

    # Third-party apps — with ZWACONTACT
    _place_file(root, "AppDomain-net.whatsapp.WhatsApp", "Documents/ChatStorage.sqlite",
                _make_whatsapp_db(include_contact_table=True), file_map)
    _place_file(root, "AppDomain-ph.telegra.Telegraph", "Documents/cache.db",
                _make_telegram_db(), file_map)
    _place_file(root, "AppDomain-com.toyopagroup.picaboo", "Documents/main.db",
                _make_snapchat_db(), file_map)

    # A few DCIM photos (tiny PNG bytes)
    tiny_png = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
        b'\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18'
        b'\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    _place_file(root, "CameraRollDomain", "Media/DCIM/100APPLE/IMG_0001.JPG",
                tiny_png, file_map)
    _place_file(root, "CameraRollDomain", "Media/DCIM/100APPLE/IMG_0002.JPG",
                tiny_png, file_map)
    _place_file(root, "CameraRollDomain", "Media/DCIM/100APPLE/VID_0001.MOV",
                b"fakevideo", file_map)

    # App metadata
    whatsapp_meta = plistlib.dumps({
        "itemName": "WhatsApp",
        "bundleShortVersionString": "22.5.1",
        "artistName": "WhatsApp Inc.",
        "genre": "Social Networking",
    })
    _place_file(root, "AppDomain-net.whatsapp.WhatsApp",
                "iTunesMetadata.plist", whatsapp_meta, file_map)

    # New Apple parsers — include in main backup for integration tests
    _place_file(root, "HomeDomain", "Library/Safari/History.db",
                _make_safari_db(), file_map)
    _place_file(root, "AppDomain-group.com.apple.notes", "NoteStore.sqlite",
                _make_notes_db(), file_map)
    _place_file(root, "HomeDomain", "Library/Calendar/Calendar.sqlitedb",
                _make_calendar_db(), file_map)
    _place_file(root, "HomeDomain", "Library/Voicemail/voicemail.db",
                _make_voicemail_db(), file_map)
    _place_file(
        root,
        "SystemPreferencesDomain",
        "Library/Preferences/SystemConfiguration/com.apple.wifi.known-networks.plist",
        _make_wifi_plist(), file_map,
    )
    _place_file(root, "AppDomain-com.viber", "Documents/Inbox.data",
                _make_viber_messages_db(), file_map)
    _place_file(root, "AppDomain-jp.naver.line", "Documents/naver_line",
                _make_line_db(), file_map)
    _place_file(root, "AppDomain-com.skype.skype", "Documents/main.db",
                _make_skype_db(), file_map)

    # Second-round Apple parsers
    _place_file(root, "HomeDomain",
                "Library/CoreDuet/Knowledge/knowledgeC.db",
                _make_knowledgec_db(), file_map)
    _place_file(root, "HomeDomain",
                "Library/CoreDuet/People/interactionC.db",
                _make_interactionc_db(), file_map)
    _place_file(root, "HomeDomain", "Library/TCC/TCC.db",
                _make_tcc_db(), file_map)
    _place_file(root, "WirelessDomain",
                "Library/Databases/DataUsage.sqlite",
                _make_data_usage_db(), file_map)
    _place_file(root, "HomeDomain",
                "Library/Accounts/Accounts3.sqlite",
                _make_accounts_db(), file_map)
    _place_file(root, "HomeDomain",
                "Library/Passes/passes23.sqlite",
                _make_wallet_db(), file_map)
    _place_file(root, "HomeDomain",
                "Library/Reminders/Container_v1/Stores/Data-ABCDEF.sqlite",
                _make_reminders_db(), file_map)
    _place_file(root, "SystemPreferencesDomain",
                "Library/Preferences/com.apple.MobileBluetooth.devices.plist",
                _make_bluetooth_plist(), file_map)
    _place_file(root, "HomeDomain",
                "Library/MobileInstallation/UninstalledApplications.plist",
                _make_uninstalled_plist(), file_map)
    _place_file(root, "HomeDomain",
                "Library/Health/healthdb_secure.sqlite",
                _make_health_db(), file_map)
    _place_file(root, "AppDomain-com.kik.chat", "kik.sqlite",
                _make_kik_db(), file_map)
    # Biome SEGB streams
    _segb = _make_segb_file()
    _place_file(root, "HomeDomain",
                "Library/Biome/streams/restricted/_DKEvent.App.inFocus/local/abc123",
                _segb, file_map)
    _place_file(root, "HomeDomain",
                "Library/Biome/streams/public/NowPlaying/local/def456",
                _segb, file_map)

    # Manifest files
    _build_manifest_db(root, file_map)
    (root / "Manifest.plist").write_bytes(_make_manifest_plist(encrypted=False))
    (root / "Info.plist").write_bytes(_make_info_plist())

    return root


@pytest.fixture(scope="session")
def backup_source(backup_root):
    """Opened BackupSource over the synthetic backup."""
    sys.path.insert(0, str(Path(__file__).parents[3]))
    from forensic.sources.backup import BackupSource
    src = BackupSource(str(backup_root))
    src.open()
    yield src
    src.close()


@pytest.fixture(scope="session")
def empty_backup_source(tmp_path_factory):
    """BackupSource with only the core iOS DBs — new parsers will not find their files."""
    from forensic.sources.backup import BackupSource
    root = tmp_path_factory.mktemp("backup_core_only")
    file_map: Dict = {}
    _place_file(root, "HomeDomain", "Library/SMS/sms.db", _make_sms_db(), file_map)
    _place_file(root, "HomeDomain", "Library/CallHistoryDB/CallHistory.storedata",
                _make_call_db(), file_map)
    _place_file(root, "HomeDomain", "Library/AddressBook/AddressBook.sqlitedb",
                _make_contacts_db(), file_map)
    _build_manifest_db(root, file_map)
    (root / "Manifest.plist").write_bytes(_make_manifest_plist(encrypted=False))
    (root / "Info.plist").write_bytes(_make_info_plist())
    src = BackupSource(str(root))
    src.open()
    yield src
    src.close()


# ── Third-party DB builders ───────────────────────────────────────────────


def _make_signal_yap_db() -> bytes:
    """Signal YapDatabase era — 'threads' + 'interactions' tables."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE threads (
            uniqueId TEXT PRIMARY KEY,
            contactPhoneNumber TEXT
        );
        CREATE TABLE interactions (
            uniqueId TEXT PRIMARY KEY,
            threadUniqueId TEXT,
            body TEXT,
            timestamp INTEGER,
            recordType INTEGER
        );
    """)
    conn.execute("INSERT INTO threads VALUES ('thread1','+15551234567')")
    # recordType 101 = incoming (Received), 102 = outgoing (Sent)
    conn.execute("INSERT INTO interactions VALUES ('m1','thread1','Hello Signal',1655287200000,101)")
    conn.execute("INSERT INTO interactions VALUES ('m2','thread1','Signal reply',1655290800000,102)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_signal_grdb_db() -> bytes:
    """Signal GRDB era (unencrypted) — model_IncomingMessage / model_OutgoingMessage."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE model_IncomingMessage (
            uniqueId TEXT PRIMARY KEY,
            body TEXT,
            timestamp INTEGER,
            authorPhoneNumber TEXT
        );
        CREATE TABLE model_OutgoingMessage (
            uniqueId TEXT PRIMARY KEY,
            body TEXT,
            timestamp INTEGER
        );
    """)
    conn.execute("INSERT INTO model_IncomingMessage VALUES ('m1','Hey GRDB',1655287200000,'+15551234567')")
    conn.execute("INSERT INTO model_OutgoingMessage VALUES ('m2','GRDB reply',1655290800000)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_signal_encrypted_db() -> bytes:
    """Simulate SQLCipher-encrypted database (not valid SQLite)."""
    # SQLCipher XORs the header so it won't start with the SQLite magic string.
    return b"\xd9\x4e\x2a\x11" * 256 + b"\xff\xfe\xfd" * 256


def _make_messenger_readable_db() -> bytes:
    """Messenger pre-Lightspeed — readable 'messages' table."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            body TEXT,
            timestamp_ms INTEGER,
            sender_id TEXT
        );
    """)
    conn.execute("INSERT INTO messages VALUES (1,'Hey Messenger!',1655287200000,'alice')")
    conn.execute("INSERT INTO messages VALUES (2,'Reply back',1655290800000,'me')")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_messenger_encrypted_db() -> bytes:
    """Messenger post-Lightspeed — body column contains binary blobs."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            body BLOB,
            timestamp_ms INTEGER
        );
    """)
    conn.execute("INSERT INTO messages VALUES (1,?,1655287200000)", (b'\xde\xad\xbe\xef' * 16,))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_instagram_db() -> bytes:
    """Instagram direct_messages table."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE direct_messages (
            id INTEGER PRIMARY KEY,
            text TEXT,
            timestamp INTEGER,
            sender_id TEXT,
            thread_id TEXT
        );
    """)
    conn.execute("INSERT INTO direct_messages VALUES (1,'Hey Instagram!',1655287200,'alice','thread_abc')")
    conn.execute("INSERT INTO direct_messages VALUES (2,'IG reply',1655290800,'me','thread_abc')")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _minimal_backup(root: Path, domain: str, rel_path: str, db_bytes: bytes) -> None:
    """Place one file, build Manifest.db, write plists."""
    file_map: Dict = {}
    _place_file(root, domain, rel_path, db_bytes, file_map)
    _build_manifest_db(root, file_map)
    (root / "Manifest.plist").write_bytes(_make_manifest_plist(encrypted=False))
    (root / "Info.plist").write_bytes(_make_info_plist())


@pytest.fixture(scope="session")
def signal_yap_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_signal_yap")
    _minimal_backup(root, "AppDomain-org.whispersystems.signal",
                    "Documents/signal.sqlite", _make_signal_yap_db())
    return root


@pytest.fixture(scope="session")
def signal_grdb_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_signal_grdb")
    _minimal_backup(root, "AppDomain-org.whispersystems.signal",
                    "Documents/signal.sqlite", _make_signal_grdb_db())
    return root


@pytest.fixture(scope="session")
def signal_encrypted_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_signal_enc")
    _minimal_backup(root, "AppDomain-org.whispersystems.signal",
                    "Documents/signal.sqlite", _make_signal_encrypted_db())
    return root


@pytest.fixture(scope="session")
def messenger_readable_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_msg_readable")
    _minimal_backup(root, "AppDomain-com.facebook.Messenger",
                    "Documents/messenger.db", _make_messenger_readable_db())
    return root


@pytest.fixture(scope="session")
def messenger_encrypted_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_msg_enc")
    _minimal_backup(root, "AppDomain-com.facebook.Messenger",
                    "Documents/messenger.db", _make_messenger_encrypted_db())
    return root


@pytest.fixture(scope="session")
def instagram_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_instagram")
    _minimal_backup(root, "AppDomain-com.burbn.instagram",
                    "Documents/direct.db", _make_instagram_db())
    return root


@pytest.fixture(scope="session")
def whatsapp_no_contact_root(tmp_path_factory) -> Path:
    """Backup with WhatsApp post-2022 (no ZWACONTACT table)."""
    root = tmp_path_factory.mktemp("backup_wa_new")
    file_map: Dict = {}
    _place_file(root, "AppDomain-net.whatsapp.WhatsApp", "Documents/ChatStorage.sqlite",
                _make_whatsapp_db(include_contact_table=False), file_map)
    _build_manifest_db(root, file_map)
    (root / "Manifest.plist").write_bytes(_make_manifest_plist(False))
    (root / "Info.plist").write_bytes(_make_info_plist())
    return root


# ── New Apple parser DB builders ──────────────────────────────────────────


def _make_safari_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE history_items (
            id INTEGER PRIMARY KEY,
            url TEXT,
            domain_expansion TEXT,
            visit_count INTEGER
        );
        CREATE TABLE history_visits (
            id INTEGER PRIMARY KEY,
            history_item INTEGER,
            visit_time REAL,
            title TEXT,
            load_successful INTEGER
        );
    """)
    t1 = 1655287200 - APPLE_EPOCH
    t2 = 1655290800 - APPLE_EPOCH
    conn.execute("INSERT INTO history_items VALUES (1,'https://example.com','example.com',5)")
    conn.execute("INSERT INTO history_items VALUES (2,'https://news.ycombinator.com','ycombinator.com',2)")
    conn.execute("INSERT INTO history_visits VALUES (1,1,?,  'Example Domain',1)", (t1,))
    conn.execute("INSERT INTO history_visits VALUES (2,2,?,  'Hacker News',1)",     (t2,))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_notes_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ZICCLOUDSYNCINGOBJECT (
            Z_PK INTEGER PRIMARY KEY,
            ZTITLE1 TEXT,
            ZCREATIONDATE1 REAL,
            ZMODIFICATIONDATE1 REAL,
            ZSNIPPET TEXT,
            ZISPASSWORDPROTECTED INTEGER
        );
        CREATE TABLE ZICNOTEDATA (
            Z_PK INTEGER PRIMARY KEY,
            ZNOTE INTEGER,
            ZDATA BLOB
        );
    """)
    t1 = 1655287200 - APPLE_EPOCH
    t2 = 1655290800 - APPLE_EPOCH
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES (1,'Meeting Notes',?,?,'Key points: ...',0)", (t1, t2))
    conn.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES (2,'Shopping List',?,?,'Milk, eggs',0)", (t1, t1))
    conn.execute("INSERT INTO ZICNOTEDATA VALUES (1,1,NULL)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_calendar_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE Calendar (
            ROWID INTEGER PRIMARY KEY,
            title TEXT,
            color INTEGER
        );
        CREATE TABLE CalendarItem (
            ROWID INTEGER PRIMARY KEY,
            summary TEXT,
            location TEXT,
            description TEXT,
            start_date REAL,
            end_date REAL,
            all_day INTEGER,
            has_recurrences INTEGER,
            calendar_id INTEGER
        );
    """)
    t1 = 1655287200 - APPLE_EPOCH
    t2 = 1655290800 - APPLE_EPOCH
    conn.execute("INSERT INTO Calendar VALUES (1,'Work',0)")
    conn.execute("INSERT INTO CalendarItem VALUES (1,'Team Meeting','Conf Room A','Weekly sync',?,?,0,0,1)", (t1, t2))
    conn.execute("INSERT INTO CalendarItem VALUES (2,'Lunch','Café','Lunch with Alice',?,?,0,0,1)", (t2, t2 + 3600))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_voicemail_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE voicemail (
            ROWID INTEGER PRIMARY KEY,
            remote_uid TEXT,
            date INTEGER,
            sender TEXT,
            callback_num TEXT,
            duration INTEGER,
            expiration INTEGER,
            trashed_date INTEGER,
            flags INTEGER
        );
    """)
    conn.execute("INSERT INTO voicemail VALUES (1,'uid1',1655287200,'+15551234567','+15551234567',45,0,0,0)")
    conn.execute("INSERT INTO voicemail VALUES (2,'uid2',1655290800,'+15559876543',NULL,          30,0,1655291000,0)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_viber_messages_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ZVIBERMESSAGE (
            ZMESSAGE_ID TEXT PRIMARY KEY,
            ZTEXT TEXT,
            ZTIMESTAMP INTEGER,
            ZCONVERSATION_ID TEXT,
            ZSENDER_VIBER_ID TEXT,
            ZDIRECTION INTEGER
        );
    """)
    conn.execute("INSERT INTO ZVIBERMESSAGE VALUES ('v1','Hi Viber!',1655287200,'conv1','alice',0)")
    conn.execute("INSERT INTO ZVIBERMESSAGE VALUES ('v2','Viber back',1655290800,'conv1','me',   1)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_line_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE contact (
            mid TEXT PRIMARY KEY,
            m_name TEXT
        );
        CREATE TABLE chat_history (
            id TEXT PRIMARY KEY,
            chat_id TEXT,
            from_mid TEXT,
            content TEXT,
            deliver_time INTEGER,
            type INTEGER
        );
    """)
    conn.execute("INSERT INTO contact VALUES ('u_alice','Alice')")
    conn.execute("INSERT INTO chat_history VALUES ('l1','chat_abc','u_alice','Hello LINE!',1655287200000,1)")
    conn.execute("INSERT INTO chat_history VALUES ('l2','chat_abc','u0',     'LINE reply', 1655290800000,1)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_skype_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE Conversations (
            id INTEGER PRIMARY KEY,
            displayname TEXT
        );
        CREATE TABLE Contacts (
            skypename TEXT PRIMARY KEY,
            displayname TEXT
        );
        CREATE TABLE Messages (
            id INTEGER PRIMARY KEY,
            body_xml TEXT,
            timestamp INTEGER,
            author TEXT,
            from_dispname TEXT,
            convo_id INTEGER,
            type INTEGER
        );
    """)
    conn.execute("INSERT INTO Conversations VALUES (1,'Alice Skype')")
    conn.execute("INSERT INTO Contacts VALUES ('alice.skype','Alice')")
    conn.execute("INSERT INTO Messages VALUES (1,'<p>Hello Skype!</p>',1655287200,'alice.skype','Alice',1,61)")
    conn.execute("INSERT INTO Messages VALUES (2,'<p>Skype reply</p>',  1655290800,'me.skype',  'Me',   1,61)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_wifi_plist() -> bytes:
    data = {
        "List of known networks": [
            {
                "SSID_STR": "HomeNetwork",
                "BSSID": "aa:bb:cc:dd:ee:ff",
                "SecurityType": "WPA2 Personal",
                "lastJoined": "2022-06-15 10:00:00 +0000",
            },
            {
                "SSID_STR": "OfficeWiFi",
                "BSSID": "11:22:33:44:55:66",
                "SecurityType": "WPA2 Enterprise",
                "lastJoined": "2022-06-14 09:00:00 +0000",
            },
        ]
    }
    return plistlib.dumps(data)


# ── New fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def safari_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_safari")
    _minimal_backup(root, "HomeDomain", "Library/Safari/History.db", _make_safari_db())
    return root


@pytest.fixture(scope="session")
def notes_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_notes")
    _minimal_backup(root, "AppDomain-group.com.apple.notes", "NoteStore.sqlite",
                    _make_notes_db())
    return root


@pytest.fixture(scope="session")
def calendar_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_calendar")
    _minimal_backup(root, "HomeDomain", "Library/Calendar/Calendar.sqlitedb",
                    _make_calendar_db())
    return root


@pytest.fixture(scope="session")
def voicemail_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_voicemail")
    _minimal_backup(root, "HomeDomain", "Library/Voicemail/voicemail.db",
                    _make_voicemail_db())
    return root


@pytest.fixture(scope="session")
def viber_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_viber")
    _minimal_backup(root, "AppDomain-com.viber", "Documents/Inbox.data",
                    _make_viber_messages_db())
    return root


@pytest.fixture(scope="session")
def line_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_line")
    _minimal_backup(root, "AppDomain-jp.naver.line", "Documents/naver_line",
                    _make_line_db())
    return root


@pytest.fixture(scope="session")
def skype_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_skype")
    _minimal_backup(root, "AppDomain-com.skype.skype", "Documents/main.db",
                    _make_skype_db())
    return root


@pytest.fixture(scope="session")
def wifi_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_wifi")
    _minimal_backup(
        root,
        "SystemPreferencesDomain",
        "Library/Preferences/SystemConfiguration/com.apple.wifi.known-networks.plist",
        _make_wifi_plist(),
    )
    return root


# ── Second-round DB builders ──────────────────────────────────────────────


def _make_knowledgec_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ZOBJECT (
            Z_PK INTEGER PRIMARY KEY,
            ZSTREAMNAME TEXT,
            ZSTARTDATE REAL,
            ZENDDATE REAL,
            ZVALUEINTEGER INTEGER,
            ZVALUESTRING TEXT,
            ZVALUEDOUBLE REAL,
            ZSTRUCTUREDMETADATA INTEGER
        );
        CREATE TABLE ZSTRUCTUREDMETADATA (
            Z_PK INTEGER PRIMARY KEY,
            ZDKAPPINSTALLMETADATAKEY__BUNDLEID TEXT,
            ZDKNOWPLAYINGMETADATAKEY__TITLE TEXT,
            ZDKNOWPLAYINGMETADATAKEY__ARTIST TEXT,
            ZDKNOWPLAYINGMETADATAKEY__ALBUM TEXT,
            ZDKNOWPLAYINGMETADATAKEY__UNIQUEID TEXT
        );
    """)
    t1 = 1655287200 - APPLE_EPOCH
    t2 = 1655290800 - APPLE_EPOCH
    conn.execute("INSERT INTO ZSTRUCTUREDMETADATA VALUES (1,'com.apple.mobilenotes',NULL,NULL,NULL,NULL)")
    conn.execute("INSERT INTO ZSTRUCTUREDMETADATA VALUES (2,NULL,'Song A','Artist B','Album C','com.apple.Music')")
    conn.execute("INSERT INTO ZOBJECT VALUES (1,'/app/usage',?,?,180,'com.apple.mobilenotes',NULL,1)", (t1, t2))
    conn.execute("INSERT INTO ZOBJECT VALUES (2,'/media/nowPlaying',?,?,NULL,NULL,NULL,2)", (t2, t2 + 240))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_interactionc_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ZINTERACTIONS (
            Z_PK INTEGER PRIMARY KEY,
            ZSTARTDATE REAL,
            ZENDDATE REAL,
            ZDIRECTION INTEGER,
            ZBUNDLEID TEXT,
            ZISRESPONSE INTEGER,
            ZCONTACT INTEGER
        );
        CREATE TABLE ZCONTACTS (
            Z_PK INTEGER PRIMARY KEY,
            ZDISPLAYNAME TEXT,
            ZPERSONID INTEGER
        );
        CREATE TABLE ZATTACHMENTS (
            Z_PK INTEGER PRIMARY KEY,
            ZINTERACTION INTEGER,
            ZATTACHMENT TEXT
        );
    """)
    t1 = 1655287200 - APPLE_EPOCH
    t2 = 1655290800 - APPLE_EPOCH
    conn.execute("INSERT INTO ZCONTACTS VALUES (1,'Alice',42)")
    conn.execute("INSERT INTO ZINTERACTIONS VALUES (1,?,?,0,'com.apple.MobileSMS',0,1)", (t1, t2))
    conn.execute("INSERT INTO ZINTERACTIONS VALUES (2,?,?,1,'com.apple.MobileSMS',1,1)", (t2, t2 + 60))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_tcc_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE access (
            service TEXT,
            client TEXT,
            client_type INTEGER,
            auth_value INTEGER,
            auth_reason INTEGER,
            last_modified INTEGER
        );
    """)
    conn.execute("INSERT INTO access VALUES ('kTCCServiceCamera','com.example.app',0,2,3,1655287200)")
    conn.execute("INSERT INTO access VALUES ('kTCCServiceMicrophone','com.example.app',0,2,3,1655290800)")
    conn.execute("INSERT INTO access VALUES ('kTCCServicePhotos','com.apple.photos',0,2,1,1655290800)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_data_usage_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ZPROCESS (
            Z_PK INTEGER PRIMARY KEY,
            ZBUNDLENAME TEXT,
            ZPROCNAME TEXT
        );
        CREATE TABLE ZPROCUID (
            Z_PK INTEGER PRIMARY KEY,
            ZPROCESS INTEGER,
            ZWIFIIN INTEGER,
            ZWIFIOUT INTEGER,
            ZWIRELESSWANIN INTEGER,
            ZWIRELESSWANOUT INTEGER,
            ZTIMESTAMP REAL
        );
    """)
    t1 = 1655287200 - APPLE_EPOCH
    conn.execute("INSERT INTO ZPROCESS VALUES (1,'com.apple.Safari','Safari')")
    conn.execute("INSERT INTO ZPROCESS VALUES (2,'com.example.app','ExampleApp')")
    conn.execute("INSERT INTO ZPROCUID VALUES (1,1,  1024000, 512000, 102400, 51200, ?)", (t1,))
    conn.execute("INSERT INTO ZPROCUID VALUES (2,2,200000000,50000000,10000000,150000000,?)", (t1,))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_accounts_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ZACCOUNTTYPE (
            Z_PK INTEGER PRIMARY KEY,
            ZIDENTIFIER TEXT,
            ZDISPLAYNAME TEXT
        );
        CREATE TABLE ZACCOUNT (
            Z_PK INTEGER PRIMARY KEY,
            ZUSERNAME TEXT,
            ZDISPLAYNAME TEXT,
            ZACCOUNTTYPE INTEGER,
            ZOAUTH_STATE INTEGER
        );
    """)
    conn.execute("INSERT INTO ZACCOUNTTYPE VALUES (1,'com.apple.account.iCloud','iCloud')")
    conn.execute("INSERT INTO ZACCOUNTTYPE VALUES (2,'com.google.Gmail','Gmail')")
    conn.execute("INSERT INTO ZACCOUNT VALUES (1,'alice@icloud.com','Alice',1,1)")
    conn.execute("INSERT INTO ZACCOUNT VALUES (2,'alice@gmail.com','Alice Gmail',2,1)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_wallet_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ZPAYMENTTRANSACTION (
            Z_PK INTEGER PRIMARY KEY,
            ZMERCHANTNAME TEXT,
            ZAMOUNT REAL,
            ZCURRENCYCODE TEXT,
            ZLATITUDE REAL,
            ZLONGITUDE REAL,
            ZTIMESTAMP REAL,
            ZPAYMENTINSTRUMENTLASTFOUR TEXT,
            ZPAYMENTINSTRUMENTTYPE TEXT
        );
        CREATE TABLE ZPASS (
            Z_PK INTEGER PRIMARY KEY,
            ZPASSTYPE TEXT,
            ZDESCRIPTION TEXT,
            ZORGANIZATIONNAME TEXT,
            ZSERIALNUMBER TEXT,
            ZEXPIRATIONDATE REAL,
            ZRELEVANTDATE REAL
        );
    """)
    t1 = 1655287200 - APPLE_EPOCH
    conn.execute("INSERT INTO ZPAYMENTTRANSACTION VALUES (1,'Coffee Shop',4.50,'USD',37.7749,-122.4194,?,4321,'Visa')", (t1,))
    conn.execute("INSERT INTO ZPASS VALUES (1,'boardingPass','Flight to NYC','Delta','ABC123',?,?)", (t1 + 86400, t1))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_reminders_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ZREMCDOBJECT (
            Z_PK INTEGER PRIMARY KEY,
            ZTITLE1 TEXT,
            ZNOTES TEXT,
            ZCREATIONDATE REAL,
            ZLASTMODIFIEDDATE REAL,
            ZDUEDATE REAL,
            ZCOMPLETED INTEGER,
            ZCOMPLETEDDATE REAL
        );
    """)
    t1 = 1655287200 - APPLE_EPOCH
    t2 = 1655290800 - APPLE_EPOCH
    conn.execute("INSERT INTO ZREMCDOBJECT VALUES (1,'Buy groceries','Milk, eggs',?,?,?,0,NULL)", (t1, t2, t2 + 3600))
    conn.execute("INSERT INTO ZREMCDOBJECT VALUES (2,'Call dentist',NULL,?,?,NULL,1,?)", (t1, t2, t2))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_bluetooth_plist() -> bytes:
    data = {
        "aa:bb:cc:dd:ee:ff": {
            "Name": "Alice's AirPods",
            "LastSeenTime": "2022-06-15 10:00:00 +0000",
            "ClassOfDevice": "0x240408",
            "BTDeviceType": "headphones",
        },
        "11:22:33:44:55:66": {
            "Name": "iPhone 13",
            "LastSeenTime": "2022-06-14 09:00:00 +0000",
            "ClassOfDevice": "0x5A020C",
        },
    }
    return plistlib.dumps(data)


def _make_uninstalled_plist() -> bytes:
    data = {
        "com.example.deletedapp": {
            "UninstallDate": "2022-06-10 08:00:00 +0000",
        },
        "com.another.removed": {},
    }
    return plistlib.dumps(data)


def _make_health_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE data_type (
            ROWID INTEGER PRIMARY KEY,
            local_name TEXT
        );
        CREATE TABLE sources (
            ROWID INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE samples (
            ROWID INTEGER PRIMARY KEY,
            data_type INTEGER,
            start_date REAL,
            end_date REAL,
            value REAL,
            source_id INTEGER
        );
        CREATE TABLE workouts (
            ROWID INTEGER PRIMARY KEY,
            workout_activity_type TEXT,
            start_date REAL,
            end_date REAL,
            duration REAL,
            total_distance REAL,
            total_energy_burned REAL
        );
    """)
    t1 = 1655287200 - APPLE_EPOCH
    conn.execute("INSERT INTO data_type VALUES (7,'Steps')")
    conn.execute("INSERT INTO data_type VALUES (19,'Heart Rate')")
    conn.execute("INSERT INTO sources VALUES (1,'iPhone')")
    conn.execute("INSERT INTO samples VALUES (1,7,?,?,8500.0,1)", (t1, t1 + 86400))
    conn.execute("INSERT INTO samples VALUES (2,19,?,?,72.0,1)", (t1, t1 + 60))
    conn.execute("INSERT INTO workouts VALUES (1,'HKWorkoutActivityTypeRunning',?,?,1800.0,5000.0,350.0)", (t1, t1 + 1800))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_kik_db() -> bytes:
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE ZKIKPERSON (
            Z_PK INTEGER PRIMARY KEY,
            BJID TEXT,
            DISPLAY_NAME TEXT
        );
        CREATE TABLE ZKIKMESSAGE (
            Z_PK INTEGER PRIMARY KEY,
            BODY TEXT,
            TIMESTAMP INTEGER,
            SENDER_JID TEXT,
            CONVO_ID TEXT,
            WAS_ME INTEGER
        );
    """)
    conn.execute("INSERT INTO ZKIKPERSON VALUES (1,'alice_kik@kik.com','Alice')")
    conn.execute("INSERT INTO ZKIKMESSAGE VALUES (1,'Hey Kik!',1655287200,'alice_kik@kik.com','kik_conv_1',0)")
    conn.execute("INSERT INTO ZKIKMESSAGE VALUES (2,'Kik reply',1655290800,'me@kik.com','kik_conv_1',1)")
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_sms_db_with_gaps() -> bytes:
    """sms.db with ROWID gaps (simulates deleted messages)."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT, service TEXT, uncanonicalized_id TEXT);
        CREATE TABLE message (ROWID INTEGER PRIMARY KEY, guid TEXT, text TEXT, attributedBody BLOB,
            handle_id INTEGER, is_from_me INTEGER, date INTEGER, service TEXT,
            cache_has_attachments INTEGER DEFAULT 0);
        CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, guid TEXT, chat_identifier TEXT,
            display_name TEXT, service_name TEXT);
        CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER, PRIMARY KEY (chat_id, message_id));
        CREATE TABLE attachment (ROWID INTEGER PRIMARY KEY, guid TEXT, filename TEXT, mime_type TEXT);
        CREATE TABLE message_attachment_join (message_id INTEGER, attachment_id INTEGER,
            PRIMARY KEY (message_id, attachment_id));
    """)
    conn.execute("INSERT INTO handle VALUES (1,'+15551234567','iMessage',NULL)")
    t1 = 1655287200 - APPLE_EPOCH
    t2 = 1655290800 - APPLE_EPOCH
    t3 = 1655294400 - APPLE_EPOCH
    # ROWIDs 1, 5, 10 — gaps of 3 and 4
    conn.execute("INSERT INTO message(ROWID,text,is_from_me,date,service) VALUES (1,'First',0,?,  'iMessage')", (t1,))
    conn.execute("INSERT INTO message(ROWID,text,is_from_me,date,service) VALUES (5,'Fifth',0,?,  'iMessage')", (t2,))
    conn.execute("INSERT INTO message(ROWID,text,is_from_me,date,service) VALUES (10,'Tenth',1,?, 'iMessage')", (t3,))
    conn.commit()
    conn.close()
    data = Path(tmp).read_bytes()
    os.unlink(tmp)
    return data


def _make_segb_file() -> bytes:
    """Build a minimal 2-record SEGB file for Biome tests."""
    import struct
    ts = 680054400.0   # arbitrary Apple epoch timestamp
    payload = b'\x08\x01'  # minimal protobuf (field 1, varint 1)
    record = struct.pack(">d", ts) + struct.pack("<I", len(payload)) + payload
    # Pad record to 8-byte alignment
    record += b'\x00' * ((8 - len(record) % 8) % 8)
    return record * 2 + b'SEGB'


# ── Second-round root fixtures ────────────────────────────────────────────

@pytest.fixture(scope="session")
def knowledgec_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_knowledgec")
    _minimal_backup(root, "HomeDomain",
                    "Library/CoreDuet/Knowledge/knowledgeC.db",
                    _make_knowledgec_db())
    return root


@pytest.fixture(scope="session")
def interactionc_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_interactionc")
    _minimal_backup(root, "HomeDomain",
                    "Library/CoreDuet/People/interactionC.db",
                    _make_interactionc_db())
    return root


@pytest.fixture(scope="session")
def tcc_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_tcc")
    _minimal_backup(root, "HomeDomain", "Library/TCC/TCC.db", _make_tcc_db())
    return root


@pytest.fixture(scope="session")
def data_usage_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_data_usage")
    _minimal_backup(root, "WirelessDomain",
                    "Library/Databases/DataUsage.sqlite",
                    _make_data_usage_db())
    return root


@pytest.fixture(scope="session")
def accounts_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_accounts")
    _minimal_backup(root, "HomeDomain",
                    "Library/Accounts/Accounts3.sqlite",
                    _make_accounts_db())
    return root


@pytest.fixture(scope="session")
def wallet_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_wallet")
    _minimal_backup(root, "HomeDomain",
                    "Library/Passes/passes23.sqlite",
                    _make_wallet_db())
    return root


@pytest.fixture(scope="session")
def reminders_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_reminders")
    _minimal_backup(root, "HomeDomain",
                    "Library/Reminders/Container_v1/Stores/Data-ABCDEF.sqlite",
                    _make_reminders_db())
    return root


@pytest.fixture(scope="session")
def bluetooth_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_bluetooth")
    _minimal_backup(
        root,
        "SystemPreferencesDomain",
        "Library/Preferences/com.apple.MobileBluetooth.devices.plist",
        _make_bluetooth_plist(),
    )
    return root


@pytest.fixture(scope="session")
def deleted_apps_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_deleted_apps")
    _minimal_backup(root, "HomeDomain",
                    "Library/MobileInstallation/UninstalledApplications.plist",
                    _make_uninstalled_plist())
    return root


@pytest.fixture(scope="session")
def sms_gaps_root(tmp_path_factory) -> Path:
    """Backup where sms.db has ROWID gaps (simulates deleted messages)."""
    root = tmp_path_factory.mktemp("backup_sms_gaps")
    _minimal_backup(root, "HomeDomain", "Library/SMS/sms.db",
                    _make_sms_db_with_gaps())
    return root


@pytest.fixture(scope="session")
def biome_root(tmp_path_factory) -> Path:
    """Backup with two synthetic SEGB Biome stream files."""
    root = tmp_path_factory.mktemp("backup_biome")
    file_map: Dict = {}
    segb = _make_segb_file()
    _place_file(root, "HomeDomain",
                "Library/Biome/streams/restricted/_DKEvent.App.inFocus/local/abc123",
                segb, file_map)
    _place_file(root, "HomeDomain",
                "Library/Biome/streams/public/NowPlaying/local/def456",
                segb, file_map)
    _build_manifest_db(root, file_map)
    (root / "Manifest.plist").write_bytes(_make_manifest_plist(encrypted=False))
    (root / "Info.plist").write_bytes(_make_info_plist())
    return root


@pytest.fixture(scope="session")
def health_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_health")
    _minimal_backup(root, "HomeDomain",
                    "Library/Health/healthdb_secure.sqlite",
                    _make_health_db())
    return root


@pytest.fixture(scope="session")
def kik_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("backup_kik")
    _minimal_backup(root, "AppDomain-com.kik.chat",
                    "kik.sqlite", _make_kik_db())
    return root
