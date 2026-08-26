"""Native quantiles / Tukey box / violin / hexbin / histogram-edges / wind-rose parity."""

from __future__ import annotations

import numpy as np
import pytest

from xyg import kernels
from xyg.marks import _distribution_stats


def _legacy_distribution_stats(group: np.ndarray):
    finite = group[np.isfinite(group)]
    if len(finite) == 0:
        empty = np.empty(0, dtype=np.float64)
        return (np.nan, np.nan, np.nan, np.nan, np.nan, empty)
    q1, median, q3 = np.percentile(finite, [25.0, 50.0, 75.0])
    iqr = q3 - q1
    lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    low = float(np.min(finite[finite >= lo_fence]))
    high = float(np.max(finite[finite <= hi_fence]))
    outliers = finite[(finite < low) | (finite > high)]
    return float(q1), float(median), float(q3), low, high, outliers


@pytest.mark.parametrize(
    "vals",
    [
        np.array([0.0, 10.0, 11.0, 12.0, 13.0, 14.0, 40.0]),
        np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
        np.linspace(-3.0, 3.0, 101),
        np.array([np.nan, 1.0, 2.0, np.inf, 3.0, 100.0]),
        np.array([], dtype=np.float64),
        np.array([np.nan, np.inf], dtype=np.float64),
    ],
)
def test_box_stats_match_legacy_percentiles(vals: np.ndarray) -> None:
    got = _distribution_stats(vals)
    exp = _legacy_distribution_stats(vals)
    for a, b in zip(got[:5], exp[:5], strict=True):
        if np.isnan(b):
            assert np.isnan(a)
        else:
            assert a == pytest.approx(b, rel=0, abs=1e-12)
    np.testing.assert_allclose(np.sort(got[5]), np.sort(exp[5]), atol=1e-12)


def test_quantiles_match_numpy_linear() -> None:
    rng = np.random.default_rng(0)
    data = rng.normal(size=257)
    probs = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    got = kernels.quantiles(data, probs)
    exp = np.quantile(data, probs, method="linear")
    np.testing.assert_allclose(got, exp, atol=1e-12)


def test_quantiles_reject_bad_probs() -> None:
    with pytest.raises(ValueError, match="probabilities"):
        kernels.quantiles(np.array([1.0, 2.0]), np.array([1.5]))


def _legacy_violin_density(finite: np.ndarray, n_bins: int):
    kernel = np.array([1.0, 2.0, 3.0, 2.0, 1.0])
    coverage = np.convolve(np.ones(n_bins), kernel, mode="same")
    lo, hi = float(np.min(finite)), float(np.max(finite))
    if lo == hi:
        lo -= 0.5
        hi += 0.5
    edges = np.linspace(lo, hi, n_bins + 1)
    counts, _ = np.histogram(finite, bins=edges)
    smooth = np.convolve(counts.astype(np.float64), kernel, mode="same") / coverage
    return edges, smooth


def test_violin_density_matches_legacy_numpy() -> None:
    rng = np.random.default_rng(1)
    data = rng.normal(loc=2.0, scale=1.5, size=80)
    edges, dens = kernels.violin_density(data, 32)
    exp_edges, exp_dens = _legacy_violin_density(data, 32)
    np.testing.assert_allclose(edges, exp_edges, atol=1e-12)
    np.testing.assert_allclose(dens, exp_dens, atol=1e-12)


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_violin_rects_compile_grouped_geometry_in_rust(orientation: str) -> None:
    result = kernels.violin_rects(
        np.array([1.0, np.nan, 2.0, np.inf, 3.0, 4.0]),
        np.array([0, 3, 4, 6], dtype=np.uintp),
        np.array([0.0, 1.0, 2.0]),
        4,
        0.8,
        orientation,
    )
    x0, y0, x1, y1, active, edges, density = result
    np.testing.assert_array_equal(active, [0, 2])
    assert len(x0) == len(y0) == len(x1) == len(y1) == 8
    assert len(edges) == len(density) == 2
    assert all(np.isfinite(column).all() for column in (x0, y0, x1, y1))


def test_violin_rects_reject_malformed_and_over_budget_groups() -> None:
    values = np.array([1.0, 2.0])
    with pytest.raises(ValueError):
        kernels.violin_rects(
            values, np.array([1, 2], dtype=np.uintp), np.array([0.0]), 4, 0.8, "vertical"
        )
    with pytest.raises(ValueError):
        kernels.violin_rects(
            values, np.array([0, 2], dtype=np.uintp), np.array([0.0]), 4, np.inf, "vertical"
        )
    groups = 2501
    with pytest.raises(ValueError):
        kernels.violin_rects(
            np.ones(groups),
            np.arange(groups + 1, dtype=np.uintp),
            np.arange(groups, dtype=float),
            4,
            0.8,
            "vertical",
        )


def _legacy_hexbin(x, y, c, w, h, xr, yr, threshold, reduce):
    fx = (x - xr[0]) * w / (xr[1] - xr[0])
    fy = (y - yr[0]) * h / (yr[1] - yr[0])
    ix1 = np.rint(fx).astype(np.int64)
    iy1 = np.rint(fy).astype(np.int64)
    ix2 = np.floor(fx).astype(np.int64)
    iy2 = np.floor(fy).astype(np.int64)
    use_first = (fx - ix1) ** 2 + 3.0 * (fy - iy1) ** 2 < (
        (fx - ix2 - 0.5) ** 2 + 3.0 * (fy - iy2 - 0.5) ** 2
    )
    valid_first = use_first & (ix1 >= 0) & (ix1 <= w) & (iy1 >= 0) & (iy1 <= h)
    valid_second = ~use_first & (ix2 >= 0) & (ix2 < w) & (iy2 >= 0) & (iy2 < h)
    flat1 = iy1 * (w + 1) + ix1
    flat2 = iy2 * w + ix2
    count1 = np.bincount(flat1[valid_first], minlength=(w + 1) * (h + 1)).astype(float)
    count2 = np.bincount(flat2[valid_second], minlength=w * h).astype(float)
    keep1 = np.flatnonzero(count1 >= threshold)
    keep2 = np.flatnonzero(count2 >= threshold)
    counts = np.concatenate((count1[keep1], count2[keep2]))
    dx, dy = (xr[1] - xr[0]) / w, (yr[1] - yr[0]) / h
    centers_x = np.concatenate((xr[0] + (keep1 % (w + 1)) * dx, xr[0] + (keep2 % w + 0.5) * dx))
    centers_y = np.concatenate((yr[0] + (keep1 // (w + 1)) * dy, yr[0] + (keep2 // w + 0.5) * dy))
    if c is None or reduce == "count":
        metric = counts.copy()
    else:
        memberships = [c[valid_first & (flat1 == flat)] for flat in keep1] + [
            c[valid_second & (flat2 == flat)] for flat in keep2
        ]
        fn = np.mean if reduce == "mean" else np.sum
        metric = np.asarray([float(fn(vals)) for vals in memberships], dtype=np.float64)
    return centers_x, centers_y, metric, counts, dx, dy


@pytest.mark.parametrize("reduce", ["count", "mean", "sum"])
def test_hexbin_matches_legacy_numpy(reduce: str) -> None:
    rng = np.random.default_rng(2)
    x = rng.uniform(0, 1, 40)
    y = rng.uniform(0, 1, 40)
    c = rng.uniform(1, 5, 40)
    w = h = 6
    xr = yr = (0.0, 1.0)
    threshold = 1
    cx, cy, metric, counts, dx, dy = kernels.hexbin(
        x,
        y,
        gridsize=(w, h),
        range=(xr, yr),
        mincnt=threshold,
        C=None if reduce == "count" else c,
        reduce=reduce,
    )
    exp = _legacy_hexbin(x, y, None if reduce == "count" else c, w, h, xr, yr, threshold, reduce)
    np.testing.assert_allclose(cx, exp[0], atol=1e-12)
    np.testing.assert_allclose(cy, exp[1], atol=1e-12)
    np.testing.assert_allclose(metric, exp[2], atol=1e-12)
    np.testing.assert_allclose(counts, exp[3], atol=1e-12)
    assert dx == pytest.approx(exp[4])
    assert dy == pytest.approx(exp[5])


def test_hexbin_auto_domain_and_default_aspect_are_rust_owned() -> None:
    assert "hexbin_ingress" in kernels.__all__
    x = np.array([np.nan, 10.0, np.inf, 10.0])
    y = np.array([0.0, 4.0, 1.0, 4.0])
    c = np.array([1.0, 2.0, 3.0, np.nan])
    xr, yr, w, h = kernels.hexbin_ingress(x, y, gridsize=16, C=c)
    assert (w, h) == (16, 9)
    assert xr == pytest.approx((9.5, 10.5))
    assert yr == pytest.approx((3.8, 4.2))
    _cx, _cy, metric, counts, dx, dy = kernels.hexbin(x, y, gridsize=16, C=c, reduce="mean")
    assert len(counts) == 1
    assert counts[0] == 1.0
    assert metric[0] == pytest.approx(2.0)
    assert dx == pytest.approx((xr[1] - xr[0]) / 16)
    assert dy == pytest.approx((yr[1] - yr[0]) / 9)
    with pytest.raises(ValueError, match="at least one finite pair"):
        kernels.hexbin(np.array([np.nan]), np.array([np.nan]), gridsize=8)


def test_histogram_edges_match_numpy_auto() -> None:
    data = np.arange(1.0, 11.0)
    got = kernels.histogram_edges(data, method="auto")
    exp = np.histogram_bin_edges(data, bins="auto")
    np.testing.assert_allclose(got, exp, atol=1e-12)
    rng = np.random.default_rng(3)
    sample = rng.normal(size=200)
    got2 = kernels.histogram_edges(sample, method="auto")
    exp2 = np.histogram_bin_edges(sample, bins="auto")
    np.testing.assert_allclose(got2, exp2, atol=1e-10)
    sturges = kernels.histogram_edges(sample, method="sturges")
    exp_s = np.histogram_bin_edges(sample, bins="sturges")
    np.testing.assert_allclose(sturges, exp_s, atol=1e-10)


def test_histogram_edges_wide_range_and_resource_bound() -> None:
    data = np.array([0.0, 1.0])
    edges = kernels.histogram_edges(data, range=(-10.0, 10.0), method="auto")
    np.testing.assert_allclose(edges, np.linspace(-10.0, 10.0, 41))
    boundary = kernels.histogram_edges(data, range=(0.0, 5_000.0), method="auto")
    assert len(boundary) == 10_001
    with pytest.raises(ValueError, match="invalid histogram_edges arguments"):
        kernels.histogram_edges(data, range=(0.0, 5_000.5), method="auto")


def test_binned_ecdf_native_contract() -> None:
    x, cumulative = kernels.binned_ecdf(np.array([0.0, 0.2, np.nan, 0.2, 0.9]), 4)
    np.testing.assert_allclose(x, [0.0, 0.225, 0.9], atol=1e-15)
    np.testing.assert_array_equal(cumulative, [0.0, 0.75, 1.0])

    x, cumulative = kernels.binned_ecdf(
        np.array([-1.0, 0.25, 0.75, 2.0, np.inf]), 2, range=(0.0, 1.0)
    )
    np.testing.assert_array_equal(x, [0.0, 0.5, 1.0])
    np.testing.assert_array_equal(cumulative, [0.0, 0.25, 0.5])

    x, cumulative = kernels.binned_ecdf(np.array([-2.0, 2.0]), 4, range=(0.0, 1.0))
    np.testing.assert_array_equal(x, [0.0])
    np.testing.assert_array_equal(cumulative, [0.0])


def test_binned_ecdf_native_rejects_invalid_and_overflowing_inputs() -> None:
    with pytest.raises(ValueError, match="finite representable"):
        kernels.binned_ecdf(np.array([np.nan, np.inf]), 4)
    with pytest.raises(ValueError, match="<= 10000"):
        kernels.binned_ecdf(np.array([0.0]), 10_001)
    with pytest.raises(ValueError, match="finite representable"):
        kernels.binned_ecdf(np.array([-np.finfo(float).max, np.finfo(float).max]), 4)
    with pytest.raises(ValueError, match="finite representable"):
        kernels.binned_ecdf(np.array([0.0, 2.0e-309, 1.0e-308]), 2)


def _legacy_wind_rose_bins(directions, speeds, sectors, speed_bins=None):
    import math

    bearings = np.asarray(directions, dtype=float).reshape(-1)
    magnitudes = np.asarray(speeds, dtype=float).reshape(-1)
    finite = np.isfinite(bearings) & np.isfinite(magnitudes)
    bearings, magnitudes = bearings[finite], magnitudes[finite]
    if speed_bins is None:
        quartiles = np.quantile(magnitudes, [0.25, 0.5, 0.75, 1.0])
        edges = np.unique([float(f"{value:.3g}") for value in quartiles])
        top = float(magnitudes.max())
        if top > 0:
            unit = 10.0 ** (math.floor(math.log10(top)) - 2)
            edges[-1] = math.ceil(top / unit) * unit
    else:
        edges = np.unique(np.asarray(speed_bins, dtype=float).reshape(-1))
    width = 360.0 / sectors
    index = np.floor(((bearings % 360.0) + width / 2.0) / width).astype(int) % sectors
    centres = np.arange(sectors, dtype=float) * width
    counts = []
    lower = -np.inf
    for upper in edges:
        in_band = (magnitudes > lower) & (magnitudes <= upper)
        counts.append(np.bincount(index[in_band], minlength=sectors).astype(float))
        lower = upper
    return edges, centres, np.vstack(counts), len(bearings)


@pytest.mark.parametrize(
    "speed_bins",
    [None, [2.0], [10.0, 20.0, 30.0]],
)
def test_wind_rose_bins_match_legacy(speed_bins) -> None:
    rng = np.random.default_rng(4)
    directions = rng.uniform(0, 360, 200)
    speeds = rng.gamma(2.0, 2.0, 200)
    if speed_bins is not None:
        speeds = np.clip(speeds, None, speed_bins[-1])
    got_e, got_c, got_counts, n_obs = kernels.wind_rose_bins(
        directions, speeds, 8, None if speed_bins is None else np.asarray(speed_bins)
    )
    exp_e, exp_c, exp_counts, exp_n = _legacy_wind_rose_bins(directions, speeds, 8, speed_bins)
    np.testing.assert_allclose(got_e, exp_e, atol=1e-12)
    np.testing.assert_allclose(got_c, exp_c, atol=1e-12)
    np.testing.assert_allclose(got_counts, exp_counts, atol=1e-12)
    assert n_obs == exp_n


def test_contourf_densify_matches_legacy_small_grid() -> None:
    rows, cols = 3, 4
    z = np.arange(rows * cols, dtype=np.float64).reshape(rows, cols)
    xpos = np.linspace(0.0, 1.0, cols)
    ypos = np.linspace(0.0, 2.0, rows)
    got_z, got_x, got_y = kernels.contourf_densify(z, xpos, ypos)

    def sample_count(size: int) -> int:
        if size > 512:
            return size
        return min(512, max(256, (size - 1) * 8 + 1))

    out_rows, out_cols = sample_count(rows), sample_count(cols)
    row_at = np.linspace(0.0, rows - 1, out_rows)
    col_at = np.linspace(0.0, cols - 1, out_cols)
    row0 = np.floor(row_at).astype(np.intp)
    col0 = np.floor(col_at).astype(np.intp)
    row1 = np.minimum(row0 + 1, rows - 1)
    col1 = np.minimum(col0 + 1, cols - 1)
    row_weight = (row_at - row0)[:, None]
    col_weight = (col_at - col0)[None, :]
    z00 = z[row0[:, None], col0[None, :]]
    z10 = z[row0[:, None], col1[None, :]]
    z01 = z[row1[:, None], col0[None, :]]
    z11 = z[row1[:, None], col1[None, :]]
    exp = (
        z00 * (1.0 - row_weight) * (1.0 - col_weight)
        + z10 * (1.0 - row_weight) * col_weight
        + z01 * row_weight * (1.0 - col_weight)
        + z11 * row_weight * col_weight
    )
    exp_x = np.interp(col_at, np.arange(cols), xpos)
    exp_y = np.interp(row_at, np.arange(rows), ypos)
    np.testing.assert_allclose(got_z, exp, atol=1e-12)
    np.testing.assert_allclose(got_x, exp_x, atol=1e-12)
    np.testing.assert_allclose(got_y, exp_y, atol=1e-12)
