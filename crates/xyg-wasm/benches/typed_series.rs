//! CodSpeed attribution for Rust-owned transferable typed-series expansion.
use divan::{black_box, Bencher};
use xyg_wasm::compile::{compile_scene_request, COMPILE_HEADER_BYTES, SERIES_DESCRIPTOR_BYTES};

fn main() {
    divan::main();
}

fn request(n: usize) -> Vec<u8> {
    let data_start = COMPILE_HEADER_BYTES + SERIES_DESCRIPTOR_BYTES;
    let mut out = vec![0u8; data_start];
    out[..4].copy_from_slice(b"XYTS");
    out[4..8].copy_from_slice(&1u32.to_le_bytes());
    out[8..12].copy_from_slice(&(COMPILE_HEADER_BYTES as u32).to_le_bytes());
    out[12..16].copy_from_slice(&3u32.to_le_bytes());
    out[16..20].copy_from_slice(&1u32.to_le_bytes());
    out[20..24].copy_from_slice(&(n as u32).to_le_bytes());
    for (offset, value) in [
        (40, 800.0f64),
        (48, 600.0),
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
    let d = COMPILE_HEADER_BYTES;
    out[d..d + 4].copy_from_slice(&0u32.to_le_bytes());
    out[d + 8..d + 12].copy_from_slice(&(n as u32).to_le_bytes());
    out[d + 24..d + 32].copy_from_slice(&f64::NAN.to_le_bytes());
    out[d + 32..d + 40].copy_from_slice(&f64::NAN.to_le_bytes());
    out[d + 48..d + 52].copy_from_slice(&(data_start as u32).to_le_bytes());
    out[d + 52..d + 56].copy_from_slice(&((data_start + n * 8) as u32).to_le_bytes());
    for index in 0..n {
        out.extend_from_slice(&((index % 1024) as f64 / 1023.0).to_le_bytes());
    }
    for index in 0..n {
        out.extend_from_slice(&(((index * 37) % 1024) as f64 / 1023.0).to_le_bytes());
    }
    out
}

#[divan::bench(args = [100usize, 10_000, 100_000, 1_000_000])]
fn rust_typed_series_expand(bencher: Bencher, n: usize) {
    let input = request(n);
    bencher.bench(|| compile_scene_request(black_box(&input), 384 * 1024 * 1024).unwrap());
}
