"""ABI 271 scene_xytc_color2_flags_pack parity."""

from __future__ import annotations

from xyg import kernels


def test_scene_xytc_color2_flags_pack_fail() -> None:
    assert kernels.scene_xytc_color2_flags_pack(4, 0, 0) == 1 << 13


def test_scene_xytc_color2_flags_pack_gradient_with_fill() -> None:
    assert kernels.scene_xytc_color2_flags_pack(2, 1 << 0, 0) == 1 << 13


def test_scene_xytc_color2_flags_pack_gradient_inject() -> None:
    assert kernels.scene_xytc_color2_flags_pack(2, 0, 1) == (1 << 0) | (1 << 19)


def test_scene_xytc_color2_flags_pack_gradient_missing_blob() -> None:
    assert kernels.scene_xytc_color2_flags_pack(2, 0, 0) == 1 << 13
