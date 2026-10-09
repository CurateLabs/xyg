//! Actual retained selection folds, inert frozen framing, and native export.
use super::*;
use crate::geo::{GeoColumn, GeoDescriptor, GeoLimits};
use crate::geo_layers::GeoStyle;
use crate::geo_linked_state::{GeoLinkedState, GeoSelectedStyle};
use crate::geo_lod::{GeoLodOptions, process_with_state};
use crate::geo_source::{
    GeoChunk, GeoIntervals, GeoManifestBuilder, GeoSourceManifest, QueryBudget, ReadRequest,
};
use crate::geo_source_session::test_processor_lock;
use crate::geo_tile_cache::{GeoTileLimits, test_process_lock};

fn fixture(reduced: bool) -> (GeoSourceManifest, Vec<u8>) {
    let n = if reduced { 32771 } else { 5 };
    let xy = if reduced {
        vec![0.; n * 2]
    } else {
        vec![0., 0., 1., 0., 3., 0., 180., 0.]
    };
    let valid = if reduced {
        vec![1; 3]
    } else {
        vec![1, 1, 0, 1, 1]
    };
    let ids = if reduced {
        vec![u64::MAX, u64::MAX, 5]
    } else {
        vec![u64::MAX, u64::MAX, 7, 42, 99]
    };
    let offsets = if reduced {
        vec![0, 16385, 32768, n as u32]
    } else {
        vec![]
    };
    let column = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: if reduced {
            GeoGeometry::MultiPoint
        } else {
            GeoGeometry::Point
        },
        crs: GeoCrs::Epsg4326,
        xy: &xy,
        validity: &valid,
        feature_ids: Some(&ids),
        offsets0: &offsets,
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let starts = if reduced {
        vec![i64::MIN; 3]
    } else {
        vec![i64::MIN, i64::MIN, i64::MIN, 1, i64::MIN]
    };
    let ends = vec![i64::MAX; ids.len()];
    let time_valid = vec![1; ids.len()];
    let raw = GeoChunk::encode(
        &column,
        Some(GeoIntervals {
            starts: &starts,
            ends: &ends,
            start_validity: &time_valid,
            end_validity: &time_valid,
        }),
    )
    .unwrap();
    let chunk = GeoChunk::parse(&raw, 96 << 20).unwrap();
    let mut builder = GeoManifestBuilder::new();
    builder.push(&chunk).unwrap();
    (builder.finish(u64::MAX).unwrap(), raw)
}
fn camera() -> GeoViewport {
    GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 0., 128., 96., 0., 0., true).unwrap()
}
fn style() -> GeoStyle {
    GeoStyle {
        fill: [0, 0, 255, 255],
        stroke: [0; 4],
        opacity: 0.5,
        ..GeoStyle::default()
    }
}
fn style_bytes() -> [u8; 48] {
    let style = style();
    let mut b = [0; 48];
    b[..4].copy_from_slice(&style.fill);
    b[4..8].copy_from_slice(&style.stroke);
    for (at, n) in [
        (8, style.stroke_width),
        (16, style.diameter),
        (24, style.opacity),
    ] {
        put64(&mut b, at, n.to_bits());
    }
    b[32] = style.symbol;
    b
}
fn run(
    reduced: bool,
    kind: GeoReducedKind,
    ids: Option<&[u64]>,
) -> (GeoPointResult, Vec<u8>, GeoOperationSnapshot) {
    let (source, raw) = fixture(reduced);
    let state = ids.map(|ids| {
        GeoLinkedState::new(
            &source,
            u64::MAX - 1,
            u64::MAX,
            7,
            ids,
            GeoSelectedStyle {
                fill: [255, 0, 0, 255],
            },
        )
        .unwrap()
    });
    let result = process_with_state(
        &source,
        &mut |_: ReadRequest| Ok(raw.clone()),
        camera(),
        TimePredicate::Instant(i64::MIN),
        u64::MAX,
        3,
        7,
        GeoLodOptions {
            kind,
            max_cells: 4,
            ..GeoLodOptions::default()
        },
        QueryBudget::default(),
        state,
        &mut || false,
    )
    .unwrap();
    let snapshot = GeoOperationSnapshot {
        source_digest: source.digest(),
        generation: source.generation(),
        camera: result.key.camera,
        time: result.key.time,
        camera_revision: u64::MAX,
        time_revision: u64::MAX - 1,
        layer_id: u64::MAX,
        layer_revision: 2,
        style_revision: 3,
        state_revision: 7,
    };
    let scene = crate::geo_lod_scene::compile(&result, style(), 32 << 20)
        .unwrap()
        .scene;
    (result, scene, snapshot)
}
fn cache() -> GeoTileCache {
    GeoTileCache::new(GeoTileLimits::default(), 0).unwrap()
}
fn selection_at(f: &GeoFrozenSnapshot) -> usize {
    SELECTED_HEADER
        + f.identity.layers.len() * LAYER
        + f.direct.len() * DIRECT
        + f.membership.len() * MEMBERSHIP
        + f.grids
            .iter()
            .map(|g| GRID + g.vertex_counts.len() * 8)
            .sum::<usize>()
}

#[test]
fn selected_snapshot_direct_full_intent_survives_original_authority_and_ordinary_bytes() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let cache = cache();
    let (result, scene, snapshot) = run(
        false,
        GeoReducedKind::Cluster,
        Some(&[u64::MAX, u64::MAX, 7, 42, 99, 12345]),
    );
    let frozen = GeoFrozenSnapshot::freeze_lod(
        &cache,
        &scene,
        &result,
        snapshot,
        &style_bytes(),
        MAX_FROZEN_PEAK,
    )
    .unwrap();
    assert_eq!(u32at(frozen.bytes(), 4), 3);
    assert_eq!(
        frozen.selections()[0].selected_ids(),
        &[7, 42, 99, 12345, u64::MAX]
    );
    assert_eq!(frozen.selections()[0].visible_selected_vertices(), 2);
    assert!(frozen.selections()[0].selected_counts().is_empty());
    assert_eq!(frozen.selections()[0].namespace(), u64::MAX - 1);
    assert_eq!(frozen.direct()[0].feature_id, u64::MAX);
    assert_eq!(frozen.identity().time, TimePredicate::Instant(i64::MIN));
    let again = GeoFrozenSnapshot::freeze_lod(
        &cache,
        &scene,
        &result,
        snapshot,
        &style_bytes(),
        MAX_FROZEN_PEAK,
    )
    .unwrap();
    assert_eq!(frozen.bytes(), again.bytes());
    drop(again);
    drop(result);
    drop(scene);
    let imported = GeoFrozenSnapshot::decode(&cache, frozen.bytes(), MAX_FROZEN_PEAK).unwrap();
    assert_eq!(imported.selections(), frozen.selections());
    let at = selection_at(&frozen);
    let length = u32at(frozen.bytes(), 196) as usize;
    let mut duplicate = frozen.bytes().to_vec();
    let record = duplicate[at..at + length].to_vec();
    duplicate.splice(at + length..at + length, record);
    put32(&mut duplicate, 192, 2);
    put32(&mut duplicate, 196, (length * 2) as u32);
    let total = duplicate.len() as u64;
    put64(&mut duplicate, 16, total);
    assert!(matches!(
        GeoFrozenSnapshot::decode(&cache, &duplicate, MAX_FROZEN_PEAK),
        Err(GeoSnapshotError::Invalid)
    ));
    let mut duplicate_ids = frozen.bytes().to_vec();
    put64(&mut duplicate_ids, at + SELECTED_RECORD + 8, 7);
    assert!(matches!(
        GeoFrozenSnapshot::decode(&cache, &duplicate_ids, MAX_FROZEN_PEAK),
        Err(GeoSnapshotError::Invalid)
    ));
    let (ordinary, scene, snapshot) = run(false, GeoReducedKind::Cluster, None);
    let legacy = GeoFrozenSnapshot::freeze_lod(
        &cache,
        &scene,
        &ordinary,
        snapshot,
        &style_bytes(),
        MAX_FROZEN_PEAK,
    )
    .unwrap();
    assert_eq!(u32at(legacy.bytes(), 4), 2);
    assert!(legacy.selections().is_empty());
    let identity = legacy.identity();
    let g = &legacy.grids()[0];
    let explicit = GeoFrozenSnapshot::freeze_with_grids(
        &cache,
        &scene,
        identity,
        legacy.direct(),
        &[],
        &[GeoFrozenGridInput {
            key: g.key,
            visible_vertices: g.visible_vertices,
            projected_vertices: g.projected_vertices,
            counts: GeoFrozenGridCounts::Counts(&[]),
            style: g.style,
        }],
        &[],
        MAX_FROZEN_PEAK,
    )
    .unwrap();
    assert_eq!(legacy.bytes(), explicit.bytes());
}

#[test]
fn selected_snapshot_cluster_density_count_profile_and_binding_negative_controls() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let cache = cache();
    for kind in [GeoReducedKind::Cluster, GeoReducedKind::Density] {
        let (result, scene, snapshot) = run(true, kind, Some(&[u64::MAX]));
        assert!(!result.key.direct);
        let frozen = GeoFrozenSnapshot::freeze_lod(
            &cache,
            &scene,
            &result,
            snapshot,
            &style_bytes(),
            MAX_FROZEN_PEAK,
        )
        .unwrap();
        let s = &frozen.selections()[0];
        assert_eq!(s.visible, 32768);
        assert_eq!(s.counts.iter().sum::<u64>(), 32768);
        assert_eq!(frozen.grids()[0].vertex_counts.iter().sum::<u64>(), 32771);
        let at = selection_at(&frozen);
        for offset in [
            at,
            at + 160 + 16,
            at + 160 + 48,
            at + 160 + 56,
            at + 160 + 64,
            at + 160 + 72,
            at + 160 + 80,
            at + 160 + 88,
            at + 160 + 96,
            at + 160 + 100,
        ] {
            let mut corrupt = frozen.bytes().to_vec();
            corrupt[offset] ^= 1;
            assert!(
                GeoFrozenSnapshot::decode(&cache, &corrupt, MAX_FROZEN_PEAK).is_err(),
                "{kind:?} offset{offset}"
            );
        }
        let mut corrupt = frozen.bytes().to_vec();
        let count_at = at + SELECTED_RECORD + 8;
        put64(&mut corrupt, count_at, u64::MAX);
        assert!(GeoFrozenSnapshot::decode(&cache, &corrupt, MAX_FROZEN_PEAK).is_err());
        // A forged profile with its recomputed fingerprint still disagrees with
        // actual captured paint; fingerprints are never authorization.
        let mut corrupt = frozen.bytes().to_vec();
        let fill = [0, 255, 0, 255];
        corrupt[at + 208..at + 212].copy_from_slice(&fill);
        let fp = crate::geo_linked_state::fingerprint(
            result.selection.as_ref().unwrap().state().binding(),
            result.key.identity.source_rows,
            result.key.identity.crs,
            result.key.identity.geometry,
            &[u64::MAX],
            GeoSelectedStyle { fill },
        );
        put64(&mut corrupt, at + 264, fp[0]);
        put64(&mut corrupt, at + 272, fp[1]);
        assert!(matches!(
            GeoFrozenSnapshot::decode(&cache, &corrupt, MAX_FROZEN_PEAK),
            Err(GeoSnapshotError::Scene)
        ));
        let before = cache.stats().derived_reserved_bytes;
        assert!(matches!(
            GeoFrozenSnapshot::decode(&cache, frozen.bytes(), 256),
            Err(GeoSnapshotError::Limit)
        ));
        assert_eq!(cache.stats().derived_reserved_bytes, before);
        assert_eq!(
            GeoFrozenSnapshot::decode(&cache, frozen.bytes(), MAX_FROZEN_PEAK)
                .unwrap()
                .selections(),
            frozen.selections()
        );
    }
}

#[test]
fn selected_snapshot_empty_intent_keeps_scene_and_rejects_noncanonical_planes() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let cache = cache();
    for reduced in [false, true] {
        let (ordinary, ordinary_scene, _) = run(reduced, GeoReducedKind::Density, None);
        let (result, scene, snapshot) = run(reduced, GeoReducedKind::Density, Some(&[]));
        assert_eq!(ordinary_scene, scene);
        assert_eq!(ordinary.key, result.key);
        let f = GeoFrozenSnapshot::freeze_lod(
            &cache,
            &scene,
            &result,
            snapshot,
            &style_bytes(),
            MAX_FROZEN_PEAK,
        )
        .unwrap();
        assert!(f.selections()[0].ids.is_empty());
        assert!(f.selections()[0].counts.is_empty());
        assert_eq!(f.selections()[0].visible, 0);
        for (offset, value) in [
            (192, 0),
            (196, 0),
            (selection_at(&f) + 160 + 24, 10001),
            (selection_at(&f) + 160 + 32, u64::MAX),
        ] {
            let mut bad = f.bytes().to_vec();
            put64(&mut bad, offset, value);
            assert!(GeoFrozenSnapshot::decode(&cache, &bad, MAX_FROZEN_PEAK).is_err());
        }
    }
}

#[cfg(feature = "raster")]
#[test]
fn selected_snapshot_six_native_formats_preserve_v3_and_offline_contract() {
    let _cpu = test_processor_lock();
    let _tile = test_process_lock();
    let cache = cache();
    let (result, scene, snapshot) = run(false, GeoReducedKind::Cluster, Some(&[u64::MAX, 7, 42]));
    let f = GeoFrozenSnapshot::freeze_lod(
        &cache,
        &scene,
        &result,
        snapshot,
        &style_bytes(),
        MAX_FROZEN_PEAK,
    )
    .unwrap();
    drop(result);
    drop(scene);
    for format in [
        GeoFrozenFormat::Svg,
        GeoFrozenFormat::Png,
        GeoFrozenFormat::Pdf,
        GeoFrozenFormat::Jpeg,
        GeoFrozenFormat::Webp,
        GeoFrozenFormat::Html,
    ] {
        let a = f
            .export(
                &cache,
                f.identity(),
                format,
                1.,
                90,
                crate::geo_tile_cache::TILE_CACHE_PROCESS_BYTES,
            )
            .unwrap();
        let paired = GeoFrozenSnapshot::decode(&cache, a.snapshot(), MAX_FROZEN_PEAK).unwrap();
        assert_eq!(paired.selections(), f.selections());
        paired.verify_artifact(a.bytes()).unwrap();
        if format == GeoFrozenFormat::Html {
            let html = std::str::from_utf8(a.bytes()).unwrap();
            assert!(
                html.contains("default-src 'none'")
                    && html.contains("xyg-frozen-snapshot")
                    && !html.contains("<script")
            );
        }
        if format == GeoFrozenFormat::Png {
            let decoder = png::Decoder::new(std::io::Cursor::new(a.bytes()));
            let mut reader = decoder.read_info().unwrap();
            let mut pixels = vec![0; reader.output_buffer_size().unwrap()];
            let info = reader.next_frame(&mut pixels).unwrap();
            assert_eq!(info.color_type, png::ColorType::Rgb);
            // Existing static Scene export composites onto opaque white. Both
            // duplicate-ID half-opacity points overlap at this interior pixel.
            assert_eq!(
                &pixels[(48 * 128 + 64) * 3..(48 * 128 + 64) * 3 + 3],
                &[255, 63, 63]
            );
        }
    }
}
