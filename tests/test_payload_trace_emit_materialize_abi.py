"""ABI 321 ``xyg_payload_trace_emit_materialize`` smoke tests."""

from __future__ import annotations

import numpy as np

from xyg._figure import Figure
from xyg.config import DECIMATION_THRESHOLD


def test_payload_trace_emit_materialize_scatter_direct() -> None:
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
    spec, blob = fig.build_payload()
    entry = spec["traces"][0]
    assert entry["kind"] == "scatter"
    assert entry["tier"] == "direct"
    assert entry["n_marks"] == 3
    assert len(blob) > 0


def test_payload_trace_emit_materialize_line_decimated() -> None:
    n = DECIMATION_THRESHOLD + 1
    fig = Figure(width=800, height=400)
    fig.line(np.linspace(0.0, 1.0, n), np.sin(np.linspace(0.0, 1.0, n) * 10.0))
    spec, _blob = fig.build_payload(px_width=400)
    entry = spec["traces"][0]
    assert entry["kind"] == "line"
    assert entry["tier"] == "decimated"
    assert entry["n_marks"] < n
