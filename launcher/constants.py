"""Application constants and defaults."""
import os

APP_NAME = "DockedLauncher"

# Edges
LEFT = "left"
RIGHT = "right"
TOP = "top"
BOTTOM = "bottom"
EDGES = [LEFT, RIGHT, TOP, BOTTOM]

# Tab dimensions (collapsed state)
TAB_W = 12
TAB_H = 40

# Panel dimensions (expanded state)
PANEL_WIDTH = 150
ICON_SIZE = 24
SHORTCUT_ITEM_HEIGHT = 32
HEADER_HEIGHT = 22
BOTTOM_BAR_HEIGHT = 26
MIN_PANEL_LENGTH = 130
MAX_PANEL_RATIO = 0.8

# Animation
ANIMATION_DURATION_MS = 300
SNAP_ANIMATION_MS = 200

# Hover polling
HOVER_POLL_MS = 150
LEAVE_POLLS_TO_COLLAPSE = 3

# Opacity
DEFAULT_OPACITY = 0.95
MIN_OPACITY = 0.5
MAX_OPACITY = 1.0

# Colors - modern dark theme
ACCENT_COLOR = "#3b82f6"     # vibrant blue
HEADER_COLOR = "#1e293b"     # slate-800
HOVER_COLOR = "rgba(59,130,246,0.25)"  # translucent accent
DRAG_REMOVE_COLOR = "#ef4444"
DARK_BG = "#0f172a"          # slate-900
DARK_ITEM_BG = "#1e293b"     # slate-800
DARK_BORDER = "#334155"      # slate-700
LIGHT_BG = "#f1f5f9"
LIGHT_ITEM_BG = "#e2e8f0"
TEXT_PRIMARY = "#f8fafc"      # slate-50
TEXT_SECONDARY = "#94a3b8"    # slate-400

# Theme
THEME_DARK = "dark"
THEME_LIGHT = "light"

# Config paths
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", ""), APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# Default settings
DEFAULT_SETTINGS = {
    "dock_edge": LEFT,
    "monitor": 0,
    "theme": THEME_DARK,
    "opacity": DEFAULT_OPACITY,
    "auto_start": True,
    "edge_offset": 0.5,
    "shortcuts": [],
}

# Arrow characters for tab indicator
EDGE_ARROWS = {
    LEFT: "\u25B6",   # right-pointing (expand direction)
    RIGHT: "\u25C0",  # left-pointing
    TOP: "\u25BC",    # down-pointing
    BOTTOM: "\u25B2", # up-pointing
}
