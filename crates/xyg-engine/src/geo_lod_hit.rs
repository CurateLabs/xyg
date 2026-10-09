//! Bounded Rust-owned hover/picking over published geographic LOD caches.
use crate::geo::{GeoError, GeoGeometry};
use crate::geo_layers::{GeoStyle, validate_style};
use crate::geo_lod::{
    CLUSTER_CELL_LIMIT, DENSITY_CELL_LIMIT, DIRECT_VERTEX_LIMIT, GeoDirectPoint, GeoLodKey,
    GeoPointOutput, GeoPointResult, GeoReducedKind,
};
use crate::geo_lod_scene::cluster_diameter;
use crate::geo_source::{MAX_PROCESSOR_BYTES, SourceError};
use crate::geo_viewport::GeoViewport;
use crate::scene::interaction_marker_hit_with_tolerance;
type Result<T> = std::result::Result<T, SourceError>;
pub const MAX_LOD_HITS: usize = 4096;
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoLodHitMode {
    Topmost,
    All,
}
#[derive(Debug, Clone, Copy)]
pub struct GeoLodHitQuery {
    pub x: f64,
    pub y: f64,
    pub tolerance: f64,
    pub mode: GeoLodHitMode,
    pub max_hits: usize,
}
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum GeoLodHit {
    Direct(GeoDirectPoint),
    Cell { ordinal: u32, count: u64 },
}
#[derive(Debug)]
pub struct GeoLodHits {
    pub key: GeoLodKey,
    pub query: GeoLodHitQuery,
    pub hits: Vec<GeoLodHit>,
}
fn invalid() -> SourceError {
    SourceError::Geometry(GeoError::InvalidArgument)
}
pub fn reservation_bytes(query: GeoLodHitQuery) -> Result<usize> {
    if ![query.x, query.y, query.tolerance]
        .iter()
        .all(|v| v.is_finite())
    {
        return Err(GeoError::NonFiniteCoordinate.into());
    }
    if query.tolerance < 0.
        || !(query.tolerance as f32).is_finite()
        || query.max_hits == 0
        || query.max_hits > MAX_LOD_HITS
    {
        return Err(invalid());
    }
    query
        .max_hits
        .checked_mul(std::mem::size_of::<GeoLodHit>())
        .and_then(|n| n.checked_add(8192))
        .ok_or(SourceError::ResourceLimit)
}
/// Caller reserves source/old-output/candidate allocations before invoking this
/// helper. Product protocol keeps the hit packet under a durable derived lease.
pub fn hit(
    result: &GeoPointResult,
    style: GeoStyle,
    query: GeoLodHitQuery,
    budget: usize,
) -> Result<GeoLodHits> {
    let reserve = reservation_bytes(query)?;
    if reserve > budget || budget > MAX_PROCESSOR_BYTES {
        return Err(SourceError::ResourceLimit);
    }
    validate_style(style)?;
    let k = result.key.camera;
    let camera = GeoViewport {
        crs: k.crs,
        center_x: f64::from_bits(k.center_x_bits),
        center_y: f64::from_bits(k.center_y_bits),
        zoom: f64::from_bits(k.zoom_bits),
        width: f64::from_bits(k.width_bits),
        height: f64::from_bits(k.height_bits),
        bearing_deg: f64::from_bits(k.bearing_deg_bits),
        pitch_deg: f64::from_bits(k.pitch_deg_bits),
        world_wrap: k.world_wrap,
    };
    camera.validate()?;
    if camera.rebuild_key()? != k
        || !matches!(
            result.key.identity.geometry,
            GeoGeometry::Point | GeoGeometry::MultiPoint
        )
    {
        return Err(invalid());
    }
    let mut out = GeoLodHits {
        key: result.key,
        query,
        hits: Vec::with_capacity(query.max_hits),
    };
    if query.x < 0. || query.y < 0. || query.x >= camera.width || query.y >= camera.height {
        return Ok(out);
    }
    let fill = crate::css::apply_opacity_rgba8(style.fill, style.opacity as f32)[3] > 0;
    let stroke = crate::css::apply_opacity_rgba8(style.stroke, style.opacity as f32)[3] > 0;
    let mut push = |value| -> Result<bool> {
        if out.hits.len() == query.max_hits {
            return Err(SourceError::ResourceLimit);
        }
        out.hits.push(value);
        Ok(query.mode == GeoLodHitMode::Topmost)
    };
    match &result.output {
        GeoPointOutput::Direct(points) => {
            if !result.key.direct || points.len() > DIRECT_VERTEX_LIMIT {
                return Err(invalid());
            }
            if style.diameter == 0. || (!fill && !stroke) {
                return Ok(out);
            }
            // Last painted point is first. All mode preserves this paint order,
            // including distinct vertices/source rows with identical literal IDs.
            for point in points.iter().rev() {
                if !point.x.is_finite()
                    || !point.y.is_finite()
                    || point.identity.source_row >= result.key.identity.source_rows
                {
                    return Err(invalid());
                }
                if interaction_marker_hit_with_tolerance(
                    style.symbol,
                    style.diameter,
                    style.stroke_width,
                    fill,
                    stroke,
                    query.x - point.x,
                    query.y - point.y,
                    query.tolerance,
                ) && push(GeoLodHit::Direct(*point))?
                {
                    break;
                }
            }
        }
        GeoPointOutput::Reduced(cells) => {
            let columns = result.key.columns as usize;
            let rows = result.key.rows as usize;
            let cap = match result.key.kind {
                GeoReducedKind::Cluster => CLUSTER_CELL_LIMIT,
                GeoReducedKind::Density => DENSITY_CELL_LIMIT,
            };
            if result.key.direct
                || columns == 0
                || rows == 0
                || columns.checked_mul(rows) != Some(cells.len())
                || cells.len() > cap
            {
                return Err(invalid());
            }
            // Aggregate colors have palette alpha255 modulated once by style opacity.
            if crate::css::apply_opacity_rgba8([255; 4], style.opacity as f32)[3] == 0 {
                return Ok(out);
            }
            match result.key.kind {
                GeoReducedKind::Cluster => {
                    let maximum = cells.iter().map(|c| c.count).max().unwrap_or(0).max(1) as f64;
                    for (ordinal, cell) in cells.iter().enumerate().rev() {
                        if cell.count == 0 {
                            continue;
                        }
                        if !cell.x.is_finite() || !cell.y.is_finite() {
                            return Err(invalid());
                        }
                        if interaction_marker_hit_with_tolerance(
                            0,
                            cluster_diameter(cell.count, maximum),
                            0.,
                            true,
                            false,
                            query.x - cell.x,
                            query.y - cell.y,
                            query.tolerance,
                        ) && push(GeoLodHit::Cell {
                            ordinal: ordinal as u32,
                            count: cell.count,
                        })? {
                            break;
                        }
                    }
                }
                GeoReducedKind::Density => {
                    // Density paints one top-first image over the viewport. A
                    // hit is its exact occupied pixel cell, not a nearest centroid.
                    let column = ((query.x / camera.width * columns as f64).floor() as usize)
                        .min(columns - 1);
                    let row =
                        ((query.y / camera.height * rows as f64).floor() as usize).min(rows - 1);
                    let ordinal = row * columns + column;
                    if cells[ordinal].count != 0 {
                        push(GeoLodHit::Cell {
                            ordinal: ordinal as u32,
                            count: cells[ordinal].count,
                        })?;
                    }
                }
            }
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo::{GeoCrs, GeoGeometry};
    use crate::geo_lod::{GeoLodIdentity, GeoPointCell};
    use crate::geo_source::{FeatureRef, TimePredicate};
    fn result(output: GeoPointOutput) -> GeoPointResult {
        let direct = matches!(output, GeoPointOutput::Direct(_));
        GeoPointResult {
            key: GeoLodKey {
                identity: GeoLodIdentity {
                    source_digest: [7; 8],
                    generation: 99,
                    source_rows: 3,
                    crs: GeoCrs::Epsg4326,
                    geometry: GeoGeometry::MultiPoint,
                    layer_id: u64::MAX,
                    style_revision: 5,
                    state_revision: 6,
                },
                camera: GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 24., 800., 600., 0., 0., true)
                    .unwrap()
                    .rebuild_key()
                    .unwrap(),
                time: TimePredicate::All,
                kind: GeoReducedKind::Cluster,
                direct,
                columns: if direct { 0 } else { 2 },
                rows: if direct { 0 } else { 1 },
            },
            output,
            visible_vertices: 3,
            projected_vertices: 3,
            grid_capped: false,
            selection: None,
        }
    }
    fn point(id: u64, row: u64, vertex: u32, x: f64) -> GeoDirectPoint {
        GeoDirectPoint {
            identity: FeatureRef {
                feature_id: id,
                source_row: row,
                chunk_index: 9,
                row: row as u32,
            },
            vertex,
            x,
            y: 300.,
        }
    }
    fn query(x: f64, y: f64) -> GeoLodHitQuery {
        GeoLodHitQuery {
            x,
            y,
            tolerance: 0.,
            mode: GeoLodHitMode::All,
            max_hits: 4096,
        }
    }
    #[test]
    fn exact_ids_vertices_paint_order_shape_and_atomic_admission() {
        let r = result(GeoPointOutput::Direct(vec![
            point(u64::MAX, 0, 0, 400.),
            point(1 << 63, 1, 8, 400.),
            point(u64::MAX, 2, 1, 402.386),
        ]));
        let style = GeoStyle {
            diameter: 2.,
            stroke_width: 0.,
            ..GeoStyle::default()
        };
        let hits = hit(&r, style, query(400., 300.), MAX_PROCESSOR_BYTES).unwrap();
        assert_eq!(
            hits.hits,
            vec![
                GeoLodHit::Direct(point(1 << 63, 1, 8, 400.)),
                GeoLodHit::Direct(point(u64::MAX, 0, 0, 400.))
            ]
        );
        assert_eq!(hits.key, r.key);
        assert_eq!(
            hit(&r, style, query(402.386, 300.), MAX_PROCESSOR_BYTES)
                .unwrap()
                .hits,
            vec![GeoLodHit::Direct(point(u64::MAX, 2, 1, 402.386))]
        );
        assert!(
            hit(&r, style, query(400.9, 300.9), MAX_PROCESSOR_BYTES)
                .unwrap()
                .hits
                .is_empty()
        );
        let mut q = query(400., 300.);
        q.max_hits = 1;
        assert!(matches!(
            hit(&r, style, q, MAX_PROCESSOR_BYTES),
            Err(SourceError::ResourceLimit)
        ));
        q.mode = GeoLodHitMode::Topmost;
        assert_eq!(
            hit(&r, style, q, MAX_PROCESSOR_BYTES).unwrap().hits.len(),
            1
        );
        q.x = f64::NAN;
        assert!(hit(&r, style, q, MAX_PROCESSOR_BYTES).is_err());
    }
    #[test]
    fn glyph_hollow_line_tolerance_alpha_and_viewport() {
        let r = result(GeoPointOutput::Direct(vec![point(u64::MAX, 0, 0, 400.)]));
        for symbol in 0..19 {
            let style = GeoStyle {
                symbol,
                diameter: 20.,
                stroke_width: 2.,
                ..GeoStyle::default()
            };
            // All nineteen canonical glyphs paint their center or its outline;
            // distant points never become hits through their bounding square.
            assert!(
                !hit(&r, style, query(400., 300.), MAX_PROCESSOR_BYTES)
                    .unwrap()
                    .hits
                    .is_empty(),
                "symbol {symbol}"
            );
            assert!(
                hit(&r, style, query(430., 330.), MAX_PROCESSOR_BYTES)
                    .unwrap()
                    .hits
                    .is_empty()
            );
        }
        let style = GeoStyle {
            fill: [0; 4],
            stroke_width: 2.,
            diameter: 20.,
            ..GeoStyle::default()
        };
        assert!(
            hit(&r, style, query(400., 300.), MAX_PROCESSOR_BYTES)
                .unwrap()
                .hits
                .is_empty()
        );
        assert_eq!(
            hit(&r, style, query(410., 300.), MAX_PROCESSOR_BYTES)
                .unwrap()
                .hits
                .len(),
            1
        );
        let mut q = query(411., 300.);
        q.tolerance = 1.;
        assert_eq!(
            hit(&r, style, q, MAX_PROCESSOR_BYTES).unwrap().hits.len(),
            1
        );
        assert!(
            hit(
                &r,
                GeoStyle {
                    opacity: 0.,
                    ..style
                },
                q,
                MAX_PROCESSOR_BYTES
            )
            .unwrap()
            .hits
            .is_empty()
        );
        assert!(
            hit(&r, style, query(-1., 300.), MAX_PROCESSOR_BYTES)
                .unwrap()
                .hits
                .is_empty()
        );
    }
    #[test]
    fn clusters_follow_painted_area_density_exact_top_first_cells() {
        let mut r = result(GeoPointOutput::Reduced(vec![
            GeoPointCell {
                count: 1,
                x: 100.,
                y: 300.,
            },
            GeoPointCell {
                count: 100,
                x: 500.,
                y: 300.,
            },
        ]));
        let style = GeoStyle::default();
        assert_eq!(
            hit(&r, style, query(511.9, 300.), MAX_PROCESSOR_BYTES)
                .unwrap()
                .hits,
            vec![GeoLodHit::Cell {
                ordinal: 1,
                count: 100
            }]
        );
        assert!(
            hit(&r, style, query(112., 300.), MAX_PROCESSOR_BYTES)
                .unwrap()
                .hits
                .is_empty()
        );
        r.key.kind = GeoReducedKind::Density;
        assert_eq!(
            hit(&r, style, query(399.9, 0.), MAX_PROCESSOR_BYTES)
                .unwrap()
                .hits,
            vec![GeoLodHit::Cell {
                ordinal: 0,
                count: 1
            }]
        );
        assert_eq!(
            hit(&r, style, query(400., 599.), MAX_PROCESSOR_BYTES)
                .unwrap()
                .hits,
            vec![GeoLodHit::Cell {
                ordinal: 1,
                count: 100
            }]
        );
        if let GeoPointOutput::Reduced(c) = &mut r.output {
            c[0].count = 0;
        }
        let mut q = query(399., 300.);
        q.tolerance = 100.;
        assert!(
            hit(&r, style, q, MAX_PROCESSOR_BYTES)
                .unwrap()
                .hits
                .is_empty()
        );
    }
}
