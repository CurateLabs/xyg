//! Trusted retained Scene lowering under an opaque admitted transport phase.
//! See spec/design/geo-source-session.md; generic authored Scenes are not admitted.
use crate::geo_lod::{GeoPointOutput, CLUSTER_CELL_LIMIT, DENSITY_CELL_LIMIT, DIRECT_VERTEX_LIMIT};
use crate::geo_source::SourceError;
use crate::geo_transport::{GeoTransportPhase, PHASE_BYTES};
use crate::scene::SceneDocument;

/// The phase owner retains the returned painter until its transport storage is
/// dropped. Source registry -> transport phase is never acquired here: callers
/// acquire the opaque phase first, then borrow immutable SceneData authority.
pub struct GeoPreparedFramePainter {
    pub bytes: Vec<u8>,
    pub records: usize,
    pub styles: usize,
}

/// Persistent overview reservation: four packets, four painter copies, bounded
/// per-triangle CPU metadata and per-style traces. GPU storage is separate.
pub(crate) fn overview_persistent_bytes(
    scene: usize,
    painter: usize,
    records: usize,
    styles: usize,
) -> Result<usize, SourceError> {
    if records > crate::geo_temporal_overview_scene::MAX_RECORDS || records % 3 != 0 || styles > 256
    {
        return Err(SourceError::ResourceLimit);
    }
    scene
        .checked_add(256 + 2048)
        .and_then(|n| n.checked_mul(4))
        .and_then(|n| painter.checked_mul(4).and_then(|p| n.checked_add(p)))
        .and_then(|n| {
            (records / 3)
                .checked_mul(1024)
                .and_then(|p| n.checked_add(p))
        })
        .and_then(|n| styles.checked_mul(2048).and_then(|p| n.checked_add(p)))
        .and_then(|n| n.checked_add(1 << 20))
        .ok_or(SourceError::ResourceLimit)
}

pub fn prepare_frame_painter(
    handle: u64,
    sequence: u64,
    phase: &GeoTransportPhase<'_>,
) -> Result<GeoPreparedFramePainter, SourceError> {
    if crate::geo_scale_protocol::is_overview_data(handle, sequence)? {
        return crate::geo_scale_protocol::with_overview_data(handle, sequence, |bytes, _, _| {
            let peak = bytes
                .len()
                .checked_mul(32)
                .and_then(|n| n.checked_add(1 << 20))
                .ok_or(SourceError::ResourceLimit)?;
            if phase.budget() > PHASE_BYTES || peak > phase.budget() {
                return Err(SourceError::ResourceLimit);
            }
            // Rust's fixed triangle/style profile bounds all persistent copies
            // before decoded geometry or the painter output is allocated.
            if bytes.len() > crate::geo_temporal_overview_scene::MAX_ENCODED_SCENE_BYTES {
                return Err(SourceError::ResourceLimit);
            }
            let painter_bound = bytes
                .len()
                .checked_mul(2)
                .and_then(|n| n.checked_add(65536))
                .ok_or(SourceError::ResourceLimit)?;
            if overview_persistent_bytes(
                bytes.len(),
                painter_bound,
                crate::geo_temporal_overview_scene::MAX_RECORDS,
                256,
            )? > crate::geo_temporal_overview_scene::DATA_CREDIT
            {
                return Err(SourceError::ResourceLimit);
            }
            let scene = SceneDocument::decode(bytes).map_err(|_| SourceError::InvalidFrame)?;
            let records = scene.record_count();
            let styles = scene.style_count();
            let painter = scene
                .to_browser_painter(phase.budget())
                .map_err(|_| SourceError::ResourceLimit)?;
            if painter.len() > painter_bound
                || overview_persistent_bytes(bytes.len(), painter.len(), records, styles)?
                    > crate::geo_temporal_overview_scene::DATA_CREDIT
            {
                return Err(SourceError::ResourceLimit);
            }
            Ok(GeoPreparedFramePainter {
                bytes: painter,
                records,
                styles,
            })
        });
    }
    crate::geo_scale_protocol::with_scene_data(handle, sequence, |view| {
        let admitted_profile = match &view.result.output {
            GeoPointOutput::Direct(points) => points.len() <= DIRECT_VERTEX_LIMIT,
            GeoPointOutput::Reduced(cells) => {
                let maximum = match view.result.key.kind {
                    crate::geo_lod::GeoReducedKind::Cluster => CLUSTER_CELL_LIMIT,
                    crate::geo_lod::GeoReducedKind::Density => DENSITY_CELL_LIMIT,
                };
                cells.len() <= maximum
            }
        };
        let peak = view
            .scene
            .len()
            .checked_mul(32)
            .and_then(|n| n.checked_add(1 << 20))
            .ok_or(SourceError::ResourceLimit)?;
        if !admitted_profile || phase.budget() > PHASE_BYTES || peak > phase.budget() {
            return Err(SourceError::ResourceLimit);
        }
        // Authority is the Rust-generated one-layer point/density Scene with no
        // authored labels/gradients/glyphs. 32x encoded bytes covers decoded
        // record/style vectors, grouping scratch, image clones and painter Vec
        // capacity concurrently; fixed 1MiB covers layout/ticks/headers. This
        // bound does not apply to arbitrary host-supplied Scene bytes.
        let scene = SceneDocument::decode(view.scene).map_err(|_| SourceError::InvalidFrame)?;
        let records = scene.record_count();
        let styles = scene.style_count();
        let bytes = scene
            .to_browser_painter(phase.budget())
            .map_err(|_| SourceError::ResourceLimit)?;
        Ok(GeoPreparedFramePainter {
            bytes,
            records,
            styles,
        })
    })?
}

/// Tile FrameData occupies its own authority namespace. Its Rust-generated
/// geographic catalog Scene includes the raster background and visible labels.
pub fn prepare_tile_frame_painter(
    handle: u64,
    epoch: u64,
    phase: &GeoTransportPhase<'_>,
) -> Result<GeoPreparedFramePainter, SourceError> {
    if crate::geo_mixed_protocol::is_mixed_handle(handle) {
        return crate::geo_mixed_protocol::with_frame_data(handle, epoch, |view| {
            let peak = view
                .scene()
                .len()
                .checked_mul(32)
                .and_then(|n| n.checked_add(1 << 20))
                .ok_or(SourceError::ResourceLimit)?;
            if phase.budget() > PHASE_BYTES || peak > phase.budget() {
                return Err(SourceError::ResourceLimit);
            }
            let scene =
                SceneDocument::decode(view.scene()).map_err(|_| SourceError::InvalidFrame)?;
            let records = scene.record_count();
            let styles = scene.style_count();
            let bytes = scene
                .to_browser_painter(phase.budget())
                .map_err(|_| SourceError::ResourceLimit)?;
            Ok(GeoPreparedFramePainter {
                bytes,
                records,
                styles,
            })
        })?;
    }
    crate::geo_tile_protocol::with_frame_data(handle, epoch, |view| {
        let peak = view
            .scene
            .len()
            .checked_mul(32)
            .and_then(|n| n.checked_add(1 << 20))
            .ok_or(SourceError::ResourceLimit)?;
        if phase.budget() > PHASE_BYTES || peak > phase.budget() {
            return Err(SourceError::ResourceLimit);
        }
        let scene = SceneDocument::decode(view.scene).map_err(|_| SourceError::InvalidFrame)?;
        let records = scene.record_count();
        let styles = scene.style_count();
        let bytes = scene
            .to_browser_painter(phase.budget())
            .map_err(|_| SourceError::ResourceLimit)?;
        Ok(GeoPreparedFramePainter {
            bytes,
            records,
            styles,
        })
    })
    .map_err(|e| match e {
        crate::geo_tile_protocol::TileProtocolError::Geo(crate::geo::GeoError::ResourceLimit) => {
            SourceError::ResourceLimit
        }
        crate::geo_tile_protocol::TileProtocolError::Geo(crate::geo::GeoError::StaleHandle) => {
            SourceError::StaleSource
        }
        crate::geo_tile_protocol::TileProtocolError::Cancelled => SourceError::Cancelled,
        _ => SourceError::InvalidFrame,
    })?
}
