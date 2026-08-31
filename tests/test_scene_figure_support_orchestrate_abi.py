"""ABI 307 scene figure-support / XYCL / XYNM orchestration parity."""

from __future__ import annotations

import xyg._scene_v3 as scene
from xyg import kernels
from xyg._figure import Figure


def test_scene_figure_support_figure_plan_polar() -> None:
    plan = kernels.scene_figure_support_figure_plan(polar=True)
    assert plan["polar"] is True
    plan = kernels.scene_figure_support_figure_plan(polar=False)
    assert plan["polar"] is False


def test_scene_figure_support_trace_dispatch_kind_gates() -> None:
    scatter = kernels.scene_figure_support_trace_dispatch_plan(
        kind="scatter",
        marker_glyph_present=True,
        marker_path_present=False,
        curve_present=False,
        fill_present=True,
    )
    assert scatter["kind_class"] == kernels.scene_kind_class("scatter")
    assert scatter["probe_marker_glyph"] is True
    assert scatter["probe_curve_smooth"] is False
    assert scatter["probe_non_css_fill"] is True

    area = kernels.scene_figure_support_trace_dispatch_plan(
        kind="area",
        marker_glyph_present=False,
        marker_path_present=False,
        curve_present=True,
        fill_present=False,
    )
    assert area["probe_curve_smooth"] is True
    assert area["probe_rect_extra"] is False

    bar = kernels.scene_figure_support_trace_dispatch_plan(
        kind="bar",
        marker_glyph_present=False,
        marker_path_present=False,
        curve_present=False,
        fill_present=False,
    )
    assert bar["probe_rect_extra"] is True

    hexbin = kernels.scene_figure_support_trace_dispatch_plan(
        kind="hexbin",
        marker_glyph_present=False,
        marker_path_present=False,
        curve_present=False,
        fill_present=False,
    )
    assert hexbin["probe_hexbin_reduce"] is True

    heatmap = kernels.scene_figure_support_trace_dispatch_plan(
        kind="heatmap",
        marker_glyph_present=False,
        marker_path_present=False,
        curve_present=False,
        fill_present=False,
    )
    assert heatmap["probe_heatmap_colormap"] is True


def test_scene_xycl_and_xynm_figure_plans() -> None:
    xycl = kernels.scene_xycl_figure_plan(polar=True)
    assert xycl["polar"] is True
    xynm = kernels.scene_xynm_figure_plan(show_legend=False)
    assert xynm["show_legend"] is False


def test_pack_figure_support_and_attach_use_orchestration() -> None:
    fig = Figure()
    fig.scatter([0.0, 1.0], [0.0, 1.0], name="s")
    support = scene._pack_figure_support(fig, [], False)
    assert support.startswith(b"XYFS")
    columns = scene._pack_xycl(fig)
    assert columns.startswith(b"XYCL")
    names = scene._pack_xynm(fig)
    assert names.startswith(b"XYNM")
