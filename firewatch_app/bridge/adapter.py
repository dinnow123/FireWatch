"""Bridge from the app's sample building data to the *validated* engine.

The app views were written against a 4-D probability cube
``(n_floors, n_timesteps, rows, cols)`` produced by ``generate_ensemble(...)``.
This module keeps that exact contract but computes the cube with the validated
``firewatch.engine`` (the one covered by the test-suite) instead of the
a standalone CA. Swapping engines therefore needs no change in any view.

Coordinate bridge — the two sides index grids differently:
    * app / floor plan: ``cell_map[row, col]``  (shape ``(rows, cols)``)
    * firewatch.engine:       ``array[x, y]``          (shape ``(nx, ny)``)
We bind ``nx = cols`` and ``ny = rows`` so engine ``x`` is a column and engine
``y`` is a row, then transpose each engine map back to ``(rows, cols)`` at the
boundary so the cube the views receive is unchanged.

Material / wall mapping (sample floorplan -> engine):
    ROOM      -> WOOD,   passable
    WALL      -> CONCRETE (multiplier 0, never ignites), starts BLOCKED
    WALL_WEAK -> GYPSUM, passable (can burn through)
    OUTSIDE   -> starts BLOCKED
Only sprinkler/shutter equipment maps to the engine; the sample's ``exit`` markers
have no counterpart in the validated SimParameters and are ignored.
"""
from __future__ import annotations

import numpy as np

from firewatch.domain import (
    Building,
    ConnectionCell,
    Floor,
    Material,
    SimParameters,
)
from firewatch.engine.ensemble import EnsembleRunner

# Chimney weights for the single stairwell connecting consecutive floors.
_UP_WEIGHT = 0.9
_DOWN_WEIGHT = 0.3


# ---------------------------------------------------------------- helpers

def params_to_simparameters(parameters: dict | None) -> SimParameters:
    """Map the scenario's sprinkler/shutter booleans to ``SimParameters``.

    Public so views can build the *same* ``SimParameters`` a run used when they
    bundle that run into a ``Scenario`` — keeping the dict→params mapping in one
    place instead of duplicating its defaults.
    """
    p = parameters or {}
    return SimParameters(
        sprinkler_active=bool(p.get("sprinkler", True)),
        shutter_active=bool(p.get("shutter", True)),
    )


def _nearest_room(cell_map: np.ndarray, x: int, y: int, room_id: int) -> tuple[int, int]:
    """Snap ``(x, y)`` (col, row) to the nearest ROOM cell; identity if already room."""
    rows, cols = cell_map.shape
    if 0 <= y < rows and 0 <= x < cols and int(cell_map[y, x]) == room_id:
        return x, y
    ys, xs = np.where(cell_map == room_id)
    if len(xs) == 0:
        return x, y
    j = int(np.argmin((xs - x) ** 2 + (ys - y) ** 2))
    return int(xs[j]), int(ys[j])


def stairwell_cell(building_data) -> tuple[int, int] | None:
    """The central inter-floor stairwell cell ``(col, row)`` the engine links
    floors through — or ``None`` for a single-floor building.

    Mirrors the connection placed in ``_build_validated_building`` exactly (nearest
    ROOM cell to the building centre) so the UI can mark the *actual* simulated
    stairwell, not a guess.
    """
    if len(building_data.floors) < 2:
        return None
    from firewatch_app.sample_data.floorplan_gen import ROOM, get_layout

    cell_map = get_layout(building_data.id)
    mid_col, mid_row = cell_map.shape[1] // 2, cell_map.shape[0] // 2
    return _nearest_room(cell_map, mid_col, mid_row, ROOM)


def _build_validated_building(
    building_data,
    floor_id: str,
    ignition_point: tuple[int, int],
) -> Building:
    """Translate sample building data + ignition into a ``firewatch.engine`` Building."""
    from firewatch_app.sample_data.floorplan_gen import (
        OUTSIDE, ROOM, WALL, WALL_WEAK, get_layout,
    )

    cell_map = get_layout(building_data.id)        # (rows, cols), indexed [row, col]
    cmap_t = cell_map.T                            # (cols, rows) = (nx, ny), indexed [x, y]
    nx, ny = cmap_t.shape
    floor_names: list[str] = list(building_data.floors)

    wall = (cmap_t == OUTSIDE) | (cmap_t == WALL)
    material = np.full((nx, ny), int(Material.WOOD), dtype=np.int8)
    material[cmap_t == WALL] = int(Material.CONCRETE)
    material[cmap_t == WALL_WEAK] = int(Material.GYPSUM)

    building = Building(building_data.id, getattr(building_data, "name", ""))
    for name in floor_names:
        floor = Floor(name, nx, ny, default_material=Material.WOOD)
        floor.wall = wall.copy()
        floor.material = material.copy()
        building.add_floor(floor)

    # Equipment — only sprinkler/shutter have an engine counterpart.
    for eq in building_data.equipment:
        if eq.floor not in floor_names:
            continue
        f = floor_names.index(eq.floor)
        if not (0 <= eq.x < nx and 0 <= eq.y < ny):
            continue
        if eq.type == "sprinkler":
            building.get_floor(f).set_sprinkler(eq.x, eq.y)
        elif eq.type == "shutter":
            building.get_floor(f).set_shutter(eq.x, eq.y)

    # Single stairwell at the central ROOM cell, linking each consecutive pair.
    n_floors = len(floor_names)
    if n_floors >= 2:
        mid_col, mid_row = cell_map.shape[1] // 2, cell_map.shape[0] // 2
        cx, cy = _nearest_room(cell_map, mid_col, mid_row, ROOM)
        for i in range(n_floors - 1):
            building.add_connection(
                ConnectionCell(i, cx, cy, i + 1, cx, cy, _UP_WEIGHT, _DOWN_WEIGHT)
            )

    # Ignition — snap to a room cell, then seed the starting BURNING cell.
    floor_idx = floor_names.index(floor_id) if floor_id in floor_names else 0
    ix, iy = _nearest_room(cell_map, ignition_point[0], ignition_point[1], ROOM)
    building.add_ignition(floor_idx, ix, iy)

    return building


# ---------------------------------------------------------------- 4D API

def generate_ensemble_ca_4d(
    building_data,
    floor_id: str,
    ignition_point: tuple[int, int],
    n_runs: int = 20,
    n_snapshots: int = 60,
    ticks_per_snapshot: int = 3,
    parameters: dict | None = None,
    seed_base: int = 42,
) -> np.ndarray:
    """Cumulative reach probability over time, shape ``(n_floors, n_snapshots, rows, cols)``.

    Each frame ``t`` is the fraction of ensemble runs in which a cell had ever
    caught fire by tick ``(t + 1) * ticks_per_snapshot`` — monotonic in ``t``.
    """
    building = _build_validated_building(building_data, floor_id, ignition_point)
    params = params_to_simparameters(parameters)
    runner = EnsembleRunner(building, params, n_runs=n_runs, base_seed=seed_base)
    per_floor = runner.run_probability_cube(n_snapshots, ticks_per_snapshot)
    # per_floor[f]: (n_snapshots, nx, ny) -> (n_snapshots, ny, nx) = (T, rows, cols)
    return np.stack([m.transpose(0, 2, 1) for m in per_floor]).astype(np.float32)


# ---------------------------------------------------------------- drop-in

def generate_ensemble(
    building,
    ignition_floor: str,
    ignition_xy: tuple[int, int],
    parameters: dict | None = None,
    n_runs: int = 30,
    n_timesteps: int = 60,
    seed: int = 42,
) -> np.ndarray:
    """Drop-in replacement for the legacy simulator: ``(n_floors, n_timesteps, rows, cols)``.

    Views import only this function, so pointing it at the validated engine is
    the entire switch to the validated engine. ``ticks_per_snapshot`` is 5 so each frame
    advances the fire further: the horizon spans ``n_timesteps * 5`` engine ticks,
    long enough to show slower, walled-off ignitions develop across the timeline.
    """
    return generate_ensemble_ca_4d(
        building_data=building,
        floor_id=ignition_floor,
        ignition_point=ignition_xy,
        n_runs=n_runs,
        n_snapshots=n_timesteps,
        ticks_per_snapshot=5,
        parameters=parameters,
        seed_base=seed,
    )
