use divan::{black_box, Bencher};
use xyg_wasm::aggregate::{
    AggregateJob, AGGREGATE_HEADER_BYTES, AGGREGATE_MAGIC, AGGREGATE_VERSION, CHECKPOINT_POINTS,
    FLAG_MEAN_COLOR, OUTPUT_MAGIC,
};

const SIZES: [usize; 3] = [10_000, 100_000, 1_000_000];

fn request(n: usize, color: bool) -> Vec<u8> {
    let mut bytes = vec![0; AGGREGATE_HEADER_BYTES];
    bytes[..4].copy_from_slice(AGGREGATE_MAGIC);
    bytes[4..8].copy_from_slice(&AGGREGATE_VERSION.to_le_bytes());
    bytes[8..12].copy_from_slice(&(AGGREGATE_HEADER_BYTES as u32).to_le_bytes());
    bytes[12..16].copy_from_slice(&(if color { FLAG_MEAN_COLOR } else { 0 }).to_le_bytes());
    bytes[16..20].copy_from_slice(&(n as u32).to_le_bytes());
    bytes[20..24].copy_from_slice(&512u32.to_le_bytes());
    bytes[24..28].copy_from_slice(&384u32.to_le_bytes());
    for (offset, value) in [(32, 0.0f64), (40, 1.0), (48, 0.0), (56, 1.0)] {
        bytes[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
    }
    for i in 0..n {
        bytes.extend_from_slice(&(((i * 17 % 10_000) as f64 + 0.5) / 10_000.0).to_le_bytes());
    }
    for i in 0..n {
        bytes.extend_from_slice(&(((i * 31 % 10_000) as f64 + 0.5) / 10_000.0).to_le_bytes());
    }
    if color {
        for i in 0..n {
            bytes.extend_from_slice(&[(i % 251) as u8, 97, 211, 255]);
        }
    }
    bytes
}

fn run(bytes: &[u8]) -> Vec<u8> {
    let mut job = AggregateJob::begin(bytes, 0, 64 * 1024 * 1024).unwrap();
    while !job.step(bytes, CHECKPOINT_POINTS).unwrap() {}
    let output = job.finish();
    assert_eq!(&output[..4], OUTPUT_MAGIC);
    output
}

#[divan::bench(args = SIZES)]
fn xyag_count_checkpoints_xyao(bencher: Bencher, n: usize) {
    let bytes = request(n, false);
    bencher.bench_local(|| black_box(run(&bytes)));
}

#[divan::bench(args = SIZES)]
fn xyag_mean_color_checkpoints_xyao(bencher: Bencher, n: usize) {
    let bytes = request(n, true);
    bencher.bench_local(|| black_box(run(&bytes)));
}

fn main() {
    divan::main();
}
