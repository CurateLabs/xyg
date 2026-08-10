#!/usr/bin/env python3
"""Scale scaffold: major mark families + soft baseline / render-graph budgets.

For each family (scatter, line, hist, bar, heatmap, hexbin, box, graph
render-graph) builds a chart (or kernel path), records wall ms + wire bytes,
and — where ``benchmarks/baseline.json`` has matching keys — soft-compares
scatter/line/hist kernel metrics with the same 3× advisory gate as
``bench_parity_kernels.py``.

Graph sizes 10k / 50k assert ``graph_build_render`` / ``run_layout`` emit
render-graph geometry within the requested node/edge budgets. Every profile
also records **10M / 100M / 1B-class** LOD decision evidence (screen-bounded
budgets); the ``evidence`` profile additionally runs a real ``build_render``
at 10M when memory allows.

Usage:
  PYTHONPATH=python python3 benchmarks/bench_scale_all_charts.py
  PYTHONPATH=python python3 benchmarks/bench_scale_all_charts.py --profile smoke
  PYTHONPATH=python python3 benchmarks/bench_scale_all_charts.py --profile evidence
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

import xy  # noqa: E402
from xy import _graph, _native  # noqa: E402

BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"
REGRESSION_FACTOR = 3.0

# Launch-baseline-aligned sizes (see benchmarks/launch_baselines/*/default-results.json).
LAUNCH_SIZES = (10_000, 100_000, 1_000_000)
# Kernel keys in baseline.json are primarily at 1e6 / 1e7.
KERNEL_SIZES = (1_000_000,)
GRAPH_SIZES = (10_000, 50_000)
# Scatter-class scale claims for graph (with aggregation) — lod_decision always.
GRAPH_CLASS_SIZES = (10_000_000, 100_000_000, 1_000_000_000)
CLASS_NODE_BUDGET = 50_000
CLASS_EDGE_BUDGET = 100_000

PROFILES = {
    "smoke": {
        "chart_sizes": (10_000,),
        "kernel_sizes": (1_000_000,),
        "graph_sizes": (10_000, 50_000),
        "graph_class_sizes": GRAPH_CLASS_SIZES,
        "graph_build_class_sizes": (),
    },
    "standard": {
        "chart_sizes": (10_000, 100_000),
        "kernel_sizes": (1_000_000,),
        "graph_sizes": (10_000, 50_000, 100_000),
        "graph_class_sizes": GRAPH_CLASS_SIZES,
        "graph_build_class_sizes": (),
    },
    "stress": {
        "chart_sizes": LAUNCH_SIZES,
        "kernel_sizes": (1_000_000, 10_000_000),
        "graph_sizes": GRAPH_SIZES + (100_000, 1_000_000),
        "graph_class_sizes": GRAPH_CLASS_SIZES,
        "graph_build_class_sizes": (),
    },
    "evidence": {
        "chart_sizes": (10_000,),
        "kernel_sizes": (1_000_000,),
        "graph_sizes": (10_000, 50_000, 100_000, 1_000_000),
        "graph_class_sizes": GRAPH_CLASS_SIZES,
        # Real build_render at 10M (ring+chords); 100M/1B stay lod_decision-only.
        "graph_build_class_sizes": (10_000_000,),
    },
}


def _best(fn, *, repeat: int = 3) -> float:
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def load_baseline() -> dict[str, float] | None:
    if not BASELINE_PATH.is_file():
        return None
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    metrics = data.get("metrics")
    return metrics if isinstance(metrics, dict) else None


def soft_compare(
    result_key: str,
    baseline_key: str,
    measured: float,
    baseline_metrics: dict[str, float],
    *,
    higher_is_better: bool,
) -> dict[str, Any] | None:
    if baseline_key not in baseline_metrics:
        return None
    baseline = float(baseline_metrics[baseline_key])
    if not math.isfinite(baseline) or baseline <= 0 or not math.isfinite(measured):
        return None
    ratio = measured / baseline
    if higher_is_better:
        ok = measured >= baseline / REGRESSION_FACTOR
        limit = baseline / REGRESSION_FACTOR
    else:
        ok = measured <= baseline * REGRESSION_FACTOR
        limit = baseline * REGRESSION_FACTOR
    # Advisory only: never raise. CI smoke/shared runners are cold and
    # variable; hard gates are render-graph budgets + structural checks.
    # Upstream-style timing regressions stay visible in the JSON report.
    return {
        "metric": result_key,
        "baseline_key": baseline_key,
        "measured": measured,
        "baseline": baseline,
        "ratio": ratio,
        "ok": ok,
        "limit": limit,
        "advisory": True,
    }


def _wire_bytes(fig: Any) -> int:
    _spec, blob = fig.build_payload()
    return len(blob)


def bench_scatter_chart(n: int) -> dict[str, Any]:
    rng = np.random.default_rng(0)
    x = rng.standard_normal(n)
    y = rng.standard_normal(n)

    def build():
        return xy.scatter_chart(xy.scatter(x, y), width=640, height=360).figure()

    t_build = _best(lambda: build())
    fig = build()
    t_payload = _best(lambda: fig.build_payload())
    wire = _wire_bytes(fig)
    return {
        "family": "scatter",
        "n": n,
        "build_ms": t_build * 1e3,
        "payload_ms": t_payload * 1e3,
        "wire_bytes": wire,
    }


def bench_line_chart(n: int) -> dict[str, Any]:
    x = np.arange(n, dtype=np.float64)
    y = np.sin(x * 1e-3)

    def build():
        return xy.line_chart(xy.line(x, y), width=640, height=360).figure()

    t_build = _best(lambda: build())
    fig = build()
    t_payload = _best(lambda: fig.build_payload())
    return {
        "family": "line",
        "n": n,
        "build_ms": t_build * 1e3,
        "payload_ms": t_payload * 1e3,
        "wire_bytes": _wire_bytes(fig),
    }


def bench_hist_chart(n: int) -> dict[str, Any]:
    rng = np.random.default_rng(1)
    values = rng.standard_normal(n)

    def build():
        return xy.histogram_chart(xy.histogram(values, bins=64), width=640, height=360).figure()

    t_build = _best(lambda: build())
    fig = build()
    t_payload = _best(lambda: fig.build_payload())
    return {
        "family": "hist",
        "n": n,
        "build_ms": t_build * 1e3,
        "payload_ms": t_payload * 1e3,
        "wire_bytes": _wire_bytes(fig),
    }


def bench_bar_chart(n: int) -> dict[str, Any]:
    # Cap categories for bar (categorical axis); n indexes input work units.
    k = min(n, 64)
    cats = [f"c{i}" for i in range(k)]
    vals = np.linspace(1.0, float(k), k)

    def build():
        return xy.bar_chart(xy.bar(cats, vals), width=640, height=360).figure()

    t_build = _best(lambda: build())
    fig = build()
    t_payload = _best(lambda: fig.build_payload())
    return {
        "family": "bar",
        "n": n,
        "categories": k,
        "build_ms": t_build * 1e3,
        "payload_ms": t_payload * 1e3,
        "wire_bytes": _wire_bytes(fig),
    }


def bench_heatmap_chart(n: int) -> dict[str, Any]:
    # n ≈ grid cells; use sqrt for a square-ish grid.
    side = max(8, int(math.sqrt(n)))
    z = np.arange(side * side, dtype=np.float64).reshape(side, side)

    def build():
        return xy.heatmap_chart(xy.heatmap(z), width=640, height=360).figure()

    t_build = _best(lambda: build())
    fig = build()
    t_payload = _best(lambda: fig.build_payload())
    return {
        "family": "heatmap",
        "n": side * side,
        "build_ms": t_build * 1e3,
        "payload_ms": t_payload * 1e3,
        "wire_bytes": _wire_bytes(fig),
    }


def bench_hexbin_chart(n: int) -> dict[str, Any]:
    rng = np.random.default_rng(2)
    x = rng.standard_normal(n)
    y = rng.standard_normal(n)

    def build():
        return xy.hexbin_chart(xy.hexbin(x, y, gridsize=32), width=640, height=360).figure()

    t_build = _best(lambda: build())
    fig = build()
    t_payload = _best(lambda: fig.build_payload())
    return {
        "family": "hexbin",
        "n": n,
        "build_ms": t_build * 1e3,
        "payload_ms": t_payload * 1e3,
        "wire_bytes": _wire_bytes(fig),
    }


def bench_box_chart(n: int) -> dict[str, Any]:
    rng = np.random.default_rng(3)
    values = rng.standard_normal(n)

    def build():
        return xy.box_chart(xy.box(values), width=640, height=360).figure()

    t_build = _best(lambda: build())
    fig = build()
    t_payload = _best(lambda: fig.build_payload())
    return {
        "family": "box",
        "n": n,
        "build_ms": t_build * 1e3,
        "payload_ms": t_payload * 1e3,
        "wire_bytes": _wire_bytes(fig),
    }


def _synthetic_graph(n_nodes: int, *, avg_degree: float = 4.0) -> _graph.GraphData:
    rng = np.random.default_rng(n_nodes)
    n_edges = max(n_nodes, int(n_nodes * avg_degree / 2))
    sources = rng.integers(0, n_nodes, size=n_edges, dtype=np.uint64)
    targets = rng.integers(0, n_nodes, size=n_edges, dtype=np.uint64)
    # Avoid self-loops for cleaner CSR.
    same = sources == targets
    targets = np.where(same, (targets + 1) % n_nodes, targets).astype(np.uint64)
    nodes = [f"n{i}" for i in range(n_nodes)]
    edges = list(zip(sources.tolist(), targets.tolist(), strict=True))
    # Prefer dense index path via normalize on id lists.
    return _graph.normalize_graph_inputs(nodes, [(nodes[int(s)], nodes[int(t)]) for s, t in edges])


def bench_graph_render(n_nodes: int, *, node_budget: int, edge_budget: int) -> dict[str, Any]:
    data = _synthetic_graph(n_nodes)
    # Preset layout from random positions — isolates render-graph cost from force.
    data.x = np.linspace(0.0, 1.0, n_nodes, dtype=np.float64)
    data.y = np.sin(np.arange(n_nodes, dtype=np.float64) * 0.01)

    def run():
        return _graph.run_layout(
            data,
            layout="preset",
            node_budget=node_budget,
            edge_budget=edge_budget,
        )

    t = _best(run, repeat=2)
    rx, ry, meta = run()
    n_out = int(meta["n_nodes"])
    e_out = int(meta["n_edges"])
    assert n_out <= node_budget, f"render-graph nodes {n_out} > budget {node_budget}"
    assert e_out <= edge_budget, f"render-graph edges {e_out} > budget {edge_budget}"
    assert len(rx) == n_out and len(ry) == n_out

    # Also time a composition-API graph chart build at this size (smaller wire).
    nodes = [f"n{i}" for i in range(min(n_nodes, 2_000))]
    edges = [(nodes[i], nodes[(i + 1) % len(nodes)]) for i in range(len(nodes))]

    def chart_build():
        return xy.graph_chart(
            xy.graph(nodes, edges, layout="grid"),
            width=400,
            height=300,
        ).figure()

    t_chart = _best(chart_build, repeat=2)
    fig = chart_build()
    wire = _wire_bytes(fig)
    return {
        "family": "graph",
        "n_nodes": n_nodes,
        "source_n_edges": int(meta.get("source_n_edges", data.n_edges)),
        "node_budget": node_budget,
        "edge_budget": edge_budget,
        "render_n_nodes": n_out,
        "render_n_edges": e_out,
        "lod_tier": int(meta.get("lod_tier", -1)),
        "render_graph_ms": t * 1e3,
        "chart_build_ms": t_chart * 1e3,
        "wire_bytes": wire,
        "budget_ok": True,
    }


def _class_label(n: int) -> str:
    if n >= 1_000_000_000:
        return "1B"
    if n >= 100_000_000:
        return "100M"
    if n >= 10_000_000:
        return "10M"
    if n >= 1_000_000:
        return "1M"
    if n >= 1_000:
        return f"{n // 1000}k"
    return str(n)


def bench_graph_scale_class(
    n_nodes: int,
    *,
    node_budget: int = CLASS_NODE_BUDGET,
    edge_budget: int = CLASS_EDGE_BUDGET,
    build_render: bool = False,
) -> dict[str, Any]:
    """10M/100M/1B-class evidence: LOD decision always; optional build_render."""
    n_edges = max(n_nodes, int(n_nodes * 2))  # ring + chords class
    tier, edges_kept = _native.graph_lod_decision(
        n_nodes, n_edges, node_budget=node_budget, edge_budget=edge_budget
    )
    row: dict[str, Any] = {
        "family": "graph_scale_class",
        "class": _class_label(n_nodes),
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "node_budget": node_budget,
        "edge_budget": edge_budget,
        "lod_tier": int(tier),
        "edges_kept": int(edges_kept),
        "mode": "lod_decision",
        "budget_ok": True,
    }
    # Past direct tier the decision must force aggregation / sampling.
    if n_nodes > node_budget:
        assert int(tier) >= 1, f"expected non-direct LOD tier for n={n_nodes}"
    if not build_render:
        return row

    # Real render-graph emission at this source size (memory-sensitive).
    data = _synthetic_graph(n_nodes, avg_degree=2.0)
    data.x = np.linspace(0.0, 1.0, n_nodes, dtype=np.float64)
    data.y = np.sin(np.arange(n_nodes, dtype=np.float64) * 0.01)

    def run():
        return _native.graph_build_render(
            data.x,
            data.y,
            data.sources,
            data.targets,
            node_budget=node_budget,
            edge_budget=edge_budget,
        )

    t = _best(run, repeat=1)
    out_x, out_y, _member, edge_s, edge_t, out_tier, kept = run()
    n_out = int(len(out_x))
    e_out = int(len(edge_s))
    assert n_out <= node_budget, f"class render-graph nodes {n_out} > {node_budget}"
    assert e_out <= edge_budget, f"class render-graph edges {e_out} > {edge_budget}"
    row.update(
        {
            "mode": "build_render",
            "render_n_nodes": n_out,
            "render_n_edges": e_out,
            "lod_tier": int(out_tier),
            "edges_kept": int(kept),
            "render_graph_ms": t * 1e3,
            "budget_ok": True,
        }
    )
    del out_y, edge_t  # silence unused
    return row


def bench_kernels(n: int, baseline: dict[str, float] | None) -> tuple[dict[str, Any], list[dict]]:
    x = np.arange(n, dtype=np.float64)
    y = np.sin(x * 1e-3)
    t_enc = _best(lambda: _native.encode_f32(x, float(x[n // 2]), 1.0))
    t_m4 = _best(lambda: _native.m4_points(x, y, 0.0, float(n), 2048))
    t_hist = _best(lambda: _native.histogram_uniform(x, 0.0, float(n), 512))
    row = {
        "family": "kernel",
        "n": n,
        "encode_ms": t_enc * 1e3,
        "encode_mpts_s": n / t_enc / 1e6,
        "m4_points_ms": t_m4 * 1e3,
        "m4_points_mpts_s": n / t_m4 / 1e6,
        "histogram_ms": t_hist * 1e3,
        "histogram_mpts_s": n / t_hist / 1e6,
    }
    comparisons: list[dict] = []
    if baseline is not None:
        for rec in (
            soft_compare(
                "encode_mpts_s",
                f"kernel.encode_mpts_s.{n}",
                row["encode_mpts_s"],
                baseline,
                higher_is_better=True,
            ),
            soft_compare(
                "histogram_ms",
                f"kernel.histogram_ms.{n}",
                row["histogram_ms"],
                baseline,
                higher_is_better=False,
            ),
            soft_compare(
                "histogram_mpts_s",
                f"kernel.histogram_mpts_s.{n}",
                row["histogram_mpts_s"],
                baseline,
                higher_is_better=True,
            ),
            soft_compare(
                "m4_points_mpts_s",
                f"kernel.m4_full_mpts_s.{n}",
                row["m4_points_mpts_s"],
                baseline,
                higher_is_better=True,
            ),
        ):
            if rec is not None:
                comparisons.append(rec)
        # Scatter wire-bytes advisory when present (chart path at matching n).
        wb_key = f"scatter.wire_bytes.{n}"
        if wb_key in baseline and n in LAUNCH_SIZES:
            # Measured separately only when we also ran scatter at this n;
            # skip here — chart rows carry wire_bytes for soft note elsewhere.
            pass
    return row, comparisons


def soft_compare_scatter_wire(
    chart_row: dict[str, Any], baseline: dict[str, float]
) -> dict[str, Any] | None:
    n = int(chart_row["n"])
    key = f"scatter.wire_bytes.{n}"
    if chart_row["family"] != "scatter" or key not in baseline:
        return None
    return soft_compare(
        "scatter.wire_bytes",
        key,
        float(chart_row["wire_bytes"]),
        baseline,
        higher_is_better=False,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="smoke",
        help="size matrix (default: smoke)",
    )
    ap.add_argument(
        "--no-baseline",
        action="store_true",
        help="skip baseline.json soft comparisons",
    )
    args = ap.parse_args()
    profile = PROFILES[args.profile]
    baseline = None if args.no_baseline else load_baseline()

    results: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []

    chart_fns = (
        bench_scatter_chart,
        bench_line_chart,
        bench_hist_chart,
        bench_bar_chart,
        bench_heatmap_chart,
        bench_hexbin_chart,
        bench_box_chart,
    )
    for n in profile["chart_sizes"]:
        for fn in chart_fns:
            row = fn(n)
            results.append(row)
            if baseline is not None and row["family"] == "scatter":
                rec = soft_compare_scatter_wire(row, baseline)
                if rec is not None:
                    comparisons.append(rec)

    for n in profile["kernel_sizes"]:
        row, comps = bench_kernels(n, baseline)
        results.append(row)
        comparisons.extend(comps)

    # Render-graph budgets: at 10k/50k use tight budgets so LOD must reduce,
    # and also default-scale budgets that must still hold the output contract.
    for n_nodes in profile["graph_sizes"]:
        # Tight: force aggregate/sample path.
        tight_nodes = max(1, n_nodes // 10)
        tight_edges = max(1, (n_nodes * 2) // 10)
        results.append(
            bench_graph_render(n_nodes, node_budget=tight_nodes, edge_budget=tight_edges)
        )
        # Generous: still assert outputs ≤ budgets (identity / direct path).
        results.append(
            bench_graph_render(
                n_nodes,
                node_budget=max(n_nodes, 200_000),
                edge_budget=max(n_nodes * 4, 500_000),
            )
        )

    # 10M / 100M / 1B-class LOD evidence (always); optional real build_render.
    build_class = set(profile.get("graph_build_class_sizes") or ())
    for n_nodes in profile.get("graph_class_sizes") or ():
        results.append(
            bench_graph_scale_class(
                n_nodes,
                build_render=n_nodes in build_class,
            )
        )

    advisory_ok = all(c.get("ok", True) for c in comparisons)
    hard_ok = all(r.get("budget_ok", True) for r in results if "budget_ok" in r)
    summary = {
        "host": "python",
        "abi_version": int(_native.ABI_VERSION),
        "profile": args.profile,
        "baseline_path": str(BASELINE_PATH) if baseline is not None else None,
        "regression_factor": REGRESSION_FACTOR if baseline is not None else None,
        "results": results,
        "comparisons": comparisons,
        "advisory_ok": advisory_ok,
        "ok": hard_ok,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not hard_ok:
        print(
            json.dumps(
                {"ok": False, "error": "render-graph or chart hard budget failed"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
