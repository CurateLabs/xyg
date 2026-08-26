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

from xyg import _native
from xyg._figure import Figure

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "exact_ecdf_scene.json").read_text())


def _native_lib() -> Path:
    if sys.platform == "win32":
        name = "xyg_core.dll"
    elif sys.platform == "darwin":
        name = "libxyg_core.dylib"
    else:
        name = "libxyg_core.so"
    return ROOT / "target" / "release" / name


def _figure(values: list[float]) -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 8.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.ecdf(values)
    figure.traces[0].id = 0
    return figure


def _node_scenes() -> dict[str, bytes]:
    node = shutil.which("node")
    if node is None or not _native_lib().is_file():
        pytest.skip("Node or native core unavailable")
    script = r"""
import { ecdfChart } from './packages/xy-node/src/index.js';
const cases = { mixed: [3, NaN, 1, 3, 2, Infinity], singleton: [7] };
const out = {};
for (const [name, values] of Object.entries(cases)) {
  const figure = ecdfChart(values);
  figure.width = 320; figure.height = 240;
  figure.setAxisDomain('x', [0, 8]); figure.setAxisDomain('y', [0, 1]);
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
        pytest.fail(f"Node exact-ECDF Scene probe failed:\n{proc.stderr}")
    return {name: base64.b64decode(value) for name, value in json.loads(proc.stdout).items()}


@pytest.mark.parametrize(
    ("name", "values", "expected_x", "expected_y"),
    [
        ("mixed", [3.0, np.nan, 1.0, 3.0, 2.0, np.inf], [1, 1, 2, 3], [0, 0.25, 0.5, 1]),
        ("singleton", [7.0], [7, 7], [0, 1]),
    ],
)
def test_exact_ecdf_is_one_rust_owned_scene_for_every_consumer(
    name: str, values: list[float], expected_x: list[float], expected_y: list[float]
) -> None:
    figure = _figure(values)
    trace = figure.traces[0]
    np.testing.assert_array_equal(trace.x.values, expected_x)
    np.testing.assert_array_equal(trace.y.values, expected_y)
    assert len(trace.x.values) <= len(values) + 1

    scene = figure.to_scene()
    assert scene == _node_scenes()[name]
    assert hashlib.sha256(scene).hexdigest() == FIXTURE[name]
    assert _native.scene_svg(scene).startswith("<svg")
    assert len(_native.scene_raster_commands(scene)) > 100
    assert _native.scene_browser_painter(scene).startswith(b"XYPB")


def test_exact_ecdf_preserves_the_public_all_nonfinite_error() -> None:
    with pytest.raises(ValueError, match="ecdf values must contain at least one finite value"):
        Figure().ecdf([np.nan, np.inf])
