"""Python demo: build an interactive chart with xy and export standalone HTML.

Run from the repo root:

    uv run python demo/python_demo.py

Writes demo/python_demo.html — a fully self-contained interactive page
(scroll to zoom, drag to pan, hover for tooltips, double-click to reset).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

import xyg


def spiral_galaxy_scatter() -> xy.Chart:
    """300k-point spiral galaxy, color-encoded by distance from center."""
    rng = np.random.default_rng(42)
    n = 300_000
    arms = 3
    arm = rng.integers(0, arms, n)
    r = rng.power(2.2, n) * 10.0
    theta = arm * (2 * np.pi / arms) + r * 0.55 + rng.normal(0, 0.18, n)
    x = r * np.cos(theta) + rng.normal(0, 0.12, n)
    y = r * np.sin(theta) + rng.normal(0, 0.12, n)
    return xy.scatter_chart(
        xy.scatter(x, y, color=r, colormap="magma", size=2.5, opacity=0.55, name="stars"),
        xy.x_axis(label="x (kpc)"),
        xy.y_axis(label="y (kpc)"),
        xy.tooltip(fields=["x", "y"], format={"x": ".2f", "y": ".2f"}),
        title="XY Python demo — 300k-point spiral galaxy (zoom, pan, hover)",
        width="100%",
        height=560,
    )


def main() -> None:
    out = Path(__file__).parent / "python_demo.html"
    chart = spiral_galaxy_scatter()
    chart.to_html(out)
    print(f"wrote {out} ({out.stat().st_size / 2**20:.1f} MB)")


if __name__ == "__main__":
    main()
