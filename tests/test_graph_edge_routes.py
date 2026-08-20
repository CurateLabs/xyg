"""Directed multigraph edge routing — Direct LOD identity + geometry (#33)."""

from __future__ import annotations

import numpy as np

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
