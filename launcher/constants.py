"""Application constants - Swiss minimalist palette."""
import os

APP_NAME = "DockedLauncher"

# Edges
LEFT = "left"
RIGHT = "right"
TOP = "top"
BOTTOM = "bottom"
EDGES = [LEFT, RIGHT, TOP, BOTTOM]

# Tab dimensions - findable but restrained pull-handle
TAB_W = 14
TAB_H = 80

# Panel dimensions
PANEL_WIDTH = 220
ICON_SIZE = 28
SHORTCUT_ITEM_HEIGHT = 42
HEADER_HEIGHT = 32
BOTTOM_BAR_HEIGHT = 32
MIN_PANEL_LENGTH = 120
MAX_PANEL_RATIO = 0.8

# Animation
ANIMATION_DURATION_MS = 200
SNAP_ANIMATION_MS = 180
HOVER_FADE_MS = 100
TAB_GLOW_PULSE_MS = 0  # no pulse

# Hover polling
HOVER_POLL_MS = 100
LEAVE_POLLS_TO_COLLAPSE = 4

# Opacity
DEFAULT_OPACITY = 1.0
MIN_OPACITY = 0.7
MAX_OPACITY = 1.0

# --- Swiss palette ---
PAPER = "#ffffff"          # primary background
PAPER_SOFT = "#fafafa"     # secondary surface (scroll area)
INK = "#0a0a0a"            # primary text / foreground
INK_SOFT = "#4a4a4a"       # secondary text
INK_MUTED = "#8a8a8a"      # tertiary / labels
HAIRLINE = "#e5e5e5"       # 1px separators, borders
HOVER = "#f2f2f2"          # item hover background
RED = "#e30613"            # single Swiss red accent (used sparingly)

# Legacy aliases (so other files that still reference these don't break)
ACCENT_COLOR = RED
ACCENT_LIGHT = RED
GLASS_BG = PAPER
GLASS_BG_SOLID = PAPER
GLASS_BORDER = HAIRLINE
GLASS_HIGHLIGHT = PAPER
HEADER_COLOR = PAPER
HEADER_COLOR_SOLID = PAPER
ITEM_BG = PAPER
ITEM_HOVER_COLOR = HOVER
DRAG_REMOVE_COLOR = RED
TEXT_PRIMARY = INK
TEXT_SECONDARY = INK_SOFT
TEXT_MUTED = INK_MUTED

# Shadows - single subtle drop shadow on the panel only
SHADOW_BLUR = 16
SHADOW_COLOR_RGBA = (0, 0, 0, 40)
SHADOW_OFFSET = 1

# Typography - Helvetica-like grotesque sans
FONT_FAMILY = "Helvetica Neue, Helvetica, Arial, sans-serif"
FONT_SIZE_TITLE = 10
FONT_SIZE_ITEM = 11
FONT_SIZE_SMALL = 9
FONT_SIZE_BUTTON = 12

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
    "theme": THEME_LIGHT,
    "opacity": DEFAULT_OPACITY,
    "auto_start": True,
    "edge_offset": 0.5,
    "shortcuts": [],
}

# Arrow characters (unused in Swiss design but kept for compatibility)
EDGE_ARROWS = {
    LEFT: "\u25B6",
    RIGHT: "\u25C0",
    TOP: "\u25BC",
    BOTTOM: "\u25B2",
}
