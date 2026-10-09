//! Host-neutral, lease-owned geographic tile receipts (§22/§27/§29).
//! Hosts perform only explicitly authorized I/O and commit after painter staging.
use crate::geo::{GeoCrs, GeoError, GeoLimits};
use crate::geo_layers::{GeoLayerKind, GeoStyle};
use crate::geo_source::MAX_PROCESSOR_BYTES;
use crate::geo_source_session::GeoProcessorLease;
use crate::geo_tile_cache::{
    GeoDerivedLease, GeoTileCache, GeoTileData, GeoTileKey, GeoTileKind, GeoTileLimits,
    GeoTileLocation, GeoTileRead, GeoTileSource, GeoTileTicket, GeoTileTime,
};
use crate::geo_tile_scene::{GeoVectorTileStyle, TileSceneError};
use crate::geo_viewport::GeoViewport;
use crate::transition::Blake2s8;
use std::sync::{Mutex, OnceLock};
pub const HEADER: usize = 128;
pub const REPLY_BYTES: usize = 256;
pub const MAX_REQUEST: usize = 32 * 1024 * 1024;
const MAX_HANDLES: usize = 80;
const MAX_CACHES: usize = 4;
const MAX_READS: usize = 64;
const MAX_FRAMES: usize = 8;
type Result<T> = std::result::Result<T, TileProtocolError>;
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TileProtocolError {
    Geo(GeoError),
    Cancelled,
}
impl From<GeoError> for TileProtocolError {
    fn from(e: GeoError) -> Self {
        Self::Geo(e)
    }
}
impl From<crate::geo_source::SourceError> for TileProtocolError {
    fn from(e: crate::geo_source::SourceError) -> Self {
        use crate::geo_source::SourceError;
        match e {
            SourceError::Geometry(g) => g.into(),
            SourceError::Cancelled => Self::Cancelled,
            SourceError::ResourceLimit => GeoError::ResourceLimit.into(),
            SourceError::StaleSource => GeoError::StaleHandle.into(),
            _ => GeoError::InvalidArgument.into(),
        }
    }
}
impl From<TileSceneError> for TileProtocolError {
    fn from(e: TileSceneError) -> Self {
        match e {
            TileSceneError::Geo(g) => g.into(),
            TileSceneError::Cancelled => Self::Cancelled,
        }
    }
}
fn invalid() -> TileProtocolError {
    GeoError::InvalidArgument.into()
}
fn stale() -> TileProtocolError {
    GeoError::StaleHandle.into()
}
fn resource() -> TileProtocolError {
    GeoError::ResourceLimit.into()
}
fn u32at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}
fn u64at(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}
fn p32(b: &mut [u8], at: usize, n: u32) {
    b[at..at + 4].copy_from_slice(&n.to_le_bytes())
}
fn p64(b: &mut [u8], at: usize, n: u64) {
    b[at..at + 8].copy_from_slice(&n.to_le_bytes())
}
fn zero(b: &[u8]) -> Result<()> {
    if b.iter().any(|&v| v != 0) {
        Err(invalid())
    } else {
        Ok(())
    }
}
fn checked(n: Option<usize>) -> Result<usize> {
    n.ok_or_else(resource)
}
fn align(n: usize) -> Result<usize> {
    Ok(checked(n.checked_add(7))? & !7)
}
fn take<'a>(b: &'a [u8], at: &mut usize, n: usize) -> Result<&'a [u8]> {
    let end = checked(at.checked_add(n))?;
    let v = b.get(*at..end).ok_or_else(invalid)?;
    *at = end;
    Ok(v)
}
fn text(b: &[u8]) -> Result<String> {
    if b.len() > 4096 {
        return Err(resource());
    }
    let s = std::str::from_utf8(b).map_err(|_| invalid())?;
    if s.trim().is_empty() || s.chars().any(|c| c.is_control()) {
        return Err(invalid());
    }
    Ok(s.to_owned())
}
fn reply(handle: u64, epoch: u64) -> [u8; REPLY_BYTES] {
    let mut b = [0; REPLY_BYTES];
    b[..4].copy_from_slice(b"XYGU");
    p32(&mut b, 4, 1);
    p64(&mut b, 16, handle);
    p64(&mut b, 24, epoch);
    b
}
fn frame(b: &[u8]) -> Result<u32> {
    if b.len() < HEADER
        || b.len() > MAX_REQUEST
        || &b[..4] != b"XYGT"
        || u32at(b, 4) != 1
        || u64at(b, 48) != (b.len() - HEADER) as u64
    {
        return Err(invalid());
    }
    zero(&b[12..16])?;
    zero(&b[56..128])?;
    let cmd = u32at(b, 8);
    if !matches!(cmd, 1..=10 | 21 | 22) {
        return Err(invalid());
    }
    if cmd != 2 && cmd != 8 {
        zero(&b[32..40])?;
    }
    if !matches!(cmd, 2 | 6 | 21 | 22) {
        zero(&b[40..48])?;
    }
    if cmd == 1 {
        zero(&b[16..40])?;
    }
    if !matches!(cmd, 2 | 4 | 6) && b.len() != HEADER {
        return Err(invalid());
    }
    Ok(cmd)
}
#[derive(Clone, Copy)]
struct SourceStamp {
    id: u64,
    generation: u64,
    layer: u64,
    digest: [u8; 8],
}
#[derive(Clone, Copy)]
struct StyleStamp {
    layer: u64,
    revision: u64,
    digest: [u8; 8],
}
struct CacheOwner {
    cache: GeoTileCache,
    epoch: u64,
    view: u64,
    stamps: Vec<SourceStamp>,
    styles: Vec<StyleStamp>,
    payloads: Vec<(GeoTileKey, [u8; 8])>,
    _metadata: GeoProcessorLease,
}
struct ReadOwner {
    read: Option<GeoTileRead>,
    ticket: GeoTileTicket,
    cache: u64,
    max_bytes: usize,
    location: GeoTileLocation,
    receipt_reads: u8,
    _host: GeoDerivedLease,
}
struct FrameOwner {
    bytes: Vec<u8>,
    camera: crate::geo_viewport::GeoViewportRebuildKey,
    keys: Vec<GeoTileKey>,
    sources: Vec<GeoTileSource>,
    provenance: Vec<GeoTileProvenance>,
    cache: u64,
    epoch: u64,
    view: u64,
    reads: u8,
    _transfer: GeoDerivedLease,
}
enum Entry {
    Cache(Box<CacheOwner>),
    Read(Box<ReadOwner>),
    Frame(Box<FrameOwner>),
}
struct Registry {
    next: u64,
    entries: Vec<(u64, Entry)>,
}
static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();
fn registry() -> &'static Mutex<Registry> {
    REGISTRY.get_or_init(|| {
        Mutex::new(Registry {
            next: 1,
            entries: Vec::new(),
        })
    })
}
fn insert(r: &mut Registry, e: Entry) -> Result<u64> {
    if r.entries.len() >= MAX_HANDLES {
        return Err(resource());
    }
    let id = r.next;
    r.next = r.next.checked_add(1).ok_or_else(resource)?;
    r.entries.push((id, e));
    Ok(id)
}
fn index(r: &Registry, id: u64) -> Result<usize> {
    r.entries
        .iter()
        .position(|(h, _)| *h == id)
        .ok_or_else(stale)
}
fn cache(r: &Registry, id: u64) -> Result<&CacheOwner> {
    match &r.entries[index(r, id)?].1 {
        Entry::Cache(c) => Ok(c),
        _ => Err(invalid()),
    }
}
fn cache_mut(r: &mut Registry, id: u64) -> Result<&mut CacheOwner> {
    let i = index(r, id)?;
    match &mut r.entries[i].1 {
        Entry::Cache(c) => Ok(c),
        _ => Err(invalid()),
    }
}
fn budget(b: &[u8]) -> Result<usize> {
    let v = usize::try_from(u64at(b, 40)).map_err(|_| resource())?;
    if v < 65536 || v > MAX_PROCESSOR_BYTES {
        return Err(resource());
    }
    Ok(v)
}
fn phase(max: usize) -> Result<GeoProcessorLease> {
    let remaining = MAX_PROCESSOR_BYTES
        .saturating_sub(GeoProcessorLease::live_bytes())
        .min(max);
    if remaining < 65536 {
        return Err(resource());
    }
    Ok(GeoProcessorLease::acquire(remaining)?)
}
fn parse_begin(bytes: &[u8]) -> Result<(GeoViewport, Vec<GeoTileSource>, Vec<SourceStamp>)> {
    if bytes.len() < 80 {
        return Err(invalid());
    }
    zero(&bytes[68..80])?;
    if u32at(bytes, 4) > 1 {
        return Err(invalid());
    }
    let f = |at| f64::from_bits(u64at(bytes, at));
    let camera = GeoViewport::new(
        GeoCrs::from_u32(u32at(bytes, 0)).ok_or_else(invalid)?,
        f(8),
        f(16),
        f(24),
        f(32),
        f(40),
        f(48),
        f(56),
        u32at(bytes, 4) == 1,
    )?;
    let count = u32at(bytes, 64) as usize;
    if count > 16 {
        return Err(resource());
    }
    let mut at = 80;
    let mut sources = Vec::with_capacity(count);
    let mut stamps = Vec::with_capacity(count);
    for _ in 0..count {
        let h = take(bytes, &mut at, 112)?;
        zero(&h[66..72])?;
        zero(&h[108..112])?;
        if u32at(h, 56) > 1 {
            return Err(invalid());
        }
        let kind = match u32at(h, 60) {
            0 => GeoTileKind::RasterRgba,
            1 => GeoTileKind::VectorXygd,
            _ => return Err(invalid()),
        };
        let locator = take(bytes, &mut at, u32at(h, 96) as usize)?;
        let attr = take(bytes, &mut at, u32at(h, 100) as usize)?;
        let location = match u32at(h, 104) {
            0 if attr.is_empty() => GeoTileLocation::Local {
                locator: text(locator)?,
            },
            1 => GeoTileLocation::Network {
                template: text(locator)?,
                attribution: text(attr)?,
            },
            _ => return Err(invalid()),
        };
        let time = if u32at(h, 56) == 1 {
            Some(GeoTileTime {
                start: u64at(h, 40) as i64,
                end: u64at(h, 48) as i64,
            })
        } else {
            zero(&h[40..56])?;
            None
        };
        let limits = GeoLimits {
            max_bytes: usize::try_from(u64at(h, 72)).map_err(|_| resource())?,
            max_features: usize::try_from(u64at(h, 80)).map_err(|_| resource())?,
            max_vertices: usize::try_from(u64at(h, 88)).map_err(|_| resource())?,
        };
        let mut digest = Blake2s8::new();
        digest.update(b"xyg-tile-source-config-v1");
        for part in [&h[60..66], &h[72..112], locator, attr] {
            digest.update(&(part.len() as u64).to_le_bytes());
            digest.update(part);
        }
        stamps.push(SourceStamp {
            id: u64at(h, 0),
            generation: u64at(h, 8),
            layer: u64at(h, 16),
            digest: digest.finish(),
        });
        sources.push(GeoTileSource {
            source_id: u64at(h, 0),
            generation: u64at(h, 8),
            layer_id: u64at(h, 16),
            layer_revision: u64at(h, 24),
            style_revision: u64at(h, 32),
            time,
            kind,
            location,
            min_zoom: h[64],
            max_zoom: h[65],
            payload_limits: limits,
        });
    }
    if at != bytes.len() {
        return Err(invalid());
    }
    Ok((camera, sources, stamps))
}
fn write_key(b: &mut [u8], key: GeoTileKey) {
    for (at, n) in [
        (0, key.source_id),
        (8, key.generation),
        (16, key.layer_id),
        (24, key.layer_revision),
        (32, key.style_revision),
    ] {
        p64(b, at, n);
    }
    if let Some(t) = key.time {
        p64(b, 40, t.start as u64);
        p64(b, 48, t.end as u64);
        p32(b, 56, 1);
    }
    p32(
        b,
        60,
        match key.kind {
            GeoTileKind::RasterRgba => 0,
            GeoTileKind::VectorXygd => 1,
        },
    );
    p32(b, 64, key.zoom as u32);
    p32(b, 68, key.x);
    p32(b, 72, key.y);
}
fn write_ticket(b: &mut [u8], t: GeoTileTicket) {
    p64(b, 0, t.cache_id as u64);
    p64(b, 8, t.epoch);
    p32(b, 16, t.ordinal);
    write_key(&mut b[24..104], t.key);
}
fn location_parts(location: &GeoTileLocation) -> (u32, &str, &str) {
    match location {
        GeoTileLocation::Local { locator } => (0, locator, ""),
        GeoTileLocation::Network {
            template,
            attribution,
        } => (1, template, attribution),
    }
}
fn read_receipt(read: &ReadOwner, handle: u64) -> Vec<u8> {
    let (kind, locator, attr) = location_parts(&read.location);
    let mut b = reply(handle, read.ticket.epoch).to_vec();
    p32(&mut b, 8, 2);
    p64(&mut b, 32, read.max_bytes as u64);
    p32(&mut b, 48, kind);
    p32(&mut b, 52, locator.len() as u32);
    p32(&mut b, 56, attr.len() as u32);
    write_ticket(&mut b[64..168], read.ticket);
    b.extend_from_slice(locator.as_bytes());
    b.extend_from_slice(attr.as_bytes());
    b
}
fn parse_styles(b: &[u8]) -> Result<(u64, Vec<GeoVectorTileStyle>, &[u8])> {
    if b.len() < 32 {
        return Err(invalid());
    }
    zero(&b[12..16])?;
    zero(&b[24..32])?;
    let count = u32at(b, 8) as usize;
    if count > 64 {
        return Err(resource());
    }
    let mut at = 32;
    let mut styles = Vec::with_capacity(count);
    for _ in 0..count {
        let h = take(b, &mut at, 64)?;
        zero(&h[12..16])?;
        zero(&h[49..64])?;
        let kind = match u32at(h, 8) {
            1 => GeoLayerKind::Points,
            2 => GeoLayerKind::Bubbles,
            3 => GeoLayerKind::Routes,
            4 => GeoLayerKind::Arcs,
            5 => GeoLayerKind::Polygons,
            6 => GeoLayerKind::Choropleth,
            7 => GeoLayerKind::Density,
            _ => return Err(invalid()),
        };
        let style = GeoStyle {
            fill: h[16..20].try_into().unwrap(),
            stroke: h[20..24].try_into().unwrap(),
            stroke_width: f64::from_bits(u64at(h, 24)),
            diameter: f64::from_bits(u64at(h, 32)),
            opacity: f64::from_bits(u64at(h, 40)),
            symbol: h[48],
        };
        crate::geo_layers::validate_style(style)?;
        styles.push(GeoVectorTileStyle {
            layer_id: u64at(h, 0),
            kind,
            style,
        });
    }
    let catalog = take(
        b,
        &mut at,
        usize::try_from(u64at(b, 16)).map_err(|_| resource())?,
    )?;
    if at != b.len() || catalog.len() < 128 || u32at(catalog, 12) & 2 != 0 {
        return Err(invalid());
    }
    Ok((u64at(b, 0), styles, catalog))
}
/// Fixed response mutations. No size probe may execute these commands.
pub fn execute(request: &[u8]) -> Result<[u8; REPLY_BYTES]> {
    let command = frame(request)?;
    if command >= 20 {
        return Err(invalid());
    }
    let handle = u64at(request, 16);
    let epoch = u64at(request, 24);
    let view = u64at(request, 32);
    let payload = &request[HEADER..];
    let mut r = registry().lock().map_err(|_| resource())?;
    if matches!(command, 1 | 3 | 6) && r.entries.len() >= MAX_HANDLES {
        return Err(resource());
    }
    if command == 1 {
        if r.entries
            .iter()
            .filter(|(_, e)| matches!(e, Entry::Cache(_)))
            .count()
            >= MAX_CACHES
        {
            return Err(resource());
        }
        let meta = GeoProcessorLease::acquire(65536)?;
        let c = GeoTileCache::new(GeoTileLimits::default(), GeoProcessorLease::live_bytes())?;
        let id = insert(
            &mut r,
            Entry::Cache(Box::new(CacheOwner {
                cache: c,
                epoch: 0,
                view: 0,
                stamps: Vec::with_capacity(128),
                styles: Vec::with_capacity(128),
                payloads: Vec::with_capacity(128),
                _metadata: meta,
            })),
        )?;
        return Ok(reply(id, 0));
    }
    if command == 2 {
        if epoch != 0 {
            return Err(invalid());
        }
        let lease = phase(budget(request)?)?;
        if checked(payload.len().checked_mul(3))? > lease.bytes() {
            return Err(resource());
        }
        let (camera, sources, stamps) = parse_begin(payload)?;
        let owner = cache_mut(&mut r, handle)?;
        let mut added = 0;
        for s in &stamps {
            if let Some(old) = owner.stamps.iter().find(|old| {
                old.id == s.id && old.layer == s.layer && old.generation == s.generation
            }) {
                if old.digest != s.digest {
                    return Err(stale());
                }
            } else {
                added += 1;
            }
        }
        if owner.stamps.len() + added > 128 {
            return Err(resource());
        }
        let epoch =
            owner
                .cache
                .begin_frame(view, &camera, &sources, GeoProcessorLease::live_bytes())?;
        for s in stamps {
            if !owner
                .stamps
                .iter()
                .any(|old| old.id == s.id && old.layer == s.layer && old.generation == s.generation)
            {
                owner.stamps.push(s);
            }
        }
        owner.epoch = epoch;
        owner.view = view;
        let mut b = reply(handle, epoch);
        p64(&mut b, 32, owner.cache.requests().len() as u64);
        p64(&mut b, 40, view);
        return Ok(b);
    }
    if command == 3 {
        if r.entries
            .iter()
            .filter(|(_, e)| matches!(e, Entry::Read(_)))
            .count()
            >= MAX_READS
        {
            return Err(resource());
        }
        let owner = cache(&r, handle)?;
        if owner.epoch != epoch || epoch == 0 {
            return Err(stale());
        }
        let req = owner
            .cache
            .requests()
            .iter()
            .find(|req| {
                !r.entries
                    .iter()
                    .any(|(_, e)| matches!(e,Entry::Read(read) if read.ticket==req.ticket))
            })
            .copied();
        let Some(req) = req else {
            return Ok(reply(0, epoch));
        };
        let source = owner.cache.request_source(req.ticket).ok_or_else(stale)?;
        let host = owner.cache.reserve_derived(checked(
            req.max_payload_bytes
                .checked_mul(3)
                .and_then(|n| n.checked_add(65536)),
        )?)?;
        let location = source.location.clone();
        let read = cache_mut(&mut r, handle)?.cache.start_read(req.ticket)?;
        let id = insert(
            &mut r,
            Entry::Read(Box::new(ReadOwner {
                read: Some(read),
                ticket: req.ticket,
                cache: handle,
                max_bytes: req.max_payload_bytes,
                location,
                receipt_reads: 0,
                _host: host,
            })),
        )?;
        let mut b = reply(id, epoch);
        p32(&mut b, 8, 1);
        p64(&mut b, 32, req.max_payload_bytes as u64);
        p64(&mut b, 40, req.reserved_bytes as u64);
        write_ticket(&mut b[64..168], req.ticket);
        return Ok(b);
    }
    if command == 4 {
        let i = index(&r, handle)?;
        let Entry::Read(read) = &mut r.entries[i].1 else {
            return Err(invalid());
        };
        if read.ticket.epoch != epoch {
            return Err(stale());
        }
        if payload.len() > read.max_bytes {
            return Err(resource());
        }
        let mut owned = read.read.take().ok_or_else(stale)?;
        let ticket = read.ticket;
        let cache_id = read.cache;
        owned.bytes_mut()[..payload.len()].copy_from_slice(payload);
        let data = match ticket.key.kind {
            GeoTileKind::RasterRgba => GeoTileData::Raster {
                width: 256,
                height: 256,
                length: payload.len(),
            },
            GeoTileKind::VectorXygd => GeoTileData::VectorXygd {
                length: payload.len(),
            },
        };
        let owner = cache_mut(&mut r, cache_id)?;
        let mut digest = Blake2s8::new();
        digest.update(b"xyg-tile-payload-v1");
        digest.update(payload);
        let digest = digest.finish();
        let complete = match owner.cache.publish(owned, data) {
            Ok(complete) => complete,
            Err(error) => {
                if owner.epoch == ticket.epoch {
                    owner.epoch = 0;
                }
                return Err(error.into());
            }
        };
        owner
            .payloads
            .retain(|(key, _)| owner.cache.payload(*key).is_some() && *key != ticket.key);
        if owner.payloads.len() >= 128 {
            return Err(resource());
        }
        owner.payloads.push((ticket.key, digest));
        let mut b = reply(handle, epoch);
        p32(&mut b, 8, u32::from(complete));
        return Ok(b);
    }
    if command == 5 {
        let i = index(&r, handle)?;
        let Entry::Read(read) = &r.entries[i].1 else {
            return Err(invalid());
        };
        if read.ticket.epoch != epoch {
            return Err(stale());
        }
        let (cache_id, abandoned) = (read.cache, read.read.is_some());
        if abandoned {
            if let Ok(owner) = cache_mut(&mut r, cache_id) {
                if owner.cache.cancel(epoch) {
                    owner.epoch = 0;
                }
            }
        }
        r.entries.remove(i);
        return Ok(reply(handle, epoch));
    }
    if command == 6 {
        if r.entries
            .iter()
            .filter(|(_, e)| matches!(e, Entry::Frame(_)))
            .count()
            >= MAX_FRAMES
        {
            return Err(resource());
        }
        let processor = phase(budget(request)?)?;
        let (image_id, styles, catalog) = parse_styles(payload)?;
        let owner = cache_mut(&mut r, handle)?;
        if owner.epoch != epoch || epoch == 0 {
            return Err(stale());
        }
        let frame = owner.cache.prepared_frame(epoch)?;
        let mut proposed_styles = Vec::with_capacity(styles.len());
        for (i, style) in styles.iter().enumerate() {
            if styles[..i].iter().any(|old| old.layer_id == style.layer_id) {
                return Err(invalid());
            }
            let mut digest = Blake2s8::new();
            digest.update(b"xyg-tile-style-v1");
            digest.update(&payload[32 + i * 64..32 + (i + 1) * 64]);
            let digest = digest.finish();
            let sources: Vec<_> = frame
                .sources
                .iter()
                .filter(|source| {
                    source.layer_id == style.layer_id && source.kind == GeoTileKind::VectorXygd
                })
                .collect();
            if sources.is_empty() {
                return Err(invalid());
            }
            for source in sources {
                let stamp = StyleStamp {
                    layer: style.layer_id,
                    revision: source.style_revision,
                    digest,
                };
                if let Some(old) = owner
                    .styles
                    .iter()
                    .find(|old| old.layer == stamp.layer && old.revision == stamp.revision)
                {
                    if old.digest != stamp.digest {
                        return Err(stale());
                    }
                } else if !proposed_styles.iter().any(|old: &StyleStamp| {
                    old.layer == stamp.layer && old.revision == stamp.revision
                }) {
                    proposed_styles.push(stamp);
                }
            }
        }
        if owner.styles.len() + proposed_styles.len() > 128 {
            return Err(resource());
        }
        let view = frame.view_id;
        let keys = frame.keys.to_vec();
        let camera = *frame.camera;
        let sources = frame.sources.to_vec();
        let mut provenance = Vec::with_capacity(keys.len());
        for key in &keys {
            let config_digest = owner
                .stamps
                .iter()
                .find(|stamp| {
                    stamp.id == key.source_id
                        && stamp.generation == key.generation
                        && stamp.layer == key.layer_id
                })
                .ok_or_else(stale)?
                .digest;
            let payload_digest = owner
                .payloads
                .iter()
                .find(|(stored, _)| stored == key)
                .ok_or_else(stale)?
                .1;
            provenance.push(GeoTileProvenance {
                key: *key,
                config_digest,
                payload_digest,
            });
        }
        let semantic_bytes = sources.iter().try_fold(
            keys.capacity() * std::mem::size_of::<GeoTileKey>()
                + provenance.capacity() * std::mem::size_of::<GeoTileProvenance>()
                + sources.capacity() * std::mem::size_of::<GeoTileSource>(),
            |bytes, source| {
                let (_, a, b) = location_parts(&source.location);
                bytes
                    .checked_add(a.len())
                    .and_then(|n| n.checked_add(b.len()))
                    .ok_or_else(resource)
            },
        )?;
        let attrs: Vec<&str> = frame
            .sources
            .iter()
            .filter_map(|source| match &source.location {
                GeoTileLocation::Network { attribution, .. } => Some(attribution.as_str()),
                _ => None,
            })
            .collect();
        let attr_bytes = attrs
            .iter()
            .try_fold(0usize, |n, a| checked(n.checked_add(align(a.len() + 8)?)))?;
        let prefix = checked(
            REPLY_BYTES
                .checked_add(keys.len() * 80)
                .and_then(|n| n.checked_add(attr_bytes)),
        )?;
        let mut charge = None;
        let mut transfer = None;
        let result = crate::geo_layers_protocol::execute_with_compiler(
            catalog,
            processor.bytes(),
            &mut |input| {
                drop(charge.take());
                drop(transfer.take());
                let prepared = crate::geo_tile_scene::compile_tile_frame(
                    &owner.cache,
                    epoch,
                    input,
                    image_id,
                    &styles,
                    &mut || false,
                )
                .map_err(|e| match e {
                    TileSceneError::Geo(g) => g,
                    TileSceneError::Cancelled => GeoError::InvalidArgument,
                })?;
                let (compiled, held) = prepared.into_parts();
                charge = Some(held);
                let doc = crate::scene::SceneDocument::decode(&compiled.scene)
                    .map_err(|_| GeoError::InvalidArgument)?;
                if attrs.iter().any(|a| !doc.has_visible_attribution(a)) {
                    return Err(GeoError::InvalidArgument);
                }
                let length = crate::geo_layers_protocol::encoded_size(&compiled, None)?;
                let total = align(length)
                    .map_err(|_| GeoError::ResourceLimit)?
                    .checked_add(prefix)
                    .ok_or(GeoError::ResourceLimit)?;
                transfer = Some(
                    owner.cache.reserve_derived(
                        total
                            .checked_mul(7)
                            .and_then(|n| n.checked_add(65536))
                            .and_then(|n| n.checked_add(semantic_bytes))
                            .ok_or(GeoError::ResourceLimit)?,
                    )?,
                );
                Ok(compiled)
            },
        );
        let catalog = match result {
            Ok(bytes) => bytes,
            Err(e) => {
                drop(charge);
                drop(transfer);
                owner.cache.cancel(epoch);
                owner.epoch = 0;
                return Err(e.into());
            }
        };
        drop(charge);
        let transfer = transfer.ok_or_else(resource)?;
        let size = checked(prefix.checked_add(align(catalog.len())?))?;
        let mut bytes = vec![0; size];
        bytes[..REPLY_BYTES].copy_from_slice(&reply(handle, epoch));
        p32(&mut bytes, 8, 1);
        p64(&mut bytes, 32, view);
        p64(&mut bytes, 40, catalog.len() as u64);
        p64(&mut bytes, 48, keys.len() as u64);
        p64(&mut bytes, 56, attrs.len() as u64);
        p64(&mut bytes, 64, attr_bytes as u64);
        p32(&mut bytes, 72, camera.crs as u32);
        p32(&mut bytes, 76, u32::from(camera.world_wrap));
        for (i, n) in [
            camera.center_x_bits,
            camera.center_y_bits,
            camera.zoom_bits,
            camera.width_bits,
            camera.height_bits,
            camera.bearing_deg_bits,
            camera.pitch_deg_bits,
        ]
        .into_iter()
        .enumerate()
        {
            p64(&mut bytes, 80 + i * 8, n);
        }
        bytes[REPLY_BYTES..REPLY_BYTES + catalog.len()].copy_from_slice(&catalog);
        let mut at = REPLY_BYTES + align(catalog.len())?;
        for key in &keys {
            write_key(&mut bytes[at..at + 80], *key);
            at += 80;
        }
        for attr in attrs {
            p32(&mut bytes, at, attr.len() as u32);
            bytes[at + 8..at + 8 + attr.len()].copy_from_slice(attr.as_bytes());
            at += align(attr.len() + 8)?;
        }
        let mut digest = Blake2s8::new();
        digest.update(b"xyg-tile-scene-receipt-v1");
        digest.update(&bytes[..136]);
        digest.update(&bytes[REPLY_BYTES..]);
        bytes[136..144].copy_from_slice(&digest.finish());
        let len = bytes.len();
        let id = insert(
            &mut r,
            Entry::Frame(Box::new(FrameOwner {
                bytes,
                camera,
                keys,
                sources,
                provenance,
                cache: handle,
                epoch,
                view,
                reads: 0,
                _transfer: transfer,
            })),
        )?;
        cache_mut(&mut r, handle)?.styles.extend(proposed_styles);
        let mut out = reply(id, epoch);
        p64(&mut out, 32, len as u64);
        p64(&mut out, 40, handle);
        p64(&mut out, 48, view);
        return Ok(out);
    }
    if command == 7 {
        let i = index(&r, handle)?;
        let Entry::Frame(f) = &r.entries[i].1 else {
            return Err(invalid());
        };
        if f.epoch != epoch {
            return Err(stale());
        }
        let (id, view) = (f.cache, f.view);
        let owner = cache_mut(&mut r, id)?;
        if owner.epoch != epoch {
            return Err(stale());
        }
        owner.cache.commit_frame(epoch)?;
        owner.epoch = 0;
        let mut out = reply(handle, epoch);
        p64(&mut out, 32, view);
        return Ok(out);
    }
    if command == 8 {
        let owner = cache_mut(&mut r, handle)?;
        let newest = owner
            .cache
            .frame(view)
            .map_or(0, |f| f.epoch)
            .max(if owner.view == view { owner.epoch } else { 0 });
        if newest != epoch || epoch == 0 {
            return Err(stale());
        }
        owner.cache.drop_view(view);
        if owner.view == view {
            owner.epoch = 0;
        }
        return Ok(reply(handle, epoch));
    }
    if command == 9 {
        let owner = cache_mut(&mut r, handle)?;
        let cancelled = owner.cache.cancel(epoch);
        if cancelled {
            owner.epoch = 0;
        }
        let mut b = reply(handle, epoch);
        p32(&mut b, 8, u32::from(cancelled));
        return Ok(b);
    }
    if command == 10 {
        let i = index(&r, handle)?;
        r.entries.remove(i);
        return Ok(reply(handle, epoch));
    }
    Err(invalid())
}
/// Pure size probe does not consume either admitted ownership transfer.
pub fn data_len(request: &[u8], max: usize) -> Result<usize> {
    let cmd = frame(request)?;
    if !matches!(cmd, 21 | 22) || max > MAX_PROCESSOR_BYTES {
        return Err(invalid());
    }
    let r = registry().lock().map_err(|_| resource())?;
    let handle = u64at(request, 16);
    let epoch = u64at(request, 24);
    let n = match (&r.entries[index(&r, handle)?].1, cmd) {
        (Entry::Read(read), 21) if read.ticket.epoch == epoch => {
            let (_, a, b) = location_parts(&read.location);
            REPLY_BYTES + a.len() + b.len()
        }
        (Entry::Frame(frame), 22) if frame.epoch == epoch => frame.bytes.len(),
        _ => return Err(stale()),
    };
    if checked(n.checked_mul(2))? > max {
        return Err(resource());
    }
    Ok(n)
}
pub fn read_data(request: &[u8], max: usize) -> Result<Vec<u8>> {
    let n = data_len(request, max)?;
    let cmd = u32at(request, 8);
    let mut r = registry().lock().map_err(|_| resource())?;
    let i = index(&r, u64at(request, 16))?;
    match (&mut r.entries[i].1, cmd) {
        (Entry::Read(read), 21) => {
            if read.receipt_reads >= 2 {
                return Err(resource());
            }
            read.receipt_reads += 1;
            let b = read_receipt(read, u64at(request, 16));
            debug_assert_eq!(b.len(), n);
            Ok(b)
        }
        (Entry::Frame(frame), 22) => {
            if frame.reads >= 2 {
                return Err(resource());
            }
            frame.reads += 1;
            Ok(frame.bytes.clone())
        }
        _ => Err(stale()),
    }
}

/// Immutable admitted tile publication authority; no registry reentry in callback.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GeoTileProvenance {
    pub key: GeoTileKey,
    pub config_digest: [u8; 8],
    pub payload_digest: [u8; 8],
}
pub struct GeoTileFrameView<'a> {
    pub receipt: &'a [u8],
    pub scene: &'a [u8],
    pub camera: crate::geo_viewport::GeoViewportRebuildKey,
    pub keys: &'a [GeoTileKey],
    pub sources: &'a [GeoTileSource],
    pub provenance: &'a [GeoTileProvenance],
}
pub fn with_frame_data<T>(
    handle: u64,
    epoch: u64,
    callback: impl FnOnce(GeoTileFrameView<'_>) -> T,
) -> Result<T> {
    let r = registry().lock().map_err(|_| resource())?;
    let Entry::Frame(frame) = &r.entries[index(&r, handle)?].1 else {
        return Err(invalid());
    };
    if frame.epoch != epoch {
        return Err(stale());
    }
    let catalog = &frame.bytes[REPLY_BYTES..];
    let scene_len = usize::try_from(u64at(catalog, 72)).map_err(|_| resource())?;
    Ok(callback(GeoTileFrameView {
        receipt: &frame.bytes,
        scene: &catalog[128..128 + scene_len],
        camera: frame.camera,
        keys: &frame.keys,
        sources: &frame.sources,
        provenance: &frame.provenance,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(cmd: u32, handle: u64, epoch: u64, view: u64, payload: &[u8]) -> Vec<u8> {
        let mut b = vec![0; HEADER];
        b[..4].copy_from_slice(b"XYGT");
        p32(&mut b, 4, 1);
        p32(&mut b, 8, cmd);
        p64(&mut b, 16, handle);
        p64(&mut b, 24, epoch);
        p64(&mut b, 32, view);
        if matches!(cmd, 2 | 6 | 21 | 22) {
            p64(&mut b, 40, MAX_PROCESSOR_BYTES as u64);
        }
        p64(&mut b, 48, payload.len() as u64);
        b.extend(payload);
        b
    }
    fn begin(cache: u64, generation: u64, network: bool, vector: bool) -> [u8; REPLY_BYTES] {
        begin_revision(cache, generation, network, vector, 1)
    }
    fn begin_revision(
        cache: u64,
        generation: u64,
        network: bool,
        vector: bool,
        revision: u64,
    ) -> [u8; REPLY_BYTES] {
        let mut b = vec![0; 80];
        p32(&mut b, 0, 4326);
        p64(&mut b, 32, 800f64.to_bits());
        p64(&mut b, 40, 600f64.to_bits());
        p32(&mut b, 64, if vector { 2 } else { 1 });
        for kind in 0..if vector { 2 } else { 1 } {
            let locator = if network {
                "https://example.test/{z}/{x}/{y}"
            } else {
                "local/tiles"
            };
            let attr = if network { "Tile attribution" } else { "" };
            let mut h = vec![0; 112];
            for (at, n) in [
                (0, kind as u64 + 1),
                (8, generation),
                (16, kind as u64 + 7),
                (24, 1),
                (32, revision),
                (72, if kind == 0 { 262144 } else { 1024 }),
                (80, 1),
                (88, 1),
            ] {
                p64(&mut h, at, n);
            }
            p32(&mut h, 60, kind);
            p32(&mut h, 96, locator.len() as u32);
            p32(&mut h, 100, attr.len() as u32);
            p32(&mut h, 104, u32::from(network));
            b.extend(h);
            b.extend(locator.as_bytes());
            b.extend(attr.as_bytes());
        }
        execute(&request(2, cache, 0, 1, &b)).unwrap()
    }
    fn point() -> Vec<u8> {
        let mut b = vec![0; 96];
        b[..4].copy_from_slice(b"XYGD");
        for (at, n) in [(4, 1), (8, 1), (12, 4326), (16, 1)] {
            p32(&mut b, at, n);
        }
        p64(&mut b, 24, 1);
        p64(&mut b, 32, 1);
        b[80] = 1;
        p64(&mut b, 88, u64::MAX);
        b
    }
    fn fill(cache: u64, epoch: u64) {
        loop {
            let reply = execute(&request(3, cache, epoch, 0, &[])).unwrap();
            let read = u64at(&reply, 16);
            if read == 0 {
                break;
            }
            let data = if u32at(&reply, 148) == 0 {
                vec![255; 262144]
            } else {
                point()
            };
            execute(&request(4, read, epoch, 0, &data)).unwrap();
            execute(&request(5, read, epoch, 0, &[])).unwrap();
        }
    }
    fn prepare(cache: u64, epoch: u64, vector: bool) -> Result<[u8; REPLY_BYTES]> {
        prepare_diameter(cache, epoch, vector, 6.)
    }
    fn prepare_diameter(
        cache: u64,
        epoch: u64,
        vector: bool,
        diameter: f64,
    ) -> Result<[u8; REPLY_BYTES]> {
        let mut catalog = vec![0; 128];
        catalog[..4].copy_from_slice(b"XYLK");
        p32(&mut catalog, 4, 1);
        p32(&mut catalog, 16, 4326);
        p64(&mut catalog, 48, 800f64.to_bits());
        p64(&mut catalog, 56, 600f64.to_bits());
        let mut b = vec![0; 32];
        p64(&mut b, 0, 42);
        p32(&mut b, 8, u32::from(vector));
        p64(&mut b, 16, catalog.len() as u64);
        if vector {
            let mut style = vec![0; 64];
            p64(&mut style, 0, 8);
            p32(&mut style, 8, 1);
            style[16..20].copy_from_slice(&[255, 0, 0, 255]);
            p64(&mut style, 32, diameter.to_bits());
            p64(&mut style, 40, 1f64.to_bits());
            b.extend(style);
        }
        b.extend(catalog);
        execute(&request(6, cache, epoch, 0, &b))
    }
    #[test]
    fn mixed_receipt_survives_cache_disposal_and_transfer_allowance_is_exact() {
        let _source = crate::geo_source_session::test_processor_lock();
        let _tile = crate::geo_tile_cache::test_process_lock();
        let cache = u64at(&execute(&request(1, 0, 0, 0, &[])).unwrap(), 16);
        let epoch = u64at(&begin(cache, 1, false, true), 24);
        fill(cache, epoch);
        let frame = u64at(&prepare(cache, epoch, true).unwrap(), 16);
        let read = request(22, frame, epoch, 0, &[]);
        let length = data_len(&read, MAX_PROCESSOR_BYTES).unwrap();
        let bytes = read_data(&read, MAX_PROCESSOR_BYTES).unwrap();
        assert_eq!(length, bytes.len());
        assert_eq!(&bytes[..4], b"XYGU");
        assert_eq!(u64at(&bytes, 48), 2);
        let catalog = &bytes[REPLY_BYTES..REPLY_BYTES + u64at(&bytes, 40) as usize];
        assert_eq!(&catalog[..4], b"XYLM");
        let scene =
            crate::scene::SceneDocument::decode(&catalog[128..128 + u64at(catalog, 72) as usize])
                .unwrap();
        assert!(scene
            .interaction_records()
            .iter()
            .any(|record| record.stable_id == u64::MAX
                && record.kind == crate::scene::SceneRecordKind::Scatter));
        assert!(scene
            .interaction_records()
            .iter()
            .any(|record| record.kind == crate::scene::SceneRecordKind::Image));
        assert!(scene.to_browser_painter(MAX_PROCESSOR_BYTES).is_ok());
        let mut digest = Blake2s8::new();
        digest.update(b"xyg-tile-scene-receipt-v1");
        digest.update(&bytes[..136]);
        digest.update(&bytes[256..]);
        assert_eq!(&bytes[136..144], &digest.finish());
        assert!(matches!(
            execute(&request(7, frame, epoch + 1, 0, &[])),
            Err(TileProtocolError::Geo(GeoError::StaleHandle))
        ));
        execute(&request(7, frame, epoch, 0, &[])).unwrap();
        execute(&request(10, cache, 0, 0, &[])).unwrap();
        assert_eq!(read_data(&read, MAX_PROCESSOR_BYTES).unwrap(), bytes);
        assert!(matches!(
            read_data(&read, MAX_PROCESSOR_BYTES),
            Err(TileProtocolError::Geo(GeoError::ResourceLimit))
        ));
        execute(&request(10, frame, 0, 0, &[])).unwrap();
    }
    #[test]
    fn retired_read_ack_and_missing_attribution_fail_closed() {
        let _source = crate::geo_source_session::test_processor_lock();
        let _tile = crate::geo_tile_cache::test_process_lock();
        let cache = u64at(&execute(&request(1, 0, 0, 0, &[])).unwrap(), 16);
        let old = u64at(&begin(cache, 1, false, false), 24);
        let read = u64at(&execute(&request(3, cache, old, 0, &[])).unwrap(), 16);
        let new = u64at(&begin(cache, 2, true, false), 24);
        assert!(execute(&request(4, read, old, 0, &vec![255; 262144])).is_err());
        execute(&request(5, read, old, 0, &[])).unwrap();
        fill(cache, new);
        assert!(prepare(cache, new, false).is_err());
        assert!(execute(&request(3, cache, new, 0, &[])).is_err());
        execute(&request(10, cache, 0, 0, &[])).unwrap();
    }
    #[test]
    fn vector_style_revision_is_bound_only_after_successful_publication() {
        let _source = crate::geo_source_session::test_processor_lock();
        let _tile = crate::geo_tile_cache::test_process_lock();
        let cache = u64at(&execute(&request(1, 0, 0, 0, &[])).unwrap(), 16);
        let epoch = u64at(&begin(cache, 1, false, true), 24);
        fill(cache, epoch);
        assert!(prepare_diameter(cache, epoch, true, f64::MAX).is_err());
        let frame = u64at(&prepare(cache, epoch, true).unwrap(), 16);
        assert!(matches!(
            prepare_diameter(cache, epoch, true, 9.),
            Err(TileProtocolError::Geo(GeoError::StaleHandle))
        ));
        let original = read_data(&request(22, frame, epoch, 0, &[]), MAX_PROCESSOR_BYTES).unwrap();
        let next = u64at(&begin_revision(cache, 1, false, true, 2), 24);
        fill(cache, next);
        let newer = u64at(&prepare_diameter(cache, next, true, 9.).unwrap(), 16);
        assert_eq!(
            read_data(&request(22, frame, epoch, 0, &[]), MAX_PROCESSOR_BYTES).unwrap(),
            original
        );
        for handle in [newer, frame, cache] {
            execute(&request(10, handle, 0, 0, &[])).unwrap();
        }
    }
}
