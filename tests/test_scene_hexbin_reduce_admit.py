"""ABI 232 Scene hexbin reduce admit — wrapper over xyg_scene_hexbin_reduce_admit."""

from __future__ import annotations

from xyg import kernels


def test_scene_hexbin_reduce_admit_table() -> None:
    assert kernels.scene_hexbin_reduce_admit("count") is True
    assert kernels.scene_hexbin_reduce_admit("mean") is True
    assert kernels.scene_hexbin_reduce_admit("sum") is True
    assert kernels.scene_hexbin_reduce_admit("custom") is True
    assert kernels.scene_hexbin_reduce_admit("") is False
    assert kernels.scene_hexbin_reduce_admit(None) is False
    assert kernels.scene_hexbin_reduce_admit("foo") is False
    assert kernels.scene_hexbin_reduce_admit("COUNT") is False
    assert kernels.scene_hexbin_reduce_admit("median") is False
