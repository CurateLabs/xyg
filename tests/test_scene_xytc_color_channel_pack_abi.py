"""ABI 263 scene_xytc_color_channel_pack parity."""

from __future__ import annotations

from xyg import kernels


def test_scene_xytc_color_channel_pack_absent() -> None:
    assert kernels.scene_xytc_color_channel_pack(0, 0) == 0


def test_scene_xytc_color_channel_pack_mode_only() -> None:
    assert kernels.scene_xytc_color_channel_pack(1, 0) == 1 << 11


def test_scene_xytc_color_channel_pack_with_constant() -> None:
    assert kernels.scene_xytc_color_channel_pack(1, 1) == (1 << 11) | (1 << 12)
