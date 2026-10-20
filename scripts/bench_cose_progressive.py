#!/usr/bin/env python3
"""First-paint and progress-cadence ladder for progressive CoSE layout (issue #35).

Drives the *shipped* schedulers on one seeded CoSE graph per rung (ring + one
deterministic chord per node, Rust-seeded start, default CoSE options):

* ``python``  -- ``xyg.GraphLayoutController`` (native Rust handle on a dedicated
  thread, checkpoints delivered on the asyncio loop);
* ``node``    -- ``packages/xy-node/src/force_scheduler.js`` ``runForceTicks``
  in a ``worker_threads`` Worker (``scripts/bench_cose_progressive_node.mjs``);
* ``browser`` -- the WASM kernel in a Web Worker via ``layoutWasmCose`` in
  headless Chromium (``scripts/bench_cose_progressive_browser.py``), when a
  Chromium binary is available.

Per rung it records first paint (job start -> first delivered checkpoint, which
includes worker start, handle construction and the seeded placement plus tick 1)
and progress cadence (gaps between later delivered checkpoints of
``chunk_steps`` ticks each), plus the worst host event-loop stall and the peak
RSS of a fresh per-rung process. Evidence, not a CI gate.

  flock /tmp/xyg-heavy-build.lock uv run python scripts/bench_cose_progressive.py \
      --out spec/performance/cose-progressive-ladder-<date>/results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import resource
import statistics
import subprocess
import sys
import time
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "benchmarks"))

CHUNK_STEPS = 10
# rung -> (nodes, progress chunks after the initial tick, repetitions). The 1M
# rung is the Node/WASM request ceiling (MAX_NODES = 1_000_000); few chunks and a
# single cold run bound wall time and memory (<= 16 GB host budget).
RUNGS = {
    "1k": (1_000, 40, 5),
    "10k": (10_000, 30, 5),
    "100k": (100_000, 10, 3),
    "1M": (1_000_000, 3, 1),
}
MAX_WALL_MS = 300_000


def ladder_edges(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Ring + one deterministic chord per node; identical in the Node/browser rungs."""
    i = np.arange(n, dtype=np.uint64)
    chord = (i * np.uint64(7) + np.uint64(3)) % np.uint64(n)
    chord = np.where(chord == i, (i + np.uint64(2)) % np.uint64(n), chord)
    sources = np.empty(2 * n, dtype=np.uint64)
    targets = np.empty(2 * n, dtype=np.uint64)
    sources[0::2] = i
    targets[0::2] = (i + np.uint64(1)) % np.uint64(n)
    sources[1::2] = i
    targets[1::2] = chord
    return sources, targets


def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def summarize(host_row: dict[str, Any]) -> dict[str, Any]:
    reps = host_row["reps"]
    cadence = [gap for rep in reps for gap in rep["cadence_ms"]]
    first = [rep["first_paint_ms"] for rep in reps]
    return {
        "first_paint_ms": {"min": min(first), "p50": statistics.median(first), "max": max(first)},
        "cadence_ms": {
            "n": len(cadence),
            "p50": statistics.median(cadence) if cadence else None,
            "p95": _pct(cadence, 0.95) if cadence else None,
            "max": max(cadence) if cadence else None,
        },
        "max_event_loop_lag_ms": max(rep["max_event_loop_lag_ms"] for rep in reps),
        "peak_rss_mb": host_row["peak_rss_mb"],
    }


async def _python_rep(controller: Any, n_steps: int) -> dict[str, Any]:
    arrivals: list[float] = []
    lag = 0.0
    stop = asyncio.Event()

    async def ticker() -> None:
        nonlocal lag
        last = time.perf_counter()
        while not stop.is_set():
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            lag = max(lag, (now - last - 0.005) * 1000.0)
            last = now

    watch = asyncio.create_task(ticker())
    started = time.perf_counter()
    result = await controller.layout(
        revision=_python_rep.revision,
        layout="cose",
        seed=7,
        total_steps=n_steps,
        chunk_steps=CHUNK_STEPS,
        max_wall_ms=MAX_WALL_MS,
        on_update=lambda _checkpoint: arrivals.append(time.perf_counter()),
    )
    wall = time.perf_counter() - started
    stop.set()
    await watch
    _python_rep.revision += 1
    return {
        "first_paint_ms": (arrivals[0] - started) * 1000.0,
        "cadence_ms": [(b - a) * 1000.0 for a, b in pairwise(arrivals)],
        "checkpoints": len(arrivals),
        "steps": result.step,
        "wall_ms": wall * 1000.0,
        "max_event_loop_lag_ms": max(0.0, lag),
    }


_python_rep.revision = 1  # type: ignore[attr-defined]


def run_python_child(nodes: int, chunks: int, reps: int) -> dict[str, Any]:
    from xyg import GraphLayoutController
    from xyg._graph import GraphData

    sources, targets = ladder_edges(nodes)
    data = GraphData(list(range(nodes)), sources, targets)
    n_steps = 1 + chunks * CHUNK_STEPS

    async def main() -> list[dict[str, Any]]:
        controller = GraphLayoutController(data)
        try:
            return [await _python_rep(controller, n_steps) for _ in range(reps)]
        finally:
            controller.dispose()

    rows = asyncio.run(main())
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    return {
        "host": "python-native",
        "nodes": nodes,
        "edges": 2 * nodes,
        "chunk_steps": CHUNK_STEPS,
        "total_steps": n_steps,
        "reps": rows,
        "peak_rss_mb": rss_mb,
    }


def _run_child(cmd: list[str], timeout_s: float) -> dict[str, Any]:
    done = subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True, timeout=timeout_s, cwd=ROOT, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(f"{cmd[:3]} failed ({done.returncode}): {done.stderr[-800:]}")
    return json.loads(done.stdout.strip().splitlines()[-1])


def run(rungs: list[str], hosts: list[str], chromium: str | None) -> dict[str, Any]:
    from environment import collect_environment_metadata

    rows: list[dict[str, Any]] = []
    for rung in rungs:
        nodes, chunks, reps = RUNGS[rung]
        for host in hosts:
            started = time.time()
            try:
                if host == "python":
                    raw = _run_child(
                        [sys.executable, __file__, "--child", "python", "--nodes", str(nodes),
                         "--chunks", str(chunks), "--reps", str(reps)],
                        timeout_s=1800,
                    )  # fmt: skip
                elif host == "node":
                    raw = _run_child(
                        ["node", "scripts/bench_cose_progressive_node.mjs", "--nodes", str(nodes),
                         "--chunks", str(chunks), "--chunk-steps", str(CHUNK_STEPS),
                         "--reps", str(reps), "--max-wall-ms", str(MAX_WALL_MS)],
                        timeout_s=1800,
                    )  # fmt: skip
                else:
                    cmd = [
                        sys.executable, "scripts/bench_cose_progressive_browser.py",
                        "--nodes", str(nodes), "--chunks", str(chunks),
                        "--chunk-steps", str(CHUNK_STEPS), "--reps", str(reps),
                    ]  # fmt: skip
                    if chromium:
                        cmd += ["--chromium", chromium]
                    raw = _run_child(cmd, timeout_s=1800)
                rows.append(
                    {
                        "rung": rung,
                        "host": raw["host"],
                        "nodes": nodes,
                        "edges": raw["edges"],
                        "chunk_steps": raw["chunk_steps"],
                        "total_steps": raw["total_steps"],
                        "status": "ok",
                        "summary": summarize(raw),
                        "reps": raw["reps"],
                        "elapsed_s": time.time() - started,
                    }
                )
            except Exception as error:  # a failed rung is recorded, never dropped
                rows.append(
                    {
                        "rung": rung,
                        "host": host,
                        "nodes": nodes,
                        "status": "failed",
                        "error": str(error),
                    }
                )
    return {
        "schema": "cose-progressive-ladder/1",
        "issue": "CurateLabs/xyg#35",
        "protocol": {
            "graph": "ring + one deterministic chord per node (2 edges/node), Rust-seeded start, "
            "default CoSE options, seed 7",
            "first_paint": "job start -> first delivered checkpoint (worker start + handle build + "
            "seeded placement + tick 1 + delivery)",
            "cadence": f"gap between delivered checkpoints of {CHUNK_STEPS} ticks each",
            "rungs": {k: {"nodes": v[0], "chunks": v[1], "reps": v[2]} for k, v in RUNGS.items()},
        },
        "environment": collect_environment_metadata(chromium=chromium),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rungs", default=",".join(RUNGS))
    parser.add_argument("--hosts", default="python,node,browser")
    parser.add_argument("--chromium")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--child", choices=["python"], help=argparse.SUPPRESS)
    parser.add_argument("--nodes", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--chunks", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--reps", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        print(json.dumps(run_python_child(args.nodes, args.chunks, args.reps)))
        return
    report = run(args.rungs.split(","), args.hosts.split(","), args.chromium)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
