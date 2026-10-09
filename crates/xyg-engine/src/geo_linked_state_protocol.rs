//! Private selected-state ownership and framing. Dossier §27/§29/§34.
use super::*;
use crate::geo_linked_state::{
    GeoLinkedState, GeoLinkedStateAdmission, GeoSelectedStyle, MAX_SELECTED_IDS,
};

pub(super) const MAX_SCOPES: usize = 8;
pub(super) struct Scope {
    pub source: GeoSourceManifest,
    pub namespace: u64,
    pub layer_id: u64,
    pub snapshot: GeoOperationSnapshot,
    pub admission: Mutex<GeoLinkedStateAdmission>,
    pub _lease: GeoProcessorLease,
}
pub(super) struct State {
    pub scope: Arc<Scope>,
    pub value: Arc<GeoLinkedState>,
}
pub(super) fn scope(entry: &Entry) -> Option<Arc<Scope>> {
    match entry {
        Entry::Session(s) => s.scope.clone(),
        Entry::Rows(s) => s.scope.clone(),
        Entry::Indexed(s) => s.scope.clone(),
        Entry::Hierarchy(hierarchy) => hierarchy::scope(hierarchy),
        Entry::Data {
            semantic: Some(s), ..
        } => s.scope.clone(),
        Entry::Data { rows: Some(s), .. } => s.scope.clone(),
        _ => None,
    }
}
fn options(request: &[u8]) -> Result<GeoLodOptions> {
    if u32at(request, 12) > 1 || u32at(request, 76) > 1 {
        return Err(SourceError::InvalidFrame);
    }
    Ok(GeoLodOptions {
        kind: match u32at(request, 68) {
            0 => GeoReducedKind::Cluster,
            1 => GeoReducedKind::Density,
            _ => return Err(SourceError::InvalidFrame),
        },
        previous_direct: u32at(request, 76) == 1,
        max_cells: u32at(request, 72) as usize,
        processor_bytes: budget(request)?.processor_bytes,
        max_projected_vertices: u64at(request, 224),
    })
}
pub(super) fn validate_current(state: &State, snapshot: GeoOperationSnapshot) -> Result<()> {
    state.value.validate_snapshot(snapshot)?;
    let admission = state
        .scope
        .admission
        .lock()
        .map_err(|_| SourceError::ResourceLimit)?;
    let current = admission.current().ok_or(SourceError::StaleSource)?;
    if current.binding() != state.value.binding()
        || current.selected_ids() != state.value.selected_ids()
        || current.style() != state.value.style()
    {
        return Err(SourceError::StaleSource);
    }
    Ok(())
}
pub(super) fn start(r: &mut Registry, request: &[u8]) -> Result<[u8; HEADER]> {
    let command = u32at(request, 8);
    let handle = u64at(request, 16);
    let sequence = u64at(request, 24);
    let payload = &request[HEADER..];
    let index = r
        .entries
        .iter()
        .position(|(id, _)| *id == handle)
        .ok_or(SourceError::StaleSource)?;
    if command == 32 {
        if payload.len() != 16 || sequence == 0 {
            return Err(SourceError::InvalidFrame);
        }
        let entry = &r.entries[index].1;
        let (source, result) = semantic_authority(entry, sequence)?;
        let namespace = u64at(payload, 0);
        let layer_id = u64at(payload, 8);
        if result.key.identity.layer_id != layer_id {
            return Err(SourceError::StaleSource);
        }
        if r.entries
            .iter()
            .filter(|(_, e)| matches!(e, Entry::Scope(_)))
            .count()
            >= MAX_SCOPES
        {
            return Err(SourceError::ResourceLimit);
        }
        if r.entries.iter().any(|(_,e)| matches!(e,Entry::Scope(s) if s.namespace==namespace && s.layer_id==layer_id && s.source.digest()==source.digest() && s.source.generation()==source.generation())) {return Err(SourceError::StaleSource);}
        let charge = source
            .clone_reserved_bytes()
            .checked_add(std::mem::size_of::<Scope>() + 256)
            .ok_or(SourceError::ResourceLimit)?;
        if charge > budget(request)?.processor_bytes {
            return Err(SourceError::ResourceLimit);
        }
        let lease = GeoProcessorLease::acquire(charge)?;
        let scope = Arc::new(Scope {
            source: source.clone_validated(),
            namespace,
            layer_id,
            snapshot: data_snapshot(entry)?,
            admission: Mutex::new(GeoLinkedStateAdmission::default()),
            _lease: lease,
        });
        let id = insert(r, Entry::Scope(scope))?;
        return Ok(reply(id, sequence));
    }
    if command == 33 || command == 34 {
        r.next.checked_add(1).ok_or(SourceError::ResourceLimit)?;
        if sequence != 0 {
            return Err(SourceError::InvalidFrame);
        }
        let Entry::Scope(scope) = &r.entries[index].1 else {
            return Err(SourceError::InvalidFrame);
        };
        let scope = scope.clone();
        let value = if command == 33 {
            if payload.len() < 24 || payload[12..16].iter().any(|&x| x != 0) {
                return Err(SourceError::InvalidFrame);
            }
            let count =
                usize::try_from(u64at(payload, 16)).map_err(|_| SourceError::ResourceLimit)?;
            if count > MAX_SELECTED_IDS
                || count.checked_mul(8).and_then(|n| n.checked_add(24)) != Some(payload.len())
            {
                return Err(SourceError::InvalidFrame);
            }
            // Temporary raw IDs and durable canonical state overlap; reserve first.
            let charge = count
                .checked_mul(16)
                .and_then(|n| n.checked_add(1024))
                .ok_or(SourceError::ResourceLimit)?;
            if charge > budget(request)?.processor_bytes {
                return Err(SourceError::ResourceLimit);
            }
            let _temporary = GeoProcessorLease::acquire(count * 8 + 128)?;
            let ids: Vec<_> = (0..count).map(|i| u64at(payload, 24 + i * 8)).collect();
            GeoLinkedState::new(
                &scope.source,
                scope.namespace,
                scope.layer_id,
                u64at(payload, 0),
                &ids,
                GeoSelectedStyle {
                    fill: payload[8..12].try_into().unwrap(),
                },
            )?
        } else {
            if payload.len() != 16 {
                return Err(SourceError::InvalidFrame);
            }
            let state = &r
                .entries
                .iter()
                .find(|(id, _)| *id == u64at(payload, 0))
                .ok_or(SourceError::StaleSource)?
                .1;
            let Entry::State(state) = state else {
                return Err(SourceError::InvalidFrame);
            };
            let charge = state
                .value
                .selected_ids()
                .len()
                .checked_mul(8)
                .and_then(|n| n.checked_add(std::mem::size_of::<GeoLinkedState>() + 128))
                .ok_or(SourceError::ResourceLimit)?;
            if charge > budget(request)?.processor_bytes {
                return Err(SourceError::ResourceLimit);
            }
            state.value.link_to(
                &scope.source,
                scope.namespace,
                scope.layer_id,
                u64at(payload, 8),
            )?
        };
        let mut snapshot = scope.snapshot;
        snapshot.state_revision = value.binding().state_revision;
        scope
            .admission
            .lock()
            .map_err(|_| SourceError::ResourceLimit)?
            .admit(value.clone(), snapshot)?;
        let revision = value.binding().state_revision;
        let id = insert(r, Entry::State(State { scope, value }))?;
        return Ok(reply(id, revision));
    }
    if payload.len() != 8 || sequence == 0 {
        return Err(SourceError::InvalidFrame);
    }
    let state_id = u64at(payload, 0);
    if state_id == handle {
        return Err(SourceError::InvalidFrame);
    }
    let state_index = r
        .entries
        .iter()
        .position(|(id, _)| *id == state_id)
        .ok_or(SourceError::StaleSource)?;
    let Entry::State(state) = &r.entries[state_index].1 else {
        return Err(SourceError::InvalidFrame);
    };
    let snapshot = index_snapshot(request)?;
    validate_current(state, snapshot)?;
    let value = state.value.clone();
    let scope = state.scope.clone();
    let options = options(request)?;
    if command == 35 {
        let Entry::Session(source) = &mut r.entries[index].1 else {
            return Err(SourceError::InvalidFrame);
        };
        if source
            .scope
            .as_ref()
            .is_some_and(|old| !Arc::ptr_eq(old, &scope))
        {
            return Err(SourceError::StaleSource);
        }
        source.begin_with_state(
            sequence,
            snapshot,
            camera(request)?,
            QuerySpec {
                bounds: None,
                time: snapshot.time,
            },
            options,
            Some(value),
        )?;
        source.scope = Some(scope);
        r.entries.remove(state_index);
        return Ok(reply(handle, sequence));
    }
    if command != 36 {
        return Err(SourceError::InvalidFrame);
    }
    if r.entries
        .iter()
        .filter(|(_, e)| overview::is_session(e))
        .count()
        >= MAX_SESSIONS
    {
        return Err(SourceError::ResourceLimit);
    }
    let Entry::Index(owner) = &r.entries[index].1 else {
        return Err(SourceError::InvalidFrame);
    };
    let owner = owner.clone();
    let mut transition = owner
        .transition
        .lock()
        .map_err(|_| SourceError::ResourceLimit)?;
    if sequence <= transition.0
        || snapshot.precedes(transition.1)
        || snapshot.source_digest != owner.index.source().digest()
        || snapshot.generation != owner.index.source().generation()
        || snapshot.style_revision
            < owner
                .painted
                .lock()
                .map_err(|_| SourceError::ResourceLimit)?
                .0
    {
        return Err(SourceError::StaleSource);
    }
    let mut lane_scope = owner.scope.lock().map_err(|_| SourceError::ResourceLimit)?;
    if lane_scope
        .as_ref()
        .is_some_and(|old| !Arc::ptr_eq(old, &scope))
    {
        return Err(SourceError::StaleSource);
    }
    let estimate = estimate_work(&owner.index, &camera(request)?, snapshot.time)?;
    let fallback = if estimate.leaf_streams > crate::geo_spatial_index::MAX_FRONTIER {
        1
    } else if estimate.leaf_reads > budget(request)?.max_chunks as u64 {
        2
    } else {
        0
    };
    if fallback != 0 {
        let mut out = reply(handle, sequence);
        put32(&mut out, 8, 10);
        put32(&mut out, 48, fallback);
        return Ok(out);
    }
    let lease = GeoProcessorLease::acquire(4096)?;
    let Some(mut session) = GeoIndexedQuerySession::new_with_state(
        owner.index.clone(),
        camera(request)?,
        snapshot.time,
        options,
        snapshot.layer_id,
        snapshot.style_revision,
        snapshot.state_revision,
        budget(request)?.max_read_bytes,
        Some(value),
    )?
    else {
        let mut out = reply(handle, sequence);
        put32(&mut out, 8, 10);
        put32(&mut out, 48, 1);
        return Ok(out);
    };
    session.set_work_limits(
        budget(request)?.max_rows_examined,
        budget(request)?.max_chunks as u64,
    )?;
    // No allocation/validation remains after the State entry is replaced.
    let query = Box::new(IndexQuery {
        owner: owner.clone(),
        scope: Some(scope.clone()),
        selected_replacement: true,
        session: Some(session),
        published: None,
        sequence,
        snapshot,
        _lease: lease,
    });
    r.entries[state_index].1 = Entry::Indexed(query);
    *lane_scope = Some(scope);
    *transition = (sequence, snapshot);
    Ok(reply(state_id, sequence))
}

pub(super) fn footer_bytes(state: &GeoLinkedState, counts: &[u64]) -> Result<usize> {
    state
        .selected_ids()
        .len()
        .checked_add(counts.len())
        .and_then(|n| n.checked_mul(8))
        .and_then(|n| n.checked_add(128))
        .ok_or(SourceError::ResourceLimit)
}
pub(super) fn append_footer(
    out: &mut Vec<u8>,
    state: &GeoLinkedState,
    counts: &[u64],
    visible: Option<u64>,
    identity: GeoLodIdentity,
) -> Result<()> {
    state.validate_identity(identity)?;
    let length = footer_bytes(state, counts)?;
    put32(out, 4, 2);
    put64(out, 248, length as u64);
    let at = out.len();
    out.resize(at + length, 0);
    let b = &mut out[at..];
    b[..4].copy_from_slice(b"XYSE");
    put32(b, 4, 1);
    put32(b, 8, if visible.is_some() { 3 } else { 1 });
    let binding = state.binding();
    for (offset, value) in [
        (16, binding.namespace),
        (24, state.selected_ids().len() as u64),
        (32, counts.len() as u64),
        (40, visible.unwrap_or(0)),
        (64, binding.generation),
        (72, binding.layer_id),
        (80, binding.state_revision),
        (88, identity.source_rows),
    ] {
        put64(b, offset, value);
    }
    b[48..52].copy_from_slice(&state.style().fill);
    b[56..64].copy_from_slice(&binding.source_digest);
    put32(b, 96, identity.geometry as u32);
    put32(b, 100, identity.crs as u32);
    let fingerprint = state.fingerprint();
    put64(b, 104, fingerprint[0]);
    put64(b, 112, fingerprint[1]);
    for (i, value) in state.selected_ids().iter().chain(counts).enumerate() {
        put64(b, 128 + i * 8, *value);
    }
    Ok(())
}
