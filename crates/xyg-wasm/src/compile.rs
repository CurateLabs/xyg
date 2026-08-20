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
    if flags & !FLAG_AUTO_MARGINS != 0 {
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
    let x_lo = f64_at(bytes, 120)?;
    let x_hi = f64_at(bytes, 128)?;
    let x_constant = f64_at(bytes, 136)?;
    let y_lo = f64_at(bytes, 144)?;
    let y_hi = f64_at(bytes, 152)?;
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
        bad[12..16].copy_from_slice(&2u32.to_le_bytes());
        assert!(compile_scene_request(&bad).is_err());
        let mut trailing = pack_scatter();
        trailing.push(0);
        assert!(compile_scene_request(&trailing).is_err());
    }
}
