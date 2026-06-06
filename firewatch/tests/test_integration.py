"""End-to-end integration test: a small 10x10, 2-floor building.

Exercises the whole pipeline (domain -> CAEngine -> EnsembleRunner ->
EnsembleResult) once, with mixed materials, a wall, a sprinkler, a shutter, and
an inter-floor connection, and checks the aggregate output is coherent.
"""

import numpy as np

from firewatch.domain import (
    Building,
    ConnectionCell,
    Floor,
    Material,
    SimParameters,
)
from firewatch.engine.ensemble import EnsembleRunner


def _build_small_building():
    b = Building("demo", "Small Demo Tower")

    f0 = Floor("1F", 10, 10, default_material=Material.WOOD)
    # A patch of more-flammable material and a non-flammable concrete column.
    for x in range(2, 5):
        for y in range(2, 5):
            f0.set_material(x, y, Material.PAPER)
    f0.set_material(7, 7, Material.CONCRETE)
    # A partial wall (not full width, so fire can route around it).
    for y in range(0, 6):
        f0.set_wall(8, y)
    f0.set_sprinkler(1, 1)
    f0.set_shutter(6, 6)

    f1 = Floor("2F", 10, 10, default_material=Material.WOOD)

    b.add_floor(f0)
    b.add_floor(f1)
    # Stairwell connection 1F<->2F with chimney effect.
    b.add_connection(ConnectionCell(0, 5, 5, 1, 5, 5, up_weight=0.9, down_weight=0.3))
    b.add_ignition(0, 5, 5)
    return b


def test_end_to_end_small_building():
    building = _build_small_building()
    params = SimParameters(sprinkler_active=True, shutter_active=True)
    runner = EnsembleRunner(building, params, n_runs=30, base_seed=2026)
    result = runner.run(max_ticks=20)

    # Two floors of probability maps, all within [0, 1].
    assert len(result.probability_maps) == 2
    for pmap in result.probability_maps:
        assert pmap.shape == (10, 10)
        assert pmap.min() >= 0.0
        assert pmap.max() <= 1.0

    # Ignition cell on floor 0 ignites every run.
    assert result.get_probability(0, 5, 5) == 1.0

    # Confidence intervals are valid for every cell on the ignition floor.
    for x in range(10):
        for y in range(10):
            low, high = result.get_ci(0, x, y)
            assert 0.0 <= low <= high <= 1.0

    # Fire spread beyond the ignition cell, and reached the upper floor via the
    # stairwell connection.
    assert result.get_spread_area(0) > 1.0
    assert result.get_spread_area(1) > 0.0

    # Top-risk zones are reported and the ignition cell is among the hottest.
    top = result.get_top_percent_zones(0, pct=10)
    assert len(top) > 0
    assert (5, 5) in top

    # Timeline spans the full run (initial state + one per tick).
    assert len(result.timeline) == 21
    snap = result.get_snapshot(20)
    assert snap.tick == 20
    assert snap.get_state(floor=0).shape == (10, 10)
    assert snap.get_heat(floor=1).shape == (10, 10)


def test_reproducible_end_to_end():
    # The whole ensemble is reproducible given the same base_seed.
    p = SimParameters(sprinkler_active=True, shutter_active=True)
    r1 = EnsembleRunner(_build_small_building(), p, n_runs=15, base_seed=7).run(max_ticks=15)
    r2 = EnsembleRunner(_build_small_building(), p, n_runs=15, base_seed=7).run(max_ticks=15)
    for f in range(2):
        assert np.array_equal(r1.fire_counts[f], r2.fire_counts[f])
