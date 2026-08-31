"""ABI 238 Scene heatmap extent admit — wrapper over xyg_scene_heatmap_extent_admit."""

from __future__ import annotations

from xyg import kernels


def test_scene_heatmap_extent_admit_table() -> None:
    assert kernels.scene_heatmap_extent_admit(0.0, 1.0, 0.0, 1.0) is True
    assert kernels.scene_heatmap_extent_admit(0.0, 0.0, 0.0, 1.0) is False
    assert kernels.scene_heatmap_extent_admit(0.0, 1.0, 0.0, 0.0) is False
    assert kernels.scene_heatmap_extent_admit(1.0, 0.0, 0.0, 1.0) is False
    assert kernels.scene_heatmap_extent_admit(float("nan"), 1.0, 0.0, 1.0) is False
    assert kernels.scene_heatmap_extent_admit(0.0, float("inf"), 0.0, 1.0) is False
