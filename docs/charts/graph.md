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

## Axes

Graph charts frame their nodes so nothing is cut off at the edge: node
markers, halos, group frames, and the labels shown at the starting zoom all
fit inside the chart, in the browser and in SVG/PNG export alike. Passing
your own axes turns this off and uses the plain automatic domain (or the
domain you set).

Graph charts hide their axes by default. Pass your own `xyg.x_axis(...)` /
`xyg.y_axis(...)` (Node: the `xAxis` / `yAxis` options) to use a log scale, a
fixed domain, or visible axes; the one you pass replaces that hidden default.

## Static export

`graph_chart(...).to_svg()` / `.to_png()` (and Node `graphChart(...).toSvg()` /
`.toPng()`) export what the interactive chart draws at its home view, framed
by the same automatic domain: edges, self-loops, arrowheads, curves, and nodes,
plus semantic styling (halos, class bodies, dashes, state fading), compound
group frames and collapsed groups, per-node sizes and color scales, the labels
visible at that zoom, and the semantic legend. Python and Node write identical
bytes for identical input.

A few limits apply to static output:

- At most 10,000 nodes and 10,000 drawn edge segments (a straight edge draws
  1 segment, a curved edge 8, a self-loop 3). Larger graphs fail with
  `XYG_SCENE_UNSUPPORTED_PUBLIC_LOD` in both hosts; use the interactive HTML
  export for them.
- At most 128 labels (8 KiB of label text); past that the export keeps the
  labels that appear first when zooming in. The default `label_budget` (64)
  stays under this limit.
- The legend goes where `xyg.legend(loc=...)` (Node: the `legend` option)
  puts it, upper right by default. Placements without a fixed position, such
  as `"best"`, fail with `XYG_STATIC_UNSUPPORTED_GRAPH`, and a legend taller
  than the plot (the interactive legend scrolls instead) fails with
  `XYG_STATIC_UNSUPPORTED_LEGEND_FOOTPRINT`; make the chart taller or pass
  `semantic_legend=False`.
- Labels and legend text use your `--chart-text` color, as in the browser.
- Annotations (`xyg.text`, rules, arrows) on a graph chart are not exported
  yet; export fails with `XYG_STATIC_UNSUPPORTED_GRAPH` rather than dropping
  them. Use the interactive HTML export for annotated graphs.

Pass chart settings such as `style=` next to a graph child:
`xyg.graph_chart(xyg.graph(...), style={"background": "#0f172a",
"--chart-text": "#e2e8f0"})`.

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
    edge_visual_state_flags="edge_flags",  # the same states for edges
    edge_metric="weight",       # numbers -> edge width
    theme="dark",
)
```

Node takes the same options in camelCase (`nodeClass`, `edgeMetric`, …).
Semantic fields replace `color`, `size`, `symbol`, `edge_color`, and
`edge_width`. When a very large graph is aggregated, per-node and per-edge
styling is left off and `spec.graph.style_contract` says so.

Epistemic codes draw a soft halo around nodes and edges and give edges a dash
pattern; edge classes add a colored body under the status stroke; and only
edges with a nonzero status get an arrowhead, whether or not the graph is
directed. SVG/PNG export draws every one of these layers (see Static export).

## Color scales

Pass an array or column as `color` / `edge_color` and pick a scale:

```python
xyg.graph(
    nodes, edges,
    color="risk",                    # ordered levels
    color_scale={"type": "ordinal", "order": ["low", "medium", "high"]},
    edge_color="delta",              # signed change
    edge_color_scale={"type": "diverging", "midpoint": 0, "colormap": "rdbu"},
)
```

`linear` takes a `colormap` and optional `domain`; `diverging` centers the
colors on `midpoint`; `ordinal` spreads a colormap over your `order`; and
`categorical` takes a `palette`. Semantic graphs show a "Graph semantics"
legend listing each class, epistemic, and status value in use; pass
`semantic_legend=False` to hide it. Node takes `colorScale`,
`edgeColorScale`, and `semanticLegend`.

## Groups (compound nodes)

Give nodes a `parent_uuid` and each group gets a frame around its members.
Collapse groups to hide their members; edges to hidden members reroute to the
group, and picking a collapsed group lists its members:

```python
xyg.graph_chart(nodes=node_table, edges=edge_table, collapsed=["<group uuid>"])
```

Positions stay put when a group opens or closes (the whole graph is laid out
once). Collapsing needs every node drawn, so very large graphs that the chart
aggregates refuse `collapsed`. SVG/PNG export draws the group frames and
collapsed groups.

## Labels

Nodes are labeled from `node_label` (default: the `label` column, then
`name`, then the node id), and edges from `edge_label` when you pass it.
`label_priority` / `edge_label_priority` decide which labels win, and
`label_budget` (default 64) caps how many can ever show. Labels are cut to 32
characters and never overlap: a crowded graph shows the most important labels
first, and zooming in reveals more.

```python
xyg.graph_chart(
    nodes=node_table,
    edges=edge_table,
    node_label="name",
    label_priority="degree",
    edge_label="relationship_type",
    label_budget=200,
)
```

Node uses `nodeLabel`, `labelPriority`, `edgeLabel`, and `labelBudget`. SVG/PNG
export draws the labels visible at the exported zoom.

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
