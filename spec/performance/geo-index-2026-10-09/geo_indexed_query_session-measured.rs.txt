//! Exact bounded leaf-stream merge; native and asynchronous WASM share state.
use crate::geo_lod::{GeoLodIdentity, GeoLodOptions, GeoLodPass, GeoPointLod, GeoPointResult};
use crate::geo_source::{SourceError, TimePredicate};
use crate::geo_source_session::{GeoProcessorLease, next_session_identity};
use crate::geo_spatial_index::*;
use crate::geo_viewport::GeoViewport;
use std::{cmp::Reverse, collections::BinaryHeap, sync::Arc};
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoIndexDecision {
    Indexed,
    FullScanFrontier,
}
#[derive(Debug, Clone, Copy, Default)]
pub struct GeoIndexQueryStats {
    pub pages_read: u64,
    pub bytes_read: u64,
    pub candidate_vertices: u64,
    pub passes: u32,
}
pub struct GeoIndexedResult {
    pub result: GeoPointResult,
    pub stats: GeoIndexQueryStats,
    _lease: GeoProcessorLease,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoIndexedReadTicket {
    pub session: u64,
    pub pass: u32,
    pub request: GeoSpatialRead,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoIndexedQueryStep {
    NeedRead(GeoIndexedReadTicket),
    AwaitRelease(GeoIndexedReadTicket),
    Complete,
    Cancelled,
}
pub fn decision(
    index: &ValidatedGeoSpatialIndex,
    camera: &GeoViewport,
    time: TimePredicate,
) -> Result<GeoIndexDecision> {
    time.validate()?;
    let bounds = camera.point_index_bounds()?;
    let mut last = None;
    let mut count = 0;
    for p in &index.pages {
        if !p.time_matches(time) || !candidate(p.cell, index.options, camera, bounds) {
            continue;
        }
        if last != Some(p.cell) {
            count += 1;
            last = Some(p.cell);
        }
        if count > MAX_FRONTIER {
            return Ok(GeoIndexDecision::FullScanFrontier);
        }
    }
    Ok(GeoIndexDecision::Indexed)
}
struct Stream {
    first: usize,
    end: usize,
    next: usize,
    buffer: Vec<Vertex>,
    cursor: usize,
}
/// At most256 leaf page heads; original row/vertex order is merged by a bounded
/// heap. One frozen query and one borrowed read loan per session, no global mask.
pub struct GeoIndexedQuerySession {
    index: Arc<ValidatedGeoSpatialIndex>,
    time: TimePredicate,
    session: u64,
    streams: Vec<Stream>,
    next_stream: usize,
    heap: BinaryHeap<Reverse<(u64, u32, usize)>>,
    pending: Option<(usize, Page, bool)>,
    max_read_bytes: u64,
    lod: Option<GeoPointLod>,
    result: Option<GeoPointResult>,
    stats: GeoIndexQueryStats,
    cancelled: bool,
    failed: bool,
    lease: GeoProcessorLease,
}
impl GeoIndexedQuerySession {
    /// None explicitly requests canonical FullScanFrontier; never thin cells.
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        index: Arc<ValidatedGeoSpatialIndex>,
        camera: GeoViewport,
        time: TimePredicate,
        options: GeoLodOptions,
        layer_id: u64,
        style_revision: u64,
        state_revision: u64,
        max_read_bytes: u64,
    ) -> Result<Option<Self>> {
        if decision(&index, &camera, time)? == GeoIndexDecision::FullScanFrontier {
            return Ok(None);
        }
        let bounds = camera.point_index_bounds()?;
        let reserve = GeoPointLod::reservation_bytes(options)?
            .checked_add(
                MAX_FRONTIER
                    * (PAGE_RECORDS * std::mem::size_of::<Vertex>()
                        + std::mem::size_of::<Stream>()
                        + 32)
                    + 4 * PAGE_BYTES
                    + 16_384,
            )
            .ok_or(SourceError::ResourceLimit)?;
        if reserve > options.processor_bytes || max_read_bytes == 0 {
            return Err(SourceError::ResourceLimit);
        }
        let lease = GeoProcessorLease::acquire(reserve)?;
        let mut streams = Vec::with_capacity(MAX_FRONTIER);
        let mut a = 0;
        while a < index.pages.len() {
            let cell = index.pages[a].cell;
            let mut end = a + 1;
            while end < index.pages.len() && index.pages[end].cell == cell {
                end += 1;
            }
            if candidate(cell, index.options, &camera, bounds)
                && index.pages[a..end].iter().any(|p| p.time_matches(time))
            {
                streams.push(Stream {
                    first: a,
                    end,
                    next: a,
                    buffer: Vec::new(),
                    cursor: 0,
                });
            }
            a = end;
        }
        let lod = GeoPointLod::new(
            GeoLodIdentity {
                source_digest: index.source.digest(),
                generation: index.source.generation(),
                source_rows: index.source.rows(),
                crs: index.source.crs(),
                geometry: index.source.geometry(),
                layer_id,
                style_revision,
                state_revision,
            },
            camera,
            time,
            options,
        )?;
        Ok(Some(Self {
            index,
            time,
            session: next_session_identity()?,
            streams,
            next_stream: 0,
            heap: BinaryHeap::with_capacity(MAX_FRONTIER),
            pending: None,
            max_read_bytes,
            lod: Some(lod),
            result: None,
            stats: GeoIndexQueryStats {
                passes: 1,
                ..Default::default()
            },
            cancelled: false,
            failed: false,
            lease,
        }))
    }
    pub fn step(&mut self) -> Result<GeoIndexedQueryStep> {
        self.step_with_cancel(&mut || false)
    }
    pub fn step_with_cancel(
        &mut self,
        cancel: &mut dyn FnMut() -> bool,
    ) -> Result<GeoIndexedQueryStep> {
        if cancel() {
            self.cancel();
        }
        let result = self.step_inner(cancel);
        if result.is_err() {
            self.failed = true;
            self.clear_work();
        }
        result
    }
    fn clear_work(&mut self) {
        self.streams = Vec::new();
        self.heap = BinaryHeap::new();
        self.lod = None;
    }
    fn step_inner(&mut self, cancel: &mut dyn FnMut() -> bool) -> Result<GeoIndexedQueryStep> {
        if let Some((_, p, consumed)) = self.pending {
            let t = self.ticket(p);
            return Ok(if consumed || self.cancelled || self.failed {
                GeoIndexedQueryStep::AwaitRelease(t)
            } else {
                GeoIndexedQueryStep::NeedRead(t)
            });
        }
        if self.cancelled || self.failed {
            return Ok(GeoIndexedQueryStep::Cancelled);
        }
        if self.result.is_some() {
            return Ok(GeoIndexedQueryStep::Complete);
        }
        loop {
            while self.next_stream < self.streams.len() {
                if cancel() {
                    return Err(SourceError::Cancelled);
                }
                let i = self.next_stream;
                self.next_stream += 1;
                if self.issue(i, cancel)? {
                    return self.step_inner(cancel);
                }
            }
            while let Some(Reverse((_, _, i))) = self.heap.pop() {
                if cancel() {
                    return Err(SourceError::Cancelled);
                }
                let stream = &mut self.streams[i];
                let v = stream.buffer[stream.cursor];
                stream.cursor += 1;
                self.lod
                    .as_mut()
                    .ok_or(SourceError::StaleSource)?
                    .fold_indexed_vertex(v.identity, v.vertex, v.xy, v.start, v.end, cancel)?;
                if stream.cursor < stream.buffer.len() {
                    self.push_head(i);
                } else if self.issue(i, cancel)? {
                    return self.step_inner(cancel);
                }
            }
            if cancel() {
                return Err(SourceError::Cancelled);
            }
            let pass = self
                .lod
                .as_mut()
                .ok_or(SourceError::StaleSource)?
                .end_pass()?;
            if cancel() {
                return Err(SourceError::Cancelled);
            }
            match pass {
                GeoLodPass::Repeat => {
                    for stream in &mut self.streams {
                        stream.next = stream.first;
                        stream.cursor = 0;
                        stream.buffer = Vec::new();
                    }
                    self.next_stream = 0;
                    self.stats.passes += 1;
                }
                GeoLodPass::Finished => {
                    self.clear_buffers();
                    let result = self.lod.take().unwrap().finish()?;
                    if cancel() {
                        return Err(SourceError::Cancelled);
                    }
                    self.lease
                        .resize(GeoPointLod::output_bytes(&result) + 16_384)?;
                    self.streams = Vec::new();
                    self.heap = BinaryHeap::new();
                    self.result = Some(result);
                    return Ok(GeoIndexedQueryStep::Complete);
                }
            }
        }
    }
    fn clear_buffers(&mut self) {
        for stream in &mut self.streams {
            stream.buffer = Vec::new();
        }
    }
    fn push_head(&mut self, i: usize) {
        let v = self.streams[i].buffer[self.streams[i].cursor];
        self.heap
            .push(Reverse((v.identity.source_row, v.vertex, i)));
    }
    fn issue(&mut self, i: usize, cancel: &mut dyn FnMut() -> bool) -> Result<bool> {
        let stream = &mut self.streams[i];
        stream.buffer = Vec::new();
        stream.cursor = 0;
        while stream.next < stream.end {
            if cancel() {
                return Err(SourceError::Cancelled);
            }
            let page = self.index.pages[stream.next];
            stream.next += 1;
            if !page.time_matches(self.time) {
                continue;
            }
            let total = self
                .stats
                .bytes_read
                .checked_add(page.read.encoded_bytes as u64)
                .ok_or(SourceError::ResourceLimit)?;
            if total > self.max_read_bytes {
                return Err(SourceError::ResourceLimit);
            }
            self.pending = Some((i, page, false));
            return Ok(true);
        }
        Ok(false)
    }
    fn ticket(&self, p: Page) -> GeoIndexedReadTicket {
        GeoIndexedReadTicket {
            session: self.session,
            pass: self.stats.passes,
            request: p.read,
        }
    }
    pub fn supply(
        &mut self,
        t: GeoIndexedReadTicket,
        bytes: &[u8],
        cancel: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        if self.cancelled || self.failed {
            return Err(SourceError::StaleSource);
        }
        let (i, p, consumed) = self.pending.ok_or(SourceError::StaleSource)?;
        if consumed || t != self.ticket(p) {
            return Err(SourceError::StaleSource);
        }
        let result = (|| {
            if cancel() {
                return Err(SourceError::Cancelled);
            }
            let vertices = decode_page(p, bytes)?;
            if cancel() {
                return Err(SourceError::Cancelled);
            }
            self.streams[i].buffer = vertices;
            self.stats.pages_read += 1;
            self.stats.bytes_read = self
                .stats
                .bytes_read
                .checked_add(bytes.len() as u64)
                .ok_or(SourceError::ResourceLimit)?;
            self.stats.candidate_vertices = self
                .stats
                .candidate_vertices
                .checked_add(p.count as u64)
                .ok_or(SourceError::ResourceLimit)?;
            self.pending = Some((i, p, true));
            Ok(())
        })();
        if result.is_err() {
            self.failed = true;
            self.clear_work();
        }
        result
    }
    pub fn release_read(&mut self, t: GeoIndexedReadTicket) -> Result<()> {
        let (i, p, consumed) = self.pending.ok_or(SourceError::StaleSource)?;
        if t != self.ticket(p) || (!consumed && !self.cancelled && !self.failed) {
            return Err(SourceError::StaleSource);
        }
        self.pending = None;
        if self.cancelled || self.failed {
            self.lease.resize(16_384)?;
        } else {
            self.push_head(i);
        }
        Ok(())
    }
    pub fn cancel(&mut self) {
        self.cancelled = true;
        self.clear_work();
        self.result = None;
    }
    pub fn has_outstanding_io(&self) -> bool {
        self.pending.is_some()
    }
    pub fn finish(&mut self) -> Result<GeoIndexedResult> {
        if self.step()? != GeoIndexedQueryStep::Complete {
            return Err(SourceError::StaleSource);
        }
        Ok(GeoIndexedResult {
            result: self.result.take().unwrap(),
            stats: self.stats,
            _lease: std::mem::replace(&mut self.lease, GeoProcessorLease::acquire(0)?),
        })
    }
}
/// Synchronous callback adapter delegates to the same resumable state machine.
#[allow(clippy::too_many_arguments)]
pub fn process_indexed<I: GeoSpatialReader>(
    index: Arc<ValidatedGeoSpatialIndex>,
    reader: &mut I,
    camera: GeoViewport,
    time: TimePredicate,
    options: GeoLodOptions,
    layer_id: u64,
    style_revision: u64,
    state_revision: u64,
    max_read_bytes: u64,
    cancel: &mut dyn FnMut() -> bool,
) -> Result<Option<GeoIndexedResult>> {
    let Some(mut s) = GeoIndexedQuerySession::new(
        index,
        camera,
        time,
        options,
        layer_id,
        style_revision,
        state_revision,
        max_read_bytes,
    )?
    else {
        return Ok(None);
    };
    loop {
        if cancel() {
            s.cancel();
            return Err(SourceError::Cancelled);
        }
        match s.step_with_cancel(cancel)? {
            GeoIndexedQueryStep::NeedRead(t) => {
                let bytes = reader.read(t.request)?;
                if bytes.capacity() > PAGE_BYTES {
                    return Err(SourceError::ResourceLimit);
                }
                s.supply(t, &bytes, cancel)?;
                drop(bytes);
                s.release_read(t)?;
            }
            GeoIndexedQueryStep::Complete => return s.finish().map(Some),
            _ => return Err(SourceError::StaleSource),
        }
    }
}
