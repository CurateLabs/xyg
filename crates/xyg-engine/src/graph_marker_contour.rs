//! Bounded flattening of the retained graph painter's marker SDF into Scene
//! triangles. The shared marker SDF owns the glyph; graph diamond uses the
//! graph GPU's L1 half-diameter normalization. No styles/layout are resolved.
use crate::graph_scene::Columns;
use crate::scene::{SceneRecordKind, MAX_SCENE_MARKS};
use crate::temporal::TemporalError as E;
const RAYS: usize = 512;
pub(crate) const MAX_RECORDS: usize = 8192;
fn distance(x: f64, y: f64, size: f64, shape: u8) -> f64 {
    if shape == 2 {
        return (x.abs() + y.abs() - size * 0.5) as f32 as f64;
    }
    crate::marker_geometry::symbol_sdf(x as f32, y as f32, (size * 0.5) as f32, shape) as f64
}
fn radius(direction: [f64; 2], size: f64, shape: u8, level: f64) -> f64 {
    if distance(0., 0., size, shape) >= level {
        return 0.;
    }
    let [cos, sin] = direction;
    let mut lo = 0.;
    let mut hi = size * 2. + level.abs() * 4. + 8.;
    for _ in 0..48 {
        let mid = (lo + hi) * 0.5;
        if distance(cos * mid, sin * mid, size, shape) < level {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    (lo + hi) * 0.5
}
/// Glyph boundary extrema supplement uniform rays so polygon corners are kept.
fn directions(size: f64, shape: u8, lo: f64, hi: f64) -> Vec<[f64; 2]> {
    let rays = if hi <= 0. && (1..=5).contains(&shape) {
        0
    } else {
        RAYS
    };
    let mut a: Vec<_> = (0..rays)
        .map(|i| {
            let (s, c) =
                crate::graph::portable_sin_cos(i as f64 * std::f64::consts::TAU / RAYS as f64);
            [c, s]
        })
        .collect();
    for level in [lo, hi] {
        for x in [0., size * 0.17 + level, size * 0.5 + level] {
            for y in [size * 0.17 + level, size * 0.5 + level] {
                for sx in [-1., 1.] {
                    for sy in [-1., 1.] {
                        let r = (x * x + y * y).sqrt();
                        if r > 0. {
                            a.push([sx * x / r, sy * y / r]);
                        }
                    }
                }
            }
        }
    }
    for i in 0..12 {
        let (s, c) = crate::graph::portable_sin_cos(i as f64 * std::f64::consts::TAU / 12.);
        a.push([c, s]);
    }
    // Interior offsets of the convex triangle/hexagon stay polygons. Include
    // their exact corner rays rather than oversampling every straight edge.
    if hi <= 0. && matches!(shape, 3 | 5) {
        let r = size * 0.5;
        let vertices: Vec<[f64; 2]> = if shape == 3 {
            vec![[0., -r], [-r, r], [r, r]]
        } else {
            (0..6)
                .map(|i| {
                    let (s, c) = crate::graph::portable_sin_cos(
                        -std::f64::consts::FRAC_PI_2 + i as f64 * std::f64::consts::TAU / 6.,
                    );
                    [c * r * 2. / 3f64.sqrt(), s * r * 2. / 3f64.sqrt()]
                })
                .collect()
        };
        let orientation = vertices
            .iter()
            .zip(vertices.iter().cycle().skip(1))
            .take(vertices.len())
            .map(|(p, q)| p[0] * q[1] - p[1] * q[0])
            .sum::<f64>()
            .signum();
        for level in [lo, hi] {
            for i in 0..vertices.len() {
                let p = vertices[i];
                let prev = vertices[(i + vertices.len() - 1) % vertices.len()];
                let next = vertices[(i + 1) % vertices.len()];
                let a0 = [p[0] - prev[0], p[1] - prev[1]];
                let a1 = [next[0] - p[0], next[1] - p[1]];
                let l0 = (a0[0] * a0[0] + a0[1] * a0[1]).sqrt();
                let l1 = (a1[0] * a1[0] + a1[1] * a1[1]).sqrt();
                let n0 = [orientation * a0[1] / l0, -orientation * a0[0] / l0];
                let n1 = [orientation * a1[1] / l1, -orientation * a1[0] / l1];
                let d = [(n1[0] - n0[0]) * level, (n1[1] - n0[1]) * level];
                let t = (d[0] * a1[1] - d[1] * a1[0]) / (a0[0] * a1[1] - a0[1] * a1[0]);
                let v = [
                    p[0] + n0[0] * level + a0[0] * t,
                    p[1] + n0[1] * level + a0[1] * t,
                ];
                let length = (v[0] * v[0] + v[1] * v[1]).sqrt();
                if length > 0. {
                    a.push([v[0] / length, v[1] / length]);
                }
            }
        }
    }
    let quadrant = |p: &[f64; 2]| {
        if p[1] >= 0. {
            if p[0] >= 0. {
                0
            } else {
                1
            }
        } else if p[0] < 0. {
            2
        } else {
            3
        }
    };
    crate::shared_sort::by(&mut a, |a, b| {
        quadrant(a)
            .cmp(&quadrant(b))
            .then_with(|| (b[0] * a[1]).total_cmp(&(a[0] * b[1])))
    });
    a.dedup_by(|a, b| (a[0] - b[0]).abs() + (a[1] - b[1]).abs() < 1e-12);
    a
}
pub(crate) fn record_bound(size: f64, shape: u8, lo: Option<f64>, hi: f64) -> usize {
    directions(size, shape, lo.unwrap_or(hi), hi).len() * if lo.is_some() { 6 } else { 3 }
}
pub(crate) fn append(
    c: &mut Columns,
    id: u64,
    center: [f64; 2],
    size: f64,
    shape: u8,
    lo: Option<f64>,
    hi: f64,
    color: [u8; 4],
) -> Result<(), E> {
    if color[3] == 0 || size <= 0. {
        return Ok(());
    }
    let a = directions(size, shape, lo.unwrap_or(hi), hi);
    if a.len() * 6 > MAX_RECORDS || c.kinds.len().saturating_add(a.len() * 6) > MAX_SCENE_MARKS {
        return Err(E::CapacityExceeded);
    }
    let style = c.style(color, [0; 4], 0.);
    let point = |t: [f64; 2], level: f64| {
        let r = radius(t, size, shape, level);
        [center[0] + r * t[0], center[1] + r * t[1]]
    };
    for i in 0..a.len() {
        let t = a[i];
        let u = a[(i + 1) % a.len()];
        let p = point(t, hi);
        let q = point(u, hi);
        let inner = lo.map(|level| (point(t, level), point(u, level)));
        let triangles = if let Some((r, s)) = inner {
            [[p, q, s], [p, s, r]]
        } else {
            [[center, p, q], [center, center, center]]
        };
        for tri in triangles {
            let area = (tri[1][0] - tri[0][0]) * (tri[2][1] - tri[0][1])
                - (tri[1][1] - tri[0][1]) * (tri[2][0] - tri[0][0]);
            if area.abs() < 1e-14 {
                continue;
            }
            for v in tri {
                c.row(
                    SceneRecordKind::Triangle,
                    id,
                    style,
                    0.,
                    0,
                    v[0],
                    v[1],
                    0.,
                    0.,
                )
                .map_err(|_| E::InvalidArgument)?;
            }
        }
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn all_retained_graph_focus_glyphs_have_the_required_sdf_band() {
        for shape in 0..6 {
            let mut c = Columns::default();
            append(
                &mut c,
                1,
                [20., 30.],
                12.,
                shape,
                Some(1.),
                3.,
                [1, 2, 3, 255],
            )
            .unwrap();
            assert!(c.kinds.len() > 100);
            assert!(c.kinds.len() <= MAX_RECORDS);
            for (x, y) in c.x0.iter().zip(&c.y0) {
                let d = distance(x - 20., y - 30., 12., shape);
                assert!((0.99998..=3.00002).contains(&d), "shape {shape}: {d}");
            }
        }
    }
}
