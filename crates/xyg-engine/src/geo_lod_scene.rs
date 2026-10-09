//! Screen-bounded point LOD lowers to the existing Scene; §28/§29.
use crate::geo::GeoError;
use crate::geo_layers::GeoStyle;
use crate::geo_lod::{GeoPointOutput, GeoPointResult, GeoReducedKind};
use crate::scene::{
    AxisScale, PlotLayout, ScaleKind, SceneBatch, SceneChromeStyle, SceneChromeText, SceneImage,
    SceneRecordKind,
};

/// Aggregate IDs are cell ordinals, not representative source feature IDs.
/// The full GeoPointResult key and paged membership remain the provenance authority.
pub struct GeoLodScene {
    pub scene: Vec<u8>,
    pub aggregate: bool,
    pub dropped_channels: u32,
}

/// The single bounded area channel used by aggregate painting and exact hit testing.
pub(crate) fn cluster_diameter(count: u64, maximum: f64) -> f64 {
    let fraction = if maximum == 1. {
        0.
    } else {
        (count as f64 - 1.) / (maximum - 1.)
    };
    (36. + fraction * (576. - 36.)).sqrt()
}

pub fn compile(
    result: &GeoPointResult,
    style: GeoStyle,
    budget: usize,
) -> Result<GeoLodScene, GeoError> {
    let width = f64::from_bits(result.key.camera.width_bits);
    let height = f64::from_bits(result.key.camera.height_bits);
    crate::geo_layers::validate_style(style)?;
    let count = match &result.output {
        GeoPointOutput::Direct(points) => points.len(),
        GeoPointOutput::Reduced(cells) => cells.len(),
    };
    let unit = if result.key.kind == GeoReducedKind::Density && !result.key.direct {
        64
    } else {
        1024
    };
    let peak = count
        .checked_mul(unit)
        .and_then(|n| n.checked_add(8192))
        .ok_or(GeoError::ResourceLimit)?;
    if peak > budget || budget > crate::geo_source::MAX_PROCESSOR_BYTES {
        return Err(GeoError::ResourceLimit);
    }
    if let Some(selection) = &result.selection {
        selection
            .validate_result(result)
            .map_err(|_| GeoError::InvalidArgument)?;
    }
    let selected_fill = result.selection.as_ref().map(|selection| {
        crate::css::apply_opacity_rgba8(selection.state().style().fill, style.opacity as f32)
    });
    let aggregate = !result.key.direct;
    let mut kinds = Vec::new();
    let mut ids = Vec::new();
    let mut xs = Vec::new();
    let mut ys = Vec::new();
    let mut diameters = Vec::new();
    let mut images = Vec::new();
    let mut refs = Vec::new();
    let mut fill = Vec::new();
    let mut stroke = Vec::new();
    let mut widths = Vec::new();
    let mut push = |id, x, y, diameter, color: [u8; 4], kind: SceneRecordKind| {
        kinds.push(kind as u8);
        ids.push(id);
        xs.push(x);
        ys.push(y);
        diameters.push(diameter);
        refs.push(widths.len() as u32);
        fill.extend(color);
        stroke.extend(if aggregate {
            [0; 4]
        } else {
            crate::css::apply_opacity_rgba8(style.stroke, style.opacity as f32)
        });
        widths.push(if aggregate { 0. } else { style.stroke_width });
    };
    match &result.output {
        GeoPointOutput::Direct(points) => {
            if !result.key.direct || points.len() > crate::geo_lod::DIRECT_VERTEX_LIMIT {
                return Err(GeoError::InvalidArgument);
            }
            let color = crate::css::apply_opacity_rgba8(style.fill, style.opacity as f32);
            for point in points {
                push(
                    point.identity.feature_id,
                    point.x,
                    point.y,
                    style.diameter,
                    if result.selection.as_ref().is_some_and(|selection| {
                        selection.state().contains(point.identity.feature_id)
                    }) {
                        selected_fill.unwrap()
                    } else {
                        color
                    },
                    SceneRecordKind::Scatter,
                );
            }
        }
        GeoPointOutput::Reduced(cells) => {
            let columns = result.key.columns as usize;
            let rows = result.key.rows as usize;
            if result.key.direct
                || columns.checked_mul(rows) != Some(cells.len())
                || cells.is_empty()
            {
                return Err(GeoError::InvalidArgument);
            }
            let maximum = cells
                .iter()
                .map(|cell| cell.count)
                .max()
                .unwrap_or(0)
                .max(1) as f64;
            let stops = crate::colormap::colormap_named_stops("viridis");
            let color = |count: u64, index: usize| {
                if count == 0 {
                    [0; 4]
                } else {
                    let base = crate::css::apply_opacity_rgba8(
                        crate::kernels::colormap_color(
                            (count as f64).ln_1p() / maximum.ln_1p(),
                            &stops,
                            255,
                        ),
                        style.opacity as f32,
                    );
                    if let Some(selection) = &result.selection {
                        crate::geo_linked_state::selected_fraction_color(
                            base,
                            selected_fill.unwrap(),
                            selection.cell_selected_count(index),
                            count,
                        )
                    } else {
                        base
                    }
                }
            };
            match result.key.kind {
                GeoReducedKind::Cluster => {
                    if cells.len() > crate::geo_lod::CLUSTER_CELL_LIMIT {
                        return Err(GeoError::ResourceLimit);
                    }
                    for (index, cell) in cells.iter().enumerate() {
                        if cell.count != 0 {
                            push(
                                index as u64,
                                cell.x,
                                cell.y,
                                cluster_diameter(cell.count, maximum),
                                color(cell.count, index),
                                SceneRecordKind::Scatter,
                            );
                        }
                    }
                }
                GeoReducedKind::Density => {
                    if cells.len() > crate::geo_lod::DENSITY_CELL_LIMIT {
                        return Err(GeoError::ResourceLimit);
                    }
                    let rgba: Vec<u8> = cells
                        .iter()
                        .enumerate()
                        .flat_map(|(i, cell)| color(cell.count, i))
                        .collect();
                    push(
                        result.key.identity.layer_id,
                        0.,
                        0.,
                        0.,
                        [255; 4],
                        SceneRecordKind::Image,
                    );
                    images.push(SceneImage {
                        stable_id: result.key.identity.layer_id,
                        width: columns as u32,
                        height: rows as u32,
                        rgba,
                    });
                }
            }
        }
    }
    let layout =
        PlotLayout::new(width, height, 0., 0., 0., 0.).map_err(|_| GeoError::InvalidArgument)?;
    let axis = |max| {
        AxisScale::new(ScaleKind::Linear, 0., max, 0., max, 1., false)
            .map_err(|_| GeoError::InvalidArgument)
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
    chrome.label_rgba = [0; 4];
    let zeros = vec![0.; kinds.len()];
    let symbols = vec![if aggregate { 0 } else { style.symbol }; kinds.len()];
    let mut x1 = zeros.clone();
    let mut y1 = zeros;
    if !images.is_empty() {
        x1[0] = width;
        y1[0] = height;
    }
    let scene = SceneBatch::new_with_chrome_literal_ids(
        layout,
        1,
        2,
        axis(width)?,
        axis(height)?,
        chrome,
        SceneChromeText::default(),
        &kinds,
        &ids,
        &refs,
        &fill,
        &stroke,
        &widths,
        &diameters,
        &symbols,
        &xs,
        &ys,
        &x1,
        &y1,
    )
    .map_err(|_| GeoError::InvalidArgument)?
    .with_images(images)
    .map_err(|_| GeoError::InvalidArgument)?
    .encode();
    if scene.len() > budget {
        return Err(GeoError::ResourceLimit);
    }
    Ok(GeoLodScene {
        scene,
        aggregate,
        dropped_channels: if aggregate { 7 } else { 0 },
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo::{GeoCrs, GeoGeometry};
    use crate::geo_lod::{GeoDirectPoint, GeoLodIdentity, GeoLodKey, GeoPointCell};
    use crate::geo_source::{FeatureRef, TimePredicate};
    use crate::geo_viewport::GeoViewport;
    fn result(direct: bool, kind: GeoReducedKind, output: GeoPointOutput) -> GeoPointResult {
        let camera =
            GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 0., 128., 96., 0., 0., true).unwrap();
        GeoPointResult {
            key: GeoLodKey {
                identity: GeoLodIdentity {
                    source_digest: [1; 8],
                    generation: u64::MAX,
                    source_rows: 50_000,
                    crs: GeoCrs::Epsg4326,
                    geometry: GeoGeometry::Point,
                    layer_id: u64::MAX,
                    style_revision: 3,
                    state_revision: 4,
                },
                camera: camera.rebuild_key().unwrap(),
                time: TimePredicate::Instant(-1),
                kind,
                direct,
                columns: if direct { 0 } else { 2 },
                rows: if direct { 0 } else { 1 },
            },
            output,
            visible_vertices: 2,
            projected_vertices: 4,
            grid_capped: false,
            selection: None,
        }
    }
    #[test]
    fn direct_preserves_every_u64_bit_and_resolves_opacity_once() {
        let result = result(
            true,
            GeoReducedKind::Cluster,
            GeoPointOutput::Direct(vec![GeoDirectPoint {
                identity: FeatureRef {
                    chunk_index: 0,
                    row: 0,
                    source_row: 0,
                    feature_id: u64::MAX,
                },
                vertex: 0,
                x: 32.,
                y: 24.,
            }]),
        );
        let scene = compile(
            &result,
            GeoStyle {
                fill: [255, 0, 0, 255],
                stroke: [0, 0, 0, 255],
                opacity: 0.5,
                ..GeoStyle::default()
            },
            1 << 20,
        )
        .unwrap();
        assert!(!scene.aggregate);
        assert_eq!(scene.dropped_channels, 0);
        let doc = crate::scene::SceneDocument::decode(&scene.scene).unwrap();
        assert_eq!(doc.interaction_records()[0].stable_id, u64::MAX);
        assert_eq!(doc.interaction_style(0).unwrap().0, [255, 0, 0, 128]);
        assert_eq!(doc.interaction_style(0).unwrap().1, [0, 0, 0, 128]);
    }
    #[test]
    fn reduced_cluster_has_explicit_cell_identity_not_source_representative() {
        let result = result(
            false,
            GeoReducedKind::Cluster,
            GeoPointOutput::Reduced(vec![
                GeoPointCell {
                    count: 0,
                    x: 0.,
                    y: 0.,
                },
                GeoPointCell {
                    count: 1_000_000_000,
                    x: 64.,
                    y: 48.,
                },
            ]),
        );
        let scene = compile(&result, GeoStyle::default(), 1 << 20).unwrap();
        assert!(scene.aggregate);
        assert_eq!(scene.dropped_channels, 7);
        let doc = crate::scene::SceneDocument::decode(&scene.scene).unwrap();
        assert_eq!(doc.interaction_records().len(), 1);
        assert_eq!(doc.interaction_records()[0].stable_id, 1);
        assert_eq!(doc.interaction_records()[0].diameter, 24.);
    }
    #[test]
    fn density_top_first_empty_cell_transparent_and_deterministic() {
        let result = result(
            false,
            GeoReducedKind::Density,
            GeoPointOutput::Reduced(vec![
                GeoPointCell {
                    count: 0,
                    x: 0.,
                    y: 0.,
                },
                GeoPointCell {
                    count: 9,
                    x: 64.,
                    y: 48.,
                },
            ]),
        );
        let a = compile(&result, GeoStyle::default(), 1 << 20).unwrap();
        let b = compile(&result, GeoStyle::default(), 1 << 20).unwrap();
        assert_eq!(a.scene, b.scene);
        let doc = crate::scene::SceneDocument::decode(&a.scene).unwrap();
        let image = doc.interaction_image(u64::MAX).unwrap();
        assert_eq!(&image.rgba[..4], &[0; 4]);
        assert_eq!(image.rgba[7], 255);
        assert!(matches!(
            compile(&result, GeoStyle::default(), 1),
            Err(GeoError::ResourceLimit)
        ));
    }
}
