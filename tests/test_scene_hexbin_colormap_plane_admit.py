"""ABI 242 Scene hexbin colormap-plane admit — wrapper over xyg_scene_hexbin_colormap_plane_admit."""

from __future__ import annotations

from xyg import kernels


def test_scene_hexbin_colormap_plane_admit_table() -> None:
    assert kernels.scene_hexbin_colormap_plane_admit("continuous", 1) is True
    assert kernels.scene_hexbin_colormap_plane_admit("continuous", 0) is False
    assert kernels.scene_hexbin_colormap_plane_admit("", 1) is False
    assert kernels.scene_hexbin_colormap_plane_admit(None, 1) is False
    assert kernels.scene_hexbin_colormap_plane_admit("CONTINUOUS", 1) is False
    assert kernels.scene_hexbin_colormap_plane_admit("categorical", 1) is False
    assert kernels.scene_hexbin_colormap_plane_admit("direct_rgba", 1) is False
