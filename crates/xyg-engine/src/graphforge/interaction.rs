//! Retained graph interaction session (#36, spec/design/graph-interaction.md).
//!
//! A [`GraphSession`] is created from one composed `XYGF` document plus its
//! session-local inputs ([`SessionLoad`]). The hierarchy comes only from the
//! document (`node.parent`), never from the host, so every host sees the same
//! forest. The session owns identity resolution ([`GraphIdentity`]) and the
//! state machine over [`GraphInteractionState`]: either its own value
//! ([`StateSlot::Owned`]) or the one inside a temporal graph
//! ([`StateSlot::Bound`]), so a bound session holds no state of its own and
//! cannot diverge from [`TemporalGraph::frame`].
//!
//! Every mutating operation carries a destination [`Stamp`] and an `op_seq`.
//! A stamp that no longer matches the session is rejected with
//! [`InteractionStatus::Stale`] and changes nothing; a repeated `op_seq`
//! returns the retained outcome without touching state.
//!
//! Implemented here (S1): create, state operations (select / clear / focus),
//! identity, binding. The render and pick pipeline is the S2 seam: the session
//! publishes no render, so `render_revision` stays `0` and an
//! [`ElementRef::Aggregate`] (which names a published render) answers
//! `Stale`. Temporal frame visibility (F4) enters at the same seam, through the
//! bound temporal graph. Nothing here pretends to paint or pick.
//!
//! [`TemporalGraph::frame`]: crate::temporal_graph::TemporalGraph::frame

use std::collections::BTreeSet;
use std::sync::Arc;

use super::composed::ComposedDocument;
use super::identity::{ElementIndex, ElementRef, GraphIdentity, ResolveError};
use super::Uuid;
use crate::graph::COSE_NO_PARENT;
use crate::graph_interaction_state::{
    ElementSet, GraphInteractionState, SelectMode, SelectionTooLarge,
};
use crate::projection::validate_parent_forest;
use crate::temporal_graph::TemporalGraph;

/// Default direct-tier budgets (`_graph.py` `layout_render`).
pub const DEFAULT_NODE_BUDGET: u64 = 200_000;
pub const DEFAULT_EDGE_BUDGET: u64 = 500_000;

/// Stable failure vocabulary of the interaction surface.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum InteractionStatus {
    /// The stamp names another instance or render revision; nothing changed.
    Stale,
    /// Coordination group 0: the instance is not linked.
    Unlinked,
    /// The request is malformed, names an unknown element, or replays an old
    /// `op_seq`.
    Invalid,
    Budget,
    /// State applied but the result did not fit the caller's buffer.
    Capacity,
    SelfEcho,
    StaleRemote,
    SelectionTooLarge,
    CompoundTooLarge,
    /// The bound temporal graph is gone.
    Unbound,
}

impl InteractionStatus {
    pub fn code(self) -> &'static str {
        match self {
            Self::Stale => "GF_INTERACTION_STALE",
            Self::Unlinked => "GF_INTERACTION_UNLINKED",
            Self::Invalid => "GF_INTERACTION_INVALID",
            Self::Budget => "GF_INTERACTION_BUDGET",
            Self::Capacity => "GF_INTERACTION_CAPACITY",
            Self::SelfEcho => "GF_INTERACTION_SELF_ECHO",
            Self::StaleRemote => "GF_INTERACTION_STALE_REMOTE",
            Self::SelectionTooLarge => "GF_INTERACTION_SELECTION_TOO_LARGE",
            Self::CompoundTooLarge => "GF_INTERACTION_COMPOUND_TOO_LARGE",
            Self::Unbound => "GF_INTERACTION_UNBOUND",
        }
    }
}

impl From<SelectionTooLarge> for InteractionStatus {
    fn from(_: SelectionTooLarge) -> Self {
        Self::SelectionTooLarge
    }
}

/// Session-local inputs. The hierarchy is deliberately absent: it is part of
/// the composed document.
#[derive(Clone, Debug, Default)]
pub struct SessionLoad {
    /// Initial positions (both or neither); absent positions are laid out
    /// from `seed` when rendering.
    pub x: Option<Vec<f64>>,
    pub y: Option<Vec<f64>>,
    /// Per-node collapsed flag (`0`/`1`).
    pub collapsed: Option<Vec<u8>>,
    /// Per-node pin (`0`/`1`); seeds the UUID-keyed pin set.
    pub pinned: Option<Vec<u8>>,
    /// `(node_budget, edge_budget)`.
    pub budgets: Option<(u64, u64)>,
    pub seed: u64,
}

/// Opaque handle of a temporal graph in its owner's registry.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct TemporalHandle(pub u64);

/// Locked access to the temporal graph behind a handle, implemented by the
/// registry that owns it. `false` means the graph is gone (disposed).
pub trait TemporalHost: Send + Sync {
    fn with_graph(&self, handle: TemporalHandle, f: &mut dyn FnMut(&mut TemporalGraph)) -> bool;
}

/// Where a session's interaction state lives.
pub enum StateSlot {
    Owned(Box<GraphInteractionState>),
    /// No state of its own: every access runs on the temporal graph's value.
    Bound {
        host: Arc<dyn TemporalHost>,
        handle: TemporalHandle,
    },
}

/// Destination stamp every local event carries.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Stamp {
    pub instance_id: u64,
    pub render_revision: u32,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct OpHeader {
    pub stamp: Stamp,
    /// Strictly increasing per session, starting at 1. Repeating the last
    /// value is an idempotent retry.
    pub op_seq: u64,
}

/// Result of one applied operation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct OpOutcome {
    pub render_revision: u32,
    /// Elements whose selection membership changed.
    pub changed: Vec<ElementRef>,
    /// Whether any state (selection, highlight, focus) changed.
    pub state_changed: bool,
    /// `SelectUuids` entries naming no element of this document.
    pub unmatched: u32,
    /// Selection size after the operation.
    pub selected: usize,
}

pub struct GraphSession {
    instance_id: u64,
    identity: GraphIdentity,
    generation: Option<Uuid>,
    /// Compound parent per node (`COSE_NO_PARENT` for roots), from the document.
    parent: Vec<u64>,
    positions: Option<(Vec<f64>, Vec<f64>)>,
    collapsed: Vec<u8>,
    budgets: (u64, u64),
    seed: u64,
    slot: StateSlot,
    render_revision: u32,
    last_op: Option<(u64, OpOutcome)>,
}

fn invalid<T>() -> Result<T, InteractionStatus> {
    Err(InteractionStatus::Invalid)
}

fn flags(plane: Option<Vec<u8>>, n: usize) -> Result<Vec<u8>, InteractionStatus> {
    match plane {
        None => Ok(vec![0; n]),
        Some(plane) if plane.len() == n && plane.iter().all(|&v| v <= 1) => Ok(plane),
        Some(_) => invalid(),
    }
}

impl GraphSession {
    /// Create an `Owned` session from a composed document.
    pub fn create(
        document: &[u8],
        load: SessionLoad,
        instance_id: u64,
    ) -> Result<Self, InteractionStatus> {
        let doc = ComposedDocument::decode(document).map_err(|_| InteractionStatus::Invalid)?;
        let identity =
            GraphIdentity::from_document(&doc).map_err(|_| InteractionStatus::Invalid)?;
        let n = identity.node_count();
        let generation = doc.generation().map_err(|_| InteractionStatus::Invalid)?;
        let parent = Self::hierarchy(&doc, n)?;

        let positions = match (load.x, load.y) {
            (None, None) => None,
            (Some(x), Some(y))
                if x.len() == n && y.len() == n && x.iter().chain(&y).all(|v| v.is_finite()) =>
            {
                Some((x, y))
            }
            _ => return invalid(),
        };
        let collapsed = flags(load.collapsed, n)?;
        let pinned = flags(load.pinned, n)?;
        let budgets = load
            .budgets
            .unwrap_or((DEFAULT_NODE_BUDGET, DEFAULT_EDGE_BUDGET));
        if budgets.0 == 0 || budgets.1 == 0 {
            return invalid();
        }

        let mut state = GraphInteractionState::default();
        state.set_pinned(
            identity
                .node_uuids()
                .iter()
                .zip(&pinned)
                .filter(|(_, &pin)| pin == 1)
                .map(|(&id, _)| id)
                .collect::<BTreeSet<_>>(),
        );
        Ok(Self {
            instance_id,
            identity,
            generation,
            parent,
            positions,
            collapsed,
            budgets,
            seed: load.seed,
            slot: StateSlot::Owned(Box::new(state)),
            render_revision: 0,
            last_op: None,
        })
    }

    /// Validate and widen the document's `node.parent` / `node.parent.valid`.
    fn hierarchy(doc: &ComposedDocument<'_>, n: usize) -> Result<Vec<u64>, InteractionStatus> {
        let (parents, valid) = match (
            doc.optional_u32s("node.parent"),
            doc.optional_u8s("node.parent.valid"),
        ) {
            (Ok(None), Ok(None)) => return Ok(vec![COSE_NO_PARENT; n]),
            (Ok(Some(parents)), Ok(Some(valid))) => (parents, valid),
            _ => return invalid(),
        };
        if parents.len() != n || valid.len() != n || valid.iter().any(|&v| v > 1) {
            return invalid();
        }
        let dense: Vec<u64> = parents.iter().map(|&p| u64::from(p)).collect();
        if dense
            .iter()
            .zip(valid)
            .any(|(&parent, &v)| v == 1 && parent >= n as u64)
            || validate_parent_forest(&dense, valid).is_err()
        {
            return invalid();
        }
        Ok(dense
            .iter()
            .zip(valid)
            .map(|(&p, &v)| if v == 1 { p } else { COSE_NO_PARENT })
            .collect())
    }

    pub fn instance_id(&self) -> u64 {
        self.instance_id
    }

    /// Revision of the last published render; `0` until the S2 pipeline lands.
    pub fn render_revision(&self) -> u32 {
        self.render_revision
    }

    pub fn identity(&self) -> &GraphIdentity {
        &self.identity
    }

    pub fn generation(&self) -> Option<Uuid> {
        self.generation
    }

    /// Compound parent of `node` (dense), if it has one.
    pub fn parent_of(&self, node: usize) -> Option<usize> {
        let parent = self.parent[node];
        (parent != COSE_NO_PARENT).then_some(parent as usize)
    }

    pub fn positions(&self) -> Option<(&[f64], &[f64])> {
        self.positions.as_ref().map(|(x, y)| (&x[..], &y[..]))
    }

    pub fn collapsed(&self) -> &[u8] {
        &self.collapsed
    }

    pub fn budgets(&self) -> (u64, u64) {
        self.budgets
    }

    pub fn seed(&self) -> u64 {
        self.seed
    }

    pub fn is_bound(&self) -> bool {
        matches!(self.slot, StateSlot::Bound { .. })
    }

    // -- state slot -----------------------------------------------------------

    fn read_state<R>(
        &self,
        f: impl FnOnce(&GraphInteractionState) -> R,
    ) -> Result<R, InteractionStatus> {
        match &self.slot {
            StateSlot::Owned(state) => Ok(f(state)),
            StateSlot::Bound { host, handle } => {
                let (mut f, mut out) = (Some(f), None);
                let found = host.with_graph(*handle, &mut |graph| {
                    out = f.take().map(|f| f(graph.interaction_state()));
                });
                match (found, out) {
                    (true, Some(out)) => Ok(out),
                    _ => Err(InteractionStatus::Unbound),
                }
            }
        }
    }

    fn write_state<R>(
        &mut self,
        f: impl FnOnce(&mut GraphInteractionState) -> R,
    ) -> Result<R, InteractionStatus> {
        match &mut self.slot {
            StateSlot::Owned(state) => Ok(f(state)),
            StateSlot::Bound { host, handle } => {
                let (mut f, mut out) = (Some(f), None);
                let found = host.with_graph(*handle, &mut |graph| {
                    out = f.take().map(|f| f(graph.interaction_state_mut()));
                });
                match (found, out) {
                    (true, Some(out)) => Ok(out),
                    _ => Err(InteractionStatus::Unbound),
                }
            }
        }
    }

    /// Bind to a temporal graph whose node and persisted-edge UUID planes
    /// equal this session's. The session's own state is discarded: the
    /// temporal graph pre-existed and may already be linked. On any failure
    /// the session is unchanged.
    pub fn bind_temporal(
        &mut self,
        host: Arc<dyn TemporalHost>,
        handle: TemporalHandle,
    ) -> Result<(), InteractionStatus> {
        let mut equal = None;
        let found = host.with_graph(handle, &mut |graph| {
            equal = Some(
                self.identity.node_uuids() == graph.node_ids()
                    && self
                        .identity
                        .persisted_edge_uuids()
                        .eq(graph.edge_ids().iter().copied()),
            );
        });
        match (found, equal) {
            (true, Some(true)) => {
                self.slot = StateSlot::Bound { host, handle };
                Ok(())
            }
            (true, Some(false)) => invalid(),
            _ => Err(InteractionStatus::Unbound),
        }
    }

    /// Leave the temporal graph (which keeps its state) for a fresh empty
    /// `Owned` state.
    pub fn unbind(&mut self) {
        self.slot = StateSlot::Owned(Box::default());
    }

    // -- operations -----------------------------------------------------------

    /// Stamp check, idempotent retry, apply, retain.
    fn operate(
        &mut self,
        header: OpHeader,
        apply: impl FnOnce(&mut Self) -> Result<OpOutcome, InteractionStatus>,
    ) -> Result<OpOutcome, InteractionStatus> {
        match &self.last_op {
            _ if header.op_seq == 0 => return invalid(),
            Some((last, outcome)) if *last == header.op_seq => return Ok(outcome.clone()),
            Some((last, _)) if header.op_seq < *last => return invalid(),
            _ => {}
        }
        if header.stamp
            != (Stamp {
                instance_id: self.instance_id,
                render_revision: self.render_revision,
            })
        {
            return Err(InteractionStatus::Stale);
        }
        let outcome = apply(self)?;
        self.last_op = Some((header.op_seq, outcome.clone()));
        Ok(outcome)
    }

    fn resolve_all(&self, refs: &[ElementRef]) -> Result<ElementSet, InteractionStatus> {
        let mut set = ElementSet::default();
        for element in refs {
            match self.identity.resolve(element) {
                Ok(index) => self.identity.insert_into(&mut set, index),
                // No render is published, so an aggregate's stamp can never match.
                Err(ResolveError::NeedsRender) => return Err(InteractionStatus::Stale),
                Err(ResolveError::Unresolved) => return invalid(),
            }
        }
        Ok(set)
    }

    fn select_set(
        &mut self,
        mode: SelectMode,
        delta: ElementSet,
        unmatched: u32,
    ) -> Result<OpOutcome, InteractionStatus> {
        let changed = self.write_state(|state| {
            state
                .select(mode, &delta)
                .map(|changed| (changed, state.selection().len()))
        })??;
        Ok(OpOutcome {
            render_revision: self.render_revision,
            state_changed: !changed.0.is_empty(),
            changed: self.identity.refs_of(&changed.0),
            unmatched,
            selected: changed.1,
        })
    }

    /// Select exact references. An unresolvable reference rejects the whole
    /// operation (`Invalid`); over the cap, `SelectionTooLarge`.
    pub fn select_refs(
        &mut self,
        header: OpHeader,
        refs: &[ElementRef],
        mode: SelectMode,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session| {
            let delta = session.resolve_all(refs)?;
            session.select_set(mode, delta, 0)
        })
    }

    /// Select by UUID. A UUID naming both a node and an edge selects both;
    /// UUIDs naming neither are counted in `unmatched`.
    pub fn select_uuids(
        &mut self,
        header: OpHeader,
        uuids: &[Uuid],
        mode: SelectMode,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session| {
            let mut delta = ElementSet::default();
            let mut unmatched = 0u32;
            for id in uuids {
                let node = session.identity.node_index(id).map(ElementIndex::Node);
                let edge = session.identity.edge_index(id).map(ElementIndex::Edge);
                unmatched += u32::from(node.is_none() && edge.is_none());
                for index in node.into_iter().chain(edge) {
                    session.identity.insert_into(&mut delta, index);
                }
            }
            session.select_set(mode, delta, unmatched)
        })
    }

    /// Empty the selection and highlight planes; focus stays.
    pub fn clear(&mut self, header: OpHeader) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session| {
            let (cleared, before) = session.write_state(|state| {
                let before = state.selection().clone();
                (state.clear(), before)
            })?;
            Ok(OpOutcome {
                render_revision: session.render_revision,
                changed: session.identity.refs_of(&before),
                state_changed: cleared,
                unmatched: 0,
                selected: 0,
            })
        })
    }

    /// Focus one element (focus is independent of selection) or clear focus.
    pub fn focus_ref(
        &mut self,
        header: OpHeader,
        target: Option<&ElementRef>,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session| {
            let focus = match target {
                None => None,
                Some(element) => match session.identity.resolve(element) {
                    Ok(index) => Some(session.identity.focus_of(index)),
                    Err(ResolveError::NeedsRender) => return Err(InteractionStatus::Stale),
                    Err(ResolveError::Unresolved) => return invalid(),
                },
            };
            let (changed, selected) = session.write_state(|state| {
                let changed = state.focus() != focus.as_ref();
                state.set_focus(focus);
                (changed, state.selection().len())
            })?;
            Ok(OpOutcome {
                render_revision: session.render_revision,
                changed: Vec::new(),
                state_changed: changed,
                unmatched: 0,
                selected,
            })
        })
    }

    /// Select the focused element under `mode`; nothing focused is `Invalid`.
    pub fn select_focused(
        &mut self,
        header: OpHeader,
        mode: SelectMode,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session| {
            let focus = session.read_state(|state| state.focus().cloned())?;
            let Some(focus) = focus else {
                return invalid();
            };
            let mut delta = ElementSet::default();
            session.identity.insert_focus(&mut delta, &focus);
            session.select_set(mode, delta, 0)
        })
    }

    /// Current selection as local references.
    pub fn selection(&self) -> Result<Vec<ElementRef>, InteractionStatus> {
        self.read_state(|state| self.identity.refs_of(state.selection()))
    }

    /// Pinned nodes (UUID-keyed, seeded from `load.pinned`).
    pub fn pinned(&self) -> Result<Vec<Uuid>, InteractionStatus> {
        self.read_state(|state| state.pinned_nodes().iter().copied().collect())
    }

    /// Current focus as a local reference.
    pub fn focus(&self) -> Result<Option<ElementRef>, InteractionStatus> {
        self.read_state(|state| {
            state
                .focus()
                .and_then(|focus| self.identity.focus_ref(focus))
        })
    }
}

#[cfg(test)]
mod tests;
