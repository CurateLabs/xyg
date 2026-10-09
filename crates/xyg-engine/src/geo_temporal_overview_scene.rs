//! Truthfully labelled coarse data-domain cells; exact temporal counts, §17/§28.
use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
use crate::geo_source::SourceError;
use crate::geo_temporal_overview::GeoOverviewResult;
use crate::geo_viewport::{GeoViewport, WEB_MERCATOR_MAX};
use crate::scene::{
    AxisScale, PlotLayout, ScaleKind, SceneBatch, SceneChromeStyle, SceneChromeText, SceneLabel,
    SceneRecordKind,
};

pub const LABEL: &str = "Exact temporal counts by data-domain cell; spatial refinement pending";
pub const MAX_RECORDS: usize = 12_288;
pub const SCRATCH_BYTES: usize = 8 * 1024 * 1024;
pub const DATA_CREDIT: usize = 16 * 1024 * 1024;
pub const MAX_ENCODED_SCENE_BYTES: usize = crate::scene::SCENE_BATCH_HEADER_BYTES
    + 256 * crate::scene::SCENE_STYLE_RECORD_BYTES
    + MAX_RECORDS * crate::scene::SCENE_BATCH_RECORD_BYTES
    + 65_536; // fixed chrome and one bounded label, with ample framing margin

/// Caller reserves SCRATCH_BYTES before entry. IDs here are explicit domain-cell
/// ordinals, never source-feature identities; the typed result is their authority.
pub(crate) fn compile(
    result: &GeoOverviewResult,
    camera: GeoViewport,
) -> Result<Vec<u8>, SourceError> {
    if camera.rebuild_key()? != result.snapshot().camera {
        return Err(SourceError::StaleSource);
    }
    compile_counts(result.counts(), camera)
}

/// Pure lowering of inert domain counts; never reconstructs source/query authority.
/// Caller admits SCRATCH_BYTES before allocation.
pub(crate) fn compile_counts(
    counts: &[u64; 256],
    camera: GeoViewport,
) -> Result<Vec<u8>, SourceError> {
    camera.rebuild_key()?;
    // Explicit output decoration cannot change the projected plot rectangle.
    // Fail closed if the exact nonfinal notice cannot fit; never truncate it.
    let label_font = 8.;
    if crate::scene::scene_text_advance(LABEL, label_font) + 8. > camera.width
        || label_font * 1.3 + 8. > camera.height
    {
        return Err(SourceError::ResourceLimit);
    }
    let mut kinds = Vec::new();
    let mut ids = Vec::new();
    let mut refs = Vec::new();
    let mut fill = Vec::new();
    let mut xs = Vec::new();
    let mut ys = Vec::new();
    let maximum = *counts.iter().max().unwrap();
    for (cell, &count) in counts.iter().enumerate() {
        if count == 0 {
            continue;
        }
        let step = 2. * WEB_MERCATOR_MAX / 16.;
        let x = -WEB_MERCATOR_MAX + (cell % 16) as f64 * step;
        let y = -WEB_MERCATOR_MAX + (cell / 16) as f64 * step;
        let right = -WEB_MERCATOR_MAX + (cell % 16 + 1) as f64 * step;
        let top = -WEB_MERCATOR_MAX + (cell / 16 + 1) as f64 * step;
        let mut xy = [x, y, right, y, right, top, x, top, x, y];
        if camera.crs == GeoCrs::Epsg4326 {
            for point in xy.chunks_exact_mut(2) {
                // Preserve the western -180 boundary rather than canonicalizing
                // it onto +180; this is an edge of a cell, not a point alias.
                point[0] = point[0] / WEB_MERCATOR_MAX * 180.;
                point[1] = crate::geo_viewport::mercator_to_lonlat(0., point[1]).1;
            }
        }
        let column = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::Polygon,
            crs: camera.crs,
            xy: &xy,
            validity: &[1],
            feature_ids: Some(&[cell as u64]),
            offsets0: &[0, 1],
            offsets1: &[0, 5],
            offsets2: &[],
            limits: GeoLimits::default(),
        })?;
        let projection = camera.project_column(&column)?;
        let polygons = projection.polygons.ok_or(SourceError::InvalidFrame)?;
        for polygon in 0..polygons.feature_ids.len() {
            let first = polygons.polygon_offsets[polygon] as usize;
            let last = polygons.polygon_offsets[polygon + 1] as usize;
            let rings: Vec<Vec<f64>> = (first..last)
                .map(|ring| {
                    let a = polygons.ring_offsets[ring] as usize * 2;
                    let b = polygons.ring_offsets[ring + 1] as usize * 2;
                    polygons.xy[a..b]
                        .chunks_exact(2)
                        .flat_map(|p| {
                            [
                                p[0] as f64 + polygons.origin_x,
                                p[1] as f64 + polygons.origin_y,
                            ]
                        })
                        .collect()
                })
                .collect();
            let input: Vec<_> = rings
                .iter()
                .enumerate()
                .map(|(i, r)| (r.as_slice(), polygons.ring_is_hole[first + i] != 0))
                .collect();
            for triangle in crate::geo_fill::tessellate(&input)? {
                if kinds.len() + 3 > MAX_RECORDS {
                    return Err(SourceError::ResourceLimit);
                }
                for point in triangle.chunks_exact(2) {
                    kinds.push(SceneRecordKind::Triangle as u8);
                    ids.push(cell as u64);
                    refs.push(cell as u32);
                    xs.push(point[0]);
                    ys.push(point[1]);
                }
            }
        }
    }
    for &count in counts {
        let strength = if count == 0 {
            0
        } else {
            (255. * ((count as f64).ln_1p() / (maximum as f64).ln_1p())).round() as u8
        };
        fill.extend([255 - strength, 128, 255, 200]);
    }
    let n = kinds.len();
    let zeros = vec![0.; n];
    let symbols = vec![0; n];
    let axis = |max| {
        AxisScale::new(ScaleKind::Linear, 0., max, 0., max, 1., false)
            .map_err(|_| SourceError::InvalidFrame)
    };
    let mut chrome = SceneChromeStyle {
        x_major_ticks: Some(Vec::new()),
        y_major_ticks: Some(Vec::new()),
        ..SceneChromeStyle::default()
    };
    for axis in [&mut chrome.x_axis, &mut chrome.y_axis] {
        axis.tick_sides = 0;
        axis.tick_label_sides = 0;
        axis.axis_rgba = [0; 4];
    }
    let scene = SceneBatch::new_with_chrome_literal_ids_and_decorations(
        PlotLayout::new(camera.width, camera.height, 0., 0., 0., 0.)
            .map_err(|_| SourceError::InvalidFrame)?,
        1,
        2,
        axis(camera.width)?,
        axis(camera.height)?,
        chrome,
        SceneChromeText::from_parts("", "", "").map_err(|_| SourceError::InvalidFrame)?,
        None,
        vec![SceneLabel {
            stable_id: 0,
            x: 4.,
            y: camera.height - 4.,
            font_size: label_font,
            rgba: [0, 0, 0, 255],
            anchor: 0,
            rotation: 0.,
            text: LABEL.to_owned(),
        }],
        &kinds,
        &ids,
        &refs,
        &fill,
        &vec![0; 256 * 4],
        &vec![0.; 256],
        &zeros,
        &symbols,
        &xs,
        &ys,
        &zeros,
        &zeros,
    )
    .map_err(|_| SourceError::InvalidFrame)?
    .encode();
    if scene.len() > MAX_ENCODED_SCENE_BYTES {
        return Err(SourceError::ResourceLimit);
    }
    Ok(scene)
}
