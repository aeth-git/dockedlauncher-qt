"""Application constants - dimensions, glassmorphism palette, typography."""
import os

APP_NAME = "DockedLauncher"

# Edges
LEFT = "left"
RIGHT = "right"
TOP = "top"
BOTTOM = "bottom"
EDGES = [LEFT, RIGHT, TOP, BOTTOM]

# Tab dimensions
TAB_W = 16
TAB_H = 90

# Panel dimensions
PANEL_WIDTH = 200
ICON_SIZE = 28
SHORTCUT_ITEM_HEIGHT = 38
HEADER_HEIGHT = 28
BOTTOM_BAR_HEIGHT = 32
MIN_PANEL_LENGTH = 130
MAX_PANEL_RATIO = 0.8

# Animation
ANIMATION_DURATION_MS = 300
SNAP_ANIMATION_MS = 200
HOVER_FADE_MS = 150
TAB_GLOW_PULSE_MS = 3000

# Hover polling
HOVER_POLL_MS = 100
LEAVE_POLLS_TO_COLLAPSE = 4  # ~400ms

# Opacity
DEFAULT_OPACITY = 0.95
MIN_OPACITY = 0.5
MAX_OPACITY = 1.0

# Glassmorphism colors
ACCENT_COLOR = "#3b82f6"
ACCENT_LIGHT = "#60a5fa"
GLASS_BG = "rgba(15, 23, 42, 0.88)"
GLASS_BG_SOLID = "#0f172a"
GLASS_BORDER = "rgba(148, 163, 184, 0.15)"
GLASS_HIGHLIGHT = "rgba(255, 255, 255, 0.05)"
HEADER_COLOR = "rgba(30, 41, 59, 0.9)"
HEADER_COLOR_SOLID = "#1e293b"

# Item colors
ITEM_BG = "transparent"
ITEM_HOVER_COLOR = "rgba(59, 130, 246, 0.18)"
DRAG_REMOVE_COLOR = "#ef4444"

# Text
TEXT_PRIMARY = "#f8fafc"
TEXT_SECONDARY = "#94a3b8"
TEXT_MUTED = "#64748b"

# Shadows
SHADOW_BLUR = 24
SHADOW_COLOR_RGBA = (0, 0, 0, 80)
SHADOW_OFFSET = 2

# Typography
FONT_FAMILY = "Segoe UI Variable, Segoe UI, sans-serif"
FONT_SIZE_TITLE = 9
FONT_SIZE_ITEM = 9
FONT_SIZE_SMALL = 8
FONT_SIZE_BUTTON = 11

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
    LEFT: "\u25B6",
    RIGHT: "\u25C0",
    TOP: "\u25BC",
    BOTTOM: "\u25B2",
}
