"""Rust-owned first-paint density emit policy (ABI 132)."""

from __future__ import annotations

import pytest

from xyg import _native, kernels


def test_density_grid_path_truth_table() -> None:
    assert (
        kernels.density_grid_path(
            oversized=True,
            full_identity=True,
            point_overlay=True,
            compact_categorical=False,
            stratified_counts=False,
        )
        == _native.DENSITY_GRID_PATH_OVERSIZED_BIN2D
    )
    assert (
        kernels.density_grid_path(
            oversized=False,
            full_identity=True,
            point_overlay=False,
            compact_categorical=False,
            stratified_counts=False,
        )
        == _native.DENSITY_GRID_PATH_IDENTITY_GRID_ONLY
    )
    assert (
        kernels.density_grid_path(
            oversized=False,
            full_identity=True,
            point_overlay=True,
            compact_categorical=True,
            stratified_counts=True,
        )
        == _native.DENSITY_GRID_PATH_IDENTITY_STRATIFIED_FUSED
    )
    assert (
        kernels.density_grid_path(
            oversized=False,
            full_identity=True,
            point_overlay=True,
            compact_categorical=True,
            stratified_counts=False,
        )
        == _native.DENSITY_GRID_PATH_IDENTITY_STRATIFIED_SPLIT
    )
    assert (
        kernels.density_grid_path(
            oversized=False,
            full_identity=True,
            point_overlay=True,
            compact_categorical=False,
            stratified_counts=False,
        )
        == _native.DENSITY_GRID_PATH_IDENTITY_SAMPLE_FUSED
    )
    assert (
        kernels.density_grid_path(
            oversized=False,
            full_identity=False,
            point_overlay=True,
            compact_categorical=False,
            stratified_counts=False,
        )
        == _native.DENSITY_GRID_PATH_RANGE_INDICES
    )


def test_density_format_binning_strings() -> None:
    assert kernels.density_format_binning(exact=True) == "exact"
    assert kernels.density_format_binning(exact=False, level=2) == "pyramid-L2"
    assert (
        kernels.density_format_binning(exact=False, level=1, tiles=True, upsampled=True)
        == "pyramid-L1-tiles-upsampled"
    )


def test_density_emit_plan_overlay_and_wasm() -> None:
    plan = kernels.density_emit_plan(
        cartesian=True,
        x_linear=True,
        y_linear=True,
        categorical=False,
        compact_categorical=False,
        stratified_counts=False,
        x_has_nulls=False,
        y_has_nulls=False,
        point_overlay=False,
        grid_from_pyramid=False,
        x_memmapped=False,
        y_memmapped=False,
        has_pyramid_resource=False,
        color_mode=_native.DENSITY_COLOR_MODE_CONSTANT,
        x_min=0.0,
        x_max=1.0,
        y_min=0.0,
        y_max=1.0,
        xr0=0.0,
        xr1=2.0,
        yr0=0.0,
        yr1=2.0,
        x_c0=0.0,
        x_c1=2.0,
        y_c0=0.0,
        y_c1=2.0,
        n_points=100,
    )
    assert plan["overlay_omitted"] == _native.DENSITY_OVERLAY_STATIC_RASTER
    assert plan["wasm_eligible"] is True
    assert plan["grid_path"] == _native.DENSITY_GRID_PATH_IDENTITY_GRID_ONLY

    huge = kernels.density_emit_plan(
        cartesian=True,
        x_linear=True,
        y_linear=True,
        categorical=False,
        compact_categorical=False,
        stratified_counts=False,
        x_has_nulls=False,
        y_has_nulls=False,
        point_overlay=True,
        grid_from_pyramid=False,
        x_memmapped=False,
        y_memmapped=False,
        has_pyramid_resource=False,
        color_mode=_native.DENSITY_COLOR_MODE_NONE,
        x_min=0.0,
        x_max=1.0,
        y_min=0.0,
        y_max=1.0,
        xr0=0.0,
        xr1=2.0,
        yr0=0.0,
        yr1=2.0,
        x_c0=0.0,
        x_c1=2.0,
        y_c0=0.0,
        y_c1=2.0,
        n_points=(1 << 32),
    )
    assert huge["oversized"] is True
    assert huge["overlay_omitted"] == _native.DENSITY_OVERLAY_ROWS_EXCEED_U32
    assert huge["grid_path"] == _native.DENSITY_GRID_PATH_OVERSIZED_BIN2D


def test_density_pyramid_preflight_matches_config() -> None:
    pre = kernels.density_pyramid_preflight(
        x_linear=True,
        y_linear=True,
        n_points=2_000_000,
        has_pyramid_resource=True,
        x_memmapped=False,
        y_memmapped=False,
    )
    assert pre["eligible"] is True
    assert pre["attempt"] is True
    assert pre["max_upsample"] == 2
    assert pre["tile_upsample"] == 1_000_000

    no_rescan = kernels.density_pyramid_preflight(
        x_linear=True,
        y_linear=True,
        n_points=200_000_001,
        has_pyramid_resource=False,
        x_memmapped=False,
        y_memmapped=False,
    )
    assert no_rescan["eligible"] is True
    assert no_rescan["attempt"] is False
    assert no_rescan["no_rescan"] is True
    assert no_rescan["max_upsample"] == 1_000_000


@pytest.mark.parametrize(
    ("categorical", "compact", "expected"),
    [
        (False, False, True),
        (True, False, False),
        (True, True, True),
    ],
)
def test_density_full_identity(categorical: bool, compact: bool, expected: bool) -> None:
    assert (
        kernels.density_full_identity(
            categorical=categorical,
            compact_categorical=compact,
            x_has_nulls=False,
            y_has_nulls=False,
            x_min=0.0,
            x_max=1.0,
            y_min=0.0,
            y_max=1.0,
            xr0=0.0,
            xr1=2.0,
            yr0=0.0,
            yr1=2.0,
        )
        is expected
    )
