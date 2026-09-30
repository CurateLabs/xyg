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
    edge_label: Union[str, ArrayLike, None] = None,
    edge_label_priority: Union[str, ArrayLike, None] = None,
    node_class: Union[str, ArrayLike, None] = None,
    node_epistemic: Union[str, ArrayLike, None] = None,
    node_status: Union[str, ArrayLike, None] = None,
    node_metric: Union[str, ArrayLike, None] = None,
    edge_class: Union[str, ArrayLike, None] = None,
    edge_epistemic: Union[str, ArrayLike, None] = None,
    edge_status: Union[str, ArrayLike, None] = None,
    edge_metric: Union[str, ArrayLike, None] = None,
    theme: str = "light",
    color_scale: dict[str, Any] | None = None,
    edge_color_scale: dict[str, Any] | None = None,
    semantic_legend: bool = True,
    collapsed: Union[str, ArrayLike, None] = None,
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

    ``color_scale`` / ``edge_color_scale`` choose how an array ``color`` /
    ``edge_color`` maps to paint: ``{"type": "linear", "colormap", "domain"}``,
    ``{"type": "diverging", "colormap" (default "rdbu"), "midpoint" (0)}``
    (Rust centers the domain on the midpoint), ``{"type": "ordinal", "order",
    "colormap"}`` (Rust samples one color per ordered level, legend in that
    order), or ``{"type": "categorical", "palette"}``. With semantic fields,
    ``semantic_legend`` (default on) shows the Rust semantic legend.

    Compound graphs (parent/child nodes) paint a Rust frame around each
    visible group. ``collapsed`` (group ids, a node mask, or a node column)
    collapses groups: the full graph is laid out once (Direct LOD), then Rust
    hides descendants, routes crossing edges to the collapsed group, drops
    newly internal edges, and propagates hidden interaction state; picking a
    collapsed group reports its hidden members.
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
    edge_label = _graph.resolve_encoding_values(data, edge_label, where="edge")
    edge_label_priority = _graph.resolve_encoding_values(data, edge_label_priority, where="edge")
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
    if node_fields is not None and color_scale is not None:
        raise ValueError("graph node semantic fields replace color_scale")
    if edge_fields is not None and edge_color_scale is not None:
        raise ValueError("graph edge semantic fields replace edge_color_scale")
    if theme not in ("light", "dark"):
        raise ValueError(f"graph theme must be 'light' or 'dark', got {theme!r}")
    full = data
    compound: dict[str, Any] | None = None
    if collapsed is not None:
        compound = _collapse_compounds(
            data,
            collapsed,
            visual_state_flags,
            layout=layout,
            seed=seed,
            iterations=iterations,
            cose=cose,
            pinned=pinned,
        )
        keep_n, keep_e = compound["visible"], compound["edge_keep"]
        n0, e0 = full.n_nodes, len(full.sources)
        data = compound["data"]
        visual_state_flags = compound["flags"][keep_n]
        color, size, node_label, label_priority = (
            _subset_rows(v, keep_n, n0) for v in (color, size, node_label, label_priority)
        )
        edge_color, edge_width, edge_label, edge_label_priority = (
            _subset_rows(v, keep_e, e0)
            for v in (edge_color, edge_width, edge_label, edge_label_priority)
        )
        if node_fields is not None:
            c, ep, st, mt = node_fields
            node_fields = (c[keep_n], ep[keep_n], st[keep_n], mt[keep_n])
        if edge_fields is not None:
            c, ep, st, mt = edge_fields
            edge_fields = (c[keep_e], ep[keep_e], st[keep_e], mt[keep_e])
        layout, pinned, cose = "preset", None, None
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
        # Every v1 layer (halo, class body, dash, arrow policy) now paints on
        # the composed mark; the key stays so hosts can gate on it.
        style_contract = {"version": 1, "theme": theme, "nodes": None, "edges": None}
        style_contract["pending_layers"] = []
    if node_fields is not None and style_contract is not None:
        if len(px) != data.n_nodes:
            style_contract["nodes"] = "omitted:aggregate"
        else:
            flags = _node_flags(visual_state_flags, data.n_nodes)
            resolved = _native.graph_semantic_styles(*node_fields, flags, theme=theme)
            node_style = _node_paint(resolved)
            node_style["layers"] = _native.graph_semantic_paint_layers(
                *node_fields, flags, theme=theme
            )
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
            layers = _native.graph_semantic_paint_layers(
                *edge_fields, no_flags, edge=True, theme=theme
            )
            edge_style = {
                "color": resolved["stroke_rgba"][rows].astype(np.float64) / 255.0,
                "width": resolved["width"][rows].astype(np.float64),
                "opacity": resolved["opacity"][rows].astype(np.float64),
                "layers": {key: value[rows] for key, value in layers.items() if key != "version"},
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
    frames = _compound_frames(
        full, compound, px, py, len(px) == data.n_nodes, node_style, node_diameter * 0.5, theme
    )
    node_scale = _color_scale(color, color_scale, "color_scale")
    edge_scale = _color_scale(edge_color_paint, edge_color_scale, "edge_color_scale")
    edge_width_paint = _expand_edge_values(edge_width, "edge_width")
    self.segments(
        x0,
        y0,
        x1,
        y1,
        name=edge_name,
        color=edge_color_paint,
        colormap=edge_scale.get("colormap", channels.DEFAULT_COLORMAP),
        domain=edge_scale.get("domain"),
        width=edge_width_paint,
        opacity=opacity
        if edge_style is None
        else _expand_edge_values(edge_style["opacity"], "edge opacity"),
        style=style,
    )
    if "channel" in edge_scale:
        self.traces[-1].color_ch = edge_scale["channel"]
    if edge_style is not None:
        # Rust's arrow policy replaces the directed default: the head bit
        # (0x40) follows each segment's source-edge `head` layer.
        segment_rows = render_edge_index.astype(np.intp)
        edge_layers = edge_style["layers"]
        edge_ends = np.array(edge_ends, dtype=np.float64)
        head = edge_layers["head"][segment_rows].astype(np.int64) * 0x40
        edge_ends[:, 6] = (edge_ends[:, 6].astype(np.int64) & ~0x40) | head
        _add_layer_channels(
            self.traces[-1],
            {key: value[segment_rows] for key, value in edge_layers.items() if key != "head"},
            edge=True,
        )
    self.traces[-1].style_channels["edge_ends"] = channels.StyleChannel(
        values=np.ascontiguousarray(edge_ends, dtype=np.float64), components=7
    )
    self.scatter(
        px,
        py,
        name=node_name,
        color=color,
        colormap=node_scale.get("colormap", channels.DEFAULT_COLORMAP),
        color_domain=node_scale.get("domain"),
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
    if "channel" in node_scale:
        self.traces[-1].color_ch = node_scale["channel"]
    if node_style is not None:
        _add_layer_channels(self.traces[-1], node_style["layers"], edge=False)
    if frames is not None and len(frames["node"]):
        _add_compound_frame_channel(self.traces[-1], frames, compound, px, py)
    if semantic_legend and (node_fields is not None or edge_fields is not None):
        _apply_semantic_legend(self, node_fields, edge_fields, theme)
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
        flags = _node_flags(visual_state_flags, data.n_nodes)
        states = _native.graph_visual_states(flags)
        # Edge labels anchor at the middle routed piece of a single-member
        # render edge (exact source identity), like the semantic Scene.
        edge_texts, edge_priorities, edge_anchor = _edge_label_rows(
            data, edge_label, edge_label_priority, single, render_edge_index
        )
        mid = edge_anchor.astype(np.intp)
        plan = _native.graph_label_plan(
            np.r_[np.zeros(data.n_nodes, np.uint8), np.ones(len(mid), np.uint8)],
            np.r_[px, (x0[mid] + x1[mid]) * 0.5],
            np.r_[py, (y0[mid] + y1[mid]) * 0.5],
            np.r_[node_diameter * 0.5, np.zeros(len(mid))],
            [_label_chars(t) for t in (*labels, *edge_texts)],
            np.r_[states.astype(np.uint8), np.zeros(len(mid), np.uint8)],
            np.r_[priorities, edge_priorities],
            int(label_budget),
            min_priority=label_priority_floor,
        )
        keep = plan["keep"]
        texts = [_truncated(t, int(k)) for t, k in zip((*labels, *edge_texts), keep, strict=True)]
        if any(t is not None and len(t.encode("utf-8")) > 4096 for t in texts):
            raise ValueError("accepted graph labels are limited to 4096 UTF-8 bytes each")
        accepted = keep[: data.n_nodes] > 0
        # Rust label plan rides the node/edge traces as per-item placement
        # (threshold px per data unit, -1 never; baseline offset px; planned
        # width and font px the painter fits the text into).
        rows = np.c_[
            np.where(np.isfinite(plan["threshold"]) & (keep > 0), plan["threshold"], -1.0),
            plan["offset_x"],
            plan["offset_y"],
            plan["width"],
            plan["font_px"],
        ]
        self.traces[-1].style_channels["label_plan"] = channels.StyleChannel(
            values=np.ascontiguousarray(rows[: data.n_nodes]), components=LABEL_PLAN_COMPONENTS
        )
        edge_rows = np.zeros((len(x0), LABEL_PLAN_COMPONENTS))
        edge_rows[:, 0] = -1.0
        painted = [i for i in range(len(mid)) if keep[data.n_nodes + i] > 0]
        for i in painted:
            edge_rows[mid[i]] = rows[data.n_nodes + i]
        if painted:
            self.traces[-2].style_channels["label_plan"] = channels.StyleChannel(
                values=np.ascontiguousarray(edge_rows), components=LABEL_PLAN_COMPONENTS
            )
            graph_meta["edge_label_segments"] = [int(mid[i]) for i in painted]
            graph_meta["edge_label_text"] = [texts[data.n_nodes + i] for i in painted]
        graph_meta.update(
            {
                "node_labels": [
                    texts[i] if bool(accepted[i]) else None for i in range(data.n_nodes)
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
    if frames is not None:
        graph_meta["compound_frames"] = [str(full.ids[int(i)]) for i in frames["node"]]
    elif full.parent_indices is not None:
        # Frames need exact source identity; Aggregate LOD omits them (§28).
        graph_meta["compound_frames"] = "omitted:aggregate"
    if compound is not None:
        graph_meta["compound_collapsed"] = compound["collapsed_ids"]
        self._graph_node_identity[graph_meta["node_trace"]] = compound["members"]
    return self


# label_plan channel row: threshold, offset x, offset y, width, font px (#34).
LABEL_PLAN_COMPONENTS = 5


_SCALE_KEYS = {
    "linear": {"type", "colormap", "domain"},
    "diverging": {"type", "colormap", "midpoint"},
    "ordinal": {"type", "colormap", "order"},
    "categorical": {"type", "palette"},
}


def _color_scale(values: Any, scale: dict[str, Any] | None, label: str) -> dict[str, Any]:
    """Resolve a graph color scale into scatter/segments arguments (#34).

    Linear and diverging scales return a colormap and domain (Rust centers a
    diverging domain on its midpoint). Ordinal and categorical scales return a
    ready categorical channel whose category order and palette come from the
    scale (ordinal colors are sampled by Rust).
    """
    from . import _native, channels

    if scale is None:
        return {}
    if not isinstance(scale, dict) or scale.get("type") not in _SCALE_KEYS:
        raise ValueError(f"graph {label} must be a dict with type {sorted(_SCALE_KEYS)}")
    kind = scale["type"]
    unknown = set(scale) - _SCALE_KEYS[kind]
    if unknown:
        raise ValueError(f"graph {label} {kind!r} does not accept {sorted(unknown)}")
    if values is None or isinstance(values, str) or np.ndim(values) != 1:
        raise ValueError(f"graph {label} needs a per-item color array or column")
    if kind in ("linear", "diverging"):
        numeric = np.asarray(values, dtype=np.float64)
        colormap = scale.get("colormap", "rdbu" if kind == "diverging" else "viridis")
        if kind == "diverging":
            domain = _native.graph_diverging_domain(numeric, float(scale.get("midpoint", 0.0)))
        else:
            domain = scale.get("domain")
        return {"colormap": colormap, "domain": None if domain is None else tuple(domain)}
    items = list(values)
    if kind == "ordinal":
        order = list(scale.get("order") or [])
        if not order or len(set(map(str, order))) != len(order):
            raise ValueError(f"graph {label} ordinal needs a nonempty, unique 'order'")
        index = {str(level): i for i, level in enumerate(order)}
        missing = sorted({str(v) for v in items if str(v) not in index})
        if missing:
            raise ValueError(f"graph {label} values {missing[:4]} are not in the ordinal order")
        codes = np.asarray([index[str(v)] for v in items], dtype=np.uint8)
        palette = _native.graph_ordinal_colors(scale.get("colormap", "viridis"), len(order))
        return {
            "channel": channels.ColorChannel(
                mode="categorical",
                codes=codes,
                categories=[str(level) for level in order],
                palette=palette,
                counts=np.bincount(codes, minlength=len(order)).astype(np.uint64),
            )
        }
    palette = scale.get("palette")
    resolved = channels.resolve_color(np.asarray(items), len(items), default_constant="#888888")
    if resolved.mode != "categorical":
        raise ValueError(f"graph {label} categorical needs category labels")
    if palette is not None:
        colors = [str(c) for c in palette]
        if not colors:
            raise ValueError(f"graph {label} categorical 'palette' must not be empty")
        resolved.palette = colors
    return {"channel": resolved}


def _apply_semantic_legend(fig: Any, node_fields: Any, edge_fields: Any, theme: str) -> None:
    """Show the Rust semantic legend: one row per class/epistemic/status value
    present on nodes or edges, ordered like the semantic Scene (#34)."""
    from . import _native

    planes = [f for f in (node_fields, edge_fields) if f is not None]
    classes, epistemic, statuses = (np.concatenate([f[k] for f in planes]) for k in range(3))
    legend = _native.graph_semantic_legend(classes, epistemic, statuses, theme=theme)
    items = []
    for field, value, rgba, shape in zip(
        legend["field"], legend["value"], legend["rgba"], legend["shape"], strict=True
    ):
        items.append(
            {
                "kind": "scatter",
                "name": _native.graph_semantic_legend_text(int(field), int(value)),
                "style": {
                    "color": "#{:02x}{:02x}{:02x}".format(*(int(c) for c in rgba[:3])),
                    "symbol": _SHAPE_SYMBOLS[int(shape) % len(_SHAPE_SYMBOLS)],
                },
            }
        )
    if items and not fig.legend_options.get("items"):
        fig.legend_options = {
            **fig.legend_options,
            "title": _native.graph_semantic_legend_text(3),
            "items": items,
        }
        fig.show_legend = True


#: Hidden members listed per collapsed-group pick before truncation; mirrors
#: GRAPH_EDGE_PICK_MEMBER_CAP.
COMPOUND_PICK_MEMBER_CAP = 256


def _subset_rows(value: Any, keep: np.ndarray, n: int) -> Any:
    """Keep the visible rows of a per-row argument; scalars/strings pass."""
    if value is None or isinstance(value, str) or np.ndim(value) == 0:
        return value
    if len(value) != n:
        return value  # the mark's own length validation reports it
    idx = np.flatnonzero(keep)
    return value[idx] if isinstance(value, np.ndarray) else [value[int(i)] for i in idx]


def _collapsed_mask(data: Any, collapsed: Any) -> np.ndarray:
    n = data.n_nodes
    if isinstance(collapsed, str):
        if collapsed not in data.node_attrs:
            raise ValueError(f"graph collapsed names unknown node column {collapsed!r}")
        collapsed = data.node_attrs[collapsed]
    values = list(collapsed)
    if len(values) == n and all(isinstance(v, (bool, np.bool_)) for v in values):
        return np.asarray(values, dtype=np.uint8)
    wanted = {str(v) for v in values}
    ids = [str(i) for i in data.ids]
    unknown = sorted(wanted - set(ids))
    if unknown:
        raise ValueError(f"graph collapsed ids {unknown[:4]} are not nodes")
    return np.asarray([i in wanted for i in ids], dtype=np.uint8)


def _collapse_compounds(
    data: Any, collapsed: Any, flags: Any, **layout_opts: Any
) -> dict[str, Any]:
    """Lay the full graph out once, then let Rust collapse it (#34)."""
    from . import _graph, _native

    if data.parent_indices is None:
        raise ValueError("graph collapsed= needs compound parents (GraphForge parent_uuid)")
    n = data.n_nodes
    mask = _collapsed_mask(data, collapsed)
    px, py, meta = _graph.run_layout(data, **layout_opts)
    if int(meta["lod_tier"]) != 0 or len(px) != n:
        raise ValueError(
            "graph compound disclosure needs Direct LOD: collapse keeps exact node "
            "identity, which Aggregate LOD does not have"
        )
    validity = (
        np.ones(n, dtype=np.uint8)
        if data.parent_validity is None
        else np.asarray(data.parent_validity, dtype=np.uint8)
    )
    parents = np.asarray(data.parent_indices, dtype=np.uint64)
    out = _native.graph_compound_collapse(
        parents, validity, mask, _node_flags(flags, n), data.sources, data.targets
    )
    visible, keep = out["visible"], out["edge_keep"]
    new_index = np.full(n, -1, dtype=np.int64)
    new_index[visible] = np.arange(int(visible.sum()))
    rows = np.flatnonzero(visible)
    erows = np.flatnonzero(keep)

    def pick(values: Any, idx: np.ndarray) -> Any:
        if values is None:
            return None
        return values[idx] if isinstance(values, np.ndarray) else [values[int(i)] for i in idx]

    sub_parents = parents[rows].copy()
    sub_validity = validity[rows].copy()
    for j, parent in enumerate(sub_parents):
        if sub_validity[j]:
            mapped = new_index[int(parent)]
            sub_parents[j], sub_validity[j] = (mapped, 1) if mapped >= 0 else (0, 0)
    sub = _graph.GraphData(
        [data.ids[int(i)] for i in rows],
        new_index[out["edge_source"][erows].astype(np.int64)],
        new_index[out["edge_target"][erows].astype(np.int64)],
        x=px[rows],
        y=py[rows],
        node_attrs={k: pick(np.asarray(v, dtype=object), rows) for k, v in data.node_attrs.items()},
        edge_ids=None if data.edge_ids is None else [data.edge_ids[int(i)] for i in erows],
        edge_attrs={
            k: pick(np.asarray(v, dtype=object), erows) for k, v in data.edge_attrs.items()
        },
        node_uuid_bytes=pick(data.node_uuid_bytes, rows),
        edge_uuid_bytes=pick(data.edge_uuid_bytes, erows),
        node_provenance_rows=pick(data.node_provenance_rows, rows),
        edge_provenance_rows=pick(data.edge_provenance_rows, erows),
        parent_indices=sub_parents,
        parent_validity=sub_validity,
        directed=data.directed,
    )
    members: dict[int, dict[str, Any]] = {}
    representative = out["representative"]
    for group in np.flatnonzero(mask):
        hidden = [
            str(data.ids[int(i)]) for i in np.flatnonzero((representative == group) & ~visible)
        ]
        if visible[group]:
            members[int(new_index[group])] = {
                "compound_collapsed": True,
                "compound_member_count": len(hidden),
                "compound_members": hidden[:COMPOUND_PICK_MEMBER_CAP],
                "compound_members_truncated": len(hidden) > COMPOUND_PICK_MEMBER_CAP,
            }
    return {
        "data": sub,
        "visible": visible,
        "edge_keep": keep,
        "flags": out["flags"],
        "mask": mask,
        "positions": (px, py),
        "collapsed_ids": [str(data.ids[int(i)]) for i in np.flatnonzero(mask)],
        "members": members,
    }


def _compound_frames(
    full: Any,
    compound: dict[str, Any] | None,
    px: np.ndarray,
    py: np.ndarray,
    direct: bool,
    node_style: dict[str, Any] | None,
    radius_px: np.ndarray,
    theme: str,
) -> dict[str, np.ndarray] | None:
    """Rust compound frames over the full graph's positions, or None."""
    from . import _native

    if full.parent_indices is None or (compound is None and not direct):
        return None
    n = full.n_nodes
    visible = np.ones(n, dtype=bool) if compound is None else compound["visible"]
    fx, fy = (px, py) if compound is None else compound["positions"]
    mask = np.zeros(n, dtype=np.uint8) if compound is None else compound["mask"]
    stroke = np.zeros((n, 4), dtype=np.uint8)
    opacity = np.ones(n, dtype=np.float32)
    radius = np.zeros(n, dtype=np.float64)
    radius[visible] = np.asarray(radius_px, dtype=np.float64)
    if node_style is not None:
        stroke[visible] = np.rint(np.asarray(node_style["stroke"]) * 255.0).astype(np.uint8)
        opacity[visible] = np.asarray(node_style["opacity"], dtype=np.float32)
    validity = (
        np.ones(n, dtype=np.uint8)
        if full.parent_validity is None
        else np.asarray(full.parent_validity, dtype=np.uint8)
    )
    return _native.graph_compound_frames(
        fx, fy, radius, full.parent_indices, validity, mask, stroke, opacity, theme=theme
    )


# compound_frame channel row: bounds deltas from the node (xmin, xmax, ymin,
# ymax; data units), RGBA 0-255, stroke width px, screen pad px (#34).
COMPOUND_FRAME_COMPONENTS = 10


def _add_compound_frame_channel(
    trace: Any,
    frames: dict[str, np.ndarray],
    compound: dict[str, Any] | None,
    px: np.ndarray,
    py: np.ndarray,
) -> None:
    """Ship Rust compound frames on the node trace: rows of nodes without a
    frame carry width 0. Bounds ride as deltas from the node so f32 transport
    stays exact (§4)."""
    from . import channels

    rows = np.zeros((len(px), COMPOUND_FRAME_COMPONENTS))
    if compound is None:
        index = np.asarray(frames["node"], dtype=np.intp)
    else:
        new_index = np.cumsum(compound["visible"]) - 1
        index = new_index[np.asarray(frames["node"], dtype=np.intp)]
    b = np.asarray(frames["bounds"], dtype=np.float64)
    rows[index, 0:2] = b[:, 0:2] - px[index, None]
    rows[index, 2:4] = b[:, 2:4] - py[index, None]
    rows[index, 4:8] = np.asarray(frames["rgba"], dtype=np.float64)
    rows[index, 8] = frames["width"]
    rows[index, 9] = frames["pad"]
    trace.style_channels["compound_frame"] = channels.StyleChannel(
        values=np.ascontiguousarray(rows), components=COMPOUND_FRAME_COMPONENTS
    )


def _label_chars(text: str | None) -> int:
    return 0 if text is None else len(text)


def _truncated(text: str | None, keep: int) -> str | None:
    """Apply Rust's ``keep`` count: ``keep`` characters plus an ellipsis."""
    if text is None or keep <= 0:
        return None
    text = str(text)
    return text if keep >= len(text) else text[:keep] + "\u2026"


def _edge_label_rows(
    data: Any, edge_label: Any, edge_label_priority: Any, single: Any, render_edge_index: Any
) -> tuple[list[str | None], np.ndarray, np.ndarray]:
    """Per render edge: label text, priority, and anchor segment (middle piece)."""
    if edge_label is None or single is None:
        return [], np.zeros(0), np.zeros(0, dtype=np.intp)
    n_edges = len(data.sources)
    raw = [edge_label] * n_edges if isinstance(edge_label, str) else list(edge_label)
    if len(raw) != n_edges:
        raise ValueError("graph edge_label must match edge count")
    if any(value is not None and not isinstance(value, str) for value in raw):
        raise TypeError("graph edge labels must be strings or null")
    priority = np.zeros(n_edges) if edge_label_priority is None else edge_label_priority
    priority = np.asarray(priority, dtype=np.float64)
    if priority.ndim == 0:
        priority = np.full(n_edges, priority.item())
    if priority.ndim != 1 or len(priority) != n_edges:
        raise ValueError("graph edge_label_priority must match edge count")
    rows = np.asarray(single, dtype=np.intp)
    texts = [raw[int(row)] for row in rows]
    priorities = priority[rows].copy()
    priorities[[text is None for text in texts]] = np.nan
    segments = np.asarray(render_edge_index, dtype=np.intp)
    starts = np.searchsorted(segments, np.arange(len(rows)), side="left")
    ends = np.searchsorted(segments, np.arange(len(rows)), side="right")
    if np.any(ends <= starts) or np.any(np.diff(segments) < 0):
        raise ValueError("graph routing must emit every render edge's segments contiguously")
    return texts, priorities, starts + (ends - starts) // 2


def _add_layer_channels(trace: Any, layers: dict[str, Any], *, edge: bool) -> None:
    """Ship Rust-lowered semantic paint layers as per-item trace channels (#34).

    Absent layers (every color all-zero, every dash solid) ship nothing, so
    plain graphs keep their exact payload. Node halos carry their diameter
    (``halo_size``); edge halos and class bodies carry widths.
    """
    from . import channels

    def rgba(name: str, values: np.ndarray) -> None:
        trace.style_channels[name] = channels.StyleChannel(
            values=np.ascontiguousarray(values, dtype=np.uint8), components=4, dtype="u8"
        )

    def floats(name: str, values: np.ndarray, components: int = 1) -> None:
        trace.style_channels[name] = channels.StyleChannel(
            values=np.ascontiguousarray(values, dtype=np.float64), components=components
        )

    if np.any(layers["halo_rgba"]):
        rgba("halo_rgba", layers["halo_rgba"])
        floats("halo_width" if edge else "halo_size", layers["halo_extent"])
    if not edge:
        return
    if np.any(layers["body_rgba"]):
        rgba("body_rgba", layers["body_rgba"])
        floats("body_width", layers["body_width"])
    if np.any(layers["dash_px"][:, 1] > 0):
        floats("edge_dash", layers["dash_px"], components=2)


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
