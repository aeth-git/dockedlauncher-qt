"""Application entry point — QApplication bootstrap."""
import sys


def main():
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt

    # HiDPI — must be set BEFORE QApplication is created
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    app.setApplicationName("iForensic")
    app.setOrganizationName("iForensic")
    app.setQuitOnLastWindowClosed(True)

    # Baseline font
    from PyQt5.QtGui import QFont
    from .constants import FONT_FAMILY, FONT_SIZE_DATA
    font = QFont(FONT_FAMILY.split(",")[0].strip(), FONT_SIZE_DATA)
    app.setFont(font)

    from .logger import setup_logging
    setup_logging()

    from .main_window import ForensicWindow
    win = ForensicWindow()
    win.show()

    sys.exit(app.exec_())
