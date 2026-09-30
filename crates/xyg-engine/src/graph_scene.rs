//! Static export of composed graph charts (#34).
//!
//! Browsers paint a composed graph from Rust-resolved planes: per-item node
//! and edge paint, semantic halo/body/dash layers, border-trimmed edges with
//! filled arrowheads, compound frames, the zoom-threshold label plan, and an
//! explicit legend. Static SVG/PNG export rebuilds the plain graph Scene the
//! figure route produced (its layout, scales, and chrome stay authoritative)
//! with those same planes, so every policy stays in Rust and the export
//! paints what the browser paints at the home view.

use std::collections::HashMap;

use crate::edge_route::{
    clip_edge_piece, NodeShape, EDGE_END_SHAPE_MASK, EDGE_END_TERMINAL,
    GRAPH_EDGE_HEAD_HALF_WIDTH_PX, GRAPH_EDGE_HEAD_LENGTH_PX,
};
use crate::scene::{
    encode_butt_caps, resolved_legend_bounds, LegendLocation, SceneBatch, SceneDocument,
    SceneError, SceneLabel, SceneLegend, SceneLegendEntry, SceneRecordKind,
    LEGEND_DEFAULT_FRAME_FILL_RGBA, LEGEND_DEFAULT_FRAME_STROKE_RGBA, LEGEND_DEFAULT_TEXT_RGBA,
    MAX_SCENE_LABELS, MAX_SCENE_LABEL_TEXT_BYTES, MAX_SCENE_MARKS,
};

/// `label_plan` row components (threshold, dx, dy, width, font px).
pub const LABEL_PLAN_STRIDE: usize = 5;
/// `compound_frame` row components (4 bound deltas, RGBA, width, pad).
pub const COMPOUND_FRAME_STRIDE: usize = 10;
/// `edge_ends` row components (route_ends, #33).
pub const EDGE_ENDS_STRIDE: usize = 7;

const EDGE_ID_BASE: u64 = 1 << 48;
const HEAD_ID_BASE: u64 = 2 << 48;
const FRAME_ID_BASE: u64 = 3 << 48;
const LABEL_ID_BASE: u64 = 4 << 48;

/// Why a composed graph Scene could not be rebuilt.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ComposedSceneError {
    /// Malformed or over-limit planes or base Scene.
    Invalid(SceneError),
    /// The explicit legend does not fit the plot (the browser scrolls it; a
    /// static image cannot), like every static legend footprint.
    LegendFootprint,
}

impl From<SceneError> for ComposedSceneError {
    fn from(error: SceneError) -> Self {
        Self::Invalid(error)
    }
}

/// One explicit legend row.
#[derive(Clone, Debug, PartialEq)]
pub struct GraphLegendRow {
    pub label: String,
    pub rgba: [u8; 4],
    pub symbol: u8,
}

/// Resolved composed-graph planes, as the browser receives them. Optional
/// planes are empty slices.
#[derive(Clone, Copy, Debug, Default)]
pub struct ComposedGraphPlanes<'a> {
    pub x: &'a [f64],
    pub y: &'a [f64],
    /// Straight RGBA per node (`n * 4`) before opacity.
    pub fill: &'a [u8],
    pub stroke: &'a [u8],
    pub stroke_width: &'a [f64],
    pub diameter: &'a [f64],
    pub symbol: &'a [u8],
    pub opacity: &'a [f64],
    /// Node halo RGBA (alpha baked) and diameter px; empty when absent.
    pub halo: &'a [u8],
    pub halo_diameter: &'a [f64],
    pub node_label_plan: &'a [f64],
    pub node_labels: &'a [Option<&'a str>],
    pub frames: &'a [f64],
    pub x0: &'a [f64],
    pub y0: &'a [f64],
    pub x1: &'a [f64],
    pub y1: &'a [f64],
    /// Straight RGBA per segment (`m * 4`) before opacity.
    pub segment_rgba: &'a [u8],
    pub segment_width: &'a [f64],
    pub segment_opacity: &'a [f64],
    pub segment_halo: &'a [u8],
    pub segment_halo_width: &'a [f64],
    pub segment_body: &'a [u8],
    pub segment_body_width: &'a [f64],
    pub segment_dash: &'a [f64],
    pub edge_ends: &'a [f64],
    pub segment_label_plan: &'a [f64],
    pub segment_labels: &'a [Option<&'a str>],
    pub legend_title: &'a str,
    pub legend: &'a [GraphLegendRow],
    /// Authored legend placement name; empty is upper right (the browser
    /// default).
    pub legend_loc: &'a str,
    /// The chart text paint (`--chart-text`) the browser labels with; `None`
    /// keeps the Scene chrome's label paint.
    pub text_rgba: Option<[u8; 4]>,
}

fn baked(rgba: [u8; 4], opacity: f64) -> [u8; 4] {
    let mut out = rgba;
    let alpha = f64::from(rgba[3]) * opacity.clamp(0.0, 1.0);
    out[3] = alpha.round().clamp(0.0, 255.0) as u8;
    out
}

fn rgba_at(plane: &[u8], index: usize) -> [u8; 4] {
    [
        plane[index * 4],
        plane[index * 4 + 1],
        plane[index * 4 + 2],
        plane[index * 4 + 3],
    ]
}

#[derive(Default)]
struct Columns {
    kinds: Vec<u8>,
    stable_ids: Vec<u64>,
    style_refs: Vec<u32>,
    fill: Vec<u8>,
    stroke: Vec<u8>,
    stroke_width: Vec<f64>,
    diameter: Vec<f64>,
    symbols: Vec<u8>,
    x0: Vec<f64>,
    y0: Vec<f64>,
    x1: Vec<f64>,
    y1: Vec<f64>,
    styles: HashMap<([u8; 4], [u8; 4], u64, bool), u32>,
    style_count: u32,
    /// Styles stroked with butt caps (dash pieces).
    butt_styles: Vec<u32>,
}

impl Columns {
    fn style(&mut self, fill: [u8; 4], stroke: [u8; 4], width: f64) -> u32 {
        self.capped_style(fill, stroke, width, false)
    }

    fn capped_style(&mut self, fill: [u8; 4], stroke: [u8; 4], width: f64, butt: bool) -> u32 {
        let key = (fill, stroke, width.to_bits(), butt);
        if let Some(&index) = self.styles.get(&key) {
            return index;
        }
        let index = self.style_count;
        self.style_count += 1;
        if butt {
            self.butt_styles.push(index);
        }
        self.fill.extend_from_slice(&fill);
        self.stroke.extend_from_slice(&stroke);
        self.stroke_width.push(width);
        self.styles.insert(key, index);
        index
    }

    #[allow(clippy::too_many_arguments)]
    fn row(
        &mut self,
        kind: SceneRecordKind,
        stable_id: u64,
        style_ref: u32,
        diameter: f64,
        symbol: u8,
        x0: f64,
        y0: f64,
        x1: f64,
        y1: f64,
    ) -> Result<(), SceneError> {
        if self.kinds.len() >= MAX_SCENE_MARKS {
            return Err(SceneError::Limit);
        }
        self.kinds.push(kind as u8);
        self.stable_ids.push(stable_id);
        self.style_refs.push(style_ref);
        self.diameter.push(diameter);
        self.symbols.push(symbol);
        self.x0.push(x0);
        self.y0.push(y0);
        self.x1.push(x1);
        self.y1.push(y1);
        Ok(())
    }
}

/// Rebuild a plain composed-graph Scene with the full composed-graph planes.
///
/// `base` is the Scene the figure route produced for the same chart with its
/// graph traces painted plainly; its layout, scales, chrome, and text are
/// kept. Its records are replaced by, in paint order: compound frames, every
/// edge piece's halo, body, and stroke layers (dash split in screen space,
/// ends trimmed at node outlines by the Scene's edge-end pass), filled
/// arrowheads, and each node's halo then marker. Labels paint where the export's
/// isotropic scale reaches their Rust threshold and their planned box fits the
/// plot; the explicit legend replaces the base legend.
pub fn rebuild_composed_graph_scene(
    base: &[u8],
    planes: &ComposedGraphPlanes<'_>,
) -> Result<Vec<u8>, ComposedSceneError> {
    let parts = SceneDocument::decode(base)?.into_graph_parts()?;
    let text_rgba = planes.text_rgba.unwrap_or(parts.chrome.label_rgba);
    let layout = parts.layout;
    let (xs, ys) = (parts.x_scale, parts.y_scale);
    let n = planes.x.len();
    let m = planes.x0.len();
    let valid_nodes = [
        planes.y.len(),
        planes.stroke_width.len(),
        planes.diameter.len(),
        planes.symbol.len(),
        planes.opacity.len(),
    ]
    .iter()
    .all(|&len| len == n)
        && planes.fill.len() == n * 4
        && planes.stroke.len() == n * 4
        && (planes.halo.is_empty()
            || (planes.halo.len() == n * 4 && planes.halo_diameter.len() == n))
        && (planes.node_label_plan.is_empty()
            || (planes.node_label_plan.len() == n * LABEL_PLAN_STRIDE
                && planes.node_labels.len() == n))
        && (planes.frames.is_empty() || planes.frames.len() == n * COMPOUND_FRAME_STRIDE);
    let valid_edges = [
        planes.y0.len(),
        planes.x1.len(),
        planes.y1.len(),
        planes.segment_width.len(),
        planes.segment_opacity.len(),
    ]
    .iter()
    .all(|&len| len == m)
        && planes.segment_rgba.len() == m * 4
        && (planes.segment_halo.is_empty()
            || (planes.segment_halo.len() == m * 4 && planes.segment_halo_width.len() == m))
        && (planes.segment_body.is_empty()
            || (planes.segment_body.len() == m * 4 && planes.segment_body_width.len() == m))
        && (planes.segment_dash.is_empty() || planes.segment_dash.len() == m * 2)
        && (planes.edge_ends.is_empty() || planes.edge_ends.len() == m * EDGE_ENDS_STRIDE)
        && (planes.segment_label_plan.is_empty()
            || (planes.segment_label_plan.len() == m * LABEL_PLAN_STRIDE
                && planes.segment_labels.len() == m));
    if !valid_nodes || !valid_edges {
        return Err(SceneError::Length.into());
    }
    let px = |x: f64, y: f64| (xs.pixel(x), ys.pixel(y));
    // Pixel-derived geometry (padded frames, arrowheads, dash spans) maps back
    // through each scale's exact inverse, so authored log and symlog axes
    // (#909) keep the browser's screen-space shapes.
    let to_data = |pxx: f64, pxy: f64| (xs.data(pxx), ys.data(pxy));
    let linear = xs.is_linear() && ys.is_linear();
    let mut columns = Columns::default();

    // 1. Compound frames, padded in screen px (clear member markers).
    if !planes.frames.is_empty() {
        for index in 0..n {
            let row =
                &planes.frames[index * COMPOUND_FRAME_STRIDE..(index + 1) * COMPOUND_FRAME_STRIDE];
            if row[8] <= 0.0 {
                continue;
            }
            let (x, y) = (planes.x[index], planes.y[index]);
            let pad = row[9];
            let (a0, a1) = (px(x + row[0], y + row[2]), px(x + row[1], y + row[3]));
            let (left, right) = (a0.0.min(a1.0) - pad, a0.0.max(a1.0) + pad);
            let (top, bottom) = (a0.1.min(a1.1) - pad, a0.1.max(a1.1) + pad);
            let (d0, d1) = (to_data(left, top), to_data(right, bottom));
            let rgba = [row[4] as u8, row[5] as u8, row[6] as u8, row[7] as u8];
            let style = columns.style([0; 4], rgba, row[8]);
            columns.row(
                SceneRecordKind::Rect,
                FRAME_ID_BASE + index as u64,
                style,
                0.0,
                0,
                d0.0.min(d1.0),
                d0.1.min(d1.1),
                d0.0.max(d1.0),
                d0.1.max(d1.1),
            )?;
        }
    }

    // 2. Edges: per piece, halo, body, then status stroke (the browser's
    //    per-item layer order), dashed along the piece from its start.
    let mut next_edge_id = EDGE_ID_BASE;
    let mut heads: Vec<([f64; 6], [u8; 4])> = Vec::new();
    for segment in 0..m {
        let (a, b) = (
            (planes.x0[segment], planes.y0[segment]),
            (planes.x1[segment], planes.y1[segment]),
        );
        let (pa, pb) = (px(a.0, a.1), px(b.0, b.1));
        let length = (pb.0 - pa.0).hypot(pb.1 - pa.1);
        if !length.is_finite() || length <= 0.0 {
            continue;
        }
        let ends = (!planes.edge_ends.is_empty()).then(|| {
            &planes.edge_ends[segment * EDGE_ENDS_STRIDE..(segment + 1) * EDGE_ENDS_STRIDE]
        });
        // The visible shaft, exactly as the browser draws it: clipped against
        // both node outlines, and ending at the arrowhead's base when the
        // piece carries the head (#33 `clip_edge_piece`).
        let mut shaft = (0.0, 1.0);
        let mut tip: Option<f64> = None;
        if let Some(row) = ends {
            let bits = row[6] as u8;
            let c0 = px(a.0 + row[0], a.1 + row[1]);
            let c1 = px(a.0 + row[3], a.1 + row[4]);
            let Some((t0, t1, head_t)) = clip_edge_piece(
                pa,
                pb,
                c0,
                row[2],
                NodeShape::from_code((bits >> 2) & EDGE_END_SHAPE_MASK),
                c1,
                row[5],
                NodeShape::from_code(bits & EDGE_END_SHAPE_MASK),
                bits & 0x40 != 0,
                bits & EDGE_END_TERMINAL != 0,
            ) else {
                continue; // entirely inside a node
            };
            tip = head_t;
            let end = if head_t.is_some() {
                t1 - GRAPH_EDGE_HEAD_LENGTH_PX / length
            } else {
                t1
            };
            shaft = (t0, end);
        }
        let dash = if planes.segment_dash.is_empty() {
            (0.0, 0.0)
        } else {
            (
                planes.segment_dash[segment * 2],
                planes.segment_dash[segment * 2 + 1],
            )
        };
        // Screen-space dash spans [t0, t1] along the untrimmed piece.
        let mut spans: Vec<(f64, f64)> = Vec::new();
        if dash.1 > 0.0 && dash.0 > 0.0 {
            let period = dash.0 + dash.1;
            let mut cursor = 0.0;
            while cursor < length {
                spans.push((cursor / length, ((cursor + dash.0).min(length)) / length));
                cursor += period;
            }
        } else {
            spans.push((0.0, 1.0));
        }
        let opacity = planes.segment_opacity[segment];
        let width = planes.segment_width[segment];
        let mut layers: Vec<([u8; 4], f64)> = Vec::with_capacity(3);
        if !planes.segment_halo.is_empty() {
            let halo = rgba_at(planes.segment_halo, segment);
            if halo != [0; 4] {
                layers.push((halo, planes.segment_halo_width[segment]));
            }
        }
        if !planes.segment_body.is_empty() {
            let body = rgba_at(planes.segment_body, segment);
            if body != [0; 4] {
                layers.push((body, planes.segment_body_width[segment]));
            }
        }
        let stroke = baked(rgba_at(planes.segment_rgba, segment), opacity);
        layers.push((stroke, width));
        // Dash spans run along the piece in screen space, like the browser.
        let at = |t: f64| {
            if t <= 0.0 {
                a
            } else if t >= 1.0 {
                b
            } else {
                to_data(pa.0 + (pb.0 - pa.0) * t, pa.1 + (pb.1 - pa.1) * t)
            }
        };
        // Dash phase stays anchored at the untrimmed start; each span is cut
        // to the visible shaft.
        let visible: Vec<(f64, f64)> = spans
            .iter()
            .map(|&(t0, t1)| (t0.max(shaft.0), t1.min(shaft.1)))
            .filter(|&(t0, t1)| t1 > t0)
            .collect();
        for (paint, layer_width) in layers {
            // Dash pieces end square to the stroke like the browser's
            // fragment discard; round caps would close the gaps.
            let style = columns.capped_style([0; 4], paint, layer_width, spans.len() > 1);
            for &(t0, t1) in &visible {
                let (p0, p1) = (at(t0), at(t1));
                let id = next_edge_id;
                next_edge_id += 1;
                for point in [p0, p1] {
                    columns.row(
                        SceneRecordKind::Polyline,
                        id,
                        style,
                        0.0,
                        0,
                        point.0,
                        point.1,
                        0.0,
                        0.0,
                    )?;
                }
            }
        }
        // Filled arrowhead (stroke color) with its tip on the target outline,
        // exactly as the browser's head pass places it.
        if let Some(tip_t) = tip {
            let (ux, uy) = ((pb.0 - pa.0) / length, (pb.1 - pa.1) / length);
            let tip = (pa.0 + (pb.0 - pa.0) * tip_t, pa.1 + (pb.1 - pa.1) * tip_t);
            let base = (
                tip.0 - ux * GRAPH_EDGE_HEAD_LENGTH_PX,
                tip.1 - uy * GRAPH_EDGE_HEAD_LENGTH_PX,
            );
            let side = (
                -uy * GRAPH_EDGE_HEAD_HALF_WIDTH_PX,
                ux * GRAPH_EDGE_HEAD_HALF_WIDTH_PX,
            );
            heads.push((
                [
                    tip.0,
                    tip.1,
                    base.0 + side.0,
                    base.1 + side.1,
                    base.0 - side.0,
                    base.1 - side.1,
                ],
                stroke,
            ));
        }
    }
    for (index, (triangle, paint)) in heads.into_iter().enumerate() {
        let style = columns.style(paint, [0; 4], 0.0);
        for vertex in 0..3 {
            let (x, y) = to_data(triangle[vertex * 2], triangle[vertex * 2 + 1]);
            columns.row(
                SceneRecordKind::PolyFill,
                HEAD_ID_BASE + index as u64,
                style,
                0.0,
                0,
                x,
                y,
                0.0,
                0.0,
            )?;
        }
    }

    // 3. Nodes: halo circle, then the marker (fill, outline, shape).
    for index in 0..n {
        let stable = (1u64 << 32) + index as u64;
        let (x, y) = (planes.x[index], planes.y[index]);
        if !planes.halo.is_empty() {
            let halo = rgba_at(planes.halo, index);
            if halo != [0; 4] {
                let style = columns.style(halo, [0; 4], 0.0);
                columns.row(
                    SceneRecordKind::Scatter,
                    stable,
                    style,
                    planes.halo_diameter[index],
                    0,
                    x,
                    y,
                    0.0,
                    0.0,
                )?;
            }
        }
        let opacity = planes.opacity[index];
        let style = columns.style(
            baked(rgba_at(planes.fill, index), opacity),
            baked(rgba_at(planes.stroke, index), opacity),
            planes.stroke_width[index],
        );
        columns.row(
            SceneRecordKind::Scatter,
            stable,
            style,
            planes.diameter[index],
            planes.symbol[index],
            x,
            y,
            0.0,
            0.0,
        )?;
    }

    // 4. Labels at the export's isotropic scale (CSS px per data unit). The
    //    plan assumes linear spacing, so like the browser no labels paint on
    //    log or symlog axes.
    let scale = if linear {
        let (ox, oy) = px(0.0, 0.0);
        let (ux, uy) = px(1.0, 1.0);
        (ux - ox).abs().min((uy - oy).abs())
    } else {
        -1.0
    };
    if !scale.is_finite() {
        return Err(SceneError::NonFinite.into());
    }
    let mut labels: Vec<(f64, usize, SceneLabel)> = Vec::new();
    let mut plan_labels = |plan: &[f64],
                           texts: &[Option<&str>],
                           anchor: &dyn Fn(usize) -> (f64, f64),
                           base_id: u64| {
        for (index, text) in texts.iter().enumerate() {
            let Some(text) = text else { continue };
            let row = &plan[index * LABEL_PLAN_STRIDE..(index + 1) * LABEL_PLAN_STRIDE];
            if !(row[0] >= 0.0) || row[0] > scale {
                continue;
            }
            let (ax, ay) = anchor(index);
            let (left, baseline) = (ax + row[1], ay + row[2]);
            let (font, width) = (row[4], row[3]);
            if left < layout.left
                || left + width > layout.right
                || baseline - font < layout.top
                || baseline + 2.0 > layout.bottom
            {
                continue;
            }
            labels.push((
                row[0],
                labels.len(),
                SceneLabel {
                    stable_id: base_id + index as u64,
                    x: left,
                    y: baseline,
                    font_size: font,
                    rgba: text_rgba,
                    anchor: 0,
                    rotation: 0.0,
                    text: (*text).to_owned(),
                },
            ));
        }
    };
    if !planes.segment_label_plan.is_empty() {
        let anchor = |segment: usize| {
            px(
                (planes.x0[segment] + planes.x1[segment]) * 0.5,
                (planes.y0[segment] + planes.y1[segment]) * 0.5,
            )
        };
        plan_labels(
            planes.segment_label_plan,
            planes.segment_labels,
            &anchor,
            LABEL_ID_BASE + (1 << 40),
        );
    }
    if !planes.node_label_plan.is_empty() {
        let anchor = |index: usize| px(planes.x[index], planes.y[index]);
        plan_labels(
            planes.node_label_plan,
            planes.node_labels,
            &anchor,
            LABEL_ID_BASE,
        );
    }
    // Past the Scene's label caps (count and text bytes): keep the lowest
    // thresholds (the labels that paint earliest when zooming in), in input
    // order.
    labels.sort_by(|a, b| a.0.total_cmp(&b.0).then(a.1.cmp(&b.1)));
    let mut text_bytes = 0usize;
    let mut kept = 0usize;
    for entry in &labels {
        if kept == MAX_SCENE_LABELS || text_bytes + entry.2.text.len() > MAX_SCENE_LABEL_TEXT_BYTES
        {
            break;
        }
        text_bytes += entry.2.text.len();
        kept += 1;
    }
    labels.truncate(kept);
    labels.sort_by_key(|entry| entry.1);
    let labels: Vec<SceneLabel> = labels.into_iter().map(|entry| entry.2).collect();

    // 5. Explicit legend, else the base legend.
    let legend = if planes.legend.is_empty() {
        parts.legend
    } else {
        let mut entries = Vec::with_capacity(planes.legend.len());
        for row in planes.legend {
            let style = columns.style(row.rgba, row.rgba, 1.5) as usize;
            entries.push(SceneLegendEntry {
                style_ref: style,
                kind: SceneRecordKind::Scatter,
                symbol: row.symbol,
                fill_rgba: row.rgba,
                stroke_rgba: row.rgba,
                label: row.label.clone(),
            });
        }
        // A themed (opaque) chart background carries the legend frame and
        // the chrome label color; otherwise the Scene's default legend paint.
        let background = parts.chrome.chart_background_rgba;
        let (text_rgba, frame_fill_rgba, frame_stroke_rgba) = if background[3] == 0 {
            (
                LEGEND_DEFAULT_TEXT_RGBA,
                LEGEND_DEFAULT_FRAME_FILL_RGBA,
                LEGEND_DEFAULT_FRAME_STROKE_RGBA,
            )
        } else {
            let label = text_rgba;
            (
                label,
                [background[0], background[1], background[2], 230],
                [label[0], label[1], label[2], 71],
            )
        };
        Some(SceneLegend {
            location: if planes.legend_loc.is_empty() {
                LegendLocation::UpperRight
            } else {
                LegendLocation::from_name(planes.legend_loc).ok_or(SceneError::Length)?
            },
            title: planes.legend_title.to_owned(),
            font_size: 11.0,
            title_font_size: 12.0,
            text_rgba,
            frame_fill_rgba,
            frame_stroke_rgba,
            entries,
        })
    };
    if let Some(legend) = &legend {
        if resolved_legend_bounds(layout, legend, None).is_err() {
            return Err(ComposedSceneError::LegendFootprint);
        }
    }
    SceneBatch::new_with_decorations_and_labels(
        layout,
        1,
        2,
        xs,
        ys,
        parts.chrome,
        parts.text,
        legend,
        labels,
        &columns.kinds,
        &columns.stable_ids,
        &columns.style_refs,
        &columns.fill,
        &columns.stroke,
        &columns.stroke_width,
        &columns.diameter,
        &columns.symbols,
        &columns.x0,
        &columns.y0,
        &columns.x1,
        &columns.y1,
    )
    .and_then(|batch| batch.with_dashes(&encode_butt_caps(&columns.butt_styles)?))
    .map(|batch| batch.encode())
    .map_err(ComposedSceneError::from)
}

/// Chart facts that fix the graph home view's plot rectangle (#910).
#[derive(Clone, Copy, Debug)]
pub struct GraphHomeLayout<'a> {
    pub viewport_width: f64,
    pub viewport_height: f64,
    pub padding: Option<[f64; 4]>,
    pub title: &'a str,
    /// The node-center autorange the home view must still contain.
    pub base_x: (f64, f64),
    pub base_y: (f64, f64),
}

/// What is drawn around one data anchor, in CSS px on each side.
#[derive(Clone, Copy, Debug)]
struct Extent {
    x: f64,
    y: f64,
    left: f64,
    right: f64,
    up: f64,
    down: f64,
}

/// Stop the solve when the pads alone would take this share of the plot.
const HOME_MAX_PAD_SHARE: f64 = 0.9;
const HOME_LAYOUT_PASSES: usize = 6;

/// The smallest `[lo, hi]` containing `base` in which every anchor's pads fit
/// on a plot `length` px long: `(v - lo) * length / (hi - lo) >= pad_lo` and
/// likewise above. `None` when the pads cannot fit.
fn home_axis(base: (f64, f64), anchors: &[(f64, f64, f64)], length: f64) -> Option<(f64, f64)> {
    let (max_lo, max_hi) = anchors
        .iter()
        .fold((0.0_f64, 0.0_f64), |(a, b), &(_, lo, hi)| {
            (a.max(lo), b.max(hi))
        });
    if !(length > 0.0) || (max_lo + max_hi) / length >= HOME_MAX_PAD_SHARE {
        return None;
    }
    let bounds = |span: f64| {
        anchors.iter().fold(base, |(lo, hi), &(v, pad_lo, pad_hi)| {
            (
                lo.min(v - pad_lo * span / length),
                hi.max(v + pad_hi * span / length),
            )
        })
    };
    let fits = |span: f64| {
        let (lo, hi) = bounds(span);
        hi - lo <= span
    };
    let base_span = base.1 - base.0;
    if !(base_span > 0.0) {
        return None;
    }
    if fits(base_span) {
        return Some(bounds(base_span));
    }
    // g(span) = hi - lo grows with slope below HOME_MAX_PAD_SHARE, so the
    // feasible spans form [span*, inf): bisect for the least one.
    let (lo_all, hi_all) = anchors
        .iter()
        .fold(base, |(lo, hi), &(v, _, _)| (lo.min(v), hi.max(v)));
    // The bracket is the exact fixed point when the widest pads sit on the
    // extreme anchors; widen it past rounding.
    let mut high = (hi_all - lo_all) / (1.0 - (max_lo + max_hi) / length) * (1.0 + 1e-9);
    let mut low = base_span;
    if !high.is_finite() || !fits(high) {
        return None;
    }
    for _ in 0..80 {
        let mid = 0.5 * (low + high);
        if fits(mid) {
            high = mid;
        } else {
            low = mid;
        }
    }
    let (lo, hi) = bounds(high);
    (lo.is_finite() && hi.is_finite() && lo < hi).then_some((lo, hi))
}

fn home_extents(planes: &ComposedGraphPlanes<'_>) -> Vec<Extent> {
    let mut out = Vec::with_capacity(planes.x.len() + planes.x0.len() * 2);
    for i in 0..planes.x.len() {
        // The marker's drawn extent (diamonds reach sqrt(2) further along the
        // axes), plus half its stroke.
        let mut r = crate::scene::marker_symbol_extent(0.5 * planes.diameter[i], planes.symbol[i])
            + 0.5 * planes.stroke_width[i];
        if !planes.halo.is_empty() && planes.halo[i * 4 + 3] > 0 {
            r = r.max(0.5 * planes.halo_diameter[i]);
        }
        let r = r + 1.0; // antialiasing
        out.push(Extent {
            x: planes.x[i],
            y: planes.y[i],
            left: r,
            right: r,
            up: r,
            down: r,
        });
        if !planes.frames.is_empty() {
            let row = &planes.frames[i * COMPOUND_FRAME_STRIDE..(i + 1) * COMPOUND_FRAME_STRIDE];
            if row[8] > 0.0 {
                let pad = row[9] + 0.5 * row[8] + 1.0;
                let (x0, x1) = (planes.x[i] + row[0], planes.x[i] + row[1]);
                let (y0, y1) = (planes.y[i] + row[2], planes.y[i] + row[3]);
                let mid = (0.5 * (x0 + x1), 0.5 * (y0 + y1));
                for (x, y, left, right, up, down) in [
                    (x0, mid.1, pad, 0.0, 0.0, 0.0),
                    (x1, mid.1, 0.0, pad, 0.0, 0.0),
                    (mid.0, y0, 0.0, 0.0, 0.0, pad),
                    (mid.0, y1, 0.0, 0.0, pad, 0.0),
                ] {
                    out.push(Extent {
                        x,
                        y,
                        left,
                        right,
                        up,
                        down,
                    });
                }
            }
        }
    }
    for s in 0..planes.x0.len() {
        let mut w = planes.segment_width[s];
        if !planes.segment_halo.is_empty() && planes.segment_halo[s * 4 + 3] > 0 {
            w = w.max(planes.segment_halo_width[s]);
        }
        let r = 0.5 * w + 1.0;
        for (x, y) in [(planes.x0[s], planes.y0[s]), (planes.x1[s], planes.y1[s])] {
            out.push(Extent {
                x,
                y,
                left: r,
                right: r,
                up: r,
                down: r,
            });
        }
    }
    out
}

/// Boxes of the labels that paint at `scale` (px per data unit), as extents
/// around their anchors (the label box model of `plan_labels`).
fn home_label_extents(planes: &ComposedGraphPlanes<'_>, scale: f64) -> Vec<Extent> {
    let mut out = Vec::new();
    let mut add = |plan: &[f64], texts: &[Option<&str>], anchor: &dyn Fn(usize) -> (f64, f64)| {
        for (index, text) in texts.iter().enumerate() {
            let row = &plan[index * LABEL_PLAN_STRIDE..(index + 1) * LABEL_PLAN_STRIDE];
            if text.is_none() || !(row[0] >= 0.0) || row[0] > scale {
                continue;
            }
            let (x, y) = anchor(index);
            let (dx, dy, width, font) = (row[1], row[2], row[3], row[4]);
            out.push(Extent {
                x,
                y,
                left: (-dx).max(0.0),
                right: (dx + width).max(0.0),
                up: (font - dy).max(0.0),
                down: (dy + 2.0).max(0.0),
            });
        }
    };
    if !planes.node_label_plan.is_empty() {
        add(planes.node_label_plan, planes.node_labels, &|i| {
            (planes.x[i], planes.y[i])
        });
    }
    if !planes.segment_label_plan.is_empty() {
        add(planes.segment_label_plan, planes.segment_labels, &|s| {
            (
                0.5 * (planes.x0[s] + planes.x1[s]),
                0.5 * (planes.y0[s] + planes.y1[s]),
            )
        });
    }
    out
}

fn home_domain_for_plot(
    extents: &[Extent],
    base_x: (f64, f64),
    base_y: (f64, f64),
    width: f64,
    height: f64,
) -> Option<[f64; 4]> {
    let xs: Vec<_> = extents.iter().map(|e| (e.x, e.left, e.right)).collect();
    // Screen up is the high end of a linear y axis.
    let ys: Vec<_> = extents.iter().map(|e| (e.y, e.down, e.up)).collect();
    let (x0, x1) = home_axis(base_x, &xs, width)?;
    let (y0, y1) = home_axis(base_y, &ys, height)?;
    Some([x0, x1, y0, y1])
}

/// The graph home view (#910): the smallest domain containing the node-center
/// autorange in which every node marker and halo, edge stroke, compound frame,
/// and home-view label fits inside the plot. Marker and frame pads are solved
/// first; the labels that paint at that scale are then added (adding room only
/// lowers the scale, so no revealed label can be clipped). The plot rectangle
/// is the Scene's cartesian layout for the hidden graph axes, re-solved until
/// it is stable. When labels cannot fit, the view pads markers and frames
/// only; when those cannot fit either, `None` keeps the autorange.
pub fn graph_home_domain(
    planes: &ComposedGraphPlanes<'_>,
    layout: &GraphHomeLayout<'_>,
) -> Option<[f64; 4]> {
    let n = planes.x.len();
    let m = planes.x0.len();
    let valid = planes.y.len() == n
        && planes.diameter.len() == n
        && planes.symbol.len() == n
        && planes.stroke_width.len() == n
        && (planes.halo.is_empty()
            || (planes.halo.len() == n * 4 && planes.halo_diameter.len() == n))
        && (planes.frames.is_empty() || planes.frames.len() == n * COMPOUND_FRAME_STRIDE)
        && (planes.node_label_plan.is_empty()
            || (planes.node_label_plan.len() == n * LABEL_PLAN_STRIDE
                && planes.node_labels.len() == n))
        && [
            planes.y0.len(),
            planes.x1.len(),
            planes.y1.len(),
            planes.segment_width.len(),
        ]
        .iter()
        .all(|&len| len == m)
        && (planes.segment_halo.is_empty()
            || (planes.segment_halo.len() == m * 4 && planes.segment_halo_width.len() == m))
        && (planes.segment_label_plan.is_empty()
            || (planes.segment_label_plan.len() == m * LABEL_PLAN_STRIDE
                && planes.segment_labels.len() == m));
    let finite = |pair: (f64, f64)| pair.0.is_finite() && pair.1.is_finite() && pair.0 < pair.1;
    if !valid || !finite(layout.base_x) || !finite(layout.base_y) {
        return None;
    }
    let geometry = home_extents(planes);
    if geometry.iter().any(|e| {
        ![e.x, e.y, e.left, e.right, e.up, e.down]
            .iter()
            .all(|v| v.is_finite())
    }) {
        return None;
    }
    let plot = |domain: [f64; 4]| -> Option<(f64, f64)> {
        let (left, right, top, bottom) =
            crate::scene::cartesian_scene_margins(crate::scene::CartesianLayoutRequest {
                viewport_width: layout.viewport_width,
                viewport_height: layout.viewport_height,
                authored_padding: layout.padding,
                title: layout.title,
                x_label: "",
                y_label: "",
                x_kind: crate::scene::ScaleKind::Linear,
                x_lo: domain[0],
                x_hi: domain[1],
                x_constant: 1.0,
                x_mask_nonpositive: false,
                x_format: None,
                x_tick_kind: 0,
                y_kind: crate::scene::ScaleKind::Linear,
                y_lo: domain[2],
                y_hi: domain[3],
                y_constant: 1.0,
                y_mask_nonpositive: false,
                y_format: None,
                y_tick_kind: 0,
                colorbar_side: crate::scene::ColorbarSide::None,
                collision: crate::scene::TickCollisionLayout::default(),
            })
            .ok()?;
        let (w, h) = (
            layout.viewport_width - left - right,
            layout.viewport_height - top - bottom,
        );
        (w > 0.0 && h > 0.0).then_some((w, h))
    };
    let mut domain = [
        layout.base_x.0,
        layout.base_x.1,
        layout.base_y.0,
        layout.base_y.1,
    ];
    for _ in 0..HOME_LAYOUT_PASSES {
        let (w, h) = plot(domain)?;
        let shapes = home_domain_for_plot(&geometry, layout.base_x, layout.base_y, w, h)?;
        let scale = (w / (shapes[1] - shapes[0])).min(h / (shapes[3] - shapes[2]));
        let mut all = geometry.clone();
        all.extend(home_label_extents(planes, scale));
        let next = home_domain_for_plot(&all, layout.base_x, layout.base_y, w, h).unwrap_or(shapes);
        let stable = next
            .iter()
            .zip(domain.iter())
            .all(|(a, b)| (a - b).abs() <= 1e-12 * (1.0 + a.abs().max(b.abs())));
        domain = next;
        if stable {
            break;
        }
    }
    Some(domain)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scene::{AxisScale, PlotLayout, ScaleKind};

    /// A plain 240x160 base Scene over the unit square (default chrome).
    fn base() -> Vec<u8> {
        let layout = PlotLayout::new(240.0, 160.0, 20.0, 20.0, 20.0, 20.0).unwrap();
        let xs = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 20.0, 220.0, 1.0, false).unwrap();
        let ys = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 140.0, 20.0, 1.0, false).unwrap();
        SceneBatch::new(
            layout,
            1,
            2,
            xs,
            ys,
            &[SceneRecordKind::Scatter as u8],
            &[1],
            &[0],
            &[0, 0, 0, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &[8.0],
            &[0],
            &[0.5],
            &[0.5],
            &[0.5],
            &[0.5],
        )
        .unwrap()
        .encode()
    }

    /// `base()` with a log x axis over [1, 100] (an authored axis, #909).
    fn log_base() -> Vec<u8> {
        let layout = PlotLayout::new(240.0, 160.0, 20.0, 20.0, 20.0, 20.0).unwrap();
        let xs = AxisScale::new(ScaleKind::Log, 1.0, 100.0, 20.0, 220.0, 1.0, false).unwrap();
        let ys = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 140.0, 20.0, 1.0, false).unwrap();
        SceneBatch::new(
            layout,
            1,
            2,
            xs,
            ys,
            &[SceneRecordKind::Scatter as u8],
            &[1],
            &[0],
            &[0, 0, 0, 255],
            &[0, 0, 0, 0],
            &[0.0],
            &[8.0],
            &[0],
            &[10.0],
            &[0.5],
            &[10.0],
            &[0.5],
        )
        .unwrap()
        .encode()
    }

    const X: [f64; 2] = [0.25, 0.75];
    const Y: [f64; 2] = [0.5, 0.5];
    const FILL: [u8; 8] = [10, 20, 30, 255, 40, 50, 60, 255];
    const ONE: [f64; 2] = [1.0, 1.0];
    const EIGHT: [f64; 2] = [8.0, 8.0];
    const CIRCLES: [u8; 2] = [0, 0];

    fn nodes() -> ComposedGraphPlanes<'static> {
        ComposedGraphPlanes {
            x: &X,
            y: &Y,
            fill: &FILL,
            stroke: &[0; 8],
            stroke_width: &[0.0; 2],
            diameter: &EIGHT,
            symbol: &CIRCLES,
            opacity: &ONE,
            ..Default::default()
        }
    }

    fn svg(planes: &ComposedGraphPlanes<'_>) -> String {
        let bytes = rebuild_composed_graph_scene(&base(), planes).unwrap();
        SceneDocument::decode(&bytes).unwrap().to_svg()
    }

    #[test]
    fn nodes_paint_their_planes_on_the_base_layout() {
        let out = svg(&nodes());
        // Unit square spans x 20..220: nodes land at 70 and 170.
        assert!(
            out.contains(r#"cx="70""#) && out.contains(r#"cx="170""#),
            "{out}"
        );
        assert!(out.contains("rgb(10,20,30)") && out.contains("rgb(40,50,60)"));
    }

    #[test]
    fn dashed_edges_split_in_screen_space_with_butt_caps() {
        let planes = ComposedGraphPlanes {
            x0: &[0.0],
            y0: &[0.5],
            x1: &[1.0],
            y1: &[0.5],
            segment_rgba: &[0, 0, 0, 255],
            segment_width: &[2.0],
            segment_opacity: &[1.0],
            // 200 px piece: 20 px period -> 10 dashes of 10 px.
            segment_dash: &[10.0, 10.0],
            ..nodes()
        };
        let out = svg(&planes);
        assert_eq!(out.matches("<polyline").count(), 10, "{out}");
        assert_eq!(out.matches(r#"stroke-linecap="butt""#).count(), 10);
        let solid = svg(&ComposedGraphPlanes {
            segment_dash: &[],
            ..planes
        });
        assert_eq!(solid.matches("<polyline").count(), 1);
        assert!(!solid.contains("butt"));
    }

    #[test]
    fn labels_paint_from_their_zoom_threshold() {
        // min(200, 120) px per data unit: threshold 100 paints, 150 waits.
        let plan = [100.0, 6.0, 4.0, 20.0, 12.0, 150.0, 6.0, 4.0, 20.0, 12.0];
        let labels = [Some("near"), Some("far")];
        let out = svg(&ComposedGraphPlanes {
            node_label_plan: &plan,
            node_labels: &labels,
            ..nodes()
        });
        assert!(out.contains(">near<") && !out.contains(">far<"), "{out}");
    }

    #[test]
    fn explicit_legend_honors_placement_and_default_paint() {
        let rows = [GraphLegendRow {
            label: "Class 1".into(),
            rgba: [0, 90, 156, 255],
            symbol: 1,
        }];
        let planes = ComposedGraphPlanes {
            legend_title: "Graph semantics",
            legend: &rows,
            legend_loc: "lower left",
            ..nodes()
        };
        let bytes = rebuild_composed_graph_scene(&base(), &planes).unwrap();
        let legend = SceneDocument::decode(&bytes)
            .unwrap()
            .into_graph_parts()
            .unwrap()
            .legend
            .unwrap();
        assert_eq!(legend.location, LegendLocation::LowerLeft);
        // A transparent chart background keeps the Scene's default legend paint.
        assert_eq!(legend.frame_fill_rgba, LEGEND_DEFAULT_FRAME_FILL_RGBA);
        assert_eq!(legend.text_rgba, LEGEND_DEFAULT_TEXT_RGBA);
        assert!(rebuild_composed_graph_scene(
            &base(),
            &ComposedGraphPlanes {
                legend_loc: "best",
                ..planes
            }
        )
        .is_err());
        // Twelve rows overflow the 120 px plot: the static footprint reason.
        let tall: Vec<GraphLegendRow> = (0..12).map(|_| rows[0].clone()).collect();
        assert_eq!(
            rebuild_composed_graph_scene(
                &base(),
                &ComposedGraphPlanes {
                    legend: &tall,
                    ..planes
                }
            ),
            Err(ComposedSceneError::LegendFootprint)
        );
    }

    /// Exported label count under the Scene caps for `n` labels of `text`.
    fn exported_labels(n: usize, text: &str) -> usize {
        let x: Vec<f64> = (0..n).map(|i| (i % 16) as f64 / 16.0).collect();
        let y: Vec<f64> = (0..n).map(|i| 0.25 + (i / 16) as f64 / 32.0).collect();
        let fill = vec![0u8; n * 4];
        let ones = vec![1.0; n];
        let diameter = vec![4.0; n];
        let symbol = vec![0u8; n];
        let labels: Vec<Option<&str>> = (0..n).map(|_| Some(text)).collect();
        // Every threshold paints at this scale; the lowest thresholds win.
        let plan: Vec<f64> = (0..n)
            .flat_map(|i| [i as f64 * 0.1, 2.0, 2.0, 1.0, 12.0])
            .collect();
        let bytes = rebuild_composed_graph_scene(
            &base(),
            &ComposedGraphPlanes {
                x: &x,
                y: &y,
                fill: &fill,
                stroke: &fill,
                stroke_width: &ones,
                diameter: &diameter,
                symbol: &symbol,
                opacity: &ones,
                node_label_plan: &plan,
                node_labels: &labels,
                ..Default::default()
            },
        )
        .unwrap();
        SceneDocument::decode(&bytes)
            .unwrap()
            .to_svg()
            .matches(text)
            .count()
    }

    #[test]
    fn exported_labels_respect_the_scene_caps() {
        // Short labels hit the count cap; wide UTF-8 labels the byte cap.
        let n = MAX_SCENE_LABELS + 8;
        assert_eq!(exported_labels(n, &"x".repeat(32)), MAX_SCENE_LABELS);
        let wide = "\u{20ac}".repeat(32);
        assert_eq!(
            exported_labels(n, &wide),
            MAX_SCENE_LABEL_TEXT_BYTES / wide.len()
        );
    }

    /// Edge-ends row for a piece from node 0 to node 1 (#33 layout): source
    /// center delta and radius, target center delta and radius, flags.
    fn ends(dx1: f64, dy1: f64, r: f64, head: bool) -> [f64; EDGE_ENDS_STRIDE] {
        let bits = EDGE_END_TERMINAL | if head { 0x40 } else { 0 };
        [0.0, 0.0, r, dx1, dy1, r, f64::from(bits)]
    }

    #[test]
    fn directed_shafts_stop_at_the_arrowhead_base() {
        // One horizontal edge from (0.25, 0.5) to (0.75, 0.5): 100 px long.
        let ends = ends(0.5, 0.0, 4.0, true);
        let planes = ComposedGraphPlanes {
            x0: &[0.25],
            y0: &[0.5],
            x1: &[0.75],
            y1: &[0.5],
            segment_rgba: &[0, 0, 0, 255],
            segment_width: &[2.0],
            segment_opacity: &[1.0],
            edge_ends: &ends,
            ..nodes()
        };
        let out = svg(&planes);
        // Target outline at x = 170 - 4; the head tip touches it and the
        // shaft ends one head length before it (the browser's clip).
        let shaft_end = 166.0 - GRAPH_EDGE_HEAD_LENGTH_PX;
        let polyline = out.split("<polyline").nth(1).expect("shaft");
        let points = polyline.split('"').nth(1).unwrap();
        let last_x: f64 = points
            .split_whitespace()
            .last()
            .unwrap()
            .split(',')
            .next()
            .unwrap()
            .parse()
            .unwrap();
        assert!(
            (last_x - shaft_end).abs() < 0.01,
            "{last_x} vs {shaft_end}: {out}"
        );
        assert!(out.contains("M 166 80"), "head tip on the outline: {out}");
    }

    #[test]
    fn log_axes_keep_screen_space_geometry_and_paint_no_labels() {
        // Nodes at x = 10 and x = 100 on log [1, 100]: px 120 and 220.
        let plan = [0.0, 6.0, 4.0, 20.0, 12.0, 0.0, 6.0, 4.0, 20.0, 12.0];
        let labels = [Some("left"), Some("right")];
        let mut frames = [0.0; 2 * COMPOUND_FRAME_STRIDE];
        // Frame around node 0 spanning x in [10, 100] with a 10 px pad.
        frames[..COMPOUND_FRAME_STRIDE]
            .copy_from_slice(&[0.0, 90.0, 0.0, 0.0, 75.0, 85.0, 99.0, 184.0, 1.0, 10.0]);
        let planes = ComposedGraphPlanes {
            x: &[10.0, 100.0],
            y: &[0.5, 0.5],
            frames: &frames,
            node_label_plan: &plan,
            node_labels: &labels,
            ..nodes()
        };
        let bytes = rebuild_composed_graph_scene(&log_base(), &planes).unwrap();
        let out = SceneDocument::decode(&bytes).unwrap().to_svg();
        // The padded frame starts 10 px left of x = 10 (px 110), measured in
        // screen space although the axis is logarithmic.
        assert!(out.contains(r#"<rect x="110""#), "{out}");
        // The label plan assumes linear spacing: none paint, like the browser.
        assert!(!out.contains(">left<") && !out.contains(">right<"));
    }

    fn home_layout() -> GraphHomeLayout<'static> {
        GraphHomeLayout {
            viewport_width: 480.0,
            viewport_height: 320.0,
            padding: None,
            title: "",
            base_x: (0.25 - 0.015, 0.75 + 0.015),
            base_y: (0.49, 0.51),
        }
    }

    /// Plot rect and px position of `(x, y)` for a solved domain.
    fn home_px(domain: [f64; 4], x: f64, y: f64) -> (f64, f64, f64, f64) {
        let (l, r, t, b) =
            crate::scene::cartesian_scene_margins(crate::scene::CartesianLayoutRequest {
                viewport_width: 480.0,
                viewport_height: 320.0,
                authored_padding: None,
                title: "",
                x_label: "",
                y_label: "",
                x_kind: crate::scene::ScaleKind::Linear,
                x_lo: domain[0],
                x_hi: domain[1],
                x_constant: 1.0,
                x_mask_nonpositive: false,
                x_format: None,
                x_tick_kind: 0,
                y_kind: crate::scene::ScaleKind::Linear,
                y_lo: domain[2],
                y_hi: domain[3],
                y_constant: 1.0,
                y_mask_nonpositive: false,
                y_format: None,
                y_tick_kind: 0,
                colorbar_side: crate::scene::ColorbarSide::None,
                collision: crate::scene::TickCollisionLayout::default(),
            })
            .unwrap();
        let (w, h) = (480.0 - l - r, 320.0 - t - b);
        let px = (x - domain[0]) / (domain[1] - domain[0]) * w;
        let py = (domain[3] - y) / (domain[3] - domain[2]) * h;
        (px, py, w, h)
    }

    #[test]
    fn home_domain_keeps_markers_and_halos_inside_the_plot() {
        let halo = [0, 0, 0, 0, 0, 90, 156, 97];
        let planes = ComposedGraphPlanes {
            diameter: &[20.0, 20.0],
            halo: &halo,
            halo_diameter: &[0.0, 40.0],
            ..nodes()
        };
        let domain = graph_home_domain(&planes, &home_layout()).unwrap();
        // Contains the autorange, and every marker (and the halo) fits.
        assert!(domain[0] <= 0.235 && domain[1] >= 0.765);
        let (px0, _, _, _) = home_px(domain, 0.25, 0.5);
        let (px1, _, w, _) = home_px(domain, 0.75, 0.5);
        assert!(px0 >= 11.0 - 1e-6, "{px0}");
        assert!(w - px1 >= 21.0 - 1e-6, "{}", w - px1);
        // Nothing drawn outside the nodes: the autorange already fits.
        let bare = ComposedGraphPlanes {
            diameter: &[0.0, 0.0],
            stroke_width: &[0.0, 0.0],
            ..nodes()
        };
        let small = graph_home_domain(&bare, &home_layout()).unwrap();
        assert!(small[1] - small[0] < domain[1] - domain[0]);
    }

    #[test]
    fn home_domain_fits_diamond_vertices() {
        // A 20 px diamond reaches 20 / sqrt(2) = 14.1 px along the axes.
        let planes = ComposedGraphPlanes {
            diameter: &[20.0, 20.0],
            symbol: &[2, 2],
            stroke_width: &[0.0, 0.0],
            ..nodes()
        };
        let domain = graph_home_domain(&planes, &home_layout()).unwrap();
        let (px1, _, w, _) = home_px(domain, 0.75, 0.5);
        let reach = 10.0 * std::f64::consts::SQRT_2 + 1.0;
        assert!(w - px1 >= reach - 1e-6, "{} < {reach}", w - px1);
        let (px0, _, _, _) = home_px(domain, 0.25, 0.5);
        assert!(px0 >= reach - 1e-6, "{px0} < {reach}");
    }

    #[test]
    fn home_domain_fits_home_view_labels_and_frames() {
        // Node 1 labels 90 px to its right from any scale; node 0 never.
        let plan = [-1.0, 6.0, 4.0, 90.0, 12.0, 0.0, 6.0, 4.0, 90.0, 12.0];
        let labels = [None, Some("right-hand label")];
        let planes = ComposedGraphPlanes {
            node_label_plan: &plan,
            node_labels: &labels,
            ..nodes()
        };
        let domain = graph_home_domain(&planes, &home_layout()).unwrap();
        let (px1, _, w, _) = home_px(domain, 0.75, 0.5);
        assert!(w - px1 >= 96.0 - 1e-6, "{}", w - px1);
        // A group frame around node 0 padded 14 px, 2 px wide, clears the edge.
        let mut frames = [0.0; 2 * COMPOUND_FRAME_STRIDE];
        frames[..COMPOUND_FRAME_STRIDE]
            .copy_from_slice(&[0.0, 0.5, -0.01, 0.01, 75.0, 85.0, 99.0, 184.0, 2.0, 14.0]);
        let framed = graph_home_domain(
            &ComposedGraphPlanes {
                frames: &frames,
                ..nodes()
            },
            &home_layout(),
        )
        .unwrap();
        let (px0, _, _, _) = home_px(framed, 0.25, 0.5);
        assert!(px0 >= 16.0 - 1e-6, "{px0}");
    }

    #[test]
    fn home_domain_keeps_the_autorange_when_pads_cannot_fit() {
        let planes = ComposedGraphPlanes {
            diameter: &[600.0, 600.0],
            ..nodes()
        };
        assert_eq!(graph_home_domain(&planes, &home_layout()), None);
        // Labels too wide to fit fall back to marker-only pads.
        let plan = [0.0, 6.0, 4.0, 900.0, 12.0, -1.0, 6.0, 4.0, 90.0, 12.0];
        let labels = [Some("far too wide"), None];
        let with_labels = graph_home_domain(
            &ComposedGraphPlanes {
                node_label_plan: &plan,
                node_labels: &labels,
                ..nodes()
            },
            &home_layout(),
        );
        assert_eq!(with_labels, graph_home_domain(&nodes(), &home_layout()));
    }
}
