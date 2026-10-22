"""Python twin of ``packages/xy-node/test/polar-legend-support.test.mjs`` (#1041).

A polar figure whose in-Scene legend cannot fit the recut polar viewport
(compact canvases under 520 px reserve a 64 px bottom band) must report the one
stable ``XYG_SCENE_UNSUPPORTED_POLAR_LEGEND`` reason from Rust on every host,
never the opaque encode code ``-16``. The expected reason per case is pinned in
``tests/fixtures/polar_legend_support_cross_host.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xyg._figure import Figure
from xyg._scene_v3 import figure_scene, scene_export_support_reason

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "polar_legend_support_cross_host.json").read_text()
)
TAU = 6.283185307179586


def _polar_bands(side: int, bands: int) -> Figure:
    figure = Figure(width=side, height=side, coords="polar")
    figure.axis_options["x"]["domain"] = (0.0, TAU)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    for index in range(bands):
        figure.bar([0.0, 1.57, 3.14], [0.5, 0.8, 0.6], color="#3987e5", name=f"band {index}")
        figure.traces[index].id = index
    return figure


CASES = [pytest.param(c, id=f"{c['side']}px-{c['bands']}bands") for c in FIXTURE["cases"]]


@pytest.mark.parametrize("case", CASES)
def test_polar_legend_support_reason_matches_the_cross_host_fixture(case: dict) -> None:
    side = case["side"]
    figure = _polar_bands(side, case["bands"])
    assert scene_export_support_reason(figure, width=side, height=side) == case["reason"]


@pytest.mark.parametrize("case", CASES)
def test_polar_legend_scene_never_leaks_the_opaque_encode_code(case: dict) -> None:
    side = case["side"]
    figure = _polar_bands(side, case["bands"])
    if case["reason"] is None:
        assert figure_scene(figure, width=side, height=side)[:4] == b"XYGS"
        return
    with pytest.raises(ValueError) as raised:
        figure_scene(figure, width=side, height=side)
    assert str(raised.value).startswith(case["reason"])


def test_wind_rose_static_exports_still_work_below_the_boundary() -> None:
    import numpy as np

    import xyg

    rng = np.random.default_rng(19)
    figure = xyg.wind_rose(
        rng.uniform(0, 360, 2_000), rng.gamma(2.0, 3.0, 2_000), sectors=16
    ).figure()
    assert scene_export_support_reason(figure, width=300, height=300) == FIXTURE["reason"]
    assert figure.to_svg(width=300, height=300).startswith("<svg")
    assert figure.to_png(width=300, height=300)[:4] == b"\x89PNG"
