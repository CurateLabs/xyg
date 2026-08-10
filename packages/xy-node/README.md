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
XY_EXPECTED_ABI=53 npm test   # optional ABI golden override
```

## Host composition (graph / sankey)

| Module | Role |
|---|---|
| `src/graph.js` | `normalizeGraphInputs` → dense u64; `runLayout` (ABI layout + `build_render`) → `nodePositions`, `edgeSegments`, meta (`lod_tier`, `member_of`, optional CSR, `source_n_*`) |
| `src/figure.js` | Minimal `Figure` holding `scatter` / `segments` traces; `buildPayload()` → `{spec, buffers}` with `protocol: PROTOCOL_VERSION` (12) and §29 f32 columns via `xy_encode_f32`. Documented subset of Python `Figure.build_payload` for graph goldens. |
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

## Exports

| Function | Role |
|---|---|
| `abiVersion()` | `xy_abi_version` |
| `graphLayout(layout, nNodes, sources, targets, opts?)` | one-shot layout → `{x, y}` |
| `graphForceCreate` / `graphForceTick` / `graphForceDestroy` | progressive force |
| `graphLodDecision` / `graphClusterAggregate` / `graphBuildRender` / `graphSampleEdges` / `graphBuildCsr` | LOD + render graph + CSR |
| `normalizeGraphInputs` / `runLayout` / `composeGraph` | host composition |
| `figure` / `Figure` / `buildPayload` | minimal figure + §29 payload subset |
| `runForceTicks` | progressive tick scheduler |
| `sankeyLayout` / `composeSankey` | Sankey placement |

Layout names match Python `_native.py`: `preset`, `grid`, `circle`, `force`,
`breadthfirst`, `auto`, `radial`, `concentric`; aliases `dagre` /
`hierarchical` → hierarchical ABI id.
