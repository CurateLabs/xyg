//! Shared geographic presentation catalog (#49, dossier §16/§19/§27/§29).
//! Canonical GeoColumn planes are borrowed; all projected marks are rebuildable.
use crate::geo::{GeoColumn, GeoCrs, GeoError, GeoGeometry};
use crate::geo_viewport::{self, GeoViewport, GeoViewportRebuildKey, ProjectedGeoGeometry};
use crate::scene::{
    self, AxisScale, LegendLocation, PlotLayout, ScaleKind, SceneBatch, SceneChromeStyle,
    SceneChromeText, SceneImage, SceneLabel, SceneLegend, SceneLegendEntry, SceneRecordKind,
};
use std::collections::BTreeMap;

pub const MAX_GEO_LAYERS: usize = 64;
pub const MAX_GEO_ARC_STEPS: u32 = 256;
pub const GEO_STATE_HIDDEN: u8 = 1;
pub const GEO_STATE_SELECTED: u8 = 2;
pub const GEO_STATE_HOVERED: u8 = 4;
pub const GEO_STATE_FOCUSED: u8 = 8;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum GeoLayerKind {
    Points = 1,
    Bubbles = 2,
    Routes = 3,
    Arcs = 4,
    Polygons = 5,
    Choropleth = 6,
    Density = 7,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GeoStyle {
    pub fill: [u8; 4],
    pub stroke: [u8; 4],
    pub stroke_width: f64,
    pub diameter: f64,
    pub opacity: f64,
    pub symbol: u8,
}
impl Default for GeoStyle {
    fn default() -> Self {
        let rgba = crate::kernels::default_mark_rgba8();
        Self {
            fill: rgba,
            stroke: rgba,
            stroke_width: 1.0,
            diameter: 6.0,
            opacity: 1.0,
            symbol: 0,
        }
    }
}
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct GeoStylePatch {
    pub fill: Option<[u8; 4]>,
    pub stroke: Option<[u8; 4]>,
    pub stroke_width: Option<f64>,
    pub diameter: Option<f64>,
    pub opacity: Option<f64>,
    pub symbol: Option<u8>,
}
impl GeoStylePatch {
    fn apply(self, style: &mut GeoStyle) {
        if let Some(v) = self.fill {
            style.fill = v;
        }
        if let Some(v) = self.stroke {
            style.stroke = v;
        }
        if let Some(v) = self.stroke_width {
            style.stroke_width = v;
        }
        if let Some(v) = self.diameter {
            style.diameter = v;
        }
        if let Some(v) = self.opacity {
            style.opacity = v;
        }
        if let Some(v) = self.symbol {
            style.symbol = v;
        }
    }
}
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GeoStateStyles {
    pub selected: GeoStylePatch,
    pub hovered: GeoStylePatch,
    pub focused: GeoStylePatch,
}
impl Default for GeoStateStyles {
    fn default() -> Self {
        Self {
            selected: GeoStylePatch {
                stroke: Some([255, 128, 0, 255]),
                stroke_width: Some(2.0),
                ..GeoStylePatch::default()
            },
            hovered: GeoStylePatch {
                stroke: Some([32, 32, 32, 255]),
                stroke_width: Some(2.0),
                ..GeoStylePatch::default()
            },
            focused: GeoStylePatch {
                stroke: Some([0, 0, 0, 255]),
                stroke_width: Some(3.0),
                ..GeoStylePatch::default()
            },
        }
    }
}
#[derive(Debug, Clone, Copy)]
pub struct GeoArcOptions {
    pub bend: f64,
    pub steps: u32,
}
impl Default for GeoArcOptions {
    fn default() -> Self {
        Self {
            bend: 0.25,
            steps: crate::geom::BEZIER_STEPS as u32,
        }
    }
}
#[derive(Debug, Clone, Copy)]
pub struct GeoDensityOptions {
    pub columns: u32,
    pub rows: u32,
}
impl Default for GeoDensityOptions {
    fn default() -> Self {
        Self {
            columns: 512,
            rows: 384,
        }
    }
}
#[derive(Debug, Clone, Copy)]
pub struct GeoLabel<'a> {
    pub feature_index: u32,
    pub coordinate: [f64; 2],
    pub text: &'a str,
    pub font_size: f64,
    pub rgba: [u8; 4],
    pub anchor: u8,
}
#[derive(Debug, Clone, Copy)]
pub struct GeoLegend<'a> {
    pub title: &'a str,
    pub location: LegendLocation,
    pub font_size: f64,
}

pub struct GeoLayer<'a> {
    pub layer_id: u64,
    pub kind: GeoLayerKind,
    pub source: &'a GeoColumn,
    pub style: GeoStyle,
    pub feature_styles: &'a [GeoStylePatch],
    pub values: &'a [f64],
    pub value_domain: Option<[f64; 2]>,
    pub color_stops: &'a [[u8; 3]],
    pub bubble_diameters: [f64; 2],
    pub state_flags: &'a [u8],
    pub state_styles: GeoStateStyles,
    pub arc: GeoArcOptions,
    pub density: GeoDensityOptions,
    pub labels: &'a [GeoLabel<'a>],
    pub legend_label: Option<&'a str>,
}
impl<'a> GeoLayer<'a> {
    pub fn new(layer_id: u64, kind: GeoLayerKind, source: &'a GeoColumn) -> Self {
        Self {
            layer_id,
            kind,
            source,
            style: GeoStyle::default(),
            feature_styles: &[],
            values: &[],
            value_domain: None,
            color_stops: &[],
            bubble_diameters: [2.0, 24.0],
            state_flags: &[],
            state_styles: GeoStateStyles::default(),
            arc: GeoArcOptions::default(),
            density: GeoDensityOptions::default(),
            labels: &[],
            legend_label: None,
        }
    }
}
pub struct GeoCatalog<'a> {
    pub viewport: GeoViewport,
    pub layers: &'a [GeoLayer<'a>],
    pub legend: Option<GeoLegend<'a>>,
    pub budget: usize,
}

/// Source-row membership rather than a fabricated representative feature.
/// Bins are CSS top-row-first; members are sorted source rows, deduplicated per bin.
#[derive(Debug, PartialEq)]
pub struct GeoDensityMembership {
    pub columns: u32,
    pub rows: u32,
    pub counts: Vec<u32>,
    pub offsets: Vec<u32>,
    pub feature_indices: Vec<u32>,
}
#[derive(Debug)]
pub struct GeoCompiledLayer {
    pub layer_id: u64,
    pub kind: GeoLayerKind,
    pub source_digest: [u8; 8],
    pub feature_ids: Vec<u64>,
    pub validity: Vec<u8>,
    pub state_flags: Vec<u8>,
    pub visible_feature_indices: Vec<u32>,
    pub visible_bounds: Option<[f64; 4]>,
    pub density: Option<GeoDensityMembership>,
    /// Density aggregates diameter, symbol and stroke channels away; exact state overlays retain them.
    pub dropped_channels: u32,
}
#[derive(Debug)]
pub struct GeoCompiled {
    pub scene: Vec<u8>,
    pub camera: GeoViewportRebuildKey,
    pub layers: Vec<GeoCompiledLayer>,
    /// Index into layers per Scene style. None is the transparent run separator.
    /// A direct pick resolves (layer_id, literal Scene feature_id).
    pub style_owners: Vec<Option<u32>>,
}

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
struct PaintKey {
    fill: [u8; 4],
    stroke: [u8; 4],
    width: u64,
}
#[derive(Default)]
struct Marks {
    kinds: Vec<u8>,
    ids: Vec<u64>,
    refs: Vec<u32>,
    diameter: Vec<f64>,
    symbols: Vec<u8>,
    x0: Vec<f64>,
    y0: Vec<f64>,
    x1: Vec<f64>,
    y1: Vec<f64>,
}
struct Builder {
    marks: Marks,
    fill: Vec<u8>,
    stroke: Vec<u8>,
    width: Vec<f64>,
    owners: Vec<Option<u32>>,
    labels: Vec<SceneLabel>,
    images: Vec<SceneImage>,
    legend_entries: Vec<SceneLegendEntry>,
    base_peak: usize,
    budget: usize,
}
impl Builder {
    fn admit(&self, records: usize, styles: usize) -> Result<(), GeoError> {
        let peak = records
            .checked_mul(1024)
            .and_then(|n| styles.checked_mul(128).and_then(|s| n.checked_add(s)))
            .and_then(|n| n.checked_add(self.base_peak))
            .ok_or(GeoError::ResourceLimit)?;
        if records > scene::MAX_SCENE_MARKS
            || styles > scene::MAX_SCENE_STYLES
            || peak > self.budget
        {
            return Err(GeoError::ResourceLimit);
        }
        Ok(())
    }
    fn paint(
        &mut self,
        owner: u32,
        style: GeoStyle,
        intern: &mut BTreeMap<PaintKey, u32>,
    ) -> Result<u32, GeoError> {
        let fill = crate::css::apply_opacity_rgba8(style.fill, style.opacity as f32);
        let stroke = crate::css::apply_opacity_rgba8(style.stroke, style.opacity as f32);
        let key = PaintKey {
            fill,
            stroke,
            width: style.stroke_width.to_bits(),
        };
        if let Some(&id) = intern.get(&key) {
            return Ok(id);
        }
        self.admit(self.marks.kinds.len(), self.width.len() + 1)?;
        let id = self.width.len() as u32;
        self.fill.extend(fill);
        self.stroke.extend(stroke);
        self.width.push(style.stroke_width);
        self.owners.push(Some(owner));
        intern.insert(key, id);
        Ok(id)
    }
    fn mark(
        &mut self,
        kind: SceneRecordKind,
        id: u64,
        style: u32,
        coordinate: [f64; 4],
        diameter: f64,
        symbol: u8,
    ) -> Result<(), GeoError> {
        self.admit(self.marks.kinds.len() + 1, self.width.len())?;
        if coordinate
            .iter()
            .any(|v| !v.is_finite() || !(*v as f32).is_finite())
        {
            return Err(GeoError::InvalidArgument);
        }
        let m = &mut self.marks;
        m.kinds.push(kind as u8);
        m.ids.push(id);
        m.refs.push(style);
        m.diameter.push(diameter);
        m.symbols.push(symbol);
        m.x0.push(coordinate[0]);
        m.y0.push(coordinate[1]);
        m.x1.push(coordinate[2]);
        m.y1.push(coordinate[3]);
        Ok(())
    }
    fn separator(&mut self, id: u64) -> Result<(), GeoError> {
        self.mark(SceneRecordKind::Scatter, id, 0, [-1., -1., 0., 0.], 0., 0)
    }
    fn segment(&mut self, id: u64, style: u32, a: [f64; 2], b: [f64; 2]) -> Result<(), GeoError> {
        self.mark(
            SceneRecordKind::Segment,
            id,
            style,
            [a[0], a[1], 0., 0.],
            0.,
            0,
        )?;
        self.mark(
            SceneRecordKind::Segment,
            id,
            style,
            [b[0], b[1], 0., 0.],
            0.,
            0,
        )?;
        Ok(())
    }
    fn triangle(&mut self, id: u64, style: u32, t: [f64; 6]) -> Result<(), GeoError> {
        for p in t.chunks_exact(2) {
            self.mark(
                SceneRecordKind::Triangle,
                id,
                style,
                [p[0], p[1], 0., 0.],
                0.,
                0,
            )?;
        }
        Ok(())
    }
}
fn scene_error(error: scene::SceneError) -> GeoError {
    if matches!(
        error,
        scene::SceneError::Limit | scene::SceneError::PainterTraceLimit
    ) {
        GeoError::ResourceLimit
    } else {
        GeoError::InvalidArgument
    }
}

fn point_kind(kind: GeoGeometry) -> bool {
    matches!(kind, GeoGeometry::Point | GeoGeometry::MultiPoint)
}
fn polygon_kind(kind: GeoGeometry) -> bool {
    matches!(kind, GeoGeometry::Polygon | GeoGeometry::MultiPolygon)
}
fn validate_style(style: GeoStyle) -> Result<(), GeoError> {
    if [style.stroke_width, style.diameter, style.opacity]
        .iter()
        .any(|v| !v.is_finite())
    {
        return Err(GeoError::NonFiniteCoordinate);
    }
    if style.stroke_width < 0.
        || style.diameter < 0.
        || !(style.stroke_width as f32).is_finite()
        || !(style.diameter as f32).is_finite()
        || !(0.0..=1.0).contains(&style.opacity)
        || style.symbol > scene::ScatterSymbol::VerticalLine as u8
    {
        return Err(GeoError::InvalidArgument);
    }
    Ok(())
}
fn resolve_style(
    layer: &GeoLayer<'_>,
    index: usize,
    stops: &[[u8; 3]],
) -> Result<GeoStyle, GeoError> {
    let mut style = layer.style;
    if matches!(layer.kind, GeoLayerKind::Bubbles | GeoLayerKind::Choropleth) {
        let domain = layer.value_domain.ok_or(GeoError::InvalidArgument)?;
        let t = ((layer.values[index] - domain[0]) / (domain[1] - domain[0])).clamp(0., 1.);
        if layer.kind == GeoLayerKind::Bubbles {
            let [lo, hi] = layer.bubble_diameters;
            style.diameter = (lo * lo + t * (hi * hi - lo * lo)).sqrt();
        } else {
            style.fill = crate::kernels::colormap_color(t, stops, style.fill[3]);
        }
    }
    if let Some(patch) = layer.feature_styles.get(index) {
        patch.apply(&mut style);
    }
    let flags = layer.state_flags.get(index).copied().unwrap_or(0);
    for (flag, patch) in [
        (GEO_STATE_SELECTED, layer.state_styles.selected),
        (GEO_STATE_HOVERED, layer.state_styles.hovered),
        (GEO_STATE_FOCUSED, layer.state_styles.focused),
    ] {
        if flags & flag != 0 {
            patch.apply(&mut style);
        }
    }
    validate_style(style)?;
    Ok(style)
}
fn hidden(layer: &GeoLayer<'_>, index: usize) -> bool {
    layer
        .state_flags
        .get(index)
        .is_some_and(|f| f & GEO_STATE_HIDDEN != 0)
}
fn checked_add(a: usize, b: usize) -> Result<usize, GeoError> {
    a.checked_add(b).ok_or(GeoError::ResourceLimit)
}
fn checked_mul(a: usize, b: usize) -> Result<usize, GeoError> {
    a.checked_mul(b).ok_or(GeoError::ResourceLimit)
}
fn source_bytes(source: &GeoColumn) -> Result<usize, GeoError> {
    let numeric = checked_mul(source.xy().len(), 8)?;
    let offsets = checked_mul(
        source.offsets0().len() + source.offsets1().len() + source.offsets2().len(),
        4,
    )?;
    checked_add(
        checked_add(numeric, offsets)?,
        checked_mul(source.len(), 10)?,
    )
}
/// Admit every scalar/style/state/text plane before any variable compile allocation.
fn admission(input: &GeoCatalog<'_>) -> Result<usize, GeoError> {
    input.viewport.validate()?;
    if input.layers.len() > MAX_GEO_LAYERS || input.budget > 384 * 1024 * 1024 {
        return Err(GeoError::ResourceLimit);
    }
    let mut base = 32768usize;
    let mut working = 0usize;
    let mut text = 0usize;
    let mut legend_text = 0usize;
    let mut labels = 0usize;
    for (i, layer) in input.layers.iter().enumerate() {
        if input.layers[..i]
            .iter()
            .any(|p| p.layer_id == layer.layer_id)
        {
            return Err(GeoError::InvalidArgument);
        }
        if layer.source.crs() != input.viewport.crs {
            return Err(GeoError::InvalidArgument);
        }
        let geometry = layer.source.geometry();
        let supported = match layer.kind {
            GeoLayerKind::Points | GeoLayerKind::Bubbles | GeoLayerKind::Density => {
                point_kind(geometry)
            }
            GeoLayerKind::Routes | GeoLayerKind::Arcs => matches!(
                geometry,
                GeoGeometry::LineString | GeoGeometry::MultiLineString
            ),
            GeoLayerKind::Polygons | GeoLayerKind::Choropleth => polygon_kind(geometry),
        };
        if !supported {
            return Err(GeoError::InvalidArgument);
        }
        let n = layer.source.len();
        if [
            layer.feature_styles.len(),
            layer.values.len(),
            layer.state_flags.len(),
        ]
        .iter()
        .any(|&len| len != 0 && len != n)
            || layer.state_flags.iter().any(|flags| flags & !15 != 0)
            || layer.color_stops.len() > 256
        {
            return Err(GeoError::InvalidArgument);
        }
        validate_style(layer.style)?;
        for patch in [
            layer.state_styles.selected,
            layer.state_styles.hovered,
            layer.state_styles.focused,
        ]
        .into_iter()
        .chain(layer.feature_styles.iter().copied())
        {
            let mut style = layer.style;
            patch.apply(&mut style);
            validate_style(style)?;
        }
        if matches!(layer.kind, GeoLayerKind::Bubbles | GeoLayerKind::Choropleth) {
            let domain = layer.value_domain.ok_or(GeoError::InvalidArgument)?;
            if layer.values.len() != n
                || !domain.iter().all(|v| v.is_finite())
                || domain[1] <= domain[0]
                || !(domain[1] - domain[0]).is_finite()
            {
                return Err(GeoError::InvalidArgument);
            }
            if layer
                .source
                .validity()
                .iter()
                .zip(layer.values)
                .any(|(&valid, value)| valid != 0 && !value.is_finite())
            {
                return Err(GeoError::NonFiniteCoordinate);
            }
            if layer
                .bubble_diameters
                .iter()
                .any(|v| !v.is_finite() || *v < 0. || !(*v as f32).is_finite())
                || layer.bubble_diameters[1] < layer.bubble_diameters[0]
            {
                return Err(GeoError::InvalidArgument);
            }
        }
        if layer.kind == GeoLayerKind::Arcs
            && (!layer.arc.bend.is_finite()
                || layer.arc.bend.abs() > 1.
                || !(1..=MAX_GEO_ARC_STEPS).contains(&layer.arc.steps))
        {
            return Err(GeoError::InvalidArgument);
        }
        let vertices = layer.source.vertex_count();
        let scratch = if polygon_kind(geometry) {
            // Same projected topology bound as GeoViewport, plus bounded fill
            // triangles and a temporary single-feature canonical slice.
            let edges = checked_mul(vertices, 16)?.min(crate::geo_fill::MAX_FILL_EDGES);
            checked_add(
                checked_mul(vertices, 4096)?,
                checked_mul(
                    checked_mul(edges, edges)?.min(crate::geo_fill::MAX_FILL_TRIANGLES),
                    128,
                )?,
            )?
        } else if layer.kind == GeoLayerKind::Arcs {
            checked_mul(checked_mul(vertices, layer.arc.steps as usize + 1)?, 256)?
        } else {
            checked_mul(vertices, 256)?
        };
        working = working.max(scratch);
        base = checked_add(base, source_bytes(layer.source)?)?;
        base = checked_add(base, checked_mul(n, 64)?)?;
        if layer.kind == GeoLayerKind::Density {
            let cells = checked_mul(layer.density.columns as usize, layer.density.rows as usize)?;
            if cells == 0
                || layer.density.columns > 4096
                || layer.density.rows > 4096
                || cells > scene::MAX_SCENE_IMAGE_PIXELS
            {
                return Err(GeoError::ResourceLimit);
            }
            // Retained RGBA and CSR/count arrays, histogram scratch, f64
            // projected points and sorted (bin,source-row) memberships.
            base = checked_add(base, checked_mul(cells, 128)?)?;
            base = checked_add(base, checked_mul(vertices, 64)?)?;
        }
        labels = checked_add(labels, layer.labels.len())?;
        for label in layer.labels {
            if label.feature_index as usize >= n
                || label.text.contains('\0')
                || !label.font_size.is_finite()
                || !(1.0..=scene::MAX_SCENE_CHROME_LENGTH).contains(&label.font_size)
                || !label.font_size.is_normal()
                || label.anchor > 2
            {
                return Err(GeoError::InvalidArgument);
            }
            input
                .viewport
                .project(label.coordinate[0], label.coordinate[1])?;
            text = checked_add(text, label.text.len())?;
        }
        if let Some(label) = layer.legend_label {
            if label.contains('\0') || label.is_empty() || label.len() > scene::MAX_SCENE_TEXT_BYTES
            {
                return Err(GeoError::InvalidArgument);
            }
            legend_text = checked_add(legend_text, label.len())?;
        }
    }
    if labels > scene::MAX_SCENE_LABELS || text > scene::MAX_SCENE_LABEL_TEXT_BYTES {
        return Err(GeoError::ResourceLimit);
    }
    if let Some(legend) = input.legend {
        if legend.title.contains('\0')
            || legend.title.len() > scene::MAX_SCENE_TEXT_BYTES
            || !legend.font_size.is_finite()
            || !(1.0..=scene::MAX_SCENE_CHROME_LENGTH).contains(&legend.font_size)
        {
            return Err(GeoError::InvalidArgument);
        }
        legend_text = checked_add(legend_text, legend.title.len())?;
    }
    if legend_text > scene::MAX_SCENE_LEGEND_TEXT_BYTES {
        return Err(GeoError::ResourceLimit);
    }
    base = checked_add(base, checked_mul(checked_add(text, legend_text)?, 4)?)?;
    base = checked_add(base, working)?;
    if base > input.budget {
        return Err(GeoError::ResourceLimit);
    }
    Ok(base)
}
fn include(bounds: &mut Option<[f64; 4]>, point: [f64; 2]) {
    let b = bounds.get_or_insert([point[0], point[1], point[0], point[1]]);
    b[0] = b[0].min(point[0]);
    b[1] = b[1].min(point[1]);
    b[2] = b[2].max(point[0]);
    b[3] = b[3].max(point[1]);
}
fn inside(vp: GeoViewport, point: [f64; 2]) -> bool {
    (0.0..=vp.width).contains(&point[0]) && (0.0..=vp.height).contains(&point[1])
}
fn feature_points(source: &GeoColumn, index: usize, point_cursor: &mut usize) -> (usize, usize) {
    if source.geometry() == GeoGeometry::Point {
        let start = *point_cursor;
        if source.validity()[index] != 0 {
            *point_cursor += 1;
        }
        (start, *point_cursor)
    } else {
        (
            source.offsets0()[index] as usize,
            source.offsets0()[index + 1] as usize,
        )
    }
}
fn line_parts(source: &GeoColumn, index: usize) -> (usize, usize, &[u32]) {
    if source.geometry() == GeoGeometry::LineString {
        (index, index + 1, source.offsets0())
    } else {
        (
            source.offsets0()[index] as usize,
            source.offsets0()[index + 1] as usize,
            source.offsets1(),
        )
    }
}
fn single_polygon(source: &GeoColumn, index: usize) -> Result<GeoColumn, GeoError> {
    let p0 = source.offsets0()[index] as usize;
    let p1 = source.offsets0()[index + 1] as usize;
    let (ring_first, ring_last, vertex_offsets) = if source.geometry() == GeoGeometry::Polygon {
        (p0, p1, source.offsets1())
    } else {
        (
            source.offsets1()[p0] as usize,
            source.offsets1()[p1] as usize,
            source.offsets2(),
        )
    };
    let first = vertex_offsets[ring_first];
    let last = vertex_offsets[ring_last];
    let o0 = [0, (p1 - p0) as u32];
    let o1: Vec<u32> = if source.geometry() == GeoGeometry::Polygon {
        vertex_offsets[ring_first..=ring_last]
            .iter()
            .map(|v| v - first)
            .collect()
    } else {
        source.offsets1()[p0..=p1]
            .iter()
            .map(|v| v - ring_first as u32)
            .collect()
    };
    let o2: Vec<u32> = if source.geometry() == GeoGeometry::MultiPolygon {
        vertex_offsets[ring_first..=ring_last]
            .iter()
            .map(|v| v - first)
            .collect()
    } else {
        Vec::new()
    };
    GeoColumn::from_descriptor(crate::geo::GeoDescriptor {
        geometry: source.geometry(),
        crs: source.crs(),
        xy: &source.xy()[first as usize * 2..last as usize * 2],
        validity: &[1],
        feature_ids: Some(&[source.feature_ids()[index]]),
        offsets0: &o0,
        offsets1: &o1,
        offsets2: &o2,
        limits: crate::geo::GeoLimits::default(),
    })
}

/// Compile the entire source-ordered catalog atomically to the ordinary Scene.
pub fn compile(input: &GeoCatalog<'_>) -> Result<GeoCompiled, GeoError> {
    let base_peak = admission(input)?;
    let vp = input.viewport;
    let mut builder = Builder {
        marks: Marks::default(),
        fill: vec![0; 4],
        stroke: vec![0; 4],
        width: vec![0.],
        owners: vec![None],
        labels: Vec::new(),
        images: Vec::new(),
        legend_entries: Vec::new(),
        base_peak,
        budget: input.budget,
    };
    let mut layers = Vec::with_capacity(input.layers.len());
    for (layer_index, layer) in input.layers.iter().enumerate() {
        let mut metadata = GeoCompiledLayer {
            layer_id: layer.layer_id,
            kind: layer.kind,
            source_digest: layer.source.metadata_digest(),
            feature_ids: layer.source.feature_ids().to_vec(),
            validity: layer.source.validity().to_vec(),
            state_flags: if layer.state_flags.is_empty() {
                vec![0; layer.source.len()]
            } else {
                layer.state_flags.to_vec()
            },
            visible_feature_indices: Vec::new(),
            visible_bounds: None,
            density: None,
            dropped_channels: if layer.kind == GeoLayerKind::Density {
                7
            } else {
                0
            },
        };
        let defaults = if layer.color_stops.is_empty() {
            crate::colormap::colormap_named_stops("viridis")
        } else {
            Vec::new()
        };
        let stops = if layer.color_stops.is_empty() {
            defaults.as_slice()
        } else {
            layer.color_stops
        };
        let mut intern = BTreeMap::new();
        let mut legend_style = None;
        if layer.kind == GeoLayerKind::Density {
            compile_density(
                &mut builder,
                layer,
                layer_index as u32,
                vp,
                stops,
                &mut intern,
                &mut metadata,
            )?;
            legend_style = intern.values().next().copied();
        } else {
            let mut point_cursor = 0;
            for index in 0..layer.source.len() {
                let point_range = if point_kind(layer.source.geometry()) {
                    feature_points(layer.source, index, &mut point_cursor)
                } else {
                    (0, 0)
                };
                if layer.source.validity()[index] == 0 || hidden(layer, index) {
                    continue;
                }
                let style = resolve_style(layer, index, stops)?;
                let style_ref = builder.paint(layer_index as u32, style, &mut intern)?;
                legend_style = legend_style.or(Some(style_ref));
                let mut bounds = None;
                match layer.kind {
                    GeoLayerKind::Points | GeoLayerKind::Bubbles => {
                        for vertex in point_range.0..point_range.1 {
                            let xy = &layer.source.xy()[vertex * 2..vertex * 2 + 2];
                            let (x, y) = vp.project(xy[0], xy[1])?;
                            if inside(vp, [x, y])
                                && style.diameter > 0.
                                && style.opacity > 0.
                                && (style.fill[3] > 0 || style.stroke[3] > 0)
                            {
                                builder.mark(
                                    SceneRecordKind::Scatter,
                                    layer.source.feature_ids()[index],
                                    style_ref,
                                    [x, y, 0., 0.],
                                    style.diameter,
                                    style.symbol,
                                )?;
                                include(&mut bounds, [x, y]);
                            }
                        }
                    }
                    GeoLayerKind::Routes | GeoLayerKind::Arcs => {
                        if style.stroke_width > 0. && style.stroke[3] > 0 && style.opacity > 0. {
                            compile_route(&mut builder, layer, index, style_ref, vp, &mut bounds)?;
                        }
                    }
                    GeoLayerKind::Polygons | GeoLayerKind::Choropleth => compile_polygon(
                        &mut builder,
                        layer,
                        index,
                        style_ref,
                        vp,
                        &mut intern,
                        &mut bounds,
                    )?,
                    GeoLayerKind::Density => unreachable!(),
                }
                if let Some(b) = bounds {
                    metadata.visible_feature_indices.push(index as u32);
                    include(&mut metadata.visible_bounds, [b[0], b[1]]);
                    include(&mut metadata.visible_bounds, [b[2], b[3]]);
                }
            }
        }
        for label in layer.labels {
            let index = label.feature_index as usize;
            if layer.source.validity()[index] == 0
                || hidden(layer, index)
                || !metadata
                    .visible_feature_indices
                    .binary_search(&label.feature_index)
                    .is_ok()
            {
                continue;
            }
            let (x, y) = vp.project(label.coordinate[0], label.coordinate[1])?;
            if inside(vp, [x, y]) {
                builder.labels.push(SceneLabel {
                    stable_id: layer.source.feature_ids()[index],
                    x,
                    y,
                    font_size: label.font_size,
                    rgba: label.rgba,
                    anchor: label.anchor,
                    rotation: 0.,
                    text: label.text.to_owned(),
                });
            }
        }
        if let (Some(label), Some(style_ref)) = (layer.legend_label, legend_style) {
            let style = style_ref as usize;
            builder.legend_entries.push(SceneLegendEntry {
                style_ref: style,
                kind: match layer.kind {
                    GeoLayerKind::Routes | GeoLayerKind::Arcs => SceneRecordKind::Polyline,
                    GeoLayerKind::Polygons | GeoLayerKind::Choropleth => SceneRecordKind::Triangle,
                    _ => SceneRecordKind::Scatter,
                },
                symbol: layer.style.symbol,
                fill_rgba: builder.fill[style * 4..style * 4 + 4].try_into().unwrap(),
                stroke_rgba: builder.stroke[style * 4..style * 4 + 4].try_into().unwrap(),
                label: label.to_owned(),
            });
        }
        layers.push(metadata);
        builder.separator(layer.layer_id)?;
    }
    let layout = PlotLayout::new(vp.width, vp.height, 0., 0., 0., 0.).map_err(scene_error)?;
    let x = AxisScale::new(ScaleKind::Linear, 0., vp.width, 0., vp.width, 1., false)
        .map_err(scene_error)?;
    let y = AxisScale::new(ScaleKind::Linear, 0., vp.height, 0., vp.height, 1., false)
        .map_err(scene_error)?;
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
    let legend = input
        .legend
        .filter(|_| !builder.legend_entries.is_empty())
        .map(|config| SceneLegend {
            location: config.location,
            title: config.title.to_owned(),
            font_size: config.font_size,
            title_font_size: config.font_size,
            text_rgba: scene::LEGEND_DEFAULT_TEXT_RGBA,
            frame_fill_rgba: scene::LEGEND_DEFAULT_FRAME_FILL_RGBA,
            frame_stroke_rgba: scene::LEGEND_DEFAULT_FRAME_STROKE_RGBA,
            entries: builder.legend_entries,
        });
    let m = &builder.marks;
    let bytes = SceneBatch::new_with_chrome_literal_ids_and_decorations(
        layout,
        1,
        2,
        x,
        y,
        chrome,
        SceneChromeText::default(),
        legend,
        builder.labels,
        &m.kinds,
        &m.ids,
        &m.refs,
        &builder.fill,
        &builder.stroke,
        &builder.width,
        &m.diameter,
        &m.symbols,
        &m.x0,
        &m.y0,
        &m.x1,
        &m.y1,
    )
    .map_err(scene_error)?
    .with_images(builder.images)
    .map_err(scene_error)?
    .encode();
    if bytes.len() > input.budget {
        return Err(GeoError::ResourceLimit);
    }
    // Shared paint admission is identical for native and browser hosts.
    // The conservative per-record reserve includes decoded and derived buffers.
    scene::SceneDocument::decode(&bytes)
        .map_err(scene_error)?
        .to_browser_painter(input.budget)
        .map_err(scene_error)?;
    Ok(GeoCompiled {
        scene: bytes,
        camera: vp.rebuild_key()?,
        layers,
        style_owners: builder.owners,
    })
}

fn compile_route(
    builder: &mut Builder,
    layer: &GeoLayer<'_>,
    index: usize,
    style_ref: u32,
    vp: GeoViewport,
    bounds: &mut Option<[f64; 4]>,
) -> Result<(), GeoError> {
    let id = layer.source.feature_ids()[index];
    let (first, last, offsets) = line_parts(layer.source, index);
    for part in first..last {
        let xy = &layer.source.xy()[offsets[part] as usize * 2..offsets[part + 1] as usize * 2];
        if xy.len() < 4 {
            continue;
        }
        let sampled = if layer.kind == GeoLayerKind::Arcs {
            Some(arc_coordinates(xy, vp, layer.arc)?)
        } else {
            None
        };
        let xy = sampled.as_deref().unwrap_or(xy);
        let projected = vp.project_line_features(xy, &[0, (xy.len() / 2) as u32], &[id])?;
        for pair in projected.xy.chunks_exact(4) {
            let a = [
                projected.origin_x + pair[0] as f64,
                projected.origin_y + pair[1] as f64,
            ];
            let b = [
                projected.origin_x + pair[2] as f64,
                projected.origin_y + pair[3] as f64,
            ];
            builder.segment(id, style_ref, a, b)?;
            include(bounds, a);
            include(bounds, b);
        }
    }
    Ok(())
}
fn arc_coordinates(
    xy: &[f64],
    vp: GeoViewport,
    options: GeoArcOptions,
) -> Result<Vec<f64>, GeoError> {
    let count = (xy.len() / 2 - 1)
        .checked_mul(options.steps as usize)
        .and_then(|n| n.checked_add(1))
        .ok_or(GeoError::ResourceLimit)?;
    if count > crate::geo::GeoLimits::default().max_vertices {
        return Err(GeoError::ResourceLimit);
    }
    let mut out = Vec::with_capacity(count * 2);
    let mercator = |x, y| {
        if vp.crs == GeoCrs::Epsg4326 {
            geo_viewport::lonlat_to_mercator(x, y)
        } else {
            (x, y)
        }
    };
    for (span, p) in xy.windows(4).step_by(2).enumerate() {
        let (x0, y0) = mercator(p[0], p[1]);
        let (x1, y1) = mercator(p[2], p[3]);
        let world = 2.0 * geo_viewport::WEB_MERCATOR_MAX;
        let mut dx = x1 - x0;
        if vp.world_wrap && dx.abs() < world {
            dx -= world * (dx / world).round();
        }
        let dy = y1 - y0;
        let nx = -dy * options.bend;
        let ny = dx * options.bend;
        for step in if span == 0 { 0 } else { 1 }..=options.steps {
            let t = step as f64 / options.steps as f64;
            let mx = x0 + crate::geom::cubic_bezier(t, 0., dx / 3. + nx, dx * 2. / 3. + nx, dx);
            let my = y0 + crate::geom::cubic_bezier(t, 0., dy / 3. + ny, dy * 2. / 3. + ny, dy);
            let half = geo_viewport::WEB_MERCATOR_MAX;
            let mx = if vp.world_wrap {
                (mx + half).rem_euclid(world) - half
            } else {
                mx.clamp(-half, half)
            };
            let my = my.clamp(-half, half);
            let (x, y) = if vp.crs == GeoCrs::Epsg4326 {
                geo_viewport::mercator_to_lonlat(mx, my)
            } else {
                (mx, my)
            };
            out.extend([x, y]);
        }
    }
    Ok(out)
}
fn compile_polygon(
    builder: &mut Builder,
    layer: &GeoLayer<'_>,
    index: usize,
    style_ref: u32,
    vp: GeoViewport,
    intern: &mut BTreeMap<PaintKey, u32>,
    bounds: &mut Option<[f64; 4]>,
) -> Result<(), GeoError> {
    let source = single_polygon(layer.source, index)?;
    let projected = vp.project_column(&source)?;
    let id = layer.source.feature_ids()[index];
    let Some(poly) = projected.polygons else {
        return Ok(());
    };
    let style = style_ref as usize;
    if builder.fill[style * 4 + 3] > 0 {
        // Opacity is already resolved in the style table. Fill primitives
        // carry no stroke; only canonical source edges receive outline paint.
        let fill: [u8; 4] = builder.fill[style * 4..style * 4 + 4].try_into().unwrap();
        let fill_ref = builder.paint(
            builder.owners[style].unwrap(),
            GeoStyle {
                fill,
                stroke: [0; 4],
                stroke_width: 0.,
                diameter: 0.,
                opacity: 1.,
                symbol: 0,
            },
            intern,
        )?;
        for polygon in poly.polygon_offsets.windows(2) {
            let mut rings = Vec::new();
            for ring in polygon[0] as usize..polygon[1] as usize {
                let mut xy = Vec::with_capacity(
                    (poly.ring_offsets[ring + 1] - poly.ring_offsets[ring]) as usize * 2,
                );
                for vertex in poly.ring_offsets[ring] as usize..poly.ring_offsets[ring + 1] as usize
                {
                    xy.extend([
                        poly.origin_x + poly.xy[2 * vertex] as f64,
                        poly.origin_y + poly.xy[2 * vertex + 1] as f64,
                    ]);
                }
                rings.push((xy, poly.ring_is_hole[ring] != 0));
            }
            let borrowed: Vec<_> = rings
                .iter()
                .map(|(xy, hole)| (xy.as_slice(), *hole))
                .collect();
            let triangles = crate::geo_fill::tessellate(&borrowed)?;
            for triangle in triangles {
                builder.triangle(id, fill_ref, triangle)?;
                for p in triangle.chunks_exact(2) {
                    include(bounds, [p[0], p[1]]);
                }
            }
        }
    }
    // Preserve separate source-over groups even when adjacent rows repeat IDs.
    builder.separator(id)?;
    if builder.width[style] > 0. && builder.stroke[style * 4 + 3] > 0 {
        if let ProjectedGeoGeometry::Outlines(lines) = projected.geometry {
            for pair in lines.xy.chunks_exact(4) {
                let a = [
                    lines.origin_x + pair[0] as f64,
                    lines.origin_y + pair[1] as f64,
                ];
                let b = [
                    lines.origin_x + pair[2] as f64,
                    lines.origin_y + pair[3] as f64,
                ];
                builder.segment(id, style_ref, a, b)?;
                include(bounds, a);
                include(bounds, b);
            }
        }
    }
    Ok(())
}
fn compile_density(
    builder: &mut Builder,
    layer: &GeoLayer<'_>,
    owner: u32,
    vp: GeoViewport,
    stops: &[[u8; 3]],
    intern: &mut BTreeMap<PaintKey, u32>,
    metadata: &mut GeoCompiledLayer,
) -> Result<(), GeoError> {
    let columns = layer.density.columns as usize;
    let rows = layer.density.rows as usize;
    let cells = columns * rows;
    let mut xs = Vec::new();
    let mut ys = Vec::new();
    let mut feature_rows = Vec::new();
    let mut colors = Vec::new();
    let mut point_cursor = 0;
    let mut mean_colors = false;
    for index in 0..layer.source.len() {
        let (first, last) = feature_points(layer.source, index, &mut point_cursor);
        if layer.source.validity()[index] == 0 || hidden(layer, index) {
            continue;
        }
        let style = resolve_style(layer, index, stops)?;
        let flags = layer.state_flags.get(index).copied().unwrap_or(0);
        mean_colors |= layer
            .feature_styles
            .get(index)
            .is_some_and(|s| s.fill.is_some() || s.opacity.is_some())
            || [
                (GEO_STATE_SELECTED, layer.state_styles.selected),
                (GEO_STATE_HOVERED, layer.state_styles.hovered),
                (GEO_STATE_FOCUSED, layer.state_styles.focused),
            ]
            .iter()
            .any(|(flag, patch)| {
                flags & flag != 0 && (patch.fill.is_some() || patch.opacity.is_some())
            });
        for vertex in first..last {
            let p = &layer.source.xy()[vertex * 2..vertex * 2 + 2];
            let (x, y) = vp.project(p[0], p[1])?;
            // Shared count kernels use half-open top/right. Source-row CSR
            // uses the identical rule, so no representative is fabricated.
            if x < 0. || x >= vp.width || y < 0. || y >= vp.height {
                continue;
            }
            xs.push(x);
            ys.push(y);
            feature_rows.push(index as u32);
            colors.extend(crate::css::apply_opacity_rgba8(
                style.fill,
                style.opacity as f32,
            ));
        }
    }
    let mut counts = vec![0u32; cells];
    crate::kernels::bin_2d_count_scalar(
        &xs,
        &ys,
        0.,
        vp.width,
        0.,
        vp.height,
        columns,
        rows,
        &mut counts,
    );
    let mut members: Vec<(usize, u32)> = xs
        .iter()
        .zip(&ys)
        .zip(&feature_rows)
        .map(|((&x, &y), &row)| {
            let cx = ((x * (columns as f64 / vp.width)) as usize).min(columns - 1);
            let cy = ((y * (rows as f64 / vp.height)) as usize).min(rows - 1);
            (cy * columns + cx, row)
        })
        .collect();
    members.sort_unstable();
    members.dedup();
    let mut offsets = vec![0u32; cells + 1];
    let mut indices = Vec::with_capacity(members.len());
    for &(cell, row) in &members {
        offsets[cell + 1] += 1;
        indices.push(row);
    }
    for i in 1..offsets.len() {
        offsets[i] += offsets[i - 1];
    }
    let mut visible = feature_rows.clone();
    visible.sort_unstable();
    visible.dedup();
    metadata.visible_feature_indices = visible;
    for (&x, &y) in xs.iter().zip(&ys) {
        include(&mut metadata.visible_bounds, [x, y]);
    }
    let raw: Vec<f64> = counts.iter().map(|&n| n as f64).collect();
    let maximum = raw.iter().copied().fold(0., f64::max);
    let mut rgba = vec![0; cells * 4];
    if !crate::kernels::density_rgba_linear_into(
        &raw,
        columns,
        rows,
        maximum,
        stops,
        if mean_colors { 1. } else { layer.style.opacity },
        &mut rgba,
    ) {
        return Err(GeoError::InvalidArgument);
    }
    if mean_colors {
        let mut mean = vec![crate::kernels::MeanColorCell::default(); cells];
        crate::kernels::bin_2d_mean_color_accumulate(
            &xs,
            &ys,
            &crate::kernels::BinColorSource::Rgba(&colors),
            0,
            0.,
            vp.width,
            0.,
            vp.height,
            columns,
            rows,
            &mut mean,
        );
        for (cell, value) in mean.iter().enumerate() {
            let color = value.rgba8();
            // density_rgba_linear_into returns image top first by vertically
            // reversing mathematical y. CSS source y already points down.
            let flipped = ((rows - 1 - cell / columns) * columns + cell % columns) * 4;
            rgba[flipped..flipped + 3].copy_from_slice(&color[..3]);
            rgba[flipped + 3] = ((rgba[flipped + 3] as u16 * color[3] as u16 + 127) / 255) as u8;
        }
    }
    // Existing density color kernels are bottom-row-first. Our source bins
    // are CSS top-row-first; undo the image flip exactly once in Rust.
    for row in 0..rows / 2 {
        let a = row * columns * 4;
        let b = (rows - 1 - row) * columns * 4;
        for x in 0..columns * 4 {
            rgba.swap(a + x, b + x);
        }
    }
    let style_ref = builder.paint(owner, layer.style, intern)?;
    builder.mark(
        SceneRecordKind::Image,
        layer.layer_id,
        style_ref,
        [0., 0., vp.width, vp.height],
        0.,
        0,
    )?;
    builder.images.push(SceneImage {
        stable_id: layer.layer_id,
        width: columns as u32,
        height: rows as u32,
        rgba,
    });
    // Selected/hovered/focused members retain exact source IDs as overlays;
    // the density blit itself remains an aggregate with complete bin CSR.
    for ((&x, &y), &row) in xs.iter().zip(&ys).zip(&feature_rows) {
        let flags = layer.state_flags.get(row as usize).copied().unwrap_or(0);
        if flags & (GEO_STATE_SELECTED | GEO_STATE_HOVERED | GEO_STATE_FOCUSED) != 0 {
            let style = resolve_style(layer, row as usize, stops)?;
            let reference = builder.paint(owner, style, intern)?;
            builder.mark(
                SceneRecordKind::Scatter,
                layer.source.feature_ids()[row as usize],
                reference,
                [x, y, 0., 0.],
                style.diameter,
                style.symbol,
            )?;
        }
    }
    metadata.density = Some(GeoDensityMembership {
        columns: columns as u32,
        rows: rows as u32,
        counts,
        offsets,
        feature_indices: indices,
    });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn viewport() -> GeoViewport {
        GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 2., 128., 128., 0., 0., true).unwrap()
    }
    fn source(
        kind: GeoGeometry,
        xy: &[f64],
        ids: &[u64],
        validity: &[u8],
        offsets: [&[u32]; 3],
    ) -> GeoColumn {
        GeoColumn::from_descriptor(crate::geo::GeoDescriptor {
            geometry: kind,
            crs: GeoCrs::Epsg4326,
            xy,
            validity,
            feature_ids: Some(ids),
            offsets0: offsets[0],
            offsets1: offsets[1],
            offsets2: offsets[2],
            limits: crate::geo::GeoLimits::default(),
        })
        .unwrap()
    }
    fn coordinates(pixels: &[[f64; 2]]) -> Vec<f64> {
        pixels
            .iter()
            .flat_map(|p| {
                let (x, y) = viewport().unproject(p[0], p[1]).unwrap();
                [x, y]
            })
            .collect()
    }
    fn point_source() -> GeoColumn {
        source(
            GeoGeometry::Point,
            &coordinates(&[[40., 64.], [88., 64.]]),
            &[u64::MAX, 0x5859_0100_0000_0001],
            &[1, 1],
            [&[], &[], &[]],
        )
    }
    fn run(layers: &[GeoLayer<'_>]) -> GeoCompiled {
        compile(&GeoCatalog {
            viewport: viewport(),
            layers,
            legend: None,
            budget: 64 << 20,
        })
        .unwrap()
    }
    fn records(scene: &[u8]) -> Vec<&[u8]> {
        scene::validate_scene_batch(scene).unwrap();
        let count = u64::from_le_bytes(scene[16..24].try_into().unwrap()) as usize;
        let styles = u64::from_le_bytes(scene[24..32].try_into().unwrap()) as usize;
        let begin = scene::SCENE_BATCH_HEADER_BYTES + styles * scene::SCENE_STYLE_RECORD_BYTES;
        scene[begin..begin + count * scene::SCENE_BATCH_RECORD_BYTES]
            .chunks_exact(scene::SCENE_BATCH_RECORD_BYTES)
            .collect()
    }
    fn number(row: &[u8], at: usize) -> f64 {
        f64::from_le_bytes(row[at..at + 8].try_into().unwrap())
    }
    fn id(row: &[u8]) -> u64 {
        u64::from_le_bytes(row[8..16].try_into().unwrap())
    }
    fn style(row: &[u8]) -> usize {
        u32::from_le_bytes(row[4..8].try_into().unwrap()) as usize
    }
    fn rgb(scene: &[u8], reference: usize) -> [u8; 4] {
        let at = scene::SCENE_BATCH_HEADER_BYTES + reference * scene::SCENE_STYLE_RECORD_BYTES;
        scene[at..at + 4].try_into().unwrap()
    }
    fn raster(scene: &[u8]) -> Vec<u8> {
        let commands = scene::SceneDocument::decode(scene)
            .unwrap()
            .to_raster_commands(1.)
            .unwrap();
        let mut pixels = vec![0; 128 * 128 * 4];
        assert!(crate::raster::rasterize_into(
            &commands,
            128,
            128,
            &mut pixels
        ));
        pixels
    }
    fn pixel(bytes: &[u8], x: usize, y: usize) -> [u8; 4] {
        bytes[(y * 128 + x) * 4..(y * 128 + x) * 4 + 4]
            .try_into()
            .unwrap()
    }
    fn fill_area(bytes: &[u8]) -> f64 {
        let mut points = Vec::new();
        let mut area = 0.;
        for row in records(bytes) {
            if row[0] == SceneRecordKind::Triangle as u8 && row[1] != 0 {
                points.push([number(row, 16), number(row, 24)]);
                if points.len() == 3 {
                    let a = points[0];
                    let b = points[1];
                    let c = points[2];
                    area +=
                        ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])).abs() * 0.5;
                    points.clear();
                }
            } else {
                assert!(points.is_empty());
            }
        }
        area
    }
    #[test]
    fn point_identity_layer_order_and_literal_namespace_survive_scene_and_decorations() {
        let source = point_source();
        let before = source.xy().to_vec();
        let labels = [GeoLabel {
            feature_index: 0,
            coordinate: [source.xy()[0], source.xy()[1]],
            text: "Canonical feature",
            font_size: 12.,
            rgba: [0, 0, 0, 255],
            anchor: 0,
        }];
        let mut first = GeoLayer::new(u64::MAX, GeoLayerKind::Points, &source);
        first.style.fill = [255, 0, 0, 255];
        first.style.stroke_width = 0.;
        first.legend_label = Some("first");
        first.labels = &labels;
        let mut second = GeoLayer::new(7, GeoLayerKind::Points, &source);
        second.style.fill = [0, 0, 255, 255];
        second.style.stroke_width = 0.;
        second.legend_label = Some("second");
        let output = compile(&GeoCatalog {
            viewport: viewport(),
            layers: &[first, second],
            legend: Some(GeoLegend {
                title: "Layers",
                location: LegendLocation::UpperRight,
                font_size: 12.,
            }),
            budget: 64 << 20,
        })
        .unwrap();
        let marks: Vec<_> = records(&output.scene)
            .into_iter()
            .filter(|r| r[0] == 0 && r[1] != 0)
            .collect();
        assert_eq!(marks.len(), 4);
        assert_eq!(
            marks.iter().map(|r| id(r)).collect::<Vec<_>>(),
            [
                u64::MAX,
                0x5859_0100_0000_0001,
                u64::MAX,
                0x5859_0100_0000_0001
            ]
        );
        assert!(marks.iter().all(|r| r[3] == 0x80));
        assert_eq!(output.style_owners[style(marks[0])], Some(0));
        assert_eq!(output.style_owners[style(marks[2])], Some(1));
        let svg = scene::SceneDocument::decode(&output.scene)
            .unwrap()
            .to_svg();
        assert!(
            svg.contains("Canonical feature") && svg.contains("first") && svg.contains("second")
        );
        assert_eq!(source.xy(), before);
        assert_eq!(output.layers[0].feature_ids, output.layers[1].feature_ids);
    }
    #[test]
    fn bubble_area_channel_then_feature_selected_hover_focus_precedence_is_explicit() {
        let source = point_source();
        let patches = [
            GeoStylePatch {
                diameter: Some(4.),
                fill: Some([0, 255, 0, 255]),
                ..Default::default()
            },
            GeoStylePatch::default(),
        ];
        let mut layer = GeoLayer::new(1, GeoLayerKind::Bubbles, &source);
        layer.values = &[0.5, 1.];
        layer.value_domain = Some([0., 1.]);
        layer.bubble_diameters = [2., 10.];
        layer.feature_styles = &patches;
        layer.state_flags = &[14, 1];
        layer.state_styles.selected.diameter = Some(7.);
        layer.state_styles.hovered.diameter = Some(8.);
        layer.state_styles.focused.diameter = Some(9.);
        layer.state_styles.focused.fill = Some([17, 18, 19, 255]);
        let output = run(&[layer]);
        let marks: Vec<_> = records(&output.scene)
            .into_iter()
            .filter(|r| r[0] == 0 && r[1] != 0)
            .collect();
        assert_eq!(marks.len(), 1);
        assert_eq!(number(marks[0], 48), 9.);
        assert_eq!(rgb(&output.scene, style(marks[0])), [17, 18, 19, 255]);
        assert_eq!(output.layers[0].visible_feature_indices, [0]);
        let mut layer = GeoLayer::new(1, GeoLayerKind::Bubbles, &source);
        layer.values = &[0.5, 1.];
        layer.value_domain = Some([0., 1.]);
        layer.bubble_diameters = [2., 10.];
        let output = run(&[layer]);
        let sizes: Vec<_> = records(&output.scene)
            .into_iter()
            .filter(|r| r[0] == 0 && r[1] != 0)
            .map(|r| number(r, 48))
            .collect();
        assert!((sizes[0] - 52f64.sqrt()).abs() < 1e-12);
        assert_eq!(sizes[1], 10.);
    }
    #[test]
    fn polygon_hole_is_empty_in_actual_raster_and_triangle_area() {
        let xy = coordinates(&[
            [20., 20.],
            [100., 20.],
            [100., 100.],
            [20., 100.],
            [20., 20.],
            [40., 40.],
            [40., 80.],
            [80., 80.],
            [80., 40.],
            [40., 40.],
        ]);
        let source = source(
            GeoGeometry::Polygon,
            &xy,
            &[u64::MAX],
            &[1],
            [&[0, 2], &[0, 5, 10], &[]],
        );
        let mut layer = GeoLayer::new(9, GeoLayerKind::Polygons, &source);
        layer.style.fill = [255, 0, 0, 255];
        layer.style.stroke_width = 0.;
        let output = run(&[layer]);
        assert!((fill_area(&output.scene) - 4800.).abs() < 1e-3);
        let pixels = raster(&output.scene);
        assert_eq!(pixel(&pixels, 30, 30), [255, 0, 0, 255]);
        assert_eq!(pixel(&pixels, 60, 60)[3], 0);
        assert_eq!(source.xy(), xy);
        let document = scene::SceneDocument::decode(&output.scene).unwrap();
        assert!(document.to_browser_painter(64 << 20).is_ok());
        assert!(records(&output.scene)
            .into_iter()
            .filter(|r| r[0] == 4)
            .all(|r| id(r) == u64::MAX && r[3] == 0x80));
    }
    #[test]
    fn multipolygon_holes_and_multipart_owner_are_preserved() {
        let xy = coordinates(&[
            [10., 10.],
            [50., 10.],
            [50., 50.],
            [10., 50.],
            [10., 10.],
            [20., 20.],
            [20., 40.],
            [40., 40.],
            [40., 20.],
            [20., 20.],
            [80., 80.],
            [110., 80.],
            [110., 110.],
            [80., 110.],
            [80., 80.],
        ]);
        let source = source(
            GeoGeometry::MultiPolygon,
            &xy,
            &[42],
            &[1],
            [&[0, 2], &[0, 2, 3], &[0, 5, 10, 15]],
        );
        let mut layer = GeoLayer::new(2, GeoLayerKind::Polygons, &source);
        layer.style.fill = [255, 0, 0, 255];
        layer.style.stroke_width = 0.;
        let output = run(&[layer]);
        assert!((fill_area(&output.scene) - 2100.).abs() < 1e-3);
        let pixels = raster(&output.scene);
        assert_eq!(pixel(&pixels, 30, 30)[3], 0);
        assert_eq!(pixel(&pixels, 15, 14)[3], 255);
        assert_eq!(pixel(&pixels, 90, 91)[3], 255);
        assert_eq!(output.layers[0].visible_feature_indices, [0]);
    }
    #[test]
    fn overlapping_choropleth_features_keep_source_paint_order_and_domain() {
        let xy = coordinates(&[
            [20., 20.],
            [90., 20.],
            [90., 90.],
            [20., 90.],
            [20., 20.],
            [50., 50.],
            [110., 50.],
            [110., 110.],
            [50., 110.],
            [50., 50.],
        ]);
        let source = source(
            GeoGeometry::Polygon,
            &xy,
            &[100, 200],
            &[1, 1],
            [&[0, 1, 2], &[0, 5, 10], &[]],
        );
        let mut layer = GeoLayer::new(1, GeoLayerKind::Choropleth, &source);
        layer.style.stroke_width = 0.;
        layer.values = &[0., 1.];
        layer.value_domain = Some([0., 1.]);
        layer.color_stops = &[[255, 0, 0], [0, 0, 255]];
        let output = run(&[layer]);
        let pixels = raster(&output.scene);
        assert_eq!(pixel(&pixels, 30, 31), [255, 0, 0, 255]);
        assert_eq!(pixel(&pixels, 70, 65), [0, 0, 255, 255]);
        assert_eq!(output.layers[0].visible_feature_indices, [0, 1]);
    }
    #[test]
    fn sampled_arc_has_independently_expected_bezier_midpoint() {
        let source = source(
            GeoGeometry::LineString,
            &coordinates(&[[20., 64.], [108., 64.]]),
            &[8],
            &[1],
            [&[0, 2], &[], &[]],
        );
        let layer = GeoLayer::new(1, GeoLayerKind::Arcs, &source);
        let output = run(&[layer]);
        let vertices: Vec<_> = records(&output.scene)
            .into_iter()
            .filter(|r| r[0] == SceneRecordKind::Segment as u8 && r[1] != 0)
            .map(|r| (number(r, 16), number(r, 24)))
            .collect();
        assert!(vertices
            .iter()
            .any(|&(x, y)| (x - 64.).abs() < 1e-4 && (y - 47.5).abs() < 1e-4));
        assert_eq!(output.layers[0].visible_feature_indices, [0]);
        assert!(records(&output.scene)
            .into_iter()
            .filter(|r| r[0] == 1)
            .all(|r| id(r) == 8));
    }
    #[test]
    fn dateline_route_and_polygon_hole_use_shared_pitched_projection() {
        let vp =
            GeoViewport::new(GeoCrs::Epsg4326, 180., 0., 2., 128., 128., 0., 30., true).unwrap();
        let line = source(
            GeoGeometry::LineString,
            &[179., 0., -179., 0.],
            &[99],
            &[1],
            [&[0, 2], &[], &[]],
        );
        let polygon = source(
            GeoGeometry::Polygon,
            &[
                170., -10., -170., -10., -170., 10., 170., 10., 170., -10., 175., -5., 175., 5.,
                -175., 5., -175., -5., 175., -5.,
            ],
            &[u64::MAX],
            &[1],
            [&[0, 2], &[0, 5, 10], &[]],
        );
        let mut fill = GeoLayer::new(1, GeoLayerKind::Polygons, &polygon);
        fill.style.fill = [255, 0, 0, 255];
        fill.style.stroke_width = 0.;
        let route = GeoLayer::new(2, GeoLayerKind::Routes, &line);
        let output = compile(&GeoCatalog {
            viewport: vp,
            layers: &[fill, route],
            legend: None,
            budget: 64 << 20,
        })
        .unwrap();
        assert_eq!(output.layers[0].visible_feature_indices, [0]);
        assert_eq!(output.layers[1].visible_feature_indices, [0]);
        assert_eq!(output.layers[0].source_digest, polygon.metadata_digest());
        let lines: Vec<_> = records(&output.scene)
            .into_iter()
            .filter(|r| r[0] == SceneRecordKind::Segment as u8 && r[1] != 0)
            .collect();
        assert_eq!(lines.len(), 4);
        assert!(lines.iter().all(|r| id(r) == 99));
        assert!(lines
            .windows(2)
            .all(|r| (number(r[0], 16) - number(r[1], 16)).abs() < 12.));
        let pixels = raster(&output.scene);
        assert_eq!(pixel(&pixels, 64, 45)[3], 0);
        let (x, y) = vp.project(172., 0.).unwrap();
        assert_eq!(
            pixel(&pixels, x.round() as usize, y.round() as usize),
            [255, 0, 0, 255]
        );
    }
    #[test]
    fn density_image_bin_counts_complete_membership_and_nulls_are_canonical() {
        let xy = coordinates(&[[10., 10.], [10., 10.], [70., 10.], [10., 70.]]);
        let source = source(
            GeoGeometry::Point,
            &xy,
            &[10, u64::MAX, 20, 30, 40],
            &[1, 1, 1, 1, 0],
            [&[], &[], &[]],
        );
        let mut layer = GeoLayer::new(900, GeoLayerKind::Density, &source);
        layer.density = GeoDensityOptions {
            columns: 2,
            rows: 2,
        };
        let output = run(&[layer]);
        let bins = output.layers[0].density.as_ref().unwrap();
        assert_eq!(bins.counts, [2, 1, 1, 0]);
        assert_eq!(bins.offsets, [0, 2, 3, 4, 4]);
        assert_eq!(bins.feature_indices, [0, 1, 2, 3]);
        assert_eq!(output.layers[0].visible_feature_indices, [0, 1, 2, 3]);
        assert_eq!(output.layers[0].feature_ids[1], u64::MAX);
        assert_eq!(output.layers[0].dropped_channels, 7);
        let pixels = raster(&output.scene);
        assert!(pixel(&pixels, 10, 10)[3] > 0);
        assert!(pixel(&pixels, 10, 100)[3] > 0);
        assert_eq!(pixel(&pixels, 100, 100)[3], 0);
        assert_eq!(
            records(&output.scene)
                .into_iter()
                .find(|r| r[0] == SceneRecordKind::Image as u8)
                .map(id),
            Some(900)
        );
    }
    #[test]
    fn density_mean_color_and_selection_overlay_keep_source_identity() {
        let source = source(
            GeoGeometry::Point,
            &coordinates(&[[10., 10.], [10., 10.]]),
            &[10, u64::MAX],
            &[1, 1],
            [&[], &[], &[]],
        );
        let patches = [
            GeoStylePatch {
                fill: Some([255, 0, 0, 255]),
                ..Default::default()
            },
            GeoStylePatch {
                fill: Some([0, 0, 255, 255]),
                ..Default::default()
            },
        ];
        let mut layer = GeoLayer::new(9, GeoLayerKind::Density, &source);
        layer.density = GeoDensityOptions {
            columns: 1,
            rows: 1,
        };
        layer.feature_styles = &patches;
        layer.state_flags = &[2, 0];
        let output = run(&[layer]);
        let overlay: Vec<_> = records(&output.scene)
            .into_iter()
            .filter(|r| r[0] == 0 && r[1] != 0)
            .collect();
        assert_eq!(overlay.len(), 1);
        assert_eq!(id(overlay[0]), 10);
        let pixels = raster(&output.scene);
        assert_eq!(pixel(&pixels, 80, 80), [188, 0, 188, 255]);
        assert_eq!(
            output.layers[0].density.as_ref().unwrap().feature_indices,
            [0, 1]
        );
    }
    #[test]
    fn polygon_fill_has_no_internal_stroke_and_opacity_is_resolved_once() {
        let polygon = source(
            GeoGeometry::Polygon,
            &coordinates(&[
                [20., 20.],
                [100., 20.],
                [100., 100.],
                [20., 100.],
                [20., 20.],
            ]),
            &[u64::MAX],
            &[1],
            [&[0, 1], &[0, 5], &[]],
        );
        let mut layer = GeoLayer::new(7, GeoLayerKind::Polygons, &polygon);
        layer.style.fill = [255, 0, 0, 255];
        layer.style.stroke = [0, 0, 255, 255];
        layer.style.stroke_width = 3.;
        layer.style.opacity = 0.5;
        let output = run(&[layer]);
        let rows = records(&output.scene);
        let triangles: Vec<_> = rows
            .iter()
            .filter(|r| r[0] == SceneRecordKind::Triangle as u8)
            .collect();
        assert!(!triangles.is_empty());
        assert_eq!(triangles.len() % 3, 0);
        for row in triangles {
            let at = scene::SCENE_BATCH_HEADER_BYTES + style(row) * scene::SCENE_STYLE_RECORD_BYTES;
            assert_eq!(&output.scene[at..at + 8], &[255, 0, 0, 128, 0, 0, 0, 0]);
            assert_eq!(number(&output.scene[at..], 8), 0.);
            assert_eq!(id(row), u64::MAX);
        }
        let edges: Vec<_> = rows
            .iter()
            .filter(|r| r[0] == SceneRecordKind::Segment as u8 && r[1] != 0)
            .collect();
        assert_eq!(edges.len(), 8);
        for edge in edges {
            let at =
                scene::SCENE_BATCH_HEADER_BYTES + style(edge) * scene::SCENE_STYLE_RECORD_BYTES;
            assert_eq!(&output.scene[at + 4..at + 8], &[0, 0, 255, 128]);
            assert_eq!(number(&output.scene[at..], 8), 3.);
        }
    }
    #[test]
    fn triangle_seams_blend_once_but_duplicate_source_rows_paint_twice() {
        let square = [
            [20., 20.],
            [100., 20.],
            [100., 100.],
            [20., 100.],
            [20., 20.],
        ];
        let one = source(
            GeoGeometry::Polygon,
            &coordinates(&square),
            &[u64::MAX],
            &[1],
            [&[0, 1], &[0, 5], &[]],
        );
        let mut layer = GeoLayer::new(7, GeoLayerKind::Polygons, &one);
        layer.style.fill = [255, 0, 0, 255];
        layer.style.stroke_width = 0.;
        layer.style.opacity = 0.5;
        assert_eq!(
            pixel(&raster(&run(&[layer]).scene), 60, 60),
            [255, 0, 0, 128]
        );
        let mut doubled = square.to_vec();
        doubled.extend(square);
        let two = source(
            GeoGeometry::Polygon,
            &coordinates(&doubled),
            &[u64::MAX, u64::MAX],
            &[1, 1],
            [&[0, 1, 2], &[0, 5, 10], &[]],
        );
        let mut layer = GeoLayer::new(7, GeoLayerKind::Polygons, &two);
        layer.style.fill = [255, 0, 0, 255];
        layer.style.stroke_width = 0.;
        layer.style.opacity = 0.5;
        assert_eq!(
            pixel(&raster(&run(&[layer]).scene), 60, 60),
            [255, 0, 0, 192]
        );
    }
    #[test]
    fn small_viewport_legend_rejection_is_independent_of_layer_id_bits() {
        let points = point_source();
        let legend = GeoLegend {
            title: "Geography",
            location: LegendLocation::UpperRight,
            font_size: 12.,
        };
        let mut results = Vec::new();
        for id in [1, u64::MAX] {
            let mut layer = GeoLayer::new(id, GeoLayerKind::Points, &points);
            layer.legend_label = Some("Locations");
            let mut vp = viewport();
            vp.width = 100.;
            vp.height = 80.;
            results.push(
                compile(&GeoCatalog {
                    viewport: vp,
                    layers: &[layer],
                    legend: Some(legend),
                    budget: 64 << 20,
                })
                .map(|_| ()),
            );
        }
        assert_eq!(results[0], results[1]);
    }
    #[test]
    fn density_mean_color_global_opacity_and_state_color_apply_once() {
        let source = source(
            GeoGeometry::Point,
            &coordinates(&[[10., 10.], [10., 10.]]),
            &[1, 2],
            &[1, 1],
            [&[], &[], &[]],
        );
        let mut layer = GeoLayer::new(3, GeoLayerKind::Density, &source);
        layer.density = GeoDensityOptions {
            columns: 1,
            rows: 1,
        };
        layer.style.fill = [255, 0, 0, 255];
        layer.style.opacity = 0.5;
        layer.state_flags = &[GEO_STATE_FOCUSED, 0];
        layer.state_styles.focused.fill = Some([0, 0, 255, 255]);
        let output = run(&[layer]);
        assert_eq!(pixel(&raster(&output.scene), 80, 80), [188, 0, 188, 128]);
    }
    #[test]
    fn deep_zoom_does_not_use_first_offscreen_point_as_f32_origin() {
        let source = source(
            GeoGeometry::Point,
            &[100., 0., 0., 0., 0.0000001, 0.],
            &[1, u64::MAX, 3],
            &[1, 1, 1],
            [&[], &[], &[]],
        );
        let mut vp = viewport();
        vp.zoom = 24.;
        let output = compile(&GeoCatalog {
            viewport: vp,
            layers: &[GeoLayer::new(8, GeoLayerKind::Points, &source)],
            legend: None,
            budget: 64 << 20,
        })
        .unwrap();
        let rows: Vec<_> = records(&output.scene)
            .into_iter()
            .filter(|r| r[0] == 0 && r[1] != 0)
            .collect();
        assert_eq!(rows.len(), 2);
        assert_eq!(id(rows[0]), u64::MAX);
        let separation = number(rows[1], 16) - number(rows[0], 16);
        assert!((separation - 2.3860929422).abs() < 1e-6, "{separation}");
        assert_eq!(output.layers[0].visible_feature_indices, [1, 2]);
    }
    #[test]
    fn multipart_and_duplicate_ids_preserve_row_styles_and_source_order() {
        let points = source(
            GeoGeometry::MultiPoint,
            &coordinates(&[[10., 10.], [20., 20.], [90., 90.]]),
            &[u64::MAX, u64::MAX],
            &[1, 1],
            [&[0, 2, 3], &[], &[]],
        );
        let patches = [
            GeoStylePatch {
                fill: Some([255, 0, 0, 255]),
                ..Default::default()
            },
            GeoStylePatch {
                fill: Some([0, 0, 255, 255]),
                ..Default::default()
            },
        ];
        let mut layer = GeoLayer::new(1, GeoLayerKind::Points, &points);
        layer.feature_styles = &patches;
        let output = run(&[layer]);
        let rows: Vec<_> = records(&output.scene)
            .into_iter()
            .filter(|r| r[0] == 0 && r[1] != 0)
            .collect();
        assert_eq!(rows.len(), 3);
        assert!(rows.iter().all(|r| id(r) == u64::MAX));
        assert_eq!(rgb(&output.scene, style(rows[0])), [255, 0, 0, 255]);
        assert_eq!(rgb(&output.scene, style(rows[1])), [255, 0, 0, 255]);
        assert_eq!(rgb(&output.scene, style(rows[2])), [0, 0, 255, 255]);
        assert_eq!(output.layers[0].visible_feature_indices, [0, 1]);
        let lines = source(
            GeoGeometry::MultiLineString,
            &coordinates(&[[10., 10.], [20., 10.], [90., 90.], [100., 90.]]),
            &[u64::MAX],
            &[1],
            [&[0, 2], &[0, 2, 4], &[]],
        );
        let output = run(&[GeoLayer::new(2, GeoLayerKind::Routes, &lines)]);
        let rows: Vec<_> = records(&output.scene)
            .into_iter()
            .filter(|r| r[0] == SceneRecordKind::Segment as u8 && r[1] != 0)
            .collect();
        assert_eq!(rows.len(), 4);
        assert!(rows.iter().all(|r| id(r) == u64::MAX));
        assert!((number(rows[1], 16) - number(rows[0], 16) - 10.).abs() < 1e-4);
        assert!((number(rows[3], 16) - number(rows[2], 16) - 10.).abs() < 1e-4);
    }
    #[test]
    fn density_and_arc_admission_precedes_large_derived_allocations() {
        let points = point_source();
        let mut layer = GeoLayer::new(1, GeoLayerKind::Density, &points);
        layer.density = GeoDensityOptions {
            columns: 4096,
            rows: 4096,
        };
        assert_eq!(
            compile(&GeoCatalog {
                viewport: viewport(),
                layers: &[layer],
                legend: None,
                budget: 64 << 20
            })
            .unwrap_err(),
            GeoError::ResourceLimit
        );
        let lines = source(
            GeoGeometry::LineString,
            &coordinates(&[[10., 10.], [100., 100.]]),
            &[1],
            &[1],
            [&[0, 2], &[], &[]],
        );
        let mut layer = GeoLayer::new(1, GeoLayerKind::Arcs, &lines);
        layer.arc.steps = 257;
        assert_eq!(
            compile(&GeoCatalog {
                viewport: viewport(),
                layers: &[layer],
                legend: None,
                budget: 64 << 20
            })
            .unwrap_err(),
            GeoError::InvalidArgument
        );
    }
    #[test]
    fn malformed_style_scalar_state_text_and_catalog_fail_atomically() {
        let source = point_source();
        let before = source.xy().to_vec();
        for value in [f64::NAN, f64::INFINITY, f64::MAX, -1.] {
            let mut layer = GeoLayer::new(1, GeoLayerKind::Points, &source);
            layer.style.diameter = value;
            assert!(compile(&GeoCatalog {
                viewport: viewport(),
                layers: &[layer],
                legend: None,
                budget: 64 << 20
            })
            .is_err());
        }
        let mut layer = GeoLayer::new(1, GeoLayerKind::Bubbles, &source);
        layer.values = &[0., 1.];
        assert!(compile(&GeoCatalog {
            viewport: viewport(),
            layers: &[layer],
            legend: None,
            budget: 64 << 20
        })
        .is_err());
        let mut layer = GeoLayer::new(1, GeoLayerKind::Points, &source);
        layer.state_flags = &[16, 0];
        assert_eq!(
            compile(&GeoCatalog {
                viewport: viewport(),
                layers: &[layer],
                legend: None,
                budget: 64 << 20
            })
            .unwrap_err(),
            GeoError::InvalidArgument
        );
        let text = "x".repeat(scene::MAX_SCENE_LABEL_TEXT_BYTES + 1);
        let labels = [GeoLabel {
            feature_index: 0,
            coordinate: [0., 0.],
            text: &text,
            font_size: 12.,
            rgba: [0; 4],
            anchor: 0,
        }];
        let mut layer = GeoLayer::new(1, GeoLayerKind::Points, &source);
        layer.labels = &labels;
        assert_eq!(
            compile(&GeoCatalog {
                viewport: viewport(),
                layers: &[layer],
                legend: None,
                budget: 64 << 20
            })
            .unwrap_err(),
            GeoError::ResourceLimit
        );
        let layers = [
            GeoLayer::new(1, GeoLayerKind::Points, &source),
            GeoLayer::new(1, GeoLayerKind::Points, &source),
        ];
        assert_eq!(
            compile(&GeoCatalog {
                viewport: viewport(),
                layers: &layers,
                legend: None,
                budget: 64 << 20
            })
            .unwrap_err(),
            GeoError::InvalidArgument
        );
        let layers = [GeoLayer::new(1, GeoLayerKind::Points, &source)];
        assert_eq!(
            compile(&GeoCatalog {
                viewport: viewport(),
                layers: &layers,
                legend: None,
                budget: 32768
            })
            .unwrap_err(),
            GeoError::ResourceLimit
        );
        assert_eq!(source.xy(), before);
    }
}
