//! Bounded same-publication picks (§2.3; dossier §28). Geometry is resolved by
//! `paint`, not by the index. A degraded index never invents an edge chord.
use super::*;
use crate::marker_geometry;

pub const MAX_GRAPH_PICK_PRIMITIVES: usize = 131_072;
pub const MAX_GRAPH_PICK_GRID_ENTRIES: usize = 1_048_576;
pub const MAX_GRAPH_PICK_CANDIDATES: usize = 65_536;
const GRID: usize = 64;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum PickTarget {
    Node(usize),
    Edge(usize),
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SelectionPolicy {
    Nodes,
    Edges,
    NodesAndInducedEdges,
}

#[derive(Clone, Copy)]
pub(super) enum RegionInput<'a> {
    Polygon(&'a [[f64; 2]]),
    Candidates(&'a [u8]),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
enum Primitive {
    Node(usize),
    Frame(usize),
    Piece(usize),
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct PickIndex {
    pub degraded: bool,
    pub node_scan: bool,
    bounds: [f64; 4],
    primitives: Vec<Primitive>,
    grid: Arc<Grid>,
    entries: usize,
}

// Immutable CSR storage: clones share the preceding publication's grid.
// Logical admission remains identical; capacities cannot retain failed builds.
#[derive(Debug, Default, PartialEq)]
struct Grid {
    offsets: Vec<u32>,
    indices: Vec<u32>,
}

#[derive(Default)]
struct Work(u64);
impl Work {
    fn charge(&mut self, n: usize) -> Result<(), InteractionStatus> {
        self.0 = self
            .0
            .checked_add(n as u64)
            .ok_or(InteractionStatus::Budget)?;
        if self.0 > MAX_GRAPH_INTERACTION_WORK {
            Err(InteractionStatus::Budget)
        } else {
            Ok(())
        }
    }
}
fn union(a: [f64; 4], b: [f64; 4]) -> [f64; 4] {
    [
        a[0].min(b[0]),
        a[1].min(b[1]),
        a[2].max(b[2]),
        a[3].max(b[3]),
    ]
}
fn point_bounds(p: [f64; 2], r: f64) -> [f64; 4] {
    [p[0] - r, p[1] - r, p[0] + r, p[1] + r]
}
fn bounds(p: Primitive, paint: &PaintGeometry) -> [f64; 4] {
    match p {
        Primitive::Node(i) => {
            let n = &paint.nodes[i];
            point_bounds(
                n.center,
                f64::from(n.style.size).max(f64::from(n.layers.halo_extent)) * 0.75,
            )
        }
        Primitive::Frame(i) => {
            let f = &paint.frames[i];
            [
                f.bounds[0] - f.half_width,
                f.bounds[1] - f.half_width,
                f.bounds[2] + f.half_width,
                f.bounds[3] + f.half_width,
            ]
        }
        Primitive::Piece(i) => {
            let e = &paint.pieces[i];
            let mut b = union(
                point_bounds(e.start, e.half_width),
                point_bounds(e.end, e.half_width),
            );
            if let Some(h) = e.head {
                for p in h {
                    b = union(b, point_bounds(p, 0.));
                }
            }
            b
        }
    }
}
impl PickIndex {
    pub fn primitive_count(&self) -> usize {
        self.primitives.len()
    }
    pub fn grid_entries(&self) -> usize {
        self.entries
    }
    pub fn build(paint: &PaintGeometry) -> Self {
        let all = || {
            (0..paint.nodes.len())
                .map(Primitive::Node)
                .chain((0..paint.frames.len()).map(Primitive::Frame))
                .chain((0..paint.pieces.len()).map(Primitive::Piece))
        };
        let domain = all().fold(
            [
                f64::INFINITY,
                f64::INFINITY,
                f64::NEG_INFINITY,
                f64::NEG_INFINITY,
            ],
            |b, p| union(b, bounds(p, paint)),
        );
        let mut out = Self {
            bounds: domain,

            ..Default::default()
        };
        if all().all(|p| out.admit(p, paint)) {
            out.finish_grid(paint);
            return out;
        }
        out.primitives.clear();
        out.entries = 0;
        out.degraded = true;
        // Nodes are exact even if their index cannot fit. No source-sized
        // second index: point/region queries scan this publication instead.
        for i in 0..paint.nodes.len() {
            if !out.admit(Primitive::Node(i), paint) {
                out.node_scan = true;
                break;
            }
        }
        if out.node_scan {
            out.primitives.clear();
            out.entries = 0;
        }
        for i in 0..paint.frames.len() {
            if !out.admit(Primitive::Frame(i), paint) {
                out.node_scan = true;
            }
        }
        if out.node_scan {
            out.primitives.clear();
            out.entries = 0;
        }
        for i in 0..paint.pieces.len() {
            let e = paint.pieces[i].edge;
            let single = paint.pieces[i].single_piece
                && (i == 0 || paint.pieces[i - 1].edge != e)
                && (i + 1 == paint.pieces.len() || paint.pieces[i + 1].edge != e);
            if single {
                out.admit(Primitive::Piece(i), paint);
            }
        }
        out.finish_grid(paint);
        out
    }
    fn cells(&self, b: [f64; 4]) -> [usize; 4] {
        let at = |v: f64, k: usize| {
            let span = self.bounds[k + 2] - self.bounds[k];
            if span > 0. {
                ((v - self.bounds[k]) / span * GRID as f64)
                    .floor()
                    .clamp(0., (GRID - 1) as f64) as usize
            } else {
                0
            }
        };
        [at(b[0], 0), at(b[1], 1), at(b[2], 0), at(b[3], 1)]
    }
    fn admit(&mut self, p: Primitive, paint: &PaintGeometry) -> bool {
        let c = self.cells(bounds(p, paint));
        let copies = (c[2] - c[0] + 1) * (c[3] - c[1] + 1);
        // Check before either primitive append or per-cell allocation.
        if self.primitives.len() == MAX_GRAPH_PICK_PRIMITIVES
            || copies > MAX_GRAPH_PICK_GRID_ENTRIES - self.entries
        {
            return false;
        }
        self.primitives.push(p);
        self.entries += copies;
        true
    }
    fn finish_grid(&mut self, paint: &PaintGeometry) {
        // admit() checked entries and primitive count before either allocation.
        let mut offsets = vec![0u32; GRID * GRID + 1];
        for &p in &self.primitives {
            let c = self.cells(bounds(p, paint));
            for y in c[1]..=c[3] {
                for x in c[0]..=c[2] {
                    offsets[y * GRID + x + 1] += 1;
                }
            }
        }
        for i in 1..offsets.len() {
            offsets[i] += offsets[i - 1];
        }
        let mut cursor = offsets[..GRID * GRID].to_vec();
        let mut indices = vec![0; self.entries];
        for (i, &p) in self.primitives.iter().enumerate() {
            let c = self.cells(bounds(p, paint));
            for y in c[1]..=c[3] {
                for x in c[0]..=c[2] {
                    let at = &mut cursor[y * GRID + x];
                    indices[*at as usize] = i as u32;
                    *at += 1;
                }
            }
        }
        self.grid = Arc::new(Grid { offsets, indices });
    }
    pub(super) fn retained_bytes(&self) -> usize {
        self.primitives.capacity() * std::mem::size_of::<Primitive>()
            + self.grid.offsets.capacity() * 4
            + self.grid.indices.capacity() * 4
            + std::mem::size_of::<Grid>()
            + 2 * std::mem::size_of::<usize>()
    }
    fn candidates(
        &self,
        b: [f64; 4],
        work: &mut Work,
    ) -> Result<Vec<Primitive>, InteractionStatus> {
        let c = self.cells(b);
        let mut seen = BTreeSet::new();
        for y in c[1]..=c[3] {
            for x in c[0]..=c[2] {
                let cell = y * GRID + x;
                let lo = self.grid.offsets.get(cell).copied().unwrap_or(0) as usize;
                let hi = self.grid.offsets.get(cell + 1).copied().unwrap_or(0) as usize;
                for &p in &self.grid.indices[lo..hi] {
                    work.charge(2)?;
                    seen.insert(p);
                    if seen.len() > MAX_GRAPH_PICK_CANDIDATES {
                        return Err(InteractionStatus::Budget);
                    }
                }
            }
        }
        Ok(seen
            .into_iter()
            .map(|i| self.primitives[i as usize])
            .collect())
    }
}
fn dist(p: [f64; 2], a: [f64; 2], b: [f64; 2]) -> f64 {
    let d = [b[0] - a[0], b[1] - a[1]];
    let len = d[0] * d[0] + d[1] * d[1];
    let t = if len > 0. {
        ((p[0] - a[0]) * d[0] + (p[1] - a[1]) * d[1]) / len
    } else {
        0.
    }
    .clamp(0., 1.);
    (p[0] - a[0] - t * d[0]).hypot(p[1] - a[1] - t * d[1])
}
fn cross(a: [f64; 2], b: [f64; 2], p: [f64; 2]) -> f64 {
    (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
}
fn intersect(a: [f64; 2], b: [f64; 2], c: [f64; 2], d: [f64; 2]) -> bool {
    let within = |p: [f64; 2], a: [f64; 2], b: [f64; 2]| {
        p[0] >= a[0].min(b[0])
            && p[0] <= a[0].max(b[0])
            && p[1] >= a[1].min(b[1])
            && p[1] <= a[1].max(b[1])
    };
    let (x, y, z, w) = (
        cross(a, b, c),
        cross(a, b, d),
        cross(c, d, a),
        cross(c, d, b),
    );
    (x == 0. && within(c, a, b))
        || (y == 0. && within(d, a, b))
        || (z == 0. && within(a, c, d))
        || (w == 0. && within(b, c, d))
        || ((x > 0.) != (y > 0.) && (z > 0.) != (w > 0.))
}
fn inside(p: [f64; 2], poly: &[[f64; 2]]) -> bool {
    let mut inside = false;
    for i in 0..poly.len() {
        let a = poly[i];
        let b = poly[(i + 1) % poly.len()];
        if dist(p, a, b) <= 1e-10 {
            return true;
        }
        if (a[1] > p[1]) != (b[1] > p[1])
            && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]
        {
            inside = !inside;
        }
    }
    inside
}
fn node_hit(n: &NodePaint, p: [f64; 2]) -> bool {
    let half = f64::from(n.style.width) * 0.5;
    let radius = (f64::from(n.style.size) * 0.5 - half).max(0.);
    let p = [p[0] - n.center[0], p[1] - n.center[1]];
    marker_geometry::rect_hit(
        n.style.shape,
        radius,
        half,
        n.layers.body[3] > 0,
        n.layers.stroke[3] > 0,
        [p[0], p[1], p[0], p[1]],
    )
}
fn frame_hit(f: &FramePaint, p: [f64; 2]) -> bool {
    let b = f.bounds;
    let corners = [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
    (0..4).any(|i| dist(p, corners[i], corners[(i + 1) % 4]) <= f.half_width)
}
fn head_hit(e: &EdgePiece, p: [f64; 2]) -> bool {
    e.head.is_some_and(|h| inside(p, &h))
}
fn piece_hit(e: &EdgePiece, p: [f64; 2]) -> bool {
    let d = [e.end[0] - e.start[0], e.end[1] - e.start[1]];
    let length = d[0].hypot(d[1]);
    if length <= 0. {
        return false;
    }
    let along = ((p[0] - e.start[0]) * d[0] + (p[1] - e.start[1]) * d[1]) / length;
    let across = ((p[0] - e.start[0]) * d[1] - (p[1] - e.start[1]) * d[0]).abs() / length;
    along >= 0.
        && along <= length
        && across <= e.half_width
        && (e.dash.0 <= 0. || (e.dash_offset + along).rem_euclid(e.dash.0 + e.dash.1) <= e.dash.0)
}
fn polygons_overlap(
    a: &[[f64; 2]],
    b: &[[f64; 2]],
    work: &mut Work,
) -> Result<bool, InteractionStatus> {
    work.charge(a.len().saturating_mul(b.len()).saturating_mul(3))?;
    Ok(a.iter().any(|&p| inside(p, b))
        || b.iter().any(|&p| inside(p, a))
        || (0..a.len()).any(|i| {
            (0..b.len()).any(|j| intersect(a[i], a[(i + 1) % a.len()], b[j], b[(j + 1) % b.len()]))
        }))
}
fn piece_region(
    e: &EdgePiece,
    polygon: &[[f64; 2]],
    work: &mut Work,
) -> Result<bool, InteractionStatus> {
    if let Some(head) = e.head {
        if polygons_overlap(&head, polygon, work)? {
            return Ok(true);
        }
    }
    let d = [e.end[0] - e.start[0], e.end[1] - e.start[1]];
    let length = d[0].hypot(d[1]);
    if length <= 0. {
        return Ok(false);
    }
    let side = [-d[1] / length * e.half_width, d[0] / length * e.half_width];
    let band = |lo: f64, hi: f64| {
        let at = |t: f64| {
            [
                e.start[0] + d[0] * t / length,
                e.start[1] + d[1] * t / length,
            ]
        };
        let (a, b) = (at(lo), at(hi));
        [
            [a[0] + side[0], a[1] + side[1]],
            [b[0] + side[0], b[1] + side[1]],
            [b[0] - side[0], b[1] - side[1]],
            [a[0] - side[0], a[1] - side[1]],
        ]
    };
    if e.dash.0 <= 0. {
        return polygons_overlap(&band(0., length), polygon, work);
    }
    let period = e.dash.0 + e.dash.1;
    let periods = (length / period).ceil() + 1.;
    if !periods.is_finite() || periods > MAX_GRAPH_INTERACTION_WORK as f64 {
        return Err(InteractionStatus::Budget);
    }
    work.charge(periods as usize)?;
    let mut lo = -e.dash_offset.rem_euclid(period);
    while lo < length {
        let hi = (lo + e.dash.0).min(length);
        if hi >= lo.max(0.) && polygons_overlap(&band(lo.max(0.), hi), polygon, work)? {
            return Ok(true);
        }
        lo += period;
    }
    Ok(false)
}
impl RenderOutput {
    fn point(&self, p: [f64; 2], work: &mut Work) -> Result<Option<PickTarget>, InteractionStatus> {
        #[cfg(test)]
        POINT_QUERY_COUNT.with(|n| n.set(n.get() + 1));
        if !p.iter().all(|v| v.is_finite()) {
            return invalid();
        }
        let candidates = self.pick.candidates(point_bounds(p, 0.), work)?;
        let (mut frame, mut edge, mut head, mut node) = (None, None, None, None);
        for primitive in candidates {
            work.charge(1)?;
            match primitive {
                Primitive::Node(i) if !self.pick.node_scan && node_hit(&self.paint.nodes[i], p) => {
                    node = Some(i)
                }
                Primitive::Frame(i) if frame_hit(&self.paint.frames[i], p) => {
                    frame = Some(self.paint.frames[i].node)
                }
                Primitive::Piece(i) => {
                    if head_hit(&self.paint.pieces[i], p) {
                        head = Some(self.paint.pieces[i].edge);
                    }
                    if piece_hit(&self.paint.pieces[i], p) {
                        edge = Some(self.paint.pieces[i].edge);
                    }
                }
                _ => {}
            }
        }
        if self.pick.node_scan {
            for (i, n) in self.paint.nodes.iter().enumerate() {
                work.charge(1)?;
                if node_hit(n, p) {
                    node = Some(i);
                }
            }
            for f in &self.paint.frames {
                work.charge(1)?;
                if frame_hit(f, p) {
                    frame = Some(f.node);
                }
            }
        }
        Ok(node
            .map(PickTarget::Node)
            .or_else(|| head.map(PickTarget::Edge))
            .or_else(|| edge.map(PickTarget::Edge))
            .or_else(|| frame.map(PickTarget::Node)))
    }
    /// Read-only diagnostic of the current publication in CSS-pixel coordinates.
    pub fn pick_at(&self, x: f64, y: f64) -> Result<Option<PickTarget>, InteractionStatus> {
        self.point([x, y], &mut Work::default())
    }
}
impl GraphSession {
    // Capture before mutation, using the same source mapping that paints this
    // publication. At Direct/EdgeSample focus_node is the actual visible
    // representative, not an Aggregate keyboard stand-in. Never expand a group.
    fn pick_receipt(
        &self,
        header: OpHeader,
        operation: u32,
        target: Option<PickTarget>,
    ) -> Result<PickReceipt, InteractionStatus> {
        let render = self.published().ok_or(InteractionStatus::Stale)?;
        let (member_count, source) = match target {
            Some(PickTarget::Node(i)) => (
                render.members_of_node(i).len() as u64,
                ElementIndex::Node(render.focus_node[i] as usize),
            ),
            Some(PickTarget::Edge(i)) => (
                render.members_of_edge(i).len() as u64,
                ElementIndex::Edge(render.members_of_edge(i)[0] as usize),
            ),
            None => {
                return Ok(PickReceipt {
                    header,
                    operation,
                    action: 0,
                    target,
                    member_count: 0,
                    source: None,
                })
            }
        };
        let source = if render.tier == crate::graph::LodTier::Aggregate {
            None
        } else {
            let reference = match source {
                ElementIndex::Node(i) => self.source.identity.node_ref(i),
                ElementIndex::Edge(i) => self.source.identity.edge_ref(i),
            };
            Some((
                source,
                self.source
                    .identity
                    .to_transport(&reference)
                    .ok_or(InteractionStatus::Invalid)?,
            ))
        };
        Ok(PickReceipt {
            header,
            operation,
            action: 0,
            target,
            member_count,
            source,
        })
    }

    fn picked_set(
        &self,
        render: &RenderOutput,
        targets: impl IntoIterator<Item = PickTarget>,
        work: &mut Work,
    ) -> Result<ElementSet, InteractionStatus> {
        let mut set = ElementSet::default();
        for target in targets {
            let (members, node) = match target {
                PickTarget::Node(i) => (render.members_of_node(i), true),
                PickTarget::Edge(i) => (render.members_of_edge(i), false),
            };
            work.charge(members.len())?;
            for &member in members {
                self.source.identity.insert_into(
                    &mut set,
                    if node {
                        ElementIndex::Node(member as usize)
                    } else {
                        ElementIndex::Edge(member as usize)
                    },
                );
                if set.len() > MAX_GRAPH_SELECTION_REFS {
                    return Err(InteractionStatus::SelectionTooLarge);
                }
            }
        }
        Ok(set)
    }
    pub fn select_at(
        &mut self,
        header: OpHeader,
        x: f64,
        y: f64,
        mode: SelectMode,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |s, w| {
            let r = s.published().ok_or(InteractionStatus::Stale)?;
            let mut work = Work::default();
            let hit = r.point([x, y], &mut work)?;
            work.charge(1)?;
            let pick = s.pick_receipt(header, 1, hit)?;
            let set = s.picked_set(r, hit, &mut work)?;
            s.work += work.0;
            let mut out = s.select_set(w, mode, set, 0)?;
            out.pick = Some(pick);
            Ok(out)
        })
    }
    pub fn hover_at(
        &mut self,
        header: OpHeader,
        x: f64,
        y: f64,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |s, w| {
            let r = s.published().ok_or(InteractionStatus::Stale)?;
            let mut work = Work::default();
            let hit = r.point([x, y], &mut work)?;
            work.charge(1)?;
            let pick = s.pick_receipt(header, 0, hit)?;
            let mut next = Hover::default();
            match hit {
                Some(PickTarget::Node(i)) => {
                    let members = r.members_of_node(i);
                    work.charge(members.len())?;
                    next.nodes = members.iter().map(|&m| m as usize).collect();
                }
                Some(PickTarget::Edge(i)) => {
                    let members = r.members_of_edge(i);
                    work.charge(members.len())?;
                    next.edges = members.iter().map(|&edge| edge as usize).collect();
                }
                None => {}
            }
            let changed = s.hover != next;
            s.work += work.0;
            s.hover = next;
            let mut out = s.outcome(w, changed);
            out.pick = Some(pick);
            Ok(out)
        })
    }
    /// Clear only transient hover; no coordinates, publication query or CSR walk.
    pub fn hover_leave(&mut self, header: OpHeader) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |s, w| {
            let changed = s.hover != Hover::default();
            s.hover = Hover::default();
            let mut out = s.outcome(w, changed);
            out.pick = Some(PickReceipt {
                header,
                operation: 0,
                action: 1,
                target: None,
                member_count: 0,
                source: None,
            });
            Ok(out)
        })
    }
    /// Region nodes use their published centers; edges use intersections with
    /// their clipped painted shafts/heads. Concave polygons use even-odd fill.
    pub fn lasso(
        &mut self,
        header: OpHeader,
        points: &[[f64; 2]],
        mode: SelectMode,
        policy: SelectionPolicy,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.select_region(header, RegionInput::Polygon(points), mode, policy)
    }

    pub(super) fn select_region(
        &mut self,
        header: OpHeader,
        input: RegionInput<'_>,
        mode: SelectMode,
        policy: SelectionPolicy,
    ) -> Result<OpOutcome, InteractionStatus> {
        self.operate(header, |s, w| {
            let mut work = Work::default();
            let mut nodes = BTreeSet::new();
            let mut edges = BTreeSet::new();
            let r = match input {
                RegionInput::Polygon(points) => {
                    work.charge(points.len())?;
                    if points.len() < 3 || points.iter().flatten().any(|v| !v.is_finite()) {
                        return invalid();
                    }
                    let r = s.published().ok_or(InteractionStatus::Stale)?;
                    let b = points.iter().fold(
                        [
                            f64::INFINITY,
                            f64::INFINITY,
                            f64::NEG_INFINITY,
                            f64::NEG_INFINITY,
                        ],
                        |b, &p| union(b, point_bounds(p, 0.)),
                    );
                    if r.pick.node_scan {
                        for (i, n) in r.paint.nodes.iter().enumerate() {
                            work.charge(1 + points.len())?;
                            if inside(n.center, points) {
                                nodes.insert(i);
                                if nodes.len() > MAX_GRAPH_PICK_CANDIDATES {
                                    return Err(InteractionStatus::Budget);
                                }
                            }
                        }
                    } else {
                        for p in r.pick.candidates(b, &mut work)? {
                            work.charge(1)?;
                            match p {
                                Primitive::Node(i) => {
                                    work.charge(points.len())?;
                                    if inside(r.paint.nodes[i].center, points) {
                                        nodes.insert(i);
                                        if nodes.len() > MAX_GRAPH_PICK_CANDIDATES {
                                            return Err(InteractionStatus::Budget);
                                        }
                                    }
                                }
                                Primitive::Piece(i)
                                    if !r.pick.degraded && policy == SelectionPolicy::Edges =>
                                {
                                    let e = &r.paint.pieces[i];
                                    work.charge(points.len() * 4)?;
                                    if piece_region(e, points, &mut work)? {
                                        edges.insert(e.edge);
                                    }
                                }
                                _ => {}
                            }
                        }
                    }
                    r
                }
                RegionInput::Candidates(refs) => {
                    if refs.len() % 4 != 0 {
                        return invalid();
                    }
                    if refs.len() / 4 > MAX_GRAPH_SELECTION_REFS {
                        return Err(InteractionStatus::SelectionTooLarge);
                    }
                    work.charge(refs.len() / 4)?;
                    let r = s.published().ok_or(InteractionStatus::Stale)?;
                    for bytes in refs.chunks_exact(4) {
                        let index = u32::from_le_bytes(bytes.try_into().unwrap());
                        if index as usize >= r.node_count() {
                            return invalid();
                        }
                        nodes.insert(index as usize);
                    }
                    r
                }
            };
            let induced = policy == SelectionPolicy::NodesAndInducedEdges
                || (r.pick.degraded && policy == SelectionPolicy::Edges);
            if induced {
                for i in 0..r.edge_count() {
                    work.charge(3)?;
                    if nodes.contains(&(r.edge_source[i] as usize))
                        && nodes.contains(&(r.edge_target[i] as usize))
                    {
                        edges.insert(i);
                    }
                }
            }
            let selected_nodes = if policy == SelectionPolicy::Edges {
                BTreeSet::new()
            } else {
                nodes
            };
            let set = s.picked_set(
                r,
                selected_nodes
                    .into_iter()
                    .map(PickTarget::Node)
                    .chain(edges.into_iter().map(PickTarget::Edge)),
                &mut work,
            )?;
            s.work += work.0;
            s.select_set(w, mode, set, 0)
        })
    }
    pub fn brush(
        &mut self,
        header: OpHeader,
        bounds: [f64; 4],
        mode: SelectMode,
        policy: SelectionPolicy,
    ) -> Result<OpOutcome, InteractionStatus> {
        if let Some((sequence, outcome)) = &self.last_op {
            if *sequence == header.op_seq && header.op_seq != 0 {
                return Ok(outcome.clone());
            }
        }
        if !bounds.iter().all(|v| v.is_finite()) || bounds[0] > bounds[2] || bounds[1] > bounds[3] {
            return invalid();
        }
        self.select_region(
            header,
            RegionInput::Polygon(&[
                [bounds[0], bounds[1]],
                [bounds[2], bounds[1]],
                [bounds[2], bounds[3]],
                [bounds[0], bounds[3]],
            ]),
            mode,
            policy,
        )
    }
}

#[cfg(test)]
mod admission_tests {
    use super::*;
    use crate::graph_style::{semantic_paint_layers, ResolvedGraphStyle};
    fn node(p: [f64; 2]) -> NodePaint {
        let style = ResolvedGraphStyle {
            fill: [0, 0, 0, 255],
            stroke: [0; 4],
            halo: [0; 4],
            size: 1.,
            width: 0.,
            opacity: 1.,
            shape: 0,
            dash: 0,
            arrow: 0,
            state: 0,
        };
        NodePaint {
            center: p,
            style,
            layers: semantic_paint_layers(&style, 0, 0, false),
        }
    }
    #[test]
    fn exact_primitive_grid_candidate_and_work_boundaries() {
        let paint = PaintGeometry {
            nodes: vec![node([0., 0.])],
            ..Default::default()
        };
        let mut index = PickIndex {
            bounds: [-1., -1., 1., 1.],

            ..Default::default()
        };
        // Every node duplicates into all 4096 cells. Exactly the grid bound
        // succeeds; the next append allocates nothing and changes no storage.
        for _ in 0..MAX_GRAPH_PICK_GRID_ENTRIES / (GRID * GRID) {
            assert!(index.admit(Primitive::Node(0), &paint));
        }
        let before = index.clone();
        assert!(!index.admit(Primitive::Node(0), &paint));
        assert_eq!(before, index);
        let mut index = PickIndex {
            bounds: [-1e9, -1e9, 1e9, 1e9],

            ..Default::default()
        };
        // Synthetic zero-sized node lies in one cell, so primitive cap is the
        // first governing limit, without a source-sized second index.
        let mut paint = paint;
        paint.nodes[0].style.size = 0.;
        paint.nodes[0].layers.halo_extent = 0.;
        for _ in 0..MAX_GRAPH_PICK_PRIMITIVES {
            assert!(index.admit(Primitive::Node(0), &paint));
        }
        assert!(!index.admit(Primitive::Node(0), &paint));
        let cell = index.cells([0.; 4]);
        let key = cell[1] * GRID + cell[0];
        index.finish_grid(&paint);
        let grid = Arc::get_mut(&mut index.grid).unwrap();
        grid.indices.truncate(MAX_GRAPH_PICK_CANDIDATES);
        for offset in &mut grid.offsets[key + 1..] {
            *offset = MAX_GRAPH_PICK_CANDIDATES as u32;
        }
        assert_eq!(
            index
                .candidates([0.; 4], &mut Work::default())
                .unwrap()
                .len(),
            MAX_GRAPH_PICK_CANDIDATES
        );
        let grid = Arc::get_mut(&mut index.grid).unwrap();
        grid.indices.push(MAX_GRAPH_PICK_CANDIDATES as u32);
        for offset in &mut grid.offsets[key + 1..] {
            *offset += 1;
        }
        assert_eq!(
            index.candidates([0.; 4], &mut Work::default()),
            Err(InteractionStatus::Budget)
        );
        let mut work = Work(MAX_GRAPH_INTERACTION_WORK - 1);
        assert!(work.charge(1).is_ok());
        assert_eq!(work.charge(1), Err(InteractionStatus::Budget));
    }
    #[test]
    fn degraded_omits_routed_edges_even_if_only_one_piece_survives() {
        let piece = EdgePiece {
            edge: 0,
            single_piece: false,
            start: [0., 0.],
            end: [20., 0.],
            half_width: 1.,
            dash: (0., 0.),
            dash_offset: 0.,
            head: None,
        };
        let paint = PaintGeometry {
            nodes: vec![node([0., 0.]); MAX_GRAPH_PICK_PRIMITIVES + 1],
            pieces: vec![piece],
            ..Default::default()
        };
        let index = PickIndex::build(&paint);
        assert!(index.degraded && index.node_scan);
        assert!(!index
            .primitives
            .iter()
            .any(|p| matches!(p, Primitive::Piece(_))));
    }
    #[test]
    fn dashed_region_uses_paint_thickness_and_triangle_edges() {
        let e = EdgePiece {
            edge: 0,
            single_piece: true,
            start: [0., 0.],
            end: [100., 0.],
            half_width: 2.,
            dash: (6., 4.),
            dash_offset: 0.,
            head: Some([[90., 0.], [82., 4.], [82., -4.]]),
        };
        let box_ =
            |x: f64, y: f64, w: f64, h: f64| [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
        assert!(
            !piece_region(&e, &box_(7., -1., 1., 2.), &mut Work::default()).unwrap(),
            "gap must not select"
        );
        assert!(
            piece_region(&e, &box_(2., 1.5, 1., 1.), &mut Work::default()).unwrap(),
            "thickness must select"
        );
        assert!(
            piece_region(&e, &box_(85., -10., 0.1, 20.), &mut Work::default()).unwrap(),
            "crossing head boundaries select with no contained vertices"
        );
        assert_eq!(
            piece_region(
                &EdgePiece {
                    end: [1e12, 0.],
                    head: None,
                    ..e
                },
                &box_(0., 10., 1e12, 1.),
                &mut Work::default()
            ),
            Err(InteractionStatus::Budget)
        );
    }
}

#[cfg(test)]
thread_local! { static POINT_QUERY_COUNT: std::cell::Cell<u64> = const { std::cell::Cell::new(0) }; }
#[cfg(test)]
pub(super) fn point_query_count() -> u64 {
    POINT_QUERY_COUNT.with(|n| n.get())
}
