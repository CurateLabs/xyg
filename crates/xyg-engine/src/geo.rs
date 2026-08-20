//! Rust-owned geographic columns (`GeoColumn`) for GraphForge GeoArrow ingress.
//!
//! Hosts decode Arrow / GeoArrow at their boundary and hand XYG a typed
//! descriptor: interleaved f64 XY, optional per-feature validity, nested
//! `u32` offset planes, and optional feature IDs. This module owns CRS
//! interpretation, geometry validation, source f64 retention, and feature
//! identity. It does **not** depend on an Arrow crate — browser/WASM and
//! native hosts share the same descriptor contract (#47, #59).
//!
//! Certified CRS profile for v1: EPSG:4326 and EPSG:3857 only. Unsupported
//! CRS fails before a column is published. Derived f32 scene buffers are
//! rebuildable caches (§27) and are not stored here.

use std::collections::HashMap;
use std::sync::{Arc, Mutex, OnceLock};

/// Web Mercator half-world extent (EPSG:3857), metres.
const WEB_MERCATOR_MAX: f64 = 20_037_508.342_789_244;

/// Resource ceilings applied before a column is accepted.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoLimits {
    /// Maximum top-level features (including nulls).
    pub max_features: usize,
    /// Maximum coordinate vertices across the column.
    pub max_vertices: usize,
    /// Maximum retained payload bytes (xy + offsets + validity + ids).
    pub max_bytes: usize,
}

impl Default for GeoLimits {
    fn default() -> Self {
        Self {
            max_features: 1_000_000,
            max_vertices: 10_000_000,
            max_bytes: 256 * 1024 * 1024,
        }
    }
}

/// Stable, value-safe validation failures. Messages never contain coordinates.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(i32)]
pub enum GeoError {
    InvalidArgument = -1,
    UnsupportedCrs = -2,
    TypeMismatch = -3,
    OffsetMismatch = -4,
    NullChild = -5,
    NonFiniteCoordinate = -6,
    CoordinateOutOfRange = -7,
    RingNotClosed = -8,
    ResourceLimit = -9,
    StaleHandle = -10,
}

impl GeoError {
    /// Stable public error code safe to log or cross the ABI.
    #[must_use]
    pub const fn code(self) -> &'static str {
        match self {
            Self::InvalidArgument => "XYG_GEO_INVALID_ARGUMENT",
            Self::UnsupportedCrs => "XYG_GEO_UNSUPPORTED_CRS",
            Self::TypeMismatch => "XYG_GEO_TYPE_MISMATCH",
            Self::OffsetMismatch => "XYG_GEO_OFFSET_MISMATCH",
            Self::NullChild => "XYG_GEO_NULL_CHILD",
            Self::NonFiniteCoordinate => "XYG_GEO_NON_FINITE_COORDINATE",
            Self::CoordinateOutOfRange => "XYG_GEO_COORDINATE_OUT_OF_RANGE",
            Self::RingNotClosed => "XYG_GEO_RING_NOT_CLOSED",
            Self::ResourceLimit => "XYG_GEO_RESOURCE_LIMIT",
            Self::StaleHandle => "XYG_GEO_STALE_HANDLE",
        }
    }

    /// Human message without coordinate values.
    #[must_use]
    pub const fn message(self) -> &'static str {
        match self {
            Self::InvalidArgument => "geographic descriptor is incomplete or inconsistent",
            Self::UnsupportedCrs => "CRS is not in the certified EPSG:4326 / EPSG:3857 profile",
            Self::TypeMismatch => "geometry kind does not match the supplied offset planes",
            Self::OffsetMismatch => "offset planes are malformed or disagree with vertex counts",
            Self::NullChild => "nested geometry parts cannot be null",
            Self::NonFiniteCoordinate => "coordinate is non-finite",
            Self::CoordinateOutOfRange => "coordinate is outside the declared CRS bounds",
            Self::RingNotClosed => "polygon ring is too short or not closed",
            Self::ResourceLimit => "geometry exceeds feature, vertex, or byte limits",
            Self::StaleHandle => "geographic column handle is stale or freed",
        }
    }
}

/// Certified CRS values for geospatial v1.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[repr(u32)]
pub enum GeoCrs {
    /// WGS 84 longitude/latitude, canonical x/y order.
    Epsg4326 = 4326,
    /// Web Mercator easting/northing, canonical x/y order.
    Epsg3857 = 3857,
}

impl GeoCrs {
    #[must_use]
    pub const fn authority_code(self) -> &'static str {
        match self {
            Self::Epsg4326 => "EPSG:4326",
            Self::Epsg3857 => "EPSG:3857",
        }
    }

    /// Canonical GeoArrow extension metadata JSON (`authority_code` form).
    #[must_use]
    pub fn extension_metadata(self) -> String {
        format!(
            "{{\"crs\":\"{}\",\"crs_type\":\"authority_code\"}}",
            self.authority_code()
        )
    }

    #[must_use]
    pub fn parse(code: &str) -> Option<Self> {
        match code {
            "EPSG:4326" | "4326" => Some(Self::Epsg4326),
            "EPSG:3857" | "3857" => Some(Self::Epsg3857),
            _ => None,
        }
    }

    #[must_use]
    pub fn from_u32(code: u32) -> Option<Self> {
        match code {
            4326 => Some(Self::Epsg4326),
            3857 => Some(Self::Epsg3857),
            _ => None,
        }
    }
}

/// Homogeneous two-dimensional GeoArrow geometry kinds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[repr(u32)]
pub enum GeoGeometry {
    Point = 1,
    LineString = 2,
    Polygon = 3,
    MultiPoint = 4,
    MultiLineString = 5,
    MultiPolygon = 6,
}

impl GeoGeometry {
    #[must_use]
    pub const fn extension_name(self) -> &'static str {
        match self {
            Self::Point => "geoarrow.point",
            Self::LineString => "geoarrow.linestring",
            Self::Polygon => "geoarrow.polygon",
            Self::MultiPoint => "geoarrow.multipoint",
            Self::MultiLineString => "geoarrow.multilinestring",
            Self::MultiPolygon => "geoarrow.multipolygon",
        }
    }

    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Point => "point",
            Self::LineString => "linestring",
            Self::Polygon => "polygon",
            Self::MultiPoint => "multipoint",
            Self::MultiLineString => "multilinestring",
            Self::MultiPolygon => "multipolygon",
        }
    }

    /// Number of nested List offset planes required by the descriptor.
    #[must_use]
    pub const fn offset_depth(self) -> usize {
        match self {
            Self::Point => 0,
            Self::LineString | Self::MultiPoint => 1,
            Self::Polygon | Self::MultiLineString => 2,
            Self::MultiPolygon => 3,
        }
    }

    #[must_use]
    pub fn from_u32(value: u32) -> Option<Self> {
        match value {
            1 => Some(Self::Point),
            2 => Some(Self::LineString),
            3 => Some(Self::Polygon),
            4 => Some(Self::MultiPoint),
            5 => Some(Self::MultiLineString),
            6 => Some(Self::MultiPolygon),
            _ => None,
        }
    }
}

/// Borrowed host descriptor for one homogeneous geographic column.
#[derive(Debug, Clone, Copy)]
pub struct GeoDescriptor<'a> {
    pub geometry: GeoGeometry,
    pub crs: GeoCrs,
    /// Interleaved `[x0, y0, x1, y1, …]` source coordinates (f64).
    pub xy: &'a [f64],
    /// Per-feature validity (`1` = present, `0` = null). Length = feature count.
    pub validity: &'a [u8],
    /// Optional explicit feature IDs; when omitted, IDs are `0..n`.
    pub feature_ids: Option<&'a [u64]>,
    /// Outermost list offsets (`n_features + 1`), empty for `Point`.
    pub offsets0: &'a [u32],
    /// Second nesting level offsets, empty when unused.
    pub offsets1: &'a [u32],
    /// Third nesting level offsets, empty when unused.
    pub offsets2: &'a [u32],
    pub limits: GeoLimits,
}

/// Validated, retained geographic column (canonical f64 geometry).
#[derive(Debug, Clone)]
pub struct GeoColumn {
    geometry: GeoGeometry,
    crs: GeoCrs,
    xy: Vec<f64>,
    validity: Vec<u8>,
    feature_ids: Vec<u64>,
    offsets0: Vec<u32>,
    offsets1: Vec<u32>,
    offsets2: Vec<u32>,
}

impl GeoColumn {
    /// Validate and copy a host descriptor into an owned column.
    pub fn from_descriptor(desc: GeoDescriptor<'_>) -> Result<Self, GeoError> {
        let n_features = desc.validity.len();
        if n_features > desc.limits.max_features {
            return Err(GeoError::ResourceLimit);
        }
        if !desc.xy.len().is_multiple_of(2) {
            return Err(GeoError::InvalidArgument);
        }
        let n_vertices = desc.xy.len() / 2;
        if n_vertices > desc.limits.max_vertices {
            return Err(GeoError::ResourceLimit);
        }
        if let Some(ids) = desc.feature_ids {
            if ids.len() != n_features {
                return Err(GeoError::InvalidArgument);
            }
        }
        for &flag in desc.validity {
            if flag > 1 {
                return Err(GeoError::InvalidArgument);
            }
        }

        validate_offset_planes(desc.geometry, n_features, n_vertices, desc)?;
        validate_coordinates(desc.xy, desc.crs)?;
        if matches!(
            desc.geometry,
            GeoGeometry::Polygon | GeoGeometry::MultiPolygon
        ) {
            validate_rings(desc)?;
        }

        let payload_bytes = desc.xy.len() * 8
            + desc.validity.len()
            + desc.offsets0.len() * 4
            + desc.offsets1.len() * 4
            + desc.offsets2.len() * 4
            + desc
                .feature_ids
                .map(|ids| ids.len() * 8)
                .unwrap_or(n_features * 8);
        if payload_bytes > desc.limits.max_bytes {
            return Err(GeoError::ResourceLimit);
        }

        let feature_ids = match desc.feature_ids {
            Some(ids) => ids.to_vec(),
            None => (0..n_features as u64).collect(),
        };

        Ok(Self {
            geometry: desc.geometry,
            crs: desc.crs,
            xy: desc.xy.to_vec(),
            validity: desc.validity.to_vec(),
            feature_ids,
            offsets0: desc.offsets0.to_vec(),
            offsets1: desc.offsets1.to_vec(),
            offsets2: desc.offsets2.to_vec(),
        })
    }

    #[must_use]
    pub fn geometry(&self) -> GeoGeometry {
        self.geometry
    }

    #[must_use]
    pub fn crs(&self) -> GeoCrs {
        self.crs
    }

    #[must_use]
    pub fn len(&self) -> usize {
        self.validity.len()
    }

    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.validity.is_empty()
    }

    #[must_use]
    pub fn vertex_count(&self) -> usize {
        self.xy.len() / 2
    }

    #[must_use]
    pub fn xy(&self) -> &[f64] {
        &self.xy
    }

    #[must_use]
    pub fn validity(&self) -> &[u8] {
        &self.validity
    }

    #[must_use]
    pub fn feature_ids(&self) -> &[u64] {
        &self.feature_ids
    }

    #[must_use]
    pub fn offsets0(&self) -> &[u32] {
        &self.offsets0
    }

    #[must_use]
    pub fn offsets1(&self) -> &[u32] {
        &self.offsets1
    }

    #[must_use]
    pub fn offsets2(&self) -> &[u32] {
        &self.offsets2
    }

    #[must_use]
    pub fn extension_name(&self) -> &'static str {
        self.geometry.extension_name()
    }

    #[must_use]
    pub fn extension_metadata(&self) -> String {
        self.crs.extension_metadata()
    }
}

fn validate_offset_planes(
    geometry: GeoGeometry,
    n_features: usize,
    n_vertices: usize,
    desc: GeoDescriptor<'_>,
) -> Result<(), GeoError> {
    let depth = geometry.offset_depth();
    let planes = [desc.offsets0, desc.offsets1, desc.offsets2];
    for (i, plane) in planes.iter().enumerate() {
        if i < depth {
            if plane.is_empty() {
                return Err(GeoError::TypeMismatch);
            }
        } else if !plane.is_empty() {
            return Err(GeoError::TypeMismatch);
        }
    }

    match geometry {
        GeoGeometry::Point => {
            let expected = desc.validity.iter().filter(|&&v| v == 1).count();
            if n_vertices != expected {
                return Err(GeoError::OffsetMismatch);
            }
            Ok(())
        }
        GeoGeometry::LineString | GeoGeometry::MultiPoint => {
            check_offsets(desc.offsets0, n_features, n_vertices as u32)
        }
        GeoGeometry::Polygon | GeoGeometry::MultiLineString => {
            check_offsets(desc.offsets0, n_features, (desc.offsets1.len() - 1) as u32)?;
            check_offsets(desc.offsets1, desc.offsets1.len() - 1, n_vertices as u32)
        }
        GeoGeometry::MultiPolygon => {
            check_offsets(desc.offsets0, n_features, (desc.offsets1.len() - 1) as u32)?;
            check_offsets(
                desc.offsets1,
                desc.offsets1.len() - 1,
                (desc.offsets2.len() - 1) as u32,
            )?;
            check_offsets(desc.offsets2, desc.offsets2.len() - 1, n_vertices as u32)
        }
    }
}

fn check_offsets(offsets: &[u32], n_items: usize, end_max: u32) -> Result<(), GeoError> {
    if offsets.len() != n_items + 1 {
        return Err(GeoError::OffsetMismatch);
    }
    if offsets[0] != 0 {
        return Err(GeoError::OffsetMismatch);
    }
    for window in offsets.windows(2) {
        if window[1] < window[0] {
            return Err(GeoError::OffsetMismatch);
        }
    }
    if *offsets.last().unwrap_or(&0) != end_max {
        return Err(GeoError::OffsetMismatch);
    }
    Ok(())
}

fn validate_coordinates(xy: &[f64], crs: GeoCrs) -> Result<(), GeoError> {
    for pair in xy.chunks_exact(2) {
        let (x, y) = (pair[0], pair[1]);
        if !x.is_finite() || !y.is_finite() {
            return Err(GeoError::NonFiniteCoordinate);
        }
        let in_range = match crs {
            GeoCrs::Epsg4326 => (-180.0..=180.0).contains(&x) && (-90.0..=90.0).contains(&y),
            GeoCrs::Epsg3857 => {
                (-WEB_MERCATOR_MAX..=WEB_MERCATOR_MAX).contains(&x)
                    && (-WEB_MERCATOR_MAX..=WEB_MERCATOR_MAX).contains(&y)
            }
        };
        if !in_range {
            return Err(GeoError::CoordinateOutOfRange);
        }
    }
    Ok(())
}

fn validate_rings(desc: GeoDescriptor<'_>) -> Result<(), GeoError> {
    let ring_offsets = match desc.geometry {
        GeoGeometry::Polygon => desc.offsets1,
        GeoGeometry::MultiPolygon => desc.offsets2,
        _ => return Ok(()),
    };
    for window in ring_offsets.windows(2) {
        let start = window[0] as usize;
        let end = window[1] as usize;
        if end < start {
            return Err(GeoError::OffsetMismatch);
        }
        let count = end - start;
        if count == 0 {
            return Err(GeoError::NullChild);
        }
        if count < 4 {
            return Err(GeoError::RingNotClosed);
        }
        let i0 = start * 2;
        let i1 = (end - 1) * 2;
        if desc.xy[i0].to_bits() != desc.xy[i1].to_bits()
            || desc.xy[i0 + 1].to_bits() != desc.xy[i1 + 1].to_bits()
        {
            return Err(GeoError::RingNotClosed);
        }
    }
    Ok(())
}

// --- Opaque handle registry (engine doc §3.3) --------------------------------

type Registry = (u64, HashMap<u64, Arc<GeoColumn>>);

fn registry() -> &'static Mutex<Registry> {
    static REG: OnceLock<Mutex<Registry>> = OnceLock::new();
    REG.get_or_init(|| Mutex::new((1, HashMap::new())))
}

pub fn reg_insert(col: GeoColumn) -> u64 {
    let mut guard = registry().lock().expect("geo registry lock");
    let id = guard.0;
    guard.0 = guard.0.wrapping_add(1).max(1);
    guard.1.insert(id, Arc::new(col));
    id
}

pub fn reg_with<R>(h: u64, f: impl FnOnce(&GeoColumn) -> R) -> Option<R> {
    let guard = registry().lock().expect("geo registry lock");
    guard.1.get(&h).map(|col| f(col))
}

pub fn reg_free(h: u64) -> Result<(), GeoError> {
    let mut guard = registry().lock().expect("geo registry lock");
    if guard.1.remove(&h).is_some() {
        Ok(())
    } else {
        Err(GeoError::StaleHandle)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn point_denver() -> GeoDescriptor<'static> {
        // GraphForge geoarrow-interchange-v1 "point" fixture.
        GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg4326,
            xy: &[-104.9903, 39.7392],
            validity: &[1],
            feature_ids: None,
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        }
    }

    #[test]
    fn point_fixture_round_trips_metadata() {
        let col = GeoColumn::from_descriptor(point_denver()).unwrap();
        assert_eq!(col.geometry(), GeoGeometry::Point);
        assert_eq!(col.crs(), GeoCrs::Epsg4326);
        assert_eq!(col.extension_name(), "geoarrow.point");
        assert_eq!(
            col.extension_metadata(),
            "{\"crs\":\"EPSG:4326\",\"crs_type\":\"authority_code\"}"
        );
        assert_eq!(col.feature_ids(), &[0]);
        assert_eq!(col.xy(), &[-104.9903, 39.7392]);
    }

    #[test]
    fn mercator_point_accepted() {
        let desc = GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg3857,
            xy: &[-11_687_469.0, 4_825_942.0],
            validity: &[1],
            feature_ids: Some(&[42]),
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        };
        let col = GeoColumn::from_descriptor(desc).unwrap();
        assert_eq!(col.feature_ids(), &[42]);
        assert_eq!(col.crs().authority_code(), "EPSG:3857");
    }

    #[test]
    fn linestring_fixture_preserves_vertices() {
        let desc = GeoDescriptor {
            geometry: GeoGeometry::LineString,
            crs: GeoCrs::Epsg4326,
            xy: &[-105.0, 39.7, -104.9, 39.8],
            validity: &[1],
            feature_ids: None,
            offsets0: &[0, 2],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        };
        let col = GeoColumn::from_descriptor(desc).unwrap();
        assert_eq!(col.vertex_count(), 2);
        assert_eq!(col.offsets0(), &[0, 2]);
    }

    #[test]
    fn polygon_fixture_requires_closed_ring() {
        let good = GeoDescriptor {
            geometry: GeoGeometry::Polygon,
            crs: GeoCrs::Epsg4326,
            xy: &[-105.0, 39.7, -104.9, 39.7, -104.9, 39.8, -105.0, 39.7],
            validity: &[1],
            feature_ids: None,
            offsets0: &[0, 1],
            offsets1: &[0, 4],
            offsets2: &[],
            limits: GeoLimits::default(),
        };
        assert!(GeoColumn::from_descriptor(good).is_ok());

        let open = GeoDescriptor {
            geometry: GeoGeometry::Polygon,
            crs: GeoCrs::Epsg4326,
            xy: &[-105.0, 39.7, -104.9, 39.7, -104.9, 39.8, -105.0, 39.71],
            validity: &[1],
            feature_ids: None,
            offsets0: &[0, 1],
            offsets1: &[0, 4],
            offsets2: &[],
            limits: GeoLimits::default(),
        };
        let err = GeoColumn::from_descriptor(open).unwrap_err();
        assert_eq!(err, GeoError::RingNotClosed);
        assert_eq!(err.code(), "XYG_GEO_RING_NOT_CLOSED");
        assert!(!err.message().contains("105"));
    }

    #[test]
    fn multipolygon_fixture_ingests() {
        let desc = GeoDescriptor {
            geometry: GeoGeometry::MultiPolygon,
            crs: GeoCrs::Epsg4326,
            xy: &[-105.0, 39.7, -104.9, 39.7, -104.9, 39.8, -105.0, 39.7],
            validity: &[1],
            feature_ids: None,
            offsets0: &[0, 1],
            offsets1: &[0, 1],
            offsets2: &[0, 4],
            limits: GeoLimits::default(),
        };
        let col = GeoColumn::from_descriptor(desc).unwrap();
        assert_eq!(col.geometry(), GeoGeometry::MultiPolygon);
        assert_eq!(col.vertex_count(), 4);
    }

    #[test]
    fn rejects_non_finite_and_out_of_range_without_leaking_values() {
        let nan = GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg4326,
            xy: &[f64::NAN, 0.0],
            validity: &[1],
            feature_ids: None,
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        };
        let err = GeoColumn::from_descriptor(nan).unwrap_err();
        assert_eq!(err.code(), "XYG_GEO_NON_FINITE_COORDINATE");
        assert!(!err.message().contains("NaN"));

        let oob = GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg4326,
            xy: &[181.0, 0.0],
            validity: &[1],
            feature_ids: None,
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        };
        let err = GeoColumn::from_descriptor(oob).unwrap_err();
        assert_eq!(err.code(), "XYG_GEO_COORDINATE_OUT_OF_RANGE");
        assert!(!err.message().contains("181"));
    }

    #[test]
    fn unsupported_crs_parser_and_limits() {
        assert_eq!(GeoCrs::parse("EPSG:26915"), None);
        let desc = GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg4326,
            xy: &[0.0, 0.0],
            validity: &[1],
            feature_ids: None,
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits {
                max_features: 0,
                ..GeoLimits::default()
            },
        };
        assert_eq!(
            GeoColumn::from_descriptor(desc).unwrap_err(),
            GeoError::ResourceLimit
        );
    }

    #[test]
    fn null_point_contributes_no_vertex() {
        let desc = GeoDescriptor {
            geometry: GeoGeometry::Point,
            crs: GeoCrs::Epsg4326,
            xy: &[-104.9903, 39.7392],
            validity: &[1, 0],
            feature_ids: Some(&[10, 11]),
            offsets0: &[],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        };
        let col = GeoColumn::from_descriptor(desc).unwrap();
        assert_eq!(col.len(), 2);
        assert_eq!(col.vertex_count(), 1);
        assert_eq!(col.validity(), &[1, 0]);
    }

    #[test]
    fn registry_insert_and_free() {
        let h = reg_insert(GeoColumn::from_descriptor(point_denver()).unwrap());
        assert!(reg_with(h, |c| c.len() == 1).unwrap());
        assert!(reg_free(h).is_ok());
        assert_eq!(reg_free(h), Err(GeoError::StaleHandle));
    }
}
