//! Packed thin-WASM compound disclosure transition framing (#34).

use crate::{fail, Instance, STATUS_INVALID_ARGUMENT, STATUS_OK, STATUS_RESOURCE_LIMIT};
use xyg_engine::graph_style::compound_collapse_transition;

const REQUEST_MAGIC: &[u8; 4] = b"XYGC";
const REQUEST_VERSION: u32 = 1;
const REQUEST_HEADER_BYTES: usize = 40;
const REQUEST_PLANE_BYTES_PER_NODE: usize = 18;
const REQUEST_VERSION_OFFSET: usize = 4;
const REQUEST_HEADER_BYTES_OFFSET: usize = 8;
const REQUEST_ACTION_OFFSET: usize = 12;
const REQUEST_LOD_TIER_OFFSET: usize = 16;
const REQUEST_NODE_COUNT_OFFSET: usize = 20;
const REQUEST_TARGET_ID_OFFSET: usize = 24;
const REQUEST_RESERVED_OFFSET: usize = 32;
const OUTPUT_MAGIC: &[u8; 4] = b"XYCO";
const OUTPUT_VERSION: u32 = 1;
const OUTPUT_HEADER_BYTES: usize = 16;
const OUTPUT_VERSION_OFFSET: usize = 4;
const OUTPUT_HEADER_BYTES_OFFSET: usize = 8;
const OUTPUT_CHANGED_OFFSET: usize = 12;
const OUTPUT_COLLAPSED_OFFSET: usize = 16;

fn u32_at(bytes: &[u8], offset: usize) -> Option<u32> {
    Some(u32::from_le_bytes(
        bytes.get(offset..offset + 4)?.try_into().ok()?,
    ))
}

fn u64_at(bytes: &[u8], offset: usize) -> Option<u64> {
    Some(u64::from_le_bytes(
        bytes.get(offset..offset + 8)?.try_into().ok()?,
    ))
}

pub(crate) fn execute(instance: &mut Instance, offset: usize, length: usize) -> i32 {
    instance.output = Vec::new();
    // Staging is single-use. Taking the arena before validation ensures both
    // successful and rejected requests release their backing allocation.
    let arena = std::mem::take(&mut instance.arena);
    let Some(end) = offset.checked_add(length) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "compound transition range overflow",
        );
    };
    let Some(request) = arena.get(offset..end) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "compound transition range lies outside the arena",
        );
    };
    if request.get(..4) != Some(REQUEST_MAGIC)
        || u32_at(request, REQUEST_VERSION_OFFSET) != Some(REQUEST_VERSION)
        || u32_at(request, REQUEST_HEADER_BYTES_OFFSET) != Some(REQUEST_HEADER_BYTES as u32)
        || u64_at(request, REQUEST_RESERVED_OFFSET) != Some(0)
    {
        return fail(instance, STATUS_INVALID_ARGUMENT, "malformed XYGC header");
    }
    let (Some(action), Some(lod_tier), Some(n), Some(target_id)) = (
        u32_at(request, REQUEST_ACTION_OFFSET),
        u32_at(request, REQUEST_LOD_TIER_OFFSET),
        u32_at(request, REQUEST_NODE_COUNT_OFFSET).map(|value| value as usize),
        u64_at(request, REQUEST_TARGET_ID_OFFSET),
    ) else {
        return fail(instance, STATUS_INVALID_ARGUMENT, "truncated XYGC header");
    };
    let Some(expected) = n
        .checked_mul(REQUEST_PLANE_BYTES_PER_NODE)
        .and_then(|planes| REQUEST_HEADER_BYTES.checked_add(planes))
    else {
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "XYGC plane length overflow",
        );
    };
    if n == 0 || expected != request.len() {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "XYGC planes have invalid lengths",
        );
    }
    let output_len = OUTPUT_HEADER_BYTES.saturating_add(n);
    let peak = expected
        .checked_add(n.saturating_mul(128))
        .and_then(|value| value.checked_add(output_len));
    if peak.is_none_or(|value| value > instance.max_arena_bytes) {
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "compound transition peak memory exceeds budget",
        );
    }
    let ids_start = REQUEST_HEADER_BYTES;
    let parents_start = ids_start + n * 8;
    let validity_start = parents_start + n * 8;
    let collapsed_start = validity_start + n;
    let decode_u64 = |start: usize| -> Option<Vec<u64>> {
        (0..n)
            .map(|index| u64_at(request, start + index * 8))
            .collect()
    };
    let (Some(node_ids), Some(parents)) = (decode_u64(ids_start), decode_u64(parents_start)) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "truncated XYGC integer plane",
        );
    };
    let validity = &request[validity_start..collapsed_start];
    let collapsed = &request[collapsed_start..collapsed_start + n];
    let (Ok(action), Ok(lod_tier)) = (u8::try_from(action), u8::try_from(lod_tier)) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "XYGC action or LOD tier is out of range",
        );
    };
    let mut next = vec![0; n];
    let Some(changed) = compound_collapse_transition(
        &node_ids, &parents, validity, collapsed, target_id, action, lod_tier, &mut next,
    ) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "compound transition was refused",
        );
    };
    if output_len > instance.max_arena_bytes
        || instance.output.try_reserve_exact(output_len).is_err()
    {
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "compound transition output exceeds budget",
        );
    }
    instance.output.resize(output_len, 0);
    instance.output[..4].copy_from_slice(OUTPUT_MAGIC);
    instance.output[OUTPUT_VERSION_OFFSET..OUTPUT_VERSION_OFFSET + 4]
        .copy_from_slice(&OUTPUT_VERSION.to_le_bytes());
    instance.output[OUTPUT_HEADER_BYTES_OFFSET..OUTPUT_HEADER_BYTES_OFFSET + 4]
        .copy_from_slice(&(OUTPUT_HEADER_BYTES as u32).to_le_bytes());
    instance.output[OUTPUT_CHANGED_OFFSET] = u8::from(changed);
    instance.output[OUTPUT_COLLAPSED_OFFSET..].copy_from_slice(&next);
    instance.last_error.clear();
    STATUS_OK
}
