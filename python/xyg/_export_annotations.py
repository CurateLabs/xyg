"""Shared static-export annotation placement and axis-title geometry."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional, cast

import numpy as np

from ._export_layout import _y_title_baseline

if TYPE_CHECKING:
    from ._layout import _PolarProjection


def _axis_label_geometry(
    axis: dict[str, Any],
    plot: dict[str, float],
    *,
    is_x: bool,
) -> dict[str, Any]:
    """Resolve named axis-title placement shared by SVG and native output.

    Named positions, offsets, and angles mirror ChartView. Structured CSS
    dictionaries remain a browser-only escape hatch because native exporters
    do not have a CSS layout engine.
    """
    style = axis.get("style") or {}
    font_size = float(style.get("label_size", 12))
    raw_position = axis.get("label_position")
    position = raw_position if isinstance(raw_position, str) else "center"
    position = position.replace("-", "_")
    inside = position.startswith("inside_")
    anchor = position.removeprefix("inside_") if inside else position
    anchor_fraction = 0.0 if anchor == "start" else 1.0 if anchor == "end" else 0.5
    offset = float(axis.get("label_offset", 0.0))
    side = axis.get("side", "bottom" if is_x else "left")

    if is_x:
        x = plot["x"] + plot["w"] * anchor_fraction
        outside_top = plot["y"] - 34
        outside_bottom = plot["y"] + plot["h"] + 24
        inside_top = plot["y"] + 12
        inside_bottom = plot["y"] + plot["h"] - 12
        y = (
            (inside_top if side == "top" else inside_bottom)
            if inside
            else (outside_top if side == "top" else outside_bottom)
        )
        y += (
            (-offset if not inside else offset)
            if side == "top"
            else (offset if not inside else -offset)
        )
        # DOM labels use top positioning; static text commands use a baseline.
        y += font_size * 0.82
        text_anchor = "start" if anchor == "start" else "end" if anchor == "end" else "middle"
        angle = float(axis.get("label_angle", 0.0))
    else:
        if inside:
            inside_x = plot["x"] + plot["w"] - 12 if side == "right" else plot["x"] + 12
            x = inside_x + (-offset if side == "right" else offset)
        else:
            # The rotated title's *line box* is centered on ChartView's inset
            # (`left:10px` / `plot-right+40px`); a static exporter emits a
            # baseline. `_y_title_baseline` applies that half-line-box
            # correction and the axis's own `label_offset`, and is the same
            # function `layout()` reserves the gutter from.
            baseline = _y_title_baseline(axis, plot)
            x = (
                baseline
                if baseline is not None
                else (plot["x"] + plot["w"] + 40 + offset if side == "right" else 10 - offset)
            )
        y = plot["y"] + plot["h"] * (1.0 - anchor_fraction)
        text_anchor = "middle"
        angle = float(axis.get("label_angle", 90.0 if side == "right" else -90.0))

    return {
        "x": x,
        "y": y,
        "anchor": text_anchor,
        "angle": angle,
        "font_size": font_size,
    }


def annotation_label_placement(
    ann: dict[str, Any],
    style: dict[str, Any],
    sx: Callable[[float], float],
    sy: Callable[[float], float],
    plot: dict[str, float],
    width: float,
    height: float,
    polar: Optional[_PolarProjection] = None,
) -> tuple[float, float, Optional[str], Optional[str]]:
    """Where an annotation's `text=` hangs, as `(x, y, anchor, vertical_align)`.

    Ported from `_drawAnnotationLabels` (js/src/51_annotations.ts) and shared by
    both static exporters, which previously drew labels for `text`/`callout`
    only — a `hline(text="target")` was silently label-less in every SVG, PNG
    and PDF while the browser drew it.

    Rules and bands carry no anchor of their own, so the returned defaults are
    the ones that keep the badge inside the plot rect."""
    px0, py0 = plot["x"], plot["y"]
    kind = ann.get("kind")
    anchor = ann.get("anchor")
    vertical_align = style.get("vertical_align")
    if kind in ("rule", "band"):
        if ann.get("axis") == "x":
            if kind == "rule":
                x = float(sx(float(ann["value"])))
            else:
                x = (float(sx(float(ann["start"]))) + float(sx(float(ann["end"])))) / 2
                anchor = anchor or "middle"
            return x, py0 + 6.0, anchor, vertical_align or "top"
        x = px0 + plot["w"] - 6.0
        if kind == "rule":
            y = float(sy(float(ann["value"])))
        else:
            y = (float(sy(float(ann["start"]))) + float(sy(float(ann["end"])))) / 2
            vertical_align = vertical_align or "middle"
        return x, y, anchor or "end", vertical_align
    if kind == "arrow":
        if polar is not None:
            x0, y0 = polar(float(ann["x0"]), float(ann["y0"]))
            x1, y1 = polar(float(ann["x1"]), float(ann["y1"]))
            x = (float(x0) + float(x1)) / 2
            y = (float(y0) + float(y1)) / 2
        else:
            x = (float(sx(float(ann["x0"]))) + float(sx(float(ann["x1"])))) / 2
            y = (float(sy(float(ann["y0"]))) + float(sy(float(ann["y1"])))) / 2
        return x, y, anchor or "middle", vertical_align or "middle"
    if kind == "marker":
        if polar is not None:
            # (theta, r) projects jointly; the separable pair would read the
            # disc centre (r = 0, any angle) as the bottom-left corner.
            ax, ay = polar(float(ann["x"]), float(ann["y"]))
            return float(ax), float(ay), anchor, vertical_align
        return float(sx(float(ann["x"]))), float(sy(float(ann["y"]))), anchor, vertical_align
    x, y = float(ann.get("x", 0.0)), float(ann.get("y", 0.0))
    space = style.get("coordinate_space")
    if space == "axes_fraction":
        return px0 + x * plot["w"], py0 + (1.0 - y) * plot["h"], anchor, vertical_align
    if space == "figure_fraction":
        return x * width, (1.0 - y) * height, anchor, vertical_align
    if space == "yaxis_transform":
        return px0 + x * plot["w"], float(sy(y)), anchor, vertical_align
    if space == "xaxis_transform":
        return float(sx(x)), py0 + (1.0 - y) * plot["h"], anchor, vertical_align
    if polar is not None:
        # Data-space (theta, r) projects jointly; the separable pair would read
        # the disc centre (r = 0, at any angle) as the bottom-left corner. The
        # fraction-space branches above are already renderer-neutral.
        ax, ay = polar(x, y)
        return float(ax), float(ay), anchor, vertical_align
    return float(sx(x)), float(sy(y)), anchor, vertical_align


def _annotation_first_baseline(
    anchor_y: float,
    line_count: int,
    line_height: float,
    font_size: float,
    vertical_align: Any,
) -> float:
    """Approximate Matplotlib's multiline vertical-alignment box.

    Matplotlib aligns ``top`` and ``bottom`` against the full multiline text
    extent, not against a block that has first been centered on the anchor.
    Its default ``baseline`` alignment pins the final line's baseline at the
    supplied position, so preceding lines grow upward from that anchor.
    With screen-space y increasing downwards, the first baseline therefore
    sits one ascent below a top anchor, or all later baselines plus one descent
    above a bottom anchor.  Center retains the established exporter
    approximation.
    """
    line_span = max(0, int(line_count) - 1) * line_height
    if vertical_align == "top":
        return anchor_y + font_size * 0.8
    if vertical_align == "bottom":
        return anchor_y - line_span - font_size * 0.2
    if vertical_align in (None, "", "baseline"):
        return anchor_y - line_span
    first_baseline = anchor_y - line_span / 2
    if vertical_align in ("center", "middle"):
        first_baseline += font_size * 0.35
    return first_baseline


def _annotation_connector_unclipped(
    ann: dict[str, Any],
    sx: Callable[[float], float],
    sy: Callable[[float], float],
    plot: dict[str, float],
    polar: Optional[_PolarProjection] = None,
) -> bool:
    """Whether an arrow may leave the axes because its target is in bounds.

    Matplotlib's default ``annotation_clip=None`` clips based on the annotated
    point, not the text/connector path.  A label may therefore sit outside the
    axes while its connector remains visible back to an in-bounds target.
    """
    kind = ann.get("kind")
    if kind == "arrow":
        target = ann.get("x1"), ann.get("y1")
    elif kind == "callout":
        target = ann.get("x"), ann.get("y")
    else:
        return False
    try:
        x, y = float(cast(Any, target[0])), float(cast(Any, target[1]))
        if polar is not None:
            if not bool(polar.position_mask(x, y)):
                return False
            px, py = polar(x, y)
            px, py = float(px), float(py)
        else:
            px, py = float(sx(x)), float(sy(y))
    except (TypeError, ValueError):
        return False
    return (
        np.isfinite(px)
        and np.isfinite(py)
        and plot["x"] <= px <= plot["x"] + plot["w"]
        and plot["y"] <= py <= plot["y"] + plot["h"]
    )
