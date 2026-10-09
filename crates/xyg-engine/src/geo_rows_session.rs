//! Bounded original-row companion paging. Dossier §20/§27; see geo-rows-session.md.
use crate::geo::{GeoCrs, GeoGeometry};
use crate::geo_source::{
    parse_authenticated, FeatureRef, GeoSourceManifest, QueryBudget, QueryCursor, QuerySpec,
    SourceError, TimePredicate, MAX_CHUNK_PEAK,
};
use crate::geo_source_session::{
    next_session_identity, GeoProcessorLease, GeoReadTicket, GeoSessionStep,
};
type Result<T> = std::result::Result<T, SourceError>;
const OVERHEAD: usize = 16_384;
const RETIRED_LIMIT: usize = 64;

/// Exact source/time/layer/state authority, independent of viewport and reduced tier.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoRowsKey {
    pub source_digest: [u8; 8],
    pub generation: u64,
    pub source_rows: u64,
    pub geometry: GeoGeometry,
    pub crs: GeoCrs,
    pub layer_id: u64,
    pub layer_revision: u64,
    pub state_revision: u64,
    pub time_revision: u64,
    pub time: TimePredicate,
}
impl GeoRowsKey {
    fn query(self) -> QuerySpec {
        QuerySpec {
            bounds: None,
            time: self.time,
        }
    }
    fn validate(self, source: &GeoSourceManifest) -> Result<()> {
        self.time.validate()?;
        if self.source_digest != source.digest()
            || self.generation != source.generation()
            || self.source_rows != source.rows()
            || self.geometry != source.geometry()
            || self.crs != source.crs()
        {
            return Err(SourceError::StaleSource);
        }
        Ok(())
    }
}
/// Issued only by a completed page. No public ordinal/decode constructor grants skips.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoRowsCursor {
    key: GeoRowsKey,
    position: QueryCursor,
}
impl GeoRowsCursor {
    pub fn key(self) -> GeoRowsKey {
        self.key
    }
    pub fn position(self) -> QueryCursor {
        self.position
    }
}
#[derive(Debug, Clone, PartialEq)]
pub struct GeoRowsRecord {
    pub feature: FeatureRef,
    pub geometry_null: bool,
    pub time_eligible: bool,
    pub eligible: bool,
    pub intervals_present: bool,
    pub interval_start: Option<i64>,
    pub interval_end: Option<i64>,
    pub value: Option<f64>,
}
#[derive(Debug)]
pub struct GeoRowsPage {
    pub records: Vec<GeoRowsRecord>,
    pub next: Option<GeoRowsCursor>,
    pub chunks_considered: usize,
    pub chunks_read: usize,
    pub bytes_read: u64,
    pub rows_examined: u64,
}

/// Storage is dropped before the quota lease. No unleased page extraction exists.
pub struct GeoPublishedRows {
    pub sequence: u64,
    pub key: GeoRowsKey,
    pub page: GeoRowsPage,
    lease: GeoProcessorLease,
}
impl GeoPublishedRows {
    pub fn reserved_bytes(&self) -> usize {
        self.lease.bytes()
    }
}
struct Read {
    ticket: GeoReadTicket,
    consumed: bool,
    lease: GeoProcessorLease,
}
pub struct GeoRowsSession {
    id: u64,
    sequence: u64,
    key: GeoRowsKey,
    next_read: u64,
    source: Option<GeoSourceManifest>,
    cursor: QueryCursor,
    draft: Option<GeoRowsPage>,
    page_lease: Option<GeoProcessorLease>,
    published: Option<GeoPublishedRows>,
    pending: Option<Read>,
    retired: Vec<Read>,
    metadata_lease: GeoProcessorLease,
    budget: QueryBudget,
    ready: bool,
    active: bool,
    disposed: bool,
}
impl GeoRowsSession {
    #[allow(clippy::too_many_arguments)]
    pub fn create(
        source: &GeoSourceManifest,
        sequence: u64,
        key: GeoRowsKey,
        cursor: Option<GeoRowsCursor>,
        budget: QueryBudget,
    ) -> Result<Self> {
        if sequence == 0 {
            return Err(SourceError::InvalidFrame);
        }
        budget.validate()?;
        key.validate(source)?;
        let q = key.query();
        if cursor.is_some_and(|cursor| cursor.key != key) {
            return Err(SourceError::StaleSource);
        }
        let cursor = cursor.map(|cursor| cursor.position).unwrap_or(QueryCursor {
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
            .checked_mul(std::mem::size_of::<GeoRowsRecord>())
            .and_then(|n| n.checked_add(4096))
            .ok_or(SourceError::ResourceLimit)?;
        if metadata
            .checked_add(page_bytes)
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
        let draft = GeoRowsPage {
            records: Vec::with_capacity(budget.page_rows),
            next: None,
            chunks_considered: 0,
            chunks_read: 0,
            bytes_read: 0,
            rows_examined: 0,
        };
        Ok(Self {
            id,
            sequence,
            key,
            next_read: 1,
            source: Some(source),
            cursor,
            draft: Some(draft),
            page_lease: Some(page_lease),
            published: None,
            pending: None,
            retired: Vec::with_capacity(RETIRED_LIMIT),
            metadata_lease,
            budget,
            ready: false,
            active: true,
            disposed: false,
        })
    }
    pub fn key(&self) -> GeoRowsKey {
        self.key
    }
    pub fn current_sequence(&self) -> u64 {
        self.sequence
    }
    pub fn published(&self) -> Option<&GeoPublishedRows> {
        self.published.as_ref()
    }
    /// Borrowed validated manifest; callers must prelease any independent clone.
    pub fn source(&self) -> Option<&GeoSourceManifest> {
        self.source.as_ref()
    }
    pub fn has_outstanding_reads(&self) -> bool {
        self.pending.is_some() || !self.retired.is_empty()
    }
    fn live_bytes(&self) -> usize {
        self.metadata_lease.bytes()
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
        'admit: {
            let index = self.cursor.chunk_index as usize;
            if index == source.chunks().len() {
                self.ready = true;
                break 'admit;
            }
            if page.chunks_considered >= self.budget.max_chunks {
                page.next = Some(GeoRowsCursor {
                    key: self.key,
                    position: self.cursor,
                });
                self.ready = true;
                break 'admit;
            }
            page.chunks_considered += 1;
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
                page.next = Some(GeoRowsCursor {
                    key: self.key,
                    position: self.cursor,
                });
                self.ready = true;
                break 'admit;
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
                lease,
            });
            return Ok(GeoSessionStep::NeedRead(ticket));
        }
        self.publish()
    }
    fn publish(&mut self) -> Result<GeoSessionStep> {
        let page = self.draft.take().ok_or(SourceError::InvalidFrame)?;
        self.published = Some(GeoPublishedRows {
            sequence: self.sequence,
            key: self.key,
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
        for f in chunk.all_rows() {
            if cancelled() {
                return Err(SourceError::Cancelled);
            }
            if f.row < self.cursor.row as usize {
                continue;
            }
            // Time eligibility is evaluated without geometry inspection/projection.
            let time_eligible = self.key.time.matches(f.interval_start, f.interval_end);
            let geometry_null = f.column.validity()[f.row] == 0;
            self.cursor.row = (f.row + 1) as u32;
            page.records.push(GeoRowsRecord {
                feature: FeatureRef {
                    chunk_index: ticket.request.chunk_index,
                    row: f.row as u32,
                    source_row: ticket.request.first_row + f.row as u64,
                    feature_id: f.column.feature_ids()[f.row],
                },
                geometry_null,
                time_eligible,
                eligible: !geometry_null && time_eligible,
                intervals_present: chunk.intervals().is_some(),
                interval_start: f.interval_start,
                interval_end: f.interval_end,
                value: f.value,
            });
            if page.records.len() == self.budget.page_rows {
                if self.cursor.row == ticket.request.rows {
                    self.cursor.chunk_index += 1;
                    self.cursor.row = 0;
                }
                page.next = if self.cursor.chunk_index as usize
                    == self.source.as_ref().unwrap().chunks().len()
                {
                    None
                } else {
                    Some(GeoRowsCursor {
                        key: self.key,
                        position: self.cursor,
                    })
                };
                self.ready = true;
                return Ok(());
            }
        }
        self.cursor.chunk_index += 1;
        self.cursor.row = 0;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo::{GeoColumn, GeoDescriptor, GeoLimits};
    use crate::geo_source::{GeoChunk, GeoIntervals, GeoManifestBuilder, MAX_PROCESSOR_BYTES};
    use crate::geo_source_session::test_processor_lock;
    fn fixture() -> (GeoSourceManifest, Vec<Vec<u8>>, GeoRowsKey) {
        let mut builder = GeoManifestBuilder::new();
        let mut bytes = Vec::new();
        for _ in 0..2 {
            // Offscreen geography is deliberately unrelated to any painted camera.
            let column = GeoColumn::from_descriptor(GeoDescriptor {
                geometry: GeoGeometry::MultiPoint,
                crs: GeoCrs::Epsg4326,
                xy: &[
                    179., 85., 179., 84., -179., 85., -179., 84., 170., 80., 170., 79., 160., 80.,
                    160., 79.,
                ],
                validity: &[1, 1, 0, 1, 1],
                feature_ids: Some(&[u64::MAX, 7, 1 << 63, 7, 9]),
                offsets0: &[0, 2, 4, 4, 6, 8],
                offsets1: &[],
                offsets2: &[],
                limits: GeoLimits::default(),
            })
            .unwrap();
            let raw = GeoChunk::encode_with_values(
                &column,
                Some(GeoIntervals {
                    starts: &[i64::MIN, -10, 0, 0, 10],
                    ends: &[-10, 0, 0, 0, i64::MAX],
                    start_validity: &[1, 1, 0, 0, 1],
                    end_validity: &[1, 1, 0, 0, 1],
                }),
                Some(&[
                    -0.,
                    f64::from_bits(0x7ff8000000000042),
                    42.,
                    f64::INFINITY,
                    5.,
                ]),
            )
            .unwrap();
            builder
                .push(&GeoChunk::parse(&raw, MAX_CHUNK_PEAK).unwrap())
                .unwrap();
            bytes.push(raw);
        }
        let source = builder.finish(u64::MAX).unwrap();
        let key = GeoRowsKey {
            source_digest: source.digest(),
            generation: source.generation(),
            source_rows: source.rows(),
            geometry: source.geometry(),
            crs: source.crs(),
            layer_id: u64::MAX,
            layer_revision: 4,
            state_revision: 5,
            time_revision: 6,
            time: TimePredicate::Instant(-10),
        };
        (source, bytes, key)
    }
    fn drive(s: &mut GeoRowsSession, bytes: &[Vec<u8>]) -> Vec<u32> {
        let mut reads = Vec::new();
        loop {
            match s.step().unwrap() {
                GeoSessionStep::NeedRead(ticket) => {
                    reads.push(ticket.request.chunk_index);
                    s.supply(
                        ticket,
                        &bytes[ticket.request.chunk_index as usize],
                        &mut || false,
                    )
                    .unwrap();
                    assert!(s.published().is_none());
                    assert_eq!(s.step().unwrap(), GeoSessionStep::AwaitRelease(ticket));
                    s.release_read(ticket).unwrap();
                }
                GeoSessionStep::Complete => return reads,
                other => panic!("unexpected {other:?}"),
            }
        }
    }
    fn need(s: &mut GeoRowsSession) -> GeoReadTicket {
        let GeoSessionStep::NeedRead(t) = s.step().unwrap() else {
            panic!("read required")
        };
        t
    }
    #[test]
    fn original_null_offscreen_multipoint_rows_and_duplicate_full_ids_page_exactly_once() {
        let _lock = test_processor_lock();
        let baseline = GeoProcessorLease::live_bytes();
        let (source, bytes, key) = fixture();
        let budget = QueryBudget {
            page_rows: 3,
            ..QueryBudget::default()
        };
        let mut cursor = None;
        let mut records = Vec::new();
        let mut sizes = Vec::new();
        loop {
            let mut s = GeoRowsSession::create(&source, 10, key, cursor, budget).unwrap();
            drive(&mut s, &bytes);
            let page = &s.published().unwrap().page;
            sizes.push(page.records.len());
            records.extend(page.records.iter().cloned());
            cursor = page.next;
            if cursor.is_none() {
                break;
            }
        }
        assert_eq!(sizes, [3, 3, 3, 1]);
        assert_eq!(
            records
                .iter()
                .map(|r| r.feature.source_row)
                .collect::<Vec<_>>(),
            (0..10).collect::<Vec<_>>()
        );
        assert_eq!(
            records.iter().filter(|r| r.feature.feature_id == 7).count(),
            4
        );
        assert_eq!(records[0].feature.feature_id, u64::MAX);
        assert_eq!(records[2].feature.feature_id, 1 << 63);
        assert!(records[2].geometry_null && records[2].time_eligible && !records[2].eligible);
        assert_eq!(records[0].value.unwrap().to_bits(), (-0f64).to_bits());
        assert_eq!(records[1].value.unwrap().to_bits(), 0x7ff8000000000042);
        assert_eq!(records[3].value, Some(f64::INFINITY));
        assert_eq!(GeoProcessorLease::live_bytes(), baseline);
    }
    #[test]
    fn time_exclusion_is_explicit_not_row_loss_and_halfopen_null_endpoints_are_shared() {
        let _lock = test_processor_lock();
        let (source, bytes, key) = fixture();
        for (time, expected) in [
            (
                TimePredicate::Instant(-10),
                [false, true, true, true, false],
            ),
            (
                TimePredicate::Window { start: -10, end: 0 },
                [false, true, true, true, false],
            ),
            (
                TimePredicate::Instant(i64::MIN),
                [true, false, true, true, false],
            ),
            (
                TimePredicate::Instant(i64::MAX),
                [false, false, true, true, false],
            ),
            (TimePredicate::All, [true; 5]),
        ] {
            let mut s = GeoRowsSession::create(
                &source,
                1,
                GeoRowsKey { time, ..key },
                None,
                QueryBudget::default(),
            )
            .unwrap();
            assert_eq!(drive(&mut s, &bytes), [0, 1]); // no temporal pruning hides excluded/null rows
            let rows = &s.published().unwrap().page.records;
            assert_eq!(rows.len(), 10);
            assert_eq!(
                rows[..5]
                    .iter()
                    .map(|r| r.time_eligible)
                    .collect::<Vec<_>>(),
                expected
            );
            assert!(rows.iter().all(|r| r.intervals_present));
            assert_eq!(rows[0].interval_start, Some(i64::MIN));
            assert_eq!(rows[3].interval_start, None);
            assert_eq!(rows[3].interval_end, None);
        }
    }
    #[test]
    fn packed_point_null_iterator_and_missing_metadata_do_not_shift_original_rows() {
        let _lock = test_processor_lock();
        let column = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg4326,
            xy: &[1., 2., 3., 4.],
            validity: &[0, 1, 0, 1],
            feature_ids: Some(&[9, 8, 7, 6]),
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        let raw = GeoChunk::encode(&column, None).unwrap();
        let chunk = GeoChunk::parse(&raw, MAX_CHUNK_PEAK).unwrap();
        assert_eq!(chunk.rows().map(|r| r.row).collect::<Vec<_>>(), [1, 3]);
        assert_eq!(
            chunk
                .all_rows()
                .map(|r| (r.row, r.vertices))
                .collect::<Vec<_>>(),
            [(0, 0..0), (1, 0..1), (2, 1..1), (3, 1..2)]
        );
        let mut builder = GeoManifestBuilder::new();
        builder.push(&chunk).unwrap();
        let source = builder.finish(1).unwrap();
        let key = GeoRowsKey {
            source_digest: source.digest(),
            generation: 1,
            source_rows: 4,
            geometry: source.geometry(),
            crs: source.crs(),
            layer_id: 1,
            layer_revision: 0,
            state_revision: 0,
            time_revision: 0,
            time: TimePredicate::All,
        };
        let mut s = GeoRowsSession::create(
            &source,
            1,
            key,
            None,
            QueryBudget {
                page_rows: 4,
                ..QueryBudget::default()
            },
        )
        .unwrap();
        drive(&mut s, &[raw]);
        let page = &s.published().unwrap().page;
        assert!(page.next.is_none()); // exact final capacity needs no redundant final read/page
        assert_eq!(
            page.records
                .iter()
                .map(|r| r.feature.feature_id)
                .collect::<Vec<_>>(),
            [9, 8, 7, 6]
        );
        assert!(page
            .records
            .iter()
            .all(|r| !r.intervals_present && r.value.is_none()));
    }
    #[test]
    fn cursor_source_time_state_and_layer_changes_reject_before_clone_or_io() {
        let _lock = test_processor_lock();
        let (source, bytes, key) = fixture();
        let mut s = GeoRowsSession::create(
            &source,
            1,
            key,
            None,
            QueryBudget {
                page_rows: 1,
                ..QueryBudget::default()
            },
        )
        .unwrap();
        drive(&mut s, &bytes);
        let cursor = s.published().unwrap().page.next;
        let baseline = GeoProcessorLease::live_bytes();
        let variants = [
            GeoRowsKey {
                state_revision: 6,
                ..key
            },
            GeoRowsKey {
                time_revision: 7,
                ..key
            },
            GeoRowsKey {
                time: TimePredicate::All,
                ..key
            },
            GeoRowsKey {
                layer_revision: 5,
                ..key
            },
            GeoRowsKey { layer_id: 0, ..key },
            GeoRowsKey {
                generation: 1,
                ..key
            },
            GeoRowsKey {
                source_digest: [0; 8],
                ..key
            },
        ];
        for key in variants {
            assert!(matches!(
                GeoRowsSession::create(&source, 2, key, cursor, QueryBudget::default()),
                Err(SourceError::StaleSource)
            ));
            assert_eq!(GeoProcessorLease::live_bytes(), baseline);
        }
        let mut malformed = cursor.unwrap();
        malformed.position.row = 65537;
        assert!(matches!(
            GeoRowsSession::create(&source, 2, key, Some(malformed), QueryBudget::default()),
            Err(SourceError::InvalidFrame)
        ));
        assert_eq!(GeoProcessorLease::live_bytes(), baseline);
        assert!(matches!(
            GeoRowsSession::create(&source, 0, key, None, QueryBudget::default()),
            Err(SourceError::InvalidFrame)
        ));
    }
    #[test]
    fn stale_tickets_cancel_dispose_and_ack_preserve_read_charge_until_release() {
        let _lock = test_processor_lock();
        let (source, bytes, key) = fixture();
        let mut a = GeoRowsSession::create(&source, 10, key, None, QueryBudget::default()).unwrap();
        let ticket = need(&mut a);
        let mut b = GeoRowsSession::create(&source, 10, key, None, QueryBudget::default()).unwrap();
        let other = need(&mut b);
        assert!(matches!(
            a.supply(other, &bytes[0], &mut || false),
            Err(SourceError::StaleSource)
        ));
        a.cancel(9).unwrap();
        assert_eq!(a.step().unwrap(), GeoSessionStep::NeedRead(ticket));
        a.cancel(10).unwrap();
        assert!(a.has_outstanding_reads());
        let charged = GeoProcessorLease::live_bytes();
        assert!(matches!(
            a.supply(ticket, &bytes[0], &mut || false),
            Err(SourceError::StaleSource)
        ));
        a.dispose().unwrap();
        assert_eq!(a.step().unwrap(), GeoSessionStep::Disposed);
        assert_eq!(GeoProcessorLease::live_bytes(), charged);
        a.release_read(ticket).unwrap();
        assert!(!a.has_outstanding_reads());
        assert!(GeoProcessorLease::live_bytes() < charged);
        assert!(matches!(
            a.release_read(ticket),
            Err(SourceError::StaleSource)
        ));
        b.supply(other, &bytes[0], &mut || false).unwrap();
        assert_eq!(b.step().unwrap(), GeoSessionStep::AwaitRelease(other));
        b.release_read(other).unwrap();
    }
    #[test]
    fn failed_authentication_and_midrow_cancellation_publish_no_partial_page() {
        let _lock = test_processor_lock();
        let (source, bytes, key) = fixture();
        let mut old =
            GeoRowsSession::create(&source, 1, key, None, QueryBudget::default()).unwrap();
        drive(&mut old, &bytes);
        for corrupt in [true, false] {
            let mut s =
                GeoRowsSession::create(&source, 2, key, None, QueryBudget::default()).unwrap();
            let t = need(&mut s);
            let mut raw = bytes[0].clone();
            if corrupt {
                *raw.last_mut().unwrap() ^= 1;
            }
            let mut checks = 0;
            let error = s
                .supply(t, &raw, &mut || {
                    checks += 1;
                    !corrupt && checks == 5
                })
                .unwrap_err();
            assert_eq!(
                error,
                if corrupt {
                    SourceError::StaleSource
                } else {
                    SourceError::Cancelled
                }
            );
            assert!(s.published().is_none());
            assert_eq!(s.step().unwrap(), GeoSessionStep::AwaitRelease(t));
            s.release_read(t).unwrap();
            assert_eq!(s.step().unwrap(), GeoSessionStep::Idle);
            assert_eq!(old.published().unwrap().page.records.len(), 10);
        }
    }
    #[test]
    fn work_boundary_advances_and_first_chunk_budget_rejection_issues_no_ticket() {
        let _lock = test_processor_lock();
        let (source, bytes, key) = fixture();
        let budget = QueryBudget {
            max_chunks: 1,
            ..QueryBudget::default()
        };
        let mut first = GeoRowsSession::create(&source, 1, key, None, budget).unwrap();
        assert_eq!(drive(&mut first, &bytes), [0]);
        let page = &first.published().unwrap().page;
        assert_eq!(page.records.len(), 5);
        let cursor = page.next;
        let mut next = GeoRowsSession::create(&source, 2, key, cursor, budget).unwrap();
        assert_eq!(drive(&mut next, &bytes), [1]);
        assert!(next.published().unwrap().page.next.is_none());
        for budget in [
            QueryBudget {
                max_rows_examined: 4,
                ..QueryBudget::default()
            },
            QueryBudget {
                max_read_bytes: 1,
                ..QueryBudget::default()
            },
        ] {
            let mut s = GeoRowsSession::create(&source, 1, key, None, budget).unwrap();
            let baseline = GeoProcessorLease::live_bytes();
            assert_eq!(s.step(), Err(SourceError::ResourceLimit));
            assert_eq!(s.step(), Err(SourceError::ResourceLimit));
            assert_eq!(GeoProcessorLease::live_bytes(), baseline);
            assert!(!s.has_outstanding_reads());
        }
    }
    #[test]
    fn admission_precedes_allocations_and_published_rows_share_global_quota() {
        let _lock = test_processor_lock();
        let (source, bytes, key) = fixture();
        let baseline = GeoProcessorLease::live_bytes();
        assert!(matches!(
            GeoRowsSession::create(
                &source,
                1,
                key,
                None,
                QueryBudget {
                    processor_bytes: 1,
                    ..QueryBudget::default()
                }
            ),
            Err(SourceError::ResourceLimit)
        ));
        assert_eq!(GeoProcessorLease::live_bytes(), baseline);
        assert!(matches!(
            GeoRowsSession::create(
                &source,
                1,
                key,
                None,
                QueryBudget {
                    page_rows: 4097,
                    ..QueryBudget::default()
                }
            ),
            Err(SourceError::ResourceLimit)
        ));
        let mut s = GeoRowsSession::create(&source, 1, key, None, QueryBudget::default()).unwrap();
        drive(&mut s, &bytes);
        let live = GeoProcessorLease::live_bytes();
        assert!(s.published().unwrap().reserved_bytes() > 0);
        let block = GeoProcessorLease::acquire(MAX_PROCESSOR_BYTES - live).unwrap();
        assert!(matches!(
            GeoRowsSession::create(&source, 2, key, None, QueryBudget::default()),
            Err(SourceError::ResourceLimit)
        ));
        drop(block);
        drop(s);
        assert_eq!(GeoProcessorLease::live_bytes(), baseline);
    }
}
