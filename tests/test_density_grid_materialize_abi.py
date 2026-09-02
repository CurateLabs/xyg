"""ABI 316 payload_density_grid_materialize parity with the Rust engine golden."""

from __future__ import annotations

import hashlib

import numpy as np

from xyg import _native, kernels


def _identity_materialize(*, n_points: int = 2):
    x = np.array([0.25, 0.75], dtype=np.float64)
    y = np.array([0.25, 0.75], dtype=np.float64)
    emit_plan = kernels.density_emit_plan(
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
        force_bin2d=False,
        force_pyramid=False,
        color_mode=_native.DENSITY_COLOR_MODE_NONE,
        x_min=0.0,
        x_max=1.0,
        y_min=0.0,
        y_max=1.0,
        xr0=0.0,
        xr1=1.0,
        yr0=0.0,
        yr1=1.0,
        x_c0=0.0,
        x_c1=1.0,
        y_c0=0.0,
        y_c1=1.0,
        n_points=n_points,
    )
    return kernels.payload_density_grid_materialize(
        emit_plan=emit_plan,
        n_points=n_points,
        bx0=0.0,
        bx1=1.0,
        by0=0.0,
        by1=1.0,
        xr0=0.0,
        xr1=1.0,
        yr0=0.0,
        yr1=1.0,
        w=4,
        h=4,
        x_raw=x,
        y_raw=y,
        bx=x,
        by=y,
    )


def test_payload_density_grid_materialize_identity_grid_only() -> None:
    out = _identity_materialize()
    assert out["encoded_grid"].shape == (16,)
    assert out["gmax"] >= 0.0
    assert out["binning"] == "exact"
    assert out["grid_from_pyramid"] is False
    assert out["visible"] == 2
    assert out["sample_sel"] is not None


def test_payload_density_grid_materialize_encoded_grid_sha256() -> None:
    out = _identity_materialize()
    digest = hashlib.sha256(out["encoded_grid"].tobytes()).hexdigest()
    assert digest == "869fa620d856999a98545e45e52b9fa13e793d05b168b54bcb12ea6108f3efc4"


def test_payload_density_grid_materialize_matches_host_log_u8_path() -> None:
    x = np.array([0.25, 0.75], dtype=np.float64)
    y = np.array([0.25, 0.75], dtype=np.float64)
    grid = kernels.bin_2d(x, y, 0.0, 1.0, 0.0, 1.0, 4, 4)
    encoded, gmax = kernels.density_log_u8(grid)
    out = _identity_materialize()
    np.testing.assert_array_equal(out["encoded_grid"], encoded.reshape(-1))
    assert out["gmax"] == gmax
