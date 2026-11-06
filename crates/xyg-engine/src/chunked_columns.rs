//! Range-readable canonical f64 columns for ordered Tier-3 traces.
//!
//! Rust owns validation, zone-map selection, budgets, cancellation and the
//! provenance returned to hosts.  The on-disk format is deliberately small:
//! a fixed header, checked per-chunk metadata, then paired `(x, y)` f64 rows.
//! Hosts only open a local artifact and request a viewport (§5/§22/§28).

use std::collections::VecDeque;
use std::fs::File;
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

const RESIDENT_LIMIT: u64 = 8 * 1024 * 1024;

const MAGIC: &[u8; 4] = b"XYGC";
const VERSION: u32 = 2;
const LEGACY_VERSION: u32 = 1;
const HEADER_BYTES: u64 = 64;
const META_BYTES: u64 = 48;
const ROW_BYTES: u64 = 16;
const OVERVIEW_BYTES: u64 = 24;
const OVERVIEW_BUCKETS: u64 = 512;
const MAX_OVERVIEW_POINTS: u64 = OVERVIEW_BUCKETS * 4;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ChunkMeta {
    pub row_start: u64,
    pub row_count: u32,
    pub x_min: f64,
    pub x_max: f64,
    pub y_min: f64,
    pub y_max: f64,
}

#[derive(Debug, PartialEq)]
pub struct ChunkAccess {
    pub chunk: u32,
    pub row_start: u64,
    pub row_count: u32,
    pub hit: bool,
}

#[derive(Debug, PartialEq)]
pub struct RangeRead {
    pub x: Vec<f64>,
    pub y: Vec<f64>,
    pub row_ids: Vec<u64>,
    pub accesses: Vec<ChunkAccess>,
    pub resident_bytes: u64,
    pub evicted_chunks: Vec<u32>,
    pub generation: u64,
    pub first_chunk: u32,
    pub chunks_considered: u32,
    pub chunks_read: u32,
    pub bytes_read: u64,
}

#[derive(Debug, PartialEq)]
pub struct RangePage {
    pub read: RangeRead,
    pub next_chunk: u32,
    pub done: bool,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct OverviewPoint {
    pub row: u64,
    pub x: f64,
    pub y: f64,
}

#[derive(Debug, PartialEq)]
pub struct OverviewRead {
    pub points: Vec<OverviewPoint>,
    pub available: u32,
    pub source_rows: u64,
}

#[derive(Default)]
struct OverviewBucket {
    first: Option<OverviewPoint>,
    low: Option<OverviewPoint>,
    high: Option<OverviewPoint>,
    last: Option<OverviewPoint>,
    rows: u64,
}

impl OverviewBucket {
    fn push(&mut self, row: u64, x: f64, y: f64) {
        self.rows += 1;
        if !x.is_finite() || !y.is_finite() {
            return;
        }
        let point = OverviewPoint { row, x, y };
        self.first.get_or_insert(point);
        if self.low.is_none_or(|current| y < current.y) {
            self.low = Some(point);
        }
        if self.high.is_none_or(|current| y > current.y) {
            self.high = Some(point);
        }
        self.last = Some(point);
    }

    fn flush(&mut self, overview: &mut Vec<OverviewPoint>) {
        let Some(first) = self.first else {
            *self = Self::default();
            return;
        };
        let mut candidates = [
            first,
            self.low.unwrap(),
            self.high.unwrap(),
            self.last.unwrap(),
        ];
        candidates.sort_by_key(|point| point.row);
        for point in candidates {
            if overview
                .last()
                .is_none_or(|previous| previous.row != point.row)
            {
                overview.push(point);
            }
        }
        *self = Self::default();
    }
}

#[derive(Debug)]
pub enum Error {
    Io(io::Error),
    Corrupt(&'static str),
    InvalidRange,
    BudgetExceeded { needed: u64, budget: u64 },
    Cancelled,
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "chunked column I/O failed: {e}"),
            Self::Corrupt(reason) => write!(f, "corrupt XYGC artifact: {reason}"),
            Self::InvalidRange => write!(f, "viewport bounds must be finite and ordered"),
            Self::BudgetExceeded { needed, budget } => write!(
                f,
                "viewport needs {needed} bytes, exceeding the {budget}-byte read budget"
            ),
            Self::Cancelled => write!(f, "viewport read cancelled by a newer generation"),
        }
    }
}

impl std::error::Error for Error {}
impl Error {
    pub fn code(&self) -> u64 {
        match self {
            Self::Io(_) => 1,
            Self::Corrupt(_) => 2,
            Self::InvalidRange => 3,
            Self::BudgetExceeded { .. } => 4,
            Self::Cancelled => 5,
        }
    }
}
impl From<io::Error> for Error {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}

#[derive(Default)]
struct ResidentChunks {
    // Front is least recently used. No Arc clones: eviction releases the slab.
    entries: VecDeque<(u32, Vec<u8>)>,
    bytes: u64,
    #[cfg(test)]
    positioned_reads: u64,
}
impl ResidentChunks {
    fn trim(&mut self, limit: u64, evicted: &mut Vec<u32>) {
        while self.bytes > limit {
            let (id, raw) = self.entries.pop_front().unwrap();
            evicted.push(id);
            self.bytes -= raw.len() as u64;
        }
    }
}

pub struct ChunkedColumns {
    file: File,
    resident: Mutex<ResidentChunks>,
    rows: u64,
    chunk_rows: u32,
    metadata: Vec<ChunkMeta>,
    data_offset: u64,
    overview: Vec<OverviewPoint>,
}

pub struct Registered {
    store: ChunkedColumns,
    current_generation: AtomicU64,
}
static REGISTRY: OnceLock<Mutex<std::collections::HashMap<u64, Arc<Registered>>>> = OnceLock::new();
static NEXT_HANDLE: AtomicU64 = AtomicU64::new(1);
fn registry() -> &'static Mutex<std::collections::HashMap<u64, Arc<Registered>>> {
    REGISTRY.get_or_init(|| Mutex::new(std::collections::HashMap::new()))
}

pub fn reg_open(path: &Path) -> Result<u64, Error> {
    let store = ChunkedColumns::open(path)?;
    let handle = NEXT_HANDLE.fetch_add(1, Ordering::Relaxed);
    registry().lock().unwrap().insert(
        handle,
        Arc::new(Registered {
            store,
            current_generation: AtomicU64::new(0),
        }),
    );
    Ok(handle)
}
pub fn reg_get(handle: u64) -> Option<Arc<Registered>> {
    registry().lock().unwrap().get(&handle).cloned()
}
pub fn reg_remove(handle: u64) -> bool {
    registry().lock().unwrap().remove(&handle).is_some()
}
impl Registered {
    pub fn set_generation(&self, generation: u64) {
        // Generations are a monotonic cancellation watermark. An older host
        // request must never move the watermark backwards and invalidate
        // newer work that has already started.
        self.current_generation
            .fetch_max(generation, Ordering::AcqRel);
    }
    pub fn rows(&self) -> u64 {
        self.store.rows()
    }
    pub fn overview(&self, max_points: usize) -> Result<OverviewRead, Error> {
        self.store.overview(max_points)
    }
    pub fn read(
        &self,
        x0: f64,
        x1: f64,
        y: Option<(f64, f64)>,
        budget: u64,
        generation: u64,
    ) -> Result<RangeRead, Error> {
        self.store.read_range(x0, x1, y, budget, generation, |g| {
            self.current_generation.load(Ordering::Acquire) == g
        })
    }
    pub fn read_page(
        &self,
        x0: f64,
        x1: f64,
        y: Option<(f64, f64)>,
        budget: u64,
        generation: u64,
        cursor: u32,
    ) -> Result<RangePage, Error> {
        self.store
            .read_range_page((x0, x1), y, budget, generation, cursor, |g| {
                self.current_generation.load(Ordering::Acquire) == g
            })
    }
}

fn finite_min_max(values: &[(f64, f64)]) -> (f64, f64, f64, f64) {
    let (mut xmin, mut xmax, mut ymin, mut ymax) = (
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
    );
    for &(x, y) in values {
        if x.is_finite() {
            xmin = xmin.min(x);
            xmax = xmax.max(x);
        }
        if y.is_finite() {
            ymin = ymin.min(y);
            ymax = ymax.max(y);
        }
    }
    (xmin, xmax, ymin, ymax)
}

impl ChunkedColumns {
    /// Write a local/offline artifact from an iterator. Only one chunk is
    /// resident during construction; x must be nondecreasing for exact
    /// binary-search viewport pruning.
    pub fn create<I>(path: &Path, rows: I, chunk_rows: u32) -> Result<(), Error>
    where
        I: IntoIterator<Item = (f64, f64)>,
        I::IntoIter: ExactSizeIterator,
    {
        if chunk_rows == 0 {
            return Err(Error::Corrupt("chunk_rows is zero"));
        }
        let mut rows = rows.into_iter();
        let total_rows = rows.len() as u64;
        let chunk_count = total_rows.div_ceil(u64::from(chunk_rows));
        if chunk_count > u64::from(u32::MAX) {
            return Err(Error::Corrupt("too many chunks"));
        }
        let data_offset = HEADER_BYTES + META_BYTES * chunk_count;
        let overview_offset = data_offset
            .checked_add(
                total_rows
                    .checked_mul(ROW_BYTES)
                    .ok_or(Error::Corrupt("size overflow"))?,
            )
            .ok_or(Error::Corrupt("size overflow"))?;
        let mut file = File::create(path)?;
        file.set_len(data_offset)?;
        file.seek(SeekFrom::Start(data_offset))?;
        let mut metadata = Vec::with_capacity(chunk_count as usize);
        let overview_bucket_rows = total_rows.div_ceil(OVERVIEW_BUCKETS).max(1);
        let mut overview = Vec::with_capacity(
            usize::try_from(total_rows.div_ceil(overview_bucket_rows).saturating_mul(4))
                .unwrap_or(0),
        );
        let mut overview_bucket = OverviewBucket::default();
        let mut current = Vec::with_capacity(chunk_rows as usize);
        let mut last_x = f64::NEG_INFINITY;
        let mut row_start = 0u64;
        let mut consumed = 0u64;
        for pair @ (x, _) in rows.by_ref() {
            consumed = consumed
                .checked_add(1)
                .ok_or(Error::Corrupt("row count overflow"))?;
            if x.is_finite() && x < last_x {
                return Err(Error::Corrupt("x is not sorted"));
            }
            if x.is_finite() {
                last_x = x;
            }
            current.push(pair);
            overview_bucket.push(consumed - 1, pair.0, pair.1);
            if current.len() == chunk_rows as usize {
                write_chunk(&mut file, &mut metadata, row_start, &current)?;
                row_start += current.len() as u64;
                current.clear();
            }
            if overview_bucket.rows == overview_bucket_rows {
                overview_bucket.flush(&mut overview);
            }
        }
        if !current.is_empty() {
            write_chunk(&mut file, &mut metadata, row_start, &current)?;
        }
        if overview_bucket.rows > 0 {
            overview_bucket.flush(&mut overview);
        }
        if consumed != total_rows || metadata.len() as u64 != chunk_count {
            return Err(Error::Corrupt("iterator length changed during creation"));
        }
        let mut header = [0u8; HEADER_BYTES as usize];
        header[0..4].copy_from_slice(MAGIC);
        header[4..8].copy_from_slice(&VERSION.to_le_bytes());
        header[8..16].copy_from_slice(&total_rows.to_le_bytes());
        header[16..20].copy_from_slice(&chunk_rows.to_le_bytes());
        header[20..24].copy_from_slice(&(metadata.len() as u32).to_le_bytes());
        header[24..32].copy_from_slice(&data_offset.to_le_bytes());
        header[32..40].copy_from_slice(&overview_offset.to_le_bytes());
        header[40..44].copy_from_slice(&(overview.len() as u32).to_le_bytes());
        file.seek(SeekFrom::Start(0))?;
        file.write_all(&header)?;
        for meta in metadata {
            file.write_all(&meta.row_start.to_le_bytes())?;
            file.write_all(&meta.row_count.to_le_bytes())?;
            file.write_all(&0u32.to_le_bytes())?;
            for value in [meta.x_min, meta.x_max, meta.y_min, meta.y_max] {
                file.write_all(&value.to_le_bytes())?;
            }
        }
        file.seek(SeekFrom::Start(overview_offset))?;
        for point in &overview {
            file.write_all(&point.row.to_le_bytes())?;
            file.write_all(&point.x.to_le_bytes())?;
            file.write_all(&point.y.to_le_bytes())?;
        }
        file.sync_all()?;
        Ok(())
    }

    pub fn open(path: &Path) -> Result<Self, Error> {
        let mut file = File::open(path)?;
        let file_len = file.metadata()?.len();
        let mut header = [0u8; HEADER_BYTES as usize];
        file.read_exact(&mut header).map_err(|e| {
            if e.kind() == io::ErrorKind::UnexpectedEof {
                Error::Corrupt("short header")
            } else {
                e.into()
            }
        })?;
        if &header[0..4] != MAGIC {
            return Err(Error::Corrupt("bad magic"));
        }
        let version = u32::from_le_bytes(header[4..8].try_into().unwrap());
        if version != VERSION && version != LEGACY_VERSION {
            return Err(Error::Corrupt("unsupported version"));
        }
        if (version == LEGACY_VERSION && header[32..].iter().any(|&byte| byte != 0))
            || (version == VERSION && header[44..].iter().any(|&byte| byte != 0))
        {
            return Err(Error::Corrupt("nonzero reserved header bytes"));
        }
        let rows = u64::from_le_bytes(header[8..16].try_into().unwrap());
        let chunk_rows = u32::from_le_bytes(header[16..20].try_into().unwrap());
        let chunk_count = u32::from_le_bytes(header[20..24].try_into().unwrap());
        let data_offset = u64::from_le_bytes(header[24..32].try_into().unwrap());
        if chunk_rows == 0 || data_offset != HEADER_BYTES + META_BYTES * u64::from(chunk_count) {
            return Err(Error::Corrupt("inconsistent header"));
        }
        let rows_end = data_offset
            .checked_add(
                rows.checked_mul(ROW_BYTES)
                    .ok_or(Error::Corrupt("size overflow"))?,
            )
            .ok_or(Error::Corrupt("size overflow"))?;
        let (overview_offset, overview_count) = if version == VERSION {
            (
                u64::from_le_bytes(header[32..40].try_into().unwrap()),
                u32::from_le_bytes(header[40..44].try_into().unwrap()),
            )
        } else {
            (rows_end, 0)
        };
        if u64::from(overview_count) > MAX_OVERVIEW_POINTS || u64::from(overview_count) > rows {
            return Err(Error::Corrupt("invalid overview count"));
        }
        if overview_offset != rows_end {
            return Err(Error::Corrupt("inconsistent overview offset"));
        }
        let expected = overview_offset
            .checked_add(u64::from(overview_count) * OVERVIEW_BYTES)
            .ok_or(Error::Corrupt("size overflow"))?;
        if file_len != expected {
            return Err(Error::Corrupt("file length does not match header"));
        }
        let mut metadata = Vec::with_capacity(chunk_count as usize);
        let mut expected_start = 0u64;
        let mut previous_max = f64::NEG_INFINITY;
        for _ in 0..chunk_count {
            let mut raw = [0u8; META_BYTES as usize];
            file.read_exact(&mut raw)?;
            if raw[12..16] != [0; 4] {
                return Err(Error::Corrupt("nonzero reserved metadata bytes"));
            }
            let meta = ChunkMeta {
                row_start: u64::from_le_bytes(raw[0..8].try_into().unwrap()),
                row_count: u32::from_le_bytes(raw[8..12].try_into().unwrap()),
                x_min: f64::from_le_bytes(raw[16..24].try_into().unwrap()),
                x_max: f64::from_le_bytes(raw[24..32].try_into().unwrap()),
                y_min: f64::from_le_bytes(raw[32..40].try_into().unwrap()),
                y_max: f64::from_le_bytes(raw[40..48].try_into().unwrap()),
            };
            if meta.row_start != expected_start
                || meta.row_count == 0
                || meta.row_count > chunk_rows
                || !meta.x_min.is_finite()
                || !meta.x_max.is_finite()
                || !meta.y_min.is_finite()
                || !meta.y_max.is_finite()
                || meta.x_min > meta.x_max
                || meta.y_min > meta.y_max
                || meta.x_min < previous_max
            {
                return Err(Error::Corrupt("invalid or unordered chunk metadata"));
            }
            expected_start += u64::from(meta.row_count);
            previous_max = meta.x_max;
            metadata.push(meta);
        }
        if expected_start != rows {
            return Err(Error::Corrupt("chunk rows do not sum to row count"));
        }
        let mut overview = Vec::with_capacity(overview_count as usize);
        file.seek(SeekFrom::Start(overview_offset))?;
        let mut previous_row = None;
        for _ in 0..overview_count {
            let mut raw = [0u8; OVERVIEW_BYTES as usize];
            file.read_exact(&mut raw)?;
            let point = OverviewPoint {
                row: u64::from_le_bytes(raw[0..8].try_into().unwrap()),
                x: f64::from_le_bytes(raw[8..16].try_into().unwrap()),
                y: f64::from_le_bytes(raw[16..24].try_into().unwrap()),
            };
            if point.row >= rows
                || !point.x.is_finite()
                || !point.y.is_finite()
                || previous_row.is_some_and(|row| row >= point.row)
            {
                return Err(Error::Corrupt("invalid overview point"));
            }
            previous_row = Some(point.row);
            overview.push(point);
        }
        Ok(Self {
            file,
            resident: Mutex::new(ResidentChunks::default()),
            rows,
            chunk_rows,
            metadata,
            data_offset,
            overview,
        })
    }

    pub fn rows(&self) -> u64 {
        self.rows
    }
    pub fn chunk_rows(&self) -> u32 {
        self.chunk_rows
    }
    pub fn metadata(&self) -> &[ChunkMeta] {
        &self.metadata
    }

    /// Return a screen-bounded, precomputed first-paint overview. No canonical
    /// detail rows are read here; row IDs preserve identity for later exact
    /// viewport refinement.
    pub fn overview(&self, max_points: usize) -> Result<OverviewRead, Error> {
        if max_points == 0 {
            return Err(Error::InvalidRange);
        }
        let available = self.overview.len();
        let points = if available <= max_points {
            self.overview.clone()
        } else if max_points == 1 {
            vec![self.overview[0]]
        } else {
            (0..max_points)
                .map(|index| {
                    let source = index * (available - 1) / (max_points - 1);
                    self.overview[source]
                })
                .collect()
        };
        Ok(OverviewRead {
            points,
            available: available as u32,
            source_rows: self.rows,
        })
    }

    /// Read exact rows in an x viewport. Zone maps select chunks; y bounds
    /// optionally prune chunks and rows. `is_current` is checked before every
    /// positioned chunk read, making stale work generation-safe.
    pub fn read_range<F>(
        &self,
        x0: f64,
        x1: f64,
        y: Option<(f64, f64)>,
        budget: u64,
        generation: u64,
        mut is_current: F,
    ) -> Result<RangeRead, Error>
    where
        F: FnMut(u64) -> bool,
    {
        if !x0.is_finite()
            || !x1.is_finite()
            || x0 > x1
            || y.is_some_and(|(a, b)| !a.is_finite() || !b.is_finite() || a > b)
        {
            return Err(Error::InvalidRange);
        }
        let first = self.metadata.partition_point(|m| m.x_max < x0);
        let end = self.metadata.partition_point(|m| m.x_min <= x1);
        let candidates = &self.metadata[first.min(end)..end];
        let mut selected = Vec::new();
        for (offset, meta) in candidates.iter().enumerate() {
            if y.is_some_and(|(a, b)| meta.y_max < a || meta.y_min > b) {
                continue;
            }
            selected.push((first + offset, *meta));
        }
        let needed = selected
            .iter()
            .try_fold(0u64, |n, (_, m)| {
                n.checked_add(u64::from(m.row_count) * ROW_BYTES)
            })
            .ok_or(Error::Corrupt("read size overflow"))?;
        if needed > budget {
            return Err(Error::BudgetExceeded { needed, budget });
        }
        let mut out = RangeRead {
            x: Vec::new(),
            y: Vec::new(),
            row_ids: Vec::new(),
            accesses: Vec::new(),
            resident_bytes: 0,
            evicted_chunks: Vec::new(),
            generation,
            first_chunk: first as u32,
            chunks_considered: candidates.len() as u32,
            chunks_read: 0,
            bytes_read: 0,
        };
        if !is_current(generation) {
            return Err(Error::Cancelled);
        }
        let mut resident = self.resident.lock().unwrap();
        if !is_current(generation) {
            return Err(Error::Cancelled);
        }
        resident.trim(budget.min(RESIDENT_LIMIT), &mut out.evicted_chunks);
        for (index, meta) in selected {
            if !is_current(generation) {
                return Err(Error::Cancelled);
            }
            self.read_chunk(
                &mut resident,
                index as u32,
                &meta,
                budget,
                generation,
                &mut is_current,
                &mut out,
                (x0, x1),
                y,
            )?;
        }
        if !is_current(generation) {
            return Err(Error::Cancelled);
        }
        out.resident_bytes = resident.bytes;
        Ok(out)
    }

    /// Read the next whole-chunk-bounded page of an exact viewport. `cursor`
    /// is an opaque absolute chunk position returned by the preceding page;
    /// zero starts at Rust's zone-map-selected first chunk. A page never reads
    /// more than `budget` canonical bytes and always advances or fails closed.
    /// Cancellation is checked around every positioned read and again before
    /// publication, so a generation superseded during the final read cannot
    /// return a stale page.
    pub fn read_range_page<F>(
        &self,
        x: (f64, f64),
        y: Option<(f64, f64)>,
        budget: u64,
        generation: u64,
        cursor: u32,
        mut is_current: F,
    ) -> Result<RangePage, Error>
    where
        F: FnMut(u64) -> bool,
    {
        let (x0, x1) = x;
        if !x0.is_finite()
            || !x1.is_finite()
            || x0 > x1
            || y.is_some_and(|(a, b)| !a.is_finite() || !b.is_finite() || a > b)
        {
            return Err(Error::InvalidRange);
        }
        let first = self.metadata.partition_point(|m| m.x_max < x0);
        let end = self.metadata.partition_point(|m| m.x_min <= x1);
        let mut index = if cursor == 0 { first } else { cursor as usize };
        if index < first || index > end {
            return Err(Error::InvalidRange);
        }
        let page_first = index;
        let mut out = RangeRead {
            x: Vec::new(),
            y: Vec::new(),
            row_ids: Vec::new(),
            accesses: Vec::new(),
            resident_bytes: 0,
            evicted_chunks: Vec::new(),
            generation,
            first_chunk: page_first as u32,
            chunks_considered: 0,
            chunks_read: 0,
            bytes_read: 0,
        };
        if !is_current(generation) {
            return Err(Error::Cancelled);
        }
        let mut resident = self.resident.lock().unwrap();
        if !is_current(generation) {
            return Err(Error::Cancelled);
        }
        resident.trim(budget.min(RESIDENT_LIMIT), &mut out.evicted_chunks);
        let mut admitted = 0u64;
        while index < end {
            if !is_current(generation) {
                return Err(Error::Cancelled);
            }
            let meta = self.metadata[index];
            out.chunks_considered += 1;
            if y.is_some_and(|(a, b)| meta.y_max < a || meta.y_min > b) {
                index += 1;
                continue;
            }
            let bytes = u64::from(meta.row_count) * ROW_BYTES;
            if admitted
                .checked_add(bytes)
                .ok_or(Error::Corrupt("read size overflow"))?
                > budget
            {
                if admitted == 0 {
                    return Err(Error::BudgetExceeded {
                        needed: bytes,
                        budget,
                    });
                }
                break;
            }
            admitted += bytes;
            self.read_chunk(
                &mut resident,
                index as u32,
                &meta,
                budget,
                generation,
                &mut is_current,
                &mut out,
                (x0, x1),
                y,
            )?;
            index += 1;
        }
        if !is_current(generation) {
            return Err(Error::Cancelled);
        }
        out.resident_bytes = resident.bytes;
        Ok(RangePage {
            read: out,
            next_chunk: index as u32,
            done: index >= end,
        })
    }
    // The per-store lock serializes slab ownership and accounting, including
    // in-flight reads. Generation changes never need this lock. Validated slabs
    // are immutable and reusable across viewport generations and predicates.
    #[allow(clippy::too_many_arguments)]
    fn read_chunk<F: FnMut(u64) -> bool>(
        &self,
        resident: &mut ResidentChunks,
        index: u32,
        meta: &ChunkMeta,
        budget: u64,
        generation: u64,
        is_current: &mut F,
        out: &mut RangeRead,
        x_bounds: (f64, f64),
        y_bounds: Option<(f64, f64)>,
    ) -> Result<(), Error> {
        if !is_current(generation) {
            return Err(Error::Cancelled);
        }
        let bytes = u64::from(meta.row_count) * ROW_BYTES;
        let limit = budget.min(RESIDENT_LIMIT);
        let position = resident.entries.iter().position(|(id, _)| *id == index);
        let hit = position.is_some();
        let raw = if let Some(position) = position {
            let (_, raw) = resident.entries.remove(position).unwrap();
            resident.bytes -= bytes;
            raw
        } else {
            // Reserve space before allocating scratch. Oversized chunks retain
            // the existing admission contract but bypass resident caching.
            resident.trim(limit.saturating_sub(bytes), &mut out.evicted_chunks);
            let mut raw = vec![0u8; bytes as usize];
            #[cfg(test)]
            {
                resident.positioned_reads += 1;
            }
            read_exact_at(
                &self.file,
                &mut raw,
                self.data_offset + meta.row_start * ROW_BYTES,
            )?;
            if !is_current(generation) {
                return Err(Error::Cancelled);
            }
            validate_chunk_rows(&raw, meta)?;
            raw
        };
        // A cancelled hit is released as well; accounting already excludes it.
        if !is_current(generation) {
            return Err(Error::Cancelled);
        }
        if !hit {
            out.chunks_read += 1;
            out.bytes_read += bytes;
        }
        out.accesses.push(ChunkAccess {
            chunk: index,
            row_start: meta.row_start,
            row_count: meta.row_count,
            hit,
        });
        for (offset, row) in raw.chunks_exact(16).enumerate() {
            let x = f64::from_le_bytes(row[0..8].try_into().unwrap());
            let y = f64::from_le_bytes(row[8..16].try_into().unwrap());
            if x.is_finite()
                && y.is_finite()
                && x >= x_bounds.0
                && x <= x_bounds.1
                && y_bounds.is_none_or(|(a, b)| y >= a && y <= b)
            {
                out.x.push(x);
                out.y.push(y);
                out.row_ids.push(meta.row_start + offset as u64);
            }
        }
        if bytes <= limit {
            resident.bytes += bytes;
            resident.entries.push_back((index, raw));
        }
        Ok(())
    }
}

// Validate fetched detail before it can be published. This checks structural
// consistency with the admitted zone map, not arbitrary byte authentication.
fn validate_chunk_rows(raw: &[u8], meta: &ChunkMeta) -> Result<(), Error> {
    let (mut xmin, mut xmax, mut ymin, mut ymax) = (
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
    );
    let mut previous_x = f64::NEG_INFINITY;
    for row in raw.chunks_exact(ROW_BYTES as usize) {
        let x = f64::from_le_bytes(row[..8].try_into().unwrap());
        let y = f64::from_le_bytes(row[8..].try_into().unwrap());
        if x.is_finite() {
            if x < previous_x {
                return Err(Error::Corrupt("unordered fetched chunk rows"));
            }
            previous_x = x;
            xmin = xmin.min(x);
            xmax = xmax.max(x);
        }
        if y.is_finite() {
            ymin = ymin.min(y);
            ymax = ymax.max(y);
        }
    }
    if (xmin, xmax, ymin, ymax) != (meta.x_min, meta.x_max, meta.y_min, meta.y_max) {
        return Err(Error::Corrupt("fetched chunk bounds differ from metadata"));
    }
    Ok(())
}

fn write_chunk(
    file: &mut File,
    metadata: &mut Vec<ChunkMeta>,
    row_start: u64,
    chunk: &[(f64, f64)],
) -> Result<(), Error> {
    let (x_min, x_max, y_min, y_max) = finite_min_max(chunk);
    if !x_min.is_finite() || !x_max.is_finite() || !y_min.is_finite() || !y_max.is_finite() {
        return Err(Error::Corrupt("chunk has no finite x/y bounds"));
    }
    metadata.push(ChunkMeta {
        row_start,
        row_count: chunk.len() as u32,
        x_min,
        x_max,
        y_min,
        y_max,
    });
    for &(x, y) in chunk {
        file.write_all(&x.to_le_bytes())?;
        file.write_all(&y.to_le_bytes())?;
    }
    Ok(())
}

#[cfg(unix)]
fn read_exact_at(file: &File, mut buf: &mut [u8], mut offset: u64) -> io::Result<()> {
    use std::os::unix::fs::FileExt;
    while !buf.is_empty() {
        match file.read_at(buf, offset) {
            Ok(0) => return Err(io::Error::from(io::ErrorKind::UnexpectedEof)),
            Ok(n) => {
                offset += n as u64;
                buf = &mut buf[n..];
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(error) => return Err(error),
        }
    }
    Ok(())
}

#[cfg(windows)]
fn read_exact_at(file: &File, mut buf: &mut [u8], mut offset: u64) -> io::Result<()> {
    use std::os::windows::fs::FileExt;
    while !buf.is_empty() {
        match file.seek_read(buf, offset) {
            Ok(0) => return Err(io::Error::from(io::ErrorKind::UnexpectedEof)),
            Ok(n) => {
                offset += n as u64;
                buf = &mut buf[n..];
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(error) => return Err(error),
        }
    }
    Ok(())
}

#[cfg(not(any(unix, windows)))]
fn read_exact_at(file: &File, buf: &mut [u8], offset: u64) -> io::Result<()> {
    let mut file = file.try_clone()?;
    file.seek(SeekFrom::Start(offset))?;
    file.read_exact(buf)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};
    fn path(name: &str) -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "xyg-{name}-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    #[test]
    fn fetched_chunk_corruption_fails_closed_in_both_read_modes() {
        let p = path("detail-corruption.xygc");
        ChunkedColumns::create(&p, (0..8).map(|i| (i as f64, i as f64)), 4).unwrap();
        let original = std::fs::read(&p).unwrap();
        let offset = (HEADER_BYTES + 2 * META_BYTES) as usize;
        // Wrong extrema, an out-of-map ordinate, and unordered interior x
        // values all preserve file length and valid open-time metadata.
        for (row, axis, value) in [(0, 0, 0.5), (1, 1, 99.0), (2, 0, 0.5)] {
            let mut bytes = original.clone();
            let start = offset + row * 16 + axis * 8;
            bytes[start..start + 8].copy_from_slice(&f64::to_le_bytes(value));
            std::fs::write(&p, &bytes).unwrap();
            let store = ChunkedColumns::open(&p).unwrap();
            assert!(matches!(
                store.read_range(0.0, 7.0, None, 128, 0, |_| true),
                Err(Error::Corrupt(_))
            ));
            assert!(matches!(
                store.read_range_page((0.0, 7.0), None, 64, 0, 0, |_| true),
                Err(Error::Corrupt(_))
            ));
        }
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn unpaged_read_checks_generation_even_without_io_and_before_publication() {
        let p = path("empty-cancel.xygc");
        ChunkedColumns::create(&p, (0..8).map(|i| (i as f64, i as f64)), 4).unwrap();
        let store = ChunkedColumns::open(&p).unwrap();
        for (x0, x1, y) in [(20.0, 30.0, None), (0.0, 7.0, Some((20.0, 30.0)))] {
            assert!(matches!(
                store.read_range(x0, x1, y, 128, 0, |_| false),
                Err(Error::Cancelled)
            ));
        }
        let mut checks = 0;
        assert!(matches!(
            store.read_range(0.0, 3.0, None, 64, 0, |_| {
                checks += 1;
                checks < 7 // final publication checkpoint after cache admission
            }),
            Err(Error::Cancelled)
        ));
        assert_eq!(checks, 7);
        std::fs::remove_file(p).unwrap();
    }

    fn assert_accounting(store: &ChunkedColumns, limit: u64) -> Vec<u32> {
        let resident = store.resident.lock().unwrap();
        assert_eq!(
            resident.bytes,
            resident
                .entries
                .iter()
                .map(|(_, raw)| raw.len() as u64)
                .sum()
        );
        assert!(resident.bytes <= limit);
        resident.entries.iter().map(|(id, _)| *id).collect()
    }

    #[test]
    fn repeated_overlap_reuses_real_reads_and_keeps_exact_row_identity() {
        let p = path("cache-overlap.xygc");
        // Duplicate x values and nonfinite y prevent coordinate-based identity.
        let rows: Vec<_> = (0..1000)
            .map(|i| {
                (
                    (i / 2) as f64,
                    if i % 13 == 0 {
                        f64::NAN
                    } else {
                        (i % 7) as f64
                    },
                )
            })
            .collect();
        ChunkedColumns::create(&p, rows.clone(), 100).unwrap();
        let store = ChunkedColumns::open(&p).unwrap();
        let first = store
            .read_range(50.0, 149.0, None, 4800, 1, |_| true)
            .unwrap();
        assert_eq!(first.bytes_read, 3200);
        let second = store
            .read_range_page((100.0, 199.0), Some((2.0, 5.0)), 4800, 2, 0, |_| true)
            .unwrap();
        assert_eq!(
            second
                .read
                .accesses
                .iter()
                .map(|a| (a.chunk, a.hit))
                .collect::<Vec<_>>(),
            vec![(2, true), (3, false)]
        );
        assert_eq!(second.read.bytes_read, 1600);
        assert_eq!(second.read.resident_bytes, 4800);
        let oracle: Vec<_> = rows
            .iter()
            .enumerate()
            .filter(|(_, (x, y))| (100.0..=199.0).contains(x) && (2.0..=5.0).contains(y))
            .map(|(id, _)| id as u64)
            .collect();
        assert_eq!(second.read.row_ids, oracle);
        for ((&id, &x), &y) in second
            .read
            .row_ids
            .iter()
            .zip(&second.read.x)
            .zip(&second.read.y)
        {
            assert_eq!((x, y), rows[id as usize]);
        }
        let repeated = store
            .read_range(100.0, 199.0, Some((2.0, 5.0)), 4800, 3, |_| true)
            .unwrap();
        assert_eq!(repeated.bytes_read, 0);
        assert_eq!(repeated.row_ids, oracle);
        assert_eq!(store.resident.lock().unwrap().positioned_reads, 3);
        assert_eq!(assert_accounting(&store, 4800), vec![1, 2, 3]);
        // New viewport evicts the least recently used chunk, not the overlap.
        let eviction = store
            .read_range(200.0, 249.0, None, 4800, 4, |_| true)
            .unwrap();
        assert_eq!(eviction.evicted_chunks, vec![1]);
        assert_eq!(assert_accounting(&store, 4800), vec![2, 3, 4]);
        assert!(matches!(
            store.read_range(100.0, 199.0, None, 1600, 5, |_| true),
            Err(Error::BudgetExceeded {
                needed: 3200,
                budget: 1600
            })
        ));
        assert_eq!(assert_accounting(&store, 4800), vec![2, 3, 4]);
        // Page admission counts hits, so a warm cache cannot enlarge a page.
        let page = store
            .read_range_page((100.0, 249.0), None, 1600, 6, 0, |_| true)
            .unwrap();
        assert_eq!(page.next_chunk, 3);
        assert!(!page.done);
        assert_eq!(page.read.row_ids.len(), 92);
        assert_accounting(&store, 1600);
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn cancelled_misses_hits_and_failed_io_keep_accounting_consistent() {
        let p = path("cache-cancel.xygc");
        ChunkedColumns::create(&p, (0..30).map(|i| (i as f64, i as f64)), 10).unwrap();
        let store = ChunkedColumns::open(&p).unwrap();
        let mut checks = 0;
        assert!(matches!(
            store.read_range(0.0, 9.0, None, 320, 1, |_| {
                checks += 1;
                checks < 5 // superseded immediately after actual positioned I/O
            }),
            Err(Error::Cancelled)
        ));
        assert_eq!(store.resident.lock().unwrap().positioned_reads, 1);
        assert!(assert_accounting(&store, 320).is_empty());
        store.read_range(0.0, 9.0, None, 320, 2, |_| true).unwrap();
        let mut checks = 0;
        assert!(matches!(
            store.read_range_page((0.0, 9.0), None, 320, 3, 0, |_| {
                checks += 1;
                checks < 5 // superseded on a cache hit before decode
            }),
            Err(Error::Cancelled)
        ));
        assert_accounting(&store, 320);
        assert_eq!(store.resident.lock().unwrap().positioned_reads, 2);
        // A stale request must not shrink current residency.
        store.read_range(0.0, 9.0, None, 320, 4, |_| true).unwrap();
        assert!(matches!(
            store.read_range_page((0.0, 29.0), None, 1, 3, 0, |_| false),
            Err(Error::Cancelled)
        ));
        assert_eq!(assert_accounting(&store, 320), vec![0]);
        // Failure on a nonresident chunk cannot publish or admit partial bytes.
        File::options()
            .write(true)
            .open(&p)
            .unwrap()
            .set_len(store.data_offset + 170)
            .unwrap();
        assert!(matches!(
            store.read_range(10.0, 19.0, None, 320, 5, |_| true),
            Err(Error::Io(_))
        ));
        assert_eq!(assert_accounting(&store, 320), vec![0]);
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn superseded_waiter_cannot_evict_current_generation_residency() {
        let p = path("cache-waiter.xygc");
        ChunkedColumns::create(&p, (0..20).map(|i| (i as f64, i as f64)), 10).unwrap();
        let registered = Registered {
            store: ChunkedColumns::open(&p).unwrap(),
            current_generation: AtomicU64::new(1),
        };
        registered.read(0.0, 9.0, None, 320, 1).unwrap();
        std::thread::scope(|scope| {
            let guard = registered.store.resident.lock().unwrap();
            let (tx, rx) = std::sync::mpsc::channel();
            let registered_ref = &registered;
            let waiter = scope.spawn(move || {
                let mut sent = false;
                registered_ref
                    .store
                    .read_range_page((0.0, 19.0), None, 1, 1, 0, |g| {
                        if !sent {
                            tx.send(()).unwrap();
                            sent = true;
                        }
                        registered_ref.current_generation.load(Ordering::Acquire) == g
                    })
            });
            rx.recv().unwrap();
            registered.set_generation(2);
            drop(guard);
            assert!(matches!(waiter.join().unwrap(), Err(Error::Cancelled)));
        });
        assert_eq!(assert_accounting(&registered.store, 320), vec![0]);
        let read = registered.read(0.0, 19.0, None, 320, 2).unwrap();
        assert_eq!(read.bytes_read, 160);
        assert_eq!(read.row_ids, (0..20).collect::<Vec<_>>());
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn cache_cap_bypasses_oversized_slabs_without_rejecting_admitted_reads() {
        let p = path("cache-cap.xygc");
        // Bounded 9 MiB fixture: one slab above the fixed resident ceiling.
        let count = (RESIDENT_LIMIT / ROW_BYTES + 1) as u32;
        ChunkedColumns::create(&p, (0..count).map(|i| (i as f64, i as f64)), count).unwrap();
        let store = ChunkedColumns::open(&p).unwrap();
        for page in [false, true] {
            let read = if page {
                store
                    .read_range_page((0.0, 0.0), None, u64::from(count) * 16, 2, 0, |_| true)
                    .unwrap()
                    .read
            } else {
                store
                    .read_range(0.0, 0.0, None, u64::from(count) * 16, 1, |_| true)
                    .unwrap()
            };
            assert_eq!(read.row_ids, vec![0]);
            assert_eq!(read.resident_bytes, 0);
            assert_eq!(read.chunks_read, 1);
        }
        assert_eq!(store.resident.lock().unwrap().positioned_reads, 2);
        assert_accounting(&store, 0);
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn range_matches_oracle_and_records_pruning() {
        let p = path("range.xygc");
        let rows: Vec<_> = (0..100).map(|i| (i as f64, (i % 7) as f64)).collect();
        ChunkedColumns::create(&p, rows.clone(), 10).unwrap();
        let store = ChunkedColumns::open(&p).unwrap();
        let got = store
            .read_range(23.0, 41.0, Some((2.0, 4.0)), 1 << 20, 7, |_| true)
            .unwrap();
        let oracle: Vec<_> = rows
            .into_iter()
            .filter(|(x, y)| (23.0..=41.0).contains(x) && (2.0..=4.0).contains(y))
            .collect();
        assert_eq!(
            got.x
                .iter()
                .copied()
                .zip(got.y.iter().copied())
                .collect::<Vec<_>>(),
            oracle
        );
        assert_eq!(got.chunks_considered, 3);
        assert_eq!(got.bytes_read, 3 * 10 * 16);
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn paged_range_is_bounded_resumable_and_matches_oracle() {
        let p = path("paged-range.xygc");
        let rows: Vec<_> = (0..10_000).map(|i| (i as f64, (i % 11) as f64)).collect();
        ChunkedColumns::create(&p, rows.clone(), 128).unwrap();
        let store = ChunkedColumns::open(&p).unwrap();
        let mut cursor = 0;
        let mut got = Vec::new();
        let mut pages = 0;
        loop {
            let page = store
                .read_range_page(
                    (123.0, 9_321.0),
                    Some((3.0, 7.0)),
                    3 * 128 * 16,
                    9,
                    cursor,
                    |_| true,
                )
                .unwrap();
            assert!(page.read.bytes_read <= 3 * 128 * 16);
            assert!(page.done || page.next_chunk > cursor);
            got.extend(page.read.x.iter().copied().zip(page.read.y.iter().copied()));
            pages += 1;
            if page.done {
                break;
            }
            cursor = page.next_chunk;
        }
        let oracle: Vec<_> = rows
            .into_iter()
            .filter(|(x, y)| (123.0..=9_321.0).contains(x) && (3.0..=7.0).contains(y))
            .collect();
        assert_eq!(got, oracle);
        assert!(pages > 20);
        assert!(matches!(
            store.read_range_page((0.0, 100.0), None, 16, 10, 0, |_| true),
            Err(Error::BudgetExceeded { .. })
        ));
        assert!(matches!(
            store.read_range_page((0.0, 100.0), None, 4096, 10, 0, |_| false),
            Err(Error::Cancelled)
        ));
        let mut checks = 0;
        assert!(matches!(
            store.read_range_page((0.0, 100.0), None, 4096, 10, 0, |_| {
                checks += 1;
                // Supersede immediately after the actual positioned read,
                // before structural validation, decode or cache admission.
                checks < 5
            }),
            Err(Error::Cancelled)
        ));
        assert_eq!(checks, 5);
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn overview_is_precomputed_bounded_and_identity_stable() {
        let p = path("overview.xygc");
        let rows: Vec<_> = (0..10_000)
            .map(|i| (i as f64, ((i * 17) % 101) as f64))
            .collect();
        ChunkedColumns::create(&p, rows.clone(), 257).unwrap();
        let store = ChunkedColumns::open(&p).unwrap();
        let full = store.overview(10_000).unwrap();
        assert!(full.points.len() <= 4 * OVERVIEW_BUCKETS as usize);
        assert_eq!(full.points.first().unwrap().row, 0);
        assert_eq!(full.points.last().unwrap().row, rows.len() as u64 - 1);
        assert_eq!(full.source_rows, rows.len() as u64);
        assert!(full.points.windows(2).all(|pair| pair[0].row < pair[1].row));
        assert!(full
            .points
            .iter()
            .all(|point| rows[point.row as usize] == (point.x, point.y)));

        let bounded = store.overview(37).unwrap();
        assert_eq!(bounded.points.len(), 37);
        assert_eq!(bounded.points.first(), full.points.first());
        assert_eq!(bounded.points.last(), full.points.last());
        assert_eq!(bounded.available as usize, full.points.len());
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn overview_omits_all_nonfinite_windows_without_rejecting_valid_chunks() {
        let p = path("overview-sparse.xygc");
        let rows = [(0.0, 0.0), (f64::NAN, f64::NAN), (2.0, 2.0)];
        ChunkedColumns::create(&p, rows, 3).unwrap();
        let store = ChunkedColumns::open(&p).unwrap();
        let overview = store.overview(10).unwrap();
        assert_eq!(overview.source_rows, 3);
        assert_eq!(overview.points.len(), 2);
        assert_eq!(overview.points[0].row, 0);
        assert_eq!(overview.points[1].row, 2);
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn overview_can_be_empty_when_chunk_bounds_are_finite_across_different_rows() {
        let p = path("overview-no-paired-finite.xygc");
        let rows = [(0.0, f64::NAN), (f64::NAN, 1.0)];
        ChunkedColumns::create(&p, rows, 2).unwrap();
        let store = ChunkedColumns::open(&p).unwrap();
        let overview = store.overview(10).unwrap();
        assert_eq!(overview.source_rows, 2);
        assert_eq!(overview.available, 0);
        assert!(overview.points.is_empty());
        let detail = store
            .read_range(-1.0, 1.0, None, 1024, 0, |_| true)
            .unwrap();
        assert!(detail.x.is_empty());
        assert!(detail.y.is_empty());
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn legacy_v1_artifact_opens_with_an_empty_overview() {
        let p = path("overview-v1.xygc");
        let mut file = File::create(&p).unwrap();
        let mut header = [0u8; HEADER_BYTES as usize];
        header[0..4].copy_from_slice(MAGIC);
        header[4..8].copy_from_slice(&LEGACY_VERSION.to_le_bytes());
        header[8..16].copy_from_slice(&2u64.to_le_bytes());
        header[16..20].copy_from_slice(&2u32.to_le_bytes());
        header[20..24].copy_from_slice(&1u32.to_le_bytes());
        header[24..32].copy_from_slice(&(HEADER_BYTES + META_BYTES).to_le_bytes());
        file.write_all(&header).unwrap();
        file.write_all(&0u64.to_le_bytes()).unwrap();
        file.write_all(&2u32.to_le_bytes()).unwrap();
        file.write_all(&0u32.to_le_bytes()).unwrap();
        for bound in [0.0f64, 1.0, 2.0, 3.0] {
            file.write_all(&bound.to_le_bytes()).unwrap();
        }
        for value in [0.0f64, 2.0, 1.0, 3.0] {
            file.write_all(&value.to_le_bytes()).unwrap();
        }
        file.sync_all().unwrap();
        let store = ChunkedColumns::open(&p).unwrap();
        assert_eq!(store.rows(), 2);
        assert!(store.overview(10).unwrap().points.is_empty());
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn budget_cancel_and_corruption_fail_closed() {
        let p = path("failure.xygc");
        ChunkedColumns::create(&p, (0..20).map(|i| (i as f64, i as f64)), 5).unwrap();
        let store = ChunkedColumns::open(&p).unwrap();
        assert!(matches!(
            store.read_range(0.0, 9.0, None, 1, 1, |_| true),
            Err(Error::BudgetExceeded { .. })
        ));
        assert!(matches!(
            store.read_range(0.0, 9.0, None, 1000, 1, |_| false),
            Err(Error::Cancelled)
        ));
        let mut bytes = std::fs::read(&p).unwrap();
        bytes[0] = b'!';
        std::fs::write(&p, bytes).unwrap();
        assert!(matches!(
            ChunkedColumns::open(&p),
            Err(Error::Corrupt("bad magic"))
        ));
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn cancellation_watermark_never_moves_backwards() {
        let p = path("generation.xygc");
        ChunkedColumns::create(&p, (0..10).map(|i| (i as f64, i as f64)), 5).unwrap();
        let registered = Registered {
            store: ChunkedColumns::open(&p).unwrap(),
            current_generation: AtomicU64::new(0),
        };
        registered.set_generation(9);
        registered.set_generation(4);
        assert!(matches!(
            registered.read(0.0, 9.0, None, 1 << 20, 4),
            Err(Error::Cancelled)
        ));
        assert!(registered.read(0.0, 9.0, None, 1 << 20, 9).is_ok());
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn nonfinite_or_reserved_metadata_is_corrupt() {
        let p = path("metadata.xygc");
        ChunkedColumns::create(&p, (0..5).map(|i| (i as f64, i as f64)), 5).unwrap();
        let original = std::fs::read(&p).unwrap();

        let mut bytes = original.clone();
        bytes[64 + 16..64 + 24].copy_from_slice(&f64::NAN.to_le_bytes());
        std::fs::write(&p, &bytes).unwrap();
        assert!(matches!(ChunkedColumns::open(&p), Err(Error::Corrupt(_))));

        let mut bytes = original;
        bytes[64 + 12] = 1;
        std::fs::write(&p, &bytes).unwrap();
        assert!(matches!(ChunkedColumns::open(&p), Err(Error::Corrupt(_))));

        let mut bytes = std::fs::read(&p).unwrap();
        bytes[64 + 12] = 0;
        bytes[40..44].copy_from_slice(&u32::MAX.to_le_bytes());
        std::fs::write(&p, &bytes).unwrap();
        assert!(matches!(
            ChunkedColumns::open(&p),
            Err(Error::Corrupt("invalid overview count"))
        ));
        std::fs::remove_file(p).unwrap();
    }

    #[test]
    fn creation_rejects_nonfinite_bounds_and_a_lying_exact_size_iterator() {
        let p = path("create-invalid.xygc");
        assert!(matches!(
            ChunkedColumns::create(&p, [(f64::NAN, f64::NAN)], 1),
            Err(Error::Corrupt("chunk has no finite x/y bounds"))
        ));

        struct Lying {
            rows: std::vec::IntoIter<(f64, f64)>,
        }
        impl Iterator for Lying {
            type Item = (f64, f64);
            fn next(&mut self) -> Option<Self::Item> {
                self.rows.next()
            }
            fn size_hint(&self) -> (usize, Option<usize>) {
                (2, Some(2))
            }
        }
        impl ExactSizeIterator for Lying {}
        let rows = Lying {
            rows: vec![(0.0, 0.0)].into_iter(),
        };
        assert!(matches!(
            ChunkedColumns::create(&p, rows, 1),
            Err(Error::Corrupt("iterator length changed during creation"))
        ));
        std::fs::remove_file(p).unwrap();
    }

    #[cfg(target_pointer_width = "64")]
    #[test]
    fn creation_rejects_declared_file_size_overflow_before_creating_a_file() {
        struct Oversized;
        impl Iterator for Oversized {
            type Item = (f64, f64);
            fn next(&mut self) -> Option<Self::Item> {
                None
            }
            fn size_hint(&self) -> (usize, Option<usize>) {
                let rows = (u64::from(u32::MAX) * u64::from(u32::MAX)) as usize;
                (rows, Some(rows))
            }
        }
        impl ExactSizeIterator for Oversized {}

        let p = path("create-overflow.xygc");
        assert!(matches!(
            ChunkedColumns::create(&p, Oversized, u32::MAX),
            Err(Error::Corrupt("size overflow"))
        ));
        assert!(!p.exists());
    }
}
