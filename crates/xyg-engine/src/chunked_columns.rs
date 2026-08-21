//! Range-readable canonical f64 columns for ordered Tier-3 traces.
//!
//! Rust owns validation, zone-map selection, budgets, cancellation and the
//! provenance returned to hosts.  The on-disk format is deliberately small:
//! a fixed header, checked per-chunk metadata, then paired `(x, y)` f64 rows.
//! Hosts only open a local artifact and request a viewport (§5/§22/§28).

use std::fs::File;
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

const MAGIC: &[u8; 4] = b"XYGC";
const VERSION: u32 = 1;
const HEADER_BYTES: u64 = 64;
const META_BYTES: u64 = 48;
const ROW_BYTES: u64 = 16;

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
pub struct RangeRead {
    pub x: Vec<f64>,
    pub y: Vec<f64>,
    pub generation: u64,
    pub first_chunk: u32,
    pub chunks_considered: u32,
    pub chunks_read: u32,
    pub bytes_read: u64,
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

pub struct ChunkedColumns {
    file: File,
    rows: u64,
    chunk_rows: u32,
    metadata: Vec<ChunkMeta>,
    data_offset: u64,
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
        let mut file = File::create(path)?;
        file.set_len(data_offset)?;
        file.seek(SeekFrom::Start(data_offset))?;
        let mut metadata = Vec::with_capacity(chunk_count as usize);
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
            if current.len() == chunk_rows as usize {
                write_chunk(&mut file, &mut metadata, row_start, &current)?;
                row_start += current.len() as u64;
                current.clear();
            }
        }
        if !current.is_empty() {
            write_chunk(&mut file, &mut metadata, row_start, &current)?;
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
        if u32::from_le_bytes(header[4..8].try_into().unwrap()) != VERSION {
            return Err(Error::Corrupt("unsupported version"));
        }
        if header[32..].iter().any(|&byte| byte != 0) {
            return Err(Error::Corrupt("nonzero reserved header bytes"));
        }
        let rows = u64::from_le_bytes(header[8..16].try_into().unwrap());
        let chunk_rows = u32::from_le_bytes(header[16..20].try_into().unwrap());
        let chunk_count = u32::from_le_bytes(header[20..24].try_into().unwrap());
        let data_offset = u64::from_le_bytes(header[24..32].try_into().unwrap());
        if chunk_rows == 0 || data_offset != HEADER_BYTES + META_BYTES * u64::from(chunk_count) {
            return Err(Error::Corrupt("inconsistent header"));
        }
        let expected = data_offset
            .checked_add(
                rows.checked_mul(ROW_BYTES)
                    .ok_or(Error::Corrupt("size overflow"))?,
            )
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
        Ok(Self {
            file,
            rows,
            chunk_rows,
            metadata,
            data_offset,
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
            generation,
            first_chunk: first as u32,
            chunks_considered: candidates.len() as u32,
            chunks_read: 0,
            bytes_read: 0,
        };
        for (_, meta) in selected {
            if !is_current(generation) {
                return Err(Error::Cancelled);
            }
            let bytes = u64::from(meta.row_count) * ROW_BYTES;
            let mut raw = vec![0u8; bytes as usize];
            read_exact_at(
                &self.file,
                &mut raw,
                self.data_offset + meta.row_start * ROW_BYTES,
            )?;
            out.chunks_read += 1;
            out.bytes_read += bytes;
            for row in raw.chunks_exact(16) {
                let x = f64::from_le_bytes(row[0..8].try_into().unwrap());
                let yy = f64::from_le_bytes(row[8..16].try_into().unwrap());
                if x.is_finite()
                    && yy.is_finite()
                    && x >= x0
                    && x <= x1
                    && y.is_none_or(|(a, b)| yy >= a && yy <= b)
                {
                    out.x.push(x);
                    out.y.push(yy);
                }
            }
        }
        Ok(out)
    }
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
}
