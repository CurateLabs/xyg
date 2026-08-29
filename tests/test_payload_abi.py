"""ABI 122 payload LOD/mask: Python host wrappers match the Rust goldens."""

from __future__ import annotations

import numpy as np

from xyg import kernels
from xyg._figure import Figure
from xyg.config import (
    DECIMATION_THRESHOLD,
    DIRECT_SOFT_CEILING,
    SCATTER_DENSITY_THRESHOLD,
)


def test_payload_tier_line_polar_skips_m4() -> None:
    assert kernels.payload_tier(0, DECIMATION_THRESHOLD) == 0
    assert kernels.payload_tier(0, DECIMATION_THRESHOLD + 1) == 1
    assert kernels.payload_tier(0, DECIMATION_THRESHOLD + 1, polar=True) == 0


def test_payload_tier_scatter_strict_gt_and_per_item_ceiling() -> None:
    assert kernels.payload_tier(1, SCATTER_DENSITY_THRESHOLD) == 0
    assert kernels.payload_tier(1, SCATTER_DENSITY_THRESHOLD + 1) == 2
    assert kernels.payload_tier(1, SCATTER_DENSITY_THRESHOLD + 1, per_item=True) == 0
    assert kernels.payload_tier(1, DIRECT_SOFT_CEILING + 1, per_item=True) == 2
    assert kernels.payload_tier(1, 10, force_density=1) == 2
    assert kernels.payload_tier(1, 10, polar=True, force_density=1) == 0
    assert kernels.payload_tier(1, 1_000_000, force_density=0) == 0


def test_payload_visible_mask_drops_nonpositive_on_log() -> None:
    x = np.array([1.0, -2.0, 3.0, 0.0, 5.0])
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    mask = kernels.payload_visible_mask(x, y, x_log=True)
    np.testing.assert_array_equal(mask, [True, False, True, False, True])
    assert not kernels.payload_visible_needed(
        x_log=False,
        y_log=False,
        prefiltered=True,
        x_has_nulls=False,
        y_has_nulls=False,
    )
    assert kernels.payload_visible_needed(
        x_log=True,
        y_log=False,
        prefiltered=True,
        x_has_nulls=False,
        y_has_nulls=False,
    )


def test_payload_visible_mask_y_log_and_base() -> None:
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 3.0])
    base = np.array([1.0, -1.0, np.nan])
    mask = kernels.payload_visible_mask(x, y, y_log=True, base=base)
    np.testing.assert_array_equal(mask, [True, False, False])
    linear = kernels.payload_visible_mask(x, y, base=base)
    np.testing.assert_array_equal(linear, [True, True, False])


def test_payload_m4_indices_polar_stays_direct() -> None:
    n = DECIMATION_THRESHOLD + 1
    x = np.arange(n, dtype=float)
    y = np.ones(n)
    tier, idx = kernels.payload_m4_indices(n, x, y, 0.0, float(n - 1), 64, polar=True)
    assert tier == 0
    assert len(idx) == 0


def test_payload_m4_indices_closed_window_matches_m4_plus_eps() -> None:
    n = DECIMATION_THRESHOLD + 1
    x = np.arange(n, dtype=float)
    y = np.sin(x)
    tier, idx = kernels.payload_m4_indices(n, x, y, 0.0, float(n - 1), 64)
    assert tier == 1
    expected = kernels.m4_indices(x, y, 0.0, float(n - 1) + np.finfo(np.float64).eps, 64)
    np.testing.assert_array_equal(idx, expected)
    empty_tier, empty_idx = kernels.payload_m4_indices(n, x, y, float(n + 10), float(n + 100), 64)
    assert empty_tier == 1
    assert len(empty_idx) == 0


def test_payload_visible_indices_keep_all_and_log_drop() -> None:
    x = np.array([1.0, -2.0, 3.0, 0.0, 5.0])
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    keep_all, idx = kernels.payload_visible_indices(
        x, y, x_log=False, prefiltered=True, x_has_nulls=False, y_has_nulls=False
    )
    assert keep_all
    assert len(idx) == 0
    keep_all, idx = kernels.payload_visible_indices(
        x, y, x_log=True, prefiltered=True, x_has_nulls=False, y_has_nulls=False
    )
    assert not keep_all
    np.testing.assert_array_equal(idx, [0, 2, 4])


def test_payload_even_indices_matches_numpy_int64_linspace() -> None:
    keep_all, idx = kernels.payload_even_indices(4, 10)
    assert keep_all
    keep_all, idx = kernels.payload_even_indices(11, 4)
    assert not keep_all
    np.testing.assert_array_equal(idx, np.linspace(0, 10, 4, dtype=np.int64))


def test_payload_segment_budget_matches_host_max() -> None:
    assert kernels.payload_segment_budget(100) == max(1024, 100 * 4)
    assert kernels.payload_segment_budget(256) == 1024
    assert kernels.payload_segment_budget(257) == 1028
    assert kernels.payload_segment_budget(256.9) == 1024
    assert kernels.payload_segment_budget(0) == 1024
    assert kernels.payload_segment_budget(-10.7) == 1024
    try:
        kernels.payload_segment_budget(float("nan"))
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_payload_errorbar_indices_expands_even_keep_across_roles() -> None:
    keep_all, idx = kernels.payload_errorbar_indices(33, 11, 20)
    assert keep_all
    keep_all, idx = kernels.payload_errorbar_indices(10, 3, 2)
    assert keep_all
    keep_all, idx = kernels.payload_errorbar_indices(33, 11, 4)
    assert not keep_all
    np.testing.assert_array_equal(idx, [0, 3, 6, 10, 11, 14, 17, 21, 22, 25, 28, 32])


def test_payload_sample_target_indices_keep_all() -> None:
    keep_all, idx = kernels.payload_sample_target_indices(100, 8_192)
    assert keep_all
    keep_all, idx = kernels.payload_sample_target_indices(10_000, 8_192)
    assert not keep_all
    assert 0 < len(idx) < 10_000


def test_polar_line_stays_direct_over_m4_threshold() -> None:
    n = DECIMATION_THRESHOLD + 1
    fig = Figure(coords="polar").line(np.arange(n, dtype=float), np.ones(n))
    spec, _blob = fig.build_payload()
    assert spec["traces"][0]["tier"] == "direct"
    assert spec["traces"][0]["n_marks"] == n
    update, _buffers = fig.decimate_view(0.0, float(n), 512)
    assert update["traces"] == []


def test_polar_scatter_stays_direct_even_when_density_forced() -> None:
    fig = Figure(coords="polar").scatter(np.arange(10.0), np.arange(10.0), density=True)
    spec, _blob = fig.build_payload()
    assert fig.traces[0].use_density()
    assert spec["traces"][0]["tier"] == "direct"
    assert spec["traces"][0]["n_marks"] == 10
