//! Bounded packed graph ingress and progressive Rust layout state for Workers.

use super::{
    fail, Instance, STATUS_CANCELLED, STATUS_INVALID_ARGUMENT, STATUS_OK, STATUS_PENDING,
    STATUS_RESOURCE_LIMIT, STATUS_STALE_REVISION, STATUS_STALE_SEQUENCE,
};
use xyg_engine::graph::{CoseOptions, ForceState, LAYOUT_COSE};

const MAGIC: &[u8; 4] = b"XYGL";
const OUTPUT_MAGIC: &[u8; 4] = b"XYGO";
const VERSION: u32 = 1;
const HEADER: usize = 128;
const OUTPUT_HEADER: usize = 40;
const FLAG_POSITIONS: u32 = 1;
const FLAG_PINS: u32 = 2;
const FLAG_PARENTS: u32 = 4;
const FLAG_BOUNDS: u32 = 8;
const MAX_NODES: usize = 1_000_000;
const MAX_EDGES: usize = 4_000_000;

pub(super) struct GraphJob {
    pub sequence: u32,
    revision: u32,
    total_steps: u32,
    completed_steps: u32,
    state: ForceState,
}

impl std::fmt::Debug for GraphJob {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("GraphJob")
            .field("sequence", &self.sequence)
            .field("revision", &self.revision)
            .field("total_steps", &self.total_steps)
            .field("completed_steps", &self.completed_steps)
            .field("nodes", &self.state.n)
            .finish()
    }
}

fn u32_at(bytes: &[u8], at: usize) -> Option<u32> {
    Some(u32::from_le_bytes(bytes.get(at..at + 4)?.try_into().ok()?))
}
fn u64_at(bytes: &[u8], at: usize) -> Option<u64> {
    Some(u64::from_le_bytes(bytes.get(at..at + 8)?.try_into().ok()?))
}
fn f64_at(bytes: &[u8], at: usize) -> Option<f64> {
    Some(f64::from_le_bytes(bytes.get(at..at + 8)?.try_into().ok()?))
}
fn take_u64(bytes: &[u8], at: &mut usize, count: usize) -> Option<Vec<u64>> {
    let size = count.checked_mul(8)?;
    let slice = bytes.get(*at..at.checked_add(size)?)?;
    *at += size;
    Some(
        slice
            .chunks_exact(8)
            .map(|v| u64::from_le_bytes(v.try_into().unwrap()))
            .collect(),
    )
}
fn take_f64(bytes: &[u8], at: &mut usize, count: usize) -> Option<Vec<f64>> {
    let size = count.checked_mul(8)?;
    let slice = bytes.get(*at..at.checked_add(size)?)?;
    *at += size;
    Some(
        slice
            .chunks_exact(8)
            .map(|v| f64::from_le_bytes(v.try_into().unwrap()))
            .collect(),
    )
}

pub(super) fn begin(
    instance: &mut Instance,
    sequence: u32,
    revision: u32,
    offset: usize,
    length: usize,
) -> i32 {
    instance.output.clear();
    if sequence == 0 || revision == 0 {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "graph sequence and revision must be nonzero",
        );
    }
    if sequence <= instance.cancelled_through {
        return fail(instance, STATUS_CANCELLED, "graph request was cancelled");
    }
    if sequence <= instance.latest_sequence {
        return fail(
            instance,
            STATUS_STALE_SEQUENCE,
            "graph request sequence is stale",
        );
    }
    let arena = std::mem::take(&mut instance.arena);
    let Some(end) = offset.checked_add(length) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "graph staging range overflow",
        );
    };
    let Some(bytes) = arena.get(offset..end) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "graph staging range lies outside the arena",
        );
    };
    if length < HEADER
        || bytes.get(0..4) != Some(MAGIC)
        || u32_at(bytes, 4) != Some(VERSION)
        || u32_at(bytes, 8) != Some(HEADER as u32)
    {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "graph request header is malformed",
        );
    }
    let flags = u32_at(bytes, 12).unwrap();
    if flags & !15 != 0 {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "graph request flags are unsupported",
        );
    }
    let n = u32_at(bytes, 16).unwrap() as usize;
    let m = u32_at(bytes, 20).unwrap() as usize;
    let total_steps = u32_at(bytes, 24).unwrap();
    let seed = u64_at(bytes, 32).unwrap();
    if n > MAX_NODES || m > MAX_EDGES || total_steps == 0 {
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "graph node, edge, or step bound exceeded",
        );
    }
    // Peak includes transferable staging, decoded typed columns, and the
    // Rust-owned ForceState before ingress temporaries are released.
    let retained = length
        .checked_mul(2)
        .and_then(|v| v.checked_add(n.checked_mul(112)?))
        .and_then(|v| v.checked_add(m.checked_mul(16)?));
    if retained.is_none_or(|v| v > instance.max_arena_bytes) {
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "graph retained state exceeds the worker budget",
        );
    }
    let bounds = if flags & FLAG_BOUNDS != 0 {
        Some([
            f64_at(bytes, 88).unwrap(),
            f64_at(bytes, 96).unwrap(),
            f64_at(bytes, 104).unwrap(),
            f64_at(bytes, 112).unwrap(),
        ])
    } else {
        None
    };
    let options = CoseOptions {
        ideal_edge_length: f64_at(bytes, 40).unwrap(),
        repulsion_strength: f64_at(bytes, 48).unwrap(),
        gravity_strength: f64_at(bytes, 56).unwrap(),
        cooling_factor: f64_at(bytes, 64).unwrap(),
        overlap_padding: f64_at(bytes, 72).unwrap(),
        component_spacing: f64_at(bytes, 80).unwrap(),
        bounds,
    };
    let mut at = HEADER;
    let Some(sources) = take_u64(bytes, &mut at, m) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "graph source buffer is truncated",
        );
    };
    let Some(targets) = take_u64(bytes, &mut at, m) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "graph target buffer is truncated",
        );
    };
    let positions = if flags & FLAG_POSITIONS != 0 {
        let Some(x) = take_f64(bytes, &mut at, n) else {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "graph x buffer is truncated",
            );
        };
        let Some(y) = take_f64(bytes, &mut at, n) else {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "graph y buffer is truncated",
            );
        };
        Some((x, y))
    } else {
        None
    };
    let pinned = if flags & FLAG_PINS != 0 {
        let Some(v) = bytes.get(at..at + n) else {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "graph pin buffer is truncated",
            );
        };
        at += n;
        v.to_vec()
    } else {
        Vec::new()
    };
    let parents = if flags & FLAG_PARENTS != 0 {
        let Some(v) = take_u64(bytes, &mut at, n) else {
            return fail(
                instance,
                STATUS_INVALID_ARGUMENT,
                "graph parent buffer is truncated",
            );
        };
        v
    } else {
        Vec::new()
    };
    if at != bytes.len() {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "graph request has trailing bytes",
        );
    }
    let (init_x, init_y) = positions.as_ref().map_or((None, None), |(x, y)| {
        (Some(x.as_slice()), Some(y.as_slice()))
    });
    let Some(state) = ForceState::new_configured(
        n as u64,
        &sources,
        &targets,
        init_x,
        init_y,
        seed,
        LAYOUT_COSE,
        options,
        &pinned,
        &parents,
    ) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "Rust rejected graph topology, CoSE options, pins, compounds, or positions",
        );
    };
    instance.latest_sequence = sequence;
    instance.graph_job = Some(GraphJob {
        sequence,
        revision,
        total_steps,
        completed_steps: 0,
        state,
    });
    instance.last_error.clear();
    STATUS_OK
}

pub(super) fn step(instance: &mut Instance, sequence: u32, revision: u32, steps: u32) -> i32 {
    instance.output.clear();
    if sequence <= instance.cancelled_through {
        instance.graph_job = None;
        return fail(instance, STATUS_CANCELLED, "graph request was cancelled");
    }
    let Some(job) = instance.graph_job.as_mut() else {
        return fail(instance, STATUS_STALE_SEQUENCE, "graph job is not active");
    };
    if job.sequence != sequence {
        return fail(
            instance,
            STATUS_STALE_SEQUENCE,
            "graph job sequence is stale",
        );
    }
    if job.revision != revision {
        return fail(
            instance,
            STATUS_STALE_REVISION,
            "graph render revision is stale",
        );
    }
    if steps == 0 {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "graph checkpoint steps must be positive",
        );
    }
    let take = steps.min(job.total_steps - job.completed_steps);
    job.state.tick(take);
    job.completed_steps += take;
    if !job.state.alpha.is_finite()
        || job
            .state
            .x
            .iter()
            .chain(&job.state.y)
            .any(|value| !value.is_finite())
    {
        instance.graph_job = None;
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "graph force produced a non-finite checkpoint",
        );
    }
    let n = job.state.n;
    let Some(output_len) = OUTPUT_HEADER.checked_add(n.checked_mul(16).unwrap_or(usize::MAX))
    else {
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "graph output size overflow",
        );
    };
    if output_len > instance.max_arena_bytes {
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "graph checkpoint exceeds worker budget",
        );
    }
    let mut out = Vec::with_capacity(output_len);
    out.extend_from_slice(OUTPUT_MAGIC);
    out.extend_from_slice(&VERSION.to_le_bytes());
    out.extend_from_slice(&(OUTPUT_HEADER as u32).to_le_bytes());
    out.extend_from_slice(&revision.to_le_bytes());
    out.extend_from_slice(&job.completed_steps.to_le_bytes());
    out.extend_from_slice(&job.total_steps.to_le_bytes());
    out.extend_from_slice(&(n as u32).to_le_bytes());
    out.extend_from_slice(&job.state.alpha.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for value in &job.state.x {
        out.extend_from_slice(&value.to_le_bytes());
    }
    for value in &job.state.y {
        out.extend_from_slice(&value.to_le_bytes());
    }
    let complete = job.completed_steps == job.total_steps || job.state.alpha < 0.001;
    instance.output = out;
    instance.last_error.clear();
    if complete {
        instance.graph_job = None;
        STATUS_OK
    } else {
        STATUS_PENDING
    }
}
