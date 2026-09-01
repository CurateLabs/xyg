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

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np

from . import _validate, channels, columns, kernels, styles
from ._marks_bar import (
    bar,  # noqa: F401
    column,  # noqa: F401
)
from ._marks_bar import (
    bar_like as _bar_like,  # noqa: F401
)
from ._marks_bar import (
    series_corner_radius as _series_corner_radius,
)
from ._marks_bar import (
    series_style_values as _series_style_values,
)
from ._marks_contour import (
    contour,  # noqa: F401
)
from ._marks_errorbar import (
    error_band,  # noqa: F401
    errorbar,  # noqa: F401
)
from ._marks_distribution import (
    distribution_groups as _distribution_groups,
)
from ._marks_distribution import (
    distribution_stats as _distribution_stats,  # noqa: F401
)
from ._marks_scatter import (
    scatter,  # noqa: F401
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
    stroke_geometry as _stroke_geometry,
)
from ._marks_style import (
    validated_marker_path as _validated_marker_path,  # noqa: F401
)
from ._trace import Trace
from ._typing import ArrayLike, Scalar
from .config import (
    DEFAULT_PALETTE,
)

if TYPE_CHECKING:
    from ._figure import Figure


def segments(
    self: "Figure",
    x0: ArrayLike,
    y0: ArrayLike,
    x1: ArrayLike,
    y1: ArrayLike,
    *,
    name: Optional[str] = None,
    color: Union[str, ArrayLike, None] = None,
    colormap: channels.ColormapLike = channels.DEFAULT_COLORMAP,
    domain: Optional[tuple[float, float]] = None,
    width: Any = 1.2,
    opacity: Any = 1.0,
    dash: Union[str, Sequence[float], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add independent line segments through the shared instanced renderer."""
    css = styles.compile_mark_style("segments", style)
    color = css.get("color", color)
    width = css.get("width", width)
    opacity = css.get("opacity", opacity)
    dash = css.get("dash", dash)
    arrays = [self._as_1d_float(values, "segments color geometry") for values in (x0, y0, x1, y1)]
    if len({len(values) for values in arrays}) != 1:
        raise ValueError("segments coordinate columns must have equal length")
    color_ch = channels.resolve_color(
        color,
        len(arrays[0]),
        colormap=colormap,
        default_constant=self.next_series_color,
        palette=self.palette,
    )
    if domain is not None:
        if color_ch.mode != "continuous":
            raise ValueError("segments domain requires a continuous numeric color array")
        color_ch.domain = self._finite_increasing_pair(domain, "segments domain")
    constant = color_ch.constant if color_ch.mode == "constant" else None
    dash_spec = _validate.dash(dash, "segments dash")
    self._append_segment_trace(
        "segments",
        arrays[0],
        arrays[2],
        arrays[1],
        arrays[3],
        name=name,
        color=constant,
        opacity=opacity,
        width=width,
        role="segments",
        dash=dash_spec,
        color_ch=None if color_ch.mode == "constant" else color_ch,
        extra_style=styles._opacity_channels(css),
    )
    return self


def ribbon(
    self: "Figure",
    x0: ArrayLike,
    x1: ArrayLike,
    source_lo: ArrayLike,
    source_hi: ArrayLike,
    target_lo: ArrayLike,
    target_hi: ArrayLike,
    *,
    color: Union[str, ArrayLike, None] = None,
    color_target: Union[str, ArrayLike, None] = None,
    colormap: channels.ColormapLike = channels.DEFAULT_COLORMAP,
    name: Optional[str] = None,
    opacity: Any = 1.0,
    stroke: Any = None,
    stroke_width: Any = 0.0,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add flow bands: a span at `x0` joined to a span at `x1` by a cubic.

    The primitive behind Sankey, and the reason it is a primitive rather than a
    composition: each band carries a colour at *each* end and the gradient runs
    along the flow, which no existing mark can express (see the ribbon geometry
    contract in spec/api/chart-kind-contract.md).

    `color`/`color_target` take a CSS colour, per-band colours (RGBA rows carry
    per-band alpha), or numeric values sampled through `colormap`; every
    encoding resolves to concrete per-band paint before shipping. `opacity`,
    `stroke` and `stroke_width` are per-trace scalars — per-band styling rides
    the colour channels, nowhere else.
    """
    css = styles.compile_mark_style("ribbon", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    stroke = css.get("stroke", stroke)
    stroke_width = css.get("stroke_width", stroke_width)
    name = self._optional_text(name, "ribbon name")
    arrays = [
        self._as_1d_float(values, f"ribbon {label}")
        for label, values in (
            ("x0", x0),
            ("x1", x1),
            ("source_lo", source_lo),
            ("source_hi", source_hi),
            ("target_lo", target_lo),
            ("target_hi", target_hi),
        )
    ]
    lengths = {len(values) for values in arrays}
    if len(lengths) != 1:
        raise ValueError(f"ribbon columns must be the same length; got {sorted(lengths)}")
    n = int(arrays[0].size)
    # Ribbon styles are per-trace scalars, refused as arrays rather than
    # silently flattened: the ribbon program's a_rgba2 shares its attribute
    # slot with a_style, so the standard per-instance style route cannot
    # coexist with the two-ended gradient, and a capability one renderer
    # cannot draw is absent everywhere (parity is identity). Per-band alpha
    # is not lost — RGBA rows in `color`/`color_target` carry it, and every
    # renderer interpolates all four channels along the band.
    opacity_constant, opacity_channel = channels.resolve_style_channel(
        opacity, n, "ribbon opacity", minimum=0.0, maximum=1.0
    )
    if opacity_channel is not None:
        raise ValueError(
            "ribbon opacity is per-trace; put per-band alpha in the color "
            "arrays instead (RGBA rows interpolate along each band)"
        )
    opacity_value = 1.0 if opacity_constant is None else float(opacity_constant)
    stroke_value, stroke_ch = _stroke_channel(stroke, n, "ribbon stroke")
    if stroke_ch is not None:
        raise ValueError(
            "ribbon stroke is per-trace; omit it to outline each band with "
            "its own fill color (edgecolors='face')"
        )
    width_constant, width_channel = channels.resolve_style_channel(
        stroke_width, n, "ribbon stroke_width", minimum=0.0
    )
    if width_channel is not None:
        raise ValueError("ribbon stroke_width is per-trace")
    stroke_width_value = 0.0 if width_constant is None else float(width_constant)
    # Ribbon ships resolved paints only (constant or direct RGBA): numeric
    # `color=` encodings are sampled through the shared exporter LUT here,
    # once, instead of teaching the two-ended ribbon program a cval path it
    # has no attribute slot for (ribbon geometry contract).
    color_ch = channels.resolve_direct_rgba(
        channels.resolve_color(
            color,
            n,
            colormap=colormap,
            default_constant=self.next_series_color,
            palette=self.palette,
        )
    )
    # No target colour means a flat band. Resolving one anyway would ship a
    # second buffer and turn every plain ribbon into a two-stop gradient in
    # three renderers for no visible difference.
    color2_ch = (
        None
        if color_target is None
        else channels.resolve_direct_rgba(
            channels.resolve_color(
                color_target,
                n,
                colormap=colormap,
                default_constant=self.next_series_color,
                palette=self.palette,
            )
        )
    )
    checkpoint = self._checkpoint()
    try:
        x0c, x1c, slo, shi, tlo, thi = [self.store.ingest(values) for values in arrays]
        style_dict: dict[str, Any] = {"opacity": opacity_value, "role": "ribbon"}
        style_dict.update(styles._opacity_channels(css))
        if stroke_value is not None:
            style_dict["stroke"] = stroke_value
        if stroke_width_value:
            style_dict["stroke_width"] = stroke_width_value
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="ribbon",
                # The six geometry slots are saturated: `x`/`y` carry the
                # TARGET span's y values, which is why `_range_columns` needs a
                # ribbon branch to autorange them on the y axis.
                x=tlo,
                y=thi,
                x0=x0c,
                x1=x1c,
                y0=slo,
                y1=shi,
                name=name,
                style=style_dict,
                color_ch=color_ch,
                color2_ch=color2_ch,
                count=n,
            )
        )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise


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


def line(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 1.5,
    opacity: float = 1.0,
    curve: str = "linear",
    dash: Union[str, Sequence[float], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a line series. Very long series are automatically downsampled for
    display without changing the drawn shape.

    ``curve="smooth"`` renders a monotone cubic; ``dash`` dashes the line.
    """
    css = styles.compile_mark_style("line", style)
    color = css.get("color", color)
    width = css.get("width", width)
    opacity = css.get("opacity", opacity)
    dash = css.get("dash", dash)
    name = self._optional_text(name, "line name")
    color = self._optional_css_color(color, "line color")
    if color is None:
        color = self.next_series_color()
    width = self._positive_scalar(width, "line width")
    opacity = self._opacity(opacity, "line opacity")
    curve = _validate.curve(curve, "line curve")
    dash_spec = _validate.dash(dash, "line dash")
    checkpoint = self._checkpoint()
    try:
        xc, yc = self._ingest_xy(x, y, "line")
        # Polar keeps the caller's sequence. Theta is the order marks are
        # JOINED in, not a domain to be scanned: sorting it redrew a path that
        # crosses the 0/turn seam (350 -> 10) or doubles back as an
        # ascending-angle fan instead of the authored track. Safe because polar
        # forces tier="direct" (config.py: "M4 decimation buckets on a
        # monotonic screen-x column, which a spiral is not"), so the sorted
        # precondition the sort exists to satisfy never applies here.
        if self.coords != "polar" and not kernels.is_sorted(xc.values):
            # LOD contract (§28): line x must be sorted; the engine sorts once
            # at ingest, and says so. The predicate is NaN-safe on purpose:
            # a NaN fails its pairs, so a NaN-carrying x cannot skip the sort
            # and violate M4's sorted precondition.
            # argsort places NaNs last, where the m4 window excludes them.
            order = kernels.argsort_stable(xc.values)
            xc = self.store.ingest(xc.values[order])
            yc = self.store.ingest(yc.values[order])
        style: dict[str, Any] = {"color": color, "width": width, "opacity": opacity}
        style.update(styles._opacity_channels(css))
        style.update(_stroke_geometry(css))
        if curve != "linear":
            style["curve"] = curve
        if dash_spec is not None:
            style["dash"] = dash_spec
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="line",
                x=xc,
                y=yc,
                name=name,
                style=style,
            )
        )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise


def area(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    base: Union[Scalar, ArrayLike] = 0.0,
    name: Optional[str] = None,
    color: Optional[str] = None,
    opacity: float = 0.35,
    line_color: Optional[str] = None,
    line_width: float = 1.2,
    line_opacity: float = 1.0,
    stroke_perimeter: bool = False,
    fill: Union[str, dict[str, str], None] = None,
    curve: str = "linear",
    dash: Union[str, Sequence[float], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a filled area trace between `y` and `base`.

    `base` may be a scalar or a length-N array, which covers both the common
    zero-baseline area chart and future stacked-area construction.
    `fill` accepts a CSS `linear-gradient(...)` (see spec/api/styling.md);
    `curve="smooth"` renders a monotone cubic through the points; `dash`
    dashes the outline.
    """
    css = styles.compile_mark_style("area", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    line_color = css.get("line_color", line_color)
    line_width = css.get("line_width", line_width)
    line_opacity = css.get("line_opacity", line_opacity)
    fill = css.get("fill", fill)
    dash = css.get("dash", dash)
    name = self._optional_text(name, "area name")
    color = self._optional_css_color(color, "area color")
    if color is None:
        color = self.next_series_color()
    opacity = self._opacity(opacity, "area opacity")
    line_color = self._optional_css_color(line_color, "area line_color")
    line_width = self._nonnegative_scalar(line_width, "area line_width")
    line_opacity = self._opacity(line_opacity, "area line_opacity")
    stroke_perimeter = _validate.bool_param(stroke_perimeter, "area stroke_perimeter")
    fill_spec = _validate.mark_fill(fill, "area fill")
    curve = _validate.curve(curve, "area curve")
    dash_spec = _validate.dash(dash, "area dash")
    checkpoint = self._checkpoint()
    try:
        xc, yc = self._ingest_xy(x, y, "area")
        bc = (
            self.store.ingest(np.full(len(xc), self._finite_scalar(base, "area base")))
            if np.isscalar(base)
            else self.store.ingest(base)
        )
        if len(bc) != len(xc):
            raise ValueError(f"area base must have length {len(xc)}, got {len(bc)}")
        if self.coords != "polar" and not kernels.is_sorted(xc.values):
            order = kernels.argsort_stable(xc.values)
            xc = self.store.ingest(xc.values[order])
            yc = self.store.ingest(yc.values[order])
            bc = self.store.ingest(bc.values[order])
        style: dict[str, Any] = {
            "color": color,
            "opacity": opacity,
            "line_width": line_width,
            "line_opacity": line_opacity,
            "stroke_perimeter": stroke_perimeter,
        }
        style.update(styles._opacity_channels(css))
        if line_color is not None:
            style["line_color"] = line_color
        if fill_spec is not None:
            style["fill"] = fill_spec
        if curve != "linear":
            style["curve"] = curve
        if dash_spec is not None:
            style["dash"] = dash_spec
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="area",
                x=xc,
                y=yc,
                base=bc,
                name=name,
                style=style,
            )
        )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise


def step(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    where: str = "post",
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 1.5,
    opacity: float = 1.0,
    dash: Union[str, Sequence[float], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a step line without expanding the canonical input columns."""
    if where not in {"pre", "post", "mid"}:
        raise ValueError("step where must be 'pre', 'post', or 'mid'")
    css = styles.compile_mark_style("step", style)
    self.line(
        x,
        y,
        name=name,
        color=css.get("color", color),
        width=css.get("width", width),
        opacity=css.get("opacity", opacity),
        dash=css.get("dash", dash),
    )
    self.traces[-1].style["step"] = where
    self.traces[-1].style.update(styles._opacity_channels(css))
    self.traces[-1].style.update(_stroke_geometry(css))
    return self


def stairs(
    self: "Figure",
    values: ArrayLike,
    edges: Optional[ArrayLike] = None,
    *,
    where: str = "post",
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 1.5,
    opacity: float = 1.0,
    dash: Union[str, Sequence[float], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a Matplotlib-style precomputed stairs series.

    Ships the compact canonical form — the k+1 edges as x plus k+1 values
    with one endpoint duplicated — and lets the step tag do all expansion
    client-side, so bins never pre-expand into polyline vertices. Every
    ``where`` renders bin i at height ``values[i]``; ``mid`` moves the risers
    to the bin centers.
    """
    if where not in {"pre", "post", "mid"}:
        raise ValueError("stairs where must be 'pre', 'post', or 'mid'")
    vals = self._as_1d_float(values, "stairs values")
    if len(vals) == 0:
        raise ValueError("stairs values must contain at least one value")
    if edges is None:
        edge_values = np.arange(len(vals) + 1, dtype=np.float64)
    else:
        edge_values = self._as_1d_float(edges, "stairs edges")
    if len(edge_values) != len(vals) + 1:
        raise ValueError(f"stairs edges must have length {len(vals) + 1}, got {len(edge_values)}")
    if not np.all(np.isfinite(edge_values)) or not np.all(np.diff(edge_values) > 0):
        raise ValueError("stairs edges must be finite and strictly increasing")
    # Step expansion holds each y from its riser onward: "pre" reads the value
    # right of each edge from the next point, so the first value repeats;
    # "post"/"mid" read it from the previous point, so the last value repeats.
    sy = np.concatenate((vals[:1], vals)) if where == "pre" else np.append(vals, vals[-1])
    return self.step(
        edge_values,
        sy,
        where=where,
        name=name,
        color=color,
        width=width,
        opacity=opacity,
        dash=dash,
        style=style,
    )


def ecdf(
    self: "Figure",
    values: ArrayLike,
    *,
    bins: Optional[int] = None,
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 1.5,
    opacity: float = 1.0,
    dash: Union[str, Sequence[float], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add an empirical cumulative distribution function.

    Exact mode coalesces repeated values before shipping. ``bins`` provides a
    bounded approximation for very large distributions using the native
    binned-ECDF kernel.
    """
    raw_values = self._as_1d_float(values, "ecdf values")
    if bins is not None:
        if (
            isinstance(bins, (bool, np.bool_))
            or not isinstance(bins, (int, np.integer))
            or int(bins) <= 0
        ):
            raise ValueError("ecdf bins must be a positive integer or None")
        try:
            sx, sy = kernels.binned_ecdf(raw_values, int(bins))
        except ValueError:
            if not np.isfinite(raw_values).any():
                raise ValueError("ecdf values must contain at least one finite value") from None
            raise
        return self.step(
            sx,
            sy,
            where="post",
            name=name,
            color=color,
            width=width,
            opacity=opacity,
            dash=dash,
            style=style,
        )
    finite = np.isfinite(raw_values)
    if not finite.any():
        raise ValueError("ecdf values must contain at least one finite value")
    unique, cdf = kernels.weighted_ecdf(raw_values, np.ones(len(raw_values), dtype=np.float64))
    sx = np.concatenate(([unique[0]], unique))
    sy = np.concatenate(([0.0], cdf))
    return self.step(
        sx,
        sy,
        where="post",
        name=name,
        color=color,
        width=width,
        opacity=opacity,
        dash=dash,
        style=style,
    )


def stem(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    base: Union[Scalar, ArrayLike] = 0.0,
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 1.2,
    opacity: float = 1.0,
    marker: bool = True,
    marker_size: float = 5.0,
    symbol: str = "circle",
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add vertical stem segments and optional point markers."""
    css = styles.compile_mark_style("stem", style)
    color = css.get("color", color)
    width = css.get("width", width)
    opacity = css.get("opacity", opacity)
    name = self._optional_text(name, "stem name")
    color = self._optional_css_color(color, "stem color")
    if color is None:
        color = self.next_series_color()
    width = self._positive_scalar(width, "stem width")
    opacity = self._opacity(opacity, "stem opacity")
    marker_size = self._nonnegative_scalar(marker_size, "stem marker_size")
    symbol = _validate.point_symbol(symbol, "stem symbol")
    checkpoint = self._checkpoint()
    try:
        xc, yc = self._ingest_xy(x, y, "stem")
        basev = self._broadcast_base(base, len(xc), "stem")
        self._append_segment_trace(
            "stem",
            xc.values,
            xc.values,
            basev,
            yc.values,
            name=name,
            color=color,
            opacity=opacity,
            width=width,
            role="stem",
            count=len(xc),
            extra_style=styles._opacity_channels(css),
        )
        if marker:
            self.scatter(
                xc.values,
                yc.values,
                name=None,
                color=color,
                size=marker_size,
                opacity=opacity,
                density=None,
                symbol=symbol,
            )
            # Retain the generated relationship for the bounded public Scene
            # exporter.  This is host provenance only: Rust still receives the
            # same ordinary scatter record after the stem record, preserving
            # paint order without adding a Scene schema feature.
            self.traces[-1].style["role"] = "stem-marker"
        return self
    except Exception:
        self._rollback(checkpoint)
        raise


def histogram(
    self: "Figure",
    values: ArrayLike,
    *,
    bins: Union[int, str, ArrayLike] = "auto",
    range: Optional[tuple[float, float]] = None,
    density: bool = False,
    cumulative: bool = False,
    name: Optional[str] = None,
    color: Any = None,
    opacity: Any = 0.85,
    corner_radius: Any = 0.0,
    stroke: Any = None,
    stroke_width: Any = 0.0,
    _artist_alpha: Any = None,
    fill: Union[str, dict[str, str], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a 1D histogram backed by the shared rectangle primitive.

    `cumulative=True` accumulates bins left-to-right: with the default
    count mode the last bin equals the number of in-range values; combined
    with `density=True` it becomes the empirical CDF (last bin ~1.0).
    """
    css = styles.compile_mark_style("histogram", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    corner_radius = css.get("corner_radius", corner_radius)
    stroke = css.get("stroke", stroke)
    stroke_width = css.get("stroke_width", stroke_width)
    fill = css.get("fill", fill)
    name = self._optional_text(name, "histogram name")
    density = self._bool_param(density, "histogram density")
    cumulative = self._bool_param(cumulative, "histogram cumulative")
    vals = self._as_1d_float(values, "histogram values")
    if density and not np.isfinite(vals).any():
        raise ValueError("histogram density requires at least one finite value")
    hist_range = None if range is None else self._finite_increasing_pair(range, "histogram range")
    if isinstance(bins, (int, np.integer)) and not isinstance(bins, bool):
        n_bins = int(bins)
        if n_bins <= 0:
            raise ValueError("histogram bins must be positive")
        try:
            edges = kernels.histogram_mark_edges(
                vals, range=hist_range, method="uniform", n_bins=n_bins
            )
        except ValueError as exc:
            raise ValueError("histogram could not produce finite bins") from exc
    elif isinstance(bins, str) and bins.lower() in {"auto", "sturges"}:
        try:
            edges = kernels.histogram_mark_edges(vals, range=hist_range, method=bins.lower())
        except ValueError as exc:
            raise ValueError("invalid histogram_edges arguments") from exc
    else:
        finite = vals[np.isfinite(vals)]
        if len(finite) == 0 and isinstance(bins, str):
            try:
                edges = kernels.histogram_mark_edges(vals, range=hist_range, method="auto")
            except ValueError as exc:
                raise ValueError("histogram could not produce finite bins") from exc
        else:
            edges = np.asarray(bins, dtype=np.float64)
            if edges.ndim != 1 or edges.size < 2:
                raise ValueError("histogram bins must be a 1-D increasing sequence")
    try:
        counts = kernels.histogram_bins(vals, edges, density=density, cumulative=cumulative)
    except ValueError as exc:
        raise ValueError("histogram could not produce finite bins") from exc
    n_bins = len(counts)
    direct_color = (
        channels.resolve_color(color, n_bins, default_constant=DEFAULT_PALETTE[0])
        if color is not None and not isinstance(color, str)
        else None
    )
    color_value = color if direct_color is None else None
    if direct_color is None and color_value is None:
        color_value = self.next_series_color()
    stroke_value, stroke_channel = _stroke_channel(stroke, n_bins, "histogram stroke")
    opacity_value, opacity_channels = _series_style_values(
        opacity,
        1,
        n_bins,
        "histogram opacity",
        "opacity",
        default=0.85,
        minimum=0.0,
        maximum=1.0,
    )
    width_value, width_channels = _series_style_values(
        stroke_width,
        1,
        n_bins,
        "histogram stroke_width",
        "stroke_width",
        default=0.0,
        minimum=0.0,
    )
    constant_radius, radius_channels = _series_corner_radius(
        corner_radius, 1, n_bins, "histogram corner_radius"
    )
    _, alpha_channels = _series_style_values(
        _artist_alpha,
        1,
        n_bins,
        "histogram alpha",
        "artist_alpha",
        default=-1.0,
        minimum=-1.0,
        maximum=1.0,
    )
    mark_style = self._rect_mark_style(
        "histogram", constant_radius, stroke_value, width_value[0], fill
    )
    mark_style.update(styles._opacity_channels(css))
    style_channels = {
        **opacity_channels[0],
        **width_channels[0],
        **radius_channels[0],
        **alpha_channels[0],
    }
    zeros = np.zeros_like(counts, dtype=np.float64)
    self._append_rect_trace(
        "histogram",
        edges[:-1],
        edges[1:],
        zeros,
        counts,
        name=name,
        color=color_value,
        opacity=opacity_value[0],
        role="histogram",
        count=int(len(vals)),
        extra_style={"cumulative": cumulative, "density": density, **mark_style},
        color_ch=direct_color,
        stroke_ch=stroke_channel,
        style_channels=style_channels,
    )
    return self


def hist(
    self: "Figure",
    values: ArrayLike,
    *,
    bins: Union[int, str, ArrayLike] = "auto",
    range: Optional[tuple[float, float]] = None,
    density: bool = False,
    cumulative: bool = False,
    name: Optional[str] = None,
    color: Any = None,
    opacity: Any = 0.85,
    corner_radius: Any = 0.0,
    stroke: Any = None,
    stroke_width: Any = 0.0,
    _artist_alpha: Any = None,
    fill: Union[str, dict[str, str], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Short alias for `histogram(...)`, matching common Python chart APIs."""
    return self.histogram(
        values,
        bins=bins,
        range=range,
        density=density,
        cumulative=cumulative,
        name=name,
        color=color,
        opacity=opacity,
        corner_radius=corner_radius,
        stroke=stroke,
        stroke_width=stroke_width,
        _artist_alpha=_artist_alpha,
        fill=fill,
        style=style,
    )


def box(
    self: "Figure",
    values: ArrayLike,
    *,
    x: Optional[ArrayLike] = None,
    group: Optional[ArrayLike] = None,
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 0.6,
    opacity: float = 0.85,
    orientation: str = "vertical",
    show_outliers: bool = True,
    outlier_size: float = 4.0,
    style: styles.StyleMapping | None = None,
    whisker_style: styles.StyleMapping | None = None,
    median_style: styles.StyleMapping | None = None,
    outlier_style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add grouped Tukey box plots with independently styleable parts."""
    css = styles.compile_mark_style("box", style)
    whisker_css = styles.compile_mark_style("segments", whisker_style, "box whisker_style")
    median_css = styles.compile_mark_style("segments", median_style, "box median_style")
    styles.compile_mark_style("scatter", outlier_style, "box outlier_style")
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    if orientation not in {"vertical", "horizontal"}:
        raise ValueError("box orientation must be 'vertical' or 'horizontal'")
    name = self._optional_text(name, "box name")
    color = self._optional_css_color(color, "box color")
    if color is None:
        color = self.next_series_color()
    width = self._positive_scalar(width, "box width")
    opacity = self._opacity(opacity, "box opacity")
    show_outliers = self._bool_param(show_outliers, "box show_outliers")
    outlier_size = self._nonnegative_scalar(outlier_size, "box outlier_size")
    category_axis = "x" if orientation == "vertical" else "y"
    groups, positions = _distribution_groups(
        self, values, x, group, "box", category_axis=category_axis
    )
    offsets = np.empty(len(groups) + 1, dtype=np.uintp)
    offsets[0] = 0
    for index, group_values in enumerate(groups):
        offsets[index + 1] = offsets[index] + len(group_values)
    flat = np.concatenate(groups) if groups else np.empty(0, dtype=np.float64)
    if not np.isfinite(flat).any():
        raise ValueError("box values must contain at least one finite group")
    try:
        geometry = kernels.box_geometry(
            flat,
            offsets,
            np.asarray(positions, dtype=np.float64),
            width,
            orientation,
            show_outliers,
        )
    except ValueError as exc:
        raise ValueError("invalid bounded box geometry") from exc
    checkpoint = self._checkpoint()
    try:
        self._commit_axis_positions(x if x is not None else group, category_axis)
        bx0, by0, bx1, by1 = geometry["body"]
        wx0, wy0, wx1, wy1 = geometry["whiskers"]
        mx0, my0, mx1, my1 = geometry["medians"]
        self._append_segment_trace(
            "box_whisker",
            wx0,
            wx1,
            wy0,
            wy1,
            name=None,
            color=whisker_css.get("color", color),
            opacity=whisker_css.get("opacity", opacity),
            width=whisker_css.get("width", 1.0),
            role="box-whisker",
            extra_style=styles._opacity_channels(whisker_css),
        )
        self._append_rect_trace(
            "box",
            bx0,
            bx1,
            by0,
            by1,
            name=name,
            color=color,
            opacity=opacity,
            role="box",
            extra_style={
                "stroke_width": css.get("stroke_width", 1.0),
                "box_orientation": orientation,
                **({"stroke": css["stroke"]} if "stroke" in css else {}),
                **styles._opacity_channels(css),
            },
        )
        self._append_segment_trace(
            "box_median",
            mx0,
            mx1,
            my0,
            my1,
            name=None,
            color=median_css.get("color", color),
            opacity=median_css.get("opacity", opacity),
            width=median_css.get("width", 1.4),
            role="box-median",
            extra_style=styles._opacity_channels(median_css),
        )
        if show_outliers and len(geometry["outlier_x"]):
            self.scatter(
                geometry["outlier_x"],
                geometry["outlier_y"],
                name=None,
                color=color,
                size=outlier_size,
                opacity=opacity,
                density=None,
                symbol="circle",
                style=outlier_style,
            )
            self.traces[-1].style["role"] = "box-outlier"
        return self
    except Exception:
        self._rollback(checkpoint)
        raise


def violin(
    self: "Figure",
    values: ArrayLike,
    *,
    x: Optional[ArrayLike] = None,
    group: Optional[ArrayLike] = None,
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 0.8,
    bins: int = 64,
    opacity: float = 0.55,
    orientation: str = "vertical",
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add bounded-resolution violin distributions.

    Density estimation and bounded rectangle geometry are computed once in the
    native core (`xyg_violin_rects`); each group ships its fixed ``bins``-sized
    band set. The client draws the bands through the shared instanced
    rectangle path, so input cardinality does not become DOM/GPU object
    cardinality.
    """
    css = styles.compile_mark_style("violin", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    if orientation not in {"vertical", "horizontal"}:
        raise ValueError("violin orientation must be 'vertical' or 'horizontal'")
    if (
        isinstance(bins, (bool, np.bool_))
        or not isinstance(bins, (int, np.integer))
        or int(bins) < 4
        or int(bins) > 1024
    ):
        raise ValueError("violin bins must be an integer between 4 and 1024")
    name = self._optional_text(name, "violin name")
    color = self._optional_css_color(color, "violin color")
    if color is None:
        color = self.next_series_color()
    width = self._positive_scalar(width, "violin width")
    opacity = self._opacity(opacity, "violin opacity")
    category_axis = "x" if orientation == "vertical" else "y"
    groups, positions = _distribution_groups(
        self, values, x, group, "violin", category_axis=category_axis
    )
    n_bins = int(bins)
    offsets = np.empty(len(groups) + 1, dtype=np.uintp)
    offsets[0] = 0
    for index, group_values in enumerate(groups):
        offsets[index + 1] = offsets[index] + len(group_values)
    flat = np.concatenate(groups) if groups else np.empty(0, dtype=np.float64)
    try:
        rect_x0, rect_y0, rect_x1, rect_y1, _active, _edges, _density = kernels.violin_rects(
            flat, offsets, np.asarray(positions, dtype=np.float64), n_bins, width, orientation
        )
    except ValueError as exc:
        raise ValueError("violin values must contain at least one finite group") from exc
    checkpoint = self._checkpoint()
    try:
        self._commit_axis_positions(x if x is not None else group, category_axis)
        self._append_rect_trace(
            "violin",
            rect_x0,
            rect_x1,
            rect_y0,
            rect_y1,
            name=name,
            color=color,
            opacity=opacity,
            role="violin",
            extra_style=styles._opacity_channels(css),
        )
    except Exception:
        self._rollback(checkpoint)
        raise
    return self


def hexbin(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    gridsize: int | tuple[int, int] = 64,
    range: Optional[tuple[tuple[float, float], tuple[float, float]]] = None,
    bins: str = "count",
    C: Optional[ArrayLike] = None,
    reduce_C_function: Callable[[np.ndarray], Scalar] = np.mean,
    mincnt: Optional[int] = None,
    name: Optional[str] = None,
    color: Any = None,
    colormap: channels.ColormapLike = channels.DEFAULT_COLORMAP,
    opacity: float = 0.9,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a screen-bounded hexagonal density plot.

    Binning is performed by the native ``xyg_hexbin`` kernel (count / mean /
    sum). Rust owns finite-pair filtering, automatic domain, default grid
    aspect, and lattice assignment. Custom ``reduce_C_function`` callables
    receive host-reduced groups from ``xyg_hexbin_groups``. Only threshold-passing
    bins are shipped as centers plus one scalar count/color channel. A literal
    ``color`` keeps constant paint so Cartesian native lattices compile onto
    shared-style Scene PolyFill; omitted ``color`` keeps the metric colormap
    and ABI 186 interns those fills through a 1×N XYHP plane. Polar hexbin,
    custom `reduce_C_function` (after Rust lattice groups), and categorical /
    `direct_rgba` cell paints intern the same way (ABI 194).
    """
    css = styles.compile_mark_style("hexbin", style)
    opacity = css.get("opacity", opacity)
    if isinstance(gridsize, (int, np.integer)) and not isinstance(gridsize, (bool, np.bool_)):
        resolved_gridsize: int | tuple[int, int] = int(gridsize)
        w = int(gridsize)
    elif isinstance(gridsize, (tuple, list)) and len(gridsize) == 2:
        if any(
            isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer))
            for value in gridsize
        ):
            raise ValueError("hexbin gridsize dimensions must be integers")
        w, h = int(gridsize[0]), int(gridsize[1])
        resolved_gridsize = (w, h)
        if h < 2:
            raise ValueError("hexbin gridsize dimensions must be >= 2")
        if h > 2048:
            raise ValueError("hexbin gridsize dimensions must be <= 2048")
    else:
        raise ValueError("hexbin gridsize must be a positive integer or (width, height)")
    if w < 2:
        raise ValueError("hexbin gridsize dimensions must be >= 2")
    if w > 2048:
        raise ValueError("hexbin gridsize dimensions must be <= 2048")
    if bins not in {"count", "log"}:
        raise ValueError("hexbin bins must be 'count' or 'log'")
    name = self._optional_text(name, "hexbin name")
    opacity = self._opacity(opacity, "hexbin opacity")
    colormap = channels.resolve_colormap(colormap)
    # Canonicalize WITHOUT ingesting: only occupied bin centers ship, so the
    # raw points must not stay resident in the figure's column store.
    x_all, _x_kind, _x_copies = columns._canonicalize(x)
    y_all, _y_kind, _y_copies = columns._canonicalize(y)
    if len(x_all) != len(y_all):
        raise ValueError(
            f"hexbin x and y must have equal length, got {len(x_all)} and {len(y_all)}"
        )
    n_points = len(x_all)
    c_all = None
    if C is not None:
        c_all, _c_kind, _c_copies = columns._canonicalize(C)
        if len(c_all) != len(x_all):
            raise ValueError("hexbin C must have the same length as x and y")
    authored_range = None
    if range is not None:
        if len(range) != 2:
            raise ValueError("hexbin range must be ((x0, x1), (y0, y1))")
        authored_range = (
            self._finite_increasing_pair(range[0], "hexbin x range"),
            self._finite_increasing_pair(range[1], "hexbin y range"),
        )
    # Matplotlib displays zero-count cells when C is absent and mincnt is not
    # specified, producing the full rectangular honeycomb. Reducer hexbins
    # cannot reduce an empty group and therefore default to one observation.
    threshold = (0 if c_all is None else 1) if mincnt is None else int(mincnt)
    if threshold < 0:
        raise ValueError("hexbin mincnt must be nonnegative")

    native_reduce: str | None
    if c_all is None:
        native_reduce = "count"
    elif reduce_C_function is np.mean or reduce_C_function is np.nanmean:
        native_reduce = "mean"
    elif reduce_C_function is np.sum or reduce_C_function is np.nansum:
        native_reduce = "sum"
    else:
        native_reduce = None

    if native_reduce is not None:
        try:
            centers_x, centers_y, metric, counts, dx, dy = kernels.hexbin(
                x_all,
                y_all,
                gridsize=resolved_gridsize,
                range=authored_range,
                mincnt=threshold,
                C=c_all,
                reduce=native_reduce,
            )
        except ValueError as exc:
            raise ValueError("hexbin x and y must contain at least one finite pair") from exc
        if len(counts) == 0:
            raise ValueError("hexbin range contains no finite points")
    else:
        # Custom reducers: Rust owns domain/aspect/lattice; host only reduces.
        try:
            centers_x, centers_y, counts, starts, lengths, indices, dx, dy = kernels.hexbin_groups(
                x_all,
                y_all,
                gridsize=resolved_gridsize,
                range=authored_range,
                mincnt=threshold,
                C=c_all,
            )
        except ValueError as exc:
            raise ValueError("hexbin x and y must contain at least one finite pair") from exc
        if len(counts) == 0:
            raise ValueError("hexbin range contains no finite points")
        assert c_all is not None
        reduced: list[float] = []
        for start, length in zip(starts, lengths, strict=True):
            values = c_all[indices[int(start) : int(start) + int(length)]]
            made = np.asarray(reduce_C_function(values))
            if made.ndim != 0 or not np.isfinite(made):
                raise ValueError("hexbin reduce_C_function must return one finite scalar per bin")
            reduced.append(float(made))
        metric = np.asarray(reduced, dtype=np.float64)

    if bins == "log":
        # Matplotlib's ``bins="log"`` is LogNorm over the original cell
        # values. Non-positive cells use the bad color (transparent by
        # default), so omitting them is the same static result while keeping
        # the continuous channel finite. The paint channel can remain the
        # engine's linear normalized scalar after applying log here; the
        # original domain is retained separately for count-space colorbars.
        positive = metric > 0.0
        centers_x, centers_y, metric = (
            centers_x[positive],
            centers_y[positive],
            metric[positive],
        )
        if not len(metric):
            raise ValueError("hexbin logarithmic colors require at least one positive cell value")
        colorbar_domain = (float(np.min(metric)), float(np.max(metric)))
        metric = np.log(metric)
    else:
        colorbar_domain = None
    # Constant ``color`` is the Scene-eligible shared-style paint path. Omitted
    # ``color`` keeps the metric colormap; ABI 186 interned those fills onto
    # HexCell PolyFills through a 1×N XYHP plane.
    paint = color if color is not None else metric
    color_ch = channels.resolve_color(
        paint, len(metric), colormap=colormap, default_constant=DEFAULT_PALETTE[0]
    )
    series_color = color if isinstance(color, str) else self.next_series_color()
    checkpoint = self._checkpoint()
    try:
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="hexbin",
                x=self.store.ingest(centers_x),
                y=self.store.ingest(centers_y),
                name=name,
                style={
                    "color": series_color,
                    "opacity": opacity,
                    "hex_dx": dx,
                    "hex_dy": dy,
                    "role": "hexbin",
                    "reduce": native_reduce or "custom",
                    **styles._opacity_channels(css),
                },
                color_ch=color_ch,
                colorbar_domain=colorbar_domain,
                colorbar_scale="log" if bins == "log" else "linear",
                size_ch=channels.SizeChannel(mode="constant", constant=8.0),
                count=int(n_points),
            )
        )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise


def heatmap(
    self: "Figure",
    z: Any,  # 2-D (rows, cols) or RGB(A) ArrayLike, or a DataFrame-like with .to_numpy()
    *,
    x: Optional[ArrayLike] = None,
    y: Optional[ArrayLike] = None,
    name: Optional[str] = None,
    color: Any = None,
    colormap: channels.ColormapLike = channels.DEFAULT_COLORMAP,
    domain: Optional[tuple[float, float]] = None,
    opacity: float = 0.95,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a rectangular heatmap from a 2D value matrix.

    `z` is shaped `(rows, columns)`. Optional `x` and `y` arrays name the
    column/row centers; string/object arrays become categorical axes.
    A literal ``color`` keeps constant paint so regular Cartesian lattices
    can compile onto Scene Rects; omitted ``color`` keeps the metric
    colormap on the compatibility exporters.
    """
    css = styles.compile_mark_style("heatmap", style)
    opacity = css.get("opacity", opacity)
    name = self._optional_text(name, "heatmap name")
    opacity = self._opacity(opacity, "heatmap opacity")
    constant_color = color if isinstance(color, str) else None
    if hasattr(z, "to_numpy"):
        z = z.to_numpy()
    arr = np.asarray(z)
    truecolor = arr.ndim == 3 and arr.shape[-1] in (3, 4)
    if not truecolor and arr.ndim != 2:
        raise ValueError(f"heatmap z must be 2-D or RGB(A), got shape {arr.shape}")
    if truecolor:
        rgba = np.asarray(arr, dtype=np.float64)
        if np.nanmax(rgba[..., :3]) > 1.0:
            rgba[..., :3] /= 255.0
        if rgba.shape[-1] == 3:
            rgba = np.dstack((rgba, np.ones(rgba.shape[:2], dtype=np.float64)))
        rgba = np.clip(rgba, 0.0, 1.0)
        rows, cols = rgba.shape[:2]
        zv = rgba[..., 0]
    else:
        zv = self._real_float_array(arr, "heatmap z")
        rows, cols = zv.shape
    xpos = self._heatmap_axis_positions(x, cols, "x")
    ypos = self._heatmap_axis_positions(y, rows, "y")
    x_edges = self._cell_edges(xpos, "heatmap x")
    y_edges = self._cell_edges(ypos, "heatmap y")
    z_flat = zv.reshape(-1)
    if not truecolor:
        colormap = channels.resolve_colormap(colormap)
    explicit_domain = (
        None
        if truecolor or domain is None
        else self._finite_increasing_pair(domain, "heatmap domain")
    )
    checkpoint = self._checkpoint()
    try:
        self._commit_axis_positions(x, "x")
        self._commit_axis_positions(y, "y")
        grid = (
            self.store.ingest(z_flat)
            if explicit_domain is None
            else self.store.ingest(z_flat, defer_zone_maps=True)
        )
        if truecolor:
            lo, hi = 0.0, 1.0
        elif explicit_domain is None:
            bounds = (grid.min, grid.max)
            lo, hi = self._auto_domain(bounds if np.isfinite(bounds).all() else None)
        else:
            lo, hi = explicit_domain
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="heatmap",
                x=self.store.ingest(np.array([x_edges[0], x_edges[-1]], dtype=np.float64)),
                y=self.store.ingest(np.array([y_edges[0], y_edges[-1]], dtype=np.float64)),
                grid=grid,
                rgba_grid=(
                    (
                        # `grid` already holds this plane: `z_flat` is
                        # `rgba[..., 0].reshape(-1)`, and re-ingesting the
                        # expression built a second contiguous copy (the source
                        # is a strided view, so each reshape materializes one)
                        # that the store kept for the figure's lifetime — 8
                        # bytes per pixel of pure duplicate.
                        grid,
                        self.store.ingest(rgba[..., 1].reshape(-1)),
                        self.store.ingest(rgba[..., 2].reshape(-1)),
                        self.store.ingest(rgba[..., 3].reshape(-1)),
                    )
                    if truecolor
                    else None
                ),
                grid_shape=(rows, cols),
                count=int(z_flat.size),
                name=name,
                style={
                    "color": (
                        constant_color if constant_color is not None else self.next_series_color()
                    ),
                    "opacity": opacity,
                    "role": "heatmap",
                    "domain": [lo, hi],
                    "x_range": [float(x_edges[0]), float(x_edges[-1])],
                    "y_range": [float(y_edges[0]), float(y_edges[-1])],
                    **(
                        {}
                        if constant_color is not None and not truecolor
                        else {"colormap": colormap, "truecolor": truecolor}
                    ),
                    **styles._opacity_channels(css),
                },
            )
        )
    except Exception:
        self._rollback(checkpoint)
        raise
    return self
