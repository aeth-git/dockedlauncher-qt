"""Shared pytest fixtures.

dock_engine calls into launcher.scaling.s(...) which needs a running
QApplication (it asks the primary screen for its height). We create a
single offscreen QApplication for the whole test session so tests can
run headless (no real display).
"""
import os
import sys

import pytest

# Qt needs a platform plugin; "offscreen" runs without any display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
