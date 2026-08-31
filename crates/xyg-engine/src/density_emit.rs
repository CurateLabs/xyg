//! First-paint density scatter emit policy (§28 / ABI 132).
//!
//! Hosts retain axis-scale transforms, pyramid/tile handles, buffer shipping,
//! and kernel invocation; this module owns the path/binning/WASM/overlay
//! decisions so Python and Node stay bit-identical.

/// Mirror `python/xyg/config.py` `PYRAMID_MIN_POINTS`.
pub const PYRAMID_MIN_POINTS: u64 = 2_000_000;
/// Mirror `python/xyg/config.py` `PYRAMID_NO_RESCAN_ROWS`.
pub const PYRAMID_NO_RESCAN_ROWS: u64 = 200_000_000;
/// Mirror `python/xyg/_wasm_aggregate_generated.py` `WASM_AGGREGATE_MAX_POINTS`.
pub const WASM_AGGREGATE_MAX_POINTS: u64 = 8_000_000;
/// Mirror `python/xyg/config.py` `DENSITY_SAMPLE_TARGET`.
pub const DENSITY_SAMPLE_TARGET: u64 = 8_192;
/// Mirror `python/xyg/config.py` `DENSITY_SAMPLE_SEED`.
pub const DENSITY_SAMPLE_SEED: u32 = 0;
/// Per-row overlay/sample kernels top out at u32 row ids.
pub const U32_MAX: u64 = (1u64 << 32) - 1;

const PYRAMID_UNBOUNDED_UPSAMPLE: u32 = 1_000_000;
const PYRAMID_BOUNDED_UPSAMPLE: u32 = 2;

/// Exact `bin_2d` on raw columns with view ranges (oversized grid-only).
pub const DENSITY_GRID_PATH_OVERSIZED_BIN2D: i32 = 0;
/// Exact grid without overlay sample (`full_identity && !point_overlay`).
pub const DENSITY_GRID_PATH_IDENTITY_GRID_ONLY: i32 = 1;
/// Fused stratified grid+sample when category counts are present.
pub const DENSITY_GRID_PATH_IDENTITY_STRATIFIED_FUSED: i32 = 2;
/// Defensive split: plain grid + separate stratified sample (no counts).
pub const DENSITY_GRID_PATH_IDENTITY_STRATIFIED_SPLIT: i32 = 3;
/// Fused grid+sample for the ordinary identity case.
pub const DENSITY_GRID_PATH_IDENTITY_SAMPLE_FUSED: i32 = 4;
/// Fused grid + visible row indices when data exceeds the view window.
pub const DENSITY_GRID_PATH_RANGE_INDICES: i32 = 5;

pub const DENSITY_COLOR_MODE_NONE: i32 = 0;
pub const DENSITY_COLOR_MODE_CONSTANT: i32 = 1;
pub const DENSITY_COLOR_MODE_OTHER: i32 = 2;

/// Host color-channel mode tokens for ``density_color_classify`` (ABI 260).
pub const DENSITY_CHANNEL_MODE_NONE: i32 = 0;
pub const DENSITY_CHANNEL_MODE_CONSTANT: i32 = 1;
pub const DENSITY_CHANNEL_MODE_CATEGORICAL: i32 = 2;
pub const DENSITY_CHANNEL_MODE_CONTINUOUS: i32 = 3;
pub const DENSITY_CHANNEL_MODE_OTHER: i32 = 4;

/// Density scatter color-channel classify (ABI 260).
///
/// Hosts pass the resolved color-channel mode plus categorical code metadata.
/// Returns ``1`` on success and writes the ``density_emit_meta`` boolean trio
/// plus ``DENSITY_COLOR_MODE_*``.
pub fn density_color_classify(
    channel_mode: i32,
    codes_present: i32,
    codes_u8: i32,
    has_counts: i32,
    out_color_mode: &mut i32,
    out_categorical: &mut i32,
    out_compact_categorical: &mut i32,
    out_stratified_counts: &mut i32,
) -> i32 {
    if !(0..=4).contains(&channel_mode) {
        return 0;
    }
    let categorical = channel_mode == DENSITY_CHANNEL_MODE_CATEGORICAL;
    let compact = categorical && codes_present != 0 && codes_u8 != 0;
    *out_categorical = i32::from(categorical);
    *out_compact_categorical = i32::from(compact);
    *out_stratified_counts = i32::from(compact && has_counts != 0);
    *out_color_mode = match channel_mode {
        DENSITY_CHANNEL_MODE_NONE => DENSITY_COLOR_MODE_NONE,
        DENSITY_CHANNEL_MODE_CONSTANT => DENSITY_COLOR_MODE_CONSTANT,
        _ => DENSITY_COLOR_MODE_OTHER,
    };
    1
}

/// Resolve density color-channel mode names (ABI 262 helper).
fn density_channel_mode_from_name(mode: &str) -> i32 {
    match mode {
        "constant" => DENSITY_CHANNEL_MODE_CONSTANT,
        "categorical" => DENSITY_CHANNEL_MODE_CATEGORICAL,
        "continuous" => DENSITY_CHANNEL_MODE_CONTINUOUS,
        _ => DENSITY_CHANNEL_MODE_OTHER,
    }
}

/// Density trace color-channel classify (ABI 262).
///
/// Hosts pass whether ``color_ch`` is present, its ``mode`` string, and
/// categorical code metadata. Resolves the channel mode then delegates to
/// ``density_color_classify``.
pub fn density_trace_color_classify(
    has_channel: i32,
    mode: &str,
    codes_present: i32,
    codes_u8: i32,
    has_counts: i32,
    out_color_mode: &mut i32,
    out_categorical: &mut i32,
    out_compact_categorical: &mut i32,
    out_stratified_counts: &mut i32,
) -> i32 {
    if !matches!(has_channel, 0 | 1) {
        return 0;
    }
    let channel_mode = if has_channel == 0 {
        DENSITY_CHANNEL_MODE_NONE
    } else {
        density_channel_mode_from_name(mode)
    };
    density_color_classify(
        channel_mode,
        codes_present,
        codes_u8,
        has_counts,
        out_color_mode,
        out_categorical,
        out_compact_categorical,
        out_stratified_counts,
    )
}

/// Select density binning coordinate endpoints (ABI 263).
///
/// Linear axes bin in view-range coordinates; nonlinear axes bin in transformed
/// column bounds from ``_binning_coords``. Matches ``_density_trace_spec``.
pub fn bin_coord_endpoints(
    x_linear: bool,
    y_linear: bool,
    xr0: f64,
    xr1: f64,
    yr0: f64,
    yr1: f64,
    bx0: f64,
    bx1: f64,
    by0: f64,
    by1: f64,
    out_x_c0: &mut f64,
    out_x_c1: &mut f64,
    out_y_c0: &mut f64,
    out_y_c1: &mut f64,
) -> i32 {
    if x_linear {
        *out_x_c0 = xr0;
        *out_x_c1 = xr1;
    } else {
        *out_x_c0 = bx0;
        *out_x_c1 = bx1;
    }
    if y_linear {
        *out_y_c0 = yr0;
        *out_y_c1 = yr1;
    } else {
        *out_y_c0 = by0;
        *out_y_c1 = by1;
    }
    1
}

/// Whether density spec uses the channel-authored colormap (ABI 264).
///
/// Returns ``1`` when ``color_ch`` is present and ``mode`` is ``constant`` or
/// ``continuous``; otherwise ``0`` (host falls back to ``DEFAULT_COLORMAP``).
pub fn density_uses_channel_colormap(has_channel: i32, mode: &str) -> i32 {
    if has_channel == 0 {
        return 0;
    }
    i32::from(matches!(mode, "constant" | "continuous"))
}

/// Whether density spec should ship ``density["color"]`` from a constant channel (ABI 268).
///
/// Returns ``1`` when ``color_ch`` is present, ``mode`` is ``constant``, and the
/// host reports a non-null constant CSS value.
pub fn density_constant_color_wire_admit(has_channel: i32, mode: &str, has_constant: i32) -> i32 {
    if has_channel == 0 || has_constant == 0 {
        return 0;
    }
    i32::from(mode == "constant")
}

/// Whether density spec should ship ``density["wasm_source"]`` (ABI 269).
///
/// Returns ``1`` when the split payload writer is active and the emit plan
/// reports WASM aggregate replay eligibility.
pub fn density_wasm_source_admit(split_payload: i32, wasm_eligible: i32) -> i32 {
    i32::from(split_payload == 1 && wasm_eligible == 1)
}

pub const DENSITY_REDUCTION_BIN2D: i32 = 0;
pub const DENSITY_REDUCTION_PYRAMID_COUNT: i32 = 1;

/// Density reduction label kind from ``density["binning"]`` (ABI 265).
///
/// Returns ``DENSITY_REDUCTION_PYRAMID_COUNT`` when ``binning`` starts with
/// ``pyramid-``; otherwise ``DENSITY_REDUCTION_BIN2D``.
pub fn density_reduction_kind(binning: &str) -> i32 {
    if binning.starts_with("pyramid-") {
        DENSITY_REDUCTION_PYRAMID_COUNT
    } else {
        DENSITY_REDUCTION_BIN2D
    }
}

/// Wire ``density["overlay_omitted"]`` when the emit plan records a drop (ABI 266).
///
/// Returns written byte length, or ``None`` when ``out`` is too small. Zero means
/// omit the wire key (``DENSITY_OVERLAY_NONE``, or static raster with overlay).
pub fn density_overlay_omitted_wire(
    overlay_omitted: u32,
    point_overlay: bool,
    out: &mut [u8],
) -> Option<usize> {
    let wire: &[u8] = match overlay_omitted {
        DENSITY_OVERLAY_ROWS_EXCEED_U32 => b"rows_exceed_u32",
        DENSITY_OVERLAY_STATIC_RASTER if !point_overlay => b"static_raster",
        _ => return Some(0),
    };
    if out.len() < wire.len() {
        return None;
    }
    out[..wire.len()].copy_from_slice(wire);
    Some(wire.len())
}

pub const DENSITY_OVERLAY_NONE: u32 = 0;
pub const DENSITY_OVERLAY_ROWS_EXCEED_U32: u32 = 1;
pub const DENSITY_OVERLAY_STATIC_RASTER: u32 = 2;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct BinWindow {
    pub x0: f64,
    pub x1: f64,
    pub y0: f64,
    pub y1: f64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PyramidPreflight {
    pub eligible: bool,
    pub attempt: bool,
    pub no_rescan: bool,
    pub max_upsample: u32,
    pub tile_upsample: u32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DensityEmitMeta {
    pub grid_path: i32,
    pub bin_window: BinWindow,
    pub full_identity: bool,
    pub oversized: bool,
    pub pyramid: PyramidPreflight,
    pub wasm_eligible: bool,
    pub needs_pyramid_sample: bool,
    pub overlay_omitted: u32,
    pub visible_is_n_points: bool,
    pub use_raw_range_bin2d: bool,
}

fn finite_increasing(lo: f64, hi: f64) -> bool {
    lo.is_finite() && hi.is_finite() && hi > lo
}

/// Bin window in axis-scale coordinates (§28), matching `_binning_coords`.
pub fn bin_window(
    x_linear: bool,
    y_linear: bool,
    xr0: f64,
    xr1: f64,
    yr0: f64,
    yr1: f64,
    x_c0: f64,
    x_c1: f64,
    y_c0: f64,
    y_c1: f64,
) -> Option<BinWindow> {
    if !finite_increasing(xr0, xr1) || !finite_increasing(yr0, yr1) {
        return None;
    }
    let (x0, x1) = if x_linear {
        (xr0, xr1)
    } else if finite_increasing(x_c0, x_c1) {
        (x_c0, x_c1)
    } else {
        (xr0, xr1)
    };
    let (y0, y1) = if y_linear {
        (yr0, yr1)
    } else if finite_increasing(y_c0, y_c1) {
        (y_c0, y_c1)
    } else {
        (yr0, yr1)
    };
    Some(BinWindow { x0, x1, y0, y1 })
}

/// Whether the trace fully covers the view window with identity row mapping.
pub fn full_identity(
    categorical: bool,
    compact_categorical: bool,
    x_has_nulls: bool,
    y_has_nulls: bool,
    x_min: f64,
    x_max: f64,
    y_min: f64,
    y_max: f64,
    xr0: f64,
    xr1: f64,
    yr0: f64,
    yr1: f64,
) -> Option<bool> {
    if !x_min.is_finite()
        || !x_max.is_finite()
        || !y_min.is_finite()
        || !y_max.is_finite()
        || !finite_increasing(xr0, xr1)
        || !finite_increasing(yr0, yr1)
    {
        return None;
    }
    if categorical && !compact_categorical {
        return Some(false);
    }
    if x_has_nulls || y_has_nulls {
        return Some(false);
    }
    Some(x_min >= xr0 && x_max <= xr1 && y_min >= yr0 && y_max <= yr1)
}

fn should_use_pyramid(n_points: u64, force_pyramid: bool, force_bin2d: bool) -> bool {
    if force_bin2d {
        return false;
    }
    if force_pyramid {
        return true;
    }
    n_points >= PYRAMID_MIN_POINTS
}

/// Tier-3 pyramid preflight before compose (§28 `pyramid-L*`).
pub fn pyramid_preflight(
    x_linear: bool,
    y_linear: bool,
    n_points: u64,
    has_pyramid_resource: bool,
    x_memmapped: bool,
    y_memmapped: bool,
    force_pyramid: bool,
    force_bin2d: bool,
) -> Option<PyramidPreflight> {
    let linear_axes = x_linear && y_linear;
    let eligible = linear_axes && should_use_pyramid(n_points, force_pyramid, force_bin2d);
    let attempt = eligible && has_pyramid_resource;
    let no_rescan = x_memmapped || y_memmapped || n_points > PYRAMID_NO_RESCAN_ROWS;
    let max_upsample = if no_rescan {
        PYRAMID_UNBOUNDED_UPSAMPLE
    } else {
        PYRAMID_BOUNDED_UPSAMPLE
    };
    let tile_upsample = if no_rescan || has_pyramid_resource {
        PYRAMID_UNBOUNDED_UPSAMPLE
    } else {
        max_upsample
    };
    Some(PyramidPreflight {
        eligible,
        attempt,
        no_rescan,
        max_upsample,
        tile_upsample,
    })
}

/// Which exact grid kernel path to run when pyramid compose did not yield a grid.
pub fn grid_path(
    oversized: bool,
    full_identity: bool,
    point_overlay: bool,
    compact_categorical: bool,
    stratified_counts: bool,
) -> i32 {
    if oversized {
        return DENSITY_GRID_PATH_OVERSIZED_BIN2D;
    }
    if full_identity && !point_overlay {
        return DENSITY_GRID_PATH_IDENTITY_GRID_ONLY;
    }
    if full_identity && point_overlay && compact_categorical && stratified_counts {
        return DENSITY_GRID_PATH_IDENTITY_STRATIFIED_FUSED;
    }
    if full_identity && point_overlay && compact_categorical && !stratified_counts {
        return DENSITY_GRID_PATH_IDENTITY_STRATIFIED_SPLIT;
    }
    if full_identity && point_overlay {
        return DENSITY_GRID_PATH_IDENTITY_SAMPLE_FUSED;
    }
    DENSITY_GRID_PATH_RANGE_INDICES
}

/// Whether grid-path dispatch initializes ``visible = n_points`` and an empty
/// ``sel`` before binning (ABI 267).
///
/// Returns ``1`` for every path except ``DENSITY_GRID_PATH_RANGE_INDICES``,
/// ``0`` for range-indices (visible comes from ``len(sel)`` after binning),
/// ``-1`` when ``grid_path`` is unknown.
pub fn density_grid_path_identity_state(grid_path: i32) -> i32 {
    match grid_path {
        DENSITY_GRID_PATH_RANGE_INDICES => 0,
        DENSITY_GRID_PATH_OVERSIZED_BIN2D
        | DENSITY_GRID_PATH_IDENTITY_GRID_ONLY
        | DENSITY_GRID_PATH_IDENTITY_STRATIFIED_FUSED
        | DENSITY_GRID_PATH_IDENTITY_STRATIFIED_SPLIT
        | DENSITY_GRID_PATH_IDENTITY_SAMPLE_FUSED => 1,
        _ => -1,
    }
}

/// Format §28 `density["binning"]` strings (no trailing NUL).
pub fn format_binning(
    exact: bool,
    level: i32,
    tiles: bool,
    upsampled: bool,
    out: &mut [u8],
) -> Option<usize> {
    if exact {
        let bytes = b"exact";
        if out.len() < bytes.len() {
            return None;
        }
        out[..bytes.len()].copy_from_slice(bytes);
        return Some(bytes.len());
    }
    if level < 0 {
        return None;
    }
    let mut scratch = [0u8; 64];
    let mut n = 0usize;
    let prefix = b"pyramid-L";
    scratch[n..n + prefix.len()].copy_from_slice(prefix);
    n += prefix.len();
    let level_text = format!("{level}");
    let level_bytes = level_text.as_bytes();
    if n + level_bytes.len() > scratch.len() {
        return None;
    }
    scratch[n..n + level_bytes.len()].copy_from_slice(level_bytes);
    n += level_bytes.len();
    if tiles {
        let suffix = b"-tiles";
        if n + suffix.len() > scratch.len() {
            return None;
        }
        scratch[n..n + suffix.len()].copy_from_slice(suffix);
        n += suffix.len();
    }
    if upsampled {
        let suffix = b"-upsampled";
        if n + suffix.len() > scratch.len() {
            return None;
        }
        scratch[n..n + suffix.len()].copy_from_slice(suffix);
        n += suffix.len();
    }
    if out.len() < n {
        return None;
    }
    out[..n].copy_from_slice(&scratch[..n]);
    Some(n)
}

/// Whether the split WASM aggregate replay lane is eligible.
pub fn wasm_eligible(
    cartesian: bool,
    x_linear: bool,
    y_linear: bool,
    color_mode: i32,
    x_has_nulls: bool,
    y_has_nulls: bool,
    n_points: u64,
) -> Option<bool> {
    if !matches!(
        color_mode,
        DENSITY_COLOR_MODE_NONE | DENSITY_COLOR_MODE_CONSTANT | DENSITY_COLOR_MODE_OTHER
    ) {
        return None;
    }
    Some(
        cartesian
            && x_linear
            && y_linear
            && matches!(
                color_mode,
                DENSITY_COLOR_MODE_NONE | DENSITY_COLOR_MODE_CONSTANT
            )
            && !x_has_nulls
            && !y_has_nulls
            && n_points > 0
            && n_points <= WASM_AGGREGATE_MAX_POINTS,
    )
}

/// Full first-paint density emit plan for one trace/viewport.
#[allow(clippy::too_many_arguments)]
pub fn emit_meta(
    cartesian: bool,
    x_linear: bool,
    y_linear: bool,
    categorical: bool,
    compact_categorical: bool,
    stratified_counts: bool,
    x_has_nulls: bool,
    y_has_nulls: bool,
    point_overlay: bool,
    grid_from_pyramid: bool,
    x_memmapped: bool,
    y_memmapped: bool,
    has_pyramid_resource: bool,
    force_bin2d: bool,
    force_pyramid: bool,
    color_mode: i32,
    x_min: f64,
    x_max: f64,
    y_min: f64,
    y_max: f64,
    xr0: f64,
    xr1: f64,
    yr0: f64,
    yr1: f64,
    x_c0: f64,
    x_c1: f64,
    y_c0: f64,
    y_c1: f64,
    n_points: u64,
) -> Option<DensityEmitMeta> {
    let bin_window = bin_window(
        x_linear, y_linear, xr0, xr1, yr0, yr1, x_c0, x_c1, y_c0, y_c1,
    )?;
    let full_identity = full_identity(
        categorical,
        compact_categorical,
        x_has_nulls,
        y_has_nulls,
        x_min,
        x_max,
        y_min,
        y_max,
        xr0,
        xr1,
        yr0,
        yr1,
    )?;
    let pyramid = pyramid_preflight(
        x_linear,
        y_linear,
        n_points,
        has_pyramid_resource,
        x_memmapped,
        y_memmapped,
        force_pyramid,
        force_bin2d,
    )?;
    let oversized = n_points > U32_MAX;
    let grid_path = if grid_from_pyramid {
        -1
    } else {
        grid_path(
            oversized,
            full_identity,
            point_overlay,
            compact_categorical,
            stratified_counts,
        )
    };
    let wasm_eligible = wasm_eligible(
        cartesian,
        x_linear,
        y_linear,
        color_mode,
        x_has_nulls,
        y_has_nulls,
        n_points,
    )?;
    let needs_pyramid_sample = grid_from_pyramid && point_overlay && !oversized;
    let overlay_omitted = if oversized {
        DENSITY_OVERLAY_ROWS_EXCEED_U32
    } else if !point_overlay {
        DENSITY_OVERLAY_STATIC_RASTER
    } else {
        DENSITY_OVERLAY_NONE
    };
    let visible_is_n_points = grid_from_pyramid || oversized || full_identity;
    let use_raw_range_bin2d = oversized;
    Some(DensityEmitMeta {
        grid_path,
        bin_window,
        full_identity,
        oversized,
        pyramid,
        wasm_eligible,
        needs_pyramid_sample,
        overlay_omitted,
        visible_is_n_points,
        use_raw_range_bin2d,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn full_identity_truth_table() {
        assert!(
            full_identity(false, false, false, false, 0.0, 1.0, 0.0, 1.0, 0.0, 2.0, 0.0, 2.0)
                .unwrap()
        );
        assert!(
            !full_identity(true, false, false, false, 0.0, 1.0, 0.0, 1.0, 0.0, 2.0, 0.0, 2.0)
                .unwrap()
        );
        assert!(
            full_identity(true, true, false, false, 0.0, 1.0, 0.0, 1.0, 0.0, 2.0, 0.0, 2.0)
                .unwrap()
        );
        assert!(
            !full_identity(false, false, true, false, 0.0, 1.0, 0.0, 1.0, 0.0, 2.0, 0.0, 2.0)
                .unwrap()
        );
        assert!(!full_identity(
            false, false, false, false, -1.0, 1.0, 0.0, 1.0, 0.0, 2.0, 0.0, 2.0
        )
        .unwrap());
    }

    #[test]
    fn density_color_classify_matches_host_table() {
        let mut color_mode = 0;
        let mut categorical = 0;
        let mut compact = 0;
        let mut stratified = 0;
        assert_eq!(
            density_color_classify(0, 0, 0, 0, &mut color_mode, &mut categorical, &mut compact, &mut stratified),
            1
        );
        assert_eq!(color_mode, DENSITY_COLOR_MODE_NONE);
        assert_eq!(categorical, 0);
        assert_eq!(
            density_color_classify(1, 0, 0, 0, &mut color_mode, &mut categorical, &mut compact, &mut stratified),
            1
        );
        assert_eq!(color_mode, DENSITY_COLOR_MODE_CONSTANT);
        assert_eq!(
            density_color_classify(2, 1, 1, 1, &mut color_mode, &mut categorical, &mut compact, &mut stratified),
            1
        );
        assert_eq!(color_mode, DENSITY_COLOR_MODE_OTHER);
        assert_eq!(categorical, 1);
        assert_eq!(compact, 1);
        assert_eq!(stratified, 1);
        assert_eq!(
            density_color_classify(2, 1, 1, 0, &mut color_mode, &mut categorical, &mut compact, &mut stratified),
            1
        );
        assert_eq!(stratified, 0);
        assert_eq!(
            density_color_classify(2, 1, 0, 0, &mut color_mode, &mut categorical, &mut compact, &mut stratified),
            1
        );
        assert_eq!(compact, 0);
        assert_eq!(density_color_classify(99, 0, 0, 0, &mut color_mode, &mut categorical, &mut compact, &mut stratified), 0);
    }

    #[test]
    fn density_trace_color_classify_matches_host_table() {
        let mut color_mode = 0;
        let mut categorical = 0;
        let mut compact = 0;
        let mut stratified = 0;
        assert_eq!(
            density_trace_color_classify(
                0,
                "",
                0,
                0,
                0,
                &mut color_mode,
                &mut categorical,
                &mut compact,
                &mut stratified,
            ),
            1
        );
        assert_eq!(color_mode, DENSITY_COLOR_MODE_NONE);
        assert_eq!(
            density_trace_color_classify(
                1,
                "constant",
                0,
                0,
                0,
                &mut color_mode,
                &mut categorical,
                &mut compact,
                &mut stratified,
            ),
            1
        );
        assert_eq!(color_mode, DENSITY_COLOR_MODE_CONSTANT);
        assert_eq!(
            density_trace_color_classify(
                1,
                "categorical",
                1,
                1,
                1,
                &mut color_mode,
                &mut categorical,
                &mut compact,
                &mut stratified,
            ),
            1
        );
        assert_eq!(categorical, 1);
        assert_eq!(stratified, 1);
        assert_eq!(
            density_trace_color_classify(
                1,
                "direct_rgba",
                0,
                0,
                0,
                &mut color_mode,
                &mut categorical,
                &mut compact,
                &mut stratified,
            ),
            1
        );
        assert_eq!(color_mode, DENSITY_COLOR_MODE_OTHER);
        assert_eq!(density_trace_color_classify(2, "constant", 0, 0, 0, &mut color_mode, &mut categorical, &mut compact, &mut stratified), 0);
    }

    #[test]
    fn bin_coord_endpoints_matches_host_linear_nonlinear() {
        let mut x_c0 = 0.0;
        let mut x_c1 = 0.0;
        let mut y_c0 = 0.0;
        let mut y_c1 = 0.0;
        assert_eq!(
            bin_coord_endpoints(
                true,
                false,
                0.0,
                10.0,
                1.0,
                9.0,
                2.0,
                8.0,
                3.0,
                7.0,
                &mut x_c0,
                &mut x_c1,
                &mut y_c0,
                &mut y_c1,
            ),
            1
        );
        assert_eq!((x_c0, x_c1), (0.0, 10.0));
        assert_eq!((y_c0, y_c1), (3.0, 7.0));
    }

    #[test]
    fn density_uses_channel_colormap_matches_host_table() {
        assert_eq!(density_uses_channel_colormap(0, "constant"), 0);
        assert_eq!(density_uses_channel_colormap(1, "constant"), 1);
        assert_eq!(density_uses_channel_colormap(1, "continuous"), 1);
        assert_eq!(density_uses_channel_colormap(1, "categorical"), 0);
        assert_eq!(density_uses_channel_colormap(1, "direct_rgba"), 0);
        assert_eq!(density_uses_channel_colormap(2, "constant"), 0);
    }

    #[test]
    fn density_constant_color_wire_admit_matches_host_table() {
        assert_eq!(density_constant_color_wire_admit(0, "constant", 1), 0);
        assert_eq!(density_constant_color_wire_admit(1, "constant", 0), 0);
        assert_eq!(density_constant_color_wire_admit(1, "constant", 1), 1);
        assert_eq!(density_constant_color_wire_admit(1, "continuous", 1), 0);
        assert_eq!(density_constant_color_wire_admit(1, "categorical", 1), 0);
    }

    #[test]
    fn density_wasm_source_admit_matches_host_and() {
        assert_eq!(density_wasm_source_admit(1, 1), 1);
        assert_eq!(density_wasm_source_admit(0, 1), 0);
        assert_eq!(density_wasm_source_admit(1, 0), 0);
        assert_eq!(density_wasm_source_admit(0, 0), 0);
    }

    #[test]
    fn density_reduction_kind_matches_host_prefix() {
        assert_eq!(density_reduction_kind("exact"), DENSITY_REDUCTION_BIN2D);
        assert_eq!(
            density_reduction_kind("pyramid-L2"),
            DENSITY_REDUCTION_PYRAMID_COUNT
        );
        assert_eq!(
            density_reduction_kind("pyramid-L0-tiles-upsampled"),
            DENSITY_REDUCTION_PYRAMID_COUNT
        );
    }

    #[test]
    fn density_overlay_omitted_wire_matches_host_policy() {
        let mut out = [0u8; 32];
        assert_eq!(
            density_overlay_omitted_wire(DENSITY_OVERLAY_ROWS_EXCEED_U32, true, &mut out),
            Some(15)
        );
        assert_eq!(&out[..15], b"rows_exceed_u32");
        assert_eq!(
            density_overlay_omitted_wire(DENSITY_OVERLAY_STATIC_RASTER, false, &mut out),
            Some(13)
        );
        assert_eq!(&out[..13], b"static_raster");
        assert_eq!(
            density_overlay_omitted_wire(DENSITY_OVERLAY_STATIC_RASTER, true, &mut out),
            Some(0)
        );
        assert_eq!(
            density_overlay_omitted_wire(DENSITY_OVERLAY_NONE, false, &mut out),
            Some(0)
        );
    }

    #[test]
    fn grid_path_truth_table() {
        assert_eq!(
            density_grid_path_identity_state(DENSITY_GRID_PATH_OVERSIZED_BIN2D),
            1
        );
        assert_eq!(
            density_grid_path_identity_state(DENSITY_GRID_PATH_IDENTITY_GRID_ONLY),
            1
        );
        assert_eq!(
            density_grid_path_identity_state(DENSITY_GRID_PATH_RANGE_INDICES),
            0
        );
        assert_eq!(density_grid_path_identity_state(99), -1);
        assert_eq!(
            grid_path(true, true, true, false, false),
            DENSITY_GRID_PATH_OVERSIZED_BIN2D
        );
        assert_eq!(
            grid_path(false, true, false, false, false),
            DENSITY_GRID_PATH_IDENTITY_GRID_ONLY
        );
        assert_eq!(
            grid_path(false, true, true, true, true),
            DENSITY_GRID_PATH_IDENTITY_STRATIFIED_FUSED
        );
        assert_eq!(
            grid_path(false, true, true, true, false),
            DENSITY_GRID_PATH_IDENTITY_STRATIFIED_SPLIT
        );
        assert_eq!(
            grid_path(false, true, true, false, false),
            DENSITY_GRID_PATH_IDENTITY_SAMPLE_FUSED
        );
        assert_eq!(
            grid_path(false, false, true, false, false),
            DENSITY_GRID_PATH_RANGE_INDICES
        );
    }

    #[test]
    fn format_binning_strings() {
        let mut out = [0u8; 32];
        assert_eq!(format_binning(true, 0, false, false, &mut out), Some(5));
        assert_eq!(&out[..5], b"exact");
        assert_eq!(format_binning(false, 2, false, false, &mut out), Some(10));
        assert_eq!(&out[..10], b"pyramid-L2");
        assert_eq!(format_binning(false, 1, true, true, &mut out), Some(26));
        assert_eq!(&out[..26], b"pyramid-L1-tiles-upsampled");
    }

    #[test]
    fn pyramid_preflight_no_rescan_and_upsample() {
        let small = pyramid_preflight(
            true,
            true,
            PYRAMID_MIN_POINTS,
            true,
            false,
            false,
            false,
            false,
        )
        .unwrap();
        assert!(small.eligible);
        assert!(small.attempt);
        assert!(!small.no_rescan);
        assert_eq!(small.max_upsample, PYRAMID_BOUNDED_UPSAMPLE);
        assert_eq!(small.tile_upsample, PYRAMID_UNBOUNDED_UPSAMPLE);

        let huge = pyramid_preflight(
            true,
            true,
            PYRAMID_NO_RESCAN_ROWS + 1,
            false,
            false,
            false,
            false,
            false,
        )
        .unwrap();
        assert!(huge.eligible);
        assert!(!huge.attempt);
        assert!(huge.no_rescan);
        assert_eq!(huge.max_upsample, PYRAMID_UNBOUNDED_UPSAMPLE);
    }

    #[test]
    fn wasm_eligible_constant_only() {
        assert!(wasm_eligible(
            true,
            true,
            true,
            DENSITY_COLOR_MODE_CONSTANT,
            false,
            false,
            100,
        )
        .unwrap());
        assert!(!wasm_eligible(
            true,
            true,
            true,
            DENSITY_COLOR_MODE_OTHER,
            false,
            false,
            100,
        )
        .unwrap());
        assert!(!wasm_eligible(
            false,
            true,
            true,
            DENSITY_COLOR_MODE_NONE,
            false,
            false,
            100,
        )
        .unwrap());
    }
}
