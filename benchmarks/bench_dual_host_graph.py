#!/usr/bin/env python3
"""Dual-host graph force + render-graph microbench (Python host).

Builds synthetic graphs, times a few force ticks and ``graph_build_render``
under node/edge budgets, asserts ``|V'| <= node_budget`` and
``|E'| <= edge_budget``, and fails CI only on catastrophic regressions
against the soft ceilings documented below.

Usage:
  python3 benchmarks/bench_dual_host_graph.py
  python3 benchmarks/bench_dual_host_graph.py --sizes 1000   # Bazel/CI quick
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from xy import _native  # noqa: E402

# Soft ceilings (ms) — catastrophic regression only, not tight SLOs.
# ~10–20× of warm release timings on a mid-range CI CPU (ABI 53 / Barnes–Hut).
# force: FORCE_TICKS progressive ticks; build_render: NODE_BUDGET / EDGE_BUDGET.
SOFT_CEILING_MS: dict[int, dict[str, float]] = {
    1_000: {"force_ms": 500.0, "build_render_ms": 100.0},
    10_000: {"force_ms": 3_000.0, "build_render_ms": 500.0},
    50_000: {"force_ms": 15_000.0, "build_render_ms": 2_000.0},
    100_000: {"force_ms": 40_000.0, "build_render_ms": 5_000.0},
}

DEFAULT_SIZES = (1_000, 10_000, 50_000)
NODE_BUDGET = 5_000
EDGE_BUDGET = 10_000
FORCE_TICKS = 5
FORCE_SEED = 7


def synthetic_graph(n: int, *, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Ring plus ~n random chords → O(n) edges."""
    rng = np.random.default_rng(seed)
    sources = list(range(n))
    targets = [((i + 1) % n) for i in range(n)]
    for _ in range(n):
        a = int(rng.integers(0, n))
        b = int(rng.integers(0, n))
        if a != b:
            sources.append(a)
            targets.append(b)
    return (
        np.asarray(sources, dtype=np.uint64),
        np.asarray(targets, dtype=np.uint64),
    )


def _best_ms(fn, *, repeat: int = 3) -> float:
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, (time.perf_counter() - t0) * 1e3)
    return best


def bench_size(n: int, *, node_budget: int, edge_budget: int, ticks: int) -> dict:
    sources, targets = synthetic_graph(n)
    # Seed positions via a one-shot circle layout so force starts from a ring.
    x0, y0 = _native.graph_layout("circle", n, sources, targets)

    def run_force() -> tuple[np.ndarray, np.ndarray]:
        handle = _native.graph_force_create(n, sources, targets, x=x0, y=y0, seed=FORCE_SEED)
        try:
            x, y, _alpha = _native.graph_force_tick(handle, n, ticks)
            return x, y
        finally:
            _native.graph_force_destroy(handle)

    # Warm + capture positions for build_render.
    x, y = run_force()
    force_ms = _best_ms(lambda: run_force())

    def run_build() -> tuple:
        return _native.graph_build_render(
            x,
            y,
            sources,
            targets,
            node_budget=node_budget,
            edge_budget=edge_budget,
        )

    out = run_build()
    build_ms = _best_ms(lambda: run_build())
    out_x, out_y, _member, edge_s, edge_t, tier, edges_kept = out
    n_prime = int(len(out_x))
    e_prime = int(len(edge_s))
    if n_prime > node_budget:
        raise AssertionError(f"|V'|={n_prime} exceeds node_budget={node_budget}")
    if e_prime > edge_budget:
        raise AssertionError(f"|E'|={e_prime} exceeds edge_budget={edge_budget}")
    if len(out_y) != n_prime or len(edge_t) != e_prime:
        raise AssertionError("render-graph length mismatch")

    ceilings = SOFT_CEILING_MS.get(n)
    force_ok = True
    build_ok = True
    if ceilings is not None:
        force_ok = force_ms <= ceilings["force_ms"]
        build_ok = build_ms <= ceilings["build_render_ms"]
        if not force_ok:
            raise AssertionError(
                f"force_ms={force_ms:.3f} exceeds soft ceiling {ceilings['force_ms']} "
                f"for n={n} (catastrophic regression)"
            )
        if not build_ok:
            raise AssertionError(
                f"build_render_ms={build_ms:.3f} exceeds soft ceiling "
                f"{ceilings['build_render_ms']} for n={n} (catastrophic regression)"
            )

    return {
        "n": n,
        "n_edges": int(len(sources)),
        "force_ticks": ticks,
        "force_ms": force_ms,
        "build_render_ms": build_ms,
        "node_budget": node_budget,
        "edge_budget": edge_budget,
        "n_prime": n_prime,
        "e_prime": e_prime,
        "tier": int(tier),
        "edges_kept": int(edges_kept),
        "soft_ceiling_ms": ceilings,
        "abi_version": int(_native.ABI_VERSION),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sizes",
        default=",".join(str(s) for s in DEFAULT_SIZES),
        help="comma-separated node counts (default: 1000,10000,50000)",
    )
    ap.add_argument("--node-budget", type=int, default=NODE_BUDGET)
    ap.add_argument("--edge-budget", type=int, default=EDGE_BUDGET)
    ap.add_argument("--ticks", type=int, default=FORCE_TICKS)
    args = ap.parse_args()
    sizes = [int(float(s.strip())) for s in args.sizes.split(",") if s.strip()]

    rows = []
    for n in sizes:
        rows.append(
            bench_size(
                n,
                node_budget=args.node_budget,
                edge_budget=args.edge_budget,
                ticks=args.ticks,
            )
        )

    summary = {
        "host": "python",
        "abi_version": int(_native.ABI_VERSION),
        "node_budget": args.node_budget,
        "edge_budget": args.edge_budget,
        "force_ticks": args.ticks,
        "results": rows,
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
