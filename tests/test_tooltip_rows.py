"""tooltip_rows payload contract — length check, selection filter, None omit."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from xyg._figure import Figure
from xyg._payload import PayloadMixin
from xyg._tooltip_columns import decode_tooltip_rows


def test_attach_tooltip_rows_none_is_noop():
    entry: dict = {}
    t = SimpleNamespace(kind="scatter", n_points=2, tooltip_rows=None)
    PayloadMixin._attach_tooltip_rows(entry, t, None)
    assert "tooltip_rows" not in entry


def test_attach_tooltip_rows_length_mismatch():
    entry: dict = {}
    t = SimpleNamespace(kind="scatter", n_points=2, tooltip_rows=[{"id": "a"}])
    with pytest.raises(ValueError, match="tooltip rows must match geometry"):
        PayloadMixin._attach_tooltip_rows(entry, t, None)


def test_attach_tooltip_rows_filters_with_selection():
    entry: dict = {}
    rows = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    t = SimpleNamespace(kind="scatter", n_points=3, tooltip_rows=rows)
    PayloadMixin._attach_tooltip_rows(entry, t, np.asarray([0, 2], dtype=np.intp))
    assert entry["tooltip_rows"] == [{"id": "a"}, {"id": "c"}]


def test_scatter_payload_ships_tooltip_rows():
    fig = Figure().scatter([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    fig.traces[-1].tooltip_rows = [{"rank": 1}, {"rank": 2}, {"rank": 3}]
    spec, blob = fig.build_payload()
    # Scalar rows ship as typed columns (graph-mark.md §2), never JSON numbers.
    assert "tooltip_rows" not in spec["traces"][0]
    assert spec["traces"][0]["tooltip_columns"]["kinds"] == ["f64"]
    assert decode_tooltip_rows(spec, blob, spec["traces"][0]) == [
        {"rank": 1},
        {"rank": 2},
        {"rank": 3},
    ]


def test_scatter_payload_omits_tooltip_rows_when_unset():
    fig = Figure().scatter([1.0], [1.0])
    spec, _blob = fig.build_payload()
    assert "tooltip_rows" not in spec["traces"][0]
    assert "tooltip_columns" not in spec["traces"][0]


def test_scatter_payload_rejects_tooltip_rows_length_mismatch():
    fig = Figure().scatter([1.0, 2.0], [1.0, 2.0])
    fig.traces[-1].tooltip_rows = [{"rank": 1}]
    with pytest.raises(ValueError, match="tooltip rows must match geometry"):
        fig.build_payload()


def test_scatter_payload_filters_tooltip_rows_with_nan_geometry():
    # Use an explicit NaN that the column zone maps as null so finite-row
    # selection drops that index and tooltip_rows follows.
    x = np.asarray([1.0, np.nan, 3.0], dtype=np.float64)
    y = np.asarray([1.0, 2.0, 3.0], dtype=np.float64)
    fig = Figure().scatter(x, y)
    fig.traces[-1].tooltip_rows = [{"i": 0}, {"i": 1}, {"i": 2}]
    assert fig.traces[-1].x.zone.null_count >= 1
    spec, blob = fig.build_payload()
    assert spec["traces"][0]["n_marks"] == 2
    assert decode_tooltip_rows(spec, blob, spec["traces"][0]) == [{"i": 0}, {"i": 2}]


def test_tooltip_columns_round_trip_every_kind_in_packed_and_split_payloads():
    rows = [
        {"id": "01a0f3fd-23dd-76d3-87e7-d765a3665ef5", "score": 0.5, "name": "a", "ok": True},
        {"id": None, "score": float("nan"), "ok": False},
        {"id": "01a0f3fd-23e2-76c3-b1d4-c2aadc972cc9", "score": -2, "name": "a"},
    ]
    fig = Figure().scatter([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    fig.traces[-1].tooltip_rows = rows
    expected = [
        {"id": rows[0]["id"], "score": 0.5, "name": "a", "ok": True},
        {"id": None, "score": None, "ok": False},
        {"id": rows[2]["id"], "score": -2.0, "name": "a"},
    ]
    spec, blob = fig.build_payload()
    columns = spec["traces"][0]["tooltip_columns"]
    assert columns["kinds"] == ["uuid", "f64", "text", "bool"]
    assert columns["dict"] == ["a"]
    assert decode_tooltip_rows(spec, blob, spec["traces"][0]) == expected
    spec, buffers = fig.build_payload_split()
    assert decode_tooltip_rows(spec, buffers, spec["traces"][0]) == expected


def test_rows_that_cannot_be_columns_stay_json():
    fig = Figure().scatter([1.0, 2.0], [1.0, 2.0])
    fig.traces[-1].tooltip_rows = [{"a": 1, "b": 2}, {"b": 3, "a": 4}]  # key order differs
    spec, _ = fig.build_payload()
    assert spec["traces"][0]["tooltip_rows"] == [{"a": 1, "b": 2}, {"b": 3, "a": 4}]
    fig.traces[-1].tooltip_rows = [{"a": [1]}, {"a": [2]}]  # not a scalar
    spec, _ = fig.build_payload()
    assert spec["traces"][0]["tooltip_rows"] == [{"a": [1]}, {"a": [2]}]
    fig.traces[-1].tooltip_rows = [{"a": 1}, {"a": "x"}]  # mixed kinds
    spec, _ = fig.build_payload()
    assert spec["traces"][0]["tooltip_rows"] == [{"a": 1}, {"a": "x"}]


def test_integers_beyond_f64_keep_json_rows():
    fig = Figure().scatter([1.0, 2.0], [1.0, 2.0])
    fig.traces[-1].tooltip_rows = [{"n": 2**53 + 1}, {"n": 1}]
    spec, _ = fig.build_payload()
    assert spec["traces"][0]["tooltip_rows"] == [{"n": 2**53 + 1}, {"n": 1}]
    fig.traces[-1].tooltip_rows = [{"n": 2**53}, {"n": -(2**53)}]  # exact in f64
    spec, blob = fig.build_payload()
    assert decode_tooltip_rows(spec, blob, spec["traces"][0]) == [{"n": 2**53}, {"n": -(2**53)}]
