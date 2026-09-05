"""Compatibility facade for pyplot axis measurement and slot metadata.

The Python static-export compatibility renderer was retired into the Rust
``StaticDocument`` boundary (M2 #873): every supported native SVG/PNG/PDF/
JPEG/WebP journey compiles canonical Scene bytes and marshals an XYST
envelope (``_static_document``). Nothing here renders. What remains is the
bounded measurement/ergonomics surface pyplot needs for non-Scene axes
(polar, extra axes, custom fonts), re-exported from ``_layout``; Rust owns
every tick/layout decision behind those calls (ABI 121/123/125/126/198).
"""

from __future__ import annotations

from ._channels_colormap import COLORMAP_STOPS  # noqa: F401
from ._fontmetrics import estimated_text_width as _estimated_text_width  # noqa: F401
from ._layout import (  # noqa: F401  # noqa: F401
    _POLAR_LABEL_ROOM,
    _POLAR_LEGEND_BAND,
    _fmt_axis,
    _fmt_log,
    _polar_label_room,
    _polar_legend_room,
    _PolarProjection,
    _Scale,
    axis_ticks,
    layout,
    legend_items,
    minor_axis_ticks,
    polar_wedge_points,
    scene_layout_rooms,
    warp_axis_indices,
)
from ._paint import colormap_lut as _lut  # noqa: F401
from ._paint import paint_rgba8 as _parse_color  # noqa: F401
from ._paint import solid_rgba8 as _solid_color  # noqa: F401
from .config import DEFAULT_PALETTE  # noqa: F401

# Unresolved CSS paints use native `STATIC_COLOR_FALLBACK_RGBA8` via
# `xyg_css_color_rgba` (76, 120, 168, 255).

#: Text properties the VECTOR writers honor on a chrome slot (SVG, and PDF via
#: the same markup). Each maps one-to-one onto an SVG presentation attribute.
#: The writers themselves are Rust-owned; pyplot's style validation mirrors
#: this list, so it stays the shared vocabulary.
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
#: the bold face. It has no family axis and no per-glyph advance control, so
#: `font-family` and `letter-spacing` are vector-only, and `opacity` is not
#: read rather than being silently approximated (§28). `SLOT_TEXT_PROPS` minus
#: this tuple is the vector-only set.
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

# Smallest gap between the canvas edge and the outermost axis ink.
# Antialiased leading glyphs must not land on the export boundary.
_AXIS_TEXT_EDGE_PAD = 4.0
