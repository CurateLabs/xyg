//! The one UUID-keyed graph interaction state (#36, spec/design/graph-interaction.md §1.1).
//!
//! Selection, focus, pins, and the three emphasis highlight planes live in a
//! single [`GraphInteractionState`] value. [`TemporalGraph`] owns one directly;
//! a [`GraphSession`] either owns one or is *bound* to the temporal graph's, so
//! two owners can never diverge: there is one value, reachable from both.
//!
//! State is keyed by opaque UUID (persisted nodes and edges) or by the exact
//! [`DerivedKey`] of a derived edge, never by frame or render position, so
//! hiding an element does not destroy its identity state. The selection is
//! bounded: every mutator computes the would-be size first and rejects the
//! whole operation with [`SelectionTooLarge`], leaving the state unchanged.
//!
//! [`TemporalGraph`]: crate::temporal_graph::TemporalGraph
//! [`GraphSession`]: crate::graphforge::interaction::GraphSession

use std::collections::BTreeSet;

use crate::projection::Uuid;

/// Hard bound on `|nodes| + |edges| + |derived|` of one selection or one
/// highlight plane. Equal to the coordination snapshot bound so a selection
/// that fits the state always fits a linked-view event.
pub const MAX_GRAPH_SELECTION_REFS: usize =
    crate::temporal_controller::MAX_COORDINATED_SELECTION_IDS;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum GraphEntity {
    Node(Uuid),
    Edge(Uuid),
}

/// Identity of a derived edge (NIL UUID in the composed document): the exact
/// result id of its layer plus `(layer, path, order)`. For ordered overlays
/// `path` is the overlay index and `order` the step; for derived pairs `path`
/// is `u64::MAX` and `order` is the layer's result row. The result id is held
/// as the exact string: a layer whose id changed no longer matches the key.
#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct DerivedKey {
    pub result_id: Option<Box<str>>,
    pub layer: u32,
    pub path: u64,
    pub order: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Focus {
    Entity(GraphEntity),
    Derived(DerivedKey),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SelectMode {
    Replace,
    Add,
    Toggle,
}

/// Independent emphasis planes that never compete in the §7.1 visual-state
/// precedence (spec/design/graph-interaction.md §2.7).
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HighlightPlane {
    Path = 0,
    Community = 1,
    External = 2,
}

/// A set of element identities: the shape of a selection or a highlight plane.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct ElementSet {
    pub nodes: BTreeSet<Uuid>,
    pub edges: BTreeSet<Uuid>,
    pub derived: BTreeSet<DerivedKey>,
}

impl ElementSet {
    pub fn len(&self) -> usize {
        self.nodes.len() + self.edges.len() + self.derived.len()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Elements in exactly one of `self` and `other`.
    fn symmetric_difference(&self, other: &Self) -> Self {
        Self {
            nodes: self
                .nodes
                .symmetric_difference(&other.nodes)
                .copied()
                .collect(),
            edges: self
                .edges
                .symmetric_difference(&other.edges)
                .copied()
                .collect(),
            derived: self
                .derived
                .symmetric_difference(&other.derived)
                .cloned()
                .collect(),
        }
    }

    /// Combine `delta` into `self` under `mode`.
    fn combined(&self, mode: SelectMode, delta: &Self) -> Self {
        match mode {
            SelectMode::Replace => delta.clone(),
            SelectMode::Add => Self {
                nodes: self.nodes.union(&delta.nodes).copied().collect(),
                edges: self.edges.union(&delta.edges).copied().collect(),
                derived: self.derived.union(&delta.derived).cloned().collect(),
            },
            SelectMode::Toggle => self.symmetric_difference(delta),
        }
    }
}

/// The would-be set exceeded [`MAX_GRAPH_SELECTION_REFS`]; nothing changed.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SelectionTooLarge {
    pub requested: usize,
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct GraphInteractionState {
    selection: ElementSet,
    highlights: [ElementSet; 3],
    focus: Option<Focus>,
    pinned: BTreeSet<Uuid>,
}

impl GraphInteractionState {
    pub fn selection(&self) -> &ElementSet {
        &self.selection
    }

    pub fn highlight_set(&self, plane: HighlightPlane) -> &ElementSet {
        &self.highlights[plane as usize]
    }

    pub fn focus(&self) -> Option<&Focus> {
        self.focus.as_ref()
    }

    /// Focus as a persisted entity; a derived-edge focus has no temporal
    /// counterpart and reads as `None`.
    pub fn focused_entity(&self) -> Option<GraphEntity> {
        match self.focus {
            Some(Focus::Entity(entity)) => Some(entity),
            _ => None,
        }
    }

    pub fn pinned_nodes(&self) -> &BTreeSet<Uuid> {
        &self.pinned
    }

    /// Apply `delta` to the selection. Returns the elements whose membership
    /// changed. Atomic: over the bound, the state is untouched.
    pub fn select(
        &mut self,
        mode: SelectMode,
        delta: &ElementSet,
    ) -> Result<ElementSet, SelectionTooLarge> {
        Self::apply(&mut self.selection, mode, delta)
    }

    /// Apply `delta` to one highlight plane (each plane is bounded separately).
    pub fn highlight(
        &mut self,
        plane: HighlightPlane,
        mode: SelectMode,
        delta: &ElementSet,
    ) -> Result<ElementSet, SelectionTooLarge> {
        Self::apply(&mut self.highlights[plane as usize], mode, delta)
    }

    fn apply(
        target: &mut ElementSet,
        mode: SelectMode,
        delta: &ElementSet,
    ) -> Result<ElementSet, SelectionTooLarge> {
        let next = target.combined(mode, delta);
        if next.len() > MAX_GRAPH_SELECTION_REFS {
            return Err(SelectionTooLarge {
                requested: next.len(),
            });
        }
        let changed = target.symmetric_difference(&next);
        *target = next;
        Ok(changed)
    }

    pub fn set_focus(&mut self, focus: Option<Focus>) {
        self.focus = focus;
    }

    pub fn set_pinned(&mut self, pinned: BTreeSet<Uuid>) {
        self.pinned = pinned;
    }

    /// Pin or unpin one node. Returns whether the pin set changed.
    pub fn set_pin(&mut self, node: Uuid, on: bool) -> bool {
        if on {
            self.pinned.insert(node)
        } else {
            self.pinned.remove(&node)
        }
    }

    /// Empty the selection and every highlight plane; focus and pins stay.
    /// Returns whether anything was cleared (hosts propagate Escape only then).
    pub fn clear(&mut self) -> bool {
        let had = !self.selection.is_empty() || self.highlights.iter().any(|set| !set.is_empty());
        self.selection = ElementSet::default();
        self.highlights = Default::default();
        had
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn id(value: u32) -> Uuid {
        let mut out = [0u8; 16];
        out[..4].copy_from_slice(&(value + 1).to_le_bytes());
        out
    }

    fn nodes(range: std::ops::Range<u32>) -> ElementSet {
        ElementSet {
            nodes: range.map(id).collect(),
            ..Default::default()
        }
    }

    #[test]
    fn selection_cap_rejects_atomically_in_every_mode() {
        let mut state = GraphInteractionState::default();
        state
            .select(
                SelectMode::Replace,
                &nodes(0..MAX_GRAPH_SELECTION_REFS as u32),
            )
            .unwrap();
        let before = state.clone();
        // One more node over the cap, in each mode that grows the set.
        let over = nodes(MAX_GRAPH_SELECTION_REFS as u32..MAX_GRAPH_SELECTION_REFS as u32 + 1);
        for mode in [SelectMode::Add, SelectMode::Toggle] {
            assert_eq!(
                state.select(mode, &over),
                Err(SelectionTooLarge {
                    requested: MAX_GRAPH_SELECTION_REFS + 1
                })
            );
            assert_eq!(state, before, "{mode:?} must leave the state unchanged");
        }
        assert_eq!(
            state.select(
                SelectMode::Replace,
                &nodes(0..MAX_GRAPH_SELECTION_REFS as u32 + 1)
            ),
            Err(SelectionTooLarge {
                requested: MAX_GRAPH_SELECTION_REFS + 1
            })
        );
        assert_eq!(state, before);
    }

    #[test]
    fn cap_counts_nodes_edges_and_derived_together_per_plane() {
        let mut state = GraphInteractionState::default();
        let mut mixed = nodes(0..MAX_GRAPH_SELECTION_REFS as u32 - 2);
        mixed.edges.insert(id(0));
        state.select(SelectMode::Replace, &mixed).unwrap();
        let one_derived = ElementSet {
            derived: [DerivedKey {
                result_id: None,
                layer: 0,
                path: 0,
                order: 0,
            }]
            .into(),
            ..Default::default()
        };
        // Exactly at the cap is accepted; one more kind-mixed element is not.
        state.select(SelectMode::Add, &one_derived).unwrap();
        assert_eq!(state.selection().len(), MAX_GRAPH_SELECTION_REFS);
        let extra = ElementSet {
            edges: [id(1)].into(),
            ..Default::default()
        };
        assert!(state.select(SelectMode::Add, &extra).is_err());
        // A full selection does not consume a highlight plane's budget.
        state
            .highlight(HighlightPlane::Path, SelectMode::Replace, &nodes(0..10))
            .unwrap();
        assert_eq!(state.highlight_set(HighlightPlane::Path).len(), 10);
    }

    #[test]
    fn toggle_reports_the_symmetric_difference_and_clear_keeps_focus() {
        let mut state = GraphInteractionState::default();
        state.select(SelectMode::Replace, &nodes(0..3)).unwrap();
        let changed = state.select(SelectMode::Toggle, &nodes(2..5)).unwrap();
        assert_eq!(changed.nodes, [id(2), id(3), id(4)].into());
        assert_eq!(state.selection().nodes, [id(0), id(1), id(3), id(4)].into());
        state.set_focus(Some(Focus::Entity(GraphEntity::Node(id(1)))));
        assert!(state.clear());
        assert!(!state.clear(), "second clear has nothing to clear");
        assert_eq!(state.focused_entity(), Some(GraphEntity::Node(id(1))));
    }
}
