"""Cross-host sorted_display_label_remap parity: Python vs Node."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from xyg import kernels

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sorted_display_label_remap_cross_host.json"
NODE_SCRIPT = (
    ROOT / "packages" / "xy-node" / "scripts" / "sorted_display_label_remap_cross_host.mjs"
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


def _python_results() -> dict[str, dict]:
    fixture = json.loads(FIXTURE.read_text())
    out: dict[str, dict] = {}
    for spec in fixture["cases"]:
        counts = None
        if "counts" in spec:
            counts = np.asarray(spec["counts"], dtype=np.uint64)
        categories, remap, agg = kernels.sorted_display_label_remap(spec["labels"], counts)
        out[spec["name"]] = {
            "categories": categories,
            "remap": remap,
            "counts": None if agg is None else agg,
        }
    return out


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
    rows = json.loads(proc.stdout)
    return {row["name"]: row for row in rows}


@pytest.mark.parametrize(
    "name",
    [spec["name"] for spec in json.loads(FIXTURE.read_text())["cases"]],
)
def test_sorted_display_label_remap_cross_host(name: str, node_results: dict[str, dict]) -> None:
    py = _python_results()[name]
    node = node_results[name]
    assert py["categories"] == node["categories"]
    np.testing.assert_array_equal(
        py["remap"],
        np.asarray(node["remap"], dtype=py["remap"].dtype),
    )
    if py["counts"] is None:
        assert node["counts"] is None
    else:
        np.testing.assert_array_equal(
            py["counts"],
            np.asarray(node["counts"], dtype=np.uint64),
        )
