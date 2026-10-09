//! Raw public execute proofs; no private registry/receipt access.
use super::*;
fn nonce(mut b: Vec<u8>, n: u64) -> Vec<u8> {
    p64(&mut b, 240, n);
    b
}
fn ack(b: &[u8], target: u64, action: u32) -> Vec<u8> {
    let mut payload = [0; 16];
    p32(&mut payload, 0, u32_at(b, 8));
    p32(&mut payload, 4, action);
    p64(&mut payload, 8, target);
    nonce(
        request(47, u64_at(b, 16), u64_at(b, 24), &payload),
        u64_at(b, 240),
    )
}
fn confirm(b: &[u8], h: u64) {
    assert_eq!(u32_at(&execute(&ack(b, h, 0)).unwrap(), 8), 0);
}
fn forget(b: &[u8], h: u64) {
    assert_eq!(u32_at(&execute(&ack(b, h, 1)).unwrap(), 8), 0);
}
fn built(h: u64, chunks: &[Vec<u8>]) -> BTreeMap<(u64, u64), Vec<u8>> {
    let mut storage = BTreeMap::new();
    loop {
        let s = step(h, 1);
        let t = &s[64..192];
        match u32_at(&s, 8) {
            1 => {
                let bytes = if u32_at(t, 32) == 1 {
                    &chunks[u32_at(t, 72) as usize]
                } else {
                    &storage[&(u64_at(t, 8), u64_at(t, 40))]
                };
                let mut p = t.to_vec();
                p.extend(bytes);
                execute(&request(7, h, 1, &p)).unwrap();
                execute(&request(8, h, 1, t)).unwrap();
            }
            7 => {
                let bytes = read_data(&request(30, h, 1, t), 128 << 20).unwrap();
                storage.insert((u64_at(t, 8), u64_at(t, 40)), bytes);
                execute(&request(31, h, 1, t)).unwrap();
            }
            13 => return storage,
            _ => panic!("unexpected"),
        }
    }
}
fn query_done(h: u64, seq: u64, storage: &BTreeMap<(u64, u64), Vec<u8>>) {
    loop {
        let s = step(h, seq);
        match u32_at(&s, 8) {
            1 => {
                let t = &s[64..192];
                let mut p = t.to_vec();
                p.extend(&storage[&(u64_at(t, 8), u64_at(t, 40))]);
                execute(&request(7, h, seq, &p)).unwrap();
                execute(&request(8, h, seq, t)).unwrap();
            }
            14 => return,
            _ => panic!("unexpected"),
        }
    }
}
#[test]
fn recovery_five_live_retains_confirm_exact_ack_replay_and_parent_disposal() {
    let _lock = test_processor_lock();
    let chunks = [chunk(u64::MAX, 0, 0.)];
    let (frame, _) = source_frame(&chunks);
    let mut targets = Vec::new();
    let mut last = Vec::new();
    for n in 1..=5 {
        let b = nonce(with_budget(request(26, frame, 1, &[])), n);
        let out = execute(&b).unwrap();
        let h = u64_at(&out, 16);
        assert_eq!(execute(&b).unwrap(), out);
        confirm(&b, h);
        assert_eq!(execute(&ack(&b, h, 0)).unwrap(), reply_bytes(h, 1));
        targets.push((b.clone(), h));
        last = b;
    }
    let mut changed = last.clone();
    p64(&mut changed, 40, 999);
    assert_eq!(execute(&changed), Err(SourceError::StaleSource));
    close(frame, 0);
    let out = execute(&last).unwrap();
    assert_eq!(u64_at(&out, 16), targets[4].1);
    confirm(&last, targets[4].1);
    close(targets[4].1, 0);
    assert_eq!(u32_at(&execute(&last).unwrap(), 8), 22);
    assert_eq!(
        u32_at(&execute(&ack(&last, targets[4].1, 0)).unwrap(), 8),
        22
    );
    forget(&last, targets[4].1);
    forget(&last, targets[4].1);
    assert_eq!(execute(&last), Err(SourceError::StaleSource));
    for (b, h) in targets[..4].iter() {
        close(*h, 0);
        execute(&ack(b, *h, 2)).unwrap();
    }
}
fn reply_bytes(h: u64, s: u64) -> [u8; HEADER] {
    let mut b = [0; HEADER];
    b[..4].copy_from_slice(b"XYGZ");
    p32(&mut b, 4, 1);
    p64(&mut b, 16, h);
    p64(&mut b, 24, s);
    b
}
#[test]
fn recovery_unconfirmed_blocks_higher_nonce_and_invalid_ack_preserves_receipt() {
    let _lock = test_processor_lock();
    let (frame, _) = source_frame(&[chunk(1, 0, 0.)]);
    let b = nonce(with_budget(request(26, frame, 1, &[])), 1);
    let out = execute(&b).unwrap();
    let h = u64_at(&out, 16);
    assert_eq!(execute(&nonce(b.clone(), 2)), Err(SourceError::StaleSource));
    let mut bad = ack(&b, h, 0);
    p64(&mut bad, 264, h + 1);
    assert_eq!(execute(&bad), Err(SourceError::StaleSource));
    close(frame, 0);
    assert_eq!(execute(&b).unwrap(), out);
    confirm(&b, h);
    forget(&b, h);
    close(h, 0);
}
#[test]
fn recovery_five_indices_and_full_sixteen_handle_same_query_data_publication() {
    let _lock = test_processor_lock();
    let chunks = [chunk(u64::MAX, 0, 0.)];
    let (frame, manifest) = source_frame(&chunks);
    let mut indices = Vec::new();
    let mut lastbuild = Vec::new();
    let mut accepted = Vec::new();
    for n in 1..=5 {
        let b = nonce(
            with_budget(request(27, frame, 1, &1_000_000u64.to_le_bytes())),
            n,
        );
        let h = u64_at(&execute(&b).unwrap(), 16);
        confirm(&b, h);
        let pages = built(h, &chunks);
        let q = finish_query(h, &manifest, None, 2, &pages);
        let d = u64_at(&execute(&with_budget(request(29, q, 2, &[]))).unwrap(), 16);
        close(q, 2);
        indices.push((h, pages, b.clone()));
        accepted.push(d);
        lastbuild = b;
    }
    let mut queries = Vec::new();
    for (i, (index, pages, _)) in indices.iter().enumerate() {
        let b = nonce(query_request(*index, &manifest, None, 3 + i as u64), 1);
        let h = u64_at(&execute(&b).unwrap(), 16);
        confirm(&b, h);
        query_done(h, 3 + i as u64, pages);
        queries.push((h, b));
    }
    // 5 indices +5 old Data +seed +5 completedQueries =16; no17th allocation.
    for (i, (q, b)) in queries.iter().enumerate() {
        let publish = nonce(with_budget(request(29, *q, 3 + i as u64, &[])), 1);
        let mut low = publish.clone();
        p64(&mut low, 32, 8192);
        assert_eq!(execute(&low), Err(SourceError::ResourceLimit));
        assert_eq!(u32_at(&step(*q, 3 + i as u64), 8), 14);
        let out = execute(&publish).unwrap();
        assert_eq!(u64_at(&out, 16), *q);
        assert_eq!(execute(&publish).unwrap(), out);
        assert_eq!(u32_at(&execute(b).unwrap(), 8), 22);
        confirm(&publish, *q);
        forget(&publish, *q);
        close(accepted[i], 0);
    }
    close(frame, 0);
    forget(&lastbuild, indices[4].0);
    for (i, (h, _, birth)) in indices.iter().enumerate() {
        close(*h, 1);
        execute(&ack(birth, *h, 2)).unwrap();
        let (_, b) = &queries[i];
        assert_eq!(u32_at(&execute(&ack(b, queries[i].0, 0)).unwrap(), 8), 22);
        forget(b, queries[i].0);
        close(queries[i].0, 0);
    }
}
#[test]
fn recovery_bank_saturation_no_mutation_and_forget_drop_recovery() {
    let _lock = test_processor_lock();
    let (mut frame, _) = source_frame(&[chunk(1, 0, 0.)]);
    let mut receipts = Vec::new();
    for _ in 0..16 {
        let b = nonce(with_budget(request(26, frame, 1, &[])), 1);
        let next = u64_at(&execute(&b).unwrap(), 16);
        confirm(&b, next);
        close(frame, 0);
        receipts.push((b, next));
        frame = next;
    }
    let b = nonce(with_budget(request(26, frame, 1, &[])), 1);
    assert_eq!(execute(&b), Err(SourceError::ResourceLimit));
    assert!(data_len(&request(23, frame, 0, &[]), 128 << 20).unwrap() > 0);
    for (b, h) in receipts {
        forget(&b, h);
    }
    let next = u64_at(&execute(&b).unwrap(), 16);
    confirm(&b, next);
    close(frame, 0);
    forget(&b, next);
    close(next, 0);
}

#[test]
fn recovery_domain_allocation_private_resume_retired_consumption_and_issuer_disposal() {
    let _lock = test_processor_lock();
    let chunks = [chunk(u64::MAX, 0, 0.)];
    let (frame, manifest) = source_frame(&chunks);
    let (index, storage) = build(frame, &chunks, true);
    let q = finish_query(index, &manifest, None, 2, &storage);
    let data = u64_at(&execute(&with_budget(request(29, q, 2, &[]))).unwrap(), 16);
    close(q, 2);
    close(index, 1);
    let mut p = [0; 24];
    p64(&mut p, 0, 10);
    p32(&mut p, 8, 136);
    p64(&mut p, 16, 1000);
    let b = nonce(with_budget(request(45, data, 2, &p)), 1);
    let out = execute(&b).unwrap();
    let h = u64_at(&out, 16);
    assert_eq!(execute(&b).unwrap(), out);
    close(data, 0);
    assert_eq!(execute(&b).unwrap(), out);
    let mut a = ack(&b, h, 0);
    p64(&mut a, 24, 10);
    assert_eq!(u32_at(&execute(&a).unwrap(), 8), 0);
    assert_eq!(execute(&a).unwrap(), reply_bytes(h, 10));
    loop {
        let s = step(h, 10);
        match u32_at(&s, 8) {
            1 => {
                let t = &s[64..192];
                let mut p = t.to_vec();
                p.extend(&chunks[u32_at(t, 40) as usize]);
                execute(&request(7, h, 10, &p)).unwrap();
                execute(&request(8, h, 10, t)).unwrap();
            }
            21 => break,
            _ => panic!("unexpected"),
        }
    }
    let pubreq = with_budget(request(46, h, 10, &[]));
    let publication = execute(&pubreq).unwrap();
    assert_eq!(u64_at(&publication, 16), h);
    assert_eq!(u32_at(&execute(&b).unwrap(), 8), 22);
    assert_eq!(u32_at(&execute(&a).unwrap(), 8), 22);
    let bytes = read_data(&request(23, h, 10, &[]), 128 << 20).unwrap();
    assert_eq!(&bytes[..4], b"XYOM");
    assert_eq!(u64_at(&bytes, 256), u64::MAX);
    assert_eq!(u64_at(&bytes, 280), 1);
    close(h, 0);
    p32(&mut a, 260, 1);
    execute(&a).unwrap();
    assert_eq!(execute(&b), Err(SourceError::StaleSource));
}

#[test]
fn recovery_lost_original_retired_zero_confirmation_releases_no_guessed_owner() {
    let _lock = test_processor_lock();
    let (frame, _) = source_frame(&[chunk(1, 0, 0.)]);
    let b = nonce(with_budget(request(26, frame, 1, &[])), 1);
    let actual = execute(&b).unwrap();
    let h = u64_at(&actual, 16);
    // Harness sees the engine's target to model external retirement. Client lost it.
    assert_eq!(execute(&ack(&b, 0, 0)), Err(SourceError::StaleSource));
    close(h, 0);
    assert_eq!(u32_at(&execute(&b).unwrap(), 8), 22);
    let mut wrong = ack(&b, 0, 0);
    p64(&mut wrong, 24, 2);
    assert_eq!(execute(&wrong), Err(SourceError::StaleSource));
    assert_eq!(u32_at(&execute(&ack(&b, 0, 0)).unwrap(), 8), 22);
    execute(&ack(&b, 0, 2)).unwrap();
    let next = nonce(b.clone(), 2);
    let nh = u64_at(&execute(&next).unwrap(), 16);
    confirm(&next, nh);
    close(frame, 0);
    forget(&next, nh);
    close(nh, 0);
    assert_eq!(execute(&ack(&b, 0, 0)), Err(SourceError::StaleSource));
    let (parent, _) = source_frame(&[chunk(2, 0, 0.)]);
    let b = nonce(with_budget(request(26, parent, 1, &[])), 1);
    let h = u64_at(&execute(&b).unwrap(), 16);
    close(parent, 0);
    close(h, 0);
    assert_eq!(u32_at(&execute(&b).unwrap(), 8), 22);
    execute(&ack(&b, 0, 0)).unwrap();
    forget(&b, 0);
    forget(&b, 0);
    assert_eq!(execute(&b), Err(SourceError::StaleSource));
}

#[test]
fn recovery_historical_retirement_confirm_release_preserves_newer_owner() {
    let _lock = test_processor_lock();
    let (parent, _) = source_frame(&[chunk(1, 0, 0.)]);
    let old = nonce(with_budget(request(26, parent, 1, &[])), 1);
    let target = u64_at(&execute(&old).unwrap(), 16);
    confirm(&old, target);
    let next = nonce(old.clone(), 2);
    let newer = u64_at(&execute(&next).unwrap(), 16);
    confirm(&next, newer);
    assert_eq!(
        execute(&ack(&old, target, 2)),
        Err(SourceError::StaleSource)
    );
    // The client loses the successful10 reply. Historical Confirm is not replay
    // of the now stale allocation and cannot revive or dispose the newer Data.
    close(target, 0);
    assert_eq!(execute(&old), Err(SourceError::StaleSource));
    let retired = execute(&ack(&old, target, 0)).unwrap();
    assert_eq!(u32_at(&retired, 8), 22);
    assert_eq!(u64_at(&retired, 16), 0);
    assert_eq!(execute(&ack(&old, target, 0)).unwrap(), retired);
    let mut forged = ack(&old, target, 0);
    p64(&mut forged, 24, 2);
    assert_eq!(execute(&forged), Err(SourceError::StaleSource));
    assert_eq!(execute(&ack(&old, newer, 0)), Err(SourceError::StaleSource));
    let release = ack(&old, target, 2);
    assert_eq!(execute(&release).unwrap(), reply_bytes(0, 1));
    assert_eq!(execute(&release).unwrap(), reply_bytes(0, 1));
    assert_eq!(
        execute(&ack(&old, target, 0)),
        Err(SourceError::StaleSource)
    );
    assert_eq!(u64_at(&execute(&next).unwrap(), 16), newer);
    assert!(data_len(&request(23, newer, 0, &[]), 128 << 20).unwrap() > 0);
    close(newer, 0);
    execute(&ack(&next, newer, 2)).unwrap();
    // Birth release preserves the issuer's nonce highwater and exact retirement.
    assert_eq!(u32_at(&execute(&next).unwrap(), 8), 22);
    assert_eq!(execute(&old), Err(SourceError::StaleSource));
    close(parent, 0);
    forget(&next, newer);
}

#[test]
fn recovery_historical_stamp_capacity_precedes_mutation_and_releases_exactly() {
    let _lock = test_processor_lock();
    let (parent, _) = source_frame(&[chunk(1, 0, 0.)]);
    let mut births = Vec::new();
    for n in 1..=16 {
        let b = nonce(with_budget(request(26, parent, 1, &[])), n);
        let target = u64_at(&execute(&b).unwrap(), 16);
        confirm(&b, target);
        close(target, 0);
        births.push((b, target));
    }
    let next = nonce(with_budget(request(26, parent, 1, &[])), 17);
    assert_eq!(execute(&next), Err(SourceError::ResourceLimit));
    assert!(data_len(&request(23, parent, 0, &[]), 128 << 20).unwrap() > 0);
    let (first, target) = &births[0];
    assert_eq!(u32_at(&execute(&ack(first, *target, 0)).unwrap(), 8), 22);
    execute(&ack(first, *target, 2)).unwrap();
    let live = u64_at(&execute(&next).unwrap(), 16);
    confirm(&next, live);
    for (b, target) in births.iter().skip(1) {
        execute(&ack(b, *target, 2)).unwrap();
    }
    close(live, 0);
    execute(&ack(&next, live, 2)).unwrap();
    close(parent, 0);
    forget(&next, live);
}
