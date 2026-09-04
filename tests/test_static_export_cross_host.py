"""Python/Node static-export identity for the ordinary M2 public route (#857)."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from xyg import _native
from xyg._figure import Figure
from xyg._scene_v3 import figure_scene, public_static_export, scene_export_support_reason

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "static_export_cross_host.mjs"


def _native_lib() -> Path:
    if sys.platform == "win32":
        name = "xyg_core.dll"
    elif sys.platform == "darwin":
        name = "libxyg_core.dylib"
    else:
        name = "libxyg_core.so"
    return ROOT / "target" / "release" / name


def _line_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2)
    figure.traces[-1].id = 0
    return figure


def _scatter_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.scatter(
        [0, 1, 2],
        [1, 3, 2],
        color="#3987e5",
        size=6,
        opacity=0.8,
        symbol="diamond",
    )
    figure.traces[-1].id = 0
    return figure


def _bar_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.bar([0, 1], [1, 2], color="#22c55e", opacity=0.85)
    figure.traces[-1].id = 0
    return figure


def _histogram_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.histogram([0, 1, 1, 2], bins=2, color="#7c3aed", opacity=0.85)
    figure.traces[-1].id = 0
    return figure


BUILDERS: dict[str, Callable[[], Figure]] = {
    "line": _line_figure,
    "scatter": _scatter_figure,
    "bar": _bar_figure,
    "histogram": _histogram_figure,
}


@pytest.fixture(scope="module")
def node_static_exports() -> dict[str, object]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found on PATH")
    native = _native_lib()
    if not native.is_file():
        pytest.skip(f"missing native core {native}")
    env = os.environ.copy()
    env.setdefault("XYG_NATIVE_LIB", str(native))
    proc = subprocess.run(
        [node, str(NODE_SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(
            "Node static-export cross-host proof failed:\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "xyg.static-export-cross-host/v1"
    return payload


@pytest.mark.parametrize("case_name", tuple(BUILDERS))
def test_python_and_node_static_scene_svg_and_raster_commands_are_identical(
    case_name: str, node_static_exports: dict[str, object]
) -> None:
    node_cases = {case["name"]: case for case in node_static_exports["cases"]}
    node_case = node_cases[case_name]
    figure = BUILDERS[case_name]()

    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    svg = public_static_export(figure, "svg")
    png = public_static_export(figure, "png")
    assert svg is not None
    assert png is not None and png.startswith(b"\x89PNG\r\n\x1a\n")

    assert base64.b64decode(node_case["scene_b64"]) == scene
    assert base64.b64decode(node_case["svg_b64"]) == svg == figure.to_svg().encode()
    assert base64.b64decode(node_case["raster_b64"]) == _native.scene_raster_commands(scene)
    assert png == figure.to_png(scale=1)


def test_browser_css_miss_stays_fail_closed_and_uses_python_compatibility(
    node_static_exports: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    from xyg import _svg

    figure = _line_figure()
    figure.class_name = "browser-only"
    reason = scene_export_support_reason(figure)
    assert reason == node_static_exports["miss"]["reason"]
    assert reason is not None
    assert public_static_export(figure, "svg") is None

    calls = {"compat": 0}
    compatibility = _svg.to_svg

    def observed_compat(target: Figure, *args: object, **kwargs: object) -> str:
        calls["compat"] += 1
        return compatibility(target, *args, **kwargs)

    monkeypatch.setattr(_svg, "to_svg", observed_compat)
    assert figure.to_svg().startswith("<svg")
    assert calls["compat"] == 1
