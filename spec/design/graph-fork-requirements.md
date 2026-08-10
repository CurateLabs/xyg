# Graph visualization — competitive research & fork requirements

**Status:** requirements. Authoritative input for the network/tree/org family
([chart-roadmap.md](../api/chart-roadmap.md) rank 31 / P4 rank 24) and for the
future `graph-mark.md` design. Does not yet change runtime behavior.

**North star:** XY should absorb the *product lessons* of dedicated graph tools
(Sigma, vis-network, Ogma, Cytoscape-class) and the *ecosystem seams* of
NetworkX/igraph, while beating Plotly’s network UX on first-class API,
performance, and interaction depth. Analysis depth may interoperate with
NetworkX/igraph rather than re-implement every algorithm.

**Architecture constraint:** layouts, graph store kernels, and O(|V|+|E|)
analysis that XY owns live in the Rust C ABI so Python and Node hosts share
bit-identical results. The JS client owns WebGL draw and gestures only
([rust-engine.md](rust-engine.md) §1; dossier §29).

---

## 1. Competitor briefs

### 1.1 Sigma.js (+ graphology)

| Dimension | What they ship | Lesson for XY |
|---|---|---|
| Role split | **graphology** = data model + layouts/metrics; **sigma** = WebGL render + interaction | Same split XY already uses: native core vs thin render client |
| Render | WebGL, instanced programs, GPU picking (v3+) | Match: instanced nodes/edges, picking buffer, not Canvas |
| Scale claim | Thousands of nodes/edges smoothly; memory-conscious instancing | XY target: comfortable 1e4–5e4 interactive; aggregate beyond |
| Layouts / algos | *Not* in sigma — ForceAtlas2, metrics, communities live in graphology (often workers) | Put ForceAtlas2-class / CoSE-class in **Rust**, not JS |
| UX loops | Display preset graphs; explore (search, neighborhood on hover); create/drag nodes; custom node programs (images, curved edges as packages) | MVP = display+explore; editing = later; custom programs via style channels first |
| Hosts | Browser + `@react-sigma`; **ipysigma** Jupyter widget | Python notebook + Reflex + Node must all hit the same mark |

**Fork takeaway:** treat Sigma as the open WebGL performance bar. Do not put
layout in the browser hot path; do ship neighborhood highlight, search-to-focus,
and progressive position updates.

### 1.2 vis-network (vis.js)

| Dimension | What they ship | Lesson for XY |
|---|---|---|
| Render | Canvas (not WebGL-first) | Keep WebGL; do not copy Canvas as the primary path |
| Physics | Live Barnes–Hut / repulsion / spring solvers; hierarchical repulsion; **stabilization**; configure UI to tune physics | Users expect *live* physics *or* a clear stabilize-then-freeze; expose both modes |
| Layout | Random seed, improvedLayout, hierarchical | Hierarchical + force are table stakes |
| Manipulation | Built-in add/edit/delete nodes and edges GUI + API | Editable graphs are a product differentiator vs Plotly; ship API hooks first, optional chrome later |
| Style | Rich node shapes, groups, edge arrows/smooth/dashes, labels inside/outside | Groups + discrete style maps matter as much as continuous scales |
| Interaction | dragNodes, zoomView, select, hover, navigation buttons, popups | Match interaction depth; nav chrome can stay optional |

**Fork takeaway:** vis-network wins on **editable, physics-playful UX** at modest
scale. XY must cover that UX loop without inheriting Canvas scale limits.

### 1.3 D3.js (`d3-force` and friends)

| Dimension | What they ship | Lesson for XY |
|---|---|---|
| Model | Force simulation as a **render-agnostic** integrator; tick → you draw SVG/Canvas/WebGL | Layout engine ≠ renderer (aligns with Rust ticks → f32 uploads) |
| Control | Composable forces (link, manyBody, center, collide, x/y); pin nodes; alpha decay | Expose force parameters and fixed nodes; do not hard-code one spring preset |
| Customization | Total visual control; steep API; SVG dies at ~hundreds–low thousands | Win on defaults + encodings; leave “every SVG path” to D3 |
| Guidance | Large static layouts should run off the UI thread | Native/Rust (or worker) layouts; never freeze the chart thread |

**Fork takeaway:** borrow D3’s **force composition contract** (named forces,
fixed nodes, tick streaming), not its SVG-first DIY surface.

### 1.4 Ogma (Linkurious, commercial)

| Dimension | What they ship | Lesson for XY |
|---|---|---|
| Render | WebGL-first; Canvas/SVG fallbacks with unified API | WebGL primary; native PNG/SVG export already fits XY static path |
| Scale marketing | Tens of thousands in seconds; enterprise fraud / investigation apps | Set explicit scale tiers and LOD (cluster / hide labels / haystack edges) |
| Layouts | force, forceLink, hierarchical, sequential, radial, grid, concentric; Promise/`onEnd`; animate camera | Async layout + animate-into-place is expected enterprise UX |
| Product surface | Import/export, filter, select, edit/draw, stylesheets, framework wrappers, Jupyter extension, support | Interop + notebook + app hosts matter as much as shaders |
| Positioning | Sells vs D3/vis/sigma on performance + batteries-included + support | XY’s open wedge: same batteries, dual-language hosts, large-data DNA |

**Fork takeaway:** Ogma is the **enterprise completeness** checklist — layout
breadth, animated layout, filter/select/edit, notebook + web app. XY’s open-source
fork does not need Linkurious support, but must not look half-finished beside it
on the viz surface.

### 1.5 NetworkX (Python)

| Dimension | What they ship | Lesson for XY |
|---|---|---|
| Role | Graph **creation, manipulation, study**; drawing is explicitly secondary | Do not try to replace NetworkX analysis; **ingest** it |
| Layouts | Many: spring/FR, ForceAtlas2, Kamada–Kawai, circular, shell, spectral, bipartite, BFS, planar, multipartite, … | Prefer ingesting `pos=` / exporting layouts; implement a **small** native layout set in Rust |
| Viz pairing | Matplotlib (`draw_*`), export to Gephi/Cytoscape, **PyVis** (vis-network), Plotly recipes | First-class `from_networkx` / edge-list / adjacency ingest is mandatory |
| Own advice | “Graph visualization is hard; use dedicated tools” | XY *is* that dedicated tool for Python (and Node) |

**Fork takeaway:** NetworkX is an **upstream data/analysis** dependency, not a
viz competitor. Fork requirement: zero-friction round-trip (attrs preserved).

### 1.6 igraph (C core; Python / R / Mathematica)

| Dimension | What they ship | Lesson for XY |
|---|---|---|
| Role | Fast cross-language **analysis** (+ layouts + basic plot) | Same dual-host lesson XY wants: one C core, many bindings |
| Scale | Designed for huge graphs (analysis); viz backends are Cairo/matplotlib/plotly — not WebGL networks | Pair: igraph/NetworkX analyze → XY visualize at interactive scale |
| Layouts | FR, KK, DrL, LGL, Sugiyama/tree, auto layout picker, … | `layout="auto"` heuristic is a good UX default |
| Interop | In-memory convert to/from NetworkX, graph-tool, pandas, PyTorch Geometric | Document converters; optional adapters over reinventing ML export |

**Fork takeaway:** igraph validates **C-core multi-language parity**. XY’s Rust
cdylib + Python ctypes + Node N-API is the same product shape for *visualization*
kernels (layouts we own, buffer export), while remaining friendly to igraph as
an analysis peer.

### 1.7 Plotly network UX (the experience to beat)

Plotly has **no first-class network mark**. The documented path is:

1. Build a NetworkX graph and compute positions (`pos` / geometric graph).
2. Manually build an edge `go.Scatter` with `None`-separated segments.
3. Build a node `go.Scatter` markers trace; encode degree into color/size by hand.
4. Hide axes; enable `hovermode='closest'`.
5. For real apps, Plotly’s own docs push **Dash + `dash-cytoscape`** — admitting
   the chart library is not the network product.

**UX failures XY must not copy**

| Plotly friction | XY requirement |
|---|---|
| Boilerplate edge/node traces | `graph_chart(nodes=..., edges=...)` or `from_networkx(G)` |
| Layout outsourced entirely | Named `layout=` with native defaults + `preset` |
| No graph semantics (neighborhood, path highlight) | First-class hover/select neighborhood |
| No drag-to-relayout / physics | Optional physics or drag-pin with layout resume |
| No editing | Deferred but API-shaped (`on_node_add` etc.) |
| Scale ceiling of Scatter/Scattergl hairballs | WebGL graph mark + LOD + native layout |
| Dash users leave Plotly for Cytoscape | Keep users inside XY for notebook, Reflex, Node |

**What Plotly still gets right (keep)**

- Hover text for node attributes / degree
- Colorbar / continuous encoding of a node metric
- Pan/zoom on a clean, axis-free canvas
- Easy notebook `show()`

---

## 2. Competitive feature matrix

Legend: **M** = must for XY MVP fork, **S** = should for parity, **L** = later,
**—** = out of scope / peer tool.

| Capability | Sigma | vis-net | D3 | Ogma | NX | igraph | Plotly net | XY fork |
|---|---|---|---|---|---|---|---|---|
| First-class graph API | yes | yes | DIY | yes | data | data+plot | no | **M** |
| WebGL node–link render | yes | no | DIY | yes | no | no | Scattergl hack | **M** |
| Preset / grid / circle layouts | via graphology | yes | DIY | yes | yes | yes | DIY | **M** |
| Force / physics layout | FA2 (graphology) | live physics | d3-force | force/forceLink | spring/FA2 | FR/KK/DrL | DIY | **M** |
| Hierarchical / DAG / tree | limited | hierarchical | DIY | hier/seq/radial | bfs/multi | Sugiyama/RT | DIY | **M** (breadthfirst; DAG **S**) |
| Progressive / animated layout | tick via app | continuous | ticks | Promise+duration | static | static | no | **M** |
| Attribute → color/size/width | yes | groups+opts | DIY | styles | draw attrs | plot attrs | manual | **M** |
| Arrows / directed edges | yes | yes | DIY | yes | draw | plot | weak | **M** |
| Labels + zoom LOD | yes | yes | DIY | yes | static | static | text mode | **M** |
| Pan / zoom / fit | yes | yes | DIY | yes | no | limited | yes | **M** |
| Select + multi-select | yes | yes | DIY | yes | no | no | limited | **M** |
| Hover neighborhood | common pattern | hover | DIY | yes | no | no | node only | **M** |
| Drag nodes | yes | yes | yes | yes | no | no | no | **M** |
| Box / lasso select | app-level | yes | DIY | yes | no | no | Dash | **S** |
| Live physics while interacting | app | **core** | yes | yes | no | no | no | **S** |
| Graph editing (add/remove) | app patterns | **manipulation** | DIY | edit/draw | mutate data | mutate | no | **S** (API); GUI **L** |
| Compounds / nested nodes | limited | poor | DIY | yes | no | no | no | **L** |
| Node images / custom programs | packages | images | total | yes | no | no | no | **L** |
| Curved / bundled edges | edge-curve pkg | smooth | DIY | yes | no | no | no | **S** curve; bundle **L** |
| Search / filter UI | app | filter/configure | DIY | yes | no | no | no | **S** filter API; UI **L** |
| GEXF / GraphML I/O | common | limited | DIY | yes | yes | yes | no | **S** |
| Shortest path / centrality viz | via graphology | no | DIY | yes | **yes** | **yes** | DIY | **S** (consume or thin native) |
| Community detection | graphology | no | DIY | yes | yes | yes | no | **L** / peer |
| `from_networkx` / igraph ingest | n/a | via PyVis | n/a | n/a | — | convert | recipe | **M** (NX); igraph **S** |
| Python + JS/Node same engine | ipysigma≠core | PyVis wrap | no | Jupyter ext | Py only | C+bindings | Py/JS split | **M** dual host |
| Native static export | no | no | no | limited | mpl | Cairo/mpl | kaleido | **M** (reuse XY PNG/SVG) |

---

## 3. Fork requirements (normative)

Requirements use **MUST** / **SHOULD** / **MAY**. IDs are stable for tracking in
`graph-mark.md` and tests.

### 3.1 Product shape

- **REQ-API-1 (MUST).** Ship a first-class composition surface
  `graph_chart` / `network_chart` (and a `graph` mark) — not a scatter+segments
  recipe. Plotly’s NetworkX cookbook is an explicit anti-goal.
- **REQ-API-2 (MUST).** Accept nodes and edges with stable IDs, optional
  columnar attributes, and optional preset `x`/`y`.
- **REQ-API-3 (MUST).** Provide `from_networkx(G, *, pos=None, ...)` that
  preserves node/edge attributes used by encodings.
- **REQ-API-4 (SHOULD).** Provide igraph / edge-list / GraphML·GEXF ingest
  helpers without requiring those packages at import time.
- **REQ-API-5 (MUST).** Python and Node public options share the same names,
  defaults, and layout/encoding semantics (idiomatic types only differ).

### 3.2 Engine placement (parity)

- **REQ-CORE-1 (MUST).** Graph store (CSR/COO + attr columns), layout kernels,
  and XY-owned analysis kernels live in Rust behind the C ABI (`xy_graph_*`).
- **REQ-CORE-2 (MUST).** Layout outputs and style channel buffers export as
  canonical f64 internally and §29 f32 wire buffers — no JSON numbers for
  geometry.
- **REQ-CORE-3 (MUST).** The JS client MUST NOT run O(|V|+|E|) layout or path
  algorithms for large graphs; it applies uploaded positions and draws.
- **REQ-CORE-4 (MUST).** Every layout/LOD decision is named in the figure spec
  (§28) — never silent tier switches.
- **REQ-CORE-5 (SHOULD).** Node N-API (or equivalent) loads the **same** cdylib
  exports as Python ctypes so golden graphs produce byte-identical position
  buffers across hosts.

### 3.3 Layouts & physics

- **REQ-LAY-1 (MUST).** Layout catalog MVP: `preset`, `grid`, `circle`, one
  force-directed (CoSE- or FA2-class), one hierarchy (`breadthfirst` minimum).
- **REQ-LAY-2 (MUST).** Force layout supports cancel, max iterations, and
  progressive tick streaming to the client (D3/Ogma/vis lesson).
- **REQ-LAY-3 (SHOULD).** `layout="auto"` picks among circle/grid/force/hierarchy
  from size and structure (igraph lesson).
- **REQ-LAY-4 (SHOULD).** Live physics mode (vis-network): optional continuous
  solver with stabilize-then-freeze default for notebooks.
- **REQ-LAY-5 (SHOULD).** DAG/hierarchical and radial/concentric layouts for org
  / dependency / ego-network views (Ogma checklist).
- **REQ-LAY-6 (MAY).** Pin/fixed nodes during force (D3 `fx`/`fy`).

### 3.4 Rendering & style

- **REQ-REN-1 (MUST).** WebGL2 instanced nodes and edges (Sigma/Ogma bar).
- **REQ-REN-2 (MUST).** Directed arrows; straight edges; simple curved edges
  (**SHOULD**).
- **REQ-REN-3 (MUST).** Discrete and continuous encodings for node color/size
  and edge color/width (Plotly degree-color pattern, without boilerplate).
- **REQ-REN-4 (MUST).** Labels with zoom-based LOD (hide/simplify when dense).
- **REQ-REN-5 (SHOULD).** Node shape set beyond circle (rect, diamond, …) and
  group styles (vis groups).
- **REQ-REN-6 (MUST).** Static `to_png` / `to_svg` / `to_html` reuse XY export
  paths for graph marks.
- **REQ-REN-7 (MAY).** Node images / custom programs (Sigma packages) after
  channel/style MVP.

### 3.5 Interaction & editing

- **REQ-IX-1 (MUST).** Pan, zoom, fit, click select, multi-select, hover
  tooltip with attributes.
- **REQ-IX-2 (MUST).** Hover (and select) **neighborhood** highlight — the
  Sigma “explore” loop Plotly lacks.
- **REQ-IX-3 (MUST).** Drag nodes; write positions back through the ABI so
  re-layout and export see them.
- **REQ-IX-4 (SHOULD).** Box or lasso select (reuse XY selection machinery).
- **REQ-IX-5 (SHOULD).** Filter API by attribute (show/hide); optional UI later.
- **REQ-IX-6 (SHOULD).** Mutation API: add/remove/update nodes and edges with
  batched updates (vis/Ogma); optional manipulation chrome **MAY** follow.
- **REQ-IX-7 (MAY).** Path highlight from analysis results (Dijkstra etc.).

### 3.6 Analysis boundary

- **REQ-AN-1 (MUST).** Document NetworkX/igraph as first-class analysis peers;
  XY visualizes their outputs without forcing users to leave the stack.
- **REQ-AN-2 (SHOULD).** Optional native helpers: degree, BFS/DFS neighborhood,
  shortest path, connected components — enough to drive encodings/highlights
  without a round-trip when peers are absent.
- **REQ-AN-3 (MAY).** Community detection / betweenness-at-scale as an extra or
  peer-delegated; not an MVP blocker.

### 3.7 Scale & LOD

- **REQ-LOD-1 (MUST).** Define published scale tiers (e.g. direct <~50k
  elements; aggregated beyond) with explicit spec fields.
- **REQ-LOD-2 (SHOULD).** Edge simplification (haystack / sample) and cluster
  collapse produced in Rust, drawn as aggregates in JS.
- **REQ-LOD-3 (MUST).** Label and overlay budgets stay screen-bounded.

### 3.8 Hosts & distribution

- **REQ-HOST-1 (MUST).** Works in Jupyter/anywidget, Reflex, standalone HTML,
  and Node-hosted apps via the shared client.
- **REQ-HOST-2 (SHOULD).** Amend dossier §32 from “Python-only forever” to
  “Python shipping host + Node parity host over one C ABI” when Node lands.
- **REQ-HOST-3 (MUST).** No Cytoscape.js or vis-network runtime dependency in
  the shipped client — XY owns the graph mark.

---

## 4. Prioritized delivery slices

Mapped from the matrix; evidence each slice must leave behind.

| Slice | Delivers requirements | Primary competitors closed |
|---|---|---|
| **A — Spec + ABI** | CORE-*, API shape | igraph dual-host lesson |
| **B — MVP viz** | API-1..3, LAY-1/2, REN-1..4/6, IX-1..3, LOD-1/3, HOST-1/3 | Plotly UX gap; Sigma display+explore |
| **C — Force quality + hierarchy** | LAY-3..6, REN-5, curved edges | vis physics; Ogma layout breadth; D3 force knobs |
| **D — Node host parity** | API-5, CORE-5, HOST-2 | igraph/Sigma multi-host |
| **E — Edit + filter + analysis** | IX-4..7, AN-*, LOD-2 | vis manipulation; Ogma explore; NX/igraph peer |

---

## 5. Explicit non-goals

- Replacing NetworkX or igraph as analysis libraries.
- Cytoscape Desktop / CX ecosystem compatibility as a release gate.
- SVG-first DIY customization at D3 depth.
- Shipping vis-network or Cytoscape.js inside XY.
- Guaranteeing Ogma’s commercial support surface or “millions of elements”
  without aggregation — claims must follow measured LOD tiers.

---

## 6. Sources (research pass)

- [Sigma.js](https://www.sigmajs.org/) — architecture (graphology + sigma), WebGL, use cases.
- [Sigma v3 notes](https://www.ouestware.com/2024/03/21/sigma-js-3-0-en/) — instancing, picking, curved edges.
- [vis-network docs](https://visjs.github.io/vis-network/docs/network/) — physics, manipulation, modules.
- [d3-force](https://d3js.org/d3-force) — render-agnostic simulation, tick model.
- [Ogma](https://linkurious.com/ogma/) / [Ogma layouts API](https://doc.linkurious.com/ogma/latest/api/ogma/layouts.html) — enterprise layout & product surface.
- [NetworkX drawing](https://networkx.org/documentation/stable/reference/drawing.html) — layouts; “use dedicated viz tools”.
- [PyVis](https://pyvis.readthedocs.io/) — NetworkX → vis-network bridge (UX users already know).
- [igraph Python visualisation](https://python.igraph.org/en/main/visualisation.html); igraph 1.0 multi-language design.
- [Plotly network graphs](https://plotly.com/python/network-graphs/) — Scatter recipe; Dash+cytoscape redirect.

---

## 7. Downstream docs

When implementation starts, split this file’s normative requirements into:

1. `spec/design/graph-mark.md` — data model, wire buffers, layout catalog, LOD.
2. Updates to [rust-engine.md](rust-engine.md) — `graph` module placement.
3. Updates to [chart-roadmap.md](../api/chart-roadmap.md) status rows.
4. Capability-matrix regeneration once the `graph` mark exists in code.
