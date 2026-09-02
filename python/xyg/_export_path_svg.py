"""Shared static-export SVG path builders for lines and areas."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import numpy as np

from . import _native
from ._export_svg_util import _num
from ._layout import _Scale

if TYPE_CHECKING:
    from ._layout import _PolarProjection


def _monotone_tangents(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fritsch–Carlson tangents — the same construction as xySmoothResample."""
    return _native.monotone_tangents(
        np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    )


def _rounded_rect_path(
    x: float, y: float, w: float, h: float, r_tip: float, r_base: float, tip_top: bool
) -> str:
    """Rect path with independent tip/base corner radii (vertical mark space)."""
    rt = min(r_tip, w / 2, h / 2)
    rb = min(r_base, w / 2, h / 2)
    top_r, bot_r = (rt, rb) if tip_top else (rb, rt)
    p = [f"M {_num(x)} {_num(y + top_r)}"]
    p.append(f"A {_num(top_r)} {_num(top_r)} 0 0 1 {_num(x + top_r)} {_num(y)}" if top_r else "")
    p.append(f"L {_num(x + w - top_r)} {_num(y)}")
    p.append(
        f"A {_num(top_r)} {_num(top_r)} 0 0 1 {_num(x + w)} {_num(y + top_r)}" if top_r else ""
    )
    p.append(f"L {_num(x + w)} {_num(y + h - bot_r)}")
    p.append(
        f"A {_num(bot_r)} {_num(bot_r)} 0 0 1 {_num(x + w - bot_r)} {_num(y + h)}" if bot_r else ""
    )
    p.append(f"L {_num(x + bot_r)} {_num(y + h)}")
    p.append(
        f"A {_num(bot_r)} {_num(bot_r)} 0 0 1 {_num(x)} {_num(y + h - bot_r)}" if bot_r else ""
    )
    p.append("Z")
    return " ".join(s for s in p if s)


def _poly_path(px: np.ndarray, py: np.ndarray) -> str:
    return _native.svg_poly_path(px, py)


def _polar_visible_runs(
    xv: np.ndarray, yv: np.ndarray, polar: "_PolarProjection"
) -> list[np.ndarray]:
    """Index runs of consecutive vertices the polar transform keeps.

    The same split `_curve_path` performs, exposed so a filled area can close
    each run against its own base instead of stitching every run to one base.
    """
    visible = polar.position_mask(xv, yv)
    if visible.size == 0:
        return []
    idx = np.flatnonzero(visible)
    if idx.size == 0:
        return []
    runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    return [run for run in runs if len(run) >= 2]


def _area_fill_path(
    xv: np.ndarray,
    yv: np.ndarray,
    bv: np.ndarray,
    sx: _Scale,
    sy: _Scale,
    smooth: bool,
    polar: "Optional[_PolarProjection]" = None,
) -> str:
    """Closed fill path between a top curve and its base, or "" if nothing is
    visible. Under polar each visible run closes separately."""
    if polar is None:
        top = _curve_path(xv, yv, sx, sy, smooth, None)
        base = _curve_path(xv[::-1], bv[::-1], sx, sy, smooth, None)
        return f"{top} L {base[2:]} Z" if top and base else ""
    parts = []
    for run in _polar_visible_runs(xv, yv, polar):
        top = _curve_path(xv[run], yv[run], sx, sy, smooth, polar)
        base = _curve_path(xv[run][::-1], bv[run][::-1], sx, sy, smooth, polar)
        if top and base:
            parts.append(f"{top} L {base[2:]} Z")
    return " ".join(parts)


def _curve_path(
    xv: np.ndarray,
    yv: np.ndarray,
    sx: _Scale,
    sy: _Scale,
    smooth: bool,
    polar: "Optional[_PolarProjection]" = None,
) -> str:
    """Pixel-space path for a polyline; smooth -> exact cubic Béziers of the
    monotone-cubic Hermite (affine axes), else polyline. The Bézier control
    points of a Hermite segment are P0 + h/3·(1, m0) and P1 - h/3·(1, m1),
    and affine axis maps carry control points exactly.

    Under `polar` the separable (sx, sy) pair is replaced by the joint
    projection and the result is always a polyline: consecutive data points are
    joined by straight **chords**, which is Plotly's polar semantics and what
    makes radar/spider edges come out straight (polar-axes.md §5). Vertices
    outside the radial range are culled like the client shader culls them —
    the path splits into visible runs, dropping any chord with a culled
    endpoint whole (§8)."""
    if len(xv) == 0:
        return ""
    if polar is not None:
        px, py = polar(xv, yv)
        visible = polar.position_mask(xv, yv)
        if bool(visible.all()):
            return _poly_path(px, py)
        runs = np.split(
            np.flatnonzero(visible),
            np.flatnonzero(np.diff(np.flatnonzero(visible)) > 1) + 1,
        )
        return " ".join(_poly_path(px[run], py[run]) for run in runs if len(run) >= 2)
    px, py = sx(xv), sy(yv)
    if not smooth or len(xv) < 3 or not (sx.affine and sy.affine):
        return _poly_path(px, py)
    m = _monotone_tangents(xv, yv)
    parts = [f"M {_num(px[0])} {_num(py[0])}"]
    for i in range(len(xv) - 1):
        h = xv[i + 1] - xv[i]
        if h <= 0:
            parts.append(f"L {_num(px[i + 1])} {_num(py[i + 1])}")
            continue
        c1x, c1y = sx(xv[i] + h / 3), sy(yv[i] + m[i] * h / 3)
        c2x, c2y = sx(xv[i + 1] - h / 3), sy(yv[i + 1] - m[i + 1] * h / 3)
        parts.append(
            f"C {_num(c1x)} {_num(c1y)} {_num(c2x)} {_num(c2y)} {_num(px[i + 1])} {_num(py[i + 1])}"
        )
    return " ".join(parts)
