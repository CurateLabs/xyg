"""Cross-host LOD parity: Python lod.py vs Node encode.js kernel delegates."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from xyg import kernels, lod

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "lod_cross_host.json"
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "lod_cross_host.mjs"


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


def _sha_f32(values: np.ndarray) -> str:
    arr = np.ascontiguousarray(values, dtype=np.float32)
    return hashlib.sha256(arr.tobytes()).hexdigest()


def _python_case(spec: dict) -> dict:
    if spec["kind"] == "lod_plan":
        exact, mode, gw, gh = kernels.lod_plan(
            spec["visible"],
            float(spec["budget"]),
            bool(spec["in_drill"]),
            exit_factor=float(spec["exit_factor"]),
            width=int(spec["width"]),
            height=int(spec["height"]),
            target_per_cell=float(spec["target_per_cell"]),
        )
        return {
            "name": spec["name"],
            "exact": exact,
            "mode": mode,
            "grid_w": gw,
            "grid_h": gh,
        }
    if spec["kind"] == "drill_decision":
        exact = kernels.drill_decision(
            spec["visible"],
            float(spec["budget"]),
            bool(spec["in_drill"]),
            float(spec["exit_factor"]),
        )
        return {"name": spec["name"], "exact": exact}
    if spec["kind"] == "aligned_window":
        lo, hi = kernels.aligned_window(
            float(spec["lo"]),
            float(spec["hi"]),
            float(spec["extent_lo"]),
            float(spec["extent_hi"]),
            float(spec["pad"]),
        )
        return {"name": spec["name"], "lo": lo, "hi": hi}
    if spec["kind"] == "aligned_window_pair":
        a = _python_case({**spec["a"], "name": f"{spec['name']}_a", "kind": "aligned_window"})
        b = _python_case({**spec["b"], "name": f"{spec['name']}_b", "kind": "aligned_window"})
        return {
            "name": spec["name"],
            "a": [a["lo"], a["hi"]],
            "b": [b["lo"], b["hi"]],
            "equal": a["lo"] == b["lo"] and a["hi"] == b["hi"],
        }
    column = lod.encode_f32_values(
        spec["values"],
        float(spec["offset"]),
        float(spec["lo"]),
        float(spec["hi"]),
        kind=spec.get("kind"),
    )
    return {
        "name": spec["name"],
        "meta": column.meta,
        "values_sha256": _sha_f32(column.values),
        "length": len(column.values),
    }


@pytest.fixture(scope="module")
def node_results() -> dict[str, dict]:
    if not _node_bin() or not NODE_SCRIPT.is_file():
        pytest.skip("node cross-host script missing")
    env = os.environ.copy()
    env.setdefault("XYG_NATIVE_LIB", str(LIB))
    proc = subprocess.run(
        [_node_bin(), str(NODE_SCRIPT)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(proc.stdout.strip())
    return {case["name"]: case for case in payload["cases"]}


@pytest.mark.parametrize("spec", json.loads(FIXTURE.read_text())["cases"], ids=lambda s: s["name"])
def test_lod_cross_host(spec: dict, node_results: dict[str, dict]) -> None:
    py = _python_case(spec)
    node = node_results[spec["name"]]
    assert py["name"] == node["name"]
    if spec["kind"] == "lod_plan":
        assert py["exact"] == node["exact"]
        assert py["mode"] == node["mode"]
        assert py["grid_w"] == node["grid_w"]
        assert py["grid_h"] == node["grid_h"]
        return
    if spec["kind"] == "drill_decision":
        assert py["exact"] == node["exact"]
        return
    if spec["kind"] == "aligned_window":
        assert py["lo"] == node["lo"]
        assert py["hi"] == node["hi"]
        return
    if spec["kind"] == "aligned_window_pair":
        assert py["equal"] is True
        assert node["equal"] is True
        assert py["a"] == node["a"]
        assert py["b"] == node["b"]
        return
    assert py["meta"] == node["meta"]
    assert py["values_sha256"] == node["values_sha256"]
    assert py["length"] == node["length"]
