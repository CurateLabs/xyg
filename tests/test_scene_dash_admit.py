"""ABI 218 Scene dash admit — Python host wrapper over xyg_scene_dash_admit."""

from __future__ import annotations

from xyg import kernels
from xyg._scene_v3 import _parse_scene_dash


def test_scene_dash_admit_presets_and_reject() -> None:
    assert kernels.scene_dash_admit("dashed") == [6.0, 4.0]
    assert kernels.scene_dash_admit("dotted") == [1.5, 3.0]
    assert kernels.scene_dash_admit("dashdot") == [6.0, 3.0, 1.5, 3.0]
    assert kernels.scene_dash_admit("solid") is None
    assert kernels.scene_dash_admit("6,foo,4") is False
    assert kernels.scene_dash_admit("", [6.0, 4.0], use_lengths=True) == [6.0, 4.0]
    assert kernels.scene_dash_admit("", [], use_lengths=True) is False


def test_parse_scene_dash_host_coercion() -> None:
    assert _parse_scene_dash(None) is None
    assert _parse_scene_dash("") is False
    assert _parse_scene_dash("Dashed") == [6.0, 4.0]
    assert _parse_scene_dash([6, 4]) == [6.0, 4.0]
    assert _parse_scene_dash([6.0]) is False
    assert _parse_scene_dash("6,foo,4") is False
    assert _parse_scene_dash(object()) is False
