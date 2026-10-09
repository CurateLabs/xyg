//! Actual public binary-protocol fixtures; no mixed registry insertion or forged authority.
use super::*;
use crate::geo::{GeoColumn, GeoDescriptor, GeoGeometry, GeoLimits};
use crate::geo_source::{GeoChunk, GeoIntervals};
use crate::scene::{SceneDocument, SceneRecordKind};
const BUDGET: usize = 128 << 20;
fn source_cmd(cmd: u32, handle: u64, seq: u64, payload: &[u8]) -> Vec<u8> {
    let mut b = source_request(cmd, handle, seq, BUDGET).to_vec();
    p64(&mut b, 232, payload.len() as u64);
    b.extend_from_slice(payload);
    b
}
fn tile_cmd(cmd: u32, handle: u64, epoch: u64, view: u64, payload: &[u8]) -> Vec<u8> {
    let mut b = vec![0; 128];
    b[..4].copy_from_slice(b"XYGT");
    p32(&mut b, 4, 1);
    p32(&mut b, 8, cmd);
    p64(&mut b, 16, handle);
    p64(&mut b, 24, epoch);
    p64(&mut b, 32, view);
    if matches!(cmd, 2 | 6 | 21 | 22) {
        p64(&mut b, 40, BUDGET as u64);
    }
    p64(&mut b, 48, payload.len() as u64);
    b.extend_from_slice(payload);
    b
}
fn mixed_cmd(cmd: u32, handle: u64, nonce: u64) -> Vec<u8> {
    let mut b = vec![0; HEADER];
    b[..4].copy_from_slice(b"XYMX");
    p32(&mut b, 4, 1);
    p32(&mut b, 8, cmd);
    p64(&mut b, 16, handle);
    p64(&mut b, 24, nonce);
    if matches!(cmd, 2 | 6 | 20) {
        p64(&mut b, 32, BUDGET as u64);
    }
    b
}
fn column(x: f64, id: u64) -> GeoColumn {
    GeoColumn::from_descriptor(GeoDescriptor {
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
    .unwrap()
}
struct Owner {
    handle: u64,
    kind: u32,
}
impl Drop for Owner {
    fn drop(&mut self) {
        match self.kind {
            0 => {
                let _ = crate::geo_scale_protocol::execute(&source_cmd(10, self.handle, 0, &[]));
            }
            1 => {
                let _ = crate::geo_tile_protocol::execute(&tile_cmd(10, self.handle, 0, 0, &[]));
            }
            2 => {
                let _ = execute(&mixed_cmd(5, self.handle, 0));
            }
            3 => {
                let _ = crate::geo_snapshot_protocol::execute(&snapshot_cmd(3, self.handle, 0));
            }
            _ => unreachable!(),
        }
    }
}
fn source_execute(b: &[u8]) -> [u8; HEADER] {
    crate::geo_scale_protocol::execute(b).unwrap()
}
fn drive(handle: u64, seq: u64, chunks: &[Vec<u8>]) {
    loop {
        let b = source_execute(&source_cmd(6, handle, seq, &[]));
        if u32at(&b, 8) != 1 {
            assert!(matches!(u32at(&b, 8), 3 | 4));
            return;
        }
        let ticket = &b[64..160];
        let mut payload = ticket.to_vec();
        payload.extend_from_slice(&chunks[u32at(ticket, 40) as usize]);
        source_execute(&source_cmd(7, handle, 0, &payload));
        source_execute(&source_cmd(8, handle, 0, ticket));
    }
}
fn source_frame() -> (Owner, Vec<Owner>) {
    let valid = [1];
    let start = [i64::MIN];
    let end = [i64::MIN + 10];
    let chunks = [GeoChunk::encode(
        &column(0., u64::MAX),
        Some(GeoIntervals {
            starts: &start,
            ends: &end,
            start_validity: &valid,
            end_validity: &valid,
        }),
    )
    .unwrap()];
    let builder = Owner {
        handle: u64at(&source_execute(&source_cmd(1, 0, 0, &[])), 16),
        kind: 0,
    };
    source_execute(&source_cmd(2, builder.handle, 0, &chunks[0]));
    let mut finish = source_cmd(3, builder.handle, 0, &[]);
    p64(&mut finish, 144, u64::MAX);
    source_execute(&finish);
    let manifest =
        crate::geo_scale_protocol::read_data(&source_cmd(21, builder.handle, 0, &[]), BUDGET)
            .unwrap();
    let source = Owner {
        handle: u64at(&source_execute(&source_cmd(4, 0, 0, &manifest)), 16),
        kind: 0,
    };
    drive(source.handle, 0, &chunks);
    let mut begin = source_cmd(5, source.handle, 1, &[]);
    p32(&mut begin, 64, 4326);
    p32(&mut begin, 72, 32768);
    p32(&mut begin, 76, 1);
    p64(&mut begin, 104, 64f64.to_bits());
    p64(&mut begin, 112, 64f64.to_bits());
    // Take the independently validated manifest digest from the source wire header.
    let validated = crate::geo_source::GeoSourceManifest::validate(
        &manifest,
        &mut |r: crate::geo_source::ReadRequest| Ok(chunks[r.chunk_index as usize].clone()),
        &mut || false,
    )
    .unwrap();
    begin[136..144].copy_from_slice(&validated.digest());
    p64(&mut begin, 144, validated.generation());
    p64(&mut begin, 152, u64::MAX);
    for at in [160, 168, 176, 184, 192] {
        p64(&mut begin, at, 1);
    }
    p32(&mut begin, 200, 2);
    p64(&mut begin, 208, i64::MIN as u64);
    p64(&mut begin, 216, (i64::MIN + 1) as u64);
    p64(&mut begin, 224, 100);
    source_execute(&begin);
    drive(source.handle, 1, &chunks);
    let mut style = [0; 48];
    style[..4].copy_from_slice(&[255, 0, 0, 255]);
    p64(&mut style, 16, 8f64.to_bits());
    p64(&mut style, 24, 1f64.to_bits());
    let frame = Owner {
        handle: u64at(
            &source_execute(&source_cmd(11, source.handle, 1, &style)),
            16,
        ),
        kind: 0,
    };
    (frame, vec![source, builder])
}
fn label_catalog() -> Vec<u8> {
    let mut b = vec![0; 128];
    b[..4].copy_from_slice(b"XYLK");
    p32(&mut b, 4, 1);
    p32(&mut b, 16, 4326);
    p64(&mut b, 48, 64f64.to_bits());
    p64(&mut b, 56, 64f64.to_bits());
    b
}
fn tile_frame() -> (Owner, Owner, u64) {
    tile_frame_with_color([0, 0, 255, 255])
}
fn tile_frame_with_color(color: [u8; 4]) -> (Owner, Owner, u64) {
    let cache = Owner {
        handle: u64at(
            &crate::geo_tile_protocol::execute(&tile_cmd(1, 0, 0, 0, &[])).unwrap(),
            16,
        ),
        kind: 1,
    };
    let mut begin = vec![0; 80];
    p32(&mut begin, 0, 4326);
    p64(&mut begin, 32, 64f64.to_bits());
    p64(&mut begin, 40, 64f64.to_bits());
    p32(&mut begin, 64, 2);
    for kind in 0..2 {
        let locator = if kind == 0 {
            "https://example.test/{z}/{x}/{y}"
        } else {
            "local/vector"
        };
        let attr = if kind == 0 { "Tiles" } else { "" };
        let mut h = vec![0; 112];
        for (at, n) in [
            (0, kind as u64 + 1),
            (8, 1),
            (16, kind as u64 + 7),
            (24, 1),
            (32, 1),
            (72, if kind == 0 { 262144 } else { 1024 }),
            (80, 1),
            (88, 1),
        ] {
            p64(&mut h, at, n);
        }
        p32(&mut h, 60, kind);
        p32(&mut h, 96, locator.len() as u32);
        p32(&mut h, 100, attr.len() as u32);
        p32(&mut h, 104, u32::from(kind == 0));
        begin.extend(h);
        begin.extend_from_slice(locator.as_bytes());
        begin.extend_from_slice(attr.as_bytes());
    }
    let epoch = u64at(
        &crate::geo_tile_protocol::execute(&tile_cmd(2, cache.handle, 0, 9, &begin)).unwrap(),
        24,
    );
    loop {
        let next =
            crate::geo_tile_protocol::execute(&tile_cmd(3, cache.handle, epoch, 0, &[])).unwrap();
        let read = u64at(&next, 16);
        if read == 0 {
            break;
        }
        let data = if u32at(&next, 148) == 0 {
            color.repeat(256 * 256)
        } else {
            descriptor(10., u64::MAX)
        };
        crate::geo_tile_protocol::execute(&tile_cmd(4, read, epoch, 0, &data)).unwrap();
        drop(data);
        crate::geo_tile_protocol::execute(&tile_cmd(5, read, epoch, 0, &[])).unwrap();
    }
    let catalog = label_catalog();
    let mut prepare = vec![0; 32];
    p64(&mut prepare, 0, 42);
    p32(&mut prepare, 8, 1);
    p64(&mut prepare, 16, catalog.len() as u64);
    let mut style = vec![0; 64];
    p64(&mut style, 0, 8);
    p32(&mut style, 8, 1);
    style[16..20].copy_from_slice(&[0, 255, 0, 255]);
    p64(&mut style, 32, 6f64.to_bits());
    p64(&mut style, 40, 1f64.to_bits());
    prepare.extend(style);
    prepare.extend(catalog);
    let frame = Owner {
        handle: u64at(
            &crate::geo_tile_protocol::execute(&tile_cmd(6, cache.handle, epoch, 0, &prepare))
                .unwrap(),
            16,
        ),
        kind: 1,
    };
    (frame, cache, epoch)
}
fn descriptor(x: f64, id: u64) -> Vec<u8> {
    let mut b = vec![0; 96];
    b[..4].copy_from_slice(b"XYGD");
    for (at, n) in [(4, 1), (8, 1), (12, 4326), (16, 1)] {
        p32(&mut b, at, n);
    }
    p64(&mut b, 24, 1);
    p64(&mut b, 32, 1);
    p64(&mut b, 64, x.to_bits());
    b[80] = 1;
    p64(&mut b, 88, id);
    b
}
fn prepare_packet(coord: u64, source: u64, tile: u64, epoch: u64) -> Vec<u8> {
    let snapshot = crate::geo_scale_protocol::with_scene_data(source, 1, |v| v.snapshot).unwrap();
    let (cache, view, stamps) = crate::geo_tile_protocol::with_frame_data(tile, epoch, |v| {
        (
            u64at(v.receipt, 16),
            u64at(v.receipt, 32),
            v.provenance.to_vec(),
        )
    })
    .unwrap();
    let mut b = mixed_cmd(2, coord, 0);
    p64(&mut b, 64, source);
    p64(&mut b, 72, 1);
    p64(&mut b, 80, tile);
    p64(&mut b, 88, epoch);
    p64(&mut b, 96, cache);
    p64(&mut b, 104, view);
    p32(&mut b, 116, stamps.len() as u32);
    b.extend(snapshot_bytes(snapshot));
    for s in stamps {
        let mut k = [0; 96];
        for (at, n) in [
            (0, s.key.source_id),
            (8, s.key.generation),
            (16, s.key.layer_id),
            (24, s.key.layer_revision),
            (32, s.key.style_revision),
        ] {
            p64(&mut k, at, n);
        }
        p32(&mut k, 60, u32::from(s.key.kind == GeoTileKind::VectorXygd));
        p32(&mut k, 64, s.key.zoom as u32);
        p32(&mut k, 68, s.key.x);
        p32(&mut k, 72, s.key.y);
        k[80..88].copy_from_slice(&s.config_digest);
        k[88..96].copy_from_slice(&s.payload_digest);
        b.extend(k);
    }
    let payload_len = b.len() - HEADER;
    p64(&mut b, 40, payload_len as u64);
    b
}
fn snapshot_cmd(cmd: u32, handle: u64, nonce: u64) -> Vec<u8> {
    let mut b = vec![0; HEADER];
    b[..4].copy_from_slice(b"XYGJ");
    p32(&mut b, 4, 1);
    p32(&mut b, 8, cmd);
    p64(&mut b, 16, handle);
    p64(&mut b, 24, nonce);
    if cmd == 5 {
        p64(&mut b, 32, BUDGET as u64);
    }
    b
}
#[test]
fn mixed_transport_actual_authority_staging_disposal_and_frozen_whole_scene() {
    let _p = crate::geo_source_session::test_processor_lock();
    let _d = crate::geo_tile_cache::test_process_lock();
    let (source, source_owners) = source_frame();
    let (tile, cache, epoch) = tile_frame();
    let coord = Owner {
        handle: u64at(&execute(&mixed_cmd(1, 0, 0)).unwrap(), 16),
        kind: 2,
    };
    let prepared = execute(&prepare_packet(
        coord.handle,
        source.handle,
        tile.handle,
        epoch,
    ))
    .unwrap();
    let data = Owner {
        handle: u64at(&prepared, 16),
        kind: 2,
    };
    let nonce = u64at(&prepared, 24);
    let bytes = read_data(&mixed_cmd(20, data.handle, nonce), BUDGET).unwrap();
    let scene_len = u64at(&bytes, 32) as usize;
    let scene = &bytes[HEADER..HEADER + scene_len];
    let doc = SceneDocument::decode(scene).unwrap();
    assert!(doc
        .interaction_records()
        .iter()
        .any(|r| r.kind == SceneRecordKind::Image));
    assert!(doc.has_visible_attribution("Tiles"));
    let range = u64at(&bytes, 48) as usize..u64at(&bytes, 56) as usize;
    assert_eq!(range.len(), 1);
    assert_eq!(doc.interaction_records()[range.start].stable_id, u64::MAX);
    execute(&mixed_cmd(3, data.handle, nonce)).unwrap();
    drop(source);
    drop(source_owners);
    drop(tile);
    drop(cache);
    let retained = execute(&mixed_cmd(6, data.handle, nonce)).unwrap();
    let source_clone = Owner {
        handle: u64at(&retained, 16),
        kind: 0,
    };
    crate::geo_scale_protocol::with_scene_data(source_clone.handle, 1, |v| {
        assert_eq!(v.result.visible_vertices, 1)
    })
    .unwrap();
    drop(source_clone);
    let frozen =
        crate::geo_snapshot_protocol::execute(&snapshot_cmd(5, data.handle, nonce)).unwrap();
    let snapshot = Owner {
        handle: u64at(&frozen, 16),
        kind: 3,
    };
    let frozen_bytes =
        crate::geo_snapshot_protocol::read_data(&snapshot_cmd(20, snapshot.handle, 0), BUDGET)
            .unwrap();
    let decode_cache = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
    let decoded =
        crate::geo_snapshot::GeoFrozenSnapshot::decode(&decode_cache, &frozen_bytes, BUDGET)
            .unwrap();
    assert_eq!(decoded.scene(), scene);
    assert_eq!(decoded.direct()[0].feature_id, u64::MAX);
    assert_eq!(
        decoded.identity().time,
        TimePredicate::Window {
            start: i64::MIN,
            end: i64::MIN + 1
        }
    );
    assert_eq!(decoded.attributions(), &["Tiles"]);
    assert_eq!(
        read_data(&mixed_cmd(20, data.handle, nonce), BUDGET).unwrap(),
        bytes
    );
    assert!(matches!(
        read_data(&mixed_cmd(20, data.handle, nonce), BUDGET),
        Err(SourceError::ResourceLimit)
    ));
    #[cfg(feature = "raster")]
    {
        let mut pixels = vec![0; 64 * 64 * 4];
        assert!(crate::raster::rasterize_into(
            &doc.to_raster_commands(1.).unwrap(),
            64,
            64,
            &mut pixels
        ));
        assert_eq!(
            &pixels[(32 * 64 + 32) * 4..(32 * 64 + 32) * 4 + 4],
            &[255, 0, 0, 255]
        );
        assert_eq!(
            &pixels[(2 * 64 + 2) * 4..(2 * 64 + 2) * 4 + 4],
            &[0, 0, 255, 255]
        );
        let artifact = decoded
            .export(
                &decode_cache,
                decoded.identity(),
                crate::geo_snapshot::GeoFrozenFormat::Svg,
                1.,
                90,
                BUDGET,
            )
            .unwrap();
        assert!(std::str::from_utf8(artifact.bytes())
            .unwrap()
            .contains("Tiles"));
    }
}

#[test]
fn mixed_transport_stale_cancel_resource_failure_preserve_old_scene() {
    let _p = crate::geo_source_session::test_processor_lock();
    let _d = crate::geo_tile_cache::test_process_lock();
    let (source, _owners) = source_frame();
    let (tile, _cache, epoch) = tile_frame();
    let coord = Owner {
        handle: u64at(&execute(&mixed_cmd(1, 0, 0)).unwrap(), 16),
        kind: 2,
    };
    let input = prepare_packet(coord.handle, source.handle, tile.handle, epoch);
    let first = execute(&input).unwrap();
    let old = Owner {
        handle: u64at(&first, 16),
        kind: 2,
    };
    let nonce = u64at(&first, 24);
    execute(&mixed_cmd(3, old.handle, nonce)).unwrap();
    let scene = with_frame_data(old.handle, nonce, |f| f.scene().to_vec()).unwrap();
    let second = execute(&input).unwrap();
    let candidate = Owner {
        handle: u64at(&second, 16),
        kind: 2,
    };
    let current = u64at(&second, 24);
    assert!(matches!(
        execute(&mixed_cmd(3, old.handle, nonce)),
        Err(SourceError::StaleSource)
    ));
    assert!(execute(&mixed_cmd(4, old.handle, nonce)).is_err());
    execute(&mixed_cmd(4, candidate.handle, current)).unwrap();
    assert!(execute(&mixed_cmd(3, candidate.handle, current)).is_err());
    let baseline = GeoProcessorLease::live_bytes();
    let mut small = input.clone();
    p64(&mut small, 32, 65536);
    assert!(matches!(execute(&small), Err(SourceError::ResourceLimit)));
    assert_eq!(GeoProcessorLease::live_bytes(), baseline);
    assert_eq!(
        with_frame_data(old.handle, nonce, |f| f.scene().to_vec()).unwrap(),
        scene
    );
    let transport = crate::geo_transport::GeoTransportLease::acquire().unwrap();
    transport
        .with_phase(BUDGET, |phase| {
            let painted =
                crate::geo_retained_painter::prepare_tile_frame_painter(old.handle, nonce, phase)
                    .unwrap();
            assert_eq!(&painted.bytes[..4], b"XYPB");
            assert!(painted.records > 1);
            assert!(crate::geo_retained_painter::prepare_tile_frame_painter(
                MIXED_HANDLE_TAG | u64::MAX,
                nonce,
                phase
            )
            .is_err());
        })
        .unwrap();
}

#[test]
fn mixed_transport_framing_and_pure_probe_never_spend_read_authority() {
    let _p = crate::geo_source_session::test_processor_lock();
    let _d = crate::geo_tile_cache::test_process_lock();
    let (source, _owners) = source_frame();
    let (tile, _cache, epoch) = tile_frame();
    let coord = Owner {
        handle: u64at(&execute(&mixed_cmd(1, 0, 0)).unwrap(), 16),
        kind: 2,
    };
    let packet = prepare_packet(coord.handle, source.handle, tile.handle, epoch);
    for at in [4, 12, 48, 120, 256 + 132, 256 + 152, 416 + 76] {
        let mut bad = packet.clone();
        bad[at] = bad[at].wrapping_add(1);
        assert!(execute(&bad).is_err(), "offset {at}");
    }
    let mut wrong = packet.clone();
    p64(&mut wrong, 64, coord.handle);
    assert!(execute(&wrong).is_err());
    let mut bad_count = packet.clone();
    p32(&mut bad_count, 116, 65);
    assert!(execute(&bad_count).is_err());
    let mut filtered = packet.clone();
    p32(&mut filtered, 112, 2);
    assert!(execute(&filtered).is_err());
    let mut stamp = packet.clone();
    stamp[416 + 88] ^= 1;
    assert!(execute(&stamp).is_err());
    // A failed admitted candidate binds its stamp history. Fresh authority is needed
    // for the original stamp set at the same source revisions.
    let fresh = Owner {
        handle: u64at(&execute(&mixed_cmd(1, 0, 0)).unwrap(), 16),
        kind: 2,
    };
    let valid = prepare_packet(fresh.handle, source.handle, tile.handle, epoch);
    let fixed = execute(&valid).unwrap();
    let data = Owner {
        handle: u64at(&fixed, 16),
        kind: 2,
    };
    let nonce = u64at(&fixed, 24);
    let read = mixed_cmd(20, data.handle, nonce);
    for _ in 0..10 {
        assert_eq!(data_len(&read, BUDGET).unwrap(), u64at(&fixed, 40) as usize);
    }
    let mut limited = read.clone();
    p64(&mut limited, 32, 65536);
    assert!(data_len(&limited, 65536).is_err());
    let first = read_data(&read, BUDGET).unwrap();
    let second = read_data(&read, BUDGET).unwrap();
    assert_eq!(first, second);
    assert!(read_data(&read, BUDGET).is_err());
    assert_eq!(
        crate::geo_tile_protocol::data_len(&read, BUDGET).unwrap(),
        first.len()
    );
    assert!(crate::geo_tile_protocol::execute(&read).is_err());
}

#[test]
fn mixed_frozen_mode_rejects_ranges_time_padding_and_whole_scene_substitution() {
    let _p = crate::geo_source_session::test_processor_lock();
    let _d = crate::geo_tile_cache::test_process_lock();
    let (source, _owners) = source_frame();
    let (tile, _cache, epoch) = tile_frame();
    let coord = Owner {
        handle: u64at(&execute(&mixed_cmd(1, 0, 0)).unwrap(), 16),
        kind: 2,
    };
    let prepared = execute(&prepare_packet(
        coord.handle,
        source.handle,
        tile.handle,
        epoch,
    ))
    .unwrap();
    let data = Owner {
        handle: u64at(&prepared, 16),
        kind: 2,
    };
    let nonce = u64at(&prepared, 24);
    let fixed =
        crate::geo_snapshot_protocol::execute(&snapshot_cmd(5, data.handle, nonce)).unwrap();
    let frozen = Owner {
        handle: u64at(&fixed, 16),
        kind: 3,
    };
    let bytes =
        crate::geo_snapshot_protocol::read_data(&snapshot_cmd(20, frozen.handle, 0), BUDGET)
            .unwrap();
    let cache = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
    let scene = u64at(&bytes, 24) as usize;
    let blob_len = u32at(&bytes, 188) as usize;
    let blob = bytes.len() - scene - blob_len;
    for at in [
        blob + 4,
        blob + 8,
        blob + 20,
        blob + 32,
        blob + 48,
        blob + 64 + 66,
    ] {
        let mut bad = bytes.clone();
        bad[at] = bad[at].wrapping_add(1);
        assert!(
            crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &bad, BUDGET).is_err(),
            "offset {at}"
        );
    }
    let mut camera = bytes.clone();
    p64(&mut camera, 80, 1f64.to_bits());
    assert!(crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &camera, BUDGET).is_err());
    let mut missing = bytes.clone();
    p32(&mut missing, blob + 8, 5);
    assert!(crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &missing, BUDGET).is_err());
    let mut old_mode = bytes.clone();
    p32(&mut old_mode, blob + 4, 1);
    assert!(crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &old_mode, BUDGET).is_err());
    let mut small = snapshot_cmd(5, data.handle, nonce);
    p64(&mut small, 32, 65536);
    assert!(crate::geo_snapshot_protocol::execute(&small).is_err());
    assert!(crate::geo_snapshot::GeoFrozenSnapshot::decode(&cache, &bytes, 65536).is_err());
}

#[test]
fn geographic_attribution_footer_is_literal_bounded_and_preserves_existing_and_local_bytes() {
    let _p = crate::geo_source_session::test_processor_lock();
    let _d = crate::geo_tile_cache::test_process_lock();
    let (source, _owners) = source_frame();
    let scene =
        crate::geo_scale_protocol::with_scene_data(source.handle, 1, |s| s.scene.to_vec()).unwrap();
    let cache = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
    let _phase = cache.reserve_derived(scene.len() * 32 + (1 << 20)).unwrap();
    assert_eq!(
        SceneDocument::with_geographic_attributions(&scene, &[]).unwrap(),
        scene
    );
    let one = SceneDocument::with_geographic_attributions(&scene, &["Tiles", "Tiles"]).unwrap();
    assert!(SceneDocument::decode(&one)
        .unwrap()
        .has_visible_attribution("Tiles"));
    assert_eq!(
        SceneDocument::with_geographic_attributions(&one, &["Tiles"]).unwrap(),
        one
    );
    let escaped = SceneDocument::with_geographic_attributions(&scene, &["A<&"]).unwrap();
    #[cfg(feature = "raster")]
    assert!(SceneDocument::decode(&escaped)
        .unwrap()
        .to_svg()
        .contains("A&lt;&amp;"));
    for text in ["", "\n", &"x".repeat(4096), &"x".repeat(4097)] {
        assert!(SceneDocument::with_geographic_attributions(&scene, &[text]).is_err());
    }
    assert!(
        SceneDocument::with_geographic_attributions(&scene, &["a", "b", "c", "d", "e", "f"])
            .is_err()
    );
}

#[test]
#[cfg(feature = "raster")]
fn geographic_footer_keeps_contrast_on_black_and_white_rasters() {
    let _p = crate::geo_source_session::test_processor_lock();
    let _d = crate::geo_tile_cache::test_process_lock();
    for color in [[0, 0, 0, 255], [255, 255, 255, 255]] {
        let (tile, _cache, epoch) = tile_frame_with_color(color);
        crate::geo_tile_protocol::with_frame_data(tile.handle, epoch, |v| {
            let doc = SceneDocument::decode(v.scene).unwrap();
            assert!(doc.has_visible_attribution("Tiles"));
            let svg = doc.to_svg();
            assert!(svg.contains("annotation_label_box"));
            let mut pixels = vec![0; 64 * 64 * 4];
            assert!(crate::raster::rasterize_into(
                &doc.to_raster_commands(1.).unwrap(),
                64,
                64,
                &mut pixels
            ));
            assert_eq!(&pixels[(2 * 64 + 2) * 4..(2 * 64 + 2) * 4 + 4], &color);
            let footer: Vec<_> = (51..63)
                .flat_map(|y| (41..61).map(move |x| (y * 64 + x) * 4))
                .map(|at| &pixels[at..at + 4])
                .collect();
            assert!(footer
                .iter()
                .any(|p| p[0] < 64 && p[1] < 64 && p[2] < 64 && p[3] == 255));
            assert!(footer.contains(&[255, 255, 255, 255].as_slice()));
        })
        .unwrap();
    }
}

#[test]
fn mixed_public_tile_descriptor_preserves_exact_authority_and_shared_copy_quota() {
    let _p = crate::geo_source_session::test_processor_lock();
    let _d = crate::geo_tile_cache::test_process_lock();
    let (tile, cache, epoch) = tile_frame();
    let descriptor = tile_cmd(23, tile.handle, epoch, 0, &[]);
    for _ in 0..10 {
        assert_eq!(
            crate::geo_tile_protocol::data_len(&descriptor, BUDGET).unwrap(),
            448
        );
    }
    assert!(crate::geo_tile_protocol::data_len(
        &tile_cmd(23, tile.handle, epoch + 1, 0, &[]),
        BUDGET
    )
    .is_err());
    let bytes = crate::geo_tile_protocol::read_data(&descriptor, BUDGET).unwrap();
    assert_eq!(&bytes[..4], b"XYUP");
    assert_eq!(u64at(&bytes, 16), tile.handle);
    assert_eq!(u64at(&bytes, 24), epoch);
    assert_eq!(u64at(&bytes, 32), cache.handle);
    crate::geo_tile_protocol::with_frame_data(tile.handle, epoch, |frame| {
        for (i, stamp) in frame.provenance.iter().enumerate() {
            assert_eq!(
                &bytes[256 + i * 96 + 80..256 + i * 96 + 88],
                &stamp.config_digest
            );
            assert_eq!(
                &bytes[256 + i * 96 + 88..256 + i * 96 + 96],
                &stamp.payload_digest
            );
        }
    })
    .unwrap();
    drop(cache);
    assert!(
        crate::geo_tile_protocol::read_data(&tile_cmd(22, tile.handle, epoch, 0, &[]), BUDGET)
            .is_ok()
    );
    assert!(crate::geo_tile_protocol::read_data(&descriptor, BUDGET).is_err());
    let handle = tile.handle;
    drop(tile);
    assert!(
        crate::geo_tile_protocol::data_len(&tile_cmd(23, handle, epoch, 0, &[]), BUDGET).is_err()
    );
}
