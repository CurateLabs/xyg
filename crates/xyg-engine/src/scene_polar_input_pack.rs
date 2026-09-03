//! Polar XYPL v1 input packing (M2 Push 3A completion, ABI 322).
//!
//! Hosts marshal polar axis literals; Rust owns theta-zero resolve, r-scale
//! kind, and XYPL v1 layout via [`crate::polar`].

use crate::polar::{encode_xypl, PolarEnvelope, XYPL_V1_BYTES};
use crate::scene_pack_orchestrate::scene_polar_figure_plan;

pub const SCENE_POLAR_INPUT_PACK_MAX: usize = XYPL_V1_BYTES;

/// Host-marshaled polar axis literals for one figure.
#[derive(Clone, Copy, Debug)]
pub struct ScenePolarInputPackIn {
    pub polar: i32,
    pub theta_unit: u32,
    pub theta_direction: u32,
    pub n_categories: u32,
    pub grid_shape: u8,
    pub r_scale_kind: u32,
    pub r_mask_nonpositive: i32,
    pub sector_start: f64,
    pub sector_end: f64,
    pub r_lo: f64,
    pub r_hi: f64,
    pub r_origin_is_nan: i32,
    pub r_origin: f64,
    pub hole: f64,
    pub r_constant: f64,
    pub theta_zero_is_label: i32,
    pub theta_zero_label_len: usize,
    pub theta_zero_numeric: f64,
}

fn resolve_theta_zero(input: &ScenePolarInputPackIn, label: &[u8]) -> Result<f64, i32> {
    if input.theta_zero_is_label != 0 {
        if let Some(value) = crate::polar::theta_zero_from_label(label) {
            return Ok(value);
        }
        if label.is_empty() {
            return Ok(0.0);
        }
        let text = std::str::from_utf8(label).map_err(|_| -1)?;
        text.parse::<f64>().map_err(|_| -1)
    } else {
        Ok(input.theta_zero_numeric)
    }
}

/// Pack XYPL v1 from host-marshaled polar literals. Returns empty when polar is
/// false. Error codes: ``-1`` invalid args.
pub fn scene_polar_input_pack(
    input: &ScenePolarInputPackIn,
    theta_zero_label: &[u8],
) -> Result<Vec<u8>, i32> {
    let mut plan = crate::scene_pack_orchestrate::PolarFigurePlan {
        polar: 0,
        attach_xypl: 0,
    };
    if scene_polar_figure_plan(input.polar, &mut plan) == 0 {
        return Err(-1);
    }
    if plan.attach_xypl == 0 {
        return Ok(Vec::new());
    }
    if !matches!(input.theta_unit, 0 | 1)
        || !matches!(input.theta_direction, 0 | 1)
        || !matches!(input.r_scale_kind, 0 | 1 | 2)
        || !matches!(input.grid_shape, 0 | 1)
        || !matches!(input.r_mask_nonpositive, 0 | 1)
    {
        return Err(-1);
    }
    if input.theta_zero_is_label != 0 && theta_zero_label.len() != input.theta_zero_label_len {
        return Err(-1);
    }
    let theta_zero = resolve_theta_zero(input, theta_zero_label)?;
    let r_origin = if input.r_origin_is_nan != 0 {
        f64::NAN
    } else {
        input.r_origin
    };
    let envelope = PolarEnvelope {
        theta_unit: input.theta_unit,
        theta_direction: input.theta_direction,
        n_categories: input.n_categories,
        r_scale_kind: input.r_scale_kind,
        grid_shape: input.grid_shape,
        r_mask_nonpositive: input.r_mask_nonpositive != 0,
        theta_zero,
        sector_start: input.sector_start,
        sector_end: input.sector_end,
        r_lo: input.r_lo,
        r_hi: input.r_hi,
        r_origin,
        hole: input.hole,
        r_constant: input.r_constant,
    };
    Ok(encode_xypl(&envelope).to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_when_not_polar() {
        let input = ScenePolarInputPackIn {
            polar: 0,
            theta_unit: 0,
            theta_direction: 0,
            n_categories: 0,
            grid_shape: 0,
            r_scale_kind: 0,
            r_mask_nonpositive: 0,
            sector_start: 0.0,
            sector_end: 1.0,
            r_lo: 0.0,
            r_hi: 1.0,
            r_origin_is_nan: 1,
            r_origin: 0.0,
            hole: 0.0,
            r_constant: 1.0,
            theta_zero_is_label: 1,
            theta_zero_label_len: 1,
            theta_zero_numeric: 0.0,
        };
        assert!(scene_polar_input_pack(&input, b"E").unwrap().is_empty());
    }

    #[test]
    fn packs_polar_xypl() {
        let input = ScenePolarInputPackIn {
            polar: 1,
            theta_unit: 0,
            theta_direction: 0,
            n_categories: 0,
            grid_shape: 0,
            r_scale_kind: 0,
            r_mask_nonpositive: 0,
            sector_start: 0.0,
            sector_end: std::f64::consts::TAU,
            r_lo: 0.0,
            r_hi: 1.0,
            r_origin_is_nan: 1,
            r_origin: 0.0,
            hole: 0.0,
            r_constant: 1.0,
            theta_zero_is_label: 1,
            theta_zero_label_len: 1,
            theta_zero_numeric: 0.0,
        };
        let packed = scene_polar_input_pack(&input, b"E").unwrap();
        assert_eq!(&packed[..4], b"XYPL");
        assert_eq!(packed.len(), XYPL_V1_BYTES);
    }
}
