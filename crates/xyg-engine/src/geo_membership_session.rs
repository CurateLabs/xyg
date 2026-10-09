//! Asynchronous exact geographic aggregate membership. See geo-membership-session.md.
use crate::geo_lod::{GeoCellCursor, GeoCellMembership, GeoCellQuery, GeoLodKey};
use crate::geo_source::{
    FeatureRef, FeatureView, GeoSourceManifest, MembershipPage, QueryBudget, QuerySpec,
    ReadRequest, SourceError,
};
use crate::geo_source_membership_driver::{SourceMatcher, SourceMembershipDriver};
use crate::geo_source_session::{GeoProcessorLease, GeoReadTicket, GeoSessionStep};
type Result<T> = std::result::Result<T, SourceError>;
/// Storage is dropped before the quota lease. No unleased page extraction exists.
pub struct GeoPublishedMembership {
    pub sequence: u64,
    pub key: GeoLodKey,
    pub cell: u32,
    pub membership: GeoCellMembership,
    lease: GeoProcessorLease,
}
impl GeoPublishedMembership {
    pub fn reserved_bytes(&self) -> usize {
        self.lease.bytes()
    }
}
struct Matcher(GeoCellQuery);
impl SourceMatcher for Matcher {
    type Record = FeatureRef;
    fn query_spec(&self) -> QuerySpec {
        self.0.query_spec()
    }
    fn matches(
        &mut self,
        f: &FeatureView<'_>,
        r: ReadRequest,
        c: &mut dyn FnMut() -> bool,
    ) -> Result<Option<FeatureRef>> {
        Ok(self.0.matches(f, c)?.then(|| FeatureRef {
            chunk_index: r.chunk_index,
            row: f.row as u32,
            source_row: r.first_row + f.row as u64,
            feature_id: f.column.feature_ids()[f.row],
        }))
    }
}
pub struct GeoMembershipSession {
    driver: SourceMembershipDriver<Matcher>,
    key: GeoLodKey,
    cell: u32,
    published: Option<GeoPublishedMembership>,
}
impl GeoMembershipSession {
    #[allow(clippy::too_many_arguments)]
    pub fn create(
        source: &GeoSourceManifest,
        sequence: u64,
        key: GeoLodKey,
        cell: u32,
        cursor: Option<GeoCellCursor>,
        budget: QueryBudget,
        max_projected_vertices: u64,
    ) -> Result<Self> {
        if sequence == 0 {
            return Err(SourceError::InvalidFrame);
        }
        let matcher = GeoCellQuery::new(source, key, cell, cursor, max_projected_vertices)?;
        let resume = matcher.source_cursor();
        Ok(Self {
            driver: SourceMembershipDriver::create(
                source,
                sequence,
                Matcher(matcher),
                resume,
                0,
                budget,
            )?,
            key,
            cell,
            published: None,
        })
    }
    pub fn key(&self) -> GeoLodKey {
        self.key
    }
    pub fn cell(&self) -> u32 {
        self.cell
    }
    pub fn current_sequence(&self) -> u64 {
        self.driver.current_sequence()
    }
    pub fn published(&self) -> Option<&GeoPublishedMembership> {
        self.published.as_ref()
    }
    pub fn has_outstanding_reads(&self) -> bool {
        self.driver.has_outstanding_reads()
    }
    pub fn cancel(&mut self, through: u64) -> Result<()> {
        self.driver.cancel(through)
    }
    pub fn dispose(&mut self) -> Result<()> {
        self.driver.dispose()?;
        self.published = None;
        Ok(())
    }
    pub fn release_read(&mut self, ticket: GeoReadTicket) -> Result<()> {
        self.driver.release_read(ticket)
    }
    pub fn step(&mut self) -> Result<GeoSessionStep> {
        let step = self.driver.step()?;
        if let Some(out) = self.driver.take_published() {
            let p = out.page;
            let next = p.next.map(|c| self.driver.matcher().0.wrap_cursor(c));
            self.published = Some(GeoPublishedMembership {
                sequence: self.current_sequence(),
                key: self.key,
                cell: self.cell,
                membership: GeoCellMembership {
                    page: MembershipPage {
                        features: p.features,
                        next: p.next,
                        chunks_considered: p.chunks_considered,
                        chunks_read: p.chunks_read,
                        bytes_read: p.bytes_read,
                        rows_examined: p.rows_examined,
                    },
                    next,
                    projected_vertices: self.driver.matcher().0.projected_vertices(),
                },
                lease: out.lease,
            });
        }
        Ok(step)
    }
    pub fn supply(
        &mut self,
        ticket: GeoReadTicket,
        bytes: &[u8],
        cancelled: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        self.driver.supply(ticket, bytes, cancelled)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
    use crate::geo_lod::{GeoLodIdentity, GeoReducedKind, membership_page};
    use crate::geo_source::{
        GeoChunk, GeoIntervals, GeoManifestBuilder, MAX_CHUNK_PEAK, MAX_PROCESSOR_BYTES,
        ReadRequest, TimePredicate,
    };
    use crate::geo_source_session::test_processor_lock;
    use crate::geo_viewport::GeoViewport;
    fn fixture() -> (GeoSourceManifest, Vec<Vec<u8>>, GeoLodKey) {
        let mut b = GeoManifestBuilder::new();
        let mut chunks = Vec::new();
        for part in 0..2 {
            let c = GeoColumn::from_descriptor(GeoDescriptor {
                geometry: GeoGeometry::MultiPoint,
                crs: GeoCrs::Epsg4326,
                xy: &[0.; 16],
                validity: &[1, 1, 0, 1, 1],
                feature_ids: Some(&[u64::MAX, 7, 0, 7, 1 << 63]),
                offsets0: &[0, 2, 4, 4, 6, 8],
                offsets1: &[],
                offsets2: &[],
                limits: GeoLimits::default(),
            })
            .unwrap();
            let starts = [part * 10; 5];
            let ends = [part * 10 + 10; 5];
            let raw = GeoChunk::encode(
                &c,
                Some(GeoIntervals {
                    starts: &starts,
                    ends: &ends,
                    start_validity: &[1; 5],
                    end_validity: &[1; 5],
                }),
            )
            .unwrap();
            b.push(&GeoChunk::parse(&raw, MAX_CHUNK_PEAK).unwrap())
                .unwrap();
            chunks.push(raw);
        }
        let source = b.finish(u64::MAX).unwrap();
        let camera =
            GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 0., 800., 600., 0., 0., true).unwrap();
        let key = GeoLodKey {
            identity: GeoLodIdentity {
                source_digest: source.digest(),
                generation: source.generation(),
                source_rows: source.rows(),
                crs: source.crs(),
                geometry: source.geometry(),
                layer_id: u64::MAX,
                style_revision: 8,
                state_revision: 9,
            },
            camera: camera.rebuild_key().unwrap(),
            time: TimePredicate::All,
            kind: GeoReducedKind::Cluster,
            direct: false,
            columns: 1,
            rows: 1,
        };
        (source, chunks, key)
    }
    fn drive(s: &mut GeoMembershipSession, chunks: &[Vec<u8>]) -> Vec<u32> {
        let mut reads = Vec::new();
        loop {
            match s.step().unwrap() {
                GeoSessionStep::NeedRead(t) => {
                    reads.push(t.request.chunk_index);
                    s.supply(t, &chunks[t.request.chunk_index as usize], &mut || false)
                        .unwrap();
                    assert_eq!(s.step().unwrap(), GeoSessionStep::AwaitRelease(t));
                    s.release_read(t).unwrap();
                }
                GeoSessionStep::Complete => return reads,
                other => panic!("unexpected step {other:?}"),
            }
        }
    }
    #[test]
    fn two_chunks_three_pages_exact_full_ids_multipoint_union_and_sync_parity() {
        let _lock = test_processor_lock();
        let (source, chunks, key) = fixture();
        let budget = QueryBudget {
            page_rows: 3,
            ..QueryBudget::default()
        };
        let mut cursor = None;
        let mut rows = Vec::new();
        let mut sizes = Vec::new();
        loop {
            let mut s =
                GeoMembershipSession::create(&source, 10, key, 0, cursor, budget, 100).unwrap();
            drive(&mut s, &chunks);
            let out = &s.published().unwrap().membership;
            let synchronous = membership_page(
                &source,
                &mut |r: ReadRequest| Ok(chunks[r.chunk_index as usize].clone()),
                key,
                0,
                cursor,
                budget,
                100,
                &mut || false,
            )
            .unwrap();
            assert_eq!(out.page.features, synchronous.page.features);
            assert_eq!(out.next, synchronous.next);
            assert_eq!(out.projected_vertices, synchronous.projected_vertices);
            sizes.push(out.page.features.len());
            rows.extend(out.page.features.iter().copied());
            cursor = out.next;
            if cursor.is_none() {
                break;
            }
        }
        assert_eq!(sizes, [3, 3, 2]);
        assert_eq!(
            rows.iter().map(|r| r.source_row).collect::<Vec<_>>(),
            [0, 1, 3, 4, 5, 6, 8, 9]
        );
        assert_eq!(rows.iter().filter(|r| r.feature_id == 7).count(), 4);
        assert_eq!(rows[0].feature_id, u64::MAX);
        assert_eq!(rows[3].feature_id, 1 << 63);
        // Two vertices per row qualify just once; time rejects the first chunk before I/O.
        let key = GeoLodKey {
            time: TimePredicate::Instant(10),
            ..key
        };
        let mut s =
            GeoMembershipSession::create(&source, 11, key, 0, None, QueryBudget::default(), 100)
                .unwrap();
        assert_eq!(drive(&mut s, &chunks), [1]);
        assert_eq!(
            s.published()
                .unwrap()
                .membership
                .page
                .features
                .iter()
                .map(|r| r.source_row)
                .collect::<Vec<_>>(),
            [5, 6, 8, 9]
        );
    }
    #[test]
    fn cursor_style_camera_cell_and_source_revisions_reject_before_allocation() {
        let _lock = test_processor_lock();
        let (source, chunks, key) = fixture();
        let mut s = GeoMembershipSession::create(
            &source,
            10,
            key,
            0,
            None,
            QueryBudget {
                page_rows: 1,
                ..QueryBudget::default()
            },
            100,
        )
        .unwrap();
        drive(&mut s, &chunks);
        let cursor = s.published().unwrap().membership.next;
        let before = GeoProcessorLease::live_bytes();
        let mut changed = key;
        changed.identity.style_revision += 1;
        assert!(matches!(
            GeoMembershipSession::create(
                &source,
                11,
                changed,
                0,
                cursor,
                QueryBudget::default(),
                100
            ),
            Err(SourceError::StaleSource)
        ));
        changed = key;
        changed.camera.zoom_bits = 1f64.to_bits();
        assert!(matches!(
            GeoMembershipSession::create(
                &source,
                11,
                changed,
                0,
                cursor,
                QueryBudget::default(),
                100
            ),
            Err(SourceError::StaleSource)
        ));
        changed = key;
        changed.columns = 2;
        assert!(matches!(
            GeoMembershipSession::create(
                &source,
                11,
                changed,
                1,
                cursor,
                QueryBudget::default(),
                100
            ),
            Err(SourceError::StaleSource)
        ));
        changed = key;
        changed.identity.generation = 1;
        assert!(matches!(
            GeoMembershipSession::create(
                &source,
                11,
                changed,
                0,
                cursor,
                QueryBudget::default(),
                100
            ),
            Err(SourceError::StaleSource)
        ));
        assert_eq!(GeoProcessorLease::live_bytes(), before);
    }
    #[test]
    fn cancel_dispose_retire_reads_and_stale_cross_session_ticket_cannot_advance() {
        let _lock = test_processor_lock();
        let (source, chunks, key) = fixture();
        let mut old =
            GeoMembershipSession::create(&source, 10, key, 0, None, QueryBudget::default(), 100)
                .unwrap();
        let GeoSessionStep::NeedRead(ticket) = old.step().unwrap() else {
            panic!()
        };
        old.cancel(9).unwrap();
        assert_eq!(old.step().unwrap(), GeoSessionStep::NeedRead(ticket));
        let mut newer =
            GeoMembershipSession::create(&source, 10, key, 0, None, QueryBudget::default(), 100)
                .unwrap();
        let GeoSessionStep::NeedRead(new_ticket) = newer.step().unwrap() else {
            panic!()
        };
        assert_ne!(ticket.session_id, new_ticket.session_id);
        old.cancel(10).unwrap();
        let live = GeoProcessorLease::live_bytes();
        assert!(old.has_outstanding_reads());
        assert_eq!(
            newer.supply(ticket, &chunks[0], &mut || false),
            Err(SourceError::StaleSource)
        );
        assert_eq!(newer.step().unwrap(), GeoSessionStep::NeedRead(new_ticket));
        assert_eq!(
            old.supply(ticket, &chunks[0], &mut || false),
            Err(SourceError::StaleSource)
        );
        old.release_read(ticket).unwrap();
        assert!(GeoProcessorLease::live_bytes() < live);
        newer.dispose().unwrap();
        assert_eq!(newer.step().unwrap(), GeoSessionStep::Disposed);
        assert!(newer.has_outstanding_reads());
        newer.release_read(new_ticket).unwrap();
        assert!(!newer.has_outstanding_reads());
    }
    #[test]
    fn global_admission_includes_old_pages_and_clone_and_pending_read() {
        let _lock = test_processor_lock();
        let (source, chunks, key) = fixture();
        let baseline = GeoProcessorLease::live_bytes();
        let mut old =
            GeoMembershipSession::create(&source, 10, key, 0, None, QueryBudget::default(), 100)
                .unwrap();
        drive(&mut old, &chunks);
        let live = GeoProcessorLease::live_bytes();
        let blocker = GeoProcessorLease::acquire(MAX_PROCESSOR_BYTES - live).unwrap();
        assert!(matches!(
            GeoMembershipSession::create(&source, 11, key, 0, None, QueryBudget::default(), 100),
            Err(SourceError::ResourceLimit)
        ));
        assert_eq!(old.published().unwrap().membership.page.features.len(), 8);
        drop(blocker);
        let mut next =
            GeoMembershipSession::create(&source, 11, key, 0, None, QueryBudget::default(), 100)
                .unwrap();
        let live = GeoProcessorLease::live_bytes();
        let blocker = GeoProcessorLease::acquire(MAX_PROCESSOR_BYTES - live).unwrap();
        assert_eq!(next.step(), Err(SourceError::ResourceLimit));
        assert!(!next.has_outstanding_reads());
        drop(blocker);
        drive(&mut next, &chunks);
        drop(next);
        drop(old);
        assert_eq!(GeoProcessorLease::live_bytes(), baseline);
    }
    #[test]
    fn read_and_row_work_publish_progress_but_stalled_chunk_fails_before_read() {
        let _lock = test_processor_lock();
        let (source, chunks, key) = fixture();
        let budget = QueryBudget {
            max_rows_examined: 5,
            ..QueryBudget::default()
        };
        let mut s = GeoMembershipSession::create(&source, 10, key, 0, None, budget, 100).unwrap();
        assert_eq!(drive(&mut s, &chunks), [0]);
        let next = s.published().unwrap().membership.next.unwrap();
        assert_eq!(next.source.chunk_index, 1);
        assert_eq!(next.source.row, 0);
        let mut resume =
            GeoMembershipSession::create(&source, 11, key, 0, Some(next), budget, 100).unwrap();
        assert_eq!(drive(&mut resume, &chunks), [1]);
        let mut failed = GeoMembershipSession::create(
            &source,
            12,
            key,
            0,
            None,
            QueryBudget {
                max_rows_examined: 4,
                ..QueryBudget::default()
            },
            100,
        )
        .unwrap();
        assert_eq!(failed.step(), Err(SourceError::ResourceLimit));
        assert_eq!(failed.step(), Err(SourceError::ResourceLimit));
        assert!(!failed.has_outstanding_reads());
        let mut bytes = GeoMembershipSession::create(
            &source,
            13,
            key,
            0,
            None,
            QueryBudget {
                max_read_bytes: chunks[0].len() as u64,
                ..QueryBudget::default()
            },
            100,
        )
        .unwrap();
        assert_eq!(drive(&mut bytes, &chunks), [0]);
        assert_eq!(
            bytes
                .published()
                .unwrap()
                .membership
                .next
                .unwrap()
                .source
                .chunk_index,
            1
        );
    }
    #[test]
    fn projection_budget_resumes_exact_row_without_empty_same_cursor_loop() {
        let _lock = test_processor_lock();
        let (source, chunks, key) = fixture();
        let mut first =
            GeoMembershipSession::create(&source, 10, key, 0, None, QueryBudget::default(), 1)
                .unwrap();
        drive(&mut first, &chunks);
        let page = &first.published().unwrap().membership;
        assert_eq!(page.page.features.len(), 1);
        let cursor = page.next.unwrap();
        assert_eq!(cursor.source.row, 1);
        let mut resumed = GeoMembershipSession::create(
            &source,
            11,
            key,
            0,
            Some(cursor),
            QueryBudget::default(),
            1,
        )
        .unwrap();
        drive(&mut resumed, &chunks);
        assert_eq!(
            resumed.published().unwrap().membership.page.features[0].source_row,
            1
        );
        assert_ne!(resumed.published().unwrap().membership.next, Some(cursor));
        // A first feature that cannot complete within its vertex budget rejects,
        // rather than returning the unchanged cursor forever.
        let far_camera =
            GeoViewport::new(GeoCrs::Epsg4326, 100., 0., 2., 800., 600., 0., 0., true).unwrap();
        let far = GeoLodKey {
            camera: far_camera.rebuild_key().unwrap(),
            ..key
        };
        let mut stalled = GeoMembershipSession::create(
            &source,
            12,
            far,
            0,
            Some(GeoCellCursor { key: far, ..cursor }),
            QueryBudget::default(),
            1,
        )
        .unwrap();
        let GeoSessionStep::NeedRead(t) = stalled.step().unwrap() else {
            panic!()
        };
        assert_eq!(
            stalled.supply(t, &chunks[0], &mut || false),
            Err(SourceError::ResourceLimit)
        );
        stalled.release_read(t).unwrap();
        assert!(stalled.published().is_none());
    }
}
