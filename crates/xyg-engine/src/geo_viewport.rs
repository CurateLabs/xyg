//! Rust-owned geographic viewport / camera (#48).
//!
//! `GeoViewport` is the host-neutral projection authority for geographic
//! scenes: center, zoom, size, bearing, pitch, CRS, and world-wrap policy.
//! MapLibre (or any shell) may feed camera events; this module owns the
//! equations, polar clamp, and rebuildable f32 offset encoding policy.
//!
//! Basemap tile lifecycle is out of scope (#49). This module lowers and clips
//! antimeridian-safe route segments; polygon fill topology remains a follow-on.

use crate::geo::{GeoCrs, GeoError, GeoLimits};
use std::mem::size_of;

/// Spherical Web Mercator radius used by EPSG:3857 (metres).
const EARTH_RADIUS_M: f64 = 6_378_137.0;

/// Web Mercator half-world extent (EPSG:3857), metres.
pub const WEB_MERCATOR_MAX: f64 = 20_037_508.342_789_244;

/// Maximum absolute latitude accepted by Web Mercator (~85.05112878°).
pub const MAX_WEB_MERCATOR_LAT_DEG: f64 = 85.051_128_779_806_6;

/// MapLibre-compatible world tile size in CSS pixels at zoom 0.
const TILE_SIZE: f64 = 512.0;

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
    /// Pitch in degrees (0 = nadir). Stored for parity; projection is
    /// orthographic until the #49 MapLibre shell needs a matching frustum.
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
        if self.width <= 0.0 || self.height <= 0.0 {
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
    pub fn project(&self, x: f64, y: f64) -> Result<(f64, f64), GeoError> {
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

    /// Inverse of [`Self::project`].
    pub fn unproject(&self, screen_x: f64, screen_y: f64) -> Result<(f64, f64), GeoError> {
        if !screen_x.is_finite() || !screen_y.is_finite() {
            return Err(GeoError::NonFiniteCoordinate);
        }
        let (mx, my) = self.screen_to_mercator(screen_x, screen_y);
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

    /// Project source coordinates to offset-encoded f32 screen pixels.
    ///
    /// Returns interleaved `[sx0,sy0,…]` plus the f64 encode origin used so
    /// deep zoom stays precise (§4/§16). Non-finite inputs fail before output.
    pub fn project_offset_f32(&self, xy: &[f64]) -> Result<(Vec<f32>, f64, f64), GeoError> {
        if !xy.len().is_multiple_of(2) {
            return Err(GeoError::InvalidArgument);
        }
        let mut out = Vec::with_capacity(xy.len());
        let mut origin_x = 0.0;
        let mut origin_y = 0.0;
        let mut have_origin = false;
        for pair in xy.chunks_exact(2) {
            let (sx, sy) = self.project(pair[0], pair[1])?;
            if !have_origin {
                origin_x = sx;
                origin_y = sy;
                have_origin = true;
            }
            out.push((sx - origin_x) as f32);
            out.push((sy - origin_y) as f32);
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
                    let Some((a, b)) = clip_segment(a, b, self.width, self.height) else {
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
        self.zoom = zoom_x.min(zoom_y).clamp(0.0, 24.0);

        let mid_mx = 0.5 * (min_mx + max_mx);
        let mid_my = 0.5 * (min_my + max_my);
        match self.crs {
            GeoCrs::Epsg4326 => {
                let (lon, lat) = mercator_to_lonlat(mid_mx, mid_my);
                self.center_x = normalize_lon(lon);
                self.center_y = lat;
            }
            GeoCrs::Epsg3857 => {
                self.center_x = mid_mx;
                self.center_y = mid_my;
            }
        }
        self.bearing_deg = 0.0;
        self.validate()
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

    /// Set pitch in the certified orthographic range `[-60, 60]` degrees.
    ///
    /// Pitch is frozen for shell/headless parity; perspective projection stays
    /// explicitly deferred to the MapLibre frustum work in #49.
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
        if !delta_x.is_finite() || !delta_y.is_finite() {
            return Err(GeoError::NonFiniteCoordinate);
        }
        if delta_x == 0.0 && delta_y == 0.0 {
            return Ok(());
        }
        let (mut mx, my) =
            self.screen_to_mercator(self.width * 0.5 + delta_x, self.height * 0.5 + delta_y);
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
                next.center_x = lon;
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
    #[must_use]
    pub fn rebuild_key(&self) -> GeoViewportRebuildKey {
        let center_x = if self.crs == GeoCrs::Epsg4326 && self.world_wrap {
            normalize_lon(self.center_x)
        } else {
            self.center_x
        };
        GeoViewportRebuildKey {
            crs: self.crs,
            center_x_bits: canonical_f64_bits(center_x),
            center_y_bits: canonical_f64_bits(self.center_y),
            zoom_bits: canonical_f64_bits(self.zoom),
            width_bits: canonical_f64_bits(self.width),
            height_bits: canonical_f64_bits(self.height),
            bearing_deg_bits: canonical_f64_bits(normalize_bearing(self.bearing_deg)),
            pitch_deg_bits: canonical_f64_bits(self.pitch_deg),
            world_wrap: self.world_wrap,
        }
    }

    fn mercator_to_screen(&self, mx: f64, my: f64) -> (f64, f64) {
        let (cx, cy) = self.center_mercator();
        let scale = 1.0 / self.metres_per_pixel();
        let mut dx_m = mx - cx;
        if self.crs == GeoCrs::Epsg4326 && self.world_wrap {
            let world_m = 2.0 * WEB_MERCATOR_MAX;
            dx_m -= (dx_m / world_m).round() * world_m;
        }
        let mut dx = dx_m * scale;
        let mut dy = (cy - my) * scale; // screen +y is down
        let bearing_deg = normalize_bearing(self.bearing_deg);
        if bearing_deg != 0.0 {
            // A positive camera bearing is a clockwise heading, so map
            // content rotates by the opposite angle (MapLibre convention).
            let rad = (-bearing_deg).to_radians();
            let (sin_b, cos_b) = (rad.sin(), rad.cos());
            let rx = dx * cos_b - dy * sin_b;
            let ry = dx * sin_b + dy * cos_b;
            dx = rx;
            dy = ry;
        }
        (self.width * 0.5 + dx, self.height * 0.5 + dy)
    }

    fn screen_to_mercator(&self, screen_x: f64, screen_y: f64) -> (f64, f64) {
        let mut dx = screen_x - self.width * 0.5;
        let mut dy = screen_y - self.height * 0.5;
        let bearing_deg = normalize_bearing(self.bearing_deg);
        if bearing_deg != 0.0 {
            let rad = bearing_deg.to_radians();
            let (sin_b, cos_b) = (rad.sin(), rad.cos());
            let rx = dx * cos_b - dy * sin_b;
            let ry = dx * sin_b + dy * cos_b;
            dx = rx;
            dy = ry;
        }
        let scale = self.metres_per_pixel();
        let (cx, cy) = self.center_mercator();
        (cx + dx * scale, cy - dy * scale)
    }

    /// Project both endpoints into one coherent wrapped-world copy. Projecting
    /// them independently makes exactly +180 degrees jump to the opposite
    /// screen edge while a nearby +170 degree point remains on the right.
    fn project_line_segment(
        &self,
        segment: [f64; 4],
        preferred_start_lon: Option<f64>,
    ) -> Result<(ScreenSegment, Option<f64>), GeoError> {
        if self.crs != GeoCrs::Epsg4326 || !self.world_wrap {
            return Ok((
                (
                    self.project(segment[0], segment[1])?,
                    self.project(segment[2], segment[3])?,
                ),
                None,
            ));
        }

        let midpoint_lon = 0.5 * (segment[0] + segment[2]);
        let world_turns = preferred_start_lon.map_or_else(
            || ((self.center_x - midpoint_lon) / 360.0).round(),
            |prior| ((prior - segment[0]) / 360.0).round(),
        );
        let project_unwrapped = |lon: f64, lat: f64| {
            let mx = EARTH_RADIUS_M * (lon + world_turns * 360.0).to_radians();
            let (_, my) = lonlat_to_mercator(0.0, lat);
            self.mercator_to_screen_unwrapped(mx, my)
        };
        Ok((
            (
                project_unwrapped(segment[0], segment[1]),
                project_unwrapped(segment[2], segment[3]),
            ),
            Some(segment[2] + world_turns * 360.0),
        ))
    }

    fn mercator_to_screen_unwrapped(&self, mx: f64, my: f64) -> (f64, f64) {
        let (cx, cy) = self.center_mercator();
        let scale = 1.0 / self.metres_per_pixel();
        let mut dx = (mx - cx) * scale;
        let mut dy = (cy - my) * scale;
        let bearing_deg = normalize_bearing(self.bearing_deg);
        if bearing_deg != 0.0 {
            let rad = (-bearing_deg).to_radians();
            let (sin_b, cos_b) = (rad.sin(), rad.cos());
            let rx = dx * cos_b - dy * sin_b;
            let ry = dx * sin_b + dy * cos_b;
            dx = rx;
            dy = ry;
        }
        (self.width * 0.5 + dx, self.height * 0.5 + dy)
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
    if crs != GeoCrs::Epsg4326 || !world_wrap || (x1 - x0).abs() <= 180.0 {
        return ([[x0, y0, x1, y1], [0.0; 4]], 1);
    }
    let (unwrapped_x1, boundary, opposite) = if x1 < x0 {
        (x1 + 360.0, 180.0, -180.0)
    } else {
        (x1 - 360.0, -180.0, 180.0)
    };
    let t = (boundary - x0) / (unwrapped_x1 - x0);
    let y_cross = y0 + (y1 - y0) * t;
    (
        [[x0, y0, boundary, y_cross], [opposite, y_cross, x1, y1]],
        2,
    )
}

/// Liang–Barsky clip against the viewport. The arithmetic is f64 and output
/// is emitted only after all bounds are proven finite.
fn clip_segment(a: ScreenPoint, b: ScreenPoint, width: f64, height: f64) -> Option<ScreenSegment> {
    let (dx, dy) = (b.0 - a.0, b.1 - a.1);
    let mut t0: f64 = 0.0;
    let mut t1: f64 = 1.0;
    for (p, q) in [
        (-dx, a.0),
        (dx, width - a.0),
        (-dy, a.1),
        (dy, height - a.1),
    ] {
        if p == 0.0 {
            if q < 0.0 {
                return None;
            }
            continue;
        }
        let r = q / p;
        if p < 0.0 {
            t0 = t0.max(r);
        } else {
            t1 = t1.min(r);
        }
        if t0 > t1 {
            return None;
        }
    }
    Some((
        (a.0 + t0 * dx, a.1 + t0 * dy),
        (a.0 + t1 * dx, a.1 + t1 * dy),
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
}
