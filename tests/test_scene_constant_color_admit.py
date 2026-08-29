"""ABI 252 Scene constant-color admit — wrapper over xyg_scene_constant_color_admit."""

from __future__ import annotations

from xyg import kernels


def test_scene_constant_color_admit_table() -> None:
    assert kernels.scene_constant_color_admit(False, False, False, False) == 1
    assert kernels.scene_constant_color_admit(True, True, False, False) == 2
    assert kernels.scene_constant_color_admit(True, False, True, False) == 1
    assert kernels.scene_constant_color_admit(True, False, False, True) == 1
    assert kernels.scene_constant_color_admit(True, False, False, False) == 0
    assert kernels.scene_constant_color_admit(True, True, True, True) == 2
