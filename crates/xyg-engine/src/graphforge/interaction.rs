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
//! Implemented here: create, state operations (select / clear / focus / hover /
//! highlight), identity, binding, the render publication
//! ([`render::RenderOutput`], F2 pipeline order, temporal visibility F4),
//! compound disclosure, pin / move / relayout, and the keyboard walks. The
//! S3 adds publication geometry/picking, coordination and atomic update.
//! The C/WASM ABI uses the shared `wire` codec and admitted transaction.
//!
//! [`TemporalGraph::frame`]: crate::temporal_graph::TemporalGraph::frame

use std::collections::BTreeSet;
use std::sync::Arc;

use super::composed::ComposedDocument;
use super::identity::{ElementIndex, ElementRef, GraphIdentity};
use super::Uuid;
use crate::graph::COSE_NO_PARENT;
use crate::graph_interaction_state::{
    ElementSet, GraphInteractionState, SelectMode, SelectionTooLarge, MAX_GRAPH_SELECTION_REFS,
};
use crate::projection::validate_parent_forest;
use crate::temporal_graph::TemporalGraph;

mod coordination;
mod layout;
mod paint;
mod pick;
mod render;
mod update;
mod walk;

pub use coordination::GraphCoordinationEvent;
pub use layout::{
    DisclosureAction, DisclosureReport, MoveCommit, MoveSpace, NodePosition, RelayoutReport,
    INITIAL_LAYOUT_STEPS, MAX_GRAPH_INTERACTION_WORK, MAX_RELAYOUT_STEPS, RELAYOUT_SETTLED_ALPHA,
};
pub use paint::{EdgePiece, FramePaint, NodePaint, PaintGeometry};
pub use pick::{
    PickIndex, PickTarget, SelectionPolicy, MAX_GRAPH_PICK_CANDIDATES, MAX_GRAPH_PICK_GRID_ENTRIES,
    MAX_GRAPH_PICK_PRIMITIVES,
};
pub use render::{Camera, RenderOutput, NOT_RENDERED};
pub mod wire;

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
    /// `render_revision` reached `u32::MAX`; no further structural change is
    /// possible, and the failed operation changed nothing. The host recreates
    /// the session.
    RevisionExhausted,
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
            Self::RevisionExhausted => "GF_INTERACTION_REVISION_EXHAUSTED",
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
#[derive(Clone)]
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
#[derive(Clone, Debug, Default, PartialEq)]
pub struct OpOutcome {
    pub render_revision: u32,
    /// Elements whose selection membership changed.
    pub changed: Vec<ElementRef>,
    /// Whether any state (selection, highlight, focus) changed.
    pub state_changed: bool,
    /// `SelectUuids` entries naming no element of this document.
    pub unmatched: u32,
    /// State identities removed by structural replacement (per plane).
    pub dropped: u32,
    /// Selection size after the operation.
    pub selected: usize,
    /// Node positions to persist (`graph.positions`): pin and move commit.
    pub positions: Vec<NodePosition>,
    pub relayout: Option<RelayoutReport>,
    pub disclosure: Option<DisclosureReport>,
}

/// Transient hover emphasis; never part of the shared interaction state.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
struct Hover {
    nodes: Vec<usize>,
    edges: Vec<usize>,
}

#[derive(Clone)]
pub struct GraphSession {
    // Only set on an admitted wire transaction candidate.
    transaction_world: Option<(Vec<u8>, Vec<u8>, u64)>,
    instance_id: u64,
    coordination: coordination::Link,
    identity: GraphIdentity,
    labels: Vec<String>,
    generation: Option<Uuid>,
    /// Compound parent per node (`COSE_NO_PARENT` for roots), from the document.
    parent: Vec<u64>,
    directed: bool,
    node_style: paint::SourceStyle,
    edge_style: paint::SourceStyle,
    /// `1` where `parent` is a real parent.
    parent_valid: Vec<u8>,
    /// Composed edge endpoints (dense node indices).
    edge_source: Vec<u64>,
    edge_target: Vec<u64>,
    /// Ordinal of each persisted edge among persisted edges (the temporal
    /// graph's edge order); `u32::MAX` for derived edges.
    edge_ordinal: Vec<u32>,
    positions: Option<(Vec<f64>, Vec<f64>)>,
    collapsed: Vec<u8>,
    budgets: (u64, u64),
    seed: u64,
    slot: StateSlot,
    render_revision: u32,
    last_op: Option<(u64, OpOutcome)>,
    /// Temporal frame revision last folded into `render_revision` (F4).
    seen_temporal: u64,
    camera: Option<Camera>,
    published: Option<RenderOutput>,
    /// Revision `published` was built at (`0`: nothing published).
    published_revision: u32,
    hover: Hover,
    move_origin: Option<layout::MoveOrigin>,
    relayout: Option<layout::Relayout>,
    /// Render node a focus ring is walking around.
    ring_anchor: Option<u64>,
    /// Deterministic work units the session has performed, for the bounded
    /// complexity proofs (every pass adds the elements it touches).
    work: u64,
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
        let container = super::container::Container::decode(document, super::container::DOCUMENT_MAGIC).map_err(|_| InteractionStatus::Invalid)?;
        let mut labels = Vec::new();
        for (name,count) in [("node.label",n),("edge.label",identity.edge_count())] {
            if let Some(section) = container.get(name,0) {
                let text = section.as_texts(name).map_err(|_| InteractionStatus::Invalid)?;
                if text.len()!=count {return invalid();}
                labels.extend(text.into_iter().map(str::to_owned));
            } else { labels.resize(labels.len()+count,String::new()); }
        }
        let generation = doc.generation().map_err(|_| InteractionStatus::Invalid)?;
        let parent = Self::hierarchy(&doc, n)?;
        let edge_source = doc
            .u64s("edge.source")
            .map_err(|_| InteractionStatus::Invalid)?;
        let edge_target = doc
            .u64s("edge.target")
            .map_err(|_| InteractionStatus::Invalid)?;
        let edges = identity.edge_count();
        let mut node_style = paint::SourceStyle::read(&doc, "node", n)?;
        let mut edge_style = paint::SourceStyle::read(&doc, "edge", edges)?;
        let directed = match doc
            .optional_u8s("graph.directed")
            .map_err(|_| InteractionStatus::Invalid)?
        {
            None => false,
            Some([v]) if *v <= 1 => *v == 1,
            _ => return invalid(),
        };
        if edge_source.len() != edges
            || edge_target.len() != edges
            || edge_source
                .iter()
                .chain(&edge_target)
                .any(|&v| v >= n as u64)
        {
            return invalid();
        }
        let mut persisted = 0u32;
        let edge_ordinal = (0..edges)
            .map(|edge| {
                if identity.is_derived(edge) {
                    u32::MAX
                } else {
                    persisted += 1;
                    persisted - 1
                }
            })
            .collect();

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
        let mut selected = ElementSet::default();
        for (node, flag) in node_style.flags.iter_mut().enumerate() {
            if *flag & crate::graph_style::FLAG_SELECTED != 0 {
                identity.insert_into(&mut selected, ElementIndex::Node(node));
                if selected.len() > MAX_GRAPH_SELECTION_REFS {
                    return Err(InteractionStatus::SelectionTooLarge);
                }
            }
            *flag &= !crate::graph_style::FLAG_SELECTED;
        }
        for (edge, flag) in edge_style.flags.iter_mut().enumerate() {
            if *flag & crate::graph_style::FLAG_SELECTED != 0 {
                identity.insert_into(&mut selected, ElementIndex::Edge(edge));
                if selected.len() > MAX_GRAPH_SELECTION_REFS {
                    return Err(InteractionStatus::SelectionTooLarge);
                }
            }
            *flag &= !crate::graph_style::FLAG_SELECTED;
        }
        state.select(SelectMode::Replace, &selected)?;
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
            transaction_world: None,
            instance_id,
            coordination: coordination::Link::default(),
            identity,
            labels,
            generation,
            parent_valid: parent
                .iter()
                .map(|&p| u8::from(p != COSE_NO_PARENT))
                .collect(),
            parent,
            directed,
            node_style,
            edge_style,
            edge_source,
            edge_target,
            edge_ordinal,
            positions,
            collapsed,
            budgets,
            seed: load.seed,
            slot: StateSlot::Owned(Box::new(state)),
            render_revision: 0,
            last_op: None,
            seen_temporal: 0,
            camera: None,
            published: None,
            published_revision: 0,
            hover: Hover::default(),
            move_origin: None,
            relayout: None,
            ring_anchor: None,
            work: 0,
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

    /// Stamp revision: advances on every structural change (see `render`).
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

    /// Deterministic work units performed so far (see the field).
    pub fn work(&self) -> u64 {
        self.work
    }

    pub fn is_bound(&self) -> bool {
        matches!(self.slot, StateSlot::Bound { .. })
    }

    // -- state slot -----------------------------------------------------------

    /// Read-only access to the state for the public getters.
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

    /// Run `f` on one consistent world: the session, the shared interaction
    /// state, and (when bound) the temporal graph's published visibility and
    /// revision, all under a single registry lock. Validating the temporal
    /// revision, mutating, and capturing render inputs therefore cannot be
    /// separated by a frame advancing in between (F4).
    ///
    /// An `Owned` session lends its state out of the slot for the call, so
    /// code inside `f` must use `world.state`, never the session's getters.
    fn locked<R>(
        &mut self,
        f: impl FnOnce(&mut Self, World<'_>) -> R,
    ) -> Result<R, InteractionStatus> {
        self.locked_validated(|_,_| Ok(()), f)
    }

    /// Validate against the canonical owner before splitting its state/world.
    /// Used by wire updates so endpoint validation and reply share one access.
    fn locked_validated<R>(
        &mut self,
        validate: impl FnOnce(&Self, &TemporalGraph)->Result<(), InteractionStatus>,
        f: impl FnOnce(&mut Self, World<'_>)->R,
    )->Result<R, InteractionStatus> {
        let bound = match &self.slot {
            StateSlot::Bound { host, handle } => Some((Arc::clone(host), *handle)),
            StateSlot::Owned(_) => None,
        };
        let Some((host, handle)) = bound else {
            let StateSlot::Owned(slot) = &mut self.slot else {
                return Err(InteractionStatus::Invalid);
            };
            let mut state = std::mem::take(&mut **slot);
            let snapshot = self.transaction_world.take();
            let out = f(
                self,
                World {
                    state: &mut state,
                    visibility: snapshot.as_ref().map(|(n, e, _)| (&n[..], &e[..])),
                    temporal_revision: snapshot.as_ref().map_or(0, |(_, _, r)| *r),
                },
            );
            self.transaction_world = snapshot;
            if let StateSlot::Owned(slot) = &mut self.slot {
                **slot = state;
            }
            return Ok(out);
        };
        let (mut f, mut validate, mut out) = (Some(f), Some(validate), None);
        let session = &mut *self;
        let found = host.with_graph(handle, &mut |graph| {
            if let Some(f) = f.take() {
                if let Err(error)=validate.take().expect("one owner access")(session,graph) {
                    out=Some(Err(error));return;
                }
                let (state, visibility, temporal_revision) = graph.world_parts();
                out = Some(Ok(f(
                    session,
                    World {
                        state,
                        visibility,
                        temporal_revision,
                    },
                )));
            }
        });
        match (found, out) {
            (true, Some(out)) => out,
            _ => Err(InteractionStatus::Unbound),
        }
    }

    /// Fail before any mutation if the revision cannot advance.
    pub(super) fn reserve_revision(&self) -> Result<(), InteractionStatus> {
        if self.render_revision == u32::MAX {
            Err(InteractionStatus::RevisionExhausted)
        } else {
            Ok(())
        }
    }

    /// Advance the revision. Callers [`reserve_revision`](Self::reserve_revision)
    /// first, so the revision never wraps and a stale stamp is never revived.
    pub(super) fn bump(&mut self) {
        self.render_revision = self.render_revision.saturating_add(1);
        self.ring_anchor = None;
    }

    /// Fold a changed temporal frame into the revision, inside the lock the
    /// caller already holds (F4). A frame change also invalidates the retained
    /// relayout, which was built from the previous visibility.
    fn sync_world(&mut self, world: &World<'_>) -> Result<(), InteractionStatus> {
        if world.temporal_revision != self.seen_temporal {
            self.reserve_revision()?;
            self.seen_temporal = world.temporal_revision;
            self.relayout = None;
            self.bump();
        }
        Ok(())
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
        self.reserve_revision()?;
        let mut bound = None;
        let found = host.with_graph(handle, &mut |graph| {
            bound = Some((
                self.identity.node_uuids() == graph.node_ids()
                    && self
                        .identity
                        .persisted_edge_uuids()
                        .eq(graph.edge_ids().iter().copied()),
                graph.applied_revision(),
            ));
        });
        match (found, bound) {
            (true, Some((true, revision))) => {
                self.slot = StateSlot::Bound { host, handle };
                self.seen_temporal = revision;
                // The pin authority and visibility changed with the slot.
                self.relayout = None;
                self.bump();
                Ok(())
            }
            (true, Some((false, _))) => invalid(),
            _ => Err(InteractionStatus::Unbound),
        }
    }

    /// Leave the temporal graph (which keeps its state) for a fresh empty
    /// `Owned` state.
    pub fn unbind(&mut self) -> Result<(), InteractionStatus> {
        self.reserve_revision()?;
        self.slot = StateSlot::Owned(Box::default());
        self.seen_temporal = 0;
        // The temporal visibility and the pin authority no longer apply.
        self.relayout = None;
        self.bump();
        Ok(())
    }

    // -- operations -----------------------------------------------------------

    /// Idempotent retry, then, under one lock: fold the temporal revision,
    /// stamp check, apply. The outcome is retained for retries.
    fn operate(
        &mut self,
        header: OpHeader,
        apply: impl FnOnce(&mut Self, &mut World<'_>) -> Result<OpOutcome, InteractionStatus>,
    ) -> Result<OpOutcome, InteractionStatus> {
        match &self.last_op {
            _ if header.op_seq == 0 => return invalid(),
            Some((last, outcome)) if *last == header.op_seq => return Ok(outcome.clone()),
            Some((last, _)) if header.op_seq < *last => return invalid(),
            _ => {}
        }
        let outcome = self.locked(|session, mut world| {
            session.sync_world(&world)?;
            if header.stamp
                != (Stamp {
                    instance_id: session.instance_id,
                    render_revision: session.render_revision,
                })
            {
                return Err(InteractionStatus::Stale);
            }
            apply(session, &mut world)
        })??;
        self.last_op = Some((header.op_seq, outcome.clone()));
        Ok(outcome)
    }

    /// Resolve references into state identities. Aggregates expand to their
    /// member source nodes, each distinct aggregate once, and the total is
    /// admitted against the selection cap *before* anything is allocated, so a
    /// repeated or oversized aggregate cannot cost more than it is allowed to
    /// select. Any failure rejects the whole set.
    fn resolve_all(&mut self, refs: &[ElementRef]) -> Result<ElementSet, InteractionStatus> {
        if refs.len() > MAX_GRAPH_SELECTION_REFS {
            return Err(InteractionStatus::SelectionTooLarge);
        }
        let mut set = ElementSet::default();
        let mut groups = BTreeSet::new();
        for element in refs {
            match self.resolve(element)? {
                render::Resolved::Element(index) => self.identity.insert_into(&mut set, index),
                render::Resolved::Group { render } => {
                    groups.insert(render);
                }
            }
        }
        let mut expanded = 0u64;
        if !groups.is_empty() {
            let render = self.published().ok_or(InteractionStatus::Stale)?;
            // Count the union: explicit node refs already represented by one
            // of these disjoint render groups must not consume the cap twice.
            let overlap = set
                .nodes
                .iter()
                .filter(|id| {
                    self.identity
                        .node_index(id)
                        .is_some_and(|node| groups.contains(&(render.member_of[node] as usize)))
                })
                .count();
            let mut total = set.len() - overlap;
            let admission_work = set.nodes.len() as u64;
            for &group in &groups {
                total += render.members_of_node(group).len();
                if total > MAX_GRAPH_SELECTION_REFS {
                    self.work += refs.len() as u64 + admission_work;
                    return Err(InteractionStatus::SelectionTooLarge);
                }
            }
            for &group in &groups {
                for &member in render.members_of_node(group) {
                    self.identity
                        .insert_into(&mut set, ElementIndex::Node(member as usize));
                }
                expanded += render.members_of_node(group).len() as u64;
            }
            expanded += admission_work;
        }
        self.work += refs.len() as u64 + expanded;
        Ok(set)
    }

    /// Outcome of an operation that changed no element membership.
    fn outcome(&self, world: &World<'_>, state_changed: bool) -> OpOutcome {
        OpOutcome {
            render_revision: self.render_revision,
            state_changed,
            selected: world.state.selection().len(),
            ..OpOutcome::default()
        }
    }

    fn select_set(
        &mut self,
        world: &mut World<'_>,
        mode: SelectMode,
        delta: ElementSet,
        unmatched: u32,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.admit_outbound()?;
        let changed = world.state.select(mode, &delta)?;
        self.queue_selection(world.state);
        Ok(OpOutcome {
            render_revision: self.render_revision,
            state_changed: !changed.is_empty(),
            changed: self.identity.refs_of(&changed),
            unmatched,
            selected: world.state.selection().len(),
            ..OpOutcome::default()
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
        self.operate(header, |session, world| {
            let delta = session.resolve_all(refs)?;
            session.select_set(world, mode, delta, 0)
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
        self.operate(header, |session, world| {
            if uuids.len() > MAX_GRAPH_SELECTION_REFS {
                return Err(InteractionStatus::SelectionTooLarge);
            }
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
            session.work += uuids.len() as u64;
            session.select_set(world, mode, delta, unmatched)
        })
    }

    /// Empty the selection and highlight planes; focus stays.
    pub fn clear(&mut self, header: OpHeader) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session, world| {
            session.admit_outbound()?;
            let before = world.state.selection().clone();
            let cleared = world.state.clear();
            session.queue_selection(world.state);
            Ok(OpOutcome {
                render_revision: session.render_revision,
                changed: session.identity.refs_of(&before),
                state_changed: cleared,
                ..OpOutcome::default()
            })
        })
    }

    /// Focus one element (focus is independent of selection) or clear focus.
    pub fn focus_ref(
        &mut self,
        header: OpHeader,
        target: Option<&ElementRef>,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session, world| {
            let focus = match target {
                None => None,
                Some(element) => Some(match session.resolve(element)? {
                    render::Resolved::Element(index) => session.identity.focus_of(index),
                    // An aggregate is focused through its lowest-index visible
                    // member; focus is UUID-keyed, so it cannot name the group.
                    render::Resolved::Group { render } => {
                        let published = session.published().ok_or(InteractionStatus::Stale)?;
                        let stand_in = published.focus_node[render];
                        session
                            .identity
                            .focus_of(ElementIndex::Node(stand_in as usize))
                    }
                }),
            };
            session.ring_anchor = None;
            let changed = world.state.focus() != focus.as_ref();
            world.state.set_focus(focus);
            Ok(session.outcome(world, changed))
        })
    }

    /// Select the focused element under `mode`; nothing focused is `Invalid`.
    /// When the focus sits on a drawn stop that stands for several elements
    /// (an aggregate node, a collapsed group, an aggregate edge), the whole
    /// stop is selected, exactly as a pointer selection of it would.
    pub fn select_focused(
        &mut self,
        header: OpHeader,
        mode: SelectMode,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session, world| {
            let Some(focus) = world.state.focus().cloned() else {
                return invalid();
            };
            let delta = session.focus_membership(&focus)?;
            session.select_set(world, mode, delta, 0)
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

/// One consistent view of the shared world, held for the length of a lock.
struct World<'a> {
    /// The one shared interaction state (the temporal graph's when bound).
    state: &'a mut GraphInteractionState,
    /// Published source visibility `(nodes, persisted edges)` of the bound
    /// temporal graph; `None` when unbound or before its first frame.
    visibility: Option<(&'a [u8], &'a [u8])>,
    /// Revision of that frame (`0` when unbound).
    temporal_revision: u64,
}

#[cfg(test)]
mod tests;
