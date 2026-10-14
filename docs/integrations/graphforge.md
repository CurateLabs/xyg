---
title: Use with GraphForge
description: Compose canonical GraphForge results into charts with Python, Node-native, and bounded browser WASM hosts.
---

# Use with GraphForge

We forked upstream XY because GraphForge needed billion-scale graph visualization.
GraphForge Core owns storage, queries, algorithms, and canonical Arrow result
schemas. XYG owns the conversion of those results into visualizations:
composition intent, UUID joins, generation checks, layout, level of detail,
styles, picking identity, and exports. Neither component reimplements the
other. GraphForge Core runs natively; XYG's browser WASM host runs the
visualization engine rather than GraphForge queries.

The examples below describe the current source checkout. See
[Installation](/docs/xy/overview/installation/) for published artifacts and
source setup. Billion-scale graph visualization remains the goal; the
[benchmark guide](/docs/xy/overview/benchmarks/) distinguishes executed graph
capacity from policy checks and scatter-density demonstrations.

## Choose your input

For a node-link view of canonical node and relationship projections, use
`xyg.from_graphforge_tables()` and `xyg.graph_chart(xyg.graph(...))`, or Node's
`fromGraphForgeTables()` and `composeGraph()`. These accept column mappings or
supported Arrow tables. The [graph guide](/docs/xy/charts/graph/) includes
complete examples.

For analytical results, pass **canonical Arrow IPC bytes** to the composition
API. It accepts IPC streams and files with uncompressed, little-endian bodies;
dictionary encoding and compressed IPC are unsupported. Keep the GraphForge
schema metadata intact. Do not convert analytical results into generic JSON
rows: Rust recognizes the schema, validates its fields, and joins identities.

Every result layer includes an explicit `intent`: `graph`, `table`,
`bar-chart`, `parallel-coordinates`, or `embedding-coordinates`, as supported
by that result
schema. XYG checks this choice against its Rust coverage ledger; it does not
infer analytical meaning from column names or choose an intent for you.

## Python

Given base-node, base-edge, and PageRank IPC bytes from one GraphForge
generation, build a chart with an analytical layer:

```python
import xyg


def visualize_graphforge(nodes_ipc, edges_ipc, pagerank_ipc, generation_uuid):
    composition = xyg.compose_graphforge(
        base={"tables": [nodes_ipc, edges_ipc], "generation": generation_uuid},
        layers=[
            {
                "result": pagerank_ipc,
                "intent": "graph",
                "result_id": "pagerank",
                "generation": generation_uuid,
            }
        ],
    )
    chart = xyg.graphforge_chart(composition, width=900, height=600)
    return composition, chart
```

`generation_uuid` is the source generation's UUID, not a new UUID created for
visualization. `result_id` is your identifier for the result, used to link
picks back to its rows. Display the returned chart in a notebook or use
`chart.to_html("graph.html")`. Static formats follow the current
[export coverage](/docs/xy/guides/display-and-export/).

Tables use `xyg.graphforge_table_html(composition)`; other supported chart
intents use `xyg.graphforge_chart(composition)`. `xyg.graphforge_ledger()`
reports the engine's schema and intent coverage. These byte-based composition
helpers need no GraphForge import or `pyarrow` dependency in XYG.

## Node and VS Code extension hosts

Node calls the same Rust composition through the native C ABI:

```javascript
import {
  composeGraphForge,
  graphforgeChart,
} from "@curatelabs/xyg-node/graphforge";

export function visualizeGraphForge(nodesIpc, edgesIpc, pagerankIpc, generation) {
  const composition = composeGraphForge({
    base: { tables: [nodesIpc, edgesIpc], generation },
    layers: [{
      result: pagerankIpc,
      intent: "graph",
      resultId: "pagerank",
      generation,
    }],
  });
  const chart = graphforgeChart(composition, { width: 900, height: 600 });
  return { composition, chart };
}
```

`chart.toHtml()` produces HTML without importing Python. Tables use
`graphforgeTableHtml(composition)`. Follow the
[Node package guide](https://github.com/CurateLabs/xyg/tree/main/packages/xy-node)
for native-library staging and package setup; npm publication is pending.

### VS Code integration recipe

The Node host provides APIs for integrating XYG into an extension. Adoption
by a specific GraphForge editor is a separate integration task. To use these
APIs, compose natively in the extension host and pass
`graphforgeWebviewPayload(composition, options)`'s `spec` and binary `buffer`
to the webview. The webview paints with the local client via
`renderStandalone(el, spec, buffer)`. Relay `{trace, index}` from `xy:click`
to the extension host and resolve it with
`graphforgePick(figure, composition, {trace, index})`. The native graph mark
uses Rust LOD, so this path supports larger views than the direct WASM Scene.
With this integration, the extension owns UI, state, and message routing;
XYG owns visualization.

## Browser WASM

When result bytes already live in a browser, run XYG in a Worker using local
client, Worker, and WASM assets from one build:

```javascript
import {
  createXygWasmWorker,
  renderWasmGraphForge,
} from "@curatelabs/xyg";

const worker = createXygWasmWorker({ workerUrl, wasm });
const { view, composition } = await renderWasmGraphForge({
  el,
  worker,
  width: 900,
  height: 600,
  input: {
    base: { tables: [nodesIpc, edgesIpc], generation },
    layers: [{ result: pagerankIpc, intent: "graph", resultId: "pagerank", generation }],
  },
});
view.root.addEventListener("xy:graphforge-select", (event) => {
  console.log(event.detail); // UUID and contributing result rows
});
```

`workerUrl` is an explicit module-Worker URL; `wasm` is the matching WASM URL
or bytes. `el` is your chart container. The current GraphForge renderer
admits **at most 1,024 composed nodes**, plus the Scene primitive budget.
Larger graphs use native Python or Node graph LOD. A larger composition
without rendered Scene output is a separate operation and does not establish
that larger browser graphs can be painted.

Use `composeWasmGraphForge(worker, input)` and
`graphforgeTableElement(composition)` for a table. Cells render as text.
Browser WASM has no Python or Node server requirement, but GraphForge Core's
queries and algorithms still execute in a native host.

For same-origin hosted assets, the WASM path needs
`script-src 'self' 'wasm-unsafe-eval'`, `worker-src 'self'`, and
`connect-src 'self'`, alongside the painter's style/image rules. VS Code
webviews require the documented local-resource and Blob-Worker setup rather
than a CDN. See the
[webview contract](https://github.com/CurateLabs/xyg/blob/main/spec/design/graphforge-compositions.md#64-vs-code-webviews)
and [Serving and CSP](/docs/xy/guides/serving-csp-and-offline-use/).

## Identity, selection, and failures

`composition.identify("node", index)` or `composition.identify("edge", index)`
returns the canonical UUID and contributing layer/result rows. Derived edges
have no invented persisted-edge UUID. `composition.select(uuids)` maps
canonical identities to composition indices; recomposition with `select`
sets their visual selection state.

Generation mismatches, unsupported schemas or intents, and missing identities
fail with coded errors. Python and Node raise `GraphForgeCompositionError`
with `code`, `layer`, and `field`; browser WASM reports `XygWasmError` with the
same Rust composition diagnostics. Keep base and analytical layers from the
same generation instead of joining stale results by row position.

The parity fixtures compare identical request and document bytes across
Python, Node, and WASM. Rendered GraphForge Scenes also have a portable Rust
layout path with byte-identical cross-host evidence. See
[Rust engine and host parity](/docs/xy/core-concepts/rust-engine-and-host-parity/)
and the [composition specification](https://github.com/CurateLabs/xyg/blob/main/spec/design/graphforge-compositions.md)
for the exact contracts and bounds.
