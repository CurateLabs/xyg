"""Shared static-export polar SVG grid, wedge paths, and tick labels."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Optional

from ._export_chrome import slot_font_size, slot_text_color
from ._export_svg_util import (
    _axis_grid_attrs,
    _num,
    escape,
    slot_text_attrs,
)
from ._export_ticks import (
    _POLAR_RLABEL_DEG,
    _axis_tick_font_size,
    polar_tick_label_layout,
)
from ._layout import polar_wedge_points
from ._paint import _css

if TYPE_CHECKING:
    from ._layout import _PolarProjection


def _wedge_edge_inset(wedge_gap: float, a0: float, a1: float):
    """Per-radius angular inset that realises a constant px gap between wedges.

    Half the gap is taken off each side, and `gap / (2r)` radians at radius `r`
    is `gap / 2` px of arc — so neighbouring slices end up separated by the same
    number of pixels from the hole to the rim. Clamped so a gap wider than the
    slice collapses it rather than inverting the edges.
    """
    half = max(0.0, float(wedge_gap)) / 2.0
    sign = 1.0 if a1 >= a0 else -1.0
    span = abs(a1 - a0)

    def inset(radius: float) -> float:
        if half <= 0.0 or radius <= 1e-9:
            return 0.0
        return sign * min(half / radius, span / 2.0)

    return inset


def _polar_wedge_path(
    polar: _PolarProjection,
    theta0: float,
    theta1: float,
    r0: float,
    r1: float,
    corner_radius: float = 0.0,
    wedge_gap: float = 0.0,
    normalized: Optional[tuple[float, float]] = None,
) -> str:
    """An annular sector as an SVG path: outer arc, inner arc reversed, closed.

    A polar bar is a wedge, not a rectangle — a 180-degree bar with chorded ends
    would read as a triangle. SVG expresses the two arcs exactly with `A`; the
    raster exporter flattens the same sector because its display list has no arc
    opcode (polar-axes.md §5/§6).
    """
    floor = polar.inner_fraction
    # Order the NORMALIZED fractions before clamping: on a reversed radial
    # axis `norm_radius` is decreasing, so norm(r1) < norm(r0) for r1 > r0 and
    # taking them positionally dropped every wedge from both static exports
    # while the shader (which min/maxes u_rrange) kept drawing them.
    lo_frac, hi_frac = (
        sorted((float(polar.norm_radius(r0)), float(polar.norm_radius(r1))))
        if normalized is None
        else sorted(normalized)
    )
    outer = min(1.0, max(floor, hi_frac)) * polar.radius
    inner = min(1.0, max(floor, lo_frac)) * polar.radius
    if outer <= 0.0 or outer <= inner:
        return ""
    angles = polar.wedge_angles(theta0, theta1)
    if angles is None:
        return ""
    a0, a1 = angles
    if corner_radius > 0.0 and inner > 0.0:
        # Rounded corners are not circular arcs once rolled back out of the
        # unrolled frame, so the shared ABI 209 polygon is the honest shape
        # here too. Auto `steps` matches the raster twin.
        pts = polar_wedge_points(
            polar,
            theta0,
            theta1,
            r0,
            r1,
            corner_radius=corner_radius,
            wedge_gap=wedge_gap,
            normalized=normalized,
        )
        if len(pts) < 3:
            return ""
        head = f"M {_num(pts[0][0])} {_num(pts[0][1])}"
        rest = " ".join(f"L {_num(x)} {_num(y)}" for x, y in pts[1:])
        return f"{head} {rest} Z"
    # `sweep` is in SVG's screen sense: y grows downward, so a counterclockwise
    # data sweep draws as a clockwise-negative arc.
    sweep = 0 if a1 > a0 else 1
    large = 1 if abs(a1 - a0) > math.pi else 0

    def at(radius: float, angle: float) -> tuple[float, float]:
        return polar.cx + radius * math.cos(angle), polar.cy - radius * math.sin(angle)

    if abs(a1 - a0) >= 2.0 * math.pi * (1.0 - 1e-9):
        # A full turn makes the arc endpoints coincide, and SVG omits such an
        # arc segment entirely — a 100% donut slice rendered as nothing. Each
        # circle is drawn as two half-turn arcs instead; the inner ring winds
        # the opposite way so the default nonzero fill leaves the hole open.
        def full_circle(radius: float, sweep_flag: int) -> str:
            x0, y0 = at(radius, a0)
            xm, ym = at(radius, a0 + math.pi)
            arc = f"A {_num(radius)} {_num(radius)} 0 1 {sweep_flag}"
            return (
                f"M {_num(x0)} {_num(y0)} {arc} {_num(xm)} {_num(ym)} {arc} {_num(x0)} {_num(y0)} Z"
            )

        if inner <= 0.0:
            return full_circle(outer, sweep)
        return f"{full_circle(outer, sweep)} {full_circle(inner, 1 - sweep)}"

    # The gap is a constant number of PIXELS, so its angular cost grows as the
    # radius shrinks (`_wedge_edge_inset`). Both arcs stay exact `A` commands —
    # only their endpoints move inward — and the radial edges become straight
    # lines a fixed distance apart, which `L` already draws.
    inset = _wedge_edge_inset(wedge_gap, a0, a1)
    d_out, d_in = inset(outer), inset(max(inner, 1e-9))
    ox0, oy0 = at(outer, a0 + d_out)
    ox1, oy1 = at(outer, a1 - d_out)
    if inner <= 0.0:
        return (
            f"M {_num(polar.cx)} {_num(polar.cy)} L {_num(ox0)} {_num(oy0)} "
            f"A {_num(outer)} {_num(outer)} 0 {large} {sweep} {_num(ox1)} {_num(oy1)} Z"
        )
    ix1, iy1 = at(inner, a1 - d_in)
    ix0, iy0 = at(inner, a0 + d_in)
    return (
        f"M {_num(ox0)} {_num(oy0)} "
        f"A {_num(outer)} {_num(outer)} 0 {large} {sweep} {_num(ox1)} {_num(oy1)} "
        f"L {_num(ix1)} {_num(iy1)} "
        f"A {_num(inner)} {_num(inner)} 0 {large} {1 - sweep} {_num(ix0)} {_num(iy0)} Z"
    )


def _polar_radial_tick_length(polar: _PolarProjection) -> float:
    """Label-density length for the radial axis under polar.

    Radial labels march along a `_POLAR_RLABEL_DEG` spoke, so their usable run
    is the annulus width projected onto that spoke — about a fifth of the plot
    at the default 22.5 degrees. Mirrored by _radialTickLength in
    js/src/50_chartview.ts.
    """
    span = polar.radius * (1.0 - polar.inner_fraction)
    return max(1.0, span * abs(math.sin(math.radians(_POLAR_RLABEL_DEG))))


def _polar_thin_radial_labels(labels: list[float], length_px: float) -> list[float]:
    """Stride-thin radial tick LABELS to what the spoke can hold.

    The grid rings and the labels come from one tick list, so sizing the whole
    list to the spoke thinned the rings too — a 520px disc dropped from three
    rings to two. Ring density stays tied to the plot; only the labels, which
    are the things that actually collide, are thinned. Endpoints are kept so
    the radial extent stays readable.
    """
    capacity = max(2, int(length_px / 45))
    if len(labels) <= capacity:
        return labels
    stride = math.ceil(len(labels) / capacity)
    thinned = labels[::stride]
    if labels and labels[-1] not in thinned:
        thinned.append(labels[-1])
    return thinned


def _polar_frame_path(polar: _PolarProjection) -> str:
    """SVG path for the visible annular sector, shared by clip and frame."""
    return _polar_wedge_path(
        polar,
        polar._theta_data_for_sector(polar.sector_start),
        polar._theta_data_for_sector(polar.sector_end),
        polar.r_lo,
        polar.r_hi,
    )


def _polar_linear_frame_path(polar: _PolarProjection, theta_values: Sequence[float]) -> str:
    """Polygon-grid counterpart of ``_polar_frame_path``."""
    outer = polar.polygon_ring(polar.r_hi, theta_values)
    if len(outer) < 2:
        return _polar_frame_path(polar)

    def polyline(points: Sequence[tuple[float, float]], close: bool = False) -> str:
        commands = [f"M {_num(points[0][0])} {_num(points[0][1])}"]
        commands.extend(f"L {_num(x)} {_num(y)}" for x, y in points[1:])
        if close:
            commands.append("Z")
        return " ".join(commands)

    parts = [polyline(outer, polar.full_sector)]
    if polar.inner_radius > 0.0:
        inner = polar.polygon_ring(polar.r_lo, theta_values)
        if inner:
            parts.append(polyline(inner, polar.full_sector))
    else:
        inner = [(polar.cx, polar.cy)]
    if not polar.full_sector:
        parts.append(polyline([outer[0], inner[0]]))
        parts.append(polyline([outer[-1], inner[-1]]))
    return " ".join(parts)


def _polar_grid(
    grid: list[str],
    polar: _PolarProjection,
    theta_ticks: list[float],
    r_ticks: list[float],
    theta_style: dict[str, Any],
    r_style: dict[str, Any],
    default_grid: str,
    hide_theta: bool,
    hide_r: bool,
) -> None:
    """Concentric rings for the radial ticks, spokes for the angular ones.

    SVG has `<circle>`, so rings are exact here rather than flattened; the
    raster exporter has no arc opcode and consumes `_PolarProjection.ring`
    instead. Both read the same tick lists, so the two outputs agree on *which*
    rings exist even though they differ in how the curve is expressed.
    """
    theta_ticks = polar.filter_theta_values(theta_ticks)
    r_ticks = [value for value in r_ticks if bool(polar.visible_mask(value))]
    r_grid = escape(_css(r_style.get("grid_color"), default_grid))
    r_width = _num(float(r_style.get("grid_width", 1)))
    r_attrs = _axis_grid_attrs(r_style)
    if not hide_r:
        for v in r_ticks:
            radius = float(polar.norm_radius(v)) * polar.radius
            if radius <= 0.0:
                continue  # the r=0 ring is a point at the centre
            if polar.grid_shape == "linear":
                points = polar.polygon_ring(v, theta_ticks)
                if len(points) < 2:
                    continue
                commands = " ".join(f"{_num(x)},{_num(y)}" for x, y in points)
                tag = "polygon" if polar.full_sector else "polyline"
                grid.append(
                    f'<{tag} data-xy-grid="ring" points="{commands}" fill="none" '
                    f'stroke="{r_grid}" stroke-width="{r_width}"{r_attrs}/>'
                )
            elif polar.full_sector:
                grid.append(
                    f'<circle data-xy-grid="ring" cx="{_num(polar.cx)}" cy="{_num(polar.cy)}" '
                    f'r="{_num(radius)}" fill="none" stroke="{r_grid}" '
                    f'stroke-width="{r_width}"{r_attrs}/>'
                )
            else:
                a0, a1 = polar.sector_a0, polar.sector_a1
                x0 = polar.cx + radius * math.cos(a0)
                y0 = polar.cy - radius * math.sin(a0)
                x1 = polar.cx + radius * math.cos(a1)
                y1 = polar.cy - radius * math.sin(a1)
                large = 1 if abs(a1 - a0) > math.pi else 0
                sweep = 0 if a1 > a0 else 1
                grid.append(
                    f'<path data-xy-grid="ring" d="M {_num(x0)} {_num(y0)} '
                    f"A {_num(radius)} {_num(radius)} 0 {large} {sweep} "
                    f'{_num(x1)} {_num(y1)}" fill="none" stroke="{r_grid}" '
                    f'stroke-width="{r_width}"{r_attrs}/>'
                )
    if hide_theta:
        return
    t_grid = escape(_css(theta_style.get("grid_color"), default_grid))
    t_width = _num(float(theta_style.get("grid_width", 1)))
    t_attrs = _axis_grid_attrs(theta_style)
    for v in theta_ticks:
        angle = float(polar.angle(v))
        inner = polar.inner_radius
        x0 = polar.cx + inner * math.cos(angle)
        y0 = polar.cy - inner * math.sin(angle)
        x1 = polar.cx + polar.radius * math.cos(angle)
        y1 = polar.cy - polar.radius * math.sin(angle)
        grid.append(
            f'<line data-xy-grid="spoke" x1="{_num(x0)}" y1="{_num(y0)}" '
            f'x2="{_num(x1)}" y2="{_num(y1)}" stroke="{t_grid}" '
            f'stroke-width="{t_width}"{t_attrs}/>'
        )


def _polar_tick_labels(
    labels: list[str],
    polar: _PolarProjection,
    theta_values: list[float],
    r_values: list[float],
    theta_step: float,
    r_step: float,
    theta_axis: dict[str, Any],
    r_axis: dict[str, Any],
    slots: dict[str, Any],
    default_text: str,
    hide_theta: bool,
    hide_r: bool,
) -> None:
    """Emit polar tick labels as SVG text, from the shared placement."""
    slot = slots.get("tick_label") or {}
    attrs = slot_text_attrs(slot)

    def tick_color(axis: dict[str, Any]) -> str:
        """Axis tick_label_color/tick_color first, chart slot second.

        Same precedence the cartesian labels use: the axis's own setting is the
        narrower selector and wins. Reading only the slot made the `text=False`
        and `show=False` shorthands — which work by setting tick_label_color to
        a transparent value — silently do nothing on a polar chart.
        """
        axis_style = axis.get("style") or {}
        own = _css(axis_style.get("tick_label_color", axis_style.get("tick_color")), "")
        return escape(own or slot_text_color(slot, default_text))

    angular, radial = polar_tick_label_layout(
        polar,
        theta_values,
        r_values,
        theta_step,
        r_step,
        theta_axis,
        r_axis,
        slot_font_size(slot, _axis_tick_font_size(theta_axis)),
        slot_font_size(slot, _axis_tick_font_size(r_axis)),
        hide_theta,
        hide_r,
    )
    for kind, placed, axis in (("theta", angular, theta_axis), ("r", radial, r_axis)):
        color = tick_color(axis)
        for item in placed:
            spin = (
                f' transform="rotate({_num(item.spin)} {_num(item.x)} {_num(item.y)})"'
                if item.spin
                else ""
            )
            labels.append(
                f'<text data-xy-tick="{kind}" x="{_num(item.x)}" y="{_num(item.y)}" '
                f'fill="{color}" font-size="{_num(item.size)}" '
                f'text-anchor="{item.anchor}"{attrs}{spin}>{escape(item.text)}</text>'
            )
