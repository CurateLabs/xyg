# Host parity — Python and Node

The browser WASM host retains packed `XYAG` for the compatibility seam and now
exposes `XYAS` v1 for the product-path successor: a header/domain/grid plus
bounded canonical f64 x/y chunks, all binned count-only by Rust and finished as
the existing packed `XYAO`. Hosts may frame and transfer chunks, but cannot
scan, bin, or select a grid/domain policy. Exact mean-color accumulation stays
on the legacy seam until its separately bounded stream contract exists.
Cancellation cleanup and the aggregate peak model remain Rust-owned. Native
hosts continue to use the same `xyg-engine` binning kernels. Wiring streamed
`XYAO` into aggregate production beyond the current density/Scene vertical is
tracked by the post-M2 follow-up **Expand direct-browser aggregate production beyond the density/Scene vertical** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)).

**Status:** requirements locked and **ready for review** with
[graph-fork-requirements.md](graph-fork-requirements.md); implementation design
in [graph-mark.md](graph-mark.md). Runtime taxonomy and machine-readable twin:
[dual-host-parity-matrix.md](dual-host-parity-matrix.md) /
[`dual-host-parity.json`](dual-host-parity.json).

**Scope:** the **entire product** — every chart type and mark family, not
graph-only. Graph is the core dual-host feature, but the three runtime surfaces
and the placement rule below apply to scatter, line, hist, area, bar, box,
heatmap, hexbin, violin, sankey, polar, and every other shipped kind.

**Priority:** **graph visualization** is the core feature. **MVP includes all
chart / visualization features** on Python and Node with equal feel and speed —
no degraded non-graph path, and **no Python host-only layout/encode leftovers**.

**Architecture principle — Rust owns decisions:** implement chart behavior in
the shared Rust C ABI so Python and Node stay thin loaders over identical
behavior. **Rust owns decisions** that affect buffers, layout, encodings, LOD,
and recorded §28 outcomes — not only O(N) loops. Hosts own ergonomics and
idiomatic I/O only; the browser client owns screen-bounded draw and gestures
only. [rust-engine.md](rust-engine.md) §1 states this rule directly for XYG
(upstream XY's "Python owns decisions" is recorded there as historical).

**Host-neutral packaging:** Python exists only when the user is using
Python. Public npm names are `@curatelabs/xyg` (paint client) and
`@curatelabs/xyg-node` (Node host) — never `@xy/node`. Plan:
[host-neutral-architecture.md](host-neutral-architecture.md) / GitHub #24.
The paint-client artifact is in-repo as `@curatelabs/xyg` (#23); registry
publish waits on the `@curatelabs` npm org (#13).

---

## 0. Three runtime surfaces (product-wide)

XYG has exactly **three** runtime surfaces. They cover all chart types. Do not
treat VS Code, notebooks, or Reflex as separate engine stacks.

| Surface | Location | Role |
|---|---|---|
| **1. Python host** | `python/xyg/` (+ `python/reflex_xy/`) | Primary authoring host for notebooks and Python apps. Loads the Rust cdylib via **ctypes**. Surfaces: **anywidget** notebooks (`show()`), **HTML export** (`to_html()` / standalone), and **Reflex**. Embeds a **copy** of the paint client plus the packaged `wasm-worker.js` / `xyg-wasm.wasm` tick assets in the wheel (`python/xyg/static/`) so Python users need no Node. The public import is `xyg`; `reflex_xy` remains a separate integration namespace. |
| **2. Node host** | `packages/xy-node` (`@curatelabs/xyg-node`) | Thin Node bindings (koffi) over the **same** Rust C ABI. Covers **server-side Node** and **VS Code extensions**: VS Code is a **consumer of the Node bindings**, not a fourth stack. Never publish `@xy/node`. Native loading uses the exact optional platform package (`@curatelabs/xyg-node-<platform>-<arch>`, #52), with only an explicit absolute-path `XYG_NATIVE_LIB` development override; it never searches a checkout, working directory, system path, or Python. Windows arm64 is an explicit unsupported error. `toHtml()` inlines the host-neutral standalone client, not the Python tree. Root `npm ci` does **not** install this package; CI Test and Python 3.11 jobs run `npm ci --prefix packages/xy-node` so koffi is present for Node host tests. |
| **3. Browser surface** | `js/src/*.ts` + Rust/WASM → `@curatelabs/xyg` (`packages/xy-client/dist/{index,standalone}.js`) | Shared WebGL2 painter and browser lifecycle. It draws §29 buffers uploaded by Python/Node and uses the #59 foundation for direct browser execution by the same Rust engine compiled to WebAssembly in a Worker. TypeScript keeps paint, pick, gestures, accessibility, DOM chrome, transitions, caches, and request scheduling; Rust owns canonical layout/LOD/encode decisions. |

The #59 foundation adds `crates/xyg-wasm`, a generated raw-export adapter,
and an explicit static module Worker. It proves bounded JS→WASM staging,
version/status/lifecycle behavior, exact Scene validation/paint lowering, and
packed typed-column compile into the same canonical Scene batch native hosts
encode. Public `frameWasmChart` / `renderWasmChart` transfer typed series while
Rust assigns identities and expands canonical mark/default geometry. The
current density/Scene vertical is delivered; broader aggregate production is
tracked by the post-M2 follow-up **Expand direct-browser aggregate production beyond the density/Scene vertical** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)). See [browser-wasm.md](browser-wasm.md).

Those typed series use versioned `XYTS` canonical compile ingress: exact raw
f64 source columns move JS → Worker and undergo one bounded copy into WASM.
They are not the live paint wire and are not `XYBF`. Rust alone validates and
lowers them to the shared offset-f32/u8 painter buffer consumed by WebGL; the
browser host has no per-record conversion or policy fallback.
Rust also owns staging-copy and resource accounting. The Worker returns those
counters unchanged on success and attaches them to public `XygWasmError`
failures after initialization; TypeScript neither reconstructs byte counts nor
estimates retained Rust resources.

`tests/fixtures/xyts_cross_host.json` is generated from the Rust XYTS decoder,
never authored by a host. Direct WASM recompiles every request and matches the
exact Scene v23 output under a local-only strict CSP. Native Python and Node
load those Scene bytes through the shared `xyg_scene_browser_painter` C ABI and
byte-compare Rust's painter-v13 lowering; the Pyodide wheel executes that same
native ABI inside an actual Pyodide runtime with network access disabled for
the conformance operation. This is intentionally asymmetric: adding an XYTS
decoder to Python or Node would duplicate browser-ingress policy rather than
prove host parity.
Filesystem-backed XYGC chunk reads and tile-store spills are intentionally
unavailable in Pyodide. The Emscripten library exports the shared ABI symbols
as fail-closed stubs so supported in-memory kernels and Scene consumers still
load. The Pyodide gate calls every stub and checks its documented sentinel and
signature; it never emulates filesystem policy in Python or JavaScript. These
stubs are Emscripten-specific, not a blanket policy for every WASM target.

The #58 scene migration is active: scene schema version 25 provides one
backend-neutral Rust-owned typed batch with fixed caller-provided plot bounds, axes,
scatter, polyline, rectangle, and versioned bounded decoration records through both host bindings. The v1
scatter SVG wrapper remains temporarily for scatter-only compatibility. Python
and Node now compile the same representative constant-style scatter/line/bar
figure fixture to identical Scene bytes; explicit host APIs feed those bytes to
Rust SVG and native-raster consumers. Public Python SVG/PNG/PDF select the Rust
Scene consumers only for the proven bounded literal Cartesian geometry subset:
all 19 constant built-in scatter symbols either without authored stroke or with
an authored constant CSS stroke and optional finite non-negative scalar width
(default 1px), and constant-style
polylines, ordinary area/error-band
Bands, bar/column/histogram Rects, disconnected segment/error-bar/stem endpoint
pairs with bounded stem markers, at most 1,024 fill-only unjoined
triangle-mesh faces (constant or interned per-face fill/stroke/width, ABI 195),
interned per-item scatter fill/stroke/width/opacity (ABI 196),
constant-style Cartesian hexbin PolyFill cells (one
6-vertex group per cell, sharing that 1,024-group painter budget), constant-style
Cartesian heatmap Rects (one regular cell per Rect, sharing the 10,000-bin
histogram ceiling), and finite
literal solid ribbons. Each accepted mesh face
is one three-vertex PolyFill group shared by SVG, raster, and browser consumers;
`joined_fill` plus per-face paint, polar meshes, alternate axes, and
larger meshes remain compatibility behavior. For ribbons,
Python and Node pack two adjacent endpoint rows and ABI 97 makes Rust apply the
axis transforms and expand the fixed 96-interval cubic into 97 paired Scene
Band samples. Two-ended gradients, polar projection, LOD/density, and
direct-browser ribbon authoring remain explicit boundaries; broader
direct-browser production paths are tracked by the post-M2 follow-up **Expand direct-browser aggregate production beyond the density/Scene vertical** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)). Every
unmodeled output contract remains an explicit compatibility route.
ABI 98 additionally gives both composition hosts one compact grouped violin
ingress. Hosts pack values, group offsets/centers, bins, width, orientation,
and literal style; Rust owns finite filtering, density normalization,
width/orientation, the 10,000-Rect bound, and final geometry. Vertical and
horizontal exact-byte fixtures feed the same SVG, raster, and browser Scene
consumers. Pyplot KDE bodies and advanced/polar variants remain compatibility.
Exact composition ECDFs in both hosts use the existing synchronous
`xyg_weighted_ecdf` kernel for total-order sorting, duplicate coalescing, and
normalized cumulative mass. Python passes its raw f64 column so Rust also
filters nonfinite observations; Node's existing coercion seam removes them
before the same kernel. After those validation/coercion seams, hosts prepend
the right-continuous zero anchor and author literal line style before the existing
Rust-expanded Step Scene path. Exact unsorted/repeated/nonfinite and singleton
fixtures are byte-identical through SVG, raster, and browser consumers. Binned
ECDFs use ABI 100 `xyg_binned_ecdf` in both hosts. Rust filters nonfinite
samples; applies the shared automatic-domain rule (constant nonzero values
widen by 5% of their absolute value, falling back to plus/minus 0.5 at zero or
when that pad is not useful) or Node's optional finite increasing authored range; enforces
the 10,000-bin bound; counts, normalizes, and omits empty bins; and returns the
zero anchor plus occupied-bin right edges. An authored Node range normalizes
in-range mass over every finite source sample, so excluded samples remain
visible in the final probability. Python deliberately adds no public range
option. The compact result remains an ordinary `post` Step and exact mode
remains `xyg_weighted_ecdf`.
An omitted composition-histogram bin count now resolves through the existing
Rust `xyg_histogram_edges(..., auto)` policy in both Python and Node. Explicit
positive integer bins and the empty-finite ten-bin compatibility case use
`xyg_histogram_mark_edges`; all-nonfinite input retains
the documented ten-bin `[0, 1]` (or authored-range) compatibility result.
ABI 101 `xyg_histogram_bins` then counts those resolved or authored edges in
Rust, applying density and left-to-right cumulative assembly. Rust caps
automatic or authored resolution at 10,000 bins (10,001 edges); invalid ranges,
non-increasing edges, or larger results fail through the hosts' existing
histogram argument errors. Unsorted, repeated, nonfinite, constant, ranged,
authored-edge, density, and cumulative fixtures produce identical Rect Scenes
for SVG, raster, and browser consumers.
ABI 102 makes composition hexbin ingress Rust-owned without a Scene-version
change. Both hosts pass raw f64 x/y (and optional C) plus either a scalar
grid width or an explicit pair; `grid_h == 0` selects matplotlib
`int(width / √3)` floored at 2, and `use_range == 0` applies the shared
automatic-domain pad. Finite-pair filtering ignores nonfinite x, y, or C.
Python custom reducers keep host group reduction after `xyg_hexbin_groups`
resolves the same domain, aspect, and lattice membership. The compact wire result remains the
existing centers-only hexbin trace. Constant-style Cartesian native
count/mean/sum lattices now compile those centers plus `hex_dx`/`hex_dy`
onto existing Scene v25 PolyFill records (one 6-vertex group per cell).
Python and Node fixtures are byte-identical through SVG, raster, and
browser consumers. Constant-style mean and sum share Scene bytes when they
occupy the same lattice, because paint ignores the metric. ABI 103 moves that
hex-cell ring and the regular heatmap lattice reconstruction into Rust
`expansion_modes` (`HexCell=5`, `HeatmapLattice=6`); hosts pack compact
center+pitch rows and a two-row extent+shape lattice. ABI 134 adds
`HeatmapPainted=9` plus an XYHP paint sidecar (or XYEX wrapping XYPL+XYHP on
the existing extras pointer): hosts pack the same two-row lattice plus RGBA8 or
scalar+stops payload; Rust tessellates cells and interns unique fills. ABI 135
adds `xyg_colormap_stops` and XYHP paint kind 2 so named tables live in Rust;
hosts pack a name or a custom RGB ramp. ABI 136 adds
`xyg_scene_resolve_pack_kind` / `xyg_scene_pack_product` so product-kind
dispatch and column remapping live in Rust. ABI 147 adds
`xyg_scene_pack_product_facts` so flags, `step_mode`, and extras resolve from
packed XYPK v1. ABI 148 adds `xyg_scene_pack_annotation_facts` so wrap vs
text vs arrow vs callout vs rule/band/marker routing resolves from packed
XYAF v1. ABI 149 adds `xyg_scene_pack_heatmap_facts` so heatmap/density
XYHP kind routing resolves from packed XYHF v1. ABI 150 adds
`xyg_scene_pack_scene_extras` so XYDS/XYLC/XYMP/XYGR/XYMG layout, concat order,
omit-empty, and XYEX wrapping resolve from packed XYSS v1 plus framed
XYPL/XYHP. ABI 151 adds
`xyg_scene_pack_density_grid` so Scene density `bin_2d` / `density_log_u8` /
optional mean-color resolve from packed columns. ABI 152 adds
`xyg_scene_pack_public_export` so XYEP layout, kind/step/annotation codes,
and flag derivation resolve from packed XYEF v1. ABI 153 adds
`xyg_scene_pack_figure_chrome` so plot layout, chrome-style resolve, legend
loc default/allowlists (empty authored loc is fail-closed, not the
upper-right default), colorbar flags/framing, XYTL tick-label framing, and
the 200-tick axis bound resolve from packed XYCF v1. Layout errors stay
plot-layout diagnostics so the public-export predicate can remap them to
`XYG_SCENE_UNSUPPORTED_VIEWPORT`. ABI 154 adds
`xyg_scene_pack_trace_compile` so opacity, symbol, color, dash, linecap,
marker-path, diameter, legend kind, step, curve-smooth, stroke-perimeter,
hex pitch, fill-gradient admission, and XYMS resolve from packed XYTC v1.
ABI 155 adds
`xyg_scene_pack_trace_attach` so heatmap/density attach policy
(shape/finite fail-closed checks, XYHF remainder order, density skip,
density XYHF flags, fact bits, density zeroing, and domain rewrite)
resolves from packed XYTO plus XYTA v1.
ABI 156 adds
`xyg_scene_pack_trace_rows` so XYPK construction, scatter-only
symbol/diameter, density domain-endpoint column rewrite, and
`pack_product_facts` resolve from packed XYTT plus XYCL v1.
ABI 157 adds
`xyg_scene_pack_trace_sidecars` so legend-name gating, heatmap-vs-density
plane selection, and per-trace style/dash/marker/gradient/plane extraction
resolve from packed XYTT plus XYNM v1.
ABI 158 adds
`xyg_scene_pack_style_sidecars` so XYSS dash/linecap/marker/gradient
records resolve from packed XYSD plus XYAO v1.
ABI 159 adds
`xyg_scene_splice_annotations` so annotation style/row splice and XYAD
extract resolve from packed product rows plus XYSD plus XYAO v1.
ABI 160 adds
`xyg_scene_encode_assembled` so assembled Scene encode resolves from packed
XYAS plus XYCC plus extras.
ABI 161 adds
`xyg_scene_pack_figure_chrome_from_sidecars` and
`xyg_scene_pack_scene_extras_from_sidecars` so legend paints and XYHP
wrapping resolve from packed XYSD.
ABI 162 adds
`xyg_scene_encode_assembled_from_sidecars` so XYCC packing, extras packing,
and viewport/axis scalars resolve from packed XYAS plus XYCF plus XYSD plus
polar plus XYSS.
ABI 163 adds
`xyg_scene_encode_product` so product-path compile, attach, sidecar, row,
annotation, style-sidecar, splice, and assembled encode resolve from packed
XYTC plus XYTA plus XYNM plus XYCL plus XYAF plus XYCF plus polar.
ABI 164 adds
`xyg_scene_static_export` so public SVG/PNG/PDF/JPEG/WebP consumers resolve
from one encoded Scene.
ABI 165 extends
`xyg_scene_encode_product` so the figure-compile support probe resolves from
packed XYFS on the same product call.
ABI 166 tessellates cartesian bar/column/histogram `corner_radius` after pixel
mapping through `geom::rounded_rect_poly`; ABI 167 applies polar
bar/column/histogram `wedge_gap` as a constant pixel inset. ABI 168
tessellates polar bar/column/histogram `corner_radius` when the inner radius
is positive. ABI 169 admits polar `curve="smooth"` plus `step` as polar step
expansion (identity chords). ABI 170 admits constant scatter `marker_glyph`
via an XYMG extras sidecar kept on the encoded Scene. ABI 171 admits
width-only scatter `stroke_width` as match-fill. ABI 172 admits cartesian
line `curve="smooth"` plus `step` as authored step expansion. ABI 181 admits
cartesian area/error_band `curve="smooth"` plus `step` as authored band step
expansion. ABI 182 admits triangle_mesh `joined_fill` as one identity PolyFill
ring. ABI 183 admits constant ribbon `color2_ch` as XYGR mark-space `dir=right`.
ABI 184 admits cartesian unwrapped text `dx`/`dy`/`anchor` as XYAW `wrap=0`.
ABI 185 admits labelled cartesian marker `dx`/`dy`/`anchor` as XYAW `wrap=0`.
ABI 186 admits cartesian colormap hexbin as a 1×N XYHP plane interned onto HexCell PolyFills.
ABI 187 admits cartesian unwrapped text `rotation` as XYAW `wrap=0` (XYAW v2 / XYLB v6).
ABI 188 admits labelled cartesian marker `rotation` as XYAW `wrap=0` (nums[8]).
ABI 189 owns heatmap/hexbin cell-fill tessellation eligibility from packed XYTA.
ABI 190 intern cartesian per-item two-ended ribbon `color2_ch` from packed XYHP kind 5.
ABI 191 admits constant multi-character scatter `marker_glyph` via XYMG v2.
ABI 192 admits polar painted heatmap inverse-raster as one Scene Image blit.
ABI 193 admits heatmap/hexbin `stroke` / `stroke_width` / `stroke_opacity`.
ABI 194 admits polar hexbin, custom host reducers, and categorical / `direct_rgba` hexbin.
ABI 195 admits triangle-mesh custom `role` and per-item fill/stroke/width interned from packed XYHP kind 6. ABI 196 intern scatter per-item fill/stroke/width/opacity from packed XYHP kind 7.
ABI 173 tessellates
heatmap `corner_radius`. ABI 174 tessellates violin/box `corner_radius`.
ABI 175 admits violin/box `fill_opacity` / `stroke_opacity`.
ABI 176 admits bar/column/histogram `fill_opacity` / `stroke_opacity`.
ABI 177 admits heatmap `fill_opacity`.
ABI 193 admits heatmap/hexbin `stroke` / `stroke_width` / `stroke_opacity`.
ABI 194 admits polar hexbin, custom host reducers, and categorical / `direct_rgba` hexbin.
ABI 195 admits triangle-mesh custom `role` and per-item fill/stroke/width interned from packed XYHP kind 6. ABI 196 intern scatter per-item fill/stroke/width/opacity from packed XYHP kind 7.
ABI 178 admits scatter `fill_opacity` / `stroke_opacity`.
ABI 179 admits hexbin `fill_opacity`.
ABI 180 admits triangle_mesh `fill_opacity` / constant stroke paint.
ABI 181 admits cartesian area/error_band `curve="smooth"` plus `step` as
authored band step expansion.
ABI 182 admits triangle_mesh `joined_fill` as one identity PolyFill ring.
ABI 183 admits constant ribbon `color2_ch` as XYGR mark-space `dir=right`.
ABI 184 admits cartesian unwrapped text `dx`/`dy`/`anchor` as XYAW `wrap=0`.
ABI 185 admits labelled cartesian marker `dx`/`dy`/`anchor` as XYAW `wrap=0`.
ABI 186 admits cartesian colormap hexbin as a 1×N XYHP plane interned onto HexCell PolyFills.
ABI 187 admits cartesian unwrapped text `rotation` as XYAW `wrap=0` (XYAW v2 / XYLB v6).
ABI 188 admits labelled cartesian marker `rotation` as XYAW `wrap=0` (nums[8]).
ABI 189 owns heatmap/hexbin cell-fill tessellation eligibility from packed XYTA.
ABI 190 intern cartesian per-item two-ended ribbon `color2_ch` from packed XYHP kind 5.
ABI 191 admits constant multi-character scatter `marker_glyph` via XYMG v2.
ABI 192 admits polar painted heatmap inverse-raster as one Scene Image blit.
ABI 193 admits heatmap/hexbin `stroke` / `stroke_width` / `stroke_opacity`.
ABI 194 admits polar hexbin, custom host reducers, and categorical / `direct_rgba` hexbin.
ABI 195 admits triangle-mesh custom `role` and per-item fill/stroke/width interned from packed XYHP kind 6. ABI 196 intern scatter per-item fill/stroke/width/opacity from packed XYHP kind 7.
ABI 137 / Scene v27 adds
`DensityBlit=10` and `SceneRecordKind::Image=5`: hosts pack the heatmap
extent lattice plus an XYHP kind-3 log-u8 plane, and Rust emits one Image
record plus XYIM. ABI 138 / Scene v28
adds XYDS constant dash on the same extras pointer (raw XYDS or XYEX v2)
and an XYDS sidecar after XYIM. ABI 139 / Scene v29 adds XYLC constant
linecap on that same extras pointer (raw XYLC, XYDS+XYLC concat, or XYEX v2)
and an XYLC sidecar after XYDS. ABI 140 / Scene v30 adds `CurveFlatten=11`
so cartesian `curve="smooth"` polylines flatten in Rust from compact knots
(pack `step_mode=4`); ABI 141 / Scene v31 adds `BandFlatten=12` so cartesian
`area(curve="smooth")` bands flatten the same way. ABI 142 admits cartesian
mean-color density as XYHP kind 4 on the existing `DensityBlit` Image blit.
ABI 143 polar density tessellates occupied `DensityBlit` cells to PolyFill
wedges. ABI 144 admits cartesian `error_band(curve="smooth")` on existing
`BandFlatten=12` and polar `curve="smooth"` line/area/error_band as identity
chords (polar-axes.md §5). ABI 145 admits constant scatter `marker_path`
via an XYMP extras sidecar tessellated after pixel mapping. ABI 146 admits
constant mark `fill` linear-gradients via an XYGR extras sidecar kept on the
encoded Scene. ABI 147 owns product packing facts from XYPK v1. ABI 148 owns
annotation family routing from XYAF v1. ABI 149 owns heatmap/density XYHP
kind routing from XYHF v1. ABI 150 owns style-sidecar layout and extras wrapping
from XYSS v1. ABI 151 owns Scene density binning and log-u8 encoding from
packed columns. ABI 152 owns XYEP layout, kind/step/annotation codes, and
flag derivation from packed XYEF v1. ABI 153 owns plot layout, chrome-style
resolve, legend loc default/allowlists (empty authored loc is fail-closed),
colorbar flags/framing, XYTL tick-label framing, and the 200-tick axis bound
from packed XYCF v1. ABI 154 owns per-trace Scene compile policy
(opacity, symbol, color, dash, linecap, marker path, diameter, legend kind,
step, curve-smooth, stroke-perimeter, hex pitch, fill-gradient admission,
and XYMS resolve) from packed XYTC v1. ABI 155 owns heatmap/density attach
policy from packed XYTO plus XYTA v1. ABI 156 owns XYPK construction,
scatter-only symbol/diameter, density domain-endpoint column rewrite, and
`pack_product_facts` from packed XYTT plus XYCL v1. ABI 157 owns
legend-name gating, heatmap-vs-density plane selection, and per-trace
style/dash/marker/gradient/plane extraction from packed XYTT plus XYNM v1.
ABI 158 owns XYSS dash/linecap/marker/gradient record construction from
packed XYSD plus XYAO v1.
ABI 159 owns annotation style/row splice and XYAD extract from packed
product rows plus XYSD plus XYAO v1.
ABI 160 owns assembled Scene encode from packed XYAS plus XYCC plus extras.
ABI 161 owns legend paints and XYHP wrapping from packed XYSD.
ABI 162 owns XYCC packing, extras packing, and viewport/axis scalars from
packed XYAS plus XYCF plus XYSD plus polar plus XYSS.
ABI 163 owns product-path compile, attach, sidecar, row, annotation,
style-sidecar, splice, and assembled encode from packed XYTC plus XYTA plus
XYNM plus XYCL plus XYAF plus XYCF plus polar.
ABI 164 owns public SVG/PNG/PDF/JPEG/WebP consumers from one encoded Scene.
ABI 165 owns the figure-compile support probe from packed XYFS on product encode.
ABI 169 admits polar `curve="smooth"` plus `step` as polar step expansion
(identity chords). ABI 170 admits constant scatter `marker_glyph` via XYMG.
ABI 171 admits width-only scatter `stroke_width` as match-fill.
ABI 172 admits cartesian line `curve="smooth"` plus `step` as authored
step expansion.
ABI 173 tessellates heatmap `corner_radius`.
ABI 174 tessellates violin/box `corner_radius`.
ABI 175 admits violin/box `fill_opacity` / `stroke_opacity`.
ABI 176 admits bar/column/histogram `fill_opacity` / `stroke_opacity`.
ABI 177 admits heatmap `fill_opacity`.
ABI 193 admits heatmap/hexbin `stroke` / `stroke_width` / `stroke_opacity`.
ABI 194 admits polar hexbin, custom host reducers, and categorical / `direct_rgba` hexbin.
ABI 195 admits triangle-mesh custom `role` and per-item fill/stroke/width interned from packed XYHP kind 6. ABI 196 intern scatter per-item fill/stroke/width/opacity from packed XYHP kind 7.
ABI 178 admits scatter `fill_opacity` / `stroke_opacity`.
ABI 179 admits hexbin `fill_opacity`.
ABI 180 admits triangle_mesh `fill_opacity` / constant stroke paint.
ABI 181 admits cartesian area/error_band `curve="smooth"` plus `step` as
authored band step expansion.
ABI 182 admits triangle_mesh `joined_fill` as one identity PolyFill ring.
ABI 183 admits constant ribbon `color2_ch` as XYGR mark-space `dir=right`.
ABI 184 admits cartesian unwrapped text `dx`/`dy`/`anchor` as XYAW `wrap=0`.
ABI 185 admits labelled cartesian marker `dx`/`dy`/`anchor` as XYAW `wrap=0`.
ABI 186 admits cartesian colormap hexbin as a 1×N XYHP plane interned onto HexCell PolyFills.
ABI 187 admits cartesian unwrapped text `rotation` as XYAW `wrap=0` (XYAW v2 / XYLB v6).
ABI 188 admits labelled cartesian marker `rotation` as XYAW `wrap=0` (nums[8]).
ABI 189 owns heatmap/hexbin cell-fill tessellation eligibility from packed XYTA.
ABI 190 intern cartesian per-item two-ended ribbon `color2_ch` from packed XYHP kind 5.
ABI 191 admits constant multi-character scatter `marker_glyph` via XYMG v2.
ABI 192 admits polar painted heatmap inverse-raster as one Scene Image blit.
ABI 193 admits heatmap/hexbin `stroke` / `stroke_width` / `stroke_opacity`.
ABI 194 admits polar hexbin, custom host reducers, and categorical / `direct_rgba` hexbin.
ABI 195 admits triangle-mesh custom `role` and per-item fill/stroke/width interned from packed XYHP kind 6. ABI 196 intern scatter per-item fill/stroke/width/opacity from packed XYHP kind 7.
ABI 104 likewise moves
disconnected endpoint pairs (`SegmentPair=7`) and unjoined triangle faces
(`TriangleFace=8`) into that compact expansion; hosts pack one four-coordinate
row per segment and two PolyFill rows per face. ABI 105 makes the public
static-export support predicate Rust-owned: Python and Node pack the same
`XYEP` v1 envelope and surface `xyg_scene_public_export_reason` verbatim.
ABI 152 makes that envelope Rust-owned: Python and Node pack `XYEF` v1 facts
and call `xyg_scene_pack_public_export`.
ABI 153 makes figure chrome Rust-owned: Python and Node pack `XYCF` v1 facts
and call `xyg_scene_pack_figure_chrome`.
ABI 154 makes per-trace Scene compile Rust-owned: Python and Node pack `XYTC`
v1 facts and call `xyg_scene_pack_trace_compile`.
ABI 155 makes heatmap/density attach Rust-owned: Python and Node pack `XYTA`
v1 facts against compiled `XYTO` and call `xyg_scene_pack_trace_attach`.
ABI 156 makes product-row packing Rust-owned: Python and Node pack `XYCL`
v1 kind/coords/id/columns against attached `XYTT` and call
`xyg_scene_pack_trace_rows`.
ABI 157 makes trace-sidecar packing Rust-owned: Python and Node pack `XYNM`
v1 names against attached `XYTT` and call `xyg_scene_pack_trace_sidecars`.
ABI 158 makes XYSS packing Rust-owned: Python and Node pass `XYSD` plus
`XYAO` and call `xyg_scene_pack_style_sidecars`.
ABI 159 makes annotation splice Rust-owned: Python and Node pass product
rows plus `XYSD` plus `XYAO` and call `xyg_scene_splice_annotations`.
ABI 160 makes assembled Scene encode Rust-owned: Python and Node pass
`XYAS` plus `XYCC` plus extras plus axis scalars and call
`xyg_scene_encode_assembled`.
ABI 161 makes XYSD chrome/extras packing Rust-owned: Python and Node pass
`XYCF` legend options plus `XYSD` to `xyg_scene_pack_figure_chrome_from_sidecars`
and polar plus `XYSD` plus `XYSS` to `xyg_scene_pack_scene_extras_from_sidecars`.
ABI 162 makes product-path assembled encode Rust-owned from sidecars: Python
and Node pass `XYAS` plus `XYCF` plus `XYSD` plus polar plus `XYSS` and call
`xyg_scene_encode_assembled_from_sidecars`.
ABI 163 makes product-path Scene encode Rust-owned from packed facts: Python
and Node pass `XYTC` plus `XYTA` plus `XYNM` plus `XYCL` plus `XYAF` plus
`XYCF` plus polar and call `xyg_scene_encode_product`.
ABI 164 makes public static-export consumers Rust-owned: Python and Node pass
one encoded Scene plus format/scale/size/quality and call
`xyg_scene_static_export`.
ABI 165 folds figure-compile support into that product call: Python and Node
pass packed `XYFS` on `xyg_scene_encode_product` instead of probing
`xyg_scene_figure_support_reason` separately. Empty `XYFS` skips the probe.
ABI 166 tessellates cartesian bar/column/histogram `corner_radius` on that
same product Scene so public `to_svg` / PNG do not fall back to `_svg.py` /
`_raster.py` for constant radii. ABI 167 applies polar
bar/column/histogram `wedge_gap` on that same product Scene. ABI 168
tessellates polar bar/column/histogram `corner_radius` on that same product
Scene when the inner radius is positive. ABI 169 admits polar `curve="smooth"`
plus `step` on that same product Scene as polar step expansion. ABI 170 admits
constant scatter `marker_glyph` on that same product Scene. ABI 171 admits
width-only scatter `stroke_width` as match-fill on that same product Scene.
ABI 172 admits cartesian line `curve="smooth"` plus `step` as authored
step expansion on that same product Scene. ABI 173 tessellates heatmap
`corner_radius` on that same product Scene. ABI 174 tessellates violin/box
`corner_radius` on that same product Scene. ABI 175 admits violin/box
`fill_opacity` / `stroke_opacity` on that same product Scene. ABI 176 admits
bar/column/histogram `fill_opacity` / `stroke_opacity` on that same product Scene.
ABI 177 admits heatmap `fill_opacity` on that same product Scene.
ABI 193 admits heatmap/hexbin `stroke` / `stroke_width` / `stroke_opacity` on that same product Scene.
ABI 194 admits polar hexbin, custom host reducers, and categorical / `direct_rgba` hexbin on that same product Scene.
ABI 178 admits scatter `fill_opacity` / `stroke_opacity` on that same product Scene.
ABI 179 admits hexbin `fill_opacity` on that same product Scene.
ABI 180 admits triangle_mesh `fill_opacity` / constant stroke paint on that same product Scene.
ABI 195 admits triangle-mesh custom `role` and per-item fill/stroke/width interned from packed XYHP kind 6 on that same product Scene.
ABI 181 admits cartesian area/error_band `curve="smooth"` plus `step` as authored
band step expansion on that same product Scene.
ABI 182 admits triangle_mesh `joined_fill` as one identity PolyFill ring on that
same product Scene.
ABI 183 admits constant ribbon `color2_ch` as XYGR mark-space `dir=right` on that
same product Scene.
ABI 184 admits cartesian unwrapped text `dx`/`dy`/`anchor` as XYAW `wrap=0` on that
same product Scene.
ABI 185 admits labelled cartesian marker `dx`/`dy`/`anchor` as XYAW `wrap=0` on that
same product Scene.
ABI 186 admits cartesian colormap hexbin as a 1×N XYHP plane interned onto
HexCell PolyFills on that same product Scene.
ABI 187 admits cartesian unwrapped text `rotation` as XYAW `wrap=0` (XYAW v2 /
XYLB v6) on that same product Scene.
ABI 188 admits labelled cartesian marker `rotation` as XYAW `wrap=0` on that
same product Scene.
ABI 189 owns heatmap/hexbin cell-fill tessellation eligibility from packed XYTA on that
same product Scene.
ABI 190 intern cartesian per-item two-ended ribbon `color2_ch` from packed XYHP kind 5 on that
same product Scene.
ABI 191 admits constant multi-character scatter `marker_glyph` via XYMG v2 on that
same product Scene.
ABI 192 admits polar painted heatmap inverse-raster as one Scene Image blit on that
same product Scene.
ABI 193 admits heatmap/hexbin `stroke` / `stroke_width` / `stroke_opacity` on that
same product Scene.
ABI 194 admits polar hexbin, custom host reducers, and categorical / `direct_rgba`
hexbin on that same product Scene.
ABI 195 admits triangle-mesh custom `role` and per-item fill/stroke/width interned from packed XYHP kind 6 on that same product Scene.
The explicit `xyg_scene_figure_support_reason` ABI remains for tests.
ABI 106 makes Figure autorange/domain the same way: Python and Node pack
`XYAR` v1 extents and zero-baseline predicates, then call
`xyg_figure_autorange` / `xyg_auto_domain`. Direct-browser WASM compile uses
the same `auto_domain` degenerate pad instead of a host-local ±0.5 fork.
LOD beyond the 1,024-group painter budget, and rich style
exceptions remain compatibility routes. ABI 107 makes Scene CSS→RGBA8 and
per-kind mark style defaults the same way: Python and Node pack `XYMS` v1
kind/opacity/CSS/width literals, then call `xyg_scene_resolve_mark_styles` /
`xyg_css_color_rgba`. ABI 108 makes Scene chrome defaults the same way:
Python and Node pack `XYCH` v1 background/axis CSS, sides, opacities, and
widths, then call `xyg_scene_resolve_chrome_style`. ABI 109 makes
Figure→Scene row packing the same way: Python and Node call
`xyg_scene_pack_trace` with kind/flags/columns and append the returned
56-byte rows. ABI 136 makes product-kind packing the same way: Python and
Node call `xyg_scene_pack_product` with the authored kind plus a canonical
`x`/`y`/`x0`/`y0`/`x1`/`y1`/`base` envelope; Rust maps kind/flags onto
pack-kind and column order. ABI 116 expands primary rule/band/marker annotations the same
way: Python and Node call `xyg_scene_pack_annotation_marks` with packed
scalars plus axis domains. ABI 117 makes figure-compile support the same way:
Python and Node pack `XYFS` observations plus axis ids/keys, then call
`xyg_scene_figure_support_reason`. ABI 118 extends that envelope to v2
per-trace allowlist flags so kind, hidden/per-item, density, dash, rect
extras, joined fill, hex reducer, heatmap colormap, and non-CSS fill
diagnostics cannot drift. ABI 119 moves composition mark ingress into Rust:
Python and Node call `xyg_argsort_stable`, `xyg_histogram_mark_edges`,
`xyg_contour_levels`, and `xyg_hexbin_groups` so line/area/error-band sort,
integer/empty-auto histogram edges, contour isoline spacing, and custom-hex
lattice membership cannot drift. Custom `reduce_C_function` callables stay
host-side over those groups. ABI 120 moves composition `loc="best"` scoring into
Rust: Python and Node call `xyg_legend_normalize` and `xyg_legend_best_loc` so
display-space occupancy, the 4096/512 sample, and the 0.02 tie band cannot drift.
ABI 197 Scene product encode settles authored `loc="best"` from packed XYCL/XYNM
plus XYCF domains; hosts pack the token and encoded XYLG still stores 0..=8.
Compatibility `_legendfit.py` / `resolveLegendBestLoc` still pack ChartView specs.
ABI 121 moves ribbon/curve/rounded-rect tessellation into Rust: Python and Node
call `xyg_ribbon_edge`, `xyg_ribbon_polygon`, `xyg_monotone_tangents`,
`xyg_curve_flatten`, and `xyg_rounded_rect_poly` so bump-X flattening,
Fritsch–Carlson tangents, Hermite polylines, and independent tip/base radii
cannot drift. Hosts still map affine scales.
ABI 122 moves compile-time payload LOD into Rust: Python and Node
call `xyg_payload_tier`, `xyg_payload_visible_needed`, and
`xyg_payload_visible_mask` so M4 vs density vs direct, polar skip,
the strict `>` scatter thresholds, and the log/null keep mask cannot
drift. ABI 204 `xyg_payload_m4_indices` owns remaining line M4 emit
(closed-window ulp, optional nonlinear buckets, polar skip) so Python
and Node cannot drift on first paint or `decimate_view`. Hosts still
map scale coordinates, gather extra columns, and ship the chosen rows.
ABI 205 moves remaining `_emit_*` sampling into Rust: Python and Node
call `xyg_payload_visible_indices`, `xyg_payload_even_indices`, and
`xyg_payload_sample_target_indices` so fused finite/log keep indices,
NumPy int64 linspace stem/errorbar sampling, and density-overlay
`min(1, target/n)` selection cannot drift. ABI 214
`xyg_payload_segment_budget` owns the stem/errorbar count budget
(`max(1024, floor(px_width)*4)`). ABI 215 `xyg_payload_errorbar_indices`
owns even-index expansion across concatenated role groups. Hosts still
gather extra columns and ship the chosen rows.
ABI 123 moves tick-label collision thinning into Rust: Python and Node
call `xyg_scene_tick_label_layout` so auto / hide / rotate / stagger,
the edge-anchor rotate gap, and stride downsampling cannot drift.
Hosts still format label strings and map tick values to pixels.
ABI 124 moves static legend box packing into Rust: Python and Node
call `xyg_legend_box_layout` so column fit, measured ellipsis, and loc /
bbox-to-anchor placement cannot drift. Hosts still resolve CSS font-size
/ em paddings and pack entry strings. Polar `legend_box_*` remapping
stays host-side.
ABI 125 moves text-block measure and cartesian axis rooms into Rust:
Python and Node call `xyg_text_block_measure`,
`xyg_text_block_rotated_extent`, `xyg_y_tick_label_extent`,
`xyg_y_axis_left_room`, `xyg_x_axis_title_room`,
`xyg_x_tick_label_room`, and `xyg_x_tick_label_edge_rooms` so wrap,
rotated extent, and title/tick gutter formulas cannot drift. Hosts still
format `_tick_text`, resolve CSS visibility / tick offsets, and iterate
axes.
ABI 126 moves compatibility static-export padding, title-band, colorbar
extra, right-y, and polar recut into Rust: Python and Node call
`xyg_compat_is_compact`, `xyg_compat_default_padding`,
`xyg_compat_title_wrap_width`, `xyg_compat_title_room`,
`xyg_compat_x_axis_side_room`, `xyg_compat_colorbar_extra`,
`xyg_compat_right_y_room`, `xyg_polar_legend_room`,
`xyg_polar_legend_reserve`, `xyg_polar_label_room`, and
`xyg_recut_polar_plot` so compact gutters, colorbar extras, and polar
disc recut cannot drift. Hosts still iterate axes, format ticks, measure
rooms, resolve CSS visibility, and decide polar legend reservation.
ABI 127 moves the pyplot tight-layout grid solve into Rust: Python and
Node call `xyg_tight_layout_solve` so edge maxima, neighbor gaps, pad
multiples, and `subplots_adjust` fractions cannot drift. Hosts still
measure per-panel chrome, suptitle, figure labels, and outside legends.
ABI 198 moves the remaining static-export combination and tight-layout
figure-edge extras into Rust: Python and Node call
`xyg_compat_combine_plot` and `xyg_tight_layout_figure_extra` so padding,
title-band, colorbar extra, right-y, floors, polar recut, and
suptitle/label/legend extras cannot drift. Hosts still iterate axes,
format ticks, measure rooms, resolve CSS visibility, and decide polar
legend reservation.
ABI 128 moves authored tick-window resolve and filter into Rust: Python
and Node call `xyg_tick_window` and `xyg_tick_window_filter` so linear
vs modular angular containment cannot drift. ABI 199 Scene product encode
filters authored cartesian majors through that window and pairs
`tick_labels` during chrome pack. ABI 200 filters authored cartesian
minors through that same window (`require_finite`). ABI 201 filters polar
theta majors/minors through the modular sector and formats Scene polar
theta labels with `format_angular_tick`. ABI 202 materializes ABI 130
time strftime and polar angular numeric formats onto `XYTL`. Hosts pack
domain tick-kind in XYCF 154–155. ABI 203 runs ABI 123 cartesian collision
at Scene SVG/raster emit. Collision rooms clamp only when compact/authored
pads already fit; overflowing compact pads stay
`XYG_SCENE_UNSUPPORTED_VIEWPORT`. Polar rim auto/hide/rotate/stagger/preserve stay
fail-closed. Invalid ABI 96 grammar still falls
back. Secondary axes stay fail-closed.
Hosts still choose tick families and
map values to pixels on the compatibility `_svg` path. ChartView JS
`_polarAngularTurn` / `_axisTicks` seam filter stays until WASM.
ABI 130 moves Cartesian compatibility tick-label formatting into Rust:
Python and Node call `xyg_tick_format` so linear/log/time/number-spec,
category, and angular defaults cannot drift. Polar tick drawing stays
host-side. Scene product-path authored `tick_labels` pair during chrome
pack (ABI 199). Authored cartesian minors filter during chrome pack (ABI 200).
Scene product encode applies ABI 130 time/angular formats (ABI 202).
Scene cartesian `tick_label_strategy` uses ABI 123 at emit (ABI 203);
polar rim collision stays refused.
ABI 131 moves static polar (theta, r) → screen-pixel projection into Rust:
Python and Node call `xyg_polar_layout`, `xyg_polar_project`, and the polar
visibility-mask helpers so disc layout, projection, and cull predicates cannot
drift on static export. ChartView GLSL `xyPolarPos` stays until WASM; hosts
still own ring/polygon helpers that call native projection. ABI 209 owns
compatibility wedge flatten (`xyg_polar_wedge_points`).
ABI 133 compiles polar Scene v26 line/scatter/area/bar/column/errorbar/heatmap/contour: Python and Node pack
XYPL v1 authoring (`_pack_polar_scene_input` / `packPolarSceneInput`); Rust
owns layout, `polar_project`, `polar_wedge_points` (annular-sector PolyFill),
clip, rings/spokes, and rim tick labels.
Polar encode applies ABI 126 `recut_polar_plot` before `polar_layout` so the
inscribed disc and polar legend gutter match compatibility static export.
Cartesian Scene bytes change only the version u32 at offset 4. Polar
density stays `XYG_SCENE_UNSUPPORTED_POLAR`. Polar heatmap constant-style
lattices tessellate Rects; ABI 192 polar painted heatmap inverse-rasters to
one plot-covering Image. Authored heatmap/hexbin stroke (ABI 193) tessellates
polar painted cells instead of Image blit so cell outlines are representable.
Polar contour
reuses SegmentPair polylines through `polar_project`.
ABI 132 moves first-paint density scatter emit policy into Rust: Python and
Node call `xyg_density_emit_meta`, `xyg_density_grid_path`,
`xyg_density_format_binning`, `xyg_density_pyramid_preflight`, and
`xyg_density_wasm_eligible` so path/binning/WASM/overlay decisions cannot
drift. Hosts still transform axis-scale coordinates, invoke `bin_2d` /
pyramid compose kernels, ship buffers, and assemble the wire spec.
ABI 129 moves Cartesian static-export grid colormap into Rust: Python
and Node call `xyg_colormap_rgba`, `xyg_colormap_rgba_canonical`, and
`xyg_density_rgba` (log-u8 density) so `_lut` stop interpolation cannot
drift on heatmap/density grid export. ABI 206 adds `xyg_colormap_lut`,
`xyg_density_rgba_linear`, and `xyg_paint_effective_rgba` so remaining
compatibility 1D LUT samples, legacy count-grid density, and artist-alpha
compositing cannot drift (#313). ABI 207 `xyg_polar_heatmap_inverse_map`
owns the compatibility polar heatmap gather-after-inverse map so SVG/raster
exporters no longer invert pixels in Python or Node (#283). ABI 208
`xyg_geometry_offset` / `xyg_f32_safe_scale` owns §4/§16 encode offset and
the §19 f32-safe scale so Python `lod.py` and Node `encode.js` cannot drift.
ABI 216 `xyg_scale_pins_offset` owns log-family `pin_zero` admission
(`log`/`symlog`, case-sensitive). Hosts still pack `EncodedColumn` metadata. ABI 209
`xyg_polar_wedge_points` owns compatibility annular-sector flatten so
Python `_svg.polar_wedge_points` and Node `polarWedgePoints` cannot drift;
SVG still emits exact `A` arcs for unrounded wedges. ABI 210
`xyg_hexbin_ring` owns the pointy-top hexagon vertex offsets scaled by cell
pitch so Python `_svg.hexbin_ring` and Node `hexbinRing` cannot drift. ABI 211
`xyg_step_arrays` owns compatibility step/stairs expand so Python
`_svg._step_arrays` and Node `stepArrays` cannot drift. ABI 212
`xyg_marker_path_scale` owns authored-marker pixel vertices
(`out_x = cx + scale * unit_x`, `out_y = cy - scale * unit_y`) so Python
`_svg._authored_marker_path_d` / `_raster` and Node `markerPathScale` cannot
drift; SVG `d=` assembly stays host. ABI 213 `xyg_css_is_functional` /
`xyg_continuous_domain` / `xyg_direct_rgba_admit` owns the `resolve_color`
CSS/numeric split, equal-bound domain pad, and Nx3/Nx4 admit so Python
`channels.resolve_color` and Node `resolveColorChannel` cannot drift; named
colors stay categories. `xyg_heatmap_rgba` keeps its
distinct normalized-scalar remap for other consumers. Hosts still
resolve stop tables, CSS paints, and truecolor RGBA buffers.
ABI 214 `xyg_payload_segment_budget` owns the stem/errorbar count budget
(`max(1024, floor(px_width)*4)`) so Python `_payload._emit_segments` and Node
`_emitSegments` cannot drift. ABI 215 `xyg_payload_errorbar_indices` owns
even-index expansion across concatenated role groups. Hosts still
gather extra columns, and ship the chosen rows.
ABI 216 `xyg_scale_pins_offset` owns log-family `pin_zero` admission
(`log`/`symlog`, case-sensitive) so Python `lod.pins_offset_to_zero` and
Node `pinsOffsetToZero` cannot drift. Hosts still pack `EncodedColumn`
metadata.
ABI 217 `xyg_arrow_geometry` / `xyg_arrow_shaft_points` /
`xyg_arrow_end_decoration` / `xyg_arrow_taper_polygon` /
`xyg_arrow_trim_polyline_end` owns annotation-arrow connectionstyle geometry
so Python `_arrowgeom.py` and Node `arrowGeometry` cannot drift. ChartView
`51_annotations.ts` keeps the same formula until WASM. Hosts still parse
comma-separated `start_offset` / `label_clear` strings.
ABI 218 `xyg_scene_dash_admit` owns Scene dash presets and 2–8 finite length
patterns so Python `_parse_scene_dash` and Node `parseSceneDash` cannot drift.
Invalid comma tokens reject the whole string. Hosts still coerce list vs
string and fail-close empty strings.
ABI 219 `xyg_scene_linecap_admit` owns Scene linecap names so Python
`_parse_scene_linecap` and Node `parseSceneLinecap` cannot drift. Unknown
names and whitespace-only strings reject. Hosts still fail-close empty
strings without calling the kernel.
ABI 220 `xyg_density_overlay_opacity` owns density overlay sample opacity
(`min(authored, 0.55)`; non-finite → `0.55`) so Python `_payload` and Node
`figure.js` cannot drift. Hosts still default omitted opacity to `0.8`.
ABI 221 `xyg_scene_marker_path_admit` owns Scene marker-path contour bounds
(1–32 contours, x/y pairs, `|v| ≤ 0.500001`, ≤ 96 vertices) so Python
`_validated_marker_path` and Node `validateMarkerPath` cannot drift. Hosts
still coerce mappings and fail-close non-numeric contours. Filled contours
shorter than 6 values stay a compile-path extra.
ABI 222 `xyg_scene_annotation_style_admit` owns Scene annotation style-key
allowlists so Python `_annotation_allowed_style` and Node
`annotationAllowedStyle` cannot drift. Hosts still skip markup/typography/
rotation and raise error text.
ABI 223 `xyg_scene_ribbon_color2_classify` owns ribbon two-ended paint class
(absent/solid/gradient/ends/fail) so Python `_classify_ribbon_color2` and
Node `classifyRibbonColor2` cannot drift. Hosts still coerce channels and
pack end RGBA8.
ABI 224 `xyg_scene_tick_label_strategy` owns Scene tick-label strategy names
so Python `_scene_tick_label_strategy` and Node `sceneTickStrategy` cannot
drift. Hyphens become underscores. Unknown names, including empty text, map
to `auto`. Hosts still pick `tick_label_strategy` vs `collision` vs camelCase
keys.
ABI 225 `xyg_scene_tick_anchor` owns Scene tick-label anchor names so Python
`_scene_tick_anchor_code` and Node `anchorCode` cannot drift. `middle` aliases
`center`. Unknown names, including empty text, reject. Hosts still pick
`tick_label_anchor` vs camelCase keys. ABI 123 layout enums stay a separate
throw-on-unknown table.
ABI 226 `xyg_scene_fill_gradient_admit` owns Scene fill-gradient stop admit
(space/dir, 2–8 monotone `t` in `[0, 1]`, `var(` reject, empty/`currentcolor`
→ mark color, RGBA8) so Python `_admitted_fill_gradient_from_fill` and Node
`admitFillGradient` cannot drift. Hosts still coerce fill mappings.
ABI 227 `xyg_scene_parse_linear_gradient` owns CSS `linear-gradient(...)`
parse (cardinal `to` directions, 2–8 resolved stops, nested function commas)
so Python `mark_fill` / `_admitted_fill_gradient_from_fill` and Node
`parseLinearGradient` cannot drift. Hosts still coerce fill mappings, wrap
authoring error text, and run `css_color` on authoring stops. Compile-path
skip-empty split stays extra.
ABI 228 `xyg_scene_rect_extra_flags` owns Scene rect extra-flag pack
(unusable-gradient bit, admitted corner-radius kinds, polar wedge-gap
exception) so Python `_rect_extra_flags` and Node `rectExtraFlags` cannot
drift. Hosts still coerce fill mappings, radius lists, and `wedge_gap`.
ABI 229 `xyg_scene_gradient_dir` owns Scene fill-gradient direction codes
(`down`/`up`/`right`/`left`; unknown/empty → 255; no lowercasing) so Python
`_pack_gradient_spec` / XYSS pack and Node `packGradientSpec` cannot drift.
Hosts still pick `dir` vs missing keys. Compile-path `to bottom` aliases stay extra.
ABI 231 `xyg_scene_gradient_space` owns Scene fill-gradient space codes
(`mark`/`plot`; unknown/empty → 255; no lowercasing) so Python
`_pack_gradient_spec` / XYSS pack and Node `packGradientSpec` cannot drift.
Hosts still pick `space` vs missing keys. XYSS plot-space is `code == 1`.
ABI 230 `xyg_scene_linear_gradient_prefix` owns the CSS `linear-gradient(`
prefix check (trim, lowercase) so Python `_fill_is_gradient_authoring` and
Node `fillIsGradientAuthoring` cannot drift. Hosts still treat dict/object
fills as authoring. Compile-path flag bits stay extra.
ABI 232 `xyg_scene_hexbin_reduce_admit` owns Scene hexbin reduce names
(`count`/`mean`/`sum`/`custom`; unknown/empty reject; no lowercasing) so
Python `_figure_trace_support_flags` and Node `figureTraceSupport` cannot
drift. Hosts still check hexbin kind. Compile-path `HEXBIN_REDUCES` in
`scene_export.rs` stays extra.
ABI 233 `xyg_scene_curve_classify` owns Scene curve names (`linear` → 0,
`smooth` → 1; unknown/empty → 255; trim then lowercase) so Python
`_figure_trace_support_flags` and Node `figureTraceSupport` cannot drift.
Hosts still check kind for `smooth`. Compile-path `curve_smooth` in
`scene_trace_compile.rs` stays extra.
ABI 234 `xyg_scene_marker_glyph_admit` owns Scene marker-glyph UTF-8 admit
(nonempty, no NUL/CR/LF, at most 64 bytes) so Python `_admitted_marker_glyph`
and Node `admittedMarkerGlyph` cannot drift. Hosts still coerce non-strings
and check scatter kind / combined `marker_path`. Compile-path `admit_glyph`
stays extra.
ABI 235 `xyg_scene_kind_admit` owns Scene product-kind names (exact
`scatter`/`line`/`bar`/`column`/`histogram`/`violin`/`box`/`segments`/
`errorbar`/`stem`/`contour`/`box_whisker`/`box_median`/`area`/`error_band`/
`ribbon`/`triangle_mesh`/`hexbin`/`heatmap`; unknown/empty reject; no
lowercasing) so Python `_figure_trace_support_flags` and Node
`figureTraceSupport` cannot drift. Packing-family bits are ABI 236.
ABI 236 `xyg_scene_kind_class` owns Scene packing-family bits (rect/segment/
band/ribbon/polyfill/hexbin/heatmap/stroke/scatter/line; unknown/empty → 0;
no lowercasing) so Python `_scene_v3` pack and Node `scene.js` pack cannot
drift. Hosts still pick channels and pack rows. Smooth-kind eligibility
uses the existing LINE|BAND bits (no new ABI).
ABI 237 `xyg_scene_hexbin_pitch_admit` owns Scene hexbin cell-pitch admit
(finite strictly-positive `dx`/`dy`) so Python `_hexbin_pitch` and Node
XYEP pack cannot drift. Field picking (`hex_dx` vs `dx`) stays host.
Compile-path `hex_pitch` in `scene_trace_compile.rs` stays extra.
ABI 238 `xyg_scene_heatmap_extent_admit` owns Scene heatmap cell-extent
admit (all four finite and `x0 < x1 && y0 < y1`) so Python `_heatmap_extent`
and Node XYEP pack cannot drift. Length==2 and field picking stay host.
Compile-path `heatmap_extent_columns` in `scene_pack.rs` stays extra.
ABI 239 `xyg_scene_heatmap_colormap_admit` owns Scene heatmap colormap
eligibility (OR of already-coerced truecolor / colormap / rgba_grid / rgba
flags) so Python `_heatmap_uses_colormap` and Node `figureTraceSupport`
cannot drift. Field picking and truthy coercion stay host. Kind checks
stay host.
ABI 240 `xyg_scene_heatmap_shape_admit` owns Scene heatmap lattice-shape
admit (finite integer-valued `rows`/`cols` `>= 1`) so Python `_heatmap_shape`
and Node XYEP pack cannot drift. Length==2 stays host. XYTA integer coerce
uses the same kernel (no new ABI). Closes Python `int()` truncation vs Node `Number.isInteger`.
ABI 241 `xyg_scene_scatter_paint_channel_admit` owns Scene scatter paint-plane
channel names (exact `color`/`stroke`/`stroke_width`/`opacity`/`artist_alpha`;
unknown/empty → 0; no lowercasing) so Python `_scatter_packs_paint_plane` and
Node `scatterPacksPaintPlane` cannot drift. Kind, density, and name gathering
stay host.
ABI 242 `xyg_scene_hexbin_colormap_plane_admit` owns Scene hexbin colormap-plane
packing (exact `continuous` plus a values-present flag; unknown/empty → 0; no
lowercasing) so Python `_hexbin_packs_colormap_plane` and Node
`hexbinPacksColormapPlane` cannot drift. Kind checks and field picking
(`color_ch` vs `colorChannel`, `values` vs `metric`) stay host.
ABI 243 `xyg_scene_hexbin_rgba_plane_admit` owns Scene hexbin RGBA-plane
modes (exact `categorical`/`direct_rgba`; unknown/empty → 0; no lowercasing)
so Python `_hexbin_packs_rgba_plane` and Node `hexbinPacksRgbaPlane` cannot
drift. Kind checks, field picking, and RGBA8 packing stay host.
ABI 244 `xyg_scene_mesh_paint_plane_admit` owns Scene mesh paint-plane packing
(exact `triangle_mesh` plus `joined_fill == 0` plus a per-item flag;
unknown/empty → 0; no lowercasing) so Python `_mesh_packs_paint_plane` and
Node `meshPacksPaintPlane` cannot drift. `joined_fill` field picking and
`has_per_item` gathering stay host.
ABI 245 `xyg_scene_item_apply_opacity` owns Scene per-item RGBA8 artist-alpha
replace then opacity multiply (ties-to-even u8 quantize) so Python
`_item_apply_opacity` and Node `itemApplyOpacity` cannot drift. Field picking
stays host.
ABI 246 `xyg_scene_item_widths_admit` owns Scene per-item stroke-width
admit (present values: `len == n` and every value finite `>= 0`; absent:
finite scalar `>= 0`) so Python `_item_widths` and Node `itemWidths` cannot
drift. Field picking and f64 packing stay host.
ABI 247 `xyg_scene_item_fill_t` owns Scene continuous per-item fill unit-t
(domain pair as-is, else finite min/max; zero/non-finite span → zeros;
clip to `[0, 1]`) so Python `_item_fill_rgba8` and Node `itemFillRgba8`
cannot drift. Field picking and colormap lookup stay host.
ABI 248 `xyg_scene_finite_all` owns Scene finite-all admit (empty → `1`)
so Python `_xyep_finite` / heatmap XYEP and Node `exportColumnFinite`
cannot drift. Field picking stays host.
ABI 249 `xyg_scene_gradient_solid_css` owns Scene gradient solid CSS
(first packed RGBA8 stop with alpha `> 0` → `rgb(r,g,b)`; else
`rgb(0,0,0)`) so Python `_gradient_solid_css` and Node `gradientSolidCss`
cannot drift. Field picking stays host.
ABI 250 `xyg_scene_arrays_equal` owns Scene f64 arrays-equal (lengths
match and every pair is IEEE `==`; empty equal; NaN never equals) so
Python companion x1/y1 match and Node `exportArraysEqual` cannot drift.
Field picking and null checks stay host.
ABI 251 `xyg_clip_quantize_u8` owns unit-f64 clip-to-`[0, 1]` × 255
ties-to-even u8 quantize (NaN → 0) so Python `_quantized_rgba8` /
`channels.ship_color_channel` and Node `clipQuantizeU8` /
`resolveColorChannel` / `channelEndRgba8` cannot drift. Field picking
stays host.
ABI 252 `xyg_scene_constant_color_admit` owns Scene constant-color admit
(`0` fail, `1` style fallback, `2` channel constant) so Python
`_constant_color` and Node `constantMarkColor` cannot drift. Ribbon-fail
and field picking stay host.
ABI 253 `xyg_scene_hidden_or_per_item_admit` owns Scene hidden-or-per-item
admit (`hidden || (has_per_item && !density_aggregates)`) so Python
`_figure_trace_support_flags` and Node `figureTraceSupport` cannot drift.
Field picking stays host.
Python `colormap_lut_rgba8` and Node `colormapLutRgba8` sample 256
unit-t texels through ABI 206 `xyg_colormap_lut` then host-pack alpha
255 so the density LUT cannot drift on half-up vs ties-to-even.
Python `quantize_unit_u8` / `_quantized_lut_idx` and Node
`quantizeUnitU8` / `resolveDensityBinColors` normalize through
`xyg_normalize_f32` (nonfinite → 0) then ABI 251 `xyg_clip_quantize_u8`.
Equal or non-finite domain stays a host zero-span short-circuit.
Python `palette_rows_rgba8` quantizes `css_check` 0-1 channels through
ABI 251 `xyg_clip_quantize_u8`. Browser-only palette status and per-index
substitute stay host.
Python `_svg._paint_rgba8` resolves CSS paints through `xyg_css_color_rgba`,
matching `_raster._parse_color` and Node `cssColorRgba8`.
Python `resolved_hex_paint` / `_resolved_rgb` quantize `css_check` 0-1
channels through ABI 251 `xyg_clip_quantize_u8`. Browser-only rejection stays host.
Python `resolve_style_channel` admits finite arrays through ABI 248
`xyg_scene_finite_all`. Bounds checks stay host.
SVG `_rgb_css` formats 0-1 RGB through ABI 251 `xyg_clip_quantize_u8`.
SVG authored-scatter marker RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster scatter RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster mesh/hexbin fill RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster rectangle style RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster segment stroke RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster mesh stroke RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster ribbon fill RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster ribbon match-fill edge RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Node `meshHasPerItem` uses `perItemChannelNames` (same as Python `has_per_item_channels`) for ABI 244.
Node `scatterPaintChannelNames` uses `perItemChannelNames` (same as Python `per_item_channel_names`) for ABI 241.
Node hexbin colormap-plane packing uses `channel.values` (same as Python); `trace.metric` is not a values fallback.
Node empty kind uses `|| "mark"` (same as Python `or "mark"`).
Node `figureTraceSupport` does not fail-close `style.smooth`; curve names stay ABI 233.
Node `itemWidths` fail-closes a present `stroke_width` channel without values (same as Python).
Node `itemApplyOpacity` fail-closes a present opacity/artist_alpha channel without values (same as Python).
Node missing scatter kind uses `|| ""` (same as Python); it is not defaulted to `"scatter"`.
Node `fillIsGradientAuthoring` rejects arrays (same as Python dict-only).
Node `rectExtraFlags` treats only mapping fills as gradient-fail (same as Python dict-only).
Node `admittedMarkerGlyph` rejects non-strings (same as Python `isinstance(..., str)`).
Node `packXyTaColormap` uses `style.colormap` only (same as Python); `trace.colormap` / `colormapStops` are not fallbacks.
Node hexbin XYTA colormap uses `channel.colormap` only (same as Python); `style.colormap` is not a fallback.
Node XYHF heatmap/density colormap uses `style.colormap` only (same as Python); `trace.colormap` / `colormapStops` are not fallbacks.
Node `constantMarkColor` uses `color_ch.constant` only (same as Python); string channels, `channel.color`, and `trace.color` are not fallbacks.
Node `channelConstantCss` uses `channel.constant` only (same as Python); string channels and `channel.color` are not fallbacks.
Node `channelEndRgba8` constant paint uses `channel.constant` only (same as Python); string channels and `channel.color` are not fallbacks.
Node `sourceColorCss` uses `color_ch` only (same as Python); `trace.color` is not a source-channel fallback.
Node `resolveColorChannel` constant CSS uses `.constant` (same as Python `ColorChannel`); `composeRibbon` writes `color_ch` / `color2_ch`.
Node `color2Channel` uses `color2_ch` only (same as Python); `color_target` / `colorTarget` are not Scene-pack fallbacks.
Node `itemFillRgba8` uses `color_ch` only (same as Python); `trace.color` is not a fill-channel fallback.
Node `scatterPaintChannelNames` uses `color_ch` only (same as Python); `trace.color` is not a per-item color channel.
Node `scatterHasNonConstantColor` uses `color_ch` only (same as Python); `trace.color` is not a non-constant-color fallback.
Node `resolveDensityBinColors` uses `color_ch` only (same as Python); `trace.color` is not a density-bin color channel.
Node `scatterHasNonConstantColor` ignores `style.color_channel` (same as Python); only `color_ch` is a non-constant-color channel.
Node `scatterPaintChannelNames` ignores `style.color_channel` / `stroke_channel` / `size_channel` (same as Python); per-item extras come from `style_channels`.
Node `resolveDensityBinColors` ignores `style.color_channel` (same as Python); only `color_ch` is a density-bin color channel.
Node XYMS mark color uses `style.color` only (same as Python `_constant_color` style fallback); `trace.color` is not a mark-color fallback.
Node XYTC style color uses `style.color` only (same as Python); `trace.color` is not a packed-color fallback.
Node XYTC constant paint uses `channel.constant` only (same as Python); `channel.color` is not a packed-constant fallback.
Node density-blit observation uses `scatterUsesDensity` (same as Python `use_density`); `style.color_channel` is not a per-item density extra.
Node XYTC color_ch packing ignores string channels (same as Python object-only); only a channel object packs COLOR_CH.
Node `scatterHasNonConstantColor` uses `channel.constant` only (same as Python); `channel.color` is not a packed-constant stand-in.
Node XYTC `COLOR_CH_CONSTANT` packs whenever `channel.constant` is set (same as Python); `mode === "constant"` is not a gate.
Node XYMS mark color uses `constantMarkColor` / ABI 252 (same as Python `_constant_color`); `style.color` is the code-1 fallback only.
Node `scatterPerItemChannels` ignores `style.color_channel` / `size_channel` / `stroke_channel` (same as Python `has_per_item_channels`); only `*_ch` presence counts.
Node `scatterPerItemChannels` is mode-based like Python `has_per_item_channels`; a constant `color_ch` is not per-item.
Node `channelEndRgba8` ignores array and typed-array channels (same as Python object-only); only `null` and mode objects pack.
Node `channelEndRgba8` categorical paint uses `DEFAULT_PALETTE` when palette is empty (same as Python); fallback CSS is not a missing-slot stand-in.
Node `packXyTaColormap` stop bytes require RGB rows like Python `_colormap_stop_bytes`; a flat or RGBA list packs empty stops.
Node `xyHfColormap` stop bytes require RGB rows like Python `_colormap_stop_bytes`; a flat or RGBA list packs empty stops.
Node `packXyTaRgbaGrid` stacks flattened planes like Python `_pack_xyta` `rgba_grid`; nested 2D index fallback is not a plane layout.
Node heatmap `trace.rgba` stores a flat uint8 buffer; `packXyTaRgba` packs that buffer like Python `_pack_xyta` and does not unwrap nested `.rgba`.
Node heatmap and density Scene packing is XYTA-only like Python `_pack_xyta`; unused XYHF paint-plane helpers are not a second plane layout.
Node `packXyTaGrid` flattens heatmap `grid` like Python `_pack_xyta` (`plane.values` or plane); nested length indexing is not a grid layout.
Node `rectFiniteSel` drops nonfinite rectangle rows through `validIndicesF64` like Python `_rect_finite_sel`; NaN never reaches vertex buffers (§19).
Node `packXyTa` density fill opacity uses `style.fill_opacity` only like Python `_pack_xyta`; `fillOpacity` is not a fill-opacity key.
Node XYTC fill opacity uses `style.fill_opacity` only like Python `_pack_xytc`; `fillOpacity` is not a fill-opacity key.
Node XYTC stroke opacity uses `style.stroke_opacity` only like Python `_pack_xytc`; `strokeOpacity` is not a stroke-opacity key.
Node XYTC line opacity uses `style.line_opacity` only like Python `_pack_xytc`; `lineOpacity` is not a line-opacity key.
Node XYTC stroke width uses `style.stroke_width` only like Python `_pack_xytc`; `strokeWidth` is not a stroke-width key.
Node XYTC line width uses `style.line_width` only like Python `_pack_xytc`; `lineWidth` is not a line-width key.
Node XYTC size uses `style.size` only like Python `_pack_xytc`; `diameter` is not a size key.
Node XYTC line color uses `style.line_color` only like Python `_pack_xytc`; `lineColor` is not a line-color key.
Node XYTC joined fill uses `style.joined_fill` only like Python `_pack_xytc`; `joinedFill` is not a joined-fill key.
Node XYTC stroke perimeter uses `style.stroke_perimeter` only like Python `_pack_xytc`; `strokePerimeter` is not a stroke-perimeter key.
Node XYTC COLOR_CH packing uses `color_ch` only like Python `_pack_xytc`; `colorChannel` is not a packed-channel fallback.
Node XYTC size_ch packing uses `size_ch` only like Python `_pack_xytc`; `sizeChannel` is not a packed-channel fallback.
Node XYEF stroke-width-only observation uses `style.stroke_width` only like Python; `strokeWidth` is not an observation key.
Node `meshJoinedFill` uses `style.joined_fill` only like Python `_mesh_joined_fill`; `joinedFill` is not a joined-fill key.
Node XYEF joined-fill observation uses `style.joined_fill` only like Python; `joinedFill` is not an observation key.
Node `constantMarkColor` uses `color_ch` only like Python `_constant_color`; `colorChannel` is not a source-channel fallback.
Node `sourceColorCss` uses `color_ch` only like Python `_trace_source_color_css`; `colorChannel` is not a source-css fallback.
Node `scatterHasNonConstantColor` uses `color_ch` only like Python; `colorChannel` is not a non-constant-color fallback.
Node `classifyRibbonColor2` source-constant CSS uses `color_ch` only like Python `_classify_ribbon_color2`; `colorChannel` is not a source-constant fallback.
Node `itemFillRgba8` uses `color_ch` only like Python `_item_fill_rgba8`; `colorChannel` is not a fill-channel fallback.
Node `resolveDensityBinColors` uses `color_ch` only like Python; `colorChannel` is not a density-bin color channel.
Node `hexbinPacksColormapPlane` uses `color_ch` only like Python `_hexbin_packs_colormap_plane`; `colorChannel` is not a colormap-plane fallback.
Node `hexbinCellRgba8` uses `color_ch` only like Python `_hexbin_cell_rgba8`; `colorChannel` is not a cell-paint fallback.
ABI 110 makes primary legend framing the same way: Python
and Node call `xyg_scene_pack_legend` with loc/flags/paints/labels.
ABI 111 makes primary colorbar framing the same way: Python and Node call
`xyg_scene_pack_colorbar` with domain/stops/ticks/title.
ABI 112 makes primary annotation framing the same way: Python and Node call
`xyg_scene_pack_annotations` with typed row meta plus concatenated labels.
ABI 113 makes closed-subset SVG→PDF the same way: Python `_pdf.svg_to_pdf` /
`_native.svg_to_pdf` and Node `svgToPdf` call `xyg_svg_to_pdf`; Rust owns
path lowering, Helvetica metrics, ExtGState/shading/image embedding, and
deterministic object numbering. ABI 114 makes static JPEG/WebP the same way:
Python `_jpeg.encode` / `_webp.encode` / `_native.encode_jpeg` /
`_native.encode_webp` and Node `encodeJpeg` / `encodeWebp` call
`xyg_encode_jpeg` / `xyg_encode_webp`; Rust owns YCbCr 4:4:4, Annex K
tables, the libjpeg quality curve, and VP8L simple-lossless packing.
ABI 115 makes static PNG the same way: Python `_png.encode` /
`_png.png_truecolor` / `_native.encode_png` and Node `encodePng` call
`xyg_encode_png`; Rust owns filter-0 scanlines, indexed-palette
selection, `tRNS`, and zlib IDAT. Polar painted heatmap inverse-raster is
Scene-owned (ABI 192). ABI 193 admits heatmap/hexbin `stroke` / `stroke_width` /
`stroke_opacity` on XYMS. ABI 194 admits polar hexbin, custom host reducers, and
categorical / `direct_rgba` hexbin on HexCell PolyFills. ABI 195 admits triangle-mesh custom `role` and per-item fill/stroke/width interned from packed XYHP kind 6. ABI 196 intern scatter per-item fill/stroke/width/opacity from packed XYHP kind 7. LOD beyond 10,000 tessellated cells, and rich style
exceptions remain compatibility routes.
Scalar colormap and truecolor heatmaps compile through `HeatmapPainted` on Python and Node.
ABI 99 gives both composition hosts one compact grouped box ingress. Hosts pack
the same f64 values/offsets/centers and literal options; Rust returns typed
active-group IDs, fixed 25-f64 group records, monotone outlier offsets, and
fixed 3-f64 outlier records. Vertical and horizontal fixtures compile to
identical Python/Node Scene bytes and feed SVG, raster, and browser consumers.
Host grouping/coercion and literal styles remain seams; Tukey policy, geometry,
stable ordering, deterministic outlier placement, and bounds do not.
Scene v13 covers solid chart/plot backgrounds, authored
  Cartesian side/visibility/major-minor geometry and paint, and a bounded
  single-column primary static legend for named constant-style traces, plus a
  bounded literal RGBA banded colorbar (right/bottom). Scene v19 evolves that
  colorbar to `XYCB` v2: hosts may frame bounded major values and a minor-tick
  request, while Rust resolves labels and geometry in `XYCT` v1 for all three
  consumers, and
  rule, band, marker annotations, bounded Rust-anchored attached labels, and
  bounded Rust-projected literal straight arrows, and bounded Rust-resolved
  Cartesian callouts. Scene v20--v23 add fixed Rust-resolved literal label
backgrounds and bounded literal label-box borders; padding, radius, wrapping,
rich markup, custom typography, and advanced text layout remain unsupported.
Extra legends, named/advanced colorbars, other deferred
  annotation forms, custom
  tick strings, and advanced text layout remain loud unsupported boundaries.
  ABI 84's versioned support predicate makes the
  ordered `XYG_SCENE_UNSUPPORTED_*` reason Rust-owned and byte-identical across
  Python and Node instead of allowing host-specific fallback policy. Both host
  compilers route real polar, custom-font, CSS/class, and normalized gradient
  representations through it and reject non-u32 request versions before FFI
  coercion. See
[scene-ir.md](scene-ir.md).
Per-item scatter size/symbol stay fail-closed; density/LOD remain explicit compatibility exceptions. Python custom glyph/path markers and other
not-yet-migrated customization remain explicit compatibility exceptions until
bounded path, text, and chrome records land.

ABI 96 additionally admits the bounded primary Cartesian numeric format
grammar `<prefix>(,).N[f|%]<suffix>` with precision `N` from 0 through 100 on
linear, log, and symlog axes without a Scene-version change. Python and Node
frame the authored strings in the same
versioned `XYAF` authoring envelope; Rust alone parses the grammar, resolves
labels and gutters, and emits existing explicit-major plus `XYTL` bytes. Shared
fixtures pin exact Python/Node formatted Scene bytes and the Node forwarding of
scale kind, symlog constant, and log nonpositive policy. Explicit authored
labels win, invalid grammar retains default labels, and legacy raw `XYAD`
annotation input remains accepted. WASM ABI 23 adds a bounded, atomic Worker
foundation for Rust-owned f64 linear/log/symlog/category/angular/UTC-time
values, steps, and formatting. Attached automatic, authored-value, and
authored-empty primary Cartesian linear/log/symlog/category/UTC-time ChartView
axes and eligible ChartView colorbars already use that lifecycle via
`attachWasmTicks`. Hosted `to_html()`, notebook widgets, and Reflex `XYChart`
attach when they pass explicit Worker/WASM URLs; srcdoc notebooks and
secondary/polar paths remain frozen deferred compatibility keepers outside the
claimed M2 subset.

For the migrated subset, public Python SVG and native PNG now use the Rust
Scene consumers and public PDF consumes their Rust SVG. The shared predicate
chooses the compatibility renderer only before Scene compilation for an
explicit unsupported feature, an export-only background override, or a valid
viewport too small for bounded Scene chrome. A malformed input or Rust
consumer failure remains an error rather than a fallback signal.
`public_static_export` is now the only optional Python product-route selector;
the older format-specific `try_public_*` adapters have been retired. The
support predicate itself is ABI 105 `xyg_scene_public_export_reason`; hosts
only pack literal figure metadata. The Python public router and facet SVG/
raster paths reuse the predicate's compiled Scene instead of compiling a second
batch for the Rust SVG/raster/PDF consumers. Format dispatch is ABI 164
`xyg_scene_static_export`. Explicit `figure_svg` /
`figure_raster_commands` callers still compile on demand. ABI 106 `xyg_figure_autorange` owns the
product domain/padding/polar/zero-baseline decisions from the same packed
extents both hosts already had. ABI 107 `xyg_scene_resolve_mark_styles` /
`xyg_css_color_rgba` own per-kind fill/stroke defaults and CSS→RGBA8 so named
colors cannot drift. ABI 108 `xyg_scene_resolve_chrome_style` owns the 200-byte
Scene chrome style input so default axis/grid/tick/label RGBA, default widths,
and `grid_opacity` scaling of the default grid color cannot drift. ABI 109
`xyg_scene_pack_trace` owns Figure→Scene row packing so record kinds,
stable-id splitting, expansion modes, ribbon/triangle doubling, heatmap
lattice framing, and finite-coordinate rejection cannot drift. ABI 136
`xyg_scene_resolve_pack_kind` / `xyg_scene_pack_product` own product-kind
mapping and the canonical host column envelope so pack-kind dispatch cannot
drift. ABI 147 `xyg_scene_pack_product_facts` owns flags, `step_mode`, and
extra0/extra1 from packed XYPK v1 so cartesian-vs-polar smooth and painted
heatmap dispatch cannot drift. ABI 148
`xyg_scene_pack_annotation_facts` owns wrap vs text vs arrow vs callout vs
rule/band/marker routing from packed XYAF v1. ABI 149
`xyg_scene_pack_heatmap_facts` owns XYHP kind routing from packed XYHF v1.
ABI 150
`xyg_scene_pack_scene_extras` owns XYDS/XYLC/XYMP/XYGR/XYMG layout, concat order,
omit-empty, and XYEX wrapping from packed XYSS v1 plus framed XYPL/XYHP.
ABI 151
`xyg_scene_pack_density_grid` owns Scene density `bin_2d` / `density_log_u8`
/ optional mean-color from packed columns.
ABI 152
`xyg_scene_pack_public_export` owns XYEP layout, kind/step/annotation codes,
and flag derivation from packed XYEF v1. The public-export predicate also
owns the PolyFill group budget, including companion traces that share the
browser painter's 1,024-group ceiling.
ABI 153
`xyg_scene_pack_figure_chrome` owns plot layout, chrome-style resolve, legend
loc default/allowlists (empty authored loc is fail-closed), colorbar
flags/framing, XYTL tick-label framing, and the 200-tick axis bound from
packed XYCF v1. Layout errors stay plot-layout diagnostics so the
public-export predicate can remap them to `XYG_SCENE_UNSUPPORTED_VIEWPORT`.
ABI 154
`xyg_scene_pack_trace_compile` owns per-trace Scene compile policy from
packed XYTC v1 so opacity, symbol, color, dash, linecap, marker path,
diameter, legend kind, step, curve-smooth, stroke-perimeter, hex pitch,
fill-gradient admission, and XYMS resolve cannot drift.
ABI 155
`xyg_scene_pack_trace_attach` owns heatmap/density attach policy from
packed XYTO plus XYTA v1 so shape/finite fail-closed checks, XYHF remainder
order, density skip, density XYHF flags, fact bits, density zeroing, and
domain rewrite cannot drift.
ABI 156
`xyg_scene_pack_trace_rows` owns XYPK construction, scatter-only
symbol/diameter, density domain-endpoint column rewrite, and
`pack_product_facts` from packed XYTT plus XYCL v1 so product rows cannot
drift.
ABI 157
`xyg_scene_pack_trace_sidecars` owns legend-name gating, heatmap-vs-density
plane selection, and per-trace style/dash/marker/gradient/plane extraction
from packed XYTT plus XYNM v1 so sidecars cannot drift.
ABI 158
`xyg_scene_pack_style_sidecars` owns XYSS dash/linecap/marker/gradient
record construction from packed XYSD plus XYAO v1 so style sidecars cannot
drift.
ABI 159
`xyg_scene_splice_annotations` owns annotation style/row splice and XYAD
extract from packed product rows plus XYSD plus XYAO v1 so batch-encode
arrays cannot drift.
ABI 160
`xyg_scene_encode_assembled` owns assembled Scene encode from packed XYAS
plus XYCC plus extras so XYAS/XYCC unpack, gutter widening, and SceneBatch
encode cannot drift.
ABI 161
`xyg_scene_pack_figure_chrome_from_sidecars` owns legend paints from packed
XYSD and `xyg_scene_pack_scene_extras_from_sidecars` owns XYHP wrapping from
XYSD planes so sidecar unpack cannot drift.
ABI 162
`xyg_scene_encode_assembled_from_sidecars` owns XYCC packing, extras packing,
and viewport/axis scalars from packed XYAS plus XYCF plus XYSD plus polar plus
XYSS so chrome/extras packing cannot drift.
ABI 163
`xyg_scene_encode_product` owns product-path compile, attach, sidecar, row,
annotation, style-sidecar, splice, and assembled encode from packed XYTC plus
XYTA plus XYNM plus XYCL plus XYAF plus XYCF plus polar so orchestration
cannot drift.
ABI 165 extends that same entry so packed XYFS figure-compile support cannot
drift either; empty XYFS skips the probe.
ABI 116
`xyg_scene_pack_annotation_marks` owns rule/band/marker domain expansion
so tags and opposite-axis spanning cannot drift. ABI 117
`xyg_scene_figure_support_reason` owns figure-compile support so feature
mapping, the primary x/y axis set, and the Scene axis-key allowlist cannot
drift. ABI 118 extends `XYFS` to v2 per-trace flags so kind and mark
allowlists cannot drift either. ABI 110
`xyg_scene_pack_legend` owns primary XYLG legend framing so header layout,
text offsets, and bounded-text rejection cannot drift. ABI 111
`xyg_scene_pack_colorbar` owns primary XYCB v2 framing so header layout,
stop/tick tables, domain-span checks, and bounded-text rejection cannot
drift. ABI 112
`xyg_scene_pack_annotations` owns primary XYAD framing so XYAT/XYAL/XYAR/
XYAC/XYAW table layout, version selection, the XYAD envelope, and
bounded-text rejection cannot drift. Explicit Scene diagnostics and consumers
remain available through `scene_export_support_reason` /
`sceneExportSupportReason`, `figure_scene`, `figure_svg`, and
`figure_raster_commands`. Python SVG/raster and pyplot automatic tick requests
also share one `_svg.axis_ticks` adapter that calls `xyg_scene_axis_ticks`
directly for every family; no per-family Python ladder adapter remains.

The public literal `x_axis`/`y_axis` `ticks=False` and `text=False` switches
are inside that migrated static subset: Rust preserves the independent
semantics in all three consumers (major-tick geometry versus tick-label/title
paint). This does not widen the boundary to rich tick strings, wrapping,
custom fonts, CSS/classes, theme-driven chrome, or arbitrary annotation text.
Scene static custom `font-family`, chart/theme CSS, and `class_name` are the
bounded fail-closed product contract (#288): `XYG_SCENE_UNSUPPORTED_CUSTOM_FONT`
and `XYG_SCENE_UNSUPPORTED_BROWSER_CSS`. Default-font figures without those
observations use Scene consumers, not `_svg.to_svg` / `_raster`. Live browser
widgets still apply CSS. CSS-room measurement of a second face stays #297.
Unresolved mark-fill `var()` / theme CSS gradients are the bounded fail-closed
Scene-static contract (#289): `XYG_SCENE_UNSUPPORTED_GRADIENT`. Literal
`linear-gradient(...)` with resolvable CSS colors stays ABI 146 Scene XYGR.
Live browser widgets still resolve `var()`.

### Contracts (MUST)

- **Rust owns decisions for all marks.** Hosts are thin: coerce inputs, schedule
  progressive work, attach transport, and assemble figure specs. They MUST NOT
  reimplement layout, LOD tiering, channel encode, or other buffer-affecting
  decisions in Python or TypeScript.
- **Browser TypeScript never reimplements layout / LOD / encode** for the
  product path. The client applies Rust-produced live §29 offset-f32/u8 buffers and runs screen-bounded
  interaction; force ticks and LOD plans stay off the browser main thread’s
  decision path (native Rust and the same Rust compiled to WASM by the #59
  foundation).
- **Isolation:** the Node package MUST NOT use browser-only APIs (`window`,
  `document`, WebGL, DOM). The browser client MUST NOT import `koffi`,
  `node:fs`, or other Node-only modules.
- **Same figure spec + §29** across Python and Node for the same inputs; the
  browser client is the **shared renderer** for both.
- **Notebooks stay first-class:** `show()` / anywidget / `to_html()` MUST NOT
  regress as Node or graph work lands. Python notebook UX remains a primary
  product surface, not a legacy path.

See [dual-host-parity-matrix.md](dual-host-parity-matrix.md) §0 and the
`runtimes` section of [`dual-host-parity.json`](dual-host-parity.json).
The exhaustive per-file application of these rules is
[ownership-audit.md](ownership-audit.md).

---

## 1. Goal

| Layer | Shared across Python and Node |
|---|---|
| Rust viz `cdylib` C ABI | All kernels (existing marks + `xyg_graph_*` + `xyg_temporal_*`); **u64** graph element indices; **i64** UTC micros for temporal columns |
| Wire / §29 buffers | Identical binary payloads for the same figure spec |
| JS render client | One bundled WebGL client (`@curatelabs/xyg`: `index.js` / `standalone.js`); Python copies into the wheel |
| Public chart semantics | Same mark kinds, options, defaults, layout/LOD decisions |
| Temporal foundation (#43) | Same `TemporalColumn` / interval visibility for identical Arrow-like fixtures ([temporal.md](temporal.md)) |
| Temporal controller (#44) | Same `TemporalController` commands, exact u64 stable-ID replacement selection, revisions, atomic apply, and coordination reject rules ([temporal-controller.md](temporal-controller.md)) |

Host-only differences are idiomatic (NumPy/pandas/Arrow vs TypedArrays;
notebook/Reflex vs Node embed / VS Code webview attach). Names and defaults
match.

The direct-browser `XygWasmTemporalController` submits packed raw i64/u64
commands to that same Rust state machine. TypeScript owns only the coalesced
clock, explicit event transport, keyboard/focus surface, and ARIA presentation.
Python lists, Node `BigUint64Array`s, and browser `BigInt[]` values all lower to
the same Rust-canonical sorted/deduplicated selection; no host truncates or
reorders the result.

---

## 2. Placement rule (Rust owns decisions)

| Lives in | Examples |
|---|---|
| **XYG Rust (shared)** | Display layouts (including today’s Python-only ones such as Sankey), graph adjacency/position buffers, channel resolution, decimation, LOD aggregates, layout/LOD **decisions**, thresholds that change buffers, progressive layout ticks, canonical temporal columns, interval/event visibility, and UUID-stable temporal graph membership/interaction state |
| **Host (Python *or* Node)** | Public API shapes, idiomatic ingest coercion (list/NumPy/TypedArray → pointers), error message text, transport attach — **no** second layout/algorithm/encode/decision path |
| **Browser client** | WebGL draw, hit-test, pan/zoom/select/drag gestures applying uploaded buffers; playback clocks submit revisioned temporal commands to Rust (#44+) |

Temporal graph native hosts follow the same boundary: Python and Node accept
UUID/time buffers, expose lifecycle methods, and return Rust-produced
visibility plus frozen provenance. They do not calculate membership, endpoint
closure, interaction persistence, revision ordering, or work budgets. Node
retains revisions and timestamps as exact `bigint`; Python performs bounded
integer conversion before the C ABI call.

The direct browser uses the same engine through WASM ABI 9 `XYTG`/`XYTF`
frames. Rust emits visible UUID membership and remapped topology before layout;
the TypeScript coordinator only owns transfer, latest-wins cancellation,
stale-reply rejection, and disposal.

Graph **analysis algorithms** (paths, centrality, communities, Cypher, …) are
not owned here — they live in GraphForge (and similar peers). This charting
stack plots their outputs; it does not reimplement them.

Node must not reimplement layouts or mark geometry in TypeScript. The browser
client must not grow a parallel “JS layout/LOD” product path.

---

## 3. Requirements

- **REQ-HOSTPARITY-0 (MUST).** The product exposes exactly the three runtime
  surfaces in §0 (Python host, Node host, browser client). VS Code extensions
  consume `packages/xy-node` (`@curatelabs/xyg-node`); they are not a separate runtime stack.
- **REQ-HOSTPARITY-0b (MUST).** Notebook UX (`show()`, anywidget, `to_html()`)
  remains first-class on the Python host and MUST NOT regress.
- **REQ-HOSTPARITY-0c (MUST).** Node bindings MUST NOT depend on browser-only
  APIs; the browser client MUST NOT import Node-only modules (`koffi`,
  `node:fs`, …).
- **REQ-HOSTPARITY-1 (MUST).** One XYG Rust C ABI serves Python (ctypes) and
  Node (Koffi, which uses Node-API internally). Both low-level declaration sets
  are generated from the typed Rust contract; `ABI_VERSION` bumps apply to both
  loaders without making XYG a PyO3 or napi-rs extension.
- **REQ-HOSTPARITY-1b (MUST).** **Rust owns decisions:** chart/graph behavior
  that affects buffers, layout, encodings, or recorded LOD/layout decisions is
  implemented in Rust. Hosts MAY validate and coerce inputs but MUST NOT own a
  parallel implementation of that behavior.
- **REQ-HOSTPARITY-2 (MUST).** For every public chart type, Python and Node
  produce the same figure spec shape and §29 buffers for the same inputs.
  Graph is the core feature; **all** chart types ship in MVP on both hosts with
  the same feel/speed.
- **REQ-HOSTPARITY-2b (MUST).** Non-graph marks retain the same composition
  quality and performance bar (Rust kernels, binary transport, WebGL). Graph
  work MUST NOT regress them or leave them second-class.
- **REQ-HOSTPARITY-2c (MUST).** Graph ingest helpers (including any GraphForge
  primary path) MUST NOT be the only way to build a graph chart on either host.
  XYG-native column/sequence formats from
  [graph-fork-requirements.md](graph-fork-requirements.md) REQ-API-3 remain
  available with the same semantics on Python and Node.
- **REQ-HOSTPARITY-2d (MUST).** Python `from_graphforge_tables()` and Node
  `fromGraphForgeTables()` pass canonical UUID buffers through the same ABI
  `GraphProjection` handle. Hosts validate UUID representation before creation;
  Rust validates duplicate identities, topology, and dense endpoint/parent
  mapping to `u64`. Hosts retain typed attributes and provenance on
  `GraphData`. `graph()` / `composeGraph()` accept GraphForge tables or a ready
  `GraphData` and attach `tooltip_rows` / identity meta for hover, encodings,
  and export. The browser never imports Arrow or receives UUIDs as JSON
  numbers. Native-vs-WASM projection parity is covered by the #59 foundation.
- **REQ-HOSTPARITY-2e (MUST).** Graph node/edge `tooltip_rows` and continuous
  size/color channels ship with the same wire shape on Python and Node
  (`tooltip_rows` length-checked against geometry; Node `shipScalar` mirrors
  Python `_ship_channels` continuous size). See
  [graph-mark.md](graph-mark.md) encodings table.
- **REQ-HOSTPARITY-3 (MUST).** The browser client is shared; hosts only differ
  in transport attachment. The same `js/src` → `@curatelabs/xyg`
  (`packages/xy-client/dist/{index,standalone}.js`) client serves Python
  notebooks (anywidget, via the wheel **copy**), HTML export on either host,
  Node-served pages, and VS Code webviews. `58_graph.ts` is an optional
  enhancement (neighborhood hover); all wire marks paint without it. The client draws uploaded §29 buffers and MUST NOT
  reimplement layout/LOD/encode for the product path.
- **REQ-HOSTPARITY-4 (MUST).** Graph viz is the core dual-host feature surface
  ([graph-fork-requirements.md](graph-fork-requirements.md)); other marks are
  first-class in the same MVP.
- **REQ-HOSTPARITY-5 (MUST, done).** [rust-engine.md](rust-engine.md) and the
  dossier's identity preamble state “Rust owns decisions” directly as the XYG
  rule; no conflicting “Python owns decisions” guidance remains in force
  (upstream text survives only as clearly-marked provenance).
- **REQ-HOSTPARITY-6 (MUST, MVP).** Remove Python host-only layout/encode
  shenanigans for MVP: remaining twins are `_payload` emit orchestration and
  `_scene_v3` pack. Sankey placement already lives in `xyg_sankey_layout`;
  encode offset/scale is ABI 208; polar wedge flatten is ABI 209; hexbin ring
  offsets are ABI 210; step/stairs expand is ABI 211; authored marker-path
  scale is ABI 212; color CSS/numeric split, domain pad, and direct RGBA admit
  are ABI 213; stem/errorbar count budget is ABI 214; errorbar role-block
  expand is ABI 215; log-family pin_zero admission is ABI 216;
  annotation-arrow geometry is ABI 217; Scene dash admit is ABI 218;
  Scene linecap admit is ABI 219; density overlay opacity is ABI 220;
  Scene marker-path admit is ABI 221;   Scene annotation style admit is ABI 222;
  Scene ribbon color2 classify is ABI 223;
  Scene tick-label strategy admit is ABI 224;
  Scene tick-label anchor admit is ABI 225;
  Scene fill-gradient admit is ABI 226;
  Scene linear-gradient CSS parse is ABI 227;
  Scene rect extra-flag pack is ABI 228;
  Scene fill-gradient direction pack is ABI 229;
  Scene linear-gradient CSS prefix is ABI 230;
  Scene fill-gradient space pack is ABI 231;
  Scene hexbin reduce admit is ABI 232.
  Scene curve-name classify is ABI 233.
  Scene marker-glyph admit is ABI 234.
  Scene product-kind admit is ABI 235.
  Scene packing-family classify is ABI 236.
  Scene hexbin cell-pitch admit is ABI 237.
  Scene heatmap cell-extent admit is ABI 238.
  Scene heatmap colormap eligibility is ABI 239.
  Scene heatmap lattice-shape admit is ABI 240.
  Scene scatter paint-channel admit is ABI 241.
  Scene hexbin colormap-plane admit is ABI 242.
  Scene hexbin RGBA-plane admit is ABI 243.
  Scene mesh paint-plane admit is ABI 244.
  Scene per-item RGBA8 artist-alpha/opacity is ABI 245.
  Scene per-item stroke-width admit is ABI 246.
  Scene continuous per-item fill unit-t is ABI 247.
  Scene finite-all admit is ABI 248.
  Scene gradient-solid CSS is ABI 249.
  Scene f64 arrays-equal is ABI 250.
  Unit-f64 clip-quantize u8 is ABI 251.
  Scene constant-color admit is ABI 252.
  Scene hidden-or-per-item admit is ABI 253.
  256-texel colormap RGBA8 LUT uses ABI 206.
  Unit-t LUT/size u8 quantize uses ABI 251.
  Node density-bin LUT idx uses the same composition.
  Categorical palette LUT u8 uses ABI 251.
  SVG `_paint_rgba8` uses `xyg_css_color_rgba`.
  Authoring hex / colormap-stop u8 uses ABI 251.
  Style-channel finite arrays use ABI 248.
  SVG `_rgb_css` uses ABI 251.
  SVG authored-scatter marker RGBA8 uses ABI 251.
  Raster scatter RGBA8 uses ABI 251.
  Raster mesh/hexbin fill RGBA8 uses ABI 251.
  Raster rectangle style RGBA8 uses ABI 251.
  Raster segment stroke RGBA8 uses ABI 251.
  Raster mesh stroke RGBA8 uses ABI 251.
  Raster ribbon fill RGBA8 uses ABI 251.
  Raster ribbon match-fill edge RGBA8 uses ABI 251.
  Node `meshHasPerItem` uses `perItemChannelNames` for ABI 244.
  Node `scatterPaintChannelNames` uses `perItemChannelNames` for ABI 241.
  Node hexbin colormap-plane packing uses `channel.values` for ABI 242.
  Node empty kind uses `|| "mark"`.
  Node `figureTraceSupport` does not fail-close `style.smooth`.
  Node `itemWidths` fail-closes a present `stroke_width` channel without values.
  Node `itemApplyOpacity` fail-closes a present opacity/artist_alpha channel without values.
  Node missing scatter kind uses `|| ""`.
  Node `fillIsGradientAuthoring` rejects arrays (same as Python dict-only).
  Node `rectExtraFlags` treats only mapping fills as gradient-fail (same as Python dict-only).
  Node `admittedMarkerGlyph` rejects non-strings (same as Python `isinstance(..., str)`).
  Node `packXyTaColormap` uses `style.colormap` only.
  Node hexbin XYTA colormap uses `channel.colormap` only.
  Node XYHF heatmap/density colormap uses `style.colormap` only.
  Node `constantMarkColor` uses `color_ch.constant` only.
  Node `channelConstantCss` uses `channel.constant` only.
  Node `channelEndRgba8` constant paint uses `channel.constant` only.
  Node `sourceColorCss` uses `color_ch` only.
  Node `resolveColorChannel` constant CSS uses `.constant`.
  Node `color2Channel` uses `color2_ch` only.
  Node `itemFillRgba8` uses `color_ch` only.
  Node `scatterPaintChannelNames` uses `color_ch` only.
  Node `scatterHasNonConstantColor` uses `color_ch` only.
  Node `resolveDensityBinColors` uses `color_ch` only.
  Node `scatterHasNonConstantColor` ignores `style.color_channel`.
  Node `scatterPaintChannelNames` ignores `style.color_channel`.
  Node `resolveDensityBinColors` ignores `style.color_channel`.
  Node XYMS mark color uses `style.color` only.
  Node XYTC style color uses `style.color` only.
  Node XYTC constant paint uses `channel.constant` only.
  Node density-blit observation uses `scatterUsesDensity`.
  Node XYTC color_ch packing ignores string channels.
  Node `scatterHasNonConstantColor` uses `channel.constant` only.
  Node XYTC `COLOR_CH_CONSTANT` packs whenever `channel.constant` is set.
  Node XYMS mark color uses `constantMarkColor`.
  Node `scatterPerItemChannels` ignores `style.color_channel`.
  Node `scatterPerItemChannels` is mode-based.
  Node `channelEndRgba8` ignores array channels.
  Node `channelEndRgba8` categorical paint uses `DEFAULT_PALETTE`.
  Node `packXyTaColormap` stop bytes require RGB rows.
  Node `xyHfColormap` stop bytes require RGB rows.
  Node `packXyTaRgbaGrid` stacks flattened planes.
  Node heatmap `trace.rgba` is a flat uint8 buffer.
  Node heatmap and density Scene packing is XYTA-only.
  Node `packXyTaGrid` flattens heatmap `grid`.
  Node `rectFiniteSel` drops nonfinite rectangle rows.
  Node `packXyTa` density fill opacity uses `fill_opacity` only.
  Node XYTC fill opacity uses `fill_opacity` only.
  Node XYTC stroke opacity uses `stroke_opacity` only.
  Node XYTC line opacity uses `line_opacity` only.
  Node XYTC stroke width uses `stroke_width` only.
  Node XYTC line width uses `line_width` only.
  Node XYTC size uses `size` only.
  Node XYTC line color uses `line_color` only.
  Node XYTC joined fill uses `joined_fill` only.
  Node XYTC stroke perimeter uses `stroke_perimeter` only.
  Node XYTC COLOR_CH packing uses `color_ch` only.
  Node XYTC size_ch packing uses `size_ch` only.
  Node XYEF stroke-width-only observation uses `stroke_width` only.
  Node `meshJoinedFill` uses `joined_fill` only.
  Node XYEF joined-fill observation uses `joined_fill` only.
  Node `constantMarkColor` uses `color_ch` only.
  Node `classifyRibbonColor2` source-constant CSS uses `color_ch` only.
  Node `hexbinPacksColormapPlane` uses `color_ch` only.
  Node `hexbinCellRgba8` uses `color_ch` only.
---

## 4. Delivery order

1. Amend placement docs; extend C ABI (**u64** graph indices; Rust-owned
   decisions); lock the three-runtime taxonomy (§0).
2. Promote host-only layouts into Rust; Node loader over the same ABI.
3. Graph mark + interactive client (core feature); tick architecture at scale.
4. All chart types on Python and Node; golden parity; scatter-class scale
   evidence for graphs on both bindings. Keep notebook `show()` / anywidget /
   `to_html()` green throughout.

---

## 5. Non-goals

- Separate Node-only or VS Code-only renderers, or host-side reimplementations
  of Rust kernels.
- Reimplementing layout/LOD/encode inside the browser client for the product
  path.
- Mixing Node-only modules into `js/src` or browser-only APIs into
  `packages/xy-node`.
- Reimplementing GraphForge (or peer) analysis algorithms inside XYG.
- Leaving layout/encode/LOD **decisions** in one host language.
- Requiring Node for Python users or vice versa.
- A heavy GraphForge extension framework in this pass (thin helper only;
  independent charting first).
- Treating notebooks as secondary once Node lands.

---

## 6. Graph LOD / interaction parity notes (MVP)

- **Render-graph ABI:** `xyg_graph_build_render` emits centroids/`member_of` +
  cluster-space edges within node/edge budgets (optional viewport) and records
  §28; `xyg_graph_cluster_aggregate` remains the node-only helper. Hosts ship
  only the reduced buffers — no second edge-sample for draw.
- **Force at scale:** exact pairwise repulsion for `n ≤ 500`
  (`FORCE_EXACT_REPULSION_MAX_N`); spatial-grid Barnes–Hut-style approx above.
- **Configured CoSE:** Python and Node normalize ergonomic option spelling and
  shape host buffers for `xyg_graph_force_create_cose`; Rust validates semantic
  numeric constraints, bounds, pins, and compound parents and applies every
  force/layout decision.
  Browser callers use `encodeWasmCose` and `XygWasmWorker.layoutCose`; the
  static Worker transports packed columns into the same Rust `ForceState` and
  emits revision-tagged f64 checkpoints. Python's per-graph
  `GraphLayoutController` likewise schedules bounded native ticks on its own
  worker thread and restarts Rust CoSE from drag coordinates plus the current
  pin mask. Complete size-ladder timing evidence remains a #35 closure gate.
- **Box-select:** reuses the existing scatter/segments selection path — no
  graph-specific selection ABI for MVP.
- **Node shapes:** via scatter `symbol=` (same mark as other scatter charts).
- **`edge_curve`:** recorded in graph meta (`straight` default) for client
- **`xyg_graph_edge_route_segments`:** Python/Node call the same Rust router after `build_render` so Direct-tier parallels, self-loops, and arrowheads stay host-neutral (`render_edge_index` on graph meta).
- **Graph style foundation:** Node utilities and private Python `_native`
  utilities call `xyg_graph_label_accept`, `xyg_graph_visual_state_resolve`,
  and `xyg_graph_compound_bounds`. Python and Node graph composition serialize
  those Rust results into the same `spec.graph` fields. Canonical Scene v12 now
  carries Rust-resolved label text/placement, theme chrome, semantic paint,
  legends, and compound bounds to browser, HTML/SVG, and raster consumers;
  TypeScript must not derive them.
  Compound validity governs ingress, so zero-filled invalid projection slots
  pass directly without host rewrite or copy.
  ABI 89 `xyg_graph_compound_scene` is the native canonical-Scene compound
  seam used by thin Python and Node helpers. It requires each compound plane
  to equal node count and additionally validates the complete
  parent forest in linear traversal, derives transitive descendant bounds, and
  resolves collapse visibility plus boundary-edge representatives before any
  painter/export allocation. Browser painter, SVG, and raster consume those
  identical Rect/Polyline/Scatter records and the same accepted-label plane;
  no host walks ancestors or recomputes collapsed endpoints. Direct-WASM XYGG
  v3 frames exact parent, parent-validity, and collapse planes into that same
  compiler without overloading a semantic plane or adding a TypeScript fallback.
  `tests/fixtures/graphforge/semantic_compound.json` anchors exact native Scene,
  painter, SVG, raster-command, and PNG bytes for both themes. The strict-CSP
  browser worker smoke consumes the same semantic and compound fields on XYGG v3 and proves
  real WebGL paint plus deterministic label/legend accessibility and stable
  IDs plus collapsed descendant omission.
  ABI 90 and WASM ABI 14 expose the same Rust-owned atomic stable-ID
  expand/collapse/toggle transaction. Native, Python, Node, and WASM only
  frame exact planes; aggregate LOD, malformed forests, duplicate IDs, and
  leaf or missing targets are refused before output changes.
  The packaged browser entry exposes the same transition through
  `transitionWasmCompound`; browser lifecycle evidence verifies one current
  label layer across expand and recollapse without duplicating hierarchy
  traversal in TypeScript.
  follow-up; curved edge rendering is not MVP-blocking.
- **Shared dashboard admission:** the browser-only
  `ChartView.applyDashboardResourceBudget(worker, budgetBytes)` surface and
  its `applyWasmDashboardResourceBudget` boundary
  snapshots logical bytes and lifecycle signals from one document-scoped
  `GLHost`, obtains retain bits from Rust `XYDP`, and applies them only if the
  exact snapshot is still current. The first evictable class is the per-chart
  RGBA8 pick attachment; canonical Scene data and source identity stay intact,
  and picking recreates the attachment lazily. Python, Reflex, and Node HTML
  inherit this browser compositor when they use the packaged client; none owns
  a parallel admission policy. The same `GLHost` coalesces registered charts'
  color paints into one animation-frame batch without ranking them in the host;
  this browser execution mechanism therefore preserves the Rust-owned
  admission decision across Python, Reflex, Node HTML, and direct-browser use.
  `ChartView.watchDashboardResourceBudget(worker, budgetBytes)` adds opt-in
  continuous enforcement: shared-host lifecycle and measured-resource changes
  coalesce into serialized calls through that same Rust boundary. The watcher
  performs no ranking, and its controller can be disposed without destroying
  any chart or canonical state.
