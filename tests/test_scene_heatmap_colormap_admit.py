"""ABI 239 Scene heatmap colormap admit — wrapper over xyg_scene_heatmap_colormap_admit."""

from __future__ import annotations

from xyg import kernels


def test_scene_heatmap_colormap_admit_table() -> None:
    assert kernels.scene_heatmap_colormap_admit(0, 0, 0, 0) is False
    assert kernels.scene_heatmap_colormap_admit(1, 0, 0, 0) is True
    assert kernels.scene_heatmap_colormap_admit(0, 1, 0, 0) is True
    assert kernels.scene_heatmap_colormap_admit(0, 0, 1, 0) is True
    assert kernels.scene_heatmap_colormap_admit(0, 0, 0, 1) is True
    assert kernels.scene_heatmap_colormap_admit(1, 1, 1, 1) is True
