//! Scene straight-arrow shape vocabulary and geometry (#1006).
//!
//! One Rust implementation of the end decorations, shrink and label clearance
//! a static annotation arrow can carry. Scene encode, the XYST arrow-metric
//! pass and batch validation all derive the same polyline and fill from it, so
//! the SVG, raster and PDF exporters (which paint Scene `Polyline` / `PolyFill`
//! records) cannot drift between hosts.
//!
//! Admitted vocabulary (anything else fails closed at pack time):
//!
//! | head      | tail   | Matplotlib arrowstyle |
//! |-----------|--------|-----------------------|
//! | triangle  | none   | `-\|>` (default)      |
//! | v (open)  | none   | `->`                  |
//! | none      | v      | `<-`                  |
//! | v         | v      | `<->`                 |
//! | none      | none   | `-`                   |
//!
//! Heads are filled triangles or open "V" wings at the shared 8 px (or
//! XYST-metric) head size; a triangle tail, bars and curved shafts are not
//! encoded. Shrink is `start_offset` (anchor → label-box centre), `gap_start` /
//! `gap_end` along the shaft, and `label_clear` (the label box extents the
//! shaft leaves), all in screen pixels through [`crate::arrow_geom`].
//!
//! Record grammar of a straight-arrow run (annotation tag 5), shaft vertices
//! first and an optional 3-vertex head fill last:
//!
//! | polyline | fill | contents                                         |
//! |----------|------|--------------------------------------------------|
//! | 2        | 0    | `[p0, p1]`                                       |
//! | 2        | 3    | `[p0, base]`, `[tip, base+side, base-side]`      |
//! | 5        | 0    | `[p0, p1, wing, p1, wing]` (V at `p1`)           |
//! | 5        | 3    | `[wing, p0, wing, p0, base]`, head fill          |
//! | 8        | 0    | `[wing, p0, wing, p0, p1, wing, p1, wing]`       |
//!
//! A tail-only V is the V of the reversed arrow, so `<-` is the 5/0 form drawn
//! from `p1` to `p0`; the run never needs to say which end is which.

use crate::arrow_geom::{label_clear_exit, ARROW_STYLE_LEN};
use crate::scene::{SceneError, STRAIGHT_ARROW_HEAD_LENGTH};

/// Largest accepted pixel magnitude of any authored shrink / clearance fact.
pub const ARROW_MAX_PIXELS: f64 = 4096.0;

/// How one end of a straight arrow is decorated.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum ArrowEnd {
    None = 0,
    Triangle = 1,
    Open = 2,
}

impl ArrowEnd {
    pub fn from_code(code: u8) -> Option<Self> {
        match code {
            0 => Some(Self::None),
            1 => Some(Self::Triangle),
            2 => Some(Self::Open),
            _ => None,
        }
    }

    /// Host style names (`head_style` / `tail_style`).
    pub fn from_name(name: &str) -> Option<Self> {
        match name {
            "none" => Some(Self::None),
            "triangle" => Some(Self::Triangle),
            "v" => Some(Self::Open),
            _ => None,
        }
    }
}

/// Screen-space facts of one straight arrow beyond its data endpoints.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ArrowShape {
    pub head: ArrowEnd,
    pub tail: ArrowEnd,
    /// Pixel offset applied to the projected start (anchor → label centre).
    pub start_offset: [f64; 2],
    pub gap_start: f64,
    pub gap_end: f64,
    /// Label box extents `[left, right, up, down]` the shaft must leave.
    pub label_clear: [f64; 4],
}

impl ArrowShape {
    /// The pre-vocabulary arrow: filled triangle head, nothing else.
    pub const DEFAULT: Self = Self {
        head: ArrowEnd::Triangle,
        tail: ArrowEnd::None,
        start_offset: [0.0; 2],
        gap_start: 0.0,
        gap_end: 0.0,
        label_clear: [0.0; 4],
    };

    /// Whether this shape is encodable. A triangle tail is outside the
    /// admitted set, and every pixel fact must be finite and bounded.
    pub fn is_admitted(&self) -> bool {
        self.tail != ArrowEnd::Triangle
            && self
                .start_offset
                .iter()
                .all(|v| v.abs() <= ARROW_MAX_PIXELS)
            && [self.gap_start, self.gap_end]
                .iter()
                .chain(&self.label_clear)
                .all(|v| (0.0..=ARROW_MAX_PIXELS).contains(v))
    }

    /// Number of Scene records (polyline + fill) the arrow paints.
    pub fn record_count(&self) -> usize {
        2 + 3 * usize::from(self.tail == ArrowEnd::Open)
            + 3 * usize::from(self.head != ArrowEnd::None)
    }
}

/// Longest run: V tail (4 vertices), shaft end, V head (4 vertices) is 8 line
/// vertices; a filled head adds 3 fill vertices to a 5-vertex line at most.
const ARROW_MAX_VERTICES: usize = 8;

/// Polyline vertices and optional 3-vertex head fill of one arrow, in a fixed
/// buffer (the browser WASM artifact has a hard raw-size budget).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ArrowPaint {
    points: [[f64; 2]; ARROW_MAX_VERTICES + 3],
    lines: usize,
    fills: usize,
}

impl ArrowPaint {
    fn new() -> Self {
        Self {
            points: [[0.0; 2]; ARROW_MAX_VERTICES + 3],
            lines: 0,
            fills: 0,
        }
    }

    fn push(&mut self, point: [f64; 2]) {
        self.points[self.lines] = point;
        self.lines += 1;
    }

    /// Shaft (and open-head) vertices, drawn as one stroked polyline.
    pub fn line(&self) -> &[[f64; 2]] {
        &self.points[..self.lines]
    }

    /// The filled head triangle's vertices, or none.
    pub fn fill(&self) -> &[[f64; 2]] {
        &self.points[self.lines..self.lines + self.fills]
    }

    /// Records in painter order (line vertices, then fill vertices) as
    /// `(is_fill, vertex)`.
    pub fn records(&self) -> impl Iterator<Item = (bool, [f64; 2])> + '_ {
        let lines = self.lines;
        self.points[..lines + self.fills]
            .iter()
            .enumerate()
            .map(move |(i, p)| (i >= lines, *p))
    }
}

fn unit(from: [f64; 2], to: [f64; 2]) -> Option<([f64; 2], f64)> {
    let length = (to[0] - from[0]).hypot(to[1] - from[1]);
    (length.is_finite() && length > 0.0).then(|| {
        (
            [(to[0] - from[0]) / length, (to[1] - from[1]) / length],
            length,
        )
    })
}

/// Head corners behind `tip` for a head pointing along `direction`.
#[inline(never)]
fn head_corners(tip: [f64; 2], direction: [f64; 2], head: f64) -> ([f64; 2], [f64; 2], [f64; 2]) {
    let base = [tip[0] - direction[0] * head, tip[1] - direction[1] * head];
    let side = [-direction[1] * head * 0.5, direction[0] * head * 0.5];
    (
        base,
        [base[0] + side[0], base[1] + side[1]],
        [base[0] - side[0], base[1] - side[1]],
    )
}

/// Canonical paint of an arrow from `p0` to `p1` (already trimmed).
#[inline(never)]
pub fn arrow_paint(
    p0: [f64; 2],
    p1: [f64; 2],
    head: ArrowEnd,
    tail: ArrowEnd,
    head_length: f64,
) -> Result<ArrowPaint, SceneError> {
    if head == ArrowEnd::None && tail == ArrowEnd::Open {
        // `<-` is `->` of the reversed arrow.
        return arrow_paint(p1, p0, ArrowEnd::Open, ArrowEnd::None, head_length);
    }
    if tail == ArrowEnd::Triangle {
        return Err(SceneError::Length);
    }
    let (u, length) = unit(p0, p1).ok_or(SceneError::Length)?;
    let ends = usize::from(head != ArrowEnd::None) + usize::from(tail != ArrowEnd::None);
    if !head_length.is_finite() || length <= head_length * ends as f64 {
        return Err(SceneError::Length);
    }
    let mut paint = ArrowPaint::new();
    if tail == ArrowEnd::Open {
        let (_, wing_a, wing_b) = head_corners(p0, [-u[0], -u[1]], head_length);
        for point in [wing_a, p0, wing_b, p0] {
            paint.push(point);
        }
    } else {
        paint.push(p0);
    }
    match head {
        ArrowEnd::None => paint.push(p1),
        ArrowEnd::Triangle => {
            let (base, wing_a, wing_b) = head_corners(p1, u, head_length);
            paint.push(base);
            // The fill follows the finished polyline in the same buffer.
            paint.points[paint.lines..paint.lines + 3].copy_from_slice(&[p1, wing_a, wing_b]);
            paint.fills = 3;
        }
        ArrowEnd::Open => {
            let (_, wing_a, wing_b) = head_corners(p1, u, head_length);
            for point in [p1, wing_a, p1, wing_b] {
                paint.push(point);
            }
        }
    }
    Ok(paint)
}

/// Project an authored arrow: apply start offset, label clearance and shrink in
/// pixel space, then lay out its ends.
///
/// The facts are honored exactly or the arrow is rejected: unlike the
/// interactive `arrow_geometry`, which restores the untrimmed shaft once the
/// trim reaches 90% of the span, a Scene arrow whose start clearance (the
/// larger of `gap_start` and the distance at which the shaft leaves the
/// `label_clear` box) plus `gap_end` consumes the whole shaft is an error.
#[inline(never)]
pub fn arrow_paint_for_shape(
    start: [f64; 2],
    tip: [f64; 2],
    shape: &ArrowShape,
    head_length: f64,
) -> Result<ArrowPaint, SceneError> {
    if !shape.is_admitted() {
        return Err(SceneError::Length);
    }
    let from = [
        start[0] + shape.start_offset[0],
        start[1] + shape.start_offset[1],
    ];
    let (u, span) = unit(from, tip).ok_or(SceneError::Length)?;
    let mut packed = [f64::NAN; ARROW_STYLE_LEN];
    packed[7..11].copy_from_slice(&shape.label_clear);
    let lead = shape.gap_start.max(label_clear_exit(&packed, (u[0], u[1])));
    if !(lead + shape.gap_end < span) {
        return Err(SceneError::Length);
    }
    arrow_paint(
        [from[0] + u[0] * lead, from[1] + u[1] * lead],
        [tip[0] - u[0] * shape.gap_end, tip[1] - u[1] * shape.gap_end],
        shape.head,
        shape.tail,
        head_length,
    )
}

/// Strictly parse `N` comma-separated finite pixel values (`start_offset`,
/// `label_clear`). Unlike [`crate::arrow_geom::arrow_style_pack`], which skips
/// malformed text, a bad fact here must reject the arrow.
pub fn parse_pixel_csv<const N: usize>(text: &str) -> Option<[f64; N]> {
    let mut values = [0.0; N];
    let mut parts = text.split(',');
    for slot in &mut values {
        *slot = parts
            .next()?
            .trim()
            .parse::<f64>()
            .ok()
            .filter(|v| v.is_finite())?;
    }
    parts.next().is_none().then_some(values)
}

/// Paint of an arrow with the default 8 px head.
pub fn default_arrow_paint(
    start: [f64; 2],
    tip: [f64; 2],
    shape: &ArrowShape,
) -> Result<ArrowPaint, SceneError> {
    arrow_paint_for_shape(start, tip, shape, STRAIGHT_ARROW_HEAD_LENGTH)
}

/// Recover `(p0, p1, head, tail)` from the vertices of a run.
#[inline(never)]
pub fn arrow_run_ends(
    line: &[[f64; 2]],
    fill: &[[f64; 2]],
) -> Option<([f64; 2], [f64; 2], ArrowEnd, ArrowEnd)> {
    match (line.len(), fill.len()) {
        (2, 0) => Some((line[0], line[1], ArrowEnd::None, ArrowEnd::None)),
        (2, 3) => Some((line[0], fill[0], ArrowEnd::Triangle, ArrowEnd::None)),
        (5, 0) => Some((line[0], line[1], ArrowEnd::Open, ArrowEnd::None)),
        (5, 3) => Some((line[1], fill[0], ArrowEnd::Triangle, ArrowEnd::Open)),
        (8, 0) => Some((line[1], line[4], ArrowEnd::Open, ArrowEnd::Open)),
        _ => None,
    }
}

/// Head length recovered from a run: tip → base distance of its first end.
#[inline(never)]
pub fn arrow_run_head_length(line: &[[f64; 2]], fill: &[[f64; 2]]) -> Option<f64> {
    let distance = |a: [f64; 2], b: [f64; 2]| (a[0] - b[0]).hypot(a[1] - b[1]);
    let mid = |a: [f64; 2], b: [f64; 2]| [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0];
    match (line.len(), fill.len()) {
        (2, 3) | (5, 3) => Some(distance(fill[0], *line.last()?)),
        (5, 0) => Some(distance(line[1], mid(line[2], line[4]))),
        (8, 0) => Some(distance(line[1], mid(line[0], line[2]))),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const H: f64 = STRAIGHT_ARROW_HEAD_LENGTH;

    fn close(a: [f64; 2], b: [f64; 2]) -> bool {
        (a[0] - b[0]).abs() < 1e-9 && (a[1] - b[1]).abs() < 1e-9
    }

    #[test]
    fn triangle_head_keeps_the_pre_vocabulary_geometry() {
        let paint = default_arrow_paint([0.0, 0.0], [100.0, 0.0], &ArrowShape::DEFAULT).unwrap();
        assert_eq!(paint.line(), [[0.0, 0.0], [92.0, 0.0]]);
        assert_eq!(paint.fill(), [[100.0, 0.0], [92.0, 4.0], [92.0, -4.0]]);
    }

    #[test]
    fn open_head_is_the_v_of_the_triangle_corners_with_no_fill() {
        let shape = ArrowShape {
            head: ArrowEnd::Open,
            ..ArrowShape::DEFAULT
        };
        let paint = default_arrow_paint([0.0, 0.0], [100.0, 0.0], &shape).unwrap();
        assert!(paint.fill().is_empty());
        assert_eq!(
            paint.line(),
            vec![
                [0.0, 0.0],
                [100.0, 0.0],
                [92.0, 4.0],
                [100.0, 0.0],
                [92.0, -4.0]
            ]
        );
    }

    #[test]
    fn tail_only_v_is_the_open_head_of_the_reversed_arrow() {
        let shape = ArrowShape {
            head: ArrowEnd::None,
            tail: ArrowEnd::Open,
            ..ArrowShape::DEFAULT
        };
        let paint = default_arrow_paint([0.0, 0.0], [100.0, 0.0], &shape).unwrap();
        assert_eq!(
            paint.line(),
            vec![
                [100.0, 0.0],
                [0.0, 0.0],
                [8.0, -4.0],
                [0.0, 0.0],
                [8.0, 4.0]
            ]
        );
        assert!(paint.fill().is_empty());
    }

    #[test]
    fn both_open_and_plain_shafts_have_the_documented_vertex_counts() {
        for (head, tail, line, fill) in [
            (ArrowEnd::None, ArrowEnd::None, 2, 0),
            (ArrowEnd::Triangle, ArrowEnd::None, 2, 3),
            (ArrowEnd::Open, ArrowEnd::None, 5, 0),
            (ArrowEnd::None, ArrowEnd::Open, 5, 0),
            (ArrowEnd::Open, ArrowEnd::Open, 8, 0),
            (ArrowEnd::Triangle, ArrowEnd::Open, 5, 3),
        ] {
            let shape = ArrowShape {
                head,
                tail,
                ..ArrowShape::DEFAULT
            };
            let paint = default_arrow_paint([0.0, 0.0], [100.0, 40.0], &shape).unwrap();
            assert_eq!(paint.line().len(), line, "{head:?}/{tail:?}");
            assert_eq!(paint.fill().len(), fill, "{head:?}/{tail:?}");
            assert_eq!(shape.record_count(), line + fill);
            let (p0, p1, _, _) = arrow_run_ends(paint.line(), paint.fill()).unwrap();
            let h = arrow_run_head_length(paint.line(), paint.fill()).unwrap_or(H);
            let (rh, rt) = if head == ArrowEnd::None && tail == ArrowEnd::Open {
                (ArrowEnd::Open, ArrowEnd::None)
            } else {
                (head, tail)
            };
            let rebuilt = arrow_paint(p0, p1, rh, rt, h).unwrap();
            assert_eq!(rebuilt.fill().len(), fill);
            for ((_, a), (_, b)) in rebuilt.records().zip(paint.records()) {
                assert!(close(a, b), "{head:?}/{tail:?}: {a:?} vs {b:?}");
            }
        }
    }

    #[test]
    fn start_offset_gap_and_label_clearance_shrink_the_shaft_in_pixels() {
        let shape = ArrowShape {
            head: ArrowEnd::None,
            tail: ArrowEnd::None,
            start_offset: [0.0, 10.0],
            gap_start: 3.0,
            gap_end: 5.0,
            label_clear: [0.0; 4],
        };
        // Offset start (0, 10) → tip (100, 10): gap_start/gap_end trim along it.
        let paint = arrow_paint_for_shape([0.0, 0.0], [100.0, 10.0], &shape, H).unwrap();
        assert!(close(paint.line()[0], [3.0, 10.0]));
        assert!(close(paint.line()[1], [95.0, 10.0]));

        // A label box 20 px to the right of its centre: the shaft starts at the
        // box edge (the larger of clearance and gap_start), not at the centre.
        let clear = ArrowShape {
            head: ArrowEnd::None,
            tail: ArrowEnd::None,
            label_clear: [5.0, 20.0, 5.0, 5.0],
            gap_start: 2.0,
            ..ArrowShape::DEFAULT
        };
        let paint = arrow_paint_for_shape([0.0, 0.0], [100.0, 0.0], &clear, H).unwrap();
        assert!(close(paint.line()[0], [20.0, 0.0]));
        assert!(close(paint.line()[1], [100.0, 0.0]));
    }

    #[test]
    fn large_gaps_and_clearance_are_honored_exactly_or_rejected() {
        let plain = |gap_start: f64, gap_end: f64, label_clear: [f64; 4]| ArrowShape {
            head: ArrowEnd::None,
            tail: ArrowEnd::None,
            gap_start,
            gap_end,
            label_clear,
            ..ArrowShape::DEFAULT
        };
        // 100 px span: a 90 px end gap leaves the tip at 10 (the interactive
        // 90% rule would have restored the untrimmed tip at 100).
        let paint = arrow_paint_for_shape([0.0, 0.0], [100.0, 0.0], &plain(0.0, 90.0, [0.0; 4]), H)
            .unwrap();
        assert!(close(paint.line()[1], [10.0, 0.0]));
        let paint = arrow_paint_for_shape([0.0, 0.0], [100.0, 0.0], &plain(0.0, 99.0, [0.0; 4]), H)
            .unwrap();
        assert!(close(paint.line()[1], [1.0, 0.0]));
        // Total trim reaching the span (or exceeding it) is unsatisfiable.
        for shape in [
            plain(0.0, 100.0, [0.0; 4]),
            plain(60.0, 40.0, [0.0; 4]),
            plain(0.0, 150.0, [0.0; 4]),
            // Label box edge at 120 px on a 100 px arrow: the start would
            // otherwise be restored inside the label.
            plain(0.0, 0.0, [120.0, 120.0, 120.0, 120.0]),
            // Clearance 60 plus gap_end 40 consumes the shaft exactly.
            plain(0.0, 40.0, [60.0, 60.0, 60.0, 60.0]),
        ] {
            assert!(
                arrow_paint_for_shape([0.0, 0.0], [100.0, 0.0], &shape, H).is_err(),
                "{shape:?}"
            );
        }
        // Just under the threshold is accepted and exact.
        let paint = arrow_paint_for_shape(
            [0.0, 0.0],
            [100.0, 0.0],
            &plain(0.0, 39.5, [60.0, 60.0, 60.0, 60.0]),
            H,
        )
        .unwrap();
        assert!(close(paint.line()[0], [60.0, 0.0]) && close(paint.line()[1], [60.5, 0.0]));
        // A zero-length shaft is rejected, not drawn.
        assert!(
            arrow_paint_for_shape([5.0, 5.0], [5.0, 5.0], &plain(0.0, 0.0, [0.0; 4]), H).is_err()
        );
    }

    #[test]
    fn short_arrows_and_unadmitted_shapes_fail_closed() {
        let two_heads = ArrowShape {
            head: ArrowEnd::Open,
            tail: ArrowEnd::Open,
            ..ArrowShape::DEFAULT
        };
        assert!(default_arrow_paint([0.0, 0.0], [15.0, 0.0], &two_heads).is_err());
        assert!(default_arrow_paint([0.0, 0.0], [17.0, 0.0], &two_heads).is_ok());
        let triangle_tail = ArrowShape {
            tail: ArrowEnd::Triangle,
            ..ArrowShape::DEFAULT
        };
        assert!(!triangle_tail.is_admitted());
        assert!(default_arrow_paint([0.0, 0.0], [100.0, 0.0], &triangle_tail).is_err());
        for bad in [f64::NAN, -1.0, ARROW_MAX_PIXELS + 1.0] {
            let mut shape = ArrowShape::DEFAULT;
            shape.gap_end = bad;
            assert!(!shape.is_admitted(), "{bad}");
            let mut shape = ArrowShape::DEFAULT;
            shape.label_clear[2] = bad;
            assert!(!shape.is_admitted(), "{bad}");
        }
        assert!(arrow_run_ends(&[[0.0; 2]; 3], &[]).is_none());
    }

    #[test]
    fn pixel_csv_rejects_malformed_text_instead_of_skipping_it() {
        assert_eq!(parse_pixel_csv::<2>("1.5, -2"), Some([1.5, -2.0]));
        assert_eq!(parse_pixel_csv::<4>("1,2,3,4"), Some([1.0, 2.0, 3.0, 4.0]));
        for bad in ["", "1", "1,2,3", "1,,2", "1,x", "1,inf", "1,NaN"] {
            assert_eq!(parse_pixel_csv::<2>(bad), None, "{bad:?}");
        }
        assert_eq!(parse_pixel_csv::<2>("1,2,3"), None);
    }

    #[test]
    fn end_names_are_the_documented_vocabulary() {
        assert_eq!(ArrowEnd::from_name("v"), Some(ArrowEnd::Open));
        assert_eq!(ArrowEnd::from_name("triangle"), Some(ArrowEnd::Triangle));
        assert_eq!(ArrowEnd::from_name("none"), Some(ArrowEnd::None));
        for rejected in ["bar", "fancy", "", "V"] {
            assert_eq!(ArrowEnd::from_name(rejected), None);
        }
    }
}
