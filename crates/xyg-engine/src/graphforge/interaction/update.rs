//! Structural document replacement: validate a temporary candidate, then
//! reconcile the authoritative state and install it in one locked world (§2.1).
use super::*;

impl GraphSession {
    /// Full replacement, not a load patch. Omitted positions seed lazily;
    /// omitted collapse/budgets take create defaults. Pins survive by UUID
    /// unless `load.pinned` explicitly replaces them.
    pub fn update(
        &mut self,
        header: OpHeader,
        document: &[u8],
        load: SessionLoad,
    ) -> Result<OpOutcome, InteractionStatus> {
        match &self.last_op {
            _ if header.op_seq == 0 => return invalid(),
            Some((last, outcome)) if *last == header.op_seq => return Ok(outcome.clone()),
            Some((last, _)) if header.op_seq < *last => return invalid(),
            _ => {}
        }
        let replace_pins = load.pinned.is_some();
        let candidate = Self::create(document, load, self.instance_id)?;
        // A bound replacement cannot change the owner's canonical UUID order
        // or persisted endpoints. Validate against the owner inside the SAME
        // access that reconciles its authoritative state.
        let bound = match &self.slot {
            StateSlot::Bound { host, handle } => Some((Arc::clone(host), *handle)),
            _ => None,
        };
        let outcome = if let Some((host, handle)) = bound {
            let mut candidate = Some(candidate);
            let mut outcome = None;
            let found = host.with_graph(handle, &mut |graph| {
                let next = candidate.take().expect("one locked access");
                if !next.matches_temporal(graph) {
                    outcome = Some(Err(InteractionStatus::Invalid));
                    return;
                }
                let (state, visibility, temporal_revision) = graph.world_parts();
                outcome = Some(self.install_update(
                    header,
                    next,
                    replace_pins,
                    World {
                        state,
                        visibility,
                        temporal_revision,
                    },
                ));
            });
            if !found {
                return Err(InteractionStatus::Unbound);
            }
            outcome.ok_or(InteractionStatus::Unbound)??
        } else {
            self.locked(|session, world| {
                session.install_update(header, candidate, replace_pins, world)
            })??
        };
        self.last_op = Some((header.op_seq, outcome.clone()));
        Ok(outcome)
    }

    fn install_update(
        &mut self,
        header: OpHeader,
        mut next: Self,
        replace_pins: bool,
        world: World<'_>,
    ) -> Result<OpOutcome, InteractionStatus> {
        if header.stamp
            != (Stamp {
                instance_id: self.instance_id,
                render_revision: self.render_revision,
            })
            || world.temporal_revision != self.seen_temporal
        {
            return Err(InteractionStatus::Stale);
        }
        self.reserve_revision()?;
        let same_generation = next.generation == self.generation;
        let dropped = world.state.retain_identities(
            |id| next.identity.node_index(id).is_some(),
            |id| next.identity.edge_index(id).is_some(),
            |key| same_generation && next.identity.resolve_derived_key(key).is_some(),
        );
        let mut pins_changed = false;
        if replace_pins {
            let StateSlot::Owned(state) = &next.slot else {
                unreachable!()
            };
            pins_changed = world.state.pinned_nodes() != state.pinned_nodes();
            world.state.set_pinned(state.pinned_nodes().clone());
        }
        next.render_revision = self.render_revision + 1;
        next.seen_temporal = world.temporal_revision;
        next.work = self.work;
        std::mem::swap(&mut next.slot, &mut self.slot);
        std::mem::swap(&mut next.coordination, &mut self.coordination);
        *self = next;
        Ok(OpOutcome {
            dropped: dropped as u32,
            ..self.outcome(&world, dropped != 0 || pins_changed)
        })
    }

    fn matches_temporal(&self, graph: &TemporalGraph) -> bool {
        self.identity.node_uuids() == graph.node_ids()
            && self
                .identity
                .persisted_edge_uuids()
                .eq(graph.edge_ids().iter().copied())
            && self
                .edge_source
                .iter()
                .zip(&self.edge_target)
                .enumerate()
                .filter(|(i, _)| !self.identity.is_derived(*i))
                .map(|(_, (&s, &t))| (s, t))
                .eq(graph.edge_endpoints())
    }
}
