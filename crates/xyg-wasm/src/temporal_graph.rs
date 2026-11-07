//! Packed direct-browser temporal graph binding and frame transport (#45).

use super::{
    fail, Instance, STATUS_CANCELLED, STATUS_INVALID_ARGUMENT, STATUS_OK, STATUS_RESOURCE_LIMIT,
    STATUS_STALE_REVISION,
};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use xyg_engine::graph_interaction_state::{ElementSet, Focus, HighlightPlane};
use xyg_engine::graphforge::interaction::{TemporalHandle, TemporalHost};
use xyg_engine::projection::{GraphProjection, Uuid};
use xyg_engine::temporal::{CancelFlag, TemporalColumn, TemporalError, TemporalPrecision};
use xyg_engine::temporal_graph::{TemporalBindingInput, TemporalGraph, TemporalGraphFrame};

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
    owner: Arc<TemporalOwner>,
    frame: Option<TemporalGraphFrame>,
    frame_context: Option<(i64, u64)>,
    sources: Vec<u64>,
    targets: Vec<u64>,
}

/// The instance owns this lease; bound sessions only borrow its authority.
/// Revocation is protected by the same mutex as every access, so an Arc held
/// by a session never extends the disposed graph's usable lifetime (§1.1).
/// This adapter must never enter the instance registry: exports already hold
/// that mutex. Its only lock is the temporal world lock, after the session.
#[derive(Debug)]
struct TemporalOwner {
    generation: u64,
    graph: Mutex<Option<TemporalGraph>>,
}

impl TemporalHost for TemporalOwner {
    fn with_graph(&self, handle: TemporalHandle, f: &mut dyn FnMut(&mut TemporalGraph)) -> bool {
        if handle.0 != self.generation {
            return false;
        }
        let mut graph = self.graph.lock().expect("WASM temporal owner poisoned");
        let Some(graph) = graph.as_mut() else {
            return false;
        };
        f(graph);
        true
    }
}

impl WasmTemporalGraph {
    fn new(
        graph: TemporalGraph,
        sources: Vec<u64>,
        targets: Vec<u64>,
    ) -> Result<Self, TemporalError> {
        static NEXT_GENERATION: AtomicU64 = AtomicU64::new(0);
        let previous = NEXT_GENERATION
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |value| {
                value.checked_add(1)
            })
            .map_err(|_| TemporalError::CapacityExceeded)?;
        Ok(Self {
            owner: Arc::new(TemporalOwner {
                generation: previous + 1,
                graph: Mutex::new(Some(graph)),
            }),
            frame: None,
            frame_context: None,
            sources,
            targets,
        })
    }

    pub(super) fn owner(&self) -> (Arc<dyn TemporalHost>, TemporalHandle) {
        (self.owner.clone(), TemporalHandle(self.owner.generation))
    }

    pub(super) fn freeze(
        &self,
        session: &xyg_engine::graphforge::interaction::wire::WireSession,
        revision: u64,
        render: u32,
        window: Option<(i64, i64)>,
        timezone: &str,
        focus: [f32; 4],
        budget: usize,
    ) -> Result<Vec<u8>, TemporalError> {
        use xyg_engine::temporal_graph_frozen::FrozenTemporalGraph;
        let (owner, handle) = self.owner();
        let publication = session
            .frozen_publication(owner.owner_identity(), handle, revision, render)
            .map_err(|_| TemporalError::StaleRevision)?;
        let graph = self
            .owner
            .graph
            .lock()
            .expect("WASM temporal owner poisoned");
        let graph = graph.as_ref().ok_or(TemporalError::Disposed)?;
        let frame = self
            .frame
            .as_ref()
            .filter(|f| f.revision() == revision)
            .ok_or(TemporalError::StaleRevision)?;
        let frozen = FrozenTemporalGraph::acquire(
            graph,
            frame,
            window,
            timezone,
            Some(publication),
            &CancelFlag::new(),
            budget,
        )?;
        let captured = frozen.with_focus_f32(focus, budget)?;
        let captured = if let Some((window, revision)) = self.frame_context {
            captured.with_controller_context(window, revision, budget)?
        } else {
            captured
        };
        Ok(captured.bytes().to_vec())
    }
    pub(super) fn dispose(&self) {
        self.owner
            .graph
            .lock()
            .expect("WASM temporal owner poisoned")
            .take();
    }

    /// Conservative retained admission charge, not an RSS measurement. 512
    /// bytes per canonical row covers UUID/dense-map capacity, interval/event
    /// columns, topology and retained visibility; 256 per tree entry covers
    /// state nodes and tree slack. Exact derived strings are charged too.
    /// Staging, frame scratch, publication and serialized replies are separate
    /// caller charges. Saturation makes arithmetic overflow refuse admission.
    pub(super) fn retained_bytes(&self) -> usize {
        let graph = self
            .owner
            .graph
            .lock()
            .expect("WASM temporal owner poisoned");
        let topology = self
            .sources
            .capacity()
            .saturating_add(self.targets.capacity())
            .saturating_mul(std::mem::size_of::<u64>());
        let Some(graph) = graph.as_ref() else {
            return 4096usize.saturating_add(topology);
        };
        let state = graph.interaction_state();
        let set_bytes = |set: &ElementSet| {
            set.derived
                .iter()
                .fold(set.len().saturating_mul(256), |bytes, key| {
                    bytes.saturating_add(key.result_id.as_ref().map_or(0, |id| id.len()))
                })
        };
        let mut bytes = 4096usize
            .saturating_add(topology)
            .saturating_add(
                graph
                    .node_ids()
                    .len()
                    .saturating_add(graph.edge_ids().len())
                    .saturating_mul(512),
            )
            .saturating_add(state.pinned_nodes().len().saturating_mul(256))
            .saturating_add(set_bytes(state.selection()));
        for plane in [
            HighlightPlane::Path,
            HighlightPlane::Community,
            HighlightPlane::External,
        ] {
            bytes = bytes.saturating_add(set_bytes(state.highlight_set(plane)));
        }
        if let Some(focus) = state.focus() {
            bytes = bytes.saturating_add(256);
            if let Focus::Derived(key) = focus {
                bytes = bytes.saturating_add(key.result_id.as_ref().map_or(0, |id| id.len()));
            }
        }
        bytes
    }
}

impl Drop for WasmTemporalGraph {
    fn drop(&mut self) {
        self.dispose();
    }
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
            let owner = match WasmTemporalGraph::new(graph, sources, targets) {
                Ok(owner) => owner,
                Err(error) => {
                    return fail(
                        instance,
                        status(error),
                        "temporal owner generation exhausted",
                    )
                }
            };
            instance.temporal_graph = Some(owner);
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
    let context =
        if u32_at(bytes, 4) == Some(2) && bytes.len() == 72 && u32_at(bytes, 8) == Some(72) {
            let window = i64_at(bytes, 56).unwrap();
            if window < 0 {
                return fail(
                    instance,
                    STATUS_INVALID_ARGUMENT,
                    "invalid controller window context",
                );
            }
            Some((window, u64_at(bytes, 64).unwrap()))
        } else {
            None
        };
    if context.is_none()
        && (bytes.len() != FRAME_HEADER
            || u32_at(bytes, 4) != Some(VERSION)
            || u32_at(bytes, 8) != Some(FRAME_HEADER as u32))
    {
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
    let result = bound
        .owner
        .graph
        .lock()
        .expect("WASM temporal owner poisoned")
        .as_mut()
        .ok_or(TemporalError::Disposed)
        .and_then(|graph| {
            graph.frame_with_output(revision, cursor, start, end, &cancel, budget, |frame| {
                encode_frame(
                    frame,
                    &bound.sources,
                    &bound.targets,
                    instance.max_arena_bytes,
                )
            })
        });
    match result {
        Ok((frame, output)) => {
            bound.frame = Some(frame);
            bound.frame_context = context;
            instance.output = output;
            instance.last_error.clear();
            STATUS_OK
        }
        Err(error) => fail(instance, status(error), "temporal graph frame failed"),
    }
}

fn encode_frame(
    frame: &TemporalGraphFrame,
    canonical_sources: &[u64],
    canonical_targets: &[u64],
    max_output_bytes: usize,
) -> Result<Vec<u8>, TemporalError> {
    let nv = frame.node_visibility();
    let ev = frame.edge_visibility();
    let visible_nodes = frame.visible_node_ids();
    let visible_edges = frame.visible_edge_ids();
    let output_len = OUTPUT_HEADER
        .checked_add(nv.len())
        .and_then(|v| v.checked_add(ev.len()))
        .and_then(|v| v.checked_add(visible_nodes.len().checked_mul(16)?))
        .and_then(|v| v.checked_add(visible_edges.len().checked_mul(16)?))
        .and_then(|v| v.checked_add(visible_edges.len().checked_mul(16)?));
    if output_len.is_none_or(|length| length > max_output_bytes) {
        return Err(TemporalError::BudgetExceeded);
    }
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
            sources.push(dense[canonical_sources[index] as usize]);
            targets.push(dense[canonical_targets[index] as usize]);
        }
    }
    let mut out = Vec::with_capacity(output_len.unwrap());
    out.extend_from_slice(OUTPUT_MAGIC);
    out.extend_from_slice(&VERSION.to_le_bytes());
    out.extend_from_slice(&(OUTPUT_HEADER as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&frame.revision().to_le_bytes());
    out.extend_from_slice(&frame.cursor_micros().to_le_bytes());
    out.extend_from_slice(&frame.range_start_micros().to_le_bytes());
    out.extend_from_slice(&frame.range_end_micros().to_le_bytes());
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
    Ok(out)
}

pub(super) fn execute(instance: &mut Instance, offset: usize, length: usize) -> i32 {
    // A retained GraphSession shares this owner. Admit replacement/frame work
    // before touching either owner or output; no second canonical state is kept.
    if let Some(session) = &instance.graph_session {
        let old = instance
            .temporal_graph
            .as_ref()
            .map_or(0, |g| g.retained_bytes());
        let staged = instance.arena.get(offset..offset.saturating_add(length));
        let incoming = staged
            .filter(|b| b.get(..4) == Some(MAGIC) && u32_at(b, 12) == Some(OP_CREATE))
            .map_or(0, |b| {
                (u32_at(b, 20).unwrap_or(u32::MAX) as usize)
                    .saturating_add(u32_at(b, 24).unwrap_or(u32::MAX) as usize)
                    .saturating_mul(2048)
            });
        let charge = session
            .retained_budget()
            .saturating_add(old.saturating_mul(3))
            .saturating_add(incoming)
            .saturating_add(instance.arena.capacity().saturating_mul(8))
            .saturating_add(instance.output.capacity());
        if charge > instance.max_arena_bytes {
            return fail(
                instance,
                STATUS_RESOURCE_LIMIT,
                "temporal/session world exceeds worker budget",
            );
        }
    }
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
    if bytes.get(0..4) != Some(MAGIC)
        || !(u32_at(bytes, 4) == Some(VERSION)
            || (u32_at(bytes, 4) == Some(2) && u32_at(bytes, 12) == Some(OP_FRAME)))
    {
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

#[cfg(test)]
mod tests {
    use super::*;

    fn graph() -> WasmTemporalGraph {
        let nodes = [[1; 16], [2; 16]];
        let edges = [[3; 16]];
        let projection =
            GraphProjection::new(&nodes, &edges, &nodes[..1], &nodes[1..], None, true).unwrap();
        let graph = TemporalGraph::bind(
            &projection,
            TemporalBindingInput::default(),
            TemporalBindingInput::default(),
        )
        .unwrap();
        WasmTemporalGraph::new(graph, vec![0], vec![1]).unwrap()
    }

    #[test]
    fn output_budget_failure_does_not_publish_and_exact_retry_matches_native_frame() {
        let handle = crate::xyg_wasm_instance_new(1024 * 1024);
        assert_ne!(handle, 0);
        super::super::with_instance_mut(handle, |instance| {
            instance.temporal_graph = Some(graph());
            let bound = instance.temporal_graph.as_ref().unwrap();
            let (owner, authority) = bound.owner();
            let mut native = None;
            owner.with_graph(authority, &mut |graph| {
                native = Some(graph.frame(1, 0, 0, 1, &CancelFlag::new(), 100).unwrap());
            });
            let native = native.unwrap();
            let expected = encode_frame(&native, &[0], &[1], 1024).unwrap();
            let mut bytes = MAGIC.to_vec();
            for value in [VERSION, FRAME_HEADER as u32, OP_FRAME] {
                bytes.extend_from_slice(&value.to_le_bytes());
            }
            for value in [2u64, 0, 0, 1, 100] {
                bytes.extend_from_slice(&value.to_le_bytes());
            }
            // The output cap is exact. One-byte-under admission must not
            // consume revision 2 or change the world observed by a session.
            instance.max_arena_bytes = expected.len() - 1;
            assert_eq!(frame(instance, &bytes), STATUS_RESOURCE_LIMIT);
            assert!(owner.with_graph(authority, &mut |graph| {
                assert_eq!(graph.applied_revision(), 1);
                assert_eq!(
                    graph.applied_visibility(),
                    Some((native.node_visibility(), native.edge_visibility()))
                );
                assert!(graph.freeze(&native).is_ok());
            }));
            instance.max_arena_bytes = expected.len();
            assert_eq!(frame(instance, &bytes), STATUS_OK);
            let mut expected = expected;
            expected[16..24].copy_from_slice(&2u64.to_le_bytes());
            assert_eq!(instance.output, expected);
            assert_eq!(frame(instance, &bytes), STATUS_STALE_REVISION);
        })
        .unwrap();
        assert_eq!(crate::xyg_wasm_instance_dispose(handle), STATUS_OK);
    }

    #[test]
    fn bound_access_and_frames_share_one_canonical_state() {
        let graph = graph();
        let (owner, handle) = graph.owner();
        let before = graph.retained_bytes();
        assert!(owner.with_graph(handle, &mut |graph| {
            graph.set_selection([[2; 16]], [[3; 16]]).unwrap();
            graph.set_pinned_nodes([[2; 16]]).unwrap();
        }));
        assert_eq!(graph.retained_bytes(), before + 3 * 256);
        let mut frame = None;
        assert!(owner.with_graph(handle, &mut |graph| {
            frame = Some(
                graph
                    .frame(
                        1,
                        0,
                        0,
                        1,
                        &CancelFlag::new(),
                        graph.required_budget().unwrap(),
                    )
                    .unwrap(),
            );
        }));
        let frame = frame.unwrap();
        assert_eq!(frame.selected_visible_node_ids(), &[[2; 16]]);
        assert_eq!(frame.selected_visible_edge_ids(), &[[3; 16]]);
        assert_eq!(frame.pinned_visible_node_ids(), &[[2; 16]]);
    }

    #[test]
    fn generations_reject_cross_instance_or_replacement_handles() {
        let first = graph();
        let second = graph();
        let (first_owner, first_handle) = first.owner();
        let (second_owner, second_handle) = second.owner();
        assert_ne!(first_handle, second_handle);
        let mut called = false;
        assert!(!first_owner.with_graph(second_handle, &mut |_| called = true));
        assert!(!second_owner.with_graph(first_handle, &mut |_| called = true));
        assert!(!called);
    }

    #[test]
    fn replacement_and_instance_drop_revoke_outstanding_arcs() {
        let mut slot = Some(graph());
        let (old_owner, old_handle) = slot.as_ref().unwrap().owner();
        slot = Some(graph());
        let (new_owner, new_handle) = slot.as_ref().unwrap().owner();
        assert!(!old_owner.with_graph(old_handle, &mut |_| panic!("disposed owner used")));
        assert!(new_owner.with_graph(new_handle, &mut |_| {}));
        drop(slot);
        assert!(!new_owner.with_graph(new_handle, &mut |_| panic!("dropped instance used")));
    }

    #[test]
    fn explicit_disposal_is_idempotent_and_drops_canonical_storage() {
        let graph = graph();
        let (owner, handle) = graph.owner();
        let before = graph.retained_bytes();
        graph.dispose();
        graph.dispose();
        assert!(graph.retained_bytes() < before);
        assert!(graph.owner.graph.lock().unwrap().is_none());
        assert!(!owner.with_graph(handle, &mut |_| panic!("disposed graph used")));
    }

    #[test]
    fn owner_is_send_sync_and_disposal_serializes_with_active_access() {
        fn send_sync<T: Send + Sync>() {}
        send_sync::<TemporalOwner>();
        let graph = graph();
        let (owner, handle) = graph.owner();
        let (entered_tx, entered_rx) = std::sync::mpsc::channel();
        let (resume_tx, resume_rx) = std::sync::mpsc::channel();
        let worker = std::thread::spawn(move || {
            assert!(owner.with_graph(handle, &mut |graph| {
                entered_tx.send(()).unwrap();
                resume_rx.recv().unwrap();
                graph.set_selection([[1; 16]], []).unwrap();
            }));
        });
        entered_rx.recv().unwrap();
        let (owner, handle) = graph.owner();
        let disposer = std::thread::spawn(move || graph.dispose());
        resume_tx.send(()).unwrap();
        worker.join().unwrap();
        disposer.join().unwrap();
        assert!(!owner.with_graph(handle, &mut |_| panic!("post-disposal access")));
    }
}
