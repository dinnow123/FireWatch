"""EnsembleRunner tests: probability range, monotone spread, sprinkler, chimney."""

import numpy as np

from firewatch.domain import (
    Building,
    ConnectionCell,
    Floor,
    Material,
    SimParameters,
)
from firewatch.engine.ensemble import EnsembleRunner


def _center_ignition_building(nx=21, ny=21, material=Material.WOOD):
    b = Building("b")
    b.add_floor(Floor("1F", nx, ny, default_material=material))
    b.add_ignition(0, nx // 2, ny // 2)
    return b


def test_probability_maps_within_unit_range():
    b = _center_ignition_building()
    runner = EnsembleRunner(b, SimParameters(sprinkler_active=False, shutter_active=False), n_runs=20)
    result = runner.run(max_ticks=12)
    pmap = result.probability_maps[0]
    assert pmap.min() >= 0.0
    assert pmap.max() <= 1.0
    # The ignition cell ignites in every run.
    assert result.get_probability(0, 10, 10) == 1.0
    assert result.get_spread_area(0) > 1.0


def test_monotone_spread_near_higher_than_far():
    # Reach probability should decay with distance from the ignition point.
    b = _center_ignition_building(material=Material.TEXTILE)
    runner = EnsembleRunner(b, SimParameters(sprinkler_active=False, shutter_active=False), n_runs=40)
    result = runner.run(max_ticks=10)
    cx, cy = 10, 10

    near = np.mean([
        result.get_probability(0, cx + 1, cy),
        result.get_probability(0, cx - 1, cy),
        result.get_probability(0, cx, cy + 1),
        result.get_probability(0, cx, cy - 1),
    ])
    far = np.mean([
        result.get_probability(0, cx + 6, cy),
        result.get_probability(0, cx - 6, cy),
        result.get_probability(0, cx, cy + 6),
        result.get_probability(0, cx, cy - 6),
    ])
    assert near > far


def test_sprinkler_lowers_average_probability():
    # Same building (sprinklers installed everywhere) and same base_seed; only
    # the sprinkler_active flag differs.
    def build():
        b = Building("b")
        f = Floor("1F", 17, 17, default_material=Material.TEXTILE)
        f.sprinkler[:, :] = True
        b.add_floor(f)
        b.add_ignition(0, 8, 8)
        return b

    on = EnsembleRunner(
        build(), SimParameters(sprinkler_active=True, shutter_active=False, sprinkler_cooling=2.0),
        n_runs=30, base_seed=100,
    ).run(max_ticks=14)
    off = EnsembleRunner(
        build(), SimParameters(sprinkler_active=False, shutter_active=False),
        n_runs=30, base_seed=100,
    ).run(max_ticks=14)

    assert on.probability_maps[0].mean() < off.probability_maps[0].mean()


def test_chimney_effect_upward_stronger_than_downward():
    # Two floors connected at (1,1). Upward transfer (up_weight) must drive a
    # higher ignition probability in the target cell than the symmetric downward
    # case (down_weight), since up_weight > down_weight.
    up_w, down_w = 0.9, 0.3

    def two_floor(ignite_floor):
        b = Building("b")
        b.add_floor(Floor("1F", 3, 3, default_material=Material.TEXTILE))  # floor 0 (lower)
        b.add_floor(Floor("2F", 3, 3, default_material=Material.TEXTILE))  # floor 1 (upper)
        b.add_connection(ConnectionCell(0, 1, 1, 1, 1, 1, up_weight=up_w, down_weight=down_w))
        b.add_ignition(ignite_floor, 1, 1)
        return b

    # A: ignite lower side -> measure upper target (upward transfer).
    up_result = EnsembleRunner(
        two_floor(ignite_floor=0), SimParameters(sprinkler_active=False, shutter_active=False),
        n_runs=60, base_seed=0,
    ).run(max_ticks=12)
    p_up = up_result.get_probability(1, 1, 1)  # upper floor target

    # B: ignite upper side -> measure lower target (downward transfer).
    down_result = EnsembleRunner(
        two_floor(ignite_floor=1), SimParameters(sprinkler_active=False, shutter_active=False),
        n_runs=60, base_seed=0,
    ).run(max_ticks=12)
    p_down = down_result.get_probability(0, 1, 1)  # lower floor target

    assert p_up > p_down


def test_timeline_recorded_for_first_run():
    b = _center_ignition_building()
    runner = EnsembleRunner(b, SimParameters(sprinkler_active=False, shutter_active=False), n_runs=5)
    result = runner.run(max_ticks=8)
    # Initial state (tick 0) plus one snapshot per tick.
    assert len(result.timeline) == 9
    assert result.get_snapshot(0).tick == 0
    assert result.get_snapshot(8).tick == 8


def test_probability_cube_shape_and_range():
    b = _center_ignition_building(nx=15, ny=11)
    runner = EnsembleRunner(
        b, SimParameters(sprinkler_active=False, shutter_active=False), n_runs=12
    )
    cube = runner.run_probability_cube(n_snapshots=6, ticks_per_snapshot=2)
    assert len(cube) == 1  # one floor
    assert cube[0].shape == (6, 15, 11)  # (n_snapshots, nx, ny)
    assert cube[0].min() >= 0.0
    assert cube[0].max() <= 1.0


def test_probability_cube_monotone_in_time():
    # Cumulative reach probability can only grow as time advances.
    b = _center_ignition_building(material=Material.TEXTILE)
    runner = EnsembleRunner(
        b, SimParameters(sprinkler_active=False, shutter_active=False), n_runs=20
    )
    cube = runner.run_probability_cube(n_snapshots=8, ticks_per_snapshot=2)[0]
    diffs = np.diff(cube, axis=0)
    assert (diffs >= -1e-12).all()  # never decreases between snapshots


def test_probability_cube_reproducible():
    def make():
        return EnsembleRunner(
            _center_ignition_building(),
            SimParameters(sprinkler_active=False, shutter_active=False),
            n_runs=10,
            base_seed=7,
        ).run_probability_cube(n_snapshots=5, ticks_per_snapshot=3)[0]

    np.testing.assert_array_equal(make(), make())


def test_probability_cube_last_snapshot_matches_reach():
    # With the same total tick budget, the final cube frame should equal the
    # ensemble reach probability from run() (both count "ever BURNING").
    n_snaps, tps = 6, 2
    total_ticks = n_snaps * tps
    params = SimParameters(sprinkler_active=False, shutter_active=False)

    cube = EnsembleRunner(
        _center_ignition_building(material=Material.TEXTILE), params, n_runs=15, base_seed=3
    ).run_probability_cube(n_snapshots=n_snaps, ticks_per_snapshot=tps)[0]
    reach = EnsembleRunner(
        _center_ignition_building(material=Material.TEXTILE), params, n_runs=15, base_seed=3
    ).run(max_ticks=total_ticks).probability_maps[0]

    np.testing.assert_allclose(cube[-1], reach, atol=1e-12)


def test_probability_cube_ignition_cell_certain():
    b = _center_ignition_building(nx=9, ny=9)
    cube = EnsembleRunner(
        b, SimParameters(sprinkler_active=False, shutter_active=False), n_runs=8
    ).run_probability_cube(n_snapshots=3, ticks_per_snapshot=1)[0]
    # The ignition cell is BURNING from tick 0, so it is certain at every frame.
    assert (cube[:, 4, 4] == 1.0).all()
