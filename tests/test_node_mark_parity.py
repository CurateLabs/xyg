"""Bit-identical mark parity: Python host vs @curatelabs/xyg-node (scatter encode, M4, hist, batch-2).

Shells ``node packages/xy-node/scripts/mark_parity_golden.mjs`` and compares
against Python ``encode_f32_values`` / ``m4_indices`` / ``histogram_uniform`` /
``box_stats`` / ``weighted_ecdf`` / ``heatmap_rgba`` / ``hexbin`` / ``violin_density``.

Also regenerates ``packages/xy-node/test/fixtures/mark_parity.json`` when the
fixture writer is available (optional; node unit tests load the fixture).

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib \\
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

from xyg import _native, kernels
from xyg.config import DECIMATION_THRESHOLD, PROTOCOL_VERSION
from xyg.lod import encode_f32_values

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "mark_parity_golden.mjs"
FIXTURE_WRITER = ROOT / "packages" / "xy-node" / "test" / "fixtures" / "write_mark_fixtures.py"
FIXTURE_JSON = ROOT / "packages" / "xy-node" / "test" / "fixtures" / "mark_parity.json"


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
def node_mark_golden() -> dict:
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


def test_area_stable_sort(node_mark_golden: dict) -> None:
    area = node_mark_golden["area"]
    x = np.frombuffer(bytes.fromhex(area["x_f64_hex"]), dtype="<f8")
    y = np.frombuffer(bytes.fromhex(area["y_f64_hex"]), dtype="<f8")
    order = np.argsort(x, kind="stable")
    x_sorted = np.frombuffer(bytes.fromhex(area["x_sorted_f64_hex"]), dtype="<f8")
    y_sorted = np.frombuffer(bytes.fromhex(area["y_sorted_f64_hex"]), dtype="<f8")
    np.testing.assert_array_equal(x[order], x_sorted)
    np.testing.assert_array_equal(y[order], y_sorted)
    assert int(area["composed_base_len"]) == len(x)


def test_bar_rect_geometry(node_mark_golden: dict) -> None:
    bar = node_mark_golden["bar"]
    x = np.frombuffer(bytes.fromhex(bar["x_f64_hex"]), dtype="<f8")
    y = np.frombuffer(bytes.fromhex(bar["y_f64_hex"]), dtype="<f8")
    half = float(bar["width"]) / 2.0
    x0 = np.frombuffer(bytes.fromhex(bar["x0_f64_hex"]), dtype="<f8")
    x1 = np.frombuffer(bytes.fromhex(bar["x1_f64_hex"]), dtype="<f8")
    y0 = np.frombuffer(bytes.fromhex(bar["y0_f64_hex"]), dtype="<f8")
    y1 = np.frombuffer(bytes.fromhex(bar["y1_f64_hex"]), dtype="<f8")
    np.testing.assert_array_equal(x0, x - half)
    np.testing.assert_array_equal(x1, x + half)
    np.testing.assert_array_equal(y0, np.zeros_like(y))
    np.testing.assert_array_equal(y1, y)


def test_box_stats_tukey(node_mark_golden: dict) -> None:
    box = node_mark_golden["box"]
    values = np.frombuffer(bytes.fromhex(box["values_f64_hex"]), dtype="<f8")
    q1, med, q3, low, high, outliers = kernels.box_stats(values)
    assert q1 == pytest.approx(float(box["q1"]))
    assert med == pytest.approx(float(box["median"]))
    assert q3 == pytest.approx(float(box["q3"]))
    assert low == pytest.approx(float(box["low"]))
    assert high == pytest.approx(float(box["high"]))
    node_out = np.frombuffer(bytes.fromhex(box["outliers_f64_hex"]), dtype="<f8")
    np.testing.assert_array_equal(outliers.astype(np.float64), node_out)
    assert int(box["n_outliers"]) == len(outliers)


def test_ecdf_weighted_exact(node_mark_golden: dict) -> None:
    ecdf = node_mark_golden["ecdf"]
    values = np.frombuffer(bytes.fromhex(ecdf["values_f64_hex"]), dtype="<f8")
    weights = np.ones(len(values), dtype=np.float64)
    x_py, y_py = kernels.weighted_ecdf(values, weights)
    x_node = np.frombuffer(bytes.fromhex(ecdf["x_f64_hex"]), dtype="<f8")
    y_node = np.frombuffer(bytes.fromhex(ecdf["y_f64_hex"]), dtype="<f8")
    np.testing.assert_array_equal(x_py, x_node)
    np.testing.assert_array_equal(y_py, y_node)
    assert int(ecdf["n_points"]) == len(x_py)


def test_segments_pass_through(node_mark_golden: dict) -> None:
    seg = node_mark_golden["segments"]
    assert int(seg["n"]) == 2
    for key in ("x0", "y0", "x1", "y1"):
        arr = np.frombuffer(bytes.fromhex(seg[f"{key}_f64_hex"]), dtype="<f8")
        assert arr.shape == (2,)


def test_heatmap_rgba_colormap(node_mark_golden: dict) -> None:
    hm = node_mark_golden["heatmap"]
    z = np.frombuffer(bytes.fromhex(hm["z_f64_hex"]), dtype="<f8")
    stops = np.frombuffer(bytes.fromhex(hm["stops_u8_hex"]), dtype=np.uint8).reshape(-1, 3)
    rgba_py = kernels.heatmap_rgba(z, int(hm["cols"]), int(hm["rows"]), stops, 255)
    rgba_node = np.frombuffer(bytes.fromhex(hm["rgba_u8_hex"]), dtype=np.uint8)
    assert rgba_py.reshape(-1).tobytes() == rgba_node.tobytes()


def test_hexbin_native_lattice(node_mark_golden: dict) -> None:
    hx = node_mark_golden["hexbin"]
    x = np.frombuffer(bytes.fromhex(hx["x_f64_hex"]), dtype="<f8")
    y = np.frombuffer(bytes.fromhex(hx["y_f64_hex"]), dtype="<f8")
    w, h = hx["gridsize"]
    xr = tuple(hx["range"][0])
    yr = tuple(hx["range"][1])
    cx, cy, metric, counts, dx, dy = kernels.hexbin(
        x,
        y,
        gridsize=(int(w), int(h)),
        range=(xr, yr),
        mincnt=int(hx["mincnt"]),
        reduce=hx["reduce"],
    )
    assert len(cx) == int(hx["n_bins"])
    np.testing.assert_array_equal(
        cx, np.frombuffer(bytes.fromhex(hx["centers_x_f64_hex"]), dtype="<f8")
    )
    np.testing.assert_array_equal(
        cy, np.frombuffer(bytes.fromhex(hx["centers_y_f64_hex"]), dtype="<f8")
    )
    np.testing.assert_array_equal(
        metric, np.frombuffer(bytes.fromhex(hx["metrics_f64_hex"]), dtype="<f8")
    )
    np.testing.assert_array_equal(
        counts, np.frombuffer(bytes.fromhex(hx["counts_f64_hex"]), dtype="<f8")
    )
    assert dx == pytest.approx(float(hx["dx"]))
    assert dy == pytest.approx(float(hx["dy"]))


def test_violin_density_kernel(node_mark_golden: dict) -> None:
    v = node_mark_golden["violin"]
    values = np.frombuffer(bytes.fromhex(v["values_f64_hex"]), dtype="<f8")
    edges_py, density_py = kernels.violin_density(values, int(v["bins"]))
    edges_node = np.frombuffer(bytes.fromhex(v["edges_f64_hex"]), dtype="<f8")
    density_node = np.frombuffer(bytes.fromhex(v["density_f64_hex"]), dtype="<f8")
    np.testing.assert_array_equal(edges_py, edges_node)
    np.testing.assert_array_equal(density_py, density_node)
    assert int(v["n_rects"]) == int(v["bins"])


def test_write_fixtures_and_match_node(node_mark_golden: dict, tmp_path: Path) -> None:
    """Fixture writer output matches the live node golden for shared contracts."""
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
    assert fixture["box"]["q1"] == node_mark_golden["box"]["q1"]
    assert fixture["hexbin"]["n_bins"] == node_mark_golden["hexbin"]["n_bins"]
    assert fixture["heatmap"]["rgba_u8_hex"] == node_mark_golden["heatmap"]["rgba_u8_hex"]


def test_chart_convenience_payload_kinds(node_mark_golden: dict) -> None:
    del node_mark_golden
    if not _node_bin() or not LIB.is_file():
        pytest.skip("node / native lib unavailable")
    script = r"""
import {
  scatterChart, lineChart, histogramChart, areaChart, barChart, boxChart,
  ecdfChart, heatmapChart, hexbinChart, violinChart, PROTOCOL_VERSION,
} from './packages/xy-node/src/index.js';
const s = scatterChart(new Float64Array([0,1]), new Float64Array([0,1]));
const l = lineChart(new Float64Array([0,1,2]), new Float64Array([0,1,0]));
const h = histogramChart(new Float64Array([1,2,2,3]), { bins: 2, range: [1, 3] });
const a = areaChart(new Float64Array([0,1,2]), new Float64Array([0,1,0]), { base: 0 });
const b = barChart(new Float64Array([0,1]), new Float64Array([1,2]));
const bx = boxChart(new Float64Array([1,2,3,4,5]));
const e = ecdfChart(new Float64Array([1,2,3]));
const hm = heatmapChart(new Float64Array([0,1,0.5,1]), { rows: 2, cols: 2 });
const hx = hexbinChart(new Float64Array([0.5,1.5]), new Float64Array([0.5,1.5]), {
  gridsize: 4, range: [[0,2],[0,2]],
});
const v = violinChart(new Float64Array([1,2,2,3,4]), { bins: 8 });
const eTrace = e.buildPayload().spec.traces[0];
const out = {
  protocol: PROTOCOL_VERSION,
  kinds: [
    s.buildPayload().spec.traces[0].kind,
    l.buildPayload().spec.traces[0].kind,
    h.buildPayload().spec.traces[0].kind,
    a.buildPayload().spec.traces[0].kind,
    b.buildPayload().spec.traces[0].kind,
        bx.buildPayload().spec.traces.find(t => t.kind === 'box')?.kind,
    eTrace.kind,
    hm.buildPayload().spec.traces[0].kind,
    hx.buildPayload().spec.traces[0].kind,
    v.buildPayload().spec.traces[0].kind,
  ],
  ecdfHasRole: Object.hasOwn(eTrace.style, "role"),
  ecdfStep: eTrace.style.step,
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
        pytest.fail(f"chart convenience probe failed:\n{proc.stderr}")
    payload = json.loads(proc.stdout)
    assert payload["protocol"] == PROTOCOL_VERSION
    assert payload["kinds"] == [
        "scatter",
        "line",
        "histogram",
        "area",
        "bar",
        "box",
        "line",
        "heatmap",
        "hexbin",
        "violin",
    ]
    assert payload["ecdfHasRole"] is False
    assert payload["ecdfStep"] == "post"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
