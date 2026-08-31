# @curatelabs/xyg-node

Thin Node.js bindings for the shared `xyg_core` C ABI cdylib. Uses
[`koffi`](https://koffi.dev/) to load the same `libxyg_core` artifact as Python
`ctypes` — graph/Sankey layout and LOD decisions stay in Rust
(`spec/design/host-parity.md`). The in-tree directory stays `packages/xy-node`;
never publish `@xy/node`.

**Use from Node servers and VS Code extensions.** The package is
runtime-dependency-light (koffi + the shared cdylib), exports a stable
`createEngine()` / chart-builder API, and never touches `window` /
`document`. VS Code webviews should load the host-neutral paint client
(`@curatelabs/xyg` / `packages/xy-client/dist` standalone IIFE) with §29
buffers produced by the extension host — see `src/vscode.js`. Do not point
webviews at `python/xyg/static`. HTML export is `figure.toHtml()` /
`toHtml(payload)`, which inlines that same standalone client.

## Setup

```bash
cargo build --release   # from repo root
cd packages/xy-node && npm ci && npm test
```

## Native library search order

The facade selects **only** the exact `process.platform`/`process.arch`
optional package (#52). Source checkouts may use one explicit override:

1. Exact optional platform package (when installed and its binary is staged):
   - `@curatelabs/xyg-node-darwin-arm64`
   - `@curatelabs/xyg-node-darwin-x64`
   - `@curatelabs/xyg-node-linux-x64`
   - `@curatelabs/xyg-node-linux-arm64`
   - `@curatelabs/xyg-node-win32-x64`
2. `XYG_NATIVE_LIB` (absolute path to `libxyg_core.so` / `.dylib` / `xyg_core.dll`)

Lookup never searches repository, current-working-directory, or system library
paths, never falls back to Python, and never loads a wrong-architecture optional package. **Windows arm64**
returns a stable unsupported-platform error before any search.

For local development, stage the built cdylib into the matching in-tree
platform package:

```bash
cargo build --release
python3 scripts/stage_node_platform_natives.py --also-facade
python3 scripts/stage_node_platform_natives.py --list
python3 scripts/verify_node_packages.py
python3 scripts/verify_node_packages.py --sbom /tmp/xyg-node-sbom.json
python3 scripts/verify_node_packages.py --require-native   # after staging
```

Each Node package ships a `NOTICE` (Apache-2.0 plus koffi MIT attribution on the
facade). `--sbom` writes a CycloneDX-lite document from local manifests/hashes
without contacting the npm registry.

Release packaging never rewrites those private source manifests. It extracts
the already-verified native from the matching release wheel and creates a
fresh publish tree with an exact tag-derived npm semver:

```bash
python3 scripts/stage_node_packages.py \
  --tag xyg-v0.6.0rc1 --output /tmp/xyg-node-release \
  --platform linux-x64 --wheel dist/xyg-0.6.0rc1-*-manylinux_2_17_x86_64.whl
python3 scripts/stage_node_packages.py \
  --tag xyg-v0.6.0rc1 --output /tmp/xyg-node-release \
  --facade --client packages/xy-client/dist/standalone.js
```

The facade embeds that exact standalone artifact under `client/`, so
`toHtml()` remains self-contained after a clean npm install and does not need
Python, a CDN, a repository checkout, or a second runtime package lookup.

```bash
XYG_NATIVE_LIB=/path/to/libxyg_core.dylib npm test
XYG_EXPECTED_ABI=60 npm test   # optional ABI golden override
```

## Paint client (HTML / webviews)

Native `.so` lookup (above) is the Rust engine. The WebGL paint client is a
separate host-neutral artifact:

1. `@curatelabs/xyg` / `packages/xy-client/dist/standalone.js` (IIFE `window.xy`)
2. `@curatelabs/xyg` / `packages/xy-client/dist/index.js` (ESM `render`)

`toHtml()` and VS Code webviews use that path. They must not read
`python/xyg/static` (that directory is the Python wheel **copy** of the same
files). From a source checkout: `npm ci && node js/build.mjs` at the repo root.

## Host composition (graph / marks / sankey)

| Module | Role |
|---|---|
| `src/graph.js` | `normalizeGraphInputs` → dense u64; `runLayout` (ABI layout + `build_render`) → `nodePositions`, `edgeSegments`, meta (`lod_tier`, `member_of`, optional CSR, `source_n_*`) |
| `src/marks/*.js` | Thin TypedArray builders for every chart family (scatter→radar); Rust kernels only |
| `src/charts.js` | `*Chart` convenience constructors for all dual-host families |
| `src/figure.js` | Minimal `Figure`; `buildPayload()` → `{spec, buffers}` (`protocol: 12`); `toHtml()` inlines `@curatelabs/xyg` standalone. Scatter **density tier** when `n > SCATTER_DENSITY_THRESHOLD` (or `forceDensity`; ABI 122 `payloadTier`). Line M4 when over `DECIMATION_THRESHOLD` (polar stays direct). Contour/errorbar/stem/mesh/ribbon/radar covered. |
| `src/force_scheduler.js` | Progressive `force_tick` helper — defaults to `worker_threads`; explicit `mode: "immediate"` is batch/test-only. Node-host only (never browser main thread). |
| `src/sankey.js` | Thin `composeSankey` over `xyg_sankey_layout` → ribbon band polygons (link + node) |
| `src/vscode.js` | VS Code extension-host re-export + webview notes (`@curatelabs/xyg`, not the Python tree) |
| `src/html.js` | `toHtml()` — self-contained HTML inlining host-neutral `standalone.js` |

Coverage matrix + LOD tiers: `spec/design/xy-coverage.md` and
`spec/design/dual-host-parity.json`.

```js
import { createEngine, runLayout, normalizeGraphInputs, abiVersion } from "@curatelabs/xyg-node";
// or: import { scatterChart, graphChart } from "@curatelabs/xyg-node/charts";
// or: import { runLayout } from "@curatelabs/xyg-node/graph";
// or: import { createEngine } from "@curatelabs/xyg-node/vscode";

const data = normalizeGraphInputs(["a", "b", "c", "d"], [
  ["a", "b"], ["b", "c"], ["c", "d"], ["d", "a"],
]);
const { nodePositions, meta } = runLayout(data, { layout: "circle", seed: 1 });

const fig = createEngine({ width: 400, height: 300 });
fig.graph(["a", "b", "c", "d"], [["a", "b"], ["b", "c"], ["c", "d"], ["d", "a"]], {
  layout: "forceatlas2",
  seed: 1,
});
const { spec, buffers } = fig.buildPayload();
console.log(abiVersion());
```

### Python ↔ Node circle golden

```bash
cargo build --release
cd packages/xy-node && npm ci
XYG_NATIVE_LIB=$PWD/../../target/release/libxyg_core.so \\
  uv run pytest tests/test_graph_node_parity.py -q
# or from packages/xy-node:
npm run golden:circle   # JSON positions + f32 hex for inspection
```

### Bounded Rust Scene chrome

`Figure.toScene()` is the public Node seam for the bounded, literal Cartesian
Scene contract. Constructor options and fluent setters only snapshot authored
literals; Rust still validates them and resolves all ticks, gutters, legend,
colorbar, and render geometry.

```js
const fig = createEngine({
  width: 640, height: 400,
  style: { background: "#f0f8ff", "--chart-bg": "#f8fafc" },
  legend: { loc: "upper right", title: "Series", toggle: false, highlight: false },
  xAxis: { domain: [0, 1], side: "top", tick_values: [0, 0.5, 1] },
  yAxis: { domain: [0, 1], side: "right", minor_tick_values: [0.25, 0.75] },
});
fig.setColorbar({
  domain: [0, 1],
  stops: [[0, [15, 23, 42, 255]], [1, [253, 224, 71, 255]]],
});
fig.scatter([0.25, 0.75], [0.4, 0.6], { name: "observations", style: { symbol: "diamond" } });
const scene = fig.toScene();
```

Unsupported CSS, custom typography, gradients, non-Cartesian layout, and rich
annotation policy fail closed; do not implement them in Node.

### Python ↔ Node mark parity (scatter encode / M4 / hist)

```bash
cargo build --release
cd packages/xy-node && npm ci
# optional: write fixtures for node unit tests
uv run python packages/xy-node/test/fixtures/write_mark_fixtures.py
XYG_NATIVE_LIB=$PWD/../../target/release/libxyg_core.so npm test
# live Python↔Node goldens:
XYG_NATIVE_LIB=$PWD/../../target/release/libxyg_core.so \\
  uv run pytest tests/test_node_mark_parity.py -q
npm run golden:marks   # JSON for inspection
```

```js
import {
  scatterChart,
  lineChart,
  histogramChart,
  contourChart,
  errorbarChart,
  radarChart,
  sankeyChart,
  graphChart,
} from "@curatelabs/xyg-node";

const scatter = scatterChart(new Float64Array([0, 1]), new Float64Array([0, 1]));
const dense = scatterChart(xs, ys, { forceDensity: true }); // Tier-2 density
const line = lineChart(xs, ys);           // M4 when n > DECIMATION_THRESHOLD
const hist = histogramChart(values, { bins: 10, range: [0, 1] });
const graph = graphChart(nodes, edges, {
  layout: "cose",
  seed: 1,
  x: new Float64Array([-0.5, 0.5]),
  y: new Float64Array([0, 0]),
  pinned: new Uint8Array([1, 0]),
  cose: { idealEdgeLength: 0.4, bounds: [-1, -1, 1, 1] },
});
```

## Exports

| Function | Role |
|---|---|
| `createEngine()` | stable engine entry (`figure` alias) |
| `toHtml()` / `Figure.toHtml()` | standalone HTML inlining `@curatelabs/xyg` (not `python/xyg/static`) |
| `abiVersion()` | `xyg_abi_version` |
| `graphLayout` / `graphForce*` / `graphLod*` / `graphBuildRender` | layout + LOD + render graph |
| `normalizeGraphInputs` / `runLayout` / `composeGraph` | host composition |
| `composeScatter` … `composeRadar` / `composeSankey` | mark builders |
| `scatterChart` … `radarChart` / `sankeyChart` / `graphChart` | convenience figures |
| `bin2d` / `densityLogU8` / `lodPlan` / `payloadTier` / `shouldUseDensity` | Tier-2 LOD helpers |
| `figure` / `Figure` / `buildPayload` | minimal figure + §29 payload |
| `runForceAnimation` | progressive tick scheduler |

`runForceAnimation`/`runForceTicks` defaults to a dedicated worker thread and
emits `initial`, `update`, and `complete` checkpoints tagged with the caller's
`revision`/`jobId`. `AbortSignal`, `chunkSteps`, and `maxWallMs` bound work;
interactive callers should not select the explicit batch/test-only
`mode: "immediate"` escape hatch.

Layout names match Python `_native.py`: `preset`, `grid`, `circle`,
`force`/`fr`, `spring`, `forceatlas2`/`fa2`, `kamada_kawai`/`kk`,
`yifanhu`, `linlog`, `stress`, `barnes_hut`, `breadthfirst`, `auto`,
`radial`, `concentric`, `cose`; aliases `dagre` / `hierarchical` → hierarchical
ABI id. Kamada–Kawai / stress fall back to FR when `n > 500`.

Configured CoSE accepts `idealEdgeLength`, `repulsionStrength`,
`gravityStrength`, `coolingFactor`, `overlapPadding`, `componentSpacing`, and
`bounds`. `pinned` is a node-length u8/bool mask and requires `x` plus `y`;
`parents` is a node-length `BigUint64Array` using `2n ** 64n - 1n` for roots. Invalid
input fails instead of selecting another layout.
