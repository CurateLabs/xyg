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


def test_polar_line_stays_direct_over_m4_threshold() -> None:
    n = DECIMATION_THRESHOLD + 1
    fig = Figure(coords="polar").line(np.arange(n, dtype=float), np.ones(n))
    spec, _blob = fig.build_payload()
    assert spec["traces"][0]["tier"] == "direct"
    assert spec["traces"][0]["n_marks"] == n


def test_polar_scatter_stays_direct_even_when_density_forced() -> None:
    fig = Figure(coords="polar").scatter(np.arange(10.0), np.arange(10.0), density=True)
    spec, _blob = fig.build_payload()
    assert fig.traces[0].use_density()
    assert spec["traces"][0]["tier"] == "direct"
    assert spec["traces"][0]["n_marks"] == 10
