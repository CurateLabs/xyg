"""Cross-host category_label parity: Python vs Node."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from xyg import channels as ch

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "category_label_cross_host.json"
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "category_label_cross_host.mjs"


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


def _decode_case(spec: dict) -> object:
    kind = spec["kind"]
    if kind == "null":
        return None
    if kind == "nan":
        return math.nan
    if kind == "string":
        return spec["value"]
    if kind == "bytes":
        return bytes.fromhex(spec["hex"])
    if kind == "int":
        return spec["value"]
    if kind == "bool":
        return spec["value"]
    raise AssertionError(f"unknown case kind {kind}")


def _python_results() -> dict[str, str]:
    fixture = json.loads(FIXTURE.read_text())
    return {spec["name"]: ch.category_label(_decode_case(spec)) for spec in fixture["cases"]}


@pytest.fixture(scope="module")
def node_results() -> dict[str, str]:
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
    return {row["name"]: row["label"] for row in rows}


def test_category_label_cross_host(node_results: dict[str, str]) -> None:
    py = _python_results()
    assert set(py) == set(node_results)
    for name, label in py.items():
        assert label == node_results[name], name
