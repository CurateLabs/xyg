"""Directed multigraph edge routing — Direct LOD identity + geometry (#33)."""

from __future__ import annotations

import numpy as np
import pytest

from xyg import _native
from xyg._figure import Figure


def test_direct_build_render_keeps_parallels_and_self_loops():
    x = np.array([0.0, 1.0, 2.0], dtype=np.float64)
    y = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    sources = np.array([0, 0, 1, 2], dtype=np.uint64)
    targets = np.array([1, 1, 2, 2], dtype=np.uint64)
    rx, ry, member, es, et, tier, kept = _native.graph_build_render(
        x, y, sources, targets, node_budget=100, edge_budget=100
    )
    assert tier == 0
    assert kept == 4
    assert len(es) == 4
    assert list(es) == [0, 0, 1, 2]
    assert list(et) == [1, 1, 2, 2]
    assert len(rx) == 3
    assert list(member) == [0, 1, 2]


def test_edge_route_separates_parallels_and_maps_source_index():
    x = np.array([0.0, 2.0, 4.0], dtype=np.float64)
    y = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    sources = np.array([0, 0, 2], dtype=np.uint64)
    targets = np.array([1, 1, 2], dtype=np.uint64)
    x0, y0, x1, y1, eidx = _native.graph_edge_route_segments(
        x, y, sources, targets, directed=True, separation=0.2, loop_radius=0.5, arrow_size=0.15
    )
    assert len(x0) == len(y0) == len(x1) == len(y1) == len(eidx) == 9
    assert abs(float(y0[0]) - float(y0[3])) > 1e-9
    assert int((eidx == 2).sum()) == 3


def test_edge_route_curved_bows_off_the_chord_and_stays_deterministic():
    x = np.array([0.0, 4.0], dtype=np.float64)
    y = np.array([0.0, 0.0], dtype=np.float64)
    sources = np.array([0], dtype=np.uint64)
    targets = np.array([1], dtype=np.uint64)
    x0, y0, x1, y1, eidx = _native.graph_edge_route_segments(
        x, y, sources, targets, directed=True, separation=0.08, arrow_size=0.12, curved=True
    )
    # CURVE_TESSELLATION_SEGMENTS (8) shaft pieces + 2 arrow wings.
    assert len(x0) == 10
    assert list(eidx) == [0] * 10
    # The mid-shaft segment must leave the straight x-axis chord.
    assert abs(float(y0[4])) > 1e-6
    x0b, y0b, x1b, y1b, eidxb = _native.graph_edge_route_segments(
        x, y, sources, targets, directed=True, separation=0.08, arrow_size=0.12, curved=True
    )
    np.testing.assert_array_equal(x0, x0b)
    np.testing.assert_array_equal(y0, y0b)
    np.testing.assert_array_equal(eidx, eidxb)


def test_graph_mark_edge_curve_curve_routes_bowed_segments():
    nodes = ["a", "b"]
    edges = [("a", "b"), ("b", "a")]
    straight = Figure().graph(nodes, edges, layout="preset", x=[0.0, 4.0], y=[0.0, 0.0])
    curved = Figure().graph(
        nodes, edges, layout="preset", x=[0.0, 4.0], y=[0.0, 0.0], edge_curve="curve"
    )
    straight_meta = straight._graph_meta[0]
    curved_meta = curved._graph_meta[0]
    assert straight_meta["edge_curve"] == "straight"
    assert curved_meta["edge_curve"] == "curve"
    straight_edges = straight.traces[0]
    curved_edges = curved.traces[0]
    # Curved reciprocal edges tessellate into more paint segments than the
    # straight+arrow routing of the same two-edge reciprocal pair.
    assert len(curved_edges.x0) > len(straight_edges.x0)
    # Stable identity survives the extra tessellation.
    assert curved_meta["render_edge_index"].count(0) > 1
    assert curved_meta["render_edge_index"].count(1) > 1


def test_graph_mark_edge_curve_rejects_unknown_values():
    with pytest.raises(ValueError, match="edge_curve"):
        Figure().graph(["a", "b"], [("a", "b")], layout="grid", edge_curve="bogus")


def test_graph_mark_paints_routed_multigraph_with_stable_edge_ids():
    nodes = {
        "node_uuid": [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000003",
        ],
        "labels": ["A", "B", "C"],
    }
    edges = {
        "edge_uuid": [
            "10000000-0000-0000-0000-000000000001",
            "10000000-0000-0000-0000-000000000002",
            "10000000-0000-0000-0000-000000000003",
            "10000000-0000-0000-0000-000000000004",
        ],
        "src_uuid": [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000003",
        ],
        "dst_uuid": [
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000003",
            "00000000-0000-0000-0000-000000000003",
        ],
        "relationship_type": ["ROUTE", "ROUTE", "SERVES", "SELF"],
    }
    fig = Figure().graph(nodes, edges, layout="grid", seed=1)
    meta = fig._graph_meta[0]
    assert meta["lod_tier"] == 0
    assert len(meta["sources"]) == 4
    assert meta["edge_ids"] == meta["source_edge_ids"]
    assert len(meta["render_edge_index"]) >= 4
    edge_trace = fig.traces[0]
    assert edge_trace.kind == "segments"
    assert len(edge_trace.x0) == len(meta["render_edge_index"])
