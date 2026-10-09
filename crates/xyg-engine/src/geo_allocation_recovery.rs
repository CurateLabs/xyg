//! Opt-in durable allocation receipts. Dossier §27/§29: no extra handle or pool.
use super::*;
const SLOTS: usize = 16;
const CONTROL: usize = 8192;
const MAX_REQUEST: usize = HEADER + 24;
#[derive(Clone, Copy, PartialEq, Eq)]
struct Birth {
    issuer: u64,
    command: u32,
    nonce: u64,
    sequence: u64,
    target: u64,
}
struct Receipt {
    birth: Birth,
    request: Vec<u8>,
    reply: [u8; HEADER],
    confirmed: bool,
    _lease: GeoProcessorLease,
}
#[derive(Clone, Copy)]
struct Stamp {
    birth: Birth,
    confirmed: bool,
    forgotten: bool,
}
pub(super) struct Bank {
    receipts: [Option<Receipt>; SLOTS],
    stamps: [Option<Stamp>; SLOTS],
    control: Option<GeoProcessorLease>,
}
const _: () = assert!(std::mem::size_of::<Bank>() <= CONTROL);
impl Default for Bank {
    fn default() -> Self {
        Self {
            receipts: std::array::from_fn(|_| None),
            stamps: [None; SLOTS],
            control: None,
        }
    }
}
fn allocation_live(r: &Registry, b: Birth) -> bool {
    r.recovery.stamps.iter().flatten().any(|s| s.birth == b) && phase_live(r, b)
}
fn phase_live(r: &Registry, b: Birth) -> bool {
    r.entries.iter().any(|(id, e)| {
        *id == b.target
            && match b.command {
                26 => matches!(e, Entry::Data { .. }),
                27 => matches!(
                    e,
                    Entry::Overview(overview::Owned::Build { .. } | overview::Owned::Index { .. })
                ),
                28 => matches!(e, Entry::Overview(overview::Owned::Query { .. })),
                29 => matches!(
                    e,
                    Entry::Data {
                        overview: Some(_),
                        ..
                    }
                ),
                35 => matches!(e, Entry::Session(s) if s.operation_live(b.sequence)),
                36 => matches!(e, Entry::Indexed(q) if q.selected_replacement && q.sequence == b.sequence && (q.published.is_some() || q.session.as_ref().is_some_and(GeoIndexedQuerySession::operation_live))),
                45 => matches!(e, Entry::OverviewMembers(o) if o.is_session()),
                _ => false,
            }
    })
}
fn issuer_live(r: &Registry, b: Birth) -> bool {
    r.entries.iter().any(|(id, e)| {
        *id == b.issuer
            && match b.command {
                26 => matches!(e, Entry::Data { .. }),
                27 => matches!(
                    e,
                    Entry::Data {
                        semantic: Some(_),
                        ..
                    }
                ),
                28 => matches!(e, Entry::Overview(overview::Owned::Index { .. })),
                29 => matches!(e, Entry::Overview(overview::Owned::Query { .. })),
                35 => matches!(e, Entry::Session(_)),
                36 => matches!(e, Entry::Index(_)),
                45 => {
                    matches!(
                        e,
                        Entry::Data {
                            overview: Some(_),
                            ..
                        }
                    ) || matches!(e, Entry::OverviewMembers(o) if o.is_data())
                }
                _ => false,
            }
    })
}
fn retired(sequence: u64) -> [u8; HEADER] {
    let mut out = reply(0, sequence);
    put32(&mut out, 8, 22);
    out
}
pub(super) fn execute(r: &mut Registry, request: &[u8]) -> Result<[u8; HEADER]> {
    let command = u32at(request, 8);
    let nonce = u64at(request, 240);
    if command == 47 {
        return confirm(r, request);
    }
    if request.len() > MAX_REQUEST || nonce == 0 {
        return Err(SourceError::InvalidFrame);
    }
    let issuer = u64at(request, 16);
    let slot = r.recovery.receipts.iter().position(|v| {
        v.as_ref()
            .is_some_and(|v| v.birth.issuer == issuer && v.birth.command == command)
    });
    if let Some(i) = slot {
        let old = r.recovery.receipts[i].as_ref().unwrap();
        if nonce < old.birth.nonce || (nonce == old.birth.nonce && request != old.request) {
            return Err(SourceError::StaleSource);
        }
        if nonce == old.birth.nonce {
            return Ok(if allocation_live(r, old.birth) {
                old.reply
            } else {
                retired(old.birth.sequence)
            });
        }
        if !old.confirmed {
            return Err(SourceError::StaleSource);
        }
    }
    let slot = slot
        .or_else(|| r.recovery.receipts.iter().position(Option::is_none))
        .ok_or(SourceError::ResourceLimit)?;
    // Retired births retain exact cleanup authority until their ACK. Admission
    // must reserve a stamp BEFORE the canonical mutation, including same-handle29.
    let stamp = r
        .recovery
        .stamps
        .iter()
        .position(Option::is_none)
        .ok_or(SourceError::ResourceLimit)?;
    // Prelease controls, exact request and four-copy transfer allowance BEFORE allocation.
    let credit = request
        .len()
        .checked_mul(4)
        .and_then(|n| n.checked_add(512))
        .ok_or(SourceError::ResourceLimit)?;
    let held = CONTROL
        + r.recovery
            .receipts
            .iter()
            .flatten()
            .map(|v| v._lease.bytes())
            .sum::<usize>();
    let limit = budget(request)?
        .processor_bytes
        .checked_sub(held + credit)
        .ok_or(SourceError::ResourceLimit)?;
    let control = if r.recovery.control.is_none() {
        Some(GeoProcessorLease::acquire(CONTROL)?)
    } else {
        None
    };
    let lease = GeoProcessorLease::acquire(credit)?;
    let raw = request.to_vec();
    let mut admitted = raw.clone();
    put64(&mut admitted, 32, limit as u64);
    let out = execute_locked(r, &admitted)?;
    // Unsupported-selected/fallback receipts are not successful allocations.
    if !matches!(u32at(&out, 8), 0 | 16) {
        return Ok(out);
    }
    let birth = Birth {
        issuer,
        command,
        nonce,
        sequence: u64at(&out, 24),
        target: u64at(&out, 16),
    };
    r.recovery.stamps[stamp] = Some(Stamp {
        birth,
        confirmed: false,
        forgotten: false,
    });
    if let Some(control) = control {
        r.recovery.control = Some(control);
    }
    r.recovery.receipts[slot] = Some(Receipt {
        birth,
        request: raw,
        reply: out,
        confirmed: false,
        _lease: lease,
    });
    Ok(out)
}
fn confirm(r: &mut Registry, request: &[u8]) -> Result<[u8; HEADER]> {
    if request.len() != HEADER + 16 || u64at(request, 240) == 0 {
        return Err(SourceError::InvalidFrame);
    }
    let payload = &request[HEADER..];
    let command = u32at(payload, 0);
    let action = u32at(payload, 4);
    let target = u64at(payload, 8);
    if !matches!(command, 26..=29 | 35 | 36 | 45) || action > 2 {
        return Err(SourceError::InvalidFrame);
    }
    let issuer = u64at(request, 16);
    let nonce = u64at(request, 240);
    let sequence = u64at(request, 24);
    let slot = r.recovery.receipts.iter().position(|v| {
        v.as_ref().is_some_and(|v| {
            v.birth.issuer == issuer && v.birth.command == command && v.birth.nonce == nonce
        })
    });
    if let Some(i) = slot {
        let b = r.recovery.receipts[i].as_ref().unwrap().birth;
        if (b.target != target && target != 0) || b.sequence != sequence {
            return Err(SourceError::StaleSource);
        }
        let live = allocation_live(r, b);
        if target == 0 && live {
            return Err(SourceError::StaleSource);
        }
        if action == 1 {
            if !r.recovery.receipts[i].as_ref().unwrap().confirmed || issuer_live(r, b) {
                return Err(SourceError::StaleSource);
            }
            for stamp in r.recovery.stamps.iter_mut().flatten() {
                if stamp.birth == b {
                    stamp.forgotten = true;
                }
            }
            r.recovery.receipts[i] = None;
            return Ok(reply(0, sequence));
        }
        if action == 2 {
            if !r.recovery.receipts[i].as_ref().unwrap().confirmed || live {
                return Err(SourceError::StaleSource);
            }
            for stamp in &mut r.recovery.stamps {
                if stamp.is_some_and(|stamp| stamp.birth == b) {
                    *stamp = None;
                }
            }
            return Ok(reply(0, sequence));
        }
        r.recovery.receipts[i].as_mut().unwrap().confirmed = true;
        for stamp in r.recovery.stamps.iter_mut().flatten() {
            if stamp.birth == b {
                stamp.confirmed = true;
            }
        }
        return Ok(if live {
            reply(target, sequence)
        } else {
            retired(sequence)
        });
    }
    // A forgotten receipt cannot allocate or confirm an unknown owner. Forget is
    // an idempotent authority-free operation; a live issuer's highwater remains.
    if action == 1 {
        return Ok(reply(0, sequence));
    }
    if target == 0 {
        return Err(SourceError::StaleSource);
    }
    let b = Birth {
        issuer,
        command,
        nonce,
        sequence,
        target,
    };
    if let Some(index) = r
        .recovery
        .stamps
        .iter()
        .position(|stamp| stamp.is_some_and(|stamp| stamp.birth == b))
    {
        let live = phase_live(r, b);
        if action == 2 {
            if live || !r.recovery.stamps[index].as_ref().unwrap().confirmed {
                return Err(SourceError::StaleSource);
            }
            r.recovery.stamps[index] = None;
            return Ok(reply(0, sequence));
        }
        r.recovery.stamps[index].as_mut().unwrap().confirmed = true;
        return Ok(if live {
            reply(target, sequence)
        } else {
            retired(sequence)
        });
    }
    if action == 2 {
        return Ok(reply(0, sequence));
    }
    Err(SourceError::StaleSource)
}

pub(super) fn collect(r: &mut Registry) {
    let released = std::array::from_fn::<_, SLOTS, _>(|index| {
        r.recovery.stamps[index].is_some_and(|stamp| stamp.forgotten && !phase_live(r, stamp.birth))
    });
    for (stamp, released) in r.recovery.stamps.iter_mut().zip(released) {
        if released {
            *stamp = None;
        }
    }
    if r.recovery.receipts.iter().all(Option::is_none)
        && r.recovery.stamps.iter().all(Option::is_none)
    {
        r.recovery.control = None;
    }
}
