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
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "binned_ecdf_scene.json").read_text())
CASES = {
    "mixed": ([3.0, np.nan, 1.0, 3.0, 2.0, np.inf], 4),
    "constant": ([7.0, 7.0, 7.0], 4),
    "sparse": ([0.0, 0.1, 9.9, 10.0], 10),
}


def _native_lib() -> Path:
    if sys.platform == "win32":
        name = "xyg_core.dll"
    elif sys.platform == "darwin":
        name = "libxyg_core.dylib"
    else:
        name = "libxyg_core.so"
    return ROOT / "target" / "release" / name


def _figure(values: list[float], bins: int) -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (-1.0, 11.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.ecdf(values, bins=bins)
    figure.traces[0].id = 0
    return figure


def _node_scenes() -> dict[str, bytes]:
    node = shutil.which("node")
    if node is None or not _native_lib().is_file():
        pytest.skip("Node or native core unavailable")
    script = r"""
import { ecdfChart } from './packages/xy-node/src/index.js';
const cases = {
  mixed: [[3,NaN,1,3,2,Infinity], 4],
  constant: [[7,7,7], 4],
  sparse: [[0,.1,9.9,10], 10],
};
const out = {};
for (const [name, [values, bins]] of Object.entries(cases)) {
  const figure = ecdfChart(values, {bins});
  figure.width = 320; figure.height = 240;
  figure.setAxisDomain('x', [-1,11]); figure.setAxisDomain('y', [0,1]);
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
        pytest.fail(f"Node binned-ECDF Scene probe failed:\n{proc.stderr}")
    return {name: base64.b64decode(value) for name, value in json.loads(proc.stdout).items()}


@pytest.mark.parametrize("name", CASES)
def test_binned_ecdf_is_one_rust_owned_scene_for_every_host(name: str) -> None:
    figure = _figure(*CASES[name])
    trace = figure.traces[0]
    assert trace.style["step"] == "post"
    assert scene_export_support_reason(figure) is None
    scene = figure.to_scene()
    assert scene == _node_scenes()[name]
    assert hashlib.sha256(scene).hexdigest() == FIXTURE[name]


def test_binned_ecdf_routes_every_static_and_browser_consumer() -> None:
    figure = _figure(*CASES["mixed"])
    scene = figure.to_scene()
    svg = _native.scene_svg(scene)
    from xyg import _static_document

    assert figure.to_svg() == _static_document.export_figure(
        figure, "svg", width=int(figure.width), height=int(figure.height)
    ).decode("utf-8")
    assert _native.scene_svg(figure.to_scene()) == svg
    assert figure.to_png(scale=1) == kernels.rasterize_png(
        _native.scene_raster_commands(scene), 320, 240
    )
    assert figure.to_image(format="pdf") == _pdf.svg_to_pdf(svg)
    assert _native.scene_browser_painter(scene).startswith(b"XYPB")


def test_binned_ecdf_preserves_public_validation_and_mode() -> None:
    with pytest.raises(ValueError, match="ecdf values must contain at least one finite value"):
        Figure().ecdf([np.nan, np.inf], bins=4)
    with pytest.raises(ValueError, match="ecdf bins must be a positive integer or None"):
        Figure().ecdf([1.0], bins=0)
    with pytest.raises(ValueError, match="ecdf bins must be <= 10000"):
        Figure().ecdf([1.0], bins=10_001)
