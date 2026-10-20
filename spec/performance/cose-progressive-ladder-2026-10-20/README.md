# CoSE progressive-layout size ladder (#35, criterion 4)

First-paint latency and progress cadence of the shipped progressive CoSE
schedulers on a node-count ladder, plus the evidence behind the cross-host
parity tolerance (`spec/design/graph-mark.md`, "CoSE cross-host parity").
**Evidence, not a CI gate** (#108 lean policy); regenerate on a quiet host
before quoting absolute numbers.

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
- **First paint** = job start → first delivered checkpoint (Worker start where
  applicable + handle build + seeded placement + tick 1 + delivery to the host
  thread). **Cadence** = gap between delivered checkpoints of 10 ticks each
  (`chunk_steps = 10`). **Event-loop lag** = worst/p95 overshoot of a 5 ms
  ticker on the host thread while the job ran. Peak RSS is of a fresh per-rung
  process (Python: `ru_maxrss`; Node: process incl. Worker thread; browser: not
  measured, JS heap in raw rows).
- Rungs: 1k, 10k, 100k, 1M nodes (7/7/5/1 repetitions, 40/30/10/5 progress
  chunks). **1M is the admission ceiling** (`MAX_NODES = 1_000_000` in the Node
  scheduler and the WASM `XYGL` request, `MAX_EDGES = 4_000_000`); nothing above
  it is admitted, so there is no 10M rung. The 1M rung is one cold repetition
  and ≤ 423 MB RSS, far inside the 16 GB budget.

## Result (this host, see caveats)

Median first paint / cadence p50 / cadence p95, milliseconds (`max` lag = worst
host-thread stall during the job):

| Rung | Host | first paint p50 (max) | cadence p50 | cadence p95 | lag p95 / max | peak RSS |
|---|---|---:|---:|---:|---:|---:|
| 1k | Python native | 4 (6) | 13 | 27 | 2.8 / 6 | 44 MB |
| 1k | Node worker_threads | 210 (376) | 11 | 24 | 3.0 / 16 | 102 MB |
| 1k | Browser WASM Worker | 4 (49) | 24 | 39 | 2.9 / 18 | n/a |
| 10k | Python native | 9 (13) | 103 | 166 | 3.1 / 35 | 46 MB |
| 10k | Node worker_threads | 251 (445) | 100 | 155 | 3.3 / 32 | 129 MB |
| 10k | Browser WASM Worker | 15 (56) | 155 | 264 | 2.7 / 591 | n/a |
| 100k | Python native | 208 (233) | 348 | 455 | 3.0 / 42 | 69 MB |
| 100k | Node worker_threads | 508 (661) | 356 | 485 | 3.8 / 31 | 227 MB |
| 100k | Browser WASM Worker | 123 (241) | 526 | 929 | 2.2 / 598 | n/a |
| 1M | Python native | 1267 | 1604 | 2039 | 2.7 / 12 | 281 MB |
| 1M | Node worker_threads | 1325 | 1621 | 1891 | 2.5 / 34 | 422 MB |
| 1M | Browser WASM Worker | 1512 | 3593 | 3824 | 1.6 / 28 | n/a |

Reading: no host runs layout on its interactive thread — the host-thread p95
stall stays ≤ 4 ms on every rung of every host. First paint up to 100k is
≤ 0.7 s and at 1M ≈ 1.3–1.5 s; progress then arrives every ~0.1 s (10k) to
~0.35–0.5 s (100k) and ~1.6 s native / ~3.6 s WASM at 1M. The browser
host-thread max stalls (591/598 ms at 10k/100k) are single events in headless
software-GL Chromium (main-thread `structuredClone`/GC of checkpoint buffers
under host load) and are recorded as an open observation, not a pass/fail claim.
The Node Worker's first paint is dominated by Worker spawn + native-library load
(≈ 200 ms) because `runForceTicks` creates a fresh Worker per job.

## Caveats

- **Shared, heavily loaded host**: load average 35–45 on 16 cores
  (`loadavg_1m` per row in `results.json`), Ryzen 7 3800X, Linux 7.0, Node
  22.22.1, CPython 3.13.12, rustc 1.96.0. Absolute times are inflated and noisy;
  relative ordering and orders of magnitude are the claim.
- The `environment.git.dirty` flag is true: the harness files themselves were
  uncommitted when the run started (commit `894027f8` + the harness edits in the
  PR that adds this directory). Chromium: Chrome for Testing 149.0.7827.55
  (Playwright cache), software GL.
- Python's `GraphLayoutController` reuses one thread across repetitions; Node
  spawns a Worker per job (as shipped); the WASM Worker is created once per
  rung and its start-up is not part of first paint.

## Reproduce

```bash
cargo build --release -p xyg-core && cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs && node js/package-wasm.mjs        # dist + xyg-wasm.wasm
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
uv run python scripts/bench_cose_progressive.py --out results.json
#   subset:  --rungs 1k,10k --hosts python,node   (browser rung: --chromium PATH)
```

`results.json` holds the raw per-repetition `first_paint_ms` / `cadence_ms`
arrays, the per-rung summary, the protocol, and `benchmarks/environment.py`
metadata. Output contract: `schema = "cose-progressive-ladder/1"`.

## Parity finding (native vs WASM)

`portable-sincos-experiment.patch` is the two-site Rust patch (`layout_circle`
and the CoSE per-component gravity anchor use `portable_sin_cos`) that makes all
11 golden fixtures — seeded and disconnected included — bitwise identical
between native and wasm32 (23/23 Node parity tests, no `todo`). It is evidence
only; it is **not applied** because it shifts every seeded layout by ulps on
all hosts and needs its own golden/ABI-fixture refresh.
