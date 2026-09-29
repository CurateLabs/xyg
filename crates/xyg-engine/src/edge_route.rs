//! Deterministic directed multigraph edge routing for paint (#33).
//!
//! Hosts call this after [`crate::graph::build_render`] so Direct-tier
//! parallels, reciprocal pairs, and self-loops become visibly distinct
//! segments with optional arrowheads. Rust owns the geometry; hosts only
//! upload the returned columns.

use std::collections::HashMap;

/// Straight-line polyline segments a curved (Bezier-class) shaft tessellates
/// into. Fixed and deterministic: same input always yields the same segment
/// count and geometry, independent of host or viewport.
const CURVE_TESSELLATION_SEGMENTS: usize = 8;

/// Maximum paint segments emitted per source edge by [`edge_route_segments`].
/// Self-loops expand to three sides; a straight directed non-loop adds two
/// arrow wings to its one shaft segment; a curved directed non-loop
/// tessellates its shaft into [`CURVE_TESSELLATION_SEGMENTS`] segments and
/// adds two arrow wings. The curved+arrow case is the largest per-edge
/// footprint and sizes this constant.
pub const EDGE_ROUTE_SEGMENTS_PER_EDGE: usize = CURVE_TESSELLATION_SEGMENTS + 2;

/// Maximum paint segments per source edge when `curved == false`: a
/// three-sided self-loop, or one shaft plus two arrow wings.
pub const STRAIGHT_EDGE_ROUTE_SEGMENTS_PER_EDGE: usize = 3;

/// Per-edge output capacity [`edge_route_segments`] requires for `curved`, so
/// straight routing does not pay the curved tessellation ceiling.
pub const fn edge_route_segments_per_edge(curved: bool) -> usize {
    if curved {
        EDGE_ROUTE_SEGMENTS_PER_EDGE
    } else {
        STRAIGHT_EDGE_ROUTE_SEGMENTS_PER_EDGE
    }
}

/// Route render-graph edges into paint segments with deterministic multi-edge
/// separation, self-loop geometry, optional Bezier-class curved shafts, and
/// optional directed arrowheads (#33).
///
/// Parallel and reciprocal edges that share an undirected endpoint pair receive
/// symmetric perpendicular offsets ranked by source edge index. Self-loops emit
/// a three-segment triangular loop (unaffected by `curved`). When `curved` is
/// set, non-loop shafts follow a quadratic Bezier whose control point is
/// displaced perpendicular to the chord by the same rank-based offset used for
/// straight separation (or a small deterministic default for unbundled edges),
/// tessellated into [`CURVE_TESSELLATION_SEGMENTS`] straight sub-segments.
/// When `arrow_size > 0` and `directed`, each non-loop edge also emits two
/// arrowhead wing segments oriented along the final shaft tangent; the shaft
/// shortens so the tip meets the geometric endpoint.
///
/// Writes `out_*` columns of equal length and returns the segment count. Each
/// `out_edge_index[i]` is the source edge index that produced segment `i`.
/// Caller buffers must hold at least
/// `sources.len() * edge_route_segments_per_edge(curved)` slots (hosts may
/// allocate the [`EDGE_ROUTE_SEGMENTS_PER_EDGE`] ceiling).
#[allow(clippy::too_many_arguments)] // mirrors the C ABI buffer list
pub fn edge_route_segments(
    n_nodes: u64,
    x: &[f64],
    y: &[f64],
    sources: &[u64],
    targets: &[u64],
    directed: bool,
    separation: f64,
    loop_radius: f64,
    arrow_size: f64,
    curved: bool,
    out_x0: &mut [f64],
    out_y0: &mut [f64],
    out_x1: &mut [f64],
    out_y1: &mut [f64],
    out_edge_index: &mut [u64],
) -> Option<u64> {
    let Ok(n) = usize::try_from(n_nodes) else {
        return None;
    };
    if x.len() != n || y.len() != n || sources.len() != targets.len() {
        return None;
    }
    if !separation.is_finite()
        || separation < 0.0
        || !loop_radius.is_finite()
        || loop_radius < 0.0
        || !arrow_size.is_finite()
        || arrow_size < 0.0
    {
        return None;
    }
    let e = sources.len();
    let capacity = e.checked_mul(edge_route_segments_per_edge(curved))?;
    if out_x0.len() < capacity
        || out_y0.len() < capacity
        || out_x1.len() < capacity
        || out_y1.len() < capacity
        || out_edge_index.len() < capacity
    {
        return None;
    }

    // Bundle ranks: undirected key so reciprocal + parallel siblings separate.
    let mut bundles: HashMap<(u64, u64), Vec<usize>> = HashMap::new();
    for (i, (&s, &t)) in sources.iter().zip(targets.iter()).enumerate() {
        if s >= n_nodes || t >= n_nodes {
            return None;
        }
        let key = if s <= t { (s, t) } else { (t, s) };
        bundles.entry(key).or_default().push(i);
    }
    let mut rank = vec![0i32; e];
    let mut bundle_size = vec![1i32; e];
    for members in bundles.values_mut() {
        members.sort_unstable();
        let size = members.len() as i32;
        for (r, &idx) in members.iter().enumerate() {
            rank[idx] = r as i32;
            bundle_size[idx] = size;
        }
    }

    let mut written = 0usize;
    let mut emit = |edge_i: u64, x0: f64, y0: f64, x1: f64, y1: f64| {
        if !x0.is_finite() || !y0.is_finite() || !x1.is_finite() || !y1.is_finite() {
            return;
        }
        out_x0[written] = x0;
        out_y0[written] = y0;
        out_x1[written] = x1;
        out_y1[written] = y1;
        out_edge_index[written] = edge_i;
        written += 1;
    };

    for i in 0..e {
        let s = sources[i] as usize;
        let t = targets[i] as usize;
        let sx = x[s];
        let sy = y[s];
        let tx = x[t];
        let ty = y[t];
        if !sx.is_finite() || !sy.is_finite() || !tx.is_finite() || !ty.is_finite() {
            continue;
        }
        let edge_i = i as u64;
        let size = bundle_size[i];
        let offset = if size <= 1 || separation == 0.0 {
            0.0
        } else {
            (rank[i] as f64 - 0.5 * (size - 1) as f64) * separation
        };

        if s == t {
            // Triangular self-loop, oriented by bundle rank for stacked loops.
            let r = if loop_radius > 0.0 {
                loop_radius
            } else {
                separation.max(0.35)
            };
            let theta = std::f64::consts::FRAC_PI_2
                + (rank[i] as f64) * (std::f64::consts::TAU / size.max(1) as f64);
            let (st, ct) = theta.sin_cos();
            let cx = sx + r * ct;
            let cy = sy + r * st;
            let px = -st;
            let py = ct;
            let a_x = cx + 0.7 * r * px;
            let a_y = cy + 0.7 * r * py;
            let b_x = cx - 0.7 * r * px;
            let b_y = cy - 0.7 * r * py;
            emit(edge_i, sx, sy, a_x, a_y);
            emit(edge_i, a_x, a_y, b_x, b_y);
            emit(edge_i, b_x, b_y, sx, sy);
            continue;
        }

        let dx = tx - sx;
        let dy = ty - sy;
        let len = dx.hypot(dy);
        if len == 0.0 {
            continue;
        }
        // Offset normal lives in the bundle's canonical (low → high node)
        // frame so a reciprocal edge's rank offset lands on its own side of
        // the chord instead of mirroring onto a sibling.
        let (ux, uy) = if s <= t {
            (-dy / len, dx / len)
        } else {
            (dy / len, -dx / len)
        };
        let x0 = sx + offset * ux;
        let y0 = sy + offset * uy;
        let mut x1 = tx + offset * ux;
        let mut y1 = ty + offset * uy;

        if curved {
            // Bezier-class routing (#33): bow the shaft off its chord by a
            // rank-signed amount so reciprocal/parallel curved edges fan out
            // just like the straight-offset siblings, then tessellate into a
            // fixed number of straight sub-segments so the client keeps
            // drawing ordinary segments. A default floor keeps unbundled
            // edges visibly curved even with `separation == 0`.
            let curve_sep = if separation > 0.0 { separation } else { 0.12 };
            let bow = if size <= 1 {
                curve_sep
            } else {
                (rank[i] as f64 - 0.5 * (size - 1) as f64) * curve_sep
            };
            let cx = (x0 + x1) * 0.5 + bow * ux;
            let cy = (y0 + y1) * 0.5 + bow * uy;
            let bezier = |t: f64| {
                let mt = 1.0 - t;
                (
                    mt * mt * x0 + 2.0 * mt * t * cx + t * t * x1,
                    mt * mt * y0 + 2.0 * mt * t * cy + t * t * y1,
                )
            };
            let k = CURVE_TESSELLATION_SEGMENTS;
            let mut points = Vec::with_capacity(k + 1);
            for step in 0..=k {
                points.push(bezier(step as f64 / k as f64));
            }
            let last = points.len() - 1;
            let (tip_x, tip_y) = points[last];
            let (prev_x, prev_y) = points[last - 1];
            let tangent_dx = tip_x - prev_x;
            let tangent_dy = tip_y - prev_y;
            let tangent_len = tangent_dx.hypot(tangent_dy);
            if directed && arrow_size > 0.0 && tangent_len > 0.0 {
                let inset = arrow_size.min(0.45 * tangent_len);
                let inv = 1.0 / tangent_len;
                let back_x = tip_x - tangent_dx * inv * arrow_size;
                let back_y = tip_y - tangent_dy * inv * arrow_size;
                let shaft_end_x = tip_x - tangent_dx * inv * inset;
                let shaft_end_y = tip_y - tangent_dy * inv * inset;
                points[last] = (shaft_end_x, shaft_end_y);
                for w in 0..last {
                    emit(
                        edge_i,
                        points[w].0,
                        points[w].1,
                        points[w + 1].0,
                        points[w + 1].1,
                    );
                }
                let wing_ux = -tangent_dy * inv;
                let wing_uy = tangent_dx * inv;
                let wing = arrow_size * 0.45;
                emit(
                    edge_i,
                    tip_x,
                    tip_y,
                    back_x + wing_ux * wing,
                    back_y + wing_uy * wing,
                );
                emit(
                    edge_i,
                    tip_x,
                    tip_y,
                    back_x - wing_ux * wing,
                    back_y - wing_uy * wing,
                );
            } else {
                // No arrow requested, or a degenerate final tangent (coincident
                // tessellation points) — draw the plain curved shaft.
                for w in 0..last {
                    emit(
                        edge_i,
                        points[w].0,
                        points[w].1,
                        points[w + 1].0,
                        points[w + 1].1,
                    );
                }
            }
            continue;
        }

        if directed && arrow_size > 0.0 {
            let inset = arrow_size.min(0.45 * len);
            let inv = 1.0 / len;
            let tip_x = x1;
            let tip_y = y1;
            x1 -= dx * inv * inset;
            y1 -= dy * inv * inset;
            // Shaft stops short of the tip so the arrowhead owns the endpoint.
            emit(edge_i, x0, y0, x1, y1);
            let back_x = tip_x - dx * inv * arrow_size;
            let back_y = tip_y - dy * inv * arrow_size;
            let wing = arrow_size * 0.45;
            emit(edge_i, tip_x, tip_y, back_x + ux * wing, back_y + uy * wing);
            emit(edge_i, tip_x, tip_y, back_x - ux * wing, back_y - uy * wing);
        } else {
            emit(edge_i, x0, y0, x1, y1);
        }
    }

    Some(written as u64)
}

/// Screen-space arrowhead length in CSS px (matches the Scene straight-arrow
/// head so graph and annotation arrows read the same).
pub const GRAPH_EDGE_HEAD_LENGTH_PX: f64 = 8.0;
/// Screen-space arrowhead half-width in CSS px.
pub const GRAPH_EDGE_HEAD_HALF_WIDTH_PX: f64 = 4.0;
/// `f64` values per segment in [`edge_route_segments_with_ends`] `out_ends`:
/// start border radius (px), end border radius (px), head length (px; 0 = none).
pub const EDGE_ENDS_STRIDE: usize = 3;

/// Per-endpoint Scene flag byte for border-aware graph edges (#33): marks a
/// Polyline point as a graph edge end (`EDGE_END_MARK`), requests an arrowhead
/// at that end (`EDGE_END_HEAD`), and carries the node outline in the low bits
/// (`EDGE_END_SHAPE_MASK`, a [`NodeShape`] code). Packed by `scene_pack`
/// (`PACK_EDGE_SEGMENT`) and consumed by the Scene pixel pass.
pub const EDGE_END_MARK: u8 = 0x80;
pub const EDGE_END_HEAD: u8 = 0x40;
pub const EDGE_END_SHAPE_MASK: u8 = 0x03;
/// Per-segment flag byte in `out_ends[2]`: [`EDGE_END_HEAD`], end-node shape in
/// bits 0-1, start-node shape in bits 2-3 (`EDGE_START_SHAPE_SHIFT`).
pub const EDGE_START_SHAPE_SHIFT: u8 = 2;
pub const EDGE_SEGMENT_FLAG_MASK: u8 =
    EDGE_END_HEAD | EDGE_END_SHAPE_MASK | (EDGE_END_SHAPE_MASK << EDGE_START_SHAPE_SHIFT);

/// Node marker outline used for border-aware edge trimming (#33).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NodeShape {
    Circle = 0,
    Square = 1,
    Diamond = 2,
}

impl NodeShape {
    /// Map a scatter symbol name to its trimming outline. Symbols without an
    /// exact rule (triangle, star, …) use their circumscribed circle.
    pub fn from_symbol(symbol: &str) -> NodeShape {
        match symbol {
            "square" => NodeShape::Square,
            "diamond" => NodeShape::Diamond,
            _ => NodeShape::Circle,
        }
    }

    /// Map a scatter symbol code (`circle`=0, `square`=1, `diamond`=2, …).
    pub fn from_symbol_code(code: u8) -> NodeShape {
        Self::from_code(code)
    }

    pub fn from_code(code: u8) -> NodeShape {
        match code {
            1 => NodeShape::Square,
            2 => NodeShape::Diamond,
            _ => NodeShape::Circle,
        }
    }
}

impl NodeShape {
    fn code(self) -> u8 {
        self as u8
    }
}

/// Distance from a node's center to its outline along the unit screen
/// direction `(ux, uy)`, for a marker of `radius` px (half its size). The
/// WebGL segment shader (`xyEdgeBorder` in `js/src/40_gl.ts`) mirrors this.
pub fn node_border_distance(shape: NodeShape, radius: f64, ux: f64, uy: f64) -> f64 {
    if !(radius > 0.0) {
        return 0.0;
    }
    let (ax, ay) = (ux.abs(), uy.abs());
    match shape {
        NodeShape::Circle => radius,
        NodeShape::Square => radius / ax.max(ay).max(1e-12),
        NodeShape::Diamond => std::f64::consts::SQRT_2 * radius / (ax + ay).max(1e-12),
    }
}

/// Route edges for screen-space, border-aware paint (#33).
///
/// Geometry is [`edge_route_segments`] with data-space arrows disabled (shaft
/// pieces only: 1 straight, 3 per self-loop, `CURVE_TESSELLATION_SEGMENTS`
/// curved). `out_ends` receives [`EDGE_ENDS_STRIDE`] values per segment: the
/// first piece of an edge carries its source node's border radius, the last
/// piece its target node's radius, and a flag byte (as `f64`) with
/// [`EDGE_END_HEAD`] when `directed` plus each end node's [`NodeShape`] code
/// (end in bits 0-1, start in bits 2-3). Interior curve pieces carry zero
/// radii. Painters trim each end by [`node_border_distance`] along the piece's
/// screen direction and draw a [`GRAPH_EDGE_HEAD_LENGTH_PX`] head at the trimmed
/// tip, so tips meet node outlines at every zoom. `node_radius_px` and
/// `node_symbol` (scatter symbol codes) are per render node; empty means no
/// trim / circles.
#[allow(clippy::too_many_arguments)] // mirrors the C ABI buffer list
pub fn edge_route_segments_with_ends(
    n_nodes: u64,
    x: &[f64],
    y: &[f64],
    sources: &[u64],
    targets: &[u64],
    directed: bool,
    separation: f64,
    loop_radius: f64,
    curved: bool,
    node_radius_px: &[f64],
    node_symbol: &[u8],
    out_x0: &mut [f64],
    out_y0: &mut [f64],
    out_x1: &mut [f64],
    out_y1: &mut [f64],
    out_edge_index: &mut [u64],
    out_ends: &mut [f64],
) -> Option<u64> {
    if !node_radius_px.is_empty()
        && (node_radius_px.len() != x.len()
            || node_radius_px.iter().any(|r| !r.is_finite() || *r < 0.0))
    {
        return None;
    }
    if !node_symbol.is_empty() && node_symbol.len() != x.len() {
        return None;
    }
    let capacity = sources
        .len()
        .checked_mul(edge_route_segments_per_edge(curved))?;
    if out_ends.len() < capacity.checked_mul(EDGE_ENDS_STRIDE)? {
        return None;
    }
    let written = edge_route_segments(
        n_nodes,
        x,
        y,
        sources,
        targets,
        directed,
        separation,
        loop_radius,
        0.0,
        curved,
        out_x0,
        out_y0,
        out_x1,
        out_y1,
        out_edge_index,
    )? as usize;
    let radius = |node: u64| node_radius_px.get(node as usize).copied().unwrap_or(0.0);
    let shape = |node: u64| {
        NodeShape::from_symbol_code(node_symbol.get(node as usize).copied().unwrap_or(0)).code()
    };
    out_ends[..written * EDGE_ENDS_STRIDE].fill(0.0);
    // Pieces of one edge are emitted contiguously; stamp the run's ends.
    let mut start = 0;
    while start < written {
        let edge = out_edge_index[start];
        let mut end = start + 1;
        while end < written && out_edge_index[end] == edge {
            end += 1;
        }
        let e = edge as usize;
        out_ends[start * EDGE_ENDS_STRIDE] = radius(sources[e]);
        let last = (end - 1) * EDGE_ENDS_STRIDE;
        out_ends[last + 1] = radius(targets[e]);
        let start_shape = shape(sources[e]) << EDGE_START_SHAPE_SHIFT;
        let end_shape = shape(targets[e]);
        for piece in start..end {
            let at = piece * EDGE_ENDS_STRIDE + 2;
            let head = if directed && piece == end - 1 {
                EDGE_END_HEAD
            } else {
                0
            };
            out_ends[at] = f64::from(head | start_shape | end_shape);
        }
        start = end;
    }
    Some(written as u64)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn separates_parallels_and_emits_loop_and_arrows() {
        let x = [0.0, 2.0, 4.0];
        let y = [0.0, 0.0, 0.0];
        let sources = [0u64, 0, 2];
        let targets = [1u64, 1, 2];
        let cap = sources.len() * EDGE_ROUTE_SEGMENTS_PER_EDGE;
        let mut ox0 = vec![0.0; cap];
        let mut oy0 = vec![0.0; cap];
        let mut ox1 = vec![0.0; cap];
        let mut oy1 = vec![0.0; cap];
        let mut eidx = vec![0u64; cap];
        let n = edge_route_segments(
            3, &x, &y, &sources, &targets, true, 0.2, 0.5, 0.15, false, &mut ox0, &mut oy0,
            &mut ox1, &mut oy1, &mut eidx,
        )
        .expect("route");
        // Two parallel edges × (shaft + 2 wings) + one 3-segment loop = 9.
        assert_eq!(n, 9);
        let shaft0_y = oy0[0];
        let shaft1_y = oy0[3];
        assert!((shaft0_y - shaft1_y).abs() > 1e-9);
        let loop_segs = eidx[..n as usize].iter().filter(|&&e| e == 2).count();
        assert_eq!(loop_segs, 3);
    }

    #[test]
    fn curved_routing_tessellates_and_orients_arrow_along_final_tangent() {
        let x = [0.0, 4.0, 4.0];
        let y = [0.0, 0.0, 0.0];
        let sources = [0u64, 1, 0];
        let targets = [1u64, 0, 1];
        let cap = sources.len() * EDGE_ROUTE_SEGMENTS_PER_EDGE;
        let mut ox0 = vec![0.0; cap];
        let mut oy0 = vec![0.0; cap];
        let mut ox1 = vec![0.0; cap];
        let mut oy1 = vec![0.0; cap];
        let mut eidx = vec![0u64; cap];
        let n = edge_route_segments(
            3, &x, &y, &sources, &targets, true, 0.2, 0.5, 0.15, true, &mut ox0, &mut oy0,
            &mut ox1, &mut oy1, &mut eidx,
        )
        .expect("route");
        // Each reciprocal edge: CURVE_TESSELLATION_SEGMENTS shaft pieces + 2
        // wings; the third source/target pair (0->1 again) duplicates edge 0's
        // bundle, adding a third reciprocal sibling — every member still gets
        // the full curved+arrow footprint.
        assert_eq!(n, 3 * (CURVE_TESSELLATION_SEGMENTS as u64 + 2));
        // Bundle siblings hold distinct ranks, so their curved midpoints must
        // diverge (edge 0 and edge 1 sit at different ranks of the 3-bundle).
        let mid0 = eidx[..n as usize]
            .iter()
            .position(|&e| e == 0)
            .map(|i| oy0[i + CURVE_TESSELLATION_SEGMENTS / 2])
            .unwrap();
        let mid1 = eidx[..n as usize]
            .iter()
            .position(|&e| e == 1)
            .map(|i| oy0[i + CURVE_TESSELLATION_SEGMENTS / 2])
            .unwrap();
        assert!((mid0 - mid1).abs() > 1e-9);
        // The curved shaft is deterministic: routing twice yields bit-identical
        // geometry.
        let mut ox0b = vec![0.0; cap];
        let mut oy0b = vec![0.0; cap];
        let mut ox1b = vec![0.0; cap];
        let mut oy1b = vec![0.0; cap];
        let mut eidxb = vec![0u64; cap];
        let n2 = edge_route_segments(
            3, &x, &y, &sources, &targets, true, 0.2, 0.5, 0.15, true, &mut ox0b, &mut oy0b,
            &mut ox1b, &mut oy1b, &mut eidxb,
        )
        .expect("route");
        assert_eq!(n, n2);
        assert_eq!(ox0[..n as usize], ox0b[..n as usize]);
        assert_eq!(oy0[..n as usize], oy0b[..n as usize]);
        assert_eq!(eidx[..n as usize], eidxb[..n as usize]);
    }

    #[test]
    fn border_distance_matches_marker_outlines() {
        let r = 8.0;
        let d = std::f64::consts::FRAC_1_SQRT_2;
        assert_eq!(node_border_distance(NodeShape::Circle, r, 0.6, 0.8), r);
        // Square: half side along an axis, half diagonal at 45 degrees.
        assert!((node_border_distance(NodeShape::Square, r, 1.0, 0.0) - r).abs() < 1e-12);
        assert!((node_border_distance(NodeShape::Square, r, d, d) - r * 2f64.sqrt()).abs() < 1e-9);
        // Diamond: vertex radius sqrt(2) r on axis, r across a face.
        assert!(
            (node_border_distance(NodeShape::Diamond, r, 0.0, -1.0) - r * 2f64.sqrt()).abs() < 1e-9
        );
        assert!((node_border_distance(NodeShape::Diamond, r, d, d) - r).abs() < 1e-9);
        assert_eq!(node_border_distance(NodeShape::Square, 0.0, 1.0, 0.0), 0.0);
        assert_eq!(NodeShape::from_symbol_code(1), NodeShape::Square);
        assert_eq!(NodeShape::from_symbol_code(2), NodeShape::Diamond);
        assert_eq!(NodeShape::from_symbol_code(7), NodeShape::Circle);
    }

    #[test]
    fn ends_stamp_first_and_last_piece_without_data_space_wings() {
        let x = [0.0, 4.0];
        let y = [0.0, 0.0];
        let (sources, targets) = ([0u64, 1], [1u64, 1]);
        for curved in [false, true] {
            let cap = sources.len() * edge_route_segments_per_edge(curved);
            let (mut a, mut b, mut c, mut d) = (
                vec![0.0; cap],
                vec![0.0; cap],
                vec![0.0; cap],
                vec![0.0; cap],
            );
            let mut index = vec![0u64; cap];
            let mut ends = vec![f64::NAN; cap * EDGE_ENDS_STRIDE];
            let n = edge_route_segments_with_ends(
                2,
                &x,
                &y,
                &sources,
                &targets,
                true,
                0.2,
                0.5,
                curved,
                &[3.0, 5.0],
                &[0, 1],
                &mut a,
                &mut b,
                &mut c,
                &mut d,
                &mut index,
                &mut ends,
            )
            .expect("ends") as usize;
            let pieces = if curved {
                CURVE_TESSELLATION_SEGMENTS
            } else {
                1
            };
            // Shaft pieces only (no wings) plus a 3-sided loop.
            assert_eq!(n, pieces + 3);
            let row = |i: usize| &ends[i * 3..i * 3 + 3];
            assert_eq!(row(0)[0], 3.0);
            assert_eq!(row(pieces - 1)[1], 5.0);
            assert_eq!(row(pieces - 1)[2] as u8, EDGE_END_HEAD | 1);
            if curved {
                // Interior pieces: no trim, no head (shape bits are inert).
                assert_eq!(&row(1)[..2], &[0.0, 0.0][..]);
                assert_eq!(row(1)[2] as u8 & EDGE_END_HEAD, 0);
            }
            // Loop on the square node: starts and ends there, head at the end.
            let square = 1 | (1 << EDGE_START_SHAPE_SHIFT);
            assert_eq!(row(pieces), &[5.0, 0.0, f64::from(square)][..]);
            assert_eq!(
                row(n - 1),
                &[0.0, 5.0, f64::from(EDGE_END_HEAD | square)][..]
            );
        }
        // Radii and symbols must be one per node.
        let mut buf = vec![0.0; 6];
        let mut idx = vec![0u64; 6];
        let mut ends = vec![0.0; 18];
        assert!(edge_route_segments_with_ends(
            2,
            &x,
            &y,
            &sources,
            &targets,
            true,
            0.2,
            0.5,
            false,
            &[3.0],
            &[],
            &mut buf.clone(),
            &mut buf.clone(),
            &mut buf.clone(),
            &mut buf,
            &mut idx,
            &mut ends,
        )
        .is_none());
    }

    #[test]
    fn capacity_contract_tracks_curve_mode() {
        // Directed parallel pair + self-loop: every straight edge fits the
        // 3-slot straight contract; curved routing requires the full ceiling.
        let x = [0.0, 4.0];
        let y = [0.0, 0.0];
        let sources = [0u64, 0, 1];
        let targets = [1u64, 1, 1];
        let route = |curved: bool, per_edge: usize| {
            let cap = sources.len() * per_edge;
            let (mut a, mut b, mut c, mut d) = (
                vec![0.0; cap],
                vec![0.0; cap],
                vec![0.0; cap],
                vec![0.0; cap],
            );
            let mut eidx = vec![0u64; cap];
            edge_route_segments(
                2, &x, &y, &sources, &targets, true, 0.2, 0.5, 0.15, curved, &mut a, &mut b,
                &mut c, &mut d, &mut eidx,
            )
        };
        let straight = STRAIGHT_EDGE_ROUTE_SEGMENTS_PER_EDGE;
        assert_eq!(route(false, straight), Some(9));
        assert_eq!(route(true, straight), None);
        assert!(route(true, EDGE_ROUTE_SEGMENTS_PER_EDGE).is_some());
    }

    #[test]
    fn reciprocal_siblings_never_share_a_route() {
        // A plain reciprocal pair and a mixed parallel+reciprocal bundle: the
        // offset normal must not flip with edge direction, or a reversed edge
        // mirrors onto a sibling's side of the chord and hides it.
        let x = [0.0, 4.0];
        let y = [0.0, 0.0];
        for (sources, targets) in [
            (vec![0u64, 1], vec![1u64, 0]),
            (vec![0u64, 0, 1], vec![1u64, 1, 0]),
        ] {
            for curved in [false, true] {
                let cap = sources.len() * EDGE_ROUTE_SEGMENTS_PER_EDGE;
                let mut ox0 = vec![0.0; cap];
                let mut oy0 = vec![0.0; cap];
                let mut ox1 = vec![0.0; cap];
                let mut oy1 = vec![0.0; cap];
                let mut eidx = vec![0u64; cap];
                let n = edge_route_segments(
                    2, &x, &y, &sources, &targets, true, 0.2, 0.5, 0.15, curved, &mut ox0,
                    &mut oy0, &mut ox1, &mut oy1, &mut eidx,
                )
                .expect("route") as usize;
                // Midpoint of each edge's shaft (x == 2 on this horizontal chord).
                let mids: Vec<f64> = (0..sources.len() as u64)
                    .map(|e| {
                        let first = eidx[..n].iter().position(|&k| k == e).unwrap();
                        if curved {
                            oy0[first + CURVE_TESSELLATION_SEGMENTS / 2]
                        } else {
                            0.5 * (oy0[first] + oy1[first])
                        }
                    })
                    .collect();
                for a in 0..mids.len() {
                    for b in a + 1..mids.len() {
                        assert!(
                            (mids[a] - mids[b]).abs() > 1e-6,
                            "edges {a} and {b} overlap (curved={curved}): {mids:?}"
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn curved_singleton_edge_bows_off_the_chord() {
        let x = [0.0, 4.0];
        let y = [0.0, 0.0];
        let sources = [0u64];
        let targets = [1u64];
        let cap = sources.len() * EDGE_ROUTE_SEGMENTS_PER_EDGE;
        let mut ox0 = vec![0.0; cap];
        let mut oy0 = vec![0.0; cap];
        let mut ox1 = vec![0.0; cap];
        let mut oy1 = vec![0.0; cap];
        let mut eidx = vec![0u64; cap];
        // separation == 0.0: curved mode still applies its deterministic
        // default bow rather than collapsing to a straight chord.
        let n = edge_route_segments(
            2, &x, &y, &sources, &targets, false, 0.0, 0.5, 0.0, true, &mut ox0, &mut oy0,
            &mut ox1, &mut oy1, &mut eidx,
        )
        .expect("route");
        assert_eq!(n, CURVE_TESSELLATION_SEGMENTS as u64);
        let midpoint_y = oy1[CURVE_TESSELLATION_SEGMENTS / 2 - 1];
        assert!(
            midpoint_y.abs() > 1e-6,
            "expected the midpoint off the x-axis chord"
        );
    }
}
