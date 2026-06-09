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


def _stadium(cols: int = 42, rows: int = 42) -> np.ndarray:
    """42×42 circular stadium: central field, ringed stands split into sectors."""
    g = np.zeros((rows, cols), dtype=np.int8)
    cy, cx = (rows - 1) / 2.0, (cols - 1) / 2.0
    yy, xx = np.ogrid[:rows, :cols]
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    r_out, r_field = 20.0, 8.0

    g[dist <= r_out] = ROOM                                   # whole interior disk
    # Radial walls split the stands into 8 sectors.
    for k in range(8):
        ang = np.pi * k / 4.0
        rs = np.arange(int(r_field) + 2, int(r_out) - 1)
        rys = np.round(cy + rs * np.sin(ang)).astype(int)
        rxs = np.round(cx + rs * np.cos(ang)).astype(int)
        ok = (rys >= 0) & (rys < rows) & (rxs >= 0) & (rxs < cols)
        g[rys[ok], rxs[ok]] = WALL
    # A 2-cell concourse ring near the outer edge reconnects every sector.
    g[(dist > r_out - 3) & (dist <= r_out - 1)] = ROOM
    # Field perimeter wall with four cardinal gates onto the field.
    g[(dist > r_field) & (dist <= r_field + 1)] = WALL
    g[dist <= r_field] = ROOM
    for ang in (0.0, np.pi / 2, np.pi, 3 * np.pi / 2):
        for rr in (r_field, r_field + 1):
            ry = int(round(cy + rr * np.sin(ang)))
            rx = int(round(cx + rr * np.cos(ang)))
            g[ry, rx] = ROOM
    # Outer structural wall ring, OUTSIDE beyond it.
    g[(dist > r_out - 1) & (dist <= r_out)] = WALL
    g[dist > r_out] = OUTSIDE
    return g


def _station(cols: int = 56, rows: int = 24) -> np.ndarray:
    """56×24 train station: upper concourse over a full-width subway tunnel.

    The subway runs straight through the bottom tunnel without stopping; the
    platform stairs are the only openings between concourse and track level.
    """
    g = np.zeros((rows, cols), dtype=np.int8)
    bx, by, bw, bh = 2, 2, 52, 20
    _outline(g, bx, by, bw, bh)

    # Through tunnel: a 3-cell-tall open run along the bottom, walled off from the
    # concourse except at the platform stairs.
    ty = by + bh - 4
    g[ty, bx + 1:bx + bw - 1] = WALL
    for k in range(5):
        sx = bx + (bw * (2 * k + 1)) // 10
        _door(g, sx, ty, "h", 2)

    # Concourse waiting halls split by vertical partitions with mid doors.
    for k in range(1, 5):
        wx = bx + (bw * k) // 5
        g[by + 1:ty - 1, wx] = WALL
        _door(g, wx, by + (ty - by) // 2, "v", 2)
    return g


def _airport(cols: int = 50, rows: int = 22) -> np.ndarray:
    """50×22 airport terminal: north check-in counters, south gates, open hall."""
    g = np.zeros((rows, cols), dtype=np.int8)
    bx, by, bw, bh = 2, 2, 46, 18
    _outline(g, bx, by, bw, bh)

    ny = by + 4                       # check-in counter line (north)
    sy = by + bh - 5                  # gate line (south)
    g[ny, bx + 1:bx + bw - 1] = WALL
    g[sy, bx + 1:bx + bw - 1] = WALL
    for k in range(1, 8):
        wx = bx + (bw * k) // 8
        g[by + 1:ny, wx] = WALL       # check-in booth dividers
        g[sy + 1:by + bh - 1, wx] = WALL  # gate-room dividers
    for k in range(8):
        dx = bx + (bw * (2 * k + 1)) // 16
        _door(g, dx, ny, "h", 1)
        _door(g, dx, sy, "h", 1)
    return g


def _aquarium(cols: int = 32, rows: int = 32) -> np.ndarray:
    """32×32 aquarium: solid central tank, ring walkway, perimeter exhibit rooms."""
    g = np.zeros((rows, cols), dtype=np.int8)
    bx, by, bw, bh = 2, 2, 28, 28
    _outline(g, bx, by, bw, bh)

    # Solid central tank (impassable block).
    tx, ty, tw, th = bx + 10, by + 10, 8, 8
    g[ty:ty + th, tx:tx + tw] = WALL

    # Perimeter exhibit rooms: an inner wall rectangle two cells off the facade,
    # with doors, leaving a ring walkway between it and the tank.
    rx, ry = bx + 4, by + 4
    rw, rh = bw - 8, bh - 8
    g[ry, rx:rx + rw] = WALL
    g[ry + rh - 1, rx:rx + rw] = WALL
    g[ry:ry + rh, rx] = WALL
    g[ry:ry + rh, rx + rw - 1] = WALL
    for d in (0.25, 0.5, 0.75):
        _door(g, rx + int(rw * d), ry, "h", 2)
        _door(g, rx + int(rw * d), ry + rh - 1, "h", 2)
        _door(g, rx, ry + int(rh * d), "v", 2)
        _door(g, rx + rw - 1, ry + int(rh * d), "v", 2)
    return g


def _garage(cols: int = 38, rows: int = 26) -> np.ndarray:
    """38×26 underground parking: open deck on a dense pillar grid, central ramp."""
    g = np.zeros((rows, cols), dtype=np.int8)
    bx, by, bw, bh = 2, 2, 34, 22
    _outline(g, bx, by, bw, bh)

    # Pillar grid (single-cell structural columns).
    for cyy in range(by + 3, by + bh - 2, 4):
        for cxx in range(bx + 3, bx + bw - 2, 4):
            g[cyy, cxx] = WALL

    # Central ramp core (drywall enclosure that can burn through).
    rx, ry, rw, rh = bx + bw // 2 - 2, by + bh // 2 - 3, 4, 6
    g[ry, rx:rx + rw] = WALL_WEAK
    g[ry + rh - 1, rx:rx + rw] = WALL_WEAK
    g[ry:ry + rh, rx] = WALL_WEAK
    g[ry:ry + rh, rx + rw - 1] = WALL_WEAK
    _door(g, rx + rw - 1, ry + rh // 2, "h", 1)

    _door(g, bx + bw // 2 - 1, by + bh - 1, "h", 3)   # vehicle entrance (south)
    return g


# --- registry ---------------------------------------------------------------

_LAYOUTS: dict[str, np.ndarray] = {
    "BLDG001": _office(30, 30),
    "BLDG002": _residential(25, 35),
    "BLDG003": _academic(22, 22),
    "BLDG004": _warehouse(48, 24),
    "BLDG005": _stadium(42, 42),
    "BLDG006": _station(56, 24),
    "BLDG007": _airport(50, 22),
    "BLDG008": _aquarium(32, 32),
    "BLDG009": _garage(38, 26),
}


def get_layout(building_id: str) -> np.ndarray:
    """Return the cell-type map for a building. Falls back to an open square."""
    if building_id in _LAYOUTS:
        return _LAYOUTS[building_id]
    raise KeyError(f"No floorplan generator registered for building {building_id!r}")
