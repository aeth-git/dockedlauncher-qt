"""Unit tests for launcher.icon_provider cache + pure helpers.

Tests focus on Qt-level logic that runs cross-platform under the offscreen
platform plugin. The Win32-only jumbo extraction path (SHGetImageList) is
not exercised here; it's covered implicitly on real Windows sessions.
"""
import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QPainter, QColor

from launcher import icon_provider as ip


@pytest.fixture(autouse=True)
def _clean_cache():
    ip.clear_cache()
    yield
    ip.clear_cache()


# ---- _default_pixmap ----

def test_default_pixmap_has_requested_size(qapp):
    pm = ip._default_pixmap(256)
    assert isinstance(pm, QPixmap)
    assert pm.width() == 256
    assert pm.height() == 256


def test_default_pixmap_is_not_null_nor_blank(qapp):
    pm = ip._default_pixmap(256)
    assert not pm.isNull()
    assert ip._is_blank_pixmap(pm) is False  # has body + diagonal stroke


def test_default_pixmap_scales_to_small_size(qapp):
    pm = ip._default_pixmap(32)
    assert pm.width() == 32 and pm.height() == 32
    assert not pm.isNull()


# ---- _is_blank_pixmap ----

def test_null_pixmap_is_blank(qapp):
    assert ip._is_blank_pixmap(QPixmap()) is True


def test_solid_color_pixmap_is_blank(qapp):
    pm = QPixmap(64, 64)
    pm.fill(Qt.white)
    assert ip._is_blank_pixmap(pm) is True


def test_two_color_pixmap_is_still_blank(qapp):
    """Helper returns True until it sees >2 distinct colors — a transparent
    + single-color pixmap is still considered blank."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.fillRect(0, 0, 32, 32, QColor("red"))
    p.end()
    # 2 colors (transparent + red) → still blank
    assert ip._is_blank_pixmap(pm) is True


def test_multicolor_pixmap_is_not_blank(qapp):
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.fillRect(0, 0, 20, 64, QColor("red"))
    p.fillRect(20, 0, 20, 64, QColor("green"))
    p.fillRect(40, 0, 24, 64, QColor("blue"))
    p.end()
    assert ip._is_blank_pixmap(pm) is False


# ---- get_pixmap: cache behavior ----

def test_missing_file_returns_default_pixmap(qapp, tmp_path):
    missing = str(tmp_path / "does_not_exist.exe")
    pm = ip.get_pixmap(missing)
    assert not pm.isNull()
    assert pm.width() == 256  # default pixmap size


def test_get_pixmap_caches_by_path(qapp, tmp_path):
    missing = str(tmp_path / "ghost.exe")
    pm1 = ip.get_pixmap(missing)
    pm2 = ip.get_pixmap(missing)
    # Same cached QPixmap instance returned
    assert pm1 is pm2


def test_cache_is_case_insensitive_on_path(qapp, tmp_path):
    """Windows paths are case-insensitive; the cache should normalize."""
    p1 = str(tmp_path / "Ghost.exe")
    p2 = str(tmp_path / "GHOST.exe")
    pm1 = ip.get_pixmap(p1)
    pm2 = ip.get_pixmap(p2)
    assert pm1 is pm2


def test_cache_eviction_at_max_size(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(ip, "_MAX_CACHE", 3)
    paths = [str(tmp_path / f"f{i}.exe") for i in range(5)]
    for p in paths:
        ip.get_pixmap(p)
    assert len(ip._pixmap_cache) == 3
    # Earliest inserts evicted, latest retained
    import os
    keys = list(ip._pixmap_cache.keys())
    assert os.path.normcase(paths[-1]) in keys
    assert os.path.normcase(paths[0]) not in keys


def test_lru_access_moves_entry_to_end(qapp, tmp_path, monkeypatch):
    """Accessing an existing key should refresh its recency."""
    import os
    monkeypatch.setattr(ip, "_MAX_CACHE", 3)
    a = str(tmp_path / "a.exe")
    b = str(tmp_path / "b.exe")
    c = str(tmp_path / "c.exe")
    d = str(tmp_path / "d.exe")
    ip.get_pixmap(a)
    ip.get_pixmap(b)
    ip.get_pixmap(c)
    ip.get_pixmap(a)  # refresh 'a'
    ip.get_pixmap(d)  # triggers eviction — should evict 'b', not 'a'
    keys = list(ip._pixmap_cache.keys())
    assert os.path.normcase(a) in keys
    assert os.path.normcase(b) not in keys


# ---- clear_cache ----

def test_clear_cache_empties_store(qapp, tmp_path):
    ip.get_pixmap(str(tmp_path / "x.exe"))
    ip.get_pixmap(str(tmp_path / "y.exe"))
    assert len(ip._pixmap_cache) == 2
    ip.clear_cache()
    assert len(ip._pixmap_cache) == 0


# ---- get_icon wraps get_pixmap ----

def test_get_icon_returns_qicon_from_pixmap(qapp, tmp_path):
    from PyQt5.QtGui import QIcon
    icon = ip.get_icon(str(tmp_path / "missing.exe"))
    assert isinstance(icon, QIcon)
    assert not icon.isNull()
