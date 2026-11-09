//! XYTJ ownership/lifetime shell, shared by the native ABI and ordinary WASM host.
use super::{dense::Job, TemporalError as E, MAX_BYTES};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
struct State {
    latest: u64,
    accepted_revision: u64,
    accepted: Vec<u8>,
    source: Option<Arc<[u8]>>,
    pending: Option<Job>,
}
struct Entry {
    state: Mutex<State>,
    cancelled: AtomicU64,
    disposed: AtomicBool,
}
#[derive(Default)]
struct Registry {
    next: u64,
    entries: Vec<(u64, Arc<Entry>)>,
}
fn registry() -> &'static Mutex<Registry> {
    static R: OnceLock<Mutex<Registry>> = OnceLock::new();
    R.get_or_init(|| Mutex::new(Registry::default()))
}
fn u(b: &[u8], i: usize) -> u64 {
    super::dense::t(b, i) as u64
}
pub fn retained(handles: &[u64]) -> usize {
    let Ok(r) = registry().lock() else {
        return MAX_BYTES;
    };
    let mut total = 0usize;
    for (h, e) in &r.entries {
        if !handles.contains(h) {
            continue;
        }
        let Ok(s) = e.state.lock() else {
            return MAX_BYTES;
        };
        total = total.saturating_add(
            s.accepted.capacity()
                + s.source.as_ref().map_or(0, |v| v.len())
                + s.pending.as_ref().map_or(0, Job::owned_bytes),
        );
    }
    total
}

pub fn close(handle: u64) {
    if let Ok(mut r) = registry().lock() {
        if let Some(i) = r.entries.iter().position(|(h, _)| *h == handle) {
            let e = r.entries.swap_remove(i).1;
            e.disposed.store(true, Ordering::Release);
        }
    }
}
fn reply(
    handle: u64,
    revision: u64,
    status: u32,
    phase: u32,
    rows: usize,
    work: usize,
    accepted: u64,
) -> Vec<u8> {
    let mut out = vec![0; 64];
    out[..4].copy_from_slice(b"XYJR");
    out[4..8].copy_from_slice(&1u32.to_le_bytes());
    for (at, v) in [
        (8, status as u64),
        (16, handle),
        (24, revision),
        (32, phase as u64),
        (40, rows as u64),
        (48, work as u64),
        (56, accepted),
    ] {
        out[at..at + 8].copy_from_slice(&v.to_le_bytes());
    }
    out
}
pub fn execute(b: &[u8], budget: usize) -> Result<Vec<u8>, E> {
    execute_with_capacity(b, budget, Some(budget))
}
pub fn execute_with_capacity(
    b: &[u8],
    budget: usize,
    capacity: Option<usize>,
) -> Result<Vec<u8>, E> {
    if b.len() < 64
        || b.len() > budget
        || budget > MAX_BYTES
        || &b[..4] != b"XYTJ"
        || b[4..8] != 1u32.to_le_bytes()
        || b[12..16].iter().chain(&b[32..64]).any(|&v| v != 0)
    {
        return Err(E::InvalidArgument);
    }
    let op = u32::from_le_bytes(b[8..12].try_into().unwrap());
    let handle = u(b, 16);
    let revision = u(b, 24);
    if op == 6 && handle == 0 && revision == 0 {
        let (columns, lanes, admitted) = Job::preview(&b[64..], budget)?;
        return Ok(reply(0, 0, 1, 0, admitted, columns * lanes, 0));
    }
    if op == 0 {
        if b.len() != 64 || handle != 0 || revision != 0 {
            return Err(E::InvalidArgument);
        }
        let mut r = registry().lock().map_err(|_| E::Disposed)?;
        if r.entries.len() >= 64 {
            return Err(E::BudgetExceeded);
        }
        r.next = r.next.checked_add(1).ok_or(E::Overflow)?;
        let h = r.next;
        r.entries.push((
            h,
            Arc::new(Entry {
                state: Mutex::new(State {
                    latest: 0,
                    accepted_revision: 0,
                    accepted: Vec::new(),
                    source: None,
                    pending: None,
                }),
                cancelled: AtomicU64::new(0),
                disposed: AtomicBool::new(false),
            }),
        ));
        return Ok(reply(h, 0, 0, 0, 0, 0, 0));
    }
    if op > 5 || op != 1 && b.len() != 64 {
        return Err(E::InvalidArgument);
    }
    let e = registry()
        .lock()
        .map_err(|_| E::Disposed)?
        .entries
        .iter()
        .find(|(h, _)| *h == handle)
        .map(|(_, e)| e.clone())
        .ok_or(E::StaleHandle)?;
    if op == 4 {
        e.cancelled.fetch_max(revision, Ordering::AcqRel);
    }
    if op == 5 {
        close(handle);
        return Ok(reply(handle, revision, 2, 0, 0, 0, 0));
    }
    let mut state = e.state.lock().map_err(|_| E::Disposed)?;
    if e.disposed.load(Ordering::Acquire) {
        return Err(E::Disposed);
    }
    if op == 1 {
        if revision == 0
            || revision <= state.latest
            || revision <= e.cancelled.load(Ordering::Acquire)
        {
            return Err(E::StaleRevision);
        }
        state.pending = None;
        let job = Job::new(&b[64..], budget, state.source.clone())?;
        state.latest = revision;
        state.pending = Some(job);
    } else if op == 2 {
        if revision != state.latest {
            return Err(E::StaleRevision);
        }
        let cancelled = || {
            e.disposed.load(Ordering::Acquire) || e.cancelled.load(Ordering::Acquire) >= revision
        };
        let done = match state.pending.as_mut().ok_or(E::Cancelled)?.step(&cancelled) {
            Ok(v) => v,
            Err(error) => {
                state.pending = None;
                return Err(error);
            }
        };
        let _ = done;
    } else if op == 3 {
        if revision == state.latest && state.pending.as_ref().is_some_and(|j| j.progress().0 == 2) {
            let job = state.pending.as_ref().unwrap();
            let result = job.finish(budget)?;
            if capacity.is_some_and(|cap| cap < result.len()) {
                return Err(E::OutputCapacity);
            }
            if capacity.is_none() {
                return Ok(result);
            }
            if e.disposed.load(Ordering::Acquire) || e.cancelled.load(Ordering::Acquire) >= revision
            {
                state.pending = None;
                return Err(E::Cancelled);
            }
            let job = state.pending.take().unwrap();
            state.source = Some(job.source);
            state.accepted = result;
            state.accepted_revision = revision;
        }
        if revision != state.accepted_revision || state.accepted_revision == 0 {
            return Err(E::StaleRevision);
        }
        return Ok(state.accepted.clone());
    } else if op == 4 {
        if revision >= state.latest {
            state.pending = None;
        }
    }
    let (phase, rows, work) = state.pending.as_ref().map_or((2, 0, 0), Job::progress);
    Ok(reply(
        handle,
        revision,
        if op == 4 {
            2
        } else if state.pending.as_ref().is_none_or(|j| j.progress().0 == 2) {
            1
        } else {
            0
        },
        phase,
        rows,
        work,
        state.accepted_revision,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn source(n: usize) -> Vec<u8> {
        let mut b = vec![0; 131 + n * 40];
        b[..4].copy_from_slice(b"XYTM");
        for (at, v) in [(4, 2u32), (8, 3), (12, n as u32), (56, 3), (64, 2)] {
            b[at..at + 4].copy_from_slice(&v.to_le_bytes());
        }
        for (at, v) in [(16, 900f64), (24, 420.), (80, 1.)] {
            b[at..at + 8].copy_from_slice(&v.to_le_bytes());
        }
        b[40..48].copy_from_slice(&(n as i64 + 1).to_le_bytes());
        b[72..80].copy_from_slice(&[31, 119, 180, 255, 31, 119, 180, 255]);
        b[128..131].copy_from_slice(b"UTC");
        for i in 0..n {
            let at = 131 + i * 40;
            b[at..at + 8].copy_from_slice(&(i as i64).to_le_bytes());
            b[at + 16..at + 24].copy_from_slice(&(i as f64).to_le_bytes());
            b[at + 24..at + 32].copy_from_slice(&(i as u64 + 42).to_le_bytes());
            b[at + 32] = 1;
        }
        b
    }
    fn command(op: u32, h: u64, rev: u64, source: &[u8], cap: Option<usize>) -> Result<Vec<u8>, E> {
        let mut b = vec![0; 64];
        b[..4].copy_from_slice(b"XYTJ");
        b[4..8].copy_from_slice(&1u32.to_le_bytes());
        b[8..12].copy_from_slice(&op.to_le_bytes());
        b[16..24].copy_from_slice(&h.to_le_bytes());
        b[24..32].copy_from_slice(&rev.to_le_bytes());
        b.extend_from_slice(source);
        execute_with_capacity(&b, MAX_BYTES, cap)
    }
    fn ready(h: u64, rev: u64) {
        while u(&command(2, h, rev, &[], Some(64)).unwrap(), 8) == 0 {}
    }
    #[test]
    fn each_scan_step_checks_cancellation_before_the_next_source_unit() {
        let mut job = Job::new(&source(10000), MAX_BYTES, None).unwrap();
        let weak = Arc::downgrade(&job.source);
        let count = std::cell::Cell::new(0);
        assert_eq!(
            job.step(&|| {
                count.set(count.get() + 1);
                count.get() == 17
            }),
            Err(E::Cancelled)
        );
        assert_eq!(job.progress().1, 16);
        drop(job);
        assert!(weak.upgrade().is_none());
    }
    #[test]
    fn ready_is_not_publication_and_capacity_cancel_teardown_preserve_the_old_accept() {
        let h = u(&command(0, 0, 0, &[], Some(64)).unwrap(), 16);
        let b = source(2000);
        command(1, h, 1, &b, Some(64)).unwrap();
        ready(h, 1);
        assert_eq!(command(3, h, 1, &[], Some(1)), Err(E::OutputCapacity));
        let picture = command(3, h, 1, &[], None).unwrap();
        command(4, h, 1, &[], Some(64)).unwrap();
        assert!(command(3, h, 1, &[], Some(MAX_BYTES)).is_err());
        command(1, h, 2, &b, Some(64)).unwrap();
        ready(h, 2);
        assert_eq!(command(3, h, 2, &[], Some(MAX_BYTES)).unwrap(), picture);
        command(1, h, 3, &b, Some(64)).unwrap();
        ready(h, 3);
        command(4, h, 3, &[], Some(64)).unwrap();
        assert_eq!(command(3, h, 2, &[], Some(MAX_BYTES)).unwrap(), picture);
        let mut foreign = b.clone();
        foreign[155] ^= 1;
        command(1, h, 4, &foreign, Some(64)).unwrap();
        assert!(command(2, h, 4, &[], Some(64)).is_err());
        assert_eq!(command(3, h, 2, &[], Some(MAX_BYTES)).unwrap(), picture);
        command(1, h, 5, &b, Some(64)).unwrap();
        command(1, h, 6, &b, Some(64)).unwrap();
        command(4, h, 5, &[], Some(64)).unwrap();
        ready(h, 6);
        assert_eq!(command(3, h, 6, &[], Some(MAX_BYTES)).unwrap(), picture);
        command(5, h, 6, &[], Some(64)).unwrap();
        assert!(command(2, h, 6, &[], Some(64)).is_err());
        for _ in 0..70 {
            let h = u(&command(0, 0, 0, &[], Some(64)).unwrap(), 16);
            command(1, h, 1, &b, Some(64)).unwrap();
            command(4, h, 1, &[], Some(64)).unwrap();
            command(5, h, 1, &[], Some(64)).unwrap();
        }
    }
}
