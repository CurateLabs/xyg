"""ABI 241 Scene scatter paint-channel admit — wrapper over xyg_scene_scatter_paint_channel_admit."""

from __future__ import annotations

from xyg import kernels

_ADMITTED = ("color", "stroke", "stroke_width", "opacity", "artist_alpha")


def test_scene_scatter_paint_channel_admit_table() -> None:
    for name in _ADMITTED:
        assert kernels.scene_scatter_paint_channel_admit(name) is True
    assert kernels.scene_scatter_paint_channel_admit("") is False
    assert kernels.scene_scatter_paint_channel_admit(None) is False
    assert kernels.scene_scatter_paint_channel_admit("STROKE") is False
    assert kernels.scene_scatter_paint_channel_admit(" color") is False
    assert kernels.scene_scatter_paint_channel_admit("size") is False
    assert kernels.scene_scatter_paint_channel_admit("symbol") is False
