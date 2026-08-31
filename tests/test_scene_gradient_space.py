"""ABI 231 Scene fill-gradient space pack — wrapper over xyg_scene_gradient_space."""

from __future__ import annotations

from xyg import kernels
from xyg._scene_v3 import _pack_gradient_spec


def test_scene_gradient_space_table() -> None:
    assert kernels.scene_gradient_space("mark") == 0
    assert kernels.scene_gradient_space("plot") == 1
    assert kernels.scene_gradient_space("") == 255
    assert kernels.scene_gradient_space(None) == 255
    assert kernels.scene_gradient_space("foo") == 255
    assert kernels.scene_gradient_space("MARK") == 255


def test_pack_gradient_spec_uses_kernel_space() -> None:
    payload = _pack_gradient_spec(
        {"space": "plot", "dir": "up", "stops": [[0.0, "red"], [1.0, "blue"]]}
    )
    assert payload is not None
    assert payload[0] == 1
    unknown = _pack_gradient_spec(
        {"space": "MARK", "dir": "down", "stops": [[0.0, "red"], [1.0, "blue"]]}
    )
    assert unknown is not None
    assert unknown[0] == 255
    missing = _pack_gradient_spec({"dir": "down", "stops": [[0.0, "red"], [1.0, "blue"]]})
    assert missing is not None
    assert missing[0] == 255
