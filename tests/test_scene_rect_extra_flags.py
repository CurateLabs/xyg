"""ABI 228 Scene rect extra flags — wrapper over xyg_scene_rect_extra_flags."""

from __future__ import annotations

from xyg import kernels
from xyg._scene_v3 import (
    _XYFS_TRACE_CORNER_RADIUS,
    _XYFS_TRACE_RECT_GRADIENT,
    _XYFS_TRACE_WEDGE_GAP,
    _rect_extra_flags,
)


def test_scene_rect_extra_flags_table() -> None:
    assert kernels.scene_rect_extra_flags("bar", False, False, [0.0], False, 0.0) == 0
    assert (
        kernels.scene_rect_extra_flags("bar", False, True, [0.0], False, 0.0)
        == _XYFS_TRACE_RECT_GRADIENT
    )
    assert kernels.scene_rect_extra_flags("bar", False, False, [1.0, 2.0], True, 0.0) == 0
    assert (
        kernels.scene_rect_extra_flags("bar", False, False, [1.0], True, 0.0)
        == _XYFS_TRACE_CORNER_RADIUS
    )
    assert (
        kernels.scene_rect_extra_flags("line", False, False, [3.0], False, 0.0)
        == _XYFS_TRACE_CORNER_RADIUS
    )
    assert (
        kernels.scene_rect_extra_flags("bar", False, False, [0.0], False, 0.2)
        == _XYFS_TRACE_WEDGE_GAP
    )
    assert kernels.scene_rect_extra_flags("bar", True, False, [0.0], False, 0.2) == 0
    assert (
        kernels.scene_rect_extra_flags("heatmap", True, False, [0.0], False, 0.2)
        == _XYFS_TRACE_WEDGE_GAP
    )


def test_rect_extra_flags_host_coercion() -> None:
    assert _rect_extra_flags({}, "bar", False) == 0
    assert _rect_extra_flags({"corner_radius": [1.0]}, "bar", False) == _XYFS_TRACE_CORNER_RADIUS
    assert _rect_extra_flags({"corner_radius": [1.0, 2.0]}, "bar", False) == 0
    assert _rect_extra_flags({"wedge_gap": 0.2}, "bar", True) == 0
    assert _rect_extra_flags({"wedge_gap": 0.2}, "heatmap", True) == _XYFS_TRACE_WEDGE_GAP
    rejected = _rect_extra_flags(
        {"fill": {"gradient": "linear-gradient(45deg, red, blue)"}}, "bar", False
    )
    assert rejected == _XYFS_TRACE_RECT_GRADIENT
