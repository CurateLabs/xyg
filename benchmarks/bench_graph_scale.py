"""Graph scale evidence for #33: render and interaction cost by tier.

Measures the graph render pipeline end to end on the graph size ladder
(small 1k, medium 10k, large 100k, massive 1M nodes; two edges per node) and
records Rust render-graph policy at 10M / 100M / 1B as LOD-decision rows.
Positions are preset (seeded normal) so the rows isolate render cost; layout
ticks are covered by ``benchmarks/test_codspeed_graph_render.py``.

Each tier row records host normalization, Rust ``build_render``, Rust edge
routing, the full graph mark, payload build, payload bytes with a sha256 of
the shipped buffers, peak RSS of a fresh per-tier process, and oracles (budgets, edge
membership coverage, edge-identity pick). Browser stages mount the payload in
headless Chromium and record first paint (mount + draw + readback), hover
(edge hit test + identity row) p50/p95, pan (pointer drag) and wheel zoom
(WheelEvent) redraw p95, JS heap, teardown, and nonblank pixels.

Profiles: ``smoke`` (small, medium; PR CI) and ``evidence`` (all tiers plus
LOD-decision rows; scheduled/manual on main, uploaded as a SHA-keyed
artifact). Usage:

  uv run python benchmarks/bench_graph_scale.py --profile smoke --out graph-scale.json
  uv run python scripts/verify_benchmark_report.py graph-scale.json --kind graph-scale
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import resource
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _xy_browser import chart_payload, json_bytes, page_for_charts, run_json_probe  # noqa: E402
from categories import BENCHMARK_CATEGORIES, categories_for  # noqa: E402
from environment import SCHEMA_VERSION, collect_environment_metadata  # noqa: E402

CATEGORY_IDS = ("graph_render_pipeline", "interaction_smoothness")
TIERS = {"small": 1_000, "medium": 10_000, "large": 100_000, "massive": 1_000_000}
PROFILES = {
    "smoke": ("small", "medium"),
    "evidence": ("small", "medium", "large", "massive"),
}
LOD_DECISION_NODES = (10_000_000, 100_000_000, 1_000_000_000)
EDGES_PER_NODE = 2
NODE_BUDGET = 200_000
EDGE_BUDGET = 500_000
PROBE_TIMEOUT_S = 240
# Browser budgets for the CI (software GL) environment. Recorded in every
# report and enforced by `verify_benchmark_report.py --kind graph-scale` for
# the tiers PR CI runs; larger tiers are evidence rows, not gates.
# Ceilings are ~3-4x the measured software-GL values (catastrophic-regression
# guards; baseline drift is judged per methodology §7).
BROWSER_BUDGETS_MS = {
    "small": {"first_paint_ms": 2_000.0, "hover_p95_ms": 60.0, "pan_p95_ms": 300.0},
    "medium": {"first_paint_ms": 6_000.0, "hover_p95_ms": 200.0, "pan_p95_ms": 2_000.0},
}


def _graph_inputs(n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(33_000 + n)
    x = rng.normal(0.0, 1.0, n)
    y = rng.normal(0.0, 1.0, n)
    edges = rng.integers(0, n, (EDGES_PER_NODE * n, 2))
    return x, y, edges


def _native_row(tier: str, n: int) -> tuple[dict[str, Any], Any]:
    import xyg
    from xyg import _graph, _native, interaction

    x, y, edges = _graph_inputs(n)
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t0 = time.perf_counter()
    data = _graph.resolve_graph_data(np.arange(n), edges)
    t1 = time.perf_counter()
    render, (offsets, members) = _native.graph_build_render_with_membership(
        x, y, data.sources, data.targets, node_budget=NODE_BUDGET, edge_budget=EDGE_BUDGET
    )
    t2 = time.perf_counter()
    rx, ry, _member_of, edge_s, edge_t, tier_code, _kept = render
    routed = _native.graph_edge_route_ends(
        rx,
        ry,
        edge_s,
        edge_t,
        node_radius_px=np.full(len(rx), 4.0),
        node_symbol=np.zeros(len(rx), dtype=np.uint8),
    )
    t3 = time.perf_counter()
    chart = xyg.graph_chart(
        xyg.graph(np.arange(n), edges, layout="preset", x=x, y=y), width=900, height=420
    )
    fig = chart.figure()
    t4 = time.perf_counter()
    spec, blob = fig.build_payload()
    t5 = time.perf_counter()
    # Peak resident set of this fresh per-tier process (Linux ru_maxrss is KiB).
    rss_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    meta = fig._graph_meta[0]
    counts = np.diff(offsets)
    pick = interaction.pick(fig, meta["edge_trace"], 0) if len(routed[0]) else None
    oracles = {
        "nodes_within_budget": len(rx) <= NODE_BUDGET,
        "edges_within_budget": len(edge_s) <= EDGE_BUDGET,
        "every_render_edge_has_members": bool(len(counts) == len(edge_s) and np.all(counts >= 1)),
        "no_member_repeats": bool(len(np.unique(members)) == len(members)),
        "edge_pick_identity": bool(pick is not None and pick.get("edge_count", 0) >= 1),
        "nonempty_payload": len(blob) > 0,
    }
    row = {
        "tier": tier,
        "mode": ("direct", "edge_sample", "aggregate")[min(int(tier_code), 2)],
        "n_nodes": n,
        "n_edges": int(len(edges)),
        "render_nodes": int(len(rx)),
        "render_edges": int(len(edge_s)),
        "routed_segments": int(len(routed[0])),
        "benchmark_categories": list(CATEGORY_IDS),
        "host_normalize_ms": 1e3 * (t1 - t0),
        "build_render_ms": 1e3 * (t2 - t1),
        "edge_route_ms": 1e3 * (t3 - t2),
        "graph_mark_ms": 1e3 * (t4 - t3),
        "payload_build_ms": 1e3 * (t5 - t4),
        "payload_bytes": json_bytes(spec) + len(blob),
        "payload_blob_sha256": hashlib.sha256(blob).hexdigest(),
        "peak_rss_bytes": int(rss_peak) * 1024,
        "peak_rss_growth_bytes": max(0, int(rss_peak - rss_before)) * 1024,
        "oracles": oracles,
        "oracle_status": "pass" if all(oracles.values()) else "fail",
    }
    return row, (spec, blob, meta)


def _probe_js(reps: int, edge_trace: int) -> str:
    return f"""
(async () => {{
  try {{
    const payload = XY_CHARTS[0];
    const el = document.createElement("div");
    el.style.width = "900px"; el.style.height = "420px";
    document.getElementById("root").appendChild(el);
    const heap0 = performance.memory ? performance.memory.usedJSHeapSize : null;
    // WebGL work is queued; a 1-pixel readback forces a frame to finish so
    // timings include rasterization, not just command submission.
    const px = new Uint8Array(4);
    let view = null;
    const sync = () => view.gl.readPixels(0, 0, 1, 1, view.gl.RGBA, view.gl.UNSIGNED_BYTE, px);
    const t0 = performance.now();
    view = xy.renderStandalone(el, payload.spec, xyBytesFromPayload(payload));
    view._drawNow();
    sync();
    const firstPaintMs = performance.now() - t0;
    const lit = xyNonblankPixels(view);
    await xyRaf();
    const g = view.gpuTraces.find((trace) => trace.trace.id === {edge_trace});
    if (!g || !g._segmentCpu) throw new Error("graph edge trace missing");
    const geom = view._polarGeometry();
    // Hover: real hit testing at routed segment midpoints; only hits on the
    // edge trace with a resolved row count as edge identity.
    const hover = [];
    let edgeHits = 0;
    const stride = Math.max(1, Math.floor(g.n / {reps}));
    for (let i = 0; i < g.n && hover.length < {reps}; i += stride) {{
      const [[x0, y0], [x1, y1]] = view._projectSegmentEndpoints(g, g._segmentCpu, i, geom);
      const cx = (x0 + x1) / 2 - view.plot.x, cy = (y0 + y1) / 2 - view.plot.y;
      const h0 = performance.now();
      const hit = view._hoverAt(cx, cy);
      const row = hit ? view._localRow(hit) : null;
      hover.push(performance.now() - h0);
      if (hit && hit.g === g && row && row.trace === {edge_trace} && hit.index < g.n) edgeHits++;
    }}
    // Pan and wheel zoom through the real input handlers, then settle the
    // queued gesture and force the frame to finish (same method as
    // bench_interaction.py).
    const rect = () => view.canvas.getBoundingClientRect();
    const at = (fx, fy) => {{ const r = rect(); return {{ clientX: r.left + fx * r.width, clientY: r.top + fy * r.height }}; }};
    view.canvas.setPointerCapture = () => {{}};
    view.canvas.releasePointerCapture = () => {{}};
    const settle = () => {{
      if (view._pendingWheelZoom) {{
        const pending = view._pendingWheelZoom;
        view._pendingWheelZoom = null;
        if (view._wheelZoomRaf) cancelAnimationFrame(view._wheelZoomRaf);
        view._wheelZoomRaf = null;
        view._zoomAt(pending.factor, pending.fx, pending.fy, false);
      }}
      if (view._viewAnim) {{ const target = view._viewAnim.target; view._cancelViewAnimation(); view.view = target; }}
      if (view._raf) {{ cancelAnimationFrame(view._raf); view._raf = null; }}
      view._drawNow();
      sync();
    }};
    const pan = [], zoom = [];
    let viewChanged = false;
    const before = JSON.stringify(view.view);
    for (let i = 0; i < {reps}; i++) {{
      const start = at(0.5, 0.5);
      const end = at(i % 2 ? 0.53 : 0.47, 0.5);
      const p0 = performance.now();
      view.canvas.dispatchEvent(new PointerEvent("pointerdown", {{ bubbles: true, pointerId: 7, ...start }}));
      view.canvas.dispatchEvent(new PointerEvent("pointermove", {{ bubbles: true, pointerId: 7, ...end }}));
      view.canvas.dispatchEvent(new PointerEvent("pointerup", {{ bubbles: true, pointerId: 7, ...end }}));
      settle();
      pan.push(performance.now() - p0);
      const z0 = performance.now();
      view.canvas.dispatchEvent(new WheelEvent("wheel", {{ bubbles: true, cancelable: true, deltaY: i % 2 ? 40 : -40, ...at(0.5, 0.5) }}));
      settle();
      zoom.push(performance.now() - z0);
      if (JSON.stringify(view.view) !== before) viewChanged = true;
    }}
    const heap1 = performance.memory ? performance.memory.usedJSHeapSize : null;
    view.gl.finish();
    const d0 = performance.now();
    if (typeof view.destroy === "function") view.destroy();
    const teardownMs = performance.now() - d0;
    xyReport("XY_GRAPH_SCALE", {{
      first_paint_ms: firstPaintMs,
      lit_pixels: lit,
      hover: xyStats(hover),
      hover_samples: hover.length,
      hover_edge_hits: edgeHits,
      pan: xyStats(pan),
      zoom: xyStats(zoom),
      view_changed: viewChanged,
      js_heap_bytes: heap1 == null || heap0 == null ? null : Math.max(0, heap1 - heap0),
      teardown_ms: teardownMs,
      segments: g.n,
    }});
  }} catch (error) {{
    xyFail("XY_GRAPH_SCALE", error);
  }}
}})();
"""


def _browser_stage(
    row: dict[str, Any],
    built: Any,
    *,
    reps: int,
    chromium: str | None,
    retries: int,
    timeout_s: int,
) -> None:
    spec, blob, meta = built
    html = page_for_charts(
        [chart_payload("graph", spec, blob)],
        _probe_js(reps, int(meta["edge_trace"])),
        title="xy graph scale probe",
    )
    row["html_bytes"] = len(html.encode("utf-8"))
    result: dict[str, Any] = {}
    for attempt in range(retries + 1):
        result = run_json_probe(
            html,
            marker="XY_GRAPH_SCALE",
            chromium=chromium,
            virtual_time_ms=None,
            timeout_s=timeout_s,
            hosted=True,
        )
        if result.get("status") == "ok":
            break
        print(
            f"graph probe retry {attempt + 1}/{retries} for {row['tier']}: {result.get('status')}",
            file=sys.stderr,
        )
    row["browser_status"] = result.get("status", "failed")
    if row["browser_status"] != "ok":
        return
    row["first_paint_ms"] = result["first_paint_ms"]
    row["lit_pixels"] = result["lit_pixels"]
    row["hover_p50_ms"] = result["hover"]["median_ms"]
    row["hover_p95_ms"] = result["hover"]["p95_ms"]
    row["hover_samples"] = result["hover_samples"]
    row["hover_edge_hits"] = result["hover_edge_hits"]
    row["pan_p95_ms"] = result["pan"]["p95_ms"]
    row["zoom_p95_ms"] = result["zoom"]["p95_ms"]
    row["js_heap_bytes"] = result["js_heap_bytes"]
    row["teardown_ms"] = result["teardown_ms"]
    row["browser_segments"] = result["segments"]
    row["oracles"]["nonblank_first_paint"] = result["lit_pixels"] > 0
    # Most midpoint hovers must resolve to an edge (crossing segments or a
    # node near a midpoint may legitimately win a few samples).
    row["oracles"]["hover_resolves_edges"] = (
        result["hover_samples"] > 0 and 2 * result["hover_edge_hits"] >= result["hover_samples"]
    )
    row["oracles"]["gestures_change_view"] = bool(result["view_changed"])
    row["oracles"]["browser_segments_match"] = result["segments"] == row["routed_segments"]
    row["oracle_status"] = "pass" if all(row["oracles"].values()) else "fail"


def _lod_rows() -> list[dict[str, Any]]:
    from xyg import _native

    rows = []
    for n in LOD_DECISION_NODES:
        t0 = time.perf_counter()
        tier_code, kept = _native.graph_lod_decision(
            n, EDGES_PER_NODE * n, node_budget=NODE_BUDGET, edge_budget=EDGE_BUDGET
        )
        rows.append(
            {
                "n_nodes": n,
                "n_edges": EDGES_PER_NODE * n,
                "mode": "lod_decision",
                "tier": ("direct", "edge_sample", "aggregate")[min(int(tier_code), 2)],
                "edges_kept": int(kept),
                "decision_ms": 1e3 * (time.perf_counter() - t0),
                "oracle_status": "pass" if int(kept) <= EDGE_BUDGET else "fail",
            }
        )
    return rows


def run(
    *,
    profile: str,
    reps: int,
    chromium: str | None,
    retries: int,
    browser: bool,
    tiers: tuple[str, ...] | None = None,
    timeout_s: int = PROBE_TIMEOUT_S,
) -> dict[str, Any]:
    rows = []
    context = multiprocessing.get_context("spawn")
    for tier in tiers or PROFILES[profile]:
        # A fresh process per tier keeps peak RSS attributable to that tier.
        # ProcessPoolExecutor raises BrokenProcessPool if the worker dies
        # (e.g. OOM) instead of hanging the run.
        with ProcessPoolExecutor(max_workers=1, mp_context=context) as pool:
            row, built = pool.submit(_native_row, tier, TIERS[tier]).result()
        if browser:
            _browser_stage(
                row, built, reps=reps, chromium=chromium, retries=retries, timeout_s=timeout_s
            )
        rows.append(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "graph-scale",
        "profile": profile,
        "measurement_scope": "graph-render-pipeline-and-browser-interaction",
        "environment": collect_environment_metadata(chromium=chromium),
        "benchmark_categories": list(BENCHMARK_CATEGORIES),
        "tracked_categories": categories_for(CATEGORY_IDS),
        "tiers": dict(TIERS),
        "edges_per_node": EDGES_PER_NODE,
        "node_budget": NODE_BUDGET,
        "edge_budget": EDGE_BUDGET,
        "browser_budgets_ms": BROWSER_BUDGETS_MS,
        "reps": reps,
        "rows": rows,
        "lod_decision_rows": _lod_rows() if profile == "evidence" else [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", choices=sorted(PROFILES), default="smoke")
    parser.add_argument("--reps", type=int, default=24)
    parser.add_argument("--chromium")
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--tiers",
        help="comma-separated tier subset for local diagnostics (not a verifiable profile)",
    )
    parser.add_argument("--probe-timeout", type=int, default=PROBE_TIMEOUT_S)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run(
        profile=args.profile,
        reps=args.reps,
        chromium=args.chromium,
        retries=args.retries,
        browser=not args.no_browser,
        tiers=tuple(args.tiers.split(",")) if args.tiers else None,
        timeout_s=args.probe_timeout,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    failed = [row["tier"] for row in report["rows"] if row["oracle_status"] != "pass"]
    if failed:
        raise SystemExit(f"graph-scale oracle failures: {failed}")


if __name__ == "__main__":
    main()
