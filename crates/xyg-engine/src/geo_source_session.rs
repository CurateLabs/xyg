//! Bounded resumable geographic source processor. See spec/design/geo-source-session.md.
use crate::geo_linked_state::GeoLinkedState;
use crate::geo_lod::{GeoLodIdentity, GeoLodOptions, GeoLodPass, GeoPointLod, GeoPointResult};
use crate::geo_source::{
    GeoManifestBuilder, GeoSourceManifest, MAX_CHUNK_PEAK, MAX_PROCESSOR_BYTES, QueryBudget,
    QuerySpec, ReadRequest, SourceError, TimePredicate, UntrustedGeoManifest, parse_authenticated,
};
use crate::geo_viewport::{GeoViewport, GeoViewportRebuildKey};
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
type Result<T> = std::result::Result<T, SourceError>;
static PROCESSOR_BYTES: AtomicUsize = AtomicUsize::new(0);
static NEXT_SESSION: AtomicU64 = AtomicU64::new(1);
/// Shared ticket namespace across source and membership sessions.
pub(crate) fn next_session_identity() -> Result<u64> {
    NEXT_SESSION
        .fetch_update(Ordering::AcqRel, Ordering::Acquire, |n| n.checked_add(1))
        .map_err(|_| SourceError::ResourceLimit)
}
const SESSION_OVERHEAD: usize = 16_384;
const MAX_RETIRED_READS: usize = 64;
#[cfg(test)]
pub(crate) fn test_processor_lock() -> std::sync::MutexGuard<'static, ()> {
    static LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
    LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// One process/one WASM-instance ledger, shared by every retained-source session.
/// The host must share a coordinator across separate WASM instances.
#[derive(Debug)]
pub struct GeoProcessorLease {
    bytes: usize,
}
impl GeoProcessorLease {
    pub fn acquire(bytes: usize) -> Result<Self> {
        let mut lease = Self { bytes: 0 };
        lease.resize(bytes)?;
        Ok(lease)
    }
    pub fn resize(&mut self, bytes: usize) -> Result<()> {
        if bytes <= self.bytes {
            PROCESSOR_BYTES.fetch_sub(self.bytes - bytes, Ordering::AcqRel);
            self.bytes = bytes;
            return Ok(());
        }
        let additional = bytes - self.bytes;
        PROCESSOR_BYTES
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |live| {
                live.checked_add(additional)
                    .filter(|n| *n <= MAX_PROCESSOR_BYTES)
            })
            .map_err(|_| SourceError::ResourceLimit)?;
        self.bytes = bytes;
        Ok(())
    }
    pub fn bytes(&self) -> usize {
        self.bytes
    }
    pub fn live_bytes() -> usize {
        PROCESSOR_BYTES.load(Ordering::Acquire)
    }
}
impl Drop for GeoProcessorLease {
    fn drop(&mut self) {
        PROCESSOR_BYTES.fetch_sub(self.bytes, Ordering::AcqRel);
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GeoOperationSnapshot {
    pub source_digest: [u8; 8],
    pub generation: u64,
    pub camera: GeoViewportRebuildKey,
    pub time: TimePredicate,
    pub camera_revision: u64,
    pub time_revision: u64,
    pub layer_id: u64,
    pub layer_revision: u64,
    pub style_revision: u64,
    pub state_revision: u64,
}
impl GeoOperationSnapshot {
    pub(crate) fn precedes(self, previous: Self) -> bool {
        (self.camera_revision == previous.camera_revision && self.camera != previous.camera)
            || (self.time_revision == previous.time_revision && self.time != previous.time)
            || (self.layer_revision == previous.layer_revision
                && self.layer_id != previous.layer_id)
            || self.camera_revision < previous.camera_revision
            || self.time_revision < previous.time_revision
            || self.layer_revision < previous.layer_revision
            || self.style_revision < previous.style_revision
            || self.state_revision < previous.state_revision
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoReadTicket {
    pub session_id: u64,
    pub read_id: u64,
    /// Zero is source validation; positive values are query sequences.
    pub sequence: u64,
    pub pass: u32,
    pub request: ReadRequest,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoSessionStep {
    NeedRead(GeoReadTicket),
    AwaitRelease(GeoReadTicket),
    SourceReady,
    Complete,
    Idle,
    Disposed,
}
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct GeoSessionStats {
    pub chunks_read: u64,
    pub bytes_read: u64,
    pub rows_examined: u64,
    pub passes: u32,
}
/// Field order ensures result storage drops before its accounting lease.
pub struct GeoPublishedResult {
    pub snapshot: GeoOperationSnapshot,
    pub sequence: u64,
    pub result: GeoPointResult,
    pub stats: GeoSessionStats,
    lease: GeoProcessorLease,
}
impl GeoPublishedResult {
    pub fn reserved_bytes(&self) -> usize {
        self.lease.bytes()
    }
}
struct PendingRead {
    ticket: GeoReadTicket,
    consumed: bool,
    lease: GeoProcessorLease,
}
struct Validation {
    manifest: UntrustedGeoManifest,
    builder: GeoManifestBuilder,
    index: usize,
}
struct Job {
    processor: GeoPointLod,
    selected_reserve: usize,
    snapshot: GeoOperationSnapshot,
    query: QuerySpec,
    sequence: u64,
    index: usize,
    pass: u32,
    stats: GeoSessionStats,
    lease: GeoProcessorLease,
}
/// Hosts retain this object until all retired read leases have been acknowledged.
/// No transport I/O is performed here. Supply takes borrowed host bytes.
pub struct GeoSourceSession {
    id: u64,
    next_read: u64,
    validation: Option<Validation>,
    source: Option<GeoSourceManifest>,
    job: Option<Job>,
    published: Option<GeoPublishedResult>,
    pending: Option<PendingRead>,
    retired: Vec<PendingRead>,
    metadata_lease: GeoProcessorLease,
    budget: QueryBudget,
    validation_stats: GeoSessionStats,
    last_sequence: u64,
    painted_style: Option<(u64, [u8; 48])>,
    cancelled_through: u64,
    last_snapshot: Option<GeoOperationSnapshot>,
    disposed: bool,
}
impl GeoSourceSession {
    pub fn create(bytes: &[u8], budget: QueryBudget) -> Result<Self> {
        budget.validate()?;
        // Reserve before making even the manifest copy. The upper bound includes
        // builder capacity growth, encoded comparison, caller input and metadata.
        let reserve = UntrustedGeoManifest::preflight_reserved_bytes(bytes)?
            .checked_add(bytes.len())
            .and_then(|n| n.checked_add(SESSION_OVERHEAD))
            .ok_or(SourceError::ResourceLimit)?;
        if reserve > budget.processor_bytes {
            return Err(SourceError::ResourceLimit);
        }
        let mut metadata_lease = GeoProcessorLease::acquire(reserve)?;
        let manifest = UntrustedGeoManifest::from_bytes(bytes, budget.processor_bytes)?;
        if manifest.chunk_count() > budget.max_chunks || manifest.rows() > budget.max_rows_examined
        {
            return Err(SourceError::ResourceLimit);
        }
        let actual = manifest
            .validation_reserved_bytes()?
            .checked_add(bytes.len())
            .and_then(|n| n.checked_add(SESSION_OVERHEAD))
            .ok_or(SourceError::ResourceLimit)?;
        metadata_lease.resize(actual)?;
        let id = next_session_identity()?;
        Ok(Self {
            id,
            next_read: 1,
            validation: Some(Validation {
                manifest,
                builder: GeoManifestBuilder::new(),
                index: 0,
            }),
            source: None,
            job: None,
            published: None,
            pending: None,
            retired: Vec::with_capacity(MAX_RETIRED_READS),
            metadata_lease,
            budget,
            validation_stats: GeoSessionStats::default(),
            last_sequence: 0,
            painted_style: None,
            cancelled_through: 0,
            last_snapshot: None,
            disposed: false,
        })
    }
    pub fn current_sequence(&self) -> u64 {
        self.last_sequence
    }
    pub fn source(&self) -> Option<&GeoSourceManifest> {
        self.source.as_ref()
    }
    pub fn published(&self) -> Option<&GeoPublishedResult> {
        self.published.as_ref()
    }
    /// Validate style identity before candidate allocation. Only successful Scene
    /// publication commits it; picking requires an already painted binding.
    pub(crate) fn validate_painted_style(
        &self,
        bytes: &[u8; 48],
        require_painted: bool,
    ) -> Result<()> {
        let revision = self
            .published
            .as_ref()
            .ok_or(SourceError::StaleSource)?
            .result
            .key
            .identity
            .style_revision;
        match self.painted_style {
            Some((old, style)) if old == revision && style == *bytes => Ok(()),
            Some((old, _)) if old == revision => Err(SourceError::StaleSource),
            _ if require_painted => Err(SourceError::StaleSource),
            _ => Ok(()),
        }
    }
    pub(crate) fn commit_painted_style(&mut self, bytes: [u8; 48]) {
        self.painted_style = Some((
            self.published
                .as_ref()
                .unwrap()
                .result
                .key
                .identity
                .style_revision,
            bytes,
        ));
    }
    pub fn begin(
        &mut self,
        sequence: u64,
        snapshot: GeoOperationSnapshot,
        camera: GeoViewport,
        query: QuerySpec,
        options: GeoLodOptions,
    ) -> Result<()> {
        self.begin_with_state(sequence, snapshot, camera, query, options, None)
    }
    /// Immutable sparse intent is validated and admitted before source I/O.
    #[allow(clippy::too_many_arguments)]
    pub fn begin_with_state(
        &mut self,
        sequence: u64,
        snapshot: GeoOperationSnapshot,
        camera: GeoViewport,
        query: QuerySpec,
        mut options: GeoLodOptions,
        state: Option<Arc<GeoLinkedState>>,
    ) -> Result<()> {
        if self.disposed
            || sequence == 0
            || sequence <= self.last_sequence
            || sequence <= self.cancelled_through
        {
            return Err(SourceError::StaleSource);
        }
        let source = self.source.as_ref().ok_or(SourceError::InvalidFrame)?;
        query.validate()?;
        // LOD folds all time-selected rows: a caller bbox must not prune its screen footprint.
        if query.bounds.is_some()
            || snapshot.source_digest != source.digest()
            || snapshot.generation != source.generation()
            || snapshot.camera != camera.rebuild_key()?
            || snapshot.time != query.time
            || self.last_snapshot.is_some_and(|old| snapshot.precedes(old))
        {
            return Err(SourceError::StaleSource);
        }
        if self.pending.is_some() && self.retired.len() == MAX_RETIRED_READS {
            return Err(SourceError::ResourceLimit);
        }
        if let Some(state) = &state {
            state.validate_snapshot(snapshot)?;
        }
        let reserve = GeoPointLod::reservation_bytes_with_state(options, state.as_deref())?;
        let wrapper = if state.is_some() { 1024 } else { 0 };
        if self
            .local_bytes()
            .checked_add(reserve)
            .and_then(|n| n.checked_add(wrapper))
            .is_none_or(|n| n > self.budget.processor_bytes)
        {
            return Err(SourceError::ResourceLimit);
        }
        let lease = GeoProcessorLease::acquire(if state.is_some() { wrapper } else { reserve })?;
        options.processor_bytes = reserve;
        let processor = GeoPointLod::new_with_state(
            GeoLodIdentity {
                source_digest: source.digest(),
                generation: source.generation(),
                source_rows: source.rows(),
                crs: source.crs(),
                geometry: source.geometry(),
                layer_id: snapshot.layer_id,
                style_revision: snapshot.style_revision,
                state_revision: snapshot.state_revision,
            },
            camera,
            query.time,
            options,
            state,
        )?;
        self.retire_pending()?;
        self.job = Some(Job {
            processor,
            selected_reserve: if wrapper != 0 { reserve } else { 0 },
            snapshot,
            query,
            sequence,
            index: 0,
            pass: 0,
            stats: GeoSessionStats::default(),
            lease,
        });
        self.last_sequence = sequence;
        self.last_snapshot = Some(snapshot);
        Ok(())
    }
    fn local_bytes(&self) -> usize {
        self.metadata_lease.bytes()
            + self
                .job
                .as_ref()
                .map_or(0, |j| j.lease.bytes() + j.selected_reserve)
            + self.published.as_ref().map_or(0, |p| {
                p.lease.bytes()
                    + p.result.selection.as_ref().map_or(0, |selection| {
                        selection.retained_bytes() + selection.state().retained_bytes()
                    })
            })
            + self.pending.as_ref().map_or(0, |r| r.lease.bytes())
            + self.retired.iter().map(|r| r.lease.bytes()).sum::<usize>()
    }
    fn retire_pending(&mut self) -> Result<()> {
        if self.pending.is_some() && self.retired.len() == MAX_RETIRED_READS {
            return Err(SourceError::ResourceLimit);
        }
        if let Some(read) = self.pending.take() {
            self.retired.push(read);
        }
        Ok(())
    }
    pub fn cancel(&mut self, through_sequence: u64) -> Result<()> {
        if self.validation.is_some() {
            self.retire_pending()?;
            self.validation = None;
            self.metadata_lease.resize(SESSION_OVERHEAD)?;
        }
        if self
            .job
            .as_ref()
            .is_some_and(|j| j.sequence <= through_sequence)
        {
            self.retire_pending()?;
            self.job = None;
        }
        self.cancelled_through = self.cancelled_through.max(through_sequence);
        Ok(())
    }
    pub fn dispose(&mut self) -> Result<()> {
        self.retire_pending()?;
        self.job = None;
        self.published = None;
        self.source = None;
        self.validation = None;
        self.metadata_lease.resize(SESSION_OVERHEAD)?;
        self.disposed = true;
        Ok(())
    }
    pub fn release_read(&mut self, ticket: GeoReadTicket) -> Result<()> {
        if self
            .pending
            .as_ref()
            .is_some_and(|r| r.ticket == ticket && r.consumed)
        {
            self.pending = None;
            return Ok(());
        }
        if let Some(i) = self.retired.iter().position(|r| r.ticket == ticket) {
            self.retired.swap_remove(i);
            return Ok(());
        }
        Err(SourceError::StaleSource)
    }
    /// Host may destroy the session only after abort/drop + release_read for all reads.
    pub fn has_outstanding_reads(&self) -> bool {
        self.pending.is_some() || !self.retired.is_empty()
    }
    pub fn step(&mut self) -> Result<GeoSessionStep> {
        let result = self.step_inner();
        if result.is_err() && result != Err(SourceError::ResourceLimit) && self.pending.is_none() {
            self.job = None;
        }
        result
    }
    fn step_inner(&mut self) -> Result<GeoSessionStep> {
        if self.disposed {
            return Ok(GeoSessionStep::Disposed);
        }
        if let Some(read) = &self.pending {
            return Ok(if read.consumed {
                GeoSessionStep::AwaitRelease(read.ticket)
            } else {
                GeoSessionStep::NeedRead(read.ticket)
            });
        }
        if let Some(v) = &self.validation {
            if v.index == v.manifest.chunk_count() {
                let v = self.validation.take().unwrap();
                let source = v.manifest.finish(v.builder)?;
                let actual = source
                    .metadata_bytes()
                    .checked_add(SESSION_OVERHEAD)
                    .ok_or(SourceError::ResourceLimit)?;
                self.source = Some(source);
                self.metadata_lease.resize(actual)?;
                return Ok(GeoSessionStep::SourceReady);
            }
            let req = v.manifest.read_request(v.index)?;
            return self.issue_read(req, 0, 0);
        }
        loop {
            let Some(job) = self.job.as_mut() else {
                return Ok(GeoSessionStep::Idle);
            };
            let source = self.source.as_ref().unwrap();
            while job.index < source.chunks().len()
                && !source.chunk_matches(job.index, job.query)?
            {
                job.index += 1;
            }
            if job.index < source.chunks().len() {
                let req = source.read_request(job.index)?;
                let (sequence, pass) = (job.sequence, job.pass);
                return self.issue_read(req, sequence, pass);
            }
            match job.processor.end_pass()? {
                GeoLodPass::Repeat => {
                    job.pass += 1;
                    job.index = 0;
                    job.stats.passes += 1;
                }
                GeoLodPass::Finished => {
                    let job = self.job.take().unwrap();
                    let result = job.processor.finish()?;
                    if result.key.identity.source_digest != job.snapshot.source_digest
                        || result.key.camera != job.snapshot.camera
                        || result.key.time != job.snapshot.time
                    {
                        return Err(SourceError::StaleSource);
                    }
                    let mut lease = job.lease;
                    lease.resize(
                        (if result.selection.is_some() {
                            0
                        } else {
                            GeoPointLod::output_bytes(&result)
                        })
                        .checked_add(1024)
                        .ok_or(SourceError::ResourceLimit)?,
                    )?;
                    self.published = Some(GeoPublishedResult {
                        snapshot: job.snapshot,
                        sequence: job.sequence,
                        result,
                        stats: job.stats,
                        lease,
                    });
                    return Ok(GeoSessionStep::Complete);
                }
            }
        }
    }
    fn issue_read(
        &mut self,
        request: ReadRequest,
        sequence: u64,
        pass: u32,
    ) -> Result<GeoSessionStep> {
        let stats = if sequence == 0 {
            self.validation_stats
        } else {
            self.job.as_ref().unwrap().stats
        };
        let total_bytes = stats
            .bytes_read
            .checked_add(request.encoded_bytes as u64)
            .ok_or(SourceError::ResourceLimit)?;
        let rows = stats
            .rows_examined
            .checked_add(request.rows as u64)
            .ok_or(SourceError::ResourceLimit)?;
        if total_bytes > self.budget.max_read_bytes
            || rows > self.budget.max_rows_examined
            || stats.chunks_read >= (self.budget.max_chunks as u64) * 2
        {
            return Err(SourceError::ResourceLimit);
        }
        let input_bytes = request
            .encoded_bytes
            .checked_mul(2)
            .ok_or(SourceError::ResourceLimit)?;
        let peak = request
            .encoded_bytes
            .checked_mul(4)
            .and_then(|n| n.checked_add(16_384))
            .ok_or(SourceError::ResourceLimit)?;
        if peak > MAX_CHUNK_PEAK
            || self
                .local_bytes()
                .checked_add(peak)
                .is_none_or(|n| n > self.budget.processor_bytes)
        {
            return Err(SourceError::ResourceLimit);
        }
        // Admission of the full parse phase occurs before the host allocates. Other
        // sessions cannot consume this promised scratch while the read is pending.
        let lease = GeoProcessorLease::acquire(peak)?;
        let ticket = GeoReadTicket {
            session_id: self.id,
            read_id: self.next_read,
            sequence,
            pass,
            request,
        };
        self.next_read = self
            .next_read
            .checked_add(1)
            .ok_or(SourceError::ResourceLimit)?;
        debug_assert!(input_bytes <= lease.bytes());
        self.pending = Some(PendingRead {
            ticket,
            consumed: false,
            lease,
        });
        Ok(GeoSessionStep::NeedRead(ticket))
    }
    pub fn supply(
        &mut self,
        ticket: GeoReadTicket,
        bytes: &[u8],
        cancelled: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        if self.disposed
            || !self
                .pending
                .as_ref()
                .is_some_and(|r| r.ticket == ticket && !r.consumed)
        {
            return Err(SourceError::StaleSource);
        }
        let result = self.consume(ticket, bytes, cancelled);
        // Host still owns bytes until release_read; retain input+scratch reservation.
        if let Some(read) = &mut self.pending {
            read.consumed = true;
        }
        if result.is_err() {
            if ticket.sequence == 0 {
                self.validation = None;
            } else {
                self.job = None;
            }
        }
        result
    }
    fn consume(
        &mut self,
        ticket: GeoReadTicket,
        bytes: &[u8],
        cancelled: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        if cancelled() {
            return Err(SourceError::Cancelled);
        }
        let peak = self.pending.as_ref().unwrap().lease.bytes();
        let chunk = parse_authenticated(ticket.request, bytes, peak)?;
        if cancelled() {
            return Err(SourceError::Cancelled);
        }
        let (stats, rows) = if ticket.sequence == 0 {
            let v = self.validation.as_mut().unwrap();
            v.manifest.accept_chunk(v.index, &chunk, &mut v.builder)?;
            v.index += 1;
            (&mut self.validation_stats, chunk.column().len())
        } else {
            let job = self.job.as_mut().ok_or(SourceError::StaleSource)?;
            if job.sequence != ticket.sequence || job.pass != ticket.pass {
                return Err(SourceError::StaleSource);
            }
            job.processor.fold_chunk(
                &chunk,
                ticket.request.chunk_index,
                ticket.request.first_row,
                cancelled,
            )?;
            job.index += 1;
            (&mut job.stats, chunk.column().len())
        };
        stats.chunks_read += 1;
        stats.bytes_read = stats
            .bytes_read
            .checked_add(bytes.len() as u64)
            .ok_or(SourceError::ResourceLimit)?;
        stats.rows_examined = stats
            .rows_examined
            .checked_add(rows as u64)
            .ok_or(SourceError::ResourceLimit)?;
        if stats.rows_examined > self.budget.max_rows_examined {
            return Err(SourceError::ResourceLimit);
        }
        stats.passes = ticket.pass + 1;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
    use crate::geo_lod::GeoPointOutput;
    use crate::geo_source::{GeoChunk, GeoIntervals};
    fn fixture(count: usize, timed: bool) -> (Vec<Vec<u8>>, Vec<u8>) {
        let mut chunks = Vec::new();
        let mut builder = GeoManifestBuilder::new();
        for part in 0..2 {
            let xy = vec![0.; count * 2];
            let valid = vec![1; count];
            let ids: Vec<_> = (0..count)
                .map(|i| u64::MAX - (i + part * count) as u64)
                .collect();
            let col = GeoColumn::from_descriptor(GeoDescriptor {
                geometry: GeoGeometry::Point,
                crs: GeoCrs::Epsg4326,
                xy: &xy,
                validity: &valid,
                feature_ids: Some(&ids),
                offsets0: &[],
                offsets1: &[],
                offsets2: &[],
                limits: GeoLimits::default(),
            })
            .unwrap();
            let starts = vec![part as i64 * 10; count];
            let ends = vec![part as i64 * 10 + 10; count];
            let time = GeoIntervals {
                starts: &starts,
                ends: &ends,
                start_validity: &valid,
                end_validity: &valid,
            };
            let bytes = GeoChunk::encode(&col, timed.then_some(time)).unwrap();
            builder
                .push(&GeoChunk::parse(&bytes, MAX_CHUNK_PEAK).unwrap())
                .unwrap();
            chunks.push(bytes);
        }
        (chunks, builder.finish(9).unwrap().encode().unwrap())
    }
    fn drive(s: &mut GeoSourceSession, chunks: &[Vec<u8>]) -> GeoSessionStep {
        loop {
            match s.step().unwrap() {
                GeoSessionStep::NeedRead(t) => {
                    s.supply(t, &chunks[t.request.chunk_index as usize], &mut || false)
                        .unwrap();
                    assert_eq!(s.step().unwrap(), GeoSessionStep::AwaitRelease(t));
                    s.release_read(t).unwrap();
                }
                other => return other,
            }
        }
    }
    fn camera() -> GeoViewport {
        GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 2., 800., 600., 0., 0., true).unwrap()
    }
    fn snapshot(s: &GeoSourceSession, time: TimePredicate, revision: u64) -> GeoOperationSnapshot {
        let source = s.source().unwrap();
        GeoOperationSnapshot {
            source_digest: source.digest(),
            generation: source.generation(),
            camera: camera().rebuild_key().unwrap(),
            time,
            camera_revision: revision,
            time_revision: revision,
            layer_id: u64::MAX,
            layer_revision: revision,
            style_revision: revision,
            state_revision: revision,
        }
    }
    fn begin(s: &mut GeoSourceSession, sequence: u64, time: TimePredicate) {
        s.begin(
            sequence,
            snapshot(s, time, sequence),
            camera(),
            QuerySpec { bounds: None, time },
            GeoLodOptions::default(),
        )
        .unwrap();
    }
    #[test]
    fn authenticated_validation_time_first_actual_lod_and_full_ids() {
        let _serial = test_processor_lock();
        let (chunks, manifest) = fixture(3, true);
        let mut s = GeoSourceSession::create(&manifest, QueryBudget::default()).unwrap();
        assert!(s.source().is_none());
        assert_eq!(drive(&mut s, &chunks), GeoSessionStep::SourceReady);
        begin(&mut s, 1, TimePredicate::Instant(10));
        assert_eq!(drive(&mut s, &chunks), GeoSessionStep::Complete);
        let p = s.published().unwrap();
        assert_eq!(p.stats.chunks_read, 1);
        assert_eq!(p.stats.rows_examined, 3);
        let GeoPointOutput::Direct(points) = &p.result.output else {
            panic!("direct expected");
        };
        assert_eq!(points.len(), 3);
        assert_eq!(points[0].identity.feature_id, u64::MAX - 3);
        assert_eq!(points[0].identity.source_row, 3);
        assert_eq!(points[0].identity.chunk_index, 1);
        // Compare the real synchronous shared engine, not a second session implementation.
        let source = s.source().unwrap();
        let snap = p.snapshot;
        let expected = crate::geo_lod::process(
            source,
            &mut |r: ReadRequest| Ok(chunks[r.chunk_index as usize].clone()),
            camera(),
            snap.time,
            snap.layer_id,
            snap.style_revision,
            snap.state_revision,
            GeoLodOptions::default(),
            QueryBudget::default(),
            &mut || false,
        )
        .unwrap();
        let GeoPointOutput::Direct(reference) = expected.output else {
            panic!()
        };
        assert_eq!(*points, reference);
    }
    #[test]
    fn two_pass_reduction_retains_read_and_output_leases() {
        let _serial = test_processor_lock();
        let (chunks, manifest) = fixture(20_000, false);
        let baseline = GeoProcessorLease::live_bytes();
        let mut s = GeoSourceSession::create(&manifest, QueryBudget::default()).unwrap();
        assert_eq!(drive(&mut s, &chunks), GeoSessionStep::SourceReady);
        begin(&mut s, 1, TimePredicate::All);
        assert_eq!(drive(&mut s, &chunks), GeoSessionStep::Complete);
        let p = s.published().unwrap();
        assert_eq!(p.stats.chunks_read, 4);
        assert_eq!(p.stats.rows_examined, 80_000);
        assert_eq!(p.stats.passes, 2);
        let GeoPointOutput::Reduced(cells) = &p.result.output else {
            panic!()
        };
        assert_eq!(cells.iter().map(|c| c.count).sum::<u64>(), 40_000);
        assert!(p.reserved_bytes() >= cells.capacity() * std::mem::size_of_val(&cells[0]));
        drop(s);
        assert_eq!(GeoProcessorLease::live_bytes(), baseline);
    }
    #[test]
    fn stale_ticket_cancel_dispose_and_old_output_are_atomic() {
        let _serial = test_processor_lock();
        let (chunks, manifest) = fixture(2, false);
        let mut s = GeoSourceSession::create(&manifest, QueryBudget::default()).unwrap();
        drive(&mut s, &chunks);
        begin(&mut s, 1, TimePredicate::All);
        drive(&mut s, &chunks);
        begin(&mut s, 2, TimePredicate::All);
        let GeoSessionStep::NeedRead(old) = s.step().unwrap() else {
            panic!()
        };
        let before = GeoProcessorLease::live_bytes();
        begin(&mut s, 3, TimePredicate::All);
        assert_eq!(
            s.supply(old, &chunks[0], &mut || false),
            Err(SourceError::StaleSource)
        );
        assert!(GeoProcessorLease::live_bytes() >= before);
        assert_eq!(s.published().unwrap().sequence, 1);
        s.cancel(2).unwrap(); // cannot cancel sequence3
        let GeoSessionStep::NeedRead(current) = s.step().unwrap() else {
            panic!()
        };
        assert_eq!(current.sequence, 3);
        s.release_read(old).unwrap();
        s.supply(current, &chunks[0], &mut || true).unwrap_err();
        s.release_read(current).unwrap();
        assert_eq!(s.step().unwrap(), GeoSessionStep::Idle);
        assert_eq!(s.published().unwrap().sequence, 1);
        begin(&mut s, 4, TimePredicate::All);
        let GeoSessionStep::NeedRead(retired) = s.step().unwrap() else {
            panic!()
        };
        s.dispose().unwrap();
        assert!(s.has_outstanding_reads());
        assert_eq!(
            s.supply(retired, &chunks[0], &mut || false),
            Err(SourceError::StaleSource)
        );
        assert_eq!(s.step().unwrap(), GeoSessionStep::Disposed);
        s.release_read(retired).unwrap();
        assert!(!s.has_outstanding_reads());
    }
    #[test]
    fn global_quota_and_admission_fail_before_io_preserve_good_output() {
        let _serial = test_processor_lock();
        let (chunks, manifest) = fixture(2, false);
        let mut s = GeoSourceSession::create(&manifest, QueryBudget::default()).unwrap();
        drive(&mut s, &chunks);
        begin(&mut s, 1, TimePredicate::All);
        drive(&mut s, &chunks);
        let live = GeoProcessorLease::live_bytes();
        let blocker = GeoProcessorLease::acquire(MAX_PROCESSOR_BYTES - live).unwrap();
        let snap = snapshot(&s, TimePredicate::All, 2);
        assert_eq!(
            s.begin(
                2,
                snap,
                camera(),
                QuerySpec {
                    bounds: None,
                    time: TimePredicate::All
                },
                GeoLodOptions::default()
            ),
            Err(SourceError::ResourceLimit)
        );
        assert_eq!(s.published().unwrap().sequence, 1);
        assert!(matches!(s.step(), Ok(GeoSessionStep::Idle)));
        assert!(GeoSourceSession::create(&manifest, QueryBudget::default()).is_err());
        drop(blocker);
        begin(&mut s, 2, TimePredicate::All);
        let live = GeoProcessorLease::live_bytes();
        let blocker = GeoProcessorLease::acquire(MAX_PROCESSOR_BYTES - live).unwrap();
        assert_eq!(s.step(), Err(SourceError::ResourceLimit));
        assert!(!s.has_outstanding_reads());
        drop(blocker);
        drive(&mut s, &chunks);
        assert_eq!(s.published().unwrap().sequence, 2);
    }
    #[test]
    fn forged_manifest_is_never_prunable_and_work_limits_precede_read() {
        let _serial = test_processor_lock();
        let (chunks, mut manifest) = fixture(2, false);
        manifest[64 + 32..64 + 40].copy_from_slice(&1f64.to_le_bytes());
        // Make a valid but forged zero-width bounds box.
        manifest[64 + 48..64 + 56].copy_from_slice(&1f64.to_le_bytes());
        let mut s = GeoSourceSession::create(&manifest, QueryBudget::default()).unwrap();
        let GeoSessionStep::NeedRead(t) = s.step().unwrap() else {
            panic!()
        };
        assert_eq!(
            s.supply(t, &chunks[0], &mut || false),
            Err(SourceError::StaleSource)
        );
        assert!(s.source().is_none());
        s.release_read(t).unwrap();
        let (_, manifest) = fixture(2, false);
        let budget = QueryBudget {
            max_read_bytes: 1,
            ..QueryBudget::default()
        };
        let mut s = GeoSourceSession::create(&manifest, budget).unwrap();
        assert_eq!(s.step(), Err(SourceError::ResourceLimit));
        assert!(!s.has_outstanding_reads());
    }
    #[test]
    fn rejected_snapshot_cannot_replace_active_and_validation_cancel_retires() {
        let _serial = test_processor_lock();
        let (chunks, manifest) = fixture(2, false);
        let mut s = GeoSourceSession::create(&manifest, QueryBudget::default()).unwrap();
        let GeoSessionStep::NeedRead(validation) = s.step().unwrap() else {
            panic!()
        };
        s.cancel(0).unwrap();
        assert_eq!(
            s.supply(validation, &chunks[0], &mut || false),
            Err(SourceError::StaleSource)
        );
        assert!(s.source().is_none());
        s.release_read(validation).unwrap();
        assert_eq!(s.step().unwrap(), GeoSessionStep::Idle);
        let mut s = GeoSourceSession::create(&manifest, QueryBudget::default()).unwrap();
        drive(&mut s, &chunks);
        begin(&mut s, 1, TimePredicate::All);
        let GeoSessionStep::NeedRead(ticket) = s.step().unwrap() else {
            panic!()
        };
        let mut newer = snapshot(&s, TimePredicate::All, 1);
        let mut changed_camera = camera();
        changed_camera.set_zoom(3.).unwrap();
        newer.camera = changed_camera.rebuild_key().unwrap();
        assert_eq!(
            s.begin(
                2,
                newer,
                changed_camera,
                QuerySpec {
                    bounds: None,
                    time: TimePredicate::All
                },
                GeoLodOptions::default()
            ),
            Err(SourceError::StaleSource)
        );
        assert_eq!(s.step().unwrap(), GeoSessionStep::NeedRead(ticket));
        assert_eq!(
            s.begin(
                1,
                snapshot(&s, TimePredicate::All, 1),
                camera(),
                QuerySpec {
                    bounds: None,
                    time: TimePredicate::All
                },
                GeoLodOptions::default()
            ),
            Err(SourceError::StaleSource)
        );
        s.supply(ticket, &chunks[0], &mut || false).unwrap();
        assert_eq!(
            s.supply(ticket, &chunks[0], &mut || false),
            Err(SourceError::StaleSource)
        );
        s.release_read(ticket).unwrap();
        assert_eq!(drive(&mut s, &chunks), GeoSessionStep::Complete);
    }
    #[test]
    fn second_pass_row_admission_precedes_read_and_old_result_survives() {
        let _serial = test_processor_lock();
        let (chunks, manifest) = fixture(20_000, false);
        let mut s = GeoSourceSession::create(
            &manifest,
            QueryBudget {
                max_rows_examined: 40_000,
                ..QueryBudget::default()
            },
        )
        .unwrap();
        drive(&mut s, &chunks);
        begin(&mut s, 1, TimePredicate::All);
        for chunk in &chunks {
            let GeoSessionStep::NeedRead(t) = s.step().unwrap() else {
                panic!()
            };
            s.supply(t, chunk, &mut || false).unwrap();
            s.release_read(t).unwrap();
        }
        assert_eq!(s.step(), Err(SourceError::ResourceLimit));
        assert!(!s.has_outstanding_reads());
        s.cancel(1).unwrap();
        assert_eq!(s.step().unwrap(), GeoSessionStep::Idle);
    }
    #[test]
    fn oversized_manifest_read_request_rejected_without_allocating_lease() {
        let _serial = test_processor_lock();
        let (_, mut bytes) = fixture(2, false);
        bytes[64 + 12..64 + 16].copy_from_slice(&u32::MAX.to_le_bytes());
        let baseline = GeoProcessorLease::live_bytes();
        assert!(matches!(
            GeoSourceSession::create(&bytes, QueryBudget::default()),
            Err(SourceError::InvalidFrame)
        ));
        assert_eq!(GeoProcessorLease::live_bytes(), baseline);
    }
}
