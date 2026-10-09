//! Independent actual typed lifecycle and issued-cursor continuation proofs.
use super::*;

#[test]
fn original_rows_page_after_source_and_scene_disposal_with_private_continuation() {
    let _source = test_processor_lock();
    let _tile = test_process_lock();
    let fixture = fixture_with_vertices(Some(0), 2);
    let prepared = execute(&style(fixture.source.0)).unwrap();
    let scene = Handle(n64(&prepared, 16));
    let mut rows = Handle(n64(
        &execute(&budget(request(15, scene.0, 1, &[]), 3)).unwrap(),
        16,
    ));
    // An owned page session carries validated source/time/state authority.
    drop(fixture.source);
    drop(scene);
    let mut original = Vec::new();
    let mut eligible = Vec::new();
    let mut counts = Vec::new();
    loop {
        drive(rows.0, 1, &fixture.chunks);
        let out = execute(&budget(request(16, rows.0, 1, &[]), 3)).unwrap();
        let data = Handle(n64(&out, 16));
        drop(rows);
        let req = request(23, data.0, 0, &[]);
        let packet = read_data(&req, 128 << 20).unwrap();
        assert_eq!(n32(&packet, 8), 4);
        assert_eq!(n64(&packet, 96), u64::MAX);
        assert_eq!(n64(&packet, 104), 8);
        assert_eq!(n64(&packet, 120), u64::MAX);
        assert_eq!(n64(&packet, 128), 1);
        assert_eq!(n64(&packet, 136), 1);
        assert_eq!(n64(&packet, 144), 1);
        assert_eq!(n32(&packet, 152), 1);
        assert_eq!(n64(&packet, 160), 0);
        let count = n64(&packet, 32) as usize;
        assert_eq!(packet.len(), 256 + 64 * count);
        counts.push(count);
        for i in 0..count {
            let at = 256 + i * 64;
            original.push((n64(&packet, at), n64(&packet, at + 8)));
            let flags = n32(&packet, at + 24);
            eligible.push(flags & 4 != 0);
            assert_eq!(flags & 1, 0);
            assert_ne!(flags & 8, 0);
            assert_eq!(packet[at + 28..at + 32], [0; 4]);
            assert_eq!(packet[at + 56..at + 64], [0; 8]);
        }
        // Size discovery is pure; only two actual Data copies are authorized.
        assert_eq!(data_len(&req, 128 << 20).unwrap(), packet.len());
        assert_eq!(read_data(&req, 128 << 20).unwrap(), packet);
        assert_eq!(read_data(&req, 128 << 20), Err(SourceError::ResourceLimit));
        if n32(&packet, 40) == 0 {
            assert_eq!(
                execute(&budget(request(15, data.0, 1, &[]), 3)),
                Err(SourceError::InvalidFrame)
            );
            break;
        }
        // Raw host ordinals/bytes cannot manufacture a continuation capability.
        assert_eq!(
            execute(&budget(request(15, data.0, 1, &[0; 16]), 3)),
            Err(SourceError::InvalidFrame)
        );
        assert_eq!(
            execute(&budget(request(15, data.0, 2, &[]), 3)),
            Err(SourceError::StaleSource)
        );
        rows = Handle(n64(
            &execute(&budget(request(15, data.0, 1, &[]), 3)).unwrap(),
            16,
        ));
        drop(data);
    }
    assert_eq!(counts, [3, 3, 2]);
    assert_eq!(
        original,
        (0..8)
            .map(|row| ([u64::MAX, 7, 7, 1 << 63][row % 4], row as u64))
            .collect::<Vec<_>>()
    );
    assert_eq!(
        eligible,
        [true, true, true, true, false, false, false, false]
    );
}

#[test]
fn malformed_budget_and_cancelled_read_reject_without_panics_or_releasing_host_storage() {
    let _source = test_processor_lock();
    let _tile = test_process_lock();
    let fixture = fixture_with_vertices(None, 2);
    let scene = Handle(n64(&execute(&style(fixture.source.0)).unwrap(), 16));
    let rows = Handle(n64(
        &execute(&budget(request(15, scene.0, 1, &[]), 3)).unwrap(),
        16,
    ));
    drive(rows.0, 1, &fixture.chunks);
    let before = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let malformed = std::panic::catch_unwind(|| execute(&request(16, rows.0, 1, &[])));
    assert!(malformed.is_ok());
    assert!(malformed.unwrap().is_err());
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        before
    );
    let data = Handle(n64(
        &execute(&budget(request(16, rows.0, 1, &[]), 3)).unwrap(),
        16,
    ));
    let pending = Handle(n64(
        &execute(&budget(request(15, data.0, 1, &[]), 3)).unwrap(),
        16,
    ));
    let out = execute(&request(6, pending.0, 1, &[])).unwrap();
    assert_eq!(n32(&out, 8), 1);
    let ticket = &out[64..160];
    execute(&request(9, pending.0, 1, &[])).unwrap();
    assert_eq!(
        n32(&execute(&request(10, pending.0, 0, &[])).unwrap(), 8),
        2
    );
    assert_eq!(
        execute(&request(7, pending.0, 0, ticket)),
        Err(SourceError::StaleSource)
    );
    execute(&request(8, pending.0, 0, ticket)).unwrap();
    assert_eq!(
        execute(&request(8, pending.0, 0, ticket)),
        Err(SourceError::StaleSource)
    );
    // An old immutable page still grants its exact issued continuation.
    let recovery = Handle(n64(
        &execute(&budget(request(15, data.0, 1, &[]), 3)).unwrap(),
        16,
    ));
    drive(recovery.0, 1, &fixture.chunks);
    let restored = Handle(n64(
        &execute(&budget(request(16, recovery.0, 1, &[]), 3)).unwrap(),
        16,
    ));
    let page = read_data(&request(23, restored.0, 0, &[]), 128 << 20).unwrap();
    assert_eq!(n64(&page, 256 + 8), 3);
}
