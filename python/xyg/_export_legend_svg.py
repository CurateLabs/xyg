"""Shared static-export legend SVG emit helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from ._export_chrome import _TEXT, slot_text_color
from ._export_legend import _legend_layout
from ._export_svg_util import (
    _dash_attr,
    _num,
    _slot_size_attr,
    escape,
    slot_text_attrs,
)
from ._paint import _css
from .config import DEFAULT_PALETTE

# Trace kinds whose legend entry is a short line sample rather than a marker
# glyph or filled patch (mirrors _raster._LEGEND_LINE_KINDS).
_LEGEND_LINE_KINDS = frozenset({"line", "segments", "step", "stairs", "errorbar"})


def _legend_marker_svg(style: dict[str, Any], x: float, y: float, default_color: str) -> str:
    """Render one Matplotlib legend marker at the center of its line handle."""
    from . import _svg as _svg_module

    symbol = str(style.get("symbol", "circle"))
    builder = _svg_module._SYMBOL_BUILDERS.get(symbol)
    marker_path = style.get("marker_path")
    marker_glyph = style.get("marker_glyph")
    radius = max(0.5, float(style.get("size", 8.0)) / 2.0)
    color = _css(style.get("color"), default_color)
    stroke_w = float(style.get("stroke_width", 0.0))
    line_symbol = symbol in {
        "plus_line",
        "x_line",
        "horizontal_line",
        "vertical_line",
    } or (bool(marker_path) and not bool(marker_path.get("filled", True)))
    if line_symbol and stroke_w <= 0:
        stroke_w = 1.0
    stroke = _css(style.get("stroke"), color) if stroke_w or line_symbol else None
    stroke_attr = f' stroke="{escape(stroke)}" stroke-width="{_num(stroke_w)}"' if stroke else ""
    if marker_glyph:
        return (
            f'<text x="{_num(x)}" y="{_num(y)}" '
            f'font-family="DejaVu Sans" font-size="{_num(2 * radius)}" '
            f'text-anchor="middle" dominant-baseline="central" '
            f'fill="{escape(color)}"{stroke_attr}>{escape(str(marker_glyph))}</text>'
        )
    if marker_path:
        d = _svg_module._authored_marker_path_d(marker_path, float(x), float(y), 2 * radius)
        fill = escape(color) if bool(marker_path.get("filled", True)) else "none"
        return f'<path d="{d}" fill="{fill}"{stroke_attr}/>'
    if builder is None:
        return (
            f'<circle cx="{_num(x)}" cy="{_num(y)}" r="{_num(radius)}" '
            f'fill="{escape(color)}"{stroke_attr}/>'
        )
    return builder(float(x), float(y), radius) + f' fill="{escape(color)}"{stroke_attr}/>'


def _legend_hatch_svg(x0: float, x1: float, y0: float, y1: float, hatch: str, color: str) -> str:
    """Small, bounded hatch sample for explicit patch legend handles."""
    from . import _svg as _svg_module

    paths: list[str] = []
    shapes: list[str] = []
    mid_y = (y0 + y1) / 2
    if "-" in hatch:
        paths.append(f"M{_num(x0)},{_num(mid_y)} L{_num(x1)},{_num(mid_y)}")
    for char, direction in (("/", 1), ("\\", -1)):
        count = min(3, hatch.count(char))
        for index in range(count):
            center = x0 + (index + 1) * (x1 - x0) / (count + 1)
            half = min((x1 - x0) / 4, (y1 - y0) / 2)
            paths.append(
                f"M{_num(center - half)},{_num(mid_y + direction * half)} "
                f"L{_num(center + half)},{_num(mid_y - direction * half)}"
            )
    if "." in hatch:
        radius = min(1.1, (y1 - y0) * 0.09)
        for fraction in (0.3, 0.7):
            shapes.append(
                f'<circle cx="{_num(x0 + fraction * (x1 - x0))}" cy="{_num(mid_y)}" '
                f'r="{_num(radius)}" fill="{escape(color)}"/>'
            )
    if "*" in hatch:
        radius = min(x1 - x0, y1 - y0) * 0.28
        shapes.append(
            _svg_module._star_path((x0 + x1) / 2, mid_y, radius, 5, 0.45, -90.0)
            + f' fill="{escape(color)}"/>'
        )
    if paths:
        shapes.insert(
            0,
            f'<path d="{" ".join(paths)}" fill="none" stroke="{escape(color)}" stroke-width="1"/>',
        )
    return "".join(shapes)


def _legend(
    named: list[dict],
    plot: dict,
    options: dict,
    clip_id: str,
    text_color: str = _TEXT,
    palette: Sequence[str] = DEFAULT_PALETTE,
    label_slot: Optional[dict[str, Any]] = None,
    title_slot: Optional[dict[str, Any]] = None,
) -> str:
    label_slot = label_slot or {}
    title_slot = title_slot or {}
    legend = _legend_layout(named, plot, options)
    if not legend["visible_count"]:
        # A plot too short for even one entry: no floating frame/title either.
        return ""
    rows = []
    style_opts = legend["style"]
    pad, handle, gap = legend["pad"], legend["handle"], legend["gap"]
    line_h, ncols = legend["line_h"], legend["ncols"]
    swatch_h = legend["swatch_h"]
    title, title_h = legend["title"], legend["title_h"]
    font_size, text_h = legend["font_size"], legend["text_h"]
    column_offsets = legend["column_offsets"]
    box_w, box_h = legend["box_w"], legend["box_h"]
    x, y = legend["x"], legend["y"]
    if style_opts.get("background") != "transparent":
        if style_opts.get("boxShadow"):
            rows.append(
                f'<rect x="{_num(x + 2)}" y="{_num(y + 2)}" width="{_num(box_w)}" '
                f'height="{_num(box_h)}" rx="4" fill="black" fill-opacity="0.22"/>'
            )
        radius = "4" if style_opts.get("borderRadius") else "0"
        background_value = style_opts.get("background")
        # An explicit background is a paint, not a tint. The browser renders
        # `background:#fef3c7` opaque, so the writers must too; the
        # frame-alpha token stays the knob for the default grey frame.
        frame_alpha = style_opts.get("--xy-legend-frame-alpha")
        if frame_alpha is not None:
            alpha = float(frame_alpha)
        else:
            alpha = 0.08 if background_value is None else 1.0
        if background_value is None and alpha == 0.08:
            fill_attrs = 'fill="rgba(128,128,128,0.08)"'
        else:
            background = _css(background_value, "#808080")
            fill_attrs = f'fill="{escape(background)}" fill-opacity="{_num(alpha)}"'
        border = _css(style_opts.get("borderColor"), "#cccccc")
        rows.append(
            f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(box_w)}" height="{_num(box_h)}" '
            f'rx="{radius}" {fill_attrs} stroke="{escape(border)}" '
            f'stroke-opacity="{_num(alpha)}" stroke-width="1"/>'
        )
    if title:
        # The layout's measured size is the default; a slot may override it.
        title_size_attr = _slot_size_attr(title_slot) or f' font-size="{_num(font_size)}"'
        rows.append(
            f'<text x="{_num(x + box_w / 2)}" '
            f'y="{_num(y + pad / 2 + font_size * 0.82)}" text-anchor="middle"'
            f"{title_size_attr}"
            f"{slot_text_attrs(title_slot, font_weight='400')} "
            f'fill="{escape(slot_text_color(title_slot, text_color))}">'
            f"{escape(str(title))}</text>"
        )
    label_size_attr = _slot_size_attr(label_slot) or f' font-size="{_num(font_size)}"'
    for i, t in enumerate(named[: legend["visible_count"]]):
        style = t.get("style") or {}
        color = _css(
            style.get("color") or (t.get("color") or {}).get("color"),
            palette[i % len(palette)],
        )
        col, row = i % ncols, i // ncols
        rx, ry = x + column_offsets[col], y + pad / 2 + title_h + row * line_h
        hx0, hx1, cy = rx, rx + handle, ry + text_h / 2
        kind = t.get("kind")
        if kind == "scatter":
            rows.append(_legend_marker_svg(style, (hx0 + hx1) / 2, cy, color))
        elif kind in _LEGEND_LINE_KINDS:
            width = float(style.get("width", 1.5))
            gap_color = style.get("legend_gap_color")
            if gap_color is not None and style.get("dash"):
                rows.append(
                    f'<line x1="{_num(hx0)}" y1="{_num(cy)}" '
                    f'x2="{_num(hx1)}" y2="{_num(cy)}" '
                    f'stroke="{escape(_css(gap_color, color))}" '
                    f'stroke-width="{_num(width)}"/>'
                )
            rows.append(
                f'<line x1="{_num(hx0)}" y1="{_num(cy)}" x2="{_num(hx1)}" y2="{_num(cy)}" '
                f'stroke="{escape(color)}" stroke-width="{_num(width)}"'
                f"{_dash_attr(style)}/>"
            )
            marker = style.get("legend_marker")
            if isinstance(marker, dict):
                rows.append(_legend_marker_svg(marker, (hx0 + hx1) / 2, cy, color))
        else:
            stroke_width = max(0.0, float(style.get("stroke_width", 0.0)))
            stroke = style.get("stroke")
            stroke_attr = (
                f' stroke="{escape(_css(stroke, color))}" stroke-width="{_num(stroke_width)}"'
                if stroke is not None and stroke_width > 0.0
                else ""
            )
            rows.append(
                f'<rect x="{_num(hx0)}" y="{_num(cy - swatch_h / 2)}" '
                f'width="{handle}" height="{_num(swatch_h)}" '
                f'rx="2" fill="{escape(color)}"{stroke_attr}/>'
            )
            if style.get("hatch"):
                rows.append(
                    _legend_hatch_svg(
                        hx0,
                        hx1,
                        cy - swatch_h / 2,
                        cy + swatch_h / 2,
                        str(style["hatch"]),
                        _css(style.get("hatch_color"), "#222222"),
                    )
                )
        rows.append(
            f'<text x="{_num(hx1 + gap)}" y="{_num(ry + font_size * 0.82)}"'
            f"{label_size_attr}"
            f"{slot_text_attrs(label_slot)} "
            f'fill="{escape(slot_text_color(label_slot, text_color))}">'
            f"{escape(legend['names'][i])}</text>"
        )
    clip = "" if options.get("anchor") else f' clip-path="url(#{clip_id})"'
    return f"<g{clip}>{''.join(rows)}</g>"
