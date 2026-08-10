#!/usr/bin/env python3
"""Parity kernel timings: encode_f32, m4_points, histogram_uniform, bin_2d.

Times fixed sizes through the Python native binding. When
``benchmarks/baseline.json`` is present, compares throughput / ms keys
softly and fails if any metric is worse than 3× the baseline (catastrophic
regression). Without a baseline, just emits timings as JSON.

Usage:
  python3 benchmarks/bench_parity_kernels.py
  python3 benchmarks/bench_parity_kernels.py --sizes 1000000
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from xy import _native  # noqa: E402

BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"
DEFAULT_SIZES = (1_000_000,)
# Soft gate: measured must be no worse than 3× baseline (throughput: 1/3×).
REGRESSION_FACTOR = 3.0


def _best(fn, *, repeat: int = 5) -> float:
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def bench_size(n: int) -> dict:
    x = np.arange(n, dtype=np.float64)
    y = np.sin(x * 1e-3)

    t_enc = _best(lambda: _native.encode_f32(x, float(x[n // 2]), 1.0))
    encode_ms = t_enc * 1e3
    encode_mpts_s = n / t_enc / 1e6

    buckets = 2048
    t_m4 = _best(lambda: _native.m4_points(x, y, 0.0, float(n), buckets))
    m4_ms = t_m4 * 1e3
    m4_mpts_s = n / t_m4 / 1e6

    n_bins = 512
    t_hist = _best(lambda: _native.histogram_uniform(x, 0.0, float(n), n_bins))
    hist_ms = t_hist * 1e3
    hist_mpts_s = n / t_hist / 1e6

    gw, gh = 512, 384
    t_bin = _best(lambda: _native.bin_2d(x, y, 0.0, float(n), -3.0, 3.0, gw, gh))
    bin_ms = t_bin * 1e3
    bin_mpts_s = n / t_bin / 1e6

    return {
        "n": n,
        "encode_ms": encode_ms,
        "encode_mpts_s": encode_mpts_s,
        "m4_points_ms": m4_ms,
        "m4_points_mpts_s": m4_mpts_s,
        "histogram_ms": hist_ms,
        "histogram_mpts_s": hist_mpts_s,
        "bin_2d_ms": bin_ms,
        "bin_2d_mpts_s": bin_mpts_s,
    }


def load_baseline() -> dict | None:
    if not BASELINE_PATH.is_file():
        return None
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    metrics = data.get("metrics")
    return metrics if isinstance(metrics, dict) else None


def compare_to_baseline(row: dict, metrics: dict) -> list[dict]:
    """Return soft comparison records; raise AssertionError on >3× regression."""
    n = int(row["n"])
    checks: list[tuple[str, str, float, bool]] = [
        # (result_key, baseline_key, measured, higher_is_better)
        ("encode_mpts_s", f"kernel.encode_mpts_s.{n}", row["encode_mpts_s"], True),
        ("histogram_ms", f"kernel.histogram_ms.{n}", row["histogram_ms"], False),
        ("histogram_mpts_s", f"kernel.histogram_mpts_s.{n}", row["histogram_mpts_s"], True),
        ("bin_2d_ms", f"kernel.bin_2d_ms.{n}", row["bin_2d_ms"], False),
        ("bin_2d_mpts_s", f"kernel.bin_2d_mpts_s.{n}", row["bin_2d_mpts_s"], True),
        # m4_points has no dedicated baseline key; reuse m4_full throughput softly.
        ("m4_points_mpts_s", f"kernel.m4_full_mpts_s.{n}", row["m4_points_mpts_s"], True),
    ]
    comparisons: list[dict] = []
    for result_key, base_key, measured, higher_better in checks:
        if base_key not in metrics:
            continue
        baseline = float(metrics[base_key])
        if not math.isfinite(baseline) or baseline <= 0:
            continue
        ratio = measured / baseline
        if higher_better:
            # throughput: regression if measured < baseline / REGRESSION_FACTOR
            ok = measured >= baseline / REGRESSION_FACTOR
            limit = baseline / REGRESSION_FACTOR
        else:
            # latency: regression if measured > baseline * REGRESSION_FACTOR
            ok = measured <= baseline * REGRESSION_FACTOR
            limit = baseline * REGRESSION_FACTOR
        comparisons.append(
            {
                "metric": result_key,
                "baseline_key": base_key,
                "measured": measured,
                "baseline": baseline,
                "ratio": ratio,
                "ok": ok,
                "limit": limit,
            }
        )
        if not ok:
            raise AssertionError(
                f"{result_key}={measured:.6g} vs baseline {baseline:.6g} "
                f"({base_key}) exceeds {REGRESSION_FACTOR}× soft gate"
            )
    return comparisons


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sizes",
        default=",".join(str(s) for s in DEFAULT_SIZES),
        help="comma-separated lengths (default: 1000000)",
    )
    ap.add_argument(
        "--no-baseline",
        action="store_true",
        help="skip baseline.json comparison even when the file exists",
    )
    args = ap.parse_args()
    sizes = [int(float(s.strip())) for s in args.sizes.split(",") if s.strip()]

    rows = [bench_size(n) for n in sizes]
    baseline = None if args.no_baseline else load_baseline()
    comparisons: list[dict] = []
    if baseline is not None:
        for row in rows:
            comparisons.extend(compare_to_baseline(row, baseline))

    summary = {
        "host": "python",
        "abi_version": int(_native.ABI_VERSION),
        "baseline_path": str(BASELINE_PATH) if baseline is not None else None,
        "regression_factor": REGRESSION_FACTOR if baseline is not None else None,
        "results": rows,
        "comparisons": comparisons,
        "ok": True,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        raise SystemExit(1) from exc
