//! Atomic immutable retained-source + tile composition. §27; see geo-mixed-frame.md.
use crate::geo_lod::{GeoPointOutput, GeoPointResult};
use crate::geo_scale_protocol::{GeoSceneDataBorrow, with_scene_data};
use crate::geo_source::{GeoSourceManifest, SourceError, TimePredicate};
use crate::geo_source_session::{GeoOperationSnapshot, GeoProcessorLease};
use crate::geo_tile_cache::{
    GeoDerivedLease, GeoTileCache, GeoTileLimits, GeoTileSource, TILE_CACHE_PROCESS_BYTES,
};
use crate::geo_tile_protocol::{GeoTileFrameView, GeoTileProvenance, with_frame_data};
use crate::scene::SceneDocument;
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicU64, Ordering},
};
static NEXT_OWNER: AtomicU64 = AtomicU64::new(1);
type Result<T> = std::result::Result<T, SourceError>;

/// Tile payloads do not have engine per-feature temporal columns.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoMixedTileTime {
    Timeless,
    ProducerWindow,
    EngineFiltered,
}
#[derive(Debug, Clone, PartialEq)]
pub struct GeoMixedRequest {
    pub source_handle: u64,
    pub source_sequence: u64,
    pub snapshot: GeoOperationSnapshot,
    pub tile_handle: u64,
    pub tile_epoch: u64,
    /// Expected trusted XYGU cache/view owner; epochs are scoped to this pair.
    pub tile_cache_handle: u64,
    pub tile_view_id: u64,
    /// Exact prepared tile key/configuration/content authority, not inferred revisions.
    pub tiles: Vec<GeoTileProvenance>,
    pub tile_time: GeoMixedTileTime,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoMixedTicket {
    owner: u64,
    sequence: u64,
}
/// Every object/view remains valid until the last Arc drops, even after source/cache disposal.
pub struct GeoMixedFrame {
    scene: Vec<u8>,
    tile_receipt: Vec<u8>,
    source: GeoSourceManifest,
    result: GeoPointResult,
    style: [u8; 48],
    authority: GeoMixedRequest,
    tile_sources: Vec<GeoTileSource>,
    retained_records: std::ops::Range<usize>,
    retained_styles: std::ops::Range<usize>,
    _source_charge: GeoProcessorLease,
    _charge: GeoDerivedLease,
}
impl GeoMixedFrame {
    pub fn scene(&self) -> &[u8] {
        &self.scene
    }
    pub fn tile_receipt(&self) -> &[u8] {
        &self.tile_receipt
    }
    pub fn source(&self) -> &GeoSourceManifest {
        &self.source
    }
    pub fn result(&self) -> &GeoPointResult {
        &self.result
    }
    pub fn style(&self) -> &[u8; 48] {
        &self.style
    }
    pub fn authority(&self) -> &GeoMixedRequest {
        &self.authority
    }
    pub fn retained_records(&self) -> std::ops::Range<usize> {
        self.retained_records.clone()
    }
    pub fn retained_styles(&self) -> std::ops::Range<usize> {
        self.retained_styles.clone()
    }
    pub fn tile_sources(&self) -> &[GeoTileSource] {
        &self.tile_sources
    }
}
pub struct GeoMixedCandidate {
    ticket: GeoMixedTicket,
    frame: Arc<GeoMixedFrame>,
}
impl GeoMixedCandidate {
    /// Borrow immutable candidate facts for admitted painter staging before commit.
    pub fn frame(&self) -> &GeoMixedFrame {
        &self.frame
    }
    pub(crate) fn frame_arc(&self) -> Arc<GeoMixedFrame> {
        Arc::clone(&self.frame)
    }
}

const MAX_TILE_SCOPES: usize = 8;
#[derive(Clone, Copy)]
struct TilePublication {
    cache: u64,
    view: u64,
    epoch: u64,
    data: u64,
}
struct PreparedStyle {
    layer: u64,
    revision: u64,
    bytes: [u8; 48],
}
pub struct GeoMixedCoordinator {
    cache: GeoTileCache,
    owner: u64,
    sequence: u64,
    pending: Option<GeoMixedRequest>,
    published: Option<Arc<GeoMixedFrame>>,
    last_admitted: Option<GeoMixedRequest>,
    tile_publications: [Option<TilePublication>; MAX_TILE_SCOPES],
    prepared_style: Mutex<Option<PreparedStyle>>,
    _request_charge: GeoDerivedLease,
}
impl GeoMixedCoordinator {
    pub fn new() -> Result<Self> {
        let owner = NEXT_OWNER
            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |n| n.checked_add(1))
            .map_err(|_| SourceError::ResourceLimit)?;
        let cache = GeoTileCache::new(GeoTileLimits::default(), 0)?;
        let request_charge = cache.reserve_derived(
            16_384
                + std::mem::size_of::<[Option<TilePublication>; MAX_TILE_SCOPES]>()
                + std::mem::size_of::<Mutex<Option<PreparedStyle>>>(),
        )?;
        Ok(Self {
            cache,
            owner,
            sequence: 0,
            pending: None,
            published: None,
            last_admitted: None,
            tile_publications: [None; MAX_TILE_SCOPES],
            prepared_style: Mutex::new(None),
            _request_charge: request_charge,
        })
    }
    pub fn begin(&mut self, request: GeoMixedRequest) -> Result<GeoMixedTicket> {
        if request.source_handle == 0
            || request.source_sequence == 0
            || request.tile_handle == 0
            || request.tile_epoch == 0
            || request.tile_cache_handle == 0
            || request.tiles.len() > 64
            || request.tiles.capacity() > 64
        {
            return Err(SourceError::InvalidFrame);
        }
        if request.tile_time == GeoMixedTileTime::EngineFiltered {
            return Err(SourceError::InvalidTime);
        }
        if let Some(previous) = &self.last_admitted {
            if !follows(request.snapshot, previous.snapshot)
                || (request.snapshot.layer_revision == previous.snapshot.layer_revision
                    && (request.source_sequence < previous.source_sequence
                        || (request.source_sequence == previous.source_sequence
                            && (request.source_handle != previous.source_handle
                                || request.snapshot != previous.snapshot))))
            {
                return Err(SourceError::StaleSource);
            }
            for old in &previous.tiles {
                if request.tiles.iter().any(|new| {
                    new.key == old.key
                        && (new.config_digest != old.config_digest
                            || new.payload_digest != old.payload_digest)
                }) {
                    return Err(SourceError::StaleSource);
                }
            }
        }
        let scope = self.tile_publications.iter().position(|p| {
            p.is_some_and(|p| {
                p.cache == request.tile_cache_handle && p.view == request.tile_view_id
            })
        });
        if scope.is_some_and(|slot| {
            let old = self.tile_publications[slot].unwrap();
            request.tile_epoch < old.epoch
                || (request.tile_epoch == old.epoch && request.tile_handle != old.data)
        }) {
            return Err(SourceError::StaleSource);
        }
        let slot = scope
            .or_else(|| self.tile_publications.iter().position(Option::is_none))
            .ok_or(SourceError::ResourceLimit)?;
        let sequence = self
            .sequence
            .checked_add(1)
            .ok_or(SourceError::ResourceLimit)?;
        self.sequence = sequence;
        self.tile_publications[slot] = Some(TilePublication {
            cache: request.tile_cache_handle,
            view: request.tile_view_id,
            epoch: request.tile_epoch,
            data: request.tile_handle,
        });
        self.last_admitted = Some(request.clone());
        self.pending = Some(request);
        Ok(GeoMixedTicket {
            owner: self.owner,
            sequence,
        })
    }
    fn request(&self, ticket: GeoMixedTicket) -> Result<&GeoMixedRequest> {
        if ticket.owner != self.owner || ticket.sequence != self.sequence {
            return Err(SourceError::StaleSource);
        }
        self.pending.as_ref().ok_or(SourceError::StaleSource)
    }
    /// Lock ordering is source registry → tile registry. No callback reentry/I/O.
    pub fn prepare(
        &self,
        ticket: GeoMixedTicket,
        budget: usize,
        cancel: &mut dyn FnMut() -> bool,
    ) -> Result<GeoMixedCandidate> {
        let request = self.request(ticket)?;
        if cancel() {
            return Err(SourceError::Cancelled);
        }
        with_scene_data(request.source_handle, request.source_sequence, |source| {
            with_frame_data(request.tile_handle, request.tile_epoch, |tiles| {
                self.prepare_borrowed(ticket, source, tiles, budget, cancel)
            })
            .map_err(|e| match e {
                crate::geo_tile_protocol::TileProtocolError::Geo(
                    crate::geo::GeoError::StaleHandle,
                ) => SourceError::StaleSource,
                crate::geo_tile_protocol::TileProtocolError::Geo(
                    crate::geo::GeoError::ResourceLimit,
                ) => SourceError::ResourceLimit,
                crate::geo_tile_protocol::TileProtocolError::Cancelled => SourceError::Cancelled,
                _ => SourceError::InvalidFrame,
            })?
        })?
    }
    pub(crate) fn prepare_borrowed(
        &self,
        ticket: GeoMixedTicket,
        source: GeoSceneDataBorrow<'_>,
        tiles: GeoTileFrameView<'_>,
        budget: usize,
        cancel: &mut dyn FnMut() -> bool,
    ) -> Result<GeoMixedCandidate> {
        let request = self.request(ticket)?;
        let stamp = tiles.receipt.get(..256).ok_or(SourceError::InvalidFrame)?;
        if &stamp[..4] != b"XYGU"
            || u32::from_le_bytes(stamp[4..8].try_into().unwrap()) != 1
            || u32::from_le_bytes(stamp[8..12].try_into().unwrap()) != 1
        {
            return Err(SourceError::InvalidFrame);
        }
        let number = |at| u64::from_le_bytes(stamp[at..at + 8].try_into().unwrap());
        if number(16) != request.tile_cache_handle
            || number(24) != request.tile_epoch
            || number(32) != request.tile_view_id
        {
            return Err(SourceError::StaleSource);
        }
        if source.snapshot != request.snapshot
            || tiles.camera != request.snapshot.camera
            || tiles.provenance != request.tiles
            || tiles.keys.len() != tiles.provenance.len()
        {
            return Err(SourceError::StaleSource);
        }
        {
            let style = self
                .prepared_style
                .lock()
                .map_err(|_| SourceError::InvalidFrame)?;
            if style.as_ref().is_some_and(|old| {
                old.layer == source.snapshot.layer_id
                    && old.revision == source.snapshot.style_revision
                    && old.bytes != *source.style
            }) {
                return Err(SourceError::StaleSource);
            }
        }
        if request.tile_time == GeoMixedTileTime::ProducerWindow
            && !matches!(request.snapshot.time, TimePredicate::Window { .. })
        {
            return Err(SourceError::InvalidTime);
        }
        for (key, provenance) in tiles.keys.iter().zip(tiles.provenance) {
            if *key != provenance.key {
                return Err(SourceError::StaleSource);
            }
            match (request.tile_time, request.snapshot.time, key.time) {
                (GeoMixedTileTime::Timeless, _, None) => (),
                (
                    GeoMixedTileTime::ProducerWindow,
                    TimePredicate::Window { start, end },
                    Some(time),
                ) if start == time.start && end == time.end => (),
                _ => return Err(SourceError::InvalidTime),
            }
        }
        if request.tile_time == GeoMixedTileTime::EngineFiltered {
            return Err(SourceError::InvalidTime);
        }
        basemap_layers(&tiles, request.snapshot.layer_id)?;
        let count = match &source.result.output {
            GeoPointOutput::Direct(p) => p.len(),
            GeoPointOutput::Reduced(p) => p.len(),
        };
        let peak = source
            .scene
            .len()
            .checked_add(tiles.receipt.len())
            .and_then(|n| n.checked_add(tiles.scene.len()))
            .and_then(|n| n.checked_mul(32))
            .and_then(|n| n.checked_add(count.checked_mul(128)?))
            .and_then(|n| n.checked_add(1024 * 1024))
            .ok_or(SourceError::ResourceLimit)?;
        if peak > budget || budget > TILE_CACHE_PROCESS_BYTES {
            return Err(SourceError::ResourceLimit);
        }
        let charge = self.cache.reserve_derived(peak)?;
        let source_charge = GeoProcessorLease::acquire(source.source.clone_reserved_bytes())?;
        if cancel() {
            return Err(SourceError::Cancelled);
        }
        let summary = |bytes| {
            crate::scene::validate_scene_batch(bytes).map_err(|_| SourceError::InvalidFrame)
        };
        let back = summary(tiles.scene)?;
        let front = summary(source.scene)?;
        let scene = SceneDocument::compose_geographic(tiles.scene, source.scene).map_err(|e| {
            if e == crate::scene::SceneError::Limit {
                SourceError::ResourceLimit
            } else {
                SourceError::InvalidFrame
            }
        })?;
        let result = GeoPointResult {
            key: source.result.key,
            output: match &source.result.output {
                GeoPointOutput::Direct(p) => GeoPointOutput::Direct(p.clone()),
                GeoPointOutput::Reduced(p) => GeoPointOutput::Reduced(p.clone()),
            },
            visible_vertices: source.result.visible_vertices,
            projected_vertices: source.result.projected_vertices,
            grid_capped: source.result.grid_capped,
            selection: source.result.selection.clone(),
        };
        let frame = GeoMixedFrame {
            scene,
            tile_receipt: tiles.receipt.to_vec(),
            source: source.source.clone_validated(),
            result,
            style: *source.style,
            authority: request.clone(),
            tile_sources: tiles.sources.to_vec(),
            retained_records: back.records..back.records + front.records,
            retained_styles: back.styles..back.styles + front.styles,
            _source_charge: source_charge,
            _charge: charge,
        };
        if cancel() {
            return Err(SourceError::Cancelled);
        }
        // Advance only after complete validated preparation and the final cancel
        // probe. Never call user cancellation callbacks under the style lock.
        {
            let mut style = self
                .prepared_style
                .lock()
                .map_err(|_| SourceError::InvalidFrame)?;
            if style.as_ref().is_some_and(|old| {
                old.layer == source.snapshot.layer_id
                    && old.revision == source.snapshot.style_revision
                    && old.bytes != *source.style
            }) {
                return Err(SourceError::StaleSource);
            }
            *style = Some(PreparedStyle {
                layer: source.snapshot.layer_id,
                revision: source.snapshot.style_revision,
                bytes: *source.style,
            });
        }
        Ok(GeoMixedCandidate {
            ticket,
            frame: Arc::new(frame),
        })
    }
    /// Caller stages this candidate's scene before commit; a newer begin/cancel fails closed.
    pub fn commit(&mut self, candidate: GeoMixedCandidate) -> Result<Arc<GeoMixedFrame>> {
        if self.request(candidate.ticket)? != &candidate.frame.authority {
            return Err(SourceError::StaleSource);
        }
        self.pending = None;
        self.published = Some(Arc::clone(&candidate.frame));
        Ok(candidate.frame)
    }
    pub fn cancel(&mut self, ticket: GeoMixedTicket) -> Result<()> {
        self.request(ticket)?;
        self.pending = None;
        Ok(())
    }
    pub fn published(&self) -> Option<&Arc<GeoMixedFrame>> {
        self.published.as_ref()
    }
}

fn follows(next: GeoOperationSnapshot, old: GeoOperationSnapshot) -> bool {
    if next.layer_id != old.layer_id
        || next.camera_revision < old.camera_revision
        || next.time_revision < old.time_revision
        || next.layer_revision < old.layer_revision
        || next.style_revision < old.style_revision
        || next.state_revision < old.state_revision
    {
        return false;
    }
    if next.camera_revision == old.camera_revision && next.camera != old.camera {
        return false;
    }
    if next.time_revision == old.time_revision && next.time != old.time {
        return false;
    }
    if next.layer_revision == old.layer_revision
        && (next.source_digest != old.source_digest || next.generation != old.generation)
    {
        return false;
    }
    true
}

// The tile protocol may include an ordinary authored foreground catalog. Those
// layers have no signed-time/state attachment; this coordinator refuses them.
pub(crate) fn basemap_layers(tiles: &GeoTileFrameView<'_>, analysis_layer: u64) -> Result<()> {
    let bytes = tiles.receipt.get(256..).ok_or(SourceError::InvalidFrame)?;
    let read = |at: usize| -> Result<usize> {
        usize::try_from(u64::from_le_bytes(
            bytes
                .get(at..at + 8)
                .ok_or(SourceError::InvalidFrame)?
                .try_into()
                .unwrap(),
        ))
        .map_err(|_| SourceError::ResourceLimit)
    };
    let align = |n: usize| -> Result<usize> {
        n.checked_add(7)
            .map(|n| n & !7)
            .ok_or(SourceError::ResourceLimit)
    };
    let layers = read(80)?;
    if layers > 64 {
        return Err(SourceError::InvalidFrame);
    }
    let mut at = align(
        128usize
            .checked_add(align(read(72)?)?)
            .and_then(|n| n.checked_add(read(88).ok()?.checked_mul(4)?))
            .ok_or(SourceError::ResourceLimit)?,
    )?;
    for _ in 0..layers {
        let h = bytes.get(at..at + 128).ok_or(SourceError::InvalidFrame)?;
        let n = |p| {
            usize::try_from(u64::from_le_bytes(h[p..p + 8].try_into().unwrap()))
                .map_err(|_| SourceError::ResourceLimit)
        };
        let layer = u64::from_le_bytes(h[..8].try_into().unwrap());
        if layer == analysis_layer
            || !tiles.keys.iter().any(|key| {
                key.layer_id == layer && key.kind == crate::geo_tile_cache::GeoTileKind::VectorXygd
            })
        {
            return Err(SourceError::InvalidFrame);
        }
        let features = n(24)?;
        let visible = n(32)?;
        at += 128;
        for size in [
            features.checked_mul(8),
            Some(features),
            Some(features),
            visible.checked_mul(4),
        ] {
            at = align(
                at.checked_add(size.ok_or(SourceError::ResourceLimit)?)
                    .ok_or(SourceError::ResourceLimit)?,
            )?;
        }
        if u32::from_le_bytes(h[12..16].try_into().unwrap()) & 2 != 0 {
            let cells = n(48)?;
            let members = n(56)?;
            for size in [
                cells.checked_mul(4),
                cells.checked_add(1).and_then(|n| n.checked_mul(4)),
                members.checked_mul(4),
            ] {
                at = align(
                    at.checked_add(size.ok_or(SourceError::ResourceLimit)?)
                        .ok_or(SourceError::ResourceLimit)?,
                )?;
            }
        }
        if at > bytes.len() {
            return Err(SourceError::InvalidFrame);
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
    use crate::geo_layers::{GeoCatalog, GeoLayer, GeoLayerKind, GeoStyle};
    use crate::geo_lod::{GeoDirectPoint, GeoLodIdentity, GeoLodKey, GeoReducedKind};
    use crate::geo_source::{FeatureRef, GeoChunk, GeoManifestBuilder, MAX_CHUNK_PEAK};
    use crate::geo_tile_cache::{GeoTileKey, GeoTileKind, GeoTileLocation, GeoTileTime};
    use crate::geo_viewport::GeoViewport;
    use crate::scene::{SceneImage, SceneRecordKind};
    struct Fixture {
        source: GeoSourceManifest,
        result: GeoPointResult,
        front: Vec<u8>,
        style: [u8; 48],
        back: Vec<u8>,
        receipt: Vec<u8>,
        sources: Vec<GeoTileSource>,
        provenance: Vec<GeoTileProvenance>,
        snapshot: GeoOperationSnapshot,
        tile_camera: crate::geo_viewport::GeoViewportRebuildKey,
    }
    fn style_bytes(style: GeoStyle) -> [u8; 48] {
        let mut bytes = [0; 48];
        bytes[..4].copy_from_slice(&style.fill);
        bytes[4..8].copy_from_slice(&style.stroke);
        bytes[8..16].copy_from_slice(&style.stroke_width.to_le_bytes());
        bytes[16..24].copy_from_slice(&style.diameter.to_le_bytes());
        bytes[24..32].copy_from_slice(&style.opacity.to_le_bytes());
        bytes[32] = style.symbol;
        bytes
    }
    impl Fixture {
        fn new() -> Self {
            let column = GeoColumn::from_descriptor(GeoDescriptor {
                geometry: GeoGeometry::Point,
                crs: GeoCrs::Epsg4326,
                xy: &[0., 0.],
                validity: &[1],
                feature_ids: Some(&[u64::MAX]),
                offsets0: &[],
                offsets1: &[],
                offsets2: &[],
                limits: GeoLimits::default(),
            })
            .unwrap();
            let chunk = GeoChunk::encode(&column, None).unwrap();
            let mut builder = GeoManifestBuilder::new();
            builder
                .push(&GeoChunk::parse(&chunk, MAX_CHUNK_PEAK).unwrap())
                .unwrap();
            let source = builder.finish(u64::MAX).unwrap();
            let camera =
                GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 0., 800., 600., 0., 0., true).unwrap();
            let key = camera.rebuild_key().unwrap();
            let snapshot = GeoOperationSnapshot {
                source_digest: source.digest(),
                generation: source.generation(),
                camera: key,
                time: TimePredicate::Window {
                    start: i64::MIN,
                    end: i64::MIN + 1,
                },
                camera_revision: 1,
                time_revision: 1,
                layer_id: u64::MAX,
                layer_revision: 1,
                style_revision: 1,
                state_revision: 1,
            };
            let result = GeoPointResult {
                key: GeoLodKey {
                    identity: GeoLodIdentity {
                        source_digest: source.digest(),
                        generation: source.generation(),
                        source_rows: 1,
                        crs: GeoCrs::Epsg4326,
                        geometry: GeoGeometry::Point,
                        layer_id: u64::MAX,
                        style_revision: 1,
                        state_revision: 1,
                    },
                    camera: key,
                    time: snapshot.time,
                    kind: GeoReducedKind::Cluster,
                    direct: true,
                    columns: 0,
                    rows: 0,
                },
                output: GeoPointOutput::Direct(vec![GeoDirectPoint {
                    identity: FeatureRef {
                        feature_id: u64::MAX,
                        source_row: 0,
                        chunk_index: 0,
                        row: 0,
                    },
                    vertex: 0,
                    x: 400.,
                    y: 300.,
                }]),
                visible_vertices: 1,
                projected_vertices: 1,
                grid_capped: false,
                selection: None,
            };
            let style = style_bytes(GeoStyle::default());
            let front = crate::geo_lod_scene::compile(&result, GeoStyle::default(), 128 << 20)
                .unwrap()
                .scene;
            let labels = [crate::geo_layers::GeoLabel {
                feature_index: 0,
                coordinate: [0., 0.],
                text: "Fixture Tiles",
                font_size: 12.,
                rgba: [0, 0, 0, 255],
                anchor: 0,
            }];
            let mut layer = GeoLayer::new(9, GeoLayerKind::Points, &column);
            layer.labels = &labels;
            let layers = [layer];
            let back = crate::geo_layers::compile_with_background(
                &GeoCatalog {
                    viewport: camera,
                    layers: &layers,
                    legend: None,
                    budget: 128 << 20,
                },
                Some(SceneImage {
                    stable_id: 10,
                    width: 1,
                    height: 1,
                    rgba: vec![0, 0, 255, 255],
                }),
            )
            .unwrap()
            .scene;
            let tile_key = GeoTileKey {
                source_id: 2,
                generation: 3,
                layer_id: 9,
                layer_revision: 4,
                style_revision: 5,
                time: Some(GeoTileTime {
                    start: i64::MIN,
                    end: i64::MIN + 1,
                }),
                kind: GeoTileKind::VectorXygd,
                zoom: 0,
                x: 0,
                y: 0,
            };
            let sources = vec![GeoTileSource {
                source_id: 2,
                generation: 3,
                layer_id: 9,
                layer_revision: 4,
                style_revision: 5,
                time: tile_key.time,
                kind: GeoTileKind::VectorXygd,
                location: GeoTileLocation::Network {
                    template: "https://fixture.invalid/{z}/{x}/{y}".into(),
                    attribution: "Fixture Tiles".into(),
                },
                min_zoom: 0,
                max_zoom: 0,
                payload_limits: GeoLimits::default(),
            }];
            let provenance = vec![GeoTileProvenance {
                key: tile_key,
                config_digest: [1; 8],
                payload_digest: [2; 8],
            }];
            // Minimal trusted catalog metadata for the prepared basemap layer.
            let mut receipt = vec![0; 256 + 128 + 128];
            receipt[..4].copy_from_slice(b"XYGU");
            receipt[4..8].copy_from_slice(&1u32.to_le_bytes());
            receipt[8..12].copy_from_slice(&1u32.to_le_bytes());
            receipt[16..24].copy_from_slice(&17u64.to_le_bytes());
            receipt[24..32].copy_from_slice(&1u64.to_le_bytes());
            receipt[32..40].copy_from_slice(&7u64.to_le_bytes());
            receipt[40..48].copy_from_slice(&256u64.to_le_bytes());
            receipt[256..260].copy_from_slice(b"XYLM");
            receipt[260..264].copy_from_slice(&1u32.to_le_bytes());
            receipt[256 + 80..256 + 88].copy_from_slice(&1u64.to_le_bytes());
            receipt[256 + 128..256 + 136].copy_from_slice(&9u64.to_le_bytes());
            Self {
                source,
                result,
                front,
                style,
                back,
                receipt,
                sources,
                provenance,
                snapshot,
                tile_camera: key,
            }
        }
        fn request(&self) -> GeoMixedRequest {
            GeoMixedRequest {
                source_handle: 1,
                source_sequence: self.snapshot.camera_revision
                    + self.snapshot.time_revision
                    + self.snapshot.layer_revision
                    + self.snapshot.style_revision
                    + self.snapshot.state_revision,
                snapshot: self.snapshot,
                tile_handle: 2,
                tile_epoch: u64::from_le_bytes(self.receipt[24..32].try_into().unwrap()),
                tile_cache_handle: u64::from_le_bytes(self.receipt[16..24].try_into().unwrap()),
                tile_view_id: u64::from_le_bytes(self.receipt[32..40].try_into().unwrap()),
                tiles: self.provenance.clone(),
                tile_time: GeoMixedTileTime::ProducerWindow,
            }
        }
        fn prepare(
            &self,
            c: &GeoMixedCoordinator,
            t: GeoMixedTicket,
            cancel: &mut dyn FnMut() -> bool,
        ) -> Result<GeoMixedCandidate> {
            let keys: Vec<_> = self.provenance.iter().map(|p| p.key).collect();
            c.prepare_borrowed(
                t,
                GeoSceneDataBorrow {
                    scene: &self.front,
                    source: &self.source,
                    result: &self.result,
                    style: &self.style,
                    snapshot: self.snapshot,
                },
                GeoTileFrameView {
                    receipt: &self.receipt,
                    scene: &self.back,
                    camera: self.tile_camera,
                    keys: &keys,
                    sources: &self.sources,
                    provenance: &self.provenance,
                },
                128 << 20,
                cancel,
            )
        }
    }
    #[test]
    fn admitted_source_order_survives_cancel_and_rejects_older_lod_frames() {
        let _processor = crate::geo_source_session::test_processor_lock();
        let _lock = crate::geo_tile_cache::test_process_lock();
        let f = Fixture::new();
        let mut c = GeoMixedCoordinator::new().unwrap();
        let t = c.begin(f.request()).unwrap();
        let old = c.commit(f.prepare(&c, t, &mut || false).unwrap()).unwrap();
        let mut newer = f.request();
        newer.source_sequence += 1;
        newer.source_handle += 1;
        newer.snapshot.state_revision += 1;
        let ticket = c.begin(newer.clone()).unwrap();
        c.cancel(ticket).unwrap();
        assert!(matches!(
            c.begin(f.request()),
            Err(SourceError::StaleSource)
        ));
        let mut changed_same_sequence = newer.clone();
        changed_same_sequence.source_handle += 1;
        assert!(matches!(
            c.begin(changed_same_sequence),
            Err(SourceError::StaleSource)
        ));
        assert!(c.begin(newer.clone()).is_ok());
        newer.snapshot.layer_revision += 1;
        newer.snapshot.generation = 1;
        newer.source_sequence = 1;
        assert!(c.begin(newer).is_ok());
        assert!(Arc::ptr_eq(c.published().unwrap(), &old));
        assert_eq!(old.result().visible_vertices, 1);
    }
    #[test]
    fn trusted_prepared_style_survives_cancel_before_first_commit_and_newer_cancel() {
        let _processor = crate::geo_source_session::test_processor_lock();
        let _lock = crate::geo_tile_cache::test_process_lock();
        let mut f = Fixture::new();
        let mut c = GeoMixedCoordinator::new().unwrap();
        let t = c.begin(f.request()).unwrap();
        let candidate = f.prepare(&c, t, &mut || false).unwrap();
        c.cancel(t).unwrap();
        drop(candidate);
        assert!(c.published().is_none());
        let blue = GeoStyle {
            fill: [0, 0, 255, 255],
            ..GeoStyle::default()
        };
        f.style = style_bytes(blue);
        f.front = crate::geo_lod_scene::compile(&f.result, blue, 128 << 20)
            .unwrap()
            .scene;
        let mut independent = f.request();
        independent.source_handle = 3;
        independent.source_sequence += 1;
        let t = c.begin(independent.clone()).unwrap();
        assert!(matches!(
            f.prepare(&c, t, &mut || false),
            Err(SourceError::StaleSource)
        ));
        f.snapshot.style_revision += 1;
        f.result.key.identity.style_revision = f.snapshot.style_revision;
        independent.snapshot = f.snapshot;
        independent.source_sequence += 1;
        independent.source_handle = 4;
        let t = c.begin(independent.clone()).unwrap();
        let candidate = f.prepare(&c, t, &mut || false).unwrap();
        c.cancel(t).unwrap();
        drop(candidate);
        // Another valid SourceData owner cannot restore an earlier paint under
        // the now successfully prepared revision2, even though none committed.
        f.style = style_bytes(GeoStyle::default());
        f.front = crate::geo_lod_scene::compile(&f.result, GeoStyle::default(), 128 << 20)
            .unwrap()
            .scene;
        independent.source_sequence += 1;
        independent.source_handle = 5;
        let t = c.begin(independent).unwrap();
        assert!(matches!(
            f.prepare(&c, t, &mut || false),
            Err(SourceError::StaleSource)
        ));
        assert!(c.published().is_none());
    }
    #[test]
    fn failed_preparation_does_not_advance_trusted_style_baseline() {
        let _processor = crate::geo_source_session::test_processor_lock();
        let _lock = crate::geo_tile_cache::test_process_lock();
        let mut f = Fixture::new();
        let mut c = GeoMixedCoordinator::new().unwrap();
        let t = c.begin(f.request()).unwrap();
        let old = c.commit(f.prepare(&c, t, &mut || false).unwrap()).unwrap();
        f.snapshot.style_revision += 1;
        f.result.key.identity.style_revision = f.snapshot.style_revision;
        f.style[0] ^= 255;
        let saved = std::mem::replace(&mut f.front, b"invalid Scene".to_vec());
        let mut independent = f.request();
        independent.source_handle = 3;
        independent.source_sequence += 1;
        let t = c.begin(independent.clone()).unwrap();
        assert!(matches!(
            f.prepare(&c, t, &mut || false),
            Err(SourceError::InvalidFrame)
        ));
        f.front = saved;
        f.style = style_bytes(GeoStyle::default());
        independent.source_sequence += 1;
        independent.source_handle = 4;
        let t = c.begin(independent).unwrap();
        assert!(f.prepare(&c, t, &mut || false).is_ok());
        assert!(Arc::ptr_eq(c.published().unwrap(), &old));
    }
    #[test]
    fn configured_but_unselected_vector_cannot_authorize_catalog_layer() {
        let _processor = crate::geo_source_session::test_processor_lock();
        let _lock = crate::geo_tile_cache::test_process_lock();
        let mut f = Fixture::new();
        let mut c = GeoMixedCoordinator::new().unwrap();
        let t = c.begin(f.request()).unwrap();
        let old = c.commit(f.prepare(&c, t, &mut || false).unwrap()).unwrap();
        // The configured vector layer and its actual Scene/metadata remain, but
        // the current prepared selection contains no vector tile authority.
        assert_eq!(f.sources[0].kind, GeoTileKind::VectorXygd);
        f.provenance.clear();
        let t = c.begin(f.request()).unwrap();
        assert!(matches!(
            f.prepare(&c, t, &mut || false),
            Err(SourceError::InvalidFrame)
        ));
        assert!(Arc::ptr_eq(c.published().unwrap(), &old));
    }
    #[test]
    fn tile_epoch_scopes_reject_regression_swap_and_switch_back_after_cancel() {
        let _processor = crate::geo_source_session::test_processor_lock();
        let _lock = crate::geo_tile_cache::test_process_lock();
        let mut f = Fixture::new();
        let mut c = GeoMixedCoordinator::new().unwrap();
        let t = c.begin(f.request()).unwrap();
        let old = c.commit(f.prepare(&c, t, &mut || false).unwrap()).unwrap();
        f.receipt[24..32].copy_from_slice(&2u64.to_le_bytes());
        let mut newer = f.request();
        newer.tile_handle = 3;
        let t = c.begin(newer.clone()).unwrap();
        let candidate = f.prepare(&c, t, &mut || false).unwrap();
        c.cancel(t).unwrap();
        assert!(matches!(c.commit(candidate), Err(SourceError::StaleSource)));
        let mut regressed = newer.clone();
        regressed.tile_epoch = 1;
        assert!(matches!(
            c.begin(regressed.clone()),
            Err(SourceError::StaleSource)
        ));
        let mut swapped = newer.clone();
        swapped.tile_handle = 4;
        assert!(matches!(c.begin(swapped), Err(SourceError::StaleSource)));
        // A new cache owner legitimately starts at epoch1. Returning to the old
        // owner must still enforce its retained epoch2 baseline.
        let mut other = newer.clone();
        other.tile_cache_handle = 18;
        other.tile_epoch = 1;
        other.tile_handle = 4;
        let other_ticket = c.begin(other).unwrap();
        c.cancel(other_ticket).unwrap();
        assert!(matches!(c.begin(regressed), Err(SourceError::StaleSource)));
        let t = c.begin(newer).unwrap();
        assert!(f.prepare(&c, t, &mut || false).is_ok());
        // A distinct view on the original cache owns its own epoch baseline.
        f.receipt[24..32].copy_from_slice(&1u64.to_le_bytes());
        f.receipt[32..40].copy_from_slice(&8u64.to_le_bytes());
        let t = c.begin(f.request()).unwrap();
        assert!(f.prepare(&c, t, &mut || false).is_ok());
        assert!(Arc::ptr_eq(c.published().unwrap(), &old));
    }
    #[test]
    fn trusted_receipt_stamp_must_match_expected_scope_and_scope_history_is_bounded() {
        let _processor = crate::geo_source_session::test_processor_lock();
        let _lock = crate::geo_tile_cache::test_process_lock();
        let f = Fixture::new();
        let mut c = GeoMixedCoordinator::new().unwrap();
        let t = c.begin(f.request()).unwrap();
        let old = c.commit(f.prepare(&c, t, &mut || false).unwrap()).unwrap();
        for field in 0..3 {
            let mut request = f.request();
            match field {
                0 => request.tile_cache_handle += 1,
                1 => request.tile_view_id += 1,
                _ => request.tile_epoch += 1,
            }
            let t = c.begin(request).unwrap();
            assert!(matches!(
                f.prepare(&c, t, &mut || false),
                Err(SourceError::StaleSource)
            ));
            c.cancel(t).unwrap();
        }
        // Three scopes already admitted; failed preparation/cancel does not
        // erase admission history. Five more scopes fit, the ninth fails.
        for cache in 100..105 {
            let mut request = f.request();
            request.tile_cache_handle = cache;
            let t = c.begin(request).unwrap();
            c.cancel(t).unwrap();
        }
        let mut ninth = f.request();
        ninth.tile_cache_handle = 105;
        assert!(matches!(c.begin(ninth), Err(SourceError::ResourceLimit)));
        assert!(Arc::ptr_eq(c.published().unwrap(), &old));
    }
    #[test]
    fn real_raster_vector_and_retained_records_preserve_full_identity_and_bytes() {
        let _processor = crate::geo_source_session::test_processor_lock();
        let _lock = crate::geo_tile_cache::test_process_lock();
        let f = Fixture::new();
        let mut c = GeoMixedCoordinator::new().unwrap();
        let t = c.begin(f.request()).unwrap();
        let candidate = f.prepare(&c, t, &mut || false).unwrap();
        let frame = c.commit(candidate).unwrap();
        let document = SceneDocument::decode(frame.scene()).unwrap();
        let records = document.interaction_records();
        assert_eq!(records.len(), 4);
        assert_eq!(frame.retained_records(), 3..4);
        assert_eq!(frame.retained_styles().len(), 1);
        assert_eq!(records[0].kind, SceneRecordKind::Image);
        assert_eq!(records.last().unwrap().stable_id, u64::MAX);
        assert_eq!(records.last().unwrap().coordinates, [400., 300., 0., 0.]);
        assert_eq!(
            document.interaction_image(10).unwrap().rgba,
            [0, 0, 255, 255]
        );
        assert!(document.has_visible_attribution("Fixture Tiles"));
        assert_eq!(frame.tile_receipt(), f.receipt);
        assert_eq!(frame.authority().snapshot.time, f.snapshot.time);
        assert_eq!(frame.source().digest(), f.source.digest());
        assert_eq!(frame.authority().tiles, f.provenance);
        drop(c);
        assert_eq!(
            SceneDocument::decode(frame.scene()).unwrap().record_count(),
            4
        );
        assert_eq!(frame.result().visible_vertices, 1);
    }
    #[test]
    fn time_camera_full_revisions_payload_and_unfiltered_catalog_fail_closed() {
        let _processor = crate::geo_source_session::test_processor_lock();
        let _lock = crate::geo_tile_cache::test_process_lock();
        let mut f = Fixture::new();
        let mut c = GeoMixedCoordinator::new().unwrap();
        let t = c.begin(f.request()).unwrap();
        let old = c.commit(f.prepare(&c, t, &mut || false).unwrap()).unwrap();
        let mut request = f.request();
        request.snapshot.state_revision = 0;
        assert!(matches!(c.begin(request), Err(SourceError::StaleSource)));
        let mut request = f.request();
        request.snapshot.camera.zoom_bits = 1f64.to_bits();
        assert!(matches!(c.begin(request), Err(SourceError::StaleSource)));
        let mut request = f.request();
        request.tiles[0].payload_digest = [3; 8];
        assert!(matches!(c.begin(request), Err(SourceError::StaleSource)));
        let mut request = f.request();
        request.tile_time = GeoMixedTileTime::EngineFiltered;
        assert!(matches!(c.begin(request), Err(SourceError::InvalidTime)));
        let t = c.begin(f.request()).unwrap();
        f.provenance[0].key.time = Some(GeoTileTime { start: 0, end: 1 });
        assert!(matches!(
            f.prepare(&c, t, &mut || false),
            Err(SourceError::StaleSource)
        ));
        f.provenance[0].key.time = Some(GeoTileTime {
            start: i64::MIN,
            end: i64::MIN + 1,
        });
        f.snapshot.camera.zoom_bits = 1f64.to_bits();
        assert!(matches!(
            f.prepare(&c, t, &mut || false),
            Err(SourceError::StaleSource)
        ));
        f.snapshot.camera.zoom_bits = 0f64.to_bits();
        f.snapshot.time = TimePredicate::Window { start: 0, end: 1 };
        f.snapshot.time_revision = 2;
        let t = c.begin(f.request()).unwrap();
        assert!(matches!(
            f.prepare(&c, t, &mut || false),
            Err(SourceError::InvalidTime)
        ));
        f.snapshot.time = TimePredicate::Window {
            start: i64::MIN,
            end: i64::MIN + 1,
        };
        f.snapshot.time_revision = 3;
        f.snapshot.camera.zoom_bits = 1f64.to_bits();
        f.snapshot.camera_revision = 2;
        let t = c.begin(f.request()).unwrap();
        assert!(matches!(
            f.prepare(&c, t, &mut || false),
            Err(SourceError::StaleSource)
        ));
        f.snapshot.camera.zoom_bits = 0f64.to_bits();
        f.snapshot.camera_revision = 3;
        let t = c.begin(f.request()).unwrap();
        f.receipt[384..392].copy_from_slice(&123u64.to_le_bytes());
        assert!(matches!(
            f.prepare(&c, t, &mut || false),
            Err(SourceError::InvalidFrame)
        ));
        assert!(Arc::ptr_eq(c.published().unwrap(), &old));
    }
    #[test]
    fn private_nonce_cancel_cross_owner_and_failure_keep_old_published_frame() {
        let _processor = crate::geo_source_session::test_processor_lock();
        let _lock = crate::geo_tile_cache::test_process_lock();
        let f = Fixture::new();
        let mut c = GeoMixedCoordinator::new().unwrap();
        let t = c.begin(f.request()).unwrap();
        let old = c.commit(f.prepare(&c, t, &mut || false).unwrap()).unwrap();
        let t = c.begin(f.request()).unwrap();
        let stale = f.prepare(&c, t, &mut || false).unwrap();
        let latest = c.begin(f.request()).unwrap();
        assert!(matches!(c.commit(stale), Err(SourceError::StaleSource)));
        assert!(matches!(c.cancel(t), Err(SourceError::StaleSource)));
        let candidate = f.prepare(&c, latest, &mut || false).unwrap();
        c.cancel(latest).unwrap();
        assert!(matches!(c.commit(candidate), Err(SourceError::StaleSource)));
        let t = c.begin(f.request()).unwrap();
        let before = c.cache.stats().process_charged_bytes;
        let source_before = GeoProcessorLease::live_bytes();
        let mut probes = 0;
        assert!(matches!(
            f.prepare(&c, t, &mut || {
                probes += 1;
                probes == 2
            }),
            Err(SourceError::Cancelled)
        ));
        assert!(Arc::ptr_eq(c.published().unwrap(), &old));
        assert_eq!(c.cache.stats().process_charged_bytes, before);
        assert_eq!(GeoProcessorLease::live_bytes(), source_before);
        let mut other = GeoMixedCoordinator::new().unwrap();
        assert!(matches!(
            other.commit(f.prepare(&c, t, &mut || false).unwrap()),
            Err(SourceError::StaleSource)
        ));
        assert!(Arc::ptr_eq(c.published().unwrap(), &old));
    }
    #[test]
    fn tiny_budget_rejected_before_scene_decoding_and_old_frame_survives() {
        let _processor = crate::geo_source_session::test_processor_lock();
        let _lock = crate::geo_tile_cache::test_process_lock();
        let f = Fixture::new();
        let mut c = GeoMixedCoordinator::new().unwrap();
        let t = c.begin(f.request()).unwrap();
        let old = c.commit(f.prepare(&c, t, &mut || false).unwrap()).unwrap();
        let t = c.begin(f.request()).unwrap();
        let keys: Vec<_> = f.provenance.iter().map(|p| p.key).collect();
        let result = c.prepare_borrowed(
            t,
            GeoSceneDataBorrow {
                scene: b"invalid",
                source: &f.source,
                result: &f.result,
                style: &f.style,
                snapshot: f.snapshot,
            },
            GeoTileFrameView {
                receipt: &f.receipt,
                scene: b"invalid",
                camera: f.snapshot.camera,
                keys: &keys,
                sources: &f.sources,
                provenance: &f.provenance,
            },
            1,
            &mut || false,
        );
        assert!(matches!(result, Err(SourceError::ResourceLimit)));
        assert!(Arc::ptr_eq(c.published().unwrap(), &old));
    }
    #[test]
    fn scene_rejects_foreground_decorations_and_conflicting_image_ids() {
        let _processor = crate::geo_source_session::test_processor_lock();
        let _lock = crate::geo_tile_cache::test_process_lock();
        let mut f = Fixture::new();
        assert!(SceneDocument::compose_geographic(&f.back, &f.back).is_err());
        f.result.key.identity.layer_id = 10;
        f.result.key.kind = GeoReducedKind::Density;
        f.result.key.direct = false;
        f.result.key.columns = 1;
        f.result.key.rows = 1;
        f.result.output = GeoPointOutput::Reduced(vec![crate::geo_lod::GeoPointCell {
            count: 1,
            x: 400.,
            y: 300.,
        }]);
        let foreground = crate::geo_lod_scene::compile(&f.result, GeoStyle::default(), 128 << 20)
            .unwrap()
            .scene;
        assert!(SceneDocument::compose_geographic(&f.back, &foreground).is_err());
    }
}
