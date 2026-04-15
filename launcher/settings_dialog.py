"""Settings panel - QWidget (not QDialog) for stability."""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QRadioButton, QSlider, QCheckBox, QPushButton, QButtonGroup,
)
from PyQt5.QtCore import Qt, pyqtSignal

from .constants import (
    LEFT, RIGHT, TOP, BOTTOM,
    THEME_DARK, THEME_LIGHT,
    MIN_OPACITY, MAX_OPACITY,
    ACCENT_COLOR, GLASS_BG_SOLID as DARK_BG,
)
from . import startup


class SettingsDialog(QWidget):
    """Settings window (top-level QWidget)."""

    settings_changed = pyqtSignal(dict)

    def __init__(self, config, parent=None):
        # No parent: standalone top-level window
        super().__init__(None)
        self._config = config.copy()
        self.setWindowTitle("Launcher Settings")
        self.setFixedSize(320, 340)
        # Standard window with title bar - simplest and most stable
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setStyleSheet("background-color: {}; color: white;".format(DARK_BG))

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Theme
        layout.addWidget(self._section_label("Theme"))
        theme_row = QHBoxLayout()
        self._theme_group = QButtonGroup(self)
        for value, label in [(THEME_DARK, "Dark"), (THEME_LIGHT, "Light")]:
            rb = QRadioButton(label)
            rb.setStyleSheet("color: white;")
            if self._config.get("theme") == value:
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, v=value: self._on_theme(v) if checked else None)
            self._theme_group.addButton(rb)
            theme_row.addWidget(rb)
        layout.addLayout(theme_row)

        # Opacity
        layout.addWidget(self._section_label("Opacity"))
        opacity_row = QHBoxLayout()
        self._opacity_slider = QSlider(Qt.Horizontal)
        self._opacity_slider.setRange(int(MIN_OPACITY * 100), int(MAX_OPACITY * 100))
        self._opacity_slider.setValue(int(self._config.get("opacity", 0.95) * 100))
        self._opacity_slider.valueChanged.connect(self._on_opacity)
        opacity_row.addWidget(self._opacity_slider)
        self._opacity_label = QLabel("{:.0f}%".format(self._config.get("opacity", 0.95) * 100))
        self._opacity_label.setStyleSheet("color: white;")
        opacity_row.addWidget(self._opacity_label)
        layout.addLayout(opacity_row)

        # Dock edge
        layout.addWidget(self._section_label("Dock Edge"))
        edge_row = QHBoxLayout()
        self._edge_group = QButtonGroup(self)
        for value, label in [(LEFT, "Left"), (RIGHT, "Right"), (TOP, "Top"), (BOTTOM, "Bottom")]:
            rb = QRadioButton(label)
            rb.setStyleSheet("color: white;")
            if self._config.get("dock_edge") == value:
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, v=value: self._on_edge(v) if checked else None)
            self._edge_group.addButton(rb)
            edge_row.addWidget(rb)
        layout.addLayout(edge_row)

        # Auto-start
        layout.addWidget(self._section_label("Startup"))
        self._autostart_cb = QCheckBox("Launch on Windows startup")
        self._autostart_cb.setStyleSheet("color: white;")
        self._autostart_cb.setChecked(self._config.get("auto_start", True))
        self._autostart_cb.toggled.connect(self._on_autostart)
        layout.addWidget(self._autostart_cb)

        layout.addStretch()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.setStyleSheet(
            "QPushButton {{ background-color: {0}; color: white; border: none; "
            "border-radius: 4px; padding: 6px; }}"
            "QPushButton:hover {{ background-color: #2980b9; }}".format(ACCENT_COLOR)
        )
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: white; font-weight: bold; font-size: 13px;")
        return lbl

    def _on_theme(self, value):
        self._config["theme"] = value
        self.settings_changed.emit(self._config)

    def _on_opacity(self, value):
        self._config["opacity"] = round(value / 100.0, 2)
        self._opacity_label.setText("{:.0f}%".format(value))
        self.settings_changed.emit(self._config)

    def _on_edge(self, value):
        self._config["dock_edge"] = value
        self.settings_changed.emit(self._config)

    def _on_autostart(self, checked):
        self._config["auto_start"] = checked
        if checked:
            startup.enable_auto_start()
        else:
            startup.disable_auto_start()
        self.settings_changed.emit(self._config)
