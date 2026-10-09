//! Hierarchy protocol proofs through public typed bytes, not private registry mutation.
use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
use crate::geo_scale_protocol::{HEADER, data_len, execute, read_data};
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
fn build_request(frame: u64, cap: u64) -> Vec<u8> {
    let mut p = vec![0; 24];
    p32(&mut p, 0, 1024);
    p64(&mut p, 8, 1000000);
    p64(&mut p, 16, cap);
    with_budget(request(37, frame, 1, &p))
}
fn drive_hierarchy(
    h: u64,
    seq: u64,
    chunks: &[Vec<u8>],
    store: &mut BTreeMap<(u64, u64), Vec<u8>>,
) -> [u8; HEADER] {
    loop {
        let s = step(h, seq);
        let t = &s[64..192];
        match u32_at(&s, 8) {
            1 => {
                let bytes = if u32_at(t, 32) == 1 {
                    &chunks[u32_at(t, 72) as usize]
                } else {
                    &store[&(u64_at(t, 8), u64_at(t, 40))]
                };
                let mut p = t.to_vec();
                p.extend(bytes);
                execute(&request(7, h, seq, &p)).unwrap();
                execute(&request(8, h, seq, t)).unwrap();
            }
            7 => {
                let q = request(40, h, seq, t);
                let n = data_len(&q, 128 << 20).unwrap();
                let b = read_data(&q, 128 << 20).unwrap();
                assert_eq!(n, b.len());
                store.insert((u64_at(t, 8), u64_at(t, 40)), b);
                execute(&request(41, h, seq, t)).unwrap();
            }
            _ => return s,
        }
    }
}
fn query(index: u64, seq: u64, m: &GeoSourceManifest, t: Option<i64>) -> Vec<u8> {
    let mut b = begin(index, seq, m, t, 1000000);
    p32(&mut b, 8, 38);
    p64(&mut b, 96, 8f64.to_bits());
    b
}
fn data(h: u64, seq: u64) -> u64 {
    let mut q = scene_request(h, seq);
    p32(&mut q, 8, 39);
    u64_at(&execute(&q).unwrap(), 16)
}
#[test]
fn hierarchy_protocol_exact_time_scene_and_disposal_independent_rows_authority() {
    let _serial = test_processor_lock();
    let chunks = vec![chunk(u64::MAX, -5, 0.), chunk(1 << 63, 100, 0.0001)];
    let (frame, m) = source_frame(&chunks);
    let old = read_data(&request(23, frame, 0, &[]), 128 << 20).unwrap();
    let h = u64_at(&execute(&build_request(frame, 64 << 20)).unwrap(), 16);
    close(frame, 0);
    let mut store = BTreeMap::new();
    let ready = drive_hierarchy(h, 1, &chunks, &mut store);
    assert_eq!(u32_at(&ready, 8), 18);
    assert_ne!(u64_at(&ready, 48), 0);
    let q = u64_at(&execute(&query(h, 2, &m, Some(0))).unwrap(), 16);
    let done = drive_hierarchy(q, 2, &chunks, &mut store);
    assert_eq!(u32_at(&done, 8), 19);
    assert!(u64_at(&done, 184) > 0);
    let d = data(q, 2);
    let b = read_data(&request(23, d, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64_at(&b, 48), 1);
    let scene_len = u64_at(&b, 32) as usize;
    assert_eq!(u64_at(&b, HEADER + scene_len), u64::MAX);
    let camera = crate::geo_viewport::GeoViewport::new(
        crate::geo::GeoCrs::Epsg4326,
        0.,
        0.,
        8.,
        800.,
        600.,
        0.,
        0.,
        true,
    )
    .unwrap();
    let reference = crate::geo_lod::process(
        &m,
        &mut |r: crate::geo_source::ReadRequest| Ok(chunks[r.chunk_index as usize].clone()),
        camera,
        crate::geo_source::TimePredicate::Instant(0),
        u64::MAX,
        2,
        2,
        crate::geo_lod::GeoLodOptions {
            kind: crate::geo_lod::GeoReducedKind::Cluster,
            previous_direct: true,
            max_cells: 32768,
            processor_bytes: 128 << 20,
            max_projected_vertices: 1000000,
        },
        crate::geo_source::QueryBudget::default(),
        &mut || false,
    )
    .unwrap();
    let style_bytes = scene_request(q, 2);
    let style = super::read_uniform_style(&style_bytes[HEADER..]).unwrap();
    let expected = crate::geo_lod_scene::compile(&reference, style, 128 << 20).unwrap();
    assert_eq!(&b[HEADER..HEADER + scene_len], expected.scene.as_slice());

    close(h, 1);
    close(q, 2);
    let retained = execute(&with_budget(request(26, d, 2, &[]))).unwrap();
    let copy = u64_at(&retained, 16);
    let bytes = read_data(&request(23, copy, 0, &[]), 128 << 20).unwrap();
    assert_eq!(&b[24..], &bytes[24..]);
    assert!(!old.is_empty());
    // Rows uses the same immutable semantic source even after hierarchy/query disposal.
    let rr = execute(&with_budget(request(15, d, 2, &[]))).unwrap();
    let rows = u64_at(&rr, 16);
    assert_eq!(drive(rows, 2, &chunks).0, 4);
    close(rows, 0);
    close(d, 0);
    close(copy, 0);
}
#[test]
fn hierarchy_protocol_cancelled_write_exact_ticket_copy_quota_and_old_frame() {
    let _serial = test_processor_lock();
    let chunks = vec![chunk(u64::MAX, 0, 0.)];
    let (frame, _) = source_frame(&chunks);
    let h = u64_at(&execute(&build_request(frame, 64 << 20)).unwrap(), 16);
    let read = step(h, 1);
    let t = &read[64..192];
    let mut p = t.to_vec();
    p.extend(&chunks[0]);
    execute(&request(7, h, 1, &p)).unwrap();
    execute(&request(8, h, 1, t)).unwrap();
    let w = step(h, 1);
    assert_eq!(u32_at(&w, 8), 7);
    let t = &w[64..192];
    let q = request(40, h, 1, t);
    for _ in 0..4 {
        assert!(data_len(&q, 128 << 20).unwrap() > 0)
    }
    read_data(&q, 128 << 20).unwrap();
    read_data(&q, 128 << 20).unwrap();
    assert_eq!(
        read_data(&q, 128 << 20).unwrap_err(),
        SourceError::ResourceLimit
    );
    execute(&request(9, h, 1, &[])).unwrap();
    assert_eq!(u32_at(&execute(&request(10, h, 1, &[])).unwrap(), 8), 2);
    let mut forged = t.to_vec();
    forged[8] ^= 1;
    assert_eq!(
        execute(&request(41, h, 1, &forged)).unwrap_err(),
        SourceError::StaleSource
    );
    execute(&request(41, h, 1, t)).unwrap();
    close(h, 1);
    assert!(
        !read_data(&request(23, frame, 0, &[]), 128 << 20)
            .unwrap()
            .is_empty()
    );
    close(frame, 0);
}
#[test]
fn hierarchy_protocol_snapshot_style_and_corrupt_leaf_preserve_old_data() {
    let _serial = test_processor_lock();
    let chunks = vec![chunk(u64::MAX, 0, 0.)];
    let (frame, m) = source_frame(&chunks);
    let h = u64_at(&execute(&build_request(frame, 64 << 20)).unwrap(), 16);
    let mut store = BTreeMap::new();
    assert_eq!(u32_at(&drive_hierarchy(h, 1, &chunks, &mut store), 8), 18);
    let q = u64_at(&execute(&query(h, 2, &m, None)).unwrap(), 16);
    assert_eq!(u32_at(&drive_hierarchy(q, 2, &chunks, &mut store), 8), 19);
    let old = data(q, 2);
    assert_eq!(
        execute(&query(h, 2, &m, None)).unwrap_err(),
        SourceError::StaleSource
    );
    let mut bad = query(h, 3, &m, None);
    p64(&mut bad, 160, 2);
    p64(&mut bad, 80, 1f64.to_bits());
    assert_eq!(execute(&bad).unwrap_err(), SourceError::StaleSource);
    let q2 = u64_at(&execute(&query(h, 3, &m, None)).unwrap(), 16);
    let s = step(q2, 3);
    let t = &s[64..192];
    let mut bytes = store[&(u64_at(t, 8), u64_at(t, 40))].clone();
    let last = bytes.len() - 1;
    bytes[last] ^= 1;
    let mut p = t.to_vec();
    p.extend(bytes);
    assert!(execute(&request(7, q2, 3, &p)).is_err());
    execute(&request(8, q2, 3, t)).unwrap();
    close(q2, 3);
    close(q, 2);
    close(h, 1);
    assert!(
        !read_data(&request(23, old, 0, &[]), 128 << 20)
            .unwrap()
            .is_empty()
    );
    close(old, 0);
    close(frame, 0);
}
#[test]
fn hierarchy_protocol_shared_eight_sessions_sixteen_handles_and_write_cap_fail_closed() {
    let _serial = test_processor_lock();
    let chunks = vec![chunk(u64::MAX, 0, 0.)];
    let (frame, _) = source_frame(&chunks);
    let (manifest, bytes) = finish_manifest(&chunks);
    let mut sessions = Vec::new();
    for _ in 0..7 {
        sessions.push(u64_at(
            &execute(&with_budget(request(4, 0, 0, &bytes))).unwrap(),
            16,
        ));
    }
    drop(manifest);
    let h = u64_at(&execute(&build_request(frame, 64 << 20)).unwrap(), 16);
    assert_eq!(
        execute(&build_request(frame, 64 << 20)).unwrap_err(),
        SourceError::ResourceLimit
    );
    assert_eq!(
        execute(&with_budget(request(4, 0, 0, &bytes))).unwrap_err(),
        SourceError::ResourceLimit
    );
    close(h, 1);
    for h in sessions {
        close(h, 0)
    }
    let mut copies = Vec::new();
    for _ in 0..7 {
        copies.push(u64_at(
            &execute(&with_budget(request(26, frame, 1, &[]))).unwrap(),
            16,
        ));
    }
    let mut scopes = Vec::new();
    for namespace in 1..=8 {
        let mut p = [0; 16];
        p64(&mut p, 0, namespace);
        p64(&mut p, 8, u64::MAX);
        scopes.push(u64_at(
            &execute(&with_budget(request(32, frame, 1, &p))).unwrap(),
            16,
        ));
    }
    assert_eq!(
        execute(&build_request(frame, 64 << 20)).unwrap_err(),
        SourceError::ResourceLimit
    );
    for h in scopes {
        close(h, 0)
    }
    for h in copies {
        close(h, 0)
    }
    let h = u64_at(&execute(&build_request(frame, 1)).unwrap(), 16);
    let s = step(h, 1);
    let t = &s[64..192];
    let mut p = t.to_vec();
    p.extend(&chunks[0]);
    execute(&request(7, h, 1, &p)).unwrap();
    execute(&request(8, h, 1, t)).unwrap();
    assert_eq!(
        execute(&request(6, h, 1, &[])).unwrap_err(),
        SourceError::ResourceLimit
    );
    assert_eq!(u32_at(&execute(&request(6, h, 1, &[])).unwrap(), 8), 9);
    close(h, 1);
    assert!(
        !read_data(&request(23, frame, 0, &[]), 128 << 20)
            .unwrap()
            .is_empty()
    );
    close(frame, 0);
}
#[test]
fn hierarchy_protocol_eight_data_handles_and_style_failure_preserve_old_authority() {
    let _serial = test_processor_lock();
    let chunks = vec![chunk(u64::MAX, 0, 0.)];
    let (frame, m) = source_frame(&chunks);
    let h = u64_at(&execute(&build_request(frame, 64 << 20)).unwrap(), 16);
    let mut store = BTreeMap::new();
    drive_hierarchy(h, 1, &chunks, &mut store);
    let q = u64_at(&execute(&query(h, 2, &m, None)).unwrap(), 16);
    drive_hierarchy(q, 2, &chunks, &mut store);
    let mut ds = Vec::new();
    for _ in 0..7 {
        ds.push(data(q, 2))
    }
    let mut dq = scene_request(q, 2);
    p32(&mut dq, 8, 39);
    assert_eq!(execute(&dq).unwrap_err(), SourceError::ResourceLimit);
    for d in ds {
        close(d, 0)
    }
    let old = data(q, 2);
    let mut changed = dq.clone();
    changed[HEADER] = 0;
    assert_eq!(execute(&changed).unwrap_err(), SourceError::StaleSource);
    close(q, 2);
    close(h, 1);
    assert!(
        !read_data(&request(23, old, 0, &[]), 128 << 20)
            .unwrap()
            .is_empty()
    );
    close(old, 0);
    close(frame, 0);
}
#[test]
fn hierarchy_protocol_selected_source_explicitly_unsupported_without_admission() {
    let _serial = test_processor_lock();
    let chunks = vec![chunk(u64::MAX, 0, 0.)];
    let (mh, bytes) = finish_manifest(&chunks);
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
    assert_eq!(drive(source, 0, &chunks).0, 3);
    execute(&begin(source, 1, &m, None, 1000000)).unwrap();
    assert_eq!(drive(source, 1, &chunks).0, 4);
    let frame = u64_at(&execute(&scene_request(source, 1)).unwrap(), 16);
    let mut p = [0; 16];
    p64(&mut p, 0, 777);
    p64(&mut p, 8, u64::MAX);
    let scope = u64_at(
        &execute(&with_budget(request(32, frame, 1, &p))).unwrap(),
        16,
    );
    let mut p = vec![0; 32];
    p64(&mut p, 0, 2);
    p[8..12].copy_from_slice(&[0, 255, 0, 255]);
    p64(&mut p, 16, 1);
    p64(&mut p, 24, u64::MAX);
    let state = u64_at(
        &execute(&with_budget(request(33, scope, 0, &p))).unwrap(),
        16,
    );
    let mut b = begin(source, 2, &m, None, 1000000);
    p32(&mut b, 8, 35);
    for at in [160, 168, 176, 184] {
        p64(&mut b, at, 1)
    }
    p64(&mut b, 232, 8);
    b.extend(state.to_le_bytes());
    execute(&b).unwrap();
    assert_eq!(drive(source, 2, &chunks).0, 4);
    let selected = u64_at(&execute(&scene_request(source, 2)).unwrap(), 16);
    let before = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let mut b = build_request(selected, 64 << 20);
    p64(&mut b, 24, 2);
    let rejected = execute(&b).unwrap();
    assert_eq!(u32_at(&rejected, 8), 17);
    assert_eq!(u64_at(&rejected, 16), selected);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        before
    );
    assert!(rejected[32..].iter().all(|v| *v == 0));
    assert!(
        !read_data(&request(23, selected, 0, &[]), 128 << 20)
            .unwrap()
            .is_empty()
    );
    close(source, 0);
    close(selected, 0);
    close(scope, 0);
    close(frame, 0);
    drop(mh);
}
#[test]
fn hierarchy_protocol_frontier_fallback_never_publishes_partial_data() {
    let _serial = test_processor_lock();
    let xy: Vec<_> = (0..17)
        .flat_map(|x| (0..17).flat_map(move |y| [-160. + x as f64 * 20., -64. + y as f64 * 8.]))
        .collect();
    let ids: Vec<_> = (0..289).map(|i| u64::MAX - i).collect();
    let validity = vec![1; 289];
    let c = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::Point,
        crs: GeoCrs::Epsg4326,
        xy: &xy,
        validity: &validity,
        feature_ids: Some(&ids),
        offsets0: &[],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let chunks = vec![GeoChunk::encode(&c, None).unwrap()];
    let (frame, m) = source_frame(&chunks);
    let h = u64_at(&execute(&build_request(frame, 64 << 20)).unwrap(), 16);
    let mut store = BTreeMap::new();
    drive_hierarchy(h, 1, &chunks, &mut store);
    let mut req = query(h, 2, &m, None);
    p64(&mut req, 96, 0f64.to_bits());
    let q = u64_at(&execute(&req).unwrap(), 16);
    loop {
        let s = step(q, 2);
        match u32_at(&s, 8) {
            1 => {
                let t = &s[64..192];
                let bytes = &store[&(u64_at(t, 8), u64_at(t, 40))];
                assert_ne!(&bytes[..4], b"XYHL");
                let mut p = t.to_vec();
                p.extend(bytes);
                execute(&request(7, q, 2, &p)).unwrap();
                execute(&request(8, q, 2, t)).unwrap();
            }
            10 => {
                assert_eq!(u32_at(&s, 48), 1);
                break;
            }
            code => panic!("unexpected{code}"),
        }
    }
    let mut dq = scene_request(q, 2);
    p32(&mut dq, 8, 39);
    assert!(execute(&dq).is_err());
    close(q, 2);
    close(h, 1);
    assert!(
        !read_data(&request(23, frame, 0, &[]), 128 << 20)
            .unwrap()
            .is_empty()
    );
    close(frame, 0);
}
#[test]
fn hierarchy_protocol_multipoint_empty_null_duplicate_ids_and_original_vertex_ordinals() {
    let _serial = test_processor_lock();
    let c = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::MultiPoint,
        crs: GeoCrs::Epsg4326,
        xy: &[0., 0., 0.0001, 0., 0.0002, 0., 0.0003, 0.],
        validity: &[1, 1, 0, 1],
        feature_ids: Some(&[u64::MAX, 7, 8, u64::MAX]),
        offsets0: &[0, 2, 2, 2, 4],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let chunks = vec![GeoChunk::encode(&c, None).unwrap()];
    let (frame, m) = source_frame(&chunks);
    let h = u64_at(&execute(&build_request(frame, 64 << 20)).unwrap(), 16);
    let mut store = BTreeMap::new();
    drive_hierarchy(h, 1, &chunks, &mut store);
    let q = u64_at(&execute(&query(h, 2, &m, None)).unwrap(), 16);
    assert_eq!(u32_at(&drive_hierarchy(q, 2, &chunks, &mut store), 8), 19);
    let d = data(q, 2);
    let b = read_data(&request(23, d, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64_at(&b, 48), 4);
    let at = HEADER + u64_at(&b, 32) as usize;
    for (i, row) in [0, 0, 3, 3].into_iter().enumerate() {
        assert_eq!(u64_at(&b, at + i * 40), u64::MAX);
        assert_eq!(u64_at(&b, at + i * 40 + 8), row);
        assert_eq!(u32_at(&b, at + i * 40 + 24), i as u32);
    }
    close(q, 2);
    close(h, 1);
    close(d, 0);
    close(frame, 0);
}
#[test]
fn hierarchy_protocol_vertex_work_fallback_is_distinct_and_no_scene_can_publish() {
    let _serial = test_processor_lock();
    let chunks = vec![chunk(u64::MAX, 0, 0.), chunk(1 << 63, 0, 0.0001)];
    let (frame, m) = source_frame(&chunks);
    let before = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let h = u64_at(&execute(&build_request(frame, 64 << 20)).unwrap(), 16);
    let mut store = BTreeMap::new();
    drive_hierarchy(h, 1, &chunks, &mut store);
    let mut req = query(h, 2, &m, None);
    p64(&mut req, 40, 1);
    let q = u64_at(&execute(&req).unwrap(), 16);
    let s = drive_hierarchy(q, 2, &chunks, &mut store);
    assert_eq!(u32_at(&s, 8), 10);
    assert_eq!(u32_at(&s, 48), 2);
    let mut dq = scene_request(q, 2);
    p32(&mut dq, 8, 39);
    assert!(execute(&dq).is_err());
    close(q, 2);
    assert_eq!(
        execute(&query(h, 2, &m, None)).unwrap_err(),
        SourceError::StaleSource
    );
    let mut bad = query(h, 3, &m, None);
    p64(&mut bad, 160, 2);
    p64(&mut bad, 80, 1f64.to_bits());
    assert_eq!(execute(&bad).unwrap_err(), SourceError::StaleSource);
    let q = u64_at(&execute(&query(h, 3, &m, None)).unwrap(), 16);
    assert_eq!(u32_at(&drive_hierarchy(q, 3, &chunks, &mut store), 8), 19);
    close(q, 3);
    close(h, 1);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        before
    );
    assert!(
        !read_data(&request(23, frame, 0, &[]), 128 << 20)
            .unwrap()
            .is_empty()
    );
    close(frame, 0);
}
#[test]
fn hierarchy_protocol_local_control_budget_exact_boundary_and_one_byte_under() {
    let _serial = test_processor_lock();
    let chunks = vec![chunk(u64::MAX, 0, 0.)];
    let (frame, m) = source_frame(&chunks);
    let core = crate::geo_spatial_hierarchy_build::GeoHierarchyBuildSession::new(
        &m,
        crate::geo_spatial_hierarchy::GeoHierarchyOptions { grid: 1024 },
        crate::geo_source::QueryBudget::default(),
        1000000,
        64 << 20,
    )
    .unwrap();
    let boundary = core.reserved_bytes() + 4096;
    drop(core);
    let before = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let mut b = build_request(frame, 64 << 20);
    p64(&mut b, 32, (boundary - 1) as u64);
    assert_eq!(execute(&b).unwrap_err(), SourceError::ResourceLimit);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        before
    );
    p64(&mut b, 32, boundary as u64);
    let temporary = u64_at(&execute(&b).unwrap(), 16);
    close(temporary, 1);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        before
    );
    let h = u64_at(&execute(&build_request(frame, 64 << 20)).unwrap(), 16);
    let mut store = BTreeMap::new();
    drive_hierarchy(h, 1, &chunks, &mut store);
    let baseline = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let mut seq = 1u64;
    // Discover the public query admission boundary without access to private root metadata.
    let mut low = 0usize;
    let mut high = 128 << 20;
    while low < high {
        let mid = (low + high) / 2;
        seq += 1;
        let mut req = query(h, seq, &m, None);
        p64(&mut req, 32, mid as u64);
        match execute(&req) {
            Ok(r) => {
                close(u64_at(&r, 16), seq);
                high = mid;
            }
            Err(SourceError::ResourceLimit) => low = mid + 1,
            Err(e) => panic!("unexpected{e:?}"),
        }
        assert_eq!(
            crate::geo_source_session::GeoProcessorLease::live_bytes(),
            baseline
        );
    }
    seq += 1;
    let mut req = query(h, seq, &m, None);
    p64(&mut req, 32, (low - 1) as u64);
    assert_eq!(execute(&req).unwrap_err(), SourceError::ResourceLimit);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        baseline
    );
    p64(&mut req, 32, low as u64);
    let temporary = u64_at(&execute(&req).unwrap(), 16);
    close(temporary, seq);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        baseline
    );
    // Publishing Data accounts retained root/control/result and new semantic/Scene scratch.
    seq += 1;
    let q = u64_at(&execute(&query(h, seq, &m, None)).unwrap(), 16);
    drive_hierarchy(q, seq, &chunks, &mut store);
    let before_data = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let mut low = 0usize;
    let mut high = 128 << 20;
    while low < high {
        let mid = (low + high) / 2;
        let mut req = scene_request(q, seq);
        p32(&mut req, 8, 39);
        p64(&mut req, 32, mid as u64);
        match execute(&req) {
            Ok(r) => {
                close(u64_at(&r, 16), 0);
                high = mid;
            }
            Err(SourceError::ResourceLimit) => low = mid + 1,
            Err(e) => panic!("unexpected{e:?}"),
        }
        assert_eq!(
            crate::geo_source_session::GeoProcessorLease::live_bytes(),
            before_data
        );
    }
    let mut req = scene_request(q, seq);
    p32(&mut req, 8, 39);
    p64(&mut req, 32, (low - 1) as u64);
    assert_eq!(execute(&req).unwrap_err(), SourceError::ResourceLimit);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        before_data
    );
    p64(&mut req, 32, low as u64);
    let d = u64_at(&execute(&req).unwrap(), 16);
    close(d, 0);
    close(q, seq);
    close(h, 1);
    close(frame, 0);
}
