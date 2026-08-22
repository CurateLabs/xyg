from __future__ import annotations

import numpy as np

from xyg import _native


def test_visual_state_and_label_budget_are_rust_owned() -> None:
    states = _native.graph_visual_states(np.array([0, 2, 3, 64 | 2], dtype=np.uint32))
    assert states.tolist() == [0, 5, 5, 7]
    accepted = _native.graph_label_accept(np.array([1.0, 5.0, 5.0, np.nan]), 2)
    assert accepted.tolist() == [False, True, True, False]


def test_compound_bounds_keep_membership_and_child_identity() -> None:
    parent_of, compounds, bounds = _native.graph_compound_bounds(
        np.array([0.0, -1.0, 2.0, 9.0]),
        np.array([0.0, 1.0, 3.0, 9.0]),
        np.array([0, 0, 0, 0], dtype=np.uint64),
        np.array([0, 1, 1, 0], dtype=np.uint8),
    )
    assert parent_of.tolist() == [2**64 - 1, 0, 0, 2**64 - 1]
    assert compounds.tolist() == [True, False, False, False]
    np.testing.assert_allclose(bounds[0], [-1.0, 2.0, 0.0, 3.0])
    assert np.isnan(bounds[1]).all()


def test_graph_style_python_ingress_rejects_lossy_values_before_ffi() -> None:
    for flags in ([True], [1.5], [-1], [2**32]):
        with np.testing.assert_raises((TypeError, ValueError, OverflowError)):
            _native.graph_visual_states(np.asarray(flags))
    for budget in (True, 1.5, -1, 2**64):
        with np.testing.assert_raises((TypeError, ValueError, OverflowError)):
            _native.graph_label_accept(np.array([1.0]), budget)  # type: ignore[arg-type]
    with np.testing.assert_raises(ValueError):
        _native.graph_compound_bounds(np.zeros(2), np.zeros(2), np.array([-1, 0]), np.array([0, 1]))
    parent_of, _, _ = _native.graph_compound_bounds(
        np.zeros(2), np.zeros(2), np.array([0, 0]), np.array([0, 1])
    )
    assert parent_of.tolist() == [2**64 - 1, 0]


def test_graph_style_python_rejects_compound_cycle() -> None:
    with np.testing.assert_raises(ValueError):
        _native.graph_compound_bounds(
            np.zeros(3),
            np.zeros(3),
            np.array([1, 2, 0], dtype=np.uint64),
            np.ones(3, dtype=np.uint8),
        )
