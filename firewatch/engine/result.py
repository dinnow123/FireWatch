"""Ensemble result types: Snapshot, EnsembleResult, and the Wilson interval.

EnsembleResult holds the aggregated output of an N-run ensemble and answers all
derived questions about it (reach probability, confidence interval, time-rewind
snapshots, top-risk zones, spread area). Per the design's "uncertainty
quantification" philosophy, confidence is reported with a Wilson Score interval,
which stays well-behaved for small N and for probabilities near 0 or 1.

Array convention matches ``domain``: per-floor maps have shape ``(nx, ny)``,
indexed ``[x, y]``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


def wilson_interval(count: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson Score confidence interval for a binomial proportion.

    Treats ``count`` successes out of ``n`` Bernoulli trials and returns the
    ``z``-level interval (z=1.96 -> 95%). The result is clamped to ``[0, 1]``.
    Returns ``(0.0, 0.0)`` when ``n <= 0``.

    Formula (spec 6.1):
        center = (p̂ + z²/2N) / (1 + z²/N)
        margin = (z / (1 + z²/N)) · sqrt( p̂(1-p̂)/N + z²/4N² )
    """
    if n <= 0:
        return (0.0, 0.0)
    p_hat = count / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2.0 * n)) / denom
    margin = (z / denom) * math.sqrt(p_hat * (1.0 - p_hat) / n + z2 / (4.0 * n * n))
    low = max(0.0, center - margin)
    high = min(1.0, center + margin)
    return (low, high)


@dataclass
class Snapshot:
    """Frozen grid state at one tick, used for time-rewind.

    ``states`` and ``heats`` are lists of per-floor 2D arrays (one entry per
    floor). The accessors default to floor 0 (the ignition-floor representative).
    """

    tick: int
    states: list[np.ndarray]
    heats: list[np.ndarray]

    def get_state(self, floor: int = 0) -> np.ndarray:
        """Return the cell-state array for ``floor`` at this tick."""
        return self.states[floor]

    def get_heat(self, floor: int = 0) -> np.ndarray:
        """Return the heat array for ``floor`` at this tick."""
        return self.heats[floor]


class EnsembleResult:
    """Aggregated result of an N-run ensemble and its derived interpretations.

    Args:
        probability_maps: per-floor 2D float arrays of reach probability (0..1).
        fire_counts: per-floor 2D int arrays of how many runs ignited each cell.
            Kept because the Wilson interval is computed from raw counts and N.
        n_runs: number of ensemble runs N.
        timeline: per-tick snapshots of one representative run (for time-rewind).
    """

    def __init__(
        self,
        probability_maps: list[np.ndarray],
        fire_counts: list[np.ndarray],
        n_runs: int,
        timeline: list[Snapshot],
    ) -> None:
        self.probability_maps = probability_maps
        self.fire_counts = fire_counts
        self.n_runs = n_runs
        self.timeline = timeline

    def get_probability(self, floor: int, x: int, y: int) -> float:
        """Return the reach probability (0..1) of cell ``(x, y)`` on ``floor``."""
        return float(self.probability_maps[floor][x, y])

    def get_ci(self, floor: int, x: int, y: int, z: float = 1.96) -> tuple[float, float]:
        """Return the Wilson Score confidence interval for cell ``(x, y)``.

        Uses the raw ignition count and N. Returns ``(0.0, 0.0)`` when N == 0.
        """
        if self.n_runs <= 0:
            return (0.0, 0.0)
        count = int(self.fire_counts[floor][x, y])
        return wilson_interval(count, self.n_runs, z)

    def get_snapshot(self, tick: int) -> Snapshot:
        """Return the timeline snapshot whose ``tick`` matches ``tick``.

        Raises:
            IndexError: if no snapshot exists for ``tick``.
        """
        for snap in self.timeline:
            if snap.tick == tick:
                return snap
        raise IndexError(f"no snapshot recorded for tick {tick}")

    def get_top_percent_zones(self, floor: int, pct: float) -> list[tuple[int, int]]:
        """Return ``(x, y)`` coords of the highest-probability ``pct``% of cells.

        Cells are ranked by reach probability (descending); the top
        ``ceil(total_cells · pct/100)`` are returned, excluding any cell with
        probability 0 (a zone never reached is not a risk zone). Returns an empty
        list when no cell has positive probability.
        """
        prob = self.probability_maps[floor]
        nx, ny = prob.shape
        total = nx * ny
        k = max(1, int(math.ceil(total * pct / 100.0)))
        flat = prob.ravel()
        order = np.argsort(flat)[::-1]  # descending probability
        coords: list[tuple[int, int]] = []
        for flat_idx in order[:k]:
            if flat[flat_idx] <= 0.0:
                break  # sorted descending: everything after is also 0
            x, y = divmod(int(flat_idx), ny)
            coords.append((x, y))
        return coords

    def get_spread_area(self, floor: int) -> float:
        """Return the number of cells with positive reach probability on ``floor``.

        Defined as the count of cells whose probability is strictly greater than
        0 (i.e. ignited in at least one run). With 1 m × 1 m cells this count is
        numerically equal to the spread area in square meters.
        """
        return float(np.count_nonzero(self.probability_maps[floor] > 0.0))
