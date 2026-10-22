# Published Core 0.6.0-rc.5 result evidence (#936)

This directory contains 112 Arrow IPC fixtures produced by the actual published
`@curatelabs/graphforge@0.6.0-rc.5` Linux x64 GNU binding: 96 algorithm
contracts, all successful, plus `find` and matching base graph tables.
`generation.json` records exact npm versions/integrities, Core source commit,
generator and manifest hashes, Node version and platform. The Core-owned
schema export is pinned separately in `../core/0.6.0-rc.5`.

```bash
npm install --prefix /tmp/xyg-core-fixtures --ignore-scripts --no-audit --no-fund @curatelabs/graphforge@0.6.0-rc.5
node scripts/gen_graphforge_result_fixtures.cjs /tmp/xyg-core-fixtures/node_modules/@curatelabs/graphforge tests/fixtures/graphforge/results-0.6.0-rc.5
```

The generator replaces its explicit output directory. Core mints fresh UUIDs;
all result and base files must be regenerated together. Never combine these
with the original 0.5.2 fixtures in `../results`.

`bfs_depth` yields cost 1; `dijkstra_cost` uses the weighted graph and yields
cost 4.25. Both produce source/target UUIDs and a cost, with no path. XYG maps
these to distinct derived endpoint pairs carrying cost, without pretending
there is an ordered path or persisted relationship. Python independently
decodes the rows to check endpoint identity and cost; Node and actual WASM
compose all 96 algorithm fixtures. Existing unsupported-schema fixtures also
prove fail-closed diagnostics on every host.

This is exact Core result qualification, not proof of a published XYG/Core
artifact cohort or editor installation. Those remain #108/#884; editor #90
must consume that package before deleting its ledger copy.
