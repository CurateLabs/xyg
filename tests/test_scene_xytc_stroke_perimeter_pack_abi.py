"""ABI 265 scene_xytc_stroke_perimeter_pack parity."""

from __future__ import annotations

from xyg import kernels


def test_scene_xytc_stroke_perimeter_pack_non_band() -> None:
    assert kernels.scene_xytc_stroke_perimeter_pack(0, 1, 1, 1) == 0


def test_scene_xytc_stroke_perimeter_pack_absent() -> None:
    assert kernels.scene_xytc_stroke_perimeter_pack(1, 0, 0, 0) == 0


def test_scene_xytc_stroke_perimeter_pack_invalid() -> None:
    assert kernels.scene_xytc_stroke_perimeter_pack(1, 1, 0, 0) == 1 << 10


def test_scene_xytc_stroke_perimeter_pack_false() -> None:
    assert kernels.scene_xytc_stroke_perimeter_pack(1, 1, 1, 0) == 0


def test_scene_xytc_stroke_perimeter_pack_true() -> None:
    assert kernels.scene_xytc_stroke_perimeter_pack(1, 1, 1, 1) == 1 << 9
