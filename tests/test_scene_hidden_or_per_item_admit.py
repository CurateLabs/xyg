"""ABI 253 Scene hidden-or-per-item admit — wrapper over xyg_scene_hidden_or_per_item_admit."""

from __future__ import annotations

from xyg import kernels


def test_scene_hidden_or_per_item_admit_table() -> None:
    assert kernels.scene_hidden_or_per_item_admit(False, False, False) is False
    assert kernels.scene_hidden_or_per_item_admit(True, False, False) is True
    assert kernels.scene_hidden_or_per_item_admit(False, True, False) is True
    assert kernels.scene_hidden_or_per_item_admit(False, True, True) is False
    assert kernels.scene_hidden_or_per_item_admit(True, True, True) is True
    assert kernels.scene_hidden_or_per_item_admit(False, False, True) is False
