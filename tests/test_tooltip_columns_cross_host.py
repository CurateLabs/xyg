"""Tooltip columns are one encoding in both hosts (graph-mark.md §2).

`tests/fixtures/tooltip_columns_cross_host.json` pins, per case, the
`tooltip_columns` entry and the bytes of every column it ships (or `null` when
the rows keep the JSON form). Python must reproduce it here and Node in
`packages/xy-node/test/tooltip-columns-cross-host.test.mjs`. Regenerate with
`XYG_REGEN_TOOLTIP_COLUMNS=1 uv run pytest tests/test_tooltip_columns_cross_host.py`.
"""

from __future__ import annotations

import json
import os
import struct
import uuid
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from xyg._graph_wire import wire_graph_meta
from xyg._tooltip_columns import encode_tooltip_rows

FIXTURE = Path(__file__).parent / "fixtures" / "tooltip_columns_cross_host.json"
U1 = "01a0f3fd-23dd-76d3-87e7-d765a3665ef5"
U2 = "01a0f3fd-23e2-76c3-b1d4-c2aadc972cc9"

CASES: dict[str, list[dict[str, Any]]] = {
    "graph_nodes": [
        {"id": U1, "provenance_row": 0, "name": "ann", "type": "Person", "pagerank.score": 0.25},
        {"id": U2, "provenance_row": 1, "type": "Person", "pagerank.score": None},
        {"id": U1, "provenance_row": 2, "name": "ann", "type": "Place", "pagerank.score": 1e-300},
    ],
    "graph_edges_with_aggregates": [
        {"source": U1, "target": U2, "edge_id": U2, "provenance_row": 7},
        {"edge_count": 12},
        {"source": U2, "target": U1, "edge_id": None, "provenance_row": 9},
        {"source": U1, "target": U1, "edge_id": "derived:1:4:0", "provenance_row": 9},
    ],
    "non_finite_and_bools": [
        {"value": float("nan"), "flag": True, "label": "naïve ☃"},
        {"value": float("inf"), "flag": False, "label": ""},
        {"value": -0.5, "flag": None, "label": "x"},
    ],
    "only_nulls": [{"a": None}, {"a": None}],
    "proto_key": [{"__proto__": "a", "x": 1}, {"__proto__": "b", "x": 2}],
    "shared_dictionary": [
        {"name": "ann", "pagerank.name": "ann"},
        {"name": "bo", "pagerank.name": "bo"},
    ],
    "key_order_differs": [{"a": 1, "b": 2}, {"b": 3, "a": 4}],
    "mixed_kinds": [{"a": 1}, {"a": "x"}],
    "nested_value": [{"a": [1, 2]}],
    "empty": [],
}


class _Recorder:
    """A payload writer that records each shipped column's dtype and bytes."""

    def __init__(self) -> None:
        self.columns: list[dict[str, str]] = []

    def _ship(self, values: np.ndarray, dtype: str) -> int:
        self.columns.append({"dtype": dtype, "hex": values.tobytes().hex()})
        return len(self.columns) - 1

    def ship_u8(self, values: np.ndarray) -> int:
        return self._ship(np.ascontiguousarray(values, dtype=np.uint8).reshape(-1), "u8")

    def ship_u32(self, values: np.ndarray) -> int:
        return self._ship(np.ascontiguousarray(values, dtype="<u4").reshape(-1), "u32")


def _encode(rows: list[dict[str, Any]]) -> dict[str, Any]:
    recorder = _Recorder()
    columns = encode_tooltip_rows(rows, recorder)
    return {"tooltip_columns": columns, "shipped": recorder.columns if columns else []}


GRAPH_META = {
    "layout": "force",
    "ids": ["a", "b", "c"],
    "csr_offsets": [0, 2, 3, 4],
    "csr_neighbors": [1, 2, 0, 0],
    "node_labels": ["a", None, "c"],
    "label_accepted": [True, False, True],
    "visual_states": [0, 5, 7],
    "source_edge_ids": ["e0", "e1"],
    "compound_nodes": [False, False, True],
}


def _graph_meta() -> dict[str, Any]:
    recorder = _Recorder()
    return {"wire": wire_graph_meta(GRAPH_META, recorder), "shipped": recorder.columns}


def test_python_matches_fixture() -> None:
    produced = {name: _encode(rows) for name, rows in CASES.items()}
    if os.environ.get("XYG_REGEN_TOOLTIP_COLUMNS"):
        cases = {name: {"rows": rows, **produced[name]} for name, rows in CASES.items()}
        cases_meta = {"meta": GRAPH_META, **_graph_meta()}
        # NaN/inf rows are rebuilt from names in the Node test; store them as strings.
        text = json.dumps(
            {
                "schema": "xyg.tooltip-columns-cross-host/v1",
                "cases": cases,
                "graph_meta": cases_meta,
            },
            indent=2,
            allow_nan=True,
        )
        FIXTURE.write_text(text.replace("NaN", '"NaN"').replace("Infinity", '"Infinity"') + "\n")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["schema"] == "xyg.tooltip-columns-cross-host/v1"
    for name, expected in fixture["cases"].items():
        assert produced[name]["tooltip_columns"] == expected["tooltip_columns"], name
        assert produced[name]["shipped"] == expected["shipped"], name
    graph_meta = _graph_meta()
    assert graph_meta["wire"] == fixture["graph_meta"]["wire"]
    assert graph_meta["shipped"] == fixture["graph_meta"]["shipped"]
    # Host-only identity planes are dropped; browser integer planes are columns.
    assert "ids" not in graph_meta["wire"] and "source_edge_ids" not in graph_meta["wire"]
    assert graph_meta["wire"]["csr_offsets"] == {"column": 0}


@pytest.mark.parametrize("count", [1, 4095, 4096, 4097, 8193])
@pytest.mark.parametrize("container", [list, tuple, deque])
def test_uuid_planes_cross_copy_boundaries_without_changing_bytes(count, container) -> None:
    rows = [
        {"id": str(uuid.UUID(int=i + 1)), "value": -0.0 if i == 0 else i / 13} for i in range(count)
    ]
    encoded = _encode(container(rows))
    assert encoded["tooltip_columns"] == {
        "n": count,
        "keys": ["id", "value"],
        "kinds": ["uuid", "f64"],
        "data": [0, 1],
        "present": [None, None],
        "dict": [],
    }
    assert encoded["shipped"] == [
        {"dtype": "u8", "hex": b"".join((i + 1).to_bytes(16, "big") for i in range(count)).hex()},
        {"dtype": "u8", "hex": b"".join(struct.pack("<d", row["value"]) for row in rows).hex()},
    ]


def test_sparse_uuid_blocks_keep_presence_dictionary_order_and_zero_padding() -> None:
    n = 8195
    rows = [{"id": U1, "other": U2, "tag": "shared"} for _ in range(n)]
    del rows[4095]["id"]
    for i in range(4096, 8192):
        rows[i]["id"] = None
    rows[4097]["id"] = "shared"
    rows[8192]["id"] = "derived:1:4:0"
    rows[0]["other"] = "derived:1:4:0"
    rows[-1]["other"] = None
    before = json.dumps(rows)

    encoded = _encode(rows)
    assert json.dumps(rows) == before
    assert encoded["tooltip_columns"] == {
        "n": n,
        "keys": ["id", "other", "tag"],
        "kinds": ["uuid", "uuid", "text"],
        "data": [1, 3, 4],
        "present": [0, 2, None],
        "dict": ["shared", "derived:1:4:0"],
    }
    first = bytearray(uuid.UUID(U1).bytes * n)
    first[4095 * 16 : 8192 * 16] = bytes((8192 - 4095) * 16)
    first[8192 * 16 : 8193 * 16] = (1).to_bytes(4, "little") + bytes(12)
    first_presence = bytearray([2] * n)
    first_presence[4096:8192] = bytes([1] * 4096)
    for i, value in [(4095, 0), (4097, 3), (8192, 3)]:
        first_presence[i] = value
    second = bytearray(uuid.UUID(U2).bytes * n)
    second[:16] = (1).to_bytes(4, "little") + bytes(12)
    second[-16:] = bytes(16)
    second_presence = bytearray([2] * n)
    second_presence[0], second_presence[-1] = 3, 1
    expected = [first_presence, first, second_presence, second, bytes(n * 4)]
    assert encoded["shipped"] == [
        {"dtype": "u32" if i == 4 else "u8", "hex": raw.hex()} for i, raw in enumerate(expected)
    ]


def test_fixture_exercises_every_kind_and_the_json_fallback() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    kinds = {
        k
        for case in fixture.values()
        if case["tooltip_columns"]
        for k in case["tooltip_columns"]["kinds"]
    }
    assert kinds == {"uuid", "f64", "text", "bool"}
    assert [name for name, case in fixture.items() if case["tooltip_columns"] is None] == [
        "key_order_differs",
        "mixed_kinds",
        "nested_value",
        "empty",
    ]
