"""ABI 230 Scene linear-gradient CSS prefix — wrapper over xyg_scene_linear_gradient_prefix."""

from __future__ import annotations

from xyg import kernels
from xyg._scene_v3 import _fill_is_gradient_authoring


def test_scene_linear_gradient_prefix_table() -> None:
    assert kernels.scene_linear_gradient_prefix("linear-gradient(red, blue)") is True
    assert kernels.scene_linear_gradient_prefix("  LINEAR-GRADIENT(red, blue)  ") is True
    assert kernels.scene_linear_gradient_prefix("linear-gradient(45deg, red, blue)") is True
    assert kernels.scene_linear_gradient_prefix("linear-gradient(") is True
    assert kernels.scene_linear_gradient_prefix("radial-gradient(red, blue)") is False
    assert kernels.scene_linear_gradient_prefix("linear-gradient") is False
    assert kernels.scene_linear_gradient_prefix("") is False
    assert kernels.scene_linear_gradient_prefix(None) is False


def test_fill_is_gradient_authoring_host_coercion() -> None:
    assert _fill_is_gradient_authoring({"space": "mark", "dir": "down", "stops": []}) is True
    assert _fill_is_gradient_authoring("linear-gradient(red, blue)") is True
    assert _fill_is_gradient_authoring("  LINEAR-GRADIENT(red, blue)") is True
    assert _fill_is_gradient_authoring("radial-gradient(red, blue)") is False
    assert _fill_is_gradient_authoring("#3987e5") is False
    assert _fill_is_gradient_authoring(None) is False
    assert _fill_is_gradient_authoring(["linear-gradient(red, blue)"]) is False
