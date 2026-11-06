# GraphForge result schemas and XYG visualization (#80)

GraphForge Core computes and owns the canonical Arrow result schemas. XYG
(Rust) owns recognition, dispositions, joins, identity policy, composition,
layout, and the Scene, on both the native Node host and the direct-browser
WASM host. The extension supplies the engine's Arrow IPC bytes, a base graph,
generation identity, and the caller's explicit intent. It keeps no algorithm
registry and never joins, lays out, encodes, or reduces result data.

The ledger table below is the contract between the two repositories. XYG
vendors this file and a Rust test fails if its ledger disagrees. This
repository's `src/test/xygAdapter.test.ts` fails if XYG's runtime ledger
(`graphforgeLedger()`) disagrees with it, or if any GraphForge contract
(`algorithmDescriptorContracts()`) has no entry.

Code:

- `src/session/arrowCodec.ts`: typed decode for the Results table.
- `src/session/xygAdapter.ts`: host loading, intents from XYG's ledger, the
  shared compose input, and row ↔ identity mapping from Rust's row planes.
- `src/webview/xygVisualizationPanel.ts` and `webview-ui/src/xygVisualization/`:
  the XYG view.
- `src/session/resultSchemas.ts` / `resultProjection.ts`: routing, plus the
  Result Graph projection that Cypher graphs still use.

## Routing

| Result | Recognized by | Drawn by |
|---|---|---|
| Algorithm results (`rank`, `cluster`, `similar`, `paths`, `analyze`) and `find` | `graphforge.verb` metadata | XYG (`GraphForge: Visualize Result with XYG…`; `Show Result Graph` and auto-open route here) |
| Cypher node/relationship/path values | entity struct fields (`node_uuid`, `edge_uuid` + `src_uuid`/`dst_uuid`, `nodes` + `relationships`) | Result Graph renderer |
| Cypher scalar identity columns | `node_uuid`/`id`, `source`/`target` and canonical UUID columns | Result Graph renderer |
| Anything else, including `schema()` | — | Results table only (`GF_RESULT_NO_IDENTITY`) |

Cypher graphs stay on the Result Graph renderer for two reasons. First, XYG's
compose request requires at least one result layer, so it has no base-only
composition yet. Second, #82 is what retires the previous renderers.

## Typed decode and provenance

`decodeTable` keeps a JSON-safe `ResultSchema` next to the rows:

- field kinds: `uuid`, `uuid-list`, `float-vector`, `int`, `float`, `utf8`,
  `bool`, `timestamp`, `date`, `binary`, nested `list`/`struct`;
- bounded `graphforge.*` metadata.

The Results table uses it. XYG receives the raw IPC bytes, never these rows.

Every engine result from Run Query and the analyst verbs gets a
`ResultProvenance`:

- `resultId`: a UUIDv7;
- `generationUuid`: the generation `CURRENT` names at read time;
- `queryId`: the Cypher `graphforge.query_id`, when present.

The session retains each result's raw IPC bytes, bounded to 16 results and
256 MiB. Run Query also saves them as `results/*.arrow` beside the JSON
document, whose provenance records their SHA-256. A reopened result is bound
to its bytes only when the hash matches.

## Composition

`graph` intents join the result onto a base graph read at a verified
generation: `MATCH (n) RETURN n` and `MATCH ()-[r]->() RETURN r`. The read is
retried once if a write commits in between. Both generations go to XYG:

- different generations fail with `GF_COMPOSE_GENERATION_STALE`;
- a generation on only one side fails with `GF_COMPOSE_GENERATION_MISSING`.

Intents come from XYG's ledger. The user picks when several apply; automatic
opening draws only `graph`. `embedding-coordinates` is never offered, because
it needs caller 2D coordinates and this extension does not produce them;
parallel coordinates show the full vectors.

Hosts (`graphforge.visualization.xygHost`) have no automatic fallback:

- `native` (default): `@curatelabs/xyg-node` composes in the extension host
  and the webview paints with `renderStandalone`. Any size; Rust LOD applies.
- `wasm`: the webview composes the same request bytes in a Blob-URL module
  Worker. Graphs and tables only, up to 1,024 nodes plus edges
  (`GF_COMPOSE_SCENE_TOO_LARGE`).

Selection links by identity, never row position:

- An XYG pick resolves to `{uuid, layers: [{resultId, row}]}`. The Results
  table accepts rows only for its own `resultId` and generation.
- A table row maps to UUIDs through Rust's per-layer row planes. Derived edges
  map to their endpoints. The view recomposes with `select`, so Rust paints the
  selected state, reusing positions.

## Ledger (XYG ledger v1, GraphForge algorithm schema v1, GraphForge 0.5.2: 94 algorithms)

| Schema | Disposition | Canonical fields | Algorithms |
|---|---|---|---|
| `node-score` | node-layer | `node_uuid`, `score` (+ node properties) | pagerank, betweenness, closeness, harmonic_closeness, degree, eigenvector, article_rank, hits_hub, hits_authority, celf, clustering_coefficient (alias local_clustering_coefficient), triangles, k_core, preferential_attachment, adamic_adar, common_neighbors, resource_allocation, total_neighbors |
| `node-community` | node-layer | `node_uuid`, `community_id` (+ node properties) | louvain, leiden, label_propagation, speaker_listener, girvan_newman, modularity_optimization, fastgreedy, infomap, leading_eigenvector, walktrap, spinglass, hdbscan, k_means, approximate_max_k_cut, components, strongly_connected, biconnected, k_core_decomposition |
| `similarity` | derived-edges | `node1_uuid`, `node2_uuid`, `similarity` | node_similarity, knn, filtered_knn, filtered_node_similarity, cosine |
| `path` | ordered-paths | `source_uuid`, `target_uuid`, `cost`, `path` | bfs, dijkstra, dijkstra_all_pairs, astar, bellman_ford, floyd_warshall, delta_stepping |
| `ranked-path` | ordered-paths | + `rank` | yens |
| `traversal` | node-layer | `node_uuid`, `depth`, `order` | dfs |
| `walk` | ordered-paths | `start_uuid`, `walk` | random_walk |
| `pair` | derived-edges | `source_uuid`, `target_uuid` | transitive_closure |
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
| `euler-trail` | ordered-paths | `node_path`, `edge_path` | euler_circuit, euler_path |
| `cycle` | ordered-paths | `cycle` | find_cycles |
| `cost-path` | ordered-paths | `cost`, `path` | dag_longest_path, dag_longest_path_weighted |
| `is-dag` | table-only | `is_dag` | is_dag |
| `has-euler-circuit` | table-only | `has_euler_circuit` | has_euler_circuit |
| `has-euler-path` | table-only | `has_euler_path` | has_euler_path |
| `is-planar` | table-only | `is_planar` | is_planar |
| `chromatic-number` | table-only | `chromatic_number` | chromatic_number |
| `triangle-count` | table-only | `triangle_count` | triangle_count |
| `automorphism-count` | table-only | `count` | count_automorphisms |
| `modularity` | table-only | `modularity` | modularity |
| `transitivity` | table-only | `transitivity` | transitivity |
| `conductance` | table-only | `partition_id`, `conductance` | conductance |
| `triad-census` | table-only | `triad_type`, `count` | triad_census |
| `dyad-census` | table-only | `dyad_type`, `count` | dyad_census |
| `embedding` | composition-required | `node_uuid`, `embedding` (float vector) | node2vec, graphsage, fast_random_projection, hashgnn |
| `search` | node-layer | `node_uuid`, `score`, `matched_on` (+ node properties) | (find) |

XYG renders these dispositions as follows:

- **Node layers and edge overlays** join onto the base graph. Uncovered base
  elements are dimmed.
- **Derived edges** (similarity, reachability, flow, cut, cut-tree) are dashed
  with a halo.
- **Ordered paths** draw steps with arrows. Euler trails use their persisted
  `edge_path`.
- **`edge-color`** joins onto base relationships.
- **Scalar results** render as tables. **Category results** render as tables
  or bar charts.
- **Embeddings** render as parallel coordinates.

## Failure codes

XYG's codes are surfaced as-is with a next action (`toXygError`):

- **Arrow bytes:** `GF_ARROW_*`.
- **Result schema:** `GF_RESULT_SCHEMA_UNREGISTERED`, `_VERSION`, `_MISMATCH`,
  `GF_RESULT_NOT_ALGORITHM`, and so on.
- **Base graph:** `GF_BASE_*`.
- **Composition:** `GF_COMPOSE_*`, including `GENERATION_STALE`/`_MISSING`,
  `INTENT_UNSUPPORTED`, `COORDINATES_REQUIRED`, `TOO_LARGE`, `SCENE_TOO_LARGE`,
  and `SCENE_EMPTY`.
- **Native loading:** `XYG_NATIVE_UNSUPPORTED_PLATFORM`, `_LIBRARY_MISSING`,
  `_LIBRARY_PATH_INVALID`, `_LOAD_FAILED`, `_ABI_MISMATCH`,
  `XYG_NODE_DEPENDENCY_MISSING`, `XYG_NODE_IMPORT_FAILED`.
- **WASM initialization:** `XYG_WASM_*`.

The extension adds:

| Code | When |
|---|---|
| `GF_RESULT_MISSING` | Nothing has run yet |
| `GF_RESULT_BYTES_UNAVAILABLE` | The engine bytes were evicted, or a saved result has no matching `.arrow` |
| `GF_BASE_GENERATION_CHANGED` | Writes kept committing while the base graph was read |
| `GF_RESULT_XYG_LAYER` | An algorithm/find result was handed to the Result Graph projection |
| `GF_RESULT_NO_IDENTITY` | A Cypher result has no graph identity |
| `GF_RESULT_TOO_LARGE` | A Cypher graph projects to more than 250,000 nodes + edges |

`graphforge.visualizeResult` returns the composition's value-free
diagnostics: kind, schema ids and versions, dispositions, intents, row/node/edge
counts, and decision codes such as `GF_COMPOSE_MISSING_DIMMED`. It never
includes values, UUIDs, vectors, or coordinates.

## Packaging

XYG is consumed from the exact-version candidate packages
(`0.0.0-dryrun.11`, CurateLabs/xyg Release run 36830463595), vendored under
`vendor/xyg/`, until npm publication in the 0.6.0-rc.1 cohort
(CurateLabs/xyg#108).

- `@curatelabs/xyg` (browser) is bundled into `dist/webview-ui/xygVisualization.js`.
  Its `wasm-worker.js`, `xyg-wasm.wasm`, NOTICE, and LICENSE are copied to
  `dist/webview-ui/xyg/`.
- `@curatelabs/xyg-node`, this platform's `@curatelabs/xyg-node-<platform>`
  core, koffi, and koffi's `@koromix/koffi-<platform>` prebuild are staged
  unbundled into `dist/node_modules/` by `scripts/stage-xyg-runtime.mjs`,
  because they locate their native files relative to themselves.
- A VSIX therefore carries the native core of the platform it was built on.
  Per-target VSIX builds are part of the #82 release matrix.

## Fixtures

`src/test/fixtures/graphforge-results/*.arrow` are raw IPC bytes from a real
`@curatelabs/graphforge` run:

- every registered algorithm;
- Cypher node/edge/path/scalar queries, `find`, and `schema()`;
- the base graph (`base-<graph>-nodes`/`-edges`) each result joins onto.

`manifest.json` records the engine version, its contracts, each result's base
graph, and any failures. Regenerate the fixtures when GraphForge adds or
changes a result schema:

```sh
node scripts/generate-result-fixtures.cjs path/to/node_modules/@curatelabs/graphforge
```

GraphForge 0.5.2 min-cost max-flow exceeds its iteration limit when a
downstream edge is the bottleneck, so the flow fixture network uses balanced
capacities.
