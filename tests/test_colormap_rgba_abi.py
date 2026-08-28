"""ABI 129 direct colormap RGBA: Python host wrappers match `_svg._lut` goldens."""

from __future__ import annotations

import numpy as np

from xyg import kernels


def test_colormap_rgba_matches_lut_grid() -> None:
    raw = np.array([[0.0, 0.5], [1.0, np.nan]], dtype=np.float64)
    stops = np.array([[0, 10, 20], [100, 110, 120]], dtype=np.uint8)
    alpha = 200

    rgba = kernels.colormap_rgba(raw, 2, 2, stops, alpha)
    t = np.clip(np.where(np.isfinite(raw), raw, 0.0), 0.0, 1.0)
    pos = np.clip(t.reshape(-1), 0.0, 1.0) * (len(stops) - 1)
    lo = np.floor(pos).astype(np.int32)
    hi = np.minimum(lo + 1, len(stops) - 1)
    fraction = pos - lo
    expected_rgb = np.empty((4, 3), dtype=np.uint8)
    stops_f = stops.astype(np.float64)
    for channel in range(3):
        start = stops_f[lo, channel]
        expected_rgb[:, channel] = np.round(
            start + (stops_f[hi, channel] - start) * fraction
        ).astype(np.uint8)
    expected_rgb = expected_rgb.reshape(2, 2, 3)
    expected_alpha = np.full((2, 2), alpha, dtype=np.uint8)
    expected_alpha[~np.isfinite(raw)] = 0
    expected_rgb[~np.isfinite(raw)] = 0
    expected = np.dstack([expected_rgb, expected_alpha])
    expected = expected[::-1]

    np.testing.assert_array_equal(rgba, expected)


def test_colormap_rgba_canonical_matches_f32_lut_samples() -> None:
    values = np.array([0.25, 0.75, np.nan], dtype=np.float64)
    domain = (0.0, 1.0)
    stops = np.array([[0, 0, 0], [200, 0, 0]], dtype=np.uint8)
    rgba = kernels.colormap_rgba_canonical(values, 1, 3, domain, stops, 255)

    t = np.zeros(3, dtype=np.float64)
    normalized = np.clip((values[np.isfinite(values)] - domain[0]) / domain[1], 0.0, 1.0)
    t[np.isfinite(values)] = normalized.astype(np.float32).astype(np.float64)
    pos = np.clip(t, 0.0, 1.0) * (len(stops) - 1)
    lo = np.floor(pos).astype(np.int32)
    hi = np.minimum(lo + 1, len(stops) - 1)
    fraction = pos - lo
    expected_rgb = np.empty((3, 3), dtype=np.uint8)
    stops_f = stops.astype(np.float64)
    for channel in range(3):
        start = stops_f[lo, channel]
        expected_rgb[:, channel] = np.round(
            start + (stops_f[hi, channel] - start) * fraction
        ).astype(np.uint8)
    expected_alpha = np.full(3, 255, dtype=np.uint8)
    expected_alpha[~np.isfinite(values)] = 0
    expected = np.column_stack((expected_rgb, expected_alpha)).reshape(3, 1, 4)[::-1]

    np.testing.assert_array_equal(rgba, expected)


def test_colormap_rgba_differs_from_heatmap_at_interior() -> None:
    stops = np.array([[0, 0, 0], [254, 0, 0]], dtype=np.uint8)
    value = np.array([0.5], dtype=np.float64)
    heat = kernels.heatmap_rgba(value, 1, 1, stops, 255)
    cmap = kernels.colormap_rgba(value, 1, 1, stops, 255)
    assert heat[0, 0, 0] != cmap[0, 0, 0]
    assert cmap[0, 0, 0] == 127


def test_colormap_lut_matches_finite_samples() -> None:
    t = np.array([0.0, 0.5, 1.0], dtype=np.float64)
    stops = np.array([[0, 10, 20], [100, 110, 120]], dtype=np.uint8)
    rgb = kernels.colormap_lut(t, stops)
    grid = kernels.colormap_rgba(t, 3, 1, stops, 255)
    np.testing.assert_array_equal(rgb, grid[0, :, :3])


def test_density_rgba_linear_empty_cell_is_transparent() -> None:
    counts = np.array([[0.0, 100.0], [50.0, np.nan]], dtype=np.float64)
    stops = np.array([[0, 10, 20], [100, 110, 120]], dtype=np.uint8)
    rgba = kernels.density_rgba_linear(counts, 2, 2, 100.0, stops, 0.85)
    assert rgba[1, 0, 3] == 0
    np.testing.assert_array_equal(rgba[1, 1], [100, 110, 120, 216])


def test_paint_effective_rgba_replaces_then_multiplies() -> None:
    intrinsic = np.array([[0.1, 0.2, 0.3, 0.8], [0.4, 0.5, 0.6, 0.9]])
    artist = np.array([-1.0, 0.5])
    opacity = np.array([0.5, 1.0])
    out = kernels.paint_effective_rgba(intrinsic, artist, opacity, 0.5)
    np.testing.assert_allclose(out[0, 3], 0.8 * 0.5 * 0.5)
    np.testing.assert_allclose(out[1, 3], 0.5 * 1.0 * 0.5)
