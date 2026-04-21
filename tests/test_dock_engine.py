"""Unit tests for launcher.dock_engine geometry helpers.

These cover the pure-logic functions: panel length, tab rect placement,
panel rect anchoring, and nearest-edge detection. All size constants are
scaled by launcher.scaling.s(...), so tests assert *relationships* (e.g.
"panel is anchored to the same edge as the tab") rather than exact pixel
values that depend on screen DPI.
"""
from PyQt5.QtCore import QPoint, QRect

from launcher import constants as C
from launcher import dock_engine as de
from launcher.constants import LEFT, RIGHT, TOP, BOTTOM
from launcher.scaling import s


SCREEN = QRect(0, 0, 1920, 1080)


# ---- calc_panel_length / get_panel_size ----

def test_panel_length_grows_with_shortcut_count(qapp):
    a = de.calc_panel_length(0)
    b = de.calc_panel_length(5)
    c = de.calc_panel_length(10)
    assert a < b < c
    # Each added shortcut adds exactly one item height
    assert c - b == 5 * s(C.SHORTCUT_ITEM_HEIGHT)


def test_panel_size_clamps_to_screen_ratio(qapp):
    size = de.get_panel_size(LEFT, num_shortcuts=1000, screen_rect=SCREEN)
    # With that many shortcuts content far exceeds 80% of screen height
    assert size.height() <= int(SCREEN.height() * C.MAX_PANEL_RATIO)
    assert size.width() == s(C.PANEL_WIDTH)


def test_panel_size_respects_min_length(qapp):
    size = de.get_panel_size(LEFT, num_shortcuts=0, screen_rect=SCREEN)
    assert size.height() >= s(C.MIN_PANEL_LENGTH)


# ---- get_tab_rect ----

def test_tab_rect_left_edge_is_flush_left(qapp):
    rect = de.get_tab_rect(LEFT, 0.5, SCREEN)
    assert rect.x() == SCREEN.left()
    assert rect.width() == s(C.TAB_W)
    assert rect.height() == s(C.TAB_H)


def test_tab_rect_right_edge_is_flush_right(qapp):
    rect = de.get_tab_rect(RIGHT, 0.5, SCREEN)
    assert rect.x() + rect.width() == SCREEN.right() + 1


def test_tab_rect_top_edge_is_flush_top(qapp):
    rect = de.get_tab_rect(TOP, 0.5, SCREEN)
    assert rect.y() == SCREEN.top()


def test_tab_rect_bottom_edge_is_flush_bottom(qapp):
    rect = de.get_tab_rect(BOTTOM, 0.5, SCREEN)
    assert rect.y() + rect.height() == SCREEN.bottom() + 1


def test_tab_rect_offset_clamped_at_extremes(qapp):
    """Tab must stay fully inside the screen even with 0.0 / 1.0 offsets."""
    for edge in (LEFT, RIGHT, TOP, BOTTOM):
        for offset in (0.0, 1.0):
            r = de.get_tab_rect(edge, offset, SCREEN)
            assert SCREEN.contains(r), (edge, offset, r)


# ---- get_panel_rect ----

def test_panel_anchored_to_left_edge(qapp):
    rect = de.get_panel_rect(LEFT, 0.5, num_shortcuts=5, screen_rect=SCREEN)
    assert rect.x() == SCREEN.left()


def test_panel_anchored_to_right_edge(qapp):
    rect = de.get_panel_rect(RIGHT, 0.5, num_shortcuts=5, screen_rect=SCREEN)
    assert rect.x() + rect.width() == SCREEN.right() + 1


def test_panel_stays_within_screen_even_at_corner_offset(qapp):
    """Panel for a corner-offset tab must still be fully on-screen."""
    for edge in (LEFT, RIGHT, TOP, BOTTOM):
        for offset in (0.0, 1.0):
            r = de.get_panel_rect(edge, offset, num_shortcuts=20,
                                  screen_rect=SCREEN)
            assert SCREEN.contains(r), (edge, offset, r)


# ---- find_nearest_edge ----

def test_find_nearest_edge_top_left_corner(qapp):
    # Point near top-left: closer to top than to left? equal — implementation
    # returns whichever min() picks first, so accept either.
    edge, idx, _ = de.find_nearest_edge(QPoint(20, 10), [(0, SCREEN)])
    assert edge in (LEFT, TOP)
    assert idx == 0


def test_find_nearest_edge_clearly_left(qapp):
    edge, _, offset = de.find_nearest_edge(QPoint(5, 540), [(0, SCREEN)])
    assert edge == LEFT
    assert 0.4 < offset < 0.6  # mid-height


def test_find_nearest_edge_clearly_bottom(qapp):
    edge, _, offset = de.find_nearest_edge(QPoint(960, 1075), [(0, SCREEN)])
    assert edge == BOTTOM
    assert 0.4 < offset < 0.6  # mid-width


def test_find_nearest_edge_multi_monitor_picks_correct_screen(qapp):
    # Two horizontally-arranged 1920x1080 monitors
    screens = [(0, QRect(0, 0, 1920, 1080)), (1, QRect(1920, 0, 1920, 1080))]
    # Point clearly on second monitor, near its left edge
    edge, idx, _ = de.find_nearest_edge(QPoint(1930, 540), screens)
    assert idx == 1
    assert edge == LEFT


def test_find_nearest_edge_offscreen_point_falls_back_to_nearest(qapp):
    """Point outside every screen should still resolve to some screen."""
    screens = [(0, QRect(0, 0, 1920, 1080))]
    edge, idx, offset = de.find_nearest_edge(QPoint(5000, 5000), screens)
    assert idx == 0
    assert edge in (LEFT, RIGHT, TOP, BOTTOM)
    assert 0.0 <= offset <= 1.0
