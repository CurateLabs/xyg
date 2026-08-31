"""ABI 271 density_categorical_color_wire_admit parity."""

from __future__ import annotations

from xyg import kernels


def test_density_categorical_color_wire_admit_both() -> None:
    assert (
        kernels.density_categorical_color_wire_admit(
            categorical=True,
            has_channel=True,
        )
        is True
    )


def test_density_categorical_color_wire_admit_not_categorical() -> None:
    assert (
        kernels.density_categorical_color_wire_admit(
            categorical=False,
            has_channel=True,
        )
        is False
    )


def test_density_categorical_color_wire_admit_no_channel() -> None:
    assert (
        kernels.density_categorical_color_wire_admit(
            categorical=True,
            has_channel=False,
        )
        is False
    )
