//! Public static-export consumers from one encoded Scene (M2 #271).
//!
//! Hosts compile once, then call `scene_static_export` with a format code.
//! Rust owns SVG/PDF lowering, the raster display list, PNG/JPEG/WebP encode,
//! and JPEG flatten-over-white so Python and Node cannot drift on the public
//! router.

use crate::jpeg;
use crate::pdf;
use crate::raster;
use crate::scene::{SceneDocument, SceneError};
use crate::webp;

/// Public static format codes shared with the C ABI.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SceneStaticFormat {
    Svg = 0,
    Png = 1,
    Pdf = 2,
    Jpeg = 3,
    Webp = 4,
}

impl SceneStaticFormat {
    pub fn from_code(code: u32) -> Option<Self> {
        match code {
            0 => Some(Self::Svg),
            1 => Some(Self::Png),
            2 => Some(Self::Pdf),
            3 => Some(Self::Jpeg),
            4 => Some(Self::Webp),
            _ => None,
        }
    }
}

/// Why a public static export was rejected.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SceneStaticExportError {
    InvalidScene,
    Scale,
    Size,
    Raster,
    Encode,
}

impl From<SceneError> for SceneStaticExportError {
    fn from(_: SceneError) -> Self {
        Self::InvalidScene
    }
}

/// Render one encoded Scene to a public static format.
pub fn scene_static_export(
    encoded: &[u8],
    format: SceneStaticFormat,
    scale: f64,
    width: usize,
    height: usize,
    quality: i32,
) -> Result<Vec<u8>, SceneStaticExportError> {
    let document =
        SceneDocument::decode(encoded).map_err(|_| SceneStaticExportError::InvalidScene)?;
    match format {
        SceneStaticFormat::Svg => Ok(document.to_svg().into_bytes()),
        SceneStaticFormat::Pdf => {
            pdf::svg_to_pdf(&document.to_svg()).map_err(|_| SceneStaticExportError::Encode)
        }
        SceneStaticFormat::Png | SceneStaticFormat::Jpeg | SceneStaticFormat::Webp => {
            export_raster(document, format, scale, width, height, quality)
        }
    }
}

fn export_raster(
    document: SceneDocument,
    format: SceneStaticFormat,
    scale: f64,
    width: usize,
    height: usize,
    quality: i32,
) -> Result<Vec<u8>, SceneStaticExportError> {
    if !scale.is_finite() || scale <= 0.0 {
        return Err(SceneStaticExportError::Scale);
    }
    if width == 0 || height == 0 {
        return Err(SceneStaticExportError::Size);
    }
    let commands = document.to_raster_commands(scale)?;
    match format {
        SceneStaticFormat::Png => rasterize_png(&commands, width, height),
        SceneStaticFormat::Jpeg => {
            let rgba = rasterize_rgba(&commands, width, height)?;
            let rgb = flatten_rgba_over_white(&rgba, width, height)?;
            jpeg::encode_jpeg(&rgb, width, height, 3, quality)
                .map_err(|_| SceneStaticExportError::Encode)
        }
        SceneStaticFormat::Webp => {
            let rgba = rasterize_rgba(&commands, width, height)?;
            webp::encode_webp(&rgba, width, height, 4).map_err(|_| SceneStaticExportError::Encode)
        }
        SceneStaticFormat::Svg | SceneStaticFormat::Pdf => unreachable!(),
    }
}

fn rasterize_rgba(
    cmds: &[u8],
    width: usize,
    height: usize,
) -> Result<Vec<u8>, SceneStaticExportError> {
    let n = width
        .checked_mul(height)
        .and_then(|count| count.checked_mul(4))
        .ok_or(SceneStaticExportError::Size)?;
    let mut out = vec![0u8; n];
    if !raster::rasterize_into(cmds, width, height, &mut out) {
        return Err(SceneStaticExportError::Raster);
    }
    Ok(out)
}

fn rasterize_png(
    cmds: &[u8],
    width: usize,
    height: usize,
) -> Result<Vec<u8>, SceneStaticExportError> {
    let raw = width
        .checked_mul(height)
        .and_then(|count| count.checked_mul(4))
        .ok_or(SceneStaticExportError::Size)?;
    let cap = raw.saturating_add(raw / 8).saturating_add(65_536);
    let mut out = vec![0u8; cap.max(1)];
    let written = raster::rasterize_png_into(cmds, width, height, &mut out)
        .ok_or(SceneStaticExportError::Raster)?;
    if written > out.len() {
        return Err(SceneStaticExportError::Raster);
    }
    out.truncate(written);
    Ok(out)
}

/// Composite straight-alpha RGBA8 over white using the public JPEG rounding.
pub fn flatten_rgba_over_white(
    rgba: &[u8],
    width: usize,
    height: usize,
) -> Result<Vec<u8>, SceneStaticExportError> {
    let n = width
        .checked_mul(height)
        .ok_or(SceneStaticExportError::Size)?;
    let expected = n.checked_mul(4).ok_or(SceneStaticExportError::Size)?;
    if rgba.len() < expected {
        return Err(SceneStaticExportError::Size);
    }
    let mut rgb = vec![0u8; n * 3];
    for index in 0..n {
        let base = index * 4;
        let alpha = u16::from(rgba[base + 3]);
        let inv = 255 - alpha;
        for channel in 0..3 {
            let source = u16::from(rgba[base + channel]);
            rgb[index * 3 + channel] = ((source * alpha + 255 * inv + 127) / 255) as u8;
        }
    }
    Ok(rgb)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn format_codes_are_stable() {
        assert_eq!(
            SceneStaticFormat::from_code(0),
            Some(SceneStaticFormat::Svg)
        );
        assert_eq!(
            SceneStaticFormat::from_code(1),
            Some(SceneStaticFormat::Png)
        );
        assert_eq!(
            SceneStaticFormat::from_code(2),
            Some(SceneStaticFormat::Pdf)
        );
        assert_eq!(
            SceneStaticFormat::from_code(3),
            Some(SceneStaticFormat::Jpeg)
        );
        assert_eq!(
            SceneStaticFormat::from_code(4),
            Some(SceneStaticFormat::Webp)
        );
        assert_eq!(SceneStaticFormat::from_code(5), None);
    }

    #[test]
    fn jpeg_flatten_uses_plus_127_rounding_over_white() {
        let rgba = [10u8, 20, 30, 128];
        let rgb = flatten_rgba_over_white(&rgba, 1, 1).expect("flatten");
        let expected = |channel: u16| ((channel * 128 + 255 * 127 + 127) / 255) as u8;
        assert_eq!(rgb, [expected(10), expected(20), expected(30)]);
    }

    #[test]
    fn rejects_empty_scene_bytes() {
        let err =
            scene_static_export(b"", SceneStaticFormat::Svg, 1.0, 1, 1, 90).expect_err("empty");
        assert_eq!(err, SceneStaticExportError::InvalidScene);
    }
}
