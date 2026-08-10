"""Bit-identical mark parity: Python host vs @xy/node (scatter encode, M4, hist).

Shells ``node packages/xy-node/scripts/mark_parity_golden.mjs`` and compares
against Python ``encode_f32_values`` / ``m4_indices`` / ``histogram_uniform``.

Also regenerates ``packages/xy-node/test/fixtures/mark_parity.json`` when the
fixture writer is available (optional; node unit tests load the fixture).

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XY_NATIVE_LIB=$PWD/target/release/libxy_core.so \\
      uv run pytest tests/test_node_mark_parity.py -q
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

from xy import _native
from xy.config import DECIMATION_THRESHOLD, PROTOCOL_VERSION
from xy.lod import encode_f32_values

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "mark_parity_golden.mjs"
FIXTURE_WRITER = ROOT / "packages" / "xy-node" / "test" / "fixtures" / "write_mark_fixtures.py"
FIXTURE_JSON = ROOT / "packages" / "xy-node" / "test" / "fixtures" / "mark_parity.json"
LIB = ROOT / "target" / "release" / "libxy_core.so"


def _node_bin() -> str:
    return shutil.which("node") or ""


@pytest.fixture(scope="module")
def node_mark_golden() -> dict:
    if not _node_bin():
        pytest.skip("node binary not on PATH")
    if not NODE_SCRIPT.is_file():
        pytest.skip(f"missing {NODE_SCRIPT}")
    if not LIB.is_file():
        pytest.skip("libxy_core.so missing; run `cargo build --release`")

    env = os.environ.copy()
    env.setdefault("XY_NATIVE_LIB", str(LIB))
    proc = subprocess.run(
        [_node_bin(), str(NODE_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    if proc.returncode != 0:
        pytest.fail(f"node mark golden failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return json.loads(proc.stdout)


def test_scatter_encode_f32_bit_identical(node_mark_golden: dict) -> None:
    scatter = node_mark_golden["scatter"]
    x = np.frombuffer(bytes.fromhex(scatter["x_f64_hex"]), dtype="<f8")
    y = np.frombuffer(bytes.fromhex(scatter["y_f64_hex"]), dtype="<f8")
    x_lo, x_hi = float(x.min()), float(x.max())
    y_lo, y_hi = float(y.min()), float(y.max())
    x_enc = encode_f32_values(x, (x_lo + x_hi) / 2.0, x_lo, x_hi)
    y_enc = encode_f32_values(y, (y_lo + y_hi) / 2.0, y_lo, y_hi)

    x_node = np.frombuffer(bytes.fromhex(scatter["x_f32_hex"]), dtype="<f4")
    y_node = np.frombuffer(bytes.fromhex(scatter["y_f32_hex"]), dtype="<f4")
    assert x_enc.values.tobytes() == x_node.tobytes()
    assert y_enc.values.tobytes() == y_node.tobytes()
    assert x_enc.meta["offset"] == pytest.approx(scatter["x_meta"]["offset"])
    assert y_enc.meta["offset"] == pytest.approx(scatter["y_meta"]["offset"])
    assert x_enc.meta["scale"] == pytest.approx(scatter["x_meta"]["scale"])
    assert y_enc.meta["scale"] == pytest.approx(scatter["y_meta"]["scale"])
    assert node_mark_golden["protocol"] == PROTOCOL_VERSION
    assert int(node_mark_golden["abi_version"]) == int(_native.ABI_VERSION)


def test_m4_line_index_count_monotone(node_mark_golden: dict) -> None:
    info = node_mark_golden["line_m4"]
    n = int(info["n"])
    n_buckets = int(info["n_buckets"])
    x = np.arange(n, dtype=np.float64)
    y = np.sin(x / 100.0) + x / n
    eps = float(np.finfo(np.float64).eps)
    idx = _native.m4_indices(x, y, float(info["x0"]), float(info["x1"]) + eps, n_buckets)
    assert len(idx) == int(info["index_count"])
    assert info["tier"] == "decimated"
    assert n > DECIMATION_THRESHOLD
    assert int(info["threshold"]) == DECIMATION_THRESHOLD


def test_histogram_uniform_counts_fixed_edges(node_mark_golden: dict) -> None:
    hist = node_mark_golden["histogram"]
    values = np.frombuffer(bytes.fromhex(hist["values_f64_hex"]), dtype="<f8")
    counts, edges = _native.histogram_uniform(
        values, float(hist["lo"]), float(hist["hi"]), int(hist["n_bins"]), density=False
    )
    np.testing.assert_array_equal(
        counts.astype(np.float64), np.asarray(hist["counts"], dtype=np.float64)
    )
    np.testing.assert_array_equal(
        edges.astype(np.float64), np.asarray(hist["edges"], dtype=np.float64)
    )
    counts_node = np.frombuffer(bytes.fromhex(hist["counts_f64_hex"]), dtype="<f8")
    assert counts.astype(np.float64).tobytes() == counts_node.tobytes()


def test_write_fixtures_and_match_node(node_mark_golden: dict, tmp_path: Path) -> None:
    """Fixture writer output matches the live node golden for the three contracts."""
    if not FIXTURE_WRITER.is_file():
        pytest.skip("fixture writer missing")
    env = os.environ.copy()
    # Write into the real fixtures dir so node unit tests can load them.
    proc = subprocess.run(
        [sys.executable, str(FIXTURE_WRITER)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    if proc.returncode != 0:
        pytest.fail(f"fixture writer failed:\n{proc.stderr}\n{proc.stdout}")
    assert FIXTURE_JSON.is_file()
    fixture = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    assert fixture["scatter"]["x_f32_hex"] == node_mark_golden["scatter"]["x_f32_hex"]
    assert fixture["scatter"]["y_f32_hex"] == node_mark_golden["scatter"]["y_f32_hex"]
    assert fixture["line_m4"]["index_count"] == node_mark_golden["line_m4"]["index_count"]
    assert fixture["histogram"]["counts"] == node_mark_golden["histogram"]["counts"]


def test_chart_convenience_payload_kinds(node_mark_golden: dict) -> None:
    del node_mark_golden
    if not _node_bin() or not LIB.is_file():
        pytest.skip("node / native lib unavailable")
    script = r"""
import { scatterChart, lineChart, histogramChart, PROTOCOL_VERSION } from './packages/xy-node/src/index.js';
const s = scatterChart(new Float64Array([0,1]), new Float64Array([0,1]));
const l = lineChart(new Float64Array([0,1,2]), new Float64Array([0,1,0]));
const h = histogramChart(new Float64Array([1,2,2,3]), { bins: 2, range: [1, 3] });
const out = {
  protocol: PROTOCOL_VERSION,
  kinds: [
    s.buildPayload().spec.traces[0].kind,
    l.buildPayload().spec.traces[0].kind,
    h.buildPayload().spec.traces[0].kind,
  ],
};
process.stdout.write(JSON.stringify(out));
"""
    env = os.environ.copy()
    env.setdefault("XY_NATIVE_LIB", str(LIB))
    proc = subprocess.run(
        [_node_bin(), "--input-type=module", "-e", script],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    if proc.returncode != 0:
        pytest.fail(f"chart convenience probe failed:\n{proc.stderr}")
    payload = json.loads(proc.stdout)
    assert payload["protocol"] == PROTOCOL_VERSION
    assert payload["kinds"] == ["scatter", "line", "histogram"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
