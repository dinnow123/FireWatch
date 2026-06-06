"""Per-building floorplan generator.

Produces a 2D cell-type map (rows, cols) for each building. The same map is
used across all floors of the building (a modeling simplification).

Cell types:
    OUTSIDE   = 0   not part of the building (surrounding empty space)
    ROOM      = 1   interior, can ignite and spread fire
    WALL      = 2   structural wall (concrete/steel) — survives even a fully
                    engulfed building; probability is capped low
    WALL_WEAK = 3   non-structural partition (drywall, glass) — burns through
"""
from __future__ import annotations

import numpy as np

OUTSIDE   = 0
ROOM      = 1
WALL      = 2
WALL_WEAK = 3


# How fire treats each cell type. Used by the simulator and by widgets.
SPREAD_COST: dict[int, float] = {
    ROOM:      1.0,
    WALL_WEAK: 2.0,
    WALL:      4.0,
    # OUTSIDE is impassable (handled separately)
}

# Maximum probability a cell of this type can reach, regardless of fire intensity.
PROB_CAP: dict[int, float] = {
    ROOM:      1.00,
    WALL_WEAK: 0.95,
    WALL:      0.40,
    OUTSIDE:   0.00,
}


# --- helpers ----------------------------------------------------------------

def _outline(g: np.ndarray, x: int, y: int, w: int, h: int) -> None:
    g[y:y + h, x:x + w] = ROOM
    g[y, x:x + w] = WALL
    g[y + h - 1, x:x + w] = WALL
    g[y:y + h, x] = WALL
    g[y:y + h, x + w - 1] = WALL


def _door(g: np.ndarray, x: int, y: int, axis: str = "h", width: int = 2) -> None:
    """Open `width` cells centered at (x, y); axis='h' opens horizontally, 'v' vertically."""
    if axis == "h":
        for d in range(width):
            if 0 <= x + d < g.shape[1]:
                g[y, x + d] = ROOM
    else:
        for d in range(width):
            if 0 <= y + d < g.shape[0]:
                g[y + d, x] = ROOM


# --- per-building layouts ---------------------------------------------------

def _office(cols: int = 30, rows: int = 30) -> np.ndarray:
    """30×30 office: central horizontal corridor, 4 rooms north and 4 south."""
    g = np.zeros((rows, cols), dtype=np.int8)
    bx, by, bw, bh = 3, 3, 24, 24
    _outline(g, bx, by, bw, bh)

    cy = by + bh // 2
    g[cy - 1, bx + 1:bx + bw - 1] = WALL
    g[cy + 1, bx + 1:bx + bw - 1] = WALL

    for k in range(1, 4):
        wx = bx + (bw * k) // 4
        g[by + 1:cy - 1, wx] = WALL
        g[cy + 2:by + bh - 1, wx] = WALL

    for k in range(4):
        wx = bx + (bw * (2 * k + 1)) // 8
        _door(g, wx, cy - 1, "h", 1)
        _door(g, wx, cy + 1, "h", 1)

    _door(g, bx + bw // 2 - 1, by + bh - 1, "h", 2)
    return g


def _residential(cols: int = 25, rows: int = 35) -> np.ndarray:
    """25×35 mixed-use residential: vertical central corridor, 6 units per side."""
    g = np.zeros((rows, cols), dtype=np.int8)
    bx, by, bw, bh = 3, 2, 19, 31
    _outline(g, bx, by, bw, bh)

    cx = bx + bw // 2
    g[by + 1:by + bh - 1, cx - 1] = WALL
    g[by + 1:by + bh - 1, cx + 1] = WALL

    for k in range(1, 6):
        wy = by + (bh * k) // 6
        g[wy, bx + 1:cx - 1] = WALL
        g[wy, cx + 2:bx + bw - 1] = WALL

    for k in range(6):
        wy = by + (bh * (2 * k + 1)) // 12
        _door(g, cx - 1, wy, "h", 1)
        _door(g, cx + 1, wy, "h", 1)

    _door(g, bx, by + bh // 2 - 1, "v", 2)
    return g


def _academic(cols: int = 22, rows: int = 22) -> np.ndarray:
    """22×22 student-union: north classrooms, south lobby, side exits."""
    g = np.zeros((rows, cols), dtype=np.int8)
    bx, by, bw, bh = 3, 3, 16, 16
    _outline(g, bx, by, bw, bh)

    lobby_top = by + 6
    g[lobby_top, bx + 1:bx + bw - 1] = WALL

    for k in range(1, 4):
        wx = bx + (bw * k) // 4
        g[by + 1:lobby_top, wx] = WALL

    for k in range(4):
        wx = bx + (bw * (2 * k + 1)) // 8
        _door(g, wx, lobby_top, "h", 1)

    _door(g, bx + bw // 2 - 1, by + bh - 1, "h", 2)
    _door(g, bx, lobby_top + 3, "v", 2)
    _door(g, bx + bw - 1, lobby_top + 3, "v", 2)
    return g


def _warehouse(cols: int = 48, rows: int = 24) -> np.ndarray:
    """48×24 warehouse: large open floor with column grid + small office on west."""
    g = np.zeros((rows, cols), dtype=np.int8)
    bx, by, bw, bh = 4, 3, 40, 18
    _outline(g, bx, by, bw, bh)

    # Column grid (4 spans × 2 spans of single-cell pillars).
    for cx in range(bx + bw // 5, bx + bw - 1, bw // 5):
        for cy in range(by + bh // 3, by + bh - 1, bh // 3):
            g[cy, cx] = WALL

    # Office partition in the west corner — drywall, marked as WALL_WEAK so
    # it can burn through if the warehouse fire intensifies.
    ox, oy, ow, oh = bx + 1, by + 1, 8, 6
    g[oy + oh - 1, ox:ox + ow] = WALL_WEAK
    g[oy:oy + oh, ox + ow - 1] = WALL_WEAK
    _door(g, ox + ow - 1, oy + oh // 2, "h", 1)

    # Loading bay doors on south wall (4 evenly spaced).
    for k in range(4):
        dx = bx + (bw * (2 * k + 1)) // 8 - 1
        _door(g, dx, by + bh - 1, "h", 3)
    return g


# --- registry ---------------------------------------------------------------

_LAYOUTS: dict[str, np.ndarray] = {
    "BLDG001": _office(30, 30),
    "BLDG002": _residential(25, 35),
    "BLDG003": _academic(22, 22),
    "BLDG004": _warehouse(48, 24),
}


def get_layout(building_id: str) -> np.ndarray:
    """Return the cell-type map for a building. Falls back to an open square."""
    if building_id in _LAYOUTS:
        return _LAYOUTS[building_id]
    raise KeyError(f"No floorplan generator registered for building {building_id!r}")
