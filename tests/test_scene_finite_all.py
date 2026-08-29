"""ABI 248 Scene finite-all admit — wrapper over xyg_scene_finite_all."""

from __future__ import annotations

from xyg import kernels


def test_scene_finite_all_table() -> None:
    assert kernels.scene_finite_all([]) is True
    assert kernels.scene_finite_all([0.0, 1.5]) is True
    assert kernels.scene_finite_all([float("nan")]) is False
    assert kernels.scene_finite_all([float("inf")]) is False
    assert kernels.scene_finite_all([float("-inf")]) is False
    assert kernels.scene_finite_all([0.0, float("nan")]) is False
