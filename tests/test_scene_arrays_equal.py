"""ABI 250 Scene f64 arrays-equal — wrapper over xyg_scene_arrays_equal."""

from __future__ import annotations

from xyg import kernels


def test_scene_arrays_equal_table() -> None:
    assert kernels.scene_arrays_equal([], []) is True
    assert kernels.scene_arrays_equal([1.0, 2.0], [1.0, 2.0]) is True
    assert kernels.scene_arrays_equal([1.0], [1.0, 2.0]) is False
    assert kernels.scene_arrays_equal([1.0], [2.0]) is False
    assert kernels.scene_arrays_equal([float("nan")], [float("nan")]) is False
    assert kernels.scene_arrays_equal([0.0], [-0.0]) is True
