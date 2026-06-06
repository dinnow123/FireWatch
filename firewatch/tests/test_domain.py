"""Step-1 sanity checks for the domain data structures and material table."""

import numpy as np

from firewatch.domain import (
    BURN_DURATION_BY_CODE,
    MULTIPLIER_BY_CODE,
    THRESHOLD_BY_CODE,
    Building,
    CellState,
    ConnectionCell,
    Floor,
    Material,
    Report,
    SimParameters,
)


def test_cell_state_values():
    assert (CellState.EMPTY, CellState.BURNING, CellState.BURNED, CellState.BLOCKED) == (0, 1, 2, 3)


def test_material_property_accessors_match_tables():
    for m in Material:
        assert m.get_multiplier() == MULTIPLIER_BY_CODE[int(m)]
        assert m.get_threshold() == THRESHOLD_BY_CODE[int(m)]
        assert m.get_burn_duration() == BURN_DURATION_BY_CODE[int(m)]


def test_material_differentiation():
    # PAPER ignites readily; CONCRETE effectively never does.
    assert Material.PAPER.get_threshold() < Material.WOOD.get_threshold()
    assert Material.PAPER.get_multiplier() > Material.WOOD.get_multiplier()
    assert Material.CONCRETE.get_multiplier() == 0.0
    assert Material.CONCRETE.get_threshold() > 1e3


def test_lookup_arrays_are_vectorizable():
    # Indexing a material grid by code must yield the per-cell property grid.
    grid = np.array([[Material.WOOD, Material.PAPER], [Material.CONCRETE, Material.TEXTILE]])
    mult = MULTIPLIER_BY_CODE[grid]
    assert mult.shape == (2, 2)
    assert mult[0, 1] == Material.PAPER.get_multiplier()
    assert mult[1, 0] == 0.0


def test_floor_shape_and_setters():
    f = Floor("1F", 10, 8, default_material=Material.WOOD)
    assert f.get_grid_size() == (10, 8)
    assert f.material.shape == (10, 8)
    f.set_material(2, 3, Material.PAPER)
    f.set_wall(0, 0)
    f.set_sprinkler(5, 5)
    f.set_shutter(6, 6)
    assert f.material[2, 3] == int(Material.PAPER)
    assert f.wall[0, 0]
    assert f.sprinkler[5, 5]
    assert f.shutter[6, 6]


def test_connection_cell_chimney_direction():
    # Floor 0 (lower) -> floor 1 (upper): upward, uses up_weight.
    c = ConnectionCell(0, 1, 1, 1, 1, 1, up_weight=0.9, down_weight=0.3)
    assert c.transfer_heat(from_floor=0, heat=10.0) == 9.0  # up
    assert c.transfer_heat(from_floor=1, heat=10.0) == 3.0  # down
    assert c.up_weight > c.down_weight


def test_sim_parameters_defaults_active():
    p = SimParameters()
    assert p.is_sprinkler_active()
    assert p.is_shutter_active()


def test_building_assembly():
    b = Building("bld-1", "Test Tower")
    i0 = b.add_floor(Floor("1F", 5, 5))
    i1 = b.add_floor(Floor("2F", 5, 5))
    assert (i0, i1) == (0, 1)
    assert b.num_floors == 2
    b.add_connection(ConnectionCell(0, 2, 2, 1, 2, 2, 0.9, 0.3))
    assert len(b.get_connections()) == 1
    b.add_ignition(0, 2, 2)
    assert b.ignition_points == [(0, 2, 2)]


def test_report_ignition_pos():
    r = Report("bld-1", ignition_x=3, ignition_y=4, ignition_floor=1)
    assert r.get_ignition_pos() == (1, 3, 4)
