"""ABI 306 scene XYTA pack orchestration parity."""

from __future__ import annotations

import xyg._scene_v3 as scene
from xyg import kernels
from xyg._figure import Figure


def test_scene_xyta_figure_plan_polar() -> None:
    plan = kernels.scene_xyta_figure_plan(polar=True)
    assert plan["polar"] is True
    plan = kernels.scene_xyta_figure_plan(polar=False)
    assert plan["polar"] is False


def test_scene_xyta_trace_dispatch_heatmap_and_density() -> None:
    heatmap = kernels.scene_xyta_trace_dispatch_plan(
        kind="heatmap",
        polar=False,
        use_density=False,
        hexbin_colormap_plane=True,
        hexbin_rgba_plane_ready=True,
        ribbon_color2_class=3,
        mesh_paint_plane=True,
        scatter_paint_plane=True,
    )
    assert heatmap["kind_class"] == kernels.scene_kind_class("heatmap")
    assert heatmap["pack_heatmap"] is True
    assert heatmap["pack_density"] is False

    density = kernels.scene_xyta_trace_dispatch_plan(
        kind="scatter",
        polar=False,
        use_density=True,
        hexbin_colormap_plane=False,
        hexbin_rgba_plane_ready=False,
        ribbon_color2_class=0,
        mesh_paint_plane=False,
        scatter_paint_plane=False,
    )
    assert density["pack_density"] is True
    assert density["pack_scatter_paint"] is False


def test_scene_xyta_trace_dispatch_hexbin_and_ribbon() -> None:
    hex_cmap = kernels.scene_xyta_trace_dispatch_plan(
        kind="hexbin",
        polar=False,
        use_density=False,
        hexbin_colormap_plane=True,
        hexbin_rgba_plane_ready=True,
        ribbon_color2_class=0,
        mesh_paint_plane=False,
        scatter_paint_plane=False,
    )
    assert hex_cmap["pack_hexbin_colormap"] is True
    assert hex_cmap["pack_hexbin_rgba"] is False

    hex_rgba = kernels.scene_xyta_trace_dispatch_plan(
        kind="hexbin",
        polar=False,
        use_density=False,
        hexbin_colormap_plane=False,
        hexbin_rgba_plane_ready=True,
        ribbon_color2_class=0,
        mesh_paint_plane=False,
        scatter_paint_plane=False,
    )
    assert hex_rgba["pack_hexbin_rgba"] is True

    ribbon = kernels.scene_xyta_trace_dispatch_plan(
        kind="ribbon",
        polar=False,
        use_density=False,
        hexbin_colormap_plane=False,
        hexbin_rgba_plane_ready=False,
        ribbon_color2_class=3,
        mesh_paint_plane=False,
        scatter_paint_plane=False,
    )
    assert ribbon["pack_ribbon_ends"] is True

    polar_ribbon = kernels.scene_xyta_trace_dispatch_plan(
        kind="ribbon",
        polar=True,
        use_density=False,
        hexbin_colormap_plane=False,
        hexbin_rgba_plane_ready=False,
        ribbon_color2_class=3,
        mesh_paint_plane=False,
        scatter_paint_plane=False,
    )
    assert polar_ribbon["pack_ribbon_ends"] is False


def test_scene_xyta_trace_dispatch_mesh_and_scatter_paint() -> None:
    mesh = kernels.scene_xyta_trace_dispatch_plan(
        kind="triangle_mesh",
        polar=False,
        use_density=False,
        hexbin_colormap_plane=False,
        hexbin_rgba_plane_ready=False,
        ribbon_color2_class=0,
        mesh_paint_plane=True,
        scatter_paint_plane=False,
    )
    assert mesh["pack_mesh_faces"] is True

    scatter = kernels.scene_xyta_trace_dispatch_plan(
        kind="scatter",
        polar=False,
        use_density=False,
        hexbin_colormap_plane=False,
        hexbin_rgba_plane_ready=False,
        ribbon_color2_class=0,
        mesh_paint_plane=False,
        scatter_paint_plane=True,
    )
    assert scatter["pack_scatter_paint"] is True


def test_pack_xyta_uses_orchestration_kernel() -> None:
    fig = Figure()
    fig.heatmap([[0.0, 1.0], [2.0, 3.0]], x=[0.0, 1.0], y=[0.0, 1.0])
    packed = scene._pack_xyta(fig)
    assert packed.startswith(b"XYTA")
