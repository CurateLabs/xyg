"""The declarative mark core: the single implementation of every chart kind.

Each function here IS both public dialects: `Figure` binds them as its fluent
methods (`Figure.scatter is marks.scatter`), and the composition API's
appliers call those same bound methods. One body, one signature, one set of
defaults — the parity tests assert the identity. Functions take the figure
as `self` (they are written as methods; `__figure.py` assigns them in the class
body) and reach engine state — store, traces, checkpoint/rollback, ingest and
axis-position helpers — through it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np

from . import channels, styles
from ._marks_bar import (
    bar,  # noqa: F401
    column,  # noqa: F401
)
from ._marks_bar import (
    bar_like as _bar_like,  # noqa: F401
)
from ._marks_contour import (
    contour,  # noqa: F401
)
from ._marks_distribution import (
    box,  # noqa: F401
    violin,  # noqa: F401
)
from ._marks_distribution import (
    distribution_stats as _distribution_stats,  # noqa: F401
)
from ._marks_errorbar import (
    error_band,  # noqa: F401
    errorbar,  # noqa: F401
)
from ._marks_heatmap import (
    heatmap,  # noqa: F401
)
from ._marks_hexbin import (
    hexbin,  # noqa: F401
)
from ._marks_histogram import (
    hist,  # noqa: F401
    histogram,  # noqa: F401
)
from ._marks_line import (
    area,  # noqa: F401
    line,  # noqa: F401
)
from ._marks_ribbon import (
    ribbon,  # noqa: F401
)
from ._marks_scatter import (
    scatter,  # noqa: F401
)
from ._marks_segments import (
    segments,  # noqa: F401
)
from ._marks_step import (
    ecdf,  # noqa: F401
    stairs,  # noqa: F401
    stem,  # noqa: F401
    step,  # noqa: F401
)
from ._marks_style import (
    SYMBOL_CODES as _SYMBOL_CODES,  # noqa: F401
)
from ._marks_style import (
    append_segment_trace as _append_segment_trace,  # noqa: F401
)
from ._marks_style import (
    direct_style as _direct_style,
)
from ._marks_style import (
    stroke_channel as _stroke_channel,
)
from ._marks_style import (
    validated_marker_path as _validated_marker_path,  # noqa: F401
)
from ._trace import Trace
from ._typing import ArrayLike

if TYPE_CHECKING:
    from ._figure import Figure


def sankey(
    self: "Figure",
    links: Any,
    *,
    nodes: Optional[Sequence[Any]] = None,
    node_width: float = 0.02,
    node_padding: float = 0.02,
    align: str = "justify",
    iterations: int = 6,
    colors: Optional[Sequence[str]] = None,
    link_opacity: Any = 0.4,
    labels: bool = True,
    label_size: float = 12.0,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a Sankey flow diagram: placed nodes, gradient ribbons, labels.

    The layout (layering, crossing minimisation, value-proportional heights,
    endpoint stacking) runs in the Rust ABI via `_sankey.compute_layout`,
    exactly as `hist` owns its binning; the drawing is two `ribbon` traces — the
    links, and the nodes themselves, since a band whose two spans are equal *is*
    a rectangle. Each link takes its source node's colour at the source end and
    its target node's at the target end, so the gradient reads as flow.

    Args:
        links: ``(source, target, value)`` triples; endpoints are node names.
        nodes: Explicit node order. Defaults to first appearance in `links`.
        node_width: Node rectangle width as a fraction of the diagram.
        node_padding: Vertical gap between nodes in a layer, as a fraction.
        align: ``"justify"`` flushes sinks to the last layer.
        iterations: Barycentre sweeps for crossing minimisation.
        colors: One CSS colour per node, in node order. Defaults to the
            figure's palette cycle.
        link_opacity: Ribbon fill opacity; nodes stay opaque.
        labels: Draw node names beside the nodes.
        label_size: Node label font size in px.
        style: Mark style overrides for the LINK ribbons.
    """
    from . import _sankey

    triples = [(s_, t_, v_) for s_, t_, v_ in links]
    layout = _sankey.compute_layout(
        triples,
        nodes=list(nodes) if nodes is not None else None,
        node_width=node_width,
        node_padding=node_padding,
        align=align,
        iterations=iterations,
    )
    n_nodes = len(layout.nodes)
    if colors is not None:
        if len(colors) != n_nodes:
            raise ValueError(
                f"sankey colors must have one entry per node ({n_nodes}); got {len(colors)}"
            )
        node_css = [str(c) for c in colors]
    else:
        node_css = [self.palette_color(i) for i in range(n_nodes)]

    try:
        link_alpha = float(link_opacity)
    except (TypeError, ValueError):
        raise ValueError(
            f"sankey link_opacity must be a number in (0, 1], got {link_opacity!r}"
        ) from None
    if not 0.0 < link_alpha <= 1.0:
        raise ValueError("sankey link_opacity must be in (0, 1]")

    checkpoint = self._checkpoint()
    try:
        if layout.links:
            self.ribbon(
                [layout.nodes[link.source].x1 for link in layout.links],
                [layout.nodes[link.target].x0 for link in layout.links],
                [link.source_y0 for link in layout.links],
                [link.source_y1 for link in layout.links],
                [link.target_y0 for link in layout.links],
                [link.target_y1 for link in layout.links],
                color=[node_css[link.source] for link in layout.links],
                color_target=[node_css[link.target] for link in layout.links],
                name=None,
                opacity=link_alpha,
                style=style,
            )
            self.traces[-1].tooltip_rows = [
                {
                    "source": layout.nodes[link.source].name,
                    "target": layout.nodes[link.target].name,
                    "value": float(link.value),
                }
                for link in layout.links
            ]
        # The nodes: a ribbon whose two spans are equal is an axis-aligned
        # rectangle, so nodes need no second primitive.
        self.ribbon(
            [node.x0 for node in layout.nodes],
            [node.x1 for node in layout.nodes],
            [node.y0 for node in layout.nodes],
            [node.y1 for node in layout.nodes],
            [node.y0 for node in layout.nodes],
            [node.y1 for node in layout.nodes],
            color=node_css,
            opacity=1.0,
        )
        self.traces[-1].tooltip_rows = [
            {"node": node.name, "value": float(node.value)} for node in layout.nodes
        ]
        if labels:
            last = max(node.layer for node in layout.nodes)
            for node in layout.nodes:
                at_right = node.layer >= (last + 1) / 2
                self.text(
                    node.x0 - 0.008 if at_right else node.x1 + 0.008,
                    (node.y0 + node.y1) / 2.0,
                    node.name,
                    dx=0.0,
                    dy=0.0,
                    anchor="end" if at_right else "start",
                    style={"font_size": label_size},
                )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise


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


def triangle_mesh(
    self: "Figure",
    x0: ArrayLike,
    y0: ArrayLike,
    x1: ArrayLike,
    y1: ArrayLike,
    x2: ArrayLike,
    y2: ArrayLike,
    *,
    color: Union[str, ArrayLike, None] = None,
    colormap: channels.ColormapLike = channels.DEFAULT_COLORMAP,
    domain: Optional[tuple[float, float]] = None,
    name: Optional[str] = None,
    opacity: Any = 1.0,
    stroke: Any = None,
    stroke_width: Any = 0.0,
    _joined_fill: bool = False,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add independently colored filled triangles as one instanced mesh."""
    css = styles.compile_mark_style("triangle_mesh", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    stroke = css.get("stroke", stroke)
    stroke_width = css.get("stroke_width", stroke_width)
    name = self._optional_text(name, "triangle_mesh name")
    arrays = [
        self._as_1d_float(values, f"triangle_mesh {label}")
        for label, values in (
            ("x0", x0),
            ("y0", y0),
            ("x1", x1),
            ("y1", y1),
            ("x2", x2),
            ("y2", y2),
        )
    ]
    if len({len(values) for values in arrays}) != 1:
        raise ValueError("triangle_mesh coordinate columns must have equal length")
    n = len(arrays[0])
    style_channels: dict[str, channels.StyleChannel] = {}
    opacity_value = _direct_style(
        opacity,
        n,
        "triangle_mesh opacity",
        style_channels,
        "opacity",
        default=1.0,
        minimum=0.0,
        maximum=1.0,
    )
    stroke_value, stroke_ch = _stroke_channel(stroke, n, "triangle_mesh stroke")
    stroke_width_value = _direct_style(
        stroke_width,
        n,
        "triangle_mesh stroke_width",
        style_channels,
        "stroke_width",
        default=0.0,
        minimum=0.0,
    )
    if (
        (stroke_value is not None or stroke_ch is not None)
        and not stroke_width_value
        and ("stroke_width" not in style_channels)
    ):
        stroke_width_value = 1.0
    color_ch = channels.resolve_color(
        color,
        n,
        colormap=colormap,
        default_constant=self.next_series_color,
        palette=self.palette,
    )
    if domain is not None:
        if color_ch.mode != "continuous":
            raise ValueError("triangle_mesh domain requires a continuous numeric color array")
        color_ch.domain = self._finite_increasing_pair(domain, "triangle_mesh domain")
    # A width without an explicit stroke means "outline in the face color".
    # Constant paints already get that fallback from the renderer; direct and
    # semantic color channels need the explicit buffer-free match mode.
    if (
        stroke_value is None
        and stroke_ch is None
        and color_ch.mode != "constant"
        and (stroke_width_value or "stroke_width" in style_channels)
    ):
        stroke_ch = channels.ColorChannel(mode="match_fill")
    checkpoint = self._checkpoint()
    try:
        x0c, y0c, x1c, y1c, x2c, y2c = [self.store.ingest(values) for values in arrays]
        style: dict[str, Any] = {"opacity": opacity_value, "role": "triangle-mesh"}
        if _joined_fill:
            style["joined_fill"] = True
        style.update(styles._opacity_channels(css))
        if stroke_value is not None:
            style["stroke"] = stroke_value
        if stroke_width_value:
            style["stroke_width"] = stroke_width_value
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="triangle_mesh",
                x=x2c,
                y=y2c,
                x0=x0c,
                x1=x1c,
                y0=y0c,
                y1=y1c,
                name=name,
                style=style,
                color_ch=color_ch,
                stroke_ch=stroke_ch,
                style_channels=style_channels,
                count=n,
            )
        )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise
