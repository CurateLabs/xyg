# Graph mark — design

**Status:** implementation design. Implements
[graph-fork-requirements.md](graph-fork-requirements.md) and
[host-parity.md](host-parity.md). Authoritative for the `graph` /
`graph_chart` surface, `xy_graph_*` ABI, wire shape, and layout tick
architecture.

---

## 1. Public API

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

**Compile target:** one logical `graph` mark expands to wire traces
`segments` (edges) + `scatter` (nodes), plus graph meta on the figure spec
(`layout`, `n_nodes`, `n_edges`, `directed`, neighbor CSR for highlight).
No PROTOCOL bump required for MVP geometry; meta rides existing spec fields.

---

## 2. Index model (`u64`)

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

## 3. `layout=` catalog

Single parameter; default **`"force"`**.

| Name | Behavior |
|---|---|
| `preset` | Use provided `x`/`y` (required) |
| `grid` | Row-major grid |
| `circle` | Even circle |
| `force` | Seeded Fruchterman–Reingold (default algorithm for `"force"`) |
| `breadthfirst` | BFS layers from lowest-index root (or `roots=`) |
| `radial` | Distance rings from root (SHOULD) |
| `concentric` | Degree / attribute rings (SHOULD) |
| `dagre` / `hierarchical` | DAG layers (SHOULD) |
| `auto` | Heuristic: tiny→circle, DAG-like→breadthfirst, else force |

All future algorithms register as new `layout=` string values (REQ-LAY-6).

Force defaults: `seed=0`, `iterations=300`, `jitter` from seed. Golden tests
pin seeded FR output across Python and Node.

---

## 4. Progressive layout ticks (REQ-CORE-6)

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

- All force math in Rust; hosts only schedule ticks (thread / `worker_threads`).
- Never run force on the JS main thread.
- Coalesce uploads to animation frames; cancel drops the handle.
- First paint: `grid`/`circle` seed or N quick ticks, then refine.
- Same ABI for Python and Node → parity at scale.

---

## 5. LOD (scatter-class scale)

Align with xy scatter claims (10M / 100M / 1B-class **with** aggregation):

| Regime | Behavior |
|---|---|
| Direct | Draw all nodes/edges under budget |
| Edge sample | Rust samples edges when `|E|` over budget; record §28 |
| Cluster / aggregate | Rust `xy_graph_cluster_aggregate` writes grid/hash bin centroids when `|V|` exceeds `node_budget` and records the §28 LOD decision (`tier` / `edges_kept`); hosts keep each node's cluster id for drill-down / hover |
| Labels | Hide below zoom / over label budget |

Budgets live in Rust decision helpers; hosts do not fork tier policy.

---

## 6. Interaction

- Pan / zoom / fit (chart view).
- Pick nodes via scatter GPU pick; edges via segment hit or neighbor of picked node.
- Neighborhood highlight: CSR (`csr_offsets` / `csr_neighbors` u64 arrays on
  `spec.graph[]`) is consumed by the WebGL client (`js/src/58_graph.ts`). On
  hover of the graph's scatter (`node_trace`), the client builds a temporary
  `selBuf` mask (hovered node + CSR neighbors) and dims the rest through the
  existing point-shader `u_selActive` path; leave clears the mask. Durable
  box/lasso/rows selection still owns `selBuf` when active. On-demand
  `xy_graph_neighbors` remains available for hosts that do not ship CSR.
- Drag nodes (SHOULD): write positions back through ABI / host buffer.
- Box select (SHOULD): reuse existing selection — graph node scatters
  participate as ordinary scatter traces (no separate path).
- Node shapes: via scatter `symbol=` (circle / square / …); no separate graph
  glyph ABI for MVP.
- `edge_curve` meta (`straight` default): recorded on graph meta for client
  follow-up; MVP geometry stays straight segments.

Interactive path is primary; export must not reshape the hot path (§7).
Geometry remains segments + scatter buffers; the client draws uploaded
buffers only (MVP keeps straight segments regardless of `edge_curve` meta).

---

## 7. Export

- HTML / WebGL interactive: primary.
- SVG: circles + polylines from screen-bounded positions (host SVG writer).
- Native PNG display-list graph ops: follow-up; do not block interactive MVP.

---

## 8. ABI sketch (`ABI_VERSION` bump with each signature change)

| Symbol | Role |
|---|---|
| `xy_graph_layout` | One-shot layout → `out_x`/`out_y` f64 |
| `xy_graph_force_create` | Handle for progressive FR |
| `xy_graph_force_tick` | Advance k steps; write positions |
| `xy_graph_force_destroy` | Free handle |
| `xy_graph_build_csr` | `offsets`/`neighbors` u64 CSR |
| `xy_graph_sample_edges` | LOD edge index sample |
| `xy_graph_lod_decision` | Recorded tier decision (§28) |
| `xy_graph_cluster_aggregate` | LOD node centroid clusters + node→cluster membership + recorded tier |

Element counts and indices are `u64` / `uint64_t`.

---

## 9. Module layout

```
src/graph/
  mod.rs       # public layout + force + csr + lod
python/xy/
  _graph.py    # ingest helpers, id map, from_networkx thin
  marks.py     # graph() → layout ABI → segments + scatter
packages/xy-node/
  # thin N-API/ffi loader over same cdylib
```

Sankey and any other host-only layouts promote into Rust under the same
“Rust owns decisions” rule for dual-host MVP ([host-parity.md](host-parity.md)).
