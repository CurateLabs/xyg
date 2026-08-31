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


def test_pack_xytc_paint_presence_css_fill() -> None:
    from xyg import _scene_v3 as scene

    assert scene._pack_xytc_paint_presence({"fill": "#336699"}) == 1 << 0


def test_pack_xytc_paint_presence_gradient_fill() -> None:
    from xyg import _scene_v3 as scene

    flags = scene._pack_xytc_paint_presence(
        {
            "fill": {
                "space": "object",
                "dir": "right",
                "stops": [(0.0, "#000"), (1.0, "#fff")],
            }
        }
    )
    assert flags == (1 << 0) | (1 << 19)


def test_pack_xytc_paint_presence_stroke_and_line_color() -> None:
    from xyg import _scene_v3 as scene

    flags = scene._pack_xytc_paint_presence({"stroke": "#000", "line_color": "#111"})
    assert flags == (1 << 1) | (1 << 2)
