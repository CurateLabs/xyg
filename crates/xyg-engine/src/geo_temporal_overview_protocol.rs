//! Private child of retained-source framing; shares its registry and admission.
use super::*;
use crate::geo_temporal_overview::{
    GeoOverviewError, GeoOverviewQuerySession, GeoOverviewResult, GeoOverviewStep,
    GeoOverviewTicket, ValidatedGeoOverview,
};
use crate::geo_temporal_overview_build::GeoOverviewBuildSession;

pub(super) struct Semantic {
    pub result: Arc<GeoOverviewResult>,
    pub camera: GeoViewport,
    pub sequence: u64,
}
pub(super) struct Pending {
    ticket: GeoOverviewTicket,
    copies: AtomicU8,
}
pub(super) enum Owned {
    Build {
        session: Box<GeoOverviewBuildSession>,
        sequence: u64,
        pending: Option<Pending>,
        _lease: GeoProcessorLease,
    },
    Index {
        value: Arc<ValidatedGeoOverview>,
        sequence: u64,
        _lease: GeoProcessorLease,
    },
    Query {
        session: Box<GeoOverviewQuerySession>,
        sequence: u64,
        camera: GeoViewport,
        pending: Option<Pending>,
        result: Option<Arc<GeoOverviewResult>>,
        _lease: GeoProcessorLease,
    },
}
impl Owned {
    pub(super) fn is_session(&self) -> bool {
        matches!(self, Self::Build { .. } | Self::Query { .. })
    }
}
fn error(e: GeoOverviewError) -> SourceError {
    match e {
        GeoOverviewError::Source(e) => e,
        GeoOverviewError::UnsupportedDomain => SourceError::InvalidFrame,
    }
}
fn wire(t: &GeoOverviewTicket, sequence: u64) -> [u8; 128] {
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
fn checked<'a>(pending: &'a Option<Pending>, payload: &[u8], sequence: u64) -> Result<&'a Pending> {
    let p = pending.as_ref().ok_or(SourceError::StaleSource)?;
    if payload.len() < 128 || payload[..128] != wire(&p.ticket, sequence) {
        return Err(SourceError::StaleSource);
    }
    Ok(p)
}
fn save(pending: &mut Option<Pending>, t: GeoOverviewTicket) {
    if pending.as_ref().is_none_or(|p| !p.ticket.same(&t)) {
        *pending = Some(Pending {
            ticket: t,
            copies: AtomicU8::new(0),
        });
    }
}
fn sessions(r: &Registry) -> usize {
    r.entries.iter().filter(|(_, e)| is_session(e)).count()
}
pub(super) fn is_session(e: &Entry) -> bool {
    matches!(
        e,
        Entry::Session(_)
            | Entry::Members(_)
            | Entry::Rows(_)
            | Entry::IndexBuild(_)
            | Entry::Indexed(_)
    ) || matches!(e,Entry::Hierarchy(h) if h.is_session())
        || matches!(e,Entry::Overview(o) if o.is_session())
}
pub(super) fn start(r: &mut Registry, request: &[u8]) -> Result<[u8; HEADER]> {
    let command = u32at(request, 8);
    let handle = u64at(request, 16);
    let sequence = u64at(request, 24);
    let payload = &request[HEADER..];
    if sequence == 0 {
        return Err(SourceError::StaleSource);
    }
    if command != 29 && sessions(r) >= MAX_SESSIONS {
        return Err(SourceError::ResourceLimit);
    }
    let entry = &r
        .entries
        .iter()
        .find(|(id, _)| *id == handle)
        .ok_or(SourceError::StaleSource)?
        .1;
    if command == 27 {
        if payload.len() != 8 {
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
        // The temporal index retains canonical source authority, not sparse
        // selected intent/counts (§34). Empty intent is still selected authority.
        if s.result.selection.is_some() || s.scope.is_some() {
            let mut out = reply(handle, sequence);
            put32(&mut out, 8, 17);
            return Ok(out);
        }
        let lease = GeoProcessorLease::acquire(4096)?;
        let session = GeoOverviewBuildSession::new(&s.source, budget(request)?, u64at(payload, 0))
            .map_err(error)?;
        let id = insert(
            r,
            Entry::Overview(Owned::Build {
                session: Box::new(session),
                sequence,
                pending: None,
                _lease: lease,
            }),
        )?;
        return Ok(reply(id, sequence));
    }
    if command == 28 {
        if !payload.is_empty()
            || u32at(request, 12) > 1
            || u32at(request, 68) != 0
            || u32at(request, 72) != 0
            || u32at(request, 76) != 0
            || u64at(request, 224) != 0
        {
            return Err(SourceError::InvalidFrame);
        }
        let Entry::Overview(Owned::Index { value, .. }) = entry else {
            return Err(SourceError::InvalidFrame);
        };
        let limits = budget(request)?;
        // Two boundary paths, at most twelve pages each. This conservative
        // admission prevents discovering a caller work limit after issuing I/O.
        if limits.processor_bytes
            < value
                .source()
                .clone_reserved_bytes()
                .checked_add(16_384 + (1 << 20))
                .ok_or(SourceError::ResourceLimit)?
            || limits.max_chunks < 24
            || limits.max_read_bytes < 24 * 65536
        {
            return Err(SourceError::ResourceLimit);
        }
        let camera = camera(request)?;
        let snapshot = GeoOperationSnapshot {
            source_digest: request[136..144].try_into().unwrap(),
            generation: u64at(request, 144),
            camera: camera.rebuild_key()?,
            time: time(request)?,
            layer_id: u64at(request, 152),
            camera_revision: u64at(request, 160),
            time_revision: u64at(request, 168),
            layer_revision: u64at(request, 176),
            style_revision: u64at(request, 184),
            state_revision: u64at(request, 192),
        };
        let lease = GeoProcessorLease::acquire(4096)?;
        // Each query is immutable and independent; no mutable index transition is claimed.
        let session =
            GeoOverviewQuerySession::new(Arc::clone(value), snapshot, camera).map_err(error)?;
        let id = insert(
            r,
            Entry::Overview(Owned::Query {
                session: Box::new(session),
                sequence,
                camera,
                pending: None,
                result: None,
                _lease: lease,
            }),
        )?;
        return Ok(reply(id, sequence));
    }
    if command != 29 || !payload.is_empty() {
        return Err(SourceError::InvalidFrame);
    }
    if r.entries
        .iter()
        .filter(|(_, e)| matches!(e, Entry::Data { .. }))
        .count()
        >= MAX_DATA_HANDLES
    {
        return Err(SourceError::ResourceLimit);
    }
    let Entry::Overview(Owned::Query {
        result: Some(result),
        camera,
        sequence: expected,
        ..
    }) = entry
    else {
        return Err(SourceError::StaleSource);
    };
    if sequence != *expected {
        return Err(SourceError::StaleSource);
    }
    let result = Arc::clone(result);
    let camera = *camera;
    let scratch = crate::geo_temporal_overview_scene::SCRATCH_BYTES;
    if budget(request)?.processor_bytes
        < result
            .source()
            .clone_reserved_bytes()
            .checked_add(scratch + 16_384 * 2 + 262_144 + 8192)
            .ok_or(SourceError::ResourceLimit)?
    {
        return Err(SourceError::ResourceLimit);
    }
    let _phase = GeoProcessorLease::acquire(scratch)?;
    let lease = reserve_data(r, crate::geo_temporal_overview_scene::DATA_CREDIT)?;
    let encoded = (|| {
        let scene = crate::geo_temporal_overview_scene::compile(&result, camera)?;
        let mut out = vec![0; HEADER + 2048 + scene.len()];
        out[..4].copy_from_slice(b"XYOV");
        put32(&mut out, 4, 1);
        put32(&mut out, 8, 3);
        put32(&mut out, 12, 16);
        put64(&mut out, 16, handle);
        put64(&mut out, 24, sequence);
        put64(&mut out, 32, scene.len() as u64);
        put64(&mut out, 40, 2048);
        out[48..56].copy_from_slice(&result.overview_digest());
        let s = result.snapshot();
        put64(&mut out, 56, s.generation);
        out[64..72].copy_from_slice(&s.source_digest);
        put32(&mut out, 72, result.source().crs() as u32);
        put32(&mut out, 76, result.source().geometry() as u32);
        put64(&mut out, 80, s.layer_id);
        put64(&mut out, 88, result.source().rows());
        put32(&mut out, 96, s.camera.crs as u32);
        put32(&mut out, 100, u32::from(s.camera.world_wrap));
        for (i, bits) in [
            s.camera.center_x_bits,
            s.camera.center_y_bits,
            s.camera.zoom_bits,
            s.camera.width_bits,
            s.camera.height_bits,
            s.camera.bearing_deg_bits,
            s.camera.pitch_deg_bits,
        ]
        .into_iter()
        .enumerate()
        {
            put64(&mut out, 112 + i * 8, bits);
        }
        for (i, revision) in [
            s.camera_revision,
            s.time_revision,
            s.layer_revision,
            s.style_revision,
            s.state_revision,
        ]
        .into_iter()
        .enumerate()
        {
            put64(&mut out, 176 + i * 8, revision);
        }
        match s.time {
            TimePredicate::All => {}
            TimePredicate::Instant(t) => {
                put32(&mut out, 224, 1);
                put64(&mut out, 232, t as u64);
            }
            TimePredicate::Window { start, end } => {
                put32(&mut out, 224, 2);
                put64(&mut out, 232, start as u64);
                put64(&mut out, 240, end as u64);
            }
        }
        for (i, &count) in result.counts().iter().enumerate() {
            put64(&mut out, HEADER + i * 8, count);
        }
        out[HEADER + 2048..].copy_from_slice(&scene);
        if out.len() * 4 > crate::geo_temporal_overview_scene::DATA_CREDIT {
            return Err(SourceError::ResourceLimit);
        }
        Ok(out)
    })();
    let bytes = match encoded {
        Ok(v) => v,
        Err(e) => {
            drop(lease);
            if !r
                .entries
                .iter()
                .any(|(_, e)| matches!(e, Entry::Data { .. }))
            {
                r.data_cache = None;
            }
            return Err(e);
        }
    };
    let length = bytes.len();
    let id = insert(
        r,
        Entry::Data {
            bytes,
            _lease: lease,
            reads: AtomicU8::new(0),
            semantic: None,
            rows: None,
            overview: Some(Box::new(Semantic {
                result,
                camera,
                sequence,
            })),
        },
    )?;
    let mut out = reply(id, sequence);
    put32(&mut out, 8, 16);
    put64(&mut out, 32, length as u64);
    put64(&mut out, 40, handle);
    Ok(out)
}
pub(super) fn operation(r: &mut Registry, index: usize, request: &[u8]) -> Result<[u8; HEADER]> {
    let command = u32at(request, 8);
    let handle = u64at(request, 16);
    let sequence = u64at(request, 24);
    let payload = &request[HEADER..];
    let mut out = reply(handle, sequence);
    let Entry::Overview(owned) = &mut r.entries[index].1 else {
        return Err(SourceError::InvalidFrame);
    };
    let expected = match owned {
        Owned::Build { sequence, .. }
        | Owned::Index { sequence, .. }
        | Owned::Query { sequence, .. } => *sequence,
    };
    if sequence != expected {
        return Err(SourceError::StaleSource);
    }
    if command == 10 {
        if !payload.is_empty() {
            return Err(SourceError::InvalidFrame);
        }
        match owned {
            Owned::Build {
                session, pending, ..
            } => {
                session.cancel();
                if pending.is_some() {
                    put32(&mut out, 8, 2);
                    return Ok(out);
                }
            }
            Owned::Query {
                session, pending, ..
            } => {
                session.cancel();
                if pending.is_some() {
                    put32(&mut out, 8, 2);
                    return Ok(out);
                }
            }
            Owned::Index { .. } => {}
        }
        r.entries.remove(index);
        return Ok(out);
    }
    match owned {
        Owned::Index { value, .. } => {
            if command != 6 || !payload.is_empty() {
                return Err(SourceError::InvalidFrame);
            }
            put32(&mut out, 8, 13);
            out[40..48].copy_from_slice(&value.digest());
            put64(&mut out, 48, value.storage_namespace());
        }
        Owned::Build {
            session,
            pending,
            _lease,
            ..
        } => match command {
            6 => {
                if !payload.is_empty() {
                    return Err(SourceError::InvalidFrame);
                }
                match session.step().map_err(error)? {
                    GeoOverviewStep::NeedRead(t) | GeoOverviewStep::NeedWrite(t) => {
                        let write = t.kind() == 3;
                        save(pending, t);
                        put32(&mut out, 8, if write { 7 } else { 1 });
                        out[64..192]
                            .copy_from_slice(&wire(&pending.as_ref().unwrap().ticket, sequence));
                    }
                    GeoOverviewStep::AwaitRelease => {
                        put32(&mut out, 8, 2);
                        if let Some(p) = pending {
                            out[64..192].copy_from_slice(&wire(&p.ticket, sequence));
                        }
                    }
                    GeoOverviewStep::Complete => {
                        let value = session.take_index().map_err(error)?;
                        out[40..48].copy_from_slice(&value.digest());
                        put64(&mut out, 48, value.storage_namespace());
                        let lease = std::mem::replace(_lease, GeoProcessorLease::acquire(0)?);
                        *owned = Owned::Index {
                            value,
                            sequence,
                            _lease: lease,
                        };
                        put32(&mut out, 8, 13);
                    }
                    GeoOverviewStep::Cancelled => put32(&mut out, 8, 9),
                    GeoOverviewStep::UnsupportedDomain => put32(&mut out, 8, 15),
                }
            }
            7 => {
                let p = checked(pending, payload, sequence)?;
                if payload.len() != 128 + p.ticket.encoded_bytes() {
                    return Err(SourceError::InvalidFrame);
                }
                session.supply(&p.ticket, &payload[128..]).map_err(error)?;
            }
            8 => {
                if payload.len() != 128 {
                    return Err(SourceError::InvalidFrame);
                }
                let p = checked(pending, payload, sequence)?;
                session.release_read(&p.ticket).map_err(error)?;
                *pending = None;
            }
            31 => {
                if payload.len() != 128 {
                    return Err(SourceError::InvalidFrame);
                }
                let p = checked(pending, payload, sequence)?;
                session.ack_write(&p.ticket).map_err(error)?;
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
            pending,
            result,
            ..
        } => match command {
            6 => {
                if !payload.is_empty() {
                    return Err(SourceError::InvalidFrame);
                }
                if result.is_some() {
                    put32(&mut out, 8, 14);
                } else {
                    match session.step().map_err(error)? {
                        GeoOverviewStep::NeedRead(t) => {
                            save(pending, t);
                            put32(&mut out, 8, 1);
                            out[64..192].copy_from_slice(&wire(
                                &pending.as_ref().unwrap().ticket,
                                sequence,
                            ));
                        }
                        GeoOverviewStep::AwaitRelease => {
                            put32(&mut out, 8, 2);
                            if let Some(p) = pending {
                                out[64..192].copy_from_slice(&wire(&p.ticket, sequence));
                            }
                        }
                        GeoOverviewStep::Complete => {
                            *result = Some(Arc::new(session.take_result().map_err(error)?));
                            put32(&mut out, 8, 14);
                        }
                        GeoOverviewStep::Cancelled => put32(&mut out, 8, 9),
                        _ => return Err(SourceError::InvalidFrame),
                    }
                }
            }
            7 => {
                let p = checked(pending, payload, sequence)?;
                if payload.len() != 128 + p.ticket.encoded_bytes() {
                    return Err(SourceError::InvalidFrame);
                }
                session.supply(&p.ticket, &payload[128..]).map_err(error)?;
            }
            8 => {
                if payload.len() != 128 {
                    return Err(SourceError::InvalidFrame);
                }
                let p = checked(pending, payload, sequence)?;
                session.release_read(&p.ticket).map_err(error)?;
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
    request: &[u8],
    budget: usize,
) -> Result<(&'a [u8], &'a AtomicU8)> {
    let Entry::Overview(Owned::Build {
        session,
        sequence,
        pending,
        ..
    }) = entry
    else {
        return Err(SourceError::InvalidFrame);
    };
    let payload = &request[HEADER..];
    if payload.len() != 128 || u64at(request, 24) != *sequence {
        return Err(SourceError::StaleSource);
    }
    let p = checked(pending, payload, *sequence)?;
    let bytes = session.write_bytes(&p.ticket).map_err(error)?;
    if bytes.len().checked_mul(4).is_none_or(|n| n > budget) {
        return Err(SourceError::ResourceLimit);
    }
    Ok((bytes, &p.copies))
}
