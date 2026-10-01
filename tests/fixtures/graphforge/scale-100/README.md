# GraphForge 100-node parity fixture

One real GraphForge 0.5.2 run on the seeded 100-node bulk graph from
`benchmarks/gen_graphforge_scale_inputs.py`: the base dump
(`MATCH (n) RETURN n`, `MATCH ()-[r]->() RETURN r`) and the engine's
`pagerank`, `louvain`, `minimum_spanning_tree`, and `dijkstra` results, with
the generation used to compose them (`manifest.json`). GraphForge mints fresh
UUIDs per run, so all files come from one run:

```bash
uv run python benchmarks/gen_graphforge_scale_inputs.py --out /tmp/gfscale --sizes 100
node benchmarks/bench_graphforge_compose.mjs --inputs /tmp/gfscale --sizes 100 --reps 1 \
  --graphforge path/to/node_modules/@curatelabs/graphforge \
  --fixture-out tests/fixtures/graphforge/scale-100 --out /tmp/bench.json
```

`packages/xy-node/test/graphforge-wasm-parity.test.mjs` renders it through the
native core and the wasm32 artifact and requires byte-identical documents and
Scenes. The graph is large enough for layout seeding and dash/arrow geometry
to expose platform-`libm` differences that the tiny contract fixtures miss.
