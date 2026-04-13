"""Entry point for DockedLauncher (PyQt5)."""
import argparse
import sys
import os

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from .config import load_config, save_config
from .constants import EDGES
from .startup import enable_auto_start, is_auto_start_enabled


def main():
    # Enable high-DPI scaling BEFORE creating QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    parser = argparse.ArgumentParser(description="DockedLauncher - Dockable application launcher")
    parser.add_argument("--edge", choices=EDGES, default=None)
    parser.add_argument("--monitor", type=int, default=None)
    args = parser.parse_args()

    config = load_config()
    if args.edge:
        config["dock_edge"] = args.edge
    if args.monitor is not None:
        config["monitor"] = args.monitor

    if config.get("auto_start", True) and not is_auto_start_enabled():
        enable_auto_start()

    save_config(config)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep running when settings dialog closes

    from .main_window import DockedLauncher
    launcher = DockedLauncher(config=config)
    launcher.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
