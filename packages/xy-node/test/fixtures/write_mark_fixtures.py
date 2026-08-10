#!/usr/bin/env python3
"""Write Python-side golden fixtures for @xy/node mark parity tests.

Produces JSON under packages/xy-node/test/fixtures/ consumed by
``test/marks.test.mjs`` and cross-checked by ``tests/test_node_mark_parity.py``.

Run from repo root::

    uv run python packages/xy-node/test/fixtures/write_mark_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "python"))

from xy import _native, kernels  # noqa: E402
from xy.config import DECIMATION_THRESHOLD, PROTOCOL_VERSION  # noqa: E402
from xy.lod import encode_f32_values  # noqa: E402

OUT = Path(__file__).resolve().parent


def _f64_hex(arr: np.ndarray) -> str:
    return np.ascontiguousarray(arr, dtype="<f8").tobytes().hex()


def _f32_hex(arr: np.ndarray) -> str:
    return np.ascontiguousarray(arr, dtype="<f4").tobytes().hex()


def _u8_hex(arr: np.ndarray) -> str:
    return np.ascontiguousarray(arr, dtype=np.uint8).tobytes().hex()


def main() -> None:
    # --- Small scatter encode ---
    scatter_x = np.asarray([0.0, 1.0, 2.0, 3.0, 4.0, -1.5, 10.25], dtype=np.float64)
    scatter_y = np.asarray([0.0, 0.5, 1.0, 1.5, 2.0, 3.25, -4.0], dtype=np.float64)
    x_lo, x_hi = float(scatter_x.min()), float(scatter_x.max())
    y_lo, y_hi = float(scatter_y.min()), float(scatter_y.max())
    x_off = (x_lo + x_hi) / 2.0
    y_off = (y_lo + y_hi) / 2.0
    x_enc = encode_f32_values(scatter_x, x_off, x_lo, x_hi)
    y_enc = encode_f32_values(scatter_y, y_off, y_lo, y_hi)

    # --- M4 line index count (monotone) ---
    n_line = 20_000
    line_x = np.arange(n_line, dtype=np.float64)
    line_y = np.sin(line_x / 100.0) + line_x / n_line
    n_buckets = 640
    x0 = 0.0
    x1 = float(n_line - 1)
    eps = float(np.finfo(np.float64).eps)
    idx = _native.m4_indices(line_x, line_y, x0, x1 + eps, n_buckets)

    # --- histogram_uniform fixed edges ---
    hist_values = np.asarray(
        [0.1, 0.2, 0.5, 0.9, 1.1, 1.4, 1.9, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, -0.5, 5.5],
        dtype=np.float64,
    )
    hist_lo, hist_hi, hist_bins = 0.0, 5.0, 5
    counts, edges = _native.histogram_uniform(
        hist_values, hist_lo, hist_hi, hist_bins, density=False
    )

    # --- area ingest (unsorted x → stable sort) ---
    area_x = np.asarray([2.0, 0.0, 1.0], dtype=np.float64)
    area_y = np.asarray([3.0, 1.0, 2.0], dtype=np.float64)
    area_base = 0.5
    order = np.argsort(area_x, kind="stable")
    area_x_sorted = area_x[order]
    area_y_sorted = area_y[order]

    # --- bar rects (numeric x, width 0.8) ---
    bar_x = np.asarray([0.0, 1.0, 2.0], dtype=np.float64)
    bar_y = np.asarray([1.0, 3.0, 2.0], dtype=np.float64)
    bar_width = 0.8
    bar_half = bar_width / 2.0
    bar_x0 = bar_x - bar_half
    bar_x1 = bar_x + bar_half
    bar_y0 = np.zeros_like(bar_y)
    bar_y1 = bar_y

    # --- box stats ---
    box_values = np.asarray([1.0, 2.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 100.0], dtype=np.float64)
    q1, med, q3, low, high, outliers = kernels.box_stats(box_values)

    # --- ecdf exact (weighted_ecdf with unit weights) ---
    ecdf_values = np.asarray([3.0, 1.0, 2.0, 1.0, 3.0], dtype=np.float64)
    ecdf_weights = np.ones(len(ecdf_values), dtype=np.float64)
    ecdf_x, ecdf_y = kernels.weighted_ecdf(ecdf_values, ecdf_weights)

    # --- segments pass-through ---
    seg_x0 = np.asarray([0.0, 1.0], dtype=np.float64)
    seg_y0 = np.asarray([0.0, 1.0], dtype=np.float64)
    seg_x1 = np.asarray([1.0, 2.0], dtype=np.float64)
    seg_y1 = np.asarray([1.0, 0.0], dtype=np.float64)

    # --- heatmap rgba ---
    heat_rows, heat_cols = 3, 3
    heat_z = np.asarray(
        [[0.0, 0.5, 1.0], [0.25, 0.75, 0.5], [1.0, 0.0, 0.5]],
        dtype=np.float64,
    )
    heat_stops = np.asarray([[0, 0, 255], [255, 255, 255], [255, 0, 0]], dtype=np.uint8)
    heat_rgba = kernels.heatmap_rgba(heat_z.reshape(-1), heat_cols, heat_rows, heat_stops, 255)

    # --- hexbin ---
    hex_x = np.asarray([0.5, 1.5, 2.5, 3.5, 1.0, 2.0, 3.0], dtype=np.float64)
    hex_y = np.asarray([0.5, 0.5, 0.5, 0.5, 2.0, 2.0, 2.0], dtype=np.float64)
    hex_range = ((0.0, 4.0), (0.0, 3.0))
    hex_w, hex_h = 8, 6
    hx, hy, metric, hex_counts, dx, dy = kernels.hexbin(
        hex_x, hex_y, gridsize=(hex_w, hex_h), range=hex_range, mincnt=0, reduce="count"
    )

    # --- violin density ---
    violin_values = np.asarray(
        [1.0, 1.5, 2.0, 2.0, 2.5, 3.0, 3.0, 3.5, 4.0, 4.5, 5.0],
        dtype=np.float64,
    )
    violin_bins = 16
    v_edges, v_density = kernels.violin_density(violin_values, violin_bins)

    payload = {
        "protocol": PROTOCOL_VERSION,
        "abi_version": int(_native.ABI_VERSION),
        "scatter": {
            "x_f64_hex": _f64_hex(scatter_x),
            "y_f64_hex": _f64_hex(scatter_y),
            "x_f32_hex": _f32_hex(x_enc.values),
            "y_f32_hex": _f32_hex(y_enc.values),
            "x_meta": {"offset": float(x_enc.meta["offset"]), "scale": float(x_enc.meta["scale"])},
            "y_meta": {"offset": float(y_enc.meta["offset"]), "scale": float(y_enc.meta["scale"])},
            "x_bounds": [x_lo, x_hi],
            "y_bounds": [y_lo, y_hi],
        },
        "line_m4": {
            "n": n_line,
            "n_buckets": n_buckets,
            "x0": x0,
            "x1": x1,
            "x1_plus_eps": x1 + eps,
            "threshold": DECIMATION_THRESHOLD,
            "index_count": int(len(idx)),
        },
        "histogram": {
            "lo": hist_lo,
            "hi": hist_hi,
            "n_bins": hist_bins,
            "density": False,
            "values_f64_hex": _f64_hex(hist_values),
            "counts": counts.astype(np.float64).tolist(),
            "edges": edges.astype(np.float64).tolist(),
            "counts_f64_hex": _f64_hex(counts.astype(np.float64)),
            "edges_f64_hex": _f64_hex(edges.astype(np.float64)),
        },
        "area": {
            "x_f64_hex": _f64_hex(area_x),
            "y_f64_hex": _f64_hex(area_y),
            "base": area_base,
            "x_sorted_f64_hex": _f64_hex(area_x_sorted),
            "y_sorted_f64_hex": _f64_hex(area_y_sorted),
        },
        "bar": {
            "x_f64_hex": _f64_hex(bar_x),
            "y_f64_hex": _f64_hex(bar_y),
            "width": bar_width,
            "x0_f64_hex": _f64_hex(bar_x0),
            "x1_f64_hex": _f64_hex(bar_x1),
            "y0_f64_hex": _f64_hex(bar_y0),
            "y1_f64_hex": _f64_hex(bar_y1),
        },
        "box": {
            "values_f64_hex": _f64_hex(box_values),
            "q1": q1,
            "median": med,
            "q3": q3,
            "low": low,
            "high": high,
            "outliers_f64_hex": _f64_hex(outliers.astype(np.float64)),
            "n_outliers": int(len(outliers)),
        },
        "ecdf": {
            "values_f64_hex": _f64_hex(ecdf_values),
            "x_f64_hex": _f64_hex(ecdf_x),
            "y_f64_hex": _f64_hex(ecdf_y),
            "n_points": int(len(ecdf_x)),
        },
        "segments": {
            "x0_f64_hex": _f64_hex(seg_x0),
            "y0_f64_hex": _f64_hex(seg_y0),
            "x1_f64_hex": _f64_hex(seg_x1),
            "y1_f64_hex": _f64_hex(seg_y1),
            "n": 2,
        },
        "heatmap": {
            "rows": heat_rows,
            "cols": heat_cols,
            "z_f64_hex": _f64_hex(heat_z.reshape(-1)),
            "stops_u8_hex": _u8_hex(heat_stops.reshape(-1)),
            "rgba_u8_hex": _u8_hex(heat_rgba.reshape(-1)),
        },
        "hexbin": {
            "x_f64_hex": _f64_hex(hex_x),
            "y_f64_hex": _f64_hex(hex_y),
            "gridsize": [hex_w, hex_h],
            "range": [[0.0, 4.0], [0.0, 3.0]],
            "mincnt": 0,
            "reduce": "count",
            "n_bins": int(len(hx)),
            "centers_x_f64_hex": _f64_hex(hx),
            "centers_y_f64_hex": _f64_hex(hy),
            "metrics_f64_hex": _f64_hex(metric),
            "counts_f64_hex": _f64_hex(hex_counts),
            "dx": dx,
            "dy": dy,
        },
        "violin": {
            "values_f64_hex": _f64_hex(violin_values),
            "bins": violin_bins,
            "edges_f64_hex": _f64_hex(v_edges),
            "density_f64_hex": _f64_hex(v_density),
        },
    }
    out_path = OUT / "mark_parity.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
