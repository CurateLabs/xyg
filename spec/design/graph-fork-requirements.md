# Graph visualization — competitive research & fork requirements

**Status:** requirements locked and **ready for review**; implementation design in
[graph-mark.md](graph-mark.md). Runtime lands with the graph ABI / mark.

**Scope (hard):** core **data visualization** of graph data — node–link marks,
layouts that place them, visual encodings, interactive reading of the chart,
and scale. Nothing else.

**Out of scope:** graph editing/manipulation UIs, investigation chrome,
search/filter product UI, I/O format zoos, and graph-theory / analysis product
surfaces (centrality, community detection, pathfinding, Cypher, …).
**Algorithms and graph computation live in GraphForge** (and peers such as
NetworkX/igraph); this stack **plots** their outputs and does not reimplement
them. Competitor sections below mark what Sigma/vis/Ogma sell that we leave
alone.

**North star:** Graph data viz is the **core feature** (first-class node–link
charts; beat Plotly’s network UX; match Sigma/Ogma on WebGL + layout quality).
Other chart types keep the **same first-class feel and speed**
([host-parity.md](host-parity.md)).

**Host parity:** Python and Node for *all* chart types. Graph viz leads
dual-host delivery.

**Architecture principle:** **Rust owns decisions** that affect chart
behavior, buffers, layout, encodings, and LOD — not only O(N) loops.
Python and Node are thin bindings for ergonomics and I/O so parity and
performance stay identical ([host-parity.md](host-parity.md)). Display
layouts, channel resolution, and LOD aggregates live in the xy C ABI; JS
draws. Analysis algorithms stay in GraphForge (and peers).

---

## 1. What “core graph data viz” means

| In | Out |
|---|---|
| Nodes, edges, attributes used as visual channels | Mutating the graph in the widget (add/delete edge GUI) |
| Layout algorithms that assign (x, y) for display | Shortest path, PageRank, Louvain as chart features |
| WebGL draw of nodes/edges/arrows/labels | Node image programs, custom shader marketplaces |
| Color / size / width / shape encodings | Stylesheet selector engines, theme marketplaces |
| Pan, zoom, fit, hover, select, neighborhood highlight | Context menus, investigation workflows |
| Drag nodes to adjust a layout for reading | Collaborative editing, undo stacks |
| LOD so large graphs remain readable | Guaranteeing “millions of elements” without aggregation |
| `graph_chart(...)` with **xyg-native** column/sequence inputs *and* GraphForge/NX helpers | Replacing GraphForge algorithm stacks; dropping list/NumPy/pandas paths |

---

## 2. Competitor briefs (viz-only lens)

### 2.1 Sigma.js (+ graphology)

| Viz-relevant | Ignore |
|---|---|
| WebGL instanced nodes/edges; GPU picking; pan/zoom/hover | graphology metrics / community detection |
| Positions + color/size as first-class draw attrs | Create-node editing apps, custom node-image packages |
| Layout runs *outside* the renderer (graphology / workers) | React wrappers as a product line |

**Takeaway:** Sigma is the open **WebGL node–link performance** bar. Display
layouts belong in Rust; the client draws and reads.

### 2.2 vis-network

| Viz-relevant | Ignore |
|---|---|
| Force / hierarchical layouts that produce readable structure | Manipulation module (add/edit/delete GUI) |
| Node/edge style (shapes, arrows, groups, labels) | Configure UI / physics tuning chrome |
| Pan, zoom, select, hover, drag-to-reposition | Navigation-button chrome |

**Takeaway:** borrow **layout + style + read interaction**; do not fork the
editor. Prefer WebGL over Canvas.

### 2.3 D3 (`d3-force`)

| Viz-relevant | Ignore |
|---|---|
| Render-agnostic force simulation; tick → draw | Full SVG DIY customization surface |
| Composable forces, fixed nodes, alpha decay | Building charts from scratch in user code |

**Takeaway:** force **as a layout engine** with progressive ticks — not D3 as
the public API.

### 2.4 Ogma

| Viz-relevant | Ignore |
|---|---|
| WebGL-first node–link; layout catalog (force, hierarchical, radial, grid, concentric) | Enterprise support, fraud-investigation positioning |
| Animated layout into place; attribute styles | Edit/draw tools, framework wrapper suite |
| Scale + LOD expectations | Import connectors / commercial Jupyter extension |

**Takeaway:** Ogma’s **layout breadth and WebGL quality** matter; the rest of
the commercial surface does not.

### 2.5 NetworkX / igraph / GraphForge (algorithm sources)

| Viz-relevant | Ignore |
|---|---|
| Precomputed `pos` / metric columns as ordinary plot encodings | Replacing their analysis APIs |
| Optional helpers (`from_networkx`, GraphForge Arrow/subgraph adapters) | Making those helpers the *only* ingest path |

**Takeaway:** algorithms stay in GraphForge (and peers). Charts accept their
outputs **and** keep xy’s existing array/sequence/DataFrame-style inputs
first-class — GraphForge-as-primary must not erase those formats.

### 2.6 Plotly network UX (anti-pattern for viz API)

Plotly has no graph mark: users hand-build edge `Scatter` (`None`-separated
segments) + node `Scatter`, hide axes, and encode degree manually. Real apps
are pushed to **Dash + dash-cytoscape**.

**Must:** one `graph_chart` (or mark), named `layout=`, encodings, WebGL graph
semantics (neighborhood on hover), axis-free canvas, notebook `show()` —
without the boilerplate or a Cytoscape detour.

---

## 3. Competitive matrix (core viz only)

Legend: **M** = must, **S** = should, **—** = out of scope.

| Capability | Sigma | vis | D3 | Ogma | Plotly | XYG |
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
| xyg-native sequence/array/column ingest | n/a | limited | DIY | n/a | recipe | **M** (never drop) |
| Edge-list / table / NX / GraphForge helpers | n/a | via PyVis | n/a | n/a | recipe | **M** (GF primary OK) |
| Python + Node same layout/render buffers | partial | wrap | no | ext | split | **M** |
| Native PNG/SVG/HTML export | no | no | no | limited | kaleido | **M** |
| Editing / manipulation | app | **core** | DIY | yes | no | **—** |
| Analysis algorithms | graphology | no | DIY | yes | DIY | **—** (GraphForge et al.) |
| Search / filter product UI | app | yes | DIY | yes | no | **—** |
| Compounds / nested nodes | limited | poor | DIY | yes | no | **—** |

\*Sigma layouts live in graphology, not the renderer.

---

## 4. Fork requirements (normative, viz-only)

### 4.1 API (plotting surface)

- **REQ-API-1 (MUST).** First-class `graph_chart` / `network_chart` and a
  `graph` mark — not a scatter+segments recipe.
- **REQ-API-2 (MUST).** Nodes and edges with stable external IDs (string or
  int), optional attributes for encodings, optional preset `x`/`y`. Internally,
  element indices are **`u64`** (not `u32`) end-to-end in the graph ABI and
  buffers — `u32` has already proven too small for GraphForge-class scale and
  for xy’s own large-row paths; do not reintroduce that ceiling for graphs.
- **REQ-API-3 (MUST).** Ingest for plotting keeps **xyg-native input formats
  first-class** — the same kinds of values existing marks already accept for
  columns (Python sequences, NumPy arrays, pandas Series / DataFrame columns,
  Arrow-backed columns where xy already does). Graph marks MUST accept at
  least:
  - parallel node id / `x` / `y` / attribute columns;
  - edge `source` / `target` (/ weight) columns or edge-list pairs;
  - adjacency structures that compile to the same internal buffers.
- **REQ-API-3b (MUST).** Optional GraphForge-oriented helpers (Arrow table /
  subgraph → `graph_chart`) MAY be the **documented primary** path for
  GraphForge users, but MUST compile into the same mark/buffer path as
  xyg-native inputs. Shipping GraphForge helpers MUST NOT remove, gate, or
  degrade the xyg-native formats in REQ-API-3. For now the helper is **thin
  only**; this charting work is built **independently first** so the extension
  framework can be designed against a real target later — do not invent a
  heavy extension framework in this requirements pass.
- **REQ-API-3c (SHOULD).** `from_networkx(G, *, pos=None, ...)` preserves
  attributes used by encodings. Precomputed metric columns from GraphForge
  (or peers) are ordinary encoding channels — do not call their engines from
  the mark hot path.
- **REQ-API-4 (MUST).** Options follow [host-parity.md](host-parity.md): same
  names/defaults on Python and Node (idiomatic types may differ). Node hosts
  mirror the same format families via TypedArrays / arrays of numbers /
  Arrow where applicable — not GraphForge-only ingest.
- **REQ-API-5 (MUST).** Layout selection is a single parameter (e.g.
  `layout=...`) with a **documented default**. Every supported layout algorithm
  (preset, grid, circle, force variants, hierarchy/DAG, radial/concentric,
  `auto`, … as they ship) is selectable through that same parameter — not a
  one-off force-only API with other layouts bolted on sideways.

### 4.2 Engine placement

- **REQ-CORE-1 (MUST).** Display layout kernels, viz adjacency/position
  buffers, bulk channel resolution, and **layout/LOD decisions that change
  buffers** live in xy Rust (`xyg_graph_*` C ABI) with **`u64` element
  indices**. Rust owns these decisions for binding parity
  ([host-parity.md](host-parity.md)). Do not reimplement GraphForge algorithm
  surfaces here; do not leave layout/encode/decision logic in Python-only or
  Node-only code.
- **REQ-CORE-2 (MUST).** Positions and channels: canonical f64 in-core, §29 f32
  on the wire — no JSON numbers for geometry. Index planes that identify
  nodes/edges use **u64** (not u32).
- **REQ-CORE-3 (MUST).** JS does not run large-graph layout; it draws uploaded
  buffers and handles gestures.
- **REQ-CORE-4 (MUST).** Layout/LOD choices are recorded in the spec (§28);
  the decision computation runs in Rust whenever it affects buffers.
- **REQ-CORE-5 (MUST).** Graph is held to Python↔Node golden-buffer tests
  ([host-parity.md](host-parity.md)).
- **REQ-CORE-6 (MUST).** Progressive/cancelable layout tick architecture is
  specified in `graph-mark.md` before implementation: must be **performant at
  scale for both Python and Node** bindings (same Rust ticks; thin host
  schedulers). Further architectural detail is required; do not leave tick
  scheduling as an ad-hoc host detail.

### 4.3 Layout (display positioning)

- **REQ-LAY-1 (MUST).** Layout catalog is selected via the single `layout=`
  parameter (REQ-API-5). MVP includes at least: `preset`, `grid`, `circle`,
  one default force-directed algorithm, and one hierarchy (`breadthfirst`
  minimum). **Default** `layout=` is documented (recommend `force` or `auto`
  once `auto` exists — pick in `graph-mark.md`).
- **REQ-LAY-2 (MUST).** Force (and other iterative) layouts: cancel, iteration
  cap, progressive ticks to the client (REQ-CORE-6).
- **REQ-LAY-3 (SHOULD).** `layout="auto"` from size/structure.
- **REQ-LAY-4 (SHOULD).** DAG/hierarchical and radial/concentric — also via
  `layout=`, not separate entry points.
- **REQ-LAY-5 (MAY, shipped for CoSE).** Fixed/pinned nodes preserve authored
  f64 positions exactly; bounds conflicts fail closed. Other force families do
  not silently inherit CoSE pin semantics.
- **REQ-LAY-6 (MUST).** Additional layout algorithms added later remain
  callable through the same `layout=` parameter (string name or enum), with
  the original default unchanged unless a versioned migration says otherwise.

Live continuous “play with physics” configure UIs are **not** requirements; a
stabilize-then-draw force layout is enough for viz.

### 4.4 Render & encodings

- **REQ-REN-1 (MUST).** WebGL2 instanced nodes and edges.
- **REQ-REN-2 (MUST).** Directed arrows; straight edges (curved **SHOULD**).
- **REQ-REN-3 (MUST).** Discrete and continuous encodings for node color/size
  and edge color/width.
- **REQ-REN-4 (MUST).** Labels with zoom LOD.
- **REQ-REN-5 (SHOULD).** Additional node shapes and group/discrete styles.
- **REQ-REN-6 (MUST).** Graph marks participate in `to_png` / `to_svg` /
  `to_html` when practical, but **interactive graph performance is primary**.
  Export MUST NOT dictate data paths, LOD, or interaction architecture that
  would cripple interactivity. Prefer a simpler export path (e.g. SVG
  circles/polylines or existing capture) over blocking interactive MVP on
  full native graph display-list parity.

### 4.5 Interaction (reading the chart)

- **REQ-IX-1 (MUST).** Pan, zoom, fit, click select, multi-select, attribute
  hover.
- **REQ-IX-2 (MUST).** Neighborhood highlight on hover/select.
- **REQ-IX-3 (SHOULD).** Drag nodes; persist positions for export/re-layout.
- **REQ-IX-4 (SHOULD).** Box/lasso select via existing selection.

No REQ for mutation APIs, manipulation chrome, path-analysis product UI, or
filter UIs.

### 4.6 Scale

- **REQ-LOD-1 (MUST).** Graph interactive scale targets the **same class of
  claim as upstream xy scatter and other large marks**: screen-bounded work on
  interaction, with an explicit tier ladder, through the large regimes xy
  already advertises for scatter (10M / 100M / 1B-class *with* aggregation —
  dossier north star). Do not treat graphs as a “tens of thousands only”
  product while scatter claims billions.
- **REQ-LOD-2 (MUST).** Edge simplification / cluster aggregates (and any
  other graph LOD) are produced in Rust when over budget; JS draws aggregates.
- **REQ-LOD-3 (MUST).** Label/overlay budgets stay screen-bounded.
- **REQ-LOD-4 (MUST).** Evidence: build harness rows that exercise graph at the
  same scale bands used for scatter launch/large-data claims (adapted to
  node–link LOD), for **both** Python and Node bindings over the same Rust
  core.

### 4.7 Hosts

- **REQ-HOST-1 (MUST).** Jupyter/anywidget, Reflex, standalone HTML, and
  Node-hosted apps use the shared graph mark + client
  ([host-parity.md](host-parity.md)).
- **REQ-HOST-2 (MUST).** No Cytoscape.js / vis-network runtime dependency.

---

## 5. Delivery slices

| Slice | Requirements | Closes |
|---|---|---|
| **A — Spec + ABI** | CORE-* (incl. u64 indices, tick arch in `graph-mark.md`); [host-parity.md](host-parity.md); rust-engine amend (Rust owns decisions) | Dual-host foundation; no host-only layout leftovers in plan |
| **B — Graph viz + full chart dual-host MVP** | API-*; LAY-*; REN-* (interactive-first); IX-*; LOD-*; HOST-*; HOSTPARITY-* | Graph core feature **and** all chart types on Python+Node with Rust-owned layout/encode — no Python host-only shenanigans |
| **C — Layout & style depth** | LAY-3..6 expansions, REN curves/shapes, IX-3/4 | Broader `layout=` catalog + polish |
| **D — Evidence** | LOD-4 | Scale bands matching xy scatter claims on both bindings |

Slice B is intentionally broad: product MVP is not “graph only, Sankey later.”

---

## 6. Explicit non-goals

> **Amendment (#34):** Compound and nested node presentation is now in scope.
> Rust owns parent-forest validation, transitive compound bounds, collapse
> visibility/representatives, label budgets, and visual-state precedence
> through the canonical Scene path. Collapsing keeps the group node visible,
> hides every descendant, remaps boundary-edge endpoints to the nearest visible
> collapsed ancestor, omits newly internal edges, and propagates hidden
> selected/hovered/neighbor/pinned state to that ancestor. This reverses the
> earlier compound-node non-goal without adding a host-side policy path.

- Reimplementing GraphForge (or peer) analysis algorithms inside the charting
  stack.
- Graph editors, manipulation GUIs, collaborative editing.
- Search/filter chrome, node-image programs.
- Cytoscape Desktop / CX, Neo4j connectors, GEXF-as-platform.
- D3-level SVG DIY; shipping vis-network or Cytoscape.js.
- Unaggregated “billions of elements” claims without the same LOD discipline xy
  uses for scatter — measure at scatter-class bands (REQ-LOD-4).
- Demoting non-graph charts’ feel or speed to fund graph work.
- Making GraphForge (or NetworkX) the sole ingest path, or dropping xy’s
  sequence / NumPy / pandas / columnar input formats when GraphForge helpers
  become the documented primary.
- Crippling interactive graph paths to satisfy export parity.
- Keeping Python host-only layout/encode paths in MVP.

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

## 8. Decided courses of action (was: open questions)

| # | Decision | Course of action |
|---|---|---|
| 1 | Index width | Use **`u64`** for graph node/edge indices in the ABI and buffers. Do not use `u32` — it already limited GraphForge-class scale and xy large-row paths. External IDs remain string/int at the API; dense internal indices are u64. (CSR/wire packing details still land in `graph-mark.md`.) |
| 2 | Layout API | Single `layout=` parameter with a **default**; every layout algorithm is selectable through it as algorithms ship (REQ-API-5, REQ-LAY-*). |
| 3 | Progressive ticks | Needs a full architecture section in `graph-mark.md`. Must be performant at scale on **Python and Node** over the same Rust tick engine (REQ-CORE-6). |
| 4 | Export vs interactive | **Interactive primary.** Export matters but must not cripple interaction paths (REQ-REN-6). |
| 5 | Placement | **Rust owns decisions** for parity/performance. Amend rust-engine away from “Python owns decisions” for this product line ([host-parity.md](host-parity.md)). |
| 6 | MVP scope | **All charts / viz features in MVP** on both hosts; remove Python host-only layout/encode paths (promote Sankey etc. into Rust as part of MVP dual-host). |
| 7 | GraphForge helper | **Thin helper only** now. Build charting independently first; use that as the target to design any later extension framework. |
| 8 | Scale evidence | Test and build to the **same scale class xy claims for scatter and other large charts** (10M / 100M / 1B-class with screen-bounded LOD), on both bindings (REQ-LOD-1, REQ-LOD-4). |

## 9. Downstream

1. [host-parity.md](host-parity.md) — Rust owns decisions; all-charts MVP dual-host.
2. `spec/design/graph-mark.md` — wire/ID (`u64`), `layout=` catalog + default,
   **tick architecture at scale**, LOD ladder aligned to scatter claims.
3. [rust-engine.md](rust-engine.md) — replace “Python owns decisions” with Rust
   owns decisions for this line; add `graph` module; promote remaining host-only
   layouts (Sankey, …) into Rust for MVP.
4. [chart-roadmap.md](../api/chart-roadmap.md) status when implementation lands.
5. Capability-matrix regeneration once the `graph` mark exists.
6. Benchmarks: graph rows at scatter-class scale bands, Python and Node.
