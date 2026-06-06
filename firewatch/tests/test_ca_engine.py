"""CAEngine tests: reproducibility, seed sensitivity, and wall blocking."""

import numpy as np

from firewatch.engine.ca_engine import CAEngine
from firewatch.domain import Building, CellState, Floor, Material, SimParameters


def _single_floor_building(nx=15, ny=15, material=Material.TEXTILE, ignition=(7, 7)):
    b = Building("b")
    b.add_floor(Floor("1F", nx, ny, default_material=material))
    b.add_ignition(0, *ignition)
    return b


def _run(engine, ticks):
    for _ in range(ticks):
        engine.step()


class _ConstRng:
    """RNG stub whose ``random`` returns a fixed value across the whole grid.

    Makes the probabilistic ignition deterministic in tests: with value 0.0 the
    draw ``u = 0`` satisfies ``u < p`` for any ``p > 0``, so a cell ignites iff
    it is an EMPTY ignition candidate.
    """

    def __init__(self, value: float) -> None:
        self._value = value

    def random(self, shape):
        return np.full(shape, self._value, dtype=np.float64)


def test_reproducibility_same_seed_identical():
    params = SimParameters(sprinkler_active=False, shutter_active=False)
    e1 = CAEngine(_single_floor_building(), params, seed=42)
    e2 = CAEngine(_single_floor_building(), params, seed=42)
    _run(e1, 20)
    _run(e2, 20)
    assert np.array_equal(e1.states[0], e2.states[0])
    assert np.array_equal(e1.heats[0], e2.heats[0])
    assert np.array_equal(e1.burn_timers[0], e2.burn_timers[0])


def test_different_seed_diverges():
    params = SimParameters(sprinkler_active=False, shutter_active=False)
    e1 = CAEngine(_single_floor_building(), params, seed=1)
    e2 = CAEngine(_single_floor_building(), params, seed=2)
    _run(e1, 20)
    _run(e2, 20)
    # After enough probabilistic ticks the two grids should differ.
    assert not np.array_equal(e1.states[0], e2.states[0])


def test_wall_blocks_spread():
    # Full-width wall row at y=5 separates ignition (below) from the region above.
    nx, ny = 11, 11
    floor = Floor("1F", nx, ny, default_material=Material.TEXTILE)
    for x in range(nx):
        floor.set_wall(x, 5)
    b = Building("b")
    b.add_floor(floor)
    b.add_ignition(0, 5, 4)  # just below the wall

    params = SimParameters(sprinkler_active=False, shutter_active=False)
    engine = CAEngine(b, params, seed=7)
    _run(engine, 80)

    state = engine.states[0]
    # Wall cells stay BLOCKED throughout.
    assert np.all(state[:, 5] == int(CellState.BLOCKED))
    # Nothing above the wall ever ignites; it stays EMPTY.
    assert np.all(state[:, 6:] == int(CellState.EMPTY))
    # Sanity: the fire actually spread within the region below the wall.
    below = state[:, :5]
    assert np.any((below == int(CellState.BURNING)) | (below == int(CellState.BURNED)))


def test_blocked_cells_never_ignite():
    # A lone wall cell adjacent to fire must remain BLOCKED.
    floor = Floor("1F", 9, 9, default_material=Material.TEXTILE)
    floor.set_wall(5, 4)
    b = Building("b")
    b.add_floor(floor)
    b.add_ignition(0, 4, 4)
    engine = CAEngine(b, SimParameters(sprinkler_active=False, shutter_active=False), seed=3)
    _run(engine, 40)
    assert engine.states[0][5, 4] == int(CellState.BLOCKED)


def test_shutter_blocks_before_ignition_same_tick():
    # Design step order: ... -> fire-shutter -> ignition -> burn-timer. A shutter
    # cell that crosses its trigger heat this tick must be BLOCKED *before* the
    # ignition step, so it can never ignite on the same tick. This pins that
    # ordering: if the shutter ran after ignition (the old order), the cell would
    # ignite and — burning out in one tick — reach BURNED, escaping the shutter.
    floor = Floor("1F", 3, 3, default_material=Material.WOOD)
    floor.set_shutter(1, 1)
    b = Building("b")
    b.add_floor(floor)  # no ignition points: we set the cell's heat directly

    params = SimParameters(
        sprinkler_active=False, shutter_active=True, shutter_trigger_heat=5.0
    )
    engine = CAEngine(b, params, seed=0)
    # Center is past both the WOOD ignition threshold (4.0) and the shutter
    # trigger (5.0): absent the shutter it would ignite this tick.
    engine.heats[0][1, 1] = 10.0
    engine.rng = _ConstRng(0.0)        # force u < p (deterministic ignition)
    engine._burn_duration[0][1, 1] = 1  # burn out in one tick (order-sensitive)

    engine.step()

    # Shutter ran before ignition: the cell is BLOCKED and never became BURNING.
    assert engine.states[0][1, 1] == int(CellState.BLOCKED)

    # Control: with the shutter inactive, the same cell DOES ignite this tick
    # (and, burning out in one tick, reaches BURNED) — proving the cell really
    # was an ignition candidate and the shutter is what stopped it.
    floor2 = Floor("1F", 3, 3, default_material=Material.WOOD)
    floor2.set_shutter(1, 1)
    b2 = Building("b")
    b2.add_floor(floor2)
    e2 = CAEngine(
        b2,
        SimParameters(sprinkler_active=False, shutter_active=False, shutter_trigger_heat=5.0),
        seed=0,
    )
    e2.heats[0][1, 1] = 10.0
    e2.rng = _ConstRng(0.0)
    e2._burn_duration[0][1, 1] = 1
    e2.step()
    assert e2.states[0][1, 1] != int(CellState.BLOCKED)
    assert e2.states[0][1, 1] in (int(CellState.BURNING), int(CellState.BURNED))


def test_get_fire_map_marks_burning_and_burned():
    engine = CAEngine(
        _single_floor_building(ignition=(7, 7)),
        SimParameters(sprinkler_active=False, shutter_active=False),
        seed=0,
    )
    _run(engine, 5)
    fire = engine.get_fire_map(0)
    assert fire.dtype == bool
    assert fire[7, 7]  # ignition cell is burning or burned
