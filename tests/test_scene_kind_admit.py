"""ABI 235 Scene product-kind admit — wrapper over xyg_scene_kind_admit."""

from __future__ import annotations

from xyg import kernels

_ADMITTED = (
    "scatter",
    "line",
    "bar",
    "column",
    "histogram",
    "violin",
    "box",
    "segments",
    "errorbar",
    "stem",
    "contour",
    "box_whisker",
    "box_median",
    "area",
    "error_band",
    "ribbon",
    "triangle_mesh",
    "hexbin",
    "heatmap",
)


def test_scene_kind_admit_table() -> None:
    for name in _ADMITTED:
        assert kernels.scene_kind_admit(name) is True
    assert kernels.scene_kind_admit("") is False
    assert kernels.scene_kind_admit(None) is False
    assert kernels.scene_kind_admit("mark") is False
    assert kernels.scene_kind_admit("SCATTER") is False
    assert kernels.scene_kind_admit("pie") is False
    assert kernels.scene_kind_admit(" scatter") is False
