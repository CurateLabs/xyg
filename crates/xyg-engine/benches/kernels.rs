//! CodSpeed benchmarks for the native compute kernels.
//!
//! The pytest suite in `benchmarks/test_codspeed_*.py` measures the engine as
//! Python calls it — figure build, payload encode, export — so a kernel
//! regression shows up there mixed with FFI and NumPy work. These benches sit
//! directly on the Rust entry points instead, so a change to `kernels.rs` is
//! attributed to the kernel that caused it and comes with its own flame graph.
//!
//! Sizes mirror the Python suite (10k / 100k / 1M rows, a 512x384 screen grid,
//! 2048 M4 buckets) so the two views describe the same workloads.
//!
//! Run locally with:
//!
//!     cargo codspeed build --bench kernels
//!     codspeed run --mode simulation -- cargo codspeed run --bench kernels

use divan::{black_box, Bencher};

use xyg_engine::kernels::{self, DEFAULT_CHUNK};
use xyg_engine::scene::{AxisScale, PlotLayout, ScaleKind, SceneBatch};

fn main() {
    divan::main();
}

const SMALL_N: usize = 10_000;
const MEDIUM_N: usize = 100_000;
const LARGE_N: usize = 1_000_000;
const GRID_W: usize = 512;
const GRID_H: usize = 384;
const N_BUCKETS: usize = 2048;
const HIST_BINS: usize = 256;

/// Deterministic pseudo-random values in `[0, 1)` — a plain SplitMix64 so the
/// benchmark inputs are byte-identical on every machine and every run without
/// pulling an RNG crate into the dependency graph.
fn uniform(n: usize, seed: u64) -> Vec<f64> {
    let mut state = seed;
    (0..n)
        .map(|_| {
            state = state.wrapping_add(0x9E37_79B9_7F4A_7C15);
            let mut z = state;
            z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
            z ^= z >> 31;
            // 53 significant bits: the exact same construction as NumPy's
            // `random_sample`, so the distribution matches the Python suite.
            ((z >> 11) as f64) * (1.0 / 9_007_199_254_740_992.0)
        })
        .collect()
}

/// A sorted x axis with a noisy y — the time-series shape the decimation and
/// autorange paths actually see.
fn series(n: usize) -> (Vec<f64>, Vec<f64>) {
    let x: Vec<f64> = (0..n).map(|i| i as f64).collect();
    let y = uniform(n, 0x5EED_1234);
    (x, y)
}

/// §22 zone maps: the autorange primitive. Chunked and fully independent, so
/// this measures the per-value scan the whole column pays on ingest.
#[divan::bench(args = [SMALL_N, MEDIUM_N, LARGE_N])]
fn zone_maps(bencher: Bencher, n: usize) {
    let data = uniform(n, 0x0077_CC88);
    bencher.bench(|| kernels::zone_maps(black_box(&data), DEFAULT_CHUNK));
}

/// Autorange without zone maps: a single NaN-skipping pass over the column.
#[divan::bench(args = [MEDIUM_N, LARGE_N])]
fn min_max(bencher: Bencher, n: usize) {
    let data = uniform(n, 0x00AA_5511);
    bencher.bench(|| kernels::min_max(black_box(&data)));
}

/// §4/§16 offset-encoded f32: every point shipped to the GPU goes through it.
#[divan::bench(args = [MEDIUM_N, LARGE_N])]
fn encode_f32(bencher: Bencher, n: usize) {
    let data = uniform(n, 0x00BB_6622);
    let mut out = vec![0.0f32; n];
    bencher.bench_local(|| kernels::encode_f32_into(black_box(&data), 0.5, 2.0, &mut out));
}

/// §5 Tier-1 decimation: M4 keeps four extrema per pixel column, so this is
/// the kernel behind every large line chart.
#[divan::bench(args = [MEDIUM_N, LARGE_N])]
fn m4_indices(bencher: Bencher, n: usize) {
    let (x, y) = series(n);
    let x1 = n as f64;
    bencher.bench(|| kernels::m4_indices(black_box(&x), black_box(&y), 0.0, x1, N_BUCKETS));
}

/// §5 Tier-2 binning: the screen-bounded density path — O(visible points) per
/// viewport change, which makes it the hottest kernel during pan and zoom.
#[divan::bench(args = [MEDIUM_N, LARGE_N])]
fn bin_2d(bencher: Bencher, n: usize) {
    let x = uniform(n, 0x00CC_7733);
    let y = uniform(n, 0x00DD_8844);
    let mut out = vec![0.0f32; GRID_W * GRID_H];
    bencher.bench_local(|| {
        kernels::bin_2d(
            black_box(&x),
            black_box(&y),
            0.0,
            1.0,
            0.0,
            1.0,
            GRID_W,
            GRID_H,
            &mut out,
        )
    });
}

/// Log-encoding the density grid into the client's R8 texture: per-view work
/// that runs on every zoom step, independent of the row count.
#[divan::bench]
fn density_log_u8(bencher: Bencher) {
    let grid: Vec<f32> = uniform(GRID_W * GRID_H, 0x00EE_9955)
        .into_iter()
        .map(|v| (v * 1000.0) as f32)
        .collect();
    let mut out = vec![0u8; grid.len()];
    bencher.bench_local(|| kernels::density_log_u8_into(black_box(&grid), &mut out));
}

/// Fixed-bin histogram — the scatter increment dominates and does not
/// vectorize, so it is worth watching per-instruction.
#[divan::bench(args = [MEDIUM_N, LARGE_N])]
fn histogram_uniform(bencher: Bencher, n: usize) {
    let data = uniform(n, 0x0011_FF22);
    let mut out = vec![0.0f64; HIST_BINS];
    bencher.bench_local(|| kernels::histogram_uniform(black_box(&data), 0.0, 1.0, &mut out));
}

/// §34 box selection: the rectangular window scan behind brush and drilldown.
#[divan::bench(args = [MEDIUM_N, LARGE_N])]
fn range_indices(bencher: Bencher, n: usize) {
    let x = uniform(n, 0x0033_EE44);
    let y = uniform(n, 0x0055_DD66);
    let mut out = vec![0u32; n];
    bencher.bench_local(|| {
        kernels::range_indices(
            black_box(&x),
            black_box(&y),
            0.25,
            0.75,
            0.25,
            0.75,
            &mut out,
        )
    });
}

/// §28 sorted-ingest predicate: single pass, early exit, run on every line and
/// area ingest.
#[divan::bench(args = [MEDIUM_N, LARGE_N])]
fn is_sorted_f64(bencher: Bencher, n: usize) {
    let (x, _) = series(n);
    bencher.bench(|| kernels::is_sorted_f64(black_box(&x)));
}

/// Scene v2's shared scale/layout/record encoding path for mixed core marks.
#[divan::bench(args = [SMALL_N, MEDIUM_N])]
fn scene_v2_batch_encode(bencher: Bencher, n: usize) {
    let x = uniform(n, 0x0055_AA11);
    let y = uniform(n, 0x0066_BB22);
    let kinds: Vec<u8> = (0..n).map(|index| (index % 3) as u8).collect();
    let ids: Vec<u64> = (0..n as u64).collect();
    let styles: Vec<u32> = (0..n).map(|index| (index % 8) as u32).collect();
    let fill = vec![0x88u8; 8 * 4];
    let stroke = vec![0x22u8; 8 * 4];
    let stroke_width = vec![1.0; 8];
    let diameter: Vec<f64> = kinds
        .iter()
        .map(|kind| if *kind == 0 { 6.0 } else { 0.0 })
        .collect();
    let symbols = vec![0u8; n];
    let layout = PlotLayout::new(800.0, 600.0, 60.0, 20.0, 20.0, 50.0).unwrap();
    let sx = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 60.0, 780.0, 1.0, false).unwrap();
    let sy = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 550.0, 20.0, 1.0, false).unwrap();
    let batch = SceneBatch::new(
        layout,
        1,
        2,
        sx,
        sy,
        &kinds,
        &ids,
        &styles,
        &fill,
        &stroke,
        &stroke_width,
        &diameter,
        &symbols,
        &x,
        &y,
        &x,
        &y,
    )
    .unwrap();
    bencher.bench(|| black_box(batch.encode()));
}
