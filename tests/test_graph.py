"""Graph mark + Rust layout ABI (graph-mark.md)."""

from __future__ import annotations

import numpy as np
import pytest

import xy
from xy import _graph, _native
from xy._figure import Figure


def test_graph_layout_circle_deterministic():
    nodes = ["a", "b", "c", "d"]
    edges = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "a")]
    data = _graph.normalize_graph_inputs(nodes, edges)
    x1, y1, meta1 = _graph.run_layout(data, layout="circle", seed=1)
    x2, y2, meta2 = _graph.run_layout(data, layout="circle", seed=1)
    assert meta1["layout"] == "circle"
    np.testing.assert_allclose(x1, x2)
    np.testing.assert_allclose(y1, y2)


def test_force_seeded_matches_across_calls():
    data = _graph.normalize_graph_inputs(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
    x1, y1, m1 = _graph.run_layout(data, layout="force", seed=7, iterations=40)
    x2, y2, m2 = _graph.run_layout(data, layout="force", seed=7, iterations=40)
    assert m1["layout"] == "force"
    np.testing.assert_allclose(x1, x2)
    np.testing.assert_allclose(y1, y2)
    assert m1["alpha"] == pytest.approx(m2["alpha"])


def test_graph_chart_emits_segments_scatter_and_meta():
    chart = xy.graph_chart(
        xy.graph(["n0", "n1", "n2"], [("n0", "n1"), ("n1", "n2")], layout="grid"),
        width=400,
        height=300,
    )
    fig = chart.figure()
    kinds = [t.kind for t in fig.traces]
    assert "segments" in kinds
    assert "scatter" in kinds
    assert fig._graph_meta is not None
    assert len(fig._graph_meta) == 1
    meta = fig._graph_meta[0]
    assert meta["n_nodes"] == 3
    assert "csr_offsets" in meta
    assert len(meta["csr_offsets"]) == 4
    spec, _blob = fig.build_payload()
    assert "graph" in spec
    assert spec["graph"][0]["layout"] == "grid"


def test_figure_graph_fluent():
    fig = Figure().graph(["a", "b"], [("a", "b")], layout="breadthfirst", directed=False)
    assert fig._graph_meta[0]["layout"] == "breadthfirst"
    assert len(fig.traces) == 2


def test_hierarchical_alias_is_breadthfirst():
    assert _native.graph_layout_id("hierarchical") == _native.GRAPH_LAYOUT_BREADTHFIRST
    assert _native.graph_layout_id("dagre") == _native.GRAPH_LAYOUT_BREADTHFIRST


def test_lod_decision_records_edge_sample():
    tier, kept = _native.graph_lod_decision(100, 10_000, node_budget=50_000, edge_budget=1_000)
    assert tier == 1
    assert kept == 1_000


def test_cluster_aggregate_records_tier_and_centroids():
    x = np.array([0.0, 1.0, 0.0, 100.0, 101.0, 100.0], dtype=np.float64)
    y = np.array([0.0, 0.0, 1.0, 100.0, 100.0, 101.0], dtype=np.float64)
    cx, cy, member_of, tier, kept = _native.graph_cluster_aggregate(
        x, y, n_edges=3, node_budget=2, edge_budget=500
    )
    assert tier == 2  # LodTier::Aggregate
    assert kept == 3
    assert len(cx) == 2
    assert len(cy) == 2
    np.testing.assert_array_equal(member_of, [0, 0, 0, 1, 1, 1])
    np.testing.assert_allclose(cx[0], 1.0 / 3.0)
    np.testing.assert_allclose(cy[0], 1.0 / 3.0)


def test_graph_exports_public():
    assert hasattr(xy, "graph")
    assert hasattr(xy, "graph_chart")
    assert callable(xy.graph)
    assert callable(xy.graph_chart)


def test_from_graphforge_tables():
    nodes = {"id": ["a", "b"]}
    edges = {"source": ["a"], "target": ["b"]}
    data = _graph.from_graphforge_tables(nodes, edges)
    assert data.n_nodes == 2
    assert data.n_edges == 1
