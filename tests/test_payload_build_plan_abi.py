"""ABI 303 payload_build_plan parity."""

from __future__ import annotations

from xyg import kernels
from xyg._figure import Figure


def test_payload_build_plan_always_attaches_show_legend() -> None:
    plan = kernels.payload_build_plan(
        split_payload=False,
        wasm_source_count=0,
        has_density_tier=False,
        coords_cartesian=True,
        has_title_options=False,
        has_palette=False,
        has_legend_options=False,
        legend_loc_best=False,
        has_extra_legends=False,
        has_frame_sides=False,
        has_colorbar_options=False,
        show_modebar_is_false=False,
        has_export_options=False,
        show_tooltip_is_false=False,
        has_padding=False,
        has_dom=False,
        has_tooltip=False,
        has_mark_style=False,
        has_interaction=False,
        has_annotations=False,
        has_animation_options=False,
        has_graph_meta=False,
    )
    assert plan["attach_show_legend"] is True
    assert plan["wasm_density_kind"] == kernels.DENSITY_WASM_DENSITY_NONE
    assert plan["attach_wasm_density"] is False


def test_payload_build_plan_optional_attach_flags() -> None:
    plan = kernels.payload_build_plan(
        split_payload=True,
        wasm_source_count=0,
        has_density_tier=True,
        coords_cartesian=False,
        has_title_options=True,
        has_palette=True,
        has_legend_options=True,
        legend_loc_best=True,
        has_extra_legends=True,
        has_frame_sides=True,
        has_colorbar_options=True,
        show_modebar_is_false=True,
        has_export_options=True,
        show_tooltip_is_false=True,
        has_padding=True,
        has_dom=True,
        has_tooltip=True,
        has_mark_style=True,
        has_interaction=True,
        has_annotations=True,
        has_animation_options=True,
        has_graph_meta=True,
    )
    assert plan["attach_wasm_density"] is True
    assert plan["wasm_density_kind"] == kernels.DENSITY_WASM_DENSITY_UNSUPPORTED
    assert plan["attach_coords"] is True
    assert plan["attach_title_options"] is True
    assert plan["resolve_legend_best"] is True
    assert plan["attach_padding"] is True
    assert plan["attach_dom"] is True


def test_build_payload_show_legend_and_padding_use_kernel_plan() -> None:
    fig = Figure(padding=[4, 4, 4, 4])
    fig.show_legend = False
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    spec, _ = fig.build_payload()
    assert spec["show_legend"] is False
    assert spec["padding"] == [4, 4, 4, 4]
