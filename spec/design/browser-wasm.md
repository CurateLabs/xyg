# Direct-browser Rust/WASM boundary

**Status:** bounded lifecycle, canonical Scene paint, and packed typed-column
compile (`XYCC`) for scatter/polyline/rect/band, plus transferable series
descriptors (`XYTS`) whose record expansion and defaults run in Rust.
This is **not** yet a complete direct-browser chart host. Tracking:
[#59](https://github.com/CurateLabs/xyg/issues/59).
Canonical scene dependency: [Scene IR](scene-ir.md).

## Runtime taxonomy

Direct-browser WASM is the safe `xyg-engine` compiled for
`wasm32-unknown-unknown` and hosted in a static module Worker. It is distinct
from both:

- the native Python/Node C ABI (`xyg-core`); and
- the Pyodide/PyEmscripten Python wheel, which runs CPython in the browser.

There is no separate “WASM implementation.” Rust owns engine decisions, the
Worker adapter owns memory/lifecycle/status transport, and the existing
TypeScript/WebGL client retains paint, pick, gestures, accessibility, and DOM
chrome.

## Foundation artifacts

| Artifact | Role |
| --- | --- |
| `crates/xyg-wasm` | Minimal raw-export adapter over `xyg-engine`; no `wasm-bindgen`, browser framework, renderer, or host algorithm |
| `spec/wasm/abi.json` | Versioned raw-export/status manifest |
| `js/src/wasm_abi_generated.ts` | Generated export validator and typed declarations |
| `js/src/wasm_worker.ts` | Static strict-CSP module Worker |
| `js/src/47_wasm.ts` | Main-thread lifecycle proxy; requires explicit worker and WASM assets |
| `js/src/48_wasm_scene.ts` | Thin display-list adapter into the existing WebGL painter |
| `js/src/49_wasm_columns.ts` | Packed `XYCC` typed-column framing; no Scene policy in TypeScript |
| `js/src/49_wasm_chart.ts` | Bounded O(series) validation/framing and lifecycle handle; no record expansion or mark defaults |
| `dist/xyg-wasm.wasm` | Separately built direct-browser engine adapter; never copied into the Python static tree |

The WASM adapter disables `xyg-engine`'s default `raster` feature. Native
SVG/PNG/PDF export remains a native-host concern; browser output reuses the
shared painter. The raw module must request no ambient WebAssembly imports.

## Memory and copy contract

An ordinary JavaScript `ArrayBuffer` cannot alias wasm32 linear memory. The
default contract is therefore:

1. Canonical typed source stays in JavaScript-owned buffers.
2. Moving a buffer to the Worker uses `postMessage` transfer by default, so it
   does not clone the payload between main thread and Worker.
   The high-level chart handle is intentionally safer: its default
   `dataOwnership: "preserve"` path uses structured cloning, copying caller
   buffers into the Worker without detaching them. This differs from the
   low-level API's default transfer; `dataOwnership: "transfer"` explicitly
   selects that zero-clone, detaching handoff for the high-level handle.
3. The Worker copies only the bounded operation slice into a reusable WASM
   staging arena. The Rust adapter enforces the per-instance logical bound and
   a 384 MiB compile-time ceiling.
4. Rust validates or computes from that slice. Outputs remain bounded scene/LOD
   records and are copied or transferred back as their contracts require.
5. The arena's logical length returns to zero. wasm32 pages may remain reserved
   because WebAssembly memory cannot shrink; the budget prevents unbounded
   ratcheting.

Future full-data algorithms must stream bounded chunks through the arena or use
an explicitly measured alternative. They must not claim zero-copy JS→WASM
aliasing. `SharedArrayBuffer` is an optional future optimization that requires
an isolated context; this foundation rejects it explicitly rather than
silently cloning or changing ownership.

The foundation diagnostics report every non-empty JS→WASM staging copy at the
successful arena-resize boundary, before validation can reject a stale,
cancelled, malformed, or incompatible request. They include copy count,
split-u64 copied bytes, current logical arena length, scene record/style counts,
arena high-water bytes, current WASM linear-memory bytes (also its high-water
because WebAssembly memory cannot shrink), ABI version, and scene version.
The Worker normalizes semantically unsigned wasm32 results before exposing
them, so a set high bit in either copied-byte half remains a non-negative u32.
They never log user values.
`XYTS` is the canonical authoring/compile ingress, not the live §29 paint wire
and not an `XYBF` transport envelope. Its column attachments are exact raw
`Float64Array` source values, matching the CPU-side f64 authority. The main
thread only validates bounded descriptor shape and transfers (or, under the
explicit preserve policy, clones) those source buffers to the Worker. The
Worker performs one bounded byte copy into WASM linear memory. Rust then
validates, expands mark records/defaults, and is the sole layer that narrows
canonical f64 geometry to offset painter f32/u8 output. TypeScript never scans,
converts, or re-encodes per-record values. The resulting `XYPB` painter buffer
is the live WebGL-consumed format governed by §29's raw-f32/u8 rule.
Painter output is attempt-local instance state. Arena resize, validation,
cancellation, the start of another prepare, any failed prepare, and disposal
clear it; the Worker copies a successful output into one transferable
ArrayBuffer before resetting the arena. A prior success can therefore never be
observed after a later failure or non-paint operation.
`prepareScene` clears the staging arena after a successful `SceneDocument`
decode and before painter lowering, so staging bytes and painter output never
both retain the per-instance byte budget at once. The combined live staging
plus painter buffers must always stay within `max_arena_bytes`.

## Version and scene contract

`WASM_ABI_VERSION` is 4 for Scene paint, packed typed-column compile, and
transferable `XYTS` series descriptors. `SCENE_VERSION` remains independently versioned
at 8. `scripts/gen_wasm_abi.py --check` rejects parameter/result drift among
the manifest, raw Rust exports, generated TypeScript declarations, and the Rust
scene constant. `js/package-wasm.mjs` parses the compiled module's type,
function, and export sections and rejects artifact-level signature drift.

`validateScene` remains the allocation-free validation seam. `prepareScene`
validates the same bytes and asks `xyg-engine::SceneDocument` to lower them to
bounded painter-ready f32/u32 columns plus a fixed trace descriptor table.
`renderWasmScene` creates only descriptor-sized views over that transferred
buffer and hydrates the existing WebGL painter. The exported lower-level
`hydrateWasmPainter` accepts only already-prepared painter output and applies
the same complete fail-closed validation before allocating browser paint state.
TypeScript does not scan Scene
records, map data, decide clipping or grouping, narrow f64 geometry, copy
columns, or run a fallback algorithm. Stable u64 IDs remain split lo/hi binary
columns and are exposed by `view.sceneStableId(traceIndex, rowIndex)`.

Painter contract v6 begins with `XYPB`, independent painter version 6, canonical
Scene v9 (`SCENE_VERSION = 9`), a 288-byte header, 64-byte trace descriptors, viewport/plot f32
bounds, bounded trace and tick counts, and absolute offsets to the tick and
UTF-8 label tables. Header bytes 64–263 are the exact validated Scene v9
chrome style input (backgrounds plus x/y side, masks, paints, and major/minor
geometry); bytes 264–275 carry the bounded figure-title/x-label/y-label UTF-8
lengths and bytes 276–279 are reserved zeros. The shared string table stores
those three authored texts before formatted tick labels. Header bytes 280–283
carry the exact appended legend byte length and 284–287 are reserved zeros; the
validated `XYLG` record follows tick-label strings and is followed by an `XYRG`
resolved-geometry trailer. Rust writes the frame bounds, title and row baselines,
and literal line/marker/rectangle swatch geometry. TypeScript validates and
projects those coordinates; it does not position, wrap, scroll, or fit the
authored legend. Legends whose intrinsic width or height exceeds the plot fail
closed before encoding so SVG, raster, and browser consumers share one policy.
Each trace descriptor identifies scatter/polyline/rect,
style, count, and absolute packed-column offsets. Rust derives default numeric
ticks or consumes bounded authored major/minor positions, formats major labels,
maps positions to painter coordinates, and emits fixed 16-byte records whose
last u32 distinguishes major from minor. TypeScript validates the three chrome
texts and supplies them to the existing title, axis-title, and accessibility
surfaces. Figure-title paint is the authored label RGBA and its size is the
authored label font size plus two pixels, matching Rust SVG and raster output.
It creates descriptor-sized views and hands
those painter-ready values to the existing canvas/DOM chrome surfaces; it does
not generate ticks, format labels, or choose layout. Reserved fields, exact
offsets, finite geometry, known kinds and symbols, valid UTF-8, and exact final
length fail closed before hydration.

The descriptor graph has an independent Rust-enforced ceiling of 1,024 trace
runs, recorded as `painter_max_traces` in the generated WASM contract. A valid
Scene can alternate stable IDs, styles, or symbols on every record; without
this ceiling its compact input could expand into O(records) `ChartView` and GL
objects on the main thread. Rust stops while discovering run 1,025 and returns
the stable `RESOURCE_LIMIT` diagnostic before allocating or transferring a
descriptor table. TypeScript repeats the generated ceiling as defense in depth.
Callers may reduce fragmentation or split work into explicitly managed views;
the browser never silently merges runs because that would change line breaks,
styles, symbols, or stable identity.

This is the public direct-browser entry for the stable Scene v9
subset with canonical solid chart/plot backgrounds and authored Cartesian grid,
spine, major/minor tick, side, visibility, label paint, and bounded primary
static legends. `frameWasmChart`
performs bounded descriptor validation and transfers exact full-buffer
`Float64Array` columns as canonical compile ingress. Rust expands
scatter/line/bar/area and performs the only f64-to-offset-f32 lowering,
assigns or preserves stable identities, and owns default diameter, line width,
bar width/baseline, area baseline, colors, domains, and margins. The default
bar width is 80% of the minimum positive spacing between sorted x values. A
singleton or all-coincident series uses 80% of the absolute authored x-domain
span (including reversed domains); invalid or degenerate fallback domains fail
closed rather than inventing data-space geometry. The returned
`XygWasmChartHandle` owns update cancellation, diagnostics, painter teardown,
and its own painter resources. Caller arrays and the caller-supplied Worker are
preserved by default. `dataOwnership: "transfer"` explicitly opts into buffer
detachment, while `workerOwnership: "own"` explicitly delegates Worker disposal
to the handle. Aggregate
production, density replacement, and cross-host conformance remain later #59
slices. The two version numbers are
checked independently so rebasing the axis/chrome work cannot silently widen
this consumer.

## Lifecycle and failure model

- Instance handles carry a generation and fail closed after disposal; stale
  handles cannot access a reused slot.
- Worker initialization enters an exclusive `initializing` state before its
  first asynchronous module-loading boundary. Concurrent or repeated init
  messages fail closed. Disposal may win while module loading or instantiation
  is pending; every post-await continuation rechecks disposal, cleans up any
  attempt-local Rust handle, and never publishes a late ready response.
- At most 64 instances exist per module. Each instance has an explicit arena
  budget no greater than 384 MiB, and the sum of declared budgets for live
  instances in one module cannot exceed that same 384 MiB ceiling. Before any
  O(N) expansion, `XYTS` computes a
  conservative total logical peak covering input retention, expansion vectors,
  repacking, canonical Scene output, and allocator slack; requests above the
  instance budget fail with `RESOURCE_LIMIT` and clear prior output. Starting
  new staging drops the prior output allocation, and each validate, prepare, or
  compile call consumes staging up front. Success and every error exit
  (including stale, cancelled, bad-range, malformed, and bounded rejection)
  therefore drop the staging allocation rather than retaining either `Vec`
  capacity across operations; a large rejected request cannot inflate a later
  small request's unaccounted resident baseline.
- Sequence zero is reserved. Lower/repeated sequences fail as stale. Cancelled
  sequences fail with a stable cancelled status. The Worker defers queued work
  one task turn so already-posted cancellation can suppress it; future long
  Rust operations must add cooperative checkpoints.
- Traps invalidate and dispose the Worker-side Rust instance. Callers must
  create a fresh Worker rather than continue with uncertain engine state.
- Invalid sources fail before Worker allocation. Initialization-send failures
  and unreadable Worker messages terminate immediately; disposal waits at most
  one second for cooperative cleanup before terminating the Worker.
- Unsupported operations, incompatible versions, malformed scenes, invalid
  ranges, and resource bounds return stable error codes. There is no silent
  JavaScript algorithm or remote-service fallback.

## CSP, offline, and asset loading

Both assets are explicit:

```js
const engine = createXygWasmWorker({
  workerUrl: new URL("./wasm-worker.js", import.meta.url),
  wasm: compiledModule, // or explicit local URL / bytes
});
const view = await renderWasmScene({
  el: document.querySelector("#chart"),
  scene: canonicalSceneBytes,
  worker: engine,
});
// Or transferable typed series (Rust owns expansion/defaults/domain/Scene):
const chartView = await renderWasmChart({
  el: document.querySelector("#chart"),
  worker: engine,
  chart: {
    width: 640,
    height: 400,
    series: [{ kind: "scatter", x: xs, y: ys }],
  },
});
```

The library never uses `Blob`, `eval`, a CDN, default URL, or path probing.
URL-based WASM loading performs one non-redirecting fetch of the exact
caller-provided URL; redirects fail initialization rather than changing the
asset authority. `Module`/bytes loading performs no WASM fetch. A strict policy needs
`script-src 'self' 'wasm-unsafe-eval'`, `worker-src 'self'`, and
`connect-src 'self'` when a local WASM URL is used. `wasm-unsafe-eval` permits
WebAssembly compilation; it does not permit JavaScript `eval`.

`scripts/wasm_foundation_smoke.mjs` serves an allowlisted local-only asset set
under that CSP and tests explicit Module/bytes/URL loading, transfer and copy
diagnostics, lifecycle, cancellation, stale sequence, malformed module/scene,
resource bounds, redirect rejection, a real runtime trap, public Scene paint,
existing-painter hydration, and disposal. It
also verifies unsigned split-u64 accounting across the `0x80000000` boundary
and that an invalid source is rejected before a Worker is allocated.

## Build and evidence

The repository pins Rust 1.96.0 and CI installs the
`wasm32-unknown-unknown` target explicitly:

```bash
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs
node scripts/wasm_foundation_smoke.mjs
node benchmarks/bench_wasm_scene.mjs
```

The opt-in Chromium benchmark reports 10k/100k/1M mixed scatter/line/rect
worker preparation, hydration/upload, two-frame first paint, Scene/painter
bytes, and JS heap delta when Chromium exposes it. It asserts three grouped
traces and stable-ID survival. Results are environmental measurements, not a
committed win claim. The hosted Rust benchmark isolates the same conversion at
those three sizes. This slice makes no startup, throughput, memory, or
bundle-size win claim. Those budgets and comparisons
must be established through the repository's hosted CodSpeed workflow before
Issue `#59` can close; raw local timings are not performance evidence.

## Remaining #59 work

- aggregate production paths beyond direct Scene records;
- native Python/Node/WASM/Pyodide conformance fixtures;
- cooperative cancellation inside long Rust operations;
- small-through-massive CodSpeed and browser budget evidence; and
- replacement (not expansion) of `46_worker.ts` only after WASM covers its
  density contract without regression.

Public chart ergonomics (`frameWasmChart` / `renderWasmChart`) transfer exact
typed columns without main-thread record expansion. `FLAG_AUTO_DOMAIN` keeps
domain scans in Rust inside the Worker.
