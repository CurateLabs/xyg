//! Bounded geographic interaction policy (#49; dossier §17/§20/§27).
use crate::geo::GeoError;
use crate::geo_layers::{
    GeoCompiled, GEO_STATE_FOCUSED, GEO_STATE_HIDDEN, GEO_STATE_HOVERED, GEO_STATE_SELECTED,
};
use crate::scene::{self, SceneDocument, SceneRecordKind};

pub const MAX_GEO_INTERACTION_ROWS: usize = 1_000_000;
pub const MAX_GEO_STATE_ROWS: usize = 2_000_000;
pub const MAX_GEO_PICK_PRIMITIVES: usize = 131_072;
pub const MAX_GEO_PICK_GRID_ENTRIES: usize = 1_048_576;
pub const MAX_GEO_PICK_CANDIDATES: usize = 65_536;
pub const MAX_GEO_INTERACTION_WORK: usize = 4_000_000;
const GRID: usize = 64;
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct GeoFeatureKey {
    pub layer_id: u64,
    pub feature_id: u64,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum GeoSelectionMode {
    Replace = 0,
    Add = 1,
    Toggle = 2,
}
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum GeoInteractionEvent {
    Hover {
        x: f64,
        y: f64,
    },
    SelectAt {
        x: f64,
        y: f64,
        mode: GeoSelectionMode,
    },
    Brush {
        bounds: [f64; 4],
        mode: GeoSelectionMode,
    },
    Clear,
    FocusStep {
        delta: i32,
    },
    FocusFeature {
        key: GeoFeatureKey,
    },
    SelectFeature {
        key: GeoFeatureKey,
        mode: GeoSelectionMode,
    },
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GeoInteractionState {
    pub layer_flags: Vec<Vec<u8>>,
    pub focus: Option<GeoFeatureKey>,
}
impl GeoInteractionState {
    /// Normalize authored focus without allocating a spatial index. Camera
    /// rebuilds preserve the first focused source row's exact feature key.
    pub fn from_compiled(compiled: &GeoCompiled) -> Result<Self, GeoError> {
        let rows = compiled
            .layers
            .iter()
            .try_fold(0usize, |n, l| n.checked_add(l.feature_ids.len()))
            .ok_or(GeoError::ResourceLimit)?;
        if rows > MAX_GEO_STATE_ROWS || compiled.layers.len() > crate::geo_layers::MAX_GEO_LAYERS {
            return Err(GeoError::ResourceLimit);
        }
        if compiled.layers.iter().enumerate().any(|(i, l)| {
            compiled.layers[..i]
                .iter()
                .any(|p| p.layer_id == l.layer_id)
        }) {
            return Err(GeoError::InvalidArgument);
        }
        let mut focus = None;
        for layer in &compiled.layers {
            if layer.feature_ids.len() != layer.validity.len()
                || layer.feature_ids.len() != layer.state_flags.len()
                || layer.state_flags.iter().any(|f| f & !15 != 0)
                || layer.validity.iter().any(|v| *v > 1)
            {
                return Err(GeoError::InvalidArgument);
            }
            if focus.is_none() {
                for row in 0..layer.feature_ids.len() {
                    if layer.validity[row] != 0
                        && layer.state_flags[row] & GEO_STATE_HIDDEN == 0
                        && layer.state_flags[row] & GEO_STATE_FOCUSED != 0
                    {
                        focus = Some(GeoFeatureKey {
                            layer_id: layer.layer_id,
                            feature_id: layer.feature_ids[row],
                        });
                        break;
                    }
                }
            }
        }
        let mut layer_flags = Vec::new();
        for layer in &compiled.layers {
            let mut flags = layer.state_flags.clone();
            for (row, f) in flags.iter_mut().enumerate() {
                *f &= !GEO_STATE_FOCUSED;
                if focus
                    == Some(GeoFeatureKey {
                        layer_id: layer.layer_id,
                        feature_id: layer.feature_ids[row],
                    })
                    && layer.validity[row] != 0
                    && layer.state_flags[row] & GEO_STATE_HIDDEN == 0
                {
                    *f |= GEO_STATE_FOCUSED;
                }
            }
            layer_flags.push(flags);
        }
        Ok(Self { layer_flags, focus })
    }
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GeoFeatureHit {
    pub key: GeoFeatureKey,
    pub feature_indices: Vec<u32>,
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GeoInteractionResult {
    pub state: GeoInteractionState,
    pub hits: Vec<GeoFeatureHit>,
}
#[derive(Debug, Clone, Copy)]
enum Shape {
    Marker {
        x: f64,
        y: f64,
        diameter: f64,
        symbol: u8,
        stroke: f64,
        fill: bool,
        outline: bool,
    },
    Segment {
        a: [f64; 2],
        b: [f64; 2],
        radius: f64,
    },
    Triangle([f64; 6]),
    Density,
}
#[derive(Debug, Clone, Copy)]
struct Primitive {
    layer: usize,
    id: u64,
    bounds: [f64; 4],
    shape: Shape,
}
/// The retained compiled result and decoded Scene are immutable for this index.
pub struct GeoPickIndex<'a> {
    compiled: &'a GeoCompiled,
    scene: SceneDocument,
    width: f64,
    height: f64,
    primitives: Vec<Primitive>,
    offsets: Vec<u32>,
    entries: Vec<u32>,
    rows: Vec<Vec<(u64, u32)>>,
    keyboard: Vec<GeoFeatureKey>,
}
fn err(error: scene::SceneError) -> GeoError {
    if matches!(
        error,
        scene::SceneError::Limit | scene::SceneError::PainterTraceLimit
    ) {
        GeoError::ResourceLimit
    } else {
        GeoError::InvalidArgument
    }
}
fn finite(p: &[f64]) -> bool {
    p.iter().all(|n| n.is_finite())
}
fn intersects(a: [f64; 4], b: [f64; 4]) -> bool {
    a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1]
}
fn bounds(points: &[f64], r: f64) -> [f64; 4] {
    let mut b = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    for p in points.chunks_exact(2) {
        b[0] = b[0].min(p[0] - r);
        b[1] = b[1].min(p[1] - r);
        b[2] = b[2].max(p[0] + r);
        b[3] = b[3].max(p[1] + r);
    }
    b
}
fn distance(p: [f64; 2], a: [f64; 2], b: [f64; 2]) -> f64 {
    let dx = b[0] - a[0];
    let dy = b[1] - a[1];
    let d = dx * dx + dy * dy;
    let t = if d == 0. {
        0.
    } else {
        ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / d
    }
    .clamp(0., 1.);
    (p[0] - a[0] - t * dx).hypot(p[1] - a[1] - t * dy)
}
fn in_triangle(p: [f64; 2], t: [f64; 6]) -> bool {
    let cross = |a: [f64; 2], b: [f64; 2], c: [f64; 2]| {
        (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    };
    let a = [t[0], t[1]];
    let b = [t[2], t[3]];
    let c = [t[4], t[5]];
    if cross(a, b, c) == 0. {
        return false;
    }
    let x = cross(a, b, p);
    let y = cross(b, c, p);
    let z = cross(c, a, p);
    (x >= 0. && y >= 0. && z >= 0.) || (x <= 0. && y <= 0. && z <= 0.)
}
fn segment_rect(a: [f64; 2], b: [f64; 2], r: [f64; 4]) -> bool {
    let mut lo: f64 = 0.;
    let mut hi: f64 = 1.;
    for (start, delta, min, max) in [
        (a[0], b[0] - a[0], r[0], r[2]),
        (a[1], b[1] - a[1], r[1], r[3]),
    ] {
        if delta == 0. {
            if start < min || start > max {
                return false;
            }
        } else {
            let x = (min - start) / delta;
            let y = (max - start) / delta;
            lo = lo.max(x.min(y));
            hi = hi.min(x.max(y));
            if lo > hi {
                return false;
            }
        }
    }
    true
}
fn segment_rect_distance(a: [f64; 2], b: [f64; 2], rect: [f64; 4]) -> f64 {
    if segment_rect(a, b, rect) {
        return 0.;
    }
    let corners = [
        [rect[0], rect[1]],
        [rect[2], rect[1]],
        [rect[2], rect[3]],
        [rect[0], rect[3]],
    ];
    let mut d = f64::INFINITY;
    for i in 0..4 {
        let c = corners[i];
        let e = corners[(i + 1) % 4];
        d = d
            .min(distance(c, a, b))
            .min(distance(a, c, e))
            .min(distance(b, c, e));
    }
    d
}
impl<'a> GeoPickIndex<'a> {
    /// Minimum immutable decode/source-row/event scratch reservation. Spatial
    /// primitives and grid duplication are checked incrementally in `new`.
    pub fn admission_floor(compiled: &GeoCompiled) -> Result<usize, GeoError> {
        let rows = compiled
            .layers
            .iter()
            .try_fold(0usize, |n, l| n.checked_add(l.feature_ids.len()))
            .ok_or(GeoError::ResourceLimit)?;
        let mut density = 0usize;
        for layer in &compiled.layers {
            if let Some(d) = &layer.density {
                density = density
                    .checked_add(
                        d.counts
                            .len()
                            .checked_mul(8)
                            .ok_or(GeoError::ResourceLimit)?,
                    )
                    .and_then(|n| {
                        d.feature_indices
                            .len()
                            .checked_mul(4)
                            .and_then(|m| n.checked_add(m))
                    })
                    .ok_or(GeoError::ResourceLimit)?;
            }
        }
        compiled
            .scene
            .len()
            .checked_mul(4)
            .and_then(|n| rows.checked_mul(128).and_then(|r| n.checked_add(r)))
            .and_then(|n| n.checked_add(density))
            .and_then(|n| n.checked_add(GRID * GRID * 16 + 32768))
            .ok_or(GeoError::ResourceLimit)
    }
    pub fn new(compiled: &'a GeoCompiled, budget: usize) -> Result<Self, GeoError> {
        let base_peak = Self::admission_floor(compiled)?;
        if base_peak > budget {
            return Err(GeoError::ResourceLimit);
        }
        let k = compiled.camera;
        crate::geo_viewport::GeoViewport {
            crs: k.crs,
            center_x: f64::from_bits(k.center_x_bits),
            center_y: f64::from_bits(k.center_y_bits),
            zoom: f64::from_bits(k.zoom_bits),
            width: f64::from_bits(k.width_bits),
            height: f64::from_bits(k.height_bits),
            bearing_deg: f64::from_bits(k.bearing_deg_bits),
            pitch_deg: f64::from_bits(k.pitch_deg_bits),
            world_wrap: k.world_wrap,
        }
        .validate()?;
        let width = f64::from_bits(compiled.camera.width_bits);
        let height = f64::from_bits(compiled.camera.height_bits);
        if !finite(&[width, height]) || width <= 0. || height <= 0. {
            return Err(GeoError::InvalidArgument);
        }
        let total = compiled
            .layers
            .iter()
            .try_fold(0usize, |n, l| n.checked_add(l.feature_ids.len()))
            .ok_or(GeoError::ResourceLimit)?;
        if total > MAX_GEO_INTERACTION_ROWS
            || budget > 384 * 1024 * 1024
            || compiled
                .scene
                .len()
                .checked_mul(4)
                .and_then(|n| n.checked_add(total * 128 + GRID * GRID * 16 + 32768))
                .is_none_or(|n| n > budget)
        {
            return Err(GeoError::ResourceLimit);
        }
        let mut density_cells = 0usize;
        let mut density_members = 0usize;
        for layer in &compiled.layers {
            if let Some(d) = &layer.density {
                density_cells = density_cells
                    .checked_add(d.counts.len())
                    .ok_or(GeoError::ResourceLimit)?;
                density_members = density_members
                    .checked_add(d.feature_indices.len())
                    .ok_or(GeoError::ResourceLimit)?;
            }
        }
        if density_cells > 4_000_000 || density_members > MAX_GEO_INTERACTION_ROWS {
            return Err(GeoError::ResourceLimit);
        }
        if compiled.scene.len() * 4
            + total * 128
            + density_cells * 8
            + density_members * 4
            + GRID * GRID * 16
            + 32768
            > budget
        {
            return Err(GeoError::ResourceLimit);
        }
        let mut rows = Vec::new();
        let mut keyboard = Vec::new();
        if compiled.layers.len() > crate::geo_layers::MAX_GEO_LAYERS
            || compiled.layers.iter().enumerate().any(|(i, l)| {
                compiled.layers[..i]
                    .iter()
                    .any(|p| p.layer_id == l.layer_id)
            })
        {
            return Err(GeoError::InvalidArgument);
        }
        for layer in &compiled.layers {
            let n = layer.feature_ids.len();
            if layer.validity.len() != n
                || layer.state_flags.len() != n
                || layer.state_flags.iter().any(|f| f & !15 != 0)
                || layer.validity.iter().any(|v| *v > 1)
            {
                return Err(GeoError::InvalidArgument);
            }
            let mut sorted: Vec<_> = layer
                .feature_ids
                .iter()
                .enumerate()
                .filter(|(i, _)| {
                    layer.validity[*i] != 0 && layer.state_flags[*i] & GEO_STATE_HIDDEN == 0
                })
                .map(|(i, &id)| (id, i as u32))
                .collect();
            sorted.sort_unstable();
            let mut firsts: Vec<_> = sorted
                .chunk_by(|a, b| a.0 == b.0)
                .map(|group| (group[0].1, group[0].0))
                .collect();
            firsts.sort_unstable();
            keyboard.extend(firsts.into_iter().map(|(_, id)| GeoFeatureKey {
                layer_id: layer.layer_id,
                feature_id: id,
            }));
            rows.push(sorted);
            if let Some(d) = &layer.density {
                let cells = (d.columns as usize)
                    .checked_mul(d.rows as usize)
                    .ok_or(GeoError::ResourceLimit)?;
                if cells == 0
                    || d.offsets.len() != cells + 1
                    || d.counts.len() != cells
                    || d.offsets[0] != 0
                    || d.offsets.last().copied() != Some(d.feature_indices.len() as u32)
                    || d.offsets.windows(2).any(|w| w[0] > w[1])
                    || d.feature_indices.iter().any(|&r| {
                        r as usize >= n
                            || layer.validity[r as usize] == 0
                            || layer.state_flags[r as usize] & GEO_STATE_HIDDEN != 0
                    })
                {
                    return Err(GeoError::InvalidArgument);
                }
            }
        }
        let scene = SceneDocument::decode(&compiled.scene).map_err(err)?;
        let records = scene.interaction_records();
        let mut primitives = Vec::new();
        let mut cursor = 0;
        while cursor < records.len() {
            let record = records[cursor];
            let style = scene
                .interaction_style(record.style_ref)
                .ok_or(GeoError::InvalidArgument)?;
            let owner = compiled
                .style_owners
                .get(record.style_ref)
                .ok_or(GeoError::InvalidArgument)?;
            let advance = if record.kind == SceneRecordKind::Triangle {
                3
            } else if record.kind == SceneRecordKind::Segment {
                2
            } else {
                1
            };
            if let Some(owner) = owner {
                let layer = *owner as usize;
                if layer >= compiled.layers.len() {
                    return Err(GeoError::InvalidArgument);
                }
                let id = record.stable_id;
                if record.kind != SceneRecordKind::Image
                    && rows[layer].binary_search_by_key(&id, |r| r.0).is_err()
                {
                    return Err(GeoError::InvalidArgument);
                }
                if record.kind == SceneRecordKind::Image && id != compiled.layers[layer].layer_id {
                    return Err(GeoError::InvalidArgument);
                }
                let xy = record.coordinates;
                let shape = if !record.visible {
                    None
                } else {
                    match record.kind {
                        SceneRecordKind::Scatter
                            if record.diameter > 0. && (style.0[3] > 0 || style.1[3] > 0) =>
                        {
                            Some(Shape::Marker {
                                x: xy[0],
                                y: xy[1],
                                diameter: record.diameter,
                                symbol: record.symbol,
                                stroke: style.2,
                                fill: style.0[3] > 0,
                                outline: style.1[3] > 0,
                            })
                        }
                        SceneRecordKind::Polyline | SceneRecordKind::Segment
                            if style.1[3] > 0 && style.2 > 0. =>
                        {
                            records
                                .get(cursor + 1)
                                .filter(|r| {
                                    r.kind == record.kind
                                        && r.visible
                                        && r.stable_id == id
                                        && r.style_ref == record.style_ref
                                })
                                .map(|r| Shape::Segment {
                                    a: [xy[0], xy[1]],
                                    b: [r.coordinates[0], r.coordinates[1]],
                                    radius: style.2 / 2.,
                                })
                        }
                        SceneRecordKind::Triangle if style.0[3] > 0 => Some(Shape::Triangle([
                            xy[0],
                            xy[1],
                            records[cursor + 1].coordinates[0],
                            records[cursor + 1].coordinates[1],
                            records[cursor + 2].coordinates[0],
                            records[cursor + 2].coordinates[1],
                        ])),
                        SceneRecordKind::Image if compiled.layers[layer].density.is_some() => {
                            Some(Shape::Density)
                        }
                        _ => None,
                    }
                };
                if let Some(shape) = shape {
                    let b = match shape {
                        Shape::Marker {
                            x,
                            y,
                            diameter,
                            symbol,
                            stroke,
                            ..
                        } => {
                            let extent = scene::interaction_marker_extent(symbol, diameter, stroke);
                            [x - extent[0], y - extent[1], x + extent[0], y + extent[1]]
                        }
                        Shape::Segment { a, b, radius } => {
                            bounds(&[a[0], a[1], b[0], b[1]], radius)
                        }
                        Shape::Triangle(t) => bounds(&t, 0.),
                        Shape::Density => [0., 0., width, height],
                    };
                    if !finite(&b) {
                        return Err(GeoError::InvalidArgument);
                    }
                    if intersects(b, [0., 0., width, height]) {
                        if base_peak
                            .checked_add((primitives.len() + 1) * 256)
                            .is_none_or(|n| n > budget)
                        {
                            return Err(GeoError::ResourceLimit);
                        }
                        if primitives.len() >= MAX_GEO_PICK_PRIMITIVES {
                            return Err(GeoError::ResourceLimit);
                        }
                        primitives.push(Primitive {
                            layer,
                            id,
                            bounds: b,
                            shape,
                        });
                    }
                }
            }
            cursor += advance;
        }
        let mut counts = vec![0u32; GRID * GRID];
        let mut duplicates = 0usize;
        let cell_range = |b: [f64; 4]| {
            let cell = |v: f64, span: f64| {
                ((v / span * GRID as f64)
                    .floor()
                    .clamp(0., (GRID - 1) as f64)) as usize
            };
            [
                cell(b[0], width),
                cell(b[1], height),
                cell(b[2], width),
                cell(b[3], height),
            ]
        };
        for p in &primitives {
            let b = cell_range(p.bounds);
            let amount = (b[2] - b[0] + 1) * (b[3] - b[1] + 1);
            duplicates = duplicates
                .checked_add(amount)
                .ok_or(GeoError::ResourceLimit)?;
            if duplicates > MAX_GEO_PICK_GRID_ENTRIES {
                return Err(GeoError::ResourceLimit);
            }
            for y in b[1]..=b[3] {
                for x in b[0]..=b[2] {
                    counts[y * GRID + x] += 1;
                }
            }
        }
        let peak = base_peak
            .checked_add(primitives.len() * 256)
            .and_then(|n| n.checked_add(duplicates * 8))
            .ok_or(GeoError::ResourceLimit)?;
        if peak > budget {
            return Err(GeoError::ResourceLimit);
        }
        let mut offsets = vec![0u32; GRID * GRID + 1];
        for (i, n) in counts.iter().enumerate() {
            offsets[i + 1] = offsets[i] + n;
        }
        let mut next = offsets[..GRID * GRID].to_vec();
        let mut entries = vec![0u32; duplicates];
        for (i, p) in primitives.iter().enumerate() {
            let b = cell_range(p.bounds);
            for y in b[1]..=b[3] {
                for x in b[0]..=b[2] {
                    let cell = y * GRID + x;
                    entries[next[cell] as usize] = i as u32;
                    next[cell] += 1;
                }
            }
        }
        Ok(Self {
            compiled,
            scene,
            width,
            height,
            primitives,
            offsets,
            entries,
            rows,
            keyboard,
        })
    }
    fn rows_for(&self, key: GeoFeatureKey) -> Result<(usize, &[(u64, u32)]), GeoError> {
        let layer = self
            .compiled
            .layers
            .iter()
            .position(|l| l.layer_id == key.layer_id)
            .ok_or(GeoError::InvalidArgument)?;
        let rows = &self.rows[layer];
        let lo = rows.partition_point(|r| r.0 < key.feature_id);
        let hi = rows.partition_point(|r| r.0 <= key.feature_id);
        if lo == hi {
            return Err(GeoError::InvalidArgument);
        }
        Ok((layer, &rows[lo..hi]))
    }
    fn hit(&self, key: GeoFeatureKey) -> Result<GeoFeatureHit, GeoError> {
        let (_, rows) = self.rows_for(key)?;
        Ok(GeoFeatureHit {
            key,
            feature_indices: rows.iter().map(|r| r.1).collect(),
        })
    }
    pub fn companion(&self) -> Result<Vec<GeoFeatureHit>, GeoError> {
        self.keyboard.iter().map(|&k| self.hit(k)).collect()
    }
    pub fn initial_state(&self) -> GeoInteractionState {
        // Construction already admitted and validated this immutable metadata.
        GeoInteractionState::from_compiled(self.compiled).unwrap()
    }
    fn candidates(&self, b: [f64; 4]) -> Result<Vec<u32>, GeoError> {
        if !intersects(b, [0., 0., self.width, self.height]) {
            return Ok(Vec::new());
        }
        let cell =
            |v: f64, s: f64| ((v / s * GRID as f64).floor().clamp(0., (GRID - 1) as f64)) as usize;
        let mut out = Vec::new();
        for y in cell(b[1], self.height)..=cell(b[3], self.height) {
            for x in cell(b[0], self.width)..=cell(b[2], self.width) {
                let c = y * GRID + x;
                let slice = &self.entries[self.offsets[c] as usize..self.offsets[c + 1] as usize];
                if out.len() + slice.len() > MAX_GEO_PICK_GRID_ENTRIES {
                    return Err(GeoError::ResourceLimit);
                }
                out.extend_from_slice(slice);
            }
        }
        out.sort_unstable();
        out.dedup();
        if out.len() > MAX_GEO_PICK_CANDIDATES {
            return Err(GeoError::ResourceLimit);
        }
        Ok(out)
    }
    fn density_hits(
        &self,
        primitive: Primitive,
        b: [f64; 4],
    ) -> Result<Vec<GeoFeatureKey>, GeoError> {
        let layer = &self.compiled.layers[primitive.layer];
        let d = layer.density.as_ref().unwrap();
        let image = self
            .scene
            .interaction_image(primitive.id)
            .ok_or(GeoError::InvalidArgument)?;
        if image.width != d.columns || image.height != d.rows {
            return Err(GeoError::InvalidArgument);
        }
        let point = b[0] == b[2] && b[1] == b[3];
        let mut result = Vec::new();
        if point && (b[0] < 0. || b[0] >= self.width || b[1] < 0. || b[1] >= self.height) {
            return Ok(result);
        }
        let cell = |v: f64, span: f64, n: u32| {
            ((v / span * n as f64).floor().clamp(0., (n - 1) as f64)) as usize
        };
        let x0 = cell(b[0], self.width, d.columns);
        let x1 = cell(b[2], self.width, d.columns);
        let y0 = cell(b[1], self.height, d.rows);
        let y1 = cell(b[3], self.height, d.rows);
        for y in y0..=y1 {
            for x in x0..=x1 {
                let cell = y * d.columns as usize + x;
                if image.rgba[cell * 4 + 3] == 0 {
                    continue;
                }
                let x = cell % d.columns as usize;
                let y = cell / d.columns as usize;
                let rect = [
                    x as f64 * self.width / d.columns as f64,
                    y as f64 * self.height / d.rows as f64,
                    (x + 1) as f64 * self.width / d.columns as f64,
                    (y + 1) as f64 * self.height / d.rows as f64,
                ];
                if if point {
                    b[0] >= rect[0] && b[0] < rect[2] && b[1] >= rect[1] && b[1] < rect[3]
                } else {
                    intersects(b, rect)
                } {
                    for &row in
                        &d.feature_indices[d.offsets[cell] as usize..d.offsets[cell + 1] as usize]
                    {
                        if result.len() >= MAX_GEO_INTERACTION_ROWS {
                            return Err(GeoError::ResourceLimit);
                        }
                        result.push(GeoFeatureKey {
                            layer_id: layer.layer_id,
                            feature_id: layer.feature_ids[row as usize],
                        });
                    }
                }
            }
        }
        result.sort_unstable();
        result.dedup();
        Ok(result)
    }
    fn picks(&self, b: [f64; 4], point: bool) -> Result<Vec<GeoFeatureKey>, GeoError> {
        if !intersects(b, [0., 0., self.width, self.height]) {
            return Ok(Vec::new());
        }
        let b = if point {
            b
        } else {
            [
                b[0].max(0.),
                b[1].max(0.),
                b[2].min(self.width),
                b[3].min(self.height),
            ]
        };
        let candidates = self.candidates(b)?;
        let mut hits = Vec::new();
        let mut work = 0usize;
        for &i in candidates.iter().rev() {
            let p = self.primitives[i as usize];
            let charge = match p.shape {
                Shape::Marker { symbol, .. } if !point && matches!(symbol, 4 | 11 | 15..=18) => {
                    1024
                }
                _ => 20,
            };
            work += charge;
            if work > MAX_GEO_INTERACTION_WORK {
                return Err(GeoError::ResourceLimit);
            }
            if !intersects(p.bounds, b) {
                continue;
            }
            let hit = match p.shape {
                Shape::Density => {
                    let keys = self.density_hits(p, b)?;
                    if !keys.is_empty() {
                        hits.extend(keys);
                        if point {
                            break;
                        }
                    }
                    false
                }
                Shape::Marker {
                    x,
                    y,
                    diameter,
                    symbol,
                    stroke,
                    fill,
                    outline,
                } => {
                    if point {
                        scene::interaction_marker_hit(
                            symbol,
                            diameter,
                            stroke,
                            fill,
                            outline,
                            b[0] - x,
                            b[1] - y,
                        )
                    } else {
                        scene::interaction_marker_rect(
                            symbol,
                            diameter,
                            stroke,
                            fill,
                            outline,
                            [b[0] - x, b[1] - y, b[2] - x, b[3] - y],
                        )
                    }
                }
                Shape::Segment { a, b: to, radius } => {
                    if point {
                        distance([b[0], b[1]], a, to) <= radius
                    } else {
                        segment_rect_distance(a, to, b) <= radius
                    }
                }
                Shape::Triangle(t) => {
                    if point {
                        in_triangle([b[0], b[1]], t)
                    } else {
                        let corners = [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
                        corners.iter().any(|&c| in_triangle(c, t))
                            || [(0, 2), (2, 4), (4, 0)]
                                .iter()
                                .any(|&(a, c)| segment_rect([t[a], t[a + 1]], [t[c], t[c + 1]], b))
                    }
                }
            };
            if hit {
                let key = GeoFeatureKey {
                    layer_id: self.compiled.layers[p.layer].layer_id,
                    feature_id: p.id,
                };
                self.rows_for(key)?;
                hits.push(key);
                if point {
                    break;
                }
            }
        }
        if !point || hits.len() > 1 {
            hits.sort_unstable();
            hits.dedup();
            hits = self
                .keyboard
                .iter()
                .filter(|key| hits.binary_search(key).is_ok())
                .copied()
                .collect();
        }
        Ok(hits)
    }
    pub fn apply(
        &self,
        state: &GeoInteractionState,
        event: GeoInteractionEvent,
    ) -> Result<GeoInteractionResult, GeoError> {
        if state.layer_flags.len() != self.compiled.layers.len() {
            return Err(GeoError::InvalidArgument);
        }
        for (flags, layer) in state.layer_flags.iter().zip(&self.compiled.layers) {
            if flags.len() != layer.feature_ids.len()
                || flags
                    .iter()
                    .zip(&layer.state_flags)
                    .any(|(&a, &b)| a & !15 != 0 || (a ^ b) & GEO_STATE_HIDDEN != 0)
            {
                return Err(GeoError::InvalidArgument);
            }
        }
        if let Some(key) = state.focus {
            self.rows_for(key)?;
        }
        for (layer, metadata) in self.compiled.layers.iter().enumerate() {
            for row in 0..metadata.feature_ids.len() {
                let focused = state.focus
                    == Some(GeoFeatureKey {
                        layer_id: metadata.layer_id,
                        feature_id: metadata.feature_ids[row],
                    })
                    && metadata.validity[row] != 0
                    && metadata.state_flags[row] & GEO_STATE_HIDDEN == 0;
                if (state.layer_flags[layer][row] & GEO_STATE_FOCUSED != 0) != focused {
                    return Err(GeoError::InvalidArgument);
                }
            }
        }
        let (keys, mode) = match event {
            GeoInteractionEvent::Hover { x, y } | GeoInteractionEvent::SelectAt { x, y, .. } => {
                if !finite(&[x, y]) {
                    return Err(GeoError::InvalidArgument);
                }
                let mode = if let GeoInteractionEvent::SelectAt { mode, .. } = event {
                    Some(mode)
                } else {
                    None
                };
                (self.picks([x, y, x, y], true)?, mode)
            }
            GeoInteractionEvent::Brush { bounds, mode } => {
                if !finite(&bounds) || bounds[0] > bounds[2] || bounds[1] > bounds[3] {
                    return Err(GeoError::InvalidArgument);
                }
                (self.picks(bounds, false)?, Some(mode))
            }
            GeoInteractionEvent::SelectFeature { key, mode } => {
                self.rows_for(key)?;
                (vec![key], Some(mode))
            }
            GeoInteractionEvent::FocusFeature { key } => {
                self.rows_for(key)?;
                (vec![key], None)
            }
            GeoInteractionEvent::FocusStep { delta } => {
                if delta != 1 && delta != -1 {
                    return Err(GeoError::InvalidArgument);
                }
                let key = if self.keyboard.is_empty() {
                    None
                } else {
                    let index = state
                        .focus
                        .and_then(|k| self.keyboard.iter().position(|p| *p == k));
                    let next = match (index, delta) {
                        (Some(i), 1) => (i + 1) % self.keyboard.len(),
                        (Some(i), _) => (i + self.keyboard.len() - 1) % self.keyboard.len(),
                        (None, 1) => 0,
                        (None, _) => self.keyboard.len() - 1,
                    };
                    Some(self.keyboard[next])
                };
                (key.into_iter().collect(), None)
            }
            GeoInteractionEvent::Clear => (Vec::new(), None),
        };
        let hits: Vec<_> = keys
            .iter()
            .map(|&k| self.hit(k))
            .collect::<Result<_, _>>()?;
        let mut next = state.clone();
        if let Some(mode) = mode {
            if mode == GeoSelectionMode::Replace {
                for flags in &mut next.layer_flags {
                    for f in flags {
                        *f &= !GEO_STATE_SELECTED;
                    }
                }
            }
            for &key in &keys {
                let (layer, rows) = self.rows_for(key)?;
                let selected = rows
                    .iter()
                    .all(|r| next.layer_flags[layer][r.1 as usize] & GEO_STATE_SELECTED != 0);
                for r in rows {
                    let f = &mut next.layer_flags[layer][r.1 as usize];
                    if mode == GeoSelectionMode::Toggle && selected {
                        *f &= !GEO_STATE_SELECTED;
                    } else {
                        *f |= GEO_STATE_SELECTED;
                    }
                }
            }
        }
        match event {
            GeoInteractionEvent::Hover { .. } => {
                for flags in &mut next.layer_flags {
                    for f in flags {
                        *f &= !GEO_STATE_HOVERED;
                    }
                }
                for &key in &keys {
                    let (layer, rows) = self.rows_for(key)?;
                    for r in rows {
                        next.layer_flags[layer][r.1 as usize] |= GEO_STATE_HOVERED;
                    }
                }
            }
            GeoInteractionEvent::FocusStep { .. } | GeoInteractionEvent::FocusFeature { .. } => {
                for flags in &mut next.layer_flags {
                    for f in flags {
                        *f &= !GEO_STATE_FOCUSED;
                    }
                }
                next.focus = keys.first().copied();
                if let Some(key) = next.focus {
                    let (layer, rows) = self.rows_for(key)?;
                    for r in rows {
                        next.layer_flags[layer][r.1 as usize] |= GEO_STATE_FOCUSED;
                    }
                }
            }
            GeoInteractionEvent::Clear => {
                for flags in &mut next.layer_flags {
                    for f in flags {
                        *f &= GEO_STATE_HIDDEN;
                    }
                }
                next.focus = None;
            }
            _ => {}
        }
        Ok(GeoInteractionResult { state: next, hits })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo::{GeoColumn, GeoCrs, GeoDescriptor, GeoGeometry, GeoLimits};
    use crate::geo_layers::{self, GeoCatalog, GeoDensityOptions, GeoLayer, GeoLayerKind};
    use crate::geo_viewport::GeoViewport;
    fn camera() -> GeoViewport {
        GeoViewport {
            crs: GeoCrs::Epsg4326,
            center_x: 0.,
            center_y: 0.,
            zoom: 2.,
            width: 128.,
            height: 128.,
            bearing_deg: 0.,
            pitch_deg: 0.,
            world_wrap: true,
        }
    }
    fn source(
        kind: GeoGeometry,
        pixels: &[[f64; 2]],
        ids: &[u64],
        offsets: [&[u32]; 3],
    ) -> GeoColumn {
        let xy: Vec<_> = pixels
            .iter()
            .flat_map(|p| {
                let (x, y) = camera().unproject(p[0], p[1]).unwrap();
                [x, y]
            })
            .collect();
        GeoColumn::from_descriptor(GeoDescriptor {
            geometry: kind,
            crs: GeoCrs::Epsg4326,
            xy: &xy,
            validity: &vec![1; ids.len()],
            feature_ids: Some(ids),
            offsets0: offsets[0],
            offsets1: offsets[1],
            offsets2: offsets[2],
            limits: GeoLimits::default(),
        })
        .unwrap()
    }
    fn compiled(layers: &[GeoLayer<'_>]) -> GeoCompiled {
        geo_layers::compile(&GeoCatalog {
            viewport: camera(),
            layers,
            legend: None,
            budget: 64 << 20,
        })
        .unwrap()
    }
    fn key(layer_id: u64, feature_id: u64) -> GeoFeatureKey {
        GeoFeatureKey {
            layer_id,
            feature_id,
        }
    }
    #[test]
    fn paint_order_full_u64_identity_and_duplicate_row_union() {
        let first = source(
            GeoGeometry::Point,
            &[[64., 64.], [20., 20.]],
            &[u64::MAX, u64::MAX],
            [&[], &[], &[]],
        );
        let second = source(
            GeoGeometry::Point,
            &[[64., 64.]],
            &[0x5859_0100_0000_0001],
            [&[], &[], &[]],
        );
        let c = compiled(&[
            GeoLayer::new(u64::MAX, GeoLayerKind::Points, &first),
            GeoLayer::new(1, GeoLayerKind::Points, &second),
        ]);
        let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
        let state = index.initial_state();
        let out = index
            .apply(&state, GeoInteractionEvent::Hover { x: 64., y: 64. })
            .unwrap();
        assert_eq!(out.hits[0].key, key(1, 0x5859_0100_0000_0001));
        assert_eq!(out.state.layer_flags[1], [GEO_STATE_HOVERED]);
        let out = index
            .apply(
                &state,
                GeoInteractionEvent::SelectFeature {
                    key: key(u64::MAX, u64::MAX),
                    mode: GeoSelectionMode::Replace,
                },
            )
            .unwrap();
        assert_eq!(out.hits[0].feature_indices, [0, 1]);
        assert_eq!(
            out.state.layer_flags[0],
            [GEO_STATE_SELECTED, GEO_STATE_SELECTED]
        );
        let out = index
            .apply(
                &out.state,
                GeoInteractionEvent::SelectFeature {
                    key: key(u64::MAX, u64::MAX),
                    mode: GeoSelectionMode::Toggle,
                },
            )
            .unwrap();
        assert_eq!(out.state.layer_flags[0], [0, 0]);
    }
    #[test]
    fn keyboard_and_companion_include_offscreen_but_exclude_hidden() {
        let source = source(
            GeoGeometry::Point,
            &[[20., 20.], [40., 40.], [300., 60.]],
            &[10, 20, u64::MAX],
            [&[], &[], &[]],
        );
        let mut layer = GeoLayer::new(3, GeoLayerKind::Points, &source);
        layer.state_flags = &[0, GEO_STATE_HIDDEN, 0];
        let c = compiled(&[layer]);
        let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
        assert_eq!(
            index
                .companion()
                .unwrap()
                .iter()
                .map(|h| h.key)
                .collect::<Vec<_>>(),
            [key(3, 10), key(3, u64::MAX)]
        );
        let first = index
            .apply(
                &index.initial_state(),
                GeoInteractionEvent::FocusStep { delta: 1 },
            )
            .unwrap();
        assert_eq!(first.state.focus, Some(key(3, 10)));
        let second = index
            .apply(&first.state, GeoInteractionEvent::FocusStep { delta: 1 })
            .unwrap();
        assert_eq!(second.state.focus, Some(key(3, u64::MAX)));
        assert_eq!(
            second.state.layer_flags[0],
            [0, GEO_STATE_HIDDEN, GEO_STATE_FOCUSED]
        );
        let selected = index
            .apply(
                &second.state,
                GeoInteractionEvent::SelectFeature {
                    key: key(3, u64::MAX),
                    mode: GeoSelectionMode::Add,
                },
            )
            .unwrap();
        assert_eq!(
            selected.state.layer_flags[0][2],
            GEO_STATE_FOCUSED | GEO_STATE_SELECTED
        );
        let cleared = index
            .apply(&selected.state, GeoInteractionEvent::Clear)
            .unwrap();
        assert_eq!(cleared.state.layer_flags[0], [0, GEO_STATE_HIDDEN, 0]);
        assert_eq!(cleared.state.focus, None);
    }
    #[test]
    fn polygon_hole_and_brush_use_actual_triangles_not_bounding_box() {
        let polygon = source(
            GeoGeometry::Polygon,
            &[
                [10., 10.],
                [110., 10.],
                [110., 110.],
                [10., 110.],
                [10., 10.],
                [40., 40.],
                [80., 40.],
                [80., 80.],
                [40., 80.],
                [40., 40.],
            ],
            &[u64::MAX],
            [&[0, 2], &[0, 5, 10], &[]],
        );
        let mut layer = GeoLayer::new(7, GeoLayerKind::Polygons, &polygon);
        layer.style.stroke_width = 0.;
        let c = compiled(&[layer]);
        let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
        let state = index.initial_state();
        assert!(index
            .apply(&state, GeoInteractionEvent::Hover { x: 60., y: 60. })
            .unwrap()
            .hits
            .is_empty());
        assert_eq!(
            index
                .apply(&state, GeoInteractionEvent::Hover { x: 20., y: 20. })
                .unwrap()
                .hits[0]
                .key,
            key(7, u64::MAX)
        );
        assert!(index
            .apply(
                &state,
                GeoInteractionEvent::Brush {
                    bounds: [50., 50., 70., 70.],
                    mode: GeoSelectionMode::Replace
                }
            )
            .unwrap()
            .hits
            .is_empty());
        let out = index
            .apply(
                &state,
                GeoInteractionEvent::Brush {
                    bounds: [35., 35., 45., 45.],
                    mode: GeoSelectionMode::Replace,
                },
            )
            .unwrap();
        assert_eq!(out.hits[0].key, key(7, u64::MAX));
    }
    #[test]
    fn route_distance_and_multipart_gap_are_exact() {
        let line = source(
            GeoGeometry::MultiLineString,
            &[[10., 30.], [40., 30.], [90., 30.], [110., 30.]],
            &[99],
            [&[0, 2], &[0, 2, 4], &[]],
        );
        let mut layer = GeoLayer::new(9, GeoLayerKind::Routes, &line);
        layer.style.stroke_width = 4.;
        let c = compiled(&[layer]);
        let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
        let state = index.initial_state();
        assert_eq!(
            index
                .apply(&state, GeoInteractionEvent::Hover { x: 20., y: 31. })
                .unwrap()
                .hits[0]
                .key,
            key(9, 99)
        );
        assert!(index
            .apply(&state, GeoInteractionEvent::Hover { x: 20., y: 33. })
            .unwrap()
            .hits
            .is_empty());
        assert!(index
            .apply(&state, GeoInteractionEvent::Hover { x: 60., y: 30. })
            .unwrap()
            .hits
            .is_empty());
        assert!(index
            .apply(
                &state,
                GeoInteractionEvent::Brush {
                    bounds: [55., 28., 65., 32.],
                    mode: GeoSelectionMode::Add
                }
            )
            .unwrap()
            .hits
            .is_empty());
    }
    #[test]
    fn density_pick_returns_complete_bin_membership_and_brush_union() {
        let points = source(
            GeoGeometry::Point,
            &[[10., 10.], [10., 10.], [100., 100.]],
            &[u64::MAX, 2, 3],
            [&[], &[], &[]],
        );
        let mut layer = GeoLayer::new(9, GeoLayerKind::Density, &points);
        layer.density = GeoDensityOptions {
            columns: 2,
            rows: 2,
        };
        let c = compiled(&[layer]);
        let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
        let state = index.initial_state();
        let out = index
            .apply(
                &state,
                GeoInteractionEvent::SelectAt {
                    x: 20.,
                    y: 20.,
                    mode: GeoSelectionMode::Replace,
                },
            )
            .unwrap();
        assert_eq!(
            out.hits
                .iter()
                .map(|h| h.key.feature_id)
                .collect::<Vec<_>>(),
            [u64::MAX, 2]
        );
        assert_eq!(out.state.layer_flags[0], [2, 2, 0]);
        let out = index
            .apply(
                &out.state,
                GeoInteractionEvent::Brush {
                    bounds: [80., 80., 120., 120.],
                    mode: GeoSelectionMode::Add,
                },
            )
            .unwrap();
        assert_eq!(out.state.layer_flags[0], [2, 2, 2]);
        assert!(index
            .apply(&state, GeoInteractionEvent::Hover { x: 100., y: 20. })
            .unwrap()
            .hits
            .is_empty());
        assert!(index
            .apply(&state, GeoInteractionEvent::Hover { x: 128., y: 100. })
            .unwrap()
            .hits
            .is_empty());
    }
    #[test]
    fn zero_alpha_and_zero_size_are_not_pickable() {
        let points = source(GeoGeometry::Point, &[[64., 64.]], &[1], [&[], &[], &[]]);
        let mut layer = GeoLayer::new(1, GeoLayerKind::Points, &points);
        layer.style.opacity = 0.;
        let c = compiled(&[layer]);
        let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
        assert!(index
            .apply(
                &index.initial_state(),
                GeoInteractionEvent::Hover { x: 64., y: 64. }
            )
            .unwrap()
            .hits
            .is_empty());
        let mut layer = GeoLayer::new(1, GeoLayerKind::Density, &points);
        layer.style.opacity = 0.;
        layer.density = GeoDensityOptions {
            columns: 1,
            rows: 1,
        };
        let c = compiled(&[layer]);
        let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
        assert!(index
            .apply(
                &index.initial_state(),
                GeoInteractionEvent::Hover { x: 64., y: 64. }
            )
            .unwrap()
            .hits
            .is_empty());
    }
    #[test]
    fn grid_duplication_is_admitted_before_entry_allocation() {
        let ids: Vec<_> = (0..257).collect();
        let points = source(
            GeoGeometry::Point,
            &vec![[64., 64.]; 257],
            &ids,
            [&[], &[], &[]],
        );
        let mut layer = GeoLayer::new(1, GeoLayerKind::Points, &points);
        layer.style.diameter = 256.;
        let c = compiled(&[layer]);
        assert!(matches!(
            GeoPickIndex::new(&c, 64 << 20),
            Err(GeoError::ResourceLimit)
        ));
    }
    #[test]
    fn circle_and_hollow_marker_brush_use_shape_not_extent_box() {
        let points = source(GeoGeometry::Point, &[[64., 64.]], &[1], [&[], &[], &[]]);
        let mut layer = GeoLayer::new(1, GeoLayerKind::Points, &points);
        layer.style.diameter = 20.;
        layer.style.stroke_width = 0.;
        let c = compiled(&[layer]);
        let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
        let state = index.initial_state();
        assert!(index
            .apply(
                &state,
                GeoInteractionEvent::Brush {
                    bounds: [72., 72., 73., 73.],
                    mode: GeoSelectionMode::Add
                }
            )
            .unwrap()
            .hits
            .is_empty());
        let mut layer = GeoLayer::new(1, GeoLayerKind::Points, &points);
        layer.style.diameter = 20.;
        layer.style.fill = [0; 4];
        layer.style.stroke_width = 2.;
        let c = compiled(&[layer]);
        let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
        assert!(index
            .apply(
                &index.initial_state(),
                GeoInteractionEvent::Hover { x: 64., y: 64. }
            )
            .unwrap()
            .hits
            .is_empty());
        assert!(index
            .apply(
                &index.initial_state(),
                GeoInteractionEvent::Brush {
                    bounds: [62., 62., 66., 66.],
                    mode: GeoSelectionMode::Add
                }
            )
            .unwrap()
            .hits
            .is_empty());
        assert_eq!(
            index
                .apply(
                    &index.initial_state(),
                    GeoInteractionEvent::Hover { x: 73., y: 64. }
                )
                .unwrap()
                .hits[0]
                .key,
            key(1, 1)
        );
    }
    #[test]
    fn nineteen_default_symbols_and_transparent_line_strokes_follow_paint_policy() {
        let points = source(GeoGeometry::Point, &[[64., 64.]], &[1], [&[], &[], &[]]);
        for symbol in 0..=18 {
            let mut layer = GeoLayer::new(1, GeoLayerKind::Points, &points);
            layer.style.diameter = 20.;
            layer.style.symbol = symbol;
            let c = compiled(&[layer]);
            let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
            assert_eq!(
                index
                    .apply(
                        &index.initial_state(),
                        GeoInteractionEvent::Hover { x: 64., y: 64. }
                    )
                    .unwrap()
                    .hits
                    .len(),
                1,
                "symbol={symbol}"
            );
        }
        for symbol in 15..=18 {
            let mut layer = GeoLayer::new(1, GeoLayerKind::Points, &points);
            layer.style.symbol = symbol;
            layer.style.stroke_width = 0.;
            layer.style.stroke = [0; 4];
            let c = compiled(&[layer]);
            let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
            assert!(index
                .apply(
                    &index.initial_state(),
                    GeoInteractionEvent::Hover { x: 64., y: 64. }
                )
                .unwrap()
                .hits
                .is_empty());
        }
    }
    #[test]
    fn hexagon_tip_is_inside_shared_clip_and_pick_extents() {
        let points = source(GeoGeometry::Point, &[[64., 64.]], &[1], [&[], &[], &[]]);
        let mut layer = GeoLayer::new(1, GeoLayerKind::Points, &points);
        layer.style.diameter = 20.;
        layer.style.symbol = 5;
        layer.style.stroke_width = 0.;
        let c = compiled(&[layer]);
        let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
        assert_eq!(
            index
                .apply(
                    &index.initial_state(),
                    GeoInteractionEvent::Hover { x: 64., y: 53. }
                )
                .unwrap()
                .hits
                .len(),
            1
        );
        assert!((scene::marker_symbol_extent(10., 5) - 20. / 3f64.sqrt()).abs() < 1e-12);
        assert_eq!(
            scene::interaction_marker_extent(5, 20., 0.),
            [10., 20. / 3f64.sqrt()]
        );
    }
    #[test]
    fn invalid_events_state_and_budget_fail_without_mutation() {
        let points = source(GeoGeometry::Point, &[[64., 64.]], &[1], [&[], &[], &[]]);
        let c = compiled(&[GeoLayer::new(1, GeoLayerKind::Points, &points)]);
        let index = GeoPickIndex::new(&c, 64 << 20).unwrap();
        let state = index.initial_state();
        let before = state.clone();
        for event in [
            GeoInteractionEvent::Hover { x: f64::NAN, y: 0. },
            GeoInteractionEvent::Brush {
                bounds: [2., 0., 1., 1.],
                mode: GeoSelectionMode::Replace,
            },
            GeoInteractionEvent::FocusStep { delta: 0 },
            GeoInteractionEvent::FocusFeature { key: key(1, 2) },
            GeoInteractionEvent::SelectFeature {
                key: key(9, 1),
                mode: GeoSelectionMode::Add,
            },
        ] {
            assert_eq!(
                index.apply(&state, event).unwrap_err(),
                GeoError::InvalidArgument
            );
            assert_eq!(state, before);
        }
        let mut invalid = state.clone();
        invalid.layer_flags[0][0] |= GEO_STATE_HIDDEN;
        assert_eq!(
            index
                .apply(&invalid, GeoInteractionEvent::Clear)
                .unwrap_err(),
            GeoError::InvalidArgument
        );
        assert!(matches!(
            GeoPickIndex::new(&c, 32768),
            Err(GeoError::ResourceLimit)
        ));
    }
}
