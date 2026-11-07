//! Native ownership/lifetime shell for immutable XYFG snapshots.
use std::collections::HashMap;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use xyg_engine::temporal::{CancelFlag, TemporalError as E};
use xyg_engine::temporal_graph_frozen::{FrozenTemporalGraph, MAX_PEAK};
static CHARGED: AtomicUsize = AtomicUsize::new(0);
struct Lease(usize);
impl Lease {
    fn new(bytes: usize) -> Result<Self, E> {
        CHARGED
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |n| {
                n.checked_add(bytes).filter(|&n| n <= MAX_PEAK)
            })
            .map_err(|_| E::BudgetExceeded)?;
        Ok(Self(bytes))
    }
    fn retain(&mut self, bytes: usize) {
        CHARGED.fetch_sub(self.0 - bytes, Ordering::AcqRel);
        self.0 = bytes;
    }
}
impl Drop for Lease {
    fn drop(&mut self) {
        CHARGED.fetch_sub(self.0, Ordering::AcqRel);
    }
}
struct Snapshot {
    value: FrozenTemporalGraph,
    _lease: Lease,
}
#[derive(Default)]
struct Registry {
    next: u64,
    entries: HashMap<u64, Arc<Snapshot>>,
}
fn registry() -> &'static Mutex<Registry> {
    static R: OnceLock<Mutex<Registry>> = OnceLock::new();
    R.get_or_init(|| Mutex::new(Registry::default()))
}
fn insert(value: FrozenTemporalGraph, mut lease: Lease) -> Result<u64, E> {
    lease.retain(value.bytes().len());
    let mut r = registry().lock().expect("frozen graph registry poisoned");
    if r.entries.len() >= 256 {
        return Err(E::CapacityExceeded);
    }
    let handle = r.next.checked_add(1).ok_or(E::CapacityExceeded)?;
    r.next = handle;
    r.entries.insert(
        handle,
        Arc::new(Snapshot {
            value,
            _lease: lease,
        }),
    );
    Ok(handle)
}
unsafe fn input<'a>(p: *const u8, n: u64, max: usize) -> Result<&'a [u8], E> {
    let n = usize::try_from(n).map_err(|_| E::CapacityExceeded)?;
    if n > max || n > isize::MAX as usize || (n != 0 && p.is_null()) {
        return Err(E::InvalidArgument);
    }
    Ok(if n == 0 {
        &[]
    } else {
        std::slice::from_raw_parts(p, n)
    })
}
/// Acquire a Rust-owned independent lifetime from the actual accepted frame.
/// Window kind0 is explicitly absent (both words zero), kind1 is half-open UTC
/// micros containing the cursor. Timezone is a bounded UTF-8 display tag only.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_graph_freeze(
    handle: u64,
    revision: u64,
    window_kind: u32,
    window_start: i64,
    window_end: i64,
    timezone: *const u8,
    timezone_len: u64,
    session: u64,
    render_revision: u32,
    budget: u64,
    out_handle: *mut u64,
) -> i32 {
    super::ffi_guard(E::InvalidArgument as i32, || {
        if out_handle.is_null() {
            return E::InvalidArgument as i32;
        }
        *out_handle = 0;
        let result = (|| {
            let window = match window_kind {
                0 if window_start == 0 && window_end == 0 => None,
                1 => Some((window_start, window_end)),
                _ => return Err(E::InvalidArgument),
            };
            let timezone = std::str::from_utf8(input(timezone, timezone_len, 128)?)
                .map_err(|_| E::TimezoneRequired)?;
            if session == 0 && render_revision != 0 {
                return Err(E::InvalidArgument);
            }
            let budget = usize::try_from(budget).map_err(|_| E::CapacityExceeded)?;
            if budget > MAX_PEAK {
                return Err(E::BudgetExceeded);
            }
            let owner = super::temporal_graph_entry(handle).ok_or(E::StaleHandle)?;
            let acquire = |publication: Option<
                xyg_engine::temporal_graph_frozen::Publication<'_>,
            >| {
                let _operation = owner.operation.lock().expect("temporal operation poisoned");
                let cancel = Arc::new(CancelFlag::new());
                let mut active = owner
                    .active_cancel
                    .lock()
                    .expect("temporal cancel poisoned");
                if owner.disposed.load(Ordering::Acquire) {
                    return Err(E::Disposed);
                }
                *active = Some(cancel.clone());
                drop(active);
                let result = (|| {
                    let state = owner.state.lock().expect("temporal graph poisoned");
                    let frame = state.frame.as_ref().ok_or(E::StaleRevision)?;
                    if revision == 0 || frame.revision() != revision {
                        return Err(E::StaleRevision);
                    }
                    let peak =
                        FrozenTemporalGraph::acquisition_peak(&state.graph, publication.as_ref())?;
                    if peak > budget {
                        return Err(E::BudgetExceeded);
                    }
                    let lease = Lease::new(peak)?;
                    let value = FrozenTemporalGraph::acquire(
                        &state.graph,
                        frame,
                        window,
                        timezone,
                        publication,
                        &cancel,
                        budget,
                    )?;
                    Ok((value, lease))
                })();
                *owner
                    .active_cancel
                    .lock()
                    .expect("temporal cancel poisoned") = None;
                result
            };
            let (value, lease) = if session == 0 {
                acquire(None)?
            } else {
                super::graphforge_session_ffi::with_frozen_publication(
                    session,
                    Arc::as_ptr(&owner) as usize,
                    handle,
                    revision,
                    render_revision,
                    |p| acquire(Some(p)),
                )?
            };
            insert(value, lease)
        })();
        match result {
            Ok(h) => {
                *out_handle = h;
                0
            }
            Err(e) => e as i32,
        }
    })
}
/// Validate canonical offline bytes before allocating a retained copy. Imported
/// source/session identifiers are provenance; they never confer live access.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_graph_frozen_import(
    data: *const u8,
    len: u64,
    budget: u64,
    out_handle: *mut u64,
) -> i32 {
    super::ffi_guard(E::InvalidArgument as i32, || {
        if out_handle.is_null() {
            return E::InvalidArgument as i32;
        }
        *out_handle = 0;
        let result = (|| {
            let budget = usize::try_from(budget).map_err(|_| E::CapacityExceeded)?;
            if budget > MAX_PEAK {
                return Err(E::BudgetExceeded);
            }
            let bytes = input(data, len, xyg_engine::temporal_graph_frozen::MAX_BYTES)?;
            let peak = FrozenTemporalGraph::required_peak(bytes.len())?;
            if peak > budget {
                return Err(E::BudgetExceeded);
            }
            let lease = Lease::new(peak)?;
            insert(FrozenTemporalGraph::decode(bytes, budget)?, lease)
        })();
        match result {
            Ok(h) => {
                *out_handle = h;
                0
            }
            Err(e) => e as i32,
        }
    })
}
/// Two-call read. Short output reports exact size and writes no output bytes.
#[no_mangle]
pub unsafe extern "C" fn xyg_temporal_graph_frozen_copy(
    handle: u64,
    out: *mut u8,
    capacity: u64,
    out_len: *mut u64,
) -> i32 {
    super::ffi_guard(E::InvalidArgument as i32, || {
        if out_len.is_null() {
            return E::InvalidArgument as i32;
        }
        *out_len = 0;
        let value = registry()
            .lock()
            .expect("frozen graph registry poisoned")
            .entries
            .get(&handle)
            .cloned();
        let Some(value) = value else {
            return E::StaleHandle as i32;
        };
        let bytes = value.value.bytes();
        *out_len = bytes.len() as u64;
        if capacity < bytes.len() as u64 {
            return E::OutputCapacity as i32;
        }
        if out.is_null() {
            return E::InvalidArgument as i32;
        }
        std::ptr::copy_nonoverlapping(bytes.as_ptr(), out, bytes.len());
        0
    })
}
#[no_mangle]
pub extern "C" fn xyg_temporal_graph_frozen_destroy(handle: u64) -> i32 {
    super::ffi_guard(E::InvalidArgument as i32, || {
        if registry()
            .lock()
            .expect("frozen graph registry poisoned")
            .entries
            .remove(&handle)
            .is_some()
        {
            0
        } else {
            E::StaleHandle as i32
        }
    })
}
