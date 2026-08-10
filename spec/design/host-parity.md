# Host parity — Python and Node

**Status:** requirements locked with [graph-fork-requirements.md](graph-fork-requirements.md);
implementation design in [graph-mark.md](graph-mark.md).

**Priority:** **graph visualization** is the core feature. **MVP includes all
chart / visualization features** on Python and Node with equal feel and speed —
no degraded non-graph path, and **no Python host-only layout/encode leftovers**.

**Architecture principle — Rust owns decisions:** implement chart behavior in
the shared Rust C ABI so Python and Node stay thin loaders over identical
behavior. **Rust owns decisions** that affect buffers, layout, encodings, LOD,
and recorded §28 outcomes — not only O(N) loops. Hosts own ergonomics and
idiomatic I/O only; the JS client owns screen-bounded draw and gestures only.
This **replaces** upstream rust-engine §1’s “Python owns decisions” for this
product line (amend that doc when implementing).

---

## 1. Goal

| Layer | Shared across Python and Node |
|---|---|
| Rust viz `cdylib` C ABI | All kernels (existing marks + `xy_graph_*`); **u64** graph element indices |
| Wire / §29 buffers | Identical binary payloads for the same figure spec |
| JS render client | One bundled WebGL client |
| Public chart semantics | Same mark kinds, options, defaults, layout/LOD decisions |

Host-only differences are idiomatic (NumPy/pandas/Arrow vs TypedArrays;
notebook/Reflex vs Node embed). Names and defaults match.

---

## 2. Placement rule (Rust owns decisions)

| Lives in | Examples |
|---|---|
| **xy Rust (shared)** | Display layouts (including today’s Python-only ones such as Sankey), graph adjacency/position buffers, channel resolution, decimation, LOD aggregates, layout/LOD **decisions**, thresholds that change buffers, progressive layout ticks |
| **Host (Python *or* Node)** | Public API shapes, idiomatic ingest coercion (list/NumPy/TypedArray → pointers), error message text, transport attach — **no** second layout/algorithm/encode/decision path |
| **JS client** | WebGL draw, hit-test, pan/zoom/select/drag gestures applying uploaded buffers |

Graph **analysis algorithms** (paths, centrality, communities, Cypher, …) are
not owned here — they live in GraphForge (and similar peers). This charting
stack plots their outputs; it does not reimplement them.

Node must not reimplement layouts or mark geometry in TypeScript.

---

## 3. Requirements

- **REQ-HOSTPARITY-1 (MUST).** One xy Rust C ABI serves Python (`ctypes` today)
  and Node (N-API). `ABI_VERSION` bumps apply to both loaders.
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
  xy-native column/sequence formats from
  [graph-fork-requirements.md](graph-fork-requirements.md) REQ-API-3 remain
  available with the same semantics on Python and Node.
- **REQ-HOSTPARITY-3 (MUST).** The browser client is shared; hosts only differ
  in transport attachment.
- **REQ-HOSTPARITY-4 (MUST).** Graph viz is the core dual-host feature surface
  ([graph-fork-requirements.md](graph-fork-requirements.md)); other marks are
  first-class in the same MVP.
- **REQ-HOSTPARITY-5 (MUST).** Amend [rust-engine.md](rust-engine.md) (and
  dossier §32 when Node lands) so “Rust owns decisions” is the documented rule
  for this product line — do not leave conflicting “Python owns decisions”
  guidance in force.
- **REQ-HOSTPARITY-6 (MUST, MVP).** Remove Python host-only layout/encode
  shenanigans for MVP: promote remaining host-only paths (e.g. Sankey) into
  Rust so every shipped mark is dual-host capable without a parallel host
  implementation.

---

## 4. Delivery order

1. Amend placement docs; extend C ABI (**u64** graph indices; Rust-owned
   decisions).
2. Promote host-only layouts into Rust; Node loader over the same ABI.
3. Graph mark + interactive client (core feature); tick architecture at scale.
4. All chart types on Python and Node; golden parity; scatter-class scale
   evidence for graphs on both bindings.

---

## 5. Non-goals

- Separate Node-only renderers or host-side reimplementations of Rust kernels.
- Reimplementing GraphForge (or peer) analysis algorithms inside xy.
- Leaving layout/encode/LOD **decisions** in one host language.
- Requiring Node for Python users or vice versa.
- A heavy GraphForge extension framework in this pass (thin helper only;
  independent charting first).

---

## 6. Graph LOD / interaction parity notes (MVP)

- **Cluster LOD ABI:** `xy_graph_cluster_aggregate` (grid/hash bin centroids +
  recorded §28 tier) is shared; Python/Node loaders must not reimplement
  clustering policy.
- **Box-select:** reuses the existing scatter/segments selection path — no
  graph-specific selection ABI for MVP.
- **Node shapes:** via scatter `symbol=` (same mark as other scatter charts).
- **`edge_curve`:** recorded in graph meta (`straight` default) for client
  follow-up; curved edge rendering is not MVP-blocking.
