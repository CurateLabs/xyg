"""Thin figure-to-Scene v4 compiler for the migrated core-mark subset.

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
        raise UnsupportedSceneV3("Scene v4 does not yet support data-driven paint channels")
    return channel.constant


def figure_scene(
    figure: Any,
    *,
    width: int | None = None,
    height: int | None = None,
    margins: tuple[float, float, float, float] = (50.0, 20.0, 20.0, 40.0),
) -> bytes:
    """Compile representative scatter/line/bar plus x/y axes to Scene v4."""
    if figure.coords != "cartesian":
        raise UnsupportedSceneV3("Scene v4 figure compilation currently supports cartesian only")
    if set(figure.axis_options) != {"x", "y"}:
        raise UnsupportedSceneV3("Scene v4 figure compilation currently supports exactly x/y axes")
    for axis_id, options in figure.axis_options.items():
        expected_side = "bottom" if axis_id == "x" else "left"
        if options.get("side", expected_side) != expected_side:
            raise UnsupportedSceneV3("Scene v4 does not yet encode customized axis sides")
        supported_axis_keys = {"type", "constant", "domain", "nonpositive", "label", "side"}
        if any(
            key not in supported_axis_keys and value not in (None, False, [], {})
            for key, value in options.items()
        ):
            raise UnsupportedSceneV3("Scene v4 does not yet encode tick, grid, or axis styling")
    if figure.title or figure.x_label or figure.y_label or figure.annotations:
        raise UnsupportedSceneV3("Scene v4 does not yet encode titles, labels, or annotations")
    if figure.colorbar_options or figure.extra_legends:
        raise UnsupportedSceneV3("Scene v4 does not yet encode colorbars or extra legends")
    supported = {"scatter", "line", "bar"}
    unsupported = next((trace.kind for trace in figure.traces if trace.kind not in supported), None)
    if unsupported is not None:
        raise UnsupportedSceneV3(f"Scene v4 figure compilation does not yet support {unsupported}")

    kinds: list[int] = []
    stable_ids: list[int] = []
    style_refs: list[int] = []
    styles: list[tuple[tuple[int, ...], tuple[int, ...], float]] = []
    diameters: list[float] = []
    symbols: list[int] = []
    coordinates: list[list[float]] = [[], [], [], []]
    for trace in figure.traces:
        if trace.x_axis != "x" or trace.y_axis != "y":
            raise UnsupportedSceneV3("Scene v4 currently supports only the primary x/y axes")
        if trace.name and figure.show_legend:
            raise UnsupportedSceneV3("Scene v4 does not yet encode legends")
        if trace.hidden or trace.has_per_item_channels():
            raise UnsupportedSceneV3("Scene v4 does not yet encode hidden or per-item styled marks")
        style = trace.style
        if any(key in style for key in ("dash", "curve", "linecap", "marker_path", "marker_glyph")):
            raise UnsupportedSceneV3(
                "Scene v4 does not yet encode dashed, curved, or authored markers"
            )
        opacity = float(style.get("opacity", 1.0))
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            raise ValueError("trace opacity must be finite and in [0, 1]")
        color = _constant_color(trace, "#3987e5")
        fill = _rgba(str(style.get("fill", color)), opacity)
        stroke_default = color if trace.kind == "line" else "transparent"
        stroke = _rgba(str(style.get("stroke", stroke_default)), opacity)
        width_value = style.get(
            "stroke_width", style.get("width", 1.5 if trace.kind == "line" else 0.0)
        )
        stroke_width = float(width_value)
        styles.append((fill, stroke, stroke_width))
        style_ref = len(styles) - 1
        if trace.kind == "bar":
            if any(value is None for value in (trace.x0, trace.y0, trace.x1, trace.y1)):
                raise ValueError("bar Scene v4 compilation requires four rectangle columns")
            arrays = [trace.x0.values, trace.y0.values, trace.x1.values, trace.y1.values]
            count = len(arrays[0])
        else:
            arrays = [
                trace.x.values,
                trace.y.values,
                np.zeros(len(trace.x)),
                np.zeros(len(trace.x)),
            ]
            count = len(trace.x)
        if any(
            not np.isfinite(source).all() for source in arrays[: 4 if trace.kind == "bar" else 2]
        ):
            raise UnsupportedSceneV3(
                "Scene v4 does not yet encode missing-data breaks or nonfinite coordinates"
            )
        symbol_name = str(style.get("symbol", "circle"))
        if symbol_name not in _SYMBOL_CODES:
            raise UnsupportedSceneV3(f"Scene v4 does not support scatter symbol {symbol_name!r}")
        diameter = (
            float(trace.size_ch.constant)
            if trace.kind == "scatter" and trace.size_ch is not None
            else float(style.get("size", 4.0))
        )
        for index in range(count):
            kinds.append({"scatter": 0, "line": 1, "bar": 2}[trace.kind])
            stable_ids.append(int(trace.id))
            style_refs.append(style_ref)
            diameters.append(diameter if trace.kind == "scatter" else 0.0)
            symbols.append(_SYMBOL_CODES[symbol_name] if trace.kind == "scatter" else 0)
            for destination, source in zip(coordinates, arrays, strict=True):
                destination.append(float(source[index]))

    w = int(width if width is not None else figure.width)
    h = int(height if height is not None else figure.height)
    left, right, top, bottom = margins
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

    return _native.scene_batch_encode(
        viewport=(w, h),
        margins=(left, right, top, bottom),
        x_axis=axis("x", 1),
        y_axis=axis("y", 2),
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
    )


def figure_svg(figure: Any, **options: Any) -> str:
    return _native.scene_svg(figure_scene(figure, **options))


def figure_raster_commands(figure: Any, *, scale: float = 1.0, **options: Any) -> bytes:
    return _native.scene_raster_commands(figure_scene(figure, **options), scale)
