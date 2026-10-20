#!/usr/bin/env python3
"""Browser Web Worker (WASM) rung of the CoSE progressive-layout ladder (#35).

Serves the repo over a loopback HTTP server, loads ``packages/xy-client/dist``
in headless Chromium, and drives ``createXygWasmWorker`` + ``layoutWasmCose``
(the shipped Worker contract) on the same ring+chord graph as
``scripts/bench_cose_progressive.py``. Prints one JSON row on stdout. The worker
is created once per rung (like a live graph view) and its ready time is recorded
separately; every repetition is a fresh job on that worker.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))

PAGE = """<!doctype html><meta charset=utf-8><body><script type=module>
import { createXygWasmWorker, layoutWasmCose } from "/packages/xy-client/dist/index.js";
const wasm = await WebAssembly.compile(await (await fetch("/packages/xy-client/dist/xyg-wasm.wasm")).arrayBuffer());
window.runRung = async ({ nodes, chunks, chunkSteps, reps }) => {
  const sources = new BigUint64Array(2 * nodes), targets = new BigUint64Array(2 * nodes);
  for (let i = 0; i < nodes; i += 1) {
    let chord = (i * 7 + 3) % nodes; if (chord === i) chord = (i + 2) % nodes;
    sources[2 * i] = BigInt(i); targets[2 * i] = BigInt((i + 1) % nodes);
    sources[2 * i + 1] = BigInt(i); targets[2 * i + 1] = BigInt(chord);
  }
  const totalSteps = 1 + chunks * chunkSteps;
  const readyStart = performance.now();
  const worker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm, maxArenaBytes: 402653184 });
  await worker.ready;
  const workerReadyMs = performance.now() - readyStart;
  const out = [];
  for (let rep = 0; rep < reps; rep += 1) {
    const arrivals = [];
    let last = performance.now(); const lags = [];
    const ticker = setInterval(() => { const now = performance.now(); lags.push(Math.max(0, now - last - 5)); last = now; }, 5);
    const started = performance.now();
    const task = layoutWasmCose(worker, { nNodes: nodes, sources, targets, totalSteps, seed: 7n },
      { revision: rep + 1, chunkSteps, maxWallMs: 300000, onUpdate: () => arrivals.push(performance.now()) });
    const result = await task.result;
    // The complete checkpoint resolves the task instead of firing onUpdate.
    if (arrivals.length < 1 + chunks) arrivals.push(performance.now());
    clearInterval(ticker);
    out.push({
      first_paint_ms: arrivals[0] - started,
      cadence_ms: arrivals.slice(1).map((t, i) => t - arrivals[i]),
      checkpoints: arrivals.length, steps: result.step, wall_ms: performance.now() - started,
      p95_event_loop_lag_ms: [...lags].sort((a, b) => a - b)[Math.min(lags.length - 1, Math.round(0.95 * (lags.length - 1)))],
      max_event_loop_lag_ms: lags.reduce((a, b) => Math.max(a, b), 0),
    });
  }
  const heap = performance.memory ? performance.memory.usedJSHeapSize / 1048576 : null;
  await worker.dispose();
  return { reps: out, worker_ready_ms: workerReadyMs, js_heap_mb: heap };
};
window.ready = true;
</script>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--nodes", type=int, required=True)
    parser.add_argument("--chunks", type=int, required=True)
    parser.add_argument("--chunk-steps", type=int, default=10)
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--chromium")
    args = parser.parse_args()

    from _cdp import Browser, default_chromium

    chromium = args.chromium or default_chromium()
    if not chromium:
        raise SystemExit("no Chromium binary found (set --chromium or XYG_CHROMIUM)")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/__cose_ladder.html":
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def log_message(self, *_args: object) -> None:
            pass

    handler = functools.partial(Handler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        browser = Browser(
            chromium, gl="software", extra_flags=["--js-flags=--max-old-space-size=8192"]
        )
        try:
            page = browser.new_page()
            page.navigate(f"{base}/__cose_ladder.html")
            page.eval(
                "new Promise(r => { const t = setInterval(() => { if (window.ready) { clearInterval(t); r(true); } }, 20); })",
                timeout_s=120,
            )
            row = page.eval(
                f"window.runRung({json.dumps({'nodes': args.nodes, 'chunks': args.chunks, 'chunkSteps': args.chunk_steps, 'reps': args.reps})})",
                timeout_s=1500.0,
            )
        finally:
            # Chromium may still be writing its profile; a temp-dir race on teardown
            # must not discard a completed measurement.
            with contextlib.suppress(OSError):
                browser.close()
        print(
            json.dumps(
                {
                    "host": "browser-wasm-worker",
                    "nodes": args.nodes,
                    "edges": 2 * args.nodes,
                    "chunk_steps": args.chunk_steps,
                    "total_steps": 1 + args.chunks * args.chunk_steps,
                    "reps": row["reps"],
                    "worker_ready_ms": row["worker_ready_ms"],
                    "peak_rss_mb": None,
                    "js_heap_mb": row["js_heap_mb"],
                }
            )
        )
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
