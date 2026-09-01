"""Static SVG export — a pure-Python renderer over the same wire payload the
browser client consumes.

The decimation tiers make static export *screen-bounded*: `build_payload`
hands this module ≤4 line points per pixel column (M4) or a fixed density
grid, so a 100M-point figure exports as a few-hundred-KB, resolution-
independent SVG in milliseconds — no browser, no extra dependencies.

Layout, tick math, colormaps, and mark styling mirror the JS client
(`30_ticks.ts`, `10_colormaps.ts`, `50_chartview.ts`); tests assert the
ported tables stay in sync with the JS parts. Known static-export
approximations, documented in spec/api/styling.md: area mark-space gradients use
the area's bounding box (SVG has no per-column gradient); complete chart color
tokens resolve statically, while nested browser-only expressions remain
browser-dependent in SVG and use the native PNG fallback.
"""

from __future__ import annotations

from collections.abc import Sequence
from os import PathLike
from typing import Any, Optional

import numpy as np

from . import _textblock
from ._columns import column as _column
from ._export_annotations import (
    _annotation_connector_unclipped,  # noqa: F401
    _axis_label_geometry,
)
from ._export_annotations_svg import _annotation_svg
from ._export_chrome import (
    _AXIS,
    _GRID,
    _TEXT,
    _colorbar_tick_target,  # noqa: F401
    apply_export_background,
    legend_options_with_slot,
    slot_font_size,
    slot_styles,
    slot_text_color,
)
from ._export_colormap import COLORMAP_STOPS  # noqa: F401
from ._export_chrome import resolve_static_css_vars as _resolve_static_css_vars
from ._export_colorbar_svg import _colorbar
from ._export_heatmap import (
    _heatmap_sample_column,  # noqa: F401
    polar_heatmap_rgba,  # noqa: F401
)
from ._export_layout import (
    _POLAR_LABEL_ROOM,  # noqa: F401
    _POLAR_LEGEND_BAND,  # noqa: F401
    _Y_TITLE_TICK_GAP,  # noqa: F401
    _decode_title_geometry,
    _polar_label_room,  # noqa: F401
    _polar_legend_room,  # noqa: F401
    _recut_polar_plot,  # noqa: F401
    _title_entries,
    _title_metrics,
    _title_wrap_width,  # noqa: F401
    _x_axis_rooms,  # noqa: F401
    _x_axis_title_room,  # noqa: F401
    _y_axis_left_room,  # noqa: F401
    _y_tick_label_room,  # noqa: F401
    layout,
    scene_layout_rooms,  # noqa: F401
)
from ._export_legend import (
    _LEGEND_CHAR_WIDTH,  # noqa: F401
    _legend_layout,  # noqa: F401
    _legend_text_width,  # noqa: F401
    legend_clip_rect,
    legend_items,
)
from ._export_legend_svg import (
    _LEGEND_LINE_KINDS,  # noqa: F401
    _legend,  # noqa: F401
    _legend_hatch_svg,  # noqa: F401
)
from ._export_marker_svg import (
    _authored_marker_path_d,  # noqa: F401
    _star_path,  # noqa: F401
)
from ._export_marks_svg import (
    _bar_marks,
    _density_image,
    _heatmap_image,
    _hexbin_marks,
    _rect_marks,
    _ribbon_marks,
    _scatter_marks,
    _segment_marks,  # noqa: F401
    _triangle_mesh_marks,
)
from ._export_path_svg import (
    _area_fill_path,
    _curve_path,
    _monotone_tangents,  # noqa: F401
)
from ._export_svg_state import _Svg
from ._export_polar_svg import (
    _polar_frame_path,
    _polar_grid,
    _polar_linear_frame_path,
    _polar_radial_tick_length,
    _polar_thin_radial_labels,
    _polar_tick_labels,
)
from ._export_svg_util import (
    _axis_grid_attrs,
    _cap_join_attrs,
    _dash_attr,
    _escape_attr,
    _num,
    _text_block_content,
    _text_cell,  # noqa: F401
    escape,
    slot_text_attrs,
)
from ._export_ticks import (
    _axis_tick_font_size,
    _axis_tick_label_baseline_shift,
    _axis_tick_label_layout,
    _axis_tick_label_offset,
    _axis_tick_label_sides,
    _axis_tick_label_strategy,
    _axis_tick_sides,
    _colorbar_right_axis_room,
    _fmt_axis,  # noqa: F401
    _fmt_log,  # noqa: F401
    _preserve_scene_chrome_for_axis_visibility,
    _tick_label_anchor,
    _tick_text,  # noqa: F401
    _tick_window,  # noqa: F401
    _tick_window_filter,  # noqa: F401
    axis_ticks,
    minor_axis_ticks,
)
from ._fontmetrics import estimated_text_width as _estimated_text_width  # noqa: F401
from ._layout import (
    THETA_ZERO,  # noqa: F401
    _PolarProjection,
    _Scale,
    _axis_scales,
    polar_wedge_points,  # noqa: F401
)
from ._paint import (
    _css,
)
from ._paint import (
    authored_marker_points as _authored_marker_points,  # noqa: F401
)
from ._paint import (
    colormap_lut as _colormap_lut,
)
from ._paint import (
    colormap_stops as _colormap_stops,  # noqa: F401
)
from ._paint import (
    physical_density_alpha as _physical_density_alpha,  # noqa: F401
)
from ._paint import (
    fill_opacity as _fill_opacity,
)
from ._paint import (
    heatmap_rgba_grid as _heatmap_rgba_grid,  # noqa: F401
)
from ._paint import (
    solid_paint as _solid_paint,
)
from ._paint import (
    step_arrays as _step_arrays,
)
from ._paint import (
    stroke_opacity as _stroke_opacity,
)
from .config import DEFAULT_PALETTE




# Unresolved CSS paints use native `STATIC_COLOR_FALLBACK_RGBA8` via
# `xyg_css_color_rgba` (76, 120, 168, 255).
_MS = {"s": 1e3, "m": 6e4, "h": 36e5, "d": 864e5}
_FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


_lut = _colormap_lut


_TEXT_ANCHORS = {"start": "start", "center": "middle", "end": "end"}


#: Text properties the VECTOR writers honor on a chrome slot (SVG, and PDF via
#: the same markup). Each maps one-to-one onto an SVG presentation attribute.
SLOT_TEXT_PROPS: tuple[str, ...] = (
    "font-size",
    "font-weight",
    "font-style",
    "font-family",
    "letter-spacing",
    "fill",
    "color",
    "opacity",
)

#: What the RASTER writer honors. The baked atlas carries a regular, a bold and
#: an italic face, so weight and style survive — a weight >= 600 rounds up to
#: the bold face (`_raster._native_font_emphasis`). It has no family axis and no
#: per-glyph advance control, so `font-family` and `letter-spacing` are
#: vector-only, and `opacity` is not read rather than being silently
#: approximated (§28). `SLOT_TEXT_PROPS` minus this tuple is the vector-only set.
SLOT_RASTER_PROPS: tuple[str, ...] = (
    "font-size",
    "font-weight",
    "font-style",
    "fill",
    "color",
)

#: Slots the native writers style. Every one names chrome that a static file
#: actually contains; the rest of `CHART_DOM_SLOTS` is live-only chrome
#: (tooltip, modebar, crosshair, selection, badge) or a container with no
#: painted text of its own, and stays browser-only.
STATIC_STYLED_SLOTS: tuple[str, ...] = (
    "title",
    "axis_title",
    "tick_label",
    "legend",
    "legend_title",
    "legend_label",
    "colorbar",
    "colorbar_title",
    "colorbar_tick",
)


# ---------------------------------------------------------------------------


# Smallest gap between the canvas edge and the outermost axis ink.
# Antialiased leading glyphs must not land on the export boundary.
_AXIS_TEXT_EDGE_PAD = 4.0
# Gap between the y title's ink and the nearest tick label's ink, as a fraction
# of the title's font size. Matplotlib leaves 5.6 px at its 13.89 px (10 pt at
# 100 dpi) default — measured with `Text.get_window_extent` on 3.11.1.


def render_svg(spec: dict[str, Any], blob: bytes, *, id_prefix: str = "") -> str:
    spec = _decode_title_geometry(spec, blob)
    spec = _resolve_static_css_vars(spec)
    spec = _preserve_scene_chrome_for_axis_visibility(spec)
    width, height, compact, plot = layout(spec)
    xa, ya = spec["x_axis"], spec["y_axis"]
    x_scales, y_scales, sx, sy, extra_x_axes, extra_y_axes = _axis_scales(spec, plot)
    svg = _Svg(id_prefix)
    cols = spec["columns"]
    # Polar reinterprets the same two axes: x carries theta, y carries r.
    polar = _PolarProjection(xa, ya, plot) if spec.get("coords") == "polar" else None
    # One plot-rect clipPath serves the marks group and every legend. Polar
    # clips to the disc instead, so nothing bleeds into the corners outside the
    # outer ring.
    clip_id = svg.uid("clip")
    # A polar legend lives in its own gutter OUTSIDE the plot rect, so the shared
    # clip has to cover the union of the two boxes or the legend is clipped away
    # entirely (`legend_clip_rect`, shared with the raster exporter).
    clip_x, clip_y, clip_w, clip_h = legend_clip_rect(plot)
    svg.defs.append(
        f'<clipPath id="{clip_id}"><rect x="{_num(clip_x)}" y="{_num(clip_y)}" '
        f'width="{_num(clip_w)}" height="{_num(clip_h)}"/></clipPath>'
    )
    # Marks clip to the disc under polar so nothing bleeds into the corners the
    # outer ring does not cover. This is a SECOND id: `clip_id` also bounds
    # every legend, and a legend sitting outside the circle would vanish.
    marks_clip_id = clip_id
    if polar is not None:
        marks_clip_id = svg.uid("clip")
        if polar.full_sector and polar.inner_fraction <= 0.0:
            svg.defs.append(
                f'<clipPath id="{marks_clip_id}"><circle cx="{_num(polar.cx)}" '
                f'cy="{_num(polar.cy)}" r="{_num(polar.radius)}"/></clipPath>'
            )
        else:
            svg.defs.append(
                f'<clipPath id="{marks_clip_id}"><path d="{_polar_frame_path(polar)}" '
                f'clip-rule="nonzero"/></clipPath>'
            )

    def ticks_for(axis: dict[str, Any], length_px: float) -> tuple[list[float], list[float], float]:
        return axis_ticks(axis, length_px, axis is xa)

    # -- grid + tick labels + baselines ------------------------------------
    xt, xlab, xstep = ticks_for(xa, plot["w"])
    yt, ylab, ystep = ticks_for(ya, plot["h"])
    if polar is not None:
        # Rings keep full density; only the labels ride the spoke.
        ylab = _polar_thin_radial_labels(ylab, _polar_radial_tick_length(polar))
    xmt, ymt = minor_axis_ticks(xa), minor_axis_ticks(ya)
    dom_style = (spec.get("dom") or {}).get("style") or {}
    xstyle, ystyle = xa.get("style") or {}, ya.get("style") or {}
    xmstyle, ymstyle = xa.get("minor_style") or {}, ya.get("minor_style") or {}
    default_grid = _css(dom_style.get("--chart-grid"), _GRID)
    default_axis = _css(dom_style.get("--chart-axis"), _AXIS)
    default_text = _css(dom_style.get("--chart-text"), _TEXT)
    slots = slot_styles(spec)
    grid: list[str] = []
    labels: list[str] = []
    # "none" silences the whole axis chrome (sparklines); "off" hides only the
    # label text and keeps grid, baselines and the axis title (mpl shared axes).
    hide_x = xa.get("tick_label_strategy") == "none"
    hide_y = ya.get("tick_label_strategy") == "none"
    if polar is not None:
        _polar_grid(grid, polar, xt, yt, xstyle, ystyle, default_grid, hide_x, hide_y)
    x_minor_px = (
        np.asarray(sx(xmt), dtype=np.float64) if polar is None and xmt else [0.0] * len(xmt)
    )
    y_minor_px = (
        np.asarray(sy(ymt), dtype=np.float64) if polar is None and ymt else [0.0] * len(ymt)
    )
    x_tick_px = np.asarray(sx(xt), dtype=np.float64) if polar is None and xt else [0.0] * len(xt)
    y_tick_px = np.asarray(sy(yt), dtype=np.float64) if polar is None and yt else [0.0] * len(yt)
    for _v, mapped in zip(xmt, x_minor_px, strict=True):
        if polar is not None:
            break
        if hide_x:
            break
        px = float(mapped)
        grid.append(
            f'<line data-xy-grid="minor" x1="{_num(px)}" y1="{_num(plot["y"])}" '
            f'x2="{_num(px)}" y2="{_num(plot["y"] + plot["h"])}" '
            f'stroke="{escape(_css(xmstyle.get("grid_color"), "transparent"))}" '
            f'stroke-width="{_num(float(xmstyle.get("grid_width", 1)))}"'
            f"{_axis_grid_attrs(xmstyle)}/>"
        )
    for _v, mapped in zip(ymt, y_minor_px, strict=True):
        if polar is not None:
            break
        if hide_y:
            break
        py = float(mapped)
        grid.append(
            f'<line data-xy-grid="minor" x1="{_num(plot["x"])}" y1="{_num(py)}" '
            f'x2="{_num(plot["x"] + plot["w"])}" y2="{_num(py)}" '
            f'stroke="{escape(_css(ymstyle.get("grid_color"), "transparent"))}" '
            f'stroke-width="{_num(float(ymstyle.get("grid_width", 1)))}"'
            f"{_axis_grid_attrs(ymstyle)}/>"
        )
    for _v, mapped in zip(xt, x_tick_px, strict=True):
        if polar is not None:
            break
        if hide_x:
            break
        px = float(mapped)
        grid.append(
            f'<line x1="{_num(px)}" y1="{_num(plot["y"])}" x2="{_num(px)}" '
            f'y2="{_num(plot["y"] + plot["h"])}" '
            f'stroke="{escape(_css(xstyle.get("grid_color"), default_grid))}" '
            f'stroke-width="{_num(float(xstyle.get("grid_width", 1)))}"'
            f"{_axis_grid_attrs(xstyle)}/>"
        )
    for _v, mapped in zip(yt, y_tick_px, strict=True):
        if polar is not None:
            break
        if hide_y:
            break
        py = float(mapped)
        grid.append(
            f'<line x1="{_num(plot["x"])}" y1="{_num(py)}" x2="{_num(plot["x"] + plot["w"])}" '
            f'y2="{_num(py)}" stroke="{escape(_css(ystyle.get("grid_color"), default_grid))}" '
            f'stroke-width="{_num(float(ystyle.get("grid_width", 1)))}"'
            f"{_axis_grid_attrs(ystyle)}/>"
        )

    def append_tick_labels(
        axis: dict[str, Any],
        values: list[float],
        step: float,
        axis_scale: _Scale,
        *,
        is_x: bool,
    ) -> None:
        axis_style = axis.get("style") or {}
        slot = slots.get("tick_label") or {}
        # The axis's own tick_label_color/tick_color is the narrower selector
        # and wins; the chart-wide slot fills in when the axis says nothing.
        color = escape(
            _css(
                axis_style.get("tick_label_color", axis_style.get("tick_color")),
                "",
            )
            or slot_text_color(slot, default_text)
        )
        font_size = slot_font_size(slot, _axis_tick_font_size(axis))
        slot_attrs = slot_text_attrs(slot)
        baseline_shift = _axis_tick_label_baseline_shift(axis)
        # An explicit tick_label_anchor (axis spec or style) overrides the
        # angle/side-derived default. Anchored labels rotate about the tick
        # point (the rotate() pivot below), so anchor and rotation compose —
        # matching the browser client.
        explicit_anchor = _tick_label_anchor(axis, axis_style, "")
        for side in _axis_tick_label_sides(axis, is_x=is_x):
            side_axis = {**axis, "side": side}
            # Unstyled defaults reproduce the pre-`tick_label_pad` placement exactly.
            if is_x:
                label_offset = (
                    _axis_tick_label_offset(axis, 7.0, 0.2)
                    if side == "top"
                    else _axis_tick_label_offset(axis, 16.0, 0.8)
                )
            else:
                label_offset = _axis_tick_label_offset(axis, 8.0)
            for item in _axis_tick_label_layout(side_axis, values, step, axis_scale, is_x):
                angle = float(item["angle"])
                block = _textblock.measure(item["text"], font_size)
                if is_x:
                    row_offset = float(item["row"]) * (font_size + 4)
                    x = float(item["pos"])
                    y = (
                        plot["y"] - label_offset - row_offset
                        if side == "top"
                        else plot["y"] + plot["h"] + label_offset + row_offset
                    )
                    if explicit_anchor:
                        anchor = _TEXT_ANCHORS[explicit_anchor]
                    elif angle == 0:
                        anchor = "middle"
                    elif (side == "bottom" and angle < 0) or (side == "top" and angle > 0):
                        anchor = "end"
                    else:
                        anchor = "start"
                else:
                    x = (
                        plot["x"] + plot["w"] + label_offset
                        if side == "right"
                        else plot["x"] - label_offset
                    )
                    y = (
                        float(item["pos"])
                        + baseline_shift
                        - (block.line_count - 1) * block.line_step / 2.0
                    )
                    if explicit_anchor:
                        anchor = _TEXT_ANCHORS[explicit_anchor]
                    else:
                        anchor = "start" if side == "right" else "end"
                transform = (
                    f' transform="rotate({_num(angle)} {_num(x)} {_num(y)})"' if angle else ""
                )
                labels.append(
                    f'<text x="{_num(x)}" y="{_num(y)}" fill="{color}" '
                    f'font-size="{_num(font_size)}" text-anchor="{anchor}"'
                    f"{slot_attrs}{transform}>"
                    f"{_text_block_content(item['text'], x, block.line_step)}</text>"
                )

    if polar is not None:
        # "off" hides only the label text (cartesian keeps grid and titles);
        # "none" — folded into hide_x/hide_y — silences the whole axis chrome.
        _polar_tick_labels(
            labels,
            polar,
            xlab,
            ylab,
            xstep,
            ystep,
            xa,
            ya,
            slots,
            default_text,
            hide_x or xa.get("tick_label_strategy") == "off",
            hide_y or ya.get("tick_label_strategy") == "off",
        )
    else:
        append_tick_labels(xa, xlab, xstep, sx, is_x=True)
        append_tick_labels(ya, ylab, ystep, sy, is_x=False)
    extra_x_ticks: dict[str, tuple[list[float], list[float], float]] = {}
    for axis_id, axis, axis_scale in extra_x_axes:
        ticks, tick_labels, step = axis_ticks(axis, plot["w"], True)
        extra_x_ticks[axis_id] = (ticks, tick_labels, step)
        append_tick_labels(axis, tick_labels, step, axis_scale, is_x=True)
    extra_y_ticks: dict[str, tuple[list[float], list[float], float]] = {}
    for axis_id, axis, axis_scale in extra_y_axes:
        ticks, tick_labels, step = axis_ticks(axis, plot["h"], False)
        extra_y_ticks[axis_id] = (ticks, tick_labels, step)
        append_tick_labels(axis, tick_labels, step, axis_scale, is_x=False)

    # -- marks --------------------------------------------------------------
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

    # -- chrome text ----------------------------------------------------------
    chrome: list[str] = []
    legacy_title = spec.get("title") if not spec.get("title_options") else None
    title_wrap_width = plot.get("title_wrap_width")
    if legacy_title:
        title_slot = slots.get("title") or {}
        legacy_size = slot_font_size(title_slot, 14.0)
        legacy_block = _textblock.measure(legacy_title, legacy_size, max_width=title_wrap_width)
        # Wrapped lines run downward from the baseline, so lift the block by its
        # trailing lines: the LAST line keeps the historical single-line baseline
        # and the extra lines fill the room `_title_room` reserved above it. A
        # one-line title has no trailing lines and is byte-identical to before.
        legacy_trailing = (legacy_block.line_count - 1) * legacy_block.line_step
        legacy_y = plot["y"] - plot["top_axis_room"] - (10 if compact else 12) - legacy_trailing
        legacy_x = width / 2
        legacy_text = "\n".join(legacy_block.lines)
        legacy_content = _text_block_content(legacy_text, legacy_x, legacy_block.line_step)
        chrome.append(
            f'<text x="{_num(legacy_x)}" '
            f'y="{_num(legacy_y)}" '
            f'text-anchor="middle" font-size="{_num(legacy_size)}"'
            f"{slot_text_attrs(title_slot, font_weight='400')} "
            f'fill="{escape(slot_text_color(title_slot, default_text))}">'
            f"{legacy_content}</text>"
        )
    for title_entry in [] if legacy_title else _title_entries(spec):
        title_style, title_size, title_block = _title_metrics(spec, title_entry, title_wrap_width)
        # Matplotlib's `axes.titleweight`/`axes.labelweight` both default to
        # "normal", so chrome text stays at 400 unless a style or rcParam asks
        # for more. Keep this in step with the `title`/`axis_title` slot rules
        # in js/src/20_theme.ts and the raster defaults in _raster.py.
        title_font_attrs = slot_text_attrs(title_style, font_weight="400")
        trailing = (title_block.line_count - 1) * title_block.line_step
        if title_entry.get("automatic_y", True):
            title_anchor_y = plot["y"] - plot["top_axis_room"]
        else:
            title_anchor_y = plot["y"] + (1.0 - float(title_entry.get("y", 1.0))) * plot["h"]
        title_y = (
            title_anchor_y - float(title_entry.get("pad", 8.0)) - title_block.descent - trailing
        )
        loc = str(title_entry.get("loc", "center"))
        title_x = {
            "left": plot["x"],
            "center": plot["x"] + plot["w"] / 2.0,
            "right": plot["x"] + plot["w"],
        }.get(loc, plot["x"] + plot["w"] / 2.0)
        anchor = {"left": "start", "center": "middle", "right": "end"}.get(loc, "middle")
        # `title_block.lines` is the wrapped set — drawing `entry["text"]` here
        # would put the whole title on one line inside a band reserved for two.
        title_content = _text_block_content(
            "\n".join(title_block.lines), title_x, title_block.line_step
        )
        chrome.append(
            f'<text x="{_num(title_x)}" '
            f'y="{_num(title_y)}" '
            f'text-anchor="{anchor}" font-size="{_num(title_size)}" '
            f"{title_font_attrs.lstrip()} "
            f'fill="{escape(slot_text_color(title_style, default_text))}">'
            f"{title_content}</text>"
        )

    def append_axis_title(axis: dict[str, Any], *, is_x: bool) -> None:
        if not axis.get("label") or _axis_tick_label_strategy(axis) == "none":
            return
        axis_style = axis.get("style") or {}
        slot = slots.get("axis_title") or {}
        geometry = _axis_label_geometry(axis, plot, is_x=is_x)
        x, y = float(geometry["x"]), float(geometry["y"])
        angle = float(geometry["angle"])
        transform = f' transform="rotate({_num(angle)} {_num(x)} {_num(y)})"' if angle else ""
        # The axis's own label_* keys are the narrower selector, so they win
        # over the chart-wide slot; the slot supplies whatever they leave unset.
        family = axis_style.get("label_font_family")
        font_style = axis_style.get("label_font_style")
        weight = axis_style.get("label_font_weight", 400)
        paint = _css(axis_style.get("label_color"), "") or slot_text_color(slot, default_text)
        font_attrs = (f' font-family="{_escape_attr(family)}"' if family is not None else "") + (
            f' font-style="{_escape_attr(font_style)}"' if font_style is not None else ""
        )
        if not font_attrs:
            font_attrs = slot_text_attrs(slot, font_weight=weight)
        else:
            font_attrs = f' font-weight="{_escape_attr(weight)}"' + font_attrs
        font_size = slot_font_size(slot, float(geometry["font_size"]))
        block = _textblock.measure(axis["label"], font_size)
        chrome.append(
            f'<text x="{_num(x)}" y="{_num(y)}" text-anchor="{geometry["anchor"]}" '
            f'font-size="{_num(font_size)}"'
            f"{font_attrs} "
            f'fill="{escape(paint)}"{transform}>'
            f"{_text_block_content(axis['label'], x, block.line_step)}</text>"
        )

    append_axis_title(xa, is_x=True)
    append_axis_title(ya, is_x=False)
    for _axis_id, axis, _axis_scale in extra_x_axes:
        append_axis_title(axis, is_x=True)
    for _axis_id, axis, _axis_scale in extra_y_axes:
        append_axis_title(axis, is_x=False)
    named = legend_items(spec["traces"], spec_palette)
    legend_label_slot = slots.get("legend_label") or {}
    legend_title_slot = slots.get("legend_title") or {}
    main_legend = spec.get("legend") or {}
    main_items = main_legend.get("items") or named
    if spec.get("show_legend", True) and main_items:
        chrome.append(
            _legend(
                main_items,
                plot,
                legend_options_with_slot(spec, main_legend),
                clip_id,
                default_text,
                spec_palette,
                legend_label_slot,
                legend_title_slot,
            )
        )
    for extra in spec.get("extra_legends") or []:
        items = extra.get("items") or []
        if items:
            chrome.append(
                _legend(
                    items,
                    plot,
                    legend_options_with_slot(spec, extra),
                    clip_id,
                    default_text,
                    spec_palette,
                    legend_label_slot,
                    legend_title_slot,
                )
            )
    if spec.get("colorbar"):
        chrome.append(
            _colorbar(
                spec["colorbar"],
                plot,
                _colorbar_right_axis_room(ya, extra_y_axes, compact),
                default_text,
                slots.get("colorbar_title") or slots.get("colorbar") or {},
                slots.get("colorbar_tick") or slots.get("colorbar") or {},
            )
        )

    annotation_marks, unclipped_annotation_marks, annotation_labels = _annotation_svg(
        spec.get("annotations") or [], sx, sy, plot, width, height, polar
    )
    marks.extend(annotation_marks)
    labels.extend(annotation_labels)

    # baselines above the marks, matching the client's overlay rules
    baselines = ""
    frame_sides = spec.get("frame_sides")
    explicit_frame_sides = frame_sides is not None
    if frame_sides is None:
        frame_sides = [xa.get("side", "bottom"), ya.get("side", "left")]
    if polar is not None:
        # One annular-sector outline replaces the four straight spines; "side"
        # has no polar meaning, so frame_sides is deliberately not consulted.
        frame_sides = []
        if not hide_x:
            frame_paint = escape(_css(xstyle.get("axis_color"), default_axis))
            frame_width = _num(float(xstyle.get("axis_width", 1)))
            if polar.full_sector and polar.inner_fraction <= 0.0 and polar.grid_shape != "linear":
                baselines += (
                    f'<circle data-xy-frame="polar" cx="{_num(polar.cx)}" '
                    f'cy="{_num(polar.cy)}" r="{_num(polar.radius)}" fill="none" '
                    f'stroke="{frame_paint}" stroke-width="{frame_width}"/>'
                )
            else:
                frame_path = (
                    _polar_linear_frame_path(polar, xt)
                    if polar.grid_shape == "linear"
                    else _polar_frame_path(polar)
                )
                baselines += (
                    f'<path data-xy-frame="polar" d="{frame_path}" fill="none" '
                    f'stroke="{frame_paint}" stroke-width="{frame_width}"/>'
                )
    if not hide_y or explicit_frame_sides:
        for side, x in (("left", plot["x"]), ("right", plot["x"] + plot["w"])):
            if side in frame_sides:
                baselines += (
                    f'<line x1="{_num(x)}" y1="{_num(plot["y"])}" x2="{_num(x)}" '
                    f'y2="{_num(plot["y"] + plot["h"])}" '
                    f'stroke="{escape(_css(ystyle.get("axis_color"), default_axis))}" '
                    f'stroke-width="{_num(float(ystyle.get("axis_width", 1)))}"/>'
                )
    if not hide_x or explicit_frame_sides:
        for side, y in (("top", plot["y"]), ("bottom", plot["y"] + plot["h"])):
            if side in frame_sides:
                baselines += (
                    f'<line x1="{_num(plot["x"])}" y1="{_num(y)}" '
                    f'x2="{_num(plot["x"] + plot["w"])}" y2="{_num(y)}" '
                    f'stroke="{escape(_css(xstyle.get("axis_color"), default_axis))}" '
                    f'stroke-width="{_num(float(xstyle.get("axis_width", 1)))}"/>'
                )
    for _axis_id, axis, _axis_scale in extra_x_axes:
        if _axis_tick_label_strategy(axis) == "none":
            continue
        axis_style = axis.get("style") or {}
        edge = plot["y"] if axis.get("side", "bottom") == "top" else plot["y"] + plot["h"]
        baselines += (
            f'<line x1="{_num(plot["x"])}" y1="{_num(edge)}" '
            f'x2="{_num(plot["x"] + plot["w"])}" y2="{_num(edge)}" '
            f'stroke="{escape(_css(axis_style.get("axis_color"), default_axis))}" '
            f'stroke-width="{_num(float(axis_style.get("axis_width", 1)))}"/>'
        )
    for _axis_id, axis, _axis_scale in extra_y_axes:
        if _axis_tick_label_strategy(axis) == "none":
            continue
        axis_style = axis.get("style") or {}
        edge = plot["x"] + plot["w"] if axis.get("side", "right") == "right" else plot["x"]
        baselines += (
            f'<line x1="{_num(edge)}" y1="{_num(plot["y"])}" x2="{_num(edge)}" '
            f'y2="{_num(plot["y"] + plot["h"])}" '
            f'stroke="{escape(_css(axis_style.get("axis_color"), default_axis))}" '
            f'stroke-width="{_num(float(axis_style.get("axis_width", 1)))}"/>'
        )

    def tick_span(style: dict[str, Any]) -> tuple[float, float, float]:
        default_length = 4 if style.get("_scene_public_chrome_defaults") else 0
        length = max(0.0, float(style.get("tick_length", default_length)))
        direction = str(style.get("tick_direction", "out"))
        if direction == "in":
            return length, 0.0, float(style.get("tick_width", 1))
        if direction == "inout":
            return length / 2, length / 2, float(style.get("tick_width", 1))
        return 0.0, length, float(style.get("tick_width", 1))

    if not hide_x and polar is None:
        inward, outward, tick_width = tick_span(xmstyle)
        side = xa.get("side", "bottom")
        edge = plot["y"] if side == "top" else plot["y"] + plot["h"]
        for value in xmt:
            x = float(sx(value))
            y1, y2 = (
                (edge - outward, edge + inward)
                if side == "top"
                else (edge - inward, edge + outward)
            )
            baselines += (
                f'<line data-xy-tick="minor" x1="{_num(x)}" y1="{_num(y1)}" '
                f'x2="{_num(x)}" y2="{_num(y2)}" '
                f'stroke="{escape(_css(xmstyle.get("tick_color"), default_axis))}" '
                f'stroke-width="{_num(tick_width)}"/>'
            )
        inward, outward, tick_width = tick_span(xstyle)
        for side in _axis_tick_sides(xa, is_x=True):
            edge = plot["y"] if side == "top" else plot["y"] + plot["h"]
            for value in xt:
                x = float(sx(value))
                y1, y2 = (
                    (edge - outward, edge + inward)
                    if side == "top"
                    else (edge - inward, edge + outward)
                )
                baselines += (
                    f'<line x1="{_num(x)}" y1="{_num(y1)}" '
                    f'x2="{_num(x)}" y2="{_num(y2)}" '
                    f'stroke="{escape(_css(xstyle.get("tick_color"), default_axis))}" '
                    f'stroke-width="{_num(tick_width)}"/>'
                )
    if not hide_y and polar is None:
        inward, outward, tick_width = tick_span(ymstyle)
        side = ya.get("side", "left")
        edge = plot["x"] + plot["w"] if side == "right" else plot["x"]
        for value in ymt:
            y = float(sy(value))
            x1, x2 = (
                (edge - inward, edge + outward)
                if side == "right"
                else (edge - outward, edge + inward)
            )
            baselines += (
                f'<line data-xy-tick="minor" x1="{_num(x1)}" y1="{_num(y)}" '
                f'x2="{_num(x2)}" y2="{_num(y)}" '
                f'stroke="{escape(_css(ymstyle.get("tick_color"), default_axis))}" '
                f'stroke-width="{_num(tick_width)}"/>'
            )
        inward, outward, tick_width = tick_span(ystyle)
        for side in _axis_tick_sides(ya, is_x=False):
            edge = plot["x"] + plot["w"] if side == "right" else plot["x"]
            for value in yt:
                y = float(sy(value))
                x1, x2 = (
                    (edge - inward, edge + outward)
                    if side == "right"
                    else (edge - outward, edge + inward)
                )
                baselines += (
                    f'<line x1="{_num(x1)}" y1="{_num(y)}" '
                    f'x2="{_num(x2)}" y2="{_num(y)}" '
                    f'stroke="{escape(_css(ystyle.get("tick_color"), default_axis))}" '
                    f'stroke-width="{_num(tick_width)}"/>'
                )
    for axis_id, axis, axis_scale in extra_x_axes:
        if _axis_tick_label_strategy(axis) == "none":
            continue
        axis_style = axis.get("style") or {}
        inward, outward, tick_width = tick_span(axis_style)
        for side in _axis_tick_sides(axis, is_x=True):
            edge = plot["y"] if side == "top" else plot["y"] + plot["h"]
            for value in extra_x_ticks[axis_id][0]:
                x = float(axis_scale(value))
                y1, y2 = (
                    (edge - outward, edge + inward)
                    if side == "top"
                    else (edge - inward, edge + outward)
                )
                baselines += (
                    f'<line x1="{_num(x)}" y1="{_num(y1)}" '
                    f'x2="{_num(x)}" y2="{_num(y2)}" '
                    f'stroke="{escape(_css(axis_style.get("tick_color"), default_axis))}" '
                    f'stroke-width="{_num(tick_width)}"/>'
                )
    for axis_id, axis, axis_scale in extra_y_axes:
        if _axis_tick_label_strategy(axis) == "none":
            continue
        axis_style = axis.get("style") or {}
        inward, outward, tick_width = tick_span(axis_style)
        for side in _axis_tick_sides(axis, is_x=False):
            edge = plot["x"] + plot["w"] if side == "right" else plot["x"]
            for value in extra_y_ticks[axis_id][0]:
                y = float(axis_scale(value))
                x1, x2 = (
                    (edge - inward, edge + outward)
                    if side == "right"
                    else (edge - outward, edge + inward)
                )
                baselines += (
                    f'<line x1="{_num(x1)}" y1="{_num(y)}" '
                    f'x2="{_num(x2)}" y2="{_num(y)}" '
                    f'stroke="{escape(_css(axis_style.get("tick_color"), default_axis))}" '
                    f'stroke-width="{_num(tick_width)}"/>'
                )

    defs = f"<defs>{''.join(svg.defs)}</defs>" if svg.defs else ""
    # Figure patch + plot-rect backgrounds, mirroring the browser: the root
    # element's CSS `background` (theme(background=)) behind everything, then
    # the --chart-bg token over the plot rect only. Solid colors only —
    # gradients stay browser-only, and an unset token stays transparent.
    backgrounds = ""
    # Export-time canvas override (unified export API `background=`): one
    # backdrop rect behind the figure patch. "transparent"/"none" mean "no
    # backdrop", which is already SVG's default — nothing to paint.
    canvas_paint = spec.get("canvas_background")
    if canvas_paint and canvas_paint not in ("transparent", "none"):
        backgrounds += f'<rect width="{width}" height="{height}" fill="{escape(canvas_paint)}"/>'
    figure_background = _solid_paint(dom_style.get("background"))
    if figure_background is not None:
        backgrounds += (
            f'<rect width="{width}" height="{height}" fill="{escape(figure_background)}"/>'
        )
    plot_paint = _solid_paint(dom_style.get("--chart-bg"))
    if plot_paint is not None:
        backgrounds += (
            f'<rect x="{_num(plot["x"])}" y="{_num(plot["y"])}" width="{_num(plot["w"])}" '
            f'height="{_num(plot["h"])}" fill="{escape(plot_paint)}"/>'
        )
    # One flat join over the pieces rather than nested `join`s inside an
    # f-string: the mark list is the whole document for a per-point chart (tens
    # of MB at 100k markers), and joining it separately would materialize a
    # second full copy of it before the result string is built.
    return "".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="{_FONT}" font-size="11">',
            defs,
            backgrounds,
            "<g>",
            *grid,
            "</g>",
            f'<g clip-path="url(#{marks_clip_id})">',
            *marks,
            "</g>",
            *unclipped_annotation_marks,
            baselines,
            f'<g fill="{escape(default_text)}">',
            *labels,
            "</g>",
            *chrome,
            "</svg>",
        ]
    )


def to_svg(
    fig: Any,
    path: Optional[str | PathLike[str]] = None,
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    id_prefix: str = "",
    background: Optional[str] = None,
) -> str:
    """Render `fig` to a standalone SVG string (optionally saved to `path`).

    `width`/`height` override the figure's pixel size (useful for fluid "100%"
    figures). Decimation runs at the export width, so output stays
    screen-bounded no matter the source size. `id_prefix` namespaces generated
    element ids for composers that inline several exports in one document.
    `background` overrides the figure canvas color ("transparent" omits the
    opaque backdrop, matching the raster exporters' alpha behavior)."""
    eff_w = (
        int(width)
        if width is not None
        else (fig.width if isinstance(fig.width, (int, float)) else 900)
    )
    spec, blob = fig.build_payload(px_width=max(256, int(eff_w)))
    if width is not None:
        spec["width"] = int(width)
    if height is not None:
        spec["height"] = int(height)
    apply_export_background(spec, background)
    out = render_svg(spec, blob, id_prefix=id_prefix)
    if path is not None:
        from .export import _atomic_write_text

        _atomic_write_text(path, out)
    return out
