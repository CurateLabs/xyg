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
from pathlib import Path
from typing import Any

import numpy as np

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
    ],
    "non_finite_and_bools": [
        {"value": float("nan"), "flag": True, "label": "naïve ☃"},
        {"value": float("inf"), "flag": False, "label": ""},
        {"value": -0.5, "flag": None, "label": "x"},
    ],
    "only_nulls": [{"a": None}, {"a": None}],
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


def test_python_matches_fixture() -> None:
    produced = {name: _encode(rows) for name, rows in CASES.items()}
    if os.environ.get("XYG_REGEN_TOOLTIP_COLUMNS"):
        cases = {name: {"rows": rows, **produced[name]} for name, rows in CASES.items()}
        # NaN/inf rows are rebuilt from names in the Node test; store them as strings.
        text = json.dumps(
            {"schema": "xyg.tooltip-columns-cross-host/v1", "cases": cases},
            indent=2,
            allow_nan=True,
        )
        FIXTURE.write_text(text.replace("NaN", '"NaN"').replace("Infinity", '"Infinity"') + "\n")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["schema"] == "xyg.tooltip-columns-cross-host/v1"
    for name, expected in fixture["cases"].items():
        assert produced[name]["tooltip_columns"] == expected["tooltip_columns"], name
        assert produced[name]["shipped"] == expected["shipped"], name


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
