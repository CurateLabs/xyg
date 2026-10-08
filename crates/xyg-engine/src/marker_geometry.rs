//! Shared marker distance policy for native paint and browser compute.
#[inline]
fn segment_distance(p: (f32, f32), a: (f32, f32), b: (f32, f32)) -> f32 {
    let e = (b.0 - a.0, b.1 - a.1);
    let v = (p.0 - a.0, p.1 - a.1);
    let h = ((v.0 * e.0 + v.1 * e.1) / (e.0 * e.0 + e.1 * e.1)).clamp(0.0, 1.0);
    ((v.0 - e.0 * h).powi(2) + (v.1 - e.1 * h).powi(2)).sqrt()
}

#[inline]
fn triangle_sdf(p: (f32, f32), a: (f32, f32), b: (f32, f32), c: (f32, f32)) -> f32 {
    let cross = |u: (f32, f32), v: (f32, f32), q: (f32, f32)| {
        (v.0 - u.0) * (q.1 - u.1) - (v.1 - u.1) * (q.0 - u.0)
    };
    let (c0, c1, c2) = (cross(a, b, p), cross(b, c, p), cross(c, a, p));
    let inside = (c0 >= 0.0 && c1 >= 0.0 && c2 >= 0.0) || (c0 <= 0.0 && c1 <= 0.0 && c2 <= 0.0);
    let d = segment_distance(p, a, b)
        .min(segment_distance(p, b, c))
        .min(segment_distance(p, c, a));
    if inside {
        -d
    } else {
        d
    }
}

#[inline]
fn pentagon_sdf(p: (f32, f32), r: f32) -> f32 {
    // Matplotlib Path.unit_regular_polygon(5), scaled to the marker radius.
    let vertices = [
        (0.0, -r),
        (-0.951_056_54 * r, -0.309_017 * r),
        (-0.587_785_24 * r, 0.809_017 * r),
        (0.587_785_24 * r, 0.809_017 * r),
        (0.951_056_54 * r, -0.309_017 * r),
    ];
    let mut distance = f32::INFINITY;
    let mut has_positive = false;
    let mut has_negative = false;
    for index in 0..5 {
        let a = vertices[index];
        let b = vertices[(index + 1) % 5];
        distance = distance.min(segment_distance(p, a, b));
        let cross = (b.0 - a.0) * (p.1 - a.1) - (b.1 - a.1) * (p.0 - a.0);
        has_positive |= cross > 0.0;
        has_negative |= cross < 0.0;
    }
    if has_positive && has_negative {
        distance
    } else {
        -distance
    }
}

#[inline]
pub(crate) fn symbol_sdf(px: f32, py: f32, r: f32, sym: u8) -> f32 {
    match sym {
        1 => px.abs().max(py.abs()) - r,                           // square
        2 => (px.abs() + py.abs()) - r * std::f32::consts::SQRT_2, // diamond
        3 | 8 | 9 | 10 => {
            // Matplotlib's normalized triangle: apex at one edge and a
            // full-width base at the opposite edge.
            let d = match sym {
                8 => (-px, -py), // down
                9 => (-py, px),  // left
                10 => (py, -px), // right
                _ => (px, py),
            };
            triangle_sdf(d, (0.0, -r), (-r, r), (r, r))
        }
        4 => {
            // plus / cross
            let (ax, ay) = (px.abs(), py.abs());
            (ax - 0.34 * r).max(ay - r).min((ax - r).max(ay - 0.34 * r))
        }
        11 => {
            // diagonal cross (matplotlib's x/X), distinct from the plus glyph
            let qx = (px + py) * std::f32::consts::FRAC_1_SQRT_2;
            let qy = (py - px) * std::f32::consts::FRAC_1_SQRT_2;
            let (ax, ay) = (qx.abs(), qy.abs());
            (ax - 0.34 * r).max(ay - r).min((ax - r).max(ay - 0.34 * r))
        }
        13 => px.abs().max(py.abs()) - r, // snapped pixel
        14 => (px.abs() / 0.6 + py.abs()) - r * std::f32::consts::SQRT_2, // thin diamond
        15 => {
            // Unfilled plus: its width comes from markeredgewidth below.
            let (ax, ay) = (px.abs(), py.abs());
            (ax - r).max(ay).min((ay - r).max(ax))
        }
        16 => {
            // Unfilled x: rotate the same two line segments by 45 degrees.
            let qx = (px + py) * std::f32::consts::FRAC_1_SQRT_2;
            let qy = (py - px) * std::f32::consts::FRAC_1_SQRT_2;
            let (ax, ay) = (qx.abs(), qy.abs());
            (ax - r).max(ay).min((ay - r).max(ax))
        }
        17 => (px.abs() - r).max(py.abs()), // unfilled horizontal line
        18 => px.abs().max(py.abs() - r),   // unfilled vertical line
        5 => {
            // regular hexagon, pointy top (IQ SDF, x/y swapped for a top vertex)
            let (k0, k1, k2) = (-0.866_025_4_f32, 0.5_f32, 0.577_350_3_f32);
            let mut p = (py.abs(), px.abs());
            let m = (k0 * p.0 + k1 * p.1).min(0.0);
            p = (p.0 - 2.0 * m * k0, p.1 - 2.0 * m * k1);
            p = (p.0 - p.0.clamp(-k2 * r, k2 * r), p.1 - r);
            (p.0 * p.0 + p.1 * p.1).sqrt() * p.1.signum()
        }
        6 => pentagon_sdf((px, py), r),
        7 => {
            // five-pointed star, apex up (IQ SDF)
            let rf = 0.45_f32;
            let (k1x, k1y) = (0.809_017_f32, -0.587_785_25_f32);
            let (k2x, k2y) = (-k1x, k1y);
            let mut p = (px.abs(), -py); // flip y so a point faces up
            let d1 = k1x * p.0 + k1y * p.1;
            let m1 = d1.max(0.0);
            p = (p.0 - 2.0 * m1 * k1x, p.1 - 2.0 * m1 * k1y);
            let d2 = k2x * p.0 + k2y * p.1;
            let m2 = d2.max(0.0);
            p = (p.0 - 2.0 * m2 * k2x, p.1 - 2.0 * m2 * k2y);
            p = (p.0.abs(), p.1 - r);
            let ba = (rf * -k1y - 0.0, rf * k1x - 1.0);
            let h = (p.0 * ba.0 + p.1 * ba.1) / (ba.0 * ba.0 + ba.1 * ba.1);
            let h = h.clamp(0.0, r);
            let q = (p.0 - ba.0 * h, p.1 - ba.1 * h);
            (q.0 * q.0 + q.1 * q.1).sqrt() * (p.1 * ba.0 - p.0 * ba.1).signum()
        }
        _ => (px * px + py * py).sqrt() - r, // circle
    }
}

#[inline]
#[cfg(feature = "raster")]
pub(crate) fn symbol_extent(r: f32, sym: u8) -> f32 {
    crate::scene::marker_symbol_extent(f64::from(r), sym) as f32
}

fn abs_range(lo: f64, hi: f64) -> (f64, f64) {
    (
        if lo <= 0. && hi >= 0. {
            0.
        } else {
            lo.abs().min(hi.abs())
        },
        lo.abs().max(hi.abs()),
    )
}
fn interval_hit(lo: f64, hi: f64, fill: bool, stroke: bool, half: f64) -> bool {
    (fill && lo <= 0.) || (stroke && half > 0. && lo <= half && hi >= -half)
}
/// Exact piecewise-affine extrema on a rectangle: extrema occur at vertices
/// of the arrangement where any two affine branches exchange ordering.
fn affine_range(rect: [f64; 4], r: f64, symbol: u8) -> (f64, f64) {
    let rotate = matches!(symbol, 11 | 16);
    let k = std::f64::consts::FRAC_1_SQRT_2;
    let (x, y) = if rotate {
        ([k, k], [-k, k])
    } else {
        ([1., 0.], [0., 1.])
    };
    let (a, b) = match symbol {
        4 | 11 => (f64::from(0.34f32) * r, r),
        15 | 16 => (0., r),
        17 => (r, 0.),
        _ => (0., r),
    };
    let pieces = [
        [x[0], x[1], -a],
        [-x[0], -x[1], -a],
        [y[0], y[1], -b],
        [-y[0], -y[1], -b],
        [x[0], x[1], -b],
        [-x[0], -x[1], -b],
        [y[0], y[1], -a],
        [-y[0], -y[1], -a],
    ];
    let mut lines = [[0.; 3]; 32];
    let mut n = 0;
    for i in 0..8 {
        for j in i + 1..8 {
            let l = [
                pieces[i][0] - pieces[j][0],
                pieces[i][1] - pieces[j][1],
                pieces[i][2] - pieces[j][2],
            ];
            if l[0] != 0. || l[1] != 0. {
                lines[n] = l;
                n += 1;
            }
        }
    }
    for l in [
        [1., 0., -rect[0]],
        [1., 0., -rect[2]],
        [0., 1., -rect[1]],
        [0., 1., -rect[3]],
    ] {
        lines[n] = l;
        n += 1;
    }
    let mut min = f64::INFINITY;
    let mut max = f64::NEG_INFINITY;
    let evaluate = |px: f64, py: f64| {
        let qx = x[0] * px + x[1] * py;
        let qy = y[0] * px + y[1] * py;
        match symbol {
            4 | 11 | 15 | 16 => (qx.abs() - a)
                .max(qy.abs() - b)
                .min((qx.abs() - b).max(qy.abs() - a)),
            17 => (px.abs() - r).max(py.abs()),
            _ => (py.abs() - r).max(px.abs()),
        }
    };
    for i in 0..n {
        for j in i + 1..n {
            let a = lines[i];
            let b = lines[j];
            let det = a[0] * b[1] - a[1] * b[0];
            if det == 0. {
                continue;
            }
            let px = (a[1] * b[2] - a[2] * b[1]) / det;
            let py = (a[2] * b[0] - a[0] * b[2]) / det;
            if px >= rect[0] && px <= rect[2] && py >= rect[1] && py <= rect[3] {
                let value = evaluate(px, py);
                min = min.min(value);
                max = max.max(value);
            }
        }
    }
    (min, max)
}
fn point_segment(p: [f64; 2], a: [f64; 2], b: [f64; 2]) -> f64 {
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
    let x = cross(a, b, c);
    let y = cross(a, b, d);
    let z = cross(c, d, a);
    let w = cross(c, d, b);
    (x == 0. && within(c, a, b))
        || (y == 0. && within(d, a, b))
        || (z == 0. && within(a, c, d))
        || (w == 0. && within(b, c, d))
        || ((x > 0.) != (y > 0.) && (z > 0.) != (w > 0.))
}
fn polygon_rect(
    vertices: &[[f64; 2]],
    rect: [f64; 4],
    fill: bool,
    stroke: bool,
    half: f64,
) -> bool {
    let corners = [
        [rect[0], rect[1]],
        [rect[2], rect[1]],
        [rect[2], rect[3]],
        [rect[0], rect[3]],
    ];
    let mut closest = f64::INFINITY;
    let mut filled = false;
    for i in 0..vertices.len() {
        let a = vertices[i];
        let b = vertices[(i + 1) % vertices.len()];
        if a[0] >= rect[0] && a[0] <= rect[2] && a[1] >= rect[1] && a[1] <= rect[3] {
            filled = true;
            closest = 0.;
        }
        for j in 0..4 {
            let c = corners[j];
            let d = corners[(j + 1) % 4];
            if intersect(a, b, c, d) {
                closest = 0.;
                filled = true;
            }
            closest = closest
                .min(point_segment(c, a, b))
                .min(point_segment(a, c, d));
        }
    }
    for p in corners {
        let mut inside = false;
        for i in 0..vertices.len() {
            let a = vertices[i];
            let b = vertices[(i + 1) % vertices.len()];
            if (a[1] > p[1]) != (b[1] > p[1])
                && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]
            {
                inside = !inside;
            }
        }
        filled |= inside;
    }
    (fill && filled) || (stroke && half > 0. && closest <= half)
}
/// Rectangle intersection uses analytic circle/affine distance extrema or
/// exact polygon-edge distances; there is no pixel or point sampling grid.
pub(crate) fn rect_hit(
    symbol: u8,
    r: f64,
    half: f64,
    fill: bool,
    stroke: bool,
    rect: [f64; 4],
) -> bool {
    let (xmin, xmax) = abs_range(rect[0], rect[2]);
    let (ymin, ymax) = abs_range(rect[1], rect[3]);
    match symbol {
        0 | 12 => interval_hit(
            xmin.hypot(ymin) - r,
            xmax.hypot(ymax) - r,
            fill,
            stroke,
            half,
        ),
        1 | 13 => interval_hit(xmin.max(ymin) - r, xmax.max(ymax) - r, fill, stroke, half),
        2 | 14 => {
            let scale = if symbol == 14 { 0.6 } else { 1. };
            interval_hit(
                xmin / scale + ymin - r * std::f64::consts::SQRT_2,
                xmax / scale + ymax - r * std::f64::consts::SQRT_2,
                fill,
                stroke,
                half,
            )
        }
        4 | 11 | 15 | 16 | 17 | 18 => {
            let (lo, hi) = affine_range(rect, r, symbol);
            interval_hit(lo, hi, fill && !matches!(symbol, 15..=18), stroke, half)
        }
        _ => {
            let mut vertices = [[0.; 2]; 10];
            let count = match symbol {
                3 | 8 | 9 | 10 => {
                    vertices[..3].copy_from_slice(&[[0., -r], [-r, r], [r, r]]);
                    for v in &mut vertices[..3] {
                        *v = match symbol {
                            8 => [-v[0], -v[1]],
                            9 => [v[1], -v[0]],
                            10 => [-v[1], v[0]],
                            _ => *v,
                        };
                    }
                    3
                }
                6 => {
                    vertices[..5].copy_from_slice(&[
                        [0., -r],
                        [
                            -f64::from(0.951_056_54f32) * r,
                            -f64::from(0.309_017f32) * r,
                        ],
                        [-f64::from(0.587_785_24f32) * r, f64::from(0.809_017f32) * r],
                        [f64::from(0.587_785_24f32) * r, f64::from(0.809_017f32) * r],
                        [f64::from(0.951_056_54f32) * r, -f64::from(0.309_017f32) * r],
                    ]);
                    5
                }
                5 => {
                    let radius = r * 2. / 3f64.sqrt();
                    for (i, v) in vertices[..6].iter_mut().enumerate() {
                        let a =
                            -std::f64::consts::FRAC_PI_2 + i as f64 * std::f64::consts::TAU / 6.;
                        *v = [a.cos() * radius, a.sin() * radius];
                    }
                    6
                }
                _ => {
                    for (i, v) in vertices.iter_mut().enumerate() {
                        let a =
                            -std::f64::consts::FRAC_PI_2 + i as f64 * std::f64::consts::TAU / 10.;
                        let radius = if i % 2 == 0 {
                            r
                        } else {
                            f64::from(0.45f32) * r
                        };
                        *v = [a.cos() * radius, a.sin() * radius];
                    }
                    10
                }
            };
            polygon_rect(&vertices[..count], rect, fill, stroke, half)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn analytic_rectangles_match_all_canonical_symbol_interiors() {
        for symbol in 0..=18 {
            for y in -24..=24 {
                for x in -24..=24 {
                    let px = x as f64 / 2.;
                    let py = y as f64 / 2.;
                    let d = symbol_sdf(px as f32, py as f32, 10., symbol);
                    if d.abs() < 1e-4 || matches!(symbol, 15..=18) {
                        continue;
                    }
                    assert_eq!(
                        rect_hit(symbol, 10., 0., true, false, [px, py, px, py]),
                        d < 0.,
                        "symbol={symbol},p={px},{py},d={d}"
                    );
                }
            }
        }
    }
    #[test]
    fn brush_rejects_circle_corners_cross_void_and_hollow_center() {
        assert!(!rect_hit(0, 10., 0., true, false, [8., 8., 9., 9.]));
        assert!(rect_hit(0, 10., 0., true, false, [9., -1., 11., 1.]));
        assert!(!rect_hit(4, 10., 0., true, false, [5., 5., 7., 7.]));
        assert!(rect_hit(4, 10., 0., true, false, [-1., 8., 1., 12.]));
        assert!(!rect_hit(0, 10., 1., false, true, [-2., -2., 2., 2.]));
        assert!(rect_hit(0, 10., 1., false, true, [9., -1., 10., 1.]));
        assert!(!rect_hit(17, 10., 1., false, true, [-2., 3., 2., 4.]));
        assert!(rect_hit(17, 10., 1., false, true, [9., 0., 11., 0.5]));
    }
}
