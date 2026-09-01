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

from __future__ import annotations  # noqa: F401

from collections.abc import Sequence  # noqa: F401
from os import PathLike  # noqa: F401
from typing import Any, Optional  # noqa: F401

from ._export_annotations import _annotation_connector_unclipped  # noqa: F401
from ._export_annotations_svg import _annotation_svg  # noqa: F401
from ._export_axis_grid_svg import _svg_axis_grid_and_labels  # noqa: F401
from ._export_baseline_svg import _svg_baselines  # noqa: F401
from ._export_chrome import (  # noqa: F401
    _colorbar_tick_target,  # noqa: F401
    apply_export_background,
)
from ._export_chrome import resolve_static_css_vars as _resolve_static_css_vars  # noqa: F401
from ._export_chrome_svg import _svg_chrome  # noqa: F401
from ._export_colormap import COLORMAP_STOPS  # noqa: F401
from ._export_heatmap import (  # noqa: F401
    _heatmap_sample_column,  # noqa: F401
    polar_heatmap_rgba,  # noqa: F401
)
from ._export_layout import (  # noqa: F401
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
from ._export_legend import (  # noqa: F401
    _LEGEND_CHAR_WIDTH,  # noqa: F401
    _legend_layout,  # noqa: F401
    _legend_text_width,  # noqa: F401
    legend_clip_rect,
)
from ._export_legend_svg import (  # noqa: F401
    _LEGEND_LINE_KINDS,  # noqa: F401
    _legend,  # noqa: F401
    _legend_hatch_svg,  # noqa: F401
)
from ._export_marker_svg import (  # noqa: F401
    _authored_marker_path_d,  # noqa: F401
    _star_path,  # noqa: F401
)
from ._export_marks_svg import _segment_marks, _svg_trace_marks  # noqa: F401
from ._export_path_svg import _monotone_tangents  # noqa: F401
from ._export_polar_svg import _polar_frame_path  # noqa: F401
from ._export_svg_state import _Svg  # noqa: F401
from ._export_svg_util import _num, escape  # noqa: F401
from ._export_ticks import (  # noqa: F401
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
from ._layout import (  # noqa: F401
    THETA_ZERO,  # noqa: F401
    _axis_scales,
    _PolarProjection,
    _Scale,  # noqa: F401
    polar_wedge_points,  # noqa: F401
)
from ._paint import (  # noqa: F401
    authored_marker_points as _authored_marker_points,  # noqa: F401
)
from ._paint import (  # noqa: F401
    colormap_lut as _colormap_lut,
)
from ._paint import (  # noqa: F401
    colormap_stops as _colormap_stops,  # noqa: F401
)
from ._paint import (  # noqa: F401
    heatmap_rgba_grid as _heatmap_rgba_grid,  # noqa: F401
)
from ._paint import (  # noqa: F401
    physical_density_alpha as _physical_density_alpha,  # noqa: F401
)
from ._paint import (  # noqa: F401
    solid_paint as _solid_paint,
)
from ._paint import (  # noqa: F401
    step_arrays as _step_arrays,  # noqa: F401
)
from ._svg_figure import to_svg  # noqa: F401
from ._svg_render import render_svg  # noqa: F401
from .config import DEFAULT_PALETTE  # noqa: F401

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
