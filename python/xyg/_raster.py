"""Native PNG export: build a display-list command buffer from a chart spec and
paint it with the Rust rasterizer (`kernels.rasterize`, `crates/xyg-engine/src/raster.rs`), then
encode PNG. Browser-free and screen-bounded — the same decimated payload the SVG
exporter consumes.

Reuses `_svg`'s layout/scale/tick/colormap math and ABI 121 tessellation
kernels so the raster matches the SVG (and the live chart). Shared CSS and
trace paint resolution live in `_paint.py`. Compatibility `_scene.py`
wrappers stay for tests; this emitter calls `kernels` directly (#310).
"""

from __future__ import annotations

from collections.abc import Sequence
from os import PathLike
from typing import Any, Optional

import numpy as np

from . import _png, _textblock
from ._export_annotations import (
    _axis_label_geometry,
)
from ._export_chrome import (
    _AXIS,
    _AXIS_GRID_DASHES,
    _GRID,
    _TEXT,
    apply_export_background,
    legend_options_with_slot,
    slot_font_size,
    slot_styles,
    slot_text_color,
)
from ._export_chrome import resolve_static_css_vars as _resolve_static_css_vars
from ._export_layout import (
    _decode_title_geometry,
    _title_entries,
    _title_metrics,
    layout,  # noqa: F401
)
from ._export_legend import (
    legend_clip_rect,
    legend_items,
)
from ._export_legend_raster import _emit_colorbar, _emit_legend  # noqa: F401
from ._export_marks_raster import (
    _emit_annotations,  # noqa: F401
    _emit_area,
    _emit_bars,
    _emit_grid,  # noqa: F401
    _emit_hexbin,
    _emit_line,
    _emit_rects,
    _emit_ribbon,
    _emit_scatter,
    _emit_segments,
    _emit_text_box,  # noqa: F401
    _emit_triangle_mesh,
    _native_font_emphasis,
)
from ._export_polar_raster import (
    _emit_polar_grid,
    _emit_polar_tick_labels,
    _polar_label_paint,
)
from ._export_raster_cmd import (
    _FILL,  # noqa: F401
    _STROKE,  # noqa: F401
    _STYLED_TEXT,  # noqa: F401
    _SYMBOLS,  # noqa: F401
    _TEXT_ANCHOR_CODES,
    _TEXT_BOLD,  # noqa: F401
    _TEXT_OP,  # noqa: F401
    _TEXT_ROT_CCW,  # noqa: F401
    _TEXT_ROT_CW,  # noqa: F401
    _Cmd,
    _emit_text_block,
    _rect_pts,
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
    _preserve_scene_chrome_for_axis_visibility,
    _tick_label_anchor,
    axis_ticks,
    minor_axis_ticks,
)
from ._layout import (
    _axis_scales,
    _PolarProjection,
    _Scale,
)
from ._paint import (
    _css,
)
from ._paint import (
    paint_rgba8 as _parse_color,  # noqa: F401
)
from ._paint import (
    solid_rgba8 as _solid_color,
)
from .config import DEFAULT_PALETTE


@_textblock.cached_measurements
def render_raster(
    spec: dict[str, Any],
    blob: bytes,
    scale: float = 2.0,
    *,
    fast_png: bool = False,
    borrowed: tuple[np.ndarray, ...] = (),
) -> np.ndarray | bytes:
    """Paint `spec` into an ``(h, w, 4)`` RGBA8 image via the native rasterizer."""
    spec = _decode_title_geometry(spec, blob)
    spec = _resolve_static_css_vars(spec)
    spec = _preserve_scene_chrome_for_axis_visibility(spec)
    width, height, compact, plot = layout(spec)
    xa, ya = spec["x_axis"], spec["y_axis"]
    x_scales, y_scales, sx, sy, extra_x_axes, extra_y_axes = _axis_scales(spec, plot)
    # Polar reinterprets the same two axes: x carries theta, y carries r. The
    # projection comes from _svg so the vector and raster exports cannot drift.
    polar = (
        _PolarProjection(spec["x_axis"], spec["y_axis"], plot)
        if spec.get("coords") == "polar"
        else None
    )
    cols = spec["columns"]
    cmd = _Cmd(scale)

    dom_style = (spec.get("dom") or {}).get("style") or {}

    # Figure patch (mpl figure.facecolor): `theme(background=)` lands on the
    # root element's CSS background, painted over the whole canvas so the
    # margins match the browser. Gradients stay browser-only (skipped).
    figure_background = _solid_color(dom_style.get("background"))

    # The fused PNG path initializes its native canvas white, avoiding a second
    # full-frame memory pass. Raw RGBA callers still receive an explicit fill —
    # skipped when an opaque figure background would fully cover it anyway
    # (a translucent one keeps the white underlay to composite over, matching
    # the browser's white host page).
    if not fast_png and (figure_background is None or figure_background[3] < 255):
        cmd.fill(
            _rect_pts(0, 0, width, height),
            _parse_color(spec.get("canvas_background", "#ffffff")),
        )
    if figure_background is not None:
        cmd.fill(_rect_pts(0, 0, width, height), figure_background)

    # Static exports honor the same axes background token as HTML/SVG.  This
    # is deliberately a plot-rect fill rather than a canvas fill: the latter
    # is the Figure patch, composed above (or by pyplot's grid exporter). An
    # unset token keeps the plot rect transparent when a figure background is
    # present — matching the browser, where the root shows through — and
    # falls back to the classic white fill otherwise.
    plot_css = _css(dom_style.get("--chart-bg"), "")
    if plot_css:
        plot_background = _parse_color(plot_css)
    elif figure_background is None:
        plot_background = _parse_color("#ffffff")
    else:
        plot_background = None
    if plot_background is not None:
        cmd.fill(
            _rect_pts(plot["x"], plot["y"], plot["x"] + plot["w"], plot["y"] + plot["h"]),
            plot_background,
        )

    xt, xlab, xstep = axis_ticks(xa, plot["w"], True)
    yt, ylab, ystep = axis_ticks(ya, plot["h"], False)
    xmt, ymt = minor_axis_ticks(xa), minor_axis_ticks(ya)
    extra_x_ticks = {
        axis_id: axis_ticks(axis, plot["w"], True) for axis_id, axis, _axis_scale in extra_x_axes
    }
    extra_y_ticks = {
        axis_id: axis_ticks(axis, plot["h"], False) for axis_id, axis, _axis_scale in extra_y_axes
    }
    xstyle, ystyle = xa.get("style") or {}, ya.get("style") or {}
    xmstyle, ymstyle = xa.get("minor_style") or {}, ya.get("minor_style") or {}
    default_grid = _css(dom_style.get("--chart-grid"), _GRID)
    default_axis = _css(dom_style.get("--chart-axis"), _AXIS)
    default_text = _css(dom_style.get("--chart-text"), _TEXT)
    px0, py0 = plot["x"], plot["y"]
    px1, py1 = plot["x"] + plot["w"], plot["y"] + plot["h"]

    hide_x = xa.get("tick_label_strategy") == "none"
    hide_y = ya.get("tick_label_strategy") == "none"

    cmd.clip(px0, py0, plot["w"], plot["h"])
    if polar is not None:
        _emit_polar_grid(cmd, polar, xt, yt, xstyle, ystyle, default_grid, hide_x, hide_y)
    for v in [] if hide_x or polar is not None else xmt:
        gx = float(sx(v))
        cmd.stroke(
            [(gx, py0), (gx, py1)],
            float(xmstyle.get("grid_width", 1)),
            _parse_color(
                _css(xmstyle.get("grid_color"), "transparent"),
                float(xmstyle.get("grid_opacity", 1.0)),
            ),
            dash=_AXIS_GRID_DASHES.get(str(xmstyle.get("grid_dash", "solid"))),
        )
    for v in [] if hide_y or polar is not None else ymt:
        gy = float(sy(v))
        cmd.stroke(
            [(px0, gy), (px1, gy)],
            float(ymstyle.get("grid_width", 1)),
            _parse_color(
                _css(ymstyle.get("grid_color"), "transparent"),
                float(ymstyle.get("grid_opacity", 1.0)),
            ),
            dash=_AXIS_GRID_DASHES.get(str(ymstyle.get("grid_dash", "solid"))),
        )
    for v in [] if hide_x or polar is not None else xt:
        gx = float(sx(v))
        cmd.stroke(
            [(gx, py0), (gx, py1)],
            float(xstyle.get("grid_width", 1)),
            _parse_color(
                _css(xstyle.get("grid_color"), default_grid),
                float(xstyle.get("grid_opacity", 1.0)),
            ),
            dash=_AXIS_GRID_DASHES.get(str(xstyle.get("grid_dash", "solid"))),
        )
    for v in [] if hide_y or polar is not None else yt:
        gy = float(sy(v))
        cmd.stroke(
            [(px0, gy), (px1, gy)],
            float(ystyle.get("grid_width", 1)),
            _parse_color(
                _css(ystyle.get("grid_color"), default_grid),
                float(ystyle.get("grid_opacity", 1.0)),
            ),
            dash=_AXIS_GRID_DASHES.get(str(ystyle.get("grid_dash", "solid"))),
        )

    # Grid/frame chrome is drawn before the shaped clip. Marks then share one
    # analytic annular-sector clip in the native painter, matching SVG's
    # polar clipPath without flattening every mark at the boundary.
    if polar is not None:
        cmd.polar_clip(polar)

    spec_palette: Sequence[str] = spec.get("palette") or DEFAULT_PALETTE
    for palette_i, t in enumerate(spec["traces"]):
        style = t.get("style") or {}
        color = _css(style.get("color"), spec_palette[palette_i % len(spec_palette)])
        kind = t["kind"]
        trace_sx = x_scales.get(t.get("x_axis", "x"), sx)
        trace_sy = y_scales.get(t.get("y_axis", "y"), sy)
        if t.get("tier") == "density" and t.get("density"):
            _emit_grid(cmd, "density", t["density"], blob, cols, trace_sx, trace_sy, style)
        elif kind == "line":
            _emit_line(cmd, t, blob, cols, trace_sx, trace_sy, style, color, polar)
        elif kind in ("area", "error_band"):
            _emit_area(cmd, t, blob, cols, trace_sx, trace_sy, style, color, plot, polar)
        elif kind == "scatter":
            _emit_scatter(cmd, t, blob, cols, trace_sx, trace_sy, style, color, polar)
        elif kind == "hexbin":
            _emit_hexbin(cmd, t, blob, cols, trace_sx, trace_sy, style, color)
        elif kind in {"errorbar", "stem", "box_whisker", "box_median", "contour", "segments"}:
            _emit_segments(cmd, t, blob, cols, trace_sx, trace_sy, style, color, polar)
        elif kind in ("bar", "column") and t.get("bar"):
            _emit_bars(cmd, t, blob, cols, trace_sx, trace_sy, style, color, plot, polar)
        elif kind == "heatmap" and t.get("heatmap"):
            _emit_grid(
                cmd,
                "heatmap",
                t["heatmap"],
                blob,
                cols,
                trace_sx,
                trace_sy,
                style,
                borrowed,
                polar,
            )
        elif kind == "triangle_mesh":
            _emit_triangle_mesh(cmd, t, blob, cols, trace_sx, trace_sy, style, color)
        elif kind == "ribbon":
            # MUST precede the rect fall-through: a ribbon ships x0/x1/y0/y1
            # too, so a later branch would draw every band as a rectangle.
            _emit_ribbon(cmd, t, blob, cols, trace_sx, trace_sy, style, color)
        elif all(k in t for k in ("x0", "x1", "y0", "y1")):
            _emit_rects(cmd, t, blob, cols, trace_sx, trace_sy, style, color, plot, polar)

    _emit_annotations(cmd, spec.get("annotations") or [], sx, sy, plot, width, height, polar=polar)

    # Chrome (unclipped): baselines, labels, title, legend.
    cmd.clip(0, 0, width, height)
    # Text annotations are unclipped like matplotlib Text (clip_on=False):
    # margin titles and edge labels may live outside the plot rectangle.
    _emit_annotations(
        cmd,
        spec.get("annotations") or [],
        sx,
        sy,
        plot,
        width,
        height,
        phase="text",
        polar=polar,
    )
    # "none" silences the whole axis chrome (sparklines); "off" hides only the
    # label text and keeps baselines and the axis title (mpl shared axes).
    frame_sides = spec.get("frame_sides")
    explicit_frame_sides = frame_sides is not None
    if frame_sides is None:
        frame_sides = [xa.get("side", "bottom"), ya.get("side", "left")]
    if polar is not None:
        # One annular-sector outline replaces the four straight spines; "side"
        # has no polar meaning, so frame_sides is deliberately not consulted.
        frame_sides = []
        explicit_frame_sides = False
        if not hide_x:
            width_ = float(xstyle.get("axis_width", 1))
            paint = _parse_color(_css(xstyle.get("axis_color"), default_axis))
            outer = polar.frame_points(xt)
            if outer:
                if polar.full_sector:
                    cmd.stroke([*outer, outer[0]], width_, paint)
                    if polar.inner_radius > 0.0:
                        inner = (
                            polar.polygon_ring(polar.r_lo, xt)
                            if polar.grid_shape == "linear"
                            else polar.ring(polar.r_lo)
                        )
                        if inner:
                            cmd.stroke([*inner, inner[0]], width_, paint)
                else:
                    inner = (
                        polar.polygon_ring(polar.r_lo, xt)
                        if polar.inner_radius > 0.0 and polar.grid_shape == "linear"
                        else polar.ring(polar.r_lo)
                        if polar.inner_radius > 0.0
                        else [(polar.cx, polar.cy)]
                    )
                    boundary = [*outer, *reversed(inner)]
                    cmd.stroke([*boundary, boundary[0]], width_, paint)
    if not hide_y or explicit_frame_sides:
        if "left" in frame_sides:
            cmd.stroke(
                [(px0, py0), (px0, py1)],
                float(ystyle.get("axis_width", 1)),
                _parse_color(_css(ystyle.get("axis_color"), default_axis)),
            )
        if "right" in frame_sides:
            cmd.stroke(
                [(px1, py0), (px1, py1)],
                float(ystyle.get("axis_width", 1)),
                _parse_color(_css(ystyle.get("axis_color"), default_axis)),
            )
    if not hide_x or explicit_frame_sides:
        if "top" in frame_sides:
            cmd.stroke(
                [(px0, py0), (px1, py0)],
                float(xstyle.get("axis_width", 1)),
                _parse_color(_css(xstyle.get("axis_color"), default_axis)),
            )
        if "bottom" in frame_sides:
            cmd.stroke(
                [(px0, py1), (px1, py1)],
                float(xstyle.get("axis_width", 1)),
                _parse_color(_css(xstyle.get("axis_color"), default_axis)),
            )
    for _axis_id, axis, _axis_scale in extra_x_axes:
        if _axis_tick_label_strategy(axis) == "none":
            continue
        axis_style = axis.get("style") or {}
        edge = py0 if axis.get("side", "bottom") == "top" else py1
        cmd.stroke(
            [(px0, edge), (px1, edge)],
            float(axis_style.get("axis_width", 1)),
            _parse_color(_css(axis_style.get("axis_color"), default_axis)),
        )
    for _axis_id, axis, _axis_scale in extra_y_axes:
        if _axis_tick_label_strategy(axis) == "none":
            continue
        axis_style = axis.get("style") or {}
        edge = px1 if axis.get("side", "right") == "right" else px0
        cmd.stroke(
            [(edge, py0), (edge, py1)],
            float(axis_style.get("axis_width", 1)),
            _parse_color(_css(axis_style.get("axis_color"), default_axis)),
        )

    def tick_span(style: dict[str, Any]) -> tuple[float, float]:
        default_length = 4 if style.get("_scene_public_chrome_defaults") else 0
        length = max(0.0, float(style.get("tick_length", default_length)))
        direction = str(style.get("tick_direction", "out"))
        if direction == "in":
            return length, 0.0
        if direction == "inout":
            return length / 2, length / 2
        return 0.0, length

    if not hide_x and polar is None:
        inward, outward = tick_span(xmstyle)
        side = xa.get("side", "bottom")
        edge = py0 if side == "top" else py1
        for value in xmt:
            x = float(sx(value))
            y0, y1 = (
                (edge - outward, edge + inward)
                if side == "top"
                else (edge - inward, edge + outward)
            )
            cmd.stroke(
                [(x, y0), (x, y1)],
                float(xmstyle.get("tick_width", 1)),
                _parse_color(_css(xmstyle.get("tick_color"), default_axis)),
            )
        inward, outward = tick_span(xstyle)
        for side in _axis_tick_sides(xa, is_x=True):
            edge = py0 if side == "top" else py1
            for value in xt:
                x = float(sx(value))
                y0, y1 = (
                    (edge - outward, edge + inward)
                    if side == "top"
                    else (edge - inward, edge + outward)
                )
                cmd.stroke(
                    [(x, y0), (x, y1)],
                    float(xstyle.get("tick_width", 1)),
                    _parse_color(_css(xstyle.get("tick_color"), default_axis)),
                )
    if not hide_y and polar is None:
        inward, outward = tick_span(ymstyle)
        side = ya.get("side", "left")
        edge = px1 if side == "right" else px0
        for value in ymt:
            y = float(sy(value))
            x0, x1 = (
                (edge - inward, edge + outward)
                if side == "right"
                else (edge - outward, edge + inward)
            )
            cmd.stroke(
                [(x0, y), (x1, y)],
                float(ymstyle.get("tick_width", 1)),
                _parse_color(_css(ymstyle.get("tick_color"), default_axis)),
            )
        inward, outward = tick_span(ystyle)
        for side in _axis_tick_sides(ya, is_x=False):
            edge = px1 if side == "right" else px0
            for value in yt:
                y = float(sy(value))
                x0, x1 = (
                    (edge - inward, edge + outward)
                    if side == "right"
                    else (edge - outward, edge + inward)
                )
                cmd.stroke(
                    [(x0, y), (x1, y)],
                    float(ystyle.get("tick_width", 1)),
                    _parse_color(_css(ystyle.get("tick_color"), default_axis)),
                )
    for axis_id, axis, axis_scale in extra_x_axes:
        if _axis_tick_label_strategy(axis) == "none":
            continue
        axis_style = axis.get("style") or {}
        inward, outward = tick_span(axis_style)
        for side in _axis_tick_sides(axis, is_x=True):
            edge = py0 if side == "top" else py1
            for value in extra_x_ticks[axis_id][0]:
                x = float(axis_scale(value))
                y0, y1 = (
                    (edge - outward, edge + inward)
                    if side == "top"
                    else (edge - inward, edge + outward)
                )
                cmd.stroke(
                    [(x, y0), (x, y1)],
                    float(axis_style.get("tick_width", 1)),
                    _parse_color(_css(axis_style.get("tick_color"), default_axis)),
                )
    for axis_id, axis, axis_scale in extra_y_axes:
        if _axis_tick_label_strategy(axis) == "none":
            continue
        axis_style = axis.get("style") or {}
        inward, outward = tick_span(axis_style)
        for side in _axis_tick_sides(axis, is_x=False):
            edge = px1 if side == "right" else px0
            for value in extra_y_ticks[axis_id][0]:
                y = float(axis_scale(value))
                x0, x1 = (
                    (edge - inward, edge + outward)
                    if side == "right"
                    else (edge - outward, edge + inward)
                )
                cmd.stroke(
                    [(x0, y), (x1, y)],
                    float(axis_style.get("tick_width", 1)),
                    _parse_color(_css(axis_style.get("tick_color"), default_axis)),
                )

    slots = slot_styles(spec)

    def slot_paint(slot: str, fallback: str) -> tuple:
        """A slot's text paint, or the writer's own default."""
        resolved = slot_text_color(slots.get(slot) or {}, "")
        return _parse_color(resolved or fallback)

    def emit_tick_labels(
        axis: dict[str, Any],
        values: list[float],
        step: float,
        axis_scale: _Scale,
        *,
        is_x: bool,
    ) -> None:
        axis_style = axis.get("style") or {}
        # The axis's own tick_label_color/tick_color is the narrower
        # selector and wins; the chart-wide slot fills in when it says nothing.
        axis_tick_paint = _css(axis_style.get("tick_label_color", axis_style.get("tick_color")), "")
        tick_color = (
            _parse_color(axis_tick_paint)
            if axis_tick_paint
            else slot_paint("tick_label", default_text)
        )
        font_size = slot_font_size(slots.get("tick_label") or {}, _axis_tick_font_size(axis))
        baseline_shift = _axis_tick_label_baseline_shift(axis)
        # An explicit tick_label_anchor (axis spec or style) overrides the
        # side-derived default, matching the browser client and SVG export.
        explicit_anchor = _tick_label_anchor(axis, axis_style, "")
        for side in _axis_tick_label_sides(axis, is_x=is_x):
            side_axis = {**axis, "side": side}
            side_items = _axis_tick_label_layout(side_axis, values, step, axis_scale, is_x)
            # Unstyled defaults reproduce the pre-`tick_label_pad` placement exactly.
            # The bottom gap is 15 here against the SVG exporter's 16: that 1 px has
            # always separated the two and is not this seam's to change.
            if is_x:
                label_offset = (
                    _axis_tick_label_offset(axis, 7.0, 0.2)
                    if side == "top"
                    # Rust Scene uses a 16 px bottom baseline.  The legacy
                    # raster's 15 px default remains for ordinary
                    # compatibility-only figures, but a visibility-switch
                    # fallback must retain the public Scene label position.
                    else _axis_tick_label_offset(
                        axis,
                        16.0 if axis_style.get("_scene_public_chrome_defaults") else 15.0,
                        0.8,
                    )
                )
            else:
                label_offset = _axis_tick_label_offset(axis, 8.0)
            for item in side_items:
                block = _textblock.measure(item["text"], font_size)
                if is_x:
                    row_offset = float(item["row"]) * (font_size + 4)
                    x = float(item["pos"])
                    y = (
                        py0 - label_offset - row_offset
                        if side == "top"
                        else py1 + label_offset + row_offset
                    )
                    angle = float(item["angle"])
                    if explicit_anchor:
                        anchor = _TEXT_ANCHOR_CODES[explicit_anchor]
                    elif angle == 0:
                        anchor = 1
                    elif (side == "bottom" and angle < 0) or (side == "top" and angle > 0):
                        anchor = 2
                    else:
                        anchor = 0
                else:
                    x = px1 + label_offset if side == "right" else px0 - label_offset
                    y = (
                        float(item["pos"])
                        + baseline_shift
                        - (block.line_count - 1) * block.line_step / 2.0
                    )
                    default_anchor = 0 if side == "right" else 2
                    anchor = (
                        _TEXT_ANCHOR_CODES[explicit_anchor] if explicit_anchor else default_anchor
                    )
                _emit_text_block(
                    cmd,
                    x,
                    y,
                    anchor,
                    font_size,
                    tick_color,
                    item["text"],
                    angle=float(item["angle"]),
                )

    if polar is not None:
        _emit_polar_tick_labels(
            cmd,
            polar,
            xlab,
            ylab,
            xstep,
            ystep,
            xa,
            ya,
            slot_font_size(slots.get("tick_label") or {}, _axis_tick_font_size(xa)),
            slot_font_size(slots.get("tick_label") or {}, _axis_tick_font_size(ya)),
            _polar_label_paint(xa, slot_paint, default_text),
            _polar_label_paint(ya, slot_paint, default_text),
            hide_x or xa.get("tick_label_strategy") == "off",
            hide_y or ya.get("tick_label_strategy") == "off",
        )
    else:
        emit_tick_labels(xa, xlab, xstep, sx, is_x=True)
        emit_tick_labels(ya, ylab, ystep, sy, is_x=False)
    for axis_id, axis, axis_scale in extra_x_axes:
        _ticks, tick_labels, step = extra_x_ticks[axis_id]
        emit_tick_labels(axis, tick_labels, step, axis_scale, is_x=True)
    for axis_id, axis, axis_scale in extra_y_axes:
        _ticks, tick_labels, step = extra_y_ticks[axis_id]
        emit_tick_labels(axis, tick_labels, step, axis_scale, is_x=False)
    legacy_title = spec.get("title") if not spec.get("title_options") else None
    # The width layout measured the title band at; wrapping anywhere else would
    # draw more lines than `title_room` reserved (see _svg._title_wrap_width).
    title_wrap_width = plot.get("title_wrap_width")
    if legacy_title:
        title_slot = slots.get("title") or {}
        title_italic, title_bold = _native_font_emphasis(
            {
                "font_style": title_slot.get("font-style"),
                "font_weight": title_slot.get("font-weight", 400),
            }
        )
        legacy_size = slot_font_size(title_slot, 14.0)
        legacy_block = _textblock.measure(legacy_title, legacy_size, max_width=title_wrap_width)
        # Lines run downward from the baseline, so lift the block by its trailing
        # lines: the last line keeps the historical single-line baseline. A
        # one-line title has no trailing lines and emits exactly as before.
        legacy_trailing = (legacy_block.line_count - 1) * legacy_block.line_step
        _emit_text_block(
            cmd,
            width / 2,
            plot["y"] - plot["top_axis_room"] - (10 if compact else 12) - legacy_trailing,
            1,
            legacy_size,
            slot_paint("title", default_text),
            "\n".join(legacy_block.lines),
            italic=title_italic,
            bold=title_bold,
        )
    for title_entry in [] if legacy_title else _title_entries(spec):
        title_style, title_size, title_block = _title_metrics(spec, title_entry, title_wrap_width)
        title_italic, title_bold = _native_font_emphasis(
            {
                "font_style": title_style.get("font-style"),
                # 400 = Matplotlib's `axes.titleweight: normal`; the baked
                # atlas only has a bold face, so anything >= 600 rounds up to
                # it. Mirrors the SVG/browser title default.
                "font_weight": title_style.get("font-weight", 400),
            }
        )
        trailing = (title_block.line_count - 1) * title_block.line_step
        if title_entry.get("automatic_y", True):
            title_anchor_y = plot["y"] - plot["top_axis_room"]
        else:
            title_anchor_y = plot["y"] + (1.0 - float(title_entry.get("y", 1.0))) * plot["h"]
        loc = str(title_entry.get("loc", "center"))
        title_x = {
            "left": plot["x"],
            "center": plot["x"] + plot["w"] / 2.0,
            "right": plot["x"] + plot["w"],
        }.get(loc, plot["x"] + plot["w"] / 2.0)
        _emit_text_block(
            cmd,
            title_x,
            title_anchor_y - float(title_entry.get("pad", 8.0)) - title_block.descent - trailing,
            {"left": 0, "center": 1, "right": 2}.get(loc, 1),
            title_size,
            _parse_color(slot_text_color(title_style, default_text)),
            # The wrapped lines, not the raw string: one long line inside a
            # two-line band is the clipping bug this reservation exists to stop.
            "\n".join(title_block.lines),
            italic=title_italic,
            bold=title_bold,
        )

    def emit_axis_title(axis: dict[str, Any], *, is_x: bool) -> None:
        if not axis.get("label") or _axis_tick_label_strategy(axis) == "none":
            return
        axis_style = axis.get("style") or {}
        geometry = _axis_label_geometry(axis, plot, is_x=is_x)
        anchor = {"start": 0, "middle": 1, "end": 2}[geometry["anchor"]]
        axis_title_slot = slots.get("axis_title") or {}
        italic, bold = _native_font_emphasis(
            {
                "font_style": axis_style.get("label_font_style")
                or axis_title_slot.get("font-style"),
                "font_weight": axis_style.get(
                    "label_font_weight", axis_title_slot.get("font-weight", 400)
                ),
            }
        )
        _emit_text_block(
            cmd,
            float(geometry["x"]),
            float(geometry["y"]),
            anchor,
            slot_font_size(slots.get("axis_title") or {}, float(geometry["font_size"])),
            (
                _parse_color(_css(axis_style.get("label_color"), ""))
                if _css(axis_style.get("label_color"), "")
                else slot_paint("axis_title", default_text)
            ),
            str(axis["label"]),
            angle=float(geometry["angle"]),
            italic=italic,
            bold=bold,
        )

    emit_axis_title(xa, is_x=True)
    emit_axis_title(ya, is_x=False)
    for _axis_id, axis, _axis_scale in extra_x_axes:
        emit_axis_title(axis, is_x=True)
    for _axis_id, axis, _axis_scale in extra_y_axes:
        emit_axis_title(axis, is_x=False)

    named = legend_items(spec["traces"], spec_palette)
    main_legend = spec.get("legend") or {}
    main_items = main_legend.get("items") or named
    show_main_legend = spec.get("show_legend", True) and bool(main_items)
    extra_legends = [(extra, extra.get("items") or []) for extra in spec.get("extra_legends") or []]
    legends: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
    if show_main_legend:
        legends.append((main_items, main_legend))
    legends.extend((items, extra) for extra, items in extra_legends if items)
    # The browser scrolls an oversized legend. Static files cannot, so clip the
    # bounded/truncated equivalent to the plot rectangle. The exemption for an
    # anchored legend (which is placed relative to, and may sit outside, the
    # axes) is scoped per legend exactly as in `_svg.py`: one anchored legend
    # must not lift the clip off its non-anchored siblings. The clip is a
    # stateful raster command, so only emit it on a transition — an
    # all-anchored or all-unanchored figure yields the same stream as before.
    # The clip is the plot rect unioned with any polar legend gutter, which sits
    # outside it — the plot rect alone erased a polar legend. Shared with the
    # SVG clipPath via `legend_clip_rect`.
    lx, ly, lw, lh = legend_clip_rect(plot)
    clipped_to_plot = False
    for items, options in legends:
        want_clip = not options.get("anchor")
        if want_clip != clipped_to_plot:
            if want_clip:
                cmd.clip(lx, ly, lw, lh)
            else:
                cmd.clip(0, 0, width, height)
            clipped_to_plot = want_clip
        _emit_legend(
            cmd,
            items,
            plot,
            legend_options_with_slot(spec, options),
            default_text,
            spec_palette,
            slots.get("legend_label") or {},
            slots.get("legend_title") or {},
        )
    if clipped_to_plot:
        cmd.clip(0, 0, width, height)
    if spec.get("colorbar"):
        _emit_colorbar(
            cmd,
            spec["colorbar"],
            plot,
            _colorbar_right_axis_room(ya, extra_y_axes, compact),
            default_text,
            slots.get("colorbar_title") or slots.get("colorbar") or {},
            slots.get("colorbar_tick") or slots.get("colorbar") or {},
        )

    w_px, h_px = max(1, round(width * scale)), max(1, round(height * scale))
    from . import _native

    spans = (blob, *borrowed)
    # The command buffer ships as a borrowed buffer, not a `bytes` copy: the
    # ctypes seam wraps it with `np.frombuffer` and the native rasterizer only
    # reads it, so freezing it would duplicate a display list that is O(marks)
    # (megabytes on a direct-tier scatter) for nothing.
    if fast_png:
        return _native.rasterize_png_spans(cmd.buf, spans, w_px, h_px)
    return _native.rasterize_spans(cmd.buf, spans, w_px, h_px)


# Trace kinds whose legend entry is a short line sample (with dash) rather


def _export_payload(
    fig: Any,
    width: Optional[int],
    height: Optional[int],
    background: Optional[str],
) -> tuple[dict[str, Any], bytes, tuple[np.ndarray, ...]]:
    """Build the raster payload with export-time size/background overrides."""
    eff_w = (
        int(width)
        if width is not None
        else (fig.width if isinstance(fig.width, (int, float)) else 900)
    )
    spec, blob, borrowed = fig._build_raster_payload(px_width=max(256, int(eff_w)))
    if width is not None:
        spec["width"] = int(width)
    if height is not None:
        spec["height"] = int(height)
    apply_export_background(spec, background)
    return spec, blob, borrowed


def to_rgba(
    fig: Any,
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    scale: float = 2.0,
    background: Optional[str] = None,
) -> np.ndarray:
    """Render `fig` to an ``(h, w, 4)`` RGBA8 array (no encode).

    The shared pixel source for every native raster format: PNG keeps its
    fused Rust encode path in `to_png`, while JPEG/WebP export encodes this
    array. `background` overrides the figure canvas color ("transparent"
    yields alpha-0 pixels outside the plot rect)."""
    spec, blob, borrowed = _export_payload(fig, width, height, background)
    rendered = render_raster(spec, blob, float(scale), borrowed=borrowed)
    assert isinstance(rendered, np.ndarray)  # fast_png=False never returns bytes
    return rendered


def to_png(
    fig: Any,
    path: Optional[str | PathLike[str]] = None,
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    scale: float = 2.0,
    fast: bool = False,
    background: Optional[str] = None,
) -> bytes:
    """Render `fig` to PNG bytes with the native rasterizer (no browser)."""
    # The fused Rust PNG path initializes an opaque white canvas, so any
    # non-default background must take the raw-RGBA encode branch.
    fast = fast and background is None
    spec, blob, borrowed = _export_payload(fig, width, height, background)
    rendered = render_raster(spec, blob, float(scale), fast_png=fast, borrowed=borrowed)
    data = rendered if isinstance(rendered, bytes) else _png.encode(rendered)
    if path is not None:
        with open(path, "wb") as f:
            f.write(data)
    return data
