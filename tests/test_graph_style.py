from __future__ import annotations

import numpy as np

from xyg import _native
from xyg._figure import Figure
from xyg._graph import GraphData


def test_visual_state_and_label_budget_are_rust_owned() -> None:
    states = _native.graph_visual_states(np.array([0, 2, 3, 64 | 2], dtype=np.uint32))
    assert states.tolist() == [0, 5, 5, 7]
    accepted = _native.graph_label_accept(np.array([1.0, 5.0, 5.0, np.nan, np.inf, -np.inf]), 2)
    assert accepted.tolist() == [False, True, True, False, False, False]
    assert accepted.flags.c_contiguous


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


def test_graph_composition_serializes_rust_owned_style_policy() -> None:
    data = GraphData(
        ["parent", "alpha", "beta"],
        np.array([1], dtype=np.uint64),
        np.array([2], dtype=np.uint64),
        x=np.array([0.0, -1.0, 2.0]),
        y=np.array([0.0, 1.0, 3.0]),
        node_attrs={
            "label": np.array(["Group", "Alpha", "Beta"]),
            "label_priority": np.array([1.0, 5.0, 5.0]),
            "state_flags": np.array([0, 2, 64 | 2], dtype=np.uint32),
        },
        parent_indices=np.array([0, 0, 0], dtype=np.uint64),
        parent_validity=np.array([0, 1, 1], dtype=np.uint8),
    )
    spec, _ = Figure().graph(data, layout="preset", label_budget=2).build_payload()
    graph = spec["graph"][0]
    assert graph["node_labels"] == [None, "Alpha", "Beta"]
    assert graph["label_accepted"] == [False, True, True]
    assert graph["visual_states"] == [0, 5, 7]
    assert graph["parent_of"] == [None, 0, 0]
    assert graph["compound_nodes"] == [True, False, False]
    assert graph["compound_bounds"][0] == [-1.0, 2.0, 0.0, 3.0]


def test_graph_composition_rejects_host_side_policy_shape_mismatch() -> None:
    with np.testing.assert_raises_regex(ValueError, "label_priority"):
        Figure().graph(["a", "b"], [("a", "b")], layout="grid", label_priority=[1.0])


def test_graph_label_text_null_fallback_and_scalar_rejection() -> None:
    data = GraphData(
        ["node-a", "node-b"],
        np.array([0], dtype=np.uint64),
        np.array([1], dtype=np.uint64),
        node_attrs={"label": np.array([None, "Beta"], dtype=object)},
    )
    spec, _ = Figure().graph(data, layout="grid").build_payload()
    assert spec["graph"][0]["node_labels"] == ["node-a", "Beta"]

    for invalid in (True, 1.0, float("nan")):
        with np.testing.assert_raises_regex(TypeError, "strings or null"):
            Figure().graph(["a", "b"], [("a", "b")], layout="grid", node_label=[invalid, "b"])


def test_graph_numeric_identity_label_fallback_is_safe_and_exact() -> None:
    spec, _ = Figure().graph([1, 2], [(1, 2)], layout="grid").build_payload()
    assert spec["graph"][0]["node_labels"] == ["1", "2"]

    unsafe = 2**60
    data = GraphData(
        [unsafe, "safe"], np.array([0], dtype=np.uint64), np.array([1], dtype=np.uint64)
    )
    spec, _ = Figure().graph(data, layout="grid").build_payload()
    assert spec["graph"][0]["node_labels"] == [None, "safe"]
    assert spec["graph"][0]["label_accepted"] == [False, True]
