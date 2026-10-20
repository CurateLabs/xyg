//! Positions and structural operations (#36 §2.5, §2.6): pin, move, relayout,
//! compound disclosure, and highlight planes.
//!
//! Every successful structural change advances the render revision, so a host
//! holding the previous publication is rejected as stale and repaints. A failed
//! operation changes nothing: inputs are validated before the first write.

use std::collections::HashMap;

use super::render::Resolved;
use super::{GraphSession, InteractionStatus, OpHeader, OpOutcome};
use crate::graph::{CoseOptions, ForceState, LAYOUT_COSE};
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

impl GraphSession {
    /// Lay the graph out from the deterministic seed when the document and
    /// load authored no positions (CoSE with the document hierarchy).
    pub(super) fn ensure_positions(&mut self) -> Result<(), InteractionStatus> {
        if self.positions.is_some() {
            return Ok(());
        }
        let n = self.identity.node_count();
        let mut layout = ForceState::new_configured(
            n as u64,
            &self.edge_source,
            &self.edge_target,
            None,
            None,
            self.seed,
            LAYOUT_COSE,
            CoseOptions::default(),
            &[],
            &self.parent,
        )
        .ok_or(InteractionStatus::Invalid)?;
        layout.tick(INITIAL_LAYOUT_STEPS);
        self.work += u64::from(INITIAL_LAYOUT_STEPS) * (n + self.edge_source.len()) as u64;
        if !layout.alpha.is_finite() || layout.x.iter().chain(&layout.y).any(|v| !v.is_finite()) {
            return Err(InteractionStatus::Invalid);
        }
        self.positions = Some((layout.x, layout.y));
        Ok(())
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
    /// old positions and pins) and the render.
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
        self.operate(header, |session| {
            let node = session.node_target(target)?;
            session.ensure_positions()?;
            let id = session.identity.node_uuids()[node];
            let changed = session.write_state(|state| state.set_pin(id, on))?;
            if changed {
                session.positions_changed();
            }
            let mut outcome = session.outcome(changed)?;
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
        self.operate(header, |session| {
            let node = session.node_target(target)?;
            session.ensure_positions()?;
            if let Some(origin) = session.move_origin {
                if origin.node != node {
                    return Err(InteractionStatus::Invalid);
                }
            }
            let (x, y) = {
                let (x, y) = session
                    .positions
                    .as_ref()
                    .ok_or(InteractionStatus::Invalid)?;
                (x[node], y[node])
            };
            let (next, origin) = match commit {
                MoveCommit::Cancel => {
                    let origin = session.move_origin.ok_or(InteractionStatus::Invalid)?;
                    ((origin.x, origin.y), None)
                }
                MoveCommit::Preview | MoveCommit::Commit => {
                    let (dx, dy) = match space {
                        MoveSpace::Data => delta,
                        MoveSpace::ScreenDelta => session
                            .camera
                            .ok_or(InteractionStatus::Invalid)?
                            .data_delta(delta.0, delta.1),
                    };
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
            let id = session.identity.node_uuids()[node];
            let pin = commit == MoveCommit::Commit;
            if pin {
                session.write_state(|state| state.set_pin(id, true))?;
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
            let mut outcome = session.outcome(true)?;
            if pin {
                outcome.positions = vec![session.node_position(node, true)];
            }
            Ok(outcome)
        })
    }

    /// Step the CoSE relayout, seeded from the current positions with pinned
    /// nodes held bit-exact. Always CoSE regardless of the composition's
    /// original layout: it is the one engine honoring pins and parents.
    pub fn relayout_step(
        &mut self,
        header: OpHeader,
        steps: u32,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session| {
            if steps == 0 || steps > MAX_RELAYOUT_STEPS {
                return Err(InteractionStatus::Invalid);
            }
            let (n, e) = (session.identity.node_count(), session.edge_source.len());
            if u64::from(steps) * (n + e) as u64 > MAX_GRAPH_INTERACTION_WORK {
                return Err(InteractionStatus::Budget);
            }
            session.ensure_positions()?;
            if session.relayout.is_none() {
                let mut mask = vec![0u8; n];
                session.read_state(|state| {
                    for id in state.pinned_nodes() {
                        if let Some(i) = session.identity.node_index(id) {
                            mask[i] = 1;
                        }
                    }
                })?;
                let (x, y) = session
                    .positions
                    .as_ref()
                    .ok_or(InteractionStatus::Invalid)?;
                session.relayout = Some(
                    ForceState::new_configured(
                        n as u64,
                        &session.edge_source,
                        &session.edge_target,
                        Some(x),
                        Some(y),
                        session.seed,
                        LAYOUT_COSE,
                        CoseOptions::default(),
                        &mask,
                        &session.parent,
                    )
                    .ok_or(InteractionStatus::Invalid)?,
                );
            }
            let layout = session
                .relayout
                .as_mut()
                .ok_or(InteractionStatus::Invalid)?;
            layout.tick(steps);
            session.work += u64::from(steps) * (n + e) as u64;
            if !layout.alpha.is_finite() || layout.x.iter().chain(&layout.y).any(|v| !v.is_finite())
            {
                session.relayout = None;
                return Err(InteractionStatus::Invalid);
            }
            let alpha = layout.alpha;
            session.positions = Some((layout.x.clone(), layout.y.clone()));
            session.bump();
            let mut outcome = session.outcome(true)?;
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
        self.operate(header, |session| {
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
                session.collapsed = next;
                session.bump();
            }
            let mut outcome = session.outcome(changed)?;
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
        self.operate(header, |session| {
            let mut delta = session.resolve_all(refs)?;
            match plane {
                HighlightPlane::Path => session.path_edges(refs, &mut delta)?,
                HighlightPlane::Community => session.induced_edges(&mut delta),
                HighlightPlane::External => {}
            }
            let changed = session.write_state(|state| state.highlight(plane, mode, &delta))??;
            let mut outcome = session.outcome(!changed.is_empty())?;
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
