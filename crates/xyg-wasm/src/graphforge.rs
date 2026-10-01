//! Direct-browser GraphForge result compositions (spec/design/graphforge-compositions.md §6.3).
//!
//! The staged bytes are one `XYGQ` request; the output is the `XYGF`
//! document the native C ABI returns for the same bytes (compositions and
//! error documents alike), so native/WASM equivalence is a byte comparison.

use super::{fail, Instance, STATUS_INVALID_ARGUMENT, STATUS_OK, STATUS_RESOURCE_LIMIT};
use xyg_engine::graphforge::compose::compose_bytes;

pub(super) fn execute(instance: &mut Instance, offset: usize, length: usize) -> i32 {
    instance.output = Vec::new();
    // Staging is single-use: take it before validation so both successful and
    // rejected requests release their backing allocation.
    let arena = std::mem::take(&mut instance.arena);
    let Some(end) = offset.checked_add(length) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "graphforge request range overflow",
        );
    };
    let Some(request) = arena.get(offset..end) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "graphforge request range lies outside the arena",
        );
    };
    let document = match compose_bytes(request) {
        Ok(document) | Err(document) => document,
    };
    drop(arena);
    if document.len() > instance.max_arena_bytes {
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "graphforge composition exceeds the instance byte budget",
        );
    }
    instance.output = document;
    instance.last_error.clear();
    STATUS_OK
}
