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
use xyg_engine::scene::{AxisScale, PlotLayout, ScaleKind, SceneBatch, SceneDocument};

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

/// Scene v4's shared scale/layout/record encoding path for mixed core marks.
#[divan::bench(args = [SMALL_N, MEDIUM_N, LARGE_N])]
fn scene_v4_batch_encode(bencher: Bencher, n: usize) {
    let mut x = uniform(n, 0x0055_AA11);
    let mut y = uniform(n, 0x0066_BB22);
    for index in (0..n).step_by(97) {
        x[index] = if index % 2 == 0 { -0.25 } else { 1.25 };
        y[index] = if index % 4 < 2 { 1.25 } else { -0.25 };
    }
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
    let mut x1 = x.clone();
    let mut y1 = y.clone();
    for index in (2..n).step_by(3) {
        let direction = if index % 2 == 0 { -1.0 } else { 1.0 };
        x1[index] = x[index] + direction * 0.15;
        y1[index] = y[index] - direction * 0.1;
    }
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
        &x1,
        &y1,
    )
    .unwrap();
    bencher.bench(|| black_box(batch.encode()));
}

fn scene_v4_document(n: usize) -> SceneDocument {
    let mut x = uniform(n, 0x0055_AA11);
    let mut y = uniform(n, 0x0066_BB22);
    let kinds: Vec<u8> = (0..n).map(|index| [1, 1, 0, 2, 2, 0][index % 6]).collect();
    let ids: Vec<u64> = (0..n)
        .map(|index| {
            if index % 6 < 2 {
                (index / 6) as u64
            } else {
                index as u64
            }
        })
        .collect();
    let style_refs: Vec<u32> = kinds.iter().map(|kind| u32::from(*kind)).collect();
    let diameter: Vec<f64> = kinds
        .iter()
        .map(|kind| if *kind == 0 { 6.0 } else { 0.0 })
        .collect();
    let mut x1 = x.clone();
    let mut y1 = y.clone();
    for index in 0..n {
        match index % 6 {
            3 => {
                x1[index] = x[index] + 0.2;
                y1[index] = y[index] + 0.15;
            }
            4 => {
                x[index] = 1.15;
                y[index] = 0.85;
                x1[index] = 0.55;
                y1[index] = -0.15;
            }
            _ => {}
        }
    }
    let layout = PlotLayout::new(800.0, 600.0, 60.0, 20.0, 20.0, 50.0).unwrap();
    let sx = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 60.0, 780.0, 1.0, false).unwrap();
    let sy = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 550.0, 20.0, 1.0, false).unwrap();
    let encoded = SceneBatch::new(
        layout,
        1,
        2,
        sx,
        sy,
        &kinds,
        &ids,
        &style_refs,
        &[0x88; 32],
        &[0x22; 32],
        &[1.0; 8],
        &diameter,
        &vec![0; n],
        &x,
        &y,
        &x1,
        &y1,
    )
    .unwrap()
    .encode();
    let document = SceneDocument::decode(&encoded).unwrap();
    let svg = document.to_svg();
    let commands = document.to_raster_commands(1.0).unwrap();
    assert!(svg.matches("<polyline points=\"").count() >= 1);
    assert!(svg.matches("<rect x=\"").count() >= 2); // plot clip + data rectangle
    let (fills, strokes, texts) =
        scene_raster_primitive_counts(&commands).expect("valid scene commands");
    assert!(fills >= 1 && strokes >= 3); // data rectangle + data line + two axes
    assert!(texts >= 2); // both canonical axes retain labels
    document
}

fn scene_raster_primitive_counts(commands: &[u8]) -> Option<(usize, usize, usize)> {
    fn advance(offset: &mut usize, count: usize, len: usize) -> Option<()> {
        *offset = offset.checked_add(count)?;
        (*offset <= len).then_some(())
    }
    fn read_u32(commands: &[u8], offset: &mut usize) -> Option<usize> {
        let end = offset.checked_add(4)?;
        let value = u32::from_le_bytes(commands.get(*offset..end)?.try_into().ok()?) as usize;
        *offset = end;
        Some(value)
    }

    let (mut fills, mut strokes, mut texts, mut offset) = (0, 0, 0, 0);
    while offset < commands.len() {
        let operation = *commands.get(offset)?;
        offset += 1;
        match operation {
            0 => advance(&mut offset, 16, commands.len())?,
            1 => {
                let points = read_u32(commands, &mut offset)?;
                advance(
                    &mut offset,
                    points.checked_mul(8)?.checked_add(4)?,
                    commands.len(),
                )?;
                fills += 1;
            }
            3 => {
                let points = read_u32(commands, &mut offset)?;
                advance(
                    &mut offset,
                    points.checked_mul(8)?.checked_add(9)?,
                    commands.len(),
                )?;
                let dash_count = read_u32(commands, &mut offset)?;
                advance(
                    &mut offset,
                    dash_count.checked_mul(4)?.checked_add(1)?,
                    commands.len(),
                )?;
                strokes += 1;
            }
            4 => advance(&mut offset, 25, commands.len())?,
            6 => {
                advance(&mut offset, 17, commands.len())?;
                let bytes = read_u32(commands, &mut offset)?;
                advance(&mut offset, bytes, commands.len())?;
                texts += 1;
            }
            _ => return None,
        }
    }
    Some((fills, strokes, texts))
}

#[divan::bench(args = [SMALL_N, MEDIUM_N, LARGE_N])]
fn scene_v4_svg(bencher: Bencher, n: usize) {
    let document = scene_v4_document(n);
    bencher.bench(|| black_box(document.to_svg()));
}

#[divan::bench(args = [SMALL_N, MEDIUM_N, LARGE_N])]
fn scene_v4_raster_commands(bencher: Bencher, n: usize) {
    let document = scene_v4_document(n);
    bencher.bench(|| black_box(document.to_raster_commands(1.0).unwrap()));
}

#[divan::bench(args = [SMALL_N, MEDIUM_N, LARGE_N])]
fn scene_v4_browser_painter(bencher: Bencher, n: usize) {
    let document = scene_v4_document(n);
    let output = document.to_browser_painter(64 * 1024 * 1024).unwrap();
    assert_eq!(&output[..4], b"XYPB");
    assert_eq!(u32::from_le_bytes(output[4..8].try_into().unwrap()), 2);
    assert!(u32::from_le_bytes(output[48..52].try_into().unwrap()) >= 3);
    assert!(u32::from_le_bytes(output[52..56].try_into().unwrap()) >= 3);
    assert!(output.len() > n * 16);
    bencher.bench(|| black_box(document.to_browser_painter(64 * 1024 * 1024).unwrap()));
}
