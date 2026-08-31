"""ABI 305 scene XYTC pack orchestration parity."""

from __future__ import annotations

import xyg._scene_v3 as scene
from xyg import kernels
from xyg._figure import Figure


def test_scene_xytc_figure_plan_show_legend() -> None:
    plan = kernels.scene_xytc_figure_plan(show_legend=True)
    assert plan["show_legend"] is True
    plan = kernels.scene_xytc_figure_plan(show_legend=False)
    assert plan["show_legend"] is False


def test_scene_xytc_trace_dispatch_scatter_glyph_and_density() -> None:
    plan = kernels.scene_xytc_trace_dispatch_plan(
        kind="scatter",
        marker_path_present=False,
        use_density=True,
        joined_fill=False,
    )
    assert plan["kind_class"] == kernels.scene_kind_class("scatter")
    assert plan["pack_opacity"] is True
    assert plan["pack_hex_pitch"] is False
    assert plan["pack_stroke_perimeter"] is False
    assert plan["pack_color2"] is False
    assert plan["pack_radius"] is False
    assert plan["marker_path_branch"] is False
    assert plan["marker_glyph_branch"] is True
    assert plan["meta_use_density"] is True
    assert plan["meta_joined_fill"] is False


def test_scene_xytc_trace_dispatch_ribbon_and_area() -> None:
    ribbon = kernels.scene_xytc_trace_dispatch_plan(
        kind="ribbon",
        marker_path_present=False,
        use_density=False,
        joined_fill=False,
    )
    assert ribbon["pack_color2"] is True
    assert ribbon["pack_stroke_perimeter"] is False

    area = kernels.scene_xytc_trace_dispatch_plan(
        kind="area",
        marker_path_present=False,
        use_density=False,
        joined_fill=False,
    )
    assert area["pack_stroke_perimeter"] is True
    assert area["pack_color2"] is False


def test_scene_xytc_trace_dispatch_bar_radius_and_hexbin_pitch() -> None:
    bar = kernels.scene_xytc_trace_dispatch_plan(
        kind="bar",
        marker_path_present=False,
        use_density=False,
        joined_fill=False,
    )
    assert bar["pack_radius"] is True

    hexbin = kernels.scene_xytc_trace_dispatch_plan(
        kind="hexbin",
        marker_path_present=False,
        use_density=False,
        joined_fill=False,
    )
    assert hexbin["pack_hex_pitch"] is True
    assert hexbin["pack_radius"] is False


def test_pack_xytc_uses_orchestration_kernel() -> None:
    fig = Figure()
    fig.show_legend = False
    fig.scatter([0.0, 1.0], [0.0, 1.0], name="s")
    packed = scene._pack_xytc(fig)
    assert packed.startswith(b"XYTC")
    assert int.from_bytes(packed[8:12], "little") == 1
