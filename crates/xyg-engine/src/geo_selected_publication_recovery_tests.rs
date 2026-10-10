//! Selected19 journals Data publication, never the consumed36 Query phase.
use super::*;
fn journal(mut b: Vec<u8>, nonce: u64) -> Vec<u8> {
    put64(&mut b, 240, nonce);
    b
}
fn ack(b: &[u8], target: u64, action: u32) -> Vec<u8> {
    let mut p = [0; 16];
    put32(&mut p, 0, u32at(b, 8));
    put32(&mut p, 4, action);
    put64(&mut p, 8, target);
    journal(req(47, u64at(b, 16), u64at(b, 24), &p), u64at(b, 240))
}
#[test]
fn selected_publication_replays_data_distinct_from_query_and_retired_lost_disposal() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let f = fixture(1);
    let sc = scope(f.frame.0, 9901);
    let (index, pages) = build_index(&f, 2);
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    );
    let mutation = journal(selected(36, index.0, 2, &f.manifest, st, 2), 1);
    execute(&mutation).unwrap();
    execute(&ack(&mutation, st, 0)).unwrap();
    drive_reads(st, 2, &[], Some(&pages));
    let publication = journal(capped(req(19, st, 2, &style())), 1);
    let out = execute(&publication).unwrap();
    assert_eq!(u64at(&out, 16), st);
    assert_eq!(execute(&publication).unwrap(), out);
    assert_eq!(u32at(&execute(&mutation).unwrap(), 8), 22);
    assert_eq!(u32at(&execute(&ack(&mutation, st, 0)).unwrap(), 8), 22);
    execute(&ack(&mutation, st, 2)).unwrap();
    assert_eq!(execute(&ack(&publication, st, 0)).unwrap(), reply(st, 2));
    let packet = read_data(&req(23, st, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64at(footer(&packet), 128), u64::MAX);
    let mut changed = publication.clone();
    changed[256] ^= 1;
    assert_eq!(execute(&changed), Err(SourceError::StaleSource));
    drop(index);
    execute(&ack(&mutation, st, 1)).unwrap();
    assert_eq!(execute(&publication).unwrap(), out);
    let retained = Handle(u64at(&execute(&capped(req(26, st, 2, &[]))).unwrap(), 16));
    execute(&req(10, st, 0, &[])).unwrap(); // successful10 reply lost
    assert_eq!(u32at(&execute(&ack(&publication, st, 0)).unwrap(), 8), 22);
    assert_eq!(u32at(&execute(&publication).unwrap(), 8), 22);
    // Lost original receipt may recover only retired target0, never guessed Data.
    assert_eq!(u32at(&execute(&ack(&publication, 0, 0)).unwrap(), 8), 22);
    execute(&ack(&publication, 0, 2)).unwrap();

    execute(&ack(&publication, st, 1)).unwrap();
    drop(f);
    assert_eq!(
        read_data(&req(23, retained.0, 0, &[]), 128 << 20).unwrap(),
        packet
    );
    drop(retained);
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}
#[test]
fn selected_publication_rejects_ordinary_optin_preserves_completed_query_on_failed_budget() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let f = fixture(1);
    let (index, pages) = build_index(&f, 2);
    let query = Handle(u64at(
        &execute(&begin(18, index.0, 2, &f.manifest)).unwrap(),
        16,
    ));
    drive_reads(query.0, 2, &[], Some(&pages));
    assert_eq!(
        execute(&journal(capped(req(19, query.0, 2, &style())), 1)),
        Err(SourceError::InvalidFrame)
    );
    let (ordinary, bytes) = data(query.0, 2, 19);
    assert_ne!(ordinary.0, query.0);
    assert!(!bytes.is_empty());
    drop(ordinary);
    drop(query);
    drop(index);
    let sc = scope(f.frame.0, 9902);
    let (index, pages) = build_index(&f, 2);
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    );
    execute(&selected(36, index.0, 2, &f.manifest, st, 2)).unwrap();
    drive_reads(st, 2, &[], Some(&pages));
    let mut p = journal(capped(req(19, st, 2, &style())), 1);
    put64(&mut p, 32, 8192);
    let held = GeoProcessorLease::live_bytes();
    assert_eq!(execute(&p), Err(SourceError::ResourceLimit));
    assert_eq!(GeoProcessorLease::live_bytes(), held);
    assert_eq!(u32at(&execute(&req(6, st, 2, &[])).unwrap(), 8), 12);
    put64(&mut p, 32, 128 << 20);
    execute(&p).unwrap();
    execute(&ack(&p, st, 0)).unwrap();
    execute(&req(10, st, 0, &[])).unwrap();
    execute(&ack(&p, st, 2)).unwrap();
    execute(&ack(&p, st, 1)).unwrap();
    drop(index);
    drop(f);
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}

#[test]
fn selected_publication_held_query_stamp_pressure_release_then_atomic_admission() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let f = fixture(1);
    let sc = scope(f.frame.0, 9903);
    let (index, pages) = build_index(&f, 2);
    let mut births = Vec::new();
    for n in 1..=15 {
        let st = u64at(
            &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
            16,
        );
        let b = journal(selected(35, f.source.0, n + 1, &f.manifest, st, 2), n);
        execute(&b).unwrap();
        execute(&ack(&b, f.source.0, 0)).unwrap();
        execute(&req(9, f.source.0, n + 1, &[])).unwrap();
        births.push(b);
    }
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    );
    let m = journal(selected(36, index.0, 2, &f.manifest, st, 2), 1);
    execute(&m).unwrap();
    execute(&ack(&m, st, 0)).unwrap();
    drive_reads(st, 2, &[], Some(&pages));
    let p = journal(capped(req(19, st, 2, &style())), 1);
    let held = GeoProcessorLease::live_bytes();
    assert_eq!(execute(&p), Err(SourceError::ResourceLimit));
    assert_eq!(GeoProcessorLease::live_bytes(), held);
    assert_eq!(u32at(&execute(&req(6, st, 2, &[])).unwrap(), 8), 12);
    execute(&ack(&births[0], f.source.0, 2)).unwrap();
    execute(&p).unwrap();
    execute(&ack(&p, st, 0)).unwrap();
    assert_eq!(u32at(&execute(&ack(&m, st, 0)).unwrap(), 8), 22);
    execute(&ack(&m, st, 2)).unwrap();
    execute(&req(10, st, 0, &[])).unwrap();
    execute(&ack(&p, st, 2)).unwrap();
    execute(&ack(&p, st, 1)).unwrap();
    for b in &births[1..] {
        execute(&ack(b, f.source.0, 2)).unwrap();
    }
    drop(index);
    execute(&ack(&m, st, 1)).unwrap();
    drop(f);
    execute(&ack(births.last().unwrap(), u64at(&births[0], 16), 1)).unwrap();
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}

#[test]
fn selected_publication_eight_data_cap_preserves_query_and_old_scene() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let f = fixture(1);
    let sc = scope(f.frame.0, 9904);
    let (index, pages) = build_index(&f, 2);
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    );
    execute(&selected(36, index.0, 2, &f.manifest, st, 2)).unwrap();
    drive_reads(st, 2, &[], Some(&pages));
    let mut copies = Vec::new();
    for _ in 0..7 {
        copies.push(Handle(u64at(
            &execute(&capped(req(26, f.frame.0, 1, &[]))).unwrap(),
            16,
        )));
    }
    let p = journal(capped(req(19, st, 2, &style())), 1);
    let held = GeoProcessorLease::live_bytes();
    assert_eq!(execute(&p), Err(SourceError::ResourceLimit));
    assert_eq!(GeoProcessorLease::live_bytes(), held);
    assert_eq!(u32at(&execute(&req(6, st, 2, &[])).unwrap(), 8), 12);
    assert!(
        !read_data(&req(23, f.frame.0, 0, &[]), 128 << 20)
            .unwrap()
            .is_empty()
    );
    drop(copies.pop());
    execute(&p).unwrap();
    execute(&ack(&p, st, 0)).unwrap();
    let mut wrong = ack(&p, st, 0);
    put64(&mut wrong, 24, 3);
    assert_eq!(execute(&wrong), Err(SourceError::StaleSource));
    put64(&mut wrong, 24, 2);
    put64(&mut wrong, 16, f.frame.0);
    assert_eq!(execute(&wrong), Err(SourceError::StaleSource));
    execute(&req(10, st, 0, &[])).unwrap();
    execute(&ack(&p, st, 2)).unwrap();
    execute(&ack(&p, st, 1)).unwrap();
    drop(copies);
    drop(index);
    drop(f);
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}
fn try_publication_budget(limit: usize, legacy_retry: bool) -> bool {
    try_publication_scope_budget(limit, legacy_retry, false)
}
fn try_publication_scope_budget(limit: usize, legacy_retry: bool, newer_scope: bool) -> bool {
    let before = GeoProcessorLease::live_bytes();
    let f = fixture(1);
    let sc = scope(f.frame.0, 9905);
    let (index, pages) = build_index(&f, 2);
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    );
    execute(&selected(36, index.0, 2, &f.manifest, st, 2)).unwrap();
    drive_reads(st, 2, &[], Some(&pages));
    let newer_state = if newer_scope {
        let ids: Vec<u64> = (0..10_000).collect();
        let mut issued = publish(sc.0, 3, &ids, [3; 4]);
        put64(&mut issued, 24, 1);
        Some(Handle(u64at(&execute(&issued).unwrap(), 16)))
    } else {
        None
    };
    let mut p = journal(capped(req(19, st, 2, &style())), 1);
    put64(&mut p, 32, limit as u64);
    let held = GeoProcessorLease::live_bytes();
    let accepted = match execute(&p) {
        Ok(out) => {
            assert_eq!(u64at(&out, 16), st);
            execute(&ack(&p, st, 0)).unwrap();
            true
        }
        Err(SourceError::ResourceLimit) => {
            assert_eq!(GeoProcessorLease::live_bytes(), held);
            assert_eq!(u32at(&execute(&req(6, st, 2, &[])).unwrap(), 8), 12);
            false
        }
        other => panic!("unexpected {other:?}"),
    };
    if !accepted && legacy_retry {
        put64(&mut p, 240, 0);
        execute(&p).unwrap();
    }
    execute(&req(10, st, 0, &[])).unwrap();
    if accepted {
        execute(&ack(&p, st, 2)).unwrap();
        execute(&ack(&p, st, 1)).unwrap();
    }
    drop(index);
    drop(f);
    drop(newer_state);
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    accepted
}
#[test]
fn selected_publication_exact_local_boundary_and_nonce_zero_policy_unchanged() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let mut low = 8192;
    let mut high = 128 << 20;
    while low + 1 < high {
        let mid = (low + high) / 2;
        if try_publication_budget(mid, false) {
            high = mid;
        } else {
            low = mid;
        }
    }
    assert!(try_publication_budget(high, false));
    assert!(!try_publication_budget(high - 1, true));
}

#[test]
fn selected_publication_five_lanes_publish_at_sixteenth_handle_with_independent_rows() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let mut fixtures = Vec::new();
    let mut scopes = Vec::new();
    let mut indices = Vec::new();
    let mut storage = Vec::new();
    for i in 0..5 {
        let f = fixture(1);
        let sc = scope(f.frame.0, 9910 + i);
        let (index, pages) = build_index(&f, 2);
        execute(&req(10, f.source.0, 0, &[])).unwrap();
        fixtures.push(f);
        scopes.push(sc);
        indices.push(index);
        storage.push(pages);
    }
    let mut receipts = Vec::new();
    for i in 0..5 {
        assert_eq!(registry().lock().unwrap().entries.len(), 15);
        let st = u64at(
            &execute(&publish(scopes[i].0, 2, &[u64::MAX], [2; 4])).unwrap(),
            16,
        );
        execute(&selected(36, indices[i].0, 2, &fixtures[i].manifest, st, 2)).unwrap();
        assert_eq!(registry().lock().unwrap().entries.len(), 16);
        drive_reads(st, 2, &[], Some(&storage[i]));
        let p = journal(capped(req(19, st, 2, &style())), 1);
        execute(&p).unwrap();
        execute(&ack(&p, st, 0)).unwrap();
        assert_eq!(registry().lock().unwrap().entries.len(), 16);
        execute(&req(10, fixtures[i].frame.0, 0, &[])).unwrap();
        fixtures[i].frame = Handle(st);
        receipts.push(p);
    }
    drop(indices); // Frame authority is independent of original Index ownership.
    for i in 0..5 {
        let st = fixtures[i].frame.0;
        let rows = Handle(u64at(&execute(&capped(req(15, st, 2, &[]))).unwrap(), 16));
        drive_reads(rows.0, 2, &fixtures[i].chunks, None);
        let rows_data = Handle(u64at(
            &execute(&capped(req(16, rows.0, 2, &[]))).unwrap(),
            16,
        ));
        let packet = read_data(&req(23, rows_data.0, 0, &[]), 128 << 20).unwrap();
        assert_eq!(u64at(footer(&packet), 128), u64::MAX);
        drop(rows_data);
        drop(rows);
    }
    drop(fixtures);
    for p in receipts {
        execute(&ack(&p, u64at(&p, 16), 2)).unwrap();
        execute(&ack(&p, u64at(&p, 16), 1)).unwrap();
    }
    drop(scopes);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}

#[test]
fn selected_publication_newer_scope_state_and_large_nonce_receipt_in_local_boundary() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let mut low = 8192;
    let mut high = 128 << 20;
    while low + 1 < high {
        let mid = (low + high) / 2;
        if try_publication_budget(mid, false) {
            high = mid;
        } else {
            low = mid;
        }
    }
    let baseline = high;
    assert!(!try_publication_scope_budget(baseline, false, true));
    low = baseline;
    high = 128 << 20;
    while low + 1 < high {
        let mid = (low + high) / 2;
        if try_publication_scope_budget(mid, false, true) {
            high = mid;
        } else {
            low = mid;
        }
    }
    assert!(high > baseline + 80_000);
    assert!(try_publication_scope_budget(high, false, true));
    assert!(!try_publication_scope_budget(high - 1, false, true));
}
