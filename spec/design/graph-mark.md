# Graph mark — design

**Status:** implementation design. Implements
[graph-fork-requirements.md](graph-fork-requirements.md) and
[host-parity.md](host-parity.md). Authoritative for the `graph` /
`graph_chart` surface, `xy_graph_*` ABI, wire shape, layout ticks, and the
**render-graph** mental model below. Dual-host expectations:
[dual-host-parity-matrix.md](dual-host-parity-matrix.md).

---

## 1. Architecture — render-graph mental model

Graph viz in xy is not “dump V/E into WebGL.” Canonical graph data stays
host/CPU-side; **Rust** decides layout, viewport culling, graph LOD, edge LOD,
and encoding; the browser receives only **bounded §29 buffers** and paints
them through the **shared WebGL host**. Analysis algorithms stay in
GraphForge (and peers); this stack plots their outputs.

### 1.1 Pipeline

```text
GraphForge / canonical graph
        │  (ids, edges, optional attrs / preset x,y — analysis stays upstream)
        ▼
Host ingest (Python or Node)  →  dense u64 indices + f64 columns
        ▼
Rust C ABI (`xy_graph_*`)
  · layout (preset / grid / circle / force / …)
  · viewport windowing
  · graph LOD (clusters / reps / exact)
  · edge LOD (sample / aggregate / exact)
  · encode → offset f32 geometry + recorded §28 decisions
        ▼
Bounded §29 buffers + figure spec / render-graph descriptors
        ▼
Shared WebGL host (GLHost) — paint only
  · upload / draw / pick / gestures on shipped buffers
  · never re-derives LOD or force
```

| Stage | Owner | Emits |
|---|---|---|
| Analysis (paths, centrality, communities, …) | GraphForge / peers | Canonical tables / attributes |
| Ingest + id maps | Host (Python \| Node) | Pointers into Rust; tooltip id maps |
| Layout, viewport, graph LOD, edge LOD, encode | **Rust** | Positions, tiered geometry, §28 records, render-graph |
| Transport | Host | Spec + §29 blobs |
| Paint / hit-test / pan-zoom gestures | Shared WebGL client | Pixels only |

**Invariant:** Rust emits the **render graph** (which drawable layers, which
buffers, which recorded tier). The WebGL client does not invent tiers or
walk raw adjacency for drawing.

### 1.2 Complexity budget

| Stage | Budget | Notes |
|---|---|---|
| Ingest / CSR / id densify | **O(V+E)** | Once per graph (or structural edit); host→Rust handoff |
| Layout | **approx** | Exact FR only at small N; Barnes–Hut / grid approx at scale (§1.5) |
| Graph + edge LOD plan | **O(V+E)** | Viewport + budgets → tier; recorded (§28) |
| Interactive path | **≈ O(visible)** | Picks, neighbor highlight, drag; CSR on demand / shipped |
| GPU / paint | **≈ O(screen)** | Past direct tier: aggregates / density / sampled edges only |

Crossing a budget is never silent: every reduction is a recorded §28 decision
(same honesty rule as scatter LOD).

### 1.3 Boundary — never expose WebGL to raw V/E past direct tier

- **Direct-render tier only:** the client may hold one vertex/instance per
  visible node or edge, and only while `|V|` / `|E|` (or visible counts) sit
  under the Rust-owned direct budgets.
- **Above direct:** Rust **must** emit a render graph of aggregates —
  cluster centroids / representative nodes, density or bin surfaces, sampled
  or bundled edges — never the full adjacency list as GL buffers.
- Hosts and JS **must not** upload raw `V`/`E` “for the GPU to sort out.”
  If a path would ship unbounded topology to the browser, it is a bug.

This is the graph analogue of scatter’s density / pyramid tiers: the browser
stays screen-safe; truthfulness lives in recorded reductions + drill.

### 1.4 Zoom story

| Zoom | Node representation | Edge representation |
|---|---|---|
| **Far** | Clusters and/or density / aggregate surface | Aggregate or heavily sampled edges between clusters |
| **Mid** | Representative nodes (cluster reps / stratified keep) | Aggregate or sampled edges among reps |
| **Near** | Exact nodes (under budget / drilled window) | Exact edges (under budget / drilled window) |

Transitions follow scatter-class hysteresis and `drill_seq` versioning where
subsets ship ([lod-architecture.md](lod-architecture.md)); graph-specific
cluster membership stays available on the host for hover/drill identity.
Far and mid views are **honest aggregates**, not silent random drops.

### 1.5 Force layout at scale

- Default `layout="force"` is seeded Fruchterman–Reingold for small graphs
  (golden-tested across hosts).
- **Exact pairwise repulsion** when `n ≤ FORCE_EXACT_REPULSION_MAX_N` (**500**);
  above that, a deterministic spatial-grid Barnes–Hut-style cell approximation
  (exact within Moore neighborhood, monopole COM for distant cells). Seeded
  tests with `n ≤ ~64` always take the exact path.
- At scale: **Barnes–Hut** / **grid** force approximations — never
  naïve O(V²) on the interactive path.
- **Progressive ticks:** `force_create` → `force_tick(k)*` → `force_destroy`;
  hosts schedule on worker threads; uploads coalesce to animation frames.
- **Never on the JS main thread.** Force math is Rust-only; the client only
  paints position buffers it already received (§4).

### 1.6 Shared WebGL host inheritance

Graph marks do **not** invent a second GL stack. They inherit the upstream
document-scoped shared host:

- Design dossier **§18** — production `GLHost` (one detached WebGL2 context;
  charts blit into per-chart Canvas2D surfaces); governed per-chart fallback
  when `XY_SHARED_WEBGL` is off / unavailable / child-frame default.
- [renderer-architecture.md](renderer-architecture.md) — mark registry,
  uniform-only pan/zoom, §29 uploads; graph compiles to `segments` +
  `scatter` (+ graph meta / CSR), drawn by existing mark paths plus thin
  graph interaction (`58_graph.ts` when present).

Paint-only: the shared host never runs layout, LOD policy, or force.

---

## 2. Public API

```python
xy.graph_chart(
    xy.graph(
        nodes,              # ids, or table with id column
        edges,              # (source, target) pairs / columns
        *,
        x=None, y=None,     # preset positions (columns or arrays)
        layout="force",     # see §3 — single parameter, documented default
        color=None, size=None,  # node encodings
        edge_color=None, edge_width=None,
        directed=True,
        seed=0,
        iterations=300,
        ...
    ),
    ...
)
```

Node hosts mirror the same option names (TypedArrays / arrays).

**Ingest (REQ-API-3):** xy-native sequences, NumPy, pandas/Arrow columns,
edge lists, adjacency. Optional thin `from_graphforge(...)` / `from_networkx`
helpers compile to the same buffers — never the only path.

**Compile target:** one logical `graph` mark expands to a Rust-emitted
**render graph** whose leaf geometry is wire traces `segments` (edges) +
`scatter` (nodes), plus graph meta on the figure spec (`layout`, `n_nodes`,
`n_edges`, `directed`, neighbor CSR for highlight, recorded LOD). No
PROTOCOL bump required for MVP geometry; meta rides existing spec fields.

---

## 3. Index model (`u64`)

| Layer | Type |
|---|---|
| Public node IDs | `str` or `int` (host map) |
| Internal dense node / edge indices | **`u64`** in Rust ABI and CSR |
| Wire geometry | f32 positions/colors (§29); u64 index planes when shipped |

Never use `u32` for graph element identity — that ceiling already failed at
GraphForge / large-row scale.

Host keeps `id_to_index: dict` / `index_to_id: list` for tooltips and
selection callbacks. Rust never requires string IDs.

---

## 4. `layout=` catalog

Single parameter; default **`"force"`**.

| Name | Behavior |
|---|---|
| `preset` | Use provided `x`/`y` (required) |
| `grid` | Row-major grid |
| `circle` | Even circle |
| `force` | Seeded Fruchterman–Reingold (default algorithm for `"force"`); Barnes–Hut / grid approx at scale (§1.5) |
| `breadthfirst` | BFS layers from lowest-index root (or `roots=`) |
| `radial` | Distance rings from root (SHOULD) |
| `concentric` | Degree / attribute rings (SHOULD) |
| `dagre` / `hierarchical` | DAG layers (SHOULD) |
| `auto` | Heuristic: tiny→circle, DAG-like→breadthfirst, else force |

All future algorithms register as new `layout=` string values (REQ-LAY-6).

Force defaults: `seed=0`, `iterations=300`, `jitter` from seed. Golden tests
pin seeded FR output across Python and Node for the exact small-N path.

---

## 5. Progressive layout ticks (REQ-CORE-6)

```mermaid
sequenceDiagram
  participant Host as Python_or_Node
  participant Rust as xy_graph_force
  participant Client as WebGL_client
  Host->>Rust: force_create(nodes,edges,seed)
  loop until alpha_low or cancel
    Host->>Rust: force_tick(k)
    Rust-->>Host: positions f64
    Host->>Client: §29 f32 position upload coalesce
    Client->>Client: rAF draw
  end
  Host->>Rust: force_destroy
```

Rules:

- All force math in Rust (exact or Barnes–Hut/grid approx); hosts only
  schedule ticks (thread / `worker_threads`).
- **Never run force on the JS main thread.**
- Coalesce uploads to animation frames; cancel drops the handle.
- First paint: `grid`/`circle` seed or N quick ticks, then refine.
- Same ABI for Python and Node → parity at scale.

---

## 6. LOD (scatter-class scale)

Align with xy scatter claims (10M / 100M / 1B-class **with** aggregation) and
the zoom story in §1.4:

| Regime | Behavior |
|---|---|
| Direct | Draw all nodes/edges under budget — sole tier that may expose per-element V/E to WebGL |
| Edge sample | Rust samples edges when `|E|` over budget; record §28 |
| Cluster / aggregate | Rust `xy_graph_build_render` (and `xy_graph_cluster_aggregate`) write centroids / reps when `|V|` exceeds `node_budget`, collapse multi-edges into cluster index space, and record §28; hosts keep `member_of` for drill / hover |
| Labels | Hide below zoom / over label budget |

Budgets and tier choice live in Rust decision helpers (render-graph emission);
hosts do not fork tier policy. Past direct tier, WebGL sees only the emitted
aggregates (§1.3).

---

## 7. Interaction

- Pan / zoom / fit (chart view) — zoom drives §1.4 LOD, not client-side
  topology walks.
- Pick nodes via scatter GPU pick; edges via segment hit or neighbor of picked node.
- Neighborhood highlight: CSR (`csr_offsets` / `csr_neighbors` u64 arrays on
  `spec.graph[]`) is consumed by the WebGL client. On hover of the graph's
  scatter (`node_trace`), the client builds a temporary `selBuf` mask
  (hovered node + CSR neighbors) and dims the rest through the existing
  point-shader `u_selActive` path; leave clears the mask. Durable
  box/lasso/rows selection still owns `selBuf` when active. On-demand
  `xy_graph_neighbors` remains available for hosts that do not ship CSR.
- Drag nodes (SHOULD): write positions back through ABI / host buffer.
- Box select (SHOULD): reuse existing selection — graph node scatters
  participate as ordinary scatter traces (no separate path).
- Node shapes: via scatter `symbol=` (circle / square / …); no separate graph
  glyph ABI for MVP.
- `edge_curve` meta (`straight` default): recorded on graph meta for client
  follow-up; MVP geometry stays straight segments.

Interactive path is primary; export must not reshape the hot path (§8).
Geometry remains segments + scatter buffers from the render graph; the client
draws uploaded buffers only (MVP keeps straight segments regardless of
`edge_curve` meta).

---

## 8. Export

- HTML / WebGL interactive: primary (shared `GLHost`, §1.6).
- SVG: circles + polylines from screen-bounded positions (host SVG writer).
- Native PNG display-list graph ops: follow-up; do not block interactive MVP.

---

## 9. ABI sketch (`ABI_VERSION` bump with each signature change)

| Symbol | Role |
|---|---|
| `xy_graph_layout` | One-shot layout → `out_x`/`out_y` f64 |
| `xy_graph_force_create` | Handle for progressive FR / approx force |
| `xy_graph_force_tick` | Advance k steps; write positions |
| `xy_graph_force_destroy` | Free handle |
| `xy_graph_build_csr` | `offsets`/`neighbors` u64 CSR |
| `xy_graph_sample_edges` | LOD edge index sample |
| `xy_graph_lod_decision` | Recorded tier decision (§28) / render-graph inputs |
| `xy_graph_cluster_aggregate` | LOD node centroid clusters + node→cluster membership + recorded tier |
| `xy_graph_build_render` | Perceptually bounded render graph: centroids/`member_of` + cluster-space edges ≤ budgets; recorded §28 |

Element counts and indices are `u64` / `uint64_t`.

---

## 10. Module layout

```
src/graph/
  mod.rs       # public layout + force + csr + lod + render-graph decisions
python/xy/
  _graph.py    # ingest helpers, id map, from_networkx thin
  marks.py     # graph() → layout/LOD ABI → segments + scatter
packages/xy-node/
  src/abi.js            # koffi loader over same cdylib
  src/graph.js          # normalize + runLayout (+ edge segments / meta)
  src/marks/            # scatter / line / histogram thin builders
  src/charts.js         # scatterChart / lineChart / histogramChart / graphChart
  src/figure.js         # minimal Figure + buildPayload (§29 subset)
  src/force_scheduler.js  # progressive ticks (setImmediate / worker_threads)
  src/sankey.js         # thin composeSankey
js/src/
  # shared GLHost paint; graph meta / CSR highlight only
```

Parity evidence: `tests/test_graph_node_parity.py` (4-node circle f64 + f32
bit-identical across Python and Node);
`tests/test_node_mark_parity.py` (scatter encode, M4 index count, histogram
counts).

Sankey and any other host-only layouts promote into Rust under the same
“Rust owns decisions” rule for dual-host MVP ([host-parity.md](host-parity.md)).
Placement of graph LOD / render-graph ownership is also recorded in
[rust-engine.md](rust-engine.md) §1.
