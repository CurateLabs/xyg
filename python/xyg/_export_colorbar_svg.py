"""Shared static-export colorbar SVG emit helpers."""

from __future__ import annotations

import hashlib
from itertools import pairwise
from typing import Any, Optional

import numpy as np

from ._export_chrome import (
    _TEXT,
    COLORBAR_FONT_SIZE,
    _colorbar_tick_target,
    slot_font_size,
    slot_text_color,
)
from ._export_svg_util import _num, escape, slot_text_attrs
from ._export_ticks import _fmt_log, axis_ticks
from ._paint import _css
from ._paint import colormap_lut as _lut
from ._paint import colormap_stops as _colormap_stops


def _colormap_key(colormap: Any) -> str:
    """A stable, document-unique id fragment for a colormap — a built-in name,
    or the digest of a custom ramp's stops (two colorbars in one document must
    not share a `<linearGradient>` id unless they are the same ramp)."""
    if isinstance(colormap, str):
        return colormap
    return "custom-" + hashlib.sha256(repr(_colormap_stops(colormap)).encode()).hexdigest()[:12]


def _colorbar_body(
    options: dict,
    x: float,
    y: float,
    width: float,
    height: float,
    orientation: str,
    gradient_id: str,
    text_color: str,
) -> str:
    """Colorbar bar fill: a smooth gradient, or N solid bands for a discrete
    (resampled) colormap so it reads like Matplotlib's segmented colorbar."""
    if options.get("line_only"):
        return (
            f'<rect data-xy-colorbar-line-only="true" x="{_num(x)}" y="{_num(y)}" '
            f'width="{_num(width)}" height="{_num(height)}" fill="white" '
            f'stroke="{escape(text_color)}" stroke-width="1"/>'
        )
    levels = options.get("levels")
    if not levels or int(levels) < 1:
        return (
            f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" '
            f'height="{_num(height)}" fill="url(#{gradient_id})"/>'
        )
    n = int(levels)
    exact_colors = options.get("band_colors")
    if isinstance(exact_colors, list) and len(exact_colors) == n:
        colors = np.asarray(exact_colors, dtype=np.uint8)
    else:
        cmap = options.get("colormap", "viridis")
        positions = (np.arange(n, dtype=np.float64) + 0.5) / n
        colors = _lut(cmap, positions)
    fractions = np.linspace(0.0, 1.0, n + 1)
    boundaries = np.asarray(options.get("boundaries", []), dtype=np.float64).reshape(-1)
    if (
        options.get("spacing") == "proportional"
        and len(boundaries) == n + 1
        and np.isfinite(boundaries).all()
        and boundaries[-1] > boundaries[0]
        and np.all(np.diff(boundaries) > 0.0)
    ):
        fractions = (boundaries - boundaries[0]) / (boundaries[-1] - boundaries[0])
    rects = []
    for index, (r, g, b) in enumerate(colors):
        lower, upper = float(fractions[index]), float(fractions[index + 1])
        if orientation == "horizontal":
            bx0 = x + width * lower
            bx1 = x + width * upper
            rects.append(
                f'<rect x="{_num(bx0)}" y="{_num(y)}" width="{_num(bx1 - bx0 + 0.5)}" '
                f'height="{_num(height)}" fill="rgb({int(r)},{int(g)},{int(b)})"/>'
            )
        else:
            by0 = y + height * (1.0 - upper)
            by1 = y + height * (1.0 - lower)
            rects.append(
                f'<rect x="{_num(x)}" y="{_num(by0)}" width="{_num(width)}" '
                f'height="{_num(by1 - by0 + 0.5)}" fill="rgb({int(r)},{int(g)},{int(b)})"/>'
            )
    return "".join(rects)


def _colorbar(
    options: dict,
    plot: dict,
    right_axis_room: float = 0.0,
    text_color: str = _TEXT,
    title_slot: Optional[dict[str, Any]] = None,
    tick_slot: Optional[dict[str, Any]] = None,
) -> str:
    title_slot = title_slot or {}
    tick_slot = tick_slot or {}
    # The `colorbar` slot's stylesheet rule is `font-size:10px`, and the raster
    # writer passes 10 explicitly. The SVG writer used to emit no size at all
    # and inherit the root <svg>'s 11px, which made it the odd renderer out on
    # every unstyled colorbar. Name the size instead of inheriting it.
    title_attrs = (
        f' font-size="{_num(slot_font_size(title_slot, COLORBAR_FONT_SIZE))}"'
        + slot_text_attrs(title_slot)
    )
    title_paint = escape(slot_text_color(title_slot, text_color))
    tick_attrs = (
        f' font-size="{_num(slot_font_size(tick_slot, COLORBAR_FONT_SIZE))}"'
        + slot_text_attrs(tick_slot)
    )
    tick_paint = escape(slot_text_color(tick_slot, text_color))
    cmap = options.get("colormap", "viridis")
    gradient_id = f"xy-colorbar-{_colormap_key(cmap)}"
    stops = _colormap_stops(cmap)
    stop_nodes = "".join(
        f'<stop offset="{100 * index / max(1, len(stops) - 1):.2f}%" '
        f'stop-color="rgb({r},{g},{b})"/>'
        for index, (r, g, b) in enumerate(stops)
    )
    orientation = options.get("orientation", "vertical")
    shrink = float(options.get("shrink", 1.0))
    anchor = options.get("anchor") or [0.5, 0.5]
    domain = options.get("domain", [0.0, 1.0])
    placement = options.get("placement")
    if placement == "axes":
        x, y, width, height = plot["x"], plot["y"], plot["w"], plot["h"]
        gradient_attrs = (
            'x1="0" y1="0" x2="100%" y2="0"'
            if orientation == "horizontal"
            else 'x1="0" y1="100%" x2="0" y2="0"'
        )
    elif orientation == "horizontal":
        width = plot["w"] * shrink
        x = plot["x"] + (plot["w"] - width) * float(anchor[0])
        gap = (
            float(options["pad"]) * plot["h"]
            if options.get("pad") is not None
            else (plot["bottom_axis_room"] or 10)
        )
        y = plot["y"] + plot["h"] + gap
        height = 18
        gradient_attrs = 'x1="0" y1="0" x2="100%" y2="0"'
    else:
        # right_axis_room shifts the whole colorbar clear of right-side named
        # y-axis chrome (layout() reserves room for both additively).
        gap = float(options["pad"]) * plot["w"] if options.get("pad") is not None else 24.0
        x = plot["x"] + plot["w"] + right_axis_room + gap
        height = plot["h"] * shrink
        y = plot["y"] + (plot["h"] - height) * (1.0 - float(anchor[1]))
        width = 18
        gradient_attrs = 'x1="0" y1="100%" x2="0" y2="0"'
    label = str(options.get("label") or "")
    label_node = (
        f'<text x="{_num(x + width + 38)}" y="{_num(y + height / 2)}" '
        f'text-anchor="middle" transform="rotate(-90 {_num(x + width + 38)} '
        f'{_num(y + height / 2)})"{title_attrs} fill="{title_paint}">{escape(label)}</text>'
        if label and orientation != "horizontal"
        else (
            f'<text x="{_num(x + width / 2)}" y="{_num(y + height + 22)}" '
            f'text-anchor="middle"{title_attrs} fill="{title_paint}">{escape(label)}</text>'
            if label
            else ""
        )
    )
    lo, hi = float(domain[0]), float(domain[1])
    log_scale = options.get("scale") == "log"

    def fraction(value: float) -> float:
        if log_scale:
            return np.log(value / lo) / np.log(hi / lo) if hi != lo else 0.0
        return (value - lo) / ((hi - lo) or 1.0)

    ticks = options.get("ticks")
    supplied_labels = options.get("tick_labels")
    paired_labels = (
        supplied_labels
        if isinstance(supplied_labels, list)
        and isinstance(ticks, list)
        and len(supplied_labels) == len(ticks)
        else None
    )
    if ticks is not None:
        tick_pairs = [
            (
                float(value),
                None if paired_labels is None else str(paired_labels[index]),
            )
            for index, value in enumerate(ticks)
            if lo <= float(value) <= hi
        ]
    else:
        tick_length = width if orientation == "horizontal" else height
        automatic = axis_ticks(
            {
                "kind": "log" if log_scale else "linear",
                "range": [lo, hi],
                "tick_count": _colorbar_tick_target(tick_length),
            },
            tick_length,
            orientation == "horizontal",
        )
        automatic_positions = (automatic[1] if log_scale else automatic[0]) or [lo, hi]
        tick_pairs = [(float(value), None) for value in automatic_positions]
    tick_positions = [value for value, _label in tick_pairs]
    format_tick = _fmt_log if log_scale else lambda value: f"{value:g}"
    tick_nodes = (
        "".join(
            f'<text x="{_num(x + width + 4)}" '
            f'y="{_num(y + height * (1 - fraction(value)) + 4)}" '
            f'{tick_attrs} fill="{tick_paint}">'
            f"{escape(label if label is not None else format_tick(value))}</text>"
            for value, label in tick_pairs
        )
        if orientation != "horizontal"
        else "".join(
            f'<text x="{_num(x + width * fraction(value))}" '
            f'y="{_num(y + height + 12)}" text-anchor="middle" '
            f'{tick_attrs} fill="{tick_paint}">'
            f"{escape(label if label is not None else format_tick(value))}</text>"
            for value, label in tick_pairs
        )
    )
    minor_nodes = ""
    if options.get("minor_ticks") and len(tick_positions) >= 2:
        ordered = sorted(set(tick_positions))
        minor_positions = (
            [
                10 ** (np.log10(left) + (np.log10(right) - np.log10(left)) * step / 5.0)
                for left, right in pairwise(ordered)
                for step in range(1, 5)
            ]
            if log_scale
            else [
                left + (right - left) * step / 5.0
                for left, right in pairwise(ordered)
                for step in range(1, 5)
            ]
        )
        if orientation != "horizontal":
            minor_nodes = "".join(
                f'<line data-xy-colorbar-minor="true" x1="{_num(x + width)}" '
                f'x2="{_num(x + width + 3)}" '
                f'y1="{_num(y + height * (1 - fraction(value)))}" '
                f'y2="{_num(y + height * (1 - fraction(value)))}" '
                f'stroke="{escape(text_color)}"/>'
                for value in minor_positions
            )
        else:
            minor_nodes = "".join(
                f'<line data-xy-colorbar-minor="true" '
                f'x1="{_num(x + width * fraction(value))}" '
                f'x2="{_num(x + width * fraction(value))}" '
                f'y1="{_num(y + height)}" y2="{_num(y + height + 3)}" '
                f'stroke="{escape(text_color)}"/>'
                for value in minor_positions
            )
    extend = options.get("extend")
    extend_nodes = ""
    line_only = bool(options.get("line_only"))
    if extend in ("max", "both"):
        r, g, b = options.get("over_color", stops[-1])
        points = (
            f"{_num(x)},{_num(y)} {_num(x + width)},{_num(y)} {_num(x + width / 2)},{_num(y - 9)}"
            if orientation != "horizontal"
            else f"{_num(x + width)},{_num(y)} {_num(x + width)},{_num(y + height)} "
            f"{_num(x + width + 9)},{_num(y + height / 2)}"
        )
        extend_nodes += (
            f'<polygon points="{points}" fill="white" stroke="{escape(text_color)}"/>'
            if line_only
            else f'<polygon points="{points}" fill="rgb({r},{g},{b})"/>'
        )
    if extend in ("min", "both"):
        r, g, b = options.get("under_color", stops[0])
        points = (
            f"{_num(x)},{_num(y + height)} {_num(x + width)},{_num(y + height)} "
            f"{_num(x + width / 2)},{_num(y + height + 9)}"
            if orientation != "horizontal"
            else f"{_num(x)},{_num(y)} {_num(x)},{_num(y + height)} "
            f"{_num(x - 9)},{_num(y + height / 2)}"
        )
        extend_nodes += (
            f'<polygon points="{points}" fill="white" stroke="{escape(text_color)}"/>'
            if line_only
            else f'<polygon points="{points}" fill="rgb({r},{g},{b})"/>'
        )
    line_nodes = ""
    for line in options.get("lines") or []:
        value = float(line.get("value", np.nan))
        if not np.isfinite(value) or value < min(lo, hi) or value > max(lo, hi):
            continue
        line_fraction = fraction(value)
        color = escape(_css(line.get("color"), text_color))
        line_width = _num(max(0.5, float(line.get("width", 1.0))))
        dash = (
            f' stroke-dasharray="{_num(3.7 * float(line_width))} {_num(1.6 * float(line_width))}"'
            if line.get("dash") == "dashed"
            else ""
        )
        if orientation == "horizontal":
            position = x + width * line_fraction
            line_nodes += (
                f'<line data-xy-colorbar-line="true" x1="{_num(position)}" '
                f'x2="{_num(position)}" y1="{_num(y)}" y2="{_num(y + height)}" '
                f'stroke="{color}" stroke-width="{line_width}"{dash}/>'
            )
        else:
            position = y + height * (1.0 - line_fraction)
            line_nodes += (
                f'<line data-xy-colorbar-line="true" x1="{_num(x)}" '
                f'x2="{_num(x + width)}" y1="{_num(position)}" y2="{_num(position)}" '
                f'stroke="{color}" stroke-width="{line_width}"{dash}/>'
            )
    return (
        f'<defs><linearGradient id="{gradient_id}" {gradient_attrs}>'
        f"{stop_nodes}</linearGradient></defs>"
        f"{_colorbar_body(options, x, y, width, height, orientation, gradient_id, text_color)}"
        f"{line_nodes}{extend_nodes}{minor_nodes}{tick_nodes}{label_node}"
    )
