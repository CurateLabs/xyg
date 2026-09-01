"""Shared static-export raster mark emit helpers."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import _paint, _png, kernels
from ._arrowgeom import arrow_shapes as _arrow_shapes
from ._columns import column as _column
from ._columns import column_ref as _column_ref
from ._columns import density_column as _density_column
from ._export_annotations import (
    _annotation_connector_unclipped,
    _annotation_first_baseline,
    annotation_label_placement,
)
from ._export_chrome import _TEXT
from ._export_raster_cmd import (
    _CAP_CODES,
    _SYMBOLS,
    _Cmd,
    _rect_pts,
    _round_rect_pts,
)
from ._layout import _Scale, affine_fast_path, polar_wedge_points, warp_grid_rgba
from ._paint import (
    _css,
    effective_paint_rgba8,
    hexbin_ring,
)
from ._paint import (
    authored_marker_points as _authored_marker_points,
)
from ._paint import (
    box_corner_radius as _box_corner_radius,
)
from ._paint import (
    colormap_stops as _colormap_stops,
)
from ._paint import (
    compat_grid_rgba as _compat_grid_rgba,
)
from ._paint import (
    corner_radii as _corner_radii,
)
from ._paint import (
    css_rgba8 as _rgba,
)
from ._paint import (
    curve_points as _curve_points,
)
from ._paint import (
    fill_opacity as _fill_opacity,
)
from ._paint import (
    grad_line as _grad_line,
)
from ._paint import (
    grad_stops as _grad_stops,
)
from ._paint import (
    grid_dest_rect as _grid_dest_rect,
)
from ._paint import (
    heatmap_rgba_grid as _heatmap_rgba_grid,
)
from ._paint import (
    paint_rgba8 as _parse_color,
)
from ._paint import (
    physical_density_alpha as _physical_density_alpha,
)
from ._paint import (
    px_size as _px_size,
)
from ._paint import (
    rect_style_arrays as _rect_style_arrays,
)
from ._paint import (
    rgba8 as _rgba8,
)
from ._paint import (
    rounded_rect_vertices as _rounded_rect_vertices,
)
from ._paint import (
    step_arrays as _step_arrays,
)
from ._paint import (
    stroke_opacity as _stroke_opacity,
)

if TYPE_CHECKING:
    from ._layout import _PolarProjection

_png_rgba = _png.png_truecolor


def _emit_line(
    cmd: _Cmd,
    t: dict[str, Any],
    blob: bytes,
    cols: list[dict[str, Any]],
    sx: _Scale,
    sy: _Scale,
    style: dict[str, Any],
    color: str,
    polar: "Optional[_PolarProjection]" = None,
) -> None:
    xv, yv = _column(blob, cols[t["x"]]), _column(blob, cols[t["y"]])
    if style.get("step"):
        xv, yv = _step_arrays(xv, yv, style["step"])
    c = _rgba(style.get("color"), color, _stroke_opacity(style))
    width = float(style.get("width", 1.5))
    # `render_raster` takes a plain spec dict, so a hand-built or round-tripped
    # one can carry a value `compile_mark_style` would have rejected. Fall back
    # to the documented default rather than raising a bare KeyError from inside
    # the byte packer.
    cap = str(style.get("linecap", "round"))
    cap = cap if cap in _CAP_CODES else "round"
    if polar is not None:
        # Chords between projected points (polar-axes.md §5). The smooth branch
        # is skipped outright: its Bezier control points are only exact under an
        # affine map, and `smooth_stroke` bakes that map into Rust. Vertices
        # outside the radial range split the stroke into visible runs — the
        # same cull the client shader applies. The shaped clip contains paint at
        # the boundary, but it cannot restore gap semantics after an invalid
        # data vertex has been projected through the centre.
        px, py = polar(xv, yv)
        visible = polar.position_mask(xv, yv)
        indices = np.flatnonzero(visible)
        runs = (
            [np.arange(len(xv))]
            if bool(visible.all())
            else np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
        )
        for run in runs:
            if len(run) < 2:
                continue
            points = list(zip(px[run].tolist(), py[run].tolist(), strict=True))
            cmd.stroke(points, width, c, dash=style.get("dash"), cap=cap)
    elif style.get("curve") == "smooth" and len(xv) >= 3 and affine_fast_path(sx, sy, polar):
        cmd.smooth_stroke(xv, yv, sx, sy, width, c, dash=style.get("dash"), cap=cap)
    else:
        pts = _curve_points(xv, yv, sx, sy, False)
        cmd.stroke(pts, width, c, dash=style.get("dash"), cap=cap)


def _native_font_emphasis(style: dict[str, Any]) -> tuple[bool, bool]:
    """Return baked-font italic/bold approximations for an annotation."""
    italic = str(style.get("font_style", "")).lower() in {"italic", "oblique"}
    weight = str(style.get("font_weight", "")).lower()
    try:
        bold = float(weight) >= 600
    except ValueError:
        bold = weight in {"bold", "semibold", "demibold", "heavy", "black"}
    return italic, bold


def _math_italic_ranges(style: dict[str, Any]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for item in str(style.get("math_italic_ranges", "")).split(","):
        try:
            start, end = (int(value) for value in item.split(":", 1))
        except ValueError:
            continue
        if 0 <= start < end:
            ranges.append((start, end))
    return ranges


def _emit_annotations(
    cmd: _Cmd,
    annotations: list[dict[str, Any]],
    sx: _Scale,
    sy: _Scale,
    plot: dict[str, float],
    width: float,
    height: float,
    *,
    phase: str = "marks",
    polar: "Optional[_PolarProjection]" = None,
) -> None:
    px0, py0 = plot["x"], plot["y"]
    text_phase = phase == "text"

    def point(x: float, y: float) -> tuple[float, float]:
        """Jointly project point-anchored geometry under polar coordinates."""
        if polar is not None:
            px, py = polar(x, y)
            return float(px), float(py)
        return float(sx(x)), float(sy(y))

    for ann in annotations:
        # Geometry (rules/bands/arrows/markers) draws in the clipped marks
        # pass; every label draws in the unclipped chrome pass, matching
        # matplotlib's Text and the client's DOM labels.
        style = ann.get("style") or {}
        restore_plot_clip = False
        color = _rgba(style.get("color"), "#667085", float(style.get("opacity", 1.0)))
        start = max(0.0, min(1.0, float(style.get("span_start", 0.0))))
        end = max(start, min(1.0, float(style.get("span_end", 1.0))))
        if text_phase:
            pass
        elif ann.get("kind") == "rule":
            if ann.get("axis") == "x":
                pos = float(sx(float(ann["value"])))
                points = [(pos, py0 + (1 - end) * plot["h"]), (pos, py0 + (1 - start) * plot["h"])]
            else:
                pos = float(sy(float(ann["value"])))
                points = [(px0 + start * plot["w"], pos), (px0 + end * plot["w"], pos)]
            cmd.stroke(
                points,
                float(style.get("width", 1.5)),
                color,
                dash=(
                    [float(value) for value in style["dash"].split(",")]
                    if isinstance(style.get("dash"), str)
                    else style.get("dash")
                ),
            )
        elif ann.get("kind") == "band":
            a, b = float(ann["start"]), float(ann["end"])
            if ann.get("axis") == "x":
                x0, x1 = sorted((float(sx(a)), float(sx(b))))
                y0, y1 = py0 + (1 - end) * plot["h"], py0 + (1 - start) * plot["h"]
            else:
                y0, y1 = sorted((float(sy(a)), float(sy(b))))
                x0, x1 = px0 + start * plot["w"], px0 + end * plot["w"]
            cmd.fill(
                _rect_pts(x0, y0, x1, y1),
                _rgba(style.get("color"), "#64748b", float(style.get("opacity", 0.14))),
            )
        elif ann.get("kind") in ("arrow", "callout"):
            if _annotation_connector_unclipped(ann, sx, sy, plot, polar):
                cmd.clip(0, 0, width, height)
                restore_plot_clip = True
            if ann.get("kind") == "arrow":
                x0, y0 = point(float(ann["x0"]), float(ann["y0"]))
                x1, y1 = point(float(ann["x1"]), float(ann["y1"]))
            else:  # pointer from the offset label back to the data point
                x1, y1 = point(float(ann["x"]), float(ann["y"]))
                x0, y0 = x1 + float(ann.get("dx", 0.0)), y1 + float(ann.get("dy", 0.0))
            if all(np.isfinite(v) for v in (x0, y0, x1, y1)):
                shapes = _arrow_shapes(x0, y0, x1, y1, style)
                stroke_width = max(0.5, float(style.get("width", 1.5)))
                if shapes["taper"] is not None:
                    cmd.fill(shapes["taper"], color)
                else:
                    cmd.stroke(
                        shapes["shaft"],
                        stroke_width,
                        color,
                        dash=(
                            [float(value) for value in style["dash"].split(",")]
                            if isinstance(style.get("dash"), str)
                            else style.get("dash")
                        ),
                    )
                for decoration in (shapes["head"], shapes["tail"]):
                    if decoration is None:
                        continue
                    if decoration["kind"] == "fill":
                        cmd.fill(decoration["points"], color)
                    else:
                        cmd.stroke(decoration["points"], stroke_width, color)
        elif ann.get("kind") == "marker":
            mx, my = point(float(ann["x"]), float(ann["y"]))
            if np.isfinite(mx) and np.isfinite(my):
                alpha = float(style.get("opacity", 1.0))
                stroke_w = float(style.get("stroke_width", 0.0))
                cmd.point(
                    mx,
                    my,
                    max(0.5, float(ann.get("size", 8.0)) / 2.0),
                    _SYMBOLS.get(str(ann.get("symbol", "circle")), 0),
                    _rgba(style.get("color"), "#2563eb", alpha),
                    stroke_w,
                    (
                        _rgba(style.get("stroke_color"), "#ffffff", alpha)
                        if stroke_w > 0
                        else (0, 0, 0, 0)
                    ),
                )
        if restore_plot_clip:
            cmd.clip(plot["x"], plot["y"], plot["w"], plot["h"])
            if polar is not None:
                cmd.polar_clip(polar)
        if text_phase and ann.get("text"):
            x, y, label_anchor, vertical_align = annotation_label_placement(
                ann, style, sx, sy, plot, width, height, polar
            )
            if not (np.isfinite(x) and np.isfinite(y)):
                continue
            if vertical_align:
                style = {**style, "vertical_align": vertical_align}
            anchor = {"start": 0, "middle": 1, "end": 2}.get(label_anchor, 0)
            font_size = _px_size(style.get("font_size"), 11.0)
            lines = str(ann["text"]).splitlines() or [""]
            line_height = font_size * 1.2
            # A callout's `color` paints its arrow; the label prefers its own.
            label_color = style.get("label_color") or style.get("color")
            label_opacity = style.get(
                "label_opacity",
                style.get("opacity", 1.0) if ann.get("kind") == "text" else 1.0,
            )
            color = _rgba(label_color, _TEXT, float(label_opacity))
            rotation = float(style.get("rotation", 0.0)) % 360.0
            italic, bold = _native_font_emphasis(style)
            math_ranges = _math_italic_ranges(style)
            line_offset = 0
            if rotation in (90.0, 270.0):
                # Vertical text via the rasterizer's rotated glyph paths.
                # matplotlib aligns the post-rotation box: vertical_align picks
                # the anchor along the reading axis, the horizontal anchor
                # shifts the baseline across it (ascent ~0.78em, descent ~0.22em).
                x += float(ann.get("dx", 0.0))
                y += float(ann.get("dy", 0.0))
                cw = rotation == 270.0
                va = str(style.get("vertical_align", ""))
                along = {"center": 1, "top": 0 if cw else 2, "bottom": 2 if cw else 0}.get(va, 0)
                ascent, descent = font_size * 0.78, font_size * 0.22
                if cw:
                    base = {0: descent, 1: (descent - ascent) / 2, 2: -ascent}[anchor]
                else:
                    base = {0: ascent, 1: (ascent - descent) / 2, 2: -descent}[anchor]
                stack = -line_height if cw else line_height  # later lines: glyph-down
                for index, line in enumerate(lines):
                    line_ranges = [
                        (max(0, start - line_offset), min(len(line), end - line_offset))
                        for start, end in math_ranges
                        if start < line_offset + len(line) and end > line_offset
                    ]
                    cmd.text(
                        x + base + index * stack,
                        y,
                        along,
                        font_size,
                        color,
                        line,
                        angle=90.0 if cw else -90.0,
                        italic=italic,
                        bold=bold,
                        italic_ranges=line_ranges,
                    )
                    line_offset += len(line) + 1
                continue
            vertical_align = style.get("vertical_align")
            text_x = x + float(ann.get("dx", 0.0))
            text_y = _annotation_first_baseline(
                y + float(ann.get("dy", 0.0)),
                len(lines),
                line_height,
                font_size,
                vertical_align,
            )
            _emit_text_box(cmd, style, lines, text_x, text_y, line_height, font_size, anchor)
            for index, line in enumerate(lines):
                line_ranges = [
                    (max(0, start - line_offset), min(len(line), end - line_offset))
                    for start, end in math_ranges
                    if start < line_offset + len(line) and end > line_offset
                ]
                cmd.text(
                    text_x,
                    text_y + index * line_height,
                    anchor,
                    font_size,
                    color,
                    line,
                    angle=-rotation,
                    italic=italic,
                    bold=bold,
                    italic_ranges=line_ranges,
                )
                line_offset += len(line) + 1


def _emit_text_box(
    cmd: _Cmd,
    style: dict[str, Any],
    lines: list[str],
    x: float,
    first_y: float,
    line_height: float,
    font_size: float,
    anchor: int,
) -> None:
    """Draw the bounded CSS approximation used by pyplot ``text(bbox=)``."""
    background = style.get("background")
    border = str(style.get("border", ""))
    if background is None and not border:
        return
    pad_parts = str(style.get("padding", "0")).split()

    def px(value: str) -> float:
        try:
            return max(0.0, float(value.removesuffix("px")))
        except ValueError:
            return 0.0

    pad_y = px(pad_parts[0]) if pad_parts else 0.0
    pad_x = px(pad_parts[1]) if len(pad_parts) > 1 else pad_y
    text_width = _estimated_text_width(lines, font_size)
    left = x - (text_width / 2 if anchor == 1 else text_width if anchor == 2 else 0.0) - pad_x
    top = first_y - font_size * 0.8 - pad_y
    right = left + text_width + pad_x * 2
    bottom = top + font_size + (len(lines) - 1) * line_height + pad_y * 2
    # `boxstyle="round"`/`round4` set border_radius, which the browser applies
    # as CSS border-radius; round the same corners here or the exported box is
    # square where the live one is not.
    points = _round_rect_pts(
        left, top, right, bottom, _box_corner_radius(style, right - left, bottom - top)
    )
    if background is not None:
        cmd.fill(points, _parse_color(str(background)))
    if border:
        parts = border.split()
        try:
            width = max(0.0, float(parts[0].removesuffix("px")))
        except (IndexError, ValueError):
            width = 1.0
        if width:
            cmd.stroke(points + [points[0]], width, _parse_color(parts[-1]))


def _emit_area(
    cmd: _Cmd,
    t: dict[str, Any],
    blob: bytes,
    cols: list[dict[str, Any]],
    sx: _Scale,
    sy: _Scale,
    style: dict[str, Any],
    color: str,
    plot: dict[str, float],
    polar: "Optional[_PolarProjection]" = None,
) -> None:
    xv = _column(blob, cols[t["x"]])
    yv = _column(blob, cols[t["y"]])
    bv = _column(blob, cols[t["base"]])
    smooth = style.get("curve") == "smooth"
    if polar is not None:
        # Chord-bounded polygon (polar-axes.md §5); smoothing is skipped because
        # its control points are only exact under an affine map. Radii clamp to
        # the radial range — the fill at each theta is [base, top] ∩
        # [r_lo, r_hi], and a base below r_lo would otherwise mirror through
        # the centre (mirrors the SVG area branch and AREA_VS). Vertices
        # outside the theta sector (or NaN) are CULLED, splitting the fill
        # into visible runs — the SVG path applies position_mask inside
        # _curve_path and the client NaN-culls in the shader; painting them
        # here drew chords across the sector boundary and let NaN reach the
        # display list (§19).
        radial_min, radial_max = sorted((polar.r_lo, polar.r_hi))
        top_r = np.clip(yv, radial_min, radial_max)
        base_r = np.clip(bv, radial_min, radial_max)
        visible = polar.position_mask(xv, top_r) & polar.position_mask(xv, base_r)
        if bool(visible.all()):
            runs = [np.arange(len(xv))]
        else:
            indices = np.flatnonzero(visible)
            runs = (
                []
                if indices.size == 0
                else np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
            )
        pieces = []
        for run in runs:
            if len(run) < 2:
                continue
            run_top = np.column_stack(polar(xv[run], top_r[run]))
            run_base = np.column_stack(polar(xv[run][::-1], base_r[run][::-1]))
            pieces.append((run_top, run_base))
    else:
        top = _curve_points(xv, yv, sx, sy, smooth)
        base = _curve_points(xv[::-1], bv[::-1], sx, sy, smooth)
        pieces = [(top, base)]
    op = _fill_opacity(style, 0.35)
    fill_spec = style.get("fill")
    for top, base in pieces:
        poly = np.vstack([top, base])
        if isinstance(fill_spec, dict):
            xs, ys = poly[:, 0], poly[:, 1]
            bbox = (xs.min(), ys.min(), xs.max() - xs.min(), ys.max() - ys.min())
            g0, g1 = _grad_line(
                fill_spec.get("space", "mark"), fill_spec.get("dir", "down"), bbox, plot
            )
            stops = [
                (o, (c[0], c[1], c[2], int(c[3] * op))) for o, c in _grad_stops(fill_spec, color)
            ]
            cmd.grad(poly.tolist(), g0, g1, stops)
        else:
            cmd.fill(poly.tolist(), _rgba(style.get("color"), color, op))
        lw = float(style.get("line_width", 1.2))
        if lw > 0:
            lop = _stroke_opacity(style, 0.35) * float(style.get("line_opacity", 1.0))
            line_color = _rgba(style.get("line_color"), style.get("color") or color, lop)
            cmd.stroke(top, lw, line_color, dash=style.get("dash"))
            if style.get("stroke_perimeter"):
                cmd.stroke(base, lw, line_color, dash=style.get("dash"))


def _emit_authored_scatter(
    cmd: _Cmd,
    t: dict[str, Any],
    blob: bytes,
    cols: list[dict[str, Any]],
    sx: _Scale,
    sy: _Scale,
    style: dict[str, Any],
    color: str,
    polar: "Optional[_PolarProjection]" = None,
) -> None:
    """Paint bounded pyplot-authored paths/glyphs in display-list space."""
    xv, yv = _column(blob, cols[t["x"]]), _column(blob, cols[t["y"]])
    px, py = polar(xv, yv) if polar is not None else (sx(xv), sy(yv))
    # Out-of-range radii are culled like the client shader culls them. The
    # shaped clip contains glyph extent at the boundary, but a below-range
    # position itself mirrors into the visible annulus and must still be
    # rejected before projection.
    visible = polar.position_mask(xv, yv) if polar is not None else None
    n = len(xv)
    if not n:
        return

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    face, fills, strokes = _paint.trace_fill_and_stroke_rgba8(
        t, style, n, color, read, default_opacity=0.8
    )
    size_ch = t.get("size") or {}
    radii = _paint.scatter_radii(size_ch, read, n)
    widths = _paint.style_values(t, "stroke_width", n, read, float(style.get("stroke_width", 0)))
    marker_path = style.get("marker_path")
    marker_glyph = style.get("marker_glyph")
    filled = bool(marker_path and marker_path.get("filled", True))

    for index in range(n):
        if visible is not None and not visible[index]:
            continue
        fill = tuple(int(value) for value in fills[index])
        stroke = tuple(int(value) for value in strokes[index])
        diameter = max(0.0, 2 * (float(radii[index]) - float(widths[index]) / 2))
        if marker_glyph:
            cmd.text(
                float(px[index]),
                float(py[index]) + diameter * 0.34,
                1,
                diameter,
                fill,
                str(marker_glyph),
            )
            continue
        if not marker_path:
            continue
        contours = []
        for contour in marker_path.get("contours") or ():
            values = np.asarray(contour, dtype=np.float64).reshape(-1, 2)
            if not len(values):
                continue
            xs, ys = _authored_marker_points(
                values[:, 0],
                values[:, 1],
                float(px[index]),
                float(py[index]),
                diameter,
            )
            contours.append(list(zip(xs.tolist(), ys.tolist(), strict=True)))
        if filled:
            for points in contours:
                cmd.fill(points, fill)
            if float(widths[index]) > 0:
                for points in contours:
                    cmd.stroke(points, float(widths[index]), stroke, closed=True)
        else:
            width = max(1.0, float(widths[index]))
            for points in contours:
                cmd.stroke(points, width, fill)


def _emit_scatter(
    cmd: _Cmd,
    t: dict[str, Any],
    blob: bytes,
    cols: list[dict[str, Any]],
    sx: _Scale,
    sy: _Scale,
    style: dict[str, Any],
    color: str,
    polar: "Optional[_PolarProjection]" = None,
) -> None:
    ch = t.get("color") or {}
    size_ch = t.get("size") or {}
    if style.get("marker_path") or style.get("marker_glyph"):
        _emit_authored_scatter(cmd, t, blob, cols, sx, sy, style, color, polar)
        return

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    fill_op = _fill_opacity(style, 0.8)
    stroke_op = _stroke_opacity(style, 0.8)
    artist_alpha = style.get("artist_alpha")
    if artist_alpha is not None:
        # Matplotlib artist alpha replaces the intrinsic paint alpha. Scalar
        # alpha does not need a style channel, so retain it in both affine
        # scatter fast paths instead of silently painting opaque points.
        scalar_alpha = float(artist_alpha)
        fill_op *= scalar_alpha
        stroke_op *= scalar_alpha
    sw = float(style.get("stroke_width", 0.0))
    sym = _SYMBOLS.get(style.get("symbol", "circle"), 0)
    # Transparent is the private wire sentinel for edgecolors="face".  The
    # native point painter replaces it with each point's resolved RGBA fill.
    stroke_value = style.get("stroke")
    stroke = (
        _rgba(stroke_value, color, stroke_op)
        if sw > 0 and stroke_value is not None
        else (0, 0, 0, 0)
    )

    color_mode = ch.get("mode")
    size_mode = size_ch.get("mode")
    if (
        affine_fast_path(sx, sy, polar)
        and not t.get("channels")
        and (t.get("stroke") is None or t["stroke"].get("mode") == "match_fill")
        and (color_mode in {"continuous", "categorical"} or size_mode == "continuous")
    ):
        paint = _parse_color(_css(ch.get("color"), color))
        alpha = max(0, min(255, int(round(fill_op * paint[3]))))
        cmd.affine_channel_points(
            cols[t["x"]],
            cols[t["y"]],
            sx,
            sy,
            ch,
            size_ch,
            (paint[0], paint[1], paint[2], alpha),
            sym,
            sw,
            stroke,
            cols,
        )
        return

    # The dominant static-scatter case needs neither materialized f64 decoded
    # columns nor projected/radius/RGBA arrays.  Rust borrows the two payload
    # spans and applies the same affine math while painting.  Keep the existing
    # command as the full-fidelity fallback for log axes and channel styling.
    if (
        affine_fast_path(sx, sy, polar)
        and ch.get("mode") not in {"continuous", "categorical", "direct_rgba"}
        and size_ch.get("mode") != "continuous"
        and not t.get("channels")
        and (t.get("stroke") is None or t["stroke"].get("mode") == "match_fill")
    ):
        paint = _parse_color(_css(ch.get("color"), color))
        alpha = max(0, min(255, int(round(fill_op * paint[3]))))
        fill = (paint[0], paint[1], paint[2], alpha)
        radius = float(size_ch.get("size", 4.0)) / 2
        cmd.affine_points(cols[t["x"]], cols[t["y"]], sx, sy, radius, fill, sym, sw, stroke)
        return

    xv, yv = _column(blob, cols[t["x"]]), _column(blob, cols[t["y"]])
    px, py = polar(xv, yv) if polar is not None else (sx(xv), sy(yv))
    n = len(xv)
    if n == 0:
        return
    face_intrinsic, fills, strokes = _paint.trace_fill_and_stroke_rgba8(
        t, style, n, color, read, default_opacity=0.8
    )
    radii = _paint.scatter_radii(size_ch, read, n)

    widths = _paint.style_values(t, "stroke_width", n, read, sw)
    symbol_channel = (t.get("channels") or {}).get("symbol")
    symbols = (
        np.asarray(read(symbol_channel["buf"]), dtype=np.uint8)[:n]
        if symbol_channel is not None
        else np.full(n, sym, dtype=np.uint8)
    )
    if polar is not None:
        # Cull out-of-range radii the way the client shader does: below r_lo a
        # sprite mirrors through the centre. The shaped clip contains glyph
        # extent at valid boundaries, but cannot distinguish that mirrored
        # invalid position from an honest in-range one.
        visible = polar.position_mask(xv, yv)
        if not bool(visible.all()):
            px, py, radii, fills = px[visible], py[visible], radii[visible], fills[visible]
            symbols, widths, strokes = symbols[visible], widths[visible], strokes[visible]
            n = len(px)
            if n == 0:
                return
    if (
        np.all(widths == widths[0])
        and np.all(symbols == symbols[0])
        and np.all(strokes == strokes[0])
    ):
        cmd.points(
            px,
            py,
            radii,
            fills,
            int(symbols[0]),
            float(widths[0]),
            tuple(int(value) for value in strokes[0]),
        )
    else:
        for index in range(n):
            cmd.points(
                px[index : index + 1],
                py[index : index + 1],
                radii[index : index + 1],
                fills[index : index + 1],
                int(symbols[index]),
                float(widths[index]),
                tuple(int(value) for value in strokes[index]),
            )


def _emit_segments(
    cmd: _Cmd,
    t: dict[str, Any],
    blob: bytes,
    cols: list[dict[str, Any]],
    sx: _Scale,
    sy: _Scale,
    style: dict[str, Any],
    color: str,
    polar: "Optional[_PolarProjection]" = None,
) -> None:
    x0 = _column(blob, cols[t["x0"]])
    x1 = _column(blob, cols[t["x1"]])
    y0 = _column(blob, cols[t["y0"]])
    y1 = _column(blob, cols[t["y1"]])

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    n = len(x0)
    colors = effective_paint_rgba8(
        t, "color", n, color, read, component="stroke", default_opacity=1.0
    )
    widths = _paint.style_values(t, "width", n, read, float(style.get("width", 1.2)))
    if polar is None:
        px0, py0, px1, py1 = sx(x0), sy(y0), sx(x1), sy(y1)
    else:
        px0, py0, px1, py1, keep = _paint.polar_clip_line_segments(polar, x0, y0, x1, y1)
        px0, py0, px1, py1 = px0[keep], py0[keep], px1[keep], py1[keep]
        colors = colors[keep]
        widths = widths[keep]
        n = len(widths)
    if n == 0:
        return
    dash = style.get("dash")
    if dash:
        # The batched segments primitive cannot dash; fall back to one dashed
        # stroke per segment (contour negative-level convention, few segments).
        dash_pattern = (
            [float(value) for value in dash.split(",")] if isinstance(dash, str) else list(dash)
        )
        for index in range(n):
            cmd.stroke(
                [(float(px0[index]), float(py0[index])), (float(px1[index]), float(py1[index]))],
                float(widths[index]),
                tuple(int(v) for v in colors[index]),
                dash=dash_pattern,
            )
        return
    if np.all(widths == widths[0]):
        cmd.segments(px0, py0, px1, py1, float(widths[0]), colors)
    else:
        for index in range(n):
            cmd.stroke(
                [
                    (float(px0[index]), float(py0[index])),
                    (float(px1[index]), float(py1[index])),
                ],
                float(widths[index]),
                tuple(int(value) for value in colors[index]),
            )


def _emit_hexbin(
    cmd: _Cmd,
    t: dict[str, Any],
    blob: bytes,
    cols: list[dict[str, Any]],
    sx: _Scale,
    sy: _Scale,
    style: dict[str, Any],
    color: str,
) -> None:
    """Expand shipped cell centers into the six-triangle hexagon fan locally
    (the payload carries centers only — see _payload._emit_hexbin)."""
    cx = _column(blob, cols[t["x"]])
    cy = _column(blob, cols[t["y"]])
    n = min(len(cx), len(cy))
    ring_x, ring_y = hexbin_ring(style)
    ring_x, ring_y = np.append(ring_x, ring_x[0]), np.append(ring_y, ring_y[0])
    x0 = np.repeat(sx(cx[:n]), 6)
    y0 = np.repeat(sy(cy[:n]), 6)
    x1 = np.asarray(sx(cx[:n, None] + ring_x[None, :-1]), dtype=np.float64).reshape(-1)
    y1 = np.asarray(sy(cy[:n, None] + ring_y[None, :-1]), dtype=np.float64).reshape(-1)
    x2 = np.asarray(sx(cx[:n, None] + ring_x[None, 1:]), dtype=np.float64).reshape(-1)
    y2 = np.asarray(sy(cy[:n, None] + ring_y[None, 1:]), dtype=np.float64).reshape(-1)

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    fills = np.repeat(
        effective_paint_rgba8(t, "color", n, color, read, component="fill", default_opacity=1.0),
        6,
        axis=0,
    )
    cmd.triangles(x0, y0, x1, y1, x2, y2, fills, 0.0, (0, 0, 0, 0))


def _emit_ribbon(
    cmd: _Cmd,
    t: dict[str, Any],
    blob: bytes,
    cols: list[dict[str, Any]],
    sx: _Scale,
    sy: _Scale,
    style: dict[str, Any],
    color: str,
) -> None:
    """Flow bands, flattened, with the gradient running along the flow.

    Geometry comes from `kernels.ribbon_polygon` (ABI 121) — the same Rust
    exporter's cubics and the golden test consume — so the two static outputs
    cannot drift. The polygon is built from the **axis-mapped** endpoints, not
    mapped after flattening: the ribbon cubic is normative in transformed space
    (ribbon geometry contract), which is the only curve the SVG exporter's
    exact pixel-space `C` and the client's clip-space sweep can both draw —
    flattening in data space and mapping each vertex bows a different curve on
    log/symlog axes. Under affine axes the two orders are the same curve.
    `cmd.grad` takes an arbitrary two-point gradient vector, which is what lets
    the ramp follow the flow rather than an axis.
    """
    x0v = _column(blob, cols[t["x0"]])
    x1v = _column(blob, cols[t["x1"]])
    slo = _column(blob, cols[t["y0"]])
    shi = _column(blob, cols[t["y1"]])
    tlo = _column(blob, cols[t["target_y0"]])
    thi = _column(blob, cols[t["target_y1"]])
    n = len(x0v)

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    source_rgba, fills, fills2 = _paint.ribbon_fill_rgba8(t, n, color, read, default_opacity=1.0)
    stroke_width = float(style.get("stroke_width", 0.0) or 0.0)
    # Outline alpha folds opacity * stroke_opacity, the same stack every other
    # stroked mark applies and the SVG writer's stroke-opacity mirrors. An
    # omitted stroke colour matches each band's own fill (edgecolors="face"),
    # resolved per band in the loop rather than once for the whole trace.
    stroke_op = _stroke_opacity(style)
    stroke_c = (
        _rgba(style.get("stroke"), color, stroke_op)
        if stroke_width > 0 and style.get("stroke") is not None
        else None
    )
    edges = None
    if stroke_width > 0 and style.get("stroke") is None:
        folded = np.column_stack([source_rgba[:, :3], source_rgba[:, 3] * stroke_op])
        edges = _rgba8(folded)

    for i in range(n):
        px0, px1 = float(sx(x0v[i])), float(sx(x1v[i]))
        py_slo, py_shi = float(sy(slo[i])), float(sy(shi[i]))
        py_tlo, py_thi = float(sy(tlo[i])), float(sy(thi[i]))
        if not all(math.isfinite(v) for v in (px0, px1, py_slo, py_shi, py_tlo, py_thi)):
            continue
        xs, ys = kernels.ribbon_polygon(px0, px1, py_slo, py_shi, py_tlo, py_thi)
        poly = list(zip(xs.tolist(), ys.tolist(), strict=True))
        # effective_rgba already folded the trace opacity into the alpha.
        a = tuple(int(v) for v in fills[i])
        b = tuple(int(v) for v in fills2[i])
        # Flat only when all FOUR channels agree: ends differing in alpha
        # alone still ramp, and cmd.grad's RGBA stops interpolate it.
        if a == b:
            cmd.fill(poly, a)
        else:
            # Gradient vector spans the two faces horizontally; the y term is
            # irrelevant because the ramp is purely along the flow.
            gy = float(ys[0])
            cmd.grad(poly, (px0, gy), (px1, gy), [(0.0, a), (1.0, b)])
        edge_c = (
            stroke_c
            if stroke_c is not None
            else (tuple(int(v) for v in edges[i]) if edges is not None else None)
        )
        if edge_c is not None:
            cmd.stroke([*poly, poly[0]], stroke_width, edge_c)


def _emit_triangle_mesh(
    cmd: _Cmd,
    t: dict[str, Any],
    blob: bytes,
    cols: list[dict[str, Any]],
    sx: _Scale,
    sy: _Scale,
    style: dict[str, Any],
    color: str,
) -> None:
    vertices = [_column(blob, cols[t[name]]) for name in ("x0", "y0", "x1", "y1", "x2", "y2")]
    n = min(len(values) for values in vertices)

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    face_intrinsic, fills, strokes = _paint.trace_fill_and_stroke_rgba8(
        t, style, n, color, read, default_opacity=1.0
    )

    x0, y0, x1, y1, x2, y2 = vertices
    widths = _paint.style_values(t, "stroke_width", n, read, float(style.get("stroke_width", 0.0)))
    projected = (sx(x0[:n]), sy(y0[:n]), sx(x1[:n]), sy(y1[:n]), sx(x2[:n]), sy(y2[:n]))
    if n == 0:
        return
    if style.get("joined_fill") and np.all(fills == fills[0]) and np.all(widths == 0.0):
        boundary = _paint.triangle_mesh_boundary(x0, y0, x1, y1, x2, y2)
        if boundary is not None:
            cmd.fill(
                list(zip(sx(boundary[:, 0]), sy(boundary[:, 1]), strict=True)),
                tuple(int(value) for value in fills[0]),
            )
            return
    if np.all(widths == widths[0]) and np.all(strokes == strokes[0]):
        cmd.triangles(
            *projected,
            fills,
            float(widths[0]),
            tuple(int(value) for value in strokes[0]),
        )
    else:
        for index in range(n):
            cmd.triangles(
                projected[0][index : index + 1],
                projected[1][index : index + 1],
                projected[2][index : index + 1],
                projected[3][index : index + 1],
                projected[4][index : index + 1],
                projected[5][index : index + 1],
                fills[index : index + 1],
                float(widths[index]),
                tuple(int(value) for value in strokes[index]),
            )


def _bar_geom(
    cmd: _Cmd,
    x: float,
    y: float,
    w: float,
    h: float,
    style: dict[str, Any],
    fill_cmd: Callable[[list[tuple[float, float]]], None],
    stroke_c: tuple[int, ...],
    sw: float,
    tip_top: bool,
) -> None:
    r_tip, r_base = _corner_radii(style)
    if r_tip or r_base:
        poly = _rounded_rect_vertices(x, y, w, h, r_tip, r_base, tip_top)
        fill_cmd(poly)
        if sw > 0:
            cmd.stroke(poly, sw, stroke_c, closed=True)
    else:
        poly = _rect_pts(x, y, x + w, y + h)
        fill_cmd(poly)
        if sw > 0:
            cmd.stroke(poly, sw, stroke_c, closed=True)


def _polar_wedge_fill(
    cmd: _Cmd,
    style: dict[str, Any],
    color: str,
    plot: dict[str, float],
    fills: np.ndarray,
) -> Callable[[list[tuple[float, float]], int], None]:
    """Paint one flattened wedge, honoring a gradient `fill=` like the cartesian
    path does.

    The polar branches used to call `cmd.fill(poly, flat)` unconditionally, so a
    gradient reached the SVG (`fill="url(#g3)"`) and the browser but came out
    flat in the PNG — a three-way divergence with the raster the odd one out.
    Per-item colors still win when there is no gradient, since each wedge in a
    pie carries its own.
    """
    if isinstance(style.get("fill"), dict):
        grad_only, _stroke_c, _sw = _fill_maker(cmd, style, color, plot)

        def paint(poly: list[tuple[float, float]], index: int) -> None:
            grad_only(poly)
    else:

        def paint(poly: list[tuple[float, float]], index: int) -> None:
            cmd.fill(poly, tuple(int(value) for value in fills[index]))

    return paint


def _fill_maker(
    cmd: _Cmd,
    style: dict[str, Any],
    color: str,
    plot: dict[str, float],
) -> tuple[Callable[[list[tuple[float, float]]], None], tuple[int, ...], float]:
    """Return (fill_cmd, stroke_c, sw) closure honoring gradient/stroke style."""
    fill_op = _fill_opacity(style, 0.85)
    stroke_op = _stroke_opacity(style, 0.85)
    sw = float(style.get("stroke_width", 0.0))
    stroke_c = _rgba(style.get("stroke"), color, stroke_op) if sw > 0 else (0, 0, 0, 0)
    fill_spec = style.get("fill")
    if isinstance(fill_spec, dict):
        stops = [
            (o, (c[0], c[1], c[2], int(c[3] * fill_op))) for o, c in _grad_stops(fill_spec, color)
        ]

        def fill_cmd(poly: list[tuple[float, float]]) -> None:
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            bbox = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
            g0, g1 = _grad_line(
                fill_spec.get("space", "mark"), fill_spec.get("dir", "down"), bbox, plot
            )
            cmd.grad(poly, g0, g1, stops)
    else:
        flat = _rgba(style.get("color"), color, fill_op)

        def fill_cmd(poly: list[tuple[float, float]]) -> None:
            cmd.fill(poly, flat)

    return fill_cmd, stroke_c, sw


def _emit_bars(
    cmd: _Cmd,
    t: dict[str, Any],
    blob: bytes,
    cols: list[dict[str, Any]],
    sx: _Scale,
    sy: _Scale,
    style: dict[str, Any],
    color: str,
    plot: dict[str, float],
    polar: "Optional[_PolarProjection]" = None,
) -> None:
    b = t["bar"]
    pos = _column_ref(blob, cols, b["pos"])
    v1 = _column_ref(blob, cols, b["value1"])
    v0 = (
        _column_ref(blob, cols, b["value0"])
        if "value0" in b
        else np.full(len(pos), float(b.get("value0_const", 0.0)))
    )
    horizontal = b.get("orientation") == "horizontal"
    half = float(b["width"]) / 2

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    fills, strokes, widths, radii = _rect_style_arrays(t, len(pos), color, read, 0.85)
    if polar is not None:
        # Annular sectors, flattened: the display list has no arc opcode, so the
        # same wedge the SVG exporter draws with `A` ships as a polygon here.
        paint = _polar_wedge_fill(cmd, style, color, plot, fills)
        radial = np.asarray(
            polar.norm_radius(np.column_stack((np.minimum(v0, v1), np.maximum(v0, v1)))),
            dtype=np.float64,
        )
        for i in range(len(pos)):
            poly = polar_wedge_points(
                polar,
                float(pos[i]) - half,
                float(pos[i]) + half,
                float(min(v0[i], v1[i])),
                float(max(v0[i], v1[i])),
                corner_radius=float(np.max(radii[i])) if len(radii) else 0.0,
                wedge_gap=float(style.get("wedge_gap", 0.0) or 0.0),
                normalized=(float(radial[i, 0]), float(radial[i, 1])),
            )
            if len(poly) < 3:
                continue
            paint(poly, i)
            if widths[i] > 0:
                cmd.stroke(
                    [*poly, poly[0]],
                    float(widths[i]),
                    tuple(int(v) for v in strokes[i]),
                )
        return
    if not isinstance(style.get("fill"), dict) and not np.any(radii) and not np.any(widths):
        if horizontal:
            xa, xb = sx(np.minimum(v0, v1)), sx(np.maximum(v0, v1))
            ya, yb = sy(pos + half), sy(pos - half)
        else:
            xa, xb = sx(pos - half), sx(pos + half)
            ya, yb = sy(np.maximum(v0, v1)), sy(np.minimum(v0, v1))
        x0, x1 = np.minimum(xa, xb), np.maximum(xa, xb)
        y0, y1 = np.minimum(ya, yb), np.maximum(ya, yb)
        cmd.rects(x0, y0, x1, y1, fills)
        return
    if not isinstance(style.get("fill"), dict):
        for i in range(len(pos)):
            if horizontal:
                x0, x1 = float(sx(min(v0[i], v1[i]))), float(sx(max(v0[i], v1[i])))
                y0, y1 = float(sy(pos[i] + half)), float(sy(pos[i] - half))
                tip_top = True
            else:
                x0, x1 = float(sx(pos[i] - half)), float(sx(pos[i] + half))
                y0, y1 = float(sy(max(v0[i], v1[i]))), float(sy(min(v0[i], v1[i])))
                tip_top = bool(v1[i] >= v0[i])
            item_style = dict(style)
            item_style["corner_radius"] = (
                float(radii[i, 0])
                if radii.shape[1] == 1
                else [float(radii[i, 0]), float(radii[i, 1])]
            )

            def fill_item(poly: list[tuple[float, float]], index: int = i) -> None:
                cmd.fill(poly, tuple(int(value) for value in fills[index]))

            _bar_geom(
                cmd,
                min(x0, x1),
                min(y0, y1),
                abs(x1 - x0),
                abs(y1 - y0),
                item_style,
                fill_item,
                tuple(int(value) for value in strokes[i]),
                float(widths[i]),
                tip_top,
            )
        return
    fill_cmd, stroke_c, sw = _fill_maker(cmd, style, color, plot)
    for i in range(len(pos)):
        if horizontal:
            x0, x1 = float(sx(min(v0[i], v1[i]))), float(sx(max(v0[i], v1[i])))
            y0, y1 = float(sy(pos[i] + half)), float(sy(pos[i] - half))
            tip_top = True
        else:
            x0, x1 = float(sx(pos[i] - half)), float(sx(pos[i] + half))
            y0, y1 = float(sy(max(v0[i], v1[i]))), float(sy(min(v0[i], v1[i])))
            tip_top = v1[i] >= v0[i]
        x, y = min(x0, x1), min(y0, y1)
        _bar_geom(cmd, x, y, abs(x1 - x0), abs(y1 - y0), style, fill_cmd, stroke_c, sw, tip_top)


def _emit_rects(
    cmd: _Cmd,
    t: dict[str, Any],
    blob: bytes,
    cols: list[dict[str, Any]],
    sx: _Scale,
    sy: _Scale,
    style: dict[str, Any],
    color: str,
    plot: dict[str, float],
    polar: "Optional[_PolarProjection]" = None,
) -> None:
    x0v, x1v = _column(blob, cols[t["x0"]]), _column(blob, cols[t["x1"]])
    y0v, y1v = _column(blob, cols[t["y0"]]), _column(blob, cols[t["y1"]])

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    fills, strokes, widths, radii = _rect_style_arrays(t, len(x0v), color, read, 0.85)
    if polar is not None:
        # Four edge columns are an annular sector, flattened (no arc opcode).
        # This is the path unequal-width slices — a pie or donut — take.
        paint = _polar_wedge_fill(cmd, style, color, plot, fills)
        for i in range(len(x0v)):
            poly = polar_wedge_points(
                polar,
                float(x0v[i]),
                float(x1v[i]),
                float(min(y0v[i], y1v[i])),
                float(max(y0v[i], y1v[i])),
                corner_radius=float(np.max(radii[i])) if len(radii) else 0.0,
                wedge_gap=float(style.get("wedge_gap", 0.0) or 0.0),
            )
            if len(poly) < 3:
                continue
            paint(poly, i)
            if widths[i] > 0:
                cmd.stroke([*poly, poly[0]], float(widths[i]), tuple(int(v) for v in strokes[i]))
        return
    if not isinstance(style.get("fill"), dict) and not np.any(radii) and not np.any(widths):
        xa, xb = sx(x0v), sx(x1v)
        ya, yb = sy(y0v), sy(y1v)
        cmd.rects(
            np.minimum(xa, xb),
            np.minimum(ya, yb),
            np.maximum(xa, xb),
            np.maximum(ya, yb),
            fills,
        )
        return
    if not isinstance(style.get("fill"), dict):
        for i in range(len(x0v)):
            xa_, xb = float(sx(x0v[i])), float(sx(x1v[i]))
            ya_, yb = float(sy(y0v[i])), float(sy(y1v[i]))
            item_style = dict(style)
            item_style["corner_radius"] = (
                float(radii[i, 0])
                if radii.shape[1] == 1
                else [float(radii[i, 0]), float(radii[i, 1])]
            )

            def fill_item(poly: list[tuple[float, float]], index: int = i) -> None:
                cmd.fill(poly, tuple(int(value) for value in fills[index]))

            _bar_geom(
                cmd,
                min(xa_, xb),
                min(ya_, yb),
                abs(xb - xa_),
                abs(yb - ya_),
                item_style,
                fill_item,
                tuple(int(value) for value in strokes[i]),
                float(widths[i]),
                bool(y1v[i] >= y0v[i]),
            )
        return
    fill_cmd, stroke_c, sw = _fill_maker(cmd, style, color, plot)
    for i in range(len(x0v)):
        xa_, xb = float(sx(x0v[i])), float(sx(x1v[i]))
        ya_, yb = float(sy(y0v[i])), float(sy(y1v[i]))
        x, y = min(xa_, xb), min(ya_, yb)
        _bar_geom(
            cmd, x, y, abs(xb - xa_), abs(yb - ya_), style, fill_cmd, stroke_c, sw, y1v[i] >= y0v[i]
        )


def _emit_grid(
    cmd: _Cmd,
    kind: str,
    g: dict[str, Any],
    blob: bytes,
    cols: list[dict[str, Any]],
    sx: _Scale,
    sy: _Scale,
    style: dict[str, Any],
    borrowed: tuple[np.ndarray, ...] = (),
    polar: "Optional[_PolarProjection]" = None,
) -> None:
    if kind == "heatmap":
        if polar is not None:
            rgba = np.ascontiguousarray(
                polar_heatmap_rgba(
                    g,
                    blob,
                    cols,
                    style,
                    polar,
                    borrowed,
                    output_scale=cmd.s,
                )
            )
            out_h, out_w = rgba.shape[:2]
            plot = polar.plot
            cmd.image(
                plot["x"],
                plot["y"],
                plot["w"],
                plot["h"],
                out_w,
                out_h,
                rgba.tobytes(),
                nearest=True,
            )
            return
        w, h = int(g["w"]), int(g["h"])
        if not (sx.affine and sy.affine):
            # Heatmap cells are uniform in *data* space, but the native image
            # ops stretch linearly across the dest rect — on a nonlinear axis
            # the grid must first be resampled to scale coordinates (the same
            # `_svg.warp_grid_rgba` the SVG exporter uses). Density grids are
            # already scale-coordinate-uniform (§28) and skip this.
            xr, yr = g["x_range"], g["y_range"]
            rgba = warp_grid_rgba(
                _heatmap_rgba_grid(g, blob, cols, style, borrowed), xr, yr, sx, sy
            )
            oh, ow = rgba.shape[:2]
            dx, dy, dw, dh = _grid_dest_rect(xr, yr, sx, sy)
            cmd.image(
                dx, dy, dw, dh, ow, oh, np.ascontiguousarray(rgba[::-1]).tobytes(), nearest=True
            )
            return
        if "rgba_bufs" in g:
            channels = [_column(blob, cols[index]) for index in g["rgba_bufs"]]
            rgba = np.clip(np.column_stack(channels) * 255.0, 0, 255).astype(np.uint8)
            rgba[:, 3] = (rgba[:, 3].astype(np.float64) * _fill_opacity(style)).astype(np.uint8)
            rgba = rgba.reshape(h, w, 4)[::-1]
            xr, yr = g["x_range"], g["y_range"]
            dx, dy, dw, dh = _grid_dest_rect(xr, yr, sx, sy)
            cmd.image(dx, dy, dw, dh, w, h, rgba.tobytes(), nearest=True)
            return
        meta = cols[g["buf"]]
        stops = np.asarray(_colormap_stops(g.get("colormap", "viridis")), dtype=np.uint8)
        alpha = int(255 * _fill_opacity(style, 0.95))
        xr, yr = g["x_range"], g["y_range"]
        dx, dy, dw, dh = _grid_dest_rect(xr, yr, sx, sy)
        canonical = g.get("enc") == "canonical-f64"
        cmd.heatmap_image(
            dx,
            dy,
            dw,
            dh,
            w,
            h,
            meta["byte_offset"],
            stops,
            alpha,
            span=int(meta.get("span", 0)),
            canonical=canonical,
            domain=tuple(g["domain"]) if canonical else (0.0, 1.0),
        )
        return
    elif g.get("enc") == "log-u8":
        w, h = int(g["w"]), int(g["h"])
        meta = cols[g["buf"]]
        xr, yr = g["x_range"], g["y_range"]
        dx, dy, dw, dh = _grid_dest_rect(xr, yr, sx, sy)
        if g.get("rgba") is not None:
            # Mean point color per cell (LOD doc §2): rgb from the shipped
            # plane; displayed alpha is the PHYSICAL compositing of the
            # cell's points (`_svg._physical_density_alpha` — the same law
            # as _svg._density_image and the client's texture upload).
            # Precomposed here and emitted as a plain image op; the
            # count→LUT density op cannot express per-cell color.
            rgba_meta = cols[g["rgba"]]
            mean = np.frombuffer(
                blob, dtype=np.uint8, count=rgba_meta["len"], offset=rgba_meta["byte_offset"]
            ).reshape(h, w, 4)
            counts = _density_column(blob, meta, g).reshape(h, w)
            alpha = _physical_density_alpha(counts, mean[..., 3], _fill_opacity(style, 0.85))
            rgba = np.ascontiguousarray(np.dstack([mean[..., :3], alpha])[::-1])
            cmd.image(dx, dy, dw, dh, w, h, rgba.tobytes(), nearest=False)
            return
        paint_alpha = 1.0
        if g.get("color") is not None:
            red, green, blue, alpha = _parse_color(g["color"])
            stops = np.asarray([(red, green, blue), (red, green, blue)], dtype=np.uint8)
            paint_alpha = alpha / 255.0
        else:
            stops = np.asarray(_colormap_stops(g.get("colormap", "viridis")), dtype=np.uint8)
        cmd.density_image(
            dx,
            dy,
            dw,
            dh,
            w,
            h,
            meta["byte_offset"],
            float(g.get("max") or 0.0),
            stops,
            _fill_opacity(style, 0.85) * paint_alpha,
            span=int(meta.get("span", 0)),
        )
        return
    else:
        rgba, xr, yr = _compat_grid_rgba(kind, g, blob, cols, style)
        h, w = rgba.shape[0], rgba.shape[1]
    dx, dy, dw, dh = _grid_dest_rect(xr, yr, sx, sy)
    cmd.image(dx, dy, dw, dh, w, h, rgba.tobytes(), nearest=kind == "heatmap")
