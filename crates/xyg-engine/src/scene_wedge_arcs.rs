//! Exact polar wedge arcs for static vector export (`XYWA` v1).
//!
//! Polar bar/column/histogram/heatmap/density wedges reach every renderer as
//! flattened PolyFill vertex runs (`polar_wedge_points`). Native raster and the
//! browser painter keep drawing those polygons. Static SVG (and the PDF that is
//! converted from it) instead writes each plain annular sector as exact SVG
//! elliptical-arc segments, so a printed or zoomed rose keeps circular edges.
//!
//! The optional `XYWA` sidecar directly precedes `XYPL` (so a polar Scene
//! still ends with its XYPL envelope) and carries, per wedge, the
//! flattened run it describes plus its radii and arc angles. Arc endpoints are
//! never re-derived: the SVG writer takes them from the run's first/last
//! vertices of each arc, so vector and raster geometry agree vertex for
//! vertex. Rounded annular corners and zero-width slices have no entry and
//! keep their flattened path. Scenes without exact wedges emit no sidecar, so
//! their bytes are unchanged.

use super::*;

pub const XYWA_MAGIC: &[u8; 4] = b"XYWA";
pub const XYWA_VERSION: u32 = 1;
/// Header: magic, version, entry count, reserved zero, then f64 centre x/y.
pub const XYWA_HEADER_BYTES: usize = 32;
/// Entry: u32 first record, u32 vertex count, then six f64 (outer radius,
/// inner radius, outer start/end angle, inner start/end angle).
pub const XYWA_ENTRY_BYTES: usize = 56;
/// Every wedge spends at least three PolyFill records.
const MAX_XYWA_ENTRIES: usize = MAX_SCENE_MARKS / 3;

/// One exact annular sector over the flattened PolyFill run
/// `first..first + count`. Angles are screen radians in the math sense
/// (`(cx + r cos a, cy - r sin a)`); `inner == 0` is a slice from the centre.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct SceneWedgeArc {
    pub(crate) first: usize,
    pub(crate) count: usize,
    pub(crate) outer: f64,
    pub(crate) inner: f64,
    pub(crate) outer_start: f64,
    pub(crate) outer_end: f64,
    pub(crate) inner_start: f64,
    pub(crate) inner_end: f64,
}

/// Every exact wedge of one polar Scene, sorted by `first`.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct SceneWedgeArcs {
    pub(crate) cx: f64,
    pub(crate) cy: f64,
    pub(crate) entries: Vec<SceneWedgeArc>,
}

/// The record fields a wedge entry is checked against.
#[derive(Clone, Copy)]
pub(crate) struct WedgeRecordView {
    pub(crate) kind: u8,
    pub(crate) visible: bool,
    pub(crate) annotation_tag: u8,
    pub(crate) style_ref: usize,
    pub(crate) stable_id: u64,
    pub(crate) x: f64,
    pub(crate) y: f64,
}

impl WedgeRecordView {
    fn from_encoded(record: &EncodedRecord) -> Self {
        Self {
            kind: record.kind as u8,
            visible: record.visible,
            annotation_tag: record.annotation_tag,
            style_ref: record.style_ref,
            stable_id: record.stable_id,
            x: record.coordinates[0],
            y: record.coordinates[1],
        }
    }

    /// Mirrors the SVG PolyFill run predicate (`same_record_run`, style,
    /// visibility) for a record following `self`.
    fn continues(&self, next: &Self) -> bool {
        next.kind == SceneRecordKind::PolyFill as u8
            && next.visible
            && next.style_ref == self.style_ref
            && next.annotation_tag == self.annotation_tag
            && (self.annotation_tag == 0x80 || next.stable_id == self.stable_id)
    }
}

impl SceneWedgeArcs {
    /// The entry describing exactly the SVG run `first..first + count`.
    pub(crate) fn find(&self, first: usize, count: usize) -> Option<&SceneWedgeArc> {
        let at = self
            .entries
            .binary_search_by_key(&first, |entry| entry.first)
            .ok()?;
        let entry = &self.entries[at];
        (entry.count == count).then_some(entry)
    }

    pub(crate) fn encode(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(XYWA_HEADER_BYTES + self.entries.len() * XYWA_ENTRY_BYTES);
        out.extend_from_slice(XYWA_MAGIC);
        out.extend_from_slice(&XYWA_VERSION.to_le_bytes());
        out.extend_from_slice(&(self.entries.len() as u32).to_le_bytes());
        out.extend_from_slice(&0u32.to_le_bytes());
        out.extend_from_slice(&self.cx.to_le_bytes());
        out.extend_from_slice(&self.cy.to_le_bytes());
        for entry in &self.entries {
            out.extend_from_slice(&(entry.first as u32).to_le_bytes());
            out.extend_from_slice(&(entry.count as u32).to_le_bytes());
            for value in [
                entry.outer,
                entry.inner,
                entry.outer_start,
                entry.outer_end,
                entry.inner_start,
                entry.inner_end,
            ] {
                out.extend_from_slice(&value.to_le_bytes());
            }
        }
        out
    }

    /// Keep only entries whose run is a maximal SVG PolyFill run. Literal-ID
    /// scenes (tag `0x80`) merge same-style neighbours into one run; those
    /// wedges keep their flattened path rather than fail validation.
    pub(crate) fn retain_maximal_runs(&mut self, records: &[WedgeRecordView]) {
        self.entries
            .retain(|entry| entry_run_is_maximal(entry, records.len(), |i| Ok(records[i])).is_ok());
    }

    /// Fail-closed consistency with the flattened records: ordered,
    /// non-overlapping maximal PolyFill runs whose arc endpoints sit on the
    /// stated circles at the stated angles.
    pub(crate) fn validate(
        &self,
        record_count: usize,
        record: impl Fn(usize) -> Result<WedgeRecordView, SceneError>,
    ) -> Result<(), SceneError> {
        if !self.cx.is_finite() || !self.cy.is_finite() || self.entries.is_empty() {
            return Err(SceneError::Length);
        }
        let mut next_free = 0usize;
        for entry in &self.entries {
            if entry.first < next_free {
                return Err(SceneError::Length);
            }
            next_free = entry
                .first
                .checked_add(entry.count)
                .ok_or(SceneError::Limit)?;
            if next_free > record_count {
                return Err(SceneError::Length);
            }
            let values = [
                entry.outer,
                entry.inner,
                entry.outer_start,
                entry.outer_end,
                entry.inner_start,
                entry.inner_end,
            ];
            let outer_span = entry.outer_end - entry.outer_start;
            let inner_span = entry.inner_start - entry.inner_end;
            if values.iter().any(|value| !value.is_finite())
                || !(entry.outer > 0.0)
                || entry.inner < 0.0
                || entry.inner >= entry.outer
                || outer_span == 0.0
                || outer_span.abs() > std::f64::consts::TAU * (1.0 + 1e-9)
                || inner_span.abs() > outer_span.abs() * (1.0 + 1e-9) + 1e-12
                || (inner_span != 0.0 && inner_span.signum() != outer_span.signum())
            {
                return Err(SceneError::Length);
            }
            let (outer_first, outer_last) = if entry.inner == 0.0 {
                if entry.count < 3 || entry.inner_start != 0.0 || entry.inner_end != 0.0 {
                    return Err(SceneError::Length);
                }
                (entry.first + 1, entry.first + entry.count - 1)
            } else {
                if entry.count < 4 || entry.count % 2 != 0 {
                    return Err(SceneError::Length);
                }
                (entry.first, entry.first + entry.count / 2 - 1)
            };
            entry_run_is_maximal(entry, record_count, &record)?;
            let tolerance = 1e-6 * (1.0 + entry.outer);
            let on = |index: usize, radius: f64, angle: f64| -> Result<(), SceneError> {
                let view = record(index)?;
                let x = self.cx + radius * angle.cos();
                let y = self.cy - radius * angle.sin();
                if (view.x - x).abs() > tolerance || (view.y - y).abs() > tolerance {
                    return Err(SceneError::Length);
                }
                Ok(())
            };
            on(outer_first, entry.outer, entry.outer_start)?;
            on(outer_last, entry.outer, entry.outer_end)?;
            if entry.inner == 0.0 {
                on(entry.first, 0.0, 0.0)?;
            } else {
                on(outer_last + 1, entry.inner, entry.inner_start)?;
                on(entry.first + entry.count - 1, entry.inner, entry.inner_end)?;
            }
        }
        Ok(())
    }
}

fn entry_run_is_maximal(
    entry: &SceneWedgeArc,
    record_count: usize,
    record: impl Fn(usize) -> Result<WedgeRecordView, SceneError>,
) -> Result<(), SceneError> {
    let end = entry.first + entry.count;
    if entry.count < 3 || end > record_count {
        return Err(SceneError::Length);
    }
    let head = record(entry.first)?;
    if head.kind != SceneRecordKind::PolyFill as u8 || !head.visible {
        return Err(SceneError::Length);
    }
    for index in entry.first + 1..end {
        let view = record(index)?;
        if !head.continues(&view) || view.stable_id != head.stable_id {
            return Err(SceneError::Length);
        }
    }
    if entry.first > 0 {
        let before = record(entry.first - 1)?;
        if before.kind == SceneRecordKind::PolyFill as u8
            && before.visible
            && before.continues(&head)
        {
            return Err(SceneError::Length);
        }
    }
    if end < record_count && head.continues(&record(end)?) {
        return Err(SceneError::Length);
    }
    Ok(())
}

/// Parse an `XYWA` v1 sidecar; empty bytes mean no exact wedges.
pub(crate) fn parse_xywa(bytes: &[u8]) -> Result<Option<SceneWedgeArcs>, SceneError> {
    if bytes.is_empty() {
        return Ok(None);
    }
    let length = xywa_len(bytes)?;
    if length != bytes.len() {
        return Err(SceneError::Length);
    }
    let f64_at = |at: usize| batch_f64(bytes, at);
    let count = batch_u32(bytes, 8)? as usize;
    let mut entries = Vec::with_capacity(count);
    for index in 0..count {
        let at = XYWA_HEADER_BYTES + index * XYWA_ENTRY_BYTES;
        entries.push(SceneWedgeArc {
            first: batch_u32(bytes, at)? as usize,
            count: batch_u32(bytes, at + 4)? as usize,
            outer: f64_at(at + 8)?,
            inner: f64_at(at + 16)?,
            outer_start: f64_at(at + 24)?,
            outer_end: f64_at(at + 32)?,
            inner_start: f64_at(at + 40)?,
            inner_end: f64_at(at + 48)?,
        });
    }
    Ok(Some(SceneWedgeArcs {
        cx: f64_at(16)?,
        cy: f64_at(24)?,
        entries,
    }))
}

/// Byte length of the `XYWA` v1 sidecar at the head of `bytes`, or `0`
/// when `bytes` does not start with one.
pub(crate) fn xywa_prefix_len(bytes: &[u8]) -> Result<usize, SceneError> {
    if bytes.get(..4) != Some(&XYWA_MAGIC[..]) {
        return Ok(0);
    }
    xywa_len(bytes)
}

fn xywa_len(bytes: &[u8]) -> Result<usize, SceneError> {
    if bytes.len() < XYWA_HEADER_BYTES || bytes.get(..4) != Some(&XYWA_MAGIC[..]) {
        return Err(SceneError::Length);
    }
    if batch_u32(bytes, 4)? != XYWA_VERSION {
        return Err(SceneError::Version);
    }
    let count = batch_u32(bytes, 8)? as usize;
    if count == 0 || batch_u32(bytes, 12)? != 0 {
        return Err(SceneError::Length);
    }
    if count > MAX_XYWA_ENTRIES {
        return Err(SceneError::Limit);
    }
    let length = XYWA_HEADER_BYTES + count * XYWA_ENTRY_BYTES;
    if bytes.len() < length {
        return Err(SceneError::Length);
    }
    Ok(length)
}

/// Decoded-record view used by `SceneDocument::decode`.
pub(crate) fn encoded_record_view(records: &[EncodedRecord], index: usize) -> WedgeRecordView {
    WedgeRecordView::from_encoded(&records[index])
}

/// Append one SVG elliptical-arc segment from the current point to `end`
/// around `(cx, cy)`. Spans above a half turn split at their mid-angle, so the
/// large-arc flag is always `0` and two-decimal endpoint rounding can neither
/// collapse a near-full turn nor flip a large arc. A zero span (an inner arc
/// a wide `wedge_gap` collapsed to a point) is a line.
fn push_svg_arc(
    out: &mut String,
    (cx, cy): (f64, f64),
    radius: f64,
    start: f64,
    end: f64,
    end_point: (f64, f64),
) {
    let span = end - start;
    if span.abs() <= 1e-12 {
        out.push_str(" L ");
        push_num(out, end_point.0);
        out.push(' ');
        push_num(out, end_point.1);
        return;
    }
    // Screen y grows downward, so an increasing math angle is a visually
    // counterclockwise (SVG negative-angle, sweep 0) arc.
    let sweep = if span > 0.0 { "0" } else { "1" };
    let mut segment = |point: (f64, f64)| {
        out.push_str(" A ");
        push_num(out, radius);
        out.push(' ');
        push_num(out, radius);
        out.push_str(" 0 0 ");
        out.push_str(sweep);
        out.push(' ');
        push_num(out, point.0);
        out.push(' ');
        push_num(out, point.1);
    };
    if span.abs() > std::f64::consts::PI {
        let mid = start + span / 2.0;
        segment((cx + radius * mid.cos(), cy - radius * mid.sin()));
    }
    segment(end_point);
}

/// Exact SVG path data for one wedge run: `M outer-start A … outer-end L
/// inner-start A … inner-end Z`, or `M centre L outer-start A … outer-end Z`
/// for a slice from the centre. Every endpoint is a flattened vertex.
pub(crate) fn push_svg_wedge_path(
    out: &mut String,
    arcs: &SceneWedgeArcs,
    entry: &SceneWedgeArc,
    run: &[EncodedRecord],
) {
    let at = |index: usize| (run[index].coordinates[0], run[index].coordinates[1]);
    let center = (arcs.cx, arcs.cy);
    let count = run.len();
    out.push_str("<path d=\"M ");
    let (first_x, first_y) = at(0);
    push_num(out, first_x);
    out.push(' ');
    push_num(out, first_y);
    if entry.inner == 0.0 {
        let (x, y) = at(1);
        out.push_str(" L ");
        push_num(out, x);
        out.push(' ');
        push_num(out, y);
        push_svg_arc(
            out,
            center,
            entry.outer,
            entry.outer_start,
            entry.outer_end,
            at(count - 1),
        );
    } else {
        let half = count / 2;
        push_svg_arc(
            out,
            center,
            entry.outer,
            entry.outer_start,
            entry.outer_end,
            at(half - 1),
        );
        let (x, y) = at(half);
        out.push_str(" L ");
        push_num(out, x);
        out.push(' ');
        push_num(out, y);
        push_svg_arc(
            out,
            center,
            entry.inner,
            entry.inner_start,
            entry.inner_end,
            at(count - 1),
        );
    }
    out.push_str(" Z\"");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f64::consts::{FRAC_PI_2, PI, TAU};

    const FILL: [u8; 4] = [37, 99, 235, 255];

    struct Polar {
        hole: f64,
        sector: (f64, f64),
        clockwise: bool,
        radii: Option<SceneCornerRadius>,
    }

    impl Default for Polar {
        fn default() -> Self {
            Self {
                hole: 0.0,
                sector: (0.0, TAU),
                clockwise: false,
                radii: None,
            }
        }
    }

    /// Encode polar Rect wedges `[theta0, r0, theta1, r1]` (radians, r in
    /// `[0, 1]`) on a 400x400 plot.
    fn polar_scene(rects: &[[f64; 4]], polar: Polar) -> Vec<u8> {
        let layout = PlotLayout::new(400.0, 400.0, 0.0, 0.0, 0.0, 0.0).unwrap();
        let x = AxisScale::new(ScaleKind::Linear, 0.0, TAU, 0.0, 400.0, 1.0, false).unwrap();
        let y = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 400.0, 0.0, 1.0, false).unwrap();
        let envelope = polar::PolarEnvelope {
            theta_unit: 0,
            theta_direction: u32::from(polar.clockwise),
            n_categories: 0,
            r_scale_kind: 0,
            grid_shape: 0,
            r_mask_nonpositive: false,
            theta_zero: 0.0,
            sector_start: polar.sector.0,
            sector_end: polar.sector.1,
            r_lo: 0.0,
            r_hi: 1.0,
            r_origin: f64::NAN,
            hole: polar.hole,
            r_constant: 1.0,
        };
        let xypl = polar::encode_xypl(&envelope);
        let n = rects.len();
        let kinds = vec![SceneRecordKind::Rect as u8; n];
        let ids = vec![1u64; n];
        let styles = vec![0u32; n];
        let zeros = vec![0.0f64; n];
        let symbols = vec![0u8; n];
        let column = |at: usize| rects.iter().map(|rect| rect[at]).collect::<Vec<_>>();
        let (x0, y0, x1, y1) = (column(0), column(1), column(2), column(3));
        let batch = SceneBatch::new(
            layout,
            1,
            2,
            x,
            y,
            &kinds,
            &ids,
            &styles,
            &FILL,
            &[0, 0, 0, 255],
            &[0.0],
            &zeros,
            &symbols,
            &x0,
            &y0,
            &x1,
            &y1,
        )
        .unwrap()
        .with_polar(&xypl)
        .unwrap();
        let batch = match polar.radii {
            Some(radius) => batch.with_corner_radii(vec![Some(radius)]).unwrap(),
            None => batch,
        };
        batch.encode()
    }

    fn radii(corner: f64, gap: f64) -> Option<SceneCornerRadius> {
        Some(SceneCornerRadius {
            r_tip: corner,
            r_base: corner,
            force_tip_top: false,
            wedge_gap: gap,
        })
    }

    /// Wedge `<path d>` data (the clip path and chrome never use the fill).
    fn wedge_paths(svg: &str) -> Vec<Vec<String>> {
        svg.split("<path d=\"")
            .skip(1)
            .filter(|chunk| chunk.contains("rgb(37,99,235)"))
            .map(|chunk| {
                chunk[..chunk.find('"').unwrap()]
                    .split(' ')
                    .map(str::to_owned)
                    .collect()
            })
            .collect()
    }

    fn num(value: f64) -> String {
        let mut out = String::new();
        push_num(&mut out, value);
        out
    }

    fn vertex(document: &SceneDocument, index: usize) -> [String; 2] {
        let [x, y, ..] = document.records[index].coordinates;
        [num(x), num(y)]
    }

    fn arcs(document: &SceneDocument) -> &SceneWedgeArcs {
        document
            .polar
            .as_ref()
            .unwrap()
            .wedge_arcs
            .as_ref()
            .unwrap()
    }

    /// The XYWA sidecar directly precedes the trailing XYPL envelope.
    fn xywa_range(bytes: &[u8]) -> Option<std::ops::Range<usize>> {
        let xypl = bytes.len() - polar::XYPL_V1_BYTES;
        assert_eq!(&bytes[xypl..xypl + 4], polar::XYPL_MAGIC);
        let start = (0..xypl).rev().find_map(|at| {
            (bytes.get(at..at + 4) == Some(&XYWA_MAGIC[..])
                && xywa_prefix_len(&bytes[at..]).ok()? == xypl - at)
                .then_some(at)
        })?;
        Some(start..xypl)
    }

    #[test]
    fn annular_wedge_writes_outer_and_reversed_inner_arcs_through_flattened_ends() {
        let bytes = polar_scene(&[[0.0, 0.25, FRAC_PI_2, 1.0]], Polar::default());
        validate_scene_batch(&bytes).unwrap();
        let document = SceneDocument::decode(&bytes).unwrap();
        let metrics = document.polar.as_ref().unwrap().metrics;
        let radius = metrics[polar::METRIC_RADIUS];
        let n = document.records.len();
        assert!(n >= 6 && n % 2 == 0);
        let paths = wedge_paths(&document.to_svg());
        assert_eq!(paths.len(), 1);
        let d = &paths[0];
        let [ox0, oy0] = vertex(&document, 0);
        let [ox1, oy1] = vertex(&document, n / 2 - 1);
        let [ix0, iy0] = vertex(&document, n / 2);
        let [ix1, iy1] = vertex(&document, n - 1);
        let (outer, inner) = (num(radius), num(0.25 * radius));
        let expected: Vec<&str> = vec![
            "M", &ox0, &oy0, "A", &outer, &outer, "0", "0", "0", &ox1, &oy1, "L", &ix0, &iy0, "A",
            &inner, &inner, "0", "0", "1", &ix1, &iy1, "Z",
        ];
        assert_eq!(d, &expected);
        let entry = arcs(&document).entries[0];
        assert_eq!((entry.first, entry.count), (0, n));
        assert_eq!(entry.outer, radius);
        assert_eq!(entry.inner, 0.25 * radius);
        assert_eq!((arcs(&document).cx, arcs(&document).cy), (200.0, 200.0));
    }

    #[test]
    fn centre_slice_and_clockwise_sweep() {
        let bytes = polar_scene(
            &[[0.0, 0.0, FRAC_PI_2, 1.0]],
            Polar {
                clockwise: true,
                ..Polar::default()
            },
        );
        let document = SceneDocument::decode(&bytes).unwrap();
        let n = document.records.len();
        let d = &wedge_paths(&document.to_svg())[0];
        let [cx, cy] = vertex(&document, 0);
        let [ox0, oy0] = vertex(&document, 1);
        let [ox1, oy1] = vertex(&document, n - 1);
        let outer = num(document.polar.as_ref().unwrap().metrics[polar::METRIC_RADIUS]);
        let expected: Vec<&str> = vec![
            "M", &cx, &cy, "L", &ox0, &oy0, "A", &outer, &outer, "0", "0", "1", &ox1, &oy1, "Z",
        ];
        assert_eq!(d, &expected);
        assert_eq!((cx.as_str(), cy.as_str()), ("200", "200"));
    }

    #[test]
    fn full_turn_annulus_and_disc_split_each_circle_into_two_arcs() {
        for (inner, a_count) in [(0.5, 4), (0.0, 2)] {
            let bytes = polar_scene(&[[0.0, inner, TAU, 1.0]], Polar::default());
            let document = SceneDocument::decode(&bytes).unwrap();
            let d = &wedge_paths(&document.to_svg())[0];
            assert_eq!(d.iter().filter(|token| *token == "A").count(), a_count);
            // The large-arc flag is always 0: every half turn is its own arc.
            assert!(d.windows(5).all(|w| !(w[0] == "A" && w[4] == "1")));
            let radius = document.polar.as_ref().unwrap().metrics[polar::METRIC_RADIUS];
            // The outer circle's first half ends at the antipode (angle pi).
            let first_arc = d.iter().position(|token| token == "A").unwrap();
            assert_eq!(d[first_arc + 6], num(200.0 - radius));
            assert_eq!(d[first_arc + 7], num(200.0));
            let n = document.records.len();
            let [ex, ey] = vertex(&document, if inner > 0.0 { n / 2 - 1 } else { n - 1 });
            assert_eq!(d[first_arc + 8], "A");
            assert_eq!(d[first_arc + 14], ex);
            assert_eq!(d[first_arc + 15], ey);
            let pdf = crate::pdf::svg_to_pdf(&document.to_svg()).unwrap();
            assert!(pdf.starts_with(b"%PDF-1.4"));
        }
    }

    #[test]
    fn rounded_annular_corners_and_zero_width_keep_flattened_paths() {
        let rounded = polar_scene(
            &[[0.0, 0.25, FRAC_PI_2, 1.0]],
            Polar {
                radii: radii(14.0, 0.0),
                ..Polar::default()
            },
        );
        assert!(xywa_range(&rounded).is_none());
        let document = SceneDocument::decode(&rounded).unwrap();
        let d = &wedge_paths(&document.to_svg())[0];
        assert!(!d.contains(&"A".to_owned()));
        assert_eq!(
            d.iter().filter(|t| *t == "L").count(),
            document.records.len() - 1
        );

        // A centre slice ignores corner_radius, so it stays exact.
        let pie = polar_scene(
            &[[0.0, 0.0, FRAC_PI_2, 1.0]],
            Polar {
                radii: radii(14.0, 0.0),
                ..Polar::default()
            },
        );
        assert!(xywa_range(&pie).is_some());

        let zero = polar_scene(&[[0.5, 0.25, 0.5, 1.0]], Polar::default());
        assert!(xywa_range(&zero).is_none());
        let document = SceneDocument::decode(&zero).unwrap();
        assert!(wedge_paths(&document.to_svg())
            .iter()
            .all(|d| !d.contains(&"A".to_owned())));
    }

    #[test]
    fn wedge_gap_insets_arc_ends_and_collapsed_inner_arc_is_a_line() {
        let bytes = polar_scene(
            &[[0.0, 0.25, FRAC_PI_2, 1.0], [FRAC_PI_2, 0.25, PI, 1.0]],
            Polar {
                radii: radii(0.0, 12.0),
                ..Polar::default()
            },
        );
        let document = SceneDocument::decode(&bytes).unwrap();
        let radius = document.polar.as_ref().unwrap().metrics[polar::METRIC_RADIUS];
        let entries = &arcs(&document).entries;
        assert_eq!(entries.len(), 2);
        assert!((entries[0].outer_start - 6.0 / radius).abs() < 1e-12);
        assert!((entries[0].inner_end - 6.0 / (0.25 * radius)).abs() < 1e-12);
        let paths = wedge_paths(&document.to_svg());
        assert_eq!(paths.len(), 2);
        assert!(paths
            .iter()
            .all(|d| d.iter().filter(|t| *t == "A").count() == 2));

        // A 10 px gap on a 2 px inner radius collapses that arc to a point.
        let collapsed = polar_scene(
            &[[0.0, 0.01, 0.2, 1.0]],
            Polar {
                radii: radii(0.0, 10.0),
                ..Polar::default()
            },
        );
        let document = SceneDocument::decode(&collapsed).unwrap();
        let d = &wedge_paths(&document.to_svg())[0];
        assert_eq!(d.iter().filter(|t| *t == "A").count(), 1);
        assert_eq!(d.iter().filter(|t| *t == "L").count(), 2);
    }

    #[test]
    fn sector_clip_moves_arc_ends_onto_the_sector_edge() {
        let bytes = polar_scene(
            &[[-0.5, 0.25, 0.5, 1.0]],
            Polar {
                sector: (0.0, FRAC_PI_2),
                ..Polar::default()
            },
        );
        let document = SceneDocument::decode(&bytes).unwrap();
        let metrics = document.polar.as_ref().unwrap().metrics;
        let (a0, a1) = polar::wedge_angles(&metrics, -0.5, 0.5).unwrap();
        assert_eq!((a0, a1), polar::wedge_angles(&metrics, 0.0, 0.5).unwrap());
        let entry = arcs(&document).entries[0];
        assert_eq!((entry.outer_start, entry.outer_end), (a0, a1));
        assert_eq!((entry.inner_start, entry.inner_end), (a1, a0));
        assert_eq!(wedge_paths(&document.to_svg()).len(), 1);
    }

    #[test]
    fn raster_and_browser_painter_ignore_the_sidecar() {
        let bytes = polar_scene(
            &[[0.0, 0.25, 2.0, 0.75], [2.0, 0.0, 5.0, 1.0]],
            Polar::default(),
        );
        let range = xywa_range(&bytes).unwrap();
        let mut stripped = bytes.clone();
        stripped.drain(range);
        validate_scene_batch(&stripped).unwrap();
        let with = SceneDocument::decode(&bytes).unwrap();
        let without = SceneDocument::decode(&stripped).unwrap();
        assert_eq!(
            with.to_raster_commands(1.0).unwrap(),
            without.to_raster_commands(1.0).unwrap()
        );
        assert_eq!(
            with.to_browser_painter(usize::MAX).unwrap(),
            without.to_browser_painter(usize::MAX).unwrap()
        );
        assert!(wedge_paths(&without.to_svg())
            .iter()
            .all(|d| !d.contains(&"A".to_owned())));
        assert!(wedge_paths(&with.to_svg())
            .iter()
            .all(|d| d.contains(&"A".to_owned())));
    }

    #[test]
    fn malformed_sidecar_fails_closed() {
        let bytes = polar_scene(&[[0.0, 0.25, FRAC_PI_2, 1.0]], Polar::default());
        let range = xywa_range(&bytes).unwrap();
        let entry = range.start + XYWA_HEADER_BYTES;
        let mut cases: Vec<Vec<u8>> = Vec::new();
        // Radius disagreeing with the flattened vertices.
        let mut radius = bytes.clone();
        let outer = f64::from_le_bytes(radius[entry + 8..entry + 16].try_into().unwrap());
        radius[entry + 8..entry + 16].copy_from_slice(&(outer + 1.0).to_le_bytes());
        cases.push(radius);
        // Run that does not cover the whole wedge.
        let mut count = bytes.clone();
        let n = u32::from_le_bytes(count[entry + 4..entry + 8].try_into().unwrap());
        count[entry + 4..entry + 8].copy_from_slice(&(n - 2).to_le_bytes());
        cases.push(count);
        // Unknown version and reserved bytes.
        let mut version = bytes.clone();
        version[range.start + 4] = 2;
        cases.push(version);
        let mut reserved = bytes.clone();
        reserved[range.start + 12] = 1;
        cases.push(reserved);
        for case in &cases {
            assert!(SceneDocument::decode(case).is_err());
            assert!(validate_scene_batch(case).is_err());
        }
        // A wedge-arc sidecar is meaningless without XYPL.
        let xywa = &bytes[range];
        assert!(scene_sidecars_after_chrome(xywa, 0).is_err());
    }

    #[test]
    fn sidecar_round_trips_and_is_bounded() {
        let bytes = polar_scene(&[[0.0, 0.25, FRAC_PI_2, 1.0]], Polar::default());
        let range = xywa_range(&bytes).unwrap();
        assert_eq!(range.len(), XYWA_HEADER_BYTES + XYWA_ENTRY_BYTES);
        let parsed = parse_xywa(&bytes[range.clone()]).unwrap().unwrap();
        assert_eq!(parsed.encode(), bytes[range.clone()]);
        let mut huge = bytes[range].to_vec();
        huge[8..12].copy_from_slice(&u32::MAX.to_le_bytes());
        assert_eq!(parse_xywa(&huge), Err(SceneError::Limit));
        assert_eq!(parse_xywa(&huge[..16]), Err(SceneError::Length));
    }
}
