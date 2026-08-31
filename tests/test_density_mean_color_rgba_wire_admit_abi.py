"""ABI 275 density_mean_color_rgba_wire_admit parity."""

from __future__ import annotations

from xyg import kernels


def test_density_mean_color_rgba_wire_admit_pyramid() -> None:
    assert (
        kernels.density_mean_color_rgba_wire_admit(
            has_pyramid_rgba=True,
            has_bin_colors=False,
        )
        is True
    )


def test_density_mean_color_rgba_wire_admit_bin_colors() -> None:
    assert (
        kernels.density_mean_color_rgba_wire_admit(
            has_pyramid_rgba=False,
            has_bin_colors=True,
        )
        is True
    )


def test_density_mean_color_rgba_wire_admit_neither() -> None:
    assert (
        kernels.density_mean_color_rgba_wire_admit(
            has_pyramid_rgba=False,
            has_bin_colors=False,
        )
        is False
    )
