# Density startup context-recovery oracle

Source parent: `8affefdd9547c125d70b83771f7866e3eaeb68a2`.

The foundation fixture could reject a supported startup recovery before the
shared renderer's first 250 ms recovery attempt. It allowed eight zero-delay
tasks, then reported `glLost:true, contextLost:true`. It also captured texture
identity before that recovery, although replacement necessarily creates new
WebGL objects. This continuation changes the fixture and its reporting, not
runtime recovery, admission, shaders, density algorithms, packaging or caps.

Each capture now waits for an already-lost context's actual restoration event
under the existing 60-second foundation deadline, then requires a completed
paint. It reads pixels once; unexpected blank/stale pixels still fail. The
retention baseline starts at the first completed presentation. The original
three no-refinement scenarios retain their grid, texture, upload, pixel,
viewport, Worker, event and teardown assertions. A fourth scenario explicitly
loses the startup context and additionally requires observed restoration,
replacement of the lost context, and a successful complete paint. Both ESM and
IIFE run all four cases, producing eight captures.

## Evidence and limits

`checks.json` binds commands/results, archived raw diagnostics, reports and
captures. The controlled old readiness path reproduces the presentation
failure. Waiting for restoration alone reaches a paint but fails its obsolete
texture-identity assertion; the corrected baseline preserves subsequent
navigation assertions. A final negative removes the wait; another removes the
forced loss. Both fail. Explicitly injected loss is not evidence for the cause
of an earlier unrequested loss.

The diagnostic runner intercepts context creation, loss/restore events and
explicit extension calls without changing their arguments, records Chromium
GPU information and console output, and otherwise uses the original launch
configuration. One initial diagnostic run failed without saving its event
record because the private runner's finalizer patch missed its target. That
failure remains preserved. A corrected ordinary run passed; its explicit loss
calls came from normal chart disposal. This does not establish a browser,
driver, product or instrumentation cause for the historical startup losses.
No SwiftShader flag, retry-for-green rule or runtime recovery delay was added.

The focused ESM/IIFE command passes all eight cases. Ten density lifecycle
source-contract tests pass. The broader foundation attempt passes its initial
page, graph scheduling/keyboard, retained temporal and seven frozen-graph
journeys, then fails the unchanged aggregate harness during initial attachment
with `xy: graph GPU context unavailable`. Its overall exit is **1**, not a
full-green result. The page-level report's `passed` field covers only that
page and does not supersede the later child failure. The aggregate failure is
preserved without a retry or claimed repair; it keeps broad qualification open.

Native405/WASM38, all 551 native declarations, 68 WASM functions, the 324
compiled inputs, nine runtime artifacts and six Python static copies remain
parent-identical. No rebuild or new timing claim is needed for this test-only
change. Prior performance, notebook and host evidence keeps its original
scope. Historical reports are unchanged.

The live milestone acceptance audit is retained as read-only evidence. It
credits the existing 72 GB chunked source proof and five automatic geographic
views, but finds no whole issue closure-ready. Remaining work includes reliable
large-graph notebook qualification, paged/cancellable massive-data filtering
with global resource admission, and complete temporal interaction/table/export
flows. This correction does not establish reliability, shipping, hosted CI,
merge-queue readiness, competitor wins or milestones 4–7 completion.

## Reproduction

Use the matching parent-verified artifacts, Node 22.23.4, explicit supplied
Chromium and disk-backed `TMPDIR=/var/tmp`:

```bash
XYG_WASM_FOUNDATION_ONLY=density-no-refinement \
XYG_WASM_FOUNDATION_REPORT=/absolute/path/density.json \
node scripts/wasm_foundation_smoke.mjs
```

Omit the focused selector for the complete source foundation gate; provide
`XYG_NATIVE_LIB` and checkout `PYTHONPATH` for its native comparisons. Failed
attempts and setup errors receive no pass credit. Exact invocations and result
boundaries are recorded in the machine-readable receipt.
