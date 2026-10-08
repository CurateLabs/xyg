//! Host-neutral bounded geographic camera commands (#48, dossier §4/§16/§29).
//! Hosts frame f64 source values; this module alone normalizes, transitions and projects.
use crate::geo::{column_from_descriptor_bytes, GeoCrs, GeoError, GeoGeometry};
use crate::geo_viewport::{GeoViewport, ProjectedGeoGeometry};

pub const REQUEST_BYTES: usize = 128;
pub const RESPONSE_BYTES: usize = 256;
pub const MAX_PROTOCOL_BYTES: usize = 384 * 1024 * 1024;

fn push_plane<T: Copy, const N: usize>(out: &mut Vec<u8>, values: &[T], encode: fn(T) -> [u8; N]) {
    for &value in values {
        out.extend_from_slice(&encode(value));
    }
    while !out.len().is_multiple_of(8) {
        out.push(0);
    }
}

/// Execute one complete `XYVC` v1 request and publish one `XYVR` v1 response.
/// Exact framing, geometry ceilings and conservative peak admission precede allocation.
pub fn execute(bytes: &[u8], budget: usize) -> Result<Vec<u8>, GeoError> {
    let invalid = GeoError::InvalidArgument;
    if budget > MAX_PROTOCOL_BYTES || bytes.len() > budget || budget < 8192 {
        return Err(GeoError::ResourceLimit);
    }
    if bytes.len() < REQUEST_BYTES || &bytes[..4] != b"XYVC" {
        return Err(invalid);
    }
    let u32_at = |i| u32::from_le_bytes(bytes[i..i + 4].try_into().unwrap());
    let f64_at = |i| f64::from_le_bytes(bytes[i..i + 8].try_into().unwrap());
    let op = u32_at(8);
    if u32_at(4) != 1
        || op > 10
        || u32_at(16) > 1
        || u32_at(20) != 0
        || bytes[120..128].iter().any(|&b| b != 0)
        || (op != 10 && bytes.len() != REQUEST_BYTES)
    {
        return Err(invalid);
    }
    let mut camera = GeoViewport::new(
        GeoCrs::from_u32(u32_at(12)).ok_or(GeoError::UnsupportedCrs)?,
        f64_at(24),
        f64_at(32),
        f64_at(40),
        f64_at(48),
        f64_at(56),
        f64_at(64),
        f64_at(72),
        u32_at(16) == 1,
    )?;
    let args = [f64_at(80), f64_at(88), f64_at(96), f64_at(104), f64_at(112)];
    let mut result = [0.0; 2];
    let mut xy = Vec::new();
    let mut ids = Vec::new();
    let mut offsets = Vec::new();
    let mut visible_ids = Vec::new();
    let mut polygon_xy = Vec::<f32>::new();
    let mut ring_offsets = Vec::<u32>::new();
    let mut polygon_offsets = Vec::<u32>::new();
    let mut polygon_ids = Vec::<u64>::new();
    let mut roles = Vec::<u8>::new();
    let mut polygon_origin = [0.0f64; 2];
    let mut response_bounds = None;
    let mut kind = 0u32;
    let mut digest = [0u8; 8];
    match op {
        0 => {}
        1 => {
            let (x, y) = camera.project(args[0], args[1])?;
            result = [x, y];
        }
        2 => {
            let (x, y) = camera.unproject(args[0], args[1])?;
            result = [x, y];
        }
        3 => camera.pan_by_pixels(args[0], args[1])?,
        4 => camera.set_zoom(args[0])?,
        5 => camera.resize(args[0], args[1])?,
        6 => camera.set_bearing(args[0])?,
        7 => camera.set_pitch(args[0])?,
        8 => camera.set_center(args[0], args[1])?,
        9 => camera.fit_bounds(args[0], args[1], args[2], args[3], args[4])?,
        10 => {
            let source = &bytes[REQUEST_BYTES..];
            if source.len() < 64 {
                return Err(invalid);
            }
            let geometry =
                GeoGeometry::from_u32(u32::from_le_bytes(source[8..12].try_into().unwrap()))
                    .ok_or(GeoError::TypeMismatch)?;
            let vertices = usize::try_from(u64::from_le_bytes(source[32..40].try_into().unwrap()))
                .map_err(|_| GeoError::ResourceLimit)?;
            let features = usize::try_from(u64::from_le_bytes(source[24..32].try_into().unwrap()))
                .map_err(|_| GeoError::ResourceLimit)?;
            let multiplier = if matches!(geometry, GeoGeometry::Point | GeoGeometry::MultiPoint) {
                1
            } else {
                6
            };
            let peak = vertices
                .checked_mul(multiplier)
                .and_then(|n| n.checked_mul(128))
                .and_then(|n| features.checked_mul(16).and_then(|v| n.checked_add(v)))
                .and_then(|n| bytes.len().checked_mul(3).and_then(|v| n.checked_add(v)))
                .and_then(|n| n.checked_add(32768))
                .ok_or(GeoError::ResourceLimit)?;
            let peak = if matches!(geometry, GeoGeometry::Polygon | GeoGeometry::MultiPolygon) {
                vertices
                    .checked_mul(4096)
                    .and_then(|n| features.checked_mul(512).and_then(|v| n.checked_add(v)))
                    .and_then(|n| peak.checked_add(n))
                    .ok_or(GeoError::ResourceLimit)?
            } else {
                peak
            };
            if peak > budget {
                return Err(GeoError::ResourceLimit);
            }
            let column = column_from_descriptor_bytes(source, budget)?;
            let projected = camera.project_column(&column)?;
            digest = projected.key.metadata_digest;
            visible_ids = projected.visible_feature_ids;
            response_bounds = projected.visible_bounds;
            if let Some(polygons) = projected.polygons {
                polygon_origin = [polygons.origin_x, polygons.origin_y];
                polygon_xy = polygons.xy;
                ring_offsets = polygons.ring_offsets;
                polygon_offsets = polygons.polygon_offsets;
                polygon_ids = polygons.feature_ids;
                roles = polygons.ring_is_hole;
            }
            match projected.geometry {
                ProjectedGeoGeometry::Points(points) => {
                    kind = 1;
                    result = [points.origin_x, points.origin_y];
                    xy = points.xy;
                    ids = points.feature_ids;
                }
                ProjectedGeoGeometry::Outlines(lines) => {
                    kind = 2;
                    result = [lines.origin_x, lines.origin_y];
                    xy = lines.xy;
                    ids = lines.feature_ids;
                    offsets = lines.offsets;
                }
            }
        }
        _ => return Err(invalid),
    }
    if result.iter().any(|v| !v.is_finite()) || xy.iter().any(|v| !v.is_finite()) {
        return Err(GeoError::NonFiniteCoordinate);
    }
    if op != 10 {
        response_bounds = Some(camera.bounds()?);
    }
    let key = camera.rebuild_key()?;
    let mut out = vec![0u8; RESPONSE_BYTES];
    out[..4].copy_from_slice(b"XYVR");
    for (at, value) in [
        (4, 1),
        (8, op),
        (12, key.crs as u32),
        (16, u32::from(key.world_wrap)),
        (20, kind),
    ] {
        out[at..at + 4].copy_from_slice(&value.to_le_bytes());
    }
    for (i, value) in [
        key.center_x_bits,
        key.center_y_bits,
        key.zoom_bits,
        key.width_bits,
        key.height_bits,
        key.bearing_deg_bits,
        key.pitch_deg_bits,
    ]
    .into_iter()
    .enumerate()
    {
        out[24 + i * 8..32 + i * 8].copy_from_slice(&value.to_le_bytes());
    }
    for (i, value) in result.into_iter().enumerate() {
        out[80 + i * 8..88 + i * 8].copy_from_slice(&value.to_le_bytes());
    }
    for (i, value) in [
        xy.len(),
        ids.len(),
        offsets.len(),
        visible_ids.len(),
        polygon_xy.len(),
        ring_offsets.len(),
        polygon_offsets.len(),
        polygon_ids.len(),
        roles.len(),
    ]
    .into_iter()
    .enumerate()
    {
        out[96 + i * 8..104 + i * 8].copy_from_slice(&(value as u64).to_le_bytes());
    }
    out[176..184].copy_from_slice(&digest);
    if let Some(bounds) = response_bounds {
        out[168..172].copy_from_slice(&1u32.to_le_bytes());
        for (i, value) in bounds.into_iter().enumerate() {
            out[184 + i * 8..192 + i * 8].copy_from_slice(&value.to_le_bytes());
        }
    }
    for (i, value) in polygon_origin.into_iter().enumerate() {
        out[216 + i * 8..224 + i * 8].copy_from_slice(&value.to_le_bytes());
    }
    push_plane(&mut out, &xy, f32::to_le_bytes);
    push_plane(&mut out, &ids, u64::to_le_bytes);
    push_plane(&mut out, &offsets, u32::to_le_bytes);
    push_plane(&mut out, &visible_ids, u64::to_le_bytes);
    push_plane(&mut out, &polygon_xy, f32::to_le_bytes);
    push_plane(&mut out, &ring_offsets, u32::to_le_bytes);
    push_plane(&mut out, &polygon_offsets, u32::to_le_bytes);
    push_plane(&mut out, &polygon_ids, u64::to_le_bytes);
    push_plane(&mut out, &roles, u8::to_le_bytes);
    if out.len() > budget {
        return Err(GeoError::ResourceLimit);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(op: u32, args: [f64; 5]) -> Vec<u8> {
        let mut b = vec![0u8; 128];
        b[..4].copy_from_slice(b"XYVC");
        for (at, v) in [(4, 1u32), (8, op), (12, 4326), (16, 1)] {
            b[at..at + 4].copy_from_slice(&v.to_le_bytes());
        }
        for (i, v) in [0., 0., 1., 800., 600., 0., 0.].into_iter().enumerate() {
            b[24 + i * 8..32 + i * 8].copy_from_slice(&f64::to_le_bytes(v));
        }
        for (i, v) in args.into_iter().enumerate() {
            b[80 + i * 8..88 + i * 8].copy_from_slice(&v.to_le_bytes());
        }
        b
    }
    #[test]
    fn commands_are_atomic_and_canonical() {
        let out = execute(&request(1, [0.; 5]), 65536).unwrap();
        assert_eq!(f64::from_le_bytes(out[80..88].try_into().unwrap()), 400.);
        assert_eq!(f64::from_le_bytes(out[88..96].try_into().unwrap()), 300.);
        assert_eq!(u32::from_le_bytes(out[168..172].try_into().unwrap()), 1);
        let camera =
            GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 1., 800., 600., 0., 0., true).unwrap();
        for (i, bound) in camera.bounds().unwrap().into_iter().enumerate() {
            assert_eq!(
                f64::from_le_bytes(out[184 + i * 8..192 + i * 8].try_into().unwrap()),
                bound
            );
        }
        let out = execute(&request(6, [720., 0., 0., 0., 0.]), 65536).unwrap();
        assert_eq!(u64::from_le_bytes(out[64..72].try_into().unwrap()), 0);
        assert_eq!(
            execute(&request(4, [25., 0., 0., 0., 0.]), 65536).unwrap_err(),
            GeoError::InvalidArgument
        );
    }
    #[test]
    fn framing_rejects_before_output() {
        let b = request(0, [0.; 5]);
        for n in 0..128 {
            assert!(execute(&b[..n], 65536).is_err());
        }
        let mut bad = b.clone();
        bad[127] = 1;
        assert!(execute(&bad, 65536).is_err());
        assert_eq!(execute(&b, 100).unwrap_err(), GeoError::ResourceLimit);
    }
}
