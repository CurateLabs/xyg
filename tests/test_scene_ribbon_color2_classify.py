"""ABI 223 Scene ribbon color2 classify — wrapper over xyg_scene_ribbon_color2_classify."""

from __future__ import annotations

from types import SimpleNamespace

from xyg import kernels
from xyg._scene_v3 import _classify_ribbon_color2


def test_scene_ribbon_color2_classify_table() -> None:
    assert (
        kernels.scene_ribbon_color2_classify(False, True, None, None, "#3987e5", False, False)
        == "absent"
    )
    assert (
        kernels.scene_ribbon_color2_classify(True, False, None, None, "#3987e5", False, False)
        == "fail"
    )
    assert (
        kernels.scene_ribbon_color2_classify(
            True, True, "#336699", "#336699", "#336699", False, False
        )
        == "solid"
    )
    assert (
        kernels.scene_ribbon_color2_classify(
            True, True, "#336699", "#34d399", "#336699", False, False
        )
        == "gradient"
    )
    assert (
        kernels.scene_ribbon_color2_classify(
            True, True, "#336699", "#34d399", "#336699", True, False
        )
        == "fail"
    )
    assert (
        kernels.scene_ribbon_color2_classify(True, True, None, "#34d399", "#336699", False, True)
        == "ends"
    )
    assert (
        kernels.scene_ribbon_color2_classify(True, True, None, None, "#336699", False, False)
        == "fail"
    )


def test_classify_ribbon_color2_host_coercion() -> None:
    absent = SimpleNamespace(kind="ribbon", color2_ch=None, color_ch=None, style={})
    assert _classify_ribbon_color2(absent) == "absent"
    not_ribbon = SimpleNamespace(
        kind="area",
        color2_ch=SimpleNamespace(mode="constant", constant="#34d399"),
        color_ch=SimpleNamespace(mode="constant", constant="#336699"),
        style={},
    )
    assert _classify_ribbon_color2(not_ribbon) == "fail"
    solid = SimpleNamespace(
        kind="ribbon",
        color2_ch=SimpleNamespace(mode="constant", constant="#336699"),
        color_ch=SimpleNamespace(mode="constant", constant="#336699"),
        style={},
    )
    assert _classify_ribbon_color2(solid) == "solid"
