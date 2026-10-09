use super::geo_spatial_hierarchy::*;
use super::geo_spatial_hierarchy_build::GeoHierarchyBuildSession;
use super::geo_spatial_hierarchy_query::*;
use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
use crate::geo_lod::{self, GeoLodOptions, GeoPointOutput, GeoPointResult, GeoReducedKind};
use crate::geo_source::{
    GeoChunk, GeoIntervals, GeoManifestBuilder, GeoSourceManifest, QueryBudget, ReadRequest,
    TimePredicate,
};
use crate::geo_source_session::test_processor_lock;
use crate::geo_viewport::GeoViewport;
use std::{collections::BTreeMap, sync::Arc};
type Store = BTreeMap<u64, Vec<u8>>;
fn camera(x: f64, zoom: f64) -> GeoViewport {
    GeoViewport::new(GeoCrs::Epsg4326, x, 0., zoom, 800., 600., 27., 0., true).unwrap()
}
fn chunk(
    crs: GeoCrs,
    kind: GeoGeometry,
    xy: &[f64],
    offsets: &[u32],
    valid: &[u8],
    ids: &[u64],
    time: Option<GeoIntervals<'_>>,
) -> GeoChunk {
    let column = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: kind,
        crs,
        xy,
        validity: valid,
        feature_ids: Some(ids),
        offsets0: offsets,
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    GeoChunk::parse(&GeoChunk::encode(&column, time).unwrap(), 96 << 20).unwrap()
}
fn source(chunks: &[GeoChunk]) -> (GeoSourceManifest, Vec<Vec<u8>>) {
    let mut m = GeoManifestBuilder::new();
    let mut raw = Vec::new();
    for c in chunks {
        m.push(c).unwrap();
        raw.push(GeoChunk::encode_with_values(c.column(), c.intervals(), c.values()).unwrap());
    }
    (m.finish(u64::MAX).unwrap(), raw)
}
fn budget() -> QueryBudget {
    QueryBudget {
        max_rows_examined: 2_000_000_000,
        max_read_bytes: 64 << 30,
        ..QueryBudget::default()
    }
}
fn drive_build(
    s: &mut GeoHierarchyBuildSession,
    raw: &[Vec<u8>],
    store: &mut Store,
) -> Result<Arc<ValidatedGeoHierarchy>> {
    loop {
        match s.step()? {
            GeoHierarchyStep::NeedRead(t) => {
                let b = if let Some(r) = t.source_request() {
                    raw[r.chunk_index as usize].clone()
                } else {
                    store[&t.page_id()].clone()
                };
                s.supply(&t, &b)?;
                s.release_read(&t)?;
            }
            GeoHierarchyStep::NeedWrite(t) => {
                store.insert(t.page_id(), s.write_bytes(&t)?.to_vec());
                s.acknowledge_write(&t)?;
            }
            GeoHierarchyStep::Complete => return s.finish(),
            other => panic!("unexpected build {other:?}"),
        }
    }
}
fn build(m: &GeoSourceManifest, raw: &[Vec<u8>], grid: u32) -> (Arc<ValidatedGeoHierarchy>, Store) {
    let mut s = GeoHierarchyBuildSession::new(
        m,
        GeoHierarchyOptions { grid },
        budget(),
        2_000_000_000,
        64 << 30,
    )
    .unwrap();
    let mut store = Store::new();
    let index = drive_build(&mut s, raw, &mut store).unwrap();
    (index, store)
}
fn query(
    i: Arc<ValidatedGeoHierarchy>,
    store: &Store,
    camera: GeoViewport,
    time: TimePredicate,
    options: GeoLodOptions,
) -> Result<Option<GeoHierarchyResult>> {
    let mut s = GeoHierarchyQuerySession::new(
        i,
        camera,
        time,
        options,
        u64::MAX,
        u64::MAX,
        u64::MAX,
        GeoHierarchyQueryLimits::default(),
    )?;
    loop {
        match s.step()? {
            GeoHierarchyStep::NeedRead(t) => {
                s.supply(&t, &store[&t.page_id()])?;
                s.release_read(&t)?;
            }
            GeoHierarchyStep::Complete => return Ok(Some(s.finish()?)),
            GeoHierarchyStep::FullScanFrontier | GeoHierarchyStep::FullScanWork => return Ok(None),
            other => panic!("unexpected query {other:?}"),
        }
    }
}
fn equal(a: &GeoPointResult, b: &GeoPointResult) {
    assert_eq!(a.key, b.key);
    assert_eq!(a.visible_vertices, b.visible_vertices);
    assert_eq!(a.grid_capped, b.grid_capped);
    match (&a.output, &b.output) {
        (GeoPointOutput::Direct(a), GeoPointOutput::Direct(b)) => assert_eq!(a, b),
        (GeoPointOutput::Reduced(a), GeoPointOutput::Reduced(b)) => {
            assert_eq!(a.len(), b.len());
            for (a, b) in a.iter().zip(b) {
                assert_eq!(
                    (a.count, a.x.to_bits(), a.y.to_bits()),
                    (b.count, b.x.to_bits(), b.y.to_bits())
                );
            }
        }
        _ => panic!("tier mismatch"),
    }
    let style = crate::geo_layers::GeoStyle::default();
    assert_eq!(
        crate::geo_lod_scene::compile(a, style, 32 << 20)
            .unwrap()
            .scene,
        crate::geo_lod_scene::compile(b, style, 32 << 20)
            .unwrap()
            .scene
    );
}
fn compare(
    m: &GeoSourceManifest,
    raw: &[Vec<u8>],
    i: Arc<ValidatedGeoHierarchy>,
    store: &Store,
    camera: GeoViewport,
    time: TimePredicate,
    options: GeoLodOptions,
) {
    let expected = geo_lod::process(
        m,
        &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
        camera,
        time,
        u64::MAX,
        u64::MAX,
        u64::MAX,
        options,
        budget(),
        &mut || false,
    )
    .unwrap();
    let actual = query(i, store, camera, time, options)
        .unwrap()
        .expect("narrow viewport should refine");
    equal(&expected, &actual.result);
}
#[test]
fn hierarchy_multi_point_temporal_full_ids_and_source_order_scene_parity() {
    let _guard = test_processor_lock();
    let starts = [i64::MIN, 0, 5, 0];
    let ends = [10, i64::MAX, 0, 20];
    let sv = [1, 1, 1, 0];
    let ev = [1, 1, 0, 1];
    let c = chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::MultiPoint,
        &[0., 0., 0.00001, 0., 0., 0., 0.00002, 0., 179., 0.],
        &[0, 2, 2, 4, 5],
        &[1, 0, 1, 1],
        &[u64::MAX, 0, 1 << 63, u64::MAX],
        Some(GeoIntervals {
            starts: &starts,
            ends: &ends,
            start_validity: &sv,
            end_validity: &ev,
        }),
    );
    let (m, raw) = source(&[c]);
    let (i, store) = build(&m, &raw, 1024);
    for time in [
        TimePredicate::All,
        TimePredicate::Instant(5),
        TimePredicate::Instant(10),
        TimePredicate::Instant(i64::MIN),
        TimePredicate::Window { start: 10, end: 20 },
    ] {
        compare(
            &m,
            &raw,
            i.clone(),
            &store,
            camera(0., 12.),
            time,
            GeoLodOptions::default(),
        );
    }
}
#[test]
fn hierarchy_cross_crs_seam_pitch_and_wrap_parity() {
    let _guard = test_processor_lock();
    for crs in [GeoCrs::Epsg4326, GeoCrs::Epsg3857] {
        let x = if crs == GeoCrs::Epsg4326 {
            180.
        } else {
            crate::geo_viewport::WEB_MERCATOR_MAX
        };
        let c = chunk(
            crs,
            GeoGeometry::Point,
            &[-x, 0., x, 0., 0., 0.],
            &[],
            &[1, 1, 1],
            &[u64::MAX, 1 << 63, 9],
            None,
        );
        let (m, raw) = source(&[c]);
        let (i, store) = build(&m, &raw, 1024);
        for cc in [GeoCrs::Epsg4326, GeoCrs::Epsg3857] {
            for wrap in [false, true] {
                for pitch in [-60., 0., 60.] {
                    let center = if cc == GeoCrs::Epsg4326 {
                        180.
                    } else {
                        crate::geo_viewport::WEB_MERCATOR_MAX
                    };
                    let camera =
                        GeoViewport::new(cc, center, 0., 9., 800., 600., 27., pitch, wrap).unwrap();
                    compare(
                        &m,
                        &raw,
                        i.clone(),
                        &store,
                        camera,
                        TimePredicate::All,
                        GeoLodOptions::default(),
                    );
                }
            }
        }
    }
}
#[test]
fn hierarchy_fine_frontier_and_authenticated_corruption() {
    let _guard = test_processor_lock();
    let n = 300;
    let mut xy = Vec::new();
    for j in 0..n {
        xy.extend([j as f64 * 0.001, 0.]);
    }
    let ids: Vec<_> = (0..n as u64).collect();
    let valid = vec![1; n];
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::Point,
        &xy,
        &[],
        &valid,
        &ids,
        None,
    )]);
    let (i, mut store) = build(&m, &raw, 1024);
    compare(
        &m,
        &raw,
        i.clone(),
        &store,
        camera(0., 14.),
        TimePredicate::All,
        GeoLodOptions::default(),
    );
    let root = i.root.unwrap();
    store.get_mut(&root.read.id).unwrap()[32] ^= 1;
    assert!(
        query(
            i,
            &store,
            camera(0., 14.),
            TimePredicate::All,
            GeoLodOptions::default()
        )
        .is_err()
    );
}
#[test]
fn hierarchy_dense_two_pass_ordered_centroid_parity() {
    let _guard = test_processor_lock();
    let n = 40_000;
    let mut xy = Vec::new();
    for j in 0..n {
        xy.extend([(j % 100) as f64 * 0.000001, (j / 100) as f64 * 0.000001]);
    }
    let ids: Vec<_> = (0..n as u64).map(|i| u64::MAX - i % 7).collect();
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::Point,
        &xy,
        &[],
        &vec![1; n],
        &ids,
        None,
    )]);
    let (i, store) = build(&m, &raw, 1024);
    for kind in [GeoReducedKind::Cluster, GeoReducedKind::Density] {
        compare(
            &m,
            &raw,
            i.clone(),
            &store,
            camera(0., 10.),
            TimePredicate::All,
            GeoLodOptions {
                kind,
                ..GeoLodOptions::default()
            },
        );
    }
}
#[test]
fn hierarchy_frontier_and_work_fallback_happen_before_leaf_io() {
    let _guard = test_processor_lock();
    let mut xy = Vec::new();
    for y in 0..20 {
        for x in 0..20 {
            xy.extend([-170. + x as f64 * 17., -65. + y as f64 * 6.5]);
        }
    }
    let ids: Vec<_> = (0..400).collect();
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::Point,
        &xy,
        &[],
        &vec![1; 400],
        &ids,
        None,
    )]);
    let (i, store) = build(&m, &raw, 1024);
    let mut s = GeoHierarchyQuerySession::new(
        i.clone(),
        camera(0., 0.),
        TimePredicate::All,
        GeoLodOptions::default(),
        1,
        1,
        1,
        GeoHierarchyQueryLimits::default(),
    )
    .unwrap();
    loop {
        match s.step().unwrap() {
            GeoHierarchyStep::NeedRead(t) => {
                assert_ne!(t.kind(), 5);
                s.supply(&t, &store[&t.page_id()]).unwrap();
                s.release_read(&t).unwrap();
            }
            GeoHierarchyStep::FullScanFrontier => break,
            o => panic!("expected frontier, {o:?}"),
        }
    }
    assert_eq!(s.stats().leaf_reads, 0);
    assert!(s.finish().is_err());
    drop(s);
    let mut s = GeoHierarchyQuerySession::new(
        i,
        camera(0., 0.),
        TimePredicate::All,
        GeoLodOptions::default(),
        1,
        1,
        1,
        GeoHierarchyQueryLimits {
            directory_reads: 1,
            ..GeoHierarchyQueryLimits::default()
        },
    )
    .unwrap();
    let GeoHierarchyStep::NeedRead(t) = s.step().unwrap() else {
        panic!()
    };
    s.supply(&t, &store[&t.page_id()]).unwrap();
    s.release_read(&t).unwrap();
    drop(t);
    assert!(matches!(s.step().unwrap(), GeoHierarchyStep::FullScanWork));
    assert_eq!(s.stats().leaf_reads, 0);
}
#[test]
fn hierarchy_namespace_exact_ack_and_retired_loans() {
    use crate::geo_source_session::GeoProcessorLease;
    let _guard = test_processor_lock();
    let before = GeoProcessorLease::live_bytes();
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::Point,
        &[0., 0.],
        &[],
        &[1],
        &[u64::MAX],
        None,
    )]);
    let mut a =
        GeoHierarchyBuildSession::new(&m, GeoHierarchyOptions::default(), budget(), 10, 64 << 30)
            .unwrap();
    let mut b =
        GeoHierarchyBuildSession::new(&m, GeoHierarchyOptions::default(), budget(), 10, 64 << 30)
            .unwrap();
    let GeoHierarchyStep::NeedRead(ta) = a.step().unwrap() else {
        panic!()
    };
    let GeoHierarchyStep::NeedRead(tb) = b.step().unwrap() else {
        panic!()
    };
    assert_ne!(ta.storage_namespace(), tb.storage_namespace());
    assert!(a.supply(&tb, &raw[0]).is_err());
    a.cancel();
    let live = GeoProcessorLease::live_bytes();
    assert!(matches!(a.step().unwrap(), GeoHierarchyStep::AwaitRelease));
    assert_eq!(live, GeoProcessorLease::live_bytes());
    assert!(a.release_read(&tb).is_err());
    a.release_read(&ta).unwrap();
    drop(a);
    drop(ta);
    b.cancel();
    b.release_read(&tb).unwrap();
    drop(tb);
    drop(b);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    let mut a =
        GeoHierarchyBuildSession::new(&m, GeoHierarchyOptions::default(), budget(), 10, 64 << 30)
            .unwrap();
    let GeoHierarchyStep::NeedRead(t) = a.step().unwrap() else {
        panic!()
    };
    a.supply(&t, &raw[0]).unwrap();
    a.release_read(&t).unwrap();
    drop(t);
    let GeoHierarchyStep::NeedWrite(t) = a.step().unwrap() else {
        panic!()
    };
    let cloned = t.clone();
    let live = GeoProcessorLease::live_bytes();
    a.cancel();
    assert!(matches!(a.step().unwrap(), GeoHierarchyStep::AwaitRelease));
    a.acknowledge_write(&t).unwrap();
    drop(t);
    drop(a);
    assert!(GeoProcessorLease::live_bytes() > before);
    assert!(GeoProcessorLease::live_bytes() < live);
    drop(cloned);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}
#[test]
fn hierarchy_canonical_import_rebuild_and_failed_publication_leave_old_root() {
    let _guard = test_processor_lock();
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::Point,
        &[0., 0., 0.001, 0.],
        &[],
        &[1, 1],
        &[u64::MAX, 1 << 63],
        None,
    )]);
    let (i, store) = build(&m, &raw, 1024);
    let mut verify =
        GeoHierarchyBuildSession::verify(&m, i.options(), budget(), 10, 64 << 30, i.digest())
            .unwrap();
    let mut rebuilt = Store::new();
    let verified = drive_build(&mut verify, &raw, &mut rebuilt).unwrap();
    assert_eq!(verified.digest(), i.digest());
    assert_eq!(store, rebuilt);
    assert_ne!(verified.storage_namespace(), i.storage_namespace());
    drop(verified);
    drop(verify);
    let mut wrong = i.digest();
    wrong[0] ^= 1;
    let mut verify =
        GeoHierarchyBuildSession::verify(&m, i.options(), budget(), 10, 64 << 30, wrong).unwrap();
    assert!(drive_build(&mut verify, &raw, &mut Store::new()).is_err());
    assert!(verify.finish().is_err());
    drop(verify);
    let mut verify =
        GeoHierarchyBuildSession::verify(&m, i.options(), budget(), 10, 64 << 30, i.digest())
            .unwrap();
    let GeoHierarchyStep::NeedRead(t) = verify.step().unwrap() else {
        panic!()
    };
    let mut bad = raw[0].clone();
    *bad.last_mut().unwrap() ^= 1;
    assert!(verify.supply(&t, &bad).is_err());
    verify.release_read(&t).unwrap();
    assert!(verify.finish().is_err());
    drop(t);
    drop(verify);
    compare(
        &m,
        &raw,
        i,
        &store,
        camera(0., 12.),
        TimePredicate::All,
        GeoLodOptions::default(),
    );
}
#[test]
fn hierarchy_final_fold_cancellation_does_not_publish() {
    let _guard = test_processor_lock();
    let n = 1000;
    let mut xy = Vec::new();
    for j in 0..n {
        xy.extend([j as f64 * 1e-8, 0.]);
    }
    let ids: Vec<_> = (0..n as u64).collect();
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::Point,
        &xy,
        &[],
        &vec![1; n],
        &ids,
        None,
    )]);
    let (i, store) = build(&m, &raw, 1024);
    let mut s = GeoHierarchyQuerySession::new(
        i.clone(),
        camera(0., 14.),
        TimePredicate::All,
        GeoLodOptions::default(),
        1,
        1,
        1,
        GeoHierarchyQueryLimits::default(),
    )
    .unwrap();
    loop {
        match s.step().unwrap() {
            GeoHierarchyStep::NeedRead(t) => {
                s.supply(&t, &store[&t.page_id()]).unwrap();
                s.release_read(&t).unwrap();
                if t.kind() == 5 {
                    break;
                }
            }
            o => panic!("{o:?}"),
        }
    }
    let mut calls = 0;
    let stopped = s.step_with_cancel(&mut || {
        calls += 1;
        calls > 20
    });
    assert!(matches!(
        stopped,
        Ok(GeoHierarchyStep::Cancelled) | Err(crate::geo_source::SourceError::Cancelled)
    ));
    assert!(calls > 20);
    assert!(s.finish().is_err());
    drop(s);
    compare(
        &m,
        &raw,
        i,
        &store,
        camera(0., 14.),
        TimePredicate::All,
        GeoLodOptions::default(),
    );
}
#[test]
fn hierarchy_source_validation_rejects_nonprojectable_ingress() {
    let _guard = test_processor_lock();
    assert!(matches!(
        GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg4326,
            xy: &[1e100, 0.],
            validity: &[1],
            feature_ids: Some(&[u64::MAX]),
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default()
        }),
        Err(crate::geo::GeoError::CoordinateOutOfRange)
    ));
}
#[test]
fn hierarchy_current_chunk_credit_survives_host_ack_and_pressure() {
    use crate::geo_source_session::GeoProcessorLease;
    let _guard = test_processor_lock();
    let before = GeoProcessorLease::live_bytes();
    let vertices = 300_000;
    let xy = vec![0.; vertices * 2];
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::MultiPoint,
        &xy,
        &[0, vertices as u32],
        &[1],
        &[u64::MAX],
        None,
    )]);
    let mut s = GeoHierarchyBuildSession::new(
        &m,
        GeoHierarchyOptions::default(),
        budget(),
        1_000_000,
        64 << 30,
    )
    .unwrap();
    let base = GeoProcessorLease::live_bytes();
    let GeoHierarchyStep::NeedRead(t) = s.step().unwrap() else {
        panic!()
    };
    let credit = t.credit.bytes();
    s.supply(&t, &raw[0]).unwrap();
    s.release_read(&t).unwrap();
    drop(t);
    assert_eq!(GeoProcessorLease::live_bytes(), base + credit);
    let GeoHierarchyStep::NeedWrite(t) = s.step().unwrap() else {
        panic!()
    };
    assert_eq!(
        GeoProcessorLease::live_bytes(),
        base + credit + t.credit.bytes()
    );
    let pressure = GeoProcessorLease::acquire(
        crate::geo_source::MAX_PROCESSOR_BYTES - GeoProcessorLease::live_bytes(),
    )
    .unwrap();
    assert!(
        GeoHierarchyBuildSession::new(
            &m,
            GeoHierarchyOptions::default(),
            budget(),
            1_000_000,
            64 << 30
        )
        .is_err()
    );
    s.cancel();
    assert!(matches!(s.step().unwrap(), GeoHierarchyStep::AwaitRelease));
    s.acknowledge_write(&t).unwrap();
    drop(t);
    drop(s);
    drop(pressure);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}
#[test]
fn hierarchy_tentative_temp_output_cannot_publish_unverified_run() {
    let _guard = test_processor_lock();
    let n = 2000;
    let mut xy = Vec::new();
    for j in 0..n {
        xy.extend([j as f64 * 1e-9, 0.]);
    }
    let ids: Vec<_> = (0..n as u64).collect();
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::Point,
        &xy,
        &[],
        &vec![1; n],
        &ids,
        None,
    )]);
    let mut s = GeoHierarchyBuildSession::new(
        &m,
        GeoHierarchyOptions::default(),
        budget(),
        10_000,
        64 << 30,
    )
    .unwrap();
    let mut store = Store::new();
    let mut changed = false;
    let mut tentative = false;
    loop {
        match s.step().unwrap() {
            GeoHierarchyStep::NeedWrite(t) => {
                let b = s.write_bytes(&t).unwrap().to_vec();
                tentative |= &b[..4] == b"XYHL";
                store.insert(t.page_id(), b);
                s.acknowledge_write(&t).unwrap();
            }
            GeoHierarchyStep::NeedRead(t) => {
                let mut b = if let Some(r) = t.source_request() {
                    raw[r.chunk_index as usize].clone()
                } else {
                    store[&t.page_id()].clone()
                };
                if t.kind() == 2 && !changed {
                    b[64 + 16 + 32..64 + 16 + 40].copy_from_slice(&0.123f64.to_le_bytes());
                    changed = true;
                }
                let supplied = s.supply(&t, &b);
                s.release_read(&t).unwrap();
                if supplied.is_err() {
                    break;
                }
            }
            o => panic!("unexpected before corruption {o:?}"),
        }
    }
    assert!(changed);
    assert!(
        tentative,
        "first pages may emit tentative output before complete rolling digest"
    );
    assert!(s.finish().is_err());
    assert!(matches!(s.step().unwrap(), GeoHierarchyStep::Cancelled));
}
#[test]
fn hierarchy_query_pressure_failure_and_cancel_retain_old_result() {
    use crate::geo_source_session::GeoProcessorLease;
    let _guard = test_processor_lock();
    let before = GeoProcessorLease::live_bytes();
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::Point,
        &[0., 0.],
        &[],
        &[1],
        &[u64::MAX],
        None,
    )]);
    let (i, store) = build(&m, &raw, 1024);
    let old = query(
        i.clone(),
        &store,
        camera(0., 12.),
        TimePredicate::All,
        GeoLodOptions::default(),
    )
    .unwrap()
    .unwrap();
    let mut s = GeoHierarchyQuerySession::new(
        i.clone(),
        camera(0., 12.),
        TimePredicate::All,
        GeoLodOptions::default(),
        1,
        1,
        1,
        GeoHierarchyQueryLimits::default(),
    )
    .unwrap();
    let pressure = GeoProcessorLease::acquire(
        crate::geo_source::MAX_PROCESSOR_BYTES - GeoProcessorLease::live_bytes(),
    )
    .unwrap();
    assert!(matches!(
        s.step(),
        Err(crate::geo_source::SourceError::ResourceLimit)
    ));
    drop(pressure);
    assert!(s.finish().is_err());
    drop(s);
    let mut s = GeoHierarchyQuerySession::new(
        i.clone(),
        camera(0., 12.),
        TimePredicate::All,
        GeoLodOptions::default(),
        1,
        1,
        1,
        GeoHierarchyQueryLimits::default(),
    )
    .unwrap();
    let GeoHierarchyStep::NeedRead(t) = s.step().unwrap() else {
        panic!()
    };
    s.cancel();
    let live = GeoProcessorLease::live_bytes();
    assert!(matches!(s.step().unwrap(), GeoHierarchyStep::AwaitRelease));
    assert_eq!(live, GeoProcessorLease::live_bytes());
    s.release_read(&t).unwrap();
    drop(t);
    drop(s);
    assert_eq!(old.result.visible_vertices, 1);
    drop(old);
    drop(i);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}
#[test]
fn hierarchy_million_vertex_bounded_external_merge_tracer() {
    let _guard = test_processor_lock();
    let count = 1_000_000usize;
    let mut chunks = Vec::new();
    for start in (0..count).step_by(65536) {
        let n = (count - start).min(65536);
        let mut xy = Vec::with_capacity(n * 2);
        let mut ids = Vec::with_capacity(n);
        for j in start..start + n {
            xy.extend([
                ((j as u64 * 104729) % 360_000) as f64 / 1000. - 180.,
                ((j as u64 * 13007) % 160_000) as f64 / 1000. - 80.,
            ]);
            ids.push(u64::MAX - j as u64);
        }
        chunks.push(chunk(
            GeoCrs::Epsg4326,
            GeoGeometry::Point,
            &xy,
            &[],
            &vec![1; n],
            &ids,
            None,
        ));
    }
    let (m, raw) = source(&chunks);
    drop(chunks);
    let (i, store) = build(&m, &raw, 1024);
    assert_eq!(i.root.unwrap().count, count as u64);
    assert!(store.values().any(|b| &b[..4] == b"XYHR"));
    assert!(store.values().any(|b| &b[..4] == b"XYHN"));
    let actual = query(
        i.clone(),
        &store,
        camera(0., 12.),
        TimePredicate::All,
        GeoLodOptions::default(),
    )
    .unwrap()
    .unwrap();
    assert!(actual.stats.vertex_records < 1000);
    assert!(actual.stats.selected_cells <= 256);
    let expected = geo_lod::process(
        &m,
        &mut |r: ReadRequest| Ok(raw[r.chunk_index as usize].clone()),
        camera(0., 12.),
        TimePredicate::All,
        u64::MAX,
        u64::MAX,
        u64::MAX,
        GeoLodOptions::default(),
        budget(),
        &mut || false,
    )
    .unwrap();
    equal(&actual.result, &expected);
    eprintln!(
        "hierarchy tracer rows={count} external_pages={} external_bytes={} query_dirs={} query_leaves={} query_candidates={} root_bytes={} result_bytes={}",
        store.len(),
        store.values().map(Vec::len).sum::<usize>(),
        actual.stats.directory_reads,
        actual.stats.leaf_reads,
        actual.stats.vertex_records,
        i.reserved_bytes(),
        actual.reserved_bytes()
    );
}
#[test]
fn hierarchy_deep_zoom_visible_separation_after_far_offscreen_row() {
    let _guard = test_processor_lock();
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::Point,
        &[100., 0., 0., 0., 1e-7, 0.],
        &[],
        &[1, 1, 1],
        &[7, u64::MAX, 1 << 63],
        None,
    )]);
    let (i, store) = build(&m, &raw, 1024);
    let c = GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 24., 800., 600., 0., 0., false).unwrap();
    let a = query(
        i.clone(),
        &store,
        c,
        TimePredicate::All,
        GeoLodOptions::default(),
    )
    .unwrap()
    .unwrap();
    let GeoPointOutput::Direct(p) = &a.result.output else {
        panic!()
    };
    assert_eq!(p.len(), 2);
    assert_eq!(p[0].identity.source_row, 1);
    assert_eq!(p[1].identity.feature_id, 1 << 63);
    assert!(((p[1].x - p[0].x) - 2.38609294).abs() < 1e-6);
    drop(a);
    compare(
        &m,
        &raw,
        i,
        &store,
        c,
        TimePredicate::All,
        GeoLodOptions::default(),
    );
}
#[test]
fn hierarchy_empty_valid_geometry_and_scalars_are_canonical() {
    let _guard = test_processor_lock();
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::MultiPoint,
        &[],
        &[0, 0, 0],
        &[1, 0],
        &[u64::MAX, 1 << 63],
        None,
    )]);
    let (i, store) = build(&m, &raw, 1024);
    assert!(i.root.is_none());
    assert!(store.is_empty());
    compare(
        &m,
        &raw,
        i,
        &store,
        camera(0., 12.),
        TimePredicate::All,
        GeoLodOptions::default(),
    );
    let c = chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::Point,
        &[0., 0., 0.00001, 0.],
        &[],
        &[1, 1],
        &[u64::MAX, u64::MAX],
        None,
    );
    let values = [f64::from_bits(0x7ff8_0000_0000_0042), -0.];
    let c = GeoChunk::parse(
        &GeoChunk::encode_with_values(c.column(), None, Some(&values)).unwrap(),
        96 << 20,
    )
    .unwrap();
    let (m, raw) = source(&[c]);
    let (i, store) = build(&m, &raw, 1024);
    let mut bits = Vec::new();
    for b in store.values().filter(|b| &b[..4] == b"XYHL") {
        for v in b[64..].chunks_exact(80) {
            bits.push(decode_vertex(v).unwrap().value.unwrap().to_bits());
        }
    }
    assert_eq!(bits, values.map(f64::to_bits));
    compare(
        &m,
        &raw,
        i,
        &store,
        camera(0., 12.),
        TimePredicate::All,
        GeoLodOptions::default(),
    );
}
#[test]
fn hierarchy_external_write_exact_cap_and_one_byte_over_fail_before_loan() {
    use crate::geo_source_session::GeoProcessorLease;
    let _guard = test_processor_lock();
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::Point,
        &[0., 0.],
        &[],
        &[1],
        &[u64::MAX],
        None,
    )]);
    let (old, old_store) = build(&m, &raw, 1024);
    let needed = old_store.values().map(|b| b.len() as u64).sum::<u64>();
    assert!(GeoHierarchyBuildSession::new(&m, old.options(), budget(), 10, 0).is_err());
    assert!(
        GeoHierarchyBuildSession::verify(&m, old.options(), budget(), 10, 0, old.digest()).is_err()
    );
    let mut exact =
        GeoHierarchyBuildSession::verify(&m, old.options(), budget(), 10, needed, old.digest())
            .unwrap();
    let rebuilt = drive_build(&mut exact, &raw, &mut Store::new()).unwrap();
    assert_eq!(exact.written_bytes(), needed);
    assert_eq!(rebuilt.digest(), old.digest());
    drop(rebuilt);
    drop(exact);
    let mut over =
        GeoHierarchyBuildSession::new(&m, old.options(), budget(), 10, needed - 1).unwrap();
    let mut store = Store::new();
    loop {
        let before = GeoProcessorLease::live_bytes();
        match over.step() {
            Ok(GeoHierarchyStep::NeedRead(t)) => {
                let b = if let Some(r) = t.source_request() {
                    raw[r.chunk_index as usize].clone()
                } else {
                    store[&t.page_id()].clone()
                };
                over.supply(&t, &b).unwrap();
                over.release_read(&t).unwrap();
            }
            Ok(GeoHierarchyStep::NeedWrite(t)) => {
                store.insert(t.page_id(), over.write_bytes(&t).unwrap().to_vec());
                over.acknowledge_write(&t).unwrap();
            }
            Err(crate::geo_source::SourceError::ResourceLimit) => {
                assert_eq!(
                    GeoProcessorLease::live_bytes(),
                    before,
                    "write limit must reject before ticket allocation"
                );
                break;
            }
            o => panic!("unexpected {o:?}"),
        }
    }
    assert_eq!(over.written_bytes() + 192, needed);
    assert!(matches!(over.step().unwrap(), GeoHierarchyStep::Cancelled));
    assert!(over.finish().is_err());
    drop(over);
    compare(
        &m,
        &raw,
        old,
        &old_store,
        camera(0., 12.),
        TimePredicate::All,
        GeoLodOptions::default(),
    );
}
#[test]
fn hierarchy_external_write_cap_cancel_requires_exact_ack() {
    use crate::geo_source_session::GeoProcessorLease;
    let _guard = test_processor_lock();
    let initial = GeoProcessorLease::live_bytes();
    let (m, raw) = source(&[chunk(
        GeoCrs::Epsg4326,
        GeoGeometry::Point,
        &[0., 0.],
        &[],
        &[1],
        &[u64::MAX],
        None,
    )]);
    let (old, store) = build(&m, &raw, 1024);
    let root_live = GeoProcessorLease::live_bytes();
    let mut s =
        GeoHierarchyBuildSession::new(&m, old.options(), budget(), 10, PAGE_BYTES as u64).unwrap();
    let GeoHierarchyStep::NeedRead(t) = s.step().unwrap() else {
        panic!()
    };
    s.supply(&t, &raw[0]).unwrap();
    s.release_read(&t).unwrap();
    drop(t);
    let GeoHierarchyStep::NeedWrite(t) = s.step().unwrap() else {
        panic!()
    };
    assert_eq!(s.written_bytes(), PAGE_BYTES as u64);
    s.cancel();
    let before = GeoProcessorLease::live_bytes();
    assert!(matches!(s.step().unwrap(), GeoHierarchyStep::AwaitRelease));
    assert_eq!(before, GeoProcessorLease::live_bytes());
    let mut forged = t.clone();
    forged.namespace ^= 1;
    assert!(s.acknowledge_write(&forged).is_err());
    drop(forged);
    s.acknowledge_write(&t).unwrap();
    assert!(s.finish().is_err());
    drop(t);
    drop(s);
    assert_eq!(GeoProcessorLease::live_bytes(), root_live);
    compare(
        &m,
        &raw,
        old,
        &store,
        camera(0., 12.),
        TimePredicate::All,
        GeoLodOptions::default(),
    );
    assert_eq!(GeoProcessorLease::live_bytes(), initial);
}
