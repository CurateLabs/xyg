"""Static SVG/PNG export of composed graph charts (#34).

The browser paints a composed graph from resolved per-item planes (node and
edge paint, semantic halo/body/dash layers, border-trimmed edges and filled
arrowheads, compound frames, the zoom-threshold label plan, and an explicit
legend). For export, the figure route first builds the plain graph Scene (so
its layout, scales, and chrome stay authoritative); Rust then rebuilds that
Scene from the same planes (``xyg_graph_composed_scene``). This module only
reads the planes off the traces and strips them for the plain pass.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from . import channels
from ._marks_style import SYMBOL_CODES

#: Style channels the plain Scene route admits on graph traces.
_PLAIN_CHANNELS = ("edge_ends",)


def _rgba_rows(fig: Any, ch: Any, n: int, fallback: str) -> np.ndarray:
    """Per-item straight RGBA8 of a resolved color channel (Rust color math)."""
    from . import _native

    if ch is None or ch.mode == "constant":
        css = (ch.constant if ch is not None else None) or fallback
        return np.tile(np.asarray(_native.css_color_rgba(css), dtype=np.uint8), (n, 1))
    if ch.mode == "direct_rgba":
        return np.rint(np.asarray(ch.rgba, dtype=np.float64).reshape(n, 4) * 255.0).astype(np.uint8)
    if ch.mode == "categorical":
        palette = ch.colors if ch.palette is None else ch.palette
        colors = [palette[i % len(palette)] for i in range(len(ch.categories or ()))]
        table = np.asarray([_native.css_color_rgba(c) for c in colors], dtype=np.uint8)
        return table[np.asarray(ch.codes, dtype=np.intp)]
    if ch.mode == "continuous":
        lo, hi = ch.domain
        values = np.asarray(ch.values, dtype=np.float64)
        unit = np.clip((values - lo) / (hi - lo), 0.0, 1.0) if hi > lo else np.zeros(n)
        colormap = channels.resolve_colormap(ch.colormap)
        stops = (
            _native.colormap_stops(colormap)
            if isinstance(colormap, str)
            else np.asarray(colormap, dtype=np.uint8)
        )
        return _native.colormap_rgba(unit, n, 1, stops, 255).reshape(n, 4)
    raise ValueError(f"unsupported graph color channel {ch.mode!r}")


def _style_value(trace: Any, name: str, default: float, n: int) -> np.ndarray:
    channel = trace.style_channels.get(name)
    if channel is not None:
        return np.asarray(channel.values, dtype=np.float64).reshape(n)
    return np.full(n, float(trace.style.get(name, default)))


def _optional(trace: Any, name: str, dtype: Any) -> Optional[np.ndarray]:
    channel = trace.style_channels.get(name)
    return None if channel is None else np.asarray(channel.values, dtype=dtype)


def composed_graph_planes(fig: Any) -> Optional[dict[str, Any]]:
    """Read one graph's composed planes off a graph-only figure, or None."""
    from . import _native
    from ._scene_marshal import _graph_marks_only

    metas = getattr(fig, "_graph_meta", None) or []
    if len(metas) != 1 or not _graph_marks_only(fig):
        return None
    meta = metas[0]
    node = fig.traces[meta["node_trace"]]
    edge = fig.traces[meta["edge_trace"]]
    n = len(node.x.values)
    m = len(edge.x0.values)
    # Node paint as the browser resolves it.
    fill = _rgba_rows(fig, node.color_ch, n, fig.palette_color(node.id))
    stroke_ch = getattr(node, "stroke_ch", None)
    if stroke_ch is not None and stroke_ch.mode == "direct_rgba":
        stroke = _rgba_rows(fig, stroke_ch, n, "#000000")
    elif node.style.get("stroke"):
        stroke = _rgba_rows(
            fig, channels.ColorChannel(mode="constant", constant=node.style["stroke"]), n, "#000000"
        )
    else:
        stroke = np.zeros((n, 4), dtype=np.uint8)
    size = node.size_ch
    if size is not None and size.mode == "continuous" and size.values is not None:
        lo, hi = size.range_px
        d0, d1 = size.domain
        unit = np.clip((np.asarray(size.values) - d0) / (d1 - d0), 0.0, 1.0) if d1 > d0 else 0.0
        diameter = lo + (hi - lo) * unit
    else:
        diameter = np.full(
            n, float(size.constant if size is not None and size.constant is not None else 8.0)
        )
    symbol_channel = node.style_channels.get("symbol")
    symbol = (
        np.asarray(symbol_channel.values, dtype=np.uint8)
        if symbol_channel is not None
        else np.full(
            n, SYMBOL_CODES.get(str(node.style.get("symbol", "circle")), 0), dtype=np.uint8
        )
    )
    stroke_width = _style_value(node, "stroke_width", 1.0 if stroke.any() else 0.0, n)
    planes: dict[str, Any] = {
        "x": node.x.values,
        "y": node.y.values,
        "fill": fill,
        "stroke": stroke,
        "stroke_width": stroke_width,
        "diameter": diameter,
        "symbol": symbol,
        "opacity": _style_value(node, "opacity", 1.0, n),
        "x0": edge.x0.values,
        "y0": edge.y0.values,
        "x1": edge.x1.values,
        "y1": edge.y1.values,
        "segment_rgba": _rgba_rows(
            fig,
            edge.color_ch,
            m,
            str(edge.style.get("color") or _native.graph_default_edge_color()),
        ),
        "segment_width": _style_value(edge, "width", 1.2, m),
        "segment_opacity": _style_value(edge, "opacity", 1.0, m),
    }
    for key, trace, name, dtype in (
        ("halo", node, "halo_rgba", np.uint8),
        ("halo_diameter", node, "halo_size", np.float64),
        ("frames", node, "compound_frame", np.float64),
        ("node_label_plan", node, "label_plan", np.float64),
        ("segment_halo", edge, "halo_rgba", np.uint8),
        ("segment_halo_width", edge, "halo_width", np.float64),
        ("segment_body", edge, "body_rgba", np.uint8),
        ("segment_body_width", edge, "body_width", np.float64),
        ("segment_dash", edge, "edge_dash", np.float64),
        ("edge_ends", edge, "edge_ends", np.float64),
        ("segment_label_plan", edge, "label_plan", np.float64),
    ):
        value = _optional(trace, name, dtype)
        if value is not None:
            planes[key] = value
    if "node_label_plan" in planes:
        planes["node_labels"] = [
            None if label is None else str(label) for label in meta.get("node_labels", [None] * n)
        ]
    if "segment_label_plan" in planes:
        texts: list[Optional[str]] = [None] * m
        for segment, text in zip(
            meta.get("edge_label_segments", []), meta.get("edge_label_text", []), strict=True
        ):
            texts[int(segment)] = text
        planes["segment_labels"] = texts
    # Labels and legend text paint in the chart text color, like the
    # browser's theme label (`--chart-text`).
    text = (getattr(fig, "style", None) or {}).get("--chart-text")
    if text:
        planes["text_rgba"] = np.asarray(_native.css_color_rgba(str(text)), dtype=np.uint8)
    items = (fig.legend_options or {}).get("items") or []
    if items and fig.show_legend:
        planes["legend_title"] = str(fig.legend_options.get("title") or "")
        # Rust resolves the placement name; unknown names fail closed.
        planes["legend_loc"] = str(fig.legend_options.get("loc") or "")
        planes["legend"] = [
            (
                str(item.get("name", "")),
                _native.css_color_rgba(str((item.get("style") or {}).get("color") or "#000000")),
                SYMBOL_CODES.get(str((item.get("style") or {}).get("symbol", "circle")), 0),
            )
            for item in items
        ]
    return planes


def strip_to_plain(fig: Any) -> None:
    """Make a projected graph figure's traces plain for the base Scene pass:
    solid paint, no per-item channels, no explicit legend (the rebuild owns
    them)."""
    meta = fig._graph_meta[0]
    for index in (meta["node_trace"], meta["edge_trace"]):
        trace = fig.traces[index]
        trace.style_channels = {
            name: value for name, value in trace.style_channels.items() if name in _PLAIN_CHANNELS
        }
        trace.color_ch = channels.ColorChannel(mode="constant", constant="#888888")
        if hasattr(trace, "stroke_ch"):
            trace.stroke_ch = None
        if index == meta["node_trace"]:
            trace.size_ch = channels.SizeChannel(mode="constant", constant=8.0)
            trace.style = {
                k: v
                for k, v in trace.style.items()
                if k not in ("stroke", "stroke_width", "symbol")
            }
    edge = fig.traces[meta["edge_trace"]]
    if len(edge.x0.values) == 0:
        # The Scene admits no empty trace; an edgeless graph's base pass is
        # its nodes alone (edges never widen the node autorange).
        del fig.traces[meta["edge_trace"]]
        meta["node_trace"] -= int(meta["node_trace"] > meta["edge_trace"])
        meta["edge_trace"] = None
    if (fig.legend_options or {}).get("items"):
        fig.legend_options = {
            k: v for k, v in fig.legend_options.items() if k not in ("items", "title")
        }
        fig.show_legend = False
