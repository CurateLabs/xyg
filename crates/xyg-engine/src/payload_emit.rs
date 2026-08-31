//! Payload emit gather/ship orchestration (issue #732).
//!
//! Hosts retain buffer shipping and NumPy gathers; this module owns multi-step
//! emit policy so Python and Node stay bit-identical.

use crate::lod_plan::{
    payload_errorbar_indices, payload_errorbar_role_maps, payload_even_indices,
    payload_segment_budget, payload_transition_keys_admit, PayloadIndexSel,
    PAYLOAD_TRANSITION_SHIP,
};

pub const PAYLOAD_SEGMENTS_TIER_DIRECT: i32 = 0;
pub const PAYLOAD_SEGMENTS_TIER_DECIMATED: i32 = 1;

/// Always ship color/size via ``_ship_channels`` (scatter, hexbin, density sample).
pub const PAYLOAD_SHIP_CHANNELS_ALWAYS: i32 = 0;
/// Ship color/size only when ``color_ch`` is present (geometry marks).
pub const PAYLOAD_SHIP_CHANNELS_IF_COLOR: i32 = 1;

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
}
