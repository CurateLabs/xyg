"""ABI 267 scene_xytc_opacity_pack parity."""

from __future__ import annotations

from xyg import kernels


def test_scene_xytc_opacity_pack_defaults() -> None:
    assert kernels.scene_xytc_opacity_pack(0, 0, 0.5, 0.6, 0.7) == (1.0, 1.0, 1.0)


def test_scene_xytc_opacity_pack_opacity_class() -> None:
    assert kernels.scene_xytc_opacity_pack(1, 0, 0.5, 0.6, 0.7) == (0.5, 0.6, 1.0)


def test_scene_xytc_opacity_pack_band_class() -> None:
    assert kernels.scene_xytc_opacity_pack(0, 1, 0.5, 0.6, 0.7) == (1.0, 1.0, 0.7)
