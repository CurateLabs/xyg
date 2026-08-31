"""ABI 229 Scene fill-gradient direction pack — wrapper over xyg_scene_gradient_dir."""

from __future__ import annotations

from xyg import kernels
from xyg._scene_v3 import _pack_gradient_spec


def test_scene_gradient_dir_table() -> None:
    assert kernels.scene_gradient_dir("down") == 0
    assert kernels.scene_gradient_dir("up") == 1
    assert kernels.scene_gradient_dir("right") == 2
    assert kernels.scene_gradient_dir("left") == 3
    assert kernels.scene_gradient_dir("") == 255
    assert kernels.scene_gradient_dir(None) == 255
    assert kernels.scene_gradient_dir("foo") == 255
    assert kernels.scene_gradient_dir("DOWN") == 255
    assert kernels.scene_gradient_dir("to bottom") == 255
    assert kernels.scene_gradient_dir("to-bottom") == 255


def test_pack_gradient_spec_uses_kernel_dir() -> None:
    payload = _pack_gradient_spec(
        {"space": "mark", "dir": "up", "stops": [[0.0, "red"], [1.0, "blue"]]}
    )
    assert payload is not None
    assert payload[1] == 1
    unknown = _pack_gradient_spec(
        {"space": "plot", "dir": "DOWN", "stops": [[0.0, "red"], [1.0, "blue"]]}
    )
    assert unknown is not None
    assert unknown[0] == 1
    assert unknown[1] == 255
