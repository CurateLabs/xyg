//! Exact hierarchy admission/publication births are independent at one handle.
use super::*;
use crate::geo_source_session::GeoProcessorLease;
fn journal(mut b: Vec<u8>, nonce: u64) -> Vec<u8> {
    p64(&mut b, 240, nonce);
    b
}
fn ack(b: &[u8], target: u64, action: u32) -> Vec<u8> {
    let mut p = [0; 16];
    p32(&mut p, 0, u32_at(b, 8));
    p32(&mut p, 4, action);
    p64(&mut p, 8, target);
    journal(
        request(47, u64_at(b, 16), u64_at(b, 24), &p),
        u64_at(b, 240),
    )
}
fn publication(q: u64, seq: u64) -> Vec<u8> {
    let mut b = scene_request(q, seq);
    p32(&mut b, 8, 44);
    journal(b, 1)
}
fn release(b: &[u8], target: u64) {
    assert_eq!(u32_at(&execute(&ack(b, target, 0)).unwrap(), 8), 22);
    execute(&ack(b, target, 2)).unwrap();
}
#[test]
fn hierarchy_recovery_same_handle_distinct_births_retained_full_rows() {
    let _serial = test_processor_lock();
    let before = GeoProcessorLease::live_bytes();
    let chunks = vec![chunk(u64::MAX, -5, 0.), chunk(7, 100, 0.0001)];
    let (index, sc, m, mut store, _) = selected_index(&chunks, &[u64::MAX, 7]);
    let st = state(sc, &[u64::MAX, 7]);
    let query = journal(selected_query(43, index, 3, &m, st), 1);
    let admitted = execute(&query).unwrap();
    assert_eq!(u64_at(&admitted, 16), st);
    assert_eq!(execute(&query).unwrap(), admitted);
    execute(&ack(&query, st, 0)).unwrap();
    assert_eq!(u32_at(&drive_hierarchy(st, 3, &chunks, &mut store), 8), 19);
    let data = publication(st, 3);
    let out = execute(&data).unwrap();
    assert_eq!(u64_at(&out, 16), st);
    assert_eq!(execute(&data).unwrap(), out);
    release(&query, st);
    execute(&ack(&data, st, 0)).unwrap();
    let packet = read_data(&request(23, st, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64_at(footer(&packet), 128), 7);
    assert_eq!(u64_at(footer(&packet), 136), u64::MAX);
    let retained = u64_at(&execute(&with_budget(request(26, st, 3, &[]))).unwrap(), 16);
    close(index, 2);
    execute(&ack(&query, st, 1)).unwrap();
    assert_eq!(execute(&data).unwrap(), out);
    close(st, 0); // successful10 response lost; no Data recreation on replay.
    release(&data, st);
    execute(&ack(&data, st, 1)).unwrap();
    assert_eq!(
        read_data(&request(23, retained, 0, &[]), 128 << 20).unwrap(),
        packet
    );
    close(retained, 0);
    close(sc, 0);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}

#[test]
fn hierarchy_recovery_cancel_failure_and_pending_disposal_retire_before_exact_ack() {
    let _serial = test_processor_lock();
    let before = GeoProcessorLease::live_bytes();
    let chunks = vec![chunk(u64::MAX, -5, 0.)];
    let (index, sc, m, mut store, _) = selected_index(&chunks, &[u64::MAX]);
    for (i, failure) in [false, true].into_iter().enumerate() {
        let seq = 3 + i as u64;
        let st = state(sc, &[u64::MAX]);
        let b = journal(selected_query(43, index, seq, &m, st), 1 + i as u64);
        execute(&b).unwrap();
        execute(&ack(&b, st, 0)).unwrap();
        let read = step(st, seq);
        assert_eq!(u32_at(&read, 8), 1);
        let t = &read[64..192];
        let charged = GeoProcessorLease::live_bytes();
        if failure {
            let mut bytes = store[&(u64_at(t, 8), u64_at(t, 40))].clone();
            bytes[0] ^= 1;
            let mut p = t.to_vec();
            p.extend(bytes);
            assert!(execute(&request(7, st, seq, &p)).is_err());
        } else {
            execute(&request(9, st, seq, &[])).unwrap();
        }
        assert_eq!(GeoProcessorLease::live_bytes(), charged);
        assert_eq!(u32_at(&execute(&request(10, st, seq, &[])).unwrap(), 8), 2);
        assert_eq!(u32_at(&execute(&b).unwrap(), 8), 22);
        release(&b, st); // receipt retirement does not settle authenticated loans.
        assert!(GeoProcessorLease::live_bytes() >= charged - (8192 + 4 * b.len() + 512));
        let mut forged = t.to_vec();
        forged[8] ^= 1;
        assert!(execute(&request(8, st, seq, &forged)).is_err());
        execute(&request(8, st, seq, t)).unwrap();
        close(st, seq);
    }
    let st = state(sc, &[u64::MAX]);
    let b = journal(selected_query(43, index, 5, &m, st), 3);
    execute(&b).unwrap();
    execute(&ack(&b, st, 0)).unwrap();
    drive_hierarchy(st, 5, &chunks, &mut store);
    execute(&request(9, st, 5, &[])).unwrap();
    release(&b, st);
    assert_eq!(execute(&publication(st, 5)), Err(SourceError::InvalidFrame));
    close(st, 5);
    close(index, 2);
    execute(&ack(&b, st, 1)).unwrap();
    close(sc, 0);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}

#[test]
fn hierarchy_recovery_budget_and_forgery_preserve_state_query_and_history() {
    let _serial = test_processor_lock();
    let before = GeoProcessorLease::live_bytes();
    let chunks = vec![chunk(u64::MAX, -5, 0.)];
    let (index, sc, m, mut store, _) = selected_index(&chunks, &[u64::MAX]);
    let st = state(sc, &[u64::MAX]);
    let mut b = journal(selected_query(43, index, 3, &m, st), 1);
    p64(&mut b, 32, 8192);
    let held = GeoProcessorLease::live_bytes();
    assert_eq!(execute(&b), Err(SourceError::ResourceLimit));
    assert_eq!(GeoProcessorLease::live_bytes(), held);
    p64(&mut b, 32, 128 << 20);
    let receipt = execute(&b).unwrap();
    let mut changed = b.clone();
    changed[40] ^= 1; // whole budget grammar is part of identity.
    assert_eq!(execute(&changed), Err(SourceError::StaleSource));
    let mut wrong = ack(&b, st, 0);
    p64(&mut wrong, 24, 4);
    assert_eq!(execute(&wrong), Err(SourceError::StaleSource));
    assert_eq!(execute(&b).unwrap(), receipt);
    execute(&ack(&b, st, 0)).unwrap();
    drive_hierarchy(st, 3, &chunks, &mut store);
    let mut data = publication(st, 3);
    p64(&mut data, 32, 8192);
    let held = GeoProcessorLease::live_bytes();
    assert_eq!(execute(&data), Err(SourceError::ResourceLimit));
    assert_eq!(GeoProcessorLease::live_bytes(), held);
    assert_eq!(u32_at(&step(st, 3), 8), 19);
    p64(&mut data, 32, 128 << 20);
    execute(&data).unwrap();
    execute(&ack(&data, st, 0)).unwrap();
    release(&b, st);
    let mut changed = data.clone();
    changed[256] ^= 1;
    assert_eq!(execute(&changed), Err(SourceError::StaleSource));
    close(st, 0);
    release(&data, st);
    execute(&ack(&data, st, 1)).unwrap();
    close(index, 2);
    execute(&ack(&b, st, 1)).unwrap();
    close(sc, 0);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}

#[test]
fn hierarchy_recovery_newer_lane_operation_retires_old_birth_not_old_data() {
    let _serial = test_processor_lock();
    let before = GeoProcessorLease::live_bytes();
    let chunks = vec![chunk(u64::MAX, -5, 0.)];
    let (index, sc, m, mut store, _) = selected_index(&chunks, &[u64::MAX]);
    let first = state(sc, &[u64::MAX]);
    let b = journal(selected_query(43, index, 3, &m, first), 1);
    execute(&b).unwrap();
    execute(&ack(&b, first, 0)).unwrap();
    drive_hierarchy(first, 3, &chunks, &mut store);
    let second = state(sc, &[u64::MAX]);
    let next = journal(selected_query(43, index, 4, &m, second), 2);
    execute(&next).unwrap();
    execute(&ack(&next, second, 0)).unwrap();
    release(&b, first); // historical exact ACK, never replay a lower-nonce allocation.
    assert_eq!(execute(&b), Err(SourceError::StaleSource));
    assert!(execute(&publication(first, 3)).is_err());
    close(first, 3);
    drive_hierarchy(second, 4, &chunks, &mut store);
    let d = publication(second, 4);
    execute(&d).unwrap();
    execute(&ack(&d, second, 0)).unwrap();
    release(&next, second);
    close(index, 2);
    execute(&ack(&next, second, 1)).unwrap();
    assert_eq!(u64_at(&execute(&d).unwrap(), 16), second);
    close(second, 0);
    release(&d, second);
    execute(&ack(&d, second, 1)).unwrap();
    close(sc, 0);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}

#[test]
fn hierarchy_recovery_fallback_retires_consumed_query_without_restoring_state() {
    let _serial = test_processor_lock();
    let before = GeoProcessorLease::live_bytes();
    for frontier in [false, true] {
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
        let chunks = if frontier {
            vec![GeoChunk::encode(&c, None).unwrap()]
        } else {
            vec![chunk(u64::MAX, -5, 0.), chunk(7, -5, 0.0001)]
        };
        let (index, sc, m, mut store, _) = selected_index(&chunks, &[u64::MAX]);
        let st = state(sc, &[u64::MAX]);
        let mut b = journal(selected_query(43, index, 3, &m, st), 1);
        if !frontier {
            p64(&mut b, 40, 1);
        }
        execute(&b).unwrap();
        execute(&ack(&b, st, 0)).unwrap();
        let out = drive_hierarchy(st, 3, &chunks, &mut store);
        assert_eq!(u32_at(&out, 8), 10);
        assert_eq!(u32_at(&out, 48), if frontier { 1 } else { 2 });
        assert_eq!(u32_at(&execute(&b).unwrap(), 8), 22);
        assert_eq!(u64_at(&execute(&b).unwrap(), 16), 0);
        release(&b, st);
        assert!(execute(&publication(st, 3)).is_err());
        close(st, 3);
        let retry = state(sc, &[u64::MAX]);
        let mut next = journal(selected_query(43, index, 4, &m, retry), 2);
        p64(&mut next, 96, 8f64.to_bits());
        execute(&next).unwrap();
        execute(&ack(&next, retry, 0)).unwrap();
        assert_eq!(
            u32_at(&drive_hierarchy(retry, 4, &chunks, &mut store), 8),
            19
        );
        close(retry, 4);
        release(&next, retry);
        close(index, 2);
        execute(&ack(&next, retry, 1)).unwrap();
        close(sc, 0);
    }
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}

#[test]
fn hierarchy_recovery_sixteen_birth_cap_before_consumption_and_release_retry() {
    let _serial = test_processor_lock();
    let before = GeoProcessorLease::live_bytes();
    let chunks = vec![chunk(u64::MAX, -5, 0.)];
    let (index, sc, m, mut store, _) = selected_index(&chunks, &[u64::MAX]);
    let mut births = Vec::new();
    for n in 1..=16 {
        let st = state(sc, &[u64::MAX]);
        let b = journal(selected_query(43, index, n + 2, &m, st), n);
        execute(&b).unwrap();
        execute(&ack(&b, st, 0)).unwrap();
        close(st, n + 2);
        births.push((b, st));
    }
    let st = state(sc, &[u64::MAX]);
    let b = journal(selected_query(43, index, 19, &m, st), 17);
    let held = GeoProcessorLease::live_bytes();
    assert_eq!(execute(&b), Err(SourceError::ResourceLimit));
    assert_eq!(GeoProcessorLease::live_bytes(), held);
    // Release a historical retired stamp. Failure did not consume State or history.
    release(&births[0].0, births[0].1);
    execute(&b).unwrap();
    execute(&ack(&b, st, 0)).unwrap();
    drive_hierarchy(st, 19, &chunks, &mut store);
    // A44 stamp needs its own slot; admission cannot retire43 implicitly.
    let d = publication(st, 19);
    let held = GeoProcessorLease::live_bytes();
    assert_eq!(execute(&d), Err(SourceError::ResourceLimit));
    assert_eq!(GeoProcessorLease::live_bytes(), held);
    assert_eq!(u32_at(&step(st, 19), 8), 19);
    for (old, target) in births.iter().skip(1) {
        release(old, *target);
    }
    execute(&d).unwrap();
    execute(&ack(&d, st, 0)).unwrap();
    release(&b, st);
    close(st, 0);
    release(&d, st);
    execute(&ack(&d, st, 1)).unwrap();
    close(index, 2);
    execute(&ack(&b, st, 1)).unwrap();
    close(sc, 0);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
}
