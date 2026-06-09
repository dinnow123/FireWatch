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


def test_diagonal_blocked_by_sealed_corner():
    # Regression: flame must not "cut" a diagonal corner that is sealed on BOTH
    # flanks. 3x3 (engine [x, y]): ignition (2,0) burns; its only two orthogonal
    # neighbors (1,0) and (2,1) are walls; the diagonal cell (1,1) sits behind
    # that sealed corner and must stay cold — its sole heat path is the diagonal
    # from (2,0), which the corner rule blocks.
    floor = Floor("1F", 3, 3, default_material=Material.WOOD)
    floor.set_wall(1, 0)
    floor.set_wall(2, 1)
    b = Building("b")
    b.add_floor(floor)
    b.add_ignition(0, 2, 0)
    engine = CAEngine(b, SimParameters(sprinkler_active=False, shutter_active=False), seed=0)
    engine.rng = _ConstRng(0.0)        # ignite iff EMPTY candidate with heat >= theta
    _run(engine, 30)

    st = engine.states[0]
    assert st[1, 1] == int(CellState.EMPTY)          # never ignited
    assert engine.heats[0][1, 1] == 0.0              # no heat leaked through the corner


def test_diagonal_allowed_when_one_flank_open():
    # Same corner, but only ONE flank is a wall: heat can wrap around the open
    # flank (an L-path), so the diagonal cell DOES catch. Guards against the
    # corner rule over-blocking legitimate diagonal spread.
    floor = Floor("1F", 3, 3, default_material=Material.WOOD)
    floor.set_wall(1, 0)               # (2,1) left open
    b = Building("b")
    b.add_floor(floor)
    b.add_ignition(0, 2, 0)
    engine = CAEngine(b, SimParameters(sprinkler_active=False, shutter_active=False), seed=0)
    engine.rng = _ConstRng(0.0)
    _run(engine, 30)

    st = engine.states[0]
    assert st[1, 1] in (int(CellState.BURNING), int(CellState.BURNED))


def test_shutter_trigger_below_threshold_prevents_breach():
    # Regression: the shutter trigger must sit BELOW the lowest passable ignition
    # threshold (WOOD theta = 4.0). If a shutter cell's heat lands in the window
    # [theta, trigger) it ignites *before* the shutter drops and fire leaks past
    # the line. Inject heat = 4.5 (past theta) and compare triggers.
    def run_once(trigger: float) -> int:
        floor = Floor("1F", 3, 3, default_material=Material.WOOD)
        floor.set_shutter(1, 1)
        b = Building("b")
        b.add_floor(floor)
        engine = CAEngine(
            b,
            SimParameters(sprinkler_active=False, shutter_active=True, shutter_trigger_heat=trigger),
            seed=0,
        )
        engine.heats[0][1, 1] = 4.5    # past WOOD theta (4.0)
        engine.rng = _ConstRng(0.0)    # force ignition if the cell is a candidate
        engine.step()
        return int(engine.states[0][1, 1])

    # Trigger BELOW theta: shutter drops first -> BLOCKED, no ignition, no breach.
    assert run_once(2.0) == int(CellState.BLOCKED)
    # Trigger ABOVE theta (the old buggy value): the cell ignites before the
    # shutter can drop -> NOT blocked. This is the window the fix closes.
    assert run_once(5.0) != int(CellState.BLOCKED)


def test_default_shutter_trigger_is_below_wood_threshold():
    # The fix lives in the default value; pin the invariant so it can't regress
    # back above the ignition threshold.
    assert SimParameters().shutter_trigger_heat < float(Material.WOOD.get_threshold())


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
