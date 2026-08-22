"""Bit-identical 4-node circle layout parity: Python host vs @curatelabs/xyg-node.

Shells ``node packages/xy-node/scripts/circle_layout_golden.mjs`` and compares
f64 positions (and §29 f32 encodings) against ``xy._graph.run_layout``.

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib \\
      uv run pytest tests/test_graph_node_parity.py -q
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

from xyg import _graph, _native
from xyg.config import PROTOCOL_VERSION
from xyg.lod import encode_f32_values

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "circle_layout_golden.mjs"


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


@pytest.fixture(scope="module")
def node_circle_golden() -> dict:
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
        pytest.fail(f"node circle golden failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return json.loads(proc.stdout)


def test_circle_layout_positions_bit_identical(node_circle_golden: dict) -> None:
    nodes = ["a", "b", "c", "d"]
    edges = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "a")]
    data = _graph.normalize_graph_inputs(nodes, edges)
    x, y, meta = _graph.run_layout(data, layout="circle", seed=1)

    assert meta["layout"] == "circle"
    assert node_circle_golden["layout"] == "circle"
    assert node_circle_golden["protocol"] == PROTOCOL_VERSION
    assert int(node_circle_golden["abi_version"]) == int(_native.ABI_VERSION)

    x_py = np.ascontiguousarray(x, dtype=np.float64)
    y_py = np.ascontiguousarray(y, dtype=np.float64)
    x_node = np.frombuffer(bytes.fromhex(node_circle_golden["x_f64_hex"]), dtype="<f8")
    y_node = np.frombuffer(bytes.fromhex(node_circle_golden["y_f64_hex"]), dtype="<f8")

    # Bit-identical f64 positions across hosts (same Rust layout kernel).
    assert x_py.tobytes() == x_node.tobytes()
    assert y_py.tobytes() == y_node.tobytes()
    np.testing.assert_array_equal(x_py, np.asarray(node_circle_golden["x"], dtype=np.float64))
    np.testing.assert_array_equal(y_py, np.asarray(node_circle_golden["y"], dtype=np.float64))

    assert meta["source_n_nodes"] == node_circle_golden["source_n_nodes"] == 4
    assert meta["source_n_edges"] == node_circle_golden["source_n_edges"] == 4
    assert meta["lod_tier"] == node_circle_golden["lod_tier"]
    np.testing.assert_array_equal(
        np.asarray(meta["member_of"], dtype=np.uint64),
        np.asarray(node_circle_golden["member_of"], dtype=np.uint64),
    )


def test_circle_encode_f32_bit_identical(node_circle_golden: dict) -> None:
    x = np.frombuffer(bytes.fromhex(node_circle_golden["x_f64_hex"]), dtype="<f8")
    y = np.frombuffer(bytes.fromhex(node_circle_golden["y_f64_hex"]), dtype="<f8")
    x_enc = encode_f32_values(x, 0.0, -4.0, 4.0)
    y_enc = encode_f32_values(y, 0.0, -4.0, 4.0)

    x_node = np.frombuffer(bytes.fromhex(node_circle_golden["x_f32_hex"]), dtype="<f4")
    y_node = np.frombuffer(bytes.fromhex(node_circle_golden["y_f32_hex"]), dtype="<f4")
    assert x_enc.values.tobytes() == x_node.tobytes()
    assert y_enc.values.tobytes() == y_node.tobytes()
    assert x_enc.meta["offset"] == pytest.approx(node_circle_golden["x_encode_meta"]["offset"])
    assert x_enc.meta["scale"] == pytest.approx(node_circle_golden["x_encode_meta"]["scale"])


def test_node_figure_payload_protocol(node_circle_golden: dict) -> None:
    """Optional: figure buildPayload protocol matches when node script is healthy."""
    del node_circle_golden
    if not _node_bin() or not LIB.is_file():
        pytest.skip("node / native lib unavailable")
    script = r"""
import { figure, PROTOCOL_VERSION } from './packages/xy-node/src/index.js';
const fig = figure({ width: 400, height: 300 });
fig.graph(['a','b','c','d'], [['a','b'],['b','c'],['c','d'],['d','a']], { layout: 'circle', seed: 1 });
const { spec, buffers } = fig.buildPayload();
const out = {
  protocol: spec.protocol,
  expected: PROTOCOL_VERSION,
  n_traces: spec.traces.length,
  kinds: spec.traces.map((t) => t.kind),
  has_graph: Array.isArray(spec.graph),
  buffer_bytes: buffers.length,
};
process.stdout.write(JSON.stringify(out));
"""
    env = os.environ.copy()
    env.setdefault("XYG_NATIVE_LIB", str(LIB))
    proc = subprocess.run(
        [_node_bin(), "--input-type=module", "-e", script],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    if proc.returncode != 0:
        pytest.fail(f"figure payload probe failed:\n{proc.stderr}")
    payload = json.loads(proc.stdout)
    assert payload["protocol"] == PROTOCOL_VERSION == payload["expected"]
    assert payload["kinds"] == ["segments", "scatter"]
    assert payload["has_graph"] is True
    assert payload["buffer_bytes"] > 0


if __name__ == "__main__":
    # Allow `python3 tests/test_graph_node_parity.py` as a smoke without pytest.
    sys.exit(pytest.main([__file__, "-q"]))
