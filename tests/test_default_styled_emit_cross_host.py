"""Cross-host default-styled emit parity: Python vs @curatelabs/xyg-node.

Compares trace style dicts where Python ``_default_styled`` fills palette color
when ``style.color`` is missing (line, area, histogram, mesh, segments, ribbon,
and rect emit paths).

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so \\
      uv run pytest tests/test_default_styled_emit_cross_host.py -q
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from xyg import _native
from xyg._figure import Figure
from xyg.config import DEFAULT_PALETTE, PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "default_styled_emit_cross_host.mjs"
FIXTURE_JSON = ROOT / "tests" / "fixtures" / "default_styled_emit_cross_host.json"

CASE_NAMES = (
    "line_default_styled",
    "area_default_styled",
    "hist_default_styled",
    "mesh_default_styled",
    "segments_default_styled",
    "ribbon_default_styled",
    "rect_default_styled",
)


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


def _build_case(name: str) -> Figure:
    fig = Figure(width=240, height=160)
    if name == "line_default_styled":
        fig.line([0.0, 1.0], [0.0, 1.0])
        trace = fig.traces[0]
        trace.id = 16
    elif name == "area_default_styled":
        fig.area([0.0, 1.0], [0.0, 1.0])
        trace = fig.traces[0]
        trace.id = 17
    elif name == "hist_default_styled":
        fig.histogram([0, 1, 1, 2], bins=2, range=(0, 2))
        trace = fig.traces[0]
        trace.id = 18
    elif name == "mesh_default_styled":
        fig.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0])
        trace = fig.traces[0]
        trace.id = 19
    elif name == "segments_default_styled":
        fig.segments([0.0, 1.0], [0.0, 1.0], [1.0, 2.0], [1.0, 2.0])
        trace = fig.traces[0]
        trace.id = 20
    elif name == "ribbon_default_styled":
        fig.ribbon([0.0], [1.0], [0.0], [1.0], [0.0], [1.0])
        trace = fig.traces[0]
        trace.id = 21
    elif name == "rect_default_styled":
        fig.box([1, 2, 3, 4, 5])
        trace = next(t for t in fig.traces if t.kind == "box_whisker")
        trace.id = 22
    else:
        raise KeyError(name)
    trace.style = {"opacity": 0.9}
    return fig


def _emit_style(spec: dict, *, kind: str | None = None) -> dict:
    if kind is None:
        trace = spec["traces"][0]
    else:
        trace = next(t for t in spec["traces"] if t["kind"] == kind)
    return {
        "trace_id": trace["id"],
        "kind": trace["kind"],
        "style": dict(trace.get("style") or {}),
        "palette_color": DEFAULT_PALETTE[trace["id"] % len(DEFAULT_PALETTE)],
    }


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def node_golden() -> dict:
    if not _node_bin():
        pytest.skip("node binary not on PATH")
    if not NODE_SCRIPT.is_file():
        pytest.skip(f"missing {NODE_SCRIPT}")
    if not LIB.is_file():
        pytest.skip(f"{LIB.name} missing; run `cargo build --release`")

    env = os.environ.copy()
    env.setdefault("XYG_NATIVE_LIB", str(LIB))
    proc = subprocess.run(
        [_node_bin(), str(NODE_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    if proc.returncode != 0:
        pytest.fail(
            "node default-styled emit cross-host golden failed:\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def test_fixture_contract(fixture: dict) -> None:
    assert fixture["schema"] == "xyg.default-styled-emit-cross-host/v1"
    assert fixture["protocol"] == PROTOCOL_VERSION
    assert int(fixture["abi_version"]) == int(_native.ABI_VERSION)
    assert len(fixture["cases"]) == len(CASE_NAMES)
    assert {case["name"] for case in fixture["cases"]} == set(CASE_NAMES)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_python_matches_checked_in_fixture(case_name: str, fixture: dict) -> None:
    entry = next(case for case in fixture["cases"] if case["name"] == case_name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        spec, _blob = _build_case(case_name).build_payload()
    meta = _emit_style(
        spec,
        kind="box_whisker" if case_name == "rect_default_styled" else None,
    )
    assert meta["trace_id"] == entry["trace_id"]
    assert meta["kind"] == entry["kind"]
    assert meta["style"] == entry["style"]
    assert meta["palette_color"] == entry["palette_color"]


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_node_live_matches_python(case_name: str, node_golden: dict) -> None:
    node_case = next(case for case in node_golden["cases"] if case["name"] == case_name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        spec, _blob = _build_case(case_name).build_payload()
    meta = _emit_style(
        spec,
        kind="box_whisker" if case_name == "rect_default_styled" else None,
    )
    assert meta["style"] == node_case["style"]
    assert meta["palette_color"] == node_case["palette_color"]
