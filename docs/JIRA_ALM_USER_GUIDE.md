h1. DockedLauncher - User Guide

h2. Overview

DockedLauncher is a lightweight application launcher that docks to the edge of your screen. Hover to expand, click to launch, drag to customize.

||Feature||Description||
|Edge Docking|Pin to any screen edge (left, right, top, bottom)|
|Auto-Hide|Collapses to a small tab when not in use|
|Drag & Drop|Drop shortcuts from Windows Explorer to add them|
|High-DPI|Native 4K support with crisp icons|
|Enterprise Safe|No network, no registry, no admin required|

----

h2. Getting Started

h3. Installation

{code}
git clone https://github.com/YOUR_USERNAME/dockedlauncher-qt.git
cd dockedlauncher-qt
pip install -r requirements.txt
{code}

*Requirements:*
* Python 3.6 or higher
* Windows 10 or 11
* PyQt5 and Pillow (installed automatically via requirements.txt)

h3. Running the Launcher

Double-click {{run.bat}} or run from command line:

{code}
pythonw -m launcher
{code}

{note}Uses {{pythonw}} so no terminal window appears.{note}

----

h2. Using the Launcher

h3. The Tab

When DockedLauncher is running, a small *blue tab* appears at the edge of your screen. This is the launcher in its collapsed state.

* *Hover* over the tab to expand the panel
* *Move your mouse away* and it collapses after about half a second

h3. Adding Shortcuts

You can add shortcuts two ways:

# *Drag and drop* - Drag any {{.exe}}, {{.lnk}}, {{.bat}}, {{.cmd}}, or {{.url}} file from Windows Explorer onto the expanded panel
# *Browse* - Click the *+* button at the bottom of the panel and select a file

h3. Launching Applications

* *Click* any shortcut in the panel to launch it
* The application opens immediately via the Windows shell

h3. Removing Shortcuts

* *Drag off* - Drag a shortcut outside the panel window and release. A ghost label follows your cursor to confirm the action.
* *Right-click* - Right-click any shortcut and select *Remove*

h3. Reordering Shortcuts

* *Right-click* any shortcut and select *Move Up* or *Move Down*

h3. Repositioning the Launcher

# *Hover* the tab to expand the panel
# *Drag the header bar* (the bar at the top that says "Launcher")
# *Move it anywhere* on screen
# *Release* - it snaps to the nearest screen edge
# Your position is saved automatically

----

h2. Settings

Click the *gear icon* at the bottom-right of the expanded panel to open Settings.

||Setting||Options||Default||Description||
|Theme|Dark / Light|Dark|Changes the panel color scheme|
|Opacity|50% - 100%|95%|How transparent the panel appears|
|Dock Edge|Left / Right / Top / Bottom|Left|Which screen edge the launcher docks to|
|Auto-start|On / Off|On|Whether the launcher starts with Windows|

Settings are applied immediately. No restart required.

----

h2. Command-Line Options

||Option||Example||Description||
|{{--edge}}|{{python -m launcher --edge right}}|Set the initial dock edge|
|{{--monitor}}|{{python -m launcher --monitor 1}}|Dock to a specific monitor (0-based index)|

----

h2. Configuration File

Settings are stored at:

{code}
%APPDATA%\DockedLauncher\config.json
{code}

Example:
{code:json}
{
  "dock_edge": "left",
  "monitor": 0,
  "theme": "dark",
  "opacity": 0.95,
  "auto_start": true,
  "edge_offset": 0.5,
  "shortcuts": [
    { "path": "C:\\Program Files\\App\\app.exe", "name": "App Name" }
  ]
}
{code}

||Field||Type||Values||Description||
|{{dock_edge}}|String|left, right, top, bottom|Which screen edge the tab docks to|
|{{monitor}}|Integer|0, 1, 2...|Which monitor to dock on (0 = primary)|
|{{theme}}|String|dark, light|Color scheme|
|{{opacity}}|Decimal|0.5 to 1.0|Window transparency|
|{{auto_start}}|Boolean|true, false|Launch on Windows startup|
|{{edge_offset}}|Decimal|0.0 to 1.0|Position along the edge (0.5 = center)|
|{{shortcuts}}|Array|List of objects|Each shortcut has a {{path}} and {{name}}|

----

h2. Enterprise Safety & Compliance

DockedLauncher is designed for use on managed enterprise laptops.

||Security Concern||Status||Details||
|Network Access|(/)|Zero network calls. No update checks, telemetry, phone-home, or analytics.|
|Windows Registry|(/)|No registry modifications. Auto-start uses the Windows Startup folder.|
|Admin / UAC|(/)|Runs entirely in user space. No elevation required.|
|DLL Injection|(/)|No DLL injection or hooking. Standard Python + PyQt5 only.|
|Background Services|(/)|Single foreground process. No services, no system tray daemon.|
|Data Storage|(/)|Only writes to {{%APPDATA%\DockedLauncher\config.json}}.|
|Dependencies|(/)|PyQt5 (Qt framework, widely used) and Pillow (image library, widely used).|
|Source Code|(/)|Fully open source and auditable. No obfuscated or compiled code.|
|Temp Files|(/)|No temp files created outside of AppData.|

----

h2. Troubleshooting

h3. I can't see the tab

* The tab is a small blue rectangle on one of your screen edges
* Check your config file for the {{dock_edge}} value to know which edge
* Try resetting: delete {{%APPDATA%\DockedLauncher\config.json}} and restart

h3. Drag and drop isn't working

* Make sure the panel is *expanded* (hover the tab first)
* Only {{.exe}}, {{.lnk}}, {{.bat}}, {{.cmd}}, and {{.url}} files are supported
* Drag the file directly from Windows Explorer onto the panel

h3. Icons look wrong or blank

* Some applications don't embed high-resolution icons
* {{.bat}} files show the Windows script icon (this is normal)
* Try removing and re-adding the shortcut

h3. The launcher doesn't start with Windows

* Open Settings (gear icon) and make sure *Auto-start* is checked
* Check that {{%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DockedLauncher.bat}} exists

h3. How do I uninstall?

# Close the launcher (right-click the tab area or end the process)
# Delete the application folder
# Delete {{%APPDATA%\DockedLauncher\}} (removes config)
# Delete {{%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DockedLauncher.bat}} (removes auto-start)

----

h2. Project Structure

{code}
dockedlauncher-qt/
  launcher/
    main.py              Entry point and DPI setup
    main_window.py       Main window (tab/panel states, docking, hover)
    shortcut_widget.py   Individual shortcut item (icon, label, interactions)
    dock_engine.py       Screen edge detection and window positioning
    icon_provider.py     High-resolution icon extraction (256x256)
    animations.py        Smooth slide animation helpers
    config.py            JSON configuration load/save
    settings_dialog.py   Settings dialog
    startup.py           Windows Startup folder integration
    constants.py         Dimensions, colors, and defaults
  tests/
    test_config.py       Config manager tests
    test_dock_engine.py  Edge detection tests
    test_icon_provider.py  Icon extraction tests
    test_startup.py      Auto-start tests
  requirements.txt       Python dependencies
  run.bat                Quick launcher script
{code}

----

h2. Version History

||Version||Date||Changes||
|2.0.0|2026-04-13|Full rewrite from CustomTkinter to PyQt5. Native 4K support. Correct edge docking on all display configurations.|
|1.0.0|2026-04-12|Initial release using CustomTkinter.|
