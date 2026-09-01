"""Shared static-export SVG marker glyph path builders."""

from __future__ import annotations

from typing import Any

import numpy as np

from ._export_svg_util import _num
from ._paint import authored_marker_points as _authored_marker_points


def _regular_polygon_path(cx: float, cy: float, r: float, n: int, start_deg: float) -> str:
    pts = []
    for i in range(n):
        theta = np.radians(start_deg + i * 360.0 / n)
        pts.append((cx + r * np.cos(theta), cy + r * np.sin(theta)))
    d = "M " + " L ".join(f"{_num(px)} {_num(py)}" for px, py in pts)
    return f'<path d="{d} Z"'


def _star_path(cx: float, cy: float, r: float, points: int, inner: float, start_deg: float) -> str:
    pts = []
    for i in range(points * 2):
        radius = r if i % 2 == 0 else r * inner
        theta = np.radians(start_deg + i * 180.0 / points)
        pts.append((cx + radius * np.cos(theta), cy + radius * np.sin(theta)))
    d = "M " + " L ".join(f"{_num(px)} {_num(py)}" for px, py in pts)
    return f'<path d="{d} Z"'


_SYMBOL_BUILDERS = {
    "pixel": lambda cx, cy, r: (
        f'<rect x="{_num(cx - r)}" y="{_num(cy - r)}" width="{_num(2 * r)}" height="{_num(2 * r)}"'
    ),
    "square": lambda cx, cy, r: (
        f'<rect x="{_num(cx - r)}" y="{_num(cy - r)}" width="{_num(2 * r)}" height="{_num(2 * r)}"'
    ),
    "diamond": lambda cx, cy, r: (
        f'<path d="M {_num(cx)} {_num(cy - 2**0.5 * r)} '
        f"L {_num(cx + 2**0.5 * r)} {_num(cy)} "
        f"L {_num(cx)} {_num(cy + 2**0.5 * r)} "
        f'L {_num(cx - 2**0.5 * r)} {_num(cy)} Z"'
    ),
    "thin_diamond": lambda cx, cy, r: (
        f'<path d="M {_num(cx)} {_num(cy - 2**0.5 * r)} '
        f"L {_num(cx + 0.6 * 2**0.5 * r)} {_num(cy)} "
        f"L {_num(cx)} {_num(cy + 2**0.5 * r)} "
        f'L {_num(cx - 0.6 * 2**0.5 * r)} {_num(cy)} Z"'
    ),
    "triangle": lambda cx, cy, r: (
        f'<path d="M {_num(cx)} {_num(cy - r)} L {_num(cx + r)} {_num(cy + r)} L {_num(cx - r)} {_num(cy + r)} Z"'
    ),
    "triangle_down": lambda cx, cy, r: (
        f'<path d="M {_num(cx)} {_num(cy + r)} L {_num(cx + r)} {_num(cy - r)} L {_num(cx - r)} {_num(cy - r)} Z"'
    ),
    "triangle_left": lambda cx, cy, r: (
        f'<path d="M {_num(cx - r)} {_num(cy)} L {_num(cx + r)} {_num(cy - r)} L {_num(cx + r)} {_num(cy + r)} Z"'
    ),
    "triangle_right": lambda cx, cy, r: (
        f'<path d="M {_num(cx + r)} {_num(cy)} L {_num(cx - r)} {_num(cy - r)} L {_num(cx - r)} {_num(cy + r)} Z"'
    ),
    "cross": lambda cx, cy, r: (
        f'<path d="M {_num(cx - 0.34 * r)} {_num(cy - r)} H {_num(cx + 0.34 * r)} V {_num(cy - 0.34 * r)} '
        f"H {_num(cx + r)} V {_num(cy + 0.34 * r)} H {_num(cx + 0.34 * r)} V {_num(cy + r)} "
        f"H {_num(cx - 0.34 * r)} V {_num(cy + 0.34 * r)} H {_num(cx - r)} V {_num(cy - 0.34 * r)} "
        f'H {_num(cx - 0.34 * r)} Z"'
    ),
    "x": lambda cx, cy, r: (
        f'<path d="M {_num(cx - 0.72 * r)} {_num(cy - r)} L {_num(cx)} {_num(cy - 0.28 * r)} '
        f"L {_num(cx + 0.72 * r)} {_num(cy - r)} L {_num(cx + r)} {_num(cy - 0.72 * r)} "
        f"L {_num(cx + 0.28 * r)} {_num(cy)} L {_num(cx + r)} {_num(cy + 0.72 * r)} "
        f"L {_num(cx + 0.72 * r)} {_num(cy + r)} L {_num(cx)} {_num(cy + 0.28 * r)} "
        f"L {_num(cx - 0.72 * r)} {_num(cy + r)} L {_num(cx - r)} {_num(cy + 0.72 * r)} "
        f'L {_num(cx - 0.28 * r)} {_num(cy)} L {_num(cx - r)} {_num(cy - 0.72 * r)} Z"'
    ),
    "plus_line": lambda cx, cy, r: (
        f'<path d="M {_num(cx - r)} {_num(cy)} H {_num(cx + r)} M {_num(cx)} {_num(cy - r)} V {_num(cy + r)}" fill="none"'
    ),
    "x_line": lambda cx, cy, r: (
        f'<path d="M {_num(cx - 0.707 * r)} {_num(cy - 0.707 * r)} L {_num(cx + 0.707 * r)} {_num(cy + 0.707 * r)} '
        f'M {_num(cx + 0.707 * r)} {_num(cy - 0.707 * r)} L {_num(cx - 0.707 * r)} {_num(cy + 0.707 * r)}" fill="none"'
    ),
    "horizontal_line": lambda cx, cy, r: (
        f'<path d="M {_num(cx - r)} {_num(cy)} H {_num(cx + r)}" fill="none"'
    ),
    "vertical_line": lambda cx, cy, r: (
        f'<path d="M {_num(cx)} {_num(cy - r)} V {_num(cy + r)}" fill="none"'
    ),
    "pentagon": lambda cx, cy, r: _regular_polygon_path(cx, cy, r, 5, -90.0),
    "hexagon": lambda cx, cy, r: _regular_polygon_path(cx, cy, r, 6, -90.0),
    "star": lambda cx, cy, r: _star_path(cx, cy, r, 5, 0.45, -90.0),
}


def _authored_marker_path_d(
    marker_path: dict[str, Any], cx: float, cy: float, diameter: float
) -> str:
    parts: list[str] = []
    for contour in marker_path.get("contours") or ():
        values = np.asarray(contour, dtype=np.float64).reshape(-1, 2)
        if not len(values):
            continue
        px, py = _authored_marker_points(values[:, 0], values[:, 1], cx, cy, diameter)
        parts.append(f"M {_num(float(px[0]))} {_num(float(py[0]))}")
        parts.extend(
            f"L {_num(float(x))} {_num(float(y))}" for x, y in zip(px[1:], py[1:], strict=True)
        )
        if bool(marker_path.get("filled", True)):
            parts.append("Z")
    return " ".join(parts)
