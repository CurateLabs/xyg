"""ABI 121 geometry helpers: Python host wrappers match the Rust goldens."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from xyg import _scene, kernels
from xyg._svg import _monotone_tangents


def test_ribbon_edge_midpoint() -> None:
    pts = _scene.ribbon_edge(0.0, 10.0, 1.0, 3.0, 8)
    assert pts.shape == (9, 2)
    np.testing.assert_allclose(pts[0], (0.0, 1.0))
    np.testing.assert_allclose(pts[4], (5.0, 2.0))
    np.testing.assert_allclose(pts[-1], (10.0, 3.0))
    xs, ys = kernels.ribbon_edge(0.0, 10.0, 1.0, 3.0, 8)
    np.testing.assert_array_equal(pts[:, 0], xs)
    np.testing.assert_array_equal(pts[:, 1], ys)


def test_ribbon_polygon_closes_upper_then_lower() -> None:
    poly = _scene.ribbon_polygon(0.0, 10.0, 0.0, 1.0, 2.0, 4.0, 4)
    assert poly.shape == (10, 2)
    np.testing.assert_allclose(poly[0], (0.0, 1.0))
    np.testing.assert_allclose(poly[4], (10.0, 4.0))
    np.testing.assert_allclose(poly[5], (10.0, 2.0))
    np.testing.assert_allclose(poly[-1], (0.0, 0.0))


def test_monotone_tangents_match_svg_and_kernels() -> None:
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    y = np.array([0.0, 1.0, 0.5, 2.0, 1.5])
    expected = np.array([1.0, 0.0, 0.0, 0.0, -0.5])
    np.testing.assert_allclose(_monotone_tangents(x, y), expected)
    np.testing.assert_allclose(kernels.monotone_tangents(x, y), expected)


def test_curve_points_keeps_knots() -> None:
    class Id:
        affine = True

        def __call__(self, v):
            return np.asarray(v, dtype=np.float64)

    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    y = np.array([0.0, 1.0, 0.5, 2.0, 1.5])
    pts = _scene.curve_points(x, y, Id(), Id(), True)
    assert pts.shape == (65, 2)
    np.testing.assert_allclose(pts[0], (0.0, 0.0))
    np.testing.assert_allclose(pts[16], (1.0, 1.0))
    np.testing.assert_allclose(pts[-1], (4.0, 1.5))
    np.testing.assert_allclose(pts[1], (0.0625, 0.066162109375))


def test_rounded_rect_zero_and_radii() -> None:
    square = _scene.rounded_rect_poly(0.0, 0.0, 4.0, 3.0, 0.0, 0.0, True)
    assert square == [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
    pts = _scene.rounded_rect_poly(1.0, 2.0, 10.0, 6.0, 2.0, 1.0, True)
    assert len(pts) == 20
    np.testing.assert_allclose(pts[0], (1.0, 4.0), atol=1e-12)
    np.testing.assert_allclose(pts[-1], (1.0, 7.0), atol=1e-12)


def test_compatibility_raster_calls_abi_121_kernels_not_scene_wrappers() -> None:
    """#310: PNG compatibility emits through kernels; product Scene never imports `_scene.py`."""
    root = Path(__file__).resolve().parents[1]
    raster = (root / "python/xyg/_raster.py").read_text()
    scene_v3 = (root / "python/xyg/_scene_v3.py").read_text()
    svg = (root / "python/xyg/_svg.py").read_text()
    assert "from . import _scene" not in raster
    assert "from . import _scene" not in scene_v3
    assert "from . import _scene" not in svg
    assert "kernels.ribbon_polygon" in raster
    assert "kernels.rounded_rect_poly" in raster
    assert "kernels.curve_flatten" in raster
