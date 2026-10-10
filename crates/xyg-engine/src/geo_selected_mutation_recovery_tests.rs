//! Raw opt-in selected mutation proofs; ordinary selected policy remains shared.
use super::*;
fn journal(mut b: Vec<u8>, nonce: u64) -> Vec<u8> {
    put64(&mut b, 240, nonce);
    b
}
fn mutation_ack(b: &[u8], target: u64, action: u32) -> Vec<u8> {
    let mut p = [0; 16];
    put32(&mut p, 0, u32at(b, 8));
    put32(&mut p, 4, action);
    put64(&mut p, 8, target);
    journal(req(47, u64at(b, 16), u64at(b, 24), &p), u64at(b, 240))
}
fn retire(b: &[u8], target: u64) {
    assert_eq!(u32at(&execute(&mutation_ack(b, target, 0)).unwrap(), 8), 22);
    assert_eq!(u32at(&execute(&mutation_ack(b, target, 2)).unwrap(), 8), 0);
}
fn forget_mutation(b: &[u8], target: u64) {
    execute(&mutation_ack(b, target, 1)).unwrap();
}
#[test]
fn selected_mutation_replay_consumed_state_cancel_and_retired_loan_stays_charged() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let f = fixture(1);
    let sc = scope(f.frame.0, 9801);
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [0, 255, 0, 255])).unwrap(),
        16,
    );
    let b = journal(selected(35, f.source.0, 2, &f.manifest, st, 2), 1);
    let out = execute(&b).unwrap();
    assert_eq!(u64at(&out, 16), f.source.0);
    assert_eq!(execute(&b).unwrap(), out);
    let mut changed = b.clone();
    changed[256] ^= 1;
    assert_eq!(execute(&changed), Err(SourceError::StaleSource));
    let ticket = execute(&req(6, f.source.0, 2, &[])).unwrap();
    assert_eq!(u32at(&ticket, 8), 1);
    let held = GeoProcessorLease::live_bytes();
    execute(&req(9, f.source.0, 2, &[])).unwrap();
    assert_eq!(u32at(&execute(&b).unwrap(), 8), 22);
    retire(&b, f.source.0);
    let after_cancel = GeoProcessorLease::live_bytes();
    assert!(after_cancel < held);
    execute(&req(8, f.source.0, 0, &ticket[64..160])).unwrap();
    assert!(GeoProcessorLease::live_bytes() < after_cancel);
    // Retiring an operation does not grant Source disposal or consume its old result.
    assert_eq!(
        u64at(&execute(&req(6, f.source.0, 2, &[])).unwrap(), 16),
        f.source.0
    );
    drop(f);
    forget_mutation(&b, u64at(&b, 16));
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}
#[test]
fn selected_mutation_completed_result_then_newer_operation_never_reclaims_source_phase() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let f = fixture(1);
    let sc = scope(f.frame.0, 9802);
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [0, 255, 0, 255])).unwrap(),
        16,
    );
    let old = journal(selected(35, f.source.0, 2, &f.manifest, st, 2), 1);
    let out = execute(&old).unwrap();
    execute(&mutation_ack(&old, f.source.0, 0)).unwrap();
    drive_reads(f.source.0, 2, &f.chunks, None);
    assert_eq!(execute(&old).unwrap(), out);
    let (accepted, bytes) = data(f.source.0, 2, 11);
    let st2 = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [0, 255, 0, 255])).unwrap(),
        16,
    );
    let newer = journal(selected(35, f.source.0, 3, &f.manifest, st2, 2), 2);
    execute(&newer).unwrap();
    assert_eq!(execute(&old), Err(SourceError::StaleSource));
    retire(&old, f.source.0);
    let ticket = execute(&req(6, f.source.0, 3, &[])).unwrap();
    assert_eq!(u32at(&ticket, 8), 1);
    assert_eq!(
        read_data(&req(23, accepted.0, 0, &[]), 128 << 20).unwrap(),
        bytes
    );
    execute(&req(9, f.source.0, 3, &[])).unwrap();
    // The step above issued a read; explicit Source disposal retains it for exact ACK.
    let pending = execute(&req(6, f.source.0, 3, &[])).unwrap();
    assert_eq!(u32at(&pending, 8), 5);
    retire(&newer, f.source.0);
    execute(&req(8, f.source.0, 0, &ticket[64..160])).unwrap();
    drop(accepted);
    drop(f);
    forget_mutation(&newer, u64at(&newer, 16));
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}
#[test]
fn selected_mutation_indexed_replacement_replay_does_not_grant_data_phase() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let f = fixture(1);
    let sc = scope(f.frame.0, 9803);
    let (index, pages) = build_index(&f, 2);
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [0, 255, 0, 255])).unwrap(),
        16,
    );
    let b = journal(selected(36, index.0, 2, &f.manifest, st, 2), 1);
    let out = execute(&b).unwrap();
    assert_eq!(u64at(&out, 16), st);
    assert_eq!(execute(&b).unwrap(), out);
    execute(&mutation_ack(&b, st, 0)).unwrap();
    drive_reads(st, 2, &[], Some(&pages));
    let data_out = execute(&capped(req(19, st, 2, &style()))).unwrap();
    assert_eq!(u64at(&data_out, 16), st);
    assert_eq!(u32at(&execute(&b).unwrap(), 8), 22);
    retire(&b, st);
    let packet = read_data(&req(23, st, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64at(footer(&packet), 128), u64::MAX);
    drop(index);
    forget_mutation(&b, st);
    execute(&req(10, st, 0, &[])).unwrap();
    drop(f);
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}

#[test]
fn selected_mutation_fallback_preserves_state_and_transition_then_same_nonce_admits() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let f = scattered_fixture();
    let sc = scope(f.frame.0, 9804);
    let (index, pages) = build_index(&f, 2);
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    );
    let b = journal(selected(36, index.0, 2, &f.manifest, st, 2), 1);
    let mut fallback = b.clone();
    put32(&mut fallback, 56, 1);
    let held = GeoProcessorLease::live_bytes();
    let out = execute(&fallback).unwrap();
    assert_eq!(u32at(&out, 8), 10);
    assert_eq!(u32at(&out, 48), 2);
    assert_eq!(execute(&fallback).unwrap(), out);
    assert_eq!(GeoProcessorLease::live_bytes(), held);
    assert_eq!(
        execute(&mutation_ack(&fallback, st, 0)),
        Err(SourceError::StaleSource)
    );
    // Non-admitted fallback journals nothing; the same sequence/nonce may admit
    // with corrected budget while the unchanged State and transition survive.
    execute(&b).unwrap();
    execute(&mutation_ack(&b, st, 0)).unwrap();
    drop(index);
    assert_eq!(u64at(&execute(&b).unwrap(), 16), st);
    drive_reads(st, 2, &[], Some(&pages));
    execute(&capped(req(19, st, 2, &style()))).unwrap();
    retire(&b, st);
    forget_mutation(&b, st);
    execute(&req(10, st, 0, &[])).unwrap();
    drop(f);
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}
fn try_canonical_budget(limit: usize) -> bool {
    let before = GeoProcessorLease::live_bytes();
    let f = fixture(1);
    let sc = scope(f.frame.0, 9805);
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    );
    let mut b = journal(selected(35, f.source.0, 2, &f.manifest, st, 2), 1);
    put64(&mut b, 32, limit as u64);
    let admitted = match execute(&b) {
        Ok(_) => {
            execute(&req(9, f.source.0, 2, &[])).unwrap();
            // Original receipt could be lost; zero-target retirement is private
            // current-receipt authority, not a guessed Source handle.
            retire(&b, 0);
            true
        }
        Err(SourceError::ResourceLimit) => {
            execute(&req(10, st, 0, &[])).unwrap();
            assert_eq!(u32at(&execute(&req(6, f.source.0, 1, &[])).unwrap(), 8), 5);
            false
        }
        other => panic!("unexpected budget outcome {other:?}"),
    };
    drop(f);
    if admitted {
        forget_mutation(&b, 0);
    }
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    admitted
}
#[test]
fn selected_mutation_local_budget_exact_boundary_and_one_byte_under_preserve_state() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let mut low = 8192;
    let mut high = 128 << 20;
    while low + 1 < high {
        let mid = (low + high) / 2;
        if try_canonical_budget(mid) {
            high = mid;
        } else {
            low = mid;
        }
    }
    assert!(try_canonical_budget(high));
    assert!(!try_canonical_budget(high - 1));
    // Nonce-zero keeps the original local admission contract on the same
    // Source after failed opt-in preflight; no permanent budget mutation.
    let f = fixture(1);
    let sc = scope(f.frame.0, 9807);
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    );
    let mut b = journal(selected(35, f.source.0, 2, &f.manifest, st, 2), 1);
    put64(&mut b, 32, (high - 1) as u64);
    assert_eq!(execute(&b), Err(SourceError::ResourceLimit));
    put64(&mut b, 240, 0);
    execute(&b).unwrap();
    execute(&req(9, f.source.0, 2, &[])).unwrap();
    drop(f);
    drop(sc);
}
#[test]
fn selected_mutation_stamp_pressure_rejects_before_consumption_then_releases() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let f = fixture(1);
    let sc = scope(f.frame.0, 9806);
    let mut births = Vec::new();
    for n in 1..=16 {
        let st = u64at(
            &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
            16,
        );
        let b = journal(selected(35, f.source.0, n + 1, &f.manifest, st, 2), n);
        execute(&b).unwrap();
        execute(&mutation_ack(&b, f.source.0, 0)).unwrap();
        execute(&req(9, f.source.0, n + 1, &[])).unwrap();
        births.push(b);
    }
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    );
    let next = journal(selected(35, f.source.0, 18, &f.manifest, st, 2), 17);
    let held = GeoProcessorLease::live_bytes();
    assert_eq!(execute(&next), Err(SourceError::ResourceLimit));
    assert_eq!(GeoProcessorLease::live_bytes(), held);
    retire(&births[0], f.source.0);
    execute(&next).unwrap();
    execute(&mutation_ack(&next, f.source.0, 0)).unwrap();
    execute(&req(9, f.source.0, 18, &[])).unwrap();
    for b in &births[1..] {
        retire(b, f.source.0);
    }
    retire(&next, f.source.0);
    drop(f);
    forget_mutation(&next, u64at(&next, 16));
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}

#[test]
fn selected_mutation_five_indexed_lanes_replace_at_sixteen_without_quota_changes() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let mut fixtures = Vec::new();
    let mut scopes = Vec::new();
    let mut indices = Vec::new();
    let mut storage = Vec::new();
    for i in 0..5 {
        let f = fixture(1);
        let sc = scope(f.frame.0, 9900 + i);
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
        let b = journal(
            selected(36, indices[i].0, 2, &fixtures[i].manifest, st, 2),
            1,
        );
        let out = execute(&b).unwrap();
        assert_eq!(execute(&b).unwrap(), out);
        execute(&mutation_ack(&b, st, 0)).unwrap();
        assert_eq!(registry().lock().unwrap().entries.len(), 16);
        drive_reads(st, 2, &[], Some(&storage[i]));
        execute(&capped(req(19, st, 2, &style()))).unwrap();
        assert_eq!(registry().lock().unwrap().entries.len(), 16);
        retire(&b, st);
        execute(&req(10, fixtures[i].frame.0, 0, &[])).unwrap();
        fixtures[i].frame = Handle(st);
        receipts.push((b, st));
    }
    drop(indices);
    for (b, st) in receipts {
        forget_mutation(&b, st);
    }
    drop(fixtures);
    drop(scopes);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    assert!(registry().lock().unwrap().entries.is_empty());
}

#[test]
fn selected_mutation_processing_failure_retires_birth_not_loan_or_old_scene() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let f = fixture(1);
    let sc = scope(f.frame.0, 9808);
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    );
    let b = journal(selected(35, f.source.0, 2, &f.manifest, st, 2), 1);
    execute(&b).unwrap();
    let mut bad_ack = mutation_ack(&b, f.source.0, 0);
    put64(&mut bad_ack, 24, 3);
    assert_eq!(execute(&bad_ack), Err(SourceError::StaleSource));
    put64(&mut bad_ack, 24, 2);
    put64(&mut bad_ack, 16, f.frame.0);
    assert_eq!(execute(&bad_ack), Err(SourceError::StaleSource));
    let ticket = execute(&req(6, f.source.0, 2, &[])).unwrap();
    let mut payload = ticket[64..160].to_vec();
    let mut corrupt = f.chunks[0].clone();
    corrupt[128] ^= 1;
    payload.extend(corrupt);
    assert!(execute(&req(7, f.source.0, 0, &payload)).is_err());
    let charged = GeoProcessorLease::live_bytes();
    assert_eq!(u32at(&execute(&b).unwrap(), 8), 22);
    retire(&b, 0);
    assert_eq!(GeoProcessorLease::live_bytes(), charged);
    assert_eq!(u32at(&execute(&req(6, f.source.0, 2, &[])).unwrap(), 8), 2);
    assert!(data_len(&req(23, f.frame.0, 0, &[]), 128 << 20).is_ok());
    execute(&req(8, f.source.0, 0, &ticket[64..160])).unwrap();
    assert!(GeoProcessorLease::live_bytes() < charged);
    drop(f);
    forget_mutation(&b, 0);
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}

#[test]
fn selected_mutation_index_cancel_complete_and_dispose_pending_retire_not_release_loan() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let f = fixture(1);
    let sc = scope(f.frame.0, 9809);
    let (index, pages) = build_index(&f, 2);
    let mut last = None;
    for mode in 0..3 {
        let seq = 2 + mode;
        let st = u64at(
            &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
            16,
        );
        let b = journal(selected(36, index.0, seq, &f.manifest, st, 2), seq);
        let out = execute(&b).unwrap();
        assert_eq!(execute(&b).unwrap(), out);
        if mode == 1 {
            drive_reads(st, seq, &[], Some(&pages));
            assert_eq!(execute(&b).unwrap(), out);
            execute(&req(9, st, seq, &[])).unwrap();
            retire(&b, st);
            execute(&req(10, st, 0, &[])).unwrap();
        } else {
            let t = execute(&req(6, st, seq, &[])).unwrap();
            assert_eq!(u32at(&t, 8), 1);
            let command = if mode == 0 { 9 } else { 10 };
            let result = execute(&req(command, st, if mode == 0 { seq } else { 0 }, &[])).unwrap();
            if mode == 2 {
                assert_eq!(u32at(&result, 8), 2);
            }
            let held = GeoProcessorLease::live_bytes();
            assert_eq!(u32at(&execute(&b).unwrap(), 8), 22);
            retire(&b, st);
            assert_eq!(GeoProcessorLease::live_bytes(), held);
            execute(&req(8, st, 0, &t[64..160])).unwrap();
            assert!(GeoProcessorLease::live_bytes() < held);
            execute(&req(10, st, 0, &[])).unwrap();
        }
        assert!(
            registry()
                .lock()
                .unwrap()
                .entries
                .iter()
                .any(|(id, e)| *id == index.0 && matches!(e, Entry::Index(_)))
        );
        last = Some((b, st));
    }
    drop(index);
    let (b, st) = last.unwrap();
    forget_mutation(&b, st);
    drop(f);
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}

#[test]
fn selected_mutation_per_call_limit_persists_through_read_admission_without_shrinking_source() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let before = GeoProcessorLease::live_bytes();
    let mut low = 8192;
    let mut high = 128 << 20;
    while low + 1 < high {
        let mid = (low + high) / 2;
        if try_canonical_budget(mid) {
            high = mid;
        } else {
            low = mid;
        }
    }
    let f = fixture(1);
    let sc = scope(f.frame.0, 9810);
    let st = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    );
    let mut b = journal(selected(35, f.source.0, 2, &f.manifest, st, 2), 1);
    put64(&mut b, 32, high as u64);
    let out = execute(&b).unwrap();
    let held = GeoProcessorLease::live_bytes();
    assert_eq!(
        execute(&req(6, f.source.0, 2, &[])),
        Err(SourceError::ResourceLimit)
    );
    assert_eq!(GeoProcessorLease::live_bytes(), held);
    assert_eq!(execute(&b).unwrap(), out);
    execute(&req(9, f.source.0, 2, &[])).unwrap();
    retire(&b, f.source.0);
    let st2 = u64at(
        &execute(&publish(sc.0, 2, &[u64::MAX], [2; 4])).unwrap(),
        16,
    );
    execute(&selected(35, f.source.0, 3, &f.manifest, st2, 2)).unwrap();
    drive_reads(f.source.0, 3, &f.chunks, None);
    drop(f);
    forget_mutation(&b, u64at(&b, 16));
    drop(sc);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}
