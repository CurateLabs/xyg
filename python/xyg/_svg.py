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

import base64
import hashlib
import math
from collections.abc import Callable, Sequence
from itertools import pairwise
from os import PathLike
from typing import Any, Optional

import numpy as np

from . import _native, _paint, _png, _textblock, kernels
from ._arrowgeom import arrow_shapes as _arrow_shapes
from ._columns import column as _column
from ._columns import column_ref as _column_ref
from ._columns import density_column as _density_column
from ._export_annotations import (
    _annotation_connector_unclipped,
    _annotation_first_baseline,
    _axis_label_geometry,
    annotation_label_placement,
)
from ._export_chrome import (
    _AXIS,
    _GRID,
    _TEXT,
    COLORBAR_FONT_SIZE,
    _colorbar_tick_target,
    apply_export_background,
    legend_options_with_slot,
    slot_font_size,
    slot_styles,
    slot_text_color,
)
from ._export_chrome import resolve_static_css_vars as _resolve_static_css_vars
from ._export_heatmap import (
    _heatmap_sample_column,  # noqa: F401
    polar_heatmap_rgba,
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
    _legend_layout,
    legend_clip_rect,
    legend_items,
)
from ._export_polar_svg import (
    _polar_frame_path,
    _polar_grid,
    _polar_linear_frame_path,
    _polar_radial_tick_length,
    _polar_thin_radial_labels,
    _polar_tick_labels,
    _polar_wedge_path,
)
from ._export_svg_util import (
    _axis_grid_attrs,
    _cap_join_attrs,
    _dash_attr,
    _escape_attr,
    _num,
    _slot_size_attr,
    _svg_font_attrs,
    _svg_mathtext_spans,
    _svg_text_box,
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
    _fmt_log,
    _preserve_scene_chrome_for_axis_visibility,
    _tick_label_anchor,
    _tick_text,  # noqa: F401
    axis_ticks,
    minor_axis_ticks,
)
from ._fontmetrics import estimated_text_width as _estimated_text_width  # noqa: F401
from ._layout import (
    _axis_scales,
    _PolarProjection,
    _Scale,
    polar_wedge_points,  # noqa: F401
    warp_grid_rgba,
)
from ._paint import (
    _css,
    hexbin_ring,
    trace_paint_rgb_css_list,
)
from ._paint import (
    authored_marker_points as _authored_marker_points,
)
from ._paint import (
    colormap_lut as _colormap_lut,
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
    px_size as _px_size,
)
from ._paint import (
    rgb_css as _rgb_css,
)
from ._paint import (
    rgba8 as _rgba8,
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
from ._paint import (
    trace_paint_rgba as _trace_paint_rgba,
)
from .config import DEFAULT_PALETTE


def _flag_stops() -> list[tuple[int, int, int]]:
    """Matplotlib's high-frequency ``flag`` map at the native 256 LUT positions."""
    x = np.linspace(0.0, 1.0, 256)
    channels = np.column_stack(
        (
            0.75 * np.sin((x * 31.5 + 0.25) * np.pi) + 0.5,
            np.sin(x * 31.5 * np.pi),
            0.75 * np.sin((x * 31.5 - 0.25) * np.pi) + 0.5,
        )
    )
    # Match Matplotlib's ``bytes=True`` conversion, which truncates rather than
    # rounds each clipped channel after scaling it to the uint8 range.
    rgb = (np.clip(channels, 0.0, 1.0) * 255.0).astype(np.uint8)
    return [(int(row[0]), int(row[1]), int(row[2])) for row in rgb]


# Built-in tables mirrored from `crates/xyg-engine/src/colormap.rs` and
# `js/src/10_colormaps.ts` (§36) — native ABI 135 is authoritative for hosts;
# this copy stays for JS-sync tests and gallery goldens.
COLORMAP_STOPS: dict[str, list[tuple[int, int, int]]] = {
    "binary": [(255, 255, 255), (0, 0, 0)],
    "flag": _flag_stops(),
    "reds": [
        (255, 245, 240),
        (254, 229, 216),
        (253, 202, 181),
        (252, 171, 143),
        (252, 138, 106),
        (251, 105, 74),
        (241, 68, 50),
        (217, 37, 35),
        (188, 20, 26),
        (152, 12, 19),
        (103, 0, 13),
    ],
    "bone": [
        (0, 0, 0),
        (22, 22, 30),
        (45, 45, 62),
        (66, 66, 93),
        (89, 92, 121),
        (112, 123, 144),
        (134, 154, 166),
        (157, 185, 188),
        (185, 210, 210),
        (221, 233, 233),
        (255, 255, 255),
    ],
    "autumn": [
        (255, 0, 0),
        (255, 25, 0),
        (255, 51, 0),
        (255, 76, 0),
        (255, 102, 0),
        (255, 128, 0),
        (255, 153, 0),
        (255, 179, 0),
        (255, 204, 0),
        (255, 230, 0),
        (255, 255, 0),
    ],
    "winter": [
        (0, 0, 255),
        (0, 25, 242),
        (0, 51, 230),
        (0, 76, 217),
        (0, 102, 204),
        (0, 128, 191),
        (0, 153, 178),
        (0, 179, 166),
        (0, 204, 153),
        (0, 230, 140),
        (0, 255, 128),
    ],
    "bupu": [
        (247, 252, 253),
        (229, 239, 246),
        (204, 221, 236),
        (178, 202, 225),
        (154, 180, 214),
        (140, 149, 198),
        (140, 116, 181),
        (138, 81, 165),
        (133, 45, 144),
        (118, 12, 113),
        (77, 0, 75),
    ],
    "gray": [
        (0, 0, 0),
        (25, 25, 25),
        (51, 51, 51),
        (76, 76, 76),
        (102, 102, 102),
        (128, 128, 128),
        (153, 153, 153),
        (179, 179, 179),
        (204, 204, 204),
        (230, 230, 230),
        (255, 255, 255),
    ],
    "viridis": [
        (68, 1, 84),
        (72, 36, 117),
        (65, 68, 135),
        (53, 95, 141),
        (42, 120, 142),
        (33, 145, 140),
        (34, 168, 132),
        (68, 191, 112),
        (122, 209, 81),
        (189, 223, 38),
        (253, 231, 37),
    ],
    "plasma": [
        (13, 8, 135),
        (65, 4, 157),
        (106, 0, 168),
        (143, 13, 164),
        (177, 42, 144),
        (204, 71, 120),
        (225, 100, 98),
        (242, 132, 75),
        (252, 166, 54),
        (252, 206, 37),
        (240, 249, 33),
    ],
    "inferno": [
        (0, 0, 4),
        (22, 11, 57),
        (66, 10, 104),
        (106, 23, 110),
        (147, 38, 103),
        (188, 55, 84),
        (221, 81, 58),
        (243, 120, 25),
        (252, 165, 10),
        (246, 215, 70),
        (252, 255, 164),
    ],
    "magma": [
        (0, 0, 4),
        (20, 14, 54),
        (59, 15, 112),
        (100, 26, 128),
        (140, 41, 129),
        (183, 55, 121),
        (222, 73, 104),
        (247, 112, 92),
        (254, 159, 109),
        (254, 207, 146),
        (252, 253, 191),
    ],
    "cividis": [
        (0, 34, 78),
        (8, 51, 112),
        (53, 69, 108),
        (79, 87, 108),
        (102, 105, 112),
        (125, 124, 120),
        (148, 142, 119),
        (174, 163, 113),
        (200, 184, 102),
        (229, 207, 82),
        (254, 232, 56),
    ],
    "coolwarm": [
        (59, 76, 192),
        (89, 119, 227),
        (123, 159, 249),
        (158, 190, 255),
        (192, 212, 245),
        (221, 220, 220),
        (242, 203, 183),
        (247, 172, 142),
        (238, 132, 104),
        (214, 82, 68),
        (180, 4, 38),
    ],
    "turbo": [
        (48, 18, 59),
        (69, 89, 203),
        (62, 155, 254),
        (25, 213, 205),
        (70, 248, 132),
        (164, 252, 60),
        (225, 221, 55),
        (254, 164, 49),
        (240, 91, 18),
        (195, 37, 3),
        (122, 4, 3),
    ],
    "rainbow": [
        (128, 0, 255),
        (78, 77, 252),
        (25, 150, 243),
        (24, 205, 228),
        (77, 243, 206),
        (128, 255, 180),
        (178, 243, 150),
        (230, 205, 115),
        (255, 150, 79),
        (255, 77, 39),
        (255, 0, 0),
    ],
    "jet": [
        (0, 0, 128),
        (0, 0, 241),
        (0, 76, 255),
        (0, 176, 255),
        (41, 255, 206),
        (125, 255, 122),
        (206, 255, 41),
        (255, 196, 0),
        (255, 104, 0),
        (241, 8, 0),
        (128, 0, 0),
    ],
    "rdgy": [
        (103, 0, 31),
        (177, 24, 43),
        (214, 96, 77),
        (243, 164, 129),
        (253, 219, 199),
        (254, 254, 254),
        (224, 224, 224),
        (185, 185, 185),
        (135, 135, 135),
        (76, 76, 76),
        (26, 26, 26),
    ],
    "rdbu": [
        (103, 0, 31),
        (177, 24, 43),
        (214, 96, 77),
        (243, 164, 129),
        (253, 219, 199),
        (246, 247, 247),
        (209, 229, 240),
        (144, 196, 221),
        (67, 147, 195),
        (32, 101, 171),
        (5, 48, 97),
    ],
    "blues": [
        (247, 251, 255),
        (227, 238, 249),
        (208, 225, 242),
        (183, 212, 234),
        (148, 196, 223),
        (106, 174, 214),
        (74, 152, 201),
        (46, 126, 188),
        (23, 100, 171),
        (8, 74, 145),
        (8, 48, 107),
    ],
    "purples": [
        (252, 251, 253),
        (242, 240, 247),
        (226, 226, 239),
        (206, 207, 229),
        (182, 182, 216),
        (158, 154, 200),
        (134, 131, 189),
        (114, 98, 172),
        (97, 64, 155),
        (79, 31, 139),
        (63, 0, 125),
    ],
    "pubu": [
        (255, 247, 251),
        (240, 234, 244),
        (219, 218, 235),
        (192, 201, 226),
        (156, 185, 217),
        (115, 169, 207),
        (66, 149, 195),
        (24, 124, 182),
        (5, 103, 162),
        (4, 83, 130),
        (2, 56, 88),
    ],
    "piyg": [
        (142, 1, 82),
        (196, 26, 124),
        (222, 119, 174),
        (241, 181, 217),
        (253, 224, 239),
        (247, 247, 246),
        (230, 245, 208),
        (183, 224, 133),
        (127, 188, 65),
        (76, 145, 33),
        (39, 100, 25),
    ],
    "prgn": [
        (64, 0, 75),
        (117, 41, 130),
        (153, 112, 171),
        (193, 164, 206),
        (231, 212, 232),
        (246, 247, 246),
        (217, 240, 211),
        (165, 218, 159),
        (90, 174, 97),
        (26, 119, 54),
        (0, 68, 27),
    ],
    "rdylgn": [
        (165, 0, 38),
        (214, 47, 39),
        (244, 109, 67),
        (253, 173, 96),
        (254, 224, 139),
        (254, 255, 190),
        (217, 239, 139),
        (165, 216, 106),
        (102, 189, 99),
        (25, 151, 80),
        (0, 104, 55),
    ],
    "rdylbu": [
        (165, 0, 38),
        (214, 47, 38),
        (244, 109, 67),
        (252, 172, 96),
        (254, 224, 144),
        (254, 254, 192),
        (224, 243, 247),
        (169, 216, 232),
        (116, 173, 209),
        (68, 115, 179),
        (49, 54, 149),
    ],
    "ylgn": [
        (255, 255, 229),
        (248, 252, 194),
        (229, 244, 171),
        (200, 232, 154),
        (162, 216, 137),
        (119, 197, 120),
        (75, 176, 98),
        (46, 146, 76),
        (21, 120, 62),
        (0, 96, 51),
        (0, 69, 41),
    ],
    "wistia": [
        (228, 255, 122),
        (238, 245, 84),
        (249, 236, 45),
        (255, 223, 21),
        (255, 206, 10),
        (255, 188, 0),
        (255, 177, 0),
        (255, 165, 0),
        (254, 153, 0),
        (253, 139, 0),
        (252, 127, 0),
    ],
    "puor": [
        (127, 59, 8),
        (177, 87, 6),
        (224, 130, 20),
        (252, 182, 97),
        (254, 224, 182),
        (246, 246, 246),
        (216, 218, 235),
        (177, 169, 209),
        (128, 115, 172),
        (83, 38, 134),
        (45, 0, 75),
    ],
    "spectral": [
        (158, 1, 66),
        (212, 61, 79),
        (244, 109, 67),
        (253, 173, 96),
        (254, 224, 139),
        (255, 255, 190),
        (230, 245, 152),
        (170, 220, 164),
        (102, 194, 165),
        (51, 135, 188),
        (94, 79, 162),
    ],
}


# Unresolved CSS paints use native `STATIC_COLOR_FALLBACK_RGBA8` via
# `xyg_css_color_rgba` (76, 120, 168, 255).
_MS = {"s": 1e3, "m": 6e4, "h": 36e5, "d": 864e5}
_FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def _colormap_key(colormap: Any) -> str:
    """A stable, document-unique id fragment for a colormap — a built-in name,
    or the digest of a custom ramp's stops (two colorbars in one document must
    not share a `<linearGradient>` id unless they are the same ramp)."""
    if isinstance(colormap, str):
        return colormap
    return "custom-" + hashlib.sha256(repr(_colormap_stops(colormap)).encode()).hexdigest()[:12]


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


# Embedded heatmap/density rasters use the shared truecolor PNG encoder.
_png_rgba = _png.png_truecolor


def _monotone_tangents(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fritsch–Carlson tangents — the same construction as xySmoothResample."""
    return _native.monotone_tangents(
        np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    )


class _Svg:
    """One export pass: collects defs + body elements, then assembles."""

    def __init__(self, id_prefix: str = "") -> None:
        self.defs: list[str] = []
        self.body: list[str] = []
        self._uid = 0
        # Composed documents (facet grids) nest several exports into one SVG;
        # the prefix keeps ids unique so url(#...) refs stay panel-local.
        self._id_prefix = id_prefix

    def uid(self, prefix: str) -> str:
        self._uid += 1
        return f"{self._id_prefix}{prefix}{self._uid}"

    def gradient(self, fill: dict[str, Any], mark_color: str, plot: Optional[dict] = None) -> str:
        """Register a <linearGradient> for a validated fill spec; returns url(#id).

        Mark space maps to each element's bounding box (exact for bars/rects;
        the area approximation is documented). Plot space maps to the plot rect.
        """
        gid = self.uid("g")
        direction = fill.get("dir", "down")
        # Gradient line start/end per CSS: "down" starts at the top.
        ends = {
            "down": (0, 0, 0, 1),
            "up": (0, 1, 0, 0),
            "right": (0, 0, 1, 0),
            "left": (1, 0, 0, 0),
        }[direction if direction in ("down", "up", "left", "right") else "down"]
        if fill.get("space") == "plot" and plot:
            x0 = plot["x"] + ends[0] * plot["w"]
            y0 = plot["y"] + ends[1] * plot["h"]
            x1 = plot["x"] + ends[2] * plot["w"]
            y1 = plot["y"] + ends[3] * plot["h"]
            units = f'gradientUnits="userSpaceOnUse" x1="{_num(x0)}" y1="{_num(y0)}" x2="{_num(x1)}" y2="{_num(y1)}"'
        else:
            units = f'x1="{ends[0]}" y1="{ends[1]}" x2="{ends[2]}" y2="{ends[3]}"'
        raw_stops = fill.get("stops", [])
        resolved = [_css(c, mark_color) for _t, c in raw_stops]
        stops_out: list[str] = []
        for index, ((t, raw_color), color) in enumerate(zip(raw_stops, resolved, strict=True)):
            offset = _num(t * 100)
            if str(raw_color).strip().lower() != "transparent":
                escaped = escape(color, {chr(34): "&quot;"})
                stops_out.append(f'<stop offset="{offset}%" stop-color="{escaped}"/>')
                continue

            # SVG interpolates stop RGB independently from stop opacity. A
            # literal `transparent` stop is transparent black, which makes a
            # colored fade pass through a muddy gray fringe. Give the zero-
            # opacity stop the adjacent visible hue instead, matching the
            # browser renderer's premultiplied-alpha interpolation. When a
            # transparent stop sits between two different colors, duplicate
            # it at the same offset; the invisible color switch preserves the
            # hue on both segments.
            previous = next(
                (
                    resolved[i]
                    for i in range(index - 1, -1, -1)
                    if str(raw_stops[i][1]).strip().lower() != "transparent"
                ),
                None,
            )
            following = next(
                (
                    resolved[i]
                    for i in range(index + 1, len(raw_stops))
                    if str(raw_stops[i][1]).strip().lower() != "transparent"
                ),
                None,
            )
            transparent_colors = [previous or following or mark_color]
            if previous and following and previous != following:
                transparent_colors.append(following)
            for transparent_color in transparent_colors:
                escaped = escape(transparent_color, {chr(34): "&quot;"})
                stops_out.append(
                    f'<stop offset="{offset}%" stop-color="{escaped}" stop-opacity="0"/>'
                )
        stops = "".join(stops_out)
        self.defs.append(f'<linearGradient id="{gid}" {units}>{stops}</linearGradient>')
        return f"url(#{gid})"

    def gradient_vector(
        self, x0: float, y0: float, x1: float, y1: float, stops: list[tuple[float, str, float]]
    ) -> str:
        """Register a two-point <linearGradient> in user space; returns url(#id).

        `gradient()` above is closed over four axis-aligned directions, which is
        the right vocabulary for a bar or an area but cannot express a ribbon's
        gradient — that one runs along the flow, from one face to the other, and
        every band in a diagram has its own. Hence an explicit endpoint pair.
        Each stop is ``(offset, color, opacity)``: per-stop opacity is how the
        alpha channel interpolates along the vector, exactly as the raster's
        RGBA stops and the client's `mix` do. `userSpaceOnUse` and
        `stop-opacity` are both in the PDF converter's allowlist, so this
        survives PDF export unchanged.
        """
        gid = self.uid("g")
        units = (
            f'gradientUnits="userSpaceOnUse" x1="{_num(x0)}" y1="{_num(y0)}" '
            f'x2="{_num(x1)}" y2="{_num(y1)}"'
        )
        parts = []
        for offset, color, opacity in stops:
            escaped = escape(color, {chr(34): "&quot;"})
            alpha = f' stop-opacity="{_num(opacity)}"' if opacity < 1 else ""
            parts.append(f'<stop offset="{_num(offset * 100)}%" stop-color="{escaped}"{alpha}/>')
        self.defs.append(f'<linearGradient id="{gid}" {units}>{"".join(parts)}</linearGradient>')
        return f"url(#{gid})"


def _rounded_rect_path(
    x: float, y: float, w: float, h: float, r_tip: float, r_base: float, tip_top: bool
) -> str:
    """Rect path with independent tip/base corner radii (vertical mark space)."""
    rt = min(r_tip, w / 2, h / 2)
    rb = min(r_base, w / 2, h / 2)
    top_r, bot_r = (rt, rb) if tip_top else (rb, rt)
    p = [f"M {_num(x)} {_num(y + top_r)}"]
    p.append(f"A {_num(top_r)} {_num(top_r)} 0 0 1 {_num(x + top_r)} {_num(y)}" if top_r else "")
    p.append(f"L {_num(x + w - top_r)} {_num(y)}")
    p.append(
        f"A {_num(top_r)} {_num(top_r)} 0 0 1 {_num(x + w)} {_num(y + top_r)}" if top_r else ""
    )
    p.append(f"L {_num(x + w)} {_num(y + h - bot_r)}")
    p.append(
        f"A {_num(bot_r)} {_num(bot_r)} 0 0 1 {_num(x + w - bot_r)} {_num(y + h)}" if bot_r else ""
    )
    p.append(f"L {_num(x + bot_r)} {_num(y + h)}")
    p.append(
        f"A {_num(bot_r)} {_num(bot_r)} 0 0 1 {_num(x)} {_num(y + h - bot_r)}" if bot_r else ""
    )
    p.append("Z")
    return " ".join(s for s in p if s)


def _poly_path(px: np.ndarray, py: np.ndarray) -> str:
    return _native.svg_poly_path(px, py)


def _polar_visible_runs(
    xv: np.ndarray, yv: np.ndarray, polar: "_PolarProjection"
) -> list[np.ndarray]:
    """Index runs of consecutive vertices the polar transform keeps.

    The same split `_curve_path` performs, exposed so a filled area can close
    each run against its own base instead of stitching every run to one base.
    """
    visible = polar.position_mask(xv, yv)
    if visible.size == 0:
        return []
    idx = np.flatnonzero(visible)
    if idx.size == 0:
        return []
    runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    return [run for run in runs if len(run) >= 2]


def _area_fill_path(
    xv: np.ndarray,
    yv: np.ndarray,
    bv: np.ndarray,
    sx: _Scale,
    sy: _Scale,
    smooth: bool,
    polar: "Optional[_PolarProjection]" = None,
) -> str:
    """Closed fill path between a top curve and its base, or "" if nothing is
    visible. Under polar each visible run closes separately."""
    if polar is None:
        top = _curve_path(xv, yv, sx, sy, smooth, None)
        base = _curve_path(xv[::-1], bv[::-1], sx, sy, smooth, None)
        return f"{top} L {base[2:]} Z" if top and base else ""
    parts = []
    for run in _polar_visible_runs(xv, yv, polar):
        top = _curve_path(xv[run], yv[run], sx, sy, smooth, polar)
        base = _curve_path(xv[run][::-1], bv[run][::-1], sx, sy, smooth, polar)
        if top and base:
            parts.append(f"{top} L {base[2:]} Z")
    return " ".join(parts)


def _curve_path(
    xv: np.ndarray,
    yv: np.ndarray,
    sx: _Scale,
    sy: _Scale,
    smooth: bool,
    polar: "Optional[_PolarProjection]" = None,
) -> str:
    """Pixel-space path for a polyline; smooth -> exact cubic Béziers of the
    monotone-cubic Hermite (affine axes), else polyline. The Bézier control
    points of a Hermite segment are P0 + h/3·(1, m0) and P1 - h/3·(1, m1),
    and affine axis maps carry control points exactly.

    Under `polar` the separable (sx, sy) pair is replaced by the joint
    projection and the result is always a polyline: consecutive data points are
    joined by straight **chords**, which is Plotly's polar semantics and what
    makes radar/spider edges come out straight (polar-axes.md §5). Vertices
    outside the radial range are culled like the client shader culls them —
    the path splits into visible runs, dropping any chord with a culled
    endpoint whole (§8)."""
    if len(xv) == 0:
        # `visible.all()` is vacuously true on an empty array, so this fell
        # through to the native poly-path builder, which rejects a zero-length
        # buffer. A log radial axis annihilating every row, or an all-NaN
        # series, therefore crashed the export instead of drawing nothing.
        return ""
    if polar is not None:
        px, py = polar(xv, yv)
        visible = polar.position_mask(xv, yv)
        if bool(visible.all()):
            return _poly_path(px, py)
        runs = np.split(
            np.flatnonzero(visible),
            np.flatnonzero(np.diff(np.flatnonzero(visible)) > 1) + 1,
        )
        return " ".join(_poly_path(px[run], py[run]) for run in runs if len(run) >= 2)
    px, py = sx(xv), sy(yv)
    if not smooth or len(xv) < 3 or not (sx.affine and sy.affine):
        return _poly_path(px, py)
    m = _monotone_tangents(xv, yv)
    parts = [f"M {_num(px[0])} {_num(py[0])}"]
    for i in range(len(xv) - 1):
        h = xv[i + 1] - xv[i]
        if h <= 0:
            parts.append(f"L {_num(px[i + 1])} {_num(py[i + 1])}")
            continue
        c1x, c1y = sx(xv[i] + h / 3), sy(yv[i] + m[i] * h / 3)
        c2x, c2y = sx(xv[i + 1] - h / 3), sy(yv[i + 1] - m[i + 1] * h / 3)
        parts.append(
            f"C {_num(c1x)} {_num(c1y)} {_num(c2x)} {_num(c2y)} {_num(px[i + 1])} {_num(py[i + 1])}"
        )
    return " ".join(parts)


_SYMBOL_BUILDERS = {
    "pixel": lambda cx, cy, r: (
        f'<rect x="{_num(cx - r)}" y="{_num(cy - r)}" width="{_num(2 * r)}" height="{_num(2 * r)}"'
    ),
    "square": lambda cx, cy, r: (
        f'<rect x="{_num(cx - r)}" y="{_num(cy - r)}" width="{_num(2 * r)}" height="{_num(2 * r)}"'
    ),
    "diamond": lambda cx, cy, r: (
        f'<path d="M {_num(cx)} {_num(cy - 2**0.5 * r)} '
        f"L {_num(cx + 2**0.5 * r)} {_num(cy)} "
        f"L {_num(cx)} {_num(cy + 2**0.5 * r)} "
        f'L {_num(cx - 2**0.5 * r)} {_num(cy)} Z"'
    ),
    "thin_diamond": lambda cx, cy, r: (
        f'<path d="M {_num(cx)} {_num(cy - 2**0.5 * r)} '
        f"L {_num(cx + 0.6 * 2**0.5 * r)} {_num(cy)} "
        f"L {_num(cx)} {_num(cy + 2**0.5 * r)} "
        f'L {_num(cx - 0.6 * 2**0.5 * r)} {_num(cy)} Z"'
    ),
    "triangle": lambda cx, cy, r: (
        f'<path d="M {_num(cx)} {_num(cy - r)} L {_num(cx + r)} {_num(cy + r)} L {_num(cx - r)} {_num(cy + r)} Z"'
    ),
    "triangle_down": lambda cx, cy, r: (
        f'<path d="M {_num(cx)} {_num(cy + r)} L {_num(cx + r)} {_num(cy - r)} L {_num(cx - r)} {_num(cy - r)} Z"'
    ),
    "triangle_left": lambda cx, cy, r: (
        f'<path d="M {_num(cx - r)} {_num(cy)} L {_num(cx + r)} {_num(cy - r)} L {_num(cx + r)} {_num(cy + r)} Z"'
    ),
    "triangle_right": lambda cx, cy, r: (
        f'<path d="M {_num(cx + r)} {_num(cy)} L {_num(cx - r)} {_num(cy - r)} L {_num(cx - r)} {_num(cy + r)} Z"'
    ),
    "cross": lambda cx, cy, r: (
        f'<path d="M {_num(cx - 0.34 * r)} {_num(cy - r)} H {_num(cx + 0.34 * r)} V {_num(cy - 0.34 * r)} '
        f"H {_num(cx + r)} V {_num(cy + 0.34 * r)} H {_num(cx + 0.34 * r)} V {_num(cy + r)} "
        f"H {_num(cx - 0.34 * r)} V {_num(cy + 0.34 * r)} H {_num(cx - r)} V {_num(cy - 0.34 * r)} "
        f'H {_num(cx - 0.34 * r)} Z"'
    ),
    "x": lambda cx, cy, r: (
        f'<path d="M {_num(cx - 0.72 * r)} {_num(cy - r)} L {_num(cx)} {_num(cy - 0.28 * r)} '
        f"L {_num(cx + 0.72 * r)} {_num(cy - r)} L {_num(cx + r)} {_num(cy - 0.72 * r)} "
        f"L {_num(cx + 0.28 * r)} {_num(cy)} L {_num(cx + r)} {_num(cy + 0.72 * r)} "
        f"L {_num(cx + 0.72 * r)} {_num(cy + r)} L {_num(cx)} {_num(cy + 0.28 * r)} "
        f"L {_num(cx - 0.72 * r)} {_num(cy + r)} L {_num(cx - r)} {_num(cy + 0.72 * r)} "
        f'L {_num(cx - 0.28 * r)} {_num(cy)} L {_num(cx - r)} {_num(cy - 0.72 * r)} Z"'
    ),
    "plus_line": lambda cx, cy, r: (
        f'<path d="M {_num(cx - r)} {_num(cy)} H {_num(cx + r)} M {_num(cx)} {_num(cy - r)} V {_num(cy + r)}" fill="none"'
    ),
    "x_line": lambda cx, cy, r: (
        f'<path d="M {_num(cx - 0.707 * r)} {_num(cy - 0.707 * r)} L {_num(cx + 0.707 * r)} {_num(cy + 0.707 * r)} '
        f'M {_num(cx + 0.707 * r)} {_num(cy - 0.707 * r)} L {_num(cx - 0.707 * r)} {_num(cy + 0.707 * r)}" fill="none"'
    ),
    "horizontal_line": lambda cx, cy, r: (
        f'<path d="M {_num(cx - r)} {_num(cy)} H {_num(cx + r)}" fill="none"'
    ),
    "vertical_line": lambda cx, cy, r: (
        f'<path d="M {_num(cx)} {_num(cy - r)} V {_num(cy + r)}" fill="none"'
    ),
    "pentagon": lambda cx, cy, r: _regular_polygon_path(cx, cy, r, 5, -90.0),
    "hexagon": lambda cx, cy, r: _regular_polygon_path(cx, cy, r, 6, -90.0),
    "star": lambda cx, cy, r: _star_path(cx, cy, r, 5, 0.45, -90.0),
}


def _regular_polygon_path(cx: float, cy: float, r: float, n: int, start_deg: float) -> str:
    pts = []
    for i in range(n):
        theta = np.radians(start_deg + i * 360.0 / n)
        pts.append((cx + r * np.cos(theta), cy + r * np.sin(theta)))
    d = "M " + " L ".join(f"{_num(px)} {_num(py)}" for px, py in pts)
    return f'<path d="{d} Z"'


def _star_path(cx: float, cy: float, r: float, points: int, inner: float, start_deg: float) -> str:
    pts = []
    for i in range(points * 2):
        radius = r if i % 2 == 0 else r * inner
        theta = np.radians(start_deg + i * 180.0 / points)
        pts.append((cx + radius * np.cos(theta), cy + radius * np.sin(theta)))
    d = "M " + " L ".join(f"{_num(px)} {_num(py)}" for px, py in pts)
    return f'<path d="{d} Z"'


# ---------------------------------------------------------------------------
# Renderer
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


def _annotation_svg(
    annotations: Sequence[dict[str, Any]],
    sx: Callable[[float], float],
    sy: Callable[[float], float],
    plot: dict[str, float],
    width: float,
    height: float,
    polar: "Optional[_PolarProjection]" = None,
) -> tuple[list[str], list[str], list[str]]:
    marks: list[str] = []
    unclipped_marks: list[str] = []
    labels: list[str] = []
    px0, py0 = plot["x"], plot["y"]

    def point(x: float, y: float) -> tuple[float, float]:
        """A point-anchored annotation's position.

        Under polar the pair is (theta, r) and must project jointly — the
        separable sx/sy would read them as cartesian, putting `(0, 0)` (the
        disc centre, at any angle) in the bottom-left corner instead.

        Only point-anchored kinds route through here. `rule` and `band` are
        genuinely different geometry on a disc — a theta rule is a spoke, an r
        rule is a ring, a band is an annulus or a sector — and stay deferred
        (polar-axes.md §9) rather than being drawn as straight cartesian bars.
        """
        if polar is not None:
            px, py = polar(x, y)
            return float(px), float(py)
        return float(sx(x)), float(sy(y))

    for ann in annotations:
        style = ann.get("style") or {}
        color = escape(_css(style.get("color"), "#667085"))
        opacity = float(style.get("opacity", 1.0))
        start = max(0.0, min(1.0, float(style.get("span_start", 0.0))))
        end = max(start, min(1.0, float(style.get("span_end", 1.0))))
        kind = ann.get("kind")
        if kind == "rule":
            if ann.get("axis") == "x":
                pos = float(sx(float(ann["value"])))
                coords = (pos, py0 + (1 - end) * plot["h"], pos, py0 + (1 - start) * plot["h"])
            else:
                pos = float(sy(float(ann["value"])))
                coords = (px0 + start * plot["w"], pos, px0 + end * plot["w"], pos)
            marks.append(
                f'<line x1="{_num(coords[0])}" y1="{_num(coords[1])}" '
                f'x2="{_num(coords[2])}" y2="{_num(coords[3])}" stroke="{color}" '
                f'stroke-width="{_num(float(style.get("width", 1.5)))}" stroke-opacity="{_num(opacity)}"'
                f"{_dash_attr(style)}/>"
            )
        elif kind == "band":
            a, b = float(ann["start"]), float(ann["end"])
            if ann.get("axis") == "x":
                x0, x1 = sorted((float(sx(a)), float(sx(b))))
                y0, y1 = py0 + (1 - end) * plot["h"], py0 + (1 - start) * plot["h"]
            else:
                y0, y1 = sorted((float(sy(a)), float(sy(b))))
                x0, x1 = px0 + start * plot["w"], px0 + end * plot["w"]
            marks.append(
                f'<rect x="{_num(x0)}" y="{_num(y0)}" width="{_num(x1 - x0)}" '
                f'height="{_num(y1 - y0)}" fill="{color}" fill-opacity="{_num(float(style.get("opacity", 0.14)))}"/>'
            )
        elif kind in ("arrow", "callout"):
            connector_marks = (
                unclipped_marks
                if _annotation_connector_unclipped(ann, sx, sy, plot, polar)
                else marks
            )
            if kind == "arrow":
                x0, y0 = point(float(ann["x0"]), float(ann["y0"]))
                x1, y1 = point(float(ann["x1"]), float(ann["y1"]))
            else:  # pointer from the offset label back to the data point
                x1, y1 = point(float(ann["x"]), float(ann["y"]))
                x0, y0 = x1 + float(ann.get("dx", 0.0)), y1 + float(ann.get("dy", 0.0))
            if all(np.isfinite(v) for v in (x0, y0, x1, y1)):
                shapes = _arrow_shapes(x0, y0, x1, y1, style)
                stroke_width = _num(max(0.5, float(style.get("width", 1.5))))
                if shapes["taper"] is not None:
                    taper = " ".join(f"{_num(px)},{_num(py)}" for px, py in shapes["taper"])
                    connector_marks.append(
                        f'<polygon points="{taper}" fill="{color}" fill-opacity="{_num(opacity)}"/>'
                    )
                else:
                    shaft = " ".join(f"{_num(px)},{_num(py)}" for px, py in shapes["shaft"])
                    connector_marks.append(
                        f'<polyline points="{shaft}" fill="none" '
                        f'stroke="{color}" stroke-width="{stroke_width}" '
                        f'stroke-opacity="{_num(opacity)}"{_dash_attr(style)}/>'
                    )
                for decoration in (shapes["head"], shapes["tail"]):
                    if decoration is None:
                        continue
                    points = " ".join(f"{_num(px)},{_num(py)}" for px, py in decoration["points"])
                    if decoration["kind"] == "fill":
                        connector_marks.append(
                            f'<polygon points="{points}" fill="{color}" '
                            f'fill-opacity="{_num(opacity)}"/>'
                        )
                    else:
                        connector_marks.append(
                            f'<polyline points="{points}" fill="none" stroke="{color}" '
                            f'stroke-width="{stroke_width}" stroke-opacity="{_num(opacity)}"/>'
                        )
        elif kind == "marker":
            mx, my = point(float(ann["x"]), float(ann["y"]))
            if all(np.isfinite(v) for v in (mx, my)):
                radius = max(0.5, float(ann.get("size", 8.0)) / 2.0)
                builder = _SYMBOL_BUILDERS.get(str(ann.get("symbol", "circle")))
                stroke_w = float(style.get("stroke_width", 0.0))
                stroke_attr = (
                    f' stroke="{escape(_css(style.get("stroke_color"), color))}"'
                    f' stroke-width="{_num(stroke_w)}"'
                    + (f' stroke-opacity="{_num(opacity)}"' if opacity < 1 else "")
                    if stroke_w
                    else ""
                )
                fill = escape(_css(style.get("color"), "#2563eb"))
                shape = (
                    f'<circle cx="{_num(mx)}" cy="{_num(my)}" r="{_num(radius)}"'
                    if builder is None
                    else builder(mx, my, radius)
                )
                marks.append(f'{shape} fill="{fill}" fill-opacity="{_num(opacity)}"{stroke_attr}/>')
        if ann.get("text"):
            tx, ty, label_anchor, vertical_align = annotation_label_placement(
                ann, style, sx, sy, plot, width, height, polar
            )
            if not (np.isfinite(tx) and np.isfinite(ty)):
                continue
            style = {**style, "vertical_align": vertical_align} if vertical_align else style
            anchor = {"start": "start", "middle": "middle", "end": "end"}.get(label_anchor, "start")
            font_size = _px_size(style.get("font_size"), 11.0)
            lines = str(ann["text"]).splitlines() or [""]
            line_height = font_size * 1.2
            rotation = float(style.get("rotation", 0.0)) % 360.0
            if rotation in (90.0, 270.0):
                # Vertical text, mirroring the native rasterizer's geometry:
                # vertical_align anchors along the reading axis, the horizontal
                # anchor shifts the baseline across the post-rotation box.
                cw = rotation == 270.0
                va = str(style.get("vertical_align", ""))
                along = {
                    "center": "middle",
                    "top": "start" if cw else "end",
                    "bottom": "end" if cw else "start",
                }.get(va, "start")
                ascent, descent = font_size * 0.78, font_size * 0.22
                if cw:
                    base = {"middle": (descent - ascent) / 2, "end": -ascent}.get(anchor, descent)
                else:
                    base = {"middle": (ascent - descent) / 2, "end": -descent}.get(anchor, ascent)
                stack = -line_height if cw else line_height  # later lines: glyph-down
                by = ty + float(ann.get("dy", 0))
                text_opacity = float(
                    style.get(
                        "label_opacity",
                        style.get("opacity", 1.0) if kind == "text" else 1.0,
                    )
                )
                line_offset = 0
                for index, line in enumerate(lines):
                    bx = tx + float(ann.get("dx", 0)) + base + index * stack
                    styled_line = _svg_mathtext_spans(line, style, line_offset)
                    labels.append(
                        f'<text text-anchor="{along}" font-size="{_num(font_size)}" '
                        f'transform="rotate({90 if cw else -90} {_num(bx)} {_num(by)})" '
                        f'x="{_num(bx)}" y="{_num(by)}" '
                        + (f'fill-opacity="{_num(text_opacity)}" ' if text_opacity < 1 else "")
                        + f'fill="{color}">{styled_line}</text>'
                    )
                    line_offset += len(line) + 1
                continue
            x_text = tx + float(ann.get("dx", 0))
            vertical_align = style.get("vertical_align")
            y_text = _annotation_first_baseline(
                ty + float(ann.get("dy", 0)),
                len(lines),
                line_height,
                font_size,
                vertical_align,
            )
            line_offset = 0
            tspan_parts = []
            for index, line in enumerate(lines):
                styled_line = _svg_mathtext_spans(line, style, line_offset)
                tspan_parts.append(
                    f'<tspan x="{_num(x_text)}" y="{_num(y_text + index * line_height)}">'
                    f"{styled_line}</tspan>"
                )
                line_offset += len(line) + 1
            tspans = "".join(tspan_parts)
            text_opacity = float(
                style.get(
                    "label_opacity",
                    style.get("opacity", 1.0) if kind == "text" else 1.0,
                )
            )
            # A callout's `color` paints its arrow; the label prefers its own.
            label_color = escape(_css(style.get("label_color"), "")) or color
            labels.extend(
                _svg_text_box(style, lines, x_text, y_text, line_height, font_size, anchor)
            )
            font_attrs = _svg_font_attrs(style)
            rotation_attr = (
                f' transform="rotate({_num(-rotation)} {_num(x_text)} {_num(y_text)})"'
                if rotation
                else ""
            )
            labels.append(
                f'<text text-anchor="{anchor}" font-size="{_num(font_size)}"{font_attrs}'
                f"{rotation_attr} "
                + (f'fill-opacity="{_num(text_opacity)}" ' if text_opacity < 1 else "")
                + f'fill="{label_color}">{tspans}</text>'
            )
    return marks, unclipped_marks, labels


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


def _authored_marker_path_d(
    marker_path: dict[str, Any], cx: float, cy: float, diameter: float
) -> str:
    parts: list[str] = []
    for contour in marker_path.get("contours") or ():
        values = np.asarray(contour, dtype=np.float64).reshape(-1, 2)
        if not len(values):
            continue
        px, py = _authored_marker_points(values[:, 0], values[:, 1], cx, cy, diameter)
        parts.append(f"M {_num(float(px[0]))} {_num(float(py[0]))}")
        parts.extend(
            f"L {_num(float(x))} {_num(float(y))}" for x, y in zip(px[1:], py[1:], strict=True)
        )
        if bool(marker_path.get("filled", True)):
            parts.append("Z")
    return " ".join(parts)


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
    svg: "_Svg",
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


def _bar_fill(style: dict, color: str, svg: _Svg, plot: dict) -> tuple[str, str]:
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
    svg: _Svg,
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
    svg: _Svg,
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
    svg: _Svg,
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
    d: dict, blob: bytes, cols: list, sx: _Scale, sy: _Scale, style: dict, svg: _Svg
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


# Trace kinds whose legend entry is a short line sample rather than a marker
# glyph or filled patch (mirrors _raster._LEGEND_LINE_KINDS).
_LEGEND_LINE_KINDS = frozenset({"line", "segments", "step", "stairs", "errorbar"})


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


def _legend_marker_svg(style: dict[str, Any], x: float, y: float, default_color: str) -> str:
    """Render one Matplotlib legend marker at the center of its line handle."""
    symbol = str(style.get("symbol", "circle"))
    builder = _SYMBOL_BUILDERS.get(symbol)
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
        d = _authored_marker_path_d(marker_path, float(x), float(y), 2 * radius)
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
            _star_path((x0 + x1) / 2, mid_y, radius, 5, 0.45, -90.0) + f' fill="{escape(color)}"/>'
        )
    if paths:
        shapes.insert(
            0,
            f'<path d="{" ".join(paths)}" fill="none" stroke="{escape(color)}" stroke-width="1"/>',
        )
    return "".join(shapes)


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
