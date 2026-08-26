from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from xyg import _native, _pdf, kernels
from xyg._figure import Figure
from xyg._scene_v3 import scene_export_support_reason

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "histogram_auto_scene.json").read_text())
CASES = {
    "mixed": ([3, 0.1, 2, 0.1, 13, np.nan, 0, 8, 5, 0.3, 0.2], {}),
    "constant": ([5, 5, 5], {}),
    "range": ([-2, 0, 0.2, 1, 3, 8], {"range": (0, 4)}),
    "wide_range": ([0, 1], {"range": (-10, 10)}),
    "density_cumulative": (
        [0, 0.1, 0.2, 0.3, 2, 3, 5, 8, 13],
        {"density": True, "cumulative": True},
    ),
    "fixed": ([0, 0.1, 0.2, 0.3, 2, 3, 5, 8, 13], {"bins": 10}),
    "authored": ([0.1, 0.2, 1.2, 2.4, np.nan], {"bins": [0.0, 1.0, 2.0, 3.0]}),
    "authored_cumulative": (
        [0.1, 0.2, 1.2, 2.4],
        {"bins": [0.0, 0.5, 2.0, 4.0], "cumulative": True},
    ),
    "empty": ([], {}),
    "all_nonfinite": ([np.nan, np.inf], {}),
}


def _native_lib() -> Path:
    if sys.platform == "win32":
        name = "xyg_core.dll"
    elif sys.platform == "darwin":
        name = "libxyg_core.dylib"
    else:
        name = "libxyg_core.so"
    return ROOT / "target" / "release" / name


def _figure(values: list[float], options: dict[str, object]) -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (-3.0, 14.0)
    figure.axis_options["y"]["domain"] = (0.0, 10.0)
    figure.histogram(values, **options)
    figure.traces[0].id = 0
    return figure


def _node_scenes() -> dict[str, bytes]:
    node = shutil.which("node")
    if node is None or not _native_lib().is_file():
        pytest.skip("Node or native core unavailable")
    script = r"""
import { histogramChart } from './packages/xy-node/src/index.js';
const cases = {
  mixed: [[3,.1,2,.1,13,NaN,0,8,5,.3,.2], {}],
  constant: [[5,5,5], {}],
  range: [[-2,0,.2,1,3,8], {range:[0,4]}],
  wide_range: [[0,1], {range:[-10,10]}],
  density_cumulative: [[0,.1,.2,.3,2,3,5,8,13], {density:true,cumulative:true}],
  fixed: [[0,.1,.2,.3,2,3,5,8,13], {bins:10}],
  authored: [[.1,.2,1.2,2.4,NaN], {bins:[0,1,2,3]}],
  authored_cumulative: [[.1,.2,1.2,2.4], {bins:[0,.5,2,4],cumulative:true}],
  empty: [[], {}],
  all_nonfinite: [[NaN,Infinity], {}],
};
const out = {};
for (const [name, [values, options]] of Object.entries(cases)) {
  const figure = histogramChart(values, options);
  figure.width = 320; figure.height = 240;
  figure.setAxisDomain('x', [-3,14]); figure.setAxisDomain('y', [0,10]);
  figure.traces[0].id = 0;
  out[name] = Buffer.from(figure.toScene()).toString('base64');
}
process.stdout.write(JSON.stringify(out));
"""
    env = os.environ.copy()
    env.setdefault("XYG_NATIVE_LIB", str(_native_lib()))
    proc = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(f"Node histogram-auto Scene probe failed:\n{proc.stderr}")
    return {name: base64.b64decode(value) for name, value in json.loads(proc.stdout).items()}


@pytest.mark.parametrize("name", CASES)
def test_histogram_auto_is_cross_host_exact_and_bounded(name: str) -> None:
    values, options = CASES[name]
    figure = _figure(values, options)
    scene = figure.to_scene()
    assert scene == _node_scenes()[name]
    assert hashlib.sha256(scene).hexdigest() == FIXTURE[name]
    trace = figure.traces[0]
    if name in {"empty", "all_nonfinite", "fixed"}:
        assert len(trace.x0.values) == 10
    elif name in {"authored", "authored_cumulative"}:
        assert len(trace.x0.values) == 3
    else:
        assert len(trace.x0.values) <= 10_000
    if name == "wide_range":
        assert len(trace.x0.values) == 40


def test_histogram_auto_counts_density_and_every_public_consumer() -> None:
    mixed = _figure(*CASES["mixed"])
    assert mixed.traces[0].y1.values.sum() == 10
    density = _figure(*CASES["density_cumulative"])
    np.testing.assert_allclose(density.traces[0].y1.values, [5 / 9, 7 / 9, 7 / 9, 8 / 9, 1])
    authored = _figure(*CASES["authored"])
    np.testing.assert_array_equal(authored.traces[0].y1.values, [2.0, 1.0, 1.0])
    authored_cdf = _figure(*CASES["authored_cumulative"])
    np.testing.assert_array_equal(authored_cdf.traces[0].y1.values, [2.0, 3.0, 4.0])

    assert scene_export_support_reason(mixed) is None
    scene = mixed.to_scene()
    svg = _native.scene_svg(scene)
    assert mixed.to_svg() == svg
    assert mixed.to_png(scale=1) == kernels.rasterize_png(
        _native.scene_raster_commands(scene), 320, 240
    )
    assert mixed.to_image(format="pdf") == _pdf.svg_to_pdf(svg)
    assert _native.scene_browser_painter(scene).startswith(b"XYPB")
