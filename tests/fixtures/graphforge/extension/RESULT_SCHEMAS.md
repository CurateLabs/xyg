# GraphForge result schemas and projection (#80)

GraphForge Core owns computation and canonical Arrow result schemas. This
extension owns *result-to-visualization intent*: for every registered result
schema it records how a result may be presented and which fields carry identity.
Geometry, layout, LOD, encoding, joins onto a base graph, and embedding
reductions belong to XYG and are never reconstructed here.

Code: `src/session/arrowCodec.ts` (typed decode), `src/session/resultSchemas.ts`
(ledger + classification), `src/session/resultProjection.ts` (identity-based
graph projection). Tests: `src/test/resultProjection.test.ts`.

## Typed decode

`decodeTable` keeps a JSON-safe `ResultSchema` next to the rows:

- Field kinds: `uuid` (`FixedSizeBinary(16)`), `uuid-list`
  (`List<FixedSizeBinary(16)>`), `float-vector` (`List`/`FixedSizeList` of floats,
  with `dimensions`), `int` (bits/signedness), `float`, `utf8`, `bool`,
  `timestamp` (timezone), `date`, `binary`, nested `list`/`struct`, `other`.
- Schema metadata: bounded to 64 entries and 1,024-character values. The
  `graphforge.algorithm`, `graphforge.verb`, `graphforge.algorithm_schema_version`,
  `graphforge.search_schema_version`, `graphforge.query_id`, and embedding
  keys are preserved.
- Values: UUIDs become hyphenated strings; UUID lists stay ordered string arrays;
  Cypher entity/path structs become plain objects; vectors stay numeric arrays;
  64-bit integers become decimal strings (no precision loss).

The schema is persisted with the result document (`results/*.json`) and
validated when read back, so saved results classify and project identically.

## Provenance

Every engine result from Run Query and the analyst verbs gets a
`ResultProvenance`:

- `resultId`: a UUIDv7 minted by the extension.
- `generationUuid`: the committed generation that `CURRENT` names at read time.
- `queryId`: the Cypher `graphforge.query_id`, when present.

A graph payload records its projection `source` (result id, generation, schema
id/version, disposition). The table and the graph are linked only when both
name the same result and generation. A graph showing a different result, or
one from another generation, never receives or sends selections.

## Dispositions

| Disposition | Meaning |
|---|---|
| `entity-graph` | Cypher node/relationship/path values with persisted UUIDs |
| `node-layer` | UUID-keyed node values (scores, communities, order, colors, search hits) |
| `edge-layer` | Persisted edges keyed by `edge_uuid` with `source_uuid`/`target_uuid` |
| `derived-edges` | Analytical pairs; edges are flagged `derived: true` |
| `ordered-paths` | Ordered UUID lists; steps are `derived` unless an `edge_path` names persisted edges |
| `table-only` | Scalar/global/category results; `GF_RESULT_TABLE_ONLY` |
| `composition-required` | Needs a base graph or explicit coordinates; `GF_RESULT_COMPOSITION_REQUIRED` |

## Coverage ledger (algorithm schema v1, GraphForge 0.5.2: 94 algorithms)

| Schema id | Disposition | Canonical fields | Algorithms |
|---|---|---|---|
| `node-score` | node-layer | `node_uuid`, `score` (+ node properties) | pagerank, betweenness, closeness, harmonic_closeness, degree, eigenvector, article_rank, hits_hub, hits_authority, celf, clustering_coefficient (alias local_clustering_coefficient), triangles, k_core, preferential_attachment, adamic_adar, common_neighbors, resource_allocation, total_neighbors |
| `node-community` | node-layer | `node_uuid`, `community_id` (+ node properties) | louvain, leiden, label_propagation, speaker_listener, girvan_newman, modularity_optimization, fastgreedy, infomap, leading_eigenvector, walktrap, spinglass, hdbscan, k_means, approximate_max_k_cut, components, strongly_connected, biconnected, k_core_decomposition |
| `similarity` | derived-edges (`SIMILAR`) | `node1_uuid`, `node2_uuid`, `similarity` | node_similarity, knn, filtered_knn, filtered_node_similarity, cosine |
| `path` | ordered-paths | `source_uuid`, `target_uuid`, `cost`, `path` | bfs, dijkstra, dijkstra_all_pairs, astar, bellman_ford, floyd_warshall, delta_stepping |
| `ranked-path` | ordered-paths | + `rank` | yens |
| `traversal` | node-layer | `node_uuid`, `depth`, `order` | dfs |
| `walk` | ordered-paths | `start_uuid`, `walk` | random_walk |
| `pair` | derived-edges (`REACHES`) | `source_uuid`, `target_uuid` | transitive_closure |
| `flow` | derived-edges | `source_uuid`, `sink_uuid`, `flow` | max_flow |
| `costed-flow` | derived-edges | + `cost` | min_cost_max_flow |
| `min-cut` | derived-edges | `source_uuid`, `sink_uuid`, `cut_value` | min_cut |
| `cut-tree` | derived-edges | `source_uuid`, `target_uuid`, `cut_value` | gomory_hu_tree |
| `flow-edges` | edge-layer | `edge_uuid`, `source_uuid`, `target_uuid`, `flow` | max_flow_edges |
| `costed-flow-edges` | edge-layer | + `unit_cost`, `flow_cost` | min_cost_max_flow_edges |
| `min-cut-edges` | edge-layer | + `capacity` | min_cut_edges |
| `steiner-edge-list` | edge-layer | + `weight` | min_steiner_tree, prize_collecting_steiner_tree |
| `edge-list` | edge-layer | + `weight` | minimum_spanning_tree, maximum_spanning_tree, max_weight_matching |
| `unweighted-edge-list` | edge-layer | `edge_uuid`, `source_uuid`, `target_uuid` | max_cardinality_matching, max_bipartite_matching, bridges |
| `k-edge-list` | edge-layer | `tree_id` + edge list | minimum_k_spanning_tree |
| `node-order` | node-layer | `node_uuid`, `order` | topological_sort |
| `node` | node-layer | `node_uuid` | articulation_points |
| `node-color` | node-layer | `node_uuid`, `color` | node_coloring, k1_coloring |
| `edge-color` | composition-required | `edge_uuid`, `color` (no endpoints) | edge_coloring |
| `euler-trail` | ordered-paths (persisted edges) | `node_path`, `edge_path` | euler_circuit, euler_path |
| `cycle` | ordered-paths | `cycle` | find_cycles |
| `cost-path` | ordered-paths | `cost`, `path` | dag_longest_path, dag_longest_path_weighted |
| scalar ids | table-only | one Boolean/UInt64/Float64 column | is_dag, has_euler_circuit, has_euler_path, is_planar, chromatic_number, triangle_count, count_automorphisms, modularity, transitivity |
| `conductance`, `triad-census`, `dyad-census` | table-only | category + value | conductance, triad_census, dyad_census |
| `embedding` | composition-required | `node_uuid`, `embedding` (float vector) | node2vec, graphsage, fast_random_projection, hashgnn |

Non-algorithm results:

| Schema id | Disposition | Recognized by |
|---|---|---|
| `search` | node-layer | `graphforge.verb=find`, search schema v1 |
| `cypher-entities` | entity-graph | node structs (`node_uuid`, `labels`), relationship structs (`edge_uuid`, `src_uuid`, `dst_uuid`, `rel_type`), path structs (`nodes`, `relationships`), including lists of them |
| `cypher-columns` | entity-graph | scalar columns written by the query author: `node_uuid`/`id`, and `source_uuid`/`src_uuid`/`source`/`start_uuid` + matching targets, with optional `edge_uuid` |
| `tabular` | table-only (`GF_RESULT_NO_IDENTITY`) | anything else, including `schema()` |

## Failure codes

| Code | When | Next action |
|---|---|---|
| `GF_RESULT_SCHEMA_UNREGISTERED` | `graphforge.algorithm` is not in the ledger | Update the extension or use the table |
| `GF_RESULT_SCHEMA_VERSION` | Algorithm/search schema version is not 1 | Align engine and extension releases |
| `GF_RESULT_SCHEMA_MISMATCH` | A canonical field is missing or has the wrong Arrow type | Re-run with a matching engine |
| `GF_RESULT_NO_IDENTITY` | No node/relationship identity | Return entities or identity columns, or chart it |
| `GF_RESULT_TABLE_ONLY` | Ledger says table-only | Use the table or a chart |
| `GF_RESULT_COMPOSITION_REQUIRED` | Embeddings / edge colors | Keep in the table until an explicit composition exists |
| `GF_RESULT_TOO_LARGE` | More than 250,000 projected nodes + edges | Filter or LIMIT the result |

`graphforge.showResultGraph` returns a `projection` diagnostic with the schema
id and version, disposition, row/node/edge counts, and duration. It never
includes values.

## Fixtures

`src/test/fixtures/graphforge-results/*.arrow` are raw IPC bytes produced by a
real `@curatelabs/graphforge` run: every registered algorithm plus Cypher
node/edge/path/scalar queries, `find`, and `schema()`. `manifest.json` records
the engine version, its `algorithmDescriptorContracts()`, and any failures.
The tests require zero failures and every contract to be present in the ledger.

Regenerate them when GraphForge adds or changes a result schema:

```sh
node scripts/generate-result-fixtures.cjs path/to/node_modules/@curatelabs/graphforge
```

GraphForge 0.5.2 min-cost max-flow exceeds its iteration limit when a
downstream edge is the bottleneck, so the flow fixture network uses balanced
capacities.

## Not yet in scope (blocked on XYG)

- Typed/columnar transfer into XYG, and the XYG-rendered node/edge layers,
  joins, and analytical compositions (CurateLabs/xyg#31, #37, plus the typed
  scene contract and host bindings). Today's projection feeds the existing
  Result Graph as JSON.
- Removing the previous renderers (#82).
