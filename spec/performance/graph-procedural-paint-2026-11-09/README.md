# Retained procedural node binding and offline fixture encoding

Parent: `770cc8f4fa6f0c8344fc04737608601256f16415`. This is a bounded
presentation change, not milestone or release acceptance. Rust, native/WASM
ABIs, module bytes, defaults, arenas, LOD, scheduler deadlines and visual
assertions remain unchanged. Historical evidence is preserved.

## Change and ownership

Eligible frame-free retained publications draw every node with six procedural
vertices, preserving the reference strip's two triangles and node order.
Coordinates come from the original offset-f32 bytes in two RGBA8UI textures;
there is no CPU vertex expansion, numeric narrowing or derived geometry.
Both input bindings share geometry, style decoding and the unchanged fragment
shader. Frame-bearing publications and counts beyond one GLsizei draw retain
the reference instanced binding. No culling or tier decision moves to the host.

Normal and focus draws share coordinate textures. Their padded allocation
replaces repeated coordinate buffers; the same object-identity ledger admits
storage before WebGL allocation. Both programs and partial objects follow
whole-chart eviction, context-loss and disposal. An empty publication remains
resident through its texture storage even when it needs no shader program;
repeated retain callbacks must not schedule new paint or storage churn. The
same final regression fails when only the new storage guard is removed.
GLHost resets samplers and
textures on units 0–4 before every pass. The source foundation now invokes the
raw-buffer probe, including all six glyphs, focus, translucent halo, dirty
neighbor bindings, exact full-GL-RGBA reference/procedural equality, failed
coordinate upload with accepted-picture preservation, retry, context restore
and final owner removal. An independent driver-facing allocation oracle agrees
with the ledger at each binding, failed-upload retry, eviction/readmission and
context-restoration checkpoint; teardown leaves no tracked allocations. This
is logical requested storage, not opaque physical VRAM or transient driver peaks.
Existing packaged journeys remain substantive.

The separate strict-CSP single-file PNG fixture now declares UTF-8 before its
hash-protected script. The existing 30-second wait is unchanged. Failure
reports include effective encoding, readiness, client/inline presence, CSP
violations and console/page errors. The actual generated file is checked by
Python's HTML parser; CSP/network restrictions and artifact assertions remain.

## CodSpeed workload and results

`benchmarks/bench_graph_retained_repaint.mjs` uses a public authored-position
Direct graph: fresh browser/Worker, first paint, five accepted identical
refreshes, six complete RGBA SHA-256 checks, count/membership checks and teardown.
All 100,000 source nodes remain rendered. It is whole-command walltime, not
steady-frame FPS or a primary/peer scheduling measurement.

CodSpeed CLI 5.6.3 / exec-harness 1.4.1, Node 22.23.4, Chromium
156.0.8078.4 with SwiftShader, Linux x86_64; three rounds per successful arm.
Commands from this work ran serially; this shared machine was not reserved as
exclusive hardware. Raw round statistics and sampled profiles are retained.
The optional harness report retains the last round; all rounds internally
check six images. Do not imply that each round's report was independently
archived.

| Comparison | Baseline best | Candidate best | CodSpeed disposition |
|---|---:|---:|---|
| Initial paired 100k | 16.87 s | 7.90 s | Improvement |
| Repeated paired 100k | 16.90 s | 7.92 s | Improvement |
| Pinned-harness prototype | 16.18 s | 7.86 s | Improvement |
| Current client, including empty residency guard | 16.18 s | 8.00 s | Improvement |

The current-client [comparison](https://app.codspeed.io/CurateLabs/xyg/runs/compare/6af245c450449d12faa69bb1..6af24bf290d2f7bffd9c553a)
uses the same pinned harness and baseline and also preserves every count and
framebuffer digest. Earlier candidate arms precede the empty-residency follow-up.

The exact harness (including console diagnostics) was source-hashed
before both arms and remained unchanged; its
[paired result](https://app.codspeed.io/CurateLabs/xyg/runs/compare/6af245c450449d12faa69bb1..6af2461a50449d12faa69bc8)
also preserves every count and framebuffer digest.

The earlier repeated comparison is
[6af23f47 → 6af23f7d](https://app.codspeed.io/CurateLabs/xyg/runs/compare/6af23f47cdd183be154857f9..6af23f7dcdd183be154857fc).
Both arms use the same harness, Worker/WASM and source; the baseline serves the
immutable archived ESM entry. All six framebuffer SHA-256 values and complete
count/tier/membership reports agree. The original
[paired comparison](https://app.codspeed.io/CurateLabs/xyg/runs/compare/6af2336cc53e4eae00d3bef4..6af23bcfcdd183be154857a3)
agrees. The figures are CodSpeed's best-round metric; complete means, spread
and profiles remain inspectable. This is no hardware-GPU, competitor, universal
scale or whole-library performance claim.

Profiles place substantial work in SwiftShader/JIT code. The repeat profiler
reported 8,127 dropped baseline events and 1,051 dropped candidate events;
precise shader-function cost attribution is not established. Walltime results
retain their complete round statistics. A separately labeled
one-pixel scissor diagnostic retained counts/submissions but changed visible
work, so it is not equivalent output and receives no product-win credit.
Early focus rejection, alternate texture addressing, transparent-halo skipping
and instanced style attributes did not establish a useful improvement and were
reverted. Their experiments and failures remain recorded.

The attempted 1k timing matrix is **not qualified**. Both archived baseline and
candidate encountered intermittent `graph GPU context unavailable`; the latter
reported `CONTEXT_LOST_WEBGL` after two successful rounds. One baseline rerun
passed. No all-green small-scale comparison or reliability repair is claimed.
The separate unchanged default-1k functional journeys pass in foundation.

## Fresh functional evidence

- Complete source foundation: preserved camera/keyboard scheduling, retained
  temporal, six controller-bound families, seven shape freezes, shared native/
  Worker Scene/XYPB/SVG/HTML/PNG, offline exports, aggregate and CSS checks.
- Two unchanged public 100k-plus-default-1k-peer journeys: trusted interaction,
  camera, progress, cancellation and disposal. Complete browser/native/shipping
  WASM replies agree for both captures.
- Unchanged public 1M-plus-default-1k-peer journey and complete reply replay.
- Normal and mixed-family 32-chart allocation/admission/selection/keyboard/
  context-restoration journeys; zero remaining tracked allocations.
- Actual Python 3.11.17 and Chrome149: all 36 frozen tests, including strict-CSP
  Blob Worker PNG and unchanged existing screenshot/tampering/pixel checks.
- Shader/reset, source provenance/real Git CRLF, ABI/assets/workflow, related
  host checks and mandatory hooks: see append-only command evidence in
  `checks.json` for exact exits and qualified totals.

The original hosted770 floor run remains **FAILED: 1 failed, 8468 passed,
365 skipped, 84 xfailed**. Its Blob Worker completion timed out; main and
foundation succeeded. A controlled Windows-1252 decode of the old unspecified-
charset file blocks its UTF-8-hashed script; automatic and explicit UTF-8 pass.
This proves a fixture weakness, **not** the exact cause of that hosted timeout.
Only fresh new-head hosted execution can qualify the correction there.

The raw probe initially failed because it used the historical v1 host registry;
it now accesses the current v2 registry and preserves all original assertions.
Initial shader-test extraction/lint mistakes and the initial CodSpeed PATH/
setup failures remain failed attempts. Passing corrections do not rewrite them.
No new native/Rust/WASM build or full Python suite is claimed in this receipt.
All 324 compiled inputs and reused artifacts are checked against the parent.
Generated client copies are rebuilt and separately pinned.

## Reproduction

Use the pinned Node22, supplied browser, explicit native library and disk
`TMPDIR=/var/tmp`. Build the client with `node js/build.mjs`. Run:

```bash
node scripts/graph_session_gpu_paint_smoke.mjs
node scripts/wasm_foundation_smoke.mjs
node scripts/dashboard_gpu_smoke.mjs
XYG_GRAPH_SCALE=100000 XYG_GRAPH_SESSION_REPORT=/absolute/report.json \
  node scripts/graph_session_public_scale_smoke.mjs
node scripts/graph_session_public_scale_replay.mjs /absolute/report.json
uv run --no-sync pytest -q tests/test_temporal_graph_frozen.py
```

For CodSpeed use the runbook in `benchmarks/README.md`, and keep the exact
archived baseline client override, runtime pins and shared harness for both arms.
The retained command/evidence manifests identify actual paths and environments.

## Remaining acceptance

Final independent exact-diff review, current-main freshness, final-head hosted
checks and merge queue remain required. Existing startup/Worker/100k watchdog
failures remain authentic and unresolved; these passes do not establish their
cause or universal contention tolerance. M4–7 and their issues remain OPEN:
broader scale/hosts/platforms, complete accessibility/export behavior, global
CPU/source/WASM/driver memory, hardware and competitor qualification remain.
