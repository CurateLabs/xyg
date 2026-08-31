"""ABI 264 density_uses_channel_colormap parity."""

from __future__ import annotations

from xyg import kernels


def test_density_uses_channel_colormap_absent() -> None:
    assert kernels.density_uses_channel_colormap(has_channel=False, mode="constant") is False


def test_density_uses_channel_colormap_constant() -> None:
    assert kernels.density_uses_channel_colormap(has_channel=True, mode="constant") is True


def test_density_uses_channel_colormap_continuous() -> None:
    assert kernels.density_uses_channel_colormap(has_channel=True, mode="continuous") is True


def test_density_uses_channel_colormap_categorical() -> None:
    assert kernels.density_uses_channel_colormap(has_channel=True, mode="categorical") is False
