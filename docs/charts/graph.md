---
title: Graph Charts and GraphForge Ingest
description: Build node-link graphs in Python and Node with xy. Ingest GraphForge Arrow projections with stable UUID identity, tooltips, and host-parity marks.
components:
  - xy.graph_chart
---

# Graph charts and GraphForge ingest

Build node–link graphs with `xy.graph` / `xy.graph_chart`, or the Node
`figure().graph(...)` / `composeGraph(...)` helpers. Layout, LOD, and encode
decisions stay in Rust; hosts only coerce inputs.

## xy-native inputs

```python
import xy

chart = xy.graph_chart(
    xy.graph(["a", "b", "c"], [("a", "b"), ("b", "c")], layout="force", seed=1),
    width=640,
    height=400,
)
```

## Canonical GraphForge tables

Pass tables that already use GraphForge field names. No rename loop is
required. Python accepts `pyarrow.Table` (optional) or plain column mappings;
Node accepts Arrow JS tables or plain `{ column: values }` objects.

```python
import xy

nodes = {
    "node_uuid": ["…", "…"],
    "labels": ["Airport", "City"],
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
fig = xy.Figure().graph(nodes, edges, layout="grid", size="rank")
```

Or validate once and reuse `GraphData`:

```python
data = xy.from_graphforge_tables(nodes, edges)
fig = xy.Figure().graph(data, layout="circle")
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
