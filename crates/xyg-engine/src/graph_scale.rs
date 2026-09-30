//! Graph color scales beyond linear and categorical (#34): ordinal colors
//! sampled from a built-in colormap and diverging domains centered on a
//! midpoint. Hosts only map values onto the returned colors or domain.

use crate::colormap::{colormap_is_builtin, colormap_named_stops};
use crate::kernels::colormap_color;

/// Largest ordinal scale (the client palette texture is 256 wide).
pub const MAX_ORDINAL_LEVELS: usize = 256;

/// `k` evenly spaced colors from a built-in colormap: level `i` samples
/// `t = i / (k - 1)` exactly as the continuous LUT does (a single level
/// samples the midpoint). `None` for unknown colormaps or out-of-range `k`.
pub fn ordinal_colors(colormap: &str, k: usize) -> Option<Vec<[u8; 3]>> {
    if !(1..=MAX_ORDINAL_LEVELS).contains(&k) || !colormap_is_builtin(colormap) {
        return None;
    }
    let stops = colormap_named_stops(colormap);
    Some(
        (0..k)
            .map(|i| {
                let t = if k == 1 {
                    0.5
                } else {
                    i as f64 / (k - 1) as f64
                };
                let rgba = colormap_color(t, &stops, 255);
                [rgba[0], rgba[1], rgba[2]]
            })
            .collect(),
    )
}

/// Continuous domain symmetric about `midpoint` that covers every finite
/// value, so the midpoint maps to the colormap center. A degenerate spread
/// widens to `midpoint ± 1`. `None` without a finite midpoint or value.
pub fn diverging_domain(values: &[f64], midpoint: f64) -> Option<(f64, f64)> {
    if !midpoint.is_finite() {
        return None;
    }
    let radius = values
        .iter()
        .filter(|v| v.is_finite())
        .map(|v| (v - midpoint).abs())
        .fold(None, |acc: Option<f64>, r| {
            Some(acc.map_or(r, |a| a.max(r)))
        })?;
    let radius = if radius > 0.0 && radius.is_finite() {
        radius
    } else {
        1.0
    };
    Some((midpoint - radius, midpoint + radius))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ordinal_colors_sample_the_continuous_ramp() {
        let colors = ordinal_colors("viridis", 3).unwrap();
        let stops = colormap_named_stops("viridis");
        assert_eq!(colors[0], stops[0]);
        assert_eq!(colors[2], stops[stops.len() - 1]);
        let mid = colormap_color(0.5, &stops, 255);
        assert_eq!(colors[1], [mid[0], mid[1], mid[2]]);
        assert_eq!(ordinal_colors("viridis", 1).unwrap()[0], colors[1]);
        assert!(ordinal_colors("not-a-map", 3).is_none());
        assert!(ordinal_colors("viridis", 0).is_none());
        assert!(ordinal_colors("viridis", 257).is_none());
        assert_eq!(ordinal_colors("viridis_r", 3).unwrap()[0], colors[2]);
    }

    #[test]
    fn diverging_domain_is_symmetric_about_the_midpoint() {
        assert_eq!(
            diverging_domain(&[-2.0, 5.0, f64::NAN], 1.0),
            Some((-3.0, 5.0))
        );
        assert_eq!(diverging_domain(&[0.0, 0.0], 0.0), Some((-1.0, 1.0)));
        assert_eq!(diverging_domain(&[f64::NAN], 0.0), None);
        assert_eq!(diverging_domain(&[1.0], f64::INFINITY), None);
    }
}
