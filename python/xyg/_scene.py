"""Compatibility geometry producers shared by tests and leftover helpers.

Ribbon/curve/rounded-rect tessellation lives in Rust (ABI 121). These wrappers
pack host coordinates and map affine scales; they do not own the cubics.
Compatibility PNG (`_raster.py`) calls those kernels directly (#310) and no
longer imports this module. `grid_rgba` colormap application uses Rust
(`xyg_colormap_rgba` / ABI 129) with a remaining `_lut` density path (#313).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from . import kernels

# Samples per smooth Bézier span when flattening to a polyline for the raster
# filler. The curve is screen-bounded (M4-decimated), so this stays cheap and
# is visually indistinguishable from the SVG's true cubics.
_BEZIER_STEPS = 16

# Segments per ribbon edge. Fixed rather than view-adaptive: a flow diagram has
# tens of links, so the ceiling is free, and a view-dependent count would have
# to be recorded per §28 rather than chosen silently. The client sweeps the same
# count so the live chart and the exports flatten identically. This resolution
# keeps chord error below a visible pixel on wide, high-contrast diagrams.
RIBBON_STEPS = 96


def ribbon_edge(
    x0: float, x1: float, ya: float, yb: float, steps: int = RIBBON_STEPS
) -> np.ndarray:
    """One edge of a flow band, in the caller's coordinate space.

    The cubic of the ribbon contract: both control points sit at the horizontal
    midpoint and hold their own end's y, so the edge leaves and arrives
    horizontally (d3's `curveBumpX`). The function is pure arithmetic with no
    opinion about units — but the contract makes the curve normative in
    **axis-transformed space**, so exporters pass mapped endpoints rather than
    mapping the flattened result (the two orders differ on log/symlog axes).
    Returned flattened because the raster display list has no curve opcode; the
    SVG exporter rebuilds the exact `C` from the same four numbers.
    """
    xs, ys = kernels.ribbon_edge(x0, x1, ya, yb, steps)
    return np.column_stack([xs, ys])


def ribbon_polygon(
    x0: float,
    x1: float,
    src_lo: float,
    src_hi: float,
    dst_lo: float,
    dst_hi: float,
    steps: int = RIBBON_STEPS,
) -> np.ndarray:
    """A whole flow band as one closed polygon, in the caller's space.

    One polygon, not two triangles or a mesh: the seam-free fill paths in both
    exporters require a single uniform-alpha shape, and a gradient across a
    triangle mesh is impossible anyway (the contract explains why). This is the
    compatibility reference the gradient/static fallback exporters and their
    golden geometry tests consume. Canonical solid-ribbon Scene expansion is
    owned by Rust and deliberately does not call this helper.
    """
    xs, ys = kernels.ribbon_polygon(x0, x1, src_lo, src_hi, dst_lo, dst_hi, steps)
    return np.column_stack([xs, ys])


def curve_points(xv: np.ndarray, yv: np.ndarray, sx: Any, sy: Any, smooth: bool) -> np.ndarray:
    """Pixel-space polyline for a series. Smooth flattens the monotone-cubic
    Hermite (the same tangents `_svg._curve_path` emits as Béziers) into short
    line segments; else it's the mapped polyline."""
    px = np.asarray(sx(xv), dtype=np.float64)
    py = np.asarray(sy(yv), dtype=np.float64)
    if not smooth or len(xv) < 3 or not (sx.affine and sy.affine):
        return np.column_stack([px, py])
    data_x, data_y = kernels.curve_flatten(
        np.asarray(xv, dtype=np.float64),
        np.asarray(yv, dtype=np.float64),
        _BEZIER_STEPS,
    )
    return np.column_stack(
        [np.asarray(sx(data_x), dtype=np.float64), np.asarray(sy(data_y), dtype=np.float64)]
    )


def rounded_rect_poly(
    x: float, y: float, w: float, h: float, r_tip: float, r_base: float, tip_top: bool
) -> list:
    """Outline polygon (CW) for a rect with independent tip/base corner radii —
    the raster tessellation of `_svg._rounded_rect_path`. `tip_top` puts the
    value end (tip radius) on the top edge."""
    xs, ys = kernels.rounded_rect_poly(x, y, w, h, r_tip, r_base, tip_top)
    return list(zip(xs.tolist(), ys.tolist(), strict=True))


def grid_rgba(kind: str, g: dict, blob: bytes, cols: list, style: dict) -> tuple:
    """Density/heatmap grid → `(h, w, 4)` uint8 RGBA (top row first), matching
    `_svg._density_image`/`_heatmap_image`. Returns (rgba, x_range, y_range)."""
    from . import _raster

    return _raster._compat_grid_rgba(kind, g, blob, cols, style)


def grid_dest_rect(x_range: list, y_range: list, sx: Any, sy: Any) -> tuple:
    """Pixel destination rect (x, y, w, h) for a grid image, matching
    `_svg._grid_image`."""
    from . import _raster

    return _raster._grid_dest_rect(x_range, y_range, sx, sy)
