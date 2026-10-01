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

The ledger lives in `crates/xyg-engine/src/graphforge/ledger.rs`. Schema ids,
canonical fields, and dispositions match the extension's
`docs/engineering/RESULT_SCHEMAS.md` (vendored at
`tests/fixtures/graphforge/extension/RESULT_SCHEMAS.md`; a Rust test fails if
they disagree). The *composition* column is XYG's rendering of each
disposition; the *intents* column lists the only intents a caller may request.
A Rust test also fails if this table drifts from the code, and another if any
GraphForge 0.5.2 contract (94 algorithms) lacks an entry.

<!-- graphforge-ledger:begin -->
| Schema | Disposition | Composition | Intents | Algorithms |
|---|---|---|---|---|
| `node-score` | node-layer | node-score | graph | pagerank, betweenness, closeness, harmonic_closeness, degree, eigenvector, article_rank, hits_hub, hits_authority, celf, clustering_coefficient, local_clustering_coefficient, triangles, k_core, preferential_attachment, adamic_adar, common_neighbors, resource_allocation, total_neighbors |
| `node-community` | node-layer | node-group | graph | louvain, leiden, label_propagation, speaker_listener, girvan_newman, modularity_optimization, fastgreedy, infomap, leading_eigenvector, walktrap, spinglass, hdbscan, k_means, approximate_max_k_cut, components, strongly_connected, biconnected, k_core_decomposition |
| `similarity` | derived-edges | derived-edges | graph | node_similarity, knn, filtered_knn, filtered_node_similarity, cosine |
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
<!-- graphforge-ledger:end -->

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
- flat node tables (`node_uuid`) and flat edge tables (`edge_uuid` plus
  `src_uuid`/`dst_uuid` or `source_uuid`/`target_uuid`), UUIDs as
  `FixedSizeBinary(16)` or canonical text;
- raw packed UUID planes (`base.node_uuid`, `base.edge_uuid`,
  `base.edge_source_uuid`, `base.edge_target_uuid`).

The same entity may appear in many rows (`RETURN a, r, b`); identical UUIDs
merge (counted as `GF_BASE_MERGED_ENTITIES`), and a relationship seen twice
must name the same endpoints (`GF_BASE_EDGE_CONFLICT`). Relationships whose
endpoints are not base nodes fail (`GF_BASE_ENDPOINT_MISSING`). Node display
names come from a `name` property/column (`label` first for flat tables), the
node type from `labels[0]`, and the relationship type from `rel_type`. Bounds:
20M nodes, 50M relationships (`GF_COMPOSE_TOO_LARGE`). No layer ever mutates
the base graph: the composed node/edge order is the base order.

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
`GF_BASE_MERGED_ENTITIES`.

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
`composition.version` (currently 1) bumps when an existing section's meaning
changes. Requests are strict: unknown request sections fail.

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
| `bar-chart` | `chart.category_name`, `chart.value_name`, `chart.category`, `chart.value`, `chart.result_row` |
| `parallel-coordinates` | `vector.dimensions`, `vector.uuid`, `vector.result_row`, `vector.base_row`, `vector.name`, `vector.values` (row-major), `vector.domain` (`x0, x1, y0, y1`) |
| `scatter` | `point.source` (`caller` or `embedding`), `vector.dimensions`, `point.uuid`, `point.result_row`, `point.base_row`, `point.name`, `point.x`, `point.y` |

Output is deterministic for identical request bytes, so native and WASM hosts
are compared byte for byte.

## 6. Hosts

### 6.1 Native C ABI (ABI 378)

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
charts through `barChart` with a category axis, parallel coordinates as one
polyline per node (`segments` with per-segment node tooltips and the Rust
domain), and embedding coordinates as a scatter with node tooltips. Tables
render with `graphforgeTableHtml(composition)`, an escaped `<table>` (cells
are text, never markup). Static export of a bar chart fails closed with
`XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS`, as every category-axis export does in
both hosts today; the interactive chart and the table carry the names.

`graphforgeWebviewPayload(composition, opts)` returns `{spec, buffer,
nodeTrace, edgeTrace, figure}` for a browser host (click events on);
`graphforgePick(figure, composition, {trace, index})` maps a relayed pick to
`composition.identify(...)` — node rows exactly below Aggregate LOD, edge
segments through Rust's render-edge membership (an aggregate edge reports its
member count, never one invented relationship).

`encodeGraphForgeRequest` / `composeGraphForgeRequest` /
`decodeGraphForgeDocument` expose the raw bytes for hosts that move requests
or documents across processes; `graphforgeGraphData` /
`graphforgeGraphOptions` / `graphforgeLegendItems` feed the ordinary graph
mark for custom figures; `graphforgeLedger()` returns the Rust ledger.

### 6.3 Direct-browser WASM (`@curatelabs/xyg`, WASM ABI 27)

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
- Native/WASM: `packages/xy-node/test/graphforge-wasm-parity.test.mjs` runs
  every GraphForge contract fixture (plus multi-layer render/select,
  coordinates, and four failure cases) through the native C ABI and the real
  wasm32 artifact and requires byte-identical documents and Scenes; the
  browser bundle's request framing must equal Node's and decode the same
  identities. `cargo test -p xyg-wasm` checks the adapter against the C ABI.
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
