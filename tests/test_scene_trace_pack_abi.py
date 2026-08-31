"""Cross-host Scene trace-pack parity for Push 2 (XYTC + XYTA).

Compares Python ``_pack_xytc`` / ``_pack_xyta`` against
``@curatelabs/xyg-node`` ``packFigureXyTc`` / ``packFigureXyTa`` and verifies
the Rust compile/attach chain (``xyg_scene_pack_trace_compile`` /
``xyg_scene_pack_trace_attach``) accepts the golden bytes for scatter, line,
hexbin, heatmap, ribbon, and triangle mesh.

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so \\
      uv run pytest tests/test_scene_trace_pack_abi.py -q
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from xyg import _native, _scene_v3
from xyg._figure import Figure

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "scene_trace_pack_cross_host.mjs"
FIXTURE_JSON = ROOT / "tests" / "fixtures" / "figure_scene_v3.json"

_PUBLIC_HEXBIN_X = [0.5, 1.5, 2.5, 3.5, 1.0, 2.0, 3.0]
_PUBLIC_HEXBIN_Y = [0.5, 0.5, 0.5, 0.5, 2.0, 2.0, 2.0]

CASE_NAMES = ("scatter", "line", "hexbin", "heatmap", "ribbon", "mesh")


def _native_lib() -> Path:
    if sys.platform == "win32":
        name = "xyg_core.dll"
    elif sys.platform == "darwin":
        name = "libxyg_core.dylib"
    else:
        name = "libxyg_core.so"
    return ROOT / "target" / "release" / name


LIB = _native_lib()


def _node_bin() -> str:
    return shutil.which("node") or ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_fixture() -> dict:
    return json.loads(FIXTURE_JSON.read_text())


def _scatter_stroke_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.scatter(
        [0.25, 1.75],
        [0.5, 1.5],
        color="#336699",
        opacity=0.75,
        size=12,
        symbol="diamond",
        stroke="#ff8800",
        stroke_width=3.5,
        name="outlined",
    )
    figure.traces[-1].id = 41
    return figure


def _line_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2)
    figure.traces[-1].id = 0
    return figure


def _hexbin_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.hexbin(
        _PUBLIC_HEXBIN_X,
        _PUBLIC_HEXBIN_Y,
        gridsize=(4, 4),
        range=((0.0, 4.0), (0.0, 5.0)),
        name="hex",
    )
    figure.traces[-1].id = 0
    return figure


def _heatmap_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.heatmap(
        [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]],
        x=[1.0, 2.0, 3.0],
        y=[1.0, 3.0],
        color="#3987e5",
        opacity=0.75,
        name="heat",
    )
    figure.traces[-1].id = 0
    return figure


def _ribbon_figure() -> Figure:
    from tests.test_scene_export_support import _public_ribbon

    return _public_ribbon("linear")


def _mesh_figure() -> Figure:
    from tests.test_scene_export_support import _public_triangle_mesh

    return _public_triangle_mesh()


def _build_case(name: str) -> Figure:
    builders: dict[str, Callable[[], Figure]] = {
        "scatter": _scatter_stroke_figure,
        "line": _line_figure,
        "hexbin": _hexbin_figure,
        "heatmap": _heatmap_figure,
        "ribbon": _ribbon_figure,
        "mesh": _mesh_figure,
    }
    return builders[name]()


def _pack_trace_chain(figure: Figure) -> dict[str, bytes]:
    xytc = _scene_v3._pack_xytc(figure)
    xyta = _scene_v3._pack_xyta(figure)
    compiled = _native.scene_pack_trace_compile(xytc)
    attached = _native.scene_pack_trace_attach(compiled, xyta)
    return {"xytc": xytc, "xyta": xyta, "xytr": compiled, "xytt": attached}


@pytest.fixture(scope="module")
def node_golden() -> dict:
    if not NODE_SCRIPT.is_file():
        pytest.skip(f"missing {NODE_SCRIPT}")
    node = _node_bin()
    if not node:
        pytest.skip("node not found on PATH")
    if not LIB.is_file():
        pytest.skip(f"missing native core {LIB}")
    env = os.environ.copy()
    env.setdefault("XYG_NATIVE_LIB", str(LIB))
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
            "node scene trace-pack cross-host golden failed:\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "xyg.scene-trace-pack-cross-host/v1"
    return {case["name"]: case for case in payload["cases"]}


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_python_trace_pack_matches_fixture_sha256(case_name: str) -> None:
    fixture = _load_fixture()["trace_pack_sha256"][case_name]
    packed = _pack_trace_chain(_build_case(case_name))
    assert packed["xytc"].startswith(b"XYTC")
    assert packed["xyta"].startswith(b"XYTA")
    assert packed["xytr"].startswith(b"XYTO")
    assert packed["xytt"].startswith(b"XYTT")
    assert _sha256(packed["xytc"]) == fixture["xytc"]
    assert _sha256(packed["xyta"]) == fixture["xyta"]
    assert _sha256(packed["xytr"]) == fixture["xytr"]
    assert _sha256(packed["xytt"]) == fixture["xytt"]


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_node_trace_pack_matches_python_and_fixture(case_name: str, node_golden: dict) -> None:
    fixture = _load_fixture()["trace_pack_sha256"][case_name]
    node_case = node_golden[case_name]
    packed = _pack_trace_chain(_build_case(case_name))
    assert node_case["xytc_magic"] == "XYTC"
    assert node_case["xyta_magic"] == "XYTA"
    assert node_case["xytc_sha256"] == _sha256(packed["xytc"])
    assert node_case["xyta_sha256"] == _sha256(packed["xyta"])
    assert node_case["xytc_sha256"] == fixture["xytc"]
    assert node_case["xyta_sha256"] == fixture["xyta"]


def test_trace_pack_fixture_aliases_existing_public_goldens() -> None:
    fixture = _load_fixture()
    trace = fixture["trace_pack_sha256"]
    assert trace["hexbin"]["xyta"] == fixture["public_hexbin_colormap_xyta_sha256"]
    assert trace["ribbon"]["xytc"] == fixture["public_ribbon_xytc_sha256"]
    assert trace["mesh"]["xytc"] == fixture["public_triangle_mesh_xytc_sha256"]
