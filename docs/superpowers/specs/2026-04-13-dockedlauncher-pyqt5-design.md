# DockedLauncher PyQt5 Rewrite - Design Spec

## Context

Rewrite the DockedLauncher application from CustomTkinter to PyQt5. The CTk version (C:\dockedlauncher) has persistent DPI scaling issues on 4K monitors at 150% scaling - CTk applies its own window scaling that conflicts with manual positioning, making edge-flush docking impossible without fragile hacks. PyQt5 handles high-DPI natively via `Qt.AA_EnableHighDpiScaling`.

**Goal**: 1:1 feature port that actually works on 4K displays. Same config schema so existing settings carry over.

## Requirements (carried from CTk version)

- Dock to any screen edge (left, right, top, bottom) on any monitor
- Collapse to a small tab when not in use; expand on hover
- User can drag the tab to any position along any edge
- Drag-and-drop .lnk/.bat/.exe/.cmd/.url files from Explorer to add shortcuts
- Hi-res icon extraction matching what Windows Explorer shows
- Click shortcut to launch via `os.startfile()`
- Right-click context menu: Move Up, Move Down, Remove
- Drag shortcut off the window to remove it (with visual ghost)
- Hover highlight on shortcut items
- Settings panel: theme (dark/light), opacity, dock edge, auto-start toggle
- Auto-start via Windows Startup folder .bat (no registry edits)
- Config persisted as JSON in `%APPDATA%/DockedLauncher/config.json`
- Enterprise-safe: zero network calls, no registry edits, no admin elevation, no background services

## Architecture

### Approach

Single `QWidget` with `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`. The widget has two states: collapsed (small tab) and expanded (full panel). Same conceptual model as the CTk version but with Qt handling all DPI, drag-drop, icons, and animation natively.

### Project Structure

```
C:\dockedlauncher-qt\
├── requirements.txt          # PyQt5, Pillow
├── .gitignore
├── README.md
├── run.bat
├── launcher/
│   ├── __init__.py
│   ├── __main__.py
│   ├── main.py               # Entry point, DPI setup, arg parsing
│   ├── main_window.py        # DockedLauncher QWidget (~200 lines)
│   ├── shortcut_widget.py    # ShortcutItem QWidget (~150 lines)
│   ├── dock_engine.py        # Edge detection, snap logic (~100 lines)
│   ├── icon_provider.py      # Icon extraction (~80 lines)
│   ├── config.py             # JSON config manager (~40 lines)
│   ├── constants.py          # Dimensions, colors, defaults
│   ├── settings_dialog.py    # QDialog for settings (~100 lines)
│   ├── startup.py            # Windows Startup folder .bat logic
│   └── animations.py         # QPropertyAnimation helpers (~50 lines)
└── tests/
    ├── test_config.py
    ├── test_dock_engine.py
    ├── test_icon_provider.py
    └── test_startup.py
```

### Dependencies

```
PyQt5>=5.15.0
Pillow>=8.0.0
```

No tkinterdnd2, no customtkinter, no ctypes for monitor enumeration.

## Component Design

### main.py - Entry Point

- `QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)` before creating `QApplication`
- Parse CLI args: `--edge`, `--monitor`
- Load config, enable auto-start on first run
- Instantiate `DockedLauncher`, run `app.exec_()`

### main_window.py - DockedLauncher

A `QWidget` with two visual states managed by showing/hiding child layouts.

**Window flags**: `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`
- `Qt.Tool` keeps it off the taskbar

**Collapsed state (tab)**:
- 28x80 widget (vertical edges) or 80x28 (horizontal edges)
- Arrow label pointing inward
- Flush against screen edge at saved offset position

**Expanded state (panel)**:
- 220xN pixels, N = header(32) + shortcuts(52 each) + bottom_bar(36) + padding(12)
- Capped at 80% of screen edge length, minimum 130px
- `QVBoxLayout`: header, `QScrollArea` with shortcuts, bottom bar
- Anchored to the tab's actual position

**Hover detection**:
- `QTimer` polling at 150ms interval
- Checks `QCursor.pos()` against window geometry + 15px margin
- Collapsed + cursor inside → expand
- Expanded + cursor outside for 3 consecutive polls (~450ms) → collapse
- No reliance on `enterEvent`/`leaveEvent`

**Drag-to-reposition**:
- `mousePressEvent` on header bar records drag start
- `mouseMoveEvent` moves window to cursor position
- `mouseReleaseEvent` → `dock_engine.find_nearest_edge()` → `QPropertyAnimation` snap to edge → collapse to tab
- Saves `dock_edge`, `monitor`, `edge_offset` to config

**Drag-and-drop from Explorer**:
- `setAcceptDrops(True)`
- `dragEnterEvent`: accept if `event.mimeData().hasUrls()`
- `dropEvent`: iterate `event.mimeData().urls()`, add each as shortcut
- Panel expands via hover polling when user drags near the tab

### shortcut_widget.py - ShortcutItem

Custom `QWidget` representing one shortcut in the list.

**Layout**: `QHBoxLayout` with icon `QLabel` (40x40) and name `QLabel`
**Height**: 52px fixed

**Interactions**:
- `enterEvent`/`leaveEvent`: toggle background color (default → accent blue)
- `mousePressEvent` + `mouseReleaseEvent` (no drag): `os.startfile(path)`
- `mousePressEvent` + `mouseMoveEvent` (>8px): start `QDrag`
  - Drag pixmap: shortcut name on dark background
  - If released outside main window → remove shortcut
  - If released inside → cancel, snap back
- `contextMenuEvent`: `QMenu` with Move Up, Move Down, separator, Remove

### dock_engine.py - Edge Detection

Uses `QApplication.screens()` and `QScreen.availableGeometry()` for all positioning. No ctypes, no manual DPI.

**Functions**:
- `get_screens()` → list of `(index, QRect)` from `QApplication.screens()`
- `find_nearest_edge(center_point, screens)` → `(edge, screen_index, offset)`
  - Computes distance from window center to each edge of each screen
  - Returns closest edge, which screen, and 0.0-1.0 offset along that edge
- `get_panel_size(edge, num_shortcuts, screen_rect)` → `QSize`
  - Adaptive: `HEADER + shortcuts*ITEM_HEIGHT + BOTTOM_BAR + padding`
  - Capped at `screen_edge_length * 0.8`, minimum 130px
- `get_tab_rect(edge, offset, screen_rect)` → `QRect`
  - Tab flush against edge, at offset position along edge
- `get_panel_rect(edge, offset, num_shortcuts, screen_rect)` → `QRect`
  - Panel anchored to tab position, clamped to screen bounds

### icon_provider.py - Icon Extraction

**Primary**: `QFileIconProvider().icon(QFileInfo(path))` → returns native shell icon at full resolution. One line.

**Fallback for .lnk files**: If icon is generic/blank, resolve .lnk target via PowerShell subprocess, re-extract from target .exe.

**Cache**: `dict` keyed by `os.path.normcase(path)` → `QIcon`

**Default**: Embedded blue square `QPixmap` for files with no extractable icon.

### animations.py - Animation Helpers

- `slide_widget(widget, start_rect, end_rect, duration_ms=300, callback=None)`
  - Creates `QPropertyAnimation` on the `geometry` property
  - `QEasingCurve.InOutCubic` easing
  - Calls `callback` on `finished` signal
- Qt handles frame timing and GPU acceleration

### config.py - Config Manager

Identical to CTk version:
- `load_config()` → read JSON, merge with `DEFAULT_SETTINGS`
- `save_config(data)` → atomic write (temp + rename)
- Path: `%APPDATA%/DockedLauncher/config.json`

### Config Schema (unchanged)

```json
{
  "dock_edge": "left",
  "monitor": 0,
  "theme": "dark",
  "opacity": 0.95,
  "auto_start": true,
  "edge_offset": 0.5,
  "shortcuts": [
    {"path": "C:\\path\\to\\file.lnk", "name": "Display Name"}
  ]
}
```

### settings_dialog.py - Settings Panel

`QDialog` with `Qt.WindowStaysOnTopHint`:
- Theme: `QRadioButton` group (Dark / Light) → applies `QPalette` or QSS stylesheet
- Opacity: `QSlider` (50-100) → `setWindowOpacity(value / 100)`
- Dock edge: 4 `QRadioButton`s (Left / Right / Top / Bottom)
- Auto-start: `QCheckBox` → `startup.enable/disable_auto_start()`
- Changes apply immediately, config saved on close

### startup.py - Auto-Start

Identical to CTk version:
- `enable_auto_start()` → create .bat in `%APPDATA%/Microsoft/Windows/Start Menu/Programs/Startup/`
- `disable_auto_start()` → remove .bat
- `is_auto_start_enabled()` → check .bat exists
- No registry edits

### constants.py - Dimensions & Defaults

```python
TAB_W = 28
TAB_H = 80
PANEL_WIDTH = 220
ICON_SIZE = 40
SHORTCUT_ITEM_HEIGHT = 52
HEADER_HEIGHT = 32
BOTTOM_BAR_HEIGHT = 36
MIN_PANEL_LENGTH = 130
MAX_PANEL_RATIO = 0.8
ANIMATION_DURATION_MS = 300
HOVER_POLL_MS = 150
LEAVE_POLLS_TO_COLLAPSE = 3
ACCENT_COLOR = "#1f6aa5"
DEFAULT_SETTINGS = { ... }
```

## DPI Handling

**Before** (CTk): Manual `_dpi_scale` factor, `ctk.ScalingTracker`, coordinate space mismatches between ctypes monitors and tkinter geometry, CTk overriding geometry calls.

**After** (PyQt5): One line in `main.py`:
```python
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
```
All `QScreen.availableGeometry()`, `QCursor.pos()`, `QWidget.geometry()` operate in consistent logical coordinates automatically. No manual DPI math.

## Enterprise Safety (unchanged)

- Zero network calls
- No Windows Registry edits (Startup folder .bat only)
- No admin/UAC elevation
- No DLL injection or hooking
- No background services or system tray processes
- No temp files outside AppData
- Dependencies: PyQt5 (well-known, widely-used), Pillow

## Verification Plan

1. `pip install -r requirements.txt` succeeds
2. `python -m launcher` launches - tab visible at correct edge, flush
3. Hover tab → panel expands with smooth animation
4. Move mouse away → panel collapses after ~450ms
5. Drag header to each edge → snaps correctly, tab stays flush
6. Drag header to corner → tab stays at that offset on the edge
7. Drag .lnk from Explorer onto expanded panel → shortcut appears with correct icon
8. Drag .exe onto panel → appears with icon
9. Click shortcut → target launches
10. Right-click → Move Up/Down/Remove work
11. Drag shortcut off panel → ghost shows, shortcut removed
12. Drag shortcut inside panel → snaps back, not removed
13. Settings gear → theme/opacity/edge changes apply immediately
14. Restart app → all shortcuts and settings persist
15. Test on 4K monitor at 150% scaling → tab flush on all 4 edges
16. Test on 1080p at 100% scaling → still works correctly
17. No network activity in Task Manager
