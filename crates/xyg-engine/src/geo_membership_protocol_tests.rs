//! Independent typed membership/ownership proofs through the public protocol.
#[path = "geo_rows_protocol_tests.rs"]
mod rows_protocol_tests;
use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoError, GeoGeometry, GeoLimits};
use crate::geo_scale_protocol::{data_len, execute, read_data};
use crate::geo_source::{GeoChunk, GeoIntervals, GeoManifestBuilder, MAX_CHUNK_PEAK, SourceError};
use crate::geo_source_session::test_processor_lock;
use crate::geo_tile_cache::{
    GeoTileCache, GeoTileLimits, TILE_CACHE_PROCESS_BYTES, test_process_lock,
};
fn n32(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}
fn n64(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}
fn p32(b: &mut [u8], at: usize, n: u32) {
    b[at..at + 4].copy_from_slice(&n.to_le_bytes());
}
fn p64(b: &mut [u8], at: usize, n: u64) {
    b[at..at + 8].copy_from_slice(&n.to_le_bytes());
}
fn request(command: u32, handle: u64, sequence: u64, payload: &[u8]) -> Vec<u8> {
    let mut b = vec![0; 256];
    b[..4].copy_from_slice(b"XYGQ");
    p32(&mut b, 4, 1);
    p32(&mut b, 8, command);
    p64(&mut b, 16, handle);
    p64(&mut b, 24, sequence);
    p64(&mut b, 232, payload.len() as u64);
    b.extend(payload);
    b
}
fn budget(mut b: Vec<u8>, page: u32) -> Vec<u8> {
    for (at, n) in [(32, 128u64 << 20), (40, 1_000_000), (48, 128 << 20)] {
        p64(&mut b, at, n);
    }
    p32(&mut b, 56, 65536);
    p32(&mut b, 60, page);
    b
}
struct Handle(u64);
impl Drop for Handle {
    fn drop(&mut self) {
        let _ = execute(&request(10, self.0, 0, &[]));
    }
}
struct Fixture {
    source: Handle,
    chunks: Vec<Vec<u8>>,
}
fn drive(handle: u64, seq: u64, chunks: &[Vec<u8>]) -> Vec<u32> {
    let mut reads = Vec::new();
    loop {
        let out = execute(&request(6, handle, seq, &[])).unwrap();
        match n32(&out, 8) {
            1 => {
                let t = &out[64..160];
                let i = n32(t, 40);
                reads.push(i);
                let mut supplied = t.to_vec();
                supplied.extend(&chunks[i as usize]);
                execute(&request(7, handle, 0, &supplied)).unwrap();
                assert_eq!(n32(&execute(&request(6, handle, seq, &[])).unwrap(), 8), 2);
                execute(&request(8, handle, 0, t)).unwrap();
            }
            3 | 4 => return reads,
            code => panic!("unexpected state {code}"),
        }
    }
}
fn fixture(instant: Option<i64>) -> Fixture {
    fixture_with_vertices(instant, 9000)
}
fn fixture_with_vertices(instant: Option<i64>, vertices: u32) -> Fixture {
    let mut chunks = Vec::new();
    let mut builder = GeoManifestBuilder::new();
    for part in 0..2 {
        let xy = vec![0.; 4 * vertices as usize * 2];
        let offsets = [0, vertices, 2 * vertices, 3 * vertices, 4 * vertices];
        let column = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::MultiPoint,
            crs: GeoCrs::Epsg4326,
            xy: &xy,
            validity: &[1; 4],
            feature_ids: Some(&[u64::MAX, 7, 7, 1 << 63]),
            offsets0: &offsets,
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        let starts = [part * 10; 4];
        let ends = [part * 10 + 10; 4];
        let raw = GeoChunk::encode(
            &column,
            Some(GeoIntervals {
                starts: &starts,
                ends: &ends,
                start_validity: &[1; 4],
                end_validity: &[1; 4],
            }),
        )
        .unwrap();
        builder
            .push(&GeoChunk::parse(&raw, MAX_CHUNK_PEAK).unwrap())
            .unwrap();
        chunks.push(raw);
    }
    let manifest = builder.finish(u64::MAX).unwrap();
    let out = execute(&budget(request(4, 0, 0, &manifest.encode().unwrap()), 4096)).unwrap();
    let source = Handle(n64(&out, 16));
    assert_eq!(drive(source.0, 0, &chunks), [0, 1]);
    let mut begin = budget(request(5, source.0, 1, &[]), 4096);
    p32(&mut begin, 12, 1);
    p32(&mut begin, 64, 4326);
    p32(&mut begin, 72, 1);
    p32(&mut begin, 76, 1);
    p64(&mut begin, 104, 800f64.to_bits());
    p64(&mut begin, 112, 600f64.to_bits());
    begin[136..144].copy_from_slice(&manifest.digest());
    p64(&mut begin, 144, u64::MAX);
    p64(&mut begin, 152, u64::MAX);
    for at in [160, 168, 176, 184, 192] {
        p64(&mut begin, at, 1);
    }
    p64(&mut begin, 224, 200_000);
    if let Some(t) = instant {
        p32(&mut begin, 200, 1);
        p64(&mut begin, 208, t as u64);
    }
    execute(&begin).unwrap();
    drive(source.0, 1, &chunks);
    Fixture { source, chunks }
}
fn create(source: u64, cursor: Option<&[u8]>, page: u32) -> Vec<u8> {
    let mut p = vec![0; 16];
    p32(&mut p, 4, u32::from(cursor.is_some()));
    p64(&mut p, 8, 200_000);
    if let Some(c) = cursor {
        p.extend(c);
    }
    budget(request(12, source, 1, &p), page)
}
fn prepare(handle: u64) -> Vec<u8> {
    budget(request(13, handle, 1, &[]), 4096)
}
fn style(source: u64) -> Vec<u8> {
    let mut p = vec![0; 48];
    p[..4].copy_from_slice(&[255, 0, 0, 255]);
    p64(&mut p, 16, 6f64.to_bits());
    p64(&mut p, 24, 1f64.to_bits());
    budget(request(11, source, 1, &p), 4096)
}
#[test]
fn three_pages_full_ids_multipoint_union_immutable_data_and_exact_cursor() {
    let _source = test_processor_lock();
    let _tile = test_process_lock();
    let fixture = fixture(None);
    let mut cursor = None;
    let mut rows = Vec::new();
    let mut sizes = Vec::new();
    let mut first_cursor = None;
    loop {
        let out = execute(&create(fixture.source.0, cursor.as_deref(), 3)).unwrap();
        let member = Handle(n64(&out, 16));
        drive(member.0, 1, &fixture.chunks);
        let out = execute(&prepare(member.0)).unwrap();
        let data = Handle(n64(&out, 16));
        let read = request(23, data.0, 0, &[]);
        for _ in 0..3 {
            assert_eq!(data_len(&read, 128 << 20).unwrap(), n64(&out, 32) as usize);
        }
        let packet = read_data(&read, 128 << 20).unwrap();
        assert_eq!(&packet[..4], b"XYGZ");
        assert_eq!(n32(&packet, 8), 2);
        assert_eq!(n64(&packet, 16), member.0);
        assert_eq!(n64(&packet, 24), 1);
        assert_eq!(n64(&packet, 88 + 32), u64::MAX);
        assert_eq!(n64(&packet, 88 + 8), u64::MAX);
        let count = n64(&packet, 32) as usize;
        let cursor_bytes = n32(&packet, 76) as usize;
        sizes.push(count);
        assert!(count <= 3);
        assert_eq!(packet.len(), 256 + cursor_bytes + count * 32);
        for i in 0..count {
            let at = 256 + cursor_bytes + i * 32;
            rows.push((
                n64(&packet, at),
                n64(&packet, at + 8),
                n32(&packet, at + 16),
                n32(&packet, at + 20),
            ));
            assert!(packet[at + 24..at + 32].iter().all(|&v| v == 0));
        }
        cursor = if n32(&packet, 72) == 1 {
            Some(packet[256..464].to_vec())
        } else {
            None
        };
        if first_cursor.is_none() {
            first_cursor = cursor.clone();
        }
        drop(member); // Packet survives its session: independently owned Data handle.
        assert_eq!(read_data(&read, 128 << 20).unwrap(), packet);
        assert_eq!(read_data(&read, 128 << 20), Err(SourceError::ResourceLimit));
        if cursor.is_none() {
            break;
        }
    }
    assert_eq!(sizes, [3, 3, 2]);
    assert_eq!(
        rows.iter().map(|r| r.1).collect::<Vec<_>>(),
        [0, 1, 2, 3, 4, 5, 6, 7]
    );
    assert_eq!(rows[0].0, u64::MAX);
    assert_eq!(rows[3].0, 1 << 63);
    assert_eq!(rows.iter().filter(|r| r.0 == 7).count(), 4);
    let original = first_cursor.unwrap();
    let mut wrong = original.clone();
    p64(&mut wrong, 40, 2);
    assert_eq!(
        execute(&create(fixture.source.0, Some(&wrong), 3)).err(),
        Some(SourceError::StaleSource)
    );
    for at in [156, 164, 200] {
        let mut bad = original.clone();
        bad[at] = 1;
        assert_eq!(
            execute(&create(fixture.source.0, Some(&bad), 3)).err(),
            Some(SourceError::InvalidFrame)
        );
    }
}
#[test]
fn temporal_pruning_and_retired_membership_ticket_protocol_lifecycle() {
    let _source = test_processor_lock();
    let _tile = test_process_lock();
    let fixture = fixture(Some(10));
    let out = execute(&create(fixture.source.0, None, 4096)).unwrap();
    let member = Handle(n64(&out, 16));
    let out = execute(&request(6, member.0, 1, &[])).unwrap();
    assert_eq!(n32(&out, 8), 1);
    let ticket = &out[64..160];
    assert_eq!(n32(ticket, 40), 1);
    assert_eq!(
        execute(&request(6, member.0, 0, &[])).err(),
        Some(SourceError::StaleSource)
    );
    execute(&request(9, member.0, 0, &[])).unwrap();
    assert_eq!(execute(&request(6, member.0, 1, &[])).unwrap(), out);
    execute(&request(9, member.0, 1, &[])).unwrap();
    let disposed = execute(&request(10, member.0, 0, &[])).unwrap();
    assert_eq!(n32(&disposed, 8), 2);
    let mut supplied = ticket.to_vec();
    supplied.extend(&fixture.chunks[1]);
    assert_eq!(
        execute(&request(7, member.0, 0, &supplied)).err(),
        Some(SourceError::StaleSource)
    );
    execute(&request(8, member.0, 0, ticket)).unwrap();
    execute(&request(10, member.0, 0, &[])).unwrap();
    let out = execute(&create(fixture.source.0, None, 4096)).unwrap();
    let member = Handle(n64(&out, 16));
    assert_eq!(drive(member.0, 1, &fixture.chunks), [1]);
    let out = execute(&prepare(member.0)).unwrap();
    let data = Handle(n64(&out, 16));
    let packet = read_data(&request(23, data.0, 0, &[]), 128 << 20).unwrap();
    assert_eq!(n64(&packet, 32), 4);
    assert_eq!(n64(&packet, 256 + 8), 4);
}
#[test]
fn failed_first_scene_derived_reservation_releases_empty_cache_and_recovers() {
    let _source = test_processor_lock();
    let _tile = test_process_lock();
    let fixture = fixture(None);
    let observer = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
    let before = observer.stats().process_charged_bytes;
    // Leave exactly enough to create the cache, then force its derived reserve
    // to fail. The failed command must release that new cache metadata charge.
    let blocker = observer
        .reserve_derived(TILE_CACHE_PROCESS_BYTES - before - (1 << 20))
        .unwrap();
    let pressure = observer.stats().process_charged_bytes;
    let processor_before = crate::geo_source_session::GeoProcessorLease::live_bytes();
    assert_eq!(
        execute(&style(fixture.source.0)).err(),
        Some(SourceError::Geometry(GeoError::ResourceLimit))
    );
    assert_eq!(observer.stats().process_charged_bytes, pressure);
    assert_eq!(
        crate::geo_source_session::GeoProcessorLease::live_bytes(),
        processor_before
    );
    drop(blocker);
    let out = execute(&style(fixture.source.0)).unwrap();
    let data = Handle(n64(&out, 16));
    assert!(read_data(&request(23, data.0, 0, &[]), 128 << 20).is_ok());
    drop(data);
    assert_eq!(observer.stats().process_charged_bytes, before);
}

#[test]
fn hit_data_binds_reduced_cell_key_and_retains_independent_owned_packet() {
    let _cpu = test_processor_lock();
    let _tiles = test_process_lock();
    let f = fixture(None);
    let mut payload = vec![0; 80];
    payload[..8].fill(255);
    p64(&mut payload, 8, 1f64.to_bits());
    p64(&mut payload, 16, 6f64.to_bits());
    p64(&mut payload, 24, 1f64.to_bits());
    p64(&mut payload, 48, 400f64.to_bits());
    p64(&mut payload, 56, 300f64.to_bits());
    p32(&mut payload, 76, 4096);
    let scene = Handle(n64(
        &execute(&budget(request(11, f.source.0, 1, &payload[..48]), 4096)).unwrap(),
        16,
    ));
    let out = execute(&budget(request(14, f.source.0, 1, &payload), 4096)).unwrap();
    let data = Handle(n64(&out, 16));
    let read = request(23, data.0, 0, &[]);
    let bytes = read_data(&read, 128 << 20).unwrap();
    assert_eq!(bytes.len(), 304);
    assert_eq!(n32(&bytes, 8), 3);
    assert_eq!(n64(&bytes, 32), 1);
    assert_eq!(n32(&bytes, 256), 1);
    assert_eq!(n64(&bytes, 296), 72000);
    assert!(bytes[260..288].iter().all(|&v| v == 0));
    assert_eq!(n64(&bytes, 96), u64::MAX); // authentic source generation in full key
    assert_eq!(n64(&bytes, 104), 8); // source row population, not vertex count
    let cell = n32(&bytes, 288);
    let mut member = vec![0; 16];
    p32(&mut member, 0, cell);
    p64(&mut member, 8, 1_000_000);
    let page = Handle(n64(
        &execute(&budget(request(12, f.source.0, 1, &member), 4096)).unwrap(),
        16,
    ));
    assert_eq!(drive(page.0, 1, &f.chunks), [0, 1]);
    let mut bad = payload.clone();
    bad[33] = 1;
    assert!(matches!(
        execute(&budget(request(14, f.source.0, 1, &bad), 4096)),
        Err(SourceError::InvalidFrame)
    ));
    assert!(matches!(
        execute(&budget(request(14, f.source.0, 2, &payload), 4096)),
        Err(SourceError::StaleSource)
    ));
    drop(page);
    drop(scene);
    drop(f);
    assert_eq!(read_data(&read, 128 << 20).unwrap(), bytes);
    assert!(matches!(
        read_data(&read, 128 << 20),
        Err(SourceError::ResourceLimit)
    ));
}

#[test]
fn painted_style_identity_rejects_same_revision_mutation_then_accepts_new_publication() {
    let _cpu = test_processor_lock();
    let _tiles = test_process_lock();
    let f = fixture(None);
    let original = style(f.source.0);
    let old = Handle(n64(&execute(&original).unwrap(), 16));
    let oldread = request(23, old.0, 0, &[]);
    let bytes = read_data(&oldread, 128 << 20).unwrap();
    let mut changed = original.clone();
    changed[256] = 0;
    assert!(matches!(execute(&changed), Err(SourceError::StaleSource)));
    assert_eq!(read_data(&oldread, 128 << 20).unwrap(), bytes);
    let done = execute(&request(6, f.source.0, 1, &[])).unwrap();
    let mut begin = budget(request(5, f.source.0, 2, &[]), 4096);
    p32(&mut begin, 12, 1);
    p32(&mut begin, 64, 4326);
    p32(&mut begin, 72, 1);
    p32(&mut begin, 76, 1);
    p64(&mut begin, 104, 800f64.to_bits());
    p64(&mut begin, 112, 600f64.to_bits());
    begin[136..144].copy_from_slice(&done[40..48]);
    p64(&mut begin, 144, u64::MAX);
    p64(&mut begin, 152, u64::MAX);
    for at in [160, 168, 176, 184, 192] {
        p64(&mut begin, at, if at == 184 { 2 } else { 1 });
    }
    p64(&mut begin, 224, 200_000);
    execute(&begin).unwrap();
    drive(f.source.0, 2, &f.chunks);
    p64(&mut changed, 24, 2);
    let mut failed = changed.clone();
    p64(&mut failed, 256 + 16, f64::MAX.to_bits());
    assert!(execute(&failed).is_err());
    let mut hit = original[256..].to_vec();
    hit.resize(80, 0);
    p64(&mut hit, 48, 400f64.to_bits());
    p64(&mut hit, 56, 300f64.to_bits());
    p32(&mut hit, 76, 1);
    let oldhit = Handle(n64(
        &execute(&budget(request(14, old.0, 1, &hit), 4096)).unwrap(),
        16,
    ));
    let hitbytes = read_data(&request(23, oldhit.0, 0, &[]), 128 << 20).unwrap();
    assert_eq!(n64(&hitbytes, 296), 72000);
    assert_eq!(n64(&hitbytes, 128), 1); // old style revision
    let new = Handle(n64(&execute(&changed).unwrap(), 16));
    assert!(read_data(&request(23, new.0, 0, &[]), 128 << 20).is_ok());
    execute(&request(10, f.source.0, 0, &[])).unwrap();
    let after_dispose = Handle(n64(
        &execute(&budget(request(14, old.0, 1, &hit), 4096)).unwrap(),
        16,
    ));
    assert_eq!(
        read_data(&request(23, after_dispose.0, 0, &[]), 128 << 20).unwrap(),
        hitbytes
    );
    let mut membership = vec![0; 16];
    p32(&mut membership, 0, n32(&hitbytes, 288));
    p64(&mut membership, 8, 200_000);
    let member = Handle(n64(
        &execute(&budget(request(12, old.0, 1, &membership), 4096)).unwrap(),
        16,
    ));
    assert_eq!(drive(member.0, 1, &f.chunks), [0, 1]);
    let page = Handle(n64(&execute(&prepare(member.0)).unwrap(), 16));
    let pagebytes = read_data(&request(23, page.0, 0, &[]), 128 << 20).unwrap();
    assert_eq!(n64(&pagebytes, 32), 8);
    assert_eq!(n64(&pagebytes, 256), u64::MAX);
}

#[test]
fn direct_hit_packet_preserves_literal_ids_source_rows_and_overlapping_vertices() {
    let _cpu = test_processor_lock();
    let _tiles = test_process_lock();
    let f = fixture_with_vertices(None, 1);
    let frame = style(f.source.0);
    let scene = Handle(n64(&execute(&frame).unwrap(), 16));
    let mut p = frame[256..].to_vec();
    p.resize(80, 0);
    p64(&mut p, 48, 400f64.to_bits());
    p64(&mut p, 56, 300f64.to_bits());
    p32(&mut p, 72, 1);
    p32(&mut p, 76, 8);
    let data = Handle(n64(
        &execute(&budget(request(14, f.source.0, 1, &p), 4096)).unwrap(),
        16,
    ));
    let bytes = read_data(&request(23, data.0, 0, &[]), 128 << 20).unwrap();
    assert_eq!(bytes.len(), 256 + 8 * 48);
    assert_eq!(n64(&bytes, 32), 8);
    let ids = [u64::MAX, 7, 7, 1 << 63];
    for i in 0..8 {
        let at = 256 + i * 48;
        let row = 7 - i;
        assert_eq!(n32(&bytes, at), 0);
        assert_eq!(n64(&bytes, at + 8), ids[row % 4]);
        assert_eq!(n64(&bytes, at + 16), row as u64);
        assert_eq!(n32(&bytes, at + 24), row as u32 / 4);
        assert_eq!(n32(&bytes, at + 28), row as u32 % 4);
        assert!(bytes[at + 32..at + 48].iter().all(|&n| n == 0));
    }
    p32(&mut p, 76, 7);
    assert!(matches!(
        execute(&budget(request(14, f.source.0, 1, &p), 4096)),
        Err(SourceError::ResourceLimit)
    ));
    assert_eq!(
        read_data(&request(23, data.0, 0, &[]), 128 << 20).unwrap(),
        bytes
    );
    drop(scene);
}

#[path = "geo_frame_lease_tests.rs"]
mod frame_lease_tests;
