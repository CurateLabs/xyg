//! Public byte-protocol proofs: the host only stores exact Rust-issued bytes.
use super::*;
use crate::geo::{GeoColumn, GeoDescriptor, GeoLimits};
use crate::geo_source_session::test_processor_lock;
use std::collections::BTreeMap;
fn req(cmd: u32, handle: u64, seq: u64, payload: &[u8]) -> Vec<u8> {
    let mut b = vec![0; HEADER];
    b[..4].copy_from_slice(b"XYGQ");
    put32(&mut b, 4, 1);
    put32(&mut b, 8, cmd);
    put64(&mut b, 16, handle);
    put64(&mut b, 24, seq);
    put64(&mut b, 232, payload.len() as u64);
    b.extend(payload);
    b
}
fn capped(mut b: Vec<u8>) -> Vec<u8> {
    put64(&mut b, 32, 128 << 20);
    put64(&mut b, 40, 1_000_000);
    put64(&mut b, 48, 128 << 20);
    put32(&mut b, 56, 65536);
    put32(&mut b, 60, 4096);
    b
}
struct Handle(u64);
impl Drop for Handle {
    fn drop(&mut self) {
        let _ = execute(&req(10, self.0, 0, &[]));
    }
}
fn style() -> [u8; 48] {
    let mut s = [0; 48];
    s[..4].copy_from_slice(&[255, 0, 0, 255]);
    put64(&mut s, 16, 6f64.to_bits());
    put64(&mut s, 24, 1f64.to_bits());
    s
}
struct Fixture {
    source: Handle,
    frame: Handle,
    chunks: Vec<Vec<u8>>,
    manifest: GeoSourceManifest,
}
fn begin(cmd: u32, h: u64, seq: u64, m: &GeoSourceManifest) -> Vec<u8> {
    let mut b = capped(req(cmd, h, seq, &[]));
    put32(&mut b, 12, 1);
    put32(&mut b, 64, 4326);
    put32(&mut b, 72, 32768);
    put32(&mut b, 76, 1);
    put64(&mut b, 104, 800f64.to_bits());
    put64(&mut b, 112, 600f64.to_bits());
    b[136..144].copy_from_slice(&m.digest());
    put64(&mut b, 144, m.generation());
    put64(&mut b, 152, u64::MAX);
    for at in [160, 168, 176, 184, 192] {
        put64(&mut b, at, seq);
    }
    put64(&mut b, 224, 1_000_000);
    b
}
fn fixture(vertices: u32) -> Fixture {
    let mut chunks = Vec::new();
    let mut m = GeoManifestBuilder::new();
    for part in 0..2 {
        let xy = vec![0.; vertices as usize * 4];
        let offsets = [0, vertices, vertices * 2];
        let col = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::MultiPoint,
            crs: GeoCrs::Epsg4326,
            xy: &xy,
            validity: &[1, 1],
            feature_ids: Some(&[u64::MAX, 1 << 63]),
            offsets0: &offsets,
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        let starts = [part * 10; 2];
        let ends = [part * 10 + 10; 2];
        let bytes = GeoChunk::encode(
            &col,
            Some(GeoIntervals {
                starts: &starts,
                ends: &ends,
                start_validity: &[1, 1],
                end_validity: &[1, 1],
            }),
        )
        .unwrap();
        m.push(&GeoChunk::parse(&bytes, 96 << 20).unwrap()).unwrap();
        chunks.push(bytes);
    }
    finish_fixture(chunks, m)
}
fn finish_fixture(chunks: Vec<Vec<u8>>, m: GeoManifestBuilder) -> Fixture {
    let manifest = m.finish(u64::MAX).unwrap();
    let mut create = capped(req(4, 0, 0, &manifest.encode().unwrap()));
    put32(&mut create, 56, chunks.len() as u32);
    let source = Handle(u64at(&execute(&create).unwrap(), 16));
    drive_reads(source.0, 0, &chunks, None);
    execute(&begin(5, source.0, 1, &manifest)).unwrap();
    drive_reads(source.0, 1, &chunks, None);
    let frame = Handle(u64at(
        &execute(&capped(req(11, source.0, 1, &style()))).unwrap(),
        16,
    ));
    Fixture {
        source,
        frame,
        chunks,
        manifest,
    }
}
fn drive_reads(
    h: u64,
    seq: u64,
    chunks: &[Vec<u8>],
    pages: Option<&BTreeMap<u64, Vec<u8>>>,
) -> [u8; HEADER] {
    loop {
        let out = execute(&req(6, h, seq, &[])).unwrap();
        match u32at(&out, 8) {
            1 => {
                let t = &out[64..160];
                let bytes = if u32at(t, 28) == 2 {
                    &pages.unwrap()[&u64at(t, 8)]
                } else {
                    &chunks[u32at(t, 40) as usize]
                };
                let mut p = t.to_vec();
                p.extend(bytes);
                execute(&req(7, h, 0, &p)).unwrap();
                assert_eq!(u32at(&execute(&req(6, h, seq, &[])).unwrap(), 8), 2);
                execute(&req(8, h, 0, t)).unwrap();
            }
            3 | 4 | 12 => return out,
            code => panic!("unexpected read state {code}"),
        }
    }
}
fn create_build(f: &Fixture, grid: u32) -> Handle {
    let mut p = [0; 16];
    put32(&mut p, 0, grid);
    put64(&mut p, 8, 1_000_000);
    Handle(u64at(
        &execute(&capped(req(17, f.frame.0, 1, &p))).unwrap(),
        16,
    ))
}
fn build_index(f: &Fixture, grid: u32) -> (Handle, BTreeMap<u64, Vec<u8>>) {
    let h = create_build(f, grid);
    let mut pages = BTreeMap::new();
    loop {
        let out = execute(&req(6, h.0, 1, &[])).unwrap();
        let t = &out[64..160];
        match u32at(&out, 8) {
            1 => {
                let mut p = t.to_vec();
                p.extend(&f.chunks[u32at(t, 40) as usize]);
                execute(&req(7, h.0, 0, &p)).unwrap();
                execute(&req(8, h.0, 0, t)).unwrap();
            }
            7 => {
                let r = req(25, h.0, 1, t);
                let len = data_len(&r, 128 << 20).unwrap();
                let bytes = read_data(&r, 128 << 20).unwrap();
                assert_eq!(bytes.len(), len);
                pages.insert(u64at(t, 8), bytes);
                execute(&req(24, h.0, 1, t)).unwrap();
            }
            11 => return (h, pages),
            code => panic!("unexpected build state {code}"),
        }
    }
}
fn data(h: u64, seq: u64, cmd: u32) -> (Handle, Vec<u8>) {
    let out = execute(&capped(req(cmd, h, seq, &style()))).unwrap();
    let data = Handle(u64at(&out, 16));
    let bytes = read_data(&req(23, data.0, 0, &[]), 128 << 20).unwrap();
    (data, bytes)
}
#[test]
fn index_protocol_exact_time_identity_scene_and_immutable_rows_authority() {
    let _guard = test_processor_lock();
    let f = fixture(600);
    let (index, pages) = build_index(&f, 16);
    assert_eq!(pages.len(), 3); // 2400 vertices compacted across source chunks.
    let mut ordinary = begin(5, f.source.0, 2, &f.manifest);
    put32(&mut ordinary, 200, 1);
    put64(&mut ordinary, 208, 10);
    execute(&ordinary).unwrap();
    drive_reads(f.source.0, 2, &f.chunks, None);
    let mut indexed = ordinary.clone();
    put32(&mut indexed, 8, 18);
    put64(&mut indexed, 16, index.0);
    let q = Handle(u64at(&execute(&indexed).unwrap(), 16));
    let stats = drive_reads(q.0, 2, &[], Some(&pages));
    assert!(u64at(&stats, 160) > 0);
    let (_normal, a) = data(f.source.0, 2, 11);
    let (frame, b) = data(q.0, 2, 19);
    assert_eq!(&a[32..56], &b[32..56]);
    assert_eq!(&a[64..], &b[64..]);
    drop(q);
    drop(index);
    drop(f.source);
    drop(f.frame);
    let rows = Handle(u64at(
        &execute(&capped(req(15, frame.0, 2, &[]))).unwrap(),
        16,
    ));
    drive_reads(rows.0, 2, &f.chunks, None);
    let page = Handle(u64at(
        &execute(&capped(req(16, rows.0, 2, &[]))).unwrap(),
        16,
    ));
    let bytes = read_data(&req(23, page.0, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64at(&bytes, 32), 4); // companion rows remain all-source, independently of frame time.
}
#[test]
fn index_protocol_write_copy_quota_retired_ack_and_atomic_disposal() {
    let _guard = test_processor_lock();
    let f = fixture(1);
    let h = create_build(&f, 16);
    let ticket = loop {
        let out = execute(&req(6, h.0, 1, &[])).unwrap();
        let t = &out[64..160];
        match u32at(&out, 8) {
            1 => {
                let mut p = t.to_vec();
                p.extend(&f.chunks[u32at(t, 40) as usize]);
                execute(&req(7, h.0, 0, &p)).unwrap();
                execute(&req(8, h.0, 0, t)).unwrap();
            }
            7 => break t.to_vec(),
            _ => panic!(),
        }
    };
    let r = req(25, h.0, 1, &ticket);
    for _ in 0..4 {
        assert!(data_len(&r, 128 << 20).unwrap() > 64);
    }
    let a = read_data(&r, 128 << 20).unwrap();
    let b = read_data(&r, 128 << 20).unwrap();
    assert_eq!(a, b);
    assert!(matches!(
        read_data(&r, 128 << 20),
        Err(SourceError::ResourceLimit)
    ));
    let live = GeoProcessorLease::live_bytes();
    execute(&req(9, h.0, 1, &[])).unwrap();
    assert_eq!(u32at(&execute(&req(10, h.0, 0, &[])).unwrap(), 8), 2);
    assert!(GeoProcessorLease::live_bytes() > 0);
    let mut forged = ticket.clone();
    forged[0] ^= 1;
    assert!(execute(&req(24, h.0, 1, &forged)).is_err());
    assert_eq!(GeoProcessorLease::live_bytes(), live); // cancelled storage drops, but write credit remains; checked below.
    drop(a);
    drop(b);
    execute(&req(24, h.0, 1, &ticket)).unwrap();
    assert_eq!(u32at(&execute(&req(10, h.0, 0, &[])).unwrap(), 8), 0);
    assert!(GeoProcessorLease::live_bytes() < live);
    assert!(execute(&req(6, h.0, 1, &[])).is_err());
}
#[test]
fn index_protocol_transition_and_style_failures_preserve_old_frame() {
    let _guard = test_processor_lock();
    let f = fixture(2);
    let (index, pages) = build_index(&f, 16);
    let query = begin(18, index.0, 2, &f.manifest);
    let q = Handle(u64at(&execute(&query).unwrap(), 16));
    drive_reads(q.0, 2, &[], Some(&pages));
    let (frame, old) = data(q.0, 2, 19);
    assert!(matches!(execute(&query), Err(SourceError::StaleSource)));
    let mut invalid = query.clone();
    put64(&mut invalid, 24, 3);
    put64(&mut invalid, 80, 1f64.to_bits());
    assert!(matches!(execute(&invalid), Err(SourceError::StaleSource)));
    invalid = query.clone();
    put64(&mut invalid, 24, 3);
    put32(&mut invalid, 200, 1);
    put64(&mut invalid, 208, 10);
    assert!(matches!(execute(&invalid), Err(SourceError::StaleSource)));
    let mut changed = style();
    changed[0] = 0;
    assert!(matches!(
        execute(&capped(req(19, q.0, 2, &changed))),
        Err(SourceError::StaleSource)
    ));
    let next = begin(18, index.0, 3, &f.manifest);
    let newer = Handle(u64at(&execute(&next).unwrap(), 16));
    assert!(matches!(
        execute(&req(6, q.0, 2, &[])),
        Err(SourceError::StaleSource)
    ));
    assert!(matches!(
        execute(&capped(req(19, q.0, 2, &style()))),
        Err(SourceError::StaleSource)
    ));
    drive_reads(newer.0, 3, &[], Some(&pages));
    let updated = Handle(u64at(
        &execute(&capped(req(19, newer.0, 3, &changed))).unwrap(),
        16,
    ));
    drop(updated);
    assert_eq!(
        read_data(&req(23, frame.0, 0, &[]), 128 << 20).unwrap(),
        old
    );
}

#[test]
fn index_protocol_bad_leaf_read_and_stale_ack_preserve_painted_data() {
    let _guard = test_processor_lock();
    let f = fixture(2);
    let (index, pages) = build_index(&f, 16);
    let initial = read_data(&req(23, f.frame.0, 0, &[]), 128 << 20).unwrap();
    let q = Handle(u64at(
        &execute(&begin(18, index.0, 2, &f.manifest)).unwrap(),
        16,
    ));
    let out = execute(&req(6, q.0, 2, &[])).unwrap();
    assert_eq!(u32at(&out, 8), 1);
    let ticket = out[64..160].to_vec();
    let mut forged = ticket.clone();
    forged[0] ^= 1;
    assert!(execute(&req(8, q.0, 0, &forged)).is_err());
    let mut bad = pages[&u64at(&ticket, 8)].clone();
    bad[80] ^= 1;
    let mut supplied = ticket.clone();
    supplied.extend(bad);
    assert!(matches!(
        execute(&req(7, q.0, 0, &supplied)),
        Err(SourceError::StaleSource)
    ));
    assert_eq!(u32at(&execute(&req(10, q.0, 0, &[])).unwrap(), 8), 2);
    assert!(matches!(
        execute(&capped(req(19, q.0, 2, &style()))),
        Err(SourceError::StaleSource)
    ));
    execute(&req(8, q.0, 0, &ticket)).unwrap();
    execute(&req(10, q.0, 0, &[])).unwrap();
    assert_eq!(
        read_data(&req(23, f.frame.0, 0, &[]), 128 << 20).unwrap(),
        initial
    );
    let next = Handle(u64at(
        &execute(&begin(18, index.0, 3, &f.manifest)).unwrap(),
        16,
    ));
    drive_reads(next.0, 3, &[], Some(&pages));
    let (_frame, _) = data(next.0, 3, 19);
}

#[test]
fn index_protocol_frontier_fallback_is_explicit_without_advancing_identity() {
    let _guard = test_processor_lock();
    let mut xy = Vec::new();
    for y in 0..32 {
        for x in 0..32 {
            let point = crate::geo_viewport::mercator_to_lonlat(
                -crate::geo_viewport::WEB_MERCATOR_MAX
                    + (x as f64 + 0.5) * 2. * crate::geo_viewport::WEB_MERCATOR_MAX / 32.,
                -crate::geo_viewport::WEB_MERCATOR_MAX
                    + (y as f64 + 0.5) * 2. * crate::geo_viewport::WEB_MERCATOR_MAX / 32.,
            );
            xy.extend([point.0, point.1]);
        }
    }
    let ids: Vec<u64> = (0..1024).map(|n| u64::MAX - n).collect();
    let col = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::Point,
        crs: GeoCrs::Epsg4326,
        xy: &xy,
        validity: &vec![1; 1024],
        feature_ids: Some(&ids),
        offsets0: &[],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let bytes = GeoChunk::encode(&col, None).unwrap();
    let mut m = GeoManifestBuilder::new();
    m.push(&GeoChunk::parse(&bytes, 96 << 20).unwrap()).unwrap();
    let f = finish_fixture(vec![bytes], m);
    let (index, pages) = build_index(&f, 32);
    assert_eq!(pages.len(), 1024);
    assert_eq!(u32at(&execute(&req(6, index.0, 1, &[])).unwrap(), 8), 11);
    let request = begin(18, index.0, 2, &f.manifest);
    let before = GeoProcessorLease::live_bytes();
    let fallback = execute(&request).unwrap();
    assert_eq!(u32at(&fallback, 8), 10);
    assert_eq!(u32at(&fallback, 48), 1);
    assert_eq!(u64at(&fallback, 16), index.0);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    let mut narrow = request.clone();
    put64(&mut narrow, 96, 8f64.to_bits());
    let q = Handle(u64at(&execute(&narrow).unwrap(), 16));
    let complete = drive_reads(q.0, 2, &[], Some(&pages));
    assert_eq!(u32at(&complete, 8), 12);
    assert_eq!(execute(&req(6, q.0, 2, &[])).unwrap(), complete);
}

#[test]
fn index_protocol_reduced_scene_parity_and_exact_membership_survive_owner_disposal() {
    let _guard = test_processor_lock();
    let f = fixture(10_000);
    let (index, pages) = build_index(&f, 16);
    execute(&begin(5, f.source.0, 2, &f.manifest)).unwrap();
    drive_reads(f.source.0, 2, &f.chunks, None);
    let query = Handle(u64at(
        &execute(&begin(18, index.0, 2, &f.manifest)).unwrap(),
        16,
    ));
    let complete = drive_reads(query.0, 2, &[], Some(&pages));
    assert_eq!(u32at(&complete, 184), 2);
    let (_ordinary, a) = data(f.source.0, 2, 11);
    let (frame, b) = data(query.0, 2, 19);
    assert_eq!(&a[32..56], &b[32..56]);
    assert_eq!(&a[64..], &b[64..]);
    let cell = with_scene_data(frame.0, 2, |borrow| {
        assert_eq!(borrow.snapshot.style_revision, 2);
        assert_eq!(borrow.result.visible_vertices, 40_000);
        let GeoPointOutput::Reduced(cells) = &borrow.result.output else {
            panic!("expected aggregate");
        };
        cells.iter().position(|c| c.count == 40_000).unwrap() as u32
    })
    .unwrap();
    drop(query);
    drop(index);
    drop(f.source);
    drop(f.frame);
    let mut payload = [0; 16];
    put32(&mut payload, 0, cell);
    put64(&mut payload, 8, 1_000_000);
    let members = Handle(u64at(
        &execute(&capped(req(12, frame.0, 2, &payload))).unwrap(),
        16,
    ));
    drive_reads(members.0, 2, &f.chunks, None);
    let page = Handle(u64at(
        &execute(&capped(req(13, members.0, 2, &[]))).unwrap(),
        16,
    ));
    let bytes = read_data(&req(23, page.0, 0, &[]), 128 << 20).unwrap();
    assert_eq!(u64at(&bytes, 32), 4);
    for row in 0..4 {
        assert_eq!(
            u64at(&bytes, HEADER + row * 32),
            if row % 2 == 0 { u64::MAX } else { 1 << 63 }
        );
        assert_eq!(u64at(&bytes, HEADER + row * 32 + 8), row as u64);
    }
}

#[test]
fn index_protocol_candidate_record_and_leaf_read_caps_admit_before_io() {
    let _guard = test_processor_lock();
    let f = fixture(600);
    let (index, pages) = build_index(&f, 16);
    let old = read_data(&req(23, f.frame.0, 0, &[]), 128 << 20).unwrap();
    let mut record_limited = begin(18, index.0, 2, &f.manifest);
    put64(&mut record_limited, 40, 1);
    let q = Handle(u64at(&execute(&record_limited).unwrap(), 16));
    assert!(matches!(
        execute(&req(6, q.0, 2, &[])),
        Err(SourceError::ResourceLimit)
    ));
    assert!(matches!(
        execute(&capped(req(19, q.0, 2, &style()))),
        Err(SourceError::StaleSource)
    ));
    drop(q);
    let mut read_limited = begin(18, index.0, 3, &f.manifest);
    put32(&mut read_limited, 56, 2);
    let before = GeoProcessorLease::live_bytes();
    let fallback = execute(&read_limited).unwrap();
    assert_eq!(u32at(&fallback, 8), 10);
    assert_eq!(u32at(&fallback, 48), 2);
    assert_eq!(u64at(&fallback, 16), index.0);
    assert_eq!(GeoProcessorLease::live_bytes(), before);
    // Two canonical chunks fit the actual source-session budget; three sidecar pages do not.
    let mut canonical = begin(5, f.source.0, 3, &f.manifest);
    put32(&mut canonical, 56, 2);
    execute(&canonical).unwrap();
    drive_reads(f.source.0, 3, &f.chunks, None);
    // The rejected index query did not consume its sequence/revision transition.
    let q = Handle(u64at(
        &execute(&begin(18, index.0, 3, &f.manifest)).unwrap(),
        16,
    ));
    drive_reads(q.0, 3, &[], Some(&pages));

    assert_eq!(
        read_data(&req(23, f.frame.0, 0, &[]), 128 << 20).unwrap(),
        old
    );
}
