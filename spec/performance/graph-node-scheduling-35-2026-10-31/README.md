# #35 Node live scheduling: bounded functional paint receipt

This is a local functional render proof on the four-node `cyclic` GraphForge
property-graph fixture, with native CoSE and the existing local painter. It is
not a timing threshold, competitor comparison, scale ladder, hardware
acceptance, installed-package qualification or WASM release qualification.
The S4 real-WASM gate remains outside this proof. Historical results/runners
are unchanged.

The exact starting source is parent local
`dee3ea37540a7126c3082ae59624bb02881bb00f`; `result.json` binds source file,
fixture, native, client and screenshot hashes, executable versions/paths,
OS/architecture, and Rust version. The parent receives the focused commit and
canonical binary/full-index diff hash after commit. Native core was rebuilt
from this base with `cargo build --release --offline`; painter bundles were
built locally once with `node js/build.mjs` (build log included). No WASM
artifact is used or promoted by this journey.

## Reproduce without overwriting this receipt

From the repository root, use Node 22.23.4, the local native build and Chromium
156.0.8078.4 at the explicit paths recorded in `result.json`. Dependencies are
root `npm ci`, `npm ci --prefix packages/xy-node` and `uv sync --group dev`.
No browser download is required on this host.

```bash
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:/home/ubuntu/.cargo/bin:$PATH
cargo build --release --offline
node js/build.mjs
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
node spec/performance/graph-node-scheduling-35-2026-10-31/run.mjs
node --test packages/xy-node/test/graphforge-layout.test.mjs packages/xy-node/test/graphforge.test.mjs packages/xy-node/test/graphforge-cross-host.test.mjs packages/xy-node/test/graph.test.mjs packages/xy-node/test/composition.test.mjs packages/xy-node/test/force-worker-lifecycle.test.mjs packages/xy-node/test/vscode_contract.test.mjs
uv run python scripts/abi_smoke.py
```

The browser runner defaults to a new `target/task-tmp/graph-node-scheduling-35-<timestamp>/`
directory; it refuses to overwrite an existing result. An explicit fresh
`XYG_GRAPH_NODE_RECEIPT_OUTPUT` can choose a different output directory. Original
capture selected this new receipt directory before it contained committed
results. The runner launches the repository fixture, loads only local assets,
and closes browser, Node workers and server afterward. Each browser wait is
bounded. It uses the repository's Playwright/headless Chromium proof workflow,
with ANGLE SwiftShader software rendering and a 900×650 viewport.

## What the raw outputs prove

`run.log` / `result.json`, `initial.png` and `final.png` show:

- Cold Node fixture startup and cold browser launch separately from navigation
  and the measured render request.
- Actual initial and changed later graph pixels, after two animation frames
  and framebuffer readback. First checkpoint delivery and first painted frame
  are separately timestamped. Source-position digests differ across step 1
  and step 60; render payloads and exact revision/job identity are retained.
- A real pointer click through the GPU pick path and host UUID response, plus
  a real pointer pan changing the viewport, on both initial and final frames.
  Pointer-to-identity and the combined multi-step pan journey include automation
  and software-rendering overhead; they are observations, not latency targets.
- No browser errors or non-local requests; disposal removes the canvas.
- Caller synchronous submission time, a 5 ms event-loop ticker, and worker
  native packing time. Source input/identity cloning and user callbacks still
  cost main-thread CPU; this small fixture does not establish scale behavior.

The consumer deliberately holds each payload ACK until screenshot/pick/pan
inspection finishes. Presentation cadence therefore includes this harness
pause and full view replacement, not native force checkpoint cadence. Full
replacement resets viewport, following the existing vanilla example. Retained
S5 updates and viewport continuity are not implemented. The existing
1k/10k/100k/1M checkpoint ladder remains scheduler-only evidence; large-scale
paint and interactivity are still required separately.

`node-tests.log` records 126 passing affected tests with no skips. New tests
trap native force outside the real scheduler Worker, composition and graph
packing on the caller thread; assert one force handle, real native destruction
and both worker exits before terminal settlement; compare all 12 CoSE golden
cases; cover bit-exact pins, compound planes, aggregate source positions,
coalescing, isolation, supersession, stale replies, disposal, abort, timeout and
callback failures. Existing property/analytical/static and scheduler tests
remain green. `abi-smoke.log` records 673 passing native seam checks.

The separately recorded `baseline-contract-failure.log` is an existing
`no_browser_globals` false positive on generated S4 ABI signature text, proved
unchanged from the parent base in `baseline-contract-finding.json`. It is not
waived or repaired here. Full repository hooks/Ruff outcomes are recorded
separately. Shared-spec/API-inventory edits and this failure need the parent's
disposition before PR; see `HANDOFF.md`.
