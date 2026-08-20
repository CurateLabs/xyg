"""tooltip_rows payload contract — length check, selection filter, None omit."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from xy._figure import Figure
from xy._payload import PayloadMixin


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
    spec, _blob = fig.build_payload()
    assert spec["traces"][0]["tooltip_rows"] == [
        {"rank": 1},
        {"rank": 2},
        {"rank": 3},
    ]


def test_scatter_payload_omits_tooltip_rows_when_unset():
    fig = Figure().scatter([1.0], [1.0])
    spec, _blob = fig.build_payload()
    assert "tooltip_rows" not in spec["traces"][0]


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
    spec, _blob = fig.build_payload()
    assert spec["traces"][0]["n_marks"] == 2
    assert spec["traces"][0]["tooltip_rows"] == [{"i": 0}, {"i": 2}]
