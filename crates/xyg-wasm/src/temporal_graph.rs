//! Packed direct-browser temporal graph binding and frame transport (#45).

use super::{
    fail, Instance, STATUS_CANCELLED, STATUS_INVALID_ARGUMENT, STATUS_OK, STATUS_RESOURCE_LIMIT,
    STATUS_STALE_REVISION,
};
use xyg_engine::projection::{GraphProjection, Uuid};
use xyg_engine::temporal::{CancelFlag, TemporalColumn, TemporalError, TemporalPrecision};
use xyg_engine::temporal_graph::{TemporalBindingInput, TemporalGraph};

const MAGIC: &[u8; 4] = b"XYTG";
const OUTPUT_MAGIC: &[u8; 4] = b"XYTF";
const VERSION: u32 = 1;
const CREATE_HEADER: usize = 32;
const FRAME_HEADER: usize = 56;
const OUTPUT_HEADER: usize = 64;
const OP_CREATE: u32 = 1;
const OP_FRAME: u32 = 2;
const MAX_ENTITIES: usize = 5_000_000;

#[derive(Debug)]
pub(super) struct WasmTemporalGraph {
    graph: TemporalGraph,
    sources: Vec<u64>,
    targets: Vec<u64>,
}

fn u32_at(bytes: &[u8], at: usize) -> Option<u32> {
    Some(u32::from_le_bytes(bytes.get(at..at + 4)?.try_into().ok()?))
}
fn u64_at(bytes: &[u8], at: usize) -> Option<u64> {
    Some(u64::from_le_bytes(bytes.get(at..at + 8)?.try_into().ok()?))
}
fn i64_at(bytes: &[u8], at: usize) -> Option<i64> {
    Some(i64::from_le_bytes(bytes.get(at..at + 8)?.try_into().ok()?))
}

fn take_uuids(bytes: &[u8], at: &mut usize, count: usize) -> Option<Vec<Uuid>> {
    let size = count.checked_mul(16)?;
    let slice = bytes.get(*at..at.checked_add(size)?)?;
    *at += size;
    Some(
        slice
            .chunks_exact(16)
            .map(|value| value.try_into().unwrap())
            .collect(),
    )
}

fn take_column(bytes: &[u8], at: &mut usize, count: usize) -> Option<TemporalColumn> {
    let value_bytes = count.checked_mul(8)?;
    let values = bytes
        .get(*at..at.checked_add(value_bytes)?)?
        .chunks_exact(8)
        .map(|value| i64::from_le_bytes(value.try_into().unwrap()))
        .collect::<Vec<_>>();
    *at += value_bytes;
    let validity = bytes.get(*at..at.checked_add(count)?)?;
    *at += count;
    TemporalColumn::from_utc_micros(&values, validity, "UTC", TemporalPrecision::Microsecond).ok()
}

fn status(error: TemporalError) -> i32 {
    match error {
        TemporalError::Cancelled => STATUS_CANCELLED,
        TemporalError::StaleRevision => STATUS_STALE_REVISION,
        TemporalError::BudgetExceeded | TemporalError::CapacityExceeded => STATUS_RESOURCE_LIMIT,
        _ => STATUS_INVALID_ARGUMENT,
    }
}

fn create(instance: &mut Instance, bytes: &[u8]) -> i32 {
    if bytes.len() < CREATE_HEADER || u32_at(bytes, 8) != Some(CREATE_HEADER as u32) {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph create header is malformed",
        );
    }
    let flags = u32_at(bytes, 16).unwrap_or(u32::MAX);
    if flags & !0x3f != 0 {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph plane flags are invalid",
        );
    }
    let n = u32_at(bytes, 20).unwrap_or(u32::MAX) as usize;
    let m = u32_at(bytes, 24).unwrap_or(u32::MAX) as usize;
    if n.checked_add(m).is_none_or(|total| total > MAX_ENTITIES) {
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "temporal graph entity bound exceeded",
        );
    }
    let mut at = CREATE_HEADER;
    let Some(node_ids) = take_uuids(bytes, &mut at, n) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph node UUIDs are truncated",
        );
    };
    let Some(edge_ids) = take_uuids(bytes, &mut at, m) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph edge UUIDs are truncated",
        );
    };
    let Some(source_ids) = take_uuids(bytes, &mut at, m) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph source UUIDs are truncated",
        );
    };
    let Some(target_ids) = take_uuids(bytes, &mut at, m) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph target UUIDs are truncated",
        );
    };
    let mut columns = Vec::with_capacity(6);
    for index in 0..6 {
        columns.push(if flags & (1 << index) != 0 {
            take_column(bytes, &mut at, if index < 3 { n } else { m })
        } else {
            None
        });
    }
    if at != bytes.len()
        || columns
            .iter()
            .enumerate()
            .any(|(i, column)| flags & (1 << i) != 0 && column.is_none())
    {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph planes are malformed",
        );
    }
    let Ok(projection) =
        GraphProjection::new(&node_ids, &edge_ids, &source_ids, &target_ids, None, true)
    else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph topology is invalid",
        );
    };
    let sources = projection.sources().to_vec();
    let targets = projection.targets().to_vec();
    let nodes = TemporalBindingInput {
        valid_from: columns[0].as_ref(),
        valid_to: columns[1].as_ref(),
        event_at: columns[2].as_ref(),
    };
    let edges = TemporalBindingInput {
        valid_from: columns[3].as_ref(),
        valid_to: columns[4].as_ref(),
        event_at: columns[5].as_ref(),
    };
    match TemporalGraph::bind(&projection, nodes, edges) {
        Ok(graph) => {
            instance.temporal_graph = Some(WasmTemporalGraph {
                graph,
                sources,
                targets,
            });
            instance.output.clear();
            instance.last_error.clear();
            STATUS_OK
        }
        Err(error) => fail(
            instance,
            status(error),
            "Rust rejected temporal graph bindings",
        ),
    }
}

fn frame(instance: &mut Instance, bytes: &[u8]) -> i32 {
    if bytes.len() != FRAME_HEADER || u32_at(bytes, 8) != Some(FRAME_HEADER as u32) {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph frame header is malformed",
        );
    }
    let revision = u64_at(bytes, 16).unwrap();
    let cursor = i64_at(bytes, 24).unwrap();
    let start = i64_at(bytes, 32).unwrap();
    let end = i64_at(bytes, 40).unwrap();
    let Ok(budget) = usize::try_from(u64_at(bytes, 48).unwrap()) else {
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "temporal graph budget overflows usize",
        );
    };
    let Some(bound) = instance.temporal_graph.as_mut() else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph is not initialized",
        );
    };
    let cancel = CancelFlag::new();
    let frame = match bound
        .graph
        .frame(revision, cursor, start, end, &cancel, budget)
    {
        Ok(frame) => frame,
        Err(error) => return fail(instance, status(error), "temporal graph frame failed"),
    };
    let nv = frame.node_visibility();
    let ev = frame.edge_visibility();
    let visible_nodes = frame.visible_node_ids();
    let visible_edges = frame.visible_edge_ids();
    let mut dense = vec![u64::MAX; nv.len()];
    let mut next = 0u64;
    for (index, &visible) in nv.iter().enumerate() {
        if visible == 1 {
            dense[index] = next;
            next += 1;
        }
    }
    let mut sources = Vec::new();
    let mut targets = Vec::new();
    for (index, &visible) in ev.iter().enumerate() {
        if visible == 1 {
            sources.push(dense[bound.sources[index] as usize]);
            targets.push(dense[bound.targets[index] as usize]);
        }
    }
    let output_len = OUTPUT_HEADER
        .checked_add(nv.len())
        .and_then(|v| v.checked_add(ev.len()))
        .and_then(|v| v.checked_add(visible_nodes.len() * 16))
        .and_then(|v| v.checked_add(visible_edges.len() * 16))
        .and_then(|v| v.checked_add(sources.len() * 16));
    if output_len.is_none_or(|length| length > instance.max_arena_bytes) {
        return fail(
            instance,
            STATUS_RESOURCE_LIMIT,
            "temporal graph frame exceeds worker budget",
        );
    }
    let mut out = Vec::with_capacity(output_len.unwrap());
    out.extend_from_slice(OUTPUT_MAGIC);
    out.extend_from_slice(&VERSION.to_le_bytes());
    out.extend_from_slice(&(OUTPUT_HEADER as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&revision.to_le_bytes());
    out.extend_from_slice(&cursor.to_le_bytes());
    out.extend_from_slice(&start.to_le_bytes());
    out.extend_from_slice(&end.to_le_bytes());
    out.extend_from_slice(&(nv.len() as u32).to_le_bytes());
    out.extend_from_slice(&(ev.len() as u32).to_le_bytes());
    out.extend_from_slice(&(visible_nodes.len() as u32).to_le_bytes());
    out.extend_from_slice(&(visible_edges.len() as u32).to_le_bytes());
    out.extend_from_slice(nv);
    out.extend_from_slice(ev);
    for id in visible_nodes {
        out.extend_from_slice(id);
    }
    for id in visible_edges {
        out.extend_from_slice(id);
    }
    for value in sources {
        out.extend_from_slice(&value.to_le_bytes());
    }
    for value in targets {
        out.extend_from_slice(&value.to_le_bytes());
    }
    instance.output = out;
    instance.last_error.clear();
    STATUS_OK
}

pub(super) fn execute(instance: &mut Instance, offset: usize, length: usize) -> i32 {
    instance.output.clear();
    let Some(end) = offset.checked_add(length) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph command range overflow",
        );
    };
    let arena = std::mem::take(&mut instance.arena);
    let Some(bytes) = arena.get(offset..end) else {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph command is outside staging",
        );
    };
    if bytes.get(0..4) != Some(MAGIC) || u32_at(bytes, 4) != Some(VERSION) {
        return fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph command header is incompatible",
        );
    }
    match u32_at(bytes, 12) {
        Some(OP_CREATE) => create(instance, bytes),
        Some(OP_FRAME) => frame(instance, bytes),
        _ => fail(
            instance,
            STATUS_INVALID_ARGUMENT,
            "temporal graph operation is unsupported",
        ),
    }
}
