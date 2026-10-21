"""Python twin of ``packages/xy-node/test/static-lod-polar.test.mjs`` (#1006).

Both hosts build the same figures, export native SVG and PNG through the one
Rust static route, and must produce the digests pinned in
``tests/fixtures/static_lod_polar_cross_host.json``: a 1,000,000-point line on
the browser's M4 tier, a 100,000-point line on a log ``y2`` axis (#1037), a
100,000-point scatter on the direct tier, and polar
bar wedges written as exact SVG arcs.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pytest

from xyg._figure import Figure
from xyg._scene_v3 import scene_export_support_reason

FIXTURE = Path(__file__).parent / "fixtures" / "static_lod_polar_cross_host.json"
LINE_N = 1_000_000
SCATTER_N = 100_000
CATEGORICAL_N = 150_000
Y2_LINE_N = 100_000
TAU = 6.283185307179586


def _line() -> Figure:
    index = np.arange(LINE_N, dtype=np.float64)
    figure = Figure(width=720, height=420)
    figure.line(
        index * 0.25,
        ((index * 7919.0) % 1009.0) / 10.0 - (index % 97.0),
        color="#ef4444",
        width=1,
    )
    figure.traces[0].id = 0
    return figure


def _scatter() -> Figure:
    index = np.arange(SCATTER_N, dtype=np.float64)
    figure = Figure(width=720, height=420)
    figure.axis_options["x"]["domain"] = (-2.0, 6.0)
    figure.axis_options["y"]["domain"] = (-2.0, 6.0)
    figure.scatter(
        ((index * 7919.0) % 1009.0) / 1009.0 * 8.0 - 2.0,
        ((index * 104729.0) % 997.0) / 997.0 * 8.0 - 2.0,
        color="#3987e5",
        size=3,
    )
    figure.traces[0].id = 0
    return figure


def _categorical_scatter() -> Figure:
    """150k per-item categorical scatter: direct tier with a per-point paint plane."""
    index = np.arange(CATEGORICAL_N, dtype=np.float64)
    figure = Figure(width=720, height=420)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.scatter(
        ((index * 7919.0) % 1009.0) / 1009.0,
        ((index * 104729.0) % 997.0) / 997.0,
        color=np.asarray([f"g{k}" for k in range(8)])[(index % 8).astype(np.int64)],
    )
    figure.traces[0].id = 0
    return figure


def _polar_bar() -> Figure:
    figure = Figure(width=320, height=240, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, TAU)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.bar([0.0, 1.57, 3.14], [0.5, 0.8, 0.6], color="#3987e5", name="pbar")
    figure.traces[0].id = 0
    return figure


def _line_y2_log() -> Figure:
    """A 100k line on a log secondary axis: M4 rows with the y2 log prefilter."""
    import xyg.components as c

    index = np.arange(Y2_LINE_N, dtype=np.float64)
    return c.line_chart(
        c.line(x=[0.0, 1.0, 2.0], y=[1.0, 2.0, 3.0]),
        c.line(
            x=index * 0.25,
            y=((index * 7919.0) % 1009.0) / 10.0 - (index % 97.0),
            y_axis="y2",
        ),
        c.x_axis(domain=(0.0, 25_000.0)),
        c.y_axis(domain=(0.0, 4.0)),
        c.y_axis(id="y2", side="right", type_="log", domain=(1.0, 200.0)),
        width=720,
        height=420,
    ).figure()


BUILDERS = {
    "line_1m_m4": _line,
    "line_y2_100k_log_m4": _line_y2_log,
    "scatter_100k_direct": _scatter,
    "scatter_150k_categorical": _categorical_scatter,
    "polar_bar_arcs": _polar_bar,
}


def _digests(figure: Figure) -> dict[str, str]:
    svg = figure.to_svg()
    png = figure.to_png(scale=1)
    return {
        "svg_sha256": hashlib.sha256(svg.encode()).hexdigest(),
        "png_sha256": hashlib.sha256(png).hexdigest(),
    }


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_python_static_lod_and_polar_exports_match_the_cross_host_fixture(name: str) -> None:
    fixture = json.loads(FIXTURE.read_text())
    assert fixture["schema"] == "xyg.static-lod-polar-cross-host/v1"
    figure = BUILDERS[name]()
    assert scene_export_support_reason(figure) is None
    assert _digests(figure) == fixture["cases"][name]


def test_cross_host_cases_exercise_the_tiers_they_name() -> None:
    line = _line().to_svg()
    (points,) = re.findall(r'<polyline points="([^"]*)"', line)
    assert 720 < len(points.split()) <= 4 * 720
    _, secondary = re.findall(r'<polyline points="([^"]*)"', _line_y2_log().to_svg())
    assert 720 < len(secondary.split()) <= 4 * 720
    assert _scatter().to_svg().count("<circle") == SCATTER_N
    paths = re.findall(r'<path d="([^"]*)"', _polar_bar().to_svg())
    wedges = [d for d in paths if " A " in d]
    assert len(wedges) == 3
