//! Packed typed-column compile requests for the direct-browser WASM host.
//!
//! The Worker copies one little-endian `XYCC` request into the staging arena.
//! Rust validates lengths and scale fields, then builds the same canonical
//! Scene batch that native hosts encode through `xyg_scene_batch_encode`.

use xyg_engine::scene::{
    self, AxisScale, CartesianLayoutRequest, PlotLayout, ScaleKind, SceneBatch, SceneChromeStyle,
    SceneChromeText, SceneError,
};

pub const COMPILE_MAGIC: &[u8; 4] = b"XYCC";
pub const COMPILE_VERSION: u32 = 1;
pub const COMPILE_HEADER_BYTES: usize = 192;
pub const FLAG_AUTO_MARGINS: u32 = 1;
/// When set, Rust derives axis domains from finite column values so the browser
/// main thread does not scan O(N) data for lo/hi.
pub const FLAG_AUTO_DOMAIN: u32 = 2;
const FLAG_KNOWN: u32 = FLAG_AUTO_MARGINS | FLAG_AUTO_DOMAIN;

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
        if matches!(kind, 2 | 3) {
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

/// Decode one packed typed-column request and encode the canonical Scene batch.
pub fn compile_scene_request(bytes: &[u8]) -> Result<CompiledScene, SceneError> {
    if bytes.len() < COMPILE_HEADER_BYTES {
        return Err(SceneError::Length);
    }
    if &bytes[..4] != COMPILE_MAGIC {
        return Err(SceneError::Length);
    }
    if u32_at(bytes, 4)? != COMPILE_VERSION {
        return Err(SceneError::Version);
    }
    if u32_at(bytes, 8)? as usize != COMPILE_HEADER_BYTES {
        return Err(SceneError::Length);
    }
    let flags = u32_at(bytes, 12)?;
    if flags & !FLAG_KNOWN != 0 {
        return Err(SceneError::Length);
    }
    let record_count = u32_at(bytes, 16)? as usize;
    let style_count = u32_at(bytes, 20)? as usize;
    let title_len = u32_at(bytes, 24)? as usize;
    let x_label_len = u32_at(bytes, 28)? as usize;
    let y_label_len = u32_at(bytes, 32)? as usize;
    if u32_at(bytes, 36)? != 0 {
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

    let viewport_width = f64_at(bytes, 40)?;
    let viewport_height = f64_at(bytes, 48)?;
    let margin_left = f64_at(bytes, 56)?;
    let margin_right = f64_at(bytes, 64)?;
    let margin_top = f64_at(bytes, 72)?;
    let margin_bottom = f64_at(bytes, 80)?;
    let x_axis_id = u64_at(bytes, 88)?;
    let y_axis_id = u64_at(bytes, 96)?;
    let x_kind = scale_kind(u32_at(bytes, 104)?)?;
    let y_kind = scale_kind(u32_at(bytes, 108)?)?;
    let x_mask = u32_at(bytes, 112)?;
    let y_mask = u32_at(bytes, 116)?;
    if !matches!(x_mask, 0 | 1) || !matches!(y_mask, 0 | 1) {
        return Err(SceneError::Length);
    }
    let mut x_lo = f64_at(bytes, 120)?;
    let mut x_hi = f64_at(bytes, 128)?;
    let x_constant = f64_at(bytes, 136)?;
    let mut y_lo = f64_at(bytes, 144)?;
    let mut y_hi = f64_at(bytes, 152)?;
    let y_constant = f64_at(bytes, 160)?;
    for reserved in (168..COMPILE_HEADER_BYTES).step_by(4) {
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

    if flags & FLAG_AUTO_DOMAIN != 0 {
        let Some(domain) = auto_domain_from_columns(&kinds, &x0, &y0, &x1, &y1) else {
            return Err(SceneError::NonFinite);
        };
        x_lo = domain.0;
        x_hi = domain.1;
        y_lo = domain.2;
        y_hi = domain.3;
    }

    let (margin_left, margin_right, margin_top, margin_bottom) =
        if flags & FLAG_AUTO_MARGINS != 0 {
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
    let batch = SceneBatch::new_with_chrome(
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
    )?;
    Ok(CompiledScene {
        records: record_count,
        styles: style_count,
        bytes: batch.encode(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pack_scatter() -> Vec<u8> {
        let mut out = vec![0u8; COMPILE_HEADER_BYTES];
        out[..4].copy_from_slice(COMPILE_MAGIC);
        out[4..8].copy_from_slice(&COMPILE_VERSION.to_le_bytes());
        out[8..12].copy_from_slice(&(COMPILE_HEADER_BYTES as u32).to_le_bytes());
        out[12..16].copy_from_slice(&FLAG_AUTO_MARGINS.to_le_bytes());
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

    #[test]
    fn packed_scatter_compiles_to_canonical_scene() {
        let compiled = compile_scene_request(&pack_scatter()).unwrap();
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
        assert!(compile_scene_request(&bad).is_err());
        let mut trailing = pack_scatter();
        trailing.push(0);
        assert!(compile_scene_request(&trailing).is_err());
    }

    #[test]
    fn auto_domain_overrides_header_lo_hi() {
        let mut packed = pack_scatter();
        packed[12..16].copy_from_slice(&(FLAG_AUTO_MARGINS | FLAG_AUTO_DOMAIN).to_le_bytes());
        // Header domains are deliberately wrong; geometry is at (0.5, 0.5).
        packed[120..128].copy_from_slice(&(-10.0f64).to_le_bytes());
        packed[128..136].copy_from_slice(&(-9.0f64).to_le_bytes());
        packed[144..152].copy_from_slice(&(-10.0f64).to_le_bytes());
        packed[152..160].copy_from_slice(&(-9.0f64).to_le_bytes());
        let compiled = compile_scene_request(&packed).unwrap();
        scene::validate_scene_batch(&compiled.bytes).unwrap();
    }
}
