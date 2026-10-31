//! Keyboard walks over the published render (#36 §5): FocusStep and FocusRing.
//!
//! Both walk render space, so an aggregate is one stop and a collapsed
//! compound is one stop. Focus is UUID-keyed state, so an aggregate stop
//! focuses its lowest-index visible member (`RenderOutput::focus_node`) and a
//! rendered aggregate edge its lowest-index member edge.

use std::collections::BTreeSet;

use super::render::{RenderOutput, NOT_RENDERED};
use super::{GraphSession, InteractionStatus, OpHeader, OpOutcome, World};
use crate::graph_interaction_state::{ElementSet, Focus, GraphEntity, MAX_GRAPH_SELECTION_REFS};
use crate::graphforge::identity::ElementIndex;

/// One stop of a focus ring, in render indices.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum Stop {
    Node(u64),
    Edge(u64),
}

impl GraphSession {
    /// Walks need the render the host is looking at.
    fn current_render(&self) -> Result<&RenderOutput, InteractionStatus> {
        self.published().ok_or(InteractionStatus::Stale)
    }

    /// The render stop a focus sits on, if it is drawn.
    pub(super) fn stop_of(&self, render: &RenderOutput, focus: Option<&Focus>) -> Option<Stop> {
        let index = match focus {
            Some(Focus::Entity(GraphEntity::Node(id))) => {
                self.identity.node_index(id).map(ElementIndex::Node)
            }
            Some(Focus::Entity(GraphEntity::Edge(id))) => {
                self.identity.edge_index(id).map(ElementIndex::Edge)
            }
            Some(Focus::Derived(key)) => self
                .identity
                .resolve_derived_key(key)
                .map(ElementIndex::Edge),
            None => None,
        };
        match index {
            Some(ElementIndex::Node(node)) => {
                let r = render.member_of[node];
                (r != NOT_RENDERED).then_some(Stop::Node(r))
            }
            Some(ElementIndex::Edge(edge)) => {
                let r = render.edge_render[edge];
                (r != NOT_RENDERED).then_some(Stop::Edge(r))
            }
            None => None,
        }
    }

    /// Everything the focused stop stands for: the member nodes of an
    /// aggregate or collapsed group, the member edges of an aggregate edge.
    /// The size is admitted against the selection cap before it is expanded.
    /// With no current publication, or a focus that is not drawn, it is the
    /// focused element alone.
    pub(super) fn focus_membership(
        &mut self,
        focus: &Focus,
    ) -> Result<ElementSet, InteractionStatus> {
        let mut delta = ElementSet::default();
        let stop = self
            .published()
            .and_then(|render| self.stop_of(render, Some(focus)).map(|stop| (render, stop)));
        let Some((render, stop)) = stop else {
            self.identity.insert_focus(&mut delta, focus);
            return Ok(delta);
        };
        let members = match stop {
            Stop::Node(r) => render.members_of_node(r as usize),
            Stop::Edge(r) => render.members_of_edge(r as usize),
        };
        if members.len() > MAX_GRAPH_SELECTION_REFS {
            return Err(InteractionStatus::SelectionTooLarge);
        }
        for &member in members {
            let element = match stop {
                Stop::Node(_) => ElementIndex::Node(member as usize),
                Stop::Edge(_) => ElementIndex::Edge(member as usize),
            };
            self.identity.insert_into(&mut delta, element);
        }
        let expanded = members.len() as u64;
        self.work += expanded;
        Ok(delta)
    }

    fn stop_focus(&self, render: &RenderOutput, stop: Stop) -> Focus {
        let element = match stop {
            Stop::Node(r) => ElementIndex::Node(render.focus_node[r as usize] as usize),
            Stop::Edge(r) => ElementIndex::Edge(render.members_of_edge(r as usize)[0] as usize),
        };
        self.identity.focus_of(element)
    }

    fn apply_focus(&mut self, world: &mut World<'_>, focus: Focus) -> OpOutcome {
        let changed = world.state.focus() != Some(&focus);
        world.state.set_focus(Some(focus));
        self.outcome(world, changed)
    }

    fn direction(delta: i32) -> Result<i64, InteractionStatus> {
        match delta {
            -1 | 1 => Ok(i64::from(delta)),
            _ => Err(InteractionStatus::Invalid),
        }
    }

    /// Move focus to the next (`+1`) or previous (`-1`) drawn node, wrapping.
    /// With nothing focused, `+1` lands on the first and `-1` on the last.
    pub fn focus_step(
        &mut self,
        header: OpHeader,
        delta: i32,
    ) -> Result<OpOutcome, InteractionStatus> {
        let dir = Self::direction(delta)?;
        self.operate(header, |session, world| {
            let render = session.current_render()?;
            let count = render.node_count() as i64;
            if count == 0 {
                return Err(InteractionStatus::Invalid);
            }
            let from = match session.stop_of(render, world.state.focus()) {
                Some(Stop::Node(r)) => Some(r as i64),
                Some(Stop::Edge(r)) => Some(render.edge_source[r as usize] as i64),
                None => None,
            };
            let next = match from {
                Some(from) => (from + dir).rem_euclid(count),
                None if dir > 0 => 0,
                None => count - 1,
            };
            let focus = session.stop_focus(render, Stop::Node(next as u64));
            session.ring_anchor = None;
            Ok(session.apply_focus(world, focus))
        })
    }

    /// The ring around `anchor`: the node, its out-edges, its in-edges, then
    /// its neighbors, each group ascending in render index.
    pub(super) fn ring(render: &RenderOutput, anchor: u64) -> Vec<Stop> {
        let mut out = Vec::new();
        let mut incoming = Vec::new();
        let mut neighbors = BTreeSet::new();
        for r in 0..render.edge_count() {
            let (s, t) = (render.edge_source[r], render.edge_target[r]);
            if s == anchor {
                out.push(Stop::Edge(r as u64));
                if t != anchor {
                    neighbors.insert(t);
                }
            } else if t == anchor {
                incoming.push(Stop::Edge(r as u64));
                neighbors.insert(s);
            }
        }
        let mut stops = vec![Stop::Node(anchor)];
        stops.extend(out);
        stops.extend(incoming);
        stops.extend(neighbors.into_iter().map(Stop::Node));
        stops
    }

    /// Walk the focus ring (Nodes -> OutEdges -> InEdges -> Neighbors) by
    /// `delta` stops, wrapping. The ring stays anchored on the node it started
    /// from until focus moves by another operation or the render changes.
    pub fn focus_ring(
        &mut self,
        header: OpHeader,
        delta: i32,
    ) -> Result<OpOutcome, InteractionStatus> {
        let dir = Self::direction(delta)?;
        self.operate(header, |session, world| {
            let render = session.current_render()?;
            if render.node_count() == 0 {
                return Err(InteractionStatus::Invalid);
            }
            let current = session.stop_of(render, world.state.focus());
            let kept = session
                .ring_anchor
                .map(|anchor| (anchor, Self::ring(render, anchor)));
            let (anchor, stops) = match (current, kept) {
                (Some(stop), Some((anchor, stops))) if stops.contains(&stop) => (anchor, stops),
                (Some(stop), _) => {
                    let anchor = match stop {
                        Stop::Node(r) => r,
                        Stop::Edge(r) => render.edge_source[r as usize],
                    };
                    (anchor, Self::ring(render, anchor))
                }
                (None, _) => {
                    // Nothing focused: enter the ring at the first/last node.
                    let last = render.node_count() as u64 - 1;
                    let stop = Stop::Node(if dir > 0 { 0 } else { last });
                    let focus = session.stop_focus(render, stop);
                    session.ring_anchor = None;
                    return Ok(session.apply_focus(world, focus));
                }
            };
            let at = current
                .and_then(|stop| stops.iter().position(|&s| s == stop))
                .unwrap_or(0) as i64;
            let next = stops[(at + dir).rem_euclid(stops.len() as i64) as usize];
            let focus = session.stop_focus(render, next);
            let edges = render.edge_count() as u64;
            session.work += edges;
            let outcome = session.apply_focus(world, focus);
            session.ring_anchor = Some(anchor);
            Ok(outcome)
        })
    }
}
