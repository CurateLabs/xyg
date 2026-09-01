"""Shared static-export raster axis frames and tick marks."""

from __future__ import annotations

from typing import Any, Optional

from ._export_raster_cmd import _Cmd
from ._export_ticks import _axis_tick_label_strategy, _axis_tick_sides
from ._layout import _PolarProjection, _Scale
from ._paint import _css
from ._paint import paint_rgba8 as _parse_color


def _raster_baselines(
    cmd: _Cmd,
    spec: dict[str, Any],
    xa: dict[str, Any],
    ya: dict[str, Any],
    sx: _Scale,
    sy: _Scale,
    extra_x_axes: list[tuple[str, dict[str, Any], _Scale]],
    extra_y_axes: list[tuple[str, dict[str, Any], _Scale]],
    polar: Optional[_PolarProjection],
    *,
    px0: float,
    py0: float,
    px1: float,
    py1: float,
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
) -> None:
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
