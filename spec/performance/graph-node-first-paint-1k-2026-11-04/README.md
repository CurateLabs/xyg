# Bounded Node rendered first paint: existing 1k rung (#35, partial)

Production source base: `207ebdbdaa2ec8b0360c571683eb0fa6165e02c0`.
This evidence-only change adds no production implementation, CI gate, benchmark
suite, policy, budget, mask, tolerance or dependency. It neither closes #35 nor
qualifies #108, M4, PyPI/npm publication, another host or a larger rung.
Parent independent review and integration are still required.

## Protocol and identities

`fixture.mjs` adapts `examples/vanilla-ts/graphforge-live.mjs`; `run.mjs`
adapts the historical review-repair runner. The raw live input is packed UUID
identity planes for **1,000 nodes / 2,000 edges**, ring plus deterministic
chord `(i*7+3)%n` (self-chord goes to `(i+2)%n`), exactly as the historical
`scripts/bench_cose_progressive_node.mjs` rung. Ascending UUIDs preserve source
order. Before timing a job, the fixture compares the canonical composed
source/target plane hashes to that generator. This verification composition
is included in cold fixture startup; the timed live call still receives raw
input and composes again in its production bridge Worker. The input XYGQ hash
is `b187c90663d6ee4a4f4228f489e4cb88c7f9485d83c834d9cf62587469f62c76`.

CoSE, seed 7, Rust-seeded positions, default CoSE options. The explicit
401-tick cap preserves the historical rung's `1+40*10`; it is **not** the live
API's default 300 cap. Chunk size is omitted (actual live default 10), as is
wall limit (default 30,000 ms). No authored positions, pins, preset layout at
ingress, masks, hierarchy overrides or LOD overrides. Width 720, height 480,
legend disabled match the old live fixture. Rust owns force, preset checkpoint
packing, topology/LOD/style decisions and offset-f32 painter geometry; no
Python, TypeScript layout or new WASM controller participates. `preset` in
output graph metadata describes existing checkpoint packing, not an alternate
layout input. Both retained payloads are Direct: 1,000 nodes / 2,000 edges.

The exact supplied parent native artifact was **reused**, copied locally before
loading, with SHA-256
`3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6`, ABI 399.
It was not rebuilt or taken from a #36 candidate. Root `npm ci`, host
`npm ci --prefix packages/xy-node` and `node js/build.mjs` built the painter in
this isolated checkout. Their logs are retained; lockfiles are unchanged.
Standalone client SHA-256:
`e8c3b4aeab6c28b80f67e35ba56003eb1a99704527f58d262acef0f876014dbf`.
The ESM client, Node/Chromium executables and all timed producer/harness sources
are hashed in `raw/unheld/result.json`. `identities.json` records affected
source trees and historical receipt preservation; `receipt-files.json` binds
all archived files except itself.

No WASM artifact was loaded, rebuilt, promoted or package-qualified. The supplied
parent module sizes (1,922,723 raw / 783,181 gzip bytes) and limits (1,878 / 765
KiB) are unchanged, **not remeasured by this task**. No compiler, arena, profile,
optimizer, export, guard or module-gate changes were made.

## Actual browser and results

Final capture: `raw/unheld/`, with Node **22.23.4**, Playwright **1.61.1** and
cached Chromium **156.0.8078.4**, Linux x64, Intel Xeon E3-1270 v6, 8 logical
CPUs, about 31 GiB RAM, shared host. Software graphics: ANGLE / Vulkan
SwiftShader. Raw environment, executable paths/hashes and load average are in
the JSON. This is a local source/native pairing, not a packaged-platform or
release qualification. Initial native/browser state is fresh per process/job;
OS disk caches and system contention are uncontrolled.

The browser uses the **normal shared WebGL2 painter and visible Canvas2D
presentation**, with no forced draw or renderer override. Two requestAnimationFrame
callbacks precede readback of the visible canvas. Pixel evidence is from
`getImageData`, and the initial/final PNGs are that same canvas. Existing client
coordinate helpers locate a candidate; `_pickAt` must return an actual GPU hit
on the node trace. No mapper or hover policy was changed.

One instrumented unheld run observed:

- Cold Node fixture readiness **166.79 ms**; cold Chromium launch **134.72 ms**;
  context plus navigation/readiness **693.92 ms**. Navigation uses Playwright
  `networkidle`, which includes a harness readiness wait. These are separate
  runner-clock observations, not a startup optimization claim.
- First host payload/checkpoint callback **302.61 ms** after Node `/start`.
  This is **checkpoint arrival**, never called paint.
- First visible painted-frame observation **887.90 ms** after browser
  `beginGraph`; first GPU node-hit readiness **966.80 ms** on that browser
  clock. Parent first-frame observation was **1,980.19 ms** after spawning the
  cold Node process, including sequential browser/navigation setup and polling.
  Paint times are observation upper bounds after two rAFs/readback, not display
  scanout timestamps or browser PerformancePaintTiming entries.
- Actual presentations were **step 1 initial** and **step 401 complete**.
  Colored visible pixels: **187,859 / 166,035** on 644×428 canvases. Each raw
  painter buffer is **333,004 bytes**; full 1k-source f64 coordinates changed
  between those presentations. Specs, buffers, source x/y and UUIDs are retained
  for **every presented frame**, not unpresented native checkpoints.
- The sole unheld painted-frame interval was **570.00 ms**. Intermediate
  checkpoints coalesced away while the initial frame was rendered/probed.
  There is **no observed update-phase presentation and no sustained cadence
  estimate**. This interval cannot stand in for ten-tick native cadence.
- A real Playwright pointer on the **settled final frame**, outside cadence,
  agreed with the GPU-probed trace/index and host UUID equaled tooltip row ID.
  Pointer command to observed UUID response was **46.14 ms**, including driver
  round trips; pan command sequence to observed view change was **787.67 ms**,
  including five mouse-move steps and observation overhead. The browser's click
  handler separately records fetch-to-UUID response time. These are not bare
  event-dispatch or renderer-only latency measurements.
- Node's 5 ms heartbeat during the live run produced **301** samples, p95
  overshoot **0.27 ms**, maximum **1.45 ms**. Browser main-thread heartbeat
  was not measured. Host completion/Worker settlement was **1,547.06 ms**,
  within the existing 30 s wall timeout. No normative numerical first-paint,
  presentation-cadence or pointer/pan threshold is specified for this path;
  this task invents none and claims no performance-budget pass.

Automatic browser ACKs happen after frame readback, GPU probing and initial/final
PNG encoding. There are **no deliberate holds** in this run, but instrumentation
and source/payload retention are included overhead. In particular, GPU readiness
probing and PNG encoding postpone acceptance. Frame intervals are not passive
production telemetry. Full source snapshots and paint buffers are retained by
the evidence server until exit: the reported process peak RSS (~**172.01 MiB**)
is instrumented process high-water, not production steady state or complete
CPU/VRAM accounting. Browser/driver memory and exact destructor execution are
not measured.

## Separate held inspection and negative checks

`inspection.mjs` starts a fresh identical 1k process and deliberately intercepts
its HTTP ACKs with Playwright. `raw/held/` is **inspection/mutation evidence**;
none of its intervals qualifies unheld presentation cadence or unheld initial
trusted response. With initial ACK held:

- A trusted pointer click on step 1 resolves the actual GPU-hit render row and
  matching source UUID. Trusted pointerdown/up records are consumed once by
  the custom click. A separate synthetic custom click after a real pointer in
  the unheld run cannot inherit that sequence's trust.
- A wrong-step ACK returns HTTP 409. The checkpoint count remains one, with
  no accepted event while inspection/pan proceeds. Releasing the actual ACK
  then presents the complete frame.
- Initial pan changes the viewport. Final replacement's recorded previous
  view equals that panned view, but its new view equals the final payload's
  authored ranges. The old replacement-camera reset is therefore **observed,
  not repaired**. Screenshots retain panned initial and reset final pages.

The unheld runner additionally rejects a wrong-job ACK and pick request. Its
separate native cancellation job cancels after the first callback, observes
`GF_LAYOUT_ABORTED`, then terminal `GF_LAYOUT_DISPOSED` after disposal. The
browser view's canvases are removed on disposal. Both main and nested Workers
are observed through read-only Node `async_hooks` WORKER init/destroy events
with thread IDs and process monotonic nanoseconds; every observed resource is
balanced. Public promise settlement follows the existing production contract.
Resource destruction observations are not instrumentation of Rust force
`finally`/destructors or proof of emergency-termination behavior. Archived
`fixture.log` retains the raw audit events.

Both initial instrumentation captures remain unchanged under
`raw/instrumentation-v1-unheld/` and `raw/instrumentation-v1-held/`, with their
own source hashes. They used a sticky pointer-trust observation. The final
captures above use consumed pointerdown/up records and the real synthetic-event
negative check. Do not use v1 as proof against stale trusted-input attribution.
`run.log` / `inspection.log` refer to v1; `run-v2.log` / `inspection-v2.log`
refer to the final captures. This is instrumentation correction, not a production
fix, repeatability claim or performance optimization experiment.

## Reproduce and verify

Use the repository-documented Playwright workflow, explicit local Chromium and
project uv. This task did not need a browser profile, network CDN, or standalone
WASM assets. All recorded page requests stayed on the local fixture origin.
Paths below are the actual tools used here; another environment must record
its own identities and observations rather than claim to reproduce these bytes.

```bash
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:$PATH
uv sync --group dev
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
# Reuse ONLY the supplied parent native bytes after verifying this hash:
mkdir -p target/release
cp /home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/release/libxyg_core.so target/release/libxyg_core.so
sha256sum target/release/libxyg_core.so
# expected: 3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
node spec/performance/graph-node-first-paint-1k-2026-11-04/run.mjs
node spec/performance/graph-node-first-paint-1k-2026-11-04/inspection.mjs
node --test spec/performance/graph-node-first-paint-1k-2026-11-04/protocol.test.mjs spec/performance/graph-node-first-paint-1k-2026-11-04/verify-receipt.test.mjs
```

If the supplied native artifact is unavailable, build **this exact source** with
`cargo build --release -p xyg-core` and record that build and its actual hash in
a **new** receipt. Do not relabel a rebuilt artifact as the reused artifact.
Runners default to fresh `target/task-tmp/` timestamped directories and refuse
an existing output directory; `XYG_NODE_PAINT_OUTPUT` and
`XYG_NODE_INSPECTION_OUTPUT` can select new directories. Reruns never write to
archived raw evidence. Receipt tests validate the archived capture, not a new
run unless new evidence is explicitly archived separately.

Focused verification: **8 tests pass**, including actual automatic ACK order,
matching raw native geometry/full-source hashes, held invalid-ACK behavior,
trusted render-row/UUID identity, synthetic-event rejection, camera reset and
balanced observed worker resources. Negative protocol cases reject checkpoint
substitution, zero pixels, stale job/step identity, missing GPU readiness and
acceptance before paint. No full Python suite was repeated. Required full-tree
hook/Ruff logs are retained separately after their actual execution.

## Exact remaining acceptance boundaries

This is **partial 1k rendered evidence**. Remaining #35 criteria include:

- Rendered first-paint/interactivity across the rest of the existing
  10k/100k/1M ladder and public hosts. No larger rung was run here.
- Actual unheld initial trusted pointer/pan response and sustained progress
  presentations/cadence. This run's first frame has real pixels/GPU readiness;
  trusted initial interaction was deliberately held and is not substituted.
- Public browser default progressive scheduling/attachment. Retained Rust
  `load.progressive` and opcode 15 are mechanisms; the current retained WASM
  attachment does not expose a force-continuation API. This task adds none.
- Python widget/notebook progressive delivery, rerender/dispose cancellation and
  public-host scheduling (#1015). A private notebook byte boundary or standalone
  controller does not prove those flows. No Python integration claim is made.
- Explicit clarification of literal async `composeGraphForge` issue wording:
  the adopted Node contract intentionally keeps metadata/static/batch
  composition synchronous, with `graphforgeWebviewPayload` live by default in
  bridge/force Workers. This proof does not silently reinterpret that criterion.

Existing shared explicit S5b attachments are separate from this replacement
consumer and do not cure these progressive-scheduler acceptance gaps. No #36
picked-target-size repair, hover contract or mapper was touched. No competitor
comparison or scale-performance win is claimed; this receipt provides no new
Matplotlib/Seaborn/Plotly/Bokeh/Altair/Datashader/HoloViews ranking. Historical
receipts remain immutable. `host-parity.md` and the dual-host force row are
corrected only where their old “default Node async composition remains open”
statement contradicted the adopted live API; literal wording and other host
criteria remain open. Parent owns independent final review, integration, PRs,
GitHub issue disposition and all publishing.
