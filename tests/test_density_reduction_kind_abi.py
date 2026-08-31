"""ABI 265 density_reduction_kind parity."""

from __future__ import annotations

from xyg import kernels


def test_density_reduction_kind_bin2d() -> None:
    assert kernels.density_reduction_kind(binning="exact") == kernels.DENSITY_REDUCTION_BIN2D


def test_density_reduction_kind_pyramid() -> None:
    assert (
        kernels.density_reduction_kind(binning="pyramid-L2")
        == kernels.DENSITY_REDUCTION_PYRAMID_COUNT
    )


def test_density_reduction_kind_pyramid_tiles() -> None:
    assert (
        kernels.density_reduction_kind(binning="pyramid-L0-tiles-upsampled")
        == kernels.DENSITY_REDUCTION_PYRAMID_COUNT
    )
