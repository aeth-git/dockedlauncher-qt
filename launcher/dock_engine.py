"""Edge detection and docking logic using Qt screen APIs."""
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QPoint, QRect, QSize

from .constants import (
    LEFT, RIGHT, TOP, BOTTOM,
    TAB_W, TAB_H, PANEL_WIDTH,
    HEADER_HEIGHT, BOTTOM_BAR_HEIGHT, SHORTCUT_ITEM_HEIGHT,
    MIN_PANEL_LENGTH, MAX_PANEL_RATIO,
)


def get_screens():
    """Return list of (index, available_geometry QRect) for all screens."""
    return [(i, s.availableGeometry()) for i, s in enumerate(QApplication.screens())]


def find_nearest_edge(center, screens=None):
    """Find the nearest screen edge for a given center point.

    Returns (edge, screen_index, offset).
    offset is 0.0-1.0 position along the edge.
    """
    if screens is None:
        screens = get_screens()

    best_edge = LEFT
    best_screen = 0
    best_dist = float("inf")

    cx, cy = center.x(), center.y()

    for idx, rect in screens:
        distances = {
            LEFT: abs(cx - rect.left()),
            RIGHT: abs(cx - rect.right()),
            TOP: abs(cy - rect.top()),
            BOTTOM: abs(cy - rect.bottom()),
        }
        for edge, dist in distances.items():
            if dist < best_dist:
                best_dist = dist
                best_edge = edge
                best_screen = idx

    # Calculate offset along the edge
    _, rect = screens[best_screen]
    if best_edge in (LEFT, RIGHT):
        offset = (cy - rect.top()) / max(1, rect.height())
    else:
        offset = (cx - rect.left()) / max(1, rect.width())
    offset = max(0.0, min(1.0, offset))

    return best_edge, best_screen, offset


def calc_panel_length(num_shortcuts):
    """Content-driven panel length."""
    return HEADER_HEIGHT + (num_shortcuts * SHORTCUT_ITEM_HEIGHT) + BOTTOM_BAR_HEIGHT + 12


def get_panel_size(edge, num_shortcuts, screen_rect):
    """Return QSize for the panel. Always vertical layout (PANEL_WIDTH wide, height grows)."""
    content = calc_panel_length(num_shortcuts)
    max_h = int(screen_rect.height() * MAX_PANEL_RATIO)
    h = max(MIN_PANEL_LENGTH, min(content, max_h))
    return QSize(PANEL_WIDTH, h)


def get_tab_rect(edge, offset, screen_rect):
    """Return QRect for the tab at the given edge and offset."""
    if edge in (LEFT, RIGHT):
        tw, th = TAB_W, TAB_H
    else:
        tw, th = TAB_H, TAB_W

    if edge == LEFT:
        x = screen_rect.left()
        y = int(screen_rect.top() + offset * screen_rect.height() - th / 2)
        y = max(screen_rect.top(), min(y, screen_rect.bottom() - th))
    elif edge == RIGHT:
        x = screen_rect.right() - tw + 1
        y = int(screen_rect.top() + offset * screen_rect.height() - th / 2)
        y = max(screen_rect.top(), min(y, screen_rect.bottom() - th))
    elif edge == TOP:
        x = int(screen_rect.left() + offset * screen_rect.width() - tw / 2)
        x = max(screen_rect.left(), min(x, screen_rect.right() - tw))
        y = screen_rect.top()
    elif edge == BOTTOM:
        x = int(screen_rect.left() + offset * screen_rect.width() - tw / 2)
        x = max(screen_rect.left(), min(x, screen_rect.right() - tw))
        y = screen_rect.bottom() - th + 1
    else:
        x, y = screen_rect.left(), screen_rect.top()

    return QRect(x, y, tw, th)


def get_panel_rect(edge, offset, num_shortcuts, screen_rect):
    """Return QRect for the expanded panel, anchored to where the tab would be."""
    size = get_panel_size(edge, num_shortcuts, screen_rect)
    pw, ph = size.width(), size.height()
    tab = get_tab_rect(edge, offset, screen_rect)

    if edge == LEFT:
        x = screen_rect.left()
        y = tab.center().y() - ph // 2
    elif edge == RIGHT:
        x = screen_rect.right() - pw + 1
        y = tab.center().y() - ph // 2
    elif edge == TOP:
        x = tab.center().x() - pw // 2
        y = screen_rect.top()
    elif edge == BOTTOM:
        x = tab.center().x() - pw // 2
        y = screen_rect.bottom() - ph + 1
    else:
        x, y = screen_rect.left(), screen_rect.top()

    # Clamp to screen
    x = max(screen_rect.left(), min(x, screen_rect.right() - pw + 1))
    y = max(screen_rect.top(), min(y, screen_rect.bottom() - ph + 1))

    return QRect(x, y, pw, ph)
