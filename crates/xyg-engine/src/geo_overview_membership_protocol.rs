//! Private exact domain-member child; shares retained registry and memory pools.
use super::*;
use crate::geo_temporal_overview_membership::{
    GeoOverviewMembershipSession, GeoOverviewMembershipStep, GeoOverviewMembershipTicket,
    GeoPublishedOverviewMembership,
};
const CONTROL: usize = 4096;
pub(super) struct Query {
    session: Box<GeoOverviewMembershipSession>,
    pending: Option<GeoOverviewMembershipTicket>,
    sequence: u64,
    control: GeoProcessorLease,
}
pub(super) struct Data {
    page: GeoPublishedOverviewMembership,
    bytes: Vec<u8>,
    reads: AtomicU8,
    _derived: GeoDerivedLease,
    _control: GeoProcessorLease,
}
pub(super) enum Owned {
    Query(Box<Query>),
    Data(Box<Data>),
}
impl Owned {
    pub(super) fn is_session(&self) -> bool {
        matches!(self, Self::Query(_))
    }
    pub(super) fn is_data(&self) -> bool {
        matches!(self, Self::Data(_))
    }
}
fn wire(t: &GeoOverviewMembershipTicket) -> [u8; 128] {
    let mut b = [0; 128];
    let r = t.request();
    put64(&mut b, 0, t.owner());
    put64(&mut b, 8, t.serial());
    put64(&mut b, 16, t.sequence());
    put32(&mut b, 24, 1);
    put64(&mut b, 32, r.generation);
    put32(&mut b, 40, r.chunk_index);
    put32(&mut b, 44, r.rows);
    put64(&mut b, 48, r.first_row);
    put64(&mut b, 56, r.encoded_bytes as u64);
    b[64..72].copy_from_slice(&r.digest);
    b
}
fn checked<'a>(
    pending: &'a Option<GeoOverviewMembershipTicket>,
    payload: &[u8],
) -> Result<&'a GeoOverviewMembershipTicket> {
    let t = pending.as_ref().ok_or(SourceError::StaleSource)?;
    if payload.len() < 128 || payload[..128] != wire(t) {
        return Err(SourceError::StaleSource);
    }
    Ok(t)
}
fn length(page: &GeoPublishedOverviewMembership) -> usize {
    HEADER + page.records().len() * 32
}
fn complete(handle: u64, page: &GeoPublishedOverviewMembership) -> [u8; HEADER] {
    let mut out = reply(handle, page.sequence());
    put32(&mut out, 8, 21);
    put64(&mut out, 32, page.records().len() as u64);
    put64(&mut out, 40, page.result().counts()[page.cell() as usize]);
    put64(&mut out, 48, page.cumulative_vertices());
    put32(&mut out, 56, u32::from(!page.complete()));
    let s = page.stats();
    put64(&mut out, 64, s.rows_examined);
    put64(&mut out, 72, s.bytes_read);
    put32(&mut out, 80, s.chunks_read as u32);
    put32(&mut out, 84, s.chunks_considered as u32);
    out
}
fn data_reply(handle: u64, data: &Data) -> [u8; HEADER] {
    let mut out = reply(handle, data.page.sequence());
    put64(&mut out, 32, data.bytes.len() as u64);
    put64(&mut out, 40, handle);
    out
}
fn encode(handle: u64, page: &GeoPublishedOverviewMembership) -> Result<Vec<u8>> {
    let result = page.result();
    let source = result.source();
    let s = page.snapshot();
    let mut out = vec![0; length(page)];
    out[..4].copy_from_slice(b"XYOM");
    put32(&mut out, 4, 1);
    put32(&mut out, 8, 3);
    put32(&mut out, 12, 16);
    put64(&mut out, 16, handle);
    put64(&mut out, 24, page.sequence());
    put64(&mut out, 32, page.records().len() as u64);
    put32(&mut out, 40, page.cell() as u32);
    put32(&mut out, 44, u32::from(!page.complete()));
    put64(&mut out, 48, result.counts()[page.cell() as usize]);
    put64(&mut out, 56, page.cumulative_vertices());
    put64(&mut out, 64, source.rows());
    put64(&mut out, 72, s.generation);
    out[80..88].copy_from_slice(&s.source_digest);
    out[88..96].copy_from_slice(&page.overview_digest());
    put64(&mut out, 96, s.layer_id);
    put32(&mut out, 104, source.crs() as u32);
    put32(&mut out, 108, source.geometry() as u32);
    put32(&mut out, 112, s.camera.crs as u32);
    put32(&mut out, 116, u32::from(s.camera.world_wrap));
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
        put64(&mut out, 120 + i * 8, bits);
    }
    for (i, v) in [
        s.camera_revision,
        s.time_revision,
        s.layer_revision,
        s.style_revision,
        s.state_revision,
    ]
    .into_iter()
    .enumerate()
    {
        put64(&mut out, 176 + i * 8, v);
    }
    match s.time {
        TimePredicate::All => {}
        TimePredicate::Instant(t) => {
            put32(&mut out, 216, 1);
            put64(&mut out, 224, t as u64);
        }
        TimePredicate::Window { start, end } => {
            put32(&mut out, 216, 2);
            put64(&mut out, 224, start as u64);
            put64(&mut out, 232, end as u64);
        }
    }
    let mut sum = 0u64;
    for (i, r) in page.records().iter().enumerate() {
        let p = HEADER + i * 32;
        put64(&mut out, p, r.feature.feature_id);
        put64(&mut out, p + 8, r.feature.source_row);
        put32(&mut out, p + 16, r.feature.chunk_index);
        put32(&mut out, p + 20, r.feature.row);
        put64(&mut out, p + 24, r.matched_vertices);
        sum = sum
            .checked_add(r.matched_vertices)
            .ok_or(SourceError::ResourceLimit)?;
    }
    put64(&mut out, 240, sum);
    Ok(out)
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
    if command == 45 {
        if payload.len() != 24
            || u32at(payload, 8) >= 256
            || u32at(payload, 12) != 0
            || u64at(payload, 0) == 0
        {
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
        let entry = &r.entries[index].1;
        let (result, previous) = match entry {
            Entry::Data {
                overview: Some(s), ..
            } if s.sequence == sequence => (Arc::clone(&s.result), None),
            Entry::OverviewMembers(Owned::Data(d)) if d.page.sequence() == sequence => {
                (Arc::clone(d.page.result()), Some(&d.page))
            }
            Entry::Data {
                overview: Some(_), ..
            }
            | Entry::OverviewMembers(Owned::Data(_)) => return Err(SourceError::StaleSource),
            _ => return Err(SourceError::InvalidFrame),
        };
        let mut limits = budget(request)?;
        limits.processor_bytes = limits
            .processor_bytes
            .checked_sub(CONTROL)
            .ok_or(SourceError::ResourceLimit)?;
        let control = GeoProcessorLease::acquire(CONTROL)?;
        let session = GeoOverviewMembershipSession::create(
            result,
            u32at(payload, 8) as u16,
            u64at(payload, 0),
            previous,
            limits,
            u64at(payload, 16),
        )?;
        let seq = session.current_sequence();
        let id = insert(
            r,
            Entry::OverviewMembers(Owned::Query(Box::new(Query {
                session: Box::new(session),
                pending: None,
                sequence: seq,
                control,
            }))),
        )?;
        return Ok(reply(id, seq));
    }
    if command != 46 || !payload.is_empty() {
        return Err(SourceError::InvalidFrame);
    }
    admit_data_slot(r)?;
    let Entry::OverviewMembers(Owned::Query(q)) = &r.entries[index].1 else {
        return Err(SourceError::InvalidFrame);
    };
    if q.sequence != sequence {
        return Err(SourceError::StaleSource);
    }
    if q.pending.is_some() || q.session.has_outstanding_reads() {
        return Err(SourceError::StaleSource);
    }
    let page = q.session.published().ok_or(SourceError::StaleSource)?;
    let reserve = length(page)
        .checked_mul(4)
        .and_then(|n| n.checked_add(CONTROL))
        .ok_or(SourceError::ResourceLimit)?;
    let held = q
        .session
        .retained_bytes()
        .checked_add(q.control.bytes())
        .ok_or(SourceError::ResourceLimit)?;
    let cache = if r.data_cache.is_none() { 1 << 20 } else { 0 };
    let limit = budget(request)?.processor_bytes;
    if held
        .checked_add(reserve)
        .and_then(|n| n.checked_add(cache))
        .is_none_or(|n| n > limit)
    {
        return Err(SourceError::ResourceLimit);
    }
    // All credits precede encode. A failure retains the completed query unchanged.
    let derived = reserve_data(r, reserve)?;
    let Entry::OverviewMembers(Owned::Query(q)) = &r.entries[index].1 else {
        unreachable!()
    };
    let bytes = match encode(handle, q.session.published().unwrap()) {
        Ok(b) => b,
        Err(e) => {
            drop(derived);
            if !r.entries.iter().any(|(_, e)| is_data_entry(e)) {
                r.data_cache = None;
            }
            return Err(e);
        }
    };
    let Entry::OverviewMembers(Owned::Query(q)) = &mut r.entries[index].1 else {
        unreachable!()
    };
    let empty_control = GeoProcessorLease::acquire(0)?;
    let page = q.session.take_page().unwrap();
    let control = std::mem::replace(&mut q.control, empty_control);
    let data = Box::new(Data {
        page,
        bytes,
        reads: AtomicU8::new(0),
        _derived: derived,
        _control: control,
    });
    let out = data_reply(handle, &data);
    r.entries[index].1 = Entry::OverviewMembers(Owned::Data(data));
    Ok(out)
}
pub(super) fn operation(r: &mut Registry, index: usize, request: &[u8]) -> Result<[u8; HEADER]> {
    let command = u32at(request, 8);
    let handle = u64at(request, 16);
    let sequence = u64at(request, 24);
    let payload = &request[HEADER..];
    let Entry::OverviewMembers(owned) = &mut r.entries[index].1 else {
        return Err(SourceError::InvalidFrame);
    };
    if let Owned::Data(d) = owned {
        if !payload.is_empty() {
            return Err(SourceError::InvalidFrame);
        }
        if command == 10 {
            if sequence != 0 {
                return Err(SourceError::InvalidFrame);
            }
            r.entries.remove(index);
            if !r.entries.iter().any(|(_, e)| is_data_entry(e)) {
                r.data_cache = None;
            }
            return Ok(reply(handle, 0));
        }
        if command != 6 {
            return Err(SourceError::InvalidFrame);
        }
        if sequence != d.page.sequence() {
            return Err(SourceError::StaleSource);
        }
        return Ok(data_reply(handle, d));
    }
    let Owned::Query(q) = owned else {
        unreachable!()
    };
    if sequence != q.sequence {
        return Err(SourceError::StaleSource);
    }
    let mut out = reply(handle, sequence);
    match command {
        6 => {
            if !payload.is_empty() {
                return Err(SourceError::InvalidFrame);
            }
            if let Some(page) = q.session.published() {
                return Ok(complete(handle, page));
            }
            let step = q.session.step()?;
            let need = matches!(&step, GeoOverviewMembershipStep::NeedRead(_));
            match step {
                GeoOverviewMembershipStep::NeedRead(t)
                | GeoOverviewMembershipStep::AwaitRelease(t) => {
                    if let Some(old) = &q.pending {
                        if wire(old) != wire(&t) {
                            return Err(SourceError::StaleSource);
                        }
                    } else {
                        q.pending = Some(t);
                    }
                    put32(&mut out, 8, if need { 1 } else { 2 });
                    out[64..192].copy_from_slice(&wire(q.pending.as_ref().unwrap()));
                }
                GeoOverviewMembershipStep::Complete => {
                    return Ok(complete(handle, q.session.published().unwrap()));
                }
                GeoOverviewMembershipStep::Cancelled | GeoOverviewMembershipStep::Disposed => {
                    put32(&mut out, 8, 9);
                }
            }
        }
        7 => {
            let t = checked(&q.pending, payload)?;
            if payload.len() != 128 + t.request().encoded_bytes {
                return Err(SourceError::InvalidFrame);
            }
            q.session.supply(t, &payload[128..], &mut || false)?;
        }
        8 => {
            if payload.len() != 128 {
                return Err(SourceError::InvalidFrame);
            }
            let t = checked(&q.pending, payload)?;
            q.session.release_read(t)?;
            q.pending = None;
        }
        9 | 10 => {
            if !payload.is_empty() {
                return Err(SourceError::InvalidFrame);
            }
            if command == 10 {
                q.session.dispose()?;
            } else {
                q.session.cancel(sequence)?;
            }
            if let Some(ticket) = &q.pending {
                put32(&mut out, 8, 2);
                out[64..192].copy_from_slice(&wire(ticket));
            } else if command == 10 {
                r.entries.remove(index);
            } else {
                put32(&mut out, 8, 9);
            }
        }
        _ => return Err(SourceError::InvalidFrame),
    }
    Ok(out)
}
pub(super) fn read_bytes<'a>(
    entry: &'a Entry,
    request: &[u8],
    budget: usize,
) -> Result<(&'a [u8], &'a AtomicU8)> {
    let Entry::OverviewMembers(Owned::Data(d)) = entry else {
        return Err(SourceError::InvalidFrame);
    };
    if request.len() != HEADER || u64at(request, 24) != d.page.sequence() {
        return Err(SourceError::StaleSource);
    }
    let held = d
        .page
        .reserved_bytes()
        .checked_add(d._control.bytes())
        .ok_or(SourceError::ResourceLimit)?;
    if d.bytes
        .len()
        .checked_mul(4)
        .and_then(|n| n.checked_add(held))
        .is_none_or(|n| n > budget)
    {
        return Err(SourceError::ResourceLimit);
    }
    Ok((&d.bytes, &d.reads))
}
