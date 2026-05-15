"""Shared fixtures: synthetic iTunes backup with all iOS database schemas."""
import hashlib
import os
import plistlib
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict

import pytest

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
    import json
    whatsapp_meta = plistlib.dumps({
        "itemName": "WhatsApp",
        "bundleShortVersionString": "22.5.1",
        "artistName": "WhatsApp Inc.",
        "genre": "Social Networking",
    })
    _place_file(root, "AppDomain-net.whatsapp.WhatsApp",
                "iTunesMetadata.plist", whatsapp_meta, file_map)

    # Manifest files
    _build_manifest_db(root, file_map)
    (root / "Manifest.plist").write_bytes(_make_manifest_plist(encrypted=False))
    (root / "Info.plist").write_bytes(_make_info_plist())

    return root


@pytest.fixture(scope="session")
def backup_source(backup_root):
    """Opened BackupSource over the synthetic backup."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[3]))
    from forensic.sources.backup import BackupSource
    src = BackupSource(str(backup_root))
    src.open()
    yield src
    src.close()


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
