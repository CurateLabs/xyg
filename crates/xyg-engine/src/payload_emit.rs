//! Payload emit gather/ship orchestration (issue #732).
//!
//! Hosts retain buffer shipping and NumPy gathers; this module owns multi-step
//! emit policy so Python and Node stay bit-identical.

use crate::lod_plan::{
    payload_errorbar_indices, payload_errorbar_role_maps, payload_even_indices,
    payload_segment_budget, PayloadIndexSel,
};

pub const PAYLOAD_SEGMENTS_TIER_DIRECT: i32 = 0;
pub const PAYLOAD_SEGMENTS_TIER_DECIMATED: i32 = 1;

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
}
