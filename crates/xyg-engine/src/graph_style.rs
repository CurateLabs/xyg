//! Rust-owned graph label acceptance, visual-state precedence, and compound bounds (#34).

use crate::edge_route::{edge_route_segments, EDGE_ROUTE_SEGMENTS_PER_EDGE};
use crate::scene::{
    AxisScale, LegendLocation, PlotLayout, ScaleKind, SceneBatch, SceneChromeStyle,
    SceneChromeText, SceneError, SceneLabel, SceneLegend, SceneLegendEntry, SceneRecordKind,
};

pub const STATE_NORMAL: u8 = 0;
pub const STATE_AGGREGATE: u8 = 1;
pub const STATE_PINNED: u8 = 2;
pub const STATE_NEIGHBOR: u8 = 3;
pub const STATE_HOVERED: u8 = 4;
pub const STATE_SELECTED: u8 = 5;
pub const STATE_FILTERED: u8 = 6;
pub const STATE_DISABLED: u8 = 7;
pub const FLAG_HOVERED: u32 = 1 << 0;
pub const FLAG_SELECTED: u32 = 1 << 1;
pub const FLAG_NEIGHBOR: u32 = 1 << 2;
pub const FLAG_FILTERED: u32 = 1 << 3;
pub const FLAG_PINNED: u32 = 1 << 4;
pub const FLAG_AGGREGATE: u32 = 1 << 5;
pub const FLAG_DISABLED: u32 = 1 << 6;
pub const KNOWN_STATE_FLAGS: u32 = (1 << 7) - 1;
pub const NO_COMPOUND: u64 = u64::MAX;
pub const COMPOUND_ACTION_EXPAND: u8 = 0;
pub const COMPOUND_ACTION_COLLAPSE: u8 = 1;
pub const COMPOUND_ACTION_TOGGLE: u8 = 2;
pub const GRAPH_LOD_DIRECT: u8 = 0;
pub const MAX_COMPOUND_TRANSITION_NODES: usize = 1_024;
pub const RESOLVED_STYLE_VERSION: u32 = 1;
pub const MAX_SEMANTIC_CODE: u8 = 7;
pub const THEME_LIGHT: u8 = 0;
pub const THEME_DARK: u8 = 1;
pub const SEMANTIC_GRAPH_SCENE_VERSION: u32 = 2;
/// Browser painter traces, not source rows, are the governing bound. A dashed
/// edge may lower to several line primitives, so the compiler checks the
/// emitted primitive count rather than trusting an input-node ceiling.
pub const MAX_SEMANTIC_GRAPH_SCENE_PRIMITIVES: usize = 1_024;
pub const MAX_SEMANTIC_GRAPH_VIEWPORT: f64 = 16_384.0;

/// Complete painter-facing graph style. Hosts may customize the semantic input
/// mapping, but never reinterpret these resolved values.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ResolvedGraphStyle {
    pub fill: [u8; 4],
    pub stroke: [u8; 4],
    pub halo: [u8; 4],
    pub size: f32,
    pub width: f32,
    pub opacity: f32,
    pub shape: u8,
    pub dash: u8,
    pub arrow: u8,
    pub state: u8,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GraphLegendEntry {
    pub field: u8,
    pub value: u8,
    pub color: [u8; 4],
    pub shape: u8,
}

#[derive(Clone, Copy, Debug)]
pub struct SemanticStyleInput<'a> {
    pub classes: &'a [u8],
    pub epistemic: &'a [u8],
    pub statuses: &'a [u8],
    pub metric: &'a [f64],
    pub flags: &'a [u32],
    pub edge: bool,
    pub theme: u8,
}

// Color-blind-safe, light/dark-background-tested semantic colors. Code zero is
// deliberately neutral; unknown codes fail closed rather than being modulo-mapped.
const LIGHT_PALETTE: [[u8; 4]; 8] = [
    [75, 85, 99, 255],
    [0, 90, 156, 255],
    [156, 74, 0, 255],
    [0, 107, 79, 255],
    [122, 62, 107, 255],
    [0, 109, 131, 255],
    [155, 44, 0, 255],
    [112, 92, 0, 255],
];
const DARK_PALETTE: [[u8; 4]; 8] = [
    [170, 178, 191, 255],
    [86, 180, 233, 255],
    [230, 159, 0, 255],
    [0, 184, 135, 255],
    [204, 121, 167, 255],
    [125, 211, 252, 255],
    [240, 120, 69, 255],
    [240, 228, 66, 255],
];

fn palette(theme: u8) -> Option<&'static [[u8; 4]; 8]> {
    match theme {
        THEME_LIGHT => Some(&LIGHT_PALETTE),
        THEME_DARK => Some(&DARK_PALETTE),
        _ => None,
    }
}

fn metric_domain(metric: &[f64]) -> (f64, f64) {
    let mut lo = f64::INFINITY;
    let mut hi = f64::NEG_INFINITY;
    for value in metric.iter().copied().filter(|v| v.is_finite()) {
        lo = lo.min(value);
        hi = hi.max(value);
    }
    if !lo.is_finite() {
        (0.0, 0.0)
    } else {
        (lo, hi)
    }
}

fn metric_unit(value: f64, domain: (f64, f64)) -> f32 {
    if !value.is_finite() || domain.0 == domain.1 {
        0.5
    } else {
        // Scaling first avoids `hi - lo == inf` for opposite-sign finite
        // extrema while retaining a finite, monotonic unit coordinate.
        let scale = domain.0.abs().max(domain.1.abs()).max(value.abs());
        let unit =
            ((value / scale) - (domain.0 / scale)) / ((domain.1 / scale) - (domain.0 / scale));
        if unit.is_finite() {
            unit.clamp(0.0, 1.0) as f32
        } else {
            0.5
        }
    }
}

/// Resolve canonical GraphForge class/epistemic/status/metric fields to paint.
/// Input vocabularies are closed (0..=7), outputs are all-or-nothing, and the
/// same routine serves nodes and edges (`edge=true`).
pub fn resolve_semantic_styles(
    input: SemanticStyleInput<'_>,
    out: &mut [ResolvedGraphStyle],
) -> Option<(f64, f64)> {
    let SemanticStyleInput {
        classes,
        epistemic,
        statuses,
        metric,
        flags,
        edge,
        theme,
    } = input;
    let n = classes.len();
    if [
        epistemic.len(),
        statuses.len(),
        metric.len(),
        flags.len(),
        out.len(),
    ]
    .iter()
    .any(|&len| len != n)
        || classes
            .iter()
            .chain(epistemic)
            .chain(statuses)
            .any(|&v| v > MAX_SEMANTIC_CODE)
        || flags.iter().any(|&value| value & !KNOWN_STATE_FLAGS != 0)
    {
        return None;
    }
    let colors = palette(theme)?;
    let domain = metric_domain(metric);
    let mut resolved = Vec::with_capacity(n);
    for i in 0..n {
        let state = resolve_visual_state(flags[i]);
        let unit = metric_unit(metric[i], domain);
        let mut fill = colors[classes[i] as usize];
        let mut stroke = colors[statuses[i] as usize];
        let halo = colors[epistemic[i] as usize];
        // Active semantic paint is opaque so its measured non-text contrast is
        // preserved after composition. Filtered/disabled are intentional
        // inactive-state exemptions below.
        let mut opacity = 1.0;
        let mut width = if edge {
            0.75 + 3.25 * unit
        } else {
            1.0 + 1.5 * unit
        };
        if state == STATE_SELECTED {
            stroke = if theme == THEME_LIGHT {
                [0, 0, 0, 255]
            } else {
                [255, 255, 255, 255]
            };
            width += 2.5;
        }
        if state == STATE_HOVERED {
            width += 1.25;
        }
        if state == STATE_NEIGHBOR {
            width += 0.5;
        }
        if state == STATE_PINNED {
            width += 1.75;
        }
        if state == STATE_AGGREGATE {
            width += 0.75;
        }
        if state == STATE_FILTERED {
            opacity = 0.08;
        }
        if state == STATE_DISABLED {
            opacity = 0.28;
            fill = colors[0];
        }
        resolved.push(ResolvedGraphStyle {
            fill,
            stroke,
            halo,
            size: if edge { 0.0 } else { 7.0 + 13.0 * unit },
            width,
            opacity,
            shape: if edge {
                0
            } else if state == STATE_AGGREGATE {
                5
            } else {
                classes[i] % 6
            },
            dash: if edge {
                if state == STATE_PINNED {
                    3
                } else if state == STATE_AGGREGATE {
                    2
                } else {
                    epistemic[i] % 4
                }
            } else {
                0
            },
            arrow: u8::from(edge && statuses[i] != 0),
            state,
        });
    }
    out.copy_from_slice(&resolved);
    Some(domain)
}

/// Deterministic, de-duplicated legend descriptors ordered field then code.
pub fn semantic_legend(
    classes: &[u8],
    epistemic: &[u8],
    statuses: &[u8],
    theme: u8,
) -> Option<Vec<GraphLegendEntry>> {
    if classes
        .iter()
        .chain(epistemic)
        .chain(statuses)
        .any(|&v| v > MAX_SEMANTIC_CODE)
    {
        return None;
    }
    let colors = palette(theme)?;
    let mut entries = Vec::new();
    for (field, values) in [(0, classes), (1, epistemic), (2, statuses)] {
        let mut seen = [false; 8];
        for &value in values {
            seen[value as usize] = true;
        }
        for (value, present) in seen.into_iter().enumerate() {
            if present {
                entries.push(GraphLegendEntry {
                    field,
                    value: value as u8,
                    color: colors[value],
                    shape: if field == 0 { value as u8 % 6 } else { 0 },
                });
            }
        }
    }
    Some(entries)
}

/// Canonical semantic graph input for the direct-WASM/export Scene seam.
/// Coordinates are canonical f64; endpoints remain u64 until Rust validates
/// them. Hosts frame these planes but never resolve paint or screen geometry.
#[derive(Clone, Copy, Debug)]
pub struct SemanticGraphSceneInput<'a> {
    pub version: u32,
    pub width: f64,
    pub height: f64,
    pub theme: u8,
    pub title: &'a str,
    pub x: &'a [f64],
    pub y: &'a [f64],
    pub node_classes: &'a [u8],
    pub node_epistemic: &'a [u8],
    pub node_statuses: &'a [u8],
    pub node_metric: &'a [f64],
    pub node_flags: &'a [u32],
    pub node_labels: &'a [&'a str],
    pub sources: &'a [u64],
    pub targets: &'a [u64],
    pub edge_classes: &'a [u8],
    pub edge_epistemic: &'a [u8],
    pub edge_statuses: &'a [u8],
    pub edge_metric: &'a [f64],
    pub edge_flags: &'a [u32],
    pub edge_labels: &'a [&'a str],
}

/// Optional compound planes for native and direct-WASM Scene consumers.
#[derive(Clone, Copy, Debug)]
pub struct CompoundGraphSceneInput<'a> {
    pub graph: SemanticGraphSceneInput<'a>,
    pub parents: &'a [u64],
    pub parent_validity: &'a [u8],
    pub collapsed: &'a [u8],
}

const MAX_GRAPH_LABEL_CHARS: usize = 32;
const GRAPH_LABEL_FONT_SIZE: f64 = 12.0;

fn bounded_label(text: &str, available_width: f64) -> Option<String> {
    if text.is_empty() || text.contains('\0') || text.len() > 4_096 || available_width < 8.0 {
        return None;
    }
    let max_chars = ((available_width / (GRAPH_LABEL_FONT_SIZE * 0.62)).floor() as usize)
        .min(MAX_GRAPH_LABEL_CHARS);
    if max_chars == 0 {
        return None;
    }
    let count = text.chars().count();
    if count <= max_chars {
        return Some(text.to_owned());
    }
    if max_chars == 1 {
        return Some("…".to_owned());
    }
    Some(text.chars().take(max_chars - 1).collect::<String>() + "…")
}

#[derive(Default)]
struct SemanticSceneColumns {
    kinds: Vec<u8>,
    stable_ids: Vec<u64>,
    style_refs: Vec<u32>,
    fill_rgba: Vec<u8>,
    stroke_rgba: Vec<u8>,
    stroke_width: Vec<f64>,
    diameter: Vec<f64>,
    symbols: Vec<u8>,
    x0: Vec<f64>,
    y0: Vec<f64>,
    x1: Vec<f64>,
    y1: Vec<f64>,
    styles: Vec<([u8; 4], [u8; 4], u64)>,
    primitives: usize,
}

impl SemanticSceneColumns {
    fn style(&mut self, fill: [u8; 4], stroke: [u8; 4], width: f64) -> u32 {
        let key = (fill, stroke, width.to_bits());
        if let Some(index) = self.styles.iter().position(|candidate| *candidate == key) {
            return index as u32;
        }
        self.styles.push(key);
        self.fill_rgba.extend_from_slice(&fill);
        self.stroke_rgba.extend_from_slice(&stroke);
        self.stroke_width.push(width);
        (self.styles.len() - 1) as u32
    }

    fn fresh_style(
        &mut self,
        fill: [u8; 4],
        stroke: [u8; 4],
        width: f64,
    ) -> Result<u32, SceneError> {
        if self.styles.len() >= MAX_SEMANTIC_GRAPH_SCENE_PRIMITIVES * 3 {
            return Err(SceneError::Limit);
        }
        self.styles.push((fill, stroke, width.to_bits()));
        self.fill_rgba.extend_from_slice(&fill);
        self.stroke_rgba.extend_from_slice(&stroke);
        self.stroke_width.push(width);
        Ok((self.styles.len() - 1) as u32)
    }

    #[allow(clippy::too_many_arguments)]
    fn point(
        &mut self,
        stable_id: u64,
        style_ref: u32,
        diameter: f64,
        symbol: u8,
        x: f64,
        y: f64,
    ) -> Result<(), SceneError> {
        self.primitives = self.primitives.checked_add(1).ok_or(SceneError::Limit)?;
        if self.primitives > MAX_SEMANTIC_GRAPH_SCENE_PRIMITIVES {
            return Err(SceneError::Limit);
        }
        self.kinds.push(SceneRecordKind::Scatter as u8);
        self.stable_ids.push(stable_id);
        self.style_refs.push(style_ref);
        self.diameter.push(diameter);
        self.symbols.push(symbol);
        self.x0.push(x);
        self.y0.push(y);
        self.x1.push(0.0);
        self.y1.push(0.0);
        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    fn line(
        &mut self,
        stable_id: u64,
        style_ref: u32,
        x0: f64,
        y0: f64,
        x1: f64,
        y1: f64,
    ) -> Result<(), SceneError> {
        self.primitives = self.primitives.checked_add(1).ok_or(SceneError::Limit)?;
        if self.primitives > MAX_SEMANTIC_GRAPH_SCENE_PRIMITIVES {
            return Err(SceneError::Limit);
        }
        for (x, y) in [(x0, y0), (x1, y1)] {
            self.kinds.push(SceneRecordKind::Polyline as u8);
            self.stable_ids.push(stable_id);
            self.style_refs.push(style_ref);
            self.diameter.push(0.0);
            self.symbols.push(0);
            self.x0.push(x);
            self.y0.push(y);
            self.x1.push(0.0);
            self.y1.push(0.0);
        }
        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    fn rect(
        &mut self,
        stable_id: u64,
        style_ref: u32,
        x0: f64,
        y0: f64,
        x1: f64,
        y1: f64,
    ) -> Result<(), SceneError> {
        self.primitives = self.primitives.checked_add(1).ok_or(SceneError::Limit)?;
        if self.primitives > MAX_SEMANTIC_GRAPH_SCENE_PRIMITIVES {
            return Err(SceneError::Limit);
        }
        self.kinds.push(SceneRecordKind::Rect as u8);
        self.stable_ids.push(stable_id);
        self.style_refs.push(style_ref);
        self.diameter.push(0.0);
        self.symbols.push(0);
        self.x0.push(x0);
        self.y0.push(y0);
        self.x1.push(x1);
        self.y1.push(y1);
        Ok(())
    }
}

fn alpha(color: [u8; 4], opacity: f32, factor: f32) -> [u8; 4] {
    let mut out = color;
    out[3] = ((f32::from(color[3]) * opacity * factor).round()).clamp(0.0, 255.0) as u8;
    out
}

fn padded_domain(values: &[f64]) -> Option<(f64, f64)> {
    let (mut lo, mut hi) = metric_domain(values);
    if !lo.is_finite() || !hi.is_finite() {
        return None;
    }
    if lo == hi {
        let pad = lo.abs().max(1.0) * 0.05;
        lo -= pad;
        hi += pad;
    } else {
        let pad = (hi - lo) * 0.05;
        lo -= pad;
        hi += pad;
    }
    (lo.is_finite() && hi.is_finite() && lo < hi).then_some((lo, hi))
}

fn semantic_legend_label(field: u8, value: u8) -> String {
    let field = match field {
        0 => "Class",
        1 => "Epistemic",
        _ => "Status",
    };
    format!("{field} {value}")
}

/// Resolve semantic graph planes and lower their complete painter contract to
/// one canonical Scene. Halos, dashed edges, and arrowheads are explicit,
/// screen-bounded primitives chosen here; browser/SVG/raster only paint them.
pub fn encode_semantic_graph_scene(
    input: SemanticGraphSceneInput<'_>,
) -> Result<Vec<u8>, SceneError> {
    encode_semantic_graph_scene_internal(input, None)
}

/// Resolve strict compound/collapse planes into the same canonical Scene used
/// by browser painting, picking, accessibility labels, SVG, and raster export.
pub fn encode_compound_graph_scene(
    input: CompoundGraphSceneInput<'_>,
) -> Result<Vec<u8>, SceneError> {
    encode_semantic_graph_scene_internal(
        input.graph,
        Some((input.parents, input.parent_validity, input.collapsed)),
    )
}

fn encode_semantic_graph_scene_internal(
    input: SemanticGraphSceneInput<'_>,
    compound: Option<(&[u64], &[u8], &[u8])>,
) -> Result<Vec<u8>, SceneError> {
    if input.version != SEMANTIC_GRAPH_SCENE_VERSION
        || !input.width.is_finite()
        || !input.height.is_finite()
        || input.width < 160.0
        || input.height < 120.0
        || input.width > MAX_SEMANTIC_GRAPH_VIEWPORT
        || input.height > MAX_SEMANTIC_GRAPH_VIEWPORT
        || input.title.len() > 4_096
        || input.title.contains('\0')
    {
        return Err(SceneError::Length);
    }
    let n = input.x.len();
    let e = input.sources.len();
    if n.checked_add(e)
        .is_none_or(|count| count > MAX_SEMANTIC_GRAPH_SCENE_PRIMITIVES)
    {
        return Err(SceneError::Limit);
    }
    if n == 0
        || [
            input.y.len(),
            input.node_classes.len(),
            input.node_epistemic.len(),
            input.node_statuses.len(),
            input.node_metric.len(),
            input.node_flags.len(),
            input.node_labels.len(),
        ]
        .iter()
        .any(|&len| len != n)
        || [
            input.targets.len(),
            input.edge_classes.len(),
            input.edge_epistemic.len(),
            input.edge_statuses.len(),
            input.edge_metric.len(),
            input.edge_flags.len(),
            input.edge_labels.len(),
        ]
        .iter()
        .any(|&len| len != e)
        || input.x.iter().chain(input.y).any(|v| !v.is_finite())
        || input
            .sources
            .iter()
            .chain(input.targets)
            .any(|&v| v >= n as u64)
    {
        return Err(SceneError::Length);
    }
    if compound.is_some_and(|(parents, validity, collapsed)| {
        parents.len() != n || validity.len() != n || collapsed.len() != n
    }) {
        return Err(SceneError::Length);
    }
    let mut hierarchy = if let Some((parents, validity, collapsed)) = compound {
        compound_hierarchy(parents, validity, collapsed).ok_or(SceneError::Length)?
    } else {
        CompoundHierarchy {
            direct_parent: vec![None; n],
            representative: (0..n).collect(),
            visible: vec![true; n],
            is_compound: vec![false; n],
            bounds: vec![[f64::NAN; 4]; n],
            depth: vec![0; n],
        }
    };
    for index in 0..n {
        hierarchy.bounds[index] = [
            input.x[index],
            input.x[index],
            input.y[index],
            input.y[index],
        ];
    }
    let mut hierarchy_order: Vec<usize> = (0..n).collect();
    hierarchy_order.sort_by_key(|&index| (std::cmp::Reverse(hierarchy.depth[index]), index));
    for index in hierarchy_order {
        let Some(parent) = hierarchy.direct_parent[index] else {
            continue;
        };
        let child = hierarchy.bounds[index];
        let bounds = &mut hierarchy.bounds[parent];
        bounds[0] = bounds[0].min(child[0]);
        bounds[1] = bounds[1].max(child[1]);
        bounds[2] = bounds[2].min(child[2]);
        bounds[3] = bounds[3].max(child[3]);
    }
    let mut nodes = vec![
        ResolvedGraphStyle {
            fill: [0; 4],
            stroke: [0; 4],
            halo: [0; 4],
            size: 0.0,
            width: 0.0,
            opacity: 0.0,
            shape: 0,
            dash: 0,
            arrow: 0,
            state: 0,
        };
        n
    ];
    let mut edges = vec![
        ResolvedGraphStyle {
            fill: [0; 4],
            stroke: [0; 4],
            halo: [0; 4],
            size: 0.0,
            width: 0.0,
            opacity: 0.0,
            shape: 0,
            dash: 0,
            arrow: 0,
            state: 0,
        };
        e
    ];
    let effective_node_flags =
        collapsed_node_flags(input.node_flags, &hierarchy).ok_or(SceneError::Length)?;
    resolve_semantic_styles(
        SemanticStyleInput {
            classes: input.node_classes,
            epistemic: input.node_epistemic,
            statuses: input.node_statuses,
            metric: input.node_metric,
            flags: &effective_node_flags,
            edge: false,
            theme: input.theme,
        },
        &mut nodes,
    )
    .ok_or(SceneError::Length)?;
    resolve_semantic_styles(
        SemanticStyleInput {
            classes: input.edge_classes,
            epistemic: input.edge_epistemic,
            statuses: input.edge_statuses,
            metric: input.edge_metric,
            flags: input.edge_flags,
            edge: true,
            theme: input.theme,
        },
        &mut edges,
    )
    .ok_or(SceneError::Length)?;

    let mut visible_x = Vec::with_capacity(n.saturating_mul(2));
    let mut visible_y = Vec::with_capacity(n.saturating_mul(2));
    for index in 0..n {
        if !hierarchy.visible[index] {
            continue;
        }
        if hierarchy.is_compound[index] {
            visible_x.extend_from_slice(&hierarchy.bounds[index][..2]);
            visible_y.extend_from_slice(&hierarchy.bounds[index][2..]);
        } else {
            visible_x.push(input.x[index]);
            visible_y.push(input.y[index]);
        }
    }
    let x_domain = padded_domain(&visible_x).ok_or(SceneError::NonFinite)?;
    let y_domain = padded_domain(&visible_y).ok_or(SceneError::NonFinite)?;
    let layout = PlotLayout::new(input.width, input.height, 52.0, 16.0, 24.0, 44.0)?;
    let x_scale = AxisScale::new(
        ScaleKind::Linear,
        x_domain.0,
        x_domain.1,
        layout.left,
        layout.right,
        1.0,
        false,
    )?;
    let y_scale = AxisScale::new(
        ScaleKind::Linear,
        y_domain.0,
        y_domain.1,
        layout.bottom,
        layout.top,
        1.0,
        false,
    )?;
    let to_px = |x: f64, y: f64| {
        (
            layout.left
                + (x - x_domain.0) / (x_domain.1 - x_domain.0) * (layout.right - layout.left),
            layout.bottom
                - (y - y_domain.0) / (y_domain.1 - y_domain.0) * (layout.bottom - layout.top),
        )
    };
    let mut columns = SemanticSceneColumns::default();

    let route_capacity = e
        .checked_mul(EDGE_ROUTE_SEGMENTS_PER_EDGE)
        .ok_or(SceneError::Limit)?;
    let mut route_x0 = vec![0.0; route_capacity];
    let mut route_y0 = vec![0.0; route_capacity];
    let mut route_x1 = vec![0.0; route_capacity];
    let mut route_y1 = vec![0.0; route_capacity];
    let mut route_edge = vec![0; route_capacity];
    let routed_sources: Vec<u64> = input
        .sources
        .iter()
        .map(|&index| hierarchy.representative[index as usize] as u64)
        .collect();
    let routed_targets: Vec<u64> = input
        .targets
        .iter()
        .map(|&index| hierarchy.representative[index as usize] as u64)
        .collect();
    let route_count = edge_route_segments(
        n as u64,
        input.x,
        input.y,
        &routed_sources,
        &routed_targets,
        false,
        0.08,
        0.35,
        0.0,
        &mut route_x0,
        &mut route_y0,
        &mut route_x1,
        &mut route_y1,
        &mut route_edge,
    )
    .ok_or(SceneError::Length)? as usize;
    let mut routes = vec![Vec::new(); e];
    for route in 0..route_count {
        routes[route_edge[route] as usize].push((
            route_x0[route],
            route_y0[route],
            route_x1[route],
            route_y1[route],
        ));
    }

    #[derive(Clone)]
    struct Candidate {
        state: u8,
        stable_id: u64,
        x: f64,
        y: f64,
        rgba: [u8; 4],
        text: String,
    }
    let foreground = if input.theme == THEME_LIGHT {
        [31, 41, 55, 255]
    } else {
        [229, 231, 235, 255]
    };
    let mut candidates = Vec::with_capacity(n.saturating_add(e));
    for (index, text) in input.node_labels.iter().enumerate() {
        if !hierarchy.visible[index]
            || nodes[index].state == STATE_AGGREGATE
            || nodes[index].state == STATE_FILTERED
        {
            continue;
        }
        let (px, py) = to_px(input.x[index], input.y[index]);
        let x = px + f64::from(nodes[index].size) * 0.5 + 4.0;
        if let Some(text) = bounded_label(text, layout.right - x) {
            candidates.push(Candidate {
                state: nodes[index].state,
                stable_id: (1_u64 << 32) + index as u64,
                x,
                y: py + 4.0,
                rgba: foreground,
                text,
            });
        }
    }
    for (index, text) in input.edge_labels.iter().enumerate() {
        if edges[index].state == STATE_AGGREGATE
            || edges[index].state == STATE_FILTERED
            || routes[index].is_empty()
            || (routed_sources[index] == routed_targets[index]
                && input.sources[index] != input.targets[index])
        {
            continue;
        }
        let segment = routes[index][routes[index].len() / 2];
        let (px, py) = to_px((segment.0 + segment.2) * 0.5, (segment.1 + segment.3) * 0.5);
        if let Some(text) = bounded_label(text, layout.right - px) {
            candidates.push(Candidate {
                state: edges[index].state,
                stable_id: index as u64 + 1,
                x: px,
                y: py - 4.0,
                rgba: foreground,
                text,
            });
        }
    }
    candidates.sort_by_key(|candidate| (std::cmp::Reverse(candidate.state), candidate.stable_id));
    let mut occupied: Vec<(f64, f64, f64, f64)> = Vec::new();
    let mut labels = Vec::new();
    for candidate in candidates {
        if labels.len() == crate::scene::MAX_SCENE_LABELS {
            break;
        }
        let width = candidate.text.chars().count() as f64 * GRAPH_LABEL_FONT_SIZE * 0.62;
        let bounds = (
            candidate.x,
            candidate.y - GRAPH_LABEL_FONT_SIZE,
            candidate.x + width,
            candidate.y + 2.0,
        );
        if bounds.0 < layout.left
            || bounds.1 < layout.top
            || bounds.2 > layout.right
            || bounds.3 > layout.bottom
            || occupied.iter().any(|other| {
                bounds.0 < other.2 && bounds.2 > other.0 && bounds.1 < other.3 && bounds.3 > other.1
            })
        {
            continue;
        }
        occupied.push(bounds);
        labels.push(SceneLabel {
            stable_id: candidate.stable_id,
            x: candidate.x,
            y: candidate.y,
            font_size: GRAPH_LABEL_FONT_SIZE,
            rgba: candidate.rgba,
            text: candidate.text,
        });
    }

    // Rust first routes multiedges and loops, then expands resolved dash and
    // arrow geometry in screen space. Hosts never see raw topology decisions.
    for (index, style) in edges.iter().enumerate() {
        if style.opacity <= 0.0
            || (routed_sources[index] == routed_targets[index]
                && input.sources[index] != input.targets[index])
        {
            continue;
        }
        let layer_count = 1
            + usize::from(input.edge_epistemic[index] != 0)
            + usize::from(input.edge_classes[index] != 0);
        let remaining = MAX_SEMANTIC_GRAPH_SCENE_PRIMITIVES
            .checked_sub(columns.primitives)
            .ok_or(SceneError::Limit)?;
        let mut geometry = Vec::new();
        let mut push_geometry = |segment| -> Result<(), SceneError> {
            let count = geometry.len().checked_add(1).ok_or(SceneError::Limit)?;
            if count
                .checked_mul(layer_count)
                .is_none_or(|value| value > remaining)
            {
                return Err(SceneError::Limit);
            }
            geometry.push(segment);
            Ok(())
        };
        for &(ax, ay, bx, by) in &routes[index] {
            let (apx, apy) = to_px(ax, ay);
            let (bpx, bpy) = to_px(bx, by);
            let length = (bpx - apx).hypot(bpy - apy);
            if !length.is_finite() || length <= f64::EPSILON {
                continue;
            }
            let pattern = match style.dash {
                1 => (6.0, 4.0),
                2 => (2.0, 3.0),
                3 => (10.0, 4.0),
                _ => (length, 0.0),
            };
            // Preserve authored dash ratios while bounding screen-space
            // expansion for very large but valid viewports.
            let period = pattern.0 + pattern.1;
            let pattern = if pattern.1 > 0.0 && length / period > 64.0 {
                let scale = length / (period * 64.0);
                (pattern.0 * scale, pattern.1 * scale)
            } else {
                pattern
            };
            let mut cursor = 0.0;
            while cursor < length {
                let end = (cursor + pattern.0).min(length);
                let t0 = cursor / length;
                let t1 = end / length;
                push_geometry((
                    ax + (bx - ax) * t0,
                    ay + (by - ay) * t0,
                    ax + (bx - ax) * t1,
                    ay + (by - ay) * t1,
                ))?;
                if pattern.1 == 0.0 {
                    break;
                }
                cursor = end + pattern.1;
            }
        }
        if style.arrow != 0 && !routes[index].is_empty() {
            let &(ax, ay, bx, by) = routes[index].last().unwrap();
            let (apx, apy) = to_px(ax, ay);
            let (bpx, bpy) = to_px(bx, by);
            let length = (bpx - apx).hypot(bpy - apy);
            if length >= 8.0 {
                let ux = (bpx - apx) / length;
                let uy = (bpy - apy) / length;
                let arrow = (6.0 + f64::from(style.width)).min(length * 0.35);
                for side in [-1.0, 1.0] {
                    let px = bpx - ux * arrow + (-uy) * side * arrow * 0.55;
                    let py = bpy - uy * arrow + ux * side * arrow * 0.55;
                    let dx = x_domain.0
                        + (px - layout.left) / (layout.right - layout.left)
                            * (x_domain.1 - x_domain.0);
                    let dy = y_domain.0
                        + (layout.bottom - py) / (layout.bottom - layout.top)
                            * (y_domain.1 - y_domain.0);
                    push_geometry((bx, by, dx, dy))?;
                }
            }
        }
        // The line-like Scene primitive has one paint. Rust therefore lowers
        // the complete three-channel semantic edge style as ordered layers:
        // epistemic halo, class body, then status stroke. Consumers only paint.
        let mut layers = Vec::with_capacity(3);
        if input.edge_epistemic[index] != 0 {
            layers.push((
                alpha(style.halo, style.opacity, 0.38),
                f64::from(style.width + 5.0),
            ));
        }
        if input.edge_classes[index] != 0 {
            layers.push((
                alpha(style.fill, style.opacity, 1.0),
                f64::from(style.width + 2.0),
            ));
        }
        layers.push((
            alpha(style.stroke, style.opacity, 1.0),
            f64::from(style.width),
        ));
        let stable = index as u64 + 1;
        for (paint, width) in layers {
            for &(x0, y0, x1, y1) in &geometry {
                // Fresh style_ref is the run plane: reusing a deduplicated
                // style would join adjacent records and paint across dash gaps.
                let style_ref = columns.fresh_style([0; 4], paint, width)?;
                columns.line(stable, style_ref, x0, y0, x1, y1)?;
            }
        }
    }
    for (index, style) in nodes.iter().copied().enumerate() {
        if !hierarchy.visible[index] || !hierarchy.is_compound[index] {
            continue;
        }
        let bounds = hierarchy.bounds[index];
        if bounds.iter().any(|value| !value.is_finite()) {
            continue;
        }
        let outline = columns.style([0; 4], alpha(style.stroke, style.opacity, 0.72), 1.5);
        columns.rect(
            (1u64 << 32) + index as u64,
            outline,
            bounds[0],
            bounds[2],
            bounds[1],
            bounds[3],
        )?;
    }
    for (index, style) in nodes.iter().enumerate() {
        if !hierarchy.visible[index] || style.opacity <= 0.0 {
            continue;
        }
        let stable = (1u64 << 32) + index as u64;
        if input.node_epistemic[index] != 0 {
            let halo = alpha(style.halo, style.opacity, 0.38);
            let halo_ref = columns.style(halo, [0; 4], 0.0);
            columns.point(
                stable,
                halo_ref,
                f64::from(style.size + 7.0),
                0,
                input.x[index],
                input.y[index],
            )?;
        }
        let node_ref = columns.style(
            alpha(style.fill, style.opacity, 1.0),
            alpha(style.stroke, style.opacity, 1.0),
            f64::from(style.width),
        );
        columns.point(
            stable,
            node_ref,
            f64::from(style.size),
            style.shape,
            input.x[index],
            input.y[index],
        )?;
    }

    let mut descriptors = semantic_legend(
        input.node_classes,
        input.node_epistemic,
        input.node_statuses,
        input.theme,
    )
    .ok_or(SceneError::Length)?;
    let edge_descriptors = semantic_legend(
        input.edge_classes,
        input.edge_epistemic,
        input.edge_statuses,
        input.theme,
    )
    .ok_or(SceneError::Length)?;
    for descriptor in edge_descriptors {
        if !descriptors
            .iter()
            .any(|item| item.field == descriptor.field && item.value == descriptor.value)
        {
            descriptors.push(descriptor);
        }
    }
    descriptors.sort_by_key(|item| (item.field, item.value));
    let mut legend_entries = Vec::with_capacity(descriptors.len());
    for descriptor in descriptors {
        let style_ref = columns.style(descriptor.color, descriptor.color, 1.5) as usize;
        legend_entries.push(SceneLegendEntry {
            style_ref,
            kind: SceneRecordKind::Scatter,
            symbol: descriptor.shape,
            fill_rgba: descriptor.color,
            stroke_rgba: descriptor.color,
            label: semantic_legend_label(descriptor.field, descriptor.value),
        });
    }
    let colors = palette(input.theme).ok_or(SceneError::Length)?;
    let legend = (!legend_entries.is_empty()).then(|| SceneLegend {
        location: LegendLocation::UpperRight,
        title: "Graph semantics".to_owned(),
        font_size: 11.0,
        title_font_size: 12.0,
        text_rgba: colors[0],
        frame_fill_rgba: if input.theme == THEME_LIGHT {
            [255, 255, 255, 238]
        } else {
            [17, 24, 39, 238]
        },
        frame_stroke_rgba: colors[0],
        entries: legend_entries,
    });
    let mut chrome = SceneChromeStyle::default();
    let (chart_bg, plot_bg, foreground, grid) = if input.theme == THEME_LIGHT {
        (
            [255, 255, 255, 255],
            [248, 250, 252, 255],
            [31, 41, 55, 255],
            [31, 41, 55, 38],
        )
    } else {
        (
            [3, 7, 18, 255],
            [17, 24, 39, 255],
            [229, 231, 235, 255],
            [229, 231, 235, 42],
        )
    };
    chrome.chart_background_rgba = chart_bg;
    chrome.plot_background_rgba = plot_bg;
    chrome.label_rgba = foreground;
    for axis in [&mut chrome.x_axis, &mut chrome.y_axis] {
        axis.axis_rgba = foreground;
        axis.tick_rgba = foreground;
        axis.minor_tick_rgba = foreground;
        axis.label_rgba = foreground;
        axis.grid_rgba = grid;
    }
    SceneBatch::new_with_decorations_and_labels(
        layout,
        1,
        2,
        x_scale,
        y_scale,
        chrome,
        SceneChromeText::from_parts(input.title, "", "")?,
        legend,
        labels,
        &columns.kinds,
        &columns.stable_ids,
        &columns.style_refs,
        &columns.fill_rgba,
        &columns.stroke_rgba,
        &columns.stroke_width,
        &columns.diameter,
        &columns.symbols,
        &columns.x0,
        &columns.y0,
        &columns.x1,
        &columns.y1,
    )
    .map(|batch| batch.encode())
}

#[must_use]
pub fn resolve_visual_state(flags: u32) -> u8 {
    if flags & FLAG_DISABLED != 0 {
        STATE_DISABLED
    } else if flags & FLAG_FILTERED != 0 {
        STATE_FILTERED
    } else if flags & FLAG_SELECTED != 0 {
        STATE_SELECTED
    } else if flags & FLAG_HOVERED != 0 {
        STATE_HOVERED
    } else if flags & FLAG_NEIGHBOR != 0 {
        STATE_NEIGHBOR
    } else if flags & FLAG_PINNED != 0 {
        STATE_PINNED
    } else if flags & FLAG_AGGREGATE != 0 {
        STATE_AGGREGATE
    } else {
        STATE_NORMAL
    }
}

pub fn resolve_visual_states(flags: &[u32], out: &mut [u8]) -> Option<()> {
    if flags.len() != out.len() {
        return None;
    }
    for (flag, state) in flags.iter().zip(out.iter_mut()) {
        *state = resolve_visual_state(*flag);
    }
    Some(())
}

pub fn label_accept(priorities: &[f64], budget: u64, floor: f64, out: &mut [u8]) -> Option<u64> {
    if priorities.len() != out.len() {
        return None;
    }
    out.fill(0);
    let mut ranked: Vec<(usize, f64)> = priorities
        .iter()
        .copied()
        .enumerate()
        .filter(|(_, p)| p.is_finite() && (!floor.is_finite() || *p >= floor))
        .collect();
    ranked.sort_by(|a, b| b.1.total_cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    let take = usize::try_from(budget)
        .unwrap_or(usize::MAX)
        .min(ranked.len());
    for &(index, _) in ranked.iter().take(take) {
        out[index] = 1;
    }
    Some(take as u64)
}

#[derive(Debug)]
struct CompoundHierarchy {
    direct_parent: Vec<Option<usize>>,
    representative: Vec<usize>,
    visible: Vec<bool>,
    is_compound: Vec<bool>,
    bounds: Vec<[f64; 4]>,
    depth: Vec<usize>,
}

fn compound_hierarchy(
    parents: &[u64],
    validity: &[u8],
    collapsed: &[u8],
) -> Option<CompoundHierarchy> {
    let n = parents.len();
    if validity.len() != n
        || collapsed.len() != n
        || validity.iter().chain(collapsed).any(|&value| value > 1)
    {
        return None;
    }
    let mut direct_parent = vec![None; n];
    let mut is_compound = vec![false; n];
    for index in 0..n {
        if validity[index] == 0 {
            continue;
        }
        let parent = usize::try_from(parents[index])
            .ok()
            .filter(|&value| value < n)?;
        if parent == index {
            return None;
        }
        direct_parent[index] = Some(parent);
        is_compound[parent] = true;
    }
    if collapsed
        .iter()
        .enumerate()
        .any(|(index, &value)| value != 0 && !is_compound[index])
    {
        return None;
    }
    let mut color = vec![0u8; n];
    let mut depth = vec![0usize; n];
    for start in 0..n {
        if color[start] == 2 {
            continue;
        }
        let mut node = start;
        let mut path = Vec::new();
        loop {
            if color[node] == 1 {
                return None;
            }
            if color[node] == 2 {
                break;
            }
            color[node] = 1;
            path.push(node);
            let Some(parent) = direct_parent[node] else {
                break;
            };
            node = parent;
        }
        let mut next_depth = if color[node] == 2 {
            depth[node].checked_add(1)?
        } else {
            0
        };
        for &visited in path.iter().rev() {
            depth[visited] = next_depth;
            next_depth = next_depth.checked_add(1)?;
            color[visited] = 2;
        }
    }
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by_key(|&index| (depth[index], index));
    let mut representative: Vec<usize> = (0..n).collect();
    let mut visible = vec![true; n];
    for &index in &order {
        let Some(parent) = direct_parent[index] else {
            continue;
        };
        if collapsed[parent] != 0 || !visible[parent] {
            visible[index] = false;
            representative[index] = representative[parent];
        }
    }
    Some(CompoundHierarchy {
        direct_parent,
        representative,
        visible,
        is_compound,
        bounds: vec![[f64::NAN; 4]; n],
        depth,
    })
}

/// Apply one public compound disclosure transition without exposing hierarchy
/// or LOD policy to a host. The complete forest and stable-ID plane are
/// validated before `out` changes; aggregate representations refuse source-ID
/// transitions because their identities are not one-to-one with source nodes.
pub fn compound_collapse_transition(
    node_ids: &[u64],
    parents: &[u64],
    validity: &[u8],
    collapsed: &[u8],
    target_id: u64,
    action: u8,
    lod_tier: u8,
    out: &mut [u8],
) -> Option<bool> {
    let n = node_ids.len();
    if n == 0
        || n > MAX_COMPOUND_TRANSITION_NODES
        || parents.len() != n
        || validity.len() != n
        || collapsed.len() != n
        || out.len() != n
        || lod_tier != GRAPH_LOD_DIRECT
        || action > COMPOUND_ACTION_TOGGLE
    {
        return None;
    }
    let hierarchy = compound_hierarchy(parents, validity, collapsed)?;
    let mut target = None;
    let mut ids = node_ids.to_vec();
    ids.sort_unstable();
    if ids.windows(2).any(|pair| pair[0] == pair[1]) {
        return None;
    }
    for (index, &id) in node_ids.iter().enumerate() {
        if id == target_id {
            target = Some(index);
            break;
        }
    }
    let target = target.filter(|&index| hierarchy.is_compound[index])?;
    let next = match action {
        COMPOUND_ACTION_EXPAND => 0,
        COMPOUND_ACTION_COLLAPSE => 1,
        COMPOUND_ACTION_TOGGLE => 1 - collapsed[target],
        _ => unreachable!(),
    };
    let changed = next != collapsed[target];
    let mut resolved = collapsed.to_vec();
    resolved[target] = next;
    out.copy_from_slice(&resolved);
    Some(changed)
}

fn collapsed_node_flags(flags: &[u32], hierarchy: &CompoundHierarchy) -> Option<Vec<u32>> {
    if flags.len() != hierarchy.visible.len() {
        return None;
    }
    const PROPAGATED: u32 = FLAG_SELECTED | FLAG_HOVERED | FLAG_NEIGHBOR | FLAG_PINNED;
    let mut effective = flags.to_vec();
    for index in 0..flags.len() {
        if !hierarchy.visible[index] {
            effective[hierarchy.representative[index]] |= flags[index] & PROPAGATED;
        }
    }
    Some(effective)
}

#[allow(clippy::too_many_arguments)]
/// Validate one parent forest and emit direct membership plus transitive bounds.
/// Outputs remain untouched when any shape, validity, parent, or cycle is invalid.
pub fn compound_bounds(
    x: &[f64],
    y: &[f64],
    parents: &[u64],
    validity: &[u8],
    parent_of: &mut [u64],
    is_compound: &mut [u8],
    xmin: &mut [f64],
    xmax: &mut [f64],
    ymin: &mut [f64],
    ymax: &mut [f64],
) -> Option<()> {
    let n = x.len();
    if [
        y.len(),
        parents.len(),
        validity.len(),
        parent_of.len(),
        is_compound.len(),
        xmin.len(),
        xmax.len(),
        ymin.len(),
        ymax.len(),
    ]
    .iter()
    .any(|&len| len != n)
    {
        return None;
    }
    let mut hierarchy = compound_hierarchy(parents, validity, &vec![0; n])?;
    parent_of.fill(NO_COMPOUND);
    is_compound.fill(0);
    xmin.fill(f64::NAN);
    xmax.fill(f64::NAN);
    ymin.fill(f64::NAN);
    ymax.fill(f64::NAN);
    let expand = |bounds: &mut [f64; 4], px: f64, py: f64| {
        if !px.is_finite() || !py.is_finite() {
            return;
        }
        if bounds[0].is_nan() {
            *bounds = [px, px, py, py];
        } else {
            bounds[0] = bounds[0].min(px);
            bounds[1] = bounds[1].max(px);
            bounds[2] = bounds[2].min(py);
            bounds[3] = bounds[3].max(py);
        }
    };
    for i in 0..n {
        expand(&mut hierarchy.bounds[i], x[i], y[i]);
        if let Some(parent) = hierarchy.direct_parent[i] {
            parent_of[i] = parent as u64;
        }
        is_compound[i] = u8::from(hierarchy.is_compound[i]);
    }
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by_key(|&index| (std::cmp::Reverse(hierarchy.depth[index]), index));
    for index in order {
        let Some(parent) = hierarchy.direct_parent[index] else {
            continue;
        };
        let child = hierarchy.bounds[index];
        if child[0].is_finite() {
            expand(&mut hierarchy.bounds[parent], child[0], child[2]);
            expand(&mut hierarchy.bounds[parent], child[1], child[3]);
        }
    }
    for i in 0..n {
        if hierarchy.is_compound[i] {
            [xmin[i], xmax[i], ymin[i], ymax[i]] = hierarchy.bounds[i];
        }
    }
    Some(())
}

#[cfg(test)]
mod tests {
    use super::*;

    macro_rules! resolve {
        ($classes:expr, $epistemic:expr, $statuses:expr, $metric:expr, $flags:expr, $edge:expr, $theme:expr, $out:expr $(,)?) => {
            resolve_semantic_styles(
                SemanticStyleInput {
                    classes: $classes,
                    epistemic: $epistemic,
                    statuses: $statuses,
                    metric: $metric,
                    flags: $flags,
                    edge: $edge,
                    theme: $theme,
                },
                $out,
            )
        };
    }
    #[test]
    fn precedence_is_stable() {
        assert_eq!(
            resolve_visual_state(FLAG_SELECTED | FLAG_DISABLED),
            STATE_DISABLED
        );
        assert_eq!(
            resolve_visual_state(FLAG_SELECTED | FLAG_HOVERED),
            STATE_SELECTED
        );
    }
    #[test]
    fn labels_are_deterministic() {
        let mut out = [0; 5];
        assert_eq!(
            label_accept(&[1., 5., 5., 3., f64::NAN], 2, f64::NAN, &mut out),
            Some(2)
        );
        assert_eq!(out, [0, 1, 1, 0, 0]);
    }
    #[test]
    fn compounds_include_parent_and_children() {
        let mut po = [0; 4];
        let mut ic = [0; 4];
        let mut xmin = [0.; 4];
        let mut xmax = [0.; 4];
        let mut ymin = [0.; 4];
        let mut ymax = [0.; 4];
        compound_bounds(
            &[0., -1., 2., 9.],
            &[0., 1., 3., 9.],
            &[0, 0, 0, 0],
            &[0, 1, 1, 0],
            &mut po,
            &mut ic,
            &mut xmin,
            &mut xmax,
            &mut ymin,
            &mut ymax,
        )
        .unwrap();
        assert_eq!(po, [NO_COMPOUND, 0, 0, NO_COMPOUND]);
        assert_eq!((xmin[0], xmax[0], ymin[0], ymax[0]), (-1., 2., 0., 3.));
    }
    #[test]
    fn compound_bounds_are_transitive_and_deep_chains_stay_bounded() {
        let n = 1024;
        let x: Vec<f64> = (0..n).map(|index| index as f64).collect();
        let y: Vec<f64> = (0..n).map(|index| -(index as f64)).collect();
        let mut parents = vec![0; n];
        let mut validity = vec![1; n];
        validity[0] = 0;
        for (index, parent) in parents.iter_mut().enumerate().skip(1) {
            *parent = (index - 1) as u64;
        }
        let mut parent_of = vec![0; n];
        let mut is_compound = vec![0; n];
        let mut xmin = vec![0.0; n];
        let mut xmax = vec![0.0; n];
        let mut ymin = vec![0.0; n];
        let mut ymax = vec![0.0; n];
        compound_bounds(
            &x,
            &y,
            &parents,
            &validity,
            &mut parent_of,
            &mut is_compound,
            &mut xmin,
            &mut xmax,
            &mut ymin,
            &mut ymax,
        )
        .unwrap();
        assert_eq!(
            [xmin[0], xmax[0], ymin[0], ymax[0]],
            [0.0, 1023.0, -1023.0, 0.0]
        );
        assert_eq!([xmin[512], xmax[512]], [512.0, 1023.0]);
        assert_eq!(parent_of[1023], 1022);
        assert_eq!(is_compound[1023], 0);
    }
    #[test]
    fn compound_cycles_fail_before_writing_outputs() {
        let mut po = [11; 3];
        let mut ic = [12; 3];
        let mut xmin = [13.; 3];
        let mut xmax = [14.; 3];
        let mut ymin = [15.; 3];
        let mut ymax = [16.; 3];
        assert_eq!(
            compound_bounds(
                &[0.; 3],
                &[0.; 3],
                &[1, 2, 0],
                &[1; 3],
                &mut po,
                &mut ic,
                &mut xmin,
                &mut xmax,
                &mut ymin,
                &mut ymax
            ),
            None
        );
        assert_eq!(po, [11; 3]);
        assert_eq!(ic, [12; 3]);
        assert_eq!(xmin, [13.; 3]);
        assert_eq!(ymax, [16.; 3]);
    }

    #[test]
    fn collapse_visibility_is_transitive_deterministic_and_strict() {
        let hierarchy =
            compound_hierarchy(&[0, 0, 1, 0, 0], &[0, 1, 1, 1, 0], &[1, 0, 0, 0, 0]).unwrap();
        assert_eq!(hierarchy.visible, [true, false, false, false, true]);
        assert_eq!(hierarchy.representative, [0, 0, 0, 0, 4]);
        assert_eq!(hierarchy.is_compound, [true, true, false, false, false]);
        assert_eq!(
            collapsed_node_flags(
                &[0, 0, FLAG_SELECTED | FLAG_DISABLED, FLAG_PINNED, 0],
                &hierarchy
            )
            .unwrap(),
            [
                FLAG_SELECTED | FLAG_PINNED,
                0,
                FLAG_SELECTED | FLAG_DISABLED,
                FLAG_PINNED,
                0
            ]
        );
        assert!(compound_hierarchy(&[0, 0], &[0, 2], &[0, 0]).is_none());
        assert!(compound_hierarchy(&[0, 0], &[0, 1], &[0, 2]).is_none());
        assert!(compound_hierarchy(&[0, 0], &[0, 0], &[0, 1]).is_none());
        assert!(compound_hierarchy(&[1, 0], &[1, 1], &[0, 0]).is_none());
    }

    #[test]
    fn semantic_style_golden_and_state_precedence_are_stable() {
        let mut out = [ResolvedGraphStyle {
            fill: [0; 4],
            stroke: [0; 4],
            halo: [0; 4],
            size: 0.0,
            width: 0.0,
            opacity: 0.0,
            shape: 0,
            dash: 0,
            arrow: 0,
            state: 0,
        }; 3];
        let domain = resolve!(
            &[1, 2, 3],
            &[2, 3, 4],
            &[1, 2, 3],
            &[10.0, 20.0, 30.0],
            &[0, FLAG_HOVERED | FLAG_SELECTED, FLAG_DISABLED],
            false,
            THEME_LIGHT,
            &mut out,
        )
        .unwrap();
        assert_eq!(domain, (10.0, 30.0));
        assert_eq!(out[0].fill, [0, 90, 156, 255]);
        assert_eq!((out[0].size, out[0].shape), (7.0, 1));
        assert_eq!(
            (out[1].state, out[1].stroke),
            (STATE_SELECTED, [0, 0, 0, 255])
        );
        assert_eq!((out[2].state, out[2].opacity), (STATE_DISABLED, 0.28));
    }

    #[test]
    fn edge_style_and_legend_are_deterministic() {
        let mut out = [ResolvedGraphStyle {
            fill: [0; 4],
            stroke: [0; 4],
            halo: [0; 4],
            size: 0.0,
            width: 0.0,
            opacity: 0.0,
            shape: 0,
            dash: 0,
            arrow: 0,
            state: 0,
        }; 2];
        resolve!(
            &[2, 2],
            &[3, 1],
            &[0, 4],
            &[f64::NAN, 8.0],
            &[0, 0],
            true,
            THEME_LIGHT,
            &mut out,
        )
        .unwrap();
        assert_eq!(out[0].size, 0.0);
        assert_eq!((out[0].dash, out[0].arrow), (3, 0));
        assert_eq!((out[1].dash, out[1].arrow), (1, 1));
        let legend = semantic_legend(&[2, 1, 2], &[3, 3, 1], &[4, 0, 4], THEME_LIGHT).unwrap();
        assert_eq!(
            legend
                .iter()
                .map(|e| (e.field, e.value))
                .collect::<Vec<_>>(),
            vec![(0, 1), (0, 2), (1, 1), (1, 3), (2, 0), (2, 4)]
        );
    }

    #[test]
    fn semantic_resolution_is_atomic_and_bounded() {
        let sentinel = ResolvedGraphStyle {
            fill: [9; 4],
            stroke: [9; 4],
            halo: [9; 4],
            size: 9.0,
            width: 9.0,
            opacity: 9.0,
            shape: 9,
            dash: 9,
            arrow: 9,
            state: 9,
        };
        let mut out = [sentinel];
        assert_eq!(
            resolve!(&[8], &[0], &[0], &[0.0], &[0], false, THEME_LIGHT, &mut out),
            None
        );
        assert_eq!(out, [sentinel]);
    }

    #[test]
    fn semantic_graph_scene_is_one_exact_browser_svg_and_raster_contract() {
        let bytes = encode_semantic_graph_scene(SemanticGraphSceneInput {
            version: SEMANTIC_GRAPH_SCENE_VERSION,
            width: 800.0,
            height: 600.0,
            theme: THEME_LIGHT,
            title: "GraphForge semantics",
            x: &[0.0, 1.0, 0.5],
            y: &[0.0, 0.0, 1.0],
            node_classes: &[1, 2, 3],
            node_epistemic: &[1, 0, 2],
            node_statuses: &[0, 1, 2],
            node_metric: &[0.0, 0.5, 1.0],
            node_flags: &[FLAG_SELECTED, FLAG_DISABLED, 0],
            node_labels: &["Selected node", "Disabled node", "Third node"],
            // Parallel edges and a self-loop prove Rust-owned routing is not
            // silently omitted by any Scene consumer.
            sources: &[0, 0, 2],
            targets: &[2, 2, 2],
            edge_classes: &[1, 2, 3],
            edge_epistemic: &[1, 3, 2],
            edge_statuses: &[1, 0, 2],
            edge_metric: &[1.0, 2.0, 3.0],
            edge_flags: &[0, FLAG_PINNED, 0],
            edge_labels: &["first edge", "pinned edge", "loop"],
        })
        .unwrap();
        let document = crate::scene::SceneDocument::decode(&bytes).unwrap();
        let svg = document.to_svg();
        let painter = document.to_browser_painter(1 << 20).unwrap();
        let raster = document.to_raster_commands(1.0).unwrap();
        assert!(svg.contains("GraphForge semantics"));
        assert!(svg.contains("Graph semantics"));
        assert!(svg.contains("Class 1"));
        assert!(svg.contains("data-xy-chrome=\"chart-background\""));
        assert!(svg.contains("data-xy-chrome=\"graph_labels\""));
        assert!(svg.contains("Selected node"));
        assert!(svg.contains("data-xy-stable-id=\"4294967296\""));
        assert!(document.record_count() > 10); // dash + arrowheads + halos
        assert_eq!(&painter[..4], b"XYPB");
        let trace_count = u32::from_le_bytes(painter[20..24].try_into().unwrap()) as usize;
        let mut edge_ids = Vec::new();
        for trace in 0..trace_count {
            let descriptor = crate::scene::BROWSER_PAINTER_HEADER_BYTES
                + trace * crate::scene::BROWSER_PAINTER_TRACE_BYTES;
            if painter[descriptor] != SceneRecordKind::Polyline as u8 {
                continue;
            }
            let count =
                u32::from_le_bytes(painter[descriptor + 4..descriptor + 8].try_into().unwrap())
                    as usize;
            let low = u32::from_le_bytes(
                painter[descriptor + 24..descriptor + 28]
                    .try_into()
                    .unwrap(),
            ) as usize;
            for row in 0..count {
                edge_ids.push(u32::from_le_bytes(
                    painter[low + row * 4..low + row * 4 + 4]
                        .try_into()
                        .unwrap(),
                ) as u64);
            }
        }
        assert!(edge_ids.iter().all(|id| (1..=3).contains(id)));
        assert!(edge_ids.iter().filter(|&&id| id == 1).count() > 4);
        assert!(edge_ids.iter().filter(|&&id| id == 3).count() >= 3);
        assert!(painter.windows(4).any(|window| window == b"XYLG"));
        assert!(painter.windows(4).any(|window| window == b"XYLB"));
        assert!(raster
            .windows("Selected node".len())
            .any(|window| window == b"Selected node"));
        assert!(!raster.is_empty());
        #[cfg(feature = "raster")]
        {
            let mut rgba = vec![0; 800 * 600 * 4];
            assert!(crate::raster::rasterize_into(&raster, 800, 600, &mut rgba));
            assert!(rgba.chunks_exact(4).any(|pixel| pixel[3] != 0));
            assert_eq!(&rgba[..4], &[255, 255, 255, 255]);
            let plot_pixel = (100 * 800 + 100) * 4;
            assert_eq!(&rgba[plot_pixel..plot_pixel + 4], &[248, 250, 252, 255]);
        }
    }

    #[test]
    fn collapsed_nested_scene_hides_descendants_and_remaps_only_boundary_edges() {
        let graph = SemanticGraphSceneInput {
            version: SEMANTIC_GRAPH_SCENE_VERSION,
            width: 640.0,
            height: 480.0,
            theme: THEME_LIGHT,
            title: "Collapsed hierarchy",
            x: &[0.0, 1.0, 2.0, -1.0, -3.0],
            y: &[0.0, 1.0, 2.0, -1.0, 0.0],
            node_classes: &[1, 1, 1, 1, 2],
            node_epistemic: &[0; 5],
            node_statuses: &[0; 5],
            node_metric: &[0.0; 5],
            node_flags: &[0, 0, FLAG_SELECTED, 0, 0],
            node_labels: &[
                "Collapsed group",
                "Hidden child",
                "Hidden grandchild",
                "Hidden sibling",
                "Outside",
            ],
            sources: &[2, 2],
            targets: &[3, 4],
            edge_classes: &[1, 1],
            edge_epistemic: &[0, 0],
            edge_statuses: &[0, 0],
            edge_metric: &[0.0, 0.0],
            edge_flags: &[0, 0],
            edge_labels: &["internal edge", "boundary edge"],
        };
        let bytes = encode_compound_graph_scene(CompoundGraphSceneInput {
            graph,
            parents: &[0, 0, 1, 0, 0],
            parent_validity: &[0, 1, 1, 1, 0],
            collapsed: &[1, 0, 0, 0, 0],
        })
        .unwrap();
        for (parents, validity, collapsed) in [
            (
                &[0, 0, 1, 0][..],
                &[0, 1, 1, 1, 0][..],
                &[1, 0, 0, 0, 0][..],
            ),
            (
                &[0, 0, 1, 0, 0, 0][..],
                &[0, 1, 1, 1, 0][..],
                &[1, 0, 0, 0, 0][..],
            ),
            (
                &[0, 0, 1, 0, 0][..],
                &[0, 1, 1, 1][..],
                &[1, 0, 0, 0, 0][..],
            ),
            (
                &[0, 0, 1, 0, 0][..],
                &[0, 1, 1, 1, 0][..],
                &[1, 0, 0, 0, 0, 0][..],
            ),
        ] {
            assert_eq!(
                encode_compound_graph_scene(CompoundGraphSceneInput {
                    graph,
                    parents,
                    parent_validity: validity,
                    collapsed,
                }),
                Err(SceneError::Length),
            );
        }
        let document = crate::scene::SceneDocument::decode(&bytes).unwrap();
        let svg = document.to_svg();
        let painter = document.to_browser_painter(1 << 20).unwrap();
        let raster = document.to_raster_commands(1.0).unwrap();
        assert!(svg.contains("Collapsed group"));
        assert!(svg.contains("Outside"));
        assert!(svg.contains("boundary edge"));
        assert!(!svg.contains("Hidden child"));
        assert!(!svg.contains("Hidden grandchild"));
        assert!(!svg.contains("Hidden sibling"));
        assert!(!svg.contains("internal edge"));
        assert!(svg.contains("data-xy-stable-id=\"4294967296\""));
        assert!(painter.windows(4).any(|window| window == b"XYLB"));
        assert!(painter
            .windows("Collapsed group".len())
            .any(|window| window == b"Collapsed group"));
        assert!(!painter
            .windows("Hidden child".len())
            .any(|window| window == b"Hidden child"));
        let trace_count = u32::from_le_bytes(painter[20..24].try_into().unwrap()) as usize;
        let mut painter_ids = Vec::new();
        for trace in 0..trace_count {
            let descriptor = crate::scene::BROWSER_PAINTER_HEADER_BYTES
                + trace * crate::scene::BROWSER_PAINTER_TRACE_BYTES;
            let count =
                u32::from_le_bytes(painter[descriptor + 4..descriptor + 8].try_into().unwrap())
                    as usize;
            let low = u32::from_le_bytes(
                painter[descriptor + 24..descriptor + 28]
                    .try_into()
                    .unwrap(),
            ) as usize;
            let high = u32::from_le_bytes(
                painter[descriptor + 28..descriptor + 32]
                    .try_into()
                    .unwrap(),
            ) as usize;
            for row in 0..count {
                let lo = u32::from_le_bytes(
                    painter[low + row * 4..low + row * 4 + 4]
                        .try_into()
                        .unwrap(),
                ) as u64;
                let hi = u32::from_le_bytes(
                    painter[high + row * 4..high + row * 4 + 4]
                        .try_into()
                        .unwrap(),
                ) as u64;
                painter_ids.push((hi << 32) | lo);
            }
        }
        assert!(painter_ids.contains(&(1_u64 << 32)));
        assert!(painter_ids.contains(&((1_u64 << 32) + 4)));
        assert!(painter_ids.contains(&2));
        assert!(!painter_ids.contains(&1));
        assert!(!(1_u64..=3).any(|index| painter_ids.contains(&((1_u64 << 32) + index))));
        assert!(!raster
            .windows("Hidden child".len())
            .any(|window| window == b"Hidden child"));
        #[cfg(feature = "raster")]
        {
            let mut rgba = vec![0; 640 * 480 * 4];
            assert!(crate::raster::rasterize_into(&raster, 640, 480, &mut rgba));
            assert!(rgba
                .chunks_exact(4)
                .any(|pixel| pixel != [255, 255, 255, 255] && pixel != [248, 250, 252, 255]));
        }
    }

    #[test]
    fn semantic_graph_scene_rejects_huge_finite_viewports_before_geometry_allocation() {
        let result = encode_semantic_graph_scene(SemanticGraphSceneInput {
            version: SEMANTIC_GRAPH_SCENE_VERSION,
            width: MAX_SEMANTIC_GRAPH_VIEWPORT + 1.0,
            height: 600.0,
            theme: THEME_LIGHT,
            title: "",
            x: &[0.0, 1.0],
            y: &[0.0, 1.0],
            node_classes: &[0, 0],
            node_epistemic: &[0, 0],
            node_statuses: &[0, 0],
            node_metric: &[0.0, 1.0],
            node_flags: &[0, 0],
            node_labels: &["", ""],
            sources: &[0],
            targets: &[1],
            edge_classes: &[1],
            edge_epistemic: &[1],
            edge_statuses: &[1],
            edge_metric: &[0.0],
            edge_flags: &[0],
            edge_labels: &[""],
        });
        assert_eq!(result, Err(SceneError::Length));
    }

    #[test]
    fn browser_semantic_graph_fixture_compiles_with_dark_state_planes() {
        assert!(encode_semantic_graph_scene(SemanticGraphSceneInput {
            version: SEMANTIC_GRAPH_SCENE_VERSION,
            width: 800.0,
            height: 600.0,
            theme: THEME_DARK,
            title: "Semantic graph",
            x: &[0.0, 1.0, 0.5],
            y: &[0.0, 0.0, 1.0],
            node_classes: &[1, 2, 3],
            node_epistemic: &[1, 0, 2],
            node_statuses: &[0, 1, 2],
            node_metric: &[0.0, 0.5, 1.0],
            node_flags: &[2, 64, 0],
            node_labels: &["", "", ""],
            sources: &[0, 1],
            targets: &[2, 2],
            edge_classes: &[1, 2],
            edge_epistemic: &[1, 3],
            edge_statuses: &[1, 0],
            edge_metric: &[1.0, 2.0],
            edge_flags: &[0, 16],
            edge_labels: &["", ""],
        })
        .is_ok());
    }

    #[test]
    fn semantic_graph_scene_fails_closed_before_unbounded_primitive_growth() {
        let edges = 6;
        assert_eq!(
            encode_semantic_graph_scene(SemanticGraphSceneInput {
                version: SEMANTIC_GRAPH_SCENE_VERSION,
                width: MAX_SEMANTIC_GRAPH_VIEWPORT,
                height: 600.0,
                theme: 0,
                title: "",
                x: &[0.0, 1.0],
                y: &[0.0, 1.0],
                node_classes: &[0, 0],
                node_epistemic: &[0, 0],
                node_statuses: &[0, 0],
                node_metric: &[0.0, 1.0],
                node_flags: &[0, 0],
                node_labels: &["", ""],
                sources: &vec![0; edges],
                targets: &vec![1; edges],
                edge_classes: &vec![1; edges],
                edge_epistemic: &vec![1; edges],
                edge_statuses: &vec![1; edges],
                edge_metric: &vec![0.0; edges],
                edge_flags: &vec![0; edges],
                edge_labels: &vec![""; edges],
            }),
            Err(SceneError::Limit)
        );
    }

    fn luminance(color: [u8; 4]) -> f64 {
        let linear = |byte: u8| {
            let c = f64::from(byte) / 255.0;
            if c <= 0.04045 {
                c / 12.92
            } else {
                ((c + 0.055) / 1.055).powf(2.4)
            }
        };
        0.2126 * linear(color[0]) + 0.7152 * linear(color[1]) + 0.0722 * linear(color[2])
    }

    fn contrast(a: [u8; 4], b: [u8; 4]) -> f64 {
        let (lo, hi) = {
            let x = luminance(a);
            let y = luminance(b);
            (x.min(y), x.max(y))
        };
        (hi + 0.05) / (lo + 0.05)
    }

    fn composite(color: [u8; 4], opacity: f32, background: [u8; 4]) -> [u8; 4] {
        let alpha = (f32::from(color[3]) / 255.0) * opacity;
        let channel = |index| {
            ((f32::from(color[index]) * alpha) + (f32::from(background[index]) * (1.0 - alpha)))
                .round() as u8
        };
        [channel(0), channel(1), channel(2), 255]
    }

    fn blank_style() -> ResolvedGraphStyle {
        ResolvedGraphStyle {
            fill: [0; 4],
            stroke: [0; 4],
            halo: [0; 4],
            size: 0.0,
            width: 0.0,
            opacity: 0.0,
            shape: 0,
            dash: 0,
            arrow: 0,
            state: 0,
        }
    }

    #[test]
    fn actual_active_styles_meet_non_text_contrast_in_both_themes() {
        let active = [
            0,
            FLAG_AGGREGATE,
            FLAG_PINNED,
            FLAG_NEIGHBOR,
            FLAG_HOVERED,
            FLAG_SELECTED,
        ];
        for (theme, background) in [
            (THEME_LIGHT, [255, 255, 255, 255]),
            (THEME_DARK, [17, 24, 39, 255]),
        ] {
            for edge in [false, true] {
                for code in 0..=MAX_SEMANTIC_CODE {
                    for flags in active {
                        let mut out = [blank_style()];
                        resolve!(
                            &[code],
                            &[code],
                            &[code],
                            &[1.0],
                            &[flags],
                            edge,
                            theme,
                            &mut out,
                        )
                        .unwrap();
                        for color in [out[0].fill, out[0].stroke, out[0].halo] {
                            let painted = composite(color, out[0].opacity, background);
                            assert!(contrast(painted, background) >= 3.0, "theme={theme} edge={edge} code={code} flags={flags} color={color:?}");
                        }
                    }
                }
            }
        }
    }

    #[test]
    fn inactive_states_are_explicit_contrast_exemptions() {
        for (flag, expected) in [(FLAG_FILTERED, 0.08), (FLAG_DISABLED, 0.28)] {
            let mut out = [blank_style()];
            resolve!(
                &[1],
                &[1],
                &[1],
                &[1.0],
                &[flag],
                false,
                THEME_LIGHT,
                &mut out,
            )
            .unwrap();
            assert_eq!(out[0].opacity, expected);
        }
    }

    #[test]
    fn every_winning_active_state_changes_node_and_edge_paint() {
        for edge in [false, true] {
            let mut styles = Vec::new();
            for flag in [
                0,
                FLAG_AGGREGATE,
                FLAG_PINNED,
                FLAG_NEIGHBOR,
                FLAG_HOVERED,
                FLAG_SELECTED,
            ] {
                let mut out = [blank_style()];
                resolve!(
                    &[1],
                    &[1],
                    &[1],
                    &[1.0],
                    &[flag],
                    edge,
                    THEME_LIGHT,
                    &mut out,
                )
                .unwrap();
                styles.push(out[0]);
            }
            for i in 0..styles.len() {
                for j in i + 1..styles.len() {
                    assert_ne!(styles[i], styles[j], "edge={edge} states {i}/{j}");
                }
            }
        }
    }

    #[test]
    fn unknown_interaction_bits_fail_atomically() {
        let sentinel = ResolvedGraphStyle {
            state: 99,
            ..blank_style()
        };
        let mut out = [sentinel];
        assert_eq!(
            resolve!(
                &[1],
                &[1],
                &[1],
                &[1.0],
                &[1 << 7],
                false,
                THEME_LIGHT,
                &mut out
            ),
            None
        );
        assert_eq!(out, [sentinel]);
    }

    #[test]
    fn extreme_finite_metric_domain_emits_only_finite_paint() {
        let blank = ResolvedGraphStyle {
            fill: [0; 4],
            stroke: [0; 4],
            halo: [0; 4],
            size: 0.0,
            width: 0.0,
            opacity: 0.0,
            shape: 0,
            dash: 0,
            arrow: 0,
            state: 0,
        };
        let mut out = [blank; 3];
        resolve!(
            &[1; 3],
            &[1; 3],
            &[1; 3],
            &[-f64::MAX, 0.0, f64::MAX],
            &[0; 3],
            false,
            THEME_DARK,
            &mut out,
        )
        .unwrap();
        assert!(out.iter().all(|style| style.size.is_finite()
            && style.width.is_finite()
            && style.opacity.is_finite()));
        assert_eq!(
            out.iter().map(|style| style.size).collect::<Vec<_>>(),
            vec![7.0, 13.5, 20.0]
        );
    }

    #[test]
    fn compound_transition_is_stable_id_owned_atomic_and_direct_only() {
        let ids = [91, 17, 44, 63];
        let parents = [0, 0, 1, 0];
        let validity = [0, 1, 1, 1];
        let collapsed = [0, 0, 0, 0];
        let mut out = [9; 4];
        assert_eq!(
            compound_collapse_transition(
                &ids,
                &parents,
                &validity,
                &collapsed,
                17,
                COMPOUND_ACTION_COLLAPSE,
                GRAPH_LOD_DIRECT,
                &mut out,
            ),
            Some(true)
        );
        assert_eq!(out, [0, 1, 0, 0]);
        assert_eq!(
            compound_collapse_transition(
                &ids,
                &parents,
                &validity,
                &out,
                17,
                COMPOUND_ACTION_TOGGLE,
                GRAPH_LOD_DIRECT,
                &mut [0; 4],
            ),
            Some(true)
        );

        for (bad_ids, target, action, tier) in [
            (&[91, 17, 17, 63][..], 17, COMPOUND_ACTION_COLLAPSE, 0),
            (&ids[..], 44, COMPOUND_ACTION_COLLAPSE, 0),
            (&ids[..], 999, COMPOUND_ACTION_COLLAPSE, 0),
            (&ids[..], 17, 9, 0),
            (&ids[..], 17, COMPOUND_ACTION_COLLAPSE, 1),
        ] {
            let mut guarded = [7; 4];
            assert_eq!(
                compound_collapse_transition(
                    bad_ids,
                    &parents,
                    &validity,
                    &collapsed,
                    target,
                    action,
                    tier,
                    &mut guarded,
                ),
                None
            );
            assert_eq!(guarded, [7; 4]);
        }
        let mut guarded = [7; 3];
        assert_eq!(
            compound_collapse_transition(
                &[1, 2, 3],
                &[1, 2, 0],
                &[1, 1, 1],
                &[0, 0, 0],
                1,
                COMPOUND_ACTION_COLLAPSE,
                GRAPH_LOD_DIRECT,
                &mut guarded,
            ),
            None
        );
        assert_eq!(guarded, [7; 3]);
        let oversized = vec![0u64; MAX_COMPOUND_TRANSITION_NODES + 1];
        let mut oversized_out = vec![7; oversized.len()];
        assert_eq!(
            compound_collapse_transition(
                &oversized,
                &oversized,
                &vec![0; oversized.len()],
                &vec![0; oversized.len()],
                0,
                COMPOUND_ACTION_COLLAPSE,
                GRAPH_LOD_DIRECT,
                &mut oversized_out,
            ),
            None
        );
        assert!(oversized_out.iter().all(|&value| value == 7));
    }
}
