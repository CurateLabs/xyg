//! Independent byte-level lifecycle proofs; no access to the protocol registry.
use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
use crate::geo_scale_protocol::{data_len, execute, read_data, HEADER};
use crate::geo_source::{GeoChunk, GeoIntervals, GeoSourceManifest, SourceError};
use crate::geo_source_session::test_processor_lock;
fn u32_at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}
fn u64_at(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}
fn p32(b: &mut [u8], at: usize, x: u32) {
    b[at..at + 4].copy_from_slice(&x.to_le_bytes());
}
fn p64(b: &mut [u8], at: usize, x: u64) {
    b[at..at + 8].copy_from_slice(&x.to_le_bytes());
}
fn request(command: u32, handle: u64, sequence: u64, payload: &[u8]) -> Vec<u8> {
    let mut b = vec![0; HEADER];
    b[..4].copy_from_slice(b"XYGQ");
    p32(&mut b, 4, 1);
    p32(&mut b, 8, command);
    p64(&mut b, 16, handle);
    p64(&mut b, 24, sequence);
    p64(&mut b, 232, payload.len() as u64);
    b.extend(payload);
    b
}
fn with_budget(mut b: Vec<u8>) -> Vec<u8> {
    p64(&mut b, 32, 128 << 20);
    p64(&mut b, 40, 1_000_000);
    p64(&mut b, 48, 128 << 20);
    p32(&mut b, 56, 65536);
    p32(&mut b, 60, 4096);
    b
}
struct Handle(u64);
impl Drop for Handle {
    fn drop(&mut self) {
        let _ = execute(&request(10, self.0, 0, &[]));
    }
}
fn builder() -> Handle {
    Handle(u64_at(&execute(&request(1, 0, 0, &[])).unwrap(), 16))
}
fn chunk(id: u64, start: i64, x: f64) -> Vec<u8> {
    let c = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::Point,
        crs: GeoCrs::Epsg4326,
        xy: &[x, 0.],
        validity: &[1],
        feature_ids: Some(&[id]),
        offsets0: &[],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    GeoChunk::encode(
        &c,
        Some(GeoIntervals {
            starts: &[start],
            ends: &[start + 10],
            start_validity: &[1],
            end_validity: &[1],
        }),
    )
    .unwrap()
}
fn finish_manifest(chunks: &[Vec<u8>]) -> (Handle, Vec<u8>) {
    let h = builder();
    for c in chunks {
        execute(&request(2, h.0, 0, c)).unwrap();
    }
    let mut b = request(3, h.0, 0, &[]);
    p64(&mut b, 144, u64::MAX);
    execute(&b).unwrap();
    let bytes = read_data(&request(21, h.0, 0, &[]), 128 << 20).unwrap();
    (h, bytes)
}
fn begin(
    h: u64,
    seq: u64,
    manifest: &GeoSourceManifest,
    instant: Option<i64>,
    work: u64,
) -> Vec<u8> {
    let mut b = with_budget(request(5, h, seq, &[]));
    p32(&mut b, 12, 1);
    p32(&mut b, 64, 4326);
    p32(&mut b, 72, 32768);
    p32(&mut b, 76, 1);
    for (at, v) in [
        (80, 0f64),
        (88, 0.),
        (96, 0.),
        (104, 800.),
        (112, 600.),
        (120, 0.),
        (128, 0.),
    ] {
        p64(&mut b, at, v.to_bits());
    }
    b[136..144].copy_from_slice(&manifest.digest());
    p64(&mut b, 144, manifest.generation());
    p64(&mut b, 152, u64::MAX);
    for at in [160, 168, 176, 184, 192] {
        p64(&mut b, at, seq);
    }
    if let Some(t) = instant {
        p32(&mut b, 200, 1);
        p64(&mut b, 208, t as u64);
    }
    p64(&mut b, 224, work);
    b
}
fn step(h: u64, seq: u64) -> [u8; HEADER] {
    execute(&request(6, h, seq, &[])).unwrap()
}
fn ticket(reply: &[u8]) -> Vec<u8> {
    reply[64..160].to_vec()
}
fn supply(h: u64, _seq: u64, t: &[u8], bytes: &[u8]) -> Result<[u8; HEADER], SourceError> {
    let mut p = t.to_vec();
    p.extend(bytes);
    execute(&request(7, h, 0, &p))
}
fn release(h: u64, _seq: u64, t: &[u8]) {
    execute(&request(8, h, 0, t)).unwrap();
}
fn drive(h: u64, seq: u64, chunks: &[Vec<u8>]) -> (u32, Vec<u32>) {
    let mut reads = Vec::new();
    loop {
        let s = step(h, seq);
        let code = u32_at(&s, 8);
        if code != 1 {
            return (code, reads);
        }
        let t = ticket(&s);
        let i = u32_at(&t, 40);
        reads.push(i);
        supply(h, seq, &t, &chunks[i as usize]).unwrap();
        assert_eq!(u32_at(&step(h, seq), 8), 2);
        release(h, seq, &t);
    }
}
fn scene_request(h: u64, seq: u64) -> Vec<u8> {
    let mut style = vec![0; 48];
    style[..4].copy_from_slice(&[255, 0, 0, 255]);
    p64(&mut style, 16, 6f64.to_bits());
    p64(&mut style, 24, 1f64.to_bits());
    with_budget(request(11, h, seq, &style))
}

use std::collections::BTreeMap;
fn close(handle: u64, seq: u64) {
    execute(&request(10, handle, seq, &[])).unwrap();
}
fn source_frame(chunks: &[Vec<u8>]) -> (u64, GeoSourceManifest) {
    let (manifest_handle, bytes) = finish_manifest(chunks);
    let manifest = GeoSourceManifest::validate(
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
    execute(&begin(source, 1, &manifest, None, 1000000)).unwrap();
    assert_eq!(drive(source, 1, chunks).0, 4);
    let frame = u64_at(&execute(&scene_request(source, 1)).unwrap(), 16);
    close(source, 0);
    drop(manifest_handle);
    (frame, manifest)
}
fn build(
    frame: u64,
    chunks: &[Vec<u8>],
    release_source: bool,
) -> (u64, BTreeMap<(u64, u64), Vec<u8>>) {
    let mut storage = BTreeMap::new();
    let handle = u64_at(
        &execute(&with_budget(request(
            27,
            frame,
            1,
            &1000000u64.to_le_bytes(),
        )))
        .unwrap(),
        16,
    );
    if release_source {
        close(frame, 0);
    }
    loop {
        let state = step(handle, 1);
        let code = u32_at(&state, 8);
        let t = &state[64..192];
        match code {
            1 => {
                let bytes = if u32_at(t, 32) == 1 {
                    &chunks[u32_at(t, 72) as usize]
                } else {
                    &storage[&(u64_at(t, 8), u64_at(t, 40))]
                };
                let mut payload = t.to_vec();
                payload.extend(bytes);
                execute(&request(7, handle, 1, &payload)).unwrap();
                execute(&request(8, handle, 1, t)).unwrap();
            }
            7 => {
                let q = request(30, handle, 1, t);
                let len = data_len(&q, 128 << 20).unwrap();
                assert_eq!(data_len(&q, 128 << 20).unwrap(), len);
                let bytes = read_data(&q, 128 << 20).unwrap();
                assert_eq!(bytes.len(), len);
                storage.insert((u64_at(t, 8), u64_at(t, 40)), bytes);
                execute(&request(31, handle, 1, t)).unwrap();
            }
            13 => return (handle, storage),
            _ => panic!("unexpected {code}"),
        }
    }
}
fn query_request(index: u64, manifest: &GeoSourceManifest, t: Option<i64>, seq: u64) -> Vec<u8> {
    let mut b = begin(index, seq, manifest, t, 0);
    p32(&mut b, 8, 28);
    p32(&mut b, 72, 0);
    p32(&mut b, 76, 0);
    b
}
fn finish_query(
    index: u64,
    manifest: &GeoSourceManifest,
    t: Option<i64>,
    seq: u64,
    storage: &BTreeMap<(u64, u64), Vec<u8>>,
) -> u64 {
    let handle = u64_at(
        &execute(&query_request(index, manifest, t, seq)).unwrap(),
        16,
    );
    loop {
        let state = step(handle, seq);
        match u32_at(&state, 8) {
            1 => {
                let ticket = &state[64..192];
                let mut payload = ticket.to_vec();
                payload.extend(&storage[&(u64_at(ticket, 8), u64_at(ticket, 40))]);
                execute(&request(7, handle, seq, &payload)).unwrap();
                execute(&request(8, handle, seq, ticket)).unwrap();
            }
            14 => return handle,
            _ => panic!("unexpected query state"),
        }
    }
}

fn overview_data() -> u64 {
    let chunks = [
        chunk(u64::MAX, -5, -179.),
        chunk(1 << 63, 0, 179.),
        chunk(7, 10, 0.),
    ];
    let (frame, manifest) = source_frame(&chunks);
    let (index, storage) = build(frame, &chunks, true);
    let query = finish_query(index, &manifest, Some(0), 7, &storage);
    let data = u64_at(
        &execute(&with_budget(request(29, query, 7, &[]))).unwrap(),
        16,
    );
    close(query, 7);
    close(index, 1);
    data
}
fn snapshot_request(command: u32, handle: u64, sequence: u64, budget: usize) -> [u8; 256] {
    let mut b = [0; 256];
    b[..4].copy_from_slice(b"XYGJ");
    p32(&mut b, 4, 1);
    p32(&mut b, 8, command);
    p64(&mut b, 16, handle);
    p64(&mut b, 24, sequence);
    p64(&mut b, 32, budget as u64);
    b
}
#[test]
fn overview_painter_snapshot_private_ownership_quota_and_atomic_admission() {
    let _cpu = test_processor_lock();
    let _derived = crate::geo_tile_cache::test_process_lock();
    let data = overview_data();
    let transport = crate::geo_transport::GeoTransportLease::acquire().unwrap();
    assert_eq!(
        transport
            .with_phase(128 << 20, |phase| {
                crate::geo_retained_painter::prepare_frame_painter(data, 6, phase)
            })
            .unwrap()
            .err(),
        Some(SourceError::StaleSource)
    );
    assert_eq!(
        transport
            .with_phase(4096, |phase| {
                crate::geo_retained_painter::prepare_frame_painter(data, 7, phase)
            })
            .unwrap()
            .err(),
        Some(SourceError::ResourceLimit)
    );
    let painter = transport
        .with_phase(128 << 20, |phase| {
            crate::geo_retained_painter::prepare_frame_painter(data, 7, phase)
        })
        .unwrap()
        .unwrap();
    assert_eq!(&painter.bytes[..4], b"XYPB");
    let original = read_data(&request(23, data, 7, &[]), 128 << 20).unwrap();
    let document = crate::scene::SceneDocument::decode(&original[2304..]).unwrap();
    assert_eq!(
        document.to_browser_painter(128 << 20).unwrap(),
        painter.bytes
    );
    let worst = crate::geo_retained_painter::overview_persistent_bytes(
        original.len() - 2304,
        2 * (original.len() - 2304) + 65536,
        crate::geo_temporal_overview_scene::MAX_RECORDS,
        256,
    )
    .unwrap();
    assert!(worst <= crate::geo_temporal_overview_scene::DATA_CREDIT);
    let freeze = snapshot_request(6, data, 7, 128 << 20);
    let mut bad = freeze;
    p64(&mut bad, 24, 6);
    assert_eq!(
        crate::geo_snapshot_protocol::execute(&bad),
        Err(crate::geo_snapshot::GeoSnapshotError::Stale)
    );
    let low = snapshot_request(6, data, 7, 4096);
    assert_eq!(
        crate::geo_snapshot_protocol::execute(&low),
        Err(crate::geo_snapshot::GeoSnapshotError::Limit)
    );
    // The point-only freezer may never silently discard the overview sidecar.
    assert!(
        crate::geo_snapshot_protocol::execute(&snapshot_request(1, data, 7, 128 << 20)).is_err()
    );
    let reply = crate::geo_snapshot_protocol::execute(&freeze).unwrap();
    let frozen = u64_at(&reply, 16);
    let duplicate = u64_at(
        &execute(&with_budget(request(26, data, 7, &[]))).unwrap(),
        16,
    );
    close(data, 0);
    let copied = read_data(&request(23, duplicate, 7, &[]), 128 << 20).unwrap();
    assert_eq!(&copied[24..], &original[24..]);
    assert_eq!(
        transport
            .with_phase(128 << 20, |phase| {
                crate::geo_retained_painter::prepare_frame_painter(duplicate, 7, phase)
            })
            .unwrap()
            .unwrap()
            .bytes,
        painter.bytes
    );
    close(duplicate, 0);
    let read = snapshot_request(20, frozen, 0, 0);
    let bytes = crate::geo_snapshot_protocol::read_data(&read, 128 << 20).unwrap();
    assert_eq!(u32_at(&bytes, 4), 4);
    assert_eq!(&bytes[288..292], b"XYOF");
    let cache = crate::geo_tile_cache::GeoTileCache::new(
        crate::geo_tile_cache::GeoTileLimits::default(),
        0,
    )
    .unwrap();
    let decoded =
        crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &bytes, 128 << 20).unwrap();
    assert_eq!(decoded.overview().unwrap().counts.iter().sum::<u64>(), 2);
    assert_eq!(decoded.overview().unwrap().counts[128], 1);
    assert_eq!(decoded.overview().unwrap().counts[143], 1);
    assert_eq!(
        decoded.identity().time,
        crate::geo_source::TimePredicate::Instant(0)
    );
    assert_eq!(decoded.identity().layers[0].layer_id, u64::MAX);
    assert!(decoded.grids().is_empty() && decoded.selections().is_empty());
    assert_eq!(decoded.scene(), &original[2304..]);
    for offset in [
        192, 196, 200, 288, 292, 296, 300, 304, 312, 316, 328, 336, 344, 352, 360, 368, 376, 384,
        432,
    ] {
        let mut corrupt = bytes.clone();
        corrupt[offset] ^= 1;
        assert!(
            crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &corrupt, 128 << 20).is_err(),
            "offset {offset}"
        );
    }
    // Zero source rows cannot produce vertices, even for MultiPoint. Keep the
    // unchanged, matching count Scene to isolate source consistency.
    let mut zero_rows = bytes.clone();
    p64(&mut zero_rows, 208 + 56, 0);
    p32(&mut zero_rows, 208 + 64, 4);
    p64(&mut zero_rows, 288 + 56, 0);
    p32(&mut zero_rows, 288 + 68, 4);
    assert!(matches!(
        crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &zero_rows, 128 << 20),
        Err(crate::geo_snapshot::GeoSnapshotError::Invalid)
    ));
    let mut oversize = bytes.clone();
    p64(
        &mut oversize,
        24,
        crate::geo_temporal_overview_scene::MAX_ENCODED_SCENE_BYTES as u64 + 1,
    );
    assert!(matches!(
        crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &oversize, 128 << 20),
        Err(crate::geo_snapshot::GeoSnapshotError::Limit)
    ));
    let retained_credit = cache.stats().derived_reserved_bytes;
    let mut trailing = bytes.clone();
    trailing.extend_from_slice(&[0; 1024]);
    let trailing_len = trailing.len() as u64;
    p64(&mut trailing, 16, trailing_len);
    assert!(matches!(
        crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &trailing, 128 << 20),
        Err(crate::geo_snapshot::GeoSnapshotError::Invalid)
    ));
    assert_eq!(cache.stats().derived_reserved_bytes, retained_credit);
    // Paint mismatches fail even if modified metadata is structurally plausible.
    let mut corrupt = bytes.clone();
    corrupt[384 + 128 * 8..392 + 128 * 8].copy_from_slice(&0u64.to_le_bytes());
    assert!(crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &corrupt, 128 << 20).is_err());
    assert_eq!(
        crate::geo_snapshot_protocol::read_data(&read, 128 << 20).unwrap(),
        bytes
    );
    assert!(crate::geo_snapshot_protocol::read_data(&read, 128 << 20).is_err());
    crate::geo_snapshot_protocol::execute(&snapshot_request(3, frozen, 0, 0)).unwrap();
}
#[test]
fn overview_painter_profile_worstcase_fits_persistent_credit() {
    assert!(
        crate::geo_retained_painter::overview_persistent_bytes(
            crate::geo_temporal_overview_scene::MAX_ENCODED_SCENE_BYTES,
            2 * crate::geo_temporal_overview_scene::MAX_ENCODED_SCENE_BYTES + 65536,
            crate::geo_temporal_overview_scene::MAX_RECORDS,
            256
        )
        .unwrap()
            <= crate::geo_temporal_overview_scene::DATA_CREDIT
    );
    let mut counts = [1; 256];
    counts[128] = 2;
    for (bearing, pitch, wrap) in [
        (0., 0., true),
        (45., 60., true),
        (45., -60., true),
        (120., 60., false),
    ] {
        let camera = crate::geo_viewport::GeoViewport {
            crs: GeoCrs::Epsg4326,
            center_x: 0.,
            center_y: 0.,
            zoom: 0.,
            width: 800.,
            height: 600.,
            bearing_deg: bearing,
            pitch_deg: pitch,
            world_wrap: wrap,
        };
        let scene = crate::geo_temporal_overview_scene::compile_counts(&counts, camera).unwrap();
        let doc = crate::scene::SceneDocument::decode(&scene).unwrap();
        let painter = doc.to_browser_painter(128 << 20).unwrap();
        assert!(painter.len() <= 2 * scene.len() + 65536);
        assert!(
            crate::geo_retained_painter::overview_persistent_bytes(
                scene.len(),
                2 * scene.len() + 65536,
                crate::geo_temporal_overview_scene::MAX_RECORDS,
                256
            )
            .unwrap()
                <= crate::geo_temporal_overview_scene::DATA_CREDIT
        );
    }
}

#[test]
fn overview_painter_duplicate_uses_shared_eight_data_cap_without_consuming_owner() {
    let _cpu = test_processor_lock();
    let _derived = crate::geo_tile_cache::test_process_lock();
    let data = overview_data();
    let duplicate_request = with_budget(request(26, data, 7, &[]));
    let mut copies = Vec::new();
    for _ in 0..7 {
        copies.push(u64_at(&execute(&duplicate_request).unwrap(), 16));
    }
    assert_eq!(execute(&duplicate_request), Err(SourceError::ResourceLimit));
    let before = read_data(&request(23, data, 7, &[]), 128 << 20).unwrap();
    close(copies.pop().unwrap(), 0);
    let copy = u64_at(&execute(&duplicate_request).unwrap(), 16);
    assert_eq!(
        &read_data(&request(23, copy, 7, &[]), 128 << 20).unwrap()[24..],
        &before[24..]
    );
    close(copy, 0);
    for copy in copies {
        close(copy, 0);
    }
    close(data, 0);
}
