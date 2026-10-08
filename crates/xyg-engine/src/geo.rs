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

use crate::transition::Blake2s8;
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
    /// Maximum retained payload bytes (xy + offsets + validity + ids + ring
    /// orientations).
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
    HoleOutsideShell = -11,
    DegenerateGeometry = -12,
    OutputCapacity = -13,
    NullFeatureNotEmpty = -14,
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
            Self::HoleOutsideShell => "XYG_GEO_HOLE_OUTSIDE_SHELL",
            Self::DegenerateGeometry => "XYG_GEO_DEGENERATE_GEOMETRY",
            Self::OutputCapacity => "XYG_GEO_OUTPUT_CAPACITY",
            Self::NullFeatureNotEmpty => "XYG_GEO_NULL_FEATURE_NOT_EMPTY",
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
            Self::HoleOutsideShell => "interior ring is not contained by its exterior ring",
            Self::DegenerateGeometry => "line part has one vertex or ring has zero area",
            Self::OutputCapacity => "host output buffer is smaller than the column",
            Self::NullFeatureNotEmpty => "null feature must not own vertices or parts",
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

/// Decode the bounded `XYGD` v1 ingress without alignment assumptions or unsafe casts.
/// Header: magic, version/kind/CRS/flags/reserved u32, followed by five u64
/// lengths (features, vertices, offsets0/1/2). Each plane starts at 8-byte alignment.
/// Rust validates the exact framing and peak budget before allocating typed planes.
pub fn column_from_descriptor_bytes(
    bytes: &[u8],
    peak_budget: usize,
) -> Result<GeoColumn, GeoError> {
    let invalid = GeoError::InvalidArgument;
    if bytes.len() < 64 || &bytes[..4] != b"XYGD" {
        return Err(invalid);
    }
    let u32_at = |i| u32::from_le_bytes(bytes[i..i + 4].try_into().unwrap());
    if u32_at(4) != 1 || u32_at(16) > 1 || u32_at(20) != 0 {
        return Err(invalid);
    }
    let geometry = GeoGeometry::from_u32(u32_at(8)).ok_or(GeoError::TypeMismatch)?;
    let crs = GeoCrs::from_u32(u32_at(12)).ok_or(GeoError::UnsupportedCrs)?;
    let mut lengths = [0usize; 5];
    for (i, value) in lengths.iter_mut().enumerate() {
        *value = usize::try_from(u64::from_le_bytes(
            bytes[24 + i * 8..32 + i * 8].try_into().unwrap(),
        ))
        .map_err(|_| invalid)?;
    }
    let [features, vertices, o0, o1, o2] = lengths;
    let xy_len = vertices.checked_mul(2).ok_or(invalid)?;
    validate_descriptor_lengths(
        geometry,
        xy_len,
        features,
        [o0, o1, o2],
        GeoLimits::default(),
    )?;
    let counts = [
        xy_len,
        features,
        if u32_at(16) == 1 { features } else { 0 },
        o0,
        o1,
        o2,
    ];
    let sizes = [8usize, 1, 8, 4, 4, 4];
    let mut cursor = 64usize;
    let mut ranges = [(0usize, 0usize); 6];
    for i in 0..6 {
        let end = counts[i]
            .checked_mul(sizes[i])
            .and_then(|n| cursor.checked_add(n))
            .ok_or(invalid)?;
        let padded = end.checked_add(7).map(|n| n & !7).ok_or(invalid)?;
        if padded > bytes.len() || bytes[end..padded].iter().any(|&b| b != 0) {
            return Err(invalid);
        }
        ranges[i] = (cursor, end);
        cursor = padded;
    }
    if cursor != bytes.len() {
        return Err(invalid);
    }
    // Transferred JavaScript source + Rust staging + decoded numeric planes + retained column. IDs
    // generated for omitted source identities still cost eight bytes per
    // feature, including all-null Point columns with no coordinate plane.
    let numeric = xy_len
        .checked_mul(8)
        .and_then(|n| {
            [o0, o1, o2].into_iter().try_fold(n, |sum, len| {
                len.checked_mul(4).and_then(|n| sum.checked_add(n))
            })
        })
        .ok_or(GeoError::ResourceLimit)?;
    let decoded = numeric
        .checked_add(if u32_at(16) == 1 {
            features.checked_mul(8).ok_or(GeoError::ResourceLimit)?
        } else {
            0
        })
        .ok_or(GeoError::ResourceLimit)?;
    let rings = match geometry {
        GeoGeometry::Polygon => o1.saturating_sub(1),
        GeoGeometry::MultiPolygon => o2.saturating_sub(1),
        _ => 0,
    };
    let retained = features
        .checked_mul(9)
        .and_then(|n| n.checked_add(numeric))
        .and_then(|n| n.checked_add(rings))
        .ok_or(GeoError::ResourceLimit)?;
    // Fixed allowance covers metadata cache + returned clone, validation stack
    // (including digest chunk buffers), and small Vec / extension strings.
    let peak = bytes
        .len()
        .checked_mul(2)
        .and_then(|n| n.checked_add(decoded))
        .and_then(|n| n.checked_add(retained))
        .and_then(|n| n.checked_add(8192))
        .ok_or(GeoError::ResourceLimit)?;
    if peak > peak_budget {
        return Err(GeoError::ResourceLimit);
    }
    let plane = |i: usize| &bytes[ranges[i].0..ranges[i].1];
    let xy: Vec<f64> = plane(0)
        .chunks_exact(8)
        .map(|b| f64::from_le_bytes(b.try_into().unwrap()))
        .collect();
    let ids: Vec<u64> = plane(2)
        .chunks_exact(8)
        .map(|b| u64::from_le_bytes(b.try_into().unwrap()))
        .collect();
    let offsets: Vec<Vec<u32>> = (3..6)
        .map(|i| {
            plane(i)
                .chunks_exact(4)
                .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
                .collect()
        })
        .collect();
    GeoColumn::from_descriptor(GeoDescriptor {
        geometry,
        crs,
        xy: &xy,
        validity: plane(1),
        feature_ids: if u32_at(16) == 1 { Some(&ids) } else { None },
        offsets0: &offsets[0],
        offsets1: &offsets[1],
        offsets2: &offsets[2],
        limits: GeoLimits::default(),
    })
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
    /// Per-ring winding recorded at validation (`1` CCW, `2` CW); empty for
    /// non-polygon kinds. Source vertex order is never rewritten.
    ring_orientations: Vec<u8>,
    /// Lazily built canonical `XYGM` document (derived, rebuildable).
    metadata: OnceLock<Vec<u8>>,
}

/// Magic bytes opening the canonical geographic metadata document.
pub const GEO_METADATA_MAGIC: &[u8; 4] = b"XYGM";
/// Canonical metadata document version (`XYGM` v1).
pub const GEO_METADATA_VERSION: u32 = 1;

/// Ring orientation code: counter-clockwise (positive signed area).
pub const GEO_RING_CCW: u8 = 1;
/// Ring orientation code: clockwise (negative signed area).
pub const GEO_RING_CW: u8 = 2;

/// Edge-visit budget multiplier for hole containment (`max_vertices * N`).
const HOLE_WORK_PER_VERTEX: usize = 64;

/// Check retained plane sizes before a host constructs slices or reads input.
/// The generated identity plane is budgeted even when IDs are omitted.
pub fn validate_descriptor_lengths(
    geometry: GeoGeometry,
    xy_len: usize,
    features: usize,
    offsets: [usize; 3],
    limits: GeoLimits,
) -> Result<(), GeoError> {
    if features > limits.max_features || xy_len / 2 > limits.max_vertices {
        return Err(GeoError::ResourceLimit);
    }
    if !xy_len.is_multiple_of(2) {
        return Err(GeoError::InvalidArgument);
    }
    let rings = match geometry {
        GeoGeometry::Polygon => offsets[1].saturating_sub(1),
        GeoGeometry::MultiPolygon => offsets[2].saturating_sub(1),
        _ => 0,
    };
    let bytes = offsets
        .into_iter()
        .fold(
            xy_len
                .saturating_mul(8)
                .saturating_add(features.saturating_mul(9)),
            |total, length| total.saturating_add(length.saturating_mul(4)),
        )
        .saturating_add(rings);
    if bytes > limits.max_bytes || bytes > isize::MAX as usize {
        return Err(GeoError::ResourceLimit);
    }
    Ok(())
}

impl GeoColumn {
    /// Validate and copy a host descriptor into an owned column.
    pub fn from_descriptor(desc: GeoDescriptor<'_>) -> Result<Self, GeoError> {
        let n_features = desc.validity.len();
        validate_descriptor_lengths(
            desc.geometry,
            desc.xy.len(),
            n_features,
            [
                desc.offsets0.len(),
                desc.offsets1.len(),
                desc.offsets2.len(),
            ],
            desc.limits,
        )?;
        let n_vertices = desc.xy.len() / 2;
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
        validate_line_parts(desc)?;
        let ring_orientations = if matches!(
            desc.geometry,
            GeoGeometry::Polygon | GeoGeometry::MultiPolygon
        ) {
            validate_rings(desc)?
        } else {
            Vec::new()
        };

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
            ring_orientations,
            metadata: OnceLock::new(),
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

    /// Per-ring winding in ring-plane order (`1` CCW, `2` CW); empty unless
    /// the column is a polygon kind. Recorded, never applied to vertices.
    #[must_use]
    pub fn ring_orientations(&self) -> &[u8] {
        &self.ring_orientations
    }

    /// Number of null features (`validity == 0`).
    #[must_use]
    pub fn null_count(&self) -> usize {
        self.validity.iter().filter(|&&flag| flag == 0).count()
    }

    /// Retained element counts: xy (f64 values), validity, feature ids,
    /// offsets0, offsets1, offsets2, ring orientations.
    #[must_use]
    pub fn plane_lens(&self) -> [u64; 7] {
        [
            self.xy.len() as u64,
            self.validity.len() as u64,
            self.feature_ids.len() as u64,
            self.offsets0.len() as u64,
            self.offsets1.len() as u64,
            self.offsets2.len() as u64,
            self.ring_orientations.len() as u64,
        ]
    }

    #[must_use]
    pub fn extension_name(&self) -> &'static str {
        self.geometry.extension_name()
    }

    #[must_use]
    pub fn extension_metadata(&self) -> String {
        self.crs.extension_metadata()
    }

    /// Canonical `XYGM` v1 metadata document (little-endian, 8-byte padded).
    ///
    /// Host-neutral and projection-independent: every host and WASM must
    /// return these bytes unchanged for the same column. Layout is pinned in
    /// `spec/design/geospatial.md`; digests are BLAKE2s-8 over each retained
    /// plane (length-prefixed, little-endian element bytes).
    #[must_use]
    pub fn canonical_metadata(&self) -> Vec<u8> {
        self.metadata
            .get_or_init(|| build_canonical_metadata(self))
            .clone()
    }

    /// Eight-byte digest of the canonical metadata document; keys derived
    /// caches (see `geo_viewport::GeoDerivedKey`).
    #[must_use]
    pub fn metadata_digest(&self) -> [u8; 8] {
        let meta = self.metadata.get_or_init(|| build_canonical_metadata(self));
        let mut hasher = Blake2s8::new();
        hasher.update(b"xygm-doc");
        hasher.update(meta);
        hasher.finish()
    }
}

fn feed_bytes(hasher: &mut Blake2s8, bytes: &[u8]) {
    hasher.update(&(bytes.len() as u64).to_le_bytes());
    hasher.update(bytes);
}

fn feed_le<T: Copy, const N: usize>(hasher: &mut Blake2s8, items: &[T], encode: fn(T) -> [u8; N]) {
    hasher.update(&(items.len() as u64).to_le_bytes());
    let mut buf = [0u8; 4096];
    for chunk in items.chunks(4096 / N) {
        for (i, &item) in chunk.iter().enumerate() {
            buf[i * N..(i + 1) * N].copy_from_slice(&encode(item));
        }
        hasher.update(&buf[..chunk.len() * N]);
    }
}

fn build_canonical_metadata(col: &GeoColumn) -> Vec<u8> {
    let mut xy = Blake2s8::new();
    xy.update(b"xygm-xy");
    feed_le(&mut xy, &col.xy, f64::to_le_bytes);
    let mut validity = Blake2s8::new();
    validity.update(b"xygm-validity");
    feed_bytes(&mut validity, &col.validity);
    let mut ids = Blake2s8::new();
    ids.update(b"xygm-ids");
    feed_le(&mut ids, &col.feature_ids, u64::to_le_bytes);
    let mut offsets = Blake2s8::new();
    offsets.update(b"xygm-offsets");
    feed_le(&mut offsets, &col.offsets0, u32::to_le_bytes);
    feed_le(&mut offsets, &col.offsets1, u32::to_le_bytes);
    feed_le(&mut offsets, &col.offsets2, u32::to_le_bytes);
    let mut orientations = Blake2s8::new();
    orientations.update(b"xygm-orient");
    feed_bytes(&mut orientations, &col.ring_orientations);

    let name = col.extension_name().as_bytes();
    let meta = col.extension_metadata().into_bytes();
    let mut out = Vec::with_capacity(160 + name.len() + meta.len());
    out.extend_from_slice(GEO_METADATA_MAGIC);
    out.extend_from_slice(&GEO_METADATA_VERSION.to_le_bytes());
    out.extend_from_slice(&(col.geometry as u32).to_le_bytes());
    out.extend_from_slice(&(col.crs as u32).to_le_bytes());
    out.extend_from_slice(&(col.validity.len() as u64).to_le_bytes());
    out.extend_from_slice(&((col.xy.len() / 2) as u64).to_le_bytes());
    out.extend_from_slice(&(col.null_count() as u64).to_le_bytes());
    out.extend_from_slice(&(col.offsets0.len() as u64).to_le_bytes());
    out.extend_from_slice(&(col.offsets1.len() as u64).to_le_bytes());
    out.extend_from_slice(&(col.offsets2.len() as u64).to_le_bytes());
    out.extend_from_slice(&(col.ring_orientations.len() as u64).to_le_bytes());
    out.extend_from_slice(&xy.finish());
    out.extend_from_slice(&validity.finish());
    out.extend_from_slice(&ids.finish());
    out.extend_from_slice(&offsets.finish());
    out.extend_from_slice(&orientations.finish());
    out.extend_from_slice(&(name.len() as u32).to_le_bytes());
    out.extend_from_slice(name);
    out.extend_from_slice(&(meta.len() as u32).to_le_bytes());
    out.extend_from_slice(&meta);
    while !out.len().is_multiple_of(8) {
        out.push(0);
    }
    out
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
            return Ok(());
        }
        GeoGeometry::LineString | GeoGeometry::MultiPoint => {
            check_offsets(desc.offsets0, n_features, n_vertices as u32)?;
        }
        GeoGeometry::Polygon | GeoGeometry::MultiLineString => {
            check_offsets(desc.offsets0, n_features, (desc.offsets1.len() - 1) as u32)?;
            check_offsets(desc.offsets1, desc.offsets1.len() - 1, n_vertices as u32)?;
        }
        GeoGeometry::MultiPolygon => {
            check_offsets(desc.offsets0, n_features, (desc.offsets1.len() - 1) as u32)?;
            check_offsets(
                desc.offsets1,
                desc.offsets1.len() - 1,
                (desc.offsets2.len() - 1) as u32,
            )?;
            check_offsets(desc.offsets2, desc.offsets2.len() - 1, n_vertices as u32)?;
        }
    }

    // Null nested features own no parts and therefore no vertices. Offsets are
    // monotonic and end at the vertex count, so an empty top-level range
    // transitively proves the feature owns nothing at deeper levels.
    for (feature, &flag) in desc.validity.iter().enumerate() {
        if flag == 0 && desc.offsets0[feature] != desc.offsets0[feature + 1] {
            return Err(GeoError::NullFeatureNotEmpty);
        }
    }
    Ok(())
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

/// Line parts (LineString features, MultiLineString lines) are empty or have
/// at least two vertices; a single vertex is not a line.
fn validate_line_parts(desc: GeoDescriptor<'_>) -> Result<(), GeoError> {
    let line_offsets = match desc.geometry {
        GeoGeometry::LineString => desc.offsets0,
        GeoGeometry::MultiLineString => desc.offsets1,
        _ => return Ok(()),
    };
    if line_offsets.windows(2).any(|w| w[1] - w[0] == 1) {
        return Err(GeoError::DegenerateGeometry);
    }
    Ok(())
}

/// Twice the signed shoelace area (positive = counter-clockwise), computed
/// relative to the first vertex so large absolute coordinates do not cancel.
fn ring_signed_area2(ring: &[f64]) -> f64 {
    let (ox, oy) = (ring[0], ring[1]);
    let mut sum = 0.0;
    for edge in ring.windows(4).step_by(2) {
        let (ax, ay) = (edge[0] - ox, edge[1] - oy);
        let (bx, by) = (edge[2] - ox, edge[3] - oy);
        sum += ax * by - bx * ay;
    }
    sum
}

/// Even-odd containment of `(px, py)` in a closed ring; boundary points count
/// as contained so holes may legally touch their shell.
fn ring_contains_point(ring: &[f64], px: f64, py: f64) -> bool {
    let mut inside = false;
    for edge in ring.windows(4).step_by(2) {
        let (ax, ay, bx, by) = (edge[0], edge[1], edge[2], edge[3]);
        let cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax);
        if cross == 0.0
            && px >= ax.min(bx)
            && px <= ax.max(bx)
            && py >= ay.min(by)
            && py <= ay.max(by)
        {
            return true;
        }
        if (ay > py) != (by > py) && px < ax + (py - ay) * (bx - ax) / (by - ay) {
            inside = !inside;
        }
    }
    inside
}

fn ring_bbox(ring: &[f64]) -> [f64; 4] {
    let mut bbox = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    for pair in ring.chunks_exact(2) {
        bbox[0] = bbox[0].min(pair[0]);
        bbox[1] = bbox[1].min(pair[1]);
        bbox[2] = bbox[2].max(pair[0]);
        bbox[3] = bbox[3].max(pair[1]);
    }
    bbox
}

/// Temporary validation/projection cache; canonical x/y bits never change.
/// Literal opposite world-edge endpoints retain an intentional full-world edge.
pub(crate) fn unwrap_ring_xy(
    ring: &[f64],
    period: f64,
    anchor: Option<f64>,
) -> Result<Vec<f64>, GeoError> {
    if ring
        .len()
        .checked_mul(size_of::<f64>())
        .ok_or(GeoError::ResourceLimit)?
        > GeoLimits::default().max_bytes
    {
        return Err(GeoError::ResourceLimit);
    }
    let mut cache = Vec::with_capacity(ring.len());
    let mut previous_raw: Option<f64> = None;
    let mut previous: Option<f64> = None;
    let (mut low, mut high) = (f64::INFINITY, f64::NEG_INFINITY);
    for pair in ring.chunks_exact(2) {
        let mut x = pair[0];
        if let (Some(raw), Some(prior)) = (previous_raw, previous) {
            if (x - raw).abs() != period {
                x += ((prior - x) / period).round() * period;
            }
        }
        previous_raw = Some(pair[0]);
        previous = Some(x);
        low = low.min(x);
        high = high.max(x);
        cache.extend([x, pair[1]]);
    }
    if high - low > period + period * 1e-12
        || cache.first() != cache.get(cache.len().saturating_sub(2))
    {
        return Err(GeoError::DegenerateGeometry);
    }
    if let Some(anchor) = anchor {
        let shift = ((anchor - (low + high) * 0.5) / period).round() * period;
        for pair in cache.chunks_exact_mut(2) {
            pair[0] += shift;
        }
    }
    Ok(cache)
}
fn ring_crosses_world_edge(ring: &[f64], period: f64) -> bool {
    ring.windows(4).step_by(2).any(|pair| {
        let delta = (pair[2] - pair[0]).abs();
        delta > period * 0.5 && delta < period
    })
}

/// Validate ring closure / area, record orientations, and require holes to
/// lie inside their exterior ring. Returns one orientation code per ring.
fn validate_rings(desc: GeoDescriptor<'_>) -> Result<Vec<u8>, GeoError> {
    let (polygon_ranges, ring_offsets) = match desc.geometry {
        GeoGeometry::Polygon => (desc.offsets0, desc.offsets1),
        GeoGeometry::MultiPolygon => (desc.offsets1, desc.offsets2),
        _ => return Ok(Vec::new()),
    };
    let ring = |index: usize| {
        let start = ring_offsets[index] as usize;
        let end = ring_offsets[index + 1] as usize;
        &desc.xy[start * 2..end * 2]
    };
    let ring_count = ring_offsets.len() - 1;
    let mut orientations = Vec::with_capacity(ring_count);
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
        let area2 = ring_signed_area2(&desc.xy[i0..i1 + 2]);
        if area2 == 0.0 {
            return Err(GeoError::DegenerateGeometry);
        }
        orientations.push(if area2 > 0.0 {
            GEO_RING_CCW
        } else {
            GEO_RING_CW
        });
    }

    // Ring 0 of every polygon is its exterior; the rest are holes. Cost is
    // bounded: one bbox test plus one first-vertex ray cast per hole, with a
    // total shell-edge visit budget tied to `max_vertices`.
    let mut budget = desc
        .limits
        .max_vertices
        .saturating_mul(HOLE_WORK_PER_VERTEX);
    for window in polygon_ranges.windows(2) {
        let (first, end) = (window[0] as usize, window[1] as usize);
        if end.saturating_sub(first) < 2 {
            continue;
        }
        let shell_source = ring(first);
        let period = match desc.crs {
            GeoCrs::Epsg4326 => 360.0,
            GeoCrs::Epsg3857 => 2.0 * WEB_MERCATOR_MAX,
        };
        let unwrap = ring_crosses_world_edge(shell_source, period);
        let shell_cache = if unwrap {
            Some(unwrap_ring_xy(shell_source, period, None)?)
        } else {
            None
        };
        let shell = shell_cache.as_deref().unwrap_or(shell_source);
        let anchor = (ring_bbox(shell)[0] + ring_bbox(shell)[2]) * 0.5;
        let shell_edges = shell.len() / 2 - 1;
        let shell_box = ring_bbox(shell);
        for hole_index in first + 1..end {
            let hole_source = ring(hole_index);
            let hole_cache = if unwrap {
                Some(unwrap_ring_xy(hole_source, period, Some(anchor))?)
            } else {
                None
            };
            let hole = hole_cache.as_deref().unwrap_or(hole_source);
            let hole_box = ring_bbox(hole);
            if hole_box[0] < shell_box[0]
                || hole_box[1] < shell_box[1]
                || hole_box[2] > shell_box[2]
                || hole_box[3] > shell_box[3]
            {
                return Err(GeoError::HoleOutsideShell);
            }
            budget = budget
                .checked_sub(shell_edges)
                .ok_or(GeoError::ResourceLimit)?;
            if !ring_contains_point(shell, hole[0], hole[1]) {
                return Err(GeoError::HoleOutsideShell);
            }
        }
    }
    Ok(orientations)
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

    /// Closed axis-aligned square ring (5 vertices); `ccw` selects winding.
    fn square(x0: f64, y0: f64, x1: f64, y1: f64, ccw: bool) -> Vec<f64> {
        if ccw {
            vec![x0, y0, x1, y0, x1, y1, x0, y1, x0, y0]
        } else {
            vec![x0, y0, x0, y1, x1, y1, x1, y0, x0, y0]
        }
    }

    fn desc<'a>(
        geometry: GeoGeometry,
        xy: &'a [f64],
        validity: &'a [u8],
        offsets: [&'a [u32]; 3],
    ) -> GeoDescriptor<'a> {
        GeoDescriptor {
            geometry,
            crs: GeoCrs::Epsg4326,
            xy,
            validity,
            feature_ids: None,
            offsets0: offsets[0],
            offsets1: offsets[1],
            offsets2: offsets[2],
            limits: GeoLimits::default(),
        }
    }

    fn err_of(d: GeoDescriptor<'_>) -> GeoError {
        GeoColumn::from_descriptor(d).unwrap_err()
    }

    #[test]
    fn error_codes_are_stable_and_value_free() {
        let table = [
            (
                GeoError::HoleOutsideShell,
                -11,
                "XYG_GEO_HOLE_OUTSIDE_SHELL",
            ),
            (
                GeoError::DegenerateGeometry,
                -12,
                "XYG_GEO_DEGENERATE_GEOMETRY",
            ),
            (GeoError::OutputCapacity, -13, "XYG_GEO_OUTPUT_CAPACITY"),
            (
                GeoError::NullFeatureNotEmpty,
                -14,
                "XYG_GEO_NULL_FEATURE_NOT_EMPTY",
            ),
        ];
        for (err, code, name) in table {
            assert_eq!(err as i32, code);
            assert_eq!(err.code(), name);
            assert!(!err.message().is_empty());
        }
        assert_eq!(GeoError::StaleHandle as i32, -10);
    }

    #[test]
    fn multipoint_fixture_retains_nulls_and_empty() {
        let xy = [-105.0, 39.7, -104.9, 39.8, -104.8, 39.9];
        // feature 0: two points; feature 1: null; feature 2: one point;
        // feature 3: present but empty.
        let col = GeoColumn::from_descriptor(desc(
            GeoGeometry::MultiPoint,
            &xy,
            &[1, 0, 1, 1],
            [&[0, 2, 2, 3, 3], &[], &[]],
        ))
        .unwrap();
        assert_eq!(col.len(), 4);
        assert_eq!(col.vertex_count(), 3);
        assert_eq!(col.null_count(), 1);
        assert_eq!(col.offsets0(), &[0, 2, 2, 3, 3]);
        assert_eq!(col.feature_ids(), &[0, 1, 2, 3]);
        assert!(col.ring_orientations().is_empty());
    }

    #[test]
    fn multilinestring_fixture_allows_empty_parts_but_not_single_vertex() {
        let xy = [-105.0, 39.7, -104.9, 39.8, -104.8, 39.9, -104.7, 40.0];
        // feature 0: two lines + one empty line; feature 1: null.
        let good = desc(
            GeoGeometry::MultiLineString,
            &xy,
            &[1, 0],
            [&[0, 3, 3], &[0, 2, 4, 4], &[]],
        );
        let col = GeoColumn::from_descriptor(good).unwrap();
        assert_eq!(col.vertex_count(), 4);
        assert_eq!(col.offsets1(), &[0, 2, 4, 4]);

        let single = desc(
            GeoGeometry::MultiLineString,
            &xy[..6],
            &[1],
            [&[0, 2], &[0, 2, 3], &[]],
        );
        assert_eq!(err_of(single), GeoError::DegenerateGeometry);
    }

    #[test]
    fn one_vertex_linestring_is_degenerate_and_empty_is_allowed() {
        let one = desc(
            GeoGeometry::LineString,
            &[-105.0, 39.7],
            &[1],
            [&[0, 1], &[], &[]],
        );
        let err = err_of(one);
        assert_eq!(err, GeoError::DegenerateGeometry);
        assert!(!err.message().contains("105"));

        let empty = desc(GeoGeometry::LineString, &[], &[1], [&[0, 0], &[], &[]]);
        assert!(GeoColumn::from_descriptor(empty).is_ok());
    }

    #[test]
    fn null_nested_features_must_own_nothing() {
        // Null linestring that still owns two vertices.
        let line = desc(
            GeoGeometry::LineString,
            &[-105.0, 39.7, -104.9, 39.8],
            &[0],
            [&[0, 2], &[], &[]],
        );
        assert_eq!(err_of(line), GeoError::NullFeatureNotEmpty);

        // Null polygon owning a ring.
        let ring = square(0.0, 0.0, 1.0, 1.0, true);
        let polygon = desc(GeoGeometry::Polygon, &ring, &[0], [&[0, 1], &[0, 5], &[]]);
        assert_eq!(err_of(polygon), GeoError::NullFeatureNotEmpty);

        // Null multipolygon owning an (even empty-ringed) polygon part.
        let multi = desc(
            GeoGeometry::MultiPolygon,
            &[],
            &[0],
            [&[0, 1], &[0, 0], &[0]],
        );
        assert_eq!(err_of(multi), GeoError::NullFeatureNotEmpty);

        // A null feature between valid ones is fine when it owns nothing.
        let ok = desc(
            GeoGeometry::LineString,
            &[-105.0, 39.7, -104.9, 39.8],
            &[1, 0],
            [&[0, 2, 2], &[], &[]],
        );
        assert!(GeoColumn::from_descriptor(ok).is_ok());
    }

    #[test]
    fn zero_area_ring_is_degenerate() {
        let collinear = [0.0, 0.0, 1.0, 1.0, 2.0, 2.0, 0.0, 0.0];
        let d = desc(
            GeoGeometry::Polygon,
            &collinear,
            &[1],
            [&[0, 1], &[0, 4], &[]],
        );
        assert_eq!(err_of(d), GeoError::DegenerateGeometry);
        // A spike ring (out and back) has zero area as well.
        let spike = [0.0, 0.0, 5.0, 5.0, 5.0, 5.0, 0.0, 0.0];
        let d = desc(GeoGeometry::Polygon, &spike, &[1], [&[0, 1], &[0, 4], &[]]);
        assert_eq!(err_of(d), GeoError::DegenerateGeometry);
    }

    #[test]
    fn polygon_with_hole_is_accepted_and_orientation_recorded_not_rewritten() {
        let mut xy = square(0.0, 0.0, 10.0, 10.0, true);
        xy.extend(square(2.0, 2.0, 4.0, 4.0, false));
        let col = GeoColumn::from_descriptor(desc(
            GeoGeometry::Polygon,
            &xy,
            &[1],
            [&[0, 2], &[0, 5, 10], &[]],
        ))
        .unwrap();
        assert_eq!(col.ring_orientations(), &[GEO_RING_CCW, GEO_RING_CW]);
        assert_eq!(col.xy(), xy.as_slice(), "source vertices never rewritten");

        // The same geometry with reversed windings is also accepted and the
        // recorded orientation follows the source, vertices still unchanged.
        let mut flipped = square(0.0, 0.0, 10.0, 10.0, false);
        flipped.extend(square(2.0, 2.0, 4.0, 4.0, true));
        let col = GeoColumn::from_descriptor(desc(
            GeoGeometry::Polygon,
            &flipped,
            &[1],
            [&[0, 2], &[0, 5, 10], &[]],
        ))
        .unwrap();
        assert_eq!(col.ring_orientations(), &[GEO_RING_CW, GEO_RING_CCW]);
        assert_eq!(col.xy(), flipped.as_slice());
    }

    #[test]
    fn dateline_holes_validate_in_temporary_cache_without_changing_canonical_planes() {
        let degrees = [
            170.0, -10.0, -170.0, -10.0, -170.0, 10.0, 170.0, 10.0, 170.0, -10.0, 175.0, -5.0,
            175.0, 5.0, -175.0, 5.0, -175.0, -5.0, 175.0, -5.0,
        ];
        for crs in [GeoCrs::Epsg4326, GeoCrs::Epsg3857] {
            let xy = degrees
                .chunks_exact(2)
                .flat_map(|p| {
                    if crs == GeoCrs::Epsg4326 {
                        [p[0], p[1]]
                    } else {
                        let (x, y) = crate::geo_viewport::lonlat_to_mercator(p[0], p[1]);
                        [x, y]
                    }
                })
                .collect::<Vec<_>>();
            let make = |xy: &[f64]| {
                GeoColumn::from_descriptor(GeoDescriptor {
                    geometry: GeoGeometry::Polygon,
                    crs,
                    xy,
                    validity: &[1],
                    feature_ids: Some(&[u64::MAX]),
                    offsets0: &[0, 2],
                    offsets1: &[0, 5, 10],
                    offsets2: &[],
                    limits: GeoLimits::default(),
                })
            };
            let column = make(&xy).unwrap();
            assert_eq!(
                column.xy().iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
                xy.iter().map(|v| v.to_bits()).collect::<Vec<_>>()
            );
            assert_eq!(column.feature_ids(), [u64::MAX]);
            assert_eq!(column.offsets1(), [0, 5, 10]);
            assert_eq!(column.ring_orientations(), [GEO_RING_CW, GEO_RING_CCW]);
            let mut outside = xy.clone();
            for pair in outside[10..].chunks_exact_mut(2) {
                pair[0] = 0.0;
            }
            assert_eq!(make(&outside).unwrap_err(), GeoError::DegenerateGeometry);
            let mut outside = xy.clone();
            let shift = if crs == GeoCrs::Epsg4326 {
                20.0
            } else {
                crate::geo_viewport::lonlat_to_mercator(0.0, 20.0).1
            };
            for pair in outside[10..].chunks_exact_mut(2) {
                pair[1] += shift;
            }
            assert_eq!(make(&outside).unwrap_err(), GeoError::HoleOutsideShell);
        }
    }

    #[test]
    fn hole_outside_shell_is_rejected() {
        let offsets: [&[u32]; 3] = [&[0, 2], &[0, 5, 10], &[]];
        // Entirely outside the shell bbox.
        let mut xy = square(0.0, 0.0, 10.0, 10.0, true);
        xy.extend(square(20.0, 20.0, 22.0, 22.0, false));
        let err = err_of(desc(GeoGeometry::Polygon, &xy, &[1], offsets));
        assert_eq!(err, GeoError::HoleOutsideShell);
        assert!(!err.message().contains("20"));

        // Inside the shell bbox but outside a concave (L-shaped) shell.
        let mut l_shell = vec![
            0.0, 0.0, 10.0, 0.0, 10.0, 4.0, 4.0, 4.0, 4.0, 10.0, 0.0, 10.0, 0.0, 0.0,
        ];
        let mut notch_hole = square(6.0, 6.0, 8.0, 8.0, false);
        let mut all = l_shell.clone();
        all.append(&mut notch_hole);
        let err = err_of(desc(
            GeoGeometry::Polygon,
            &all,
            &[1],
            [&[0, 2], &[0, 7, 12], &[]],
        ));
        assert_eq!(err, GeoError::HoleOutsideShell);

        // A hole inside the L is accepted.
        l_shell.extend(square(1.0, 1.0, 3.0, 3.0, false));
        assert!(GeoColumn::from_descriptor(desc(
            GeoGeometry::Polygon,
            &l_shell,
            &[1],
            [&[0, 2], &[0, 7, 12], &[]],
        ))
        .is_ok());
    }

    #[test]
    fn hole_touching_shell_boundary_is_accepted() {
        let mut xy = square(0.0, 0.0, 10.0, 10.0, true);
        // First vertex of the hole sits exactly on the shell edge.
        xy.extend([5.0, 0.0, 6.0, 2.0, 4.0, 2.0, 5.0, 0.0]);
        assert!(GeoColumn::from_descriptor(desc(
            GeoGeometry::Polygon,
            &xy,
            &[1],
            [&[0, 2], &[0, 5, 9], &[]],
        ))
        .is_ok());
    }

    #[test]
    fn multipolygon_with_holes_across_two_polygons() {
        // Feature 0: two polygons, each shell + hole; feature 1: null;
        // feature 2: one polygon without holes.
        let mut xy = Vec::new();
        xy.extend(square(0.0, 0.0, 10.0, 10.0, true));
        xy.extend(square(2.0, 2.0, 4.0, 4.0, false));
        xy.extend(square(20.0, 20.0, 30.0, 30.0, true));
        xy.extend(square(22.0, 22.0, 24.0, 24.0, false));
        xy.extend(square(40.0, 40.0, 41.0, 41.0, false));
        let offsets2: Vec<u32> = (0..=5).map(|i| i * 5).collect();
        let col = GeoColumn::from_descriptor(desc(
            GeoGeometry::MultiPolygon,
            &xy,
            &[1, 0, 1],
            [&[0, 2, 2, 3], &[0, 2, 4, 5], &offsets2],
        ))
        .unwrap();
        assert_eq!(col.vertex_count(), 25);
        assert_eq!(col.ring_orientations(), &[1, 2, 1, 2, 2]);
        assert_eq!(col.null_count(), 1);

        // Move the second polygon's hole into the first polygon's shell: it is
        // inside *a* shell but not its own, so the ownership grouping matters.
        let mut bad = xy.clone();
        bad.splice(30..40, square(2.0, 2.0, 4.0, 4.0, false));
        let bad = &bad[..];
        assert_eq!(
            err_of(desc(
                GeoGeometry::MultiPolygon,
                bad,
                &[1, 0, 1],
                [&[0, 2, 2, 3], &[0, 2, 4, 5], &offsets2],
            )),
            GeoError::HoleOutsideShell
        );
    }

    #[test]
    fn budget_overrides_reject_before_validation_or_copy() {
        let mut xy = square(0.0, 0.0, 10.0, 10.0, true);
        xy.extend(square(2.0, 2.0, 4.0, 4.0, false));
        let base = desc(GeoGeometry::Polygon, &xy, &[1], [&[0, 2], &[0, 5, 10], &[]]);
        assert!(GeoColumn::from_descriptor(base).is_ok());

        let mut few_vertices = base;
        few_vertices.limits.max_vertices = 9;
        assert_eq!(err_of(few_vertices), GeoError::ResourceLimit);
        few_vertices.limits.max_vertices = 10;
        assert!(GeoColumn::from_descriptor(few_vertices).is_ok());

        // 160 xy + 1 validity + 8 + 12 + 8 ids + 2 orientations = 191 bytes.
        let mut few_bytes = base;
        few_bytes.limits.max_bytes = 190;
        assert_eq!(err_of(few_bytes), GeoError::ResourceLimit);
        few_bytes.limits.max_bytes = 191;
        assert!(GeoColumn::from_descriptor(few_bytes).is_ok());

        // Budget wins over malformed offsets: no per-vertex work on hostile input.
        let mut hostile = desc(
            GeoGeometry::Polygon,
            &xy,
            &[1],
            [&[0, 99], &[0, 5, 10], &[]],
        );
        hostile.limits.max_bytes = 8;
        assert_eq!(err_of(hostile), GeoError::ResourceLimit);
    }

    #[test]
    fn canonical_metadata_is_stable_aligned_and_content_sensitive() {
        let a = GeoColumn::from_descriptor(point_denver()).unwrap();
        let meta = a.canonical_metadata();
        assert_eq!(&meta[..4], GEO_METADATA_MAGIC);
        assert_eq!(u32::from_le_bytes(meta[4..8].try_into().unwrap()), 1);
        assert_eq!(u32::from_le_bytes(meta[8..12].try_into().unwrap()), 1);
        assert_eq!(u32::from_le_bytes(meta[12..16].try_into().unwrap()), 4326);
        assert_eq!(u64::from_le_bytes(meta[16..24].try_into().unwrap()), 1);
        assert_eq!(u64::from_le_bytes(meta[24..32].try_into().unwrap()), 1);
        assert_eq!(u64::from_le_bytes(meta[32..40].try_into().unwrap()), 0);
        assert_eq!(meta.len() % 8, 0);
        let name_len = u32::from_le_bytes(meta[112..116].try_into().unwrap()) as usize;
        assert_eq!(&meta[116..116 + name_len], b"geoarrow.point");
        assert!(meta.windows(9).any(|w| w == b"EPSG:4326"));

        let b = GeoColumn::from_descriptor(point_denver()).unwrap();
        assert_eq!(meta, b.canonical_metadata());
        assert_eq!(a.metadata_digest(), b.metadata_digest());
        assert_eq!(a.clone().canonical_metadata(), meta);

        let mut moved = point_denver();
        moved.xy = &[-104.9904, 39.7392];
        let c = GeoColumn::from_descriptor(moved).unwrap();
        let other = c.canonical_metadata();
        assert_eq!(other.len(), meta.len());
        assert_ne!(other, meta);
        assert_ne!(c.metadata_digest(), a.metadata_digest());

        let mut ids = point_denver();
        ids.feature_ids = Some(&[7]);
        assert_ne!(
            GeoColumn::from_descriptor(ids)
                .unwrap()
                .canonical_metadata(),
            meta
        );

        let mut mercator = point_denver();
        mercator.crs = GeoCrs::Epsg3857;
        mercator.xy = &[-104.9903, 39.7392];
        assert_ne!(
            GeoColumn::from_descriptor(mercator)
                .unwrap()
                .canonical_metadata(),
            meta
        );
    }

    #[test]
    fn plane_lens_and_orientation_digest_track_rings() {
        let mut xy = square(0.0, 0.0, 10.0, 10.0, true);
        xy.extend(square(2.0, 2.0, 4.0, 4.0, false));
        let ccw_hole = {
            let mut v = square(0.0, 0.0, 10.0, 10.0, true);
            v.extend(square(2.0, 2.0, 4.0, 4.0, true));
            v
        };
        let offsets: [&[u32]; 3] = [&[0, 2], &[0, 5, 10], &[]];
        let a = GeoColumn::from_descriptor(desc(GeoGeometry::Polygon, &xy, &[1], offsets)).unwrap();
        assert_eq!(a.plane_lens(), [20, 1, 1, 2, 3, 0, 2]);
        let b = GeoColumn::from_descriptor(desc(GeoGeometry::Polygon, &ccw_hole, &[1], offsets))
            .unwrap();
        assert_ne!(a.canonical_metadata(), b.canonical_metadata());
        // Ring count appears in the header at byte 64.
        assert_eq!(
            u64::from_le_bytes(a.canonical_metadata()[64..72].try_into().unwrap()),
            2
        );
    }
}

#[cfg(test)]
mod fuzz {
    //! Deterministic fuzz for the descriptor validation boundary. Zero-crate:
    //! a seeded xorshift64* PRNG makes every failure reproducible from its
    //! iteration number (same convention as `kernels::fuzz`). Valid columns of
    //! all six kinds are generated, then hostile mutations are applied.
    //!
    //! Invariants: `from_descriptor` never panics; known-bad mutations are
    //! rejected with the expected stable error; accepted columns reproduce the
    //! input bitwise and have a stable canonical metadata document; derived
    //! projections are finite, ID-preserving, and bit-reproducible.
    use super::*;
    use crate::geo_viewport::{GeoViewport, ProjectedGeoGeometry};

    struct Rng(u64);
    impl Rng {
        fn next(&mut self) -> u64 {
            let mut x = self.0;
            x ^= x >> 12;
            x ^= x << 25;
            x ^= x >> 27;
            self.0 = x;
            x.wrapping_mul(0x2545F4914F6CDD1D)
        }
        fn below(&mut self, n: u64) -> usize {
            (self.next() % n) as usize
        }
        fn f01(&mut self) -> f64 {
            (self.next() >> 11) as f64 / (1u64 << 53) as f64
        }
        fn range(&mut self, lo: f64, hi: f64) -> f64 {
            lo + self.f01() * (hi - lo)
        }
    }

    #[derive(Clone)]
    struct Owned {
        geometry: GeoGeometry,
        crs: GeoCrs,
        xy: Vec<f64>,
        validity: Vec<u8>,
        ids: Option<Vec<u64>>,
        o: [Vec<u32>; 3],
        limits: GeoLimits,
        scale: f64,
    }

    impl Owned {
        fn desc(&self) -> GeoDescriptor<'_> {
            GeoDescriptor {
                geometry: self.geometry,
                crs: self.crs,
                xy: &self.xy,
                validity: &self.validity,
                feature_ids: self.ids.as_deref(),
                offsets0: &self.o[0],
                offsets1: &self.o[1],
                offsets2: &self.o[2],
                limits: self.limits,
            }
        }
        fn build(&self) -> Result<GeoColumn, GeoError> {
            GeoColumn::from_descriptor(self.desc())
        }
    }

    fn push_square(rng: &mut Rng, owned: &mut Owned, cx: f64, cy: f64, half: f64, hole: bool) {
        let ccw = rng.below(2) == 0;
        let h = if hole { half * 0.25 } else { half };
        let (x0, y0, x1, y1) = (cx - h, cy - h, cx + h, cy + h);
        let ring = if ccw {
            [x0, y0, x1, y0, x1, y1, x0, y1, x0, y0]
        } else {
            [x0, y0, x0, y1, x1, y1, x1, y0, x0, y0]
        };
        owned.xy.extend(ring);
    }

    /// One polygon: shell plus 0..=2 holes; returns ring count.
    fn push_polygon(rng: &mut Rng, owned: &mut Owned) -> u32 {
        let s = owned.scale;
        let cx = rng.range(-100.0, 100.0) * s;
        let cy = rng.range(-60.0, 60.0) * s;
        let half = rng.range(2.0, 10.0) * s;
        push_square(rng, owned, cx, cy, half, false);
        let holes = rng.below(3) as u32;
        for _ in 0..holes {
            push_square(rng, owned, cx, cy, half, true);
        }
        1 + holes
    }

    fn generate(rng: &mut Rng, geometry: GeoGeometry, crs: GeoCrs) -> Owned {
        let scale = if crs == GeoCrs::Epsg3857 { 1e5 } else { 1.0 };
        let mut owned = Owned {
            geometry,
            crs,
            xy: Vec::new(),
            validity: Vec::new(),
            ids: None,
            o: [Vec::new(), Vec::new(), Vec::new()],
            limits: GeoLimits::default(),
            scale,
        };
        let features = rng.below(6);
        let mut o0 = vec![0u32];
        let mut o1 = vec![0u32];
        let mut o2 = vec![0u32];
        for _ in 0..features {
            let null = rng.below(4) == 0;
            owned.validity.push(u8::from(!null));
            match geometry {
                GeoGeometry::Point => {
                    if !null {
                        owned.xy.push(rng.range(-170.0, 170.0) * scale);
                        owned.xy.push(rng.range(-80.0, 80.0) * scale);
                    }
                }
                GeoGeometry::MultiPoint => {
                    let n = if null { 0 } else { rng.below(4) };
                    for _ in 0..n {
                        owned.xy.push(rng.range(-170.0, 170.0) * scale);
                        owned.xy.push(rng.range(-80.0, 80.0) * scale);
                    }
                    o0.push((owned.xy.len() / 2) as u32);
                }
                GeoGeometry::LineString => {
                    let n = if null || rng.below(5) == 0 {
                        0
                    } else {
                        2 + rng.below(4)
                    };
                    for _ in 0..n {
                        owned.xy.push(rng.range(-170.0, 170.0) * scale);
                        owned.xy.push(rng.range(-80.0, 80.0) * scale);
                    }
                    o0.push((owned.xy.len() / 2) as u32);
                }
                GeoGeometry::MultiLineString => {
                    let lines = if null { 0 } else { rng.below(4) };
                    for _ in 0..lines {
                        let n = if rng.below(5) == 0 {
                            0
                        } else {
                            2 + rng.below(3)
                        };
                        for _ in 0..n {
                            owned.xy.push(rng.range(-170.0, 170.0) * scale);
                            owned.xy.push(rng.range(-80.0, 80.0) * scale);
                        }
                        o1.push((owned.xy.len() / 2) as u32);
                    }
                    o0.push(o1.len() as u32 - 1);
                }
                GeoGeometry::Polygon => {
                    if !null {
                        let rings = push_polygon(rng, &mut owned);
                        for _ in 0..rings {
                            let last = *o1.last().unwrap();
                            o1.push(last + 5);
                        }
                    }
                    o0.push(o1.len() as u32 - 1);
                }
                GeoGeometry::MultiPolygon => {
                    let polys = if null { 0 } else { rng.below(3) };
                    for _ in 0..polys {
                        let rings = push_polygon(rng, &mut owned);
                        for _ in 0..rings {
                            let last = *o2.last().unwrap();
                            o2.push(last + 5);
                        }
                        o1.push(o2.len() as u32 - 1);
                    }
                    o0.push(o1.len() as u32 - 1);
                }
            }
        }
        let depth = geometry.offset_depth();
        owned.o = [
            if depth >= 1 { o0 } else { Vec::new() },
            if depth >= 2 { o1 } else { Vec::new() },
            if depth >= 3 { o2 } else { Vec::new() },
        ];
        if rng.below(2) == 0 {
            owned.ids = Some((0..features as u64).map(|i| 1000 + i * 3).collect());
        }
        owned
    }

    fn assert_round_trip(owned: &Owned, col: &GeoColumn, ctx: &str) {
        assert_eq!(col.geometry(), owned.geometry, "{ctx}");
        assert_eq!(col.crs(), owned.crs, "{ctx}");
        assert!(
            col.xy()
                .iter()
                .map(|v| v.to_bits())
                .eq(owned.xy.iter().map(|v| v.to_bits())),
            "{ctx}: xy bitwise"
        );
        assert_eq!(col.validity(), owned.validity.as_slice(), "{ctx}");
        match &owned.ids {
            Some(ids) => assert_eq!(col.feature_ids(), ids.as_slice(), "{ctx}"),
            None => assert!(
                col.feature_ids()
                    .iter()
                    .copied()
                    .eq(0..owned.validity.len() as u64),
                "{ctx}"
            ),
        }
        assert_eq!(col.offsets0(), owned.o[0].as_slice(), "{ctx}");
        assert_eq!(col.offsets1(), owned.o[1].as_slice(), "{ctx}");
        assert_eq!(col.offsets2(), owned.o[2].as_slice(), "{ctx}");
        let rebuilt = owned.build().unwrap();
        assert_eq!(
            col.canonical_metadata(),
            rebuilt.canonical_metadata(),
            "{ctx}"
        );
        assert_eq!(col.canonical_metadata().len() % 8, 0, "{ctx}");
        assert!(
            col.ring_orientations().iter().all(|&o| o == 1 || o == 2),
            "{ctx}"
        );
        assert_eq!(
            col.ring_orientations(),
            rebuilt.ring_orientations(),
            "{ctx}"
        );
    }

    fn assert_projection(col: &GeoColumn, ctx: &str) {
        let world_wrap = col.crs() == GeoCrs::Epsg4326;
        let vp = GeoViewport::new(col.crs(), 0.0, 0.0, 1.0, 640.0, 480.0, 0.0, 0.0, world_wrap)
            .unwrap_or_else(|e| panic!("{ctx}: viewport {e:?}"));
        let a = vp.project_column(col).unwrap();
        let b = vp.project_column(col).unwrap();
        assert_eq!(a, b, "{ctx}: bit-identical rebuild");
        let ids: std::collections::HashSet<u64> = col.feature_ids().iter().copied().collect();
        match &a.geometry {
            ProjectedGeoGeometry::Points(points) => {
                assert!(points.xy.iter().all(|v| v.is_finite()), "{ctx}");
                assert_eq!(points.xy.len() / 2, points.feature_ids.len(), "{ctx}");
                assert_eq!(points.feature_ids.len(), col.vertex_count(), "{ctx}");
                assert!(
                    points.feature_ids.iter().all(|id| ids.contains(id)),
                    "{ctx}"
                );
            }
            ProjectedGeoGeometry::Outlines(lines) => {
                assert!(lines.xy.iter().all(|v| v.is_finite()), "{ctx}");
                assert_eq!(lines.offsets.len(), lines.feature_ids.len() + 1, "{ctx}");
                assert!(lines.feature_ids.iter().all(|id| ids.contains(id)), "{ctx}");
                assert_eq!(
                    *lines.offsets.last().unwrap() as usize,
                    lines.xy.len() / 2,
                    "{ctx}"
                );
            }
        }
    }

    const KINDS: [GeoGeometry; 6] = [
        GeoGeometry::Point,
        GeoGeometry::LineString,
        GeoGeometry::Polygon,
        GeoGeometry::MultiPoint,
        GeoGeometry::MultiLineString,
        GeoGeometry::MultiPolygon,
    ];

    #[test]
    fn fuzz_valid_columns_round_trip_and_project() {
        let mut rng = Rng(0x6E0_0001);
        for it in 0..240 {
            let geometry = KINDS[it % KINDS.len()];
            let crs = if rng.below(4) == 0 {
                GeoCrs::Epsg3857
            } else {
                GeoCrs::Epsg4326
            };
            let owned = generate(&mut rng, geometry, crs);
            let ctx = format!("it={it} {geometry:?} {crs:?}");
            let col = owned
                .build()
                .unwrap_or_else(|e| panic!("{ctx}: valid input rejected: {e:?}"));
            assert_round_trip(&owned, &col, &ctx);
            assert_projection(&col, &ctx);
        }
    }

    /// Pick a random index of a non-empty slice, or `None`.
    fn pick(rng: &mut Rng, len: usize) -> Option<usize> {
        (len > 0).then(|| rng.below(len as u64))
    }

    #[test]
    fn fuzz_mutations_never_panic_and_known_bad_inputs_fail_closed() {
        let mut rng = Rng(0x6E0_0002);
        let mut applied = [0usize; 12];
        for it in 0..1200 {
            let geometry = KINDS[it % KINDS.len()];
            let crs = if rng.below(4) == 0 {
                GeoCrs::Epsg3857
            } else {
                GeoCrs::Epsg4326
            };
            let mut owned = generate(&mut rng, geometry, crs);
            let ctx = format!("it={it} {geometry:?} {crs:?}");
            let s = owned.scale;
            // `Some(expected)` = must fail with exactly that code; `None` =
            // outcome unconstrained but must not panic and must round trip.
            let class = rng.below(12);
            let expected: Option<Option<GeoError>> = match class {
                0 => {
                    // Inflate the last offset of the deepest plane.
                    let depth = geometry.offset_depth();
                    if depth == 0 {
                        None
                    } else {
                        *owned.o[depth - 1].last_mut().unwrap() += 1;
                        Some(Some(GeoError::OffsetMismatch))
                    }
                }
                1 => match pick(&mut rng, owned.xy.len()) {
                    Some(i) => {
                        owned.xy[i] = [f64::NAN, f64::INFINITY, f64::NEG_INFINITY][rng.below(3)];
                        Some(Some(GeoError::NonFiniteCoordinate))
                    }
                    None => None,
                },
                2 => match pick(&mut rng, owned.xy.len()) {
                    Some(i) => {
                        owned.xy[i] = match (crs, i % 2) {
                            (GeoCrs::Epsg4326, 0) => 181.0,
                            (GeoCrs::Epsg4326, _) => 91.0,
                            (GeoCrs::Epsg3857, _) => 1e9,
                        };
                        Some(Some(GeoError::CoordinateOutOfRange))
                    }
                    None => None,
                },
                3 => {
                    // Open a ring by nudging its last vertex.
                    let ring_plane = match geometry {
                        GeoGeometry::Polygon => Some(1),
                        GeoGeometry::MultiPolygon => Some(2),
                        _ => None,
                    };
                    match ring_plane.and_then(|p| {
                        pick(&mut rng, owned.o[p].len().saturating_sub(1)).map(|r| (p, r))
                    }) {
                        Some((p, ring)) => {
                            let end = owned.o[p][ring + 1] as usize;
                            owned.xy[(end - 1) * 2] += 0.5 * s;
                            Some(Some(GeoError::RingNotClosed))
                        }
                        None => None,
                    }
                }
                4 => {
                    // Move a hole far away from its shell.
                    let ring_plane = match geometry {
                        GeoGeometry::Polygon => Some((0usize, 1usize)),
                        GeoGeometry::MultiPolygon => Some((1, 2)),
                        _ => None,
                    };
                    let mut moved = None;
                    if let Some((parent, ring_p)) = ring_plane {
                        let windows: Vec<(usize, usize)> = owned.o[parent]
                            .windows(2)
                            .map(|w| (w[0] as usize, w[1] as usize))
                            .filter(|(a, b)| b - a >= 2)
                            .collect();
                        if let Some(w) = pick(&mut rng, windows.len()) {
                            let (first, end) = windows[w];
                            let hole = first + 1 + rng.below((end - first - 1) as u64);
                            let (v0, v1) = (
                                owned.o[ring_p][hole] as usize,
                                owned.o[ring_p][hole + 1] as usize,
                            );
                            for v in v0..v1 {
                                owned.xy[v * 2] += 50.0 * s;
                            }
                            moved = Some(Some(GeoError::HoleOutsideShell));
                        }
                    }
                    moved
                }
                5 => {
                    // Shrink the vertex budget below the column.
                    let vertices = owned.xy.len() / 2;
                    if vertices > 0 {
                        owned.limits.max_vertices = vertices - 1;
                        Some(Some(GeoError::ResourceLimit))
                    } else {
                        None
                    }
                }
                6 => {
                    // Nullify a feature that still owns data.
                    let depth = geometry.offset_depth();
                    if depth == 0 {
                        None
                    } else {
                        let owners: Vec<usize> = owned.o[0]
                            .windows(2)
                            .enumerate()
                            .filter(|(_, w)| w[1] > w[0])
                            .map(|(i, _)| i)
                            .collect();
                        match pick(&mut rng, owners.len()) {
                            Some(k) => {
                                owned.validity[owners[k]] = 0;
                                Some(Some(GeoError::NullFeatureNotEmpty))
                            }
                            None => None,
                        }
                    }
                }
                7 => {
                    // Break monotonicity of an offset plane.
                    let depth = geometry.offset_depth();
                    if depth == 0 {
                        None
                    } else {
                        let plane = rng.below(depth as u64);
                        let o = &mut owned.o[plane];
                        let strict: Vec<usize> =
                            (0..o.len() - 1).filter(|&i| o[i + 1] > o[i]).collect();
                        match pick(&mut rng, strict.len()) {
                            Some(k) => {
                                let i = strict[k];
                                o.swap(i, i + 1);
                                Some(Some(GeoError::OffsetMismatch))
                            }
                            None => None,
                        }
                    }
                }
                8 => {
                    // Out-of-band validity flag.
                    match pick(&mut rng, owned.validity.len()) {
                        Some(i) => {
                            owned.validity[i] = 2 + rng.below(250) as u8;
                            Some(Some(GeoError::InvalidArgument))
                        }
                        None => None,
                    }
                }
                9 => {
                    // Feature-id plane of the wrong length.
                    owned.ids = Some(vec![7; owned.validity.len() + 1]);
                    Some(Some(GeoError::InvalidArgument))
                }
                10 => {
                    // Wrong geometry kind for the supplied planes.
                    let other = KINDS[(it + 1 + rng.below(5)) % KINDS.len()];
                    if other.offset_depth() != geometry.offset_depth() {
                        owned.geometry = other;
                        Some(Some(GeoError::TypeMismatch))
                    } else {
                        None
                    }
                }
                _ => {
                    // Unconstrained byte-level garbage on one offset entry.
                    let depth = geometry.offset_depth();
                    if depth > 0 {
                        let plane = rng.below(depth as u64);
                        if let Some(i) = pick(&mut rng, owned.o[plane].len()) {
                            owned.o[plane][i] = rng.next() as u32;
                        }
                    }
                    None
                }
            };
            if expected.is_some() || class == 11 {
                applied[class] += 1;
            }
            let result = owned.build();
            match (expected, &result) {
                (Some(Some(want)), Err(got)) => assert_eq!(*got, want, "{ctx}"),
                (Some(Some(_)), Ok(_)) => panic!("{ctx}: known-bad input accepted"),
                (_, Err(err)) => {
                    // Stable code, value-free message.
                    assert!(err.code().starts_with("XYG_GEO_"), "{ctx}");
                    assert!(!err.message().chars().any(|c| c.is_ascii_digit()), "{ctx}");
                }
                (_, Ok(col)) => {
                    assert_round_trip(&owned, col, &ctx);
                    assert_projection(col, &ctx);
                }
            }
        }
        // Every mutation class must actually have been exercised.
        for (class, &count) in applied.iter().enumerate() {
            assert!(count > 0, "mutation class {class} never applied");
        }
    }

    #[test]
    fn fuzz_hole_work_budget_is_bounded() {
        // One large shell with many holes: quadratic containment work must hit
        // the ResourceLimit budget instead of running unbounded.
        let shell_edges = 4_000usize;
        let mut xy = Vec::new();
        // CCW polygon approximated by a convex regular-ish ring.
        for i in 0..shell_edges {
            let a = (i as f64) / (shell_edges as f64) * std::f64::consts::TAU;
            xy.push(100.0 * a.cos());
            xy.push(50.0 * a.sin());
        }
        xy.push(xy[0]);
        xy.push(xy[1]);
        let mut ring_offsets = vec![0u32, (shell_edges + 1) as u32];
        let holes = 600usize;
        for i in 0..holes {
            let (cx, cy) = ((i % 30) as f64 * 5.0 - 70.0, (i / 30) as f64 * 3.0 - 30.0);
            xy.extend([cx, cy, cx + 1.0, cy, cx + 1.0, cy - 1.0, cx, cy]);
            let last = *ring_offsets.last().unwrap();
            ring_offsets.push(last + 4);
        }
        let rings = ring_offsets.len() as u32 - 1;
        let o0 = [0u32, rings];
        let mk = |max_vertices| GeoDescriptor {
            geometry: GeoGeometry::Polygon,
            crs: GeoCrs::Epsg4326,
            xy: &xy,
            validity: &[1],
            feature_ids: None,
            offsets0: &o0,
            offsets1: &ring_offsets,
            offsets2: &[],
            limits: GeoLimits {
                max_vertices,
                ..GeoLimits::default()
            },
        };
        let vertices = xy.len() / 2;
        // work = 600 holes * 4000 edges = 2.4e6; budget = max_vertices * 64.
        assert!(GeoColumn::from_descriptor(mk(vertices.max(2_400_000 / 64 + 1))).is_ok());
        assert_eq!(
            GeoColumn::from_descriptor(mk(vertices)).unwrap_err(),
            GeoError::ResourceLimit
        );
    }
}
