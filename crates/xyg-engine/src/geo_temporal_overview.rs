//! Exact temporal data-domain overview, dossier §17/§27/§28.
//! This is deliberately distinct from the exact geographic screen-bin result.
use crate::geo_source::{GeoSourceManifest, SourceError, TimePredicate};
use crate::geo_source_session::{GeoOperationSnapshot, GeoProcessorLease, next_session_identity};
use crate::geo_viewport::GeoViewport;
use crate::transition::Blake2s8;
use std::sync::Arc;

pub type Result<T> = std::result::Result<T, GeoOverviewError>;
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoOverviewError {
    Source(SourceError),
    UnsupportedDomain,
}
impl From<SourceError> for GeoOverviewError {
    fn from(e: SourceError) -> Self {
        Self::Source(e)
    }
}
impl From<crate::geo::GeoError> for GeoOverviewError {
    fn from(e: crate::geo::GeoError) -> Self {
        Self::Source(e.into())
    }
}
pub const CELLS: usize = 256;
pub(crate) const PAGE: usize = 65_536;
pub(crate) const EVENTS: usize = (PAGE - 64) / 16;
pub(crate) const FANOUT: usize = 8;
pub(crate) const CHILD: usize = 4144;
pub(crate) const LEVELS: usize = 12;
pub(crate) type Hist = [u64; 512];
pub(crate) fn invalid<T>() -> Result<T> {
    Err(SourceError::InvalidFrame.into())
}
pub(crate) fn limit<T>() -> Result<T> {
    Err(SourceError::ResourceLimit.into())
}
pub(crate) fn plus(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b).ok_or(SourceError::ResourceLimit.into())
}
pub(crate) fn digest(b: &[u8]) -> [u8; 8] {
    let mut h = Blake2s8::new();
    h.update(b"xyg-overview-v1");
    h.update(b);
    h.finish()
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) struct Event {
    pub time: i64,
    pub cell: u16,
    pub end: bool,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct PageRef {
    pub id: u64,
    pub len: usize,
    pub digest: [u8; 8],
}
#[derive(Clone, Debug)]
pub(crate) struct NodeRef {
    pub page: PageRef,
    pub first: i64,
    pub last: i64,
    pub hist: Hist,
}
pub(crate) fn event_bytes(id: u64, e: &[Event]) -> Vec<u8> {
    let mut b = vec![0; 64 + 16 * e.len()];
    b[..4].copy_from_slice(b"XYOE");
    b[4..8].copy_from_slice(&1u32.to_le_bytes());
    b[8..16].copy_from_slice(&id.to_le_bytes());
    b[16..20].copy_from_slice(&(e.len() as u32).to_le_bytes());
    for (i, e) in e.iter().enumerate() {
        let p = 64 + i * 16;
        b[p..p + 8].copy_from_slice(&e.time.to_le_bytes());
        b[p + 8..p + 10].copy_from_slice(&e.cell.to_le_bytes());
        b[p + 10] = u8::from(e.end);
    }
    b
}
pub(crate) fn events(b: &[u8], r: PageRef) -> Result<Vec<Event>> {
    checked(b, r)?;
    if b.len() < 64
        || &b[..4] != b"XYOE"
        || u32at(b, 4) != 1
        || u64at(b, 8) != r.id
        || b[20..64].iter().any(|v| *v != 0)
    {
        return invalid();
    }
    let n = u32at(b, 16) as usize;
    if n == 0 || n > EVENTS || b.len() != 64 + n * 16 {
        return invalid();
    }
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        let p = 64 + i * 16;
        let cell = u16::from_le_bytes(b[p + 8..p + 10].try_into().unwrap());
        if cell >= 256 || b[p + 10] > 1 || b[p + 11..p + 16].iter().any(|v| *v != 0) {
            return invalid();
        }
        out.push(Event {
            time: i64at(b, p),
            cell,
            end: b[p + 10] == 1,
        });
    }
    if out.windows(2).any(|w| w[0] > w[1]) {
        return invalid();
    }
    Ok(out)
}
pub(crate) fn checked(b: &[u8], r: PageRef) -> Result<()> {
    if b.len() != r.len || b.len() > PAGE || digest(b) != r.digest {
        return invalid();
    }
    Ok(())
}
pub(crate) fn leaf(r: PageRef, e: &[Event]) -> Result<NodeRef> {
    let mut hist = [0; 512];
    for e in e {
        let i = e.cell as usize + usize::from(e.end) * 256;
        hist[i] = plus(hist[i], 1)?;
    }
    Ok(NodeRef {
        page: r,
        first: e.first().ok_or(SourceError::InvalidFrame)?.time,
        last: e.last().ok_or(SourceError::InvalidFrame)?.time,
        hist,
    })
}
pub(crate) fn node_bytes(id: u64, c: &[NodeRef]) -> Vec<u8> {
    let mut b = vec![0; 64 + c.len() * CHILD];
    b[..4].copy_from_slice(b"XYON");
    b[4..8].copy_from_slice(&1u32.to_le_bytes());
    b[8..16].copy_from_slice(&id.to_le_bytes());
    b[16..20].copy_from_slice(&(c.len() as u32).to_le_bytes());
    for (i, c) in c.iter().enumerate() {
        let p = 64 + i * CHILD;
        b[p..p + 8].copy_from_slice(&c.page.id.to_le_bytes());
        b[p + 8..p + 16].copy_from_slice(&(c.page.len as u64).to_le_bytes());
        b[p + 16..p + 24].copy_from_slice(&c.page.digest);
        b[p + 24..p + 32].copy_from_slice(&c.first.to_le_bytes());
        b[p + 32..p + 40].copy_from_slice(&c.last.to_le_bytes());
        for (j, n) in c.hist.iter().enumerate() {
            b[p + 48 + j * 8..p + 56 + j * 8].copy_from_slice(&n.to_le_bytes());
        }
    }
    b
}
pub(crate) fn children(b: &[u8], r: PageRef) -> Result<Vec<NodeRef>> {
    checked(b, r)?;
    if b.len() < 64
        || &b[..4] != b"XYON"
        || u32at(b, 4) != 1
        || u64at(b, 8) != r.id
        || b[20..64].iter().any(|v| *v != 0)
    {
        return invalid();
    }
    let n = u32at(b, 16) as usize;
    if n == 0 || n > FANOUT || b.len() != 64 + n * CHILD {
        return invalid();
    }
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        let p = 64 + i * CHILD;
        let len = usize::try_from(u64at(b, p + 8)).map_err(|_| SourceError::ResourceLimit)?;
        let first = i64at(b, p + 24);
        let last = i64at(b, p + 32);
        if len < 64 || len > PAGE || first > last || b[p + 40..p + 48].iter().any(|x| *x != 0) {
            return invalid();
        }
        let mut hist = [0; 512];
        for (j, v) in hist.iter_mut().enumerate() {
            *v = u64at(b, p + 48 + j * 8)
        }
        out.push(NodeRef {
            page: PageRef {
                id: u64at(b, p),
                len,
                digest: b[p + 16..p + 24].try_into().unwrap(),
            },
            first,
            last,
            hist,
        });
    }
    if out.windows(2).any(|w| w[0].last > w[1].first) {
        return invalid();
    }
    Ok(out)
}
pub(crate) fn parent(r: PageRef, c: &[NodeRef]) -> Result<NodeRef> {
    let mut hist = [0; 512];
    for c in c {
        for (i, n) in c.hist.iter().enumerate() {
            hist[i] = plus(hist[i], *n)?;
        }
    }
    Ok(NodeRef {
        page: r,
        first: c[0].first,
        last: c[c.len() - 1].last,
        hist,
    })
}
pub(crate) fn u64at(b: &[u8], p: usize) -> u64 {
    u64::from_le_bytes(b[p..p + 8].try_into().unwrap())
}
pub(crate) fn i64at(b: &[u8], p: usize) -> i64 {
    i64::from_le_bytes(b[p..p + 8].try_into().unwrap())
}
pub(crate) fn u32at(b: &[u8], p: usize) -> u32 {
    u32::from_le_bytes(b[p..p + 4].try_into().unwrap())
}
/// Exact private authority. An owning ticket keeps its anticipated host-copy credit.
#[derive(Clone, Debug)]
pub struct GeoOverviewTicket {
    pub(crate) owner: u64,
    pub(crate) namespace: u64,
    pub(crate) serial: u64,
    pub(crate) kind: u8,
    pub(crate) page: PageRef,
    pub(crate) source: Option<crate::geo_source::ReadRequest>,
    pub(crate) _credit: Arc<GeoProcessorLease>,
}
impl GeoOverviewTicket {
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
        self.page.id
    }
    pub fn encoded_bytes(&self) -> usize {
        self.page.len
    }
    pub fn digest(&self) -> [u8; 8] {
        self.page.digest
    }
    pub fn source_request(&self) -> Option<crate::geo_source::ReadRequest> {
        self.source
    }
    pub(crate) fn same(&self, b: &Self) -> bool {
        self.owner == b.owner
            && self.namespace == b.namespace
            && self.source.map(|r| {
                (
                    r.generation,
                    r.chunk_index,
                    r.first_row,
                    r.rows,
                    r.encoded_bytes,
                    r.digest,
                )
            }) == b.source.map(|r| {
                (
                    r.generation,
                    r.chunk_index,
                    r.first_row,
                    r.rows,
                    r.encoded_bytes,
                    r.digest,
                )
            })
            && self.serial == b.serial
            && self.kind == b.kind
            && self.page == b.page
    }
}
pub(crate) fn ticket(
    owner: u64,
    serial: u64,
    kind: u8,
    page: PageRef,
    source: Option<crate::geo_source::ReadRequest>,
) -> Result<GeoOverviewTicket> {
    let bytes = page
        .len
        .checked_mul(if kind == 1 { 6 } else { 4 })
        .and_then(|n| n.checked_add(65_536))
        .ok_or(SourceError::ResourceLimit)?;
    Ok(GeoOverviewTicket {
        owner,
        namespace: owner,
        serial,
        kind,
        page,
        source,
        _credit: Arc::new(GeoProcessorLease::acquire(bytes)?),
    })
}
#[derive(Clone, Debug)]
pub enum GeoOverviewStep {
    NeedRead(GeoOverviewTicket),
    NeedWrite(GeoOverviewTicket),
    AwaitRelease,
    Complete,
    Cancelled,
    UnsupportedDomain,
}
/// Only authenticated canonical rebuild constructs this capability.
pub struct ValidatedGeoOverview {
    pub(crate) source: GeoSourceManifest,
    pub(crate) root: Option<NodeRef>,
    pub(crate) baseline: [u64; 256],
    pub(crate) all: [u64; 256],
    pub(crate) digest: [u8; 8],
    pub(crate) namespace: u64,
    pub(crate) _credit: GeoProcessorLease,
}
impl ValidatedGeoOverview {
    pub fn source(&self) -> &GeoSourceManifest {
        &self.source
    }
    pub fn digest(&self) -> [u8; 8] {
        self.digest
    }
    pub fn storage_namespace(&self) -> u64 {
        self.namespace
    }
}
pub(crate) fn overview_digest(
    source: &GeoSourceManifest,
    root: &Option<NodeRef>,
    baseline: &[u64; 256],
    all: &[u64; 256],
) -> [u8; 8] {
    let mut h = Blake2s8::new();
    h.update(b"xyg-overview-root-v1");
    h.update(&source.digest());
    h.update(&source.generation().to_le_bytes());
    if let Some(r) = root {
        h.update(&r.page.digest)
    }
    for v in baseline.iter().chain(all) {
        h.update(&v.to_le_bytes())
    }
    h.finish()
}
/// Counts are complete data-space domain-cell counts, not screen-bin centroids.
pub struct GeoOverviewResult {
    snapshot: GeoOperationSnapshot,
    overview_digest: [u8; 8],
    temporal_exact: bool,
    data_space: bool,
    final_result: bool,
    counts: [u64; 256],
    index: Arc<ValidatedGeoOverview>,
    _credit: GeoProcessorLease,
}
impl GeoOverviewResult {
    pub fn snapshot(&self) -> GeoOperationSnapshot {
        self.snapshot
    }
    pub fn overview_digest(&self) -> [u8; 8] {
        self.overview_digest
    }
    pub fn temporal_exact(&self) -> bool {
        self.temporal_exact
    }
    pub fn data_space(&self) -> bool {
        self.data_space
    }
    pub fn final_result(&self) -> bool {
        self.final_result
    }
    pub fn source(&self) -> &GeoSourceManifest {
        self.index.source()
    }
    pub fn counts(&self) -> &[u64; 256] {
        &self.counts
    }
}
struct Prefix {
    threshold: i64,
    inclusive: bool,
    end: bool,
    next: Option<NodeRef>,
    sum: [u64; 256],
}
pub struct GeoOverviewQuerySession {
    index: Arc<ValidatedGeoOverview>,
    snapshot: GeoOperationSnapshot,
    prefixes: Vec<Prefix>,
    at: usize,
    pending: Option<(GeoOverviewTicket, bool)>,
    serial: u64,
    owner: u64,
    cancelled: bool,
    failed: bool,
    result: Option<GeoOverviewResult>,
    _credit: GeoProcessorLease,
}
impl GeoOverviewQuerySession {
    pub fn new(
        index: Arc<ValidatedGeoOverview>,
        snapshot: GeoOperationSnapshot,
        camera: GeoViewport,
    ) -> Result<Self> {
        snapshot.time.validate()?;
        if snapshot.source_digest != index.source.digest()
            || snapshot.generation != index.source.generation()
            || snapshot.camera != camera.rebuild_key()?
        {
            return Err(SourceError::StaleSource.into());
        }
        let _credit = GeoProcessorLease::acquire(262_144)?;
        let args = match snapshot.time {
            TimePredicate::All => vec![],
            TimePredicate::Instant(t) => vec![(t, true, false), (t, true, true)],
            TimePredicate::Window { start, end } => vec![(end, false, false), (start, true, true)],
        };
        let prefixes = args
            .into_iter()
            .map(|(threshold, inclusive, end)| Prefix {
                threshold,
                inclusive,
                end,
                next: index.root.clone(),
                sum: [0; 256],
            })
            .collect();
        Ok(Self {
            index,
            snapshot,
            prefixes,
            at: 0,
            pending: None,
            serial: 0,
            owner: next_session_identity()?,
            cancelled: false,
            failed: false,
            result: None,
            _credit,
        })
    }
    pub fn step(&mut self) -> Result<GeoOverviewStep> {
        if self.pending.is_some() {
            return Ok(GeoOverviewStep::AwaitRelease);
        }
        if self.cancelled {
            return Ok(GeoOverviewStep::Cancelled);
        }
        if self.failed {
            return invalid();
        }
        if self.result.is_some() {
            return Ok(GeoOverviewStep::Complete);
        }
        while self.at < self.prefixes.len() {
            let p = &mut self.prefixes[self.at];
            if let Some(node) = p.next.as_ref() {
                let below = |t| t < p.threshold || (p.inclusive && t == p.threshold);
                if below(node.last) {
                    for i in 0..256 {
                        p.sum[i] = plus(p.sum[i], node.hist[i + usize::from(p.end) * 256])?;
                    }
                    p.next = None;
                    continue;
                }
                if !below(node.first) {
                    p.next = None;
                    continue;
                }
                // Do not consume the boundary node or serial until admission succeeds.
                let serial = plus(self.serial, 1)?;
                let mut t = ticket(self.owner, serial, 2, node.page, None)?;
                t.namespace = self.index.namespace;
                self.serial = serial;
                self.pending = Some((t.clone(), false));
                return Ok(GeoOverviewStep::NeedRead(t));
            }
            self.at += 1;
        }
        let mut counts = self.index.all;
        if !self.prefixes.is_empty() {
            for (i, n) in counts.iter_mut().enumerate() {
                *n = plus(self.index.baseline[i], self.prefixes[0].sum[i])?
                    .checked_sub(self.prefixes[1].sum[i])
                    .ok_or(SourceError::InvalidFrame)?;
            }
        }
        let credit = GeoProcessorLease::acquire(16_384)?;
        self.result = Some(GeoOverviewResult {
            snapshot: self.snapshot,
            overview_digest: self.index.digest,
            temporal_exact: true,
            data_space: true,
            final_result: false,
            counts,
            index: Arc::clone(&self.index),
            _credit: credit,
        });
        Ok(GeoOverviewStep::Complete)
    }
    pub fn supply(&mut self, t: &GeoOverviewTicket, b: &[u8]) -> Result<()> {
        let (p, accepted) = self.pending.as_ref().ok_or(SourceError::StaleSource)?;
        if !t.same(p) || *accepted || self.cancelled {
            return Err(SourceError::StaleSource.into());
        }
        let result = self.consume(t, b);
        if result.is_err() {
            self.failed = true;
        } else if let Some(p) = self.pending.as_mut() {
            p.1 = true;
        }
        result
    }
    fn consume(&mut self, t: &GeoOverviewTicket, b: &[u8]) -> Result<()> {
        let p = &mut self.prefixes[self.at];
        let node = p.next.take().ok_or(SourceError::InvalidFrame)?;
        checked(b, t.page)?;
        let below = |v| v < p.threshold || (p.inclusive && v == p.threshold);
        if b.starts_with(b"XYOE") {
            let e = events(b, t.page)?;
            let check = leaf(t.page, &e)?;
            if check.hist != node.hist || check.first != node.first || check.last != node.last {
                return invalid();
            }
            for e in e {
                if below(e.time) && e.end == p.end {
                    p.sum[e.cell as usize] = plus(p.sum[e.cell as usize], 1)?;
                }
            }
        } else {
            let c = children(b, t.page)?;
            let check = parent(t.page, &c)?;
            if check.hist != node.hist || check.first != node.first || check.last != node.last {
                return invalid();
            }
            for c in c {
                if below(c.last) {
                    for i in 0..256 {
                        p.sum[i] = plus(p.sum[i], c.hist[i + usize::from(p.end) * 256])?
                    }
                } else if below(c.first) {
                    p.next = Some(c);
                    break;
                } else {
                    break;
                }
            }
        }
        Ok(())
    }
    pub fn release_read(&mut self, t: &GeoOverviewTicket) -> Result<()> {
        let (p, accepted) = self.pending.as_ref().ok_or(SourceError::StaleSource)?;
        if !t.same(p) || (!*accepted && !self.cancelled && !self.failed) {
            return Err(SourceError::StaleSource.into());
        }
        self.pending = None;
        Ok(())
    }
    pub fn cancel(&mut self) {
        self.cancelled = true;
        self.result = None;
    }
    pub fn take_result(&mut self) -> Result<GeoOverviewResult> {
        if self.cancelled || self.failed || self.pending.is_some() {
            return Err(SourceError::Cancelled.into());
        }
        self.result.take().ok_or(SourceError::InvalidFrame.into())
    }
}
