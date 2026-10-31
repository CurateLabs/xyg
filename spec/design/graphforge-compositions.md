# GraphForge result compositions

**Status:** implementation design (xyg#37; unblocks CurateLabs/graphforge-vscode#80).
Authoritative for GraphForge result recognition, UUID joins, identity
policies, generation checks, the `XYGQ` request / `XYGF` composition
document, and how compositions paint. Related: [graph-mark.md](graph-mark.md)
(the mark compositions paint through), [host-parity.md](host-parity.md),
[browser-wasm.md](browser-wasm.md).

GraphForge Core computes; XYG composes and renders. XYG never executes a
GraphForge algorithm and never recommends a chart: every result layer carries
an explicit caller intent, and every schema has one documented composition.

## 1. Architecture

```text
GraphForge (engine) ── Arrow IPC bytes ──┐  result tables + base-graph entity tables
extension / host    ── generation UUIDs, intent, policy words
                                          ▼
Host adapter (Node JS today; browser TS twin with WASM parity)
  · frames bytes into one XYGQ request (no decoding, no joins)
                                          ▼
Rust  xyg_engine::graphforge  (native C ABI and, with WASM parity, the browser)
  · arrow_ipc: bounded Arrow IPC reader (stream + file, V4/V5)
  · recognize: schema from graphforge.* metadata + field-type checks
  · base: canonical base graph from entity tables / UUID planes
  · compose: UUID joins, missing/extra policy, generation checks,
             channel ownership, semantic planes, legend, decisions
                                          ▼
XYGF document (identity + planes + provenance + value-free diagnostics)
                                          ▼
Host paints through the existing graph mark (Rust layout / LOD / paint)
```

Rust owns result-schema dispatch, joins, membership/provenance, dimensional
decisions, and the planes. Hosts own only transport and presentation; the
TypeScript/Node adapters never hold a second analytical registry.

## 2. Arrow IPC ingress

`crates/xyg-engine/src/arrow_ipc.rs` is a dependency-free reader for the
bytes GraphForge returns. Accepted: little-endian IPC streams and files,
metadata V4/V5, uncompressed bodies, any number of record batches. Rejected
with `GF_ARROW_UNSUPPORTED`: dictionary encoding, compressed bodies,
big-endian data, tensors. Every flatbuffer offset, buffer range, offsets
array, validity bitmap, UTF-8 value, and child length is validated before a
value is read; malformed input fails with `GF_ARROW_MALFORMED` and never
panics (truncation and byte-flip fuzz tests over the fixture corpus). Types a
composition never reads (unions, maps, views, run-end encoding) are walked for
buffer accounting only.

| Bound | Value |
|---|---|
| Fields per schema (nested included) / depth | 4,096 / 16 |
| Schema metadata entries / key bytes / value bytes | 64 / 256 / 1,024 |
| Record batches / rows per table | 2^20 / 2^31 |

Exceeding a bound fails with `GF_ARROW_LIMIT`.

## 3. Recognition and the coverage ledger

Algorithm results are recognized from schema metadata only:
`graphforge.verb` ∈ {rank, cluster, similar, paths, analyze},
`graphforge.algorithm`, and `graphforge.algorithm_schema_version` (must be
`1`). `find` results use `graphforge.verb=find` and
`graphforge.search_schema_version` (must be `1`). Embedding metadata such as
`graphforge.dimensions` stays attached to the table. Nothing is inferred from
column names or values for these results. Cypher results (entity structs) are
base-graph material, not result layers (`GF_RESULT_NOT_ALGORITHM`).

After the ledger lookup, every canonical field must exist with its Arrow kind:
`uuid` = `FixedSizeBinary(16)`, `uuid-list` = `List<FixedSizeBinary(16)>`,
`float`/`int` = any width, `utf8`, `bool`, `float-vector` =
`List`/`FixedSizeList` of floats. Leading canonical fields are followed by
nullable node properties in rank/cluster/find results; those are carried, not
checked.

The authoritative disposition/composition ledger lives in
`crates/xyg-engine/src/graphforge/ledger.rs`, with this XYG-owned table as its
reviewable document. Python `graphforge_ledger()`, Node `graphforgeLedger()`,
and `xyg_graphforge_ledger_tsv` expose the runtime form; hosts do not maintain
another registry. A Rust test requires this table to match the code.

Core owns algorithm descriptors and Arrow schema facts. The pinned corpus in
`tests/fixtures/graphforge/core` is exported from Core's own Rust registry
and descriptor iterator at the immutable commit in `provenance.json`.
CI retrieves those exact Core sources and regenerates the corpus in check
mode; changed exported facts fail the build. Rust also requires every Core
algorithm/version/canonical field to map to the ledger and agree with the
real Core-produced IPC fixtures (including field order, nullable flags,
integer signedness/width, and float widths). Variable embedding dimensions
remain Core's `Float32List` family, admitting its fixed-size list encoding.
The editor's previous vendored ledger is removed from XYG; editor issue #90
replaces its own copy with a runtime coverage test against this authority.

### Qualified Core releases and version rejection (#936)

`python/xyg/graphforge-compatibility.json` is the single release declaration.
It ships in the Python package and is copied unchanged to the Node facade
and browser package roots. The release-cohort verifier rejects missing or
different declarations and records its hash and exact supported Core
versions in the release evidence. This is release metadata, not a client
handshake or a substitute for per-result schema validation.

Qualified exact releases are **Core 0.5.2** (94 algorithm results) and
**Core 0.6.0-rc.5** (96 algorithm results), each with its own pinned Core-owned
schema/descriptor corpus, real published-binding IPC run, `find` fixture,
and native/Python/Node/WASM composition evidence. The rc.5 corpus lives in
`tests/fixtures/graphforge/core/0.6.0-rc.5` and its 112 real fixtures in
`tests/fixtures/graphforge/results-0.6.0-rc.5`; the original 0.5.2 evidence
is preserved. Ledger contents version 2 adds `path-cost`: `bfs_depth` and
`dijkstra_cost` draw derived endpoint pairs carrying `cost`, without inferring
an ordered path or a persisted relationship.

This declares no version interval, later release candidate, or installable
editor pairing. #108/#884 still require the actual Core/XYG artifact cohort
and package-level installation evidence; equal RC suffixes are not a
compatibility rule. Editor #90 consumes a published qualified XYG package
before deleting its copy and retaining runtime-ledger coverage.

During composition, an unsupported numeric result version retains the
stable `GF_RESULT_SCHEMA_VERSION` code and now reports, for example,
`node-score result schema version 2 is not supported (expected 1)`, followed
by a next action to use a declared-compatible Core or upgrade XYG. Search
versions name the `search` schema. Missing/malformed version metadata is
reported as `(missing or invalid)` without echoing arbitrary metadata.
No row values, identities, or paths enter the error. All hosts surface the
same Rust error document; requesting `table` does not bypass rejection.
There is no ABI, request, Scene, or composition-wire version change.

<!-- graphforge-ledger:begin -->
| Schema | Disposition | Composition | Intents | Algorithms |
|---|---|---|---|---|
| `node-score` | node-layer | node-score | graph | pagerank, betweenness, closeness, harmonic_closeness, degree, eigenvector, article_rank, hits_hub, hits_authority, celf, clustering_coefficient, local_clustering_coefficient, triangles, k_core, preferential_attachment, adamic_adar, common_neighbors, resource_allocation, total_neighbors |
| `node-community` | node-layer | node-group | graph | louvain, leiden, label_propagation, speaker_listener, girvan_newman, modularity_optimization, fastgreedy, infomap, leading_eigenvector, walktrap, spinglass, hdbscan, k_means, approximate_max_k_cut, components, strongly_connected, biconnected, k_core_decomposition |
| `similarity` | derived-edges | derived-edges | graph | node_similarity, knn, filtered_knn, filtered_node_similarity, cosine |
| `path-cost` | derived-edges | derived-edges | graph | bfs_depth, dijkstra_cost |
| `path` | ordered-paths | paths | graph | bfs, dijkstra, dijkstra_all_pairs, astar, bellman_ford, floyd_warshall, delta_stepping |
| `ranked-path` | ordered-paths | paths | graph | yens |
| `traversal` | node-layer | node-traversal | graph | dfs |
| `walk` | ordered-paths | walks | graph | random_walk |
| `pair` | derived-edges | derived-edges | graph | transitive_closure |
| `flow` | derived-edges | derived-edges | graph | max_flow |
| `costed-flow` | derived-edges | derived-edges | graph | min_cost_max_flow |
| `min-cut` | derived-edges | derived-edges | graph | min_cut |
| `cut-tree` | derived-edges | derived-edges | graph | gomory_hu_tree |
| `flow-edges` | edge-layer | edge-overlay | graph | max_flow_edges |
| `costed-flow-edges` | edge-layer | edge-overlay | graph | min_cost_max_flow_edges |
| `min-cut-edges` | edge-layer | edge-overlay | graph | min_cut_edges |
| `steiner-edge-list` | edge-layer | edge-overlay | graph | min_steiner_tree, prize_collecting_steiner_tree |
| `edge-list` | edge-layer | edge-overlay | graph | minimum_spanning_tree, maximum_spanning_tree, max_weight_matching |
| `unweighted-edge-list` | edge-layer | edge-overlay | graph | max_cardinality_matching, max_bipartite_matching, bridges |
| `k-edge-list` | edge-layer | edge-overlay | graph | minimum_k_spanning_tree |
| `node-order` | node-layer | node-order | graph | topological_sort |
| `node` | node-layer | node-set | graph | articulation_points |
| `node-color` | node-layer | node-group | graph | node_coloring, k1_coloring |
| `edge-color` | composition-required | edge-group | graph | edge_coloring |
| `euler-trail` | ordered-paths | euler-trail | graph | euler_circuit, euler_path |
| `cycle` | ordered-paths | cycles | graph | find_cycles |
| `cost-path` | ordered-paths | paths | graph | dag_longest_path, dag_longest_path_weighted |
| `is-dag` | table-only | table | table | is_dag |
| `has-euler-circuit` | table-only | table | table | has_euler_circuit |
| `has-euler-path` | table-only | table | table | has_euler_path |
| `is-planar` | table-only | table | table | is_planar |
| `chromatic-number` | table-only | table | table | chromatic_number |
| `triangle-count` | table-only | table | table | triangle_count |
| `automorphism-count` | table-only | table | table | count_automorphisms |
| `modularity` | table-only | table | table | modularity |
| `transitivity` | table-only | table | table | transitivity |
| `conductance` | table-only | category | table, bar-chart | conductance |
| `triad-census` | table-only | category | table, bar-chart | triad_census |
| `dyad-census` | table-only | category | table, bar-chart | dyad_census |
| `embedding` | composition-required | embedding | embedding-coordinates, parallel-coordinates | node2vec, graphsage, fast_random_projection, hashgnn |
| `search` | node-layer | node-search | graph | (find) |
| `entity_graph` | entity-graph | entity-graph | graph | (base graph) |
<!-- graphforge-ledger:end -->

`entity_graph` is the ledger's row for the base property graph itself (the
extension's `entity-graph` disposition): it has no result fields and no
algorithms, and a request that names it (a base and no result layer) composes
the default view of §4.4a. Adding the row changes no other entry, so
`LEDGER_VERSION` and every existing document stay byte-identical.

**Delivery status.** Every schema composes: graph intents (node and edge
layers, derived edges, ordered overlays; §4.4–4.5), tables and bar charts for
scalar and category results, and embedding views (§4.6), on the native C ABI
and in direct-browser WASM from the same bytes (§6.3).

## 4. Composition

### 4.1 Base graph

The base graph is the canonical graph a result joins onto. It is built from
any mix of, in order:

- GraphForge Cypher entity results: struct columns with `node_uuid` (nodes),
  `edge_uuid` + `src_uuid`/`dst_uuid` (relationships), or `nodes` +
  `relationships` lists (paths), including lists of those structs — e.g.
  `MATCH (n) RETURN n` and `MATCH ()-[r]->() RETURN r`;
- flat node tables (`node_uuid`, optionally `parent_uuid`: the compound
  hierarchy, see below) and flat edge tables (`edge_uuid` plus
  `src_uuid`/`dst_uuid` or `source_uuid`/`target_uuid`), UUIDs as
  `FixedSizeBinary(16)` or canonical text;
- raw packed UUID planes (`base.node_uuid`, `base.edge_uuid`,
  `base.edge_source_uuid`, `base.edge_target_uuid`).

The same entity may appear in many rows (`RETURN a, r, b`); identical UUIDs
merge (counted as `GF_BASE_MERGED_ENTITIES`), and a relationship seen twice
must name the same endpoints (`GF_BASE_EDGE_CONFLICT`). Relationships whose
endpoints are not base nodes fail (`GF_BASE_ENDPOINT_MISSING`). Node display
names come from the first non-empty of the `name`, `title`, and `label`
properties/columns, in that order (flat tables included), the
node type from `labels[0]`, and the relationship type from `rel_type`. Bounds:
20M nodes, 50M relationships (`GF_COMPOSE_TOO_LARGE`). No layer ever mutates
the base graph: the composed node/edge order is the base order.

**Hierarchy (`parent_uuid`).** A flat node table may carry a nullable
`parent_uuid` column (same name as the Python `GraphData` mapping default). A
null parent is a root. Parents resolve to dense base indices through the same
resolver as `xyg_graph_projection_create` (`projection::resolve_parents`) and
must form a forest, validated before anything is composed: an unknown parent is
`GF_BASE_PARENT_UNKNOWN`, a node naming itself `GF_BASE_PARENT_SELF`, a cycle
`GF_BASE_PARENT_CYCLE`, a nil parent `GF_BASE_NULL_IDENTITY`, and a node seen in
two rows with different parents `GF_BASE_PARENT_CONFLICT`. An absent column is
undeclared; a null row explicitly declares a root. Root/parent declarations
conflict in either order, while agreeing repeats are accepted. Failure is atomic: no
document is produced. The hierarchy is part of the document (§5.3
`node.parent`), so native, direct-browser, Python, and Node hosts see one forest
and no host lowers parents itself. When a layer hides a parent, its children
attach to the nearest visible ancestor (recorded as
`GF_COMPOSE_PARENT_REPARENTED`, count of re-attached children). Ancestor resolution
memoizes each chain in O(n); the deterministic regression bound is at most 2n
parent-link visits, including a 100,000-deep shared hidden chain.

### 4.2 Generation identity

Callers pass the generation the base graph was read at (`base.generation`)
and, per layer, the generation the result was computed at. Both present and
different: `GF_COMPOSE_GENERATION_STALE`. Exactly one present:
`GF_COMPOSE_GENERATION_MISSING`. Both absent: the join is allowed and
recorded as `GF_COMPOSE_GENERATION_UNVERIFIED`. Joins also fail when the
identities themselves disagree with the base (§4.3), so an incompatible base
graph is caught even without generations.

### 4.3 Joins and identity policies

Node layers join `node_uuid` onto base nodes; edge layers join `edge_uuid`
onto base relationships and require the result's `source_uuid`/`target_uuid`
to equal the base endpoints (or their reverse; reversed matches are counted as
`GF_COMPOSE_EDGE_REVERSED`, or reoriented for directional overlays and counted
as `GF_COMPOSE_EDGE_REORIENTED`). A mismatch fails with
`GF_COMPOSE_EDGE_ENDPOINT_MISMATCH`. A node identity that names a base
relationship (or the reverse) fails with `GF_COMPOSE_IDENTITY_KIND`; one
element in two rows fails with `GF_COMPOSE_DUPLICATE_ID`, except k spanning
trees sharing an edge (the first row paints it; `GF_COMPOSE_SHARED_MEMBERSHIP`).
Null identities fail with `GF_RESULT_NULL_IDENTITY`.

| Policy | Values | Default | Meaning |
|---|---|---|---|
| `extra` (result identities absent from the base) | `error`, `drop` | `error` | `GF_COMPOSE_EXTRA_IDS`, or drop and record `GF_COMPOSE_EXTRA_DROPPED` |
| `missing` (base elements the layer does not cover) | `dim`, `hide`, `keep`, `error` | `dim` for coverage layers (score, group, order, traversal) and edge overlays; `keep` for sets and search | `dim` sets the disabled visual state (recorded `GF_COMPOSE_MISSING_DIMMED`); `hide` removes them, and hidden nodes take their relationships (`GF_COMPOSE_EDGES_HIDDEN_WITH_NODES`); `keep` paints them normally; `error` fails with `GF_COMPOSE_MISSING_IDS` |

`rows` restricts a layer to explicit result rows (unique, in range).

### 4.4 Planes, channels, and paint

A composition writes the graph mark's v1 semantic planes
([graph-mark.md §7.1.1–7.1.2](graph-mark.md)): per node and per relationship
`class`, `epistemic`, `status` (codes 0–7), `metric` (f64), and visual-state
`flags`, plus node labels and label priorities. The graph mark resolves them
in Rust exactly like any semantic graph (palette, sizes, widths, halos, dashes,
arrowheads, states). Each channel has one writer; a second layer writing the
same channel fails with `GF_COMPOSE_CHANNEL_CONFLICT`, so multiple layers
coexist only when they are complementary (e.g. PageRank size + Louvain class +
spanning-tree overlay + articulation points).

| Composition | Planes written |
|---|---|
| node-score, node-search | node `metric` = score (size 7–20 px); label priority = score. Search hits also get node `status` 1 |
| node-group | node `class`: the six largest groups (ties by ascending id) get codes 1–6; with more than seven groups the rest share 7 (`GF_COMPOSE_GROUPS_BUCKETED`). Negative ids (e.g. HDBSCAN noise) and nulls are class 0 (`GF_COMPOSE_UNASSIGNED_GROUP`, `GF_COMPOSE_NULL_VALUES`) |
| node-order | node label = order value; label priority = −order |
| node-traversal | node label = order; node `metric` = depth |
| node-set | node `status` 1 (combined across set layers by maximum) |
| edge-overlay | relationship `class` 1 for members (or group codes for `tree_id`); `metric` = the schema's metric (flow, capacity, weight); directional overlays (flow, cut edges) set `status` 1, which draws the arrowhead |
| edge-group | relationship `class` from the group id (edge coloring), bucketed like node groups |
| derived-edges | one **derived edge** per result row between the two joined nodes (§4.5) with the derived type's `epistemic` code, `status` 1 (arrowhead) for directed types, and `metric` = similarity / flow / cut value |
| paths, walks, cycles | one derived **step** edge per consecutive node pair (cycles add the closing step), `status` 1 in travel direction, `edge.order` = step index, `edge.path` = overlay index; nodes on the overlay get node `status` 2 and path/walk endpoints `status` 3 (combined by maximum). A layer that composes exactly one overlay labels its nodes with their first 0-based position (owning node labels); several overlays stay unlabeled (`GF_COMPOSE_PATH_LABELS_OMITTED`) |
| euler-trail | the persisted relationships named by `edge_path`, in order: relationship `class` 1, `status` 1, `edge.order`/edge label = step index, reoriented to the travel direction (`GF_COMPOSE_EDGE_REORIENTED`); each step must connect consecutive `node_path` nodes (`GF_COMPOSE_EDGE_ENDPOINT_MISMATCH`); no derived edges |

Base elements start at class/epistemic/status 0 and metric NaN. Node labels
default to the base display name. Missing elements under `dim` carry the
disabled flag (opacity 0.28, neutral fill). The graph mark gained
`edge_visual_state_flags` / `edgeVisualStateFlags` (an array or an edge
column name) so relationships resolve
states through the same Rust precedence as nodes (Python and Node).

The document's legend rows are Rust's: side (node/relationship), semantic
field and code, text such as `community 3`, `other communities (4)`,
`spanning tree edge`, `articulation point`, or `not in result`, the class
shape, and the light and dark palette colors. Hosts render them as the
chart legend (marker swatches, like the semantic legend) instead of the
generic `Class n` rows.

### 4.4a Property-graph default view (no result layer)

A request with a base graph and **no result layer** composes the base
property graph with XYG's default view; no analytical layer or configuration
is needed. The base is the graph layer, whether it arrives as Cypher entity
results or as flat tables (§4.1), and the ledger row is `entity_graph` (§3).
Rust alone owns these defaults, so the Python, Node, and direct-browser WASM
hosts draw the same graph from the same bytes. Layered compositions keep the
encodings of §4.4 and are unchanged; the defaults below apply only when
there is no result layer. (Only `layers: []` is new: a request that carries
no base still fails with `GF_COMPOSE_BASE_REQUIRED`, and layers still check
`GF_COMPOSE_GENERATION_STALE` against the base generation.)

| Default | Rule |
|---|---|
| Node class | `labels[0]` ranked like any group (§4.4 node-group): the six largest labels (ties by ascending label text) get codes 1–6; with more than seven labels the rest share 7 (`GF_COMPOSE_GROUPS_BUCKETED`, no layer). Unlabeled nodes stay class 0. The palette is the shared categorical palette |
| Legend | one node row per label class present, labeled with the label text, `other labels (n)` for the shared bucket, and `no label` for class 0 when labeled nodes also exist |
| Node caption | the first non-empty of `name`, `title`, `label` (§4.1), else the last eight hex digits of the node UUID (the random tail of a UUIDv7); nodes that fell back are counted in `GF_COMPOSE_CAPTION_IDENTITY` |
| Relationship type | `edge.type` carries it for hover and selection; `edge.label` repeats it with `edge.label_priority` −1, below every node caption (0), so the graph mark's zoom-monotone label plan (`graph_label_plan`) ranks types after captions and shows them as zoom frees room |
| Direction | when `graph.directed` is 1 every base relationship gets edge `status` 1, the directional-overlay signal that `graph_style` resolves to a target-end arrowhead in both the graph mark and the Scene, with a `directed relationship` legend row. Undirected graphs keep status 0 and no arrowheads (layered compositions keep their per-layer status) |
| Layout | the graph mark's seeded force layout (§6.3: seed 0, 300 ticks over every composed edge) |
| Identity | every node and relationship keeps its UUID; parallel relationships stay separate edges and self-loops stay one edge with equal endpoints, both painted by the Scene under their own stable IDs |

Composing the same graph and Version twice yields identical bytes, document
and Scene alike (the layout is seeded and `libm`-free; §6.3). The canonical
semantic Scene places each head on the target marker's screen-space outline
(including its stroke) using the ordinary graph mark's `clip_edge_piece`
geometry. Circle, square and diamond outlines, parallel routes and self-loop
return segments are covered by geometric position regressions; checking only
Scene record counts does not prove direction is visible. Shafts retain their
routing and stable edge identity. This corrects every canonical semantic Scene
with directed edges, including analytical and compound scenes; the current
cross-host/semantic goldens change accordingly. Historical Scene32 refresh
hashes remain untouched and no longer describe a version-only difference from
the current geometry.

**Level of detail (recorded, never silent).** The direct-tier Scene is bounded
to 1,024 nodes plus edges (`GF_COMPOSE_SCENE_TOO_LARGE`); larger graphs paint
through the native graph mark, whose Rust level-of-detail tiers apply
unchanged and are recorded by that mark (§28): Direct, Edge sample (edges over
budget), and Cluster/aggregate (nodes over `node_budget`), with caption
acceptance by label priority (`xyg_graph_label_accept`; graph-mark.md §6, §7.1).
Inside the direct tier the Scene's label planner is the caption culler: node
captions are placed in stable-ID order, truncated to the label bound, and
dropped when they collide or leave the plot; the default view puts no
relationship-type labels in the static Scene, because a still picture cannot
zoom-gate them and edge labels would outrank node captions in that order.
**Known gap:** the direct-browser WASM view paints that fixed-range Scene
(`renderWasmScene`: `drag_action: "none"`, one fixed view range, labels baked
into the Scene), so relationship types appear there on selection only (the
`xy:graphforge-select` detail carries `type`), not at zoom; zoom-gated types are delivered by the native graph mark
(`edge.label`). Zoom-gating on the WASM path needs the interactive
render/pick pipeline of #36 and is tracked on #934.
Static PNG/SVG export of the default view follows the Scene, and its parity
with the interactive view is tracked by #935. Accessible selection and
keyboard navigation of the graph are owned by #36, not by this composition. Notebook and Streamlit
application proof remains tracked by #1015/#1016. #1009 is closed and is no
longer a hold on this work; these remaining #934 acceptance gaps are open.

### 4.5 Derived edges

Derived edges are analytical relationships a result asserts between base
nodes; they are never persisted relationships. They are appended after the
base relationships, carry no UUID (`edge.derived` = 1, `edge.uuid` nil,
`edge.base_row` = `u64::MAX`, `edge.layer` = the owning layer), and are
identified by their layer and result row (`layer.edge_rows`). They paint
visibly apart: every derived type has a nonzero epistemic code, which draws
the epistemic halo and a screen-space dash (code 4 is skipped because the v1
dash table makes it solid).

| Derived type | Epistemic | Arrowhead | Legend |
|---|---|---|---|
| `SIMILAR` (similarity) | 1 | no | similar (derived) |
| `REACHES` (transitive closure) | 2 | yes | reaches (derived) |
| `MAX_FLOW`, `MIN_COST_FLOW` | 3 | yes | source-to-sink flow (derived) |
| `MIN_CUT` | 5 | yes | source-to-sink cut (derived) |
| `CUT_TREE` (Gomory–Hu) | 6 | no | cut tree (derived) |
| `PATH_STEP`, `WALK_STEP`, `CYCLE_STEP` | 7 | yes | path / walk / cycle step (derived) |

Endpoints that are not base nodes follow the layer's `extra` policy (a path
through an absent node drops as a whole); endpoints naming base relationships
fail with `GF_COMPOSE_IDENTITY_KIND`. Derived edges and steps across all
layers are bounded to 5,000,000 (`GF_COMPOSE_TOO_LARGE`; select rows with
`rows`). Hidden nodes take their derived edges with them, and an overlay that
loses any node or step leaves the `path.*` sections
(`GF_COMPOSE_PATHS_HIDDEN`). Paths with fewer than two nodes (no route) are
kept without steps and counted as `GF_COMPOSE_EMPTY_PATHS`.

### 4.6 Tables, bar charts, and embeddings

Intents other than `graph` compose exactly one layer
(`GF_COMPOSE_INTENT_CONFLICT` otherwise) and never produce a graph. A base
graph is optional; when one is passed, the generation rules of §4.2 apply and
embedding rows join it for display names (and follow the `extra` policy).

- **table** (scalar and category results): the schema's canonical columns in
  ledger order; per cell, deterministic text (booleans `true`/`false`,
  integers in exact decimal (unsigned counts above `i64::MAX` included), floats as the shortest round-trip decimal), the numeric
  value (NaN for text), and validity. At most 1,000,000 cells.
- **bar-chart** (category results): one bar per result row in result order
  (never re-sorted), category text and value; nulls are recorded
  (`GF_COMPOSE_NULL_VALUES`).
- **parallel-coordinates** (embeddings): every node's full vector over the
  dimension index, with the node UUID, result row, and base display name,
  plus a Rust plot domain (dimension span and finite value range, each padded
  by 5%). `graphforge.dimensions`, when present, must equal the vector length
  (`GF_RESULT_SCHEMA_MISMATCH`). At most 20,000,000 values, checked from the
  declared width before any vector is decoded. A one-dimensional embedding
  renders as points at dimension 0.
- **embedding-coordinates** (embeddings): nodes placed at caller-provided 2D
  coordinates (`layer.coordinates`: Arrow IPC `node_uuid`, numeric `x`, `y`;
  malformed, null, or non-finite coordinates fail with
  `GF_COMPOSE_COORDINATES_INVALID`). Embedded nodes without coordinates fail
  (`GF_COMPOSE_COORDINATES_MISSING`) unless `missing: "hide"`; coordinates for
  nodes outside the embedding follow `extra`. Without coordinates, only a
  two-dimensional embedding may place itself (recorded
  `GF_COMPOSE_EMBEDDING_2D`); any other dimensionality fails with
  `GF_COMPOSE_COORDINATES_REQUIRED`, so the first two of many dimensions are
  never plotted as x/y.

### 4.7 Decisions (never silent)

Every reduction or policy outcome is a recorded decision `(code, layer,
count)` in the document, never a silent change: `GF_COMPOSE_GENERATION_UNVERIFIED`,
`GF_COMPOSE_MISSING_{DIMMED,HIDDEN,KEPT}`, `GF_COMPOSE_EXTRA_DROPPED`,
`GF_COMPOSE_EDGES_HIDDEN_WITH_NODES`, `GF_COMPOSE_GROUPS_BUCKETED`,
`GF_COMPOSE_UNASSIGNED_GROUP`, `GF_COMPOSE_NULL_VALUES`,
`GF_COMPOSE_EDGE_REVERSED`, `GF_COMPOSE_EDGE_REORIENTED`,
`GF_COMPOSE_SHARED_MEMBERSHIP`, `GF_COMPOSE_EMPTY_PATHS`,
`GF_COMPOSE_PATH_LABELS_OMITTED`, `GF_COMPOSE_PATHS_HIDDEN`,
`GF_COMPOSE_EMBEDDING_2D`, `GF_COMPOSE_SCENE_EMPTY`,
`GF_COMPOSE_PARENT_REPARENTED`, `GF_BASE_MERGED_ENTITIES`.

## 5. Wire contract

### 5.1 Container

`XYGQ` (request) and `XYGF` (document) share one self-describing
named-section container (`crates/xyg-engine/src/graphforge/container.rs`,
Node `packages/xy-node/src/graphforge-container.js`):

```text
0   magic[4]            "XYGQ" | "XYGF"
4   version u32         1
8   entry_count u32     ≤ 8,192
12  names_bytes u32
16  total_bytes u64     == buffer length
24  reserved u64        0
32  entries × 40: name_offset u32, name_len u32, dtype u32, index u32,
                  offset u64, count u64, byte_len u64
..  names ([a-z0-9._], ≤ 64 bytes each), zero-padded to 8
..  payloads, each 8-aligned, non-overlapping
```

dtypes: 1 `u8`, 2 `u32`, 3 `u64`, 4 `i64`, 5 `f64`, 6 bytes, 7 UUID (16
bytes each), 8 UTF-8, 9 text list (`count + 1` u64 offsets, then UTF-8).
All little-endian. Sections are keyed by `(name, index)`; `index` is the layer
for `layer.*` sections. Hosts decode sections generically and ignore unknown
document sections, so sections can be added without a version bump;
`composition.version` (currently 2) bumps when an existing section's meaning
changes. Version 2 makes the document the single carrier of the compound
hierarchy (`node.parent`); sessions refuse any other version. Requests are strict: unknown request sections fail.

### 5.2 Request (`XYGQ`)

| Section | dtype | Meaning |
|---|---|---|
| `base.table` [i] | bytes | GraphForge Arrow IPC base tables (§4.1), in order |
| `base.node_uuid`, `base.edge_uuid`, `base.edge_source_uuid`, `base.edge_target_uuid` | UUID | packed base planes (optional) |
| `base.generation` | UUID ×1 | base-graph generation |
| `base.directed` | u8 ×1 | default 1 |
| `layer.result` [i] | bytes | GraphForge Arrow IPC result (required; ≤ 16 layers) |
| `layer.intent` [i] | UTF-8 | required: `graph`, `table`, `bar-chart`, `embedding-coordinates`, `parallel-coordinates` |
| `layer.result_id` [i] | UTF-8 | caller result id, echoed (1–128 of `[A-Za-z0-9._:-]`) |
| `layer.generation` [i] | UUID ×1 | result generation |
| `layer.missing`, `layer.extra` [i] | UTF-8 | policies (§4.3) |
| `layer.rows` [i] | u64 | explicit result rows |
| `layer.coordinates` [i] | bytes | Arrow IPC `node_uuid`, `x`, `y` (embeddings) |
| `select.uuid` | UUID | node or relationship UUIDs painted in the selected state (§4.4 flags); a UUID naming both a node and a relationship (separate identity spaces) selects both; unknown UUIDs are counted (`GF_COMPOSE_SELECTION_UNMATCHED`) |
| `render.width`, `render.height` | f64 ×1 | viewport (160–16,384 × 120–16,384 CSS px): also lower a graph composition to the canonical Scene (§6.3); other kinds fail with `GF_COMPOSE_RENDER_UNSUPPORTED` |
| `render.theme`, `render.title` | UTF-8 | `light` (default) or `dark`; chart title |

### 5.3 Document (`XYGF`)

`status` (u32: 0 composition, 1 error). An error document holds `error.code`,
`error.message` (value-free), `error.layer` (u32, `u32::MAX` none), and
optionally `error.field`. A graph composition holds:

| Sections | Meaning |
|---|---|
| `kind`, `composition.version`, `ledger.version` | `"graph"`; versions |
| `graph.directed`, `base.generation`, `base.counts` | base facts |
| `node.uuid`, `node.base_row`, `node.name`, `node.type` | identity (hidden nodes removed; `base_row` maps back) |
| `node.class`, `node.epistemic`, `node.status`, `node.metric`, `node.flags`, `node.label`, `node.label_priority` | semantic planes |
| `node.parent` (u32), `node.parent.valid` (u8) | compound hierarchy in composed node indices (`u32::MAX` / `0` for roots); present only when a base node table carried `parent_uuid` (§4.1); absent means no hierarchy |
| `edge.uuid`, `edge.base_row`, `edge.source`, `edge.target`, `edge.type`, `edge.derived`, `edge.layer` | identity and dense endpoints (`edge.derived` 1 marks derived edges; persisted edges keep their UUID) |
| `edge.order` (i64, −1 none), `edge.path` (u64) | step index and overlay index of ordered steps and Euler trail edges |
| `edge.class`, `edge.epistemic`, `edge.status`, `edge.metric`, `edge.flags`, `edge.label`, `edge.label_priority` | semantic planes and edge labels (Euler step indices) |
| `path.layer`, `path.row`, `path.rank`, `path.cost` (NaN when absent), `path.node_offsets` / `path.nodes`, `path.edge_offsets` / `path.edges` | ordered overlays as composed node and edge indices |
| `layer.schema`, `layer.schema_version`, `layer.verb`, `layer.algorithm`, `layer.disposition`, `layer.composition`, `layer.intent`, `layer.missing_policy`, `layer.extra_policy`, `layer.result_id`, `layer.generation`, `layer.derived_type` [i] | layer provenance |
| `layer.counts` [i] | u64 ×5: result rows, selected rows, matched, missing, extra |
| `layer.value_names`, `layer.node_values` / `layer.edge_values`, `layer.node_rows` / `layer.edge_rows` [i] | exact result values joined per element (row-major, NaN absent) and the result row per element (`u64::MAX` absent), for tooltips and table ↔ chart selection. Node layers list the canonical value fields first, then the numeric node properties rank/cluster/find results carry; derived edges and path steps carry their layer's row (rank/cost for steps) |
| `layer.text_names`, `layer.node_texts` [i] | text node properties of node layers, joined per node (row-major, empty when absent); at most 32 property columns per layer (`GF_COMPOSE_PROPERTIES_TRUNCATED`) |
| `legend.*` | Rust legend rows (§4.4) |
| `decision.code`, `decision.layer`, `decision.count` | §4.7 |
| `scene.version`, `scene.stable_id_base`, `scene.x`, `scene.y`, `scene.canonical` | with `render`: Scene version, stable-ID bases (node `2^32`, edge `1`), laid-out node positions, and the canonical Scene bytes (§6.3) |

Other document kinds share the header, `layer.*` provenance (index 0),
`layer.counts`, and `decision.*`:

| `kind` | Sections |
|---|---|
| `table` | `table.columns`, `table.kinds`, `table.rows` (result rows), `table.cells` (text list, row-major), `table.values` (f64), `table.valid` (u8) |
| `bar-chart` | `chart.category_name`, `chart.value_name`, `chart.category`, `chart.value`, `chart.result_row`, `chart.domain` (`[x0, x1, y0, y1]`: bar slots 0..k−1 as `[-0.5, k-0.5]`, and a value range that includes zero with 5% headroom away from it) |
| `parallel-coordinates` | `vector.dimensions`, `vector.uuid`, `vector.result_row`, `vector.base_row`, `vector.name`, `vector.values` (row-major), `vector.domain` (`x0, x1, y0, y1`) |
| `scatter` | `point.source` (`caller` or `embedding`), `vector.dimensions`, `point.uuid`, `point.result_row`, `point.base_row`, `point.name`, `point.x`, `point.y` |

Output is deterministic for identical request bytes, so native and WASM hosts
are compared byte for byte.

## 6. Hosts

### 6.1 Native C ABI (current ABI 395)

| Symbol | Role |
|---|---|
| `xyg_graphforge_compose(request, len, out_handle)` | 0 composition, 1 error document, −1 bad arguments, −2 too many live documents (1,024) |
| `xyg_graphforge_document_len` / `_copy` / `_destroy` | read and release the document (−7 stale handle, −8 undersized buffer) |
| `xyg_graphforge_composition_version` | `XYGF` semantics version |
| `xyg_graphforge_ledger_tsv` | the ledger as TSV (schema, version, disposition, composition, intents, fields, algorithms) |

### 6.2 Node (`@curatelabs/xyg-node/graphforge`)

```js
import { composeGraphForge, graphforgeChart } from "@curatelabs/xyg-node/graphforge";

const composition = composeGraphForge({
  base: { tables: [nodesIpc, edgesIpc], generation: generationUuid },
  layers: [
    { result: pagerankIpc, intent: "graph", resultId, generation: generationUuid },
    { result: louvainIpc, intent: "graph", resultId: other, generation: generationUuid },
  ],
});                                   // throws GraphForgeCompositionError (.code/.layer/.field)
const fig = graphforgeChart(composition, { width: 800, height: 600, theme: "dark" });
fig.toHtml();                         // or toPng()/toSvg()/payload
composition.identify("node", i);      // { uuid, layers: [{ layer, resultId, row }] }
composition.identify("edge", j);      // + derived, type, source/target UUIDs, order/path for steps
composition.paths;                    // [{ layer, row, rank, cost, nodes: [i], edges: [j] }]
composition.select([uuid, ...]);      // { nodes: [i], edges: [j] } for highlight
composition.diagnostics();            // schema ids, counts, decision codes only
```

`graphforgeChart` dispatches on `kind`: graphs through the graph mark, bar
charts as bars on integer slots of a linear x axis whose ticks carry the
category names (`chart.domain`, `tick_values`, `tick_labels`) with
category/value hover rows, parallel coordinates as one
polyline per node (`segments` with per-segment node tooltips and the Rust
domain), and embedding coordinates as a scatter with node tooltips. Tables
render with `graphforgeTableHtml(composition)`, an escaped `<table>` (cells
are text, never markup). Because bar charts use a labelled linear axis rather
than a category axis, their SVG/PNG export labels every bar like the browser
(the public Scene axis admits authored ticks and labels); category axes
themselves remain outside static export.

`graphforgeWebviewPayload(composition, opts)` returns `{spec, buffer,
nodeTrace, edgeTrace, figure, positions}` for a browser host (click events on).
Hover rows travel as typed tooltip columns (protocol v14, graph-mark.md §2),
not per-element JSON. `positions` (also `graphforgePositions(figure,
composition)`) are the laid-out node positions keyed by node UUID.
`graphforgeChart(next, { positions })` and `graphforgeWebviewPayload(next, {
positions })` reuse them with a preset layout, skipping the force ticks, when
every composed node has one (a recomposition of the same base with other
layers, selection, or theme); otherwise the graph is laid out afresh. At 10k
nodes reuse takes the payload from 1.9 s to 0.27 s with identical positions.
`decodeGraphForgeDocument` builds UUID text and lookup maps on first use, so
decoding stays proportional to the typed planes (about 75 ms at 100k nodes).

`graphforgePick(figure, composition, {trace, index})` maps a relayed pick to
`graphforgePick(figure, composition, {trace, index})` maps a relayed pick to
`composition.identify(...)` — node rows exactly below Aggregate LOD, edge
segments through Rust's render-edge membership (an aggregate edge reports its
member count, never one invented relationship).

`encodeGraphForgeRequest` / `composeGraphForgeRequest` /
`decodeGraphForgeDocument` expose the raw bytes for hosts that move requests
or documents across processes; `graphforgeGraphData` /
`graphforgeGraphOptions` / `graphforgeLegendItems` feed the ordinary graph
mark for custom figures; `graphforgeLedger()` returns the Rust ledger.

### 6.2a Python (`xyg.compose_graphforge`)

The Python host binds the same C ABI (`_native.graphforge_compose`) and frames
and decodes the container in `xyg._graphforge_container`, byte-identical to
Node and the browser:

```python
import xyg

composition = xyg.compose_graphforge(
    base={"tables": [nodes_ipc, edges_ipc], "generation": generation_uuid},
    layers=[{"result": pagerank_ipc, "intent": "graph", "result_id": rid, "generation": generation_uuid}],
    select=None, render=None,
)                                    # raises GraphForgeCompositionError (.code/.layer/.field)
composition.identify("node", i)      # {"uuid", "layers": [{"layer", "result_id", "row"}]}
xyg.graphforge_chart(composition, width=800, height=600)   # a Chart (graph, bars, parallel, scatter)
xyg.graphforge_table_html(table_composition)               # escaped <table>
xyg.graphforge_ledger()                                    # the Rust coverage ledger
```

Inputs and outputs mirror §6.2 in snake case (`result_id`, `node_values`,
`edge_rows`, …). `graphforge_chart` returns an ordinary `Chart`: graphs use
the `graph` mark with the composition's planes and Rust legend; bar charts,
parallel coordinates, and embedding scatters attach the same UUID hover rows
as Node. `encode_graphforge_request` and `decode_graphforge_document` expose
the raw bytes. `tests/fixtures/graphforge/cross_host.json` pins the request and
document SHA-256 for 101 cases; the Python generator
(`scripts/gen_graphforge_cross_host.py`) writes it and both
`tests/test_graphforge.py` and `packages/xy-node/test/graphforge-cross-host.test.mjs`
reproduce it.

### 6.3 Direct-browser WASM (`@curatelabs/xyg`, current WASM ABI 34)

`xyg_wasm_graphforge_compose(handle, offset, length)` composes one staged
`XYGQ` request with the same engine call as the native host and returns its
`XYGF` document (error documents included) in the instance output. The Worker
message `graphforge.compose` and `XygWasmWorker.graphforgeCompose(request)`
move the bytes; nothing else runs in TypeScript. Public browser API
(`js/src/49_wasm_graphforge.ts`):

```js
import { createXygWasmWorker, renderWasmGraphForge, composeWasmGraphForge,
         graphforgeTableElement } from "@curatelabs/xyg";

const worker = createXygWasmWorker({ workerUrl, wasm });        // local assets only
const { view, composition } = await renderWasmGraphForge({
  el, worker, width: 800, height: 600, theme: "dark",
  input: { base: { tables: [nodesIpc, edgesIpc], generation },
           layers: [{ result: pagerankIpc, intent: "graph", generation, resultId }],
           select: [uuid] },                                   // optional
});
view.root.addEventListener("xy:graphforge-select", (e) => e.detail);
//   { kind, index, uuid (null for derived edges), type, source, target,
//     order/path (steps), layers: [{ layer, resultId, row }] }
const table = await composeWasmGraphForge(worker, { layers: [{ result, intent: "table" }] }).result;
el.append(graphforgeTableElement(table));                      // text-only DOM
```

`renderWasmGraphForge` adds `render` sections, so Rust also lays the composed
graph out (the graph mark's `layout="force"` default: seed 0, 300 ticks, over
every composed edge) and lowers the document's planes and legend to the
canonical semantic graph Scene (`graph_style::encode_semantic_graph_scene_with_legend`:
the semantic Scene with the composition's legend text). The browser paints it
through `renderWasmScene`; clicks map Scene stable IDs (node `2^32 + i`,
edge `j + 1`) back to the composition with
`XygGraphForgeComposition.identifyStableId`. The Scene is direct tier: at most
1,024 composed nodes plus edges and the semantic Scene's primitive bound
(`GF_COMPOSE_SCENE_TOO_LARGE`); larger graphs use the native graph mark,
whose Rust level-of-detail applies. A composition that hides every node has
nothing to lay out: the document carries no `scene.*` sections and records
`GF_COMPOSE_SCENE_EMPTY`, and `renderWasmGraphForge` rejects it with that
code so the host shows its empty state. Non-graph
documents render in the host (`graphforgeTableElement`, or the chart helpers
from their sections). `graphforgeTableElement` is the one DOM surface here,
like the client's legends and tooltips: it lays out no data, only places the
Rust-formatted cells as `textContent`. `decodeWasmGraphForgeDocument` throws
an `XygWasmError` carrying the Rust `code`, `layer`, and `field`; a document
whose sections disagree on shape (for example table cells that do not fill
`rows × columns`) fails with `GF_COMPOSE_DOCUMENT_INVALID` in both the browser
and Node decoders. The Worker defers `graphforge.compose` by one task turn, as
it does Scene operations, so a cancellation already queued suppresses the
work before synchronous composition and layout start.

**Equivalence.** Documents contain only integer, UUID, text, and IEEE value
copies, so identical request bytes give identical documents on every host.
Scene bytes additionally include force-layout positions. The graph mark's
force layout seeds a circle with the platform `libm` `sin`/`cos`, which can
differ from wasm32's by an ulp that 300 force ticks amplify (about 1e-3 on a
six-node graph), so the Scene seeds the same circle with
`graph::portable_sin_cos` (Cody–Waite reduction and Taylor polynomials in
basic IEEE operations) through `graph::layout_force_portable`; the ticks use
only `+ − × ÷ √`. The semantic Scene's edge lowering measures segment lengths
(dash cuts, arrowheads) with `√` rather than `libm` `hypot`. Scene bytes are
therefore identical on every host and platform (parity tests cover 37-, 150-, and 330-node graphs), and the layout
matches the graph mark's wherever `libm` rounds the circle the same way.

**Webview / CSP.** The Worker and WASM are ordinary same-origin assets, so a
strict policy needs only `script-src 'self' 'wasm-unsafe-eval'`,
`worker-src 'self'`, and `connect-src 'self'` (browser-wasm.md, CSP). The
self-contained HTML inline density worker (`xyg-wasm-inline.js`) is the only
path that needs `worker-src blob:`.

### 6.4 VS Code webviews

A webview is a browser document with a nonce CSP whose resources are served
from a different origin (`webview.cspSource`), so a Worker cannot be created
from a resource URL and nothing may load from a CDN. Both host paths work
under these constraints (proved by `scripts/graphforge_webview_smoke.mjs`,
which serves the page and its assets from two origins):

- **Native (extension host).** The extension host composes with
  `@curatelabs/xyg-node/graphforge` and posts `graphforgeWebviewPayload(...)`'s
  `{spec, buffer}` (transfer the buffer). The webview imports the local
  `@curatelabs/xyg` `index.js` (or `standalone.js`, `window.xy`) with its
  nonce and calls `xy.renderStandalone(el, spec, buffer)`. Any graph size
  (Rust level-of-detail applies).
- **Direct-browser WASM (webview).** The webview fetches the local
  `wasm-worker.js` text and `xyg-wasm.wasm` bytes, creates the module Worker
  from a Blob URL (`createXygWasmWorker({workerUrl: blobUrl, wasm: bytes})`),
  and calls `renderWasmGraphForge`. Direct tier (≤ 1,024 elements).

Required webview CSP (VS Code's recommended shape plus exactly what the paint
client needs):

```text
default-src 'none';
script-src 'nonce-${nonce}' ${webview.cspSource} 'wasm-unsafe-eval';
style-src ${webview.cspSource} 'unsafe-inline';
img-src ${webview.cspSource} data: blob:;
font-src ${webview.cspSource};
connect-src ${webview.cspSource};
worker-src blob:;
```

`'wasm-unsafe-eval'` compiles WASM (it does not allow JavaScript `eval`);
`worker-src blob:` is for the Blob-URL Worker (WASM path) and the
self-contained HTML inline density worker; `style-src 'unsafe-inline'` is
required because the client injects its theme `<style>` element
(`20_theme.ts`) and sets inline styles. The native path without density needs
neither `'wasm-unsafe-eval'` nor `worker-src`.

Message contract (all identities are UUID strings; no values are logged):

| Direction | Message | Payload |
|---|---|---|
| host → webview | `xyg.render` | `{composition: {version, kind}, spec, buffer}` (native) or `{request}` (`XYGQ` bytes, WASM) |
| webview → host | `xyg.pick` | native: `{trace, index}` from `xy:click`, mapped host-side with `graphforgePick`; WASM: the `xy:graphforge-select` detail `{kind, uuid, derived, type, source, target, order, path, layers: [{layer, resultId, row}]}` |
| host → webview | `xyg.select` | `{uuids}`: recompose with `select: uuids` (Rust sets the selected state) and re-render |
| host → webview | `xyg.error` | `{code, layer, field, message}` from `GraphForgeCompositionError` / `XygWasmError` |

Table rows and chart elements link through `layers[].resultId` + `row` (the
caller's result id and the result row) or the element UUID; a selection from
another result or generation never matches (generation checks, §4.2).

## 7. Evidence

- Fixtures: `tests/fixtures/graphforge/results/` — real GraphForge 0.5.2
  output for every algorithm, Cypher node/edge/path/scalar results, `find`,
  `schema()`, and one base-graph dump per synthetic graph, all from one engine
  run (`scripts/gen_graphforge_result_fixtures.cjs`, adapted from the
  extension's generator). `composition_expectations.json` holds UUID → value
  pairs decoded independently with pyarrow
  (`scripts/gen_graphforge_composition_expectations.py --check`).
- Rust: reader fuzz and bounds tests; recognition of every fixture; code
  tests for unknown algorithms, versions, and type mismatches; joins for
  every node/edge layer fixture; generation, extra, missing, conflict,
  endpoint, identity-kind, and intent negatives; determinism; value-free
  diagnostics.
- Rust (ordered/derived): every graph-intent fixture (78 algorithms) composes
  onto its base; similarity/closure/flow/cut/cut-tree style and direction;
  single-path order, labels, and cost; ranked and all-pairs paths; cycle
  closing steps; walks; Euler trails over persisted edges with reorientation;
  coexistence and metric conflicts; hide cascades; extra policy for paths.
- Rust (views): every scalar and category schema composes as a table (and
  categories as bar charts) and never as a graph; exact cell text and values;
  parallel coordinates for all four embedding algorithms with and without a
  base, vectors equal to the result's, and a covering domain; caller
  coordinates, a two-dimensional embedding placing itself, and the
  required/missing/extra coordinate failures. Coordinate and 2D-embedding
  inputs are derived from the real `node2vec` output
  (`scripts/gen_graphforge_derived_fixtures.py --check`).
- Rust (property graph, #934): a zero-layer request composes end to end
  (`tests/fixtures/graphforge/results/base-property-*.arrow`: labels, captions
  from `name`/`title`/`label`/identity, a parallel pair, a self-loop, an
  unlabeled node): UUID identity and order, label classes and legend,
  captions, relationship-type labels below node captions, arrowheads only when
  directed, label ranking and bucketing, byte-identical recomposition, and the
  `entity_graph` ledger row.
  Arrowhead positions are checked against target outlines for ordinary,
  parallel and loop edges, including circle/square/diamond nodes.
- Fixture regeneration (#934): the Core producer
  `node scripts/gen_graphforge_result_fixtures.cjs <core-module> <results-dir>`
  clears and rebuilds its output. Run
  `uv run python scripts/gen_graphforge_ipc_fixtures.py --results-directory <results-dir>`
  afterward. The Python producer owns both deterministic `base-property-*.arrow`
  files and `manifest.bases.property` (including generation), preserving all
  Core-owned manifest fields. This synthetic base is not Core-produced evidence.
  The compatibility declaration's 0.5.2 manifest digest is refreshed because the
  index includes this added base; Core result/schema bytes and qualified releases
  remain unchanged.
  `tests/test_graphforge_fixture_generation.py` proves file/manifest restoration
  and repeatability with and without an existing Core manifest; full regeneration
  is checked with actual Core 0.5.2 in a disposable output directory. Regenerating
  Core identities also requires regenerating dependent expectation/derived/parity
  fixtures (§6.2a); do not mix Arrow files from different Core runs.
- Python/Node: `tests/fixtures/graphforge/cross_host.json` (101 cases: every
  contract fixture with its intent, multi-layer render/select, the property
  graph with and without render, rows and policies, coordinates, and failures) pins request and document digests that
  both hosts reproduce, so Python, Node, and WASM agree byte for byte.
- Native/WASM: `packages/xy-node/test/graphforge-wasm-parity.test.mjs` runs
  every GraphForge contract fixture (plus multi-layer render/select,
  coordinates, the property graph, and four failure cases) through the native C ABI and the real
  wasm32 artifact and requires byte-identical documents and Scenes; the
  browser bundle's request framing must equal Node's and decode the same
  identities. `cargo test -p xyg-wasm` checks the adapter against the C ABI.
  Recovery onto ABI 396 preserves the accepted packaging gates of
  **1,507 KiB raw / 624 KiB gzip** (`npm run build:wasm`); the historical
  #934 branch's smaller gates are superseded. The isolated artifact is
  1,543,118 raw / 638,560 gzip bytes (50 / 416 bytes of headroom; environment,
  hash and reproduction under browser-wasm.md "Artifact size"). Caption
  candidates merge serially, short identities use direct hex digits, and class
  ranking remains a sort-free selection using one code vector for assignment
  tracking. Default encodings and document bytes are preserved.
- Browser: `scripts/graphforge_wasm_smoke.mjs` serves only the packaged
  Worker/WASM/client and fixtures under a strict CSP (no `blob:`), paints a
  PageRank + similarity composition through WebGL, maps every painted row to
  a composed UUID, routes a click to `xy:graphforge-select` with the result
  row, renders a table as text, and surfaces a stale generation's code.
- Webview: `scripts/graphforge_webview_smoke.mjs` (CI) serves a nonce-CSP
  page from one origin and every asset from another, renders the native
  payload through `renderStandalone` and a WASM composition through a Blob
  module Worker, clicks a node on each with real mouse events, and requires
  the native relay (`graphforgePick`) and the WASM `xy:graphforge-select`
  event to name the node's UUID and per-layer result rows, with no CSP
  violations and only local asset requests.
- Release: the `publish.yaml` clean-install job installs the packed facade and
  exact-platform package on every supported OS/arch and composes real
  GraphForge fixtures (join, derived edges, Scene, pick relay, coded error)
  through the packaged core.
- Scale: `benchmarks/bench_graphforge_compose.mjs` composes real GraphForge
  0.5.2 output on 100 to 100,000-node graphs. Four layers over 100k nodes
  compose in 203 ms native and 247 ms WASM, byte-identical
  (`spec/benchmarks/graphforge-compose-local.json`; spec/benchmarks/results.md
  "GraphForge composition scale"). Its 100-node run is kept as
  `tests/fixtures/graphforge/scale-100`, which the parity suite renders on
  both hosts.
- Node: joins checked against the independent expectations for node and edge
  layers, selection round trips (including derived edges by layer and row and
  path steps), error codes, chart paint, legend, and edge labels, the edge
  visual-state flags; Python asserts the same edge-flag resolution.

## 8. Privacy

Diagnostics, errors, and decisions never contain result values, UUIDs,
vectors, coordinates, or paths: only codes, schema ids and versions, field and
type names, and counts. Metadata echoed in a message is reduced to a bounded
identifier. Displayed text (labels, legend, tooltips) is painted as text
(canvas/`textContent`), never as markup.
