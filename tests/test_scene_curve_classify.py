"""ABI 233 Scene curve-name classify — wrapper over xyg_scene_curve_classify."""

from __future__ import annotations

from xyg import kernels


def test_scene_curve_classify_table() -> None:
    assert kernels.scene_curve_classify("linear") == 0
    assert kernels.scene_curve_classify("smooth") == 1
    assert kernels.scene_curve_classify("LINEAR") == 0
    assert kernels.scene_curve_classify("SMOOTH") == 1
    assert kernels.scene_curve_classify("  Smooth  ") == 1
    assert kernels.scene_curve_classify("") == 255
    assert kernels.scene_curve_classify(None) == 255
    assert kernels.scene_curve_classify("foo") == 255
    assert kernels.scene_curve_classify("step") == 255
