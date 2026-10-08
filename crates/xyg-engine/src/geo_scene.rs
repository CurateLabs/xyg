//! Frozen geographic point/outline lowering into ordinary canonical Scenes.
//! `XYGP` is an authoring envelope, never a second geographic scene schema.
use crate::geo::{column_from_descriptor_bytes, GeoError, GeoGeometry};
use crate::geo_viewport::{GeoViewport, ProjectedGeoGeometry};
use crate::scene::{
    AxisScale, PlotLayout, ScaleKind, SceneBatch, SceneChromeStyle, SceneChromeText, SceneError,
    MAX_SCENE_MARKS,
};

pub const GEO_SCENE_MAGIC: &[u8; 4] = b"XYGP";
pub const GEO_SCENE_VERSION: u32 = 1;
pub const GEO_SCENE_HEADER_BYTES: usize = 128;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoSceneError {
    Geo(GeoError),
    Unsupported,
}
impl GeoSceneError {
    pub fn code(self) -> &'static str {
        match self {
            Self::Geo(error) => error.code(),
            Self::Unsupported => "XYG_GEO_SCENE_UNSUPPORTED",
        }
    }
    pub fn is_resource(self) -> bool {
        self == Self::Geo(GeoError::ResourceLimit)
    }
}
impl From<GeoError> for GeoSceneError {
    fn from(error: GeoError) -> Self {
        Self::Geo(error)
    }
}
impl From<SceneError> for GeoSceneError {
    fn from(error: SceneError) -> Self {
        Self::Geo(if error == SceneError::Limit {
            GeoError::ResourceLimit
        } else {
            GeoError::InvalidArgument
        })
    }
}

/// Validate and lower a frozen camera + typed geometry to the existing `XYGS`.
/// Peak admission accounts for transferred JS input, Rust staging, canonical
/// source, projected caches, compact columns, prepared marks, encoded output,
/// and capacity slack before any variable allocation occurs.
pub fn compile_geo_scene(bytes: &[u8], budget: usize) -> Result<Vec<u8>, GeoSceneError> {
    let bad = GeoError::InvalidArgument;
    if bytes.len() < GEO_SCENE_HEADER_BYTES + 64 || &bytes[..4] != GEO_SCENE_MAGIC {
        return Err(bad.into());
    }
    let u32_at = |i| u32::from_le_bytes(bytes[i..i + 4].try_into().unwrap());
    let u64_at = |i| u64::from_le_bytes(bytes[i..i + 8].try_into().unwrap());
    let f64_at = |i| f64::from_le_bytes(bytes[i..i + 8].try_into().unwrap());
    if u32_at(4) != 1
        || u32_at(8) != 128
        || u32_at(12) > 7
        || u32_at(20) != 0
        || bytes[112..128].iter().any(|&v| v != 0)
    {
        return Err(bad.into());
    }
    let length = usize::try_from(u64_at(104)).map_err(|_| bad)?;
    if length != bytes.len() - 128 {
        return Err(bad.into());
    }
    let descriptor = &bytes[128..];
    let crs = crate::geo::GeoCrs::from_u32(u32_at(16)).ok_or(GeoError::UnsupportedCrs)?;
    let viewport = GeoViewport::new(
        crs,
        f64_at(24),
        f64_at(32),
        f64_at(40),
        f64_at(48),
        f64_at(56),
        f64_at(64),
        f64_at(72),
        u32_at(12) & 1 != 0,
    )?;
    // Terrain/elevation, roll, basemap and layer fills remain #49. Ground
    // perspective uses the same certified GeoViewport as native hosts.
    let diameter = if f64_at(80).is_nan() { 6.0 } else { f64_at(80) };
    let width = if f64_at(88).is_nan() { 1.0 } else { f64_at(88) };
    if !diameter.is_finite()
        || diameter < 0.0
        || !width.is_finite()
        || width < 0.0
        || [diameter, width, viewport.width, viewport.height]
            .iter()
            .any(|&v| !(v as f32).is_finite())
    {
        return Err(bad.into());
    }
    let geometry = GeoGeometry::from_u32(u32::from_le_bytes(descriptor[8..12].try_into().unwrap()))
        .ok_or(GeoError::TypeMismatch)?;
    let vertices = usize::try_from(u64::from_le_bytes(descriptor[32..40].try_into().unwrap()))
        .map_err(|_| bad)?;
    let features = usize::try_from(u64::from_le_bytes(descriptor[24..32].try_into().unwrap()))
        .map_err(|_| bad)?;
    // Each source line edge can split into two clipped segments, each needing
    // two visible vertices plus one invisible run separator. Points need one.
    let records = vertices
        .checked_mul(
            if matches!(geometry, GeoGeometry::Point | GeoGeometry::MultiPoint) {
                1
            } else {
                6
            },
        )
        .ok_or(GeoError::ResourceLimit)?;
    if records > MAX_SCENE_MARKS {
        return Err(GeoError::ResourceLimit.into());
    }
    let mut peak = bytes
        .len()
        .checked_mul(3)
        .and_then(|n| features.checked_mul(16).and_then(|v| n.checked_add(v)))
        .and_then(|n| records.checked_mul(512).and_then(|v| n.checked_add(v)))
        .and_then(|n| n.checked_add(32768))
        .ok_or(GeoError::ResourceLimit)?;
    if matches!(geometry, GeoGeometry::Polygon | GeoGeometry::MultiPolygon) {
        peak = peak
            .checked_add(vertices.checked_mul(4096).ok_or(GeoError::ResourceLimit)?)
            .and_then(|n| features.checked_mul(512).and_then(|f| n.checked_add(f)))
            .ok_or(GeoError::ResourceLimit)?;
    }
    if peak > budget {
        return Err(GeoError::ResourceLimit.into());
    }
    let column = column_from_descriptor_bytes(descriptor, budget)?;
    let projected = viewport.project_column(&column)?;
    let mut kinds = Vec::with_capacity(records);
    let mut ids = Vec::with_capacity(records);
    let mut refs = Vec::with_capacity(records);
    let mut xs = Vec::with_capacity(records);
    let mut ys = Vec::with_capacity(records);
    let mut diameters = Vec::with_capacity(records);
    match projected.geometry {
        ProjectedGeoGeometry::Points(points) => {
            for (i, &id) in points.feature_ids.iter().enumerate() {
                kinds.push(0u8);
                refs.push(0);
                ids.push(id);
                xs.push(points.origin_x + points.xy[2 * i] as f64);
                ys.push(points.origin_y + points.xy[2 * i + 1] as f64);
                diameters.push(diameter);
            }
        }
        ProjectedGeoGeometry::Outlines(lines) => {
            for (i, &id) in lines.feature_ids.iter().enumerate() {
                for v in lines.offsets[i] as usize..lines.offsets[i + 1] as usize {
                    kinds.push(1u8);
                    refs.push(0);
                    ids.push(id);
                    xs.push(lines.origin_x + lines.xy[2 * v] as f64);
                    ys.push(lines.origin_y + lines.xy[2 * v + 1] as f64);
                    diameters.push(0.0);
                }
                // A finite, zero-size offscreen scatter record breaks the
                // polyline run. Its transparent style prevents any paint, and
                // canonical Scene validation never receives NaN (§19).
                kinds.push(0u8);
                refs.push(1);
                ids.push(id);
                xs.push(-1.0);
                ys.push(-1.0);
                diameters.push(0.0);
            }
        }
    }
    let layout = PlotLayout::new(viewport.width, viewport.height, 0.0, 0.0, 0.0, 0.0)?;
    let x_scale = AxisScale::new(
        ScaleKind::Linear,
        0.0,
        viewport.width,
        0.0,
        viewport.width,
        1.0,
        false,
    )?;
    // These inputs are already screen-space caches. Identity scales avoid
    // geographic/Cartesian domain reinterpretation or a second y inversion.
    let y_scale = AxisScale::new(
        ScaleKind::Linear,
        0.0,
        viewport.height,
        0.0,
        viewport.height,
        1.0,
        false,
    )?;
    let mut chrome = SceneChromeStyle {
        x_major_ticks: Some(Vec::new()),
        y_major_ticks: Some(Vec::new()),
        ..SceneChromeStyle::default()
    };
    chrome.x_axis.tick_sides = 0;
    chrome.x_axis.tick_label_sides = 0;
    chrome.y_axis.tick_sides = 0;
    chrome.y_axis.tick_label_sides = 0;
    chrome.x_axis.axis_rgba = [0; 4];
    chrome.y_axis.axis_rgba = [0; 4];
    chrome.label_rgba = [0; 4];
    let zeros = vec![0.0; kinds.len()];
    let symbols = vec![0u8; kinds.len()];
    let default = crate::kernels::default_mark_rgba8();
    let fill: [u8; 4] = if u32_at(12) & 2 != 0 {
        bytes[96..100].try_into().unwrap()
    } else {
        default
    };
    let stroke: [u8; 4] = if u32_at(12) & 4 != 0 {
        bytes[100..104].try_into().unwrap()
    } else {
        default
    };
    let scene = SceneBatch::new_with_chrome_literal_ids(
        layout,
        1,
        2,
        x_scale,
        y_scale,
        chrome,
        SceneChromeText::default(),
        &kinds,
        &ids,
        &refs,
        &[fill[0], fill[1], fill[2], fill[3], 0, 0, 0, 0],
        &[stroke[0], stroke[1], stroke[2], stroke[3], 0, 0, 0, 0],
        &[width, 0.0],
        &diameters,
        &symbols,
        &xs,
        &ys,
        &zeros,
        &zeros,
    )?
    .encode();
    if scene.len() > budget {
        return Err(GeoError::ResourceLimit.into());
    }
    Ok(scene)
}
