"""EnsembleRunner: repeat the probabilistic CA run N times and aggregate.

Each run uses a different seed, so the ensemble samples the "different plausible
spread tendencies under incomplete information" that the design philosophy
describes. For every run we record which cells ever caught fire; dividing those
counts by N yields the per-cell reach probability returned in an EnsembleResult.

The per-run work is isolated in ``_run_once`` so the run loop could later be
parallelized (runs are independent); the current implementation is sequential.

Array convention matches ``domain``: per-floor arrays have shape ``(nx, ny)``.
"""

from __future__ import annotations

import numpy as np

from firewatch.engine.ca_engine import CAEngine
from firewatch.domain import Building, CellState, SimParameters
from firewatch.engine.result import EnsembleResult, Snapshot


class EnsembleRunner:
    """Run an ensemble of CA simulations and aggregate reach probabilities.

    Args:
        building: the building to simulate.
        parameters: the scenario's simulation parameters (equipment on/off etc.).
            This is the "scenario" configuration the runner applies to every run.
        n_runs: number of ensemble runs N (the spec targets 20-50).
        base_seed: seed of run 0; run ``i`` uses ``base_seed + i``. Fixing it
            makes the whole ensemble reproducible and lets two scenarios be
            compared under identical randomness.
    """

    def __init__(
        self,
        building: Building,
        parameters: SimParameters,
        n_runs: int,
        base_seed: int = 0,
    ) -> None:
        if n_runs < 1:
            raise ValueError("n_runs must be >= 1")
        self.building = building
        self.parameters = parameters
        self.n_runs = n_runs
        self.base_seed = base_seed
        # Per-floor cumulative ignition counts (filled in by run()).
        self.fire_counts: list[np.ndarray] = []

    def run(self, max_ticks: int) -> EnsembleResult:
        """Run N simulations of ``max_ticks`` ticks and return the aggregate.

        Accumulates, per cell, the number of runs in which it ever became
        BURNING, keeps the first run's per-tick snapshots as the timeline, and
        returns ``probability_maps = fire_counts / n_runs``.
        """
        num_floors = self.building.num_floors
        self.fire_counts = [
            np.zeros(self.building.get_floor(f).get_grid_size(), dtype=np.int64)
            for f in range(num_floors)
        ]
        timeline: list[Snapshot] = []

        for i in range(self.n_runs):
            ever_burning, run_timeline = self._run_once(
                run_index=i, max_ticks=max_ticks, record_timeline=(i == 0)
            )
            for f in range(num_floors):
                self.fire_counts[f] += ever_burning[f].astype(np.int64)
            if i == 0:
                timeline = run_timeline

        probability_maps = [fc / self.n_runs for fc in self.fire_counts]
        return EnsembleResult(probability_maps, self.fire_counts, self.n_runs, timeline)

    def run_probability_cube(
        self, n_snapshots: int, ticks_per_snapshot: int
    ) -> list[np.ndarray]:
        """Run the ensemble and return per-floor *cumulative reach probability over time*.

        Unlike ``run`` (which keeps only the final aggregate plus one run's
        timeline), this accumulates, for every snapshot ``t``, the fraction of
        runs in which each cell had *ever* been BURNING by tick
        ``(t + 1) * ticks_per_snapshot``. The reach mask is OR-accumulated on
        *every* tick (not just at snapshot boundaries) so a cell that flared and
        burned out between two snapshots is still counted; this makes each cube
        monotonically non-decreasing in ``t`` and consistent with ``run``'s
        ``probability_maps`` once enough ticks have elapsed.

        Args:
            n_snapshots: number of time frames to record (the slider's length).
            ticks_per_snapshot: CA ticks advanced between consecutive frames.

        Returns:
            A list with one array per floor, each of shape
            ``(n_snapshots, nx, ny)`` and values in ``[0, 1]``.
        """
        if n_snapshots < 1:
            raise ValueError("n_snapshots must be >= 1")
        if ticks_per_snapshot < 1:
            raise ValueError("ticks_per_snapshot must be >= 1")

        num_floors = self.building.num_floors
        counts = [
            np.zeros((n_snapshots, *self.building.get_floor(f).get_grid_size()), dtype=np.int64)
            for f in range(num_floors)
        ]

        for i in range(self.n_runs):
            engine = CAEngine(self.building, self.parameters, self.base_seed + i)
            ever = [
                engine.states[f] == int(CellState.BURNING) for f in range(num_floors)
            ]
            for snap in range(n_snapshots):
                for _ in range(ticks_per_snapshot):
                    engine.step()
                    for f in range(num_floors):
                        ever[f] |= engine.states[f] == int(CellState.BURNING)
                for f in range(num_floors):
                    counts[f][snap] += ever[f].astype(np.int64)

        return [c / self.n_runs for c in counts]

    def _run_once(
        self, run_index: int, max_ticks: int, record_timeline: bool
    ) -> tuple[list[np.ndarray], list[Snapshot]]:
        """Run a single ensemble member; return its per-floor ever-burning masks.

        ``ever_burning[f][x, y]`` is True if cell ``(x, y)`` on floor ``f`` was
        BURNING at any tick of this run (including the initial ignition and even
        if the cell later turned BURNED or BLOCKED). When ``record_timeline`` is
        set, a Snapshot is captured for the initial state (tick 0) and after each
        tick.
        """
        seed = self.base_seed + run_index
        engine = CAEngine(self.building, self.parameters, seed)
        num_floors = self.building.num_floors

        ever_burning = [
            engine.states[f] == int(CellState.BURNING) for f in range(num_floors)
        ]
        timeline: list[Snapshot] = []
        if record_timeline:
            states, heats = engine.snapshot_arrays()
            timeline.append(Snapshot(0, states, heats))

        for tick in range(1, max_ticks + 1):
            engine.step()
            for f in range(num_floors):
                ever_burning[f] |= engine.states[f] == int(CellState.BURNING)
            if record_timeline:
                states, heats = engine.snapshot_arrays()
                timeline.append(Snapshot(tick, states, heats))

        return ever_burning, timeline
