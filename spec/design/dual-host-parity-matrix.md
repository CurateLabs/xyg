# Dual-host parity matrix

**Status:** living matrix for Python | Node architectural and surface parity
across the **entire product** (all chart types). Anchored to the three runtime
surfaces in [host-parity.md](host-parity.md) §0, the graph **render-graph**
mental model in [graph-mark.md](graph-mark.md) §1, and the placement rule in
[host-parity.md](host-parity.md) / [rust-engine.md](rust-engine.md) §1.

**Architecture principle:** GraphForge/canonical → Rust (layout, viewport,
graph LOD, edge LOD, encode, **render-graph emission**, and all other mark
decisions) → bounded §29 buffers → shared WebGL browser client (**paint only**).
Both hosts are thin loaders over the same `libxy_core` C ABI; neither
reimplements LOD, force, or encode. The browser client never reimplements
layout/LOD/encode for the product path.

**Status values:** `ready` | `partial` | `missing` | `design` (spec locked;
runtime may still be landing).

---

## 0. Three runtime surfaces (not graph-only)

| Id | Surface | Path / artifact | Consumers | Owns | Must not |
| --- | --- | --- | --- | --- | --- |
| `python` | Python host | `python/xy/` (+ `reflex_xy`) | Notebooks (**anywidget** / `show()`), **HTML export** (`to_html()`), **Reflex** | ctypes → Rust ABI; idiomatic Python ingest; transport attach | Parallel layout/LOD/encode decisions |
| `node` | Node host | `packages/xy-node` | **Server-side Node** and **VS Code extensions** (VS Code consumes Node bindings — not a separate stack) | koffi → same Rust ABI; TypedArray ingest; embed/webview attach | Browser-only APIs (`window` / DOM / WebGL) |
| `browser` | Browser client | `js/src` → `python/xy/static/{index,standalone}.js` | Shared renderer for every host | WebGL2 **paint / pick / gestures** on uploaded §29 buffers | Layout / LOD / encode product path; `koffi` / `node:fs` |

**Invariants**

- Same figure spec + §29 bytes across Python and Node for the same inputs;
  browser is the shared renderer.
- Notebook `show()` / anywidget / `to_html()` remain first-class and must not
  regress.
- Machine-readable twin: [`dual-host-parity.json`](dual-host-parity.json)
  `runtimes` section.

---

## 1. Pipeline-layer parity (must match across hosts)

| Layer | Python | Node | Shared artifact | Notes |
| --- | --- | --- | --- | --- |
| GraphForge / canonical ingest helpers | design / partial | design / partial | Same mark buffers | Optional; never the only path ([graph-fork-requirements.md](graph-fork-requirements.md) REQ-API-3) |
| Dense `u64` indices + f64 columns | required | required | Host→Rust pointers | No `u32` element identity |
| Layout (preset/grid/circle/force/…) | Rust ABI | Rust ABI | `xy_graph_layout` / force handle | Seeded FR goldens bit-identical |
| Force ticks (progressive) | Host schedules | Host schedules | `xy_graph_force_*` | **Never browser main-thread decisions**; Barnes–Hut/grid approx at scale |
| Viewport + graph LOD + edge LOD | Rust | Rust | `xy_graph_lod_*` / cluster / sample | Recorded §28; Rust emits render graph |
| Encode → §29 f32 | Rust | Rust | Same binary payloads | Offset-encoded; no JSON numbers |
| Shared WebGL browser paint | shared client | shared client | `GLHost` (dossier §18) | Paint / pick / gestures only; no raw V/E past direct tier |

Complexity budgets (both hosts inherit the same Rust costs):

| Stage | Budget |
| --- | --- |
| Ingest | O(V+E) |
| Layout | approx (exact only when small) |
| LOD plan | O(V+E) |
| Interactive | ≈ O(visible) |
| GPU | ≈ O(screen) past direct tier |

---

## 2. Zoom / LOD parity (render-graph contract)

| Zoom band | What both hosts must ship | WebGL may see |
| --- | --- | --- |
| Far | Clusters / density + aggregate edges | Aggregate layers only |
| Mid | Reps + aggregate/sampled edges | Bounded reps + edges |
| Near / direct | Exact nodes/edges under budget | Per-element V/E **only** in this tier |

**Invariant:** past the direct-render tier, neither host may upload raw
topology for the GPU to “figure out.” Divergence here is a host-parity bug.
The browser client does not invent a second LOD plan in JS.

---

## 3. Mark / composition surface matrix

Graph and Sankey lead dual-host delivery; other kinds keep equal class
([host-parity.md](host-parity.md) REQ-HOSTPARITY-2). Fill runtime cells as
ABI and Node exports land; do not claim `ready` without a shared Rust path.

| Kind | Python | Node | Rust decisions | Parity evidence |
| --- | --- | --- | --- | --- |
| graph | ready | ready (`packages/xy-node` composition) | ready: layout, force, LOD, render-graph | `tests/test_graph_node_parity.py` circle goldens + dual-host force benches |
| sankey | promote to Rust | thin `composeSankey` loader | layout in Rust | Layout ABI parity |
| scatter / line / hist / bar / … | ready (Python) | ready (thin marks + `charts.js`; figure MVP) | kernels ready (`xy_bar_stack` ABI 57) | `tests/test_node_mark_parity.py` encode/M4/hist goldens |
| polar / pie / wind_rose / facet | ready (Python) | pie/wind_rose ready; polar/facet partial stubs | ready bins + bar stack; facet host-only | Node `marks/polar.js` composers |

Update this table in the same change that lands a Node export or Rust
decision path. The machine-readable twin is
[`dual-host-parity.json`](dual-host-parity.json) (mark kinds with
python/node/rust status + `runtimes`). Soft dual-host force/render benches live
under `benchmarks/bench_dual_host_graph*.{py,mjs}` and `//:perf_parity_test`.
This markdown remains the authoritative architecture view; keep the JSON in
lockstep.

---

## 4. Explicit non-parity (allowed differences)

| Allowed to differ | Must not differ |
| --- | --- |
| Idiomatic ingest (NumPy/pandas vs TypedArrays) | LOD tier / render-graph for the same inputs |
| Error *message* text | §29 buffer bytes for the same figure |
| Transport attach (comm vs embed vs VS Code webview) | Force positions for the same seed/ticks |
| Public helper names’ packaging | Shared WebGL paint semantics |
| Host process model (CPython vs Node vs extension host) | Three-surface taxonomy (no fourth engine stack) |

---

## 5. References

- [host-parity.md](host-parity.md) §0 — three runtime surfaces; REQ-HOSTPARITY-*
- [graph-mark.md](graph-mark.md) §1 — pipeline, budgets, zoom, force, `GLHost`
- [rust-engine.md](rust-engine.md) §1 — Rust owns graph LOD / render-graph
- Design dossier §18 — shared WebGL host / governor fallback
- [renderer-architecture.md](renderer-architecture.md) — mark registry + paint
- `packages/xy-node/README.md` — Node host package notes
