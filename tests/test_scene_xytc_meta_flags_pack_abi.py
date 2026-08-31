"""ABI 270 scene_xytc_meta_flags_pack parity."""

from __future__ import annotations

from xyg import kernels


def test_scene_xytc_meta_flags_pack_scatter_density() -> None:
    assert kernels.scene_xytc_meta_flags_pack(1, 1, "scatter", 1, 0, 0, 0, 0) == (1 << 16) | (
        1 << 15
    ) | (1 << 14)


def test_scene_xytc_meta_flags_pack_joined_fill() -> None:
    assert kernels.scene_xytc_meta_flags_pack(0, 0, "triangle_mesh", 0, 1, 0, 0, 0) == 1 << 25


def test_scene_xytc_meta_flags_pack_marker() -> None:
    assert kernels.scene_xytc_meta_flags_pack(0, 0, "scatter", 0, 0, 1, 1, 0) == 1 << 18


def test_scene_xytc_meta_flags_pack_glyph() -> None:
    assert kernels.scene_xytc_meta_flags_pack(0, 0, "scatter", 0, 0, 0, 0, 1) == 1 << 24


def test_pack_xytc_meta_flags_name_and_legend() -> None:
    from types import SimpleNamespace

    from xyg import _scene_v3 as scene

    trace = SimpleNamespace(kind="line", name="series-a", style={}, use_density=lambda: False)
    assert scene._pack_xytc_meta_flags(
        trace, True, marker_path_present=0, marker_packed=0, glyph_packed=0
    ) == (1 << 16) | (1 << 15)


def test_pack_xytc_meta_flags_joined_fill() -> None:
    from types import SimpleNamespace

    from xyg import _scene_v3 as scene

    trace = SimpleNamespace(
        kind="triangle_mesh",
        name=None,
        style={"joined_fill": True},
        use_density=lambda: False,
    )
    assert scene._pack_xytc_meta_flags(
        trace, False, marker_path_present=0, marker_packed=0, glyph_packed=0
    ) == (1 << 25)
