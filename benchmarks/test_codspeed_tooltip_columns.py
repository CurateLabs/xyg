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


class _LabelText(str):
    pass


@pytest.fixture(scope="module", params=[1, 8, 1_000, 100_000], ids=lambda n: f"rows-{n}")
def scalar_count(request):
    return request.param


@pytest.fixture(
    scope="module",
    params=[
        "numeric",
        "bool",
        "null",
        "text",
        "npstr",
        "subclass",
        "sparse",
        "late-fallback",
        "npstr-uuid",
        "subclass-uuid",
        "mixed-npstr-uuid",
        "mixed-subclass-uuid",
        "null-heavy-uuid",
        "missing-heavy-uuid",
    ],
)
def scalar_tooltips(request, scalar_count):
    n = scalar_count
    kind = request.param
    if kind == "numeric":
        rows = [{"x": i / 7, "i": i} for i in range(n)]
        meta = dict(
            n=n, keys=["x", "i"], kinds=["f64", "f64"], data=[0, 1], present=[None, None], dict=[]
        )
        planes = [
            ("u8", np.asarray([i / 7 for i in range(n)], dtype="<f8").tobytes()),
            ("u8", np.arange(n, dtype="<f8").tobytes()),
        ]
    elif kind == "bool":
        rows = [{"b": bool(i % 2), "np": np.bool_(i % 3)} for i in range(n)]
        meta = dict(
            n=n,
            keys=["b", "np"],
            kinds=["bool", "bool"],
            data=[0, 1],
            present=[None, None],
            dict=[],
        )
        planes = [
            ("u8", bytes(i % 2 for i in range(n))),
            ("u8", bytes(bool(i % 3) for i in range(n))),
        ]
    elif kind == "null":
        rows = [{"x": None} for _ in range(n)]
        meta = dict(n=n, keys=["x"], kinds=["bool"], data=[1], present=[0], dict=[])
        planes = [("u8", bytes([1]) * n), ("u8", bytes(n))]
    elif kind == "late-fallback":
        rows = [{"text": f"label-{i % 17}"} for i in range(n)]
        rows[-1]["text"] = 2**54
        meta, planes = None, []
    elif kind.endswith("-uuid"):
        text = "0199c82c-c000-7100-8000-000000000001"
        if "heavy" in kind:
            null = kind.startswith("null-")
            rows = [{"text": text}] + (
                [{"text": None} for _ in range(n - 1)] if null else [{} for _ in range(n - 1)]
            )
            presence = bytes([2]) + bytes([1 if null else 0]) * (n - 1)
            planes = ([] if n == 1 else [("u8", presence)]) + [
                ("u8", uuid.UUID(text).bytes + bytes(16 * (n - 1)))
            ]
            meta = dict(
                n=n,
                keys=["text"],
                kinds=["uuid"],
                data=[0 if n == 1 else 1],
                present=[None if n == 1 else 0],
                dict=[],
            )
        else:
            cls = np.str_ if "npstr" in kind else _LabelText
            rows = [{"text": cls(text)} for _ in range(n)]
            if kind.startswith("mixed-"):
                rows[0]["text"] = text
            meta = dict(n=n, keys=["text"], kinds=["uuid"], data=[0], present=[None], dict=[])
            planes = [("u8", uuid.UUID(text).bytes * n)]
    else:
        cls = np.str_ if kind == "npstr" else _LabelText if kind == "subclass" else str
        labels = [cls(f"label-{i % 17}") for i in range(n)]
        if kind == "sparse":
            labels = [None if i % 5 == 0 or i % 7 == 0 else value for i, value in enumerate(labels)]
            rows = [{} if i % 5 == 0 else {"text": value} for i, value in enumerate(labels)]
            presence = bytes(
                0 if i % 5 == 0 else 1 if value is None else 2 for i, value in enumerate(labels)
            )
        else:
            rows = [{"text": value} for value in labels]
            presence = None
        dictionary = list(dict.fromkeys(str(value) for value in labels if value is not None))
        indices = np.asarray(
            [dictionary.index(value) if value is not None else 0 for value in labels], dtype="<u4"
        ).tobytes()
        meta = dict(
            n=n,
            keys=["text"],
            kinds=["text"],
            data=[1 if presence is not None else 0],
            present=[0 if presence is not None else None],
            dict=dictionary,
        )
        planes = ([] if presence is None else [("u8", presence)]) + [("u32", indices)]
        if not any("text" in row for row in rows):
            meta = dict(n=n, keys=[], kinds=[], data=[], present=[], dict=[])
            planes = []
    return rows, meta, planes, repr(rows)


def test_tooltip_scalar_columns(benchmark, scalar_tooltips):
    rows, expected, planes, before = scalar_tooltips
    entry, columns, buffers = benchmark(_encode, rows)
    assert entry == expected
    assert len(columns) == len(planes)
    for column, (dtype, raw) in zip(columns, planes, strict=True):
        assert column["dtype"] == dtype
        assert column["byte_offset"] == 0
        assert column["len"] == len(raw) // (4 if dtype == "u32" else 1)
        assert bytes(buffers[column["buf"]]) == raw + bytes((-len(raw)) % 4)
    assert repr(rows) == before
