"""Forensic app constants — Swiss minimalist palette (mirrors launcher)."""
import os

APP_NAME = "iForensic"
APP_VERSION = "1.0.0"

# --- Swiss palette (identical to launcher) ---
PAPER = "#ffffff"
PAPER_SOFT = "#fafafa"
INK = "#0a0a0a"
INK_SOFT = "#4a4a4a"
INK_MUTED = "#8a8a8a"
HAIRLINE = "#e5e5e5"
HOVER = "#f2f2f2"
RED = "#e30613"
RED_LIGHT = "#fff5f5"
RED_BUBBLE = "#fff0f0"

# --- Typography ---
FONT_FAMILY = "Helvetica Neue, Helvetica, Arial, sans-serif"
FONT_SIZE_TITLE = 13
FONT_SIZE_DATA = 11
FONT_SIZE_LABEL = 9

# --- Window ---
WINDOW_MIN_W = 1100
WINDOW_MIN_H = 700
WINDOW_DEFAULT_W = 1280
WINDOW_DEFAULT_H = 820

# --- Source bar ---
SOURCE_BAR_H = 52
DEVICE_INFO_BAR_H = 32

# --- Table rows ---
ROW_H = 44
HEADER_H = 32

# --- Photos grid ---
THUMB_CELL = 148
THUMB_IMG = 140

# --- Message conversation panel ---
CONV_LIST_W = 280
BUBBLE_RADIUS = 8
BUBBLE_MAX_W = 500

# --- Skeleton shimmer ---
SHIMMER_ROWS = 12

# --- Log dir ---
LOG_DIR = os.path.join(os.path.expanduser("~"), ".iforensic")

# --- Domain → filesystem prefix map (raw image sources) ---
DOMAIN_FS_MAP = {
    "HomeDomain": "private/var/mobile",
    "CameraRollDomain": "private/var/mobile/Media",
    "AppDomain": "private/var/mobile/Containers/Data/Application",
}

# --- Known backup DB paths (domain, relative_path) ---
SMS_DB = ("HomeDomain", "Library/SMS/sms.db")
CALL_DB = ("HomeDomain", "Library/CallHistoryDB/CallHistory.storedata")
CONTACTS_DB = ("HomeDomain", "Library/AddressBook/AddressBook.sqlitedb")
DCIM_DOMAIN = "CameraRollDomain"
DCIM_PREFIX = "Media/DCIM"

# --- Apple system DB paths ---
SAFARI_HISTORY_DB = ("HomeDomain", "Library/Safari/History.db")
SAFARI_BOOKMARKS_DB = ("HomeDomain", "Library/Safari/Bookmarks.db")
NOTES_DB = ("AppDomain-group.com.apple.notes", "NoteStore.sqlite")
CALENDAR_DB = ("HomeDomain", "Library/Calendar/Calendar.sqlitedb")
VOICEMAIL_DB = ("HomeDomain", "Library/Voicemail/voicemail.db")
LOCATION_CONSOLIDATED_DB = ("RootDomain", "Library/Caches/locationd/consolidated.db")
LOCATION_ROUTINED_DB = ("HomeDomain", "Library/Caches/com.apple.routined/Local.sqlite")
WIFI_KNOWN_NETWORKS = ("SystemPreferencesDomain",
                       "Library/Preferences/SystemConfiguration/com.apple.wifi.known-networks.plist")
WIFI_PREFS = ("SystemPreferencesDomain",
              "Library/Preferences/com.apple.wifi.plist")

# --- Third-party bundles ---
BUNDLE_WHATSAPP = "net.whatsapp.WhatsApp"
BUNDLE_TELEGRAM = "ph.telegra.Telegraph"
BUNDLE_SIGNAL = "org.whispersystems.signal"
BUNDLE_MESSENGER = "com.facebook.Messenger"
BUNDLE_INSTAGRAM = "com.burbn.instagram"
BUNDLE_SNAPCHAT = "com.toyopagroup.picaboo"
BUNDLE_VIBER = "com.viber"
BUNDLE_LINE = "jp.naver.line"
BUNDLE_WECHAT = "com.tencent.xin"
BUNDLE_DISCORD = "com.hammerandchisel.discord"
BUNDLE_SKYPE = "com.skype.skype"

# --- Second-round parser DB paths ---
KNOWLEDGE_C_DB = ("HomeDomain", "Library/CoreDuet/Knowledge/knowledgeC.db")
INTERACTION_C_DB = ("HomeDomain", "Library/CoreDuet/People/interactionC.db")
TCC_DB = ("HomeDomain", "Library/TCC/TCC.db")
TCC_ROOT_DB = ("RootDomain", "Library/Logs/Accessibility/TCC.db")
DATA_USAGE_DB = ("WirelessDomain", "Library/Databases/DataUsage.sqlite")
ACCOUNTS_DB = ("HomeDomain", "Library/Accounts/Accounts3.sqlite")
WALLET_DB = ("HomeDomain", "Library/Passes/passes23.sqlite")
BLUETOOTH_PLIST = ("SystemPreferencesDomain",
                   "Library/Preferences/com.apple.MobileBluetooth.devices.plist")
BUNDLE_KIK = "com.kik.chat"

# ABMultiValue property codes
AB_PROP_PHONE = 3
AB_PROP_EMAIL = 4

AB_LABEL_MAP = {
    1: "home", 2: "work", 3: "other", 4: "mobile",
    5: "main", 6: "home fax", 7: "work fax", 8: "pager",
}
