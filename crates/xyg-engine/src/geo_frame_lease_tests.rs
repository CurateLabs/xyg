//! Independent trusted SceneData duplication and resource-lifetime proofs.
use super::*;

#[test]
fn retained_direct_and_reduced_frames_keep_trusted_authority_and_independent_copy_quota() {
    let _source = test_processor_lock();
    let _tile = test_process_lock();
    for vertices in [1, 9000] {
        let fixture = fixture_with_vertices(None, vertices);
        let original = Handle(n64(&execute(&style(fixture.source.0)).unwrap(), 16));
        let packet = read_data(&request(23, original.0, 0, &[]), 128 << 20).unwrap();
        let cpu = crate::geo_source_session::GeoProcessorLease::live_bytes();
        let duplicate = execute(&budget(request(26, original.0, 1, &[]), 4096)).unwrap();
        let retained = Handle(n64(&duplicate, 16));
        assert_ne!(retained.0, original.0);
        assert_eq!(n64(&duplicate, 40), original.0);
        // Immutable source/result authority is shared under its existing lease.
        assert_eq!(
            crate::geo_source_session::GeoProcessorLease::live_bytes(),
            cpu
        );
        let read = request(23, retained.0, 0, &[]);
        let mut expected = packet.clone();
        p64(&mut expected, 16, original.0);
        drop(original);
        drop(fixture.source);
        assert_eq!(read_data(&read, 128 << 20).unwrap(), expected);
        assert_eq!(read_data(&read, 128 << 20).unwrap(), expected);
        assert_eq!(read_data(&read, 128 << 20), Err(SourceError::ResourceLimit));
        // Full-source rows survive original source+frame disposal.
        let rows = Handle(n64(
            &execute(&budget(request(15, retained.0, 1, &[]), 4096)).unwrap(),
            16,
        ));
        drive(rows.0, 1, &fixture.chunks);
        let rows_data = Handle(n64(
            &execute(&budget(request(16, rows.0, 1, &[]), 4096)).unwrap(),
            16,
        ));
        let rows_packet = read_data(&request(23, rows_data.0, 0, &[]), 128 << 20).unwrap();
        assert_eq!(n64(&rows_packet, 32), 8);
        assert_eq!(n64(&rows_packet, 256), u64::MAX);
        let mut pick = style(0)[256..].to_vec();
        pick.resize(80, 0);
        p64(&mut pick, 48, 400f64.to_bits());
        p64(&mut pick, 56, 300f64.to_bits());
        p32(&mut pick, 76, 1);
        let hit = Handle(n64(
            &execute(&budget(request(14, retained.0, 1, &pick), 4096)).unwrap(),
            16,
        ));
        let hit_packet = read_data(&request(23, hit.0, 0, &[]), 128 << 20).unwrap();
        assert_eq!(n64(&hit_packet, 32), 1);
        if vertices == 1 {
            assert_eq!(n64(&hit_packet, 256 + 8), 1 << 63);
        } else {
            let mut membership = vec![0; 16];
            p32(&mut membership, 0, n32(&hit_packet, 256 + 32));
            p64(&mut membership, 8, 200_000);
            let member = Handle(n64(
                &execute(&budget(request(12, retained.0, 1, &membership), 4096)).unwrap(),
                16,
            ));
            drive(member.0, 1, &fixture.chunks);
            let page = Handle(n64(&execute(&prepare(member.0)).unwrap(), 16));
            let members = read_data(&request(23, page.0, 0, &[]), 128 << 20).unwrap();
            assert_eq!(n64(&members, 32), 8); // Original rows, not 72000 vertices.
            assert_eq!(n64(&members, 256), u64::MAX);
        }
        // Painter/export helpers borrow this same immutable semantic authority.
        crate::geo_scale_protocol::with_scene_data(retained.0, 1, |view| {
            assert_eq!(view.result.key.identity.layer_id, u64::MAX);
            assert_eq!(
                view.scene,
                &expected[256..256 + n64(&expected, 32) as usize]
            );
        })
        .unwrap();
    }
}

#[test]
fn duplicate_rejects_forgery_stale_and_pressure_then_drains_without_losing_old_frame() {
    let _source = test_processor_lock();
    let _tile = test_process_lock();
    let fixture = fixture_with_vertices(None, 2);
    let original = Handle(n64(&execute(&style(fixture.source.0)).unwrap(), 16));
    assert_eq!(
        execute(&budget(request(26, fixture.source.0, 1, &[]), 4096)),
        Err(SourceError::InvalidFrame)
    );
    assert_eq!(
        execute(&budget(request(26, original.0, 2, &[]), 4096)),
        Err(SourceError::StaleSource)
    );
    assert_eq!(
        execute(&budget(request(26, original.0, 1, &[0]), 4096)),
        Err(SourceError::InvalidFrame)
    );
    let mut small = budget(request(26, original.0, 1, &[]), 4096);
    p64(&mut small, 32, 256);
    assert_eq!(execute(&small), Err(SourceError::ResourceLimit));
    let cpu = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let mut retained = Vec::new();
    for _ in 0..7 {
        retained.push(Handle(n64(
            &execute(&budget(request(26, original.0, 1, &[]), 4096)).unwrap(),
            16,
        )));
    }
    assert_eq!(
        execute(&budget(request(26, original.0, 1, &[]), 4096)),
        Err(SourceError::ResourceLimit)
    );
    retained.clear();
    for _ in 0..100 {
        let owned = Handle(n64(
            &execute(&budget(request(26, original.0, 1, &[]), 4096)).unwrap(),
            16,
        ));
        drop(owned);
    }
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        cpu
    );
    assert!(data_len(&request(23, original.0, 0, &[]), 128 << 20).unwrap() > 256);
}
