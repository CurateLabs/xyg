"""ABI 247 Scene item-fill unit-t — wrapper over xyg_scene_item_fill_t."""

from __future__ import annotations

from xyg import kernels


def test_scene_item_fill_t_table() -> None:
    domain = kernels.scene_item_fill_t([0.0, 10.0], 2, (0.0, 10.0))
    assert domain is not None
    assert list(domain) == [0.0, 1.0]
    equal = kernels.scene_item_fill_t([5.0, 5.0], 2, None)
    assert equal is not None
    assert list(equal) == [0.0, 0.0]
    assert kernels.scene_item_fill_t([float("nan")], 1, None) is None
    assert kernels.scene_item_fill_t([0.0], 2, None) is None
    clipped = kernels.scene_item_fill_t([-1.0], 1, (0.0, 1.0))
    assert clipped is not None
    assert clipped[0] == 0.0
    high = kernels.scene_item_fill_t([2.0], 1, (0.0, 1.0))
    assert high is not None
    assert high[0] == 1.0
