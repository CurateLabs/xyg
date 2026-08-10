# @xy/node

Thin Node.js bindings for the shared `xy_core` C ABI cdylib. Uses
[`koffi`](https://koffi.dev/) to load the same `libxy_core.so` as Python
`ctypes` — graph/Sankey layout and LOD decisions stay in Rust
(`spec/design/host-parity.md`).

## Setup

```bash
cargo build --release   # from repo root
cd packages/xy-node && npm ci && npm test
```

## Native library search order

1. `XY_NATIVE_LIB` (absolute path to `libxy_core.so`)
2. `../../target/release/libxy_core.so` (relative to this package)
3. `process.cwd()/target/release/libxy_core.so`

```bash
XY_NATIVE_LIB=/path/to/libxy_core.so npm test
XY_EXPECTED_ABI=55 npm test   # optional ABI golden override
```

## Host composition (graph / marks / sankey)

| Module | Role |
|---|---|
| `src/graph.js` | `normalizeGraphInputs` → dense u64; `runLayout` (ABI layout + `build_render`) → `nodePositions`, `edgeSegments`, meta (`lod_tier`, `member_of`, optional CSR, `source_n_*`) |
| `src/marks/{scatter,line,histogram}.js` | Thin TypedArray builders: encode / M4 / `histogram_uniform` via Rust; attach to `Figure` |
| `src/charts.js` | `scatterChart` / `lineChart` / `histogramChart` / `graphChart` convenience |
| `src/figure.js` | Minimal `Figure` holding `scatter` / `line` / `histogram` / `segments` traces; `buildPayload()` → `{spec, buffers}` with `protocol: PROTOCOL_VERSION` (12) and §29 f32 columns via `xy_encode_f32`. Line M4 when over `DECIMATION_THRESHOLD`. Documented subset of Python `Figure.build_payload`. |
| `src/force_scheduler.js` | Progressive `force_tick` helper — default chunked `setImmediate` loop; `mode: "worker"` uses `worker_threads`. Node-host only (never browser main thread). |
| `src/sankey.js` | Thin `composeSankey` over `xy_sankey_layout` → segment + scatter traces |

```js
import { figure, runLayout, normalizeGraphInputs } from "@xy/node";

const data = normalizeGraphInputs(["a", "b", "c", "d"], [
  ["a", "b"], ["b", "c"], ["c", "d"], ["d", "a"],
]);
const { nodePositions, meta } = runLayout(data, { layout: "circle", seed: 1 });

const fig = figure({ width: 400, height: 300 });
fig.graph(["a", "b", "c", "d"], [["a", "b"], ["b", "c"], ["c", "d"], ["d", "a"]], {
  layout: "circle",
  seed: 1,
});
const { spec, buffers } = fig.buildPayload();
```

### Python ↔ Node circle golden

```bash
cargo build --release
cd packages/xy-node && npm ci
XY_NATIVE_LIB=$PWD/../../target/release/libxy_core.so \\
  uv run pytest tests/test_graph_node_parity.py -q
# or from packages/xy-node:
npm run golden:circle   # JSON positions + f32 hex for inspection
```

### Python ↔ Node mark parity (scatter encode / M4 / hist)

```bash
cargo build --release
cd packages/xy-node && npm ci
# optional: write fixtures for node unit tests
uv run python packages/xy-node/test/fixtures/write_mark_fixtures.py
XY_NATIVE_LIB=$PWD/../../target/release/libxy_core.so npm test
# live Python↔Node goldens:
XY_NATIVE_LIB=$PWD/target/release/libxy_core.so \\
  uv run pytest tests/test_node_mark_parity.py -q
npm run golden:marks   # JSON for inspection
```

```js
import { scatterChart, lineChart, histogramChart, graphChart } from "@xy/node";

const scatter = scatterChart(new Float64Array([0, 1]), new Float64Array([0, 1]));
const line = lineChart(xs, ys);           // M4 when n > DECIMATION_THRESHOLD
const hist = histogramChart(values, { bins: 10, range: [0, 1] });
const graph = graphChart(nodes, edges, { layout: "circle", seed: 1 });
```

## Exports

| Function | Role |
|---|---|
| `abiVersion()` | `xy_abi_version` |
| `graphLayout(layout, nNodes, sources, targets, opts?)` | one-shot layout → `{x, y}` |
| `graphForceCreate` / `graphForceTick` / `graphForceDestroy` | progressive force |
| `graphLodDecision` / `graphClusterAggregate` / `graphBuildRender` / `graphSampleEdges` / `graphBuildCsr` | LOD + render graph + CSR |
| `normalizeGraphInputs` / `runLayout` / `composeGraph` | host composition |
| `composeScatter` / `composeLine` / `composeHistogram` | mark builders (TypedArray → traces) |
| `scatterChart` / `lineChart` / `histogramChart` / `graphChart` | convenience figures |
| `figure` / `Figure` / `buildPayload` | minimal figure + §29 payload subset |
| `runForceTicks` | progressive tick scheduler |
| `sankeyLayout` / `composeSankey` | Sankey placement |

Layout names match Python `_native.py`: `preset`, `grid`, `circle`, `force`,
`breadthfirst`, `auto`, `radial`, `concentric`; aliases `dagre` /
`hierarchical` → hierarchical ABI id.
