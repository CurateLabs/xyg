//! Payload emit gather/ship orchestration (issue #732).
//!
//! Hosts retain buffer shipping and NumPy gathers; this module owns multi-step
//! emit policy so Python and Node stay bit-identical.

use crate::density_emit::{
    bin_coord_endpoints, density_categorical_color_wire_admit, density_channels_dropped_compat,
    density_constant_color_wire_admit, density_grid_path_identity_state,
    density_mean_color_rgba_wire_admit, density_overlay_omitted_wire, density_trace_color_classify,
    density_uses_channel_colormap, density_wasm_density_wire_kind, density_wasm_source_admit,
    emit_meta, DENSITY_OVERLAY_ROWS_EXCEED_U32, DENSITY_WASM_DENSITY_NONE,
};
use crate::lod_plan::{
    payload_errorbar_indices, payload_errorbar_role_maps, payload_even_indices,
    payload_segment_budget, payload_tier, payload_transition_keys_admit, PayloadIndexSel,
    PAYLOAD_KIND_SCATTER, PAYLOAD_TIER_DENSITY, PAYLOAD_TRANSITION_SHIP,
};

pub const PAYLOAD_SEGMENTS_TIER_DIRECT: i32 = 0;
pub const PAYLOAD_SEGMENTS_TIER_DECIMATED: i32 = 1;

/// Always ship color/size via ``_ship_channels`` (scatter, hexbin, density sample).
pub const PAYLOAD_SHIP_CHANNELS_ALWAYS: i32 = 0;
/// Ship color/size only when ``color_ch`` is present (geometry marks).
pub const PAYLOAD_SHIP_CHANNELS_IF_COLOR: i32 = 1;

/// ``pw.ship`` scale for linear axes (`_axis_scale` default).
pub const PAYLOAD_BASE_ENTRY_SHIP_SCALE_LINEAR: i32 = 0;
/// ``pw.ship`` scale for log axes.
pub const PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG: i32 = 1;
/// ``pw.ship`` scale for symlog axes.
pub const PAYLOAD_BASE_ENTRY_SHIP_SCALE_SYMLOG: i32 = 2;

/// Rectangle / histogram / bar geometry emit (`_emit_rect`).
pub const PAYLOAD_NONXY_KIND_RECT: i32 = 0;
/// Hexbin center emit (`_emit_hexbin`).
pub const PAYLOAD_NONXY_KIND_HEXBIN: i32 = 1;
/// Density overlay sample sub-spec (`_density_sample_spec`).
pub const PAYLOAD_NONXY_KIND_DENSITY_SAMPLE: i32 = 2;

/// Histogram rect skeleton (`_emit_histogram` → `_emit_rect`).
pub const PAYLOAD_BAR_HIST_KIND_HISTOGRAM: i32 = 0;
/// Bar/column compact skeleton (`_emit_bar_compact`).
pub const PAYLOAD_BAR_HIST_KIND_BAR_COMPACT: i32 = 1;

/// Vertical bar orientation (`style.orientation == "vertical"`).
pub const PAYLOAD_BAR_ORIENTATION_VERTICAL: i32 = 0;
/// Horizontal bar orientation (`style.orientation == "horizontal"`).
pub const PAYLOAD_BAR_ORIENTATION_HORIZONTAL: i32 = 1;

/// Compact bar values ship on the y axis.
pub const PAYLOAD_VALUE_AXIS_Y: i32 = 0;
/// Compact bar values ship on the x axis.
pub const PAYLOAD_VALUE_AXIS_X: i32 = 1;

/// Heatmap RGBA lattice path (`rgba_grid` present).
pub const PAYLOAD_HEATMAP_PATH_RGBA: i32 = 0;
/// Heatmap normalized grid + colormap path.
pub const PAYLOAD_HEATMAP_PATH_GRID: i32 = 1;

fn payload_base_entry_ship_scale(axis_type: i32) -> i32 {
    match axis_type {
        1 => PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG,
        2 => PAYLOAD_BASE_ENTRY_SHIP_SCALE_SYMLOG,
        _ => PAYLOAD_BASE_ENTRY_SHIP_SCALE_LINEAR,
    }
}

/// Base-entry skeleton policy from ``_base_entry`` / ``_default_styled``.
///
/// Owns when animation ships on the base skeleton (directly, not deferred to
/// ``_transition_entry``), ``n_marks`` from gathered geometry, palette default
/// for missing trace color, and axis ship-scale selection. Hosts still copy
/// trace metadata, ship f32 columns, and attach transition keys separately.
pub fn payload_base_entry_plan(
    has_trace_animation: i32,
    n_xv: usize,
    style_color_is_none: i32,
    x_axis_type: i32,
    y_axis_type: i32,
    out_attach_animation: &mut i32,
    out_n_marks: &mut usize,
    out_apply_palette_default: &mut i32,
    out_x_ship_scale: &mut i32,
    out_y_ship_scale: &mut i32,
) -> i32 {
    *out_attach_animation = i32::from(has_trace_animation != 0);
    *out_n_marks = n_xv;
    *out_apply_palette_default = i32::from(style_color_is_none != 0);
    *out_x_ship_scale = payload_base_entry_ship_scale(x_axis_type);
    *out_y_ship_scale = payload_base_entry_ship_scale(y_axis_type);
    1
}

/// Non-xy trace skeleton / channel-attach plan from ``_emit_rect``,
/// ``_emit_hexbin``, and ``_density_sample_spec``.
///
/// Owns direct tier, gathered ``n_marks``, palette default for missing trace
/// color, axis ship scales, trace-channel attach slot/styles, and whether the
/// host wraps with ``_transition_entry``. Hosts still gather geometry, ship
/// columns, and attach channels via ``payload_trace_channels_ship_attach``.
/// Returns ``1`` on success, ``0`` when ``kind`` is invalid.
pub fn payload_nonxy_emit_plan(
    kind: i32,
    n_marks: usize,
    style_color_is_none: i32,
    x_axis_type: i32,
    y_axis_type: i32,
    out_tier_direct: &mut i32,
    out_n_marks: &mut usize,
    out_apply_palette_default: &mut i32,
    out_x_ship_scale: &mut i32,
    out_y_ship_scale: &mut i32,
    out_channel_slot: &mut i32,
    out_include_trace_styles: &mut i32,
    out_attach_transition: &mut i32,
) -> i32 {
    let (channel_slot, include_trace_styles, attach_transition) = match kind {
        PAYLOAD_NONXY_KIND_RECT => (
            PAYLOAD_SHIP_CHANNELS_IF_COLOR,
            1,
            1,
        ),
        PAYLOAD_NONXY_KIND_HEXBIN => (PAYLOAD_SHIP_CHANNELS_ALWAYS, 0, 0),
        PAYLOAD_NONXY_KIND_DENSITY_SAMPLE => (PAYLOAD_SHIP_CHANNELS_ALWAYS, 1, 0),
        _ => return 0,
    };
    *out_tier_direct = 1;
    *out_n_marks = n_marks;
    *out_apply_palette_default = i32::from(style_color_is_none != 0);
    *out_x_ship_scale = payload_base_entry_ship_scale(x_axis_type);
    *out_y_ship_scale = payload_base_entry_ship_scale(y_axis_type);
    *out_channel_slot = channel_slot;
    *out_include_trace_styles = include_trace_styles;
    *out_attach_transition = attach_transition;
    1
}

/// Histogram / bar-compact emit skeleton from ``_emit_histogram`` and
/// ``_emit_bar_compact``.
///
/// Histogram always uses rect geometry (``out_emit_bar = 0``). Bar-compact uses
/// nested ``bar`` when ``compact != 0``; otherwise rect fallback. Hosts still
/// run ``payload_bar_compact_admit``, gather finite rows, and ship columns.
/// Returns ``1`` on success, ``0`` when ``kind`` or ``orientation`` is invalid.
pub fn payload_bar_hist_emit_plan(
    kind: i32,
    compact: i32,
    n_marks: usize,
    style_color_is_none: i32,
    x_axis_type: i32,
    y_axis_type: i32,
    orientation: i32,
    out_emit_bar: &mut i32,
    out_tier_direct: &mut i32,
    out_n_marks: &mut usize,
    out_apply_palette_default: &mut i32,
    out_x_ship_scale: &mut i32,
    out_y_ship_scale: &mut i32,
    out_pos_ship_scale: &mut i32,
    out_value_ship_scale: &mut i32,
    out_value_axis: &mut i32,
    out_channel_slot: &mut i32,
    out_include_trace_styles: &mut i32,
    out_attach_transition: &mut i32,
) -> i32 {
    match kind {
        PAYLOAD_BAR_HIST_KIND_HISTOGRAM => {
            *out_emit_bar = 0;
            let ok = payload_nonxy_emit_plan(
                PAYLOAD_NONXY_KIND_RECT,
                n_marks,
                style_color_is_none,
                x_axis_type,
                y_axis_type,
                out_tier_direct,
                out_n_marks,
                out_apply_palette_default,
                out_x_ship_scale,
                out_y_ship_scale,
                out_channel_slot,
                out_include_trace_styles,
                out_attach_transition,
            );
            if ok == 0 {
                return 0;
            }
            *out_pos_ship_scale = *out_x_ship_scale;
            *out_value_ship_scale = *out_y_ship_scale;
            *out_value_axis = PAYLOAD_VALUE_AXIS_Y;
            1
        }
        PAYLOAD_BAR_HIST_KIND_BAR_COMPACT if compact == 0 => {
            *out_emit_bar = 0;
            let ok = payload_nonxy_emit_plan(
                PAYLOAD_NONXY_KIND_RECT,
                n_marks,
                style_color_is_none,
                x_axis_type,
                y_axis_type,
                out_tier_direct,
                out_n_marks,
                out_apply_palette_default,
                out_x_ship_scale,
                out_y_ship_scale,
                out_channel_slot,
                out_include_trace_styles,
                out_attach_transition,
            );
            if ok == 0 {
                return 0;
            }
            *out_pos_ship_scale = *out_x_ship_scale;
            *out_value_ship_scale = *out_y_ship_scale;
            *out_value_axis = PAYLOAD_VALUE_AXIS_Y;
            ok
        }
        PAYLOAD_BAR_HIST_KIND_BAR_COMPACT => {
            *out_emit_bar = 1;
            *out_tier_direct = 1;
            *out_n_marks = n_marks;
            *out_apply_palette_default = i32::from(style_color_is_none != 0);
            let x_scale = payload_base_entry_ship_scale(x_axis_type);
            let y_scale = payload_base_entry_ship_scale(y_axis_type);
            *out_x_ship_scale = x_scale;
            *out_y_ship_scale = y_scale;
            *out_channel_slot = PAYLOAD_SHIP_CHANNELS_IF_COLOR;
            *out_include_trace_styles = 1;
            *out_attach_transition = 1;
            match orientation {
                PAYLOAD_BAR_ORIENTATION_VERTICAL => {
                    *out_pos_ship_scale = x_scale;
                    *out_value_ship_scale = y_scale;
                    *out_value_axis = PAYLOAD_VALUE_AXIS_Y;
                }
                PAYLOAD_BAR_ORIENTATION_HORIZONTAL => {
                    *out_pos_ship_scale = y_scale;
                    *out_value_ship_scale = x_scale;
                    *out_value_axis = PAYLOAD_VALUE_AXIS_X;
                }
                _ => return 0,
            }
            1
        }
        _ => 0,
    }
}

/// Heatmap emit skeleton from ``_emit_heatmap``.
///
/// Owns rgba-vs-grid path selection, lattice ``n_marks``, top-level color
/// attach on the grid path, canonical-f64 borrow encoding, and constant-color
/// colormap fallback when ``style.colormap`` is absent. Hosts still ship grid
/// buffers, parse fallback colors, and copy trace metadata.
/// Returns ``1`` on success, ``0`` when ``grid_rows * grid_cols`` overflows.
pub fn payload_heatmap_emit_plan(
    has_rgba_grid: i32,
    grid_rows: usize,
    grid_cols: usize,
    style_colormap_is_none: i32,
    borrow_heatmaps: i32,
    out_path: &mut i32,
    out_tier_direct: &mut i32,
    out_n_marks: &mut usize,
    out_attach_color: &mut i32,
    out_borrow_canonical: &mut i32,
    out_attach_encoding: &mut i32,
    out_use_constant_colormap_fallback: &mut i32,
) -> i32 {
    let n_marks = match grid_rows.checked_mul(grid_cols) {
        Some(n) => n,
        None => return 0,
    };
    *out_tier_direct = 1;
    *out_n_marks = n_marks;
    if has_rgba_grid != 0 {
        *out_path = PAYLOAD_HEATMAP_PATH_RGBA;
        *out_attach_color = 0;
        *out_borrow_canonical = 0;
        *out_attach_encoding = 0;
        *out_use_constant_colormap_fallback = 0;
    } else {
        *out_path = PAYLOAD_HEATMAP_PATH_GRID;
        *out_attach_color = 1;
        *out_borrow_canonical = i32::from(borrow_heatmaps != 0);
        *out_attach_encoding = i32::from(borrow_heatmaps != 0);
        *out_use_constant_colormap_fallback = i32::from(style_colormap_is_none != 0);
    }
    1
}

/// Triangle-mesh emit skeleton from ``_emit_triangle_mesh``.
///
/// Owns direct tier, gathered ``n_marks``, palette default for missing trace
/// color, axis ship scales, ``valid_indices_f64`` gather policy (geometry nulls
/// plus continuous ``color_ch`` values), trace-channel attach slot/styles, and
/// transition wrap. Hosts still gather geometry, ship columns, and attach
/// channels. Returns ``1`` on success, ``0`` when continuous color lacks values.
pub fn payload_mesh_emit_plan(
    n_marks: usize,
    style_color_is_none: i32,
    x_axis_type: i32,
    y_axis_type: i32,
    any_geometry_nulls: i32,
    has_continuous_color: i32,
    continuous_color_values_missing: i32,
    out_tier_direct: &mut i32,
    out_n_marks: &mut usize,
    out_apply_palette_default: &mut i32,
    out_x_ship_scale: &mut i32,
    out_y_ship_scale: &mut i32,
    out_channel_slot: &mut i32,
    out_include_trace_styles: &mut i32,
    out_attach_transition: &mut i32,
    out_attempt_gather: &mut i32,
    out_gather_include_color: &mut i32,
) -> i32 {
    if has_continuous_color != 0 && continuous_color_values_missing != 0 {
        return 0;
    }
    *out_tier_direct = 1;
    *out_n_marks = n_marks;
    *out_apply_palette_default = i32::from(style_color_is_none != 0);
    *out_x_ship_scale = payload_base_entry_ship_scale(x_axis_type);
    *out_y_ship_scale = payload_base_entry_ship_scale(y_axis_type);
    *out_channel_slot = PAYLOAD_SHIP_CHANNELS_IF_COLOR;
    *out_include_trace_styles = 1;
    *out_attach_transition = 1;
    *out_gather_include_color = i32::from(has_continuous_color != 0);
    *out_attempt_gather = i32::from(any_geometry_nulls != 0 || has_continuous_color != 0);
    1
}

/// Ribbon emit skeleton from ``_emit_ribbon``.
///
/// Owns direct tier, gathered ``n_marks``, palette default for missing trace
/// color, axis ship scales, geometry-null ``valid_indices_f64`` gather policy,
/// trace-channel attach slot/styles, ``color2_ch`` attach, and transition wrap.
/// Hosts still gather geometry, ship columns, and attach channels.
pub fn payload_ribbon_emit_plan(
    n_marks: usize,
    style_color_is_none: i32,
    x_axis_type: i32,
    y_axis_type: i32,
    any_geometry_nulls: i32,
    has_color2_ch: i32,
    out_tier_direct: &mut i32,
    out_n_marks: &mut usize,
    out_apply_palette_default: &mut i32,
    out_x_ship_scale: &mut i32,
    out_y_ship_scale: &mut i32,
    out_channel_slot: &mut i32,
    out_include_trace_styles: &mut i32,
    out_attach_transition: &mut i32,
    out_attempt_gather: &mut i32,
    out_attach_color2: &mut i32,
) -> i32 {
    *out_tier_direct = 1;
    *out_n_marks = n_marks;
    *out_apply_palette_default = i32::from(style_color_is_none != 0);
    *out_x_ship_scale = payload_base_entry_ship_scale(x_axis_type);
    *out_y_ship_scale = payload_base_entry_ship_scale(y_axis_type);
    *out_channel_slot = PAYLOAD_SHIP_CHANNELS_IF_COLOR;
    *out_include_trace_styles = 1;
    *out_attach_transition = 1;
    *out_attempt_gather = i32::from(any_geometry_nulls != 0);
    *out_attach_color2 = i32::from(has_color2_ch != 0);
    1
}

/// Segment emit skeleton from ``_emit_segments``.
///
/// Owns palette default for missing trace color, axis ship scales,
/// trace-channel attach slot/styles, segment gather attempt policy,
/// errorbar role-key transition attach, and transition wrap.
/// Hosts still call ``payload_segments_emit_gather``, apply indices,
/// run ``_rect_finite_sel``, ship columns, and attach channels.
pub fn payload_segments_emit_plan(
    kind: &str,
    n_marks: usize,
    style_color_is_none: i32,
    x_axis_type: i32,
    y_axis_type: i32,
    has_transition_keys: i32,
    out_n_marks: &mut usize,
    out_apply_palette_default: &mut i32,
    out_x_ship_scale: &mut i32,
    out_y_ship_scale: &mut i32,
    out_channel_slot: &mut i32,
    out_include_trace_styles: &mut i32,
    out_attach_transition: &mut i32,
    out_attempt_gather: &mut i32,
    out_attempt_role_keys: &mut i32,
) -> i32 {
    *out_n_marks = n_marks;
    *out_apply_palette_default = i32::from(style_color_is_none != 0);
    *out_x_ship_scale = payload_base_entry_ship_scale(x_axis_type);
    *out_y_ship_scale = payload_base_entry_ship_scale(y_axis_type);
    *out_channel_slot = PAYLOAD_SHIP_CHANNELS_IF_COLOR;
    *out_include_trace_styles = 1;
    *out_attach_transition = 1;
    *out_attempt_gather = 1;
    *out_attempt_role_keys = i32::from(kind == "errorbar" && has_transition_keys != 0);
    1
}

/// Scatter emit skeleton from ``_emit_scatter``.
///
/// Owns density-vs-direct tier routing (``payload_tier`` / ``force_density``
/// tri-state), direct-tier palette default (always off — raw ``t.style``),
/// axis ship scales, trace-channel attach (``PAYLOAD_SHIP_CHANNELS_ALWAYS``),
/// transition wrap (always for density; keyed for direct), tooltip attach
/// flags, and density-path ``shipped_sel`` / ``drill_mode`` side effects.
/// Hosts still visible-select, ship columns, run ``_density_trace_spec``, and
/// attach channels.
pub fn payload_scatter_emit_plan(
    n_points: u64,
    polar: i32,
    force_density: i32,
    force_direct: i32,
    per_item: i32,
    n_marks: usize,
    has_trace_animation: i32,
    x_axis_type: i32,
    y_axis_type: i32,
    has_transition_keys: i32,
    has_tooltip_rows: i32,
    n_tooltip_rows: usize,
    out_emit_density: &mut i32,
    out_clear_shipped_sel: &mut i32,
    out_drill_mode_false: &mut i32,
    out_set_shipped_sel: &mut i32,
    out_tier_direct: &mut i32,
    out_n_marks: &mut usize,
    out_apply_palette_default: &mut i32,
    out_attach_animation: &mut i32,
    out_x_ship_scale: &mut i32,
    out_y_ship_scale: &mut i32,
    out_channel_slot: &mut i32,
    out_include_trace_styles: &mut i32,
    out_attach_transition: &mut i32,
    out_attach_tooltip: &mut i32,
    out_filter_tooltip_by_sel: &mut i32,
    out_tooltip_length_ok: &mut i32,
) -> i32 {
    let Some(tier) = payload_tier(
        PAYLOAD_KIND_SCATTER,
        n_points,
        polar != 0,
        force_density,
        force_direct != 0,
        per_item != 0,
    ) else {
        return 0;
    };
    *out_emit_density = i32::from(tier == PAYLOAD_TIER_DENSITY);
    *out_clear_shipped_sel = 0;
    *out_drill_mode_false = 0;
    *out_set_shipped_sel = 0;
    *out_tier_direct = 0;
    *out_n_marks = 0;
    *out_apply_palette_default = 0;
    *out_attach_animation = 0;
    *out_x_ship_scale = 0;
    *out_y_ship_scale = 0;
    *out_channel_slot = 0;
    *out_include_trace_styles = 0;
    *out_attach_transition = 0;
    *out_attach_tooltip = 0;
    *out_filter_tooltip_by_sel = 0;
    *out_tooltip_length_ok = 1;

    if tier == PAYLOAD_TIER_DENSITY {
        *out_clear_shipped_sel = 1;
        *out_drill_mode_false = 1;
        *out_attach_transition = 1;
        return 1;
    }

    *out_set_shipped_sel = 1;
    *out_tier_direct = 1;
    if payload_base_entry_plan(
        has_trace_animation,
        n_marks,
        0,
        x_axis_type,
        y_axis_type,
        out_attach_animation,
        out_n_marks,
        out_apply_palette_default,
        out_x_ship_scale,
        out_y_ship_scale,
    ) == 0
    {
        return 0;
    }
    *out_apply_palette_default = 0;
    *out_channel_slot = PAYLOAD_SHIP_CHANNELS_ALWAYS;
    *out_include_trace_styles = 1;
    *out_attach_transition = i32::from(has_transition_keys != 0);
    let mut attach_animation = 0i32;
    let mut attempt_keys = 0i32;
    let mut filter_keys_by_sel = 0i32;
    let mut ship_keys = 0i32;
    let mut animation_fallback = 0i32;
    const MAX_ANIMATION_MATCH_ROWS: usize = 200_000;
    if payload_transition_entry_attach(
        0,
        0,
        0,
        0,
        0,
        1,
        n_marks,
        0,
        0,
        0,
        MAX_ANIMATION_MATCH_ROWS,
        has_tooltip_rows,
        n_tooltip_rows,
        n_points as usize,
        &mut attach_animation,
        &mut attempt_keys,
        &mut filter_keys_by_sel,
        &mut ship_keys,
        &mut animation_fallback,
        out_attach_tooltip,
        out_filter_tooltip_by_sel,
        out_tooltip_length_ok,
    ) == 0
    {
        return 0;
    }
    1
}

/// Density trace emit orchestration from ``_density_trace_spec``.
///
/// Composes color classify, bin coord endpoints, ``emit_meta``, visible/sample
/// init, pyramid routing hints, sample-overlay attach, transition wrap, and
/// density wire-admit flags. Hosts still run pyramid compose, bin kernels,
/// buffer shipping, and ``_density_sample_spec`` column gathers.
#[allow(clippy::too_many_arguments)]
pub fn payload_density_trace_emit_plan(
    has_channel: i32,
    mode: &str,
    codes_present: i32,
    codes_u8: i32,
    has_counts: i32,
    has_constant: i32,
    cartesian: i32,
    x_linear: i32,
    y_linear: i32,
    x_has_nulls: i32,
    y_has_nulls: i32,
    point_overlay: i32,
    split_payload: i32,
    grid_w: u32,
    grid_h: u32,
    grid_from_pyramid: i32,
    has_pyramid_resource: i32,
    grid_present: i32,
    force_bin2d: i32,
    force_pyramid: i32,
    x_memmapped: i32,
    y_memmapped: i32,
    x_min: f64,
    x_max: f64,
    y_min: f64,
    y_max: f64,
    xr0: f64,
    xr1: f64,
    yr0: f64,
    yr1: f64,
    bx0: f64,
    bx1: f64,
    by0: f64,
    by1: f64,
    n_points: u64,
    has_pyramid_rgba: i32,
    has_bin_colors: i32,
    dropped_count: i32,
    out_color_mode: &mut i32,
    out_categorical: &mut i32,
    out_compact_categorical: &mut i32,
    out_stratified_counts: &mut i32,
    out_x_c0: &mut f64,
    out_x_c1: &mut f64,
    out_y_c0: &mut f64,
    out_y_c1: &mut f64,
    out_grid_path: &mut i32,
    out_pyramid_eligible: &mut i32,
    out_pyramid_attempt: &mut i32,
    out_pyramid_no_rescan: &mut i32,
    out_pyramid_max_upsample: &mut u32,
    out_pyramid_tile_upsample: &mut u32,
    out_wasm_eligible: &mut i32,
    out_needs_pyramid_sample: &mut i32,
    out_overlay_omitted: &mut u32,
    out_visible_is_n_points: &mut i32,
    out_use_raw_range_bin2d: &mut i32,
    out_attach_transition: &mut i32,
    out_n_marks: &mut usize,
    out_visible_init_n_points: &mut i32,
    out_attach_sample: &mut i32,
    out_pyramid_sample_stratified: &mut i32,
    out_use_channel_colormap: &mut i32,
    out_ship_wasm_source: &mut i32,
    out_ship_mean_color_rgba: &mut i32,
    out_ship_constant_color: &mut i32,
    out_ship_categorical_entry_color: &mut i32,
    out_mean_color_aggregates: &mut i32,
    out_overlay_wire_static_raster: &mut i32,
    out_overlay_wire_rows_exceed: &mut i32,
    out_channels_dropped_compat: &mut i32,
) -> i32 {
    if density_trace_color_classify(
        has_channel,
        mode,
        codes_present,
        codes_u8,
        has_counts,
        out_color_mode,
        out_categorical,
        out_compact_categorical,
        out_stratified_counts,
    ) == 0
    {
        return 0;
    }
    if bin_coord_endpoints(
        x_linear != 0,
        y_linear != 0,
        xr0,
        xr1,
        yr0,
        yr1,
        bx0,
        bx1,
        by0,
        by1,
        out_x_c0,
        out_x_c1,
        out_y_c0,
        out_y_c1,
    ) == 0
    {
        return 0;
    }
    let Some(meta) = emit_meta(
        cartesian != 0,
        x_linear != 0,
        y_linear != 0,
        *out_categorical != 0,
        *out_compact_categorical != 0,
        *out_stratified_counts != 0,
        x_has_nulls != 0,
        y_has_nulls != 0,
        point_overlay != 0,
        grid_from_pyramid != 0,
        x_memmapped != 0,
        y_memmapped != 0,
        has_pyramid_resource != 0,
        force_bin2d != 0,
        force_pyramid != 0,
        *out_color_mode,
        x_min,
        x_max,
        y_min,
        y_max,
        xr0,
        xr1,
        yr0,
        yr1,
        *out_x_c0,
        *out_x_c1,
        *out_y_c0,
        *out_y_c1,
        n_points,
    ) else {
        return 0;
    };
    let n_marks = match (grid_w as usize).checked_mul(grid_h as usize) {
        Some(n) => n,
        None => return 0,
    };
    *out_grid_path = meta.grid_path;
    *out_pyramid_eligible = i32::from(meta.pyramid.eligible);
    *out_pyramid_attempt = i32::from(meta.pyramid.attempt);
    *out_pyramid_no_rescan = i32::from(meta.pyramid.no_rescan);
    *out_pyramid_max_upsample = meta.pyramid.max_upsample;
    *out_pyramid_tile_upsample = meta.pyramid.tile_upsample;
    *out_wasm_eligible = i32::from(meta.wasm_eligible);
    *out_needs_pyramid_sample = i32::from(meta.needs_pyramid_sample);
    *out_overlay_omitted = meta.overlay_omitted;
    *out_visible_is_n_points = i32::from(meta.visible_is_n_points);
    *out_use_raw_range_bin2d = i32::from(meta.use_raw_range_bin2d);
    *out_attach_transition = 1;
    *out_n_marks = n_marks;
    *out_visible_init_n_points = if grid_present != 0 && meta.visible_is_n_points {
        1
    } else if grid_present == 0
        && meta.grid_path >= 0
        && density_grid_path_identity_state(meta.grid_path) == 1
    {
        1
    } else {
        0
    };
    *out_attach_sample = i32::from(
        point_overlay != 0 && meta.overlay_omitted != DENSITY_OVERLAY_ROWS_EXCEED_U32,
    );
    *out_pyramid_sample_stratified =
        i32::from(meta.needs_pyramid_sample && *out_compact_categorical != 0);
    *out_use_channel_colormap = density_uses_channel_colormap(has_channel, mode);
    *out_ship_wasm_source =
        density_wasm_source_admit(split_payload, i32::from(meta.wasm_eligible));
    *out_ship_mean_color_rgba =
        density_mean_color_rgba_wire_admit(has_pyramid_rgba, has_bin_colors);
    *out_mean_color_aggregates = *out_ship_mean_color_rgba;
    *out_ship_constant_color =
        density_constant_color_wire_admit(has_channel, mode, has_constant);
    *out_ship_categorical_entry_color =
        density_categorical_color_wire_admit(*out_categorical, has_channel);
    let mut overlay_buf = [0u8; 32];
    let overlay_len = density_overlay_omitted_wire(
        meta.overlay_omitted,
        point_overlay != 0,
        &mut overlay_buf,
    );
    *out_overlay_wire_static_raster = i32::from(
        overlay_len == Some(b"static_raster".len())
            && overlay_buf.starts_with(b"static_raster"),
    );
    *out_overlay_wire_rows_exceed = i32::from(
        meta.overlay_omitted == DENSITY_OVERLAY_ROWS_EXCEED_U32,
    );
    *out_channels_dropped_compat = density_channels_dropped_compat(dropped_count);
    1
}

/// Transition-entry / tooltip-row attach orchestration from
/// ``_transition_entry`` and ``_attach_tooltip_rows``.
///
/// Hosts still copy animation dicts, ship u32 key planes, and build tooltip
/// row lists. Returns ``1`` on success, ``0`` when ``max_rows`` is zero.
pub fn payload_transition_entry_attach(
    has_trace_animation: i32,
    entry_has_animation: i32,
    has_trace_keys: i32,
    has_key_values: i32,
    has_sel: i32,
    tier_direct: i32,
    n_marks: usize,
    n_trace_key_rows: usize,
    n_key_value_rows: usize,
    n_sel_rows: usize,
    max_rows: usize,
    has_tooltip_rows: i32,
    n_tooltip_rows: usize,
    n_points: usize,
    out_attach_animation: &mut i32,
    out_attempt_keys: &mut i32,
    out_filter_keys_by_sel: &mut i32,
    out_ship_keys: &mut i32,
    out_animation_fallback: &mut i32,
    out_attach_tooltip: &mut i32,
    out_filter_tooltip_by_sel: &mut i32,
    out_tooltip_length_ok: &mut i32,
) -> i32 {
    if max_rows == 0 {
        return 0;
    }
    *out_attach_animation = i32::from(has_trace_animation != 0 && entry_has_animation == 0);
    *out_attempt_keys = 0;
    *out_filter_keys_by_sel = 0;
    *out_ship_keys = 0;
    *out_animation_fallback = PAYLOAD_TRANSITION_SHIP;
    *out_attach_tooltip = 0;
    *out_filter_tooltip_by_sel = 0;
    *out_tooltip_length_ok = 1;

    let attempt_keys = has_key_values != 0 || has_trace_keys != 0;
    *out_attempt_keys = i32::from(attempt_keys);
    if attempt_keys {
        let filter_keys_by_sel = has_key_values == 0 && has_sel != 0;
        *out_filter_keys_by_sel = i32::from(filter_keys_by_sel);
        let n_keys = if has_key_values != 0 {
            n_key_value_rows
        } else if filter_keys_by_sel {
            n_sel_rows
        } else {
            n_trace_key_rows
        };
        let n_marks_eff = if n_marks > 0 { n_marks } else { n_keys };
        let admit = payload_transition_keys_admit(1, tier_direct, n_keys, n_marks_eff, max_rows);
        if admit == PAYLOAD_TRANSITION_SHIP {
            *out_ship_keys = 1;
        } else {
            *out_animation_fallback = admit;
        }
    }

    if has_tooltip_rows != 0 {
        if n_tooltip_rows != n_points {
            *out_tooltip_length_ok = 0;
        } else {
            *out_attach_tooltip = 1;
            *out_filter_tooltip_by_sel = i32::from(has_sel != 0);
        }
    }
    1
}

/// Top-level ``build_payload`` / ``_payload_spec`` attach orchestration.
///
/// Owns when optional figure-level spec sections ship (not field admit).
/// Hosts still build axis specs, dom dicts, legend resolution, and trace emits.
#[allow(clippy::too_many_arguments)]
pub fn payload_build_plan(
    split_payload: i32,
    wasm_source_count: u64,
    has_density_tier: i32,
    coords_cartesian: i32,
    has_title_options: i32,
    has_palette: i32,
    has_legend_options: i32,
    legend_loc_best: i32,
    has_extra_legends: i32,
    has_frame_sides: i32,
    has_colorbar_options: i32,
    show_modebar_is_false: i32,
    has_export_options: i32,
    show_tooltip_is_false: i32,
    has_padding: i32,
    has_dom: i32,
    has_tooltip: i32,
    has_mark_style: i32,
    has_interaction: i32,
    has_annotations: i32,
    has_animation_options: i32,
    has_graph_meta: i32,
    out_attach_show_legend: &mut i32,
    out_wasm_density_kind: &mut i32,
    out_attach_wasm_density: &mut i32,
    out_attach_title_options: &mut i32,
    out_attach_coords: &mut i32,
    out_attach_palette: &mut i32,
    out_attach_legend: &mut i32,
    out_resolve_legend_best: &mut i32,
    out_attach_extra_legends: &mut i32,
    out_attach_frame_sides: &mut i32,
    out_attach_colorbar: &mut i32,
    out_attach_show_modebar: &mut i32,
    out_attach_export: &mut i32,
    out_attach_show_tooltip: &mut i32,
    out_attach_padding: &mut i32,
    out_attach_dom: &mut i32,
    out_attach_tooltip: &mut i32,
    out_attach_mark_style: &mut i32,
    out_attach_interaction: &mut i32,
    out_attach_annotations: &mut i32,
    out_attach_animation: &mut i32,
    out_attach_graph: &mut i32,
) -> i32 {
    *out_attach_show_legend = 1;
    let kind = density_wasm_density_wire_kind(split_payload, wasm_source_count, has_density_tier);
    *out_wasm_density_kind = kind;
    *out_attach_wasm_density = i32::from(kind != DENSITY_WASM_DENSITY_NONE);
    *out_attach_title_options = has_title_options;
    *out_attach_coords = i32::from(coords_cartesian == 0);
    *out_attach_palette = has_palette;
    *out_attach_legend = has_legend_options;
    *out_resolve_legend_best = i32::from(has_legend_options != 0 && legend_loc_best != 0);
    *out_attach_extra_legends = has_extra_legends;
    *out_attach_frame_sides = has_frame_sides;
    *out_attach_colorbar = has_colorbar_options;
    *out_attach_show_modebar = show_modebar_is_false;
    *out_attach_export = has_export_options;
    *out_attach_show_tooltip = show_tooltip_is_false;
    *out_attach_padding = has_padding;
    *out_attach_dom = has_dom;
    *out_attach_tooltip = has_tooltip;
    *out_attach_mark_style = has_mark_style;
    *out_attach_interaction = has_interaction;
    *out_attach_annotations = has_annotations;
    *out_attach_animation = has_animation_options;
    *out_attach_graph = has_graph_meta;
    1
}

fn axis_spec_attach_shared(out: &mut AxisSpecAttachPlanOut) {
    out.attach_id = 1;
    out.attach_kind = 1;
    out.attach_side = 1;
    out.attach_label = 1;
    out.attach_range = 1;
    out.attach_scale = 1;
    out.attach_ticks = 1;
    out.attach_tick_sides = 1;
    out.attach_tick_label_sides = 1;
    out.attach_label_position = 1;
    out.attach_label_offset = 1;
    out.attach_label_angle = 1;
    out.attach_tick_label_angle = 1;
    out.attach_tick_label_strategy = 1;
    out.attach_tick_label_anchor = 1;
    out.attach_tick_label_min_gap = 1;
    out.attach_constant = 1;
    out.attach_nonpositive = 1;
    out.attach_reverse = 1;
    out.attach_domain = 1;
    out.attach_bounds = 1;
    out.attach_minor_style = 1;
    out.attach_format = 1;
    out.attach_style = 1;
    out.attach_categories = 1;
}

struct AxisSpecAttachPlanOut {
    attach_id: i32,
    attach_kind: i32,
    attach_side: i32,
    attach_label: i32,
    attach_range: i32,
    attach_scale: i32,
    attach_ticks: i32,
    attach_tick_sides: i32,
    attach_tick_label_sides: i32,
    attach_label_position: i32,
    attach_label_offset: i32,
    attach_label_angle: i32,
    attach_tick_label_angle: i32,
    attach_tick_label_strategy: i32,
    attach_tick_label_anchor: i32,
    attach_tick_label_min_gap: i32,
    attach_constant: i32,
    attach_nonpositive: i32,
    attach_reverse: i32,
    attach_domain: i32,
    attach_bounds: i32,
    attach_minor_style: i32,
    attach_format: i32,
    attach_style: i32,
    attach_categories: i32,
    attach_theta_unit: i32,
    attach_theta_zero: i32,
    attach_theta_direction: i32,
    attach_sector: i32,
    attach_grid_shape: i32,
    attach_hole: i32,
    attach_r_origin: i32,
}

/// ``_axis_spec`` field attach orchestration for cartesian vs polar axes.
///
/// Owns which axis-spec slots may ship on the wire (not field admit). Hosts
/// still resolve labels, compile styles, and gate optional values.
pub fn payload_axis_spec_attach_plan(
    coords_cartesian: i32,
    axis_is_x: i32,
    out_attach_id: &mut i32,
    out_attach_kind: &mut i32,
    out_attach_side: &mut i32,
    out_attach_label: &mut i32,
    out_attach_range: &mut i32,
    out_attach_scale: &mut i32,
    out_attach_ticks: &mut i32,
    out_attach_tick_sides: &mut i32,
    out_attach_tick_label_sides: &mut i32,
    out_attach_label_position: &mut i32,
    out_attach_label_offset: &mut i32,
    out_attach_label_angle: &mut i32,
    out_attach_tick_label_angle: &mut i32,
    out_attach_tick_label_strategy: &mut i32,
    out_attach_tick_label_anchor: &mut i32,
    out_attach_tick_label_min_gap: &mut i32,
    out_attach_constant: &mut i32,
    out_attach_nonpositive: &mut i32,
    out_attach_reverse: &mut i32,
    out_attach_domain: &mut i32,
    out_attach_bounds: &mut i32,
    out_attach_minor_style: &mut i32,
    out_attach_format: &mut i32,
    out_attach_style: &mut i32,
    out_attach_categories: &mut i32,
    out_attach_theta_unit: &mut i32,
    out_attach_theta_zero: &mut i32,
    out_attach_theta_direction: &mut i32,
    out_attach_sector: &mut i32,
    out_attach_grid_shape: &mut i32,
    out_attach_hole: &mut i32,
    out_attach_r_origin: &mut i32,
) -> i32 {
    let mut out = AxisSpecAttachPlanOut {
        attach_id: 0,
        attach_kind: 0,
        attach_side: 0,
        attach_label: 0,
        attach_range: 0,
        attach_scale: 0,
        attach_ticks: 0,
        attach_tick_sides: 0,
        attach_tick_label_sides: 0,
        attach_label_position: 0,
        attach_label_offset: 0,
        attach_label_angle: 0,
        attach_tick_label_angle: 0,
        attach_tick_label_strategy: 0,
        attach_tick_label_anchor: 0,
        attach_tick_label_min_gap: 0,
        attach_constant: 0,
        attach_nonpositive: 0,
        attach_reverse: 0,
        attach_domain: 0,
        attach_bounds: 0,
        attach_minor_style: 0,
        attach_format: 0,
        attach_style: 0,
        attach_categories: 0,
        attach_theta_unit: 0,
        attach_theta_zero: 0,
        attach_theta_direction: 0,
        attach_sector: 0,
        attach_grid_shape: 0,
        attach_hole: 0,
        attach_r_origin: 0,
    };
    axis_spec_attach_shared(&mut out);
    let polar_theta = coords_cartesian == 0 && axis_is_x != 0;
    let polar_r = coords_cartesian == 0 && axis_is_x == 0;
    out.attach_theta_unit = i32::from(polar_theta);
    out.attach_theta_zero = i32::from(polar_theta);
    out.attach_theta_direction = i32::from(polar_theta);
    out.attach_sector = i32::from(polar_theta);
    out.attach_grid_shape = i32::from(polar_theta);
    out.attach_hole = i32::from(polar_r);
    out.attach_r_origin = i32::from(polar_r);
    *out_attach_id = out.attach_id;
    *out_attach_kind = out.attach_kind;
    *out_attach_side = out.attach_side;
    *out_attach_label = out.attach_label;
    *out_attach_range = out.attach_range;
    *out_attach_scale = out.attach_scale;
    *out_attach_ticks = out.attach_ticks;
    *out_attach_tick_sides = out.attach_tick_sides;
    *out_attach_tick_label_sides = out.attach_tick_label_sides;
    *out_attach_label_position = out.attach_label_position;
    *out_attach_label_offset = out.attach_label_offset;
    *out_attach_label_angle = out.attach_label_angle;
    *out_attach_tick_label_angle = out.attach_tick_label_angle;
    *out_attach_tick_label_strategy = out.attach_tick_label_strategy;
    *out_attach_tick_label_anchor = out.attach_tick_label_anchor;
    *out_attach_tick_label_min_gap = out.attach_tick_label_min_gap;
    *out_attach_constant = out.attach_constant;
    *out_attach_nonpositive = out.attach_nonpositive;
    *out_attach_reverse = out.attach_reverse;
    *out_attach_domain = out.attach_domain;
    *out_attach_bounds = out.attach_bounds;
    *out_attach_minor_style = out.attach_minor_style;
    *out_attach_format = out.attach_format;
    *out_attach_style = out.attach_style;
    *out_attach_categories = out.attach_categories;
    *out_attach_theta_unit = out.attach_theta_unit;
    *out_attach_theta_zero = out.attach_theta_zero;
    *out_attach_theta_direction = out.attach_theta_direction;
    *out_attach_sector = out.attach_sector;
    *out_attach_grid_shape = out.attach_grid_shape;
    *out_attach_hole = out.attach_hole;
    *out_attach_r_origin = out.attach_r_origin;
    1
}

/// Maximum geometry columns returned by ``payload_column_ship_plan``.
pub const PAYLOAD_COLUMN_SHIP_MAX: usize = 8;

/// Spec registry key: ``x``.
pub const PAYLOAD_COL_KEY_X: i32 = 0;
/// Spec registry key: ``y``.
pub const PAYLOAD_COL_KEY_Y: i32 = 1;
/// Spec registry key: ``x0``.
pub const PAYLOAD_COL_KEY_X0: i32 = 2;
/// Spec registry key: ``x1``.
pub const PAYLOAD_COL_KEY_X1: i32 = 3;
/// Spec registry key: ``y0``.
pub const PAYLOAD_COL_KEY_Y0: i32 = 4;
/// Spec registry key: ``y1``.
pub const PAYLOAD_COL_KEY_Y1: i32 = 5;
/// Spec registry key: ``x2``.
pub const PAYLOAD_COL_KEY_X2: i32 = 6;
/// Spec registry key: ``y2``.
pub const PAYLOAD_COL_KEY_Y2: i32 = 7;
/// Spec registry key: ``base`` (area baseline).
pub const PAYLOAD_COL_KEY_BASE: i32 = 8;
/// Spec registry key: ``target_y0`` (ribbon far span on the y scale).
pub const PAYLOAD_COL_KEY_TARGET_Y0: i32 = 9;
/// Spec registry key: ``target_y1``.
pub const PAYLOAD_COL_KEY_TARGET_Y1: i32 = 10;
/// Nested bar spec key: ``pos`` (bar-compact).
pub const PAYLOAD_COL_KEY_POS: i32 = 11;
/// Nested bar spec key: ``value0`` (bar-compact baseline).
pub const PAYLOAD_COL_KEY_VALUE0: i32 = 12;
/// Nested bar spec key: ``value1`` (bar-compact extent).
pub const PAYLOAD_COL_KEY_VALUE1: i32 = 13;

/// Trace column slot: ``t.x``.
pub const PAYLOAD_TRACE_SLOT_X: i32 = 0;
/// Trace column slot: ``t.y``.
pub const PAYLOAD_TRACE_SLOT_Y: i32 = 1;
/// Trace column slot: ``t.x0``.
pub const PAYLOAD_TRACE_SLOT_X0: i32 = 2;
/// Trace column slot: ``t.x1``.
pub const PAYLOAD_TRACE_SLOT_X1: i32 = 3;
/// Trace column slot: ``t.y0``.
pub const PAYLOAD_TRACE_SLOT_Y0: i32 = 4;
/// Trace column slot: ``t.y1``.
pub const PAYLOAD_TRACE_SLOT_Y1: i32 = 5;
/// Trace column slot: ``t.base``.
pub const PAYLOAD_TRACE_SLOT_BASE: i32 = 6;

/// ``pw.ship`` offset-encoded geometry backed by a ``Column``.
pub const PAYLOAD_COL_SHIP_OFFSET: i32 = 0;
/// ``pw.ship_values`` temporary geometry without a canonical ``Column``.
pub const PAYLOAD_COL_SHIP_VALUES: i32 = 1;
/// ``pw.ship_f64`` canonical replay source (density ``wasm_source`` only).
pub const PAYLOAD_COL_SHIP_F64: i32 = 2;

/// Per-column ship scale: x-axis family.
pub const PAYLOAD_COL_SCALE_X: i32 = 0;
/// Per-column ship scale: y-axis family.
pub const PAYLOAD_COL_SCALE_Y: i32 = 1;

/// No row gather before shipping geometry.
pub const PAYLOAD_GATHER_NONE: i32 = 0;
/// ``_visible_sel`` on xy geometry (scatter direct, hexbin).
pub const PAYLOAD_GATHER_VISIBLE_SEL: i32 = 1;
/// ``_rect_finite_sel`` on rectangle geometry (rect, histogram, segments post-decimation).
pub const PAYLOAD_GATHER_RECT_FINITE: i32 = 2;
/// ``valid_indices_f64`` on geometry nulls (+ optional continuous color).
pub const PAYLOAD_GATHER_VALID_INDICES: i32 = 3;
/// ``payload_segments_emit_gather`` then optional ``_rect_finite_sel``.
pub const PAYLOAD_GATHER_SEGMENTS: i32 = 4;
/// ``_m4_decimate`` on parallel xy arrays (line, area).
pub const PAYLOAD_GATHER_M4: i32 = 5;

/// One geometry column in the payload registry.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PayloadColumnShipEntry {
    pub registry_key: i32,
    pub trace_slot: i32,
    pub ship_method: i32,
    pub ship_scale: i32,
    pub gather: i32,
}

/// Column registry / gather policy from per-kind ``_emit_*`` geometry shipping.
///
/// Owns which trace columns ship under which spec keys, offset vs values encode,
/// axis ship-scale selection, and the host gather hook (visible sel, rect finite,
/// valid indices, segment decimation, M4). Hosts still NumPy-gather and call
/// ``pw.ship`` / ``pw.ship_values``. Returns ``1`` on success, ``0`` for unknown
/// kinds.
pub fn payload_column_ship_plan(
    kind: &str,
    x_axis_type: i32,
    y_axis_type: i32,
    orientation: i32,
    out_gather_policy: &mut i32,
    out_gather_include_color: &mut i32,
    out_n_columns: &mut usize,
    out_x_ship_scale: &mut i32,
    out_y_ship_scale: &mut i32,
    out_columns: &mut [PayloadColumnShipEntry; PAYLOAD_COLUMN_SHIP_MAX],
) -> i32 {
    *out_gather_include_color = 0;
    *out_n_columns = 0;
    *out_x_ship_scale = payload_base_entry_ship_scale(x_axis_type);
    *out_y_ship_scale = payload_base_entry_ship_scale(y_axis_type);
    let _x_scale = *out_x_ship_scale;
    let _y_scale = *out_y_ship_scale;

    fn push_rect(out: &mut [PayloadColumnShipEntry; PAYLOAD_COLUMN_SHIP_MAX], n: &mut usize) {
        let cols = [
            PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_X0,
                trace_slot: PAYLOAD_TRACE_SLOT_X0,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_X,
                gather: 1,
            },
            PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_X1,
                trace_slot: PAYLOAD_TRACE_SLOT_X1,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_X,
                gather: 1,
            },
            PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_Y0,
                trace_slot: PAYLOAD_TRACE_SLOT_Y0,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_Y,
                gather: 1,
            },
            PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_Y1,
                trace_slot: PAYLOAD_TRACE_SLOT_Y1,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_Y,
                gather: 1,
            },
        ];
        out[..4].copy_from_slice(&cols);
        *n = 4;
    }

    fn push_xy(
        out: &mut [PayloadColumnShipEntry; PAYLOAD_COLUMN_SHIP_MAX],
        n: &mut usize,
        ship_method: i32,
    ) {
        out[0] = PayloadColumnShipEntry {
            registry_key: PAYLOAD_COL_KEY_X,
            trace_slot: PAYLOAD_TRACE_SLOT_X,
            ship_method,
            ship_scale: PAYLOAD_COL_SCALE_X,
            gather: 1,
        };
        out[1] = PayloadColumnShipEntry {
            registry_key: PAYLOAD_COL_KEY_Y,
            trace_slot: PAYLOAD_TRACE_SLOT_Y,
            ship_method,
            ship_scale: PAYLOAD_COL_SCALE_Y,
            gather: 1,
        };
        *n = 2;
    }

    match kind {
        "line" => {
            *out_gather_policy = PAYLOAD_GATHER_M4;
            push_xy(out_columns, out_n_columns, PAYLOAD_COL_SHIP_OFFSET);
        }
        "area" | "error_band" => {
            *out_gather_policy = PAYLOAD_GATHER_M4;
            push_xy(out_columns, out_n_columns, PAYLOAD_COL_SHIP_OFFSET);
            out_columns[2] = PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_BASE,
                trace_slot: PAYLOAD_TRACE_SLOT_BASE,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_Y,
                gather: 1,
            };
            *out_n_columns = 3;
        }
        "scatter" => {
            *out_gather_policy = PAYLOAD_GATHER_VISIBLE_SEL;
            push_xy(out_columns, out_n_columns, PAYLOAD_COL_SHIP_OFFSET);
        }
        "hexbin" => {
            *out_gather_policy = PAYLOAD_GATHER_VISIBLE_SEL;
            push_xy(out_columns, out_n_columns, PAYLOAD_COL_SHIP_VALUES);
        }
        "density_sample" => {
            *out_gather_policy = PAYLOAD_GATHER_NONE;
            push_xy(out_columns, out_n_columns, PAYLOAD_COL_SHIP_VALUES);
            for entry in out_columns.iter_mut().take(*out_n_columns) {
                entry.gather = 0;
            }
        }
        "density_wasm_source" => {
            *out_gather_policy = PAYLOAD_GATHER_NONE;
            push_xy(out_columns, out_n_columns, PAYLOAD_COL_SHIP_F64);
            for entry in out_columns.iter_mut().take(*out_n_columns) {
                entry.gather = 0;
            }
        }
        "rect" | "histogram" | "box" | "violin" => {
            *out_gather_policy = PAYLOAD_GATHER_RECT_FINITE;
            push_rect(out_columns, out_n_columns);
        }
        "segments"
        | "errorbar"
        | "stem"
        | "box_median"
        | "box_whisker"
        | "contour" => {
            *out_gather_policy = PAYLOAD_GATHER_SEGMENTS;
            push_rect(out_columns, out_n_columns);
        }
        "ribbon" => {
            *out_gather_policy = PAYLOAD_GATHER_VALID_INDICES;
            push_rect(out_columns, out_n_columns);
            out_columns[4] = PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_TARGET_Y0,
                trace_slot: PAYLOAD_TRACE_SLOT_X,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_Y,
                gather: 1,
            };
            out_columns[5] = PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_TARGET_Y1,
                trace_slot: PAYLOAD_TRACE_SLOT_Y,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_Y,
                gather: 1,
            };
            *out_n_columns = 6;
        }
        "triangle_mesh" => {
            *out_gather_policy = PAYLOAD_GATHER_VALID_INDICES;
            *out_gather_include_color = 1;
            out_columns[0] = PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_X0,
                trace_slot: PAYLOAD_TRACE_SLOT_X0,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_X,
                gather: 1,
            };
            out_columns[1] = PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_X1,
                trace_slot: PAYLOAD_TRACE_SLOT_X1,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_X,
                gather: 1,
            };
            out_columns[2] = PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_X2,
                trace_slot: PAYLOAD_TRACE_SLOT_X,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_X,
                gather: 1,
            };
            out_columns[3] = PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_Y0,
                trace_slot: PAYLOAD_TRACE_SLOT_Y0,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_Y,
                gather: 1,
            };
            out_columns[4] = PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_Y1,
                trace_slot: PAYLOAD_TRACE_SLOT_Y1,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_Y,
                gather: 1,
            };
            out_columns[5] = PayloadColumnShipEntry {
                registry_key: PAYLOAD_COL_KEY_Y2,
                trace_slot: PAYLOAD_TRACE_SLOT_Y,
                ship_method: PAYLOAD_COL_SHIP_OFFSET,
                ship_scale: PAYLOAD_COL_SCALE_Y,
                gather: 1,
            };
            *out_n_columns = 6;
        }
        "bar_compact" => {
            *out_gather_policy = PAYLOAD_GATHER_RECT_FINITE;
            match orientation {
                PAYLOAD_BAR_ORIENTATION_VERTICAL => {
                    out_columns[0] = PayloadColumnShipEntry {
                        registry_key: PAYLOAD_COL_KEY_POS,
                        trace_slot: PAYLOAD_TRACE_SLOT_X,
                        ship_method: PAYLOAD_COL_SHIP_OFFSET,
                        ship_scale: PAYLOAD_COL_SCALE_X,
                        gather: 0,
                    };
                    out_columns[1] = PayloadColumnShipEntry {
                        registry_key: PAYLOAD_COL_KEY_VALUE1,
                        trace_slot: PAYLOAD_TRACE_SLOT_Y,
                        ship_method: PAYLOAD_COL_SHIP_OFFSET,
                        ship_scale: PAYLOAD_COL_SCALE_Y,
                        gather: 0,
                    };
                    out_columns[2] = PayloadColumnShipEntry {
                        registry_key: PAYLOAD_COL_KEY_VALUE0,
                        trace_slot: PAYLOAD_TRACE_SLOT_Y0,
                        ship_method: PAYLOAD_COL_SHIP_OFFSET,
                        ship_scale: PAYLOAD_COL_SCALE_Y,
                        gather: 0,
                    };
                }
                PAYLOAD_BAR_ORIENTATION_HORIZONTAL => {
                    out_columns[0] = PayloadColumnShipEntry {
                        registry_key: PAYLOAD_COL_KEY_POS,
                        trace_slot: PAYLOAD_TRACE_SLOT_Y0,
                        ship_method: PAYLOAD_COL_SHIP_VALUES,
                        ship_scale: PAYLOAD_COL_SCALE_Y,
                        gather: 0,
                    };
                    out_columns[1] = PayloadColumnShipEntry {
                        registry_key: PAYLOAD_COL_KEY_VALUE1,
                        trace_slot: PAYLOAD_TRACE_SLOT_X1,
                        ship_method: PAYLOAD_COL_SHIP_OFFSET,
                        ship_scale: PAYLOAD_COL_SCALE_X,
                        gather: 0,
                    };
                    out_columns[2] = PayloadColumnShipEntry {
                        registry_key: PAYLOAD_COL_KEY_VALUE0,
                        trace_slot: PAYLOAD_TRACE_SLOT_X0,
                        ship_method: PAYLOAD_COL_SHIP_OFFSET,
                        ship_scale: PAYLOAD_COL_SCALE_X,
                        gather: 0,
                    };
                }
                _ => return 0,
            }
            *out_n_columns = 3;
        }
        _ => return 0,
    }
    1
}

/// Maximum u8 grid buffers returned by ``payload_density_grid_ship_plan``.
pub const PAYLOAD_DENSITY_GRID_SHIP_MAX_BUFFERS: usize = 2;
/// Maximum attach steps returned by ``payload_density_grid_ship_plan``.
pub const PAYLOAD_DENSITY_GRID_SHIP_MAX_ATTACH: usize = 10;

/// Density grid registry key: ``density["buf"]`` (log-u8 count plane).
pub const PAYLOAD_DENSITY_KEY_BUF: i32 = 0;
/// Density grid registry key: ``density["rgba"]`` (mean-color plane).
pub const PAYLOAD_DENSITY_KEY_RGBA: i32 = 1;

/// Host buffer slot: encoded count grid (``density_log_u8`` output).
pub const PAYLOAD_DENSITY_SLOT_COUNT: i32 = 0;
/// Host buffer slot: mean-color RGBA plane (pyramid or ``bin_2d_mean_color``).
pub const PAYLOAD_DENSITY_SLOT_RGBA: i32 = 1;

/// Ship via host ``ship_u8`` / ``pw.shipU8``.
pub const PAYLOAD_DENSITY_SHIP_U8: i32 = 0;

/// Attach ``density["wasm_source"]`` (f64 replay columns via column registry).
pub const PAYLOAD_DENSITY_ATTACH_WASM_SOURCE: i32 = 0;
/// Attach ``density["tiles"]`` (pyramid tile stats dict).
pub const PAYLOAD_DENSITY_ATTACH_TILES: i32 = 1;
/// Attach ``density["rgba"]`` and ``density["color_agg"] = "mean"``.
pub const PAYLOAD_DENSITY_ATTACH_RGBA: i32 = 2;
/// Attach ``density["channels_dropped"]`` compat scalar.
pub const PAYLOAD_DENSITY_ATTACH_CHANNELS_DROPPED: i32 = 3;
/// Attach ``density["dropped_channels"]`` filtered list.
pub const PAYLOAD_DENSITY_ATTACH_DROPPED_CHANNELS: i32 = 4;
/// Attach ``density["color"]`` constant CSS.
pub const PAYLOAD_DENSITY_ATTACH_CONSTANT_COLOR: i32 = 5;
/// Attach ``density["overlay_omitted"] = "rows_exceed_u32"``.
pub const PAYLOAD_DENSITY_ATTACH_OVERLAY_ROWS_EXCEED: i32 = 6;
/// Attach ``density["sample"]`` overlay spec.
pub const PAYLOAD_DENSITY_ATTACH_SAMPLE: i32 = 7;
/// Attach ``density["overlay_omitted"] = "static_raster"`` when sample omitted.
pub const PAYLOAD_DENSITY_ATTACH_OVERLAY_STATIC_RASTER: i32 = 8;
/// Attach slim categorical ``entry["color"]`` (legend toggle path).
pub const PAYLOAD_DENSITY_ATTACH_ENTRY_COLOR: i32 = 9;

/// One u8 grid buffer in the density registry.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PayloadDensityGridBufferEntry {
    pub registry_key: i32,
    pub buffer_slot: i32,
    pub ship_method: i32,
}

/// One ordered attach step after the count grid ships.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PayloadDensityGridAttachEntry {
    pub attach_kind: i32,
}

/// Density grid buffer registry and attach-order policy from ``_density_trace_spec``.
///
/// Owns which u8 planes ship under ``density["buf"]`` / ``density["rgba"]`` and
/// the ordered nested attach steps (wasm_source, tiles, rgba/color_agg,
/// dropped-channel metadata, constant color, overlay_omitted, sample,
/// entry color). Hosts still run bin2d/pyramid compose, ``density_log_u8``,
/// and buffer materialization.
pub fn payload_density_grid_ship_plan(
    ship_mean_color_rgba: i32,
    ship_wasm_source: i32,
    attach_sample: i32,
    has_tiles: i32,
    ship_constant_color: i32,
    overlay_wire_rows_exceed: i32,
    overlay_wire_static_raster: i32,
    ship_categorical_entry_color: i32,
    out_n_buffers: &mut usize,
    out_buffers: &mut [PayloadDensityGridBufferEntry; PAYLOAD_DENSITY_GRID_SHIP_MAX_BUFFERS],
    out_n_attach: &mut usize,
    out_attach: &mut [PayloadDensityGridAttachEntry; PAYLOAD_DENSITY_GRID_SHIP_MAX_ATTACH],
) -> i32 {
    *out_n_buffers = 0;
    *out_n_attach = 0;

    out_buffers[0] = PayloadDensityGridBufferEntry {
        registry_key: PAYLOAD_DENSITY_KEY_BUF,
        buffer_slot: PAYLOAD_DENSITY_SLOT_COUNT,
        ship_method: PAYLOAD_DENSITY_SHIP_U8,
    };
    *out_n_buffers = 1;
    if ship_mean_color_rgba != 0 {
        out_buffers[1] = PayloadDensityGridBufferEntry {
            registry_key: PAYLOAD_DENSITY_KEY_RGBA,
            buffer_slot: PAYLOAD_DENSITY_SLOT_RGBA,
            ship_method: PAYLOAD_DENSITY_SHIP_U8,
        };
        *out_n_buffers = 2;
    }

    let mut n = 0usize;
    fn push_attach(
        out: &mut [PayloadDensityGridAttachEntry; PAYLOAD_DENSITY_GRID_SHIP_MAX_ATTACH],
        n: &mut usize,
        kind: i32,
    ) {
        out[*n] = PayloadDensityGridAttachEntry { attach_kind: kind };
        *n += 1;
    }

    if ship_wasm_source != 0 {
        push_attach(out_attach, &mut n, PAYLOAD_DENSITY_ATTACH_WASM_SOURCE);
    }
    if has_tiles != 0 {
        push_attach(out_attach, &mut n, PAYLOAD_DENSITY_ATTACH_TILES);
    }
    if ship_mean_color_rgba != 0 {
        push_attach(out_attach, &mut n, PAYLOAD_DENSITY_ATTACH_RGBA);
    }
    push_attach(
        out_attach,
        &mut n,
        PAYLOAD_DENSITY_ATTACH_CHANNELS_DROPPED,
    );
    push_attach(
        out_attach,
        &mut n,
        PAYLOAD_DENSITY_ATTACH_DROPPED_CHANNELS,
    );
    if ship_constant_color != 0 {
        push_attach(
            out_attach,
            &mut n,
            PAYLOAD_DENSITY_ATTACH_CONSTANT_COLOR,
        );
    }
    if overlay_wire_rows_exceed != 0 {
        push_attach(
            out_attach,
            &mut n,
            PAYLOAD_DENSITY_ATTACH_OVERLAY_ROWS_EXCEED,
        );
    }
    if attach_sample != 0 {
        push_attach(out_attach, &mut n, PAYLOAD_DENSITY_ATTACH_SAMPLE);
    } else if overlay_wire_static_raster != 0 {
        push_attach(
            out_attach,
            &mut n,
            PAYLOAD_DENSITY_ATTACH_OVERLAY_STATIC_RASTER,
        );
    }
    if ship_categorical_entry_color != 0 {
        push_attach(out_attach, &mut n, PAYLOAD_DENSITY_ATTACH_ENTRY_COLOR);
    }

    *out_n_attach = n;
    1
}

/// Maximum paint/style channels returned by ``payload_channel_ship_plan``.
pub const PAYLOAD_CHANNEL_SHIP_MAX: usize = 5;

/// Spec registry key: ``color``.
pub const PAYLOAD_CHAN_KEY_COLOR: i32 = 0;
/// Spec registry key: ``size`` (shipped with ``color`` via ``color_size`` method).
pub const PAYLOAD_CHAN_KEY_SIZE: i32 = 1;
/// Spec registry key: ``stroke``.
pub const PAYLOAD_CHAN_KEY_STROKE: i32 = 2;
/// Spec registry key: ``channels`` (style channel dict).
pub const PAYLOAD_CHAN_KEY_CHANNELS: i32 = 3;
/// Spec registry key: ``color_target`` (ribbon far-band paint).
pub const PAYLOAD_CHAN_KEY_COLOR_TARGET: i32 = 4;

/// Trace channel slot: ``t.color_ch``.
pub const PAYLOAD_CHAN_SLOT_COLOR: i32 = 0;
/// Trace channel slot: ``t.size_ch`` (paired with ``color_ch``).
pub const PAYLOAD_CHAN_SLOT_SIZE: i32 = 1;
/// Trace channel slot: ``t.stroke_ch``.
pub const PAYLOAD_CHAN_SLOT_STROKE: i32 = 2;
/// Trace channel slot: ``t.style_channels``.
pub const PAYLOAD_CHAN_SLOT_STYLE: i32 = 3;
/// Trace channel slot: ``t.color2_ch``.
pub const PAYLOAD_CHAN_SLOT_COLOR2: i32 = 4;

/// ``channels.ship_channels`` color+size pair.
pub const PAYLOAD_CHAN_SHIP_COLOR_SIZE: i32 = 0;
/// ``channels.ship_color_channel`` single paint channel.
pub const PAYLOAD_CHAN_SHIP_COLOR: i32 = 1;
/// ``channels.ship_style_channels`` direct style dict.
pub const PAYLOAD_CHAN_SHIP_STYLE: i32 = 2;

/// One paint/style channel in the payload registry.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PayloadChannelShipEntry {
    pub registry_key: i32,
    pub trace_slot: i32,
    pub ship_method: i32,
}

/// Channel registry / attach-order policy from ``_ship_channels`` /
/// ``_ship_trace_channel_attach`` and ribbon ``color2_ch``.
///
/// Owns which trace channels ship under which spec keys and in what order
/// (``color_target`` before the color/size pair). Hosts still slice columns and
/// call ``channels.ship_*`` / ``pw.ship*``. Returns ``1`` on success, ``0`` when
/// ``slot`` is invalid.
pub fn payload_channel_ship_plan(
    slot: i32,
    include_trace_styles: i32,
    has_color2_ch: i32,
    has_color_ch: i32,
    has_stroke_ch: i32,
    has_style_channels: i32,
    out_n_channels: &mut usize,
    out_channels: &mut [PayloadChannelShipEntry; PAYLOAD_CHANNEL_SHIP_MAX],
) -> i32 {
    *out_n_channels = 0;
    let mut n = 0usize;

    fn push(
        out: &mut [PayloadChannelShipEntry; PAYLOAD_CHANNEL_SHIP_MAX],
        n: &mut usize,
        registry_key: i32,
        trace_slot: i32,
        ship_method: i32,
    ) {
        out[*n] = PayloadChannelShipEntry {
            registry_key,
            trace_slot,
            ship_method,
        };
        *n += 1;
    }

    if has_color2_ch != 0 {
        push(
            out_channels,
            &mut n,
            PAYLOAD_CHAN_KEY_COLOR_TARGET,
            PAYLOAD_CHAN_SLOT_COLOR2,
            PAYLOAD_CHAN_SHIP_COLOR,
        );
    }

    let mut ship_color = 0i32;
    let mut ship_size = 0i32;
    let mut ship_stroke = 0i32;
    let mut ship_style = 0i32;
    if payload_trace_channels_ship_attach(
        slot,
        include_trace_styles,
        has_color_ch,
        has_stroke_ch,
        has_style_channels,
        &mut ship_color,
        &mut ship_size,
        &mut ship_stroke,
        &mut ship_style,
    ) == 0
    {
        return 0;
    }

    if ship_color != 0 {
        push(
            out_channels,
            &mut n,
            PAYLOAD_CHAN_KEY_COLOR,
            PAYLOAD_CHAN_SLOT_COLOR,
            PAYLOAD_CHAN_SHIP_COLOR_SIZE,
        );
    }
    if ship_stroke != 0 {
        push(
            out_channels,
            &mut n,
            PAYLOAD_CHAN_KEY_STROKE,
            PAYLOAD_CHAN_SLOT_STROKE,
            PAYLOAD_CHAN_SHIP_COLOR,
        );
    }
    if ship_style != 0 {
        push(
            out_channels,
            &mut n,
            PAYLOAD_CHAN_KEY_CHANNELS,
            PAYLOAD_CHAN_SLOT_STYLE,
            PAYLOAD_CHAN_SHIP_STYLE,
        );
    }

    *out_n_channels = n;
    1
}

/// Client palette LUT width; categorical codes ship as u8 at or below this count.
pub const PAYLOAD_CHAN_MAX_CATEGORIES_U8: usize = 256;

/// Wire-encode role: color / stroke paint (``ship_color_channel``).
pub const PAYLOAD_CHAN_WIRE_ROLE_COLOR: i32 = 0;
/// Wire-encode role: size channel (``ship_channels`` size half).
pub const PAYLOAD_CHAN_WIRE_ROLE_SIZE: i32 = 1;
/// Wire-encode role: direct style channel (``ship_style_channels``).
pub const PAYLOAD_CHAN_WIRE_ROLE_STYLE: i32 = 2;

/// Channel mode: constant (spec-only, no buffer).
pub const PAYLOAD_CHAN_MODE_CONSTANT: i32 = 0;
/// Channel mode: continuous normalized or quantized unit values.
pub const PAYLOAD_CHAN_MODE_CONTINUOUS: i32 = 1;
/// Channel mode: categorical palette-index codes.
pub const PAYLOAD_CHAN_MODE_CATEGORICAL: i32 = 2;
/// Channel mode: per-item packed RGBA8.
pub const PAYLOAD_CHAN_MODE_DIRECT_RGBA: i32 = 3;
/// Channel mode: match_fill (spec-only, no buffer).
pub const PAYLOAD_CHAN_MODE_MATCH_FILL: i32 = 4;
/// Channel mode: direct style values (``StyleChannel``).
pub const PAYLOAD_CHAN_MODE_DIRECT: i32 = 5;

/// No buffer is shipped for this channel slice.
pub const PAYLOAD_CHAN_BUF_NONE: i32 = 0;
/// Ship via host ``ship_u8`` / ``pw.shipU8``.
pub const PAYLOAD_CHAN_BUF_U8: i32 = 1;
/// Ship via host ``ship_scalar`` / ``pw.shipScalar`` (unit f32).
pub const PAYLOAD_CHAN_BUF_F32: i32 = 2;

/// No value transform before ship.
pub const PAYLOAD_CHAN_XFORM_NONE: i32 = 0;
/// ``normalize_to_unit`` / ``normalizeF32`` over the channel domain.
pub const PAYLOAD_CHAN_XFORM_NORMALIZE: i32 = 1;
/// ``quantize_unit_u8`` / ``quantizeUnitU8`` over the channel domain.
pub const PAYLOAD_CHAN_XFORM_QUANTIZE_U8: i32 = 2;
/// ``_quantized_rgba8`` pack then u8 ship (direct_rgba).
pub const PAYLOAD_CHAN_XFORM_RGBA_PACK: i32 = 3;
/// Passthrough values (style channels, categorical codes).
pub const PAYLOAD_CHAN_XFORM_RAW: i32 = 4;

/// Channel wire encoding policy from ``channels.ship_*`` (ABI 312).
///
/// Owns buffer kind (none/u8/f32), pre-ship transform, and spec flags
/// (``dtype: "u8"``, categorical ``palette``, per-item ``n``). Hosts still
/// slice columns, run the chosen transform, and ship buffers.
///
/// Returns ``1`` on success, ``0`` when ``role``/``mode`` is invalid.
pub fn payload_channel_wire_encode(
    role: i32,
    mode: i32,
    n_categories: usize,
    style_dtype_u8: i32,
    quantize_continuous: i32,
    out_buf_kind: &mut i32,
    out_transform: &mut i32,
    out_mark_dtype_u8: &mut i32,
    out_ship_palette: &mut i32,
    out_set_n: &mut i32,
) -> i32 {
    *out_buf_kind = PAYLOAD_CHAN_BUF_NONE;
    *out_transform = PAYLOAD_CHAN_XFORM_NONE;
    *out_mark_dtype_u8 = 0;
    *out_ship_palette = 0;
    *out_set_n = 0;

    match role {
        PAYLOAD_CHAN_WIRE_ROLE_COLOR => match mode {
            PAYLOAD_CHAN_MODE_CONSTANT | PAYLOAD_CHAN_MODE_MATCH_FILL => 1,
            PAYLOAD_CHAN_MODE_DIRECT_RGBA => {
                *out_buf_kind = PAYLOAD_CHAN_BUF_U8;
                *out_transform = PAYLOAD_CHAN_XFORM_RGBA_PACK;
                *out_set_n = 1;
                1
            }
            PAYLOAD_CHAN_MODE_CONTINUOUS => {
                if quantize_continuous != 0 {
                    *out_buf_kind = PAYLOAD_CHAN_BUF_U8;
                    *out_transform = PAYLOAD_CHAN_XFORM_QUANTIZE_U8;
                    *out_mark_dtype_u8 = 1;
                } else {
                    *out_buf_kind = PAYLOAD_CHAN_BUF_F32;
                    *out_transform = PAYLOAD_CHAN_XFORM_NORMALIZE;
                }
                1
            }
            PAYLOAD_CHAN_MODE_CATEGORICAL => {
                *out_ship_palette = 1;
                if n_categories <= PAYLOAD_CHAN_MAX_CATEGORIES_U8 {
                    *out_buf_kind = PAYLOAD_CHAN_BUF_U8;
                    *out_transform = PAYLOAD_CHAN_XFORM_RAW;
                    *out_mark_dtype_u8 = 1;
                } else {
                    *out_buf_kind = PAYLOAD_CHAN_BUF_F32;
                    *out_transform = PAYLOAD_CHAN_XFORM_RAW;
                }
                1
            }
            _ => 0,
        },
        PAYLOAD_CHAN_WIRE_ROLE_SIZE => match mode {
            PAYLOAD_CHAN_MODE_CONSTANT => 1,
            PAYLOAD_CHAN_MODE_CONTINUOUS => {
                if quantize_continuous != 0 {
                    *out_buf_kind = PAYLOAD_CHAN_BUF_U8;
                    *out_transform = PAYLOAD_CHAN_XFORM_QUANTIZE_U8;
                    *out_mark_dtype_u8 = 1;
                } else {
                    *out_buf_kind = PAYLOAD_CHAN_BUF_F32;
                    *out_transform = PAYLOAD_CHAN_XFORM_NORMALIZE;
                }
                1
            }
            _ => 0,
        },
        PAYLOAD_CHAN_WIRE_ROLE_STYLE => {
            if mode != PAYLOAD_CHAN_MODE_DIRECT {
                return 0;
            }
            *out_buf_kind = if style_dtype_u8 != 0 {
                PAYLOAD_CHAN_BUF_U8
            } else {
                PAYLOAD_CHAN_BUF_F32
            };
            *out_transform = PAYLOAD_CHAN_XFORM_RAW;
            *out_set_n = 1;
            1
        }
        _ => 0,
    }
}

/// Trace channel attach policy from ``_ship_channels`` / ``_ship_trace_styles``.
///
/// ``slot`` is ``PAYLOAD_SHIP_CHANNELS_ALWAYS`` or ``PAYLOAD_SHIP_CHANNELS_IF_COLOR``.
/// When ``include_trace_styles`` is zero, stroke and style-channel slots stay off
/// (hexbin). Returns ``1`` on success, ``0`` when ``slot`` is invalid.
pub fn payload_trace_channels_ship_attach(
    slot: i32,
    include_trace_styles: i32,
    has_color_ch: i32,
    has_stroke_ch: i32,
    has_style_channels: i32,
    out_ship_color: &mut i32,
    out_ship_size: &mut i32,
    out_ship_stroke: &mut i32,
    out_ship_style_channels: &mut i32,
) -> i32 {
    let ship_color_size = match slot {
        PAYLOAD_SHIP_CHANNELS_ALWAYS => true,
        PAYLOAD_SHIP_CHANNELS_IF_COLOR => has_color_ch != 0,
        _ => return 0,
    };
    *out_ship_color = i32::from(ship_color_size);
    *out_ship_size = i32::from(ship_color_size);
    if include_trace_styles != 0 {
        *out_ship_stroke = i32::from(has_stroke_ch != 0);
        *out_ship_style_channels = i32::from(has_style_channels != 0);
    } else {
        *out_ship_stroke = 0;
        *out_ship_style_channels = 0;
    }
    1
}

/// Segment emit gather orchestration from ``_emit_segments`` (ABI 292).
///
/// Owns errorbar role-map setup plus stem/errorbar decimation index selection.
/// Hosts apply returned indices to geometry arrays and run ``_rect_finite_sel``
/// separately.
pub fn payload_segments_emit_gather(
    kind: &str,
    n_segments: usize,
    n_points: usize,
    px_width: f64,
    out_tier: &mut i32,
    out_role_maps: &mut i32,
    out_keep_all: &mut i32,
    out_indices: &mut [u32],
    out_sources: &mut [u32],
    out_roles: &mut [u32],
) -> Option<usize> {
    if n_segments > u32::MAX as usize {
        return None;
    }
    let budget = payload_segment_budget(px_width)?;
    *out_tier = PAYLOAD_SEGMENTS_TIER_DIRECT;
    *out_role_maps = 0;
    *out_keep_all = 1;
    let n_out;

    match kind {
        "errorbar" if n_points > 0 => {
            let mut sources_full = vec![0u32; n_segments];
            let mut roles_full = vec![0u32; n_segments];
            let mut applicable = 0i32;
            if payload_errorbar_role_maps(
                n_segments,
                n_points,
                &mut sources_full,
                &mut roles_full,
                &mut applicable,
            ) == 1
                && applicable == 1
            {
                *out_role_maps = 1;
            }
            let sel = payload_errorbar_indices(n_segments, n_points, budget)?;
            match sel {
                PayloadIndexSel::KeepAll => {
                    n_out = n_segments;
                    if *out_role_maps == 1 {
                        if out_sources.len() < n_segments || out_roles.len() < n_segments {
                            return Some(n_segments);
                        }
                        out_sources[..n_segments].copy_from_slice(&sources_full);
                        out_roles[..n_segments].copy_from_slice(&roles_full);
                    }
                }
                PayloadIndexSel::Indices(indices) => {
                    *out_tier = PAYLOAD_SEGMENTS_TIER_DECIMATED;
                    *out_keep_all = 0;
                    n_out = indices.len();
                    if out_indices.len() < n_out {
                        return Some(n_out);
                    }
                    out_indices[..n_out].copy_from_slice(&indices);
                    if *out_role_maps == 1 {
                        if out_sources.len() < n_out || out_roles.len() < n_out {
                            return Some(n_out);
                        }
                        for (i, &idx) in indices.iter().enumerate() {
                            let j = idx as usize;
                            out_sources[i] = sources_full[j];
                            out_roles[i] = roles_full[j];
                        }
                    }
                }
            }
        }
        "stem" if n_segments > budget => match payload_even_indices(n_segments, budget)? {
            PayloadIndexSel::KeepAll => {
                n_out = n_segments;
            }
            PayloadIndexSel::Indices(indices) => {
                *out_tier = PAYLOAD_SEGMENTS_TIER_DECIMATED;
                *out_keep_all = 0;
                n_out = indices.len();
                if out_indices.len() < n_out {
                    return Some(n_out);
                }
                out_indices[..n_out].copy_from_slice(&indices);
            }
        },
        _ => {
            n_out = n_segments;
        }
    }
    Some(n_out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn payload_segments_emit_gather_errorbar_role_maps_without_decimation() {
        let n_segments = 33;
        let n_points = 11;
        let mut tier = -1;
        let mut role_maps = -1;
        let mut keep_all = -1;
        let mut indices = vec![0u32; n_segments];
        let mut sources = vec![0u32; n_segments];
        let mut roles = vec![0u32; n_segments];
        let n_out = payload_segments_emit_gather(
            "errorbar",
            n_segments,
            n_points,
            100.0,
            &mut tier,
            &mut role_maps,
            &mut keep_all,
            &mut indices,
            &mut sources,
            &mut roles,
        )
        .unwrap();
        assert_eq!(tier, PAYLOAD_SEGMENTS_TIER_DIRECT);
        assert_eq!(role_maps, 1);
        assert_eq!(keep_all, 1);
        assert_eq!(n_out, n_segments);
        assert_eq!(sources[0], 0);
        assert_eq!(sources[10], 10);
        assert_eq!(sources[11], 0);
        assert_eq!(roles[10], 0);
        assert_eq!(roles[11], 1);
    }

    #[test]
    fn payload_segments_emit_gather_stem_decimates_without_roles() {
        let n_segments = 3000;
        let mut tier = -1;
        let mut role_maps = -1;
        let mut keep_all = -1;
        let mut indices = vec![0u32; n_segments];
        let mut sources = vec![0u32; 0];
        let mut roles = vec![0u32; 0];
        let n_out = payload_segments_emit_gather(
            "stem",
            n_segments,
            0,
            100.0,
            &mut tier,
            &mut role_maps,
            &mut keep_all,
            &mut indices,
            &mut sources,
            &mut roles,
        )
        .unwrap();
        assert_eq!(tier, PAYLOAD_SEGMENTS_TIER_DECIMATED);
        assert_eq!(role_maps, 0);
        assert_eq!(keep_all, 0);
        assert_eq!(n_out, 1024);
    }

    #[test]
    fn payload_trace_channels_ship_attach_scatter_always() {
        let mut ship_color = -1;
        let mut ship_size = -1;
        let mut ship_stroke = -1;
        let mut ship_style = -1;
        assert_eq!(
            payload_trace_channels_ship_attach(
                PAYLOAD_SHIP_CHANNELS_ALWAYS,
                1,
                0,
                1,
                1,
                &mut ship_color,
                &mut ship_size,
                &mut ship_stroke,
                &mut ship_style,
            ),
            1
        );
        assert_eq!(ship_color, 1);
        assert_eq!(ship_size, 1);
        assert_eq!(ship_stroke, 1);
        assert_eq!(ship_style, 1);
    }

    #[test]
    fn payload_trace_channels_ship_attach_hexbin_skips_trace_styles() {
        let mut ship_color = -1;
        let mut ship_size = -1;
        let mut ship_stroke = -1;
        let mut ship_style = -1;
        assert_eq!(
            payload_trace_channels_ship_attach(
                PAYLOAD_SHIP_CHANNELS_ALWAYS,
                0,
                0,
                1,
                1,
                &mut ship_color,
                &mut ship_size,
                &mut ship_stroke,
                &mut ship_style,
            ),
            1
        );
        assert_eq!(ship_color, 1);
        assert_eq!(ship_stroke, 0);
        assert_eq!(ship_style, 0);
    }

    #[test]
    fn payload_trace_channels_ship_attach_geometry_if_color() {
        let mut ship_color = -1;
        let mut ship_size = -1;
        let mut ship_stroke = -1;
        let mut ship_style = -1;
        assert_eq!(
            payload_trace_channels_ship_attach(
                PAYLOAD_SHIP_CHANNELS_IF_COLOR,
                1,
                0,
                1,
                0,
                &mut ship_color,
                &mut ship_size,
                &mut ship_stroke,
                &mut ship_style,
            ),
            1
        );
        assert_eq!(ship_color, 0);
        assert_eq!(ship_size, 0);
        assert_eq!(ship_stroke, 1);
        assert_eq!(
            payload_trace_channels_ship_attach(
                PAYLOAD_SHIP_CHANNELS_IF_COLOR,
                1,
                1,
                0,
                1,
                &mut ship_color,
                &mut ship_size,
                &mut ship_stroke,
                &mut ship_style,
            ),
            1
        );
        assert_eq!(ship_color, 1);
        assert_eq!(ship_stroke, 0);
        assert_eq!(ship_style, 1);
    }

    #[test]
    fn payload_trace_channels_ship_attach_rejects_unknown_slot() {
        let mut ship_color = 0;
        let mut ship_size = 0;
        let mut ship_stroke = 0;
        let mut ship_style = 0;
        assert_eq!(
            payload_trace_channels_ship_attach(
                9,
                1,
                1,
                1,
                1,
                &mut ship_color,
                &mut ship_size,
                &mut ship_stroke,
                &mut ship_style,
            ),
            0
        );
    }

    fn run_channel_ship_plan(
        slot: i32,
        include_trace_styles: i32,
        has_color2_ch: i32,
        has_color_ch: i32,
        has_stroke_ch: i32,
        has_style_channels: i32,
    ) -> (i32, usize, [PayloadChannelShipEntry; PAYLOAD_CHANNEL_SHIP_MAX]) {
        let mut n = 0usize;
        let mut cols = [PayloadChannelShipEntry {
            registry_key: -1,
            trace_slot: -1,
            ship_method: -1,
        }; PAYLOAD_CHANNEL_SHIP_MAX];
        let ok = payload_channel_ship_plan(
            slot,
            include_trace_styles,
            has_color2_ch,
            has_color_ch,
            has_stroke_ch,
            has_style_channels,
            &mut n,
            &mut cols,
        );
        (ok, n, cols)
    }

    #[test]
    fn payload_channel_ship_plan_scatter_color_size_stroke_style() {
        let (ok, n, cols) = run_channel_ship_plan(
            PAYLOAD_SHIP_CHANNELS_ALWAYS,
            1,
            0,
            0,
            1,
            1,
        );
        assert_eq!(ok, 1);
        assert_eq!(n, 3);
        assert_eq!(cols[0].registry_key, PAYLOAD_CHAN_KEY_COLOR);
        assert_eq!(cols[0].ship_method, PAYLOAD_CHAN_SHIP_COLOR_SIZE);
        assert_eq!(cols[1].registry_key, PAYLOAD_CHAN_KEY_STROKE);
        assert_eq!(cols[2].registry_key, PAYLOAD_CHAN_KEY_CHANNELS);
    }

    #[test]
    fn payload_channel_ship_plan_ribbon_color2_before_color_size() {
        let (ok, n, cols) = run_channel_ship_plan(
            PAYLOAD_SHIP_CHANNELS_IF_COLOR,
            1,
            1,
            1,
            0,
            0,
        );
        assert_eq!(ok, 1);
        assert_eq!(n, 2);
        assert_eq!(cols[0].registry_key, PAYLOAD_CHAN_KEY_COLOR_TARGET);
        assert_eq!(cols[0].trace_slot, PAYLOAD_CHAN_SLOT_COLOR2);
        assert_eq!(cols[1].registry_key, PAYLOAD_CHAN_KEY_COLOR);
    }

    #[test]
    fn payload_channel_ship_plan_hexbin_color_size_only() {
        let (ok, n, cols) = run_channel_ship_plan(
            PAYLOAD_SHIP_CHANNELS_ALWAYS,
            0,
            0,
            0,
            1,
            1,
        );
        assert_eq!(ok, 1);
        assert_eq!(n, 1);
        assert_eq!(cols[0].ship_method, PAYLOAD_CHAN_SHIP_COLOR_SIZE);
    }

    #[test]
    fn payload_channel_ship_plan_rejects_unknown_slot() {
        let (ok, n, _) = run_channel_ship_plan(9, 1, 0, 1, 1, 1);
        assert_eq!(ok, 0);
        assert_eq!(n, 0);
    }

    fn run_channel_wire_encode(
        role: i32,
        mode: i32,
        n_categories: usize,
        style_dtype_u8: i32,
        quantize_continuous: i32,
    ) -> (i32, i32, i32, i32, i32, i32) {
        let mut buf_kind = -1;
        let mut transform = -1;
        let mut mark_dtype_u8 = -1;
        let mut ship_palette = -1;
        let mut set_n = -1;
        let ok = payload_channel_wire_encode(
            role,
            mode,
            n_categories,
            style_dtype_u8,
            quantize_continuous,
            &mut buf_kind,
            &mut transform,
            &mut mark_dtype_u8,
            &mut ship_palette,
            &mut set_n,
        );
        (ok, buf_kind, transform, mark_dtype_u8, ship_palette, set_n)
    }

    #[test]
    fn payload_channel_wire_encode_continuous_f32_and_quantized_u8() {
        let (ok, buf, xform, dtype_u8, _, _) = run_channel_wire_encode(
            PAYLOAD_CHAN_WIRE_ROLE_COLOR,
            PAYLOAD_CHAN_MODE_CONTINUOUS,
            0,
            0,
            0,
        );
        assert_eq!(ok, 1);
        assert_eq!(buf, PAYLOAD_CHAN_BUF_F32);
        assert_eq!(xform, PAYLOAD_CHAN_XFORM_NORMALIZE);
        assert_eq!(dtype_u8, 0);

        let (ok, buf, xform, dtype_u8, _, _) = run_channel_wire_encode(
            PAYLOAD_CHAN_WIRE_ROLE_SIZE,
            PAYLOAD_CHAN_MODE_CONTINUOUS,
            0,
            0,
            1,
        );
        assert_eq!(ok, 1);
        assert_eq!(buf, PAYLOAD_CHAN_BUF_U8);
        assert_eq!(xform, PAYLOAD_CHAN_XFORM_QUANTIZE_U8);
        assert_eq!(dtype_u8, 1);
    }

    #[test]
    fn payload_channel_wire_encode_categorical_u8_vs_f32() {
        let (ok, buf, _, dtype_u8, palette, _) = run_channel_wire_encode(
            PAYLOAD_CHAN_WIRE_ROLE_COLOR,
            PAYLOAD_CHAN_MODE_CATEGORICAL,
            256,
            0,
            0,
        );
        assert_eq!(ok, 1);
        assert_eq!(buf, PAYLOAD_CHAN_BUF_U8);
        assert_eq!(dtype_u8, 1);
        assert_eq!(palette, 1);

        let (ok, buf, _, dtype_u8, palette, _) = run_channel_wire_encode(
            PAYLOAD_CHAN_WIRE_ROLE_COLOR,
            PAYLOAD_CHAN_MODE_CATEGORICAL,
            257,
            0,
            0,
        );
        assert_eq!(ok, 1);
        assert_eq!(buf, PAYLOAD_CHAN_BUF_F32);
        assert_eq!(dtype_u8, 0);
        assert_eq!(palette, 1);
    }

    #[test]
    fn payload_channel_wire_encode_direct_rgba_and_style() {
        let (ok, buf, xform, _, _, set_n) = run_channel_wire_encode(
            PAYLOAD_CHAN_WIRE_ROLE_COLOR,
            PAYLOAD_CHAN_MODE_DIRECT_RGBA,
            0,
            0,
            0,
        );
        assert_eq!(ok, 1);
        assert_eq!(buf, PAYLOAD_CHAN_BUF_U8);
        assert_eq!(xform, PAYLOAD_CHAN_XFORM_RGBA_PACK);
        assert_eq!(set_n, 1);

        let (ok, buf, xform, _, _, set_n) = run_channel_wire_encode(
            PAYLOAD_CHAN_WIRE_ROLE_STYLE,
            PAYLOAD_CHAN_MODE_DIRECT,
            0,
            1,
            0,
        );
        assert_eq!(ok, 1);
        assert_eq!(buf, PAYLOAD_CHAN_BUF_U8);
        assert_eq!(xform, PAYLOAD_CHAN_XFORM_RAW);
        assert_eq!(set_n, 1);
    }

    #[test]
    fn payload_channel_wire_encode_rejects_invalid_role_mode() {
        assert_eq!(
            run_channel_wire_encode(
                PAYLOAD_CHAN_WIRE_ROLE_SIZE,
                PAYLOAD_CHAN_MODE_CATEGORICAL,
                0,
                0,
                0,
            )
            .0,
            0
        );
    }

    #[test]
    fn payload_segments_emit_gather_other_stays_direct() {
        let mut tier = -1;
        let mut role_maps = -1;
        let mut keep_all = -1;
        let mut indices = vec![0u32; 0];
        let mut sources = vec![0u32; 0];
        let mut roles = vec![0u32; 0];
        let n_out = payload_segments_emit_gather(
            "segments",
            50,
            0,
            100.0,
            &mut tier,
            &mut role_maps,
            &mut keep_all,
            &mut indices,
            &mut sources,
            &mut roles,
        )
        .unwrap();
        assert_eq!(tier, PAYLOAD_SEGMENTS_TIER_DIRECT);
        assert_eq!(role_maps, 0);
        assert_eq!(keep_all, 1);
        assert_eq!(n_out, 50);
    }

    #[test]
    fn payload_transition_entry_attach_animation_and_ship_keys() {
        let mut attach_animation = -1;
        let mut attempt_keys = -1;
        let mut filter_keys = -1;
        let mut ship_keys = -1;
        let mut fallback = -1;
        let mut attach_tooltip = -1;
        let mut filter_tooltip = -1;
        let mut tooltip_ok = -1;
        assert_eq!(
            payload_transition_entry_attach(
                1,
                0,
                1,
                0,
                0,
                1,
                10,
                10,
                0,
                0,
                200_000,
                0,
                0,
                0,
                &mut attach_animation,
                &mut attempt_keys,
                &mut filter_keys,
                &mut ship_keys,
                &mut fallback,
                &mut attach_tooltip,
                &mut filter_tooltip,
                &mut tooltip_ok,
            ),
            1
        );
        assert_eq!(attach_animation, 1);
        assert_eq!(attempt_keys, 1);
        assert_eq!(filter_keys, 0);
        assert_eq!(ship_keys, 1);
        assert_eq!(fallback, PAYLOAD_TRANSITION_SHIP);
        assert_eq!(attach_tooltip, 0);
        assert_eq!(tooltip_ok, 1);
    }

    #[test]
    fn payload_transition_entry_attach_decimated_snap_aggregate() {
        let mut attach_animation = 0;
        let mut attempt_keys = 0;
        let mut filter_keys = 0;
        let mut ship_keys = 0;
        let mut fallback = 0;
        let mut attach_tooltip = 0;
        let mut filter_tooltip = 0;
        let mut tooltip_ok = 0;
        assert_eq!(
            payload_transition_entry_attach(
                0,
                0,
                1,
                0,
                0,
                0,
                10,
                10,
                0,
                0,
                200_000,
                0,
                0,
                0,
                &mut attach_animation,
                &mut attempt_keys,
                &mut filter_keys,
                &mut ship_keys,
                &mut fallback,
                &mut attach_tooltip,
                &mut filter_tooltip,
                &mut tooltip_ok,
            ),
            1
        );
        assert_eq!(ship_keys, 0);
        assert_eq!(fallback, 1);
    }

    #[test]
    fn payload_transition_entry_attach_filter_keys_and_tooltip() {
        let mut attach_animation = 0;
        let mut attempt_keys = 0;
        let mut filter_keys = 0;
        let mut ship_keys = 0;
        let mut fallback = 0;
        let mut attach_tooltip = 0;
        let mut filter_tooltip = 0;
        let mut tooltip_ok = 0;
        assert_eq!(
            payload_transition_entry_attach(
                0,
                0,
                1,
                0,
                1,
                1,
                3,
                5,
                0,
                3,
                200_000,
                1,
                5,
                5,
                &mut attach_animation,
                &mut attempt_keys,
                &mut filter_keys,
                &mut ship_keys,
                &mut fallback,
                &mut attach_tooltip,
                &mut filter_tooltip,
                &mut tooltip_ok,
            ),
            1
        );
        assert_eq!(filter_keys, 1);
        assert_eq!(ship_keys, 1);
        assert_eq!(attach_tooltip, 1);
        assert_eq!(filter_tooltip, 1);
        assert_eq!(tooltip_ok, 1);
    }

    #[test]
    fn payload_transition_entry_attach_tooltip_length_mismatch() {
        let mut attach_animation = 0;
        let mut attempt_keys = 0;
        let mut filter_keys = 0;
        let mut ship_keys = 0;
        let mut fallback = 0;
        let mut attach_tooltip = 0;
        let mut filter_tooltip = 0;
        let mut tooltip_ok = 0;
        assert_eq!(
            payload_transition_entry_attach(
                0,
                0,
                0,
                0,
                0,
                1,
                0,
                0,
                0,
                0,
                200_000,
                1,
                2,
                3,
                &mut attach_animation,
                &mut attempt_keys,
                &mut filter_keys,
                &mut ship_keys,
                &mut fallback,
                &mut attach_tooltip,
                &mut filter_tooltip,
                &mut tooltip_ok,
            ),
            1
        );
        assert_eq!(attach_tooltip, 0);
        assert_eq!(tooltip_ok, 0);
    }

    #[test]
    fn payload_base_entry_plan_ships_animation_and_marks() {
        let mut attach_animation = -1;
        let mut n_marks = 0;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        assert_eq!(
            payload_base_entry_plan(
                1,
                42,
                1,
                1,
                2,
                &mut attach_animation,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
            ),
            1
        );
        assert_eq!(attach_animation, 1);
        assert_eq!(n_marks, 42);
        assert_eq!(apply_palette, 1);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG);
        assert_eq!(y_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_SYMLOG);
    }

    #[test]
    fn payload_base_entry_plan_linear_without_animation() {
        let mut attach_animation = -1;
        let mut n_marks = 0;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        assert_eq!(
            payload_base_entry_plan(
                0,
                5,
                0,
                0,
                9,
                &mut attach_animation,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
            ),
            1
        );
        assert_eq!(attach_animation, 0);
        assert_eq!(n_marks, 5);
        assert_eq!(apply_palette, 0);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LINEAR);
        assert_eq!(y_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LINEAR);
    }

    #[test]
    fn payload_nonxy_emit_plan_rect_ships_if_color_and_transition() {
        let mut tier_direct = -1;
        let mut n_marks = 0;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        assert_eq!(
            payload_nonxy_emit_plan(
                PAYLOAD_NONXY_KIND_RECT,
                7,
                1,
                1,
                0,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
            ),
            1
        );
        assert_eq!(tier_direct, 1);
        assert_eq!(n_marks, 7);
        assert_eq!(apply_palette, 1);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG);
        assert_eq!(y_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LINEAR);
        assert_eq!(slot, PAYLOAD_SHIP_CHANNELS_IF_COLOR);
        assert_eq!(include_styles, 1);
        assert_eq!(attach_transition, 1);
    }

    #[test]
    fn payload_nonxy_emit_plan_hexbin_always_color_no_styles() {
        let mut tier_direct = -1;
        let mut n_marks = 0;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        assert_eq!(
            payload_nonxy_emit_plan(
                PAYLOAD_NONXY_KIND_HEXBIN,
                12,
                0,
                2,
                2,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
            ),
            1
        );
        assert_eq!(n_marks, 12);
        assert_eq!(apply_palette, 0);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_SYMLOG);
        assert_eq!(y_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_SYMLOG);
        assert_eq!(slot, PAYLOAD_SHIP_CHANNELS_ALWAYS);
        assert_eq!(include_styles, 0);
        assert_eq!(attach_transition, 0);
    }

    #[test]
    fn payload_nonxy_emit_plan_density_sample_always_with_styles() {
        let mut tier_direct = -1;
        let mut n_marks = 0;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        assert_eq!(
            payload_nonxy_emit_plan(
                PAYLOAD_NONXY_KIND_DENSITY_SAMPLE,
                200,
                0,
                0,
                1,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
            ),
            1
        );
        assert_eq!(n_marks, 200);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LINEAR);
        assert_eq!(y_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG);
        assert_eq!(slot, PAYLOAD_SHIP_CHANNELS_ALWAYS);
        assert_eq!(include_styles, 1);
        assert_eq!(attach_transition, 0);
    }

    #[test]
    fn payload_nonxy_emit_plan_rejects_unknown_kind() {
        let mut tier_direct = 0;
        let mut n_marks = 0;
        let mut apply_palette = 0;
        let mut x_scale = 0;
        let mut y_scale = 0;
        let mut slot = 0;
        let mut include_styles = 0;
        let mut attach_transition = 0;
        assert_eq!(
            payload_nonxy_emit_plan(
                99,
                1,
                0,
                0,
                0,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
            ),
            0
        );
    }

    #[test]
    fn payload_bar_hist_emit_plan_histogram_matches_rect() {
        let mut emit_bar = -1;
        let mut tier_direct = -1;
        let mut n_marks = 0;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut pos_scale = -1;
        let mut value_scale = -1;
        let mut value_axis = -1;
        let mut slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        assert_eq!(
            payload_bar_hist_emit_plan(
                PAYLOAD_BAR_HIST_KIND_HISTOGRAM,
                1,
                5,
                1,
                1,
                0,
                PAYLOAD_BAR_ORIENTATION_VERTICAL,
                &mut emit_bar,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut pos_scale,
                &mut value_scale,
                &mut value_axis,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
            ),
            1
        );
        assert_eq!(emit_bar, 0);
        assert_eq!(tier_direct, 1);
        assert_eq!(n_marks, 5);
        assert_eq!(apply_palette, 1);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG);
        assert_eq!(y_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LINEAR);
        assert_eq!(slot, PAYLOAD_SHIP_CHANNELS_IF_COLOR);
        assert_eq!(include_styles, 1);
        assert_eq!(attach_transition, 1);
    }

    #[test]
    fn payload_bar_hist_emit_plan_bar_compact_vertical() {
        let mut emit_bar = -1;
        let mut tier_direct = -1;
        let mut n_marks = 0;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut pos_scale = -1;
        let mut value_scale = -1;
        let mut value_axis = -1;
        let mut slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        assert_eq!(
            payload_bar_hist_emit_plan(
                PAYLOAD_BAR_HIST_KIND_BAR_COMPACT,
                1,
                8,
                0,
                0,
                1,
                PAYLOAD_BAR_ORIENTATION_VERTICAL,
                &mut emit_bar,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut pos_scale,
                &mut value_scale,
                &mut value_axis,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
            ),
            1
        );
        assert_eq!(emit_bar, 1);
        assert_eq!(n_marks, 8);
        assert_eq!(pos_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LINEAR);
        assert_eq!(value_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG);
        assert_eq!(value_axis, PAYLOAD_VALUE_AXIS_Y);
    }

    #[test]
    fn payload_bar_hist_emit_plan_bar_compact_horizontal() {
        let mut emit_bar = -1;
        let mut tier_direct = -1;
        let mut n_marks = 0;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut pos_scale = -1;
        let mut value_scale = -1;
        let mut value_axis = -1;
        let mut slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        assert_eq!(
            payload_bar_hist_emit_plan(
                PAYLOAD_BAR_HIST_KIND_BAR_COMPACT,
                1,
                3,
                0,
                2,
                2,
                PAYLOAD_BAR_ORIENTATION_HORIZONTAL,
                &mut emit_bar,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut pos_scale,
                &mut value_scale,
                &mut value_axis,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
            ),
            1
        );
        assert_eq!(emit_bar, 1);
        assert_eq!(pos_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_SYMLOG);
        assert_eq!(value_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_SYMLOG);
        assert_eq!(value_axis, PAYLOAD_VALUE_AXIS_X);
    }

    #[test]
    fn payload_bar_hist_emit_plan_bar_compact_rect_fallback() {
        let mut emit_bar = -1;
        let mut tier_direct = -1;
        let mut n_marks = 0;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut pos_scale = -1;
        let mut value_scale = -1;
        let mut value_axis = -1;
        let mut slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        assert_eq!(
            payload_bar_hist_emit_plan(
                PAYLOAD_BAR_HIST_KIND_BAR_COMPACT,
                0,
                4,
                1,
                0,
                0,
                PAYLOAD_BAR_ORIENTATION_VERTICAL,
                &mut emit_bar,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut pos_scale,
                &mut value_scale,
                &mut value_axis,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
            ),
            1
        );
        assert_eq!(emit_bar, 0);
        assert_eq!(n_marks, 4);
        assert_eq!(attach_transition, 1);
    }

    #[test]
    fn payload_bar_hist_emit_plan_rejects_unknown_kind_and_orientation() {
        let mut emit_bar = 0;
        let mut tier_direct = 0;
        let mut n_marks = 0;
        let mut apply_palette = 0;
        let mut x_scale = 0;
        let mut y_scale = 0;
        let mut pos_scale = 0;
        let mut value_scale = 0;
        let mut value_axis = 0;
        let mut slot = 0;
        let mut include_styles = 0;
        let mut attach_transition = 0;
        assert_eq!(
            payload_bar_hist_emit_plan(
                9,
                1,
                1,
                0,
                0,
                0,
                PAYLOAD_BAR_ORIENTATION_VERTICAL,
                &mut emit_bar,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut pos_scale,
                &mut value_scale,
                &mut value_axis,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
            ),
            0
        );
        assert_eq!(
            payload_bar_hist_emit_plan(
                PAYLOAD_BAR_HIST_KIND_BAR_COMPACT,
                1,
                1,
                0,
                0,
                0,
                9,
                &mut emit_bar,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut pos_scale,
                &mut value_scale,
                &mut value_axis,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
            ),
            0
        );
    }

    #[test]
    fn payload_heatmap_emit_plan_rgba_path() {
        let mut path = -1;
        let mut tier_direct = -1;
        let mut n_marks = 0;
        let mut attach_color = -1;
        let mut borrow_canonical = -1;
        let mut attach_encoding = -1;
        let mut use_fallback = -1;
        assert_eq!(
            payload_heatmap_emit_plan(
                1,
                10,
                20,
                1,
                1,
                &mut path,
                &mut tier_direct,
                &mut n_marks,
                &mut attach_color,
                &mut borrow_canonical,
                &mut attach_encoding,
                &mut use_fallback,
            ),
            1
        );
        assert_eq!(path, PAYLOAD_HEATMAP_PATH_RGBA);
        assert_eq!(tier_direct, 1);
        assert_eq!(n_marks, 200);
        assert_eq!(attach_color, 0);
        assert_eq!(borrow_canonical, 0);
        assert_eq!(attach_encoding, 0);
        assert_eq!(use_fallback, 0);
    }

    #[test]
    fn payload_heatmap_emit_plan_grid_borrow() {
        let mut path = -1;
        let mut tier_direct = -1;
        let mut n_marks = 0;
        let mut attach_color = -1;
        let mut borrow_canonical = -1;
        let mut attach_encoding = -1;
        let mut use_fallback = -1;
        assert_eq!(
            payload_heatmap_emit_plan(
                0,
                4,
                5,
                0,
                1,
                &mut path,
                &mut tier_direct,
                &mut n_marks,
                &mut attach_color,
                &mut borrow_canonical,
                &mut attach_encoding,
                &mut use_fallback,
            ),
            1
        );
        assert_eq!(path, PAYLOAD_HEATMAP_PATH_GRID);
        assert_eq!(n_marks, 20);
        assert_eq!(attach_color, 1);
        assert_eq!(borrow_canonical, 1);
        assert_eq!(attach_encoding, 1);
        assert_eq!(use_fallback, 0);
    }

    #[test]
    fn payload_heatmap_emit_plan_grid_constant_colormap() {
        let mut path = -1;
        let mut tier_direct = -1;
        let mut n_marks = 0;
        let mut attach_color = -1;
        let mut borrow_canonical = -1;
        let mut attach_encoding = -1;
        let mut use_fallback = -1;
        assert_eq!(
            payload_heatmap_emit_plan(
                0,
                2,
                3,
                1,
                0,
                &mut path,
                &mut tier_direct,
                &mut n_marks,
                &mut attach_color,
                &mut borrow_canonical,
                &mut attach_encoding,
                &mut use_fallback,
            ),
            1
        );
        assert_eq!(path, PAYLOAD_HEATMAP_PATH_GRID);
        assert_eq!(borrow_canonical, 0);
        assert_eq!(attach_encoding, 0);
        assert_eq!(use_fallback, 1);
    }

    #[test]
    fn payload_mesh_emit_plan_gather_and_transition() {
        let mut tier_direct = -1;
        let mut n_marks = 0;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        let mut attempt_gather = -1;
        let mut gather_color = -1;
        assert_eq!(
            payload_mesh_emit_plan(
                12,
                1,
                1,
                0,
                1,
                1,
                0,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
                &mut attempt_gather,
                &mut gather_color,
            ),
            1
        );
        assert_eq!(tier_direct, 1);
        assert_eq!(n_marks, 12);
        assert_eq!(apply_palette, 1);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG);
        assert_eq!(y_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LINEAR);
        assert_eq!(slot, PAYLOAD_SHIP_CHANNELS_IF_COLOR);
        assert_eq!(include_styles, 1);
        assert_eq!(attach_transition, 1);
        assert_eq!(attempt_gather, 1);
        assert_eq!(gather_color, 1);
    }

    #[test]
    fn payload_mesh_emit_plan_no_gather_without_nulls_or_color() {
        let mut tier_direct = 0;
        let mut n_marks = 0;
        let mut apply_palette = 0;
        let mut x_scale = 0;
        let mut y_scale = 0;
        let mut slot = 0;
        let mut include_styles = 0;
        let mut attach_transition = 0;
        let mut attempt_gather = 0;
        let mut gather_color = 0;
        assert_eq!(
            payload_mesh_emit_plan(
                5,
                0,
                0,
                0,
                0,
                0,
                0,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
                &mut attempt_gather,
                &mut gather_color,
            ),
            1
        );
        assert_eq!(attempt_gather, 0);
        assert_eq!(gather_color, 0);
        assert_eq!(apply_palette, 0);
    }

    #[test]
    fn payload_mesh_emit_plan_rejects_missing_continuous_color_values() {
        let mut tier_direct = 0;
        let mut n_marks = 0;
        let mut apply_palette = 0;
        let mut x_scale = 0;
        let mut y_scale = 0;
        let mut slot = 0;
        let mut include_styles = 0;
        let mut attach_transition = 0;
        let mut attempt_gather = 0;
        let mut gather_color = 0;
        assert_eq!(
            payload_mesh_emit_plan(
                1,
                0,
                0,
                0,
                0,
                1,
                1,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
                &mut attempt_gather,
                &mut gather_color,
            ),
            0
        );
    }

    #[test]
    fn payload_ribbon_emit_plan_gather_transition_and_color2() {
        let mut tier_direct = -1;
        let mut n_marks = 0;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        let mut attempt_gather = -1;
        let mut attach_color2 = -1;
        assert_eq!(
            payload_ribbon_emit_plan(
                8,
                1,
                1,
                0,
                1,
                1,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
                &mut attempt_gather,
                &mut attach_color2,
            ),
            1
        );
        assert_eq!(tier_direct, 1);
        assert_eq!(n_marks, 8);
        assert_eq!(apply_palette, 1);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG);
        assert_eq!(y_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LINEAR);
        assert_eq!(slot, PAYLOAD_SHIP_CHANNELS_IF_COLOR);
        assert_eq!(include_styles, 1);
        assert_eq!(attach_transition, 1);
        assert_eq!(attempt_gather, 1);
        assert_eq!(attach_color2, 1);
    }

    #[test]
    fn payload_ribbon_emit_plan_no_gather_without_nulls() {
        let mut tier_direct = 0;
        let mut n_marks = 0;
        let mut apply_palette = 0;
        let mut x_scale = 0;
        let mut y_scale = 0;
        let mut slot = 0;
        let mut include_styles = 0;
        let mut attach_transition = 0;
        let mut attempt_gather = 0;
        let mut attach_color2 = 0;
        assert_eq!(
            payload_ribbon_emit_plan(
                3,
                0,
                0,
                0,
                0,
                0,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut slot,
                &mut include_styles,
                &mut attach_transition,
                &mut attempt_gather,
                &mut attach_color2,
            ),
            1
        );
        assert_eq!(attempt_gather, 0);
        assert_eq!(attach_color2, 0);
        assert_eq!(apply_palette, 0);
    }

    #[test]
    fn payload_segments_emit_plan_errorbar_role_keys_and_gather() {
        let mut n_marks = 0usize;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut channel_slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        let mut attempt_gather = -1;
        let mut attempt_role_keys = -1;
        assert_eq!(
            payload_segments_emit_plan(
                "errorbar",
                33,
                1,
                1,
                0,
                1,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut channel_slot,
                &mut include_styles,
                &mut attach_transition,
                &mut attempt_gather,
                &mut attempt_role_keys,
            ),
            1
        );
        assert_eq!(n_marks, 33);
        assert_eq!(apply_palette, 1);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG);
        assert_eq!(y_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LINEAR);
        assert_eq!(channel_slot, PAYLOAD_SHIP_CHANNELS_IF_COLOR);
        assert_eq!(include_styles, 1);
        assert_eq!(attach_transition, 1);
        assert_eq!(attempt_gather, 1);
        assert_eq!(attempt_role_keys, 1);
    }

    #[test]
    fn payload_segments_emit_plan_stem_no_role_keys_without_transition() {
        let mut n_marks = 0usize;
        let mut apply_palette = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut channel_slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        let mut attempt_gather = -1;
        let mut attempt_role_keys = -1;
        assert_eq!(
            payload_segments_emit_plan(
                "stem",
                3000,
                0,
                0,
                2,
                0,
                &mut n_marks,
                &mut apply_palette,
                &mut x_scale,
                &mut y_scale,
                &mut channel_slot,
                &mut include_styles,
                &mut attach_transition,
                &mut attempt_gather,
                &mut attempt_role_keys,
            ),
            1
        );
        assert_eq!(n_marks, 3000);
        assert_eq!(apply_palette, 0);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LINEAR);
        assert_eq!(y_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_SYMLOG);
        assert_eq!(attempt_gather, 1);
        assert_eq!(attempt_role_keys, 0);
    }

    #[test]
    fn payload_scatter_emit_plan_density_tier_routing() {
        use crate::lod_plan::SCATTER_DENSITY_THRESHOLD;

        let mut emit_density = -1;
        let mut clear_sel = -1;
        let mut drill_false = -1;
        let mut set_sel = -1;
        let mut tier_direct = -1;
        let mut n_marks = 0usize;
        let mut apply_palette = -1;
        let mut attach_anim = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut channel_slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        let mut attach_tooltip = -1;
        let mut filter_tooltip = -1;
        let mut tooltip_ok = -1;
        assert_eq!(
            payload_scatter_emit_plan(
                SCATTER_DENSITY_THRESHOLD + 1,
                0,
                -1,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                &mut emit_density,
                &mut clear_sel,
                &mut drill_false,
                &mut set_sel,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut attach_anim,
                &mut x_scale,
                &mut y_scale,
                &mut channel_slot,
                &mut include_styles,
                &mut attach_transition,
                &mut attach_tooltip,
                &mut filter_tooltip,
                &mut tooltip_ok,
            ),
            1
        );
        assert_eq!(emit_density, 1);
        assert_eq!(clear_sel, 1);
        assert_eq!(drill_false, 1);
        assert_eq!(attach_transition, 1);
        assert_eq!(set_sel, 0);
    }

    #[test]
    fn payload_scatter_emit_plan_direct_channels_and_tooltip() {
        let mut emit_density = -1;
        let mut clear_sel = -1;
        let mut drill_false = -1;
        let mut set_sel = -1;
        let mut tier_direct = -1;
        let mut n_marks = 0usize;
        let mut apply_palette = -1;
        let mut attach_anim = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut channel_slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        let mut attach_tooltip = -1;
        let mut filter_tooltip = -1;
        let mut tooltip_ok = -1;
        assert_eq!(
            payload_scatter_emit_plan(
                100,
                0,
                -1,
                0,
                0,
                50,
                1,
                1,
                0,
                1,
                1,
                100,
                &mut emit_density,
                &mut clear_sel,
                &mut drill_false,
                &mut set_sel,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut attach_anim,
                &mut x_scale,
                &mut y_scale,
                &mut channel_slot,
                &mut include_styles,
                &mut attach_transition,
                &mut attach_tooltip,
                &mut filter_tooltip,
                &mut tooltip_ok,
            ),
            1
        );
        assert_eq!(emit_density, 0);
        assert_eq!(set_sel, 1);
        assert_eq!(tier_direct, 1);
        assert_eq!(n_marks, 50);
        assert_eq!(apply_palette, 0);
        assert_eq!(attach_anim, 1);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG);
        assert_eq!(channel_slot, PAYLOAD_SHIP_CHANNELS_ALWAYS);
        assert_eq!(include_styles, 1);
        assert_eq!(attach_transition, 1);
        assert_eq!(attach_tooltip, 1);
        assert_eq!(filter_tooltip, 0);
        assert_eq!(tooltip_ok, 1);
    }

    #[test]
    fn payload_scatter_emit_plan_force_density_false_overrides_threshold() {
        let mut emit_density = -1;
        let mut clear_sel = -1;
        let mut drill_false = -1;
        let mut set_sel = -1;
        let mut tier_direct = -1;
        let mut n_marks = 0usize;
        let mut apply_palette = -1;
        let mut attach_anim = -1;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut channel_slot = -1;
        let mut include_styles = -1;
        let mut attach_transition = -1;
        let mut attach_tooltip = -1;
        let mut filter_tooltip = -1;
        let mut tooltip_ok = -1;
        assert_eq!(
            payload_scatter_emit_plan(
                1_000_000,
                0,
                0,
                0,
                0,
                100,
                0,
                0,
                0,
                0,
                0,
                0,
                &mut emit_density,
                &mut clear_sel,
                &mut drill_false,
                &mut set_sel,
                &mut tier_direct,
                &mut n_marks,
                &mut apply_palette,
                &mut attach_anim,
                &mut x_scale,
                &mut y_scale,
                &mut channel_slot,
                &mut include_styles,
                &mut attach_transition,
                &mut attach_tooltip,
                &mut filter_tooltip,
                &mut tooltip_ok,
            ),
            1
        );
        assert_eq!(emit_density, 0);
        assert_eq!(set_sel, 1);
    }

    #[test]
    fn payload_density_trace_emit_plan_identity_grid_and_wire() {
        use crate::density_emit::{
            DENSITY_COLOR_MODE_OTHER, DENSITY_GRID_PATH_IDENTITY_STRATIFIED_FUSED,
        };

        let mut color_mode = -1;
        let mut categorical = -1;
        let mut compact = -1;
        let mut stratified = -1;
        let mut x_c0 = 0.0;
        let mut x_c1 = 0.0;
        let mut y_c0 = 0.0;
        let mut y_c1 = 0.0;
        let mut grid_path = -1;
        let mut pyramid_eligible = -1;
        let mut pyramid_attempt = -1;
        let mut pyramid_no_rescan = -1;
        let mut pyramid_max_upsample = 0u32;
        let mut pyramid_tile_upsample = 0u32;
        let mut wasm_eligible = -1;
        let mut needs_pyramid_sample = -1;
        let mut overlay_omitted = 0u32;
        let mut visible_is_n_points = -1;
        let mut use_raw_range_bin2d = -1;
        let mut attach_transition = -1;
        let mut n_marks = 0usize;
        let mut visible_init = -1;
        let mut attach_sample = -1;
        let mut pyramid_sample_stratified = -1;
        let mut use_channel_colormap = -1;
        let mut ship_wasm = -1;
        let mut ship_mean_rgba = -1;
        let mut ship_constant = -1;
        let mut ship_categorical = -1;
        let mut mean_color_aggregates = -1;
        let mut overlay_static = -1;
        let mut overlay_rows = -1;
        let mut channels_dropped = -1;
        assert_eq!(
            payload_density_trace_emit_plan(
                1,
                "categorical",
                1,
                1,
                1,
                0,
                1,
                1,
                1,
                0,
                0,
                1,
                0,
                512,
                512,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0.0,
                1.0,
                0.0,
                1.0,
                0.0,
                1.0,
                0.0,
                1.0,
                0.0,
                1.0,
                0.0,
                1.0,
                10_000,
                0,
                0,
                2,
                &mut color_mode,
                &mut categorical,
                &mut compact,
                &mut stratified,
                &mut x_c0,
                &mut x_c1,
                &mut y_c0,
                &mut y_c1,
                &mut grid_path,
                &mut pyramid_eligible,
                &mut pyramid_attempt,
                &mut pyramid_no_rescan,
                &mut pyramid_max_upsample,
                &mut pyramid_tile_upsample,
                &mut wasm_eligible,
                &mut needs_pyramid_sample,
                &mut overlay_omitted,
                &mut visible_is_n_points,
                &mut use_raw_range_bin2d,
                &mut attach_transition,
                &mut n_marks,
                &mut visible_init,
                &mut attach_sample,
                &mut pyramid_sample_stratified,
                &mut use_channel_colormap,
                &mut ship_wasm,
                &mut ship_mean_rgba,
                &mut ship_constant,
                &mut ship_categorical,
                &mut mean_color_aggregates,
                &mut overlay_static,
                &mut overlay_rows,
                &mut channels_dropped,
            ),
            1
        );
        assert_eq!(color_mode, DENSITY_COLOR_MODE_OTHER);
        assert_eq!(categorical, 1);
        assert_eq!(grid_path, DENSITY_GRID_PATH_IDENTITY_STRATIFIED_FUSED);
        assert_eq!(n_marks, 512 * 512);
        assert_eq!(attach_transition, 1);
        assert_eq!(visible_init, 1);
        assert_eq!(attach_sample, 1);
        assert_eq!(ship_categorical, 1);
        assert_eq!(use_channel_colormap, 0);
        assert_eq!(channels_dropped, 1);
    }

    #[test]
    fn payload_build_plan_always_attaches_show_legend_and_optional_sections() {
        let mut attach_show_legend = 0;
        let mut wasm_kind = -1;
        let mut attach_wasm = -1;
        let mut attach_title = -1;
        let mut attach_coords = -1;
        let mut attach_palette = -1;
        let mut attach_legend = -1;
        let mut resolve_best = -1;
        let mut attach_extra = -1;
        let mut attach_frame = -1;
        let mut attach_colorbar = -1;
        let mut attach_modebar = -1;
        let mut attach_export = -1;
        let mut attach_tooltip_flag = -1;
        let mut attach_padding = -1;
        let mut attach_dom = -1;
        let mut attach_tooltip = -1;
        let mut attach_mark = -1;
        let mut attach_interaction = -1;
        let mut attach_annotations = -1;
        let mut attach_animation = -1;
        let mut attach_graph = -1;
        assert_eq!(
            payload_build_plan(
                0,
                0,
                0,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                &mut attach_show_legend,
                &mut wasm_kind,
                &mut attach_wasm,
                &mut attach_title,
                &mut attach_coords,
                &mut attach_palette,
                &mut attach_legend,
                &mut resolve_best,
                &mut attach_extra,
                &mut attach_frame,
                &mut attach_colorbar,
                &mut attach_modebar,
                &mut attach_export,
                &mut attach_tooltip_flag,
                &mut attach_padding,
                &mut attach_dom,
                &mut attach_tooltip,
                &mut attach_mark,
                &mut attach_interaction,
                &mut attach_annotations,
                &mut attach_animation,
                &mut attach_graph,
            ),
            1
        );
        assert_eq!(attach_show_legend, 1);
        assert_eq!(wasm_kind, DENSITY_WASM_DENSITY_NONE);
        assert_eq!(attach_wasm, 0);
        assert_eq!(attach_title, 1);
        assert_eq!(attach_coords, 0);
        assert_eq!(attach_palette, 1);
        assert_eq!(attach_legend, 1);
        assert_eq!(resolve_best, 1);
        assert_eq!(attach_extra, 1);
        assert_eq!(attach_frame, 1);
        assert_eq!(attach_colorbar, 1);
        assert_eq!(attach_modebar, 1);
        assert_eq!(attach_export, 1);
        assert_eq!(attach_tooltip_flag, 1);
        assert_eq!(attach_padding, 1);
        assert_eq!(attach_dom, 1);
        assert_eq!(attach_tooltip, 1);
        assert_eq!(attach_mark, 1);
        assert_eq!(attach_interaction, 1);
        assert_eq!(attach_annotations, 1);
        assert_eq!(attach_animation, 1);
        assert_eq!(attach_graph, 1);
    }

    fn run_payload_build_plan(
        scratch: &mut PayloadBuildPlanScratch,
        split_payload: i32,
        wasm_source_count: u64,
        has_density_tier: i32,
        coords_cartesian: i32,
        has_title_options: i32,
        has_palette: i32,
        has_legend_options: i32,
        legend_loc_best: i32,
        has_extra_legends: i32,
        has_frame_sides: i32,
        has_colorbar_options: i32,
        show_modebar_is_false: i32,
        has_export_options: i32,
        show_tooltip_is_false: i32,
        has_padding: i32,
        has_dom: i32,
        has_tooltip: i32,
        has_mark_style: i32,
        has_interaction: i32,
        has_annotations: i32,
        has_animation_options: i32,
        has_graph_meta: i32,
    ) -> i32 {
        payload_build_plan(
            split_payload,
            wasm_source_count,
            has_density_tier,
            coords_cartesian,
            has_title_options,
            has_palette,
            has_legend_options,
            legend_loc_best,
            has_extra_legends,
            has_frame_sides,
            has_colorbar_options,
            show_modebar_is_false,
            has_export_options,
            show_tooltip_is_false,
            has_padding,
            has_dom,
            has_tooltip,
            has_mark_style,
            has_interaction,
            has_annotations,
            has_animation_options,
            has_graph_meta,
            &mut scratch.attach_show_legend,
            &mut scratch.wasm_kind,
            &mut scratch.attach_wasm,
            &mut scratch.attach_title,
            &mut scratch.attach_coords,
            &mut scratch.attach_palette,
            &mut scratch.attach_legend,
            &mut scratch.resolve_best,
            &mut scratch.attach_extra,
            &mut scratch.attach_frame,
            &mut scratch.attach_colorbar,
            &mut scratch.attach_modebar,
            &mut scratch.attach_export,
            &mut scratch.attach_tooltip_flag,
            &mut scratch.attach_padding,
            &mut scratch.attach_dom,
            &mut scratch.attach_tooltip,
            &mut scratch.attach_mark,
            &mut scratch.attach_interaction,
            &mut scratch.attach_annotations,
            &mut scratch.attach_animation,
            &mut scratch.attach_graph,
        )
    }

    #[test]
    fn payload_build_plan_wasm_density_split_automatic_and_unsupported() {
        let mut outs = payload_build_plan_scratch();
        assert_eq!(
            run_payload_build_plan(&mut outs, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            1
        );
        assert_eq!(outs.wasm_kind, crate::density_emit::DENSITY_WASM_DENSITY_AUTOMATIC);
        assert_eq!(outs.attach_wasm, 1);

        outs = payload_build_plan_scratch();
        assert_eq!(
            run_payload_build_plan(&mut outs, 1, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            1
        );
        assert_eq!(outs.wasm_kind, crate::density_emit::DENSITY_WASM_DENSITY_UNSUPPORTED);
        assert_eq!(outs.attach_wasm, 1);
    }

    struct PayloadBuildPlanScratch {
        attach_show_legend: i32,
        wasm_kind: i32,
        attach_wasm: i32,
        attach_title: i32,
        attach_coords: i32,
        attach_palette: i32,
        attach_legend: i32,
        resolve_best: i32,
        attach_extra: i32,
        attach_frame: i32,
        attach_colorbar: i32,
        attach_modebar: i32,
        attach_export: i32,
        attach_tooltip_flag: i32,
        attach_padding: i32,
        attach_dom: i32,
        attach_tooltip: i32,
        attach_mark: i32,
        attach_interaction: i32,
        attach_annotations: i32,
        attach_animation: i32,
        attach_graph: i32,
    }

    impl PayloadBuildPlanScratch {
        fn new() -> Self {
            Self {
                attach_show_legend: 0,
                wasm_kind: 0,
                attach_wasm: 0,
                attach_title: 0,
                attach_coords: 0,
                attach_palette: 0,
                attach_legend: 0,
                resolve_best: 0,
                attach_extra: 0,
                attach_frame: 0,
                attach_colorbar: 0,
                attach_modebar: 0,
                attach_export: 0,
                attach_tooltip_flag: 0,
                attach_padding: 0,
                attach_dom: 0,
                attach_tooltip: 0,
                attach_mark: 0,
                attach_interaction: 0,
                attach_annotations: 0,
                attach_animation: 0,
                attach_graph: 0,
            }
        }
    }

    fn payload_build_plan_scratch() -> PayloadBuildPlanScratch {
        PayloadBuildPlanScratch::new()
    }

    fn run_axis_spec_attach_plan(coords_cartesian: i32, axis_is_x: i32) -> AxisSpecAttachPlanOut {
        let mut out = AxisSpecAttachPlanOut {
            attach_id: 0,
            attach_kind: 0,
            attach_side: 0,
            attach_label: 0,
            attach_range: 0,
            attach_scale: 0,
            attach_ticks: 0,
            attach_tick_sides: 0,
            attach_tick_label_sides: 0,
            attach_label_position: 0,
            attach_label_offset: 0,
            attach_label_angle: 0,
            attach_tick_label_angle: 0,
            attach_tick_label_strategy: 0,
            attach_tick_label_anchor: 0,
            attach_tick_label_min_gap: 0,
            attach_constant: 0,
            attach_nonpositive: 0,
            attach_reverse: 0,
            attach_domain: 0,
            attach_bounds: 0,
            attach_minor_style: 0,
            attach_format: 0,
            attach_style: 0,
            attach_categories: 0,
            attach_theta_unit: 0,
            attach_theta_zero: 0,
            attach_theta_direction: 0,
            attach_sector: 0,
            attach_grid_shape: 0,
            attach_hole: 0,
            attach_r_origin: 0,
        };
        assert_eq!(
            payload_axis_spec_attach_plan(
                coords_cartesian,
                axis_is_x,
                &mut out.attach_id,
                &mut out.attach_kind,
                &mut out.attach_side,
                &mut out.attach_label,
                &mut out.attach_range,
                &mut out.attach_scale,
                &mut out.attach_ticks,
                &mut out.attach_tick_sides,
                &mut out.attach_tick_label_sides,
                &mut out.attach_label_position,
                &mut out.attach_label_offset,
                &mut out.attach_label_angle,
                &mut out.attach_tick_label_angle,
                &mut out.attach_tick_label_strategy,
                &mut out.attach_tick_label_anchor,
                &mut out.attach_tick_label_min_gap,
                &mut out.attach_constant,
                &mut out.attach_nonpositive,
                &mut out.attach_reverse,
                &mut out.attach_domain,
                &mut out.attach_bounds,
                &mut out.attach_minor_style,
                &mut out.attach_format,
                &mut out.attach_style,
                &mut out.attach_categories,
                &mut out.attach_theta_unit,
                &mut out.attach_theta_zero,
                &mut out.attach_theta_direction,
                &mut out.attach_sector,
                &mut out.attach_grid_shape,
                &mut out.attach_hole,
                &mut out.attach_r_origin,
            ),
            1
        );
        out
    }

    #[test]
    fn payload_axis_spec_attach_plan_cartesian_core_and_no_polar() {
        let plan = run_axis_spec_attach_plan(1, 1);
        assert_eq!(plan.attach_id, 1);
        assert_eq!(plan.attach_kind, 1);
        assert_eq!(plan.attach_side, 1);
        assert_eq!(plan.attach_label, 1);
        assert_eq!(plan.attach_range, 1);
        assert_eq!(plan.attach_scale, 1);
        assert_eq!(plan.attach_ticks, 1);
        assert_eq!(plan.attach_domain, 1);
        assert_eq!(plan.attach_format, 1);
        assert_eq!(plan.attach_bounds, 1);
        assert_eq!(plan.attach_theta_unit, 0);
        assert_eq!(plan.attach_hole, 0);
        assert_eq!(plan.attach_r_origin, 0);
    }

    #[test]
    fn payload_axis_spec_attach_plan_polar_theta_on_x_only() {
        let x = run_axis_spec_attach_plan(0, 1);
        assert_eq!(x.attach_theta_unit, 1);
        assert_eq!(x.attach_theta_zero, 1);
        assert_eq!(x.attach_theta_direction, 1);
        assert_eq!(x.attach_sector, 1);
        assert_eq!(x.attach_grid_shape, 1);
        assert_eq!(x.attach_hole, 0);
        assert_eq!(x.attach_r_origin, 0);
        let y = run_axis_spec_attach_plan(0, 0);
        assert_eq!(y.attach_theta_unit, 0);
        assert_eq!(y.attach_hole, 1);
        assert_eq!(y.attach_r_origin, 1);
    }

    fn run_column_ship_plan(kind: &str, orientation: i32) -> (
        i32,
        i32,
        usize,
        i32,
        i32,
        [PayloadColumnShipEntry; PAYLOAD_COLUMN_SHIP_MAX],
    ) {
        let mut gather_policy = -1;
        let mut gather_include_color = -1;
        let mut n_columns = 0usize;
        let mut x_scale = -1;
        let mut y_scale = -1;
        let mut columns = [PayloadColumnShipEntry {
            registry_key: -1,
            trace_slot: -1,
            ship_method: -1,
            ship_scale: -1,
            gather: -1,
        }; PAYLOAD_COLUMN_SHIP_MAX];
        let ok = payload_column_ship_plan(
            kind,
            1,
            2,
            orientation,
            &mut gather_policy,
            &mut gather_include_color,
            &mut n_columns,
            &mut x_scale,
            &mut y_scale,
            &mut columns,
        );
        assert_eq!(ok, 1);
        (gather_policy, gather_include_color, n_columns, x_scale, y_scale, columns)
    }

    #[test]
    fn payload_column_ship_plan_bar_compact_vertical() {
        let (gather, _, n, _, _, cols) =
            run_column_ship_plan("bar_compact", PAYLOAD_BAR_ORIENTATION_VERTICAL);
        assert_eq!(gather, PAYLOAD_GATHER_RECT_FINITE);
        assert_eq!(n, 3);
        assert_eq!(cols[0].registry_key, PAYLOAD_COL_KEY_POS);
        assert_eq!(cols[0].trace_slot, PAYLOAD_TRACE_SLOT_X);
        assert_eq!(cols[1].registry_key, PAYLOAD_COL_KEY_VALUE1);
        assert_eq!(cols[2].registry_key, PAYLOAD_COL_KEY_VALUE0);
        assert_eq!(cols[2].trace_slot, PAYLOAD_TRACE_SLOT_Y0);
    }

    #[test]
    fn payload_column_ship_plan_bar_compact_horizontal() {
        let (_, _, n, _, _, cols) =
            run_column_ship_plan("bar_compact", PAYLOAD_BAR_ORIENTATION_HORIZONTAL);
        assert_eq!(n, 3);
        assert_eq!(cols[0].registry_key, PAYLOAD_COL_KEY_POS);
        assert_eq!(cols[0].ship_method, PAYLOAD_COL_SHIP_VALUES);
        assert_eq!(cols[1].registry_key, PAYLOAD_COL_KEY_VALUE1);
        assert_eq!(cols[1].trace_slot, PAYLOAD_TRACE_SLOT_X1);
        assert_eq!(cols[2].registry_key, PAYLOAD_COL_KEY_VALUE0);
        assert_eq!(cols[2].trace_slot, PAYLOAD_TRACE_SLOT_X0);
    }

    #[test]
    fn payload_column_ship_plan_rect_registry_and_finite_gather() {
        let (gather, _, n, x_scale, y_scale, cols) =
            run_column_ship_plan("rect", PAYLOAD_BAR_ORIENTATION_VERTICAL);
        assert_eq!(gather, PAYLOAD_GATHER_RECT_FINITE);
        assert_eq!(n, 4);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG);
        assert_eq!(y_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_SYMLOG);
        assert_eq!(cols[0].registry_key, PAYLOAD_COL_KEY_X0);
        assert_eq!(cols[3].registry_key, PAYLOAD_COL_KEY_Y1);
        assert!(cols.iter().take(4).all(|c| c.ship_method == PAYLOAD_COL_SHIP_OFFSET));
    }

    #[test]
    fn payload_column_ship_plan_hexbin_values_and_visible_gather() {
        let (gather, _, n, _, _, cols) =
            run_column_ship_plan("hexbin", PAYLOAD_BAR_ORIENTATION_VERTICAL);
        assert_eq!(gather, PAYLOAD_GATHER_VISIBLE_SEL);
        assert_eq!(n, 2);
        assert_eq!(cols[0].ship_method, PAYLOAD_COL_SHIP_VALUES);
        assert_eq!(cols[1].ship_method, PAYLOAD_COL_SHIP_VALUES);
    }

    #[test]
    fn payload_column_ship_plan_density_sample_values_no_gather() {
        let (gather, _, n, _, _, cols) =
            run_column_ship_plan("density_sample", PAYLOAD_BAR_ORIENTATION_VERTICAL);
        assert_eq!(gather, PAYLOAD_GATHER_NONE);
        assert_eq!(n, 2);
        assert_eq!(cols[0].registry_key, PAYLOAD_COL_KEY_X);
        assert_eq!(cols[0].ship_method, PAYLOAD_COL_SHIP_VALUES);
        assert_eq!(cols[0].gather, 0);
        assert_eq!(cols[1].registry_key, PAYLOAD_COL_KEY_Y);
        assert_eq!(cols[1].ship_method, PAYLOAD_COL_SHIP_VALUES);
        assert_eq!(cols[1].gather, 0);
    }

    #[test]
    fn payload_column_ship_plan_density_wasm_source_f64_no_gather() {
        let (gather, _, n, x_scale, y_scale, cols) =
            run_column_ship_plan("density_wasm_source", PAYLOAD_BAR_ORIENTATION_VERTICAL);
        assert_eq!(gather, PAYLOAD_GATHER_NONE);
        assert_eq!(n, 2);
        assert_eq!(x_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_LOG);
        assert_eq!(y_scale, PAYLOAD_BASE_ENTRY_SHIP_SCALE_SYMLOG);
        assert_eq!(cols[0].registry_key, PAYLOAD_COL_KEY_X);
        assert_eq!(cols[0].trace_slot, PAYLOAD_TRACE_SLOT_X);
        assert_eq!(cols[0].ship_method, PAYLOAD_COL_SHIP_F64);
        assert_eq!(cols[0].gather, 0);
        assert_eq!(cols[1].ship_method, PAYLOAD_COL_SHIP_F64);
    }

    #[test]
    fn payload_column_ship_plan_ribbon_six_columns_with_targets() {
        let (gather, _, n, _, _y_scale, cols) =
            run_column_ship_plan("ribbon", PAYLOAD_BAR_ORIENTATION_VERTICAL);
        assert_eq!(gather, PAYLOAD_GATHER_VALID_INDICES);
        assert_eq!(n, 6);
        assert_eq!(cols[4].registry_key, PAYLOAD_COL_KEY_TARGET_Y0);
        assert_eq!(cols[4].trace_slot, PAYLOAD_TRACE_SLOT_X);
        assert_eq!(cols[4].ship_scale, PAYLOAD_COL_SCALE_Y);
        assert_eq!(cols[5].registry_key, PAYLOAD_COL_KEY_TARGET_Y1);
    }

    #[test]
    fn payload_column_ship_plan_area_includes_base_after_m4() {
        let (gather, _, n, _, _, cols) =
            run_column_ship_plan("area", PAYLOAD_BAR_ORIENTATION_VERTICAL);
        assert_eq!(gather, PAYLOAD_GATHER_M4);
        assert_eq!(n, 3);
        assert_eq!(cols[2].registry_key, PAYLOAD_COL_KEY_BASE);
        assert_eq!(cols[2].trace_slot, PAYLOAD_TRACE_SLOT_BASE);
    }

    #[test]
    fn payload_column_ship_plan_rejects_unknown_kind() {
        let mut gather_policy = 0;
        let mut gather_include_color = 0;
        let mut n_columns = 0usize;
        let mut x_scale = 0;
        let mut y_scale = 0;
        let mut columns = [PayloadColumnShipEntry {
            registry_key: 0,
            trace_slot: 0,
            ship_method: 0,
            ship_scale: 0,
            gather: 0,
        }; PAYLOAD_COLUMN_SHIP_MAX];
        assert_eq!(
            payload_column_ship_plan(
                "sankey",
                0,
                0,
                PAYLOAD_BAR_ORIENTATION_VERTICAL,
                &mut gather_policy,
                &mut gather_include_color,
                &mut n_columns,
                &mut x_scale,
                &mut y_scale,
                &mut columns,
            ),
            0
        );
    }

    fn run_density_grid_ship_plan(
        ship_mean_color_rgba: i32,
        ship_wasm_source: i32,
        attach_sample: i32,
        has_tiles: i32,
        ship_constant_color: i32,
        overlay_wire_rows_exceed: i32,
        overlay_wire_static_raster: i32,
        ship_categorical_entry_color: i32,
    ) -> (
        usize,
        [PayloadDensityGridBufferEntry; PAYLOAD_DENSITY_GRID_SHIP_MAX_BUFFERS],
        usize,
        [PayloadDensityGridAttachEntry; PAYLOAD_DENSITY_GRID_SHIP_MAX_ATTACH],
    ) {
        let mut n_buffers = 0usize;
        let mut buffers = [PayloadDensityGridBufferEntry {
            registry_key: -1,
            buffer_slot: -1,
            ship_method: -1,
        }; PAYLOAD_DENSITY_GRID_SHIP_MAX_BUFFERS];
        let mut n_attach = 0usize;
        let mut attach = [PayloadDensityGridAttachEntry { attach_kind: -1 };
            PAYLOAD_DENSITY_GRID_SHIP_MAX_ATTACH];
        let ok = payload_density_grid_ship_plan(
            ship_mean_color_rgba,
            ship_wasm_source,
            attach_sample,
            has_tiles,
            ship_constant_color,
            overlay_wire_rows_exceed,
            overlay_wire_static_raster,
            ship_categorical_entry_color,
            &mut n_buffers,
            &mut buffers,
            &mut n_attach,
            &mut attach,
        );
        assert_eq!(ok, 1);
        (n_buffers, buffers, n_attach, attach)
    }

    #[test]
    fn payload_density_grid_ship_plan_count_only() {
        let (n_buf, bufs, n_attach, steps) = run_density_grid_ship_plan(0, 0, 0, 0, 0, 0, 0, 0);
        assert_eq!(n_buf, 1);
        assert_eq!(bufs[0].registry_key, PAYLOAD_DENSITY_KEY_BUF);
        assert_eq!(bufs[0].buffer_slot, PAYLOAD_DENSITY_SLOT_COUNT);
        assert_eq!(bufs[0].ship_method, PAYLOAD_DENSITY_SHIP_U8);
        assert_eq!(n_attach, 2);
        assert_eq!(
            steps[0].attach_kind,
            PAYLOAD_DENSITY_ATTACH_CHANNELS_DROPPED
        );
        assert_eq!(
            steps[1].attach_kind,
            PAYLOAD_DENSITY_ATTACH_DROPPED_CHANNELS
        );
    }

    #[test]
    fn payload_density_grid_ship_plan_full_identity_overlay() {
        let (n_buf, bufs, n_attach, steps) =
            run_density_grid_ship_plan(1, 1, 1, 1, 1, 0, 0, 1);
        assert_eq!(n_buf, 2);
        assert_eq!(bufs[1].registry_key, PAYLOAD_DENSITY_KEY_RGBA);
        assert_eq!(n_attach, 8);
        assert_eq!(
            steps[0].attach_kind,
            PAYLOAD_DENSITY_ATTACH_WASM_SOURCE
        );
        assert_eq!(steps[1].attach_kind, PAYLOAD_DENSITY_ATTACH_TILES);
        assert_eq!(steps[2].attach_kind, PAYLOAD_DENSITY_ATTACH_RGBA);
        assert_eq!(
            steps[6].attach_kind,
            PAYLOAD_DENSITY_ATTACH_SAMPLE
        );
        assert_eq!(
            steps[7].attach_kind,
            PAYLOAD_DENSITY_ATTACH_ENTRY_COLOR
        );
    }

    #[test]
    fn payload_density_grid_ship_plan_static_raster_when_sample_off() {
        let (_, _, n_attach, steps) = run_density_grid_ship_plan(0, 0, 0, 0, 0, 0, 1, 0);
        assert_eq!(n_attach, 3);
        assert_eq!(
            steps[2].attach_kind,
            PAYLOAD_DENSITY_ATTACH_OVERLAY_STATIC_RASTER
        );
    }

    #[test]
    fn payload_density_grid_ship_plan_rows_exceed_before_sample() {
        let (_, _, n_attach, steps) = run_density_grid_ship_plan(0, 0, 1, 0, 0, 1, 0, 0);
        assert_eq!(n_attach, 4);
        assert_eq!(
            steps[2].attach_kind,
            PAYLOAD_DENSITY_ATTACH_OVERLAY_ROWS_EXCEED
        );
        assert_eq!(steps[3].attach_kind, PAYLOAD_DENSITY_ATTACH_SAMPLE);
    }
}
