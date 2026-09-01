"""Shared static-export raster legend and colorbar emit."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise
from typing import Any, Optional, cast

import numpy as np

from ._export_chrome import (
    _TEXT,
    COLORBAR_FONT_SIZE,
    _colorbar_tick_target,
    slot_font_size,
    slot_text_color,
)
from ._export_legend import _legend_layout
from ._export_raster_cmd import (
    _SYMBOLS,
    _TEXT_ROT_CCW,
    _Cmd,
    _rect_pts,
    _round_rect_pts,
)
from ._export_ticks import (
    _fmt_log,
    axis_ticks,
)
from ._paint import _css
from ._paint import authored_marker_points as _authored_marker_points
from ._paint import colormap_lut as _lut
from ._paint import css_rgba8 as _rgba
from ._paint import paint_rgba8 as _parse_color
from .config import DEFAULT_PALETTE

_LEGEND_LINE_KINDS = frozenset({"line", "segments", "step", "stairs", "errorbar"})


def _emit_legend(
    cmd: _Cmd,
    named: list[dict[str, Any]],
    plot: dict[str, float],
    options: dict[str, Any],
    text_color: str = _TEXT,
    palette: Sequence[str] = DEFAULT_PALETTE,
    label_slot: Optional[dict[str, Any]] = None,
    title_slot: Optional[dict[str, Any]] = None,
) -> None:
    label_slot = label_slot or {}
    title_slot = title_slot or {}
    legend = _legend_layout(named, plot, options)
    if not legend["visible_count"]:
        # A plot too short for even one entry: no floating frame/title either.
        return
    style_opts = legend["style"]
    pad, handle, gap = legend["pad"], legend["handle"], legend["gap"]
    line_h, ncols = legend["line_h"], legend["ncols"]
    swatch_h = legend["swatch_h"]
    title, title_h = legend["title"], legend["title_h"]
    font_size, text_h = legend["font_size"], legend["text_h"]
    column_offsets = legend["column_offsets"]
    box_w, box_h = legend["box_w"], legend["box_h"]
    x, y = legend["x"], legend["y"]
    # frameon=False (background transparent) drops the box entirely (§ mpl parity).
    if style_opts.get("background") != "transparent":
        radius = 4.0 if style_opts.get("borderRadius") else 0.0
        frame_points = _round_rect_pts(x, y, x + box_w, y + box_h, radius)
        if style_opts.get("boxShadow"):
            shadow_points = _round_rect_pts(x + 2, y + 2, x + box_w + 2, y + box_h + 2, radius)
            cmd.fill(shadow_points, (0, 0, 0, 55))
        # An explicit background is a paint, not a tint — see the matching note
        # in `_svg._legend`; the two writers must agree.
        frame_alpha = style_opts.get("--xy-legend-frame-alpha")
        if frame_alpha is not None:
            alpha = float(frame_alpha)
        else:
            alpha = 0.08 if style_opts.get("background") is None else 1.0
        background = style_opts.get("background")
        frame = (
            _rgba(background, "#808080", alpha)
            if background
            else (128, 128, 128, round(255 * alpha))
        )
        cmd.fill(frame_points, frame)
        border = _rgba(style_opts.get("borderColor"), "#cccccc", alpha)
        # closed=True: the point list omits a repeated start point. Without it,
        # the final edge is silently dropped for both square and rounded frames.
        cmd.stroke(frame_points, 1.0, border, closed=True)
    if title:
        cmd.text(
            x + box_w / 2,
            y + pad / 2 + font_size * 0.82,
            1,
            slot_font_size(title_slot, font_size),
            _parse_color(slot_text_color(title_slot, text_color)),
            str(title),
        )
    for i, t in enumerate(named[: legend["visible_count"]]):
        style = t.get("style") or {}
        color_str = _css(
            style.get("color") or (t.get("color") or {}).get("color"),
            palette[i % len(palette)],
        )
        c = _parse_color(color_str)
        col, row = i % ncols, i // ncols
        rx, ry = x + column_offsets[col], y + pad / 2 + title_h + row * line_h
        hx0, hx1, cy = rx, rx + handle, ry + text_h / 2
        kind = t.get("kind")
        if kind == "scatter":
            _emit_legend_marker(cmd, style, (hx0 + hx1) / 2, cy, color_str)
        elif kind in _LEGEND_LINE_KINDS:
            width = float(style.get("width", 1.5))
            gap_color = style.get("legend_gap_color")
            if gap_color is not None and style.get("dash"):
                cmd.stroke(
                    [(hx0, cy), (hx1, cy)],
                    width,
                    _parse_color(_css(gap_color, color_str)),
                )
            cmd.stroke(
                [(hx0, cy), (hx1, cy)],
                width,
                c,
                dash=style.get("dash"),
            )
            marker = style.get("legend_marker")
            if isinstance(marker, dict):
                _emit_legend_marker(cmd, marker, (hx0 + hx1) / 2, cy, color_str)
        else:
            swatch_points = _rect_pts(hx0, cy - swatch_h / 2, hx1, cy + swatch_h / 2)
            cmd.fill(swatch_points, c)
            stroke_width = max(0.0, float(style.get("stroke_width", 0.0)))
            if style.get("stroke") is not None and stroke_width > 0.0:
                cmd.stroke(
                    swatch_points,
                    stroke_width,
                    _rgba(style.get("stroke"), color_str),
                    closed=True,
                )
            hatch = style.get("hatch")
            if hatch:
                _emit_legend_hatch(
                    cmd,
                    hx0,
                    hx1,
                    cy - swatch_h / 2,
                    cy + swatch_h / 2,
                    str(hatch),
                    _parse_color(_css(style.get("hatch_color"), "#222222")),
                )
        cmd.text(
            hx1 + gap,
            ry + font_size * 0.82,
            0,
            slot_font_size(label_slot, font_size),
            _parse_color(slot_text_color(label_slot, text_color)),
            legend["names"][i],
        )


def _emit_legend_marker(
    cmd: _Cmd,
    style: dict[str, Any],
    x: float,
    y: float,
    default_color: str,
) -> None:
    """Render one Matplotlib marker centered on its legend line sample."""
    symbol = str(style.get("symbol", "circle"))
    sym = _SYMBOLS.get(symbol, 0)
    marker_path = style.get("marker_path")
    marker_glyph = style.get("marker_glyph")
    color_str = _css(style.get("color"), default_color)
    color = _parse_color(color_str)
    sw = float(style.get("stroke_width", 0.0))
    if (
        symbol in {"plus_line", "x_line", "horizontal_line", "vertical_line"}
        or (marker_path and not bool(marker_path.get("filled", True)))
    ) and sw <= 0:
        sw = 1.0
    stroke = _rgba(style.get("stroke"), color_str) if sw > 0 else (0, 0, 0, 0)
    radius = max(0.5, float(style.get("size", 8.0)) / 2.0)
    if marker_glyph:
        cmd.text(x, y + radius * 0.68, 1, 2 * radius, color, str(marker_glyph))
    elif marker_path:
        for contour in marker_path.get("contours") or ():
            values = np.asarray(contour, dtype=np.float64).reshape(-1, 2)
            if not len(values):
                continue
            xs, ys = _authored_marker_points(values[:, 0], values[:, 1], x, y, 2 * radius)
            points = list(zip(xs.tolist(), ys.tolist(), strict=True))
            if bool(marker_path.get("filled", True)):
                cmd.fill(points, color)
                if sw > 0:
                    cmd.stroke(points, sw, stroke if stroke[3] else color, closed=True)
            else:
                cmd.stroke(points, max(1.0, sw), color)
    else:
        cmd.point(x, y, radius, sym, color, sw, stroke)


def _emit_legend_hatch(
    cmd: _Cmd,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    hatch: str,
    color: tuple[int, int, int, int],
) -> None:
    mid_y = (y0 + y1) / 2
    if "-" in hatch:
        cmd.stroke([(x0, mid_y), (x1, mid_y)], 1.0, color)
    for char, direction in (("/", 1), ("\\", -1)):
        count = min(3, hatch.count(char))
        for index in range(count):
            center = x0 + (index + 1) * (x1 - x0) / (count + 1)
            half = min((x1 - x0) / 4, (y1 - y0) / 2)
            cmd.stroke(
                [
                    (center - half, mid_y + direction * half),
                    (center + half, mid_y - direction * half),
                ],
                1.0,
                color,
            )
    if "." in hatch:
        for fraction in (0.3, 0.7):
            x = x0 + fraction * (x1 - x0)
            cmd.point(
                x,
                mid_y,
                min(1.1, (y1 - y0) * 0.09),
                _SYMBOLS["circle"],
                color,
                0.0,
                (0, 0, 0, 0),
            )
    if "*" in hatch:
        center = (x0 + x1) / 2
        cmd.point(
            center,
            mid_y,
            min(x1 - x0, y1 - y0) * 0.28,
            _SYMBOLS["star"],
            color,
            0.0,
            (0, 0, 0, 0),
        )


def _emit_colorbar(
    cmd: _Cmd,
    options: dict[str, Any],
    plot: dict[str, float],
    right_axis_room: float = 0.0,
    text_color: str = _TEXT,
    title_slot: Optional[dict[str, Any]] = None,
    tick_slot: Optional[dict[str, Any]] = None,
) -> None:
    title_slot = title_slot or {}
    tick_slot = tick_slot or {}
    title_size = slot_font_size(title_slot, COLORBAR_FONT_SIZE)
    title_paint = _parse_color(slot_text_color(title_slot, text_color))
    tick_size = slot_font_size(tick_slot, COLORBAR_FONT_SIZE)
    tick_paint = _parse_color(slot_text_color(tick_slot, text_color))

    orientation = options.get("orientation", "vertical")
    shrink = float(options.get("shrink", 1.0))
    anchor = options.get("anchor") or [0.5, 0.5]
    placement = options.get("placement")
    if placement == "axes":
        x, y, width, height = plot["x"], plot["y"], plot["w"], plot["h"]
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
    else:
        # right_axis_room shifts the whole colorbar clear of right-side named
        # y-axis chrome (layout() reserves room for both additively).
        gap = float(options["pad"]) * plot["w"] if options.get("pad") is not None else 24.0
        x = plot["x"] + plot["w"] + right_axis_room + gap
        height = plot["h"] * shrink
        y = plot["y"] + (plot["h"] - height) * (1.0 - float(anchor[1]))
        width = 18
    # A discrete (resampled) colormap paints N solid bands; otherwise a smooth
    # 64-step gradient approximates the continuous ramp.
    levels = options.get("levels")
    if levels and int(levels) >= 1:
        n_seg = int(levels)
        exact_colors = options.get("band_colors")
        colors = (
            np.asarray(exact_colors, dtype=np.uint8)
            if isinstance(exact_colors, list) and len(exact_colors) == n_seg
            else _lut(
                options.get("colormap", "viridis"),
                (np.arange(n_seg, dtype=np.float64) + 0.5) / n_seg,
            )
        )
    else:
        n_seg = 64
        colors = _lut(options.get("colormap", "viridis"), np.linspace(0.0, 1.0, n_seg))
    fractions = np.linspace(0.0, 1.0, n_seg + 1)
    boundaries = np.asarray(options.get("boundaries", []), dtype=np.float64).reshape(-1)
    if (
        levels
        and options.get("spacing") == "proportional"
        and len(boundaries) == n_seg + 1
        and np.isfinite(boundaries).all()
        and boundaries[-1] > boundaries[0]
        and np.all(np.diff(boundaries) > 0.0)
    ):
        fractions = (boundaries - boundaries[0]) / (boundaries[-1] - boundaries[0])
    line_only = bool(options.get("line_only"))
    if line_only:
        outline = _rect_pts(x, y, x + width, y + height)
        cmd.fill(outline, (255, 255, 255, 255))
        cmd.stroke([*outline, outline[0]], 1.0, _parse_color(text_color))
    else:
        for index, color in enumerate(colors):
            lower, upper = float(fractions[index]), float(fractions[index + 1])
            if orientation == "horizontal":
                x0, x1 = x + width * lower, x + width * upper
                cmd.fill(_rect_pts(x0, y, x1 + 0.5, y + height), (*map(int, color), 255))
            else:
                y0 = y + height * (1.0 - upper)
                y1 = y + height * (1.0 - lower)
                cmd.fill(_rect_pts(x, y0, x + width, y1 + 0.5), (*map(int, color), 255))
    domain = options.get("domain", [0.0, 1.0])
    lo, hi = float(domain[0]), float(domain[1])
    log_scale = options.get("scale") == "log"

    def fraction(value: float) -> float:
        if log_scale:
            return np.log(value / lo) / np.log(hi / lo) if hi != lo else 0.0
        return (value - lo) / ((hi - lo) or 1.0)

    def automatic_ticks(length: float) -> list[float]:
        target = _colorbar_tick_target(length)
        automatic = axis_ticks(
            {
                "kind": "log" if log_scale else "linear",
                "range": [lo, hi],
                "tick_count": target,
            },
            length,
            orientation == "horizontal",
        )
        return (automatic[1] if log_scale else automatic[0]) or [lo, hi]

    format_tick = _fmt_log if log_scale else lambda value: f"{value:g}"
    ticks = options.get("ticks")
    supplied_labels = options.get("tick_labels")
    tick_label_map = (
        {float(cast(Any, value)): str(supplied_labels[index]) for index, value in enumerate(ticks)}
        if isinstance(ticks, list)
        and isinstance(supplied_labels, list)
        and len(ticks) == len(supplied_labels)
        else {}
    )

    def tick_text(value: float) -> str:
        return tick_label_map.get(float(value), format_tick(value))

    extend = options.get("extend")
    if extend in ("max", "both"):
        color = (
            (255, 255, 255, 255)
            if line_only
            else (*map(int, options.get("over_color", colors[-1])), 255)
        )
        if orientation == "horizontal":
            pts = [(x + width, y), (x + width, y + height), (x + width + 9, y + height / 2)]
        else:
            pts = [(x, y), (x + width, y), (x + width / 2, y - 9)]
        cmd.fill(pts, color)
        if line_only:
            cmd.stroke([*pts, pts[0]], 1.0, _parse_color(text_color))
    if extend in ("min", "both"):
        color = (
            (255, 255, 255, 255)
            if line_only
            else (*map(int, options.get("under_color", colors[0])), 255)
        )
        if orientation == "horizontal":
            pts = [(x, y), (x, y + height), (x - 9, y + height / 2)]
        else:
            pts = [(x, y + height), (x + width, y + height), (x + width / 2, y + height + 9)]
        cmd.fill(pts, color)
        if line_only:
            cmd.stroke([*pts, pts[0]], 1.0, _parse_color(text_color))
    for line in options.get("lines") or []:
        value = float(line.get("value", np.nan))
        if not np.isfinite(value) or value < min(lo, hi) or value > max(lo, hi):
            continue
        line_fraction = fraction(value)
        color = _parse_color(str(line.get("color") or text_color))
        line_width = max(0.5, float(line.get("width", 1.0)))
        dash = [3.7 * line_width, 1.6 * line_width] if line.get("dash") == "dashed" else None
        if orientation == "horizontal":
            position = x + width * line_fraction
            cmd.stroke([(position, y), (position, y + height)], line_width, color, dash=dash)
        else:
            position = y + height * (1.0 - line_fraction)
            cmd.stroke([(x, position), (x + width, position)], line_width, color, dash=dash)
    if orientation == "horizontal":
        h_positions = (
            [float(value) for value in ticks if lo <= float(value) <= hi]
            if ticks is not None
            else automatic_ticks(width)
        )
        if options.get("minor_ticks") and len(h_positions) >= 2:
            ordered = sorted(set(h_positions))
            for left, right in pairwise(ordered):
                for step in range(1, 5):
                    value = (
                        10 ** (np.log10(left) + (np.log10(right) - np.log10(left)) * step / 5.0)
                        if log_scale
                        else left + (right - left) * step / 5.0
                    )
                    tx = x + width * fraction(value)
                    cmd.stroke(
                        [(tx, y + height), (tx, y + height + 3)],
                        1,
                        _parse_color(text_color),
                    )
        for value in h_positions:
            cmd.text(
                x + width * fraction(value),
                y + height + 13,
                1,
                tick_size,
                tick_paint,
                tick_text(value),
            )
        if options.get("label"):
            cmd.text(
                x + width / 2,
                y + height + 26,
                1,
                title_size,
                title_paint,
                str(options["label"]),
            )
    else:
        tick_positions = (
            [float(value) for value in ticks if lo <= float(value) <= hi]
            if ticks is not None
            else automatic_ticks(height)
        )
        if options.get("minor_ticks") and len(tick_positions) >= 2:
            ordered = sorted(set(tick_positions))
            for lower, upper in pairwise(ordered):
                for step in range(1, 5):
                    value = (
                        10 ** (np.log10(lower) + (np.log10(upper) - np.log10(lower)) * step / 5.0)
                        if log_scale
                        else lower + (upper - lower) * step / 5.0
                    )
                    ty = y + height * (1 - fraction(value))
                    cmd.stroke(
                        [(x + width, ty), (x + width + 3, ty)],
                        1,
                        _parse_color(text_color),
                    )
        for value in tick_positions:
            cmd.text(
                x + width + 4,
                y + height * (1 - fraction(value)) + 4,
                0,
                tick_size,
                tick_paint,
                tick_text(value),
            )
        # Matplotlib rotates a vertical colorbar's label 90° CCW and centers it
        # alongside the bar, outboard of the tick labels. The native glyph
        # protocol rotates in quarter turns (_TEXT_ROT_CCW), so 90° is exact
        # here; the upright-glyph limitation applies only to arbitrary angles.
        # A horizontal label above the bar instead sat at `plot.y - 5`, where
        # the glyph ascent overflowed the canvas top edge and was clipped. The
        # baseline matches the SVG exporter's `x + width + 38` so both static
        # paths agree, inside the room layout() already reserves for a label.
        if options.get("label"):
            cmd.text(
                x + width + 38,
                y + height / 2,
                1 | _TEXT_ROT_CCW,
                title_size,
                title_paint,
                str(options["label"]),
            )
