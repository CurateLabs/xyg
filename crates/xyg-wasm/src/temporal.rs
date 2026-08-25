//! Packed direct-browser seam for the shared Rust TemporalController (#44).

use xyg_engine::temporal::TemporalError;
use xyg_engine::temporal_controller::{
    ControllerState, CoordinationEvent, PlaybackDirection, TemporalController,
};

use crate::{
    fail, Instance, STATUS_DISPOSED, STATUS_INVALID_ARGUMENT, STATUS_OK, STATUS_RESOURCE_LIMIT,
    STATUS_SELF_ECHO, STATUS_STALE_REVISION,
};

const COMMAND_MAGIC: &[u8; 4] = b"XYTC";
const RESPONSE_MAGIC: &[u8; 4] = b"XYTR";
const VERSION: u32 = 2;
const HEADER: usize = 16;
const RESPONSE_BYTES: usize = 176;

fn u32_at(bytes: &[u8], offset: usize) -> Option<u32> {
    Some(u32::from_le_bytes(
        bytes.get(offset..offset + 4)?.try_into().ok()?,
    ))
}

fn i32_at(bytes: &[u8], offset: usize) -> Option<i32> {
    Some(i32::from_le_bytes(
        bytes.get(offset..offset + 4)?.try_into().ok()?,
    ))
}

fn u64_at(bytes: &[u8], offset: usize) -> Option<u64> {
    Some(u64::from_le_bytes(
        bytes.get(offset..offset + 8)?.try_into().ok()?,
    ))
}

fn i64_at(bytes: &[u8], offset: usize) -> Option<i64> {
    Some(i64::from_le_bytes(
        bytes.get(offset..offset + 8)?.try_into().ok()?,
    ))
}

fn status(error: TemporalError) -> i32 {
    match error {
        TemporalError::Disposed => STATUS_DISPOSED,
        TemporalError::StaleRevision => STATUS_STALE_REVISION,
        TemporalError::SelfEcho => STATUS_SELF_ECHO,
        _ => STATUS_INVALID_ARGUMENT,
    }
}

fn put_u32(out: &mut [u8], offset: usize, value: u32) {
    out[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
}

fn put_i32(out: &mut [u8], offset: usize, value: i32) {
    out[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
}

fn put_u64(out: &mut [u8], offset: usize, value: u64) {
    out[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
}

fn put_i64(out: &mut [u8], offset: usize, value: i64) {
    out[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
}

fn response(state: &ControllerState, event: Option<&CoordinationEvent>, result: bool) -> Vec<u8> {
    let mut out = vec![0; RESPONSE_BYTES + state.selection.len() * 8];
    out[..4].copy_from_slice(RESPONSE_MAGIC);
    put_u32(&mut out, 4, VERSION);
    put_u32(
        &mut out,
        8,
        u32::from(result) | (u32::from(event.is_some()) << 1),
    );
    put_u32(&mut out, 12, state.selection.len() as u32);
    put_u64(&mut out, 16, state.instance_id);
    put_u64(&mut out, 24, state.group_id);
    put_i64(&mut out, 32, state.domain_start);
    put_i64(&mut out, 40, state.domain_end);
    put_i64(&mut out, 48, state.range_start);
    put_i64(&mut out, 56, state.range_end);
    put_i64(&mut out, 64, state.cursor);
    put_i64(&mut out, 72, state.window);
    put_i64(&mut out, 80, state.step);
    put_i32(&mut out, 88, state.direction as i32);
    put_u32(&mut out, 92, state.rate_milli);
    put_u32(&mut out, 96, u32::from(state.loop_enabled));
    put_u32(&mut out, 100, u32::from(state.playing));
    put_u32(&mut out, 104, u32::from(state.reduced_motion));
    put_u32(&mut out, 108, u32::from(state.disposed));
    put_u64(&mut out, 112, state.revision);
    if let Some(event) = event {
        put_u64(&mut out, 120, event.group_id);
        put_u64(&mut out, 128, event.source_instance);
        put_u64(&mut out, 136, event.revision);
        put_i64(&mut out, 144, event.range_start);
        put_i64(&mut out, 152, event.range_end);
        put_i64(&mut out, 160, event.cursor);
        put_i64(&mut out, 168, event.window);
    }
    for (index, id) in state.selection.iter().copied().enumerate() {
        put_u64(&mut out, RESPONSE_BYTES + index * 8, id);
    }
    out
}

fn selection_at(bytes: &[u8], count_offset: usize, ids_offset: usize) -> Option<Vec<u64>> {
    let count = usize::try_from(u32_at(bytes, count_offset)?).ok()?;
    if count > xyg_engine::temporal_controller::MAX_COORDINATED_SELECTION_IDS {
        return None;
    }
    let expected = ids_offset.checked_add(count.checked_mul(8)?)?;
    if bytes.len() != expected {
        return None;
    }
    (0..count)
        .map(|index| u64_at(bytes, ids_offset + index * 8))
        .collect()
}

pub(super) fn execute(instance: &mut Instance, offset: usize, length: usize) -> i32 {
    let Some(end) = offset.checked_add(length) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal command range overflow",
        );
    };
    if length < HEADER || end > instance.arena.len() {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal command is outside the staging arena",
        );
    }
    let command = &instance.arena[offset..end];
    if command.get(..4) != Some(COMMAND_MAGIC.as_slice()) || u32_at(command, 4) != Some(VERSION) {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "unsupported temporal command header",
        );
    }
    let Some(op) = u32_at(command, 8) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "truncated temporal command",
        );
    };

    if op == 1 {
        if length != 88 || instance.temporal.is_some() {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "temporal controller already exists or create is malformed",
            );
        }
        if !matches!(u32_at(command, 80), Some(0 | 1))
            || !matches!(u32_at(command, 84), Some(0 | 1))
        {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "temporal boolean fields must be zero or one",
            );
        }
        let Some(direction) = i32_at(command, 72).and_then(PlaybackDirection::from_i32) else {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "temporal direction must be -1 or 1",
            );
        };
        let created = TemporalController::create(
            u64_at(command, 16).unwrap_or(0),
            u64_at(command, 24).unwrap_or(0),
            i64_at(command, 32).unwrap_or(0),
            i64_at(command, 40).unwrap_or(0),
            i64_at(command, 48).unwrap_or(0),
            i64_at(command, 56).unwrap_or(-1),
            i64_at(command, 64).unwrap_or(0),
            direction,
            u32_at(command, 76).unwrap_or(0),
            u32_at(command, 80) == Some(1),
            u32_at(command, 84) == Some(1),
        );
        match created {
            Ok(controller) => instance.temporal = Some(controller),
            Err(error) => {
                return fail(
                    instance,
                    status(error),
                    "invalid temporal controller descriptor",
                )
            }
        }
    } else if instance.temporal.is_none() {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal controller is not initialized",
        );
    }

    let controller = instance
        .temporal
        .as_mut()
        .expect("created or checked above");
    let outcome = match op {
        1 => Ok(false),
        2 | 15 if length == HEADER => Ok(false),
        3 if length == 32 => controller
            .set_range(i64_at(command, 16).unwrap(), i64_at(command, 24).unwrap())
            .map(|_| false),
        4 if length == 24 => controller
            .set_cursor(i64_at(command, 16).unwrap())
            .map(|_| false),
        5 if length == HEADER => controller.step().map(|_| false),
        6 if length == HEADER => controller.play().map(|_| false),
        7 if length == HEADER => controller.pause().map(|_| false),
        8 if length == 20 => controller
            .set_rate_milli(u32_at(command, 16).unwrap())
            .map(|_| false),
        9 if length == 20 => PlaybackDirection::from_i32(i32_at(command, 16).unwrap())
            .ok_or(TemporalError::InvalidArgument)
            .and_then(|value| controller.set_direction(value))
            .map(|_| false),
        10 if length == 20 && matches!(u32_at(command, 16), Some(0 | 1)) => controller
            .set_loop(u32_at(command, 16) == Some(1))
            .map(|_| false),
        11 if length == 20 && matches!(u32_at(command, 16), Some(0 | 1)) => controller
            .set_reduced_motion(u32_at(command, 16) == Some(1))
            .map(|_| false),
        12 if length == 24 => controller.tick(i64_at(command, 16).unwrap()),
        13 => selection_at(command, 72, 80)
            .ok_or(TemporalError::InvalidArgument)
            .and_then(|selection| {
                controller.apply_event(&CoordinationEvent {
                    group_id: u64_at(command, 16).unwrap(),
                    source_instance: u64_at(command, 24).unwrap(),
                    revision: u64_at(command, 32).unwrap(),
                    range_start: i64_at(command, 40).unwrap(),
                    range_end: i64_at(command, 48).unwrap(),
                    cursor: i64_at(command, 56).unwrap(),
                    window: i64_at(command, 64).unwrap(),
                    selection,
                })
            }),
        14 if length == HEADER => controller.dispose().map(|_| false),
        16 => selection_at(command, 16, 24)
            .ok_or(TemporalError::InvalidArgument)
            .and_then(|selection| controller.set_selection(&selection))
            .map(|_| false),
        _ => Err(TemporalError::InvalidArgument),
    };
    let result = match outcome {
        Ok(value) => value,
        Err(error) => {
            return fail(
                instance,
                status(error),
                "temporal controller command failed",
            )
        }
    };
    let event = controller.take_outbound();
    instance.output = response(controller.state(), event.as_ref(), result);
    if instance.output.len() > instance.max_arena_bytes {
        instance.output.clear();
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "temporal response exceeds the instance budget",
        );
    }
    STATUS_OK
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn selection_decode_rejects_counts_above_the_product_limit() {
        let mut command = [0_u8; 24];
        put_u32(
            &mut command,
            16,
            u32::try_from(xyg_engine::temporal_controller::MAX_COORDINATED_SELECTION_IDS + 1)
                .unwrap(),
        );
        assert_eq!(selection_at(&command, 16, 24), None);
    }

    #[test]
    fn create_step_and_dispose_are_packed_and_rust_owned() {
        let mut instance = Instance {
            arena: vec![0; 88],
            output: vec![],
            max_arena_bytes: 4096,
            last_error: String::new(),
            latest_sequence: 0,
            cancelled_through: 0,
            copy_count: 0,
            copy_bytes: 0,
            arena_high_water: 0,
            last_scene_records: 0,
            last_scene_styles: 0,
            aggregate_job: None,
            stream_aggregate_job: None,
            aggregate_sequence: 0,
            temporal: None,
            temporal_graph: None,
            graph_job: None,
            compile_job: None,
        };
        instance.arena[..4].copy_from_slice(COMMAND_MAGIC);
        put_u32(&mut instance.arena, 4, VERSION);
        put_u32(&mut instance.arena, 8, 1);
        put_u64(&mut instance.arena, 16, 7);
        put_u64(&mut instance.arena, 24, 9);
        put_i64(&mut instance.arena, 32, 0);
        put_i64(&mut instance.arena, 40, 100);
        put_i64(&mut instance.arena, 48, 10);
        put_i64(&mut instance.arena, 56, 20);
        put_i64(&mut instance.arena, 64, 5);
        put_i32(&mut instance.arena, 72, 1);
        put_u32(&mut instance.arena, 76, 1000);
        assert_eq!(execute(&mut instance, 0, 88), STATUS_OK);
        assert_eq!(i64_at(&instance.output, 64), Some(10));
        instance.arena.resize(16, 0);
        instance.arena[..4].copy_from_slice(COMMAND_MAGIC);
        put_u32(&mut instance.arena, 4, VERSION);
        put_u32(&mut instance.arena, 8, 5);
        assert_eq!(execute(&mut instance, 0, 16), STATUS_OK);
        assert_eq!(i64_at(&instance.output, 64), Some(15));
        assert_eq!(u32_at(&instance.output, 8).unwrap() & 2, 2);
        instance.arena.resize(56, 0);
        instance.arena[..4].copy_from_slice(COMMAND_MAGIC);
        put_u32(&mut instance.arena, 4, VERSION);
        put_u32(&mut instance.arena, 8, 16);
        put_u32(&mut instance.arena, 16, 4);
        for (index, id) in [u64::MAX, 7, 7, 0].into_iter().enumerate() {
            put_u64(&mut instance.arena, 24 + index * 8, id);
        }
        assert_eq!(execute(&mut instance, 0, 56), STATUS_OK);
        assert_eq!(u32_at(&instance.output, 12), Some(3));
        assert_eq!(u64_at(&instance.output, 176), Some(0));
        assert_eq!(u64_at(&instance.output, 184), Some(7));
        assert_eq!(u64_at(&instance.output, 192), Some(u64::MAX));
        instance.arena.resize(16, 0);
        instance.arena[..4].copy_from_slice(COMMAND_MAGIC);
        put_u32(&mut instance.arena, 4, VERSION);
        put_u32(&mut instance.arena, 8, 14);
        assert_eq!(execute(&mut instance, 0, 16), STATUS_OK);
        assert_eq!(u32_at(&instance.output, 108), Some(1));
    }
}
