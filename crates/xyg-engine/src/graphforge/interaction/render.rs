//! Render publication (#36 §2.3, F2, F4): the one `RenderOutput` a session
//! publishes to painters and, in S3, to the pick index.
//!
//! Pipeline, in source index space until the last step:
//! 1. temporal visibility (F4) masks source nodes and edges, read from the
//!    bound temporal graph under the same lock as the shared state, *and* the
//!    hierarchy itself: an invisible node leaves the forest and its children
//!    re-attach to the nearest surviving ancestor;
//! 2. [`compound_collapse`] over that surviving hierarchy gives visibility,
//!    representatives, and rerouted endpoints with edge provenance;
//! 3. [`build_render`] culls and applies LOD over the collapsed source graph;
//! 4. membership composes source node -> representative -> render node and
//!    render edge -> source edges.

use std::borrow::Cow;

use super::{GraphSession, InteractionStatus, OpHeader, OpOutcome, World};
use crate::graph::{build_render, LodTier, Viewport, COSE_NO_PARENT};
use crate::graph_interaction_state::{
    ElementSet, Focus, GraphEntity, GraphInteractionState, HighlightPlane,
};
use crate::graph_style::{
    compound_collapse, resolve_visual_state, CompoundCollapse, EMPHASIS_MASK, EMPHASIS_SHIFT,
    FLAG_AGGREGATE, FLAG_COMMUNITY, FLAG_EXTERNAL, FLAG_FOCUSED, FLAG_HOVERED, FLAG_NEIGHBOR,
    FLAG_PATH, FLAG_PINNED, FLAG_SELECTED,
};

use super::super::compose::nearest_visible_ancestors;
use super::super::identity::{AggregateRef, ElementIndex, ElementRef, ResolveError};

/// Sentinel for "not in the render set" in every membership map.
pub const NOT_RENDERED: u64 = u64::MAX;

/// Screen mapping of one render: `screen = data * scale + offset` in CSS px.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Camera {
    pub scale_x: f64,
    pub scale_y: f64,
    pub offset_x: f64,
    pub offset_y: f64,
    pub viewport_width: f64,
    pub viewport_height: f64,
    pub dpr: f64,
}

impl Camera {
    fn validate(&self) -> Result<(), InteractionStatus> {
        let finite = [
            self.scale_x,
            self.scale_y,
            self.offset_x,
            self.offset_y,
            self.viewport_width,
            self.viewport_height,
            self.dpr,
        ]
        .iter()
        .all(|v| v.is_finite());
        if finite
            && self.scale_x != 0.0
            && self.scale_y != 0.0
            && self.viewport_width > 0.0
            && self.viewport_height > 0.0
            && self.dpr > 0.0
        {
            Ok(())
        } else {
            Err(InteractionStatus::Invalid)
        }
    }

    /// The data-space rectangle the viewport shows.
    fn viewport(&self) -> Viewport {
        Viewport {
            x0: (0.0 - self.offset_x) / self.scale_x,
            y0: (0.0 - self.offset_y) / self.scale_y,
            x1: (self.viewport_width - self.offset_x) / self.scale_x,
            y1: (self.viewport_height - self.offset_y) / self.scale_y,
        }
    }

    /// Screen delta (CSS px) as a data delta.
    pub(super) fn data_delta(&self, dx: f64, dy: f64) -> (f64, f64) {
        (dx / self.scale_x, dy / self.scale_y)
    }
}

/// Everything a painter (and the S3 pick index) reads for one revision.
#[derive(Clone, Debug, PartialEq)]
pub struct RenderOutput {
    pub revision: u32,
    pub tier: LodTier,
    pub edges_kept: u64,
    pub node_x: Vec<f64>,
    pub node_y: Vec<f64>,
    /// Render node of every source node (`NOT_RENDERED` if hidden, culled, or
    /// temporally invisible). Hidden members of a collapsed compound map to
    /// their representative's render node.
    pub member_of: Vec<u64>,
    pub edge_source: Vec<u64>,
    pub edge_target: Vec<u64>,
    /// CSR: render edge `r` represents `edge_members[offsets[r]..offsets[r+1]]`
    /// (ascending source edge indices).
    pub edge_member_offsets: Vec<u64>,
    pub edge_members: Vec<u64>,
    pub visual_states: Vec<u8>,
    pub emphasis: Vec<u8>,
    pub edge_visual_states: Vec<u8>,
    pub edge_emphasis: Vec<u8>,
    /// CSR: render node -> member source nodes, ascending.
    pub node_member_offsets: Vec<u64>,
    pub node_members: Vec<u64>,
    /// Lowest-index source node that is itself visible, per render node: the
    /// stand-in a keyboard focus lands on.
    pub focus_node: Vec<u64>,
    /// Render edge of every source edge (`NOT_RENDERED` if not drawn).
    pub edge_render: Vec<u64>,
}

impl RenderOutput {
    pub fn node_count(&self) -> usize {
        self.node_x.len()
    }

    pub fn edge_count(&self) -> usize {
        self.edge_source.len()
    }

    pub fn members_of_node(&self, render: usize) -> &[u64] {
        let (lo, hi) = (
            self.node_member_offsets[render] as usize,
            self.node_member_offsets[render + 1] as usize,
        );
        &self.node_members[lo..hi]
    }

    pub fn members_of_edge(&self, render: usize) -> &[u64] {
        let (lo, hi) = (
            self.edge_member_offsets[render] as usize,
            self.edge_member_offsets[render + 1] as usize,
        );
        &self.edge_members[lo..hi]
    }
}

/// Source node and edge visibility under one temporal snapshot (F4); `1` is
/// visible. An edge is invisible when its own temporal validity, or either
/// endpoint, is.
pub(super) struct Visible {
    pub node: Vec<u8>,
    pub edge: Vec<u8>,
}

/// The parent forest and collapse plane after temporal masking.
pub(super) struct Hierarchy<'a> {
    pub parent: Cow<'a, [u64]>,
    pub valid: Cow<'a, [u8]>,
    pub collapsed: Cow<'a, [u8]>,
    /// Work units spent resolving surviving ancestors.
    pub work: u64,
}

/// State a render reads, collected under the same lock as its visibility.
struct Inputs {
    node_flags: Vec<u32>,
    edge_flags: Vec<u32>,
}

/// A reference resolved against the current publication.
pub(super) enum Resolved {
    Element(ElementIndex),
    /// A render node of the current publication standing for several source
    /// nodes (an aggregate, or a collapsed group with its hidden members).
    Group {
        render: usize,
    },
}

impl GraphSession {
    /// The latest publication, if it is still current (no revision bump since).
    pub fn published(&self) -> Option<&RenderOutput> {
        self.published
            .as_ref()
            .filter(|_| self.published_revision == self.render_revision)
    }

    /// Resolve a reference, aggregates against the current publication.
    pub(super) fn resolve(&self, element: &ElementRef) -> Result<Resolved, InteractionStatus> {
        match element {
            ElementRef::Aggregate(AggregateRef {
                render_revision,
                index,
            }) => {
                let render = self.published().ok_or(InteractionStatus::Stale)?;
                if *render_revision != render.revision {
                    return Err(InteractionStatus::Stale);
                }
                let index = *index as usize;
                if index >= render.node_count() {
                    return Err(InteractionStatus::Invalid);
                }
                Ok(Resolved::Group { render: index })
            }
            other => match self.identity.resolve(other) {
                Ok(index) => Ok(Resolved::Element(index)),
                Err(ResolveError::Unresolved | ResolveError::NeedsRender) => {
                    Err(InteractionStatus::Invalid)
                }
            },
        }
    }

    /// Source visibility under the snapshot the caller holds locked.
    pub(super) fn visible(
        &mut self,
        visibility: Option<(&[u8], &[u8])>,
    ) -> Result<Visible, InteractionStatus> {
        let (n, e) = (self.identity.node_count(), self.identity.edge_count());
        let mut node = vec![1u8; n];
        let mut edge = vec![1u8; e];
        if let Some((nodes, edges)) = visibility {
            if nodes.len() != n {
                return Err(InteractionStatus::Invalid);
            }
            node.copy_from_slice(nodes);
            for (index, &ordinal) in self.edge_ordinal.iter().enumerate() {
                if ordinal != u32::MAX {
                    edge[index] = *edges
                        .get(ordinal as usize)
                        .ok_or(InteractionStatus::Invalid)?;
                }
            }
        }
        for index in 0..e {
            let (s, t) = (
                self.edge_source[index] as usize,
                self.edge_target[index] as usize,
            );
            edge[index] &= node[s] & node[t];
        }
        self.work += (n + e) as u64;
        Ok(Visible { node, edge })
    }

    /// The hierarchy the temporal snapshot leaves (F2 step 1): `(parent,
    /// valid, collapsed)` per source node. An invisible node leaves the forest
    /// with its collapsed flag, and its children re-attach to the nearest
    /// surviving ancestor, so an expired group never hides or reroutes live
    /// members.
    pub(super) fn surviving_hierarchy(&self, node_visible: &[u8]) -> Hierarchy<'_> {
        if node_visible.iter().all(|&v| v == 1) {
            return Hierarchy {
                parent: Cow::Borrowed(&self.parent[..]),
                valid: Cow::Borrowed(&self.parent_valid[..]),
                collapsed: Cow::Borrowed(&self.collapsed[..]),
                work: 0,
            };
        }
        let visible: Vec<bool> = node_visible.iter().map(|&v| v == 1).collect();
        let (ancestor, links) = nearest_visible_ancestors(&self.parent, &visible);
        let parent: Vec<u64> = (0..visible.len())
            .map(|i| {
                if visible[i] {
                    ancestor[i]
                } else {
                    COSE_NO_PARENT
                }
            })
            .collect();
        let valid = parent
            .iter()
            .map(|&p| u8::from(p != COSE_NO_PARENT))
            .collect();
        let collapsed = (0..visible.len())
            .map(|i| if visible[i] { self.collapsed[i] } else { 0 })
            .collect();
        Hierarchy {
            parent: Cow::Owned(parent),
            valid: Cow::Owned(valid),
            collapsed: Cow::Owned(collapsed),
            work: links + visible.len() as u64,
        }
    }

    /// Publish the render for the current state. The revision advances when a
    /// structural change (pin, move, relayout, disclosure, temporal frame) did,
    /// or when the camera of the previous publication differs; otherwise the
    /// same revision is republished with fresh style planes. The temporal
    /// revision, visibility, and shared state are one locked snapshot.
    pub fn render(&mut self, camera: Option<Camera>) -> Result<&RenderOutput, InteractionStatus> {
        if let Some(camera) = &camera {
            camera.validate()?;
        }
        self.locked(|session, world| session.publish(camera, world))??;
        self.published.as_ref().ok_or(InteractionStatus::Invalid)
    }

    fn publish(
        &mut self,
        camera: Option<Camera>,
        world: World<'_>,
    ) -> Result<(), InteractionStatus> {
        self.sync_world(&world)?;
        let advance = self.render_revision == self.published_revision
            && (self.published.is_none() || camera != self.camera);
        if advance {
            self.reserve_revision()?;
        }
        let vis = self.visible(world.visibility)?;
        self.ensure_positions(&vis)?;
        let revision = if advance {
            self.render_revision + 1
        } else {
            self.render_revision
        };
        let output = self.build_output(camera, revision, world.state, &vis)?;
        if advance {
            self.bump();
        }
        self.camera = camera;
        self.published_revision = self.render_revision;
        self.published = Some(output);
        Ok(())
    }

    fn collect_inputs(&mut self, state: &GraphInteractionState, vis: &Visible) -> Inputs {
        let (n, e) = (self.identity.node_count(), self.identity.edge_count());
        let mut node_flags = vec![0u32; n];
        let mut edge_flags = vec![0u32; e];
        let mark = |set: &ElementSet, flag: u32, nodes: &mut [u32], edges: &mut [u32]| {
            for id in &set.nodes {
                if let Some(i) = self.identity.node_index(id) {
                    nodes[i] |= flag;
                }
            }
            for id in &set.edges {
                if let Some(i) = self.identity.edge_index(id) {
                    edges[i] |= flag;
                }
            }
            for key in &set.derived {
                if let Some(i) = self.identity.resolve_derived_key(key) {
                    edges[i] |= flag;
                }
            }
        };
        mark(
            state.selection(),
            FLAG_SELECTED,
            &mut node_flags,
            &mut edge_flags,
        );
        for (plane, flag) in [
            (HighlightPlane::Path, FLAG_PATH),
            (HighlightPlane::Community, FLAG_COMMUNITY),
            (HighlightPlane::External, FLAG_EXTERNAL),
        ] {
            mark(
                state.highlight_set(plane),
                flag,
                &mut node_flags,
                &mut edge_flags,
            );
        }
        for id in state.pinned_nodes() {
            if let Some(i) = self.identity.node_index(id) {
                node_flags[i] |= FLAG_PINNED;
            }
        }
        match state.focus() {
            Some(Focus::Entity(GraphEntity::Node(id))) => {
                if let Some(i) = self.identity.node_index(id) {
                    node_flags[i] |= FLAG_FOCUSED;
                }
            }
            Some(Focus::Entity(GraphEntity::Edge(id))) => {
                if let Some(i) = self.identity.edge_index(id) {
                    edge_flags[i] |= FLAG_FOCUSED;
                }
            }
            Some(Focus::Derived(key)) => {
                if let Some(i) = self.identity.resolve_derived_key(key) {
                    edge_flags[i] |= FLAG_FOCUSED;
                }
            }
            None => {}
        }
        self.work += (state.selection().len() + state.pinned_nodes().len()) as u64;

        // State of an element that is not visible is not drawn; its identity
        // key survives, so re-entry restores it.
        for (flag, &visible) in node_flags.iter_mut().zip(&vis.node) {
            if visible == 0 {
                *flag = 0;
            }
        }
        for (flag, &visible) in edge_flags.iter_mut().zip(&vis.edge) {
            if visible == 0 {
                *flag = 0;
            }
        }
        Inputs {
            node_flags,
            edge_flags,
        }
    }

    /// Hover follows the drawn topology after temporal masking and collapse.
    /// Resolve representatives anew for each publication, so disclosure never
    /// leaves a previously expanded hover set on unrelated source nodes.
    fn apply_hover(&mut self, inputs: &mut Inputs, collapse: &mut CompoundCollapse, vis: &Visible) {
        if !self.hover.nodes.is_empty() {
            let mut hovered = vec![false; self.identity.node_count()];
            for &node in &self.hover.nodes {
                if vis.node[node] == 1 {
                    let representative = collapse.representative[node];
                    hovered[representative] = true;
                    collapse.flags[representative] |= FLAG_HOVERED;
                }
            }
            for edge in 0..self.edge_source.len() {
                if vis.edge[edge] == 0 || !collapse.edge_keep[edge] {
                    continue;
                }
                let (s, t) = (collapse.edge_source[edge], collapse.edge_target[edge]);
                if hovered[s] && !hovered[t] {
                    collapse.flags[t] |= FLAG_NEIGHBOR;
                } else if hovered[t] && !hovered[s] {
                    collapse.flags[s] |= FLAG_NEIGHBOR;
                }
            }
            self.work += (hovered.len() + self.hover.nodes.len() + self.edge_source.len()) as u64;
        }
        if let Some(edge) = self.hover.edge {
            if vis.edge[edge] == 1 && collapse.edge_keep[edge] {
                inputs.edge_flags[edge] |= FLAG_HOVERED;
            }
        }
    }

    fn build_output(
        &mut self,
        camera: Option<Camera>,
        revision: u32,
        state: &GraphInteractionState,
        vis: &Visible,
    ) -> Result<RenderOutput, InteractionStatus> {
        let (n, e) = (self.identity.node_count(), self.identity.edge_count());
        let mut inputs = self.collect_inputs(state, vis);
        let hierarchy = self.surviving_hierarchy(&vis.node);
        let mut collapse = compound_collapse(
            &hierarchy.parent,
            &hierarchy.valid,
            &hierarchy.collapsed,
            &inputs.node_flags,
            &self.edge_source,
            &self.edge_target,
        )
        .ok_or(InteractionStatus::Invalid)?;
        let mut work = (n + e) as u64 + hierarchy.work;
        drop(hierarchy);
        self.apply_hover(&mut inputs, &mut collapse, vis);

        let (x, y) = self.positions.as_ref().ok_or(InteractionStatus::Invalid)?;
        let active: Vec<bool> = (0..n)
            .map(|s| vis.node[s] == 1 && collapse.visible[s])
            .collect();
        let masked = |plane: &[f64]| -> Vec<f64> {
            plane
                .iter()
                .zip(&active)
                .map(|(&v, &on)| if on { v } else { f64::NAN })
                .collect()
        };
        let (mx, my) = (masked(x), masked(y));
        let kept: Vec<usize> = (0..e)
            .filter(|&i| vis.edge[i] == 1 && collapse.edge_keep[i])
            .collect();
        let ks: Vec<u64> = kept
            .iter()
            .map(|&i| collapse.edge_source[i] as u64)
            .collect();
        let kt: Vec<u64> = kept
            .iter()
            .map(|&i| collapse.edge_target[i] as u64)
            .collect();
        work += (n + e + kept.len()) as u64;

        let (node_budget, edge_budget) = (self.budgets.0.max(1), self.budgets.1.max(1));
        let node_cap = node_budget.min(n as u64) as usize;
        let edge_cap = edge_budget.min(kept.len() as u64) as usize;
        let mut out_x = vec![0.0f64; node_cap];
        let mut out_y = vec![0.0f64; node_cap];
        let mut built_member = vec![NOT_RENDERED; n];
        let mut out_s = vec![0u64; edge_cap];
        let mut out_t = vec![0u64; edge_cap];
        let (mut out_nodes, mut out_edges) = (0u64, 0u64);
        let mut offsets = vec![0u64; edge_cap + 1];
        let mut members = vec![0u64; kept.len()];
        let decision = build_render(
            n as u64,
            &mx,
            &my,
            &ks,
            &kt,
            node_budget,
            edge_budget,
            camera.as_ref().map(Camera::viewport),
            &mut out_x,
            &mut out_y,
            &mut built_member,
            &mut out_s,
            &mut out_t,
            &mut out_nodes,
            &mut out_edges,
            Some((&mut offsets, &mut members)),
        )
        .ok_or(InteractionStatus::Invalid)?;
        let (rn, re) = (out_nodes as usize, out_edges as usize);
        out_x.truncate(rn);
        out_y.truncate(rn);
        out_s.truncate(re);
        out_t.truncate(re);
        offsets.truncate(re + 1);
        members.truncate(offsets[re] as usize);
        // Render-edge members back to composed (source) edge indices.
        for member in &mut members {
            *member = kept[*member as usize] as u64;
        }
        work += (rn + re + members.len()) as u64;

        // Source node -> representative -> render node. A temporally invisible
        // node is in no render node; a node hidden by a collapsed group rides
        // that group's render node (membership is not source visibility).
        let member_of: Vec<u64> = (0..n)
            .map(|s| {
                if vis.node[s] == 0 {
                    NOT_RENDERED
                } else {
                    built_member[collapse.representative[s]]
                }
            })
            .collect();

        let mut node_flags = vec![0u32; rn];
        let mut node_counts = vec![0u32; rn];
        let mut focus_node = vec![NOT_RENDERED; rn];
        for s in 0..n {
            let render = built_member[s];
            if active[s] && render != NOT_RENDERED {
                let r = render as usize;
                node_flags[r] |= collapse.flags[s];
                node_counts[r] += 1;
                if focus_node[r] == NOT_RENDERED {
                    focus_node[r] = s as u64;
                }
            }
        }
        for (flag, &count) in node_flags.iter_mut().zip(&node_counts) {
            if count > 1 {
                *flag |= FLAG_AGGREGATE;
            }
        }

        let mut edge_flags = vec![0u32; re];
        let mut edge_render = vec![NOT_RENDERED; e];
        for r in 0..re {
            let (lo, hi) = (offsets[r] as usize, offsets[r + 1] as usize);
            for &edge in &members[lo..hi] {
                edge_flags[r] |= inputs.edge_flags[edge as usize];
                edge_render[edge as usize] = r as u64;
            }
            if hi - lo > 1 {
                edge_flags[r] |= FLAG_AGGREGATE;
            }
        }

        // Render node -> member source nodes (counting sort, ascending).
        let mut node_member_offsets = vec![0u64; rn + 1];
        for &render in &member_of {
            if render != NOT_RENDERED {
                node_member_offsets[render as usize + 1] += 1;
            }
        }
        for r in 0..rn {
            node_member_offsets[r + 1] += node_member_offsets[r];
        }
        let mut cursor = node_member_offsets[..rn].to_vec();
        let mut node_members = vec![0u64; node_member_offsets[rn] as usize];
        for (s, &render) in member_of.iter().enumerate() {
            if render != NOT_RENDERED {
                let at = &mut cursor[render as usize];
                node_members[*at as usize] = s as u64;
                *at += 1;
            }
        }
        work += (n + rn) as u64;
        self.work += work;

        let states = |flags: &[u32]| -> (Vec<u8>, Vec<u8>) {
            (
                flags.iter().map(|&f| resolve_visual_state(f)).collect(),
                flags
                    .iter()
                    .map(|&f| ((f >> EMPHASIS_SHIFT) & EMPHASIS_MASK) as u8)
                    .collect(),
            )
        };
        let (visual_states, emphasis) = states(&node_flags);
        let (edge_visual_states, edge_emphasis) = states(&edge_flags);
        Ok(RenderOutput {
            revision,
            tier: decision.tier,
            edges_kept: decision.edges_kept,
            node_x: out_x,
            node_y: out_y,
            member_of,
            edge_source: out_s,
            edge_target: out_t,
            edge_member_offsets: offsets,
            edge_members: members,
            visual_states,
            emphasis,
            edge_visual_states,
            edge_emphasis,
            node_member_offsets,
            node_members,
            focus_node,
            edge_render,
        })
    }

    /// Hover emphasis: HOVERED on the target (every member of an aggregate),
    /// NEIGHBOR one visible edge away. `None` clears it. Transient: never
    /// part of the shared interaction state, never bumps the revision.
    pub fn hover(
        &mut self,
        header: OpHeader,
        target: Option<&ElementRef>,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session, world| {
            let mut next = super::Hover::default();
            match target {
                None => {}
                Some(element) => match session.resolve(element)? {
                    Resolved::Element(ElementIndex::Node(node)) => next.nodes.push(node),
                    Resolved::Element(ElementIndex::Edge(edge)) => next.edge = Some(edge),
                    Resolved::Group { render } => {
                        let published = session.published().ok_or(InteractionStatus::Stale)?;
                        next.nodes = published
                            .members_of_node(render)
                            .iter()
                            .map(|&s| s as usize)
                            .collect();
                    }
                },
            }
            let changed = session.hover != next;
            session.work += next.nodes.len() as u64;
            session.hover = next;
            Ok(session.outcome(world, changed))
        })
    }
}
