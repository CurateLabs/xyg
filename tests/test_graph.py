"""Graph mark + Rust layout ABI (graph-mark.md)."""

from __future__ import annotations

import numpy as np
import pytest

import xyg
from xyg import _graph, _native
from xyg._figure import Figure


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


def test_cose_options_pins_bounds_and_compounds_cross_python_abi():
    data = _graph.normalize_graph_inputs(
        ["parent-a", "child-a", "parent-b", "child-b"],
        [],
        x=[-0.8, -0.6, 0.8, 0.6],
        y=[0.2, 0.0, -0.2, 0.0],
    )
    data.parent_indices = np.array([0, 0, 0, 2], dtype=np.uint64)
    data.parent_validity = np.array([0, 1, 0, 1], dtype=np.uint8)
    x, y, meta = _graph.run_layout(
        data,
        layout="cose",
        seed=19,
        iterations=20,
        pinned=[True, False, False, False],
        cose={
            "ideal_edge_length": 0.4,
            "repulsion_strength": 2.0,
            "gravity_strength": 0.2,
            "cooling_factor": 0.9,
            "overlap_padding": 0.5,
            "component_spacing": 3.0,
            "bounds": (-1.0, -1.0, 1.0, 1.0),
        },
    )
    assert meta["layout"] == "cose"
    assert (x[0], y[0]) == (-0.8, 0.2)
    assert np.all((x >= -1.0) & (x <= 1.0))
    assert np.all((y >= -1.0) & (y <= 1.0))
    assert meta["alpha"] == pytest.approx(0.9**20)


def test_cose_ergonomics_fail_closed():
    data = _graph.normalize_graph_inputs(["a"], [], x=[0.0], y=[0.0])
    with pytest.raises(ValueError, match="unknown CoSE option"):
        _graph.run_layout(data, layout="cose", cose={"host_force": 1})
    with pytest.raises(ValueError, match="require algorithm='cose'"):
        _graph.run_layout(data, layout="force", cose={})
    without_positions = _graph.normalize_graph_inputs(["a"], [])
    with pytest.raises(ValueError, match="require explicit x and y"):
        _graph.run_layout(without_positions, layout="cose", pinned=[True])
    outside_bounds = _graph.normalize_graph_inputs(["a"], [], x=[2.0], y=[0.0])
    with pytest.raises(ValueError, match="native graph_force_create failed"):
        _graph.run_layout(
            outside_bounds,
            layout="cose",
            pinned=[True],
            cose={"bounds": (-1.0, -1.0, 1.0, 1.0)},
        )
    with pytest.raises(ValueError, match="iterations > 0"):
        _graph.run_layout(data, layout="cose", iterations=0, cose={})


@pytest.mark.parametrize(
    "layout",
    [
        "force",
        "fr",
        "spring",
        "forceatlas2",
        "fa2",
        "linlog",
        "yifanhu",
        "kamada_kawai",
        "kk",
        "stress",
        "barnes_hut",
        "cose",
    ],
)
def test_force_layout_catalog_seeded(layout):
    data = _graph.normalize_graph_inputs(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
    x1, y1, m1 = _graph.run_layout(data, layout=layout, seed=11, iterations=25)
    x2, y2, m2 = _graph.run_layout(data, layout=layout, seed=11, iterations=25)
    assert m1["layout"] == layout
    np.testing.assert_allclose(x1, x2)
    np.testing.assert_allclose(y1, y2)
    assert m1["alpha"] == pytest.approx(m2["alpha"])


def test_force_layout_aliases_match_ids():
    assert _native.graph_layout_id("fr") == _native.GRAPH_LAYOUT_FORCE
    assert _native.graph_layout_id("fa2") == _native.GRAPH_LAYOUT_FORCEATLAS2
    assert _native.graph_layout_id("kk") == _native.GRAPH_LAYOUT_KAMADA_KAWAI
    assert _native.graph_layout_id("spring") == _native.GRAPH_LAYOUT_SPRING
    assert _native.graph_layout_id("stress") == _native.GRAPH_LAYOUT_STRESS
    assert _native.graph_layout_id("yifanhu") == _native.GRAPH_LAYOUT_YIFANHU
    assert _native.graph_layout_id("linlog") == _native.GRAPH_LAYOUT_LINLOG
    assert _native.graph_layout_id("cose") == _native.GRAPH_LAYOUT_COSE
    assert _native.graph_is_progressive_force("spring")
    assert _native.graph_is_progressive_force("forceatlas2")
    assert _native.graph_is_progressive_force("cose")


def test_tiny_force_golden_stable():
    data = _graph.normalize_graph_inputs(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
    x, y, meta = _graph.run_layout(data, layout="force", seed=7, iterations=20)
    assert meta["layout"] == "force"
    assert np.isfinite(x).all() and np.isfinite(y).all()
    # Bit-stable across hosts for the exact FR path.
    x2, y2, _ = _graph.run_layout(data, layout="force", seed=7, iterations=20)
    np.testing.assert_array_equal(x, x2)
    np.testing.assert_array_equal(y, y2)


def test_graph_chart_emits_segments_scatter_and_meta():
    chart = xyg.graph_chart(
        xyg.graph(["n0", "n1", "n2"], [("n0", "n1"), ("n1", "n2")], layout="grid"),
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


def test_graph_chart_exposes_cose_options_and_pin_column_ergonomically():
    chart = xyg.graph_chart(
        xyg.graph(
            {"id": ["a", "b"], "fixed": [True, False]},
            [("a", "b")],
            x=[-0.5, 0.5],
            y=[0.0, 0.0],
            layout="cose",
            pinned="fixed",
            cose={"ideal_edge_length": 0.4, "bounds": (-1, -1, 1, 1)},
            iterations=10,
        )
    )
    fig = chart.figure()
    node_trace = next(trace for trace in fig.traces if trace.kind == "scatter")
    assert node_trace.x.values[0] == -0.5
    assert node_trace.y.values[0] == 0.0


def test_figure_graph_fluent():
    fig = Figure().graph(["a", "b"], [("a", "b")], layout="breadthfirst", directed=False)
    assert fig._graph_meta[0]["layout"] == "breadthfirst"
    assert len(fig.traces) == 2


def test_hierarchical_alias_is_distinct_from_breadthfirst():
    assert _native.graph_layout_id("hierarchical") == _native.GRAPH_LAYOUT_HIERARCHICAL
    assert _native.graph_layout_id("dagre") == _native.GRAPH_LAYOUT_HIERARCHICAL
    assert _native.GRAPH_LAYOUT_HIERARCHICAL != _native.GRAPH_LAYOUT_BREADTHFIRST


def test_lod_decision_records_edge_sample():
    tier, kept = _native.graph_lod_decision(100, 10_000, node_budget=50_000, edge_budget=1_000)
    assert tier == 1
    assert kept == 1_000


def test_lod_decision_scale_classes_10m_100m_1b():
    """Scatter-class graph scale evidence: budgets stay screen-bounded."""
    node_budget = 50_000
    edge_budget = 100_000
    for n in (10_000_000, 100_000_000, 1_000_000_000):
        tier, kept = _native.graph_lod_decision(
            n, n * 2, node_budget=node_budget, edge_budget=edge_budget
        )
        assert tier >= 1
        assert kept <= edge_budget


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
    assert hasattr(xyg, "graph")
    assert hasattr(xyg, "graph_chart")
    assert callable(xyg.graph)
    assert callable(xyg.graph_chart)


def test_from_graphforge_tables():
    nodes = {
        "node_uuid": [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ],
        "labels": ["Airport", "Airport"],
        "provenance_row": [4, 8],
    }
    edges = {
        "edge_uuid": ["10000000-0000-0000-0000-000000000001"],
        "src_uuid": ["00000000-0000-0000-0000-000000000001"],
        "dst_uuid": ["00000000-0000-0000-0000-000000000002"],
        "relationship_type": ["ROUTE"],
        "provenance_row": [12],
    }
    data = _graph.from_graphforge_tables(nodes, edges)
    assert data.n_nodes == 2
    assert data.n_edges == 1
    assert data.node_uuid_bytes.shape == (2, 16)
    assert data.edge_uuid_bytes.shape == (1, 16)
    assert data.edge_ids == ["10000000-0000-0000-0000-000000000001"]
    assert data.node_attrs["labels"].tolist() == ["Airport", "Airport"]
    assert data.edge_attrs["relationship_type"].tolist() == ["ROUTE"]
    np.testing.assert_array_equal(data.node_provenance_rows, [4, 8])
    np.testing.assert_array_equal(data.edge_provenance_rows, [12])


def test_from_graphforge_tables_uses_native_dense_mapping_and_parents():
    nodes = {
        "node_uuid": [
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000001",
        ],
        "parent_uuid": [None, "00000000-0000-0000-0000-000000000002"],
    }
    edges = {
        "edge_uuid": ["10000000-0000-0000-0000-000000000001"],
        "src_uuid": ["00000000-0000-0000-0000-000000000001"],
        "dst_uuid": ["00000000-0000-0000-0000-000000000002"],
    }
    data = xyg.from_graphforge_tables(nodes, edges, directed=False)
    np.testing.assert_array_equal(data.sources, [1])
    np.testing.assert_array_equal(data.targets, [0])
    np.testing.assert_array_equal(data.parent_indices, [0, 0])
    np.testing.assert_array_equal(data.parent_validity, [0, 1])
    assert data.directed is False


def test_from_graphforge_tables_rejects_nil_uuid_in_native_core():
    nodes = {"node_uuid": ["00000000-0000-0000-0000-000000000000"]}
    edges = {"edge_uuid": [], "src_uuid": [], "dst_uuid": []}
    with pytest.raises(_graph.GraphProjectionError) as exc:
        _graph.from_graphforge_tables(nodes, edges)
    assert exc.value.code == "GF_GRAPH_UUID_INVALID"


def test_from_graphforge_tables_reports_native_duplicate_identity_code():
    duplicate = "00000000-0000-0000-0000-000000000001"
    nodes = {"node_uuid": [duplicate, duplicate]}
    edges = {"edge_uuid": [], "src_uuid": [], "dst_uuid": []}
    with pytest.raises(_graph.GraphProjectionError) as exc:
        _graph.from_graphforge_tables(nodes, edges)
    assert exc.value.code == "GF_GRAPH_NODE_DUPLICATE"


def test_native_projection_destroy_rejects_stale_handle():
    node_ids = np.array([[1] * 16], dtype=np.uint8)
    empty = np.empty((0, 16), dtype=np.uint8)
    handle = _native.graph_projection_create(node_ids, empty, empty, empty)
    _native.graph_projection_destroy(handle)
    with pytest.raises(_native.GraphProjectionNativeError) as exc:
        _native.graph_projection_destroy(handle)
    assert exc.value.status == -7


def test_from_graphforge_tables_rejects_missing_endpoint_with_stable_code():
    nodes = {"node_uuid": ["00000000-0000-0000-0000-000000000001"]}
    edges = {
        "edge_uuid": ["10000000-0000-0000-0000-000000000001"],
        "source_uuid": ["00000000-0000-0000-0000-000000000001"],
        "target_uuid": ["00000000-0000-0000-0000-000000000002"],
    }
    with pytest.raises(_graph.GraphProjectionError) as exc:
        _graph.from_graphforge_tables(nodes, edges)
    assert exc.value.code == "GF_GRAPH_ENDPOINT_MISSING"
    assert exc.value.field == "target_uuid"
    assert exc.value.row == 0


def test_from_graphforge_tables_rejects_ambiguous_endpoint_columns():
    nodes = {"node_uuid": ["00000000-0000-0000-0000-000000000001"]}
    edges = {
        "edge_uuid": ["10000000-0000-0000-0000-000000000001"],
        "src_uuid": ["00000000-0000-0000-0000-000000000001"],
        "source_uuid": ["00000000-0000-0000-0000-000000000001"],
        "dst_uuid": ["00000000-0000-0000-0000-000000000001"],
    }
    with pytest.raises(_graph.GraphProjectionError) as exc:
        _graph.from_graphforge_tables(nodes, edges)
    assert exc.value.code == "GF_GRAPH_FIELD_AMBIGUOUS"


def test_build_render_respects_budgets():
    x = np.array([0.0, 1.0, 0.0, 100.0, 101.0, 100.0], dtype=np.float64)
    y = np.array([0.0, 0.0, 1.0, 100.0, 100.0, 101.0], dtype=np.float64)
    sources = np.array([0, 1, 3, 4, 0], dtype=np.uint64)
    targets = np.array([1, 2, 4, 5, 3], dtype=np.uint64)
    rx, ry, member_of, es, et, tier, kept = _native.graph_build_render(
        x, y, sources, targets, node_budget=2, edge_budget=4
    )
    assert tier == 2
    assert len(rx) <= 2
    assert len(es) <= 4
    assert kept == len(es)
    np.testing.assert_array_equal(member_of, [0, 0, 0, 1, 1, 1])


def test_run_layout_emits_render_graph_meta():
    data = _graph.normalize_graph_inputs(
        [f"n{i}" for i in range(6)],
        [("n0", "n1"), ("n1", "n2"), ("n3", "n4"), ("n4", "n5"), ("n0", "n3")],
    )
    # Preset positions so clustering is deterministic without force.
    data.x = np.array([0.0, 1.0, 0.0, 100.0, 101.0, 100.0], dtype=np.float64)
    data.y = np.array([0.0, 0.0, 1.0, 100.0, 100.0, 101.0], dtype=np.float64)
    rx, ry, meta = _graph.run_layout(data, layout="preset", node_budget=2, edge_budget=4)
    assert meta["source_n_nodes"] == 6
    assert meta["source_n_edges"] == 5
    assert meta["n_nodes"] <= 2
    assert meta["n_edges"] <= 4
    assert len(rx) == meta["n_nodes"]
    assert "member_of" in meta
    assert len(meta["member_of"]) == 6
    assert meta["lod_tier"] == 2
