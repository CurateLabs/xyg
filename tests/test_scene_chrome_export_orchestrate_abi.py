"""ABI 308 scene chrome / XYAF / XYEF orchestration parity."""

from __future__ import annotations

import xyg._scene_v3 as scene
from xyg import kernels
from xyg._figure import Figure


def test_scene_xycf_figure_plan_attach_routes() -> None:
    plan = kernels.scene_xycf_figure_plan(show_legend=True, colorbar_ok=True, polar=False)
    assert plan["attach_legend"] is True
    assert plan["attach_colorbar"] is True
    plan = kernels.scene_xycf_figure_plan(show_legend=False, colorbar_ok=False, polar=True)
    assert plan["attach_legend"] is False
    assert plan["polar"] is True


def test_scene_xyaf_annotation_dispatch_wrapped_and_rule() -> None:
    text = kernels.scene_xyaf_annotation_dispatch_plan(
        kind="text",
        authored_wrap=False,
        layout_text=True,
    )
    assert text["wrapped"] is True
    assert text["pack_rule_dash"] is False

    rule = kernels.scene_xyaf_annotation_dispatch_plan(
        kind="rule",
        authored_wrap=False,
        layout_text=False,
    )
    assert rule["wrapped"] is False
    assert rule["pack_rule_dash"] is True
    assert rule["pack_axis"] is True


def test_scene_public_export_orchestration_routes() -> None:
    figure = kernels.scene_public_export_figure_plan(
        polar=True,
        has_chrome_styles=True,
        has_title_options=False,
    )
    assert figure["polar"] is True
    assert figure["has_chrome_styles"] is True

    scatter = kernels.scene_public_export_trace_dispatch_plan(
        kind="scatter",
        polar=False,
        use_density=True,
    )
    assert scatter["pack_density_blit"] is True

    polar_scatter = kernels.scene_public_export_trace_dispatch_plan(
        kind="scatter",
        polar=True,
        use_density=True,
    )
    assert polar_scatter["pack_density_blit"] is False

    hexbin = kernels.scene_public_export_trace_dispatch_plan(
        kind="hexbin",
        polar=False,
        use_density=False,
    )
    assert hexbin["pack_hexbin_pitch"] is True


def test_pack_chrome_and_export_use_orchestration() -> None:
    fig = Figure()
    fig.scatter([0.0, 1.0], [0.0, 1.0], name="s")
    chrome = scene._pack_chrome_facts(fig, width=400, height=300, margins=None, colorbar_ok=True)
    assert chrome.startswith(b"XYCF")
    export = scene._pack_public_export_support(fig, width=400, height=300)
    assert export.startswith(b"XYEP")
