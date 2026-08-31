"""ABI 256 Scene channel-constant CSS — wrapper over xyg_scene_channel_constant_css."""

from __future__ import annotations

from xyg import kernels
from xyg._scene_v3 import _channel_constant_css


def test_scene_channel_constant_css_table() -> None:
    assert kernels.scene_channel_constant_css("constant", True, "red") == "red"
    assert kernels.scene_channel_constant_css("constant", True, "") == ""
    assert kernels.scene_channel_constant_css("constant", False, "red") is None
    assert kernels.scene_channel_constant_css("direct_rgba", True, "red") is None
    assert kernels.scene_channel_constant_css("", True, "red") is None
    assert kernels.scene_channel_constant_css("CONSTANT", True, "red") is None
    assert kernels.scene_channel_constant_css(None, True, "red") is None


def test_channel_constant_css_host_coercion() -> None:
    class Channel:
        def __init__(self, mode: object | None, constant: object | None) -> None:
            self.mode = mode
            self.constant = constant

    assert _channel_constant_css(Channel("constant", "red")) == "red"
    assert _channel_constant_css(Channel("constant", None)) is None
    assert _channel_constant_css(Channel("direct_rgba", "red")) is None
    assert _channel_constant_css("red") is None
    assert _channel_constant_css(None) is None
    assert _channel_constant_css(Channel("constant", 12)) == "12"
    colored = Channel("constant", None)
    colored.color = "red"  # type: ignore[attr-defined]
    assert _channel_constant_css(colored) is None
