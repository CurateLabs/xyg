# XY full-surface coverage

**Status:** living checklist for chart-family coverage across the three runtime
surfaces ([host-parity.md](host-parity.md) §0) and utilization of the
performance architecture ([lod-architecture.md](lod-architecture.md),
dossier §28).

Machine-readable twin: [`dual-host-parity.json`](dual-host-parity.json)
(`mark_kinds`, `lod_tiers`, `runtimes`).

## Surfaces

| Surface | Composition API | Scale path |
| --- | --- | --- |
| Python | `python/xy/components.py` + `marks.py` → `Figure.build_payload` | Density / M4 / hexbin / graph render-graph / LOD plan |
| Node | `packages/xy-node` `charts.js` + `marks/*` → `Figure.buildPayload` | Same Rust ABI: density, M4, hist, graph LOD, lodPlan |
| Browser | `js/src` → `python/xy/static/{index,standalone}.js` | Paint / pick only on §29 buffers (`55_marks.ts` kind table) |

## Chart classifications (must ship on every host)

| Classification | Families | Node entry points |
| --- | --- | --- |
| Point / path | scatter, line, area, step, stairs, stem, ecdf | `*Chart` + `compose*` |
| Distribution | histogram, box, violin, hexbin | same |
| Grid / field | heatmap, contour, triangle_mesh | same |
| Interval / uncertainty | errorbar, error_band | same |
| Categorical / flow | bar, column, pie, sankey (ribbon), funnel* | `barChart` / `sankeyChart` / polar |
| Polar | polar, radar, wind_rose | `polarChart` / `radarChart` / `windRoseChart` |
| Graph | graph | `graphChart` / `composeGraph` |
| Layout | facet | `facetChart` |

\*Funnel: Python ready; Node may compose via bar/ribbon helpers — track in
`dual-host-parity.json` if a dedicated composer lands.

## Performance architecture utilization

| Tier | Contract | Python | Node | Browser |
| --- | --- | --- | --- | --- |
| 1 Direct | Exact marks under budget; line M4 when over threshold | ready | ready | paints direct |
| 2 Density / aggregate | Scatter log-u8 density; hexbin; graph render-graph | ready | ready (`force_density` / auto ≥ 200k) | paints density / aggregates |
| 3 Tile pyramid | Out-of-core tiles for 100M–1B | partial (design + memmap paths) | **design** (not productized) | receives composed grids only |

**Scale evidence (not raw 1B allocation in CI):**

- `benchmarks/bench_scale_all_charts.py` — Python families + graph LOD classes
- `benchmarks/bench_scale_all_charts_node.mjs` — Node twin for mark families + density
- `benchmarks/bench_graph_scale_classes_node.mjs` — 10M / 100M / 1B LOD decisions

Every profile records screen-bounded budgets; Tier-3 claims must not assert that
CI allocated a billion points.

## Tests

| Suite | What it proves |
| --- | --- |
| `packages/xy-node/test/coverage.test.mjs` | Density tier, lodPlan, contour/error*/stem/step/mesh/radar/sankey payloads |
| `packages/xy-node/test/marks.test.mjs` | Encode / M4 / hist / box / violin / polar goldens |
| `tests/test_node_mark_parity.py` | Live Python↔Node bit parity |
| `tests/test_graph_node_parity.py` | Graph layout goldens |
| Browser mark table | `js/src/55_marks.ts` includes contour, errorbar, stem, triangle_mesh, error_band |

## Invariants (do not regress)

- No JSON numbers on the wire; §29 f32 / u8 columns only.
- Density / LOD decisions recorded on the trace (`tier`, `density.enc`, graph meta).
- Polar never uses cartesian density auto-path.
- Browser never reimplements layout/LOD/encode for the product path.
