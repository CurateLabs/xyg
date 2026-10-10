//! Independent snapshot-local recovery proofs; no private registry access.
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

fn overview_fixture() -> (u64, u64) {
    let chunks = [chunk(u64::MAX, i64::MIN, 0.)];
    let (seed, manifest) = source_frame(&chunks);
    let (index, pages) = build(seed, &chunks, true);
    let query = finish_query(index, &manifest, Some(i64::MIN), 2, &pages);
    let data = u64_at(
        &execute(&with_budget(request(29, query, 2, &[]))).unwrap(),
        16,
    );
    close(query, 2);
    close(index, 1);
    (data, 2)
}
fn snapshot_request(command: u32, issuer: u64, sequence: u64, nonce: u64) -> [u8; 256] {
    let mut b = [0; 256];
    b[..4].copy_from_slice(b"XYGJ");
    p32(&mut b, 4, 1);
    p32(&mut b, 8, command);
    p64(&mut b, 16, issuer);
    p64(&mut b, 24, sequence);
    p64(&mut b, 240, nonce);
    if command == 6 {
        p64(&mut b, 32, 128 << 20);
    }
    b
}
fn control(issuer: u64, seq: u64, nonce: u64, target: u64, action: u32) -> [u8; 256] {
    let mut b = snapshot_request(7, issuer, seq, nonce);
    p64(&mut b, 40, target);
    p32(&mut b, 48, action);
    b
}
#[test]
fn snapshot_recovery_exact_replay_confirm_and_two_reads() {
    let _lock = test_processor_lock();
    let (issuer, seq) = overview_fixture();
    let q = snapshot_request(6, issuer, seq, 1);
    let first = crate::geo_snapshot_protocol::execute(&q).expect("opt-in6 must allocate");
    let target = u64_at(&first, 16);
    assert_eq!(crate::geo_snapshot_protocol::execute(&q).unwrap(), first);
    let ack = crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, target, 0)).unwrap();
    assert_eq!(u64_at(&ack, 16), target);
    assert_eq!(u64_at(&ack, 32), 0);
    close(issuer, 0);
    assert_eq!(crate::geo_snapshot_protocol::execute(&q).unwrap(), first);
    let read = snapshot_request(20, target, 0, 0);
    let one = crate::geo_snapshot_protocol::read_data(&read, 128 << 20).unwrap();
    let two = crate::geo_snapshot_protocol::read_data(&read, 128 << 20).unwrap();
    assert_eq!(one, two);
    assert!(crate::geo_snapshot_protocol::read_data(&read, 128 << 20).is_err());
    drop(one);
    drop(two);
    crate::geo_snapshot_protocol::execute(&snapshot_request(3, target, 0, 0)).unwrap();
    let retired = crate::geo_snapshot_protocol::execute(&q).unwrap();
    assert_eq!(u32_at(&retired, 8), 2);
    assert_eq!(u64_at(&retired, 16), 0);
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, 0, 0)).unwrap();
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, 0, 2)).unwrap();
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, 0, 1)).unwrap();
}

fn dispose_snapshot(target: u64) {
    crate::geo_snapshot_protocol::execute(&snapshot_request(3, target, 0, 0)).unwrap();
}
fn retire_release(issuer: u64, seq: u64, nonce: u64, target: u64) {
    dispose_snapshot(target);
    let retired =
        crate::geo_snapshot_protocol::execute(&control(issuer, seq, nonce, target, 0)).unwrap();
    assert_eq!(u32_at(&retired, 8), 2);
    assert_eq!(u64_at(&retired, 16), 0);
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, nonce, target, 2)).unwrap();
}
#[test]
fn snapshot_recovery_preserves_eight_owners_and_legacy_bytes() {
    let _lock = test_processor_lock();
    let (issuer, seq) = overview_fixture();
    let mut targets = Vec::new();
    let legacy =
        crate::geo_snapshot_protocol::execute(&snapshot_request(6, issuer, seq, 0)).unwrap();
    let old = u64_at(&legacy, 16);
    let legacy_bytes =
        crate::geo_snapshot_protocol::read_data(&snapshot_request(20, old, 0, 0), 128 << 20)
            .unwrap();
    dispose_snapshot(old);
    for nonce in 1..=8 {
        let q = snapshot_request(6, issuer, seq, nonce);
        let fixed = crate::geo_snapshot_protocol::execute(&q).unwrap();
        let target = u64_at(&fixed, 16);
        assert_eq!(crate::geo_snapshot_protocol::execute(&q).unwrap(), fixed);
        assert!(crate::geo_snapshot_protocol::data_len(
            &snapshot_request(20, target, 0, 0),
            128 << 20
        )
        .is_err());
        crate::geo_snapshot_protocol::execute(&control(issuer, seq, nonce, target, 0)).unwrap();
        let bytes =
            crate::geo_snapshot_protocol::read_data(&snapshot_request(20, target, 0, 0), 128 << 20)
                .unwrap();
        assert_eq!(bytes, legacy_bytes);
        drop(bytes);
        targets.push(target);
    }
    let ninth = snapshot_request(6, issuer, seq, 9);
    assert!(crate::geo_snapshot_protocol::execute(&ninth).is_err());
    close(issuer, 0);
    for (i, target) in targets.iter().enumerate() {
        retire_release(issuer, seq, i as u64 + 1, *target);
    }
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 8, 0, 1)).unwrap();
}
#[test]
fn snapshot_recovery_full_request_and_confirm_precede_new_nonce() {
    let _lock = test_processor_lock();
    let (issuer, seq) = overview_fixture();
    let first = snapshot_request(6, issuer, seq, 1);
    let fixed = crate::geo_snapshot_protocol::execute(&first).unwrap();
    let target = u64_at(&fixed, 16);
    let mut changed = first;
    p64(&mut changed, 32, 64 << 20);
    assert!(crate::geo_snapshot_protocol::execute(&changed).is_err());
    assert!(crate::geo_snapshot_protocol::execute(&snapshot_request(6, issuer, seq, 2)).is_err());
    assert!(
        crate::geo_snapshot_protocol::execute(&control(issuer, seq + 1, 1, target, 0)).is_err()
    );
    assert!(crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, target, 2)).is_err());
    for at in [12, 52, 56, 239, 248, 255] {
        let mut bad = control(issuer, seq, 1, target, 0);
        bad[at] = 1;
        assert!(crate::geo_snapshot_protocol::execute(&bad).is_err());
    }
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, target, 0)).unwrap();
    assert!(crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, target, 2)).is_err());
    let mut tiny = snapshot_request(6, issuer, seq, 2);
    p64(&mut tiny, 32, 34304);
    assert!(crate::geo_snapshot_protocol::execute(&tiny).is_err());
    assert_eq!(
        crate::geo_snapshot_protocol::execute(&first).unwrap(),
        fixed
    );
    close(issuer, 0);
    retire_release(issuer, seq, 1, target);
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, 0, 1)).unwrap();
}
#[test]
fn snapshot_recovery_historical_retirement_and_lost_release_ack() {
    let _lock = test_processor_lock();
    let (issuer, seq) = overview_fixture();
    let a = snapshot_request(6, issuer, seq, 1);
    let t1 = u64_at(&crate::geo_snapshot_protocol::execute(&a).unwrap(), 16);
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, t1, 0)).unwrap();
    let b = snapshot_request(6, issuer, seq, 2);
    let t2 = u64_at(&crate::geo_snapshot_protocol::execute(&b).unwrap(), 16);
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 2, t2, 0)).unwrap();
    assert!(crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, t1 + 100, 0)).is_err());
    dispose_snapshot(t1);
    let retired = crate::geo_snapshot_protocol::execute(&a).unwrap();
    assert_eq!(u32_at(&retired, 8), 2);
    assert_eq!(u64_at(&retired, 16), 0);
    let c = control(issuer, seq, 1, t1, 0);
    assert_eq!(crate::geo_snapshot_protocol::execute(&c).unwrap(), retired);
    let release = control(issuer, seq, 1, t1, 2);
    let ack = crate::geo_snapshot_protocol::execute(&release).unwrap();
    assert_eq!(
        crate::geo_snapshot_protocol::execute(&release).unwrap(),
        ack
    );
    assert!(crate::geo_snapshot_protocol::execute(&a).is_err());
    close(issuer, 0);
    retire_release(issuer, seq, 2, t2);
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 2, 0, 1)).unwrap();
}

#[test]
fn snapshot_recovery_sixteen_issuer_pressure_and_death_refund() {
    let _lock = test_processor_lock();
    let mut held = Vec::new();
    for _ in 0..16 {
        let (issuer, seq) = overview_fixture();
        let q = snapshot_request(6, issuer, seq, 1);
        let target = u64_at(&crate::geo_snapshot_protocol::execute(&q).unwrap(), 16);
        crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, target, 0)).unwrap();
        close(issuer, 0);
        dispose_snapshot(target);
        held.push((issuer, seq));
    }
    let (issuer, seq) = overview_fixture();
    let q = snapshot_request(6, issuer, seq, 1);
    assert!(crate::geo_snapshot_protocol::execute(&q).is_err());
    let (old, s) = held.remove(0);
    crate::geo_snapshot_protocol::execute(&control(old, s, 1, 0, 2)).unwrap();
    let target = u64_at(&crate::geo_snapshot_protocol::execute(&q).unwrap(), 16);
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, target, 0)).unwrap();
    close(issuer, 0);
    retire_release(issuer, seq, 1, target);
    for (issuer, seq) in held {
        crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, 0, 2)).unwrap();
    }
}
#[test]
fn snapshot_recovery_sixteen_historical_stamps_fail_before_mutation_then_retry() {
    let _lock = test_processor_lock();
    let (issuer, seq) = overview_fixture();
    let mut held = Vec::new();
    for nonce in 1..=17 {
        let target = u64_at(
            &crate::geo_snapshot_protocol::execute(&snapshot_request(6, issuer, seq, nonce))
                .unwrap(),
            16,
        );
        crate::geo_snapshot_protocol::execute(&control(issuer, seq, nonce, target, 0)).unwrap();
        dispose_snapshot(target);
        held.push(target);
    }
    let next = snapshot_request(6, issuer, seq, 18);
    assert!(crate::geo_snapshot_protocol::execute(&next).is_err());
    let first = held[0];
    let release = control(issuer, seq, 1, first, 2);
    crate::geo_snapshot_protocol::execute(&release).unwrap();
    let target = u64_at(&crate::geo_snapshot_protocol::execute(&next).unwrap(), 16);
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 18, target, 0)).unwrap();
    assert_eq!(
        u64_at(
            &crate::geo_snapshot_protocol::execute(&release).unwrap(),
            16
        ),
        0
    );
    close(issuer, 0);
    retire_release(issuer, seq, 18, target);
    for (i, target) in held.into_iter().enumerate().skip(1) {
        crate::geo_snapshot_protocol::execute(&control(issuer, seq, i as u64 + 1, target, 2))
            .unwrap();
    }
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 18, 0, 1)).unwrap();
}

#[test]
fn snapshot_recovery_older_live_birth_reserves_retirement_through_pressure() {
    let _lock = test_processor_lock();
    let (issuer, seq) = overview_fixture();
    let first = snapshot_request(6, issuer, seq, 1);
    let old = u64_at(&crate::geo_snapshot_protocol::execute(&first).unwrap(), 16);
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 1, old, 0)).unwrap();
    let mut held = Vec::new();
    for nonce in 2..=17 {
        let target = u64_at(
            &crate::geo_snapshot_protocol::execute(&snapshot_request(6, issuer, seq, nonce))
                .unwrap(),
            16,
        );
        crate::geo_snapshot_protocol::execute(&control(issuer, seq, nonce, target, 0)).unwrap();
        dispose_snapshot(target);
        held.push(target);
    }
    let next = snapshot_request(6, issuer, seq, 18);
    assert!(crate::geo_snapshot_protocol::execute(&next).is_err());
    let bytes =
        crate::geo_snapshot_protocol::read_data(&snapshot_request(20, old, 0, 0), 128 << 20)
            .unwrap();
    assert_eq!(&bytes[..4], b"XYGX");
    drop(bytes);
    // Retiring the older live owner must use its already-reserved slot.
    retire_release(issuer, seq, 1, old);
    let target = u64_at(&crate::geo_snapshot_protocol::execute(&next).unwrap(), 16);
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 18, target, 0)).unwrap();
    close(issuer, 0);
    retire_release(issuer, seq, 18, target);
    for (i, target) in held.into_iter().enumerate() {
        crate::geo_snapshot_protocol::execute(&control(issuer, seq, i as u64 + 2, target, 2))
            .unwrap();
    }
    crate::geo_snapshot_protocol::execute(&control(issuer, seq, 18, 0, 1)).unwrap();
}
