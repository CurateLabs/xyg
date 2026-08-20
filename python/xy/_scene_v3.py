"""Thin figure-to-Scene v5 compiler for the migrated core-mark subset.

Rust owns mapping, clipping, record semantics, SVG construction, and raster
display-list construction. This module only projects already-validated Figure
objects into the typed ABI and rejects features whose canonical Scene record
does not exist yet.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from . import _native
from .marks import _SYMBOL_CODES

# Host mark kinds that lower to Scene Rect (kind 2). Geometry is already
# x0/y0/x1/y1 columns on the Trace; Scene does not recompute bar stacking.
_RECT_KINDS = frozenset({"bar", "column", "histogram", "violin"})
# Endpoint pairs that lower to disconnected Scene Polyline runs (kind 1).
_SEGMENT_KINDS = frozenset({"segments", "errorbar", "stem"})
_POINT_KINDS = frozenset({"scatter", "line"})
_SUPPORTED_KINDS = _POINT_KINDS | _RECT_KINDS | _SEGMENT_KINDS
_STROKE_KINDS = frozenset({"line"}) | _SEGMENT_KINDS
_KIND_CODES = {
    "scatter": 0,
    "line": 1,
    "segments": 1,
    "errorbar": 1,
    "stem": 1,
    "bar": 2,
    "column": 2,
    "histogram": 2,
    "violin": 2,
}


class UnsupportedSceneV3(ValueError):
    """The figure uses a feature outside the currently migrated Scene subset."""


def _rgba(css: str, opacity: float) -> tuple[int, int, int, int]:
    from ._raster import _parse_color

    return _parse_color(css, opacity)


def _constant_color(trace: Any, fallback: str) -> str:
    channel = trace.color_ch
    if channel is None:
        return str(trace.style.get("color", fallback))
    if channel.mode != "constant" or channel.constant is None:
        raise UnsupportedSceneV3("Scene v5 does not yet support data-driven paint channels")
    return channel.constant


def _reject_rect_extras(style: dict[str, Any], kind: str) -> None:
    fill = style.get("fill")
    if isinstance(fill, dict):
        raise UnsupportedSceneV3(f"Scene v5 does not yet encode {kind} gradient fills")
    radius = style.get("corner_radius", 0.0)
    if isinstance(radius, (list, tuple)):
        if any(float(value) != 0.0 for value in radius):
            raise UnsupportedSceneV3(f"Scene v5 does not yet encode {kind} corner_radius")
    elif float(radius) != 0.0:
        raise UnsupportedSceneV3(f"Scene v5 does not yet encode {kind} corner_radius")
    if float(style.get("wedge_gap", 0.0) or 0.0) != 0.0:
        raise UnsupportedSceneV3(f"Scene v5 does not yet encode {kind} wedge_gap")


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
        raise ValueError(f"{trace.kind} Scene v5 compilation requires four rectangle columns")
    arrays = [trace.x0.values, trace.y0.values, trace.x1.values, trace.y1.values]
    lengths = {len(column) for column in arrays}
    if len(lengths) != 1:
        raise UnsupportedSceneV3(f"Scene v5 {trace.kind} rectangle columns must have equal length")
    return arrays


def _segment_columns(trace: Any) -> list[np.ndarray]:
    if any(value is None for value in (trace.x0, trace.y0, trace.x1, trace.y1)):
        raise ValueError(f"{trace.kind} Scene v5 compilation requires four endpoint columns")
    arrays = [trace.x0.values, trace.y0.values, trace.x1.values, trace.y1.values]
    lengths = {len(column) for column in arrays}
    if len(lengths) != 1:
        raise UnsupportedSceneV3(f"Scene v5 {trace.kind} endpoint columns must have equal length")
    return arrays


def figure_scene(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
    margins: tuple[float, float, float, float] | None = None,
) -> bytes:
    """Compile migrated cartesian marks plus x/y axes to Scene v5."""
    if figure.coords != "cartesian":
        raise UnsupportedSceneV3("Scene v5 figure compilation currently supports cartesian only")
    if set(figure.axis_options) != {"x", "y"}:
        raise UnsupportedSceneV3("Scene v5 figure compilation currently supports exactly x/y axes")
    for axis_id, options in figure.axis_options.items():
        expected_side = "bottom" if axis_id == "x" else "left"
        if options.get("side", expected_side) != expected_side:
            raise UnsupportedSceneV3("Scene v5 does not yet encode customized axis sides")
        supported_axis_keys = {"type", "constant", "domain", "nonpositive", "label", "side"}
        if any(
            key not in supported_axis_keys and value not in (None, False, [], {})
            for key, value in options.items()
        ):
            raise UnsupportedSceneV3("Scene v5 does not yet encode tick, grid, or axis styling")
    if figure.annotations:
        raise UnsupportedSceneV3("Scene v5 does not yet encode annotations")
    if figure.colorbar_options or figure.extra_legends:
        raise UnsupportedSceneV3("Scene v5 does not yet encode colorbars or extra legends")
    unsupported = next(
        (trace.kind for trace in figure.traces if trace.kind not in _SUPPORTED_KINDS), None
    )
    if unsupported is not None:
        raise UnsupportedSceneV3(f"Scene v5 figure compilation does not yet support {unsupported}")

    kinds: list[int] = []
    stable_ids: list[int] = []
    style_refs: list[int] = []
    styles: list[tuple[tuple[int, ...], tuple[int, ...], float]] = []
    diameters: list[float] = []
    symbols: list[int] = []
    coordinates: list[list[float]] = [[], [], [], []]
    for trace in figure.traces:
        if trace.x_axis != "x" or trace.y_axis != "y":
            raise UnsupportedSceneV3("Scene v5 currently supports only the primary x/y axes")
        if trace.name and figure.show_legend:
            raise UnsupportedSceneV3("Scene v5 does not yet encode legends")
        if trace.hidden or trace.has_per_item_channels():
            raise UnsupportedSceneV3("Scene v5 does not yet encode hidden or per-item styled marks")
        if trace.kind == "scatter" and trace.use_density():
            raise UnsupportedSceneV3("Scene v5 does not yet encode density-tier scatter")
        style = trace.style
        if any(key in style for key in ("dash", "curve", "linecap", "marker_path", "marker_glyph")):
            raise UnsupportedSceneV3(
                "Scene v5 does not yet encode dashed, curved, or authored markers"
            )
        if trace.kind in _RECT_KINDS:
            _reject_rect_extras(style, trace.kind)
        opacity = float(style.get("opacity", 1.0))
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ValueError("trace opacity must be finite and in [0, 1]")
        color = _constant_color(trace, "#3987e5")
        fill_default = "transparent" if trace.kind in _SEGMENT_KINDS else color
        fill_value = style.get("fill", fill_default)
        if not isinstance(fill_value, str):
            raise UnsupportedSceneV3(f"Scene v5 does not yet encode {trace.kind} non-CSS fills")
        fill = _rgba(fill_value, opacity)
        stroke_default = color if trace.kind in _STROKE_KINDS else "transparent"
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
            raise UnsupportedSceneV3(f"Scene v5 does not support scatter symbol {symbol_name!r}")
        diameter = (
            float(trace.size_ch.constant)
            if trace.kind == "scatter" and trace.size_ch is not None
            else float(style.get("size", 4.0))
        )
        kind_code = _KIND_CODES[trace.kind]

        if trace.kind in _RECT_KINDS:
            arrays = _rect_columns(trace)
            if any(not np.isfinite(source).all() for source in arrays):
                raise UnsupportedSceneV3(
                    "Scene v5 does not yet encode missing-data breaks or nonfinite coordinates"
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
                    "Scene v5 does not yet encode missing-data breaks or nonfinite coordinates"
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
                raise UnsupportedSceneV3("Scene v5 step expansion applies only to line traces")
            if where not in {"pre", "post", "mid"}:
                raise UnsupportedSceneV3(f"Scene v5 does not support step mode {where!r}")
            xv, yv = _step_arrays(xv, yv, where)
        if not np.isfinite(xv).all() or not np.isfinite(yv).all():
            raise UnsupportedSceneV3(
                "Scene v5 does not yet encode missing-data breaks or nonfinite coordinates"
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
