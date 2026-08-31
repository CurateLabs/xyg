"""ABI 268 density_constant_color_wire_admit parity."""

from __future__ import annotations

from xyg import kernels


def test_density_constant_color_wire_admit_absent_channel() -> None:
    assert (
        kernels.density_constant_color_wire_admit(
            has_channel=False,
            mode="constant",
            has_constant=True,
        )
        is False
    )


def test_density_constant_color_wire_admit_missing_constant() -> None:
    assert (
        kernels.density_constant_color_wire_admit(
            has_channel=True,
            mode="constant",
            has_constant=False,
        )
        is False
    )


def test_density_constant_color_wire_admit_constant() -> None:
    assert (
        kernels.density_constant_color_wire_admit(
            has_channel=True,
            mode="constant",
            has_constant=True,
        )
        is True
    )


def test_density_constant_color_wire_admit_continuous() -> None:
    assert (
        kernels.density_constant_color_wire_admit(
            has_channel=True,
            mode="continuous",
            has_constant=True,
        )
        is False
    )
