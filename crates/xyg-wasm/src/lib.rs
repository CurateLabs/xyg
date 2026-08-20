//! Raw, dependency-free WebAssembly boundary for direct-browser XYG.
//!
//! This crate owns only WASM memory, instance, status, and lifecycle concerns.
//! Product policy stays in `xyg-engine`; browser painting stays in TypeScript.
//! Bounded seams validate/prepare canonical Scene batches and compile packed
//! typed-column requests into those same batches. This is not a second browser
//! scene schema and does not claim complete public chart-spec coverage.

mod compile;

use std::sync::{Mutex, MutexGuard};
use xyg_engine::scene::{self, SceneError};

pub const WASM_ABI_VERSION: u32 = 3;
pub const STATUS_OK: i32 = 0;
pub const STATUS_INVALID_HANDLE: i32 = 1;
pub const STATUS_INVALID_ARGUMENT: i32 = 2;
pub const STATUS_RESOURCE_LIMIT: i32 = 3;
pub const STATUS_SCENE_VERSION: i32 = 4;
pub const STATUS_MALFORMED_SCENE: i32 = 5;
pub const STATUS_CANCELLED: i32 = 6;
pub const STATUS_STALE_SEQUENCE: i32 = 7;

pub const MAX_INSTANCES: usize = 64;
pub const MAX_ARENA_BYTES: usize = 64 * 1024 * 1024;
const HANDLE_SLOT_BITS: u32 = 8;
const HANDLE_SLOT_MASK: u32 = (1 << HANDLE_SLOT_BITS) - 1;
const MAX_GENERATION: u32 = u32::MAX >> HANDLE_SLOT_BITS;

#[derive(Debug)]
struct Instance {
    arena: Vec<u8>,
    output: Vec<u8>,
    max_arena_bytes: usize,
    last_error: String,
    latest_sequence: u32,
    cancelled_through: u32,
    copy_count: u32,
    copy_bytes: u64,
    last_scene_records: usize,
    last_scene_styles: usize,
}

#[derive(Debug)]
struct Slot {
    generation: u32,
    instance: Option<Instance>,
}

#[derive(Debug)]
struct Registry {
    slots: Vec<Slot>,
    next_generation: u32,
}

impl Registry {
    const fn new() -> Self {
        Self {
            slots: Vec::new(),
            next_generation: 1,
        }
    }

    fn allocate(&mut self, max_arena_bytes: usize) -> u32 {
        if max_arena_bytes == 0 || max_arena_bytes > MAX_ARENA_BYTES {
            return 0;
        }
        let slot_index =
            if let Some(index) = self.slots.iter().position(|slot| slot.instance.is_none()) {
                index
            } else if self.slots.len() < MAX_INSTANCES {
                self.slots.push(Slot {
                    generation: 0,
                    instance: None,
                });
                self.slots.len() - 1
            } else {
                return 0;
            };
        let generation = self.next_generation;
        if generation == 0 || generation > MAX_GENERATION {
            return 0;
        }
        self.next_generation = if generation == MAX_GENERATION {
            0
        } else {
            generation + 1
        };
        self.slots[slot_index] = Slot {
            generation,
            instance: Some(Instance {
                arena: Vec::new(),
                output: Vec::new(),
                max_arena_bytes,
                last_error: String::new(),
                latest_sequence: 0,
                cancelled_through: 0,
                copy_count: 0,
                copy_bytes: 0,
                last_scene_records: 0,
                last_scene_styles: 0,
            }),
        };
        (generation << HANDLE_SLOT_BITS) | (slot_index as u32 + 1)
    }

    fn slot_mut(&mut self, handle: u32) -> Option<&mut Slot> {
        let encoded_slot = handle & HANDLE_SLOT_MASK;
        if encoded_slot == 0 {
            return None;
        }
        let generation = handle >> HANDLE_SLOT_BITS;
        let slot = self.slots.get_mut(encoded_slot as usize - 1)?;
        (slot.generation == generation && slot.instance.is_some()).then_some(slot)
    }
}

static REGISTRY: Mutex<Registry> = Mutex::new(Registry::new());

fn registry() -> MutexGuard<'static, Registry> {
    REGISTRY
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
}

fn with_instance_mut<T>(handle: u32, operation: impl FnOnce(&mut Instance) -> T) -> Result<T, i32> {
    let mut registry = registry();
    let instance = registry
        .slot_mut(handle)
        .and_then(|slot| slot.instance.as_mut())
        .ok_or(STATUS_INVALID_HANDLE)?;
    Ok(operation(instance))
}

fn fail(instance: &mut Instance, status: i32, message: &str) -> i32 {
    instance.last_error.clear();
    instance.last_error.push_str(message);
    status
}

#[no_mangle]
pub extern "C" fn xyg_wasm_abi_version() -> u32 {
    WASM_ABI_VERSION
}

#[no_mangle]
pub extern "C" fn xyg_wasm_scene_version() -> u32 {
    scene::SCENE_VERSION
}

#[no_mangle]
pub extern "C" fn xyg_wasm_max_arena_bytes() -> usize {
    MAX_ARENA_BYTES
}

#[no_mangle]
pub extern "C" fn xyg_wasm_instance_new(max_arena_bytes: usize) -> u32 {
    registry().allocate(max_arena_bytes)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_instance_dispose(handle: u32) -> i32 {
    let mut registry = registry();
    let Some(slot) = registry.slot_mut(handle) else {
        return STATUS_INVALID_HANDLE;
    };
    slot.instance = None;
    STATUS_OK
}

#[no_mangle]
pub extern "C" fn xyg_wasm_arena_resize(handle: u32, length: usize) -> i32 {
    with_instance_mut(handle, |instance| {
        instance.output.clear();
        if length > instance.max_arena_bytes {
            return fail(
                instance,
                STATUS_RESOURCE_LIMIT,
                "requested staging arena exceeds the instance byte budget",
            );
        }
        if length > instance.arena.capacity()
            && instance
                .arena
                .try_reserve_exact(length - instance.arena.len())
                .is_err()
        {
            return fail(
                instance,
                STATUS_RESOURCE_LIMIT,
                "unable to reserve the bounded staging arena",
            );
        }
        instance.arena.resize(length, 0);
        if length != 0 {
            instance.copy_count = instance.copy_count.saturating_add(1);
            instance.copy_bytes = instance.copy_bytes.saturating_add(length as u64);
        }
        instance.last_error.clear();
        STATUS_OK
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_arena_ptr(handle: u32) -> usize {
    with_instance_mut(handle, |instance| instance.arena.as_mut_ptr() as usize).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_arena_len(handle: u32) -> usize {
    with_instance_mut(handle, |instance| instance.arena.len()).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_cancel(handle: u32, sequence: u32) -> i32 {
    with_instance_mut(handle, |instance| {
        instance.output.clear();
        if sequence == 0 {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "sequence zero is reserved",
            );
        }
        instance.cancelled_through = instance.cancelled_through.max(sequence);
        instance.last_error.clear();
        STATUS_OK
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_scene_validate(
    handle: u32,
    sequence: u32,
    offset: usize,
    length: usize,
) -> i32 {
    with_instance_mut(handle, |instance| {
        instance.output.clear();
        if sequence == 0 {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "sequence zero is reserved",
            );
        }
        if sequence <= instance.cancelled_through {
            return fail(instance, STATUS_CANCELLED, "request was cancelled");
        }
        if sequence <= instance.latest_sequence {
            return fail(instance, STATUS_STALE_SEQUENCE, "request sequence is stale");
        }
        let Some(end) = offset.checked_add(length) else {
            return fail(instance, STATUS_INVALID_ARGUMENT, "staging range overflow");
        };
        let Some(batch) = instance.arena.get(offset..end) else {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "staging range lies outside the arena",
            );
        };
        let result = scene::validate_scene_batch(batch);
        instance.latest_sequence = sequence;
        match result {
            Ok(summary) => {
                instance.last_scene_records = summary.records;
                instance.last_scene_styles = summary.styles;
                instance.last_error.clear();
                STATUS_OK
            }
            Err(SceneError::Version) => fail(
                instance,
                STATUS_SCENE_VERSION,
                "canonical scene version is incompatible",
            ),
            Err(SceneError::Limit) => fail(
                instance,
                STATUS_RESOURCE_LIMIT,
                "canonical scene exceeds a Rust engine bound",
            ),
            Err(_) => fail(
                instance,
                STATUS_MALFORMED_SCENE,
                "canonical scene batch is malformed",
            ),
        }
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

/// Validate and lower one canonical Scene batch to engine-owned painter-ready
/// columns and descriptors. The output remains owned by this instance until
/// the next operation or disposal.
#[no_mangle]
pub extern "C" fn xyg_wasm_scene_prepare(
    handle: u32,
    sequence: u32,
    offset: usize,
    length: usize,
) -> i32 {
    with_instance_mut(handle, |instance| {
        instance.output.clear();
        if sequence == 0 {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "sequence zero is reserved",
            );
        }
        if sequence <= instance.cancelled_through {
            return fail(instance, STATUS_CANCELLED, "request was cancelled");
        }
        if sequence <= instance.latest_sequence {
            return fail(instance, STATUS_STALE_SEQUENCE, "request sequence is stale");
        }
        let Some(end) = offset.checked_add(length) else {
            return fail(instance, STATUS_INVALID_ARGUMENT, "staging range overflow");
        };
        if end > instance.arena.len() {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "staging range lies outside the arena",
            );
        }
        // Decode owns the scene; end the arena borrow before clearing staging so
        // staging and painter output never both retain the full byte budget.
        let decoded = scene::SceneDocument::decode(&instance.arena[offset..end]);
        instance.arena.clear();
        let result = decoded.and_then(|document| {
            let counts = (document.record_count(), document.style_count());
            let output = document.to_browser_painter(instance.max_arena_bytes)?;
            Ok((counts, output))
        });
        instance.latest_sequence = sequence;
        match result {
            Ok(((records, styles), output)) if output.len() <= instance.max_arena_bytes => {
                instance.last_scene_records = records;
                instance.last_scene_styles = styles;
                instance.output = output;
                instance.last_error.clear();
                STATUS_OK
            }
            Err(SceneError::PainterTraceLimit) => fail(
                instance, STATUS_RESOURCE_LIMIT,
                "canonical scene fragments into more than 1024 browser traces",
            ),
            Ok(_) | Err(SceneError::Limit) => fail(
                instance,
                STATUS_RESOURCE_LIMIT,
                "canonical scene output exceeds the instance byte budget",
            ),
            Err(SceneError::Version) => fail(
                instance,
                STATUS_SCENE_VERSION,
                "canonical scene version is incompatible",
            ),
            Err(_) => fail(
                instance,
                STATUS_MALFORMED_SCENE,
                "canonical scene batch cannot be lowered for browser paint",
            ),
        }
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

fn map_compile_error(instance: &mut Instance, error: SceneError) -> i32 {
    match error {
        SceneError::Version => fail(
            instance,
            STATUS_SCENE_VERSION,
            "typed-column compile version is incompatible",
        ),
        SceneError::Limit | SceneError::PainterTraceLimit => fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "typed-column compile exceeds a Rust engine bound",
        ),
        _ => fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "typed-column compile request is malformed",
        ),
    }
}

fn compile_from_arena(
    instance: &mut Instance,
    sequence: u32,
    offset: usize,
    length: usize,
    paint: bool,
) -> i32 {
    instance.output.clear();
    if sequence == 0 {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "sequence zero is reserved",
        );
    }
    if sequence <= instance.cancelled_through {
        return fail(instance, STATUS_CANCELLED, "request was cancelled");
    }
    if sequence <= instance.latest_sequence {
        return fail(instance, STATUS_STALE_SEQUENCE, "request sequence is stale");
    }
    let Some(end) = offset.checked_add(length) else {
        return fail(instance, STATUS_INVALID_ARGUMENT, "staging range overflow");
    };
    if end > instance.arena.len() {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "staging range lies outside the arena",
        );
    }
    let compiled = compile::compile_scene_request(&instance.arena[offset..end]);
    instance.arena.clear();
    instance.latest_sequence = sequence;
    let compiled = match compiled {
        Ok(value) => value,
        Err(error) => return map_compile_error(instance, error),
    };
    if compiled.bytes.len() > instance.max_arena_bytes {
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "compiled scene exceeds the instance byte budget",
        );
    }
    instance.last_scene_records = compiled.records;
    instance.last_scene_styles = compiled.styles;
    if !paint {
        instance.output = compiled.bytes;
        instance.last_error.clear();
        return STATUS_OK;
    }
    let result = scene::SceneDocument::decode(&compiled.bytes)
        .and_then(|document| document.to_browser_painter(instance.max_arena_bytes));
    match result {
        Ok(output) if output.len() <= instance.max_arena_bytes => {
            instance.output = output;
            instance.last_error.clear();
            STATUS_OK
        }
        Err(SceneError::PainterTraceLimit) => fail(
            instance, STATUS_RESOURCE_LIMIT,
            "compiled scene fragments into more than 1024 browser traces",
        ),
        Ok(_) | Err(SceneError::Limit) => fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "compiled scene output exceeds the instance byte budget",
        ),
        Err(SceneError::Version) => fail(
            instance,
            STATUS_SCENE_VERSION,
            "compiled scene version is incompatible",
        ),
        Err(_) => fail(
            instance,
            STATUS_MALFORMED_SCENE,
            "compiled scene cannot be lowered for browser paint",
        ),
    }
}

/// Compile one packed typed-column request into a canonical Scene batch.
#[no_mangle]
pub extern "C" fn xyg_wasm_scene_compile(
    handle: u32,
    sequence: u32,
    offset: usize,
    length: usize,
) -> i32 {
    with_instance_mut(handle, |instance| {
        compile_from_arena(instance, sequence, offset, length, false)
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

/// Compile packed typed columns and lower the resulting Scene for browser paint.
#[no_mangle]
pub extern "C" fn xyg_wasm_scene_compile_prepare(
    handle: u32,
    sequence: u32,
    offset: usize,
    length: usize,
) -> i32 {
    with_instance_mut(handle, |instance| {
        compile_from_arena(instance, sequence, offset, length, true)
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_output_ptr(handle: u32) -> usize {
    with_instance_mut(handle, |instance| instance.output.as_ptr() as usize).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_output_len(handle: u32) -> usize {
    with_instance_mut(handle, |instance| instance.output.len()).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_last_error_ptr(handle: u32) -> usize {
    with_instance_mut(handle, |instance| instance.last_error.as_ptr() as usize).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_last_error_len(handle: u32) -> usize {
    with_instance_mut(handle, |instance| instance.last_error.len()).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_copy_count(handle: u32) -> u32 {
    with_instance_mut(handle, |instance| instance.copy_count).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_copy_bytes_lo(handle: u32) -> u32 {
    with_instance_mut(handle, |instance| instance.copy_bytes as u32).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_copy_bytes_hi(handle: u32) -> u32 {
    with_instance_mut(handle, |instance| (instance.copy_bytes >> 32) as u32).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_last_scene_records(handle: u32) -> usize {
    with_instance_mut(handle, |instance| instance.last_scene_records).unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_last_scene_styles(handle: u32) -> usize {
    with_instance_mut(handle, |instance| instance.last_scene_styles).unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use xyg_engine::scene::{AxisScale, PlotLayout, ScaleKind, SceneBatch};

    fn valid_scene() -> Vec<u8> {
        let layout = PlotLayout::new(100.0, 80.0, 10.0, 10.0, 10.0, 10.0).unwrap();
        let x = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 10.0, 90.0, 1.0, false).unwrap();
        let y = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 70.0, 10.0, 1.0, false).unwrap();
        SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &[0],
            &[7],
            &[0],
            &[1, 2, 3, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &[8.0],
            &[0],
            &[0.5],
            &[0.5],
            &[0.0],
            &[0.0],
        )
        .unwrap()
        .encode()
    }

    fn write_arena(handle: u32, bytes: &[u8]) {
        assert_eq!(xyg_wasm_arena_resize(handle, bytes.len()), STATUS_OK);
        with_instance_mut(handle, |instance| instance.arena.copy_from_slice(bytes)).unwrap();
    }

    fn fragmented_scene(count: usize) -> Vec<u8> {
        let layout = scene::PlotLayout::new(100.0, 80.0, 10.0, 10.0, 10.0, 10.0).unwrap();
        let x = scene::AxisScale::new(scene::ScaleKind::Linear, 0.0, 1.0, 10.0, 90.0, 1.0, false).unwrap();
        let y = scene::AxisScale::new(scene::ScaleKind::Linear, 0.0, 1.0, 70.0, 10.0, 1.0, false).unwrap();
        let coordinates = vec![0.5; count];
        let zeros = vec![0.0; count];
        let symbols: Vec<u8> = (0..count).map(|index| (index % 2) as u8).collect();
        scene::SceneBatch::new(
            layout, 1, 2, x, y, &vec![0; count], &vec![7; count], &vec![0; count],
            &[1, 2, 3, 255], &[0, 0, 0, 0], &[0.0], &vec![4.0; count], &symbols,
            &coordinates, &coordinates, &zeros, &zeros,
        )
        .unwrap()
        .encode()
    }

    #[test]
    fn lifecycle_bounds_and_generation_handles_fail_closed() {
        let handle = xyg_wasm_instance_new(256);
        assert_ne!(handle, 0);
        assert_eq!(xyg_wasm_arena_resize(handle, 257), STATUS_RESOURCE_LIMIT);
        assert_eq!(xyg_wasm_arena_resize(handle, 64), STATUS_OK);
        assert_ne!(xyg_wasm_arena_ptr(handle), 0);
        assert_eq!(xyg_wasm_arena_len(handle), 64);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
        assert_eq!(xyg_wasm_arena_resize(handle, 1), STATUS_INVALID_HANDLE);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_INVALID_HANDLE);
    }

    #[test]
    fn scene_v4_status_cancel_stale_and_diagnostics_are_stable() {
        let bytes = valid_scene();
        let handle = xyg_wasm_instance_new(bytes.len() + 8);
        write_arena(handle, &bytes);
        assert_eq!(
            xyg_wasm_scene_validate(handle, 1, 0, bytes.len()),
            STATUS_OK
        );
        assert_eq!(xyg_wasm_last_scene_records(handle), 1);
        assert_eq!(xyg_wasm_last_scene_styles(handle), 1);
        assert_eq!(xyg_wasm_copy_count(handle), 1);
        write_arena(handle, &bytes);
        assert_eq!(
            xyg_wasm_scene_validate(handle, 1, 0, bytes.len()),
            STATUS_STALE_SEQUENCE
        );
        assert_eq!(xyg_wasm_copy_count(handle), 2);
        assert_eq!(xyg_wasm_cancel(handle, 3), STATUS_OK);
        write_arena(handle, &bytes);
        assert_eq!(
            xyg_wasm_scene_validate(handle, 2, 0, bytes.len()),
            STATUS_CANCELLED
        );
        assert_eq!(xyg_wasm_copy_count(handle), 3);
        assert_eq!(xyg_wasm_copy_bytes_lo(handle), (bytes.len() * 3) as u32);
        assert_eq!(
            xyg_wasm_scene_validate(handle, 4, bytes.len(), 1),
            STATUS_INVALID_ARGUMENT
        );
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn malformed_and_incompatible_scene_versions_are_distinct() {
        let mut bytes = valid_scene();
        let handle = xyg_wasm_instance_new(bytes.len());
        bytes[4..8].copy_from_slice(&(scene::SCENE_VERSION + 1).to_le_bytes());
        write_arena(handle, &bytes);
        assert_eq!(
            xyg_wasm_scene_validate(handle, 1, 0, bytes.len()),
            STATUS_SCENE_VERSION
        );
        bytes[4..8].copy_from_slice(&scene::SCENE_VERSION.to_le_bytes());
        bytes[0] = b'!';
        write_arena(handle, &bytes);
        assert_eq!(
            xyg_wasm_scene_validate(handle, 2, 0, bytes.len()),
            STATUS_MALFORMED_SCENE
        );
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn scene_paint_uses_engine_checked_f32_output() {
        let bytes = valid_scene();
        let handle = xyg_wasm_instance_new(4096);
        write_arena(handle, &bytes);
        assert_eq!(xyg_wasm_scene_prepare(handle, 1, 0, bytes.len()), STATUS_OK);
        assert_ne!(xyg_wasm_output_ptr(handle), 0);
        assert_eq!(xyg_wasm_output_len(handle), 258);
        assert_eq!(xyg_wasm_last_scene_records(handle), 1);
        with_instance_mut(handle, |instance| {
            assert_eq!(&instance.output[..4], b"XYPB");
            assert_eq!(
                u32::from_le_bytes(instance.output[4..8].try_into().unwrap()),
                2
            );
            assert_eq!(
                u32::from_le_bytes(instance.output[20..24].try_into().unwrap()),
                1
            );
            assert_eq!(
                u32::from_le_bytes(instance.output[136..140].try_into().unwrap()),
                7
            );
            assert_eq!(
                u32::from_le_bytes(instance.output[140..144].try_into().unwrap()),
                0
            );
            assert_eq!(
                u32::from_le_bytes(instance.output[48..52].try_into().unwrap()),
                3
            );
            assert_eq!(
                u32::from_le_bytes(instance.output[52..56].try_into().unwrap()),
                3
            );
            let strings = u32::from_le_bytes(instance.output[60..64].try_into().unwrap()) as usize;
            assert!(strings < instance.output.len());
            assert!(std::str::from_utf8(&instance.output[strings..]).is_ok());
        })
        .unwrap();

        // prepare clears staging after decode; restage before the next call.
        write_arena(handle, &bytes);
        assert_eq!(
            xyg_wasm_scene_validate(handle, 2, 0, bytes.len()),
            STATUS_OK
        );
        assert_eq!(xyg_wasm_output_len(handle), 0);

        write_arena(handle, &bytes);
        assert_eq!(xyg_wasm_scene_prepare(handle, 3, 0, bytes.len()), STATUS_OK);
        assert!(xyg_wasm_output_len(handle) > 0);

        write_arena(handle, &bytes);
        assert_eq!(
            xyg_wasm_scene_prepare(handle, 4, bytes.len(), 1),
            STATUS_INVALID_ARGUMENT
        );
        assert_eq!(xyg_wasm_output_len(handle), 0);
        write_arena(handle, &bytes);
        assert_eq!(xyg_wasm_scene_prepare(handle, 5, 0, bytes.len()), STATUS_OK);
        assert!(xyg_wasm_output_len(handle) > 0);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
        assert_eq!(xyg_wasm_output_len(handle), 0);
    }

    #[test]
    fn prepare_releases_staging_before_painter_budget() {
        let bytes = valid_scene();
        // Budget large enough for staging or painter alone, but not both if
        // staging were retained through lowering.
        let painter_len = {
            let document = scene::SceneDocument::decode(&bytes).unwrap();
            document.to_browser_painter(64 * 1024).unwrap().len()
        };
        let budget = bytes.len().max(painter_len);
        let handle = xyg_wasm_instance_new(budget);
        write_arena(handle, &bytes);
        assert_eq!(xyg_wasm_arena_len(handle), bytes.len());
        assert_eq!(xyg_wasm_scene_prepare(handle, 1, 0, bytes.len()), STATUS_OK);
        assert_eq!(xyg_wasm_arena_len(handle), 0);
        assert_eq!(xyg_wasm_output_len(handle), painter_len);
        with_instance_mut(handle, |instance| {
            assert!(instance.arena.len() + instance.output.len() <= instance.max_arena_bytes);
        })
        .unwrap();
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn fragmented_scene_returns_stable_resource_limit_without_output() {
        let bytes = fragmented_scene(scene::MAX_BROWSER_PAINTER_TRACES + 1);
        let handle = xyg_wasm_instance_new(bytes.len());
        write_arena(handle, &bytes);
        assert_eq!(xyg_wasm_scene_prepare(handle, 1, 0, bytes.len()), STATUS_RESOURCE_LIMIT);
        assert_eq!(xyg_wasm_output_len(handle), 0);
        with_instance_mut(handle, |instance| {
            assert_eq!(instance.last_error, "canonical scene fragments into more than 1024 browser traces");
        })
        .unwrap();
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    fn packed_columns() -> Vec<u8> {
        let mut out = vec![0u8; compile::COMPILE_HEADER_BYTES];
        out[..4].copy_from_slice(compile::COMPILE_MAGIC);
        out[4..8].copy_from_slice(&compile::COMPILE_VERSION.to_le_bytes());
        out[8..12].copy_from_slice(&(compile::COMPILE_HEADER_BYTES as u32).to_le_bytes());
        out[16..20].copy_from_slice(&1u32.to_le_bytes());
        out[20..24].copy_from_slice(&1u32.to_le_bytes());
        for (offset, value) in [
            (40, 100.0f64),
            (48, 80.0),
            (56, 10.0),
            (64, 10.0),
            (72, 10.0),
            (80, 10.0),
            (120, 0.0),
            (128, 1.0),
            (136, 1.0),
            (144, 0.0),
            (152, 1.0),
            (160, 1.0),
        ] {
            out[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        }
        out[88..96].copy_from_slice(&1u64.to_le_bytes());
        out[96..104].copy_from_slice(&2u64.to_le_bytes());
        out.extend_from_slice(&[0]);
        while !out.len().is_multiple_of(8) {
            out.push(0);
        }
        out.extend_from_slice(&7u64.to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        while !out.len().is_multiple_of(8) {
            out.push(0);
        }
        out.extend_from_slice(&8.0f64.to_le_bytes());
        out.push(0);
        while !out.len().is_multiple_of(8) {
            out.push(0);
        }
        for value in [0.5f64, 0.5, 0.0, 0.0] {
            out.extend_from_slice(&value.to_le_bytes());
        }
        out.extend_from_slice(&[1, 2, 3, 255, 0, 0, 0, 0]);
        while !out.len().is_multiple_of(8) {
            out.push(0);
        }
        out.extend_from_slice(&0.0f64.to_le_bytes());
        out
    }

    #[test]
    fn typed_columns_compile_and_paint_through_wasm() {
        let request = packed_columns();
        let handle = xyg_wasm_instance_new(8192);
        write_arena(handle, &request);
        assert_eq!(
            xyg_wasm_scene_compile(handle, 1, 0, request.len()),
            STATUS_OK
        );
        assert_eq!(xyg_wasm_last_scene_records(handle), 1);
        assert_eq!(xyg_wasm_arena_len(handle), 0);
        with_instance_mut(handle, |instance| {
            assert_eq!(&instance.output[..4], b"XYGS");
            assert_eq!(
                u32::from_le_bytes(instance.output[4..8].try_into().unwrap()),
                scene::SCENE_VERSION
            );
        })
        .unwrap();
        write_arena(handle, &request);
        assert_eq!(
            xyg_wasm_scene_compile_prepare(handle, 2, 0, request.len()),
            STATUS_OK
        );
        assert!(xyg_wasm_output_len(handle) > 64);
        with_instance_mut(handle, |instance| {
            assert_eq!(&instance.output[..4], b"XYPB");
        })
        .unwrap();
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }
}
