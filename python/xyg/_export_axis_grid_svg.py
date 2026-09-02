"""Shared static-export SVG axis grid lines and tick labels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from . import _textblock
from ._export_chrome import _AXIS, _GRID, _TEXT, slot_font_size, slot_styles, slot_text_color
from ._export_polar_svg import (
    _polar_grid,
    _polar_radial_tick_length,
    _polar_thin_radial_labels,
    _polar_tick_labels,
)
from ._export_svg_util import _axis_grid_attrs, _num, _text_block_content, escape, slot_text_attrs
from ._export_ticks import (
    _axis_tick_font_size,
    _axis_tick_label_baseline_shift,
    _axis_tick_label_layout,
    _axis_tick_label_offset,
    _axis_tick_label_sides,
    _tick_label_anchor,
    axis_ticks,
    minor_axis_ticks,
)
from ._layout import _PolarProjection, _Scale
from ._paint import _css

_TEXT_ANCHORS = {"start": "start", "center": "middle", "end": "end"}


@dataclass(frozen=True)
class _AxisGridParts:
    grid: list[str]
    labels: list[str]
    extra_x_ticks: dict[str, tuple[list[float], list[float], float]]
    extra_y_ticks: dict[str, tuple[list[float], list[float], float]]
    xt: list[float]
    yt: list[float]
    xmt: list[float]
    ymt: list[float]
    hide_x: bool
    hide_y: bool
    default_grid: str
    default_axis: str
    default_text: str
    xstyle: dict[str, Any]
    ystyle: dict[str, Any]
    xmstyle: dict[str, Any]
    ymstyle: dict[str, Any]
    slots: dict[str, dict[str, Any]]


def _svg_axis_grid_and_labels(
    spec: dict[str, Any],
    plot: dict[str, float],
    xa: dict[str, Any],
    ya: dict[str, Any],
    sx: _Scale,
    sy: _Scale,
    extra_x_axes: list[tuple[str, dict[str, Any], _Scale]],
    extra_y_axes: list[tuple[str, dict[str, Any], _Scale]],
    polar: Optional[_PolarProjection],
) -> _AxisGridParts:
    xt, xlab, xstep = axis_ticks(xa, plot["w"], True)
    yt, ylab, ystep = axis_ticks(ya, plot["h"], False)
    if polar is not None:
        # Rings keep full density; only the labels ride the spoke.
        ylab = _polar_thin_radial_labels(ylab, _polar_radial_tick_length(polar))
    xmt, ymt = minor_axis_ticks(xa), minor_axis_ticks(ya)
    dom_style = (spec.get("dom") or {}).get("style") or {}
    xstyle, ystyle = xa.get("style") or {}, ya.get("style") or {}
    xmstyle, ymstyle = xa.get("minor_style") or {}, ya.get("minor_style") or {}
    default_grid = _css(dom_style.get("--chart-grid"), _GRID)
    default_axis = _css(dom_style.get("--chart-axis"), _AXIS)
    default_text = _css(dom_style.get("--chart-text"), _TEXT)
    slots = slot_styles(spec)
    grid: list[str] = []
    labels: list[str] = []
    # "none" silences the whole axis chrome (sparklines); "off" hides only the
    # label text and keeps grid, baselines and the axis title (mpl shared axes).
    hide_x = xa.get("tick_label_strategy") == "none"
    hide_y = ya.get("tick_label_strategy") == "none"
    if polar is not None:
        _polar_grid(grid, polar, xt, yt, xstyle, ystyle, default_grid, hide_x, hide_y)
    x_minor_px = (
        np.asarray(sx(xmt), dtype=np.float64) if polar is None and xmt else [0.0] * len(xmt)
    )
    y_minor_px = (
        np.asarray(sy(ymt), dtype=np.float64) if polar is None and ymt else [0.0] * len(ymt)
    )
    x_tick_px = np.asarray(sx(xt), dtype=np.float64) if polar is None and xt else [0.0] * len(xt)
    y_tick_px = np.asarray(sy(yt), dtype=np.float64) if polar is None and yt else [0.0] * len(yt)
    for _v, mapped in zip(xmt, x_minor_px, strict=True):
        if polar is not None:
            break
        if hide_x:
            break
        px = float(mapped)
        grid.append(
            f'<line data-xy-grid="minor" x1="{_num(px)}" y1="{_num(plot["y"])}" '
            f'x2="{_num(px)}" y2="{_num(plot["y"] + plot["h"])}" '
            f'stroke="{escape(_css(xmstyle.get("grid_color"), "transparent"))}" '
            f'stroke-width="{_num(float(xmstyle.get("grid_width", 1)))}"'
            f"{_axis_grid_attrs(xmstyle)}/>"
        )
    for _v, mapped in zip(ymt, y_minor_px, strict=True):
        if polar is not None:
            break
        if hide_y:
            break
        py = float(mapped)
        grid.append(
            f'<line data-xy-grid="minor" x1="{_num(plot["x"])}" y1="{_num(py)}" '
            f'x2="{_num(plot["x"] + plot["w"])}" y2="{_num(py)}" '
            f'stroke="{escape(_css(ymstyle.get("grid_color"), "transparent"))}" '
            f'stroke-width="{_num(float(ymstyle.get("grid_width", 1)))}"'
            f"{_axis_grid_attrs(ymstyle)}/>"
        )
    for _v, mapped in zip(xt, x_tick_px, strict=True):
        if polar is not None:
            break
        if hide_x:
            break
        px = float(mapped)
        grid.append(
            f'<line x1="{_num(px)}" y1="{_num(plot["y"])}" x2="{_num(px)}" '
            f'y2="{_num(plot["y"] + plot["h"])}" '
            f'stroke="{escape(_css(xstyle.get("grid_color"), default_grid))}" '
            f'stroke-width="{_num(float(xstyle.get("grid_width", 1)))}"'
            f"{_axis_grid_attrs(xstyle)}/>"
        )
    for _v, mapped in zip(yt, y_tick_px, strict=True):
        if polar is not None:
            break
        if hide_y:
            break
        py = float(mapped)
        grid.append(
            f'<line x1="{_num(plot["x"])}" y1="{_num(py)}" x2="{_num(plot["x"] + plot["w"])}" '
            f'y2="{_num(py)}" stroke="{escape(_css(ystyle.get("grid_color"), default_grid))}" '
            f'stroke-width="{_num(float(ystyle.get("grid_width", 1)))}"'
            f"{_axis_grid_attrs(ystyle)}/>"
        )

    def append_tick_labels(
        axis: dict[str, Any],
        values: list[float],
        step: float,
        axis_scale: _Scale,
        *,
        is_x: bool,
    ) -> None:
        axis_style = axis.get("style") or {}
        slot = slots.get("tick_label") or {}
        # The axis's own tick_label_color/tick_color is the narrower selector
        # and wins; the chart-wide slot fills in when the axis says nothing.
        color = escape(
            _css(
                axis_style.get("tick_label_color", axis_style.get("tick_color")),
                "",
            )
            or slot_text_color(slot, default_text)
        )
        font_size = slot_font_size(slot, _axis_tick_font_size(axis))
        slot_attrs = slot_text_attrs(slot)
        baseline_shift = _axis_tick_label_baseline_shift(axis)
        # An explicit tick_label_anchor (axis spec or style) overrides the
        # angle/side-derived default. Anchored labels rotate about the tick
        # point (the rotate() pivot below), so anchor and rotation compose —
        # matching the browser client.
        explicit_anchor = _tick_label_anchor(axis, axis_style, "")
        for side in _axis_tick_label_sides(axis, is_x=is_x):
            side_axis = {**axis, "side": side}
            # Unstyled defaults reproduce the pre-`tick_label_pad` placement exactly.
            if is_x:
                label_offset = (
                    _axis_tick_label_offset(axis, 7.0, 0.2)
                    if side == "top"
                    else _axis_tick_label_offset(axis, 16.0, 0.8)
                )
            else:
                label_offset = _axis_tick_label_offset(axis, 8.0)
            for item in _axis_tick_label_layout(side_axis, values, step, axis_scale, is_x):
                angle = float(item["angle"])
                block = _textblock.measure(item["text"], font_size)
                if is_x:
                    row_offset = float(item["row"]) * (font_size + 4)
                    x = float(item["pos"])
                    y = (
                        plot["y"] - label_offset - row_offset
                        if side == "top"
                        else plot["y"] + plot["h"] + label_offset + row_offset
                    )
                    if explicit_anchor:
                        anchor = _TEXT_ANCHORS[explicit_anchor]
                    elif angle == 0:
                        anchor = "middle"
                    elif (side == "bottom" and angle < 0) or (side == "top" and angle > 0):
                        anchor = "end"
                    else:
                        anchor = "start"
                else:
                    x = (
                        plot["x"] + plot["w"] + label_offset
                        if side == "right"
                        else plot["x"] - label_offset
                    )
                    y = (
                        float(item["pos"])
                        + baseline_shift
                        - (block.line_count - 1) * block.line_step / 2.0
                    )
                    if explicit_anchor:
                        anchor = _TEXT_ANCHORS[explicit_anchor]
                    else:
                        anchor = "start" if side == "right" else "end"
                transform = (
                    f' transform="rotate({_num(angle)} {_num(x)} {_num(y)})"' if angle else ""
                )
                labels.append(
                    f'<text x="{_num(x)}" y="{_num(y)}" fill="{color}" '
                    f'font-size="{_num(font_size)}" text-anchor="{anchor}"'
                    f"{slot_attrs}{transform}>"
                    f"{_text_block_content(item['text'], x, block.line_step)}</text>"
                )

    if polar is not None:
        # "off" hides only the label text (cartesian keeps grid and titles);
        # "none" — folded into hide_x/hide_y — silences the whole axis chrome.
        _polar_tick_labels(
            labels,
            polar,
            xlab,
            ylab,
            xstep,
            ystep,
            xa,
            ya,
            slots,
            default_text,
            hide_x or xa.get("tick_label_strategy") == "off",
            hide_y or ya.get("tick_label_strategy") == "off",
        )
    else:
        append_tick_labels(xa, xlab, xstep, sx, is_x=True)
        append_tick_labels(ya, ylab, ystep, sy, is_x=False)
    extra_x_ticks: dict[str, tuple[list[float], list[float], float]] = {}
    for axis_id, axis, axis_scale in extra_x_axes:
        ticks, tick_labels, step = axis_ticks(axis, plot["w"], True)
        extra_x_ticks[axis_id] = (ticks, tick_labels, step)
        append_tick_labels(axis, tick_labels, step, axis_scale, is_x=True)
    extra_y_ticks: dict[str, tuple[list[float], list[float], float]] = {}
    for axis_id, axis, axis_scale in extra_y_axes:
        ticks, tick_labels, step = axis_ticks(axis, plot["h"], False)
        extra_y_ticks[axis_id] = (ticks, tick_labels, step)
        append_tick_labels(axis, tick_labels, step, axis_scale, is_x=False)

    return _AxisGridParts(
        grid=grid,
        labels=labels,
        extra_x_ticks=extra_x_ticks,
        extra_y_ticks=extra_y_ticks,
        xt=xt,
        yt=yt,
        xmt=xmt,
        ymt=ymt,
        hide_x=hide_x,
        hide_y=hide_y,
        default_grid=default_grid,
        default_axis=default_axis,
        default_text=default_text,
        xstyle=xstyle,
        ystyle=ystyle,
        xmstyle=xmstyle,
        ymstyle=ymstyle,
        slots=slots,
    )
