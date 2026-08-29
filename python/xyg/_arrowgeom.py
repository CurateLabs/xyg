"""Arrow-annotation path geometry shared by the SVG and raster exporters.

Admission is ABI 217 ``xyg_arrow_geometry`` / shaft / taper / trim / end
decoration so Python and Node cannot drift. Style keys stay host-parsed:
``curve`` (matplotlib arc3 rad — quadratic bulge as a fraction of chord
length), ``angle_a``/``angle_b`` (matplotlib angle3/angle departure/arrival
angles, degrees, y-up screen space), ``elbow``, ``gap_start``/``gap_end``,
``start_offset`` (an "x,y" px shift), ``label_clear`` (a "left,right,up,down"
px rectangle), ``head_style``/``tail_style`` (``triangle``/``v``/``bar``/
``none``) and ``head_size``.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from . import kernels


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _pack_style(style: dict[str, Any]) -> list[float]:
    packed = [math.nan] * 12
    raw_offset = style.get("start_offset")
    if isinstance(raw_offset, str):
        offset = [_number(part) for part in raw_offset.split(",")]
        if len(offset) == 2 and None not in offset:
            packed[0] = offset[0] if offset[0] is not None else math.nan
            packed[1] = offset[1] if offset[1] is not None else math.nan
    angle_a = _number(style.get("angle_a"))
    angle_b = _number(style.get("angle_b"))
    if angle_a is not None:
        packed[2] = angle_a
    if angle_b is not None:
        packed[3] = angle_b
    curve = _number(style.get("curve"))
    if curve is not None:
        packed[4] = curve
    gap_start = _number(style.get("gap_start"))
    gap_end = _number(style.get("gap_end"))
    if gap_start is not None:
        packed[5] = gap_start
    if gap_end is not None:
        packed[6] = gap_end
    raw_clear = style.get("label_clear")
    if isinstance(raw_clear, str):
        parts = [_number(part) for part in raw_clear.split(",")]
        extents = [part for part in parts if part is not None and part >= 0]
        if len(parts) == 4 and len(extents) == 4:
            packed[7], packed[8], packed[9], packed[10] = extents
    if style.get("elbow"):
        packed[11] = 1.0
    return packed


def _unpack_geom(out: Any) -> dict[str, Any]:
    has_control = float(out[6]) != 0.0
    return {
        "p0": (float(out[0]), float(out[1])),
        "p1": (float(out[2]), float(out[3])),
        "control": (float(out[4]), float(out[5])) if has_control else None,
        "elbow": bool(has_control and float(out[6])),
        "dir0": (float(out[7]), float(out[8])),
        "dir1": (float(out[9]), float(out[10])),
    }


def arrow_geometry(
    x0: float, y0: float, x1: float, y1: float, style: dict[str, Any]
) -> dict[str, Any]:
    packed = _pack_style(style)
    # Elbow is independent of whether a control point resolved.
    out = kernels.arrow_geometry(x0, y0, x1, y1, packed)
    geom = _unpack_geom(out)
    geom["elbow"] = bool(style.get("elbow"))
    return geom


def shaft_points(geom: dict[str, Any], samples: int = 24) -> list[tuple[float, float]]:
    """The shaft as a polyline (quadratic Bézier sampled when curved)."""
    (x0, y0), (x1, y1) = geom["p0"], geom["p1"]
    control = geom["control"]
    cx, cy = (0.0, 0.0) if control is None else control
    xs, ys = kernels.arrow_shaft_points(
        x0, y0, x1, y1, cx, cy, control is not None, bool(geom.get("elbow")), samples
    )
    return [(float(x), float(y)) for x, y in zip(xs, ys, strict=True)]


def end_decoration(
    point: tuple[float, float],
    direction: tuple[float, float],
    end_style: str,
    head: float,
) -> Optional[dict[str, Any]]:
    """One endpoint decoration: {'kind': 'fill'|'stroke', 'points': [...]}.

    ``direction`` is the unit tangent INTO the point; styles mirror matplotlib
    arrowstyles: triangle (filled, "-|>"/fancy), v (open stroke, "->"),
    bar ("|-|" caps), none.
    """
    kind, xs, ys = kernels.arrow_end_decoration(
        point[0], point[1], direction[0], direction[1], end_style, head
    )
    if kind == 0:
        return None
    points = [(float(x), float(y)) for x, y in zip(xs, ys, strict=True)]
    return {"kind": "fill" if kind == 1 else "stroke", "points": points}


def taper_polygon(
    points: list[tuple[float, float]], width_start: float, width_end: float
) -> list[tuple[float, float]]:
    """The shaft polyline as a filled polygon whose width interpolates from
    ``width_start`` to ``width_end`` (matplotlib's fancy/simple/wedge
    arrowstyles are filled tapered shafts, not stroked lines)."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    ox, oy = kernels.arrow_taper_polygon(xs, ys, width_start, width_end)
    return [(float(x), float(y)) for x, y in zip(ox, oy, strict=True)]


def trim_polyline_end(points: list[tuple[float, float]], trim: float) -> list[tuple[float, float]]:
    """The polyline with ``trim`` px of arclength removed from its end."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    ox, oy = kernels.arrow_trim_polyline_end(xs, ys, trim)
    return [(float(x), float(y)) for x, y in zip(ox, oy, strict=True)]


def arrow_shapes(
    x0: float, y0: float, x1: float, y1: float, style: dict[str, Any]
) -> dict[str, Any]:
    """Shaft polyline (or taper polygon) + endpoint decorations for one
    arrow/callout spec."""
    geom = arrow_geometry(x0, y0, x1, y1, style)
    head = max(4.0, _number(style.get("head_size")) or 8.0)
    head_style = str(style.get("head_style") or "triangle")
    shaft = shaft_points(geom)
    width_start = _number(style.get("shaft_width_start"))
    width_end = _number(style.get("shaft_width_end"))
    taper = None
    if width_start is not None or width_end is not None:
        if head_style == "triangle":
            # matplotlib construction: the shaft ends at the head BASE and the
            # head spans base→tip — a full-length shaft would swallow the head.
            shaft = trim_polyline_end(shaft, head * math.cos(math.pi / 6))
        taper = taper_polygon(shaft, width_start or 1.0, width_end or 1.0)
    return {
        "shaft": None if taper else shaft,
        "taper": taper,
        "head": end_decoration(geom["p1"], geom["dir1"], head_style, head),
        "tail": end_decoration(
            geom["p0"], geom["dir0"], str(style.get("tail_style") or "none"), head
        ),
    }
