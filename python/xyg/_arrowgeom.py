"""Arrow-annotation path geometry shared by the SVG and raster exporters.

Admission is ABI 217 ``xyg_arrow_geometry`` / shaft / taper / trim / end
decoration so Python and Node cannot drift. ABI 254 ``xyg_arrow_style_pack``
owns comma-separated ``start_offset`` / ``label_clear`` packing. ABI 257
``xyg_arrow_shapes`` owns shaft/taper/head/tail orchestration for compat
exporters. ChartView ``51_annotations.ts`` keeps the same CSV parse until WASM.
Hosts still coerce style keys and elbow truthiness. Remaining host-only keys:
``curve`` (matplotlib arc3 rad — quadratic bulge as a fraction of chord length),
``angle_a``/``angle_b`` (matplotlib angle3/angle departure/arrival angles,
degrees, y-up screen space), ``elbow``, ``gap_start``/``gap_end``, ``head_style``/
``tail_style`` (``triangle``/``v``/``bar``/``none``) and ``head_size``.
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


def _finite_or_nan(value: Any) -> float:
    number = _number(value)
    return math.nan if number is None else number


def _pack_style(style: dict[str, Any]) -> list[float]:
    raw_offset = style.get("start_offset")
    raw_clear = style.get("label_clear")
    packed = kernels.arrow_style_pack(
        raw_offset if isinstance(raw_offset, str) else None,
        _finite_or_nan(style.get("angle_a")),
        _finite_or_nan(style.get("angle_b")),
        _finite_or_nan(style.get("curve")),
        _finite_or_nan(style.get("gap_start")),
        _finite_or_nan(style.get("gap_end")),
        raw_clear if isinstance(raw_clear, str) else None,
        1.0 if style.get("elbow") else math.nan,
    )
    return [float(value) for value in packed]


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


def _point_pairs(xs: Any, ys: Any, start: int, count: int) -> list[tuple[float, float]]:
    return [
        (float(x), float(y))
        for x, y in zip(xs[start : start + count], ys[start : start + count], strict=True)
    ]


def _decoration_from_meta(
    kind: int, xs: Any, ys: Any, start: int, count: int
) -> Optional[dict[str, Any]]:
    if kind == 0 or count == 0:
        return None
    return {
        "kind": "fill" if kind == 1 else "stroke",
        "points": _point_pairs(xs, ys, start, count),
    }


def arrow_shapes(
    x0: float, y0: float, x1: float, y1: float, style: dict[str, Any]
) -> dict[str, Any]:
    """Shaft polyline (or taper polygon) + endpoint decorations for one
    arrow/callout spec."""
    width_start = _number(style.get("shaft_width_start"))
    width_end = _number(style.get("shaft_width_end"))
    meta, xs, ys = kernels.arrow_shapes(
        x0,
        y0,
        x1,
        y1,
        _pack_style(style),
        str(style.get("head_style") or "triangle"),
        str(style.get("tail_style") or "none"),
        _finite_or_nan(style.get("head_size")),
        math.nan if width_start is None else width_start,
        math.nan if width_end is None else width_end,
        bool(style.get("elbow")),
    )
    shaft_n, taper_n, head_kind, head_n, tail_kind, tail_n = (int(v) for v in meta)
    offset = 0
    shaft = None
    taper = None
    if shaft_n:
        shaft = _point_pairs(xs, ys, offset, shaft_n)
        offset += shaft_n
    if taper_n:
        taper = _point_pairs(xs, ys, offset, taper_n)
        offset += taper_n
    head = _decoration_from_meta(head_kind, xs, ys, offset, head_n)
    offset += head_n
    tail = _decoration_from_meta(tail_kind, xs, ys, offset, tail_n)
    return {
        "shaft": shaft,
        "taper": taper,
        "head": head,
        "tail": tail,
    }
