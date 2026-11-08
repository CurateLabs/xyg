//! Exact temporal catalog lowering. Timestamp arithmetic precedes float projection (§16).
use crate::scene::{
    linear_fraction, AxisScale, PlotLayout, ScaleKind, SceneBatch, SceneChromeStyle,
    SceneChromeText,
};
use crate::temporal::{TemporalError, TemporalPrecision};

#[path = "temporal_scene_dense.rs"]
mod dense;
#[path = "temporal_scene_jobs.rs"]
pub mod jobs;

pub const MAX_BYTES: usize = 64 * 1024 * 1024;

/// XYTM v1: fixed 128-byte header, UTF-8 zone/title, then 40-byte source rows.
/// All time fields are signed UTC microseconds; no timestamp passes through f64.
pub fn compile(bytes: &[u8], budget: usize) -> Result<Vec<u8>, TemporalError> {
    if bytes.get(..4) == Some(b"XYTJ") {
        return jobs::execute(bytes, budget);
    }
    check(bytes, budget)?;
    use TemporalError::InvalidArgument as Bad;
    let u = |i| dense::u(bytes, i);
    let t = |i| dense::t(bytes, i);
    let f = |i| dense::f(bytes, i);
    let (kind, n, width, height, lo, hi, zone_len, title_len) = (
        u(8),
        u(12) as usize,
        f(16),
        f(24),
        t(32),
        t(40),
        u(56) as usize,
        u(60) as usize,
    );
    if u(4) == 2 {
        return dense::compile(bytes, budget);
    }
    let zone = std::str::from_utf8(&bytes[128..128 + zone_len]).map_err(|_| Bad)?;
    // Calendar formatting currently supports UTC only. Never infer a local zone.
    if zone != "UTC" {
        return Err(TemporalError::UnitUnsupported);
    }
    std::str::from_utf8(&bytes[128 + zone_len..128 + zone_len + title_len]).map_err(|_| Bad)?;
    let (min, max) = dense::validate(bytes)?;
    let plot_width = width - 89.0;
    let plot_height = height - 96.0;
    let project =
        |v: i64| ((v as i128 - lo as i128) as f64 / (hi as i128 - lo as i128) as f64) * plot_width;
    // Negating the axis preserves the ordinary (max-v)/(max-min) operation
    // order while sharing Scene's overflow-safe finite-domain projection.
    let y = |v: f64| linear_fraction(-v, -max, -min) * plot_height;
    let mut kinds = Vec::new();
    let mut out_ids = Vec::new();
    let mut x0 = Vec::new();
    let mut y0 = Vec::new();
    let mut x1 = Vec::new();
    let mut y1 = Vec::new();
    let mut sizes = Vec::new();
    let mut refs = Vec::new();
    for i in 0..n {
        let at = 128 + zone_len + title_len + i * 40;
        let start = t(at);
        let end = t(at + 8);
        let value = f(at + 16);
        let id = dense::t(bytes, at + 24) as u64;
        let sv = bytes[at + 32];
        let ev = bytes[at + 33];
        if kind == 3 && sv == 0 {
            kinds.push(0);
            out_ids.push(id);
            refs.push(1);
            x0.push(-1.0);
            y0.push(-1.0);
            x1.push(0.0);
            y1.push(0.0);
            sizes.push(0.0);
            continue;
        }
        let interval = kind == 1 || kind == 2;
        if interval {
            if (ev != 0 && end <= lo) || (sv != 0 && start >= hi) {
                continue;
            }
        } else if sv == 0 || (kind != 3 && (start < lo || start >= hi)) {
            continue;
        }
        let mut a = if interval && sv == 0 {
            lo
        } else {
            start.max(lo)
        };
        let mut ordinate = y(value);
        if kind == 3 {
            let neighbor = if start < lo {
                if i + 1 == n || bytes[at + 40 + 32] == 0 || t(at + 40) < lo {
                    continue;
                }
                Some((at, at + 40, lo))
            } else if start >= hi {
                if i == 0 || bytes[at - 40 + 32] == 0 || t(at - 40) >= hi {
                    continue;
                }
                Some((at - 40, at, hi))
            } else {
                None
            };
            if let Some((left, right, edge)) = neighbor {
                ordinate = interpolate(
                    t(left) as i128,
                    t(right) as i128,
                    y(f(left + 16)),
                    y(f(right + 16)),
                    edge as i128,
                );
                a = edge;
            }
        }
        let b = if ev == 0 { hi } else { end.min(hi) };
        kinds.push(if interval || kind == 4 {
            2
        } else if kind == 3 {
            1
        } else {
            0
        });
        refs.push(0);
        out_ids.push(id);
        x0.push(project(a));
        y0.push(if interval {
            ordinate - 4.0
        } else if kind == 4 {
            ordinate.min(y(0.0))
        } else {
            ordinate
        });
        x1.push(if interval {
            project(b)
        } else if kind == 4 {
            project(a) + 6.0
        } else {
            0.0
        });
        y1.push(if interval {
            ordinate + 4.0
        } else if kind == 4 {
            ordinate.max(y(0.0))
        } else {
            0.0
        });
        sizes.push(if kind == 0 || kind == 5 { 6.0 } else { 0.0 });
    }
    paint(
        bytes, budget, &kinds, &out_ids, &refs, &sizes, &x0, &y0, &x1, &y1,
    )
}

#[inline(never)]
fn check(bytes: &[u8], budget: usize) -> Result<(), TemporalError> {
    check_frame(bytes, budget, bytes.len())
}
fn check_frame(bytes: &[u8], budget: usize, wire_len: usize) -> Result<(), TemporalError> {
    use TemporalError::{BudgetExceeded as Limit, InvalidArgument as Bad};
    if bytes.len() < 128 || wire_len > budget || budget > MAX_BYTES {
        return Err(Limit);
    }
    let u = |i| dense::u(bytes, i);
    let t = |i| dense::t(bytes, i);
    let f = |i| dense::f(bytes, i);
    if &bytes[..4] != b"XYTM"
        || !(1..=2).contains(&u(4))
        || u(8) > 5
        || (u(4) == 1 && bytes[88..128].iter().any(|&v| v != 0))
    {
        return Err(Bad);
    }
    let n = u(12) as usize;
    let width = f(16);
    let height = f(24);
    let lo = t(32);
    let hi = t(40);
    let cursor = t(48);
    let zone_len = u(56) as usize;
    let title_len = u(60) as usize;
    TemporalPrecision::from_u32(u(64)).ok_or(Bad)?;
    let size = 128usize
        .checked_add(zone_len)
        .and_then(|v| v.checked_add(title_len))
        .and_then(|v| n.checked_mul(40).and_then(|r| v.checked_add(r)))
        .ok_or(Limit)?;
    if size != wire_len
        || zone_len > 128
        || title_len > 4096
        || lo >= hi
        || cursor < lo
        || cursor >= hi
        || !(160.0..=16384.0).contains(&width)
        || !(120.0..=16384.0).contains(&height)
    {
        return Err(Bad);
    }
    // Direct tier is intentionally bounded and refuses rather than silently sampling.
    if u(4) == 1
        && (n > (width as usize) * 4
            || n.checked_mul(1024)
                .and_then(|v| v.checked_add(size * 3 + 65536))
                .is_none_or(|v| v > budget))
    {
        return Err(Limit);
    }
    Ok(())
}

/// Interpolate bounded projected ordinates, subtracting exact time first.
#[inline(never)]
fn interpolate(a: i128, b: i128, ya: f64, yb: f64, edge: i128) -> f64 {
    if a == b {
        return ya;
    }
    ya + (yb - ya) * ((edge - a) as f64 / (b - a) as f64)
}

#[allow(clippy::too_many_arguments)]
fn paint(
    bytes: &[u8],
    budget: usize,
    kinds: &[u8],
    out_ids: &[u64],
    refs: &[u32],
    sizes: &[f64],
    x0: &[f64],
    y0: &[f64],
    x1: &[f64],
    y1: &[f64],
) -> Result<Vec<u8>, TemporalError> {
    use TemporalError::{BudgetExceeded as Limit, InvalidArgument as Bad};
    let f = |i| dense::f(bytes, i);
    let t = |i| dense::t(bytes, i);
    let u = |i| dense::u(bytes, i) as usize;
    let (width, height, lo, hi, cursor) = (f(16), f(24), t(32), t(40), t(48));
    let title = std::str::from_utf8(&bytes[128 + u(56)..128 + u(56) + u(60)]).map_err(|_| Bad)?;
    let layout = PlotLayout::new(width, height, 65.0, 24.0, 48.0, 48.0).map_err(|_| Bad)?;
    let (plot_width, plot_height) = (width - 89.0, height - 96.0);
    let project =
        |v: i64| ((v as i128 - lo as i128) as f64 / (hi as i128 - lo as i128) as f64) * plot_width;
    let count = kinds.len();
    let symbols = vec![0; count];
    let scale_x = AxisScale::new(
        ScaleKind::Linear,
        0.0,
        plot_width,
        65.0,
        width - 24.0,
        1.0,
        false,
    )
    .map_err(|_| Bad)?;
    let scale_y = AxisScale::new(
        ScaleKind::Linear,
        0.0,
        plot_height,
        48.0,
        height - 48.0,
        1.0,
        false,
    )
    .map_err(|_| Bad)?;
    let mut chrome = SceneChromeStyle::default();
    let ticks = temporal_ticks(lo, hi, 6);
    chrome.x_major_ticks = Some(ticks.iter().map(|&v| project(v)).collect());
    chrome.x_tick_labels = Some(ticks.iter().map(|&v| format_time(v)).collect());
    chrome.y_major_ticks = Some(Vec::new());
    let text = SceneChromeText::from_parts(
        title,
        &format!("UTC · cursor {cursor} µs · [{lo}, {hi})"),
        "",
    )
    .map_err(|_| Bad)?;
    let scene = SceneBatch::new_with_chrome_literal_ids(
        layout,
        1,
        2,
        scale_x,
        scale_y,
        chrome,
        text,
        &kinds,
        &out_ids,
        &refs,
        &[bytes[72], bytes[73], bytes[74], bytes[75], 0, 0, 0, 0],
        &[bytes[76], bytes[77], bytes[78], bytes[79], 0, 0, 0, 0],
        &[f(80), 0.0],
        &sizes,
        &symbols,
        &x0,
        &y0,
        &x1,
        &y1,
    )
    .map_err(|_| Bad)?
    .encode();
    if scene.len() > budget {
        return Err(Limit);
    }
    Ok(scene)
}

/// Exact integer ticks across the entire signed i64 domain. These are elapsed
/// microsecond ticks, explicitly not approximate calendar-month ticks.
pub fn integer_ticks(lo: i64, hi: i64, target: usize) -> Vec<i64> {
    if lo >= hi || target == 0 || target > 1024 {
        return Vec::new();
    }
    let span = hi as i128 - lo as i128;
    let step = ((span + target as i128 - 1) / target as i128).max(1);
    (0..=target)
        .map(|i| lo as i128 + i as i128 * step)
        .filter(|&v| v <= hi as i128)
        .map(|v| v as i64)
        .collect()
}

const DAY: i128 = 86_400_000_000;
fn civil(t: i64) -> (i128, i128, i128) {
    // A full i64 microsecond timestamp has fewer than 107 million days.
    let (year, month, day) =
        crate::calendar::civil_from_shifted_days(t.div_euclid(DAY as i64) + 719468);
    (year as i128, month as i128, day as i128)
}
fn month_start(year: i128, month: i128) -> i128 {
    crate::calendar::month_days(year as i64, month as i64) as i128 * DAY
}

fn format_time(t: i64) -> String {
    let (y, m, d) = civil(t);
    // i64 microseconds span fewer than 300,000 civil years. Only formatting
    // narrows these bounded fields, sharing the ordinary integer formatter.
    let (y, m, d) = (y as i64, m as u64, d as u64);
    let us = (t as i128).rem_euclid(DAY) as u64;
    format!(
        "{y:04}-{m:02}-{d:02} {:02}:{:02}:{:02}.{:06}Z",
        us / 3600000000,
        us / 60000000 % 60,
        us / 1000000 % 60,
        us % 1000000
    )
}
/// Long-range ticks advance Gregorian month indices, never 30-day durations.
pub fn temporal_ticks(lo: i64, hi: i64, target: usize) -> Vec<i64> {
    if lo >= hi || target == 0 || target > 1024 {
        return Vec::new();
    }
    if hi as i128 - (lo as i128) < DAY * 28 {
        return integer_ticks(lo, hi, target);
    }
    let (ly, lm, _) = civil(lo);
    let (hy, hm, _) = civil(hi);
    let months = (hy - ly) * 12 + hm - lm + 1;
    let step = ((months + target as i128 - 1) / target as i128).max(1);
    let mut index = ly * 12 + lm - 1;
    let mut out = Vec::new();
    for _ in 0..=target + 1 {
        let t = month_start(index.div_euclid(12), index.rem_euclid(12) + 1);
        if t > hi as i128 {
            break;
        }
        if t >= lo as i128 {
            out.push(t as i64);
        }
        index += step;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    fn line_request(rows: &[(Option<i64>, f64)], lo: i64, hi: i64) -> Vec<u8> {
        let mut request = vec![0; 128];
        request[..4].copy_from_slice(b"XYTM");
        for (offset, value) in [(4, 1u32), (8, 3), (12, rows.len() as u32), (56, 3), (64, 2)] {
            request[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
        }
        for (offset, value) in [(16, 900f64), (24, 420.), (80, 1.)] {
            request[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        }
        for (offset, value) in [(32, lo), (40, hi), (48, lo)] {
            request[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        }
        request[72..80].copy_from_slice(&[31, 119, 180, 255, 31, 119, 180, 255]);
        request.extend_from_slice(b"UTC");
        for (i, &(time, value)) in rows.iter().enumerate() {
            request.extend_from_slice(&time.unwrap_or(0).to_le_bytes());
            request.extend_from_slice(&0i64.to_le_bytes());
            request.extend_from_slice(&value.to_le_bytes());
            request.extend_from_slice(&(i as u64 + 42).to_le_bytes());
            request.extend_from_slice(&[u8::from(time.is_some()), 0, 0, 0, 0, 0, 0, 0]);
        }
        request
    }
    #[test]
    fn line_clips_adjacent_window_support_and_keeps_null_breaks() {
        let request = line_request(&[(Some(-1), 0.), (Some(11), 12.)], 0, 10);
        let bytes = compile(&request, MAX_BYTES).unwrap();
        let scene = crate::scene::SceneDocument::decode(&bytes).unwrap();
        assert_eq!(scene.record_count(), 2);
        assert!(scene.to_svg().contains("points=\"65,345 876,75\""));
        let request = line_request(&[(Some(-1), 0.), (None, 6.), (Some(11), 12.)], 0, 10);
        let bytes = compile(&request, MAX_BYTES).unwrap();
        let scene = crate::scene::SceneDocument::decode(&bytes).unwrap();
        assert_eq!(scene.record_count(), 1);
        assert!(!scene.to_svg().contains("<polyline"));
    }
    #[test]
    fn line_window_interpolation_handles_extreme_integer_times_and_values() {
        for values in [[0., 12.], [-f64::MAX, f64::MAX]] {
            let request = line_request(
                &[(Some(i64::MIN), values[0]), (Some(i64::MAX), values[1])],
                -1,
                1,
            );
            let bytes = compile(&request, MAX_BYTES).unwrap();
            let scene = crate::scene::SceneDocument::decode(&bytes).unwrap();
            assert_eq!(scene.record_count(), 2);
            let svg = scene.to_svg();
            assert!(svg.contains("points=\"65,210 876,210\""));
            assert!(!svg.contains("NaN") && !svg.contains("Infinity"));
        }
    }

    #[test]
    fn extreme_finite_values_remain_visible() {
        for extent in [1e308, f64::MAX] {
            for kind in 0u32..6 {
                let mut request = vec![0; 128];
                request[..4].copy_from_slice(b"XYTM");
                request[4..8].copy_from_slice(&1u32.to_le_bytes());
                request[8..12].copy_from_slice(&kind.to_le_bytes());
                request[12..16].copy_from_slice(&3u32.to_le_bytes());
                request[16..24].copy_from_slice(&900f64.to_le_bytes());
                request[24..32].copy_from_slice(&420f64.to_le_bytes());
                request[40..48].copy_from_slice(&10i64.to_le_bytes());
                request[56..60].copy_from_slice(&3u32.to_le_bytes());
                request[64..68].copy_from_slice(&2u32.to_le_bytes());
                request[72..80].copy_from_slice(&[31, 119, 180, 255, 31, 119, 180, 255]);
                request[80..88].copy_from_slice(&1f64.to_le_bytes());
                request.extend_from_slice(b"UTC");
                for (i, value) in [-extent, 0.0, extent].iter().enumerate() {
                    request.extend_from_slice(&(i as i64 + 1).to_le_bytes());
                    request.extend_from_slice(&(i as i64 + 2).to_le_bytes());
                    request.extend_from_slice(&value.to_le_bytes());
                    request.extend_from_slice(&(i as u64 + 1).to_le_bytes());
                    request.extend_from_slice(&[1, 1, 0, 0, 0, 0, 0, 0]);
                }
                let scene = compile(&request, MAX_BYTES).unwrap();
                let svg = crate::scene::SceneDocument::decode(&scene)
                    .unwrap()
                    .to_svg();
                assert!(!svg.contains("NaN") && !svg.contains("Infinity"));
                if kind == 0 || kind == 5 {
                    assert_eq!(svg.matches("<circle ").count(), 3);
                    for cy in [372, 210, 48] {
                        assert!(svg.contains(&format!("cy=\"{cy}\"")));
                    }
                }
            }
        }
    }

    #[test]
    fn gregorian_ticks_and_pre_epoch_labels() {
        assert_eq!(
            temporal_ticks(0, 90 * DAY as i64, 4),
            vec![0, 31 * DAY as i64, 59 * DAY as i64, 90 * DAY as i64]
        );
        assert_eq!(format_time(-1), "1969-12-31 23:59:59.999999Z");
        let ticks = temporal_ticks(1580515200000000, 1585699200000000, 3);
        assert_eq!(ticks[1] - ticks[0], 29 * DAY as i64);
    }
    #[test]
    fn exact_ticks() {
        let lo = i64::MAX - 10;
        assert_eq!(
            integer_ticks(lo, i64::MAX, 5),
            vec![lo, lo + 2, lo + 4, lo + 6, lo + 8, lo + 10]
        );
        assert_eq!(integer_ticks(-3, 3, 6), vec![-3, -2, -1, 0, 1, 2, 3]);
        assert_eq!(
            integer_ticks(i64::MIN, i64::MAX, 1),
            vec![i64::MIN, i64::MAX]
        );
    }
}
