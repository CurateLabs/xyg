//! Resumable, memory-bounded density aggregation for the direct-browser host.
use xyg_engine::kernels::{self, BinColorSource, MeanColorCell};

pub const AGGREGATE_MAGIC: &[u8; 4] = b"XYAG";
pub const AGGREGATE_VERSION: u32 = 1;
pub const AGGREGATE_HEADER_BYTES: usize = 64;
pub const FLAG_MEAN_COLOR: u32 = 1;
pub const OUTPUT_MAGIC: &[u8; 4] = b"XYAO";
pub const OUTPUT_VERSION: u32 = 1;
pub const OUTPUT_HEADER_BYTES: usize = 32;
pub const MAX_GRID_CELLS: usize = 2048 * 2048;
pub const MAX_POINTS: usize = 8_000_000;
pub const MAX_REQUEST_BYTES: usize = 64 * 1024 * 1024;
pub const REQUEST_STRIDE_COUNT: usize = 16;
pub const REQUEST_STRIDE_COLOR: usize = 20;
pub const ACCUMULATOR_STRIDE_COUNT: usize = 4;
pub const ACCUMULATOR_STRIDE_COLOR: usize = 40;
pub const OUTPUT_STRIDE_COUNT: usize = 4;
pub const OUTPUT_STRIDE_COLOR: usize = 8;
pub const CHECKPOINT_STRIDE_COUNT: usize = 16;
pub const CHECKPOINT_STRIDE_COLOR: usize = 20;
pub const REQUEST_COPY_FACTOR: usize = 2;
pub const OUTPUT_COPY_FACTOR: usize = 2;
pub const CHECKPOINT_POINTS: usize = 32 * 1024;
/// Streaming count-only aggregate header. Unlike `XYAG`, no full source
/// columns follow this header: the host supplies bounded x/y chunks through
/// the lifecycle ABI below.
pub const STREAM_MAGIC: &[u8; 4] = b"XYAS";
pub const STREAM_VERSION: u32 = 1;
pub const STREAM_HEADER_BYTES: usize = 64;
pub const STREAM_CHUNK_POINTS: usize = 32 * 1024;
pub const STREAM_CHUNK_BYTES: usize = 524_288;
pub const STREAM_CHUNK_COPY_FACTOR: usize = 2;
const _: () = assert!(STREAM_CHUNK_POINTS == CHECKPOINT_POINTS);
const _: () = assert!(STREAM_CHUNK_BYTES == STREAM_CHUNK_POINTS * REQUEST_STRIDE_COUNT);
pub const REQUEST_OFFSETS: [usize; 11] = [4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56];
pub const OUTPUT_OFFSETS: [usize; 7] = [4, 8, 12, 16, 20, 24, 28];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AggregateError {
    Length,
    Version,
    Limit,
    Domain,
}
#[derive(Debug)]
enum Accumulator {
    Counts(Vec<u32>),
    Colors(Vec<MeanColorCell>),
}
#[derive(Debug)]
pub struct AggregateJob {
    point_count: usize,
    cursor: usize,
    width: usize,
    height: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    request_base: usize,
    y_offset: usize,
    rgba_offset: usize,
    accumulator: Accumulator,
}

/// A count-only aggregate which never retains the full source. The header
/// declares the final point count and grid/domain; each pushed chunk is the
/// canonical little-endian layout `[x: f64; n][y: f64; n]`.
#[derive(Debug)]
pub struct StreamAggregateJob {
    expected_points: usize,
    received_points: usize,
    width: usize,
    height: usize,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    counts: Vec<u32>,
}

fn u32_at(bytes: &[u8], offset: usize) -> Result<u32, AggregateError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(AggregateError::Length)?
            .try_into()
            .map_err(|_| AggregateError::Length)?,
    ))
}
fn f64_at(bytes: &[u8], offset: usize) -> Result<f64, AggregateError> {
    Ok(f64::from_le_bytes(
        bytes
            .get(offset..offset + 8)
            .ok_or(AggregateError::Length)?
            .try_into()
            .map_err(|_| AggregateError::Length)?,
    ))
}
fn domain_ok(lo: f64, hi: f64) -> bool {
    lo.is_finite() && hi.is_finite() && hi > lo
}

fn count_output(width: usize, height: usize, counts: Vec<u32>) -> Vec<u8> {
    let cells = width * height;
    let mut out = vec![0; OUTPUT_HEADER_BYTES];
    out.reserve(cells * OUTPUT_STRIDE_COUNT);
    out[..4].copy_from_slice(OUTPUT_MAGIC);
    for (offset, value) in [
        (OUTPUT_OFFSETS[0], OUTPUT_VERSION),
        (OUTPUT_OFFSETS[1], OUTPUT_HEADER_BYTES as u32),
        (OUTPUT_OFFSETS[2], 0),
        (OUTPUT_OFFSETS[3], width as u32),
        (OUTPUT_OFFSETS[4], height as u32),
    ] {
        out[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
    }
    let max = counts.iter().copied().max().unwrap_or(0) as f32;
    out[OUTPUT_OFFSETS[5]..OUTPUT_OFFSETS[5] + 4].copy_from_slice(&max.to_le_bytes());
    for n in counts {
        out.extend_from_slice(&(n as f32).to_le_bytes());
    }
    out
}

impl AggregateJob {
    pub fn begin(bytes: &[u8], request_base: usize, budget: usize) -> Result<Self, AggregateError> {
        if bytes.len() < AGGREGATE_HEADER_BYTES || &bytes[..4] != AGGREGATE_MAGIC {
            return Err(AggregateError::Length);
        }
        if u32_at(bytes, REQUEST_OFFSETS[0])? != AGGREGATE_VERSION {
            return Err(AggregateError::Version);
        }
        if u32_at(bytes, REQUEST_OFFSETS[1])? as usize != AGGREGATE_HEADER_BYTES
            || u32_at(bytes, REQUEST_OFFSETS[6])? != 0
        {
            return Err(AggregateError::Length);
        }
        let flags = u32_at(bytes, REQUEST_OFFSETS[2])?;
        if flags & !FLAG_MEAN_COLOR != 0 {
            return Err(AggregateError::Length);
        }
        let point_count = u32_at(bytes, REQUEST_OFFSETS[3])? as usize;
        let width = u32_at(bytes, REQUEST_OFFSETS[4])? as usize;
        let height = u32_at(bytes, REQUEST_OFFSETS[5])? as usize;
        if width == 0 || height == 0 {
            return Err(AggregateError::Length);
        }
        if point_count > MAX_POINTS {
            return Err(AggregateError::Limit);
        }
        let x0 = f64_at(bytes, REQUEST_OFFSETS[7])?;
        let x1 = f64_at(bytes, REQUEST_OFFSETS[8])?;
        let y0 = f64_at(bytes, REQUEST_OFFSETS[9])?;
        let y1 = f64_at(bytes, REQUEST_OFFSETS[10])?;
        if !domain_ok(x0, x1) || !domain_ok(y0, y1) {
            return Err(AggregateError::Domain);
        }
        let cells = width.checked_mul(height).ok_or(AggregateError::Limit)?;
        if cells > MAX_GRID_CELLS {
            return Err(AggregateError::Limit);
        }
        let color = flags & FLAG_MEAN_COLOR != 0;
        let expected = AGGREGATE_HEADER_BYTES
            .checked_add(
                point_count
                    .checked_mul(if color {
                        REQUEST_STRIDE_COLOR
                    } else {
                        REQUEST_STRIDE_COUNT
                    })
                    .ok_or(AggregateError::Limit)?,
            )
            .ok_or(AggregateError::Limit)?;
        if bytes.len() != expected {
            return Err(AggregateError::Length);
        }
        if bytes.len() > MAX_REQUEST_BYTES {
            return Err(AggregateError::Limit);
        }
        let accum = cells
            .checked_mul(if color {
                ACCUMULATOR_STRIDE_COLOR
            } else {
                ACCUMULATOR_STRIDE_COUNT
            })
            .ok_or(AggregateError::Limit)?;
        let output = OUTPUT_HEADER_BYTES
            .checked_add(
                cells
                    .checked_mul(if color {
                        OUTPUT_STRIDE_COLOR
                    } else {
                        OUTPUT_STRIDE_COUNT
                    })
                    .ok_or(AggregateError::Limit)?,
            )
            .ok_or(AggregateError::Limit)?;
        let checkpoint = point_count
            .min(CHECKPOINT_POINTS)
            .checked_mul(if color {
                CHECKPOINT_STRIDE_COLOR
            } else {
                CHECKPOINT_STRIDE_COUNT
            })
            .ok_or(AggregateError::Limit)?;
        let peak = bytes
            .len()
            // Browser-wide peak: the transferred JS request remains retained
            // while this WASM staging copy is active.
            .checked_add(bytes.len().saturating_mul(REQUEST_COPY_FACTOR - 1))
            .and_then(|v| v.checked_add(accum))
            .and_then(|v| v.checked_add(output.saturating_mul(OUTPUT_COPY_FACTOR - 1)))
            // Copying XYAO for transfer briefly coexists with Rust output.
            .and_then(|v| v.checked_add(output))
            .and_then(|v| v.checked_add(checkpoint))
            .ok_or(AggregateError::Limit)?;
        if peak > budget {
            return Err(AggregateError::Limit);
        }
        let accumulator = if color {
            Accumulator::Colors(vec![MeanColorCell::default(); cells])
        } else {
            Accumulator::Counts(vec![0; cells])
        };
        Ok(Self {
            point_count,
            cursor: 0,
            width,
            height,
            x0,
            x1,
            y0,
            y1,
            request_base,
            y_offset: AGGREGATE_HEADER_BYTES + point_count * 8,
            rgba_offset: AGGREGATE_HEADER_BYTES + point_count * 16,
            accumulator,
        })
    }
    pub fn step(&mut self, bytes: &[u8], max_points: usize) -> Result<bool, AggregateError> {
        let end = self
            .cursor
            .saturating_add(max_points.max(1))
            .min(self.point_count);
        let mut x = Vec::with_capacity(end - self.cursor);
        let mut y = Vec::with_capacity(end - self.cursor);
        for i in self.cursor..end {
            x.push(f64_at(
                bytes,
                self.request_base + AGGREGATE_HEADER_BYTES + i * 8,
            )?);
            y.push(f64_at(bytes, self.request_base + self.y_offset + i * 8)?);
        }
        match &mut self.accumulator {
            Accumulator::Counts(grid) => kernels::bin_2d_count_scalar(
                &x,
                &y,
                self.x0,
                self.x1,
                self.y0,
                self.y1,
                self.width,
                self.height,
                grid,
            ),
            Accumulator::Colors(grid) => {
                let lo = self.request_base + self.rgba_offset + self.cursor * 4;
                let hi = self.request_base + self.rgba_offset + end * 4;
                kernels::bin_2d_mean_color_accumulate(
                    &x,
                    &y,
                    &BinColorSource::Rgba(bytes.get(lo..hi).ok_or(AggregateError::Length)?),
                    0,
                    self.x0,
                    self.x1,
                    self.y0,
                    self.y1,
                    self.width,
                    self.height,
                    grid,
                );
            }
        }
        self.cursor = end;
        Ok(end == self.point_count)
    }
    pub fn finish(self) -> Vec<u8> {
        let cells = self.width * self.height;
        let colors = match self.accumulator {
            Accumulator::Counts(counts) => return count_output(self.width, self.height, counts),
            Accumulator::Colors(colors) => colors,
        };
        let mut out = vec![0; OUTPUT_HEADER_BYTES];
        out.reserve(cells * 8);
        out[..4].copy_from_slice(OUTPUT_MAGIC);
        for (offset, value) in [
            (OUTPUT_OFFSETS[0], OUTPUT_VERSION),
            (OUTPUT_OFFSETS[1], OUTPUT_HEADER_BYTES as u32),
            (OUTPUT_OFFSETS[2], 1),
            (OUTPUT_OFFSETS[3], self.width as u32),
            (OUTPUT_OFFSETS[4], self.height as u32),
        ] {
            out[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
        }
        let max = colors.iter().map(|c| c.count).max().unwrap_or(0) as f32;
        out[OUTPUT_OFFSETS[5]..OUTPUT_OFFSETS[5] + 4].copy_from_slice(&max.to_le_bytes());
        for c in &colors {
            out.extend_from_slice(&(c.count as f32).to_le_bytes())
        }
        for c in &colors {
            out.extend_from_slice(&c.rgba8())
        }
        out
    }
}

impl StreamAggregateJob {
    pub fn begin(header: &[u8], budget: usize) -> Result<Self, AggregateError> {
        if header.len() != STREAM_HEADER_BYTES || &header[..4] != STREAM_MAGIC {
            return Err(AggregateError::Length);
        }
        if u32_at(header, REQUEST_OFFSETS[0])? != STREAM_VERSION {
            return Err(AggregateError::Version);
        }
        if u32_at(header, REQUEST_OFFSETS[1])? as usize != STREAM_HEADER_BYTES
            || u32_at(header, REQUEST_OFFSETS[2])? != 0
            || u32_at(header, REQUEST_OFFSETS[6])? != 0
        {
            return Err(AggregateError::Length);
        }
        let expected_points = u32_at(header, REQUEST_OFFSETS[3])? as usize;
        let width = u32_at(header, REQUEST_OFFSETS[4])? as usize;
        let height = u32_at(header, REQUEST_OFFSETS[5])? as usize;
        if expected_points > MAX_POINTS || width == 0 || height == 0 {
            return Err(AggregateError::Limit);
        }
        let x0 = f64_at(header, REQUEST_OFFSETS[7])?;
        let x1 = f64_at(header, REQUEST_OFFSETS[8])?;
        let y0 = f64_at(header, REQUEST_OFFSETS[9])?;
        let y1 = f64_at(header, REQUEST_OFFSETS[10])?;
        if !domain_ok(x0, x1) || !domain_ok(y0, y1) {
            return Err(AggregateError::Domain);
        }
        let cells = width.checked_mul(height).ok_or(AggregateError::Limit)?;
        if cells > MAX_GRID_CELLS {
            return Err(AggregateError::Limit);
        }
        let accumulator = cells
            .checked_mul(ACCUMULATOR_STRIDE_COUNT)
            .ok_or(AggregateError::Limit)?;
        let output = OUTPUT_HEADER_BYTES
            .checked_add(
                cells
                    .checked_mul(OUTPUT_STRIDE_COUNT)
                    .ok_or(AggregateError::Limit)?,
            )
            .ok_or(AggregateError::Limit)?;
        let peak = STREAM_HEADER_BYTES
            .checked_add(accumulator)
            .and_then(|v| v.checked_add(output.saturating_mul(OUTPUT_COPY_FACTOR)))
            .and_then(|v| v.checked_add(STREAM_CHUNK_BYTES * STREAM_CHUNK_COPY_FACTOR))
            .ok_or(AggregateError::Limit)?;
        if peak > budget {
            return Err(AggregateError::Limit);
        }
        Ok(Self {
            expected_points,
            received_points: 0,
            width,
            height,
            x0,
            x1,
            y0,
            y1,
            counts: vec![0; cells],
        })
    }

    /// Adds exactly one bounded source chunk. Returning `false` makes the
    /// caller yield/check cancellation before staging another chunk.
    pub fn push(&mut self, chunk: &[u8]) -> Result<bool, AggregateError> {
        if chunk.is_empty() || !chunk.len().is_multiple_of(REQUEST_STRIDE_COUNT) {
            return Err(AggregateError::Length);
        }
        let points = chunk.len() / REQUEST_STRIDE_COUNT;
        if points > STREAM_CHUNK_POINTS
            || self
                .received_points
                .checked_add(points)
                .ok_or(AggregateError::Limit)?
                > self.expected_points
        {
            return Err(AggregateError::Limit);
        }
        let mut x = Vec::with_capacity(points);
        let mut y = Vec::with_capacity(points);
        for index in 0..points {
            x.push(f64_at(chunk, index * 8)?);
            y.push(f64_at(chunk, points * 8 + index * 8)?);
        }
        kernels::bin_2d_count_scalar(
            &x,
            &y,
            self.x0,
            self.x1,
            self.y0,
            self.y1,
            self.width,
            self.height,
            &mut self.counts,
        );
        self.received_points += points;
        Ok(false)
    }

    pub fn finish(self) -> Result<Vec<u8>, AggregateError> {
        if self.received_points != self.expected_points {
            return Err(AggregateError::Length);
        }
        Ok(count_output(self.width, self.height, self.counts))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn stream_header(n: u32) -> Vec<u8> {
        let mut o = vec![0; STREAM_HEADER_BYTES];
        o[..4].copy_from_slice(STREAM_MAGIC);
        o[4..8].copy_from_slice(&STREAM_VERSION.to_le_bytes());
        o[8..12].copy_from_slice(&(STREAM_HEADER_BYTES as u32).to_le_bytes());
        o[16..20].copy_from_slice(&n.to_le_bytes());
        o[20..24].copy_from_slice(&4u32.to_le_bytes());
        o[24..28].copy_from_slice(&4u32.to_le_bytes());
        for (p, v) in [(32, 0.), (40, 4.), (48, 0.), (56, 4.)] {
            o[p..p + 8].copy_from_slice(&f64::to_le_bytes(v));
        }
        o
    }
    fn stream_chunk(points: &[(f64, f64)]) -> Vec<u8> {
        let mut o = Vec::with_capacity(points.len() * REQUEST_STRIDE_COUNT);
        for (x, _) in points {
            o.extend_from_slice(&x.to_le_bytes());
        }
        for (_, y) in points {
            o.extend_from_slice(&y.to_le_bytes());
        }
        o
    }
    fn pack(n: u32, color: bool) -> Vec<u8> {
        let mut o = vec![0; 64];
        o[..4].copy_from_slice(b"XYAG");
        o[4..8].copy_from_slice(&1u32.to_le_bytes());
        o[8..12].copy_from_slice(&64u32.to_le_bytes());
        o[12..16].copy_from_slice(&(if color { 1u32 } else { 0 }).to_le_bytes());
        o[16..20].copy_from_slice(&n.to_le_bytes());
        o[20..24].copy_from_slice(&4u32.to_le_bytes());
        o[24..28].copy_from_slice(&4u32.to_le_bytes());
        for (p, v) in [(32, 0.), (40, 4.), (48, 0.), (56, 4.)] {
            o[p..p + 8].copy_from_slice(&f64::to_le_bytes(v));
        }
        for i in 0..n {
            o.extend_from_slice(&((i % 4) as f64 + 0.5).to_le_bytes())
        }
        for i in 0..n {
            o.extend_from_slice(&((i % 4) as f64 + 0.5).to_le_bytes())
        }
        if color {
            for _ in 0..n {
                o.extend_from_slice(&[255, 0, 0, 255])
            }
        }
        o
    }
    #[test]
    fn resumes() {
        for color in [false, true] {
            let b = pack(2, color);
            let mut j = AggregateJob::begin(&b, 0, 1 << 20).unwrap();
            assert!(!j.step(&b, 1).unwrap());
            assert!(j.step(&b, 1).unwrap());
            let expected = j.finish();
            assert_eq!(&expected[..4], b"XYAO");

            let request_base = 13;
            let mut arena = vec![0xa5; request_base];
            arena.extend_from_slice(&b);
            let mut offset_job =
                AggregateJob::begin(&arena[request_base..], request_base, 1 << 20).unwrap();
            assert!(!offset_job.step(&arena, 1).unwrap());
            assert!(offset_job.step(&arena, 1).unwrap());
            assert_eq!(offset_job.finish(), expected);
        }
    }
    #[test]
    fn budgets_peak() {
        let b = pack(2, true);
        assert_eq!(
            AggregateJob::begin(&b, 0, b.len()).unwrap_err(),
            AggregateError::Limit
        );
        let mut huge = pack(1, true);
        huge[20..24].copy_from_slice(&2048u32.to_le_bytes());
        huge[24..28].copy_from_slice(&2048u32.to_le_bytes());
        assert_eq!(
            AggregateJob::begin(&huge, 0, 64 * 1024 * 1024).unwrap_err(),
            AggregateError::Limit
        )
    }

    #[test]
    fn empty_count_and_color_emit_zero_filled_native_parity_grids() {
        assert_eq!(
            std::mem::size_of::<MeanColorCell>(),
            ACCUMULATOR_STRIDE_COLOR
        );
        for color in [false, true] {
            let bytes = pack(0, color);
            let mut job = AggregateJob::begin(&bytes, 0, 1 << 20).unwrap();
            assert!(job.step(&bytes, 1).unwrap());
            let output = job.finish();
            assert_eq!(&output[..4], OUTPUT_MAGIC);
            assert!(output[OUTPUT_HEADER_BYTES..].iter().all(|byte| *byte == 0));
        }
    }

    #[test]
    fn stream_keeps_only_count_grid_and_one_bounded_chunk() {
        let mut job = StreamAggregateJob::begin(&stream_header(3), 8 << 20).unwrap();
        assert!(!job.push(&stream_chunk(&[(0.5, 0.5), (1.5, 1.5)])).unwrap());
        assert_eq!(job.finish().unwrap_err(), AggregateError::Length);

        let mut job = StreamAggregateJob::begin(&stream_header(3), 8 << 20).unwrap();
        assert!(!job.push(&stream_chunk(&[(0.5, 0.5), (1.5, 1.5)])).unwrap());
        assert!(!job.push(&stream_chunk(&[(2.5, 2.5)])).unwrap());
        let output = job.finish().unwrap();
        assert_eq!(&output[..4], OUTPUT_MAGIC);
        assert_eq!(
            f32::from_le_bytes(output[OUTPUT_HEADER_BYTES..][..4].try_into().unwrap()),
            1.0
        );

        let mut job = StreamAggregateJob::begin(&stream_header(1), 8 << 20).unwrap();
        assert_eq!(job.push(&[]).unwrap_err(), AggregateError::Length);
        assert_eq!(
            job.push(&vec![0; STREAM_CHUNK_BYTES + REQUEST_STRIDE_COUNT])
                .unwrap_err(),
            AggregateError::Limit
        );
    }
}
