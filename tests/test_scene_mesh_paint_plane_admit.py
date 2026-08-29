"""ABI 244 Scene mesh paint-plane admit — wrapper over xyg_scene_mesh_paint_plane_admit."""

from __future__ import annotations

from xyg import kernels


def test_scene_mesh_paint_plane_admit_table() -> None:
    assert kernels.scene_mesh_paint_plane_admit("triangle_mesh", 0, 1) is True
    assert kernels.scene_mesh_paint_plane_admit("triangle_mesh", 0, 2) is True
    assert kernels.scene_mesh_paint_plane_admit("triangle_mesh", 1, 1) is False
    assert kernels.scene_mesh_paint_plane_admit("triangle_mesh", 0, 0) is False
    assert kernels.scene_mesh_paint_plane_admit("", 0, 1) is False
    assert kernels.scene_mesh_paint_plane_admit(None, 0, 1) is False
    assert kernels.scene_mesh_paint_plane_admit("TRIANGLE_MESH", 0, 1) is False
    assert kernels.scene_mesh_paint_plane_admit("scatter", 0, 1) is False
    assert kernels.scene_mesh_paint_plane_admit(" triangle_mesh", 0, 1) is False
