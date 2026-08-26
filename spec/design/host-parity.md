# Host parity — Python and Node

The browser WASM host retains packed `XYAG` for the compatibility seam and now
exposes `XYAS` v1 for the product-path successor: a header/domain/grid plus
bounded canonical f64 x/y chunks, all binned count-only by Rust and finished as
the existing packed `XYAO`. Hosts may frame and transfer chunks, but cannot
scan, bin, or select a grid/domain policy. Exact mean-color accumulation stays
on the legacy seam until its separately bounded stream contract exists.
Cancellation cleanup and the aggregate peak model remain Rust-owned. Native
hosts continue to use the same `xyg-engine` binning kernels. Wiring streamed
`XYAO` into the complete live density/LOD product path remains part of #59.

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
| **1. Python host** | `python/xyg/` (+ `python/reflex_xy/`) | Primary authoring host for notebooks and Python apps. Loads the Rust cdylib via **ctypes**. Surfaces: **anywidget** notebooks (`show()`), **HTML export** (`to_html()` / standalone), and **Reflex**. Embeds a **copy** of the paint client in the wheel (`python/xyg/static/`) so Python users need no Node. The public import is `xyg`; `reflex_xy` remains a separate integration namespace. |
| **2. Node host** | `packages/xy-node` (`@curatelabs/xyg-node`) | Thin Node bindings (koffi) over the **same** Rust C ABI. Covers **server-side Node** and **VS Code extensions**: VS Code is a **consumer of the Node bindings**, not a fourth stack. Never publish `@xy/node`. Native loading uses the exact optional platform package (`@curatelabs/xyg-node-<platform>-<arch>`, #52), with only an explicit absolute-path `XYG_NATIVE_LIB` development override; it never searches a checkout, working directory, system path, or Python. Windows arm64 is an explicit unsupported error. `toHtml()` inlines the host-neutral standalone client, not the Python tree. Root `npm ci` does **not** install this package; CI Test and Python 3.11 jobs run `npm ci --prefix packages/xy-node` so koffi is present for Node host tests. |
| **3. Browser surface** | `js/src/*.ts` + Rust/WASM → `@curatelabs/xyg` (`packages/xy-client/dist/{index,standalone}.js`) | Shared WebGL2 painter and browser lifecycle. Today it draws §29 buffers uploaded by Python/Node and has a bounded kernel-less fallback; #59 adds direct browser execution by compiling the same Rust engine to WebAssembly in a Worker. TypeScript keeps paint, pick, gestures, accessibility, DOM chrome, transitions, caches, and request scheduling; Rust owns canonical layout/LOD/encode decisions. |

The #59 foundation now adds `crates/xyg-wasm`, a generated raw-export adapter,
and an explicit static module Worker. It proves bounded JS→WASM staging,
version/status/lifecycle behavior, exact Scene validation/paint lowering, and
packed typed-column compile into the same canonical Scene batch native hosts
encode. Public `frameWasmChart` / `renderWasmChart` transfer typed series while
Rust assigns identities and expands canonical mark/default geometry; density replacement remains
open, so the direct-browser product acceptance remains open. See
[browser-wasm.md](browser-wasm.md).

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
pairs with bounded stem markers, at most 1,024 fill-only unjoined constant-color
triangle-mesh faces, and finite literal solid ribbons. Each accepted mesh face
is one three-vertex PolyFill group shared by SVG, raster, and browser consumers;
joined fills, component alpha, outlines, per-face styles, alternate axes, and
larger meshes remain compatibility behavior. For ribbons,
Python and Node pack two adjacent endpoint rows and ABI 97 makes Rust apply the
axis transforms and expand the fixed 96-interval cubic into 97 paired Scene
Band samples. Two-ended gradients, polar projection, LOD/density, and
direct-browser ribbon authoring remain explicit boundaries; the last is #59
work. Every unmodeled output contract remains an explicit compatibility route.
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
positive integer bins remain uniform and unchanged; all-nonfinite input retains
the documented ten-bin `[0, 1]` (or authored-range) compatibility result.
Rust caps automatic resolution at 10,000 bins (10,001 edges); invalid ranges or
larger results fail through the hosts' existing histogram argument errors.
Unsorted, repeated, nonfinite, constant, ranged, density, and cumulative
fixtures produce identical Rect Scenes for SVG, raster, and browser consumers.
Authored arbitrary edges and cumulative assembly remain separate host-policy
debt.
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
[scene-ir.md](scene-ir.md). Per-item scatter stroke/width, custom marker
paths/glyphs, and density/LOD remain explicit compatibility exceptions. Python custom glyph/path markers and other
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
values, steps, and formatting. Attached automatic primary Cartesian ChartView
axes already use that lifecycle via `attachWasmTicks`. Notebook, Reflex, and
secondary/polar/colorbar paths remain #59 work.

For the migrated subset, public Python SVG and native PNG now use the Rust
Scene consumers and public PDF consumes their Rust SVG. The shared predicate
chooses the compatibility renderer only before Scene compilation for an
explicit unsupported feature, an export-only background override, or a valid
viewport too small for bounded Scene chrome. A malformed input or Rust
consumer failure remains an error rather than a fallback signal.

The public literal `x_axis`/`y_axis` `ticks=False` and `text=False` switches
are inside that migrated static subset: Rust preserves the independent
semantics in all three consumers (major-tick geometry versus tick-label/title
paint). This does not widen the boundary to rich tick strings, wrapping,
custom fonts, CSS/classes, theme-driven chrome, or arbitrary annotation text.

### Contracts (MUST)

- **Rust owns decisions for all marks.** Hosts are thin: coerce inputs, schedule
  progressive work, attach transport, and assemble figure specs. They MUST NOT
  reimplement layout, LOD tiering, channel encode, or other buffer-affecting
  decisions in Python or TypeScript.
- **Browser TypeScript never reimplements layout / LOD / encode** for the
  product path. The client applies Rust-produced live §29 offset-f32/u8 buffers and runs screen-bounded
  interaction; force ticks and LOD plans stay off the browser main thread’s
  decision path (native Rust today, the same Rust compiled to WASM under #59).
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
  numbers. Native-vs-WASM projection parity is covered with #59.
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
  shenanigans for MVP: promote remaining host-only paths (e.g. Sankey) into
  Rust so every shipped mark is dual-host capable without a parallel host
  implementation.

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
