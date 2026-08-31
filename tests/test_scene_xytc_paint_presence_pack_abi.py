"""ABI 269 scene_xytc_paint_presence_pack parity."""

from __future__ import annotations

from xyg import kernels


def test_scene_xytc_paint_presence_pack_stroke_line_only() -> None:
    assert kernels.scene_xytc_paint_presence_pack(0, 0, 1, 1) == (1 << 1) | (1 << 2)


def test_scene_xytc_paint_presence_pack_css_fill() -> None:
    assert kernels.scene_xytc_paint_presence_pack(1, 1, 0, 0) == 1 << 0


def test_scene_xytc_paint_presence_pack_gradient_fill() -> None:
    assert kernels.scene_xytc_paint_presence_pack(1, 2, 0, 0) == (1 << 0) | (1 << 19)


def test_scene_xytc_paint_presence_pack_fill_dict() -> None:
    assert kernels.scene_xytc_paint_presence_pack(1, 3, 0, 0) == (1 << 0) | (1 << 20)
