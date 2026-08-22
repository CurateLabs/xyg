//! CodSpeed attribution for Rust-owned transferable typed-series expansion.
use divan::{black_box, Bencher};
use xyg_wasm::compile::{
    compile_scene_request, COMPILE_HEADER_BYTES, DESCRIPTOR_DIAMETER, DESCRIPTOR_KIND,
    DESCRIPTOR_RECORD_COUNT, DESCRIPTOR_STROKE_WIDTH, DESCRIPTOR_X, DESCRIPTOR_Y, HEADER_FLAGS,
    HEADER_FLAG_AUTO_DOMAIN, HEADER_FLAG_AUTO_MARGINS, HEADER_HEADER_BYTES, HEADER_HEIGHT,
    HEADER_RECORD_COUNT, HEADER_SERIES_COUNT, HEADER_VERSION, HEADER_WIDTH, HEADER_X_AXIS_ID,
    HEADER_X_CONSTANT, HEADER_X_HI, HEADER_X_LO, HEADER_Y_AXIS_ID, HEADER_Y_CONSTANT, HEADER_Y_HI,
    HEADER_Y_LO, KIND_SCATTER, SERIES_DESCRIPTOR_BYTES, SERIES_MAGIC, SERIES_VERSION,
};

fn main() {
    divan::main();
}

fn request(n: usize) -> Vec<u8> {
    let data_start = COMPILE_HEADER_BYTES + SERIES_DESCRIPTOR_BYTES;
    let mut out = vec![0u8; data_start];
    out[..4].copy_from_slice(SERIES_MAGIC);
    out[HEADER_VERSION..HEADER_VERSION + 4].copy_from_slice(&SERIES_VERSION.to_le_bytes());
    out[HEADER_HEADER_BYTES..HEADER_HEADER_BYTES + 4]
        .copy_from_slice(&(COMPILE_HEADER_BYTES as u32).to_le_bytes());
    out[HEADER_FLAGS..HEADER_FLAGS + 4]
        .copy_from_slice(&(HEADER_FLAG_AUTO_MARGINS | HEADER_FLAG_AUTO_DOMAIN).to_le_bytes());
    out[HEADER_SERIES_COUNT..HEADER_SERIES_COUNT + 4].copy_from_slice(&1u32.to_le_bytes());
    out[HEADER_RECORD_COUNT..HEADER_RECORD_COUNT + 4].copy_from_slice(&(n as u32).to_le_bytes());
    for (offset, value) in [
        (HEADER_WIDTH, 800.0f64),
        (HEADER_HEIGHT, 600.0),
        (HEADER_X_LO, 0.0),
        (HEADER_X_HI, 1.0),
        (HEADER_X_CONSTANT, 1.0),
        (HEADER_Y_LO, 0.0),
        (HEADER_Y_HI, 1.0),
        (HEADER_Y_CONSTANT, 1.0),
    ] {
        out[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
    }
    out[HEADER_X_AXIS_ID..HEADER_X_AXIS_ID + 8].copy_from_slice(&1u64.to_le_bytes());
    out[HEADER_Y_AXIS_ID..HEADER_Y_AXIS_ID + 8].copy_from_slice(&2u64.to_le_bytes());
    let d = COMPILE_HEADER_BYTES;
    out[d + DESCRIPTOR_KIND..d + DESCRIPTOR_KIND + 4].copy_from_slice(&KIND_SCATTER.to_le_bytes());
    out[d + DESCRIPTOR_RECORD_COUNT..d + DESCRIPTOR_RECORD_COUNT + 4]
        .copy_from_slice(&(n as u32).to_le_bytes());
    out[d + DESCRIPTOR_DIAMETER..d + DESCRIPTOR_DIAMETER + 8]
        .copy_from_slice(&f64::NAN.to_le_bytes());
    out[d + DESCRIPTOR_STROKE_WIDTH..d + DESCRIPTOR_STROKE_WIDTH + 8]
        .copy_from_slice(&f64::NAN.to_le_bytes());
    out[d + DESCRIPTOR_X..d + DESCRIPTOR_X + 4].copy_from_slice(&(data_start as u32).to_le_bytes());
    out[d + DESCRIPTOR_Y..d + DESCRIPTOR_Y + 4]
        .copy_from_slice(&((data_start + n * 8) as u32).to_le_bytes());
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
