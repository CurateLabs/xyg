//! Frozen accountable geographic export (§27/§29); see geo-frozen-export.md.
//! Immutable XYGX carries Scene32 and exact source/camera/time/revision facts.
use crate::geo::{GeoCrs, GeoGeometry};
use crate::geo_lod::{
    CLUSTER_CELL_LIMIT, DENSITY_CELL_LIMIT, GeoLodIdentity, GeoLodKey, GeoPointCell,
    GeoPointOutput, GeoPointResult, GeoReducedKind,
};
use crate::geo_source::{MAX_CHUNK_ROWS, MAX_SOURCE_ROWS, QueryCursor, TimePredicate};
use crate::geo_source_session::GeoOperationSnapshot;
use crate::geo_tile_cache::{GeoDerivedLease, GeoTileCache};
use crate::geo_viewport::{GeoViewport, GeoViewportRebuildKey};
use crate::scene::{SCENE_VERSION, SceneDocument};
use crate::transition::Blake2s8;
use std::ops::Range;

pub const MAX_FROZEN_BYTES: usize = 32 * 1024 * 1024;
pub const MAX_FROZEN_SCENE_BYTES: usize = 16 * 1024 * 1024;
pub const MAX_FROZEN_PEAK: usize = 128 * 1024 * 1024;
pub const MAX_FROZEN_LAYERS: usize = 64;
pub const MAX_FROZEN_DIRECT: usize = 65_536;
pub const MAX_FROZEN_MEMBERSHIP: usize = 4096;
pub const MAX_FROZEN_ATTRIBUTIONS: usize = 64;
pub const MAX_FROZEN_TEXT_BYTES: usize = 4096;
pub const MAX_FROZEN_ARTIFACT_BYTES: usize = 64 * 1024 * 1024;
const HEADER: usize = 192;
const LAYER: usize = 80;
const DIRECT: usize = 48;
const GRID: usize = 232;
pub const MAX_FROZEN_GRID_CELLS: usize = DENSITY_CELL_LIMIT;
const MEMBERSHIP: usize = 96;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoSnapshotError {
    Invalid,
    Scene,
    Limit,
    Stale,
    Attribution,
    Export,
    Unsupported,
}
type Result<T> = std::result::Result<T, GeoSnapshotError>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GeoFrozenLayer {
    pub layer_id: u64,
    pub source_id: u64,
    pub source_generation: u64,
    pub layer_revision: u64,
    pub style_revision: u64,
    pub state_revision: u64,
    pub source_digest: [u8; 8],
    pub source_rows: u64,
    pub geometry: GeoGeometry,
    pub crs: GeoCrs,
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GeoFrozenIdentity {
    pub camera: GeoViewportRebuildKey,
    pub time: TimePredicate,
    pub camera_revision: u64,
    pub time_revision: u64,
    /// Paint order is semantic and is preserved, never sorted by ID.
    pub layers: Vec<GeoFrozenLayer>,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoFrozenDirect {
    pub layer_id: u64,
    pub source_row: u64,
    pub feature_id: u64,
    pub chunk_index: u32,
    pub row: u32,
    pub vertex: u32,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoFrozenMembership {
    pub layer_id: u64,
    pub cell: u32,
    pub columns: u32,
    pub rows: u32,
    pub kind: GeoReducedKind,
    pub member_count: u64,
    /// Paged source reference, never a fabricated representative feature ID.
    pub cursor: Option<QueryCursor>,
}
/// Full viewport grid counts are visible vertices, never unique source rows.
#[derive(Debug, PartialEq)]
pub struct GeoFrozenGrid {
    pub key: GeoLodKey,
    pub visible_vertices: u64,
    pub projected_vertices: u64,
    pub vertex_counts: Vec<u64>,
    pub style: [u8; 48],
}
#[derive(Clone, Copy)]
pub enum GeoFrozenGridCounts<'a> {
    Counts(&'a [u64]),
    Cells(&'a [GeoPointCell]),
}
impl GeoFrozenGridCounts<'_> {
    fn len(self) -> usize {
        match self {
            Self::Counts(v) => v.len(),
            Self::Cells(v) => v.len(),
        }
    }
    fn count(self, i: usize) -> u64 {
        match self {
            Self::Counts(v) => v[i],
            Self::Cells(v) => v[i].count,
        }
    }
}
pub struct GeoFrozenGridInput<'a> {
    pub key: GeoLodKey,
    pub visible_vertices: u64,
    pub projected_vertices: u64,
    pub counts: GeoFrozenGridCounts<'a>,
    pub style: [u8; 48],
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoFrozenFormat {
    Svg = 0,
    Png = 1,
    Pdf = 2,
    Jpeg = 3,
    Webp = 4,
    Html = 5,
}
impl GeoFrozenFormat {
    pub fn from_code(code: u32) -> Result<Self> {
        match code {
            0 => Ok(Self::Svg),
            1 => Ok(Self::Png),
            2 => Ok(Self::Pdf),
            3 => Ok(Self::Jpeg),
            4 => Ok(Self::Webp),
            5 => Ok(Self::Html),
            _ => Err(GeoSnapshotError::Invalid),
        }
    }
}
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GeoFrozenArtifactBinding {
    pub format: GeoFrozenFormat,
    pub scale: f64,
    pub quality: i32,
    pub bytes: u64,
    /// BLAKE2s8 content linkage, not authentication or authorization.
    pub digest: [u8; 8],
}

/// All storage is private and drops before its process-accounting lease.
pub struct GeoFrozenSnapshot {
    encoded: Vec<u8>,
    scene: Range<usize>,
    tile: Option<Range<usize>>,
    identity: GeoFrozenIdentity,
    direct: Vec<GeoFrozenDirect>,
    membership: Vec<GeoFrozenMembership>,
    grids: Vec<GeoFrozenGrid>,
    attributions: Vec<String>,
    binding: Option<GeoFrozenArtifactBinding>,
    _charge: GeoDerivedLease,
}
pub struct GeoFrozenArtifact {
    bytes: Vec<u8>,
    snapshot: Vec<u8>,
    binding: GeoFrozenArtifactBinding,
    _charge: GeoDerivedLease,
}
impl GeoFrozenArtifact {
    pub fn bytes(&self) -> &[u8] {
        &self.bytes
    }
    pub fn snapshot(&self) -> &[u8] {
        &self.snapshot
    }
    pub fn binding(&self) -> GeoFrozenArtifactBinding {
        self.binding
    }
}

fn hash(domain: &[u8], bytes: &[u8]) -> [u8; 8] {
    let mut h = Blake2s8::new();
    h.update(domain);
    h.update(bytes);
    h.finish()
}
fn u32at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}
fn u64at(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}
fn put32(b: &mut [u8], at: usize, v: u32) {
    b[at..at + 4].copy_from_slice(&v.to_le_bytes());
}
fn put64(b: &mut [u8], at: usize, v: u64) {
    b[at..at + 8].copy_from_slice(&v.to_le_bytes());
}
fn camera(key: GeoViewportRebuildKey) -> GeoViewport {
    GeoViewport {
        crs: key.crs,
        center_x: f64::from_bits(key.center_x_bits),
        center_y: f64::from_bits(key.center_y_bits),
        zoom: f64::from_bits(key.zoom_bits),
        width: f64::from_bits(key.width_bits),
        height: f64::from_bits(key.height_bits),
        bearing_deg: f64::from_bits(key.bearing_deg_bits),
        pitch_deg: f64::from_bits(key.pitch_deg_bits),
        world_wrap: key.world_wrap,
    }
}
#[cfg(feature = "raster")]
fn escaped(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}
fn identity_validate(identity: &GeoFrozenIdentity) -> Result<()> {
    if identity.layers.len() > MAX_FROZEN_LAYERS {
        return Err(GeoSnapshotError::Limit);
    }
    if camera(identity.camera)
        .rebuild_key()
        .map_err(|_| GeoSnapshotError::Invalid)?
        != identity.camera
        || identity.time.validate().is_err()
    {
        return Err(GeoSnapshotError::Invalid);
    }
    for (i, layer) in identity.layers.iter().enumerate() {
        if layer.source_generation == 0
            || layer.source_rows > MAX_SOURCE_ROWS
            || identity.layers[..i]
                .iter()
                .any(|old| old.layer_id == layer.layer_id)
        {
            return Err(GeoSnapshotError::Invalid);
        }
    }
    Ok(())
}

fn invalid_attribution_text(text: &str) -> bool {
    text.trim().is_empty()
        || text.len() > MAX_FROZEN_TEXT_BYTES
        || text
            .chars()
            .any(|c| c.is_control() || matches!(c, '\u{fffe}' | '\u{ffff}'))
}
fn layer_bytes(layer: &GeoFrozenLayer) -> [u8; LAYER] {
    let mut b = [0; LAYER];
    for (i, v) in [
        layer.layer_id,
        layer.source_id,
        layer.source_generation,
        layer.layer_revision,
        layer.style_revision,
        layer.state_revision,
    ]
    .into_iter()
    .enumerate()
    {
        put64(&mut b, i * 8, v);
    }
    b[48..56].copy_from_slice(&layer.source_digest);
    put64(&mut b, 56, layer.source_rows);
    put32(&mut b, 64, layer.geometry as u32);
    put32(&mut b, 68, layer.crs as u32);
    b
}
fn membership_bytes(
    identity: &GeoFrozenIdentity,
    member: GeoFrozenMembership,
) -> Result<[u8; MEMBERSHIP]> {
    let layer = identity
        .layers
        .iter()
        .find(|l| l.layer_id == member.layer_id)
        .ok_or(GeoSnapshotError::Invalid)?;
    let cells = (member.columns as usize)
        .checked_mul(member.rows as usize)
        .ok_or(GeoSnapshotError::Limit)?;
    let cap = if member.kind == GeoReducedKind::Cluster {
        CLUSTER_CELL_LIMIT
    } else {
        DENSITY_CELL_LIMIT
    };
    if cells == 0
        || cells > cap
        || member.cell as usize >= cells
        || member.member_count == 0
        || member.member_count > layer.source_rows
    {
        return Err(GeoSnapshotError::Invalid);
    }
    let mut b = [0; MEMBERSHIP];
    put64(&mut b, 0, member.layer_id);
    put32(&mut b, 16, member.cell);
    put32(&mut b, 20, member.columns);
    put32(&mut b, 24, member.rows);
    put32(
        &mut b,
        28,
        if member.kind == GeoReducedKind::Cluster {
            0
        } else {
            1
        },
    );
    put64(&mut b, 32, member.member_count);
    if let Some(c) = member.cursor {
        if c.generation != layer.source_generation
            || c.source_digest != layer.source_digest
            || c.row as usize >= MAX_CHUNK_ROWS
            || c.chunk_index as usize >= crate::geo_source::MAX_CHUNKS
        {
            return Err(GeoSnapshotError::Stale);
        }
        put32(&mut b, 40, 1);
        put64(&mut b, 48, c.generation);
        b[56..64].copy_from_slice(&c.source_digest);
        b[64..72].copy_from_slice(&c.query_digest);
        put32(&mut b, 72, c.chunk_index);
        put32(&mut b, 76, c.row);
    }
    let mut h = Blake2s8::new();
    h.update(b"xyg-frozen-membership-v1");
    h.update(&identity_header(identity));
    h.update(&layer_bytes(layer));
    h.update(&b[16..40]);
    let token = h.finish();
    b[8..16].copy_from_slice(&token);
    Ok(b)
}
fn identity_header(identity: &GeoFrozenIdentity) -> [u8; HEADER] {
    let mut b = [0; HEADER];
    b[..4].copy_from_slice(b"XYGX");
    put32(&mut b, 4, 2);
    put32(&mut b, 8, SCENE_VERSION);
    match identity.time {
        TimePredicate::All => (),
        TimePredicate::Instant(t) => {
            put32(&mut b, 52, 1);
            put64(&mut b, 56, t as u64);
        }
        TimePredicate::Window { start, end } => {
            put32(&mut b, 52, 2);
            put64(&mut b, 56, start as u64);
            put64(&mut b, 64, end as u64);
        }
    }
    put64(&mut b, 136, identity.camera_revision);
    put64(&mut b, 176, identity.time_revision);
    put32(&mut b, 72, identity.camera.crs as u32);
    put32(&mut b, 76, identity.camera.world_wrap as u32);
    for (i, v) in [
        identity.camera.center_x_bits,
        identity.camera.center_y_bits,
        identity.camera.zoom_bits,
        identity.camera.width_bits,
        identity.camera.height_bits,
        identity.camera.bearing_deg_bits,
        identity.camera.pitch_deg_bits,
    ]
    .into_iter()
    .enumerate()
    {
        put64(&mut b, 80 + i * 8, v);
    }
    b
}
#[cfg(feature = "raster")]
fn set_binding(b: &mut [u8], binding: Option<GeoFrozenArtifactBinding>) {
    b[144..176].fill(0);
    put32(b, 12, u32::from(binding.is_some()));
    if let Some(v) = binding {
        put32(b, 144, v.format as u32);
        put32(b, 148, v.quality as u32);
        put64(b, 152, v.scale.to_bits());
        put64(b, 160, v.bytes);
        b[168..176].copy_from_slice(&v.digest);
    }
}
fn peak(length: usize, budget: usize) -> Result<usize> {
    let required = length
        .checked_mul(8)
        .and_then(|n| n.checked_add(65_536))
        .ok_or(GeoSnapshotError::Limit)?;
    if length > MAX_FROZEN_BYTES || required > budget || budget > MAX_FROZEN_PEAK {
        return Err(GeoSnapshotError::Limit);
    }
    Ok(required)
}
fn mixed_peak(length: usize, budget: usize) -> Result<usize> {
    let required = length
        .checked_mul(32)
        .and_then(|n| n.checked_add(1 << 20))
        .ok_or(GeoSnapshotError::Limit)?;
    if length > MAX_FROZEN_BYTES || required > budget || budget > MAX_FROZEN_PEAK {
        return Err(GeoSnapshotError::Limit);
    }
    Ok(required)
}

impl GeoFrozenSnapshot {
    #[allow(clippy::too_many_arguments)]
    pub fn freeze(
        cache: &GeoTileCache,
        scene: &[u8],
        identity: &GeoFrozenIdentity,
        direct: &[GeoFrozenDirect],
        membership: &[GeoFrozenMembership],
        attributions: &[String],
        budget: usize,
    ) -> Result<Self> {
        Self::freeze_with_grids(
            cache,
            scene,
            identity,
            direct,
            membership,
            &[],
            attributions,
            budget,
        )
    }
    #[allow(clippy::too_many_arguments)]
    pub fn freeze_with_grids(
        cache: &GeoTileCache,
        scene: &[u8],
        identity: &GeoFrozenIdentity,
        direct: &[GeoFrozenDirect],
        membership: &[GeoFrozenMembership],
        grids: &[GeoFrozenGridInput<'_>],
        attributions: &[String],
        budget: usize,
    ) -> Result<Self> {
        Self::freeze_full(
            cache,
            scene,
            identity,
            direct,
            membership,
            grids,
            attributions,
            budget,
            &[],
        )
    }
    fn freeze_full(
        cache: &GeoTileCache,
        scene: &[u8],
        identity: &GeoFrozenIdentity,
        direct: &[GeoFrozenDirect],
        membership: &[GeoFrozenMembership],
        grids: &[GeoFrozenGridInput<'_>],
        attributions: &[String],
        budget: usize,
        tile: &[u8],
    ) -> Result<Self> {
        identity_validate(identity)?;
        if scene.len() > MAX_FROZEN_SCENE_BYTES
            || direct.len() > MAX_FROZEN_DIRECT
            || membership.len() > MAX_FROZEN_MEMBERSHIP
            || attributions.len() > MAX_FROZEN_ATTRIBUTIONS
        {
            return Err(GeoSnapshotError::Limit);
        }
        if grids.len() > MAX_FROZEN_LAYERS {
            return Err(GeoSnapshotError::Limit);
        }
        if grids.iter().enumerate().any(|(i, grid)| {
            grids[..i]
                .iter()
                .any(|previous| previous.key.identity.layer_id == grid.key.identity.layer_id)
        }) {
            return Err(GeoSnapshotError::Invalid);
        }
        let grid_cells = grids.iter().try_fold(0usize, |n, g| {
            grid_validate(identity, g, direct)?;
            n.checked_add(g.counts.len()).ok_or(GeoSnapshotError::Limit)
        })?;
        if grid_cells > MAX_FROZEN_GRID_CELLS {
            return Err(GeoSnapshotError::Limit);
        }
        let text = attributions.iter().try_fold(0usize, |n, v| {
            if invalid_attribution_text(v) {
                return Err(GeoSnapshotError::Attribution);
            }
            n.checked_add(4 + v.len()).ok_or(GeoSnapshotError::Limit)
        })?;
        let total = HEADER
            .checked_add(identity.layers.len() * LAYER)
            .and_then(|n| n.checked_add(direct.len() * DIRECT))
            .and_then(|n| n.checked_add(membership.len() * MEMBERSHIP))
            .and_then(|n| n.checked_add(grids.len() * GRID + grid_cells * 8))
            .and_then(|n| n.checked_add(text))
            .and_then(|n| n.checked_add(tile.len()))
            .and_then(|n| n.checked_add(scene.len()))
            .ok_or(GeoSnapshotError::Limit)?;
        let required = if tile.len() >= TILE_HEADER && u32at(tile, 4) == 2 {
            mixed_peak(total, budget)?
        } else {
            peak(total, budget)?
        };
        let charge = cache
            .reserve_derived(required)
            .map_err(|_| GeoSnapshotError::Limit)?;
        let mut b = Vec::with_capacity(total);
        b.extend_from_slice(&identity_header(identity));
        put64(&mut b, 16, total as u64);
        put64(&mut b, 24, scene.len() as u64);
        for (at, count) in [
            (32, identity.layers.len()),
            (36, direct.len()),
            (40, membership.len()),
            (44, attributions.len()),
            (48, text),
        ] {
            put32(&mut b, at, count as u32);
        }
        put32(&mut b, 184, grids.len() as u32);
        put32(&mut b, 188, tile.len() as u32);
        for layer in &identity.layers {
            b.extend_from_slice(&layer_bytes(layer));
        }
        for v in direct {
            b.extend_from_slice(&v.layer_id.to_le_bytes());
            b.extend_from_slice(&v.source_row.to_le_bytes());
            b.extend_from_slice(&v.feature_id.to_le_bytes());
            b.extend_from_slice(&v.chunk_index.to_le_bytes());
            b.extend_from_slice(&v.row.to_le_bytes());
            b.extend_from_slice(&v.vertex.to_le_bytes());
            b.extend_from_slice(&[0; 12]);
        }
        for v in membership {
            b.extend_from_slice(&membership_bytes(identity, *v)?);
        }
        for g in grids {
            let mut header = [0; GRID];
            write_grid_key(&mut header[..160], g.key);
            put64(&mut header, 160, g.counts.len() as u64);
            put64(&mut header, 168, g.visible_vertices);
            put64(&mut header, 176, g.projected_vertices);
            header[184..232].copy_from_slice(&g.style);
            b.extend_from_slice(&header);
            for i in 0..g.counts.len() {
                b.extend_from_slice(&g.counts.count(i).to_le_bytes());
            }
        }
        for v in attributions {
            b.extend_from_slice(&(v.len() as u32).to_le_bytes());
            b.extend_from_slice(v.as_bytes());
        }
        b.extend_from_slice(tile);
        b.extend_from_slice(scene);
        Self::decode_owned(b, charge)
    }
    pub fn decode(cache: &GeoTileCache, bytes: &[u8], budget: usize) -> Result<Self> {
        let mixed = if bytes.len() >= HEADER {
            let sl = usize::try_from(u64at(bytes, 24)).map_err(|_| GeoSnapshotError::Limit)?;
            let tl = u32at(bytes, 188) as usize;
            bytes
                .len()
                .checked_sub(sl)
                .and_then(|n| n.checked_sub(tl))
                .and_then(|at| bytes.get(at..at.checked_add(TILE_HEADER)?))
                .is_some_and(|b| tl >= TILE_HEADER && u32at(b, 4) == 2)
        } else {
            false
        };
        let required = if mixed {
            mixed_peak(bytes.len(), budget)?
        } else {
            peak(bytes.len(), budget)?
        };
        let charge = cache
            .reserve_derived(required)
            .map_err(|_| GeoSnapshotError::Limit)?;
        Self::decode_owned(bytes.to_vec(), charge)
    }
    fn decode_owned(b: Vec<u8>, charge: GeoDerivedLease) -> Result<Self> {
        if b.len() < HEADER
            || &b[..4] != b"XYGX"
            || u32at(&b, 4) != 2
            || u32at(&b, 8) != SCENE_VERSION
            || u32at(&b, 12) > 1
            || u64at(&b, 16) != b.len() as u64
        {
            return Err(GeoSnapshotError::Invalid);
        }
        let scene_len = usize::try_from(u64at(&b, 24)).map_err(|_| GeoSnapshotError::Limit)?;
        let counts = [
            u32at(&b, 32) as usize,
            u32at(&b, 36) as usize,
            u32at(&b, 40) as usize,
            u32at(&b, 44) as usize,
            u32at(&b, 48) as usize,
        ];
        if scene_len > MAX_FROZEN_SCENE_BYTES
            || counts[0] > MAX_FROZEN_LAYERS
            || counts[1] > MAX_FROZEN_DIRECT
            || counts[2] > MAX_FROZEN_MEMBERSHIP
            || counts[3] > MAX_FROZEN_ATTRIBUTIONS
            || counts[4] > MAX_FROZEN_ATTRIBUTIONS * (MAX_FROZEN_TEXT_BYTES + 4)
        {
            return Err(GeoSnapshotError::Limit);
        }
        let tables = HEADER
            .checked_add(counts[0] * LAYER)
            .and_then(|n| n.checked_add(counts[1] * DIRECT))
            .and_then(|n| n.checked_add(counts[2] * MEMBERSHIP))
            .ok_or(GeoSnapshotError::Limit)?;
        let grid_count = u32at(&b, 184) as usize;
        if grid_count > MAX_FROZEN_LAYERS {
            return Err(GeoSnapshotError::Limit);
        }
        let mut grid_end = tables;
        let mut grid_cells = 0usize;
        for _ in 0..grid_count {
            let end = grid_end
                .checked_add(GRID)
                .filter(|n| *n <= b.len())
                .ok_or(GeoSnapshotError::Invalid)?;
            let cells =
                usize::try_from(u64at(&b, grid_end + 160)).map_err(|_| GeoSnapshotError::Limit)?;
            grid_cells = grid_cells
                .checked_add(cells)
                .ok_or(GeoSnapshotError::Limit)?;
            if grid_cells > MAX_FROZEN_GRID_CELLS {
                return Err(GeoSnapshotError::Limit);
            }
            grid_end = cells
                .checked_mul(8)
                .and_then(|n| end.checked_add(n))
                .filter(|n| *n <= b.len())
                .ok_or(GeoSnapshotError::Invalid)?;
        }
        let attribution_end = grid_end
            .checked_add(counts[4])
            .ok_or(GeoSnapshotError::Limit)?;
        let tile_len = u32at(&b, 188) as usize;
        let scene_start = attribution_end
            .checked_add(tile_len)
            .ok_or(GeoSnapshotError::Limit)?;
        if scene_start.checked_add(scene_len) != Some(b.len()) {
            return Err(GeoSnapshotError::Invalid);
        }
        let time = match u32at(&b, 52) {
            0 if u64at(&b, 56) == 0 && u64at(&b, 64) == 0 => TimePredicate::All,
            1 if u64at(&b, 64) == 0 => TimePredicate::Instant(u64at(&b, 56) as i64),
            2 => TimePredicate::Window {
                start: u64at(&b, 56) as i64,
                end: u64at(&b, 64) as i64,
            },
            _ => return Err(GeoSnapshotError::Invalid),
        };
        if u32at(&b, 76) > 1 {
            return Err(GeoSnapshotError::Invalid);
        }
        let key = GeoViewportRebuildKey {
            crs: GeoCrs::from_u32(u32at(&b, 72)).ok_or(GeoSnapshotError::Invalid)?,
            world_wrap: u32at(&b, 76) == 1,
            center_x_bits: u64at(&b, 80),
            center_y_bits: u64at(&b, 88),
            zoom_bits: u64at(&b, 96),
            width_bits: u64at(&b, 104),
            height_bits: u64at(&b, 112),
            bearing_deg_bits: u64at(&b, 120),
            pitch_deg_bits: u64at(&b, 128),
        };
        let mut layers = Vec::with_capacity(counts[0]);
        let mut at = HEADER;
        for _ in 0..counts[0] {
            let s = &b[at..at + LAYER];
            if s[72..80].iter().any(|v| *v != 0) {
                return Err(GeoSnapshotError::Invalid);
            }
            layers.push(GeoFrozenLayer {
                layer_id: u64at(s, 0),
                source_id: u64at(s, 8),
                source_generation: u64at(s, 16),
                layer_revision: u64at(s, 24),
                style_revision: u64at(s, 32),
                state_revision: u64at(s, 40),
                source_digest: s[48..56].try_into().unwrap(),
                source_rows: u64at(s, 56),
                geometry: GeoGeometry::from_u32(u32at(s, 64)).ok_or(GeoSnapshotError::Invalid)?,
                crs: GeoCrs::from_u32(u32at(s, 68)).ok_or(GeoSnapshotError::Invalid)?,
            });
            at += LAYER;
        }
        let identity = GeoFrozenIdentity {
            camera: key,
            time,
            camera_revision: u64at(&b, 136),
            time_revision: u64at(&b, 176),
            layers,
        };
        identity_validate(&identity)?;
        let mut direct = Vec::with_capacity(counts[1]);
        for _ in 0..counts[1] {
            let value = GeoFrozenDirect {
                layer_id: u64at(&b, at),
                source_row: u64at(&b, at + 8),
                feature_id: u64at(&b, at + 16),
                chunk_index: u32at(&b, at + 24),
                row: u32at(&b, at + 28),
                vertex: u32at(&b, at + 32),
            };
            if b[at + 36..at + DIRECT].iter().any(|n| *n != 0)
                || value.chunk_index as usize >= crate::geo_source::MAX_CHUNKS
                || value.row as usize >= MAX_CHUNK_ROWS
            {
                return Err(GeoSnapshotError::Invalid);
            }
            if identity
                .layers
                .iter()
                .find(|v| v.layer_id == value.layer_id)
                .is_none_or(|v| value.source_row >= v.source_rows)
            {
                return Err(GeoSnapshotError::Invalid);
            }
            direct.push(value);
            at += DIRECT;
        }
        let mut membership = Vec::with_capacity(counts[2]);
        for _ in 0..counts[2] {
            let s = &b[at..at + MEMBERSHIP];
            if u32at(s, 40) > 1
                || s[44..48].iter().chain(&s[80..96]).any(|v| *v != 0)
                || (u32at(s, 40) == 0 && s[48..80].iter().any(|v| *v != 0))
            {
                return Err(GeoSnapshotError::Invalid);
            }
            let value = GeoFrozenMembership {
                layer_id: u64at(s, 0),
                cell: u32at(s, 16),
                columns: u32at(s, 20),
                rows: u32at(s, 24),
                kind: match u32at(s, 28) {
                    0 => GeoReducedKind::Cluster,
                    1 => GeoReducedKind::Density,
                    _ => return Err(GeoSnapshotError::Invalid),
                },
                member_count: u64at(s, 32),
                cursor: if u32at(s, 40) == 1 {
                    Some(QueryCursor {
                        generation: u64at(s, 48),
                        source_digest: s[56..64].try_into().unwrap(),
                        query_digest: s[64..72].try_into().unwrap(),
                        chunk_index: u32at(s, 72),
                        row: u32at(s, 76),
                    })
                } else {
                    None
                },
            };
            if membership_bytes(&identity, value)? != s {
                return Err(GeoSnapshotError::Stale);
            }
            membership.push(value);
            at += MEMBERSHIP;
        }
        let mut grids = Vec::with_capacity(grid_count);
        for _ in 0..grid_count {
            let key = read_grid_key(&b[at..at + 160])?;
            let cells = u64at(&b, at + 160) as usize;
            let visible_vertices = u64at(&b, at + 168);
            let projected_vertices = u64at(&b, at + 176);
            let style = b[at + 184..at + 232].try_into().unwrap();
            at += GRID;
            let vertex_counts = b[at..at + cells * 8]
                .chunks_exact(8)
                .map(|v| u64at(v, 0))
                .collect::<Vec<_>>();
            grid_validate(
                &identity,
                &GeoFrozenGridInput {
                    key,
                    visible_vertices,
                    projected_vertices,
                    counts: GeoFrozenGridCounts::Counts(&vertex_counts),
                    style,
                },
                &direct,
            )?;
            if grids
                .iter()
                .any(|g: &GeoFrozenGrid| g.key.identity.layer_id == key.identity.layer_id)
            {
                return Err(GeoSnapshotError::Invalid);
            }
            grids.push(GeoFrozenGrid {
                key,
                visible_vertices,
                projected_vertices,
                vertex_counts,
                style,
            });
            at += cells * 8;
        }
        let mut attributions = Vec::with_capacity(counts[3]);
        for _ in 0..counts[3] {
            if at.checked_add(4).is_none_or(|n| n > attribution_end) {
                return Err(GeoSnapshotError::Invalid);
            }
            let len = u32at(&b, at) as usize;
            at += 4;
            let end = at
                .checked_add(len)
                .filter(|n| *n <= attribution_end)
                .ok_or(GeoSnapshotError::Invalid)?;
            if len > MAX_FROZEN_TEXT_BYTES {
                return Err(GeoSnapshotError::Limit);
            }
            let text =
                std::str::from_utf8(&b[at..end]).map_err(|_| GeoSnapshotError::Attribution)?;
            if invalid_attribution_text(text) {
                return Err(GeoSnapshotError::Attribution);
            }
            attributions.push(text.to_owned());
            at = end;
        }
        if at != attribution_end {
            return Err(GeoSnapshotError::Invalid);
        }
        let scene = scene_start..b.len();
        let tile = if tile_len == 0 {
            None
        } else {
            let blob = &b[attribution_end..scene_start];
            if blob.len() < TILE_HEADER {
                return Err(GeoSnapshotError::Invalid);
            }
            if u32at(blob, 4) == 1
                && (!identity.layers.is_empty()
                    || !direct.is_empty()
                    || !membership.is_empty()
                    || !grids.is_empty()
                    || identity.time != TimePredicate::All
                    || identity.camera_revision != 0
                    || identity.time_revision != 0)
            {
                return Err(GeoSnapshotError::Invalid);
            }
            if u32at(blob, 4) == 2
                && (identity.layers.len() != 1 || grids.len() != 1 || !membership.is_empty())
            {
                return Err(GeoSnapshotError::Invalid);
            }
            validate_tile_blob(blob, &identity, &b[scene.clone()], &attributions)?;
            Some(attribution_end..scene_start)
        };
        let document =
            SceneDocument::decode(&b[scene.clone()]).map_err(|_| GeoSnapshotError::Scene)?;
        let (scene_width, scene_height) = document.viewport_size();
        if scene_width.to_bits() != key.width_bits || scene_height.to_bits() != key.height_bits {
            return Err(GeoSnapshotError::Stale);
        }
        if attributions
            .iter()
            .any(|text| !document.has_visible_attribution(text))
        {
            return Err(GeoSnapshotError::Attribution);
        }
        let binding = if u32at(&b, 12) == 1 {
            let v = GeoFrozenArtifactBinding {
                format: GeoFrozenFormat::from_code(u32at(&b, 144))?,
                quality: u32at(&b, 148) as i32,
                scale: f64::from_bits(u64at(&b, 152)),
                bytes: u64at(&b, 160),
                digest: b[168..176].try_into().unwrap(),
            };
            if !v.scale.is_finite()
                || v.scale <= 0.
                || !(1..=100).contains(&v.quality)
                || v.bytes == 0
                || v.bytes > MAX_FROZEN_ARTIFACT_BYTES as u64
            {
                return Err(GeoSnapshotError::Invalid);
            }
            Some(v)
        } else {
            if b[144..176].iter().any(|v| *v != 0) {
                return Err(GeoSnapshotError::Invalid);
            }
            None
        };
        Ok(Self {
            encoded: b,
            scene,
            tile,
            identity,
            direct,
            membership,
            grids,
            attributions,
            binding,
            _charge: charge,
        })
    }
    pub fn bytes(&self) -> &[u8] {
        &self.encoded
    }
    pub fn scene(&self) -> &[u8] {
        &self.encoded[self.scene.clone()]
    }
    /// Exact typed tile/catalog receipt provenance, with explicit external-time tag.
    pub fn tile_provenance(&self) -> Option<&[u8]> {
        self.tile.as_ref().map(|range| &self.encoded[range.clone()])
    }
    pub fn identity(&self) -> &GeoFrozenIdentity {
        &self.identity
    }
    pub fn direct(&self) -> &[GeoFrozenDirect] {
        &self.direct
    }
    pub fn membership(&self) -> &[GeoFrozenMembership] {
        &self.membership
    }
    pub fn grids(&self) -> &[GeoFrozenGrid] {
        &self.grids
    }
    pub fn attributions(&self) -> &[String] {
        &self.attributions
    }
    pub fn binding(&self) -> Option<GeoFrozenArtifactBinding> {
        self.binding
    }
    pub fn require_identity(&self, expected: &GeoFrozenIdentity) -> Result<()> {
        if &self.identity == expected {
            Ok(())
        } else {
            Err(GeoSnapshotError::Stale)
        }
    }
    pub fn verify_artifact(&self, bytes: &[u8]) -> Result<()> {
        let binding = self.binding.ok_or(GeoSnapshotError::Invalid)?;
        if binding.bytes != bytes.len() as u64
            || binding.digest != hash(b"xyg-frozen-artifact-v1", bytes)
        {
            return Err(GeoSnapshotError::Stale);
        }
        Ok(())
    }

    #[cfg(feature = "raster")]
    pub fn export(
        &self,
        cache: &GeoTileCache,
        expected: &GeoFrozenIdentity,
        format: GeoFrozenFormat,
        scale: f64,
        quality: i32,
        budget: usize,
    ) -> Result<GeoFrozenArtifact> {
        self.require_identity(expected)?;
        if !scale.is_finite() || scale <= 0. || !(1..=100).contains(&quality) {
            return Err(GeoSnapshotError::Invalid);
        }
        let camera = camera(self.identity.camera);
        let width = (camera.width * scale).ceil();
        let height = (camera.height * scale).ceil();
        if !width.is_finite()
            || !height.is_finite()
            || width < 1.
            || height < 1.
            || width > 65535.
            || height > 65535.
        {
            return Err(GeoSnapshotError::Limit);
        }
        let pixels = (width as usize)
            .checked_mul(height as usize)
            .ok_or(GeoSnapshotError::Limit)?;
        let peak = self
            .encoded
            .len()
            .checked_mul(32)
            .and_then(|n| pixels.checked_mul(64).and_then(|p| n.checked_add(p)))
            .and_then(|n| n.checked_add(1024 * 1024))
            .ok_or(GeoSnapshotError::Limit)?;
        if pixels > 2_000_000
            || peak > budget
            || budget > crate::geo_tile_cache::TILE_CACHE_PROCESS_BYTES
        {
            return Err(GeoSnapshotError::Limit);
        }
        let charge = cache
            .reserve_derived(peak)
            .map_err(|_| GeoSnapshotError::Limit)?;
        let native_format =
            crate::scene_static::SceneStaticFormat::from_code(if format == GeoFrozenFormat::Html {
                0
            } else {
                format as u32
            })
            .unwrap();
        let mut bytes = crate::scene_static::scene_static_export(
            self.scene(),
            native_format,
            scale,
            width as usize,
            height as usize,
            quality,
        )
        .map_err(|_| GeoSnapshotError::Export)?;
        let mut unbound = self.encoded.clone();
        set_binding(&mut unbound, None);
        let base64 = crate::scene::encode_base64(&unbound);
        if matches!(format, GeoFrozenFormat::Svg | GeoFrozenFormat::Html) {
            let mut svg = String::from_utf8(bytes).map_err(|_| GeoSnapshotError::Export)?;
            let end = svg.rfind("</svg>").ok_or(GeoSnapshotError::Export)?;
            let attrs = self
                .attributions
                .iter()
                .map(|text| escaped(text))
                .collect::<Vec<_>>()
                .join("; ");
            svg.insert_str(end,&format!("<metadata id=\"xyg-frozen-snapshot\">{base64}</metadata><metadata id=\"xyg-attribution\">{attrs}</metadata>"));
            bytes = svg.into_bytes();
            if format == GeoFrozenFormat::Html {
                let image = crate::scene::encode_base64(&bytes);
                let attribution = self
                    .attributions
                    .iter()
                    .map(|text| escaped(text))
                    .collect::<Vec<_>>()
                    .join("; ");
                // The frozen HTML is a static, self-contained replay of the
                // ordinary Scene export. No provider, script or external font
                // can fetch data or reinterpret temporal/LOD policy on reopen.
                bytes = format!("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src data:; base-uri 'none'; form-action 'none'\"><title>XYG frozen geographic scene</title><body><figure><img alt=\"Frozen geographic visualization\" width=\"{width}\" height=\"{height}\" src=\"data:image/svg+xml;base64,{image}\"><figcaption>{attribution}</figcaption></figure><template id=\"xyg-frozen-snapshot\">{base64}</template></body></html>").into_bytes();
            }
        } else if format == GeoFrozenFormat::Png {
            if bytes.len() < 12 || &bytes[bytes.len() - 8..bytes.len() - 4] != b"IEND" {
                return Err(GeoSnapshotError::Export);
            }
            let mut text = b"XYG frozen snapshot\0\0\0\0\0".to_vec();
            text.extend_from_slice(base64.as_bytes());
            let end = bytes.split_off(bytes.len() - 12);
            crate::png_encode::push_chunk(&mut bytes, b"iTXt", &text);
            bytes.extend_from_slice(&end);
        }
        if bytes.len() > MAX_FROZEN_ARTIFACT_BYTES {
            return Err(GeoSnapshotError::Limit);
        }
        let binding = GeoFrozenArtifactBinding {
            format,
            scale,
            quality,
            bytes: bytes.len() as u64,
            digest: hash(b"xyg-frozen-artifact-v1", &bytes),
        };
        set_binding(&mut unbound, Some(binding));
        Ok(GeoFrozenArtifact {
            bytes,
            snapshot: unbound,
            binding,
            _charge: charge,
        })
    }
}

fn write_grid_key(b: &mut [u8], key: GeoLodKey) {
    b.fill(0);
    b[..8].copy_from_slice(&key.identity.source_digest);
    for (at, v) in [
        (8, key.identity.generation),
        (16, key.identity.source_rows),
        (32, key.identity.layer_id),
        (40, key.identity.style_revision),
        (48, key.identity.state_revision),
    ] {
        put64(b, at, v);
    }
    put32(b, 24, key.identity.crs as u32);
    put32(b, 28, key.identity.geometry as u32);
    put32(b, 56, key.camera.crs as u32);
    put32(b, 60, u32::from(key.camera.world_wrap));
    for (i, v) in [
        key.camera.center_x_bits,
        key.camera.center_y_bits,
        key.camera.zoom_bits,
        key.camera.width_bits,
        key.camera.height_bits,
        key.camera.bearing_deg_bits,
        key.camera.pitch_deg_bits,
    ]
    .into_iter()
    .enumerate()
    {
        put64(b, 64 + i * 8, v);
    }
    match key.time {
        TimePredicate::All => {}
        TimePredicate::Instant(t) => {
            put32(b, 120, 1);
            put64(b, 128, t as u64);
        }
        TimePredicate::Window { start, end } => {
            put32(b, 120, 2);
            put64(b, 128, start as u64);
            put64(b, 136, end as u64);
        }
    }
    put32(
        b,
        124,
        if key.kind == GeoReducedKind::Cluster {
            0
        } else {
            1
        },
    );
    put32(b, 144, u32::from(key.direct));
    put32(b, 148, key.columns);
    put32(b, 152, key.rows);
}
fn read_grid_key(b: &[u8]) -> Result<GeoLodKey> {
    if b.len() != 160
        || b[156..160].iter().any(|n| *n != 0)
        || u32at(b, 60) > 1
        || u32at(b, 144) > 1
    {
        return Err(GeoSnapshotError::Invalid);
    }
    let time = match u32at(b, 120) {
        0 if u64at(b, 128) == 0 && u64at(b, 136) == 0 => TimePredicate::All,
        1 if u64at(b, 136) == 0 => TimePredicate::Instant(u64at(b, 128) as i64),
        2 => TimePredicate::Window {
            start: u64at(b, 128) as i64,
            end: u64at(b, 136) as i64,
        },
        _ => return Err(GeoSnapshotError::Invalid),
    };
    let crs = |at| GeoCrs::from_u32(u32at(b, at)).ok_or(GeoSnapshotError::Invalid);
    Ok(GeoLodKey {
        identity: GeoLodIdentity {
            source_digest: b[..8].try_into().unwrap(),
            generation: u64at(b, 8),
            source_rows: u64at(b, 16),
            crs: crs(24)?,
            geometry: GeoGeometry::from_u32(u32at(b, 28)).ok_or(GeoSnapshotError::Invalid)?,
            layer_id: u64at(b, 32),
            style_revision: u64at(b, 40),
            state_revision: u64at(b, 48),
        },
        camera: GeoViewportRebuildKey {
            crs: crs(56)?,
            world_wrap: u32at(b, 60) == 1,
            center_x_bits: u64at(b, 64),
            center_y_bits: u64at(b, 72),
            zoom_bits: u64at(b, 80),
            width_bits: u64at(b, 88),
            height_bits: u64at(b, 96),
            bearing_deg_bits: u64at(b, 104),
            pitch_deg_bits: u64at(b, 112),
        },
        time,
        kind: match u32at(b, 124) {
            0 => GeoReducedKind::Cluster,
            1 => GeoReducedKind::Density,
            _ => return Err(GeoSnapshotError::Invalid),
        },
        direct: u32at(b, 144) == 1,
        columns: u32at(b, 148),
        rows: u32at(b, 152),
    })
}
fn grid_validate(
    identity: &GeoFrozenIdentity,
    g: &GeoFrozenGridInput<'_>,
    direct: &[GeoFrozenDirect],
) -> Result<()> {
    let key = g.key;
    let layer = identity
        .layers
        .iter()
        .find(|l| l.layer_id == key.identity.layer_id)
        .ok_or(GeoSnapshotError::Invalid)?;
    let cells = (key.columns as usize)
        .checked_mul(key.rows as usize)
        .ok_or(GeoSnapshotError::Limit)?;
    let cap = if key.kind == GeoReducedKind::Cluster {
        CLUSTER_CELL_LIMIT
    } else {
        DENSITY_CELL_LIMIT
    };
    if (!key.direct && cells == 0)
        || (key.direct && (cells != 0 || key.columns != 0 || key.rows != 0))
        || cells > cap
        || g.counts.len() != cells
        || key.camera != identity.camera
        || key.time != identity.time
        || key.identity.source_digest != layer.source_digest
        || key.identity.generation != layer.source_generation
        || key.identity.source_rows != layer.source_rows
        || key.identity.crs != layer.crs
        || key.identity.geometry != layer.geometry
        || key.identity.style_revision != layer.style_revision
        || key.identity.state_revision != layer.state_revision
        || !matches!(layer.geometry, GeoGeometry::Point | GeoGeometry::MultiPoint)
        || g.visible_vertices > g.projected_vertices
    {
        return Err(GeoSnapshotError::Invalid);
    }
    let mut total = 0u64;
    for i in 0..cells {
        total = total
            .checked_add(g.counts.count(i))
            .ok_or(GeoSnapshotError::Limit)?;
    }
    if (key.direct
        && direct
            .iter()
            .filter(|p| p.layer_id == key.identity.layer_id)
            .count() as u64
            != g.visible_vertices)
        || (!key.direct && total != g.visible_vertices)
    {
        return Err(GeoSnapshotError::Invalid);
    }
    if g.style[33..48].iter().any(|n| *n != 0) {
        return Err(GeoSnapshotError::Invalid);
    }
    crate::geo_layers::validate_style(crate::geo_layers::GeoStyle {
        fill: g.style[..4].try_into().unwrap(),
        stroke: g.style[4..8].try_into().unwrap(),
        stroke_width: f64::from_bits(u64at(&g.style, 8)),
        diameter: f64::from_bits(u64at(&g.style, 16)),
        opacity: f64::from_bits(u64at(&g.style, 24)),
        symbol: g.style[32],
    })
    .map_err(|_| GeoSnapshotError::Invalid)?;
    Ok(())
}
impl GeoFrozenSnapshot {
    /// Freeze the already-rendered immutable retained frame, never recompile it.
    pub fn freeze_lod(
        cache: &GeoTileCache,
        scene: &[u8],
        result: &GeoPointResult,
        snapshot: GeoOperationSnapshot,
        style: &[u8; 48],
        budget: usize,
    ) -> Result<Self> {
        Self::freeze_lod_full(cache, scene, result, snapshot, style, budget, &[], &[])
    }
    fn freeze_lod_full(
        cache: &GeoTileCache,
        scene: &[u8],
        result: &GeoPointResult,
        snapshot: GeoOperationSnapshot,
        style: &[u8; 48],
        budget: usize,
        attributions: &[String],
        tile: &[u8],
    ) -> Result<Self> {
        // XYGX currently lacks the full XYSE intent/profile/count authority.
        // Reject before frozen allocation rather than silently lose selection.
        if result.selection.is_some() {
            return Err(GeoSnapshotError::Unsupported);
        }
        let k = result.key;
        if snapshot.source_digest != k.identity.source_digest
            || snapshot.generation != k.identity.generation
            || snapshot.layer_id != k.identity.layer_id
            || snapshot.style_revision != k.identity.style_revision
            || snapshot.state_revision != k.identity.state_revision
            || snapshot.camera != k.camera
            || snapshot.time != k.time
        {
            return Err(GeoSnapshotError::Stale);
        }
        let direct_len = match &result.output {
            GeoPointOutput::Direct(v) => v.len(),
            _ => 0,
        };
        if direct_len > MAX_FROZEN_DIRECT || budget > MAX_FROZEN_PEAK {
            return Err(GeoSnapshotError::Limit);
        }
        let scratch = direct_len
            .checked_mul(std::mem::size_of::<GeoFrozenDirect>())
            .and_then(|n| n.checked_add(8192))
            .ok_or(GeoSnapshotError::Limit)?;
        if scratch > budget {
            return Err(GeoSnapshotError::Limit);
        }
        let _scratch = cache
            .reserve_derived(scratch)
            .map_err(|_| GeoSnapshotError::Limit)?;
        let identity = GeoFrozenIdentity {
            camera: k.camera,
            time: k.time,
            camera_revision: snapshot.camera_revision,
            time_revision: snapshot.time_revision,
            layers: vec![GeoFrozenLayer {
                layer_id: k.identity.layer_id,
                source_id: 0,
                source_generation: k.identity.generation,
                layer_revision: snapshot.layer_revision,
                style_revision: k.identity.style_revision,
                state_revision: k.identity.state_revision,
                source_digest: k.identity.source_digest,
                source_rows: k.identity.source_rows,
                geometry: k.identity.geometry,
                crs: k.identity.crs,
            }],
        };
        let direct = match &result.output {
            GeoPointOutput::Direct(v) => v
                .iter()
                .map(|p| GeoFrozenDirect {
                    layer_id: k.identity.layer_id,
                    source_row: p.identity.source_row,
                    feature_id: p.identity.feature_id,
                    chunk_index: p.identity.chunk_index,
                    row: p.identity.row,
                    vertex: p.vertex,
                })
                .collect::<Vec<_>>(),
            _ => Vec::new(),
        };
        let grid = GeoFrozenGridInput {
            key: k,
            visible_vertices: result.visible_vertices,
            projected_vertices: result.projected_vertices,
            style: *style,
            counts: match &result.output {
                GeoPointOutput::Reduced(v) => GeoFrozenGridCounts::Cells(v),
                GeoPointOutput::Direct(_) => GeoFrozenGridCounts::Counts(&[]),
            },
        };
        Self::freeze_full(
            cache,
            scene,
            &identity,
            &direct,
            &[],
            std::slice::from_ref(&grid),
            attributions,
            budget.checked_sub(scratch).ok_or(GeoSnapshotError::Limit)?,
            tile,
        )
    }
}

const TILE_HEADER: usize = 64;
const TILE_SOURCE: usize = 128;
const TILE_STAMP: usize = 96;
fn tile_key_bytes(key: crate::geo_tile_cache::GeoTileKey) -> [u8; 80] {
    use crate::geo_tile_cache::GeoTileKind;
    let mut b = [0; 80];
    for (at, n) in [
        (0, key.source_id),
        (8, key.generation),
        (16, key.layer_id),
        (24, key.layer_revision),
        (32, key.style_revision),
    ] {
        put64(&mut b, at, n);
    }
    if let Some(t) = key.time {
        put64(&mut b, 40, t.start as u64);
        put64(&mut b, 48, t.end as u64);
        put32(&mut b, 56, 1);
    }
    put32(
        &mut b,
        60,
        if key.kind == GeoTileKind::RasterRgba {
            0
        } else {
            1
        },
    );
    for (at, n) in [(64, key.zoom as u32), (68, key.x), (72, key.y)] {
        put32(&mut b, at, n);
    }
    b
}
fn tile_source_header(
    source: &crate::geo_tile_cache::GeoTileSource,
) -> ([u8; TILE_SOURCE], &str, &str) {
    use crate::geo_tile_cache::{GeoTileKind, GeoTileLocation};
    let mut b = [0; TILE_SOURCE];
    for (at, n) in [
        (0, source.source_id),
        (8, source.generation),
        (16, source.layer_id),
        (24, source.layer_revision),
        (32, source.style_revision),
    ] {
        put64(&mut b, at, n);
    }
    if let Some(t) = source.time {
        put64(&mut b, 40, t.start as u64);
        put64(&mut b, 48, t.end as u64);
        put32(&mut b, 56, 1);
    }
    put32(
        &mut b,
        60,
        if source.kind == GeoTileKind::RasterRgba {
            0
        } else {
            1
        },
    );
    b[64] = source.min_zoom;
    b[65] = source.max_zoom;
    for (at, n) in [
        (72, source.payload_limits.max_bytes),
        (80, source.payload_limits.max_features),
        (88, source.payload_limits.max_vertices),
    ] {
        put64(&mut b, at, n as u64);
    }
    let (kind, locator, attr) = match &source.location {
        GeoTileLocation::Local { locator } => (0, locator.as_str(), ""),
        GeoTileLocation::Network {
            template,
            attribution,
        } => (1, template.as_str(), attribution.as_str()),
    };
    put32(&mut b, 96, locator.len() as u32);
    put32(&mut b, 100, attr.len() as u32);
    put32(&mut b, 104, kind);
    let mut digest = Blake2s8::new();
    digest.update(b"xyg-tile-source-config-v1");
    for part in [&b[60..66], &b[72..112], locator.as_bytes(), attr.as_bytes()] {
        digest.update(&(part.len() as u64).to_le_bytes());
        digest.update(part);
    }
    b[112..120].copy_from_slice(&digest.finish());
    (b, locator, attr)
}
fn tile_blob_size(view: &crate::geo_tile_protocol::GeoTileFrameView<'_>) -> Result<usize> {
    if view.sources.len() > 16 || view.keys.len() > 64 || view.provenance.len() != view.keys.len() {
        return Err(GeoSnapshotError::Limit);
    }
    view.sources.iter().try_fold(
        TILE_HEADER + view.keys.len() * TILE_STAMP + view.receipt.len(),
        |n, s| {
            s.validate().map_err(|_| GeoSnapshotError::Invalid)?;
            let (_, locator, attr) = tile_source_header(s);
            n.checked_add(TILE_SOURCE + locator.len() + attr.len())
                .ok_or(GeoSnapshotError::Limit)
        },
    )
}
impl GeoFrozenSnapshot {
    /// Freeze the complete already-composed mixed Scene and original authorities.
    /// The trusted caller borrows its retained SourceData anchor, never requeries.
    pub fn freeze_mixed(
        cache: &GeoTileCache,
        frame: &crate::geo_mixed_frame::GeoMixedFrame,
        foreground: &[u8],
        budget: usize,
    ) -> Result<Self> {
        let request = frame.authority();
        let receipt = frame.tile_receipt();
        if receipt.len() < 384 || budget > MAX_FROZEN_PEAK {
            return Err(GeoSnapshotError::Invalid);
        }
        if budget < 8192 {
            return Err(GeoSnapshotError::Limit);
        }
        let _fixed = cache
            .reserve_derived(8192)
            .map_err(|_| GeoSnapshotError::Limit)?;
        let budget = budget - 8192;
        let scene_len =
            usize::try_from(u64at(receipt, 256 + 72)).map_err(|_| GeoSnapshotError::Limit)?;
        let tile_scene = receipt
            .get(
                384..384usize
                    .checked_add(scene_len)
                    .ok_or(GeoSnapshotError::Limit)?,
            )
            .ok_or(GeoSnapshotError::Invalid)?;
        let keys: Vec<_> = request.tiles.iter().map(|p| p.key).collect();
        let view = crate::geo_tile_protocol::GeoTileFrameView {
            receipt,
            scene: tile_scene,
            camera: request.snapshot.camera,
            keys: &keys,
            sources: frame.tile_sources(),
            provenance: &request.tiles,
        };
        let length = tile_blob_size(&view)?
            .checked_add(foreground.len())
            .ok_or(GeoSnapshotError::Limit)?;
        let scratch = length
            .checked_mul(32)
            .and_then(|n| n.checked_add(1 << 20))
            .ok_or(GeoSnapshotError::Limit)?;
        if scratch > budget || foreground.len() > MAX_FROZEN_SCENE_BYTES {
            return Err(GeoSnapshotError::Limit);
        }
        let _scratch = cache
            .reserve_derived(scratch)
            .map_err(|_| GeoSnapshotError::Limit)?;
        let mut blob = vec![0; TILE_HEADER];
        blob.reserve_exact(length - TILE_HEADER);
        put32(&mut blob, 0, 1);
        put32(&mut blob, 4, 2);
        put32(
            &mut blob,
            8,
            match request.tile_time {
                crate::geo_mixed_frame::GeoMixedTileTime::Timeless => 4,
                crate::geo_mixed_frame::GeoMixedTileTime::ProducerWindow => 5,
                _ => return Err(GeoSnapshotError::Invalid),
            },
        );
        put32(&mut blob, 12, view.sources.len() as u32);
        put32(&mut blob, 16, keys.len() as u32);
        put32(&mut blob, 20, foreground.len() as u32);
        put64(&mut blob, 24, receipt.len() as u64);
        let rr = frame.retained_records();
        let sr = frame.retained_styles();
        for (at, n) in [(32, rr.start), (40, rr.end), (48, sr.start), (56, sr.end)] {
            put64(&mut blob, at, n as u64);
        }
        let mut attrs = Vec::new();
        for source in view.sources {
            let (h, locator, attr) = tile_source_header(source);
            blob.extend_from_slice(&h);
            blob.extend_from_slice(locator.as_bytes());
            blob.extend_from_slice(attr.as_bytes());
            if !attr.is_empty()
                && view.keys.iter().any(|key| {
                    key.source_id == source.source_id
                        && key.layer_id == source.layer_id
                        && key.generation == source.generation
                })
            {
                attrs.push(attr.to_owned());
            }
        }
        for stamp in view.provenance {
            blob.extend_from_slice(&tile_key_bytes(stamp.key));
            blob.extend_from_slice(&stamp.config_digest);
            blob.extend_from_slice(&stamp.payload_digest);
        }
        blob.extend_from_slice(receipt);
        blob.extend_from_slice(foreground);
        Self::freeze_lod_full(
            cache,
            frame.scene(),
            frame.result(),
            request.snapshot,
            frame.style(),
            budget - scratch,
            &attrs,
            &blob,
        )
    }
    /// The exact catalog receipt explicitly owns ordinary foreground metadata,
    /// including literal source IDs/styles. It is not a fabricated generation.
    pub fn freeze_tile(
        cache: &GeoTileCache,
        view: &crate::geo_tile_protocol::GeoTileFrameView<'_>,
        budget: usize,
    ) -> Result<Self> {
        let length = tile_blob_size(view)?;
        let scratch = length
            .checked_mul(4)
            .and_then(|n| n.checked_add(32768))
            .ok_or(GeoSnapshotError::Limit)?;
        if scratch > budget || budget > MAX_FROZEN_PEAK {
            return Err(GeoSnapshotError::Limit);
        }
        let _scratch = cache
            .reserve_derived(scratch)
            .map_err(|_| GeoSnapshotError::Limit)?;
        let mut blob = Vec::with_capacity(length);
        blob.resize(TILE_HEADER, 0);
        put32(&mut blob, 0, 1);
        put32(&mut blob, 4, 1);
        put32(&mut blob, 8, 3); // external-time + unspecified camera/time revisions
        put32(&mut blob, 12, view.sources.len() as u32);
        put32(&mut blob, 16, view.keys.len() as u32);
        put64(&mut blob, 24, view.receipt.len() as u64);
        let mut attrs = Vec::new();
        for source in view.sources {
            let (h, locator, attr) = tile_source_header(source);
            blob.extend_from_slice(&h);
            blob.extend_from_slice(locator.as_bytes());
            blob.extend_from_slice(attr.as_bytes());
            if !attr.is_empty()
                && view.keys.iter().any(|key| {
                    key.source_id == source.source_id
                        && key.layer_id == source.layer_id
                        && key.generation == source.generation
                })
            {
                attrs.push(attr.to_owned());
            }
        }
        for (i, stamp) in view.provenance.iter().enumerate() {
            if stamp.key != view.keys[i] {
                return Err(GeoSnapshotError::Stale);
            }
            blob.extend_from_slice(&tile_key_bytes(stamp.key));
            blob.extend_from_slice(&stamp.config_digest);
            blob.extend_from_slice(&stamp.payload_digest);
        }
        blob.extend_from_slice(view.receipt);
        let identity = GeoFrozenIdentity {
            camera: view.camera,
            time: TimePredicate::All,
            camera_revision: 0,
            time_revision: 0,
            layers: Vec::new(),
        };
        Self::freeze_full(
            cache,
            view.scene,
            &identity,
            &[],
            &[],
            &[],
            &attrs,
            budget - scratch,
            &blob,
        )
    }
}
fn validate_tile_blob(
    blob: &[u8],
    identity: &GeoFrozenIdentity,
    scene: &[u8],
    attrs: &[String],
) -> Result<()> {
    use crate::geo_tile_cache::{GeoTileKind, GeoTileLocation, GeoTileSource, GeoTileTime};
    let camera = identity.camera;
    if blob.len() < TILE_HEADER
        || u32at(blob, 0) != 1
        || !matches!(u32at(blob, 4), 1 | 2)
        || (u32at(blob, 4) == 1
            && (u32at(blob, 8) != 3
                || blob[20..24]
                    .iter()
                    .chain(blob[32..64].iter())
                    .any(|&v| v != 0)))
        || (u32at(blob, 4) == 2 && !matches!(u32at(blob, 8), 4 | 5))
    {
        return Err(GeoSnapshotError::Invalid);
    }
    if u32at(blob, 4) == 2
        && u32at(blob, 8) == 5
        && !matches!(identity.time, TimePredicate::Window { .. })
    {
        return Err(GeoSnapshotError::Stale);
    }
    let source_count = u32at(blob, 12) as usize;
    let key_count = u32at(blob, 16) as usize;
    if source_count > 16 || key_count > 64 {
        return Err(GeoSnapshotError::Limit);
    }
    let receipt_len = usize::try_from(u64at(blob, 24)).map_err(|_| GeoSnapshotError::Limit)?;
    let mut at = TILE_HEADER;
    let mut sources = Vec::with_capacity(source_count);
    let mut digests = Vec::with_capacity(source_count);
    for _ in 0..source_count {
        let h = blob
            .get(at..at.checked_add(TILE_SOURCE).ok_or(GeoSnapshotError::Limit)?)
            .ok_or(GeoSnapshotError::Invalid)?;
        at += TILE_SOURCE;
        if h[66..72]
            .iter()
            .chain(h[108..112].iter())
            .chain(h[120..128].iter())
            .any(|&v| v != 0)
            || u32at(h, 56) > 1
            || u32at(h, 60) > 1
            || u32at(h, 104) > 1
        {
            return Err(GeoSnapshotError::Invalid);
        }
        let ln = u32at(h, 96) as usize;
        let an = u32at(h, 100) as usize;
        if ln > 4096 || an > 4096 {
            return Err(GeoSnapshotError::Limit);
        }
        let text = blob
            .get(at..at.checked_add(ln + an).ok_or(GeoSnapshotError::Limit)?)
            .ok_or(GeoSnapshotError::Invalid)?;
        at += ln + an;
        let locator = std::str::from_utf8(&text[..ln]).map_err(|_| GeoSnapshotError::Invalid)?;
        let attr = std::str::from_utf8(&text[ln..]).map_err(|_| GeoSnapshotError::Invalid)?;
        let time = if u32at(h, 56) == 1 {
            Some(GeoTileTime {
                start: u64at(h, 40) as i64,
                end: u64at(h, 48) as i64,
            })
        } else {
            if h[40..56].iter().any(|&v| v != 0) {
                return Err(GeoSnapshotError::Invalid);
            }
            None
        };
        let location = if u32at(h, 104) == 0 {
            if !attr.is_empty() {
                return Err(GeoSnapshotError::Invalid);
            }
            GeoTileLocation::Local {
                locator: locator.to_owned(),
            }
        } else {
            GeoTileLocation::Network {
                template: locator.to_owned(),
                attribution: attr.to_owned(),
            }
        };
        let source = GeoTileSource {
            source_id: u64at(h, 0),
            generation: u64at(h, 8),
            layer_id: u64at(h, 16),
            layer_revision: u64at(h, 24),
            style_revision: u64at(h, 32),
            time,
            kind: if u32at(h, 60) == 0 {
                GeoTileKind::RasterRgba
            } else {
                GeoTileKind::VectorXygd
            },
            location,
            min_zoom: h[64],
            max_zoom: h[65],
            payload_limits: crate::geo::GeoLimits {
                max_bytes: usize::try_from(u64at(h, 72)).map_err(|_| GeoSnapshotError::Limit)?,
                max_features: usize::try_from(u64at(h, 80)).map_err(|_| GeoSnapshotError::Limit)?,
                max_vertices: usize::try_from(u64at(h, 88)).map_err(|_| GeoSnapshotError::Limit)?,
            },
        };
        source.validate().map_err(|_| GeoSnapshotError::Invalid)?;
        if sources.iter().any(|s: &GeoTileSource| {
            s.source_id == source.source_id && s.layer_id == source.layer_id
        }) {
            return Err(GeoSnapshotError::Invalid);
        }
        let (canonical, _, _) = tile_source_header(&source);
        if canonical != h {
            return Err(GeoSnapshotError::Stale);
        }
        digests.push(<[u8; 8]>::try_from(&h[112..120]).unwrap());
        sources.push(source);
    }
    let keys_start = at;
    let key_end = at
        .checked_add(key_count * TILE_STAMP)
        .ok_or(GeoSnapshotError::Limit)?;
    let keys = blob.get(at..key_end).ok_or(GeoSnapshotError::Invalid)?;
    at = key_end;
    let mut mixed_keys = Vec::with_capacity(if u32at(blob, 4) == 2 { key_count } else { 0 });
    for (i, k) in keys.chunks_exact(TILE_STAMP).enumerate() {
        if k[76..80].iter().any(|&v| v != 0)
            || u32at(k, 56) > 1
            || u32at(k, 60) > 1
            || u32at(k, 64) > 25
        {
            return Err(GeoSnapshotError::Invalid);
        }
        if keys[..i * TILE_STAMP]
            .chunks_exact(TILE_STAMP)
            .any(|other| other[..80] == k[..80])
        {
            return Err(GeoSnapshotError::Invalid);
        }
        let source = sources
            .iter()
            .position(|s| s.source_id == u64at(k, 0) && s.layer_id == u64at(k, 16))
            .ok_or(GeoSnapshotError::Stale)?;
        let s = &sources[source];
        let key = crate::geo_tile_cache::GeoTileKey {
            source_id: s.source_id,
            generation: s.generation,
            layer_id: s.layer_id,
            layer_revision: s.layer_revision,
            style_revision: s.style_revision,
            time: s.time,
            kind: s.kind,
            zoom: u32at(k, 64) as u8,
            x: u32at(k, 68),
            y: u32at(k, 72),
        };
        if tile_key_bytes(key) != k[..80]
            || digests[source] != k[80..88]
            || key.zoom < s.min_zoom
            || key.zoom > s.max_zoom
            || key.x >= 1u32 << key.zoom
            || key.y >= 1u32 << key.zoom
        {
            return Err(GeoSnapshotError::Stale);
        }
        if u32at(blob, 4) == 2 {
            mixed_keys.push(key);
            if key.layer_id == identity.layers[0].layer_id {
                return Err(GeoSnapshotError::Stale);
            }
            match (u32at(blob, 8), identity.time, key.time) {
                (4, _, None) => (),
                (5, TimePredicate::Window { start, end }, Some(t))
                    if t.start == start && t.end == end => {}
                _ => return Err(GeoSnapshotError::Stale),
            }
        }
    }
    let receipt = blob
        .get(at..at.checked_add(receipt_len).ok_or(GeoSnapshotError::Limit)?)
        .ok_or(GeoSnapshotError::Invalid)?;
    let foreground_len = if u32at(blob, 4) == 2 {
        u32at(blob, 20) as usize
    } else {
        0
    };
    if foreground_len > MAX_FROZEN_SCENE_BYTES
        || at
            .checked_add(receipt_len)
            .and_then(|n| n.checked_add(foreground_len))
            != Some(blob.len())
        || receipt.len() < 256
        || &receipt[..4] != b"XYGU"
        || u32at(receipt, 4) != 1
        || u32at(receipt, 8) != 1
        || receipt[12..16]
            .iter()
            .chain(receipt[144..256].iter())
            .any(|&v| v != 0)
    {
        return Err(GeoSnapshotError::Invalid);
    }
    let cat_len = usize::try_from(u64at(receipt, 40)).map_err(|_| GeoSnapshotError::Limit)?;
    let padded = cat_len.checked_add(7).ok_or(GeoSnapshotError::Limit)? & !7;
    let attr_len = usize::try_from(u64at(receipt, 64)).map_err(|_| GeoSnapshotError::Limit)?;
    if u64at(receipt, 48) != key_count as u64
        || u64at(receipt, 56) != attrs.len() as u64
        || 256usize
            .checked_add(padded)
            .and_then(|n| n.checked_add(key_count * 80 + attr_len))
            != Some(receipt.len())
        || u32at(receipt, 72) != camera.crs as u32
        || u32at(receipt, 76) != u32::from(camera.world_wrap)
    {
        return Err(GeoSnapshotError::Stale);
    }
    for (i, n) in [
        camera.center_x_bits,
        camera.center_y_bits,
        camera.zoom_bits,
        camera.width_bits,
        camera.height_bits,
        camera.bearing_deg_bits,
        camera.pitch_deg_bits,
    ]
    .iter()
    .enumerate()
    {
        if u64at(receipt, 80 + i * 8) != *n {
            return Err(GeoSnapshotError::Stale);
        }
    }
    let catalog = &receipt[256..256 + cat_len];
    if catalog.len() < 128 || &catalog[..4] != b"XYLM" || u32at(catalog, 4) != 1 {
        return Err(GeoSnapshotError::Stale);
    }
    let tile_scene_len =
        usize::try_from(u64at(catalog, 72)).map_err(|_| GeoSnapshotError::Limit)?;
    let tile_scene = catalog
        .get(
            128..128usize
                .checked_add(tile_scene_len)
                .ok_or(GeoSnapshotError::Limit)?,
        )
        .ok_or(GeoSnapshotError::Invalid)?;
    if u32at(blob, 4) == 1 {
        if tile_scene != scene {
            return Err(GeoSnapshotError::Stale);
        }
    } else {
        let foreground = &blob[at + receipt_len..];
        let back =
            crate::scene::validate_scene_batch(tile_scene).map_err(|_| GeoSnapshotError::Scene)?;
        let front =
            crate::scene::validate_scene_batch(foreground).map_err(|_| GeoSnapshotError::Scene)?;
        if [
            u64at(blob, 32),
            u64at(blob, 40),
            u64at(blob, 48),
            u64at(blob, 56),
        ] != [
            back.records as u64,
            (back.records + front.records) as u64,
            back.styles as u64,
            (back.styles + front.styles) as u64,
        ] || SceneDocument::compose_geographic(tile_scene, foreground)
            .map_err(|_| GeoSnapshotError::Scene)?
            != scene
        {
            return Err(GeoSnapshotError::Stale);
        }
    }
    if u32at(blob, 4) == 2 {
        crate::geo_mixed_frame::basemap_layers(
            &crate::geo_tile_protocol::GeoTileFrameView {
                receipt,
                scene: tile_scene,
                camera,
                keys: &mixed_keys,
                sources: &sources,
                provenance: &[],
            },
            identity.layers[0].layer_id,
        )
        .map_err(|_| GeoSnapshotError::Stale)?;
    }
    if receipt[256 + cat_len..256 + padded].iter().any(|&v| v != 0) {
        return Err(GeoSnapshotError::Invalid);
    }
    for i in 0..key_count {
        if receipt[256 + padded + i * 80..256 + padded + (i + 1) * 80]
            != blob[keys_start + i * TILE_STAMP..keys_start + i * TILE_STAMP + 80]
        {
            return Err(GeoSnapshotError::Stale);
        }
    }
    let mut attr_at = 256 + padded + key_count * 80;
    for attr in attrs {
        let h = receipt
            .get(attr_at..attr_at + 8)
            .ok_or(GeoSnapshotError::Invalid)?;
        if h[4..8].iter().any(|&v| v != 0) || u32at(h, 0) != attr.len() as u32 {
            return Err(GeoSnapshotError::Stale);
        }
        let end = attr_at + 8 + attr.len();
        let next = (end + 7) & !7;
        if receipt.get(attr_at + 8..end) != Some(attr.as_bytes())
            || receipt
                .get(end..next)
                .is_none_or(|p| p.iter().any(|&v| v != 0))
        {
            return Err(GeoSnapshotError::Stale);
        }
        attr_at = next;
    }
    if attr_at != receipt.len() {
        return Err(GeoSnapshotError::Invalid);
    }
    let mut digest = Blake2s8::new();
    digest.update(b"xyg-tile-scene-receipt-v1");
    digest.update(&receipt[..136]);
    digest.update(&receipt[256..]);
    if receipt[136..144] != digest.finish() {
        return Err(GeoSnapshotError::Stale);
    }
    let source_attrs: Vec<&str> = sources
        .iter()
        .filter(|source| {
            keys.chunks_exact(TILE_STAMP).any(|key| {
                u64at(key, 0) == source.source_id
                    && u64at(key, 16) == source.layer_id
                    && u64at(key, 8) == source.generation
            })
        })
        .filter_map(|s| match &s.location {
            GeoTileLocation::Network { attribution, .. } => Some(attribution.as_str()),
            _ => None,
        })
        .collect();
    if source_attrs
        .iter()
        .copied()
        .ne(attrs.iter().map(String::as_str))
    {
        return Err(GeoSnapshotError::Stale);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo_tile_cache::{GeoTileLimits, test_process_lock};
    use crate::scene::{
        AxisScale, PlotLayout, ScaleKind, SceneBatch, SceneChromeStyle, SceneChromeText, SceneLabel,
    };

    fn identity() -> GeoFrozenIdentity {
        GeoFrozenIdentity {
            camera: GeoViewport::new(GeoCrs::Epsg4326, 45., 40., 2., 256., 64., 23., 40., true)
                .unwrap()
                .rebuild_key()
                .unwrap(),
            time: TimePredicate::Window {
                start: i64::MIN,
                end: i64::MAX,
            },
            camera_revision: u64::MAX,
            time_revision: u64::MAX - 1,
            layers: vec![GeoFrozenLayer {
                layer_id: u64::MAX,
                source_id: u64::MAX - 1,
                source_generation: 7,
                layer_revision: 8,
                style_revision: 9,
                state_revision: 10,
                source_digest: [11; 8],
                source_rows: 2,
                geometry: GeoGeometry::Point,
                crs: GeoCrs::Epsg4326,
            }],
        }
    }
    fn label(text: &str) -> SceneLabel {
        SceneLabel {
            stable_id: 9,
            x: 4.,
            y: 52.,
            font_size: 8.,
            rgba: [0, 0, 0, 255],
            anchor: 0,
            rotation: 0.,
            text: text.into(),
        }
    }
    fn scene(labels: Vec<SceneLabel>) -> Vec<u8> {
        let layout = PlotLayout::new(256., 64., 0., 0., 0., 0.).unwrap();
        let x = AxisScale::new(ScaleKind::Linear, 0., 1., 0., 256., 1., false).unwrap();
        let y = AxisScale::new(ScaleKind::Linear, 0., 1., 64., 0., 1., false).unwrap();
        SceneBatch::new_with_decorations_and_labels(
            layout,
            1,
            2,
            x,
            y,
            SceneChromeStyle {
                x_major_ticks: Some(Vec::new()),
                y_major_ticks: Some(Vec::new()),
                ..SceneChromeStyle::default()
            },
            SceneChromeText::default(),
            None,
            labels,
            &[0, 6, 6, 6, 7, 7],
            &[u64::MAX; 6],
            &[0; 6],
            &[20, 40, 80, 255],
            &[0; 4],
            &[0.],
            &[8., 0., 0., 0., 0., 0.],
            &[0; 6],
            &[0.5, 0.1, 0.4, 0.2, 0., 1.],
            &[0.5, 0.1, 0.1, 0.4, 0.8, 0.8],
            &[0.; 6],
            &[0.; 6],
        )
        .unwrap()
        .encode()
    }
    fn direct() -> [GeoFrozenDirect; 2] {
        [
            GeoFrozenDirect {
                layer_id: u64::MAX,
                source_row: 0,
                feature_id: u64::MAX,
                chunk_index: 0,
                row: 0,
                vertex: 0,
            },
            GeoFrozenDirect {
                layer_id: u64::MAX,
                source_row: 1,
                feature_id: u64::MAX,
                chunk_index: 0,
                row: 1,
                vertex: 1,
            },
        ]
    }
    fn membership() -> [GeoFrozenMembership; 1] {
        [GeoFrozenMembership {
            layer_id: u64::MAX,
            cell: 2,
            columns: 2,
            rows: 2,
            kind: GeoReducedKind::Cluster,
            member_count: 2,
            cursor: Some(QueryCursor {
                generation: 7,
                source_digest: [11; 8],
                query_digest: [12; 8],
                chunk_index: 0,
                row: 1,
            }),
        }]
    }
    fn cache() -> GeoTileCache {
        GeoTileCache::new(GeoTileLimits::default(), 0).unwrap()
    }

    #[test]
    fn deterministic_roundtrip_preserves_exact_scene_identity_time_and_full_ids() {
        let _lock = test_process_lock();
        let cache = cache();
        let s = scene(vec![label("© Local tiles")]);
        let id = identity();
        let attrs = vec!["© Local tiles".into()];
        let one = GeoFrozenSnapshot::freeze(
            &cache,
            &s,
            &id,
            &direct(),
            &membership(),
            &attrs,
            MAX_FROZEN_PEAK,
        )
        .unwrap();
        let two = GeoFrozenSnapshot::freeze(
            &cache,
            &s,
            &id,
            &direct(),
            &membership(),
            &attrs,
            MAX_FROZEN_PEAK,
        )
        .unwrap();
        assert_eq!(one.bytes(), two.bytes());
        let decoded = GeoFrozenSnapshot::decode(&cache, one.bytes(), MAX_FROZEN_PEAK).unwrap();
        assert_eq!(decoded.scene(), s);
        assert_eq!(decoded.identity(), &id);
        assert_eq!(decoded.direct(), direct());
        assert_eq!(decoded.membership(), membership());
        assert_eq!(decoded.attributions(), attrs);
        assert!(decoded.binding().is_none());
        assert_eq!(u32at(decoded.scene(), 4), 32);
    }
    #[test]
    fn stale_camera_time_layer_source_style_state_and_provenance_are_rejected() {
        let _lock = test_process_lock();
        let cache = cache();
        let id = identity();
        let s = scene(Vec::new());
        let frozen = GeoFrozenSnapshot::freeze(
            &cache,
            &s,
            &id,
            &direct(),
            &membership(),
            &[],
            MAX_FROZEN_PEAK,
        )
        .unwrap();
        for index in 0..7 {
            let mut stale = id.clone();
            match index {
                0 => stale.camera.zoom_bits = 3f64.to_bits(),
                1 => stale.time = TimePredicate::Instant(-1),
                2 => stale.layers[0].layer_revision += 1,
                3 => stale.layers[0].source_generation += 1,
                4 => stale.layers[0].style_revision += 1,
                5 => stale.layers[0].state_revision += 1,
                _ => stale.layers[0].source_digest[0] ^= 1,
            };
            assert_eq!(
                frozen.require_identity(&stale),
                Err(GeoSnapshotError::Stale)
            );
        }
        let mut stale = frozen.bytes().to_vec();
        let member = HEADER + LAYER + direct().len() * DIRECT;
        stale[member + 8] ^= 1;
        assert!(matches!(
            GeoFrozenSnapshot::decode(&cache, &stale, MAX_FROZEN_PEAK),
            Err(GeoSnapshotError::Stale)
        ));
        let mut cursor = membership();
        cursor[0].cursor.as_mut().unwrap().generation += 1;
        assert!(matches!(
            GeoFrozenSnapshot::freeze(&cache, &s, &id, &[], &cursor, &[], MAX_FROZEN_PEAK),
            Err(GeoSnapshotError::Stale)
        ));
    }
    #[test]
    fn attribution_requires_bounded_visible_literal_scene_labels() {
        let _lock = test_process_lock();
        let cache = cache();
        let id = identity();
        let attrs = vec!["Owner".to_string()];
        for labels in [
            Vec::new(),
            vec![SceneLabel {
                rgba: [0; 4],
                ..label("Owner")
            }],
            vec![SceneLabel {
                x: -100.,
                ..label("Owner")
            }],
            vec![SceneLabel {
                font_size: 7.,
                ..label("Owner")
            }],
            vec![SceneLabel {
                rotation: 10.,
                ..label("Owner")
            }],
        ] {
            assert!(matches!(
                GeoFrozenSnapshot::freeze(
                    &cache,
                    &scene(labels),
                    &id,
                    &[],
                    &[],
                    &attrs,
                    MAX_FROZEN_PEAK
                ),
                Err(GeoSnapshotError::Attribution)
            ));
        }
        for text in ["", "\u{0}", "line\nfeed", "\u{fffe}", "\u{ffff}"] {
            assert!(matches!(
                GeoFrozenSnapshot::freeze(
                    &cache,
                    &scene(Vec::new()),
                    &id,
                    &[],
                    &[],
                    &[text.into()],
                    MAX_FROZEN_PEAK
                ),
                Err(GeoSnapshotError::Attribution)
            ));
        }
        assert!(
            GeoFrozenSnapshot::freeze(
                &cache,
                &scene(vec![label("Owner")]),
                &id,
                &[],
                &[],
                &attrs,
                MAX_FROZEN_PEAK
            )
            .is_ok()
        );
    }
    #[test]
    fn malformed_lengths_flags_reserved_utf8_scene_and_exact_budget_fail_atomically() {
        let _lock = test_process_lock();
        let cache = cache();
        let id = identity();
        let s = scene(vec![label("Owner")]);
        let f = GeoFrozenSnapshot::freeze(
            &cache,
            &s,
            &id,
            &direct(),
            &membership(),
            &["Owner".into()],
            MAX_FROZEN_PEAK,
        )
        .unwrap();
        let before = cache.stats().derived_reserved_bytes;
        for at in [4, 8, 12, 16, 188] {
            let mut bad = f.bytes().to_vec();
            bad[at] = 255;
            assert!(GeoFrozenSnapshot::decode(&cache, &bad, MAX_FROZEN_PEAK).is_err());
            assert_eq!(cache.stats().derived_reserved_bytes, before);
        }
        for at in [24, 32, 36, 40, 44, 48] {
            let mut bad = f.bytes().to_vec();
            bad[at..at + 4].fill(255);
            assert!(GeoFrozenSnapshot::decode(&cache, &bad, MAX_FROZEN_PEAK).is_err());
        }
        let mut bad = f.bytes().to_vec();
        let text = HEADER + LAYER + direct().len() * DIRECT + MEMBERSHIP + 4;
        bad[text] = 255;
        assert!(matches!(
            GeoFrozenSnapshot::decode(&cache, &bad, MAX_FROZEN_PEAK),
            Err(GeoSnapshotError::Attribution)
        ));
        let mut bad = f.bytes().to_vec();
        bad[f.scene.start + 4] = 31;
        assert!(matches!(
            GeoFrozenSnapshot::decode(&cache, &bad, MAX_FROZEN_PEAK),
            Err(GeoSnapshotError::Scene)
        ));
        let required = peak(f.bytes().len(), MAX_FROZEN_PEAK).unwrap();
        assert!(matches!(
            GeoFrozenSnapshot::decode(&cache, f.bytes(), required - 1),
            Err(GeoSnapshotError::Limit)
        ));
        assert!(GeoFrozenSnapshot::decode(&cache, f.bytes(), required).is_ok());
        assert_eq!(cache.stats().derived_reserved_bytes, before);
    }
    #[test]
    fn immutable_storage_reservation_survives_cache_drop() {
        let _lock = test_process_lock();
        let cache = cache();
        let s = scene(Vec::new());
        let snapshot =
            GeoFrozenSnapshot::freeze(&cache, &s, &identity(), &[], &[], &[], MAX_FROZEN_PEAK)
                .unwrap();
        let global = cache.stats().process_charged_bytes;
        let held = cache.stats().derived_reserved_bytes;
        drop(cache);
        let other = self::cache();
        assert!(other.stats().process_charged_bytes >= held);
        assert_eq!(other.stats().process_charged_bytes, global);
        drop(snapshot);
        assert_eq!(other.stats().derived_reserved_bytes, 0);
    }
    #[cfg(feature = "raster")]
    #[test]
    fn six_formats_share_scene_visible_attribution_and_accountable_binding() {
        let _lock = test_process_lock();
        let cache = cache();
        let text = "A<&\"' ©";
        let id = identity();
        let s = scene(vec![label(text)]);
        let f = GeoFrozenSnapshot::freeze(
            &cache,
            &s,
            &id,
            &direct(),
            &membership(),
            &[text.into()],
            MAX_FROZEN_PEAK,
        )
        .unwrap();
        let before = cache.stats().derived_reserved_bytes;
        for format in [
            GeoFrozenFormat::Svg,
            GeoFrozenFormat::Png,
            GeoFrozenFormat::Pdf,
            GeoFrozenFormat::Jpeg,
            GeoFrozenFormat::Webp,
            GeoFrozenFormat::Html,
        ] {
            let artifact = f
                .export(
                    &cache,
                    &id,
                    format,
                    1.,
                    90,
                    crate::geo_tile_cache::TILE_CACHE_PROCESS_BYTES,
                )
                .unwrap();
            let paired =
                GeoFrozenSnapshot::decode(&cache, artifact.snapshot(), MAX_FROZEN_PEAK).unwrap();
            paired.verify_artifact(artifact.bytes()).unwrap();
            assert_eq!(paired.identity(), &id);
            assert_eq!(paired.attributions(), [text]);
            assert_eq!(paired.scene(), s);
            let mut wrong = artifact.bytes().to_vec();
            wrong[0] ^= 1;
            assert_eq!(paired.verify_artifact(&wrong), Err(GeoSnapshotError::Stale));
            match format {
                GeoFrozenFormat::Svg => {
                    let svg = std::str::from_utf8(artifact.bytes()).unwrap();
                    assert!(svg.contains("xyg-frozen-snapshot"));
                    assert!(svg.contains(
                        "<metadata id=\"xyg-attribution\">A&lt;&amp;&quot;&apos; ©</metadata>"
                    ));
                    assert!(!svg.contains("<script>"));
                }
                GeoFrozenFormat::Png => {
                    let mut decoder = png::Decoder::new(std::io::Cursor::new(artifact.bytes()));
                    decoder.set_transformations(png::Transformations::EXPAND);
                    let mut reader = decoder.read_info().unwrap();
                    let mut rgba = vec![0; reader.output_buffer_size().unwrap()];
                    let info = reader.next_frame(&mut rgba).unwrap();
                    assert!(
                        rgba[..info.buffer_size()]
                            .chunks_exact(info.color_type.samples())
                            .any(|p| p[..3] == [20, 40, 80])
                    );
                    reader.finish().unwrap();
                    assert_eq!(reader.info().utf8_text.len(), 1);
                    assert_eq!(reader.info().utf8_text[0].keyword, "XYG frozen snapshot");
                    let mut embedded = artifact.snapshot().to_vec();
                    set_binding(&mut embedded, None);
                    assert_eq!(
                        reader.info().utf8_text[0].get_text().unwrap(),
                        crate::scene::encode_base64(&embedded)
                    );
                }
                GeoFrozenFormat::Pdf => assert!(artifact.bytes().starts_with(b"%PDF")),
                GeoFrozenFormat::Jpeg => assert!(artifact.bytes().starts_with(&[255, 216])),
                GeoFrozenFormat::Webp => assert!(artifact.bytes().starts_with(b"RIFF")),
                GeoFrozenFormat::Html => {
                    let mut embedded = artifact.snapshot().to_vec();
                    set_binding(&mut embedded, None);
                    let html = std::str::from_utf8(artifact.bytes()).unwrap();
                    assert!(html.starts_with("<!doctype html>"));
                    assert!(html.contains("default-src 'none'; img-src data:"));
                    assert!(html.contains("data:image/svg+xml;base64,"));
                    assert!(html.contains(&format!(
                        "<template id=\"xyg-frozen-snapshot\">{}</template>",
                        crate::scene::encode_base64(&embedded)
                    )));
                    assert!(!html.contains("<script"));
                    assert!(!html.contains("src=\"http"));
                }
            }
            if !matches!(
                format,
                GeoFrozenFormat::Svg | GeoFrozenFormat::Png | GeoFrozenFormat::Html
            ) {
                assert_eq!(
                    artifact.bytes(),
                    crate::scene_static::scene_static_export(
                        &s,
                        crate::scene_static::SceneStaticFormat::from_code(format as u32).unwrap(),
                        1.,
                        256,
                        64,
                        90
                    )
                    .unwrap()
                );
            }
        }
        assert_eq!(cache.stats().derived_reserved_bytes, before);
        let mut stale = id.clone();
        stale.layers[0].state_revision += 1;
        assert!(matches!(
            f.export(
                &cache,
                &stale,
                GeoFrozenFormat::Png,
                1.,
                90,
                crate::geo_tile_cache::TILE_CACHE_PROCESS_BYTES
            ),
            Err(GeoSnapshotError::Stale)
        ));
        let mut wrong_viewport = id.clone();
        wrong_viewport.camera.width_bits = 128f64.to_bits();
        assert!(matches!(
            GeoFrozenSnapshot::freeze(&cache, &s, &wrong_viewport, &[], &[], &[], MAX_FROZEN_PEAK),
            Err(GeoSnapshotError::Stale)
        ));
        assert_eq!(cache.stats().derived_reserved_bytes, before);
    }
    #[test]
    fn compact_full_density_grid_preserves_vertex_counts_above_source_rows() {
        let _lock = test_process_lock();
        let cache = cache();
        let mut id = identity();
        id.layers[0].geometry = GeoGeometry::MultiPoint;
        id.layers[0].source_rows = 1;
        let layer = &id.layers[0];
        let key = GeoLodKey {
            identity: GeoLodIdentity {
                source_digest: layer.source_digest,
                generation: layer.source_generation,
                source_rows: 1,
                crs: layer.crs,
                geometry: layer.geometry,
                layer_id: layer.layer_id,
                style_revision: layer.style_revision,
                state_revision: layer.state_revision,
            },
            camera: id.camera,
            time: id.time,
            kind: GeoReducedKind::Density,
            direct: false,
            columns: 512,
            rows: 384,
        };
        let cells = vec![
            GeoPointCell {
                count: 2,
                x: 0.,
                y: 0.
            };
            DENSITY_CELL_LIMIT
        ];
        let result = GeoPointResult {
            key,
            output: GeoPointOutput::Reduced(cells),
            visible_vertices: 393216,
            projected_vertices: 786432,
            grid_capped: true,
            selection: None,
        };
        let paint = crate::geo_layers::GeoStyle::default();
        let scene = crate::geo_lod_scene::compile(&result, paint, MAX_FROZEN_PEAK).unwrap();
        let mut style = [0; 48];
        style[..4].copy_from_slice(&paint.fill);
        style[4..8].copy_from_slice(&paint.stroke);
        put64(&mut style, 8, paint.stroke_width.to_bits());
        put64(&mut style, 16, paint.diameter.to_bits());
        put64(&mut style, 24, paint.opacity.to_bits());
        style[32] = paint.symbol;
        let operation = GeoOperationSnapshot {
            source_digest: layer.source_digest,
            generation: layer.source_generation,
            camera: id.camera,
            time: id.time,
            camera_revision: id.camera_revision,
            time_revision: id.time_revision,
            layer_id: layer.layer_id,
            layer_revision: layer.layer_revision,
            style_revision: layer.style_revision,
            state_revision: layer.state_revision,
        };
        let frozen = GeoFrozenSnapshot::freeze_lod(
            &cache,
            &scene.scene,
            &result,
            operation,
            &style,
            MAX_FROZEN_PEAK,
        )
        .unwrap();
        assert_eq!(frozen.scene(), scene.scene);
        assert_eq!(frozen.grids().len(), 1);
        assert_eq!(frozen.grids()[0].vertex_counts.len(), 196608);
        assert_eq!(frozen.grids()[0].vertex_counts.iter().sum::<u64>(), 393216);
        assert_eq!(frozen.grids()[0].key, key);
        assert_eq!(frozen.grids()[0].style, style);
        assert_eq!(frozen.identity().camera_revision, u64::MAX);
        assert_eq!(frozen.identity().time_revision, u64::MAX - 1);
        assert!(frozen.bytes().len() < 4 * 1024 * 1024);
        let decoded = GeoFrozenSnapshot::decode(&cache, frozen.bytes(), MAX_FROZEN_PEAK).unwrap();
        assert_eq!(decoded.grids(), frozen.grids());
        let before = cache.stats().derived_reserved_bytes;
        let grid = HEADER + LAYER;
        for offset in [grid + 60, grid + 156, grid + 168, grid + 184 + 33] {
            let mut bad = frozen.bytes().to_vec();
            bad[offset] ^= 0x80;
            assert!(GeoFrozenSnapshot::decode(&cache, &bad, MAX_FROZEN_PEAK).is_err());
            assert_eq!(cache.stats().derived_reserved_bytes, before);
        }
        let mut stale = frozen.identity().clone();
        stale.camera_revision -= 1;
        assert_eq!(
            frozen.require_identity(&stale),
            Err(GeoSnapshotError::Stale)
        );
    }
}
