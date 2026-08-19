# Source ownership audit

<!-- xyg-ownership-schema: 1 -->

**Status:** enforced architecture contract. Machine-readable twin: [`ownership-audit.json`](ownership-audit.json). Tracking issue: [#56](https://github.com/CurateLabs/xyg/issues/56).

This ledger answers ownership file by file without treating language percentages as a quality target. Rust owns row scans and every parity-affecting decision. Python and Node own host ergonomics. TypeScript owns browser painting and interaction. Files marked for migration remain supported, but must not gain new canonical policy while their named issue is open.

The verifier inventories tracked source only. Tests, examples, benchmarks, generated bundles, dependencies, vendor trees, and untracked local files are deliberately outside this production-source ledger.

Migration status: Scene v4 now moves canonical viewport/plot bounds, numeric
axis transforms, default numeric tick/label/grid/spine chrome, clipping
visibility, and scatter/polyline/rectangle record
encoding into `crates/xyg-engine/src/scene.rs`. `python/xy/_native.py` and
`packages/xy-node/src/scene.js` only coerce typed arrays and call the generated
batch ABI. Their remaining migration classification covers figure-to-record
assembly, additional mark families, and legacy static-export consumers.

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
| `crates/xyg-engine/src/css.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/font.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/graph.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/hexbin.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/kernels.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/lib.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/lod_plan.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/raster.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/sankey.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/scene.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/simd.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/stats.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/stream.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/svg.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/tiles.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/transition.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `js/src/00_header.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/10_colormaps.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/20_theme.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/30_ticks.ts` | Shared TypeScript client with canonical-policy debt | `browser-scene-migration` | `move-rust` | #58 |
| `js/src/40_gl.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/42_glhost.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/45_lod.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/46_worker.ts` | Shared TypeScript fallback compute | `browser-wasm-migration` | `replace-with-rust-wasm` | #59 |
| `js/src/47_wasm.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/50_chartview.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/51_annotations.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/52_tooltip.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/53_interaction.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/54_kernel.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/55_marks.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/56_animation.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/57_viewstate.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/58_graph.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/60_entries.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/wasm_abi_generated.ts` | Generated TypeScript WASM binding | `browser-wasm-generated` | `generate` | #59 |
| `js/src/wasm_worker.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `packages/xy-node/src/_abi_generated.js` | Node low-level ABI binding | `node-abi-generated` | `generate` | #57 |
| `packages/xy-node/src/abi.js` | Node host | `node-host` | `keep-host` | — |
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
| `packages/xy-node/src/marks/step.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/triangle_mesh.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/violin.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/native-path.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/native.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/pyramid.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/sankey.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/scene.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
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
| `python/xy/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/_abi_generated.py` | Python low-level ABI binding | `python-abi-generated` | `generate` | #57 |
| `python/xy/_annotations.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_arrowgeom.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_benchmark_theme.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/_chromium.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/_figure.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_fontmetrics.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_framing.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_graph.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_hosts.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/_jpeg.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_legendfit.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_native.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/_ooc.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/_paint.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_payload.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_pdf.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_png.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_raster.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_sankey.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_scene.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_scene_v3.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_spatial.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/_svg.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_textblock.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/_trace.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/_typing.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/_validate.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/_webp.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/channel.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/channels.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/columns.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/components.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/config.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/dom.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/export.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/facets.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/interaction.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/kernels.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/lod.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/marks.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xy/plugins.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_artists.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_axes.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_axisgrid.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_colors.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_fmt.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_grid.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_markers.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_mathtext.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_mplfig.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_plot_types.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_rc.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_state.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_ticker.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_transforms.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/_translate.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/pyplot/dates.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/styles.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/styling/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/styling/capabilities.py` | Python host | `python-host` | `keep-host` | — |
| `python/xy/widget.py` | Python host | `python-host` | `keep-host` | — |

## Contributor rule

Run `python3 scripts/verify_ownership.py` after adding, removing, or renaming production source. A new file is intentionally unclassified until this ledger names its owner and boundary in the same change. Moving a file between policies requires updating both this audit and its JSON twin; do not weaken a policy to make a new host algorithm pass.
