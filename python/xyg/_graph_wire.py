"""Wire form of graph meta (graph-mark.md §7, "Wire graph meta").

Dependency-free so payload serialization can use it without loading the graph
ingest stack or the native core.
"""

from __future__ import annotations

from typing import Any

import numpy as np

__all__ = [
    "HOST_ONLY_GRAPH_META",
    "WIRE_COLUMN_GRAPH_META",
    "decode_wire_graph_meta",
    "wire_graph_meta",
]

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


# Per-node/per-edge integer planes the browser reads (CSR neighborhood,
# accessibility counts) ship as typed payload columns, `{"column": index}`,
# never as JSON numbers; Node `WIRE_COLUMN_GRAPH_META` is the same table.
WIRE_COLUMN_GRAPH_META = {
    "csr_offsets": "u32",
    "csr_neighbors": "u32",
    "label_accepted": "u8",
    "visual_states": "u8",
    "compound_nodes": "u8",
}


def _wire_column(values: Any, dtype: str, pw: Any) -> dict[str, int] | None:
    if not isinstance(values, (list, tuple, np.ndarray)) or any(v is None for v in values):
        return None
    array = np.asarray(values)
    limit = np.iinfo(np.uint32 if dtype == "u32" else np.uint8).max
    if array.ndim != 1 or array.dtype.kind not in "biu":
        return None
    if array.size and (int(array.min()) < 0 or int(array.max()) > limit):
        return None
    return {"column": pw.ship_u32(array) if dtype == "u32" else pw.ship_u8(array)}


def wire_graph_meta(meta: dict[str, Any], pw: Any = None) -> dict[str, Any]:
    """The ``spec.graph`` entry for one graph: host meta minus host-only identity
    planes, with browser-read integer planes as typed columns when ``pw`` is given."""
    out: dict[str, Any] = {}
    for key, value in meta.items():
        if key in HOST_ONLY_GRAPH_META:
            continue
        dtype = WIRE_COLUMN_GRAPH_META.get(key)
        column = _wire_column(value, dtype, pw) if dtype is not None and pw is not None else None
        out[key] = column if column is not None else value
    return out


def decode_wire_graph_meta(
    spec: dict[str, Any], payload: Any, entry: dict[str, Any]
) -> dict[str, Any]:
    """A ``spec.graph`` entry with its typed-column planes read back as lists
    (``label_accepted`` and ``compound_nodes`` as bools), for tests and hosts."""
    out = dict(entry)
    for key, dtype in WIRE_COLUMN_GRAPH_META.items():
        ref = entry.get(key)
        if not isinstance(ref, dict) or "column" not in ref:
            continue
        meta = spec["columns"][ref["column"]]
        width = 4 if dtype == "u32" else 1
        source = payload[meta["buf"]] if "buf" in meta else payload
        raw = memoryview(source).cast("B")
        start = int(meta["byte_offset"])
        values = np.frombuffer(
            raw[start : start + int(meta["len"]) * width], dtype="<u4" if dtype == "u32" else "u1"
        )
        out[key] = (
            [bool(v) for v in values]
            if key in ("label_accepted", "compound_nodes")
            else [int(v) for v in values]
        )
    return out
