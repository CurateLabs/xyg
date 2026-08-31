"""ABI 122 payload LOD/mask: Python host wrappers match the Rust goldens."""

from __future__ import annotations

import numpy as np
import pytest

from xyg import kernels
from xyg._figure import Figure
from xyg.config import (
    DECIMATION_THRESHOLD,
    DIRECT_SOFT_CEILING,
    SCATTER_DENSITY_THRESHOLD,
)


def test_payload_tier_line_polar_skips_m4() -> None:
    assert kernels.payload_tier(0, DECIMATION_THRESHOLD) == 0
    assert kernels.payload_tier(0, DECIMATION_THRESHOLD + 1) == 1
    assert kernels.payload_tier(0, DECIMATION_THRESHOLD + 1, polar=True) == 0


def test_payload_tier_scatter_strict_gt_and_per_item_ceiling() -> None:
    assert kernels.payload_tier(1, SCATTER_DENSITY_THRESHOLD) == 0
    assert kernels.payload_tier(1, SCATTER_DENSITY_THRESHOLD + 1) == 2
    assert kernels.payload_tier(1, SCATTER_DENSITY_THRESHOLD + 1, per_item=True) == 0
    assert kernels.payload_tier(1, DIRECT_SOFT_CEILING + 1, per_item=True) == 2
    assert kernels.payload_tier(1, 10, force_density=1) == 2
    assert kernels.payload_tier(1, 10, polar=True, force_density=1) == 0
    assert kernels.payload_tier(1, 1_000_000, force_density=0) == 0


def test_payload_visible_mask_drops_nonpositive_on_log() -> None:
    x = np.array([1.0, -2.0, 3.0, 0.0, 5.0])
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    mask = kernels.payload_visible_mask(x, y, x_log=True)
    np.testing.assert_array_equal(mask, [True, False, True, False, True])
    assert not kernels.payload_visible_needed(
        x_log=False,
        y_log=False,
        prefiltered=True,
        x_has_nulls=False,
        y_has_nulls=False,
    )
    assert kernels.payload_visible_needed(
        x_log=True,
        y_log=False,
        prefiltered=True,
        x_has_nulls=False,
        y_has_nulls=False,
    )


def test_payload_visible_mask_y_log_and_base() -> None:
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 3.0])
    base = np.array([1.0, -1.0, np.nan])
    mask = kernels.payload_visible_mask(x, y, y_log=True, base=base)
    np.testing.assert_array_equal(mask, [True, False, False])
    linear = kernels.payload_visible_mask(x, y, base=base)
    np.testing.assert_array_equal(linear, [True, True, False])


def test_payload_m4_indices_polar_stays_direct() -> None:
    n = DECIMATION_THRESHOLD + 1
    x = np.arange(n, dtype=float)
    y = np.ones(n)
    tier, idx = kernels.payload_m4_indices(n, x, y, 0.0, float(n - 1), 64, polar=True)
    assert tier == 0
    assert len(idx) == 0


def test_payload_m4_indices_closed_window_matches_m4_plus_eps() -> None:
    n = DECIMATION_THRESHOLD + 1
    x = np.arange(n, dtype=float)
    y = np.sin(x)
    tier, idx = kernels.payload_m4_indices(n, x, y, 0.0, float(n - 1), 64)
    assert tier == 1
    expected = kernels.m4_indices(x, y, 0.0, float(n - 1) + np.finfo(np.float64).eps, 64)
    np.testing.assert_array_equal(idx, expected)
    empty_tier, empty_idx = kernels.payload_m4_indices(n, x, y, float(n + 10), float(n + 100), 64)
    assert empty_tier == 1
    assert len(empty_idx) == 0


def test_payload_visible_indices_keep_all_and_log_drop() -> None:
    x = np.array([1.0, -2.0, 3.0, 0.0, 5.0])
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    keep_all, idx = kernels.payload_visible_indices(
        x, y, x_log=False, prefiltered=True, x_has_nulls=False, y_has_nulls=False
    )
    assert keep_all
    assert len(idx) == 0
    keep_all, idx = kernels.payload_visible_indices(
        x, y, x_log=True, prefiltered=True, x_has_nulls=False, y_has_nulls=False
    )
    assert not keep_all
    np.testing.assert_array_equal(idx, [0, 2, 4])


def test_payload_even_indices_matches_numpy_int64_linspace() -> None:
    keep_all, idx = kernels.payload_even_indices(4, 10)
    assert keep_all
    keep_all, idx = kernels.payload_even_indices(11, 4)
    assert not keep_all
    np.testing.assert_array_equal(idx, np.linspace(0, 10, 4, dtype=np.int64))


def test_payload_segment_budget_matches_host_max() -> None:
    assert kernels.payload_segment_budget(100) == max(1024, 100 * 4)
    assert kernels.payload_segment_budget(256) == 1024
    assert kernels.payload_segment_budget(257) == 1028
    assert kernels.payload_segment_budget(256.9) == 1024
    assert kernels.payload_segment_budget(0) == 1024
    assert kernels.payload_segment_budget(-10.7) == 1024
    try:
        kernels.payload_segment_budget(float("nan"))
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_payload_errorbar_indices_expands_even_keep_across_roles() -> None:
    keep_all, idx = kernels.payload_errorbar_indices(33, 11, 20)
    assert keep_all
    keep_all, idx = kernels.payload_errorbar_indices(10, 3, 2)
    assert keep_all
    keep_all, idx = kernels.payload_errorbar_indices(33, 11, 4)
    assert not keep_all
    np.testing.assert_array_equal(idx, [0, 3, 6, 10, 11, 14, 17, 21, 22, 25, 28, 32])


def test_payload_errorbar_role_keys_xor_mix() -> None:
    keys = kernels.payload_errorbar_role_keys(
        np.array([10, 20], dtype=np.uint32),
        np.array([30, 40], dtype=np.uint32),
        np.array([0, 1, 0, 1], dtype=np.uint32),
        np.array([0, 0, 1, 1], dtype=np.uint32),
    )
    assert keys.shape == (4, 2)
    assert keys[2, 0] == np.uint32(10 ^ 0x9E3779B9)


def test_payload_sample_target_indices_keep_all() -> None:
    keep_all, idx = kernels.payload_sample_target_indices(100, 8_192)
    assert keep_all
    keep_all, idx = kernels.payload_sample_target_indices(10_000, 8_192)
    assert not keep_all
    assert 0 < len(idx) < 10_000


def test_payload_segments_emit_gather_stem_decimates() -> None:
    gather = kernels.payload_segments_emit_gather("stem", 3000, 0, 100.0)
    assert gather["tier"] == 1
    assert not gather["role_maps"]
    assert not gather["keep_all"]
    assert gather["n_out"] == 1024
    assert len(gather["indices"]) == 1024


def test_payload_segments_emit_gather_errorbar_role_maps() -> None:
    gather = kernels.payload_segments_emit_gather("errorbar", 33, 11, 100.0)
    assert gather["tier"] == 0
    assert gather["role_maps"]
    assert gather["keep_all"]
    assert gather["n_out"] == 33
    np.testing.assert_array_equal(gather["sources"][:12], [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 0])
    np.testing.assert_array_equal(gather["roles"][:12], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1])


def test_payload_trace_channels_ship_attach_scatter() -> None:
    attach = kernels.payload_trace_channels_ship_attach(
        kernels.PAYLOAD_SHIP_CHANNELS_ALWAYS,
        include_trace_styles=True,
        has_color_ch=False,
        has_stroke_ch=True,
        has_style_channels=True,
    )
    assert attach == {
        "ship_color": True,
        "ship_size": True,
        "ship_stroke": True,
        "ship_style_channels": True,
    }


def test_payload_trace_channels_ship_attach_hexbin() -> None:
    attach = kernels.payload_trace_channels_ship_attach(
        kernels.PAYLOAD_SHIP_CHANNELS_ALWAYS,
        include_trace_styles=False,
        has_color_ch=False,
        has_stroke_ch=True,
        has_style_channels=True,
    )
    assert attach == {
        "ship_color": True,
        "ship_size": True,
        "ship_stroke": False,
        "ship_style_channels": False,
    }


def test_payload_trace_channels_ship_attach_geometry_if_color() -> None:
    attach = kernels.payload_trace_channels_ship_attach(
        kernels.PAYLOAD_SHIP_CHANNELS_IF_COLOR,
        include_trace_styles=True,
        has_color_ch=False,
        has_stroke_ch=True,
        has_style_channels=False,
    )
    assert attach == {
        "ship_color": False,
        "ship_size": False,
        "ship_stroke": True,
        "ship_style_channels": False,
    }
    attach = kernels.payload_trace_channels_ship_attach(
        kernels.PAYLOAD_SHIP_CHANNELS_IF_COLOR,
        include_trace_styles=True,
        has_color_ch=True,
        has_stroke_ch=False,
        has_style_channels=True,
    )
    assert attach == {
        "ship_color": True,
        "ship_size": True,
        "ship_stroke": False,
        "ship_style_channels": True,
    }


def test_payload_transition_entry_attach_ship_keys() -> None:
    from xyg.config import MAX_ANIMATION_MATCH_ROWS

    plan = kernels.payload_transition_entry_attach(
        has_trace_animation=True,
        entry_has_animation=False,
        has_trace_keys=True,
        has_key_values=False,
        has_sel=False,
        tier_direct=True,
        n_marks=10,
        n_trace_key_rows=10,
        n_key_value_rows=0,
        n_sel_rows=0,
        max_rows=MAX_ANIMATION_MATCH_ROWS,
        has_tooltip_rows=False,
        n_tooltip_rows=0,
        n_points=10,
    )
    assert plan["attach_animation"]
    assert plan["attempt_keys"]
    assert plan["ship_keys"]
    assert plan["animation_fallback"] is None


def test_payload_transition_entry_attach_decimated_fallback() -> None:
    from xyg.config import MAX_ANIMATION_MATCH_ROWS

    plan = kernels.payload_transition_entry_attach(
        has_trace_animation=False,
        entry_has_animation=False,
        has_trace_keys=True,
        has_key_values=False,
        has_sel=False,
        tier_direct=False,
        n_marks=10,
        n_trace_key_rows=10,
        n_key_value_rows=0,
        n_sel_rows=0,
        max_rows=MAX_ANIMATION_MATCH_ROWS,
        has_tooltip_rows=False,
        n_tooltip_rows=0,
        n_points=10,
    )
    assert plan["attempt_keys"]
    assert not plan["ship_keys"]
    assert plan["animation_fallback"] == "snap:aggregate"


def test_payload_transition_entry_attach_tooltip_filter() -> None:
    from xyg.config import MAX_ANIMATION_MATCH_ROWS

    plan = kernels.payload_transition_entry_attach(
        has_trace_animation=False,
        entry_has_animation=False,
        has_trace_keys=False,
        has_key_values=False,
        has_sel=True,
        tier_direct=False,
        n_marks=0,
        n_trace_key_rows=0,
        n_key_value_rows=0,
        n_sel_rows=2,
        max_rows=MAX_ANIMATION_MATCH_ROWS,
        has_tooltip_rows=True,
        n_tooltip_rows=3,
        n_points=3,
    )
    assert plan["attach_tooltip"]
    assert plan["filter_tooltip_by_sel"]
    assert plan["tooltip_length_ok"]


def test_payload_base_entry_plan_animation_and_scales() -> None:
    plan = kernels.payload_base_entry_plan(
        has_trace_animation=True,
        n_xv=12,
        style_color_is_none=True,
        x_axis_scale="log",
        y_axis_scale="symlog",
    )
    assert plan == {
        "attach_animation": True,
        "n_marks": 12,
        "apply_palette_default": True,
        "x_ship_scale": "log",
        "y_ship_scale": "symlog",
    }


def test_payload_base_entry_plan_linear_no_animation() -> None:
    plan = kernels.payload_base_entry_plan(
        has_trace_animation=False,
        n_xv=3,
        style_color_is_none=False,
        x_axis_scale="linear",
        y_axis_scale="linear",
    )
    assert plan == {
        "attach_animation": False,
        "n_marks": 3,
        "apply_palette_default": False,
        "x_ship_scale": "linear",
        "y_ship_scale": "linear",
    }


def test_payload_nonxy_emit_plan_rect() -> None:
    plan = kernels.payload_nonxy_emit_plan(
        kind="rect",
        n_marks=7,
        style_color_is_none=True,
        x_axis_scale="log",
        y_axis_scale="linear",
    )
    assert plan == {
        "tier_direct": True,
        "n_marks": 7,
        "apply_palette_default": True,
        "x_ship_scale": "log",
        "y_ship_scale": "linear",
        "channel_slot": kernels.PAYLOAD_SHIP_CHANNELS_IF_COLOR,
        "include_trace_styles": True,
        "attach_transition": True,
    }


def test_payload_nonxy_emit_plan_hexbin() -> None:
    plan = kernels.payload_nonxy_emit_plan(
        kind="hexbin",
        n_marks=12,
        style_color_is_none=False,
        x_axis_scale="symlog",
        y_axis_scale="symlog",
    )
    assert plan == {
        "tier_direct": True,
        "n_marks": 12,
        "apply_palette_default": False,
        "x_ship_scale": "symlog",
        "y_ship_scale": "symlog",
        "channel_slot": kernels.PAYLOAD_SHIP_CHANNELS_ALWAYS,
        "include_trace_styles": False,
        "attach_transition": False,
    }


def test_payload_nonxy_emit_plan_density_sample() -> None:
    plan = kernels.payload_nonxy_emit_plan(
        kind="density_sample",
        n_marks=200,
        style_color_is_none=False,
        x_axis_scale="linear",
        y_axis_scale="log",
    )
    assert plan == {
        "tier_direct": True,
        "n_marks": 200,
        "apply_palette_default": False,
        "x_ship_scale": "linear",
        "y_ship_scale": "log",
        "channel_slot": kernels.PAYLOAD_SHIP_CHANNELS_ALWAYS,
        "include_trace_styles": True,
        "attach_transition": False,
    }


def test_payload_bar_hist_emit_plan_histogram() -> None:
    plan = kernels.payload_bar_hist_emit_plan(
        kind="histogram",
        n_marks=6,
        style_color_is_none=True,
        x_axis_scale="log",
        y_axis_scale="linear",
    )
    assert plan == {
        "emit_bar": False,
        "tier_direct": True,
        "n_marks": 6,
        "apply_palette_default": True,
        "x_ship_scale": "log",
        "y_ship_scale": "linear",
        "pos_ship_scale": "log",
        "value_ship_scale": "linear",
        "value_axis": "y",
        "channel_slot": kernels.PAYLOAD_SHIP_CHANNELS_IF_COLOR,
        "include_trace_styles": True,
        "attach_transition": True,
    }


def test_payload_bar_hist_emit_plan_bar_compact_vertical() -> None:
    plan = kernels.payload_bar_hist_emit_plan(
        kind="bar_compact",
        compact=True,
        n_marks=4,
        style_color_is_none=False,
        x_axis_scale="linear",
        y_axis_scale="log",
        orientation="vertical",
    )
    assert plan == {
        "emit_bar": True,
        "tier_direct": True,
        "n_marks": 4,
        "apply_palette_default": False,
        "x_ship_scale": "linear",
        "y_ship_scale": "log",
        "pos_ship_scale": "linear",
        "value_ship_scale": "log",
        "value_axis": "y",
        "channel_slot": kernels.PAYLOAD_SHIP_CHANNELS_IF_COLOR,
        "include_trace_styles": True,
        "attach_transition": True,
    }


def test_payload_bar_hist_emit_plan_bar_compact_rect_fallback() -> None:
    plan = kernels.payload_bar_hist_emit_plan(
        kind="bar_compact",
        compact=False,
        n_marks=3,
        style_color_is_none=True,
        x_axis_scale="linear",
        y_axis_scale="linear",
        orientation="vertical",
    )
    assert plan["emit_bar"] is False
    assert plan["n_marks"] == 3
    assert plan["attach_transition"] is True


def test_payload_heatmap_emit_plan_rgba_path() -> None:
    plan = kernels.payload_heatmap_emit_plan(
        has_rgba_grid=True,
        grid_rows=10,
        grid_cols=20,
        style_colormap_is_none=True,
        borrow_heatmaps=True,
    )
    assert plan == {
        "path": "rgba",
        "tier_direct": True,
        "n_marks": 200,
        "attach_color": False,
        "borrow_canonical": False,
        "attach_encoding": False,
        "use_constant_colormap_fallback": False,
    }


def test_payload_heatmap_emit_plan_grid_borrow() -> None:
    plan = kernels.payload_heatmap_emit_plan(
        has_rgba_grid=False,
        grid_rows=4,
        grid_cols=5,
        style_colormap_is_none=False,
        borrow_heatmaps=True,
    )
    assert plan == {
        "path": "grid",
        "tier_direct": True,
        "n_marks": 20,
        "attach_color": True,
        "borrow_canonical": True,
        "attach_encoding": True,
        "use_constant_colormap_fallback": False,
    }


def test_payload_mesh_emit_plan_gather_and_transition() -> None:
    plan = kernels.payload_mesh_emit_plan(
        n_marks=12,
        style_color_is_none=True,
        x_axis_scale="log",
        y_axis_scale="linear",
        any_geometry_nulls=True,
        has_continuous_color=True,
        continuous_color_values_missing=False,
    )
    assert plan == {
        "tier_direct": True,
        "n_marks": 12,
        "apply_palette_default": True,
        "x_ship_scale": "log",
        "y_ship_scale": "linear",
        "channel_slot": kernels.PAYLOAD_SHIP_CHANNELS_IF_COLOR,
        "include_trace_styles": True,
        "attach_transition": True,
        "attempt_gather": True,
        "gather_include_color": True,
    }


def test_payload_mesh_emit_plan_rejects_missing_continuous_color() -> None:
    with pytest.raises(ValueError, match="payload_mesh_emit_plan"):
        kernels.payload_mesh_emit_plan(
            n_marks=1,
            style_color_is_none=False,
            x_axis_scale="linear",
            y_axis_scale="linear",
            any_geometry_nulls=False,
            has_continuous_color=True,
            continuous_color_values_missing=True,
        )


def test_payload_column_ship_plan_bar_compact_vertical() -> None:
    plan = kernels.payload_column_ship_plan(
        kind="bar_compact",
        x_axis_scale="linear",
        y_axis_scale="log",
        orientation="vertical",
    )
    assert plan["gather_policy"] == "rect_finite"
    assert plan["n_columns"] == 3
    assert plan["columns"][0] == {
        "registry_key": "pos",
        "trace_slot": "x",
        "ship_method": "offset",
        "ship_scale": "linear",
        "gather": False,
    }
    assert plan["columns"][1]["registry_key"] == "value1"
    assert plan["columns"][2]["registry_key"] == "value0"


def test_payload_column_ship_plan_bar_compact_horizontal() -> None:
    plan = kernels.payload_column_ship_plan(
        kind="bar_compact",
        x_axis_scale="log",
        y_axis_scale="symlog",
        orientation="horizontal",
    )
    assert plan["n_columns"] == 3
    assert plan["columns"][0]["registry_key"] == "pos"
    assert plan["columns"][0]["ship_method"] == "values"
    assert plan["columns"][1]["trace_slot"] == "x1"
    assert plan["columns"][2]["trace_slot"] == "x0"


def test_payload_column_ship_plan_rect() -> None:
    plan = kernels.payload_column_ship_plan(
        kind="rect",
        x_axis_scale="log",
        y_axis_scale="symlog",
    )
    assert plan == {
        "gather_policy": "rect_finite",
        "gather_include_color": False,
        "n_columns": 4,
        "x_ship_scale": "log",
        "y_ship_scale": "symlog",
        "columns": [
            {
                "registry_key": "x0",
                "trace_slot": "x0",
                "ship_method": "offset",
                "ship_scale": "log",
                "gather": True,
            },
            {
                "registry_key": "x1",
                "trace_slot": "x1",
                "ship_method": "offset",
                "ship_scale": "log",
                "gather": True,
            },
            {
                "registry_key": "y0",
                "trace_slot": "y0",
                "ship_method": "offset",
                "ship_scale": "symlog",
                "gather": True,
            },
            {
                "registry_key": "y1",
                "trace_slot": "y1",
                "ship_method": "offset",
                "ship_scale": "symlog",
                "gather": True,
            },
        ],
    }


def test_payload_column_ship_plan_ribbon_targets() -> None:
    plan = kernels.payload_column_ship_plan(
        kind="ribbon",
        x_axis_scale="linear",
        y_axis_scale="log",
    )
    assert plan["gather_policy"] == "valid_indices"
    assert plan["n_columns"] == 6
    assert plan["columns"][4]["registry_key"] == "target_y0"
    assert plan["columns"][4]["trace_slot"] == "x"
    assert plan["columns"][4]["ship_scale"] == "log"


def test_payload_column_ship_plan_density_sample_values_no_gather() -> None:
    plan = kernels.payload_column_ship_plan(
        kind="density_sample",
        x_axis_scale="linear",
        y_axis_scale="log",
    )
    assert plan == {
        "gather_policy": "none",
        "gather_include_color": False,
        "n_columns": 2,
        "x_ship_scale": "linear",
        "y_ship_scale": "log",
        "columns": [
            {
                "registry_key": "x",
                "trace_slot": "x",
                "ship_method": "values",
                "ship_scale": "linear",
                "gather": False,
            },
            {
                "registry_key": "y",
                "trace_slot": "y",
                "ship_method": "values",
                "ship_scale": "log",
                "gather": False,
            },
        ],
    }


def test_payload_column_ship_plan_density_wasm_source_f64_no_gather() -> None:
    plan = kernels.payload_column_ship_plan(
        kind="density_wasm_source",
        x_axis_scale="log",
        y_axis_scale="symlog",
    )
    assert plan["gather_policy"] == "none"
    assert plan["n_columns"] == 2
    assert plan["x_ship_scale"] == "log"
    assert plan["y_ship_scale"] == "symlog"
    assert plan["columns"][0] == {
        "registry_key": "x",
        "trace_slot": "x",
        "ship_method": "f64",
        "ship_scale": "log",
        "gather": False,
    }
    assert plan["columns"][1]["ship_method"] == "f64"


def test_payload_column_ship_plan_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="payload_column_ship_plan"):
        kernels.payload_column_ship_plan(
            kind="sankey",
            x_axis_scale="linear",
            y_axis_scale="linear",
        )


def test_payload_channel_ship_plan_scatter() -> None:
    plan = kernels.payload_channel_ship_plan(
        kernels.PAYLOAD_SHIP_CHANNELS_ALWAYS,
        include_trace_styles=True,
        has_stroke_ch=True,
        has_style_channels=True,
    )
    assert plan == {
        "n_channels": 3,
        "channels": [
            {
                "registry_key": "color",
                "trace_slot": "color_ch",
                "ship_method": "color_size",
            },
            {
                "registry_key": "stroke",
                "trace_slot": "stroke_ch",
                "ship_method": "color",
            },
            {
                "registry_key": "channels",
                "trace_slot": "style_channels",
                "ship_method": "style",
            },
        ],
    }


def test_payload_channel_ship_plan_ribbon_color2_first() -> None:
    plan = kernels.payload_channel_ship_plan(
        kernels.PAYLOAD_SHIP_CHANNELS_IF_COLOR,
        include_trace_styles=True,
        has_color2_ch=True,
        has_color_ch=True,
    )
    assert plan["n_channels"] == 2
    assert plan["channels"][0] == {
        "registry_key": "color_target",
        "trace_slot": "color2_ch",
        "ship_method": "color",
    }
    assert plan["channels"][1]["ship_method"] == "color_size"


def test_payload_channel_ship_plan_hexbin_color_size_only() -> None:
    plan = kernels.payload_channel_ship_plan(
        kernels.PAYLOAD_SHIP_CHANNELS_ALWAYS,
        include_trace_styles=False,
        has_stroke_ch=True,
        has_style_channels=True,
    )
    assert plan == {
        "n_channels": 1,
        "channels": [
            {
                "registry_key": "color",
                "trace_slot": "color_ch",
                "ship_method": "color_size",
            },
        ],
    }


def test_payload_channel_ship_plan_rejects_unknown_slot() -> None:
    with pytest.raises(ValueError, match="payload_channel_ship_plan"):
        kernels.payload_channel_ship_plan(9, include_trace_styles=True)


def test_payload_channel_wire_encode_continuous_and_categorical() -> None:
    assert kernels.payload_channel_wire_encode("color", "continuous") == {
        "buf_kind": "f32",
        "transform": "normalize",
        "mark_dtype_u8": False,
        "ship_palette": False,
        "set_n": False,
    }
    assert kernels.payload_channel_wire_encode("size", "continuous", quantize_continuous=True) == {
        "buf_kind": "u8",
        "transform": "quantize_u8",
        "mark_dtype_u8": True,
        "ship_palette": False,
        "set_n": False,
    }
    assert kernels.payload_channel_wire_encode("color", "categorical", n_categories=256) == {
        "buf_kind": "u8",
        "transform": "raw",
        "mark_dtype_u8": True,
        "ship_palette": True,
        "set_n": False,
    }
    assert (
        kernels.payload_channel_wire_encode("color", "categorical", n_categories=300)["buf_kind"]
        == "f32"
    )
    assert kernels.payload_channel_wire_encode("color", "direct_rgba") == {
        "buf_kind": "u8",
        "transform": "rgba_pack",
        "mark_dtype_u8": False,
        "ship_palette": False,
        "set_n": True,
    }
    assert kernels.payload_channel_wire_encode("style", "direct", style_dtype_u8=True) == {
        "buf_kind": "u8",
        "transform": "raw",
        "mark_dtype_u8": False,
        "ship_palette": False,
        "set_n": True,
    }


def test_payload_channel_wire_encode_rejects_invalid_role_mode() -> None:
    with pytest.raises(ValueError, match="payload_channel_wire_encode"):
        kernels.payload_channel_wire_encode("size", "categorical")


def test_payload_ribbon_emit_plan_gather_and_transition() -> None:
    plan = kernels.payload_ribbon_emit_plan(
        n_marks=6,
        style_color_is_none=True,
        x_axis_scale="log",
        y_axis_scale="linear",
        any_geometry_nulls=True,
        has_color2_ch=True,
    )
    assert plan == {
        "tier_direct": True,
        "n_marks": 6,
        "apply_palette_default": True,
        "x_ship_scale": "log",
        "y_ship_scale": "linear",
        "channel_slot": kernels.PAYLOAD_SHIP_CHANNELS_IF_COLOR,
        "include_trace_styles": True,
        "attach_transition": True,
        "attempt_gather": True,
        "attach_color2": True,
    }


def test_payload_ribbon_emit_plan_no_gather_without_nulls() -> None:
    plan = kernels.payload_ribbon_emit_plan(
        n_marks=4,
        style_color_is_none=False,
        x_axis_scale="linear",
        y_axis_scale="linear",
        any_geometry_nulls=False,
        has_color2_ch=False,
    )
    assert plan["attempt_gather"] is False
    assert plan["attach_color2"] is False
    assert plan["apply_palette_default"] is False


def test_payload_segments_emit_plan_errorbar_role_keys() -> None:
    plan = kernels.payload_segments_emit_plan(
        kind="errorbar",
        n_marks=33,
        style_color_is_none=True,
        x_axis_scale="log",
        y_axis_scale="linear",
        has_transition_keys=True,
    )
    assert plan == {
        "n_marks": 33,
        "apply_palette_default": True,
        "x_ship_scale": "log",
        "y_ship_scale": "linear",
        "channel_slot": kernels.PAYLOAD_SHIP_CHANNELS_IF_COLOR,
        "include_trace_styles": True,
        "attach_transition": True,
        "attempt_gather": True,
        "attempt_role_keys": True,
    }


def test_payload_segments_emit_plan_stem_no_role_keys() -> None:
    plan = kernels.payload_segments_emit_plan(
        kind="stem",
        n_marks=3000,
        style_color_is_none=False,
        x_axis_scale="linear",
        y_axis_scale="symlog",
        has_transition_keys=False,
    )
    assert plan["attempt_role_keys"] is False
    assert plan["y_ship_scale"] == "symlog"
    assert plan["apply_palette_default"] is False


def test_payload_scatter_emit_plan_density_tier() -> None:
    plan = kernels.payload_scatter_emit_plan(
        n_points=SCATTER_DENSITY_THRESHOLD + 1,
        polar=False,
        force_density=-1,
        force_direct=False,
        per_item=False,
        n_marks=0,
        has_trace_animation=False,
        x_axis_scale="linear",
        y_axis_scale="linear",
        has_transition_keys=False,
        has_tooltip_rows=False,
        n_tooltip_rows=0,
    )
    assert plan["emit_density"] is True
    assert plan["clear_shipped_sel"] is True
    assert plan["drill_mode_false"] is True
    assert plan["attach_transition"] is True


def test_payload_scatter_emit_plan_direct_channels_always() -> None:
    plan = kernels.payload_scatter_emit_plan(
        n_points=100,
        polar=False,
        force_density=-1,
        force_direct=False,
        per_item=False,
        n_marks=50,
        has_trace_animation=True,
        x_axis_scale="log",
        y_axis_scale="linear",
        has_transition_keys=True,
        has_tooltip_rows=True,
        n_tooltip_rows=100,
    )
    assert plan == {
        "emit_density": False,
        "clear_shipped_sel": False,
        "drill_mode_false": False,
        "set_shipped_sel": True,
        "attach_transition": True,
        "attach_tooltip": True,
        "filter_tooltip_by_sel": False,
        "tooltip_length_ok": True,
        "tier_direct": True,
        "n_marks": 50,
        "apply_palette_default": False,
        "attach_animation": True,
        "x_ship_scale": "log",
        "y_ship_scale": "linear",
        "channel_slot": kernels.PAYLOAD_SHIP_CHANNELS_ALWAYS,
        "include_trace_styles": True,
    }


def test_payload_scatter_emit_plan_force_density_false() -> None:
    plan = kernels.payload_scatter_emit_plan(
        n_points=1_000_000,
        polar=False,
        force_density=0,
        force_direct=False,
        per_item=False,
        n_marks=100,
        has_trace_animation=False,
        x_axis_scale="linear",
        y_axis_scale="linear",
        has_transition_keys=False,
        has_tooltip_rows=False,
        n_tooltip_rows=0,
    )
    assert plan["emit_density"] is False
    assert plan["set_shipped_sel"] is True


def test_payload_density_trace_emit_plan_identity_grid() -> None:
    plan = kernels.payload_density_trace_emit_plan(
        has_channel=True,
        mode="categorical",
        codes_present=True,
        codes_u8=True,
        has_counts=True,
        has_constant=False,
        cartesian=True,
        x_linear=True,
        y_linear=True,
        x_has_nulls=False,
        y_has_nulls=False,
        point_overlay=True,
        split_payload=False,
        grid_w=512,
        grid_h=384,
        grid_from_pyramid=False,
        has_pyramid_resource=False,
        grid_present=False,
        x_min=0.0,
        x_max=1.0,
        y_min=0.0,
        y_max=1.0,
        xr0=0.0,
        xr1=1.0,
        yr0=0.0,
        yr1=1.0,
        bx0=0.0,
        bx1=1.0,
        by0=0.0,
        by1=1.0,
        n_points=10_000,
        dropped_count=2,
    )
    assert plan["attach_transition"] is True
    assert plan["n_marks"] == 512 * 384
    assert plan["visible_init_n_points"] is True
    assert plan["attach_sample"] is True
    assert plan["ship_categorical_entry_color"] is True
    assert plan["channels_dropped_compat"] is True


def test_line_scatter_area_base_entry_ships_animation_and_log_scale() -> None:
    anim = {"duration": 250}
    fig = Figure().set_axis("x", type_="log")
    fig.scatter([1.0, 10.0], [1.0, 10.0])
    fig.line([2.0, 20.0], [2.0, 20.0])
    fig.area([3.0, 30.0], [3.0, 30.0])
    for trace in fig.traces:
        trace.animation = anim
    spec, _blob = fig.build_payload()
    for entry in spec["traces"]:
        assert entry["animation"] == anim
        x_col = spec["columns"][entry["x"]]
        assert x_col.get("offset") == 0.0


def test_polar_line_stays_direct_over_m4_threshold() -> None:
    n = DECIMATION_THRESHOLD + 1
    fig = Figure(coords="polar").line(np.arange(n, dtype=float), np.ones(n))
    spec, _blob = fig.build_payload()
    assert spec["traces"][0]["tier"] == "direct"
    assert spec["traces"][0]["n_marks"] == n
    update, _buffers = fig.decimate_view(0.0, float(n), 512)
    assert update["traces"] == []


def test_polar_scatter_stays_direct_even_when_density_forced() -> None:
    fig = Figure(coords="polar").scatter(np.arange(10.0), np.arange(10.0), density=True)
    spec, _blob = fig.build_payload()
    assert fig.traces[0].use_density()
    assert spec["traces"][0]["tier"] == "direct"
    assert spec["traces"][0]["n_marks"] == 10
