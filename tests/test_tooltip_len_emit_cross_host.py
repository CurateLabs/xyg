"""Cross-host tooltip_rows length parity: Python vs @curatelabs/xyg-node.

Compares attach/reject behavior for scatter, segments, and ribbon emit paths
where Python ``_attach_tooltip_rows`` length-checks against ``n_points``.

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so \\
      uv run pytest tests/test_tooltip_len_emit_cross_host.py -q
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from xyg import _native
from xyg._figure import Figure
from xyg.config import PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "tooltip_len_emit_cross_host.mjs"
FIXTURE_JSON = ROOT / "tests" / "fixtures" / "tooltip_len_emit_cross_host.json"

CASE_NAMES = (
    "scatter_tooltip_ok",
    "segments_tooltip_ok",
    "ribbon_tooltip_ok",
    "scatter_tooltip_mismatch",
    "segments_tooltip_mismatch",
    "ribbon_tooltip_mismatch",
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
    if name == "scatter_tooltip_ok":
        fig.scatter([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        fig.traces[-1].tooltip_rows = [{"rank": 1}, {"rank": 2}, {"rank": 3}]
        fig.traces[-1].id = 40
    elif name == "segments_tooltip_ok":
        fig.segments([0.0, 1.0], [0.0, 1.0], [1.0, 2.0], [1.0, 2.0])
        fig.traces[-1].tooltip_rows = [{"id": "a"}, {"id": "b"}]
        fig.traces[-1].id = 41
    elif name == "ribbon_tooltip_ok":
        fig.ribbon(
            [0.0, 1.0],
            [1.0, 2.0],
            [0.0, 1.0],
            [1.0, 2.0],
            [0.5, 1.5],
            [1.5, 2.5],
        )
        fig.traces[-1].tooltip_rows = [{"id": "a"}, {"id": "b"}]
        fig.traces[-1].id = 42
    elif name == "scatter_tooltip_mismatch":
        fig.scatter([0.0, 1.0], [0.0, 1.0])
        fig.traces[-1].tooltip_rows = [{"id": "a"}]
        fig.traces[-1].id = 43
    elif name == "segments_tooltip_mismatch":
        fig.segments([0.0, 1.0], [0.0, 1.0], [1.0, 2.0], [1.0, 2.0])
        fig.traces[-1].tooltip_rows = [{"id": "a"}]
        fig.traces[-1].id = 44
    elif name == "ribbon_tooltip_mismatch":
        fig.ribbon([0.0], [1.0], [0.0], [1.0], [0.0], [1.0])
        fig.traces[-1].tooltip_rows = [{"id": "a"}, {"id": "b"}]
        fig.traces[-1].id = 45
    else:
        raise KeyError(name)
    return fig


def _emit_meta(spec: dict) -> dict:
    trace = spec["traces"][0]
    return {
        "trace_id": trace["id"],
        "kind": trace["kind"],
        "n_points": trace["n_points"],
        "tooltip_rows": trace.get("tooltip_rows"),
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
            "node tooltip-len emit cross-host golden failed:\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def test_fixture_contract(fixture: dict) -> None:
    assert fixture["schema"] == "xyg.tooltip-len-emit-cross-host/v1"
    assert fixture["protocol"] == PROTOCOL_VERSION
    assert int(fixture["abi_version"]) == int(_native.ABI_VERSION)
    assert len(fixture["cases"]) == len(CASE_NAMES)
    assert {case["name"] for case in fixture["cases"]} == set(CASE_NAMES)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_python_matches_checked_in_fixture(case_name: str, fixture: dict) -> None:
    entry = next(case for case in fixture["cases"] if case["name"] == case_name)
    fig = _build_case(case_name)
    if entry["expect_error"]:
        with pytest.raises(ValueError, match=re.escape(entry["error_match"])):
            fig.build_payload()
        return
    spec, _blob = fig.build_payload()
    meta = _emit_meta(spec)
    assert meta["trace_id"] == entry["trace_id"]
    assert meta["kind"] == entry["kind"]
    assert meta["n_points"] == entry["n_points"]
    assert meta["tooltip_rows"] == entry["tooltip_rows"]


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_node_live_matches_python(case_name: str, node_golden: dict) -> None:
    node_case = next(case for case in node_golden["cases"] if case["name"] == case_name)
    fig = _build_case(case_name)
    if node_case["expect_error"]:
        with pytest.raises(ValueError, match=re.escape(node_case["error_match"])):
            fig.build_payload()
        assert node_case.get("error_message") is not None
        return
    spec, _blob = fig.build_payload()
    meta = _emit_meta(spec)
    assert meta["tooltip_rows"] == node_case["tooltip_rows"]
    assert meta["n_points"] == node_case["n_points"]
