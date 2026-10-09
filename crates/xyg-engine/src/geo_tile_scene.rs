//! Rust-owned raster XYZ composition; dossier §22/§27/§29.
//! Tile transport/decoding is separate. Sampling uses the exact GeoViewport
//! inverse, including bearing/pitch, and emits the existing SceneImage.
use crate::geo::{GeoCrs, GeoError};
use crate::geo_tile_cache::{GeoTileKey, GeoTilePayload};
use crate::geo_viewport::{GeoViewport, WEB_MERCATOR_MAX};
use crate::scene::SceneImage;
use std::collections::BTreeMap;

/// Fields drop in declaration order: live Scene buffers precede their charge.
pub struct PreparedRasterScene {
    compiled: crate::geo_layers::GeoCompiled,
    _charge: crate::geo_tile_cache::GeoDerivedLease,
}

impl PreparedRasterScene {
    /// Crate-only consuming transfer to the protocol's immutable receipt owner.
    /// That owner must drop compiled/encoded storage before its derived charge.
    pub(crate) fn into_parts(
        self,
    ) -> (
        crate::geo_layers::GeoCompiled,
        crate::geo_tile_cache::GeoDerivedLease,
    ) {
        (self.compiled, self._charge)
    }
    pub fn compiled(&self) -> &crate::geo_layers::GeoCompiled {
        &self.compiled
    }
}

/// Explicit vector source paint contract; tile feature IDs remain literal.
#[derive(Clone, Copy)]
pub struct GeoVectorTileStyle {
    pub layer_id: u64,
    pub kind: crate::geo_layers::GeoLayerKind,
    pub style: crate::geo_layers::GeoStyle,
}

/// Raster and vector basemaps use the ordinary geographic catalog. Multiple
/// tiles of one vector layer are concatenated in prepared-frame order before
/// compilation, preserving repeated-ID union semantics and source topology.
pub fn compile_tile_frame(
    cache: &crate::geo_tile_cache::GeoTileCache,
    epoch: u64,
    catalog: &crate::geo_layers::GeoCatalog<'_>,
    image_id: u64,
    vector_styles: &[GeoVectorTileStyle],
    cancel: &mut impl FnMut() -> bool,
) -> Result<PreparedRasterScene, TileSceneError> {
    use crate::geo::{GeoColumn, GeoDescriptor, GeoLimits};
    use crate::geo_layers::{GeoCatalog, GeoLayer};
    if catalog.budget > crate::geo_source::MAX_PROCESSOR_BYTES
        || catalog.budget < 131072
        || vector_styles.len() > 64
    {
        return Err(GeoError::ResourceLimit.into());
    }
    let frame = cache.prepared_frame(epoch)?;
    if catalog.viewport.rebuild_key()? != *frame.camera {
        return Err(GeoError::StaleHandle.into());
    }
    let charge = cache.reserve_derived(catalog.budget)?;
    let mut raw_bytes = 0usize;
    let mut simplify_bytes = 0usize;
    let mut raster = Vec::new();
    let mut groups: Vec<(u64, Vec<&GeoColumn>)> = Vec::new();
    for &key in frame.keys {
        if cancel() {
            return Err(TileSceneError::Cancelled);
        }
        let payload = cache.payload(key).ok_or(GeoError::StaleHandle)?;
        match payload {
            GeoTilePayload::Raster { .. } => raster.push((key, payload)),
            GeoTilePayload::Vector(column) => {
                if vector_styles
                    .iter()
                    .filter(|s| s.layer_id == key.layer_id)
                    .count()
                    != 1
                {
                    return Err(GeoError::InvalidArgument.into());
                }
                let bytes = column
                    .xy()
                    .len()
                    .checked_mul(8)
                    .and_then(|n| column.len().checked_mul(9).and_then(|v| n.checked_add(v)))
                    .and_then(|n| {
                        [column.offsets0(), column.offsets1(), column.offsets2()]
                            .iter()
                            .try_fold(n, |a, o| {
                                o.len().checked_mul(4).and_then(|v| a.checked_add(v))
                            })
                    })
                    .ok_or(GeoError::ResourceLimit)?;
                raw_bytes = raw_bytes
                    .checked_add(bytes)
                    .ok_or(GeoError::ResourceLimit)?;
                if !matches!(
                    column.geometry(),
                    crate::geo::GeoGeometry::Point | crate::geo::GeoGeometry::MultiPoint
                ) {
                    simplify_bytes = simplify_bytes
                        .checked_add(
                            crate::geo_simplify::materialization_bytes(column)
                                .map_err(TileSceneError::from)?,
                        )
                        .ok_or(GeoError::ResourceLimit)?;
                }
                if let Some((_, columns)) = groups.iter_mut().find(|(id, _)| *id == key.layer_id) {
                    columns.push(column);
                } else {
                    groups.push((key.layer_id, vec![column]));
                }
            }
        }
    }
    if groups.len() + catalog.layers.len() > crate::geo_layers::MAX_GEO_LAYERS {
        return Err(GeoError::ResourceLimit.into());
    }
    let merge_peak = raw_bytes
        .checked_mul(4)
        .and_then(|n| n.checked_add(simplify_bytes))
        .and_then(|n| n.checked_add(131072))
        .ok_or(GeoError::ResourceLimit)?;
    let compile_budget = catalog
        .budget
        .checked_sub(merge_peak)
        .ok_or(GeoError::ResourceLimit)?;
    let mut merged = Vec::with_capacity(groups.len());
    for (id, columns) in &groups {
        let first = columns[0];
        let mut xy = Vec::new();
        let mut validity = Vec::new();
        let mut ids = Vec::new();
        let mut offsets: [Vec<u32>; 3] = std::array::from_fn(|_| Vec::new());
        for column in columns {
            if cancel() {
                return Err(TileSceneError::Cancelled);
            }
            if column.geometry() != first.geometry() || column.crs() != first.crs() {
                return Err(GeoError::TypeMismatch.into());
            }
            xy.extend_from_slice(column.xy());
            validity.extend_from_slice(column.validity());
            ids.extend_from_slice(column.feature_ids());
            for (out, input) in
                offsets
                    .iter_mut()
                    .zip([column.offsets0(), column.offsets1(), column.offsets2()])
            {
                if input.is_empty() {
                    continue;
                }
                let base = out.last().copied().unwrap_or(0);
                if out.is_empty() {
                    out.push(0);
                }
                for &value in &input[1..] {
                    out.push(base.checked_add(value).ok_or(GeoError::ResourceLimit)?);
                }
            }
        }
        let column = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: first.geometry(),
            crs: first.crs(),
            xy: &xy,
            validity: &validity,
            feature_ids: Some(&ids),
            offsets0: &offsets[0],
            offsets1: &offsets[1],
            offsets2: &offsets[2],
            limits: GeoLimits {
                max_bytes: merge_peak,
                ..GeoLimits::default()
            },
        })?;
        let column = if !matches!(
            column.geometry(),
            crate::geo::GeoGeometry::Point | crate::geo::GeoGeometry::MultiPoint
        ) {
            let (center_x, center_y) = match column.crs() {
                GeoCrs::Epsg4326 => catalog.viewport.center_lonlat(),
                GeoCrs::Epsg3857 => catalog.viewport.center_mercator(),
            };
            let camera = GeoViewport {
                crs: column.crs(),
                center_x,
                center_y,
                ..catalog.viewport
            };
            let (_, reduced) = crate::geo_simplify::simplify_column(
                &column,
                &camera,
                crate::geo_simplify::SimplifyOptions {
                    max_bytes: simplify_bytes,
                    ..crate::geo_simplify::SimplifyOptions::default()
                },
                cancel,
            )
            .map_err(TileSceneError::from)?;
            reduced
        } else {
            column
        };
        merged.push((*id, column));
    }
    let mut layers = Vec::with_capacity(merged.len() + catalog.layers.len());
    for (id, column) in &merged {
        let configured = vector_styles.iter().find(|s| s.layer_id == *id).unwrap();
        let mut layer = GeoLayer::new(*id, configured.kind, column);
        layer.style = configured.style;
        layers.push(layer);
    }
    layers.extend(catalog.layers.iter().cloned());
    let image = if raster.is_empty() {
        None
    } else {
        Some(warp_raster_tiles(
            catalog.viewport,
            image_id,
            &raster,
            compile_budget,
            cancel,
        )?)
    };
    let combined = GeoCatalog {
        viewport: catalog.viewport,
        layers: &layers,
        legend: catalog.legend,
        budget: compile_budget,
    };
    let compiled = crate::geo_layers::compile_with_background(&combined, image)?;
    if cancel() {
        return Err(TileSceneError::Cancelled);
    }
    Ok(PreparedRasterScene {
        compiled,
        _charge: charge,
    })
}

/// Compile a complete candidate without committing its cache frame. A host
/// stages the returned ordinary painter buffers, then commits the same epoch.
pub fn compile_raster_frame(
    cache: &crate::geo_tile_cache::GeoTileCache,
    epoch: u64,
    catalog: &crate::geo_layers::GeoCatalog<'_>,
    image_id: u64,
    cancel: &mut impl FnMut() -> bool,
) -> Result<PreparedRasterScene, TileSceneError> {
    if catalog.budget > crate::geo_source::MAX_PROCESSOR_BYTES {
        return Err(GeoError::ResourceLimit.into());
    }
    let frame = cache.prepared_frame(epoch)?;
    if catalog.viewport.rebuild_key()? != *frame.camera {
        return Err(GeoError::StaleHandle.into());
    }
    let charge = cache.reserve_derived(catalog.budget)?;
    let mut tiles = Vec::with_capacity(frame.keys.len());
    for &key in frame.keys {
        let payload = cache.payload(key).ok_or(GeoError::StaleHandle)?;
        if !matches!(payload, GeoTilePayload::Raster { .. }) {
            return Err(GeoError::TypeMismatch.into());
        }
        tiles.push((key, payload));
    }
    let image = warp_raster_tiles(catalog.viewport, image_id, &tiles, catalog.budget, cancel)?;
    let compiled = crate::geo_layers::compile_with_background(catalog, Some(image))?;
    if cancel() {
        return Err(TileSceneError::Cancelled);
    }
    Ok(PreparedRasterScene {
        compiled,
        _charge: charge,
    })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TileSceneError {
    Geo(GeoError),
    Cancelled,
}
impl From<GeoError> for TileSceneError {
    fn from(error: GeoError) -> Self {
        Self::Geo(error)
    }
}
impl From<crate::geo_simplify::SimplifyError> for TileSceneError {
    fn from(error: crate::geo_simplify::SimplifyError) -> Self {
        use crate::geo_simplify::SimplifyError;
        match error {
            SimplifyError::Geo(error) => Self::Geo(error),
            SimplifyError::Cancelled => Self::Cancelled,
            SimplifyError::ResourceLimit => Self::Geo(GeoError::ResourceLimit),
            SimplifyError::InvalidOptions => Self::Geo(GeoError::InvalidArgument),
        }
    }
}

pub const MAX_BASEMAP_PIXELS: usize = 2_000_000;
pub const MAX_BASEMAP_TILES: usize = 64;

/// Source order is paint order. Keys must be a complete prepared cache frame.
/// Nearest-neighbour sampling is explicit; no host resampling/projection occurs.
pub fn warp_raster_tiles(
    camera: GeoViewport,
    image_id: u64,
    tiles: &[(GeoTileKey, &GeoTilePayload)],
    consumer_budget: usize,
    cancel: &mut impl FnMut() -> bool,
) -> Result<SceneImage, TileSceneError> {
    camera.validate()?;
    if tiles.len() > MAX_BASEMAP_TILES {
        return Err(GeoError::ResourceLimit.into());
    }
    let width = camera.width.ceil() as usize;
    let height = camera.height.ceil() as usize;
    let pixels = width.checked_mul(height).ok_or(GeoError::ResourceLimit)?;
    let bytes = pixels.checked_mul(4).ok_or(GeoError::ResourceLimit)?;
    if pixels > MAX_BASEMAP_PIXELS
        || bytes
            .checked_mul(5)
            .and_then(|n| tiles.len().checked_mul(2048).and_then(|s| n.checked_add(s)))
            .and_then(|n| n.checked_add(8192))
            .is_none_or(|n| n > consumer_budget)
    {
        return Err(GeoError::ResourceLimit.into());
    }
    let (mx, my) = camera.center_mercator();
    let mercator = GeoViewport {
        crs: GeoCrs::Epsg3857,
        center_x: mx,
        center_y: my,
        ..camera
    };
    let mut sources = Vec::new();
    let mut lookup = BTreeMap::new();
    let mut revisions = BTreeMap::new();
    for &(key, payload) in tiles {
        let GeoTilePayload::Raster {
            width,
            height,
            rgba,
        } = payload
        else {
            continue;
        };
        if key.zoom > 25
            || key.x >= 1 << key.zoom
            || key.y >= 1 << key.zoom
            || *width == 0
            || *height == 0
            || (*width as usize)
                .checked_mul(*height as usize)
                .and_then(|n| n.checked_mul(4))
                != Some(rgba.len())
        {
            return Err(GeoError::InvalidArgument.into());
        }
        let source = (key.source_id, key.layer_id, key.zoom);
        let revision = (
            key.generation,
            key.layer_revision,
            key.style_revision,
            key.time.map(|time| (time.start, time.end)),
            key.zoom,
        );
        if revisions
            .insert((key.source_id, key.layer_id), revision)
            .is_some_and(|old| old != revision)
        {
            return Err(GeoError::StaleHandle.into());
        }
        if !sources.contains(&source) {
            sources.push(source);
        }
        if lookup
            .insert((source, key.x, key.y), (*width, *height, rgba.as_slice()))
            .is_some()
        {
            return Err(GeoError::InvalidArgument.into());
        }
    }
    let mut rgba = vec![0; bytes];
    let world = 2.0 * WEB_MERCATOR_MAX;
    for y in 0..height {
        if cancel() {
            return Err(TileSceneError::Cancelled);
        }
        for x in 0..width {
            let (gx, gy) = mercator.unproject_mercator_ray(
                (x as f64 + 0.5) * camera.width / width as f64,
                (y as f64 + 0.5) * camera.height / height as f64,
            )?;
            let mut u = (gx + WEB_MERCATOR_MAX) / world;
            let v = (WEB_MERCATOR_MAX - gy) / world;
            if camera.world_wrap {
                u = u.rem_euclid(1.0);
            }
            if !(0.0..1.0).contains(&u) || !(0.0..1.0).contains(&v) {
                continue;
            }
            let dst: &mut [u8] = &mut rgba[(y * width + x) * 4..][..4];
            for &source in &sources {
                let n = (1u64 << source.2) as f64;
                let tx = (u * n).floor() as u32;
                let ty = (v * n).floor() as u32;
                if let Some(&(w, h, pixels)) = lookup.get(&(source, tx, ty)) {
                    let px = ((u * n - tx as f64) * w as f64).floor() as usize;
                    let py = ((v * n - ty as f64) * h as f64).floor() as usize;
                    let offset = (py.min(h as usize - 1) * w as usize + px.min(w as usize - 1)) * 4;
                    source_over(dst, &pixels[offset..offset + 4]);
                }
            }
        }
    }
    if cancel() {
        return Err(TileSceneError::Cancelled);
    }
    Ok(SceneImage {
        stable_id: image_id,
        width: width as u32,
        height: height as u32,
        rgba,
    })
}

fn source_over(dst: &mut [u8], src: &[u8]) {
    let sa = src[3] as u32;
    let da = dst[3] as u32;
    let alpha = sa * 255 + da * (255 - sa);
    if alpha == 0 {
        return;
    }
    for c in 0..3 {
        dst[c] = ((src[c] as u32 * sa * 255 + dst[c] as u32 * da * (255 - sa) + alpha / 2) / alpha)
            as u8;
    }
    dst[3] = ((alpha + 127) / 255) as u8;
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo_layers::{GeoCatalog, compile, compile_with_background};
    use crate::geo_tile_cache::GeoTileKind;

    fn camera() -> GeoViewport {
        GeoViewport::new(GeoCrs::Epsg3857, 0., 0., 0., 512., 512., 0., 0., true).unwrap()
    }
    fn key(source_id: u64) -> GeoTileKey {
        GeoTileKey {
            source_id,
            generation: 1,
            layer_id: source_id,
            layer_revision: 1,
            style_revision: 1,
            time: None,
            kind: GeoTileKind::RasterRgba,
            zoom: 0,
            x: 0,
            y: 0,
        }
    }
    fn quadrants() -> GeoTilePayload {
        GeoTilePayload::Raster {
            width: 2,
            height: 2,
            rgba: vec![
                255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 0, 255,
            ],
        }
    }
    fn pixel(image: &SceneImage, x: usize, y: usize) -> [u8; 4] {
        image.rgba[(y * image.width as usize + x) * 4..][..4]
            .try_into()
            .unwrap()
    }
    #[test]
    fn north_top_first_and_bearing_rotate_same_xyz_source() {
        let source = quadrants();
        let tiles = [(key(1), &source)];
        let image = warp_raster_tiles(camera(), 9, &tiles, 16 << 20, &mut || false).unwrap();
        assert_eq!(pixel(&image, 64, 64), [255, 0, 0, 255]);
        assert_eq!(pixel(&image, 448, 64), [0, 255, 0, 255]);
        assert_eq!(pixel(&image, 64, 448), [0, 0, 255, 255]);
        let rotated = GeoViewport {
            bearing_deg: 90.,
            ..camera()
        };
        let image = warp_raster_tiles(rotated, 9, &tiles, 16 << 20, &mut || false).unwrap();
        // Bearing is clockwise camera rotation: map north appears left.
        assert_eq!(pixel(&image, 64, 64), [0, 255, 0, 255]);
        assert_eq!(pixel(&image, 448, 64), [255, 255, 0, 255]);
    }
    #[test]
    fn pitch_uses_ground_inverse_not_axis_aligned_stretch() {
        let source = quadrants();
        let pitched = GeoViewport {
            pitch_deg: 40.,
            bearing_deg: 23.,
            ..camera()
        };
        let image =
            warp_raster_tiles(pitched, 9, &[(key(1), &source)], 16 << 20, &mut || false).unwrap();
        let GeoTilePayload::Raster { rgba, .. } = &source else {
            unreachable!()
        };
        for (mx, my, expected) in [
            (-WEB_MERCATOR_MAX / 2., WEB_MERCATOR_MAX / 2., 0),
            (WEB_MERCATOR_MAX / 2., -WEB_MERCATOR_MAX / 2., 3),
        ] {
            let (x, y) = pitched.project(mx, my).unwrap();
            assert_eq!(
                pixel(&image, x.floor() as usize, y.floor() as usize),
                rgba[expected * 4..][..4]
            );
        }
    }
    #[test]
    fn ordered_alpha_and_missing_tiles_are_explicit() {
        let red = GeoTilePayload::Raster {
            width: 1,
            height: 1,
            rgba: vec![255, 0, 0, 255],
        };
        let blue = GeoTilePayload::Raster {
            width: 1,
            height: 1,
            rgba: vec![0, 0, 255, 128],
        };
        let image = warp_raster_tiles(
            camera(),
            9,
            &[(key(1), &red), (key(2), &blue)],
            16 << 20,
            &mut || false,
        )
        .unwrap();
        assert_eq!(pixel(&image, 4, 4), [127, 0, 128, 255]);
        assert_eq!(
            pixel(
                &warp_raster_tiles(camera(), 9, &[], 16 << 20, &mut || false).unwrap(),
                4,
                4
            ),
            [0; 4]
        );
    }
    #[test]
    fn malformed_budget_and_cancellation_publish_nothing() {
        let bad = GeoTilePayload::Raster {
            width: 2,
            height: 2,
            rgba: vec![1],
        };
        assert_eq!(
            warp_raster_tiles(camera(), 9, &[(key(1), &bad)], 16 << 20, &mut || false),
            Err(TileSceneError::Geo(GeoError::InvalidArgument))
        );
        assert_eq!(
            warp_raster_tiles(camera(), 9, &[], 1, &mut || false),
            Err(TileSceneError::Geo(GeoError::ResourceLimit))
        );
        assert_eq!(
            warp_raster_tiles(camera(), 9, &[], 16 << 20, &mut || true),
            Err(TileSceneError::Cancelled)
        );
    }
    #[test]
    fn outside_world_rays_are_transparent_and_horizontal_wrap_is_explicit() {
        let source = quadrants();
        let north = GeoViewport {
            center_y: WEB_MERCATOR_MAX,
            ..camera()
        };
        let image =
            warp_raster_tiles(north, 9, &[(key(1), &source)], 16 << 20, &mut || false).unwrap();
        assert_eq!(pixel(&image, 256, 64), [0; 4]);
        assert_ne!(pixel(&image, 256, 448), [0; 4]);
        let west = GeoViewport {
            center_x: -WEB_MERCATOR_MAX,
            world_wrap: false,
            ..camera()
        };
        let image =
            warp_raster_tiles(west, 9, &[(key(1), &source)], 16 << 20, &mut || false).unwrap();
        assert_eq!(pixel(&image, 64, 64), [0; 4]);
        let wrapped = GeoViewport {
            world_wrap: true,
            ..west
        };
        let image =
            warp_raster_tiles(wrapped, 9, &[(key(1), &source)], 16 << 20, &mut || false).unwrap();
        assert_eq!(pixel(&image, 64, 64), [0, 255, 0, 255]);
    }
    #[test]
    fn tiny_image_budget_still_admits_tile_lookup_scratch() {
        let source = quadrants();
        let tiles: Vec<_> = (1..=64).map(|id| (key(id), &source)).collect();
        let tiny = GeoViewport {
            width: 1.,
            height: 1.,
            ..camera()
        };
        assert_eq!(
            warp_raster_tiles(tiny, 9, &tiles, 8192, &mut || false),
            Err(TileSceneError::Geo(GeoError::ResourceLimit))
        );
    }
    #[test]
    fn ordinary_scene_export_contains_basemap_and_empty_path_is_identical() {
        let catalog = GeoCatalog {
            viewport: camera(),
            layers: &[],
            legend: None,
            budget: 16 << 20,
        };
        assert_eq!(
            compile(&catalog).unwrap().scene,
            compile_with_background(&catalog, None).unwrap().scene
        );
        let source = quadrants();
        let image =
            warp_raster_tiles(camera(), 9, &[(key(1), &source)], 16 << 20, &mut || false).unwrap();
        let result = compile_with_background(&catalog, Some(image)).unwrap();
        let svg = crate::scene::SceneDocument::decode(&result.scene)
            .unwrap()
            .to_svg();
        assert!(svg.contains("data:image/png;base64,"));
        assert_eq!(result.style_owners, vec![None]);
    }
}
