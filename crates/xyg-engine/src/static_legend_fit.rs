//! Measured pyplot best-legend policy (M2 #873; dossier §21/§28).
//!
//! Unlike composition's mean-occupancy heuristic, pyplot uses weighted vertex
//! counts, one extra point for path intersection, and exact candidate order.
use crate::legend_layout::{legend_box_layout, LegendBoxRequest};

const MAX_BYTES: usize = 64 * 1024 * 1024;
const MAX_TEXT: usize = 4096;
const MAX_ITEMS: usize = 4096;
pub const CANDIDATES: [&str; 9] = [
    "upper right",
    "upper left",
    "lower left",
    "lower right",
    "right",
    "center left",
    "lower center",
    "upper center",
    "center",
];
const ANCHORS: [(f64, f64); 9] = [
    (1.0, 1.0),
    (0.0, 1.0),
    (0.0, 0.0),
    (1.0, 0.0),
    (1.0, 0.5),
    (0.0, 0.5),
    (0.5, 0.0),
    (0.5, 1.0),
    (0.5, 0.5),
];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LegendFitError {
    Header,
    Version,
    Flags,
    Limit,
    Text,
    Facts,
    Entry,
}
impl LegendFitError {
    pub fn reason(self) -> &'static str {
        match self {
            Self::Header => "XYG_STATIC_LEGEND_HEADER",
            Self::Version => "XYG_STATIC_LEGEND_VERSION",
            Self::Flags => "XYG_STATIC_LEGEND_FLAGS",
            Self::Limit => "XYG_STATIC_LEGEND_LIMIT",
            Self::Text => "XYG_STATIC_LEGEND_TEXT",
            Self::Facts => "XYG_STATIC_LEGEND_FACTS",
            Self::Entry => "XYG_STATIC_UNSUPPORTED_LEGEND_FOOTPRINT",
        }
    }
}
type Result<T> = std::result::Result<T, LegendFitError>;

struct Reader<'a> {
    data: &'a [u8],
    at: usize,
}
impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8]> {
        let end = self.at.checked_add(n).ok_or(LegendFitError::Limit)?;
        let out = self.data.get(self.at..end).ok_or(LegendFitError::Header)?;
        self.at = end;
        Ok(out)
    }
    fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
    fn f64(&mut self) -> Result<f64> {
        Ok(f64::from_le_bytes(self.take(8)?.try_into().unwrap()))
    }
    fn text(&mut self, n: usize) -> Result<&'a str> {
        if n > MAX_TEXT {
            return Err(LegendFitError::Limit);
        }
        let bytes = self.take(n)?;
        if bytes.contains(&0) {
            return Err(LegendFitError::Text);
        }
        std::str::from_utf8(bytes).map_err(|_| LegendFitError::Text)
    }
    fn column(&mut self, n: usize) -> Result<Column<'a>> {
        Ok(Column(
            self.take(n.checked_mul(8).ok_or(LegendFitError::Limit)?)?,
        ))
    }
}
#[derive(Clone, Copy)]
struct Column<'a>(&'a [u8]);
impl Column<'_> {
    fn len(self) -> usize {
        self.0.len() / 8
    }
    fn get(self, i: usize) -> f64 {
        let at = i * 8;
        f64::from_le_bytes(self.0[at..at + 8].try_into().unwrap())
    }
    fn broadcast(self, i: usize, default: f64) -> f64 {
        if self.len() == 0 {
            default
        } else {
            self.get(if self.len() == 1 { 0 } else { i })
        }
    }
}
struct Entry<'a> {
    kind: u32,
    x: Column<'a>,
    y: Column<'a>,
    base: Column<'a>,
    width: Column<'a>,
}
fn broadcast_len(x: usize, y: usize) -> Result<usize> {
    if x == y {
        Ok(x)
    } else if x == 1 {
        Ok(y)
    } else if y == 1 {
        Ok(x)
    } else {
        Err(LegendFitError::Entry)
    }
}
fn optional_column(n: usize, target: usize) -> bool {
    n == 0 || n == 1 || n == target
}
fn css_number(raw: &str, suffix: &str, default: f64, floor: f64) -> f64 {
    raw.trim()
        .strip_suffix(suffix)
        .and_then(|v| v.trim().parse::<f64>().ok())
        .filter(|v| v.is_finite())
        .map(|v| v.max(floor))
        .unwrap_or(default)
}
fn inside(p: (f64, f64), b: [f64; 4]) -> bool {
    p.0 > b[0] && p.0 < b[1] && p.1 > b[2] && p.1 < b[3]
}
fn finite(p: (f64, f64)) -> bool {
    p.0.is_finite() && p.1.is_finite()
}
fn intersects(a: (f64, f64), z: (f64, f64), b: [f64; 4]) -> bool {
    if !finite(a)
        || !finite(z)
        || a.0.max(z.0) < b[0]
        || a.0.min(z.0) > b[1]
        || a.1.max(z.1) < b[2]
        || a.1.min(z.1) > b[3]
    {
        return false;
    }
    let contains = |p: (f64, f64)| p.0 >= b[0] && p.0 <= b[1] && p.1 >= b[2] && p.1 <= b[3];
    if contains(a) || contains(z) {
        return true;
    }
    let dx = z.0 - a.0;
    let dy = z.1 - a.1;
    if dx != 0.0 {
        for edge in [b[0], b[1]] {
            let t = (edge - a.0) / dx;
            if (0.0..=1.0).contains(&t) && (b[2]..=b[3]).contains(&(a.1 + t * dy)) {
                return true;
            }
        }
    }
    if dy != 0.0 {
        for edge in [b[2], b[3]] {
            let t = (edge - a.1) / dy;
            if (0.0..=1.0).contains(&t) && (b[0]..=b[1]).contains(&(a.0 + t * dx)) {
                return true;
            }
        }
    }
    false
}

/// Resolve a bounded XYLF request into an XYLR layout/scoring witness.
pub fn resolve_packed(data: &[u8]) -> Result<Vec<u8>> {
    if data.len() > MAX_BYTES {
        return Err(LegendFitError::Limit);
    }
    let mut r = Reader { data, at: 0 };
    if r.take(4)? != b"XYLF" {
        return Err(LegendFitError::Header);
    }
    if r.u32()? != 1 {
        return Err(LegendFitError::Version);
    }
    let flags = r.u32()?;
    let name_count = r.u32()? as usize;
    let entry_count = r.u32()? as usize;
    let ncols = r.u32()?;
    let mut lengths = [0; 4];
    for n in &mut lengths {
        *n = r.u32()? as usize;
    }
    if flags & !31 != 0 || r.u32()? != 0 || r.u32()? != 0 {
        return Err(LegendFitError::Flags);
    }
    if name_count > MAX_ITEMS || entry_count > MAX_ITEMS || ncols > MAX_ITEMS as u32 {
        return Err(LegendFitError::Limit);
    }
    let mut v = [0.0; 12];
    for value in &mut v {
        *value = r.f64()?;
    }
    if v.iter().any(|x| !x.is_finite())
        || v[2] <= 0.0
        || v[3] <= 0.0
        || v[..4].iter().any(|x| x.abs() > 65535.0)
        || v[8..].iter().any(|x| x.abs() > 65535.0)
    {
        return Err(LegendFitError::Facts);
    }
    for i in 0..3 {
        if flags & (4 << i) == 0 && v[8 + i].to_bits() != 0 {
            return Err(LegendFitError::Facts);
        }
    }
    let title = r.text(lengths[0])?;
    let font = css_number(r.text(lengths[1])?, "px", 11.0, 1.0);
    let padding = css_number(r.text(lengths[2])?, "em", 0.4, 0.0);
    let row_gap = css_number(r.text(lengths[3])?, "em", 0.5, 0.0);
    if [font, padding, row_gap].iter().any(|x| *x > 65535.0) {
        return Err(LegendFitError::Limit);
    }
    let mut names = Vec::with_capacity(name_count.max(1));
    for _ in 0..name_count {
        let n = r.u32()? as usize;
        names.push(r.text(n)?);
    }
    if names.is_empty() {
        names.push("");
    }
    let mut entries = Vec::with_capacity(entry_count);
    for _ in 0..entry_count {
        let kind = r.u32()?;
        let mut counts = [0; 4];
        for n in &mut counts {
            *n = r.u32()? as usize;
        }
        if r.u32()? != 0 {
            return Err(LegendFitError::Flags);
        }
        if kind > 6 {
            return Err(LegendFitError::Entry);
        }
        let x = r.column(counts[0])?;
        let y = r.column(counts[1])?;
        let base = r.column(counts[2])?;
        let width = r.column(counts[3])?;
        match kind {
            4 if x.len() != y.len() + 1 || base.len() != 0 || width.len() != 0 => {
                return Err(LegendFitError::Entry)
            }
            5 if y.len() != 0 || base.len() != 0 || width.len() != 0 => {
                return Err(LegendFitError::Entry)
            }
            4 | 5 => {}
            _ => {
                let n = broadcast_len(x.len(), y.len())?;
                if !optional_column(base.len(), n)
                    || !optional_column(width.len(), n)
                    || (kind < 2 && (base.len() != 0 || width.len() != 0))
                    || (kind == 6 && width.len() != 0)
                {
                    return Err(LegendFitError::Entry);
                }
            }
        }
        entries.push(Entry {
            kind,
            x,
            y,
            base,
            width,
        });
    }
    if r.at != data.len() {
        return Err(LegendFitError::Header);
    }
    let layout = legend_box_layout(LegendBoxRequest {
        plot_x: 0.0,
        plot_y: 0.0,
        plot_w: v[2],
        plot_h: v[3],
        names: &names,
        title: if title.is_empty() { None } else { Some(title) },
        loc: "upper right",
        font_size: font,
        handlelength: (flags & 4 != 0).then_some(v[8]),
        handletextpad: (flags & 8 != 0).then_some(v[9]),
        handleheight: (flags & 16 != 0).then_some(v[10]),
        ncols: ncols.max(1),
        padding_em: padding,
        row_gap_em: row_gap,
        anchor: None,
        border_axes_pad: v[11].max(0.0),
    })
    .ok_or(LegendFitError::Facts)?;
    let bw = layout.box_w / v[2];
    let bh = layout.box_h / v[3];
    let px = v[11].max(0.0) / v[2];
    let py = v[11].max(0.0) / v[3];
    let sx = (1.0 - 2.0 * px - bw).max(0.0);
    let sy = (1.0 - 2.0 * py - bh).max(0.0);
    let boxes = ANCHORS.map(|(hx, vy)| {
        let x = px + hx * sx;
        let y = py + vy * sy;
        [x, x + bw, y, y + bh]
    });
    let mut scores = [0.0; 9];
    let mut used = 0u32;
    let xlo = v[4].min(v[5]);
    let xhi = v[4].max(v[5]);
    let ylo = v[6].min(v[7]);
    let yhi = v[6].max(v[7]);
    if xhi > xlo && yhi > ylo {
        let normalize = |x: f64, y: f64| {
            let mut nx = (x - xlo) / (xhi - xlo);
            let mut ny = (y - ylo) / (yhi - ylo);
            if flags & 1 != 0 {
                nx = 1.0 - nx;
            }
            if flags & 2 != 0 {
                ny = 1.0 - ny;
            }
            (nx, ny)
        };
        for entry in entries {
            if entry.kind == 2 || entry.kind == 3 {
                let n = broadcast_len(entry.x.len(), entry.y.len())?;
                let mut any = false;
                for i in 0..n {
                    let category = entry.x.broadcast(i, 0.0);
                    let value = entry.y.broadcast(i, 0.0);
                    let base = entry.base.broadcast(i, 0.0);
                    let width = entry.width.broadcast(i, 0.8);
                    let (a, z) = if entry.kind == 2 {
                        (
                            normalize(category - width / 2.0, base),
                            normalize(category + width / 2.0, base + value),
                        )
                    } else {
                        (
                            normalize(base, category - width / 2.0),
                            normalize(base + value, category + width / 2.0),
                        )
                    };
                    if !finite(a) || !finite(z) {
                        continue;
                    }
                    any = true;
                    for (score, b) in scores.iter_mut().zip(boxes) {
                        if a.0.min(z.0) < b[1]
                            && a.0.max(z.0) > b[0]
                            && a.1.min(z.1) < b[3]
                            && a.1.max(z.1) > b[2]
                        {
                            *score += 1.0;
                        }
                    }
                }
                used += u32::from(any);
                continue;
            }
            let mut ecdf = Vec::new();
            let source_n = if entry.kind == 4 {
                entry.y.len()
            } else if entry.kind == 5 {
                ecdf = (0..entry.x.len())
                    .map(|i| entry.x.get(i))
                    .filter(|x| x.is_finite())
                    .collect();
                ecdf.sort_by(f64::total_cmp);
                ecdf.len()
            } else {
                broadcast_len(entry.x.len(), entry.y.len())?
            };
            if source_n == 0 {
                continue;
            }
            let total = match entry.kind {
                4 => source_n * 2,
                5 => source_n + 1,
                6 => source_n * 2 + 1,
                _ => source_n,
            };
            let point = |i: usize| match entry.kind {
                4 => (entry.x.get(i.div_ceil(2)), entry.y.get(i / 2)),
                5 => (ecdf[i.saturating_sub(1)], i as f64 / source_n as f64),
                6 if i >= source_n && i < source_n * 2 => {
                    let j = source_n * 2 - i - 1;
                    (entry.x.broadcast(j, 0.0), entry.base.broadcast(j, 0.0))
                }
                6 if i == source_n * 2 => (entry.x.broadcast(0, 0.0), entry.y.broadcast(0, 0.0)),
                _ => (entry.x.broadcast(i, 0.0), entry.y.broadcast(i, 0.0)),
            };
            let budget = if entry.kind == 1 { 4096 } else { 512 };
            // NumPy linspace(dtype=intp) floors nonnegative sample coordinates.
            let index = |i: usize| {
                if i + 1 == budget {
                    total - 1
                } else {
                    (i as f64 * ((total - 1) as f64 / (budget - 1) as f64)).floor() as usize
                }
            };
            let sampled = if total > budget && (0..budget).any(|i| finite(point(index(i)))) {
                budget
            } else {
                total
            };
            let weight = total as f64 / sampled as f64;
            let mut counts = [0usize; 9];
            let mut hits = [false; 9];
            let mut previous = None;
            let mut any = false;
            for i in 0..sampled {
                let raw = point(if sampled < total { index(i) } else { i });
                let p = normalize(raw.0, raw.1);
                if finite(p) {
                    any = true;
                }
                for j in 0..9 {
                    if finite(p) && inside(p, boxes[j]) {
                        counts[j] += 1;
                        if entry.kind != 1 {
                            hits[j] = true;
                        }
                    }
                    if entry.kind != 1
                        && !hits[j]
                        && previous.is_some_and(|a| intersects(a, p, boxes[j]))
                    {
                        hits[j] = true;
                    }
                }
                previous = Some(p);
            }
            if any {
                used += 1;
                for j in 0..9 {
                    scores[j] += counts[j] as f64 * weight + f64::from(hits[j]);
                }
            }
        }
    }
    let best = scores.iter().copied().fold(f64::INFINITY, f64::min);
    let chosen = scores
        .iter()
        .position(|score| *score <= best * (1.0 + 1e-9))
        .unwrap_or(0);
    let mut out = b"XYLR".to_vec();
    for n in [1u32, chosen as u32, used] {
        out.extend_from_slice(&n.to_le_bytes());
    }
    for value in v[..4]
        .iter()
        .copied()
        .chain([layout.box_w, layout.box_h, px, py])
        .chain(scores)
        .chain([
            v[0] + boxes[chosen][0] * v[2],
            v[1] + (1.0 - boxes[chosen][3]) * v[3],
            layout.box_w,
            layout.box_h,
        ])
    {
        if !value.is_finite() {
            return Err(LegendFitError::Facts);
        }
        out.extend_from_slice(&value.to_le_bytes());
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn frame(kind: u32, x: &[f64], y: &[f64], base: &[f64], width: &[f64]) -> Vec<u8> {
        let mut out = b"XYLF".to_vec();
        for v in [1u32, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0] {
            out.extend_from_slice(&v.to_le_bytes());
        }
        for v in [
            0.0f64, 0.0, 300.0, 200.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0,
        ] {
            out.extend_from_slice(&v.to_le_bytes());
        }
        out.extend_from_slice(&6u32.to_le_bytes());
        out.extend_from_slice(b"Series");
        for v in [
            kind,
            x.len() as u32,
            y.len() as u32,
            base.len() as u32,
            width.len() as u32,
            0,
        ] {
            out.extend_from_slice(&v.to_le_bytes());
        }
        for v in x.iter().chain(y).chain(base).chain(width) {
            out.extend_from_slice(&v.to_le_bytes());
        }
        out
    }
    fn result(data: &[u8]) -> (u32, u32, Vec<f64>) {
        let out = resolve_packed(data).unwrap();
        assert_eq!(out.len(), 184);
        (
            u32::from_le_bytes(out[8..12].try_into().unwrap()),
            u32::from_le_bytes(out[12..16].try_into().unwrap()),
            out[16..]
                .chunks_exact(8)
                .map(|v| f64::from_le_bytes(v.try_into().unwrap()))
                .collect(),
        )
    }
    #[test]
    fn empty_and_offplot_keep_first_candidate() {
        assert_eq!(result(&frame(0, &[], &[], &[], &[])).0, 0);
        let (_, used, values) = result(&frame(1, &[2.0], &[2.0], &[], &[]));
        assert_eq!(used, 1);
        assert!(values[8..17].iter().all(|v| *v == 0.0));
    }
    #[test]
    fn measured_footprint_and_vertex_counts() {
        let (chosen, used, values) = result(&frame(1, &[0.9], &[0.95], &[], &[]));
        assert_eq!((chosen, used), (1, 1));
        assert_eq!(values[8], 1.0);
        assert!(values[4] > 40.0 && values[4] < 100.0);
        assert!((values[5] - 20.13).abs() < 1e-12);
    }
    #[test]
    fn paths_score_crossings_and_do_not_bridge_nan() {
        let (_, _, values) = result(&frame(0, &[0.5, 1.1], &[0.95, 0.95], &[], &[]));
        assert_eq!(values[8], 1.0);
        let (_, _, values) = result(&frame(0, &[0.5, f64::NAN, 1.1], &[0.95; 3], &[], &[]));
        assert_eq!(values[8], 0.0);
    }
    #[test]
    fn sampled_away_nan_gaps_keep_historical_occupancy_approximation() {
        let x: Vec<f64> = (0..1023)
            .map(|i| {
                if i % 2 == 1 {
                    f64::NAN
                } else if i < 512 {
                    0.5
                } else {
                    1.1
                }
            })
            .collect();
        let y = vec![0.95; 1023];
        let (chosen, used, values) = result(&frame(0, &x, &y, &[], &[]));
        assert_eq!((chosen, used), (1, 1));
        assert_eq!(values[8], 1.0);
    }
    #[test]
    fn bars_score_overlap_not_corner_vertices() {
        let (chosen, _, values) = result(&frame(2, &[0.9], &[1.1], &[-0.1], &[0.3]));
        assert_eq!(chosen, 1);
        assert_eq!(values[8], 1.0);
    }
    #[test]
    fn expansion_and_reverse_are_native() {
        for data in [
            frame(4, &[0.0, 1.0], &[0.95], &[], &[]),
            frame(5, &[0.8, 0.9, 1.0], &[], &[], &[]),
            frame(6, &[0.0, 1.0], &[0.95, 0.95], &[], &[]),
        ] {
            assert!(result(&data).2[8] > 0.0);
        }
        let mut data = frame(1, &[0.9], &[0.95], &[], &[]);
        data[8..12].copy_from_slice(&1u32.to_le_bytes());
        let (chosen, _, values) = result(&data);
        assert_eq!(chosen, 0);
        assert_eq!(values[9], 1.0);
    }
    #[test]
    fn bounded_parser_rejects_inactive_and_malformed_inputs() {
        let data = frame(0, &[0.0, 1.0], &[0.0, 1.0], &[], &[]);
        for n in 0..data.len() {
            assert!(resolve_packed(&data[..n]).is_err(), "length {n}");
        }
        let mut extra = data.clone();
        extra.push(0);
        assert!(resolve_packed(&extra).is_err());
        for (at, v) in [(4, 2u32), (8, 32), (12, 4097), (40, 1), (154, 7)] {
            let mut bad = data.clone();
            bad[at..at + 4].copy_from_slice(&v.to_le_bytes());
            assert!(resolve_packed(&bad).is_err(), "offset {at}");
        }
        let mut bad = data.clone();
        bad[112..120].copy_from_slice(&(-0.0f64).to_le_bytes());
        assert!(resolve_packed(&bad).is_err());
        assert!(resolve_packed(&frame(0, &[1.0, 2.0], &[1.0, 2.0, 3.0], &[], &[])).is_err());
    }
}
