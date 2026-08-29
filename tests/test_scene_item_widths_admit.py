"""ABI 246 Scene item-widths admit — wrapper over xyg_scene_item_widths_admit."""

from __future__ import annotations

from xyg import kernels


def test_scene_item_widths_admit_table() -> None:
    assert kernels.scene_item_widths_admit([0.0, 1.5], 2, 0.0) is True
    assert kernels.scene_item_widths_admit([], 0, 0.0) is True
    assert kernels.scene_item_widths_admit([0.0], 2, 0.0) is False
    assert kernels.scene_item_widths_admit([-0.1], 1, 0.0) is False
    assert kernels.scene_item_widths_admit([float("nan")], 1, 0.0) is False
    assert kernels.scene_item_widths_admit(None, 3, 0.0) is True
    assert kernels.scene_item_widths_admit(None, 3, 2.5) is True
    assert kernels.scene_item_widths_admit(None, 3, -1.0) is False
    assert kernels.scene_item_widths_admit(None, 3, float("inf")) is False
