//! Independent real-cache staging/rollback proof for mixed geographic tiles.
use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
use crate::geo_source_session::test_processor_lock;
fn p32(b: &mut [u8], at: usize, x: u32) {
    b[at..at + 4].copy_from_slice(&x.to_le_bytes());
}
fn p64(b: &mut [u8], at: usize, x: u64) {
    b[at..at + 8].copy_from_slice(&x.to_le_bytes());
}

#[test]
fn mixed_real_tile_cache_scene_is_staged_before_commit_and_failures_preserve_frame() {
    use crate::geo_layers::{GeoCatalog, GeoLayer, GeoLayerKind, GeoStyle};
    use crate::geo_tile_cache::{
        GeoTileCache, GeoTileData, GeoTileKind, GeoTileLimits, GeoTileLocation, GeoTileSource,
    };
    use crate::geo_tile_scene::{GeoVectorTileStyle, TileSceneError, compile_tile_frame};
    use crate::geo_viewport::GeoViewport;
    let _guard = test_processor_lock();
    let camera = GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 0., 128., 96., 0., 0., true).unwrap();
    let raster = GeoTileSource {
        source_id: 1,
        generation: u64::MAX,
        layer_id: 100,
        layer_revision: 1,
        style_revision: 1,
        time: None,
        kind: GeoTileKind::RasterRgba,
        location: GeoTileLocation::Local {
            locator: "fixture-raster".into(),
        },
        min_zoom: 0,
        max_zoom: 0,
        payload_limits: GeoLimits {
            max_features: 16,
            max_vertices: 32,
            max_bytes: 256 * 256 * 4,
        },
    };
    let vector = GeoTileSource {
        source_id: 2,
        layer_id: 200,
        kind: GeoTileKind::VectorXygd,
        location: GeoTileLocation::Local {
            locator: "fixture-vector".into(),
        },
        payload_limits: GeoLimits {
            max_features: 2,
            max_vertices: 4,
            max_bytes: 256,
        },
        ..raster.clone()
    };
    let sources = [raster, vector];
    let mut cache = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
    let epoch = cache.begin_frame(1, &camera, &sources, 0).unwrap();
    let requests = cache.requests().to_vec();
    assert_eq!(requests.len(), 2);
    let mut descriptor = vec![0; 96];
    descriptor[..4].copy_from_slice(b"XYGD");
    p32(&mut descriptor, 4, 1);
    p32(&mut descriptor, 8, 1);
    p32(&mut descriptor, 12, 4326);
    p32(&mut descriptor, 16, 1);
    p64(&mut descriptor, 24, 1);
    p64(&mut descriptor, 32, 1);
    descriptor[80] = 1;
    p64(&mut descriptor, 88, u64::MAX);
    for request in requests {
        let mut read = cache.start_read(request.ticket).unwrap();
        let data = match request.ticket.key.kind {
            GeoTileKind::RasterRgba => {
                for pixel in read.bytes_mut().chunks_exact_mut(4) {
                    pixel.copy_from_slice(&[32, 64, 96, 255]);
                }
                GeoTileData::Raster {
                    width: 256,
                    height: 256,
                    length: 256 * 256 * 4,
                }
            }
            GeoTileKind::VectorXygd => {
                read.bytes_mut()[..descriptor.len()].copy_from_slice(&descriptor);
                GeoTileData::VectorXygd {
                    length: descriptor.len(),
                }
            }
        };
        cache.publish(read, data).unwrap();
    }
    let analysis = GeoColumn::from_descriptor(GeoDescriptor {
        geometry: GeoGeometry::Point,
        crs: GeoCrs::Epsg4326,
        xy: &[1., 0.],
        validity: &[1],
        feature_ids: Some(&[0x8000000000000001]),
        offsets0: &[],
        offsets1: &[],
        offsets2: &[],
        limits: GeoLimits::default(),
    })
    .unwrap();
    let layers = [GeoLayer::new(300, GeoLayerKind::Points, &analysis)];
    let catalog = GeoCatalog {
        viewport: camera,
        layers: &layers,
        legend: None,
        budget: 16 << 20,
    };
    let styles = [GeoVectorTileStyle {
        layer_id: 200,
        kind: GeoLayerKind::Points,
        style: GeoStyle::default(),
    }];
    let staged = compile_tile_frame(&cache, epoch, &catalog, 400, &styles, &mut || false).unwrap();
    assert!(cache.frame(1).is_none());
    let compiled = staged.compiled();
    assert_eq!(
        compiled
            .layers
            .iter()
            .map(|l| l.layer_id)
            .collect::<Vec<_>>(),
        [200, 300]
    );
    assert_eq!(compiled.layers[0].feature_ids, [u64::MAX]);
    assert_eq!(compiled.layers[1].feature_ids, [0x8000000000000001]);
    let scene = crate::scene::SceneDocument::decode(&compiled.scene).unwrap();
    assert_eq!(
        &scene.interaction_image(400).unwrap().rgba[..4],
        &[32, 64, 96, 255]
    );
    let ids: Vec<_> = scene
        .interaction_records()
        .iter()
        .filter(|r| r.kind == crate::scene::SceneRecordKind::Scatter && r.diameter > 0.)
        .map(|r| r.stable_id)
        .collect();
    assert_eq!(ids, [u64::MAX, 0x8000000000000001]);
    let prior = cache.commit_frame(epoch).unwrap().clone();
    let old_scene = compiled.scene.clone();
    let shifted = GeoViewport {
        center_x: 1.,
        ..camera
    };
    let next = cache.begin_frame(1, &shifted, &sources, 0).unwrap();
    assert!(cache.requests().is_empty());
    let next_catalog = GeoCatalog {
        viewport: shifted,
        ..catalog
    };
    let reserved = cache.stats().derived_reserved_bytes;
    assert!(matches!(
        compile_tile_frame(&cache, next, &next_catalog, 400, &styles, &mut || true),
        Err(TileSceneError::Cancelled)
    ));
    assert_eq!(cache.stats().derived_reserved_bytes, reserved);
    assert_eq!(cache.frame(1), Some(&prior));
    assert_eq!(staged.compiled().scene, old_scene);
    let bad_styles = [GeoVectorTileStyle {
        layer_id: 200,
        kind: GeoLayerKind::Points,
        style: GeoStyle {
            opacity: f64::NAN,
            ..GeoStyle::default()
        },
    }];
    assert!(
        compile_tile_frame(&cache, next, &next_catalog, 400, &bad_styles, &mut || false).is_err()
    );
    assert_eq!(cache.stats().derived_reserved_bytes, reserved);
    assert_eq!(cache.frame(1), Some(&prior));
    let recovered =
        compile_tile_frame(&cache, next, &next_catalog, 400, &styles, &mut || false).unwrap();
    assert_eq!(cache.frame(1), Some(&prior));
    cache.commit_frame(next).unwrap();
    assert_eq!(cache.frame(1).unwrap().epoch, next);
    assert_eq!(recovered.compiled().layers[0].feature_ids, [u64::MAX]);
}
