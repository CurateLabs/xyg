---
title: Graph Charts and GraphForge Ingest
description: Build node-link graphs in Python and Node with xyg. Ingest GraphForge Arrow projections with stable UUID identity, tooltips, and host-parity marks.
components:
  - xyg.graph_chart
---

# Graph charts and GraphForge ingest

Build node–link graphs with `xyg.graph` / `xyg.graph_chart`, or the Node
`figure().graph(...)` / `composeGraph(...)` helpers. Layout, LOD, and encode
decisions stay in Rust; hosts only coerce inputs.

## xyg-native inputs

```python
import xyg

chart = xyg.graph_chart(
    xyg.graph(["a", "b", "c"], [("a", "b"), ("b", "c")], layout="force", seed=1),
    width=640,
    height=400,
)
```

## Canonical GraphForge tables

Pass tables that already use GraphForge field names. No rename loop is
required. Python accepts `pyarrow.Table` (optional) or plain column mappings;
Node accepts Arrow JS tables or plain `{ column: values }` objects.

```python
import xyg

nodes = {
    "node_uuid": ["…", "…"],
    "labels": ["Airport", "City"],
    "rank": [1.0, 2.0],
    "provenance_row": [10, 11],
}
edges = {
    "edge_uuid": ["…"],
    "src_uuid": ["…"],
    "dst_uuid": ["…"],
    "relationship_type": ["ROUTE"],
    "provenance_row": [100],
}

# Directly into the mark — Rust validates identity, then the mark attaches
# tooltip_rows from labels / relationship_type / provenance.
fig = xyg.Figure().graph(nodes, edges, layout="grid", size="rank")
```

Or validate once and reuse `GraphData`:

```python
data = xyg.from_graphforge_tables(nodes, edges)
fig = xyg.Figure().graph(data, layout="circle")
```

Node mirror:

```javascript
import { composeGraph, figure, fromGraphForgeTables } from "@curatelabs/xyg-node";

const composed = composeGraph(nodes, edges, { layout: "grid", size: "rank" });
// or
const data = fromGraphForgeTables(nodes, edges);
const fig = figure({ width: 640, height: 400 }).graph(data, null, { layout: "circle" });
```

Invalid UUIDs, duplicate node/edge ids, and missing endpoints raise stable
`GraphProjectionError` codes (`GF_GRAPH_*`) before paint.

IPC fixtures used in CI live under `tests/fixtures/graphforge/` (regenerate with
`scripts/gen_graphforge_ipc_fixtures.py`).

## Static export

`graph_chart(...).to_svg()` / `.to_png()` (and Node `graphChart(...).toSvg()` /
`.toPng()`) export the same edges, self-loops, arrowheads, curves, and nodes the
interactive chart draws, framed by the same automatic domain. Static export
currently admits at most 10,000 nodes and 10,000 drawn edge segments (a
straight edge draws 1 segment, a curved edge 8, a self-loop 3), and nodes with
a per-node `size` array are not yet admitted statically. Larger graphs
fail with a stable reason: `XYG_SCENE_UNSUPPORTED_PUBLIC_LOD` in Python (nodes or
segments) and in Node for nodes, while Node reports edge-segment overflow as
`XYG_SCENE_UNSUPPORTED_PUBLIC_SEGMENTS`. Use the interactive HTML export for
larger graphs.

## Semantic styling

Name GraphForge semantic columns and Rust resolves a color-blind-safe
palette, sizes, widths, shapes, and state fading for you:

```python
xyg.graph_chart(
    nodes=node_table,
    edges=edge_table,
    node_class="kind",          # codes 0-7 -> fill color and shape
    node_epistemic="belief",    # codes 0-7
    node_status="health",       # codes 0-7 -> outline color
    node_metric="score",        # numbers -> node size
    visual_state_flags="flags", # selected / hovered / filtered / disabled …
    edge_class="relation",
    edge_metric="weight",       # numbers -> edge width
    theme="dark",
)
```

Node takes the same options in camelCase (`nodeClass`, `edgeMetric`, …).
Semantic fields replace `color`, `size`, `symbol`, `edge_color`, and
`edge_width`. When a very large graph is aggregated, per-node and per-edge
styling is left off and `spec.graph.style_contract` says so. Halos, dashed
edges, and per-status arrow policy are not drawn on this chart yet (listed in
`style_contract.pending_layers`), and SVG/PNG export of a semantically styled
graph is not supported yet; use HTML export.

## Arrowheads and node borders

Edges start and end on node outlines, and directed edges (including
self-loops) end in a filled arrowhead whose tip touches the target node, at
every zoom level and in SVG/PNG exports alike. Circle, square, and diamond
nodes use their exact outline; other symbols use their circumscribed circle.
Edges between nodes that overlap on screen are hidden rather than drawn
backwards.

## Edge identity on hover and pick

Hovering or clicking an edge reports the exact GraphForge `edge_uuid` whenever
the drawn edge is a single source edge, including routed self-loops, arrow
wings, curved tessellation, and parallel or reciprocal siblings. When a very
large graph is aggregated, one drawn edge stands for several source edges; its
tooltip shows `edge_count`, and a pick reply lists the members in ascending
order (`source_edges`, `edge_ids`, capped at 256 with `members_truncated`).
It never names one arbitrary edge on the aggregate's behalf.

```javascript
const fig = figure().graph(nodes, edges, { layout: "grid" });
const { edge_trace } = fig._graphMeta[0];
fig.graphEdgePick(edge_trace, 0);
// { render_edge: 0, edge_count: 1, source_edges: [0], members_truncated: false,
//   edge_ids: ["…"] }
```

Python returns the same fields in the widget/Reflex `pick` and `click`
replies.
