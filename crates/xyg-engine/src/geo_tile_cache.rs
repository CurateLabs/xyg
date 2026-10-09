//! Bounded geographic tile selection and publication (§22/§28, #50).
//! I/O belongs to adapters; this module authorizes a finite request window
//! before any read and keeps complete published frames alive on failure.

use crate::geo::{column_from_descriptor_bytes, GeoColumn, GeoCrs, GeoError, GeoLimits};
use crate::geo_viewport::{GeoViewport, GeoViewportRebuildKey, WEB_MERCATOR_MAX};
use crate::tiles::TILE_DIM;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Arc;

pub const PROCESS_CPU_BYTES: usize = 512 * 1024 * 1024;
pub const SOURCE_QUERY_RESERVE_BYTES: usize = 128 * 1024 * 1024;
pub const TILE_CACHE_PROCESS_BYTES: usize = PROCESS_CPU_BYTES - SOURCE_QUERY_RESERVE_BYTES;
pub const MAX_TILE_PAYLOAD_BYTES: usize = 8 * 1024 * 1024;
// Covers bounded entry/request arrays, eight frame key/attribution tables,
// current + candidate source configuration and transient selection metadata.
const METADATA_BYTES: usize = 1024 * 1024;
const MAX_TEXT_BYTES: usize = 4096;
static PROCESS_CHARGED: AtomicUsize = AtomicUsize::new(0);
static NEXT_CACHE_ID: AtomicUsize = AtomicUsize::new(1);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoTileLimits {
    pub max_bytes: usize,
    pub max_entries: usize,
    pub max_pending: usize,
    pub max_visible: usize,
    pub max_sources: usize,
    pub max_views: usize,
}

impl Default for GeoTileLimits {
    fn default() -> Self {
        Self {
            max_bytes: TILE_CACHE_PROCESS_BYTES,
            max_entries: 128,
            max_pending: 64,
            max_visible: 64,
            max_sources: 16,
            max_views: 8,
        }
    }
}

impl GeoTileLimits {
    fn validate(self) -> Result<(), GeoError> {
        if !(METADATA_BYTES..=TILE_CACHE_PROCESS_BYTES).contains(&self.max_bytes)
            || self.max_entries == 0
            || self.max_entries > 128
            || self.max_pending == 0
            || self.max_pending > 64
            || self.max_visible == 0
            || self.max_visible > 64
            || self.max_sources == 0
            || self.max_sources > 16
            || self.max_views == 0
            || self.max_views > 8
        {
            return Err(GeoError::ResourceLimit);
        }
        Ok(())
    }
}

/// Half-open canonical time predicate; changing either bound invalidates tiles.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct GeoTileTime {
    pub start: i64,
    pub end: i64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum GeoTileKind {
    RasterRgba,
    VectorXygd,
}

/// Configuration only. Rust selects requests; hosts execute local reads or
/// explicitly configured network requests. No provider or URL is invented.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GeoTileLocation {
    Local {
        locator: String,
    },
    Network {
        template: String,
        attribution: String,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GeoTileSource {
    pub source_id: u64,
    pub generation: u64,
    pub layer_id: u64,
    pub layer_revision: u64,
    pub style_revision: u64,
    pub time: Option<GeoTileTime>,
    pub kind: GeoTileKind,
    pub location: GeoTileLocation,
    pub min_zoom: u8,
    pub max_zoom: u8,
    /// Declared bounds authorize read/staging/decoding before I/O.
    pub payload_limits: GeoLimits,
}

impl GeoTileSource {
    pub(crate) fn validate(&self) -> Result<(), GeoError> {
        let default = GeoLimits::default();
        if self.min_zoom > self.max_zoom
            || self.max_zoom > 25
            || self.time.is_some_and(|time| time.start >= time.end)
        {
            return Err(GeoError::InvalidArgument);
        }
        let limits = self.payload_limits;
        if limits.max_bytes == 0
            || limits.max_bytes > MAX_TILE_PAYLOAD_BYTES
            || limits.max_features == 0
            || limits.max_features > default.max_features
            || limits.max_vertices == 0
            || limits.max_vertices > default.max_vertices
        {
            return Err(GeoError::ResourceLimit);
        }
        if self.kind == GeoTileKind::RasterRgba && limits.max_bytes < TILE_DIM * TILE_DIM * 4 {
            return Err(GeoError::ResourceLimit);
        }
        let text = |value: &str| !value.trim().is_empty() && value.len() <= MAX_TEXT_BYTES;
        match &self.location {
            GeoTileLocation::Local { locator } if text(locator) => Ok(()),
            GeoTileLocation::Network {
                template,
                attribution,
            } if text(template)
                && text(attribution)
                && (template.starts_with("https://") || template.starts_with("http://"))
                && ["{z}", "{x}", "{y}"]
                    .iter()
                    .all(|part| template.contains(part)) =>
            {
                Ok(())
            }
            _ => Err(GeoError::InvalidArgument),
        }
    }

    fn reservation(&self) -> Result<usize, GeoError> {
        let payload = self.payload_limits.max_bytes;
        // Vector decode may generate IDs for all-null rows, even when there
        // is no coordinate/ID input plane. Include those independently.
        if self.kind == GeoTileKind::VectorXygd {
            payload
                .checked_mul(4)
                .and_then(|n| {
                    self.payload_limits
                        .max_features
                        .checked_mul(17)
                        .and_then(|f| n.checked_add(f))
                })
                .and_then(|n| n.checked_add(8192))
                .ok_or(GeoError::ResourceLimit)
        } else {
            payload
                .checked_mul(2)
                .and_then(|n| n.checked_add(8192))
                .ok_or(GeoError::ResourceLimit)
        }
    }

    fn key(&self, zoom: u8, x: u32, y: u32) -> GeoTileKey {
        GeoTileKey {
            source_id: self.source_id,
            generation: self.generation,
            layer_id: self.layer_id,
            layer_revision: self.layer_revision,
            style_revision: self.style_revision,
            time: self.time,
            kind: self.kind,
            zoom,
            x,
            y,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct GeoTileKey {
    pub source_id: u64,
    pub generation: u64,
    pub layer_id: u64,
    pub layer_revision: u64,
    pub style_revision: u64,
    pub time: Option<GeoTileTime>,
    pub kind: GeoTileKind,
    pub zoom: u8,
    pub x: u32,
    pub y: u32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GeoTileSelection {
    pub camera: GeoViewportRebuildKey,
    pub keys: Vec<GeoTileKey>,
}

/// XYZ tiles intersecting the Mercator AABB of the exact camera footprint.
/// Bearing/pitch can overfetch; no visible ground is omitted. Dateline columns
/// wrap to canonical X, poles clamp to the certified Mercator extent.
pub fn select_tiles(
    camera: &GeoViewport,
    sources: &[GeoTileSource],
    limits: GeoTileLimits,
) -> Result<GeoTileSelection, GeoError> {
    limits.validate()?;
    camera.validate()?;
    if sources.len() > limits.max_sources {
        return Err(GeoError::ResourceLimit);
    }
    for (i, source) in sources.iter().enumerate() {
        source.validate()?;
        if sources[..i]
            .iter()
            .any(|other| other.source_id == source.source_id && other.layer_id == source.layer_id)
        {
            return Err(GeoError::InvalidArgument);
        }
    }
    // Reuse the engine's perspective ground footprint instead of introducing
    // XYZ-camera math. EPSG:3857 bounds retain unwrapped X across the dateline.
    let (mx, my) = camera.center_mercator();
    let mercator = GeoViewport {
        crs: GeoCrs::Epsg3857,
        center_x: mx,
        center_y: my,
        ..*camera
    };
    let [x0, y0, x1, y1] = mercator.bounds()?;
    let mut ranges = Vec::with_capacity(sources.len());
    let mut count = 0usize;
    for source in sources {
        // GeoViewport world is 512px at zoom zero; 256² XYZ tiles therefore
        // use zoom+1, clamped only to explicitly available source levels.
        let zoom = ((camera.zoom + (512.0 / TILE_DIM as f64).log2()).floor() as u8)
            .clamp(source.min_zoom, source.max_zoom);
        let n = 1i64 << zoom;
        let world = 2.0 * WEB_MERCATOR_MAX;
        let mut start_x = ((x0 + WEB_MERCATOR_MAX) / world * n as f64).floor();
        let mut end_x = ((x1 + WEB_MERCATOR_MAX) / world * n as f64).ceil();
        if !start_x.is_finite()
            || !end_x.is_finite()
            || start_x < i64::MIN as f64
            || end_x >= i64::MAX as f64
        {
            return Err(GeoError::ResourceLimit);
        }
        if camera.world_wrap {
            end_x = end_x.min(start_x + n as f64);
        } else {
            start_x = start_x.clamp(0.0, n as f64);
            end_x = end_x.clamp(0.0, n as f64);
        }
        let start_y = (((WEB_MERCATOR_MAX - y1) / world * n as f64).floor() as i64).clamp(0, n);
        let end_y = (((WEB_MERCATOR_MAX - y0) / world * n as f64).ceil() as i64).clamp(0, n);
        let start_x = start_x as i64;
        let end_x = end_x as i64;
        let cells = end_x.saturating_sub(start_x) as usize;
        count = cells
            .checked_mul(end_y.saturating_sub(start_y) as usize)
            .and_then(|n| count.checked_add(n))
            .ok_or(GeoError::ResourceLimit)?;
        if count > limits.max_visible {
            return Err(GeoError::ResourceLimit);
        }
        ranges.push((zoom, n, start_x, end_x, start_y, end_y));
    }
    let mut keys = Vec::with_capacity(count);
    for (source, (zoom, n, x0, x1, y0, y1)) in sources.iter().zip(ranges) {
        for y in y0..y1 {
            for x in x0..x1 {
                keys.push(source.key(zoom, x.rem_euclid(n) as u32, y as u32));
            }
        }
    }
    Ok(GeoTileSelection {
        camera: camera.rebuild_key()?,
        keys,
    })
}

/// Input allocation is made only after this ticket's reservation is accepted.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoTileTicket {
    pub cache_id: usize,
    pub epoch: u64,
    pub ordinal: u32,
    pub key: GeoTileKey,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoTileRequest {
    pub ticket: GeoTileTicket,
    pub max_payload_bytes: usize,
    pub reserved_bytes: usize,
}

enum GeoTileInput {
    Raster {
        width: u32,
        height: u32,
        rgba: Vec<u8>,
    },
    VectorXygd(Vec<u8>),
}

/// Metadata describing bytes filled into an authorized read buffer.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoTileData {
    Raster {
        width: u32,
        height: u32,
        length: usize,
    },
    VectorXygd {
        length: usize,
    },
}

struct ReadState {
    detached: AtomicBool,
    bytes: usize,
}
impl Drop for ReadState {
    fn drop(&mut self) {
        if self.detached.load(Ordering::SeqCst) {
            process_adjust(self.bytes, 0).expect("release cannot fail");
        }
    }
}

/// Single owned I/O buffer. Its reserve survives cancellation and cache drop;
/// buffers cannot be cloned or extracted independently of their read lease.
pub struct GeoTileRead {
    buffer: Vec<u8>,
    ticket: GeoTileTicket,
    state: Arc<ReadState>,
}
impl GeoTileRead {
    pub fn ticket(&self) -> GeoTileTicket {
        self.ticket
    }
    pub fn bytes_mut(&mut self) -> &mut [u8] {
        &mut self.buffer
    }
}

#[derive(Debug)]
pub enum GeoTilePayload {
    Raster {
        width: u32,
        height: u32,
        rgba: Vec<u8>,
    },
    Vector(GeoColumn),
}

struct Entry {
    key: GeoTileKey,
    payload: GeoTilePayload,
    bytes: usize,
    tick: u64,
}
struct Candidate {
    epoch: u64,
    view_id: u64,
    selection: GeoTileSelection,
    sources: Vec<GeoTileSource>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GeoTileFrame {
    pub view_id: u64,
    pub epoch: u64,
    pub camera: GeoViewportRebuildKey,
    pub keys: Vec<GeoTileKey>,
    pub attributions: Vec<String>,
}

/// Complete candidate data borrowed while the prior frame stays pinned.
/// Compile and stage derived output before `commit_frame`; cancel on failure.
pub struct GeoTilePreparedFrame<'a> {
    pub view_id: u64,
    pub epoch: u64,
    pub camera: &'a GeoViewportRebuildKey,
    pub keys: &'a [GeoTileKey],
    pub sources: &'a [GeoTileSource],
}

/// Engine-internal preflight lease for derived Scene/paint/transfer storage.
/// Its consuming owner must drop storage before this lease. The charge and
/// owning ledger are private and cannot be mutated by adapters.
pub(crate) struct GeoDerivedLease {
    bytes: usize,
    owner: Arc<AtomicUsize>,
}

impl Drop for GeoDerivedLease {
    fn drop(&mut self) {
        self.owner.fetch_sub(self.bytes, Ordering::SeqCst);
        process_adjust(self.bytes, 0).expect("release cannot fail");
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoTileStats {
    pub charged_bytes: usize,
    pub resident_bytes: usize,
    pub pending_reserved_bytes: usize,
    pub derived_reserved_bytes: usize,
    pub process_charged_bytes: usize,
    pub process_limit_bytes: usize,
    pub other_live_bytes: usize,
    pub entries: usize,
    pub pending: usize,
    pub active_reads: usize,
    pub views: usize,
}

/// Shared between views. One active request window bounds candidate work;
/// up to eight complete frames can pin resident tiles without an overshoot.
pub struct GeoTileCache {
    id: usize,
    limits: GeoTileLimits,
    entries: Vec<Entry>,
    pending: Vec<GeoTileRequest>,
    reads: Vec<(GeoTileTicket, Arc<ReadState>)>,
    frames: Vec<GeoTileFrame>,
    candidate: Option<Candidate>,
    charged: usize,
    derived: Arc<AtomicUsize>,
    other_live_bytes: usize,
    epoch: u64,
    tick: u64,
}

fn process_adjust(old: usize, new: usize) -> Result<(), GeoError> {
    if new <= old {
        PROCESS_CHARGED.fetch_sub(old - new, Ordering::SeqCst);
        return Ok(());
    }
    let extra = new - old;
    PROCESS_CHARGED
        .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |used| {
            used.checked_add(extra)
                .filter(|next| *next <= TILE_CACHE_PROCESS_BYTES)
        })
        .map(|_| ())
        .map_err(|_| GeoError::ResourceLimit)
}

impl GeoTileCache {
    pub fn new(limits: GeoTileLimits, other_live_bytes: usize) -> Result<Self, GeoError> {
        limits.validate()?;
        if other_live_bytes > SOURCE_QUERY_RESERVE_BYTES {
            return Err(GeoError::ResourceLimit);
        }
        let id = NEXT_CACHE_ID
            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |n| n.checked_add(1))
            .map_err(|_| GeoError::ResourceLimit)?;
        process_adjust(0, METADATA_BYTES)?;
        Ok(Self {
            id,
            limits,
            entries: Vec::with_capacity(limits.max_entries),
            pending: Vec::with_capacity(limits.max_pending),
            frames: Vec::with_capacity(limits.max_views),
            reads: Vec::with_capacity(limits.max_pending),
            candidate: None,
            charged: METADATA_BYTES,
            derived: Arc::new(AtomicUsize::new(0)),
            other_live_bytes,
            epoch: 0,
            tick: 0,
        })
    }

    fn pinned(&self, key: GeoTileKey) -> bool {
        self.frames.iter().any(|frame| frame.keys.contains(&key))
    }

    fn reap_reads(&mut self) {
        if let Some(epoch) = self
            .candidate
            .as_ref()
            .filter(|candidate| {
                self.reads.iter().any(|(ticket, state)| {
                    ticket.epoch == candidate.epoch && Arc::strong_count(state) == 1
                })
            })
            .map(|candidate| candidate.epoch)
        {
            self.cancel(epoch);
        }
        let mut released = 0;
        self.reads.retain(|(_, state)| {
            if Arc::strong_count(state) == 1 {
                released += state.bytes;
                false
            } else {
                true
            }
        });
        let next = self.charged - released;
        process_adjust(self.charged, next).expect("release cannot fail");
        self.charged = next;
    }

    /// Complete admission and eviction planning precede candidate replacement
    /// and any I/O. An impossible plan leaves old frames and requests intact.
    pub fn begin_frame(
        &mut self,
        view_id: u64,
        camera: &GeoViewport,
        sources: &[GeoTileSource],
        other_live_bytes: usize,
    ) -> Result<u64, GeoError> {
        self.reap_reads();
        if other_live_bytes > SOURCE_QUERY_RESERVE_BYTES
            || (!self.frames.iter().any(|frame| frame.view_id == view_id)
                && self.frames.len() >= self.limits.max_views)
        {
            return Err(GeoError::ResourceLimit);
        }
        let selection = select_tiles(camera, sources, self.limits)?;
        let epoch = self.epoch.checked_add(1).ok_or(GeoError::ResourceLimit)?;
        let tick = self.tick.checked_add(1).ok_or(GeoError::ResourceLimit)?;
        let mut requests = Vec::with_capacity(selection.keys.len().min(self.limits.max_pending));
        for (ordinal, key) in selection.keys.iter().enumerate() {
            if self.entries.iter().any(|entry| entry.key == *key) {
                continue;
            }
            if requests.len() + self.reads.len() >= self.limits.max_pending {
                return Err(GeoError::ResourceLimit);
            }
            let source = sources
                .iter()
                .find(|source| source.source_id == key.source_id && source.layer_id == key.layer_id)
                .ok_or(GeoError::InvalidArgument)?;
            requests.push(GeoTileRequest {
                ticket: GeoTileTicket {
                    cache_id: self.id,
                    epoch,
                    ordinal: ordinal as u32,
                    key: *key,
                },
                max_payload_bytes: source.payload_limits.max_bytes,
                reserved_bytes: source.reservation()?,
            });
        }
        let reserved = requests
            .iter()
            .try_fold(0usize, |n, request| n.checked_add(request.reserved_bytes))
            .ok_or(GeoError::ResourceLimit)?;
        // In-flight reads are retained, even when their candidate is replaced.
        let old_reserved: usize = self
            .pending
            .iter()
            .filter(|request| {
                !self
                    .reads
                    .iter()
                    .any(|(ticket, _)| *ticket == request.ticket)
            })
            .map(|request| request.reserved_bytes)
            .sum();
        let mut charged = self
            .charged
            .checked_sub(old_reserved)
            .and_then(|n| n.checked_add(reserved))
            .ok_or(GeoError::ResourceLimit)?;
        let mut remaining = self.entries.len();
        let mut evict = Vec::with_capacity(self.limits.max_entries);
        let derived = self.derived.load(Ordering::SeqCst);
        while charged
            .checked_add(derived)
            .ok_or(GeoError::ResourceLimit)?
            > self.limits.max_bytes
            || remaining + requests.len() > self.limits.max_entries
        {
            let Some((index, entry)) = self
                .entries
                .iter()
                .enumerate()
                .filter(|(index, entry)| {
                    !evict.contains(index)
                        && !self.pinned(entry.key)
                        && !selection.keys.contains(&entry.key)
                })
                .min_by_key(|(_, entry)| entry.tick)
            else {
                return Err(GeoError::ResourceLimit);
            };
            charged -= entry.bytes;
            remaining -= 1;
            evict.push(index);
        }
        // This CAS also covers simultaneous caches, not just this view/window.
        let peak = self.charged.max(charged);
        process_adjust(self.charged, peak)?;
        // Drop physical payloads before releasing their process reservation.
        evict.sort_unstable();
        for index in evict.into_iter().rev() {
            self.entries.remove(index);
        }
        self.pending = requests;
        self.candidate = None;
        process_adjust(peak, charged)?;
        self.charged = charged;
        self.other_live_bytes = other_live_bytes;
        self.epoch = epoch;
        self.tick = tick;
        for entry in &mut self.entries {
            if selection.keys.contains(&entry.key) {
                entry.tick = tick;
            }
        }
        self.candidate = Some(Candidate {
            epoch,
            view_id,
            selection,
            sources: sources.to_vec(),
        });
        Ok(epoch)
    }

    pub fn requests(&self) -> &[GeoTileRequest] {
        &self.pending
    }

    /// Reserve derived memory before allocating it. Old and candidate storage
    /// count toward both the local ceiling and shared process pool. The lease
    /// can outlive its cache without releasing its process charge.
    pub(crate) fn reserve_derived(&self, bytes: usize) -> Result<GeoDerivedLease, GeoError> {
        if bytes == 0 || bytes > self.limits.max_bytes {
            return Err(GeoError::ResourceLimit);
        }
        process_adjust(0, bytes)?;
        let reserved = self
            .derived
            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |used| {
                used.checked_add(bytes).filter(|total| {
                    self.charged
                        .checked_add(*total)
                        .is_some_and(|n| n <= self.limits.max_bytes)
                })
            });
        if reserved.is_err() {
            process_adjust(bytes, 0).expect("release cannot fail");
            return Err(GeoError::ResourceLimit);
        }
        Ok(GeoDerivedLease {
            bytes,
            owner: Arc::clone(&self.derived),
        })
    }

    pub fn start_read(&mut self, ticket: GeoTileTicket) -> Result<GeoTileRead, GeoError> {
        self.reap_reads();
        let request = *self
            .pending
            .iter()
            .find(|request| request.ticket == ticket)
            .ok_or(GeoError::StaleHandle)?;
        if self.reads.iter().any(|(other, _)| *other == ticket) {
            return Err(GeoError::InvalidArgument);
        }
        let mut buffer = Vec::new();
        buffer
            .try_reserve_exact(request.max_payload_bytes)
            .map_err(|_| GeoError::ResourceLimit)?;
        if buffer.capacity() > request.max_payload_bytes {
            return Err(GeoError::ResourceLimit);
        }
        buffer.resize(request.max_payload_bytes, 0);
        let state = Arc::new(ReadState {
            detached: AtomicBool::new(false),
            bytes: request.reserved_bytes,
        });
        self.reads.push((ticket, Arc::clone(&state)));
        Ok(GeoTileRead {
            buffer,
            ticket,
            state,
        })
    }

    pub fn request_source(&self, ticket: GeoTileTicket) -> Option<&GeoTileSource> {
        let candidate = self.candidate.as_ref()?;
        if ticket.cache_id != self.id
            || candidate.epoch != ticket.epoch
            || !self.pending.iter().any(|request| request.ticket == ticket)
        {
            return None;
        }
        candidate.sources.iter().find(|source| {
            source.source_id == ticket.key.source_id && source.layer_id == ticket.key.layer_id
        })
    }

    pub fn publish(&mut self, read: GeoTileRead, data: GeoTileData) -> Result<bool, GeoError> {
        let GeoTileRead {
            ticket,
            mut buffer,
            state,
        } = read;
        let Some(read_index) = self
            .reads
            .iter()
            .position(|(other, retained)| *other == ticket && Arc::ptr_eq(retained, &state))
        else {
            drop(buffer);
            drop(state);
            return Err(GeoError::StaleHandle);
        };
        let Some(index) = self
            .pending
            .iter()
            .position(|request| request.ticket == ticket)
        else {
            drop(buffer);
            self.reads.remove(read_index);
            let next = self.charged - state.bytes;
            process_adjust(self.charged, next)?;
            self.charged = next;
            return Err(GeoError::StaleHandle);
        };
        let request = self.pending[index];
        let source = self.request_source(ticket).ok_or(GeoError::StaleHandle)?;
        let length = match data {
            GeoTileData::Raster { length, .. } | GeoTileData::VectorXygd { length } => length,
        };
        let result = if length > buffer.len() {
            drop(buffer);
            Err(GeoError::ResourceLimit)
        } else {
            buffer.truncate(length);
            let input = match data {
                GeoTileData::Raster { width, height, .. } => GeoTileInput::Raster {
                    width,
                    height,
                    rgba: buffer,
                },
                GeoTileData::VectorXygd { .. } => GeoTileInput::VectorXygd(buffer),
            };
            admit_payload(source, request.reserved_bytes, input)
        };
        self.reads.remove(read_index);
        let (payload, bytes) = match result {
            Ok(value) => value,
            Err(error) => {
                self.cancel(ticket.epoch);
                return Err(error);
            }
        };
        debug_assert!(bytes <= request.reserved_bytes);
        let charged = self.charged - request.reserved_bytes + bytes;
        process_adjust(self.charged, charged)?;
        self.charged = charged;
        self.pending.remove(index);
        self.entries.push(Entry {
            key: ticket.key,
            payload,
            bytes,
            tick: self.tick,
        });
        Ok(self.pending.is_empty())
    }

    pub fn cancel(&mut self, epoch: u64) -> bool {
        if self
            .candidate
            .as_ref()
            .is_none_or(|candidate| candidate.epoch != epoch)
        {
            return false;
        }
        let reserved: usize = self
            .pending
            .iter()
            .filter(|request| {
                !self
                    .reads
                    .iter()
                    .any(|(ticket, _)| *ticket == request.ticket)
            })
            .map(|request| request.reserved_bytes)
            .sum();
        let next = self.charged - reserved;
        process_adjust(self.charged, next).expect("release cannot fail");
        self.charged = next;
        self.pending.clear();
        self.candidate = None;
        true
    }

    pub fn commit_frame(&mut self, epoch: u64) -> Result<&GeoTileFrame, GeoError> {
        let candidate = self.candidate.as_ref().ok_or(GeoError::StaleHandle)?;
        if candidate.epoch != epoch {
            return Err(GeoError::StaleHandle);
        }
        if !self.pending.is_empty() {
            return Err(GeoError::InvalidArgument);
        }
        let view_id = candidate.view_id;
        let candidate = self.candidate.take().unwrap();
        let attributions = candidate
            .sources
            .iter()
            .filter_map(|source| match &source.location {
                GeoTileLocation::Network { attribution, .. } => Some(attribution.clone()),
                _ => None,
            })
            .collect();
        let frame = GeoTileFrame {
            view_id,
            epoch,
            camera: candidate.selection.camera,
            keys: candidate.selection.keys,
            attributions,
        };
        let index = if let Some(index) = self
            .frames
            .iter()
            .position(|frame| frame.view_id == view_id)
        {
            self.frames[index] = frame;
            index
        } else {
            self.frames.push(frame);
            self.frames.len() - 1
        };
        Ok(&self.frames[index])
    }

    pub fn frame(&self, view_id: u64) -> Option<&GeoTileFrame> {
        self.frames.iter().find(|frame| frame.view_id == view_id)
    }

    pub fn prepared_frame(&self, epoch: u64) -> Result<GeoTilePreparedFrame<'_>, GeoError> {
        let candidate = self.candidate.as_ref().ok_or(GeoError::StaleHandle)?;
        if candidate.epoch != epoch {
            return Err(GeoError::StaleHandle);
        }
        if !self.pending.is_empty() {
            return Err(GeoError::InvalidArgument);
        }
        Ok(GeoTilePreparedFrame {
            view_id: candidate.view_id,
            epoch,
            camera: &candidate.selection.camera,
            keys: &candidate.selection.keys,
            sources: &candidate.sources,
        })
    }
    pub fn payload(&self, key: GeoTileKey) -> Option<&GeoTilePayload> {
        self.entries
            .iter()
            .find(|entry| entry.key == key)
            .map(|entry| &entry.payload)
    }

    pub fn drop_view(&mut self, view_id: u64) {
        if let Some(epoch) = self
            .candidate
            .as_ref()
            .filter(|candidate| candidate.view_id == view_id)
            .map(|candidate| candidate.epoch)
        {
            self.cancel(epoch);
        }
        if let Some(index) = self
            .frames
            .iter()
            .position(|frame| frame.view_id == view_id)
        {
            self.frames.remove(index);
        }
    }

    pub fn stats(&self) -> GeoTileStats {
        let derived = self.derived.load(Ordering::SeqCst);
        GeoTileStats {
            charged_bytes: self.charged + derived,
            resident_bytes: self.entries.iter().map(|entry| entry.bytes).sum(),
            pending_reserved_bytes: self.charged
                - METADATA_BYTES
                - self.entries.iter().map(|entry| entry.bytes).sum::<usize>(),
            derived_reserved_bytes: derived,
            process_charged_bytes: PROCESS_CHARGED.load(Ordering::SeqCst),
            process_limit_bytes: TILE_CACHE_PROCESS_BYTES,
            other_live_bytes: self.other_live_bytes,
            entries: self.entries.len(),
            pending: self.pending.len(),
            active_reads: self.reads.len(),
            views: self.frames.len(),
        }
    }
}

impl Drop for GeoTileCache {
    fn drop(&mut self) {
        let mut held = 0;
        for (_, state) in &self.reads {
            if Arc::strong_count(state) > 1 {
                state.detached.store(true, Ordering::SeqCst);
                held += state.bytes;
            }
        }
        drop(std::mem::take(&mut self.entries));
        drop(std::mem::take(&mut self.pending));
        drop(std::mem::take(&mut self.frames));
        self.candidate = None;
        drop(std::mem::take(&mut self.reads));
        process_adjust(self.charged, held).expect("release cannot fail");
    }
}

fn admit_payload(
    source: &GeoTileSource,
    reservation: usize,
    input: GeoTileInput,
) -> Result<(GeoTilePayload, usize), GeoError> {
    match (source.kind, input) {
        (
            GeoTileKind::RasterRgba,
            GeoTileInput::Raster {
                width,
                height,
                rgba,
            },
        ) => {
            if width as usize != TILE_DIM
                || height as usize != TILE_DIM
                || rgba.len() != TILE_DIM * TILE_DIM * 4
            {
                return Err(GeoError::InvalidArgument);
            }
            if rgba.capacity() > source.payload_limits.max_bytes {
                return Err(GeoError::ResourceLimit);
            }
            let bytes = rgba.capacity();
            Ok((
                GeoTilePayload::Raster {
                    width,
                    height,
                    rgba,
                },
                bytes,
            ))
        }
        (GeoTileKind::VectorXygd, GeoTileInput::VectorXygd(bytes)) => {
            if bytes.capacity() > source.payload_limits.max_bytes {
                return Err(GeoError::ResourceLimit);
            }
            if bytes.len() < 64 {
                return Err(GeoError::InvalidArgument);
            }
            let number = |at| u64::from_le_bytes(bytes[at..at + 8].try_into().unwrap());
            let features = usize::try_from(number(24)).map_err(|_| GeoError::ResourceLimit)?;
            let vertices = usize::try_from(number(32)).map_err(|_| GeoError::ResourceLimit)?;
            if features > source.payload_limits.max_features
                || vertices > source.payload_limits.max_vertices
            {
                return Err(GeoError::ResourceLimit);
            }
            let column = column_from_descriptor_bytes(&bytes, reservation)?;
            // Conservative retained charge includes capacities, generated IDs,
            // canonical metadata and fixed validation bookkeeping.
            let retained = bytes
                .len()
                .checked_mul(2)
                .and_then(|n| features.checked_mul(17).and_then(|f| n.checked_add(f)))
                .and_then(|n| n.checked_add(8192))
                .ok_or(GeoError::ResourceLimit)?;
            Ok((GeoTilePayload::Vector(column), retained))
        }
        _ => Err(GeoError::TypeMismatch),
    }
}

#[cfg(test)]
pub(crate) fn test_process_lock() -> std::sync::MutexGuard<'static, ()> {
    use std::sync::{Mutex, OnceLock};
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
        .lock()
        .unwrap_or_else(|error| error.into_inner())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo_viewport::lonlat_to_mercator;

    fn lock() -> std::sync::MutexGuard<'static, ()> {
        super::test_process_lock()
    }

    fn camera() -> GeoViewport {
        GeoViewport::new(
            GeoCrs::Epsg4326,
            45.0,
            40.0,
            1.0,
            64.0,
            64.0,
            0.0,
            0.0,
            true,
        )
        .unwrap()
    }

    fn raster() -> GeoTileSource {
        GeoTileSource {
            source_id: u64::MAX,
            generation: 1,
            layer_id: 7,
            layer_revision: 2,
            style_revision: 3,
            time: None,
            kind: GeoTileKind::RasterRgba,
            location: GeoTileLocation::Local {
                locator: "opaque-local-tile-set".into(),
            },
            min_zoom: 0,
            max_zoom: 25,
            payload_limits: GeoLimits {
                max_features: 16,
                max_vertices: 32,
                max_bytes: TILE_DIM * TILE_DIM * 4,
            },
        }
    }

    fn vector() -> GeoTileSource {
        GeoTileSource {
            kind: GeoTileKind::VectorXygd,
            payload_limits: GeoLimits {
                max_features: 2,
                max_vertices: 4,
                max_bytes: 256,
            },
            ..raster()
        }
    }

    fn point_bytes() -> Vec<u8> {
        let mut bytes = vec![0u8; 96];
        bytes[..4].copy_from_slice(b"XYGD");
        for (at, n) in [(4, 1u32), (8, 1), (12, 4326), (16, 1)] {
            bytes[at..at + 4].copy_from_slice(&n.to_le_bytes());
        }
        bytes[24..32].copy_from_slice(&1u64.to_le_bytes());
        bytes[32..40].copy_from_slice(&1u64.to_le_bytes());
        bytes[64..72].copy_from_slice(&45f64.to_le_bytes());
        bytes[72..80].copy_from_slice(&40f64.to_le_bytes());
        bytes[80] = 1;
        bytes[88..96].copy_from_slice(&u64::MAX.to_le_bytes());
        bytes
    }

    fn complete_raster(cache: &mut GeoTileCache, epoch: u64) {
        let requests = cache.requests().to_vec();
        for request in requests {
            let mut read = cache.start_read(request.ticket).unwrap();
            for rgba in read.bytes_mut().chunks_exact_mut(4) {
                rgba.copy_from_slice(&[1, 2, 3, 128]);
            }
            cache
                .publish(
                    read,
                    GeoTileData::Raster {
                        width: 256,
                        height: 256,
                        length: TILE_DIM * TILE_DIM * 4,
                    },
                )
                .unwrap();
        }
        cache.commit_frame(epoch).unwrap();
    }

    #[test]
    fn selection_is_camera_owned_and_covers_dateline_poles_bearing_pitch() {
        let _lock = lock();
        for (lon, lat, pitch, bearing) in [
            (179.0, 20.0, 45.0, 35.0),
            (-179.0, -20.0, -45.0, -35.0),
            (0.0, 90.0, 0.0, 0.0),
            (0.0, -90.0, 40.0, 55.0),
        ] {
            let view = GeoViewport {
                center_x: lon,
                center_y: lat,
                zoom: 2.0,
                width: 160.0,
                height: 120.0,
                pitch_deg: pitch,
                bearing_deg: bearing,
                world_wrap: true,
                ..camera()
            };
            let selection = select_tiles(&view, &[raster()], GeoTileLimits::default()).unwrap();
            assert_eq!(selection.camera, view.rebuild_key().unwrap());
            assert!(selection.keys.len() <= 64);
            for fy in [0.1, 0.5, 0.9] {
                for fx in [0.1, 0.5, 0.9] {
                    let (lon, lat) = view.unproject(view.width * fx, view.height * fy).unwrap();
                    let (mx, my) = lonlat_to_mercator(lon, lat);
                    let n = 1u32 << selection.keys[0].zoom;
                    let x = (((mx + WEB_MERCATOR_MAX) / (2. * WEB_MERCATOR_MAX) * n as f64).floor()
                        as i64)
                        .rem_euclid(n as i64) as u32;
                    let y = (((WEB_MERCATOR_MAX - my) / (2. * WEB_MERCATOR_MAX) * n as f64).floor()
                        as i64)
                        .clamp(0, n as i64 - 1) as u32;
                    assert!(
                        selection.keys.iter().any(|key| key.x == x && key.y == y),
                        "visible ground tile omitted"
                    );
                }
            }
        }
        let view = GeoViewport {
            center_x: 179.0,
            center_y: 0.0,
            zoom: 2.0,
            width: 160.0,
            height: 120.0,
            world_wrap: true,
            ..camera()
        };
        let keys = select_tiles(&view, &[raster()], GeoTileLimits::default())
            .unwrap()
            .keys;
        assert!(keys.iter().any(|key| key.x == 0) && keys.iter().any(|key| key.x == 7));
        let huge = GeoViewport {
            width: 1e30,
            height: 1e30,
            zoom: 24.0,
            ..camera()
        };
        assert_eq!(
            select_tiles(&huge, &[raster()], GeoTileLimits::default()),
            Err(GeoError::ResourceLimit)
        );
    }

    #[test]
    fn explicit_provider_and_all_revision_dimensions_are_part_of_tile_identity() {
        let _lock = lock();
        let mut source = raster();
        source.location = GeoTileLocation::Network {
            template: "https://app.example/{z}/{x}/{y}".into(),
            attribution: String::new(),
        };
        assert_eq!(
            select_tiles(&camera(), &[source.clone()], GeoTileLimits::default()),
            Err(GeoError::InvalidArgument)
        );
        source.location = GeoTileLocation::Network {
            template: "https://app.example/{z}/{x}/{y}".into(),
            attribution: "App-authored attribution".into(),
        };
        let key = select_tiles(&camera(), &[source.clone()], GeoTileLimits::default())
            .unwrap()
            .keys[0];
        for variant in [
            GeoTileSource {
                generation: 2,
                ..source.clone()
            },
            GeoTileSource {
                layer_revision: 3,
                ..source.clone()
            },
            GeoTileSource {
                style_revision: 4,
                ..source.clone()
            },
            GeoTileSource {
                layer_id: 8,
                ..source.clone()
            },
            GeoTileSource {
                time: Some(GeoTileTime { start: -1, end: 1 }),
                ..source.clone()
            },
        ] {
            assert_ne!(
                select_tiles(&camera(), &[variant], GeoTileLimits::default())
                    .unwrap()
                    .keys[0],
                key
            );
        }
        let mut cache = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
        let epoch = cache.begin_frame(1, &camera(), &[source], 0).unwrap();
        complete_raster(&mut cache, epoch);
        assert_eq!(
            cache.frame(1).unwrap().attributions,
            ["App-authored attribution"]
        );
    }

    #[test]
    fn byte_and_entry_admission_precede_io_and_keep_the_old_frame() {
        let _lock = lock();
        let source = raster();
        let reservation = source.reservation().unwrap();
        let payload = source.payload_limits.max_bytes;
        let limits = GeoTileLimits {
            max_bytes: METADATA_BYTES + reservation + payload - 1,
            max_entries: 2,
            ..GeoTileLimits::default()
        };
        let mut cache = GeoTileCache::new(limits, SOURCE_QUERY_RESERVE_BYTES).unwrap();
        let epoch = cache
            .begin_frame(
                1,
                &camera(),
                std::slice::from_ref(&source),
                SOURCE_QUERY_RESERVE_BYTES,
            )
            .unwrap();
        complete_raster(&mut cache, epoch);
        let old = cache.frame(1).unwrap().clone();
        let shifted = GeoViewport {
            center_x: -45.0,
            ..camera()
        };
        assert_eq!(
            cache.begin_frame(1, &shifted, std::slice::from_ref(&source), 0),
            Err(GeoError::ResourceLimit)
        );
        assert_eq!(cache.frame(1), Some(&old));
        assert!(cache.requests().is_empty());
        assert_eq!(cache.stats().charged_bytes, METADATA_BYTES + payload);
        cache.limits.max_bytes += 1;
        let candidate = cache.begin_frame(1, &shifted, &[source], 0).unwrap();
        assert_eq!(cache.stats().charged_bytes, cache.limits.max_bytes);
        assert_eq!(
            cache.commit_frame(candidate),
            Err(GeoError::InvalidArgument)
        );
        let request = cache.requests()[0];
        let read = cache.start_read(request.ticket).unwrap();
        assert_eq!(
            cache.publish(
                read,
                GeoTileData::Raster {
                    width: 256,
                    height: 256,
                    length: 1
                }
            ),
            Err(GeoError::InvalidArgument)
        );
        assert_eq!(cache.frame(1), Some(&old));
        assert!(cache.requests().is_empty());
    }

    #[test]
    fn stale_cancelled_reads_are_bounded_and_cannot_replace_a_newer_frame() {
        let _lock = lock();
        let mut cache = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
        let epoch = cache.begin_frame(1, &camera(), &[raster()], 0).unwrap();
        let request = cache.requests()[0];
        let read = cache.start_read(request.ticket).unwrap();
        assert!(cache.cancel(epoch));
        assert_eq!(cache.stats().pending_reserved_bytes, request.reserved_bytes);
        let newer = cache
            .begin_frame(
                1,
                &camera(),
                &[GeoTileSource {
                    generation: 2,
                    ..raster()
                }],
                0,
            )
            .unwrap();
        complete_raster(&mut cache, newer);
        let frame = cache.frame(1).unwrap().clone();
        assert!(!cache.cancel(epoch));
        assert_eq!(
            cache.publish(
                read,
                GeoTileData::Raster {
                    width: 256,
                    height: 256,
                    length: TILE_DIM * TILE_DIM * 4
                }
            ),
            Err(GeoError::StaleHandle)
        );
        assert_eq!(cache.frame(1), Some(&frame));
        assert_eq!(cache.stats().active_reads, 0);
        assert_eq!(cache.stats().pending_reserved_bytes, 0);
        let hit = cache
            .begin_frame(
                1,
                &camera(),
                &[GeoTileSource {
                    generation: 2,
                    ..raster()
                }],
                0,
            )
            .unwrap();
        assert!(cache.requests().is_empty());
        cache.commit_frame(hit).unwrap();
    }

    #[test]
    fn read_buffer_reservation_survives_cache_drop_and_duplicate_read_is_rejected() {
        let _lock = lock();
        let before = PROCESS_CHARGED.load(Ordering::SeqCst);
        let mut cache = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
        cache.begin_frame(1, &camera(), &[raster()], 0).unwrap();
        let request = cache.requests()[0];
        let read = cache.start_read(request.ticket).unwrap();
        assert!(matches!(
            cache.start_read(request.ticket),
            Err(GeoError::InvalidArgument)
        ));
        drop(cache);
        assert_eq!(
            PROCESS_CHARGED.load(Ordering::SeqCst),
            before + request.reserved_bytes
        );
        drop(read);
        assert_eq!(PROCESS_CHARGED.load(Ordering::SeqCst), before);
    }

    #[test]
    fn vector_payload_uses_shared_xygd_validator_and_preserves_full_ids() {
        let _lock = lock();
        let mut cache = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
        let epoch = cache.begin_frame(1, &camera(), &[vector()], 0).unwrap();
        let request = cache.requests()[0];
        let mut read = cache.start_read(request.ticket).unwrap();
        let bytes = point_bytes();
        read.bytes_mut()[..bytes.len()].copy_from_slice(&bytes);
        assert!(cache
            .publish(
                read,
                GeoTileData::VectorXygd {
                    length: bytes.len()
                }
            )
            .unwrap());
        let frame = cache.commit_frame(epoch).unwrap().clone();
        match cache.payload(frame.keys[0]).unwrap() {
            GeoTilePayload::Vector(column) => {
                assert_eq!(column.feature_ids(), [u64::MAX]);
                assert_eq!(column.xy(), [45., 40.]);
            }
            _ => panic!("wrong tile kind"),
        }
        let newer = cache
            .begin_frame(
                1,
                &camera(),
                &[GeoTileSource {
                    generation: 2,
                    ..vector()
                }],
                0,
            )
            .unwrap();
        let mut read = cache.start_read(cache.requests()[0].ticket).unwrap();
        let mut invalid = point_bytes();
        invalid[24..32].copy_from_slice(&3u64.to_le_bytes());
        read.bytes_mut()[..invalid.len()].copy_from_slice(&invalid);
        assert_eq!(
            cache.publish(
                read,
                GeoTileData::VectorXygd {
                    length: invalid.len()
                }
            ),
            Err(GeoError::ResourceLimit)
        );
        assert_eq!(cache.frame(1), Some(&frame));
        assert_eq!(cache.commit_frame(newer), Err(GeoError::StaleHandle));
    }

    #[test]
    fn process_pool_and_many_views_share_hard_limits_without_pinned_overshoot() {
        let _lock = lock();
        assert!(matches!(
            GeoTileCache::new(GeoTileLimits::default(), SOURCE_QUERY_RESERVE_BYTES + 1),
            Err(GeoError::ResourceLimit)
        ));
        assert!(matches!(
            GeoTileCache::new(
                GeoTileLimits {
                    max_bytes: TILE_CACHE_PROCESS_BYTES + 1,
                    ..GeoTileLimits::default()
                },
                0
            ),
            Err(GeoError::ResourceLimit)
        ));
        let mut cache = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
        for view in 0..5 {
            let epoch = cache.begin_frame(view, &camera(), &[raster()], 0).unwrap();
            if view == 0 {
                complete_raster(&mut cache, epoch);
            } else {
                assert!(cache.requests().is_empty());
                cache.commit_frame(epoch).unwrap();
            }
        }
        assert_eq!((cache.stats().views, cache.stats().entries), (5, 1));
        cache.drop_view(0);
        assert_eq!(cache.stats().views, 4);
        let source = GeoTileSource {
            kind: GeoTileKind::VectorXygd,
            payload_limits: GeoLimits {
                max_features: 1_000_000,
                max_vertices: 1,
                max_bytes: MAX_TILE_PAYLOAD_BYTES,
            },
            ..raster()
        };
        let view = GeoViewport {
            center_x: 0.0,
            center_y: 0.0,
            ..camera()
        };
        let mut first = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
        first
            .begin_frame(1, &view, std::slice::from_ref(&source), 0)
            .unwrap();
        let mut second = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
        assert_eq!(
            second.begin_frame(1, &view, std::slice::from_ref(&source), 0),
            Err(GeoError::ResourceLimit)
        );
        assert!(second.requests().is_empty());
        drop(first);
        second.begin_frame(1, &view, &[source], 0).unwrap();
        assert!(second.stats().process_charged_bytes <= TILE_CACHE_PROCESS_BYTES);
    }

    #[test]
    fn lru_evicts_only_unpinned_payloads_and_entry_admission_is_atomic() {
        let _lock = lock();
        let mut cache = GeoTileCache::new(
            GeoTileLimits {
                max_entries: 2,
                ..GeoTileLimits::default()
            },
            0,
        )
        .unwrap();
        let sources: Vec<_> = (1..=3)
            .map(|generation| GeoTileSource {
                generation,
                ..raster()
            })
            .collect();
        let mut keys = Vec::new();
        for source in &sources[..2] {
            let epoch = cache
                .begin_frame(1, &camera(), std::slice::from_ref(source), 0)
                .unwrap();
            complete_raster(&mut cache, epoch);
            keys.push(cache.frame(1).unwrap().keys[0]);
        }
        // Reusing generation1 refreshes recency without an I/O request.
        let hit = cache.begin_frame(1, &camera(), &sources[..1], 0).unwrap();
        assert!(cache.requests().is_empty());
        cache.commit_frame(hit).unwrap();
        let epoch = cache.begin_frame(1, &camera(), &sources[2..], 0).unwrap();
        assert!(cache.payload(keys[0]).is_some());
        assert!(cache.payload(keys[1]).is_none());
        assert_eq!(cache.frame(1).unwrap().keys, [keys[0]]);
        complete_raster(&mut cache, epoch);
        assert_eq!(cache.stats().entries, 2);

        let mut pinned = GeoTileCache::new(
            GeoTileLimits {
                max_entries: 1,
                ..GeoTileLimits::default()
            },
            0,
        )
        .unwrap();
        let epoch = pinned.begin_frame(1, &camera(), &sources[..1], 0).unwrap();
        complete_raster(&mut pinned, epoch);
        let old = pinned.frame(1).unwrap().clone();
        let before = pinned.stats();
        assert_eq!(
            pinned.begin_frame(2, &camera(), &sources[1..2], 0),
            Err(GeoError::ResourceLimit)
        );
        assert_eq!(pinned.frame(1), Some(&old));
        assert!(pinned.requests().is_empty());
        assert_eq!(pinned.stats(), before);
    }

    #[test]
    fn cancelled_read_window_is_bounded_until_buffers_are_dropped() {
        let _lock = lock();
        let mut cache = GeoTileCache::new(
            GeoTileLimits {
                max_pending: 2,
                ..GeoTileLimits::default()
            },
            0,
        )
        .unwrap();
        let mut reads = Vec::new();
        for generation in 1..=2 {
            let epoch = cache
                .begin_frame(
                    1,
                    &camera(),
                    &[GeoTileSource {
                        generation,
                        ..raster()
                    }],
                    0,
                )
                .unwrap();
            reads.push(cache.start_read(cache.requests()[0].ticket).unwrap());
            assert!(cache.cancel(epoch));
        }
        let charged = cache.stats().charged_bytes;
        assert_eq!(
            cache.begin_frame(
                1,
                &camera(),
                &[GeoTileSource {
                    generation: 3,
                    ..raster()
                }],
                0
            ),
            Err(GeoError::ResourceLimit)
        );
        assert_eq!(cache.stats().charged_bytes, charged);
        assert_eq!(cache.stats().active_reads, 2);
        drop(reads.pop());
        let epoch = cache
            .begin_frame(
                1,
                &camera(),
                &[GeoTileSource {
                    generation: 3,
                    ..raster()
                }],
                0,
            )
            .unwrap();
        assert_eq!(cache.stats().active_reads, 1);
        complete_raster(&mut cache, epoch);
        assert_eq!(
            cache.stats().pending_reserved_bytes,
            raster().reservation().unwrap()
        );
        drop(reads);
        let hit = cache
            .begin_frame(
                1,
                &camera(),
                &[GeoTileSource {
                    generation: 3,
                    ..raster()
                }],
                0,
            )
            .unwrap();
        cache.commit_frame(hit).unwrap();
        assert_eq!(cache.stats().active_reads, 0);
        assert_eq!(cache.stats().pending_reserved_bytes, 0);
    }

    #[test]
    fn foreign_or_abandoned_read_cannot_strand_an_authorized_candidate() {
        let _lock = lock();
        let mut owner = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
        let epoch = owner.begin_frame(1, &camera(), &[raster()], 0).unwrap();
        let read = owner.start_read(owner.requests()[0].ticket).unwrap();
        let mut foreign = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
        let before = foreign.stats().charged_bytes;
        assert_eq!(
            foreign.publish(
                read,
                GeoTileData::Raster {
                    width: 256,
                    height: 256,
                    length: TILE_DIM * TILE_DIM * 4
                }
            ),
            Err(GeoError::StaleHandle)
        );
        assert_eq!(foreign.stats().charged_bytes, before);
        // The owner detects the lost read lease before allocating any new
        // request and cancels that incomplete frame, freeing its reservation.
        let newer = owner.begin_frame(1, &camera(), &[raster()], 0).unwrap();
        assert_eq!(owner.stats().active_reads, 0);
        assert_eq!(owner.commit_frame(epoch), Err(GeoError::StaleHandle));
        complete_raster(&mut owner, newer);
        let old = owner.frame(1).unwrap().clone();
        let epoch = owner
            .begin_frame(
                1,
                &camera(),
                &[GeoTileSource {
                    generation: 2,
                    ..raster()
                }],
                0,
            )
            .unwrap();
        let read = owner.start_read(owner.requests()[0].ticket).unwrap();
        drop(read);
        let newer = owner
            .begin_frame(
                1,
                &camera(),
                &[GeoTileSource {
                    generation: 3,
                    ..raster()
                }],
                0,
            )
            .unwrap();
        assert_eq!(owner.commit_frame(epoch), Err(GeoError::StaleHandle));
        assert_eq!(owner.frame(1), Some(&old));
        complete_raster(&mut owner, newer);
    }

    #[test]
    fn prepared_candidate_can_fail_composition_without_replacing_the_old_frame() {
        let _lock = lock();
        let mut cache = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
        let epoch = cache.begin_frame(1, &camera(), &[raster()], 0).unwrap();
        complete_raster(&mut cache, epoch);
        let old = cache.frame(1).unwrap().clone();
        let sources = [GeoTileSource {
            generation: 2,
            ..raster()
        }];
        let epoch = cache.begin_frame(1, &camera(), &sources, 0).unwrap();
        assert!(matches!(
            cache.prepared_frame(epoch),
            Err(GeoError::InvalidArgument)
        ));
        for request in cache.requests().to_vec() {
            let read = cache.start_read(request.ticket).unwrap();
            cache
                .publish(
                    read,
                    GeoTileData::Raster {
                        width: 256,
                        height: 256,
                        length: TILE_DIM * TILE_DIM * 4,
                    },
                )
                .unwrap();
        }
        let prepared = cache.prepared_frame(epoch).unwrap();
        assert_eq!((prepared.view_id, prepared.epoch), (1, epoch));
        assert_eq!(*prepared.camera, camera().rebuild_key().unwrap());
        assert_eq!(prepared.sources, sources);
        assert!(prepared
            .keys
            .iter()
            .all(|key| cache.payload(*key).is_some()));
        assert_eq!(cache.frame(1), Some(&old));
        // An enclosing composer fails; dropping candidate output then
        // cancelling keeps the old camera, tiles and attribution intact.
        assert!(cache.cancel(epoch));
        assert!(matches!(
            cache.prepared_frame(epoch),
            Err(GeoError::StaleHandle)
        ));
        assert_eq!(cache.frame(1), Some(&old));
    }

    #[test]
    fn old_and_candidate_derived_memory_share_local_and_process_admission() {
        let _lock = lock();
        let source = raster();
        let max_bytes =
            METADATA_BYTES + source.payload_limits.max_bytes + source.reservation().unwrap();
        let mut cache = GeoTileCache::new(
            GeoTileLimits {
                max_bytes,
                ..GeoTileLimits::default()
            },
            0,
        )
        .unwrap();
        let epoch = cache.begin_frame(1, &camera(), &[source], 0).unwrap();
        complete_raster(&mut cache, epoch);
        let old = cache.frame(1).unwrap().clone();
        let old_scene = cache.reserve_derived(1).unwrap();
        assert_eq!(cache.stats().derived_reserved_bytes, 1);
        assert_eq!(
            cache.begin_frame(
                1,
                &camera(),
                &[GeoTileSource {
                    generation: 2,
                    ..raster()
                }],
                0
            ),
            Err(GeoError::ResourceLimit)
        );
        assert_eq!(cache.frame(1), Some(&old));
        drop(old_scene);
        let newer = cache
            .begin_frame(
                1,
                &camera(),
                &[GeoTileSource {
                    generation: 2,
                    ..raster()
                }],
                0,
            )
            .unwrap();
        assert_eq!(cache.stats().charged_bytes, max_bytes);
        assert!(matches!(
            cache.reserve_derived(1),
            Err(GeoError::ResourceLimit)
        ));
        assert!(cache.cancel(newer));
        assert_eq!(cache.stats().derived_reserved_bytes, 0);
        assert!(matches!(
            cache.reserve_derived(0),
            Err(GeoError::ResourceLimit)
        ));
        drop(cache);

        let before = PROCESS_CHARGED.load(Ordering::SeqCst);
        let first = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
        let bytes = TILE_CACHE_PROCESS_BYTES - before - 2 * METADATA_BYTES;
        let derived = first.reserve_derived(bytes).unwrap();
        let second = GeoTileCache::new(GeoTileLimits::default(), 0).unwrap();
        assert!(matches!(
            second.reserve_derived(1),
            Err(GeoError::ResourceLimit)
        ));
        drop(first);
        assert_eq!(
            PROCESS_CHARGED.load(Ordering::SeqCst),
            before + METADATA_BYTES + bytes
        );
        let second_derived = second.reserve_derived(METADATA_BYTES).unwrap();
        assert_eq!(second.stats().derived_reserved_bytes, METADATA_BYTES);
        drop(derived);
        drop(second);
        assert_eq!(
            PROCESS_CHARGED.load(Ordering::SeqCst),
            before + METADATA_BYTES
        );
        drop(second_derived);
        assert_eq!(PROCESS_CHARGED.load(Ordering::SeqCst), before);
    }
}
