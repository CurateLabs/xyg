//! Positions and structural operations (#36 §2.5, §2.6): pin, move, relayout,
//! compound disclosure, and highlight planes.
//!
//! Every successful structural change advances the render revision, so a host
//! holding the previous publication is rejected as stale and repaints. A failed
//! operation changes nothing: inputs are validated before the first write.

use std::collections::HashMap;

use super::render::{Resolved, Visible};
use super::{GraphSession, InteractionStatus, OpHeader, OpOutcome};
use crate::graph::{CoseOptions, ForceState, COSE_NO_PARENT, LAYOUT_COSE};
use crate::graph_interaction_state::{ElementSet, HighlightPlane, SelectMode};
use crate::graph_style::{
    compound_collapse_transition, COMPOUND_ACTION_COLLAPSE, COMPOUND_ACTION_EXPAND,
    COMPOUND_ACTION_TOGGLE, MAX_COMPOUND_TRANSITION_NODES,
};
use crate::graphforge::identity::{ElementIndex, ElementRef};

/// Force steps run to seed positions the document did not author (matches the
/// host `layout_render` default of 300 iterations).
pub const INITIAL_LAYOUT_STEPS: u32 = 300;
/// Upper bound of one `relayout_step`.
pub const MAX_RELAYOUT_STEPS: u32 = 64;
/// Interactive work ceiling of one operation: `steps * (nodes + edges)`.
pub const MAX_GRAPH_INTERACTION_WORK: u64 = 4_000_000;
/// Alpha below which the force layout has settled (the engine's own cutoff).
pub const RELAYOUT_SETTLED_ALPHA: f64 = 0.001;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DisclosureAction {
    Expand,
    Collapse,
    Toggle,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum MoveSpace {
    /// `dx`/`dy` are data units.
    Data,
    /// `dx`/`dy` are CSS pixels, converted through the last rendered camera.
    ScreenDelta,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum MoveCommit {
    /// Update the position; remember where the move started.
    Preview,
    /// Apply any final delta, pin the node, and report its position.
    Commit,
    /// Restore the position the move started from, bit for bit.
    Cancel,
}

/// A node position in a result (`graph.positions`).
#[derive(Clone, Debug, PartialEq)]
pub struct NodePosition {
    pub node: ElementRef,
    pub x: f64,
    pub y: f64,
    pub pinned: bool,
}

/// Progress of the relayout state (`graph.relayout`).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct RelayoutReport {
    pub alpha: f64,
    pub done: bool,
}

/// Result of a disclosure change (`graph.disclosure`).
#[derive(Clone, Debug, PartialEq)]
pub struct DisclosureReport {
    pub node: ElementRef,
    pub collapsed: bool,
}

/// Where an in-flight move started.
#[derive(Clone, Copy, Debug)]
pub(super) struct MoveOrigin {
    node: usize,
    x: f64,
    y: f64,
}

/// The retained force layout and the world it was built from. It is valid
/// only while both still hold: the same visible nodes (a frame change) and the
/// same pin set (which the shared state can change from outside the session).
pub(super) struct Relayout {
    force: ForceState,
    active: Vec<usize>,
    pins: Vec<u8>,
}

/// The visible subgraph the force layout runs on, in compact indices, with
/// the map back to source indices. Invisible nodes do not repel, invisible
/// edges do not pull, and an invisible parent hands its children to the
/// nearest surviving ancestor.
struct Problem {
    active: Vec<usize>,
    sources: Vec<u64>,
    targets: Vec<u64>,
    parents: Vec<u64>,
}

impl GraphSession {
    fn layout_problem(&mut self, vis: &Visible) -> Problem {
        let n = self.identity.node_count();
        let mut dense = vec![COSE_NO_PARENT; n];
        let mut active = Vec::new();
        for (node, &visible) in vis.node.iter().enumerate() {
            if visible == 1 {
                dense[node] = active.len() as u64;
                active.push(node);
            }
        }
        let hierarchy = self.surviving_hierarchy(&vis.node);
        let parents = active
            .iter()
            .map(|&node| match hierarchy.parent[node] {
                COSE_NO_PARENT => COSE_NO_PARENT,
                parent => dense[parent as usize],
            })
            .collect();
        let work = hierarchy.work;
        drop(hierarchy);
        let (mut sources, mut targets) = (Vec::new(), Vec::new());
        for edge in 0..self.edge_source.len() {
            if vis.edge[edge] == 1 {
                sources.push(dense[self.edge_source[edge] as usize]);
                targets.push(dense[self.edge_target[edge] as usize]);
            }
        }
        self.work += work + (n + self.edge_source.len()) as u64;
        Problem {
            active,
            sources,
            targets,
            parents,
        }
    }

    /// Lay the graph out from the deterministic seed when the document and
    /// load authored no positions: CoSE over the *visible* subgraph and its
    /// surviving hierarchy. A node invisible at that moment is parked at the
    /// visible layout's centroid until a relayout moves it.
    pub(super) fn ensure_positions(&mut self, vis: &Visible) -> Result<(), InteractionStatus> {
        if self.positions.is_some() {
            return Ok(());
        }
        self.positions = Some(self.initial_positions(vis)?);
        Ok(())
    }

    /// Keep freshly seeded positions local until an operation is admitted.
    fn initial_positions(
        &mut self,
        vis: &Visible,
    ) -> Result<(Vec<f64>, Vec<f64>), InteractionStatus> {
        let n = self.identity.node_count();
        let problem = self.layout_problem(vis);
        let m = problem.active.len();
        let mut layout = ForceState::new_configured(
            m as u64,
            &problem.sources,
            &problem.targets,
            None,
            None,
            self.seed,
            LAYOUT_COSE,
            CoseOptions::default(),
            &[],
            &problem.parents,
        )
        .ok_or(InteractionStatus::Invalid)?;
        layout.tick(INITIAL_LAYOUT_STEPS);
        self.work += u64::from(INITIAL_LAYOUT_STEPS) * (m + problem.sources.len()) as u64;
        if !layout.alpha.is_finite() || layout.x.iter().chain(&layout.y).any(|v| !v.is_finite()) {
            return Err(InteractionStatus::Invalid);
        }
        let centroid = |plane: &[f64]| {
            if plane.is_empty() {
                0.0
            } else {
                plane.iter().sum::<f64>() / plane.len() as f64
            }
        };
        let (mut x, mut y) = (vec![centroid(&layout.x); n], vec![centroid(&layout.y); n]);
        for (k, &node) in problem.active.iter().enumerate() {
            x[node] = layout.x[k];
            y[node] = layout.y[k];
        }
        Ok((x, y))
    }

    /// The node a structural operation names. Groups and edges are not nodes.
    fn node_target(&self, target: &ElementRef) -> Result<usize, InteractionStatus> {
        match self.resolve(target)? {
            Resolved::Element(ElementIndex::Node(node)) => Ok(node),
            _ => Err(InteractionStatus::Invalid),
        }
    }

    fn node_position(&self, node: usize, pinned: bool) -> NodePosition {
        let (x, y) = self
            .positions
            .as_ref()
            .map_or((f64::NAN, f64::NAN), |(x, y)| (x[node], y[node]));
        NodePosition {
            node: self.identity.node_ref(node),
            x,
            y,
            pinned,
        }
    }

    /// A position change invalidates the relayout state (it was built from the
    /// old positions and pins) and the render. Callers reserved the revision.
    fn positions_changed(&mut self) {
        self.relayout = None;
        self.bump();
    }

    /// Pin or unpin a node at its current position.
    pub fn pin(
        &mut self,
        header: OpHeader,
        target: &ElementRef,
        on: bool,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session, world| {
            let node = session.node_target(target)?;
            let id = session.identity.node_uuids()[node];
            let changed = world.state.pinned_nodes().contains(&id) != on;
            if changed {
                session.reserve_revision()?;
                let vis = session.visible(world.visibility)?;
                session.ensure_positions(&vis)?;
                world.state.set_pin(id, on);
                session.positions_changed();
            }
            let mut outcome = session.outcome(world, changed);
            if changed {
                outcome.positions = vec![session.node_position(node, on)];
            }
            Ok(outcome)
        })
    }

    /// Move a node: preview steps, then commit (pins) or cancel (restores).
    pub fn move_node(
        &mut self,
        header: OpHeader,
        target: &ElementRef,
        delta: (f64, f64),
        space: MoveSpace,
        commit: MoveCommit,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session, world| {
            let node = session.node_target(target)?;
            session.reserve_revision()?;
            if let Some(origin) = session.move_origin {
                if origin.node != node {
                    return Err(InteractionStatus::Invalid);
                }
            }
            // Reject malformed requests before seeding any force layout.
            let data_delta = match commit {
                MoveCommit::Cancel => {
                    session.move_origin.ok_or(InteractionStatus::Invalid)?;
                    (0.0, 0.0)
                }
                _ => {
                    let delta = match space {
                        MoveSpace::Data => delta,
                        MoveSpace::ScreenDelta => session
                            .camera
                            .ok_or(InteractionStatus::Invalid)?
                            .data_delta(delta.0, delta.1),
                    };
                    if !delta.0.is_finite() || !delta.1.is_finite() {
                        return Err(InteractionStatus::Invalid);
                    }
                    delta
                }
            };
            let seeded = if session.positions.is_none() {
                let vis = session.visible(world.visibility)?;
                Some(session.initial_positions(&vis)?)
            } else {
                None
            };
            let (px, py) = session
                .positions
                .as_ref()
                .or(seeded.as_ref())
                .ok_or(InteractionStatus::Invalid)?;
            let (x, y) = (px[node], py[node]);
            let (next, origin) = match commit {
                MoveCommit::Cancel => {
                    let origin = session.move_origin.ok_or(InteractionStatus::Invalid)?;
                    ((origin.x, origin.y), None)
                }
                MoveCommit::Preview | MoveCommit::Commit => {
                    let (dx, dy) = data_delta;
                    let next = (x + dx, y + dy);
                    if !(dx.is_finite()
                        && dy.is_finite()
                        && next.0.is_finite()
                        && next.1.is_finite())
                    {
                        return Err(InteractionStatus::Invalid);
                    }
                    let origin = session.move_origin.or(Some(MoveOrigin { node, x, y }));
                    (next, origin)
                }
            };
            if let Some(positions) = seeded {
                session.positions = Some(positions);
            }
            let id = session.identity.node_uuids()[node];
            let pin = commit == MoveCommit::Commit;
            if pin {
                world.state.set_pin(id, true);
            }
            if let Some((px, py)) = session.positions.as_mut() {
                px[node] = next.0;
                py[node] = next.1;
            }
            session.move_origin = if commit == MoveCommit::Preview {
                origin
            } else {
                None
            };
            session.positions_changed();
            let mut outcome = session.outcome(world, true);
            if pin {
                outcome.positions = vec![session.node_position(node, true)];
            }
            Ok(outcome)
        })
    }

    /// Step the CoSE relayout over the visible subgraph, seeded from the
    /// current positions with pinned nodes held bit-exact and the surviving
    /// hierarchy. Always CoSE regardless of the composition's original layout:
    /// it is the one engine honoring pins and parents. The retained force
    /// state is rebuilt whenever the visible nodes or the authoritative pin
    /// set differ from the ones it was built with.
    pub fn relayout_step(
        &mut self,
        header: OpHeader,
        steps: u32,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session, world| {
            if steps == 0 || steps > MAX_RELAYOUT_STEPS {
                return Err(InteractionStatus::Invalid);
            }
            let vis = session.visible(world.visibility)?;
            let active = vis.node.iter().filter(|&&v| v == 1).count();
            let live_edges = vis.edge.iter().filter(|&&v| v == 1).count();
            let force_steps = u64::from(steps)
                + if session.positions.is_none() {
                    u64::from(INITIAL_LAYOUT_STEPS)
                } else {
                    0
                };
            if force_steps * (active + live_edges) as u64 > MAX_GRAPH_INTERACTION_WORK {
                return Err(InteractionStatus::Budget);
            }
            session.reserve_revision()?;
            session.ensure_positions(&vis)?;
            let n = session.identity.node_count();
            let mut pins = vec![0u8; n];
            for id in world.state.pinned_nodes() {
                if let Some(i) = session.identity.node_index(id) {
                    pins[i] = 1;
                }
            }
            session.work += (n + world.state.pinned_nodes().len()) as u64;
            let problem = session.layout_problem(&vis);
            let fresh = session
                .relayout
                .as_ref()
                .is_some_and(|r| r.active == problem.active && r.pins == pins);
            if !fresh {
                let (x, y) = session
                    .positions
                    .as_ref()
                    .ok_or(InteractionStatus::Invalid)?;
                let pick = |plane: &[f64]| -> Vec<f64> {
                    problem.active.iter().map(|&i| plane[i]).collect()
                };
                let mask: Vec<u8> = problem.active.iter().map(|&i| pins[i]).collect();
                let force = ForceState::new_configured(
                    problem.active.len() as u64,
                    &problem.sources,
                    &problem.targets,
                    Some(&pick(x)),
                    Some(&pick(y)),
                    session.seed,
                    LAYOUT_COSE,
                    CoseOptions::default(),
                    &mask,
                    &problem.parents,
                )
                .ok_or(InteractionStatus::Invalid)?;
                session.relayout = Some(Relayout {
                    force,
                    active: problem.active.clone(),
                    pins,
                });
            }
            let retained = session
                .relayout
                .as_mut()
                .ok_or(InteractionStatus::Invalid)?;
            retained.force.tick(steps);
            session.work += u64::from(steps) * (active + live_edges) as u64;
            let force = &retained.force;
            if !force.alpha.is_finite() || force.x.iter().chain(&force.y).any(|v| !v.is_finite()) {
                session.relayout = None;
                return Err(InteractionStatus::Invalid);
            }
            let alpha = force.alpha;
            if let Some((px, py)) = session.positions.as_mut() {
                for (k, &node) in retained.active.iter().enumerate() {
                    px[node] = force.x[k];
                    py[node] = force.y[k];
                }
            }
            session.bump();
            let mut outcome = session.outcome(world, true);
            outcome.relayout = Some(RelayoutReport {
                alpha,
                done: alpha < RELAYOUT_SETTLED_ALPHA,
            });
            Ok(outcome)
        })
    }

    /// Expand, collapse, or toggle a compound node. Explicit disclosure is a
    /// direct-tier feature bounded at [`MAX_COMPOUND_TRANSITION_NODES`] source
    /// nodes; aggregates take no action (spec §2.5, graph-mark.md §7.1.5).
    pub fn toggle_disclosure(
        &mut self,
        header: OpHeader,
        target: &ElementRef,
        action: DisclosureAction,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session, world| {
            let n = session.identity.node_count();
            if n > MAX_COMPOUND_TRANSITION_NODES {
                return Err(InteractionStatus::CompoundTooLarge);
            }
            let node = session.node_target(target)?;
            let ids: Vec<u64> = (0..n as u64).collect();
            let action = match action {
                DisclosureAction::Expand => COMPOUND_ACTION_EXPAND,
                DisclosureAction::Collapse => COMPOUND_ACTION_COLLAPSE,
                DisclosureAction::Toggle => COMPOUND_ACTION_TOGGLE,
            };
            let tier = session.published().map_or(0, |render| render.tier as u8);
            let mut next = vec![0u8; n];
            let changed = compound_collapse_transition(
                &ids,
                &session.parent,
                &session.parent_valid,
                &session.collapsed,
                node as u64,
                action,
                tier,
                &mut next,
            )
            .ok_or(InteractionStatus::Invalid)?;
            session.work += n as u64;
            if changed {
                session.reserve_revision()?;
                session.collapsed = next;
                session.bump();
            }
            let mut outcome = session.outcome(world, changed);
            outcome.disclosure = Some(DisclosureReport {
                node: session.identity.node_ref(node),
                collapsed: session.collapsed[node] == 1,
            });
            Ok(outcome)
        })
    }

    /// Set a highlight plane (spec §2.2 SetHighlight). Path refs are ordered
    /// nodes whose consecutive pairs must share a composed edge (either
    /// direction); that edge, lowest index first, joins the highlight.
    /// Community refs gain their induced edges. External refs are as given.
    pub fn set_highlight(
        &mut self,
        header: OpHeader,
        plane: HighlightPlane,
        refs: &[ElementRef],
        mode: SelectMode,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session, world| {
            let mut delta = session.resolve_all(refs)?;
            match plane {
                HighlightPlane::Path => session.path_edges(refs, &mut delta)?,
                HighlightPlane::Community => session.induced_edges(&mut delta),
                HighlightPlane::External => {}
            }
            let changed = world.state.highlight(plane, mode, &delta)?;
            let mut outcome = session.outcome(world, !changed.is_empty());
            outcome.changed = session.identity.refs_of(&changed);
            Ok(outcome)
        })
    }

    fn path_edges(
        &mut self,
        refs: &[ElementRef],
        delta: &mut ElementSet,
    ) -> Result<(), InteractionStatus> {
        let mut nodes = Vec::with_capacity(refs.len());
        for element in refs {
            nodes.push(self.node_target(element)? as u64);
        }
        let mut found: HashMap<(u64, u64), Option<usize>> = nodes
            .windows(2)
            .flat_map(|pair| [(pair[0], pair[1]), (pair[1], pair[0])])
            .map(|key| (key, None))
            .collect();
        for edge in 0..self.edge_source.len() {
            if let Some(slot) = found.get_mut(&(self.edge_source[edge], self.edge_target[edge])) {
                slot.get_or_insert(edge);
            }
        }
        self.work += (self.edge_source.len() + nodes.len()) as u64;
        for pair in nodes.windows(2) {
            let forward = found[&(pair[0], pair[1])];
            let backward = found[&(pair[1], pair[0])];
            let edge = match (forward, backward) {
                (Some(a), Some(b)) => a.min(b),
                (Some(a), None) | (None, Some(a)) => a,
                (None, None) => return Err(InteractionStatus::Invalid),
            };
            self.identity.insert_into(delta, ElementIndex::Edge(edge));
        }
        Ok(())
    }

    fn induced_edges(&mut self, delta: &mut ElementSet) {
        let members: Vec<usize> = delta
            .nodes
            .iter()
            .filter_map(|id| self.identity.node_index(id))
            .collect();
        let mut inside = vec![false; self.identity.node_count()];
        for &node in &members {
            inside[node] = true;
        }
        for edge in 0..self.edge_source.len() {
            if inside[self.edge_source[edge] as usize] && inside[self.edge_target[edge] as usize] {
                self.identity.insert_into(delta, ElementIndex::Edge(edge));
            }
        }
        self.work += (self.edge_source.len() + members.len()) as u64;
    }
}
