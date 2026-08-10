"""Graph ingest helpers — id maps and thin adapters (graph-mark.md).

Layout math lives in the Rust ABI (`_native.graph_layout`); this module only
coerces xy-native inputs and optional NetworkX / GraphForge tables into dense
u64 indices + columns.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from . import _native

__all__ = [
    "DEFAULT_LAYOUT",
    "GraphData",
    "from_networkx",
    "normalize_graph_inputs",
]

DEFAULT_LAYOUT = "force"


class GraphData:
    """Dense graph ready for layout + segments/scatter emit."""

    __slots__ = (
        "directed",
        "ids",
        "node_attrs",
        "sources",
        "targets",
        "x",
        "y",
    )

    def __init__(
        self,
        ids: list[Any],
        sources: np.ndarray,
        targets: np.ndarray,
        *,
        x: np.ndarray | None = None,
        y: np.ndarray | None = None,
        node_attrs: Mapping[str, np.ndarray] | None = None,
        directed: bool = True,
    ) -> None:
        self.ids = list(ids)
        self.sources = np.ascontiguousarray(sources, dtype=np.uint64)
        self.targets = np.ascontiguousarray(targets, dtype=np.uint64)
        self.x = None if x is None else np.ascontiguousarray(x, dtype=np.float64)
        self.y = None if y is None else np.ascontiguousarray(y, dtype=np.float64)
        self.node_attrs = dict(node_attrs or {})
        self.directed = bool(directed)

    @property
    def n_nodes(self) -> int:
        return len(self.ids)

    @property
    def n_edges(self) -> int:
        return int(len(self.sources))


def _as_1d(values: Any, name: str) -> np.ndarray:
    arr = np.asarray(values)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D")
    return arr


def normalize_graph_inputs(
    nodes: Any,
    edges: Any,
    *,
    x: Any = None,
    y: Any = None,
    directed: bool = True,
) -> GraphData:
    """Accept ids + edge pairs/columns (xy-native formats)."""
    if isinstance(nodes, Mapping) and "id" in nodes:
        ids = list(_as_1d(nodes["id"], "nodes.id"))
        attrs = {
            key: np.asarray(val) for key, val in nodes.items() if key != "id" and not callable(val)
        }
    elif hasattr(nodes, "columns") and "id" in getattr(nodes, "columns", []):
        ids = list(nodes["id"])
        attrs = {col: np.asarray(nodes[col]) for col in nodes.columns if col != "id"}
    else:
        ids = list(_as_1d(nodes, "nodes"))
        attrs = {}

    id_to_index = {node_id: i for i, node_id in enumerate(ids)}
    if len(id_to_index) != len(ids):
        raise ValueError("graph node ids must be unique")

    if isinstance(edges, Mapping) and "source" in edges and "target" in edges:
        src_ids = _as_1d(edges["source"], "edges.source")
        tgt_ids = _as_1d(edges["target"], "edges.target")
    elif hasattr(edges, "columns"):
        cols = list(edges.columns)
        if "source" not in cols or "target" not in cols:
            raise ValueError("edge table requires source and target columns")
        src_ids = np.asarray(edges["source"])
        tgt_ids = np.asarray(edges["target"])
    else:
        pairs = np.asarray(edges, dtype=object)
        if pairs.ndim == 2 and pairs.shape[1] == 2:
            src_ids = pairs[:, 0]
            tgt_ids = pairs[:, 1]
        elif isinstance(edges, Sequence) and edges and isinstance(edges[0], (tuple, list)):
            src_ids = np.asarray([e[0] for e in edges], dtype=object)
            tgt_ids = np.asarray([e[1] for e in edges], dtype=object)
        else:
            raise ValueError(
                "edges must be (source, target) pairs, or a mapping/table with "
                "source and target columns"
            )

    if len(src_ids) != len(tgt_ids):
        raise ValueError("edge source/target lengths differ")

    sources = np.empty(len(src_ids), dtype=np.uint64)
    targets = np.empty(len(tgt_ids), dtype=np.uint64)
    for i, (s, t) in enumerate(zip(src_ids, tgt_ids, strict=True)):
        if s not in id_to_index or t not in id_to_index:
            raise ValueError(f"edge endpoints {(s, t)!r} are not in nodes")
        sources[i] = id_to_index[s]
        targets[i] = id_to_index[t]

    xs = None if x is None else np.ascontiguousarray(_as_1d(x, "x"), dtype=np.float64)
    ys = None if y is None else np.ascontiguousarray(_as_1d(y, "y"), dtype=np.float64)
    if (xs is None) ^ (ys is None):
        raise ValueError("x and y must both be provided or both omitted")
    if xs is not None and len(xs) != len(ids):
        raise ValueError("x/y must match node count")

    return GraphData(
        ids,
        sources,
        targets,
        x=xs,
        y=ys,
        node_attrs=attrs,
        directed=directed,
    )


def from_networkx(graph: Any, *, pos: Mapping[Any, Sequence[float]] | None = None) -> GraphData:
    """Thin NetworkX adapter — optional convenience, not required."""
    try:
        nodes = list(graph.nodes())
    except Exception as exc:  # noqa: BLE001 — surface adapter errors clearly
        raise TypeError("from_networkx expects a NetworkX-like graph") from exc
    edges = list(graph.edges())
    x = y = None
    if pos is not None:
        x = np.asarray([float(pos[n][0]) for n in nodes], dtype=np.float64)
        y = np.asarray([float(pos[n][1]) for n in nodes], dtype=np.float64)
    directed = bool(getattr(graph, "is_directed", lambda: False)())
    return normalize_graph_inputs(nodes, edges, x=x, y=y, directed=directed)


def from_graphforge_tables(
    nodes: Any,
    edges: Any,
    *,
    directed: bool = True,
) -> GraphData:
    """Thin GraphForge/Arrow-table helper: expects id/source/target columns."""
    return normalize_graph_inputs(nodes, edges, directed=directed)


def run_layout(
    data: GraphData,
    layout: str = DEFAULT_LAYOUT,
    *,
    seed: int = 0,
    iterations: int = 300,
    node_budget: int = 200_000,
    edge_budget: int = 500_000,
    viewport: tuple[float, float, float, float] | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Layout via Rust ABI, then emit a perceptually bounded render graph.

    Layout runs on the **full** source graph (Barnes–Hut repulsion when
    ``n > 500``). LOD reduction happens once via ``graph_build_render`` —
    hosts must not double-sample edges for draw.
    """
    layout_name = str(layout or DEFAULT_LAYOUT).strip().lower()
    n = data.n_nodes
    e = data.n_edges
    sources = data.sources
    targets = data.targets
    alpha = None
    layout_id = _native.graph_layout_id(layout_name)
    use_progressive = iterations > 0 and layout_id in _native._GRAPH_PROGRESSIVE_FORCE
    if use_progressive:
        handle = _native.graph_force_create(
            n,
            sources,
            targets,
            x=data.x,
            y=data.y,
            seed=seed,
            algorithm=layout_id,
        )
        try:
            x, y, alpha = _native.graph_force_tick(handle, n, max(1, int(iterations)))
        finally:
            _native.graph_force_destroy(handle)
    else:
        if layout_name == "preset" and (data.x is None or data.y is None):
            raise ValueError("layout='preset' requires x and y")
        x, y = _native.graph_layout(
            layout_name,
            n,
            sources,
            targets,
            x=data.x,
            y=data.y,
            seed=seed,
        )

    rx, ry, member_of, edge_s, edge_t, tier, edges_kept = _native.graph_build_render(
        x,
        y,
        sources,
        targets,
        node_budget=int(node_budget),
        edge_budget=int(edge_budget),
        viewport=viewport,
    )
    meta: dict[str, Any] = {
        "layout": layout_name,
        "seed": int(seed),
        "lod_tier": int(tier),
        "edges_kept": int(edges_kept),
        "nodes_kept": int(len(rx)),
        "n_nodes": int(len(rx)),
        "n_edges": int(len(edge_s)),
        "source_n_nodes": int(n),
        "source_n_edges": int(e),
        "member_of": member_of,
        "render_sources": edge_s,
        "render_targets": edge_t,
        "node_budget": int(node_budget),
        "edge_budget": int(edge_budget),
    }
    if use_progressive:
        meta["iterations"] = int(iterations)
        meta["alpha"] = float(alpha) if alpha is not None else None
    return rx, ry, meta
