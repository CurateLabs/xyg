"""ABI 225 Scene tick-label anchor — wrapper over xyg_scene_tick_anchor."""

from __future__ import annotations

from xyg import kernels
from xyg._scene_v3 import _scene_tick_anchor_code


def test_scene_tick_anchor_table() -> None:
    assert kernels.scene_tick_anchor("start") == 0
    assert kernels.scene_tick_anchor("center") == 1
    assert kernels.scene_tick_anchor("middle") == 1
    assert kernels.scene_tick_anchor("end") == 2
    assert kernels.scene_tick_anchor("") is None
    assert kernels.scene_tick_anchor("foo") is None
    assert kernels.scene_tick_anchor("START") is None
    assert kernels.scene_tick_anchor("left") is None
    assert kernels.scene_tick_anchor(None) is None


def test_scene_tick_anchor_host_key_pick() -> None:
    assert _scene_tick_anchor_code({"tick_label_anchor": "end"}) == 2
    assert _scene_tick_anchor_code({"tick_label_anchor": "middle"}) == 1
    assert _scene_tick_anchor_code({"tick_label_anchor": "foo"}) is None
    assert _scene_tick_anchor_code({}) is None
