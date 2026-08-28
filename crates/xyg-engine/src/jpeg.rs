//! Baseline sequential JFIF JPEG encoder (M2 #274).
//!
//! Ports `python/xyg/_jpeg.py`: 8-bit YCbCr 4:4:4, Annex K quantization scaled
//! with the libjpeg quality curve, Annex K Huffman tables, orthonormal 8-point
//! DCT-II, and round-half-away-from-zero. Alpha is ignored; the export host
//! composites over white before calling this encoder. Native hosts only
//! (`raster` feature).

use std::sync::OnceLock;

pub type JpegResult<T> = Result<T, String>;

const QUANT_LUMA: [i32; 64] = [
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113,
    92, 49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99,
];
const QUANT_CHROMA: [i32; 64] = [
    17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99, 24, 26, 56, 99, 99, 99, 99, 99,
    47, 66, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99,
];
const ZIGZAG: [usize; 64] = [
    0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20,
    13, 6, 7, 14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59,
    52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63,
];
const DC_LUMA_BITS: &[u8] = &[
    0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
];
const DC_LUMA_VALUES: &[u8] = &[
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B,
];
const DC_CHROMA_BITS: &[u8] = &[
    0x00, 0x03, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
];
const DC_CHROMA_VALUES: &[u8] = &[
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B,
];
const AC_LUMA_BITS: &[u8] = &[
    0x00, 0x02, 0x01, 0x03, 0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
];
const AC_LUMA_VALUES: &[u8] = &[
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07,
    0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0,
    0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
    0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
    0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7,
    0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5,
    0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
    0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8,
    0xF9, 0xFA,
];
const AC_CHROMA_BITS: &[u8] = &[
    0x00, 0x02, 0x01, 0x02, 0x04, 0x04, 0x03, 0x04, 0x07, 0x05, 0x04, 0x04, 0x00, 0x01, 0x02, 0x77,
];
const AC_CHROMA_VALUES: &[u8] = &[
    0x00, 0x01, 0x02, 0x03, 0x11, 0x04, 0x05, 0x21, 0x31, 0x06, 0x12, 0x41, 0x51, 0x07, 0x61, 0x71,
    0x13, 0x22, 0x32, 0x81, 0x08, 0x14, 0x42, 0x91, 0xA1, 0xB1, 0xC1, 0x09, 0x23, 0x33, 0x52, 0xF0,
    0x15, 0x62, 0x72, 0xD1, 0x0A, 0x16, 0x24, 0x34, 0xE1, 0x25, 0xF1, 0x17, 0x18, 0x19, 0x1A, 0x26,
    0x27, 0x28, 0x29, 0x2A, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48,
    0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68,
    0x69, 0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87,
    0x88, 0x89, 0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5,
    0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3,
    0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA,
    0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8,
    0xF9, 0xFA,
];

struct HuffTable {
    code: [u16; 256],
    len: [u8; 256],
}

fn huff_lookup(bits: &[u8], values: &[u8]) -> HuffTable {
    let mut table = HuffTable {
        code: [0; 256],
        len: [0; 256],
    };
    let mut code = 0u16;
    let mut k = 0usize;
    for length in 1..=16 {
        for _ in 0..bits[length - 1] {
            let symbol = values[k] as usize;
            table.code[symbol] = code;
            table.len[symbol] = length as u8;
            code += 1;
            k += 1;
        }
        code <<= 1;
    }
    table
}

fn huffman_tables() -> &'static [HuffTable; 4] {
    static TABLES: OnceLock<[HuffTable; 4]> = OnceLock::new();
    TABLES.get_or_init(|| {
        [
            huff_lookup(DC_LUMA_BITS, DC_LUMA_VALUES),
            huff_lookup(AC_LUMA_BITS, AC_LUMA_VALUES),
            huff_lookup(DC_CHROMA_BITS, DC_CHROMA_VALUES),
            huff_lookup(AC_CHROMA_BITS, AC_CHROMA_VALUES),
        ]
    })
}

fn dct_matrix() -> &'static [[f32; 8]; 8] {
    static DCT: OnceLock<[[f32; 8]; 8]> = OnceLock::new();
    DCT.get_or_init(|| {
        let mut d = [[0f32; 8]; 8];
        let inv_sqrt8 = (1.0f64 / 8.0f64.sqrt()) as f32;
        for freq in 0..8 {
            for spatial in 0..8 {
                let angle =
                    (2.0 * spatial as f64 + 1.0) * freq as f64 * std::f64::consts::PI / 16.0;
                d[freq][spatial] = (angle.cos() / 2.0) as f32;
            }
        }
        d[0] = [inv_sqrt8; 8];
        d
    })
}

struct BitWriter {
    bytes: Vec<u8>,
    acc: u64,
    nbits: u32,
}

impl BitWriter {
    fn new() -> Self {
        Self {
            bytes: Vec::new(),
            acc: 0,
            nbits: 0,
        }
    }

    fn write(&mut self, value: u32, n: u32) {
        if n == 0 {
            return;
        }
        self.acc = (self.acc << n) | u64::from(value & ((1u32 << n) - 1));
        self.nbits += n;
        while self.nbits >= 8 {
            self.nbits -= 8;
            let byte = (self.acc >> self.nbits) as u8;
            self.bytes.push(byte);
            if byte == 0xFF {
                self.bytes.push(0x00);
            }
        }
    }

    fn write_huff(&mut self, table: &HuffTable, symbol: u8) {
        let len = table.len[symbol as usize];
        self.write(table.code[symbol as usize] as u32, len as u32);
    }

    fn finish(mut self) -> Vec<u8> {
        if self.nbits > 0 {
            let pad = 8 - self.nbits;
            self.write((1u32 << pad) - 1, pad);
        }
        self.bytes
    }
}

fn bit_size(magnitude: i16) -> u8 {
    if magnitude == 0 {
        0
    } else {
        (magnitude.unsigned_abs() as u32).ilog2() as u8 + 1
    }
}

fn amplitude_bits(value: i16, size: u8) -> u32 {
    if size == 0 {
        return 0;
    }
    if value < 0 {
        (value as i32 + (1 << size) - 1) as u32
    } else {
        value as u32
    }
}

fn scaled_quant(base: &[i32; 64], quality: i32) -> [u8; 64] {
    let scale = if quality < 50 {
        5000 / quality
    } else {
        200 - 2 * quality
    };
    let mut out = [0u8; 64];
    for (i, &q) in base.iter().enumerate() {
        let v = (q * scale + 50) / 100;
        out[i] = v.clamp(1, 255) as u8;
    }
    out
}

fn zigzag_quant(natural: &[u8; 64]) -> [u8; 64] {
    let mut out = [0u8; 64];
    for (i, &idx) in ZIGZAG.iter().enumerate() {
        out[i] = natural[idx];
    }
    out
}

fn sample_rgb(
    pixels: &[u8],
    width: usize,
    height: usize,
    channels: usize,
    x: usize,
    y: usize,
) -> (u8, u8, u8) {
    let sx = x.min(width - 1);
    let sy = y.min(height - 1);
    let i = (sy * width + sx) * channels;
    (pixels[i], pixels[i + 1], pixels[i + 2])
}

fn ycbcr(r: f32, g: f32, b: f32) -> (f32, f32, f32) {
    (
        0.299 * r + 0.587 * g + 0.114 * b - 128.0,
        -0.168736 * r - 0.331264 * g + 0.5 * b,
        0.5 * r - 0.418688 * g - 0.081312 * b,
    )
}

fn fdct_block(block: &[[f32; 8]; 8]) -> [f32; 64] {
    let d = dct_matrix();
    let mut tmp = [[0f32; 8]; 8];
    for i in 0..8 {
        for j in 0..8 {
            let mut acc = 0f32;
            for k in 0..8 {
                acc += d[i][k] * block[k][j];
            }
            tmp[i][j] = acc;
        }
    }
    let mut out = [0f32; 64];
    for i in 0..8 {
        for p in 0..8 {
            let mut acc = 0f32;
            for j in 0..8 {
                acc += tmp[i][j] * d[p][j];
            }
            out[i * 8 + p] = acc;
        }
    }
    out
}

fn quantize_block(coef: &[f32; 64], q_zz: &[u8; 64]) -> [i16; 64] {
    let mut out = [0i16; 64];
    for (i, &idx) in ZIGZAG.iter().enumerate() {
        let mut scaled = coef[idx] / q_zz[i] as f32;
        scaled += scaled.signum() * 0.5;
        let mut q = scaled.trunc() as i16;
        if i > 0 {
            q = q.clamp(-1023, 1023);
        }
        out[i] = q;
    }
    out
}

fn encode_block(
    writer: &mut BitWriter,
    zz: &[i16; 64],
    prev_dc: i16,
    dc_tbl: &HuffTable,
    ac_tbl: &HuffTable,
) -> i16 {
    let dc = zz[0];
    let diff = dc.wrapping_sub(prev_dc);
    let dsize = bit_size(diff);
    writer.write_huff(dc_tbl, dsize);
    writer.write(amplitude_bits(diff, dsize), dsize as u32);

    let mut run = 0u8;
    for pos in 1..64 {
        let v = zz[pos];
        if v == 0 {
            run += 1;
            continue;
        }
        while run >= 16 {
            writer.write_huff(ac_tbl, 0xF0);
            run -= 16;
        }
        let size = bit_size(v);
        writer.write_huff(ac_tbl, (run << 4) | size);
        writer.write(amplitude_bits(v, size), size as u32);
        run = 0;
    }
    if zz[63] == 0 {
        writer.write_huff(ac_tbl, 0);
    }
    dc
}

fn headers(h: usize, w: usize, qy_zz: &[u8; 64], qc_zz: &[u8; 64]) -> Vec<u8> {
    let mut out = Vec::with_capacity(600);
    out.extend_from_slice(&[0xFF, 0xD8]);
    out.extend_from_slice(&[
        0xFF, 0xE0, 0x00, 0x10, b'J', b'F', b'I', b'F', 0x00, 0x01, 0x02, 0x01, 0x00, 0x60, 0x00,
        0x60, 0x00, 0x00,
    ]);
    out.extend_from_slice(&[0xFF, 0xDB, 0x00, 0x84, 0x00]);
    out.extend_from_slice(qy_zz);
    out.push(0x01);
    out.extend_from_slice(qc_zz);
    out.extend_from_slice(&[
        0xFF,
        0xC0,
        0x00,
        0x11,
        0x08,
        (h >> 8) as u8,
        (h & 0xFF) as u8,
        (w >> 8) as u8,
        (w & 0xFF) as u8,
        0x03,
        0x01,
        0x11,
        0x00,
        0x02,
        0x11,
        0x01,
        0x03,
        0x11,
        0x01,
    ]);
    let dht_payload = [
        (0x00u8, DC_LUMA_BITS, DC_LUMA_VALUES),
        (0x10, AC_LUMA_BITS, AC_LUMA_VALUES),
        (0x01, DC_CHROMA_BITS, DC_CHROMA_VALUES),
        (0x11, AC_CHROMA_BITS, AC_CHROMA_VALUES),
    ];
    let dht_len = 2 + dht_payload
        .iter()
        .map(|(_, bits, values)| 1 + bits.len() + values.len())
        .sum::<usize>();
    out.extend_from_slice(&[0xFF, 0xC4, (dht_len >> 8) as u8, (dht_len & 0xFF) as u8]);
    for (cls_id, bits, values) in dht_payload {
        out.push(cls_id);
        out.extend_from_slice(bits);
        out.extend_from_slice(values);
    }
    out.extend_from_slice(&[
        0xFF, 0xDA, 0x00, 0x0C, 0x03, 0x01, 0x00, 0x02, 0x11, 0x03, 0x11, 0x00, 0x3F, 0x00,
    ]);
    out
}

/// Encode packed RGB or RGBA8 pixels as a baseline JFIF JPEG.
pub fn encode_jpeg(
    pixels: &[u8],
    width: usize,
    height: usize,
    channels: usize,
    quality: i32,
) -> JpegResult<Vec<u8>> {
    if !(1..=100).contains(&quality) {
        return Err(format!("quality must be in 1..100, got {quality}"));
    }
    if channels != 3 && channels != 4 {
        return Err(format!(
            "JPEG image must be (h, w, 4) RGBA or (h, w, 3) RGB, got channels={channels}"
        ));
    }
    if width == 0 || height == 0 {
        return Err("JPEG image must be non-empty".into());
    }
    if width > 65535 || height > 65535 {
        return Err("JPEG dimensions are limited to 65535".into());
    }
    let expected = width
        .checked_mul(height)
        .and_then(|n| n.checked_mul(channels))
        .ok_or_else(|| "JPEG image must be non-empty".to_string())?;
    if pixels.len() < expected {
        return Err("JPEG pixel buffer length does not match width*height*channels".into());
    }

    let qy = zigzag_quant(&scaled_quant(&QUANT_LUMA, quality));
    let qc = zigzag_quant(&scaled_quant(&QUANT_CHROMA, quality));
    let tables = huffman_tables();
    let bw = width.div_ceil(8);
    let bh = height.div_ceil(8);
    let mut writer = BitWriter::new();
    let mut prev_dc = [0i16; 3];

    for by in 0..bh {
        for bx in 0..bw {
            for comp in 0..3 {
                let mut block = [[0f32; 8]; 8];
                for row in 0..8 {
                    for col in 0..8 {
                        let (r, g, b) =
                            sample_rgb(pixels, width, height, channels, bx * 8 + col, by * 8 + row);
                        let (y, cb, cr) = ycbcr(r as f32, g as f32, b as f32);
                        block[row][col] = match comp {
                            0 => y,
                            1 => cb,
                            _ => cr,
                        };
                    }
                }
                let q_zz = if comp == 0 { &qy } else { &qc };
                let zz = quantize_block(&fdct_block(&block), q_zz);
                let (dc_tbl, ac_tbl) = if comp == 0 {
                    (&tables[0], &tables[1])
                } else {
                    (&tables[2], &tables[3])
                };
                prev_dc[comp] = encode_block(&mut writer, &zz, prev_dc[comp], dc_tbl, ac_tbl);
            }
        }
    }

    let mut out = headers(height, width, &qy, &qc);
    out.extend_from_slice(&writer.finish());
    out.extend_from_slice(&[0xFF, 0xD9]);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_invalid_quality_and_size() {
        let px = [0u8; 12];
        assert!(encode_jpeg(&px, 2, 2, 3, 0).is_err());
        assert!(encode_jpeg(&px, 2, 2, 3, 101).is_err());
        assert!(encode_jpeg(&px, 0, 2, 3, 90).is_err());
        assert!(encode_jpeg(&px, 2, 2, 2, 90).is_err());
    }

    #[test]
    fn flat_pixel_is_jfif() {
        let px = [100u8, 100, 100, 255];
        let jpeg = encode_jpeg(&px, 1, 1, 4, 90).unwrap();
        assert_eq!(&jpeg[..2], b"\xff\xd8");
        assert_eq!(&jpeg[jpeg.len() - 2..], b"\xff\xd9");
        assert_eq!(&jpeg[6..11], b"JFIF\x00");
    }

    #[test]
    fn rgb_matches_rgba_when_alpha_ignored() {
        let rgb = [10u8, 20, 30, 40, 50, 60];
        let rgba = [10u8, 20, 30, 1, 40, 50, 60, 2];
        assert_eq!(
            encode_jpeg(&rgb, 2, 1, 3, 90).unwrap(),
            encode_jpeg(&rgba, 2, 1, 4, 90).unwrap()
        );
    }

    #[test]
    fn deterministic() {
        let mut px = vec![0u8; 16 * 16 * 3];
        for (i, v) in px.iter_mut().enumerate() {
            *v = (i % 251) as u8;
        }
        assert_eq!(
            encode_jpeg(&px, 16, 16, 3, 90).unwrap(),
            encode_jpeg(&px, 16, 16, 3, 90).unwrap()
        );
    }
}
