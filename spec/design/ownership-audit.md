# Source ownership audit

<!-- xyg-ownership-schema: 1 -->

**Status:** enforced architecture contract. Machine-readable twin: [`ownership-audit.json`](ownership-audit.json). Tracking issue: [#56](https://github.com/CurateLabs/xyg/issues/56).

This ledger answers ownership file by file without treating language percentages as a quality target. Rust owns row scans and every parity-affecting decision. Python and Node own host ergonomics. TypeScript owns browser painting and interaction. Files marked for migration remain supported, but must not gain new canonical policy while their named issue is open.

The verifier inventories tracked source only. Tests, examples, benchmarks, generated bundles, dependencies, vendor trees, and untracked local files are deliberately outside this production-source ledger.

Migration status: Scene v25 now moves canonical viewport/plot bounds, numeric
axis transforms, chart/plot backgrounds, authored axis side and visibility,
explicit major/minor tick geometry and paint, bounded primary static legend
entry order/placement/frame/text/swatch policy, bounded semantic graph label
collision/truncation/final screen geometry and source identity, default numeric
tick/label/grid/spine chrome, clipping visibility, and scatter/polyline/rectangle record
encoding plus Band `None`/`Top`/`Perimeter` outline topology into
`crates/xyg-engine/src/scene.rs`. `python/xyg/_native.py` and
`packages/xy-node/src/scene.js` only coerce typed arrays and call the generated
batch ABI. Their remaining migration classification covers figure-to-record
assembly, additional mark families, and legacy static-export consumers. ABI 84
also makes Rust authoritative for the ordered, stable failure reason attached
to deferred authored Scene features; hosts only pack the versioned presence mask.
Rust also owns bounded multiline/wrapped annotation line breaking, line count,
and screen-space box/leader bounds; public hosts only pack literal inputs and
reject markup, CSS/classes, custom fonts, and collision policy. Rust also owns
whether resolved Cartesian Scene chrome produces SVG/raster
primitives. Host paint alpha is data, not an implicit polar-mode signal; both
hosts reject polar Scene compilation until the Scene schema records that mode.
ABI 97 also makes Rust authoritative for bounded solid-ribbon Scene geometry:
Python and Node pack two adjacent compact endpoint rows, while Rust transforms
the endpoints through the selected Cartesian axes and expands the fixed
96-interval cubic into ordinary Scene v25 Band samples. Host-local ribbon
polygon helpers remain compatibility-renderer code, not canonical Scene policy.
The public constant built-in marker slice admits all 19 fixed symbol codes when
the scatter mark does not author a separate stroke or stroke width. Python and
Node preserve the constant fill paint in the Scene style table, including
fill-as-stroke for line-only symbols, while Rust owns implicit 1px line-only
width, symbol paths, extent-aware clipping, legend swatches, and
SVG/raster/browser lowering. Authored scatter stroke paint/width remains on the
compatibility route for a later bounded cutover.
The public literal triangle-mesh slice admits at most 1,024 unjoined faces with
one constant fill and scalar overall opacity. Python and Node pack six authored
vertex columns as three-row PolyFill runs; Rust owns their stable-run grouping,
plot clipping, legend swatch, and SVG/raster/browser lowering. Joined fills,
component alpha, authored outlines, per-face paint/style, alternate axes, and
larger meshes remain compatibility behavior.

Static-export routing status (#117): `Figure.to_svg`, native `to_png`, native
`to_image(..., "svg"|"png"|"pdf")`, `write_image`, and the native branch of
`write_images` now delegate the proven
literal Cartesian public geometry subset—constant-style built-in scatter symbols
and polylines, bounded fill-only unjoined triangle meshes, ordinary finite
fixed-domain area/error-band Bands,
ordinary bar/column/histogram Rects, bounded disconnected
segment/error-bar/stem endpoint pairs, and finite literal solid-color ribbons
expanded by Rust—plus the proven literal static
chrome contract (chart/plot backgrounds, title, authored axis
labels/sides/major-minor ticks, independent literal `ticks`/`text` visibility
switches, primary legend, literal colorbar), and the existing bounded primary
Cartesian annotation family: unoffset plain text, Rust-positioned labelled rules/bands/markers,
unlabelled straight arrows, ordinary callouts, and bounded wrapped text/callouts,
to the Rust Scene
SVG and raster consumers (PDF consumes Rust SVG). `FacetGrid.to_svg` and native grid
PDF independently route each supported panel through that same Rust SVG
consumer, namespacing its closed clip-id vocabulary only for nested-document
composition; panel backgrounds and unsupported panels deliberately select
compatibility before compilation. `python/xyg/_scene_v3.py` is the single
preflight/orchestration seam for that subset: `public_static_export` owns the
Scene-format selection, while Python entry points only retain host options and
the documented compatibility exceptions. `_svg.py`, `_raster.py`, and
`_pdf.py` remain compatibility owners for rich text and legend variants, every
annotation outside that bounded primary Cartesian family (including rotation,
collision/layout directives, markup, CSS/classes, and custom typography), themes, custom fonts or CSS/classes,
nonliteral/custom chrome, custom marker paths/glyphs, data-driven symbol channels, unmodeled marks or
segment roles/styles, LOD inputs, export background overrides, and any other
unmodeled output contract; #58/#117 must
retire each exception only with cross-host differential and performance proof.
Two-ended ribbon gradients, polar ribbons, and LOD/density ribbon policy remain
explicit compatibility exceptions, and direct-browser ribbon authoring remains
under #59.

The ABI 96 primary numeric-format slice removes one more duplicated host
decision from that compatibility boundary. For Scene-eligible linear, log, and
symlog x/y axes, `crates/xyg-engine/src/scene.rs` exclusively parses
`<prefix>(,).N[f|%]<suffix>` with precision `N` from 0 through 100, resolves
final labels (including invalid-format
fallback, log sub-unit collapse protection, and explicit-label precedence),
and measures gutters. `python/xyg/_scene_v3.py` and
`packages/xy-node/src/scene.js` only retain authoring options and pack bounded
UTF-8 through the versioned ABI envelope. `js/src/30_ticks.ts` remains
canonical-policy debt for the dynamic browser path under #59; this slice does
not duplicate or extend it.

## Binding seam decision

XYG intentionally ships one versioned C ABI cdylib for all hosts. Python uses ctypes and Node uses Koffi; Koffi itself is built on Node-API, but XYG is not an N-API addon. PyO3/abi3 and napi-rs would create separate host-specific native artifacts, packaging paths, and version seams. They are not the default while the product requires one core artifact usable by CPython versions, Node, VS Code, and future adapters. Issue #57 generated both low-level bindings and the C header from one typed ABI contract; measured evidence may revisit the seam later.

## Disposition summary

| Policy | Files | Disposition | Destination |
| --- | ---: | --- | --- |
| `rust-engine` | 16 | `keep-rust` | current owner |
| `rust-c-abi` | 1 | `keep-rust` | current owner |
| `rust-wasm-abi` | 1 | `implement-rust-wasm` | [#59](https://github.com/CurateLabs/xyg/issues/59) |
| `python-host` | 52 | `keep-host` | current owner |
| `python-scene-migration` | 23 | `split-and-move-rust` | [#58](https://github.com/CurateLabs/xyg/issues/58) |
| `python-abi-generated` | 1 | `generate` | [#57](https://github.com/CurateLabs/xyg/issues/57) |
| `node-host` | 7 | `keep-host` | current owner |
| `node-scene-migration` | 29 | `split-and-move-rust` | [#58](https://github.com/CurateLabs/xyg/issues/58) |
| `node-abi-generated` | 1 | `generate` | [#57](https://github.com/CurateLabs/xyg/issues/57) |
| `browser-client` | 16 | `keep-shared-client` | current owner |
| `browser-scene-migration` | 1 | `move-rust` | [#58](https://github.com/CurateLabs/xyg/issues/58) |
| `browser-wasm-migration` | 1 | `replace-with-rust-wasm` | [#59](https://github.com/CurateLabs/xyg/issues/59) |
| `browser-wasm-adapter` | 2 | `implement-rust-wasm` | [#59](https://github.com/CurateLabs/xyg/issues/59) |
| `browser-wasm-generated` | 1 | `generate` | [#59](https://github.com/CurateLabs/xyg/issues/59) |

## Boundary policies

### `rust-engine`

Owner: Rust safe engine. Disposition: `keep-rust`.

Allowed:

- Row scans, geometry, aggregation, layout, LOD, encoding, and deterministic product policy.
- Canonical scene and static-export construction shared by every host.

Forbidden:

- Python, Node, browser DOM, or transport-specific API behavior.
- Host-specific error wording or package discovery.

### `rust-c-abi`

Owner: Rust C ABI shell. Disposition: `keep-rust`.

Allowed:

- C-compatible marshaling, panic containment, ABI versioning, and opaque-handle lifecycle.

Forbidden:

- A second implementation of algorithms or deterministic product policy that belongs in xyg-engine.
- Python- or Node-specific extension-module APIs.

### `rust-wasm-abi`

Owner: Rust WASM lifecycle adapter. Disposition: `implement-rust-wasm` under
[#59](https://github.com/CurateLabs/xyg/issues/59).

Allowed:

- Raw WebAssembly exports, bounded staging memory, instance handles, stable
  status codes, lifecycle diagnostics, and thin calls into `xyg-engine`.

Forbidden:

- A second implementation of engine policy, browser DOM/WebGL behavior,
  package asset discovery, or host-specific chart APIs.

### `python-host`

Owner: Python host. Disposition: `keep-host`.

Allowed:

- Composition and pyplot APIs, Reflex integration, ingest coercion, validation messages, transport, and notebook lifecycle.

Forbidden:

- A parallel implementation of canonical layout, LOD, encoding, aggregation, scene, or export policy.
- Hand-maintained low-level C signatures.

### `python-scene-migration`

Owner: Python host with canonical-policy debt. Disposition: `split-and-move-rust` under [#58](https://github.com/CurateLabs/xyg/issues/58).

Allowed:

- Compatibility wrappers, Python object coercion, public error text, and temporary orchestration during migration.

Forbidden:

- New canonical scene, layout, tick, geometry, colormap, or static-export behavior.
- Expanding an implementation that must match Node and direct-browser hosts.

### `python-abi-generated`

Owner: Python low-level ABI binding. Disposition: `generate` under [#57](https://github.com/CurateLabs/xyg/issues/57).

Allowed:

- Generated ctypes declarations plus a narrow handwritten ergonomic wrapper layer.

Forbidden:

- Hand-maintained symbol signatures, argument order, pointer mutability, or return types.
- Canonical engine algorithms.

### `node-host`

Owner: Node host. Disposition: `keep-host`.

Allowed:

- Idiomatic JS APIs, TypedArray coercion, errors, native-library discovery, HTML embedding, and VS Code transport.

Forbidden:

- A parallel implementation of canonical layout, LOD, encoding, aggregation, scene, or export policy.
- Hand-maintained Koffi C signatures.

### `node-scene-migration`

Owner: Node host with canonical-policy debt. Disposition: `split-and-move-rust` under [#58](https://github.com/CurateLabs/xyg/issues/58).

Allowed:

- TypedArray coercion, idiomatic composition methods, and temporary scene orchestration during migration.

Forbidden:

- New canonical scene, layout, LOD, encoding, aggregation, or static-export policy.
- Behavior that can diverge from Python or direct-browser hosts.

### `node-abi-generated`

Owner: Node low-level ABI binding. Disposition: `generate` under [#57](https://github.com/CurateLabs/xyg/issues/57).

Allowed:

- Generated Koffi declarations plus minimal loading and ABI-version validation.

Forbidden:

- Hand-maintained C signatures or canonical engine behavior.

### `browser-client`

Owner: Shared TypeScript browser client. Disposition: `keep-shared-client`.

Allowed:

- WebGL painting, picking, gestures, DOM chrome, accessibility, animation, client cache, and browser lifecycle.
- Screen-bounded presentation and transport attachment over engine-produced buffers.

Forbidden:

- Canonical layout, tick generation, data aggregation, encoding, or full-data row scans.
- Node-only modules, Koffi, filesystem access, or a second renderer.

### `browser-scene-migration`

Owner: Shared TypeScript client with canonical-policy debt. Disposition: `move-rust` under [#58](https://github.com/CurateLabs/xyg/issues/58).

Allowed:

- Temporary tick consumption and browser-specific label presentation during scene migration.
- The existing TypeScript generator stays frozen as an interaction compatibility
  path until #59 can execute the Rust-owned linear/log/symlog/category/angular/time
  ladders for each browser view and resize.

Forbidden:

- Expanding canonical tick generation or layout policy in TypeScript.

### `browser-wasm-migration`

Owner: Shared TypeScript fallback compute. Disposition: `replace-with-rust-wasm` under [#59](https://github.com/CurateLabs/xyg/issues/59).

Allowed:

- A bounded compatibility fallback and the future thin Worker adapter around Rust/WASM.

Forbidden:

- Expanding JavaScript row scans, binning, encoding, aggregation, layout, or other engine algorithms.

### `browser-wasm-adapter`

Owner: Shared TypeScript WASM lifecycle adapter. Disposition:
`implement-rust-wasm` under [#59](https://github.com/CurateLabs/xyg/issues/59).

Allowed:

- Explicit static Worker/WASM asset loading, bounded memory copies, stable
  status transport, cancellation, trap handling, and disposal.
- O(series) validation and framing for transferable typed columns. Rust owns
  per-record expansion, stable identities, and default mark/bar geometry. Exact
  per-record u64 identities remain an attached transferable column; TypeScript
  does not inspect their values.
- Generated `XYTS` offsets, flags, and kind codes from the versioned WASM
  manifest; handwritten wire-layout numbers are forbidden in the adapter.

Forbidden:

- Canonical engine algorithms, implicit CDN/path lookup, eval, Blob workers,
  or silent JavaScript fallbacks.

### `browser-wasm-generated`

Owner: Generated TypeScript WASM binding. Disposition: `generate` under
[#59](https://github.com/CurateLabs/xyg/issues/59).

Allowed:

- Generated export declarations, version checks, and status constants from
  `spec/wasm/abi.json`.

Forbidden:

- Hand-maintained raw signatures or canonical engine behavior.

## File ledger

| Path | Current owner | Policy | Disposition | Follow-up |
| --- | --- | --- | --- | ---: |
| `crates/xyg-core/src/lib.rs` | Rust C ABI shell | `rust-c-abi` | `keep-rust` | — |
| `crates/xyg-wasm/src/lib.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/compound.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/dashboard.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/compile.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/bin/xyts_conformance.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/graph.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/aggregate.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/temporal.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/temporal_graph.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/typed_series_abi_generated.rs` | Generated cross-host WASM contract binding | `browser-wasm-generated` | `generate` | #59 |
| `crates/xyg-engine/src/css.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/dashboard.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/font.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/geo.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/chunked_columns.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/edge_route.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/geo_viewport.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/graph.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/graph_style.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/hexbin.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/kernels.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/lib.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/lod_plan.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/projection.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/raster.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/sankey.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/scene.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/simd.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/stats.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/stream.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/svg.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/temporal.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/temporal_controller.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/temporal_graph.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/tile_store.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/tiles.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/transition.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `js/src/00_header.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/10_colormaps.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/20_theme.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/30_ticks.ts` | Shared TypeScript client with canonical-policy debt | `browser-scene-migration` | `move-rust` | #58 |
| `js/src/40_gl.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/42_glhost.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/45_lod.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/47_wasm.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/48_wasm_scene.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_compound.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_dashboard.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_graph.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_columns.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_semantic_graph.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_chart.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_aggregate.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_density.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_temporal.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_temporal_graph.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/50_chartview.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/51_annotations.ts` | Shared TypeScript browser client | `browser-client` | `literal-projection-only`; Scene v24 owns rule/band/marker geometry, order, clipping, defaults, bounded attached-label anchors, literal Cartesian straight-arrow projection/head geometry, bounded Cartesian callout leader/label anchoring, fixed literal label backgrounds/borders, and wrapped-line/box geometry in Rust; markup, CSS/classes, custom fonts, and collision policy remain migration debt | #116 |
| `js/src/52_tooltip.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/53_interaction.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/54_kernel.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/55_marks.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/56_animation.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/57_viewstate.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/58_graph.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/60_entries.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/wasm_abi_generated.ts` | Generated cross-host WASM contract binding | `browser-wasm-generated` | `generate` | #59 |
| `js/src/wasm_inline_worker.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/wasm_worker.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `packages/xy-node/src/_abi_generated.js` | Node low-level ABI binding | `node-abi-generated` | `generate` | #57 |
| `packages/xy-node/src/abi.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/chunked-columns.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/charts.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/color.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/encode.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/figure.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/force_scheduler.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/graph.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/html.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/index.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/marks/area.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/bar.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/box.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/contour.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/distribution.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/ecdf.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/error_band.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/errorbar.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/heatmap.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/hexbin.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/histogram.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/line.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/polar.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/radar.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/ribbon.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/scatter.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/segments.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/stem.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/step.js` | Node compact authoring adapter | `node-host-authoring` | `keep-thin`; ABI 95 passes compact step mode/source columns and Rust owns canonical Scene expansion | #58 |
| `packages/xy-node/src/marks/triangle_mesh.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/violin.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/native-path.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/native.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/pyramid.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/sankey.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/scene.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/temporal-graph.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/vscode.js` | Node host | `node-host` | `keep-host` | — |
| `python/reflex_xy/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/app.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/assets/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/component.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/events.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/namespace.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/payload_asset.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/registry.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/selections.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/state_bridge.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/tokens.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/vars.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_abi_generated.py` | Python low-level ABI binding | `python-abi-generated` | `generate` | #57 |
| `python/xyg/_wasm_aggregate_generated.py` | Generated cross-host WASM contract binding | `browser-wasm-generated` | `generate` | #59 |
| `python/xyg/_annotations.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_arrowgeom.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_benchmark_theme.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_chromium.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_figure.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_fontmetrics.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_framing.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_geoarrow.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_graph.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_hosts.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_jpeg.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_legendfit.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_native.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_ooc.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_paint.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_payload.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_pdf.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_png.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_raster.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_sankey.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_scene.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_scene_v3.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_spatial.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_svg.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_textblock.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_trace.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_typing.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_validate.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_webp.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/channel.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/channels.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/columns.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/components.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/config.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/dom.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/export.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/facets.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/graph_layout.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/interaction.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/kernels.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/lod.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/marks.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/plugins.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_artists.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_axes.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_axisgrid.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_colors.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_fmt.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_grid.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_markers.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_mathtext.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_mplfig.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_plot_types.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_rc.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_state.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_ticker.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_transforms.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_translate.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/dates.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/styles.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/styling/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/styling/capabilities.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/temporal_controller.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/temporal_graph.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/widget.py` | Python host | `python-host` | `keep-host` | — |

## Contributor rule

Run `python3 scripts/verify_ownership.py` after adding, removing, or renaming production source. A new file is intentionally unclassified until this ledger names its owner and boundary in the same change. Moving a file between policies requires updating both this audit and its JSON twin; do not weaken a policy to make a new host algorithm pass.
