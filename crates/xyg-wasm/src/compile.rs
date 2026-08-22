//! Packed typed-column compile requests for the direct-browser WASM host.
//!
//! The Worker copies one little-endian `XYCC` request into the staging arena.
//! Rust validates lengths and scale fields, then builds the same canonical
//! Scene batch that native hosts encode through `xyg_scene_batch_encode`.

pub use crate::typed_series_abi_generated::*;
use xyg_engine::scene::{
    self, AxisScale, CartesianLayoutRequest, PlotLayout, ScaleKind, SceneBatch, SceneChromeStyle,
    SceneChromeText, SceneError,
};

pub const COMPILE_MAGIC: &[u8; 4] = b"XYCC";
pub const COMPILE_VERSION: u32 = 1;
// Conservative simultaneous logical storage for one expanded record: parsed
// columns, mark metadata, the canonical Scene record, packed output, and Vec
// capacity slack. Keep this above the sum of those representations whenever
// the lowering pipeline changes.
/// When set, Rust derives axis domains from finite column values so the browser
/// main thread does not scan O(N) data for lo/hi.

#[derive(Debug)]
pub struct CompiledScene {
    pub bytes: Vec<u8>,
    pub records: usize,
    pub styles: usize,
}

fn u32_at(bytes: &[u8], offset: usize) -> Result<u32, SceneError> {
    let end = offset.checked_add(4).ok_or(SceneError::Length)?;
    let slice = bytes.get(offset..end).ok_or(SceneError::Length)?;
    Ok(u32::from_le_bytes(
        slice.try_into().map_err(|_| SceneError::Length)?,
    ))
}

fn u64_at(bytes: &[u8], offset: usize) -> Result<u64, SceneError> {
    let end = offset.checked_add(8).ok_or(SceneError::Length)?;
    let slice = bytes.get(offset..end).ok_or(SceneError::Length)?;
    Ok(u64::from_le_bytes(
        slice.try_into().map_err(|_| SceneError::Length)?,
    ))
}

fn f64_at(bytes: &[u8], offset: usize) -> Result<f64, SceneError> {
    let end = offset.checked_add(8).ok_or(SceneError::Length)?;
    let slice = bytes.get(offset..end).ok_or(SceneError::Length)?;
    Ok(f64::from_le_bytes(
        slice.try_into().map_err(|_| SceneError::Length)?,
    ))
}

fn align8(offset: usize) -> usize {
    offset.saturating_add(7) & !7
}

fn take<'a>(bytes: &'a [u8], offset: &mut usize, len: usize) -> Result<&'a [u8], SceneError> {
    let end = offset.checked_add(len).ok_or(SceneError::Length)?;
    let out = bytes.get(*offset..end).ok_or(SceneError::Length)?;
    *offset = end;
    Ok(out)
}

fn take_f64s(bytes: &[u8], offset: &mut usize, count: usize) -> Result<Vec<f64>, SceneError> {
    *offset = align8(*offset);
    let byte_len = count.checked_mul(8).ok_or(SceneError::Limit)?;
    let raw = take(bytes, offset, byte_len)?;
    let mut values = Vec::with_capacity(count);
    for chunk in raw.chunks_exact(8) {
        values.push(f64::from_le_bytes(
            chunk.try_into().map_err(|_| SceneError::Length)?,
        ));
    }
    Ok(values)
}

fn take_u64s(bytes: &[u8], offset: &mut usize, count: usize) -> Result<Vec<u64>, SceneError> {
    *offset = align8(*offset);
    let byte_len = count.checked_mul(8).ok_or(SceneError::Limit)?;
    let raw = take(bytes, offset, byte_len)?;
    let mut values = Vec::with_capacity(count);
    for chunk in raw.chunks_exact(8) {
        values.push(u64::from_le_bytes(
            chunk.try_into().map_err(|_| SceneError::Length)?,
        ));
    }
    Ok(values)
}

fn take_u32s(bytes: &[u8], offset: &mut usize, count: usize) -> Result<Vec<u32>, SceneError> {
    *offset = align8(*offset);
    let byte_len = count.checked_mul(4).ok_or(SceneError::Limit)?;
    let raw = take(bytes, offset, byte_len)?;
    let mut values = Vec::with_capacity(count);
    for chunk in raw.chunks_exact(4) {
        values.push(u32::from_le_bytes(
            chunk.try_into().map_err(|_| SceneError::Length)?,
        ));
    }
    Ok(values)
}

fn scale_kind(value: u32) -> Result<ScaleKind, SceneError> {
    match value {
        0 => Ok(ScaleKind::Linear),
        1 => Ok(ScaleKind::Log),
        2 => Ok(ScaleKind::SymLog),
        _ => Err(SceneError::Length),
    }
}

fn consider_finite(value: f64, lo: &mut f64, hi: &mut f64, any: &mut bool) {
    if !value.is_finite() {
        return;
    }
    if !*any {
        *lo = value;
        *hi = value;
        *any = true;
        return;
    }
    if value < *lo {
        *lo = value;
    }
    if value > *hi {
        *hi = value;
    }
}

/// Derive axis domains from finite geometry columns. Scatter/polyline use
/// `(x0, y0)`; rect/band also include `(x1, y1)`. Returns `None` when either
/// axis has no finite coordinate.
fn auto_domain_from_columns(
    kinds: &[u8],
    x0: &[f64],
    y0: &[f64],
    x1: &[f64],
    y1: &[f64],
) -> Option<(f64, f64, f64, f64)> {
    let mut x_lo = 0.0;
    let mut x_hi = 0.0;
    let mut y_lo = 0.0;
    let mut y_hi = 0.0;
    let mut any_x = false;
    let mut any_y = false;
    for (index, kind) in kinds.iter().copied().enumerate() {
        consider_finite(x0[index], &mut x_lo, &mut x_hi, &mut any_x);
        consider_finite(y0[index], &mut y_lo, &mut y_hi, &mut any_y);
        // Rect (2) and band (3) span both corners; scatter/polyline leave x1/y1 unused.
        if matches!(kind as u32, KIND_BAR | KIND_AREA) {
            consider_finite(x1[index], &mut x_lo, &mut x_hi, &mut any_x);
            consider_finite(y1[index], &mut y_lo, &mut y_hi, &mut any_y);
        }
    }
    if !any_x || !any_y {
        return None;
    }
    if x_lo == x_hi {
        x_lo -= 0.5;
        x_hi += 0.5;
    }
    if y_lo == y_hi {
        y_lo -= 0.5;
        y_hi += 0.5;
    }
    Some((x_lo, x_hi, y_lo, y_hi))
}

fn compile_columns_request(bytes: &[u8], literal_ids: bool) -> Result<CompiledScene, SceneError> {
    if bytes.len() < COMPILE_HEADER_BYTES {
        return Err(SceneError::Length);
    }
    if &bytes[..4] != COMPILE_MAGIC {
        return Err(SceneError::Length);
    }
    if u32_at(bytes, HEADER_VERSION)? != COMPILE_VERSION {
        return Err(SceneError::Version);
    }
    if u32_at(bytes, HEADER_HEADER_BYTES)? as usize != COMPILE_HEADER_BYTES {
        return Err(SceneError::Length);
    }
    let flags = u32_at(bytes, HEADER_FLAGS)?;
    if flags & !HEADER_FLAG_KNOWN != 0 {
        return Err(SceneError::Length);
    }
    let record_count = u32_at(bytes, HEADER_SERIES_COUNT)? as usize;
    let style_count = u32_at(bytes, HEADER_RECORD_COUNT)? as usize;
    let title_len = u32_at(bytes, HEADER_TITLE_BYTES)? as usize;
    let x_label_len = u32_at(bytes, HEADER_X_LABEL_BYTES)? as usize;
    let y_label_len = u32_at(bytes, HEADER_Y_LABEL_BYTES)? as usize;
    if u32_at(bytes, HEADER_RESERVED0)? != 0 {
        return Err(SceneError::Length);
    }
    if record_count > scene::MAX_SCENE_MARKS
        || style_count > scene::MAX_SCENE_STYLES
        || title_len > scene::MAX_SCENE_TEXT_BYTES
        || x_label_len > scene::MAX_SCENE_TEXT_BYTES
        || y_label_len > scene::MAX_SCENE_TEXT_BYTES
    {
        return Err(SceneError::Limit);
    }

    let viewport_width = f64_at(bytes, HEADER_WIDTH)?;
    let viewport_height = f64_at(bytes, HEADER_HEIGHT)?;
    let margin_left = f64_at(bytes, HEADER_MARGINS)?;
    let margin_right = f64_at(bytes, HEADER_MARGINS + 8)?;
    let margin_top = f64_at(bytes, HEADER_MARGINS + 16)?;
    let margin_bottom = f64_at(bytes, HEADER_MARGINS + 24)?;
    let x_axis_id = u64_at(bytes, HEADER_X_AXIS_ID)?;
    let y_axis_id = u64_at(bytes, HEADER_Y_AXIS_ID)?;
    let x_kind = scale_kind(u32_at(bytes, HEADER_X_SCALE_KIND)?)?;
    let y_kind = scale_kind(u32_at(bytes, HEADER_Y_SCALE_KIND)?)?;
    let x_mask = u32_at(bytes, HEADER_X_MASK_NONPOSITIVE)?;
    let y_mask = u32_at(bytes, HEADER_Y_MASK_NONPOSITIVE)?;
    if !matches!(x_mask, 0 | 1) || !matches!(y_mask, 0 | 1) {
        return Err(SceneError::Length);
    }
    let mut x_lo = f64_at(bytes, HEADER_X_LO)?;
    let mut x_hi = f64_at(bytes, HEADER_X_HI)?;
    let x_constant = f64_at(bytes, HEADER_X_CONSTANT)?;
    let mut y_lo = f64_at(bytes, HEADER_Y_LO)?;
    let mut y_hi = f64_at(bytes, HEADER_Y_HI)?;
    let y_constant = f64_at(bytes, HEADER_Y_CONSTANT)?;
    for reserved in (HEADER_RESERVED_TAIL..COMPILE_HEADER_BYTES).step_by(4) {
        if u32_at(bytes, reserved)? != 0 {
            return Err(SceneError::Length);
        }
    }

    let mut offset = COMPILE_HEADER_BYTES;
    let kinds = take(bytes, &mut offset, record_count)?.to_vec();
    let stable_ids = take_u64s(bytes, &mut offset, record_count)?;
    let style_refs = take_u32s(bytes, &mut offset, record_count)?;
    let diameter = take_f64s(bytes, &mut offset, record_count)?;
    let symbols = take(bytes, &mut offset, record_count)?.to_vec();
    let x0 = take_f64s(bytes, &mut offset, record_count)?;
    let y0 = take_f64s(bytes, &mut offset, record_count)?;
    let x1 = take_f64s(bytes, &mut offset, record_count)?;
    let y1 = take_f64s(bytes, &mut offset, record_count)?;
    let fill_rgba = take(bytes, &mut offset, style_count.saturating_mul(4))?.to_vec();
    let stroke_rgba = take(bytes, &mut offset, style_count.saturating_mul(4))?.to_vec();
    let stroke_width = take_f64s(bytes, &mut offset, style_count)?;
    let title_bytes = take(bytes, &mut offset, title_len)?;
    let x_label_bytes = take(bytes, &mut offset, x_label_len)?;
    let y_label_bytes = take(bytes, &mut offset, y_label_len)?;
    if offset != bytes.len() {
        return Err(SceneError::Length);
    }

    let title = std::str::from_utf8(title_bytes).map_err(|_| SceneError::Length)?;
    let x_label = std::str::from_utf8(x_label_bytes).map_err(|_| SceneError::Length)?;
    let y_label = std::str::from_utf8(y_label_bytes).map_err(|_| SceneError::Length)?;
    let text = SceneChromeText::from_parts(title, x_label, y_label)?;

    if flags & HEADER_FLAG_AUTO_DOMAIN != 0 {
        let Some(domain) = auto_domain_from_columns(&kinds, &x0, &y0, &x1, &y1) else {
            return Err(SceneError::NonFinite);
        };
        x_lo = domain.0;
        x_hi = domain.1;
        y_lo = domain.2;
        y_hi = domain.3;
    }

    let (margin_left, margin_right, margin_top, margin_bottom) =
        if flags & HEADER_FLAG_AUTO_MARGINS != 0 {
            scene::cartesian_scene_margins(CartesianLayoutRequest {
                viewport_width,
                viewport_height,
                authored_padding: None,
                title,
                x_label,
                y_label,
                x_kind,
                x_lo,
                x_hi,
                x_constant,
                x_mask_nonpositive: x_mask != 0,
                y_kind,
                y_lo,
                y_hi,
                y_constant,
                y_mask_nonpositive: y_mask != 0,
            })?
        } else {
            (margin_left, margin_right, margin_top, margin_bottom)
        };

    let layout = PlotLayout::new(
        viewport_width,
        viewport_height,
        margin_left,
        margin_right,
        margin_top,
        margin_bottom,
    )?;
    let x_scale = AxisScale::new(
        x_kind,
        x_lo,
        x_hi,
        layout.left,
        layout.right,
        x_constant,
        x_mask != 0,
    )?;
    let y_scale = AxisScale::new(
        y_kind,
        y_lo,
        y_hi,
        layout.bottom,
        layout.top,
        y_constant,
        y_mask != 0,
    )?;
    let batch = if literal_ids {
        SceneBatch::new_with_chrome_literal_ids(
            layout,
            x_axis_id,
            y_axis_id,
            x_scale,
            y_scale,
            SceneChromeStyle::default(),
            text,
            &kinds,
            &stable_ids,
            &style_refs,
            &fill_rgba,
            &stroke_rgba,
            &stroke_width,
            &diameter,
            &symbols,
            &x0,
            &y0,
            &x1,
            &y1,
        )?
    } else {
        SceneBatch::new_with_chrome(
            layout,
            x_axis_id,
            y_axis_id,
            x_scale,
            y_scale,
            SceneChromeStyle::default(),
            text,
            &kinds,
            &stable_ids,
            &style_refs,
            &fill_rgba,
            &stroke_rgba,
            &stroke_width,
            &diameter,
            &symbols,
            &x0,
            &y0,
            &x1,
            &y1,
        )?
    };
    Ok(CompiledScene {
        records: record_count,
        styles: style_count,
        bytes: batch.encode(),
    })
}

fn append_aligned_u64s(out: &mut Vec<u8>, values: &[u64]) {
    while !out.len().is_multiple_of(8) {
        out.push(0);
    }
    for value in values {
        out.extend_from_slice(&value.to_le_bytes());
    }
}

fn append_aligned_u32s(out: &mut Vec<u8>, values: &[u32]) {
    while !out.len().is_multiple_of(8) {
        out.push(0);
    }
    for value in values {
        out.extend_from_slice(&value.to_le_bytes());
    }
}

fn append_aligned_f64s(out: &mut Vec<u8>, values: &[f64]) {
    while !out.len().is_multiple_of(8) {
        out.push(0);
    }
    for value in values {
        out.extend_from_slice(&value.to_le_bytes());
    }
}

fn default_bar_half_width(xs: &[f64], domain_lo: f64, domain_hi: f64) -> Result<f64, SceneError> {
    if xs.iter().any(|value| !value.is_finite()) {
        return Err(SceneError::NonFinite);
    }
    let mut sorted = xs.to_vec();
    sorted.sort_by(f64::total_cmp);
    let spacing = sorted
        .windows(2)
        .map(|pair| pair[1] - pair[0])
        .filter(|value| *value > 0.0)
        .min_by(f64::total_cmp);
    let domain_span = (domain_hi - domain_lo).abs();
    let basis =
        spacing.or_else(|| (domain_span.is_finite() && domain_span > 0.0).then_some(domain_span));
    basis.map(|value| value * 0.4).ok_or(SceneError::NonFinite)
}

fn series_f64s(
    bytes: &[u8],
    offset: u32,
    count: usize,
    data_start: usize,
) -> Result<Vec<f64>, SceneError> {
    let start = offset as usize;
    if start < data_start || !start.is_multiple_of(8) {
        return Err(SceneError::Length);
    }
    let end = start
        .checked_add(count.checked_mul(8).ok_or(SceneError::Limit)?)
        .ok_or(SceneError::Limit)?;
    let raw = bytes.get(start..end).ok_or(SceneError::Length)?;
    raw.chunks_exact(8)
        .map(|chunk| {
            Ok(f64::from_le_bytes(
                chunk.try_into().map_err(|_| SceneError::Length)?,
            ))
        })
        .collect()
}

fn next_series_f64s(
    bytes: &[u8],
    offset: u32,
    count: usize,
    data_start: usize,
    cursor: &mut usize,
) -> Result<Vec<f64>, SceneError> {
    if offset as usize != *cursor {
        return Err(SceneError::Length);
    }
    let values = series_f64s(bytes, offset, count, data_start)?;
    *cursor = cursor
        .checked_add(count.checked_mul(8).ok_or(SceneError::Limit)?)
        .ok_or(SceneError::Limit)?;
    Ok(values)
}

fn next_series_u64s(
    bytes: &[u8],
    offset: u32,
    count: usize,
    data_start: usize,
    cursor: &mut usize,
) -> Result<Vec<u64>, SceneError> {
    if offset as usize != *cursor || !(offset as usize).is_multiple_of(8) {
        return Err(SceneError::Length);
    }
    let byte_len = count.checked_mul(8).ok_or(SceneError::Limit)?;
    let end = cursor.checked_add(byte_len).ok_or(SceneError::Limit)?;
    let raw = bytes.get(*cursor..end).ok_or(SceneError::Length)?;
    let values = raw
        .chunks_exact(8)
        .map(|chunk| {
            Ok(u64::from_le_bytes(
                chunk.try_into().map_err(|_| SceneError::Length)?,
            ))
        })
        .collect::<Result<Vec<_>, _>>()?;
    if *cursor < data_start {
        return Err(SceneError::Length);
    }
    *cursor = end;
    Ok(values)
}

/// Expand packed transferable typed-series descriptors in Rust, then compile
/// through the canonical typed-column path. TypeScript never assigns stable
/// ids, chooses mark defaults, or performs per-record expansion.
fn series_peak_bytes(
    input_bytes: usize,
    record_count: usize,
    series_count: usize,
) -> Result<usize, SceneError> {
    input_bytes
        .checked_mul(SERIES_PEAK_INPUT_MULTIPLIER)
        .and_then(|value| {
            value.checked_add(record_count.checked_mul(SERIES_PEAK_BYTES_PER_RECORD)?)
        })
        .and_then(|value| {
            value.checked_add(series_count.checked_mul(SERIES_PEAK_BYTES_PER_SERIES)?)
        })
        .and_then(|value| value.checked_add(SERIES_PEAK_FIXED_BYTES))
        .ok_or(SceneError::Limit)
}

fn compile_series_request(bytes: &[u8], peak_budget: usize) -> Result<CompiledScene, SceneError> {
    if bytes.len() < COMPILE_HEADER_BYTES || &bytes[..4] != SERIES_MAGIC {
        return Err(SceneError::Length);
    }
    if u32_at(bytes, HEADER_VERSION)? != SERIES_VERSION {
        return Err(SceneError::Version);
    }
    if u32_at(bytes, HEADER_HEADER_BYTES)? as usize != COMPILE_HEADER_BYTES {
        return Err(SceneError::Length);
    }
    let series_count = u32_at(bytes, HEADER_SERIES_COUNT)? as usize;
    let record_count = u32_at(bytes, HEADER_RECORD_COUNT)? as usize;
    let domain_x_lo = f64_at(bytes, HEADER_X_LO)?;
    let domain_x_hi = f64_at(bytes, HEADER_X_HI)?;
    if series_count == 0
        || series_count > MAX_SERIES.min(scene::MAX_SCENE_STYLES)
        || record_count > MAX_RECORDS.min(scene::MAX_SCENE_MARKS)
    {
        return Err(SceneError::Limit);
    }
    if series_peak_bytes(bytes.len(), record_count, series_count)? > peak_budget {
        return Err(SceneError::Limit);
    }
    let descriptors_end = COMPILE_HEADER_BYTES
        .checked_add(
            series_count
                .checked_mul(SERIES_DESCRIPTOR_BYTES)
                .ok_or(SceneError::Limit)?,
        )
        .ok_or(SceneError::Limit)?;
    if descriptors_end > bytes.len() {
        return Err(SceneError::Length);
    }
    let title_len = u32_at(bytes, HEADER_TITLE_BYTES)? as usize;
    let x_label_len = u32_at(bytes, HEADER_X_LABEL_BYTES)? as usize;
    let y_label_len = u32_at(bytes, HEADER_Y_LABEL_BYTES)? as usize;
    if title_len > MAX_TEXT_BYTES || x_label_len > MAX_TEXT_BYTES || y_label_len > MAX_TEXT_BYTES {
        return Err(SceneError::Limit);
    }
    let text_bytes = title_len
        .checked_add(x_label_len)
        .and_then(|value| value.checked_add(y_label_len))
        .ok_or(SceneError::Limit)?;
    let data_start = align8(
        descriptors_end
            .checked_add(text_bytes)
            .ok_or(SceneError::Limit)?,
    );
    if data_start > bytes.len()
        || bytes[descriptors_end + text_bytes..data_start]
            .iter()
            .any(|byte| *byte != 0)
    {
        return Err(SceneError::Length);
    }

    let mut kinds = Vec::with_capacity(record_count);
    let mut stable_ids = Vec::with_capacity(record_count);
    let mut style_refs = Vec::with_capacity(record_count);
    let mut diameter = Vec::with_capacity(record_count);
    let mut symbols = Vec::with_capacity(record_count);
    let mut x0 = Vec::with_capacity(record_count);
    let mut y0 = Vec::with_capacity(record_count);
    let mut x1 = Vec::with_capacity(record_count);
    let mut y1 = Vec::with_capacity(record_count);
    let mut fill_rgba = Vec::with_capacity(series_count * 4);
    let mut stroke_rgba = Vec::with_capacity(series_count * 4);
    let mut stroke_width = Vec::with_capacity(series_count);
    let mut next_default_id = 1u64;
    let mut data_cursor = data_start;

    for series_index in 0..series_count {
        let base = COMPILE_HEADER_BYTES + series_index * SERIES_DESCRIPTOR_BYTES;
        let kind = u32_at(bytes, base + DESCRIPTOR_KIND)?;
        if !matches!(kind, KIND_SCATTER | KIND_LINE | KIND_BAR | KIND_AREA) {
            return Err(SceneError::Length);
        }
        let symbol = u32_at(bytes, base + DESCRIPTOR_SYMBOL)?;
        if symbol > MAX_SYMBOL_CODE {
            return Err(SceneError::Length);
        }
        let count = u32_at(bytes, base + DESCRIPTOR_RECORD_COUNT)? as usize;
        let flags = u32_at(bytes, base + DESCRIPTOR_FLAGS)?;
        if count == 0 || flags & !DESCRIPTOR_FLAG_KNOWN != 0 {
            return Err(SceneError::Length);
        }
        if flags & DESCRIPTOR_FLAG_STABLE_ID_BASE != 0 && flags & DESCRIPTOR_FLAG_STABLE_IDS != 0 {
            return Err(SceneError::Length);
        }
        let stable_base = if flags & DESCRIPTOR_FLAG_STABLE_ID_BASE != 0 {
            u64_at(bytes, base + DESCRIPTOR_STABLE_ID_BASE)?
        } else {
            next_default_id
        };
        let identity_count = if matches!(kind, KIND_LINE | KIND_AREA) {
            1
        } else {
            count as u64
        };
        let scalar_diameter = f64_at(bytes, base + DESCRIPTOR_DIAMETER)?;
        let authored_stroke = f64_at(bytes, base + DESCRIPTOR_STROKE_WIDTH)?;
        if flags & DESCRIPTOR_FLAG_FILL_RGBA != 0 {
            fill_rgba.extend_from_slice(
                bytes
                    .get(base + DESCRIPTOR_FILL_RGBA..base + DESCRIPTOR_FILL_RGBA + 4)
                    .ok_or(SceneError::Length)?,
            );
        } else if kind == KIND_LINE {
            fill_rgba.extend_from_slice(&[0, 0, 0, 0]);
        } else {
            fill_rgba.extend_from_slice(&[37, 99, 235, 255]);
        }
        if flags & DESCRIPTOR_FLAG_STROKE_RGBA != 0 {
            stroke_rgba.extend_from_slice(
                bytes
                    .get(base + DESCRIPTOR_STROKE_RGBA..base + DESCRIPTOR_STROKE_RGBA + 4)
                    .ok_or(SceneError::Length)?,
            );
        } else if kind == KIND_LINE {
            stroke_rgba.extend_from_slice(&[37, 99, 235, 255]);
        } else {
            stroke_rgba.extend_from_slice(&[0, 0, 0, 0]);
        }
        stroke_width.push(if authored_stroke.is_nan() {
            if kind == KIND_LINE {
                1.5
            } else {
                0.0
            }
        } else {
            authored_stroke
        });
        let xs = next_series_f64s(
            bytes,
            u32_at(bytes, base + DESCRIPTOR_X)?,
            count,
            data_start,
            &mut data_cursor,
        )?;
        let ys = next_series_f64s(
            bytes,
            u32_at(bytes, base + DESCRIPTOR_Y)?,
            count,
            data_start,
            &mut data_cursor,
        )?;
        let lower = if flags & DESCRIPTOR_FLAG_Y0 != 0 {
            Some(next_series_f64s(
                bytes,
                u32_at(bytes, base + DESCRIPTOR_Y0)?,
                count,
                data_start,
                &mut data_cursor,
            )?)
        } else {
            None
        };
        let upper = if flags & DESCRIPTOR_FLAG_Y1 != 0 {
            Some(next_series_f64s(
                bytes,
                u32_at(bytes, base + DESCRIPTOR_Y1)?,
                count,
                data_start,
                &mut data_cursor,
            )?)
        } else {
            None
        };
        let diameters = if flags & DESCRIPTOR_FLAG_DIAMETERS != 0 {
            Some(next_series_f64s(
                bytes,
                u32_at(bytes, base + DESCRIPTOR_DIAMETERS)?,
                count,
                data_start,
                &mut data_cursor,
            )?)
        } else {
            None
        };
        let authored_stable_ids = if flags & DESCRIPTOR_FLAG_STABLE_IDS != 0 {
            Some(next_series_u64s(
                bytes,
                u32_at(bytes, base + DESCRIPTOR_STABLE_IDS)?,
                count,
                data_start,
                &mut data_cursor,
            )?)
        } else {
            None
        };
        next_default_id = if let Some(ids) = &authored_stable_ids {
            ids.iter()
                .copied()
                .max()
                .unwrap_or(0)
                .checked_add(1)
                .ok_or(SceneError::Limit)?
                .max(next_default_id)
        } else {
            stable_base
                .checked_add(identity_count)
                .ok_or(SceneError::Limit)?
                .max(next_default_id)
        };
        let bar_half_width = if kind == KIND_BAR {
            Some(default_bar_half_width(&xs, domain_x_lo, domain_x_hi)?)
        } else {
            None
        };
        for index in 0..count {
            kinds.push(kind as u8);
            stable_ids.push(if let Some(ids) = &authored_stable_ids {
                ids[index]
            } else if matches!(kind, KIND_LINE | KIND_AREA) {
                stable_base
            } else {
                stable_base
                    .checked_add(index as u64)
                    .ok_or(SceneError::Limit)?
            });
            style_refs.push(series_index as u32);
            symbols.push(if kind == KIND_SCATTER {
                symbol as u8
            } else {
                0
            });
            diameter.push(if kind == KIND_SCATTER {
                diameters.as_ref().map(|values| values[index]).unwrap_or(
                    if scalar_diameter.is_nan() {
                        8.0
                    } else {
                        scalar_diameter
                    },
                )
            } else {
                0.0
            });
            match kind {
                KIND_SCATTER | KIND_LINE => {
                    x0.push(xs[index]);
                    y0.push(ys[index]);
                    x1.push(0.0);
                    y1.push(0.0);
                }
                KIND_BAR => {
                    let half_width = bar_half_width.ok_or(SceneError::Length)?;
                    x0.push(xs[index] - half_width);
                    x1.push(xs[index] + half_width);
                    y0.push(lower.as_ref().map(|v| v[index]).unwrap_or(0.0));
                    y1.push(upper.as_ref().map(|v| v[index]).unwrap_or(ys[index]));
                }
                KIND_AREA => {
                    x0.push(xs[index]);
                    x1.push(xs[index]);
                    y0.push(lower.as_ref().map(|v| v[index]).unwrap_or(0.0));
                    y1.push(upper.as_ref().map(|v| v[index]).unwrap_or(ys[index]));
                }
                _ => unreachable!(),
            }
        }
    }
    if kinds.len() != record_count || data_cursor != bytes.len() {
        return Err(SceneError::Length);
    }

    let packed_capacity = COMPILE_HEADER_BYTES
        .checked_add(record_count.checked_mul(56).ok_or(SceneError::Limit)?)
        .and_then(|value| value.checked_add(series_count.checked_mul(16)?))
        .and_then(|value| value.checked_add(text_bytes))
        .and_then(|value| value.checked_add(64))
        .ok_or(SceneError::Limit)?;
    let mut packed = Vec::new();
    packed
        .try_reserve_exact(packed_capacity)
        .map_err(|_| SceneError::Limit)?;
    packed.extend_from_slice(&bytes[..COMPILE_HEADER_BYTES]);
    packed[..4].copy_from_slice(COMPILE_MAGIC);
    packed[4..8].copy_from_slice(&COMPILE_VERSION.to_le_bytes());
    packed[16..20].copy_from_slice(&(record_count as u32).to_le_bytes());
    packed[20..24].copy_from_slice(&(series_count as u32).to_le_bytes());
    for offset in (168..COMPILE_HEADER_BYTES).step_by(4) {
        packed[offset..offset + 4].fill(0);
    }
    packed.extend_from_slice(&kinds);
    append_aligned_u64s(&mut packed, &stable_ids);
    append_aligned_u32s(&mut packed, &style_refs);
    append_aligned_f64s(&mut packed, &diameter);
    packed.extend_from_slice(&symbols);
    append_aligned_f64s(&mut packed, &x0);
    append_aligned_f64s(&mut packed, &y0);
    append_aligned_f64s(&mut packed, &x1);
    append_aligned_f64s(&mut packed, &y1);
    packed.extend_from_slice(&fill_rgba);
    packed.extend_from_slice(&stroke_rgba);
    append_aligned_f64s(&mut packed, &stroke_width);
    let text_start = descriptors_end;
    let text_end = text_start
        .checked_add(title_len + x_label_len + y_label_len)
        .ok_or(SceneError::Limit)?;
    packed.extend_from_slice(bytes.get(text_start..text_end).ok_or(SceneError::Length)?);
    compile_columns_request(&packed, true)
}

/// Decode either packed canonical columns (`XYCC`) or transferable typed
/// series (`XYTS`) and encode the canonical Scene batch.
pub fn compile_scene_request(
    bytes: &[u8],
    peak_budget: usize,
) -> Result<CompiledScene, SceneError> {
    if bytes.get(..4) == Some(SERIES_MAGIC) {
        compile_series_request(bytes, peak_budget)
    } else {
        compile_columns_request(bytes, false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pack_scatter() -> Vec<u8> {
        let mut out = vec![0u8; COMPILE_HEADER_BYTES];
        out[..4].copy_from_slice(COMPILE_MAGIC);
        out[4..8].copy_from_slice(&COMPILE_VERSION.to_le_bytes());
        out[8..12].copy_from_slice(&(COMPILE_HEADER_BYTES as u32).to_le_bytes());
        out[HEADER_FLAGS..HEADER_FLAGS + 4]
            .copy_from_slice(&HEADER_FLAG_AUTO_MARGINS.to_le_bytes());
        out[16..20].copy_from_slice(&1u32.to_le_bytes());
        out[20..24].copy_from_slice(&1u32.to_le_bytes());
        for (offset, value) in [
            (40, 320.0f64),
            (48, 240.0),
            (120, 0.0),
            (128, 1.0),
            (136, 1.0),
            (144, 0.0),
            (152, 1.0),
            (160, 1.0),
        ] {
            out[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        }
        out[88..96].copy_from_slice(&1u64.to_le_bytes());
        out[96..104].copy_from_slice(&2u64.to_le_bytes());
        out.extend_from_slice(&[0]); // kind scatter
        while !out.len().is_multiple_of(8) {
            out.push(0);
        }
        out.extend_from_slice(&7u64.to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        while !out.len().is_multiple_of(8) {
            out.push(0);
        }
        out.extend_from_slice(&8.0f64.to_le_bytes());
        out.push(0);
        while !out.len().is_multiple_of(8) {
            out.push(0);
        }
        for value in [0.5f64, 0.5, 0.0, 0.0] {
            out.extend_from_slice(&value.to_le_bytes());
        }
        out.extend_from_slice(&[37, 99, 235, 255, 0, 0, 0, 0]);
        while !out.len().is_multiple_of(8) {
            out.push(0);
        }
        out.extend_from_slice(&0.0f64.to_le_bytes());
        out
    }

    fn pack_typed_series() -> Vec<u8> {
        let data_start = COMPILE_HEADER_BYTES + SERIES_DESCRIPTOR_BYTES;
        let mut out = vec![0u8; data_start];
        out[..4].copy_from_slice(SERIES_MAGIC);
        out[4..8].copy_from_slice(&SERIES_VERSION.to_le_bytes());
        out[8..12].copy_from_slice(&(COMPILE_HEADER_BYTES as u32).to_le_bytes());
        out[HEADER_FLAGS..HEADER_FLAGS + 4]
            .copy_from_slice(&(HEADER_FLAG_AUTO_MARGINS | HEADER_FLAG_AUTO_DOMAIN).to_le_bytes());
        out[16..20].copy_from_slice(&1u32.to_le_bytes());
        out[20..24].copy_from_slice(&2u32.to_le_bytes());
        for (offset, value) in [
            (40, 320.0f64),
            (48, 240.0),
            (120, 0.0),
            (128, 1.0),
            (136, 1.0),
            (144, 0.0),
            (152, 1.0),
            (160, 1.0),
        ] {
            out[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        }
        out[88..96].copy_from_slice(&1u64.to_le_bytes());
        out[96..104].copy_from_slice(&2u64.to_le_bytes());
        let descriptor = COMPILE_HEADER_BYTES;
        out[descriptor..descriptor + 4].copy_from_slice(&0u32.to_le_bytes());
        out[descriptor + 8..descriptor + 12].copy_from_slice(&2u32.to_le_bytes());
        out[descriptor + 24..descriptor + 32].copy_from_slice(&f64::NAN.to_le_bytes());
        out[descriptor + 32..descriptor + 40].copy_from_slice(&f64::NAN.to_le_bytes());
        out[descriptor + 48..descriptor + 52].copy_from_slice(&(data_start as u32).to_le_bytes());
        out[descriptor + 52..descriptor + 56]
            .copy_from_slice(&((data_start + 16) as u32).to_le_bytes());
        for value in [0.25f64, 0.75, 0.5, 0.9] {
            out.extend_from_slice(&value.to_le_bytes());
        }
        out
    }

    #[test]
    fn packed_scatter_compiles_to_canonical_scene() {
        let compiled = compile_scene_request(&pack_scatter(), usize::MAX).unwrap();
        assert_eq!(compiled.records, 1);
        assert_eq!(compiled.styles, 1);
        assert_eq!(&compiled.bytes[..4], b"XYGS");
        assert_eq!(
            u32::from_le_bytes(compiled.bytes[4..8].try_into().unwrap()),
            scene::SCENE_VERSION
        );
        scene::validate_scene_batch(&compiled.bytes).unwrap();
    }

    #[test]
    fn unknown_flags_and_trailing_bytes_fail_closed() {
        let mut bad = pack_scatter();
        bad[12..16].copy_from_slice(&4u32.to_le_bytes()); // bit 2 is unknown
        assert!(compile_scene_request(&bad, usize::MAX).is_err());
        let mut trailing = pack_scatter();
        trailing.push(0);
        assert!(compile_scene_request(&trailing, usize::MAX).is_err());
    }

    #[test]
    fn auto_domain_overrides_header_lo_hi() {
        let mut packed = pack_scatter();
        packed[HEADER_FLAGS..HEADER_FLAGS + 4]
            .copy_from_slice(&(HEADER_FLAG_AUTO_MARGINS | HEADER_FLAG_AUTO_DOMAIN).to_le_bytes());
        // Header domains are deliberately wrong; geometry is at (0.5, 0.5).
        packed[120..128].copy_from_slice(&(-10.0f64).to_le_bytes());
        packed[128..136].copy_from_slice(&(-9.0f64).to_le_bytes());
        packed[144..152].copy_from_slice(&(-10.0f64).to_le_bytes());
        packed[152..160].copy_from_slice(&(-9.0f64).to_le_bytes());
        let compiled = compile_scene_request(&packed, usize::MAX).unwrap();
        scene::validate_scene_batch(&compiled.bytes).unwrap();
    }

    #[test]
    fn typed_series_expands_defaults_and_stable_ids_in_rust() {
        let request = pack_typed_series();
        let required = series_peak_bytes(request.len(), 2, 1).unwrap();
        assert!(compile_scene_request(&request, required - 1).is_err());
        let compiled = compile_scene_request(&request, required).unwrap();
        assert_eq!((compiled.records, compiled.styles), (2, 1));
        scene::validate_scene_batch(&compiled.bytes).unwrap();
        let first_record = scene::SCENE_BATCH_HEADER_BYTES + 16;
        assert_eq!(
            u64::from_le_bytes(
                compiled.bytes[first_record + 8..first_record + 16]
                    .try_into()
                    .unwrap()
            ),
            1
        );
        assert_eq!(
            u64::from_le_bytes(
                compiled.bytes[first_record + scene::SCENE_BATCH_RECORD_BYTES + 8
                    ..first_record + scene::SCENE_BATCH_RECORD_BYTES + 16]
                    .try_into()
                    .unwrap()
            ),
            2
        );
        assert_eq!(
            f64::from_le_bytes(
                compiled.bytes[first_record + 48..first_record + 56]
                    .try_into()
                    .unwrap()
            ),
            8.0
        );
        let painter = scene::SceneDocument::decode(&compiled.bytes)
            .unwrap()
            .to_browser_painter(1024 * 1024)
            .unwrap();
        assert_eq!(&painter[..4], b"XYPB");
        assert!(painter.windows(4).any(|rgba| rgba == [37, 99, 235, 255]));

        let mut malformed = pack_typed_series();
        malformed[COMPILE_HEADER_BYTES + 48..COMPILE_HEADER_BYTES + 52]
            .copy_from_slice(&0u32.to_le_bytes());
        assert!(compile_scene_request(&malformed, usize::MAX).is_err());

        let mut aliased = pack_typed_series();
        let x_offset = aliased[COMPILE_HEADER_BYTES + 48..COMPILE_HEADER_BYTES + 52].to_vec();
        aliased[COMPILE_HEADER_BYTES + 52..COMPILE_HEADER_BYTES + 56].copy_from_slice(&x_offset);
        assert!(compile_scene_request(&aliased, usize::MAX).is_err());

        let mut trailing = pack_typed_series();
        trailing.extend_from_slice(&0f64.to_le_bytes());
        assert!(compile_scene_request(&trailing, usize::MAX).is_err());

        let mut wrong_version = pack_typed_series();
        wrong_version[4..8].copy_from_slice(&(SERIES_VERSION + 1).to_le_bytes());
        assert!(matches!(
            compile_scene_request(&wrong_version, usize::MAX),
            Err(SceneError::Version)
        ));
        let mut wrong_header = pack_typed_series();
        wrong_header[8..12].copy_from_slice(&0u32.to_le_bytes());
        assert!(matches!(
            compile_scene_request(&wrong_header, usize::MAX),
            Err(SceneError::Length)
        ));
    }

    #[test]
    fn typed_series_preserves_transferred_per_record_stable_ids() {
        let mut request = pack_typed_series();
        let descriptor = COMPILE_HEADER_BYTES;
        let ids_offset = request.len();
        request[descriptor + DESCRIPTOR_FLAGS..descriptor + DESCRIPTOR_FLAGS + 4]
            .copy_from_slice(&DESCRIPTOR_FLAG_STABLE_IDS.to_le_bytes());
        request[descriptor + DESCRIPTOR_STABLE_IDS..descriptor + DESCRIPTOR_STABLE_IDS + 4]
            .copy_from_slice(&(ids_offset as u32).to_le_bytes());
        request.extend_from_slice(&91u64.to_le_bytes());
        request.extend_from_slice(&7u64.to_le_bytes());

        let compiled = compile_scene_request(&request, usize::MAX).unwrap();
        let first = scene::SCENE_BATCH_HEADER_BYTES + 16;
        let second = first + scene::SCENE_BATCH_RECORD_BYTES;
        assert_eq!(u64_at(&compiled.bytes, first + 8).unwrap(), 91);
        assert_eq!(u64_at(&compiled.bytes, second + 8).unwrap(), 7);

        let mut conflicting = request;
        let flags = DESCRIPTOR_FLAG_STABLE_IDS | DESCRIPTOR_FLAG_STABLE_ID_BASE;
        conflicting[descriptor + DESCRIPTOR_FLAGS..descriptor + DESCRIPTOR_FLAGS + 4]
            .copy_from_slice(&flags.to_le_bytes());
        assert!(matches!(
            compile_scene_request(&conflicting, usize::MAX),
            Err(SceneError::Length)
        ));
    }

    #[test]
    fn legacy_xycc_stable_ids_remain_run_boundaries() {
        let mut request = vec![0u8; COMPILE_HEADER_BYTES];
        request[..4].copy_from_slice(COMPILE_MAGIC);
        request[4..8].copy_from_slice(&COMPILE_VERSION.to_le_bytes());
        request[8..12].copy_from_slice(&(COMPILE_HEADER_BYTES as u32).to_le_bytes());
        request[16..20].copy_from_slice(&2u32.to_le_bytes());
        request[20..24].copy_from_slice(&1u32.to_le_bytes());
        for (offset, value) in [
            (40, 320.0f64),
            (48, 240.0),
            (120, 0.0),
            (128, 1.0),
            (136, 1.0),
            (144, 0.0),
            (152, 1.0),
            (160, 1.0),
        ] {
            request[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        }
        request[88..96].copy_from_slice(&1u64.to_le_bytes());
        request[96..104].copy_from_slice(&2u64.to_le_bytes());
        request.extend_from_slice(&[KIND_LINE as u8, KIND_LINE as u8]);
        append_aligned_u64s(&mut request, &[10, 11]);
        append_aligned_u32s(&mut request, &[0, 0]);
        append_aligned_f64s(&mut request, &[0.0, 0.0]);
        request.extend_from_slice(&[0, 0]);
        append_aligned_f64s(&mut request, &[0.1, 0.9]);
        append_aligned_f64s(&mut request, &[0.2, 0.8]);
        append_aligned_f64s(&mut request, &[0.0, 0.0]);
        append_aligned_f64s(&mut request, &[0.0, 0.0]);
        request.extend_from_slice(&[0, 0, 0, 0]);
        request.extend_from_slice(&[37, 99, 235, 255]);
        append_aligned_f64s(&mut request, &[1.5]);
        let compiled = compile_columns_request(&request, false).unwrap();
        assert_eq!(compiled.bytes[scene::SCENE_BATCH_HEADER_BYTES + 16 + 3], 0);
        let painter = scene::SceneDocument::decode(&compiled.bytes)
            .unwrap()
            .to_browser_painter(1 << 20)
            .unwrap();
        assert_eq!(u32::from_le_bytes(painter[20..24].try_into().unwrap()), 2);
    }

    #[test]
    fn default_bar_width_tracks_spacing_and_domain() {
        assert!(
            (default_bar_half_width(&[0.1, 0.2, 0.4], 0.0, 1.0).unwrap() - 0.04).abs()
                < f64::EPSILON
        );
        assert_eq!(
            default_bar_half_width(&[0.0, 1_000_000.0], 0.0, 1_000_000.0).unwrap(),
            400_000.0
        );
        assert_eq!(default_bar_half_width(&[5.0], 10.0, 0.0).unwrap(), 4.0);
        assert_eq!(default_bar_half_width(&[2.0, 2.0], 0.0, 10.0).unwrap(), 4.0);
        assert!(matches!(
            default_bar_half_width(&[f64::NAN], 0.0, 1.0),
            Err(SceneError::NonFinite)
        ));

        let mut request = pack_typed_series();
        request[COMPILE_HEADER_BYTES..COMPILE_HEADER_BYTES + 4]
            .copy_from_slice(&2u32.to_le_bytes());
        let compiled = compile_scene_request(&request, usize::MAX).unwrap();
        let first_record = scene::SCENE_BATCH_HEADER_BYTES + scene::SCENE_STYLE_RECORD_BYTES;
        let x0 = f64::from_le_bytes(
            compiled.bytes[first_record + 16..first_record + 24]
                .try_into()
                .unwrap(),
        );
        let x1 = f64::from_le_bytes(
            compiled.bytes[first_record + 32..first_record + 40]
                .try_into()
                .unwrap(),
        );
        assert!(x0.is_finite() && x1.is_finite() && x1 > x0);
    }
}
