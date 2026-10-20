"""Artist-alpha paint matrix through public composition, Python vs Node (#1006).

role (fill, stroke) x source (constant/scalar, per-item) x paint (keyword
``transparent``, explicit ``#00000000``, opaque, translucent), each with a per-item
artist-alpha channel of 0.5. Rust decides absence from the effective paint:
the keyword stays absent for constant/scalar sources, while explicit
RGBA paints and per-item arrays (which have no keyword form; Matplotlib 3.11
also lets a *list* of ``"none"`` take the alpha) have their alpha replaced
exactly once.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from xyg import _native
from xyg._figure import Figure
from xyg._scene_v3 import figure_scene, scene_export_support_reason

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = (
    ROOT / "packages" / "xy-node" / "scripts" / "static_export_artist_alpha_cross_host.mjs"
)
PAINTS = {
    "keyword": "transparent",
    "hex0": "#00000000",
    "opaque": "#ff0000",
    "translucent": "#ff000080",
}
# A per-item array has no keyword form: the keyword and ``#00000000`` are the same row.
ROWS = {
    "keyword": [0.0, 0.0, 0.0, 0.0],
    "hex0": [0.0, 0.0, 0.0, 0.0],
    "opaque": [1.0, 0.0, 0.0, 1.0],
    "translucent": [1.0, 0.0, 0.0, 128 / 255],
}
CASES = [
    (role, source, paint)
    for role in ("fill", "stroke")
    for source in ("constant", "per_item")
    for paint in PAINTS
]


def _expected_alpha(source: str, paint: str) -> float:
    # The keyword is absent only as a constant/scalar paint.
    return 0.0 if paint == "keyword" and source == "constant" else 0.5


def _figure(role: str, source: str, paint: str) -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    css = PAINTS[paint]
    value: Any = [ROWS[paint], ROWS[paint]] if source == "per_item" else css
    artist = np.array([0.5, 0.5])
    if role == "fill":
        figure.scatter([0.3, 0.7], [0.5, 0.5], color=value, opacity=1.0, _artist_alpha=artist)
    else:
        figure.scatter(
            [0.3, 0.7],
            [0.5, 0.5],
            color="#00ff00",
            stroke=value,
            stroke_width=4,
            opacity=1.0,
            _artist_alpha=artist,
        )
    figure.traces[0].id = 0
    return figure


def _alpha(svg: str, role: str) -> float:
    circle = re.search(r"<circle[^>]*>", svg)
    assert circle is not None
    tag = circle.group(0)
    paint = re.search(rf'(?<![-\w]){role}="([^"]*)"', tag)
    if paint is None or paint.group(1) in {"none", "transparent"}:
        return 0.0
    rgba = re.match(r"rgba\([^,]+,[^,]+,[^,]+,([\d.]+)\)", paint.group(1))
    base = float(rgba.group(1)) if rgba else 1.0
    opacity = re.search(rf'{role}-opacity="([\d.]+)"', tag)
    return base * (float(opacity.group(1)) if opacity else 1.0)


@pytest.fixture(scope="module")
def node_cases() -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found on PATH")
    lib = "libxyg_core.dylib" if sys.platform == "darwin" else "libxyg_core.so"
    native = ROOT / "target" / "release" / lib
    if not native.is_file():
        pytest.skip(f"missing native core {native}")
    env = {**os.environ, "XYG_NATIVE_LIB": os.environ.get("XYG_NATIVE_LIB", str(native))}
    proc = subprocess.run(
        [node, str(NODE_SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        pytest.fail(f"Node proof failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return json.loads(proc.stdout)


@pytest.mark.parametrize(("role", "source", "paint"), CASES)
def test_artist_alpha_matrix_python(role: str, source: str, paint: str) -> None:
    figure = _figure(role, source, paint)
    assert scene_export_support_reason(figure) is None
    svg = _native.scene_svg(figure_scene(figure))
    assert _alpha(svg, role) == pytest.approx(_expected_alpha(source, paint), abs=0.01)


@pytest.mark.parametrize(("role", "source", "paint"), CASES)
def test_artist_alpha_matrix_python_and_node_scenes_are_identical(
    role: str, source: str, paint: str, node_cases: dict[str, Any]
) -> None:
    node = node_cases[f"{role}/{source}/{paint}"]
    figure = _figure(role, source, paint)
    reason = scene_export_support_reason(figure)
    assert reason is None
    if (role, source, paint) == ("stroke", "constant", "keyword"):
        # Node's scalar stroke accepts only functional CSS (`#…`/`rgb()`), so the
        # keyword is not composable there; Python's is covered above.
        assert node == {"error": "scatter stroke must be a CSS color"}
        return
    assert "error" not in node, node
    assert base64.b64decode(node["scene_b64"]) == figure_scene(figure)
