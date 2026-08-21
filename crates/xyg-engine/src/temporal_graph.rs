//! Identity-safe temporal graph filtering (#45).
//!
//! Validity and event predicates are evaluated against the canonical
//! [`GraphProjection`](crate::projection::GraphProjection) order before graph
//! LOD, layout, picking, or styling sees a frame. Persistent interaction state
//! is keyed by opaque UUID, never by frame position, so hiding an entity does
//! not destroy its selection, focus, pin, or provenance identity.

use std::collections::{BTreeSet, HashMap};

use crate::projection::{GraphProjection, Uuid};
use crate::temporal::{
    CancelFlag, IntervalEndpoints, IntervalIndex, TemporalColumn, TemporalError,
};

/// Optional temporal planes for one canonical graph entity table.
#[derive(Clone, Copy, Debug, Default)]
pub struct TemporalBindingInput<'a> {
    /// Half-open validity starts. `None` means every start is unbounded.
    pub valid_from: Option<&'a TemporalColumn>,
    /// Half-open validity ends. `None` means every end is unbounded.
    pub valid_to: Option<&'a TemporalColumn>,
    /// Optional event instants. When present, the event must fall in the
    /// requested frame range in addition to satisfying validity at the cursor.
    pub event_at: Option<&'a TemporalColumn>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum GraphEntity {
    Node(Uuid),
    Edge(Uuid),
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TemporalGraphFrame {
    pub revision: u64,
    pub cursor_micros: i64,
    pub range_start_micros: i64,
    pub range_end_micros: i64,
    pub node_visibility: Vec<u8>,
    pub edge_visibility: Vec<u8>,
    pub visible_node_ids: Vec<Uuid>,
    pub visible_edge_ids: Vec<Uuid>,
    pub selected_visible_node_ids: Vec<Uuid>,
    pub selected_visible_edge_ids: Vec<Uuid>,
    pub focused_visible: Option<GraphEntity>,
    pub pinned_visible_node_ids: Vec<Uuid>,
}

/// Exact temporal and identity membership captured by a static export.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FrozenTemporalGraphState {
    pub revision: u64,
    pub cursor_micros: i64,
    pub range_start_micros: i64,
    pub range_end_micros: i64,
    pub visible_node_ids: Vec<Uuid>,
    pub visible_edge_ids: Vec<Uuid>,
    pub selected_node_ids: Vec<Uuid>,
    pub selected_edge_ids: Vec<Uuid>,
    pub focused: Option<GraphEntity>,
    pub pinned_node_ids: Vec<Uuid>,
}

#[derive(Debug)]
struct EntityBinding {
    validity: IntervalIndex,
    event_at: Option<(Vec<i64>, Vec<u8>)>,
}

impl EntityBinding {
    fn build(len: usize, input: TemporalBindingInput<'_>) -> Result<Self, TemporalError> {
        let zero_values = vec![0_i64; len];
        let zero_validity = vec![0_u8; len];
        let (starts, start_valid) = input
            .valid_from
            .map(|column| (column.values(), column.validity()))
            .unwrap_or((&zero_values, &zero_validity));
        let (ends, end_valid) = input
            .valid_to
            .map(|column| (column.values(), column.validity()))
            .unwrap_or((&zero_values, &zero_validity));
        if starts.len() != len
            || start_valid.len() != len
            || ends.len() != len
            || end_valid.len() != len
        {
            return Err(TemporalError::InvalidArgument);
        }
        let event_at = match input.event_at {
            Some(column) => {
                let values = column.values();
                let validity = column.validity();
                if values.len() != len || validity.len() != len || validity.iter().any(|&v| v > 1) {
                    return Err(TemporalError::InvalidArgument);
                }
                Some((values.to_vec(), validity.to_vec()))
            }
            None => None,
        };
        Ok(Self {
            validity: IntervalIndex::build(IntervalEndpoints {
                starts,
                start_valid,
                ends,
                end_valid,
            })?,
            event_at,
        })
    }

    fn work(&self) -> usize {
        self.validity.len() * (1 + usize::from(self.event_at.is_some()))
    }

    fn visibility(
        &self,
        cursor: i64,
        range_start: i64,
        range_end: i64,
        cancel: &CancelFlag,
        budget: usize,
    ) -> Result<Vec<u8>, TemporalError> {
        let len = self.validity.len();
        let mut visible = vec![0; len];
        self.validity
            .visibility_at(cursor, &mut visible, cancel, budget)?;
        if let Some((events, event_valid)) = &self.event_at {
            let mut event_visible = vec![0; len];
            self.validity.events_in_range(
                events,
                event_valid,
                Some(range_start),
                Some(range_end),
                &mut event_visible,
                cancel,
                budget,
            )?;
            for (valid, event) in visible.iter_mut().zip(event_visible) {
                *valid &= event;
            }
        }
        Ok(visible)
    }
}

/// Rust-owned temporal bindings plus interaction state for one graph instance.
#[derive(Debug)]
pub struct TemporalGraph {
    node_ids: Vec<Uuid>,
    edge_ids: Vec<Uuid>,
    sources: Vec<u64>,
    targets: Vec<u64>,
    node_dense: HashMap<Uuid, usize>,
    edge_dense: HashMap<Uuid, usize>,
    nodes: EntityBinding,
    edges: EntityBinding,
    selected_nodes: BTreeSet<Uuid>,
    selected_edges: BTreeSet<Uuid>,
    focused: Option<GraphEntity>,
    pinned_nodes: BTreeSet<Uuid>,
    applied_revision: u64,
}

impl TemporalGraph {
    pub fn bind(
        projection: &GraphProjection,
        nodes: TemporalBindingInput<'_>,
        edges: TemporalBindingInput<'_>,
    ) -> Result<Self, TemporalError> {
        let node_ids = projection.node_ids().to_vec();
        let edge_ids = projection.edge_ids().to_vec();
        Ok(Self {
            node_dense: node_ids
                .iter()
                .enumerate()
                .map(|(i, &id)| (id, i))
                .collect(),
            edge_dense: edge_ids
                .iter()
                .enumerate()
                .map(|(i, &id)| (id, i))
                .collect(),
            nodes: EntityBinding::build(node_ids.len(), nodes)?,
            edges: EntityBinding::build(edge_ids.len(), edges)?,
            sources: projection.sources().to_vec(),
            targets: projection.targets().to_vec(),
            node_ids,
            edge_ids,
            selected_nodes: BTreeSet::new(),
            selected_edges: BTreeSet::new(),
            focused: None,
            pinned_nodes: BTreeSet::new(),
            applied_revision: 0,
        })
    }

    /// Replace persistent selection atomically after validating every UUID.
    pub fn set_selection(
        &mut self,
        node_ids: impl IntoIterator<Item = Uuid>,
        edge_ids: impl IntoIterator<Item = Uuid>,
    ) -> Result<(), TemporalError> {
        let nodes: BTreeSet<_> = node_ids.into_iter().collect();
        let edges: BTreeSet<_> = edge_ids.into_iter().collect();
        if nodes.iter().any(|id| !self.node_dense.contains_key(id))
            || edges.iter().any(|id| !self.edge_dense.contains_key(id))
        {
            return Err(TemporalError::InvalidArgument);
        }
        self.selected_nodes = nodes;
        self.selected_edges = edges;
        Ok(())
    }

    pub fn set_focus(&mut self, focused: Option<GraphEntity>) -> Result<(), TemporalError> {
        let valid = match focused {
            Some(GraphEntity::Node(id)) => self.node_dense.contains_key(&id),
            Some(GraphEntity::Edge(id)) => self.edge_dense.contains_key(&id),
            None => true,
        };
        if !valid {
            return Err(TemporalError::InvalidArgument);
        }
        self.focused = focused;
        Ok(())
    }

    pub fn set_pinned_nodes(
        &mut self,
        node_ids: impl IntoIterator<Item = Uuid>,
    ) -> Result<(), TemporalError> {
        let nodes: BTreeSet<_> = node_ids.into_iter().collect();
        if nodes.iter().any(|id| !self.node_dense.contains_key(id)) {
            return Err(TemporalError::InvalidArgument);
        }
        self.pinned_nodes = nodes;
        Ok(())
    }

    /// Compute and atomically publish a frame. Failed, cancelled, over-budget,
    /// or stale work never changes the last applied revision or identity state.
    pub fn frame(
        &mut self,
        revision: u64,
        cursor_micros: i64,
        range_start_micros: i64,
        range_end_micros: i64,
        cancel: &CancelFlag,
        budget: usize,
    ) -> Result<TemporalGraphFrame, TemporalError> {
        if revision == 0 || revision <= self.applied_revision {
            return Err(TemporalError::StaleRevision);
        }
        if range_start_micros >= range_end_micros
            || cursor_micros < range_start_micros
            || cursor_micros >= range_end_micros
        {
            return Err(TemporalError::InvalidArgument);
        }
        let required = self
            .nodes
            .work()
            .checked_add(self.edges.work())
            .and_then(|work| work.checked_add(self.edge_ids.len()))
            .ok_or(TemporalError::CapacityExceeded)?;
        if budget < required {
            return Err(TemporalError::BudgetExceeded);
        }
        if cancel.is_cancelled() {
            return Err(TemporalError::Cancelled);
        }

        let node_visibility = self.nodes.visibility(
            cursor_micros,
            range_start_micros,
            range_end_micros,
            cancel,
            budget,
        )?;
        let mut edge_visibility = self.edges.visibility(
            cursor_micros,
            range_start_micros,
            range_end_micros,
            cancel,
            budget,
        )?;
        for (i, visible) in edge_visibility.iter_mut().enumerate() {
            if (i & 0xffff) == 0 && cancel.is_cancelled() {
                return Err(TemporalError::Cancelled);
            }
            let source = usize::try_from(self.sources[i]).map_err(|_| TemporalError::Overflow)?;
            let target = usize::try_from(self.targets[i]).map_err(|_| TemporalError::Overflow)?;
            *visible &= node_visibility[source] & node_visibility[target];
        }

        let visible_node_ids = visible_ids(&self.node_ids, &node_visibility);
        let visible_edge_ids = visible_ids(&self.edge_ids, &edge_visibility);
        let selected_visible_node_ids = visible_node_ids
            .iter()
            .copied()
            .filter(|id| self.selected_nodes.contains(id))
            .collect();
        let selected_visible_edge_ids = visible_edge_ids
            .iter()
            .copied()
            .filter(|id| self.selected_edges.contains(id))
            .collect();
        let focused_visible = self.focused.filter(|entity| match entity {
            GraphEntity::Node(id) => node_visibility[self.node_dense[id]] == 1,
            GraphEntity::Edge(id) => edge_visibility[self.edge_dense[id]] == 1,
        });
        let pinned_visible_node_ids = visible_node_ids
            .iter()
            .copied()
            .filter(|id| self.pinned_nodes.contains(id))
            .collect();

        self.applied_revision = revision;
        Ok(TemporalGraphFrame {
            revision,
            cursor_micros,
            range_start_micros,
            range_end_micros,
            node_visibility,
            edge_visibility,
            visible_node_ids,
            visible_edge_ids,
            selected_visible_node_ids,
            selected_visible_edge_ids,
            focused_visible,
            pinned_visible_node_ids,
        })
    }

    /// Freeze exact state for HTML/PNG/SVG metadata. Persistent selected,
    /// focused, and pinned identities are recorded even when currently hidden.
    pub fn freeze(
        &self,
        frame: &TemporalGraphFrame,
    ) -> Result<FrozenTemporalGraphState, TemporalError> {
        if frame.revision != self.applied_revision {
            return Err(TemporalError::StaleRevision);
        }
        Ok(FrozenTemporalGraphState {
            revision: frame.revision,
            cursor_micros: frame.cursor_micros,
            range_start_micros: frame.range_start_micros,
            range_end_micros: frame.range_end_micros,
            visible_node_ids: frame.visible_node_ids.clone(),
            visible_edge_ids: frame.visible_edge_ids.clone(),
            selected_node_ids: self.selected_nodes.iter().copied().collect(),
            selected_edge_ids: self.selected_edges.iter().copied().collect(),
            focused: self.focused,
            pinned_node_ids: self.pinned_nodes.iter().copied().collect(),
        })
    }
}

fn visible_ids(ids: &[Uuid], visibility: &[u8]) -> Vec<Uuid> {
    ids.iter()
        .zip(visibility)
        .filter_map(|(&id, &visible)| (visible == 1).then_some(id))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::temporal::TemporalPrecision;

    fn id(value: u8) -> Uuid {
        [value; 16]
    }

    fn projection() -> GraphProjection {
        GraphProjection::new(
            &[id(1), id(2), id(3)],
            &[id(11), id(12)],
            &[id(1), id(2)],
            &[id(2), id(3)],
            None,
            true,
        )
        .unwrap()
    }

    fn column(values: &[i64], validity: &[u8]) -> TemporalColumn {
        TemporalColumn::from_utc_micros(values, validity, "UTC", TemporalPrecision::Microsecond)
            .unwrap()
    }

    fn binding<'a>(
        starts: &'a TemporalColumn,
        ends: &'a TemporalColumn,
    ) -> TemporalBindingInput<'a> {
        TemporalBindingInput {
            valid_from: Some(starts),
            valid_to: Some(ends),
            event_at: None,
        }
    }

    #[test]
    fn applies_half_open_validity_before_endpoint_closed_edge_visibility() {
        let graph = projection();
        let starts = [0, 10, 20];
        let ends = [30, 20, 40];
        let valid = [1, 1, 1];
        let starts = column(&starts, &valid);
        let ends = column(&ends, &valid);
        let edge_starts = [0, 0];
        let edge_ends = [50, 50];
        let edge_valid = [1, 1];
        let edge_starts = column(&edge_starts, &edge_valid);
        let edge_ends = column(&edge_ends, &edge_valid);
        let mut temporal = TemporalGraph::bind(
            &graph,
            binding(&starts, &ends),
            binding(&edge_starts, &edge_ends),
        )
        .unwrap();
        let frame = temporal
            .frame(1, 20, 20, 21, &CancelFlag::new(), 7)
            .unwrap();
        assert_eq!(frame.node_visibility, [1, 0, 1]);
        assert_eq!(frame.edge_visibility, [0, 0]);
        assert_eq!(frame.visible_node_ids, [id(1), id(3)]);
    }

    #[test]
    fn event_binding_conjoins_range_membership_and_preserves_source_order() {
        let graph = projection();
        let events = [5, 10, 15];
        let event_valid = [1, 0, 1];
        let edge_events = [7, 12];
        let edge_event_valid = [1, 1];
        let events = column(&events, &event_valid);
        let edge_events = column(&edge_events, &edge_event_valid);
        let mut temporal = TemporalGraph::bind(
            &graph,
            TemporalBindingInput {
                event_at: Some(&events),
                ..TemporalBindingInput::default()
            },
            TemporalBindingInput {
                event_at: Some(&edge_events),
                ..TemporalBindingInput::default()
            },
        )
        .unwrap();
        let frame = temporal.frame(1, 9, 0, 10, &CancelFlag::new(), 12).unwrap();
        assert_eq!(frame.node_visibility, [1, 0, 0]);
        assert_eq!(frame.edge_visibility, [0, 0]);
        assert_eq!(frame.visible_node_ids, [id(1)]);
    }

    #[test]
    fn selection_focus_and_pins_survive_hidden_frames_by_uuid() {
        let graph = projection();
        let starts = [0, 10, 20];
        let ends = [10, 20, 30];
        let valid = [1, 1, 1];
        let starts = column(&starts, &valid);
        let ends = column(&ends, &valid);
        let mut temporal = TemporalGraph::bind(
            &graph,
            binding(&starts, &ends),
            TemporalBindingInput::default(),
        )
        .unwrap();
        temporal.set_selection([id(2)], [id(11)]).unwrap();
        temporal.set_focus(Some(GraphEntity::Node(id(2)))).unwrap();
        temporal.set_pinned_nodes([id(2)]).unwrap();

        let visible = temporal
            .frame(1, 15, 15, 16, &CancelFlag::new(), 7)
            .unwrap();
        assert_eq!(visible.selected_visible_node_ids, [id(2)]);
        assert_eq!(visible.focused_visible, Some(GraphEntity::Node(id(2))));
        assert_eq!(visible.pinned_visible_node_ids, [id(2)]);

        let hidden = temporal
            .frame(2, 25, 25, 26, &CancelFlag::new(), 7)
            .unwrap();
        assert!(hidden.selected_visible_node_ids.is_empty());
        assert_eq!(hidden.focused_visible, None);
        assert!(hidden.pinned_visible_node_ids.is_empty());
        let frozen = temporal.freeze(&hidden).unwrap();
        assert_eq!(frozen.selected_node_ids, [id(2)]);
        assert_eq!(frozen.focused, Some(GraphEntity::Node(id(2))));
        assert_eq!(frozen.pinned_node_ids, [id(2)]);
    }

    #[test]
    fn stale_cancelled_and_over_budget_frames_commit_nothing() {
        let graph = projection();
        let mut temporal = TemporalGraph::bind(
            &graph,
            TemporalBindingInput::default(),
            TemporalBindingInput::default(),
        )
        .unwrap();
        assert_eq!(
            temporal
                .frame(1, 5, 0, 10, &CancelFlag::new(), 6)
                .unwrap_err(),
            TemporalError::BudgetExceeded
        );
        let cancelled = CancelFlag::new();
        cancelled.cancel();
        assert_eq!(
            temporal.frame(1, 5, 0, 10, &cancelled, 7).unwrap_err(),
            TemporalError::Cancelled
        );
        let frame = temporal.frame(1, 5, 0, 10, &CancelFlag::new(), 7).unwrap();
        assert_eq!(frame.visible_node_ids.len(), 3);
        assert_eq!(
            temporal
                .frame(1, 5, 0, 10, &CancelFlag::new(), 7)
                .unwrap_err(),
            TemporalError::StaleRevision
        );
    }

    #[test]
    fn invalid_planes_and_unknown_interaction_ids_fail_atomically() {
        let graph = projection();
        let short = column(&[0], &[1]);
        assert_eq!(
            TemporalGraph::bind(
                &graph,
                TemporalBindingInput {
                    valid_from: Some(&short),
                    ..TemporalBindingInput::default()
                },
                TemporalBindingInput::default(),
            )
            .unwrap_err(),
            TemporalError::InvalidArgument
        );
        let mut temporal = TemporalGraph::bind(
            &graph,
            TemporalBindingInput::default(),
            TemporalBindingInput::default(),
        )
        .unwrap();
        temporal.set_selection([id(1)], [id(11)]).unwrap();
        assert_eq!(
            temporal.set_selection([id(99)], []).unwrap_err(),
            TemporalError::InvalidArgument
        );
        let frame = temporal.frame(1, 5, 0, 10, &CancelFlag::new(), 7).unwrap();
        assert_eq!(frame.selected_visible_node_ids, [id(1)]);
        assert_eq!(frame.selected_visible_edge_ids, [id(11)]);
    }
}
