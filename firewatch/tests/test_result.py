"""EnsembleResult / Snapshot / Wilson CI tests, including a hand-calc check."""

import numpy as np
import pytest

from firewatch.engine.result import EnsembleResult, Snapshot, wilson_interval


def test_wilson_hand_calculation():
    # N=100, fire=50, z=1.96 -> well-known Wilson 95% CI ~ (0.4038, 0.5962).
    low, high = wilson_interval(50, 100, z=1.96)
    assert low == pytest.approx(0.4038, abs=1e-3)
    assert high == pytest.approx(0.5962, abs=1e-3)
    # Symmetric around p̂=0.5 in this case.
    assert (low + high) / 2 == pytest.approx(0.5, abs=1e-6)


def test_wilson_bounds_within_unit_interval():
    for count in (0, 1, 50, 99, 100):
        low, high = wilson_interval(count, 100)
        assert low >= 0.0
        assert high <= 1.0
        assert low <= high


def test_wilson_zero_n_returns_zero():
    assert wilson_interval(0, 0) == (0.0, 0.0)


def _make_result(n_runs=10):
    # 3x3 single floor. fire_counts chosen so probabilities are easy to reason about.
    counts = np.array([[10, 5, 0], [3, 0, 0], [0, 0, 0]], dtype=np.int64)
    prob = counts / n_runs
    snap0 = Snapshot(tick=0, states=[np.zeros((3, 3), dtype=np.int8)], heats=[np.zeros((3, 3))])
    snap1 = Snapshot(tick=1, states=[np.ones((3, 3), dtype=np.int8)], heats=[np.ones((3, 3))])
    return EnsembleResult([prob], [counts], n_runs, [snap0, snap1])


def test_get_probability():
    r = _make_result(n_runs=10)
    assert r.get_probability(0, 0, 0) == 1.0
    assert r.get_probability(0, 0, 1) == 0.5
    assert r.get_probability(0, 2, 2) == 0.0


def test_get_ci_matches_wilson_of_counts():
    r = _make_result(n_runs=10)
    assert r.get_ci(0, 0, 1) == wilson_interval(5, 10)
    # All probability maps stay within [0,1] confidence bounds.
    low, high = r.get_ci(0, 0, 0)
    assert 0.0 <= low <= high <= 1.0


def test_get_top_percent_zones_returns_highest():
    r = _make_result(n_runs=10)
    # Top ~33% of 9 cells = 3 cells: the three highest counts (10, 5, 3).
    zones = r.get_top_percent_zones(0, pct=33)
    assert zones[0] == (0, 0)  # highest probability
    assert set(zones) == {(0, 0), (0, 1), (1, 0)}


def test_get_top_percent_zones_excludes_zero():
    r = _make_result(n_runs=10)
    # Asking for 100% must still skip cells with zero probability.
    zones = r.get_top_percent_zones(0, pct=100)
    assert set(zones) == {(0, 0), (0, 1), (1, 0)}
    assert (2, 2) not in zones


def test_get_spread_area_counts_positive_cells():
    r = _make_result(n_runs=10)
    assert r.get_spread_area(0) == 3.0


def test_get_snapshot_by_tick():
    r = _make_result()
    assert r.get_snapshot(1).tick == 1
    assert np.array_equal(r.get_snapshot(1).get_state(), np.ones((3, 3)))
    with pytest.raises(IndexError):
        r.get_snapshot(99)
