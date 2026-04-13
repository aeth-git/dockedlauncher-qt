# DockedLauncher

A lightweight, dockable application launcher for Windows. Pin it to any screen edge for instant access to your shortcuts.

![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue) ![PyQt5](https://img.shields.io/badge/GUI-PyQt5-green) ![Enterprise Safe](https://img.shields.io/badge/enterprise-safe-brightgreen)

---

## How It Works

DockedLauncher lives as a **small tab** on the edge of your screen. Hover over it and a **panel slides out** with your shortcuts. Move your mouse away and it disappears. That's it.

```
Screen Edge
    |
    |  [tab]  <-- hover to expand
    |
    |  +------------+
    |  | Launcher   |  <-- drag header to reposition
    |  |------------|
    |  | [icon] App |  <-- click to launch
    |  | [icon] App |  <-- drag off to remove
    |  |------------|
    |  | [+]    [gear]|  <-- add shortcut / settings
    |  +------------+
```

### Adding Shortcuts

- **Drag and drop** any `.exe`, `.lnk`, `.bat`, `.cmd`, or `.url` file onto the expanded panel
- Or click the **+** button and browse

### Removing Shortcuts

- **Drag** a shortcut off the panel to remove it
- Or **right-click** and choose "Remove"

### Repositioning

- **Drag the header bar** anywhere on screen
- Release and it **snaps to the nearest edge**
- Works on all 4 edges (left, right, top, bottom)
- Your position is remembered between sessions

---

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/dockedlauncher-qt.git
cd dockedlauncher-qt
pip install -r requirements.txt
```

### Requirements

- Python 3.6+
- Windows 10/11
- Dependencies: `PyQt5`, `Pillow`

---

## Usage

### Run

Double-click `run.bat` or:

```bash
pythonw -m launcher
```

> Uses `pythonw` so no terminal window appears.

### Command-Line Options

```bash
python -m launcher --edge left      # start docked to the left
python -m launcher --edge right     # start docked to the right
python -m launcher --monitor 1      # dock to second monitor
```

### Settings

Click the **gear icon** to configure:

| Setting | Options | Default |
|---------|---------|---------|
| Theme | Dark / Light | Dark |
| Opacity | 50% - 100% | 95% |
| Dock Edge | Left / Right / Top / Bottom | Left |
| Auto-start | On / Off | On |

---

## Enterprise Safety

Designed for corporate environments with strict IT policies:

| Concern | How it's handled |
|---------|-----------------|
| Network access | **Zero** network calls. No update checks, telemetry, or analytics. |
| Registry edits | **None**. Auto-start uses the Startup folder, not the registry. |
| Admin privileges | **Not required**. Runs entirely in user space. |
| DLL injection | **None**. Uses standard Python + PyQt5. |
| Background services | **None**. Single foreground process. |
| Data storage | Only `%APPDATA%/DockedLauncher/config.json`. |
| Dependencies | PyQt5 and Pillow. Both widely-used, well-known packages. |
| Source code | Fully open and auditable. |

---

## Project Structure

```
dockedlauncher-qt/
  launcher/
    main.py              # Entry point, DPI setup
    main_window.py       # Tab/panel window (collapse, expand, dock)
    shortcut_widget.py   # Individual shortcut (icon, label, interactions)
    dock_engine.py       # Screen edge detection and positioning
    icon_provider.py     # High-res icon extraction (256x256 jumbo)
    animations.py        # QPropertyAnimation helpers
    config.py            # JSON config load/save
    settings_dialog.py   # Settings panel
    startup.py           # Windows Startup folder integration
    constants.py         # Dimensions, colors, defaults
  tests/
    test_config.py
    test_dock_engine.py
    test_icon_provider.py
    test_startup.py
  requirements.txt
  run.bat
```

---

## Configuration

Stored at `%APPDATA%/DockedLauncher/config.json`:

```json
{
  "dock_edge": "left",
  "monitor": 0,
  "theme": "dark",
  "opacity": 0.95,
  "auto_start": true,
  "edge_offset": 0.5,
  "shortcuts": [
    { "path": "C:\\path\\to\\app.lnk", "name": "App Name" }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `dock_edge` | string | `"left"`, `"right"`, `"top"`, or `"bottom"` |
| `monitor` | int | Monitor index (0-based) |
| `theme` | string | `"dark"` or `"light"` |
| `opacity` | float | Window opacity, 0.5 to 1.0 |
| `auto_start` | bool | Launch on Windows startup |
| `edge_offset` | float | Position along the edge, 0.0 to 1.0 |
| `shortcuts` | array | List of `{path, name}` objects |

---

## 4K / High-DPI Support

DockedLauncher handles high-DPI displays natively:

- `Qt.AA_EnableHighDpiScaling` is set before the application starts
- All positioning uses `QScreen.availableGeometry()` which returns correct logical coordinates
- Icons are extracted at 256x256 (jumbo) via Windows `SHGetImageList` and converted with `QtWin.fromHICON` for correct color channels
- No manual DPI math anywhere in the codebase

---

## License

MIT
