//! Persistent transport credit composes WASM staging/FIFO with the tile ledger.
use crate::geo::GeoError;
use crate::geo_tile_cache::{GeoDerivedLease, GeoTileCache, GeoTileLimits};
pub const TRANSPORT_BYTES: usize = 160 * 1024 * 1024;
pub const PHASE_BYTES: usize = 128 * 1024 * 1024;
/// Opaque, noncloneable credit. The consuming WASM owner drops every staging,
/// result and queued buffer before dropping this lease. The cache metadata is
/// included in the160 MiB reservation, never charged outside it.
pub struct GeoTransportLease {
    _derived: GeoDerivedLease,
    _cache: GeoTileCache,
    phase: std::sync::Mutex<()>,
}
impl std::fmt::Debug for GeoTransportLease {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("GeoTransportLease").finish_non_exhaustive()
    }
}
/// An admitted phase cannot be created from a bare adapter byte budget.
/// It borrows its persistent transport owner and exclusive operation guard.
pub struct GeoTransportPhase<'a> {
    budget: usize,
    _guard: std::sync::MutexGuard<'a, ()>,
}
impl GeoTransportPhase<'_> {
    pub fn budget(&self) -> usize {
        self.budget
    }
}
impl GeoTransportLease {
    pub fn with_phase<T>(
        &self,
        budget: usize,
        f: impl FnOnce(&GeoTransportPhase<'_>) -> T,
    ) -> Result<T, GeoError> {
        if budget == 0 || budget > PHASE_BYTES {
            return Err(GeoError::ResourceLimit);
        }
        let guard = self.phase.lock().map_err(|_| GeoError::InvalidArgument)?;
        Ok(f(&GeoTransportPhase {
            budget,
            _guard: guard,
        }))
    }
    pub fn acquire() -> Result<Self, GeoError> {
        let cache = GeoTileCache::new(GeoTileLimits::default(), 0)?;
        let bytes = TRANSPORT_BYTES
            .checked_sub(cache.stats().charged_bytes)
            .ok_or(GeoError::ResourceLimit)?;
        let derived = cache.reserve_derived(bytes)?;
        Ok(Self {
            _derived: derived,
            _cache: cache,
            phase: std::sync::Mutex::new(()),
        })
    }
}
