"""Shared static-export SVG mark emit helpers."""

from __future__ import annotations

import base64
import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import _native, _paint, _png, kernels
from ._columns import column as _column
from ._columns import column_ref as _column_ref
from ._columns import density_column as _density_column
from ._export_heatmap import polar_heatmap_rgba
from ._export_marker_svg import (
    _SYMBOL_BUILDERS,
    _authored_marker_path_d,
)
from ._export_path_svg import _area_fill_path, _curve_path, _rounded_rect_path
from ._export_polar_svg import _polar_wedge_path
from ._export_svg_util import _cap_join_attrs, _dash_attr, _num, escape
from ._layout import _Scale, warp_grid_rgba
from ._paint import (
    _css,
    hexbin_ring,
    trace_paint_rgb_css_list,
)
from ._paint import (
    colormap_stops as _colormap_stops,
)
from ._paint import (
    corner_radii as _corner_radii,
)
from ._paint import (
    fill_opacity as _fill_opacity,
)
from ._paint import (
    heatmap_rgba_grid as _heatmap_rgba_grid,
)
from ._paint import (
    paint_rgba8 as _paint_rgba8,
)
from ._paint import (
    physical_density_alpha as _physical_density_alpha,
)
from ._paint import (
    rgb_css as _rgb_css,
)
from ._paint import (
    rgba8 as _rgba8,
)
from ._paint import (
    step_arrays as _step_arrays,
)
from ._paint import (
    stroke_opacity as _stroke_opacity,
)
from ._paint import (
    trace_paint_rgba as _trace_paint_rgba,
)
from .config import DEFAULT_PALETTE

if TYPE_CHECKING:
    from ._layout import _PolarProjection

_png_rgba = _png.png_truecolor


def _segment_marks(
    t: dict[str, Any],
    blob: bytes,
    cols: list,
    sx: _Scale,
    sy: _Scale,
    style: dict,
    color: str,
    polar: "Optional[_PolarProjection]" = None,
) -> str:
    x0 = _column(blob, cols[t["x0"]])
    x1 = _column(blob, cols[t["x1"]])
    y0 = _column(blob, cols[t["y0"]])
    y1 = _column(blob, cols[t["y1"]])
    n = len(x0)

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    colors = _paint.effective_paint_rgba(
        t, "color", n, color, read, component="stroke", default_opacity=1.0
    )
    widths = _paint.style_values(t, "width", n, read, float(style.get("width", 1.2)))
    plain_css, constant_paint = _paint.trace_paint_css_constant(t, "color", color)
    css_paint = escape(plain_css)
    if polar is None:
        px0, py0 = sx(x0), sy(y0)
        px1, py1 = sx(x1), sy(y1)
        keep = np.ones(n, dtype=bool)
    else:
        px0, py0, px1, py1, keep = _paint.polar_clip_line_segments(polar, x0, y0, x1, y1)
    return "".join(
        f'<line x1="{_num(float(px0[i]))}" y1="{_num(float(py0[i]))}" '
        f'x2="{_num(float(px1[i]))}" y2="{_num(float(py1[i]))}" '
        f'stroke="{css_paint if constant_paint else _rgb_css(colors[i])}" '
        f'stroke-opacity="{_num(float(colors[i, 3]))}" '
        f'stroke-width="{_num(float(widths[i]))}" fill="none" stroke-linecap="round"'
        f"{_dash_attr(style)}/>"
        for i in range(len(x0))
        if keep[i]
    )


#: Markers per emitted string block. One SVG element per point means the mark
#: list is the document, and a list of N short strings costs ~50 bytes of object
#: header each on top of the markup — 40% overhead at 100k points, live at the
#: same time as the joined result. Collapsing every block keeps the per-object
#: overhead bounded while staying a single linear pass (byte-identical output:
#: concatenation is associative).
_SVG_MARK_BLOCK = 4096


def _scatter_marks(
    t: dict,
    blob: bytes,
    cols: list,
    sx: _Scale,
    sy: _Scale,
    style: dict,
    fallback: str,
    polar: "Optional[_PolarProjection]" = None,
) -> list[str]:
    xv = _column(blob, cols[t["x"]])
    yv = _column(blob, cols[t["y"]])
    # Only the centres move under polar; the marker glyphs are pixel-space
    # around each centre and stay round. Out-of-range radii are culled like
    # the client shader culls them — below r_lo a point mirrors through the
    # centre INSIDE the disc, where no clip can save it.
    px, py = polar(xv, yv) if polar is not None else (sx(xv), sy(yv))
    visible = polar.position_mask(xv, yv) if polar is not None else None
    n = len(xv)

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    face_intrinsic = _trace_paint_rgba(t, "color", n, fallback, read)
    effective_trace, face_intrinsic, grouped_alpha, scalar_artist = (
        _paint.scatter_grouped_artist_alpha(t, style, face_intrinsic)
    )
    face_rgba, stroke_rgba, face_css, face_css_constant, stroke_css, stroke_css_constant = (
        _paint.scatter_svg_paint(
            t, style, effective_trace, face_intrinsic, fallback, read, default_opacity=0.8
        )
    )

    size_ch = t.get("size") or {}
    radii = _paint.scatter_radii(size_ch, read, n)

    stroke_widths = _paint.style_values(t, "stroke_width", n, read, 0.0)
    symbols = _symbol_names(t, n, read, str(style.get("symbol", "circle")))
    marker_path = style.get("marker_path")
    marker_glyph = style.get("marker_glyph")
    if not marker_path and not marker_glyph and not grouped_alpha:
        symbol_codes = np.fromiter(
            (_SYMBOL_NAMES.index(symbol) if symbol in _SYMBOL_NAMES else 0 for symbol in symbols),
            dtype=np.uint8,
            count=n,
        )
        fill_u8 = _rgba8(face_rgba)
        stroke_u8 = _rgba8(stroke_rgba)
        return [
            _native.scene_scatter_svg(
                px,
                py,
                radii * 2.0,
                fill_u8,
                stroke_u8,
                stroke_widths,
                symbol_codes,
                visible,
                face_css if face_css_constant else None,
                stroke_css if stroke_css_constant else None,
            )
        ]
    if grouped_alpha:
        fill_group = float(scalar_artist) * _fill_opacity(style, 1.0)
        stroke_group = float(scalar_artist) * _stroke_opacity(style, 1.0)
        blocks = [f'<g fill-opacity="{_num(fill_group)}" stroke-opacity="{_num(stroke_group)}">']
    else:
        blocks = ["<g>"]
    out: list[str] = []
    for i in range(n):
        if visible is not None and not visible[i]:
            continue
        fill = face_rgba[i]
        fill_value = escape(face_css) if face_css_constant else _rgb_css(fill)
        fill_attr = f' fill="{fill_value}"' + (
            f' fill-opacity="{_num(float(fill[3]))}"' if float(fill[3]) < 1.0 else ""
        )
        symbol = symbols[i]
        builder = _SYMBOL_BUILDERS.get(symbol)
        authored_line = bool(marker_path) and not bool(marker_path.get("filled", True))
        line_symbol = (
            symbol
            in {
                "plus_line",
                "x_line",
                "horizontal_line",
                "vertical_line",
            }
            or authored_line
        )
        stroke_w = float(stroke_widths[i])
        if line_symbol and stroke_w <= 0:
            stroke_w = 1.0
        stroke_color = stroke_rgba[i]
        stroke_value = (
            fill_value
            if authored_line
            else escape(stroke_css)
            if stroke_css_constant
            else _rgb_css(stroke_color)
        )
        stroke_attr = (
            f' stroke="{stroke_value}"'
            + (
                f' stroke-opacity="{_num(float(stroke_color[3]))}"'
                if float(stroke_color[3]) < 1.0
                else ""
            )
            + f' stroke-width="{_num(stroke_w)}"'
            if stroke_w > 0 or line_symbol
            else ""
        )
        # `size` includes the edge; SVG strokes are centered on the path.
        marker_radius = max(0.0, float(radii[i]) - stroke_w / 2)
        if marker_glyph:
            out.append(
                f'<text x="{_num(px[i])}" y="{_num(py[i])}" '
                f'font-family="DejaVu Sans" font-size="{_num(2 * marker_radius)}" '
                f'text-anchor="middle" dominant-baseline="central"'
                f"{fill_attr}{stroke_attr}>{escape(str(marker_glyph))}</text>"
            )
        elif marker_path:
            d = _authored_marker_path_d(marker_path, float(px[i]), float(py[i]), 2 * marker_radius)
            authored_fill = fill_attr if bool(marker_path.get("filled", True)) else ' fill="none"'
            out.append(f'<path d="{d}"{authored_fill}{stroke_attr}/>')
        elif builder is None:
            out.append(
                f'<circle cx="{_num(px[i])}" cy="{_num(py[i])}" r="{_num(marker_radius)}"'
                f"{fill_attr}{stroke_attr}/>"
            )
        else:
            out.append(
                builder(float(px[i]), float(py[i]), marker_radius) + f"{fill_attr}{stroke_attr}/>"
            )
        if len(out) >= _SVG_MARK_BLOCK:
            blocks.append("".join(out))
            out.clear()
    if out:
        blocks.append("".join(out))
    blocks.append("</g>")
    return blocks


_SYMBOL_NAMES = (
    "circle",
    "square",
    "diamond",
    "triangle",
    "cross",
    "hexagon",
    "pentagon",
    "star",
    "triangle_down",
    "triangle_left",
    "triangle_right",
    "x",
    "point",
    "pixel",
    "thin_diamond",
    "plus_line",
    "x_line",
    "horizontal_line",
    "vertical_line",
)


def _symbol_names(
    trace: dict[str, Any], n: int, read: _paint.ColumnReader, fallback: str
) -> list[str]:
    channel = (trace.get("channels") or {}).get("symbol")
    if channel is None:
        return [fallback] * n
    codes = np.asarray(read(int(channel["buf"])), dtype=np.uint8)[:n]
    return [
        _SYMBOL_NAMES[int(code)] if int(code) < len(_SYMBOL_NAMES) else fallback for code in codes
    ]


def _hexbin_marks(
    t: dict, blob: bytes, cols: list, sx: _Scale, sy: _Scale, style: dict, fallback: str
) -> str:
    """One hexagon polygon per cell, expanded locally from shipped centers."""
    cx = _column(blob, cols[t["x"]])
    cy = _column(blob, cols[t["y"]])
    n = min(len(cx), len(cy))

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    fills = trace_paint_rgb_css_list(t, "color", n, fallback, read)
    ring_x, ring_y = hexbin_ring(style)
    xs = np.asarray(sx(cx[:n, None] + ring_x[None, :]), dtype=np.float64)
    ys = np.asarray(sy(cy[:n, None] + ring_y[None, :]), dtype=np.float64)
    fill_op = _fill_opacity(style)
    group_attr = (
        f' fill-opacity="{_num(fill_op)}" stroke-opacity="{_num(fill_op)}"' if fill_op < 1 else ""
    )
    out = [f"<g{group_attr}>"]
    for i in range(n):
        points = " ".join(
            f"{_num(float(x))},{_num(float(y))}" for x, y in zip(xs[i], ys[i], strict=True)
        )
        paint = escape(fills[i])
        # Matplotlib's default ``edgecolors="face"`` covers antialiasing
        # cracks where adjacent hexagons meet. A same-color hairline preserves
        # the face color while preventing white striping in vector viewers.
        out.append(
            f'<polygon points="{points}" fill="{paint}" stroke="{paint}" '
            'stroke-width="0.5" stroke-linejoin="round"/>'
        )
    out.append("</g>")
    return "".join(out)


def _ribbon_marks(
    t: dict,
    blob: bytes,
    cols: list,
    sx: _Scale,
    sy: _Scale,
    style: dict,
    fallback: str,
    svg: Any,
) -> str:
    """Flow bands as one `<path>` each: exact cubics, gradient along the flow.

    A single path per band, never a mesh — the seam-free mesh route requires one
    uniform colour, which is exactly what a two-ended ribbon is not (see the
    ribbon geometry contract). When both ends resolve to the same paint the
    band gets a plain `fill=` rather than a one-colour gradient, so an ordinary
    Sankey stays small.
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

    source_rgba, fills, fills2 = _paint.ribbon_fill_rgba(t, n, fallback, read, default_opacity=1.0)
    stroke_css = style.get("stroke")
    stroke_width = float(style.get("stroke_width", 0.0) or 0.0)
    stroke_op = _stroke_opacity(style)
    # An omitted stroke colour matches the band's own fill per band
    # (edgecolors="face"), so a per-band ribbon does not outline every flow in
    # one arbitrary colour. Explicit strokes stay a single declared paint.
    stroke_paint = None if stroke_css is None else escape(_css(stroke_css, fallback))

    out: list[str] = []
    for i in range(n):
        px0, px1 = float(sx(x0v[i])), float(sx(x1v[i]))
        y_slo, y_shi = float(sy(slo[i])), float(sy(shi[i]))
        y_tlo, y_thi = float(sy(tlo[i])), float(sy(thi[i]))
        if not all(math.isfinite(v) for v in (px0, px1, y_slo, y_shi, y_tlo, y_thi)):
            continue
        # Control points at the horizontal midpoint holding each end's own y:
        # the band leaves and arrives horizontally (ribbon geometry contract).
        mid = (px0 + px1) / 2.0
        d = (
            f"M {_num(px0)} {_num(y_shi)} "
            f"C {_num(mid)} {_num(y_shi)} {_num(mid)} {_num(y_thi)} {_num(px1)} {_num(y_thi)} "
            f"L {_num(px1)} {_num(y_tlo)} "
            f"C {_num(mid)} {_num(y_tlo)} {_num(mid)} {_num(y_slo)} {_num(px0)} {_num(y_slo)} Z"
        )
        a, b = fills[i], fills2[i]
        rgb_same = all(abs(float(a[k]) - float(b[k])) < 1e-9 for k in range(3))
        # effective_rgba already folded the trace opacity into the channel
        # alpha; folding _fill_opacity in again squared it (0.4 -> 0.16).
        alpha_a, alpha_b = float(a[3]), float(b[3])
        alpha_same = abs(alpha_a - alpha_b) < 1e-9
        if rgb_same and alpha_same:
            paint = f'fill="{_rgb_css(a)}"'
            attrs = paint + (f' fill-opacity="{_num(alpha_a)}"' if alpha_a < 1 else "")
        elif alpha_same:
            ramp = svg.gradient_vector(
                px0, 0.0, px1, 0.0, [(0.0, _rgb_css(a), 1.0), (1.0, _rgb_css(b), 1.0)]
            )
            attrs = f'fill="{ramp}"' + (f' fill-opacity="{_num(alpha_a)}"' if alpha_a < 1 else "")
        else:
            # Differing endpoint alphas ride per-stop stop-opacity so the
            # alpha channel interpolates along the flow like the RGB channels
            # (the raster and the client already do); a path-level
            # fill-opacity would flatten both ends to the source's alpha.
            ramp = svg.gradient_vector(
                px0, 0.0, px1, 0.0, [(0.0, _rgb_css(a), alpha_a), (1.0, _rgb_css(b), alpha_b)]
            )
            attrs = f'fill="{ramp}"'
        if stroke_width > 0:
            paint_css = stroke_paint if stroke_paint is not None else _rgb_css(source_rgba[i])
            # The band paint's own alpha rides the stroke stack, exactly as
            # `effective_rgba` folds it into the fill.
            edge_op = stroke_op * (1.0 if stroke_paint is not None else float(source_rgba[i][3]))
            attrs += f' stroke="{paint_css}" stroke-width="{_num(stroke_width)}" '
            if edge_op < 1:
                attrs += f'stroke-opacity="{_num(edge_op)}" '
        out.append(f'<path d="{d}" {attrs}/>')
    return "".join(out)


def _triangle_mesh_marks(
    t: dict, blob: bytes, cols: list, sx: _Scale, sy: _Scale, style: dict, fallback: str
) -> str:
    vertices = [_column(blob, cols[t[name]]) for name in ("x0", "y0", "x1", "y1", "x2", "y2")]
    n = min(len(values) for values in vertices)

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    face, fills, strokes = _paint.trace_fill_and_stroke_rgba(
        t, style, n, fallback, read, default_opacity=1.0
    )
    stroke_widths = _paint.style_values(
        t, "stroke_width", n, read, float(style.get("stroke_width", 0.0))
    )
    x0, y0, x1, y1, x2, y2 = vertices
    if (
        style.get("joined_fill")
        and n
        and np.all(fills == fills[0])
        and np.all(stroke_widths == 0.0)
    ):
        boundary = _paint.triangle_mesh_boundary(x0, y0, x1, y1, x2, y2)
        if boundary is not None:
            points = " ".join(f"{_num(float(sx(x)))},{_num(float(sy(y)))}" for x, y in boundary)
            fill = fills[0]
            return (
                f'<polygon points="{points}" fill="{_rgb_css(fill)}" '
                f'fill-opacity="{_num(float(fill[3]))}"/>'
            )
    out = ["<g>"]
    for i in range(n):
        points = " ".join(
            f"{_num(float(sx(x)))},{_num(float(sy(y)))}"
            for x, y in ((x0[i], y0[i]), (x1[i], y1[i]), (x2[i], y2[i]))
        )
        fill = fills[i]
        attrs = f' fill="{_rgb_css(fill)}" fill-opacity="{_num(float(fill[3]))}"'
        if stroke_widths[i] > 0:
            stroke = strokes[i]
            attrs += (
                f' stroke="{_rgb_css(stroke)}" stroke-opacity="{_num(float(stroke[3]))}" '
                f'stroke-width="{_num(float(stroke_widths[i]))}"'
            )
        out.append(f'<polygon points="{points}"{attrs}/>')
    out.append("</g>")
    return "".join(out)


def _bar_fill(style: dict, color: str, svg: Any, plot: dict) -> tuple[str, str]:
    fill_spec = style.get("fill")
    fill = svg.gradient(fill_spec, color, plot) if isinstance(fill_spec, dict) else escape(color)
    fill_op = _fill_opacity(style, 0.85)
    stroke_op = _stroke_opacity(style, 0.85)
    stroke_w = float(style.get("stroke_width", 0.0))
    stroke = _css(style.get("stroke"), color) if stroke_w else None
    extra = f' fill-opacity="{_num(fill_op)}"' if fill_op < 1 else ""
    if stroke:
        extra += f' stroke="{escape(stroke)}" stroke-width="{_num(stroke_w)}"'
        if stroke_op < 1:
            extra += f' stroke-opacity="{_num(stroke_op)}"'
    return fill, extra


def _rect_svg_styles(
    trace: dict[str, Any],
    n: int,
    fallback: str,
    read: _paint.ColumnReader,
    style: dict[str, Any],
    svg: Any,
    plot: dict[str, Any],
) -> tuple[list[str], list[str], np.ndarray]:
    """Resolve per-rectangle SVG fill/stroke attributes and radii."""
    radius_channel = _paint.style_matrix(trace, "corner_radius", n, read)
    if radius_channel is None:
        tip, base = _corner_radii(style)
        radii = np.tile(np.asarray([[tip, base]], dtype=np.float64), (n, 1))
    elif radius_channel.shape[1] == 1:
        radii = np.repeat(radius_channel, 2, axis=1)
    else:
        radii = radius_channel
    if isinstance(style.get("fill"), dict):
        fill, extra = _bar_fill(style, fallback, svg, plot)
        return [fill] * n, [extra] * n, radii

    face, fills_rgba, strokes = _paint.trace_fill_and_stroke_rgba(
        trace, style, n, fallback, read, default_opacity=0.85
    )
    widths = _paint.style_values(
        trace, "stroke_width", n, read, float(style.get("stroke_width", 0.0))
    )
    fills: list[str] = []
    extras: list[str] = []
    for fill, stroke, width in zip(fills_rgba, strokes, widths, strict=True):
        fills.append(_rgb_css(fill))
        extra = f' fill-opacity="{_num(float(fill[3]))}"'
        if width > 0:
            extra += (
                f' stroke="{_rgb_css(stroke)}" stroke-opacity="{_num(float(stroke[3]))}" '
                f'stroke-width="{_num(float(width))}"'
            )
        extras.append(extra)
    return fills, extras, radii


def _bar_marks(
    t: dict,
    blob: bytes,
    cols: list,
    sx: _Scale,
    sy: _Scale,
    style: dict,
    color: str,
    svg: Any,
    plot: dict,
    polar: "Optional[_PolarProjection]" = None,
) -> str:
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

    fills, extras, radii = _rect_svg_styles(t, len(pos), color, read, style, svg, plot)
    out = []
    if polar is not None:
        # Annular sectors. SVG has real arcs, so these are exact `A` commands
        # rather than the flattened polygons the raster path needs.
        radial = np.asarray(
            polar.norm_radius(np.column_stack((np.minimum(v0, v1), np.maximum(v0, v1)))),
            dtype=np.float64,
        )
        for i in range(len(pos)):
            d = _polar_wedge_path(
                polar,
                float(pos[i]) - half,
                float(pos[i]) + half,
                float(min(v0[i], v1[i])),
                float(max(v0[i], v1[i])),
                float(np.max(radii[i])) if radii is not None and len(radii) else 0.0,
                float(style.get("wedge_gap", 0.0) or 0.0),
                normalized=(float(radial[i, 0]), float(radial[i, 1])),
            )
            if d:
                out.append(f'<path d="{d}" fill="{fills[i]}"{extras[i]}/>')
        return "".join(out)
    for i in range(len(pos)):
        if horizontal:
            x0, x1 = float(sx(min(v0[i], v1[i]))), float(sx(max(v0[i], v1[i])))
            y0, y1 = float(sy(pos[i] + half)), float(sy(pos[i] - half))
        else:
            x0, x1 = float(sx(pos[i] - half)), float(sx(pos[i] + half))
            y0, y1 = float(sy(max(v0[i], v1[i]))), float(sy(min(v0[i], v1[i])))
        w, h = abs(x1 - x0), abs(y1 - y0)
        x, y = min(x0, x1), min(y0, y1)
        r_tip, r_base = radii[i]
        if r_tip or r_base:
            tip_top = not horizontal and v1[i] >= v0[i]
            d = _rounded_rect_path(x, y, w, h, r_tip, r_base, tip_top or horizontal)
            out.append(f'<path d="{d}" fill="{fills[i]}"{extras[i]}/>')
        else:
            out.append(
                f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" '
                f'fill="{fills[i]}"{extras[i]}/>'
            )
    return "".join(out)


def _rect_marks(
    t: dict,
    blob: bytes,
    cols: list,
    sx: _Scale,
    sy: _Scale,
    style: dict,
    color: str,
    svg: Any,
    plot: dict,
    polar: "Optional[_PolarProjection]" = None,
) -> str:
    x0v = _column(blob, cols[t["x0"]])
    x1v = _column(blob, cols[t["x1"]])
    y0v = _column(blob, cols[t["y0"]])
    y1v = _column(blob, cols[t["y1"]])

    def read(index: int) -> np.ndarray:
        return _column(blob, cols[index])

    fills, extras, radii = _rect_svg_styles(t, len(x0v), color, read, style, svg, plot)
    out = []
    if polar is not None:
        # Four edge columns are an annular sector: (x0, x1) is the angular span
        # and (y0, y1) the radial one. This is the path unequal-width slices (a
        # pie or donut) take, since the compact bar path ships one scalar width.
        out = []
        for i in range(len(x0v)):
            d = _polar_wedge_path(
                polar,
                float(x0v[i]),
                float(x1v[i]),
                float(min(y0v[i], y1v[i])),
                float(max(y0v[i], y1v[i])),
                float(np.max(radii[i])) if radii is not None and len(radii) else 0.0,
                float(style.get("wedge_gap", 0.0) or 0.0),
            )
            if d:
                out.append(f'<path d="{d}" fill="{fills[i]}"{extras[i]}/>')
        return "".join(out)
    for i in range(len(x0v)):
        xa_, xb = float(sx(x0v[i])), float(sx(x1v[i]))
        ya_, yb = float(sy(y0v[i])), float(sy(y1v[i]))
        x, y = min(xa_, xb), min(ya_, yb)
        w, h = abs(xb - xa_), abs(yb - ya_)
        r_tip, r_base = radii[i]
        if r_tip or r_base:
            d = _rounded_rect_path(x, y, w, h, r_tip, r_base, y1v[i] >= y0v[i])
            out.append(f'<path d="{d}" fill="{fills[i]}"{extras[i]}/>')
        else:
            out.append(
                f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" '
                f'fill="{fills[i]}"{extras[i]}/>'
            )
    return "".join(out)


def _grid_image(
    w: int, h: int, rgba: bytes, x_range: list, y_range: list, sx: _Scale, sy: _Scale
) -> str:
    px0, px1 = float(sx(x_range[0])), float(sx(x_range[1]))
    py0, py1 = float(sy(y_range[1])), float(sy(y_range[0]))  # grid row 0 = y_range bottom
    b64 = base64.b64encode(_png_rgba(w, h, rgba)).decode("ascii")
    return (
        f'<image x="{_num(min(px0, px1))}" y="{_num(min(py0, py1))}" '
        f'width="{_num(abs(px1 - px0))}" height="{_num(abs(py1 - py0))}" '
        f'preserveAspectRatio="none" style="image-rendering:pixelated" '
        f'href="data:image/png;base64,{b64}"/>'
    )


def _density_image(
    d: dict, blob: bytes, cols: list, sx: _Scale, sy: _Scale, style: dict, svg: Any
) -> str:
    w, h = int(d["w"]), int(d["h"])
    gmax = float(d.get("max") or 1.0) or 1.0
    paint_alpha: float = 1.0
    if d.get("rgba") is not None:
        grid = _density_column(blob, cols[d["buf"]], d).reshape(h, w)
        # Mean point color per cell (LOD doc §2): rgb from the shipped plane;
        # displayed alpha is the PHYSICAL compositing of the cell's points —
        # 1 − (1 − a_pt)^count for drawn per-point alpha a_pt = channel alpha
        # × style opacity (folded INSIDE the exponent: dense cells saturate
        # past the style opacity exactly like overplotted marks). Same law as
        # the client's texture upload.
        meta = cols[d["rgba"]]
        mean = np.frombuffer(
            blob, dtype=np.uint8, count=meta["len"], offset=meta["byte_offset"]
        ).reshape(h, w, 4)
        rgb = mean[..., :3]
        alpha = _physical_density_alpha(grid, mean[..., 3], _fill_opacity(style, 0.85))
        rgba = np.dstack([rgb, alpha])[::-1].tobytes()  # flip: PNG rows are top-first
        return _grid_image(w, h, rgba, d["x_range"], d["y_range"], sx, sy)
    if d.get("color") is not None:
        red, green, blue, alpha8 = _paint_rgba8(d["color"])
        paint_alpha = alpha8 / 255.0
    if d.get("enc") == "log-u8":
        meta = cols[d["buf"]]
        encoded = np.frombuffer(blob, dtype=np.uint8, count=meta["len"], offset=meta["byte_offset"])
        if d.get("color") is not None:
            stops = np.asarray([(red, green, blue), (red, green, blue)], dtype=np.uint8)
        else:
            stops = np.asarray(_colormap_stops(d.get("colormap", "viridis")), dtype=np.uint8)
        rgba = kernels.density_rgba(
            encoded,
            w,
            h,
            gmax,
            stops,
            _fill_opacity(style, 0.85) * paint_alpha,
        )
        return _grid_image(w, h, rgba.tobytes(), d["x_range"], d["y_range"], sx, sy)
    grid = _density_column(blob, cols[d["buf"]], d).reshape(h, w)
    if d.get("color") is not None:
        stops = np.asarray([(red, green, blue), (red, green, blue)], dtype=np.uint8)
    else:
        stops = np.asarray(_colormap_stops(d.get("colormap", "viridis")), dtype=np.uint8)
    rgba = kernels.density_rgba_linear(
        grid,
        w,
        h,
        gmax,
        stops,
        _fill_opacity(style, 0.85) * paint_alpha,
    )
    return _grid_image(w, h, rgba.tobytes(), d["x_range"], d["y_range"], sx, sy)


def _heatmap_image(
    hm: dict,
    blob: bytes,
    cols: list,
    sx: _Scale,
    sy: _Scale,
    style: dict,
    polar: "Optional[_PolarProjection]" = None,
) -> str:
    if polar is not None:
        grid_rgba = polar_heatmap_rgba(hm, blob, cols, style, polar)
        out_h, out_w = grid_rgba.shape[:2]
        b64 = base64.b64encode(_png_rgba(out_w, out_h, grid_rgba.tobytes())).decode("ascii")
        plot = polar.plot
        return (
            f'<image data-xy-polar-heatmap="true" x="{_num(plot["x"])}" '
            f'y="{_num(plot["y"])}" width="{_num(plot["w"])}" height="{_num(plot["h"])}" '
            f'preserveAspectRatio="none" style="image-rendering:pixelated" '
            f'href="data:image/png;base64,{b64}"/>'
        )
    grid_rgba = _heatmap_rgba_grid(hm, blob, cols, style)
    # Heatmap cells are uniform in *data* space; on a nonlinear axis the image
    # must be resampled so internal cell edges land at their transformed
    # positions, not on a linear stretch between the endpoints.
    grid_rgba = warp_grid_rgba(grid_rgba, hm["x_range"], hm["y_range"], sx, sy)
    out_h, out_w = grid_rgba.shape[:2]
    rgba = grid_rgba[::-1].tobytes()
    return _grid_image(out_w, out_h, rgba, hm["x_range"], hm["y_range"], sx, sy)


def _svg_trace_marks(
    spec: dict[str, Any],
    blob: bytes,
    cols: list,
    plot: dict[str, float],
    sx: _Scale,
    sy: _Scale,
    x_scales: dict[str, _Scale],
    y_scales: dict[str, _Scale],
    svg: Any,
    polar: "Optional[_PolarProjection]",
    *,
    palette_cycle: int = 0,
) -> tuple[list[str], int]:
    marks: list[str] = []
    # The chart's categorical cycle (`xyg.theme(palette=...)`), else the
    # built-in default. Traces normally carry a baked style color; this is the
    # fallback for specs that do not.
    spec_palette: Sequence[str] = spec.get("palette") or DEFAULT_PALETTE
    palette_cycle = 0

    def line_attrs(style: dict[str, Any], color: str) -> str:
        w = float(style.get("width", 1.5))
        op = _stroke_opacity(style)
        return (
            f'stroke="{escape(color)}" stroke-width="{_num(w)}" fill="none" '
            + _cap_join_attrs(style)
            + (f' stroke-opacity="{_num(op)}"' if op < 1 else "")
            + _dash_attr(style)
        )

    for t in spec["traces"]:
        style = t.get("style") or {}
        kind = t["kind"]
        tier = t.get("tier")
        color = _css(style.get("color"), spec_palette[palette_cycle % len(spec_palette)])
        palette_cycle += 1
        trace_sx = x_scales.get(t.get("x_axis", "x"), sx)
        trace_sy = y_scales.get(t.get("y_axis", "y"), sy)

        if tier == "density" and t.get("density"):
            marks.append(_density_image(t["density"], blob, cols, trace_sx, trace_sy, style, svg))
            continue

        if kind == "line":
            xv = _column(blob, cols[t["x"]])
            yv = _column(blob, cols[t["y"]])
            if style.get("step"):
                xv, yv = _step_arrays(xv, yv, style["step"])
            d = _curve_path(xv, yv, trace_sx, trace_sy, style.get("curve") == "smooth", polar)
            marks.append(f'<path d="{d}" {line_attrs(style, color)}/>')

        elif kind in ("area", "error_band"):
            xv = _column(blob, cols[t["x"]])
            yv = _column(blob, cols[t["y"]])
            bv = _column(blob, cols[t["base"]])
            smooth = style.get("curve") == "smooth"
            if polar is not None:
                radial_min, radial_max = sorted((polar.r_lo, polar.r_hi))
                yv = np.clip(yv, radial_min, radial_max)
                bv = np.clip(bv, radial_min, radial_max)
            # Still needed for the (non-perimeter) outline below; the fill
            # builds its own paired paths so each visible run can close alone.
            top_path = _curve_path(xv, yv, trace_sx, trace_sy, smooth, polar)
            fill_spec = style.get("fill")
            fill = (
                svg.gradient(fill_spec, color, plot)
                if isinstance(fill_spec, dict)
                else escape(color)
            )
            op = _fill_opacity(style, 0.35)
            # A polar area can be culled away entirely — every vertex outside
            # the authored sector, or a log radial axis annihilating each row —
            # or split into several visible runs. The flat join then produced
            # " L  Z", malformed path data that also reached the PDF
            # converter's _parse_path, or stitched the first top run onto the
            # base with a stray L. Close each visible run on its own.
            joined = _area_fill_path(xv, yv, bv, trace_sx, trace_sy, smooth, polar)
            if joined:
                marks.append(f'<path d="{joined}" fill="{fill}" fill-opacity="{_num(op)}"/>')
            lw = float(style.get("line_width", 1.2))
            if lw > 0 and (joined or top_path):
                lop = _stroke_opacity(style, 0.35) * float(style.get("line_opacity", 1.0))
                line_color = style.get("line_color") or color
                outline_path = joined if style.get("stroke_perimeter") else top_path
                marks.append(
                    f'<path d="{outline_path}" stroke="{escape(line_color)}" stroke-width="{_num(lw)}" '
                    'fill="none"'
                    # The area outline named its join but inherited SVG's `butt`
                    # cap, while the native rasterizer capped it round. Naming
                    # both settles that on the rasterizer's answer.
                    + _cap_join_attrs(style)
                    + (f' stroke-opacity="{_num(lop)}"' if lop < 1 else "")
                    + _dash_attr(style)
                    + "/>"
                )

        elif kind == "scatter":
            marks.extend(_scatter_marks(t, blob, cols, trace_sx, trace_sy, style, color, polar))

        elif kind == "hexbin":
            marks.append(_hexbin_marks(t, blob, cols, trace_sx, trace_sy, style, color))

        elif kind in {"errorbar", "stem", "box_whisker", "box_median", "contour", "segments"}:
            marks.append(_segment_marks(t, blob, cols, trace_sx, trace_sy, style, color, polar))

        elif kind in ("bar", "column") and t.get("bar"):
            marks.append(
                _bar_marks(t, blob, cols, trace_sx, trace_sy, style, color, svg, plot, polar)
            )

        elif kind == "heatmap" and t.get("heatmap"):
            marks.append(_heatmap_image(t["heatmap"], blob, cols, trace_sx, trace_sy, style, polar))

        elif kind == "triangle_mesh":
            marks.append(_triangle_mesh_marks(t, blob, cols, trace_sx, trace_sy, style, color))

        elif kind == "ribbon":
            # MUST precede the rect fall-through below: a ribbon ships
            # x0/x1/y0/y1 too, so a later branch would silently draw every
            # flow band as a rectangle.
            marks.append(_ribbon_marks(t, blob, cols, trace_sx, trace_sy, style, color, svg))

        elif all(k in t for k in ("x0", "x1", "y0", "y1")):  # histogram / rect family
            marks.append(
                _rect_marks(t, blob, cols, trace_sx, trace_sy, style, color, svg, plot, polar)
            )

    return marks, palette_cycle
