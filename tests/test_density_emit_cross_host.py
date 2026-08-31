"""Cross-host density wire-metadata parity: Python vs @curatelabs/xyg-node.

Compares density spec fields that do not ride the §29 payload blob (colormap,
dropped_channels, channels_dropped, density sample channel attach) for forced-density
scatters.

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so \\
      uv run pytest tests/test_density_emit_cross_host.py -q
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from xyg import _native
from xyg._figure import Figure
from xyg.channels import StyleChannel
from xyg.config import PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "density_emit_cross_host.mjs"
FIXTURE_JSON = ROOT / "tests" / "fixtures" / "density_emit_cross_host.json"

SAMPLE_CASE_KEYS = frozenset(
    {
        "trace_id",
        "tier",
        "has_sample",
        "sample_n",
        "sample_visible",
        "sample_color",
        "sample_size",
        "sample_stroke",
        "sample_channels",
        "sample_x_offset",
        "sample_y_offset",
        "animation_fallback",
    }
)


def _case_keys(case_name: str, entry: dict) -> list[str]:
    if case_name.startswith("density_sample_"):
        return [key for key in entry if key in SAMPLE_CASE_KEYS]
    return [key for key in entry if key != "name"]


CASE_NAMES = (
    "scatter_density_colormap",
    "scatter_density_dropped_channels",
    "scatter_density_mean_color_categorical",
    "density_sample_color_size",
    "density_sample_stroke",
    "density_sample_style_channels",
    "density_sample_log_x_ship",
    "density_sample_transition_fallback",
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


def _strip_wire_buffers(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            key: _strip_wire_buffers(value)
            for key, value in obj.items()
            if key not in {"buf", "byte_offset", "col"}
        }
    if isinstance(obj, list):
        return [_strip_wire_buffers(item) for item in obj]
    return obj


def _build_case(name: str) -> Figure:
    if name == "scatter_density_colormap":
        fig = Figure(width=240, height=160)
        fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5], density=True, colormap="plasma")
        fig.traces[0].id = 21
        fig.traces[0].color_ch.colormap = "magma"
        return fig
    if name == "scatter_density_dropped_channels":
        fig = Figure(width=240, height=160)
        fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5], density=True, size=[1.0, 2.0, 3.0])
        fig.traces[0].id = 22
        return fig
    if name == "scatter_density_mean_color_categorical":
        fig = Figure(width=240, height=160)
        fig.scatter(
            [0.0, 1.0, 2.0, 3.0, 4.0],
            [0.0, 1.0, 0.5, 0.2, 0.8],
            density=True,
            color=["a", "b", "a", "c", "b"],
            size=[1.0, 2.0, 3.0, 4.0, 5.0],
        )
        fig.traces[0].id = 23
        return fig
    if name == "density_sample_color_size":
        fig = Figure(width=240, height=160)
        fig.scatter(
            [0.0, 1.0, 2.0, 3.0, 4.0],
            [0.0, 1.0, 0.5, 0.2, 0.8],
            density=True,
            color=["a", "b", "a", "c", "b"],
            size=[1.0, 2.0, 3.0, 4.0, 5.0],
        )
        fig.traces[0].id = 31
        return fig
    if name == "density_sample_stroke":
        fig = Figure(width=240, height=160)
        fig.scatter(
            [0.0, 1.0, 2.0],
            [0.0, 1.0, 0.5],
            density=True,
            stroke=["#f00", "#0f0", "#00f"],
        )
        fig.traces[0].id = 32
        return fig
    if name == "density_sample_style_channels":
        fig = Figure(width=240, height=160)
        fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5], density=True)
        fig.traces[0].id = 33
        fig.traces[0].style_channels = {
            "opacity": StyleChannel(
                values=np.array([0.5, 0.6, 0.7], dtype=np.float64),
                components=1,
                dtype="f32",
            )
        }
        return fig
    if name == "density_sample_log_x_ship":
        fig = Figure(width=240, height=160)
        fig.axis_options = {"x": {"type": "log"}, "y": {}}
        fig.scatter([1.0, 10.0, 100.0], [1.0, 10.0, 100.0], density=True)
        fig.traces[0].id = 34
        return fig
    if name == "density_sample_transition_fallback":
        fig = Figure(width=240, height=160)
        fig.scatter([0.0, 1.0], [0.0, 1.0], density=True)
        fig.traces[0].id = 35
        fig.traces[0].transition_keys = [[1, 2], [3, 4]]
        return fig
    raise KeyError(name)


def _density_wire_meta(spec: dict) -> dict:
    trace = spec["traces"][0]
    density = trace.get("density") or {}
    sample = density.get("sample") or {}
    return {
        "trace_id": trace["id"],
        "tier": trace.get("tier"),
        "density_colormap": density.get("colormap"),
        "density_dropped_channels": density.get("dropped_channels") or [],
        "density_channels_dropped": bool(density.get("channels_dropped")),
        "density_color_agg": density.get("color_agg"),
        "density_has_rgba": "rgba" in density,
        "has_sample": bool(sample),
        "sample_n": sample.get("n"),
        "sample_visible": sample.get("visible"),
        "sample_color": _strip_wire_buffers(sample.get("color")),
        "sample_size": _strip_wire_buffers(sample.get("size")),
        "sample_stroke": _strip_wire_buffers(sample.get("stroke")),
        "sample_channels": _strip_wire_buffers(sample.get("channels")),
        "sample_x_offset": (sample.get("x") or {}).get("offset")
        if isinstance(sample.get("x"), dict)
        else None,
        "sample_y_offset": (sample.get("y") or {}).get("offset")
        if isinstance(sample.get("y"), dict)
        else None,
        "animation_fallback": trace.get("animation_fallback"),
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
            f"node density emit cross-host golden failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def test_fixture_contract(fixture: dict) -> None:
    assert fixture["schema"] == "xyg.density-emit-cross-host/v1"
    assert fixture["protocol"] == PROTOCOL_VERSION
    assert int(fixture["abi_version"]) == int(_native.ABI_VERSION)
    assert len(fixture["cases"]) == len(CASE_NAMES)
    assert {case["name"] for case in fixture["cases"]} == set(CASE_NAMES)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_python_matches_checked_in_fixture(case_name: str, fixture: dict) -> None:
    entry = next(case for case in fixture["cases"] if case["name"] == case_name)
    spec, _blob = _build_case(case_name).build_payload()
    meta = _density_wire_meta(spec)
    for key in _case_keys(case_name, entry):
        assert meta[key] == entry[key], (key, meta[key], entry[key])


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_node_live_matches_python(case_name: str, node_golden: dict) -> None:
    node_case = next(case for case in node_golden["cases"] if case["name"] == case_name)
    spec, _blob = _build_case(case_name).build_payload()
    meta = _density_wire_meta(spec)
    for key in _case_keys(case_name, node_case):
        assert meta[key] == node_case[key], (key, meta[key], node_case[key])
