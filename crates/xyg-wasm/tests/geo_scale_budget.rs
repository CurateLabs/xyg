//! Exclusive-process proof of the actual shared WASM instance quota.
//! This maximum-budget test cannot compete with parallel lib-test instances.
#![cfg(not(target_arch = "wasm32"))]
use xyg_wasm::{
    xyg_wasm_arena_ptr, xyg_wasm_arena_resize, xyg_wasm_geo_scale_read, xyg_wasm_instance_dispose,
    xyg_wasm_instance_new, xyg_wasm_output_len, xyg_wasm_output_ptr, STATUS_OK,
    STATUS_RESOURCE_LIMIT, STATUS_STALE_SEQUENCE,
};
fn stage_scale(handle: u32, request: &[u8]) {
    assert_eq!(xyg_wasm_arena_resize(handle, request.len()), STATUS_OK);
    unsafe {
        std::ptr::copy_nonoverlapping(
            request.as_ptr(),
            xyg_wasm_arena_ptr(handle) as *mut u8,
            request.len(),
        );
    }
}
fn output(handle: u32) -> Vec<u8> {
    let length = xyg_wasm_output_len(handle);
    assert!(length > 0);
    unsafe { std::slice::from_raw_parts(xyg_wasm_output_ptr(handle) as *const u8, length).to_vec() }
}
#[test]
fn full_instance_budget_and_retained_read_ownership_are_bounded() {
    use xyg_engine::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
    use xyg_engine::geo_source::{GeoChunk, GeoManifestBuilder, MAX_CHUNK_PEAK};
    fn req(command: u32, handle: u64, sequence: u64, payload: &[u8]) -> Vec<u8> {
        let mut b = vec![0; 256];
        b[..4].copy_from_slice(b"XYGQ");
        b[4..8].copy_from_slice(&1u32.to_le_bytes());
        b[8..12].copy_from_slice(&command.to_le_bytes());
        for (at, n) in [
            (16, handle),
            (24, sequence),
            (32, 128 << 20),
            (40, 1_000_000),
            (48, 128 << 20),
            (232, payload.len() as u64),
        ] {
            b[at..at + 8].copy_from_slice(&n.to_le_bytes());
        }
        b[56..60].copy_from_slice(&65536u32.to_le_bytes());
        b[60..64].copy_from_slice(&4096u32.to_le_bytes());
        b.extend(payload);
        b
    }
    let column = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::Point,
        crs: GeoCrs::Epsg4326,
        xy: &[0., 0.],
        validity: &[1],
        feature_ids: Some(&[u64::MAX]),
        offsets0: &[],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let bytes = GeoChunk::encode(&column, None).unwrap();
    let mut builder = GeoManifestBuilder::new();
    builder
        .push(&GeoChunk::parse(&bytes, MAX_CHUNK_PEAK).unwrap())
        .unwrap();
    let manifest = builder.finish(1).unwrap();
    let out = xyg_engine::geo_scale_protocol::execute(&req(4, 0, 0, &manifest.encode().unwrap()))
        .unwrap();
    let session = u64::from_le_bytes(out[16..24].try_into().unwrap());
    fn drive(session: u64, sequence: u64, bytes: &[u8]) {
        loop {
            let out =
                xyg_engine::geo_scale_protocol::execute(&req(6, session, sequence, &[])).unwrap();
            if u32::from_le_bytes(out[8..12].try_into().unwrap()) != 1 {
                break;
            }
            let ticket = &out[64..160];
            let mut supply = ticket.to_vec();
            supply.extend(bytes);
            xyg_engine::geo_scale_protocol::execute(&req(7, session, 0, &supply)).unwrap();
            xyg_engine::geo_scale_protocol::execute(&req(8, session, 0, ticket)).unwrap();
        }
    }
    drive(session, 0, &bytes);
    let mut begin = req(5, session, 1, &[]);
    begin[12..16].copy_from_slice(&1u32.to_le_bytes());
    for (at, n) in [(64, 4326u32), (72, 32768), (76, 1)] {
        begin[at..at + 4].copy_from_slice(&n.to_le_bytes());
    }
    for (at, n) in [(104, 800f64), (112, 600.)] {
        begin[at..at + 8].copy_from_slice(&n.to_le_bytes());
    }
    begin[136..144].copy_from_slice(&manifest.digest());
    for (at, n) in [
        (144, 1u64),
        (152, u64::MAX),
        (160, 1),
        (168, 1),
        (176, 1),
        (184, 1),
        (192, 1),
        (224, 100),
    ] {
        begin[at..at + 8].copy_from_slice(&n.to_le_bytes());
    }
    xyg_engine::geo_scale_protocol::execute(&begin).unwrap();
    drive(session, 1, &bytes);
    let mut style = vec![0; 48];
    style[..4].copy_from_slice(&[255, 0, 0, 255]);
    style[16..24].copy_from_slice(&6f64.to_le_bytes());
    style[24..32].copy_from_slice(&1f64.to_le_bytes());
    let out = xyg_engine::geo_scale_protocol::execute(&req(11, session, 1, &style)).unwrap();
    let data = u64::from_le_bytes(out[16..24].try_into().unwrap());
    let read = req(23, data, 0, &[]);
    // C length queries and undersized copies must not consume either data
    // ownership transfer. The same registry then serves both WASM copies.
    let mut required = 0usize;
    for _ in 0..3 {
        unsafe {
            assert_eq!(
                xyg_core::xyg_geo_scale_read(
                    read.as_ptr(),
                    read.len(),
                    128 << 20,
                    std::ptr::null_mut(),
                    0,
                    &mut required
                ),
                0
            );
        }
    }
    let mut undersized = [91u8; 1];
    let mut untouched = 999usize;
    unsafe {
        assert_eq!(
            xyg_core::xyg_geo_scale_read(
                read.as_ptr(),
                read.len(),
                128 << 20,
                undersized.as_mut_ptr(),
                1,
                &mut untouched
            ),
            -13
        );
    }
    assert!(required > 256);
    assert_eq!(untouched, 999);
    assert_eq!(undersized, [91]);
    let h = xyg_wasm_instance_new(384 << 20);
    assert_ne!(h, 0);
    assert_eq!(xyg_wasm_instance_new(1), 0); // Exact shared384MiB ceiling.
    let mut first = Vec::new();
    for sequence in [1, 2] {
        stage_scale(h, &read);
        assert_eq!(
            xyg_wasm_geo_scale_read(h, sequence, 0, read.len()),
            STATUS_OK
        );
        let accepted = output(h);
        if sequence == 1 {
            first = accepted;
        } else {
            assert_eq!(accepted, first);
        }
    }
    assert_eq!(xyg_wasm_instance_new(1), 0); // Success restores the full declared budget.
    let previous = output(h);
    assert!(previous.len() > 256);
    // A rejected old call does not need new staging and must preserve the
    // accepted observable WASM output at the public call boundary.
    assert_eq!(
        xyg_wasm_geo_scale_read(h, 2, 0, read.len()),
        STATUS_STALE_SEQUENCE
    );
    assert_eq!(output(h), previous);
    // Public arena-resize releases prior WASM output. The host retains its
    // accepted CPU copy while staging the third ownership read.
    stage_scale(h, &read);
    assert_eq!(
        xyg_wasm_geo_scale_read(h, 3, 0, read.len()),
        STATUS_RESOURCE_LIMIT
    );
    assert_eq!(xyg_wasm_output_len(h), 0);
    assert_eq!(xyg_wasm_instance_new(1), 0); // Failure also restores that budget.
    assert_eq!(previous, first);
    // Immutable admitted SceneData remains the trusted paint authority after
    // its mutable source is disposed. Painting borrows it, consuming no read.
    xyg_engine::geo_scale_protocol::execute(&req(10, session, 0, &[])).unwrap();
    assert_eq!(
        xyg_wasm::xyg_wasm_geo_frame_prepare(h, 10, data, 1),
        STATUS_OK
    );
    let painter = output(h);
    assert_eq!(&painter[..4], b"XYPB");
    assert_eq!(
        xyg_wasm::xyg_wasm_geo_frame_prepare(h, 11, data, 2),
        STATUS_STALE_SEQUENCE
    );
    xyg_engine::geo_scale_protocol::execute(&req(10, data, 0, &[])).unwrap();
    assert_eq!(xyg_wasm_instance_dispose(h), STATUS_OK);
    let recovered = xyg_wasm_instance_new(384 << 20);
    assert_ne!(recovered, 0);
    assert_eq!(xyg_wasm_instance_dispose(recovered), STATUS_OK);
}
