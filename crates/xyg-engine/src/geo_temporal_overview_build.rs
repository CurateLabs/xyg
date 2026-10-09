//! Resumable external sort and authenticated overview publication (§17/§27/§28).
use super::geo_temporal_overview::*;
use crate::geo::GeoGeometry;
use crate::geo_source::{
    GeoChunk, GeoSourceManifest, MAX_CHUNK_PEAK, QueryBudget, SourceError, parse_authenticated,
};
use crate::geo_source_session::{GeoProcessorLease, next_session_identity};
use crate::geo_spatial_index::{GeoSpatialOptions, cell};
use std::sync::Arc;
const RUN_EVENTS: usize = 262_144;
const MAX_PAGES: usize = 524_288;
const MAX_RUNS: usize = 16_384;
#[derive(Clone, Copy)]
struct Run {
    start: usize,
    end: usize,
}
struct Head {
    run: Run,
    next: usize,
    events: Vec<Event>,
    at: usize,
}
#[derive(Clone, Copy, PartialEq)]
enum Phase {
    Source,
    Merge,
    Tree,
    Ready,
}
enum WriteAction {
    Run,
    Node(usize, Box<NodeRef>),
}
enum ReadAction {
    Source,
    Merge(usize),
    Tree,
}
struct PendingRead {
    ticket: GeoOverviewTicket,
    action: ReadAction,
    accepted: bool,
}
struct PendingWrite {
    bytes: Vec<u8>,
    ticket: GeoOverviewTicket,
    action: WriteAction,
}
pub struct GeoOverviewBuildSession {
    source: Option<GeoSourceManifest>,
    budget: QueryBudget,
    owner: u64,
    serial: u64,
    next_id: u64,
    phase: Phase,
    chunk: usize,
    current: Option<GeoChunk>,
    current_credit: Option<Arc<GeoProcessorLease>>,
    row: usize,
    vertex: usize,
    point_vertex: usize,
    events: Vec<Event>,
    flush_at: usize,
    flushing: bool,
    run_start: usize,
    runs: Vec<Run>,
    pages: Vec<PageRef>,
    next_runs: Vec<Run>,
    next_pages: Vec<PageRef>,
    group: usize,
    heads: Vec<Head>,
    output: Vec<Event>,
    tree_at: usize,
    levels: Vec<Vec<NodeRef>>,
    node_ready: Option<(usize, NodeRef)>,
    baseline: [u64; 256],
    all: [u64; 256],
    vertices: u64,
    vertex_limit: u64,
    read_bytes: u64,
    expected: Option<[u8; 8]>,
    pending_read: Option<PendingRead>,
    pending_write: Option<PendingWrite>,
    cancelled: bool,
    failed: bool,
    overflow: bool,
    published: Option<Arc<ValidatedGeoOverview>>,
    credit: Option<GeoProcessorLease>,
    base_bytes: usize,
}
impl GeoOverviewBuildSession {
    pub fn new(source: &GeoSourceManifest, budget: QueryBudget, max_vertices: u64) -> Result<Self> {
        Self::create(source, budget, max_vertices, None)
    }
    /// Semantic import verification re-authenticates every canonical chunk and rebuilds every sorted page.
    /// A matching checksum alone never constructs a trusted overview capability.
    pub fn verify(
        source: &GeoSourceManifest,
        budget: QueryBudget,
        max_vertices: u64,
        expected: [u8; 8],
    ) -> Result<Self> {
        Self::create(source, budget, max_vertices, Some(expected))
    }
    fn create(
        source: &GeoSourceManifest,
        budget: QueryBudget,
        max_vertices: u64,
        expected: Option<[u8; 8]>,
    ) -> Result<Self> {
        budget.validate()?;
        if !matches!(
            source.geometry(),
            GeoGeometry::Point | GeoGeometry::MultiPoint
        ) {
            return invalid();
        }
        if source.rows() > budget.max_rows_examined
            || source.chunks().len() > budget.max_chunks
            || max_vertices == 0
            || max_vertices > 2_000_000_000
        {
            return limit();
        }
        let base = source
            .clone_reserved_bytes()
            .checked_add(2 * MAX_PAGES * 32 + 2 * MAX_RUNS * 16 + RUN_EVENTS * 16 + 4_194_304)
            .ok_or(SourceError::ResourceLimit)?;
        if base > budget.processor_bytes {
            return limit();
        }
        let credit = GeoProcessorLease::acquire(base)?;
        // The declared work ceiling is independently enforced per emitted source vertex.
        let mut s = Self {
            source: Some(source.clone_validated()),
            budget,
            owner: next_session_identity()?,
            serial: 0,
            next_id: 0,
            phase: Phase::Source,
            chunk: 0,
            current: None,
            current_credit: None,
            row: 0,
            vertex: 0,
            point_vertex: 0,
            events: Vec::with_capacity(RUN_EVENTS),
            flush_at: 0,
            flushing: false,
            run_start: 0,
            runs: Vec::with_capacity(MAX_RUNS),
            pages: Vec::with_capacity(MAX_PAGES),
            next_runs: Vec::with_capacity(MAX_RUNS),
            next_pages: Vec::with_capacity(MAX_PAGES),
            group: 0,
            heads: Vec::with_capacity(FANOUT),
            output: Vec::with_capacity(EVENTS),
            tree_at: 0,
            levels: (0..LEVELS).map(|_| Vec::with_capacity(FANOUT)).collect(),
            node_ready: None,
            baseline: [0; 256],
            all: [0; 256],
            vertices: 0,
            vertex_limit: max_vertices,
            read_bytes: 0,
            expected,
            pending_read: None,
            pending_write: None,
            cancelled: false,
            failed: false,
            overflow: false,
            published: None,
            credit: Some(credit),
            base_bytes: base,
        };
        // Store max_vertices without widening the schema's row ceiling.
        s.vertex_limit = max_vertices;
        Ok(s)
    }
    pub fn storage_namespace(&self) -> u64 {
        self.owner
    }
    pub fn reserved_bytes(&self) -> usize {
        self.credit.as_ref().map_or(0, GeoProcessorLease::bytes)
    }
    pub fn step(&mut self) -> Result<GeoOverviewStep> {
        self.step_with_cancel(&mut || false)
    }
    pub fn step_with_cancel(
        &mut self,
        cancel: &mut dyn FnMut() -> bool,
    ) -> Result<GeoOverviewStep> {
        if cancel() {
            self.cancel()
        }
        if let Some(p) = &self.pending_write {
            return Ok(if self.cancelled || self.failed {
                GeoOverviewStep::AwaitRelease
            } else {
                GeoOverviewStep::NeedWrite(p.ticket.clone())
            });
        }
        if let Some(p) = &self.pending_read {
            return Ok(if p.accepted || self.cancelled || self.failed {
                GeoOverviewStep::AwaitRelease
            } else {
                GeoOverviewStep::NeedRead(p.ticket.clone())
            });
        }
        if self.cancelled {
            return Ok(GeoOverviewStep::Cancelled);
        }
        if self.overflow {
            return Ok(GeoOverviewStep::UnsupportedDomain);
        }
        if self.failed {
            return invalid();
        }
        let r = self.advance(cancel);
        if r.is_err() {
            self.failed = true
        }
        r
    }
    fn advance(&mut self, cancel: &mut dyn FnMut() -> bool) -> Result<GeoOverviewStep> {
        loop {
            if cancel() {
                self.cancel();
                return Ok(GeoOverviewStep::Cancelled);
            }
            if let Some((level, node)) = self.node_ready.take() {
                if level >= LEVELS {
                    return limit();
                }
                self.levels[level].push(node);
            }
            if let Some(level) = self.levels.iter().position(|v| v.len() == FANOUT) {
                return self.write_node(level);
            }
            match self.phase {
                Phase::Ready => return Ok(GeoOverviewStep::Complete),
                Phase::Source => {
                    if self.flushing {
                        if self.flush_at < self.events.len() {
                            let end = (self.flush_at + EVENTS).min(self.events.len());
                            let id = self.id()?;
                            let bytes = event_bytes(id, &self.events[self.flush_at..end]);
                            self.flush_at = end;
                            return self.write(bytes, WriteAction::Run);
                        }
                        self.push_run()?;
                        self.events.clear();
                        self.flushing = false;
                        self.flush_at = 0;
                        continue;
                    }
                    if self.events.len() + 2 > RUN_EVENTS {
                        self.sort_run();
                        continue;
                    }
                    if self.current.is_some() {
                        if self.feed_one()? {
                            continue;
                        }
                        self.current = None;
                        self.current_credit = None;
                        self.chunk += 1;
                        self.row = 0;
                        self.vertex = 0;
                        self.point_vertex = 0;
                        continue;
                    }
                    let source = self.source.as_ref().unwrap();
                    if self.chunk < source.chunks().len() {
                        let request = source.read_request(self.chunk)?;
                        let page = PageRef {
                            id: self.chunk as u64,
                            len: request.encoded_bytes,
                            digest: request.digest,
                        };
                        return self.read(page, 1, Some(request), ReadAction::Source);
                    }
                    if !self.events.is_empty() {
                        self.sort_run();
                        continue;
                    }
                    self.phase = Phase::Merge;
                }
                Phase::Merge => {
                    if self.runs.len() <= 1 {
                        self.phase = Phase::Tree;
                        self.tree_at = 0;
                        continue;
                    }
                    if self.heads.is_empty() {
                        if self.group == self.runs.len() {
                            self.pages.clear();
                            self.runs.clear();
                            std::mem::swap(&mut self.pages, &mut self.next_pages);
                            std::mem::swap(&mut self.runs, &mut self.next_runs);
                            self.group = 0;
                            continue;
                        }
                        self.run_start = self.next_pages.len();
                        let end = (self.group + FANOUT).min(self.runs.len());
                        for run in &self.runs[self.group..end] {
                            self.heads.push(Head {
                                run: *run,
                                next: run.start,
                                events: Vec::new(),
                                at: 0,
                            })
                        }
                        self.group = end;
                    }
                    for i in 0..self.heads.len() {
                        let h = &self.heads[i];
                        if h.at == h.events.len() && h.next < h.run.end {
                            return self.read(self.pages[h.next], 2, None, ReadAction::Merge(i));
                        }
                    }
                    if self.output.len() == EVENTS {
                        let id = self.id()?;
                        let bytes = event_bytes(id, &self.output);
                        self.output.clear();
                        return self.write(bytes, WriteAction::Run);
                    }
                    let chosen = self
                        .heads
                        .iter()
                        .enumerate()
                        .filter(|(_, h)| h.at < h.events.len())
                        .min_by_key(|(_, h)| h.events[h.at])
                        .map(|(i, _)| i);
                    if let Some(i) = chosen {
                        let h = &mut self.heads[i];
                        self.output.push(h.events[h.at]);
                        h.at += 1;
                        continue;
                    }
                    if !self.output.is_empty() {
                        let id = self.id()?;
                        let bytes = event_bytes(id, &self.output);
                        self.output.clear();
                        return self.write(bytes, WriteAction::Run);
                    }
                    if self.next_runs.len() == MAX_RUNS {
                        return limit();
                    }
                    self.next_runs.push(Run {
                        start: self.run_start,
                        end: self.next_pages.len(),
                    });
                    self.heads.clear();
                }
                Phase::Tree => {
                    if self.tree_at < self.pages.len() {
                        return self.read(self.pages[self.tree_at], 2, None, ReadAction::Tree);
                    }
                    let nonempty = self.levels.iter().filter(|x| !x.is_empty()).count();
                    if nonempty == 0 {
                        return self.publish(None, cancel);
                    }
                    let level = self.levels.iter().position(|x| !x.is_empty()).unwrap();
                    if nonempty == 1 && self.levels[level].len() == 1 {
                        let root = self.levels[level].pop();
                        return self.publish(root, cancel);
                    }
                    return self.write_node(level);
                }
            }
        }
    }
    fn feed_one(&mut self) -> Result<bool> {
        let c = self.current.as_ref().unwrap();
        let column = c.column();
        if self.row >= column.len() {
            return Ok(false);
        }
        let valid = column.validity()[self.row] == 1;
        let (a, z) = if column.geometry() == GeoGeometry::Point {
            (self.point_vertex, self.point_vertex + usize::from(valid))
        } else {
            (
                column.offsets0()[self.row] as usize,
                column.offsets0()[self.row + 1] as usize,
            )
        };
        self.vertex = self.vertex.max(a);
        if !valid || self.vertex >= z {
            if column.geometry() == GeoGeometry::Point {
                self.point_vertex = z;
            }
            self.row += 1;
            self.vertex = z;
            return Ok(true);
        }
        let xy = [
            column.xy()[2 * self.vertex],
            column.xy()[2 * self.vertex + 1],
        ];
        let index = cell(column.crs(), xy, GeoSpatialOptions { grid: 16 });
        if index == u32::MAX {
            self.overflow = true;
            return Err(GeoOverviewError::UnsupportedDomain);
        }
        self.vertices = plus(self.vertices, 1)?;
        if self.vertices > self.vertex_limit {
            return limit();
        }
        let index = index as usize;
        self.all[index] = plus(self.all[index], 1)?;
        let (start, end) = c.intervals().map_or((None, None), |t| {
            (
                if t.start_validity[self.row] == 1 {
                    Some(t.starts[self.row])
                } else {
                    None
                },
                if t.end_validity[self.row] == 1 {
                    Some(t.ends[self.row])
                } else {
                    None
                },
            )
        });
        if let Some(time) = start {
            self.events.push(Event {
                time,
                cell: index as u16,
                end: false,
            })
        } else {
            self.baseline[index] = plus(self.baseline[index], 1)?
        }
        if let Some(time) = end {
            self.events.push(Event {
                time,
                cell: index as u16,
                end: true,
            })
        }
        self.vertex += 1;
        Ok(true)
    }
    fn sort_run(&mut self) {
        self.events.sort_unstable();
        self.flushing = true;
        self.flush_at = 0;
        self.run_start = self.pages.len();
    }
    fn push_run(&mut self) -> Result<()> {
        if self.runs.len() == MAX_RUNS {
            return limit();
        }
        self.runs.push(Run {
            start: self.run_start,
            end: self.pages.len(),
        });
        Ok(())
    }
    fn id(&mut self) -> Result<u64> {
        let id = self.next_id;
        self.next_id = plus(id, 1)?;
        Ok(id)
    }
    fn read(
        &mut self,
        page: PageRef,
        kind: u8,
        source: Option<crate::geo_source::ReadRequest>,
        action: ReadAction,
    ) -> Result<GeoOverviewStep> {
        let total = plus(self.read_bytes, page.len as u64)?;
        if total > self.budget.max_read_bytes {
            return limit();
        }
        let needed = page
            .len
            .checked_mul(if kind == 1 { 6 } else { 4 })
            .and_then(|n| n.checked_add(65_536))
            .ok_or(SourceError::ResourceLimit)?;
        if self
            .base_bytes
            .checked_add(self.current_credit.as_ref().map_or(0, |c| c.bytes()))
            .and_then(|n| n.checked_add(needed))
            .is_none_or(|n| n > self.budget.processor_bytes)
        {
            return limit();
        }
        self.serial = plus(self.serial, 1)?;
        let ticket = ticket(self.owner, self.serial, kind, page, source)?;
        self.read_bytes = total;
        self.pending_read = Some(PendingRead {
            ticket: ticket.clone(),
            action,
            accepted: false,
        });
        Ok(GeoOverviewStep::NeedRead(ticket))
    }
    fn write(&mut self, bytes: Vec<u8>, action: WriteAction) -> Result<GeoOverviewStep> {
        if matches!(action, WriteAction::Run)
            && (if self.phase == Phase::Source {
                self.pages.len()
            } else {
                self.next_pages.len()
            }) >= MAX_PAGES
        {
            self.failed = true;
            return limit();
        }
        if bytes.capacity() > PAGE
            || self
                .base_bytes
                .checked_add(self.current_credit.as_ref().map_or(0, |c| c.bytes()))
                .and_then(|n| n.checked_add(bytes.len() * 4 + 65_536))
                .is_none_or(|n| n > self.budget.processor_bytes)
        {
            return limit();
        }
        self.serial = plus(self.serial, 1)?;
        let page = PageRef {
            id: u64at(&bytes, 8),
            len: bytes.len(),
            digest: digest(&bytes),
        };
        let t = ticket(self.owner, self.serial, 3, page, None)?;
        self.pending_write = Some(PendingWrite {
            bytes,
            ticket: t.clone(),
            action,
        });
        Ok(GeoOverviewStep::NeedWrite(t))
    }
    fn write_node(&mut self, level: usize) -> Result<GeoOverviewStep> {
        let id = self.id()?;
        let c = std::mem::replace(&mut self.levels[level], Vec::with_capacity(FANOUT));
        let bytes = node_bytes(id, &c);
        let page = PageRef {
            id,
            len: bytes.len(),
            digest: digest(&bytes),
        };
        let node = parent(page, &c)?;
        self.write(bytes, WriteAction::Node(level + 1, Box::new(node)))
    }
    pub fn write_bytes(&self, t: &GeoOverviewTicket) -> Result<&[u8]> {
        let p = self
            .pending_write
            .as_ref()
            .ok_or(SourceError::StaleSource)?;
        if !p.ticket.same(t) {
            return Err(SourceError::StaleSource.into());
        }
        Ok(&p.bytes)
    }
    pub fn ack_write(&mut self, t: &GeoOverviewTicket) -> Result<()> {
        let p = self
            .pending_write
            .as_ref()
            .ok_or(SourceError::StaleSource)?;
        if !p.ticket.same(t) {
            return Err(SourceError::StaleSource.into());
        }
        let p = self.pending_write.take().unwrap();
        if !self.cancelled && !self.failed {
            match p.action {
                WriteAction::Run => {
                    let target = if self.phase == Phase::Source {
                        &mut self.pages
                    } else {
                        &mut self.next_pages
                    };
                    if target.len() >= MAX_PAGES {
                        self.failed = true;
                        return limit();
                    }
                    target.push(p.ticket.page)
                }
                WriteAction::Node(level, node) => self.node_ready = Some((level, *node)),
            }
        }
        Ok(())
    }
    pub fn supply(&mut self, t: &GeoOverviewTicket, b: &[u8]) -> Result<()> {
        let p = self.pending_read.as_ref().ok_or(SourceError::StaleSource)?;
        if !t.same(&p.ticket) || p.accepted || self.cancelled {
            return Err(SourceError::StaleSource.into());
        }
        let r = self.consume(b);
        if r.is_err() {
            self.failed = true
        } else if let Some(p) = self.pending_read.as_mut() {
            p.accepted = true
        }
        r
    }
    fn consume(&mut self, b: &[u8]) -> Result<()> {
        let p = self.pending_read.as_ref().unwrap();
        match p.action {
            ReadAction::Source => {
                if b.len() != p.ticket.page.len {
                    return invalid();
                }
                let peak = (p.ticket.page.len * 6 + 65_536).min(MAX_CHUNK_PEAK);
                self.current = Some(parse_authenticated(p.ticket.source.unwrap(), b, peak)?);
                self.current_credit = Some(Arc::clone(&p.ticket._credit));
            }
            ReadAction::Merge(i) => {
                let e = events(b, p.ticket.page)?;
                let h = &mut self.heads[i];
                if let Some(last) = h.events.last() {
                    if e[0] < *last {
                        return invalid();
                    }
                }
                h.events = e;
                h.at = 0;
                h.next += 1;
            }
            ReadAction::Tree => {
                let e = events(b, p.ticket.page)?;
                self.node_ready = Some((0, leaf(p.ticket.page, &e)?));
                self.tree_at += 1;
            }
        }
        Ok(())
    }
    pub fn release_read(&mut self, t: &GeoOverviewTicket) -> Result<()> {
        let p = self.pending_read.as_ref().ok_or(SourceError::StaleSource)?;
        if !p.ticket.same(t) || (!p.accepted && !self.cancelled && !self.failed) {
            return Err(SourceError::StaleSource.into());
        }
        self.pending_read = None;
        Ok(())
    }
    pub fn cancel(&mut self) {
        self.cancelled = true;
        self.published = None;
    }
    fn publish(
        &mut self,
        root: Option<NodeRef>,
        cancel: &mut dyn FnMut() -> bool,
    ) -> Result<GeoOverviewStep> {
        let source = self.source.as_ref().unwrap();
        let digest = overview_digest(source, &root, &self.baseline, &self.all);
        if self.expected.is_some_and(|v| v != digest) {
            return invalid();
        }
        if cancel() {
            self.cancel();
            return Ok(GeoOverviewStep::Cancelled);
        }
        self.events = Vec::new();
        self.pages = Vec::new();
        self.next_pages = Vec::new();
        self.runs = Vec::new();
        self.next_runs = Vec::new();
        self.heads = Vec::new();
        self.output = Vec::new();
        self.levels = Vec::new();
        let mut credit = self.credit.take().unwrap();
        credit.resize(source.clone_reserved_bytes() + 16_384)?;
        self.published = Some(Arc::new(ValidatedGeoOverview {
            source: self.source.take().unwrap(),
            root,
            baseline: self.baseline,
            all: self.all,
            digest,
            namespace: self.owner,
            _credit: credit,
        }));
        self.phase = Phase::Ready;
        Ok(GeoOverviewStep::Complete)
    }
    pub fn take_index(&mut self) -> Result<Arc<ValidatedGeoOverview>> {
        if self.cancelled || self.failed || self.phase != Phase::Ready {
            return Err(SourceError::StaleSource.into());
        }
        self.published
            .take()
            .ok_or(SourceError::InvalidFrame.into())
    }
}
#[cfg(test)]
mod bounded_failure_tests {
    use super::*;
    use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoLimits};
    use crate::geo_source::GeoManifestBuilder;
    #[test]
    fn overview_write_page_limit_cannot_publish_after_failed_ack() {
        let _lock = crate::geo_source_session::test_processor_lock();
        let column = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg4326,
            xy: &[0., 0.],
            validity: &[1],
            feature_ids: Some(&[u64::MAX]),
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        let raw = GeoChunk::encode(&column, None).unwrap();
        let mut m = GeoManifestBuilder::new();
        m.push(&GeoChunk::parse(&raw, MAX_CHUNK_PEAK).unwrap())
            .unwrap();
        let source = m.finish(1).unwrap();
        let mut b = GeoOverviewBuildSession::new(&source, QueryBudget::default(), 100).unwrap();
        let bytes = event_bytes(
            0,
            &[Event {
                time: 0,
                cell: 136,
                end: false,
            }],
        );
        let GeoOverviewStep::NeedWrite(t) = b.write(bytes, WriteAction::Run).unwrap() else {
            panic!()
        };
        b.pages.resize(
            MAX_PAGES,
            PageRef {
                id: 0,
                len: 64,
                digest: [0; 8],
            },
        );
        assert!(matches!(
            b.ack_write(&t),
            Err(GeoOverviewError::Source(SourceError::ResourceLimit))
        ));
        assert!(b.step().is_err());
        assert!(b.take_index().is_err());
        drop(t);
        drop(b);
        let mut b = GeoOverviewBuildSession::new(&source, QueryBudget::default(), 100).unwrap();
        b.pages.resize(
            MAX_PAGES,
            PageRef {
                id: 0,
                len: 64,
                digest: [0; 8],
            },
        );
        assert!(
            b.write(
                event_bytes(
                    0,
                    &[Event {
                        time: 0,
                        cell: 136,
                        end: false
                    }]
                ),
                WriteAction::Run
            )
            .is_err()
        );
        assert!(b.step().is_err());
        assert!(b.take_index().is_err());
    }
}
