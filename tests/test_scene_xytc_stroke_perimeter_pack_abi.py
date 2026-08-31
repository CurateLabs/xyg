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


def test_pack_xytc_stroke_perimeter_delegates_to_kernel() -> None:
    from xyg import _scene_v3 as scene

    assert scene._pack_xytc_stroke_perimeter(scene._SCENE_KIND_CLASS_BAND, {}) == 0
    assert (
        scene._pack_xytc_stroke_perimeter(
            scene._SCENE_KIND_CLASS_BAND,
            {"stroke_perimeter": "yes"},
        )
        == 1 << 10
    )
    assert (
        scene._pack_xytc_stroke_perimeter(
            scene._SCENE_KIND_CLASS_BAND,
            {"stroke_perimeter": True},
        )
        == 1 << 9
    )
