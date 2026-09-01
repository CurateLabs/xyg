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
from xyg import kernels

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
    if spec["kind"] in (
        "probe",
        "stringlike",
        "real_numeric",
        "fixed_probe",
        "fold_codes_u8",
        "quantize_unit_u8",
    ):
        raise AssertionError(f"{spec['kind']} cases use dedicated helpers")
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


def _python_probe_case(spec: dict) -> bool:
    return kernels.factorize_use_native_probe(
        int(spec["distinct"]),
        int(spec["probe_len"]),
        int(spec["record_width"]),
    )


def _python_stringlike_case(spec: dict) -> bool:
    arr = np.asarray(spec["values"], dtype=object)
    return ch._object_column_is_stringlike(arr)


def _python_real_numeric_case(spec: dict) -> bool:
    arr = np.asarray(spec["values"], dtype=object)
    return ch._object_array_is_real_numeric(arr)


def _build_fixed_probe_array(spec: dict) -> np.ndarray:
    row_count = int(spec["row_count"])
    dtype = np.dtype(spec["dtype"])
    if row_count == 0:
        return np.asarray([], dtype=dtype)
    if "modulo" in spec:
        return np.asarray([i % int(spec["modulo"]) for i in range(row_count)], dtype=dtype)
    return np.arange(row_count, dtype=dtype)


def _python_fixed_probe_case(spec: dict) -> bool:
    arr = _build_fixed_probe_array(spec)
    return ch._use_native_fixed_factorizer(arr)


def _python_fold_codes_case(spec: dict) -> list[int]:
    codes = np.asarray(spec["codes"], dtype=np.uint32)
    folded = ch._folded_codes_u8(codes, int(spec["n_palette"]))
    return folded.tolist()


def _python_quantize_unit_case(spec: dict) -> list[int]:
    values = np.asarray(
        [float("nan") if value is None else float(value) for value in spec["values"]],
        dtype=np.float64,
    )
    domain = (float(spec["domain"][0]), float(spec["domain"][1]))
    return ch.quantize_unit_u8(values, domain).tolist()


FIXTURE_CASES = json.loads(FIXTURE.read_text())["cases"]
FACTORIZE_CASES = [
    c
    for c in FIXTURE_CASES
    if c["kind"]
    not in (
        "probe",
        "stringlike",
        "real_numeric",
        "fixed_probe",
        "fold_codes_u8",
        "quantize_unit_u8",
    )
]
PROBE_CASES = [c for c in FIXTURE_CASES if c["kind"] == "probe"]
FIXED_PROBE_CASES = [c for c in FIXTURE_CASES if c["kind"] == "fixed_probe"]
FOLD_CODES_CASES = [c for c in FIXTURE_CASES if c["kind"] == "fold_codes_u8"]
QUANTIZE_UNIT_CASES = [c for c in FIXTURE_CASES if c["kind"] == "quantize_unit_u8"]
STRINGLIKE_CASES = [c for c in FIXTURE_CASES if c["kind"] == "stringlike"]
REAL_NUMERIC_CASES = [c for c in FIXTURE_CASES if c["kind"] == "real_numeric"]


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


@pytest.mark.parametrize("spec", FACTORIZE_CASES, ids=lambda s: s["name"])
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


@pytest.mark.parametrize("spec", PROBE_CASES, ids=lambda s: s["name"])
def test_factorize_probe_cross_host(spec: dict, node_results: dict[str, dict]) -> None:
    use_native = _python_probe_case(spec)
    node = node_results[spec["name"]]
    assert use_native == node["use_native"]


@pytest.mark.parametrize("spec", FIXED_PROBE_CASES, ids=lambda s: s["name"])
def test_factorize_fixed_probe_cross_host(spec: dict, node_results: dict[str, dict]) -> None:
    use_native = _python_fixed_probe_case(spec)
    node = node_results[spec["name"]]
    assert use_native == node["use_native"]


@pytest.mark.parametrize("spec", FOLD_CODES_CASES, ids=lambda s: s["name"])
def test_fold_codes_u8_cross_host(spec: dict, node_results: dict[str, dict]) -> None:
    folded = _python_fold_codes_case(spec)
    node = node_results[spec["name"]]
    assert folded == node["folded"]


@pytest.mark.parametrize("spec", QUANTIZE_UNIT_CASES, ids=lambda s: s["name"])
def test_quantize_unit_u8_cross_host(spec: dict, node_results: dict[str, dict]) -> None:
    quantized = _python_quantize_unit_case(spec)
    node = node_results[spec["name"]]
    assert quantized == node["quantized"]


@pytest.mark.parametrize("spec", STRINGLIKE_CASES, ids=lambda s: s["name"])
def test_object_stringlike_cross_host(spec: dict, node_results: dict[str, dict]) -> None:
    stringlike = _python_stringlike_case(spec)
    node = node_results[spec["name"]]
    assert stringlike == node["stringlike"]


@pytest.mark.parametrize("spec", REAL_NUMERIC_CASES, ids=lambda s: s["name"])
def test_object_real_numeric_cross_host(spec: dict, node_results: dict[str, dict]) -> None:
    real_numeric = _python_real_numeric_case(spec)
    node = node_results[spec["name"]]
    assert real_numeric == node["real_numeric"]
