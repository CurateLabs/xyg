//! Graph snapshots use exact identities and a sequence independent of paint.
use super::*;
use crate::coordination::{CoordinationGate, GateError};
use crate::graphforge::identity::ResultRef;
use std::cmp::Ordering;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct GraphCoordinationEvent {
    pub group_id: u64,
    pub source_instance: u64,
    /// Outbound selection sequence, not render_revision or op_seq.
    pub revision: u64,
    pub generation: Option<Uuid>,
    pub refs: Vec<ElementRef>,
}

#[derive(Clone, Default)]
pub(super) struct Link {
    pub group: u64,
    pub sequence: u64,
    pub gate: CoordinationGate,
    pub pending: Option<GraphCoordinationEvent>,
}

// Semantic transport order: node UUID, edge UUID, then exact
// (result-id None before Some, layer, path, order). Local table slots and
// aggregates are never transport identities.
fn compare(a: &ElementRef, b: &ElementRef) -> Ordering {
    let kind = |r: &ElementRef| match r {
        ElementRef::Node(_) => 0,
        ElementRef::Edge(_) => 1,
        ElementRef::Derived(_) => 2,
        ElementRef::Aggregate(_) => 3,
    };
    kind(a).cmp(&kind(b)).then_with(|| match (a, b) {
        (ElementRef::Node(a), ElementRef::Node(b)) | (ElementRef::Edge(a), ElementRef::Edge(b)) => {
            a.cmp(b)
        }
        (ElementRef::Derived(a), ElementRef::Derived(b)) => {
            let exact = |r: &ResultRef| match r {
                ResultRef::Exact(s) => s.clone(),
                _ => None,
            };
            (exact(&a.result), a.layer, a.path, a.order).cmp(&(
                exact(&b.result),
                b.layer,
                b.path,
                b.order,
            ))
        }
        _ => Ordering::Equal,
    })
}

impl GraphCoordinationEvent {
    pub(super) fn validate(&self) -> Result<(), InteractionStatus> {
        if self.refs.len() > MAX_GRAPH_SELECTION_REFS {
            return Err(InteractionStatus::SelectionTooLarge);
        }
        if self.source_instance == 0
            || self.revision == 0
            || self.refs.iter().any(|r| match r {
                ElementRef::Node(id) | ElementRef::Edge(id) => *id == super::super::NIL_UUID,
                ElementRef::Derived(d) => match &d.result {
                    ResultRef::Local(_) => true,
                    ResultRef::Exact(_) => false,
                },
                ElementRef::Aggregate(_) => true,
            })
            || self
                .refs
                .windows(2)
                .any(|p| compare(&p[0], &p[1]) != Ordering::Less)
        {
            return Err(InteractionStatus::Invalid);
        }
        Ok(())
    }
}

impl GraphSession {
    /// Compatible unlinked `create`; linked hosts use this typed S3 constructor.
    pub fn create_linked(
        document: &[u8],
        load: SessionLoad,
        instance_id: u64,
        group_id: u64,
    ) -> Result<Self, InteractionStatus> {
        if instance_id == 0 {
            return invalid();
        }
        let mut session = Self::create(document, load, instance_id)?;
        session.coordination.group = group_id;
        Ok(session)
    }

    pub fn group_id(&self) -> u64 {
        self.coordination.group
    }
    pub fn pending_outbound(&self) -> Option<&GraphCoordinationEvent> {
        self.coordination.pending.as_ref()
    }
    pub fn take_outbound(&mut self) -> Option<GraphCoordinationEvent> {
        self.coordination.pending.take()
    }

    pub(super) fn admit_outbound(&self) -> Result<(), InteractionStatus> {
        if self.coordination.group != 0 && self.coordination.sequence == u64::MAX {
            return Err(InteractionStatus::RevisionExhausted);
        }
        Ok(())
    }

    pub(super) fn queue_selection(&mut self, state: &GraphInteractionState) {
        if self.coordination.group == 0 {
            return;
        }
        self.coordination.sequence += 1; // admitted before state writes
        let mut refs: Vec<_> = self
            .identity
            .refs_of(state.selection())
            .iter()
            .filter_map(|r| self.identity.to_transport(r))
            .collect();
        refs.sort_by(compare);
        self.coordination.pending = Some(GraphCoordinationEvent {
            group_id: self.coordination.group,
            source_instance: self.instance_id,
            revision: self.coordination.sequence,
            generation: self.generation,
            refs,
        });
    }

    /// Validate the entire remote snapshot before filtering its group. Resolve
    /// all identities before the one state write; a failure consumes no watermark.
    pub fn apply_remote(
        &mut self,
        header: OpHeader,
        event: &GraphCoordinationEvent,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |session, world| {
            event.validate()?;
            if session.coordination.group == 0 {
                return Err(InteractionStatus::Unlinked);
            }
            let apply = session
                .coordination
                .gate
                .validate(
                    session.instance_id,
                    session.coordination.group,
                    event.source_instance,
                    event.group_id,
                    event.revision,
                )
                .map_err(|e| match e {
                    GateError::Invalid => InteractionStatus::Invalid,
                    GateError::SelfEcho => InteractionStatus::SelfEcho,
                    GateError::Stale => InteractionStatus::StaleRemote,
                })?;
            if !apply {
                return Ok(session.outcome(world, false));
            }
            let mut delta = ElementSet::default();
            let mut unmatched = 0;
            for reference in &event.refs {
                let resolved = if matches!(reference, ElementRef::Derived(_))
                    && event.generation != session.generation
                {
                    None
                } else {
                    session.identity.resolve(reference).ok()
                };
                if let Some(index) = resolved {
                    session.identity.insert_into(&mut delta, index);
                } else {
                    unmatched += 1;
                }
            }
            let changed = world.state.select(SelectMode::Replace, &delta)?;
            session
                .coordination
                .gate
                .commit(event.source_instance, event.revision);
            Ok(OpOutcome {
                changed: session.identity.refs_of(&changed),
                unmatched,
                ..session.outcome(world, !changed.is_empty())
            })
        })
    }
}
