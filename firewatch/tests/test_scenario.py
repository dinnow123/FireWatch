"""Scenario tests: bundling params with a result cube and per-cell Δ (UC10)."""

import numpy as np
import pytest

from firewatch.domain import Scenario, SimParameters


def _scn(prob, **params):
    return Scenario(SimParameters(**params), np.asarray(prob, dtype=np.float64))


def test_compute_delta_is_elementwise_difference():
    a = _scn([[0.8, 0.2], [0.0, 1.0]])
    b = _scn([[0.5, 0.2], [0.1, 0.4]])
    assert np.allclose(a.compute_delta(b), [[0.3, 0.0], [-0.1, 0.6]])


def test_compute_delta_sign_convention():
    # self − other: positive where self is more dangerous, negative where safer.
    risky = _scn([[0.9]])
    safe = _scn([[0.2]])
    assert risky.compute_delta(safe)[0, 0] > 0   # this scenario more dangerous
    assert safe.compute_delta(risky)[0, 0] < 0   # this scenario safer


def test_compute_delta_antisymmetric():
    a = _scn([[0.7, 0.1]])
    b = _scn([[0.3, 0.9]])
    assert np.allclose(a.compute_delta(b), -b.compute_delta(a))


def test_compute_delta_preserves_cube_shape():
    # A full (F, T, nx, ny) cube differences element-wise, same shape out.
    rng = np.random.default_rng(0)
    cube_a = rng.random((2, 5, 4, 4))
    cube_b = rng.random((2, 5, 4, 4))
    delta = Scenario(SimParameters(), cube_a).compute_delta(
        Scenario(SimParameters(), cube_b)
    )
    assert delta.shape == (2, 5, 4, 4)
    assert np.array_equal(delta, cube_a - cube_b)


def test_compute_delta_shape_mismatch_raises():
    a = _scn([[0.1, 0.2]])
    b = _scn([[0.1, 0.2, 0.3]])
    with pytest.raises(ValueError):
        a.compute_delta(b)


def test_scenario_bundles_parameters():
    s = _scn([[0.0]], sprinkler_active=False, shutter_active=True)
    assert s.parameters.sprinkler_active is False
    assert s.parameters.shutter_active is True
