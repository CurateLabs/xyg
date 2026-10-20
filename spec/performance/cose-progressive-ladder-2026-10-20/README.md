# CoSE progressive-layout size ladder (#35, criterion 4)

**Checkpoint-delivery latency and cadence** of the shipped progressive CoSE
schedulers on a node-count ladder (the cross-host parity tolerance lives in
`spec/design/graph-mark.md`, "CoSE cross-host parity"). **Evidence, not a CI
gate** (#108 lean policy); regenerate on a quiet host before quoting absolute
numbers.

**What this is not.** It does *not* measure first paint or interactivity. The
browser rung records when a checkpoint reaches an otherwise empty page: it
renders no graph, excludes browser start-up, and measures no pick/pan latency.
Criterion 4's first-paint gate therefore stays **open** (see "Remaining for
#35"). The JSON key `first_paint_ms` in `results.json` is a historical name for
*first-checkpoint delivery latency*.

## Protocol

- Graph: ring + one deterministic chord per node (2 edges/node, identical
  generators in Python and JS), Rust-seeded start, default CoSE options, seed 7.
  No authored positions, so every host runs the same "fast initial placement".
- Schedulers under test, unmodified:
  `xyg.GraphLayoutController` (native Rust handle, dedicated thread, callbacks
  on the asyncio loop); `packages/xy-node/src/force_scheduler.js`
  `runForceTicks` in a `worker_threads` Worker (Worker spawned per job);
  `createXygWasmWorker` + `layoutWasmCose` (WASM kernel in a Web Worker, one
  Worker per rung, fresh job per repetition) in headless Chromium 149 with
  SwiftShader (the Worker path does not touch GL).
- **First-checkpoint latency** (`first_paint_ms`) = job start → first delivered
  checkpoint (Worker start where applicable + handle build + seeded placement +
  tick 1 + delivery to the host thread; nothing is rendered). **Cadence** = gap between delivered checkpoints of 10 ticks each
  (`chunk_steps = 10`). **Event-loop lag** = worst/p95 overshoot of a 5 ms
  ticker on the host thread while the job ran. Peak RSS is of a fresh per-rung
  process (Python: `ru_maxrss`; Node: process incl. Worker thread; browser: not
  measured). The browser script also reports `worker_ready_ms` and `js_heap_mb`,
  but the orchestrator that wrote the committed `results.json` dropped them (fixed
  for future runs; the committed run does not contain them).
- Rungs: 1k, 10k, 100k, 1M nodes (7/7/5/1 repetitions, 40/30/10/5 progress
  chunks). **1M is the admission ceiling** (`MAX_NODES = 1_000_000` in the Node
  scheduler and the WASM `XYGL` request, `MAX_EDGES = 4_000_000`); nothing above
  it is admitted, so there is no 10M rung. The 1M rung is one cold repetition
  and ≤ 423 MB RSS, far inside the 16 GB budget.

## Result (this host, see caveats)

Milliseconds. First-checkpoint latency is the median (max); cadence is the gap
between delivered 10-tick checkpoints; lag is the host-thread p95 / max stall of
a 5 ms ticker while the job ran.

| Rung | Host | first-checkpoint p50 (max) | cadence p50 | cadence p95 | lag p95 / max | peak RSS |
|---|---|---:|---:|---:|---:|---:|
| 1k | python-native | 2 (4) | 11 | 13 | 3.2 / 8 | 44 MB |
| 1k | node-worker-threads | 143 (160) | 11 | 14 | 2.1 / 10 | 102 MB |
| 1k | browser-wasm-worker | 2 (9) | 13 | 18 | 2.6 / 4 | n/a |
| 10k | python-native | 5 (6) | 32 | 39 | 1.5 / 5 | 46 MB |
| 10k | node-worker-threads | 119 (145) | 35 | 45 | 1.8 / 8 | 173 MB |
| 10k | browser-wasm-worker | 8 (25) | 112 | 125 | 0.6 / 40 | n/a |
| 100k | python-native | 53 (81) | 140 | 186 | 3.6 / 7 | 70 MB |
| 100k | node-worker-threads | 128 (179) | 136 | 152 | 1.5 / 5 | 198 MB |
| 100k | browser-wasm-worker | 50 (106) | 315 | 533 | 0.3 / 4 | n/a |
| 1M | python-native | 806 (806) | 1362 | 1383 | 1.8 / 12 | 281 MB |
| 1M | node-worker-threads | 965 (965) | 1376 | 1395 | 1.8 / 25 | 423 MB |
| 1M | browser-wasm-worker | 1281 (1281) | 2852 | 3214 | 0.1 / 19 | n/a |

Reading: the layout work runs on a worker thread/Worker on every host, and
the measured host-thread stalls are small but not zero: p95 ≤ 3.6 ms on every
rung, **max stalls up to 40 ms** (browser, 10k), 25 ms (Node, 1M), 12 ms (Python,
1M). This is consistent with, but does not prove, "layout never blocks the
host". First-checkpoint latency p50 is ≤ 0.15 s through 100k nodes (Python/WASM
≤ 0.06 s) and 0.8–1.3 s at 1M; progress then arrives every ~11–13 ms (1k),
32–112 ms (10k), 136–315 ms (100k) and ~1.4 s native / ~2.9 s WASM (1M). The
Node latency (~120–140 ms through 100k) is Worker spawn + native-library load,
because `runForceTicks` creates a fresh Worker per job. The WASM kernel's cadence
is ~2–3× the native one at 10k and above.

**Browser main-thread stalls — not reproduced.** The first (more heavily
loaded, load average 35–45) run measured single browser host-thread stalls of
591 ms at 10k and 598 ms at 100k. In this run the browser rung's max stalls were
4 ms (1k), 40 ms (10k), 4 ms (100k) and 19 ms (1M), so the large stalls did not
persist at lower host load (load average 12–23). They are not diagnosed here;
if they are reported again they should be tracked as a separate issue.

## Caveats

- **Shared host**: load average 15.2/18.4/23.8 at start and 12.3/16.6/22.5 at
  end (`environment.loadavg`, 1-minute value per row in `loadavg_1m`), Ryzen 7
  3800X (16 threads), Linux 7.0, Node 22.22.1, CPython 3.13.12, rustc 1.96.0,
  Chrome for Testing 149.0.7827.55 with software GL. Treat absolute times as
  upper-ish bounds and re-run on a quiet host before quoting.
- `environment.git`: commit `cb78c1f4`, `dirty: false`. The run uses the build
  that includes the `portable_sin_cos` change (seeded layouts differ by ulps
  from earlier runs).
- Python's `GraphLayoutController` reuses one thread across repetitions; Node
  spawns a Worker per job (as shipped); the WASM Worker is created once per
  rung and its start-up is not part of first-checkpoint latency.

## Reproduce

```bash
cargo build --release -p xyg-core && cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs && node js/package-wasm.mjs        # dist + xyg-wasm.wasm
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
uv run python scripts/bench_cose_progressive.py --out results.json
#   subset:  --rungs 1k,10k --hosts python,node   (browser rung: --chromium PATH)
```

## Remaining for #35

- A **render-based first-paint and interactivity measurement** on the ladder
  (graph drawn, first pick/pan latency, browser start-up included) — criterion 4
  stays open until it exists.
- **Node async composition** (criterion 7: `composeGraphForge` /
  `graphforgeWebviewPayload` defaulting to `worker_threads`), after #934.

`results.json` holds the raw per-repetition `first_paint_ms` / `cadence_ms`
arrays, the per-rung summary, the protocol, and `benchmarks/environment.py`
metadata. Output contract: `schema = "cose-progressive-ladder/1"`.
