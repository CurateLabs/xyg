"""Cross-host density wire-metadata parity: Python vs @curatelabs/xyg-node.

Compares density spec fields that do not ride the §29 payload blob (colormap,
dropped_channels, channels_dropped) for forced-density scatters.

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

import pytest

from xyg import _native
from xyg._figure import Figure
from xyg.config import PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "density_emit_cross_host.mjs"
FIXTURE_JSON = ROOT / "tests" / "fixtures" / "density_emit_cross_host.json"


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
    raise KeyError(name)


def _density_wire_meta(spec: dict) -> dict:
    trace = spec["traces"][0]
    density = trace.get("density") or {}
    return {
        "trace_id": trace["id"],
        "tier": trace.get("tier"),
        "density_colormap": density.get("colormap"),
        "density_dropped_channels": density.get("dropped_channels") or [],
        "density_channels_dropped": bool(density.get("channels_dropped")),
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
    assert len(fixture["cases"]) == 2
    assert {case["name"] for case in fixture["cases"]} == {
        "scatter_density_colormap",
        "scatter_density_dropped_channels",
    }


@pytest.mark.parametrize(
    "case_name",
    ["scatter_density_colormap", "scatter_density_dropped_channels"],
)
def test_python_matches_checked_in_fixture(case_name: str, fixture: dict) -> None:
    entry = next(case for case in fixture["cases"] if case["name"] == case_name)
    spec, _blob = _build_case(case_name).build_payload()
    meta = _density_wire_meta(spec)
    assert meta["trace_id"] == entry["trace_id"]
    assert meta["tier"] == entry["tier"]
    assert meta["density_colormap"] == entry["density_colormap"]
    assert meta["density_dropped_channels"] == entry["density_dropped_channels"]
    assert meta["density_channels_dropped"] == entry["density_channels_dropped"]


@pytest.mark.parametrize(
    "case_name",
    ["scatter_density_colormap", "scatter_density_dropped_channels"],
)
def test_node_live_matches_python(case_name: str, node_golden: dict) -> None:
    node_case = next(case for case in node_golden["cases"] if case["name"] == case_name)
    spec, _blob = _build_case(case_name).build_payload()
    meta = _density_wire_meta(spec)
    assert meta["density_colormap"] == node_case["density_colormap"]
    assert meta["density_dropped_channels"] == node_case["density_dropped_channels"]
    assert meta["density_channels_dropped"] == node_case["density_channels_dropped"]
