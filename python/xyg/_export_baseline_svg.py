"""Shared static-export SVG axis frames and tick marks."""

from __future__ import annotations

from typing import Any, Optional

from ._export_polar_svg import _polar_frame_path, _polar_linear_frame_path
from ._export_svg_util import _num, escape
from ._export_ticks import _axis_tick_label_strategy, _axis_tick_sides
from ._layout import _PolarProjection, _Scale
from ._paint import _css


def _svg_baselines(
    spec: dict[str, Any],
    plot: dict[str, float],
    xa: dict[str, Any],
    ya: dict[str, Any],
    sx: _Scale,
    sy: _Scale,
    extra_x_axes: list[tuple[str, dict[str, Any], _Scale]],
    extra_y_axes: list[tuple[str, dict[str, Any], _Scale]],
    polar: Optional[_PolarProjection],
    *,
    xt: list[float],
    yt: list[float],
    xmt: list[float],
    ymt: list[float],
    extra_x_ticks: dict[str, tuple[list[float], list[float], float]],
    extra_y_ticks: dict[str, tuple[list[float], list[float], float]],
    hide_x: bool,
    hide_y: bool,
    default_axis: str,
    xstyle: dict[str, Any],
    ystyle: dict[str, Any],
    xmstyle: dict[str, Any],
    ymstyle: dict[str, Any],
) -> str:
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

    return baselines
