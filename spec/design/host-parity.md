# Host parity — Python and Node

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
| **1. Python host** | `python/xy/` (+ `python/reflex_xy/`) | Primary authoring host for notebooks and Python apps. Loads the Rust cdylib via **ctypes**. Surfaces: **anywidget** notebooks (`show()`), **HTML export** (`to_html()` / standalone), and **Reflex**. Embeds a **copy** of the paint client in the wheel (`python/xy/static/`) so Python users need no Node. The naming matrix decides `import xyg` / `python/xyg/`; that directory rename is staged after the crate split. |
| **2. Node host** | `packages/xy-node` (`@curatelabs/xyg-node`) | Thin Node bindings (koffi) over the **same** Rust C ABI. Covers **server-side Node** and **VS Code extensions**: VS Code is a **consumer of the Node bindings**, not a fourth stack. Never publish `@xy/node`. `toHtml()` inlines the host-neutral standalone client, not the Python tree. Root `npm ci` does **not** install this package; CI Test and Python 3.11 jobs run `npm ci --prefix packages/xy-node` so koffi is present for Node host tests. |
| **3. Browser surface** | `js/src/*.ts` + Rust/WASM → `@curatelabs/xyg` (`packages/xy-client/dist/{index,standalone}.js`) | Shared WebGL2 painter and browser lifecycle. Today it draws §29 buffers uploaded by Python/Node and has a bounded kernel-less fallback; #59 adds direct browser execution by compiling the same Rust engine to WebAssembly in a Worker. TypeScript keeps paint, pick, gestures, accessibility, DOM chrome, transitions, caches, and request scheduling; Rust owns canonical layout/LOD/encode decisions. |

The #59 foundation now adds `crates/xyg-wasm`, a generated raw-export adapter,
and an explicit static module Worker. It proves bounded JS→WASM staging,
version/status/lifecycle behavior, and exact Scene v4 validation. It does not
yet compile browser chart specifications or replace the kernel-less density
fallback, so the direct-browser product acceptance remains open. See
[browser-wasm.md](browser-wasm.md).

The #58 scene migration is active: scene schema version 4 provides one
backend-neutral Rust-owned typed batch with fixed caller-provided plot bounds, axes,
scatter, polyline, and rectangle records through both host bindings. The v1
scatter SVG wrapper remains temporarily for scatter-only compatibility. Python
and Node now compile the same representative constant-style scatter/line/bar
figure fixture to identical Scene bytes; explicit host APIs feed those bytes to
Rust SVG and native-raster consumers. Public Python SVG/PNG/PDF retain the
compatibility renderer until Rust owns canonical layout/gutter selection and Scene
records cover authored text/style beyond its Rust-owned default numeric chrome. See
[scene-ir.md](scene-ir.md). Python custom glyph/path markers and other
not-yet-migrated customization remain explicit compatibility exceptions until
bounded path, text, and chrome records land.

### Contracts (MUST)

- **Rust owns decisions for all marks.** Hosts are thin: coerce inputs, schedule
  progressive work, attach transport, and assemble figure specs. They MUST NOT
  reimplement layout, LOD tiering, channel encode, or other buffer-affecting
  decisions in Python or TypeScript.
- **Browser TypeScript never reimplements layout / LOD / encode** for the
  product path. The client applies Rust-produced §29 buffers and runs screen-bounded
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
| Rust viz `cdylib` C ABI | All kernels (existing marks + `xyg_graph_*`); **u64** graph element indices |
| Wire / §29 buffers | Identical binary payloads for the same figure spec |
| JS render client | One bundled WebGL client (`@curatelabs/xyg`: `index.js` / `standalone.js`); Python copies into the wheel |
| Public chart semantics | Same mark kinds, options, defaults, layout/LOD decisions |

Host-only differences are idiomatic (NumPy/pandas/Arrow vs TypedArrays;
notebook/Reflex vs Node embed / VS Code webview attach). Names and defaults
match.

---

## 2. Placement rule (Rust owns decisions)

| Lives in | Examples |
|---|---|
| **XYG Rust (shared)** | Display layouts (including today’s Python-only ones such as Sankey), graph adjacency/position buffers, channel resolution, decimation, LOD aggregates, layout/LOD **decisions**, thresholds that change buffers, progressive layout ticks |
| **Host (Python *or* Node)** | Public API shapes, idiomatic ingest coercion (list/NumPy/TypedArray → pointers), error message text, transport attach — **no** second layout/algorithm/encode/decision path |
| **Browser client** | WebGL draw, hit-test, pan/zoom/select/drag gestures applying uploaded buffers |

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
- **Box-select:** reuses the existing scatter/segments selection path — no
  graph-specific selection ABI for MVP.
- **Node shapes:** via scatter `symbol=` (same mark as other scatter charts).
- **`edge_curve`:** recorded in graph meta (`straight` default) for client
  follow-up; curved edge rendering is not MVP-blocking.
