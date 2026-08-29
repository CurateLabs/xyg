"""ABI 248 Scene finite-all admit — wrapper over xyg_scene_finite_all."""

from __future__ import annotations

import pytest

from xyg import channels, kernels


def test_scene_finite_all_table() -> None:
    assert kernels.scene_finite_all([]) is True
    assert kernels.scene_finite_all([0.0, 1.5]) is True
    assert kernels.scene_finite_all([float("nan")]) is False
    assert kernels.scene_finite_all([float("inf")]) is False
    assert kernels.scene_finite_all([float("-inf")]) is False
    assert kernels.scene_finite_all([0.0, float("nan")]) is False


def test_resolve_style_channel_admits_finite_arrays() -> None:
    constant, channel = channels.resolve_style_channel([0.25, 0.9], 2, "opacity")
    assert constant is None
    assert channel is not None
    assert list(channel.values) == [0.25, 0.9]
    with pytest.raises(ValueError, match="must contain only finite values"):
        channels.resolve_style_channel([0.25, float("nan")], 2, "opacity")
    with pytest.raises(ValueError, match="must contain only finite values"):
        channels.resolve_style_channel([float("inf")], 1, "opacity")
