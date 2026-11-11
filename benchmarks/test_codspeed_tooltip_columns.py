"""Typed graph-hover encoding; fixture construction is outside measurement.

Run through CodSpeed. These rows isolate transport encoding, not notebook
startup, layout, GPU paint, request latency or whole-graph acceptance.
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest

from xyg import kernels
from xyg._payload_writer import PayloadWriter
from xyg._tooltip_columns import encode_tooltip_rows


@pytest.fixture(scope="module", params=[1_000, 10_000, 100_000], ids=lambda n: f"nodes-{n}")
def graph_tooltips(request):
    assert kernels.BACKEND == "native"
    n = request.param
    node_ids = [f"0199c82c-c000-7100-8000-{i:012x}" for i in range(n)]
    edge_ids = [f"0199c82c-c000-7200-8000-{i:012x}" for i in range(2 * n)]
    node_bytes = [uuid.UUID(value).bytes for value in node_ids]
    edge_bytes = [uuid.UUID(value).bytes for value in edge_ids]
    return {
        "nodes": [{"id": value, "provenance_row": i} for i, value in enumerate(node_ids)],
        "edges": [
            {
                "source": node_ids[i % n],
                "target": node_ids[(i + 1) % n],
                "edge_id": value,
                "provenance_row": i,
            }
            for i, value in enumerate(edge_ids)
        ],
        "node_planes": [b"".join(node_bytes)],
        "edge_planes": [
            b"".join(node_bytes[i % n] for i in range(2 * n)),
            b"".join(node_bytes[(i + 1) % n] for i in range(2 * n)),
            b"".join(edge_bytes),
        ],
    }


def _encode(rows):
    writer = PayloadWriter(split=True)
    entry = encode_tooltip_rows(rows, writer)
    return entry, writer.columns, writer.buffers()


def _assert_planes(encoded, n, keys, planes):
    entry, columns, buffers = encoded
    assert entry == {
        "n": n,
        "keys": keys,
        "kinds": ["uuid"] * len(planes) + ["f64"],
        "data": list(range(len(keys))),
        "present": [None] * len(keys),
        "dict": [],
    }
    expected = [*planes, np.arange(n, dtype="<f8").tobytes()]
    for index, raw in enumerate(expected):
        column = columns[index]
        assert column["dtype"] == "u8" and column["len"] == len(raw)
        assert bytes(buffers[column["buf"]]) == raw


def test_tooltip_nodes_uuid_columns(benchmark, graph_tooltips):
    rows = graph_tooltips["nodes"]
    encoded = benchmark(_encode, rows)
    _assert_planes(encoded, len(rows), ["id", "provenance_row"], graph_tooltips["node_planes"])


def test_tooltip_edges_uuid_columns(benchmark, graph_tooltips):
    rows = graph_tooltips["edges"]
    encoded = benchmark(_encode, rows)
    _assert_planes(
        encoded,
        len(rows),
        ["source", "target", "edge_id", "provenance_row"],
        graph_tooltips["edge_planes"],
    )
