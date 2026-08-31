"""ABI 273 density_channels_dropped_compat parity."""

from __future__ import annotations

from xyg import kernels


def test_density_channels_dropped_compat_empty() -> None:
    assert kernels.density_channels_dropped_compat(dropped_count=0) is False


def test_density_channels_dropped_compat_nonempty() -> None:
    assert kernels.density_channels_dropped_compat(dropped_count=1) is True
    assert kernels.density_channels_dropped_compat(dropped_count=3) is True


def test_density_channels_dropped_compat_negative() -> None:
    assert kernels.density_channels_dropped_compat(dropped_count=-1) is False
