"""Per-item ``scatter(s=array)`` exports through the Rust size plane (#1006).

``plt.scatter`` pins ``size_range`` to the min/max pixel diameter, so the
Rust-mapped diameters must reproduce Matplotlib's absolute ``s`` (points²).
"""

from __future__ import annotations

import re
from io import BytesIO

import numpy as np
import pytest

import xyg.pyplot as plt


def _svg_radii(fig: object) -> list[float]:
    buffer = BytesIO()
    fig.savefig(buffer, format="svg")  # type: ignore[attr-defined]
    svg = buffer.getvalue().decode("utf-8")
    return [float(r) for r in re.findall(r'<circle[^>]*\sr="([^"]+)"', svg)]


def test_size_array_radii_follow_the_absolute_point_area() -> None:
    sizes = np.array([20.0, 80.0, 180.0, 320.0])
    fig, ax = plt.subplots()
    try:
        ax.scatter([0, 1, 2, 3], [0, 1, 0, 1], s=sizes, c="tab:purple")
        radii = _svg_radii(fig)
        # Each per-item radius must equal a scalar scatter of the same size, so
        # a wrong scale or offset (e.g. the default 2-18 px range) cannot pass.
        scalar = []
        for size in sizes:
            single, axis = plt.subplots()
            axis.scatter([0], [0], s=float(size), c="tab:purple")
            scalar.extend(_svg_radii(single))
    finally:
        plt.close("all")
    assert len(radii) == len(sizes)
    assert radii == pytest.approx(scalar, rel=1e-3)
    assert list(radii) == sorted(radii)


def test_uniform_size_array_keeps_its_authored_diameter() -> None:
    fig, ax = plt.subplots()
    try:
        ax.scatter([0, 1, 2], [0, 1, 0], s=np.full(3, 150.0), c="tab:blue")
        uniform = _svg_radii(fig)
        scalar_fig, scalar_ax = plt.subplots()
        scalar_ax.scatter([0, 1, 2], [0, 1, 0], s=150.0, c="tab:blue")
        scalar = _svg_radii(scalar_fig)
    finally:
        plt.close("all")
    assert uniform == pytest.approx(scalar, rel=1e-3)
