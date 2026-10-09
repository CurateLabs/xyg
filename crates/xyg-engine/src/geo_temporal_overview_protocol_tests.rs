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
#[test]
fn overview_protocol_rejects_full_and_empty_selected_authority_without_admission() {
    let _lock = test_processor_lock();
    let baseline = crate::geo_source_session::GeoProcessorLease::live_bytes();
    for ids in [vec![u64::MAX, u64::MAX], Vec::new()] {
        let chunks = [chunk(u64::MAX, -5, 0.)];
        let (ordinary, manifest) = source_frame(&chunks);
        let (builder, bytes) = finish_manifest(&chunks);
        let source = u64_at(
            &execute(&with_budget(request(4, 0, 0, &bytes))).unwrap(),
            16,
        );
        assert_eq!(drive(source, 0, &chunks).0, 3);
        execute(&begin(source, 1, &manifest, None, 1000000)).unwrap();
        assert_eq!(drive(source, 1, &chunks).0, 4);
        let mut binding = [0; 16];
        p64(&mut binding, 0, 777);
        p64(&mut binding, 8, u64::MAX);
        let scope = u64_at(
            &execute(&with_budget(request(32, ordinary, 1, &binding))).unwrap(),
            16,
        );
        let issue = || {
            let mut payload = vec![0; 24];
            p64(&mut payload, 0, 2);
            payload[8..12].copy_from_slice(&[0, 255, 0, 255]);
            p64(&mut payload, 16, ids.len() as u64);
            for id in &ids {
                payload.extend(id.to_le_bytes());
            }
            u64_at(
                &execute(&with_budget(request(33, scope, 0, &payload))).unwrap(),
                16,
            )
        };
        let selected_begin = |state: u64, sequence| {
            let mut b = begin(source, sequence, &manifest, None, 1000000);
            p32(&mut b, 8, 35);
            p64(&mut b, 192, 2);
            p64(&mut b, 232, 8);
            b.extend(state.to_le_bytes());
            b
        };
        execute(&selected_begin(issue(), 2)).unwrap();
        assert_eq!(drive(source, 2, &chunks).0, 4);
        let selected = u64_at(&execute(&scene_request(source, 2)).unwrap(), 16);
        let old = read_data(&request(23, selected, 0, &[]), 128 << 20).unwrap();
        assert_eq!(u32_at(&old, 4), 2);
        let issued = issue();
        let live = crate::geo_source_session::GeoProcessorLease::live_bytes();
        let reject = with_budget(request(27, selected, 2, &1000000u64.to_le_bytes()));
        let answer = execute(&reject).unwrap();
        assert_eq!(u32_at(&answer, 8), 17);
        assert_eq!(u64_at(&answer, 16), selected);
        assert_eq!(u64_at(&answer, 24), 2);
        assert!(answer[32..].iter().all(|b| *b == 0));
        assert_eq!(execute(&reject).unwrap(), answer);
        let mut low_budget = reject.clone();
        p64(&mut low_budget, 32, 4096);
        assert_eq!(execute(&low_budget).unwrap(), answer);
        assert_eq!(
            crate::geo_source_session::GeoProcessorLease::live_bytes(),
            live
        );
        assert_eq!(
            read_data(&request(23, selected, 0, &[]), 128 << 20).unwrap(),
            old
        );
        // Rejection neither consumes independently issued intent nor advances source history.
        execute(&selected_begin(issued, 3)).unwrap();
        assert_eq!(drive(source, 3, &chunks).0, 4);
        let ordinary_build = u64_at(
            &execute(&with_budget(request(
                27,
                ordinary,
                1,
                &1000000u64.to_le_bytes(),
            )))
            .unwrap(),
            16,
        );
        close(ordinary_build, 1);
        close(selected, 0);
        close(source, 0);
        close(scope, 0);
        close(ordinary, 0);
        drop(builder);
    }
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        baseline
    );
}
#[test]
fn overview_protocol_exact_counts_scene_and_old_data_survive_source_index_disposal() {
    let _lock = test_processor_lock();
    let before = crate::geo_source_session::GeoProcessorLease::live_bytes();
    let chunks = [
        chunk(u64::MAX, -5, -179.),
        chunk(u64::MAX, 0, 179.),
        chunk(1 << 63, 10, 0.),
    ];
    let (frame, manifest) = source_frame(&chunks);
    let (index, storage) = build(frame, &chunks, true);
    let query = finish_query(index, &manifest, Some(0), 7, &storage);
    let data_reply = execute(&with_budget(request(29, query, 7, &[]))).unwrap();
    assert_eq!(u32_at(&data_reply, 8), 16);
    let data = u64_at(&data_reply, 16);
    close(query, 7);
    close(index, 1);
    assert_eq!(
        read_data(&request(23, data, 6, &[]), 128 << 20),
        Err(SourceError::StaleSource)
    );
    let read = request(23, data, 7, &[]);
    let bytes = read_data(&read, 128 << 20).unwrap();
    assert_eq!(&bytes[..4], b"XYOV");
    assert_eq!(u32_at(&bytes, 8), 3);
    assert_eq!(u32_at(&bytes, 12), 16);
    assert_eq!(u64_at(&bytes, 56), u64::MAX);
    assert_eq!(u64_at(&bytes, 80), u64::MAX);
    assert_eq!(u32_at(&bytes, 224), 1);
    assert_eq!(u64_at(&bytes, 232), 0);
    let counts: Vec<u64> = bytes[256..2304]
        .chunks_exact(8)
        .map(|v| u64::from_le_bytes(v.try_into().unwrap()))
        .collect();
    assert_eq!(counts.iter().sum::<u64>(), 2);
    assert_eq!(counts[128], 1);
    assert_eq!(counts[143], 1);
    let scene = &bytes[2304..];
    let doc = crate::scene::SceneDocument::decode(scene).unwrap();
    assert!(!doc.interaction_records().is_empty());
    // At zoom zero the 512px world is centred in this 800px viewport.
    // Row eight starts at the equator: independently expected cell corners.
    for expected in [[144., 300.], [656., 300.]] {
        assert!(
            doc.interaction_records()
                .iter()
                .any(|r| (r.coordinates[0] - expected[0]).abs() < 1e-6
                    && (r.coordinates[1] - expected[1]).abs() < 1e-6)
        );
    }

    assert!(
        scene
            .windows(crate::geo_temporal_overview_scene::LABEL.len())
            .any(|w| w == crate::geo_temporal_overview_scene::LABEL.as_bytes())
    );
    assert!(
        doc.interaction_records()
            .iter()
            .all(|r| r.stable_id == 128 || r.stable_id == 143)
    );
    assert!(
        doc.interaction_records()
            .iter()
            .all(|r| r.coordinates.iter().all(|v| v.is_finite()))
    );
    crate::geo_scale_protocol::with_overview_data(data, 7, |scene, result, _| {
        assert_eq!(result.counts().iter().sum::<u64>(), 2);
        assert!(!result.final_result());
        assert!(result.temporal_exact() && result.data_space());
        assert!(!scene.is_empty());
        Ok(())
    })
    .unwrap();
    assert!(execute(&request(14, data, 7, &[0; 64])).is_err());
    assert_eq!(data_len(&read, 128 << 20).unwrap(), bytes.len());
    read_data(&read, 128 << 20).unwrap();
    assert_eq!(read_data(&read, 128 << 20), Err(SourceError::ResourceLimit));
    close(data, 0);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        before
    );
}
#[test]
fn overview_protocol_cancelled_write_requires_exact_ack_and_retains_old_frame() {
    let _lock = test_processor_lock();
    let chunks = [chunk(u64::MAX, 0, 0.)];
    let (frame, _) = source_frame(&chunks);
    let handle = u64_at(
        &execute(&with_budget(request(27, frame, 1, &100u64.to_le_bytes()))).unwrap(),
        16,
    );
    let read = step(handle, 1);
    let t = &read[64..192];
    let mut p = t.to_vec();
    p.extend(&chunks[0]);
    execute(&request(7, handle, 1, &p)).unwrap();
    execute(&request(8, handle, 1, t)).unwrap();
    let write = step(handle, 1);
    assert_eq!(u32_at(&write, 8), 7);
    let t = &write[64..192];
    let request_bytes = request(30, handle, 1, t);
    let mut forged = t.to_vec();
    forged[8] ^= 1;
    assert_eq!(
        data_len(&request(30, handle, 1, &forged), 128 << 20),
        Err(SourceError::StaleSource)
    );
    assert_eq!(
        read_data(&request_bytes, 128 << 20).unwrap(),
        read_data(&request_bytes, 128 << 20).unwrap()
    );
    assert_eq!(
        read_data(&request_bytes, 128 << 20),
        Err(SourceError::ResourceLimit)
    );
    execute(&request(9, handle, 1, &[])).unwrap();
    assert_eq!(
        u32_at(&execute(&request(10, handle, 1, &[])).unwrap(), 8),
        2
    );
    assert_eq!(
        execute(&request(31, handle, 1, &forged)),
        Err(SourceError::StaleSource)
    );
    execute(&request(31, handle, 1, t)).unwrap();
    close(handle, 1);
    assert!(
        !read_data(&request(23, frame, 0, &[]), 128 << 20)
            .unwrap()
            .is_empty()
    );
    close(frame, 0);
}
#[test]
fn overview_protocol_bad_page_and_invalid_snapshot_cannot_replace_previous_typed_data() {
    let _lock = test_processor_lock();
    let chunks = [chunk(u64::MAX, 0, 0.)];
    let (frame, manifest) = source_frame(&chunks);
    let (index, storage) = build(frame, &chunks, false);
    let query = finish_query(index, &manifest, None, 2, &storage);
    let data = u64_at(
        &execute(&with_budget(request(29, query, 2, &[]))).unwrap(),
        16,
    );
    let before = read_data(&request(23, data, 2, &[]), 128 << 20).unwrap();
    let empty_query = finish_query(index, &manifest, Some(20), 4, &storage);
    let empty_data = u64_at(
        &execute(&with_budget(request(29, empty_query, 4, &[]))).unwrap(),
        16,
    );
    let empty = read_data(&request(23, empty_data, 4, &[]), 128 << 20).unwrap();
    assert!(empty[256..2304].iter().all(|v| *v == 0));
    assert!(
        crate::scene::SceneDocument::decode(&empty[2304..])
            .unwrap()
            .interaction_records()
            .is_empty()
    );
    close(empty_data, 0);
    close(empty_query, 4);
    let mut stale = query_request(index, &manifest, Some(1), 3);
    stale[136] ^= 1;
    assert_eq!(execute(&stale), Err(SourceError::StaleSource));
    let mut low = query_request(index, &manifest, Some(1), 3);
    p32(&mut low, 56, 1);
    assert_eq!(execute(&low), Err(SourceError::ResourceLimit));
    let q = u64_at(
        &execute(&query_request(index, &manifest, Some(1), 3)).unwrap(),
        16,
    );
    let state = step(q, 3);
    assert_eq!(u32_at(&state, 8), 1);
    let t = &state[64..192];
    let mut corrupt = storage[&(u64_at(t, 8), u64_at(t, 40))].clone();
    corrupt[0] ^= 1;
    let mut payload = t.to_vec();
    payload.extend(corrupt);
    assert!(execute(&request(7, q, 3, &payload)).is_err());
    execute(&request(8, q, 3, t)).unwrap();
    assert!(execute(&with_budget(request(29, q, 3, &[]))).is_err());
    close(q, 3);
    assert_eq!(
        read_data(&request(23, data, 2, &[]), 128 << 20).unwrap(),
        before
    );
    close(data, 0);
    close(query, 2);
    close(index, 1);
    close(frame, 0);
}

#[test]
fn overview_protocol_multipoint_population_and_projected_scene_match_both_camera_crss() {
    let _lock = test_processor_lock();
    for crs in [GeoCrs::Epsg4326, GeoCrs::Epsg3857] {
        let xy: Vec<_> = [-179., 0., 179., 0., 0., 0.]
            .chunks_exact(2)
            .flat_map(|p| {
                if crs == GeoCrs::Epsg3857 {
                    let (x, y) = crate::geo_viewport::lonlat_to_mercator(p[0], p[1]);
                    [x, y]
                } else {
                    [p[0], p[1]]
                }
            })
            .collect();
        let column = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::MultiPoint,
            crs,
            xy: &xy,
            validity: &[1, 0],
            feature_ids: Some(&[u64::MAX, 1 << 63]),
            offsets0: &[0, 3, 3],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        let bytes = GeoChunk::encode(
            &column,
            Some(GeoIntervals {
                starts: &[i64::MIN, i64::MIN],
                ends: &[i64::MAX, i64::MAX],
                start_validity: &[0, 1],
                end_validity: &[0, 1],
            }),
        )
        .unwrap();
        let chunks = [bytes];
        let (frame, manifest) = source_frame(&chunks);
        let (index, storage) = build(frame, &chunks, false);
        close(frame, 0);
        for camera_crs in [4326, 3857] {
            for (wrap, pitch) in [(0, -60.), (1, 60.)] {
                let mut q = query_request(index, &manifest, None, 10);
                p32(&mut q, 64, camera_crs);
                p32(&mut q, 12, wrap);
                p64(&mut q, 120, 45f64.to_bits());
                p64(&mut q, 128, f64::to_bits(pitch));
                p32(&mut q, 200, 2);
                p64(&mut q, 208, i64::MIN as u64);
                p64(&mut q, 216, i64::MAX as u64);
                let query = u64_at(&execute(&q).unwrap(), 16);
                loop {
                    let state = step(query, 10);
                    if u32_at(&state, 8) == 14 {
                        break;
                    }
                    assert_eq!(u32_at(&state, 8), 1);
                    let t = &state[64..192];
                    let mut payload = t.to_vec();
                    payload.extend(&storage[&(u64_at(t, 8), u64_at(t, 40))]);
                    execute(&request(7, query, 10, &payload)).unwrap();
                    execute(&request(8, query, 10, t)).unwrap();
                }
                let data = u64_at(
                    &execute(&with_budget(request(29, query, 10, &[]))).unwrap(),
                    16,
                );
                let bytes = read_data(&request(23, data, 10, &[]), 128 << 20).unwrap();
                assert_eq!(
                    bytes[256..2304]
                        .chunks_exact(8)
                        .map(|v| u64::from_le_bytes(v.try_into().unwrap()))
                        .sum::<u64>(),
                    3
                );
                assert_eq!(u32_at(&bytes, 224), 2);
                assert_eq!(u64_at(&bytes, 232), i64::MIN as u64);
                assert_eq!(u64_at(&bytes, 240), i64::MAX as u64);
                let scene = crate::scene::SceneDocument::decode(&bytes[2304..]).unwrap();
                assert!(
                    scene
                        .interaction_records()
                        .iter()
                        .all(|r| r.coordinates.iter().all(|v| v.is_finite()))
                );
                assert!(
                    scene
                        .interaction_records()
                        .iter()
                        .all(|r| [128, 136, 143].contains(&r.stable_id))
                );
                close(data, 0);
                close(query, 10);
            }
        }
        close(index, 1);
    }
}

#[test]
fn overview_protocol_sessions_and_data_use_existing_shared_caps_and_recover_after_drop() {
    let _lock = test_processor_lock();
    let chunks = [chunk(u64::MAX, 0, 0.)];
    let (frame, manifest) = source_frame(&chunks);
    let (index, storage) = build(frame, &chunks, false);
    close(frame, 0);
    let queries: Vec<_> = (1..=8)
        .map(|seq| finish_query(index, &manifest, None, seq, &storage))
        .collect();
    assert_eq!(
        execute(&query_request(index, &manifest, None, 9)),
        Err(SourceError::ResourceLimit)
    );
    // Eight overview query sessions also prevent creation of an ordinary source session.
    let bytes = manifest.encode().unwrap();
    assert_eq!(
        execute(&with_budget(request(4, 0, 0, &bytes))),
        Err(SourceError::ResourceLimit)
    );
    for (seq, q) in queries.into_iter().enumerate() {
        close(q, seq as u64 + 1);
    }
    let query = finish_query(index, &manifest, None, 10, &storage);
    let data: Vec<_> = (0..8)
        .map(|_| {
            u64_at(
                &execute(&with_budget(request(29, query, 10, &[]))).unwrap(),
                16,
            )
        })
        .collect();
    assert_eq!(
        execute(&with_budget(request(29, query, 10, &[]))),
        Err(SourceError::ResourceLimit)
    );
    close(data[0], 0);
    let replacement = u64_at(
        &execute(&with_budget(request(29, query, 10, &[]))).unwrap(),
        16,
    );
    close(replacement, 0);
    for handle in data.into_iter().skip(1) {
        close(handle, 0);
    }
    close(query, 10);
    close(index, 1);
}
