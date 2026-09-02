"""SVG payload rendering (layout + mark assembly).

Static SVG export — a pure-Python renderer over the same wire payload the
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
from typing import Any

from ._export_annotations import _annotation_connector_unclipped  # noqa: F401
from ._export_annotations_svg import _annotation_svg
from ._export_axis_grid_svg import _svg_axis_grid_and_labels
from ._export_baseline_svg import _svg_baselines
from ._export_chrome import (
    _colorbar_tick_target,  # noqa: F401
)
from ._export_chrome import resolve_static_css_vars as _resolve_static_css_vars
from ._export_chrome_svg import _svg_chrome
from ._export_colormap import COLORMAP_STOPS  # noqa: F401
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
from ._export_marks_svg import _segment_marks, _svg_trace_marks  # noqa: F401
from ._export_path_svg import _monotone_tangents  # noqa: F401
from ._export_polar_svg import _polar_frame_path
from ._export_svg_state import _Svg
from ._export_svg_util import _num, escape
from ._export_ticks import (
    _axis_tick_label_layout,  # noqa: F401
    _fmt_axis,  # noqa: F401
    _fmt_log,  # noqa: F401
    _preserve_scene_chrome_for_axis_visibility,
    _tick_text,  # noqa: F401
    _tick_window,  # noqa: F401
    _tick_window_filter,  # noqa: F401
    axis_ticks,  # noqa: F401
    minor_axis_ticks,  # noqa: F401
)
from ._fontmetrics import estimated_text_width as _estimated_text_width  # noqa: F401
from ._layout import (
    THETA_ZERO,  # noqa: F401
    _axis_scales,
    _PolarProjection,
    _Scale,  # noqa: F401
    polar_wedge_points,  # noqa: F401
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
    heatmap_rgba_grid as _heatmap_rgba_grid,  # noqa: F401
)
from ._paint import (
    physical_density_alpha as _physical_density_alpha,  # noqa: F401
)
from ._paint import (
    solid_paint as _solid_paint,
)
from ._paint import (
    step_arrays as _step_arrays,  # noqa: F401
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

    axis = _svg_axis_grid_and_labels(spec, plot, xa, ya, sx, sy, extra_x_axes, extra_y_axes, polar)
    grid = axis.grid
    labels = axis.labels
    marks, _palette_cycle = _svg_trace_marks(
        spec,
        blob,
        cols,
        plot,
        sx,
        sy,
        x_scales,
        y_scales,
        svg,
        polar,
        palette_cycle=0,
    )
    spec_palette: Sequence[str] = spec.get("palette") or DEFAULT_PALETTE
    chrome = _svg_chrome(
        spec,
        plot,
        width,
        xa,
        ya,
        extra_x_axes,
        extra_y_axes,
        compact=compact,
        clip_id=clip_id,
        default_text=axis.default_text,
        spec_palette=spec_palette,
        slots=axis.slots,
    )
    annotation_marks, unclipped_annotation_marks, annotation_labels = _annotation_svg(
        spec.get("annotations") or [], sx, sy, plot, width, height, polar
    )
    marks.extend(annotation_marks)
    labels.extend(annotation_labels)
    baselines = _svg_baselines(
        spec,
        plot,
        xa,
        ya,
        sx,
        sy,
        extra_x_axes,
        extra_y_axes,
        polar,
        xt=axis.xt,
        yt=axis.yt,
        xmt=axis.xmt,
        ymt=axis.ymt,
        extra_x_ticks=axis.extra_x_ticks,
        extra_y_ticks=axis.extra_y_ticks,
        hide_x=axis.hide_x,
        hide_y=axis.hide_y,
        default_axis=axis.default_axis,
        xstyle=axis.xstyle,
        ystyle=axis.ystyle,
        xmstyle=axis.xmstyle,
        ymstyle=axis.ymstyle,
    )
    dom_style = (spec.get("dom") or {}).get("style") or {}

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
            f'<g fill="{escape(axis.default_text)}">',
            *labels,
            "</g>",
            *chrome,
            "</svg>",
        ]
    )
