//! Certified, conservative source-index reduction before geographic tessellation.
//! See spec/design/geo-simplification.md. Source f64 planes are never changed.
use crate::geo::{GeoColumn, GeoCrs, GeoError, GeoGeometry};
use crate::geo_fill::{MAX_FILL_EDGES, MAX_FILL_WORK};
use crate::geo_viewport::{GeoViewport, GeoViewportRebuildKey};
use std::ops::Range;

pub const DEFAULT_TOLERANCE_PX: f64 = 0.5;
pub const MAX_SIMPLIFY_BYTES: usize = 128 * 1024 * 1024;

/// Allocation-free admission for materialization and simultaneous reduction scratch.
pub fn materialization_bytes(source: &GeoColumn) -> Result<usize, SimplifyError> {
    source
        .vertex_count()
        .checked_mul(192)
        .and_then(|n| source.len().checked_mul(128).and_then(|v| n.checked_add(v)))
        .and_then(|n| {
            [source.offsets0(), source.offsets1(), source.offsets2()]
                .iter()
                .try_fold(n, |a, o| {
                    o.len().checked_mul(512).and_then(|v| a.checked_add(v))
                })
        })
        .and_then(|n| n.checked_add(32768))
        .ok_or(SimplifyError::ResourceLimit)
}

/// Materialize certified source indices into the same canonical geometry
/// schema consumed by the shared clip/tessellation/catalog path. Feature rows,
/// full IDs and outer topology remain unchanged, so row style/state planes
/// retain their original alignment. A coordinator must lease this budget.
pub fn simplify_column<F: FnMut() -> bool>(
    source: &GeoColumn,
    camera: &GeoViewport,
    options: SimplifyOptions,
    cancelled: &mut F,
) -> Result<(SimplifiedGeo, GeoColumn), SimplifyError> {
    let peak = materialization_bytes(source)?;
    if peak > options.max_bytes {
        return Err(SimplifyError::ResourceLimit);
    }
    let mut result = simplify(source, camera, options, cancelled)?;
    result.admitted_bytes = peak;
    if source.geometry() == GeoGeometry::Point {
        if cancelled() {
            return Err(SimplifyError::Cancelled);
        }
        let column = source.clone();
        if cancelled() {
            return Err(SimplifyError::Cancelled);
        }
        return Ok((result, column));
    }
    let mut offsets0 = source.offsets0().to_vec();
    let mut offsets1 = source.offsets1().to_vec();
    let mut offsets2 = source.offsets2().to_vec();
    let leaf = match source.geometry() {
        GeoGeometry::MultiPoint | GeoGeometry::LineString => &mut offsets0,
        GeoGeometry::Polygon | GeoGeometry::MultiLineString => &mut offsets1,
        GeoGeometry::MultiPolygon => &mut offsets2,
        GeoGeometry::Point => unreachable!(),
    };
    let mut lengths = vec![0u32; leaf.len().saturating_sub(1)];
    let vertices = result.parts.iter().map(|p| p.vertices.len()).sum::<usize>();
    let mut xy = Vec::with_capacity(vertices * 2);
    for part in &result.parts {
        if cancelled() {
            return Err(SimplifyError::Cancelled);
        }
        lengths[part.part_index as usize] = part.vertices.len() as u32;
        for &index in &part.vertices {
            xy.extend_from_slice(&source.xy()[index as usize * 2..index as usize * 2 + 2]);
        }
    }
    leaf[0] = 0;
    for (i, len) in lengths.into_iter().enumerate() {
        leaf[i + 1] = leaf[i]
            .checked_add(len)
            .ok_or(SimplifyError::ResourceLimit)?;
    }
    let column = GeoColumn::from_descriptor(crate::geo::GeoDescriptor {
        geometry: source.geometry(),
        crs: source.crs(),
        xy: &xy,
        validity: source.validity(),
        feature_ids: Some(source.feature_ids()),
        offsets0: &offsets0,
        offsets1: &offsets1,
        offsets2: &offsets2,
        limits: crate::geo::GeoLimits {
            max_bytes: options.max_bytes,
            ..crate::geo::GeoLimits::default()
        },
    })?;
    if cancelled() {
        return Err(SimplifyError::Cancelled);
    }
    Ok((result, column))
}

#[derive(Debug, Clone, Copy)]
pub struct SimplifyOptions {
    /// Explicit CSS-pixel error bound, in (0, 0.5]. Zero is not an implicit disable.
    pub tolerance_px: f64,
    /// Includes live borrowed source planes, metadata, output and simultaneous scratch.
    pub max_bytes: usize,
    /// Projection, distance, orientation and containment edge visits are charged.
    pub max_edge_visits: usize,
}
impl Default for SimplifyOptions {
    fn default() -> Self {
        Self {
            tolerance_px: DEFAULT_TOLERANCE_PX,
            max_bytes: MAX_SIMPLIFY_BYTES,
            max_edge_visits: MAX_FILL_WORK,
        }
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SimplifyError {
    Geo(GeoError),
    InvalidOptions,
    ResourceLimit,
    Cancelled,
}
impl From<GeoError> for SimplifyError {
    fn from(value: GeoError) -> Self {
        Self::Geo(value)
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FallbackReason {
    Unchanged,
    Points,
    ProjectionBoundary,
    WorldSeam,
    TopologyUncertified,
    TopologyWorkLimit,
}
#[derive(Debug, Clone, PartialEq)]
pub struct SimplifiedPart {
    pub feature_index: u32,
    /// Original global polygon index; None for point/line geometry.
    pub polygon_index: Option<u32>,
    /// Original global ring/line/point-part index (not a newly assigned ID).
    pub part_index: u32,
    pub is_hole: bool,
    pub original_vertices: Range<u32>,
    /// Strictly source-ordered global vertex indices; rings retain the closing vertex.
    pub vertices: Vec<u32>,
    pub fallback: FallbackReason,
    pub max_error_px: f64,
}
#[derive(Debug, Clone, PartialEq)]
pub struct SimplifiedGeo {
    pub source_digest: [u8; 8],
    pub camera: GeoViewportRebuildKey,
    pub geometry: GeoGeometry,
    pub feature_ids: Vec<u64>,
    pub validity: Vec<u8>,
    pub parts: Vec<SimplifiedPart>,
    pub tolerance_px: f64,
    pub max_error_px: f64,
    pub edge_visits: usize,
    pub admitted_bytes: usize,
}
struct Work<'a, F> {
    visits: usize,
    limit: usize,
    cancelled: &'a mut F,
}
impl<F: FnMut() -> bool> Work<'_, F> {
    fn tick(&mut self) -> Result<(), SimplifyError> {
        if (self.cancelled)() {
            return Err(SimplifyError::Cancelled);
        }
        self.visits = self
            .visits
            .checked_add(1)
            .ok_or(SimplifyError::ResourceLimit)?;
        if self.visits > self.limit {
            return Err(SimplifyError::ResourceLimit);
        }
        Ok(())
    }
}
type Point = [f64; 2];

/// Return an index cache, never a replacement canonical column. The callback returns
/// true to cancel. Errors publish no partial result. Null features have no parts;
/// their original ID/validity remain in the result. Hidden/state policy is the caller's.
pub fn simplify<F: FnMut() -> bool>(
    source: &GeoColumn,
    camera: &GeoViewport,
    options: SimplifyOptions,
    cancelled: &mut F,
) -> Result<SimplifiedGeo, SimplifyError> {
    if !options.tolerance_px.is_finite()
        || options.tolerance_px <= 0.0
        || options.tolerance_px > DEFAULT_TOLERANCE_PX
        || options.max_bytes > MAX_SIMPLIFY_BYTES
        || options.max_edge_visits == 0
    {
        return Err(SimplifyError::InvalidOptions);
    }
    let key = camera.rebuild_key()?;
    if camera.crs != source.crs() {
        return Err(GeoError::InvalidArgument.into());
    }
    let n = source.vertex_count();
    let part_count = match source.geometry() {
        GeoGeometry::Point => source.len(),
        GeoGeometry::MultiPoint | GeoGeometry::LineString => {
            source.offsets0().len().saturating_sub(1)
        }
        GeoGeometry::Polygon | GeoGeometry::MultiLineString => {
            source.offsets1().len().saturating_sub(1)
        }
        GeoGeometry::MultiPolygon => source.offsets2().len().saturating_sub(1),
    };
    // Worst-case original result + projected f64 + candidate + keep + RDP stack,
    // borrowed canonical planes, GeoColumn metadata/digest cache and allocator slack.
    let bytes = n
        .checked_mul(96)
        .and_then(|v| part_count.checked_mul(256).and_then(|p| v.checked_add(p)))
        .and_then(|v| source.len().checked_mul(64).and_then(|f| v.checked_add(f)))
        .and_then(|v| {
            [source.offsets0(), source.offsets1(), source.offsets2()]
                .iter()
                .try_fold(v, |s, o| {
                    o.len().checked_mul(16).and_then(|b| s.checked_add(b))
                })
        })
        .and_then(|v| v.checked_add(16 * 1024))
        .ok_or(SimplifyError::ResourceLimit)?;
    if bytes > options.max_bytes || n > u32::MAX as usize {
        return Err(SimplifyError::ResourceLimit);
    }
    let mut work = Work {
        visits: 0,
        limit: options.max_edge_visits,
        cancelled,
    };
    work.tick()?;
    let mut parts = Vec::with_capacity(part_count);
    let mut point_vertex = 0usize;
    for feature in 0..source.len() {
        work.tick()?;
        if source.validity()[feature] == 0 {
            continue;
        }
        let o0 = source.offsets0();
        let o1 = source.offsets1();
        let o2 = source.offsets2();
        match source.geometry() {
            GeoGeometry::Point => {
                add(
                    &mut parts,
                    &mut work,
                    feature,
                    None,
                    feature,
                    false,
                    point_vertex,
                    point_vertex + 1,
                )?;
                point_vertex += 1;
            }
            GeoGeometry::MultiPoint | GeoGeometry::LineString => add(
                &mut parts,
                &mut work,
                feature,
                None,
                feature,
                false,
                o0[feature] as usize,
                o0[feature + 1] as usize,
            )?,
            GeoGeometry::MultiLineString => {
                for p in o0[feature] as usize..o0[feature + 1] as usize {
                    add(
                        &mut parts,
                        &mut work,
                        feature,
                        None,
                        p,
                        false,
                        o1[p] as usize,
                        o1[p + 1] as usize,
                    )?;
                }
            }
            GeoGeometry::Polygon => {
                for r in o0[feature] as usize..o0[feature + 1] as usize {
                    add(
                        &mut parts,
                        &mut work,
                        feature,
                        Some(feature),
                        r,
                        r != o0[feature] as usize,
                        o1[r] as usize,
                        o1[r + 1] as usize,
                    )?;
                }
            }
            GeoGeometry::MultiPolygon => {
                for p in o0[feature] as usize..o0[feature + 1] as usize {
                    for r in o1[p] as usize..o1[p + 1] as usize {
                        add(
                            &mut parts,
                            &mut work,
                            feature,
                            Some(p),
                            r,
                            r != o1[p] as usize,
                            o2[r] as usize,
                            o2[r + 1] as usize,
                        )?;
                    }
                }
            }
        }
    }
    if matches!(
        source.geometry(),
        GeoGeometry::Point | GeoGeometry::MultiPoint
    ) {
        for part in &mut parts {
            part.fallback = FallbackReason::Points;
        }
    } else {
        let mut projected = Vec::with_capacity(n);
        for xy in source.xy().chunks_exact(2) {
            work.tick()?;
            let (x, y) = camera.project(xy[0], xy[1])?;
            projected.push([x, y]);
        }
        let mut start = 0;
        while start < parts.len() {
            let mut end = start + 1;
            if parts[start].polygon_index.is_some()
                || source.geometry() == GeoGeometry::MultiLineString
            {
                while end < parts.len() && parts[end].feature_index == parts[start].feature_index {
                    end += 1;
                }
            }
            reduce_group(
                &mut parts[start..end],
                &projected,
                source,
                camera,
                options.tolerance_px,
                &mut work,
            )?;
            start = end;
        }
    }
    work.tick()?;
    let max_error_px = parts.iter().map(|p| p.max_error_px).fold(0.0, f64::max);
    let source_digest = source.metadata_digest();
    work.tick()?;
    Ok(SimplifiedGeo {
        source_digest,
        camera: key,
        geometry: source.geometry(),
        feature_ids: source.feature_ids().to_vec(),
        validity: source.validity().to_vec(),
        parts,
        tolerance_px: options.tolerance_px,
        max_error_px,
        edge_visits: work.visits,
        admitted_bytes: bytes,
    })
}

fn add<F: FnMut() -> bool>(
    parts: &mut Vec<SimplifiedPart>,
    work: &mut Work<'_, F>,
    feature: usize,
    polygon: Option<usize>,
    part: usize,
    hole: bool,
    a: usize,
    b: usize,
) -> Result<(), SimplifyError> {
    if a == b {
        return Ok(());
    }
    let mut vertices = Vec::with_capacity(b - a);
    for i in a..b {
        work.tick()?;
        vertices.push(i as u32);
    }
    parts.push(SimplifiedPart {
        feature_index: feature as u32,
        polygon_index: polygon.map(|v| v as u32),
        part_index: part as u32,
        is_hole: hole,
        original_vertices: a as u32..b as u32,
        vertices,
        fallback: FallbackReason::Unchanged,
        max_error_px: 0.0,
    });
    Ok(())
}

fn fallback<F: FnMut() -> bool>(
    parts: &mut [SimplifiedPart],
    reason: FallbackReason,
    work: &mut Work<'_, F>,
) -> Result<(), SimplifyError> {
    for p in parts {
        let mut vertices = Vec::with_capacity(p.original_vertices.len());
        for i in p.original_vertices.clone() {
            work.tick()?;
            vertices.push(i);
        }
        p.vertices = vertices;
        p.fallback = reason;
        p.max_error_px = 0.0;
    }
    Ok(())
}
fn reduce_group<F: FnMut() -> bool>(
    parts: &mut [SimplifiedPart],
    projected: &[Point],
    source: &GeoColumn,
    camera: &GeoViewport,
    tolerance: f64,
    work: &mut Work<'_, F>,
) -> Result<(), SimplifyError> {
    // Every source edge must stay on a single world copy and wholly inside the
    // convex front frustum. Boundary/near-plane/clip cases keep the exact source.
    let period = match source.crs() {
        GeoCrs::Epsg4326 => 360.0,
        GeoCrs::Epsg3857 => 40_075_016.685_578_49,
    };
    for part in parts.iter() {
        for i in part.original_vertices.clone() {
            work.tick()?;
            let [x, y] = projected[i as usize];
            if !x.is_finite()
                || !y.is_finite()
                || x <= tolerance
                || y <= tolerance
                || x >= camera.width - tolerance
                || y >= camera.height - tolerance
            {
                fallback(parts, FallbackReason::ProjectionBoundary, work)?;
                return Ok(());
            }
            let d = camera.camera_distance();
            let (sin, cos) = camera.pitch_deg.to_radians().sin_cos();
            let denominator = d * cos + (y - camera.height * 0.5) * sin;
            let depth = d - (y - camera.height * 0.5) * d / denominator * sin;
            let (near, far) = camera.depth_range();
            if !depth.is_finite() || depth <= near || depth >= far {
                fallback(parts, FallbackReason::ProjectionBoundary, work)?;
                return Ok(());
            }
            if i + 1 < part.original_vertices.end {
                let a = source.xy()[i as usize * 2];
                let b = source.xy()[(i as usize + 1) * 2];
                let wrap =
                    |v: f64| (v - camera.center_x + period * 0.5).rem_euclid(period) - period * 0.5;
                if (b - a).abs() >= period * 0.5
                    || (camera.world_wrap && (wrap(b) - wrap(a)).abs() >= period * 0.5)
                {
                    fallback(parts, FallbackReason::WorldSeam, work)?;
                    return Ok(());
                }
            }
        }
    }
    let polygon = parts[0].polygon_index.is_some();
    if polygon {
        let edges: usize = parts.iter().map(|p| p.vertices.len() - 1).sum();
        // Two full topology certificates plus shortened-chord/source comparisons.
        // Conservative early fallback avoids allocating quadratic work lists.
        let estimate = edges.checked_mul(edges).and_then(|n| n.checked_mul(4));
        if edges > MAX_FILL_EDGES
            || estimate
                .is_none_or(|n| n > MAX_FILL_WORK || n > work.limit.saturating_sub(work.visits))
        {
            fallback(parts, FallbackReason::TopologyWorkLimit, work)?;
            return Ok(());
        }
        if !topology(parts, projected, work)? {
            fallback(parts, FallbackReason::TopologyUncertified, work)?;
            return Ok(());
        }
    }
    for part in parts.iter_mut() {
        let original = part.original_vertices.clone();
        part.vertices = rdp(original.clone(), projected, tolerance, polygon, work)?;
        if polygon && part.vertices.len() < 4 {
            fallback(parts, FallbackReason::TopologyUncertified, work)?;
            return Ok(());
        }
    }
    if polygon && !topology(parts, projected, work)? {
        fallback(parts, FallbackReason::TopologyUncertified, work)?;
        return Ok(());
    }
    // A new chord must not cross any retained/original edge outside its span.
    // This also protects hole boundaries and prevents new route self crossings.
    for part in parts.iter() {
        for pair in part.vertices.windows(2) {
            let (a, b) = (pair[0], pair[1]);
            if b == a + 1 {
                continue;
            }
            for other in parts.iter() {
                for e in other.original_vertices.start..other.original_vertices.end - 1 {
                    work.tick()?;
                    if other.part_index == part.part_index && e >= a && e < b {
                        continue;
                    }
                    if same_point(projected[e as usize], projected[a as usize])
                        || same_point(projected[(e + 1) as usize], projected[a as usize])
                        || same_point(projected[e as usize], projected[b as usize])
                        || same_point(projected[(e + 1) as usize], projected[b as usize])
                    {
                        continue;
                    }
                    if intersects(
                        projected[a as usize],
                        projected[b as usize],
                        projected[e as usize],
                        projected[(e + 1) as usize],
                    ) {
                        fallback(parts, FallbackReason::TopologyUncertified, work)?;
                        return Ok(());
                    }
                }
            }
        }
    }
    if polygon {
        for part in parts.iter() {
            let original: Vec<u32> = part.original_vertices.clone().collect();
            if area(&original, projected).signum() != area(&part.vertices, projected).signum() {
                fallback(parts, FallbackReason::TopologyUncertified, work)?;
                return Ok(());
            }
        }
    }
    for part in parts {
        // Independently certify every original vertex against its owning reduced
        // segment, including all vertices discarded by RDP and the closing span.
        let mut error: f64 = 0.0;
        for pair in part.vertices.windows(2) {
            for i in pair[0]..=pair[1] {
                work.tick()?;
                error = error.max(distance(
                    projected[i as usize],
                    projected[pair[0] as usize],
                    projected[pair[1] as usize],
                ));
            }
        }
        if !error.is_finite() || error > tolerance {
            return Err(SimplifyError::ResourceLimit);
        }
        part.max_error_px = error;
    }
    Ok(())
}
fn rdp<F: FnMut() -> bool>(
    range: Range<u32>,
    points: &[Point],
    tolerance: f64,
    closed: bool,
    work: &mut Work<'_, F>,
) -> Result<Vec<u32>, SimplifyError> {
    let a = range.start as usize;
    let b = range.end as usize - 1;
    let mut keep = vec![false; b - a + 1];
    keep[0] = true;
    keep[b - a] = true;
    let mut stack = Vec::with_capacity(b - a + 1);
    if closed {
        let mut far = a + 1;
        let mut far_dist = 0.0;
        for i in a + 1..b {
            work.tick()?;
            let d = distance(points[i], points[a], points[a]);
            if d > far_dist {
                far = i;
                far_dist = d;
            }
        }
        keep[far - a] = true;
        stack.push((far, b));
        stack.push((a, far));
    } else {
        stack.push((a, b));
    }
    while let Some((left, right)) = stack.pop() {
        let mut far = left;
        let mut maximum = tolerance;
        for i in left + 1..right {
            work.tick()?;
            let d = distance(points[i], points[left], points[right]);
            if d > maximum {
                maximum = d;
                far = i;
            }
        }
        if far != left {
            keep[far - a] = true;
            stack.push((far, right));
            stack.push((left, far));
        }
    }
    Ok(keep
        .iter()
        .enumerate()
        .filter_map(|(i, &yes)| yes.then_some((a + i) as u32))
        .collect())
}
fn distance(p: Point, a: Point, b: Point) -> f64 {
    let dx = b[0] - a[0];
    let dy = b[1] - a[1];
    let norm = dx * dx + dy * dy;
    let t = if norm == 0.0 {
        0.0
    } else {
        (((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / norm).clamp(0.0, 1.0)
    };
    (p[0] - a[0] - t * dx).hypot(p[1] - a[1] - t * dy)
}
fn same_point(a: Point, b: Point) -> bool {
    a == b
}
// Conservative filtered orientation: uncertain floating-point signs count as
// touching/intersection, causing fallback rather than a false topology proof.
fn orient(a: Point, b: Point, c: Point) -> i8 {
    let x = (b[0] - a[0]) * (c[1] - a[1]);
    let y = (b[1] - a[1]) * (c[0] - a[0]);
    let v = x - y;
    let eps = 64.0 * f64::EPSILON * (x.abs() + y.abs() + 1.0);
    if v > eps {
        1
    } else if v < -eps {
        -1
    } else {
        0
    }
}
fn intersects(a: Point, b: Point, c: Point, d: Point) -> bool {
    if a[0].max(b[0]) < c[0].min(d[0])
        || c[0].max(d[0]) < a[0].min(b[0])
        || a[1].max(b[1]) < c[1].min(d[1])
        || c[1].max(d[1]) < a[1].min(b[1])
    {
        return false;
    }
    let (ab_c, ab_d, cd_a, cd_b) = (
        orient(a, b, c),
        orient(a, b, d),
        orient(c, d, a),
        orient(c, d, b),
    );
    ab_c * ab_d <= 0 && cd_a * cd_b <= 0
}
fn area(indices: &[u32], points: &[Point]) -> f64 {
    let origin = points[indices[0] as usize];
    let mut sum = 0.0;
    let mut magnitude = 0.0;
    for p in indices.windows(2) {
        let a = points[p[0] as usize];
        let b = points[p[1] as usize];
        let x = (a[0] - origin[0]) * (b[1] - origin[1]);
        let y = (b[0] - origin[0]) * (a[1] - origin[1]);
        sum += x - y;
        magnitude += x.abs() + y.abs();
    }
    // Refuse to certify a winding sign inside the floating-point error bound.
    if sum.abs() <= 128.0 * f64::EPSILON * (magnitude + 1.0) * indices.len() as f64 {
        0.0
    } else {
        sum
    }
}
fn inside<F: FnMut() -> bool>(
    p: Point,
    ring: &[u32],
    points: &[Point],
    work: &mut Work<'_, F>,
) -> Result<bool, SimplifyError> {
    let mut inside = false;
    for e in ring.windows(2) {
        work.tick()?;
        let a = points[e[0] as usize];
        let b = points[e[1] as usize];
        if orient(a, b, p) == 0
            && p[0] >= a[0].min(b[0])
            && p[0] <= a[0].max(b[0])
            && p[1] >= a[1].min(b[1])
            && p[1] <= a[1].max(b[1])
        {
            return Ok(false);
        }
        if (a[1] > p[1]) != (b[1] > p[1])
            && p[0] < a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
        {
            inside = !inside;
        }
    }
    Ok(inside)
}
fn topology<F: FnMut() -> bool>(
    parts: &[SimplifiedPart],
    points: &[Point],
    work: &mut Work<'_, F>,
) -> Result<bool, SimplifyError> {
    for (ri, ring) in parts.iter().enumerate() {
        let sign = area(&ring.vertices, points);
        if !sign.is_finite() || sign == 0.0 {
            return Ok(false);
        }
        for (ei, e) in ring.vertices.windows(2).enumerate() {
            if points[e[0] as usize] == points[e[1] as usize] {
                return Ok(false);
            }
            for (rj, other) in parts.iter().enumerate().skip(ri) {
                for (ej, f) in other.vertices.windows(2).enumerate() {
                    if ri == rj && (ej <= ei + 1 || (ei == 0 && ej == ring.vertices.len() - 2)) {
                        continue;
                    }
                    work.tick()?;
                    if intersects(
                        points[e[0] as usize],
                        points[e[1] as usize],
                        points[f[0] as usize],
                        points[f[1] as usize],
                    ) {
                        return Ok(false);
                    }
                }
            }
        }
        if ring.is_hole {
            let shell = parts
                .iter()
                .find(|p| p.polygon_index == ring.polygon_index && !p.is_hole)
                .unwrap();
            if !inside(
                points[ring.vertices[0] as usize],
                &shell.vertices,
                points,
                work,
            )? {
                return Ok(false);
            }
            for other in parts
                .iter()
                .take(ri)
                .filter(|p| p.is_hole && p.polygon_index == ring.polygon_index)
            {
                if inside(
                    points[ring.vertices[0] as usize],
                    &other.vertices,
                    points,
                    work,
                )? || inside(
                    points[other.vertices[0] as usize],
                    &ring.vertices,
                    points,
                    work,
                )? {
                    return Ok(false);
                }
            }
        } else {
            // Nested/overlapping MultiPolygon components are outside this
            // conservative certificate. Preserve the entire feature unchanged.
            for other in parts.iter().take(ri).filter(|p| !p.is_hole) {
                if inside(
                    points[ring.vertices[0] as usize],
                    &other.vertices,
                    points,
                    work,
                )? || inside(
                    points[other.vertices[0] as usize],
                    &ring.vertices,
                    points,
                    work,
                )? {
                    return Ok(false);
                }
            }
        }
    }
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geo::{GeoDescriptor, GeoLimits};
    fn camera() -> GeoViewport {
        GeoViewport::new(GeoCrs::Epsg4326, 0., 0., 8., 800., 600., 0., 0., false).unwrap()
    }
    fn col(
        kind: GeoGeometry,
        xy: &[f64],
        o0: &[u32],
        o1: &[u32],
        o2: &[u32],
        ids: &[u64],
        valid: &[u8],
    ) -> GeoColumn {
        GeoColumn::from_descriptor(GeoDescriptor {
            geometry: kind,
            crs: GeoCrs::Epsg4326,
            xy,
            offsets0: o0,
            offsets1: o1,
            offsets2: o2,
            feature_ids: Some(ids),
            validity: valid,
            limits: GeoLimits::default(),
        })
        .unwrap()
    }
    fn run(source: &GeoColumn, vp: &GeoViewport) -> SimplifiedGeo {
        simplify(source, vp, SimplifyOptions::default(), &mut || false).unwrap()
    }
    fn assert_errors(source: &GeoColumn, vp: &GeoViewport, result: &SimplifiedGeo) {
        for p in &result.parts {
            assert_eq!(p.vertices.first(), Some(&p.original_vertices.start));
            assert_eq!(p.vertices.last(), Some(&(p.original_vertices.end - 1)));
            for pair in p.vertices.windows(2) {
                let screen = |i: u32| {
                    let (x, y) = vp
                        .project(source.xy()[i as usize * 2], source.xy()[i as usize * 2 + 1])
                        .unwrap();
                    [x, y]
                };
                for i in pair[0]..=pair[1] {
                    assert!(
                        distance(screen(i), screen(pair[0]), screen(pair[1]))
                            <= result.tolerance_px
                    );
                }
            }
        }
    }
    #[test]
    fn large_route_certifies_every_original_vertex_and_full_identity() {
        let xy: Vec<f64> = (0..10_000)
            .flat_map(|i| [-0.5 + i as f64 / 10_000., (i as f64 * 0.01).sin() * 0.0001])
            .collect();
        let source = col(
            GeoGeometry::LineString,
            &xy,
            &[0, 10_000],
            &[],
            &[],
            &[u64::MAX],
            &[1],
        );
        let before = source.xy().to_vec();
        let result = run(&source, &camera());
        assert_eq!(result.parts[0].vertices, vec![0, 9999]);
        assert_eq!(result.feature_ids, vec![u64::MAX]);
        assert_errors(&source, &camera(), &result);
        assert_eq!(source.xy(), before);
        assert_eq!(result, run(&source, &camera()));
    }
    #[test]
    fn sharp_route_corner_is_retained() {
        let source = col(
            GeoGeometry::LineString,
            &[-0.5, 0., -0.25, 0., 0., 0.2, 0.25, 0., 0.5, 0.],
            &[0, 5],
            &[],
            &[],
            &[0x8000000000000001],
            &[1],
        );
        let result = run(&source, &camera());
        assert!(result.parts[0].vertices.contains(&2));
        assert_errors(&source, &camera(), &result);
    }
    #[test]
    fn polygon_and_hole_reduce_collinear_vertices_preserve_winding() {
        let xy = [
            -0.5, -0.5, 0., -0.5, 0.5, -0.5, 0.5, 0., 0.5, 0.5, 0., 0.5, -0.5, 0.5, -0.5, 0., -0.5,
            -0.5, -0.2, -0.2, -0.2, 0., -0.2, 0.2, 0., 0.2, 0.2, 0.2, 0.2, 0., 0.2, -0.2, 0., -0.2,
            -0.2, -0.2,
        ];
        let source = col(
            GeoGeometry::Polygon,
            &xy,
            &[0, 2],
            &[0, 9, 18],
            &[],
            &[u64::MAX],
            &[1],
        );
        let result = run(&source, &camera());
        assert_eq!(result.parts.len(), 2);
        assert_eq!(result.parts[0].vertices.len(), 5);
        assert_eq!(result.parts[1].vertices.len(), 5);
        assert!(!result.parts[0].is_hole);
        assert!(result.parts[1].is_hole);
        assert_errors(&source, &camera(), &result);
        let pts: Vec<Point> = source
            .xy()
            .chunks_exact(2)
            .map(|p| {
                let (x, y) = camera().project(p[0], p[1]).unwrap();
                [x, y]
            })
            .collect();
        for p in &result.parts {
            assert_eq!(
                area(&p.original_vertices.clone().collect::<Vec<_>>(), &pts).signum(),
                area(&p.vertices, &pts).signum()
            );
        }
        let reduced: Vec<Vec<f64>> = result
            .parts
            .iter()
            .map(|p| p.vertices.iter().flat_map(|&i| pts[i as usize]).collect())
            .collect();
        assert!(crate::geo_fill::tessellate(&[(&reduced[0], false), (&reduced[1], true)]).is_ok());
    }
    #[test]
    fn multipart_mapping_and_null_identity_are_retained() {
        let source = col(
            GeoGeometry::MultiLineString,
            &[-0.5, 0., -0.4, 0., -0.3, 0., 0.3, 0., 0.4, 0., 0.5, 0.],
            &[0, 2, 2],
            &[0, 3, 6],
            &[],
            &[u64::MAX, 7],
            &[1, 0],
        );
        let result = run(&source, &camera());
        assert_eq!(result.validity, vec![1, 0]);
        assert_eq!(result.feature_ids, vec![u64::MAX, 7]);
        assert_eq!(result.parts[0].vertices, vec![0, 2]);
        assert_eq!(result.parts[1].vertices, vec![3, 5]);
        assert_eq!(result.parts[1].part_index, 1);
        assert_eq!(result.parts[1].feature_index, 0);
    }
    #[test]
    fn multipolygon_shells_stay_independent() {
        let source = col(
            GeoGeometry::MultiPolygon,
            &[
                -0.5, -0.2, -0.3, -0.2, -0.3, 0.2, -0.5, 0.2, -0.5, -0.2, 0.3, -0.2, 0.5, -0.2,
                0.5, 0.2, 0.3, 0.2, 0.3, -0.2,
            ],
            &[0, 2],
            &[0, 1, 2],
            &[0, 5, 10],
            &[u64::MAX],
            &[1],
        );
        let result = run(&source, &camera());
        assert_eq!(result.parts[0].polygon_index, Some(0));
        assert_eq!(result.parts[1].polygon_index, Some(1));
        assert!(!result.parts[1].is_hole);
        assert_eq!(result.feature_ids, vec![u64::MAX]);
        assert_errors(&source, &camera(), &result);
    }
    #[test]
    fn points_and_multipoints_are_identity_only() {
        for (kind, o0) in [
            (GeoGeometry::Point, vec![]),
            (GeoGeometry::MultiPoint, vec![0, 1, 2]),
        ] {
            let source = col(
                kind,
                &[0., 0., 0.1, 0.1],
                &o0,
                &[],
                &[],
                &[u64::MAX, 9],
                &[1, 1],
            );
            let result = run(&source, &camera());
            assert!(
                result
                    .parts
                    .iter()
                    .all(|p| p.fallback == FallbackReason::Points)
            );
            assert_eq!(
                result
                    .parts
                    .iter()
                    .flat_map(|p| p.vertices.clone())
                    .collect::<Vec<_>>(),
                vec![0, 1]
            );
        }
    }
    #[test]
    fn dateline_clip_and_horizon_keep_exact_source() {
        let seam = col(
            GeoGeometry::LineString,
            &[179., 0., 180., 0., -179., 0.],
            &[0, 3],
            &[],
            &[],
            &[1],
            &[1],
        );
        let mut vp =
            GeoViewport::new(GeoCrs::Epsg4326, 180., 0., 0., 800., 600., 0., 0., true).unwrap();
        vp.world_wrap = true;
        let r = run(&seam, &vp);
        assert_eq!(r.parts[0].vertices, vec![0, 1, 2]);
        assert_eq!(r.parts[0].fallback, FallbackReason::WorldSeam);
        let clip = col(
            GeoGeometry::LineString,
            &[-2., 0., 0., 0., 2., 0.],
            &[0, 3],
            &[],
            &[],
            &[1],
            &[1],
        );
        assert_eq!(
            run(&clip, &camera()).parts[0].fallback,
            FallbackReason::ProjectionBoundary
        );
        vp.pitch_deg = 60.;
        vp.zoom = 8.;
        let horizon = col(
            GeoGeometry::LineString,
            &[0., -85., 0., 0., 0., 85.],
            &[0, 3],
            &[],
            &[],
            &[1],
            &[1],
        );
        assert_eq!(run(&horizon, &vp).parts[0].vertices, vec![0, 1, 2]);
    }
    #[test]
    fn pitched_front_route_error_is_css_pixels() {
        let xy: Vec<f64> = (0..100)
            .flat_map(|i| [-0.4 + i as f64 * 0.008, 0.05 * (i as f64 * 0.1).sin()])
            .collect();
        let source = col(
            GeoGeometry::LineString,
            &xy,
            &[0, 100],
            &[],
            &[],
            &[1],
            &[1],
        );
        let mut vp = camera();
        vp.pitch_deg = 40.;
        vp.bearing_deg = 31.;
        assert_errors(&source, &vp, &run(&source, &vp));
    }
    #[test]
    fn self_crossing_polygon_falls_back_not_repaired() {
        let source = col(
            GeoGeometry::Polygon,
            &[-0.4, -0.4, 0.4, 0.4, -0.4, 0.4, 0.3, -0.4, -0.4, -0.4],
            &[0, 1],
            &[0, 5],
            &[],
            &[1],
            &[1],
        );
        let result = run(&source, &camera());
        assert_eq!(
            result.parts[0].fallback,
            FallbackReason::TopologyUncertified
        );
        assert_eq!(result.parts[0].vertices, vec![0, 1, 2, 3, 4]);
    }
    #[test]
    fn admission_work_and_cancellation_publish_no_partial_cache() {
        let source = col(
            GeoGeometry::LineString,
            &[-0.5, 0., 0., 0., 0.5, 0.],
            &[0, 3],
            &[],
            &[],
            &[u64::MAX],
            &[1],
        );
        let before = source.xy().to_vec();
        let mut called = 0;
        let options = SimplifyOptions {
            max_bytes: 1,
            ..SimplifyOptions::default()
        };
        assert_eq!(
            simplify(&source, &camera(), options, &mut || {
                called += 1;
                false
            }),
            Err(SimplifyError::ResourceLimit)
        );
        assert_eq!(called, 0);
        let options = SimplifyOptions {
            max_edge_visits: 2,
            ..SimplifyOptions::default()
        };
        assert_eq!(
            simplify(&source, &camera(), options, &mut || false),
            Err(SimplifyError::ResourceLimit)
        );
        let mut ticks = 0;
        assert_eq!(
            simplify(&source, &camera(), SimplifyOptions::default(), &mut || {
                ticks += 1;
                ticks == 5
            }),
            Err(SimplifyError::Cancelled)
        );
        assert_eq!(source.xy(), before);
        assert_eq!(run(&source, &camera()).parts[0].vertices, vec![0, 2]);
    }
    #[test]
    fn compact_null_point_indices_do_not_use_feature_row() {
        let source = col(
            GeoGeometry::Point,
            &[0., 0., 0.1, 0.1],
            &[],
            &[],
            &[],
            &[7, u64::MAX, 9],
            &[0, 1, 1],
        );
        let result = run(&source, &camera());
        assert_eq!(result.parts[0].feature_index, 1);
        assert_eq!(result.parts[0].vertices, vec![0]);
        assert_eq!(result.parts[1].feature_index, 2);
        assert_eq!(result.parts[1].vertices, vec![1]);
        let empty = col(GeoGeometry::Point, &[], &[], &[], &[], &[u64::MAX], &[0]);
        assert!(run(&empty, &camera()).parts.is_empty());
    }
    #[test]
    fn topology_work_falls_back_before_quadratic_scan() {
        let mut xy: Vec<f64> = (0..600)
            .flat_map(|i| {
                let a = i as f64 / 600. * std::f64::consts::TAU;
                [a.cos() * 0.4, a.sin() * 0.4]
            })
            .collect();
        xy.extend_from_slice(&[0.4, 0.]);
        let source = col(
            GeoGeometry::Polygon,
            &xy,
            &[0, 1],
            &[0, 601],
            &[],
            &[1],
            &[1],
        );
        let result = run(&source, &camera());
        assert_eq!(result.parts[0].fallback, FallbackReason::TopologyWorkLimit);
        assert_eq!(result.parts[0].vertices.len(), 601);
        assert!(result.edge_visits < 10_000);
    }
    #[test]
    fn topology_negative_controls_detect_new_crossings_and_hole_escape() {
        let pts = [
            [0., 0.],
            [4., 0.],
            [4., 4.],
            [0., 4.],
            [0., 0.],
            [1., 1.],
            [1., 2.],
            [2., 2.],
            [2., 1.],
            [1., 1.],
        ];
        let part = |range: Range<u32>, hole| SimplifiedPart {
            feature_index: 0,
            polygon_index: Some(0),
            part_index: range.start,
            is_hole: hole,
            vertices: range.clone().collect(),
            original_vertices: range,
            fallback: FallbackReason::Unchanged,
            max_error_px: 0.,
        };
        let mut parts = vec![part(0..5, false), part(5..10, true)];
        let mut cancel = || false;
        let mut work = Work {
            visits: 0,
            limit: 1000,
            cancelled: &mut cancel,
        };
        assert!(topology(&parts, &pts, &mut work).unwrap());
        parts[0].vertices = vec![0, 2, 1, 3, 4];
        assert!(!topology(&parts, &pts, &mut work).unwrap());
        parts[0].vertices = vec![0, 1, 2, 3, 4];
        let mut outside = pts;
        outside[5] = [5., 1.];
        outside[9] = outside[5];
        assert!(!topology(&parts, &outside, &mut work).unwrap());
    }
    #[test]
    fn mercator_and_deep_zoom_use_the_same_screen_error_contract() {
        let source = GeoColumn::from_descriptor(GeoDescriptor {
            geometry: GeoGeometry::LineString,
            crs: GeoCrs::Epsg3857,
            xy: &[-1000., 0., 0., 0.01, 1000., 0.],
            validity: &[1],
            feature_ids: Some(&[u64::MAX]),
            offsets0: &[0, 3],
            offsets1: &[],
            offsets2: &[],
            limits: GeoLimits::default(),
        })
        .unwrap();
        let vp =
            GeoViewport::new(GeoCrs::Epsg3857, 0., 0., 8., 800., 600., 10., 30., false).unwrap();
        let result = run(&source, &vp);
        assert_eq!(result.parts[0].vertices, vec![0, 2]);
        assert_errors(&source, &vp, &result);
        let fine = col(
            GeoGeometry::LineString,
            &[10., 20., 10.00000005, 20.000000001, 10.0000001, 20.],
            &[0, 3],
            &[],
            &[],
            &[u64::MAX],
            &[1],
        );
        let vp =
            GeoViewport::new(GeoCrs::Epsg4326, 10., 20., 24., 800., 600., 0., 0., true).unwrap();
        let result = run(&fine, &vp);
        assert_eq!(result.parts[0].vertices, vec![0, 2]);
        assert_errors(&fine, &vp, &result);
        assert_eq!(result.camera, vp.rebuild_key().unwrap());
    }
    #[test]
    fn materialization_preserves_all_six_schemas_null_rows_and_literal_ids() {
        let ids = [17, u64::MAX, 0x8000000000000001];
        let shell_hole = vec![
            0., 0., 2., 0., 4., 0., 4., 4., 0., 4., 0., 0., 1., 1., 1., 2., 2., 2., 2., 1., 1., 1.,
            8., 0., 10., 0., 10., 2., 8., 2., 8., 0.,
        ];
        let mut multi_polygons = shell_hole.clone();
        multi_polygons.extend([-10., -2., -8., -2., -8., 0., -10., 0., -10., -2.]);
        let cases = vec![
            (
                GeoGeometry::Point,
                vec![0., 0., 1., 1.],
                vec![],
                vec![],
                vec![],
                vec![],
            ),
            (
                GeoGeometry::MultiPoint,
                vec![-2., 0., -1., 0., 1., 0., 2., 0.],
                vec![0, 0, 2, 4],
                vec![],
                vec![],
                vec![0, 0, 2, 4],
            ),
            (
                GeoGeometry::LineString,
                vec![
                    -4., 0., -3., 0., -2., 0., -1., 0., 1., 0., 2., 0., 3., 0., 4., 0.,
                ],
                vec![0, 0, 4, 8],
                vec![],
                vec![],
                vec![0, 0, 2, 4],
            ),
            (
                GeoGeometry::MultiLineString,
                vec![
                    -4., -2., -3., -2., -2., -2., -1., -2., -4., 2., -3., 2., -2., 2., -1., 2., 1.,
                    0., 2., 0., 3., 0., 4., 0.,
                ],
                vec![0, 0, 2, 3],
                vec![0, 4, 8, 12],
                vec![],
                vec![0, 2, 4, 6],
            ),
            (
                GeoGeometry::Polygon,
                shell_hole,
                vec![0, 0, 2, 3],
                vec![0, 6, 11, 16],
                vec![],
                vec![0, 5, 10, 15],
            ),
            (
                GeoGeometry::MultiPolygon,
                multi_polygons,
                vec![0, 0, 2, 3],
                vec![0, 2, 3, 4],
                vec![0, 6, 11, 16, 21],
                vec![0, 5, 10, 15, 20],
            ),
        ];
        let vp = GeoViewport {
            zoom: 4.,
            ..camera()
        };
        for (kind, xy, o0, o1, o2, expected_leaf) in cases {
            let source = col(kind, &xy, &o0, &o1, &o2, &ids, &[0, 1, 1]);
            let before = (
                source.xy().to_vec(),
                source.offsets0().to_vec(),
                source.offsets1().to_vec(),
                source.offsets2().to_vec(),
                source.metadata_digest(),
            );
            let (certificate, reduced) =
                simplify_column(&source, &vp, SimplifyOptions::default(), &mut || false).unwrap();
            assert_eq!(source.xy(), before.0);
            assert_eq!(source.offsets0(), before.1);
            assert_eq!(source.offsets1(), before.2);
            assert_eq!(source.offsets2(), before.3);
            assert_eq!(source.metadata_digest(), before.4);
            assert_eq!(
                certificate.admitted_bytes,
                materialization_bytes(&source).unwrap()
            );
            assert_eq!(reduced.geometry(), kind);
            assert_eq!(reduced.crs(), source.crs());
            assert_eq!(reduced.feature_ids(), ids);
            assert_eq!(reduced.validity(), &[0, 1, 1]);
            assert_eq!(reduced.len(), 3);
            let leaf = match kind {
                GeoGeometry::Point => {
                    assert_eq!(reduced.xy(), source.xy());
                    continue;
                }
                GeoGeometry::MultiPoint | GeoGeometry::LineString => reduced.offsets0(),
                GeoGeometry::Polygon | GeoGeometry::MultiLineString => {
                    assert_eq!(reduced.offsets0(), source.offsets0());
                    reduced.offsets1()
                }
                GeoGeometry::MultiPolygon => {
                    assert_eq!(reduced.offsets0(), source.offsets0());
                    assert_eq!(reduced.offsets1(), source.offsets1());
                    reduced.offsets2()
                }
            };
            assert_eq!(leaf, expected_leaf, "{kind:?}");
            for part in &certificate.parts {
                let range = leaf[part.part_index as usize] as usize
                    ..leaf[part.part_index as usize + 1] as usize;
                assert_eq!(range.len(), part.vertices.len());
                for (actual, &original) in reduced.xy()[range.start * 2..range.end * 2]
                    .chunks_exact(2)
                    .zip(&part.vertices)
                {
                    assert_eq!(
                        actual,
                        &source.xy()[original as usize * 2..original as usize * 2 + 2]
                    );
                }
                if part.polygon_index.is_some() {
                    assert_eq!(
                        &reduced.xy()[range.start * 2..range.start * 2 + 2],
                        &reduced.xy()[range.end * 2 - 2..range.end * 2]
                    );
                }
            }
            assert_errors(&source, &vp, &certificate);
        }
    }
    #[test]
    fn materialization_failure_preserves_source_and_discards_post_certificate_cancel() {
        let source = col(
            GeoGeometry::LineString,
            &[-2., 0., -1., 0., 0., 0., 1., 0., 2., 0.],
            &[0, 5],
            &[],
            &[],
            &[u64::MAX],
            &[1],
        );
        let vp = GeoViewport {
            zoom: 4.,
            ..camera()
        };
        let before = source.xy().to_vec();
        assert!(matches!(
            simplify_column(
                &source,
                &vp,
                SimplifyOptions {
                    max_bytes: 1,
                    ..SimplifyOptions::default()
                },
                &mut || false
            ),
            Err(SimplifyError::ResourceLimit)
        ));
        let mut base_checks = 0;
        simplify(&source, &vp, SimplifyOptions::default(), &mut || {
            base_checks += 1;
            false
        })
        .unwrap();
        let mut checks = 0;
        assert!(matches!(
            simplify_column(&source, &vp, SimplifyOptions::default(), &mut || {
                checks += 1;
                checks > base_checks + 1
            }),
            Err(SimplifyError::Cancelled)
        ));
        let point = col(
            GeoGeometry::Point,
            &[0., 0.],
            &[],
            &[],
            &[],
            &[u64::MAX],
            &[1],
        );
        let mut point_checks = 0;
        simplify(&point, &vp, SimplifyOptions::default(), &mut || {
            point_checks += 1;
            false
        })
        .unwrap();
        let mut current = 0;
        assert!(matches!(
            simplify_column(&point, &vp, SimplifyOptions::default(), &mut || {
                current += 1;
                current > point_checks + 1
            }),
            Err(SimplifyError::Cancelled)
        ));
        assert_eq!(source.xy(), before);
        assert_eq!(source.feature_ids(), &[u64::MAX]);
        assert_eq!(source.offsets0(), &[0, 5]);
    }
}
