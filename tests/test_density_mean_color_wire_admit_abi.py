"""ABI 272 density_mean_color_wire_admit parity."""

from __future__ import annotations

from xyg import channels, kernels
from xyg.channels import ColorChannel


def test_density_mean_color_wire_admit_absent_channel() -> None:
    assert (
        kernels.density_mean_color_wire_admit(
            has_channel=False,
            mode="continuous",
        )
        is False
    )


def test_density_mean_color_wire_admit_constant() -> None:
    assert (
        kernels.density_mean_color_wire_admit(
            has_channel=True,
            mode="constant",
        )
        is False
    )


def test_density_mean_color_wire_admit_continuous() -> None:
    assert (
        kernels.density_mean_color_wire_admit(
            has_channel=True,
            mode="continuous",
        )
        is True
    )


def test_density_mean_color_wire_admit_categorical() -> None:
    assert (
        kernels.density_mean_color_wire_admit(
            has_channel=True,
            mode="categorical",
        )
        is True
    )


def test_density_mean_color_wire_admit_direct_rgba() -> None:
    assert (
        kernels.density_mean_color_wire_admit(
            has_channel=True,
            mode="direct_rgba",
        )
        is True
    )


def test_bins_mean_color_delegates_to_kernel() -> None:
    cc = ColorChannel(mode="categorical", categories=("a",), codes=None)
    assert channels.bins_mean_color(cc) is True
    assert channels.bins_mean_color(None) is False
