//! Private paged-hierarchy child; registry, transfer credit and Scene policy stay shared.
use super::*;
use crate::geo_spatial_hierarchy::{
    GeoHierarchyOptions, GeoHierarchyStep, GeoHierarchyTicket, ValidatedGeoHierarchy,
};
use crate::geo_spatial_hierarchy_build::GeoHierarchyBuildSession;
use crate::geo_spatial_hierarchy_query::{
    GeoHierarchyQueryLimits, GeoHierarchyQuerySession, GeoHierarchyResult,
};

pub(super) struct Owner {
    index: Arc<ValidatedGeoHierarchy>,
    sequence: u64,
    created_snapshot: GeoOperationSnapshot,
    created_style: [u8; 48],
    scope: Option<Arc<linked_state::Scope>>,
    transition: Mutex<(u64, GeoOperationSnapshot)>,
    painted: Mutex<(u64, [u8; 48])>,
    _lease: GeoProcessorLease,
}
pub(super) struct Pending {
    ticket: GeoHierarchyTicket,
    copies: AtomicU8,
}
pub(super) enum Owned {
    Build {
        session: Box<GeoHierarchyBuildSession>,
        sequence: u64,
        snapshot: GeoOperationSnapshot,
        style: [u8; 48],
        scope: Option<Arc<linked_state::Scope>>,
        pending: Option<Pending>,
        _lease: GeoProcessorLease,
    },
    Index(Arc<Owner>),
    Query {
        session: Box<GeoHierarchyQuerySession>,
        owner: Arc<Owner>,
        sequence: u64,
        snapshot: GeoOperationSnapshot,
        pending: Option<Pending>,
        result: Option<Box<GeoHierarchyResult>>,
        state: Option<Arc<crate::geo_linked_state::GeoLinkedState>>,
        selected_replacement: bool,
        _lease: GeoProcessorLease,
    },
}
impl Owned {
    pub(super) fn is_session(&self) -> bool {
        !matches!(self, Self::Index(_))
    }
}
fn wire(t: &GeoHierarchyTicket, sequence: u64) -> [u8; 128] {
    let mut b = [0; 128];
    put64(&mut b, 0, t.owner());
    put64(&mut b, 8, t.storage_namespace());
    put64(&mut b, 16, t.serial());
    put64(&mut b, 24, sequence);
    put32(&mut b, 32, t.kind() as u32);
    put64(&mut b, 40, t.page_id());
    put64(&mut b, 48, t.encoded_bytes() as u64);
    b[56..64].copy_from_slice(&t.digest());
    if let Some(r) = t.source_request() {
        put64(&mut b, 64, r.generation);
        put32(&mut b, 72, r.chunk_index);
        put32(&mut b, 76, r.rows);
        put64(&mut b, 80, r.first_row);
        put64(&mut b, 88, r.encoded_bytes as u64);
        b[96..104].copy_from_slice(&r.digest);
    }
    b
}
fn checked<'a>(p: &'a Option<Pending>, b: &[u8], seq: u64) -> Result<&'a Pending> {
    let p = p.as_ref().ok_or(SourceError::StaleSource)?;
    if b.len() < 128 || b[..128] != wire(&p.ticket, seq) {
        return Err(SourceError::StaleSource);
    }
    Ok(p)
}
fn save(p: &mut Option<Pending>, t: GeoHierarchyTicket) {
    if p.as_ref().is_none_or(|p| !p.ticket.same(&t)) {
        *p = Some(Pending {
            ticket: t,
            copies: AtomicU8::new(0),
        })
    }
}
fn unsupported(handle: u64, sequence: u64) -> [u8; HEADER] {
    let mut b = reply(handle, sequence);
    put32(&mut b, 8, 17);
    b
}
const CONTROL_BYTES: usize = 4096;
fn remaining(bytes: usize, held: usize) -> Result<usize> {
    bytes
        .checked_sub(held)
        .filter(|v| *v > 0)
        .ok_or(SourceError::ResourceLimit)
}
pub(super) fn scope(owned: &Owned) -> Option<Arc<linked_state::Scope>> {
    match owned {
        Owned::Build { scope, .. } => scope.clone(),
        Owned::Index(o) | Owned::Query { owner: o, .. } => o.scope.clone(),
    }
}
pub(super) fn selected_complete(entry: &Entry) -> bool {
    matches!(entry,Entry::Hierarchy(Owned::Query{selected_replacement:true,result:Some(_),session,pending:None,..}) if !session.has_outstanding_io())
}
fn same_source(a: &GeoSourceManifest, b: &GeoSourceManifest) -> bool {
    a.digest() == b.digest()
        && a.generation() == b.generation()
        && a.rows() == b.rows()
        && a.geometry() == b.geometry()
        && a.crs() == b.crs()
        && a.chunks() == b.chunks()
}
// Shared references do not clone metadata/IDs; count each distinct live State lease.
fn scope_charge(
    scope: Option<&Arc<linked_state::Scope>>,
    state: Option<&Arc<crate::geo_linked_state::GeoLinkedState>>,
) -> Result<usize> {
    let Some(scope) = scope else { return Ok(0) };
    let admission = scope
        .admission
        .lock()
        .map_err(|_| SourceError::ResourceLimit)?;
    let current = admission.current();
    scope
        ._lease
        .bytes()
        .checked_add(
            current
                .filter(|current| state.is_none_or(|s| !Arc::ptr_eq(s, current)))
                .map_or(0, |s| s.retained_bytes()),
        )
        .ok_or(SourceError::ResourceLimit)
}
pub(super) fn data_budget(entry: &Entry, bytes: usize) -> Result<usize> {
    let Entry::Hierarchy(Owned::Query {
        owner,
        session,
        result: Some(result),
        state,
        _lease,
        ..
    }) = entry
    else {
        return Err(SourceError::InvalidFrame);
    };
    let held = owner
        .index
        .reserved_bytes()
        .checked_add(owner._lease.bytes())
        .and_then(|n| n.checked_add(_lease.bytes()))
        .and_then(|n| n.checked_add(session.reserved_bytes()))
        .and_then(|n| n.checked_add(result.reserved_bytes()))
        .ok_or(SourceError::ResourceLimit)?;
    let held = held
        .checked_add(scope_charge(owner.scope.as_ref(), state.as_ref())?)
        .and_then(|n| n.checked_add(state.as_ref().map_or(0, |s| s.retained_bytes())))
        .and_then(|n| {
            n.checked_add(
                result
                    .result
                    .selection
                    .as_ref()
                    .map_or(0, |s| s.retained_bytes()),
            )
        })
        .ok_or(SourceError::ResourceLimit)?;
    remaining(bytes, held)
}
pub(super) fn start(r: &mut Registry, b: &[u8]) -> Result<[u8; HEADER]> {
    let command = u32at(b, 8);
    let handle = u64at(b, 16);
    let sequence = u64at(b, 24);
    let payload = &b[HEADER..];
    if sequence == 0 {
        return Err(SourceError::StaleSource);
    }
    let entry = &r
        .entries
        .iter()
        .find(|(id, _)| *id == handle)
        .ok_or(SourceError::StaleSource)?
        .1;
    if command == 37 {
        if payload.len() != 24 || payload[4..8].iter().any(|v| *v != 0) {
            return Err(SourceError::InvalidFrame);
        }
        let Entry::Data {
            semantic: Some(s), ..
        } = entry
        else {
            return Err(SourceError::InvalidFrame);
        };
        if sequence != s.sequence {
            return Err(SourceError::StaleSource);
        }
        if s.scope.is_some() != s.result.selection.is_some() {
            return Err(SourceError::InvalidFrame);
        }
        if let Some(scope) = &s.scope {
            if !same_source(&scope.source, &s.source)
                || scope.layer_id != s.result.key.identity.layer_id
            {
                return Err(SourceError::StaleSource);
            }
        }
        let snapshot = data_snapshot(entry)?;
        let style = s.style;
        if r.entries
            .iter()
            .filter(|(_, e)| overview::is_session(e))
            .count()
            >= MAX_SESSIONS
        {
            return Err(SourceError::ResourceLimit);
        }
        if r.entries.len() >= MAX_HANDLES {
            return Err(SourceError::ResourceLimit);
        }
        let mut phase = budget(b)?;
        phase.processor_bytes = remaining(
            phase.processor_bytes,
            CONTROL_BYTES
                .checked_add(scope_charge(s.scope.as_ref(), None)?)
                .ok_or(SourceError::ResourceLimit)?,
        )?;
        let lease = GeoProcessorLease::acquire(CONTROL_BYTES)?;
        let session = GeoHierarchyBuildSession::new(
            &s.source,
            GeoHierarchyOptions {
                grid: u32at(payload, 0),
            },
            phase,
            u64at(payload, 8),
            u64at(payload, 16),
        )?;
        let id = insert(
            r,
            Entry::Hierarchy(Owned::Build {
                session: Box::new(session),
                sequence,
                snapshot,
                style,
                scope: s.scope.clone(),
                pending: None,
                _lease: lease,
            }),
        )?;
        return Ok(reply(id, sequence));
    }
    if !matches!(command, 38 | 42 | 43)
        || (command != 43 && !payload.is_empty())
        || (command == 43 && payload.len() != 8)
        || u32at(b, 12) > 1
        || u32at(b, 76) > 1
    {
        return Err(SourceError::InvalidFrame);
    }
    let Entry::Hierarchy(Owned::Index(owner)) = entry else {
        return Err(SourceError::InvalidFrame);
    };
    let owner = owner.clone();
    if command == 42 {
        if sequence != owner.sequence {
            return Err(SourceError::StaleSource);
        }
        if r.entries.len() >= MAX_HANDLES {
            return Err(SourceError::ResourceLimit);
        }
        let held = owner
            .index
            .reserved_bytes()
            .checked_add(2 * CONTROL_BYTES)
            .and_then(|n| n.checked_add(scope_charge(owner.scope.as_ref(), None).ok()?))
            .ok_or(SourceError::ResourceLimit)?;
        remaining(budget(b)?.processor_bytes, held)?;
        let lease = GeoProcessorLease::acquire(CONTROL_BYTES)?;
        let fork = Arc::new(Owner {
            index: owner.index.clone(),
            sequence: owner.sequence,
            created_snapshot: owner.created_snapshot,
            created_style: owner.created_style,
            scope: owner.scope.clone(),
            transition: Mutex::new((owner.sequence, owner.created_snapshot)),
            painted: Mutex::new((owner.created_snapshot.style_revision, owner.created_style)),
            _lease: lease,
        });
        let id = insert(r, Entry::Hierarchy(Owned::Index(fork)))?;
        return Ok(reply(id, sequence));
    }
    let snapshot = index_snapshot(b)?;
    let (state_id, state) = if command == 43 {
        let state_id = u64at(payload, 0);
        let Entry::State(state) = &r
            .entries
            .iter()
            .find(|(id, _)| *id == state_id)
            .ok_or(SourceError::StaleSource)?
            .1
        else {
            return Err(SourceError::InvalidFrame);
        };
        let Some(scope) = owner.scope.as_ref() else {
            return Ok(unsupported(handle, sequence));
        };
        if !Arc::ptr_eq(scope, &state.scope)
            || !same_source(&scope.source, owner.index.source())
            || scope.layer_id != snapshot.layer_id
        {
            return Err(SourceError::StaleSource);
        }
        linked_state::validate_current(state, snapshot)?;
        (Some(state_id), Some(state.value.clone()))
    } else {
        if owner.scope.is_some() {
            return Err(SourceError::StaleSource);
        }
        (None, None)
    };
    let mut transition = owner
        .transition
        .lock()
        .map_err(|_| SourceError::ResourceLimit)?;
    if sequence <= transition.0
        || snapshot.precedes(transition.1)
        || snapshot.style_revision
            < owner
                .painted
                .lock()
                .map_err(|_| SourceError::ResourceLimit)?
                .0
        || snapshot.source_digest != owner.index.source().digest()
        || snapshot.generation != owner.index.source().generation()
    {
        return Err(SourceError::StaleSource);
    }
    if r.entries
        .iter()
        .filter(|(_, e)| overview::is_session(e))
        .count()
        >= MAX_SESSIONS
    {
        return Err(SourceError::ResourceLimit);
    }
    let mut limits = budget(b)?;
    limits.processor_bytes = remaining(
        limits.processor_bytes,
        CONTROL_BYTES
            .checked_add(owner._lease.bytes())
            .and_then(|n| n.checked_add(scope_charge(owner.scope.as_ref(), state.as_ref()).ok()?))
            .ok_or(SourceError::ResourceLimit)?,
    )?;
    let options = GeoLodOptions {
        kind: match u32at(b, 68) {
            0 => GeoReducedKind::Cluster,
            1 => GeoReducedKind::Density,
            _ => return Err(SourceError::InvalidFrame),
        },
        previous_direct: u32at(b, 76) == 1,
        max_cells: u32at(b, 72) as usize,
        processor_bytes: limits.processor_bytes,
        max_projected_vertices: u64at(b, 224),
    };
    if state_id.is_none() && r.entries.len() >= MAX_HANDLES {
        return Err(SourceError::ResourceLimit);
    }
    let lease = GeoProcessorLease::acquire(CONTROL_BYTES)?;
    let session = GeoHierarchyQuerySession::new_with_state(
        owner.index.clone(),
        camera(b)?,
        snapshot.time,
        options,
        snapshot.layer_id,
        snapshot.style_revision,
        snapshot.state_revision,
        GeoHierarchyQueryLimits {
            processor_bytes: limits.processor_bytes,
            directory_reads: limits.max_chunks as u64,
            leaf_reads: limits.max_chunks as u64,
            vertex_records: limits.max_rows_examined,
            read_bytes: limits.max_read_bytes,
        },
        state.clone(),
    )?;
    let query = Entry::Hierarchy(Owned::Query {
        session: Box::new(session),
        owner: owner.clone(),
        sequence,
        snapshot,
        pending: None,
        result: None,
        state,
        selected_replacement: command == 43,
        _lease: lease,
    });
    let id = if let Some(id) = state_id {
        let position = r
            .entries
            .iter()
            .position(|(h, _)| *h == id)
            .ok_or(SourceError::StaleSource)?;
        r.entries[position].1 = query;
        id
    } else {
        insert(r, query)?
    };
    *transition = (sequence, snapshot);
    Ok(reply(id, sequence))
}
pub(super) fn authority(
    entry: &Entry,
    seq: u64,
) -> Result<(&GeoSourceManifest, &GeoPointResult, GeoOperationSnapshot)> {
    let Entry::Hierarchy(Owned::Query {
        owner,
        sequence,
        snapshot,
        result: Some(result),
        ..
    }) = entry
    else {
        return Err(SourceError::InvalidFrame);
    };
    if seq != *sequence
        || owner
            .transition
            .lock()
            .map_err(|_| SourceError::ResourceLimit)?
            .0
            != seq
    {
        return Err(SourceError::StaleSource);
    }
    Ok((owner.index.source(), &result.result, *snapshot))
}
pub(super) fn validate_style(entry: &Entry, style: &[u8; 48]) -> Result<()> {
    let Entry::Hierarchy(Owned::Query {
        owner,
        snapshot,
        sequence,
        ..
    }) = entry
    else {
        return Err(SourceError::InvalidFrame);
    };
    if owner
        .transition
        .lock()
        .map_err(|_| SourceError::ResourceLimit)?
        .0
        != *sequence
    {
        return Err(SourceError::StaleSource);
    }
    let p = owner
        .painted
        .lock()
        .map_err(|_| SourceError::ResourceLimit)?;
    if snapshot.style_revision < p.0 || (snapshot.style_revision == p.0 && *style != p.1) {
        return Err(SourceError::StaleSource);
    }
    Ok(())
}
pub(super) fn commit_style(entry: &Entry, style: [u8; 48]) -> Result<()> {
    let Entry::Hierarchy(Owned::Query {
        owner, snapshot, ..
    }) = entry
    else {
        return Err(SourceError::InvalidFrame);
    };
    *owner
        .painted
        .lock()
        .map_err(|_| SourceError::ResourceLimit)? = (snapshot.style_revision, style);
    Ok(())
}
fn complete(out: &mut [u8], result: &GeoHierarchyResult) {
    put32(out, 8, 19);
    let s = result.stats;
    put64(out, 160, s.directory_reads);
    put64(out, 168, s.leaf_reads);
    put64(out, 176, s.bytes_read);
    put64(out, 184, s.vertex_records);
    put32(out, 192, s.passes);
    put32(out, 196, s.selected_cells as u32);
}
pub(super) fn operation(r: &mut Registry, index: usize, b: &[u8]) -> Result<[u8; HEADER]> {
    let command = u32at(b, 8);
    let handle = u64at(b, 16);
    let seq = u64at(b, 24);
    let payload = &b[HEADER..];
    let mut out = reply(handle, seq);
    let Entry::Hierarchy(owned) = &mut r.entries[index].1 else {
        return Err(SourceError::InvalidFrame);
    };
    let expected = match owned {
        Owned::Build { sequence, .. } | Owned::Query { sequence, .. } => *sequence,
        Owned::Index(o) => o.sequence,
    };
    if seq != expected {
        return Err(SourceError::StaleSource);
    }
    if command == 10 {
        if !payload.is_empty() {
            return Err(SourceError::InvalidFrame);
        }
        let outstanding = match owned {
            Owned::Build { session, .. } => {
                session.cancel();
                session.has_outstanding_io()
            }
            Owned::Query { session, .. } => {
                session.cancel();
                session.has_outstanding_io()
            }
            Owned::Index(_) => false,
        };
        if outstanding {
            put32(&mut out, 8, 2)
        } else {
            r.entries.remove(index);
        }
        return Ok(out);
    }
    match owned {
        Owned::Index(o) => {
            if command != 6 || !payload.is_empty() {
                return Err(SourceError::InvalidFrame);
            }
            put32(&mut out, 8, 18);
            out[40..48].copy_from_slice(&o.index.digest());
            put64(&mut out, 48, o.index.storage_namespace());
        }
        Owned::Build {
            session,
            sequence,
            snapshot,
            style,
            scope,
            pending,
            _lease,
        } => match command {
            6 => {
                if !payload.is_empty() {
                    return Err(SourceError::InvalidFrame);
                }
                match session.step()? {
                    GeoHierarchyStep::NeedRead(t) | GeoHierarchyStep::NeedWrite(t) => {
                        let write = t.kind() == 3;
                        save(pending, t);
                        put32(&mut out, 8, if write { 7 } else { 1 });
                        out[64..192].copy_from_slice(&wire(&pending.as_ref().unwrap().ticket, seq));
                    }
                    GeoHierarchyStep::AwaitRelease => {
                        put32(&mut out, 8, 2);
                        if let Some(p) = pending {
                            out[64..192].copy_from_slice(&wire(&p.ticket, seq));
                        }
                    }
                    GeoHierarchyStep::Complete => {
                        let value = session.finish()?;
                        out[40..48].copy_from_slice(&value.digest());
                        put64(&mut out, 48, value.storage_namespace());
                        let lease = std::mem::replace(_lease, GeoProcessorLease::acquire(0)?);
                        *owned = Owned::Index(Arc::new(Owner {
                            index: value,
                            sequence: *sequence,
                            created_snapshot: *snapshot,
                            created_style: *style,
                            scope: scope.clone(),
                            transition: Mutex::new((*sequence, *snapshot)),
                            painted: Mutex::new((snapshot.style_revision, *style)),
                            _lease: lease,
                        }));
                        put32(&mut out, 8, 18);
                    }
                    GeoHierarchyStep::Cancelled => put32(&mut out, 8, 9),
                    _ => return Err(SourceError::InvalidFrame),
                }
            }
            7 => {
                let p = checked(pending, payload, seq)?;
                if payload.len() != 128 + p.ticket.encoded_bytes() {
                    return Err(SourceError::InvalidFrame);
                }
                session.supply(&p.ticket, &payload[128..])?;
            }
            8 => {
                if payload.len() != 128 {
                    return Err(SourceError::InvalidFrame);
                }
                let p = checked(pending, payload, seq)?;
                session.release_read(&p.ticket)?;
                *pending = None;
            }
            41 => {
                if payload.len() != 128 {
                    return Err(SourceError::InvalidFrame);
                }
                let p = checked(pending, payload, seq)?;
                session.acknowledge_write(&p.ticket)?;
                *pending = None;
            }
            9 => {
                if !payload.is_empty() {
                    return Err(SourceError::InvalidFrame);
                }
                session.cancel();
            }
            _ => return Err(SourceError::InvalidFrame),
        },
        Owned::Query {
            session,
            owner,
            sequence,
            pending,
            result,
            ..
        } => match command {
            6 => {
                if !payload.is_empty() {
                    return Err(SourceError::InvalidFrame);
                }
                if owner
                    .transition
                    .lock()
                    .map_err(|_| SourceError::ResourceLimit)?
                    .0
                    != *sequence
                {
                    return Err(SourceError::StaleSource);
                }
                if let Some(value) = result {
                    complete(&mut out, value)
                } else {
                    match session.step()? {
                        GeoHierarchyStep::NeedRead(t) => {
                            save(pending, t);
                            put32(&mut out, 8, 1);
                            out[64..192]
                                .copy_from_slice(&wire(&pending.as_ref().unwrap().ticket, seq));
                        }
                        GeoHierarchyStep::AwaitRelease => {
                            put32(&mut out, 8, 2);
                            if let Some(p) = pending {
                                out[64..192].copy_from_slice(&wire(&p.ticket, seq));
                            }
                        }
                        GeoHierarchyStep::Complete => {
                            *result = Some(Box::new(session.finish()?));
                            complete(&mut out, result.as_ref().unwrap());
                        }
                        decision @ (GeoHierarchyStep::FullScanFrontier
                        | GeoHierarchyStep::FullScanWork) => {
                            let reason = if matches!(decision, GeoHierarchyStep::FullScanFrontier) {
                                1
                            } else {
                                2
                            };
                            put32(&mut out, 8, 10);
                            put32(&mut out, 48, reason);
                        }
                        GeoHierarchyStep::Cancelled => put32(&mut out, 8, 9),
                        _ => return Err(SourceError::InvalidFrame),
                    }
                }
            }
            7 => {
                let p = checked(pending, payload, seq)?;
                if payload.len() != 128 + p.ticket.encoded_bytes() {
                    return Err(SourceError::InvalidFrame);
                }
                session.supply(&p.ticket, &payload[128..])?;
            }
            8 => {
                if payload.len() != 128 {
                    return Err(SourceError::InvalidFrame);
                }
                let p = checked(pending, payload, seq)?;
                session.release_read(&p.ticket)?;
                *pending = None;
            }
            9 => {
                if !payload.is_empty() {
                    return Err(SourceError::InvalidFrame);
                }
                session.cancel();
                *result = None;
            }
            _ => return Err(SourceError::InvalidFrame),
        },
    }
    Ok(out)
}
pub(super) fn write_bytes<'a>(
    entry: &'a Entry,
    b: &[u8],
    budget: usize,
) -> Result<(&'a [u8], &'a AtomicU8)> {
    let Entry::Hierarchy(Owned::Build {
        session,
        sequence,
        pending,
        ..
    }) = entry
    else {
        return Err(SourceError::InvalidFrame);
    };
    if u64at(b, 24) != *sequence || b.len() != HEADER + 128 {
        return Err(SourceError::StaleSource);
    }
    let p = checked(pending, &b[HEADER..], *sequence)?;
    let bytes = session.write_bytes(&p.ticket)?;
    if bytes.len().checked_mul(3).is_none_or(|n| n > budget) {
        return Err(SourceError::ResourceLimit);
    }
    Ok((bytes, &p.copies))
}
