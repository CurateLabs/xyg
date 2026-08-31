"""Cross-host animation attach parity: Python vs @curatelabs/xyg-node.

Compares scatter, line, area, density, histogram, bar, segments, ribbon, and
mesh emit paths where Python attaches ``t.animation`` via
``payload_base_entry_plan`` or ``_transition_entry``.

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so \\
      uv run pytest tests/test_animation_emit_cross_host.py -q
"""

from __future__ import annotations

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
from xyg.config import PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "animation_emit_cross_host.mjs"
FIXTURE_JSON = ROOT / "tests" / "fixtures" / "animation_emit_cross_host.json"

ANIM = {"duration": 250, "easing": "linear"}
TRANSITION_KEYS = [[1, 2], [3, 4]]

CASE_NAMES = (
    "scatter_animation",
    "line_animation",
    "scatter_no_animation",
    "line_no_animation",
    "scatter_log_animation",
    "line_decimated_animation",
    "area_animation",
    "area_no_animation",
    "area_decimated_animation",
    "density_animation",
    "density_no_animation",
    "hist_animation",
    "hist_no_animation",
    "bar_animation",
    "bar_no_animation",
    "segments_animation",
    "segments_no_animation",
    "ribbon_animation",
    "ribbon_no_animation",
    "mesh_animation",
    "mesh_no_animation",
    "density_transition_keys",
    "hist_transition_keys",
    "rect_transition_keys",
    "segments_transition_keys",
    "ribbon_transition_keys",
    "mesh_transition_keys",
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
    if name == "scatter_animation":
        fig.scatter([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        trace = fig.traces[-1]
        trace.id = 50
        trace.animation = dict(ANIM)
    elif name == "line_animation":
        fig.line([0.0, 1.0, 2.0], [0.0, 1.0, 2.0])
        trace = fig.traces[-1]
        trace.id = 51
        trace.animation = dict(ANIM)
    elif name == "scatter_no_animation":
        fig.scatter([1.0, 2.0], [1.0, 2.0])
        fig.traces[-1].id = 52
    elif name == "line_no_animation":
        fig.line([0.0, 1.0], [0.0, 1.0])
        fig.traces[-1].id = 53
    elif name == "scatter_log_animation":
        fig.set_axis("x", type_="log")
        fig.scatter([1.0, 10.0, 100.0], [1.0, 10.0, 100.0])
        trace = fig.traces[-1]
        trace.id = 54
        trace.animation = dict(ANIM)
    elif name == "line_decimated_animation":
        n = 10001
        xs = [float(i) for i in range(n)]
        ys = [float(i % 7) for i in range(n)]
        fig.line(xs, ys)
        trace = fig.traces[-1]
        trace.id = 55
        trace.animation = dict(ANIM)
    elif name == "area_animation":
        fig.area([0.0, 1.0, 2.0], [0.0, 1.0, 2.0])
        trace = fig.traces[-1]
        trace.id = 56
        trace.animation = dict(ANIM)
    elif name == "area_no_animation":
        fig.area([0.0, 1.0], [0.0, 1.0])
        fig.traces[-1].id = 57
    elif name == "area_decimated_animation":
        n = 10001
        xs = [float(i) for i in range(n)]
        ys = [float(i % 7) for i in range(n)]
        fig.area(xs, ys)
        trace = fig.traces[-1]
        trace.id = 58
        trace.animation = dict(ANIM)
    elif name == "density_animation":
        fig.scatter([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], density=True)
        trace = fig.traces[-1]
        trace.id = 59
        trace.animation = dict(ANIM)
    elif name == "density_no_animation":
        fig.scatter([1.0, 2.0], [1.0, 2.0], density=True)
        fig.traces[-1].id = 60
    elif name == "hist_animation":
        fig.histogram([0, 1, 1, 2], bins=2, range=(0, 2))
        trace = fig.traces[-1]
        trace.id = 61
        trace.animation = dict(ANIM)
    elif name == "hist_no_animation":
        fig.histogram([0, 1, 1, 2], bins=2, range=(0, 2))
        fig.traces[-1].id = 62
    elif name == "bar_animation":
        fig.bar([0, 1], [1, 2])
        trace = fig.traces[-1]
        trace.id = 63
        trace.animation = dict(ANIM)
    elif name == "bar_no_animation":
        fig.bar([0, 1], [1, 2])
        fig.traces[-1].id = 64
    elif name == "segments_animation":
        fig.segments([0.0, 1.0], [0.0, 1.0], [1.0, 2.0], [1.0, 2.0])
        trace = fig.traces[-1]
        trace.id = 65
        trace.animation = dict(ANIM)
    elif name == "segments_no_animation":
        fig.segments([0.0, 1.0], [0.0, 1.0], [1.0, 2.0], [1.0, 2.0])
        fig.traces[-1].id = 66
    elif name == "ribbon_animation":
        fig.ribbon([0.0], [1.0], [0.0], [1.0], [0.0], [1.0])
        trace = fig.traces[-1]
        trace.id = 67
        trace.animation = dict(ANIM)
    elif name == "ribbon_no_animation":
        fig.ribbon([0.0], [1.0], [0.0], [1.0], [0.0], [1.0])
        fig.traces[-1].id = 68
    elif name == "mesh_animation":
        fig.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0])
        trace = fig.traces[-1]
        trace.id = 69
        trace.animation = dict(ANIM)
    elif name == "mesh_no_animation":
        fig.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0])
        fig.traces[-1].id = 70
    elif name == "density_transition_keys":
        fig.scatter([0.0, 1.0], [0.0, 1.0], density=True)
        trace = fig.traces[-1]
        trace.id = 71
        trace.transition_keys = np.array(TRANSITION_KEYS, dtype=np.uint32)
    elif name == "hist_transition_keys":
        fig.histogram([0, 1, 1, 2], bins=2, range=(0, 2))
        trace = fig.traces[-1]
        trace.id = 72
        trace.transition_keys = np.array(TRANSITION_KEYS, dtype=np.uint32)
    elif name == "rect_transition_keys":
        fig.bar([0, 1], [1, 2])
        trace = fig.traces[-1]
        trace.id = 73
        trace.transition_keys = np.array(TRANSITION_KEYS, dtype=np.uint32)
    elif name == "segments_transition_keys":
        fig.segments([0.0, 1.0], [0.0, 1.0], [1.0, 2.0], [1.0, 2.0])
        trace = fig.traces[-1]
        trace.id = 74
        trace.transition_keys = np.array(TRANSITION_KEYS, dtype=np.uint32)
    elif name == "ribbon_transition_keys":
        fig.ribbon([0.0, 1.0], [1.0, 2.0], [0.0, 0.0], [1.0, 1.0], [0.0, 0.0], [1.0, 1.0])
        trace = fig.traces[-1]
        trace.id = 75
        trace.transition_keys = np.array(TRANSITION_KEYS, dtype=np.uint32)
    elif name == "mesh_transition_keys":
        fig.triangle_mesh([0.0, 1.0], [0.0, 0.0], [1.0, 2.0], [0.0, 0.0], [0.5, 1.5], [1.0, 1.0])
        trace = fig.traces[-1]
        trace.id = 76
        trace.transition_keys = np.array(TRANSITION_KEYS, dtype=np.uint32)
    else:
        raise KeyError(name)
    return fig


def _emit_meta(spec: dict) -> dict:
    trace = spec["traces"][0]
    meta = {
        "trace_id": trace["id"],
        "kind": trace["kind"],
        "n_points": trace["n_points"],
        "tier": trace["tier"],
        "animation": trace.get("animation"),
    }
    if "animation_fallback" in trace:
        meta["animation_fallback"] = trace.get("animation_fallback")
    if "keys" in trace:
        meta["has_keys"] = True
    return meta


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
            "node animation emit cross-host golden failed:\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def test_fixture_contract(fixture: dict) -> None:
    assert fixture["schema"] == "xyg.animation-emit-cross-host/v1"
    assert fixture["protocol"] == PROTOCOL_VERSION
    assert int(fixture["abi_version"]) == int(_native.ABI_VERSION)
    assert len(fixture["cases"]) == len(CASE_NAMES)
    assert {case["name"] for case in fixture["cases"]} == set(CASE_NAMES)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_python_matches_checked_in_fixture(case_name: str, fixture: dict) -> None:
    entry = next(case for case in fixture["cases"] if case["name"] == case_name)
    fig = _build_case(case_name)
    spec, _blob = fig.build_payload()
    meta = _emit_meta(spec)
    for key, value in entry.items():
        if key == "name":
            continue
        assert meta[key] == value


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_node_live_matches_python(case_name: str, node_golden: dict) -> None:
    node_case = next(case for case in node_golden["cases"] if case["name"] == case_name)
    fig = _build_case(case_name)
    spec, _blob = fig.build_payload()
    meta = _emit_meta(spec)
    for key, value in node_case.items():
        if key == "name":
            continue
        assert meta[key] == value
