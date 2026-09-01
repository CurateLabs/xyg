"""Shared static-export SVG chrome text (titles, axis labels, legends)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from . import _textblock
from ._export_annotations import _axis_label_geometry
from ._export_chrome import (
    legend_options_with_slot,
    slot_font_size,
    slot_text_color,
)
from ._export_colorbar_svg import _colorbar
from ._export_layout import _title_entries, _title_metrics
from ._export_legend import legend_items
from ._export_legend_svg import _legend
from ._export_svg_util import _escape_attr, _num, _text_block_content, escape, slot_text_attrs
from ._export_ticks import _axis_tick_label_strategy, _colorbar_right_axis_room
from ._paint import _css


def _svg_chrome(
    spec: dict[str, Any],
    plot: dict[str, float],
    width: float,
    xa: dict[str, Any],
    ya: dict[str, Any],
    extra_x_axes: list[tuple[str, dict[str, Any], object]],
    extra_y_axes: list[tuple[str, dict[str, Any], object]],
    *,
    compact: bool,
    clip_id: str,
    default_text: str,
    spec_palette: Sequence[str],
    slots: dict[str, dict[str, Any]],
) -> list[str]:
    chrome: list[str] = []
    legacy_title = spec.get("title") if not spec.get("title_options") else None
    title_wrap_width = plot.get("title_wrap_width")
    if legacy_title:
        title_slot = slots.get("title") or {}
        legacy_size = slot_font_size(title_slot, 14.0)
        legacy_block = _textblock.measure(legacy_title, legacy_size, max_width=title_wrap_width)
        # Wrapped lines run downward from the baseline, so lift the block by its
        # trailing lines: the LAST line keeps the historical single-line baseline
        # and the extra lines fill the room `_title_room` reserved above it. A
        # one-line title has no trailing lines and is byte-identical to before.
        legacy_trailing = (legacy_block.line_count - 1) * legacy_block.line_step
        legacy_y = plot["y"] - plot["top_axis_room"] - (10 if compact else 12) - legacy_trailing
        legacy_x = width / 2
        legacy_text = "\n".join(legacy_block.lines)
        legacy_content = _text_block_content(legacy_text, legacy_x, legacy_block.line_step)
        chrome.append(
            f'<text x="{_num(legacy_x)}" '
            f'y="{_num(legacy_y)}" '
            f'text-anchor="middle" font-size="{_num(legacy_size)}"'
            f"{slot_text_attrs(title_slot, font_weight='400')} "
            f'fill="{escape(slot_text_color(title_slot, default_text))}">'
            f"{legacy_content}</text>"
        )
    for title_entry in [] if legacy_title else _title_entries(spec):
        title_style, title_size, title_block = _title_metrics(spec, title_entry, title_wrap_width)
        # Matplotlib's `axes.titleweight`/`axes.labelweight` both default to
        # "normal", so chrome text stays at 400 unless a style or rcParam asks
        # for more. Keep this in step with the `title`/`axis_title` slot rules
        # in js/src/20_theme.ts and the raster defaults in _raster.py.
        title_font_attrs = slot_text_attrs(title_style, font_weight="400")
        trailing = (title_block.line_count - 1) * title_block.line_step
        if title_entry.get("automatic_y", True):
            title_anchor_y = plot["y"] - plot["top_axis_room"]
        else:
            title_anchor_y = plot["y"] + (1.0 - float(title_entry.get("y", 1.0))) * plot["h"]
        title_y = (
            title_anchor_y - float(title_entry.get("pad", 8.0)) - title_block.descent - trailing
        )
        loc = str(title_entry.get("loc", "center"))
        title_x = {
            "left": plot["x"],
            "center": plot["x"] + plot["w"] / 2.0,
            "right": plot["x"] + plot["w"],
        }.get(loc, plot["x"] + plot["w"] / 2.0)
        anchor = {"left": "start", "center": "middle", "right": "end"}.get(loc, "middle")
        # `title_block.lines` is the wrapped set — drawing `entry["text"]` here
        # would put the whole title on one line inside a band reserved for two.
        title_content = _text_block_content(
            "\n".join(title_block.lines), title_x, title_block.line_step
        )
        chrome.append(
            f'<text x="{_num(title_x)}" '
            f'y="{_num(title_y)}" '
            f'text-anchor="{anchor}" font-size="{_num(title_size)}" '
            f"{title_font_attrs.lstrip()} "
            f'fill="{escape(slot_text_color(title_style, default_text))}">'
            f"{title_content}</text>"
        )

    def append_axis_title(axis: dict[str, Any], *, is_x: bool) -> None:
        if not axis.get("label") or _axis_tick_label_strategy(axis) == "none":
            return
        axis_style = axis.get("style") or {}
        slot = slots.get("axis_title") or {}
        geometry = _axis_label_geometry(axis, plot, is_x=is_x)
        x, y = float(geometry["x"]), float(geometry["y"])
        angle = float(geometry["angle"])
        transform = f' transform="rotate({_num(angle)} {_num(x)} {_num(y)})"' if angle else ""
        # The axis's own label_* keys are the narrower selector, so they win
        # over the chart-wide slot; the slot supplies whatever they leave unset.
        family = axis_style.get("label_font_family")
        font_style = axis_style.get("label_font_style")
        weight = axis_style.get("label_font_weight", 400)
        paint = _css(axis_style.get("label_color"), "") or slot_text_color(slot, default_text)
        font_attrs = (f' font-family="{_escape_attr(family)}"' if family is not None else "") + (
            f' font-style="{_escape_attr(font_style)}"' if font_style is not None else ""
        )
        if not font_attrs:
            font_attrs = slot_text_attrs(slot, font_weight=weight)
        else:
            font_attrs = f' font-weight="{_escape_attr(weight)}"' + font_attrs
        font_size = slot_font_size(slot, float(geometry["font_size"]))
        block = _textblock.measure(axis["label"], font_size)
        chrome.append(
            f'<text x="{_num(x)}" y="{_num(y)}" text-anchor="{geometry["anchor"]}" '
            f'font-size="{_num(font_size)}"'
            f"{font_attrs} "
            f'fill="{escape(paint)}"{transform}>'
            f"{_text_block_content(axis['label'], x, block.line_step)}</text>"
        )

    append_axis_title(xa, is_x=True)
    append_axis_title(ya, is_x=False)
    for _axis_id, axis, _axis_scale in extra_x_axes:
        append_axis_title(axis, is_x=True)
    for _axis_id, axis, _axis_scale in extra_y_axes:
        append_axis_title(axis, is_x=False)
    named = legend_items(spec["traces"], spec_palette)
    legend_label_slot = slots.get("legend_label") or {}
    legend_title_slot = slots.get("legend_title") or {}
    main_legend = spec.get("legend") or {}
    main_items = main_legend.get("items") or named
    if spec.get("show_legend", True) and main_items:
        chrome.append(
            _legend(
                main_items,
                plot,
                legend_options_with_slot(spec, main_legend),
                clip_id,
                default_text,
                spec_palette,
                legend_label_slot,
                legend_title_slot,
            )
        )
    for extra in spec.get("extra_legends") or []:
        items = extra.get("items") or []
        if items:
            chrome.append(
                _legend(
                    items,
                    plot,
                    legend_options_with_slot(spec, extra),
                    clip_id,
                    default_text,
                    spec_palette,
                    legend_label_slot,
                    legend_title_slot,
                )
            )
    if spec.get("colorbar"):
        chrome.append(
            _colorbar(
                spec["colorbar"],
                plot,
                _colorbar_right_axis_room(ya, extra_y_axes, compact),
                default_text,
                slots.get("colorbar_title") or slots.get("colorbar") or {},
                slots.get("colorbar_tick") or slots.get("colorbar") or {},
            )
        )

    return chrome
