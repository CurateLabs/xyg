//! Rust-owned geographic viewport / camera (#48).
//!
//! `GeoViewport` is the host-neutral projection authority for geographic
//! scenes: center, zoom, size, bearing, pitch, CRS, and world-wrap policy.
//! MapLibre (or any shell) may feed camera events; this module owns the
//! equations, polar clamp, and rebuildable f32 offset encoding policy.
//!
//! Basemap tile lifecycle is out of scope (#49). This module lowers and clips
//! antimeridian-safe routes and closed polygon topology. Fill painting is #49.

use crate::geo::{GeoColumn, GeoCrs, GeoError, GeoGeometry, GeoLimits};
use std::collections::BTreeSet;
use std::mem::size_of;

/// Spherical Web Mercator radius used by EPSG:3857 (metres).
const EARTH_RADIUS_M: f64 = 6_378_137.0;

/// Web Mercator half-world extent (EPSG:3857), metres.
pub const WEB_MERCATOR_MAX: f64 = 20_037_508.342_789_244;

/// Maximum absolute latitude accepted by Web Mercator (~85.05112878°).
pub const MAX_WEB_MERCATOR_LAT_DEG: f64 = 85.051_128_779_806_6;

/// MapLibre-compatible world tile size in CSS pixels at zoom 0.
const TILE_SIZE: f64 = 512.0;

/// Mercator zero-elevation, zero-roll/padding default vertical FOV.
pub const GEO_VERTICAL_FOV_RAD: f64 = 0.643_501_108_793_284_4;

type ScreenPoint = (f64, f64);
type ScreenSegment = (ScreenPoint, ScreenPoint);

/// Absolute tolerances for projection goldens (metres / degrees / pixels).
pub mod tolerances {
    /// Lon/lat ↔ mercator round-trip (degrees).
    pub const LONLAT_DEG: f64 = 1e-9;
    /// Mercator metre round-trip.
    pub const MERCATOR_M: f64 = 1e-6;
    /// Screen-space project/unproject (CSS pixels).
    pub const SCREEN_PX: f64 = 1e-6;
}

/// Explicit geographic camera state shared by browser and headless hosts.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GeoViewport {
    /// CRS that interprets `center_x` / `center_y` and fit bounds.
    pub crs: GeoCrs,
    /// Camera center X (lon° for EPSG:4326, easting m for EPSG:3857).
    pub center_x: f64,
    /// Camera center Y (lat° for EPSG:4326, northing m for EPSG:3857).
    pub center_y: f64,
    /// MapLibre-style zoom (world width = `512 * 2^zoom` CSS pixels).
    pub zoom: f64,
    /// Viewport width in CSS pixels.
    pub width: f64,
    /// Viewport height in CSS pixels.
    pub height: f64,
    /// Clockwise bearing in degrees (0 = north up).
    pub bearing_deg: f64,
    /// Ground-plane perspective pitch in degrees (0 = nadir).
    pub pitch_deg: f64,
    /// When true, longitude differences wrap across ±180°.
    pub world_wrap: bool,
}

/// Exact, host-neutral identity for a frozen geographic camera.
///
/// Hosts may retain this value beside rebuildable painter buffers and compare
/// it after camera or context events. Float fields are represented by their
/// IEEE-754 bits, avoiding string formatting, host rounding, or JSON-number
/// identity. Validated viewports cannot contain NaN, so bit identity is also
/// semantic identity for this contract.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct GeoViewportRebuildKey {
    pub crs: GeoCrs,
    pub center_x_bits: u64,
    pub center_y_bits: u64,
    pub zoom_bits: u64,
    pub width_bits: u64,
    pub height_bits: u64,
    pub bearing_deg_bits: u64,
    pub pitch_deg_bits: u64,
    pub world_wrap: bool,
}

/// Screen-clipped line segments with stable source-feature identity.
///
/// Every offset range is one independent two-point segment. Keeping segments
/// independent avoids inventing a connection across the antimeridian or a
/// clipped-away portion of a route. Coordinates are offset-encoded f32 around
/// the f64 viewport centre, so painter uploads remain precise at deep zoom.
#[derive(Debug, Clone, PartialEq)]
pub struct ProjectedGeoLines {
    /// Interleaved centre-relative f32 screen coordinates.
    pub xy: Vec<f32>,
    /// Two-point segment boundaries; always `feature_ids.len() + 1` entries.
    pub offsets: Vec<u32>,
    /// Stable source-feature identity for each emitted segment.
    pub feature_ids: Vec<u64>,
    /// Viewport-centre f64 X origin used to decode `xy`.
    pub origin_x: f64,
    /// Viewport-centre f64 Y origin used to decode `xy`.
    pub origin_y: f64,
}

/// Cache identity for a derived scene buffer: exact camera identity plus the
/// digest of the source column's canonical `XYGM` metadata. Two projections
/// with equal keys are bit-identical, so a host may keep or drop the buffers
/// freely (§27: derived buffers are rebuildable caches).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct GeoDerivedKey {
    pub rebuild: GeoViewportRebuildKey,
    pub metadata_digest: [u8; 8],
}

/// Offset-encoded point vertices projected from a Point / MultiPoint column.
///
/// One entry per retained vertex (null points own no vertex), each tagged
/// with the source feature ID. `xy` is `f32` relative to the viewport centre
/// (`origin_x`, `origin_y` in f64 screen pixels).
#[derive(Debug, Clone, PartialEq)]
pub struct ProjectedGeoPoints {
    pub xy: Vec<f32>,
    pub feature_ids: Vec<u64>,
    pub origin_x: f64,
    pub origin_y: f64,
}

/// Closed projected polygon fragments, preserving shell/hole association.
#[derive(Debug, Clone, PartialEq)]
pub struct ProjectedGeoPolygons {
    pub xy: Vec<f32>,
    pub ring_offsets: Vec<u32>,
    pub polygon_offsets: Vec<u32>,
    pub feature_ids: Vec<u64>,
    pub ring_is_hole: Vec<u8>,
    pub origin_x: f64,
    pub origin_y: f64,
}

/// Projected payload for one column; the variant follows the geometry kind.
#[derive(Debug, Clone, PartialEq)]
pub enum ProjectedGeoGeometry {
    /// Point / MultiPoint vertices.
    Points(ProjectedGeoPoints),
    /// LineString / MultiLineString lines and Polygon / MultiPolygon ring
    /// outlines as clipped two-point segments (fill topology is #49).
    Outlines(ProjectedGeoLines),
}

/// A derived, rebuildable projection of a [`GeoColumn`] with its cache key.
#[derive(Debug, Clone, PartialEq)]
pub struct ProjectedGeoColumn {
    pub key: GeoDerivedKey,
    pub geometry: ProjectedGeoGeometry,
    pub polygons: Option<ProjectedGeoPolygons>,
    pub visible_feature_ids: Vec<u64>,
    pub visible_bounds: Option<[f64; 4]>,
}

impl GeoViewport {
    /// Construct and validate a viewport. Rejects non-finite values, empty
    /// size, out-of-range pitch/zoom, and CRS-out-of-bounds centers.
    #[expect(
        clippy::too_many_arguments,
        reason = "explicit camera fields match the #48 GeoViewport contract"
    )]
    pub fn new(
        crs: GeoCrs,
        center_x: f64,
        center_y: f64,
        zoom: f64,
        width: f64,
        height: f64,
        bearing_deg: f64,
        pitch_deg: f64,
        world_wrap: bool,
    ) -> Result<Self, GeoError> {
        let vp = Self {
            crs,
            center_x,
            center_y,
            zoom,
            width,
            height,
            bearing_deg: normalize_bearing(bearing_deg),
            pitch_deg,
            world_wrap,
        };
        vp.validate()?;
        Ok(vp)
    }

    /// Validate every field without allocating.
    pub fn validate(self) -> Result<(), GeoError> {
        for value in [
            self.center_x,
            self.center_y,
            self.zoom,
            self.width,
            self.height,
            self.bearing_deg,
            self.pitch_deg,
        ] {
            if !value.is_finite() {
                return Err(GeoError::NonFiniteCoordinate);
            }
        }
        if self.width <= 0.0
            || self.height <= 0.0
            || !(self.width as f32).is_finite()
            || !(self.height as f32).is_finite()
            || self.width as f32 == 0.0
            || self.height as f32 == 0.0
        {
            return Err(GeoError::InvalidArgument);
        }
        if !(0.0..=24.0).contains(&self.zoom) {
            return Err(GeoError::InvalidArgument);
        }
        if !(-60.0..=60.0).contains(&self.pitch_deg) {
            return Err(GeoError::InvalidArgument);
        }
        match self.crs {
            GeoCrs::Epsg4326 => {
                if self.center_x.abs() > 180.0 || self.center_y.abs() > 90.0 {
                    return Err(GeoError::CoordinateOutOfRange);
                }
            }
            GeoCrs::Epsg3857 => {
                if self.center_x.abs() > WEB_MERCATOR_MAX || self.center_y.abs() > WEB_MERCATOR_MAX
                {
                    return Err(GeoError::CoordinateOutOfRange);
                }
            }
        }
        Ok(())
    }

    /// Camera center as longitude/latitude degrees (clamped for mercator).
    #[must_use]
    pub fn center_lonlat(&self) -> (f64, f64) {
        match self.crs {
            GeoCrs::Epsg4326 => (self.center_x, clamp_lat(self.center_y)),
            GeoCrs::Epsg3857 => mercator_to_lonlat(self.center_x, self.center_y),
        }
    }

    /// Camera center as Web Mercator metres.
    #[must_use]
    pub fn center_mercator(&self) -> (f64, f64) {
        match self.crs {
            GeoCrs::Epsg4326 => lonlat_to_mercator(self.center_x, self.center_y),
            GeoCrs::Epsg3857 => (
                self.center_x.clamp(-WEB_MERCATOR_MAX, WEB_MERCATOR_MAX),
                self.center_y.clamp(-WEB_MERCATOR_MAX, WEB_MERCATOR_MAX),
            ),
        }
    }

    /// CSS pixels covered by the full mercator world at the current zoom.
    #[must_use]
    pub fn world_size_px(&self) -> f64 {
        TILE_SIZE * (2.0_f64).powf(self.zoom)
    }

    /// Metres → CSS pixels scale at the current zoom.
    #[must_use]
    pub fn metres_per_pixel(&self) -> f64 {
        (2.0 * WEB_MERCATOR_MAX) / self.world_size_px()
    }

    /// Project a source-CRS coordinate to CSS pixel space (origin top-left).
    /// A ground point behind the near plane receives a finite offscreen
    /// sentinel, and contributes no visible feature membership.
    pub fn project(&self, x: f64, y: f64) -> Result<(f64, f64), GeoError> {
        self.validate()?;
        self.project_validated(x, y)
    }

    fn project_validated(&self, x: f64, y: f64) -> Result<(f64, f64), GeoError> {
        if !x.is_finite() || !y.is_finite() {
            return Err(GeoError::NonFiniteCoordinate);
        }
        let (mx, my) = match self.crs {
            GeoCrs::Epsg4326 => {
                if x.abs() > 180.0 || y.abs() > 90.0 {
                    return Err(GeoError::CoordinateOutOfRange);
                }
                lonlat_to_mercator(x, y)
            }
            GeoCrs::Epsg3857 => {
                if x.abs() > WEB_MERCATOR_MAX || y.abs() > WEB_MERCATOR_MAX {
                    return Err(GeoError::CoordinateOutOfRange);
                }
                (x, y)
            }
        };
        Ok(self.mercator_to_screen(mx, my))
    }

    /// Inverse of [`Self::project`] for front-facing ground coordinates.
    /// Rays on or above the ground horizon fail rather than emitting infinity.
    pub fn unproject(&self, screen_x: f64, screen_y: f64) -> Result<(f64, f64), GeoError> {
        self.validate()?;
        if !screen_x.is_finite() || !screen_y.is_finite() {
            return Err(GeoError::NonFiniteCoordinate);
        }
        let (mx, my) = self.screen_to_mercator(screen_x, screen_y)?;
        match self.crs {
            GeoCrs::Epsg4326 => {
                let mx = if self.world_wrap {
                    let world_m = 2.0 * WEB_MERCATOR_MAX;
                    (mx + WEB_MERCATOR_MAX).rem_euclid(world_m) - WEB_MERCATOR_MAX
                } else {
                    mx
                };
                Ok(mercator_to_lonlat(mx, my))
            }
            GeoCrs::Epsg3857 => Ok((
                mx.clamp(-WEB_MERCATOR_MAX, WEB_MERCATOR_MAX),
                my.clamp(-WEB_MERCATOR_MAX, WEB_MERCATOR_MAX),
            )),
        }
    }

    /// Raw Mercator ground ray for Rust tile sampling. Unlike the public
    /// authoring inverse, this retains rays outside the bounded world.
    pub(crate) fn unproject_mercator_ray(&self, x: f64, y: f64) -> Result<ScreenPoint, GeoError> {
        self.validate()?;
        if !x.is_finite() || !y.is_finite() {
            return Err(GeoError::NonFiniteCoordinate);
        }
        self.screen_to_mercator(x, y)
    }

    /// Project source coordinates to offset-encoded f32 screen pixels.
    ///
    /// Returns interleaved `[sx0,sy0,…]` plus the f64 encode origin used so
    /// deep zoom stays precise (§4/§16). Non-finite inputs fail before output.
    pub fn project_offset_f32(&self, xy: &[f64]) -> Result<(Vec<f32>, f64, f64), GeoError> {
        self.validate()?;
        if !xy.len().is_multiple_of(2) {
            return Err(GeoError::InvalidArgument);
        }
        let mut out = Vec::with_capacity(xy.len());
        // Recenter on the visible camera, never on an arbitrary offscreen
        // source vertex whose magnitude would erase visible f32 detail.
        let origin_x = self.width * 0.5;
        let origin_y = self.height * 0.5;
        for pair in xy.chunks_exact(2) {
            let (sx, sy) = self.project_validated(pair[0], pair[1])?;
            let (x, y) = ((sx - origin_x) as f32, (sy - origin_y) as f32);
            if !x.is_finite() || !y.is_finite() {
                return Err(GeoError::ResourceLimit);
            }
            out.push(x);
            out.push(y);
        }
        Ok((out, origin_x, origin_y))
    }

    /// Split, project, and clip line features while preserving source IDs.
    ///
    /// `offsets` uses the canonical Arrow-style contract: it starts at zero,
    /// ends at half the interleaved coordinate-buffer length, and has one more
    /// entry than `feature_ids`.
    /// EPSG:4326 segments crossing ±180° are split at the dateline before
    /// projection when world wrapping is enabled. The returned ranges contain
    /// only finite points inside the CSS viewport; invisible features produce
    /// no range and no ID.
    pub fn project_line_features(
        &self,
        xy: &[f64],
        offsets: &[u32],
        feature_ids: &[u64],
    ) -> Result<ProjectedGeoLines, GeoError> {
        self.validate()?;
        if !xy.len().is_multiple_of(2)
            || offsets.len() != feature_ids.len() + 1
            || offsets.first() != Some(&0)
            || offsets.last().copied().map(|v| v as usize) != Some(xy.len() / 2)
            || offsets.windows(2).any(|pair| pair[0] > pair[1])
        {
            return Err(GeoError::OffsetMismatch);
        }
        let limits = GeoLimits::default();
        if feature_ids.len() > limits.max_features
            || xy.len() / 2 > limits.max_vertices
            || xy.len().saturating_mul(size_of::<f64>()) > limits.max_bytes
        {
            return Err(GeoError::ResourceLimit);
        }

        // Validate the complete descriptor before doing projection work or
        // allocating derived output. Callers get one atomic failure even when
        // a malformed feature appears late in a large column.
        validate_line_coordinates(self.crs, xy)?;
        let origin_x = self.width * 0.5;
        let origin_y = self.height * 0.5;
        let mut out = ProjectedGeoLines {
            xy: Vec::new(),
            offsets: vec![0],
            feature_ids: Vec::new(),
            origin_x,
            origin_y,
        };

        for (feature_index, &feature_id) in feature_ids.iter().enumerate() {
            let start = offsets[feature_index] as usize;
            let end = offsets[feature_index + 1] as usize;
            if end - start < 2 {
                continue;
            }
            let points = &xy[start * 2..end * 2];
            let mut prior_source_end_lon = None;
            for index in 0..points.len() / 2 - 1 {
                let (x0, y0) = (points[index * 2], points[index * 2 + 1]);
                let (x1, y1) = (points[(index + 1) * 2], points[(index + 1) * 2 + 1]);
                let (segments, count) =
                    split_line_segment(self.crs, self.world_wrap, x0, y0, x1, y1);
                for (split_index, segment) in segments.into_iter().take(count).enumerate() {
                    // Preserve continuity between source segments, but not
                    // across the paired screen edges introduced by a dateline
                    // split. Each half selects the visible wrapped-world copy.
                    let preferred_start = if split_index == 0 {
                        prior_source_end_lon
                    } else {
                        None
                    };
                    let ((a, b), source_end_lon) =
                        self.project_line_segment(segment, preferred_start)?;
                    prior_source_end_lon = source_end_lon;
                    let Some((a, b)) = a.zip(b) else {
                        continue;
                    };
                    let next_bytes = (out.xy.len() + 4) * size_of::<f32>()
                        + (out.feature_ids.len() + 1) * size_of::<u64>()
                        + (out.offsets.len() + 1) * size_of::<u32>();
                    if next_bytes > limits.max_bytes {
                        return Err(GeoError::ResourceLimit);
                    }
                    for (x, y) in [a, b] {
                        out.xy.push((x - origin_x) as f32);
                        out.xy.push((y - origin_y) as f32);
                    }
                    out.feature_ids.push(feature_id);
                    out.offsets.push((out.xy.len() / 2) as u32);
                }
            }
        }
        Ok(out)
    }

    /// Project a retained [`GeoColumn`] into offset-encoded f32 scene inputs.
    ///
    /// The result is a rebuildable cache keyed by [`GeoDerivedKey`]; the
    /// canonical f64 column is never modified. Point kinds emit one vertex
    /// per retained point; line kinds emit each line part and polygon kinds
    /// emit each ring (exterior and holes) as closed outlines through
    /// [`Self::project_line_features`], so null features are absent, source
    /// feature IDs are preserved, and no NaN reaches the output. A column
    /// whose CRS differs from the camera is rejected (`InvalidArgument`);
    /// an invalid camera fails before any output is built.
    pub fn project_column(&self, col: &GeoColumn) -> Result<ProjectedGeoColumn, GeoError> {
        let rebuild = self.rebuild_key()?;
        if col.crs() != self.crs {
            return Err(GeoError::InvalidArgument);
        }
        if matches!(
            col.geometry(),
            GeoGeometry::Polygon | GeoGeometry::MultiPolygon
        ) {
            polygon_peak_admission(col)?;
        }
        let key = GeoDerivedKey {
            rebuild,
            metadata_digest: col.metadata_digest(),
        };
        let geometry = match col.geometry() {
            GeoGeometry::Point | GeoGeometry::MultiPoint => {
                let feature_ids = point_vertex_feature_ids(col);
                let (xy, origin_x, origin_y) = self.project_offset_f32(col.xy())?;
                ProjectedGeoGeometry::Points(ProjectedGeoPoints {
                    xy,
                    feature_ids,
                    origin_x,
                    origin_y,
                })
            }
            _ => {
                let (offsets, feature_ids) = outline_parts(col);
                ProjectedGeoGeometry::Outlines(self.project_line_features(
                    col.xy(),
                    &offsets,
                    &feature_ids,
                )?)
            }
        };
        let polygons = if matches!(
            col.geometry(),
            GeoGeometry::Polygon | GeoGeometry::MultiPolygon
        ) {
            Some(self.project_polygons(col)?)
        } else {
            None
        };
        let mut seen = BTreeSet::new();
        let mut visible_feature_ids = Vec::new();
        let mut visible_bounds = None;
        let mut include = |id: u64, x: f64, y: f64| {
            if seen.insert(id) {
                visible_feature_ids.push(id);
            }
            let bounds = visible_bounds.get_or_insert([x, y, x, y]);
            bounds[0] = bounds[0].min(x);
            bounds[1] = bounds[1].min(y);
            bounds[2] = bounds[2].max(x);
            bounds[3] = bounds[3].max(y);
        };
        if let Some(poly) = &polygons {
            for (i, &id) in poly.feature_ids.iter().enumerate() {
                for ring in poly.polygon_offsets[i] as usize..poly.polygon_offsets[i + 1] as usize {
                    for vertex in
                        poly.ring_offsets[ring] as usize..poly.ring_offsets[ring + 1] as usize
                    {
                        include(
                            id,
                            poly.origin_x + poly.xy[2 * vertex] as f64,
                            poly.origin_y + poly.xy[2 * vertex + 1] as f64,
                        );
                    }
                }
            }
        } else {
            match &geometry {
                ProjectedGeoGeometry::Points(points) => {
                    for (i, &id) in points.feature_ids.iter().enumerate() {
                        let (x, y) = (
                            points.origin_x + points.xy[2 * i] as f64,
                            points.origin_y + points.xy[2 * i + 1] as f64,
                        );
                        if (0.0..=self.width).contains(&x) && (0.0..=self.height).contains(&y) {
                            include(id, x, y);
                        }
                    }
                }
                ProjectedGeoGeometry::Outlines(lines) => {
                    for (i, &id) in lines.feature_ids.iter().enumerate() {
                        for vertex in lines.offsets[i] as usize..lines.offsets[i + 1] as usize {
                            include(
                                id,
                                lines.origin_x + lines.xy[2 * vertex] as f64,
                                lines.origin_y + lines.xy[2 * vertex + 1] as f64,
                            );
                        }
                    }
                }
            }
        }
        Ok(ProjectedGeoColumn {
            key,
            geometry,
            polygons,
            visible_feature_ids,
            visible_bounds,
        })
    }

    /// Fit the camera to an axis-aligned source-CRS bounding box.
    ///
    /// `padding_px` is applied on every side. When `world_wrap` is set and the
    /// CRS is lon/lat, the shorter longitudinal span across the antimeridian
    /// is preferred.
    pub fn fit_bounds(
        &mut self,
        min_x: f64,
        min_y: f64,
        max_x: f64,
        max_y: f64,
        padding_px: f64,
    ) -> Result<(), GeoError> {
        self.validate()?;
        for value in [min_x, min_y, max_x, max_y, padding_px] {
            if !value.is_finite() {
                return Err(GeoError::NonFiniteCoordinate);
            }
        }
        if padding_px < 0.0 || self.width <= 2.0 * padding_px || self.height <= 2.0 * padding_px {
            return Err(GeoError::InvalidArgument);
        }

        let (min_mx, min_my, max_mx, max_my) = match self.crs {
            GeoCrs::Epsg4326 => {
                if min_x.abs() > 180.0
                    || max_x.abs() > 180.0
                    || min_y.abs() > 90.0
                    || max_y.abs() > 90.0
                {
                    return Err(GeoError::CoordinateOutOfRange);
                }
                let (west, east) = if self.world_wrap {
                    wrapped_lon_span(min_x, max_x)
                } else {
                    if max_x < min_x {
                        return Err(GeoError::InvalidArgument);
                    }
                    (min_x, max_x)
                };
                if max_y < min_y {
                    return Err(GeoError::InvalidArgument);
                }
                // `east` may intentionally exceed 180 degrees so a
                // dateline-crossing interval remains the short interval.
                // The general converter normalizes longitude and would turn
                // 170..190 into the incorrect 340-degree span here.
                let x0 = EARTH_RADIUS_M * west.to_radians();
                let x1 = EARTH_RADIUS_M * east.to_radians();
                let (_, y0) = lonlat_to_mercator(0.0, min_y);
                let (_, y1) = lonlat_to_mercator(0.0, max_y);
                (x0.min(x1), y0.min(y1), x0.max(x1), y0.max(y1))
            }
            GeoCrs::Epsg3857 => {
                if [min_x, max_x, min_y, max_y]
                    .into_iter()
                    .any(|v| v.abs() > WEB_MERCATOR_MAX)
                {
                    return Err(GeoError::CoordinateOutOfRange);
                }
                if max_x < min_x || max_y < min_y {
                    return Err(GeoError::InvalidArgument);
                }
                (min_x, min_y, max_x, max_y)
            }
        };

        let span_x = (max_mx - min_mx).max(1e-9);
        let span_y = (max_my - min_my).max(1e-9);
        let avail_w = self.width - 2.0 * padding_px;
        let avail_h = self.height - 2.0 * padding_px;
        let zoom_x = (avail_w * (2.0 * WEB_MERCATOR_MAX) / (span_x * TILE_SIZE)).log2();
        let zoom_y = (avail_h * (2.0 * WEB_MERCATOR_MAX) / (span_y * TILE_SIZE)).log2();
        let mut next = *self;
        next.zoom = zoom_x.min(zoom_y).clamp(0.0, 24.0);

        let mid_mx = 0.5 * (min_mx + max_mx);
        let mid_my = 0.5 * (min_my + max_my);
        match self.crs {
            GeoCrs::Epsg4326 => {
                let (lon, lat) = mercator_to_lonlat(mid_mx, mid_my);
                next.center_x = normalize_lon(lon);
                next.center_y = lat;
            }
            GeoCrs::Epsg3857 => {
                next.center_x = mid_mx;
                next.center_y = mid_my;
            }
        }
        next.bearing_deg = 0.0;
        next.validate()?;
        if next.pitch_deg != 0.0 {
            let fits = |camera: &Self| {
                [
                    (min_mx, min_my),
                    (max_mx, min_my),
                    (max_mx, max_my),
                    (min_mx, max_my),
                ]
                .into_iter()
                .all(|(x, y)| {
                    let (x, y) = camera.ground_to_screen(camera.ground_from_mercator(x, y, false));
                    x >= padding_px
                        && x <= camera.width - padding_px
                        && y >= padding_px
                        && y <= camera.height - padding_px
                })
            };
            if !fits(&next) {
                let mut low = 0.0;
                let mut high = next.zoom;
                next.zoom = low;
                if !fits(&next) {
                    return Err(GeoError::InvalidArgument);
                }
                for _ in 0..48 {
                    let middle = 0.5 * (low + high);
                    next.zoom = middle;
                    if fits(&next) {
                        low = middle;
                    } else {
                        high = middle;
                    }
                }
                next.zoom = low;
            }
        }
        *self = next;
        Ok(())
    }

    /// Pan so `center` becomes the camera center (source CRS units).
    pub fn set_center(&mut self, x: f64, y: f64) -> Result<(), GeoError> {
        let mut next = *self;
        next.center_x = x;
        next.center_y = y;
        if next.crs == GeoCrs::Epsg4326 && next.world_wrap {
            next.center_x = normalize_lon(next.center_x);
        }
        next.validate()?;
        *self = next;
        Ok(())
    }

    /// Set MapLibre-style zoom.
    pub fn set_zoom(&mut self, zoom: f64) -> Result<(), GeoError> {
        let mut next = *self;
        next.zoom = zoom;
        next.validate()?;
        *self = next;
        Ok(())
    }

    /// Resize the CSS pixel viewport.
    pub fn resize(&mut self, width: f64, height: f64) -> Result<(), GeoError> {
        let mut next = *self;
        next.width = width;
        next.height = height;
        next.validate()?;
        *self = next;
        Ok(())
    }

    /// Set the clockwise bearing, normalized to `(-180, 180]` degrees.
    ///
    /// The update is transactional: invalid input leaves the camera unchanged.
    pub fn set_bearing(&mut self, bearing_deg: f64) -> Result<(), GeoError> {
        if !bearing_deg.is_finite() {
            return Err(GeoError::NonFiniteCoordinate);
        }
        let mut next = *self;
        next.bearing_deg = normalize_bearing(bearing_deg);
        next.validate()?;
        *self = next;
        Ok(())
    }

    /// Set perspective pitch in the certified range `[-60, 60]` degrees.
    pub fn set_pitch(&mut self, pitch_deg: f64) -> Result<(), GeoError> {
        let mut next = *self;
        next.pitch_deg = pitch_deg;
        next.validate()?;
        *self = next;
        Ok(())
    }

    /// Move the camera centre by a screen-space CSS-pixel displacement.
    ///
    /// Positive X moves the centre toward the current screen-right direction;
    /// positive Y moves it toward screen-bottom. Bearing is therefore applied
    /// exactly as it is for project/unproject. Wrapped longitude is normalized;
    /// a non-wrapped camera and both Mercator axes stop at the certified world
    /// bounds. The transition is atomic and allocation-free.
    pub fn pan_by_pixels(&mut self, delta_x: f64, delta_y: f64) -> Result<(), GeoError> {
        self.validate()?;
        if !delta_x.is_finite() || !delta_y.is_finite() {
            return Err(GeoError::NonFiniteCoordinate);
        }
        if delta_x == 0.0 && delta_y == 0.0 {
            return Ok(());
        }
        let (mut mx, my) =
            self.screen_to_mercator(self.width * 0.5 + delta_x, self.height * 0.5 + delta_y)?;
        let my = my.clamp(-WEB_MERCATOR_MAX, WEB_MERCATOR_MAX);
        if self.crs == GeoCrs::Epsg3857 || !self.world_wrap {
            mx = mx.clamp(-WEB_MERCATOR_MAX, WEB_MERCATOR_MAX);
        } else {
            let world_m = 2.0 * WEB_MERCATOR_MAX;
            mx = (mx + WEB_MERCATOR_MAX).rem_euclid(world_m) - WEB_MERCATOR_MAX;
        }

        let mut next = *self;
        match self.crs {
            GeoCrs::Epsg4326 => {
                let (lon, lat) = mercator_to_lonlat(mx, my);
                // `mercator_to_lonlat` canonicalizes -180° to +180°. Preserve
                // the distinct west stop when this camera cannot wrap.
                next.center_x = if self.world_wrap {
                    lon
                } else {
                    (mx / EARTH_RADIUS_M).to_degrees().clamp(-180.0, 180.0)
                };
                next.center_y = lat;
            }
            GeoCrs::Epsg3857 => {
                next.center_x = mx;
                next.center_y = my;
            }
        }
        next.validate()?;
        *self = next;
        Ok(())
    }

    /// Return exact rebuild identity for the complete frozen camera state.
    ///
    /// Restored/public-field cameras are revalidated before identity is
    /// published, so an invalid camera cannot masquerade as a reusable cache.
    pub fn rebuild_key(&self) -> Result<GeoViewportRebuildKey, GeoError> {
        self.validate()?;
        let center_x = if self.crs == GeoCrs::Epsg4326 && self.world_wrap {
            normalize_lon(self.center_x)
        } else {
            self.center_x
        };
        Ok(GeoViewportRebuildKey {
            crs: self.crs,
            center_x_bits: canonical_f64_bits(center_x),
            center_y_bits: canonical_f64_bits(self.center_y),
            zoom_bits: canonical_f64_bits(self.zoom),
            width_bits: canonical_f64_bits(self.width),
            height_bits: canonical_f64_bits(self.height),
            bearing_deg_bits: canonical_f64_bits(normalize_bearing(self.bearing_deg)),
            pitch_deg_bits: canonical_f64_bits(self.pitch_deg),
            world_wrap: self.world_wrap,
        })
    }

    fn project_polygons(&self, col: &GeoColumn) -> Result<ProjectedGeoPolygons, GeoError> {
        polygon_peak_admission(col)?;
        let mut association_work = 4_000_000usize;
        let mut out = ProjectedGeoPolygons {
            xy: Vec::new(),
            ring_offsets: vec![0],
            polygon_offsets: vec![0],
            feature_ids: Vec::new(),
            ring_is_hole: Vec::new(),
            origin_x: self.width * 0.5,
            origin_y: self.height * 0.5,
        };
        let ring_vertices = if col.geometry() == GeoGeometry::Polygon {
            col.offsets1()
        } else {
            col.offsets2()
        };
        let polygon_rings = if col.geometry() == GeoGeometry::Polygon {
            col.offsets0()
        } else {
            col.offsets1()
        };
        for (feature, &id) in col.feature_ids().iter().enumerate() {
            let polygons = if col.geometry() == GeoGeometry::Polygon {
                feature..feature + 1
            } else {
                col.offsets0()[feature] as usize..col.offsets0()[feature + 1] as usize
            };
            for polygon in polygons {
                let range = polygon_rings[polygon] as usize..polygon_rings[polygon + 1] as usize;
                if range.is_empty() {
                    continue;
                }
                let mut rings = Vec::with_capacity(range.len());
                let mut shell_anchor = 0.0;
                for (ordinal, ring) in range.enumerate() {
                    let start = ring_vertices[ring] as usize;
                    let end = ring_vertices[ring + 1] as usize;
                    let source = &col.xy()[start * 2..end * 2];
                    let period = if self.crs == GeoCrs::Epsg4326 {
                        360.0
                    } else {
                        2.0 * WEB_MERCATOR_MAX
                    };
                    let cache = if self.world_wrap {
                        Some(crate::geo::unwrap_ring_xy(
                            source,
                            period,
                            if ordinal == 0 {
                                None
                            } else {
                                Some(shell_anchor)
                            },
                        )?)
                    } else {
                        None
                    };
                    let source = cache.as_deref().unwrap_or(source);
                    let min_x = source
                        .chunks_exact(2)
                        .map(|p| p[0])
                        .fold(f64::INFINITY, f64::min);
                    let max_x = source
                        .chunks_exact(2)
                        .map(|p| p[0])
                        .fold(f64::NEG_INFINITY, f64::max);
                    if ordinal == 0 {
                        shell_anchor = 0.5 * (min_x + max_x);
                    }
                    let coordinates = source
                        .chunks_exact(2)
                        .map(|pair| {
                            if self.crs == GeoCrs::Epsg4326 {
                                (
                                    EARTH_RADIUS_M * pair[0].to_radians(),
                                    lonlat_to_mercator(0.0, pair[1]).1,
                                )
                            } else {
                                (pair[0], pair[1])
                            }
                        })
                        .collect::<Vec<ScreenPoint>>();
                    rings.push(coordinates);
                }
                let shell = &rings[0];
                let min_mx = shell.iter().map(|p| p.0).fold(f64::INFINITY, f64::min);
                let max_mx = shell.iter().map(|p| p.0).fold(f64::NEG_INFINITY, f64::max);
                let first = if self.world_wrap {
                    ((min_mx + WEB_MERCATOR_MAX) / (2.0 * WEB_MERCATOR_MAX)).floor() as i64
                } else {
                    0
                };
                let last = if self.world_wrap {
                    ((max_mx + WEB_MERCATOR_MAX) / (2.0 * WEB_MERCATOR_MAX)).floor() as i64
                } else {
                    0
                };
                if last - first > 2 {
                    return Err(GeoError::ResourceLimit);
                }
                for strip in first..=last {
                    let midpoint = (min_mx + max_mx) * 0.5;
                    let (cx, _) = self.center_mercator();
                    let world = 2.0 * WEB_MERCATOR_MAX;
                    let reference = if self.world_wrap {
                        let west = -WEB_MERCATOR_MAX + strip as f64 * world;
                        0.5 * (min_mx.max(west) + max_mx.min(west + world))
                    } else {
                        midpoint
                    };
                    let shift = if self.world_wrap {
                        ((cx - reference) / world).round() * world
                    } else {
                        0.0
                    };
                    let mut region = self.ground_footprint();
                    if self.world_wrap {
                        let west = -WEB_MERCATOR_MAX + strip as f64 * world + shift;
                        let east = west + world;
                        let scale = self.metres_per_pixel();
                        let (sin, cos) = normalize_bearing(self.bearing_deg).to_radians().sin_cos();
                        region =
                            clip_convex(&region, HalfPlane(scale * cos, -scale * sin, cx - west));
                        region =
                            clip_convex(&region, HalfPlane(-scale * cos, scale * sin, east - cx));
                    }
                    if region.len() < 3 {
                        continue;
                    }
                    let ground_rings: Vec<_> = rings
                        .iter()
                        .map(|ring| {
                            ring.iter()
                                .map(|&(x, y)| self.ground_from_mercator(x + shift, y, false))
                                .collect::<Vec<_>>()
                        })
                        .collect();
                    let fragments = clip_ring_components(&ground_rings[0], &region)?;
                    let mut holes = Vec::new();
                    for ring in ground_rings.iter().skip(1) {
                        holes.extend(clip_ring_components(ring, &region)?);
                    }
                    for shell in fragments {
                        let shell_area = signed_area(&shell).abs();
                        let mut assigned = Vec::new();
                        let mut hole_area = 0.0;
                        for hole in &holes {
                            association_work = association_work
                                .checked_sub(shell.len().saturating_mul(hole.len()))
                                .ok_or(GeoError::ResourceLimit)?;
                            // A clipped hole may touch the clipping boundary, so use
                            // any contained vertex, including the clipping boundary.
                            if hole.iter().any(|&p| ring_contains(&shell, p)) {
                                hole_area += signed_area(hole).abs();
                                assigned.push(hole);
                            }
                        }
                        if shell_area - hole_area <= 1e-12 {
                            continue;
                        }
                        for (role, ring) in std::iter::once((0, &shell))
                            .chain(assigned.into_iter().map(|ring| (1, ring)))
                        {
                            for &ground in ring {
                                let (x, y) = self.ground_to_screen(ground);
                                let (x, y) = ((x - out.origin_x) as f32, (y - out.origin_y) as f32);
                                if !x.is_finite() || !y.is_finite() {
                                    return Err(GeoError::ResourceLimit);
                                }
                                out.xy.extend([x, y]);
                            }
                            out.ring_offsets.push(
                                u32::try_from(out.xy.len() / 2)
                                    .map_err(|_| GeoError::ResourceLimit)?,
                            );
                            out.ring_is_hole.push(role);
                        }
                        out.feature_ids.push(id);
                        out.polygon_offsets.push(out.ring_is_hole.len() as u32);
                    }
                }
            }
        }
        Ok(out)
    }

    fn ground_footprint(&self) -> Vec<ScreenPoint> {
        let d = self.camera_distance();
        let (sin, cos) = self.pitch_deg.to_radians().sin_cos();
        [
            (0.0, 0.0),
            (self.width, 0.0),
            (self.width, self.height),
            (0.0, self.height),
        ]
        .into_iter()
        .map(|(x, y)| {
            let sy = y - self.height * 0.5;
            let gy = sy * d / (d * cos + sy * sin);
            ((x - self.width * 0.5) * (d - gy * sin) / d, gy)
        })
        .collect()
    }

    /// Default Mercator camera distance in CSS-pixel world units.
    pub fn camera_distance(&self) -> f64 {
        self.height * 1.5
    }

    /// Near/far ground-plane depth limits. The far plane encloses the top
    /// ground corner with the reference camera's 1% precision margin.
    pub fn depth_range(&self) -> (f64, f64) {
        let distance = self.camera_distance();
        let pitch = self.pitch_deg.abs().to_radians();
        let far = distance * pitch.cos() / (pitch.cos() - pitch.sin() / 3.0) * 1.01;
        (self.height / 50.0, far)
    }

    fn ground_from_mercator(&self, mx: f64, my: f64, wrap: bool) -> ScreenPoint {
        let (cx, cy) = self.center_mercator();
        let mut dx = mx - cx;
        if wrap && self.world_wrap {
            let world = 2.0 * WEB_MERCATOR_MAX;
            dx -= (dx / world).round() * world;
        }
        let scale = 1.0 / self.metres_per_pixel();
        let (x, y) = (dx * scale, (cy - my) * scale);
        let (sin, cos) = (-normalize_bearing(self.bearing_deg))
            .to_radians()
            .sin_cos();
        (x * cos - y * sin, x * sin + y * cos)
    }

    fn ground_to_screen(&self, ground: ScreenPoint) -> ScreenPoint {
        let (x, y) = ground;
        let distance = self.camera_distance();
        let (sin, cos) = self.pitch_deg.to_radians().sin_cos();
        let depth = distance - y * sin;
        if depth <= self.depth_range().0 {
            // A non-visible point gets a finite offscreen sentinel. Frustum
            // segment clipping always occurs before perspective division.
            let (dx, dy) = (x, if x == 0.0 && y == 0.0 { 1.0 } else { y * cos });
            let factor = (self.width * 1.5 / dx.abs()).min(self.height * 1.5 / dy.abs());
            return (
                self.width * 0.5 + dx * factor,
                self.height * 0.5 + dy * factor,
            );
        }
        (
            self.width * 0.5 + distance * x / depth,
            self.height * 0.5 + distance * y * cos / depth,
        )
    }

    fn mercator_to_screen(&self, mx: f64, my: f64) -> ScreenPoint {
        self.ground_to_screen(self.ground_from_mercator(mx, my, true))
    }

    fn screen_to_mercator(&self, screen_x: f64, screen_y: f64) -> Result<ScreenPoint, GeoError> {
        let distance = self.camera_distance();
        let (sin, cos) = self.pitch_deg.to_radians().sin_cos();
        let sy = screen_y - self.height * 0.5;
        let denominator = distance * cos + sy * sin;
        if denominator <= 0.0 || !denominator.is_finite() {
            return Err(GeoError::InvalidArgument);
        }
        let y = sy * distance / denominator;
        let x = (screen_x - self.width * 0.5) * (distance - y * sin) / distance;
        let (sin_b, cos_b) = normalize_bearing(self.bearing_deg).to_radians().sin_cos();
        let dx = x * cos_b - y * sin_b;
        let dy = x * sin_b + y * cos_b;
        let scale = self.metres_per_pixel();
        let (cx, cy) = self.center_mercator();
        let result = (cx + dx * scale, cy - dy * scale);
        if !result.0.is_finite() || !result.1.is_finite() {
            return Err(GeoError::InvalidArgument);
        }
        Ok(result)
    }

    /// Source-CRS bounds of the ground footprint, with an unwrapped longitude
    /// interval for dateline-spanning EPSG:4326 cameras.
    pub fn bounds(&self) -> Result<[f64; 4], GeoError> {
        self.validate()?;
        let mut bounds = [
            f64::INFINITY,
            f64::INFINITY,
            f64::NEG_INFINITY,
            f64::NEG_INFINITY,
        ];
        for (x, y) in [
            (0.0, 0.0),
            (self.width, 0.0),
            (self.width, self.height),
            (0.0, self.height),
        ] {
            let (mx, my) = self.screen_to_mercator(x, y)?;
            let (x, y) = match self.crs {
                GeoCrs::Epsg4326 => (
                    (mx / EARTH_RADIUS_M).to_degrees(),
                    mercator_to_lonlat(mx, my).1,
                ),
                GeoCrs::Epsg3857 => (mx, my.clamp(-WEB_MERCATOR_MAX, WEB_MERCATOR_MAX)),
            };
            bounds[0] = bounds[0].min(x);
            bounds[1] = bounds[1].min(y);
            bounds[2] = bounds[2].max(x);
            bounds[3] = bounds[3].max(y);
        }
        Ok(bounds)
    }

    /// Conservative Mercator envelope for authenticated point-index pruning.
    /// Failed/horizon inverse returns None: readers retain all candidates
    /// rather than infer a tighter box. Periodic cell selection handles wrap.
    pub fn point_index_bounds(&self) -> Result<Option<[f64; 4]>, GeoError> {
        self.validate()?;
        let mut bounds = [
            f64::INFINITY,
            f64::INFINITY,
            f64::NEG_INFINITY,
            f64::NEG_INFINITY,
        ];
        for (x, y) in [
            (0., 0.),
            (self.width, 0.),
            (self.width, self.height),
            (0., self.height),
        ] {
            let Ok((mx, my)) = self.screen_to_mercator(x, y) else {
                return Ok(None);
            };
            bounds[0] = bounds[0].min(mx);
            bounds[1] = bounds[1].min(my);
            bounds[2] = bounds[2].max(mx);
            bounds[3] = bounds[3].max(my);
        }
        if !bounds.iter().all(|n| n.is_finite()) {
            return Ok(None);
        }
        // Small outward error allowance prevents rounding at cell boundaries.
        let pad = 1e-6
            + (bounds[2] - bounds[0])
                .abs()
                .max((bounds[3] - bounds[1]).abs())
                * 1e-12;
        bounds[0] -= pad;
        bounds[1] -= pad;
        bounds[2] += pad;
        bounds[3] += pad;
        Ok(Some(bounds))
    }

    // Linear half-planes in camera-relative ground pixels, before division.
    fn ground_planes(&self) -> [HalfPlane; 6] {
        let distance = self.camera_distance();
        let (sin, cos) = self.pitch_deg.to_radians().sin_cos();
        let (hw, hh) = (self.width * 0.5, self.height * 0.5);
        let (near, far) = self.depth_range();
        [
            HalfPlane(distance, -hw * sin, hw * distance),
            HalfPlane(-distance, -hw * sin, hw * distance),
            HalfPlane(0.0, distance * cos - hh * sin, hh * distance),
            HalfPlane(0.0, -distance * cos - hh * sin, hh * distance),
            HalfPlane(0.0, -sin, distance - near),
            HalfPlane(0.0, sin, far - distance),
        ]
    }

    /// Project both endpoints into one coherent wrapped-world copy. Projecting
    /// them independently makes exactly +180 degrees jump to the opposite
    /// screen edge while a nearby +170 degree point remains on the right.
    fn project_line_segment(
        &self,
        segment: [f64; 4],
        preferred_start: Option<f64>,
    ) -> Result<((Option<ScreenPoint>, Option<ScreenPoint>), Option<f64>), GeoError> {
        let period = match self.crs {
            GeoCrs::Epsg4326 => 360.0,
            GeoCrs::Epsg3857 => 2.0 * WEB_MERCATOR_MAX,
        };
        let shift = if self.world_wrap {
            preferred_start.map_or_else(
                || ((self.center_x - 0.5 * (segment[0] + segment[2])) / period).round(),
                |prior| ((prior - segment[0]) / period).round(),
            ) * period
        } else {
            0.0
        };
        let ground = |x: f64, y: f64| {
            let (mx, my) = match self.crs {
                GeoCrs::Epsg4326 => (
                    EARTH_RADIUS_M * (x + shift).to_radians(),
                    lonlat_to_mercator(0.0, y).1,
                ),
                GeoCrs::Epsg3857 => (x + shift, y),
            };
            self.ground_from_mercator(mx, my, false)
        };
        let clipped = clip_half_planes(
            ground(segment[0], segment[1]),
            ground(segment[2], segment[3]),
            &self.ground_planes(),
        );
        let (a, b) = clipped.map_or((None, None), |(a, b)| {
            (
                Some(self.ground_to_screen(a)),
                Some(self.ground_to_screen(b)),
            )
        });
        Ok((
            (a, b),
            if self.world_wrap {
                Some(segment[2] + shift)
            } else {
                None
            },
        ))
    }
}

fn polygon_peak_admission(col: &GeoColumn) -> Result<(), GeoError> {
    let peak = col
        .vertex_count()
        .checked_mul(4096)
        .and_then(|n| col.len().checked_mul(512).and_then(|f| n.checked_add(f)))
        .ok_or(GeoError::ResourceLimit)?;
    if peak > GeoLimits::default().max_bytes {
        return Err(GeoError::ResourceLimit);
    }
    Ok(())
}
const TOPOLOGY_EPS: f64 = 1e-7;
fn signed_area(ring: &[ScreenPoint]) -> f64 {
    if ring.len() < 3 {
        return 0.0;
    }
    // Translate before area accumulation; distant source magnitude never
    // participates in the products for a small closed fragment (§16).
    let origin = ring[0];
    let mut area = 0.0;
    for pair in ring.windows(2) {
        area += (pair[0].0 - origin.0) * (pair[1].1 - origin.1)
            - (pair[1].0 - origin.0) * (pair[0].1 - origin.1);
    }
    area * 0.5
}
fn ring_contains(ring: &[ScreenPoint], p: ScreenPoint) -> bool {
    let mut inside = false;
    for edge in ring.windows(2) {
        let (a, b) = (edge[0], edge[1]);
        let cross = (b.0 - a.0) * (p.1 - a.1) - (b.1 - a.1) * (p.0 - a.0);
        if cross.abs() <= TOPOLOGY_EPS * (b.0 - a.0).hypot(b.1 - a.1)
            && p.0 >= a.0.min(b.0) - TOPOLOGY_EPS
            && p.0 <= a.0.max(b.0) + TOPOLOGY_EPS
            && p.1 >= a.1.min(b.1) - TOPOLOGY_EPS
            && p.1 <= a.1.max(b.1) + TOPOLOGY_EPS
        {
            return true;
        }
        if (a.1 > p.1) != (b.1 > p.1) && p.0 < (b.0 - a.0) * (p.1 - a.1) / (b.1 - a.1) + a.0 {
            inside = !inside;
        }
    }
    inside
}
fn clip_convex(input: &[ScreenPoint], plane: HalfPlane) -> Vec<ScreenPoint> {
    if input.is_empty() {
        return Vec::new();
    }
    let mut output = Vec::with_capacity(input.len() + 1);
    let mut a = *input.last().unwrap();
    let mut va = plane.value(a);
    for &b in input {
        let vb = plane.value(b);
        if (va >= 0.0) != (vb >= 0.0) {
            let t = va / (va - vb);
            output.push((a.0 + (b.0 - a.0) * t, a.1 + (b.1 - a.1) * t));
        }
        if vb >= 0.0 {
            output.push(b);
        }
        a = b;
        va = vb;
    }
    output
}

/// Clip a possibly concave ring to a convex region by tracing a directed
/// boundary graph. Sorted crossing intervals add only clipping-boundary edges
/// inside the source ring; disjoint components remain separate closed cycles.
fn clip_ring_components(
    ring: &[ScreenPoint],
    region: &[ScreenPoint],
) -> Result<Vec<Vec<ScreenPoint>>, GeoError> {
    if ring.len() < 4 || region.len() < 3 {
        return Ok(Vec::new());
    }
    let max_edges = ring
        .len()
        .checked_mul(region.len() + 2)
        .and_then(|n| n.checked_add(region.len() * 4))
        .ok_or(GeoError::ResourceLimit)?;
    if max_edges.checked_mul(256).ok_or(GeoError::ResourceLimit)? > GeoLimits::default().max_bytes {
        return Err(GeoError::ResourceLimit);
    }
    let mut planes = Vec::with_capacity(region.len());
    for i in 0..region.len() {
        let (a, b) = (region[i], region[(i + 1) % region.len()]);
        let length = (b.0 - a.0).hypot(b.1 - a.1);
        if length == 0.0 {
            continue;
        }
        let (nx, ny) = (-(b.1 - a.1) / length, (b.0 - a.0) / length);
        planes.push(HalfPlane(nx, ny, -nx * a.0 - ny * a.1));
    }
    let mut graph = RingGraph::default();
    for edge in ring.windows(2) {
        if let Some((a, b)) = clip_half_planes(edge[0], edge[1], &planes) {
            if !planes.iter().any(|plane| {
                plane.value(a).abs() < TOPOLOGY_EPS && plane.value(b).abs() < TOPOLOGY_EPS
            }) {
                graph.edge(a, b);
            }
        }
    }
    let positive = signed_area(ring) > 0.0;
    for i in 0..region.len() {
        let (a, b) = (region[i], region[(i + 1) % region.len()]);
        let length = (b.0 - a.0).hypot(b.1 - a.1);
        if length == 0.0 {
            continue;
        }
        let tangent = ((b.0 - a.0) / length, (b.1 - a.1) / length);
        let normal = (-tangent.1, tangent.0);
        let value = |p: ScreenPoint| {
            let v = (p.0 - a.0) * normal.0 + (p.1 - a.1) * normal.1;
            if v.abs() < TOPOLOGY_EPS {
                0.0
            } else {
                v
            }
        };
        let mut crossings = Vec::with_capacity(ring.len());
        for edge in ring.windows(2) {
            let (va, vb) = (value(edge[0]), value(edge[1]));
            if (va > 0.0) != (vb > 0.0) {
                let t = va / (va - vb);
                let p = (
                    edge[0].0 + (edge[1].0 - edge[0].0) * t,
                    edge[0].1 + (edge[1].1 - edge[0].1) * t,
                );
                let position = (p.0 - a.0) * tangent.0 + (p.1 - a.1) * tangent.1;
                crossings.push((position, p));
            }
        }
        crossings.sort_by(|a, b| a.0.total_cmp(&b.0));
        if crossings.len() % 2 != 0 {
            return Err(GeoError::InvalidArgument);
        }
        for pair in crossings.chunks_exact(2) {
            let lo = pair[0].0.max(0.0);
            let hi = pair[1].0.min(length);
            if hi - lo <= TOPOLOGY_EPS {
                continue;
            }
            let start = if pair[0].0 <= 0.0 { a } else { pair[0].1 };
            let end = if pair[1].0 >= length { b } else { pair[1].1 };
            if positive {
                graph.edge(start, end);
            } else {
                graph.edge(end, start);
            }
        }
    }
    graph.cycles(max_edges)
}
#[derive(Default)]
struct RingGraph {
    edges: Vec<ScreenSegment>,
}
impl RingGraph {
    fn edge(&mut self, a: ScreenPoint, b: ScreenPoint) {
        // Only polygon clipping intersections are welded at a fraction of the
        // documented screen tolerance. Canonical source stays exact f64.
        let snap_coordinate = |value: f64| {
            let snapped = (value / TOPOLOGY_EPS).round() * TOPOLOGY_EPS;
            // Numeric equality welds both signed zeros. Normalize the derived
            // node so total-order sorting and endpoint lookup agree with it.
            if snapped == 0.0 {
                0.0
            } else {
                snapped
            }
        };
        let snap = |p: ScreenPoint| (snap_coordinate(p.0), snap_coordinate(p.1));
        let (a, b) = (snap(a), snap(b));
        if a != b {
            self.edges.push((a, b));
        }
    }
    fn cycles(self, max_edges: usize) -> Result<Vec<Vec<ScreenPoint>>, GeoError> {
        if self.edges.len() > max_edges {
            return Err(GeoError::ResourceLimit);
        }
        let cmp = |a: &ScreenPoint, b: &ScreenPoint| a.0.total_cmp(&b.0).then(a.1.total_cmp(&b.1));
        let mut nodes = Vec::with_capacity(self.edges.len() * 2);
        for &(a, b) in &self.edges {
            nodes.extend([a, b]);
        }
        nodes.sort_by(cmp);
        nodes.dedup();
        let mut edges = Vec::with_capacity(self.edges.len());
        for (a, b) in self.edges {
            edges.push((
                nodes.binary_search_by(|p| cmp(p, &a)).unwrap(),
                nodes.binary_search_by(|p| cmp(p, &b)).unwrap(),
            ));
        }
        edges.sort_unstable();
        edges.dedup();
        let mut next = vec![usize::MAX; nodes.len()];
        let mut incoming = vec![0u8; nodes.len()];
        for (a, b) in edges {
            if next[a] != usize::MAX {
                return Err(GeoError::InvalidArgument);
            }
            next[a] = b;
            incoming[b] = incoming[b].saturating_add(1);
        }
        for (i, &target) in next.iter().enumerate() {
            if target != usize::MAX && incoming[i] != 1 {
                return Err(GeoError::InvalidArgument);
            }
        }
        let mut cycles = Vec::new();
        for start in 0..nodes.len() {
            if next[start] == usize::MAX {
                continue;
            }
            let mut ring = vec![nodes[start]];
            let mut current = start;
            loop {
                let target = next[current];
                if target == usize::MAX {
                    return Err(GeoError::InvalidArgument);
                }
                next[current] = usize::MAX;
                ring.push(nodes[target]);
                current = target;
                if current == start {
                    break;
                }
                if ring.len() > max_edges + 1 {
                    return Err(GeoError::ResourceLimit);
                }
            }
            if ring.len() >= 4 && signed_area(&ring).abs() > 1e-12 {
                cycles.push(ring);
            }
        }
        Ok(cycles)
    }
}

/// Source feature ID for every retained Point / MultiPoint vertex.
fn point_vertex_feature_ids(col: &GeoColumn) -> Vec<u64> {
    let ids = col.feature_ids();
    if col.geometry() == GeoGeometry::Point {
        // Null points contribute no vertex.
        return col
            .validity()
            .iter()
            .zip(ids)
            .filter(|(&flag, _)| flag == 1)
            .map(|(_, &id)| id)
            .collect();
    }
    let offsets = col.offsets0();
    let mut out = Vec::with_capacity(col.vertex_count());
    for (feature, &id) in ids.iter().enumerate() {
        let count = (offsets[feature + 1] - offsets[feature]) as usize;
        out.extend(std::iter::repeat_n(id, count));
    }
    out
}

/// Flatten a line / polygon column into `(part_offsets, part_feature_ids)`:
/// one part per line (LineString feature, MultiLineString line) or ring, with
/// the owning feature ID, over the column's unmodified vertex plane.
fn outline_parts(col: &GeoColumn) -> (Vec<u32>, Vec<u64>) {
    let ids = col.feature_ids();
    let (o0, o1) = (col.offsets0(), col.offsets1());
    match col.geometry() {
        GeoGeometry::LineString => (o0.to_vec(), ids.to_vec()),
        GeoGeometry::MultiLineString => {
            let mut parts = Vec::with_capacity(o1.len().saturating_sub(1));
            for (feature, &id) in ids.iter().enumerate() {
                let lines = (o0[feature + 1] - o0[feature]) as usize;
                parts.extend(std::iter::repeat_n(id, lines));
            }
            (o1.to_vec(), parts)
        }
        GeoGeometry::Polygon => {
            let mut parts = Vec::with_capacity(o1.len().saturating_sub(1));
            for (feature, &id) in ids.iter().enumerate() {
                let rings = (o0[feature + 1] - o0[feature]) as usize;
                parts.extend(std::iter::repeat_n(id, rings));
            }
            (o1.to_vec(), parts)
        }
        GeoGeometry::MultiPolygon => {
            let o2 = col.offsets2();
            let mut parts = Vec::with_capacity(o2.len().saturating_sub(1));
            for (feature, &id) in ids.iter().enumerate() {
                let first_ring = o1[o0[feature] as usize] as usize;
                let end_ring = o1[o0[feature + 1] as usize] as usize;
                parts.extend(std::iter::repeat_n(id, end_ring - first_ring));
            }
            (o2.to_vec(), parts)
        }
        GeoGeometry::Point | GeoGeometry::MultiPoint => (vec![0], Vec::new()),
    }
}

fn validate_line_coordinates(crs: GeoCrs, xy: &[f64]) -> Result<(), GeoError> {
    for pair in xy.chunks_exact(2) {
        if !pair[0].is_finite() || !pair[1].is_finite() {
            return Err(GeoError::NonFiniteCoordinate);
        }
        let valid = match crs {
            GeoCrs::Epsg4326 => pair[0].abs() <= 180.0 && pair[1].abs() <= 90.0,
            GeoCrs::Epsg3857 => {
                pair[0].abs() <= WEB_MERCATOR_MAX && pair[1].abs() <= WEB_MERCATOR_MAX
            }
        };
        if !valid {
            return Err(GeoError::CoordinateOutOfRange);
        }
    }
    Ok(())
}

/// Return independent source-CRS segments, splitting dateline crossings into
/// paired ±180° endpoints. Interpolating latitude in source space is the
/// deterministic v1 route contract; geographic curves remain a later layer.
fn split_line_segment(
    crs: GeoCrs,
    world_wrap: bool,
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
) -> ([[f64; 4]; 2], usize) {
    let half = match crs {
        GeoCrs::Epsg4326 => 180.0,
        GeoCrs::Epsg3857 => WEB_MERCATOR_MAX,
    };
    if !world_wrap || (x1 - x0).abs() <= half || (x1 - x0).abs() == 2.0 * half {
        return ([[x0, y0, x1, y1], [0.0; 4]], 1);
    }
    let (end, boundary) = if x1 < x0 {
        (x1 + 2.0 * half, half)
    } else {
        (x1 - 2.0 * half, -half)
    };
    let t = (boundary - x0) / (end - x0);
    let cross = y0 + (y1 - y0) * t;
    ([[x0, y0, boundary, cross], [-boundary, cross, x1, y1]], 2)
}

#[derive(Clone, Copy, Debug)]
struct HalfPlane(f64, f64, f64);
impl HalfPlane {
    fn value(self, p: ScreenPoint) -> f64 {
        self.0 * p.0 + self.1 * p.1 + self.2
    }
}
fn clip_half_planes(a: ScreenPoint, b: ScreenPoint, planes: &[HalfPlane]) -> Option<ScreenSegment> {
    let (mut lo, mut hi) = (0.0f64, 1.0f64);
    for &plane in planes {
        let (va, vb) = (plane.value(a), plane.value(b));
        if va < 0.0 && vb < 0.0 {
            return None;
        }
        if va < 0.0 {
            lo = lo.max(va / (va - vb));
        }
        if vb < 0.0 {
            hi = hi.min(va / (va - vb));
        }
    }
    if lo > hi {
        return None;
    }
    Some((
        (a.0 + (b.0 - a.0) * lo, a.1 + (b.1 - a.1) * lo),
        (a.0 + (b.0 - a.0) * hi, a.1 + (b.1 - a.1) * hi),
    ))
}

/// Clamp latitude to the Web Mercator domain.
#[must_use]
pub fn clamp_lat(lat_deg: f64) -> f64 {
    lat_deg.clamp(-MAX_WEB_MERCATOR_LAT_DEG, MAX_WEB_MERCATOR_LAT_DEG)
}

/// Normalize longitude into (-180, 180].
#[must_use]
pub fn normalize_lon(lon_deg: f64) -> f64 {
    if !lon_deg.is_finite() {
        return lon_deg;
    }
    let mut lon = ((lon_deg + 180.0) % 360.0 + 360.0) % 360.0 - 180.0;
    if lon == -180.0 {
        lon = 180.0;
    }
    lon
}

/// Normalize bearing into `(-180, 180]` degrees.
#[must_use]
pub fn normalize_bearing(bearing_deg: f64) -> f64 {
    normalize_lon(bearing_deg)
}

fn canonical_f64_bits(value: f64) -> u64 {
    if value == 0.0 {
        0.0_f64.to_bits()
    } else {
        value.to_bits()
    }
}

/// Lon/lat degrees → Web Mercator metres (EPSG:3857).
#[must_use]
pub fn lonlat_to_mercator(lon_deg: f64, lat_deg: f64) -> (f64, f64) {
    let lon = normalize_lon(lon_deg);
    let lat = clamp_lat(lat_deg);
    let x = EARTH_RADIUS_M * lon.to_radians();
    let y = EARTH_RADIUS_M
        * (std::f64::consts::FRAC_PI_4 + lat.to_radians() / 2.0)
            .tan()
            .ln();
    (
        x.clamp(-WEB_MERCATOR_MAX, WEB_MERCATOR_MAX),
        y.clamp(-WEB_MERCATOR_MAX, WEB_MERCATOR_MAX),
    )
}

/// Web Mercator metres → lon/lat degrees.
#[must_use]
pub fn mercator_to_lonlat(x: f64, y: f64) -> (f64, f64) {
    let x = x.clamp(-WEB_MERCATOR_MAX, WEB_MERCATOR_MAX);
    let y = y.clamp(-WEB_MERCATOR_MAX, WEB_MERCATOR_MAX);
    let lon = normalize_lon((x / EARTH_RADIUS_M).to_degrees());
    let lat = (2.0 * (y / EARTH_RADIUS_M).exp().atan() - std::f64::consts::FRAC_PI_2).to_degrees();
    (lon, clamp_lat(lat))
}

/// Choose the longitudinal span (west, east) that is ≤ 180° wide, allowing
/// antimeridian wrap when `max_lon < min_lon` or the wrapped path is shorter.
fn wrapped_lon_span(min_lon: f64, max_lon: f64) -> (f64, f64) {
    let a = normalize_lon(min_lon);
    let b = normalize_lon(max_lon);
    let direct = (b - a + 360.0) % 360.0;
    if direct <= 180.0 {
        (a, if b < a { b + 360.0 } else { b })
    } else {
        // Prefer the other direction: treat `b` as west.
        (b, a + 360.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn denver() -> GeoViewport {
        GeoViewport::new(
            GeoCrs::Epsg4326,
            -104.9903,
            39.7392,
            10.0,
            800.0,
            600.0,
            0.0,
            0.0,
            true,
        )
        .unwrap()
    }

    #[test]
    fn camera_renderability_failures_are_atomic_and_behind_points_are_not_visible() {
        let mut vp = denver();
        let before = vp;
        for value in [f64::MAX, 1e-300, 0.0, -1.0] {
            assert!(vp.resize(value, 600.0).is_err());
            assert_eq!(vp, before);
            assert!(vp.resize(800.0, value).is_err());
            assert_eq!(vp, before);
        }
        let tiny = GeoViewport::new(
            GeoCrs::Epsg4326,
            0.0,
            0.0,
            0.0,
            f32::MIN_POSITIVE as f64,
            f32::MIN_POSITIVE as f64,
            0.0,
            60.0,
            true,
        )
        .unwrap();
        let cache = tiny.project_offset_f32(&[0.0, 0.0]).unwrap();
        assert!(cache.0.iter().all(|v| v.is_finite()));
        let vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            0.0,
            0.0,
            4.0,
            800.0,
            600.0,
            0.0,
            60.0,
            true,
        )
        .unwrap();
        let source = column(
            GeoGeometry::Point,
            &[0.0, -70.0, 0.0, 0.0],
            &[1, 1],
            Some(&[1, u64::MAX]),
            [&[], &[], &[]],
        );
        let result = vp.project_column(&source).unwrap();
        assert_eq!(result.visible_feature_ids, [u64::MAX]);
        let ProjectedGeoGeometry::Points(points) = result.geometry else {
            panic!("points");
        };
        assert!(points.xy.iter().all(|v| v.is_finite()));
    }
    #[test]
    fn pitched_polygon_deep_zoom_preserves_local_f32_detail_and_source() {
        let vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            0.0,
            0.0,
            24.0,
            800.0,
            600.0,
            0.0,
            45.0,
            false,
        )
        .unwrap();
        let xy = [0.0, 0.0, 1e-7, 0.0, 1e-7, 1e-7, 0.0, 1e-7, 0.0, 0.0];
        let source = column(
            GeoGeometry::Polygon,
            &xy,
            &[1],
            Some(&[9]),
            [&[0, 1], &[0, 5], &[]],
        );
        let projected = vp.project_column(&source).unwrap();
        let poly = projected.polygons.unwrap();
        assert_eq!(poly.feature_ids, [9]);
        let bottom: Vec<_> = poly
            .xy
            .chunks_exact(2)
            .filter(|p| p[1].abs() < 1e-5)
            .map(|p| p[0] as f64)
            .collect();
        assert!(bottom.len() >= 2);
        let spread = bottom.iter().copied().fold(f64::NEG_INFINITY, f64::max)
            - bottom.iter().copied().fold(f64::INFINITY, f64::min);
        assert!((spread - 2.386092942222222).abs() < 1e-6);
        assert_eq!(source.xy(), xy);
    }
    #[test]
    fn polygon_peak_rejects_before_outline_and_topology_allocations() {
        let vp = denver();
        let mut xy = Vec::with_capacity(65542 * 2);
        for _ in 0..21847 {
            xy.extend([0.0, 0.0, 1.0, 0.0, 0.0, 1.0]);
        }
        xy.extend([0.0, 0.0]);
        let source = column(
            GeoGeometry::Polygon,
            &xy,
            &[1],
            None,
            [&[0, 1], &[0, (xy.len() / 2) as u32], &[]],
        );
        assert_eq!(
            vp.project_column(&source).unwrap_err(),
            GeoError::ResourceLimit
        );
    }

    #[test]
    fn perspective_matches_default_mercator_matrix_goldens_and_inverts() {
        // Independent zero-roll/elevation MapLibre matrix goldens: world
        // pixels offset(100,100), default vertical FOV and 800x600 camera.
        for (pitch, x, y) in [
            (30.0, 505.88235294117646, 391.6968074595288),
            (60.0, 510.64701387421803, 355.323506937109),
            (-45.0, 492.7155763594051, 365.5598127653545),
        ] {
            let vp = GeoViewport::new(
                GeoCrs::Epsg3857,
                0.0,
                0.0,
                0.0,
                800.0,
                600.0,
                0.0,
                pitch,
                false,
            )
            .unwrap();
            let source = (
                100.0 * vp.metres_per_pixel(),
                -100.0 * vp.metres_per_pixel(),
            );
            let actual = vp.project(source.0, source.1).unwrap();
            assert!((actual.0 - x).abs() < tolerances::SCREEN_PX);
            assert!((actual.1 - y).abs() < tolerances::SCREEN_PX);
            let back = vp.unproject(actual.0, actual.1).unwrap();
            assert!((back.0 - source.0).abs() < tolerances::MERCATOR_M);
            assert!((back.1 - source.1).abs() < tolerances::MERCATOR_M);
            let mut turned = vp;
            turned.set_bearing(73.0).unwrap();
            let screen = turned.project(source.0, source.1).unwrap();
            let back = turned.unproject(screen.0, screen.1).unwrap();
            assert!((back.0 - source.0).abs() < tolerances::MERCATOR_M);
            assert!((back.1 - source.1).abs() < tolerances::MERCATOR_M);
        }
    }
    #[test]
    fn perspective_clips_before_dividing_and_rejects_horizon_inverse() {
        let vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            0.0,
            0.0,
            4.0,
            800.0,
            600.0,
            0.0,
            60.0,
            false,
        )
        .unwrap();
        let lines = vp
            .project_line_features(&[0.0, -70.0, 0.0, 70.0], &[0, 2], &[u64::MAX])
            .unwrap();
        assert!(!lines.xy.is_empty());
        assert!(lines.xy.iter().all(|v| v.is_finite()));
        for pair in lines.xy.chunks_exact(2) {
            let (x, y) = (
                lines.origin_x + pair[0] as f64,
                lines.origin_y + pair[1] as f64,
            );
            assert!(x >= -1e-4 && x <= vp.width + 1e-4 && y >= -1e-4 && y <= vp.height + 1e-4);
        }
        assert!(vp.unproject(400.0, -1000.0).is_err());
        let behind = vp.project_offset_f32(&[0.0, -70.0]).unwrap();
        assert!(behind.0.iter().all(|v| v.is_finite()));
    }
    #[test]
    fn pitched_fit_and_pan_preserve_complete_transactional_camera() {
        let mut vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            0.0,
            0.0,
            4.0,
            800.0,
            600.0,
            37.0,
            60.0,
            true,
        )
        .unwrap();
        vp.fit_bounds(-10.0, -5.0, 10.0, 5.0, 40.0).unwrap();
        for (x, y) in [(-10.0, -5.0), (10.0, -5.0), (10.0, 5.0), (-10.0, 5.0)] {
            let (x, y) = vp.project(x, y).unwrap();
            assert!((40.0 - 1e-6..=760.0 + 1e-6).contains(&x));
            assert!((40.0 - 1e-6..=560.0 + 1e-6).contains(&y));
        }
        let expected = vp.unproject(450.0, 325.0).unwrap();
        vp.pan_by_pixels(50.0, 25.0).unwrap();
        assert!((vp.center_x - expected.0).abs() < 1e-9);
        assert!((vp.center_y - expected.1).abs() < 1e-9);
        let before = vp;
        assert!(vp.fit_bounds(-180.0, -80.0, 180.0, 80.0, 299.0).is_err());
        assert_eq!(vp, before);
    }
    fn polygon_at_screen(vp: &GeoViewport, rings: &[Vec<ScreenPoint>]) -> GeoColumn {
        let mut xy = Vec::new();
        let mut offsets = vec![0u32];
        for ring in rings {
            for &(x, y) in ring {
                let p = vp.unproject(x, y).unwrap();
                xy.extend([p.0, p.1]);
            }
            offsets.push((xy.len() / 2) as u32);
        }
        column(
            GeoGeometry::Polygon,
            &xy,
            &[1],
            Some(&[0xffffffffffffffff]),
            [&[0, rings.len() as u32], &offsets, &[]],
        )
    }
    #[test]
    fn clipping_graph_welds_signed_zero_endpoints_into_one_closed_ring() {
        for origin in [(-0.0, 0.0), (0.0, -0.0), (-0.0, -0.0), (0.0, 0.0)] {
            let mut graph = RingGraph::default();
            graph.edge(origin, (1.0, 0.0));
            graph.edge((1.0, 0.0), (1.0, 1.0));
            graph.edge((1.0, 1.0), (0.0, 1.0));
            graph.edge((0.0, 1.0), (0.0, 0.0));
            let rings = graph.cycles(4).unwrap();
            assert_eq!(rings.len(), 1);
            assert_eq!(rings[0].first(), rings[0].last());
            assert_eq!(signed_area(&rings[0]), 1.0);
            for &(x, y) in &rings[0] {
                for coordinate in [x, y] {
                    if coordinate == 0.0 {
                        assert_eq!(coordinate.to_bits(), 0);
                    }
                }
            }
        }
    }
    #[test]
    fn concave_clip_preserves_two_closed_components_without_boundary_bridge() {
        let vp =
            GeoViewport::new(GeoCrs::Epsg4326, 0.0, 0.0, 0.0, 4.0, 2.0, 0.0, 0.0, false).unwrap();
        let ring = vec![
            (0.5, -2.0),
            (3.5, -2.0),
            (3.5, 2.0),
            (2.5, 2.0),
            (2.5, -1.0),
            (1.5, -1.0),
            (1.5, 2.0),
            (0.5, 2.0),
            (0.5, -2.0),
        ];
        let col = polygon_at_screen(&vp, &[ring]);
        let projected = vp.project_column(&col).unwrap();
        let polygons = projected.polygons.unwrap();
        assert_eq!(polygons.feature_ids, [u64::MAX; 2]);
        assert_eq!(polygons.polygon_offsets, [0, 1, 2]);
        assert_eq!(polygons.ring_is_hole, [0, 0]);
        assert_eq!(projected.visible_feature_ids, [u64::MAX]);
        for range in polygons.ring_offsets.windows(2) {
            let vertices = &polygons.xy[range[0] as usize * 2..range[1] as usize * 2];
            assert_eq!(&vertices[..2], &vertices[vertices.len() - 2..]);
            let min = vertices
                .chunks_exact(2)
                .map(|p| p[0])
                .fold(f32::INFINITY, f32::min);
            let max = vertices
                .chunks_exact(2)
                .map(|p| p[0])
                .fold(f32::NEG_INFINITY, f32::max);
            assert!((max - min - 1.0).abs() < 1e-6);
        }
    }
    #[test]
    fn polygon_inside_hole_is_invisible_and_border_contact_retains_hole_role() {
        let vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            0.0,
            0.0,
            0.0,
            800.0,
            600.0,
            0.0,
            0.0,
            false,
        )
        .unwrap();
        let shell = vec![
            (-100.0, -100.0),
            (900.0, -100.0),
            (900.0, 700.0),
            (-100.0, 700.0),
            (-100.0, -100.0),
        ];
        // Use zoom2 so offscreen authoring points remain within source world.
        let mut vp = vp;
        vp.set_zoom(2.0).unwrap();
        let covering_hole = vec![
            (-50.0, -50.0),
            (-50.0, 650.0),
            (850.0, 650.0),
            (850.0, -50.0),
            (-50.0, -50.0),
        ];
        let col = polygon_at_screen(&vp, &[shell.clone(), covering_hole]);
        let result = vp.project_column(&col).unwrap();
        assert!(result.visible_feature_ids.is_empty());
        assert!(result.polygons.unwrap().feature_ids.is_empty());
        assert_eq!(result.visible_bounds, None);
        let border_hole = vec![
            (400.0, 100.0),
            (400.0, 500.0),
            (850.0, 500.0),
            (850.0, 100.0),
            (400.0, 100.0),
        ];
        let col = polygon_at_screen(&vp, &[shell, border_hole]);
        let result = vp.project_column(&col).unwrap();
        let poly = result.polygons.unwrap();
        assert_eq!(result.visible_feature_ids, [u64::MAX]);
        assert_eq!(poly.polygon_offsets, [0, 2]);
        assert_eq!(poly.ring_is_hole, [0, 1]);
        assert!(poly.xy.iter().all(|v| v.is_finite()));
    }
    #[test]
    fn dateline_polygon_shell_and_hole_remain_closed_and_identified() {
        let vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            180.0,
            0.0,
            2.0,
            800.0,
            600.0,
            30.0,
            45.0,
            true,
        )
        .unwrap();
        let xy = [
            170.0, -10.0, -170.0, -10.0, -170.0, 10.0, 170.0, 10.0, 170.0, -10.0, 175.0, -5.0,
            175.0, 5.0, -175.0, 5.0, -175.0, -5.0, 175.0, -5.0,
        ];
        let col = column(
            GeoGeometry::Polygon,
            &xy,
            &[1],
            Some(&[42]),
            [&[0, 2], &[0, 5, 10], &[]],
        );
        let result = vp.project_column(&col).unwrap();
        let poly = result.polygons.unwrap();
        assert_eq!(result.visible_feature_ids, [42]);
        assert!(!poly.feature_ids.is_empty());
        assert!(poly.feature_ids.iter().all(|&id| id == 42));
        assert!(poly.ring_is_hole.contains(&1));
        for range in poly.ring_offsets.windows(2) {
            let vertices = &poly.xy[range[0] as usize * 2..range[1] as usize * 2];
            assert_eq!(&vertices[..2], &vertices[vertices.len() - 2..]);
            assert!(vertices.iter().all(|v| v.is_finite()));
        }
        assert_eq!(col.xy(), xy);
    }

    #[test]
    fn mercator_round_trip_at_known_points() {
        for &(lon, lat) in &[
            (0.0, 0.0),
            (-104.9903, 39.7392),
            (179.9, 0.0),
            (-179.9, -40.0),
            (0.0, MAX_WEB_MERCATOR_LAT_DEG),
        ] {
            let (x, y) = lonlat_to_mercator(lon, lat);
            let (lon2, lat2) = mercator_to_lonlat(x, y);
            assert!((lon2 - normalize_lon(lon)).abs() < tolerances::LONLAT_DEG);
            assert!((lat2 - clamp_lat(lat)).abs() < tolerances::LONLAT_DEG);
            assert!(x.abs() <= WEB_MERCATOR_MAX + 1e-6);
            assert!(y.abs() <= WEB_MERCATOR_MAX + 1e-6);
        }
    }

    #[test]
    fn polar_latitudes_clamp_before_mercator() {
        let (x, y) = lonlat_to_mercator(0.0, 89.9);
        let (_lon, lat) = mercator_to_lonlat(x, y);
        assert!((lat - MAX_WEB_MERCATOR_LAT_DEG).abs() < 1e-9);
        assert!((y - WEB_MERCATOR_MAX).abs() < 1e-6);
    }

    #[test]
    fn project_unproject_round_trip() {
        let vp = denver();
        for &(lon, lat) in &[(-104.9903, 39.7392), (-105.0, 40.0), (-104.5, 39.5)] {
            let (sx, sy) = vp.project(lon, lat).unwrap();
            let (lon2, lat2) = vp.unproject(sx, sy).unwrap();
            assert!((lon2 - lon).abs() < tolerances::LONLAT_DEG);
            assert!((lat2 - lat).abs() < tolerances::LONLAT_DEG);
        }
        // Center projects to viewport midpoint.
        let (sx, sy) = vp.project(vp.center_x, vp.center_y).unwrap();
        assert!((sx - 400.0).abs() < tolerances::SCREEN_PX);
        assert!((sy - 300.0).abs() < tolerances::SCREEN_PX);
    }

    #[test]
    fn bearing_rotates_and_inverts() {
        let mut vp = denver();
        vp.bearing_deg = 90.0;
        let (sx, sy) = vp.project(-104.9903 + 0.1, 39.7392).unwrap();
        assert!((sx - vp.width * 0.5).abs() < tolerances::SCREEN_PX);
        assert!(
            sy < vp.height * 0.5,
            "east must be screen-up at +90° bearing"
        );
        let (lon, lat) = vp.unproject(sx, sy).unwrap();
        assert!((lon - (-104.9903 + 0.1)).abs() < 1e-7);
        assert!((lat - 39.7392).abs() < 1e-7);
    }

    #[test]
    fn fit_and_pan_reject_restored_invalid_cameras_without_mutation() {
        for invalid in [f64::NAN, f64::INFINITY, 61.0] {
            let mut vp = denver();
            vp.pitch_deg = invalid;
            let before = [
                vp.center_x.to_bits(),
                vp.center_y.to_bits(),
                vp.zoom.to_bits(),
                vp.bearing_deg.to_bits(),
                vp.pitch_deg.to_bits(),
            ];
            assert!(vp.fit_bounds(-105.1, 39.6, -104.8, 39.9, 40.0).is_err());
            assert_eq!(
                [
                    vp.center_x.to_bits(),
                    vp.center_y.to_bits(),
                    vp.zoom.to_bits(),
                    vp.bearing_deg.to_bits(),
                    vp.pitch_deg.to_bits()
                ],
                before
            );
            for delta in [(0.0, 0.0), (10.0, 20.0)] {
                assert!(vp.pan_by_pixels(delta.0, delta.1).is_err());
                assert_eq!(
                    [
                        vp.center_x.to_bits(),
                        vp.center_y.to_bits(),
                        vp.zoom.to_bits(),
                        vp.bearing_deg.to_bits(),
                        vp.pitch_deg.to_bits()
                    ],
                    before
                );
            }
        }
        let mut vp = denver();
        vp.center_x = 181.0;
        assert_eq!(
            vp.pan_by_pixels(0.0, 0.0),
            Err(GeoError::CoordinateOutOfRange)
        );
        assert_eq!(
            vp.fit_bounds(-10.0, -10.0, 10.0, 10.0, 0.0),
            Err(GeoError::CoordinateOutOfRange)
        );
        assert_eq!(vp.center_x, 181.0);
    }

    #[test]
    fn fit_bounds_centers_and_zooms() {
        let mut vp = denver();
        vp.fit_bounds(-105.1, 39.6, -104.8, 39.9, 40.0).unwrap();
        assert!((vp.center_x - (-104.95)).abs() < 1e-6);
        assert!((vp.center_y - 39.75).abs() < 1e-3);
        assert!(vp.zoom > 8.0 && vp.zoom < 14.0);
        let (sx0, sy0) = vp.project(-105.1, 39.6).unwrap();
        let (sx1, sy1) = vp.project(-104.8, 39.9).unwrap();
        assert!(sx0 > 40.0 - 1.0 && sx0 < vp.width - 40.0 + 1.0);
        assert!(sx1 > 40.0 - 1.0 && sx1 < vp.width - 40.0 + 1.0);
        assert!(sy0.min(sy1) > 40.0 - 1.0);
        assert!(sy0.max(sy1) < vp.height - 40.0 + 1.0);
    }

    #[test]
    fn fit_bounds_prefers_antimeridian_short_span() {
        let mut vp = denver();
        // Dateline-crossing bbox: 170E .. 170W (= -170)
        vp.fit_bounds(170.0, -10.0, -170.0, 10.0, 20.0).unwrap();
        assert_eq!(vp.center_x, 180.0);
        assert!(vp.zoom > 3.0, "20-degree span must not fit as 340 degrees");
        let (west_x, _) = vp.project(170.0, 0.0).unwrap();
        let (east_x, _) = vp.project(-170.0, 0.0).unwrap();
        assert!(west_x >= 20.0 - 1.0);
        assert!(east_x <= vp.width - 20.0 + 1.0);
        assert!(west_x < east_x);
    }

    #[test]
    fn world_wrap_projects_across_dateline_by_shortest_path() {
        let vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            179.0,
            0.0,
            5.0,
            800.0,
            600.0,
            0.0,
            0.0,
            true,
        )
        .unwrap();
        let (sx, _) = vp.project(-179.0, 0.0).unwrap();
        assert!(sx > 400.0 && sx < 600.0);
        let (lon, lat) = vp.unproject(sx, 300.0).unwrap();
        assert!((lon - -179.0).abs() < tolerances::LONLAT_DEG);
        assert!(lat.abs() < tolerances::LONLAT_DEG);
    }

    #[test]
    fn rejected_mutations_leave_camera_valid_and_unchanged() {
        let mut vp = denver();
        let original = vp;
        assert_eq!(
            vp.set_center(f64::NAN, 0.0),
            Err(GeoError::NonFiniteCoordinate)
        );
        assert_eq!(vp, original);
        assert_eq!(vp.set_zoom(25.0), Err(GeoError::InvalidArgument));
        assert_eq!(vp, original);
        assert_eq!(vp.resize(0.0, 600.0), Err(GeoError::InvalidArgument));
        assert_eq!(vp, original);
        assert_eq!(vp.set_pitch(61.0), Err(GeoError::InvalidArgument));
        assert_eq!(vp, original);
        assert_eq!(
            vp.set_bearing(f64::INFINITY),
            Err(GeoError::NonFiniteCoordinate)
        );
        assert_eq!(vp, original);
        assert_eq!(
            vp.pan_by_pixels(f64::NAN, 0.0),
            Err(GeoError::NonFiniteCoordinate)
        );
        assert_eq!(vp, original);
    }

    #[test]
    fn camera_setters_normalize_bearing_and_freeze_pitch() {
        let mut vp = denver();
        vp.set_bearing(450.0).unwrap();
        vp.set_pitch(45.0).unwrap();
        assert_eq!(vp.bearing_deg, 90.0);
        assert_eq!(vp.pitch_deg, 45.0);

        let source = (-104.8, 39.8);
        let screen = vp.project(source.0, source.1).unwrap();
        let restored = vp.unproject(screen.0, screen.1).unwrap();
        assert!((restored.0 - source.0).abs() < tolerances::LONLAT_DEG);
        assert!((restored.1 - source.1).abs() < tolerances::LONLAT_DEG);
    }

    #[test]
    fn constructor_and_projection_canonicalize_full_turn_bearings() {
        let canonical = denver();
        let restored = GeoViewport::new(
            canonical.crs,
            canonical.center_x,
            canonical.center_y,
            canonical.zoom,
            canonical.width,
            canonical.height,
            360.0,
            canonical.pitch_deg,
            canonical.world_wrap,
        )
        .unwrap();
        assert_eq!(restored.bearing_deg, 0.0);
        assert_eq!(restored.rebuild_key(), canonical.rebuild_key());
        assert_eq!(
            restored.project(-104.8, 39.8).unwrap(),
            canonical.project(-104.8, 39.8).unwrap()
        );

        // A deserialized/public-field camera cannot turn an otherwise finite
        // projection into NaN through degree-to-radian overflow.
        let mut extreme = canonical;
        extreme.bearing_deg = f64::MAX;
        let projected = extreme.project(-104.8, 39.8).unwrap();
        assert!(projected.0.is_finite() && projected.1.is_finite());
    }

    #[test]
    fn pixel_pan_moves_center_in_bearing_aware_screen_space() {
        let mut vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            0.0,
            0.0,
            4.0,
            800.0,
            600.0,
            90.0,
            0.0,
            true,
        )
        .unwrap();
        let expected = vp.unproject(440.0, 320.0).unwrap();
        vp.pan_by_pixels(40.0, 20.0).unwrap();
        assert!((vp.center_x - expected.0).abs() < tolerances::LONLAT_DEG);
        assert!((vp.center_y - expected.1).abs() < tolerances::LONLAT_DEG);
        let (sx, sy) = vp.project(vp.center_x, vp.center_y).unwrap();
        assert!((sx - 400.0).abs() < tolerances::SCREEN_PX);
        assert!((sy - 300.0).abs() < tolerances::SCREEN_PX);
        assert!(vp.center_x < 0.0, "screen-down points west at +90° bearing");
        assert!(
            vp.center_y < 0.0,
            "screen-right points south at +90° bearing"
        );
    }

    #[test]
    fn pixel_pan_wraps_or_stops_at_world_and_polar_limits() {
        let mut wrapped = GeoViewport::new(
            GeoCrs::Epsg4326,
            179.0,
            84.0,
            2.0,
            800.0,
            600.0,
            0.0,
            0.0,
            true,
        )
        .unwrap();
        wrapped.pan_by_pixels(200.0, -10_000.0).unwrap();
        assert!((-180.0..=180.0).contains(&wrapped.center_x));
        assert_eq!(wrapped.center_y, MAX_WEB_MERCATOR_LAT_DEG);

        let mut bounded = wrapped;
        bounded.world_wrap = false;
        bounded.center_x = 179.0;
        bounded.pan_by_pixels(10_000.0, 0.0).unwrap();
        assert_eq!(bounded.center_x, 180.0);
        bounded.center_x = -179.0;
        bounded.pan_by_pixels(-10_000.0, 0.0).unwrap();
        assert_eq!(bounded.center_x, -180.0);
    }

    #[test]
    fn rebuild_key_is_complete_canonical_and_noop_stable() {
        let mut vp = denver();
        let initial = vp.rebuild_key();
        vp.pan_by_pixels(0.0, -0.0).unwrap();
        assert_eq!(vp.rebuild_key(), initial);

        let mut equivalent = vp;
        equivalent.bearing_deg = 360.0;
        assert_eq!(equivalent.rebuild_key(), initial);

        let east = GeoViewport::new(
            GeoCrs::Epsg4326,
            180.0,
            0.0,
            1.0,
            100.0,
            100.0,
            0.0,
            0.0,
            true,
        )
        .unwrap();
        let west = GeoViewport::new(
            GeoCrs::Epsg4326,
            -180.0,
            0.0,
            1.0,
            100.0,
            100.0,
            0.0,
            0.0,
            true,
        )
        .unwrap();
        assert_eq!(east.rebuild_key(), west.rebuild_key());

        vp.resize(801.0, 600.0).unwrap();
        assert_ne!(vp.rebuild_key(), initial);
        let resized = vp.rebuild_key();
        vp.set_pitch(1.0).unwrap();
        assert_ne!(vp.rebuild_key(), resized);
    }

    #[test]
    fn restored_nonfinite_camera_fails_closed_before_projection_or_identity() {
        let mut vp = denver();
        vp.bearing_deg = f64::NAN;
        assert_eq!(vp.project(-104.8, 39.8), Err(GeoError::NonFiniteCoordinate));
        assert_eq!(
            vp.unproject(400.0, 300.0),
            Err(GeoError::NonFiniteCoordinate)
        );
        assert_eq!(
            vp.project_offset_f32(&[-104.8, 39.8]),
            Err(GeoError::NonFiniteCoordinate)
        );
        assert_eq!(
            vp.project_line_features(&[-104.8, 39.8, -104.7, 39.9], &[0, 2], &[7]),
            Err(GeoError::NonFiniteCoordinate)
        );
        assert_eq!(vp.rebuild_key(), Err(GeoError::NonFiniteCoordinate));
    }

    #[test]
    fn offset_f32_encode_keeps_relative_precision() {
        let vp = denver();
        let xy = [-104.9903, 39.7392, -104.9902, 39.7393];
        let (encoded, ox, oy) = vp.project_offset_f32(&xy).unwrap();
        assert_eq!(encoded.len(), 4);
        assert_eq!(encoded[0], 0.0);
        assert_eq!(encoded[1], 0.0);
        let (sx1, sy1) = vp.project(xy[2], xy[3]).unwrap();
        assert!(((encoded[2] as f64) - (sx1 - ox)).abs() < 1e-3);
        assert!(((encoded[3] as f64) - (sy1 - oy)).abs() < 1e-3);
    }

    #[test]
    fn rejects_non_finite_and_bad_size() {
        assert_eq!(
            GeoViewport::new(GeoCrs::Epsg4326, 0.0, 0.0, 1.0, 0.0, 100.0, 0.0, 0.0, false)
                .unwrap_err(),
            GeoError::InvalidArgument
        );
        let vp = denver();
        assert_eq!(
            vp.project(f64::NAN, 0.0).unwrap_err(),
            GeoError::NonFiniteCoordinate
        );
    }

    #[test]
    fn epsg3857_center_round_trips_through_screen() {
        let (mx, my) = lonlat_to_mercator(-104.9903, 39.7392);
        let vp =
            GeoViewport::new(GeoCrs::Epsg3857, mx, my, 8.0, 640.0, 480.0, 0.0, 0.0, false).unwrap();
        let (sx, sy) = vp.project(mx + 1000.0, my - 500.0).unwrap();
        let (x2, y2) = vp.unproject(sx, sy).unwrap();
        assert!((x2 - (mx + 1000.0)).abs() < tolerances::MERCATOR_M);
        assert!((y2 - (my - 500.0)).abs() < tolerances::MERCATOR_M);
    }

    #[test]
    fn dateline_route_splits_without_long_world_segment() {
        let vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            180.0,
            0.0,
            2.0,
            800.0,
            600.0,
            0.0,
            0.0,
            true,
        )
        .unwrap();
        let lines = vp
            .project_line_features(&[170.0, -10.0, -170.0, 10.0], &[0, 2], &[42])
            .unwrap();
        assert_eq!(lines.offsets, [0, 2, 4]);
        assert_eq!(lines.feature_ids, [42, 42]);
        assert_eq!(lines.xy.len(), 8);
        for point in lines.xy.chunks_exact(2) {
            let x = point[0] as f64 + lines.origin_x;
            let y = point[1] as f64 + lines.origin_y;
            assert!((0.0..=vp.width).contains(&x));
            assert!((0.0..=vp.height).contains(&y));
        }
    }

    #[test]
    fn dateline_route_uses_coherent_world_copies_away_from_dateline_center() {
        let vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            0.0,
            0.0,
            0.0,
            512.0,
            300.0,
            0.0,
            0.0,
            true,
        )
        .unwrap();
        for xy in [[170.0, 0.0, -170.0, 0.0], [-170.0, 0.0, 170.0, 0.0]] {
            let lines = vp.project_line_features(&xy, &[0, 2], &[42]).unwrap();
            assert_eq!(lines.offsets, [0, 2, 4]);
            assert_eq!(lines.feature_ids, [42, 42]);
            let ranges = lines
                .xy
                .chunks_exact(4)
                .map(|segment| (segment[2] - segment[0]).abs())
                .collect::<Vec<_>>();
            assert!(ranges.iter().all(|&span| span < 20.0), "{ranges:?}");
            assert!(lines.xy.chunks_exact(2).all(|point| {
                let x = point[0] as f64 + lines.origin_x;
                x <= 16.0 || x >= vp.width - 16.0
            }));
        }
    }

    #[test]
    fn wrapped_multi_segment_route_keeps_shared_source_vertex_continuous() {
        let vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            -179.0,
            0.0,
            0.0,
            512.0,
            300.0,
            0.0,
            0.0,
            true,
        )
        .unwrap();
        let lines = vp
            .project_line_features(&[-10.0, 0.0, 0.0, 0.0, 170.0, 0.0], &[0, 3], &[7])
            .unwrap();
        assert_eq!(lines.offsets, [0, 2, 4]);
        assert_eq!(lines.feature_ids, [7, 7]);
        assert_eq!(lines.xy[2], lines.xy[4]);
        assert_eq!(lines.xy[3], lines.xy[5]);
    }

    #[test]
    fn empty_and_single_vertex_features_emit_nothing() {
        let vp = denver();
        let lines = vp
            .project_line_features(&[-105.0, 40.0], &[0, 0, 1], &[7, 9])
            .unwrap();
        assert!(lines.xy.is_empty());
        assert_eq!(lines.offsets, [0]);
        assert!(lines.feature_ids.is_empty());
    }

    #[test]
    fn line_projection_clips_and_preserves_visible_identity() {
        let vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            0.0,
            0.0,
            3.0,
            400.0,
            300.0,
            0.0,
            0.0,
            false,
        )
        .unwrap();
        let lines = vp
            .project_line_features(
                &[-30.0, 0.0, 30.0, 0.0, 100.0, 70.0, 110.0, 70.0],
                &[0, 2, 4],
                &[7, 9],
            )
            .unwrap();
        assert_eq!(lines.offsets, [0, 2]);
        assert_eq!(lines.feature_ids, [7]);
        let first_x = lines.xy[0] as f64 + lines.origin_x;
        let last_x = lines.xy[2] as f64 + lines.origin_x;
        assert_eq!(first_x, 0.0);
        assert_eq!(last_x, vp.width);
    }

    #[test]
    fn line_projection_rejects_bad_offsets_atomically() {
        let vp = denver();
        assert_eq!(
            vp.project_line_features(&[-105.0, 40.0, -104.0, 40.0], &[1, 2], &[1]),
            Err(GeoError::OffsetMismatch)
        );
        assert_eq!(
            vp.project_line_features(&[-105.0, 40.0, f64::NAN, 40.0], &[0, 2], &[1]),
            Err(GeoError::NonFiniteCoordinate)
        );
        assert_eq!(
            vp.project_line_features(
                &[-105.0, 40.0, -104.0, 40.0, -103.0, 40.0, f64::NAN, 40.0],
                &[0, 2, 4],
                &[1, 2],
            ),
            Err(GeoError::NonFiniteCoordinate)
        );
    }

    fn column(
        geometry: GeoGeometry,
        xy: &[f64],
        validity: &[u8],
        ids: Option<&[u64]>,
        offsets: [&[u32]; 3],
    ) -> GeoColumn {
        GeoColumn::from_descriptor(crate::geo::GeoDescriptor {
            geometry,
            crs: GeoCrs::Epsg4326,
            xy,
            validity,
            feature_ids: ids,
            offsets0: offsets[0],
            offsets1: offsets[1],
            offsets2: offsets[2],
            limits: GeoLimits::default(),
        })
        .unwrap()
    }

    #[test]
    fn project_column_points_are_offset_encoded_and_keep_feature_ids() {
        let vp = denver();
        let xy = [-104.9903, 39.7392, -104.9902, 39.7393];
        // Null point in the middle contributes no vertex and no ID.
        let col = column(
            GeoGeometry::Point,
            &xy,
            &[1, 0, 1],
            Some(&[10, 11, 12]),
            [&[], &[], &[]],
        );
        let projected = vp.project_column(&col).unwrap();
        let ProjectedGeoGeometry::Points(points) = &projected.geometry else {
            panic!("points expected");
        };
        assert_eq!(points.feature_ids, [10, 12]);
        assert_eq!(points.xy.len(), 4);
        assert_eq!((points.xy[0], points.xy[1]), (0.0, 0.0));
        let (sx, sy) = vp.project(xy[2], xy[3]).unwrap();
        assert!(((points.xy[2] as f64) - (sx - points.origin_x)).abs() < 1e-3);
        assert!(((points.xy[3] as f64) - (sy - points.origin_y)).abs() < 1e-3);
        assert!(points.xy.iter().all(|v| v.is_finite()));
        assert_eq!(projected.key.rebuild, vp.rebuild_key().unwrap());
        assert_eq!(projected.key.metadata_digest, col.metadata_digest());
    }

    #[test]
    fn offscreen_first_point_does_not_erase_visible_deep_zoom_detail() {
        let vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            0.0,
            0.0,
            24.0,
            800.0,
            600.0,
            0.0,
            0.0,
            true,
        )
        .unwrap();
        let col = column(
            GeoGeometry::Point,
            &[-180.0, 0.0, 0.0, 0.0, 1e-7, 0.0],
            &[1, 1, 1],
            Some(&[1, 2, 3]),
            [&[], &[], &[]],
        );
        let ProjectedGeoGeometry::Points(points) = vp.project_column(&col).unwrap().geometry else {
            panic!("points expected")
        };
        let separation = vp.project(1e-7, 0.0).unwrap().0 - vp.project(0.0, 0.0).unwrap().0;
        assert!(separation > 2.0);
        assert!(((points.xy[4] - points.xy[2]) as f64 - separation).abs() < 1e-6);
        assert_eq!((points.origin_x, points.origin_y), (400.0, 300.0));
        assert_eq!(points.feature_ids, [1, 2, 3]);
    }

    #[test]
    fn project_column_multipoint_repeats_owner_id_per_vertex() {
        let vp = denver();
        let xy = [-105.0, 39.7, -104.9, 39.8, -104.8, 39.9];
        let col = column(
            GeoGeometry::MultiPoint,
            &xy,
            &[1, 0, 1],
            Some(&[5, 6, 7]),
            [&[0, 2, 2, 3], &[], &[]],
        );
        let projected = vp.project_column(&col).unwrap();
        let ProjectedGeoGeometry::Points(points) = &projected.geometry else {
            panic!("points expected");
        };
        assert_eq!(points.feature_ids, [5, 5, 7]);
        assert_eq!(points.xy.len(), 6);
    }

    #[test]
    fn project_column_outlines_cover_lines_and_every_ring_with_ids() {
        let vp = GeoViewport::new(
            GeoCrs::Epsg4326,
            0.0,
            0.0,
            3.0,
            400.0,
            300.0,
            0.0,
            0.0,
            false,
        )
        .unwrap();
        // LineString: null feature is absent, IDs preserved.
        let line = column(
            GeoGeometry::LineString,
            &[-10.0, 0.0, 10.0, 0.0],
            &[0, 1],
            Some(&[3, 4]),
            [&[0, 0, 2], &[], &[]],
        );
        let ProjectedGeoGeometry::Outlines(lines) = vp.project_column(&line).unwrap().geometry
        else {
            panic!("outlines expected");
        };
        assert_eq!(lines.feature_ids, [4]);
        assert_eq!(lines.offsets, [0, 2]);

        // Polygon with a hole: 4 shell edges + 4 hole edges, all tagged 9.
        let mut xy = vec![
            -10.0, -10.0, 10.0, -10.0, 10.0, 10.0, -10.0, 10.0, -10.0, -10.0,
        ];
        xy.extend([-2.0, -2.0, -2.0, 2.0, 2.0, 2.0, 2.0, -2.0, -2.0, -2.0]);
        let polygon = column(
            GeoGeometry::Polygon,
            &xy,
            &[1],
            Some(&[9]),
            [&[0, 2], &[0, 5, 10], &[]],
        );
        let ProjectedGeoGeometry::Outlines(lines) = vp.project_column(&polygon).unwrap().geometry
        else {
            panic!("outlines expected");
        };
        assert_eq!(lines.feature_ids, [9; 8]);
        assert_eq!(lines.xy.len(), 8 * 4);
        assert!(lines.xy.iter().all(|v| v.is_finite()));

        // MultiPolygon: ids follow the owning feature across polygons.
        let mut xy = vec![
            -15.0, -10.0, -5.0, -10.0, -5.0, 10.0, -15.0, 10.0, -15.0, -10.0,
        ];
        xy.extend([5.0, -10.0, 15.0, -10.0, 15.0, 10.0, 5.0, 10.0, 5.0, -10.0]);
        let multi = column(
            GeoGeometry::MultiPolygon,
            &xy,
            &[1, 1],
            Some(&[70, 71]),
            [&[0, 1, 2], &[0, 1, 2], &[0, 5, 10]],
        );
        let ProjectedGeoGeometry::Outlines(lines) = vp.project_column(&multi).unwrap().geometry
        else {
            panic!("outlines expected");
        };
        assert_eq!(lines.feature_ids, [70, 70, 70, 70, 71, 71, 71, 71]);

        // MultiLineString: lines carry their feature id.
        let mls = column(
            GeoGeometry::MultiLineString,
            &[-10.0, 0.0, 0.0, 0.0, 0.0, 5.0, 10.0, 5.0],
            &[1],
            Some(&[8]),
            [&[0, 2], &[0, 2, 4], &[]],
        );
        let ProjectedGeoGeometry::Outlines(lines) = vp.project_column(&mls).unwrap().geometry
        else {
            panic!("outlines expected");
        };
        assert_eq!(lines.feature_ids, [8, 8]);
    }

    #[test]
    fn project_column_is_bit_reproducible_from_its_key() {
        let vp = denver();
        let col = column(
            GeoGeometry::LineString,
            &[-105.0, 39.7, -104.9, 39.8, -104.8, 39.75],
            &[1],
            None,
            [&[0, 3], &[], &[]],
        );
        let a = vp.project_column(&col).unwrap();
        let b = vp.project_column(&col.clone()).unwrap();
        assert_eq!(a.key, b.key);
        assert_eq!(a, b);

        // A moved camera changes the key; a changed column changes the key.
        let mut moved = vp;
        moved.set_zoom(11.0).unwrap();
        assert_ne!(moved.project_column(&col).unwrap().key, a.key);
        let other = column(
            GeoGeometry::LineString,
            &[-105.0, 39.7, -104.9, 39.8, -104.8, 39.76],
            &[1],
            None,
            [&[0, 3], &[], &[]],
        );
        assert_ne!(vp.project_column(&other).unwrap().key, a.key);
    }

    #[test]
    fn project_column_fails_before_output_on_bad_camera_or_crs() {
        let col = column(
            GeoGeometry::Point,
            &[-104.9903, 39.7392],
            &[1],
            None,
            [&[], &[], &[]],
        );
        let mut broken = denver();
        broken.zoom = f64::NAN;
        assert_eq!(
            broken.project_column(&col),
            Err(GeoError::NonFiniteCoordinate)
        );
        let mercator = GeoViewport::new(
            GeoCrs::Epsg3857,
            0.0,
            0.0,
            2.0,
            100.0,
            100.0,
            0.0,
            0.0,
            false,
        )
        .unwrap();
        assert_eq!(
            mercator.project_column(&col),
            Err(GeoError::InvalidArgument)
        );
    }
}
