//! Native lifetime shell. All protocol/product decisions live in the engine.
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use xyg_engine::filter_tier_c::{FilterTierCSession, RequestGate, MAX_PACKET};
struct Entry {
    state: Mutex<FilterTierCSession>,
    gate: RequestGate,
    disposed: AtomicBool,
}
#[derive(Default)]
struct Registry {
    next: u64,
    entries: HashMap<u64, Arc<Entry>>,
}
fn registry() -> &'static Mutex<Registry> {
    static R: OnceLock<Mutex<Registry>> = OnceLock::new();
    R.get_or_init(|| Mutex::new(Registry::default()))
}
fn entry(h: u64) -> Option<Arc<Entry>> {
    registry().lock().ok()?.entries.get(&h).cloned()
}
pub fn create(max_bytes: u64) -> u64 {
    if max_bytes == 0 || max_bytes > MAX_PACKET as u64 {
        return 0;
    }
    let Ok(mut r) = registry().lock() else {
        return 0;
    };
    if r.entries.len() >= 64 {
        return 0;
    }
    let Some(next) = r.next.checked_add(1) else {
        return 0;
    };
    r.next = next;
    r.entries.insert(
        next,
        Arc::new(Entry {
            state: Mutex::new(FilterTierCSession::with_limit(max_bytes as usize)),
            gate: RequestGate::default(),
            disposed: AtomicBool::new(false),
        }),
    );
    next
}
pub fn free(h: u64) {
    if let Ok(mut r) = registry().lock() {
        if let Some(e) = r.entries.remove(&h) {
            e.disposed.store(true, Ordering::Release);
        }
    }
}
pub fn cancel(h: u64, revision: u64) -> i32 {
    let Some(e) = entry(h) else { return -1 };
    e.gate.cancel(revision);
    0
}
pub unsafe fn execute(
    h: u64,
    b: *const u8,
    len: usize,
    out: *mut u8,
    cap: usize,
    written: *mut usize,
) -> i32 {
    if written.is_null() {
        return -2;
    }
    *written = 0;
    if b.is_null() || len > MAX_PACKET || cap > MAX_PACKET || (cap != 0 && out.is_null()) {
        return -2;
    }
    let Some(e) = entry(h) else { return -1 };
    let input = std::slice::from_raw_parts(b, len);
    let seq = e.gate.enter(input);
    let Ok(mut state) = e.state.lock() else {
        return -3;
    };
    match state.execute(input, cap, || {
        e.disposed.load(Ordering::Acquire) || e.gate.obsolete(seq)
    }) {
        Ok(reply) => {
            *written = reply.len();
            if !reply.is_empty() {
                std::ptr::copy_nonoverlapping(reply.as_ptr(), out, reply.len());
            }
            0
        }
        Err(required) => {
            *written = required;
            -4
        }
    }
}
