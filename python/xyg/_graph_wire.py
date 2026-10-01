"""Wire form of graph meta (graph-mark.md §7, "Wire graph meta").

Dependency-free so payload serialization can use it without loading the graph
ingest stack or the native core.
"""

from __future__ import annotations

from typing import Any

__all__ = ["HOST_ONLY_GRAPH_META", "wire_graph_meta"]

# Host-side identity planes kept on ``figure._graph_meta`` for picks, edge
# identity, and selection. The browser never reads them, so the wire spec omits
# them (graph-mark.md §7, "Wire graph meta"); Node `HOST_ONLY_GRAPH_META` is the
# same list.
HOST_ONLY_GRAPH_META = (
    "ids",
    "sources",
    "targets",
    "member_of",
    "render_edge_index",
    "source_edge_ids",
    "edge_ids",
    "node_provenance_rows",
    "edge_provenance_rows",
    "node_tooltip_rows",
    "edge_tooltip_rows",
)


def wire_graph_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """The ``spec.graph`` entry for one graph: host meta minus host-only identity planes."""
    return {key: value for key, value in meta.items() if key not in HOST_ONLY_GRAPH_META}
