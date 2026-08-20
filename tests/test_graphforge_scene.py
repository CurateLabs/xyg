"""GraphForge scene ingest — IPC fixtures, tooltips, typed-vs-JSON evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import xyg
from xyg import _graph
from xyg._figure import Figure

pytest.importorskip("pyarrow")
import pyarrow as pa  # noqa: E402
import pyarrow.ipc as pa_ipc  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "graphforge"


def _load_arrow(name: str) -> pa.Table:
    path = FIXTURES / name
    with pa.memory_map(str(path), "r") as source:
        return pa_ipc.open_file(source).read_all()


def _airports_tables():
    return _load_arrow("airports_nodes.arrow"), _load_arrow("airports_edges.arrow")


def test_graphforge_ipc_preserves_parallel_edge_identity_and_node_tooltips():
    nodes, edges = _airports_tables()
    data = xyg.from_graphforge_tables(nodes, edges)
    assert data.n_edges == 4
    assert len(set(data.edge_ids)) == 4

    fig = Figure().graph(nodes, edges, layout="grid", seed=1)
    assert len(fig.traces) == 2
    edge_trace, node_trace = fig.traces
    assert edge_trace.kind == "segments"
    assert node_trace.kind == "scatter"
    # Nodes stay 1:1 under default budgets → node tooltip_rows on the scatter.
    assert node_trace.tooltip_rows is not None
    assert len(node_trace.tooltip_rows) == 3
    assert node_trace.tooltip_rows[0]["labels"] == "Airport"
    assert node_trace.tooltip_rows[0]["provenance_row"] == 10
    meta = fig._graph_meta[0]
    assert meta["source_edge_ids"] is not None
    assert len(meta["source_edge_ids"]) == 4
    assert len(set(meta["source_edge_ids"])) == 4
    if len(meta["sources"]) == data.n_edges:
        assert meta["edge_ids"] == meta["source_edge_ids"]
    else:
        assert "edge_ids" not in meta
    assert meta["node_provenance_rows"] == [10, 11, 12]
    assert meta["edge_provenance_rows"] == [100, 101, 102, 103]
    # Direct tier keeps all four GraphForge edges; routing expands loops/arrows.
    assert len(meta["sources"]) == 4
    assert meta["edge_ids"] == meta["source_edge_ids"]
    assert edge_trace.tooltip_rows is not None
    assert len(edge_trace.tooltip_rows) == len(meta["render_edge_index"])
    assert {row["edge_id"] for row in edge_trace.tooltip_rows} == set(meta["source_edge_ids"])
    assert any(row["relationship_type"] == "SELF" for row in edge_trace.tooltip_rows)
    spec, blob = fig.build_payload()
    assert "tooltip_rows" in spec["traces"][1]
    assert isinstance(blob, (bytes, memoryview, bytearray))


def test_graphforge_simple_path_ships_edge_tooltips_on_trace():
    """No parallel edges / self-loops → Direct render keeps edge tooltip_rows."""
    nodes = {
        "node_uuid": [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000003",
        ],
        "labels": ["A", "B", "C"],
        "provenance_row": [1, 2, 3],
    }
    edges = {
        "edge_uuid": [
            "10000000-0000-0000-0000-000000000001",
            "10000000-0000-0000-0000-000000000002",
        ],
        "src_uuid": [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ],
        "dst_uuid": [
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000003",
        ],
        "relationship_type": ["ROUTE", "SERVES"],
        "provenance_row": [10, 11],
    }
    fig = Figure().graph(nodes, edges, layout="grid", seed=1)
    edge_trace = fig.traces[0]
    meta = fig._graph_meta[0]
    assert edge_trace.tooltip_rows is not None
    # Directed routing expands each edge into shaft + arrow wings.
    assert len(edge_trace.tooltip_rows) == len(meta["render_edge_index"]) == 6
    assert edge_trace.tooltip_rows[0]["relationship_type"] == "ROUTE"
    assert {row["edge_id"] for row in edge_trace.tooltip_rows} == set(meta["edge_ids"])


def test_graphforge_graphdata_passthrough_and_column_encoding():
    nodes, edges = _airports_tables()
    data = xyg.from_graphforge_tables(nodes, edges)
    fig = Figure().graph(data, layout="circle", seed=2, size="rank", color="rank")
    node_trace = fig.traces[-1]
    assert node_trace.size_ch is not None
    assert node_trace.color_ch is not None
    spec, _ = fig.build_payload()
    assert spec["traces"][1]["size"]["mode"] == "continuous"
    assert spec["traces"][1]["color"]["mode"] == "continuous"


def test_graphforge_ipc_missing_endpoint_fails_before_paint():
    nodes = _load_arrow("airports_nodes.arrow")
    edges = _load_arrow("airports_edges_missing_endpoint.arrow")
    with pytest.raises(_graph.GraphProjectionError, match="GF_GRAPH_ENDPOINT_MISSING"):
        Figure().graph(nodes, edges, layout="grid")


def test_graphforge_ipc_duplicate_edge_fails_before_paint():
    nodes = _load_arrow("airports_nodes.arrow")
    edges = _load_arrow("airports_edges_duplicate_edge.arrow")
    with pytest.raises(_graph.GraphProjectionError, match="GF_GRAPH_EDGE_DUPLICATE"):
        Figure().graph(nodes, edges, layout="grid")


def test_graphforge_typed_path_beats_json_row_bridge_memory():
    """Typed Arrow columns should ship the same §29 paint payload as JSON rematerialization."""
    nodes, edges = _airports_tables()

    def typed_payload_bytes() -> int:
        fig = Figure().graph(nodes, edges, layout="grid", seed=1)
        _spec, blob = fig.build_payload()
        return len(blob)

    def json_bridge_payload_bytes() -> int:
        node_rows = nodes.to_pylist()
        edge_rows = edges.to_pylist()
        node_table = {key: [row[key] for row in node_rows] for key in node_rows[0]}
        edge_table = {key: [row[key] for row in edge_rows] for key in edge_rows[0]}
        node_table = json.loads(json.dumps(node_table))
        edge_table = json.loads(json.dumps(edge_table))
        fig = Figure().graph(node_table, edge_table, layout="grid", seed=1)
        _spec, blob = fig.build_payload()
        return len(blob)

    typed = typed_payload_bytes()
    bridged = json_bridge_payload_bytes()
    assert typed == bridged
    assert typed > 0


def test_looks_like_graphforge_tables():
    nodes, edges = _airports_tables()
    assert _graph.looks_like_graphforge_tables(nodes, edges)
    assert not _graph.looks_like_graphforge_tables(["a", "b"], [("a", "b")])
    mapped_nodes = {
        "id": [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ],
    }
    mapped_edges = {
        "eid": ["10000000-0000-0000-0000-000000000001"],
        "src": ["00000000-0000-0000-0000-000000000001"],
        "dst": ["00000000-0000-0000-0000-000000000002"],
    }
    mapping = {
        "node_uuid": "id",
        "edge_uuid": "eid",
        "source_uuid": "src",
        "target_uuid": "dst",
    }
    assert _graph.looks_like_graphforge_tables(mapped_nodes, mapped_edges, mapping)
    data = _graph.resolve_graph_data(mapped_nodes, mapped_edges, mapping=mapping)
    assert data.n_nodes == 2
    assert data.n_edges == 1


def test_projection_tooltip_rows_preserve_large_integers_as_strings():
    nodes = {
        "node_uuid": [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ],
        "big": [9_007_199_254_740_993, 1],
    }
    edges = {
        "edge_uuid": ["10000000-0000-0000-0000-000000000001"],
        "src_uuid": ["00000000-0000-0000-0000-000000000001"],
        "dst_uuid": ["00000000-0000-0000-0000-000000000002"],
    }
    data = xyg.from_graphforge_tables(nodes, edges)
    node_rows, _edge_rows = _graph.projection_tooltip_rows(data)
    assert node_rows is not None
    assert node_rows[0]["big"] == "9007199254740993"


def test_resolve_graph_data_rejects_mismatched_preset_y():
    nodes = {
        "node_uuid": [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ],
    }
    edges = {
        "edge_uuid": ["10000000-0000-0000-0000-000000000001"],
        "src_uuid": ["00000000-0000-0000-0000-000000000001"],
        "dst_uuid": ["00000000-0000-0000-0000-000000000002"],
    }
    with pytest.raises(ValueError, match="x/y must match node count"):
        _graph.resolve_graph_data(nodes, edges, x=[0.0, 1.0], y=[0.0])
