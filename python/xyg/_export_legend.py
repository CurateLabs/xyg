"""Shared static-export legend row expansion and box layout helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from . import _native
from . import channels as _channels
from ._fontmetrics import text_width as _fontmetrics_text_width
from ._paint import rgba8_hex as _rgba8_hex
from .config import DEFAULT_PALETTE

#: Font size the legend emitters set labels at, and the size at which
#: ``_LEGEND_CHAR_WIDTH`` is the nominal *average* advance.
_LEGEND_CHAR_WIDTH = 6.2
_LEGEND_FONT_PX = 11.0
#: Exact-fit comparisons are made against a measured float sum, so absorb the
#: binary-float underflow at the boundary rather than ellipsizing a label that
#: fits to the last subpixel.
_LEGEND_FIT_EPS = 1e-9


def _legend_font_size(style: dict[str, Any]) -> float:
    """Resolve the bounded pixel font size used by static legend geometry."""
    value = str(style.get("fontSize", "")).strip()
    if value.endswith("px"):
        try:
            return max(1.0, float(value[:-2]))
        except ValueError:
            pass
    return 11.0


def _legend_em(style: dict[str, Any], key: str, default: float) -> float:
    value = str(style.get(key, "")).strip()
    if value.endswith("em"):
        try:
            return max(0.0, float(value[:-2]))
        except ValueError:
            pass
    return default


def _legend_text_width(value: Any, char_width: float = _LEGEND_CHAR_WIDTH) -> float:
    """Measured advance width, in pixels, of a static legend string.

    Legend columns used to be sized as ``len(text) * _LEGEND_CHAR_WIDTH``. A
    flat average cannot bound a proportional face — DejaVu's ``m`` is over
    three times the width of its ``l`` — so ``"gamma"`` really sets 42.6 px at
    11 px against a 31.0 px estimate, and a frame sized from the estimate was
    narrower than its own labels. Advances come from the same face the native
    rasterizer blits (``_fontmetrics``, generated beside ``crates/xyg-engine/src/font.rs`` by
    ``scripts/gen_font.py``), which is what makes a frame sized from this
    actually contain the text the SVG and raster emitters draw. It is also what
    the browser does natively, sizing each legend column to ``max-content``.

    ``char_width`` carries the nominal average advance, so scaling the legend
    font scales the measurement with it.

    A codepoint the atlas lacks reserves the nominal ``char_width`` instead of
    the rasterizer's zero advance: SVG resolves it against the viewer's own
    fonts and does paint it, and over-reserving only widens the frame, which
    can never spill a label.
    """
    font_size = char_width * (_LEGEND_FONT_PX / _LEGEND_CHAR_WIDTH)
    return _fontmetrics_text_width(value, font_size, missing_advance=char_width)


def _legend_text(value: Any, max_width: float, char_width: float = _LEGEND_CHAR_WIDTH) -> str:
    """Conservatively ellipsize a static legend string to a pixel budget.

    The budget is measured, not counted, so the returned string's own advance
    width is ``<= max_width`` and therefore fits the column it was sized for.
    """
    text = str(value)
    if _legend_text_width(text, char_width) <= max_width + _LEGEND_FIT_EPS:
        return text
    # Longest prefix that still leaves room for the ellipsis.
    keep = 0
    for index in range(1, len(text)):
        if _legend_text_width(f"{text[:index]}...", char_width) > max_width + _LEGEND_FIT_EPS:
            break
        keep = index
    if keep:
        return f"{text[:keep]}..."
    # Too narrow for even one glyph plus an ellipsis: emit the dots that fit.
    for count in (3, 2, 1):
        if _legend_text_width("." * count, char_width) <= max_width + _LEGEND_FIT_EPS:
            return "." * count
    return ""


def legend_items(traces: list[dict], palette: Sequence[str] = DEFAULT_PALETTE) -> list[dict]:
    """Legend rows for a trace list — shared by the SVG and raster exporters.

    A categorical `color=` channel is ONE trace carrying N categories, so the
    old `[t for t in traces if t.get("name")]` drew a single row bearing the
    trace's name and the trace's constant color: a legend that actively
    misdescribed the picture beside it. Expand those into one row per category,
    exactly as `ChartView._legend` does for the live client."""
    items: list[dict] = []
    for trace in traces:
        style = dict(trace.get("style") or {})
        use_trace_size = bool(style.pop("_legend_trace_size", False))
        size = trace.get("size") or {}
        if trace.get("kind") == "scatter" and use_trace_size and size.get("mode") == "constant":
            style["size"] = float(size.get("size", 8.0))
        color = trace.get("color") or {}
        if color.get("mode") == "categorical":
            categories = color.get("categories") or []
            entry_palette = list(color.get("palette") or palette) or list(palette)
            rows = _channels.palette_rows_rgba8(entry_palette, len(entry_palette))
            for index, category in enumerate(categories):
                item_style = dict(style)
                item_style["color"] = _rgba8_hex(rows[index % len(rows)])
                items.append(
                    {"name": str(category), "kind": trace.get("kind"), "style": item_style}
                )
        elif trace.get("name"):
            item = dict(trace)
            item["style"] = style
            items.append(item)
    return items


def legend_clip_rect(plot: dict) -> tuple[float, float, float, float]:
    """Rect that bounds a static legend: the plot, union any polar gutter.

    A polar legend lives in a `legend_box_*` gutter OUTSIDE the plot rect
    (`_recut_polar_plot`), so clipping a legend to the plot rect alone erases it
    entirely. Union, not replacement: the same rect still bounds in-plot chrome.
    Shared so the SVG clipPath and the raster clip command cannot drift.
    """
    x0, y0 = float(plot["x"]), float(plot["y"])
    x1, y1 = x0 + float(plot["w"]), y0 + float(plot["h"])
    if "legend_box_w" in plot:
        x0 = min(x0, float(plot["legend_box_x"]))
        y0 = min(y0, float(plot["legend_box_y"]))
        x1 = max(x1, float(plot["legend_box_x"]) + float(plot["legend_box_w"]))
        y1 = max(y1, float(plot["legend_box_y"]) + float(plot["legend_box_h"]))
    return x0, y0, x1 - x0, y1 - y0


def _legend_layout(named: list[dict], plot: dict, options: dict) -> dict[str, Any]:
    """Thin packer over Rust static legend box packing (ABI 124).

    Hosts still resolve CSS font-size / em paddings and pack entry strings.
    Column sizing, measured ellipsis, and loc / bbox-to-anchor placement live
    in ``legend_layout.rs`` so SVG, raster, and Node cannot drift.
    """
    if "legend_box_w" in plot:
        plot = {
            **plot,
            "x": plot["legend_box_x"],
            "y": plot["legend_box_y"],
            "w": plot["legend_box_w"],
            "h": plot["legend_box_h"],
        }
    style_opts = options.get("style") or {}
    font_size = _legend_font_size(style_opts)
    raw_title = options.get("title")
    raw_anchor = options.get("anchor")
    laid = _native.scene_legend_box_layout(
        plot=plot,
        names=[str(item.get("name", "")) for item in named],
        title=str(raw_title) if raw_title else None,
        loc=str(options.get("loc") or "upper right"),
        font_size=font_size,
        handlelength=options.get("handlelength"),
        handletextpad=options.get("handletextpad"),
        handleheight=options.get("handleheight"),
        ncols=max(1, int(options.get("ncols", 1))),
        padding_em=_legend_em(style_opts, "padding", 0.4),
        row_gap_em=_legend_em(style_opts, "rowGap", 0.5),
        anchor=raw_anchor if raw_anchor is not None and len(raw_anchor) in (2, 4) else None,
        border_axes_pad=max(0.0, float(options.get("border_pad", 0.0) or 0.0)),
    )
    laid["style"] = style_opts
    return laid
