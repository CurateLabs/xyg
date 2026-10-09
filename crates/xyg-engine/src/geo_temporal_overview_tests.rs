use super::geo_temporal_overview::*;
use super::geo_temporal_overview_build::GeoOverviewBuildSession;
use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
use crate::geo_source::{GeoChunk, GeoIntervals, GeoManifestBuilder, MAX_CHUNK_PEAK, QueryBudget};
use crate::geo_source::{GeoSourceManifest, SourceError, TimePredicate};
use crate::geo_source_session::test_processor_lock;
use crate::geo_source_session::{GeoOperationSnapshot, GeoProcessorLease};
use crate::geo_viewport::GeoViewport;
use std::collections::BTreeMap;
use std::sync::Arc;
fn budget() -> QueryBudget {
    QueryBudget {
        processor_bytes: 128 << 20,
        max_rows_examined: 2_000_000,
        max_chunks: 65536,
        max_read_bytes: 2_000_000_000,
        page_rows: 4096,
    }
}
fn chunk(crs: GeoCrs, multi: bool) -> Vec<u8> {
    let xy = if crs == GeoCrs::Epsg4326 {
        vec![-179., 0., 179., 0., 0., 0., 0., 0.]
    } else {
        vec![
            -19_926_188.851_995_97,
            0.,
            19_926_188.851_995_97,
            0.,
            0.,
            0.,
            0.,
            0.,
        ]
    };
    let c = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: if multi {
            GeoGeometry::MultiPoint
        } else {
            GeoGeometry::Point
        },
        crs,
        xy: &xy,
        validity: &[1, 1, 1, 1, 0],
        feature_ids: Some(&[u64::MAX, u64::MAX, 1 << 63, (1 << 53) + 1, 7]),
        offsets0: if multi { &[0, 2, 3, 4, 4, 4] } else { &[] },
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    GeoChunk::encode(
        &c,
        Some(GeoIntervals {
            starts: &[i64::MIN, 0, 10, 0, 0],
            ends: &[0, 10, i64::MAX, 0, 0],
            start_validity: &[1, 1, 1, 0, 0],
            end_validity: &[1, 1, 1, 0, 0],
        }),
    )
    .unwrap()
}
fn manifest(chunks: &[Vec<u8>]) -> GeoSourceManifest {
    let mut m = GeoManifestBuilder::new();
    for b in chunks {
        m.push(&GeoChunk::parse(b, MAX_CHUNK_PEAK).unwrap())
            .unwrap()
    }
    m.finish(7).unwrap()
}
fn build(
    source: &GeoSourceManifest,
    chunks: &[Vec<u8>],
    expected: Option<[u8; 8]>,
) -> (Arc<ValidatedGeoOverview>, BTreeMap<u64, Vec<u8>>) {
    let mut b = if let Some(e) = expected {
        GeoOverviewBuildSession::verify(source, budget(), 2_000_000, e).unwrap()
    } else {
        GeoOverviewBuildSession::new(source, budget(), 2_000_000).unwrap()
    };
    let mut pages: BTreeMap<u64, Vec<u8>> = BTreeMap::new();
    loop {
        match b.step().unwrap() {
            GeoOverviewStep::NeedRead(t) => {
                let bytes = t.source_request().map_or_else(
                    || pages.get(&t.page_id()).unwrap().clone(),
                    |r| chunks[r.chunk_index as usize].clone(),
                );
                b.supply(&t, &bytes).unwrap();
                drop(bytes);
                b.release_read(&t).unwrap()
            }
            GeoOverviewStep::NeedWrite(t) => {
                pages.insert(t.page_id(), b.write_bytes(&t).unwrap().to_vec());
                b.ack_write(&t).unwrap()
            }
            GeoOverviewStep::Complete => break,
            other => panic!("{other:?}"),
        }
    }
    (b.take_index().unwrap(), pages)
}
fn snapshot(
    index: &ValidatedGeoOverview,
    time: crate::geo_source::TimePredicate,
) -> (GeoOperationSnapshot, GeoViewport) {
    let camera = GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 0., 800., 600., 0., 0., true).unwrap();
    (
        GeoOperationSnapshot {
            source_digest: index.source.digest(),
            generation: index.source.generation(),
            camera: camera.rebuild_key().unwrap(),
            time,
            camera_revision: 1,
            time_revision: 1,
            layer_id: u64::MAX,
            layer_revision: 1,
            style_revision: 1,
            state_revision: 1,
        },
        camera,
    )
}
fn query(
    index: Arc<ValidatedGeoOverview>,
    pages: &BTreeMap<u64, Vec<u8>>,
    time: TimePredicate,
) -> GeoOverviewResult {
    let (s, c) = snapshot(&index, time);
    let mut q = GeoOverviewQuerySession::new(index, s, c).unwrap();
    loop {
        match q.step().unwrap() {
            GeoOverviewStep::NeedRead(t) => {
                q.supply(&t, pages.get(&t.page_id()).unwrap()).unwrap();
                q.release_read(&t).unwrap()
            }
            GeoOverviewStep::Complete => return q.take_result().unwrap(),
            other => panic!("{other:?}"),
        }
    }
}
#[test]
fn temporal_goldens_nulls_dateline_full_ids_and_half_open_extrema() {
    let _lock = test_processor_lock();
    for crs in [GeoCrs::Epsg4326, GeoCrs::Epsg3857] {
        let chunks = vec![chunk(crs, false)];
        let m = manifest(&chunks);
        let (index, p) = build(&m, &chunks, None);
        let all = query(index.clone(), &p, TimePredicate::All);
        assert_eq!(all.counts().iter().sum::<u64>(), 4);
        assert_eq!(all.counts()[128], 1);
        assert_eq!(all.counts()[143], 1);
        assert_eq!(all.counts()[136], 2);
        for (t, n) in [
            (i64::MIN, 2),
            (-1, 2),
            (0, 2),
            (9, 2),
            (10, 2),
            (i64::MAX, 1),
        ] {
            assert_eq!(
                query(index.clone(), &p, TimePredicate::Instant(t))
                    .counts()
                    .iter()
                    .sum::<u64>(),
                n
            )
        }
        for (start, end, n) in [(0, 10, 2), (-1, 1, 3), (9, 11, 3), (i64::MIN, i64::MAX, 4)] {
            let r = query(index.clone(), &p, TimePredicate::Window { start, end });
            assert_eq!(r.counts().iter().sum::<u64>(), n);
            assert!(r.temporal_exact() && r.data_space() && !r.final_result());
            assert_eq!(r.snapshot().layer_id, u64::MAX)
        }
    }
}
#[test]
fn multipoint_vertex_population_empty_and_null_rows() {
    let _lock = test_processor_lock();
    let chunks = vec![chunk(GeoCrs::Epsg4326, true)];
    let m = manifest(&chunks);
    let (i, p) = build(&m, &chunks, None);
    assert_eq!(
        query(i.clone(), &p, TimePredicate::All)
            .counts()
            .iter()
            .sum::<u64>(),
        4
    );
    assert_eq!(
        query(i.clone(), &p, TimePredicate::Instant(-1))
            .counts()
            .iter()
            .sum::<u64>(),
        2
    );
    assert_eq!(
        query(i, &p, TimePredicate::Instant(0))
            .counts()
            .iter()
            .sum::<u64>(),
        1
    )
}
#[test]
fn canonical_rebuild_verification_rejects_omitted_or_forged_import_digest() {
    let _lock = test_processor_lock();
    let chunks = vec![chunk(GeoCrs::Epsg4326, false)];
    let m = manifest(&chunks);
    let (i, _) = build(&m, &chunks, None);
    let expected = i.digest();
    let (copy, _) = build(&m, &chunks, Some(expected));
    assert_eq!(copy.digest(), expected);
    drop(copy);
    let mut forged = expected;
    forged[0] ^= 1;
    let mut b = GeoOverviewBuildSession::verify(&m, budget(), 100, forged).unwrap();
    let mut pages: BTreeMap<u64, Vec<u8>> = BTreeMap::new();
    loop {
        match b.step() {
            Ok(GeoOverviewStep::NeedRead(t)) => {
                let bytes = t.source_request().map_or_else(
                    || pages.get(&t.page_id()).unwrap(),
                    |r| &chunks[r.chunk_index as usize],
                );
                b.supply(&t, bytes).unwrap();
                b.release_read(&t).unwrap()
            }
            Ok(GeoOverviewStep::NeedWrite(t)) => {
                pages.insert(t.page_id(), b.write_bytes(&t).unwrap().to_vec());
                b.ack_write(&t).unwrap()
            }
            Err(GeoOverviewError::Source(SourceError::InvalidFrame)) => break,
            other => panic!("{other:?}"),
        }
    }
    assert!(b.take_index().is_err())
}
#[test]
fn cancellation_retired_read_write_and_bad_digest_preserve_old_output() {
    let _lock = test_processor_lock();
    let chunks = vec![chunk(GeoCrs::Epsg4326, false)];
    let m = manifest(&chunks);
    let (i, p) = build(&m, &chunks, None);
    let old = query(i.clone(), &p, TimePredicate::All);
    let before = GeoProcessorLease::live_bytes();
    let mut b = GeoOverviewBuildSession::new(&m, budget(), 100).unwrap();
    let GeoOverviewStep::NeedRead(t) = b.step().unwrap() else {
        panic!()
    };
    let mut foreign = t.clone();
    foreign.serial += 1;
    assert!(b.release_read(&foreign).is_err());
    b.cancel();
    assert!(matches!(b.step().unwrap(), GeoOverviewStep::AwaitRelease));
    assert!(GeoProcessorLease::live_bytes() > before);
    b.release_read(&t).unwrap();
    drop(b);
    assert!(GeoProcessorLease::live_bytes() > before);
    drop(t);
    drop(foreign);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    let (s, c) = snapshot(&i, TimePredicate::Instant(0));
    let mut q = GeoOverviewQuerySession::new(i.clone(), s, c).unwrap();
    let GeoOverviewStep::NeedRead(t) = q.step().unwrap() else {
        panic!()
    };
    let mut bad = p[&t.page_id()].clone();
    bad[64] ^= 1;
    assert!(q.supply(&t, &bad).is_err());
    assert!(q.take_result().is_err());
    q.release_read(&t).unwrap();
    assert_eq!(old.counts().iter().sum::<u64>(), 4);
    drop(q);
    drop(t);
    let mut b = GeoOverviewBuildSession::new(&m, budget(), 100).unwrap();
    let GeoOverviewStep::NeedRead(t) = b.step().unwrap() else {
        panic!()
    };
    b.supply(&t, &chunks[0]).unwrap();
    b.release_read(&t).unwrap();
    drop(t);
    let GeoOverviewStep::NeedWrite(t) = b.step().unwrap() else {
        panic!()
    };
    let bytes = b.write_bytes(&t).unwrap().to_vec();
    b.cancel();
    b.ack_write(&t).unwrap();
    assert!(matches!(b.step().unwrap(), GeoOverviewStep::Cancelled));
    assert_eq!(bytes.len(), t.encoded_bytes());
    assert!(b.take_index().is_err());
    assert_eq!(old.counts().iter().sum::<u64>(), 4)
}
#[test]
fn snapshot_identity_domain_fallback_and_global_pressure_are_explicit() {
    let _lock = test_processor_lock();
    let chunks = vec![chunk(GeoCrs::Epsg4326, false)];
    let m = manifest(&chunks);
    let (i, p) = build(&m, &chunks, None);
    let (s, c) = snapshot(&i, TimePredicate::All);
    let mut bad = s;
    bad.generation += 1;
    assert!(matches!(
        GeoOverviewQuerySession::new(i.clone(), bad, c),
        Err(GeoOverviewError::Source(SourceError::StaleSource))
    ));
    let live = GeoProcessorLease::live_bytes();
    let pressure = GeoProcessorLease::acquire((128 << 20) - live).unwrap();
    assert!(GeoOverviewQuerySession::new(i.clone(), s, c).is_err());
    drop(pressure);
    assert_eq!(
        query(i, &p, TimePredicate::All)
            .counts()
            .iter()
            .sum::<u64>(),
        4
    );
    assert!(matches!(
        GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg3857,
            xy: &[1e100, 0.],
            validity: &[1],
            feature_ids: Some(&[u64::MAX]),
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        }),
        Err(crate::geo::GeoError::CoordinateOutOfRange)
    ));
    // The shared canonical ingress already excludes this overflow domain;
    // no fabricated manifest/column may bypass it to acquire overview authority.
    assert_eq!(
        crate::geo_spatial_index::cell(
            GeoCrs::Epsg3857,
            [1e100, 0.],
            crate::geo_spatial_index::GeoSpatialOptions { grid: 16 }
        ),
        u32::MAX
    );
}
fn generated_chunk(first: usize, n: usize) -> Vec<u8> {
    let mut xy = Vec::with_capacity(2 * n);
    let mut offsets = Vec::with_capacity(n + 1);
    offsets.push(0u32);
    let mut validity = Vec::with_capacity(n);
    let mut ids = Vec::with_capacity(n);
    let mut starts = Vec::with_capacity(n);
    let mut ends = Vec::with_capacity(n);
    for r in first..first + n {
        let valid = r % 17 != 0;
        validity.push(u8::from(valid));
        ids.push(if r % 3 == 0 {
            u64::MAX
        } else {
            (1 << 63) + r as u64
        });
        starts.push((r % 997) as i64);
        ends.push((r % 997 + 5) as i64);
        if valid {
            let w = crate::geo_viewport::WEB_MERCATOR_MAX;
            xy.push(-w + ((r % 16) as f64 + 0.5) / 16. * (2. * w));
            xy.push(-w + (((r / 16) % 16) as f64 + 0.5) / 16. * (2. * w));
            let end = xy.len();
            xy.extend_from_within(end - 2..end);
        }
        offsets.push((xy.len() / 2) as u32);
    }
    let c = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::MultiPoint,
        crs: GeoCrs::Epsg3857,
        xy: &xy,
        validity: &validity,
        feature_ids: Some(&ids),
        offsets0: &offsets,
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let flags = vec![1; n];
    GeoChunk::encode(
        &c,
        Some(GeoIntervals {
            starts: &starts,
            ends: &ends,
            start_validity: &flags,
            end_validity: &flags,
        }),
    )
    .unwrap()
}
#[test]
fn million_row_external_merge_and_prefix_tracer() {
    let _lock = test_processor_lock();
    const N: usize = 1_000_000;
    const CHUNK: usize = 65536;
    let mut m = GeoManifestBuilder::new();
    for first in (0..N).step_by(CHUNK) {
        let b = generated_chunk(first, (N - first).min(CHUNK));
        m.push(&GeoChunk::parse(&b, MAX_CHUNK_PEAK).unwrap())
            .unwrap()
    }
    let source = m.finish(19).unwrap();
    let mut b = GeoOverviewBuildSession::new(&source, budget(), 2_000_000).unwrap();
    let mut pages: BTreeMap<u64, Vec<u8>> = BTreeMap::new();
    let mut reads = 0;
    let mut writes = 0;
    let mut peak = GeoProcessorLease::live_bytes();
    loop {
        match b.step().unwrap() {
            GeoOverviewStep::NeedRead(t) => {
                reads += 1;
                peak = peak.max(GeoProcessorLease::live_bytes());
                let bytes = if let Some(r) = t.source_request() {
                    generated_chunk(r.first_row as usize, r.rows as usize)
                } else {
                    pages[&t.page_id()].clone()
                };
                b.supply(&t, &bytes).unwrap();
                drop(bytes);
                b.release_read(&t).unwrap()
            }
            GeoOverviewStep::NeedWrite(t) => {
                writes += 1;
                peak = peak.max(GeoProcessorLease::live_bytes());
                pages.insert(t.page_id(), b.write_bytes(&t).unwrap().to_vec());
                b.ack_write(&t).unwrap()
            }
            GeoOverviewStep::Complete => break,
            other => panic!("{other:?}"),
        }
    }
    assert!(
        writes > 500 && reads > 500,
        "fixture must exercise external merge and multilevel tree"
    );
    assert!(peak <= 128 << 20);
    let i = b.take_index().unwrap();
    drop(b);
    let (s, c) = snapshot(
        &i,
        TimePredicate::Window {
            start: 400,
            end: 405,
        },
    );
    let mut q = GeoOverviewQuerySession::new(i.clone(), s, c).unwrap();
    let mut query_reads = 0;
    loop {
        match q.step().unwrap() {
            GeoOverviewStep::NeedRead(t) => {
                query_reads += 1;
                assert_eq!(t.storage_namespace(), i.storage_namespace());
                q.supply(&t, &pages[&t.page_id()]).unwrap();
                q.release_read(&t).unwrap()
            }
            GeoOverviewStep::Complete => break,
            other => panic!("{other:?}"),
        }
    }
    let out = q.take_result().unwrap();
    let mut expected = [0u64; 256];
    for r in 0..N {
        if r % 17 != 0 && (396..405).contains(&(r % 997)) {
            expected[r % 256] += 2
        }
    }
    assert_eq!(out.counts(), &expected);
    assert!(query_reads <= 10, "two logarithmic prefix traversals");
    println!(
        "overview1M: rows={N} build_reads={reads} writes={writes} prefix_reads={query_reads} processor_peak={peak} external_bytes={} result_bytes=2048",
        pages.values().map(Vec::len).sum::<usize>()
    );
    drop(q);
    drop(i);
    assert_eq!(out.counts(), &expected);
    assert_eq!(out.source().generation(), 19)
}
#[test]
fn corrupted_canonical_read_and_cancelled_prefix_never_replace_owned_counts() {
    let _lock = test_processor_lock();
    let chunks = vec![chunk(GeoCrs::Epsg4326, false)];
    let source = manifest(&chunks);
    let (index, pages) = build(&source, &chunks, None);
    let old = query(index.clone(), &pages, TimePredicate::All);
    let mut b = GeoOverviewBuildSession::new(&source, budget(), 100).unwrap();
    let GeoOverviewStep::NeedRead(t) = b.step().unwrap() else {
        panic!()
    };
    let mut bad = chunks[0].clone();
    bad[128] ^= 1;
    assert!(b.supply(&t, &bad).is_err());
    assert!(matches!(b.step().unwrap(), GeoOverviewStep::AwaitRelease));
    b.release_read(&t).unwrap();
    assert!(b.take_index().is_err());
    drop(b);
    drop(t);
    let (s, c) = snapshot(&index, TimePredicate::Instant(5));
    let mut q = GeoOverviewQuerySession::new(index.clone(), s, c).unwrap();
    let GeoOverviewStep::NeedRead(t) = q.step().unwrap() else {
        panic!()
    };
    q.cancel();
    assert!(matches!(q.step().unwrap(), GeoOverviewStep::AwaitRelease));
    assert!(q.supply(&t, &pages[&t.page_id()]).is_err());
    q.release_read(&t).unwrap();
    assert!(matches!(q.step().unwrap(), GeoOverviewStep::Cancelled));
    assert!(q.take_result().is_err());
    assert_eq!(old.counts().iter().sum::<u64>(), 4);
    drop(q);
    drop(index);
    assert_eq!(old.source().generation(), 7);
}
#[test]
fn nullable_endpoints_at_signed_extrema_do_not_overflow_or_change_half_open_policy() {
    let _lock = test_processor_lock();
    let c = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::Point,
        crs: GeoCrs::Epsg4326,
        xy: &[0.; 10],
        validity: &[1; 5],
        feature_ids: Some(&[u64::MAX; 5]),
        offsets0: &[],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let bytes = GeoChunk::encode(
        &c,
        Some(GeoIntervals {
            starts: &[0, i64::MAX, 0, i64::MIN, i64::MAX - 1],
            ends: &[i64::MIN, 0, 0, i64::MIN + 1, i64::MAX],
            start_validity: &[0, 1, 0, 1, 1],
            end_validity: &[1, 0, 0, 1, 1],
        }),
    )
    .unwrap();
    let chunks = vec![bytes];
    let source = manifest(&chunks);
    let (i, p) = build(&source, &chunks, None);
    for (t, n) in [
        (i64::MIN, 2),
        (i64::MIN + 1, 1),
        (i64::MAX - 1, 2),
        (i64::MAX, 2),
    ] {
        assert_eq!(
            query(i.clone(), &p, TimePredicate::Instant(t)).counts()[136],
            n
        )
    }
    assert_eq!(query(i.clone(), &p, TimePredicate::All).counts()[136], 5);
    assert_eq!(
        query(
            i,
            &p,
            TimePredicate::Window {
                start: i64::MIN,
                end: i64::MAX
            }
        )
        .counts()[136],
        3
    )
}
#[test]
fn decoded_chunk_retains_charge_after_read_ack_and_blocks_unadmitted_parallel_build() {
    let _lock = test_processor_lock();
    let before = GeoProcessorLease::live_bytes();
    let n = 65536;
    let vertices = n * 8;
    let xy = vec![0.; vertices * 2];
    let flags = vec![1; n];
    let ids = vec![u64::MAX; n];
    let offsets: Vec<u32> = (0..=n).map(|i| (i * 8) as u32).collect();
    let column = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::MultiPoint,
        crs: GeoCrs::Epsg4326,
        xy: &xy,
        validity: &flags,
        feature_ids: Some(&ids),
        offsets0: &offsets,
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let starts = vec![0; n];
    let ends = vec![10; n];
    let bytes = GeoChunk::encode(
        &column,
        Some(GeoIntervals {
            starts: &starts,
            ends: &ends,
            start_validity: &flags,
            end_validity: &flags,
        }),
    )
    .unwrap();
    let source = manifest(std::slice::from_ref(&bytes));
    let mut b = GeoOverviewBuildSession::new(&source, budget(), 1_000_000).unwrap();
    let GeoOverviewStep::NeedRead(t) = b.step().unwrap() else {
        panic!()
    };
    b.supply(&t, &bytes).unwrap();
    let charged = GeoProcessorLease::live_bytes();
    b.release_read(&t).unwrap();
    drop(t);
    assert_eq!(
        GeoProcessorLease::live_bytes(),
        charged,
        "decoded chunk still owns its parser/working credit"
    );
    assert!(matches!(
        GeoOverviewBuildSession::new(&source, budget(), 1_000_000),
        Err(GeoOverviewError::Source(SourceError::ResourceLimit))
    ));
    let GeoOverviewStep::NeedWrite(t) = b.step().unwrap() else {
        panic!()
    };
    assert!(
        GeoProcessorLease::live_bytes() > charged,
        "runflush charges output alongside retained decoded chunk"
    );
    b.cancel();
    b.ack_write(&t).unwrap();
    drop(t);
    drop(b);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    let recovered = GeoOverviewBuildSession::new(&source, budget(), 1_000_000).unwrap();
    drop(recovered);
    assert_eq!(GeoProcessorLease::live_bytes(), before)
}
#[test]
fn prefix_read_admission_failure_is_retry_atomic_and_never_skips_boundary() {
    let _lock = test_processor_lock();
    let chunks = vec![chunk(GeoCrs::Epsg4326, false)];
    let source = manifest(&chunks);
    let (index, pages) = build(&source, &chunks, None);
    let (s, c) = snapshot(&index, TimePredicate::Instant(5));
    let mut q = GeoOverviewQuerySession::new(index, s, c).unwrap();
    let pressure =
        GeoProcessorLease::acquire((128 << 20) - GeoProcessorLease::live_bytes()).unwrap();
    assert!(matches!(
        q.step(),
        Err(GeoOverviewError::Source(SourceError::ResourceLimit))
    ));
    drop(pressure);
    loop {
        match q.step().unwrap() {
            GeoOverviewStep::NeedRead(t) => {
                q.supply(&t, &pages[&t.page_id()]).unwrap();
                q.release_read(&t).unwrap()
            }
            GeoOverviewStep::Complete => break,
            other => panic!("{other:?}"),
        }
    }
    let r = q.take_result().unwrap();
    assert_eq!(r.counts()[143], 1);
    assert_eq!(r.counts()[136], 1);
    assert_eq!(r.counts().iter().sum::<u64>(), 2)
}
