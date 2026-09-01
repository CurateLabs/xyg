"""Cross-host categorical factorization parity: Python vs Node."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from xyg import channels as ch

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "factorize_cross_host.json"
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "factorize_cross_host.mjs"


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


def _python_case(spec: dict) -> tuple[list[str], np.ndarray, np.ndarray | None]:
    if spec["kind"] == "uint8":
        arr = np.asarray(spec["values"], dtype=np.uint8)
    elif spec["kind"] == "object":
        arr = np.asarray(spec["values"], dtype=object)
    elif spec["kind"] == "unicode" and "seed" in spec:
        rng = np.random.default_rng(spec["seed"])
        categories = np.asarray([f"group-{i:03d}" for i in range(spec["category_count"])])
        labels = categories[rng.integers(0, len(categories), size=spec["row_count"])]
        arr = labels.astype(object)
    else:
        arr = np.asarray(spec["values"], dtype=str)
    cats, codes, counts = ch._factorize_categories(arr)
    return cats, codes, counts


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
def test_factorize_cross_host(spec: dict, node_results: dict[str, dict]) -> None:
    cats, codes, counts = _python_case(spec)
    node = node_results[spec["name"]]
    assert cats == node["categories"]
    np.testing.assert_array_equal(codes, np.asarray(node["codes"], dtype=codes.dtype))
    if counts is None:
        assert node["counts"] is None
    else:
        assert node["counts"] is not None
        np.testing.assert_array_equal(counts, np.asarray(node["counts"], dtype=np.uint64))
