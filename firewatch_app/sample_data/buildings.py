"""Sample building data for the app.

Equipment placement is kept *physically plausible* so the demo reads like a real
floor plan:

* Sprinklers are a ceiling grid — one per lattice point, evenly spread across the
  interior, repeated on every floor. The engine cools only the single installed
  cell (no radius), so coverage is "as many cells as you install"; the grid just
  makes that honest and even.
* Fire shutters are *lines*, not dots: a run of adjacent cells that seals a
  corridor / open span and splits the floor into fire zones. Wide halls
  (BLDG003/004) get a perpendicular crossing line; the 1-cell-wide corridors
  (BLDG001/002) get a segment laid *along* the corridor that closes the passage.
  Every shutter cell sits on a ROOM (passable) cell so closing it actually blocks
  spread. See ``_build_equipment`` for how the compact specs below expand.
"""
from __future__ import annotations

from dataclasses import dataclass

from firewatch_app.sample_data.floorplan_gen import ROOM, get_layout


@dataclass(frozen=True)
class Equipment:
    type: str   # "sprinkler" | "shutter" | "exit"
    floor: str
    x: int
    y: int


@dataclass(frozen=True)
class Building:
    id: str
    name: str
    address: str
    floors: tuple[str, ...]
    grid_size: tuple[int, int]   # (cols, rows)
    equipment: tuple[Equipment, ...]


def _build_equipment(
    floors: tuple[str, ...],
    sprinklers: tuple[tuple[int, int], ...],
    shutter_lines: tuple[tuple[tuple[int, int], ...], ...],
    exits_1f: tuple[tuple[int, int], ...] = (),
) -> tuple[Equipment, ...]:
    """Expand compact per-floor specs into a flat Equipment tuple.

    Sprinklers and every cell of every shutter line are placed on *all* floors
    (real buildings protect each storey alike); exits are ground-floor only.
    """
    shutter_cells = [cell for line in shutter_lines for cell in line]
    eq: list[Equipment] = []
    for f in floors:
        for x, y in sprinklers:
            eq.append(Equipment("sprinkler", f, x, y))
        for x, y in shutter_cells:
            eq.append(Equipment("shutter", f, x, y))
    for x, y in exits_1f:
        eq.append(Equipment("exit", "1F", x, y))
    return tuple(eq)


# --- equipment derived from the actual floorplan ----------------------------
# For the BLDG005+ demo buildings the layouts are irregular (circular stadium,
# tunnels, tanks), so hand-picking coordinates is error-prone. These helpers read
# the generated cell map and only ever place equipment on ROOM (passable) cells.

def _lattice_sprinklers(
    layout, step: int = 6, margin: int = 4
) -> tuple[tuple[int, int], ...]:
    """ROOM cells on a regular lattice → sprinkler points ``(x=col, y=row)``."""
    rows, cols = layout.shape
    pts: list[tuple[int, int]] = []
    for r in range(margin, rows - margin, step):
        for c in range(margin, cols - margin, step):
            if layout[r, c] == ROOM:
                pts.append((c, r))
    return tuple(pts)


def _line_shutter(
    layout, axis: str, fixed: int, lo: int, hi: int
) -> tuple[tuple[int, int], ...]:
    """ROOM cells along a row/col segment → one shutter line ``(x=col, y=row)``.

    ``axis='v'``: column ``fixed``, rows ``lo..hi``; ``axis='h'``: row ``fixed``,
    cols ``lo..hi``. Non-ROOM cells are dropped so the line lands only on passable
    cells — where a closed shutter actually blocks spread.
    """
    rows, cols = layout.shape
    if axis == "v":
        return tuple(
            (fixed, r)
            for r in range(lo, hi + 1)
            if 0 <= r < rows and 0 <= fixed < cols and layout[r, fixed] == ROOM
        )
    return tuple(
        (c, fixed)
        for c in range(lo, hi + 1)
        if 0 <= fixed < rows and 0 <= c < cols and layout[fixed, c] == ROOM
    )


# --- BLDG001: 30×30 office, single horizontal corridor at row 15 ---------------
_FLOORS_001 = ("B1", "1F", "2F", "3F", "4F", "5F")
_SPRINK_001 = (
    (6, 6), (12, 6), (18, 6),
    (6, 13), (12, 13), (18, 13),
    (6, 20), (12, 20), (18, 20),
)
# Two segments laid along the corridor → west / center / east fire zones.
_SHUTTERS_001 = (
    ((8, 15), (9, 15), (10, 15), (11, 15)),
    ((18, 15), (19, 15), (20, 15), (21, 15)),
)

# --- BLDG002: 25×35 residential tower, vertical spine corridor at col 12 -------
_FLOORS_002 = ("B2", "B1", "1F", "2F", "3F", "4F", "5F", "6F", "7F")
_SPRINK_002 = (
    (5, 5), (12, 5), (17, 5),
    (5, 11), (17, 11),
    (5, 18), (12, 17), (17, 18),
    (5, 23), (17, 23),
    (5, 29), (12, 29), (17, 29),
)
# Two segments laid along the spine → upper / middle / lower fire zones.
_SHUTTERS_002 = (
    ((12, 7), (12, 8), (12, 9), (12, 10), (12, 11)),
    ((12, 22), (12, 23), (12, 24), (12, 25), (12, 26)),
)

# --- BLDG003: 22×22 student union, open lobby (rows 10–17) ---------------------
_FLOORS_003 = ("B1", "1F", "2F", "3F")
_SPRINK_003 = (
    (5, 6), (10, 6), (16, 6),
    (5, 11), (10, 11), (15, 11),
    (5, 16), (10, 16), (15, 16),
)
# Two vertical lines crossing the lobby hall → west / center / east fire zones.
_SHUTTERS_003 = (
    tuple((8, y) for y in range(10, 18)),
    tuple((14, y) for y in range(10, 18)),
)

# --- BLDG004: 48×24 warehouse, open floor ------------------------------------
_FLOORS_004 = ("1F", "2F")
_SPRINK_004 = (
    (7, 6), (15, 6), (23, 6), (31, 6), (39, 6),
    (7, 13), (15, 13), (23, 13), (31, 13), (39, 13),
)
# Two full-height crossing lines compartmentalize the open floor into 3 bays.
_SHUTTERS_004 = (
    tuple((16, y) for y in range(4, 20)),
    tuple((32, y) for y in range(4, 20)),
)


# --- BLDG005~009: 추가 데모 건물 — 평면도에서 설비 자동 도출 ------------------
_L005, _L006, _L007, _L008, _L009 = (
    get_layout("BLDG005"), get_layout("BLDG006"), get_layout("BLDG007"),
    get_layout("BLDG008"), get_layout("BLDG009"),
)

_FLOORS_005 = ("1F", "2F", "3F")
_FLOORS_006 = ("B1", "1F", "2F")            # B1 = 통과터널/승강장, 1F 콩코스
_FLOORS_007 = ("1F", "2F", "3F")
_FLOORS_008 = ("B1", "1F", "2F")
_FLOORS_009 = ("B3", "B2", "B1", "1F")

# 셔터선: 통로/홀을 가로지르는 직선을 ROOM 셀만 남겨 구획화.
_SHUTTERS_005 = (_line_shutter(_L005, "v", 20, 9, 32), _line_shutter(_L005, "h", 20, 9, 32))
_SHUTTERS_006 = (
    _line_shutter(_L006, "v", 13, 3, 17),
    _line_shutter(_L006, "v", 42, 3, 17),
    _line_shutter(_L006, "h", 19, 5, 50),   # 통과터널 가로 차단
)
_SHUTTERS_007 = (_line_shutter(_L007, "v", 17, 8, 14), _line_shutter(_L007, "v", 33, 8, 14))
_SHUTTERS_008 = (_line_shutter(_L008, "v", 16, 4, 27), _line_shutter(_L008, "h", 16, 4, 27))
_SHUTTERS_009 = (_line_shutter(_L009, "v", 12, 3, 22), _line_shutter(_L009, "v", 25, 3, 22))


BUILDINGS: tuple[Building, ...] = (
    Building(
        id="BLDG001",
        name="경산역 인근 사무용 건물",
        address="대구 경산시 대학로 123",
        floors=_FLOORS_001,
        grid_size=(30, 30),
        equipment=_build_equipment(
            _FLOORS_001, _SPRINK_001, _SHUTTERS_001, exits_1f=((0, 14), (29, 14))
        ),
    ),
    Building(
        id="BLDG002",
        name="중앙로 주거복합 빌딩",
        address="대구 경산시 중앙로 45",
        floors=_FLOORS_002,
        grid_size=(25, 35),
        equipment=_build_equipment(
            _FLOORS_002, _SPRINK_002, _SHUTTERS_002, exits_1f=((0, 17),)
        ),
    ),
    Building(
        id="BLDG003",
        name="영남대학교 제2학생회관",
        address="대구 경산시 대학로 280",
        floors=_FLOORS_003,
        grid_size=(22, 22),
        equipment=_build_equipment(
            _FLOORS_003, _SPRINK_003, _SHUTTERS_003, exits_1f=((0, 3), (0, 18), (21, 10))
        ),
    ),
    Building(
        id="BLDG004",
        name="남촌 물류센터 A동",
        address="대구 경산시 산업로 200",
        floors=_FLOORS_004,
        grid_size=(48, 24),
        equipment=_build_equipment(
            _FLOORS_004, _SPRINK_004, _SHUTTERS_004, exits_1f=((0, 12), (47, 12))
        ),
    ),
    Building(
        id="BLDG005",
        name="경산 시민 원형 스타디움",
        address="대구 경산시 체육공원로 50",
        floors=_FLOORS_005,
        grid_size=(42, 42),
        equipment=_build_equipment(_FLOORS_005, _lattice_sprinklers(_L005), _SHUTTERS_005),
    ),
    Building(
        id="BLDG006",
        name="경산역 환승센터 (지하철 통과역)",
        address="대구 경산시 역전로 1",
        floors=_FLOORS_006,
        grid_size=(56, 24),
        equipment=_build_equipment(_FLOORS_006, _lattice_sprinklers(_L006), _SHUTTERS_006),
    ),
    Building(
        id="BLDG007",
        name="경산 국제터미널 제2청사",
        address="대구 경산시 공항대로 300",
        floors=_FLOORS_007,
        grid_size=(50, 22),
        equipment=_build_equipment(_FLOORS_007, _lattice_sprinklers(_L007), _SHUTTERS_007),
    ),
    Building(
        id="BLDG008",
        name="경산 아쿠아리움",
        address="대구 경산시 호수로 77",
        floors=_FLOORS_008,
        grid_size=(32, 32),
        equipment=_build_equipment(_FLOORS_008, _lattice_sprinklers(_L008), _SHUTTERS_008),
    ),
    Building(
        id="BLDG009",
        name="중산 지하주차타워",
        address="대구 경산시 중산로 21",
        floors=_FLOORS_009,
        grid_size=(38, 26),
        equipment=_build_equipment(_FLOORS_009, _lattice_sprinklers(_L009), _SHUTTERS_009),
    ),
)


def find_building(query: str) -> Building | None:
    """Match a building by substring on address, id, or name."""
    needle = query.strip().lower()
    if not needle:
        return None
    for b in BUILDINGS:
        if (
            needle in b.address.lower()
            or needle == b.id.lower()
            or needle in b.name.lower()
        ):
            return b
    return None
