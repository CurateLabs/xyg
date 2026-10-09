//! Exclusive-process proof that retained transport credit composes globally.
#![cfg(not(target_arch = "wasm32"))]
use xyg_engine::geo_tile_cache::{GeoTileCache, GeoTileLimits};
use xyg_wasm::*;

#[test]
fn retained_transport_credit_is_atomic_bounded_and_released() {
    let observer = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
    let baseline = observer.stats().process_charged_bytes;
    let a = xyg_wasm_instance_new(128 << 20);
    let b = xyg_wasm_instance_new(128 << 20);
    let c = xyg_wasm_instance_new(1 << 20);
    assert!(a != 0 && b != 0 && c != 0);
    assert_eq!(xyg_wasm_arena_resize(a, 4096), STATUS_OK);
    assert_eq!(xyg_wasm_geo_transport_acquire(a), STATUS_OK);
    assert_eq!(xyg_wasm_arena_len(a), 0);
    assert_eq!(
        observer.stats().process_charged_bytes,
        baseline + (160 << 20)
    );
    assert_eq!(xyg_wasm_geo_transport_acquire(a), STATUS_OK);
    assert_eq!(
        observer.stats().process_charged_bytes,
        baseline + (160 << 20)
    );
    assert_eq!(xyg_wasm_geo_transport_acquire(b), STATUS_OK);
    assert_eq!(
        observer.stats().process_charged_bytes,
        baseline + (320 << 20)
    );
    assert_eq!(xyg_wasm_geo_transport_acquire(c), STATUS_RESOURCE_LIMIT);
    assert_eq!(
        observer.stats().process_charged_bytes,
        baseline + (320 << 20)
    );
    assert_eq!(
        xyg_wasm_arena_resize(a, (128 << 20) + 1),
        STATUS_RESOURCE_LIMIT
    );
    assert_eq!(xyg_wasm_arena_resize(a, 8), STATUS_OK);
    assert_eq!(xyg_wasm_scene_prepare(a, 1, 0, 8), STATUS_INVALID_ARGUMENT);
    assert_eq!(xyg_wasm_arena_len(a), 0);
    assert_eq!(xyg_wasm_output_len(a), 0);
    assert_eq!(xyg_wasm_arena_resize(a, 8), STATUS_OK);
    assert_eq!(xyg_wasm_scene_validate(a, 2, 0, 8), STATUS_INVALID_ARGUMENT);
    // Every ordinary product lane rejects before inspecting hostile staged
    // bytes. Read-only diagnostics and lifecycle exports remain available.
    let lanes: [extern "C" fn(u32, usize, usize) -> i32; 5] = [
        xyg_wasm_temporal_execute,
        xyg_wasm_temporal_graph_execute,
        xyg_wasm_graphforge_compose,
        xyg_wasm_compound_transition,
        xyg_wasm_ticks_resolve,
    ];
    for lane in lanes {
        assert_eq!(xyg_wasm_arena_resize(a, 8), STATUS_OK);
        assert_eq!(lane(a, usize::MAX, usize::MAX), STATUS_INVALID_ARGUMENT);
        assert_eq!(xyg_wasm_arena_len(a), 0);
    }
    for lane in [
        xyg_wasm_geo_column_ingest,
        xyg_wasm_geo_scene_compile,
        xyg_wasm_geo_viewport_execute,
        xyg_wasm_geo_catalog_compile,
        xyg_wasm_scene_compile,
        xyg_wasm_scene_compile_prepare,
    ] {
        assert_eq!(xyg_wasm_arena_resize(a, 8), STATUS_OK);
        assert_eq!(lane(a, 3, usize::MAX, usize::MAX), STATUS_INVALID_ARGUMENT);
    }
    assert_eq!(xyg_wasm_instance_dispose(a), STATUS_OK);
    assert_eq!(
        observer.stats().process_charged_bytes,
        baseline + (160 << 20)
    );
    assert_eq!(xyg_wasm_geo_transport_acquire(c), STATUS_OK);
    assert_eq!(
        xyg_wasm_arena_resize(c, (1 << 20) + 1),
        STATUS_RESOURCE_LIMIT
    );
    assert_eq!(xyg_wasm_instance_dispose(b), STATUS_OK);
    assert_eq!(xyg_wasm_instance_dispose(c), STATUS_OK);
    assert_eq!(observer.stats().process_charged_bytes, baseline);
}
