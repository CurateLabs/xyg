"""ABI 219 Scene linecap admit — Python host wrapper over xyg_scene_linecap_admit."""

from __future__ import annotations

from xyg import kernels
from xyg._scene_v3 import _parse_scene_linecap


def test_scene_linecap_admit_names_and_reject() -> None:
    assert kernels.scene_linecap_admit("butt") == 0
    assert kernels.scene_linecap_admit("square") == 2
    assert kernels.scene_linecap_admit("round") is None
    assert kernels.scene_linecap_admit("SOLID") is False
    assert kernels.scene_linecap_admit("foo") is False
    assert kernels.scene_linecap_admit("") is None
    assert kernels.scene_linecap_admit("  ") is False


def test_parse_scene_linecap_host_coercion() -> None:
    assert _parse_scene_linecap(None) is None
    assert _parse_scene_linecap("") is False
    assert _parse_scene_linecap("  ") is False
    assert _parse_scene_linecap("Butt") == 0
    assert _parse_scene_linecap("SQUARE") == 2
    assert _parse_scene_linecap(" round ") is None
    assert _parse_scene_linecap("foo") is False
    assert _parse_scene_linecap(object()) is False
