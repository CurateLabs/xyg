"""Cross-host scatter emit tier parity: Python vs @curatelabs/xyg-node.

Compares tier / n_marks for large/small scatters where Node trace flags
``force_direct`` / ``force_pyramid`` are ignored to match Python ``_emit_scatter``.

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so \\
      uv run pytest tests/test_force_emit_cross_host.py -q
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
from xyg.config import PROTOCOL_VERSION, SCATTER_DENSITY_THRESHOLD

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "force_emit_cross_host.mjs"
FIXTURE_JSON = ROOT / "tests" / "fixtures" / "force_emit_cross_host.json"


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
    if name == "scatter_large_auto_density":
        n = SCATTER_DENSITY_THRESHOLD + 1
        fig = Figure(width=240, height=160)
        fig.scatter(np.arange(n, dtype=np.float64) / n, np.arange(n, dtype=np.float64) / n)
        fig.traces[0].id = 31
        return fig
    if name == "scatter_small_auto_direct":
        n = 10_000
        fig = Figure(width=240, height=160)
        fig.scatter(np.arange(n, dtype=np.float64) / n, np.arange(n, dtype=np.float64) / n)
        fig.traces[0].id = 32
        return fig
    raise KeyError(name)


def _emit_meta(spec: dict) -> dict:
    trace = spec["traces"][0]
    return {
        "trace_id": trace["id"],
        "n_points": trace["n_points"],
        "tier": trace.get("tier"),
        "n_marks": trace.get("n_marks"),
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
            f"node force emit cross-host golden failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def test_fixture_contract(fixture: dict) -> None:
    assert fixture["schema"] == "xyg.force-emit-cross-host/v1"
    assert fixture["protocol"] == PROTOCOL_VERSION
    assert int(fixture["abi_version"]) == int(_native.ABI_VERSION)
    assert fixture["scatter_density_threshold"] == SCATTER_DENSITY_THRESHOLD
    assert len(fixture["cases"]) == 2
    assert {case["name"] for case in fixture["cases"]} == {
        "scatter_large_auto_density",
        "scatter_small_auto_direct",
    }


@pytest.mark.parametrize(
    "case_name",
    ["scatter_large_auto_density", "scatter_small_auto_direct"],
)
def test_python_matches_checked_in_fixture(case_name: str, fixture: dict) -> None:
    entry = next(case for case in fixture["cases"] if case["name"] == case_name)
    spec, _blob = _build_case(case_name).build_payload()
    meta = _emit_meta(spec)
    assert meta["trace_id"] == entry["trace_id"]
    assert meta["tier"] == entry["tier"]
    assert meta["n_marks"] == entry["n_marks"]


@pytest.mark.parametrize(
    "case_name",
    ["scatter_large_auto_density", "scatter_small_auto_direct"],
)
def test_node_live_matches_python(case_name: str, node_golden: dict) -> None:
    node_case = next(case for case in node_golden["cases"] if case["name"] == case_name)
    spec, _blob = _build_case(case_name).build_payload()
    meta = _emit_meta(spec)
    assert meta["tier"] == node_case["tier"]
    assert meta["n_marks"] == node_case["n_marks"]
