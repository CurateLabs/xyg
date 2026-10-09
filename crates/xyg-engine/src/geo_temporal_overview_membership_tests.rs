use super::*;
use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
use crate::geo_source::{
    GeoChunk, GeoIntervals, GeoManifestBuilder, GeoSourceManifest, MAX_CHUNK_PEAK, QueryBudget,
    SourceError, TimePredicate,
};
use crate::geo_source_session::{GeoOperationSnapshot, GeoProcessorLease, test_processor_lock};
use crate::geo_temporal_overview::{
    GeoOverviewQuerySession, GeoOverviewResult, GeoOverviewStep, ValidatedGeoOverview,
};
use crate::geo_temporal_overview_build::GeoOverviewBuildSession;
use crate::geo_viewport::GeoViewport;
use std::collections::BTreeMap;
use std::sync::Arc;
fn fixture(crs: GeoCrs) -> (GeoSourceManifest, Vec<Vec<u8>>) {
    let xy = if crs == GeoCrs::Epsg4326 {
        vec![
            0., 0., 0.01, 0., 179., 0., 0., 0., 0., 0., -179., 0., 0., 0.,
        ]
    } else {
        vec![
            0.,
            0.,
            1000.,
            0.,
            19_926_188.851_995_97,
            0.,
            0.,
            0.,
            0.,
            0.,
            -19_926_188.851_995_97,
            0.,
            0.,
            0.,
        ]
    };
    let column = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::MultiPoint,
        crs,
        xy: &xy,
        validity: &[1, 1, 0, 1, 1, 1, 1],
        feature_ids: Some(&[u64::MAX, u64::MAX, 0, 1 << 63, (1 << 53) + 1, 7, 8]),
        offsets0: &[0, 2, 3, 3, 5, 6, 6, 7],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let raw = GeoChunk::encode(
        &column,
        Some(GeoIntervals {
            starts: &[i64::MIN, 0, 0, 10, 0, 0, i64::MAX - 1],
            ends: &[0, 10, 0, i64::MAX, 0, 0, i64::MAX],
            start_validity: &[1, 1, 0, 1, 0, 0, 1],
            end_validity: &[1, 1, 0, 1, 0, 0, 1],
        }),
    )
    .unwrap();
    let mut builder = GeoManifestBuilder::new();
    let chunks = vec![raw.clone(), raw];
    for raw in &chunks {
        builder
            .push(&GeoChunk::parse(raw, MAX_CHUNK_PEAK).unwrap())
            .unwrap();
    }
    (builder.finish(u64::MAX).unwrap(), chunks)
}
fn index(
    source: &GeoSourceManifest,
    chunks: &[Vec<u8>],
) -> (Arc<ValidatedGeoOverview>, BTreeMap<u64, Vec<u8>>) {
    let mut session = GeoOverviewBuildSession::new(source, QueryBudget::default(), 1000).unwrap();
    let mut pages = BTreeMap::new();
    loop {
        match session.step().unwrap() {
            GeoOverviewStep::NeedRead(t) => {
                let bytes = t.source_request().map_or_else(
                    || pages.get(&t.page_id()).unwrap(),
                    |r| &chunks[r.chunk_index as usize],
                );
                session.supply(&t, bytes).unwrap();
                session.release_read(&t).unwrap();
            }
            GeoOverviewStep::NeedWrite(t) => {
                pages.insert(t.page_id(), session.write_bytes(&t).unwrap().to_vec());
                session.ack_write(&t).unwrap();
            }
            GeoOverviewStep::Complete => return (session.take_index().unwrap(), pages),
            _ => panic!(),
        }
    }
}
fn result(
    index: Arc<ValidatedGeoOverview>,
    pages: &BTreeMap<u64, Vec<u8>>,
    time: TimePredicate,
) -> Arc<GeoOverviewResult> {
    // An intentionally unrelated camera proves domain membership includes offscreen rows.
    let camera =
        GeoViewport::new(GeoCrs::Epsg4326, 130., 60., 24., 80., 60., 35., 40., false).unwrap();
    let snapshot = GeoOperationSnapshot {
        source_digest: index.source().digest(),
        generation: index.source().generation(),
        camera: camera.rebuild_key().unwrap(),
        time,
        camera_revision: 7,
        time_revision: 8,
        layer_id: u64::MAX,
        layer_revision: 9,
        style_revision: 10,
        state_revision: 11,
    };
    let mut query = GeoOverviewQuerySession::new(index, snapshot, camera).unwrap();
    loop {
        match query.step().unwrap() {
            GeoOverviewStep::NeedRead(t) => {
                query.supply(&t, &pages[&t.page_id()]).unwrap();
                query.release_read(&t).unwrap();
            }
            GeoOverviewStep::Complete => return Arc::new(query.take_result().unwrap()),
            _ => panic!(),
        }
    }
}
fn drive(s: &mut GeoOverviewMembershipSession, chunks: &[Vec<u8>]) {
    loop {
        match s.step().unwrap() {
            GeoOverviewMembershipStep::NeedRead(t) => {
                s.supply(&t, &chunks[t.request().chunk_index as usize], &mut || false)
                    .unwrap();
                assert!(matches!(
                    s.step().unwrap(),
                    GeoOverviewMembershipStep::AwaitRelease(_)
                ));
                s.release_read(&t).unwrap();
            }
            GeoOverviewMembershipStep::Complete => break,
            _ => panic!(),
        }
    }
}
#[test]
fn temporal_cells_goldens_all_instant_window_extrema_and_crs() {
    let _lock = test_processor_lock();
    for crs in [GeoCrs::Epsg4326, GeoCrs::Epsg3857] {
        let (source, chunks) = fixture(crs);
        let (idx, pages) = index(&source, &chunks);
        // Independent rows/vertex goldens, two identical chunks. Cell136 contains x/y≈0.
        for (time, rows, total) in [
            (TimePredicate::All, vec![0, 3, 6, 7, 10, 13], 10),
            (TimePredicate::Instant(i64::MIN), vec![0, 7], 4),
            (TimePredicate::Instant(0), vec![], 0),
            (TimePredicate::Instant(10), vec![3, 10], 4),
            (TimePredicate::Instant(i64::MAX), vec![], 0),
            (
                TimePredicate::Window { start: -1, end: 11 },
                vec![0, 3, 7, 10],
                8,
            ),
            (TimePredicate::Instant(i64::MAX - 1), vec![3, 6, 10, 13], 6),
        ] {
            let r = result(Arc::clone(&idx), &pages, time);
            assert_eq!(r.counts()[136], total);
            let mut s =
                GeoOverviewMembershipSession::create(r, 136, 1, None, QueryBudget::default(), 100)
                    .unwrap();
            drive(&mut s, &chunks);
            let out = s.published().unwrap();
            assert!(out.complete());
            assert_eq!(
                out.records()
                    .iter()
                    .map(|r| r.feature.source_row)
                    .collect::<Vec<_>>(),
                rows
            );
            assert_eq!(
                out.records()
                    .iter()
                    .map(|r| r.matched_vertices)
                    .sum::<u64>(),
                total
            );
            assert_eq!(out.cumulative_vertices(), total);
            for record in out.records() {
                assert_eq!(
                    record.feature.feature_id,
                    if record.feature.row == 0 {
                        u64::MAX
                    } else if record.feature.row == 3 {
                        1 << 63
                    } else {
                        8
                    }
                );
            }
        }
        for (cell, id) in [(128, (1 << 53) + 1), (143, u64::MAX)] {
            let r = result(Arc::clone(&idx), &pages, TimePredicate::All);
            let mut s =
                GeoOverviewMembershipSession::create(r, cell, 2, None, QueryBudget::default(), 100)
                    .unwrap();
            drive(&mut s, &chunks);
            assert_eq!(s.published().unwrap().records().len(), 2);
            assert!(
                s.published()
                    .unwrap()
                    .records()
                    .iter()
                    .all(|r| r.feature.feature_id == id && r.matched_vertices == 1)
            );
        }
    }
}
#[test]
fn three_pages_private_continuation_source_order_duplicates_and_disposal() {
    let _lock = test_processor_lock();
    let (source, chunks) = fixture(GeoCrs::Epsg4326);
    let (idx, pages) = index(&source, &chunks);
    let r = result(Arc::clone(&idx), &pages, TimePredicate::All);
    drop(idx);
    drop(source);
    drop(pages);
    let b = QueryBudget {
        page_rows: 2,
        ..QueryBudget::default()
    };
    let mut prior = None;
    let mut got = Vec::new();
    let mut sequence = 1;
    loop {
        let mut s = GeoOverviewMembershipSession::create(
            Arc::clone(&r),
            136,
            sequence,
            prior.as_ref(),
            b,
            100,
        )
        .unwrap();
        drive(&mut s, &chunks);
        let out = s.take_page().unwrap();
        s.dispose().unwrap();
        got.extend_from_slice(out.records());
        let complete = out.complete();
        prior = Some(out);
        sequence += 1;
        if complete {
            break;
        }
    }
    assert_eq!(
        got.iter().map(|r| r.feature.source_row).collect::<Vec<_>>(),
        [0, 3, 6, 7, 10, 13]
    );
    assert_eq!(prior.as_ref().unwrap().cumulative_vertices(), 10);
    assert!(
        GeoOverviewMembershipSession::create(r, 136, sequence, prior.as_ref(), b, 100).is_err()
    );
}
#[test]
fn continuation_rejects_other_result_cell_sequence_without_allocating() {
    let _lock = test_processor_lock();
    let (source, chunks) = fixture(GeoCrs::Epsg4326);
    let (idx, pages) = index(&source, &chunks);
    let r = result(Arc::clone(&idx), &pages, TimePredicate::All);
    let other = result(idx, &pages, TimePredicate::All);
    let b = QueryBudget {
        page_rows: 1,
        ..QueryBudget::default()
    };
    let mut s =
        GeoOverviewMembershipSession::create(Arc::clone(&r), 136, 10, None, b, 100).unwrap();
    drive(&mut s, &chunks);
    let old = s.take_page().unwrap();
    drop(s);
    let baseline = GeoProcessorLease::live_bytes();
    for (result, cell, sequence) in [
        (Arc::clone(&other), 136, 11),
        (Arc::clone(&r), 137, 11),
        (Arc::clone(&r), 136, 10),
    ] {
        assert!(matches!(
            GeoOverviewMembershipSession::create(result, cell, sequence, Some(&old), b, 100),
            Err(SourceError::StaleSource)
        ));
        assert_eq!(GeoProcessorLease::live_bytes(), baseline);
    }
}
#[test]
fn vertex_budget_is_row_atomic_progress_then_no_progress_rejection() {
    let _lock = test_processor_lock();
    let (source, chunks) = fixture(GeoCrs::Epsg4326);
    let (idx, pages) = index(&source, &chunks);
    let r = result(idx, &pages, TimePredicate::All);
    let mut s = GeoOverviewMembershipSession::create(
        Arc::clone(&r),
        136,
        1,
        None,
        QueryBudget::default(),
        3,
    )
    .unwrap();
    drive(&mut s, &chunks);
    let page = s.take_page().unwrap();
    assert_eq!(page.records().len(), 1);
    assert_eq!(page.records()[0].matched_vertices, 2);
    assert!(!page.complete());
    let mut next =
        GeoOverviewMembershipSession::create(r, 136, 2, Some(&page), QueryBudget::default(), 1)
            .unwrap();
    let t = match next.step().unwrap() {
        GeoOverviewMembershipStep::NeedRead(t) => t,
        _ => panic!(),
    };
    assert_eq!(
        next.supply(&t, &chunks[0], &mut || false),
        Err(SourceError::ResourceLimit)
    );
    next.release_read(&t).unwrap();
    assert!(next.published().is_none());
}
#[test]
fn owning_loan_cancel_drop_exact_ack_and_corruption_preserve_old_page() {
    let _lock = test_processor_lock();
    let (source, chunks) = fixture(GeoCrs::Epsg4326);
    let (idx, pages) = index(&source, &chunks);
    let r = result(idx, &pages, TimePredicate::All);
    let b = QueryBudget {
        page_rows: 1,
        ..QueryBudget::default()
    };
    let mut old =
        GeoOverviewMembershipSession::create(Arc::clone(&r), 136, 1, None, b, 100).unwrap();
    drive(&mut old, &chunks);
    let old = old.take_page().unwrap();
    let mut s =
        GeoOverviewMembershipSession::create(Arc::clone(&r), 136, 2, Some(&old), b, 100).unwrap();
    let t = match s.step().unwrap() {
        GeoOverviewMembershipStep::NeedRead(t) => t,
        _ => panic!(),
    };
    let loan = t.reserved_bytes();
    let mut foreign =
        GeoOverviewMembershipSession::create(Arc::clone(&r), 136, 3, None, b, 100).unwrap();
    assert_eq!(foreign.release_read(&t), Err(SourceError::StaleSource));
    s.cancel(2).unwrap();
    assert!(s.has_outstanding_reads());
    assert_eq!(
        s.supply(&t, &chunks[0], &mut || false),
        Err(SourceError::StaleSource)
    );
    let charged = GeoProcessorLease::live_bytes();
    s.release_read(&t).unwrap();
    assert_eq!(GeoProcessorLease::live_bytes(), charged);
    drop(s);
    let held = GeoProcessorLease::live_bytes();
    drop(t);
    assert_eq!(GeoProcessorLease::live_bytes(), held - loan);
    let mut bad = GeoOverviewMembershipSession::create(r, 136, 4, Some(&old), b, 100).unwrap();
    let t = match bad.step().unwrap() {
        GeoOverviewMembershipStep::NeedRead(t) => t,
        _ => panic!(),
    };
    let mut bytes = chunks[0].clone();
    let last = bytes.len() - 1;
    bytes[last] ^= 1;
    assert!(bad.supply(&t, &bytes, &mut || false).is_err());
    bad.release_read(&t).unwrap();
    assert!(bad.published().is_none());
    assert_eq!(old.records()[0].feature.feature_id, u64::MAX);
}

#[test]
fn exact_local_admission_global_pressure_and_ticket_drop_lifetime() {
    let _lock = test_processor_lock();
    let (source, chunks) = fixture(GeoCrs::Epsg4326);
    let (idx, pages) = index(&source, &chunks);
    let r = result(idx, &pages, TimePredicate::All);
    let required = r.retained_bytes()
        + source.clone_reserved_bytes()
        + 16_384
        + 4096
        + std::mem::size_of::<GeoOverviewMember>();
    let before = GeoProcessorLease::live_bytes();
    let mut b = QueryBudget {
        page_rows: 1,
        processor_bytes: required - 1,
        ..QueryBudget::default()
    };
    assert!(matches!(
        GeoOverviewMembershipSession::create(Arc::clone(&r), 136, 1, None, b, 100),
        Err(SourceError::ResourceLimit)
    ));
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    b.processor_bytes += 1;
    let mut s = GeoOverviewMembershipSession::create(Arc::clone(&r), 136, 1, None, b, 100).unwrap();
    // Creation includes retained authority, but even one canonical read needs extra room.
    assert!(matches!(s.step(), Err(SourceError::ResourceLimit)));
    assert!(!s.has_outstanding_reads());
    drop(s);
    let pressure = GeoProcessorLease::acquire(
        crate::geo_source::MAX_PROCESSOR_BYTES - GeoProcessorLease::live_bytes(),
    )
    .unwrap();
    assert!(matches!(
        GeoOverviewMembershipSession::create(
            Arc::clone(&r),
            136,
            2,
            None,
            QueryBudget::default(),
            100
        ),
        Err(SourceError::ResourceLimit)
    ));
    drop(pressure);
    let mut s =
        GeoOverviewMembershipSession::create(r, 136, 2, None, QueryBudget::default(), 100).unwrap();
    let t = match s.step().unwrap() {
        GeoOverviewMembershipStep::NeedRead(t) => t,
        _ => panic!(),
    };
    let loan = t.reserved_bytes();
    drop(s);
    let live = GeoProcessorLease::live_bytes();
    assert!(live >= loan);
    drop(t);
    assert_eq!(GeoProcessorLease::live_bytes(), live - loan);
}
#[test]
fn time_before_geometry_and_final_count_reconciliation_and_cancel_publication() {
    let _lock = test_processor_lock();
    // Excluded malformed geometry must not be sliced by matching policy.
    let column = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::Point,
        crs: GeoCrs::Epsg4326,
        xy: &[0., 0.],
        validity: &[1],
        feature_ids: None,
        offsets0: &[],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let malformed = crate::geo_source::FeatureView {
        column: &column,
        row: 0,
        vertices: usize::MAX..usize::MAX,
        interval_start: Some(10),
        interval_end: Some(20),
        value: None,
    };
    let mut m = super::Matcher {
        query: crate::geo_source::QuerySpec {
            bounds: None,
            time: TimePredicate::Instant(0),
        },
        cell: 136,
        expected: 0,
        cumulative: 0,
        examined_vertices: 0,
        max_vertices: 1,
    };
    let (source, chunks) = fixture(GeoCrs::Epsg4326);
    use crate::geo_source_membership_driver::SourceMatcher;
    assert_eq!(
        m.matches(&malformed, source.read_request(0).unwrap(), &mut || panic!(
            "excluded row cannot call geometry cancellation"
        )),
        Ok(None)
    );
    m.expected = 1;
    assert_eq!(m.finish(true), Err(SourceError::InvalidFrame));
    let (idx, pages) = index(&source, &chunks);
    let r = result(idx, &pages, TimePredicate::All);
    let mut s =
        GeoOverviewMembershipSession::create(r, 136, 1, None, QueryBudget::default(), 100).unwrap();
    // Both chunks are fully processed and ACKed; cancellation just before publication cannot expose a page.
    for chunk in &chunks {
        let t = match s.step().unwrap() {
            GeoOverviewMembershipStep::NeedRead(t) => t,
            _ => panic!(),
        };
        s.supply(&t, chunk, &mut || false).unwrap();
        s.release_read(&t).unwrap();
    }
    let mut calls = 0;
    assert!(matches!(
        s.step_with_cancel(&mut || {
            calls += 1;
            calls == 2
        })
        .unwrap(),
        GeoOverviewMembershipStep::Cancelled
    ));
    assert!(s.published().is_none());
    assert!(!s.has_outstanding_reads());
}
#[test]
fn final_vertex_cancel_ack_retains_ticket_and_old_result() {
    let _lock = test_processor_lock();
    let (source, chunks) = fixture(GeoCrs::Epsg4326);
    let (idx, pages) = index(&source, &chunks);
    let r = result(idx, &pages, TimePredicate::All);
    let expected = *r.counts();
    let mut s = GeoOverviewMembershipSession::create(
        Arc::clone(&r),
        136,
        1,
        None,
        QueryBudget::default(),
        100,
    )
    .unwrap();
    let t = match s.step().unwrap() {
        GeoOverviewMembershipStep::NeedRead(t) => t,
        _ => panic!(),
    };
    let mut calls = 0;
    assert_eq!(
        s.supply(&t, &chunks[0], &mut || {
            calls += 1;
            calls == 6
        }),
        Err(SourceError::Cancelled)
    );
    assert!(s.has_outstanding_reads());
    s.release_read(&t).unwrap();
    assert!(matches!(
        s.step().unwrap(),
        GeoOverviewMembershipStep::Cancelled
    ));
    assert!(s.published().is_none());
    assert_eq!(*r.counts(), expected);
}

#[test]
fn point_all_cells_partition_exact_counts_and_full_ids_across_crs() {
    let _lock = test_processor_lock();
    for crs in [GeoCrs::Epsg4326, GeoCrs::Epsg3857] {
        let xy = if crs == GeoCrs::Epsg4326 {
            vec![-180., 0., 180., 0., 0., 90., 0., -90., 0., 0.]
        } else {
            let m = crate::geo_viewport::WEB_MERCATOR_MAX;
            vec![-m, 0., m, 0., 0., m, 0., -m, 0., 0.]
        };
        let c = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs,
            xy: &xy,
            validity: &[1, 1, 1, 1, 0, 1],
            feature_ids: Some(&[u64::MAX, u64::MAX, 1 << 63, 7, 0, 8]),
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        let raw = GeoChunk::encode(&c, None).unwrap();
        let mut b = GeoManifestBuilder::new();
        b.push(&GeoChunk::parse(&raw, MAX_CHUNK_PEAK).unwrap())
            .unwrap();
        let source = b.finish(1).unwrap();
        let (idx, pages) = index(&source, std::slice::from_ref(&raw));
        let r = result(idx, &pages, TimePredicate::All);
        let mut records = Vec::new();
        for cell in 0..256 {
            let mut s = GeoOverviewMembershipSession::create(
                Arc::clone(&r),
                cell,
                1,
                None,
                QueryBudget::default(),
                100,
            )
            .unwrap();
            drive(&mut s, std::slice::from_ref(&raw));
            let out = s.published().unwrap();
            assert!(out.complete());
            assert_eq!(out.cumulative_vertices(), r.counts()[cell as usize]);
            records.extend_from_slice(out.records());
        }
        records.sort_by_key(|r| r.feature.source_row);
        assert_eq!(
            records
                .iter()
                .map(|r| r.feature.source_row)
                .collect::<Vec<_>>(),
            [0, 1, 2, 3, 5]
        );
        assert!(records.iter().all(|r| r.matched_vertices == 1));
        assert_eq!(records[0].feature.feature_id, u64::MAX);
        assert_eq!(records[1].feature.feature_id, u64::MAX);
        assert_eq!(r.counts().iter().sum::<u64>(), 5);
    }
}
