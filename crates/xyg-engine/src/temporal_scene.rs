//! Exact temporal catalog lowering. Timestamp arithmetic precedes float projection (§16).
use crate::scene::{
    linear_fraction, AxisScale, PlotLayout, ScaleKind, SceneBatch, SceneChromeStyle, SceneChromeText,
};
use crate::temporal::{TemporalColumn, TemporalError, TemporalPrecision};

pub const MAX_BYTES: usize = 64 * 1024 * 1024;

/// XYTM v1: fixed 128-byte header, UTF-8 zone/title, then 40-byte source rows.
/// All time fields are signed UTC microseconds; no timestamp passes through f64.
pub fn compile(bytes: &[u8], budget: usize) -> Result<Vec<u8>, TemporalError> {
    use TemporalError::{BudgetExceeded as Limit, InvalidArgument as Bad};
    if bytes.len() < 128 || bytes.len() > budget || budget > MAX_BYTES {
        return Err(Limit);
    }
    let u = |i| u32::from_le_bytes(bytes[i..i + 4].try_into().unwrap());
    let t = |i| i64::from_le_bytes(bytes[i..i + 8].try_into().unwrap());
    let f = |i| f64::from_le_bytes(bytes[i..i + 8].try_into().unwrap());
    if &bytes[..4] != b"XYTM" || u(4) != 1 || u(8) > 5 || bytes[88..128].iter().any(|&v| v != 0) {
        return Err(Bad);
    }
    let kind = u(8);
    let n = u(12) as usize;
    let width = f(16);
    let height = f(24);
    let lo = t(32);
    let hi = t(40);
    let cursor = t(48);
    let zone_len = u(56) as usize;
    let title_len = u(60) as usize;
    let precision = TemporalPrecision::from_u32(u(64)).ok_or(Bad)?;
    let size = 128usize
        .checked_add(zone_len)
        .and_then(|v| v.checked_add(title_len))
        .and_then(|v| n.checked_mul(40).and_then(|r| v.checked_add(r)))
        .ok_or(Limit)?;
    if size != bytes.len()
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
    if n > (width as usize) * 4
        || n.checked_mul(1024)
            .and_then(|v| v.checked_add(size * 3 + 65536))
            .is_none_or(|v| v > budget)
    {
        return Err(Limit);
    }
    let zone = std::str::from_utf8(&bytes[128..128 + zone_len]).map_err(|_| Bad)?;
    // Calendar formatting currently supports UTC only. Never infer a local zone.
    if zone != "UTC" {
        return Err(TemporalError::UnitUnsupported);
    }
    let title =
        std::str::from_utf8(&bytes[128 + zone_len..128 + zone_len + title_len]).map_err(|_| Bad)?;
    let mut starts = Vec::with_capacity(n);
    let mut ends = Vec::with_capacity(n);
    let mut sv = Vec::with_capacity(n);
    let mut ev = Vec::with_capacity(n);
    let mut values = Vec::with_capacity(n);
    let mut ids = Vec::with_capacity(n);
    let mut unique = std::collections::HashSet::new();
    for i in 0..n {
        let at = 128 + zone_len + title_len + i * 40;
        starts.push(t(at));
        ends.push(t(at + 8));
        values.push(f(at + 16));
        let id = u64::from_le_bytes(bytes[at + 24..at + 32].try_into().unwrap());
        if !unique.insert(id)
            || bytes[at + 32] > 1
            || bytes[at + 33] > 1
            || bytes[at + 34..at + 40].iter().any(|&v| v != 0)
            || !values[i].is_finite()
        {
            return Err(Bad);
        }
        ids.push(id);
        sv.push(bytes[at + 32]);
        ev.push(bytes[at + 33]);
        if (kind == 1 || kind == 2) && sv[i] != 0 && ev[i] != 0 && starts[i] >= ends[i] {
            return Err(TemporalError::ReversedInterval);
        }
    }
    if kind == 3 {
        let mut previous = None;
        for i in 0..n {
            if sv[i] != 0 {
                if previous.is_some_and(|v| starts[i] < v) {
                    return Err(Bad);
                }
                previous = Some(starts[i]);
            }
        }
    }
    let source = TemporalColumn::from_utc_micros(&starts, &sv, zone, precision)?;
    let _end = TemporalColumn::from_utc_micros(&ends, &ev, zone, precision)?;
    let layout = PlotLayout::new(width, height, 65.0, 24.0, 48.0, 48.0).map_err(|_| Bad)?;
    let plot_width = width - 89.0;
    let plot_height = height - 96.0;
    let project =
        |v: i64| ((v as i128 - lo as i128) as f64 / (hi as i128 - lo as i128) as f64) * plot_width;
    let mut min = 0.0f64;
    let mut max = 1.0f64;
    for &v in &values {
        min = min.min(v);
        max = max.max(v);
    }
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
        if kind == 3 && sv[i] == 0 {
            kinds.push(0);
            out_ids.push(ids[i]);
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
            if (ev[i] != 0 && ends[i] <= lo) || (sv[i] != 0 && starts[i] >= hi) {
                continue;
            }
        } else if source.validity()[i] == 0 || starts[i] < lo || starts[i] >= hi {
            continue;
        }
        let a = if interval && sv[i] == 0 {
            lo
        } else {
            starts[i].max(lo)
        };
        let b = if ev[i] == 0 { hi } else { ends[i].min(hi) };
        kinds.push(if interval || kind == 4 {
            2
        } else if kind == 3 {
            1
        } else {
            0
        });
        refs.push(0);
        out_ids.push(ids[i]);
        x0.push(project(a));
        y0.push(if interval {
            y(values[i]) - 4.0
        } else if kind == 4 {
            y(values[i]).min(y(0.0))
        } else {
            y(values[i])
        });
        x1.push(if interval {
            project(b)
        } else if kind == 4 {
            project(a) + 6.0
        } else {
            0.0
        });
        y1.push(if interval {
            y(values[i]) + 4.0
        } else if kind == 4 {
            y(values[i]).max(y(0.0))
        } else {
            0.0
        });
        sizes.push(if kind == 0 || kind == 5 { 6.0 } else { 0.0 });
    }
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
    let z = (t as i128).div_euclid(DAY) + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let mut y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = mp + if mp < 10 { 3 } else { -9 };
    if m <= 2 {
        y += 1;
    }
    (y, m, d)
}
fn month_start(year: i128, month: i128) -> i128 {
    let y = year - if month <= 2 { 1 } else { 0 };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let mp = month + if month > 2 { -3 } else { 9 };
    (era * 146097 + yoe * 365 + yoe / 4 - yoe / 100 + (153 * mp + 2) / 5 - 719468) * DAY
}
fn format_time(t: i64) -> String {
    let (y, m, d) = civil(t);
    let us = (t as i128).rem_euclid(DAY);
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
                let svg = crate::scene::SceneDocument::decode(&scene).unwrap().to_svg();
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
