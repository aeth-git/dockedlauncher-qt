"""Edge detection and docking logic using Qt screen APIs."""
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QPoint, QRect, QSize

from . import constants as C
from .constants import LEFT, RIGHT, TOP, BOTTOM
from .scaling import s
from .logger import get_logger

_log = get_logger("dock_engine")


def TAB_W():
    return s(C.TAB_W)


def TAB_H():
    return s(C.TAB_H)


def PANEL_WIDTH():
    return s(C.PANEL_WIDTH)


def _min_panel_length():
    return s(C.MIN_PANEL_LENGTH)


def get_screens():
    """Return list of (index, available_geometry QRect) for all screens."""
    screens = [(i, s.availableGeometry()) for i, s in enumerate(QApplication.screens())]
    if not screens:
        _log.warning("No screens detected, using fallback 1920x1080")
        screens = [(0, QRect(0, 0, 1920, 1080))]
    return screens


def _find_containing_screen(center, screens):
    """Find which screen contains the center point. Falls back to nearest screen."""
    cx, cy = center.x(), center.y()

    # First: exact containment check
    for idx, rect in screens:
        if rect.contains(center):
            return idx, rect

    # Fallback: nearest screen center
    best_idx = 0
    best_dist = float("inf")
    for idx, rect in screens:
        dx = cx - rect.center().x()
        dy = cy - rect.center().y()
        dist = dx * dx + dy * dy
        if dist < best_dist:
            best_dist = dist
            best_idx = idx

    return best_idx, screens[best_idx][1]


def find_nearest_edge(center, screens=None):
    """Find nearest edge of the CURRENT screen only. Returns (edge, screen_index, offset 0.0-1.0)."""
    if screens is None:
        screens = get_screens()

    cx, cy = center.x(), center.y()

    # Step 1: determine which screen the window is on
    screen_idx, rect = _find_containing_screen(center, screens)

    # Step 2: find nearest edge of THAT screen only
    distances = {
        LEFT: abs(cx - rect.left()),
        RIGHT: abs(cx - rect.right()),
        TOP: abs(cy - rect.top()),
        BOTTOM: abs(cy - rect.bottom()),
    }
    best_edge = min(distances, key=distances.get)

    # Step 3: calculate offset along the edge
    if best_edge in (LEFT, RIGHT):
        offset = (cy - rect.top()) / max(1, rect.height())
    else:
        offset = (cx - rect.left()) / max(1, rect.width())
    offset = max(0.0, min(1.0, offset))

    return best_edge, screen_idx, offset


def calc_panel_length(num_shortcuts):
    return s(C.HEADER_HEIGHT) + (num_shortcuts * s(C.SHORTCUT_ITEM_HEIGHT)) + s(C.BOTTOM_BAR_HEIGHT) + s(12)


def get_panel_size(edge, num_shortcuts, screen_rect):
    """Always vertical layout (PANEL_WIDTH wide, height grows with shortcuts)."""
    content = calc_panel_length(num_shortcuts)
    max_h = int(screen_rect.height() * C.MAX_PANEL_RATIO)
    h = max(_min_panel_length(), min(content, max_h))
    return QSize(PANEL_WIDTH(), h)


def get_tab_rect(edge, offset, screen_rect):
    """QRect for the tab at given edge and offset."""
    if edge in (LEFT, RIGHT):
        tw, th = TAB_W(), TAB_H()
    else:
        tw, th = TAB_H(), TAB_W()

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
    """QRect for expanded panel, anchored to tab position."""
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

    x = max(screen_rect.left(), min(x, screen_rect.right() - pw + 1))
    y = max(screen_rect.top(), min(y, screen_rect.bottom() - ph + 1))

    return QRect(x, y, pw, ph)
