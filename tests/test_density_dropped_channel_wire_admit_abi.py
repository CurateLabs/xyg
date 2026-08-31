"""ABI 274 density_dropped_channel_wire_admit parity."""

from __future__ import annotations

from xyg import kernels


def test_density_dropped_channel_wire_admit_color_aggregated() -> None:
    assert (
        kernels.density_dropped_channel_wire_admit(
            channel="color",
            mean_color_aggregates=True,
        )
        is False
    )


def test_density_dropped_channel_wire_admit_color_not_aggregated() -> None:
    assert (
        kernels.density_dropped_channel_wire_admit(
            channel="color",
            mean_color_aggregates=False,
        )
        is True
    )


def test_density_dropped_channel_wire_admit_other_channel() -> None:
    assert (
        kernels.density_dropped_channel_wire_admit(
            channel="size",
            mean_color_aggregates=True,
        )
        is True
    )
