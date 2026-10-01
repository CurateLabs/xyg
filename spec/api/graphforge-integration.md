# GraphForge integration note (for GraphForge for VS Code, #80)

How the extension hands GraphForge results to XYG and paints them. Design and
full contract: [../design/graphforge-compositions.md](../design/graphforge-compositions.md).
Split of responsibilities (graphforge-vscode#80 Rust/WASM amendment):
GraphForge computes; the extension supplies result bytes, the base graph,
generation identity, and explicit intent; **Rust owns recognition, joins,
identity policy, composition, layout, and the Scene** on both hosts. The
extension never rebuilds a registry, join, LOD, layout, or encoding policy.

## 1. What to pass

Everything is GraphForge Arrow IPC bytes exactly as the engine returned them
(`Uint8Array`/`Buffer`/`ArrayBuffer`); XYG decodes them in Rust.

| Input | Where it comes from | Notes |
|---|---|---|
| `layers[i].result` | the engine result (`g.rank(...)`, `g.cluster(...)`, `g.paths(...)`, `g.analyze(...)`, `g.similar(...)`, `g.find(...)`) | recognized from `graphforge.verb` / `graphforge.algorithm` / `graphforge.algorithm_schema_version` (or `graphforge.search_schema_version`) |
| `layers[i].intent` | the user's choice among the ledger's intents | required; XYG never picks one (see table below) |
| `layers[i].resultId`, `layers[i].generation` | `ResultProvenance.resultId`, `.generationUuid` | echoed back on every pick for table ↔ chart linking |
| `base.tables` | the graph the result belongs to, read at the same generation, e.g. `g.execute("MATCH (n) RETURN n")` and `g.execute("MATCH ()-[r]->() RETURN r")` (Cypher entity structs), or `RETURN a, r, b` / path results, or flat `node_uuid` / `edge_uuid` + endpoint tables | required for `graph` intent; optional elsewhere (display names, stale checks) |
| `base.generation` | the generation `CURRENT` named when the base tables were read | a stale result fails with `GF_COMPOSE_GENERATION_STALE` |
| `layers[i].missing` / `.extra` | optional policy | defaults: dim uncovered base elements; fail on identities absent from the base |
| `layers[i].rows` | optional explicit result rows | e.g. one path of an all-pairs result |
| `layers[i].coordinates` | caller 2D reduction for embeddings (Arrow IPC `node_uuid`, `x`, `y`) | embeddings are never plotted from dimensions 0/1 |
| `select` | UUIDs selected in the results table | painted in the selected state by Rust |

Intent per extension disposition (the full per-schema ledger is
`graphforgeLedger()` / `xyg_graphforge_ledger_tsv`, and agrees with
`RESULT_SCHEMAS.md` by test):

| Extension disposition | XYG intent(s) | Result |
|---|---|---|
| `node-layer`, `edge-layer`, `derived-edges`, `ordered-paths` | `graph` | base graph + result planes, derived edges dashed with a halo, ordered steps with arrows |
| `composition-required` — `edge-color` | `graph` | edge colors joined onto the base relationships |
| `composition-required` — `embedding` | `parallel-coordinates`, or `embedding-coordinates` with `coordinates` | full-vector view, or the caller's 2D placement |
| `table-only` scalars | `table` | canonical columns, text cells |
| `table-only` categories (conductance, triad/dyad census) | `table` or `bar-chart` | bars in result order |
| `entity-graph` (Cypher) | — | pass as `base.tables` |

Several `graph` layers compose together when they write different channels
(e.g. PageRank size + community class + spanning-tree overlay + a path);
two layers writing one channel fail with `GF_COMPOSE_CHANNEL_CONFLICT`.

## 2. Node host (extension host process)

```js
import {
  composeGraphForge, graphforgeWebviewPayload, graphforgePick,
  graphforgeTableHtml, graphforgeLedger, GraphForgeCompositionError,
} from "@curatelabs/xyg-node/graphforge";
import { loadXygNode, LOAD_ERROR_CODES } from "@curatelabs/xyg-node/load";

const loaded = await loadXygNode();   // never throws; messages carry no paths
if (!loaded.ok) return showUnavailable(loaded.code);      // stable code (§6)

const composition = composeGraphForge({
  base: { tables: [nodesIpc, edgesIpc], generation: generationUuid },
  layers: [{ result, intent: "graph", resultId, generation: generationUuid }],
  select: selectedUuids,                                  // optional
});
composition.kind;              // "graph" | "table" | "bar-chart" | "parallel-coordinates" | "scatter"
composition.identify("node", i);   // { uuid, layers: [{ layer, resultId, row }] }
composition.select(uuids);         // { nodes: [i], edges: [j] }
composition.diagnostics();         // value-free: schema ids, counts, decision codes
const { spec, buffer, figure, positions } = graphforgeWebviewPayload(composition, { width, height, theme });
graphforgePick(figure, composition, { trace, index });     // relayed webview click → identity
// Recomposing the same base (new layers, selection, theme): reuse the layout.
graphforgeWebviewPayload(next, { width, height, theme, positions });
graphforgeTableHtml(tableComposition);                     // escaped <table> for table intents
```

Failures throw `GraphForgeCompositionError` (`code`, `layer`, `field`,
value-free `message`). `encodeGraphForgeRequest(input)` /
`composeGraphForgeRequest(bytes)` / `decodeGraphForgeDocument(bytes)` expose
the raw `XYGQ`/`XYGF` bytes (e.g. to compose in the webview instead).

## 3. Direct-browser WASM host (webview)

```js
import { createXygWasmWorker, renderWasmGraphForge, composeWasmGraphForge,
         encodeWasmGraphForgeRequest, graphforgeTableElement } from "@curatelabs/xyg";

// Webview resources are cross-origin: build the Worker from a Blob.
const source = await (await fetch(workerUri)).text();
const workerUrl = URL.createObjectURL(new Blob([source], { type: "text/javascript" }));
const wasm = new Uint8Array(await (await fetch(wasmUri)).arrayBuffer());
const worker = createXygWasmWorker({ workerUrl, wasm, maxArenaBytes: 64 << 20 });

const { view, composition } = await renderWasmGraphForge({
  el, worker, width, height, theme,
  input: { base: { tables, generation }, layers: [{ result, intent: "graph", resultId, generation }] },
});
view.root.addEventListener("xy:graphforge-select", (e) => vscode.postMessage({ type: "xyg.pick", ...e.detail }));
```

`decodeWasmGraphForgeDocument` / `composeWasmGraphForge` reject with
`XygWasmError` carrying the Rust `code`, `layer`, and `field`. The WASM Scene
is direct tier (≤ 1,024 nodes + edges; `GF_COMPOSE_SCENE_TOO_LARGE` above);
use the Node host for larger graphs. Documents are byte-identical to the
native host's for the same request.

## 4. Webview CSP and messages

```text
default-src 'none';
script-src 'nonce-${nonce}' ${webview.cspSource} 'wasm-unsafe-eval';
style-src ${webview.cspSource} 'unsafe-inline';
img-src ${webview.cspSource} data: blob:;
font-src ${webview.cspSource};
connect-src ${webview.cspSource};
worker-src blob:;
```

Load `@curatelabs/xyg`'s `index.js` (or `standalone.js`) from the extension's
media folder with the nonce; no CDN or network access is needed. The native
path renders with `xy.renderStandalone(el, spec, buffer)`. Messages (UUIDs
only, never logged): `xyg.render` host→webview (`{spec, buffer}` or an `XYGQ`
request), `xyg.pick` webview→host (native `{trace, index}` → `graphforgePick`;
WASM the `xy:graphforge-select` detail), `xyg.select` host→webview (`{uuids}`:
recompose with `select`, re-render), `xyg.error` (`{code, layer, field,
message}`). Details: design §6.4.

## 5. Versions

| Constant | Value | Where |
|---|---|---|
| Native C ABI | 378 | `abiVersion()`, `xyg_abi_version` |
| WASM ABI | 27 | `XYG_WASM_ABI_VERSION`, `xyg_wasm_abi_version` |
| Scene | 31 | `SCENE_VERSION` |
| Paint protocol | 12 | `PROTOCOL_VERSION` |
| `XYGF` composition semantics | 1 | `GRAPHFORGE_COMPOSITION_VERSION`, `composition.version` |
| Container (`XYGQ`/`XYGF`) | 1 | header word |
| Coverage ledger | 1 | `composition.ledgerVersion` |
| GraphForge algorithm / search schema | 1 / 1 | ledger (GraphForge 0.5.2: 94 algorithms) |

## 6. Error codes

| Family | Codes |
|---|---|
| Arrow bytes | `GF_ARROW_MALFORMED`, `GF_ARROW_UNSUPPORTED` (dictionary, compression, big-endian), `GF_ARROW_LIMIT` |
| Result schema (same as the extension ledger) | `GF_RESULT_SCHEMA_UNREGISTERED`, `GF_RESULT_SCHEMA_VERSION`, `GF_RESULT_SCHEMA_MISMATCH`, `GF_RESULT_NOT_ALGORITHM`, `GF_RESULT_NULL_IDENTITY`, `GF_RESULT_UUID_INVALID`, `GF_RESULT_VALUE_RANGE` |
| Base graph | `GF_BASE_SCHEMA`, `GF_BASE_EMPTY`, `GF_BASE_ENDPOINT_MISSING`, `GF_BASE_EDGE_CONFLICT`, `GF_BASE_NULL_IDENTITY` |
| Composition | `GF_COMPOSE_REQUEST_INVALID`, `GF_COMPOSE_VERSION`, `GF_COMPOSE_INTENT_REQUIRED`, `GF_COMPOSE_INTENT_INVALID`, `GF_COMPOSE_INTENT_UNSUPPORTED`, `GF_COMPOSE_INTENT_CONFLICT`, `GF_COMPOSE_BASE_REQUIRED`, `GF_COMPOSE_GENERATION_STALE`, `GF_COMPOSE_GENERATION_MISSING`, `GF_COMPOSE_EXTRA_IDS`, `GF_COMPOSE_MISSING_IDS`, `GF_COMPOSE_DUPLICATE_ID`, `GF_COMPOSE_IDENTITY_KIND`, `GF_COMPOSE_EDGE_ENDPOINT_MISMATCH`, `GF_COMPOSE_CHANNEL_CONFLICT`, `GF_COMPOSE_TOO_LARGE`, `GF_COMPOSE_COORDINATES_REQUIRED`, `GF_COMPOSE_COORDINATES_MISSING`, `GF_COMPOSE_COORDINATES_INVALID` |
| Scene | `GF_COMPOSE_RENDER_UNSUPPORTED`, `GF_COMPOSE_SCENE_TOO_LARGE`, `GF_COMPOSE_SCENE_INVALID`, `GF_COMPOSE_SCENE_EMPTY` (every node hidden: `renderWasmGraphForge` rejects, the document records the decision) |
| Document decoding | `GF_COMPOSE_DOCUMENT_INVALID` (a supplied document is malformed or its sections disagree on shape) |
| Native loading (`LOAD_ERROR_CODES`) | `XYG_NATIVE_UNSUPPORTED_PLATFORM`, `XYG_NATIVE_LIBRARY_MISSING`, `XYG_NATIVE_LIBRARY_PATH_INVALID`, `XYG_NATIVE_LOAD_FAILED`, `XYG_NATIVE_ABI_MISMATCH` (also a library without `xyg_abi_version`), `XYG_NODE_DEPENDENCY_MISSING` (e.g. `koffi` absent), `XYG_NODE_IMPORT_FAILED`; messages never include filesystem paths or loader text |
| WASM init | `XYG_WASM_ABI_MISMATCH`, `XYG_WASM_SCENE_MISMATCH`, `XYG_WASM_PALETTE_MISMATCH`, `XYG_WASM_EXPORT_MISMATCH`, `XYG_WASM_IMPORTS_REJECTED`, `XYG_WASM_BUDGET_EXCEEDED`, `XYG_WASM_INSTANCE_EXHAUSTED`, `XYG_WASM_INIT_FAILED` (asset loading) |

Recorded (non-fatal) decisions arrive in `composition.decisions` as
`{code, layer, count}`: e.g. `GF_COMPOSE_MISSING_DIMMED`,
`GF_COMPOSE_EXTRA_DROPPED`, `GF_COMPOSE_GROUPS_BUCKETED`,
`GF_COMPOSE_GENERATION_UNVERIFIED`; they are safe to log.

## 7. Consuming the packages

- `@curatelabs/xyg-node` (facade: JS, the offline standalone client, NOTICE)
  plus exactly one `@curatelabs/xyg-node-<platform>` (`darwin-arm64`,
  `darwin-x64`, `linux-x64`, `linux-arm64`, `win32-x64`; the native core with
  its NOTICE). Linux cores are the release wheels' `manylinux_2_17` builds, so
  the glibc floor is 2.17, the same as `pip install xyg`.
- `@curatelabs/xyg` (browser: `index.js`, `standalone.js`, `wasm-worker.js`,
  `xyg-wasm.wasm`, `ASSET-MANIFEST.json` with sizes and SHA-256, NOTICE).
  Copy these into the extension's media folder; do not mix versions.
- Until public npm publication (#13/#108), consume the exact-version
  candidate tarballs the `Release` workflow (`publish.yaml`) builds and
  retains as run artifacts (`node-facade`, `node-platform-<platform>`,
  `browser-package`), e.g.
  `npm install ./curatelabs-xyg-node-<v>.tgz ./curatelabs-xyg-node-linux-x64-<v>.tgz`.
  Its clean-install job proves every platform package loads and composes
  GraphForge fixtures from the packed artifacts.
- In a VSIX, keep the platform package external to any bundler (it is a
  native binary resolved by exact package name) and ship one VSIX per
  platform, or all platform packages, per VS Code's platform-specific
  extension rules.

## 8. Known limits

- Scale (spec/benchmarks/results.md, "GraphForge composition scale"): Rust
  composition takes about 0.2 s for four layers over 100k nodes, but the
  graph-mark chart build (force layout) takes about 13 s. The webview spec
  JSON reaches about 98 MiB at 100k because of per-element tooltip rows, so
  for very large graphs select rows (`layers[].rows`, `select`) or reuse
  positions across recompositions.

- WASM Scene: direct tier only (≤ 1,024 elements).
- Scene positions come from Rust's seeded force layout with a `libm`-free
  seed, so documents and Scene bytes are bit-identical across hosts and
  platforms.
