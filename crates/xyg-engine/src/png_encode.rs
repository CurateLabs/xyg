//! Filter-0 PNG encoder for host static export (M2 #274).
//!
//! Ports `python/xyg/_png.py`: RGBA8 truecolor (color type 6) and auto
//! indexed-palette (color type 3 + `tRNS`) when the image has ≤256 distinct
//! RGBA colors. Scanlines use PNG filter type None (0) so SVG-embedded density
//! rasters and size-oriented `optimize=True` exports stay compact without the
//! fused rasterizer's Up filter. Native hosts only (`raster` feature).

use std::collections::{HashMap, HashSet};
use std::io::Write;

use flate2::write::ZlibEncoder;
use flate2::Compression;

pub type PngResult<T> = Result<T, String>;

/// `mode = 0`: auto indexed when ≤256 unique RGBA colors, else truecolor.
pub const PNG_MODE_AUTO: i32 = 0;
/// `mode = 1`: force RGBA8 truecolor (color type 6).
pub const PNG_MODE_TRUECOLOR: i32 = 1;

const MAX_DIM: usize = 65_535;
const PALETTE_LIMIT: usize = 256;
const PROBE_THRESHOLD: usize = 65_536;
const PNG_SIGNATURE: &[u8] = b"\x89PNG\r\n\x1a\n";

/// ISO 3309 / PNG CRC table (same polynomial as `zlib.crc32`).
const CRC_TABLE: [u32; 256] = {
    let mut table = [0u32; 256];
    let mut n = 0;
    while n < 256 {
        let mut c = n as u32;
        let mut k = 0;
        while k < 8 {
            c = if c & 1 == 1 {
                0xEDB88320 ^ (c >> 1)
            } else {
                c >> 1
            };
            k += 1;
        }
        table[n] = c;
        n += 1;
    }
    table
};

fn crc32_parts(parts: &[&[u8]]) -> u32 {
    let mut c = 0xFFFF_FFFFu32;
    for part in parts {
        for &b in *part {
            c = CRC_TABLE[((c ^ u32::from(b)) & 0xFF) as usize] ^ (c >> 8);
        }
    }
    c ^ 0xFFFF_FFFF
}

fn push_chunk(out: &mut Vec<u8>, tag: &[u8; 4], data: &[u8]) {
    out.extend_from_slice(&(data.len() as u32).to_be_bytes());
    out.extend_from_slice(tag);
    out.extend_from_slice(data);
    out.extend_from_slice(&crc32_parts(&[tag.as_slice(), data]).to_be_bytes());
}

fn zlib_compress(data: &[u8], level: u32) -> PngResult<Vec<u8>> {
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::new(level));
    encoder
        .write_all(data)
        .and_then(|_| encoder.finish())
        .map_err(|err| format!("PNG zlib compress failed: {err}"))
}

fn pixel_key(pixels: &[u8], index: usize, channels: usize) -> u32 {
    let offset = index * channels;
    let r = pixels[offset];
    let g = pixels[offset + 1];
    let b = pixels[offset + 2];
    let a = if channels == 4 {
        pixels[offset + 3]
    } else {
        255
    };
    u32::from_le_bytes([r, g, b, a])
}

fn unique_sorted_keys(keys: impl Iterator<Item = u32>) -> Option<Vec<u32>> {
    let mut seen = HashSet::new();
    for key in keys {
        seen.insert(key);
        if seen.len() > PALETTE_LIMIT {
            return None;
        }
    }
    let mut unique: Vec<u32> = seen.into_iter().collect();
    unique.sort_unstable();
    Some(unique)
}

fn ihdr(width: usize, height: usize, color_type: u8) -> [u8; 13] {
    let mut data = [0u8; 13];
    data[..4].copy_from_slice(&(width as u32).to_be_bytes());
    data[4..8].copy_from_slice(&(height as u32).to_be_bytes());
    data[8] = 8;
    data[9] = color_type;
    data
}

fn finish_png(ihdr: &[u8], extra: &[(&[u8; 4], &[u8])], idat: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(8 + 12 + ihdr.len() + 12 + idat.len() + 12);
    out.extend_from_slice(PNG_SIGNATURE);
    push_chunk(&mut out, b"IHDR", ihdr);
    for (tag, data) in extra {
        push_chunk(&mut out, tag, data);
    }
    push_chunk(&mut out, b"IDAT", idat);
    push_chunk(&mut out, b"IEND", &[]);
    out
}

fn encode_truecolor(
    pixels: &[u8],
    width: usize,
    height: usize,
    channels: usize,
    compression: u32,
) -> PngResult<Vec<u8>> {
    let stride = width * 4;
    let mut rows = vec![0u8; height * (stride + 1)];
    for y in 0..height {
        let row = y * (stride + 1);
        rows[row] = 0;
        if channels == 4 {
            let src = y * stride;
            rows[row + 1..row + 1 + stride].copy_from_slice(&pixels[src..src + stride]);
        } else {
            for x in 0..width {
                let src = (y * width + x) * 3;
                let dst = row + 1 + x * 4;
                rows[dst] = pixels[src];
                rows[dst + 1] = pixels[src + 1];
                rows[dst + 2] = pixels[src + 2];
                rows[dst + 3] = 255;
            }
        }
    }
    let idat = zlib_compress(&rows, compression)?;
    Ok(finish_png(&ihdr(width, height, 6), &[], &idat))
}

fn encode_indexed(
    pixels: &[u8],
    width: usize,
    height: usize,
    channels: usize,
    palette: &[u32],
    compression: u32,
) -> PngResult<Vec<u8>> {
    let mut index = HashMap::with_capacity(palette.len());
    for (i, key) in palette.iter().copied().enumerate() {
        index.insert(key, i as u8);
    }
    let mut rows = vec![0u8; height * (width + 1)];
    for y in 0..height {
        let row = y * (width + 1);
        rows[row] = 0;
        for x in 0..width {
            let key = pixel_key(pixels, y * width + x, channels);
            rows[row + 1 + x] = *index
                .get(&key)
                .ok_or_else(|| "PNG palette missing key".to_string())?;
        }
    }
    let mut plte = Vec::with_capacity(palette.len() * 3);
    let mut trns = Vec::with_capacity(palette.len());
    for key in palette {
        let [r, g, b, a] = key.to_le_bytes();
        plte.extend_from_slice(&[r, g, b]);
        trns.push(a);
    }
    let idat = zlib_compress(&rows, compression)?;
    Ok(finish_png(
        &ihdr(width, height, 3),
        &[(b"PLTE", plte.as_slice()), (b"tRNS", trns.as_slice())],
        &idat,
    ))
}

/// Encode packed RGB or RGBA8 pixels as a PNG.
///
/// `mode` 0 auto-selects indexed palette (≤256 unique LE RGBA keys, matching
/// NumPy `uint32` views on little-endian hosts) else truecolor. `mode` 1
/// forces truecolor. `compression` is the zlib level in `0..=9`.
pub fn encode_png(
    pixels: &[u8],
    width: usize,
    height: usize,
    channels: usize,
    mode: i32,
    compression: i32,
) -> PngResult<Vec<u8>> {
    if mode != PNG_MODE_AUTO && mode != PNG_MODE_TRUECOLOR {
        return Err(format!(
            "PNG mode must be 0 (auto) or 1 (truecolor), got {mode}"
        ));
    }
    if !(0..=9).contains(&compression) {
        return Err(format!(
            "PNG compression must be in 0..9, got {compression}"
        ));
    }
    if channels != 3 && channels != 4 {
        return Err(format!(
            "PNG image must be (h, w, 4) RGBA or (h, w, 3) RGB, got channels={channels}"
        ));
    }
    if width == 0 || height == 0 {
        return Err("PNG image must be non-empty".into());
    }
    if width > MAX_DIM || height > MAX_DIM {
        return Err("PNG dimensions are limited to 65535".into());
    }
    let expected = width
        .checked_mul(height)
        .and_then(|n| n.checked_mul(channels))
        .ok_or_else(|| "PNG image must be non-empty".to_string())?;
    if pixels.len() < expected {
        return Err("PNG pixel buffer length does not match width*height*channels".into());
    }
    let pixels = &pixels[..expected];
    let level = compression as u32;
    if mode == PNG_MODE_TRUECOLOR {
        return encode_truecolor(pixels, width, height, channels, level);
    }
    let pixel_count = width * height;
    if pixel_count > PROBE_THRESHOLD {
        let step = pixel_count / PROBE_THRESHOLD;
        let probe = (0..pixel_count)
            .step_by(step)
            .map(|i| pixel_key(pixels, i, channels));
        if unique_sorted_keys(probe).is_none() {
            return encode_truecolor(pixels, width, height, channels, level);
        }
    }
    match unique_sorted_keys((0..pixel_count).map(|i| pixel_key(pixels, i, channels))) {
        Some(palette) => encode_indexed(pixels, width, height, channels, &palette, level),
        None => encode_truecolor(pixels, width, height, channels, level),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn decode_rgba(bytes: &[u8]) -> (u32, u32, Vec<u8>) {
        let mut decoder = png::Decoder::new(Cursor::new(bytes));
        decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::ALPHA);
        let mut reader = decoder.read_info().unwrap();
        let mut buf = vec![0; reader.output_buffer_size().unwrap()];
        let info = reader.next_frame(&mut buf).unwrap();
        buf.truncate(info.buffer_size());
        let mut rgba = Vec::with_capacity((info.width * info.height * 4) as usize);
        match info.color_type {
            png::ColorType::Rgba => rgba.extend_from_slice(&buf),
            png::ColorType::Rgb => {
                for chunk in buf.chunks_exact(3) {
                    rgba.extend_from_slice(&[chunk[0], chunk[1], chunk[2], 255]);
                }
            }
            png::ColorType::Grayscale => {
                for &v in &buf {
                    rgba.extend_from_slice(&[v, v, v, 255]);
                }
            }
            png::ColorType::GrayscaleAlpha => {
                for chunk in buf.chunks_exact(2) {
                    rgba.extend_from_slice(&[chunk[0], chunk[0], chunk[0], chunk[1]]);
                }
            }
            png::ColorType::Indexed => panic!("indexed PNG was not expanded"),
        }
        (info.width, info.height, rgba)
    }

    fn color_type(bytes: &[u8]) -> u8 {
        assert_eq!(&bytes[..8], PNG_SIGNATURE);
        assert_eq!(&bytes[12..16], b"IHDR");
        bytes[25]
    }

    #[test]
    fn rejects_bad_mode_compression_and_empty() {
        let px = [255u8, 0, 0, 255];
        assert!(encode_png(&px, 1, 1, 4, 2, 6).is_err());
        assert!(encode_png(&px, 1, 1, 4, 0, 10).is_err());
        assert!(encode_png(&px, 0, 1, 4, 0, 6).is_err());
        assert!(encode_png(&px, 1, 1, 2, 0, 6).is_err());
        assert!(encode_png(&px, MAX_DIM + 1, 1, 4, 1, 6).is_err());
    }

    #[test]
    fn truecolor_roundtrips_through_png_crate() {
        let px = [255u8, 0, 0, 128, 0, 255, 0, 255];
        let out = encode_png(&px, 2, 1, 4, PNG_MODE_TRUECOLOR, 6).unwrap();
        assert_eq!(color_type(&out), 6);
        let (w, h, rgba) = decode_rgba(&out);
        assert_eq!((w, h), (2, 1));
        assert_eq!(rgba, px);
    }

    #[test]
    fn auto_selects_indexed_for_few_colors() {
        let mut px = vec![255u8, 0, 0, 255];
        px.extend_from_slice(&[0, 0, 255, 255]);
        let out = encode_png(&px, 2, 1, 4, PNG_MODE_AUTO, 6).unwrap();
        assert_eq!(color_type(&out), 3);
        let (w, h, rgba) = decode_rgba(&out);
        assert_eq!((w, h), (2, 1));
        assert_eq!(rgba, px);
    }

    #[test]
    fn auto_selects_truecolor_past_256_colors() {
        let mut px = Vec::with_capacity(257 * 4);
        for i in 0..257u16 {
            px.extend_from_slice(&[i as u8, (i >> 8) as u8, 0, 255]);
        }
        let out = encode_png(&px, 257, 1, 4, PNG_MODE_AUTO, 6).unwrap();
        assert_eq!(color_type(&out), 6);
        let (_, _, rgba) = decode_rgba(&out);
        assert_eq!(rgba, px);
    }

    #[test]
    fn rgb_matches_opaque_rgba() {
        let rgb = [10u8, 20, 30, 40, 50, 60];
        let rgba = [10u8, 20, 30, 255, 40, 50, 60, 255];
        assert_eq!(
            encode_png(&rgb, 2, 1, 3, PNG_MODE_TRUECOLOR, 6).unwrap(),
            encode_png(&rgba, 2, 1, 4, PNG_MODE_TRUECOLOR, 6).unwrap()
        );
    }

    #[test]
    fn filter_none_on_truecolor_scanlines() {
        let px = [1u8, 2, 3, 4];
        let out = encode_png(&px, 1, 1, 4, PNG_MODE_TRUECOLOR, 0).unwrap();
        // compression 0 still zlib-wraps; inflate and check the filter byte.
        let idat_start = out.windows(4).position(|w| w == b"IDAT").expect("IDAT") + 4;
        let len =
            u32::from_be_bytes(out[idat_start - 8..idat_start - 4].try_into().unwrap()) as usize;
        let compressed = &out[idat_start..idat_start + len];
        let mut raw = Vec::new();
        {
            use flate2::read::ZlibDecoder;
            use std::io::Read;
            ZlibDecoder::new(compressed).read_to_end(&mut raw).unwrap();
        }
        assert_eq!(raw[0], 0);
        assert_eq!(&raw[1..], &px);
    }
}
