"""Sankey mark — Rust layout + ribbon composition + optional labels."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Optional

from . import styles

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
