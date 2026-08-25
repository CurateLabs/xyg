# Direct-browser Rust/WASM boundary

## Tier-2 aggregate seam (`XYAG` to `XYAO`)

WASM ABI 5 adds a resumable Rust-owned density aggregate operation. TypeScript
only frames the generated `XYAG` request, transfers it to the static Worker,
schedules bounded checkpoints, and decodes the generated `XYAO` output header.
The shared Rust `bin_2d` and mean-color kernels own binning policy and numeric
behavior; standalone density refinement now uses this path exclusively, while
the remaining #59 evidence requirements remain open.

The generated ABI manifest is authoritative for request/output offsets, aligned
strides, copy factors, the 32,768-point checkpoint, and the 64 MiB aggregate
peak. The peak includes the retained transferred request and WASM staging copy,
the accumulator, one decode checkpoint, and both Rust-owned and transferred
output copies. Aggregate calls require ownership transfer; clone mode fails
closed. A newer sequence cancels an active aggregate only after stale-sequence
validation, and every scene operation clears older aggregate state.

**Status:** bounded lifecycle, canonical Scene paint, and packed typed-column
compile (`XYCC`) for scatter/polyline/rect/band, plus transferable series
descriptors (`XYTS`) whose record expansion and defaults run in Rust.
This is **not** yet a complete direct-browser chart host. Tracking:
[#59](https://github.com/CurateLabs/xyg/issues/59).
Canonical scene dependency: [Scene IR](scene-ir.md).

### Supported ChartView density refinement

`attachWasmDensity(view, { worker, input })` is the first supported product
path for an already-painted Cartesian density trace, including one explicitly
attached kernel-backed scatter workload. `input` supplies canonical
`Float64Array` x/y source columns and, optionally, resolved straight-alpha
RGBA8 colors. For an explicit multi-trace attachment, pass `inputs` with
distinct trace ids. The one resumable WASM aggregate slot processes these
sources in supplied order; each retains its own axes and emits one bounded
Rust-owned `XYAG`/`XYAO` pair. On every ChartView viewport refinement it asks
Rust for typed output and uploads that grid through ChartView's ordinary
density texture path. It neither serializes data as JSON nor implements
binning, color aggregation, representation policy, or resource accounting in
TypeScript.

The attachment cancels the active request on a newer view, retains the current
surface until a current result arrives, and admits a result only when its
monotonic viewport sequence, handle, ChartView, and GL lifecycle all still
match. `destroy()` cancels any request; an explicitly owned Worker is then
disposed. Worker failures emit the `wasm_density_error` chart event with the
stable error code, corrective message, and resource/copy diagnostics, never
user data. Its event detail includes the failed `traceId` for a multi-trace
attachment. Normal kernel-backed ChartViews with exactly one retained typed
density source use automatic source provisioning to own a packaged same-origin
WASM worker and pass
decoded canonical f64 source values through the same XYAG/XYAO adapter; this
does not apply TypeScript aggregation. Unsupported kernel-less sources retain
their overview and dispatch an explicit no-refinement diagnostic.

The first full host vertical is deliberately one Cartesian linear count-only
trace. A split payload retains its canonical f64 x/y columns in ChartView so a
later pan can replay them. Each viewport sends an `XYAS` declaration followed
by transferable raw chunks of at most 32,768 points; no Worker retains a whole
source and no TypeScript scans, bins, grids, derives domains, or chooses LOD.
Rust owns `XYAS`-to-`XYAO` aggregation. The capacity is the generated ABI
aggregate limit (8,000,000 rows); source/chunk policy beyond one million rows,
colors, multiple traces, and nonlinear axes remain out of this vertical and
emit `XYG_WASM_SOURCE_UNSUPPORTED` when no refinement is available. There is
no JavaScript aggregation fallback.

An `XYAO` reply that passes Worker transport but fails its generated header,
length, or typed-plane validation reports `XYG_WASM_MALFORMED_OUTPUT`, rather
than a caller argument error. The error retains the Worker accounting snapshot,
leaves the last painted density surface intact, and clears the failed attempt
before an owned Worker is disposed. A corrupt aggregate therefore cannot retain
a pending task, upload a new texture, or expose source values.

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
| `js/src/49_wasm_semantic_graph.ts` | Packed direct-tier `XYGG` semantic planes; Rust emits styles, primitives, and legend |
| `js/src/49_wasm_chart.ts` | Bounded O(series) validation/framing and lifecycle handle; no record expansion or mark defaults |
| `dist/xyg-wasm.wasm` | Separately built direct-browser engine adapter; never copied into the Python static tree |

The WASM adapter disables `xyg-engine`'s default `raster` feature. Native
SVG/PNG/PDF export remains a native-host concern; browser output reuses the
shared painter. The raw module must request no ambient WebAssembly imports.

`XYTS` magic, header and descriptor offsets, flags, and mark-kind codes are
owned by `spec/wasm/abi.json` and emitted into generated TypeScript and Rust
contract modules. The thin framer and Rust decoder both consume those generated
values, while schema validation rejects missing, unknown, overlapping,
misaligned, or out-of-range fields before either module can be emitted. This keeps wire
mechanics host-visible while leaving identities, mark defaults, geometry, and
all per-record decisions exclusively in Rust.

`XYGG` v3 is the bounded semantic-graph compile ingress. Its source count is
limited to a combined 1,024 direct-tier nodes and edges (`n + e <= 1,024`),
and Rust separately enforces the
1,024 emitted-painter-trace ceiling after expanding resolved halo, dash, and
arrow primitives. The framer validates the direct tier, combined element
count, viewport dimensions, bounded string labels, finite coordinates, exact
codes and flags, compound-plane shape/representation, and final aligned buffer
length. Rust owns semantic interpretation, domains, state precedence, light/dark
paint, legend ordering, final node/edge label placement and truncation,
transitive compound/collapse resolution, and all screen-space expansion. The
thin framer requires exact node-count parent, parent-validity, and collapse
planes together; omitted planes encode one flat forest. Aggregate
LOD must omit source-indexed semantic planes and is rejected explicitly.

The compiler preserves source-edge IDs through parallel routes, self-loops,
semantic layers, dash spans, and arrowheads; run grouping is independent of
pick identity. Viewports are bounded to 16,384 px per side, peak storage is
charged before owned column allocation, and each expanded primitive is charged
before append. Light/dark backgrounds and axis/label chrome are Scene bytes,
not CSS defaults.

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
Successful results expose this snapshot directly. Worker-reported failures
after instance initialization attach the same snapshot to
`XygWasmError.diagnostics`; locally rejected or pre-initialization failures use
`null`. The error snapshot is captured after
fail-closed staging cleanup, so `arenaBytes` is zero while cumulative copy and
high-water counters remain inspectable. Rust tests and the strict-CSP Worker
test pin the typed-series fragmentation boundary at 1,025 painter traces: the
request returns `RESOURCE_LIMIT`, publishes no painter output, and reports the
one staging copy and exact copied byte count without host-side inference.
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

`WASM_ABI_VERSION` is 22. ABI 22 retains the bounded `XYSA` v1 envelope and
accepts `XYAD` v2 annotation decorations: existing `XYAT`/`XYAL`/`XYAR` slices
plus bounded `XYAC` v1 Cartesian callouts. Rust decodes the complete canonical
`XYGS` Scene first, then validates and projects raw Cartesian anchors through
its already validated layout/scales, applies the bounded screen-space offset,
and emits the ordinary painter output. TypeScript only frames/transfers byte
slices; it does not derive callout geometry or placement. ABI 13 adds exact compound planes to `XYGG` v3 and
routes them through the canonical Rust compound Scene compiler while retaining
the Scene v16/painter v11 contract. ABI 12 added the bounded `XYDP` dashboard
resource planner. Earlier revisions added Scene
paint, packed typed-column compile, transferable `XYTS` series descriptors,
resumable Tier-2 aggregation, and packed `XYTC`/`XYTR` temporal-controller
commands and snapshots. ABI 8 adds
packed `XYTG` temporal-graph binding/frame commands and Rust-produced `XYTF`
visibility, UUID membership, and remapped visible topology for layout.
ABI 14 adds packed `XYGC` → `XYCO` disclosure transitions. Stable IDs
(`u64[n]`), parents (`u64[n]`), validity (`u8[n]`), and collapse state
(`u8[n]`) are exact and bounded to 1,024 nodes. Rust alone validates the group,
forest, action, and Direct-LOD eligibility and computes the atomic next state.
The public `transitionWasmCompound` helper performs strict structural framing
and delegates the transition to that worker export. The strict-CSP browser
evidence expands and recollapses a real semantic graph, proving descendant
identity appears and disappears together in GPU traces and the single current
accessibility label layer.
The temporal subprotocol is version 2: its variable tail is a bounded raw-u64
stable-ID selection owned and canonicalized by Rust, while all temporal samples
remain raw i64. A range/cursor/window/selection snapshot is decoded and committed as
one Worker response; TypeScript neither sorts IDs nor applies partial state.
`SCENE_VERSION` remains independently versioned and is 25 for this contract.
`scripts/gen_wasm_abi.py --check` rejects parameter/result drift among
the manifest, raw Rust exports, generated TypeScript declarations, and the Rust
scene constant, including aggregate and temporal lifecycle exports. `js/package-wasm.mjs` parses the compiled module's type,
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
Scene v25 retains record metadata byte 3 explicitly: `0` retains legacy
trace/run identity, `1..6` identifies the bounded annotation kinds (with `5`
for Rust-projected straight arrows and `6` for Rust-resolved Cartesian
callout leaders), and `128`
marks literal per-row identity whose value must never classify annotations or
split connected line/area geometry. Painter v14 retains only the annotation tag
in descriptor byte 2. TypeScript therefore never interprets an authored u64 as
an internal namespace, while pick identity round-trips unchanged.

Painter contract v14 begins with `XYPB`, independent painter version 14, canonical
Scene v25 (`SCENE_VERSION = 25`), a 300-byte header, 64-byte trace descriptors, viewport/plot f32
bounds, bounded trace and tick counts, and absolute offsets to the tick and
UTF-8 label tables. Header bytes 64–263 are the exact validated Scene v23
chrome style input (backgrounds plus x/y side, masks, paints, and major/minor
geometry); bytes 264–275 carry the bounded figure-title/x-label/y-label UTF-8
lengths and bytes 276–279 are reserved zeros. The shared string table stores
those three authored texts before formatted tick labels. Header bytes 280–283
carry the exact appended legend byte length, 284–287 the bounded literal `XYCB`
colorbar length, and 288–291 the bounded `XYLB` label-block length. The
validated trailer order after tick-label strings is `XYLG` → `XYRG` → `XYCB` →
`XYRG` → `XYCT` → `XYLB`: Rust resolves the geometry of each optional legend/colorbar
record before the following decoration. `XYCB` v2 carries only bounded literal
stops, optional major values, and a minor-tick request; the following `XYCT` v1
contains Rust-resolved major/minor values, screen positions, and major-label UTF-8
tables. Rust writes the frame bounds, title and row baselines,
and literal line/marker/rectangle swatch geometry. TypeScript validates and
projects those coordinates; it does not position, wrap, scroll, or fit the
authored legend. `XYLB` stores Rust-final graph-label screen coordinates, font,
RGBA, UTF-8 text, and source u64 identity; v2 additionally carries a
Rust-owned text-anchor. Version 3 additionally carries a Rust-resolved optional
callout-label background rectangle and RGBA fill. TypeScript projects that exact
box before its label and marks it `aria-hidden`; it does not measure or reposition it.
TypeScript validates and materializes those decisions
without positioning or collision policy. Legends whose intrinsic width or height exceeds the plot fail
closed before encoding so SVG, raster, and browser consumers share one policy.
The strict-CSP foundation proof also fetches the v23-schema authored Scene
fixture generated by the public Python `Figure`; its paired Node public-API
test reconstructs the same declarative Cartesian authoring and requires the
same Scene SHA-256. The browser consumes the bytes only through the WASM
worker, then verifies chart/plot backgrounds, top/right axes and labels,
legend, literal colorbar ticks, and the callout-label background. This keeps
browser chrome consumption structural rather than host-layout-derived.
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

For a Band descriptor, byte 1 is the Rust-owned Scene v25 outline mode
(`None`, `Top`, or `Perimeter`). TypeScript projects that mode into the existing
area painter only: `Top` draws the top boundary, `Perimeter` additionally draws
the base and both endpoint faces, and `None` allocates no outline buffers. It
does not infer topology from paint alpha or reconstruct a closed path from
host defaults.

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

This is the public direct-browser entry for the stable Scene v20
subset with canonical solid chart/plot backgrounds and authored Cartesian grid,
spine, major/minor tick, side, visibility, label paint, and bounded primary
static legends, plain-text annotations, bounded Rust-projected straight
arrows, bounded Rust-resolved Cartesian callouts, and their optional
Rust-resolved literal label backgrounds. Scene v14 adds bounded
authored Cartesian major tick-label strings:
the host frames only `XYTL` v1 length-prefixed UTF-8, while Rust validates pairing
with explicit major positions, measures gutters, and emits SVG/raster/painter text.
No custom fonts, rotation, collision policy, markup, or automatic-label override is
encoded. Scene v14 also carries bounded, unlabeled axis-aligned rules and
bands plus built-in markers with literal solid paint, opacity, finite width/size,
reserved stable identity, Rust-owned clipping/order, and a visually hidden
`role=note` browser projection that names each reference without presenting
projected pixel coordinates as authored data values. `frameWasmChart`
performs bounded descriptor validation and transfers exact full-buffer
`Float64Array` columns as canonical compile ingress. Rust expands
scatter/line/bar/area and performs the only f64-to-offset-f32 lowering,
assigns or preserves stable identities, and owns default diameter, line width,
bar width/baseline, area baseline, colors, domains, and margins. The XYTS v2
descriptor predates an explicit Band topology field, so Rust preserves its
established contract deterministically: an area with positive stroke width and
nontransparent stroke paint uses `Perimeter`; otherwise it uses canonical
`None`. TypeScript does not infer that topology. The default
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

The cross-host closure fixture is generated by
`cargo run -p xyg-wasm --bin xyts_conformance` beside this Rust decoder. It
covers scatter, line, bar, and area; generated and authored arbitrary u64
identities (including the legacy annotation-prefix range); reversed and
singleton bar defaults; explicit area bounds; incompatible versions,
unsupported kinds, nonfinite geometry, and identity overflow. The committed
request, exact Scene v25 bytes, and exact painter v14 bytes are checked by the
strict-CSP direct-WASM runtime. Native Python, native Node, and real Pyodide
consume the same generated Scene bytes through the shared native
`xyg_scene_browser_painter` ABI and byte-compare its painter-v14 result with the
Rust-generated golden. They do
not decode XYTS: XYTS is the direct-browser authoring ingress, while Scene is
the portable cross-host output contract. Exact Scene and painter bytes are
portable for the pinned little-endian IEEE-754 targets; SVG text/raster pixels
remain consumer outputs and are tested structurally rather than as byte
goldens.

`XYTS` version 2 adds an optional exact `BigUint64Array` stable-ID column. The
main thread validates only its type, length, ownership, and distinct buffer;
Rust consumes the transferred values, preserves arbitrary identities, and
advances later generated IDs beyond the greatest authored identity. The column
is mutually exclusive with `stableIdBase`, and overflow fails with the stable
resource-limit status. Version 1 requests fail closed rather than being
reinterpreted with the wider descriptor contract.

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
  sequences fail with a stable cancelled status. ABI 11 starts `XYTS`/`XYCC`
  compiles with `xyg_wasm_scene_compile_begin` and advances real Rust geometry
  decode/validation in 4,096-record Worker checkpoints. Progress reports the
  completed record count and phase; it is not inferred from elapsed bytes.
  Cancellation, a newer sequence,
  or disposal can therefore retire a compile after work has begun, before it
  publishes Scene/painter output; each exit clears staging and suppresses late
  paint. The final canonical Scene lowering remains one Rust-owned operation,
  so no TypeScript policy or record expansion is introduced. The scheduler
  yields once more after all records validate and before canonical build/lower,
  including requests smaller than the old byte checkpoint. Each compile runs
  in a short-lived, same-origin static module Worker with its own Rust/WASM
  instance. The lifecycle Worker remains responsive while canonical expansion,
  Scene encode/decode, or painter lowering is executing and can terminate that
  instance immediately on cancel, supersession, or disposal. Termination is
  the cancellation boundary inside those otherwise synchronous engine loops;
  it drops all partial Rust/WASM memory and cannot publish a late response.
  Progress phase 1 reports bounded record decoding, phase 2 is the yield after
  all records decode, and phase 3 is emitted immediately before entering
  canonical expansion/Scene encode/painter lowering in the isolated instance.
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
// `update()` is sequence-safe; cancel an in-flight compile without disposing
// the caller-owned Worker.
const pendingUpdate = chartView.update(nextChart);
chartView.cancel();
await pendingUpdate; // rejects with XygWasmError code XYG_WASM_CANCELLED
// Or progressive Rust CoSE. `onUpdate` receives the one-tick initial placement
// and later coalescible checkpoints; only revision 42 may update this view.
const layout = layoutWasmCose(engine, {
  nNodes: 3,
  sources: new BigUint64Array([0n, 1n]),
  targets: new BigUint64Array([1n, 2n]),
  totalSteps: 300,
  cose: { idealEdgeLength: 0.4 },
}, { revision: 42, onUpdate: paintPositions });
const finalPositions = await layout.result;
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
also starts large `XYTS` work before exercising task and chart-handle cancel,
newer-update supersession, disposal, stable errors, and no-late-paint cleanup. It
waits for the real Rust record phase and the pre-lowering phase heartbeat, then
terminates the isolated compile instance while expensive lowering is eligible
to run. A fragmented request below 256 KiB separately proves the old byte-sized
zero-cancellation window is gone.
also exercises progressive CoSE initial/update/completion phases, pins,
revision-safe supersession, and two concurrent graph workers. It
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
committed win claim. The hosted Rust benchmark isolates typed-series conversion
at 100, 10k, 100k, and 1M records. The existing changed-main nightly/manual
CodSpeed workflow runs those simulation rows and a separate strict-CSP Chromium
job at the same four sizes. The browser job validates the zero-record-visit
contract and copy/memory metrics, then uploads SHA-keyed raw JSON. It is not PR
CI. This slice makes no startup, throughput, memory, bundle-size, or
competitive-win claim before a hosted artifact is available; raw local timings
are not performance evidence.

The same changed-main browser-evidence job also runs the self-contained
strict-CSP density ChartView journey at 100, 10k, 100k, and 1m points. Its
SHA-keyed `hosted-density-browser-<sha>.json` records browser first paint,
newest-viewport supersession, cancellation, malformed/resource/trap recovery,
disposal, typed `XYAO` payload bytes, Rust copy/memory counters, and an actual
home-viewport canvas comparison. `verify_inline_density_benchmark.py` rejects
absent or placeholder rows. This remains nightly/manual-only evidence, never
PR CI or a CodSpeed simulation claim.

## Remaining #59 work

- aggregate production paths beyond direct Scene records;
- interpreted budgets/comparisons after collecting the SHA-keyed
  small-through-massive CodSpeed and browser artifacts; and
- ongoing hosted performance and visual evidence for the Rust/WASM density
  contract, including its explicit no-refinement degradation boundary.

Public chart ergonomics (`frameWasmChart` / `renderWasmChart`) transfer exact
typed columns without main-thread record expansion. `FLAG_AUTO_DOMAIN` keeps
domain scans in Rust inside the Worker.
