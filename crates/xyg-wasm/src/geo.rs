//! Single-use GeoColumn ingress; product validation stays in the shared engine.
use super::{
    fail, Instance, STATUS_CANCELLED, STATUS_INVALID_ARGUMENT, STATUS_OK, STATUS_RESOURCE_LIMIT,
    STATUS_STALE_SEQUENCE,
};
use xyg_engine::geo::{column_from_descriptor_bytes, GeoError};

pub(super) fn execute(instance: &mut Instance, sequence: u32, offset: usize, length: usize) -> i32 {
    execute_with(instance, sequence, offset, length, |request, budget| {
        column_from_descriptor_bytes(request, budget)
            .map(|column| column.canonical_metadata())
            .map_err(|error| (error.code(), error == GeoError::ResourceLimit))
    })
}

pub(super) fn execute_scene(
    instance: &mut Instance,
    sequence: u32,
    offset: usize,
    length: usize,
) -> i32 {
    execute_with(instance, sequence, offset, length, |request, budget| {
        xyg_engine::geo_scene::compile_geo_scene(request, budget)
            .map_err(|error| (error.code(), error.is_resource()))
    })
}

pub(super) fn execute_viewport(
    instance: &mut Instance,
    sequence: u32,
    offset: usize,
    length: usize,
) -> i32 {
    execute_with(instance, sequence, offset, length, |request, budget| {
        xyg_engine::geo_viewport_protocol::execute(request, budget)
            .map_err(|error| (error.code(), error == GeoError::ResourceLimit))
    })
}

pub(super) fn execute_catalog(
    instance: &mut Instance,
    sequence: u32,
    offset: usize,
    length: usize,
) -> i32 {
    execute_with(instance, sequence, offset, length, |request, budget| {
        xyg_engine::geo_layers_protocol::execute(request, budget)
            .map_err(|error| (error.code(), error == GeoError::ResourceLimit))
    })
}

// One lifecycle body serves all geographic processors. Only the bounded
// request-level dispatch is indirect; Rust geometry loops retain normal O3.
type GeoProcessor = fn(&[u8], usize) -> Result<Vec<u8>, (&'static str, bool)>;

#[inline(never)]
fn execute_with(
    instance: &mut Instance,
    sequence: u32,
    offset: usize,
    length: usize,
    processor: GeoProcessor,
) -> i32 {
    // Rejected old calls must not consume the staging owned by a newer
    // aggregate, streamed aggregate, graph or compile operation.
    let newest = instance
        .latest_sequence
        .max(instance.aggregate_sequence)
        .max(instance.compile_job.as_ref().map_or(0, |job| job.sequence))
        .max(instance.graph_job.as_ref().map_or(0, |job| job.sequence));
    let rejected = if sequence == 0 {
        Some((STATUS_INVALID_ARGUMENT, GeoError::InvalidArgument.code()))
    } else if sequence <= instance.cancelled_through {
        Some((STATUS_CANCELLED, "request was cancelled"))
    } else if sequence <= newest {
        Some((STATUS_STALE_SEQUENCE, "request sequence is stale"))
    } else {
        None
    };
    if let Some((status, message)) = rejected {
        if instance.aggregate_job.is_none()
            && instance.stream_aggregate_job.is_none()
            && instance.graph_job.is_none()
            && instance.compile_job.is_none()
        {
            instance.arena = Vec::new();
            instance.output = Vec::new();
        }
        return fail(instance, status, message);
    }
    instance.output = Vec::new();
    instance.clear_aggregate();
    instance.graph_job = None;
    instance.compile_job = None;
    let arena = std::mem::take(&mut instance.arena);
    instance.latest_sequence = sequence;
    let Some(request) = offset
        .checked_add(length)
        .and_then(|end| arena.get(offset..end))
    else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            GeoError::InvalidArgument.code(),
        );
    };
    // Include staging capacity outside the request (prefixes / previous capacity).
    let budget = instance
        .max_arena_bytes
        .saturating_sub(arena.capacity().saturating_sub(length));
    let result = processor(request, budget);
    drop(arena);
    match result {
        Ok(output) => {
            instance.output = output;
            instance.last_error.clear();
            STATUS_OK
        }
        Err((code, resource)) => fail(
            instance,
            if resource {
                STATUS_RESOURCE_LIMIT
            } else {
                STATUS_INVALID_ARGUMENT
            },
            code,
        ),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        with_instance_mut, xyg_wasm_arena_resize, xyg_wasm_geo_column_ingest,
        xyg_wasm_instance_dispose, xyg_wasm_instance_new,
    };

    fn point_request(features: usize) -> Vec<u8> {
        let mut request = vec![0; 64 + features.div_ceil(8) * 8];
        request[..4].copy_from_slice(b"XYGD");
        for (offset, value) in [(4, 1u32), (8, 1), (12, 4326)] {
            request[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
        }
        request[24..32].copy_from_slice(&(features as u64).to_le_bytes());
        request // null Point features deliberately have no source vertices/IDs.
    }
    fn stage(handle: u32, request: &[u8]) {
        assert_eq!(xyg_wasm_arena_resize(handle, request.len()), STATUS_OK);
        with_instance_mut(handle, |instance| instance.arena.copy_from_slice(request)).unwrap();
    }
    fn scene_request() -> Vec<u8> {
        let descriptor = point_request(2);
        let mut request = vec![0u8; 128];
        request[..4].copy_from_slice(b"XYGP");
        for (offset, value) in [(4, 1u32), (8, 128), (16, 4326)] {
            request[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
        }
        for (offset, value) in [(48, 800f64), (56, 600.0), (80, 6.0), (88, 1.0)] {
            request[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        }
        request[104..112].copy_from_slice(&(descriptor.len() as u64).to_le_bytes());
        request.extend(descriptor);
        request
    }
    #[test]
    fn catalog_output_resource_cancel_recovery_and_dispose() {
        let descriptor = point_request(2);
        let mut request = vec![0u8; 512];
        request[..4].copy_from_slice(b"XYLK");
        for (at, n) in [(4, 1u32), (8, 1), (16, 4326), (136, 1)] {
            request[at..at + 4].copy_from_slice(&n.to_le_bytes());
        }
        for (at, n) in [(48, 800f64), (56, 600f64)] {
            request[at..at + 8].copy_from_slice(&n.to_le_bytes());
        }
        request[392..400].copy_from_slice(&(descriptor.len() as u64).to_le_bytes());
        request.extend_from_slice(&descriptor);
        let h = xyg_wasm_instance_new(8 << 20);
        stage(h, &request);
        assert_eq!(
            crate::xyg_wasm_geo_catalog_compile(h, 1, 0, request.len()),
            STATUS_OK
        );
        with_instance_mut(h, |i| {
            assert_eq!(&i.output[..4], b"XYLM");
            assert_eq!(i.arena.capacity(), 0);
        })
        .unwrap();
        stage(h, &request);
        assert_eq!(crate::xyg_wasm_cancel(h, 2), STATUS_OK);
        assert_eq!(
            crate::xyg_wasm_geo_catalog_compile(h, 2, 0, request.len()),
            STATUS_CANCELLED
        );
        stage(h, &request);
        assert_eq!(
            crate::xyg_wasm_geo_catalog_compile(h, 3, 0, request.len()),
            STATUS_OK
        );
        let mut bad = request.clone();
        bad[96] = 1;
        stage(h, &bad);
        assert_eq!(
            crate::xyg_wasm_geo_catalog_compile(h, 4, 0, bad.len()),
            STATUS_INVALID_ARGUMENT
        );
        with_instance_mut(h, |i| {
            assert_eq!(i.arena.capacity(), 0);
            assert_eq!(i.output.capacity(), 0);
        })
        .unwrap();
        stage(h, &request);
        assert_eq!(
            crate::xyg_wasm_geo_catalog_compile(h, 5, 0, request.len()),
            STATUS_OK
        );
        assert_eq!(xyg_wasm_instance_dispose(h), STATUS_OK);
        assert_eq!(
            crate::xyg_wasm_geo_catalog_compile(h, 6, 0, request.len()),
            crate::STATUS_INVALID_HANDLE
        );
        let h = xyg_wasm_instance_new(65536);
        stage(h, &request);
        assert_eq!(
            crate::xyg_wasm_geo_catalog_compile(h, 1, 0, request.len()),
            STATUS_RESOURCE_LIMIT
        );
        assert_eq!(xyg_wasm_instance_dispose(h), STATUS_OK);
    }
    #[test]
    fn scene_output_resource_cancel_recovery_and_dispose_are_atomic() {
        let request = scene_request();
        let handle = xyg_wasm_instance_new(65536);
        stage(handle, &request);
        assert_eq!(
            crate::xyg_wasm_geo_scene_compile(handle, 1, 0, request.len()),
            STATUS_OK
        );
        with_instance_mut(handle, |instance| {
            assert_eq!(&instance.output[..4], b"XYGS");
            assert_eq!(instance.arena.capacity(), 0);
        })
        .unwrap();
        stage(handle, &request);
        assert_eq!(crate::xyg_wasm_cancel(handle, 2), STATUS_OK);
        assert_eq!(
            crate::xyg_wasm_geo_scene_compile(handle, 2, 0, request.len()),
            STATUS_CANCELLED
        );
        stage(handle, &request);
        assert_eq!(
            crate::xyg_wasm_geo_scene_compile(handle, 3, 0, request.len()),
            STATUS_OK
        );
        let mut bad = request.clone();
        bad[80..88].copy_from_slice(&f64::MAX.to_le_bytes());
        stage(handle, &bad);
        assert_eq!(
            crate::xyg_wasm_geo_scene_compile(handle, 4, 0, bad.len()),
            STATUS_INVALID_ARGUMENT
        );
        with_instance_mut(handle, |instance| {
            assert_eq!(instance.arena.capacity(), 0);
            assert_eq!(instance.output.capacity(), 0);
        })
        .unwrap();
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
        assert_eq!(
            crate::xyg_wasm_geo_scene_compile(handle, 5, 0, request.len()),
            crate::STATUS_INVALID_HANDLE
        );
        let handle = xyg_wasm_instance_new(8192);
        stage(handle, &request);
        assert_eq!(
            crate::xyg_wasm_geo_scene_compile(handle, 1, 0, request.len()),
            STATUS_RESOURCE_LIMIT
        );
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }
    #[test]
    fn viewport_output_cancel_recovery_and_dispose_are_atomic() {
        let mut request = vec![0u8; 128];
        request[..4].copy_from_slice(b"XYVC");
        for (offset, value) in [(4, 1u32), (12, 4326)] {
            request[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
        }
        for (offset, value) in [(48, 800f64), (56, 600.0)] {
            request[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        }
        let handle = xyg_wasm_instance_new(65536);
        stage(handle, &request);
        assert_eq!(
            crate::xyg_wasm_geo_viewport_execute(handle, 1, 0, request.len()),
            STATUS_OK
        );
        with_instance_mut(handle, |instance| {
            assert_eq!(&instance.output[..4], b"XYVR");
            assert_eq!(instance.arena.capacity(), 0);
        })
        .unwrap();
        stage(handle, &request);
        assert_eq!(crate::xyg_wasm_cancel(handle, 2), STATUS_OK);
        assert_eq!(
            crate::xyg_wasm_geo_viewport_execute(handle, 2, 0, request.len()),
            STATUS_CANCELLED
        );
        stage(handle, &request);
        assert_eq!(
            crate::xyg_wasm_geo_viewport_execute(handle, 3, 0, request.len()),
            STATUS_OK
        );
        let mut bad = request.clone();
        bad[48..56].copy_from_slice(&f64::MAX.to_le_bytes());
        stage(handle, &bad);
        assert_eq!(
            crate::xyg_wasm_geo_viewport_execute(handle, 4, 0, bad.len()),
            STATUS_INVALID_ARGUMENT
        );
        with_instance_mut(handle, |instance| {
            assert_eq!(instance.arena.capacity(), 0);
            assert_eq!(instance.output.capacity(), 0);
        })
        .unwrap();
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
        assert_eq!(
            crate::xyg_wasm_geo_viewport_execute(handle, 5, 0, request.len()),
            crate::STATUS_INVALID_HANDLE
        );
    }

    #[test]
    fn scene_framing_rejects_all_truncation_before_projection() {
        let request = scene_request();
        for end in 0..request.len() {
            assert!(xyg_engine::geo_scene::compile_geo_scene(&request[..end], 65536).is_err());
        }
    }
    #[test]
    fn packed_and_typed_ingress_feed_identical_rebuildable_caches() {
        use xyg_engine::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
        use xyg_engine::geo_viewport::GeoViewport;
        let xy = [-104.9903f64, 39.7392, -104.9902, 39.7393];
        let validity = [1, 0, 1];
        let ids = [10u64, u64::MAX, 12];
        let direct = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg4326,
            xy: &xy,
            validity: &validity,
            feature_ids: Some(&ids),
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        let mut request = vec![0u8; 128];
        request[..4].copy_from_slice(b"XYGD");
        for (offset, value) in [(4, 1u32), (8, 1), (12, 4326), (16, 1)] {
            request[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
        }
        request[24..32].copy_from_slice(&3u64.to_le_bytes());
        request[32..40].copy_from_slice(&2u64.to_le_bytes());
        for (i, value) in xy.into_iter().enumerate() {
            request[64 + i * 8..72 + i * 8].copy_from_slice(&value.to_le_bytes());
        }
        request[96..99].copy_from_slice(&validity);
        for (i, value) in ids.into_iter().enumerate() {
            request[104 + i * 8..112 + i * 8].copy_from_slice(&value.to_le_bytes());
        }
        let decoded = column_from_descriptor_bytes(&request, 65536).unwrap();
        assert_eq!(direct.canonical_metadata(), decoded.canonical_metadata());
        assert_eq!(decoded.feature_ids(), ids);
        let viewport = GeoViewport::new(
            GeoCrs::Epsg4326,
            -104.9903,
            39.7392,
            16.0,
            800.0,
            600.0,
            0.0,
            0.0,
            true,
        )
        .unwrap();
        assert_eq!(
            viewport.project_column(&direct).unwrap(),
            viewport.project_column(&decoded).unwrap()
        );
    }

    #[test]
    fn rejected_old_geo_calls_preserve_newer_aggregate_staging() {
        let mut aggregate = vec![0u8; 64];
        aggregate[..4].copy_from_slice(b"XYAG");
        for (offset, value) in [(4, 1u32), (8, 64), (16, 2), (20, 4), (24, 4)] {
            aggregate[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
        }
        for (offset, value) in [(32, 0f64), (40, 1.0), (48, 0.0), (56, 1.0)] {
            aggregate[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        }
        for _ in 0..4 {
            aggregate.extend_from_slice(&0.5f64.to_le_bytes());
        }
        let handle = xyg_wasm_instance_new(1 << 20);
        stage(handle, &aggregate);
        assert_eq!(
            crate::xyg_wasm_aggregate_bin2d(handle, 4, 0, aggregate.len()),
            crate::STATUS_PENDING
        );
        assert_eq!(crate::xyg_wasm_cancel(handle, 2), STATUS_OK);
        for (sequence, status) in [
            (0, STATUS_INVALID_ARGUMENT),
            (2, STATUS_CANCELLED),
            (3, STATUS_STALE_SEQUENCE),
        ] {
            assert_eq!(
                xyg_wasm_geo_column_ingest(handle, sequence, usize::MAX, 0),
                status
            );
            assert_eq!(
                crate::xyg_wasm_geo_scene_compile(handle, sequence, usize::MAX, 0),
                status
            );
            assert_eq!(
                crate::xyg_wasm_geo_viewport_execute(handle, sequence, usize::MAX, 0),
                status
            );
            with_instance_mut(handle, |instance| {
                assert_eq!(instance.arena, aggregate);
                assert!(instance.aggregate_job.is_some());
                assert_eq!(instance.aggregate_sequence, 4);
            })
            .unwrap();
        }
        assert_eq!(crate::xyg_wasm_aggregate_step(handle, 4, 2), STATUS_OK);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn pending_compile_sequence_is_protected_before_publication() {
        let handle = xyg_wasm_instance_new(65536);
        let request = point_request(2);
        stage(handle, &request);
        with_instance_mut(handle, |instance| {
            instance.latest_sequence = 1;
            instance.compile_job = Some(crate::CompileJob {
                sequence: 4,
                offset: 0,
                length: request.len(),
                records_total: 2,
                records_processed: 0,
                phase: 0,
                paint: false,
            });
        })
        .unwrap();
        assert_eq!(
            xyg_wasm_geo_column_ingest(handle, 3, 0, request.len()),
            STATUS_STALE_SEQUENCE
        );
        with_instance_mut(handle, |instance| {
            assert_eq!(instance.arena, request);
            assert_eq!(instance.compile_job.as_ref().unwrap().sequence, 4);
        })
        .unwrap();
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn generated_identity_plane_is_in_peak_budget() {
        let request = point_request(1024);
        let handle = xyg_wasm_instance_new(10000);
        stage(handle, &request);
        assert_eq!(
            xyg_wasm_geo_column_ingest(handle, 1, 0, request.len()),
            STATUS_RESOURCE_LIMIT
        );
        with_instance_mut(handle, |instance| {
            assert_eq!(instance.last_error, GeoError::ResourceLimit.code());
            assert_eq!(instance.arena.capacity(), 0);
            assert_eq!(instance.output.capacity(), 0);
        })
        .unwrap();
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }
    #[test]
    fn source_is_released_on_success_error_cancel_and_stale() {
        let request = point_request(2);
        let handle = xyg_wasm_instance_new(65536);
        stage(handle, &request);
        assert_eq!(
            xyg_wasm_geo_column_ingest(handle, 1, 0, request.len()),
            STATUS_OK
        );
        let expected = column_from_descriptor_bytes(&request, 65536)
            .unwrap()
            .canonical_metadata();
        with_instance_mut(handle, |instance| {
            assert_eq!(instance.output, expected);
            assert_eq!(instance.arena.capacity(), 0);
        })
        .unwrap();
        stage(handle, &request);
        assert_eq!(
            xyg_wasm_geo_column_ingest(handle, 1, 0, request.len()),
            STATUS_STALE_SEQUENCE
        );
        stage(handle, &request);
        assert_eq!(crate::xyg_wasm_cancel(handle, 2), STATUS_OK);
        assert_eq!(
            xyg_wasm_geo_column_ingest(handle, 2, 0, request.len()),
            STATUS_CANCELLED
        );
        stage(handle, &request);
        assert_eq!(
            xyg_wasm_geo_column_ingest(handle, 3, usize::MAX, request.len()),
            STATUS_INVALID_ARGUMENT
        );
        with_instance_mut(handle, |instance| {
            assert_eq!(instance.arena.capacity(), 0);
            assert_eq!(instance.output.capacity(), 0);
        })
        .unwrap();
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
        assert_eq!(
            xyg_wasm_geo_column_ingest(handle, 4, 0, request.len()),
            crate::STATUS_INVALID_HANDLE
        );
    }
    #[test]
    fn bounded_parser_rejects_every_truncation_and_reserved_bit() {
        let request = point_request(2);
        for length in 0..request.len() {
            assert!(column_from_descriptor_bytes(&request[..length], 65536).is_err());
        }
        for offset in [4, 16, 20] {
            let mut bad = request.clone();
            bad[offset] = 2;
            assert!(column_from_descriptor_bytes(&bad, 65536).is_err());
        }
        let mut bad = request.clone();
        bad[66] = 1;
        assert_eq!(
            column_from_descriptor_bytes(&bad, 65536).unwrap_err(),
            GeoError::InvalidArgument
        );
        let mut bad = request.clone();
        bad.extend_from_slice(&[0; 8]);
        assert_eq!(
            column_from_descriptor_bytes(&bad, 65536).unwrap_err(),
            GeoError::InvalidArgument
        );
    }
}
