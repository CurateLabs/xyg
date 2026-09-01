"""Shared static-export annotation SVG emit helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from ._arrowgeom import arrow_shapes as _arrow_shapes
from ._export_annotations import (
    _annotation_connector_unclipped,
    _annotation_first_baseline,
    annotation_label_placement,
)
from ._export_marker_svg import _SYMBOL_BUILDERS
from ._export_svg_util import (
    _dash_attr,
    _num,
    _svg_font_attrs,
    _svg_mathtext_spans,
    _svg_text_box,
    escape,
)
from ._paint import _css
from ._paint import px_size as _px_size

if TYPE_CHECKING:
    from ._layout import _PolarProjection


def _annotation_svg(
    annotations: Sequence[dict[str, Any]],
    sx: Callable[[float], float],
    sy: Callable[[float], float],
    plot: dict[str, float],
    width: float,
    height: float,
    polar: "Optional[_PolarProjection]" = None,
) -> tuple[list[str], list[str], list[str]]:
    marks: list[str] = []
    unclipped_marks: list[str] = []
    labels: list[str] = []
    px0, py0 = plot["x"], plot["y"]

    def point(x: float, y: float) -> tuple[float, float]:
        """A point-anchored annotation's position.

        Under polar the pair is (theta, r) and must project jointly — the
        separable sx/sy would read them as cartesian, putting `(0, 0)` (the
        disc centre, at any angle) in the bottom-left corner instead.

        Only point-anchored kinds route through here. `rule` and `band` are
        genuinely different geometry on a disc — a theta rule is a spoke, an r
        rule is a ring, a band is an annulus or a sector — and stay deferred
        (polar-axes.md §9) rather than being drawn as straight cartesian bars.
        """
        if polar is not None:
            px, py = polar(x, y)
            return float(px), float(py)
        return float(sx(x)), float(sy(y))

    for ann in annotations:
        style = ann.get("style") or {}
        color = escape(_css(style.get("color"), "#667085"))
        opacity = float(style.get("opacity", 1.0))
        start = max(0.0, min(1.0, float(style.get("span_start", 0.0))))
        end = max(start, min(1.0, float(style.get("span_end", 1.0))))
        kind = ann.get("kind")
        if kind == "rule":
            if ann.get("axis") == "x":
                pos = float(sx(float(ann["value"])))
                coords = (pos, py0 + (1 - end) * plot["h"], pos, py0 + (1 - start) * plot["h"])
            else:
                pos = float(sy(float(ann["value"])))
                coords = (px0 + start * plot["w"], pos, px0 + end * plot["w"], pos)
            marks.append(
                f'<line x1="{_num(coords[0])}" y1="{_num(coords[1])}" '
                f'x2="{_num(coords[2])}" y2="{_num(coords[3])}" stroke="{color}" '
                f'stroke-width="{_num(float(style.get("width", 1.5)))}" stroke-opacity="{_num(opacity)}"'
                f"{_dash_attr(style)}/>"
            )
        elif kind == "band":
            a, b = float(ann["start"]), float(ann["end"])
            if ann.get("axis") == "x":
                x0, x1 = sorted((float(sx(a)), float(sx(b))))
                y0, y1 = py0 + (1 - end) * plot["h"], py0 + (1 - start) * plot["h"]
            else:
                y0, y1 = sorted((float(sy(a)), float(sy(b))))
                x0, x1 = px0 + start * plot["w"], px0 + end * plot["w"]
            marks.append(
                f'<rect x="{_num(x0)}" y="{_num(y0)}" width="{_num(x1 - x0)}" '
                f'height="{_num(y1 - y0)}" fill="{color}" fill-opacity="{_num(float(style.get("opacity", 0.14)))}"/>'
            )
        elif kind in ("arrow", "callout"):
            connector_marks = (
                unclipped_marks
                if _annotation_connector_unclipped(ann, sx, sy, plot, polar)
                else marks
            )
            if kind == "arrow":
                x0, y0 = point(float(ann["x0"]), float(ann["y0"]))
                x1, y1 = point(float(ann["x1"]), float(ann["y1"]))
            else:  # pointer from the offset label back to the data point
                x1, y1 = point(float(ann["x"]), float(ann["y"]))
                x0, y0 = x1 + float(ann.get("dx", 0.0)), y1 + float(ann.get("dy", 0.0))
            if all(np.isfinite(v) for v in (x0, y0, x1, y1)):
                shapes = _arrow_shapes(x0, y0, x1, y1, style)
                stroke_width = _num(max(0.5, float(style.get("width", 1.5))))
                if shapes["taper"] is not None:
                    taper = " ".join(f"{_num(px)},{_num(py)}" for px, py in shapes["taper"])
                    connector_marks.append(
                        f'<polygon points="{taper}" fill="{color}" fill-opacity="{_num(opacity)}"/>'
                    )
                else:
                    shaft = " ".join(f"{_num(px)},{_num(py)}" for px, py in shapes["shaft"])
                    connector_marks.append(
                        f'<polyline points="{shaft}" fill="none" '
                        f'stroke="{color}" stroke-width="{stroke_width}" '
                        f'stroke-opacity="{_num(opacity)}"{_dash_attr(style)}/>'
                    )
                for decoration in (shapes["head"], shapes["tail"]):
                    if decoration is None:
                        continue
                    points = " ".join(f"{_num(px)},{_num(py)}" for px, py in decoration["points"])
                    if decoration["kind"] == "fill":
                        connector_marks.append(
                            f'<polygon points="{points}" fill="{color}" '
                            f'fill-opacity="{_num(opacity)}"/>'
                        )
                    else:
                        connector_marks.append(
                            f'<polyline points="{points}" fill="none" stroke="{color}" '
                            f'stroke-width="{stroke_width}" stroke-opacity="{_num(opacity)}"/>'
                        )
        elif kind == "marker":
            mx, my = point(float(ann["x"]), float(ann["y"]))
            if all(np.isfinite(v) for v in (mx, my)):
                radius = max(0.5, float(ann.get("size", 8.0)) / 2.0)
                builder = _SYMBOL_BUILDERS.get(str(ann.get("symbol", "circle")))
                stroke_w = float(style.get("stroke_width", 0.0))
                stroke_attr = (
                    f' stroke="{escape(_css(style.get("stroke_color"), color))}"'
                    f' stroke-width="{_num(stroke_w)}"'
                    + (f' stroke-opacity="{_num(opacity)}"' if opacity < 1 else "")
                    if stroke_w
                    else ""
                )
                fill = escape(_css(style.get("color"), "#2563eb"))
                shape = (
                    f'<circle cx="{_num(mx)}" cy="{_num(my)}" r="{_num(radius)}"'
                    if builder is None
                    else builder(mx, my, radius)
                )
                marks.append(f'{shape} fill="{fill}" fill-opacity="{_num(opacity)}"{stroke_attr}/>')
        if ann.get("text"):
            tx, ty, label_anchor, vertical_align = annotation_label_placement(
                ann, style, sx, sy, plot, width, height, polar
            )
            if not (np.isfinite(tx) and np.isfinite(ty)):
                continue
            style = {**style, "vertical_align": vertical_align} if vertical_align else style
            anchor = {"start": "start", "middle": "middle", "end": "end"}.get(label_anchor, "start")
            font_size = _px_size(style.get("font_size"), 11.0)
            lines = str(ann["text"]).splitlines() or [""]
            line_height = font_size * 1.2
            rotation = float(style.get("rotation", 0.0)) % 360.0
            if rotation in (90.0, 270.0):
                # Vertical text, mirroring the native rasterizer's geometry:
                # vertical_align anchors along the reading axis, the horizontal
                # anchor shifts the baseline across the post-rotation box.
                cw = rotation == 270.0
                va = str(style.get("vertical_align", ""))
                along = {
                    "center": "middle",
                    "top": "start" if cw else "end",
                    "bottom": "end" if cw else "start",
                }.get(va, "start")
                ascent, descent = font_size * 0.78, font_size * 0.22
                if cw:
                    base = {"middle": (descent - ascent) / 2, "end": -ascent}.get(anchor, descent)
                else:
                    base = {"middle": (ascent - descent) / 2, "end": -descent}.get(anchor, ascent)
                stack = -line_height if cw else line_height  # later lines: glyph-down
                by = ty + float(ann.get("dy", 0))
                text_opacity = float(
                    style.get(
                        "label_opacity",
                        style.get("opacity", 1.0) if kind == "text" else 1.0,
                    )
                )
                line_offset = 0
                for index, line in enumerate(lines):
                    bx = tx + float(ann.get("dx", 0)) + base + index * stack
                    styled_line = _svg_mathtext_spans(line, style, line_offset)
                    labels.append(
                        f'<text text-anchor="{along}" font-size="{_num(font_size)}" '
                        f'transform="rotate({90 if cw else -90} {_num(bx)} {_num(by)})" '
                        f'x="{_num(bx)}" y="{_num(by)}" '
                        + (f'fill-opacity="{_num(text_opacity)}" ' if text_opacity < 1 else "")
                        + f'fill="{color}">{styled_line}</text>'
                    )
                    line_offset += len(line) + 1
                continue
            x_text = tx + float(ann.get("dx", 0))
            vertical_align = style.get("vertical_align")
            y_text = _annotation_first_baseline(
                ty + float(ann.get("dy", 0)),
                len(lines),
                line_height,
                font_size,
                vertical_align,
            )
            line_offset = 0
            tspan_parts = []
            for index, line in enumerate(lines):
                styled_line = _svg_mathtext_spans(line, style, line_offset)
                tspan_parts.append(
                    f'<tspan x="{_num(x_text)}" y="{_num(y_text + index * line_height)}">'
                    f"{styled_line}</tspan>"
                )
                line_offset += len(line) + 1
            tspans = "".join(tspan_parts)
            text_opacity = float(
                style.get(
                    "label_opacity",
                    style.get("opacity", 1.0) if kind == "text" else 1.0,
                )
            )
            # A callout's `color` paints its arrow; the label prefers its own.
            label_color = escape(_css(style.get("label_color"), "")) or color
            labels.extend(
                _svg_text_box(style, lines, x_text, y_text, line_height, font_size, anchor)
            )
            font_attrs = _svg_font_attrs(style)
            rotation_attr = (
                f' transform="rotate({_num(-rotation)} {_num(x_text)} {_num(y_text)})"'
                if rotation
                else ""
            )
            labels.append(
                f'<text text-anchor="{anchor}" font-size="{_num(font_size)}"{font_attrs}'
                f"{rotation_attr} "
                + (f'fill-opacity="{_num(text_opacity)}" ' if text_opacity < 1 else "")
                + f'fill="{label_color}">{tspans}</text>'
            )
    return marks, unclipped_marks, labels
