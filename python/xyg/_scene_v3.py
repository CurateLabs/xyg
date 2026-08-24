"""Thin figure-to-Scene v12 compiler for the migrated core-mark subset.

Rust owns mapping, clipping, record semantics, SVG construction, and raster
display-list construction. This module only projects already-validated Figure
objects into the typed ABI and rejects features whose canonical Scene record
does not exist yet.
"""

from __future__ import annotations

import struct
from typing import Any

import numpy as np

from . import _native
from ._scene import RIBBON_STEPS, ribbon_edge
from .marks import _SYMBOL_CODES

# Host mark kinds that lower to Scene Rect (kind 2). Geometry is already
# x0/y0/x1/y1 columns on the Trace; Scene does not recompute bar stacking.
_RECT_KINDS = frozenset({"bar", "column", "histogram", "violin", "box"})
# Endpoint pairs that lower to disconnected Scene Polyline runs (kind 1).
_SEGMENT_KINDS = frozenset({"segments", "errorbar", "stem", "contour", "box_whisker", "box_median"})
# Top/base samples that lower to Scene Band (kind 3) filled polygons.
_BAND_KINDS = frozenset({"area", "error_band"})
# Host-tessellated flow bands also lower to Scene Band samples.
_RIBBON_KINDS = frozenset({"ribbon"})
# Independent triangles lower to Scene PolyFill (kind 4) vertex runs.
_POLYFILL_KINDS = frozenset({"triangle_mesh"})
_POINT_KINDS = frozenset({"scatter", "line"})
_SUPPORTED_KINDS = (
    _POINT_KINDS | _RECT_KINDS | _SEGMENT_KINDS | _BAND_KINDS | _RIBBON_KINDS | _POLYFILL_KINDS
)
_STROKE_KINDS = frozenset({"line"}) | _SEGMENT_KINDS

_LEGEND_LOCATIONS = {
    "upper right": 0,
    "upper left": 1,
    "lower left": 2,
    "lower right": 3,
    "center right": 4,
    "center left": 5,
    "upper center": 6,
    "lower center": 7,
    "center": 8,
}


def _colorbar_input(figure: Any) -> bytes:
    """Frame only the small literal XYCB subset; Rust resolves all policy."""
    options = getattr(figure, "colorbar_options", None)
    if not options:
        return b""
    if not isinstance(options, dict) or set(options) - {
        "domain",
        "stops",
        "side",
        "title",
        "text_rgba",
        "ticks",
        "minor_ticks",
    }:
        raise UnsupportedSceneV3("Scene v19 colorbars require literal bounded RGBA stops")
    domain = options.get("domain")
    stops = options.get("stops")
    if not (
        isinstance(domain, (list, tuple))
        and len(domain) == 2
        and isinstance(stops, (list, tuple))
        and 2 <= len(stops) <= 16
    ):
        raise UnsupportedSceneV3(
            "Scene v19 colorbars require a two-value domain and 2-16 literal stops"
        )
    try:
        lo, hi = (float(domain[0]), float(domain[1]))
        parsed = [(float(item[0]), bytes(item[1])) for item in stops]
    except (TypeError, ValueError, IndexError):
        raise UnsupportedSceneV3(
            "Scene v19 colorbar stops are (finite value, RGBA[4]) pairs"
        ) from None
    if not np.isfinite([lo, hi]).all() or lo >= hi or any(len(rgba) != 4 for _, rgba in parsed):
        raise UnsupportedSceneV3(
            "Scene v19 colorbar values must be finite and RGBA literals exactly four bytes"
        )
    if (
        parsed[0][0] != lo
        or parsed[-1][0] != hi
        or any(value <= parsed[index - 1][0] for index, (value, _) in enumerate(parsed) if index)
    ):
        raise UnsupportedSceneV3(
            "Scene v19 colorbar stops must be strictly increasing and match the domain endpoints"
        )
    horizontal = options.get("side", "right") == "bottom"
    if options.get("side", "right") not in {"right", "bottom"}:
        raise UnsupportedSceneV3("Scene v19 colorbars support only right or bottom placement")
    title = options.get("title", "")
    if not isinstance(title, str):
        raise UnsupportedSceneV3("Scene v19 colorbar title must be a string")
    title_b = title.encode("utf-8")
    try:
        text_rgba = bytes(options.get("text_rgba", (32, 32, 32, 255)))
    except (TypeError, ValueError):
        raise UnsupportedSceneV3(
            "Scene v19 colorbar text is bounded and uses literal RGBA"
        ) from None
    if len(title_b) > 4096 or len(text_rgba) != 4:
        raise UnsupportedSceneV3("Scene v19 colorbar text is bounded and uses literal RGBA")
    raw_ticks = options.get("ticks")
    if raw_ticks is None:
        ticks: list[float] = []
    elif not isinstance(raw_ticks, (list, tuple)) or len(raw_ticks) > 32:
        raise UnsupportedSceneV3("Scene v19 colorbar ticks are limited to 32 finite ordered values")
    else:
        try:
            ticks = [float(value) for value in raw_ticks]
        except (TypeError, ValueError):
            raise UnsupportedSceneV3(
                "Scene v19 colorbar ticks are limited to 32 finite ordered values"
            ) from None
        if (
            not np.isfinite(ticks).all()
            or any(value < lo or value > hi for value in ticks)
            or any(value <= ticks[index - 1] for index, value in enumerate(ticks) if index)
        ):
            raise UnsupportedSceneV3(
                "Scene v19 colorbar ticks are limited to 32 finite ordered values"
            )
    minor_ticks = options.get("minor_ticks", False)
    if not isinstance(minor_ticks, bool):
        raise UnsupportedSceneV3("Scene v19 colorbar minor_ticks must be a boolean")
    authored_ticks = bool(ticks)
    out = bytearray(56 + len(parsed) * 12 + len(ticks) * 8 + len(title_b))
    out[:4] = b"XYCB"
    struct.pack_into("<I", out, 4, 2)
    out[8] = int(horizontal) | 2 | (int(minor_ticks) << 2) | (int(authored_ticks) << 3)
    struct.pack_into("<III2d", out, 12, len(parsed), len(ticks), len(title_b), lo, hi)
    out[40:44] = text_rgba
    for index, (value, rgba) in enumerate(parsed):
        struct.pack_into("<d", out, 56 + index * 12, value)
        out[64 + index * 12 : 68 + index * 12] = rgba
    ticks_start = 56 + len(parsed) * 12
    for index, value in enumerate(ticks):
        struct.pack_into("<d", out, ticks_start + index * 8, value)
    out[ticks_start + len(ticks) * 8 :] = title_b
    return bytes(out)


def _legend_input(
    figure: Any, entries: list[tuple[int, int, int, str]], styles: list[Any]
) -> bytes:
    if not figure.show_legend or not entries:
        return b""
    options = dict(figure.legend_options or {})
    unsupported = {
        key
        for key in options
        if key not in {"loc", "title", "ncols", "style", "highlight", "toggle"}
    }
    if unsupported or int(options.get("ncols") or 1) != 1:
        raise UnsupportedSceneV3(
            "Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content"
        )
    if any(key in options and options[key] is not False for key in ("toggle", "highlight")):
        raise UnsupportedSceneV3(
            "Scene v12 primary legends are static; toggle and highlight must be false"
        )
    authored_loc = options.get("loc")
    loc = "upper right" if authored_loc is None else str(authored_loc)
    if loc not in _LEGEND_LOCATIONS:
        raise UnsupportedSceneV3(f"Scene v12 does not support legend location {loc!r}")
    style = dict(options.get("style") or {})
    unsupported_style = set(style) - {"background", "color", "font_size", "title_font_size"}
    if unsupported_style:
        raise UnsupportedSceneV3(
            "Scene v12 legends support only background, color, font_size, and title_font_size"
        )
    authored_font_size = style.get("font_size")
    authored_title_font_size = style.get("title_font_size")
    font_size = 0.0 if authored_font_size is None else float(authored_font_size)
    title_font_size = 0.0 if authored_title_font_size is None else float(authored_title_font_size)
    if not (
        (authored_font_size is None or 1.0 <= font_size <= 1000.0)
        and (authored_title_font_size is None or 1.0 <= title_font_size <= 1000.0)
    ):
        raise ValueError("legend font sizes must be finite and in [1, 1000]")
    title_value = options.get("title")
    if isinstance(title_value, bool):
        title_value = str(title_value).lower()
    title = str("" if title_value is None else title_value).encode("utf-8")
    labels = [label.encode("utf-8") for _, _, _, label in entries]
    if len(entries) > 128 or any(not label or len(label) > 4096 for label in labels):
        raise ValueError("Scene v12 legends are limited to 128 nonempty 4096-byte labels")
    text_bytes = len(title) + sum(map(len, labels))
    if text_bytes > _native.MAX_SCENE_LEGEND_INPUT_BYTES - 48 - 128 * 24 or len(title) > 4096:
        raise ValueError("Scene v12 legend text is limited to 16,384 UTF-8 bytes")
    out = bytearray(48 + len(entries) * 24)
    out[:4] = b"XYLG"
    out[4] = _LEGEND_LOCATIONS[loc]
    out[5] = (
        int(authored_loc is not None)
        | (int(authored_font_size is not None) << 1)
        | (int(authored_title_font_size is not None) << 2)
        | (int("color" in style) << 3)
        | (int("background" in style) << 4)
    )
    struct.pack_into("<II2d", out, 8, len(entries), len(title), font_size, title_font_size)
    if "color" in style:
        out[32:36] = bytes(_rgba(str(style["color"]), 1.0))
    if "background" in style:
        out[36:40] = bytes(_rgba(str(style["background"]), 1.0))
    text_offset = len(title)
    for index, ((style_ref, kind, symbol, _), label) in enumerate(
        zip(entries, labels, strict=True)
    ):
        offset = 48 + index * 24
        struct.pack_into(
            "<IBBHII", out, offset, style_ref, kind, symbol, 0, text_offset, len(label)
        )
        fill, stroke, _ = styles[style_ref]
        out[offset + 16 : offset + 20] = bytes(fill)
        out[offset + 20 : offset + 24] = bytes(stroke)
        text_offset += len(label)
    out.extend(title)
    for label in labels:
        out.extend(label)
    return bytes(out)


_KIND_CODES = {
    "scatter": 0,
    "line": 1,
    "segments": 1,
    "errorbar": 1,
    "stem": 1,
    "contour": 1,
    "box_whisker": 1,
    "box_median": 1,
    "bar": 2,
    "column": 2,
    "histogram": 2,
    "violin": 2,
    "box": 2,
    "area": 3,
    "error_band": 3,
    "ribbon": 3,
    "triangle_mesh": 4,
}


class UnsupportedSceneV3(ValueError):
    """The figure uses a feature outside the currently migrated Scene subset."""


def _rgba(css: str, opacity: float) -> tuple[int, int, int, int]:
    from ._raster import _parse_color

    return _parse_color(css, opacity)


def _constant_color(trace: Any, fallback: str) -> str:
    channel = trace.color_ch
    if getattr(trace, "color2_ch", None) is not None:
        raise UnsupportedSceneV3("Scene v12 does not yet encode two-ended ribbon gradients")
    if channel is None:
        return str(trace.style.get("color", fallback))
    if channel.mode != "constant" or channel.constant is None:
        raise UnsupportedSceneV3("Scene v12 does not yet support data-driven paint channels")
    return channel.constant


_SCENE_AXIS_STYLE_KEYS = frozenset(
    {
        "grid_color",
        "grid_width",
        "grid_opacity",
        "axis_color",
        "axis_width",
        "tick_color",
        "tick_width",
        "tick_length",
        "tick_direction",
        "tick_label_color",
        "label_color",
    }
)


def _scene_side_mask(
    values: Any,
    name: str,
    axis_id: str,
    allowed: tuple[str, str],
    side_code: int,
) -> int:
    if values is None:
        return 1 << side_code
    if any(value not in allowed for value in values):
        raise UnsupportedSceneV3(
            f"Scene v12 {axis_id} axis {name} must contain only {list(allowed)!r}"
        )
    return sum(1 << index for index, candidate in enumerate(allowed) if candidate in values)


def _scene_chrome_style(figure: Any) -> bytes:
    """Pack the generated ABI's fixed Scene v12 chrome style input."""
    result = bytearray(200)
    figure_style = getattr(figure, "style", None) or {}
    result[0:4] = bytes(_rgba(str(figure_style.get("background") or "transparent"), 1.0))
    result[4:8] = bytes(_rgba(str(figure_style.get("--chart-bg") or "transparent"), 1.0))
    result[8:12] = bytes((32, 32, 32, 217))
    struct.pack_into("<d", result, 16, 12.0)
    for axis_id, offset in (("x", 24), ("y", 112)):
        options = figure.axis_options[axis_id]
        style = dict(options.get("style") or {})
        minor = dict(options.get("minor_style") or {})
        for label, authored in (("style", style), ("minor_style", minor)):
            unsupported = set(authored) - _SCENE_AXIS_STYLE_KEYS
            if unsupported:
                raise UnsupportedSceneV3(
                    f"Scene v12 does not yet encode {axis_id} axis {label} keys {sorted(unsupported)!r}"
                )
        side = options.get("side", "bottom" if axis_id == "x" else "left")
        allowed = ("bottom", "top") if axis_id == "x" else ("left", "right")
        if side not in allowed:
            raise UnsupportedSceneV3(
                f"Scene v12 {axis_id} axis side must be one of {list(allowed)!r}"
            )
        side_low = side in {"bottom", "left"}
        side_code = 0 if side_low else 1
        tick_sides = options.get("tick_sides")
        label_sides = options.get("tick_label_sides")

        result[offset] = side_code
        result[offset + 1] = _scene_side_mask(tick_sides, "tick_sides", axis_id, allowed, side_code)
        result[offset + 2] = _scene_side_mask(
            label_sides, "tick_label_sides", axis_id, allowed, side_code
        )
        directions = {"out": 0, "in": 1, "inout": 2}
        result[offset + 3] = directions.get(str(style.get("tick_direction", "out")), 255)
        result[offset + 4] = directions.get(str(minor.get("tick_direction", "out")), 255)
        grid_opacity = float(style.get("grid_opacity", 1.0))
        minor_grid_opacity = float(minor.get("grid_opacity", 1.0))
        colors = (
            _rgba(str(style.get("axis_color", "#202020")), 1.0 if "axis_color" in style else 0.55),
            _rgba(
                str(style.get("grid_color", "#202020")),
                grid_opacity * (1.0 if "grid_color" in style else 0.14),
            ),
            _rgba(str(style.get("tick_color", "#202020")), 1.0 if "tick_color" in style else 0.55),
            _rgba(str(minor.get("grid_color", "transparent")), minor_grid_opacity),
            _rgba(str(minor.get("tick_color", "#202020")), 1.0 if "tick_color" in minor else 0.55),
            _rgba(
                str(style.get("tick_label_color", style.get("label_color", "#202020"))),
                1.0 if ("tick_label_color" in style or "label_color" in style) else 0.85,
            ),
        )
        for index, color in enumerate(colors):
            result[offset + 8 + index * 4 : offset + 12 + index * 4] = bytes(color)
        struct.pack_into(
            "<7d",
            result,
            offset + 32,
            float(style.get("axis_width", 1.0)),
            float(style.get("grid_width", 1.0)),
            float(style.get("tick_width", 1.0)),
            float(style.get("tick_length", 4.0)),
            float(minor.get("grid_width", 1.0)),
            float(minor.get("tick_width", 1.0)),
            float(minor.get("tick_length", 0.0)),
        )
    return bytes(result)


def _reject_rect_extras(style: dict[str, Any], kind: str) -> None:
    fill = style.get("fill")
    if isinstance(fill, dict):
        raise UnsupportedSceneV3(f"Scene v12 does not yet encode {kind} gradient fills")
    radius = style.get("corner_radius", 0.0)
    if isinstance(radius, (list, tuple)):
        if any(float(value) != 0.0 for value in radius):
            raise UnsupportedSceneV3(f"Scene v12 does not yet encode {kind} corner_radius")
    elif float(radius) != 0.0:
        raise UnsupportedSceneV3(f"Scene v12 does not yet encode {kind} corner_radius")
    if float(style.get("wedge_gap", 0.0) or 0.0) != 0.0:
        raise UnsupportedSceneV3(f"Scene v12 does not yet encode {kind} wedge_gap")


def _step_arrays(xv: np.ndarray, yv: np.ndarray, where: str) -> tuple[np.ndarray, np.ndarray]:
    """Expand compact step samples into polyline corners (parity with `_svg`)."""
    if len(xv) < 2:
        return xv, yv
    xs = [float(xv[0])]
    ys = [float(yv[0])]
    for index in range(1, len(xv)):
        if where == "pre":
            xs.extend((float(xv[index - 1]), float(xv[index])))
            ys.extend((float(yv[index]), float(yv[index])))
        elif where == "mid":
            mid = (float(xv[index - 1]) + float(xv[index])) * 0.5
            xs.extend((mid, mid, float(xv[index])))
            ys.extend((float(yv[index - 1]), float(yv[index]), float(yv[index])))
        else:
            xs.extend((float(xv[index]), float(xv[index])))
            ys.extend((float(yv[index - 1]), float(yv[index])))
    return np.asarray(xs), np.asarray(ys)


def _rect_columns(trace: Any) -> list[np.ndarray]:
    if any(value is None for value in (trace.x0, trace.y0, trace.x1, trace.y1)):
        raise ValueError(f"{trace.kind} Scene v12 compilation requires four rectangle columns")
    arrays = [trace.x0.values, trace.y0.values, trace.x1.values, trace.y1.values]
    lengths = {len(column) for column in arrays}
    if len(lengths) != 1:
        raise UnsupportedSceneV3(f"Scene v12 {trace.kind} rectangle columns must have equal length")
    return arrays


def _segment_columns(trace: Any) -> list[np.ndarray]:
    if any(value is None for value in (trace.x0, trace.y0, trace.x1, trace.y1)):
        raise ValueError(f"{trace.kind} Scene v12 compilation requires four endpoint columns")
    arrays = [trace.x0.values, trace.y0.values, trace.x1.values, trace.y1.values]
    lengths = {len(column) for column in arrays}
    if len(lengths) != 1:
        raise UnsupportedSceneV3(f"Scene v12 {trace.kind} endpoint columns must have equal length")
    return arrays


def _band_columns(trace: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if trace.x is None or trace.y is None or trace.base is None:
        raise ValueError(f"{trace.kind} Scene v12 compilation requires x, y, and base columns")
    xv = np.asarray(trace.x.values, dtype=np.float64)
    yv = np.asarray(trace.y.values, dtype=np.float64)
    base = np.asarray(trace.base.values, dtype=np.float64)
    if not (len(xv) == len(yv) == len(base)):
        raise UnsupportedSceneV3(f"Scene v12 {trace.kind} band columns must have equal length")
    return xv, yv, base


def _ribbon_band_samples(
    x0: float, x1: float, source_lo: float, source_hi: float, target_lo: float, target_hi: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Tessellate one flow band into Band top/base samples (data space)."""
    upper = ribbon_edge(x0, x1, source_hi, target_hi, RIBBON_STEPS)
    lower = ribbon_edge(x0, x1, source_lo, target_lo, RIBBON_STEPS)
    return upper[:, 0], upper[:, 1], lower[:, 0], lower[:, 1]


def figure_scene(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
    margins: tuple[float, float, float, float] | None = None,
) -> bytes:
    """Compile migrated cartesian marks plus x/y axes to Scene v12."""
    annotations = list(getattr(figure, "annotations", None) or [])
    features = 0
    if figure.coords != "cartesian":
        features |= 1 << 0
    chrome_styles = getattr(figure, "chrome_styles", None) or {}
    if any("font-family" in (style or {}) for style in chrome_styles.values()):
        features |= 1 << 1
    if (
        getattr(figure, "class_name", None)
        or getattr(figure, "class_names", None)
        or chrome_styles
        or set(getattr(figure, "style", None) or {}) - {"background", "--chart-bg"}
        or any(annotation.get("class_name") not in (None, "") for annotation in annotations)
    ):
        features |= 1 << 2
    if any(
        isinstance((getattr(trace, "style", None) or {}).get("fill"), dict)
        or getattr(trace, "color2_ch", None) is not None
        or (
            getattr(trace, "color_ch", None) is not None
            and (trace.color_ch.mode != "constant" or trace.color_ch.constant is None)
        )
        for trace in figure.traces
    ):
        features |= 1 << 3
    try:
        colorbar_input = _colorbar_input(figure)
    except UnsupportedSceneV3:
        colorbar_input = b""
        features |= 1 << 4
    if figure.extra_legends:
        features |= 1 << 5
    if any(
        annotation.get("kind") not in {"callout", "arrow", "text"}
        and annotation.get("text") not in (None, "")
        for annotation in annotations
    ):
        features |= 1 << 7
    reason = _native.scene_support_reason(features)
    if reason:
        raise UnsupportedSceneV3(reason)
    if set(figure.axis_options) != {"x", "y"}:
        raise UnsupportedSceneV3("Scene v12 figure compilation currently supports exactly x/y axes")
    for options in figure.axis_options.values():
        supported_axis_keys = {
            "type",
            "constant",
            "domain",
            "nonpositive",
            "label",
            "side",
            "tick_sides",
            "tick_label_sides",
            "style",
            "minor_style",
            "tick_values",
            "tick_labels",
            "minor_tick_values",
        }
        if any(
            key not in supported_axis_keys and value not in (None, False, [], {})
            for key, value in options.items()
        ):
            raise UnsupportedSceneV3(
                "Scene v12 does not yet encode tick formatting, collision policy, or advanced axis layout"
            )
    unsupported = next(
        (trace.kind for trace in figure.traces if trace.kind not in _SUPPORTED_KINDS), None
    )
    if unsupported is not None:
        raise UnsupportedSceneV3(f"Scene v12 figure compilation does not yet support {unsupported}")

    kinds: list[int] = []
    stable_ids: list[int] = []
    style_refs: list[int] = []
    styles: list[tuple[tuple[int, ...], tuple[int, ...], float]] = []
    diameters: list[float] = []
    symbols: list[int] = []
    coordinates: list[list[float]] = [[], [], [], []]
    legend_entries: list[tuple[int, int, int, str]] = []
    for trace in figure.traces:
        if trace.x_axis != "x" or trace.y_axis != "y":
            raise UnsupportedSceneV3("Scene v12 currently supports only the primary x/y axes")
        if trace.hidden or trace.has_per_item_channels():
            raise UnsupportedSceneV3(
                "Scene v12 does not yet encode hidden or per-item styled marks"
            )
        if trace.kind == "scatter" and trace.use_density():
            raise UnsupportedSceneV3("Scene v12 does not yet encode density-tier scatter")
        style = trace.style
        if any(key in style for key in ("dash", "curve", "linecap", "marker_path", "marker_glyph")):
            raise UnsupportedSceneV3(
                "Scene v12 does not yet encode dashed, curved, or authored markers"
            )
        if trace.kind in _RECT_KINDS:
            _reject_rect_extras(style, trace.kind)
        if trace.kind in _POLYFILL_KINDS and style.get("joined_fill"):
            raise UnsupportedSceneV3("Scene v12 does not yet encode joined triangle-mesh fills")
        opacity = float(style.get("opacity", 1.0))
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ValueError("trace opacity must be finite and in [0, 1]")
        color = _constant_color(trace, "#3987e5")
        if trace.kind in _SEGMENT_KINDS:
            fill_default = "transparent"
        elif trace.kind in _BAND_KINDS | _RIBBON_KINDS | _POLYFILL_KINDS:
            fill_default = color
        else:
            fill_default = color
        fill_value = style.get("fill", fill_default)
        if not isinstance(fill_value, str):
            raise UnsupportedSceneV3(f"Scene v12 does not yet encode {trace.kind} non-CSS fills")
        fill = _rgba(fill_value, opacity)
        stroke_default = color if trace.kind in _STROKE_KINDS else "transparent"
        if trace.kind in _RIBBON_KINDS | _POLYFILL_KINDS:
            stroke_default = str(style.get("stroke", "transparent"))
        stroke = _rgba(str(style.get("stroke", stroke_default)), opacity)
        width_value = style.get(
            "stroke_width",
            style.get("width", 1.5 if trace.kind in _STROKE_KINDS else 0.0),
        )
        stroke_width = float(width_value)
        styles.append((fill, stroke, stroke_width))
        style_ref = len(styles) - 1
        symbol_name = str(style.get("symbol", "circle"))
        if symbol_name not in _SYMBOL_CODES:
            raise UnsupportedSceneV3(f"Scene v12 does not support scatter symbol {symbol_name!r}")
        diameter = (
            float(trace.size_ch.constant)
            if trace.kind == "scatter" and trace.size_ch is not None
            else float(style.get("size", 4.0))
        )
        kind_code = _KIND_CODES[trace.kind]
        if trace.name and figure.show_legend:
            legend_kind = 0 if trace.kind == "scatter" else 1 if trace.kind in _STROKE_KINDS else 2
            legend_entries.append(
                (
                    style_ref,
                    legend_kind,
                    _SYMBOL_CODES[symbol_name] if legend_kind == 0 else 0,
                    str(trace.name),
                )
            )

        if trace.kind in _RIBBON_KINDS:
            if any(
                value is None
                for value in (trace.x0, trace.x1, trace.y0, trace.y1, trace.x, trace.y)
            ):
                raise ValueError("ribbon Scene v12 compilation requires six geometry columns")
            x0s = np.asarray(trace.x0.values, dtype=np.float64)
            x1s = np.asarray(trace.x1.values, dtype=np.float64)
            source_lo = np.asarray(trace.y0.values, dtype=np.float64)
            source_hi = np.asarray(trace.y1.values, dtype=np.float64)
            target_lo = np.asarray(trace.x.values, dtype=np.float64)
            target_hi = np.asarray(trace.y.values, dtype=np.float64)
            if not (
                len(x0s)
                == len(x1s)
                == len(source_lo)
                == len(source_hi)
                == len(target_lo)
                == len(target_hi)
            ):
                raise UnsupportedSceneV3("Scene v12 ribbon columns must have equal length")
            arrays = (x0s, x1s, source_lo, source_hi, target_lo, target_hi)
            if any(not np.isfinite(column).all() for column in arrays):
                raise UnsupportedSceneV3(
                    "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
                )
            for band_index in range(len(x0s)):
                tops_x, tops_y, bases_x, bases_y = _ribbon_band_samples(
                    float(x0s[band_index]),
                    float(x1s[band_index]),
                    float(source_lo[band_index]),
                    float(source_hi[band_index]),
                    float(target_lo[band_index]),
                    float(target_hi[band_index]),
                )
                stable_id = (int(trace.id) << 32) | band_index
                for sample in range(len(tops_x)):
                    kinds.append(3)
                    stable_ids.append(stable_id)
                    style_refs.append(style_ref)
                    diameters.append(0.0)
                    symbols.append(0)
                    coordinates[0].append(float(tops_x[sample]))
                    coordinates[1].append(float(tops_y[sample]))
                    coordinates[2].append(float(bases_x[sample]))
                    coordinates[3].append(float(bases_y[sample]))
            continue

        if trace.kind in _POLYFILL_KINDS:
            if any(
                value is None
                for value in (trace.x0, trace.y0, trace.x1, trace.y1, trace.x, trace.y)
            ):
                raise ValueError("triangle_mesh Scene v12 compilation requires six vertex columns")
            x0s = np.asarray(trace.x0.values, dtype=np.float64)
            y0s = np.asarray(trace.y0.values, dtype=np.float64)
            x1s = np.asarray(trace.x1.values, dtype=np.float64)
            y1s = np.asarray(trace.y1.values, dtype=np.float64)
            x2s = np.asarray(trace.x.values, dtype=np.float64)
            y2s = np.asarray(trace.y.values, dtype=np.float64)
            if not (len(x0s) == len(y0s) == len(x1s) == len(y1s) == len(x2s) == len(y2s)):
                raise UnsupportedSceneV3("Scene v12 triangle_mesh columns must have equal length")
            arrays = (x0s, y0s, x1s, y1s, x2s, y2s)
            if any(not np.isfinite(column).all() for column in arrays):
                raise UnsupportedSceneV3(
                    "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
                )
            for tri_index in range(len(x0s)):
                stable_id = (int(trace.id) << 32) | tri_index
                for px, py in (
                    (float(x0s[tri_index]), float(y0s[tri_index])),
                    (float(x1s[tri_index]), float(y1s[tri_index])),
                    (float(x2s[tri_index]), float(y2s[tri_index])),
                ):
                    kinds.append(4)
                    stable_ids.append(stable_id)
                    style_refs.append(style_ref)
                    diameters.append(0.0)
                    symbols.append(0)
                    coordinates[0].append(px)
                    coordinates[1].append(py)
                    coordinates[2].append(0.0)
                    coordinates[3].append(0.0)
            continue

        if trace.kind in _BAND_KINDS:
            xv, yv, base = _band_columns(trace)
            if not (np.isfinite(xv).all() and np.isfinite(yv).all() and np.isfinite(base).all()):
                raise UnsupportedSceneV3(
                    "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
                )
            for index in range(len(xv)):
                kinds.append(3)
                stable_ids.append(int(trace.id))
                style_refs.append(style_ref)
                diameters.append(0.0)
                symbols.append(0)
                coordinates[0].append(float(xv[index]))
                coordinates[1].append(float(yv[index]))
                coordinates[2].append(float(xv[index]))
                coordinates[3].append(float(base[index]))
            continue

        if trace.kind in _RECT_KINDS:
            arrays = _rect_columns(trace)
            if any(not np.isfinite(source).all() for source in arrays):
                raise UnsupportedSceneV3(
                    "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
                )
            for index in range(len(arrays[0])):
                kinds.append(kind_code)
                stable_ids.append(int(trace.id))
                style_refs.append(style_ref)
                diameters.append(0.0)
                symbols.append(0)
                for destination, source in zip(coordinates, arrays, strict=True):
                    destination.append(float(source[index]))
            continue

        if trace.kind in _SEGMENT_KINDS:
            arrays = _segment_columns(trace)
            if any(not np.isfinite(source).all() for source in arrays):
                raise UnsupportedSceneV3(
                    "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
                )
            x0s, y0s, x1s, y1s = arrays
            for index in range(len(x0s)):
                # Unique stable id per segment so polyline runs stay disconnected.
                stable_id = (int(trace.id) << 32) | index
                for x_value, y_value in (
                    (float(x0s[index]), float(y0s[index])),
                    (float(x1s[index]), float(y1s[index])),
                ):
                    kinds.append(1)
                    stable_ids.append(stable_id)
                    style_refs.append(style_ref)
                    diameters.append(0.0)
                    symbols.append(0)
                    coordinates[0].append(x_value)
                    coordinates[1].append(y_value)
                    coordinates[2].append(0.0)
                    coordinates[3].append(0.0)
            continue

        xv = np.asarray(trace.x.values, dtype=np.float64)
        yv = np.asarray(trace.y.values, dtype=np.float64)
        where = style.get("step")
        if where is not None:
            if trace.kind != "line":
                raise UnsupportedSceneV3("Scene v12 step expansion applies only to line traces")
            if where not in {"pre", "post", "mid"}:
                raise UnsupportedSceneV3(f"Scene v12 does not support step mode {where!r}")
            xv, yv = _step_arrays(xv, yv, where)
        if not np.isfinite(xv).all() or not np.isfinite(yv).all():
            raise UnsupportedSceneV3(
                "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
            )
        for index in range(len(xv)):
            kinds.append(kind_code)
            stable_ids.append(int(trace.id))
            style_refs.append(style_ref)
            diameters.append(diameter if trace.kind == "scatter" else 0.0)
            symbols.append(_SYMBOL_CODES[symbol_name] if trace.kind == "scatter" else 0)
            coordinates[0].append(float(xv[index]))
            coordinates[1].append(float(yv[index]))
            coordinates[2].append(0.0)
            coordinates[3].append(0.0)

    # Scene v12's bounded primary-annotation subset is represented by ordinary
    # canonical records with a reserved stable-id namespace. Rust therefore
    # remains the sole owner of scale projection, clipping, painter lowering,
    # SVG/raster order and marker geometry; hosts only coerce authored values.
    annotation_prefix = 0x5859000000000000
    x_domain = tuple(float(value) for value in figure._range("x"))
    y_domain = tuple(float(value) for value in figure._range("y"))

    def annotation_number(values: dict[str, Any], key: str, default: Any, label: str) -> float:
        raw = values.get(key, default)
        if (
            raw is None
            or isinstance(raw, (bool, np.bool_))
            or (isinstance(raw, str) and not raw.strip())
        ):
            raise ValueError(f"Scene v12 annotation {label} must be numeric")
        try:
            value = float(raw)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Scene v12 annotation {label} must be numeric") from error
        return value

    def annotation_color(style: dict[str, Any], key: str, default: str, label: str) -> str:
        raw = style.get(key, default)
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"Scene v12 annotation {label} must be a nonempty CSS color")
        return raw

    # XYAL v2 carries only literal RGBA paint with the annotation identity and
    # text. Rust still owns the anchor, clipping, typography, and paint order.
    attached_labels: list[tuple[int, tuple[int, int, int, int], str]] = []
    straight_arrows: list[
        tuple[int, float, float, float, float, tuple[int, int, int, int], float, float]
    ] = []
    # XYAC v1 is deliberately a compact host framing seam.  Every layout,
    # projection, label placement, connector shape, clipping, and paint-order
    # decision remains in Rust.  One row is little-endian
    # ``dddd4sddB3xI`` (60 fixed bytes) followed by its UTF-8 text:
    # data x/y, pixel dx/dy, literal RGBA, opacity, width, anchor code
    # (start=0/middle=1/end=2), three required zero bytes, and u32 text
    # byte length. Rust derives the callout identity from record order.
    cartesian_callouts: list[
        tuple[
            float,
            float,
            float,
            float,
            tuple[int, int, int, int],
            float,
            float,
            int,
            bytes,
            tuple[int, int, int, int] | None,
        ]
    ] = []
    for annotation_index, annotation in enumerate(annotations):
        kind = annotation.get("kind")
        if kind == "text":
            continue
        if kind == "arrow":
            if annotation.get("text") not in (None, "") or annotation.get("class_name") not in (
                None,
                "",
            ):
                raise UnsupportedSceneV3("Scene arrows do not encode text or class_name")
            style = dict(annotation.get("style") or {})
            bad = sorted(
                key
                for key, value in style.items()
                if key not in {"color", "opacity", "width"} and value is not None
            )
            if bad:
                raise UnsupportedSceneV3(f"Scene arrow style does not encode {bad!r}")
            opacity = annotation_number(style, "opacity", 1.0, "arrow opacity")
            width_value = annotation_number(style, "width", 1.5, "arrow width")
            if (
                not np.isfinite(opacity)
                or not 0 <= opacity <= 1
                or not np.isfinite(width_value)
                or width_value <= 0
            ):
                raise ValueError("Scene arrow opacity must be in [0, 1] and width must be positive")
            straight_arrows.append(
                (
                    annotation_prefix | (5 << 40) | annotation_index,
                    annotation_number(annotation, "x0", None, "arrow x0"),
                    annotation_number(annotation, "y0", None, "arrow y0"),
                    annotation_number(annotation, "x1", None, "arrow x1"),
                    annotation_number(annotation, "y1", None, "arrow y1"),
                    _rgba(annotation_color(style, "color", "#667085", "arrow color"), 1.0),
                    opacity,
                    width_value,
                )
            )
            continue
        if kind == "callout":
            if annotation.get("class_name") not in (None, ""):
                raise UnsupportedSceneV3("Scene callouts do not encode class_name")
            value = annotation.get("text")
            if not isinstance(value, str) or not value or "\0" in value:
                raise UnsupportedSceneV3("Scene callouts require nonempty NUL-free text")
            encoded = value.encode("utf-8")
            if len(encoded) > 4096:
                raise UnsupportedSceneV3("Scene callouts are limited to 4,096 UTF-8 bytes")
            style = dict(annotation.get("style") or {})
            bad = sorted(
                key
                for key, style_value in style.items()
                if key not in {"color", "opacity", "width", "label_background"}
                and style_value is not None
            )
            if bad:
                raise UnsupportedSceneV3(f"Scene callout style does not encode {bad!r}")
            opacity = annotation_number(style, "opacity", 1.0, "callout opacity")
            width_value = annotation_number(style, "width", 1.5, "callout width")
            if (
                not np.isfinite(opacity)
                or not 0 <= opacity <= 1
                or not np.isfinite(width_value)
                or width_value <= 0
            ):
                raise ValueError(
                    "Scene callout opacity must be in [0, 1] and width must be positive"
                )
            anchor = annotation.get("anchor", "start")
            anchor_code = {"start": 0, "middle": 1, "end": 2}.get(anchor)
            if anchor_code is None:
                raise UnsupportedSceneV3("Scene callout anchor must be start, middle, or end")
            x = annotation_number(annotation, "x", None, "callout x")
            y = annotation_number(annotation, "y", None, "callout y")
            dx = annotation_number(annotation, "dx", 36.0, "callout dx")
            dy = annotation_number(annotation, "dy", -30.0, "callout dy")
            if not all(np.isfinite(number) for number in (x, y, dx, dy)):
                raise ValueError("Scene callout coordinates and offsets must be finite")
            label_background = style.get("label_background")
            label_fill = (
                _rgba(
                    annotation_color(style, "label_background", "", "callout label background"), 1.0
                )
                if label_background is not None
                else None
            )
            cartesian_callouts.append(
                (
                    x,
                    y,
                    dx,
                    dy,
                    _rgba(annotation_color(style, "color", "#344054", "callout color"), 1.0),
                    opacity,
                    width_value,
                    anchor_code,
                    encoded,
                    label_fill,
                )
            )
            continue
        if kind not in {"rule", "band", "marker"}:
            raise UnsupportedSceneV3(
                f"Scene v12 annotations support rule, band, and unlabeled marker only; {kind!r} is deferred"
            )
        attached_text = annotation.get("text")
        if attached_text not in (None, "") and (
            not isinstance(attached_text, str) or "\0" in attached_text
        ):
            raise UnsupportedSceneV3("Scene v16 annotation labels require nonempty NUL-free text")
        if annotation.get("class_name") not in (None, ""):
            raise UnsupportedSceneV3("Scene v12 annotations do not encode class_name")
        style = dict(annotation.get("style") or {})
        allowed = {"color", "opacity"}
        if attached_text not in (None, ""):
            allowed |= {"label_color", "label_opacity"}
        if kind == "rule":
            allowed.add("width")
        elif kind == "marker":
            allowed |= {"stroke_color", "stroke_width"}
        unsupported_style = sorted(
            key for key, value in style.items() if key not in allowed and value is not None
        )
        if unsupported_style:
            raise UnsupportedSceneV3(
                f"Scene v12 {kind} annotation style does not encode {unsupported_style!r}"
            )
        opacity = annotation_number(
            style, "opacity", 0.14 if kind == "band" else 1.0, f"{kind} opacity"
        )
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ValueError(f"Scene v12 {kind} annotation opacity must be finite and in [0, 1]")
        color = annotation_color(
            style, "color", "#64748b" if kind == "band" else "#667085", f"{kind} color"
        )
        fill = _rgba(color, opacity) if kind != "rule" else (0, 0, 0, 0)
        stroke_color = annotation_color(style, "stroke_color", color, f"{kind} stroke color")
        stroke = _rgba(stroke_color, opacity)
        width_key = "width" if kind == "rule" else "stroke_width"
        width_value = annotation_number(
            style, width_key, 1.5 if kind != "band" else 0.0, f"{kind} width"
        )
        if not np.isfinite(width_value) or width_value < 0 or (kind == "rule" and width_value == 0):
            raise ValueError(f"Scene v12 {kind} annotation width must be finite and nonnegative")
        styles.append((fill, stroke, width_value))
        style_ref = len(styles) - 1
        tag = (
            4
            if kind == "band" and annotation.get("axis") == "y"
            else {"rule": 1, "band": 2, "marker": 3}[kind]
        )
        stable_id = annotation_prefix | (tag << 40) | annotation_index
        if attached_text not in (None, ""):
            encoded_text = attached_text.encode("utf-8")
            if len(encoded_text) > 4096:
                raise UnsupportedSceneV3(
                    "Scene v16 annotation labels are limited to 4,096 UTF-8 bytes"
                )
            label_opacity = annotation_number(style, "label_opacity", 1.0, f"{kind} label opacity")
            if not np.isfinite(label_opacity) or not 0.0 <= label_opacity <= 1.0:
                raise ValueError(
                    f"Scene v16 {kind} annotation label opacity must be finite and in [0, 1]"
                )
            label_color = annotation_color(style, "label_color", "#667085", f"{kind} label color")
            attached_labels.append((stable_id, _rgba(label_color, label_opacity), attached_text))

        def append_record(
            record_kind: int,
            a: float,
            b: float,
            c: float,
            d: float,
            *,
            size: float = 0.0,
            symbol: int = 0,
            annotation_kind: str = kind,
            annotation_stable_id: int = stable_id,
            annotation_style_ref: int = style_ref,
        ) -> None:
            values = (a, b, c, d, size)
            if not all(np.isfinite(value) for value in values):
                raise ValueError(f"Scene v12 {annotation_kind} annotation geometry must be finite")
            kinds.append(record_kind)
            stable_ids.append(annotation_stable_id)
            style_refs.append(annotation_style_ref)
            diameters.append(size)
            symbols.append(symbol)
            for destination, value in zip(coordinates, (a, b, c, d), strict=True):
                destination.append(float(value))

        if kind == "rule":
            axis_name = annotation.get("axis")
            if axis_name not in {"x", "y"}:
                raise ValueError("Scene v12 rule annotation axis must be 'x' or 'y'")
            value = annotation_number(annotation, "value", None, f"{kind} value")
            if axis_name == "x":
                append_record(1, value, y_domain[0], 0.0, 0.0)
                append_record(1, value, y_domain[1], 0.0, 0.0)
            else:
                append_record(1, x_domain[0], value, 0.0, 0.0)
                append_record(1, x_domain[1], value, 0.0, 0.0)
        elif kind == "band":
            axis_name = annotation.get("axis")
            if axis_name not in {"x", "y"}:
                raise ValueError("Scene v12 band annotation axis must be 'x' or 'y'")
            start = annotation_number(annotation, "start", None, f"{kind} start")
            end = annotation_number(annotation, "end", None, f"{kind} end")
            if axis_name == "x":
                append_record(2, start, y_domain[0], end, y_domain[1])
            else:
                append_record(2, x_domain[0], start, x_domain[1], end)
        else:
            symbol_name = str(annotation.get("symbol", "circle"))
            if symbol_name not in _SYMBOL_CODES:
                raise UnsupportedSceneV3(
                    f"Scene v12 does not support marker symbol {symbol_name!r}"
                )
            size = annotation_number(annotation, "size", 8.0, f"{kind} size")
            if not np.isfinite(size) or size <= 0:
                raise ValueError("Scene v12 marker annotation size must be finite and positive")
            append_record(
                0,
                annotation_number(annotation, "x", None, f"{kind} x"),
                annotation_number(annotation, "y", None, f"{kind} y"),
                0.0,
                0.0,
                size=size,
                symbol=_SYMBOL_CODES[symbol_name],
            )

    w = int(width if width is not None else figure.width)
    h = int(height if height is not None else figure.height)
    fill_rgba = [channel for fill, _, _ in styles for channel in fill]
    stroke_rgba = [channel for _, stroke, _ in styles for channel in stroke]
    stroke_width = [value for _, _, value in styles]
    kind_codes = {"linear": 0, "log": 1, "symlog": 2}

    def axis(axis_id: str, stable_id: int) -> tuple[int, int, float, float, float, bool]:
        scale = figure._axis_scale(axis_id)
        options = figure.axis_options[axis_id]
        return (
            stable_id,
            kind_codes[scale],
            *figure._range(axis_id),
            float(options.get("constant") or 1.0),
            options.get("nonpositive", "clip") == "mask",
        )

    x_axis = axis("x", 1)
    y_axis = axis("y", 2)
    title = str(figure.title or "")
    x_label = str(figure.x_label or figure.axis_options.get("x", {}).get("label") or "")
    y_label = str(figure.y_label or figure.axis_options.get("y", {}).get("label") or "")
    if margins is None:
        authored = None
        if getattr(figure, "padding", None) is not None:
            pad = figure.padding
            if isinstance(pad, (list, tuple)) and len(pad) == 4:
                authored = (float(pad[0]), float(pad[1]), float(pad[2]), float(pad[3]))
        left, right, top, bottom = _native.scene_plot_layout(
            viewport=(w, h),
            x_axis=x_axis[1:],
            y_axis=y_axis[1:],
            title=title,
            x_label=x_label,
            y_label=y_label,
            padding=authored,
            colorbar_side=("bottom" if colorbar_input[8] & 1 else "right")
            if colorbar_input
            else None,
        )
    else:
        left, right, top, bottom = margins
    text_annotations = [
        annotation for annotation in annotations if annotation.get("kind") == "text"
    ]
    if len(cartesian_callouts) > 128:
        raise UnsupportedSceneV3("Scene callouts are limited to 128 entries")
    xyat = bytearray(
        b"XYAT" + (1).to_bytes(4, "little") + len(text_annotations).to_bytes(4, "little")
    )
    for annotation in text_annotations:
        value = annotation.get("text")
        if not isinstance(value, str) or not value or "\0" in value:
            raise UnsupportedSceneV3("Scene v16 text annotations require nonempty NUL-free text")
        encoded = value.encode("utf-8")
        if len(encoded) > 4096:
            raise UnsupportedSceneV3("Scene v16 text annotations are limited to 4,096 UTF-8 bytes")
        x = annotation_number(annotation, "x", None, "text x")
        y = annotation_number(annotation, "y", None, "text y")
        style = dict(annotation.get("style") or {})
        if set(style) - {"color", "opacity"}:
            raise UnsupportedSceneV3("Scene v16 text annotations support only color and opacity")
        rgba = _rgba(
            annotation_color(style, "color", "#667085", "text color"),
            annotation_number(style, "opacity", 1.0, "text opacity"),
        )
        xyat.extend(struct.pack("<dd4sI", x, y, bytes(rgba), len(encoded)))
        xyat.extend(encoded)
    xyal = bytearray(
        b"XYAL" + (2).to_bytes(4, "little") + len(attached_labels).to_bytes(4, "little")
    )
    for stable_id, rgba, value in attached_labels:
        encoded = value.encode("utf-8")
        xyal.extend(struct.pack("<Q4sI", stable_id, bytes(rgba), len(encoded)))
        xyal.extend(encoded)
    xyar = bytearray(
        b"XYAR" + (1).to_bytes(4, "little") + len(straight_arrows).to_bytes(4, "little")
    )
    for stable_id, x0, y0, x1, y1, rgba, opacity, width_value in straight_arrows:
        xyar.extend(
            struct.pack("<Qdddd4sdd", stable_id, x0, y0, x1, y1, bytes(rgba), opacity, width_value)
        )
    xyac_v2 = any(label_fill is not None for *_, label_fill in cartesian_callouts)
    xyac = bytearray(
        b"XYAC"
        + (2 if xyac_v2 else 1).to_bytes(4, "little")
        + len(cartesian_callouts).to_bytes(4, "little")
    )
    for (
        x,
        y,
        dx,
        dy,
        rgba,
        opacity,
        width_value,
        anchor_code,
        encoded,
        label_fill,
    ) in cartesian_callouts:
        xyac.extend(
            struct.pack(
                "<dddd4sddB3xI",
                x,
                y,
                dx,
                dy,
                bytes(rgba),
                opacity,
                width_value,
                anchor_code,
                len(encoded),
            )
        )
        if xyac_v2:
            xyac.extend(bytes(label_fill or (0, 0, 0, 0)))
        xyac.extend(encoded)
    framed_annotations = bytearray(
        b"XYAD"
        + (2).to_bytes(4, "little")
        + len(xyat).to_bytes(4, "little")
        + len(xyal).to_bytes(4, "little")
        + len(xyar).to_bytes(4, "little")
        + len(xyac).to_bytes(4, "little")
    )
    framed_annotations.extend(xyat)
    framed_annotations.extend(xyal)
    framed_annotations.extend(xyar)
    framed_annotations.extend(xyac)
    return _native.scene_batch_encode(
        viewport=(w, h),
        margins=(left, right, top, bottom),
        x_axis=x_axis,
        y_axis=y_axis,
        kinds=kinds,
        stable_ids=stable_ids,
        style_refs=style_refs,
        fill_rgba=fill_rgba,
        stroke_rgba=stroke_rgba,
        stroke_width=stroke_width,
        diameter=diameters,
        symbols=symbols,
        x0=coordinates[0],
        y0=coordinates[1],
        x1=coordinates[2],
        y1=coordinates[3],
        title=title,
        x_label=x_label,
        y_label=y_label,
        chrome_style=_scene_chrome_style(figure),
        x_major_ticks=figure.axis_options["x"].get("tick_values"),
        x_tick_labels=figure.axis_options["x"].get("tick_labels"),
        x_minor_ticks=figure.axis_options["x"].get("minor_tick_values") or (),
        y_major_ticks=figure.axis_options["y"].get("tick_values"),
        y_tick_labels=figure.axis_options["y"].get("tick_labels"),
        y_minor_ticks=figure.axis_options["y"].get("minor_tick_values") or (),
        legend_input=_legend_input(figure, legend_entries, styles),
        colorbar_input=colorbar_input,
        authored_text_annotations=bytes(framed_annotations)
        if text_annotations or attached_labels or straight_arrows or cartesian_callouts
        else b"",
    )


def figure_svg(figure: Any, **options: Any) -> str:
    return _native.scene_svg(figure_scene(figure, **options))


def figure_raster_commands(figure: Any, *, scale: float = 1.0, **options: Any) -> bytes:
    return _native.scene_raster_commands(figure_scene(figure, **options), scale)


def scene_export_support_reason(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
) -> str | None:
    """Return why a figure cannot compile to the canonical Rust Scene, or ``None``.

    This is the single support predicate the #117 public static-export router
    consults before selecting the Rust Scene path over the compatibility
    ``_svg`` / ``_raster`` renderers. Unlike :func:`try_public_svg`, which only
    signals success by returning output, this reports the stable
    ``XYG_SCENE_UNSUPPORTED_*`` diagnostic (or the compiler's own bounded
    message) so callers can log or surface an actionable reason for the fallback.

    This is deliberately narrower than :func:`figure_scene`: the explicit
    Scene API can exercise a migrating record before the public compatibility
    renderer's complete output contract is modeled. Only the proven
    constant-style circle-scatter subset routes automatically. Input errors
    (for example a non-finite opacity) are not a routing question and
    propagate unchanged.
    """
    # The compatibility exporter resolves fluid authoring dimensions at its
    # document boundary.  Scene records require concrete viewport dimensions;
    # keep fluid figures on that documented path unless a static override is
    # supplied by the caller.
    if (width is None and not isinstance(figure.width, int)) or (
        height is None and not isinstance(figure.height, int)
    ):
        return "XYG_SCENE_UNSUPPORTED_FLUID_VIEWPORT"
    # ``figure_scene`` deliberately has a wider explicit-API contract than the
    # public exporter: vertical migration lets its Rust consumers exercise
    # newly framed records before every legacy static-output detail is proven.
    # Public routing is narrower.  Keep any legacy styling, layout, annotation,
    # legend, or screen-bounded LOD behavior on the compatibility renderer
    # until it is modeled end-to-end, rather than accepting it merely because
    # the Scene encoder can serialize part of it.
    if getattr(figure, "style", None) or getattr(figure, "chrome_styles", None):
        return "XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE"
    if getattr(figure, "title", None) or getattr(figure, "title_options", None):
        return "XYG_SCENE_UNSUPPORTED_PUBLIC_TEXT"
    if getattr(figure, "annotations", None):
        return "XYG_SCENE_UNSUPPORTED_PUBLIC_ANNOTATION"
    if getattr(figure, "legend_options", None) or any(
        getattr(trace, "name", None) for trace in figure.traces
    ):
        return "XYG_SCENE_UNSUPPORTED_PUBLIC_LEGEND"
    for axis_id, options in figure.axis_options.items():
        axis_style = options.get("style") or {}
        # The public ``ticks=`` / ``text=`` switches lower to these exact
        # compatibility-renderer style records.  Scene has not yet carried
        # their independently visible semantics (ticks off must retain tick
        # labels; text off must retain tick marks), so keep them out of the
        # public route before compilation rather than accepting a partial
        # chrome record merely because the Scene encoder can serialize it.
        if (axis_style.get("tick_length") == 0 and axis_style.get("tick_width") == 0) or (
            axis_style.get("tick_label_color") == "#00000000"
            and axis_style.get("label_color") == "#00000000"
        ):
            return "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS_VISIBILITY"
        if options.get("label") is not None or options.get("side") != (
            "bottom" if axis_id == "x" else "left"
        ):
            return "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS"
        if any(
            options.get(key) not in (None, False, [], {})
            for key in ("style", "minor_style", "tick_values", "tick_labels", "minor_tick_values")
        ) or any(options.get(key) for key in ("tick_sides", "tick_label_sides")):
            return "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS"
    # Until the compatibility raster's line/rect sampling, palette choices,
    # and SVG spelling are represented in the whole-scene consumers, public
    # auto-routing is deliberately limited to constant-style circle scatter.
    # The broader mark set remains available through explicit ``to_scene``.
    public_kinds = {"scatter"}
    public_style_keys = {
        "scatter": {"color", "opacity", "symbol", "size"},
        "line": {"color", "opacity", "width", "step"},
        "bar": {"color", "opacity", "role", "orientation"},
        "column": {"color", "opacity", "role", "orientation"},
        "histogram": {"color", "opacity", "role", "orientation"},
    }
    for trace in figure.traces:
        opacity = float((getattr(trace, "style", None) or {}).get("opacity", 1.0))
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ValueError("trace opacity must be finite and in [0, 1]")
        x_column = getattr(trace, "x", None)
        if x_column is not None and len(x_column.values) > 10_000:
            return "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD"
        if trace.kind not in public_kinds:
            return "XYG_SCENE_UNSUPPORTED_PUBLIC_MARK"
        if trace.kind == "scatter" and (trace.style or {}).get("symbol", "circle") != "circle":
            # The long-standing public diamond/other-symbol route uses the
            # compatibility scatter SVG wrapper, whose exact SVG spelling is
            # part of the current export contract.
            return "XYG_SCENE_UNSUPPORTED_PUBLIC_SYMBOL"
        if any(
            value is not None and key not in public_style_keys[trace.kind]
            for key, value in (getattr(trace, "style", None) or {}).items()
        ):
            return "XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE"
    try:
        figure_scene(figure, width=width, height=height)
    except UnsupportedSceneV3 as unsupported:
        return str(unsupported)
    except ValueError as exc:
        # A valid public export can request a viewport smaller than the
        # bounded Scene chrome can contain.  Treat that as an explicit routing
        # exception before a Scene batch exists; other invalid inputs remain
        # failures and must never select compatibility rendering.
        if str(exc) == "invalid canonical scene plot layout":
            return "XYG_SCENE_UNSUPPORTED_VIEWPORT"
        raise
    return None


def try_public_svg(figure: Any, **options: Any) -> str | None:
    """Return Scene SVG when the figure is in the migrated subset, else ``None``.

    Public exporters keep the compatibility ``_svg`` / ``_raster`` paths until
    Scene chrome and CSS-spelling parity land; callers may opt into these
    helpers for explicit Scene selection.
    """
    try:
        return figure_svg(figure, **options)
    except UnsupportedSceneV3:
        return None


def try_public_png(
    figure: Any,
    *,
    scale: float = 1.0,
    width: int | None = None,
    height: int | None = None,
    **options: Any,
) -> bytes | None:
    """Return Scene-rasterized PNG bytes when the figure is Scene-capable."""
    from . import kernels

    try:
        scene = figure_scene(figure, width=width, height=height, **options)
        commands = _native.scene_raster_commands(scene, scale)
    except UnsupportedSceneV3:
        return None
    w = int(width if width is not None else figure.width)
    h = int(height if height is not None else figure.height)
    pixel_w = max(1, int(round(w * float(scale))))
    pixel_h = max(1, int(round(h * float(scale))))
    return kernels.rasterize_png(commands, pixel_w, pixel_h)


def try_public_pdf(figure: Any, **options: Any) -> bytes | None:
    """Return Scene SVG→PDF for a Scene-capable figure.

    This is deliberately not a catch-all fallback boundary: a malformed Scene
    or a failure in the Rust/PDF consumers is an export failure, not evidence
    that the compatibility renderer should be selected.
    """
    from . import _pdf

    svg = try_public_svg(figure, **options)
    if svg is None:
        return None
    return _pdf.svg_to_pdf(svg)
