//! Independent byte-level lifecycle proofs; no access to the protocol registry.
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
fn overview_data(chunks: &[Vec<u8>], time: Option<i64>) -> u64 {
    let (frame, manifest) = source_frame(chunks);
    let (index, storage) = build(frame, chunks, true);
    let query = finish_query(index, &manifest, time, 7, &storage);
    let data = u64_at(
        &execute(&with_budget(request(29, query, 7, &[]))).unwrap(),
        16,
    );
    close(query, 7);
    close(index, 1);
    data
}
fn member_request(data: u64, issuer: u64, seq: u64, cell: u32, rows: u32) -> Vec<u8> {
    let mut p = [0; 24];
    p64(&mut p, 0, seq);
    p32(&mut p, 8, cell);
    p64(&mut p, 16, 1_000_000);
    let mut b = with_budget(request(45, data, issuer, &p));
    p32(&mut b, 60, rows);
    b
}
fn members_drive(query: u64, seq: u64, chunks: &[Vec<u8>]) -> [u8; HEADER] {
    loop {
        let s = step(query, seq);
        match u32_at(&s, 8) {
            1 => {
                let t = &s[64..192];
                let mut p = t.to_vec();
                p.extend(&chunks[u32_at(t, 40) as usize]);
                execute(&request(7, query, seq, &p)).unwrap();
                execute(&request(8, query, seq, t)).unwrap();
            }
            21 => return s,
            c => panic!("unexpected member status {c}"),
        }
    }
}
#[test]
fn domain_members_protocol_pages_full_ids_and_outlives_all_original_owners() {
    let _lock = test_processor_lock();
    let before = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let chunks = [chunk(u64::MAX, -5, 0.), chunk(u64::MAX, -5, 0.)];
    let mut prior = overview_data(&chunks, Some(0));
    let mut issuer = 7;
    for row in 0..3 {
        let seq = 10 + row;
        let q = u64_at(
            &execute(&member_request(prior, issuer, seq, 136, 1)).unwrap(),
            16,
        );
        close(prior, 0);
        let done = members_drive(q, seq, &chunks);
        assert_eq!(u64_at(&done, 40), 2);
        assert_eq!(u64_at(&done, 48), (row + 1).min(2));
        assert_eq!(u32_at(&done, 56), u32::from(row < 2));
        let result = execute(&with_budget(request(46, q, seq, &[]))).unwrap();
        assert_eq!(u64_at(&result, 16), q);
        // Lost publication response is recoverable without allocating or replaying 46.
        assert_eq!(step(q, seq), result);
        assert!(execute(&with_budget(request(46, q, seq, &[]))).is_err());
        let read = request(23, q, seq, &[]);
        let len = data_len(&read, 128 << 20).unwrap();
        assert_eq!(data_len(&read, 128 << 20).unwrap(), len);
        let b = read_data(&read, 128 << 20).unwrap();
        assert_eq!(&b[..4], b"XYOM");
        assert_eq!(u32_at(&b, 8), 3);
        if row < 2 {
            assert_eq!(u64_at(&b, 256), u64::MAX);
            assert_eq!(u64_at(&b, 264), row);
            assert_eq!(u64_at(&b, 280), 1);
        } else {
            assert_eq!(b.len(), HEADER);
        }
        assert_eq!(u64_at(&b, 224), 0);
        assert_eq!(u64_at(&b, 48), 2);
        assert!(crate::geo_scale_protocol::with_overview_data(q, seq, |_, _, _| Ok(())).is_err());
        drop(b);
        drop(read_data(&read, 128 << 20).unwrap());
        assert_eq!(read_data(&read, 128 << 20), Err(SourceError::ResourceLimit));
        prior = q;
        issuer = seq;
    }
    close(prior, 0);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        before
    );
}
#[test]
fn domain_members_failed_publish_preserves_query_and_exact_pending_ack() {
    let _lock = test_processor_lock();
    let chunks = [chunk(1, -5, 0.)];
    let data = overview_data(&chunks, None);
    let q = u64_at(
        &execute(&member_request(data, 7, 10, 136, 4096)).unwrap(),
        16,
    );
    let read = step(q, 10);
    let ticket = read[64..192].to_vec();
    let mut forged = ticket.clone();
    forged[8] ^= 1;
    assert_eq!(
        execute(&request(8, q, 10, &forged)),
        Err(SourceError::StaleSource)
    );
    assert_eq!(u32_at(&execute(&request(10, q, 10, &[])).unwrap(), 8), 2);
    execute(&request(8, q, 10, &ticket)).unwrap();
    close(q, 10);
    let q = u64_at(
        &execute(&member_request(data, 7, 11, 136, 4096)).unwrap(),
        16,
    );
    members_drive(q, 11, &chunks);
    let mut small = with_budget(request(46, q, 11, &[]));
    p64(&mut small, 32, 1);
    assert_eq!(execute(&small), Err(SourceError::ResourceLimit));
    assert_eq!(u32_at(&step(q, 11), 8), 21);
    execute(&with_budget(request(46, q, 11, &[]))).unwrap();
    close(q, 0);
    close(data, 0);
}
#[test]
fn domain_members_share_eight_data_cap_and_failed_conversion_recovers() {
    let _lock = test_processor_lock();
    let chunks = [chunk(1, -5, 0.)];
    let data = overview_data(&chunks, None);
    let mut pages = Vec::new();
    for seq in 10..17 {
        let q = u64_at(
            &execute(&member_request(data, 7, seq, 136, 4096)).unwrap(),
            16,
        );
        members_drive(q, seq, &chunks);
        execute(&with_budget(request(46, q, seq, &[]))).unwrap();
        pages.push(q);
    }
    let q = u64_at(
        &execute(&member_request(data, 7, 17, 136, 4096)).unwrap(),
        16,
    );
    members_drive(q, 17, &chunks);
    assert_eq!(
        execute(&with_budget(request(46, q, 17, &[]))),
        Err(SourceError::ResourceLimit)
    );
    assert_eq!(u32_at(&step(q, 17), 8), 21);
    close(data, 0);
    execute(&with_budget(request(46, q, 17, &[]))).unwrap();
    for p in pages {
        close(p, 0);
    }
    close(q, 0);
}
#[test]
fn domain_members_private_continuation_rejects_foreign_cell_and_sequence() {
    let _lock = test_processor_lock();
    let chunks = [chunk(u64::MAX, -5, 0.), chunk(1 << 63, -5, 0.)];
    let data = overview_data(&chunks, None);
    assert_eq!(
        execute(&member_request(data, 8, 10, 136, 1)),
        Err(SourceError::StaleSource)
    );
    let q = u64_at(&execute(&member_request(data, 7, 10, 136, 1)).unwrap(), 16);
    members_drive(q, 10, &chunks);
    execute(&with_budget(request(46, q, 10, &[]))).unwrap();
    assert_eq!(
        execute(&member_request(q, 10, 11, 137, 1)),
        Err(SourceError::StaleSource)
    );
    assert_eq!(
        execute(&member_request(q, 10, 10, 136, 1)),
        Err(SourceError::StaleSource)
    );
    assert!(execute(&request(26, q, 10, &[])).is_err());
    assert!(execute(&request(12, q, 10, &[])).is_err());
    close(q, 0);
    close(data, 0);
}
fn multipoint_chunk() -> Vec<u8> {
    let ids = [u64::MAX, 1 << 63, u64::MAX, 9];
    let column = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::MultiPoint,
        crs: GeoCrs::Epsg4326,
        xy: &[0., 0., 0., 0., -180., 0., 0., 0.],
        validity: &[1, 0, 1, 1],
        feature_ids: Some(&ids),
        offsets0: &[0, 2, 2, 3, 4],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    GeoChunk::encode(
        &column,
        Some(GeoIntervals {
            starts: &[i64::MIN, 0, 0, 10],
            ends: &[i64::MAX, 0, 10, 20],
            start_validity: &[0, 0, 1, 1],
            end_validity: &[0, 0, 1, 1],
        }),
    )
    .unwrap()
}
#[test]
fn domain_members_multipoint_timefirst_counts_vertices_once_per_original_row() {
    let _lock = test_processor_lock();
    let chunks = [multipoint_chunk()];
    for (time, expected) in [(Some(i64::MIN), 2), (Some(0), 2), (Some(10), 3)] {
        let data = overview_data(&chunks, time);
        let q = u64_at(
            &execute(&member_request(data, 7, 10, 136, 4096)).unwrap(),
            16,
        );
        close(data, 0);
        let done = members_drive(q, 10, &chunks);
        assert_eq!(u64_at(&done, 40), expected);
        execute(&with_budget(request(46, q, 10, &[]))).unwrap();
        let packet = read_data(&request(23, q, 10, &[]), 128 << 20).unwrap();
        assert_eq!(u64_at(&packet, 256), u64::MAX);
        assert_eq!(u64_at(&packet, 264), 0);
        assert_eq!(u64_at(&packet, 280), 2);
        assert_eq!(u64_at(&packet, 240), expected);
        assert_eq!(u64_at(&packet, 224), time.unwrap() as u64);
        assert_eq!(u64_at(&packet, 32), if expected == 3 { 2 } else { 1 });
        if expected == 3 {
            assert_eq!(u64_at(&packet, 288), 9);
            assert_eq!(u64_at(&packet, 296), 3);
        }
        drop(packet);
        close(q, 0);
    }
}
#[test]
fn domain_members_sessions_cap_and_corrupt_read_never_publish() {
    let _lock = test_processor_lock();
    let chunks = [chunk(1, -5, 0.)];
    let data = overview_data(&chunks, None);
    let mut queries = Vec::new();
    for seq in 10..18 {
        queries.push((
            u64_at(
                &execute(&member_request(data, 7, seq, 136, 4096)).unwrap(),
                16,
            ),
            seq,
        ));
    }
    assert_eq!(
        execute(&member_request(data, 7, 18, 136, 4096)),
        Err(SourceError::ResourceLimit)
    );
    let (q, seq) = queries.pop().unwrap();
    let reply = step(q, seq);
    let t = reply[64..192].to_vec();
    let mut bytes = chunks[0].clone();
    bytes[0] ^= 1;
    let mut p = t.clone();
    p.extend(bytes);
    assert!(execute(&request(7, q, seq, &p)).is_err());
    assert!(execute(&with_budget(request(46, q, seq, &[]))).is_err());
    assert_eq!(u32_at(&execute(&request(9, q, seq, &[])).unwrap(), 8), 2);
    assert_eq!(u32_at(&execute(&request(10, q, seq, &[])).unwrap(), 8), 2);
    execute(&request(8, q, seq, &t)).unwrap();
    close(q, seq);
    for (q, seq) in queries {
        close(q, seq);
    }
    close(data, 0);
}
#[test]
fn domain_members_same_handle_publication_works_at_total_handle_cap() {
    let _lock = test_processor_lock();
    let chunks = [chunk(1, -5, 0.)];
    let data = overview_data(&chunks, None);
    let q = u64_at(
        &execute(&member_request(data, 7, 10, 136, 4096)).unwrap(),
        16,
    );
    members_drive(q, 10, &chunks);
    let held = (0..14)
        .map(|_| finish_manifest(&chunks).0)
        .collect::<Vec<_>>();
    assert_eq!(
        execute(&request(1, 0, 0, &[])),
        Err(SourceError::ResourceLimit)
    );
    assert_eq!(
        u64_at(&execute(&with_budget(request(46, q, 10, &[]))).unwrap(), 16),
        q
    );
    assert_eq!(u32_at(&step(q, 10), 8), 0);
    close(q, 0);
    close(data, 0);
    drop(held);
}
