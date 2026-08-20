"""Thin figure-to-Scene v7 compiler for the migrated core-mark subset.

Rust owns mapping, clipping, record semantics, SVG construction, and raster
display-list construction. This module only projects already-validated Figure
objects into the typed ABI and rejects features whose canonical Scene record
does not exist yet.
"""

from __future__ import annotations

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
        raise UnsupportedSceneV3("Scene v7 does not yet encode two-ended ribbon gradients")
    if channel is None:
        return str(trace.style.get("color", fallback))
    if channel.mode != "constant" or channel.constant is None:
        raise UnsupportedSceneV3("Scene v7 does not yet support data-driven paint channels")
    return channel.constant


def _reject_rect_extras(style: dict[str, Any], kind: str) -> None:
    fill = style.get("fill")
    if isinstance(fill, dict):
        raise UnsupportedSceneV3(f"Scene v7 does not yet encode {kind} gradient fills")
    radius = style.get("corner_radius", 0.0)
    if isinstance(radius, (list, tuple)):
        if any(float(value) != 0.0 for value in radius):
            raise UnsupportedSceneV3(f"Scene v7 does not yet encode {kind} corner_radius")
    elif float(radius) != 0.0:
        raise UnsupportedSceneV3(f"Scene v7 does not yet encode {kind} corner_radius")
    if float(style.get("wedge_gap", 0.0) or 0.0) != 0.0:
        raise UnsupportedSceneV3(f"Scene v7 does not yet encode {kind} wedge_gap")


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
        raise ValueError(f"{trace.kind} Scene v7 compilation requires four rectangle columns")
    arrays = [trace.x0.values, trace.y0.values, trace.x1.values, trace.y1.values]
    lengths = {len(column) for column in arrays}
    if len(lengths) != 1:
        raise UnsupportedSceneV3(f"Scene v7 {trace.kind} rectangle columns must have equal length")
    return arrays


def _segment_columns(trace: Any) -> list[np.ndarray]:
    if any(value is None for value in (trace.x0, trace.y0, trace.x1, trace.y1)):
        raise ValueError(f"{trace.kind} Scene v7 compilation requires four endpoint columns")
    arrays = [trace.x0.values, trace.y0.values, trace.x1.values, trace.y1.values]
    lengths = {len(column) for column in arrays}
    if len(lengths) != 1:
        raise UnsupportedSceneV3(f"Scene v7 {trace.kind} endpoint columns must have equal length")
    return arrays


def _band_columns(trace: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if trace.x is None or trace.y is None or trace.base is None:
        raise ValueError(f"{trace.kind} Scene v7 compilation requires x, y, and base columns")
    xv = np.asarray(trace.x.values, dtype=np.float64)
    yv = np.asarray(trace.y.values, dtype=np.float64)
    base = np.asarray(trace.base.values, dtype=np.float64)
    if not (len(xv) == len(yv) == len(base)):
        raise UnsupportedSceneV3(f"Scene v7 {trace.kind} band columns must have equal length")
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
    """Compile migrated cartesian marks plus x/y axes to Scene v7."""
    if figure.coords != "cartesian":
        raise UnsupportedSceneV3("Scene v7 figure compilation currently supports cartesian only")
    if set(figure.axis_options) != {"x", "y"}:
        raise UnsupportedSceneV3("Scene v7 figure compilation currently supports exactly x/y axes")
    figure_style = getattr(figure, "style", None) or {}
    if isinstance(figure_style, dict):
        background = figure_style.get("background")
        if background not in (None, "", "transparent", "none"):
            raise UnsupportedSceneV3("Scene v7 does not yet encode figure backgrounds")
        plot_background = figure_style.get("--chart-bg")
        if plot_background not in (None, "", "transparent", "none", "#ffffff", "#fff", "white"):
            raise UnsupportedSceneV3("Scene v7 does not yet encode plot backgrounds")
    for axis_id, options in figure.axis_options.items():
        expected_side = "bottom" if axis_id == "x" else "left"
        if options.get("side", expected_side) != expected_side:
            raise UnsupportedSceneV3("Scene v7 does not yet encode customized axis sides")
        supported_axis_keys = {"type", "constant", "domain", "nonpositive", "label", "side"}
        if any(
            key not in supported_axis_keys and value not in (None, False, [], {})
            for key, value in options.items()
        ):
            raise UnsupportedSceneV3("Scene v7 does not yet encode tick, grid, or axis styling")
    annotations = list(getattr(figure, "annotations", None) or [])
    for annotation in annotations:
        kind = annotation.get("kind")
        if kind not in {"rule", "band"}:
            raise UnsupportedSceneV3("Scene v7 does not yet encode annotations")
        if annotation.get("text"):
            raise UnsupportedSceneV3("Scene v7 does not yet encode annotation labels")
    if figure.colorbar_options or figure.extra_legends:
        raise UnsupportedSceneV3("Scene v7 does not yet encode colorbars or extra legends")
    unsupported = next(
        (trace.kind for trace in figure.traces if trace.kind not in _SUPPORTED_KINDS), None
    )
    if unsupported is not None:
        raise UnsupportedSceneV3(f"Scene v7 figure compilation does not yet support {unsupported}")

    kinds: list[int] = []
    stable_ids: list[int] = []
    style_refs: list[int] = []
    styles: list[tuple[tuple[int, ...], tuple[int, ...], float]] = []
    diameters: list[float] = []
    symbols: list[int] = []
    coordinates: list[list[float]] = [[], [], [], []]
    for trace in figure.traces:
        if trace.x_axis != "x" or trace.y_axis != "y":
            raise UnsupportedSceneV3("Scene v7 currently supports only the primary x/y axes")
        if trace.name and figure.show_legend:
            raise UnsupportedSceneV3("Scene v7 does not yet encode legends")
        if trace.hidden or trace.has_per_item_channels():
            raise UnsupportedSceneV3("Scene v7 does not yet encode hidden or per-item styled marks")
        if trace.kind == "scatter" and trace.use_density():
            raise UnsupportedSceneV3("Scene v7 does not yet encode density-tier scatter")
        style = trace.style
        if any(key in style for key in ("dash", "curve", "linecap", "marker_path", "marker_glyph")):
            raise UnsupportedSceneV3(
                "Scene v7 does not yet encode dashed, curved, or authored markers"
            )
        if trace.kind in _RECT_KINDS:
            _reject_rect_extras(style, trace.kind)
        if trace.kind in _POLYFILL_KINDS and style.get("joined_fill"):
            raise UnsupportedSceneV3("Scene v7 does not yet encode joined triangle-mesh fills")
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
            raise UnsupportedSceneV3(f"Scene v7 does not yet encode {trace.kind} non-CSS fills")
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
            raise UnsupportedSceneV3(f"Scene v7 does not support scatter symbol {symbol_name!r}")
        diameter = (
            float(trace.size_ch.constant)
            if trace.kind == "scatter" and trace.size_ch is not None
            else float(style.get("size", 4.0))
        )
        kind_code = _KIND_CODES[trace.kind]

        if trace.kind in _RIBBON_KINDS:
            if any(
                value is None
                for value in (trace.x0, trace.x1, trace.y0, trace.y1, trace.x, trace.y)
            ):
                raise ValueError("ribbon Scene v7 compilation requires six geometry columns")
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
                raise UnsupportedSceneV3("Scene v7 ribbon columns must have equal length")
            arrays = (x0s, x1s, source_lo, source_hi, target_lo, target_hi)
            if any(not np.isfinite(column).all() for column in arrays):
                raise UnsupportedSceneV3(
                    "Scene v7 does not yet encode missing-data breaks or nonfinite coordinates"
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
                raise ValueError("triangle_mesh Scene v7 compilation requires six vertex columns")
            x0s = np.asarray(trace.x0.values, dtype=np.float64)
            y0s = np.asarray(trace.y0.values, dtype=np.float64)
            x1s = np.asarray(trace.x1.values, dtype=np.float64)
            y1s = np.asarray(trace.y1.values, dtype=np.float64)
            x2s = np.asarray(trace.x.values, dtype=np.float64)
            y2s = np.asarray(trace.y.values, dtype=np.float64)
            if not (len(x0s) == len(y0s) == len(x1s) == len(y1s) == len(x2s) == len(y2s)):
                raise UnsupportedSceneV3("Scene v7 triangle_mesh columns must have equal length")
            arrays = (x0s, y0s, x1s, y1s, x2s, y2s)
            if any(not np.isfinite(column).all() for column in arrays):
                raise UnsupportedSceneV3(
                    "Scene v7 does not yet encode missing-data breaks or nonfinite coordinates"
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
                    "Scene v7 does not yet encode missing-data breaks or nonfinite coordinates"
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
                    "Scene v7 does not yet encode missing-data breaks or nonfinite coordinates"
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
                    "Scene v7 does not yet encode missing-data breaks or nonfinite coordinates"
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
                raise UnsupportedSceneV3("Scene v7 step expansion applies only to line traces")
            if where not in {"pre", "post", "mid"}:
                raise UnsupportedSceneV3(f"Scene v7 does not support step mode {where!r}")
            xv, yv = _step_arrays(xv, yv, where)
        if not np.isfinite(xv).all() or not np.isfinite(yv).all():
            raise UnsupportedSceneV3(
                "Scene v7 does not yet encode missing-data breaks or nonfinite coordinates"
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

    x_lo, x_hi = figure._range("x")
    y_lo, y_hi = figure._range("y")
    for annotation_index, annotation in enumerate(annotations):
        axis = annotation.get("axis")
        style = dict(annotation.get("style") or {})
        if any(key in style for key in ("dash", "curve", "linecap")):
            raise UnsupportedSceneV3(
                "Scene v7 does not yet encode dashed or curved annotation strokes"
            )
        opacity = float(style.get("opacity", 1.0))
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ValueError("annotation opacity must be finite and in [0, 1]")
        color = style.get("color") or "#667085"
        if not isinstance(color, str):
            raise UnsupportedSceneV3("Scene v7 annotation color must be a constant CSS color")
        stable_base = (int(annotation_index) + 1) << 40
        if annotation.get("kind") == "rule":
            value = float(annotation["value"])
            if not np.isfinite(value):
                raise UnsupportedSceneV3(
                    "Scene v7 does not yet encode missing-data breaks or nonfinite coordinates"
                )
            stroke_width = float(style.get("width", 1.5))
            if not np.isfinite(stroke_width) or stroke_width < 0.0:
                raise ValueError("annotation width must be finite and non-negative")
            styles.append((_rgba("transparent", 1.0), _rgba(color, opacity), stroke_width))
            style_ref = len(styles) - 1
            if axis == "x":
                points = ((value, y_lo), (value, y_hi))
            elif axis == "y":
                points = ((x_lo, value), (x_hi, value))
            else:
                raise UnsupportedSceneV3("Scene v7 rule annotations require axis 'x' or 'y'")
            for x_value, y_value in points:
                kinds.append(1)
                stable_ids.append(stable_base)
                style_refs.append(style_ref)
                diameters.append(0.0)
                symbols.append(0)
                coordinates[0].append(float(x_value))
                coordinates[1].append(float(y_value))
                coordinates[2].append(0.0)
                coordinates[3].append(0.0)
            continue
        start = float(annotation["start"])
        end = float(annotation["end"])
        if not np.isfinite(start) or not np.isfinite(end):
            raise UnsupportedSceneV3(
                "Scene v7 does not yet encode missing-data breaks or nonfinite coordinates"
            )
        styles.append((_rgba(color, opacity), _rgba("transparent", 1.0), 0.0))
        style_ref = len(styles) - 1
        if axis == "x":
            ax0, ax1, ay0, ay1 = start, end, y_lo, y_hi
        elif axis == "y":
            ax0, ax1, ay0, ay1 = x_lo, x_hi, start, end
        else:
            raise UnsupportedSceneV3("Scene v7 band annotations require axis 'x' or 'y'")
        kinds.append(2)
        stable_ids.append(stable_base)
        style_refs.append(style_ref)
        diameters.append(0.0)
        symbols.append(0)
        coordinates[0].append(float(ax0))
        coordinates[1].append(float(ay0))
        coordinates[2].append(float(ax1))
        coordinates[3].append(float(ay1))

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
        )
    else:
        left, right, top, bottom = margins
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
    )


def figure_svg(figure: Any, **options: Any) -> str:
    return _native.scene_svg(figure_scene(figure, **options))


def figure_raster_commands(figure: Any, *, scale: float = 1.0, **options: Any) -> bytes:
    return _native.scene_raster_commands(figure_scene(figure, **options), scale)


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
    except (UnsupportedSceneV3, ValueError):
        return None
    w = int(width if width is not None else figure.width)
    h = int(height if height is not None else figure.height)
    pixel_w = max(1, int(round(w * float(scale))))
    pixel_h = max(1, int(round(h * float(scale))))
    return kernels.rasterize_png(commands, pixel_w, pixel_h)


def try_public_pdf(figure: Any, **options: Any) -> bytes | None:
    """Return Scene SVG→PDF when both Scene compilation and the PDF subset accept."""
    from . import _pdf

    svg = try_public_svg(figure, **options)
    if svg is None:
        return None
    try:
        return _pdf.svg_to_pdf(svg)
    except ValueError:
        # Scene SVG may use attributes outside the closed ``_pdf`` subset; fall back.
        return None
