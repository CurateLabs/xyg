# Dual-host parity matrix

**Status:** living matrix for Python | Node architectural and surface parity.
Anchored to the graph **render-graph** mental model in
[graph-mark.md](graph-mark.md) §1 and the placement rule in
[host-parity.md](host-parity.md) / [rust-engine.md](rust-engine.md) §1.

**Architecture principle:** GraphForge/canonical → Rust (layout, viewport,
graph LOD, edge LOD, encode, **render-graph emission**) → bounded §29
buffers → shared WebGL host (**paint only**). Both hosts are thin loaders
over the same `libxy_core` C ABI; neither reimplements LOD, force, or encode.

**Status values:** `ready` | `partial` | `missing` | `design` (spec locked;
runtime may still be landing).

---

## 1. Pipeline-layer parity (must match across hosts)

| Layer | Python | Node | Shared artifact | Notes |
| --- | --- | --- | --- | --- |
| GraphForge / canonical ingest helpers | design / partial | design / partial | Same mark buffers | Optional; never the only path ([graph-fork-requirements.md](graph-fork-requirements.md) REQ-API-3) |
| Dense `u64` indices + f64 columns | required | required | Host→Rust pointers | No `u32` element identity |
| Layout (preset/grid/circle/force/…) | Rust ABI | Rust ABI | `xy_graph_layout` / force handle | Seeded FR goldens bit-identical |
| Force ticks (progressive) | Host schedules | Host schedules | `xy_graph_force_*` | **Never JS main thread**; Barnes–Hut/grid approx at scale |
| Viewport + graph LOD + edge LOD | Rust | Rust | `xy_graph_lod_*` / cluster / sample | Recorded §28; Rust emits render graph |
| Encode → §29 f32 | Rust | Rust | Same binary payloads | Offset-encoded; no JSON numbers |
| Shared WebGL host paint | shared client | shared client | `GLHost` (dossier §18) | Paint / pick / gestures only; no raw V/E past direct tier |

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

---

## 3. Mark / composition surface matrix

Graph and Sankey lead dual-host delivery; other kinds keep equal class
([host-parity.md](host-parity.md) REQ-HOSTPARITY-2). Fill runtime cells as
ABI and Node exports land; do not claim `ready` without a shared Rust path.

| Kind | Python | Node | Rust decisions | Parity evidence |
| --- | --- | --- | --- | --- |
| graph | ready | ready (`packages/xy-node` composition) | ready: layout, force, LOD, render-graph | `tests/test_graph_node_parity.py` circle goldens + dual-host force benches |
| sankey | promote to Rust | thin `composeSankey` loader | layout in Rust | Layout ABI parity |
| scatter / line / hist / … | ready (Python) | partial (figure MVP: scatter/segments) | kernels ready / partial | Shared encode/m4/hist; Node figure subset for graph |
| polar / pie / wind_rose / facet | ready (Python) | missing | partial | Host surface gap, not kernel gap |

Update this table in the same change that lands a Node export or Rust
decision path. The machine-readable twin is
[`dual-host-parity.json`](dual-host-parity.json) (mark kinds with
python/node/rust status). Soft dual-host force/render benches live under
`benchmarks/bench_dual_host_graph*.{py,mjs}` and
`//:perf_parity_test`. This markdown remains the authoritative architecture
view; keep the JSON in lockstep.

---

## 4. Explicit non-parity (allowed differences)

| Allowed to differ | Must not differ |
| --- | --- |
| Idiomatic ingest (NumPy/pandas vs TypedArrays) | LOD tier / render-graph for the same inputs |
| Error *message* text | §29 buffer bytes for the same figure |
| Transport attach (comm vs embed) | Force positions for the same seed/ticks |
| Public helper names’ packaging | Shared WebGL paint semantics |

---

## 5. References

- [graph-mark.md](graph-mark.md) §1 — pipeline, budgets, zoom, force, `GLHost`
- [host-parity.md](host-parity.md) — REQ-HOSTPARITY-*
- [rust-engine.md](rust-engine.md) §1 — Rust owns graph LOD / render-graph
- Design dossier §18 — shared WebGL host / governor fallback
- [renderer-architecture.md](renderer-architecture.md) — mark registry + paint
