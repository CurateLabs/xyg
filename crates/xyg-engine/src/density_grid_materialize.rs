//! Payload density grid materialization (M2 big push #1, ABI 316).
//!
//! Owns pyramid/tile compose, bin2d path dispatch, log-u8 encode, optional
//! mean-color RGBA, and overlay sample row selection — the execution half of
//! ``_density_trace_spec`` after emit-plan policy is resolved.

use crate::density_emit::{
    format_binning, DensityEmitMeta, DENSITY_GRID_PATH_IDENTITY_GRID_ONLY,
    DENSITY_GRID_PATH_IDENTITY_SAMPLE_FUSED, DENSITY_GRID_PATH_IDENTITY_STRATIFIED_FUSED,
    DENSITY_GRID_PATH_IDENTITY_STRATIFIED_SPLIT, DENSITY_GRID_PATH_OVERSIZED_BIN2D,
    DENSITY_GRID_PATH_RANGE_INDICES, DENSITY_OVERLAY_NONE, DENSITY_SAMPLE_SEED,
    DENSITY_SAMPLE_TARGET,
};
use crate::kernels::{self, BinColorSource};
use crate::lod_plan::{self, PayloadIndexSel};
#[cfg(not(target_family = "wasm"))]
use crate::tile_store;
use crate::tiles;

const SAMPLE_GROWTH: f64 = 2.0;

/// Resource kind for pyramid first-paint compose.
pub const DENSITY_RESOURCE_NONE: i32 = 0;
pub const DENSITY_RESOURCE_PYRAMID: i32 = 1;
pub const DENSITY_RESOURCE_TILE_STORE: i32 = 2;

#[derive(Debug, Clone)]
pub struct DensityGridMaterializeOut {
    pub encoded_grid: Vec<u8>,
    pub gmax: f64,
    pub rgba_grid: Option<Vec<u8>>,
    pub sample_sel: Option<Vec<u32>>,
    pub visible_sel: Vec<u32>,
    pub visible: u64,
    pub binning: String,
    pub grid_from_pyramid: bool,
    pub has_pyramid_rgba: bool,
    pub pyramid_level: i32,
    pub from_tiles: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DensityGridMaterializeError {
    InvalidArgs,
    UnexpectedPath,
    StratifiedFailed,
}

fn sample_fraction_for(n: usize, target: u64, level: u32) -> Option<f64> {
    if n == 0 || target == 0 {
        return None;
    }
    let base = (target as f64 / n as f64).min(1.0);
    if base >= 1.0 {
        return Some(1.0);
    }
    if (SAMPLE_GROWTH - 1.0).abs() == 0.0 {
        return Some(base);
    }
    let Ok(level_i) = i32::try_from(level) else {
        return Some(1.0);
    };
    Some((base * SAMPLE_GROWTH.powi(level_i)).min(1.0))
}

fn n_groups_from_codes(codes: &[u8]) -> Option<usize> {
    codes.iter().map(|&code| code as usize).max().map(|max| max + 1)
}

/// Resolve exact per-code counts, computing them from dense u8 codes when the
/// host did not ship factorizer counts (object-array categoricals).
fn resolve_group_counts(codes: &[u8], counts: Option<&[u64]>) -> Option<Vec<u64>> {
    if let Some(counts) = counts {
        if counts.is_empty()
            || counts.len() > 256
            || counts
                .iter()
                .try_fold(0u64, |sum, &count| sum.checked_add(count))?
                != codes.len() as u64
        {
            return None;
        }
        return Some(counts.to_vec());
    }
    let n_groups = n_groups_from_codes(codes)?;
    if n_groups == 0 || n_groups > 256 {
        return None;
    }
    let mut computed = vec![0u64; n_groups];
    for &code in codes {
        *computed.get_mut(code as usize)? += 1;
    }
    Some(computed)
}

fn stratified_sample_sel(
    codes: &[u8],
    counts: Option<&[u64]>,
    seed: u64,
    fraction: f64,
    min_count: u64,
) -> Option<Vec<u32>> {
    if fraction >= 1.0 {
        return Some((0..codes.len() as u32).collect());
    }
    match counts {
        Some(counts) => {
            kernels::stratified_sample_range_u8_counted(codes, counts, seed, fraction, min_count)
        }
        None => {
            let n_groups = n_groups_from_codes(codes)?;
            kernels::stratified_sample_range_u8(codes, n_groups, seed, fraction, min_count)
        }
    }
}

fn pyramid_sample_sel(
    n_points: u64,
    stratified: bool,
    codes: Option<&[u8]>,
    counts: Option<&[u64]>,
) -> Option<Vec<u32>> {
    if stratified {
        let codes = codes?;
        if codes.len() != n_points as usize {
            return None;
        }
        let fraction = sample_fraction_for(codes.len(), DENSITY_SAMPLE_TARGET, 0)?;
        stratified_sample_sel(
            codes,
            counts,
            DENSITY_SAMPLE_SEED as u64,
            fraction,
            1,
        )
    } else {
        match lod_plan::payload_sample_target_indices(
            n_points as usize,
            DENSITY_SAMPLE_TARGET as usize,
            DENSITY_SAMPLE_SEED as u64,
            0,
            SAMPLE_GROWTH,
        )? {
            PayloadIndexSel::KeepAll => Some((0..n_points as u32).collect()),
            PayloadIndexSel::Indices(v) => Some(v),
        }
    }
}

fn try_pyramid_compose(
    resource: i32,
    handle: u64,
    pyr_colored: bool,
    bx0: f64,
    bx1: f64,
    by0: f64,
    by1: f64,
    w: usize,
    h: usize,
    max_upsample: usize,
) -> Option<(Vec<f32>, Option<Vec<u8>>, usize, bool, bool)> {
    let cells = w.checked_mul(h)?;
    let mut grid = vec![0.0f32; cells];
    match resource {
        DENSITY_RESOURCE_TILE_STORE => {
            #[cfg(not(target_family = "wasm"))]
            {
                let mut rgba = pyr_colored.then(|| vec![0u8; cells * 4]);
                let (level, upsampled) = tile_store::reg_with(handle, |store| {
                    if pyr_colored {
                        let rgba_buf = rgba.as_mut()?;
                        let level = store
                            .compose_color(
                                bx0,
                                bx1,
                                by0,
                                by1,
                                w,
                                h,
                                max_upsample,
                                &mut grid,
                                rgba_buf,
                            )
                            .ok()??;
                        Some((
                            level,
                            store.level_is_upsampled(level, bx0, bx1, by0, by1, w, h),
                        ))
                    } else {
                        let level = store
                            .compose(bx0, bx1, by0, by1, w, h, max_upsample, &mut grid)
                            .ok()??;
                        Some((
                            level,
                            store.level_is_upsampled(level, bx0, bx1, by0, by1, w, h),
                        ))
                    }
                })??;
                Some((grid, rgba, level, true, upsampled))
            }
            #[cfg(target_family = "wasm")]
            {
                None
            }
        }
        DENSITY_RESOURCE_PYRAMID => {
            if pyr_colored {
                let mut rgba = vec![0u8; cells * 4];
                let (level, upsampled) = tiles::reg_with(handle, |pyr| {
                    let level = tiles::compose_color(
                        pyr,
                        bx0,
                        bx1,
                        by0,
                        by1,
                        w,
                        h,
                        max_upsample,
                        &mut grid,
                        &mut rgba,
                    )?;
                    Some((
                        level,
                        tiles::level_is_upsampled(pyr, level, bx0, bx1, by0, by1, w, h),
                    ))
                })??;
                Some((grid, Some(rgba), level, false, upsampled))
            } else {
                let (level, upsampled) = tiles::reg_with(handle, |pyr| {
                    let level =
                        tiles::compose(pyr, bx0, bx1, by0, by1, w, h, max_upsample, &mut grid)?;
                    Some((
                        level,
                        tiles::level_is_upsampled(pyr, level, bx0, bx1, by0, by1, w, h),
                    ))
                })??;
                Some((grid, None, level, false, upsampled))
            }
        }
        _ => None,
    }
}

fn binning_pyramid(level: usize, from_tiles: bool, upsampled: bool) -> String {
    let mut buf = [0u8; 64];
    let n = format_binning(false, level as i32, from_tiles, upsampled, &mut buf)
        .expect("pyramid binning fits");
    String::from_utf8(buf[..n].to_vec()).expect("ascii binning")
}

fn binning_exact() -> String {
    let mut buf = [0u8; 64];
    let n = format_binning(true, 0, false, false, &mut buf).expect("exact binning fits");
    String::from_utf8(buf[..n].to_vec()).expect("ascii binning")
}

#[allow(clippy::too_many_arguments)]
pub fn payload_density_grid_materialize(
    meta: &DensityEmitMeta,
    n_points: u64,
    bx0: f64,
    bx1: f64,
    by0: f64,
    by1: f64,
    xr0: f64,
    xr1: f64,
    yr0: f64,
    yr1: f64,
    w: usize,
    h: usize,
    x_raw: &[f64],
    y_raw: &[f64],
    bx: &[f64],
    by: &[f64],
    pyramid_attempt: bool,
    pyramid_resource: i32,
    pyramid_handle: u64,
    pyr_colored: bool,
    max_upsample: usize,
    tile_upsample: usize,
    _pyramid_no_rescan: bool,
    needs_pyramid_sample: bool,
    pyramid_sample_stratified: bool,
    color_codes: Option<&[u8]>,
    color_counts: Option<&[u64]>,
    bin_colors: Option<BinColorSource<'_>>,
    ship_mean_color: bool,
) -> Result<DensityGridMaterializeOut, DensityGridMaterializeError> {
    if w == 0
        || h == 0
        || x_raw.len() != y_raw.len()
        || bx.len() != by.len()
        || bx.len() != x_raw.len()
    {
        return Err(DensityGridMaterializeError::InvalidArgs);
    }
    let cells = w
        .checked_mul(h)
        .ok_or(DensityGridMaterializeError::InvalidArgs)?;

    let mut grid_from_pyramid = false;
    let mut from_tiles = false;
    let mut pyramid_level = -1i32;
    let mut rgba_from_pyramid: Option<Vec<u8>> = None;
    let mut grid: Option<Vec<f32>> = None;
    let mut binning = binning_exact();
    let mut sample_sel: Option<Vec<u32>> = None;

    if pyramid_attempt && pyramid_resource != DENSITY_RESOURCE_NONE {
        let upsample = if pyramid_resource == DENSITY_RESOURCE_TILE_STORE {
            tile_upsample.max(1)
        } else {
            max_upsample.max(1)
        };
        if let Some((g, rgba, level, tiles_flag, upsampled)) = try_pyramid_compose(
            pyramid_resource,
            pyramid_handle,
            pyr_colored,
            bx0,
            bx1,
            by0,
            by1,
            w,
            h,
            upsample,
        ) {
            grid_from_pyramid = true;
            from_tiles = tiles_flag;
            pyramid_level = level as i32;
            rgba_from_pyramid = rgba;
            grid = Some(g);
            binning = binning_pyramid(level, from_tiles, upsampled);
        }
    }

    let wants_pyramid_sample = needs_pyramid_sample
        || (grid_from_pyramid
            && !meta.oversized
            && meta.overlay_omitted == DENSITY_OVERLAY_NONE);
    if wants_pyramid_sample && sample_sel.is_none() {
        sample_sel = pyramid_sample_sel(n_points, pyramid_sample_stratified, color_codes, color_counts);
    }

    let mut visible = n_points;
    let mut visible_sel: Vec<u32> = Vec::new();

    if grid.is_none() {
        let path = meta.grid_path;
        if meta.use_raw_range_bin2d {
            sample_sel = None;
            let mut g = vec![0.0f32; cells];
            kernels::bin_2d(x_raw, y_raw, xr0, xr1, yr0, yr1, w, h, &mut g);
            grid = Some(g);
            binning = binning_exact();
        } else if path == DENSITY_GRID_PATH_IDENTITY_GRID_ONLY {
            let mut g = vec![0.0f32; cells];
            kernels::bin_2d(bx, by, bx0, bx1, by0, by1, w, h, &mut g);
            grid = Some(g);
            binning = binning_exact();
        } else if path == DENSITY_GRID_PATH_IDENTITY_STRATIFIED_FUSED {
            let codes = color_codes.ok_or(DensityGridMaterializeError::StratifiedFailed)?;
            let counts = resolve_group_counts(codes, color_counts)
                .ok_or(DensityGridMaterializeError::StratifiedFailed)?;
            let fraction = sample_fraction_for(bx.len(), DENSITY_SAMPLE_TARGET, 0)
                .ok_or(DensityGridMaterializeError::StratifiedFailed)?;
            let mut g = vec![0.0f32; cells];
            sample_sel = Some(
                kernels::bin_2d_stratified_sample_range_u8_counted(
                    bx,
                    by,
                    codes,
                    &counts,
                    bx0,
                    bx1,
                    by0,
                    by1,
                    w,
                    h,
                    DENSITY_SAMPLE_SEED as u64,
                    fraction,
                    1,
                    &mut g,
                )
                .ok_or(DensityGridMaterializeError::StratifiedFailed)?,
            );
            grid = Some(g);
            binning = binning_exact();
        } else if path == DENSITY_GRID_PATH_IDENTITY_STRATIFIED_SPLIT {
            let codes = color_codes.ok_or(DensityGridMaterializeError::StratifiedFailed)?;
            let mut g = vec![0.0f32; cells];
            kernels::bin_2d(bx, by, bx0, bx1, by0, by1, w, h, &mut g);
            let fraction = sample_fraction_for(codes.len(), DENSITY_SAMPLE_TARGET, 0)
                .ok_or(DensityGridMaterializeError::StratifiedFailed)?;
            sample_sel = Some(
                stratified_sample_sel(
                    codes,
                    color_counts,
                    DENSITY_SAMPLE_SEED as u64,
                    fraction,
                    1,
                )
                .ok_or(DensityGridMaterializeError::StratifiedFailed)?,
            );
            grid = Some(g);
            binning = binning_exact();
        } else if path == DENSITY_GRID_PATH_IDENTITY_SAMPLE_FUSED {
            let fraction = sample_fraction_for(bx.len(), DENSITY_SAMPLE_TARGET, 0)
                .ok_or(DensityGridMaterializeError::StratifiedFailed)?;
            let mut g = vec![0.0f32; cells];
            if fraction >= 1.0 {
                kernels::bin_2d(bx, by, bx0, bx1, by0, by1, w, h, &mut g);
                sample_sel = Some((0..bx.len() as u32).collect());
            } else {
                let threshold = kernels::sample_threshold(fraction);
                let cap = bx.len().min((DENSITY_SAMPLE_TARGET as usize * 2).max(64));
                let mut rows = vec![0u32; cap];
                let n = kernels::bin_2d_sample_range(
                    bx,
                    by,
                    bx0,
                    bx1,
                    by0,
                    by1,
                    w,
                    h,
                    DENSITY_SAMPLE_SEED as u64,
                    threshold,
                    &mut g,
                    &mut rows,
                );
                rows.truncate(n);
                sample_sel = Some(rows);
            }
            grid = Some(g);
            binning = binning_exact();
        } else if path == DENSITY_GRID_PATH_RANGE_INDICES {
            let mut g = vec![0.0f32; cells];
            let mut idx = vec![0u32; bx.len()];
            let n = kernels::bin_2d_indices(bx, by, bx0, bx1, by0, by1, w, h, &mut g, &mut idx);
            idx.truncate(n);
            visible = n as u64;
            visible_sel = idx;
            grid = Some(g);
            binning = binning_exact();
        } else if path == DENSITY_GRID_PATH_OVERSIZED_BIN2D {
            return Err(DensityGridMaterializeError::UnexpectedPath);
        } else {
            return Err(DensityGridMaterializeError::UnexpectedPath);
        }
    } else if meta.visible_is_n_points {
        visible = n_points;
        visible_sel.clear();
    }

    let grid = grid.ok_or(DensityGridMaterializeError::InvalidArgs)?;
    let mut encoded_grid = vec![0u8; cells];
    let gmax = kernels::density_log_u8_into(&grid, &mut encoded_grid);

    let mut rgba_grid = None;
    let has_pyramid_rgba = rgba_from_pyramid.is_some();
    if ship_mean_color {
        if let Some(rgba) = rgba_from_pyramid {
            rgba_grid = Some(rgba);
        } else if let Some(source) = bin_colors {
            let mut mean = vec![0u8; cells * 4];
            kernels::bin_2d_mean_color(bx, by, &source, bx0, bx1, by0, by1, w, h, &mut mean);
            rgba_grid = Some(mean);
        }
    }

    Ok(DensityGridMaterializeOut {
        encoded_grid,
        gmax,
        rgba_grid,
        sample_sel,
        visible_sel,
        visible,
        binning,
        grid_from_pyramid,
        has_pyramid_rgba,
        pyramid_level,
        from_tiles,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::density_emit::emit_meta;

    fn identity_meta(n: u64) -> DensityEmitMeta {
        emit_meta(
            true,
            true,
            true,
            false,
            false,
            false,
            false,
            false,
            true,
            false,
            false,
            false,
            false,
            false,
            false,
            crate::density_emit::DENSITY_COLOR_MODE_NONE,
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
            n,
        )
        .expect("identity meta")
    }

    #[test]
    fn materialize_identity_grid_only() {
        let x = [0.25, 0.75];
        let y = [0.25, 0.75];
        let meta = identity_meta(2);
        let out = payload_density_grid_materialize(
            &meta,
            2,
            0.0,
            1.0,
            0.0,
            1.0,
            0.0,
            1.0,
            0.0,
            1.0,
            4,
            4,
            &x,
            &y,
            &x,
            &y,
            false,
            DENSITY_RESOURCE_NONE,
            0,
            false,
            2,
            2,
            false,
            false,
            false,
            None,
            None,
            None,
            false,
        )
        .expect("materialize");
        assert_eq!(out.encoded_grid.len(), 16);
        assert!(out.gmax >= 0.0);
        assert_eq!(out.binning, "exact");
        assert!(!out.grid_from_pyramid);
    }

    #[test]
    fn materialize_labels_resident_and_tiled_l0_from_actual_resolution() {
        let x = [0.1, 0.9];
        let y = [0.1, 0.9];
        let pyramid = tiles::build(&x, &y, 0.0, 1.0, 0.0, 1.0, 32).expect("pyramid");
        let store = tile_store::TileStore::spill(&pyramid).expect("spill");
        let resident = tiles::reg_insert(pyramid);
        let tiled = tile_store::reg_insert(store);
        let meta = identity_meta(20_000_000);

        for (resource, handle, suffix) in [
            (DENSITY_RESOURCE_PYRAMID, resident, ""),
            (DENSITY_RESOURCE_TILE_STORE, tiled, "-tiles"),
        ] {
            let compose = |w| {
                payload_density_grid_materialize(
                    &meta,
                    20_000_000,
                    0.25,
                    0.5,
                    0.0,
                    1.0,
                    0.25,
                    0.5,
                    0.0,
                    1.0,
                    w,
                    4,
                    &x,
                    &y,
                    &x,
                    &y,
                    true,
                    resource,
                    handle,
                    false,
                    1 << 20,
                    1 << 20,
                    true,
                    false,
                    false,
                    None,
                    None,
                    None,
                    false,
                )
                .expect("pyramid materialize")
            };

            // A quarter of a 32-cell base supplies eight source cells. Six
            // requested pixels are served natively; twelve truly enlarge L0.
            assert_eq!(compose(6).binning, format!("pyramid-L0{suffix}"));
            assert_eq!(compose(12).binning, format!("pyramid-L0{suffix}-upsampled"));
        }

        assert!(tiles::reg_remove(resident));
        assert!(tile_store::reg_remove(tiled));
    }

    #[test]
    fn materialize_stratified_split_without_shipped_counts() {
        let n = 10_000usize;
        let mut x = vec![0.0f64; n];
        let mut y = vec![0.0f64; n];
        let mut codes = vec![0u8; n];
        for i in 0..n {
            x[i] = (i as f64 / n as f64).fract();
            y[i] = ((i * 7) as f64 / n as f64).fract();
            codes[i] = if i == 17 { 1 } else { 0 };
        }
        let meta = emit_meta(
            true,
            true,
            true,
            true,
            true,
            false,
            false,
            false,
            true,
            false,
            false,
            false,
            false,
            false,
            false,
            crate::density_emit::DENSITY_COLOR_MODE_OTHER,
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
            n as u64,
        )
        .expect("stratified split meta");
        let out = payload_density_grid_materialize(
            &meta,
            n as u64,
            0.0,
            1.0,
            0.0,
            1.0,
            0.0,
            1.0,
            0.0,
            1.0,
            32,
            32,
            &x,
            &y,
            &x,
            &y,
            false,
            DENSITY_RESOURCE_NONE,
            0,
            false,
            2,
            2,
            false,
            false,
            false,
            Some(&codes),
            None,
            None,
            false,
        )
        .expect("stratified split without counts");
        assert_eq!(out.encoded_grid.len(), 32 * 32);
        let sample = out.sample_sel.expect("sample rows");
        assert!(!sample.is_empty());
        assert!(sample.contains(&17));
    }
}
