//! Rust-owned canonical f64 append buffers (engine doc §5).
//!
//! Hosts coerce ingest and hold an opaque u64 handle; this module owns the
//! growable values, computes zone maps on seal, and exposes a contiguous
//! slice so pyramid build/compose can read through the handle instead of
//! requiring the host to pass full canonical arrays on every call.
//!
//! Growth is a capacity-doubling `Vec<f64>` whose logical ZONE_CHUNK slices
//! match `kernels::zone_maps` (DEFAULT_CHUNK = 65,536). Seal splices only
//! chunks at or after the previously sealed length, so the maps are bitwise
//! identical to a from-scratch fold over the concatenated column.
//!
//! Out-of-core memmap columns stay host-owned: they cannot sit behind this
//! first in-RAM handle (follow-up, not Phase-4 disk spill).
//!
//! Handles are slab indices behind a Mutex (engine doc §3.3): stale or
//! double-freed handles are error codes, never UB. No unsafe here.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, OnceLock};

use crate::kernels::{self, ZoneMap, DEFAULT_CHUNK};

/// Minimum reservation for a non-empty stream, matching the host Phase-0
/// growth floor (`max(n_new, n_old * 2, 1024)`).
const MIN_CAP: usize = 1024;

pub struct StreamColumn {
    values: Vec<f64>,
    zones: Vec<ZoneMap>,
    /// `values.len()` as of the last successful seal. Append past this
    /// unseals; seal is a no-op when they already match.
    sealed_len: usize,
}

impl StreamColumn {
    fn with_capacity_for(len: usize) -> Vec<f64> {
        let cap = if len == 0 { 0 } else { len.max(MIN_CAP) };
        Vec::with_capacity(cap)
    }

    pub fn new(data: &[f64]) -> Self {
        let mut values = Self::with_capacity_for(data.len());
        values.extend_from_slice(data);
        StreamColumn {
            values,
            zones: Vec::new(),
            sealed_len: 0,
        }
    }

    pub fn len(&self) -> usize {
        self.values.len()
    }

    pub fn is_empty(&self) -> bool {
        self.values.is_empty()
    }

    pub fn capacity(&self) -> usize {
        self.values.capacity()
    }

    pub fn values(&self) -> &[f64] {
        &self.values
    }

    pub fn is_sealed(&self) -> bool {
        self.sealed_len == self.values.len()
    }

    /// Zone maps from the last seal. Empty until the first seal; stale
    /// (shorter than the live column) after a subsequent append until seal.
    pub fn zones(&self) -> &[ZoneMap] {
        &self.zones
    }

    pub fn append(&mut self, data: &[f64]) {
        if data.is_empty() {
            return;
        }
        let n_new = self.values.len() + data.len();
        if self.values.capacity() < n_new {
            let cap = n_new.max(self.values.len().saturating_mul(2)).max(MIN_CAP);
            self.values.reserve(cap - self.values.len());
        }
        self.values.extend_from_slice(data);
    }

    /// Recompute zone maps for chunks at or after the previously sealed
    /// length. The splice is bitwise identical to `kernels::zone_maps` over
    /// the whole column because chunks fold serially either way.
    pub fn seal(&mut self) {
        let n = self.values.len();
        if n == 0 {
            self.zones.clear();
            self.sealed_len = 0;
            return;
        }
        if self.sealed_len == n && !self.zones.is_empty() {
            return;
        }
        let k = self.sealed_len / DEFAULT_CHUNK;
        let tail = kernels::zone_maps(&self.values[k * DEFAULT_CHUNK..], DEFAULT_CHUNK);
        self.zones.truncate(k);
        self.zones.extend(tail);
        self.sealed_len = n;
    }
}

// -- handle registry (engine doc §3.3) ---------------------------------------

type Registry = (u64, HashMap<u64, Arc<StreamColumn>>);

static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();

fn registry() -> &'static Mutex<Registry> {
    REGISTRY.get_or_init(|| Mutex::new((0, HashMap::new())))
}

pub fn reg_insert(col: StreamColumn) -> u64 {
    let mut g = registry().lock().expect("stream registry poisoned");
    g.0 += 1;
    let h = g.0;
    g.1.insert(h, Arc::new(col));
    h
}

pub fn reg_with<R>(h: u64, f: impl FnOnce(&StreamColumn) -> R) -> Option<R> {
    let col = {
        let g = registry().lock().expect("stream registry poisoned");
        g.1.get(&h).cloned()
    };
    col.map(|c| f(&c))
}

pub fn reg_with_mut<R>(h: u64, f: impl FnOnce(&mut StreamColumn) -> R) -> Option<R> {
    let mut g = registry().lock().expect("stream registry poisoned");
    let col = Arc::get_mut(g.1.get_mut(&h)?)?;
    Some(f(col))
}

pub fn reg_remove(h: u64) -> bool {
    let mut g = registry().lock().expect("stream registry poisoned");
    g.1.remove(&h).is_some()
}

/// Clone the live Arcs for a pair of handles and drop the registry lock
/// before the caller runs compute (same discipline as `tiles::reg_with`).
pub fn reg_pair(x: u64, y: u64) -> Option<(Arc<StreamColumn>, Arc<StreamColumn>)> {
    let g = registry().lock().expect("stream registry poisoned");
    Some((g.1.get(&x)?.clone(), g.1.get(&y)?.clone()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn chunked_append_and_seal_matches_from_scratch_zone_maps() {
        let mut first = vec![0.0; DEFAULT_CHUNK + 137];
        for (i, v) in first.iter_mut().enumerate() {
            *v = (i as f64) * 0.01 - 50.0;
        }
        let mut second = vec![0.0; DEFAULT_CHUNK / 3];
        for (i, v) in second.iter_mut().enumerate() {
            *v = (i as f64) * 0.02 - 10.0;
        }
        second[7] = f64::NAN;

        let mut stream = StreamColumn::new(&first);
        stream.append(&second);
        stream.seal();

        let mut concat = first;
        concat.extend_from_slice(&second);
        let fresh = kernels::zone_maps(&concat, DEFAULT_CHUNK);
        assert_eq!(stream.zones(), fresh.as_slice());
        assert_eq!(stream.len(), concat.len());
        assert!(stream.is_sealed());
    }

    #[test]
    fn seal_is_idempotent_and_append_unseals() {
        let mut stream = StreamColumn::new(&[1.0, 2.0, 3.0]);
        stream.seal();
        let first = stream.zones().to_vec();
        stream.seal();
        assert_eq!(stream.zones(), first.as_slice());
        stream.append(&[4.0]);
        assert!(!stream.is_sealed());
        stream.seal();
        let fresh = kernels::zone_maps(&[1.0, 2.0, 3.0, 4.0], DEFAULT_CHUNK);
        assert_eq!(stream.zones(), fresh.as_slice());
    }

    #[test]
    fn growth_amortizes_without_pointer_churn_inside_capacity() {
        let mut stream = StreamColumn::new(&[0.0; 10]);
        let ptr = stream.values().as_ptr();
        let cap = stream.capacity();
        assert!(cap >= MIN_CAP);
        for i in 10..200 {
            stream.append(&[i as f64]);
        }
        assert_eq!(
            stream.values().as_ptr(),
            ptr,
            "append within cap must not realloc"
        );
        assert_eq!(stream.len(), 200);
    }

    #[test]
    fn empty_new_seal_and_append() {
        let mut stream = StreamColumn::new(&[]);
        stream.seal();
        assert!(stream.zones().is_empty());
        stream.append(&[1.0, f64::NAN, 3.0]);
        stream.seal();
        let fresh = kernels::zone_maps(&[1.0, f64::NAN, 3.0], DEFAULT_CHUNK);
        assert_eq!(stream.zones(), fresh.as_slice());
    }

    #[test]
    fn handle_roundtrip_and_stale_free() {
        let h = reg_insert(StreamColumn::new(&[1.0, 2.0]));
        assert_eq!(reg_with(h, |c| c.len()), Some(2));
        assert!(reg_with_mut(h, |c| {
            c.append(&[3.0]);
            c.seal();
        })
        .is_some());
        assert_eq!(reg_with(h, |c| c.len()), Some(3));
        assert!(reg_remove(h));
        assert!(reg_with(h, |_| ()).is_none(), "stale handle is refused");
        assert!(!reg_remove(h), "double-free is stale, not UB");
    }

    #[test]
    fn concurrent_reader_blocks_mut() {
        let h = reg_insert(StreamColumn::new(&[1.0]));
        let held = {
            let g = registry().lock().expect("stream registry poisoned");
            g.1.get(&h).cloned()
        };
        assert!(held.is_some());
        assert!(
            reg_with_mut(h, |_| ()).is_none(),
            "a live Arc clone must refuse exclusive mutation"
        );
        drop(held);
        assert!(reg_with_mut(h, |_| ()).is_some());
        assert!(reg_remove(h));
    }
}
