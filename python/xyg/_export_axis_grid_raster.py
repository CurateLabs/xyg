"""Shared static-export raster axis grid lines."""

from __future__ import annotations

from typing import Any, Optional

from ._export_chrome import _AXIS_GRID_DASHES
from ._export_polar_raster import _emit_polar_grid
from ._export_raster_cmd import _Cmd
from ._layout import _PolarProjection, _Scale
from ._paint import _css
from ._paint import paint_rgba8 as _parse_color


def _raster_axis_grid(
    cmd: _Cmd,
    polar: Optional[_PolarProjection],
    sx: _Scale,
    sy: _Scale,
    *,
    xt: list[float],
    yt: list[float],
    xmt: list[float],
    ymt: list[float],
    xstyle: dict[str, Any],
    ystyle: dict[str, Any],
    xmstyle: dict[str, Any],
    ymstyle: dict[str, Any],
    default_grid: str,
    hide_x: bool,
    hide_y: bool,
    px0: float,
    py0: float,
    px1: float,
    py1: float,
) -> None:
    if polar is not None:
        _emit_polar_grid(cmd, polar, xt, yt, xstyle, ystyle, default_grid, hide_x, hide_y)
    for v in [] if hide_x or polar is not None else xmt:
        gx = float(sx(v))
        cmd.stroke(
            [(gx, py0), (gx, py1)],
            float(xmstyle.get("grid_width", 1)),
            _parse_color(
                _css(xmstyle.get("grid_color"), "transparent"),
                float(xmstyle.get("grid_opacity", 1.0)),
            ),
            dash=_AXIS_GRID_DASHES.get(str(xmstyle.get("grid_dash", "solid"))),
        )
    for v in [] if hide_y or polar is not None else ymt:
        gy = float(sy(v))
        cmd.stroke(
            [(px0, gy), (px1, gy)],
            float(ymstyle.get("grid_width", 1)),
            _parse_color(
                _css(ymstyle.get("grid_color"), "transparent"),
                float(ymstyle.get("grid_opacity", 1.0)),
            ),
            dash=_AXIS_GRID_DASHES.get(str(ymstyle.get("grid_dash", "solid"))),
        )
    for v in [] if hide_x or polar is not None else xt:
        gx = float(sx(v))
        cmd.stroke(
            [(gx, py0), (gx, py1)],
            float(xstyle.get("grid_width", 1)),
            _parse_color(
                _css(xstyle.get("grid_color"), default_grid),
                float(xstyle.get("grid_opacity", 1.0)),
            ),
            dash=_AXIS_GRID_DASHES.get(str(xstyle.get("grid_dash", "solid"))),
        )
    for v in [] if hide_y or polar is not None else yt:
        gy = float(sy(v))
        cmd.stroke(
            [(px0, gy), (px1, gy)],
            float(ystyle.get("grid_width", 1)),
            _parse_color(
                _css(ystyle.get("grid_color"), default_grid),
                float(ystyle.get("grid_opacity", 1.0)),
            ),
            dash=_AXIS_GRID_DASHES.get(str(ystyle.get("grid_dash", "solid"))),
        )
