//! Selected hierarchy byte-protocol proofs. No private registry mutation.
use super::*;
fn scope(frame: u64) -> u64 {
    scope_in(frame, 777)
}
fn scope_in(frame: u64, namespace: u64) -> u64 {
    let mut p = [0; 16];
    p64(&mut p, 0, namespace);
    p64(&mut p, 8, u64::MAX);
    u64_at(
        &execute(&with_budget(request(32, frame, 1, &p))).unwrap(),
        16,
    )
}
fn state(scope: u64, ids: &[u64]) -> u64 {
    let mut p = vec![0; 24];
    p64(&mut p, 0, 2);
    p[8..12].copy_from_slice(&[0, 255, 0, 255]);
    p64(&mut p, 16, ids.len() as u64);
    for id in ids {
        p.extend(id.to_le_bytes());
    }
    u64_at(
        &execute(&with_budget(request(33, scope, 0, &p))).unwrap(),
        16,
    )
}
fn selected_query(cmd: u32, h: u64, seq: u64, m: &GeoSourceManifest, state: u64) -> Vec<u8> {
    let mut b = begin(h, seq, m, None, 1000000);
    p32(&mut b, 8, cmd);
    p64(&mut b, 192, 2);
    p64(&mut b, 232, 8);
    b.extend(state.to_le_bytes());
    b
}
fn selected_data(q: u64, seq: u64) -> u64 {
    let mut b = scene_request(q, seq);
    p32(&mut b, 8, 44);
    let d = u64_at(&execute(&b).unwrap(), 16);
    assert_eq!(d, q);
    d
}
// Build from a selected canonical publication, then retire all original Source/Data owners.
type SelectedFixture = (
    u64,
    u64,
    GeoSourceManifest,
    BTreeMap<(u64, u64), Vec<u8>>,
    Vec<u8>,
);
fn selected_index(chunks: &[Vec<u8>], ids: &[u64]) -> SelectedFixture {
    selected_index_in(777, chunks, ids)
}
fn selected_index_in(
    namespace: u64,
    chunks: &[Vec<u8>],
    ids: &[u64],
) -> (
    u64,
    u64,
    GeoSourceManifest,
    BTreeMap<(u64, u64), Vec<u8>>,
    Vec<u8>,
) {
    let (mh, bytes) = finish_manifest(chunks);
    let m = GeoSourceManifest::validate(
        &bytes,
        &mut |r: crate::geo_source::ReadRequest| Ok(chunks[r.chunk_index as usize].clone()),
        &mut || false,
    )
    .unwrap();
    let source = u64_at(
        &execute(&with_budget(request(4, 0, 0, &bytes))).unwrap(),
        16,
    );
    assert_eq!(drive(source, 0, chunks).0, 3);
    execute(&begin(source, 1, &m, None, 1000000)).unwrap();
    assert_eq!(drive(source, 1, chunks).0, 4);
    let frame = u64_at(&execute(&scene_request(source, 1)).unwrap(), 16);
    let scope = scope_in(frame, namespace);
    let state = state(scope, ids);
    execute(&selected_query(35, source, 2, &m, state)).unwrap();
    assert_eq!(drive(source, 2, chunks).0, 4);
    let selected = u64_at(&execute(&scene_request(source, 2)).unwrap(), 16);
    let reference = read_data(&request(23, selected, 0, &[]), 128 << 20).unwrap();
    let mut b = build_request(selected, 64 << 20);
    p64(&mut b, 24, 2);
    let index = u64_at(&execute(&b).unwrap(), 16);
    close(selected, 0);
    close(frame, 0);
    close(source, 0);
    drop(mh);
    let mut store = BTreeMap::new();
    assert_eq!(
        u32_at(&drive_hierarchy(index, 2, chunks, &mut store), 8),
        18
    );
    (index, scope, m, store, reference)
}
fn footer(b: &[u8]) -> &[u8] {
    assert_eq!(u32_at(b, 4), 2);
    let n = u64_at(b, 248) as usize;
    let f = &b[b.len() - n..];
    assert_eq!(&f[..4], b"XYSE");
    f
}
#[test]
fn five_selected_lanes_replace_queries_and_preserve_old_frames() {
    let _serial = test_processor_lock();
    let before = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let chunks = vec![chunk(u64::MAX, -5, 0.), chunk(7, 100, 0.0001)];
    let (index, scope, m, mut store, _) = selected_index(&chunks, &[u64::MAX, 7]);
    let mut lanes = vec![index];
    // Advance lane0 first. Forks must start at immutable creation, not lane0's camera/time history.
    let st = state(scope, &[u64::MAX, 7]);
    let q = u64_at(
        &execute(&selected_query(43, index, 50, &m, st)).unwrap(),
        16,
    );
    assert_eq!(q, st);
    assert_eq!(u32_at(&drive_hierarchy(q, 50, &chunks, &mut store), 8), 19);
    let mut old = vec![selected_data(q, 50)];
    for _ in 0..4 {
        lanes.push(u64_at(
            &execute(&with_budget(request(42, index, 2, &[]))).unwrap(),
            16,
        ));
    }
    for lane in &lanes[1..] {
        let st = state(scope, &[u64::MAX, 7]);
        let q = u64_at(&execute(&selected_query(43, *lane, 3, &m, st)).unwrap(), 16);
        assert_eq!(q, st);
        assert_eq!(u32_at(&drive_hierarchy(q, 3, &chunks, &mut store), 8), 19);
        old.push(selected_data(q, 3));
    }
    // Scope1 + lanes5 + oldData5; one State replaces itself twice, never adds a 17th handle.
    let st = state(scope, &[u64::MAX, 7]);
    let pressure: Vec<_> = (0..4)
        .map(|_| {
            u64_at(
                &execute(&with_budget(request(42, index, 2, &[]))).unwrap(),
                16,
            )
        })
        .collect();
    assert_eq!(
        execute(&request(1, 0, 0, &[])).unwrap_err(),
        SourceError::ResourceLimit
    );
    let q = u64_at(
        &execute(&selected_query(43, index, 51, &m, st)).unwrap(),
        16,
    );
    assert_eq!(q, st);
    assert_eq!(u32_at(&drive_hierarchy(q, 51, &chunks, &mut store), 8), 19);
    let before_failed = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let mut low = scene_request(q, 51);
    p32(&mut low, 8, 44);
    p64(&mut low, 32, 4096);
    assert_eq!(execute(&low).unwrap_err(), SourceError::ResourceLimit);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        before_failed
    );
    let candidate = selected_data(q, 51);
    assert_eq!(
        execute(&request(1, 0, 0, &[])).unwrap_err(),
        SourceError::ResourceLimit
    );
    for h in pressure {
        close(h, 2);
    }
    assert_eq!(
        execute(&request(10, scope, 0, &[])).unwrap_err(),
        SourceError::ResourceLimit
    );
    for lane in lanes {
        close(lane, 2);
    }
    // All frames remain independent after every lane and canonical Source owner disappears.
    for d in old.drain(..).chain([candidate]) {
        let b = read_data(&request(23, d, 0, &[]), 128 << 20).unwrap();
        assert_eq!(u64_at(&b, 48), 2);
        assert!(!footer(&b).is_empty());
        close(d, 0);
    }
    close(scope, 0);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        before
    );
}
#[test]
fn selected_preflight_preserves_state_and_cancel_keeps_issued_loan_until_ack() {
    let _serial = test_processor_lock();
    let chunks = vec![chunk(u64::MAX, -5, 0.)];
    let (index, scope, m, mut store, _) = selected_index(&chunks, &[u64::MAX]);
    let st = state(scope, &[u64::MAX]);
    let mut b = selected_query(43, index, 3, &m, st);
    p64(&mut b, 32, 4096);
    let before = crate::geo_source_session::GeoProcessorLease::live_bytes();
    assert_eq!(execute(&b).unwrap_err(), SourceError::ResourceLimit);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        before
    );
    let mut wrong = selected_query(43, index, 3, &m, st);
    wrong[136] ^= 1;
    assert_eq!(execute(&wrong).unwrap_err(), SourceError::StaleSource);
    let q = u64_at(&execute(&selected_query(43, index, 3, &m, st)).unwrap(), 16);
    assert_eq!(q, st);
    let read = step(q, 3);
    assert_eq!(u32_at(&read, 8), 1);
    let t = read[64..192].to_vec();
    execute(&request(9, q, 3, &[])).unwrap();
    assert_eq!(u32_at(&execute(&request(10, q, 3, &[])).unwrap(), 8), 2);
    let mut forged = t.clone();
    forged[8] ^= 1;
    assert!(execute(&request(8, q, 3, &forged)).is_err());
    execute(&request(8, q, 3, &t)).unwrap();
    close(q, 3);
    let stale_state = state(scope, &[u64::MAX]);
    assert!(execute(&selected_query(43, index, 3, &m, stale_state)).is_err());
    close(stale_state, 0);
    // Reissue exact intent; admitted cancel advances history, so only a newer query can succeed.
    let st = state(scope, &[u64::MAX]);
    let q = u64_at(&execute(&selected_query(43, index, 4, &m, st)).unwrap(), 16);
    assert_eq!(u32_at(&drive_hierarchy(q, 4, &chunks, &mut store), 8), 19);
    let d = selected_data(q, 4);
    close(index, 2);
    close(d, 0);
    close(scope, 0);
}
#[test]
fn unscoped_hierarchy_rejects_selected_query_without_consuming_state() {
    let _serial = test_processor_lock();
    let chunks = vec![chunk(u64::MAX, -5, 0.)];
    let (frame, m) = source_frame(&chunks);
    let scope = scope(frame);
    let st = state(scope, &[u64::MAX]);
    let index = u64_at(&execute(&build_request(frame, 64 << 20)).unwrap(), 16);
    let mut store = BTreeMap::new();
    assert_eq!(
        u32_at(&drive_hierarchy(index, 1, &chunks, &mut store), 8),
        18
    );
    let before = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let r = execute(&selected_query(43, index, 2, &m, st)).unwrap();
    assert_eq!(u32_at(&r, 8), 17);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        before
    );
    close(st, 0);
    let q = u64_at(&execute(&query(index, 2, &m, None)).unwrap(), 16);
    assert_eq!(u32_at(&drive_hierarchy(q, 2, &chunks, &mut store), 8), 19);
    let mut b = scene_request(q, 2);
    p32(&mut b, 8, 44);
    assert_eq!(execute(&b).unwrap_err(), SourceError::InvalidFrame);
    let d = data(q, 2);
    close(q, 2);
    close(index, 1);
    close(d, 0);
    close(scope, 0);
    close(frame, 0);
}
#[test]
fn selected_multipoint_canonical_bytes_rows_and_frozen_intent_survive_lane_disposal() {
    let _serial = test_processor_lock();
    let _tile = crate::geo_tile_cache::test_process_lock();
    let c = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::MultiPoint,
        crs: GeoCrs::Epsg4326,
        xy: &[0., 0., 0.0001, 0., 0.0002, 0., 0.0003, 0.],
        validity: &[1, 0, 1, 1],
        feature_ids: Some(&[u64::MAX, 7, 8, u64::MAX]),
        offsets0: &[0, 2, 2, 2, 4],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let chunks = vec![GeoChunk::encode(&c, None).unwrap()];
    let (index, scope, m, mut store, reference) = selected_index(&chunks, &[u64::MAX, 7, 8]);
    let st = state(scope, &[u64::MAX, 7, 8]);
    let mut b = selected_query(43, index, 3, &m, st);
    for at in [160, 168, 176, 184] {
        p64(&mut b, at, 2);
    }
    let q = u64_at(&execute(&b).unwrap(), 16);
    assert_eq!(u32_at(&drive_hierarchy(q, 3, &chunks, &mut store), 8), 19);
    let d = selected_data(q, 3);
    let packet = read_data(&request(23, d, 0, &[]), 128 << 20).unwrap();
    assert_eq!(&packet[32..], &reference[32..]);
    assert_eq!(u64_at(&packet, 48), 4);
    let f = footer(&packet);
    assert_eq!(u64_at(f, 16), 777);
    assert_eq!(u64_at(f, 24), 3);
    assert_eq!(u64_at(f, 40), 4);
    assert_eq!(u64_at(f, 128), 7);
    assert_eq!(u64_at(f, 144), u64::MAX);
    close(index, 2);
    let rows = u64_at(&execute(&with_budget(request(15, d, 3, &[]))).unwrap(), 16);
    assert_eq!(drive(rows, 3, &chunks).0, 4);
    let rd = u64_at(
        &execute(&with_budget(request(16, rows, 3, &[]))).unwrap(),
        16,
    );
    close(rows, 0);
    let row_packet = read_data(&request(23, rd, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64_at(&row_packet, 32), 4);
    for i in 0..4 {
        assert_ne!(u32_at(&row_packet, 256 + i * 64 + 24) & 128, 0);
    }
    assert_ne!(u32_at(&row_packet, 320 + 24) & 1, 0);
    let mut freeze = [0; HEADER];
    freeze[..4].copy_from_slice(b"XYGJ");
    p32(&mut freeze, 4, 1);
    p32(&mut freeze, 8, 1);
    p64(&mut freeze, 16, d);
    p64(&mut freeze, 24, 3);
    p64(&mut freeze, 32, 128 << 20);
    let frozen = crate::geo_snapshot_protocol::execute(&freeze).unwrap();
    p32(&mut freeze, 8, 20);
    p64(&mut freeze, 16, u64_at(&frozen, 16));
    p64(&mut freeze, 24, 0);
    p64(&mut freeze, 32, 0);
    let raw = crate::geo_snapshot_protocol::read_data(&freeze, 128 << 20).unwrap();
    let cache = crate::geo_tile_cache::GeoTileCache::new(
        crate::geo_tile_cache::GeoTileLimits::default(),
        0,
    )
    .unwrap();
    let imported = crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &raw, 128 << 20).unwrap();
    assert_eq!(imported.selections()[0].selected_ids(), &[7, 8, u64::MAX]);
    assert_eq!(imported.selections()[0].visible_selected_vertices(), 4);
    drop(imported);
    drop(raw);
    p32(&mut freeze, 8, 3);
    crate::geo_snapshot_protocol::execute(&freeze).unwrap();
    close(d, 0);
    assert_eq!(
        execute(&request(10, scope, 0, &[])).unwrap_err(),
        SourceError::ResourceLimit
    );
    close(rd, 0);
    close(scope, 0);
}
#[test]
fn selected_planning_fallback_consumes_state_and_requires_explicit_reissue() {
    let _serial = test_processor_lock();
    let xy: Vec<_> = (0..17)
        .flat_map(|x| (0..17).flat_map(move |y| [-160. + x as f64 * 20., -64. + y as f64 * 8.]))
        .collect();
    let ids: Vec<_> = (0..289).map(|i| u64::MAX - i).collect();
    let c = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::Point,
        crs: GeoCrs::Epsg4326,
        xy: &xy,
        validity: &vec![1; 289],
        feature_ids: Some(&ids),
        offsets0: &[],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let chunks = vec![GeoChunk::encode(&c, None).unwrap()];
    let (index, scope, m, mut store, old) = selected_index(&chunks, &[u64::MAX]);
    let st = state(scope, &[u64::MAX]);
    let q = u64_at(&execute(&selected_query(43, index, 3, &m, st)).unwrap(), 16);
    assert_eq!(q, st);
    loop {
        let s = step(q, 3);
        match u32_at(&s, 8) {
            1 => {
                let t = &s[64..192];
                let bytes = &store[&(u64_at(t, 8), u64_at(t, 40))];
                let mut p = t.to_vec();
                p.extend(bytes);
                execute(&request(7, q, 3, &p)).unwrap();
                execute(&request(8, q, 3, t)).unwrap();
            }
            10 => {
                assert_eq!(u32_at(&s, 48), 1);
                break;
            }
            code => panic!("unexpected {code}"),
        }
    }
    let mut b = scene_request(q, 3);
    p32(&mut b, 8, 44);
    assert!(execute(&b).is_err());
    close(q, 3);
    let st = state(scope, &[u64::MAX]);
    let mut b = selected_query(43, index, 4, &m, st);
    p64(&mut b, 96, 8f64.to_bits());
    let q = u64_at(&execute(&b).unwrap(), 16);
    assert_eq!(u32_at(&drive_hierarchy(q, 4, &chunks, &mut store), 8), 19);
    let d = selected_data(q, 4);
    assert_eq!(u64_at(footer(&old), 24), 1);
    close(index, 2);
    close(d, 0);
    close(scope, 0);
}
#[test]
fn five_distinct_scopes_fifteen_handles_replace_sixteenth_without_quota_expansion() {
    let _serial = test_processor_lock();
    let baseline = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let chunks = vec![chunk(u64::MAX, -5, 0.)];
    let mut fixtures = Vec::new();
    for n in 0..5 {
        fixtures.push(selected_index_in(777 + n, &chunks, &[u64::MAX]));
    }
    let mut old = Vec::new();
    for (index, scope, m, store, _) in &mut fixtures {
        let st = state(*scope, &[u64::MAX]);
        let q = u64_at(&execute(&selected_query(43, *index, 3, m, st)).unwrap(), 16);
        assert_eq!(q, st);
        assert_eq!(u32_at(&drive_hierarchy(q, 3, &chunks, store), 8), 19);
        old.push(selected_data(q, 3));
    }
    // Five distinct privateScope/lane/oldData triples consume15 handles.
    let (index, scope, m, store, _) = &mut fixtures[0];
    let st = state(*scope, &[u64::MAX]);
    assert_eq!(
        execute(&request(1, 0, 0, &[])).unwrap_err(),
        SourceError::ResourceLimit
    );
    let q = u64_at(&execute(&selected_query(43, *index, 4, m, st)).unwrap(), 16);
    assert_eq!(q, st);
    assert_eq!(u32_at(&drive_hierarchy(q, 4, &chunks, store), 8), 19);
    let live = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let mut low = scene_request(q, 4);
    p32(&mut low, 8, 44);
    p64(&mut low, 32, 4096);
    assert_eq!(execute(&low).unwrap_err(), SourceError::ResourceLimit);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        live
    );
    assert_eq!(u32_at(&step(q, 4), 8), 19);
    let d = selected_data(q, 4);
    assert_eq!(d, st);
    assert_eq!(
        execute(&request(1, 0, 0, &[])).unwrap_err(),
        SourceError::ResourceLimit
    );
    for (i, (index, scope, _, _, _)) in fixtures.into_iter().enumerate() {
        close(index, 2);
        let bytes = read_data(&request(23, old[i], 0, &[]), 128 << 20).unwrap();
        assert_eq!(u64_at(footer(&bytes), 16), 777 + i as u64);
        close(old[i], 0);
        if i == 0 {
            close(d, 0);
        }
        close(scope, 0);
    }
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        baseline
    );
}
#[test]
fn reduced_selected_counts_match_canonical_for_duplicate_ids_before_tessellation() {
    let _serial = test_processor_lock();
    let n = 32769;
    let xy = vec![0.; n * 2];
    let ids: Vec<_> = (0..n)
        .map(|i| if i % 7 == 0 { u64::MAX } else { 7 })
        .collect();
    let c = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::Point,
        crs: GeoCrs::Epsg4326,
        xy: &xy,
        validity: &vec![1; n],
        feature_ids: Some(&ids),
        offsets0: &[],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let chunks = vec![GeoChunk::encode(&c, None).unwrap()];
    let (index, scope, m, mut store, reference) = selected_index(&chunks, &[u64::MAX]);
    let st = state(scope, &[u64::MAX]);
    let mut b = selected_query(43, index, 3, &m, st);
    for at in [160, 168, 176, 184] {
        p64(&mut b, at, 2);
    }
    let q = u64_at(&execute(&b).unwrap(), 16);
    assert_eq!(u32_at(&drive_hierarchy(q, 3, &chunks, &mut store), 8), 19);
    let d = selected_data(q, 3);
    let packet = read_data(&request(23, d, 0, &[]), 128 << 20).unwrap();
    assert_eq!(&packet[32..], &reference[32..]);
    assert_eq!(u32_at(&packet, 8), 1);
    let f = footer(&packet);
    let cells = u64_at(f, 32) as usize;
    assert_eq!(cells, (u32_at(&packet, 64) * u32_at(&packet, 68)) as usize);
    assert_eq!(u64_at(f, 40), 4682);
    let counts: Vec<_> = (0..cells).map(|i| u64_at(f, 136 + i * 8)).collect();
    assert_eq!(counts.iter().filter(|&&n| n != 0).count(), 1);
    assert_eq!(counts.iter().sum::<u64>(), 4682);
    close(index, 2);
    close(d, 0);
    close(scope, 0);
}
