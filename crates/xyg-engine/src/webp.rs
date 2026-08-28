//! Lossless WebP (VP8L) encoder for static export (M2 #274).
//!
//! Ports `python/xyg/_webp.py`: simple lossless subset (no transforms, no
//! color cache, one meta prefix group), distance-1 LZ77 runs, and
//! length-limited canonical prefix codes. Round-trips are bit-exact through
//! libwebp, alpha included. Native hosts only (`raster` feature).

const MAX_DIM: usize = 1 << 14;
const MAX_RUN: usize = 4096;
const GREEN_ALPHABET: usize = 256 + 24;
const DIST_ALPHABET: usize = 40;
const CODE_LENGTH_ORDER: [usize; 19] = [
    17, 18, 0, 1, 2, 3, 4, 5, 16, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
];

pub type WebpResult<T> = Result<T, String>;

struct BitSink {
    values: Vec<u64>,
    nbits: Vec<u8>,
}

impl BitSink {
    fn new() -> Self {
        Self {
            values: Vec::new(),
            nbits: Vec::new(),
        }
    }

    fn put(&mut self, value: u64, n: u8) {
        self.values.push(value);
        self.nbits.push(n);
    }

    fn pack_lsb(self) -> Vec<u8> {
        let mut acc = 0u64;
        let mut nacc = 0u32;
        let mut out = Vec::new();
        for (value, n) in self.values.into_iter().zip(self.nbits) {
            if n == 0 {
                continue;
            }
            acc |= (value & ((1u64 << n) - 1)) << nacc;
            nacc += u32::from(n);
            while nacc >= 8 {
                out.push((acc & 0xFF) as u8);
                acc >>= 8;
                nacc -= 8;
            }
        }
        if nacc > 0 {
            out.push((acc & 0xFF) as u8);
        }
        out
    }
}

fn length_prefix(len: usize) -> (u16, u8, u16) {
    if len <= 4 {
        return ((len - 1) as u16, 0, 0);
    }
    let d = len - 1;
    let hb = d.ilog2();
    let code = (2 * hb + ((d as u32 >> (hb - 1)) & 1)) as u16;
    let ebits = (hb - 1) as u8;
    let extra = (d as u32 & ((1u32 << (hb - 1)) - 1)) as u16;
    (code, ebits, extra)
}

fn limited_lengths(freqs: &[u32], limit: usize) -> Vec<u8> {
    let mut lengths = vec![0u8; freqs.len()];
    let used: Vec<usize> = freqs
        .iter()
        .enumerate()
        .filter_map(|(i, &f)| if f > 0 { Some(i) } else { None })
        .collect();
    if used.is_empty() {
        return lengths;
    }
    if used.len() == 1 {
        lengths[used[0]] = 1;
        return lengths;
    }
    let leaves: Vec<(u64, Vec<u16>)> = {
        let mut items: Vec<(u64, Vec<u16>)> = used
            .iter()
            .map(|&s| (u64::from(freqs[s]), vec![s as u16]))
            .collect();
        items.sort();
        items
    };
    let mut current = leaves.clone();
    for _ in 0..limit.saturating_sub(1) {
        let mut packages = Vec::new();
        let mut i = 0;
        while i + 1 < current.len() {
            let mut syms = current[i].1.clone();
            syms.extend_from_slice(&current[i + 1].1);
            packages.push((current[i].0 + current[i + 1].0, syms));
            i += 2;
        }
        current = leaves.clone();
        current.extend(packages);
        current.sort();
    }
    let take = 2 * (used.len() - 1);
    for (_, syms) in current.into_iter().take(take) {
        for s in syms {
            lengths[s as usize] = lengths[s as usize].saturating_add(1);
        }
    }
    lengths
}

fn reverse_bits(mut code: u32, nbits: u8) -> u64 {
    let mut r = 0u32;
    for _ in 0..nbits {
        r = (r << 1) | (code & 1);
        code >>= 1;
    }
    u64::from(r)
}

fn canonical_rev_codes(lengths: &[u8]) -> Vec<u64> {
    let mut codes = vec![0u64; lengths.len()];
    let max_len = usize::from(lengths.iter().copied().max().unwrap_or(0));
    let mut bl_count = vec![0u32; max_len + 1];
    for &n in lengths {
        bl_count[usize::from(n)] += 1;
    }
    let mut next_code = vec![0u32; max_len + 1];
    let mut code = 0u32;
    for length in 1..=max_len {
        code = (code + bl_count[length - 1]) << 1;
        next_code[length] = code;
    }
    for (sym, &n) in lengths.iter().enumerate() {
        if n > 0 {
            let len = usize::from(n);
            codes[sym] = reverse_bits(next_code[len], n);
            next_code[len] += 1;
        }
    }
    codes
}

fn write_normal_code(sink: &mut BitSink, lengths: &[u8], alphabet_size: usize) {
    sink.put(0, 1);
    let last = lengths
        .iter()
        .rposition(|&n| n > 0)
        .expect("normal prefix code has at least one length");
    let emitted = &lengths[..=last];
    let mut cl_hist = [0u32; 19];
    for &length in emitted {
        cl_hist[usize::from(length)] += 1;
    }
    let cl_used: Vec<usize> = cl_hist
        .iter()
        .enumerate()
        .filter_map(|(i, &f)| if f > 0 { Some(i) } else { None })
        .collect();
    let (cl_declared, cl_len, cl_code) = if cl_used.len() == 1 {
        let mut declared = vec![0u8; 19];
        declared[cl_used[0]] = 1;
        (declared, vec![0u8; 19], vec![0u64; 19])
    } else {
        let declared = limited_lengths(&cl_hist, 7);
        let codes = canonical_rev_codes(&declared);
        let lens = declared.clone();
        (declared, lens, codes)
    };
    let last_pos = CODE_LENGTH_ORDER
        .iter()
        .enumerate()
        .filter_map(|(i, &s)| if cl_declared[s] > 0 { Some(i) } else { None })
        .max()
        .unwrap_or(0);
    let num_cl = last_pos.saturating_add(1).max(4);
    sink.put((num_cl - 4) as u64, 4);
    for i in 0..num_cl {
        sink.put(u64::from(cl_declared[CODE_LENGTH_ORDER[i]]), 3);
    }
    if last + 1 == alphabet_size {
        sink.put(0, 1);
    } else {
        sink.put(1, 1);
        let val = (last + 1) - 2;
        let mut sel = 0u32;
        while val >= (1 << (2 + 2 * sel)) {
            sel += 1;
        }
        sink.put(u64::from(sel), 3);
        sink.put(val as u64, (2 + 2 * sel) as u8);
    }
    for &length in emitted {
        sink.put(cl_code[usize::from(length)], cl_len[usize::from(length)]);
    }
}

struct PrefixLut {
    len: Vec<u8>,
    code: Vec<u64>,
}

fn write_prefix_code(sink: &mut BitSink, hist: &[u32]) -> PrefixLut {
    let mut lut = PrefixLut {
        len: vec![0u8; hist.len()],
        code: vec![0u64; hist.len()],
    };
    let used: Vec<usize> = hist
        .iter()
        .enumerate()
        .filter_map(|(i, &f)| if f > 0 { Some(i) } else { None })
        .collect();
    if used.is_empty() {
        sink.put(1, 1);
        sink.put(0, 1);
        sink.put(0, 1);
        sink.put(0, 1);
        return lut;
    }
    if used.len() <= 2 && *used.last().unwrap() <= 255 {
        sink.put(1, 1);
        sink.put((used.len() - 1) as u64, 1);
        let s0 = used[0];
        if s0 <= 1 {
            sink.put(0, 1);
            sink.put(s0 as u64, 1);
        } else {
            sink.put(1, 1);
            sink.put(s0 as u64, 8);
        }
        if used.len() == 2 {
            sink.put(used[1] as u64, 8);
            lut.len[used[0]] = 1;
            lut.len[used[1]] = 1;
            lut.code[used[1]] = 1;
        }
        return lut;
    }
    let lengths = if used.len() == 1 {
        let mut lengths = vec![0u8; hist.len()];
        lengths[used[0]] = 1;
        lengths
    } else {
        let lengths = limited_lengths(hist, 15);
        lut.len.clone_from(&lengths);
        lut.code = canonical_rev_codes(&lengths);
        lengths
    };
    write_normal_code(sink, &lengths, hist.len());
    lut
}

fn pixel_key(pixels: &[u8], index: usize, channels: usize) -> u32 {
    let i = index * channels;
    let r = pixels[i];
    let g = pixels[i + 1];
    let b = pixels[i + 2];
    let a = if channels == 4 { pixels[i + 3] } else { 255 };
    u32::from_le_bytes([r, g, b, a])
}

fn rgba_at(pixels: &[u8], index: usize, channels: usize) -> [u8; 4] {
    let i = index * channels;
    [
        pixels[i],
        pixels[i + 1],
        pixels[i + 2],
        if channels == 4 { pixels[i + 3] } else { 255 },
    ]
}

/// Encode packed RGB or RGBA8 pixels as a lossless VP8L WebP.
pub fn encode_webp(
    pixels: &[u8],
    width: usize,
    height: usize,
    channels: usize,
) -> WebpResult<Vec<u8>> {
    if channels != 3 && channels != 4 {
        return Err("WebP image must be (h, w, 4) RGBA or (h, w, 3) RGB".into());
    }
    if !(1..=MAX_DIM).contains(&width) || !(1..=MAX_DIM).contains(&height) {
        return Err(format!(
            "WebP dimensions must be 1..{MAX_DIM}, got {width}x{height}"
        ));
    }
    let n = width
        .checked_mul(height)
        .ok_or_else(|| "WebP image must be non-empty".to_string())?;
    let expected = n
        .checked_mul(channels)
        .ok_or_else(|| "WebP image must be non-empty".to_string())?;
    if pixels.len() < expected {
        return Err("WebP pixel buffer length does not match width*height*channels".into());
    }

    let mut starts = vec![0usize];
    for i in 1..n {
        if pixel_key(pixels, i, channels) != pixel_key(pixels, i - 1, channels) {
            starts.push(i);
        }
    }
    starts.push(n);

    struct RefRun {
        extra: u16,
        ebits: u8,
        sym: usize,
    }
    let mut refs: Vec<RefRun> = Vec::new();
    let nseg = starts.len() - 1;
    let mut nref_per_seg = vec![0usize; nseg];
    for seg in 0..nseg {
        let rem = starts[seg + 1] - starts[seg] - 1;
        let mut left = rem;
        while left > 0 {
            let run = left.min(MAX_RUN);
            let (code, ebits, extra) = length_prefix(run);
            refs.push(RefRun {
                extra,
                ebits,
                sym: 256 + usize::from(code),
            });
            nref_per_seg[seg] += 1;
            left -= run;
        }
    }

    let mut g_hist = vec![0u32; GREEN_ALPHABET];
    let mut r_hist = vec![0u32; 256];
    let mut b_hist = vec![0u32; 256];
    let mut a_hist = vec![0u32; 256];
    let mut d_hist = vec![0u32; DIST_ALPHABET];
    let mut lits = Vec::with_capacity(nseg);
    let mut alpha_used = false;
    for seg in 0..nseg {
        let px = rgba_at(pixels, starts[seg], channels);
        lits.push(px);
        r_hist[px[0] as usize] += 1;
        g_hist[px[1] as usize] += 1;
        b_hist[px[2] as usize] += 1;
        a_hist[px[3] as usize] += 1;
        if px[3] != 255 {
            alpha_used = true;
        }
    }
    for run in &refs {
        g_hist[run.sym] += 1;
    }
    d_hist[1] = refs.len() as u32;

    let mut sink = BitSink::new();
    sink.put(0x2F, 8);
    sink.put((width - 1) as u64, 14);
    sink.put((height - 1) as u64, 14);
    sink.put(u64::from(alpha_used), 1);
    sink.put(0, 3);
    sink.put(0, 1);
    sink.put(0, 1);
    sink.put(0, 1);
    let g_lut = write_prefix_code(&mut sink, &g_hist);
    let r_lut = write_prefix_code(&mut sink, &r_hist);
    let b_lut = write_prefix_code(&mut sink, &b_hist);
    let a_lut = write_prefix_code(&mut sink, &a_hist);
    let d_lut = write_prefix_code(&mut sink, &d_hist);

    let mut ref_at = 0usize;
    for (seg, px) in lits.iter().enumerate() {
        let gi = px[1] as usize;
        let ri = px[0] as usize;
        sink.put(
            g_lut.code[gi] | (r_lut.code[ri] << g_lut.len[gi]),
            g_lut.len[gi] + r_lut.len[ri],
        );
        let bi = px[2] as usize;
        let ai = px[3] as usize;
        sink.put(
            b_lut.code[bi] | (a_lut.code[ai] << b_lut.len[bi]),
            b_lut.len[bi] + a_lut.len[ai],
        );
        for _ in 0..nref_per_seg[seg] {
            let run = &refs[ref_at];
            let shift = g_lut.len[run.sym];
            sink.put(
                g_lut.code[run.sym]
                    | (u64::from(run.extra) << shift)
                    | (d_lut.code[1] << (shift + run.ebits)),
                shift + run.ebits + d_lut.len[1],
            );
            ref_at += 1;
        }
    }

    let payload = sink.pack_lsb();
    let mut chunk = Vec::with_capacity(8 + payload.len() + 1);
    chunk.extend_from_slice(b"VP8L");
    chunk.extend_from_slice(&(payload.len() as u32).to_le_bytes());
    chunk.extend_from_slice(&payload);
    if payload.len() & 1 == 1 {
        chunk.push(0x00);
    }
    let mut out = Vec::with_capacity(12 + chunk.len());
    out.extend_from_slice(b"RIFF");
    out.extend_from_slice(&(4u32 + chunk.len() as u32).to_le_bytes());
    out.extend_from_slice(b"WEBP");
    out.extend_from_slice(&chunk);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_invalid_size() {
        let px = [0u8; 4];
        assert!(encode_webp(&px, 0, 1, 4).is_err());
        assert!(encode_webp(&px, 1, 1, 2).is_err());
        assert!(encode_webp(&px, MAX_DIM + 1, 1, 4).is_err());
    }

    #[test]
    fn riff_container() {
        let px = [10u8, 20, 30, 255];
        let out = encode_webp(&px, 1, 1, 4).unwrap();
        assert_eq!(&out[..4], b"RIFF");
        assert_eq!(&out[8..16], b"WEBPVP8L");
        assert_eq!(out.len() % 2, 0);
    }

    #[test]
    fn rgb_is_opaque() {
        let rgb = [1u8, 2, 3];
        let rgba = [1u8, 2, 3, 255];
        assert_eq!(
            encode_webp(&rgb, 1, 1, 3).unwrap(),
            encode_webp(&rgba, 1, 1, 4).unwrap()
        );
    }
}
