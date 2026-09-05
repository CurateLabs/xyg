//! Rust-owned static panel placement and title reservation (M2 #873; dossier §21).
//!
//! XYSL carries authored panel sizes, optional figure-fraction positions, and
//! title facts. XYLO returns placement ready to marshal into StaticDocument.
//! See `spec/design/static-document-layout.md` for the bounded wire contract.

use crate::textblock;

pub const VERSION: u32 = 1;
pub const HEADER_BYTES: usize = 64;
pub const PANEL_BYTES: usize = 40;
pub const OUTPUT_HEADER_BYTES: usize = 48;
pub const MAX_PANELS: usize = 256;
pub const MAX_TITLE_BYTES: usize = 4096;
pub const MAX_DIMENSION: u32 = 65_535;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StaticLayoutError {
    Header,
    Version,
    Flags,
    Limit,
    Panel,
    Title,
}

impl StaticLayoutError {
    pub fn reason(self) -> &'static str {
        match self {
            Self::Header => "XYG_STATIC_LAYOUT_HEADER",
            Self::Version => "XYG_STATIC_LAYOUT_VERSION",
            Self::Flags => "XYG_STATIC_LAYOUT_FLAGS",
            Self::Limit => "XYG_STATIC_LAYOUT_LIMIT",
            Self::Panel => "XYG_STATIC_LAYOUT_PANEL",
            Self::Title => "XYG_STATIC_LAYOUT_TITLE",
        }
    }
}

fn u32_at(bytes: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(bytes[at..at + 4].try_into().unwrap())
}

fn f64_at(bytes: &[u8], at: usize) -> f64 {
    f64::from_le_bytes(bytes[at..at + 8].try_into().unwrap())
}

fn dimension(value: u32) -> bool {
    (1..=MAX_DIMENSION).contains(&value)
}

fn coordinate(value: f64) -> Result<i32, StaticLayoutError> {
    let rounded = value.round_ties_even();
    if !rounded.is_finite() || rounded.abs() > f64::from(MAX_DIMENSION) {
        return Err(StaticLayoutError::Limit);
    }
    Ok(rounded as i32)
}

/// Resolve one complete XYSL document. All bounds are checked before allocation
/// or text measurement; no trailing bytes or ignored mode-specific facts exist.
pub fn resolve_packed(bytes: &[u8]) -> Result<Vec<u8>, StaticLayoutError> {
    if bytes.len() < HEADER_BYTES || &bytes[..4] != b"XYSL" {
        return Err(StaticLayoutError::Header);
    }
    if u32_at(bytes, 4) != VERSION {
        return Err(StaticLayoutError::Version);
    }
    let mode = u32_at(bytes, 8);
    let nrows = u32_at(bytes, 12) as usize;
    let ncols = u32_at(bytes, 16) as usize;
    let count = u32_at(bytes, 20) as usize;
    let canvas_w = u32_at(bytes, 24);
    let canvas_h = u32_at(bytes, 28);
    let flags = u32_at(bytes, 32);
    let title_len = u32_at(bytes, 36) as usize;
    if mode > 2 || flags & !1 != 0 {
        return Err(StaticLayoutError::Flags);
    }
    if count == 0 || count > MAX_PANELS || title_len > MAX_TITLE_BYTES {
        return Err(StaticLayoutError::Limit);
    }
    let title_at = HEADER_BYTES + count * PANEL_BYTES;
    if bytes.len() != title_at + title_len {
        return Err(StaticLayoutError::Header);
    }
    let title = std::str::from_utf8(&bytes[title_at..]).map_err(|_| StaticLayoutError::Title)?;
    let size = f64_at(bytes, 40);
    let title_fraction_x = f64_at(bytes, 48);
    let title_fraction_y = f64_at(bytes, 56);
    if title.contains('\0')
        || !size.is_finite()
        || size <= 0.0
        || size > f64::from(MAX_DIMENSION)
        || !title_fraction_x.is_finite()
        || !title_fraction_y.is_finite()
    {
        return Err(StaticLayoutError::Title);
    }
    if mode == 0 {
        if nrows == 0
            || ncols == 0
            || ncols > count
            || nrows != count.div_ceil(ncols)
            || canvas_w != 0
            || canvas_h != 0
        {
            return Err(StaticLayoutError::Panel);
        }
    } else {
        if nrows != 0
            || flags != 0
            || !dimension(canvas_w)
            || !dimension(canvas_h)
            || (mode == 1 && ncols != 0)
            || (mode == 2 && (ncols == 0 || ncols > MAX_PANELS))
        {
            return Err(StaticLayoutError::Panel);
        }
        if mode == 2 && (size != 16.0 || title_fraction_x != 0.5 || title_fraction_y != 0.98) {
            return Err(StaticLayoutError::Title);
        }
    }
    let mut panel_sizes = Vec::with_capacity(count);
    let mut positions = Vec::with_capacity(count);
    for index in 0..count {
        let at = HEADER_BYTES + index * PANEL_BYTES;
        let width = u32_at(bytes, at);
        let height = u32_at(bytes, at + 4);
        if mode == 2 {
            let gap = f64_at(bytes, at + 8);
            if width != 0
                || height != 0
                || !gap.is_finite()
                || gap < 0.0
                || gap > f64::from(MAX_DIMENSION)
                || gap.fract() != 0.0
                || bytes[at + 16..at + PANEL_BYTES]
                    .iter()
                    .any(|byte| *byte != 0)
                || bytes[at + 8..at + 16] != bytes[HEADER_BYTES + 8..HEADER_BYTES + 16]
            {
                return Err(StaticLayoutError::Panel);
            }
            continue;
        }
        if !dimension(width) || !dimension(height) {
            return Err(StaticLayoutError::Panel);
        }
        panel_sizes.push((width, height));
        if mode == 0 {
            if bytes[at + 8..at + PANEL_BYTES]
                .iter()
                .any(|byte| *byte != 0)
            {
                return Err(StaticLayoutError::Panel);
            }
        } else {
            let left = f64_at(bytes, at + 8);
            let bottom = f64_at(bytes, at + 16);
            let fraction_w = f64_at(bytes, at + 24);
            let fraction_h = f64_at(bytes, at + 32);
            if ![left, bottom, fraction_w, fraction_h]
                .iter()
                .all(|v| v.is_finite())
                || fraction_w <= 0.0
                || fraction_h <= 0.0
            {
                return Err(StaticLayoutError::Panel);
            }
            let x = coordinate(left * f64::from(canvas_w))?;
            let y = coordinate((1.0 - bottom - fraction_h) * f64::from(canvas_h))?;
            if i64::from(x) >= i64::from(canvas_w)
                || i64::from(y) >= i64::from(canvas_h)
                || i64::from(x) + i64::from(width) <= 0
                || i64::from(y) + i64::from(height) <= 0
            {
                return Err(StaticLayoutError::Panel);
            }
            positions.push((x, y));
        }
    }
    let block = if title.is_empty() {
        None
    } else {
        Some(
            textblock::measure(title, size, textblock::LINE_HEIGHT, None)
                .ok_or(StaticLayoutError::Title)?,
        )
    };
    let (width, height, reserve) = if mode == 0 {
        let mut columns = vec![0u32; ncols];
        let mut rows = vec![0u32; nrows];
        for (index, &(width, height)) in panel_sizes.iter().enumerate() {
            columns[index % ncols] = columns[index % ncols].max(width);
            rows[index / ncols] = rows[index / ncols].max(height);
        }
        let reserve = match &block {
            Some(block) => coordinate(block.height + 12.0)? as u32,
            None => 0,
        };
        let width = columns.iter().sum::<u32>();
        let height = rows.iter().sum::<u32>() + reserve + if flags & 1 != 0 { 52 } else { 0 };
        if !dimension(width) || !dimension(height) {
            return Err(StaticLayoutError::Limit);
        }
        for index in 0..count {
            let x = columns[..index % ncols].iter().sum::<u32>();
            let y = reserve + rows[..index / ncols].iter().sum::<u32>();
            positions.push((x as i32, y as i32));
        }
        (width, height, reserve)
    } else if mode == 2 {
        let gap = f64_at(bytes, HEADER_BYTES + 8) as u32;
        let rows = count.div_ceil(ncols) as u32;
        let available = i64::from(canvas_w) - (ncols as i64 - 1) * i64::from(gap);
        let panel_width = (available / ncols as i64).max(120) as u32;
        let reserve = if title.is_empty() { 0 } else { 24 };
        let height = rows * canvas_h + (rows - 1) * gap + reserve;
        if !dimension(height) {
            return Err(StaticLayoutError::Limit);
        }
        for index in 0..count {
            let x = (index % ncols) as u32 * (panel_width + gap);
            let y = reserve + (index / ncols) as u32 * (canvas_h + gap);
            if x >= canvas_w {
                return Err(StaticLayoutError::Panel);
            }
            positions.push((x as i32, y as i32));
            panel_sizes.push((panel_width, canvas_h));
        }
        (canvas_w, height, reserve)
    } else {
        (canvas_w, canvas_h, 0)
    };
    let title_band = f64::from(if reserve == 0 { height } else { reserve });
    let (ascent, descent, trailing) =
        block
            .as_ref()
            .map_or((0.75 * size, 0.25 * size, 0.0), |block| {
                (
                    block.ascent,
                    block.descent,
                    (block.line_count() - 1) as f64 * block.line_step,
                )
            });
    let desired = (1.0 - title_fraction_y) * f64::from(height) + ascent;
    let maximum = ascent.max(title_band - trailing - descent - 2.0);
    let title_baseline = if mode == 2 {
        16.0
    } else {
        desired.max(ascent).min(maximum)
    };
    let title_x = f64::from(width) * title_fraction_x;
    if !desired.is_finite() || !title_x.is_finite() || title_x.abs() > f64::from(MAX_DIMENSION) {
        return Err(StaticLayoutError::Title);
    }
    let mut out = Vec::with_capacity(OUTPUT_HEADER_BYTES + count * if mode == 2 { 16 } else { 8 });
    out.extend_from_slice(b"XYLO");
    for value in [VERSION, width, height, count as u32, reserve] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    for value in [title_x, title_baseline, title_band] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    for (index, (x, y)) in positions.into_iter().enumerate() {
        out.extend_from_slice(&x.to_le_bytes());
        out.extend_from_slice(&y.to_le_bytes());
        if mode == 2 {
            let (width, height) = panel_sizes[index];
            out.extend_from_slice(&width.to_le_bytes());
            out.extend_from_slice(&height.to_le_bytes());
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(mode: u32, panels: &[(u32, u32, [f64; 4])], title: &str) -> Vec<u8> {
        let mut out = Vec::new();
        out.extend_from_slice(b"XYSL");
        let count = panels.len() as u32;
        for value in [
            VERSION,
            mode,
            if mode == 0 { count.div_ceil(2) } else { 0 },
            if mode == 0 { count.min(2) } else { 0 },
            count,
            if mode == 1 { 400 } else { 0 },
            if mode == 1 { 300 } else { 0 },
            0,
            title.len() as u32,
        ] {
            out.extend_from_slice(&value.to_le_bytes());
        }
        for value in [16.0_f64, 0.5, 0.98] {
            out.extend_from_slice(&value.to_le_bytes());
        }
        for (width, height, fractions) in panels {
            out.extend_from_slice(&width.to_le_bytes());
            out.extend_from_slice(&height.to_le_bytes());
            for value in fractions {
                out.extend_from_slice(&value.to_le_bytes());
            }
        }
        out.extend_from_slice(title.as_bytes());
        out
    }

    fn positions(bytes: &[u8]) -> Vec<(i32, i32)> {
        bytes[OUTPUT_HEADER_BYTES..]
            .chunks_exact(8)
            .map(|row| {
                (
                    i32::from_le_bytes(row[..4].try_into().unwrap()),
                    i32::from_le_bytes(row[4..].try_into().unwrap()),
                )
            })
            .collect()
    }

    #[test]
    fn uneven_grid_reserves_multiline_title_and_shared_colorbar() {
        let mut input = request(
            0,
            &[(100, 70, [0.0; 4]), (80, 90, [0.0; 4]), (130, 50, [0.0; 4])],
            "first\nsecond",
        );
        input[32..36].copy_from_slice(&1u32.to_le_bytes());
        let output = resolve_packed(&input).unwrap();
        assert_eq!(&output[..4], b"XYLO");
        assert_eq!(u32_at(&output, 8), 210);
        assert_eq!(u32_at(&output, 12), 242);
        assert_eq!(u32_at(&output, 20), 50);
        assert_eq!(positions(&output), vec![(0, 50), (130, 50), (0, 140)]);
        assert_eq!(f64_at(&output, 24), 105.0);
        assert!((f64_at(&output, 32) - 19.84).abs() < 1e-12);
        assert_eq!(f64_at(&output, 40), 50.0);
    }

    #[test]
    fn normalized_placement_keeps_signed_chrome_overhang_and_ties_even() {
        let input = request(
            1,
            &[
                (140, 100, [-0.00625, 0.5, 0.35, 0.25]),
                (140, 100, [0.50625, 0.0, 0.35, 0.25]),
            ],
            "title",
        );
        let output = resolve_packed(&input).unwrap();
        assert_eq!(positions(&output), vec![(-2, 75), (202, 225)]);
        assert_eq!(u32_at(&output, 20), 0);
        assert!((f64_at(&output, 32) - 21.0).abs() < 1e-12);
        assert_eq!(f64_at(&output, 40), 300.0);
    }

    #[test]
    fn title_baseline_clamps_entire_block_inside_reserved_band() {
        let mut input = request(0, &[(200, 150, [0.0; 4])], "a\nb\nc");
        input[56..64].copy_from_slice(&(-1.0_f64).to_le_bytes());
        let output = resolve_packed(&input).unwrap();
        assert_eq!(u32_at(&output, 20), 70);
        assert!((f64_at(&output, 32) - 25.6).abs() < 1e-12);
        input[56..64].copy_from_slice(&2.0_f64.to_le_bytes());
        assert_eq!(f64_at(&resolve_packed(&input).unwrap(), 32), 15.0);
    }

    #[test]
    fn title_newlines_are_measured_identically() {
        let panels = [(200, 150, [0.0; 4])];
        assert_eq!(
            resolve_packed(&request(0, &panels, "a\r\nb\rc")).unwrap(),
            resolve_packed(&request(0, &panels, "a\nb\nc")).unwrap()
        );
        let output = resolve_packed(&request(0, &panels, "")).unwrap();
        assert_eq!(u32_at(&output, 20), 0);
        assert_eq!(positions(&output), vec![(0, 0)]);
    }

    #[test]
    fn malformed_frames_reject_without_panics() {
        let valid = request(0, &[(200, 150, [0.0; 4])], "title");
        for len in 0..valid.len() {
            assert!(resolve_packed(&valid[..len]).is_err(), "prefix {len}");
        }
        let mut extra = valid.clone();
        extra.push(0);
        assert_eq!(resolve_packed(&extra), Err(StaticLayoutError::Header));
        for (offset, value, reason) in [
            (4, 2u32, StaticLayoutError::Version),
            (8, 3, StaticLayoutError::Flags),
            (12, 0, StaticLayoutError::Panel),
            (16, 2, StaticLayoutError::Panel),
            (20, 257, StaticLayoutError::Limit),
            (24, 1, StaticLayoutError::Panel),
            (32, 2, StaticLayoutError::Flags),
            (36, 4097, StaticLayoutError::Limit),
            (64, 0, StaticLayoutError::Panel),
            (68, 65_536, StaticLayoutError::Panel),
        ] {
            let mut input = valid.clone();
            input[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
            assert_eq!(resolve_packed(&input), Err(reason), "field {offset}");
        }
        for offset in [40, 48, 56, 72] {
            let mut input = valid.clone();
            input[offset..offset + 8].copy_from_slice(&f64::NAN.to_le_bytes());
            assert!(resolve_packed(&input).is_err());
        }
        for invalid in [0, 255] {
            let mut input = valid.clone();
            *input.last_mut().unwrap() = invalid;
            assert_eq!(resolve_packed(&input), Err(StaticLayoutError::Title));
        }
    }

    #[test]
    fn bounds_and_inactive_mode_facts_fail_closed() {
        let valid = request(1, &[(140, 100, [0.0, 0.5, 0.35, 0.25])], "title");
        for offset in [12, 16, 32] {
            let mut input = valid.clone();
            input[offset..offset + 4].copy_from_slice(&1u32.to_le_bytes());
            assert_eq!(resolve_packed(&input), Err(StaticLayoutError::Panel));
        }
        for (offset, value) in [(72, 2.0_f64), (80, f64::NAN), (88, 0.0), (96, -1.0)] {
            let mut input = valid.clone();
            input[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
            assert!(resolve_packed(&input).is_err(), "field {offset}");
        }
        let huge_grid = request(0, &[(40_000, 100, [0.0; 4]), (40_000, 100, [0.0; 4])], "");
        assert_eq!(resolve_packed(&huge_grid), Err(StaticLayoutError::Limit));
    }

    fn facet_request(
        count: usize,
        cols: u32,
        width: u32,
        height: u32,
        gap: f64,
        title: &str,
    ) -> Vec<u8> {
        let mut input = request(2, &vec![(0, 0, [gap, 0.0, 0.0, 0.0]); count], title);
        input[16..20].copy_from_slice(&cols.to_le_bytes());
        input[24..28].copy_from_slice(&width.to_le_bytes());
        input[28..32].copy_from_slice(&height.to_le_bytes());
        input
    }

    #[test]
    fn facets_preserve_remainder_gaps_partial_rows_and_fixed_title() {
        let output = resolve_packed(&facet_request(4, 3, 901, 160, 12.0, "Facets")).unwrap();
        assert_eq!((u32_at(&output, 8), u32_at(&output, 12)), (901, 356));
        assert_eq!(u32_at(&output, 20), 24);
        assert_eq!(f64_at(&output, 24), 450.5);
        assert_eq!(f64_at(&output, 32), 16.0);
        let records: Vec<_> = output[48..]
            .chunks_exact(16)
            .map(|row| {
                (
                    u32_at(row, 0),
                    u32_at(row, 4),
                    u32_at(row, 8),
                    u32_at(row, 12),
                )
            })
            .collect();
        assert_eq!(
            records,
            vec![
                (0, 24, 292, 160),
                (304, 24, 292, 160),
                (608, 24, 292, 160),
                (0, 196, 292, 160)
            ]
        );
        let minimum = resolve_packed(&facet_request(2, 2, 200, 100, 12.0, "")).unwrap();
        assert_eq!(u32_at(&minimum, 20), 0);
        assert_eq!(u32_at(&minimum, 48 + 8), 120);
        assert_eq!(u32_at(&minimum, 64), 132);
    }

    #[test]
    fn facets_reject_ignored_facts_and_invalid_dimensions() {
        let valid = facet_request(2, 3, 901, 160, 12.0, "Facets");
        for offset in [12, 32, 64, 68, 80, 88, 96] {
            let mut input = valid.clone();
            input[offset] = 1;
            assert_eq!(
                resolve_packed(&input),
                Err(StaticLayoutError::Panel),
                "field {offset}"
            );
        }
        for gap in [-1.0, 0.5, f64::NAN, f64::INFINITY, 65_536.0] {
            assert_eq!(
                resolve_packed(&facet_request(2, 3, 901, 160, gap, "")),
                Err(StaticLayoutError::Panel)
            );
        }
        let mut input = valid.clone();
        input[HEADER_BYTES + PANEL_BYTES + 8..HEADER_BYTES + PANEL_BYTES + 16]
            .copy_from_slice(&13.0_f64.to_le_bytes());
        assert_eq!(resolve_packed(&input), Err(StaticLayoutError::Panel));
        assert_eq!(
            resolve_packed(&facet_request(2, 0, 901, 160, 12.0, "")),
            Err(StaticLayoutError::Panel)
        );
        assert_eq!(
            resolve_packed(&facet_request(2, 1, 901, 65_535, 12.0, "")),
            Err(StaticLayoutError::Limit)
        );
        assert_eq!(
            resolve_packed(&facet_request(3, 3, 200, 100, 12.0, "")),
            Err(StaticLayoutError::Panel)
        );
        let mut input = valid;
        input[48..56].copy_from_slice(&0.4_f64.to_le_bytes());
        assert_eq!(resolve_packed(&input), Err(StaticLayoutError::Title));
    }
}
