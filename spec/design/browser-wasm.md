# Direct-browser Rust/WASM boundary

## Dynamic viewport ticks (`XYTK` to `XYTO`)

The tick operation introduced in WASM ABI 23 is carried by current WASM ABI 31
and makes tick resolution one bounded Rust-owned Worker operation.
Axes carry explicit scale family and `automatic`, `authored_values`, or
`authored_empty` provenance; symlog constants, log masking, angular units,
UTC-time semantics, category tables, and bounded formats are versioned input,
never inferred from packed bytes. Authored values and labels always win, and an
explicitly empty authored set remains distinct from automatic provenance.

The low-level TypeScript codec submits an atomic axis batch and strictly decodes
the echoed sequence, axis identity, revision, provenance, f64 values/step, and
UTF-8 labels. The Worker owns a tick-specific FIFO and cancellation watermark,
so a cancelled or disposed request cannot publish a result.

Tick work is independent and therefore does not cancel compile, density,
graph, or temporal work. Each axis is capped
at 200 output positions and 65,536 source categories; label/category text is
capped at 65,536 UTF-8 bytes per axis. Embedded NUL, nonfinite input, and
category/label/format planes irrelevant to the declared family or request
provenance are rejected before output across every host.

`attachWasmTicks(view, { worker })` installs the bounded ChartView product
cutover for automatic, authored-value, and authored-empty primary and secondary
Cartesian axes; angular/radial polar axes; authored minor-axis slots; and
eligible major/minor colorbar slots. Linear, log, symlog, category, UTC-time,
angular-radian, and angular-degree families are explicit `XYTK` input. Rust
exclusively chooses positions and labels. Eligibility excludes category axes
without a non-empty NUL-free string table, Scene-placed axes/colorbars (already
Rust-owned via painter tick descriptors/`XYCB`), and log domains that are not
strictly positive. An axis
is *covered* only after an admitted Rust cache exists for that eligible slot
and still matches its current family, category table, format, and provenance;
newly eligible slots or family/provenance switches after mount paint no tick
positions or labels until that cache arrives. An admitted `authored_empty`
cache is a real empty result, not that pre-admission fail-close. The first
current `XYTO` result is
admitted before the attachment becomes authoritative; later pan/zoom/resize
requests cancel older work and retain only the last admitted Rust cache until
a matching sequence and axis revision returns. Admission reconciles the
Rust-produced label metrics through ChartView's complete forced resize path so
plot, mark canvas, chrome, titles, and interaction geometry move atomically;
it never calls `_layout()` alone. An unchanged screen-bounded target
deduplicates, while a changed target may schedule one current follow-up batch.
The browser foundation proves formatted/title, category/time, and authored-label
attachments settle without revision churn. A stale, cancelled, destroyed, or
replaced attachment cannot publish. No ChartView tick slot calls a TypeScript ladder or axis
formatter, even
after a Worker failure. Failed snapshots emit one coalesced
`xy:wasm_ticks_error` and remain eligible to retry.

This cutover is deliberately explicit and bounded. Missing, malformed,
unattached, or not-yet-admitted WASM fails closed with a stable diagnostic and
paints no synthetic ticks. A canonical Rust Scene may instead carry tagged
resolved tick descriptors, which ChartView consumes without recomputation.
Self-contained
Blob-worker HTML remains ineligible. Hosted `to_html()`, notebook widgets, and
Reflex `XYChart` auto-attach when they serve the packaged `wasm-worker.js` and
`xyg-wasm.wasm` files at explicit same-origin URLs (`workerUrl` stays required;
there is no path guessing or CDN). The srcdoc notebook iframe cannot load those
siblings and fails closed for dynamic ticks. The M2-claimed delivery and its
deferred/follow-up boundaries are recorded below. Related to #59; dedicated
follow-up issues track work outside that claimed subset.

M2 #869 makes `xyg-engine::packed_ticks` the single packed resolver called by
current WASM ABI 30 and native ABI 361 `xyg_tick_resolve_packed`. The boundary
was introduced in WASM ABI 23/native ABI 360. The native function
uses the capacity-aware probe/write contract and returns `usize::MAX` for an
invalid `XYTK`. `packed_ticks_cross_host.json` proves byte-identical `XYTO`
positions, labels, provenance, angular filtering, minor ticks, and failure
behavior through Python/native, Node/native, and a real browser/WASM Worker.

## Tier-2 aggregate seam (`XYAG` to `XYAO`)

WASM ABI 5 adds a resumable Rust-owned density aggregate operation. TypeScript
only frames the generated `XYAG` request, transfers it to the static Worker,
schedules bounded checkpoints, and decodes the generated `XYAO` output header.
The shared Rust `bin_2d` and mean-color kernels own binning policy and numeric
behavior; standalone density refinement now uses this path exclusively, while
broader hosted evidence is tracked by the post-M2 follow-up **Refresh hosted WASM evidence and prove density no-refinement degradation** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)).

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
This is **not** yet a complete direct-browser chart host. Broader aggregate
production and release-matrix conformance continue under
[#54](https://github.com/CurateLabs/xyg/issues/54). The delivered M2 foundation
is related to [#59](https://github.com/CurateLabs/xyg/issues/59).
Canonical scene dependency: [Scene IR](scene-ir.md).

WASM ABI 24 also exposes `xyg_wasm_density_first_paint_plan`, an
allocation-free policy diagnostic over the shared Rust payload orchestrator.
It accepts a split-u64 source count plus grid dimensions and packs the tier,
screen-bounded mark count, pyramid/WASM eligibility, sample attachment, and
source-shipment flags into one u32. `0xffffffff` is the fail-closed result;
the exact bit layout is generated from `spec/wasm/abi.json`. This is not an
alternate aggregator or permission to ship canonical f64: the strict-CSP
browser gate queries it at 1M and 100M and requires source shipment to remain
false at both sizes.

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
attachment. Normal Python/Node kernel-backed ChartViews do not include
canonical f64 in the ordinary split first-paint payload. They retain the
screen-bounded overview and use the host kernel route for later views. A
dedicated Worker/WASM replay journey must explicitly request the replay source
(`wasm_source=True` in Python, `wasmSource: true` in Node); true direct-browser
callers already own their typed source locally and stage it through the same
XYAG/XYAO adapter. This does not apply TypeScript aggregation. Unsupported
kernel-less sources retain their overview and dispatch an explicit
no-refinement diagnostic.
This is automatic source provisioning only after that explicit opt-in; the
default split payload never retains replay columns.

The first full host vertical is deliberately one Cartesian linear count-only
trace. An explicitly replay-enabled split payload retains canonical f64 x/y
columns in ChartView so a later pan can replay them; ordinary split first paint
does not. Each viewport sends an `XYAS` declaration followed
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
| `js/src/49_wasm_graphforge.ts` | GraphForge `XYGQ` framing, `XYGF` decoding, Scene stable-ID → UUID identity, text-only tables; no joins or policy |
| `js/src/49_wasm_chart.ts` | Bounded O(series) validation/framing and lifecycle handle; no record expansion or mark defaults |
| `js/src/49_wasm_ticks.ts` | XYTK/XYTO codec plus latest-wins primary Cartesian ChartView attachment |
| `dist/xyg-wasm.wasm` | Separately built direct-browser engine adapter; never copied into the Python static tree |

The WASM adapter disables `xyg-engine`'s default `raster` feature. Native
SVG/PNG/PDF export remains a native-host concern; browser output reuses the
shared painter. The raw module must request no ambient WebAssembly imports.

**Artifact size.** `dist/xyg-wasm.wasm` is built with the workspace release
profile (`opt-level = 3`, fat LTO, one codegen unit, stripped) and is about
921 KiB raw and 336 KiB gzipped at WASM ABI 27. ABI 28 with GeoColumn
ingestion measures 968137 raw bytes and 352160 gzip bytes (level 9), within
the unchanged 1 MiB raw artifact budget. ABI 29 with frozen geographic
Scene lowering measures 994525 raw bytes and 362640 gzip bytes (level 9).
GraphForge compositions
(composition, views, request/base decoding) and the Arrow IPC reader account
for about 224 KiB of code; there is no single outlier. A size-optimized
profile was measured and rejected, since the module's compute is on users'
interactive path:

| profile | raw | gzip | GraphForge compose, 10k / 100k nodes |
|---|---:|---:|---:|
| `opt-level = 3` (shipped) | 943 KB | 344 KB | 15.6 / 156 ms |
| `opt-level = "s"` | 877 KB | 311 KB | 21.1 / 203 ms |
| `opt-level = "z"` | 777 KB | 280 KB | 38.3 / 363 ms |

ABI 30 camera transport and closed polygon caches make the default O3 artifact
1,060,579 raw bytes. The target-specific `.cargo/config.toml` keeps O3, fat LTO,
one codegen unit and stripping; ABI30 set LLVM's inline threshold to 150.
Native builds remain unchanged. The ABI30 artifact was 1,028,586 raw bytes and
376,783 gzip bytes, below the unchanged 1 MiB gate. This is a measured size/runtime
tradeoff, not a claim of a speedup: four ABBA pairs at 100/10,000/100,000 rows
produced byte-identical outputs across GraphForge composition, geographic Scene
compile and camera-column projection. At 10k/100k rows, median candidate costs
were 0.8–4.8% above baseline (about 1.89ms at the largest GraphForge case); the
100-row GraphForge case costs about 4.5µs more. These synthetic Arrow contracts
measure XYG composition, not GraphForge algorithm execution, browser paint or
massive-data behavior. Raw samples, environment, input generator and reproduction
commands are recorded in `spec/benchmarks/wasm-inline-150-local.json`.
The earlier global size-optimized profiles remain rejected.


ABI31's complete geographic catalog and interactions use the same O3 profile,
with a target-specific inline threshold of 100 and a build-only pinned
Binaryen132.0.0 `wasm-opt -O3 --all-features` post-link pass. Packaging reads the
source once, optimizes an isolated temporary copy, validates the exact optimized
export/import/signature and ABI/Scene version contract (start functions are rejected; painter version is verified by the real painter conformance tests), applies the recorded raw and gzip size gates, then
publishes those validated bytes and their deterministic inline digest. The
optimizer is an Apache2.0 npm devDependency; no Binaryen code or dependency
enters the browser runtime. Native builds remain unchanged.

The measured artifact is 1,034,845 raw / 418,362 level9 gzip bytes. The
same-source inline150 raw baseline is 1,172,316 / 431,903 bytes. Four ABBA
pairs compare byte-identical admitted GraphForge, Scene, camera, catalog and
interaction results at 100/10k/100k rows. Geographic medians range from 6.0%
faster to unchanged. GraphForge costs about 9µs more at100 rows, 0.067ms more
at10k and 1.64ms more at100k (+3.6%). Both artifacts explicitly reject the
100k interaction request under the existing processor peak policy; no latency
is assigned to that rejected operation. Fresh-process Node startup medians
were 27.73ms versus26.92ms, with compilation1.09ms versus1.01ms. These local
measurements do not establish browser paint, production or massive-scale wins.
Raw samples, hashes, environment, source files and commands are committed in
`spec/benchmarks/wasm-geographic-profile-local.json`.

The original raw artifact gate was 1 MiB. The retained geographic source,
resumable membership, certified simplification, tile cache, frozen snapshots,
and transport credit introduced in ABI 33 require an explicit budget decision:
**1,310,720 raw bytes (1.25 MiB), plus 524,288 gzip bytes (512 KiB)**. Packaging
fails either gate. The release compiler and pinned Binaryen 132 `-O3
--all-features` profile remain unchanged; this decision admits functionality,
not a compiler optimization or performance win.

The local ABI 33 candidate is 1,230,703 raw / 502,593 gzip bytes, SHA-256
`b4ef252d2acb7ab0c916cd8e91d966bb3e7c1b1b64d2ec79887bce47cfdf2f72`.
The ABI 32 predecessor was 1,034,845 raw / 418,362 gzip bytes. This growth is
18.9% raw and 20.1% gzip. Three fresh-browser-process/profile retained Worker
startup samples are 28.3, 25.9, and 34.7 ms (median 28.3 ms), accompanied by
actual five-view GL painting, strict offline CSP, cancellation/ownership, and
malformed-receipt regressions. [Raw reports and reproduction commands](../performance/geo-scale-browser-2026-10-08/README.md)
record the artifact, environment, and verified output contracts. Startup is
Worker construction to ready over raw loopback HTTP with a warm OS file cache;
it excludes main ESM parsing and was measured under uncontrolled development
load. These are local samples, not a paired profile comparison, cold disk/WAN
latency, or massive-scale paint/interaction evidence. Further growth beyond
either gate requires another recorded decision rather than silent drift.

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

`WASM_ABI_VERSION` is 30. ABI 30 adds the stateless typed camera protocol
(`xyg_wasm_geo_viewport_execute`; [contract](geo-viewport-protocol.md)). ABI 29 adds frozen geographic `XYGP` → `XYGS` compilation
(`xyg_wasm_geo_scene_compile`). ABI 28 adds sequenced single-use GeoColumn
ingestion (`xyg_wasm_geo_column_ingest`) and `xyg_wasm_geo_metadata_version`.
ABI 27 adds `xyg_wasm_graphforge_compose` and
`xyg_wasm_graphforge_composition_version`: one staged GraphForge `XYGQ`
request in, the native host's byte-identical `XYGF` document out
([graphforge-compositions.md](graphforge-compositions.md) §6.3). ABI 23 introduced the bounded `XYTK`/`XYTO` tick
resolver and its independent Worker sequence lane; ABI 26 added the
default-palette and stricter packed-tick validation cuts that ABI 27 keeps.
ABI 22 retains the bounded `XYSA` v1 envelope and
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
`SCENE_VERSION` remains independently versioned and is 32 for this contract.
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

Painter contract v15 begins with `XYPB`, independent painter version 15, canonical
Scene v32 (`SCENE_VERSION = 32`), a 300-byte header, 64-byte trace descriptors, viewport/plot f32
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
Each 64-byte trace descriptor starts with kind/symbol/annotation/reserved bytes,
then a u32 primitive count. Kinds 0–4 retain their prior scatter/polyline/rect/
band/three-vertex polygon layouts. All offsets are absolute and all data planes
are emitted contiguously in the order below; metadata views consume the planes
without JavaScript gathering, sorting, triangulation, color resolution, or size
normalization. Canonical Image records are consumed rather than omitted.

| Derived kind | Coordinate offsets | Identity offsets | Additional planes |
| --- | --- | --- | --- |
| 5, Image (`count=1`) | 8/12/16/20: one f32 x0/y0/x1/y1 | 24/28: u32 low/high | 48/52: width/height values; 56: raw RGBA8 offset; 60: exact byte length `width*height*4` |
| 7, triangle instances | 8/12/16/20/48/52: f32 x0/y0/x1/y1/x2/y2 | 24/28: u32 low/high per triangle | 56: RGBA8 fill plane; 60: byte length `count*4` |
| 8, marker instances | 8/12: f32 x/y; 16: u32 source style refs; 20: zero | 24/28: u32 low/high per marker | 48: raw f32 CSS diameter; 52/56: RGBA8 fill/stroke; 60: four-f32 CSS style rows |
| 9, segment instances | 8/12/16/20: f32 x0/y0/x1/y1 | 24/28: u32 low/high per segment | 48: RGBA8 stroke; 52: four-f32 CSS style rows; 56: u32 source style refs; 60: zero |

Kinds 5/8/9 reserve bytes 32–47 as zero. Kind 7 reserves its scalar fill
32–35 as zero and retains common stroke RGBA/width at 36–43, with zero diameter.
New kinds have zero symbol and annotation bytes. Kind 7 batches only explicit
Scene Triangle primitives, splitting on a visible primitive of another kind,
an invisible source boundary, annotation tag, or differing stroke paint/width.
Each instance carries its own resolved fill and complete u64 identity. Kind 8
batches adjacent ordinary visible Scatter records across color, width, diameter,
and symbol changes. Kind 9 batches only explicit Scene Segment primitives;
an arbitrary Polyline is never reinterpreted as independent segments. Paint
order is retained. Marker/segment planes use 48 bytes per instance; triangles
use 36. Rust includes every plane and image byte in preallocation admission.

The CSS style row is `[1,-1,resolved_width,symbol]` (segment symbol is -1).
The marker width includes Rust's line-only-symbol default. The existing GPU
program applies only CSS-to-device width conversion through
`u_instanceStyleCss` and `u_dpr`; the client uploads the exact plane, never
rebakes it on DPR changes. Raw marker diameters use the existing size channel
with unit range `[0,1]`, preserving the Rust float values for paint and picking.
Packed canonical segments retain the native round-cap policy within the
existing segment program, including DPR scaling. Generic authored channels and
segments keep their existing units and behavior.

Image pixels are straight-alpha RGBA8 in image-top-first order. They upload
directly into the existing nearest-filtered true-color texture program. The
image's screen y range anchors row zero at its top; no host pixel transform is
performed. Positive dimensions, positive bounds, exact byte length, kind-specific
reserved fields, count, and contiguous offsets fail closed before hydration.
Per-instance planes retain complete identities, with no synthesized feature IDs.

Rust derives default numeric
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
production beyond the current density/Scene vertical is tracked by
the post-M2 follow-up **Expand direct-browser aggregate production beyond the density/Scene vertical** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)); release-level cross-host conformance remains under
[#54](https://github.com/CurateLabs/xyg/issues/54). The two version numbers are
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
- Sequence zero is reserved. Lower/repeated sequences fail as stale. Worker
  aggregate-stream begin participates in the same operation watermark as
  geographic/camera, scene, aggregate, and graph requests. Deferred operations
  recheck admission before cancelling lanes or staging bytes, so a stale or
  zero camera call preserves a newer stream and a current camera supersedes it.
  Cancelled
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
  ranges, and resource bounds return stable error codes. Initialization
  mismatches are distinct: `XYG_WASM_ABI_MISMATCH` (WASM ABI differs from the
  client's), `XYG_WASM_SCENE_MISMATCH` (Scene version), `XYG_WASM_PALETTE_MISMATCH`
  (default palette contract), `XYG_WASM_EXPORT_MISMATCH` (a required export is
  absent or has another signature at the same versions),
  `XYG_WASM_IMPORTS_REJECTED` (the module requests ambient imports),
  `XYG_WASM_BUDGET_EXCEEDED` (`maxArenaBytes` above the adapter bound), and
  `XYG_WASM_INSTANCE_EXHAUSTED`; asset loading failures (fetch, redirect,
  compile) stay `XYG_WASM_INIT_FAILED`. The self-contained HTML inline worker
  embeds its WASM bytes beside its own source, so a version skew cannot occur
  there and it reports `XYG_WASM_INIT_FAILED`. There is no silent
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
// Or cut a normal ChartView's supported primary Cartesian ticks to Rust.
// These are deployed same-origin files copied from one @curatelabs/xyg release.
const tickWorker = createXygWasmWorker({
  workerUrl: "/assets/xyg/wasm-worker.js",
  wasm: "/assets/xyg/xyg-wasm.wasm",
  maxArenaBytes: 1024 * 1024,
});
const tickHandle = await attachWasmTicks(existingChartView, {
  worker: tickWorker,
  workerOwnership: "own",
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

The browser-package tick asset contract is the ESM client plus the exported
`./wasm-worker` and `./xyg-wasm.wasm` files from one package version. A host
must deploy the Worker and WASM at explicit same-origin URLs (or pass checked
WASM bytes/`WebAssembly.Module`) and must not mix versions. Release
`ASSET-MANIFEST.json` records every shipped filename's byte length and SHA-256
alongside the wire, WASM ABI, Scene, and painter versions; release staging and
the published-package smoke verify those hashes before deployment. There is no
runtime Worker-byte hash helper—the Worker URL is loaded directly so a
fetch-then-Worker check would introduce a time-of-check/time-of-use gap.
Initialization still fails closed on the generated ABI/Scene version check
before `attachWasmTicks` mounts. A missing asset emits
`xy:wasm_ticks_error` and rejects the attachment; a failure after mounting
retains the last Rust-produced cache and never starts JavaScript generation.
This contract does not authorize Blob/data Workers or synchronous main-thread
WASM.

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
node scripts/wasm_html_ticks_smoke.mjs
node benchmarks/bench_wasm_scene.mjs
```

Both the primary full-suite job and the Python 3.11 floor build that real WASM
payload before running browser probes. The generated Worker alone is not a
valid fixture: its missing paired payload must retain the production
fail-closed diagnostic instead of silently selecting a JavaScript tick path.
The polar phase 6/7 live-example smoke copies that exact packaged pair, serves
it beside each page over same-origin HTTP under a strict CSP, and captures only
after `ticks_ready`; categorical polar labels therefore prove Rust admission
instead of passing through a timing-dependent or canonical JavaScript ladder.
The interaction-stress benchmark uses the same hosted packaged pair and waits
for admitted primary axes before timing gestures or auditing label overlap;
its measurements use real time rather than a Worker-incompatible virtual-time
controller.
The dashboard reliability benchmark likewise waits for one admitted primary
axis pair per successfully created chart before measuring the complete page;
its 10/20/50/60-chart rows cannot pass with blank fail-closed chrome.
The direct-browser foundation independently exercises natural asynchronous
attachment and resize reconciliation without the legacy probe helper's manual
layout boundary. HTTP-backed browser probes preserve an explicit Chromium
device-scale-factor request in their Playwright page context, so moving those
probes off `file:` URLs does not silently reduce high-DPI coverage to DPR 1.

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

## M2 #59 disposition and follow-up work

The claimed M2 subset is delivered: the Worker/WASM foundation and strict-CSP
contract; packaged WASM tick assets (#258); authored ChartView ticks (#257);
ChartView colorbar ticks (#262); Reflex `XYChart` auto-attach implementation
(#260); and interpreted Wave B evidence (#263).

Angular/polar and secondary-axis ChartView cutovers are **frozen deferred
keepers** on their existing compatibility paths. They are outside the
follow-up issues and do not block the claimed M2 subset.

Work outside that claimed subset is tracked independently:

- real-browser E2E proof for Reflex packaged tick-asset auto-attach
  (`XYChart` already injects explicit `./wasm-worker.js` +
  `./xyg-wasm.wasm` and calls `attachHostWasmTicks`):
  the post-M2 follow-up **Prove Reflex packaged WASM tick auto-attach in a real browser** (related to [#54](https://github.com/CurateLabs/xyg/issues/54));
- direct-browser aggregate production paths beyond the current density/Scene
  vertical: the post-M2 follow-up **Expand direct-browser aggregate production beyond the density/Scene vertical** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)); and
- post-Wave-A current-`main` SHA-keyed hosted artifacts, a green CodSpeed
  simulation, interpreted competitive budgets, and hosted visual evidence for
  the explicit no-refinement degradation boundary:
  the post-M2 follow-up **Refresh hosted WASM evidence and prove density no-refinement degradation** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)).

The delivered hosted-artifact interpretation subset is recorded in
[`spec/benchmarks/results.md`](../benchmarks/results.md). Related to #59;
the follow-up issues above track the remaining work independently.

## Density no-refinement gate

Unsupported or kernel-less sources must retain the already-painted
Rust-authored overview and dispatch `xy:wasm_density_no_refinement`. There is
no JavaScript aggregator fallback.

| Surface | Location | Status |
|---|---|---|
| Adapter policy | `js/src/49_wasm_density.ts` | shipped: missing/invalid inline artifact and unsupported sources fail closed |
| Kernel dispatch | `js/src/54_kernel.ts` (`wasm_density_no_refinement`) | shipped |
| Observer phase | `js/src/60_entries.ts` (`density_no_refinement`) | shipped |
| Standalone missing WASM | `tests/test_density_pan_no_rebin.py` | green when Chromium is present |
| Bundle / contract probes | `tests/test_static_client_security.py`, `tests/test_wasm_density_chartview_contract.py`, `tests/test_wasm_full_density_source.py` | green |
| Hosted SHA-keyed visual evidence of this boundary | nightly `hosted-density-browser-<sha>.json` | tracked by the post-M2 follow-up **Refresh hosted WASM evidence and prove density no-refinement degradation** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)); current artifacts prove refinement lifecycle, not no-refinement |

Stable codes: `XYG_WASM_UNAVAILABLE`, `XYG_WASM_SOURCE_UNAVAILABLE`, and
`XYG_WASM_SOURCE_UNSUPPORTED`.

Public chart ergonomics (`frameWasmChart` / `renderWasmChart`) transfer exact
typed columns without main-thread record expansion. `FLAG_AUTO_DOMAIN` keeps
domain scans in Rust inside the Worker.

## GeoColumn descriptor ingestion (`XYGD` to `XYGM`)

WASM ABI 28 exposes `xyg_wasm_geo_column_ingest(handle, sequence, offset,
length) -> i32`. It reads one `XYGD` v1 typed descriptor and returns the shared
engine's byte-identical `XYGM` v1 metadata through the instance output. The
column is temporary: neither whole source nor canonical geometry is retained
past the call. All six two-dimensional geometry kinds, null features, polygon holes, exact
f64 coordinates, and full u64 identities use `GeoColumn` validation. There is
no Arrow dependency or TypeScript geometry/topology engine.

`XYGD` is little-endian with a 64-byte header: magic at 0, version u32 at 4,
geometry u32 at 8, CRS u32 at 12, flags u32 at 16 (bit 0: explicit identities),
reserved zero u32 at 20, feature count u64 at 24, vertex count u64 at 32, and
three offset-plane lengths u64 at 40/48/56. Planes follow in order: interleaved
f64 coordinates, per-feature u8 validity, optional u64 identities, then three
u32 offset planes. Every plane is padded with zero bytes to eight-byte
alignment. Unknown flags, nonzero reserved/padding bytes, truncation, overflow,
and trailing bytes fail closed. This canonical authoring ingress carries raw
f64; it is never a live painter payload (§29).

`encodeWasmGeoDescriptor` frames typed arrays without interpreting CRS or
geometry. `XygWasmWorker.geoColumnIngest` transfers the resulting request and
returns metadata; original typed source buffers stay with the caller because
the encoder copies them. The worker defers one task turn so immediate cancel
can suppress execution. Requests share the worker's operation sequence lane;
zero/stale/cancelled sequences fail, and disposal rejects pending tasks. A
synchronous call cannot be interrupted mid-validation; shared geometry and
hole-work ceilings bound its work. Frozen geographic point/outline Scene lowering
is specified below; live camera transitions use XYVC/XYVR. Map layer/fill programs
remain #49, and LOD/export #50.

Rust rejects before allocating typed planes when simultaneous transferred JS
request bytes, staging capacity,
decoded numeric planes, retained canonical planes (including generated IDs and
ring winding), plus 8192 fixed scratch/metadata bytes exceed the instance
budget. Retained staging capacity outside the request is subtracted too.
`GeoLimits` also enforces feature/vertex/canonical-byte limits. Accepted sequences release staging capacity on success or geometry/framing
failure and clear previous output. Rejected zero/stale/cancelled sequences
preserve an active newer operation and its staging; idle rejections release it. Only the
small metadata output survives until the next operation or disposal; linear
WASM memory itself cannot shrink. Resource failures return WASM status 3;
geometry/framing failures status 2 with the exact value-safe `XYG_GEO_*` code
in `last_error`; lifecycle statuses keep their existing meanings.

Evidence: `packages/xy-node/test/geo-wasm-parity.test.mjs` sends the committed
Python/GraphForge goldens through the actual wasm32 artifact and native ABI,
comparing metadata bytes and stable failures for six kinds, nulls, holes,
3857, exact f64 and u64 identity planes. It also proves allocation admission,
nonzero request offsets, malformed framing, cancellation, stale sequences,
recovery, and disposal. `crates/xyg-wasm/src/geo.rs` tests generated-identity
peak accounting and released backing allocations. The strict-CSP browser
probe is `scripts/geo_wasm_smoke.mjs`.

### Frozen geographic Scene ingress (WASM ABI 29, #47)

`xyg_wasm_geo_scene_compile(handle, sequence, offset, length)` runs the shared
`xyg-engine::geo_scene::compile_geo_scene` processor. Its `XYGP` v1 authoring
frame contains a frozen camera, a single point/outline style, and a checked
`XYGD` descriptor. Output is ordinary canonical `XYGS`, consumed by the
existing Rust Scene preparation and WebGL paint/pick path. No geographic
geometry policy is implemented in TypeScript.

The 128-byte little-endian header contains: magic at 0, version u32 at 4,
header length u32 at 8, flags u32 at 12 (world wrap bit 0, authored fill bit 1,
authored stroke bit 2), camera CRS u32 at 16, zero reserved u32 at 20; nine f64
values at 24 through 88 (center x/y, zoom, width/height, bearing/pitch in degrees,
point diameter, stroke width); fill/stroke RGBA8 at 96/100; descriptor length
u64 at 104; zero reserved bytes 112–127. The exact descriptor follows at 128.
Camera and source CRS must agree. NaN diameter/width select Rust defaults 6/1;
otherwise styles must be finite, nonnegative, and representable as finite f32.
Canvas dimensions must likewise narrow to finite f32, and satisfy GeoViewport
validation. Missing paints select the engine default palette row. Unknown
flags, reserved bytes, framing errors and non-paintable fields fail atomically.

Points retain the shared projected origin before lowering to screen-space
Scatter records. Offscreen centers are culled by the canonical marker bounds,
including diameter/stroke extent. Outlines use GeoViewport's dateline splitting
and viewport segment clipping. A transparent zero-size offscreen Scatter record
separates clipped Polyline runs, without nonfinite authoring coordinates or
connections between independent segments. Both segment endpoints and the
invisible separator retain the source u64 identity with literal Scene metadata;
annotation-shaped identities and u64::MAX have no alternate interpretation.
Null geometry contributes no marks. Polygon holes are outline rings; fills are
not part of this ingress. Screen identity axes preserve projection orientation.
Chrome has explicitly empty major ticks and transparent axis/label paints.

Admission precedes variable engine allocations. At most one point record per
source vertex or six outline records per source vertex is admitted, also capped
by `MAX_SCENE_MARKS`. The conservative simultaneous peak ceiling is three times
request bytes + 16 bytes per feature + 512 bytes per maximum record + 32768 bytes
fixed scratch. This covers transfer/staging, canonical planes, projection,
compact input columns, prepared marks and encoded Scene, including capacity
slack. Additional retained arena capacity is subtracted by the lifecycle shell.
Only output survives execution; no canonical source is retained indefinitely.
The native `geo_scene_conformance` executable bounds stdin to budget + 1 before
reading and uses exactly the same processor. Resource failures use status 3 and
`XYG_GEO_RESOURCE_LIMIT`; invalid geometry/framing/style uses status 2 and the
shared `XYG_GEO_*` code. Pitch within the certified −60°..60° ground-plane
range uses the shared frustum processor; out-of-range pitch fails admission.
Zero/stale/cancelled sequences preserve newer active
operations; accepted calls supersede them and release staging on every outcome.

`packages/xy-node/test/geo-scene-wasm-parity.test.mjs` compares native executable
output with the actual wasm32 export for all six geometry kinds, nulls, holes,
EPSG:3857, f64 source precision, full u64 identities, independent wrapped
segments, framing and allocation failures. Scene structure, IDs, paints and
sidecars are byte-identical; projected coordinates permit at most 1e-6 CSS pixel
cross-target difference. The offscreen-first zoom-24 regression independently
requires the expected 2.386092942 CSS-pixel separation. The strict-CSP
`scripts/geo_wasm_smoke.mjs` submits transferred requests through the packaged
Worker, hydrates ordinary Scene paint, verifies painted pixels, GPU picks and
full u64 identity, independent outline runs, cancellation and recovery. The
hydrated deep-zoom upload independently retains the same separation within
1e-4 CSS pixel (the existing painter stores screen coordinates as f32).

The bounded frozen point/outline path supplies #47's actual derived Scene parity
evidence. ABI 30 also supports certified perspective pitch through the same
GeoViewport frustum processor; live transitions use XYVC/XYVR below;
MapLibre/catalog/fills/interaction use the ABI31 catalog below; geographic LOD and frozen massive-source export remain #50.


The camera protocol is a separate sequenced geographic command in the existing
Worker lane. `XygWasmWorker.geoViewportExecute` transfers `XYVC` and resolves
with aligned `XYVR` typed planes. The shared Rust processor owns normalization,
transitions, inverse/projection, visible IDs/bounds, and closed ring topology.
[The exact byte and allocation contract](geo-viewport-protocol.md) is normative.
Actual wasm32/native/C-ABI parity is `geo-viewport-wasm-parity.test.mjs`.
