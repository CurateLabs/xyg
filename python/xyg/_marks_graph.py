"""Graph mark — GraphForge ingest, Rust layout, segments + scatter emit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np

from . import styles
from ._typing import ArrayLike

if TYPE_CHECKING:
    from ._figure import Figure


def graph(
    self: "Figure",
    nodes: Any,
    edges: Any = None,
    *,
    x: Any = None,
    y: Any = None,
    layout: str = "force",
    directed: bool = True,
    seed: int = 0,
    iterations: int = 300,
    cose: dict[str, Any] | None = None,
    pinned: Union[str, ArrayLike, None] = None,
    color: Union[str, ArrayLike, None] = None,
    size: Union[float, ArrayLike, None] = None,
    edge_color: Union[str, ArrayLike, None] = None,
    edge_width: Any = 1.2,
    symbol: Any = "circle",
    edge_curve: str = "straight",
    name: Optional[str] = None,
    opacity: Any = 1.0,
    style: styles.StyleMapping | None = None,
    mapping: dict[str, str] | None = None,
    node_label: Union[str, ArrayLike, None] = None,
    label_priority: Union[str, ArrayLike, None] = None,
    label_budget: int = 64,
    label_priority_floor: float | None = None,
    visual_state_flags: Union[str, ArrayLike, None] = None,
) -> "Figure":
    """Add a node–link graph: Rust layout, then segments (edges) + scatter (nodes).

    See ``spec/design/graph-mark.md``. Analysis stays in GraphForge; this mark
    only positions and draws. ``layout=`` selects the algorithm (default
    ``\"force\"``).

    ``nodes``/``edges`` may be xyg-native sequences, a ready ``GraphData`` from
    ``from_graphforge_tables`` (pass ``GraphData`` as ``nodes`` and omit
    ``edges``), or canonical GraphForge tables with ``node_uuid`` /
    ``edge_uuid`` columns.
    """
    from . import _graph, _native

    data = _graph.resolve_graph_data(nodes, edges, x=x, y=y, directed=directed, mapping=mapping)
    color = _graph.resolve_encoding_values(data, color, where="node")
    size = _graph.resolve_encoding_values(data, size, where="node")
    pinned = _graph.resolve_encoding_values(data, pinned, where="node")
    edge_color = _graph.resolve_encoding_values(data, edge_color, where="edge")
    node_label = _graph.resolve_encoding_values(data, node_label, where="node")
    label_priority = _graph.resolve_encoding_values(data, label_priority, where="node")
    visual_state_flags = _graph.resolve_encoding_values(data, visual_state_flags, where="node")
    px, py, meta = _graph.run_layout(
        data,
        layout=layout,
        seed=seed,
        iterations=iterations,
        cose=cose,
        pinned=pinned,
    )
    # Emit ONLY the Rust render-graph buffers (no second edge sample).
    tier = meta["lod_tier"]
    sources = np.asarray(meta["render_sources"], dtype=np.uint64)
    targets = np.asarray(meta["render_targets"], dtype=np.uint64)
    # Rust-owned multigraph routing: parallel offsets, self-loops, arrowheads (#33).
    arrow_size = 0.12 if directed else 0.0
    x0, y0, x1, y1, render_edge_index = _native.graph_edge_route_segments(
        px,
        py,
        sources,
        targets,
        directed=bool(directed),
        separation=0.08,
        loop_radius=0.35,
        arrow_size=arrow_size,
    )
    edge_name = None if name is None else f"{name}:edges"
    node_name = None if name is None else f"{name}:nodes"
    curve = str(edge_curve or "straight").strip().lower()

    def _expand_edge_values(values, label: str):
        if values is None or np.isscalar(values) or isinstance(values, str):
            return values
        arr = np.asarray(values)
        if arr.ndim == 0:
            return values
        if len(arr) == len(sources):
            return arr[render_edge_index.astype(np.intp)]
        if len(arr) == len(x0):
            return arr
        raise ValueError(
            f"graph {label} length {len(arr)} must match render edges "
            f"{len(sources)} or routed segments {len(x0)}"
        )

    edge_color_paint = _expand_edge_values(edge_color, "edge_color")
    edge_width_paint = _expand_edge_values(edge_width, "edge_width")
    self.segments(
        x0,
        y0,
        x1,
        y1,
        name=edge_name,
        color=edge_color_paint,
        width=edge_width_paint,
        opacity=opacity,
        style=style,
    )
    self.scatter(
        px,
        py,
        name=node_name,
        color=color,
        size=size if size is not None else 8.0,
        opacity=opacity,
        symbol=symbol,
        style=style,
    )
    # Attach GraphForge semantic rows when render LOD kept a 1:1 mapping.
    # Direct tier preserves parallels/self-loops; routing may expand loops/arrows
    # into multiple segments — expand tooltip rows by render_edge_index (#33).
    node_tooltips, edge_tooltips = _graph.projection_tooltip_rows(data)
    if node_tooltips is not None and len(px) == data.n_nodes:
        self.traces[-1].tooltip_rows = node_tooltips
    if edge_tooltips is not None and len(sources) == data.n_edges:
        self.traces[-2].tooltip_rows = [edge_tooltips[int(i)] for i in render_edge_index.tolist()]
    # CSR matches the *render* node index space (scatter), not raw source V.
    offsets, neighbors = _native.graph_build_csr(len(px), sources, targets, directed=bool(directed))
    # §28 recorded layout/LOD decision for hosts/clients.
    member_of = np.asarray(meta["member_of"], dtype=np.uint64)
    graph_meta = {
        **{
            k: v
            for k, v in meta.items()
            if k not in ("member_of", "render_sources", "render_targets")
        },
        "directed": bool(directed),
        "ids": [str(i) for i in data.ids],
        "sources": sources.astype(np.uint64).tolist(),
        "targets": targets.astype(np.uint64).tolist(),
        "render_edge_index": [int(i) for i in render_edge_index.tolist()],
        "member_of": member_of.astype(np.uint64).tolist(),
        "source_n_nodes": int(meta["source_n_nodes"]),
        "source_n_edges": int(meta["source_n_edges"]),
        "csr_offsets": offsets.astype(np.uint64).tolist(),
        "csr_neighbors": neighbors.astype(np.uint64).tolist(),
        "node_symbol": symbol if isinstance(symbol, str) else "circle",
        "edge_curve": curve,
        "tier_name": ("direct", "edge_sample", "aggregate")[min(int(tier), 2)],
        "node_trace": len(self.traces) - 1,
        "edge_trace": len(self.traces) - 2,
    }
    # Rust owns acceptance, precedence, and compound membership. Hosts only
    # serialize the accepted paint contract; Aggregate LOD has a different
    # identity plane and therefore intentionally omits source-node metadata.
    if len(px) == data.n_nodes:
        if node_label is None:
            node_label = data.node_attrs.get(
                "label", data.node_attrs.get("name", [None] * data.n_nodes)
            )
        raw_labels = (
            [node_label] * data.n_nodes if isinstance(node_label, str) else list(node_label)
        )
        fallback_names = data.node_attrs.get("name")
        labels: list[str | None] = []
        for index, value in enumerate(raw_labels):
            if value is None and fallback_names is not None:
                value = fallback_names[index]
            if value is None:
                identity = data.ids[index]
                if isinstance(identity, str):
                    value = identity
                elif (
                    isinstance(identity, (int, np.integer))
                    and not isinstance(identity, (bool, np.bool_))
                    and -(2**53 - 1) <= int(identity) <= 2**53 - 1
                ):
                    value = str(int(identity))
                else:
                    value = None
            if value is not None and not isinstance(value, str):
                raise TypeError("graph labels must be strings or null")
            labels.append(value)
        if len(labels) != data.n_nodes:
            raise ValueError("graph node_label must match node count")
        if label_priority is None:
            label_priority = data.node_attrs.get("label_priority", np.zeros(data.n_nodes))
        priorities = np.asarray(label_priority, dtype=np.float64)
        if priorities.ndim == 0:
            priorities = np.full(data.n_nodes, priorities.item(), dtype=np.float64)
        priorities = np.ascontiguousarray(priorities)
        if priorities.ndim != 1 or len(priorities) != data.n_nodes:
            raise ValueError("graph label_priority must match node count")
        priorities = priorities.copy()
        priorities[[label is None for label in labels]] = np.nan
        if isinstance(label_budget, bool) or not isinstance(label_budget, (int, np.integer)):
            raise TypeError("graph label_budget must be an exact integer")
        if int(label_budget) < 0 or int(label_budget) > 4096:
            raise ValueError("graph label_budget must be between 0 and 4096")
        accepted = _native.graph_label_accept(
            priorities, label_budget, min_priority=label_priority_floor
        )
        if any(
            label is not None and len(label.encode("utf-8")) > 4096
            for label, keep in zip(labels, accepted, strict=True)
            if keep
        ):
            raise ValueError("accepted graph labels are limited to 4096 UTF-8 bytes each")
        if visual_state_flags is None:
            visual_state_flags = data.node_attrs.get(
                "visual_state_flags",
                data.node_attrs.get("state_flags", np.zeros(data.n_nodes, dtype=np.uint32)),
            )
        flags = np.asarray(visual_state_flags)
        if flags.ndim == 0:
            flags = np.full(data.n_nodes, flags.item())
        if flags.ndim != 1 or len(flags) != data.n_nodes:
            raise ValueError("graph visual_state_flags must match node count")
        states = _native.graph_visual_states(flags)
        graph_meta.update(
            {
                "node_labels": [
                    label if bool(accepted[i]) else None for i, label in enumerate(labels)
                ],
                "label_accepted": accepted.astype(bool).tolist(),
                "label_budget": int(label_budget),
                "visual_states": states.astype(np.uint8).tolist(),
            }
        )
        if data.parent_indices is not None:
            validity = (
                np.ones(data.n_nodes, dtype=np.uint8)
                if data.parent_validity is None
                else np.asarray(data.parent_validity, dtype=np.uint8)
            )
            parent_of, compounds, bounds = _native.graph_compound_bounds(
                px, py, data.parent_indices, validity
            )
            sentinel = np.iinfo(np.uint64).max
            graph_meta["parent_of"] = [
                None if value == sentinel else int(value) for value in parent_of
            ]
            graph_meta["compound_nodes"] = compounds.astype(bool).tolist()
            graph_meta["compound_bounds"] = [
                None if not bool(compounds[i]) else [float(v) for v in bounds[i]]
                for i in range(data.n_nodes)
            ]
    if data.edge_ids:
        # Source-indexed identity; Aggregate LOD may collapse multi-edges/self-loops.
        source_edge_ids = [str(edge_id) for edge_id in data.edge_ids]
        graph_meta["source_edge_ids"] = source_edge_ids
        if len(sources) == data.n_edges:
            graph_meta["edge_ids"] = source_edge_ids
    if data.node_provenance_rows is not None:
        graph_meta["node_provenance_rows"] = [int(v) for v in data.node_provenance_rows.tolist()]
    if data.edge_provenance_rows is not None:
        graph_meta["edge_provenance_rows"] = [int(v) for v in data.edge_provenance_rows.tolist()]
    if edge_tooltips is not None and len(sources) != data.n_edges:
        # Source-indexed semantic table when Aggregate LOD collapsed multi-edges/loops.
        graph_meta["edge_tooltip_rows"] = edge_tooltips
    if node_tooltips is not None and len(px) != data.n_nodes:
        graph_meta["node_tooltip_rows"] = node_tooltips
    existing = getattr(self, "_graph_meta", None)
    if existing is None:
        self._graph_meta = [graph_meta]
    else:
        existing.append(graph_meta)
    return self
