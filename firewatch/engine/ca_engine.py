"""CAEngine: one probabilistic cellular-automata fire-spread run.

A single CAEngine instance carries the mutable simulation state for one
ensemble member. ``step()`` advances the whole building by one tick using the
formulas from spec section 5; all grid operations are vectorized numpy (no
per-cell Python loops — the only loops are over the 8 fixed Moore directions and
over the small list of inter-floor connections).

heat is a *cumulative risk indicator*, not a temperature: it has no natural
decay and only ever decreases when a sprinkler cools a cell.

Coordinate / array convention follows ``domain``: every per-floor array has
shape ``(nx, ny)`` and is indexed ``arr[x, y]``. The building is a list of such
floors (effectively 3D).
"""

from __future__ import annotations

import numpy as np

from firewatch.domain import (
    BURN_DURATION_BY_CODE,
    MULTIPLIER_BY_CODE,
    THRESHOLD_BY_CODE,
    Building,
    CellState,
    SimParameters,
)

# Moore neighborhood split into orthogonal (distance 1) and diagonal directions.
_ORTHOGONAL = ((-1, 0), (1, 0), (0, -1), (0, 1))
_DIAGONAL = ((-1, -1), (-1, 1), (1, -1), (1, 1))


def _shift_mask(mask: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Return ``result[x, y] = mask[x + dx, y + dy]`` with zero-fill at edges.

    Unlike ``np.roll`` this does NOT wrap around grid boundaries, so fire cannot
    leak from one edge to the opposite edge.
    """
    nx, ny = mask.shape
    out = np.zeros_like(mask)
    x_src0, x_src1 = max(0, dx), nx + min(0, dx)
    y_src0, y_src1 = max(0, dy), ny + min(0, dy)
    x_dst0, x_dst1 = max(0, -dx), nx + min(0, -dx)
    y_dst0, y_dst1 = max(0, -dy), ny + min(0, -dy)
    out[x_dst0:x_dst1, y_dst0:y_dst1] = mask[x_src0:x_src1, y_src0:y_src1]
    return out


class CAEngine:
    """Single probabilistic CA fire-spread run over a building.

    Args:
        building: the building to simulate (its floors supply static per-cell
            material / sprinkler / shutter / wall data, and its
            ``ignition_points`` seed the initial BURNING cells).
        parameters: scenario parameters (equipment on/off and their strengths).
        seed: RNG seed. With a fixed seed the run is fully reproducible.
    """

    # Empirical coefficients shared by all instances. These are NOT physically
    # calibrated values; only relative comparisons between scenarios/materials
    # are meaningful. Tune them here.
    BASE_TRANSFER: float = 1.0
    BASE_IGNITION_PROB: float = 0.35
    DIAGONAL_FACTOR: float = 1.0 / np.sqrt(2.0)  # mathematical constant ~0.7071

    def __init__(self, building: Building, parameters: SimParameters, seed: int) -> None:
        self.building = building
        self.parameters = parameters
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.tick = 0

        # Mutable per-floor working state.
        self.states: list[np.ndarray] = []
        self.heats: list[np.ndarray] = []
        self.burn_timers: list[np.ndarray] = []
        # Static per-floor property arrays (precomputed from material codes).
        self._multiplier: list[np.ndarray] = []
        self._threshold: list[np.ndarray] = []
        self._burn_duration: list[np.ndarray] = []
        self._sprinkler: list[np.ndarray] = []
        self._shutter: list[np.ndarray] = []

        for floor in building.floors:
            nx, ny = floor.get_grid_size()
            state = np.full((nx, ny), int(CellState.EMPTY), dtype=np.int8)
            state[floor.wall] = int(CellState.BLOCKED)
            self.states.append(state)
            self.heats.append(np.zeros((nx, ny), dtype=np.float64))
            self.burn_timers.append(np.zeros((nx, ny), dtype=np.int64))
            self._multiplier.append(MULTIPLIER_BY_CODE[floor.material])
            self._threshold.append(THRESHOLD_BY_CODE[floor.material])
            self._burn_duration.append(BURN_DURATION_BY_CODE[floor.material])
            self._sprinkler.append(floor.sprinkler)
            self._shutter.append(floor.shutter)

        # Seed initial BURNING cells from the building's ignition points.
        for floor_idx, x, y in building.ignition_points:
            self.states[floor_idx][x, y] = int(CellState.BURNING)

    # ------------------------------------------------------------------ public
    def step(self) -> None:
        """Advance the whole building by one tick.

        Sub-step order follows the design spec exactly:
        (1) same-floor heat → (2) inter-floor heat  [both in ``_propagate_heat``]
        → (3) sprinkler cooling → (4) fire-shutter drop → (5) probabilistic
        ignition → (6) burn-timer aging.

        The shutter drop (4) runs *before* ignition (5): a shutter cell that
        reaches its trigger heat this tick becomes BLOCKED first, so it can no
        longer be an EMPTY ignition candidate and cannot ignite on the same tick.
        """
        self._propagate_heat()
        self._apply_sprinkler()
        self._apply_shutter()
        self._determine_ignition()
        self._update_burning()
        self.tick += 1

    def get_fire_map(self, floor: int) -> np.ndarray:
        """Return a boolean map of cells that are BURNING or BURNED on ``floor``."""
        state = self.states[floor]
        return (state == int(CellState.BURNING)) | (state == int(CellState.BURNED))

    def snapshot_arrays(self) -> tuple[list[np.ndarray], list[np.ndarray]]:
        """Return deep copies of (per-floor states, per-floor heats) for timeline use."""
        return ([s.copy() for s in self.states], [h.copy() for h in self.heats])

    # --------------------------------------------------------------- internals
    def _propagate_heat(self) -> None:
        """Accumulate heat from BURNING neighbors: Moore (same floor) + connections.

        Heat added to a target cell uses the *target* cell's material multiplier
        (spec 5.1: ``m`` is the absorbing cell's multiplier).
        """
        burning_masks = [(s == int(CellState.BURNING)) for s in self.states]

        # Same-floor Moore-neighbor transfer (vectorized via directional shifts).
        for floor_idx, burning in enumerate(burning_masks):
            burning_f = burning.astype(np.float64)
            contrib = np.zeros_like(burning_f)
            for dx, dy in _ORTHOGONAL:
                contrib += _shift_mask(burning_f, dx, dy)
            # Diagonal transfer, but flame cannot squeeze through a corner that is
            # sealed on both flanks: a diagonal step into target (x, y) from a
            # burning source (x+dx, y+dy) is blocked when BOTH orthogonal cells
            # flanking it — (x+dx, y) and (x, y+dy) — are BLOCKED (wall / dropped
            # shutter / outside). If at least one flank is open, heat can wrap
            # around it, so the diagonal still applies.
            blocked_f = (self.states[floor_idx] == int(CellState.BLOCKED)).astype(np.float64)
            diag = np.zeros_like(burning_f)
            for dx, dy in _DIAGONAL:
                src = _shift_mask(burning_f, dx, dy)
                corner_a = _shift_mask(blocked_f, dx, 0)   # cell (x+dx, y)
                corner_b = _shift_mask(blocked_f, 0, dy)   # cell (x, y+dy)
                src[(corner_a > 0.0) & (corner_b > 0.0)] = 0.0
                diag += src
            contrib += diag * self.DIAGONAL_FACTOR
            self.heats[floor_idx] += self.BASE_TRANSFER * contrib * self._multiplier[floor_idx]

        # Inter-floor transfer through connection cells (chimney effect).
        for conn in self.building.get_connections():
            self._transfer_connection(conn, burning_masks)

    def _transfer_connection(self, conn, burning_masks: list[np.ndarray]) -> None:
        """Apply one ConnectionCell's vertical heat transfer for this tick."""
        # If side A is burning, side B (on conn.floor_b) absorbs heat.
        if burning_masks[conn.floor_a][conn.x_a, conn.y_a]:
            weighted = conn.transfer_heat(from_floor=conn.floor_a, heat=self.BASE_TRANSFER)
            self.heats[conn.floor_b][conn.x_b, conn.y_b] += (
                weighted * self._multiplier[conn.floor_b][conn.x_b, conn.y_b]
            )
        # If side B is burning, side A (on conn.floor_a) absorbs heat.
        if burning_masks[conn.floor_b][conn.x_b, conn.y_b]:
            weighted = conn.transfer_heat(from_floor=conn.floor_b, heat=self.BASE_TRANSFER)
            self.heats[conn.floor_a][conn.x_a, conn.y_a] += (
                weighted * self._multiplier[conn.floor_a][conn.x_a, conn.y_a]
            )

    def _apply_sprinkler(self) -> None:
        """Cool sprinkler cells (spec 5.2). No-op if sprinklers are inactive."""
        if not self.parameters.is_sprinkler_active():
            return
        cooling = self.parameters.sprinkler_cooling
        for floor_idx, mask in enumerate(self._sprinkler):
            heat = self.heats[floor_idx]
            np.subtract(heat, cooling, out=heat, where=mask)
            np.clip(heat, 0.0, None, out=heat)

    def _determine_ignition(self) -> None:
        """Probabilistically ignite EMPTY cells whose heat passed threshold (spec 5.3).

        ``rng.random`` is drawn once per floor per tick over the whole grid, so
        the seed fully determines which cells ignite.
        """
        for floor_idx in range(len(self.states)):
            state = self.states[floor_idx]
            heat = self.heats[floor_idx]
            theta = self._threshold[floor_idx]
            m_mult = self._multiplier[floor_idx]

            frac = np.clip((heat - theta) / theta, 0.0, 1.0)
            p = self.BASE_IGNITION_PROB * m_mult * frac

            candidate = (state == int(CellState.EMPTY)) & (heat >= theta)
            u = self.rng.random(state.shape)
            ignite = candidate & (u < p)
            state[ignite] = int(CellState.BURNING)

    def _update_burning(self) -> None:
        """Age BURNING cells and transition them to BURNED (spec 5.4)."""
        for floor_idx in range(len(self.states)):
            state = self.states[floor_idx]
            timer = self.burn_timers[floor_idx]
            duration = self._burn_duration[floor_idx]

            burning = state == int(CellState.BURNING)
            timer[burning] += 1
            burned = burning & (timer >= duration)
            state[burned] = int(CellState.BURNED)

    def _apply_shutter(self) -> None:
        """Drop fire shutters that have reached their trigger heat (spec sub-step 4).

        Runs before ignition, so a shutter cell tripped this tick is BLOCKED
        before the ignition step sees it and therefore cannot ignite on the same
        tick. A triggered shutter cell becomes BLOCKED, physically halting
        spread. Only EMPTY or BURNING cells convert; already-BURNED cells are
        left as-is.
        """
        if not self.parameters.is_shutter_active():
            return
        trigger = self.parameters.shutter_trigger_heat
        for floor_idx, shutter in enumerate(self._shutter):
            state = self.states[floor_idx]
            heat = self.heats[floor_idx]
            active = (state == int(CellState.EMPTY)) | (state == int(CellState.BURNING))
            trip = shutter & (heat >= trigger) & active
            state[trip] = int(CellState.BLOCKED)
