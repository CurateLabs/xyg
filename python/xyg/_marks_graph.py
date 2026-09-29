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
    node_class: Union[str, ArrayLike, None] = None,
    node_epistemic: Union[str, ArrayLike, None] = None,
    node_status: Union[str, ArrayLike, None] = None,
    node_metric: Union[str, ArrayLike, None] = None,
    edge_class: Union[str, ArrayLike, None] = None,
    edge_epistemic: Union[str, ArrayLike, None] = None,
    edge_status: Union[str, ArrayLike, None] = None,
    edge_metric: Union[str, ArrayLike, None] = None,
    theme: str = "light",
) -> "Figure":
    """Add a node–link graph: Rust layout, then segments (edges) + scatter (nodes).

    See ``spec/design/graph-mark.md``. Analysis stays in GraphForge; this mark
    only positions and draws. ``layout=`` selects the algorithm (default
    ``\"force\"``).

    ``nodes``/``edges`` may be xyg-native sequences, a ready ``GraphData`` from
    ``from_graphforge_tables`` (pass ``GraphData`` as ``nodes`` and omit
    ``edges``), or canonical GraphForge tables with ``node_uuid`` /
    ``edge_uuid`` columns.

    ``node_class`` / ``node_epistemic`` / ``node_status`` (integer codes 0-7)
    and ``node_metric`` (numbers), plus the ``edge_*`` equivalents, may be
    arrays or column names. When any is given for a side, Rust resolves the
    versioned GraphForge semantic style contract (v1; ``theme`` ``"light"`` or
    ``"dark"``; node states from ``visual_state_flags``) and the mark paints the
    resolved node fill, stroke, stroke width, size, shape, and opacity and the
    edge color, width, and opacity. Semantic fields replace ``color`` / ``size``
    / ``symbol`` (nodes) and ``edge_color`` / ``edge_width`` (edges). They are
    indexed by source row, so they paint where render identity is exact and are
    omitted (and recorded in ``style_contract``) under Aggregate LOD.
    """
    from . import _graph, _native, channels
    from ._channels_lut import normalize_to_unit
    from ._marks_style import SYMBOL_CODES

    data = _graph.resolve_graph_data(nodes, edges, x=x, y=y, directed=directed, mapping=mapping)
    color = _graph.resolve_encoding_values(data, color, where="node")
    size = _graph.resolve_encoding_values(data, size, where="node")
    pinned = _graph.resolve_encoding_values(data, pinned, where="node")
    edge_color = _graph.resolve_encoding_values(data, edge_color, where="edge")
    node_label = _graph.resolve_encoding_values(data, node_label, where="node")
    label_priority = _graph.resolve_encoding_values(data, label_priority, where="node")
    visual_state_flags = _graph.resolve_encoding_values(data, visual_state_flags, where="node")
    if visual_state_flags is None:
        visual_state_flags = data.node_attrs.get(
            "visual_state_flags",
            data.node_attrs.get("state_flags", np.zeros(data.n_nodes, dtype=np.uint32)),
        )
    node_fields = _semantic_fields(
        data, "node", node_class, node_epistemic, node_status, node_metric
    )
    edge_fields = _semantic_fields(
        data, "edge", edge_class, edge_epistemic, edge_status, edge_metric
    )
    if node_fields is not None and (color is not None or size is not None):
        raise ValueError("graph node semantic fields replace color= and size=")
    if edge_fields is not None and edge_color is not None:
        raise ValueError("graph edge semantic fields replace edge_color=")
    _reject_semantic_style_overrides(style, node_fields is not None, edge_fields is not None)
    if theme not in ("light", "dark"):
        raise ValueError(f"graph theme must be 'light' or 'dark', got {theme!r}")
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
    # Rust-owned multigraph routing: parallel offsets, self-loops, arrowheads,
    # and optional Bezier-class curved shafts (#33).
    curve = str(edge_curve or "straight").strip().lower()
    if curve not in ("straight", "curve"):
        raise ValueError(f"graph edge_curve must be 'straight' or 'curve', got {edge_curve!r}")
    # Semantic styling (#34): Rust resolves the v1 contract per source row;
    # rows paint only where render identity is exact.
    style_contract: dict[str, Any] | None = None
    node_style: dict[str, Any] | None = None
    edge_style: dict[str, Any] | None = None
    if node_fields is not None or edge_fields is not None:
        style_contract = {"version": 1, "theme": theme, "nodes": None, "edges": None}
        style_contract["pending_layers"] = list(SEMANTIC_PENDING_LAYERS)
    if node_fields is not None and style_contract is not None:
        if len(px) != data.n_nodes:
            style_contract["nodes"] = "omitted:aggregate"
        else:
            flags = _node_flags(visual_state_flags, data.n_nodes)
            resolved = _native.graph_semantic_styles(*node_fields, flags, theme=theme)
            node_style = _node_paint(resolved)
            style_contract["nodes"] = "resolved"
            style_contract["node_metric_domain"] = list(resolved["metric_domain"])
    if edge_fields is not None and style_contract is not None:
        member_offsets = np.asarray(meta["render_edge_member_offsets"], dtype=np.intp)
        if not bool(np.all(np.diff(member_offsets) == 1)):
            style_contract["edges"] = "omitted:aggregate"
        else:
            members = np.asarray(meta["render_edge_members"], dtype=np.intp)
            rows = members[member_offsets[:-1]]
            # Resolve every source edge so the metric domain is the source
            # domain (EdgeSample must not rescale widths), then gather rows.
            no_flags = np.zeros(len(edge_fields[0]), dtype=np.uint32)
            resolved = _native.graph_semantic_styles(*edge_fields, no_flags, edge=True, theme=theme)
            edge_style = {
                "color": resolved["stroke_rgba"][rows].astype(np.float64) / 255.0,
                "width": resolved["width"][rows].astype(np.float64),
                "opacity": resolved["opacity"][rows].astype(np.float64),
            }
            edge_color, edge_width = edge_style["color"], edge_style["width"]
            style_contract["edges"] = "resolved"
            style_contract["edge_metric_domain"] = list(resolved["metric_domain"])
    if node_style is not None:
        color, size, symbol = node_style["color"], node_style["size"], node_style["symbol"]
    size_range = node_style["size_range"] if node_style is not None else (2.0, 18.0)
    # Border-aware ends (#33): Rust trims each edge to its nodes' outlines and
    # places arrowheads in screen space, so it needs each node's on-screen
    # radius (the same size mapping the node scatter ships) and outline.
    node_size = channels.resolve_size(
        size if size is not None else 8.0, len(px), range_px=size_range
    )
    if node_size.mode == "continuous" and node_size.values is not None and node_size.domain:
        lo, hi = node_size.range_px
        unit = normalize_to_unit(node_size.values, node_size.domain)
        node_diameter = lo + (hi - lo) * np.nan_to_num(unit, nan=0.0)
    else:
        node_diameter = np.full(len(px), float(node_size.constant))
    node_symbol = (
        np.full(len(px), SYMBOL_CODES.get(symbol, 0), dtype=np.uint8)
        if isinstance(symbol, str)
        else np.asarray([SYMBOL_CODES.get(str(v), 0) for v in np.ravel(symbol)], dtype=np.uint8)
    )
    x0, y0, x1, y1, render_edge_index, edge_ends = _native.graph_edge_route_ends(
        px,
        py,
        sources,
        targets,
        directed=bool(directed),
        separation=0.08,
        loop_radius=0.35,
        curved=curve == "curve",
        node_radius_px=node_diameter * 0.5,
        node_symbol=node_symbol,
    )
    edge_name = None if name is None else f"{name}:edges"
    node_name = None if name is None else f"{name}:nodes"

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
        opacity=opacity
        if edge_style is None
        else _expand_edge_values(edge_style["opacity"], "edge opacity"),
        style=style,
    )
    self.traces[-1].style_channels["edge_ends"] = channels.StyleChannel(
        values=np.ascontiguousarray(edge_ends, dtype=np.float64), components=7
    )
    self.scatter(
        px,
        py,
        name=node_name,
        color=color,
        size=size if size is not None else 8.0,
        size_range=size_range,
        opacity=opacity if node_style is None else node_style["opacity"],
        symbol=symbol,
        stroke=None if node_style is None else node_style["stroke"],
        stroke_width=0.0 if node_style is None else node_style["stroke_width"],
        # Density surfaces drop per-node paint; resolved semantic rows must
        # paint exactly as style_contract reports.
        density=None if node_style is None else False,
        style=style,
    )
    # Edge identity follows Rust's render-edge membership, not a count match
    # (#33): a render edge with one member carries that source edge's row; an
    # Aggregate edge carries its member count, never one invented source edge.
    # Routing expands loops/arrows/curves into several segments per render
    # edge, so rows are expanded by render_edge_index.
    edge_identity = _graph.GraphEdgeIdentity(
        render_edge_index=np.asarray(render_edge_index, dtype=np.uint64),
        offsets=np.asarray(meta["render_edge_member_offsets"], dtype=np.uint64),
        members=np.asarray(meta["render_edge_members"], dtype=np.uint64),
        source_edge_ids=[str(edge_id) for edge_id in data.edge_ids] if data.edge_ids else None,
    )
    single = edge_identity.single_member()
    node_tooltips, edge_tooltips = _graph.projection_tooltip_rows(data)
    if node_tooltips is not None and len(px) == data.n_nodes:
        self.traces[-1].tooltip_rows = node_tooltips
    if edge_tooltips is not None:
        counts = np.diff(edge_identity.offsets)
        render_rows = [
            edge_tooltips[int(edge_identity.members[int(edge_identity.offsets[r])])]
            if counts[r] == 1
            else {"edge_count": int(counts[r])}
            for r in range(len(sources))
        ]
        self.traces[-2].tooltip_rows = [render_rows[int(i)] for i in render_edge_index.tolist()]
    # CSR matches the *render* node index space (scatter), not raw source V.
    offsets, neighbors = _native.graph_build_csr(len(px), sources, targets, directed=bool(directed))
    # §28 recorded layout/LOD decision for hosts/clients.
    member_of = np.asarray(meta["member_of"], dtype=np.uint64)
    graph_meta = {
        **{
            k: v
            for k, v in meta.items()
            if k
            not in (
                "member_of",
                "render_sources",
                "render_targets",
                "render_edge_member_offsets",
                "render_edge_members",
            )
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
        **({} if style_contract is None else {"style_contract": style_contract}),
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
        flags = _node_flags(visual_state_flags, data.n_nodes)
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
        if single is not None:
            # Render-edge-indexed identity when every render edge is exactly
            # one source edge (Direct, EdgeSample, uncollapsed Aggregate).
            graph_meta["edge_ids"] = [source_edge_ids[int(m)] for m in single]
    if data.node_provenance_rows is not None:
        graph_meta["node_provenance_rows"] = [int(v) for v in data.node_provenance_rows.tolist()]
    if data.edge_provenance_rows is not None:
        graph_meta["edge_provenance_rows"] = [int(v) for v in data.edge_provenance_rows.tolist()]
    if edge_tooltips is not None and single is None:
        # Source-indexed semantic table when Aggregate LOD collapsed multi-edges/loops.
        graph_meta["edge_tooltip_rows"] = edge_tooltips
    if node_tooltips is not None and len(px) != data.n_nodes:
        graph_meta["node_tooltip_rows"] = node_tooltips
    existing = getattr(self, "_graph_meta", None)
    if existing is None:
        self._graph_meta = [graph_meta]
    else:
        existing.append(graph_meta)
    # Register the identity plane only once the graph fully validated.
    self._graph_edge_identity[graph_meta["edge_trace"]] = edge_identity
    return self


# Paint layers of the v1 semantic contract that the composed graph mark does
# not draw yet (#34); recorded so hosts never mistake them for painted.
SEMANTIC_PENDING_LAYERS = (
    "node_halo",
    "edge_halo",
    "edge_class_body",
    "edge_dash",
    "edge_arrow_policy",
)
_SHAPE_SYMBOLS = ("circle", "square", "diamond", "triangle", "cross", "hexagon")


def _semantic_fields(
    data: Any, where: str, classes, epistemic, statuses, metric
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    """Source-row semantic columns for one side, or ``None`` when unset."""
    from . import _graph

    raw = (classes, epistemic, statuses, metric)
    if all(value is None for value in raw):
        return None
    n = data.n_nodes if where == "node" else len(data.sources)
    out = []
    for index, value in enumerate(raw):
        value = _graph.resolve_encoding_values(data, value, where=where)
        label = ("class", "epistemic", "status", "metric")[index]
        if isinstance(value, str):
            raise ValueError(f"graph {where}_{label} names unknown {where} column {value!r}")
        if value is None:
            arr = np.zeros(n, dtype=np.float64 if index == 3 else np.uint8)
        elif index == 3:
            arr = np.asarray(value, dtype=np.float64)
        else:
            arr = np.asarray(value)
            if arr.dtype.kind not in "iu" or arr.dtype == np.bool_:
                raise ValueError(f"graph {where}_{label} must be integer codes 0..7")
            # Validate every source row even when Aggregate LOD omits paint.
            if arr.size and (int(arr.min()) < 0 or int(arr.max()) > 7):
                raise ValueError(f"graph {where}_{label} codes must be in 0..7")
        if arr.ndim == 0:
            arr = np.full(n, arr.item(), dtype=arr.dtype)
        if arr.ndim != 1 or len(arr) != n:
            raise ValueError(f"graph {where}_{label} must match {where} count {n}")
        out.append(arr)
    return out[0], out[1], out[2], out[3]


# Compiled CSS keys that would override each side's resolved semantic paint.
_NODE_SEMANTIC_CSS = (
    "color",
    "opacity",
    "stroke",
    "stroke_width",
    "symbol",
    "fill_opacity",
    "stroke_opacity",
)
_EDGE_SEMANTIC_CSS = ("color", "width", "opacity")


def _reject_semantic_style_overrides(style: Any, nodes: bool, edges: bool) -> None:
    if not style:
        return
    for enabled, kind, keys in (
        (nodes, "scatter", _NODE_SEMANTIC_CSS),
        (edges, "segments", _EDGE_SEMANTIC_CSS),
    ):
        if not enabled:
            continue
        try:
            css = styles.compile_mark_style(kind, style)
        except ValueError:
            continue  # the mark itself reports unsupported properties
        conflicts = sorted(key for key in keys if key in css)
        if conflicts:
            side = "node" if kind == "scatter" else "edge"
            raise ValueError(
                f"graph {side} semantic fields own paint; style must not set {conflicts}"
            )


def _node_flags(visual_state_flags: Any, n: int) -> np.ndarray:
    flags = np.asarray(visual_state_flags)
    if flags.ndim == 0:
        flags = np.full(n, flags.item())
    if flags.ndim != 1 or len(flags) != n:
        raise ValueError("graph visual_state_flags must match node count")
    return flags


def _node_paint(resolved: dict[str, Any]) -> dict[str, Any]:
    """Map resolved node rows onto the scatter mark's existing channels."""
    sizes = resolved["size"].astype(np.float64)
    lo = float(sizes.min()) if len(sizes) else 8.0
    hi = float(sizes.max()) if len(sizes) else 8.0
    # Identity size mapping: an array spanning [lo, hi] onto range [lo, hi]
    # paints exact pixels; a constant array collapses to one scalar.
    return {
        "color": resolved["fill_rgba"].astype(np.float64) / 255.0,
        "stroke": resolved["stroke_rgba"].astype(np.float64) / 255.0,
        "stroke_width": resolved["width"].astype(np.float64),
        "opacity": resolved["opacity"].astype(np.float64),
        "size": sizes if hi > lo else lo,
        "size_range": (lo, hi) if hi > lo else (2.0, 18.0),
        "symbol": [_SHAPE_SYMBOLS[int(code)] for code in resolved["shape"]],
    }
