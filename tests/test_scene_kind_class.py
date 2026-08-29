"""ABI 236 Scene packing-family classify — wrapper over xyg_scene_kind_class."""

from __future__ import annotations

from xyg import kernels


def test_scene_kind_class_table() -> None:
    assert kernels.scene_kind_class("bar") == 1 << 0
    assert kernels.scene_kind_class("segments") == (1 << 1) | (1 << 7)
    assert kernels.scene_kind_class("area") == 1 << 2
    assert kernels.scene_kind_class("ribbon") == 1 << 3
    assert kernels.scene_kind_class("triangle_mesh") == 1 << 4
    assert kernels.scene_kind_class("hexbin") == 1 << 5
    assert kernels.scene_kind_class("heatmap") == 1 << 6
    assert kernels.scene_kind_class("scatter") == 1 << 8
    assert kernels.scene_kind_class("line") == (1 << 9) | (1 << 7)
    assert kernels.scene_kind_class("") == 0
    assert kernels.scene_kind_class(None) == 0
    assert kernels.scene_kind_class("mark") == 0
    assert kernels.scene_kind_class("SCATTER") == 0
    assert kernels.scene_kind_class("BAR") == 0
