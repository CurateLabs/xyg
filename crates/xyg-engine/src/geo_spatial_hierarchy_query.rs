//! Exact source-order refinement over bounded authenticated hierarchy pages.
use crate::geo_lod::{GeoLodIdentity, GeoLodOptions, GeoLodPass, GeoPointLod, GeoPointResult};
use crate::geo_source::{SourceError, TimePredicate};
use crate::geo_source_session::GeoProcessorLease;
use crate::geo_spatial_hierarchy::*;
use crate::geo_spatial_index::Vertex;
use crate::geo_viewport::GeoViewport;
use std::{cmp::Reverse, collections::BinaryHeap, sync::Arc};
const CACHE_NODES: usize = 64;
#[derive(Clone, Copy, Debug)]
pub struct GeoHierarchyQueryLimits {
    pub processor_bytes: usize,
    pub directory_reads: u64,
    pub leaf_reads: u64,
    pub vertex_records: u64,
    pub read_bytes: u64,
}
impl Default for GeoHierarchyQueryLimits {
    fn default() -> Self {
        Self {
            processor_bytes: crate::geo_source::MAX_PROCESSOR_BYTES,
            directory_reads: 65_536,
            leaf_reads: 65_536,
            vertex_records: 200_000_000,
            read_bytes: 16 << 30,
        }
    }
}
#[derive(Clone, Copy, Debug, Default)]
pub struct GeoHierarchyQueryStats {
    pub directory_reads: u64,
    pub leaf_reads: u64,
    pub bytes_read: u64,
    pub vertex_records: u64,
    pub passes: u32,
    pub selected_cells: usize,
}
pub struct GeoHierarchyResult {
    pub result: GeoPointResult,
    pub stats: GeoHierarchyQueryStats,
    index: Arc<ValidatedGeoHierarchy>,
    credit: GeoProcessorLease,
}
impl GeoHierarchyResult {
    pub fn index(&self) -> &Arc<ValidatedGeoHierarchy> {
        &self.index
    }
    pub fn reserved_bytes(&self) -> usize {
        self.credit.bytes()
    }
}
struct Stream {
    root: Node,
    next: u64,
    buffer: Vec<Vertex>,
    at: usize,
}
#[derive(Clone, Copy)]
struct Locate {
    slot: usize,
    node: Node,
    ordinal: u64,
}
#[derive(Clone, Copy)]
enum Action {
    Plan(Node),
    Open(usize, Node),
    Locate(Locate),
    Data(usize, Node),
}
struct Pending {
    ticket: GeoHierarchyTicket,
    action: Action,
    accepted: bool,
}
#[derive(Clone, Copy, PartialEq)]
enum Phase {
    Plan,
    Run,
    Frontier,
    Work,
    Done,
}
/// Query fields are independent immutable authority; a future mutable host registry
/// must separately enforce publication sequences/revision transitions.
pub struct GeoHierarchyQuerySession {
    index: Arc<ValidatedGeoHierarchy>,
    camera: GeoViewport,
    bounds: Option<[f64; 4]>,
    time: TimePredicate,
    limits: GeoHierarchyQueryLimits,
    owner: u64,
    serial: u64,
    phase: Phase,
    stack: Vec<Node>,
    streams: Vec<Stream>,
    cache: Vec<(Node, Vec<Node>)>,
    locating: Option<Locate>,
    next_stream: usize,
    refill: Option<usize>,
    heap: BinaryHeap<Reverse<(u64, u32, usize)>>,
    pending: Option<Pending>,
    lod: Option<GeoPointLod>,
    stats: GeoHierarchyQueryStats,
    result: Option<GeoPointResult>,
    cancelled: bool,
    failed: bool,
    credit: Option<GeoProcessorLease>,
    base_bytes: usize,
}
impl GeoHierarchyQuerySession {
    #[expect(clippy::too_many_arguments)]
    pub fn new(
        index: Arc<ValidatedGeoHierarchy>,
        camera: GeoViewport,
        time: TimePredicate,
        options: GeoLodOptions,
        layer_id: u64,
        style_revision: u64,
        state_revision: u64,
        limits: GeoHierarchyQueryLimits,
    ) -> Result<Self> {
        camera.validate()?;
        time.validate()?;
        if limits.processor_bytes > crate::geo_source::MAX_PROCESSOR_BYTES
            || limits.directory_reads == 0
            || limits.leaf_reads == 0
            || limits.vertex_records == 0
            || limits.read_bytes == 0
        {
            return limit();
        }
        let base = GeoPointLod::reservation_bytes(options)?
            .checked_add(
                MAX_FRONTIER * (DATA_RECORDS * 128 + 512)
                    + CACHE_NODES * FANOUT * 128
                    + LEVELS * FANOUT * 128
                    + 262144,
            )
            .ok_or(SourceError::ResourceLimit)?;
        if base
            .checked_add(index.reserved_bytes())
            .is_none_or(|n| n > limits.processor_bytes)
        {
            return limit();
        }
        let credit = GeoProcessorLease::acquire(base)?;
        let identity = GeoLodIdentity {
            source_digest: index.source.digest(),
            generation: index.source.generation(),
            source_rows: index.source.rows(),
            crs: index.source.crs(),
            geometry: index.source.geometry(),
            layer_id,
            style_revision,
            state_revision,
        };
        let lod = GeoPointLod::new(identity, camera, time, options)?;
        let mut stack = Vec::with_capacity(LEVELS * FANOUT);
        if let Some(root) = index.root {
            stack.push(root);
        }
        Ok(Self {
            index,
            camera,
            bounds: camera.point_index_bounds()?,
            time,
            limits,
            owner: nonce()?,
            serial: 0,
            phase: Phase::Plan,
            stack,
            streams: Vec::with_capacity(MAX_FRONTIER),
            cache: Vec::with_capacity(CACHE_NODES),
            locating: None,
            next_stream: 0,
            refill: None,
            heap: BinaryHeap::with_capacity(MAX_FRONTIER),
            pending: None,
            lod: Some(lod),
            stats: GeoHierarchyQueryStats::default(),
            result: None,
            cancelled: false,
            failed: false,
            credit: Some(credit),
            base_bytes: base,
        })
    }
    pub fn reserved_bytes(&self) -> usize {
        self.credit.as_ref().map_or(0, GeoProcessorLease::bytes)
    }
    pub fn stats(&self) -> GeoHierarchyQueryStats {
        self.stats
    }
    pub fn has_outstanding_io(&self) -> bool {
        self.pending.is_some()
    }
    pub fn step(&mut self) -> Result<GeoHierarchyStep> {
        self.step_with_cancel(&mut || false)
    }
    pub fn step_with_cancel(
        &mut self,
        cancel: &mut dyn FnMut() -> bool,
    ) -> Result<GeoHierarchyStep> {
        if cancel() {
            self.cancel();
        }
        let result = self.advance(cancel);
        if result.is_err() {
            self.failed = true;
        }
        result
    }
    fn advance(&mut self, cancel: &mut dyn FnMut() -> bool) -> Result<GeoHierarchyStep> {
        if let Some(p) = &self.pending {
            return Ok(if p.accepted || self.failed || self.cancelled {
                GeoHierarchyStep::AwaitRelease
            } else {
                GeoHierarchyStep::NeedRead(p.ticket.clone())
            });
        }
        if self.failed || self.cancelled {
            return Ok(GeoHierarchyStep::Cancelled);
        }
        loop {
            if cancel() {
                self.cancel();
                return Ok(GeoHierarchyStep::Cancelled);
            }
            match self.phase {
                Phase::Frontier => return Ok(GeoHierarchyStep::FullScanFrontier),
                Phase::Work => return Ok(GeoHierarchyStep::FullScanWork),
                Phase::Done => return Ok(GeoHierarchyStep::Complete),
                Phase::Plan => {
                    if let Some(n) = self.stack.last().copied() {
                        if !n.time(self.time)
                            || !candidate(n, self.index.options, &self.camera, self.bounds)
                        {
                            self.stack.pop();
                            continue;
                        }
                        if n.kind == 3 {
                            if self.streams.len() == MAX_FRONTIER {
                                self.fallback(Phase::Frontier);
                                continue;
                            }
                            self.stack.pop();
                            self.streams.push(Stream {
                                root: n,
                                next: 0,
                                buffer: Vec::new(),
                                at: 0,
                            });
                            continue;
                        }
                        if n.kind != 4 {
                            return invalid();
                        }
                        if self.stats.directory_reads == self.limits.directory_reads {
                            self.fallback(Phase::Work);
                            continue;
                        }
                        return self.issue(n, Action::Plan(n));
                    }
                    let pages = self.streams.iter().try_fold(0u64, |sum, s| {
                        sum.checked_add(s.root.pages)
                            .ok_or(SourceError::ResourceLimit)
                    })?;
                    let records = self.streams.iter().try_fold(0u64, |sum, s| {
                        sum.checked_add(s.root.count)
                            .ok_or(SourceError::ResourceLimit)
                    })?;
                    if pages > self.limits.leaf_reads || records > self.limits.vertex_records {
                        self.fallback(Phase::Work);
                        continue;
                    }
                    self.stats.selected_cells = self.streams.len();
                    self.stats.passes = 1;
                    self.phase = Phase::Run;
                    continue;
                }
                Phase::Run => {
                    if let Some(l) = self.locating {
                        if !l.node.time(self.time) {
                            self.streams[l.slot].next += l.node.pages - l.ordinal;
                            self.locating = None;
                            continue;
                        }
                        if l.node.kind == 1 {
                            return self.issue(l.node, Action::Data(l.slot, l.node));
                        }
                        if l.node.kind != 2 {
                            return invalid();
                        }
                        if let Some(children) = self.cached(l.node) {
                            let chosen = Self::locate_child(&children, l.ordinal)?;
                            self.locating = Some(Locate {
                                slot: l.slot,
                                node: chosen.0,
                                ordinal: chosen.1,
                            });
                            continue;
                        }
                        return self.issue(l.node, Action::Locate(l));
                    }
                    if let Some(slot) = self.refill {
                        if self.streams[slot].at < self.streams[slot].buffer.len() {
                            self.push(slot);
                            self.refill = None;
                            continue;
                        }
                        if self.streams[slot].next == self.streams[slot].root.pages {
                            self.refill = None;
                            continue;
                        }
                        self.locating = Some(Locate {
                            slot,
                            node: self.streams[slot].root,
                            ordinal: self.streams[slot].next,
                        });
                        continue;
                    }
                    while self.next_stream < self.streams.len() {
                        let slot = self.next_stream;
                        if self.streams[slot].at < self.streams[slot].buffer.len() {
                            self.push(slot);
                            self.next_stream += 1;
                            continue;
                        }
                        if self.streams[slot].next == self.streams[slot].root.pages {
                            self.next_stream += 1;
                            continue;
                        }
                        let root = self.streams[slot].root;
                        if root.kind == 3 {
                            return self.issue(root, Action::Open(slot, root));
                        }
                        self.locating = Some(Locate {
                            slot,
                            node: root,
                            ordinal: self.streams[slot].next,
                        });
                        break;
                    }
                    if self.locating.is_some() {
                        continue;
                    }
                    if let Some(Reverse((_, _, slot))) = self.heap.pop() {
                        let stream = &mut self.streams[slot];
                        let v = stream.buffer[stream.at];
                        stream.at += 1;
                        self.stats.vertex_records = self
                            .stats
                            .vertex_records
                            .checked_add(1)
                            .ok_or(SourceError::ResourceLimit)?;
                        if self.stats.vertex_records > self.limits.vertex_records {
                            return limit();
                        }
                        self.lod
                            .as_mut()
                            .ok_or(SourceError::StaleSource)?
                            .fold_indexed_vertex(
                                v.identity, v.vertex, v.xy, v.start, v.end, cancel,
                            )?;
                        if stream.at < stream.buffer.len() {
                            self.push(slot);
                        } else {
                            self.refill = Some(slot);
                        }
                        continue;
                    }
                    if cancel() {
                        self.cancel();
                        return Ok(GeoHierarchyStep::Cancelled);
                    }
                    match self.lod.as_mut().unwrap().end_pass()? {
                        GeoLodPass::Repeat => {
                            if cancel() {
                                self.cancel();
                                return Ok(GeoHierarchyStep::Cancelled);
                            }
                            for s in &mut self.streams {
                                s.next = 0;
                                s.buffer = Vec::new();
                                s.at = 0;
                            }
                            self.next_stream = 0;
                            self.refill = None;
                            self.stats.passes += 1;
                            continue;
                        }
                        GeoLodPass::Finished => {
                            if cancel() {
                                self.cancel();
                                return Ok(GeoHierarchyStep::Cancelled);
                            }
                            let result = self.lod.take().unwrap().finish()?;
                            if cancel() {
                                self.cancel();
                                return Ok(GeoHierarchyStep::Cancelled);
                            }
                            self.result = Some(result);
                            self.phase = Phase::Done;
                            return Ok(GeoHierarchyStep::Complete);
                        }
                    }
                }
            }
        }
    }
    fn push(&mut self, slot: usize) {
        let stream = &self.streams[slot];
        let v = stream.buffer[stream.at];
        self.heap
            .push(Reverse((v.identity.source_row, v.vertex, slot)));
    }
    fn fallback(&mut self, phase: Phase) {
        self.phase = phase;
        self.stack = Vec::new();
        self.streams = Vec::new();
        self.lod = None;
        self.cache = Vec::new();
        self.heap = BinaryHeap::new();
    }
    fn cached(&mut self, n: Node) -> Option<Vec<Node>> {
        let at = self.cache.iter().position(|(old, _)| *old == n)?;
        let entry = self.cache.remove(at);
        let result = entry.1.clone();
        self.cache.push(entry);
        Some(result)
    }
    fn locate_child(children: &[Node], ordinal: u64) -> Result<(Node, u64)> {
        let mut remaining = ordinal;
        for &n in children {
            if remaining < n.pages {
                return Ok((n, remaining));
            }
            remaining -= n.pages;
        }
        invalid()
    }
    fn issue(&mut self, n: Node, action: Action) -> Result<GeoHierarchyStep> {
        let is_data = n.kind == 1;
        if (is_data && self.stats.leaf_reads == self.limits.leaf_reads)
            || (!is_data && self.stats.directory_reads == self.limits.directory_reads)
        {
            return limit();
        }
        let total = self
            .stats
            .bytes_read
            .checked_add(n.read.len as u64)
            .ok_or(SourceError::ResourceLimit)?;
        if total > self.limits.read_bytes {
            return limit();
        }
        let charge = n
            .read
            .len
            .checked_mul(4)
            .and_then(|n| n.checked_add(65536))
            .ok_or(SourceError::ResourceLimit)?;
        if self
            .base_bytes
            .checked_add(self.index.reserved_bytes())
            .and_then(|n| n.checked_add(charge))
            .is_none_or(|n| n > self.limits.processor_bytes)
        {
            return limit();
        }
        let serial = self
            .serial
            .checked_add(1)
            .ok_or(SourceError::ResourceLimit)?;
        let t = ticket(
            self.owner,
            self.index.namespace,
            serial,
            if is_data { 5 } else { 4 },
            n.read,
            None,
        )?;
        self.serial = serial;
        self.stats.bytes_read = total;
        if is_data {
            self.stats.leaf_reads += 1;
        } else {
            self.stats.directory_reads += 1;
        }
        self.pending = Some(Pending {
            ticket: t.clone(),
            action,
            accepted: false,
        });
        Ok(GeoHierarchyStep::NeedRead(t))
    }
    pub fn supply(&mut self, t: &GeoHierarchyTicket, b: &[u8]) -> Result<()> {
        let p = self.pending.as_ref().ok_or(SourceError::StaleSource)?;
        if !p.ticket.same(t) || p.accepted {
            return Err(SourceError::StaleSource);
        }
        let result = self.consume(b);
        if result.is_err() {
            self.failed = true;
        }
        self.pending.as_mut().unwrap().accepted = true;
        result
    }
    fn consume(&mut self, b: &[u8]) -> Result<()> {
        if self.failed || self.cancelled {
            return Err(SourceError::Cancelled);
        }
        let action = self.pending.as_ref().unwrap().action;
        match action {
            Action::Data(slot, n) => {
                let values = data(b, n, self.index.options.grid)?;
                if values
                    .iter()
                    .any(|v| v.identity.source_row >= self.index.source.rows())
                {
                    return invalid();
                }
                let stream = &mut self.streams[slot];
                stream.next += 1;
                stream.buffer = values;
                stream.at = 0;
                self.locating = None;
            }
            Action::Plan(n) => {
                let children = children(b, n, self.index.options.grid)?;
                if self.stack.last() != Some(&n)
                    || self.stack.len() - 1 + children.len() > LEVELS * FANOUT
                {
                    return invalid();
                }
                self.stack.pop();
                self.stack.extend(children.into_iter().rev());
            }
            Action::Open(slot, n) => {
                let children = children(b, n, self.index.options.grid)?;
                self.streams[slot].root = children[0];
            }
            Action::Locate(l) => {
                let children = children(b, l.node, self.index.options.grid)?;
                let (node, ordinal) = Self::locate_child(&children, l.ordinal)?;
                if self.cache.len() == CACHE_NODES {
                    self.cache.remove(0);
                }
                self.cache.push((l.node, children));
                self.locating = Some(Locate {
                    slot: l.slot,
                    node,
                    ordinal,
                });
            }
        }
        Ok(())
    }
    pub fn release_read(&mut self, t: &GeoHierarchyTicket) -> Result<()> {
        let p = self.pending.as_ref().ok_or(SourceError::StaleSource)?;
        if !p.ticket.same(t) || (!p.accepted && !self.failed && !self.cancelled) {
            return Err(SourceError::StaleSource);
        }
        self.pending = None;
        Ok(())
    }
    pub fn cancel(&mut self) {
        self.cancelled = true;
        self.result = None;
    }
    pub fn finish(&mut self) -> Result<GeoHierarchyResult> {
        if self.failed || self.cancelled || self.pending.is_some() {
            return Err(SourceError::Cancelled);
        }
        let result = self.result.take().ok_or(SourceError::StaleSource)?;
        self.streams = Vec::new();
        self.cache = Vec::new();
        self.stack = Vec::new();
        self.heap = BinaryHeap::new();
        let mut credit = self.credit.take().unwrap();
        credit.resize(GeoPointLod::output_bytes(&result) + 16384)?;
        Ok(GeoHierarchyResult {
            result,
            stats: self.stats,
            index: Arc::clone(&self.index),
            credit,
        })
    }
}
