"""ABI 243 Scene hexbin RGBA-plane admit — wrapper over xyg_scene_hexbin_rgba_plane_admit."""

from __future__ import annotations

from xyg import kernels


def test_scene_hexbin_rgba_plane_admit_table() -> None:
    assert kernels.scene_hexbin_rgba_plane_admit("categorical") is True
    assert kernels.scene_hexbin_rgba_plane_admit("direct_rgba") is True
    assert kernels.scene_hexbin_rgba_plane_admit("") is False
    assert kernels.scene_hexbin_rgba_plane_admit(None) is False
    assert kernels.scene_hexbin_rgba_plane_admit("CATEGORICAL") is False
    assert kernels.scene_hexbin_rgba_plane_admit("continuous") is False
    assert kernels.scene_hexbin_rgba_plane_admit("direct-rgba") is False
