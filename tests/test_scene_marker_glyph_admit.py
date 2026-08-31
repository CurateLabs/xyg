"""ABI 234 Scene marker-glyph admit — wrapper over xyg_scene_marker_glyph_admit."""

from __future__ import annotations

from xyg import kernels


def test_scene_marker_glyph_admit_table() -> None:
    assert kernels.scene_marker_glyph_admit("A") is True
    assert kernels.scene_marker_glyph_admit("\u03b1") is True
    assert kernels.scene_marker_glyph_admit("") is False
    assert kernels.scene_marker_glyph_admit(None) is False
    assert kernels.scene_marker_glyph_admit("a\0b") is False
    assert kernels.scene_marker_glyph_admit("a\nb") is False
    assert kernels.scene_marker_glyph_admit("a\rb") is False
    assert kernels.scene_marker_glyph_admit("x" * 64) is True
    assert kernels.scene_marker_glyph_admit("x" * 65) is False
