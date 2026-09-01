"""Shared static-export SVG text, escape, and stroke-attribute helpers."""

from __future__ import annotations

from typing import Any

from . import _fontmetrics, _textblock
from ._export_chrome import _AXIS_GRID_DASHES
from ._fontmetrics import estimated_text_width as _estimated_text_width
from ._paint import box_corner_radius as _box_corner_radius
from ._paint import px_size as _px_size


def escape(data: str, entities: dict[str, str] | None = None) -> str:
    """Escape ``&``, ``<`` and ``>`` in a string of data.

    Byte-for-byte equivalent to :func:`xml.sax.saxutils.escape`, vendored so a
    static export does not import it. That one function costs ~7.5 ms of cold
    start: ``xml.sax.saxutils`` pulls in ``urllib.request``, which pulls in
    ``http.client``, ``ssl``, ``socket`` and the whole ``email`` package — 35+
    modules for three ``str.replace`` calls. Nothing else in xy needs them, and
    a cold ``to_png`` at 10M points spent more time on that import than on
    binning ten million points.

    ``tests/test_svg_escape.py`` differentially fuzzes this against the stdlib
    so it cannot drift.
    """
    # must do ampersand first
    data = data.replace("&", "&amp;")
    data = data.replace(">", "&gt;")
    data = data.replace("<", "&lt;")
    if entities:
        for key, value in entities.items():
            data = data.replace(key, value)
    return data


def _escape_attr(data: Any) -> str:
    """Escape arbitrary text for a double-quoted XML attribute."""
    return escape(str(data), {'"': "&quot;"})


def _num(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _slot_size_attr(style: dict[str, Any]) -> str:
    """` font-size="N"` only when the slot asks for one. Text that inherits the
    root `font-size` must keep inheriting it when unstyled, so that existing
    output stays byte-identical."""
    if "font-size" not in style:
        return ""
    return f' font-size="{_num(_px_size(style["font-size"], 11.0))}"'


def slot_text_attrs(style: dict[str, Any], **defaults: Any) -> str:
    """Extra SVG `<text>` attributes for a slot's non-paint text properties.

    `font-size` and the paint are resolved by the caller (they have per-slot
    defaults and feed the raster writer too); this covers the rest, which map
    one-to-one onto SVG presentation attributes. `defaults` carries the
    writer's own values under their Python spelling (`font_weight="600"`) and
    each is emitted exactly once — a repeated attribute is malformed XML, and
    the parser would keep the first, silently discarding the author's.
    """
    parts: list[str] = []
    for prop in ("font-weight", "font-style", "font-family", "letter-spacing", "opacity"):
        value = style.get(prop, defaults.get(prop.replace("-", "_")))
        if value is None:
            continue
        if prop == "letter-spacing" and not isinstance(value, str):
            value = _num(_px_size(value, 0.0))
        # `_escape_attr`, not `escape`: a font-family stack quotes any name with
        # a space (`"Times New Roman", serif`), and a bare `"` closes the
        # attribute and breaks the document.
        parts.append(f' {prop}="{_escape_attr(value)}"')
    return "".join(parts)


def _axis_grid_attrs(style: dict[str, Any]) -> str:
    opacity = float(style.get("grid_opacity", 1.0))
    dash = _AXIS_GRID_DASHES.get(str(style.get("grid_dash", "solid")))
    return (f' stroke-opacity="{_num(opacity)}"' if opacity < 1 else "") + (
        f' stroke-dasharray="{",".join(_num(value) for value in dash)}"' if dash else ""
    )


def _cap_join_attrs(style: dict[str, Any], *, join: bool = True) -> str:
    """Polyline stroke geometry, always written out rather than inherited.

    SVG's initial values are `butt`/`miter`; XYG's are `round`/`round`, and the
    trace only carries `linecap` when it differs (`marks._stroke_geometry`).
    The join is not selectable, but it is still named on every stroked path:
    leaving it out let the format's `miter` default through, and `_pdf` reads
    these attributes straight back out of this markup, so an unnamed join meant
    SVG and PDF disagreeing with the rasterizer for free.
    """
    cap = style.get("linecap", "round")
    attrs = f' stroke-linecap="{escape(str(cap))}"'
    if join:
        attrs = ' stroke-linejoin="round"' + attrs
    return attrs


def _dash_attr(style: dict[str, Any]) -> str:
    dash = style.get("dash")
    if not dash:
        return ""
    if isinstance(dash, str):
        dash = dash.split(",")
    return f' stroke-dasharray="{",".join(_num(float(v)) for v in dash)}"'


def _text_cell(font_size: float) -> tuple[float, float]:
    """(ascent, descent) in px of the core's DejaVu face at `font_size`."""
    return (
        font_size * _fontmetrics.ASCENT / _fontmetrics.BASE_PX,
        font_size * _fontmetrics.DESCENT / _fontmetrics.BASE_PX,
    )


def _text_block_content(text: object, x: float, line_step: float) -> str:
    """SVG text children for the shared newline-delimited block geometry."""
    split = _textblock.split_lines(text)
    if len(split) == 1:
        # Keep ordinary text as a direct text node.  Besides producing the
        # smallest SVG, the PDF exporter consumes these nodes as vector text
        # and existing callers intentionally inspect ``Element.text``.
        return escape(split[0])
    lines = []
    for index, line in enumerate(split):
        dy = f' dy="{_num(line_step)}"' if index else ""
        lines.append(f'<tspan x="{_num(x)}"{dy}>{escape(line)}</tspan>')
    return "".join(lines)


def _svg_font_attrs(style: dict[str, Any]) -> str:
    attrs = []
    for key, attribute in (
        ("font_family", "font-family"),
        ("font_weight", "font-weight"),
        ("font_style", "font-style"),
    ):
        if style.get(key) is not None:
            attrs.append(f' {attribute}="{escape(str(style[key]))}"')
    return "".join(attrs)


def _svg_mathtext_spans(line: str, style: dict[str, Any], offset: int) -> str:
    ranges: list[tuple[int, int]] = []
    for item in str(style.get("math_italic_ranges", "")).split(","):
        try:
            start, end = (int(value) for value in item.split(":", 1))
        except ValueError:
            continue
        start, end = max(0, start - offset), min(len(line), end - offset)
        if start < end:
            ranges.append((start, end))
    if not ranges:
        return escape(line)
    ranges.sort()
    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            previous_start, previous_end = merged[-1]
            merged[-1] = previous_start, max(previous_end, end)
        else:
            merged.append((start, end))
    out: list[str] = []
    cursor = 0
    for start, end in merged:
        start = max(start, cursor)
        if start >= end:
            continue
        if cursor < start:
            out.append(escape(line[cursor:start]))
        out.append(f'<tspan font-style="italic">{escape(line[start:end])}</tspan>')
        cursor = end
    out.append(escape(line[cursor:]))
    return "".join(out)


def _svg_text_box(
    style: dict[str, Any],
    lines: list[str],
    x: float,
    first_y: float,
    line_height: float,
    font_size: float,
    anchor: str,
) -> list[str]:
    """SVG counterpart of the pyplot text-bbox CSS approximation."""
    background = style.get("background")
    border = str(style.get("border", ""))
    if background is None and not border:
        return []
    pad_parts = str(style.get("padding", "0")).split()

    def px(value: str) -> float:
        try:
            return max(0.0, float(value.removesuffix("px")))
        except ValueError:
            return 0.0

    pad_y = px(pad_parts[0]) if pad_parts else 0.0
    pad_x = px(pad_parts[1]) if len(pad_parts) > 1 else pad_y
    text_width = _estimated_text_width(lines, font_size)
    left = (
        x
        - (text_width / 2 if anchor == "middle" else text_width if anchor == "end" else 0.0)
        - pad_x
    )
    top = first_y - font_size * 0.8 - pad_y
    height = font_size + (len(lines) - 1) * line_height + pad_y * 2
    fill = "none" if background is None else escape(str(background))
    stroke = "none"
    stroke_width = 0.0
    if border:
        parts = border.split()
        stroke = escape(parts[-1])
        try:
            stroke_width = max(0.0, float(parts[0].removesuffix("px")))
        except (IndexError, ValueError):
            stroke_width = 1.0
    # `boxstyle="round"`/`round4` set border_radius; the browser gets it as CSS
    # border-radius, so the exporters have to round the same corners or an
    # exported box is square where the live one is not.
    radius = _box_corner_radius(style, text_width + pad_x * 2, height)
    radius_attr = f' rx="{_num(radius)}"' if radius > 0 else ""
    return [
        f'<rect x="{_num(left)}" y="{_num(top)}" '
        f'width="{_num(text_width + pad_x * 2)}" height="{_num(height)}"{radius_attr} '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{_num(stroke_width)}"/>'
    ]
