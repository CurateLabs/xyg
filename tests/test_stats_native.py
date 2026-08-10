"""Native quantiles / Tukey box / violin / hexbin / histogram-edges parity."""

from __future__ import annotations

import numpy as np
import pytest

from xy import kernels
from xy.marks import _distribution_stats


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
