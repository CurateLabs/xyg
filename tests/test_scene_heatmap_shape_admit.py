"""ABI 240 Scene heatmap shape admit — wrapper over xyg_scene_heatmap_shape_admit."""

from __future__ import annotations

from xyg import kernels


def test_scene_heatmap_shape_admit_table() -> None:
    assert kernels.scene_heatmap_shape_admit(1.0, 2.0) is True
    assert kernels.scene_heatmap_shape_admit(0.0, 2.0) is False
    assert kernels.scene_heatmap_shape_admit(1.0, 0.0) is False
    assert kernels.scene_heatmap_shape_admit(1.5, 2.0) is False
    assert kernels.scene_heatmap_shape_admit(float("nan"), 2.0) is False
    assert kernels.scene_heatmap_shape_admit(float("inf"), 2.0) is False
