"""Shared static-export raster chrome text (tick labels, titles, legends)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from . import _textblock
from ._export_annotations import _axis_label_geometry
from ._export_chrome import (
    legend_options_with_slot,
    slot_font_size,
    slot_styles,
    slot_text_color,
)
from ._export_layout import _title_entries, _title_metrics
from ._export_legend import legend_clip_rect, legend_items
from ._export_legend_raster import _emit_colorbar
from ._export_marks_raster import _native_font_emphasis
from ._export_polar_raster import _emit_polar_tick_labels, _polar_label_paint
from ._export_raster_cmd import _TEXT_ANCHOR_CODES, _Cmd, _emit_text_block
from ._export_ticks import (
    _axis_tick_font_size,
    _axis_tick_label_baseline_shift,
    _axis_tick_label_layout,
    _axis_tick_label_offset,
    _axis_tick_label_sides,
    _axis_tick_label_strategy,
    _colorbar_right_axis_room,
    _tick_label_anchor,
)
from ._layout import _PolarProjection, _Scale
from ._paint import _css
from ._paint import paint_rgba8 as _parse_color


def _raster_chrome(
    cmd: _Cmd,
    spec: dict[str, Any],
    plot: dict[str, float],
    width: float,
    height: float,
    xa: dict[str, Any],
    ya: dict[str, Any],
    sx: _Scale,
    sy: _Scale,
    extra_x_axes: list[tuple[str, dict[str, Any], _Scale]],
    extra_y_axes: list[tuple[str, dict[str, Any], _Scale]],
    polar: Optional[_PolarProjection],
    *,
    compact: bool,
    px0: float,
    py0: float,
    px1: float,
    py1: float,
    xlab: list[float],
    ylab: list[float],
    xstep: float,
    ystep: float,
    extra_x_ticks: dict[str, tuple[list[float], list[float], float]],
    extra_y_ticks: dict[str, tuple[list[float], list[float], float]],
    hide_x: bool,
    hide_y: bool,
    default_text: str,
    spec_palette: Sequence[str],
) -> None:
    slots = slot_styles(spec)

    def slot_paint(slot: str, fallback: str) -> tuple:
        """A slot's text paint, or the writer's own default."""
        resolved = slot_text_color(slots.get(slot) or {}, "")
        return _parse_color(resolved or fallback)

    def emit_tick_labels(
        axis: dict[str, Any],
        values: list[float],
        step: float,
        axis_scale: _Scale,
        *,
        is_x: bool,
    ) -> None:
        axis_style = axis.get("style") or {}
        # The axis's own tick_label_color/tick_color is the narrower
        # selector and wins; the chart-wide slot fills in when it says nothing.
        axis_tick_paint = _css(axis_style.get("tick_label_color", axis_style.get("tick_color")), "")
        tick_color = (
            _parse_color(axis_tick_paint)
            if axis_tick_paint
            else slot_paint("tick_label", default_text)
        )
        font_size = slot_font_size(slots.get("tick_label") or {}, _axis_tick_font_size(axis))
        baseline_shift = _axis_tick_label_baseline_shift(axis)
        # An explicit tick_label_anchor (axis spec or style) overrides the
        # side-derived default, matching the browser client and SVG export.
        explicit_anchor = _tick_label_anchor(axis, axis_style, "")
        for side in _axis_tick_label_sides(axis, is_x=is_x):
            side_axis = {**axis, "side": side}
            side_items = _axis_tick_label_layout(side_axis, values, step, axis_scale, is_x)
            # Unstyled defaults reproduce the pre-`tick_label_pad` placement exactly.
            # The bottom gap is 15 here against the SVG exporter's 16: that 1 px has
            # always separated the two and is not this seam's to change.
            if is_x:
                label_offset = (
                    _axis_tick_label_offset(axis, 7.0, 0.2)
                    if side == "top"
                    # Rust Scene uses a 16 px bottom baseline.  The legacy
                    # raster's 15 px default remains for ordinary
                    # compatibility-only figures, but a visibility-switch
                    # fallback must retain the public Scene label position.
                    else _axis_tick_label_offset(
                        axis,
                        16.0 if axis_style.get("_scene_public_chrome_defaults") else 15.0,
                        0.8,
                    )
                )
            else:
                label_offset = _axis_tick_label_offset(axis, 8.0)
            for item in side_items:
                block = _textblock.measure(item["text"], font_size)
                if is_x:
                    row_offset = float(item["row"]) * (font_size + 4)
                    x = float(item["pos"])
                    y = (
                        py0 - label_offset - row_offset
                        if side == "top"
                        else py1 + label_offset + row_offset
                    )
                    angle = float(item["angle"])
                    if explicit_anchor:
                        anchor = _TEXT_ANCHOR_CODES[explicit_anchor]
                    elif angle == 0:
                        anchor = 1
                    elif (side == "bottom" and angle < 0) or (side == "top" and angle > 0):
                        anchor = 2
                    else:
                        anchor = 0
                else:
                    x = px1 + label_offset if side == "right" else px0 - label_offset
                    y = (
                        float(item["pos"])
                        + baseline_shift
                        - (block.line_count - 1) * block.line_step / 2.0
                    )
                    default_anchor = 0 if side == "right" else 2
                    anchor = (
                        _TEXT_ANCHOR_CODES[explicit_anchor] if explicit_anchor else default_anchor
                    )
                _emit_text_block(
                    cmd,
                    x,
                    y,
                    anchor,
                    font_size,
                    tick_color,
                    item["text"],
                    angle=float(item["angle"]),
                )

    if polar is not None:
        _emit_polar_tick_labels(
            cmd,
            polar,
            xlab,
            ylab,
            xstep,
            ystep,
            xa,
            ya,
            slot_font_size(slots.get("tick_label") or {}, _axis_tick_font_size(xa)),
            slot_font_size(slots.get("tick_label") or {}, _axis_tick_font_size(ya)),
            _polar_label_paint(xa, slot_paint, default_text),
            _polar_label_paint(ya, slot_paint, default_text),
            hide_x or xa.get("tick_label_strategy") == "off",
            hide_y or ya.get("tick_label_strategy") == "off",
        )
    else:
        emit_tick_labels(xa, xlab, xstep, sx, is_x=True)
        emit_tick_labels(ya, ylab, ystep, sy, is_x=False)
    for axis_id, axis, axis_scale in extra_x_axes:
        _ticks, tick_labels, step = extra_x_ticks[axis_id]
        emit_tick_labels(axis, tick_labels, step, axis_scale, is_x=True)
    for axis_id, axis, axis_scale in extra_y_axes:
        _ticks, tick_labels, step = extra_y_ticks[axis_id]
        emit_tick_labels(axis, tick_labels, step, axis_scale, is_x=False)
    legacy_title = spec.get("title") if not spec.get("title_options") else None
    # The width layout measured the title band at; wrapping anywhere else would
    # draw more lines than `title_room` reserved (see _svg._title_wrap_width).
    title_wrap_width = plot.get("title_wrap_width")
    if legacy_title:
        title_slot = slots.get("title") or {}
        title_italic, title_bold = _native_font_emphasis(
            {
                "font_style": title_slot.get("font-style"),
                "font_weight": title_slot.get("font-weight", 400),
            }
        )
        legacy_size = slot_font_size(title_slot, 14.0)
        legacy_block = _textblock.measure(legacy_title, legacy_size, max_width=title_wrap_width)
        # Lines run downward from the baseline, so lift the block by its trailing
        # lines: the last line keeps the historical single-line baseline. A
        # one-line title has no trailing lines and emits exactly as before.
        legacy_trailing = (legacy_block.line_count - 1) * legacy_block.line_step
        _emit_text_block(
            cmd,
            width / 2,
            plot["y"] - plot["top_axis_room"] - (10 if compact else 12) - legacy_trailing,
            1,
            legacy_size,
            slot_paint("title", default_text),
            "\n".join(legacy_block.lines),
            italic=title_italic,
            bold=title_bold,
        )
    for title_entry in [] if legacy_title else _title_entries(spec):
        title_style, title_size, title_block = _title_metrics(spec, title_entry, title_wrap_width)
        title_italic, title_bold = _native_font_emphasis(
            {
                "font_style": title_style.get("font-style"),
                # 400 = Matplotlib's `axes.titleweight: normal`; the baked
                # atlas only has a bold face, so anything >= 600 rounds up to
                # it. Mirrors the SVG/browser title default.
                "font_weight": title_style.get("font-weight", 400),
            }
        )
        trailing = (title_block.line_count - 1) * title_block.line_step
        if title_entry.get("automatic_y", True):
            title_anchor_y = plot["y"] - plot["top_axis_room"]
        else:
            title_anchor_y = plot["y"] + (1.0 - float(title_entry.get("y", 1.0))) * plot["h"]
        loc = str(title_entry.get("loc", "center"))
        title_x = {
            "left": plot["x"],
            "center": plot["x"] + plot["w"] / 2.0,
            "right": plot["x"] + plot["w"],
        }.get(loc, plot["x"] + plot["w"] / 2.0)
        _emit_text_block(
            cmd,
            title_x,
            title_anchor_y - float(title_entry.get("pad", 8.0)) - title_block.descent - trailing,
            {"left": 0, "center": 1, "right": 2}.get(loc, 1),
            title_size,
            _parse_color(slot_text_color(title_style, default_text)),
            # The wrapped lines, not the raw string: one long line inside a
            # two-line band is the clipping bug this reservation exists to stop.
            "\n".join(title_block.lines),
            italic=title_italic,
            bold=title_bold,
        )

    def emit_axis_title(axis: dict[str, Any], *, is_x: bool) -> None:
        if not axis.get("label") or _axis_tick_label_strategy(axis) == "none":
            return
        axis_style = axis.get("style") or {}
        geometry = _axis_label_geometry(axis, plot, is_x=is_x)
        anchor = {"start": 0, "middle": 1, "end": 2}[geometry["anchor"]]
        axis_title_slot = slots.get("axis_title") or {}
        italic, bold = _native_font_emphasis(
            {
                "font_style": axis_style.get("label_font_style")
                or axis_title_slot.get("font-style"),
                "font_weight": axis_style.get(
                    "label_font_weight", axis_title_slot.get("font-weight", 400)
                ),
            }
        )
        _emit_text_block(
            cmd,
            float(geometry["x"]),
            float(geometry["y"]),
            anchor,
            slot_font_size(slots.get("axis_title") or {}, float(geometry["font_size"])),
            (
                _parse_color(_css(axis_style.get("label_color"), ""))
                if _css(axis_style.get("label_color"), "")
                else slot_paint("axis_title", default_text)
            ),
            str(axis["label"]),
            angle=float(geometry["angle"]),
            italic=italic,
            bold=bold,
        )

    emit_axis_title(xa, is_x=True)
    emit_axis_title(ya, is_x=False)
    for _axis_id, axis, _axis_scale in extra_x_axes:
        emit_axis_title(axis, is_x=True)
    for _axis_id, axis, _axis_scale in extra_y_axes:
        emit_axis_title(axis, is_x=False)

    named = legend_items(spec["traces"], spec_palette)
    main_legend = spec.get("legend") or {}
    main_items = main_legend.get("items") or named
    show_main_legend = spec.get("show_legend", True) and bool(main_items)
    extra_legends = [(extra, extra.get("items") or []) for extra in spec.get("extra_legends") or []]
    legends: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
    if show_main_legend:
        legends.append((main_items, main_legend))
    legends.extend((items, extra) for extra, items in extra_legends if items)
    # The browser scrolls an oversized legend. Static files cannot, so clip the
    # bounded/truncated equivalent to the plot rectangle. The exemption for an
    # anchored legend (which is placed relative to, and may sit outside, the
    # axes) is scoped per legend exactly as in `_svg.py`: one anchored legend
    # must not lift the clip off its non-anchored siblings. The clip is a
    # stateful raster command, so only emit it on a transition — an
    # all-anchored or all-unanchored figure yields the same stream as before.
    # The clip is the plot rect unioned with any polar legend gutter, which sits
    # outside it — the plot rect alone erased a polar legend. Shared with the
    # SVG clipPath via `legend_clip_rect`.
    lx, ly, lw, lh = legend_clip_rect(plot)
    clipped_to_plot = False
    for items, options in legends:
        want_clip = not options.get("anchor")
        if want_clip != clipped_to_plot:
            if want_clip:
                cmd.clip(lx, ly, lw, lh)
            else:
                cmd.clip(0, 0, width, height)
            clipped_to_plot = want_clip
        # Host seam: tests monkeypatch `_raster._emit_legend`.
        from . import _raster as _host

        _host._emit_legend(
            cmd,
            items,
            plot,
            legend_options_with_slot(spec, options),
            default_text,
            spec_palette,
            slots.get("legend_label") or {},
            slots.get("legend_title") or {},
        )
    if clipped_to_plot:
        cmd.clip(0, 0, width, height)
    if spec.get("colorbar"):
        _emit_colorbar(
            cmd,
            spec["colorbar"],
            plot,
            _colorbar_right_axis_room(ya, extra_y_axes, compact),
            default_text,
            slots.get("colorbar_title") or slots.get("colorbar") or {},
            slots.get("colorbar_tick") or slots.get("colorbar") or {},
        )
