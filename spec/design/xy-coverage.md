# XYG full-surface coverage

**Status:** living checklist for chart-family coverage across the three runtime
surfaces ([host-parity.md](host-parity.md) §0) and utilization of the
performance architecture ([lod-architecture.md](lod-architecture.md),
dossier §28).

Machine-readable twin: [`dual-host-parity.json`](dual-host-parity.json)
(`mark_kinds`, `lod_tiers`, `runtimes`).

## Surfaces

| Surface | Composition API | Scale path |
| --- | --- | --- |
| Python | `python/xyg/components.py` + `marks.py` → `Figure.build_payload` | Density / M4 / hexbin / graph render-graph / LOD plan |
| Node | `packages/xy-node` `charts.js` + `marks/*` → `Figure.buildPayload` | Same Rust ABI: density, M4, hist, graph LOD, lodPlan |
| Browser | `js/src` → `@curatelabs/xyg` (`packages/xy-client/dist`); Python copies into `python/xyg/static/` | Paint / pick only on §29 buffers (`55_marks.ts` kind table) |

## Chart classifications (must ship on every host)

| Classification | Families | Node entry points |
| --- | --- | --- |
| Point / path | scatter, line, area, step, stairs, stem, ecdf | `*Chart` + `compose*` |
| Distribution | histogram, box, violin, hexbin | same |
| Grid / field | heatmap, contour, triangle_mesh | same |
| Interval / uncertainty | errorbar, error_band | same |
| Categorical / flow | bar, column, pie, sankey (ribbon), funnel* | `barChart` / `sankeyChart` / polar |
| Polar | polar, radar, wind_rose | `polarChart` / `radarChart` / `windRoseChart` |
| Graph | graph | `graphChart` / `composeGraph`; direct browser consumes Rust-owned semantic Scene paint; native compound Scene resolution owns transitive bounds/collapse and all painter/export/a11y consumers share its output |
| GraphForge canonical graph | `from_graphforge_tables` | `fromGraphForgeTables`; ABI 60 UUID/topology/parent parity |
| Layout | facet | `facetChart` |

\*Funnel: Python ready; Node may compose via bar/ribbon helpers — track in
`dual-host-parity.json` if a dedicated composer lands.

## Performance architecture utilization

| Tier | Contract | Python | Node | Browser |
| --- | --- | --- | --- | --- |
| 1 Direct | Exact marks under budget; line M4 when over threshold | ready | ready | paints direct |
| 2 Density / aggregate | Scatter log-u8 density; hexbin; graph render-graph | ready | ready (`force_density` / auto ≥ 200k) | paints density / aggregates |
| 3 Tile pyramid | Multi-res count pyramid; compose O(cells) | ready (first paint + density_view) | ready (`pyramid.js`) | receives composed grids |

**Scale evidence (not raw 1B allocation in CI):**

- `benchmarks/bench_scale_all_charts.py` — Python families + graph LOD classes
- `benchmarks/bench_scale_all_charts_node.mjs` — Node twin for mark families + density
- `benchmarks/bench_graph_scale_classes_node.mjs` — 10M / 100M / 1B LOD decisions
- `benchmarks/bench_tier3_pyramid.{py,mjs}` — build-once / compose-many; see [tier3-testing.md](tier3-testing.md)

Every profile records screen-bounded budgets; Tier-3 CI proves pyramid compose
is O(grid) with modest N — it does not allocate a billion points. Phase-4
disk-resident 256² tile spill is the next residency milestone —
[tier3-phase4-roadmap.md](tier3-phase4-roadmap.md) /
[#5](https://github.com/CurateLabs/xyg/issues/5).

## Tests

| Suite | What it proves |
| --- | --- |
| `packages/xy-node/test/coverage.test.mjs` | Density tier, lodPlan, contour/error*/stem/step/mesh/radar/sankey payloads |
| `packages/xy-node/test/marks.test.mjs` | Encode / M4 / hist / box / violin / polar goldens |
| `tests/test_node_mark_parity.py` | Live Python↔Node bit parity |
| `tests/test_graph_node_parity.py` | Graph layout goldens |
| `tests/test_graphforge_semantic_evidence.py` | Exact light/dark GraphForge semantic compound Scene, painter, SVG, raster, PNG, collapse, label, and stable-ID goldens |
| `tests/browser/wasm_foundation_page.mjs` | Direct-WASM semantic graph paint, identity, Rust-placed labels/truncation, legend, theme, and accessibility parity |
| Browser mark table | `js/src/55_marks.ts` includes contour, errorbar, stem, triangle_mesh, error_band |

## Invariants (do not regress)

- No JSON numbers on the wire; §29 f32 / u8 columns only.
- Density / LOD decisions recorded on the trace (`tier`, `density.enc`, graph meta).
- Polar never uses cartesian density auto-path.
- Browser never reimplements layout/LOD/encode for the product path.
