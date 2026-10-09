//! Typed mixed-frame staging and immutable authority. Dossier §27/§29.
//! Registry order: snapshot (when exporting) -> mixed -> source -> tile.
use crate::geo::{GeoCrs, GeoError};
use crate::geo_mixed_frame::{
    GeoMixedCandidate, GeoMixedCoordinator, GeoMixedFrame, GeoMixedRequest, GeoMixedTicket,
    GeoMixedTileTime,
};
use crate::geo_source::{QueryBudget, SourceError, TimePredicate, MAX_PROCESSOR_BYTES};
use crate::geo_source_session::{GeoOperationSnapshot, GeoProcessorLease};
use crate::geo_tile_cache::{
    GeoDerivedLease, GeoTileCache, GeoTileKey, GeoTileKind, GeoTileLimits, GeoTileTime,
};
use crate::geo_tile_protocol::GeoTileProvenance;
use crate::geo_viewport::GeoViewport;
use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc, Mutex, OnceLock,
};

pub const HEADER: usize = 256;
pub const MAX_PACKET: usize = 32 << 20;
pub const MIXED_HANDLE_TAG: u64 = 1 << 63;
const MAX_COORDINATORS: usize = 4;
const MAX_DATA: usize = 8;
type Result<T> = std::result::Result<T, SourceError>;
fn invalid() -> SourceError {
    SourceError::InvalidFrame
}
fn limit() -> SourceError {
    SourceError::ResourceLimit
}
pub(crate) fn u32at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}
pub(crate) fn u64at(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}
fn p32(b: &mut [u8], at: usize, n: u32) {
    b[at..at + 4].copy_from_slice(&n.to_le_bytes());
}
fn p64(b: &mut [u8], at: usize, n: u64) {
    b[at..at + 8].copy_from_slice(&n.to_le_bytes());
}
fn zero(b: &[u8]) -> Result<()> {
    if b.iter().any(|n| *n != 0) {
        Err(invalid())
    } else {
        Ok(())
    }
}
fn checked(n: Option<usize>) -> Result<usize> {
    n.ok_or_else(limit)
}
pub fn is_mixed_handle(handle: u64) -> bool {
    handle & MIXED_HANDLE_TAG != 0
}
pub fn is_request(b: &[u8]) -> bool {
    b.get(..4) == Some(b"XYMX")
}

struct Anchor {
    handle: u64,
    sequence: u64,
    bytes: usize,
}
impl Anchor {
    fn retain(handle: u64, sequence: u64, budget: usize) -> Result<Self> {
        let reply =
            crate::geo_scale_protocol::execute(&source_request(26, handle, sequence, budget))?;
        Ok(Self {
            handle: u64at(&reply, 16),
            sequence,
            bytes: usize::try_from(u64at(&reply, 32)).map_err(|_| limit())?,
        })
    }
}
impl Drop for Anchor {
    fn drop(&mut self) {
        // The source mutex is not held here; every callback ends before owner drop.
        let _ = crate::geo_scale_protocol::execute(&source_request(10, self.handle, 0, 0));
    }
}
fn source_request(command: u32, handle: u64, sequence: u64, budget: usize) -> [u8; HEADER] {
    let mut b = [0; HEADER];
    b[..4].copy_from_slice(b"XYGQ");
    p32(&mut b, 4, 1);
    p32(&mut b, 8, command);
    p64(&mut b, 16, handle);
    p64(&mut b, 24, sequence);
    if budget != 0 {
        let q = QueryBudget::default();
        p64(&mut b, 32, budget as u64);
        p64(&mut b, 40, q.max_rows_examined);
        p64(&mut b, 48, q.max_read_bytes);
        p32(&mut b, 56, q.max_chunks as u32);
        p32(&mut b, 60, q.page_rows as u32);
    }
    b
}
struct Coordinator {
    value: GeoMixedCoordinator,
    nonce: u64,
}
struct Data {
    bytes: Vec<u8>,
    frame: Arc<GeoMixedFrame>,
    candidate: Option<GeoMixedCandidate>,
    ticket: GeoMixedTicket,
    coordinator: u64,
    nonce: u64,
    reads: u8,
    anchor: Anchor,
    _transfer: GeoDerivedLease,
}
enum Entry {
    Coordinator(Box<Coordinator>),
    Data(Box<Data>),
}
struct Registry {
    entries: Vec<(u64, Entry)>,
    cache: GeoTileCache,
    _metadata: GeoProcessorLease,
}
static NEXT_HANDLE: AtomicU64 = AtomicU64::new(1);
static REGISTRY: OnceLock<Mutex<Option<Registry>>> = OnceLock::new();
fn registry() -> &'static Mutex<Option<Registry>> {
    REGISTRY.get_or_init(|| Mutex::new(None))
}
fn initialize(slot: &mut Option<Registry>) -> Result<&mut Registry> {
    if slot.is_none() {
        let metadata = GeoProcessorLease::acquire(65536)?;
        let cache = GeoTileCache::new(GeoTileLimits::default(), 0)?;
        *slot = Some(Registry {
            entries: Vec::with_capacity(MAX_COORDINATORS + MAX_DATA),
            cache,
            _metadata: metadata,
        });
    }
    Ok(slot.as_mut().unwrap())
}
fn index(r: &Registry, handle: u64) -> Result<usize> {
    r.entries
        .iter()
        .position(|(h, _)| *h == handle)
        .ok_or(SourceError::StaleSource)
}
fn insert(r: &mut Registry, entry: Entry) -> Result<u64> {
    if r.entries.len() >= MAX_COORDINATORS + MAX_DATA {
        return Err(limit());
    }
    let handle = NEXT_HANDLE
        .fetch_update(Ordering::AcqRel, Ordering::Acquire, |n| {
            n.checked_add(1).filter(|n| *n < MIXED_HANDLE_TAG)
        })
        .map_err(|_| limit())?
        | MIXED_HANDLE_TAG;
    r.entries.push((handle, entry));
    Ok(handle)
}
fn reply(handle: u64, nonce: u64, owner: u64, bytes: usize, kind: u32) -> [u8; HEADER] {
    let mut b = [0; HEADER];
    b[..4].copy_from_slice(b"XYMY");
    p32(&mut b, 4, 1);
    p32(&mut b, 8, kind);
    p64(&mut b, 16, handle);
    p64(&mut b, 24, nonce);
    p64(&mut b, 32, owner);
    p64(&mut b, 40, bytes as u64);
    b
}
fn frame(b: &[u8]) -> Result<u32> {
    if b.len() < HEADER
        || b.len() > MAX_PACKET
        || !is_request(b)
        || u32at(b, 4) != 1
        || u64at(b, 40) != (b.len() - HEADER) as u64
    {
        return Err(invalid());
    }
    zero(&b[12..16])?;
    zero(&b[48..64])?;
    zero(&b[120..256])?;
    let cmd = u32at(b, 8);
    if !matches!(cmd, 1..=6 | 20) {
        return Err(invalid());
    }
    if cmd != 2 {
        zero(&b[64..120])?;
        if b.len() != HEADER {
            return Err(invalid());
        }
    }
    if cmd == 1 && (u64at(b, 16) != 0 || u64at(b, 24) != 0) {
        return Err(invalid());
    }
    if matches!(cmd, 1 | 3 | 4 | 5) && u64at(b, 32) != 0 {
        return Err(invalid());
    }
    if matches!(cmd, 2 | 6 | 20) && !(65536..=MAX_PROCESSOR_BYTES as u64).contains(&u64at(b, 32)) {
        return Err(limit());
    }
    if matches!(cmd, 2 | 5) && u64at(b, 24) != 0 {
        return Err(invalid());
    }
    Ok(cmd)
}

/// Camera bits and exact signed time are canonical, never normalized by hosts.
pub(crate) fn parse_snapshot(b: &[u8]) -> Result<GeoOperationSnapshot> {
    if b.len() != 160 || u32at(b, 4) > 1 {
        return Err(invalid());
    }
    zero(&b[132..136])?;
    zero(&b[152..160])?;
    let f = |at| f64::from_bits(u64at(b, at));
    let camera = GeoViewport::new(
        GeoCrs::from_u32(u32at(b, 0)).ok_or_else(invalid)?,
        f(8),
        f(16),
        f(24),
        f(32),
        f(40),
        f(48),
        f(56),
        u32at(b, 4) == 1,
    )?;
    let key = camera.rebuild_key()?;
    let time = match u32at(b, 128) {
        0 if u64at(b, 136) == 0 && u64at(b, 144) == 0 => TimePredicate::All,
        1 if u64at(b, 144) == 0 => TimePredicate::Instant(u64at(b, 136) as i64),
        2 => TimePredicate::Window {
            start: u64at(b, 136) as i64,
            end: u64at(b, 144) as i64,
        },
        _ => return Err(invalid()),
    };
    time.validate()?;
    let snapshot = GeoOperationSnapshot {
        source_digest: b[64..72].try_into().unwrap(),
        generation: u64at(b, 72),
        camera: key,
        time,
        layer_id: u64at(b, 80),
        camera_revision: u64at(b, 88),
        time_revision: u64at(b, 96),
        layer_revision: u64at(b, 104),
        style_revision: u64at(b, 112),
        state_revision: u64at(b, 120),
    };
    if snapshot_bytes(snapshot) != b {
        return Err(invalid());
    }
    Ok(snapshot)
}
pub(crate) fn snapshot_bytes(s: GeoOperationSnapshot) -> [u8; 160] {
    let mut b = [0; 160];
    p32(&mut b, 0, s.camera.crs as u32);
    p32(&mut b, 4, u32::from(s.camera.world_wrap));
    for (i, n) in [
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
        p64(&mut b, 8 + i * 8, n);
    }
    b[64..72].copy_from_slice(&s.source_digest);
    for (i, n) in [
        s.generation,
        s.layer_id,
        s.camera_revision,
        s.time_revision,
        s.layer_revision,
        s.style_revision,
        s.state_revision,
    ]
    .into_iter()
    .enumerate()
    {
        p64(&mut b, 72 + i * 8, n);
    }
    match s.time {
        TimePredicate::All => (),
        TimePredicate::Instant(t) => {
            p32(&mut b, 128, 1);
            p64(&mut b, 136, t as u64);
        }
        TimePredicate::Window { start, end } => {
            p32(&mut b, 128, 2);
            p64(&mut b, 136, start as u64);
            p64(&mut b, 144, end as u64);
        }
    }
    b
}
fn parse_request(b: &[u8]) -> Result<GeoMixedRequest> {
    let count = u32at(b, 116) as usize;
    if count > 64 || b.len() != HEADER + 160 + count * 96 {
        return Err(invalid());
    }
    let tile_time = match u32at(b, 112) {
        0 => GeoMixedTileTime::Timeless,
        1 => GeoMixedTileTime::ProducerWindow,
        _ => return Err(SourceError::InvalidTime),
    };
    let snapshot = parse_snapshot(&b[HEADER..HEADER + 160])?;
    let mut tiles = Vec::with_capacity(count);
    for s in b[HEADER + 160..].chunks_exact(96) {
        zero(&s[76..80])?;
        let time = match u32at(s, 56) {
            0 if u64at(s, 40) == 0 && u64at(s, 48) == 0 => None,
            1 => Some(GeoTileTime {
                start: u64at(s, 40) as i64,
                end: u64at(s, 48) as i64,
            }),
            _ => return Err(invalid()),
        };
        if time.is_some_and(|t| t.end <= t.start) {
            return Err(SourceError::InvalidTime);
        }
        let kind = match u32at(s, 60) {
            0 => GeoTileKind::RasterRgba,
            1 => GeoTileKind::VectorXygd,
            _ => return Err(invalid()),
        };
        let zoom = u32at(s, 64);
        if zoom > 25 || u32at(s, 68) >= 1 << zoom || u32at(s, 72) >= 1 << zoom {
            return Err(invalid());
        }
        let key = GeoTileKey {
            source_id: u64at(s, 0),
            generation: u64at(s, 8),
            layer_id: u64at(s, 16),
            layer_revision: u64at(s, 24),
            style_revision: u64at(s, 32),
            time,
            kind,
            zoom: zoom as u8,
            x: u32at(s, 68),
            y: u32at(s, 72),
        };
        if tiles.iter().any(|t: &GeoTileProvenance| t.key == key) {
            return Err(invalid());
        }
        tiles.push(GeoTileProvenance {
            key,
            config_digest: s[80..88].try_into().unwrap(),
            payload_digest: s[88..96].try_into().unwrap(),
        });
    }
    Ok(GeoMixedRequest {
        source_handle: u64at(b, 64),
        source_sequence: u64at(b, 72),
        snapshot,
        tile_handle: u64at(b, 80),
        tile_epoch: u64at(b, 88),
        tile_cache_handle: u64at(b, 96),
        tile_view_id: u64at(b, 104),
        tiles,
        tile_time,
    })
}

/// Mutations have fixed output. No length probe may create, prepare, retain or commit.
pub fn execute(b: &[u8]) -> Result<[u8; HEADER]> {
    let cmd = frame(b)?;
    if cmd == 20 {
        return Err(invalid());
    }
    let mut slot = registry().lock().map_err(|_| limit())?;
    let r = if cmd == 1 {
        initialize(&mut slot)?
    } else {
        slot.as_mut().ok_or(SourceError::StaleSource)?
    };
    let handle = u64at(b, 16);
    let nonce = u64at(b, 24);
    if cmd == 1 {
        if r.entries
            .iter()
            .filter(|(_, e)| matches!(e, Entry::Coordinator(_)))
            .count()
            >= MAX_COORDINATORS
        {
            return Err(limit());
        }
        let id = insert(
            r,
            Entry::Coordinator(Box::new(Coordinator {
                value: GeoMixedCoordinator::new()?,
                nonce: 0,
            })),
        )?;
        return Ok(reply(id, 0, 0, 0, 0));
    }
    let i = index(r, handle)?;
    if cmd == 5 {
        r.entries.remove(i);
        if r.entries.is_empty() {
            *slot = None;
        }
        return Ok(reply(handle, 0, 0, 0, 0));
    }
    if cmd == 2 {
        if r.entries
            .iter()
            .filter(|(_, e)| matches!(e, Entry::Data(_)))
            .count()
            >= MAX_DATA
        {
            return Err(limit());
        }
        let budget = u64at(b, 32) as usize;
        let _framing = GeoProcessorLease::acquire(16384)?;
        let request = parse_request(b)?;
        let anchor = Anchor::retain(request.source_handle, request.source_sequence, budget)?;
        let Entry::Coordinator(c) = &mut r.entries[i].1 else {
            return Err(invalid());
        };
        let next = c.nonce.checked_add(1).ok_or_else(limit)?;
        let ticket = c.value.begin(request.clone())?;
        c.nonce = next;
        let candidate = crate::geo_scale_protocol::with_scene_data(
            anchor.handle,
            anchor.sequence,
            |source| {
                crate::geo_tile_protocol::with_frame_data(
                    request.tile_handle,
                    request.tile_epoch,
                    |tile| {
                        c.value
                            .prepare_borrowed(ticket, source, tile, budget, &mut || false)
                    },
                )
                .map_err(SourceError::from)
            },
        )???;
        let frame = candidate.frame_arc();
        let length = checked(
            HEADER
                .checked_add(frame.scene().len())
                .and_then(|n| n.checked_add(frame.tile_receipt().len()))
                .and_then(|n| n.checked_add(160 + 48)),
        )?;
        if length > MAX_PACKET || checked(length.checked_mul(2))? > budget {
            return Err(limit());
        }
        let transfer = r.cache.reserve_derived(checked(
            length.checked_mul(7).and_then(|n| n.checked_add(65536)),
        )?)?;
        let mut bytes = vec![0; HEADER];
        bytes[..4].copy_from_slice(b"XYMF");
        p32(&mut bytes, 4, 1);
        p64(&mut bytes, 16, handle);
        p64(&mut bytes, 24, next);
        p64(&mut bytes, 32, frame.scene().len() as u64);
        p64(&mut bytes, 40, frame.tile_receipt().len() as u64);
        let rr = frame.retained_records();
        let sr = frame.retained_styles();
        for (at, n) in [(48, rr.start), (56, rr.end), (64, sr.start), (72, sr.end)] {
            p64(&mut bytes, at, n as u64);
        }
        p64(&mut bytes, 80, request.source_handle);
        p64(&mut bytes, 88, request.source_sequence);
        p64(&mut bytes, 96, request.tile_handle);
        p64(&mut bytes, 104, request.tile_epoch);
        p64(&mut bytes, 112, request.tile_cache_handle);
        p64(&mut bytes, 120, request.tile_view_id);
        p32(
            &mut bytes,
            128,
            u32::from(request.tile_time == GeoMixedTileTime::ProducerWindow),
        );
        p64(&mut bytes, 136, length as u64);
        p64(&mut bytes, 144, frame.result().visible_vertices);
        p64(&mut bytes, 152, frame.result().projected_vertices);
        bytes.reserve_exact(length - HEADER);
        bytes.extend_from_slice(frame.scene());
        bytes.extend_from_slice(frame.tile_receipt());
        bytes.extend_from_slice(&snapshot_bytes(request.snapshot));
        bytes.extend_from_slice(frame.style());
        let id = insert(
            r,
            Entry::Data(Box::new(Data {
                bytes,
                frame,
                candidate: Some(candidate),
                ticket,
                coordinator: handle,
                nonce: next,
                reads: 0,
                anchor,
                _transfer: transfer,
            })),
        )?;
        return Ok(reply(id, next, handle, length, 1));
    }
    let Entry::Data(data) = &r.entries[i].1 else {
        return Err(invalid());
    };
    if nonce == 0 || nonce != data.nonce {
        return Err(SourceError::StaleSource);
    }
    if cmd == 6 {
        let anchor = Anchor::retain(
            data.anchor.handle,
            data.anchor.sequence,
            u64at(b, 32) as usize,
        )?;
        let result = reply(anchor.handle, anchor.sequence, handle, anchor.bytes, 2);
        // Ownership transfers to the caller; explicit SourceData disposal is mandatory.
        std::mem::forget(anchor);
        return Ok(result);
    }
    let coordinator = data.coordinator;
    let ticket = data.ticket;
    let ci = index(r, coordinator)?;
    if cmd == 4 {
        let Entry::Coordinator(c) = &mut r.entries[ci].1 else {
            return Err(invalid());
        };
        c.value.cancel(ticket)?;
        let Entry::Data(data) = &mut r.entries[i].1 else {
            unreachable!()
        };
        data.candidate = None;
        return Ok(reply(handle, nonce, coordinator, 0, 0));
    }
    if cmd == 3 {
        // Check authority before consuming the candidate; stale failure keeps bytes/painter usable.
        let Entry::Coordinator(c) = &r.entries[ci].1 else {
            return Err(invalid());
        };
        if c.nonce != nonce {
            return Err(SourceError::StaleSource);
        }
        let Entry::Data(data) = &mut r.entries[i].1 else {
            unreachable!()
        };
        let candidate = data.candidate.take().ok_or(SourceError::StaleSource)?;
        let Entry::Coordinator(c) = &mut r.entries[ci].1 else {
            unreachable!()
        };
        c.value.commit(candidate)?;
        return Ok(reply(handle, nonce, coordinator, 0, 0));
    }
    Err(invalid())
}
pub fn data_len(b: &[u8], budget: usize) -> Result<usize> {
    if frame(b)? != 20 || budget > MAX_PROCESSOR_BYTES {
        return Err(invalid());
    }
    let slot = registry().lock().map_err(|_| limit())?;
    let r = slot.as_ref().ok_or(SourceError::StaleSource)?;
    let Entry::Data(d) = &r.entries[index(r, u64at(b, 16))?].1 else {
        return Err(invalid());
    };
    if d.nonce != u64at(b, 24) {
        return Err(SourceError::StaleSource);
    }
    if checked(d.bytes.len().checked_mul(2))? > budget.min(u64at(b, 32) as usize) {
        return Err(limit());
    }
    Ok(d.bytes.len())
}
pub fn read_data(b: &[u8], budget: usize) -> Result<Vec<u8>> {
    // Validate again under the mutation lock; a disposed owner cannot race a pure probe.
    let n = data_len(b, budget)?;
    let mut slot = registry().lock().map_err(|_| limit())?;
    let r = slot.as_mut().ok_or(SourceError::StaleSource)?;
    let i = index(r, u64at(b, 16))?;
    let Entry::Data(d) = &mut r.entries[i].1 else {
        return Err(invalid());
    };
    if d.nonce != u64at(b, 24) {
        return Err(SourceError::StaleSource);
    }
    if d.reads >= 2 {
        return Err(limit());
    }
    d.reads += 1;
    debug_assert_eq!(n, d.bytes.len());
    Ok(d.bytes.clone())
}
/// Borrows trusted private mixed authority. Callback may not reenter any registry.
pub fn with_frame_data<T>(
    handle: u64,
    nonce: u64,
    callback: impl FnOnce(&GeoMixedFrame) -> T,
) -> Result<T> {
    let slot = registry().lock().map_err(|_| limit())?;
    let r = slot.as_ref().ok_or(SourceError::StaleSource)?;
    let Entry::Data(d) = &r.entries[index(r, handle)?].1 else {
        return Err(invalid());
    };
    if d.nonce != nonce || nonce == 0 {
        return Err(SourceError::StaleSource);
    }
    Ok(callback(&d.frame))
}
pub(crate) fn with_source_scene<T>(
    handle: u64,
    nonce: u64,
    callback: impl FnOnce(&GeoMixedFrame, &[u8]) -> T,
) -> Result<T> {
    let slot = registry().lock().map_err(|_| limit())?;
    let r = slot.as_ref().ok_or(SourceError::StaleSource)?;
    let Entry::Data(d) = &r.entries[index(r, handle)?].1 else {
        return Err(invalid());
    };
    if d.nonce != nonce || nonce == 0 {
        return Err(SourceError::StaleSource);
    }
    crate::geo_scale_protocol::with_scene_data(d.anchor.handle, d.anchor.sequence, |source| {
        callback(&d.frame, source.scene)
    })
}
impl From<crate::geo_tile_protocol::TileProtocolError> for SourceError {
    fn from(e: crate::geo_tile_protocol::TileProtocolError) -> Self {
        match e {
            crate::geo_tile_protocol::TileProtocolError::Cancelled => Self::Cancelled,
            crate::geo_tile_protocol::TileProtocolError::Geo(GeoError::ResourceLimit) => {
                Self::ResourceLimit
            }
            crate::geo_tile_protocol::TileProtocolError::Geo(GeoError::StaleHandle) => {
                Self::StaleSource
            }
            crate::geo_tile_protocol::TileProtocolError::Geo(e) => Self::Geometry(e),
        }
    }
}

#[cfg(test)]
#[path = "geo_mixed_protocol_tests.rs"]
mod tests;
