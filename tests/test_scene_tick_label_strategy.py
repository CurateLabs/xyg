"""ABI 224 Scene tick-label strategy — wrapper over xyg_scene_tick_label_strategy."""

from __future__ import annotations

from xyg import kernels
from xyg._scene_v3 import _scene_tick_label_strategy


def test_scene_tick_label_strategy_table() -> None:
    assert kernels.scene_tick_label_strategy("auto") == 0
    assert kernels.scene_tick_label_strategy("hide") == 1
    assert kernels.scene_tick_label_strategy("rotate") == 2
    assert kernels.scene_tick_label_strategy("stagger") == 3
    assert kernels.scene_tick_label_strategy("preserve") == 4
    assert kernels.scene_tick_label_strategy("none") == 5
    assert kernels.scene_tick_label_strategy("off") == 6
    assert kernels.scene_tick_label_strategy("hide-overlap") == 0
    assert kernels.scene_tick_label_strategy("") == 0
    assert kernels.scene_tick_label_strategy("foo") == 0
    assert kernels.scene_tick_label_strategy("HIDE") == 0
    assert kernels.scene_tick_label_strategy(None) == 0


def test_scene_tick_label_strategy_host_key_pick() -> None:
    assert _scene_tick_label_strategy({"tick_label_strategy": "rotate"}) == "rotate"
    assert _scene_tick_label_strategy({"collision": "stagger"}) == "stagger"
    assert _scene_tick_label_strategy({"tick_label_strategy": "hide-overlap"}) == "auto"
    assert _scene_tick_label_strategy({}) == "auto"
