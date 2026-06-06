"""Domain data structures for the FireWatch Engine Layer.

This module defines the pure data structures the Engine consumes as input:
cell-state / material enums, the per-material physical-property table, and the
building grid (Building -> Floor -> per-cell numpy arrays), plus the simulation
parameters and inter-floor connections.

Engine independence: nothing here depends on UI or storage. A Floor stores its
*static* per-cell data (material, sprinkler/shutter placement, walls) as numpy
arrays so the engine can run vectorized operations over the whole grid instead
of iterating cell objects. The *dynamic* simulation state (current cell state,
accumulated heat, burn timers) lives in CAEngine, not here.

Coordinate convention: every per-floor array has shape ``(nx, ny)`` and is
indexed ``arr[x, y]``. This matches the spec's ``fire_counts[floor][x][y]`` and
``get_probability(floor, x, y)`` ordering.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

import numpy as np


class CellState(enum.IntEnum):
    """Discrete cell state. Stored as small integers for numpy compatibility."""

    EMPTY = 0
    BURNING = 1
    BURNED = 2
    BLOCKED = 3


class Material(enum.IntEnum):
    """Cell material. WOOD is the default.

    The integer value doubles as the index into the property lookup arrays
    (``MULTIPLIER_BY_CODE`` etc.), so the engine can map a material array to a
    property array with a single fancy-index instead of a Python loop.
    """

    CONCRETE = 0
    GYPSUM = 1
    WOOD = 2
    TEXTILE = 3
    PLASTIC = 4
    PAPER = 5

    def get_multiplier(self) -> float:
        """Ignition-probability / heat-absorption multiplier of this material."""
        return float(MATERIAL_PROPS[self].multiplier)

    def get_threshold(self) -> float:
        """Heat threshold theta above which the cell becomes an ignition candidate."""
        return float(MATERIAL_PROPS[self].threshold)

    def get_burn_duration(self) -> int:
        """Number of ticks the cell stays BURNING before turning BURNED."""
        return int(MATERIAL_PROPS[self].burn_duration)


@dataclass(frozen=True)
class MaterialProps:
    """Physical properties of a material.

    These are deliberately *empirical placeholders*, not validated fire-science
    values. Only the relative ordering between materials is meant to be
    meaningful (e.g. PAPER ignites far more readily than CONCRETE); the absolute
    numbers are tunable in one place for later calibration.

    Attributes:
        multiplier: scales both heat absorbed per tick and ignition probability.
        threshold: accumulated-heat level required before ignition is possible.
        burn_duration: ticks spent BURNING before transitioning to BURNED.
    """

    multiplier: float
    threshold: float
    burn_duration: int


# --- Empirical material constant table (calibrate here, not in the engine) ----
# Design intent (spec 4): PAPER -> low threshold, high multiplier; CONCRETE ->
# effectively never ignites (multiplier 0, astronomically high threshold).
MATERIAL_PROPS: dict[Material, MaterialProps] = {
    Material.CONCRETE: MaterialProps(multiplier=0.0, threshold=1.0e6, burn_duration=9999),
    Material.GYPSUM: MaterialProps(multiplier=0.3, threshold=8.0, burn_duration=14),
    Material.WOOD: MaterialProps(multiplier=1.0, threshold=4.0, burn_duration=8),
    Material.TEXTILE: MaterialProps(multiplier=1.6, threshold=2.5, burn_duration=5),
    Material.PLASTIC: MaterialProps(multiplier=1.4, threshold=3.0, burn_duration=10),
    Material.PAPER: MaterialProps(multiplier=2.2, threshold=1.5, burn_duration=3),
}

# Vectorized lookup arrays indexed by Material integer code. The engine uses
# these to turn a per-cell material array into per-cell property arrays in one
# shot: ``MULTIPLIER_BY_CODE[material_array]``.
_ORDERED = [Material(code) for code in range(len(Material))]
MULTIPLIER_BY_CODE: np.ndarray = np.array(
    [MATERIAL_PROPS[m].multiplier for m in _ORDERED], dtype=np.float64
)
THRESHOLD_BY_CODE: np.ndarray = np.array(
    [MATERIAL_PROPS[m].threshold for m in _ORDERED], dtype=np.float64
)
BURN_DURATION_BY_CODE: np.ndarray = np.array(
    [MATERIAL_PROPS[m].burn_duration for m in _ORDERED], dtype=np.int64
)


class Floor:
    """A single building floor: a grid of cells held as static numpy arrays.

    Conceptually a 2D array of cells, but for performance the per-cell data is
    stored as separate numpy arrays of shape ``(nx, ny)``. Only static structure
    lives here; the engine derives its mutable working state from these arrays.
    """

    def __init__(
        self,
        floor_id: str,
        nx: int,
        ny: int,
        default_material: Material = Material.WOOD,
    ) -> None:
        """Create an ``nx`` by ``ny`` floor filled with ``default_material``.

        Args:
            floor_id: human-readable identifier such as ``"B1"`` or ``"1F"``.
            nx: grid size along x (first array axis).
            ny: grid size along y (second array axis).
            default_material: material every cell starts with.
        """
        self.floor_id = floor_id
        self.nx = nx
        self.ny = ny
        self.material: np.ndarray = np.full((nx, ny), int(default_material), dtype=np.int8)
        self.sprinkler: np.ndarray = np.zeros((nx, ny), dtype=bool)
        self.shutter: np.ndarray = np.zeros((nx, ny), dtype=bool)
        # Walls: cells that start BLOCKED and never transition.
        self.wall: np.ndarray = np.zeros((nx, ny), dtype=bool)

    def get_grid_size(self) -> tuple[int, int]:
        """Return the grid size as ``(nx, ny)``."""
        return (self.nx, self.ny)

    def set_material(self, x: int, y: int, material: Material) -> None:
        """Set the material of cell ``(x, y)``."""
        self.material[x, y] = int(material)

    def set_wall(self, x: int, y: int, value: bool = True) -> None:
        """Mark cell ``(x, y)`` as a wall (starts and stays BLOCKED)."""
        self.wall[x, y] = value

    def set_sprinkler(self, x: int, y: int, value: bool = True) -> None:
        """Place (or remove) a sprinkler at cell ``(x, y)``."""
        self.sprinkler[x, y] = value

    def set_shutter(self, x: int, y: int, value: bool = True) -> None:
        """Place (or remove) a fire shutter at cell ``(x, y)``."""
        self.shutter[x, y] = value


@dataclass
class ConnectionCell:
    """An inter-floor fire path (stairwell / elevator / duct).

    Heat transferred upward uses ``up_weight``; downward uses ``down_weight``.
    To model the chimney effect, callers set ``up_weight > down_weight``.
    """

    floor_a: int
    x_a: int
    y_a: int
    floor_b: int
    x_b: int
    y_b: int
    up_weight: float
    down_weight: float

    def transfer_heat(self, from_floor: int, heat: float) -> float:
        """Return the heat delivered across this connection.

        If ``from_floor`` is the *lower* of the two connected floors the heat is
        travelling upward (``up_weight``); otherwise it is travelling downward
        (``down_weight``).
        """
        lower = min(self.floor_a, self.floor_b)
        weight = self.up_weight if from_floor == lower else self.down_weight
        return heat * weight


@dataclass
class SimParameters:
    """Scenario parameters: which fire-safety equipment is active, and how strong.

    Defaults to all equipment active (spec UC3: unset means everything on).
    """

    sprinkler_active: bool = True
    shutter_active: bool = True
    sprinkler_cooling: float = 1.0
    shutter_trigger_heat: float = 5.0

    def is_sprinkler_active(self) -> bool:
        """Whether sprinklers are active in this scenario."""
        return self.sprinkler_active

    def is_shutter_active(self) -> bool:
        """Whether fire shutters are active in this scenario."""
        return self.shutter_active


@dataclass
class Scenario:
    """One ensemble run as a unit: its input parameters + the result it produced.

    A Scenario pairs the ``SimParameters`` that drove an ensemble run with the
    *reach-probability cube* that run produced. ``probability[floor, t, x, y]`` is
    the fraction of ensemble members in which cell ``(x, y)`` on ``floor`` had
    caught fire by snapshot ``t`` — a value in ``[0, 1]``. One Scenario is created
    per ensemble run; comparing two of them (spec UC10) is a per-cell subtraction.

    Pure domain data: bundling a cube and differencing two cubes needs only
    numpy, so this stays in the Domain layer with no engine-run or UI dependency.
    """

    parameters: SimParameters
    probability: np.ndarray  # reach probability in [0, 1]; typically (F, T, nx, ny)

    def compute_delta(self, other: "Scenario") -> np.ndarray:
        """Per-cell reach-probability difference ``self − other`` (spec UC10).

        Returns the element-wise difference of the two probability cubes, with the
        same shape as ``probability``: cells are positive where *this* scenario is
        more likely to be reached (more dangerous) than ``other`` and negative
        where it is safer. The two cubes must share a shape.
        """
        if self.probability.shape != other.probability.shape:
            raise ValueError(
                "scenario probability shape mismatch: "
                f"{self.probability.shape} vs {other.probability.shape}"
            )
        return self.probability - other.probability


@dataclass
class Report:
    """A fire report: where and when ignition started.

    For the engine-only scope this simply carries the initial ignition
    coordinates that seed the simulation.
    """

    building_id: str
    ignition_x: int
    ignition_y: int
    ignition_floor: int
    ignition_time: object = None

    def get_ignition_pos(self) -> tuple[int, int, int]:
        """Return ignition position as ``(floor, x, y)``."""
        return (self.ignition_floor, self.ignition_x, self.ignition_y)


class Building:
    """A building: an ordered list of Floors plus inter-floor connections.

    Floor index 0 is the lowest floor; higher indices are higher floors. This
    ordering is what ConnectionCell uses to decide up vs. down transfer.

    Initial ignition points are carried on the building (``ignition_points``)
    so that CAEngine(building, parameters, seed) can seed the starting BURNING
    cells without changing its constructor signature.
    """

    def __init__(self, building_id: str, name: str = "") -> None:
        self.id = building_id
        self.name = name
        self.floors: list[Floor] = []
        self.connections: list[ConnectionCell] = []
        # (floor, x, y) cells that start BURNING.
        self.ignition_points: list[tuple[int, int, int]] = []

    def add_floor(self, floor: Floor) -> int:
        """Append a floor and return its index."""
        self.floors.append(floor)
        return len(self.floors) - 1

    def get_floor(self, idx: int) -> Floor:
        """Return the floor at index ``idx`` (0 = lowest)."""
        return self.floors[idx]

    def add_connection(self, connection: ConnectionCell) -> None:
        """Register an inter-floor connection."""
        self.connections.append(connection)

    def get_connections(self) -> list[ConnectionCell]:
        """Return all inter-floor connections."""
        return self.connections

    def add_ignition(self, floor: int, x: int, y: int) -> None:
        """Register an initial BURNING cell at ``(floor, x, y)``."""
        self.ignition_points.append((floor, x, y))

    @property
    def num_floors(self) -> int:
        """Number of floors in the building."""
        return len(self.floors)
