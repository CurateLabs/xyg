# Graph visualization — competitive research & fork requirements

**Status:** requirements for **graphforge-xy**, the visualization extension of
[core GraphForge](https://github.com/CurateLabs/graphforge)
([graphforge-extension.md](graphforge-extension.md)). Authoritative input for
the network/tree/org family ([chart-roadmap.md](../api/chart-roadmap.md)
rank 31 / P4 rank 24) and for the future `graph-mark.md` design. Does not yet
change runtime behavior.

**Scope (hard):** core **data visualization** of graph data — node–link marks,
layouts that place them, visual encodings, interactive reading of the chart,
and scale. Nothing else.

**Out of scope:** graph editing/manipulation UIs, investigation/enterprise
chrome, search/filter product UI, I/O format zoos, and graph-theory / analysis
toolkits (centrality, community detection, pathfinding as a product surface).
**Those belong in core GraphForge** (Cypher, analyst verbs, algorithm catalog),
not in this viz extension. Competitor sections below mark what Sigma/vis/Ogma
sell that we deliberately leave to GraphForge or ignore.

**North star:** give GraphForge users a first-class node–link chart (beat
Plotly’s network UX; match Sigma/Ogma on WebGL + layout quality) without
forking the GraphForge engine.

**Host parity:** Python and Node for *all* chart types, matching GraphForge’s
dual-host matrix ([host-parity.md](host-parity.md)). Graph viz is the **lead
feature** of this extension.

**Architecture constraint:** display layouts and channel resolution over
|V|/|E| live in the **xy** Rust C ABI so both hosts share bit-identical viz
buffers. GraphForge remains the source of graph truth. The JS client owns
WebGL draw and gestures ([rust-engine.md](rust-engine.md) §1; dossier §29).

---

## 1. What “core graph data viz” means

| In | Out |
|---|---|
| Nodes, edges, attributes used as visual channels | Mutating the graph in the widget (add/delete edge GUI) |
| Layout algorithms that assign (x, y) for display | Shortest path, PageRank, Louvain as XY features |
| WebGL draw of nodes/edges/arrows/labels | Node image programs, custom shader marketplaces |
| Color / size / width / shape encodings | Stylesheet selector engines, theme marketplaces |
| Pan, zoom, fit, hover, select, neighborhood highlight | Context menus, investigation workflows, fraud tooling |
| Drag nodes to adjust a layout for reading | Collaborative editing, undo stacks |
| LOD so large graphs remain readable | Guaranteeing “millions of elements” without aggregation |
| `graph_chart(...)` / GraphForge Arrow·subgraph ingest for plotting | Replacing GraphForge storage/Cypher; GraphML/GEXF platforms |

---

## 2. Competitor briefs (viz-only lens)

### 2.1 Sigma.js (+ graphology)

| Viz-relevant | Ignore for XY fork |
|---|---|
| WebGL instanced nodes/edges; GPU picking; pan/zoom/hover | graphology metrics / community detection |
| Positions + color/size as first-class draw attrs | Create-node editing apps, custom node-image packages |
| Layout runs *outside* the renderer (graphology / workers) | React wrappers as a product line |

**Takeaway:** Sigma is the open **WebGL node–link performance** bar. Layouts
belong in Rust; the client draws and reads.

### 2.2 vis-network

| Viz-relevant | Ignore for XY fork |
|---|---|
| Force / hierarchical layouts that produce readable structure | Manipulation module (add/edit/delete GUI) |
| Node/edge style (shapes, arrows, groups, labels) | Configure UI / physics tuning chrome |
| Pan, zoom, select, hover, drag-to-reposition | Navigation-button chrome |

**Takeaway:** borrow **layout + style + read interaction**; do not fork the
editor. Prefer WebGL over Canvas.

### 2.3 D3 (`d3-force`)

| Viz-relevant | Ignore for XY fork |
|---|---|
| Render-agnostic force simulation; tick → draw | Full SVG DIY customization surface |
| Composable forces, fixed nodes, alpha decay | Building charts from scratch in user code |

**Takeaway:** force **as a layout engine** with progressive ticks — not D3 as
the public API.

### 2.4 Ogma

| Viz-relevant | Ignore for XY fork |
|---|---|
| WebGL-first node–link; layout catalog (force, hierarchical, radial, grid, concentric) | Enterprise support, fraud-investigation positioning |
| Animated layout into place; attribute styles | Edit/draw tools, framework wrapper suite |
| Scale + LOD expectations | Import connectors / commercial Jupyter extension |

**Takeaway:** Ogma’s **layout breadth and WebGL quality** matter; the rest of
the commercial surface does not.

### 2.5 GraphForge (data source) vs NetworkX / igraph

| Viz-relevant | Leave to core GraphForge / peers |
|---|---|
| GraphForge Arrow results and node/edge exports as **primary plot inputs** | Cypher, persistence, analyst verbs, algorithms |
| Optional NetworkX/`pos` only as a convenience adapter for plotting | Replacing NetworkX/igraph analysis APIs |
| Same Python + Node host matrix as GraphForge | Building a second graph engine inside xy |

**Takeaway:** this extension **visualizes** GraphForge graphs. Analysis stays
in GraphForge (or peer libs); xy owns display layout + render.

### 2.6 Plotly network UX (anti-pattern for viz API)

Plotly has no graph mark: users hand-build edge `Scatter` (`None`-separated
segments) + node `Scatter`, hide axes, and encode degree manually. Real apps
are pushed to **Dash + dash-cytoscape**.

**graphforge-xy must:** one `graph_chart` (or mark), named `layout=`,
encodings, WebGL graph semantics (neighborhood on hover), axis-free canvas,
notebook/`show()` — fed primarily from GraphForge — without the boilerplate or
a Cytoscape detour.

---

## 3. Competitive matrix (core viz only)

Legend: **M** = must, **S** = should, **—** = out of scope for this fork.

| Capability | Sigma | vis | D3 | Ogma | Plotly | XY |
|---|---|---|---|---|---|---|
| First-class graph mark / API | yes | yes | DIY | yes | no | **M** |
| WebGL nodes + edges | yes | no | DIY | yes | hack | **M** |
| Preset / grid / circle layout | yes* | yes | DIY | yes | DIY | **M** |
| Force layout (for display) | yes* | yes | yes | yes | DIY | **M** |
| Hierarchy / tree layout | limited | yes | DIY | yes | DIY | **M** |
| Progressive layout ticks | app | yes | yes | yes | no | **M** |
| Attr → color / size / width | yes | yes | DIY | yes | manual | **M** |
| Directed arrows | yes | yes | DIY | yes | weak | **M** |
| Labels + zoom LOD | yes | yes | DIY | yes | text | **M** |
| Pan / zoom / fit | yes | yes | DIY | yes | yes | **M** |
| Select + hover tooltips | yes | yes | DIY | yes | hover | **M** |
| Neighborhood highlight | pattern | hover | DIY | yes | no | **M** |
| Drag to adjust positions | yes | yes | yes | yes | no | **S** |
| Extra shapes / groups | packages | yes | DIY | yes | no | **S** |
| Curved edges | package | yes | DIY | yes | no | **S** |
| Box select | app | yes | DIY | yes | Dash | **S** |
| `from_graphforge` / edge-list ingest | n/a | via PyVis | n/a | n/a | recipe | **M** (GraphForge primary) |
| Python + Node same layout/render buffers | partial | wrap | no | ext | split | **M** (match GraphForge hosts) |
| Native PNG/SVG/HTML export | no | no | no | limited | kaleido | **M** |
| Editing / manipulation | app | **core** | DIY | yes | no | **—** |
| Analysis algorithms | graphology | no | DIY | yes | DIY | **—** |
| Search / filter product UI | app | yes | DIY | yes | no | **—** |
| Compounds / nested nodes | limited | poor | DIY | yes | no | **—** |

\*Sigma layouts live in graphology, not the renderer.

---

## 4. Fork requirements (normative, viz-only)

### 4.1 API (plotting surface)

- **REQ-API-1 (MUST).** First-class `graph_chart` / `network_chart` and a
  `graph` mark — not a scatter+segments recipe.
- **REQ-API-2 (MUST).** Nodes and edges with stable IDs, optional attributes for
  encodings, optional preset `x`/`y`.
- **REQ-API-3 (MUST).** Primary ingest from **GraphForge** (Arrow tables /
  subgraph or node–edge export) preserving attributes used by channels; also
  accept plain edge lists. `from_networkx` is a **SHOULD** convenience only.
- **REQ-API-4 (MUST).** Graph options follow [host-parity.md](host-parity.md):
  same names/defaults on Python and Node (idiomatic types may differ).
- **REQ-API-5 (MUST).** GraphForge remains optional at import for non-graph
  charts; graph ingest fails clearly if the adapter/engine is missing.
### 4.2 Engine placement

- **REQ-CORE-1 (MUST).** Display layout kernels + bulk channel resolution in
  **xy** Rust (`xy_graph_*` C ABI). Do not reimplement GraphForge storage or
  Cypher here; a viz-side adjacency/position buffer for layout is allowed.
- **REQ-CORE-2 (MUST).** Positions and channels: canonical f64 in-core, §29 f32
  on the wire — no JSON numbers for geometry.
- **REQ-CORE-3 (MUST).** JS does not run large-graph layout; it draws uploaded
  buffers and handles gestures.
- **REQ-CORE-4 (MUST).** Layout/LOD choices are recorded in the spec (§28).
- **REQ-CORE-5 (MUST).** Graph is the first mark with enforced Python↔Node
  golden-buffer tests (see REQ-HOSTPARITY-4).

### 4.3 Layout (display positioning)

- **REQ-LAY-1 (MUST).** `preset`, `grid`, `circle`, one force-directed, one
  hierarchy (`breadthfirst` minimum).
- **REQ-LAY-2 (MUST).** Force layout: cancel, iteration cap, progressive ticks
  to the client.
- **REQ-LAY-3 (SHOULD).** `layout="auto"` from size/structure.
- **REQ-LAY-4 (SHOULD).** DAG/hierarchical and radial/concentric for dependency
  and ego-style views.
- **REQ-LAY-5 (MAY).** Fixed/pinned nodes during force.

Live continuous “play with physics” modes and physics configure UIs are **not**
requirements; a stabilize-then-draw force layout is enough for viz.

### 4.4 Render & encodings

- **REQ-REN-1 (MUST).** WebGL2 instanced nodes and edges.
- **REQ-REN-2 (MUST).** Directed arrows; straight edges (curved **SHOULD**).
- **REQ-REN-3 (MUST).** Discrete and continuous encodings for node color/size
  and edge color/width.
- **REQ-REN-4 (MUST).** Labels with zoom LOD.
- **REQ-REN-5 (SHOULD).** Additional node shapes and group/discrete styles.
- **REQ-REN-6 (MUST).** Graph marks participate in XY `to_png` / `to_svg` /
  `to_html`.

### 4.5 Interaction (reading the chart)

- **REQ-IX-1 (MUST).** Pan, zoom, fit, click select, multi-select, attribute
  hover.
- **REQ-IX-2 (MUST).** Neighborhood highlight on hover/select.
- **REQ-IX-3 (SHOULD).** Drag nodes; persist positions for export/re-layout.
- **REQ-IX-4 (SHOULD).** Box/lasso select via existing XY selection.

No REQ for mutation APIs, manipulation chrome, path-analysis highlighting, or
filter UIs.

### 4.6 Scale

- **REQ-LOD-1 (MUST).** Published direct vs aggregated tiers with explicit spec
  fields.
- **REQ-LOD-2 (SHOULD).** Edge simplification / cluster aggregates from Rust
  when over budget.
- **REQ-LOD-3 (MUST).** Label/overlay budgets stay screen-bounded.

### 4.7 Hosts

- **REQ-HOST-1 (MUST).** Jupyter/anywidget, Reflex, standalone HTML, and
  Node-hosted apps use the shared graph mark + client
  ([host-parity.md](host-parity.md)).
- **REQ-HOST-2 (MUST).** No Cytoscape.js / vis-network runtime dependency.

---

## 5. Delivery slices (viz only)

| Slice | Requirements | Closes |
|---|---|---|
| **A — Spec + ABI** | CORE-*; platform [host-parity.md](host-parity.md) | Dual-host foundation for all marks |
| **B — MVP graph viz** | API-1..3, LAY-1/2, REN-1..4/6, IX-1/2, LOD-1/3, HOST-* | Plotly gap; Sigma display+explore (**main need**) |
| **C — Layout & style depth** | LAY-3..5, REN-2 curve / REN-5, IX-3/4 | vis/Ogma/D3 viz quality |
| **D — Dual-host graph parity** | API-4, CORE-5, HOSTPARITY-* | Graph proves Python↔Node; then other chart types on Node |

---

## 6. Explicit non-goals

- Replacing or forking core GraphForge (engine, Cypher, storage, algorithms).
- Graph editors, manipulation GUIs, collaborative editing.
- Analysis product surface in xy — use GraphForge (or peers) and plot results
  as attributes.
- Search/filter chrome, compounds/nested nodes, node-image programs.
- Cytoscape Desktop / CX, Neo4j connectors, GEXF-as-platform.
- D3-level SVG DIY; shipping vis-network or Cytoscape.js inside xy.
- Unaggregated “millions of nodes” claims without measured LOD.

---

## 7. Sources

- [Sigma.js](https://www.sigmajs.org/), [Sigma v3](https://www.ouestware.com/2024/03/21/sigma-js-3-0-en/)
- [vis-network](https://visjs.github.io/vis-network/docs/network/)
- [d3-force](https://d3js.org/d3-force)
- [Ogma](https://linkurious.com/ogma/) / [layouts](https://doc.linkurious.com/ogma/latest/api/ogma/layouts.html)
- [NetworkX drawing](https://networkx.org/documentation/stable/reference/drawing.html)
- [igraph Python visualisation](https://python.igraph.org/en/main/visualisation.html)
- [Plotly network graphs](https://plotly.com/python/network-graphs/)

---

## 8. Downstream

1. [graphforge-extension.md](graphforge-extension.md) — product split vs core
   GraphForge.
2. [host-parity.md](host-parity.md) — Python↔Node for all chart types; graph is
   the lead feature.
3. `spec/design/graph-mark.md` — data model, wire buffers, layout catalog, LOD,
   GraphForge ingest contract.
4. [rust-engine.md](rust-engine.md) — `graph` viz module (layout + channels).
5. [chart-roadmap.md](../api/chart-roadmap.md) status when implementation lands.
6. Capability-matrix regeneration once the `graph` mark exists in code.
