"""ABI 263 density_bin_coord_endpoints parity."""

from __future__ import annotations

from xyg import kernels


def test_density_bin_coord_endpoints_linear_x() -> None:
    x_c0, x_c1, y_c0, y_c1 = kernels.density_bin_coord_endpoints(
        x_linear=True,
        y_linear=False,
        xr0=0.0,
        xr1=10.0,
        yr0=1.0,
        yr1=9.0,
        bx0=2.0,
        bx1=8.0,
        by0=3.0,
        by1=7.0,
    )
    assert (x_c0, x_c1) == (0.0, 10.0)
    assert (y_c0, y_c1) == (3.0, 7.0)


def test_density_bin_coord_endpoints_nonlinear() -> None:
    x_c0, x_c1, y_c0, y_c1 = kernels.density_bin_coord_endpoints(
        x_linear=False,
        y_linear=False,
        xr0=0.0,
        xr1=10.0,
        yr0=1.0,
        yr1=9.0,
        bx0=2.0,
        bx1=8.0,
        by0=3.0,
        by1=7.0,
    )
    assert (x_c0, x_c1) == (2.0, 8.0)
    assert (y_c0, y_c1) == (3.0, 7.0)
