//! Compact Figure→Scene density-grid packing (M2 #271).
//!
//! Hosts pass authored x/y columns, the product domain, and an optional
//! mean-color source. Rust owns the Scene blit grid size (512×384), `bin_2d`,
//! `density_log_u8`, optional `bin_2d_mean_color`, and XYDE wrapping so Python
//! and Node cannot drift on the density Image lattice. Encoded Scene v31 is
//! unchanged.

use crate::kernels::{self, BinColorSource};

pub const XYDE_MAGIC: &[u8; 4] = b"XYDE";
pub const XYDE_VERSION: u32 = 1;
pub const XYDE_V1_HEADER_BYTES: usize = 32;
pub const XYDE_HAS_MEAN_RGBA: u32 = 1 << 0;

/// Scene density Image lattice (lockstep with `python/xyg/config.py`
/// `DENSITY_GRID`).
pub const SCENE_DENSITY_GRID_COLS: usize = 512;
pub const SCENE_DENSITY_GRID_ROWS: usize = 384;

/// Why a density-grid packing request was rejected. Discriminants are the
/// C-ABI error codes (returned negated by `xyg_scene_pack_density_grid`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DensityGridError {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    Shape = 5,
    Payload = 6,
}

fn finite_increasing(lo: f64, hi: f64) -> bool {
    lo.is_finite() && hi.is_finite() && hi > lo
}

/// Pack Scene density encoded log-u8 (and optional mean RGBA) as XYDE v1.
///
/// Empty columns or a non-increasing domain skip the blit (empty output),
/// matching the host `use_density` product path.
pub fn pack_density_grid(
    x: &[f64],
    y: &[f64],
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    colors: Option<BinColorSource<'_>>,
) -> Result<Vec<u8>, DensityGridError> {
    if x.len() != y.len() {
        return Err(DensityGridError::Shape);
    }
    if x.is_empty() || !finite_increasing(x0, x1) || !finite_increasing(y0, y1) {
        return Ok(Vec::new());
    }
    if let Some(source) = &colors {
        match source {
            BinColorSource::Indexed { idx, lut } => {
                if idx.len() != x.len() || lut.is_empty() || lut.len() > 256 {
                    return Err(DensityGridError::Payload);
                }
            }
            BinColorSource::Rgba(rgba) => {
                if rgba.len() != x.len().saturating_mul(4) {
                    return Err(DensityGridError::Payload);
                }
            }
        }
    }
    let cells = SCENE_DENSITY_GRID_COLS
        .checked_mul(SCENE_DENSITY_GRID_ROWS)
        .ok_or(DensityGridError::Limit)?;
    let mut grid = vec![0.0f32; cells];
    kernels::bin_2d(
        x,
        y,
        x0,
        x1,
        y0,
        y1,
        SCENE_DENSITY_GRID_COLS,
        SCENE_DENSITY_GRID_ROWS,
        &mut grid,
    );
    let mut encoded = vec![0u8; cells];
    let gmax = kernels::density_log_u8_into(&grid, &mut encoded);
    let mut flags = 0u32;
    let mut mean = Vec::new();
    if let Some(source) = colors {
        mean.resize(cells.saturating_mul(4), 0u8);
        kernels::bin_2d_mean_color(
            x,
            y,
            &source,
            x0,
            x1,
            y0,
            y1,
            SCENE_DENSITY_GRID_COLS,
            SCENE_DENSITY_GRID_ROWS,
            &mut mean,
        );
        flags |= XYDE_HAS_MEAN_RGBA;
    }
    let mut out = Vec::with_capacity(XYDE_V1_HEADER_BYTES + encoded.len() + mean.len());
    out.extend_from_slice(XYDE_MAGIC);
    out.extend_from_slice(&XYDE_VERSION.to_le_bytes());
    out.extend_from_slice(&(SCENE_DENSITY_GRID_COLS as u32).to_le_bytes());
    out.extend_from_slice(&(SCENE_DENSITY_GRID_ROWS as u32).to_le_bytes());
    out.extend_from_slice(&flags.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&gmax.to_le_bytes());
    out.extend_from_slice(&encoded);
    out.extend_from_slice(&mean);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_columns_skip_density_blit() {
        assert!(pack_density_grid(&[], &[], 0.0, 1.0, 0.0, 1.0, None)
            .unwrap()
            .is_empty());
    }

    #[test]
    fn invalid_domain_skips_density_blit() {
        assert!(pack_density_grid(&[0.0], &[0.0], 1.0, 1.0, 0.0, 1.0, None)
            .unwrap()
            .is_empty());
    }

    #[test]
    fn points_encode_xyde_log_u8_grid() {
        let extras =
            pack_density_grid(&[0.25, 0.75], &[0.25, 0.75], 0.0, 1.0, 0.0, 1.0, None).unwrap();
        assert_eq!(&extras[..4], XYDE_MAGIC);
        assert_eq!(u32::from_le_bytes(extras[4..8].try_into().unwrap()), 1);
        assert_eq!(
            u32::from_le_bytes(extras[8..12].try_into().unwrap()),
            SCENE_DENSITY_GRID_COLS as u32
        );
        assert_eq!(
            u32::from_le_bytes(extras[12..16].try_into().unwrap()),
            SCENE_DENSITY_GRID_ROWS as u32
        );
        assert_eq!(u32::from_le_bytes(extras[16..20].try_into().unwrap()), 0);
        let cells = SCENE_DENSITY_GRID_COLS * SCENE_DENSITY_GRID_ROWS;
        assert_eq!(extras.len(), XYDE_V1_HEADER_BYTES + cells);
        assert!(extras[XYDE_V1_HEADER_BYTES..]
            .iter()
            .any(|&value| value > 0));
    }

    #[test]
    fn rgba_source_sets_mean_flag() {
        let rgba = [255u8, 0, 0, 255, 0, 0, 255, 255];
        let extras = pack_density_grid(
            &[0.25, 0.75],
            &[0.25, 0.75],
            0.0,
            1.0,
            0.0,
            1.0,
            Some(BinColorSource::Rgba(&rgba)),
        )
        .unwrap();
        assert_eq!(
            u32::from_le_bytes(extras[16..20].try_into().unwrap()),
            XYDE_HAS_MEAN_RGBA
        );
        let cells = SCENE_DENSITY_GRID_COLS * SCENE_DENSITY_GRID_ROWS;
        assert_eq!(extras.len(), XYDE_V1_HEADER_BYTES + cells + cells * 4);
    }

    #[test]
    fn mismatched_columns_are_shape() {
        assert_eq!(
            pack_density_grid(&[0.0, 1.0], &[0.0], 0.0, 1.0, 0.0, 1.0, None),
            Err(DensityGridError::Shape)
        );
    }
}
