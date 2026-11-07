//! Retained Worker acquisition and shared XYFX export. No product policy here.
use super::{fail, Instance, STATUS_INVALID_ARGUMENT, STATUS_OK, STATUS_RESOURCE_LIMIT};
pub(super) fn execute(i: &mut Instance, offset: usize, length: usize) -> i32 {
    if i.aggregate_job.is_some()
        || i.stream_aggregate_job.is_some()
        || i.graph_job.is_some()
        || i.compile_job.is_some()
        || i.temporal.is_some()
    {
        return fail(
            i,
            STATUS_INVALID_ARGUMENT,
            "Frozen export requires a drained dedicated Worker",
        );
    }
    i.output = Vec::new();
    let arena = std::mem::take(&mut i.arena);
    let mut unavailable = false;
    let mut resource = false;
    let result = (|| {
        let bytes = arena
            .get(offset..offset.checked_add(length).ok_or(())?)
            .ok_or(())?;
        if bytes.len() < 64 || &bytes[..4] != b"XYFX" || bytes[4..8] != 1u32.to_le_bytes() {
            return Err(());
        }
        let u32at = |at| u32::from_le_bytes(bytes[at..at + 4].try_into().unwrap());
        let u64at = |at| u64::from_le_bytes(bytes[at..at + 8].try_into().unwrap());
        let budget = usize::try_from(u64at(48))
            .map_err(|_| ())?
            .min(i.max_arena_bytes);
        let retained = i
            .graph_session
            .as_ref()
            .map_or(0, |s| s.retained_budget())
            .checked_add(i.temporal_graph.as_ref().map_or(0, |g| g.retained_bytes()))
            .ok_or(())?;
        let available = budget.checked_sub(retained).ok_or(())?;
        if u32at(8) != 0 {
            return xyg_engine::temporal_graph_export::execute_packet(bytes, available).map_err(
                |e| {
                    unavailable = e == xyg_engine::temporal::TemporalError::UnitUnsupported;
                    resource = matches!(
                        e,
                        xyg_engine::temporal::TemporalError::BudgetExceeded
                            | xyg_engine::temporal::TemporalError::CapacityExceeded
                    );
                    ()
                },
            );
        }
        if bytes[16..20] != [0; 4]
            || u32at(20) > 1
            || bytes.len()
                != 64usize
                    .checked_add(usize::try_from(u64at(56)).map_err(|_| ())?)
                    .and_then(|n| n.checked_add(16))
                    .ok_or(())?
        {
            return Err(());
        }
        let window = if u32at(20) == 0 {
            if bytes[32..48] != [0; 16] {
                return Err(());
            }
            None
        } else {
            Some((
                i64::from_le_bytes(bytes[32..40].try_into().unwrap()),
                i64::from_le_bytes(bytes[40..48].try_into().unwrap()),
            ))
        };
        let timezone = std::str::from_utf8(&bytes[64..bytes.len() - 16]).map_err(|_| ())?;
        let graph = i.temporal_graph.as_ref().ok_or(())?;
        let session = i.graph_session.as_ref().ok_or(())?;
        graph
            .freeze(
                session,
                u64at(24),
                u32at(12),
                window,
                timezone,
                std::array::from_fn(|i| {
                    f32::from_le_bytes(
                        bytes[bytes.len() - 16 + i * 4..bytes.len() - 12 + i * 4]
                            .try_into()
                            .unwrap(),
                    )
                }),
                available,
            )
            .map_err(|_| ())
    })();
    match result {
        Ok(bytes) if bytes.len() <= i.max_arena_bytes => {
            i.output = bytes;
            i.last_error.clear();
            STATUS_OK
        }
        Ok(_) => fail(
            i,
            STATUS_RESOURCE_LIMIT,
            "frozen graph output exceeds Worker budget",
        ),
        Err(()) if unavailable=>fail(i,STATUS_RESOURCE_LIMIT,"XYG_FROZEN_PNG_UNAVAILABLE: shared Rust PNG cannot fit the unchanged browser artifact caps"),
        Err(()) if resource=>fail(i,STATUS_RESOURCE_LIMIT,"frozen export exceeds the operation reservation"),
        Err(()) => fail(i, STATUS_INVALID_ARGUMENT, "frozen graph request rejected"),
    }
}
