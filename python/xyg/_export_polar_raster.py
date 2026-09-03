"""Shared static-export polar raster grid and tick labels."""

from __future__ import annotations

import math
from typing import Any

from ._export_chrome import _AXIS_GRID_DASHES
from ._export_raster_cmd import _TEXT_ANCHOR_CODES, _Cmd
from ._export_ticks import polar_tick_label_layout
from ._layout import _PolarProjection
from ._paint import _css
from ._paint import paint_rgba8 as _parse_color


def _emit_polar_grid(
    cmd: _Cmd,
    polar: _PolarProjection,
    theta_ticks: list[float],
    r_ticks: list[float],
    theta_style: dict[str, Any],
    r_style: dict[str, Any],
    default_grid: str,
    hide_theta: bool,
    hide_r: bool,
) -> None:
    """Concentric rings and radial spokes, in display-list commands.

    The rasterizer has no arc, wedge or circle opcode — its only curves are
    pre-flattened polylines — so each ring ships as a closed polyline from
    `_PolarProjection.ring`. The SVG exporter draws the same rings as exact
    `<circle>` elements; both read the same tick list, so they agree on which
    rings exist even though the curve is expressed differently.
    """
    theta_ticks = polar.filter_theta_values(theta_ticks)
    r_ticks = [value for value in r_ticks if bool(polar.visible_mask(value))]
    if not hide_r:
        for v in r_ticks:
            radius = float(polar.norm_radius(v)) * polar.radius
            if radius <= 0.0:
                continue
            ring = (
                polar.polygon_ring(v, theta_ticks)
                if polar.grid_shape == "linear"
                else polar.ring(v)
            )
            if len(ring) < 2:
                continue
            cmd.stroke(
                [*ring, ring[0]] if polar.full_sector else ring,
                float(r_style.get("grid_width", 1)),
                _parse_color(
                    _css(r_style.get("grid_color"), default_grid),
                    float(r_style.get("grid_opacity", 1.0)),
                ),
                dash=_AXIS_GRID_DASHES.get(str(r_style.get("grid_dash", "solid"))),
            )
    if hide_theta:
        return
    for v in theta_ticks:
        angle = float(polar.angle(v))
        inner = polar.inner_radius
        cmd.stroke(
            [
                (
                    polar.cx + inner * math.cos(angle),
                    polar.cy - inner * math.sin(angle),
                ),
                (
                    polar.cx + polar.radius * math.cos(angle),
                    polar.cy - polar.radius * math.sin(angle),
                ),
            ],
            float(theta_style.get("grid_width", 1)),
            _parse_color(
                _css(theta_style.get("grid_color"), default_grid),
                float(theta_style.get("grid_opacity", 1.0)),
            ),
            dash=_AXIS_GRID_DASHES.get(str(theta_style.get("grid_dash", "solid"))),
        )


def _polar_label_paint(axis: dict[str, Any], slot_paint: Any, default_text: str) -> tuple[int, ...]:
    """Axis tick_label_color/tick_color first, chart slot second.

    Mirrors `tick_color` inside `_svg._polar_tick_labels`. Without the axis
    lookup the `text=False`/`show=False` shorthands — which work by setting
    tick_label_color transparent — silently did nothing on a polar chart.
    """
    axis_style = axis.get("style") or {}
    own = _css(axis_style.get("tick_label_color", axis_style.get("tick_color")), "")
    return _parse_color(own) if own else slot_paint("tick_label", default_text)


def _emit_polar_tick_labels(
    cmd: _Cmd,
    polar: _PolarProjection,
    theta_values: list[float],
    r_values: list[float],
    theta_step: float,
    r_step: float,
    theta_axis: dict[str, Any],
    r_axis: dict[str, Any],
    theta_size: float,
    r_size: float,
    theta_color: tuple[int, ...],
    r_color: tuple[int, ...],
    hide_theta: bool,
    hide_r: bool,
) -> None:
    """Emit polar tick labels as display-list text, from the shared placement.

    Placement lives in `_svg.polar_tick_label_layout`; this is only the sink,
    so the two exporters cannot drift on rim offsets, quadrant anchors or the
    radial spoke angle.
    """
    angular, radial = polar_tick_label_layout(
        polar,
        theta_values,
        r_values,
        theta_step,
        r_step,
        theta_axis,
        r_axis,
        theta_size,
        r_size,
        hide_theta,
        hide_r,
    )
    for placed, paint in ((angular, theta_color), (radial, r_color)):
        for item in placed:
            cmd.text(
                item.x,
                item.y,
                # The layout speaks SVG's anchor vocabulary; the display list
                # calls the same thing "center".
                _TEXT_ANCHOR_CODES["center" if item.anchor == "middle" else item.anchor],
                item.size,
                paint,
                item.text,
                angle=item.spin,
            )
