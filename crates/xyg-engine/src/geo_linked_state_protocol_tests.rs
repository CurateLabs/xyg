//! Selected ownership tests through exact public bytes, not a parallel host policy.
use super::*;
use crate::geo_tile_cache::test_process_lock;
fn scope(frame: u64, namespace: u64) -> Handle {
    let mut p = [0; 16];
    put64(&mut p, 0, namespace);
    put64(&mut p, 8, u64::MAX);
    Handle(u64at(&execute(&capped(req(32, frame, 1, &p))).unwrap(), 16))
}
fn publish(scope: u64, revision: u64, ids: &[u64], color: [u8; 4]) -> Vec<u8> {
    let mut p = vec![0; 24];
    put64(&mut p, 0, revision);
    p[8..12].copy_from_slice(&color);
    put64(&mut p, 16, ids.len() as u64);
    for id in ids {
        p.extend(id.to_le_bytes());
    }
    capped(req(33, scope, 0, &p))
}
fn selected(
    cmd: u32,
    h: u64,
    seq: u64,
    m: &GeoSourceManifest,
    state: u64,
    revision: u64,
) -> Vec<u8> {
    let mut b = begin(cmd, h, seq, m);
    put64(&mut b, 192, revision);
    put64(&mut b, 232, 8);
    b.extend(state.to_le_bytes());
    b
}
fn footer(bytes: &[u8]) -> &[u8] {
    assert_eq!(u32at(bytes, 4), 2);
    let len = u64at(bytes, 248) as usize;
    let b = &bytes[bytes.len() - len..];
    assert_eq!(&b[..4], b"XYSE");
    b
}
#[test]
fn canonical_selected_state_consumption_cancel_baseline_and_immutable_rows() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let f = fixture(1);
    let scope = scope(f.frame.0, 777);
    let state = Handle(u64at(
        &execute(&publish(
            scope.0,
            2,
            &[u64::MAX, u64::MAX],
            [0, 255, 0, 255],
        ))
        .unwrap(),
        16,
    ));
    // Source mismatch never consumes the issued State capability.
    let mut wrong = selected(35, f.source.0, 2, &f.manifest, state.0, 2);
    wrong[136] ^= 1;
    assert!(matches!(execute(&wrong), Err(SourceError::StaleSource)));
    let before_begin = GeoProcessorLease::live_bytes();
    execute(&selected(35, f.source.0, 2, &f.manifest, state.0, 2)).unwrap();
    assert!(matches!(
        execute(&req(10, state.0, 0, &[])),
        Err(SourceError::StaleSource)
    ));
    let t = execute(&req(6, f.source.0, 2, &[])).unwrap();
    assert_eq!(u32at(&t, 8), 1);
    execute(&req(9, f.source.0, 3, &[])).unwrap();
    execute(&req(8, f.source.0, 0, &t[64..160])).unwrap();
    assert_eq!(GeoProcessorLease::live_bytes(), before_begin);
    assert!(matches!(
        execute(&publish(scope.0, 2, &[1 << 63], [0, 255, 0, 255])),
        Err(SourceError::StaleSource)
    ));
    assert!(matches!(
        execute(&publish(scope.0, 2, &[u64::MAX], [255, 0, 0, 255])),
        Err(SourceError::StaleSource)
    ));
    let replacement = Handle(u64at(
        &execute(&publish(scope.0, 2, &[u64::MAX], [0, 255, 0, 255])).unwrap(),
        16,
    ));
    execute(&selected(35, f.source.0, 4, &f.manifest, replacement.0, 2)).unwrap();
    drive_reads(f.source.0, 4, &f.chunks, None);
    let (frame, bytes) = data(f.source.0, 4, 11);
    let selected_footer = footer(&bytes);
    assert_eq!(u64at(selected_footer, 16), 777);
    assert_eq!(u64at(selected_footer, 24), 1);
    assert_eq!(u64at(selected_footer, 40), 2);
    assert_eq!(u64at(selected_footer, 128), u64::MAX);
    assert!(matches!(
        execute(&begin(5, f.source.0, 5, &f.manifest)),
        Err(SourceError::StaleSource)
    ));
    assert!(matches!(
        execute(&req(10, scope.0, 0, &[])),
        Err(SourceError::ResourceLimit)
    ));
    let mut freeze = [0; HEADER];
    freeze[..4].copy_from_slice(b"XYGJ");
    put32(&mut freeze, 4, 1);
    put32(&mut freeze, 8, 1);
    put64(&mut freeze, 16, frame.0);
    put64(&mut freeze, 24, 4);
    put64(&mut freeze, 32, 128 << 20);
    let selected_frozen = crate::geo_snapshot_protocol::execute(&freeze).unwrap();
    put32(&mut freeze, 8, 20);
    put64(&mut freeze, 16, u64at(&selected_frozen, 16));
    put64(&mut freeze, 24, 0);
    put64(&mut freeze, 32, 0);
    let frozen_bytes = crate::geo_snapshot_protocol::read_data(&freeze, 128 << 20).unwrap();
    let cache = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
    let imported =
        crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &frozen_bytes, 128 << 20).unwrap();
    assert_eq!(imported.selections()[0].selected_ids(), &[u64::MAX]);
    assert_eq!(imported.selections()[0].namespace(), 777);
    assert_eq!(imported.selections()[0].visible_selected_vertices(), 2);
    assert!(frozen_bytes
        .windows(selected_footer.len())
        .any(|bytes| bytes == selected_footer));
    drop(imported);
    drop(frozen_bytes);
    put32(&mut freeze, 8, 3);
    put64(&mut freeze, 32, 0);
    crate::geo_snapshot_protocol::execute(&freeze).unwrap();
    // The original ordinary immutable frame still freezes successfully.
    put64(&mut freeze, 16, f.frame.0);
    put64(&mut freeze, 24, 1);
    put32(&mut freeze, 8, 1);
    put64(&mut freeze, 32, 128 << 20);
    let frozen = crate::geo_snapshot_protocol::execute(&freeze).unwrap();
    put32(&mut freeze, 8, 3);
    put64(&mut freeze, 16, u64at(&frozen, 16));
    put64(&mut freeze, 24, 0);
    put64(&mut freeze, 32, 0);
    crate::geo_snapshot_protocol::execute(&freeze).unwrap();
    let rows = Handle(u64at(
        &execute(&capped(req(15, frame.0, 4, &[]))).unwrap(),
        16,
    ));
    drive_reads(rows.0, 4, &f.chunks, None);
    let rows_data = Handle(u64at(
        &execute(&capped(req(16, rows.0, 4, &[]))).unwrap(),
        16,
    ));
    let packet = read_data(&req(23, rows_data.0, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u32at(&packet, 256 + 24) & 128, 128);
    assert_eq!(u32at(&packet, 320 + 24) & 128, 0);
    assert_eq!(u32at(footer(&packet), 8), 1);
    // Public frame and all row data keep the namespace scope after source disposal.
    drop(rows);
    drop(f);
    assert!(matches!(
        execute(&req(10, scope.0, 0, &[])),
        Err(SourceError::ResourceLimit)
    ));
    drop(rows_data);
    drop(frame);
    execute(&req(10, scope.0, 0, &[])).unwrap();
}
#[test]
fn indexed_selected_replaces_state_then_query_without_spending_an_extra_handle() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let f = fixture(1);
    let scope = scope(f.frame.0, 123);
    let (index, pages) = build_index(&f, 2);
    let state = Handle(u64at(
        &execute(&publish(scope.0, 2, &[u64::MAX], [0, 255, 0, 255])).unwrap(),
        16,
    ));
    let query = execute(&selected(36, index.0, 2, &f.manifest, state.0, 2)).unwrap();
    assert_eq!(u64at(&query, 16), state.0);
    drive_reads(state.0, 2, &[], Some(&pages));
    let out = execute(&capped(req(19, state.0, 2, &style()))).unwrap();
    assert_eq!(u64at(&out, 16), state.0);
    let bytes = read_data(&req(23, state.0, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64at(footer(&bytes), 40), 2);
    assert!(matches!(
        execute(&begin(18, index.0, 3, &f.manifest)),
        Err(SourceError::StaleSource)
    ));
    drop(index);
    drop(f);
    assert!(matches!(
        execute(&req(10, scope.0, 0, &[])),
        Err(SourceError::ResourceLimit)
    ));
    drop(state);
    execute(&req(10, scope.0, 0, &[])).unwrap();
}
#[test]
fn raw_id_limit_precedes_dedup_and_explicit_link_binds_target_namespace() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let f = fixture(1);
    let a = scope(f.frame.0, 1);
    let target = scattered_fixture();
    assert_ne!(f.manifest.digest(), target.manifest.digest());
    let b = scope(target.frame.0, 2);
    assert!(matches!(
        execute(&publish(a.0, 1, &vec![u64::MAX; 10001], [1; 4])),
        Err(SourceError::InvalidFrame)
    ));
    let mut ids: Vec<_> = (0..1000).collect();
    ids.push(u64::MAX);
    let state = Handle(u64at(&execute(&publish(a.0, 1, &ids, [1; 4])).unwrap(), 16));
    let mut p = [0; 16];
    put64(&mut p, 0, state.0);
    put64(&mut p, 8, 2);
    let mut low = capped(req(34, b.0, 0, &p));
    put64(&mut low, 32, 4096);
    let before = GeoProcessorLease::live_bytes();
    assert!(matches!(execute(&low), Err(SourceError::ResourceLimit)));
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    // Retrying the exact target revision proves failed link did not advance admission.
    let linked = Handle(u64at(&execute(&capped(req(34, b.0, 0, &p))).unwrap(), 16));
    assert!(matches!(
        execute(&selected(
            35,
            target.source.0,
            2,
            &target.manifest,
            state.0,
            1
        )),
        Err(SourceError::StaleSource)
    ));
    execute(&selected(
        35,
        target.source.0,
        2,
        &target.manifest,
        linked.0,
        2,
    ))
    .unwrap();
    drive_reads(target.source.0, 2, &target.chunks, None);
    let (frame, bytes) = data(target.source.0, 2, 11);
    assert_eq!(u64at(footer(&bytes), 16), 2);
    drop(frame);
    drop(state);
    drop(f);
    drop(target);
    execute(&req(10, a.0, 0, &[])).unwrap();
    execute(&req(10, b.0, 0, &[])).unwrap();
}

#[test]
fn five_canonical_frames_keep_quotas_and_original_page_on_explicit_engine_parking() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let mut fixtures = Vec::new();
    let mut scopes = Vec::new();
    for i in 0..5 {
        let f = fixture(1);
        scopes.push(scope(f.frame.0, 100 + i));
        fixtures.push(f);
    }
    assert_eq!(registry().lock().unwrap().entries.len(), 15);
    let state = Handle(u64at(
        &execute(&publish(scopes[0].0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    ));
    assert_eq!(registry().lock().unwrap().entries.len(), 16);
    execute(&selected(
        35,
        fixtures[0].source.0,
        2,
        &fixtures[0].manifest,
        state.0,
        2,
    ))
    .unwrap();
    assert_eq!(registry().lock().unwrap().entries.len(), 15);
    drive_reads(fixtures[0].source.0, 2, &fixtures[0].chunks, None);
    let (newframe, bytes) = data(fixtures[0].source.0, 2, 11);
    assert_eq!(u64at(footer(&bytes), 40), 2);
    execute(&req(10, fixtures[0].frame.0, 0, &[])).unwrap();
    fixtures[0].frame = newframe;
    assert_eq!(registry().lock().unwrap().entries.len(), 15);
    let mut start = capped(req(15, fixtures[0].frame.0, 2, &[]));
    put32(&mut start, 60, 1);
    let blocked_rows = Handle(u64at(&execute(&start).unwrap(), 16));
    drive_reads(blocked_rows.0, 2, &fixtures[0].chunks, None);
    assert!(matches!(
        execute(&capped(req(16, blocked_rows.0, 2, &[]))),
        Err(SourceError::ResourceLimit)
    ));
    drop(blocked_rows);
    // Parking two query engines is an explicit caller action, not hidden quota expansion.
    execute(&req(10, fixtures[1].source.0, 0, &[])).unwrap();
    execute(&req(10, fixtures[2].source.0, 0, &[])).unwrap();
    let rows = Handle(u64at(&execute(&start).unwrap(), 16));
    drive_reads(rows.0, 2, &fixtures[0].chunks, None);
    let oldpage = Handle(u64at(
        &execute(&capped(req(16, rows.0, 2, &[]))).unwrap(),
        16,
    ));
    drop(rows);
    let oldbytes = read_data(&req(23, oldpage.0, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64at(&oldbytes, 256), u64::MAX);
    let mut next = capped(req(15, oldpage.0, 2, &[]));
    put32(&mut next, 60, 1);
    let nextrows = Handle(u64at(&execute(&next).unwrap(), 16));
    // Failed authentication cannot publish a partial replacement or invalidate old page.
    let issued = execute(&req(6, nextrows.0, 2, &[])).unwrap();
    let t = &issued[64..160];
    let mut malformed = t.to_vec();
    malformed.extend([0; 8]);
    assert!(execute(&req(7, nextrows.0, 0, &malformed)).is_err());
    execute(&req(8, nextrows.0, 0, t)).unwrap();
    drop(nextrows);
    let nextrows = Handle(u64at(&execute(&next).unwrap(), 16));
    drive_reads(nextrows.0, 2, &fixtures[0].chunks, None);
    let nextpage = Handle(u64at(
        &execute(&capped(req(16, nextrows.0, 2, &[]))).unwrap(),
        16,
    ));
    assert_eq!(registry().lock().unwrap().entries.len(), 16);
    assert_eq!(
        read_data(&req(23, oldpage.0, 0, &[]), 128 << 20).unwrap(),
        oldbytes
    );
    for f in &fixtures {
        assert!(data_len(&req(23, f.frame.0, 0, &[]), 128 << 20).is_ok());
    }
    drop(nextpage);
    drop(nextrows);
    drop(oldpage);
    drop(fixtures);
    for s in scopes {
        execute(&req(10, s.0, 0, &[])).unwrap();
    }
    assert!(registry().lock().unwrap().entries.is_empty());
}

fn scattered_fixture() -> Fixture {
    let column = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::MultiPoint,
        crs: GeoCrs::Epsg4326,
        xy: &[-90., 0., 90., 0.],
        validity: &[1, 1],
        feature_ids: Some(&[u64::MAX, 1 << 63]),
        offsets0: &[0, 1, 2],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let mut builder = GeoManifestBuilder::new();
    let mut chunks = Vec::new();
    for _ in 0..2 {
        let raw = GeoChunk::encode(&column, None).unwrap();
        builder
            .push(&GeoChunk::parse(&raw, 96 << 20).unwrap())
            .unwrap();
        chunks.push(raw);
    }
    finish_fixture(chunks, builder)
}
#[test]
fn five_indexed_frames_replace_at_sixteen_and_fallback_preserves_state() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let mut fixtures = Vec::new();
    let mut scopes = Vec::new();
    let mut indices = Vec::new();
    let mut storage = Vec::new();
    for i in 0..5 {
        let f = scattered_fixture();
        let s = scope(f.frame.0, 200 + i);
        let (index, pages) = build_index(&f, 2);
        execute(&req(10, f.source.0, 0, &[])).unwrap();
        fixtures.push(f);
        scopes.push(s);
        indices.push(index);
        storage.push(pages);
    }
    assert_eq!(registry().lock().unwrap().entries.len(), 15);
    let state = Handle(u64at(
        &execute(&publish(scopes[0].0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    ));
    let mut fallback = selected(36, indices[0].0, 2, &fixtures[0].manifest, state.0, 2);
    put32(&mut fallback, 56, 1);
    let out = execute(&fallback).unwrap();
    assert_eq!(u32at(&out, 8), 10);
    assert_eq!(u32at(&out, 48), 2);
    assert!(matches!(
        registry()
            .lock()
            .unwrap()
            .entries
            .iter()
            .find(|(h, _)| *h == state.0)
            .unwrap()
            .1,
        Entry::State(_)
    ));
    execute(&selected(
        36,
        indices[0].0,
        2,
        &fixtures[0].manifest,
        state.0,
        2,
    ))
    .unwrap();
    assert_eq!(registry().lock().unwrap().entries.len(), 16);
    drive_reads(state.0, 2, &[], Some(&storage[0]));
    let out = execute(&capped(req(19, state.0, 2, &style()))).unwrap();
    assert_eq!(u64at(&out, 16), state.0);
    assert_eq!(registry().lock().unwrap().entries.len(), 16);
    let packet = read_data(&req(23, state.0, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64at(footer(&packet), 40), 2);
    execute(&req(10, fixtures[0].frame.0, 0, &[])).unwrap();
    fixtures[0].frame = state;
    assert_eq!(registry().lock().unwrap().entries.len(), 15);
    drop(indices);
    drop(fixtures);
    for s in scopes {
        execute(&req(10, s.0, 0, &[])).unwrap();
    }
    assert!(registry().lock().unwrap().entries.is_empty());
}

#[test]
fn reduced_canonical_indexed_scene_and_exact_vertex_counts_are_identical() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let f = fixture(9000);
    let scope = scope(f.frame.0, 55);
    let (index, pages) = build_index(&f, 2);
    let state = Handle(u64at(
        &execute(&publish(scope.0, 2, &[u64::MAX], [0, 255, 0, 255])).unwrap(),
        16,
    ));
    execute(&selected(35, f.source.0, 2, &f.manifest, state.0, 2)).unwrap();
    drive_reads(f.source.0, 2, &f.chunks, None);
    let (canonical, mut bytes) = data(f.source.0, 2, 11);
    let extra = footer(&bytes);
    assert_eq!(u32at(&bytes, 8), 1);
    assert_eq!(u64at(extra, 40), 18000);
    assert_eq!(u64at(&bytes, 48), 36000);
    let n = u64at(extra, 32) as usize;
    assert!(n > 0);
    let selected_total = (0..n).map(|i| u64at(extra, 136 + i * 8)).sum::<u64>();
    assert_eq!(selected_total, 18000);
    let state = Handle(u64at(
        &execute(&publish(scope.0, 2, &[u64::MAX], [0, 255, 0, 255])).unwrap(),
        16,
    ));
    execute(&selected(36, index.0, 2, &f.manifest, state.0, 2)).unwrap();
    drive_reads(state.0, 2, &[], Some(&pages));
    execute(&capped(req(19, state.0, 2, &style()))).unwrap();
    let mut indexed = read_data(&req(23, state.0, 0, &[]), 128 << 20).unwrap();
    bytes[16..24].fill(0);
    indexed[16..24].fill(0);
    assert_eq!(bytes, indexed);
    drop(state);
    drop(canonical);
    drop(index);
    drop(f);
    execute(&req(10, scope.0, 0, &[])).unwrap();
}

#[test]
fn selected_query_session_cap_rejects_before_consumption_and_scope_cap_stays_eight() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let f = fixture(1);
    let scope = scope(f.frame.0, 901);
    let (index, pages) = build_index(&f, 2);
    let state = Handle(u64at(
        &execute(&publish(scope.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    ));
    let mut extra = Vec::new();
    for _ in 0..7 {
        extra.push(Handle(u64at(
            &execute(&capped(req(4, 0, 0, &f.manifest.encode().unwrap()))).unwrap(),
            16,
        )));
    }
    let begin = selected(36, index.0, 2, &f.manifest, state.0, 2);
    assert!(matches!(execute(&begin), Err(SourceError::ResourceLimit)));
    assert!(matches!(
        registry()
            .lock()
            .unwrap()
            .entries
            .iter()
            .find(|(h, _)| *h == state.0)
            .unwrap()
            .1,
        Entry::State(_)
    ));
    drop(extra);
    execute(&begin).unwrap();
    drive_reads(state.0, 2, &[], Some(&pages));
    execute(&capped(req(19, state.0, 2, &style()))).unwrap();
    drop(state);
    drop(index);
    drop(f);
    execute(&req(10, scope.0, 0, &[])).unwrap();
    let f = fixture(1);
    let mut scopes = Vec::new();
    for ns in 0..8 {
        scopes.push(self::scope(f.frame.0, ns));
    }
    let mut payload = [0; 16];
    put64(&mut payload, 0, 9);
    put64(&mut payload, 8, u64::MAX);
    assert!(matches!(
        execute(&capped(req(32, f.frame.0, 1, &payload))),
        Err(SourceError::ResourceLimit)
    ));
    drop(scopes);
    drop(f);
    assert!(registry().lock().unwrap().entries.is_empty());
}

#[test]
fn selected_processor_pressure_preserves_state_and_old_paint_before_io() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let f = fixture(1);
    let scope = scope(f.frame.0, 66);
    let state = Handle(u64at(
        &execute(&publish(scope.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    ));
    let before = GeoProcessorLease::live_bytes();
    let pressure =
        GeoProcessorLease::acquire(crate::geo_source::MAX_PROCESSOR_BYTES - before - 2048).unwrap();
    assert!(matches!(
        execute(&selected(35, f.source.0, 2, &f.manifest, state.0, 2)),
        Err(SourceError::ResourceLimit)
    ));
    assert!(matches!(
        registry()
            .lock()
            .unwrap()
            .entries
            .iter()
            .find(|(id, _)| *id == state.0)
            .unwrap()
            .1,
        Entry::State(_)
    ));
    assert_eq!(u32at(&execute(&req(6, f.source.0, 1, &[])).unwrap(), 8), 5);
    assert!(data_len(&req(23, f.frame.0, 0, &[]), 128 << 20).is_ok());
    drop(pressure);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    execute(&selected(35, f.source.0, 2, &f.manifest, state.0, 2)).unwrap();
    drive_reads(f.source.0, 2, &f.chunks, None);
    let (frame, bytes) = data(f.source.0, 2, 11);
    assert_eq!(u64at(footer(&bytes), 40), 2);
    drop(frame);
    drop(f);
    execute(&req(10, scope.0, 0, &[])).unwrap();
}

#[test]
fn empty_explicit_intent_keeps_ordinary_scene_bytes_and_only_adds_typed_provenance() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let f = fixture(1);
    let original = read_data(&req(23, f.frame.0, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u32at(&original, 4), 1);
    assert_eq!(u64at(&original, 248), 0);
    let scope = scope(f.frame.0, 909);
    let state = Handle(u64at(
        &execute(&publish(scope.0, 2, &[], [0, 255, 0, 255])).unwrap(),
        16,
    ));
    execute(&selected(35, f.source.0, 2, &f.manifest, state.0, 2)).unwrap();
    drive_reads(f.source.0, 2, &f.chunks, None);
    let (frame, bytes) = data(f.source.0, 2, 11);
    assert_eq!(
        &bytes[256..256 + u64at(&bytes, 32) as usize],
        &original[256..256 + u64at(&original, 32) as usize]
    );
    let intent = footer(&bytes);
    assert_eq!(intent.len(), 128);
    assert_eq!(u64at(intent, 24), 0);
    assert_eq!(u64at(intent, 32), 0);
    assert_eq!(u64at(intent, 40), 0);
    drop(frame);
    drop(f);
    execute(&req(10, scope.0, 0, &[])).unwrap();
}

#[test]
fn selected_direct_pick_matches_effective_painted_alpha() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let f = fixture(1);
    let scope = scope(f.frame.0, 717);
    for (revision, selected_alpha, ordinary_alpha, expected_id) in
        [(2, 0, 255, 1u64 << 63), (3, 255, 0, u64::MAX)]
    {
        let state = Handle(u64at(
            &execute(&publish(
                scope.0,
                revision,
                &[u64::MAX],
                [0, 255, 0, selected_alpha],
            ))
            .unwrap(),
            16,
        ));
        execute(&selected(
            35,
            f.source.0,
            revision,
            &f.manifest,
            state.0,
            revision,
        ))
        .unwrap();
        drive_reads(f.source.0, revision, &f.chunks, None);
        let mut profile = style();
        profile[3] = ordinary_alpha;
        let frame = Handle(u64at(
            &execute(&capped(req(11, f.source.0, revision, &profile))).unwrap(),
            16,
        ));
        with_scene_data(frame.0, revision, |view| {
            use crate::geo_lod_hit::{hit, GeoLodHit, GeoLodHitMode, GeoLodHitQuery};
            let hits = hit(view.result, read_uniform_style(view.style).unwrap(), GeoLodHitQuery {x: 400., y: 300., tolerance: 0., mode: GeoLodHitMode::All, max_hits: 16}, 128 << 20).unwrap();
            assert_eq!(hits.hits.len(), 2);
            assert!(hits.hits.iter().all(|value| matches!(value, GeoLodHit::Direct(point) if point.identity.feature_id == expected_id)));
            let mut transparent = read_uniform_style(view.style).unwrap();
            transparent.opacity = 0.;
            assert!(hit(view.result, transparent, hits.query, 128 << 20).unwrap().hits.is_empty());
        }).unwrap();
    }
    drop(f);
    drop(scope);
}

#[test]
fn fully_selected_transparent_aggregate_cells_are_not_pickable() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let f = fixture(17000);
    let scope = scope(f.frame.0, 718);
    for (revision, kind) in [(2, 0), (3, 1)] {
        let state = Handle(u64at(
            &execute(&publish(scope.0, revision, &[u64::MAX, 1 << 63], [0; 4])).unwrap(),
            16,
        ));
        let mut begin = selected(35, f.source.0, revision, &f.manifest, state.0, revision);
        put32(&mut begin, 68, kind);
        execute(&begin).unwrap();
        drive_reads(f.source.0, revision, &f.chunks, None);
        let (frame, _) = data(f.source.0, revision, 11);
        with_scene_data(frame.0, revision, |view| {
            use crate::geo_lod_hit::{GeoLodHitMode, GeoLodHitQuery, hit};
            let query = GeoLodHitQuery {
                x: 400.,
                y: 300.,
                tolerance: 0.,
                mode: GeoLodHitMode::All,
                max_hits: 16,
            };
            assert!(!view.result.key.direct);
            assert!(
                hit(
                    view.result,
                    read_uniform_style(view.style).unwrap(),
                    query,
                    128 << 20
                )
                .unwrap()
                .hits
                .is_empty()
            );
        })
        .unwrap();
    }
    drop(f);
    drop(scope);
}

#[test]
fn state_nonce_replay_tombstone_and_failure_atomic_admission() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let f = fixture(1);
    let scope = scope(f.frame.0, 900);
    let mut request = publish(scope.0, 2, &[u64::MAX, 1 << 63], [0, 255, 0, 255]);
    put64(&mut request, 24, 1);
    let reply = execute(&request).unwrap();
    let state = Handle(u64at(&reply, 16));
    let charged = GeoProcessorLease::live_bytes();
    assert_eq!(execute(&request).unwrap(), reply);
    assert_eq!(GeoProcessorLease::live_bytes(), charged);
    let mut changed = request.clone();
    changed[HEADER + 8] ^= 1;
    assert!(matches!(execute(&changed), Err(SourceError::StaleSource)));
    let mut budget_changed = request.clone();
    put64(&mut budget_changed, 40, u64at(&request, 40) - 1);
    assert!(matches!(
        execute(&budget_changed),
        Err(SourceError::StaleSource)
    ));
    let mut reordered = request.clone();
    put64(&mut reordered, HEADER + 24, 1 << 63);
    put64(&mut reordered, HEADER + 32, u64::MAX);
    assert!(matches!(execute(&reordered), Err(SourceError::StaleSource)));
    let mut newer = request.clone();
    put64(&mut newer, 24, 2);
    assert!(matches!(execute(&newer), Err(SourceError::StaleSource)));
    execute(&req(10, state.0, 0, &[])).unwrap();
    std::mem::forget(state);
    assert_eq!(u32at(&execute(&request).unwrap(), 8), 20);
    let mut invalid = newer.clone();
    invalid[HEADER + 12] = 1;
    assert!(matches!(execute(&invalid), Err(SourceError::InvalidFrame)));
    let next = Handle(u64at(&execute(&newer).unwrap(), 16));
    assert!(matches!(execute(&request), Err(SourceError::StaleSource)));
    assert_ne!(next.0, u64at(&reply, 16));
}

#[test]
fn state_nonce_replays_at_full_handle_cap_and_consumption_never_reconstructs() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let initial_handles = registry().lock().unwrap().entries.len();
    let f = fixture(1);
    let pressure_scope = scope(f.frame.0, 902);
    let scope = scope(f.frame.0, 901);
    let mut request = publish(scope.0, 2, &[u64::MAX], [0, 255, 0, 255]);
    put64(&mut request, 24, 1);
    let reply = execute(&request).unwrap();
    let state = u64at(&reply, 16);
    let mut pressure = Vec::new();
    while registry().lock().unwrap().entries.len() < MAX_HANDLES {
        pressure.push(Handle(u64at(
            &execute(&publish(pressure_scope.0, 2, &[u64::MAX], [0, 255, 0, 255])).unwrap(),
            16,
        )));
    }
    assert_eq!(execute(&request).unwrap(), reply);
    let mut newer = request.clone();
    put64(&mut newer, 24, 2);
    assert!(matches!(execute(&newer), Err(SourceError::StaleSource)));
    drop(pressure);
    execute(&selected(35, f.source.0, 2, &f.manifest, state, 2)).unwrap();
    assert_eq!(u32at(&execute(&request).unwrap(), 8), 20);
    execute(&req(9, f.source.0, 2, &[])).unwrap();
    let next = Handle(u64at(&execute(&newer).unwrap(), 16));
    assert_ne!(next.0, state);
    // The canonical query retains the selected Scope after consuming State.
    // Release children before Scope; Handle::drop deliberately ignores errors.
    drop(next);
    drop(f);
    drop(scope);
    drop(pressure_scope);
    assert_eq!(registry().lock().unwrap().entries.len(), initial_handles);
}

#[test]
fn state_nonce_receipt_local_boundary_global_pressure_and_legacy_cannot_bypass() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let f = fixture(1);
    let scope = scope(f.frame.0, 903);
    let mut request = publish(scope.0, 2, &[u64::MAX], [0, 255, 0, 255]);
    put64(&mut request, 24, 9);
    let required = request.len() + 128 + (request.len() - HEADER) * 2 + 1024;
    let before = GeoProcessorLease::live_bytes();
    put64(&mut request, 32, (required - 1) as u64);
    assert!(matches!(execute(&request), Err(SourceError::ResourceLimit)));
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    put64(&mut request, 32, required as u64);
    let pressure =
        GeoProcessorLease::acquire(crate::geo_source::MAX_PROCESSOR_BYTES - before).unwrap();
    assert!(matches!(execute(&request), Err(SourceError::ResourceLimit)));
    drop(pressure);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    let reply = execute(&request).unwrap();
    let state = Handle(u64at(&reply, 16));
    assert!(matches!(
        execute(&publish(scope.0, 3, &[1], [1; 4])),
        Err(SourceError::StaleSource)
    ));
    let charged = GeoProcessorLease::live_bytes();
    let next = {
        let mut r = registry().lock().unwrap();
        let next = r.next;
        r.next = u64::MAX;
        next
    };
    assert_eq!(execute(&request).unwrap(), reply);
    drop(state);
    let retired = execute(&request).unwrap();
    assert_eq!(u32at(&retired, 8), 20);
    assert_eq!(u64at(&retired, 16), 0);
    assert_eq!(u64at(&retired, 24), 2);
    registry().lock().unwrap().next = next;
    assert_eq!(GeoProcessorLease::live_bytes(), charged);
    drop(scope);
    assert!(GeoProcessorLease::live_bytes() < charged);
}

#[path = "geo_selected_mutation_recovery_tests.rs"]
mod selected_mutation_recovery_tests;
