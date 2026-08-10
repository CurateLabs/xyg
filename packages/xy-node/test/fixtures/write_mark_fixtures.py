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

from xy import _native  # noqa: E402
from xy.config import DECIMATION_THRESHOLD, PROTOCOL_VERSION  # noqa: E402
from xy.lod import encode_f32_values  # noqa: E402

OUT = Path(__file__).resolve().parent


def _f64_hex(arr: np.ndarray) -> str:
    return np.ascontiguousarray(arr, dtype="<f8").tobytes().hex()


def _f32_hex(arr: np.ndarray) -> str:
    return np.ascontiguousarray(arr, dtype="<f4").tobytes().hex()


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
    }
    out_path = OUT / "mark_parity.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
