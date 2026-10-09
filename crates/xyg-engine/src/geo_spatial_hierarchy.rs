//! Bounded authenticated external geographic hierarchy; dossier §17/§27/§28.
use crate::geo_source::{GeoSourceManifest, ReadRequest, SourceError, TimePredicate};
use crate::geo_source_session::{GeoProcessorLease, next_session_identity};
use crate::geo_spatial_index::{self as flat, GeoSpatialOptions, Vertex};
use crate::geo_viewport::GeoViewport;
use crate::transition::Blake2s8;
use std::sync::Arc;
pub(crate) type Result<T> = std::result::Result<T, SourceError>;
pub const PAGE_BYTES: usize = 65_536;
pub const MAX_FRONTIER: usize = 256;
pub(crate) const FANOUT: usize = 128;
pub(crate) const LEVELS: usize = 12;
pub(crate) const DESC: usize = 128;
pub(crate) const DATA_RECORDS: usize = (PAGE_BYTES - 64) / 80;
pub(crate) const RUN_RECORDS: usize = (PAGE_BYTES - 64) / 96;
pub(crate) use flat::{get32, get64, put32, put64};
pub(crate) fn invalid<T>() -> Result<T> {
    Err(SourceError::InvalidFrame)
}
pub(crate) fn limit<T>() -> Result<T> {
    Err(SourceError::ResourceLimit)
}
pub(crate) fn hash(b: &[u8]) -> [u8; 8] {
    let mut h = Blake2s8::new();
    h.update(b"xyg-hierarchy-page-v1");
    h.update(b);
    h.finish()
}
pub(crate) fn run_hash() -> Blake2s8 {
    let mut h = Blake2s8::new();
    h.update(b"xyg-hierarchy-run-v1");
    h
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GeoHierarchyOptions {
    pub grid: u32,
}
impl Default for GeoHierarchyOptions {
    fn default() -> Self {
        Self { grid: 1024 }
    }
}
impl GeoHierarchyOptions {
    pub fn validate(self) -> Result<()> {
        if self.grid < 16 || self.grid > 4096 || !self.grid.is_power_of_two() {
            return invalid();
        }
        Ok(())
    }
}
pub(crate) fn morton(cell: u32, grid: u32) -> u32 {
    if cell == u32::MAX {
        return u32::MAX;
    }
    let (x, y) = (cell % grid, cell / grid);
    let mut out = 0;
    for b in 0..grid.trailing_zeros() {
        out |= ((x >> b) & 1) << (2 * b);
        out |= ((y >> b) & 1) << (2 * b + 1);
    }
    out
}
pub(crate) fn unmorton(key: u32, grid: u32) -> u32 {
    let (mut x, mut y) = (0, 0);
    for b in 0..grid.trailing_zeros() {
        x |= ((key >> (2 * b)) & 1) << b;
        y |= ((key >> (2 * b + 1)) & 1) << b;
    }
    y * grid + x
}
#[derive(Clone, Copy, Debug)]
pub(crate) struct Record {
    pub cell: u32,
    pub value: Vertex,
}
impl Record {
    pub(crate) fn key(self, grid: u32) -> (u32, u64, u32) {
        (
            morton(self.cell, grid),
            self.value.identity.source_row,
            self.value.vertex,
        )
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Ref {
    pub id: u64,
    pub len: usize,
    pub digest: [u8; 8],
}
/// Data=1; leaf-reference node=2; cell wrapper=3; outer cell directory=4.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Node {
    pub read: Ref,
    pub kind: u32,
    pub first: u32,
    pub last: u32,
    pub count: u64,
    pub pages: u64,
    pub start: Option<i64>,
    pub end: Option<i64>,
}
impl Node {
    pub(crate) fn time(self, t: TimePredicate) -> bool {
        t.matches(self.start, self.end)
    }
}
pub(crate) fn descriptor(b: &mut [u8], a: usize, n: Node) {
    put64(b, a, n.read.id);
    put64(b, a + 8, n.read.len as u64);
    b[a + 16..a + 24].copy_from_slice(&n.read.digest);
    put32(b, a + 24, n.kind);
    put32(b, a + 28, n.first);
    put32(b, a + 32, n.last);
    put32(
        b,
        a + 36,
        u32::from(n.start.is_some()) | u32::from(n.end.is_some()) << 1,
    );
    put64(b, a + 40, n.count);
    put64(b, a + 48, n.pages);
    put64(b, a + 56, n.start.unwrap_or(0) as u64);
    put64(b, a + 64, n.end.unwrap_or(0) as u64);
}
pub(crate) fn parse_descriptor(b: &[u8], a: usize, grid: u32) -> Result<Node> {
    let flags = get32(b, a + 36);
    let n = Node {
        read: Ref {
            id: get64(b, a),
            len: usize::try_from(get64(b, a + 8)).map_err(|_| SourceError::ResourceLimit)?,
            digest: b[a + 16..a + 24].try_into().unwrap(),
        },
        kind: get32(b, a + 24),
        first: get32(b, a + 28),
        last: get32(b, a + 32),
        count: get64(b, a + 40),
        pages: get64(b, a + 48),
        start: (flags & 1 != 0).then(|| get64(b, a + 56) as i64),
        end: (flags & 2 != 0).then(|| get64(b, a + 64) as i64),
    };
    if flags > 3
        || !(1..=4).contains(&n.kind)
        || n.first > n.last
        || (n.first >= grid * grid && n.first != u32::MAX)
        || (n.last >= grid * grid && n.last != u32::MAX)
        || n.read.id == 0
        || n.read.len < 64
        || n.read.len > PAGE_BYTES
        || n.count == 0
        || n.pages == 0
        || b[a + 72..a + DESC].iter().any(|v| *v != 0)
        || (n.start.is_none() && get64(b, a + 56) != 0)
        || (n.end.is_none() && get64(b, a + 64) != 0)
    {
        return invalid();
    }
    Ok(n)
}
pub(crate) fn combine(read: Ref, kind: u32, c: &[Node]) -> Result<Node> {
    let first = c.first().ok_or(SourceError::InvalidFrame)?;
    let last = c.last().unwrap();
    let (mut count, mut pages) = (0u64, 0u64);
    let (mut start, mut end) = (first.start, first.end);
    for n in c {
        count = count
            .checked_add(n.count)
            .ok_or(SourceError::ResourceLimit)?;
        pages = pages
            .checked_add(n.pages)
            .ok_or(SourceError::ResourceLimit)?;
        start = match (start, n.start) {
            (Some(a), Some(b)) => Some(a.min(b)),
            _ => None,
        };
        end = match (end, n.end) {
            (Some(a), Some(b)) => Some(a.max(b)),
            _ => None,
        };
    }
    Ok(Node {
        read,
        kind,
        first: first.first,
        last: last.last,
        count,
        pages,
        start,
        end,
    })
}
pub(crate) fn node_bytes(id: u64, kind: u32, c: &[Node]) -> Vec<u8> {
    let mut b = vec![0; 64 + c.len() * DESC];
    b[..4].copy_from_slice(b"XYHN");
    put32(&mut b, 4, 1);
    put64(&mut b, 8, id);
    put32(&mut b, 16, kind);
    put32(&mut b, 20, c.len() as u32);
    for (i, &n) in c.iter().enumerate() {
        descriptor(&mut b, 64 + i * DESC, n);
    }
    b
}
pub(crate) fn children(b: &[u8], n: Node, grid: u32) -> Result<Vec<Node>> {
    if b.len() != n.read.len
        || hash(b) != n.read.digest
        || b.len() < 64
        || &b[..4] != b"XYHN"
        || get32(b, 4) != 1
        || get64(b, 8) != n.read.id
        || get32(b, 16) != n.kind
        || b[24..64].iter().any(|v| *v != 0)
    {
        return invalid();
    }
    let count = get32(b, 20) as usize;
    if count == 0 || count > FANOUT || b.len() != 64 + count * DESC {
        return invalid();
    }
    let mut out = Vec::with_capacity(count);
    for i in 0..count {
        out.push(parse_descriptor(b, 64 + i * DESC, grid)?);
    }
    if out.iter().any(|c| c.read.id >= n.read.id)
        || out.windows(2).any(|p| p[0].last > p[1].first)
        || (n.kind == 2 && out.iter().any(|c| c.kind != 1 && c.kind != 2))
        || (n.kind == 3 && (out.len() != 1 || out[0].kind > 2 || out[0].first != out[0].last))
        || (n.kind == 4 && out.iter().any(|c| c.kind != 3 && c.kind != 4))
        || combine(n.read, n.kind, &out)? != n
    {
        return invalid();
    }
    Ok(out)
}
pub(crate) fn data_bytes(id: u64, cell: u32, values: &[Vertex]) -> Vec<u8> {
    let mut b = vec![0; 64 + values.len() * 80];
    b[..4].copy_from_slice(b"XYHL");
    put32(&mut b, 4, 1);
    put64(&mut b, 8, id);
    put32(&mut b, 16, cell);
    put32(&mut b, 20, values.len() as u32);
    for (i, &v) in values.iter().enumerate() {
        flat::write_vertex(&mut b, 64 + i * 80, v);
    }
    b
}
pub(crate) fn decode_vertex(b: &[u8]) -> Result<Vertex> {
    let flags = get32(b, 28);
    if flags > 7
        || b[72..80].iter().any(|v| *v != 0)
        || (flags & 1 == 0 && get64(b, 48) != 0)
        || (flags & 2 == 0 && get64(b, 56) != 0)
        || (flags & 4 == 0 && get64(b, 64) != 0)
    {
        return invalid();
    }
    let v = Vertex {
        identity: crate::geo_source::FeatureRef {
            source_row: get64(b, 0),
            feature_id: get64(b, 8),
            chunk_index: get32(b, 16),
            row: get32(b, 20),
        },
        vertex: get32(b, 24),
        xy: [f64::from_bits(get64(b, 32)), f64::from_bits(get64(b, 40))],
        start: (flags & 1 != 0).then(|| get64(b, 48) as i64),
        end: (flags & 2 != 0).then(|| get64(b, 56) as i64),
        value: (flags & 4 != 0).then(|| f64::from_bits(get64(b, 64))),
    };
    if v.xy.iter().any(|v| !v.is_finite()) || matches!((v.start,v.end),(Some(a),Some(b))if a>=b) {
        return invalid();
    }
    Ok(v)
}
pub(crate) fn data(b: &[u8], n: Node, grid: u32) -> Result<Vec<Vertex>> {
    if b.len() != n.read.len
        || hash(b) != n.read.digest
        || b.len() < 64
        || &b[..4] != b"XYHL"
        || get32(b, 4) != 1
        || get64(b, 8) != n.read.id
        || (get32(b, 16) >= grid * grid && get32(b, 16) != u32::MAX)
        || morton(get32(b, 16), grid) != n.first
        || n.first != n.last
        || get32(b, 20) as u64 != n.count
        || n.kind != 1
        || n.pages != 1
        || b[24..64].iter().any(|v| *v != 0)
        || n.count > DATA_RECORDS as u64
        || b.len() != 64 + n.count as usize * 80
    {
        return invalid();
    }
    let mut out = Vec::with_capacity(n.count as usize);
    for bytes in b[64..].chunks_exact(80) {
        out.push(decode_vertex(bytes)?);
    }
    if out
        .windows(2)
        .any(|p| (p[0].identity.source_row, p[0].vertex) >= (p[1].identity.source_row, p[1].vertex))
    {
        return invalid();
    }
    let summary = summarize(n.read, n.first, &out)?;
    if summary != n {
        return invalid();
    }
    Ok(out)
}
pub(crate) fn summarize(read: Ref, key: u32, v: &[Vertex]) -> Result<Node> {
    let first = v.first().ok_or(SourceError::InvalidFrame)?;
    let (mut start, mut end) = (first.start, first.end);
    for v in v.iter().skip(1) {
        start = match (start, v.start) {
            (Some(a), Some(b)) => Some(a.min(b)),
            _ => None,
        };
        end = match (end, v.end) {
            (Some(a), Some(b)) => Some(a.max(b)),
            _ => None,
        };
    }
    Ok(Node {
        read,
        kind: 1,
        first: key,
        last: key,
        count: v.len() as u64,
        pages: 1,
        start,
        end,
    })
}
pub(crate) fn candidate(
    n: Node,
    options: GeoHierarchyOptions,
    camera: &GeoViewport,
    bounds: Option<[f64; 4]>,
) -> bool {
    if n.last == u32::MAX {
        return true;
    }
    let bits = options.grid.trailing_zeros();
    let xor = n.first ^ n.last;
    let pairs = if xor == 0 {
        0
    } else {
        (32 - xor.leading_zeros()).div_ceil(2)
    };
    let coarse = options.grid >> pairs.min(bits);
    let key = n.first >> (2 * pairs.min(bits));
    flat::candidate(
        unmorton(key, coarse),
        GeoSpatialOptions { grid: coarse },
        camera,
        bounds,
    )
}
#[derive(Clone, Debug)]
pub struct GeoHierarchyTicket {
    pub(crate) owner: u64,
    pub(crate) namespace: u64,
    pub(crate) serial: u64,
    pub(crate) kind: u8,
    pub(crate) read: Ref,
    pub(crate) source: Option<ReadRequest>,
    pub(crate) credit: Arc<GeoProcessorLease>,
}
impl GeoHierarchyTicket {
    pub fn owner(&self) -> u64 {
        self.owner
    }
    pub fn storage_namespace(&self) -> u64 {
        self.namespace
    }
    pub fn serial(&self) -> u64 {
        self.serial
    }
    pub fn kind(&self) -> u8 {
        self.kind
    }
    pub fn page_id(&self) -> u64 {
        self.read.id
    }
    pub fn encoded_bytes(&self) -> usize {
        self.read.len
    }
    pub fn digest(&self) -> [u8; 8] {
        self.read.digest
    }
    pub fn source_request(&self) -> Option<ReadRequest> {
        self.source
    }
    pub(crate) fn same(&self, b: &Self) -> bool {
        self.owner == b.owner
            && self.namespace == b.namespace
            && self.serial == b.serial
            && self.kind == b.kind
            && self.read == b.read
            && self.source.map(|r| {
                (
                    r.generation,
                    r.chunk_index,
                    r.rows,
                    r.first_row,
                    r.encoded_bytes,
                    r.digest,
                )
            }) == b.source.map(|r| {
                (
                    r.generation,
                    r.chunk_index,
                    r.rows,
                    r.first_row,
                    r.encoded_bytes,
                    r.digest,
                )
            })
    }
}
pub(crate) fn ticket(
    owner: u64,
    namespace: u64,
    serial: u64,
    kind: u8,
    read: Ref,
    source: Option<ReadRequest>,
) -> Result<GeoHierarchyTicket> {
    let bytes = read
        .len
        .checked_mul(if kind == 1 { 6 } else { 4 })
        .and_then(|n| n.checked_add(65536))
        .ok_or(SourceError::ResourceLimit)?;
    Ok(GeoHierarchyTicket {
        owner,
        namespace,
        serial,
        kind,
        read,
        source,
        credit: Arc::new(GeoProcessorLease::acquire(bytes)?),
    })
}
#[derive(Clone, Debug)]
pub enum GeoHierarchyStep {
    NeedRead(GeoHierarchyTicket),
    NeedWrite(GeoHierarchyTicket),
    AwaitRelease,
    Complete,
    Cancelled,
    FullScanFrontier,
    FullScanWork,
}
/// Only a full authenticated canonical build constructs pruning authority.
pub struct ValidatedGeoHierarchy {
    pub(crate) source: GeoSourceManifest,
    pub(crate) options: GeoHierarchyOptions,
    pub(crate) root: Option<Node>,
    pub(crate) namespace: u64,
    pub(crate) digest: [u8; 8],
    pub(crate) credit: GeoProcessorLease,
}
impl ValidatedGeoHierarchy {
    pub fn source(&self) -> &GeoSourceManifest {
        &self.source
    }
    pub fn options(&self) -> GeoHierarchyOptions {
        self.options
    }
    pub fn storage_namespace(&self) -> u64 {
        self.namespace
    }
    pub fn digest(&self) -> [u8; 8] {
        self.digest
    }
    pub fn reserved_bytes(&self) -> usize {
        self.credit.bytes()
    }
}
pub(crate) fn root_digest(
    source: &GeoSourceManifest,
    options: GeoHierarchyOptions,
    root: Option<Node>,
) -> [u8; 8] {
    let mut h = Blake2s8::new();
    h.update(b"xyg-hierarchy-root-v1");
    h.update(&source.digest());
    h.update(&source.generation().to_le_bytes());
    h.update(&options.grid.to_le_bytes());
    if let Some(n) = root {
        let mut b = [0; DESC];
        descriptor(&mut b, 0, n);
        h.update(&b);
    }
    h.finish()
}
pub(crate) fn nonce() -> Result<u64> {
    next_session_identity()
}
