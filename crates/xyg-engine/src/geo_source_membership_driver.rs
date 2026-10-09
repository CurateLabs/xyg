//! Shared bounded authenticated source membership driver, dossier §27/§28.
use crate::geo_source::{
    FeatureView, GeoSourceManifest, MAX_CHUNK_PEAK, QueryBudget, QueryCursor, QuerySpec,
    ReadRequest, SourceError, parse_authenticated,
};
use crate::geo_source_session::{
    GeoProcessorLease, GeoReadTicket, GeoSessionStep, next_session_identity,
};
use std::sync::Arc;
type Result<T> = std::result::Result<T, SourceError>;
const OVERHEAD: usize = 16_384;
const RETIRED_LIMIT: usize = 64;
pub(crate) trait SourceMatcher {
    type Record;
    fn query_spec(&self) -> QuerySpec;
    fn matches(
        &mut self,
        feature: &FeatureView<'_>,
        request: ReadRequest,
        cancelled: &mut dyn FnMut() -> bool,
    ) -> Result<Option<Self::Record>>;
    fn finish(&mut self, _exhausted: bool) -> Result<()> {
        Ok(())
    }
}
pub(crate) struct SourcePage<R> {
    pub features: Vec<R>,
    pub next: Option<QueryCursor>,
    pub chunks_considered: usize,
    pub chunks_read: usize,
    pub bytes_read: u64,
    pub rows_examined: u64,
}
pub(crate) struct SourcePublished<R> {
    pub page: SourcePage<R>,
    pub lease: GeoProcessorLease,
}
struct Read {
    ticket: GeoReadTicket,
    consumed: bool,
    lease: Arc<GeoProcessorLease>,
}
pub(crate) struct SourceMembershipDriver<M: SourceMatcher> {
    id: u64,
    sequence: u64,
    next_read: u64,
    source: Option<GeoSourceManifest>,
    matcher: M,
    cursor: QueryCursor,
    initial_cursor: QueryCursor,
    draft: Option<SourcePage<M::Record>>,
    page_lease: Option<GeoProcessorLease>,
    published: Option<SourcePublished<M::Record>>,
    pending: Option<Read>,
    retired: Vec<Read>,
    metadata_lease: GeoProcessorLease,
    budget: QueryBudget,
    retained_bytes: usize,
    ready: bool,
    active: bool,
    disposed: bool,
}
impl<M: SourceMatcher> SourceMembershipDriver<M> {
    #[allow(clippy::too_many_arguments)]
    pub fn create(
        source: &GeoSourceManifest,
        sequence: u64,
        matcher: M,
        resume: Option<QueryCursor>,
        retained_bytes: usize,
        budget: QueryBudget,
    ) -> Result<Self> {
        if sequence == 0 {
            return Err(SourceError::InvalidFrame);
        }
        budget.validate()?;
        let q = matcher.query_spec();
        let cursor = resume.unwrap_or(QueryCursor {
            generation: source.generation(),
            source_digest: source.digest(),
            query_digest: q.digest(),
            chunk_index: 0,
            row: 0,
        });
        if cursor.generation != source.generation()
            || cursor.source_digest != source.digest()
            || cursor.query_digest != q.digest()
        {
            return Err(SourceError::StaleSource);
        }
        if cursor.chunk_index as usize > source.chunks().len()
            || cursor.row > crate::geo_source::MAX_CHUNK_ROWS as u32
            || (cursor.chunk_index as usize == source.chunks().len() && cursor.row != 0)
            || source
                .chunks()
                .get(cursor.chunk_index as usize)
                .is_some_and(|c| cursor.row > c.rows)
        {
            return Err(SourceError::InvalidFrame);
        }
        let metadata = source
            .clone_reserved_bytes()
            .checked_add(OVERHEAD)
            .ok_or(SourceError::ResourceLimit)?;
        let page_bytes = budget
            .page_rows
            .checked_mul(std::mem::size_of::<M::Record>())
            .and_then(|n| n.checked_add(4096))
            .ok_or(SourceError::ResourceLimit)?;
        if retained_bytes
            .checked_add(metadata)
            .and_then(|n| n.checked_add(page_bytes))
            .is_none_or(|n| n > budget.processor_bytes)
        {
            return Err(SourceError::ResourceLimit);
        }
        // Reserve both allocations while the caller's original source/LOD output
        // remains leased; no per-session allowance bypasses the global ledger.
        let metadata_lease = GeoProcessorLease::acquire(metadata)?;
        let page_lease = GeoProcessorLease::acquire(page_bytes)?;
        let id = next_session_identity()?;
        let source = source.clone_validated();
        let draft = SourcePage {
            features: Vec::with_capacity(budget.page_rows),
            next: None,
            chunks_considered: 0,
            chunks_read: 0,
            bytes_read: 0,
            rows_examined: 0,
        };
        Ok(Self {
            id,
            sequence,
            next_read: 1,
            source: Some(source),
            matcher,
            cursor,
            initial_cursor: cursor,
            draft: Some(draft),
            page_lease: Some(page_lease),
            published: None,
            pending: None,
            retired: Vec::with_capacity(RETIRED_LIMIT),
            metadata_lease,
            budget,
            retained_bytes,
            ready: false,
            active: true,
            disposed: false,
        })
    }
    pub fn current_sequence(&self) -> u64 {
        self.sequence
    }
    pub(crate) fn take_published(&mut self) -> Option<SourcePublished<M::Record>> {
        self.published.take()
    }
    pub(crate) fn matcher(&self) -> &M {
        &self.matcher
    }
    pub(crate) fn read_credit(&self, ticket: GeoReadTicket) -> Result<Arc<GeoProcessorLease>> {
        self.pending
            .iter()
            .chain(self.retired.iter())
            .find(|r| r.ticket == ticket)
            .map(|r| Arc::clone(&r.lease))
            .ok_or(SourceError::StaleSource)
    }
    pub fn has_outstanding_reads(&self) -> bool {
        self.pending.is_some() || !self.retired.is_empty()
    }
    fn live_bytes(&self) -> usize {
        self.retained_bytes
            + self.metadata_lease.bytes()
            + self.page_lease.as_ref().map_or(0, |l| l.bytes())
            + self.published.as_ref().map_or(0, |p| p.lease.bytes())
            + self.pending.as_ref().map_or(0, |r| r.lease.bytes())
            + self.retired.iter().map(|r| r.lease.bytes()).sum::<usize>()
    }
    fn retire(&mut self) -> Result<()> {
        if self.pending.is_some() && self.retired.len() == RETIRED_LIMIT {
            return Err(SourceError::ResourceLimit);
        }
        if let Some(read) = self.pending.take() {
            self.retired.push(read);
        }
        Ok(())
    }
    fn stop(&mut self) {
        self.draft = None;
        self.page_lease = None;
        self.source = None;
        self.active = false;
        // Data is dropped before lowering its admission lease.
        let _ = self.metadata_lease.resize(OVERHEAD);
    }
    pub fn cancel(&mut self, through: u64) -> Result<()> {
        if through >= self.sequence && self.active {
            self.retire()?;
            self.stop();
        }
        Ok(())
    }
    pub fn dispose(&mut self) -> Result<()> {
        self.retire()?;
        self.stop();
        self.published = None;
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
    pub fn step(&mut self) -> Result<GeoSessionStep> {
        if self.disposed {
            return Ok(GeoSessionStep::Disposed);
        }
        if let Some(r) = &self.pending {
            return Ok(if r.consumed {
                GeoSessionStep::AwaitRelease(r.ticket)
            } else {
                GeoSessionStep::NeedRead(r.ticket)
            });
        }
        if !self.active {
            return Ok(GeoSessionStep::Idle);
        }
        if self.ready {
            return self.publish();
        }
        let source = self.source.as_ref().unwrap();
        let page = self.draft.as_mut().unwrap();
        loop {
            let index = self.cursor.chunk_index as usize;
            if index == source.chunks().len() {
                self.ready = true;
                break;
            }
            if page.chunks_considered >= self.budget.max_chunks {
                page.next = Some(self.cursor);
                self.ready = true;
                break;
            }
            page.chunks_considered += 1;
            if !source.chunk_matches(index, self.matcher.query_spec())? {
                self.cursor.chunk_index += 1;
                self.cursor.row = 0;
                continue;
            }
            let request = source.read_request(index)?;
            if page
                .bytes_read
                .checked_add(request.encoded_bytes as u64)
                .is_none_or(|n| n > self.budget.max_read_bytes)
                || page
                    .rows_examined
                    .checked_add(request.rows as u64)
                    .is_none_or(|n| n > self.budget.max_rows_examined)
            {
                if page.chunks_read == 0 {
                    page.chunks_considered -= 1;
                    return Err(SourceError::ResourceLimit);
                }
                page.next = Some(self.cursor);
                self.ready = true;
                break;
            }
            let peak = request
                .encoded_bytes
                .checked_mul(4)
                .and_then(|n| n.checked_add(16_384))
                .ok_or(SourceError::ResourceLimit)?;
            if peak > MAX_CHUNK_PEAK
                || self
                    .live_bytes()
                    .checked_add(peak)
                    .is_none_or(|n| n > self.budget.processor_bytes)
            {
                // A failed admission doesn't issue I/O or advance the source cursor.
                self.draft.as_mut().unwrap().chunks_considered -= 1;
                return Err(SourceError::ResourceLimit);
            }
            let lease = GeoProcessorLease::acquire(peak);
            if lease.is_err() {
                self.draft.as_mut().unwrap().chunks_considered -= 1;
            }
            let lease = lease?;
            let ticket = GeoReadTicket {
                session_id: self.id,
                read_id: self.next_read,
                sequence: self.sequence,
                pass: 0,
                request,
            };
            self.next_read = self
                .next_read
                .checked_add(1)
                .ok_or(SourceError::ResourceLimit)?;
            self.pending = Some(Read {
                ticket,
                consumed: false,
                lease: Arc::new(lease),
            });
            return Ok(GeoSessionStep::NeedRead(ticket));
        }
        self.publish()
    }
    fn publish(&mut self) -> Result<GeoSessionStep> {
        if let Err(error) = self.matcher.finish(
            self.draft
                .as_ref()
                .ok_or(SourceError::InvalidFrame)?
                .next
                .is_none(),
        ) {
            self.stop();
            return Err(error);
        }
        let page = self.draft.take().unwrap();
        self.published = Some(SourcePublished {
            page,
            lease: self.page_lease.take().unwrap(),
        });
        self.active = false;
        Ok(GeoSessionStep::Complete)
    }
    pub fn supply(
        &mut self,
        ticket: GeoReadTicket,
        bytes: &[u8],
        cancelled: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        if self.disposed
            || !self.active
            || !self
                .pending
                .as_ref()
                .is_some_and(|r| r.ticket == ticket && !r.consumed)
        {
            return Err(SourceError::StaleSource);
        }
        let result = self.consume(ticket, bytes, cancelled);
        if let Some(r) = &mut self.pending {
            r.consumed = true;
        }
        if result.is_err() {
            self.stop();
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
        let chunk = parse_authenticated(
            ticket.request,
            bytes,
            self.pending.as_ref().unwrap().lease.bytes(),
        )?;
        if cancelled() {
            return Err(SourceError::Cancelled);
        }
        let page = self.draft.as_mut().unwrap();
        page.chunks_read += 1;
        page.bytes_read += bytes.len() as u64;
        page.rows_examined += ticket.request.rows as u64;
        let query = self.matcher.query_spec();
        for f in chunk.rows() {
            if f.row < self.cursor.row as usize {
                continue;
            }
            if cancelled() {
                return Err(SourceError::Cancelled);
            }
            // Temporal predicate precedes exact projected-cell testing.
            let accepts = if f.matches(query) {
                self.matcher.matches(&f, ticket.request, cancelled)
            } else {
                Ok(None)
            };
            if let Err(error) = accepts {
                if error == SourceError::ResourceLimit && self.cursor != self.initial_cursor {
                    page.next = Some(self.cursor);
                    self.ready = true;
                    return Ok(());
                }
                return Err(error);
            }
            self.cursor.row = (f.row + 1) as u32;
            if let Some(record) = accepts? {
                page.features.push(record);
                if page.features.len() == self.budget.page_rows {
                    page.next = Some(self.cursor);
                    self.ready = true;
                    return Ok(());
                }
            }
        }
        self.cursor.chunk_index += 1;
        self.cursor.row = 0;
        Ok(())
    }
}
