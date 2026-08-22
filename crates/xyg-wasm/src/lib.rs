//! Raw, dependency-free WebAssembly boundary for direct-browser XYG.
//!
//! This crate owns only WASM memory, instance, status, and lifecycle concerns.
//! Product policy stays in `xyg-engine`; browser painting stays in TypeScript.
//! Bounded seams validate/prepare canonical Scene batches, compile packed
//! typed-column requests into those same batches, and produce Tier-2 density
//! aggregates via the shared `bin_2d` kernels. This is not a second browser
//! scene schema and does not claim complete density-worker replacement yet.

pub mod aggregate;
pub mod compile;
mod graph;
mod temporal;
mod temporal_graph;
mod typed_series_abi_generated;

use std::sync::{Mutex, MutexGuard};
use xyg_engine::scene::{self, SceneError};

pub const WASM_ABI_VERSION: u32 = 11;
pub const STATUS_OK: i32 = 0;
pub const STATUS_INVALID_HANDLE: i32 = 1;
pub const STATUS_INVALID_ARGUMENT: i32 = 2;
pub const STATUS_RESOURCE_LIMIT: i32 = 3;
pub const STATUS_SCENE_VERSION: i32 = 4;
pub const STATUS_MALFORMED_SCENE: i32 = 5;
pub const STATUS_CANCELLED: i32 = 6;
pub const STATUS_STALE_SEQUENCE: i32 = 7;
pub const STATUS_PENDING: i32 = 8;
pub const STATUS_DISPOSED: i32 = 9;
pub const STATUS_STALE_REVISION: i32 = 10;
pub const STATUS_SELF_ECHO: i32 = 11;

pub const MAX_INSTANCES: usize = 64;
pub const MAX_ARENA_BYTES: usize = 402_653_184;
// Multiple handles share one wasm32 memory. Reserve their declared operation
// budgets against one module-wide ceiling so retained outputs across otherwise
// idle instances cannot collectively promise more memory than the seam allows.
pub const MAX_TOTAL_INSTANCE_BUDGET_BYTES: usize = MAX_ARENA_BYTES;
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
    arena_high_water: usize,
    last_scene_records: usize,
    last_scene_styles: usize,
    aggregate_job: Option<aggregate::AggregateJob>,
    aggregate_sequence: u32,
    temporal: Option<xyg_engine::temporal_controller::TemporalController>,
    temporal_graph: Option<temporal_graph::WasmTemporalGraph>,
    graph_job: Option<graph::GraphJob>,
    compile_job: Option<CompileJob>,
}

#[derive(Debug)]
struct CompileJob {
    sequence: u32,
    offset: usize,
    length: usize,
    records_total: usize,
    records_processed: usize,
    phase: u32,
    paint: bool,
}

impl Instance {
    fn clear_aggregate(&mut self) {
        self.aggregate_job = None;
        self.aggregate_sequence = 0;
    }
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
        let reserved = self
            .slots
            .iter()
            .filter_map(|slot| slot.instance.as_ref())
            .try_fold(0usize, |total, instance| {
                total.checked_add(instance.max_arena_bytes)
            });
        let Some(reserved_after) = reserved.and_then(|total| total.checked_add(max_arena_bytes))
        else {
            return 0;
        };
        if reserved_after > MAX_TOTAL_INSTANCE_BUDGET_BYTES {
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
                arena_high_water: 0,
                last_scene_records: 0,
                last_scene_styles: 0,
                aggregate_job: None,
                aggregate_sequence: 0,
                temporal: None,
                temporal_graph: None,
                graph_job: None,
                compile_job: None,
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

/// Execute one packed `XYTC` temporal-controller command and place its packed
/// `XYTR` snapshot in the ordinary output buffer. Temporal values remain raw
/// i64/u64 bytes across the browser boundary; TypeScript never owns policy.
#[no_mangle]
pub extern "C" fn xyg_wasm_temporal_execute(handle: u32, offset: usize, length: usize) -> i32 {
    with_instance_mut(handle, |instance| {
        temporal::execute(instance, offset, length)
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

/// Execute one packed Rust-owned temporal graph create/frame command.
#[no_mangle]
pub extern "C" fn xyg_wasm_temporal_graph_execute(
    handle: u32,
    offset: usize,
    length: usize,
) -> i32 {
    with_instance_mut(handle, |instance| {
        temporal_graph::execute(instance, offset, length)
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_arena_resize(handle: u32, length: usize) -> i32 {
    with_instance_mut(handle, |instance| {
        // A prior result is no longer observable once the caller starts a new
        // request. Drop its allocation before reserving staging so retained
        // capacity cannot stack on top of the next operation's peak budget.
        instance.output = Vec::new();
        if length > instance.max_arena_bytes {
            return fail(
                instance,
                STATUS_RESOURCE_LIMIT,
                "requested staging arena exceeds the instance byte budget",
            );
        }
        instance.clear_aggregate();
        instance.compile_job = None;
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
        instance.arena_high_water = instance.arena_high_water.max(length);
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
        if instance
            .graph_job
            .as_ref()
            .is_some_and(|job| job.sequence <= sequence)
        {
            instance.graph_job = None;
        }
        if instance
            .compile_job
            .as_ref()
            .is_some_and(|job| job.sequence <= sequence)
        {
            instance.compile_job = None;
            instance.arena = Vec::new();
        }
        instance.last_error.clear();
        STATUS_OK
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

/// Start a checkpointed typed-column compile. The request remains in the
/// bounded Rust staging arena until `xyg_wasm_scene_compile_step` completes,
/// is superseded, cancelled, or disposed.
#[no_mangle]
pub extern "C" fn xyg_wasm_scene_compile_begin(
    handle: u32,
    sequence: u32,
    offset: usize,
    length: usize,
    paint: u32,
) -> i32 {
    with_instance_mut(handle, |instance| {
        instance.output.clear();
        if sequence == 0 || paint > 1 {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "compile scheduler arguments are invalid",
            );
        }
        if sequence <= instance.cancelled_through {
            instance.arena = Vec::new();
            return fail(instance, STATUS_CANCELLED, "request was cancelled");
        }
        if sequence <= instance.latest_sequence {
            instance.arena = Vec::new();
            return fail(instance, STATUS_STALE_SEQUENCE, "request sequence is stale");
        }
        let Some(end) = offset.checked_add(length) else {
            return fail(instance, STATUS_INVALID_ARGUMENT, "staging range overflow");
        };
        if length == 0 || end > instance.arena.len() {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "staging range lies outside the arena",
            );
        }
        let records_total = match compile::checkpoint_record_count(&instance.arena[offset..end]) {
            Ok(value) => value,
            Err(error) => return map_compile_error(instance, error),
        };
        instance.clear_aggregate();
        instance.compile_job = Some(CompileJob {
            sequence,
            offset,
            length,
            records_total,
            records_processed: 0,
            phase: 1,
            paint: paint != 0,
        });
        instance.last_error.clear();
        STATUS_PENDING
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

/// Advance real record decoding by at most `record_budget` rows, then run the
/// canonical build/lower phase after a separate cancellation heartbeat.
#[no_mangle]
pub extern "C" fn xyg_wasm_scene_compile_step(
    handle: u32,
    sequence: u32,
    record_budget: usize,
) -> i32 {
    with_instance_mut(handle, |instance| {
        if record_budget == 0 {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "compile record budget must be nonzero",
            );
        }
        let Some(job) = instance.compile_job.as_mut() else {
            return fail(
                instance,
                STATUS_STALE_SEQUENCE,
                "compile job is no longer active",
            );
        };
        if job.sequence != sequence {
            return fail(
                instance,
                STATUS_STALE_SEQUENCE,
                "compile request sequence is stale",
            );
        }
        if job.phase == 1 {
            let count = record_budget.min(job.records_total.saturating_sub(job.records_processed));
            let request_end = job.offset + job.length;
            if let Err(error) = compile::checkpoint_validate_records(
                &instance.arena[job.offset..request_end],
                job.records_processed,
                count,
            ) {
                instance.compile_job = None;
                instance.arena = Vec::new();
                return map_compile_error(instance, error);
            }
            job.records_processed += count;
            if job.records_processed < job.records_total {
                instance.last_error.clear();
                return STATUS_PENDING;
            }
            job.phase = 2;
            instance.last_error.clear();
            return STATUS_PENDING;
        }
        let job = instance.compile_job.take().expect("checked above");
        compile_from_arena(instance, job.sequence, job.offset, job.length, job.paint)
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_scene_compile_records_processed(handle: u32) -> usize {
    with_instance_mut(handle, |instance| {
        instance
            .compile_job
            .as_ref()
            .map_or(0, |job| job.records_processed)
    })
    .unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn xyg_wasm_scene_compile_phase(handle: u32) -> u32 {
    with_instance_mut(handle, |instance| {
        instance.compile_job.as_ref().map_or(0, |job| job.phase)
    })
    .unwrap_or(0)
}

/// Start a Rust-owned progressive graph layout from one packed `XYGL` request.
#[no_mangle]
pub extern "C" fn xyg_wasm_graph_begin(
    handle: u32,
    sequence: u32,
    revision: u32,
    offset: usize,
    length: usize,
) -> i32 {
    with_instance_mut(handle, |instance| {
        graph::begin(instance, sequence, revision, offset, length)
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

/// Advance the active graph layout and encode one `XYGO` position checkpoint.
#[no_mangle]
pub extern "C" fn xyg_wasm_graph_step(
    handle: u32,
    sequence: u32,
    revision: u32,
    steps: u32,
) -> i32 {
    with_instance_mut(handle, |instance| {
        graph::step(instance, sequence, revision, steps)
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
        instance.output = Vec::new();
        if sequence == 0 {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "sequence zero is reserved",
            );
        }
        if sequence <= instance.cancelled_through {
            if instance.aggregate_job.is_none() {
                instance.arena = Vec::new();
            }
            return fail(instance, STATUS_CANCELLED, "request was cancelled");
        }
        if sequence <= instance.latest_sequence {
            if instance.aggregate_job.is_none() {
                instance.arena = Vec::new();
            }
            return fail(instance, STATUS_STALE_SEQUENCE, "request sequence is stale");
        }
        instance.clear_aggregate();
        // Only a strictly newer operation may consume shared staging. Keeping
        // it local makes all subsequent early returns drop its allocation.
        let arena = std::mem::take(&mut instance.arena);
        let Some(end) = offset.checked_add(length) else {
            return fail(instance, STATUS_INVALID_ARGUMENT, "staging range overflow");
        };
        let Some(batch) = arena.get(offset..end) else {
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
        instance.output = Vec::new();
        if sequence == 0 {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "sequence zero is reserved",
            );
        }
        if sequence <= instance.cancelled_through {
            if instance.aggregate_job.is_none() {
                instance.arena = Vec::new();
            }
            return fail(instance, STATUS_CANCELLED, "request was cancelled");
        }
        if sequence <= instance.latest_sequence {
            if instance.aggregate_job.is_none() {
                instance.arena = Vec::new();
            }
            return fail(instance, STATUS_STALE_SEQUENCE, "request sequence is stale");
        }
        instance.clear_aggregate();
        let arena = std::mem::take(&mut instance.arena);
        let Some(end) = offset.checked_add(length) else {
            return fail(instance, STATUS_INVALID_ARGUMENT, "staging range overflow");
        };
        if end > arena.len() {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "staging range lies outside the arena",
            );
        }
        // Decode owns the scene; end the arena borrow before clearing staging so
        // staging and painter output never both retain the full byte budget.
        let decoded = scene::SceneDocument::decode(&arena[offset..end]);
        drop(arena);
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
                instance,
                STATUS_RESOURCE_LIMIT,
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
            "scene compile version is incompatible",
        ),
        SceneError::Limit | SceneError::PainterTraceLimit => fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "scene compile peak or output exceeds the instance byte budget",
        ),
        _ => fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "scene compile request is malformed",
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
    instance.output = Vec::new();
    if sequence == 0 {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "sequence zero is reserved",
        );
    }
    if sequence <= instance.cancelled_through {
        if instance.aggregate_job.is_none() {
            instance.arena = Vec::new();
        }
        return fail(instance, STATUS_CANCELLED, "request was cancelled");
    }
    if sequence <= instance.latest_sequence {
        if instance.aggregate_job.is_none() {
            instance.arena = Vec::new();
        }
        return fail(instance, STATUS_STALE_SEQUENCE, "request sequence is stale");
    }
    instance.clear_aggregate();
    let arena = std::mem::take(&mut instance.arena);
    let Some(end) = offset.checked_add(length) else {
        return fail(instance, STATUS_INVALID_ARGUMENT, "staging range overflow");
    };
    if end > arena.len() {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "staging range lies outside the arena",
        );
    }
    let compiled = compile::compile_scene_request(&arena[offset..end], instance.max_arena_bytes);
    drop(arena);
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
            instance,
            STATUS_RESOURCE_LIMIT,
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

fn map_aggregate_error(instance: &mut Instance, error: aggregate::AggregateError) -> i32 {
    match error {
        aggregate::AggregateError::Limit => fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "aggregate exceeds its total memory, point, or grid bound; reduce the grid or omit mean color",
        ),
        aggregate::AggregateError::Version
        | aggregate::AggregateError::Domain
        | aggregate::AggregateError::Length => fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "aggregate request is malformed",
        ),
    }
}

fn aggregate_from_arena(
    instance: &mut Instance,
    sequence: u32,
    offset: usize,
    length: usize,
) -> i32 {
    instance.output = Vec::new();
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
    instance.clear_aggregate();
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
    let retained_slack = instance.arena.capacity().saturating_sub(length);
    let aggregate_budget = instance.max_arena_bytes.saturating_sub(retained_slack);
    let aggregated =
        aggregate::AggregateJob::begin(&instance.arena[offset..end], offset, aggregate_budget);
    instance.latest_sequence = sequence;
    let aggregated = match aggregated {
        Ok(value) => value,
        Err(error) => {
            instance.arena = Vec::new();
            return map_aggregate_error(instance, error);
        }
    };
    instance.aggregate_job = Some(aggregated);
    instance.aggregate_sequence = sequence;
    instance.last_error.clear();
    STATUS_PENDING
}

/// Bin points from a packed `XYAG` request into a screen-bounded count grid
/// (optional mean-color plane). Output is a transferable `XYAO` buffer.
#[no_mangle]
pub extern "C" fn xyg_wasm_aggregate_bin2d(
    handle: u32,
    sequence: u32,
    offset: usize,
    length: usize,
) -> i32 {
    with_instance_mut(handle, |instance| {
        aggregate_from_arena(instance, sequence, offset, length)
    })
    .unwrap_or(STATUS_INVALID_HANDLE)
}

/// Advance the active aggregate by at most `max_points`. `PENDING` requires
/// the Worker to yield before calling again so cancel/new viewport messages run.
#[no_mangle]
pub extern "C" fn xyg_wasm_aggregate_step(handle: u32, sequence: u32, max_points: usize) -> i32 {
    with_instance_mut(handle, |instance| {
        if sequence == 0 {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "sequence zero is reserved",
            );
        }
        instance.output.clear();
        if sequence != instance.aggregate_sequence {
            return fail(
                instance,
                STATUS_CANCELLED,
                "aggregate request was superseded by a newer viewport",
            );
        }
        if sequence <= instance.cancelled_through {
            instance.clear_aggregate();
            instance.arena = Vec::new();
            return fail(
                instance,
                STATUS_CANCELLED,
                "aggregate request was cancelled at a checkpoint",
            );
        }
        if max_points == 0 || max_points > aggregate::CHECKPOINT_POINTS {
            instance.clear_aggregate();
            instance.arena = Vec::new();
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "aggregate checkpoint is invalid",
            );
        }
        let Some(job) = instance.aggregate_job.as_mut() else {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "aggregate job is not active",
            );
        };
        match job.step(&instance.arena, max_points) {
            Ok(false) => STATUS_PENDING,
            Ok(true) => {
                let job = instance.aggregate_job.take().expect("active aggregate job");
                instance.aggregate_sequence = 0;
                instance.output = job.finish();
                instance.arena = Vec::new();
                instance.last_error.clear();
                STATUS_OK
            }
            Err(error) => {
                instance.clear_aggregate();
                instance.arena = Vec::new();
                map_aggregate_error(instance, error)
            }
        }
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
pub extern "C" fn xyg_wasm_arena_high_water(handle: u32) -> usize {
    with_instance_mut(handle, |instance| instance.arena_high_water).unwrap_or(0)
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

    fn typed_series_points(count: usize) -> Vec<u8> {
        let data_start = compile::COMPILE_HEADER_BYTES + compile::SERIES_DESCRIPTOR_BYTES;
        let mut out = vec![0u8; data_start];
        out[..4].copy_from_slice(compile::SERIES_MAGIC);
        out[4..8].copy_from_slice(&compile::SERIES_VERSION.to_le_bytes());
        out[8..12].copy_from_slice(&(compile::COMPILE_HEADER_BYTES as u32).to_le_bytes());
        out[12..16].copy_from_slice(&3u32.to_le_bytes());
        out[16..20].copy_from_slice(&1u32.to_le_bytes());
        out[20..24].copy_from_slice(&(count as u32).to_le_bytes());
        for (offset, value) in [
            (40, 100.0f64),
            (48, 80.0),
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
        let descriptor = compile::COMPILE_HEADER_BYTES;
        out[descriptor + 8..descriptor + 12].copy_from_slice(&(count as u32).to_le_bytes());
        out[descriptor + 24..descriptor + 32].copy_from_slice(&f64::NAN.to_le_bytes());
        out[descriptor + 32..descriptor + 40].copy_from_slice(&f64::NAN.to_le_bytes());
        out[descriptor + 48..descriptor + 52].copy_from_slice(&(data_start as u32).to_le_bytes());
        out[descriptor + 52..descriptor + 56]
            .copy_from_slice(&((data_start + count * 8) as u32).to_le_bytes());
        for index in 0..count {
            out.extend_from_slice(&((index as f64 + 0.5) / count as f64).to_le_bytes());
        }
        for index in 0..count {
            out.extend_from_slice(&((index as f64 + 0.5) / count as f64).to_le_bytes());
        }
        out
    }

    fn one_point_typed_series() -> Vec<u8> {
        typed_series_points(1)
    }

    fn write_arena(handle: u32, bytes: &[u8]) {
        assert_eq!(xyg_wasm_arena_resize(handle, bytes.len()), STATUS_OK);
        with_instance_mut(handle, |instance| instance.arena.copy_from_slice(bytes)).unwrap();
    }

    fn fragmented_scene(count: usize) -> Vec<u8> {
        let layout = scene::PlotLayout::new(100.0, 80.0, 10.0, 10.0, 10.0, 10.0).unwrap();
        let x = scene::AxisScale::new(scene::ScaleKind::Linear, 0.0, 1.0, 10.0, 90.0, 1.0, false)
            .unwrap();
        let y = scene::AxisScale::new(scene::ScaleKind::Linear, 0.0, 1.0, 70.0, 10.0, 1.0, false)
            .unwrap();
        let coordinates = vec![0.5; count];
        let zeros = vec![0.0; count];
        let symbols: Vec<u8> = (0..count).map(|index| (index % 2) as u8).collect();
        scene::SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &vec![0; count],
            &vec![7; count],
            &vec![0; count],
            &[1, 2, 3, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &vec![4.0; count],
            &symbols,
            &coordinates,
            &coordinates,
            &zeros,
            &zeros,
        )
        .unwrap()
        .encode()
    }

    fn aggregate_request(points: usize) -> Vec<u8> {
        let mut out = vec![0u8; aggregate::AGGREGATE_HEADER_BYTES];
        out[..4].copy_from_slice(aggregate::AGGREGATE_MAGIC);
        out[4..8].copy_from_slice(&aggregate::AGGREGATE_VERSION.to_le_bytes());
        out[8..12].copy_from_slice(&(aggregate::AGGREGATE_HEADER_BYTES as u32).to_le_bytes());
        out[16..20].copy_from_slice(&(points as u32).to_le_bytes());
        out[20..24].copy_from_slice(&4u32.to_le_bytes());
        out[24..28].copy_from_slice(&4u32.to_le_bytes());
        for (offset, value) in [(32, 0.0f64), (40, 1.0), (48, 0.0), (56, 1.0)] {
            out[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        }
        for _ in 0..points * 2 {
            out.extend_from_slice(&0.5f64.to_le_bytes());
        }
        out
    }

    #[test]
    fn aggregate_checkpoints_cancel_and_allow_newer_viewport() {
        let first = aggregate_request(aggregate::CHECKPOINT_POINTS + 1);
        let handle = xyg_wasm_instance_new(2 * 1024 * 1024);
        write_arena(handle, &first);
        assert_eq!(
            xyg_wasm_aggregate_bin2d(handle, 1, 0, first.len()),
            STATUS_PENDING
        );
        assert_eq!(
            xyg_wasm_aggregate_step(handle, 1, aggregate::CHECKPOINT_POINTS),
            STATUS_PENDING
        );
        assert_eq!(xyg_wasm_cancel(handle, 1), STATUS_OK);
        assert_eq!(xyg_wasm_aggregate_step(handle, 1, 1), STATUS_CANCELLED);
        assert_eq!(xyg_wasm_output_len(handle), 0);
        let newer = aggregate_request(1);
        write_arena(handle, &newer);
        assert_eq!(
            xyg_wasm_aggregate_bin2d(handle, 2, 0, newer.len()),
            STATUS_PENDING
        );
        assert_eq!(xyg_wasm_aggregate_step(handle, 2, 1), STATUS_OK);
        assert!(xyg_wasm_output_len(handle) > aggregate::OUTPUT_HEADER_BYTES);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn aggregate_accepts_nonzero_staging_offset() {
        let request = aggregate_request(2);
        let prefix = 37;
        let handle = xyg_wasm_instance_new(1024 * 1024);
        assert_eq!(
            xyg_wasm_arena_resize(handle, prefix + request.len()),
            STATUS_OK
        );
        with_instance_mut(handle, |instance| {
            instance.arena[..prefix].fill(0xa5);
            instance.arena[prefix..].copy_from_slice(&request);
        })
        .unwrap();
        assert_eq!(
            xyg_wasm_aggregate_bin2d(handle, 1, prefix, request.len()),
            STATUS_PENDING
        );
        assert_eq!(xyg_wasm_aggregate_step(handle, 1, 2), STATUS_OK);
        assert!(xyg_wasm_output_len(handle) > aggregate::OUTPUT_HEADER_BYTES);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn every_aggregate_clear_invalidates_its_sequence() {
        let request = aggregate_request(2);
        let handle = xyg_wasm_instance_new(1024 * 1024);
        write_arena(handle, &request);
        assert_eq!(
            xyg_wasm_aggregate_bin2d(handle, 1, 0, request.len()),
            STATUS_PENDING
        );
        assert_eq!(
            xyg_wasm_aggregate_step(handle, 1, 0),
            STATUS_INVALID_ARGUMENT
        );
        assert_eq!(xyg_wasm_aggregate_step(handle, 1, 1), STATUS_CANCELLED);

        write_arena(handle, &request);
        assert_eq!(
            xyg_wasm_aggregate_bin2d(handle, 2, 0, request.len()),
            STATUS_PENDING
        );
        let mut malformed = request.clone();
        malformed[0] = 0;
        write_arena(handle, &malformed);
        assert_eq!(
            xyg_wasm_aggregate_bin2d(handle, 3, 0, malformed.len()),
            STATUS_INVALID_ARGUMENT
        );
        assert_eq!(xyg_wasm_aggregate_step(handle, 2, 1), STATUS_CANCELLED);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn raw_scene_export_supersedes_nonzero_offset_aggregate_in_shared_arena() {
        let aggregate = aggregate_request(2);
        let scene = valid_scene();
        let aggregate_offset = 19;
        let scene_offset = aggregate_offset + aggregate.len() + 23;
        let handle = xyg_wasm_instance_new(1024 * 1024);
        assert_eq!(
            xyg_wasm_arena_resize(handle, scene_offset + scene.len()),
            STATUS_OK
        );
        with_instance_mut(handle, |instance| {
            instance.arena[aggregate_offset..aggregate_offset + aggregate.len()]
                .copy_from_slice(&aggregate);
            instance.arena[scene_offset..scene_offset + scene.len()].copy_from_slice(&scene);
        })
        .unwrap();
        assert_eq!(
            xyg_wasm_aggregate_bin2d(handle, 1, aggregate_offset, aggregate.len()),
            STATUS_PENDING
        );
        assert_eq!(
            xyg_wasm_scene_validate(handle, 2, scene_offset, scene.len()),
            STATUS_OK
        );
        assert_eq!(xyg_wasm_aggregate_step(handle, 1, 1), STATUS_CANCELLED);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn stale_raw_scene_export_does_not_cancel_newer_aggregate() {
        let aggregate = aggregate_request(2);
        let scene = valid_scene();
        let scene_offset = aggregate.len();
        let handle = xyg_wasm_instance_new(1024 * 1024);
        assert_eq!(
            xyg_wasm_arena_resize(handle, scene_offset + scene.len()),
            STATUS_OK
        );
        with_instance_mut(handle, |instance| {
            instance.arena[..aggregate.len()].copy_from_slice(&aggregate);
            instance.arena[scene_offset..].copy_from_slice(&scene);
        })
        .unwrap();
        assert_eq!(
            xyg_wasm_aggregate_bin2d(handle, 2, 0, aggregate.len()),
            STATUS_PENDING
        );
        assert_eq!(
            xyg_wasm_scene_validate(handle, 1, scene_offset, scene.len()),
            STATUS_STALE_SEQUENCE
        );
        assert_eq!(xyg_wasm_aggregate_step(handle, 2, 2), STATUS_OK);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn zero_sequence_aggregate_step_does_not_mutate_an_idle_arena() {
        let handle = xyg_wasm_instance_new(1024);
        assert_eq!(xyg_wasm_arena_resize(handle, 8), STATUS_OK);
        with_instance_mut(handle, |instance| {
            instance.arena.copy_from_slice(b"sentinel");
        })
        .unwrap();

        assert_eq!(
            xyg_wasm_aggregate_step(handle, 0, 1),
            STATUS_INVALID_ARGUMENT
        );
        with_instance_mut(handle, |instance| {
            assert_eq!(instance.arena, b"sentinel");
            assert!(instance.aggregate_job.is_none());
            assert_eq!(instance.aggregate_sequence, 0);
        })
        .unwrap();
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn lifecycle_bounds_and_generation_handles_fail_closed() {
        let handle = xyg_wasm_instance_new(256);
        assert_ne!(handle, 0);
        assert_eq!(xyg_wasm_arena_resize(handle, 257), STATUS_RESOURCE_LIMIT);
        assert_eq!(xyg_wasm_arena_resize(handle, 64), STATUS_OK);
        assert_ne!(xyg_wasm_arena_ptr(handle), 0);
        assert_eq!(xyg_wasm_arena_len(handle), 64);
        assert_eq!(xyg_wasm_arena_high_water(handle), 64);
        assert_eq!(xyg_wasm_arena_resize(handle, 8), STATUS_OK);
        assert_eq!(xyg_wasm_arena_high_water(handle), 64);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
        assert_eq!(xyg_wasm_arena_resize(handle, 1), STATUS_INVALID_HANDLE);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_INVALID_HANDLE);
    }

    #[test]
    fn registry_caps_aggregate_declared_instance_budgets() {
        let mut registry = Registry::new();
        let first = registry.allocate(300 * 1024 * 1024);
        assert_ne!(first, 0);
        assert_eq!(registry.allocate(100 * 1024 * 1024), 0);
        registry.slot_mut(first).unwrap().instance = None;
        assert_ne!(registry.allocate(100 * 1024 * 1024), 0);
    }

    #[test]
    fn typed_series_peak_budget_rejects_before_allocating_and_clears_output() {
        let request = one_point_typed_series();
        let handle = xyg_wasm_instance_new(request.len());
        assert_ne!(handle, 0);
        with_instance_mut(handle, |instance| {
            instance.output.extend_from_slice(b"stale")
        })
        .unwrap();
        write_arena(handle, &request);
        assert_eq!(
            xyg_wasm_scene_compile(handle, 1, 0, request.len()),
            STATUS_RESOURCE_LIMIT
        );
        assert_eq!(xyg_wasm_output_len(handle), 0);
        assert!(
            with_instance_mut(handle, |instance| instance.last_error.clone())
                .unwrap()
                .contains("byte budget")
        );
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn checkpointed_compile_can_cancel_after_progress_and_releases_staging() {
        let request = one_point_typed_series();
        let handle = xyg_wasm_instance_new(1024 * 1024);
        write_arena(handle, &request);
        assert_eq!(
            xyg_wasm_scene_compile_begin(handle, 1, 0, request.len(), 1),
            STATUS_PENDING
        );
        assert_eq!(xyg_wasm_scene_compile_step(handle, 1, 1), STATUS_PENDING);
        assert_eq!(xyg_wasm_scene_compile_records_processed(handle), 1);
        assert_eq!(xyg_wasm_scene_compile_phase(handle), 2);
        assert_eq!(xyg_wasm_cancel(handle, 1), STATUS_OK);
        assert_eq!(xyg_wasm_arena_len(handle), 0);
        assert_eq!(
            xyg_wasm_scene_compile_step(handle, 1, request.len()),
            STATUS_STALE_SEQUENCE
        );

        write_arena(handle, &request);
        assert_eq!(
            xyg_wasm_scene_compile_begin(handle, 2, 0, request.len(), 1),
            STATUS_PENDING
        );
        assert_eq!(
            xyg_wasm_scene_compile_step(handle, 2, request.len()),
            STATUS_PENDING
        );
        assert_eq!(
            xyg_wasm_scene_compile_step(handle, 2, request.len()),
            STATUS_OK
        );
        assert!(xyg_wasm_output_len(handle) > 0);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn typed_series_large_then_small_does_not_retain_capacity_across_operations() {
        let large = typed_series_points(2_000);
        let small = one_point_typed_series();
        let budget = 1_048_576;
        let handle = xyg_wasm_instance_new(budget);
        assert_ne!(handle, 0);
        write_arena(handle, &large);
        assert_eq!(xyg_wasm_scene_compile(handle, 1, 0, large.len()), STATUS_OK);
        with_instance_mut(handle, |instance| {
            assert_eq!(instance.arena.capacity(), 0);
            assert!(instance.output.capacity() <= budget);
        })
        .unwrap();

        write_arena(handle, &small);
        with_instance_mut(handle, |instance| {
            assert_eq!(instance.output.capacity(), 0);
            assert!(instance.arena.capacity() <= small.len());
            assert!(instance.arena.capacity() + instance.output.capacity() <= budget);
        })
        .unwrap();
        assert_eq!(xyg_wasm_scene_compile(handle, 2, 0, small.len()), STATUS_OK);
        with_instance_mut(handle, |instance| {
            assert_eq!(instance.arena.capacity(), 0);
            assert!(instance.output.capacity() <= budget);
            assert!(instance.arena.capacity() + instance.output.capacity() <= budget);
        })
        .unwrap();
        assert_eq!(xyg_wasm_arena_high_water(handle), large.len());
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn rejected_compile_requests_release_large_staging_before_small_retry() {
        let large = typed_series_points(2_000);
        let small = one_point_typed_series();
        let handle = xyg_wasm_instance_new(1_048_576);
        assert_ne!(handle, 0);
        write_arena(handle, &small);
        assert_eq!(xyg_wasm_scene_compile(handle, 1, 0, small.len()), STATUS_OK);

        write_arena(handle, &large);
        assert_eq!(
            xyg_wasm_scene_compile(handle, 1, 0, large.len()),
            STATUS_STALE_SEQUENCE
        );
        with_instance_mut(handle, |instance| assert_eq!(instance.arena.capacity(), 0)).unwrap();

        assert_eq!(xyg_wasm_cancel(handle, 2), STATUS_OK);
        write_arena(handle, &large);
        assert_eq!(
            xyg_wasm_scene_compile(handle, 2, 0, large.len()),
            STATUS_CANCELLED
        );
        with_instance_mut(handle, |instance| assert_eq!(instance.arena.capacity(), 0)).unwrap();

        let malformed = vec![0u8; large.len()];
        write_arena(handle, &malformed);
        assert_eq!(
            xyg_wasm_scene_compile(handle, 3, 0, malformed.len()),
            STATUS_INVALID_ARGUMENT
        );
        with_instance_mut(handle, |instance| assert_eq!(instance.arena.capacity(), 0)).unwrap();

        write_arena(handle, &small);
        assert_eq!(xyg_wasm_scene_compile(handle, 4, 0, small.len()), STATUS_OK);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn rejected_validate_and_prepare_release_large_staging() {
        let valid = valid_scene();
        let large_malformed = vec![0u8; 256 * 1024];
        let handle = xyg_wasm_instance_new(1_048_576);
        assert_ne!(handle, 0);
        write_arena(handle, &valid);
        assert_eq!(
            xyg_wasm_scene_validate(handle, 1, 0, valid.len()),
            STATUS_OK
        );

        write_arena(handle, &large_malformed);
        assert_eq!(
            xyg_wasm_scene_validate(handle, 1, 0, large_malformed.len()),
            STATUS_STALE_SEQUENCE
        );
        with_instance_mut(handle, |instance| assert_eq!(instance.arena.capacity(), 0)).unwrap();

        assert_eq!(xyg_wasm_cancel(handle, 2), STATUS_OK);
        write_arena(handle, &large_malformed);
        assert_eq!(
            xyg_wasm_scene_prepare(handle, 2, 0, large_malformed.len()),
            STATUS_CANCELLED
        );
        with_instance_mut(handle, |instance| assert_eq!(instance.arena.capacity(), 0)).unwrap();

        write_arena(handle, &large_malformed);
        assert_eq!(
            xyg_wasm_scene_prepare(handle, 3, 0, large_malformed.len()),
            STATUS_MALFORMED_SCENE
        );
        with_instance_mut(handle, |instance| assert_eq!(instance.arena.capacity(), 0)).unwrap();

        write_arena(handle, &valid);
        assert_eq!(xyg_wasm_scene_prepare(handle, 4, 0, valid.len()), STATUS_OK);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
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
        assert_eq!(xyg_wasm_output_len(handle), 482);
        assert_eq!(xyg_wasm_last_scene_records(handle), 1);
        with_instance_mut(handle, |instance| {
            assert_eq!(&instance.output[..4], b"XYPB");
            assert_eq!(
                u32::from_le_bytes(instance.output[4..8].try_into().unwrap()),
                scene::BROWSER_PAINTER_VERSION
            );
            assert_eq!(
                u32::from_le_bytes(instance.output[20..24].try_into().unwrap()),
                1
            );
            assert_eq!(
                u32::from_le_bytes(
                    instance.output[scene::BROWSER_PAINTER_HEADER_BYTES
                        + scene::BROWSER_PAINTER_TRACE_BYTES
                        + 8
                        ..scene::BROWSER_PAINTER_HEADER_BYTES
                            + scene::BROWSER_PAINTER_TRACE_BYTES
                            + 12]
                        .try_into()
                        .unwrap()
                ),
                7
            );
            assert_eq!(
                u32::from_le_bytes(instance.output[340..344].try_into().unwrap()),
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
        assert_eq!(
            xyg_wasm_scene_prepare(handle, 1, 0, bytes.len()),
            STATUS_RESOURCE_LIMIT
        );
        assert_eq!(xyg_wasm_output_len(handle), 0);
        with_instance_mut(handle, |instance| {
            assert_eq!(
                instance.last_error,
                "canonical scene fragments into more than 1024 browser traces"
            );
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

    fn packed_cose(total_steps: u32) -> Vec<u8> {
        let n = 3usize;
        let mut out = vec![0u8; 128];
        out[..4].copy_from_slice(b"XYGL");
        out[4..8].copy_from_slice(&1u32.to_le_bytes());
        out[8..12].copy_from_slice(&128u32.to_le_bytes());
        out[12..16].copy_from_slice(&3u32.to_le_bytes()); // positions + pins
        out[16..20].copy_from_slice(&(n as u32).to_le_bytes());
        out[20..24].copy_from_slice(&2u32.to_le_bytes());
        out[24..28].copy_from_slice(&total_steps.to_le_bytes());
        out[32..40].copy_from_slice(&7u64.to_le_bytes());
        for (at, value) in [
            (40, 1.0),
            (48, 1.25),
            (56, 0.08),
            (64, 0.985),
            (72, 0.35),
            (80, 2.5),
        ] as [(usize, f64); 6]
        {
            out[at..at + 8].copy_from_slice(&value.to_le_bytes());
        }
        for values in [[0u64, 1], [1u64, 2]] {
            for value in values {
                out.extend_from_slice(&value.to_le_bytes());
            }
        }
        for values in [[-0.5f64, 0.0, 0.5], [0.0f64, 0.0, 0.0]] {
            for value in values {
                out.extend_from_slice(&value.to_le_bytes());
            }
        }
        out.extend_from_slice(&[1, 0, 0]);
        out
    }

    #[test]
    fn graph_progress_is_revision_safe_cancellable_and_keeps_pins() {
        let request = packed_cose(5);
        let mut native = xyg_engine::graph::ForceState::new_configured(
            3,
            &[0, 1],
            &[1, 2],
            Some(&[-0.5, 0.0, 0.5]),
            Some(&[0.0, 0.0, 0.0]),
            7,
            xyg_engine::graph::LAYOUT_COSE,
            xyg_engine::graph::CoseOptions::default(),
            &[1, 0, 0],
            &[],
        )
        .unwrap();
        native.tick(5);
        let handle = xyg_wasm_instance_new(64 * 1024);
        write_arena(handle, &request);
        assert_eq!(
            xyg_wasm_graph_begin(handle, 1, 9, 0, request.len()),
            STATUS_OK
        );
        assert_eq!(xyg_wasm_graph_step(handle, 1, 8, 1), STATUS_STALE_REVISION);
        assert_eq!(xyg_wasm_graph_step(handle, 1, 9, 1), STATUS_PENDING);
        with_instance_mut(handle, |instance| {
            assert_eq!(&instance.output[..4], b"XYGO");
            assert_eq!(
                f64::from_le_bytes(instance.output[40..48].try_into().unwrap()),
                -0.5
            );
        })
        .unwrap();
        assert_eq!(xyg_wasm_graph_step(handle, 1, 9, 4), STATUS_OK);
        with_instance_mut(handle, |instance| {
            assert!(instance.graph_job.is_none());
            let n = 3;
            for index in 0..n {
                let x_at = 40 + index * 8;
                let y_at = 40 + n * 8 + index * 8;
                assert_eq!(
                    f64::from_le_bytes(instance.output[x_at..x_at + 8].try_into().unwrap()),
                    native.x[index]
                );
                assert_eq!(
                    f64::from_le_bytes(instance.output[y_at..y_at + 8].try_into().unwrap()),
                    native.y[index]
                );
            }
        })
        .unwrap();
        assert_eq!(xyg_wasm_cancel(handle, 1), STATUS_OK);
        assert_eq!(xyg_wasm_graph_step(handle, 1, 9, 1), STATUS_CANCELLED);
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn graph_instances_are_independent_and_malformed_requests_fail_closed() {
        let request = packed_cose(2);
        let first = xyg_wasm_instance_new(64 * 1024);
        let second = xyg_wasm_instance_new(64 * 1024);
        write_arena(first, &request);
        write_arena(second, &request);
        assert_eq!(
            xyg_wasm_graph_begin(first, 1, 1, 0, request.len()),
            STATUS_OK
        );
        assert_eq!(
            xyg_wasm_graph_begin(second, 1, 2, 0, request.len()),
            STATUS_OK
        );
        assert_eq!(xyg_wasm_graph_step(first, 1, 1, 1), STATUS_PENDING);
        assert_eq!(xyg_wasm_graph_step(second, 1, 2, 2), STATUS_OK);
        let mut malformed = request;
        malformed[0] = b'!';
        write_arena(first, &malformed);
        assert_eq!(
            xyg_wasm_graph_begin(first, 2, 3, 0, malformed.len()),
            STATUS_INVALID_ARGUMENT
        );
        let mut future_header = packed_cose(2);
        future_header[28] = 1;
        write_arena(first, &future_header);
        assert_eq!(
            xyg_wasm_graph_begin(first, 2, 3, 0, future_header.len()),
            STATUS_INVALID_ARGUMENT
        );
        assert_eq!(xyg_wasm_instance_dispose(first), STATUS_OK);
        assert_eq!(xyg_wasm_instance_dispose(second), STATUS_OK);
    }

    #[test]
    fn graph_edge_heavy_construction_peak_is_rejected_before_decode() {
        let request = packed_cose(2);
        // The request itself fits, but the conservative CoSE construction
        // high-water (decoded endpoints + ForceState + joined adjacency)
        // does not. This guards the edge multiplier in graph::begin.
        let budget = request.len() * graph::REQUEST_COPY_FACTOR
            + 3 * graph::CONSTRUCTION_BYTES_PER_NODE
            + 2 * graph::CONSTRUCTION_BYTES_PER_EDGE
            - 1;
        let handle = xyg_wasm_instance_new(budget);
        write_arena(handle, &request);
        assert_eq!(
            xyg_wasm_graph_begin(handle, 1, 1, 0, request.len()),
            STATUS_RESOURCE_LIMIT
        );
        with_instance_mut(handle, |instance| {
            assert!(instance.graph_job.is_none());
            assert!(instance.output.is_empty());
        })
        .unwrap();
        assert_eq!(xyg_wasm_instance_dispose(handle), STATUS_OK);
    }
}
