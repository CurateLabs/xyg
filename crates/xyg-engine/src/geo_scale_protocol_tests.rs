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
struct Snapshot {
    bytes: Vec<u8>,
    _handle: Handle,
}
fn scene_data(h: u64, seq: u64) -> Result<Snapshot, SourceError> {
    let fixed = execute(&scene_request(h, seq))?;
    let data = Handle(u64_at(&fixed, 16));
    for _ in 0..4 {
        assert_eq!(
            data_len(&request(23, data.0, 0, &[]), 128 << 20)?,
            u64_at(&fixed, 32) as usize
        );
    }
    let bytes = read_data(&request(23, data.0, 0, &[]), 128 << 20)?;
    assert_eq!(u64_at(&fixed, 32), bytes.len() as u64);
    assert_eq!(u64_at(&fixed, 40), h);
    Ok(Snapshot {
        bytes,
        _handle: data,
    })
}
#[test]
fn byte_lifecycle_preserves_full_ids_time_first_and_failure_atomicity() {
    let _guard = test_processor_lock();
    let chunks = [chunk(u64::MAX, 0, 0.), chunk(0x8000000000000001, 10, 1.)];
    let (_builder, bytes) = finish_manifest(&chunks);
    let manifest = GeoSourceManifest::validate(
        &bytes,
        &mut |r: crate::geo_source::ReadRequest| Ok(chunks[r.chunk_index as usize].clone()),
        &mut || false,
    )
    .unwrap();
    assert_eq!(manifest.generation(), u64::MAX);
    assert_eq!(manifest.rows(), 2);
    let session = Handle(u64_at(
        &execute(&with_budget(request(4, 0, 0, &bytes))).unwrap(),
        16,
    ));
    assert_eq!(drive(session.0, 0, &chunks), (3, vec![0, 1]));
    let mut malformed = begin(session.0, 1, &manifest, None, 100);
    p64(&mut malformed, 208, 1);
    assert!(matches!(
        execute(&malformed),
        Err(SourceError::InvalidFrame)
    ));
    let mut malformed = begin(session.0, 1, &manifest, Some(5), 100);
    p64(&mut malformed, 216, 1);
    assert!(matches!(
        execute(&malformed),
        Err(SourceError::InvalidFrame)
    ));
    execute(&begin(session.0, 10, &manifest, Some(5), 100)).unwrap();
    assert_eq!(drive(session.0, 10, &chunks), (4, vec![0]));
    let baseline_snapshot = scene_data(session.0, 10).unwrap();
    let baseline = &baseline_snapshot.bytes;
    assert_eq!(&baseline[..4], b"XYGZ");
    assert_eq!(u64_at(baseline, 24), 10);
    assert_eq!(u64_at(baseline, 48), 1);
    let scene_len = u64_at(baseline, 32) as usize;
    let metadata = &baseline[HEADER + scene_len..];
    assert_eq!(metadata.len(), 40);
    assert_eq!(u64_at(metadata, 0), u64::MAX);
    assert_eq!(u64_at(metadata, 8), 0);
    let mut invalid_style = scene_request(session.0, 10);
    invalid_style[HEADER + 32] = 255;
    assert!(execute(&invalid_style).is_err());

    assert_eq!(u32_at(baseline, 80), 4326);
    assert_eq!(u32_at(baseline, 84), 1);
    assert_eq!(&baseline[144..152], &manifest.digest());
    assert_eq!(u64_at(baseline, 152), u64::MAX);
    assert_eq!(u64_at(baseline, 160), u64::MAX);
    for at in [168, 176, 184, 192, 200] {
        assert_eq!(u64_at(baseline, at), 10);
    }
    assert_eq!(u32_at(baseline, 208), 1);
    assert_eq!(u64_at(baseline, 216), 5);
    assert_eq!(u64_at(baseline, 232), 2);
    assert_eq!(u32_at(baseline, 240), GeoGeometry::Point as u32);
    assert_eq!(u32_at(baseline, 244), GeoCrs::Epsg4326 as u32);

    assert!(matches!(
        execute(&begin(session.0, 5, &manifest, None, 100)),
        Err(SourceError::StaleSource)
    ));
    assert_eq!(scene_data(session.0, 10).unwrap().bytes, *baseline);
    assert!(matches!(
        scene_data(session.0, 9),
        Err(SourceError::StaleSource)
    ));
    execute(&begin(session.0, 11, &manifest, None, 1)).unwrap();
    let first = ticket(&step(session.0, 11));
    supply(session.0, 11, &first, &chunks[0]).unwrap();
    release(session.0, 11, &first);
    let second = ticket(&step(session.0, 11));
    assert!(matches!(
        supply(session.0, 11, &second, &chunks[1]),
        Err(SourceError::ResourceLimit)
    ));
    release(session.0, 11, &second);
    assert_eq!(scene_data(session.0, 10).unwrap().bytes, *baseline);
    execute(&begin(session.0, 20, &manifest, None, 100)).unwrap();
    assert!(matches!(
        execute(&request(6, session.0, 0, &[])),
        Err(SourceError::StaleSource)
    ));
    assert!(matches!(
        execute(&request(6, session.0, 19, &[])),
        Err(SourceError::StaleSource)
    ));
    let old = ticket(&step(session.0, 20));
    execute(&begin(session.0, 21, &manifest, None, 100)).unwrap();
    assert!(matches!(
        supply(session.0, 20, &old, &chunks[0]),
        Err(SourceError::StaleSource)
    ));
    release(session.0, 20, &old);
    assert_eq!(drive(session.0, 21, &chunks), (4, vec![0, 1]));
    let output_snapshot = scene_data(session.0, 21).unwrap();
    let output = &output_snapshot.bytes;
    let at = HEADER + u64_at(output, 32) as usize;
    assert_eq!(u64_at(&output[at + 40..], 0), 0x8000000000000001);
    assert_eq!(u64_at(&output[at + 40..], 8), 1);

    execute(&begin(session.0, 22, &manifest, None, 100)).unwrap();
    let pending = ticket(&step(session.0, 22));
    assert_eq!(
        u32_at(&execute(&request(10, session.0, 0, &[])).unwrap(), 8),
        2
    );
    assert!(matches!(
        supply(session.0, 22, &pending, &chunks[0]),
        Err(SourceError::StaleSource)
    ));
    release(session.0, 22, &pending);
    execute(&request(10, session.0, 0, &[])).unwrap();
    assert_eq!(
        read_data(&request(23, baseline_snapshot._handle.0, 0, &[]), 128 << 20).unwrap(),
        *baseline
    );
    assert!(matches!(
        read_data(&request(23, baseline_snapshot._handle.0, 0, &[]), 128 << 20),
        Err(SourceError::ResourceLimit)
    ));
    assert!(matches!(
        execute(&request(6, session.0, 0, &[])),
        Err(SourceError::StaleSource)
    ));
}
#[test]
fn exact_header_and_retired_ticket_padding_reject_before_mutation() {
    let _guard = test_processor_lock();
    let mut b = request(1, 0, 0, &[]);
    b[228] = 1;
    let r = execute(&b);
    if let Ok(out) = &r {
        let _ = execute(&request(10, u64_at(out, 16), 0, &[]));
    }
    assert!(matches!(r, Err(SourceError::InvalidFrame)));
    for b in [
        request(0, 0, 0, &[]),
        request(u32::MAX, 0, 0, &[]),
        request(1, 0, 0, &[0]),
    ] {
        assert!(execute(&b).is_err());
    }
    let chunks = [chunk(u64::MAX, 0, 0.)];
    let (_h, bytes) = finish_manifest(&chunks);
    let s = Handle(u64_at(
        &execute(&with_budget(request(4, 0, 0, &bytes))).unwrap(),
        16,
    ));
    let valid = ticket(&step(s.0, 0));
    let mut bad = valid.clone();
    bad[72] = 1;
    assert!(matches!(
        supply(s.0, 0, &bad, &chunks[0]),
        Err(SourceError::InvalidFrame)
    ));
    assert_eq!(ticket(&step(s.0, 0)), valid);
    supply(s.0, 0, &valid, &chunks[0]).unwrap();
    release(s.0, 0, &valid);
}

#[test]
fn registry_cap_stale_handles_and_failed_commands_preserve_manifest() {
    let _guard = test_processor_lock();
    let chunks = [chunk(u64::MAX, 0, 0.)];
    let mut held = Vec::new();
    for _ in 0..crate::geo_scale_protocol::MAX_HANDLES {
        let (h, bytes) = finish_manifest(&chunks);
        assert!(!bytes.is_empty());
        held.push(h);
    }
    assert!(matches!(
        execute(&request(1, 0, 0, &[])),
        Err(SourceError::ResourceLimit)
    ));
    let saved = read_data(&request(21, held[0].0, 0, &[]), 128 << 20).unwrap();
    assert!(execute(&request(2, held[0].0, 0, &chunks[0])).is_err());
    assert!(execute(&request(3, held[0].0, 0, &[])).is_err());
    assert_eq!(
        read_data(&request(21, held[0].0, 0, &[]), 128 << 20).unwrap(),
        saved
    );
    let old = held.pop().unwrap();
    let old_id = old.0;
    drop(old);
    assert!(matches!(
        read_data(&request(21, old_id, 0, &[]), 128 << 20),
        Err(SourceError::StaleSource)
    ));
    let replacement = builder();
    assert!(replacement.0 > old_id);
}

#[test]
fn typed_chunk_authoring_preserves_ids_signed_time_and_scalar_and_rejects_bad_lengths() {
    let _guard = test_processor_lock();
    let mut descriptor = vec![0; 96];
    descriptor[..4].copy_from_slice(b"XYGD");
    p32(&mut descriptor, 4, 1);
    p32(&mut descriptor, 8, 1);
    p32(&mut descriptor, 12, 4326);
    p32(&mut descriptor, 16, 1);
    p64(&mut descriptor, 24, 1);
    p64(&mut descriptor, 32, 1);
    p64(&mut descriptor, 64, 1.25f64.to_bits());
    p64(&mut descriptor, 72, (-2.5f64).to_bits());
    descriptor[80] = 1;
    p64(&mut descriptor, 88, u64::MAX);
    let mut payload = vec![0; 32];
    p64(&mut payload, 0, 96);
    p32(&mut payload, 8, 3);
    p64(&mut payload, 16, 1);
    payload.extend(&descriptor);
    payload.extend((-9i64).to_le_bytes());
    payload.extend(3i64.to_le_bytes());
    payload.extend([1, 1]);
    payload.extend(42.5f64.to_le_bytes());
    let encoded = read_data(&request(20, 0, 0, &payload), 128 << 20).unwrap();
    let decoded = GeoChunk::parse(&encoded, 96 << 20).unwrap();
    assert_eq!(decoded.column().feature_ids(), &[u64::MAX]);
    assert_eq!(decoded.column().xy(), &[1.25, -2.5]);
    let f = decoded.rows().next().unwrap();
    assert_eq!(f.interval_start, Some(-9));
    assert_eq!(f.interval_end, Some(3));
    assert_eq!(f.value, Some(42.5));
    let mut bad = payload.clone();
    p64(&mut bad, 0, u64::MAX);
    assert!(read_data(&request(20, 0, 0, &bad), 128 << 20).is_err());
    let mut bad = payload.clone();
    bad[12] = 1;
    assert!(matches!(
        read_data(&request(20, 0, 0, &bad), 128 << 20),
        Err(SourceError::InvalidFrame)
    ));
    let mut bad = payload.clone();
    bad.push(0);
    assert!(read_data(&request(20, 0, 0, &bad), 128 << 20).is_err());
    assert!(matches!(
        read_data(&request(20, 0, 0, &payload), 256),
        Err(SourceError::ResourceLimit)
    ));
}

#[test]
fn session_and_snapshot_caps_are_independent_and_recover_after_release() {
    let _guard = test_processor_lock();
    let chunks = [chunk(u64::MAX, 0, 0.)];
    let (_builder, bytes) = finish_manifest(&chunks);
    let manifest = GeoSourceManifest::validate(
        &bytes,
        &mut |r: crate::geo_source::ReadRequest| Ok(chunks[r.chunk_index as usize].clone()),
        &mut || false,
    )
    .unwrap();
    let mut sessions = Vec::new();
    for _ in 0..8 {
        sessions.push(Handle(u64_at(
            &execute(&with_budget(request(4, 0, 0, &bytes))).unwrap(),
            16,
        )));
    }
    assert!(matches!(
        execute(&with_budget(request(4, 0, 0, &bytes))),
        Err(SourceError::ResourceLimit)
    ));
    let primary = sessions.remove(0);
    drop(sessions);
    assert_eq!(drive(primary.0, 0, &chunks).0, 3);
    execute(&begin(primary.0, 1, &manifest, None, 100)).unwrap();
    assert_eq!(drive(primary.0, 1, &chunks).0, 4);
    let mut snapshots = Vec::new();
    for _ in 0..8 {
        snapshots.push(scene_data(primary.0, 1).unwrap());
    }
    assert!(matches!(
        scene_data(primary.0, 1),
        Err(SourceError::ResourceLimit)
    ));
    let released = snapshots.pop().unwrap();
    let old = released._handle.0;
    drop(released);
    assert!(matches!(
        read_data(&request(23, old, 0, &[]), 128 << 20),
        Err(SourceError::StaleSource)
    ));
    let recovered = scene_data(primary.0, 1).unwrap();
    assert!(recovered._handle.0 > old);
}

#[test]
fn actual_density_snapshot_counts_multipoint_vertices_and_carries_exact_profile() {
    let _guard = test_processor_lock();
    let n = 32773;
    let column = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::MultiPoint,
        crs: GeoCrs::Epsg4326,
        xy: &vec![0.; n * 2],
        validity: &[1],
        feature_ids: Some(&[u64::MAX]),
        offsets0: &[0, n as u32],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let chunks = [GeoChunk::encode(&column, None).unwrap()];
    let (_builder, bytes) = finish_manifest(&chunks);
    let manifest = GeoSourceManifest::validate(
        &bytes,
        &mut |r: crate::geo_source::ReadRequest| Ok(chunks[r.chunk_index as usize].clone()),
        &mut || false,
    )
    .unwrap();
    let session = Handle(u64_at(
        &execute(&with_budget(request(4, 0, 0, &bytes))).unwrap(),
        16,
    ));
    assert_eq!(drive(session.0, 0, &chunks).0, 3);
    let mut command = begin(session.0, 1, &manifest, None, 100000);
    p32(&mut command, 68, 1);
    p32(&mut command, 72, 196608);
    execute(&command).unwrap();
    assert_eq!(drive(session.0, 1, &chunks), (4, vec![0, 0]));
    let snapshot = scene_data(session.0, 1).unwrap();
    let packet = &snapshot.bytes;
    assert_eq!(u32_at(packet, 8), 1);
    assert_eq!(u32_at(packet, 12), 7);
    assert_eq!(u32_at(packet, 212), 1);
    assert_eq!(u64_at(packet, 48), n as u64);
    assert_eq!(u64_at(packet, 56), n as u64 * 2);
    assert_eq!(u64_at(packet, 232), 1);
    assert_eq!(u32_at(packet, 240), GeoGeometry::MultiPoint as u32);
    let cells = u32_at(packet, 64) as usize * u32_at(packet, 68) as usize;
    let metadata = &packet[HEADER + u64_at(packet, 32) as usize..];
    assert_eq!(metadata.len(), cells * 24);
    assert!(cells <= 196608);
    let nonempty: Vec<_> = metadata
        .chunks_exact(24)
        .filter(|c| u64_at(c, 0) > 0)
        .collect();
    assert_eq!(nonempty.len(), 1);
    assert_eq!(u64_at(nonempty[0], 0), n as u64);
    assert_eq!(f64::from_bits(u64_at(nonempty[0], 8)), 400.);
    assert_eq!(f64::from_bits(u64_at(nonempty[0], 16)), 300.);
    let document =
        crate::scene::SceneDocument::decode(&packet[HEADER..HEADER + u64_at(packet, 32) as usize])
            .unwrap();
    assert!(document.interaction_image(u64::MAX).is_some());
}
