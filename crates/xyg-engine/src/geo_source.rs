//! Host-neutral retained geographic chunks. Dossier §27/§28; see geo-retained-source.md.
//! Zone maps are conservative candidates, never geographic visibility or LOD decisions.
use crate::geo::{column_from_descriptor_bytes, GeoColumn, GeoCrs, GeoError, GeoGeometry};
use crate::transition::Blake2s8;
use std::ops::Range;

pub const MAX_SOURCE_ROWS: u64 = 1_000_000_000;
pub const MAX_CHUNKS: usize = 65_536;
pub const MAX_CHUNK_ROWS: usize = 65_536;
pub const MAX_CHUNK_BYTES: usize = 16 * 1024 * 1024;
pub const MAX_MANIFEST_BYTES: usize = 32 * 1024 * 1024;
pub const MAX_CHUNK_PEAK: usize = 96 * 1024 * 1024;
pub const MAX_PROCESSOR_BYTES: usize = 128 * 1024 * 1024;
pub const MAX_PAGE_ROWS: usize = 4096;
const HEADER: usize = 64;
const ENTRY: usize = 128;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SourceError {
    InvalidFrame,
    Geometry(GeoError),
    InvalidTime,
    ResourceLimit,
    Cancelled,
    StaleSource,
    Reader,
}
impl From<GeoError> for SourceError {
    fn from(e: GeoError) -> Self {
        Self::Geometry(e)
    }
}
impl SourceError {
    pub const fn code(self) -> &'static str {
        match self {
            Self::InvalidFrame => "XYG_GEO_SOURCE_INVALID_FRAME",
            Self::Geometry(e) => e.code(),
            Self::InvalidTime => "XYG_GEO_SOURCE_INVALID_TIME",
            Self::ResourceLimit => "XYG_GEO_SOURCE_RESOURCE_LIMIT",
            Self::Cancelled => "XYG_GEO_SOURCE_CANCELLED",
            Self::StaleSource => "XYG_GEO_SOURCE_STALE",
            Self::Reader => "XYG_GEO_SOURCE_READER",
        }
    }
}
type Result<T> = std::result::Result<T, SourceError>;
fn add(a: usize, b: usize) -> Result<usize> {
    a.checked_add(b).ok_or(SourceError::ResourceLimit)
}
fn add64(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b).ok_or(SourceError::ResourceLimit)
}
fn mul(a: usize, b: usize) -> Result<usize> {
    a.checked_mul(b).ok_or(SourceError::ResourceLimit)
}
fn geometric_bytes(
    kind: GeoGeometry,
    rows: usize,
    vertices: usize,
    offsets: [usize; 3],
) -> Result<usize> {
    let mut size = add(mul(rows, 9)?, mul(vertices, 16)?)?;
    for count in offsets {
        size = add(size, mul(count, 4)?)?;
    }
    let rings = match kind {
        GeoGeometry::Polygon => offsets[1].saturating_sub(1),
        GeoGeometry::MultiPolygon => offsets[2].saturating_sub(1),
        _ => 0,
    };
    add(size, rings)
}
fn pad(n: usize) -> Result<usize> {
    Ok(add(n, 7)? & !7)
}
fn u32at(b: &[u8], i: usize) -> u32 {
    u32::from_le_bytes(b[i..i + 4].try_into().unwrap())
}
fn u64at(b: &[u8], i: usize) -> u64 {
    u64::from_le_bytes(b[i..i + 8].try_into().unwrap())
}
fn i64at(b: &[u8], i: usize) -> i64 {
    i64::from_le_bytes(b[i..i + 8].try_into().unwrap())
}
fn f64at(b: &[u8], i: usize) -> f64 {
    f64::from_le_bytes(b[i..i + 8].try_into().unwrap())
}
fn put32(b: &mut [u8], i: usize, n: u32) {
    b[i..i + 4].copy_from_slice(&n.to_le_bytes());
}
fn put64(b: &mut [u8], i: usize, n: u64) {
    b[i..i + 8].copy_from_slice(&n.to_le_bytes());
}
fn hash(domain: &[u8], b: &[u8]) -> [u8; 8] {
    let mut h = Blake2s8::new();
    h.update(domain);
    h.update(b);
    h.finish()
}
fn check_cancel(cancel: &mut impl FnMut() -> bool) -> Result<()> {
    if cancel() {
        Err(SourceError::Cancelled)
    } else {
        Ok(())
    }
}

/// Coordinates are canonical CRS units. Dateline-crossing boxes use two separate queries,
/// or a full-world box; min_x must not exceed max_x.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SourceBounds {
    pub min_x: f64,
    pub min_y: f64,
    pub max_x: f64,
    pub max_y: f64,
}
impl SourceBounds {
    fn valid(self) -> bool {
        [self.min_x, self.min_y, self.max_x, self.max_y]
            .into_iter()
            .all(f64::is_finite)
            && self.min_x <= self.max_x
            && self.min_y <= self.max_y
    }
    fn intersects(self, b: Self) -> bool {
        self.min_x <= b.max_x
            && b.min_x <= self.max_x
            && self.min_y <= b.max_y
            && b.min_y <= self.max_y
    }
    fn include(&mut self, b: Self) {
        self.min_x = self.min_x.min(b.min_x);
        self.max_x = self.max_x.max(b.max_x);
        self.min_y = self.min_y.min(b.min_y);
        self.max_y = self.max_y.max(b.max_y);
    }
    fn conservative(mut self, crs: GeoCrs) -> Self {
        let half = if crs == GeoCrs::Epsg4326 {
            180.
        } else {
            20_037_508.342_789_244
        };
        if self.max_x - self.min_x > half {
            self.min_x = -half;
            self.max_x = half;
        }
        self
    }
}

/// Signed UTC microseconds. Null endpoints are unbounded; valid endpoints require start < end.
#[derive(Clone, Copy)]
pub struct GeoIntervals<'a> {
    pub starts: &'a [i64],
    pub ends: &'a [i64],
    pub start_validity: &'a [u8],
    pub end_validity: &'a [u8],
}
struct OwnedIntervals {
    starts: Vec<i64>,
    ends: Vec<i64>,
    start_validity: Vec<u8>,
    end_validity: Vec<u8>,
}
impl OwnedIntervals {
    fn borrowed(&self) -> GeoIntervals<'_> {
        GeoIntervals {
            starts: &self.starts,
            ends: &self.ends,
            start_validity: &self.start_validity,
            end_validity: &self.end_validity,
        }
    }
}
fn validate_intervals(t: GeoIntervals<'_>, n: usize) -> Result<()> {
    if [
        t.starts.len(),
        t.ends.len(),
        t.start_validity.len(),
        t.end_validity.len(),
    ]
    .into_iter()
    .any(|x| x != n)
    {
        return Err(SourceError::InvalidTime);
    }
    for i in 0..n {
        let (s, e) = (t.start_validity[i], t.end_validity[i]);
        if s > 1 || e > 1 || (s == 1 && e == 1 && t.starts[i] >= t.ends[i]) {
            return Err(SourceError::InvalidTime);
        }
    }
    Ok(())
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TimePredicate {
    All,
    Instant(i64),
    Window { start: i64, end: i64 },
}
impl TimePredicate {
    pub fn validate(self) -> Result<()> {
        if matches!(self,Self::Window{start,end} if start>=end) {
            Err(SourceError::InvalidTime)
        } else {
            Ok(())
        }
    }
    pub fn matches(self, start: Option<i64>, end: Option<i64>) -> bool {
        match self {
            Self::All => true,
            Self::Instant(t) => start.is_none_or(|s| s <= t) && end.is_none_or(|e| t < e),
            Self::Window { start: s, end: e } => {
                start.is_none_or(|a| a < e) && end.is_none_or(|b| s < b)
            }
        }
    }
}

/// Immutable, independently validated canonical chunk. No full-source geometry is retained.
pub struct GeoChunk {
    column: GeoColumn,
    time: Option<OwnedIntervals>,
    values: Option<Vec<f64>>,
    encoded_bytes: usize,
    digest: [u8; 8],
}
impl GeoChunk {
    pub fn column(&self) -> &GeoColumn {
        &self.column
    }
    pub fn intervals(&self) -> Option<GeoIntervals<'_>> {
        self.time.as_ref().map(OwnedIntervals::borrowed)
    }
    pub fn digest(&self) -> [u8; 8] {
        self.digest
    }
    /// Canonical writer: explicit full-u64 IDs, original geometry order and f64 bit patterns.
    pub fn encode(column: &GeoColumn, time: Option<GeoIntervals<'_>>) -> Result<Vec<u8>> {
        Self::encode_with_values(column, time, None)
    }
    pub fn values(&self) -> Option<&[f64]> {
        self.values.as_deref()
    }
    /// Optional canonical scalar values are retained bitwise, including NaN/Inf.
    /// Layer compilation owns scalar-domain/missing-value semantics, not this source.
    pub fn encode_with_values(
        column: &GeoColumn,
        time: Option<GeoIntervals<'_>>,
        values: Option<&[f64]>,
    ) -> Result<Vec<u8>> {
        let n = column.len();
        if values.is_some_and(|v| v.len() != n) {
            return Err(SourceError::InvalidFrame);
        }
        if n > MAX_CHUNK_ROWS || column.vertex_count() > 524_288 {
            return Err(SourceError::ResourceLimit);
        }
        if let Some(t) = time {
            validate_intervals(t, n)?;
        }
        if geometric_bytes(
            column.geometry(),
            n,
            column.vertex_count(),
            [
                column.offsets0().len(),
                column.offsets1().len(),
                column.offsets2().len(),
            ],
        )? > MAX_CHUNK_BYTES
        {
            return Err(SourceError::ResourceLimit);
        }
        let sizes = [
            mul(column.xy().len(), 8)?,
            n,
            mul(n, 8)?,
            mul(column.offsets0().len(), 4)?,
            mul(column.offsets1().len(), 4)?,
            mul(column.offsets2().len(), 4)?,
        ];
        let gd_len = sizes.into_iter().try_fold(HEADER, |a, b| add(a, pad(b)?))?;
        let time_len = if time.is_some() {
            add(mul(n, 16)?, mul(pad(n)?, 2)?)?
        } else {
            0
        };
        let len = add(
            add(add(HEADER, gd_len)?, time_len)?,
            if values.is_some() { mul(n, 8)? } else { 0 },
        )?;
        if len > MAX_CHUNK_BYTES {
            return Err(SourceError::ResourceLimit);
        }
        let mut b = vec![0; len];
        b[..4].copy_from_slice(b"XYGK");
        put32(&mut b, 4, 1);
        put32(
            &mut b,
            8,
            u32::from(time.is_some()) | u32::from(values.is_some()) << 1,
        );
        put64(&mut b, 16, gd_len as u64);
        put64(&mut b, 24, n as u64);
        let at = HEADER;
        b[at..at + 4].copy_from_slice(b"XYGD");
        put32(&mut b, at + 4, 1);
        put32(&mut b, at + 8, column.geometry() as u32);
        put32(&mut b, at + 12, column.crs() as u32);
        put32(&mut b, at + 16, 1);
        for (i, v) in [
            n,
            column.vertex_count(),
            column.offsets0().len(),
            column.offsets1().len(),
            column.offsets2().len(),
        ]
        .into_iter()
        .enumerate()
        {
            put64(&mut b, at + 24 + i * 8, v as u64);
        }
        let mut cursor = at + HEADER;
        for v in column.xy() {
            put64(&mut b, cursor, v.to_bits());
            cursor += 8
        }
        cursor = pad(cursor)?;
        b[cursor..cursor + n].copy_from_slice(column.validity());
        cursor = pad(cursor + n)?;
        for v in column.feature_ids() {
            put64(&mut b, cursor, *v);
            cursor += 8
        }
        cursor = pad(cursor)?;
        for plane in [column.offsets0(), column.offsets1(), column.offsets2()] {
            for v in plane {
                put32(&mut b, cursor, *v);
                cursor += 4
            }
            cursor = pad(cursor)?;
        }
        if let Some(t) = time {
            for (values, valid) in [(t.starts, t.start_validity), (t.ends, t.end_validity)] {
                for (i, v) in values.iter().enumerate() {
                    put64(&mut b, cursor, if valid[i] == 1 { *v as u64 } else { 0 });
                    cursor += 8
                }
            }
            for valid in [t.start_validity, t.end_validity] {
                b[cursor..cursor + n].copy_from_slice(valid);
                cursor = pad(cursor + n)?;
            }
        }
        if let Some(values) = values {
            for value in values {
                put64(&mut b, cursor, value.to_bits());
                cursor += 8;
            }
        }
        debug_assert_eq!(cursor, len);
        Ok(b)
    }
    pub fn parse(b: &[u8], peak_budget: usize) -> Result<Self> {
        if b.len() > MAX_CHUNK_BYTES || peak_budget > MAX_CHUNK_PEAK {
            return Err(SourceError::ResourceLimit);
        }
        if b.len() < 128
            || &b[..4] != b"XYGK"
            || u32at(b, 4) != 1
            || u32at(b, 8) > 3
            || b[12..16].iter().chain(&b[32..64]).any(|x| *x != 0)
        {
            return Err(SourceError::InvalidFrame);
        }
        let gd_len = usize::try_from(u64at(b, 16)).map_err(|_| SourceError::ResourceLimit)?;
        let n = usize::try_from(u64at(b, 24)).map_err(|_| SourceError::ResourceLimit)?;
        if n > MAX_CHUNK_ROWS {
            return Err(SourceError::ResourceLimit);
        }
        let end = add(HEADER, gd_len)?;
        if gd_len < 64 || end > b.len() {
            return Err(SourceError::InvalidFrame);
        }
        let gd = &b[HEADER..end];
        if &gd[..4] != b"XYGD" || u64at(gd, 24) != n as u64 || u32at(gd, 16) != 1 {
            return Err(SourceError::InvalidFrame);
        }
        // Strict chunk limits before the shared descriptor parser can allocate typed planes.
        let vertices = u64at(gd, 32);
        if vertices > 524_288 {
            return Err(SourceError::ResourceLimit);
        }
        let kind = GeoGeometry::from_u32(u32at(gd, 8))
            .ok_or(SourceError::Geometry(GeoError::TypeMismatch))?;
        let mut offsets = [0; 3];
        for (slot, at) in [40, 48, 56].into_iter().enumerate() {
            offsets[slot] =
                usize::try_from(u64at(gd, at)).map_err(|_| SourceError::ResourceLimit)?;
        }
        if geometric_bytes(kind, n, vertices as usize, offsets)? > MAX_CHUNK_BYTES {
            return Err(SourceError::ResourceLimit);
        }
        let temporal = u32at(b, 8) & 1 != 0;
        let has_values = u32at(b, 8) & 2 != 0;
        let values_len = if has_values { mul(n, 8)? } else { 0 };
        let time_len = if temporal {
            add(mul(n, 16)?, mul(pad(n)?, 2)?)?
        } else {
            0
        };
        if add(add(end, time_len)?, values_len)? != b.len() {
            return Err(SourceError::InvalidFrame);
        }
        let time_peak = mul(add(time_len, values_len)?, 2)?;
        let column_budget = peak_budget
            .checked_sub(add(time_peak, 4096)?)
            .ok_or(SourceError::ResourceLimit)?;
        // Validate optional temporal framing/endpoints before allocating the GeoColumn.
        if temporal {
            let starts = end;
            let ends = end + n * 8;
            let sv = end + n * 16;
            let ev = sv + pad(n)?;
            if b[sv + n..ev].iter().any(|v| *v != 0)
                || b[ev + n..end + time_len].iter().any(|v| *v != 0)
            {
                return Err(SourceError::InvalidFrame);
            }
            for row in 0..n {
                let (vs, ve) = (b[sv + row], b[ev + row]);
                let (start, stop) = (i64at(b, starts + row * 8), i64at(b, ends + row * 8));
                if vs > 1 || ve > 1 || (vs == 1 && ve == 1 && start >= stop) {
                    return Err(SourceError::InvalidTime);
                }
                if (vs == 0 && start != 0) || (ve == 0 && stop != 0) {
                    return Err(SourceError::InvalidFrame);
                }
            }
        }
        let column = column_from_descriptor_bytes(gd, column_budget)?;
        let time = if temporal {
            let mut cursor = end;
            let starts: Vec<i64> = (0..n).map(|i| i64at(b, cursor + i * 8)).collect();
            cursor += n * 8;
            let ends: Vec<i64> = (0..n).map(|i| i64at(b, cursor + i * 8)).collect();
            cursor += n * 8;
            let start_validity = b[cursor..cursor + n].to_vec();
            if b[cursor + n..pad(cursor + n)?].iter().any(|v| *v != 0) {
                return Err(SourceError::InvalidFrame);
            }
            cursor = pad(cursor + n)?;
            let end_validity = b[cursor..cursor + n].to_vec();
            if b[cursor + n..end + time_len].iter().any(|v| *v != 0) {
                return Err(SourceError::InvalidFrame);
            }
            let t = OwnedIntervals {
                starts,
                ends,
                start_validity,
                end_validity,
            };
            validate_intervals(t.borrowed(), n)?;
            for i in 0..n {
                if (t.start_validity[i] == 0 && t.starts[i] != 0)
                    || (t.end_validity[i] == 0 && t.ends[i] != 0)
                {
                    return Err(SourceError::InvalidFrame);
                }
            }
            Some(t)
        } else {
            None
        };
        let values = if has_values {
            Some((0..n).map(|i| f64at(b, end + time_len + i * 8)).collect())
        } else {
            None
        };
        Ok(Self {
            column,
            time,
            values,
            encoded_bytes: b.len(),
            digest: hash(b"xyg-geo-chunk-v1", b),
        })
    }
    pub fn rows(&self) -> FeatureRows<'_> {
        FeatureRows {
            chunk: self,
            row: 0,
            point_vertex: 0,
            include_null: false,
        }
    }
    /// Every original source row, including null geometry; no viewport or time filtering.
    pub fn all_rows(&self) -> FeatureRows<'_> {
        FeatureRows {
            chunk: self,
            row: 0,
            point_vertex: 0,
            include_null: true,
        }
    }
}

/// Borrowed canonical topology: the complete column is retained only for this bounded chunk.
#[derive(Clone)]
pub struct FeatureView<'a> {
    pub column: &'a GeoColumn,
    pub row: usize,
    pub vertices: Range<usize>,
    pub interval_start: Option<i64>,
    pub interval_end: Option<i64>,
    pub value: Option<f64>,
}
impl FeatureView<'_> {
    pub fn bounds(&self) -> Option<SourceBounds> {
        let mut b = None;
        for xy in self.column.xy()[self.vertices.start * 2..self.vertices.end * 2].chunks_exact(2) {
            let p = SourceBounds {
                min_x: xy[0],
                max_x: xy[0],
                min_y: xy[1],
                max_y: xy[1],
            };
            if let Some(v) = &mut b {
                SourceBounds::include(v, p)
            } else {
                b = Some(p)
            }
        }
        b.map(|v| v.conservative(self.column.crs()))
    }
    /// Always evaluates time first, before reading geometry for spatial candidate filtering.
    pub fn matches(&self, q: QuerySpec) -> bool {
        q.time.matches(self.interval_start, self.interval_end)
            && q.bounds
                .is_none_or(|b| self.bounds().is_some_and(|v| v.intersects(b)))
    }
}
pub struct FeatureRows<'a> {
    chunk: &'a GeoChunk,
    row: usize,
    point_vertex: usize,
    include_null: bool,
}
impl<'a> Iterator for FeatureRows<'a> {
    type Item = FeatureView<'a>;
    fn next(&mut self) -> Option<Self::Item> {
        let c = &self.chunk.column;
        while self.row < c.len() {
            let row = self.row;
            self.row += 1;
            let valid = c.validity()[row] == 1;
            let vertices = match c.geometry() {
                GeoGeometry::Point => {
                    let v = self.point_vertex;
                    self.point_vertex += usize::from(valid);
                    v..self.point_vertex
                }
                GeoGeometry::LineString | GeoGeometry::MultiPoint => {
                    c.offsets0()[row] as usize..c.offsets0()[row + 1] as usize
                }
                GeoGeometry::Polygon | GeoGeometry::MultiLineString => {
                    let a = c.offsets0()[row] as usize;
                    let z = c.offsets0()[row + 1] as usize;
                    c.offsets1()[a] as usize..c.offsets1()[z] as usize
                }
                GeoGeometry::MultiPolygon => {
                    let a = c.offsets1()[c.offsets0()[row] as usize] as usize;
                    let z = c.offsets1()[c.offsets0()[row + 1] as usize] as usize;
                    c.offsets2()[a] as usize..c.offsets2()[z] as usize
                }
            };
            if !valid && !self.include_null {
                continue;
            }
            let (start, end) = self.chunk.intervals().map_or((None, None), |t| {
                (
                    if t.start_validity[row] == 1 {
                        Some(t.starts[row])
                    } else {
                        None
                    },
                    if t.end_validity[row] == 1 {
                        Some(t.ends[row])
                    } else {
                        None
                    },
                )
            });
            return Some(FeatureView {
                column: c,
                row,
                vertices,
                interval_start: start,
                interval_end: end,
                value: self.chunk.values.as_ref().map(|values| values[row]),
            });
        }
        None
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ChunkSummary {
    pub first_row: u64,
    pub rows: u32,
    pub encoded_bytes: u32,
    pub digest: [u8; 8],
    pub bounds: Option<SourceBounds>,
    pub has_time: bool,
    pub time_start: Option<i64>,
    pub time_end: Option<i64>,
}
fn summarize(c: &GeoChunk, first_row: u64) -> ChunkSummary {
    let mut bounds = None;
    let mut start = None;
    let mut end = None;
    let mut start_unbounded = false;
    let mut end_unbounded = false;
    for f in c.rows() {
        if let Some(b) = f.bounds() {
            if let Some(v) = &mut bounds {
                SourceBounds::include(v, b)
            } else {
                bounds = Some(b)
            }
        }
        match f.interval_start {
            Some(s) => start = Some(start.map_or(s, |v: i64| v.min(s))),
            None => start_unbounded = true,
        }
        match f.interval_end {
            Some(e) => end = Some(end.map_or(e, |v: i64| v.max(e))),
            None => end_unbounded = true,
        }
    }
    ChunkSummary {
        first_row,
        rows: c.column.len() as u32,
        encoded_bytes: c.encoded_bytes as u32,
        digest: c.digest,
        bounds: bounds.map(|b| b.conservative(c.column.crs())),
        has_time: c.time.is_some(),
        time_start: if start_unbounded { None } else { start },
        time_end: if end_unbounded { None } else { end },
    }
}
fn write_summary(b: &mut [u8], at: usize, c: &ChunkSummary) {
    put64(b, at, c.first_row);
    put32(b, at + 8, c.rows);
    put32(b, at + 12, c.encoded_bytes);
    b[at + 16..at + 24].copy_from_slice(&c.digest);
    let flags = u32::from(c.bounds.is_some())
        | u32::from(c.has_time) << 1
        | u32::from(c.time_start.is_some()) << 2
        | u32::from(c.time_end.is_some()) << 3;
    put32(b, at + 24, flags);
    if let Some(v) = c.bounds {
        for (j, x) in [v.min_x, v.min_y, v.max_x, v.max_y].into_iter().enumerate() {
            put64(b, at + 32 + j * 8, x.to_bits())
        }
    }
    if let Some(v) = c.time_start {
        put64(b, at + 64, v as u64)
    }
    if let Some(v) = c.time_end {
        put64(b, at + 72, v as u64)
    }
}
fn summary_matches(c: &ChunkSummary, q: QuerySpec) -> bool {
    q.time.matches(c.time_start, c.time_end)
        && q.bounds
            .is_none_or(|b| c.bounds.is_some_and(|v| v.intersects(b)))
}
/// Persisted framing has no trusted pruning capability until all chunks are accepted.
pub struct UntrustedGeoManifest {
    bytes: Vec<u8>,
    count: usize,
    generation: u64,
    rows: u64,
}
impl UntrustedGeoManifest {
    /// Allocation-free complete metadata validation-phase admission.
    pub fn preflight_reserved_bytes(bytes: &[u8]) -> Result<usize> {
        let (count, _, _) = manifest_frame(bytes)?;
        add(
            add(mul(bytes.len(), 2)?, std::mem::size_of::<Self>())?,
            add(
                mul(count.max(4), mul(3, std::mem::size_of::<ChunkSummary>())?)?,
                8192,
            )?,
        )
    }
    pub fn from_bytes(bytes: &[u8], processor_bytes: usize) -> Result<Self> {
        let (count, generation, rows) = manifest_frame(bytes)?;
        if processor_bytes > MAX_PROCESSOR_BYTES
            || Self::preflight_reserved_bytes(bytes)? > processor_bytes
        {
            return Err(SourceError::ResourceLimit);
        }
        Ok(Self {
            bytes: bytes.to_vec(),
            count,
            generation,
            rows,
        })
    }
    pub fn chunk_count(&self) -> usize {
        self.count
    }
    pub fn rows(&self) -> u64 {
        self.rows
    }
    pub fn generation(&self) -> u64 {
        self.generation
    }
    pub fn metadata_bytes(&self) -> usize {
        self.bytes.capacity() + std::mem::size_of::<Self>()
    }
    pub fn validation_reserved_bytes(&self) -> Result<usize> {
        add(
            add(self.metadata_bytes(), self.bytes.len())?,
            add(
                mul(
                    self.count.max(4),
                    mul(3, std::mem::size_of::<ChunkSummary>())?,
                )?,
                8192,
            )?,
        )
    }
    pub fn read_request(&self, index: usize) -> Result<ReadRequest> {
        if index >= self.count {
            return Err(SourceError::InvalidFrame);
        }
        let at = HEADER + index * ENTRY;
        let bytes = &self.bytes;
        Ok(ReadRequest {
            generation: self.generation,
            chunk_index: index as u32,
            first_row: u64at(bytes, at),
            rows: u32at(bytes, at + 8),
            encoded_bytes: u32at(bytes, at + 12) as usize,
            digest: bytes[at + 16..at + 24].try_into().unwrap(),
        })
    }
    pub fn accept_chunk(
        &self,
        index: usize,
        chunk: &GeoChunk,
        builder: &mut GeoManifestBuilder,
    ) -> Result<()> {
        if index != builder.chunks.len() {
            return Err(SourceError::InvalidFrame);
        }
        let req = self.read_request(index)?;
        if req.digest != chunk.digest()
            || req.encoded_bytes != chunk.encoded_bytes
            || chunk.column.geometry() as u32 != u32at(&self.bytes, 8)
            || chunk.column.crs() as u32 != u32at(&self.bytes, 12)
        {
            return Err(SourceError::StaleSource);
        }
        let summary = summarize(chunk, req.first_row);
        let mut encoded = [0u8; ENTRY];
        write_summary(&mut encoded, 0, &summary);
        if encoded != self.bytes[HEADER + index * ENTRY..HEADER + (index + 1) * ENTRY] {
            return Err(SourceError::StaleSource);
        }
        builder.push(chunk)
    }
    pub fn finish(self, builder: GeoManifestBuilder) -> Result<GeoSourceManifest> {
        if builder.chunks.len() != self.count {
            return Err(SourceError::InvalidFrame);
        }
        let manifest = builder.finish(self.generation)?;
        if manifest.encode_inner()? != self.bytes {
            return Err(SourceError::StaleSource);
        }
        Ok(manifest)
    }
}
/// Authenticate one supplied bounded read without owning the host's byte buffer.
pub fn parse_authenticated(request: ReadRequest, bytes: &[u8], peak: usize) -> Result<GeoChunk> {
    if bytes.len() != request.encoded_bytes {
        return Err(SourceError::InvalidFrame);
    }
    if hash(b"xyg-geo-chunk-v1", bytes) != request.digest {
        return Err(SourceError::StaleSource);
    }
    GeoChunk::parse(bytes, peak)
}
/// Admission-only sizing, never evidence that a billion rows were ingested or rendered.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoSourcePlan {
    pub rows: u64,
    pub chunk_rows: u32,
    pub chunks: u32,
    pub manifest_bytes: usize,
    pub processor_bytes: usize,
}
impl GeoSourcePlan {
    pub fn new(rows: u64, chunk_rows: u32) -> Result<Self> {
        if rows == 0 || chunk_rows == 0 {
            return Err(SourceError::InvalidFrame);
        }
        if rows > MAX_SOURCE_ROWS || chunk_rows as usize > MAX_CHUNK_ROWS {
            return Err(SourceError::ResourceLimit);
        }
        let chunks = rows.div_ceil(chunk_rows as u64);
        if chunks > MAX_CHUNKS as u64 {
            return Err(SourceError::ResourceLimit);
        }
        let manifest_bytes = add(HEADER, mul(chunks as usize, ENTRY)?)?;
        Ok(Self {
            rows,
            chunk_rows,
            chunks: chunks as u32,
            manifest_bytes,
            processor_bytes: MAX_PROCESSOR_BYTES,
        })
    }
}
/// Only Rust-derived summaries enter this builder. Push drops no canonical geometry or IDs.
#[derive(Clone)]
pub struct GeoManifestBuilder {
    chunks: Vec<ChunkSummary>,
    rows: u64,
    geometry: Option<GeoGeometry>,
    crs: Option<GeoCrs>,
}
impl Default for GeoManifestBuilder {
    fn default() -> Self {
        Self::new()
    }
}
impl GeoManifestBuilder {
    pub fn new() -> Self {
        Self {
            chunks: Vec::new(),
            rows: 0,
            geometry: None,
            crs: None,
        }
    }
    pub fn push(&mut self, c: &GeoChunk) -> Result<()> {
        if self.chunks.len() >= MAX_CHUNKS || c.column.is_empty() {
            return Err(SourceError::ResourceLimit);
        }
        let rows = self
            .rows
            .checked_add(c.column.len() as u64)
            .ok_or(SourceError::ResourceLimit)?;
        if rows > MAX_SOURCE_ROWS {
            return Err(SourceError::ResourceLimit);
        }
        if self.geometry.is_some_and(|g| g != c.column.geometry())
            || self.crs.is_some_and(|g| g != c.column.crs())
        {
            return Err(SourceError::InvalidFrame);
        }
        if self.chunks.len() == self.chunks.capacity() {
            let target = self
                .chunks
                .capacity()
                .saturating_mul(2)
                .clamp(4, MAX_CHUNKS);
            let growth_peak = mul(
                add(self.chunks.capacity(), target)?,
                std::mem::size_of::<ChunkSummary>(),
            )?;
            if growth_peak > MAX_MANIFEST_BYTES {
                return Err(SourceError::ResourceLimit);
            }
            self.chunks
                .try_reserve_exact(target - self.chunks.len())
                .map_err(|_| SourceError::ResourceLimit)?;
            if mul(self.chunks.capacity(), std::mem::size_of::<ChunkSummary>())?
                > MAX_MANIFEST_BYTES
            {
                return Err(SourceError::ResourceLimit);
            }
        }
        let summary = summarize(c, self.rows);
        self.chunks.push(summary);
        self.rows = rows;
        self.geometry = Some(c.column.geometry());
        self.crs = Some(c.column.crs());
        Ok(())
    }
    pub fn finish(self, generation: u64) -> Result<GeoSourceManifest> {
        if generation == 0 || self.chunks.is_empty() {
            return Err(SourceError::InvalidFrame);
        }
        let mut m = GeoSourceManifest {
            chunks: self.chunks,
            rows: self.rows,
            generation,
            geometry: self.geometry.unwrap(),
            crs: self.crs.unwrap(),
            digest: [0; 8],
        };
        m.digest = hash(b"xyg-geo-manifest-v1", &m.encode_inner()?);
        Ok(m)
    }
}
/// Validated capability, with no public constructor from user-authored zone maps.
pub struct GeoSourceManifest {
    chunks: Vec<ChunkSummary>,
    rows: u64,
    generation: u64,
    geometry: GeoGeometry,
    crs: GeoCrs,
    digest: [u8; 8],
}
impl GeoSourceManifest {
    /// Caller acquires the shared processor lease before invoking clone_validated.
    pub(crate) fn clone_reserved_bytes(&self) -> usize {
        self.chunks.len() * std::mem::size_of::<ChunkSummary>() + std::mem::size_of::<Self>()
    }
    pub(crate) fn clone_validated(&self) -> Self {
        Self {
            chunks: self.chunks.clone(),
            rows: self.rows,
            generation: self.generation,
            geometry: self.geometry,
            crs: self.crs,
            digest: self.digest,
        }
    }
    pub fn rows(&self) -> u64 {
        self.rows
    }
    pub fn generation(&self) -> u64 {
        self.generation
    }
    pub fn digest(&self) -> [u8; 8] {
        self.digest
    }
    pub fn chunks(&self) -> &[ChunkSummary] {
        &self.chunks
    }
    pub fn crs(&self) -> GeoCrs {
        self.crs
    }
    pub fn geometry(&self) -> GeoGeometry {
        self.geometry
    }
    pub fn metadata_bytes(&self) -> usize {
        self.chunks.capacity() * std::mem::size_of::<ChunkSummary>() + std::mem::size_of::<Self>()
    }
    fn encode_inner(&self) -> Result<Vec<u8>> {
        let len = add(HEADER, mul(self.chunks.len(), ENTRY)?)?;
        if len > MAX_MANIFEST_BYTES {
            return Err(SourceError::ResourceLimit);
        }
        let mut b = vec![0; len];
        b[..4].copy_from_slice(b"XYGI");
        put32(&mut b, 4, 1);
        put32(&mut b, 8, self.geometry as u32);
        put32(&mut b, 12, self.crs as u32);
        put64(&mut b, 16, self.generation);
        put64(&mut b, 24, self.rows);
        put64(&mut b, 32, self.chunks.len() as u64);
        for (i, c) in self.chunks.iter().enumerate() {
            write_summary(&mut b, HEADER + i * ENTRY, c);
        }

        Ok(b)
    }
    pub fn encode(&self) -> Result<Vec<u8>> {
        self.encode_inner()
    }
    /// Validate every untrusted persisted summary against canonical bytes before pruning any chunk.
    pub fn validate<R: GeoChunkReader>(
        bytes: &[u8],
        reader: &mut R,
        cancel: &mut impl FnMut() -> bool,
    ) -> Result<Self> {
        Self::validate_with_budget(bytes, reader, cancel, QueryBudget::default())
    }
    /// Explicit full-source validation work/read admission, independent of resident memory.
    pub fn validate_with_budget<R: GeoChunkReader>(
        bytes: &[u8],
        reader: &mut R,
        cancel: &mut impl FnMut() -> bool,
        budget: QueryBudget,
    ) -> Result<Self> {
        budget.validate()?;
        let untrusted = UntrustedGeoManifest::from_bytes(bytes, budget.processor_bytes)?;
        let count = untrusted.chunk_count();
        if count > budget.max_chunks || untrusted.rows() > budget.max_rows_examined {
            return Err(SourceError::ResourceLimit);
        }
        let chunk_peak = budget
            .processor_bytes
            .checked_sub(add(untrusted.validation_reserved_bytes()?, bytes.len())?)
            .ok_or(SourceError::ResourceLimit)?
            .min(MAX_CHUNK_PEAK);
        let mut bytes_read = 0u64;
        let mut builder = GeoManifestBuilder::new();
        for i in 0..count {
            check_cancel(cancel)?;
            let req = untrusted.read_request(i)?;
            bytes_read = add64(bytes_read, req.encoded_bytes as u64)?;
            if bytes_read > budget.max_read_bytes {
                return Err(SourceError::ResourceLimit);
            }
            let raw = reader.read_chunk(req)?;
            check_cancel(cancel)?;
            check_read(&raw, req)?;
            let peak = chunk_peak
                .checked_sub(raw.capacity() - raw.len())
                .ok_or(SourceError::ResourceLimit)?;
            let chunk = GeoChunk::parse(&raw, peak)?;
            untrusted.accept_chunk(i, &chunk, &mut builder)?;
        }
        untrusted.finish(builder)
    }
    pub fn read_request(&self, index: usize) -> Result<ReadRequest> {
        let c = self.chunks.get(index).ok_or(SourceError::InvalidFrame)?;
        Ok(ReadRequest {
            generation: self.generation,
            chunk_index: index as u32,
            first_row: c.first_row,
            rows: c.rows,
            encoded_bytes: c.encoded_bytes as usize,
            digest: c.digest,
        })
    }
    pub fn chunk_matches(&self, index: usize, q: QuerySpec) -> Result<bool> {
        q.validate()?;
        let c = self.chunks.get(index).ok_or(SourceError::InvalidFrame)?;
        Ok(summary_matches(c, q))
    }
    pub fn read_chunk<R: GeoChunkReader>(
        &self,
        index: usize,
        reader: &mut R,
        cancel: &mut impl FnMut() -> bool,
        peak: usize,
    ) -> Result<GeoChunk> {
        let req = self.read_request(index)?;
        check_cancel(cancel)?;
        let raw = reader.read_chunk(req)?;
        check_cancel(cancel)?;
        check_read(&raw, req)?;
        GeoChunk::parse(
            &raw,
            peak.checked_sub(raw.capacity() - raw.len())
                .ok_or(SourceError::ResourceLimit)?,
        )
    }
    /// Streaming fold: each admitted chunk is read once, with no membership allocation.
    /// Consumer memory must fit `consumer_bytes`; callbacks publish only after success.
    pub fn scan_chunks<R: GeoChunkReader>(
        &self,
        q: QuerySpec,
        budget: QueryBudget,
        consumer_bytes: usize,
        reader: &mut R,
        cancel: &mut impl FnMut() -> bool,
        mut consumer: impl FnMut(FeatureView<'_>, FeatureRef) -> Result<()>,
    ) -> Result<ScanStats> {
        q.validate()?;
        budget.validate()?;
        let reserve = add(self.metadata_bytes(), add(consumer_bytes, 8192)?)?;
        let peak = budget
            .processor_bytes
            .checked_sub(reserve)
            .ok_or(SourceError::ResourceLimit)?
            .min(MAX_CHUNK_PEAK);
        let mut stats = ScanStats::default();
        for (index, c) in self.chunks.iter().enumerate() {
            check_cancel(cancel)?;
            if stats.chunks_considered == budget.max_chunks {
                return Err(SourceError::ResourceLimit);
            }
            stats.chunks_considered += 1;
            if !summary_matches(c, q) {
                continue;
            }
            if add64(stats.bytes_read, c.encoded_bytes as u64)? > budget.max_read_bytes
                || add64(stats.rows_examined, c.rows as u64)? > budget.max_rows_examined
            {
                return Err(SourceError::ResourceLimit);
            }
            let chunk = self.read_chunk(index, reader, cancel, peak)?;
            stats.chunks_read += 1;
            stats.bytes_read += c.encoded_bytes as u64;
            stats.rows_examined += c.rows as u64;
            for f in chunk.rows() {
                if f.row % 256 == 0 {
                    check_cancel(cancel)?;
                }
                if f.matches(q) {
                    let id = FeatureRef {
                        chunk_index: index as u32,
                        row: f.row as u32,
                        source_row: c.first_row + f.row as u64,
                        feature_id: f.column.feature_ids()[f.row],
                    };
                    consumer(f, id)?;
                    stats.features_visited += 1;
                }
            }
        }
        Ok(stats)
    }
    /// Full membership is paged source order, never a sampled representative or global mask.
    /// Consumer callbacks are tentative until this call succeeds; callers publish transactionally.
    pub fn query_page<R: GeoChunkReader>(
        &self,
        q: QuerySpec,
        cursor: Option<QueryCursor>,
        budget: QueryBudget,
        reader: &mut R,
        cancel: &mut impl FnMut() -> bool,
        consumer: impl FnMut(FeatureView<'_>, FeatureRef) -> Result<()>,
    ) -> Result<MembershipPage> {
        self.query_page_where(q, cursor, budget, reader, cancel, |_| Ok(true), consumer)
    }
    /// Refine conservative candidates in Rust. Predicate identity belongs to the caller's
    /// outer cursor (camera/bin/tier/style); the source cursor binds only source and QuerySpec.
    #[allow(clippy::too_many_arguments)]
    pub fn query_page_where<R: GeoChunkReader>(
        &self,
        q: QuerySpec,
        cursor: Option<QueryCursor>,
        budget: QueryBudget,
        reader: &mut R,
        cancel: &mut impl FnMut() -> bool,
        mut predicate: impl FnMut(&FeatureView<'_>) -> Result<bool>,
        mut consumer: impl FnMut(FeatureView<'_>, FeatureRef) -> Result<()>,
    ) -> Result<MembershipPage> {
        q.validate()?;
        budget.validate()?;
        let token = q.digest();
        let mut current = cursor.unwrap_or(QueryCursor {
            generation: self.generation,
            source_digest: self.digest,
            query_digest: token,
            chunk_index: 0,
            row: 0,
        });
        if current.generation != self.generation
            || current.source_digest != self.digest
            || current.query_digest != token
        {
            return Err(SourceError::StaleSource);
        }
        if current.chunk_index as usize > self.chunks.len() || current.row > MAX_CHUNK_ROWS as u32 {
            return Err(SourceError::InvalidFrame);
        }
        let output = mul(budget.page_rows, std::mem::size_of::<FeatureRef>())?;
        let peak = budget
            .processor_bytes
            .checked_sub(add(self.metadata_bytes(), add(output, 8192)?)?)
            .ok_or(SourceError::ResourceLimit)?
            .min(MAX_CHUNK_PEAK);
        let mut page = MembershipPage {
            features: Vec::with_capacity(budget.page_rows),
            next: None,
            chunks_considered: 0,
            chunks_read: 0,
            bytes_read: 0,
            rows_examined: 0,
        };
        while (current.chunk_index as usize) < self.chunks.len() {
            check_cancel(cancel)?;
            let idx = current.chunk_index as usize;
            let c = &self.chunks[idx];
            if current.row > c.rows {
                return Err(SourceError::InvalidFrame);
            }
            if page.chunks_considered == budget.max_chunks {
                page.next = Some(current);
                return Ok(page);
            }
            page.chunks_considered += 1;
            // Temporal zone map precedes spatial zone map, including for cancelled/revised consumers.
            if !summary_matches(c, q) {
                current.chunk_index += 1;
                current.row = 0;
                continue;
            }
            let bytes = c.encoded_bytes as usize;
            if add64(page.bytes_read, bytes as u64)? > budget.max_read_bytes {
                return Err(SourceError::ResourceLimit);
            }
            // Every decode walks the whole bounded chunk, including null rows and a
            // resumed prefix. Charge that work, not merely callback memberships.
            if add64(page.rows_examined, c.rows as u64)? > budget.max_rows_examined {
                if page.chunks_read == 0 {
                    return Err(SourceError::ResourceLimit);
                }
                page.next = Some(current);
                return Ok(page);
            }
            page.rows_examined += c.rows as u64;
            let chunk = self.read_chunk(idx, reader, cancel, peak)?;
            page.chunks_read += 1;
            page.bytes_read += bytes as u64;
            for f in chunk.rows() {
                if f.row < current.row as usize {
                    continue;
                }
                current.row = (f.row + 1) as u32;
                if f.row % 256 == 0 {
                    check_cancel(cancel)?;
                }
                if f.matches(q) && predicate(&f)? {
                    let identity = FeatureRef {
                        chunk_index: idx as u32,
                        row: f.row as u32,
                        source_row: c.first_row + f.row as u64,
                        feature_id: chunk.column.feature_ids()[f.row],
                    };
                    consumer(f, identity)?;
                    page.features.push(identity);
                    if page.features.len() == budget.page_rows {
                        page.next = Some(current);
                        return Ok(page);
                    }
                }
            }
            current.chunk_index += 1;
            current.row = 0;
        }
        Ok(page)
    }
}
fn manifest_frame(bytes: &[u8]) -> Result<(usize, u64, u64)> {
    if bytes.len() < HEADER
        || bytes.len() > MAX_MANIFEST_BYTES
        || &bytes[..4] != b"XYGI"
        || u32at(bytes, 4) != 1
        || bytes[40..64].iter().any(|x| *x != 0)
    {
        return Err(SourceError::InvalidFrame);
    }
    let count = usize::try_from(u64at(bytes, 32)).map_err(|_| SourceError::ResourceLimit)?;
    if count == 0 || count > MAX_CHUNKS || add(HEADER, mul(count, ENTRY)?)? != bytes.len() {
        return Err(SourceError::InvalidFrame);
    }
    let generation = u64at(bytes, 16);
    if generation == 0
        || u64at(bytes, 24) > MAX_SOURCE_ROWS
        || GeoGeometry::from_u32(u32at(bytes, 8)).is_none()
        || GeoCrs::from_u32(u32at(bytes, 12)).is_none()
    {
        return Err(SourceError::InvalidFrame);
    }
    let mut first = 0u64;
    for i in 0..count {
        let at = HEADER + i * ENTRY;
        let rows = u32at(bytes, at + 8);
        let flags = u32at(bytes, at + 24);
        let encoded_bytes = u32at(bytes, at + 12) as usize;
        if !(128..=MAX_CHUNK_BYTES).contains(&encoded_bytes)
            || u64at(bytes, at) != first
            || rows == 0
            || rows as usize > MAX_CHUNK_ROWS
            || flags & !15 != 0
            || (flags & 2 == 0 && flags & 12 != 0)
            || bytes[at + 28..at + 32]
                .iter()
                .chain(&bytes[at + 80..at + ENTRY])
                .any(|b| *b != 0)
        {
            return Err(SourceError::InvalidFrame);
        }
        let bounds = SourceBounds {
            min_x: f64at(bytes, at + 32),
            min_y: f64at(bytes, at + 40),
            max_x: f64at(bytes, at + 48),
            max_y: f64at(bytes, at + 56),
        };
        if (flags & 1 != 0 && !bounds.valid())
            || (flags & 1 == 0 && bytes[at + 32..at + 64].iter().any(|b| *b != 0))
            || (flags & 4 == 0 && u64at(bytes, at + 64) != 0)
            || (flags & 8 == 0 && u64at(bytes, at + 72) != 0)
        {
            return Err(SourceError::InvalidFrame);
        }
        first = first
            .checked_add(rows as u64)
            .ok_or(SourceError::ResourceLimit)?;
    }
    if first != u64at(bytes, 24) {
        return Err(SourceError::InvalidFrame);
    }
    Ok((count, generation, first))
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ReadRequest {
    pub generation: u64,
    pub chunk_index: u32,
    pub first_row: u64,
    pub rows: u32,
    pub encoded_bytes: usize,
    pub digest: [u8; 8],
}
/// Host transport must honor the exact request length BEFORE allocating or issuing I/O.
/// Returned capacity is checked as well as length; no implicit filesystem/network transport exists.
pub trait GeoChunkReader {
    fn read_chunk(&mut self, request: ReadRequest) -> Result<Vec<u8>>;
}
impl<F: FnMut(ReadRequest) -> Result<Vec<u8>>> GeoChunkReader for F {
    fn read_chunk(&mut self, r: ReadRequest) -> Result<Vec<u8>> {
        self(r)
    }
}
fn check_read(b: &Vec<u8>, r: ReadRequest) -> Result<()> {
    if b.len() != r.encoded_bytes || b.capacity() > MAX_CHUNK_BYTES {
        return Err(SourceError::ResourceLimit);
    }
    if hash(b"xyg-geo-chunk-v1", b) != r.digest {
        return Err(SourceError::StaleSource);
    }
    Ok(())
}
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct QuerySpec {
    pub bounds: Option<SourceBounds>,
    pub time: TimePredicate,
}
impl QuerySpec {
    pub fn validate(self) -> Result<()> {
        self.time.validate()?;
        if self.bounds.is_some_and(|v| !v.valid()) {
            Err(SourceError::InvalidFrame)
        } else {
            Ok(())
        }
    }
    pub fn digest(self) -> [u8; 8] {
        let mut b = [0u8; 56];
        if let Some(v) = self.bounds {
            b[0] = 1;
            for (i, x) in [v.min_x, v.min_y, v.max_x, v.max_y].into_iter().enumerate() {
                put64(&mut b, 8 + i * 8, x.to_bits())
            }
        }
        match self.time {
            TimePredicate::All => {}
            TimePredicate::Instant(t) => {
                b[1] = 1;
                put64(&mut b, 40, t as u64)
            }
            TimePredicate::Window { start, end } => {
                b[1] = 2;
                put64(&mut b, 40, start as u64);
                put64(&mut b, 48, end as u64)
            }
        }
        hash(b"xyg-geo-query-v1", &b)
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FeatureRef {
    pub chunk_index: u32,
    pub row: u32,
    pub source_row: u64,
    pub feature_id: u64,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct QueryCursor {
    pub generation: u64,
    pub source_digest: [u8; 8],
    pub query_digest: [u8; 8],
    pub chunk_index: u32,
    pub row: u32,
}
#[derive(Debug, Clone, Copy)]
pub struct QueryBudget {
    pub processor_bytes: usize,
    pub page_rows: usize,
    pub max_chunks: usize,
    pub max_rows_examined: u64,
    pub max_read_bytes: u64,
}
impl Default for QueryBudget {
    fn default() -> Self {
        Self {
            processor_bytes: MAX_PROCESSOR_BYTES,
            page_rows: MAX_PAGE_ROWS,
            max_chunks: MAX_CHUNKS,
            max_rows_examined: 1_000_000,
            max_read_bytes: 128 * 1024 * 1024,
        }
    }
}
impl QueryBudget {
    pub fn validate(self) -> Result<()> {
        if self.processor_bytes > MAX_PROCESSOR_BYTES
            || self.page_rows == 0
            || self.page_rows > MAX_PAGE_ROWS
            || self.max_chunks == 0
            || self.max_chunks > MAX_CHUNKS
            || self.max_rows_examined == 0
            || self.max_read_bytes == 0
        {
            Err(SourceError::ResourceLimit)
        } else {
            Ok(())
        }
    }
}
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct ScanStats {
    pub chunks_considered: usize,
    pub chunks_read: usize,
    pub bytes_read: u64,
    pub rows_examined: u64,
    pub features_visited: usize,
}
#[derive(Debug)]
pub struct MembershipPage {
    pub features: Vec<FeatureRef>,
    pub next: Option<QueryCursor>,
    pub chunks_considered: usize,
    pub chunks_read: usize,
    pub bytes_read: u64,
    pub rows_examined: u64,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo::{GeoDescriptor, GeoLimits};
    fn column(kind: GeoGeometry, ids: &[u64]) -> GeoColumn {
        let point = [179.0, 1.0];
        let line = [179.0, 1.0, -179.0, 2.0];
        let ring = [179.0, 0.0, -179.0, 0.0, -179.0, 3.0, 179.0, 3.0, 179.0, 0.0];
        let (xy, o0, o1, o2): (&[f64], &[u32], &[u32], &[u32]) = match kind {
            GeoGeometry::Point => (&point, &[], &[], &[]),
            GeoGeometry::LineString | GeoGeometry::MultiPoint => (&line, &[0, 2, 2], &[], &[]),
            GeoGeometry::Polygon | GeoGeometry::MultiLineString => {
                (&ring, &[0, 1, 1], &[0, 5], &[])
            }
            GeoGeometry::MultiPolygon => (&ring, &[0, 1, 1], &[0, 1], &[0, 5]),
        };
        GeoColumn::from_descriptor(GeoDescriptor {
            geometry: kind,
            crs: GeoCrs::Epsg4326,
            xy,
            validity: &[1, 0],
            feature_ids: Some(ids),
            offsets0: o0,
            offsets1: o1,
            offsets2: o2,
            limits: GeoLimits::default(),
        })
        .unwrap()
    }
    fn encoded(kind: GeoGeometry) -> Vec<u8> {
        GeoChunk::encode(&column(kind, &[u64::MAX, 1 << 63]), None).unwrap()
    }
    fn manifest(chunks: &[Vec<u8>]) -> GeoSourceManifest {
        let mut builder = GeoManifestBuilder::new();
        for b in chunks {
            builder
                .push(&GeoChunk::parse(b, MAX_CHUNK_PEAK).unwrap())
                .unwrap()
        }
        builder.finish(7).unwrap()
    }
    fn all() -> QuerySpec {
        QuerySpec {
            bounds: None,
            time: TimePredicate::All,
        }
    }
    #[test]
    fn all_six_kinds_canonical_roundtrip_exact_ids_nulls_topology_and_dateline() {
        for kind in [
            GeoGeometry::Point,
            GeoGeometry::LineString,
            GeoGeometry::Polygon,
            GeoGeometry::MultiPoint,
            GeoGeometry::MultiLineString,
            GeoGeometry::MultiPolygon,
        ] {
            let b = encoded(kind);
            let parsed = GeoChunk::parse(&b, MAX_CHUNK_PEAK).unwrap();
            let expected = column(kind, &[u64::MAX, 1 << 63]);
            assert_eq!(
                parsed.column.canonical_metadata(),
                expected.canonical_metadata()
            );
            assert_eq!(parsed.column.feature_ids(), &[u64::MAX, 1 << 63]);
            assert_eq!(
                GeoChunk::encode(parsed.column(), parsed.intervals()).unwrap(),
                b
            );
            let features: Vec<_> = parsed.rows().collect();
            assert_eq!(features.len(), 1);
            assert_eq!(features[0].row, 0);
            assert_eq!(features[0].vertices.end, expected.vertex_count());
            let bounds = features[0].bounds().unwrap();
            if kind != GeoGeometry::Point {
                assert_eq!((bounds.min_x, bounds.max_x), (-180., 180.));
            }
        }
    }
    #[test]
    fn paged_membership_source_ordinals_include_nulls_and_duplicate_full_ids() {
        let chunks = vec![
            encoded(GeoGeometry::MultiPoint),
            encoded(GeoGeometry::MultiPoint),
        ];
        let m = manifest(&chunks);
        let mut reads = 0;
        let mut reader = |r: ReadRequest| {
            reads += 1;
            Ok(chunks[r.chunk_index as usize].clone())
        };
        let mut seen = Vec::new();
        let budget = QueryBudget {
            page_rows: 1,
            ..Default::default()
        };
        let first = m
            .query_page(all(), None, budget, &mut reader, &mut || false, |f, id| {
                seen.push((f.vertices, id));
                Ok(())
            })
            .unwrap();
        assert_eq!(first.features[0].source_row, 0);
        assert_eq!(first.features[0].feature_id, u64::MAX);
        let second = m
            .query_page(
                all(),
                first.next,
                budget,
                &mut reader,
                &mut || false,
                |f, id| {
                    seen.push((f.vertices, id));
                    Ok(())
                },
            )
            .unwrap();
        assert_eq!(second.features[0].source_row, 2);
        assert_eq!(second.features[0].feature_id, u64::MAX);
        let final_page = m
            .query_page(
                all(),
                second.next,
                budget,
                &mut reader,
                &mut || false,
                |_, _| panic!("no remaining member"),
            )
            .unwrap();
        assert!(final_page.features.is_empty());
        assert!(final_page.next.is_none());
        assert_eq!(seen.len(), 2);
        assert_eq!(reads, 4);
    }
    #[test]
    fn signed_half_open_time_filters_before_spatial_reads_and_unbounded_endpoints() {
        let c = column(GeoGeometry::Point, &[u64::MAX, 4]);
        let t = GeoIntervals {
            starts: &[-10, 0],
            ends: &[10, 0],
            start_validity: &[1, 0],
            end_validity: &[1, 0],
        };
        let b = GeoChunk::encode(&c, Some(t)).unwrap();
        let chunks = vec![b];
        let m = manifest(&chunks);
        let mut reads = 0;
        let mut reader = |r: ReadRequest| {
            reads += 1;
            Ok(chunks[r.chunk_index as usize].clone())
        };
        for instant in [-11, 10, i64::MAX] {
            let q = QuerySpec {
                bounds: Some(SourceBounds {
                    min_x: 178.,
                    max_x: 180.,
                    min_y: 0.,
                    max_y: 3.,
                }),
                time: TimePredicate::Instant(instant),
            };
            let p = m
                .query_page(
                    q,
                    None,
                    Default::default(),
                    &mut reader,
                    &mut || false,
                    |_, _| panic!("expired member"),
                )
                .unwrap();
            assert_eq!(p.chunks_read, 0);
        }
        let q = QuerySpec {
            bounds: None,
            time: TimePredicate::Window {
                start: -10,
                end: -9,
            },
        };
        let p = m
            .query_page(
                q,
                None,
                Default::default(),
                &mut reader,
                &mut || false,
                |f, _| {
                    assert_eq!(f.interval_start, Some(-10));
                    Ok(())
                },
            )
            .unwrap();
        assert_eq!(p.features.len(), 1);
        assert_eq!(reads, 1);
        let invalid = GeoIntervals {
            starts: &[i64::MAX, 0],
            ends: &[i64::MIN, 0],
            start_validity: &[1, 0],
            end_validity: &[1, 0],
        };
        assert_eq!(
            GeoChunk::encode(&c, Some(invalid)).err(),
            Some(SourceError::InvalidTime)
        );
        let unlimited = GeoIntervals {
            starts: &[123, 456],
            ends: &[-123, 0],
            start_validity: &[0, 0],
            end_validity: &[0, 0],
        };
        let b = GeoChunk::encode(&c, Some(unlimited)).unwrap();
        let parsed = GeoChunk::parse(&b, MAX_CHUNK_PEAK).unwrap();
        assert_eq!(parsed.intervals().unwrap().starts, &[0, 0]);
        assert!(parsed.rows().next().unwrap().matches(QuerySpec {
            bounds: None,
            time: TimePredicate::Instant(i64::MAX)
        }));
    }
    #[test]
    fn persisted_summaries_are_untrusted_until_every_chunk_validates() {
        let chunks = vec![encoded(GeoGeometry::Polygon), encoded(GeoGeometry::Polygon)];
        let m = manifest(&chunks);
        let bytes = m.encode().unwrap();
        let mut reads = 0;
        let mut reader = |r: ReadRequest| {
            reads += 1;
            Ok(chunks[r.chunk_index as usize].clone())
        };
        let validated = GeoSourceManifest::validate(&bytes, &mut reader, &mut || false).unwrap();
        assert_eq!(validated.digest(), m.digest());
        assert_eq!(reads, 2);
        let mut forged = bytes.clone();
        put64(&mut forged, 64 + 32, 0f64.to_bits());
        let mut reads = 0;
        let mut reader = |r: ReadRequest| {
            reads += 1;
            Ok(chunks[r.chunk_index as usize].clone())
        };
        assert_eq!(
            GeoSourceManifest::validate(&forged, &mut reader, &mut || false).err(),
            Some(SourceError::StaleSource)
        );
        assert_eq!(reads, 1);
        let mut changed = chunks[0].clone();
        changed[128] ^= 1;
        let mut reader = |_: ReadRequest| Ok(changed.clone());
        assert_eq!(
            m.read_chunk(0, &mut reader, &mut || false, MAX_CHUNK_PEAK)
                .err(),
            Some(SourceError::StaleSource)
        );
    }
    #[test]
    fn cancellation_before_and_after_read_never_calls_spatial_consumer() {
        let chunks = vec![encoded(GeoGeometry::LineString)];
        let m = manifest(&chunks);
        let mut reader = |_: ReadRequest| panic!("cancelled read issued");
        assert_eq!(
            m.query_page(
                all(),
                None,
                Default::default(),
                &mut reader,
                &mut || true,
                |_, _| panic!()
            )
            .err(),
            Some(SourceError::Cancelled)
        );
        let mut reader = |_: ReadRequest| Ok(chunks[0].clone());
        let mut checks = 0;
        let mut cancel = || {
            checks += 1;
            checks == 3
        };
        assert_eq!(
            m.query_page(
                all(),
                None,
                Default::default(),
                &mut reader,
                &mut cancel,
                |_, _| panic!("cancelled consumer")
            )
            .err(),
            Some(SourceError::Cancelled)
        );
    }
    #[test]
    fn framing_limits_and_cursor_revision_fail_closed() {
        let b = encoded(GeoGeometry::Point);
        let mut malformed = b.clone();
        put64(&mut malformed, 24, (MAX_CHUNK_ROWS + 1) as u64);
        assert_eq!(
            GeoChunk::parse(&malformed, MAX_CHUNK_PEAK).err(),
            Some(SourceError::ResourceLimit)
        );
        let mut malformed = b.clone();
        malformed[12] = 1;
        assert_eq!(
            GeoChunk::parse(&malformed, MAX_CHUNK_PEAK).err(),
            Some(SourceError::InvalidFrame)
        );
        assert!(GeoChunk::parse(&b, 1).is_err());
        let m = manifest(std::slice::from_ref(&b));
        let mut reader = |_: ReadRequest| Ok(b.clone());
        let first = m
            .query_page(
                all(),
                None,
                QueryBudget {
                    page_rows: 1,
                    ..Default::default()
                },
                &mut reader,
                &mut || false,
                |_, _| Ok(()),
            )
            .unwrap();
        let mut cursor = first.next.unwrap();
        cursor.generation += 1;
        assert_eq!(
            m.query_page(
                all(),
                Some(cursor),
                Default::default(),
                &mut reader,
                &mut || false,
                |_, _| panic!()
            )
            .err(),
            Some(SourceError::StaleSource)
        );
        let q = QuerySpec {
            bounds: None,
            time: TimePredicate::Instant(0),
        };
        assert_eq!(
            m.query_page(
                q,
                first.next,
                Default::default(),
                &mut reader,
                &mut || false,
                |_, _| panic!()
            )
            .err(),
            Some(SourceError::StaleSource)
        );
        assert_eq!(
            m.query_page(
                all(),
                None,
                QueryBudget {
                    max_read_bytes: 1,
                    ..Default::default()
                },
                &mut reader,
                &mut || false,
                |_, _| panic!()
            )
            .err(),
            Some(SourceError::ResourceLimit)
        );
        assert_eq!(
            m.query_page(
                all(),
                None,
                QueryBudget {
                    processor_bytes: 100,
                    ..Default::default()
                },
                &mut reader,
                &mut || false,
                |_, _| panic!()
            )
            .err(),
            Some(SourceError::ResourceLimit)
        );
    }
}

#[cfg(test)]
mod additional_tests {
    use super::*;
    use crate::geo::{GeoDescriptor, GeoLimits};
    fn points() -> GeoColumn {
        GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg4326,
            xy: &[100., 0., -100., 0., 10., 0.],
            validity: &[1, 1, 1, 0],
            feature_ids: Some(&[u64::MAX, 4, 4, 999]),
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap()
    }
    #[test]
    fn unordered_scalar_scan_reads_once_time_first_and_preserves_bit_patterns() {
        let c = points();
        let values = [f64::from_bits(0x7ff8000000001234), -0., 17., f64::INFINITY];
        let times = GeoIntervals {
            starts: &[-100, -100, 0, 0],
            ends: &[-10, -10, 20, 0],
            start_validity: &[1, 1, 1, 0],
            end_validity: &[1, 1, 1, 0],
        };
        let bytes = GeoChunk::encode_with_values(&c, Some(times), Some(&values)).unwrap();
        let chunk = GeoChunk::parse(&bytes, MAX_CHUNK_PEAK).unwrap();
        assert_eq!(
            chunk
                .values()
                .unwrap()
                .iter()
                .map(|v| v.to_bits())
                .collect::<Vec<_>>(),
            values.iter().map(|v| v.to_bits()).collect::<Vec<_>>()
        );
        assert_eq!(
            GeoChunk::encode_with_values(chunk.column(), chunk.intervals(), chunk.values())
                .unwrap(),
            bytes
        );
        let mut builder = GeoManifestBuilder::new();
        builder.push(&chunk).unwrap();
        let m = builder.finish(99).unwrap();
        let reads = std::cell::Cell::new(0);
        let mut reader = |_: ReadRequest| {
            reads.set(reads.get() + 1);
            Ok(bytes.clone())
        };
        let mut seen = Vec::new();
        let q = QuerySpec {
            bounds: Some(SourceBounds {
                min_x: 9.,
                max_x: 11.,
                min_y: -1.,
                max_y: 1.,
            }),
            time: TimePredicate::Instant(0),
        };
        let stats = m
            .scan_chunks(
                q,
                Default::default(),
                1024,
                &mut reader,
                &mut || false,
                |f, id| {
                    assert_eq!(f.value, Some(17.));
                    seen.push(id);
                    Ok(())
                },
            )
            .unwrap();
        assert_eq!(reads.get(), 1);
        assert_eq!(stats.rows_examined, 4);
        assert_eq!(stats.features_visited, 1);
        assert_eq!(seen[0].source_row, 2);
        assert_eq!(seen[0].feature_id, 4);
        assert_eq!(
            m.scan_chunks(
                q,
                QueryBudget {
                    max_rows_examined: 3,
                    ..Default::default()
                },
                0,
                &mut reader,
                &mut || false,
                |_, _| panic!()
            )
            .err(),
            Some(SourceError::ResourceLimit)
        );
        assert_eq!(reads.get(), 1);
        assert_eq!(
            m.scan_chunks(
                q,
                Default::default(),
                MAX_PROCESSOR_BYTES,
                &mut reader,
                &mut || false,
                |_, _| panic!()
            )
            .err(),
            Some(SourceError::ResourceLimit)
        );
    }
    #[test]
    fn multipolygon_hole_and_parts_are_retained_as_canonical_topology() {
        let xy = [
            0., 0., 4., 0., 4., 4., 0., 4., 0., 0., 1., 1., 2., 1., 2., 2., 1., 2., 1., 1., 10.,
            0., 14., 0., 14., 4., 10., 4., 10., 0.,
        ];
        let c = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::MultiPolygon,
            crs: GeoCrs::Epsg4326,
            xy: &xy,
            validity: &[1, 0],
            feature_ids: Some(&[u64::MAX, 0]),
            offsets0: &[0, 2, 2],
            offsets1: &[0, 2, 3],
            offsets2: &[0, 5, 10, 15],
            limits: GeoLimits::default(),
        })
        .unwrap();
        let b = GeoChunk::encode(&c, None).unwrap();
        let parsed = GeoChunk::parse(&b, MAX_CHUNK_PEAK).unwrap();
        assert_eq!(parsed.column.canonical_metadata(), c.canonical_metadata());
        let f = parsed.rows().next().unwrap();
        assert_eq!(f.vertices, 0..15);
        assert_eq!(f.column.offsets1(), &[0, 2, 3]);
        assert_eq!(f.column.offsets2(), &[0, 5, 10, 15]);
    }
    #[test]
    fn read_capacity_and_manifest_validation_work_are_admitted_before_consumer() {
        let b = GeoChunk::encode(&points(), None).unwrap();
        let c = GeoChunk::parse(&b, MAX_CHUNK_PEAK).unwrap();
        let mut builder = GeoManifestBuilder::new();
        builder.push(&c).unwrap();
        let m = builder.finish(1).unwrap();
        let manifest = m.encode().unwrap();
        let mut reader = |_: ReadRequest| panic!("over-budget read");
        assert_eq!(
            GeoSourceManifest::validate_with_budget(
                &manifest,
                &mut reader,
                &mut || false,
                QueryBudget {
                    max_rows_examined: 3,
                    ..Default::default()
                }
            )
            .err(),
            Some(SourceError::ResourceLimit)
        );
        let mut reader = |_: ReadRequest| {
            let mut huge = Vec::with_capacity(MAX_CHUNK_BYTES + 1);
            huge.extend_from_slice(&b);
            Ok(huge)
        };
        assert_eq!(
            m.read_chunk(0, &mut reader, &mut || false, MAX_CHUNK_PEAK)
                .err(),
            Some(SourceError::ResourceLimit)
        );
        let mut invalid = manifest.clone();
        put64(&mut invalid, 16, 0);
        let mut reader = |_: ReadRequest| panic!("invalid framing issued read");
        assert_eq!(
            GeoSourceManifest::validate(&invalid, &mut reader, &mut || false).err(),
            Some(SourceError::InvalidFrame)
        );
        let mut invalid = b.clone();
        put32(&mut invalid, 8, 4);
        assert_eq!(
            GeoChunk::parse(&invalid, MAX_CHUNK_PEAK).err(),
            Some(SourceError::InvalidFrame)
        );
    }
}

#[cfg(test)]
mod refinement_tests {
    use super::*;
    use crate::geo::{GeoDescriptor, GeoLimits};
    #[test]
    fn paged_predicate_sees_only_time_candidates_and_returns_full_source_membership() {
        let c = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::MultiPoint,
            crs: GeoCrs::Epsg4326,
            xy: &[0., 0., 0., 0., 1., 1., 2., 2.],
            validity: &[1, 1, 1],
            feature_ids: Some(&[u64::MAX, 4, 4]),
            offsets0: &[0, 2, 3, 4],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        let time = GeoIntervals {
            starts: &[-5, -5, -5],
            ends: &[5, -1, 5],
            start_validity: &[1, 1, 1],
            end_validity: &[1, 1, 1],
        };
        let bytes = GeoChunk::encode(&c, Some(time)).unwrap();
        let chunk = GeoChunk::parse(&bytes, MAX_CHUNK_PEAK).unwrap();
        let mut builder = GeoManifestBuilder::new();
        builder.push(&chunk).unwrap();
        let m = builder.finish(1).unwrap();
        let mut reader = |_: ReadRequest| Ok(bytes.clone());
        let q = QuerySpec {
            bounds: None,
            time: TimePredicate::Instant(0),
        };
        let mut candidates = Vec::new();
        let page = m
            .query_page_where(
                q,
                None,
                Default::default(),
                &mut reader,
                &mut || false,
                |f| {
                    candidates.push(f.row);
                    Ok(f.vertices.len() > 1)
                },
                |f, id| {
                    assert_eq!(f.vertices, 0..2);
                    assert_eq!(id.feature_id, u64::MAX);
                    Ok(())
                },
            )
            .unwrap();
        assert_eq!(candidates, vec![0, 2]);
        assert_eq!(page.features.len(), 1);
        assert_eq!(page.rows_examined, 3);
        assert!(page.next.is_none());
    }
    #[test]
    fn billion_row_plan_is_allocation_free_and_stream_counters_exceed_u32() {
        let plan = GeoSourcePlan::new(MAX_SOURCE_ROWS, MAX_CHUNK_ROWS as u32).unwrap();
        assert_eq!(plan.chunks, 15259);
        assert_eq!(plan.manifest_bytes, 1_953_216);
        assert_eq!(plan.processor_bytes, 128 * 1024 * 1024);
        assert_eq!(
            GeoSourcePlan::new(MAX_SOURCE_ROWS + 1, 65536).err(),
            Some(SourceError::ResourceLimit)
        );
        assert_eq!(
            GeoSourcePlan::new(MAX_SOURCE_ROWS, 1).err(),
            Some(SourceError::ResourceLimit)
        );
        let budget = QueryBudget {
            max_read_bytes: u32::MAX as u64 + 1_000_000_000,
            max_rows_examined: MAX_SOURCE_ROWS,
            ..Default::default()
        };
        assert!(budget.validate().is_ok());
        assert_eq!(add64(u32::MAX as u64, 16).unwrap(), 4_294_967_311);
    }
}

#[cfg(test)]
mod mercator_tests {
    use super::*;
    use crate::geo::{GeoDescriptor, GeoLimits};
    #[test]
    fn mercator_dateline_and_extreme_signed_interval_end_are_conservative() {
        let c = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::MultiPoint,
            crs: GeoCrs::Epsg3857,
            xy: &[19_900_000., 0., -19_900_000., 1.],
            validity: &[1],
            feature_ids: Some(&[u64::MAX]),
            offsets0: &[0, 2],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        let t = GeoIntervals {
            starts: &[i64::MIN],
            ends: &[i64::MAX],
            start_validity: &[1],
            end_validity: &[1],
        };
        let b = GeoChunk::encode(&c, Some(t)).unwrap();
        let chunk = GeoChunk::parse(&b, MAX_CHUNK_PEAK).unwrap();
        let f = chunk.rows().next().unwrap();
        let bounds = f.bounds().unwrap();
        assert_eq!(
            (bounds.min_x, bounds.max_x),
            (-20_037_508.342_789_244, 20_037_508.342_789_244)
        );
        assert!(f.matches(QuerySpec {
            bounds: None,
            time: TimePredicate::Instant(i64::MIN)
        }));
        assert!(!f.matches(QuerySpec {
            bounds: None,
            time: TimePredicate::Instant(i64::MAX)
        }));
    }
}
