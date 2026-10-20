"""Rust-owned per-point scatter size plane through the public path (#1006).

A scatter whose ``size`` is a per-point array used to fail closed in static
export (``Scene v12 does not yet encode hidden or per-item styled marks``).
Rust now maps the raw values onto ``size_range`` pixel diameters and interns
them onto Scene scatter records; Python and Node only marshal the raw channel.
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
from xyg import _static_document as sd
from xyg._figure import Figure
from xyg._scene_v3 import figure_scene, public_static_export, scene_export_support_reason

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = (
    ROOT / "packages" / "xy-node" / "scripts" / "static_export_scatter_size_cross_host.mjs"
)

X = [0.5, 1.0, 1.5, 2.0, 2.5]
Y = [1.0, 2.0, 1.0, 2.0, 1.0]
SIZE = [10.0, 20.0, 30.0, 40.0, 50.0]
#: ``size_range=(4, 14)`` maps the domain ``[10, 50]`` linearly onto diameters.
DIAMETERS = [4.0, 6.5, 9.0, 11.5, 14.0]


def _figure(name: str) -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 3.0)
    figure.axis_options["y"]["domain"] = (0.0, 3.0)
    if name == "size_array_constant_color":
        figure.scatter(X, Y, color="#9467bd", size=SIZE, size_range=(4.0, 14.0))
    else:
        figure.scatter(X, Y, color=[0, 1, 2, 3, 4], size=SIZE, size_range=(4.0, 14.0))
    for index, trace in enumerate(figure.traces):
        trace.id = index
    return figure


def _radii(svg: str) -> list[float]:
    return [float(r) for r in re.findall(r'<circle[^>]*\sr="([^"]+)"', svg)]


@pytest.mark.parametrize("name", ["size_array_constant_color", "size_array_continuous_color"])
def test_size_array_scatter_exports_one_radius_per_point(name: str) -> None:
    figure = _figure(name)
    assert scene_export_support_reason(figure) is None
    svg = _native.scene_svg(figure_scene(figure))
    assert _radii(svg) == pytest.approx([d / 2 for d in DIAMETERS], abs=1e-3)


def test_size_range_endpoints_are_the_extreme_diameters() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 3.0)
    figure.axis_options["y"]["domain"] = (0.0, 3.0)
    figure.scatter([1.0, 2.0], [1.0, 2.0], size=[3.0, 9.0], size_range=(5.0, 13.0))
    radii = _radii(_native.scene_svg(figure_scene(figure)))
    assert radii == pytest.approx([2.5, 6.5], abs=1e-3)


def test_per_item_color_only_scatter_keeps_the_trace_diameter() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 3.0)
    figure.axis_options["y"]["domain"] = (0.0, 3.0)
    figure.scatter(X, Y, color=[0, 1, 2, 3, 4], size=7.0)
    radii = _radii(_native.scene_svg(figure_scene(figure)))
    assert radii == pytest.approx([3.5] * 5, abs=1e-3)


def test_non_finite_size_value_keeps_the_stable_fail_closed_reason() -> None:
    figure = Figure(width=320, height=240)
    size = np.array(SIZE)
    size[2] = np.nan
    figure.scatter(X, Y, color="#9467bd", size=size)
    assert scene_export_support_reason(figure) == (
        "Scene v12 does not yet encode hidden or per-item styled marks"
    )


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


@pytest.mark.parametrize("name", ["size_array_constant_color", "size_array_continuous_color"])
def test_python_and_node_export_identical_bytes(name: str, node_exports: dict[str, Any]) -> None:
    figure = _figure(name)
    scene = figure_scene(figure)
    node = node_exports[name]
    assert base64.b64decode(node["scene_b64"]) == scene
    assert base64.b64decode(node["xyst_b64"]) == sd.encode(
        [sd.Panel(scene, 0, 0, 320, 240)], width=320, height=240
    )
    assert base64.b64decode(node["svg_b64"]) == public_static_export(figure, "svg")
    assert base64.b64decode(node["png_b64"]) == _native.scene_static_export(
        scene, "png", width=320, height=240, scale=1.0
    )
