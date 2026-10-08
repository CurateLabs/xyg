//! Bounded screen-space polygon tessellation for geographic layers (#49).
//! Rings are closed projected caches; source geometry remains retained f64 (§27).
use crate::geo::GeoError;

/// Direct fill admission is deliberately bounded; spatial simplification/LOD is #50.
pub const MAX_FILL_EDGES: usize = 4096;
pub const MAX_FILL_WORK: usize = 1_000_000;
pub const MAX_FILL_TRIANGLES: usize = 65_536;

#[derive(Clone, Copy)]
struct Edge {
    a: (f64, f64),
    b: (f64, f64),
    hole: bool,
    ring: usize,
}
impl Edge {
    fn x(self, y: f64) -> f64 {
        self.a.0 + (self.b.0 - self.a.0) * ((y - self.a.1) / (self.b.1 - self.a.1))
    }
}

/// Tessellate one shell and its holes without a winding convention.
/// Each horizontal slab has constant edge order. Ring parity selects the shell
/// minus the union of holes; touching and overlapping hole intervals remain empty.
/// A crossing inside a slab fails closed rather than emitting a wrong fill.
pub fn tessellate(rings: &[(&[f64], bool)]) -> Result<Vec<[f64; 6]>, GeoError> {
    if rings.is_empty() || rings[0].1 || rings.iter().skip(1).any(|r| !r.1) {
        return Err(GeoError::InvalidArgument);
    }
    let count = rings.iter().try_fold(0usize, |n, (xy, _)| {
        if xy.len() < 8 || xy.len() % 2 != 0 {
            return Err(GeoError::InvalidArgument);
        }
        n.checked_add(xy.len() / 2 - 1)
            .ok_or(GeoError::ResourceLimit)
    })?;
    if count > MAX_FILL_EDGES {
        return Err(GeoError::ResourceLimit);
    }
    let mut edges = Vec::with_capacity(count);
    let mut ys = Vec::with_capacity(count);
    for (ring, &(xy, hole)) in rings.iter().enumerate() {
        if xy.iter().any(|v| !v.is_finite()) {
            return Err(GeoError::NonFiniteCoordinate);
        }
        if xy.iter().any(|v| v.abs() > f64::from(f32::MAX)) {
            return Err(GeoError::InvalidArgument);
        }
        if xy[..2] != xy[xy.len() - 2..] {
            return Err(GeoError::RingNotClosed);
        }
        for pair in xy.windows(4).step_by(2) {
            let a = (pair[0], pair[1]);
            let b = (pair[2], pair[3]);
            ys.push(a.1);
            if a.1 != b.1 {
                edges.push(Edge { a, b, hole, ring });
            }
        }
    }
    ys.sort_by(f64::total_cmp);
    ys.dedup();
    if ys.len().saturating_mul(edges.len()) > MAX_FILL_WORK {
        return Err(GeoError::ResourceLimit);
    }
    let mut triangles = Vec::new();
    let mut active = Vec::with_capacity(edges.len());
    let mut inside = vec![false; rings.len()];
    for slab in ys.windows(2) {
        let (y0, y1) = (slab[0], slab[1]);
        let mid = y0 + (y1 - y0) * 0.5;
        active.clear();
        active.extend(
            edges
                .iter()
                .copied()
                .filter(|e| mid > e.a.1.min(e.b.1) && mid < e.a.1.max(e.b.1)),
        );
        active.sort_by(|a, b| a.x(mid).total_cmp(&b.x(mid)).then(a.ring.cmp(&b.ring)));
        for pair in active.windows(2) {
            for y in [y0, y1] {
                let (left, right) = (pair[0].x(y), pair[1].x(y));
                let tolerance = 1e-10 * left.abs().max(right.abs()).max(1.0);
                if left > right + tolerance {
                    return Err(GeoError::InvalidArgument);
                }
            }
        }
        inside.fill(false);
        let mut holes = 0usize;
        let mut left = None;
        for edge in active.iter().copied() {
            let was_filled = inside[0] && holes == 0;
            inside[edge.ring] = !inside[edge.ring];
            if edge.hole {
                if inside[edge.ring] {
                    holes += 1;
                } else {
                    holes -= 1;
                }
            }
            let filled = inside[0] && holes == 0;
            if !was_filled && filled {
                left = Some(edge);
            } else if was_filled && !filled {
                let a: Edge = left.take().ok_or(GeoError::InvalidArgument)?;
                let (l0, l1, r0, r1) = (a.x(y0), a.x(y1), edge.x(y0), edge.x(y1));
                if [l0, l1, r0, r1].iter().any(|v| !v.is_finite()) {
                    return Err(GeoError::NonFiniteCoordinate);
                }
                // An edge-order reversal indicates an unrecorded intersection.
                let tolerance = 1e-10 * l0.abs().max(l1.abs()).max(r0.abs()).max(r1.abs()).max(1.0);
                if l0 > r0 + tolerance || l1 > r1 + tolerance {
                    return Err(GeoError::InvalidArgument);
                }
                for triangle in [[l0, y0, r0, y0, r1, y1], [l0, y0, r1, y1, l1, y1]] {
                    let area = (triangle[2] - triangle[0]) * (triangle[5] - triangle[1])
                        - (triangle[4] - triangle[0]) * (triangle[3] - triangle[1]);
                    if area != 0.0 {
                        if triangles.len() == MAX_FILL_TRIANGLES {
                            return Err(GeoError::ResourceLimit);
                        }
                        triangles.push(triangle);
                    }
                }
            }
        }
        if inside.iter().any(|&v| v) || left.is_some() {
            return Err(GeoError::InvalidArgument);
        }
    }
    Ok(triangles)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn area(triangles: &[[f64; 6]]) -> f64 {
        triangles
            .iter()
            .map(|t| ((t[2] - t[0]) * (t[5] - t[1]) - (t[4] - t[0]) * (t[3] - t[1])).abs() * 0.5)
            .sum()
    }
    const SQUARE: [f64; 10] = [0., 0., 10., 0., 10., 10., 0., 10., 0., 0.];
    #[test]
    fn holes_are_empty_independently_of_winding() {
        let hole = [2., 2., 2., 4., 4., 4., 4., 2., 2., 2.];
        assert_eq!(
            area(&tessellate(&[(&SQUARE, false), (&hole, true)]).unwrap()),
            96.
        );
        let reversed: Vec<f64> = hole.chunks_exact(2).rev().flatten().copied().collect();
        assert_eq!(
            area(&tessellate(&[(&SQUARE, false), (&reversed, true)]).unwrap()),
            96.
        );
    }
    #[test]
    fn concave_shell_preserves_empty_notch() {
        let ring = [0., 0., 10., 0., 10., 2., 2., 2., 2., 10., 0., 10., 0., 0.];
        assert_eq!(area(&tessellate(&[(&ring, false)]).unwrap()), 36.);
    }
    #[test]
    fn touching_and_overlapping_holes_use_union() {
        let a = [2., 2., 6., 2., 6., 6., 2., 6., 2., 2.];
        let b = [4., 2., 8., 2., 8., 6., 4., 6., 4., 2.];
        assert_eq!(
            area(&tessellate(&[(&SQUARE, false), (&a, true), (&b, true)]).unwrap()),
            76.
        );
        let border = [0., 0., 5., 0., 5., 10., 0., 10., 0., 0.];
        assert_eq!(
            area(&tessellate(&[(&SQUARE, false), (&border, true)]).unwrap()),
            50.
        );
    }
    #[test]
    fn malformed_and_work_attacks_fail_before_output() {
        assert_eq!(
            tessellate(&[(&[0., 0., 1., 0., 1., 1., f64::NAN, 0.], false)]),
            Err(GeoError::NonFiniteCoordinate)
        );
        let large = vec![0.; (MAX_FILL_EDGES + 2) * 2];
        assert_eq!(tessellate(&[(&large, false)]), Err(GeoError::ResourceLimit));
    }

    #[test]
    fn unrecorded_self_intersection_fails_closed() {
        let crossing = [0., 0., 10., 10., 0., 10., 8., 0., 0., 0.];
        assert_eq!(
            tessellate(&[(&crossing, false)]),
            Err(GeoError::InvalidArgument)
        );
    }
}
