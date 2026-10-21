"""Python/Node identity for Rust-owned no-op traces and per-segment paint (#1006)."""

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

import pytest

from xyg import _native
from xyg._figure import Figure
from xyg._scene_v3 import figure_scene, public_static_export, scene_export_support_reason

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "static_export_noop_paint_cross_host.mjs"


@pytest.fixture(scope="module")
def node_exports() -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found on PATH")
    name = "xyg_core.dll" if sys.platform == "win32" else "libxyg_core.so"
    native = (
        ROOT / "target" / "release" / (name if sys.platform != "darwin" else "libxyg_core.dylib")
    )
    if not native.is_file():
        pytest.skip(f"missing native core {native}")
    env = {**os.environ, "XYG_NATIVE_LIB": os.environ.get("XYG_NATIVE_LIB", str(native))}
    proc = subprocess.run(
        [node, str(NODE_SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        pytest.fail(f"Node proof failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return json.loads(proc.stdout)


# Same authored facts as the Node script (#1025): Rust lowers every one.
_CONTOURS: dict[str, dict[str, Any]] = {
    "contour_default_colormap": {},
    "contour_named_colormap": {"colormap": "magma"},
    "contour_constant_color": {"color": "#ef4444"},
    "contour_level_colors": {"color": [[1, 0, 0], [1, 1, 0], [0, 0, 1]]},
}


# Custom colormaps fail closed in Scene export on both hosts (#1025).
_REJECTED_CONTOURS: dict[str, dict[str, Any]] = {
    "contour_gradient_colormap": {"colormap": "linear-gradient(#ff0000, #0000ff)"},
    "contour_listed_colormap": {"colormap": ["#ff0000", "#00ff00", "#0000ff"]},
    "contour_stops_colormap": {"colormap": [[255, 0, 0], [0, 0, 255]]},
}
CONTOUR_REASON = "XYG_SCENE_UNSUPPORTED_CONTOUR_CUSTOM_COLORMAP"


def _figure(name: str) -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 3.0)
    figure.axis_options["y"]["domain"] = (0.0, 3.0)
    if name == "empty_traces":
        figure.line([0, 1, 2], [0, 2, 1], color="#ef4444")
        figure.line([], [], color="#22c55e", name="proxy")
        figure.scatter([], [], color="#3987e5", size=6)
    elif name in _CONTOURS or name in _REJECTED_CONTOURS:
        figure.contour(
            [[0, 1, 0], [1, 2, 1], [0, 1, 0]],
            levels=[0.25, 1.0, 1.75],
            corner_mask=False,
            **_CONTOURS.get(name, _REJECTED_CONTOURS.get(name, {})),
        )
    else:
        figure.segments([0, 1, 2, 0], [0, 1, 2, 2], [1, 2, 3, 1], [1, 0, 3, 3], color=[0, 0, 1, 1])
    for index, trace in enumerate(figure.traces):
        trace.id = index
    return figure


@pytest.mark.parametrize("name", ["empty_traces", "colormapped_segments", *_CONTOURS])
def test_python_and_node_export_identical_bytes(name: str, node_exports: dict[str, Any]) -> None:
    figure = _figure(name)
    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    node = node_exports[name]
    assert base64.b64decode(node["scene_b64"]) == scene
    assert base64.b64decode(node["svg_b64"]) == public_static_export(figure, "svg")
    assert base64.b64decode(node["png_b64"]) == _native.scene_static_export(
        scene, "png", width=320, height=240, scale=1.0
    )


def test_colormapped_segments_paint_one_literal_stroke_per_level() -> None:
    svg = _native.scene_svg(figure_scene(_figure("colormapped_segments")))
    strokes = set(re.findall(r'stroke="(rgb\([^"]+\))"', svg))
    assert len(strokes) == 2  # two distinct mapped colors, not one flat stroke


def test_empty_traces_add_no_marks() -> None:
    with_empty = _figure("empty_traces")
    with_empty.traces[1].name = None  # the legend entry is checked separately
    figure = _figure("empty_traces")
    figure.traces = figure.traces[:1]
    assert _native.scene_svg(figure_scene(with_empty)) == _native.scene_svg(figure_scene(figure))


@pytest.mark.parametrize("name", list(_REJECTED_CONTOURS))
def test_custom_contour_colormaps_fail_closed_on_both_hosts(
    name: str, node_exports: dict[str, Any]
) -> None:
    assert scene_export_support_reason(_figure(name)) == CONTOUR_REASON
    assert node_exports[name]["reason"] == CONTOUR_REASON


def _strokes(node_exports: dict[str, Any], name: str) -> list[str]:
    svg = base64.b64decode(node_exports[name]["svg_b64"]).decode()
    return list(dict.fromkeys(re.findall(r'stroke="(rgb\([^"]+\))"', svg)))


def test_contour_colormaps_paint_the_authored_strokes(node_exports: dict[str, Any]) -> None:
    assert _strokes(node_exports, "contour_default_colormap") == [
        "rgb(68,1,84)",
        "rgb(33,145,140)",
        "rgb(253,231,37)",
    ]
    assert _strokes(node_exports, "contour_named_colormap") == [
        "rgb(0,0,4)",
        "rgb(183,55,121)",
        "rgb(252,253,191)",
    ]
    assert _strokes(node_exports, "contour_level_colors") == [
        "rgb(255,0,0)",
        "rgb(255,255,0)",
        "rgb(0,0,255)",
    ]
    assert _strokes(node_exports, "contour_constant_color") == ["rgb(239,68,68)"]


def test_public_colormapped_contour_paints_one_literal_stroke_per_level() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 3.0)
    figure.axis_options["y"]["domain"] = (0.0, 3.0)
    figure.contour([[0, 1, 0], [1, 2, 1], [0, 1, 0]], levels=[0.25, 1.0, 1.75], corner_mask=False)
    assert scene_export_support_reason(figure) is None
    svg = _native.scene_svg(figure_scene(figure))
    assert len(set(re.findall(r'stroke="(rgb\([^"]+\))"', svg))) == 3
