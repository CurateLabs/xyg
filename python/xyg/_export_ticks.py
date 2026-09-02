"""Shared static-export tick ladders, labels, and polar tick placement."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, NamedTuple

import numpy as np

from . import _native
from ._layout import _PolarProjection, _Scale

_MS = {"s": 1e3, "m": 6e4, "h": 36e5, "d": 864e5}

# Gap in px between the outer ring and the angular tick labels.
# Mirrored by POLAR_TICK_GAP in js/src/50_chartview.ts.
_POLAR_TICK_GAP = 8.0

# Angle of the spoke the radial tick labels run along, in degrees off the theta
# zero direction. Matplotlib's default `rlabel_position`; keeping the labels off
# the zero spoke stops them colliding with the theta=0 angular label. Shared by
# both exporters so they cannot drift apart.
# Mirrored by POLAR_RLABEL_DEG in js/src/50_chartview.ts.
_POLAR_RLABEL_DEG = 22.5


def _fmt_log(v: float) -> str:
    """Colorbar log tick labels — same magnitude policy as axis log ticks."""
    return _native.tick_format(float(v), 1.0, scale="log")


def _fmt_axis(axis: dict[str, Any], v: float, step: float) -> str:
    return _native.tick_format(
        float(v),
        float(step),
        kind=axis.get("kind"),
        scale=axis.get("scale"),
        theta_unit=axis.get("theta_unit"),
        format=axis.get("format"),
        categories=axis.get("categories"),
    )


def _tick_text(axis: dict[str, Any], value: float, step: float) -> str:
    values = axis.get("tick_values")
    labels = axis.get("tick_labels")
    if values is not None and labels is not None:
        for index, candidate in enumerate(values):
            if float(candidate) == value and index < len(labels):
                return str(labels[index])
    return _fmt_axis(axis, value, step)


def _tick_label_anchor(axis: dict[str, Any], style: dict[str, Any], default: str) -> str:
    """Canonical tick-label anchor (``start``/``center``/``end``) from the
    axis spec or its style — validators normalize the mpl aliases upstream —
    with ``default`` (the classic layout) when unset."""
    raw = axis.get("tick_label_anchor") or style.get("tick_label_anchor")
    return raw if raw in ("start", "center", "end") else default


def _colorbar_right_axis_room(
    y_axis: dict[str, Any],
    extra_y_axes: list[tuple[str, dict[str, Any], _Scale]],
    compact: bool,
) -> float:
    """Gutter layout() reserves for visible right-side named y axes.

    The vertical colorbar shifts right by this amount so its bar/ticks/label
    clear the axis tick labels (plot-right+8) and rotated axis title
    (plot-right+40); the JS client applies the identical rule."""
    axes = [y_axis, *(axis for _axis_id, axis, _axis_scale in extra_y_axes)]
    if any(
        (axis.get("side", "left") == "right" or "right" in _axis_tick_label_sides(axis, is_x=False))
        and _axis_tick_label_strategy(axis) != "none"
        for axis in axes
    ):
        return float(_native.compat_right_y_room(compact))
    return 0.0


def _tick_window(axis: dict[str, Any]) -> tuple[float, float]:
    """The value window ticks are drawn in — the sector for an angular axis."""
    lo, hi = (float(v) for v in axis["range"])
    sector = axis.get("sector")
    if sector:
        sector_lo, sector_hi = float(sector[0]), float(sector[1])
    else:
        sector_lo = sector_hi = float("nan")
    return _native.tick_window(
        lo,
        hi,
        theta_unit=axis.get("theta_unit"),
        kind="category" if axis.get("kind") == "category" else "linear",
        n_categories=len(axis.get("categories") or []),
        sector_lo=sector_lo,
        sector_hi=sector_hi,
    )


def _tick_window_filter(
    axis: dict[str, Any],
    lo: float,
    hi: float,
    values: Sequence[Any],
    *,
    require_finite: bool = False,
) -> list[float]:
    """Compact ``values`` that fall inside the axis window."""
    return _native.tick_window_filter(
        [float(v) for v in values],
        lo,
        hi,
        theta_unit=axis.get("theta_unit"),
        kind="category" if axis.get("kind") == "category" else "linear",
        require_finite=require_finite,
    )


def axis_ticks(
    axis: dict[str, Any], length_px: float, is_x: bool
) -> tuple[list[float], list[float], float]:
    """(ticks, labeled ticks, step) for an axis at a given pixel length — shared
    tick density so SVG and PNG label the same values."""
    kind = axis.get("kind")
    lo, hi = _tick_window(axis)
    if axis.get("tick_values") is not None:
        ticks = _tick_window_filter(axis, lo, hi, axis["tick_values"])
        step = abs(ticks[1] - ticks[0]) if len(ticks) > 1 else 1.0
        return ticks, ticks, step
    requested = axis.get("tick_count")
    if isinstance(requested, (int, float)) and not isinstance(requested, bool) and requested > 0:
        target = max(1, min(200, int(requested)))
    else:
        target = max(3, int(length_px / 80)) if is_x else max(3, int(length_px / 45))
    aux = 0.0
    if kind == "category":
        categories = axis.get("categories") or []
        if axis.get("theta_unit") is not None and requested is None:
            target = len(categories)
        rust_kind = 2
        aux = float(len(categories))
    elif axis.get("theta_unit") is not None:
        rust_kind = 3 if axis["theta_unit"] == "degrees" else 4
    elif axis.get("scale") == "log" or kind == "log":
        rust_kind = 1
    elif axis.get("scale") == "symlog":
        rust_kind = 6
        aux = float(axis.get("constant", 1.0))
    elif kind == "time":
        rust_kind = 5
    else:
        rust_kind = 0
    try:
        return _native.scene_axis_ticks(rust_kind, lo, hi, target, aux=aux)
    except ValueError:
        return [], [], _MS["d"] if rust_kind == 5 else 1.0


def minor_axis_ticks(axis: dict[str, Any]) -> list[float]:
    values = axis.get("minor_tick_values")
    if values is None:
        return []
    lo, hi = _tick_window(axis)
    return _tick_window_filter(axis, lo, hi, values, require_finite=True)


def _axis_tick_label_strategy(axis: dict[str, Any]) -> str:
    value = str(axis.get("tick_label_strategy") or "auto").replace("-", "_")
    return (
        value
        if value in {"auto", "hide", "rotate", "stagger", "preserve", "none", "off"}
        else "auto"
    )


def _axis_tick_font_size(axis: dict[str, Any]) -> float:
    style = axis.get("style") or {}
    default = 12 if style.get("_scene_public_chrome_defaults") else 11
    return max(8.0, float(style.get("tick_label_size", style.get("tick_size", default))))


def _axis_visibility_switch(style: dict[str, Any]) -> bool:
    """Whether an axis uses a public ticks/text visibility shorthand."""
    return (style.get("tick_length") == 0 and style.get("tick_width") == 0) or (
        style.get("tick_label_color") == "#00000000" and style.get("label_color") == "#00000000"
    )


def _preserve_scene_chrome_for_axis_visibility(spec: dict[str, Any]) -> dict[str, Any]:
    """Keep a visibility-switch fallback visually continuous with public Scene."""
    primary = (spec.get("x_axis") or {}, spec.get("y_axis") or {})
    if not any(_axis_visibility_switch(axis.get("style") or {}) for axis in primary):
        return spec
    copied = dict(spec)
    for name in ("x_axis", "y_axis"):
        axis = dict(spec[name])
        axis["style"] = {**(axis.get("style") or {}), "_scene_public_chrome_defaults": True}
        copied[name] = axis
    return copied


def _axis_tick_geometry_authored(axis: dict[str, Any]) -> bool:
    """True when the axis authored tick geometry (label pad or mark length)."""
    style = axis.get("style") or {}
    if "tick_padding" in style:
        return True
    if "tick_length" not in style:
        return False
    return not (
        float(style.get("tick_length", 0)) == 0.0 and float(style.get("tick_width", 1)) == 0.0
    )


def _axis_tick_sides(axis: dict[str, Any], *, is_x: bool) -> list[str]:
    """Sides that paint tick marks, independent of the label-bearing side."""
    allowed = ("bottom", "top") if is_x else ("left", "right")
    authored = axis.get("tick_sides")
    if not isinstance(authored, list):
        return [axis.get("side", allowed[0])]
    return [side for side in allowed if side in authored]


def _axis_tick_label_sides(axis: dict[str, Any], *, is_x: bool) -> list[str]:
    """Sides that paint tick labels, independent of tick marks and titles."""
    allowed = ("bottom", "top") if is_x else ("left", "right")
    authored = axis.get("tick_label_sides")
    if not isinstance(authored, list):
        return [axis.get("side", allowed[0])]
    return [side for side in allowed if side in authored]


def _axis_tick_label_offset(axis: dict[str, Any], unstyled: float, font_room: float = 0.0) -> float:
    """Distance from the axis spine to a tick label's anchor point, in px."""
    if not _axis_tick_geometry_authored(axis):
        return unstyled
    style = axis.get("style") or {}
    length = max(0.0, float(style.get("tick_length", 0)))
    direction = str(style.get("tick_direction", "out"))
    outward = 0.0 if direction == "in" else length / 2 if direction == "inout" else length
    pad = outward + float(style.get("tick_padding", 4))
    return pad + _axis_tick_font_size(axis) * font_room


def _axis_tick_label_baseline_shift(axis: dict[str, Any]) -> float:
    """Baseline nudge that centers a y tick label on its tick, in px."""
    if not _axis_tick_geometry_authored(axis):
        return 4.0
    return _axis_tick_font_size(axis) * 0.35


def _axis_tick_label_layout(
    axis: dict[str, Any],
    values: list[float],
    step: float,
    scale: _Scale,
    is_x: bool,
) -> list[dict[str, Any]]:
    """Thin packer over Rust tick-label collision layout (ABI 123)."""
    strategy = _axis_tick_label_strategy(axis)
    font_size = _axis_tick_font_size(axis)
    min_gap = float(axis.get("tick_label_min_gap", 8 if is_x else 4))
    raw_angle = axis.get("tick_label_angle")
    explicit_angle = float(raw_angle) if raw_angle is not None else float("nan")
    axis_style = axis.get("style") or {}
    anchor = _tick_label_anchor(axis, axis_style, "center") if is_x else "center"
    positions = np.asarray(scale(values), dtype=np.float64)
    texts = [_tick_text(axis, value, step) for value in values]
    side_raw = str(axis.get("side") or "").strip().lower()
    side = side_raw if side_raw in {"bottom", "top", "left", "right"} else "bottom"
    kept = _native.scene_tick_label_layout(
        positions,
        texts,
        kind=strategy,
        side=side,
        anchor=anchor,
        is_x=is_x,
        category=axis.get("kind") == "category",
        font_size=font_size,
        min_gap=min_gap,
        explicit_angle=explicit_angle,
    )
    out: list[dict[str, Any]] = []
    for item in kept:
        index = int(item["index"])
        out.append(
            {
                "value": float(values[index]),
                "pos": float(positions[index]),
                "text": texts[index],
                "angle": float(item["angle"]),
                "row": int(item["row"]),
            }
        )
    return out


class PolarTickLabel(NamedTuple):
    """One placed polar tick label, in renderer-neutral terms."""

    x: float
    y: float
    anchor: str
    size: float
    text: str
    spin: float


def polar_tick_label_layout(
    polar: _PolarProjection,
    theta_values: list[float],
    r_values: list[float],
    theta_step: float,
    r_step: float,
    theta_axis: dict[str, Any],
    r_axis: dict[str, Any],
    theta_size: float,
    r_size: float,
    hide_theta: bool,
    hide_r: bool,
) -> tuple[list[PolarTickLabel], list[PolarTickLabel]]:
    """Where every polar tick label goes: (angular, radial)."""
    angular: list[PolarTickLabel] = []
    radial: list[PolarTickLabel] = []
    theta_spin = float(theta_axis.get("tick_label_angle") or 0.0)
    r_spin = float(r_axis.get("tick_label_angle") or 0.0)
    if not hide_theta:
        for v in polar.filter_theta_values(theta_values):
            angle = float(polar.angle(v))
            x = polar.cx + (polar.radius + _POLAR_TICK_GAP) * math.cos(angle)
            y = polar.cy - (polar.radius + _POLAR_TICK_GAP) * math.sin(angle)
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            anchor = "middle" if abs(cos_a) < 0.3 else ("start" if cos_a > 0 else "end")
            dy = 0.0 if abs(sin_a) < 0.3 else (-0.1 * theta_size if sin_a > 0 else 0.8 * theta_size)
            angular.append(
                PolarTickLabel(
                    x, y + dy, anchor, theta_size, _tick_text(theta_axis, v, theta_step), theta_spin
                )
            )
    if not hide_r:
        angle = polar.zero + polar.dir * math.radians(_POLAR_RLABEL_DEG)
        if not polar.angle_visible(angle):
            angle = (polar.sector_a0 + polar.sector_a1) / 2.0
        for v in r_values:
            if not bool(polar.visible_mask(v)):
                continue
            radius = float(polar.norm_radius(v)) * polar.radius
            if radius <= 0.0:
                continue
            radial.append(
                PolarTickLabel(
                    polar.cx + radius * math.cos(angle) + 3.0,
                    polar.cy - radius * math.sin(angle) - 3.0,
                    "start",
                    r_size,
                    _tick_text(r_axis, v, r_step),
                    r_spin,
                )
            )
    return angular, radial
