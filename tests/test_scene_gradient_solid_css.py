"""ABI 249 Scene gradient-solid CSS — wrapper over xyg_scene_gradient_solid_css."""

from __future__ import annotations

from xyg import kernels


def test_scene_gradient_solid_css_table() -> None:
    assert kernels.scene_gradient_solid_css([]) == "rgb(0,0,0)"
    assert kernels.scene_gradient_solid_css([1, 2, 3, 0, 10, 20, 30, 255]) == "rgb(10,20,30)"
    assert kernels.scene_gradient_solid_css([255, 0, 0, 1]) == "rgb(255,0,0)"
    assert kernels.scene_gradient_solid_css([1, 2, 3, 0]) == "rgb(0,0,0)"
    assert kernels.scene_gradient_solid_css([1, 2, 3]) is None
