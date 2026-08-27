//! Scene mark fill/stroke defaults, chrome style, and CSS→RGBA8 paint
//! (M2 #271 / #283).
//!
//! Hosts pack a versioned `XYMS` envelope of per-trace kind, opacities,
//! authored CSS strings, and width fields, plus a versioned `XYCH` envelope
//! of per-axis chrome paints and widths. Rust owns the per-kind fill/stroke
//! defaults, line-only scatter stroke, band `line_color` vs `stroke`, default
//! stroke widths, Scene chrome default RGBA/widths (title, axis, ticks, grid,
//! labels), and the static Scene/raster CSS→RGBA8 conversion (including
//! `none` → transparent and the never-invisible fallback). Python
//! `figure_scene` and Node `figureSceneV3` pack literals only so the hosts
//! cannot drift on named colors or defaults.

use crate::css;
use crate::scene::{SceneChromeStyle, SCENE_CHROME_STYLE_INPUT_BYTES};

const XYMS_MAGIC: &[u8; 4] = b"XYMS";
const XYMS_VERSION: u32 = 1;
const XYMS_HEADER_BYTES: usize = 16;
const XYMS_RECORD_PREFIX: usize = 52;
const XYMS_OUTPUT_BYTES: usize = 16;
const MAX_XYMS_MARKS: usize = 4_096;
const MAX_XYMS_CSS_BYTES: usize = 4_096;

const FLAG_LINE_ONLY_SYMBOL: u8 = 1 << 0;
const FLAG_HAS_FILL: u8 = 1 << 1;
const FLAG_HAS_STROKE: u8 = 1 << 2;
const FLAG_HAS_LINE_COLOR: u8 = 1 << 3;
const FLAG_HAS_STROKE_WIDTH: u8 = 1 << 5;
const FLAG_HAS_WIDTH: u8 = 1 << 6;
const FLAG_HAS_LINE_WIDTH: u8 = 1 << 7;

const KIND_SCATTER: u8 = 0;
const KIND_LINE: u8 = 1;
const KIND_BOX_WHISKER: u8 = 7;
const KIND_BOX_MEDIAN: u8 = 8;
const KIND_SEGMENTS: u8 = 9;
const KIND_ERRORBAR: u8 = 10;
const KIND_STEM: u8 = 11;
const KIND_AREA: u8 = 12;
const KIND_ERROR_BAND: u8 = 13;
const KIND_RIBBON: u8 = 14;
const KIND_TRIANGLE_MESH: u8 = 15;
const KIND_CONTOUR: u8 = 18;

const DEFAULT_COLOR: &str = "#3987e5";
const TRANSPARENT: &str = "transparent";

const XYCH_MAGIC: &[u8; 4] = b"XYCH";
const XYCH_VERSION: u32 = 1;
const XYCH_HEADER_BYTES: usize = 16;
const XYCH_AXIS_PREFIX: usize = 84;
const XYCH_FLAG_HAS_CHART_BG: u32 = 1 << 0;
const XYCH_FLAG_HAS_PLOT_BG: u32 = 1 << 1;
const XYCH_N_AXES_SHIFT: u32 = 8;
const XYCH_N_AXES_MASK: u32 = 0xff;
const XYCH_PAINT_AXIS: u8 = 1 << 0;
const XYCH_PAINT_GRID: u8 = 1 << 1;
const XYCH_PAINT_TICK: u8 = 1 << 2;
#[allow(dead_code)] // hosts record authorship; opacity is always minor_grid_opacity
const XYCH_PAINT_MINOR_GRID: u8 = 1 << 3;
const XYCH_PAINT_MINOR_TICK: u8 = 1 << 4;
const XYCH_PAINT_LABEL: u8 = 1 << 5;
const CHROME_DEFAULT_AXIS_COLOR: &str = "#202020";
const CHROME_DEFAULT_GRID_COLOR: &str = "#202020";
const CHROME_DEFAULT_TICK_COLOR: &str = "#202020";
const CHROME_DEFAULT_MINOR_GRID_COLOR: &str = "transparent";
const CHROME_DEFAULT_MINOR_TICK_COLOR: &str = "#202020";
const CHROME_DEFAULT_LABEL_COLOR: &str = "#202020";
const CHROME_DEFAULT_AXIS_OPACITY: f32 = 0.55;
const CHROME_DEFAULT_GRID_OPACITY: f32 = 0.14;
const CHROME_DEFAULT_TICK_OPACITY: f32 = 0.55;
const CHROME_DEFAULT_MINOR_TICK_OPACITY: f32 = 0.55;
const CHROME_DEFAULT_LABEL_OPACITY: f32 = 0.85;
const CHROME_AXIS_OFFSETS: [usize; 2] = [24, 112];

/// Why an XYMS/XYCH envelope was rejected. Discriminants are the C-ABI error
/// codes (returned negated by `xyg_scene_resolve_mark_styles` and
/// `xyg_scene_resolve_chrome_style`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MarkStyleError {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
}

/// One resolved Scene style: fill RGBA8, stroke RGBA8, stroke width in px.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ResolvedMarkStyle {
    pub fill: [u8; 4],
    pub stroke: [u8; 4],
    pub stroke_width: f64,
}

impl ResolvedMarkStyle {
    pub fn to_bytes(self) -> [u8; XYMS_OUTPUT_BYTES] {
        let mut out = [0u8; XYMS_OUTPUT_BYTES];
        out[0..4].copy_from_slice(&self.fill);
        out[4..8].copy_from_slice(&self.stroke);
        out[8..16].copy_from_slice(&self.stroke_width.to_le_bytes());
        out
    }
}

struct Cursor<'a> {
    bytes: &'a [u8],
    offset: usize,
}

impl<'a> Cursor<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, offset: 0 }
    }

    fn remaining(&self) -> usize {
        self.bytes.len().saturating_sub(self.offset)
    }

    fn u8(&mut self) -> Result<u8, MarkStyleError> {
        let value = *self.bytes.get(self.offset).ok_or(MarkStyleError::Length)?;
        self.offset += 1;
        Ok(value)
    }

    fn u16(&mut self) -> Result<u16, MarkStyleError> {
        let raw = self
            .bytes
            .get(self.offset..self.offset + 2)
            .ok_or(MarkStyleError::Length)?;
        self.offset += 2;
        Ok(u16::from_le_bytes(
            raw.try_into().map_err(|_| MarkStyleError::Length)?,
        ))
    }

    fn u32(&mut self) -> Result<u32, MarkStyleError> {
        let raw = self
            .bytes
            .get(self.offset..self.offset + 4)
            .ok_or(MarkStyleError::Length)?;
        self.offset += 4;
        Ok(u32::from_le_bytes(
            raw.try_into().map_err(|_| MarkStyleError::Length)?,
        ))
    }

    fn f32(&mut self) -> Result<f32, MarkStyleError> {
        let raw = self
            .bytes
            .get(self.offset..self.offset + 4)
            .ok_or(MarkStyleError::Length)?;
        self.offset += 4;
        Ok(f32::from_le_bytes(
            raw.try_into().map_err(|_| MarkStyleError::Length)?,
        ))
    }

    fn f64(&mut self) -> Result<f64, MarkStyleError> {
        let raw = self
            .bytes
            .get(self.offset..self.offset + 8)
            .ok_or(MarkStyleError::Length)?;
        self.offset += 8;
        Ok(f64::from_le_bytes(
            raw.try_into().map_err(|_| MarkStyleError::Length)?,
        ))
    }

    fn bytes(&mut self, count: usize) -> Result<&'a [u8], MarkStyleError> {
        let end = self
            .offset
            .checked_add(count)
            .ok_or(MarkStyleError::Limit)?;
        let slice = self
            .bytes
            .get(self.offset..end)
            .ok_or(MarkStyleError::Length)?;
        self.offset = end;
        Ok(slice)
    }

    fn css(&mut self, len: u16) -> Result<&'a str, MarkStyleError> {
        let n = len as usize;
        if n > MAX_XYMS_CSS_BYTES {
            return Err(MarkStyleError::Limit);
        }
        let raw = self.bytes(n)?;
        std::str::from_utf8(raw).map_err(|_| MarkStyleError::Length)
    }
}

fn is_stroke_kind(kind: u8) -> bool {
    matches!(
        kind,
        KIND_LINE
            | KIND_BOX_WHISKER
            | KIND_BOX_MEDIAN
            | KIND_SEGMENTS
            | KIND_ERRORBAR
            | KIND_STEM
            | KIND_CONTOUR
    )
}

fn is_segment_kind(kind: u8) -> bool {
    matches!(
        kind,
        KIND_BOX_WHISKER
            | KIND_BOX_MEDIAN
            | KIND_SEGMENTS
            | KIND_ERRORBAR
            | KIND_STEM
            | KIND_CONTOUR
    )
}

fn is_band_kind(kind: u8) -> bool {
    matches!(kind, KIND_AREA | KIND_ERROR_BAND)
}

fn resolve_one(
    kind: u8,
    flags: u8,
    opacity: f32,
    fill_opacity: f32,
    stroke_opacity: f32,
    line_opacity: f32,
    stroke_width: f64,
    width: f64,
    line_width: f64,
    fill_css: &str,
    stroke_css: &str,
    line_color_css: &str,
    color_css: &str,
) -> ResolvedMarkStyle {
    let color = if color_css.is_empty() {
        DEFAULT_COLOR
    } else {
        color_css
    };
    let fill_default = if is_segment_kind(kind) {
        TRANSPARENT
    } else {
        color
    };
    let fill_value = if flags & FLAG_HAS_FILL != 0 {
        fill_css
    } else {
        fill_default
    };
    let mut stroke_default =
        if is_stroke_kind(kind) || (kind == KIND_SCATTER && flags & FLAG_LINE_ONLY_SYMBOL != 0) {
            color
        } else {
            TRANSPARENT
        };
    if kind == KIND_RIBBON {
        stroke_default = if flags & FLAG_HAS_STROKE != 0 {
            stroke_css
        } else {
            color
        };
    } else if kind == KIND_TRIANGLE_MESH {
        stroke_default = if flags & FLAG_HAS_STROKE != 0 {
            stroke_css
        } else {
            TRANSPARENT
        };
    }
    let (stroke_value, stroke_alpha) = if is_band_kind(kind) {
        let value = if flags & FLAG_HAS_LINE_COLOR != 0 {
            line_color_css
        } else {
            color
        };
        (value, opacity * stroke_opacity * line_opacity)
    } else {
        let value = if flags & FLAG_HAS_STROKE != 0 {
            stroke_css
        } else {
            stroke_default
        };
        (value, opacity * stroke_opacity)
    };
    let resolved_width = if flags & FLAG_HAS_STROKE_WIDTH != 0 {
        stroke_width
    } else if flags & FLAG_HAS_WIDTH != 0 {
        width
    } else if flags & FLAG_HAS_LINE_WIDTH != 0 {
        line_width
    } else if is_stroke_kind(kind) {
        1.5
    } else {
        0.0
    };
    ResolvedMarkStyle {
        fill: css::color_rgba8(fill_value, opacity * fill_opacity),
        stroke: css::color_rgba8(stroke_value, stroke_alpha),
        stroke_width: resolved_width,
    }
}

/// Resolve packed `XYMS` v1 mark styles to fill/stroke RGBA8 and width.
pub fn resolve_mark_styles(bytes: &[u8]) -> Result<Vec<ResolvedMarkStyle>, MarkStyleError> {
    if bytes.len() < XYMS_HEADER_BYTES {
        return Err(MarkStyleError::Length);
    }
    let mut cur = Cursor::new(bytes);
    let magic = cur.bytes(4)?;
    if magic != XYMS_MAGIC {
        return Err(MarkStyleError::Length);
    }
    let version = cur.u32()?;
    if version != XYMS_VERSION {
        return Err(MarkStyleError::Version);
    }
    let n_marks = cur.u32()? as usize;
    let _reserved = cur.u32()?;
    if n_marks > MAX_XYMS_MARKS {
        return Err(MarkStyleError::Limit);
    }
    let mut out = Vec::with_capacity(n_marks);
    for _ in 0..n_marks {
        if cur.remaining() < XYMS_RECORD_PREFIX {
            return Err(MarkStyleError::Length);
        }
        let kind = cur.u8()?;
        let flags = cur.u8()?;
        let _pad = cur.u16()?;
        let opacity = cur.f32()?;
        let fill_opacity = cur.f32()?;
        let stroke_opacity = cur.f32()?;
        let line_opacity = cur.f32()?;
        let stroke_width = cur.f64()?;
        let width = cur.f64()?;
        let line_width = cur.f64()?;
        let fill_len = cur.u16()?;
        let stroke_len = cur.u16()?;
        let line_color_len = cur.u16()?;
        let color_len = cur.u16()?;
        let fill_css = cur.css(fill_len)?;
        let stroke_css = cur.css(stroke_len)?;
        let line_color_css = cur.css(line_color_len)?;
        let color_css = cur.css(color_len)?;
        out.push(resolve_one(
            kind,
            flags,
            opacity,
            fill_opacity,
            stroke_opacity,
            line_opacity,
            stroke_width,
            width,
            line_width,
            fill_css,
            stroke_css,
            line_color_css,
            color_css,
        ));
    }
    if cur.remaining() != 0 {
        return Err(MarkStyleError::Length);
    }
    Ok(out)
}

/// Encode resolved styles into the C-ABI output buffer. Returns the mark
/// count, or `Output` when `out` is too small.
pub fn encode_mark_styles(
    styles: &[ResolvedMarkStyle],
    out: &mut [u8],
) -> Result<i32, MarkStyleError> {
    let needed = styles
        .len()
        .checked_mul(XYMS_OUTPUT_BYTES)
        .ok_or(MarkStyleError::Limit)?;
    if out.len() < needed {
        return Err(MarkStyleError::Output);
    }
    for (index, style) in styles.iter().enumerate() {
        let start = index * XYMS_OUTPUT_BYTES;
        out[start..start + XYMS_OUTPUT_BYTES].copy_from_slice(&style.to_bytes());
    }
    i32::try_from(styles.len()).map_err(|_| MarkStyleError::Limit)
}

/// Overlay authored chrome CSS/widths onto the Scene default 200-byte style.
///
/// Hosts pack sides, paint flags, opacities, widths, and CSS literals. Default
/// RGBA, default widths, `grid_opacity` scaling of the default grid color, and
/// CSS→RGBA8 stay here so Python and Node cannot drift.
pub fn resolve_chrome_style(
    bytes: &[u8],
) -> Result<[u8; SCENE_CHROME_STYLE_INPUT_BYTES], MarkStyleError> {
    if bytes.len() < XYCH_HEADER_BYTES {
        return Err(MarkStyleError::Length);
    }
    let mut cur = Cursor::new(bytes);
    let magic = cur.bytes(4)?;
    if magic != XYCH_MAGIC {
        return Err(MarkStyleError::Length);
    }
    let version = cur.u32()?;
    if version != XYCH_VERSION {
        return Err(MarkStyleError::Version);
    }
    let flags = cur.u32()?;
    let n_axes = ((flags >> XYCH_N_AXES_SHIFT) & XYCH_N_AXES_MASK) as usize;
    if n_axes > 2 {
        return Err(MarkStyleError::Limit);
    }
    let chart_len = cur.u16()?;
    let plot_len = cur.u16()?;
    let chart_css = cur.css(chart_len)?;
    let plot_css = cur.css(plot_len)?;

    let defaults = SceneChromeStyle::default_style().style_input();
    let mut out = [0u8; SCENE_CHROME_STYLE_INPUT_BYTES];
    out.copy_from_slice(&defaults);

    if flags & XYCH_FLAG_HAS_CHART_BG != 0 {
        let value = if chart_css.is_empty() {
            TRANSPARENT
        } else {
            chart_css
        };
        out[0..4].copy_from_slice(&css::color_rgba8(value, 1.0));
    }
    if flags & XYCH_FLAG_HAS_PLOT_BG != 0 {
        let value = if plot_css.is_empty() {
            TRANSPARENT
        } else {
            plot_css
        };
        out[4..8].copy_from_slice(&css::color_rgba8(value, 1.0));
    }

    for axis_index in 0..n_axes {
        if cur.remaining() < XYCH_AXIS_PREFIX {
            return Err(MarkStyleError::Length);
        }
        let side = cur.u8()?;
        let tick_sides = cur.u8()?;
        let tick_label_sides = cur.u8()?;
        let major_dir = cur.u8()?;
        let minor_dir = cur.u8()?;
        let paint_flags = cur.u8()?;
        let width_flags = cur.u8()?;
        let _reserved = cur.u8()?;
        let grid_opacity = cur.f32()?;
        let minor_grid_opacity = cur.f32()?;
        let mut widths = [0f64; 7];
        for width in &mut widths {
            *width = cur.f64()?;
        }
        let mut lens = [0u16; 6];
        for len in &mut lens {
            *len = cur.u16()?;
        }
        let axis_css = cur.css(lens[0])?;
        let grid_css = cur.css(lens[1])?;
        let tick_css = cur.css(lens[2])?;
        let minor_grid_css = cur.css(lens[3])?;
        let minor_tick_css = cur.css(lens[4])?;
        let label_css = cur.css(lens[5])?;

        let offset = CHROME_AXIS_OFFSETS[axis_index];
        out[offset] = side;
        out[offset + 1] = tick_sides;
        out[offset + 2] = tick_label_sides;
        out[offset + 3] = major_dir;
        out[offset + 4] = minor_dir;

        let paints = [
            (
                nonempty_css(axis_css, CHROME_DEFAULT_AXIS_COLOR),
                if paint_flags & XYCH_PAINT_AXIS != 0 {
                    1.0
                } else {
                    CHROME_DEFAULT_AXIS_OPACITY
                },
            ),
            (
                nonempty_css(grid_css, CHROME_DEFAULT_GRID_COLOR),
                grid_opacity
                    * if paint_flags & XYCH_PAINT_GRID != 0 {
                        1.0
                    } else {
                        CHROME_DEFAULT_GRID_OPACITY
                    },
            ),
            (
                nonempty_css(tick_css, CHROME_DEFAULT_TICK_COLOR),
                if paint_flags & XYCH_PAINT_TICK != 0 {
                    1.0
                } else {
                    CHROME_DEFAULT_TICK_OPACITY
                },
            ),
            (
                nonempty_css(minor_grid_css, CHROME_DEFAULT_MINOR_GRID_COLOR),
                minor_grid_opacity,
            ),
            (
                nonempty_css(minor_tick_css, CHROME_DEFAULT_MINOR_TICK_COLOR),
                if paint_flags & XYCH_PAINT_MINOR_TICK != 0 {
                    1.0
                } else {
                    CHROME_DEFAULT_MINOR_TICK_OPACITY
                },
            ),
            (
                nonempty_css(label_css, CHROME_DEFAULT_LABEL_COLOR),
                if paint_flags & XYCH_PAINT_LABEL != 0 {
                    1.0
                } else {
                    CHROME_DEFAULT_LABEL_OPACITY
                },
            ),
        ];
        for (index, (css_value, opacity)) in paints.into_iter().enumerate() {
            let start = offset + 8 + index * 4;
            out[start..start + 4].copy_from_slice(&css::color_rgba8(css_value, opacity));
        }
        for (index, width) in widths.into_iter().enumerate() {
            if width_flags & (1 << index) == 0 {
                continue;
            }
            let start = offset + 32 + index * 8;
            out[start..start + 8].copy_from_slice(&width.to_le_bytes());
        }
    }
    if cur.remaining() != 0 {
        return Err(MarkStyleError::Length);
    }
    Ok(out)
}

fn nonempty_css<'a>(value: &'a str, default: &'static str) -> &'a str {
    if value.is_empty() {
        default
    } else {
        value
    }
}

/// Copy the resolved 200-byte chrome style into the C-ABI output buffer.
pub fn encode_chrome_style(
    style: &[u8; SCENE_CHROME_STYLE_INPUT_BYTES],
    out: &mut [u8],
) -> Result<i32, MarkStyleError> {
    if out.len() < SCENE_CHROME_STYLE_INPUT_BYTES {
        return Err(MarkStyleError::Output);
    }
    out[..SCENE_CHROME_STYLE_INPUT_BYTES].copy_from_slice(style);
    i32::try_from(SCENE_CHROME_STYLE_INPUT_BYTES).map_err(|_| MarkStyleError::Limit)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn header(n: u32) -> Vec<u8> {
        let mut bytes = Vec::from(*XYMS_MAGIC);
        bytes.extend_from_slice(&XYMS_VERSION.to_le_bytes());
        bytes.extend_from_slice(&n.to_le_bytes());
        bytes.extend_from_slice(&0u32.to_le_bytes());
        bytes
    }

    fn push_record(
        bytes: &mut Vec<u8>,
        kind: u8,
        flags: u8,
        opacity: f32,
        fill_opacity: f32,
        stroke_opacity: f32,
        line_opacity: f32,
        stroke_width: f64,
        width: f64,
        line_width: f64,
        fill: &str,
        stroke: &str,
        line_color: &str,
        color: &str,
    ) {
        bytes.push(kind);
        bytes.push(flags);
        bytes.extend_from_slice(&0u16.to_le_bytes());
        for value in [opacity, fill_opacity, stroke_opacity, line_opacity] {
            bytes.extend_from_slice(&value.to_le_bytes());
        }
        for value in [stroke_width, width, line_width] {
            bytes.extend_from_slice(&value.to_le_bytes());
        }
        for css in [fill, stroke, line_color, color] {
            bytes.extend_from_slice(&(css.len() as u16).to_le_bytes());
        }
        bytes.extend_from_slice(fill.as_bytes());
        bytes.extend_from_slice(stroke.as_bytes());
        bytes.extend_from_slice(line_color.as_bytes());
        bytes.extend_from_slice(color.as_bytes());
    }

    #[test]
    fn default_scatter_is_filled_brand_blue() {
        let mut bytes = header(1);
        push_record(
            &mut bytes,
            KIND_SCATTER,
            0,
            1.0,
            1.0,
            1.0,
            1.0,
            0.0,
            0.0,
            0.0,
            "",
            "",
            "",
            "",
        );
        let styles = resolve_mark_styles(&bytes).unwrap();
        assert_eq!(styles[0].fill, css::color_rgba8(DEFAULT_COLOR, 1.0));
        assert_eq!(styles[0].stroke, css::color_rgba8(TRANSPARENT, 1.0));
        assert_eq!(styles[0].stroke_width, 0.0);
    }

    #[test]
    fn line_defaults_stroke_to_color_and_width_1_5() {
        let mut bytes = header(1);
        push_record(
            &mut bytes,
            KIND_LINE,
            0,
            1.0,
            1.0,
            1.0,
            1.0,
            0.0,
            0.0,
            0.0,
            "",
            "",
            "",
            "steelblue",
        );
        let styles = resolve_mark_styles(&bytes).unwrap();
        assert_eq!(styles[0].fill, css::color_rgba8("steelblue", 1.0));
        assert_eq!(styles[0].stroke, css::color_rgba8("steelblue", 1.0));
        assert_eq!(styles[0].stroke_width, 1.5);
    }

    #[test]
    fn segments_default_fill_transparent() {
        let mut bytes = header(1);
        push_record(
            &mut bytes,
            KIND_SEGMENTS,
            0,
            1.0,
            1.0,
            1.0,
            1.0,
            0.0,
            0.0,
            0.0,
            "",
            "",
            "",
            "",
        );
        let styles = resolve_mark_styles(&bytes).unwrap();
        assert_eq!(styles[0].fill, [0, 0, 0, 0]);
        assert_eq!(styles[0].stroke, css::color_rgba8(DEFAULT_COLOR, 1.0));
        assert_eq!(styles[0].stroke_width, 1.5);
    }

    #[test]
    fn line_only_scatter_strokes_in_the_fill_color() {
        let mut bytes = header(1);
        push_record(
            &mut bytes,
            KIND_SCATTER,
            FLAG_LINE_ONLY_SYMBOL,
            1.0,
            1.0,
            1.0,
            1.0,
            0.0,
            0.0,
            0.0,
            "",
            "",
            "",
            "#ff0000",
        );
        let styles = resolve_mark_styles(&bytes).unwrap();
        assert_eq!(styles[0].fill, css::color_rgba8("#ff0000", 1.0));
        assert_eq!(styles[0].stroke, css::color_rgba8("#ff0000", 1.0));
        assert_eq!(styles[0].stroke_width, 0.0);
    }

    #[test]
    fn band_uses_line_color_and_combined_opacity() {
        let mut bytes = header(1);
        push_record(
            &mut bytes,
            KIND_AREA,
            FLAG_HAS_LINE_COLOR,
            0.5,
            0.5,
            0.5,
            0.5,
            0.0,
            0.0,
            0.0,
            "",
            "",
            "black",
            "#3987e5",
        );
        let styles = resolve_mark_styles(&bytes).unwrap();
        assert_eq!(styles[0].fill, css::color_rgba8("#3987e5", 0.25));
        assert_eq!(styles[0].stroke, css::color_rgba8("black", 0.125));
        assert_eq!(styles[0].stroke_width, 0.0);
    }

    #[test]
    fn authored_stroke_width_wins() {
        let mut bytes = header(1);
        push_record(
            &mut bytes,
            KIND_LINE,
            FLAG_HAS_STROKE_WIDTH,
            1.0,
            1.0,
            1.0,
            1.0,
            3.25,
            9.0,
            8.0,
            "",
            "",
            "",
            "",
        );
        let styles = resolve_mark_styles(&bytes).unwrap();
        assert_eq!(styles[0].stroke_width, 3.25);
    }

    #[test]
    fn named_fill_matches_css_color_rgba8() {
        let mut bytes = header(1);
        push_record(
            &mut bytes,
            KIND_SCATTER,
            FLAG_HAS_FILL,
            1.0,
            1.0,
            1.0,
            1.0,
            0.0,
            0.0,
            0.0,
            "steelblue",
            "",
            "",
            "",
        );
        let styles = resolve_mark_styles(&bytes).unwrap();
        assert_eq!(styles[0].fill, [70, 130, 180, 255]);
    }

    #[test]
    fn rejects_trailing_bytes() {
        let mut bytes = header(0);
        bytes.push(0);
        assert_eq!(resolve_mark_styles(&bytes), Err(MarkStyleError::Length));
    }

    #[test]
    fn rejects_unknown_version() {
        let mut bytes = header(0);
        bytes[4..8].copy_from_slice(&2u32.to_le_bytes());
        assert_eq!(resolve_mark_styles(&bytes), Err(MarkStyleError::Version));
    }

    fn chrome_header(flags: u32, chart: &str, plot: &str) -> Vec<u8> {
        let mut bytes = Vec::from(*XYCH_MAGIC);
        bytes.extend_from_slice(&XYCH_VERSION.to_le_bytes());
        bytes.extend_from_slice(&flags.to_le_bytes());
        bytes.extend_from_slice(&(chart.len() as u16).to_le_bytes());
        bytes.extend_from_slice(&(plot.len() as u16).to_le_bytes());
        bytes.extend_from_slice(chart.as_bytes());
        bytes.extend_from_slice(plot.as_bytes());
        bytes
    }

    fn push_chrome_axis(
        bytes: &mut Vec<u8>,
        side: u8,
        tick_sides: u8,
        label_sides: u8,
        major_dir: u8,
        minor_dir: u8,
        paint_flags: u8,
        width_flags: u8,
        grid_opacity: f32,
        minor_grid_opacity: f32,
        widths: [f64; 7],
        paints: [&str; 6],
    ) {
        bytes.extend_from_slice(&[
            side,
            tick_sides,
            label_sides,
            major_dir,
            minor_dir,
            paint_flags,
            width_flags,
            0,
        ]);
        bytes.extend_from_slice(&grid_opacity.to_le_bytes());
        bytes.extend_from_slice(&minor_grid_opacity.to_le_bytes());
        for width in widths {
            bytes.extend_from_slice(&width.to_le_bytes());
        }
        for css in paints {
            bytes.extend_from_slice(&(css.len() as u16).to_le_bytes());
        }
        for css in paints {
            bytes.extend_from_slice(css.as_bytes());
        }
    }

    #[test]
    fn empty_chrome_envelope_is_scene_default() {
        let bytes = chrome_header(0, "", "");
        let resolved = resolve_chrome_style(&bytes).unwrap();
        assert_eq!(
            resolved.as_slice(),
            SceneChromeStyle::default_style().style_input()
        );
    }

    #[test]
    fn grid_opacity_scales_default_grid_paint() {
        let mut bytes = chrome_header(2 << XYCH_N_AXES_SHIFT, "", "");
        push_chrome_axis(
            &mut bytes,
            0,
            1,
            1,
            0,
            0,
            0,
            0,
            0.0,
            1.0,
            [1.0, 1.0, 1.0, 4.0, 1.0, 1.0, 0.0],
            ["", "", "", "", "", ""],
        );
        push_chrome_axis(
            &mut bytes,
            0,
            1,
            1,
            0,
            0,
            0,
            0,
            1.0,
            1.0,
            [1.0, 1.0, 1.0, 4.0, 1.0, 1.0, 0.0],
            ["", "", "", "", "", ""],
        );
        let resolved = resolve_chrome_style(&bytes).unwrap();
        assert_eq!(&resolved[24 + 12..24 + 16], &[32, 32, 32, 0]);
        assert_eq!(&resolved[112 + 12..112 + 16], &[32, 32, 32, 36]);
    }

    #[test]
    fn authored_axis_color_is_opaque() {
        let mut bytes = chrome_header(2 << XYCH_N_AXES_SHIFT, "", "");
        push_chrome_axis(
            &mut bytes,
            0,
            1,
            1,
            0,
            0,
            XYCH_PAINT_AXIS,
            1 << 0,
            1.0,
            1.0,
            [2.0, 1.0, 1.0, 4.0, 1.0, 1.0, 0.0],
            ["#ef4444", "", "", "", "", ""],
        );
        push_chrome_axis(
            &mut bytes,
            0,
            1,
            1,
            0,
            0,
            0,
            0,
            1.0,
            1.0,
            [1.0, 1.0, 1.0, 4.0, 1.0, 1.0, 0.0],
            ["", "", "", "", "", ""],
        );
        let resolved = resolve_chrome_style(&bytes).unwrap();
        assert_eq!(
            &resolved[24 + 8..24 + 12],
            &css::color_rgba8("#ef4444", 1.0)
        );
        assert_eq!(&resolved[24 + 32..24 + 40], &2.0f64.to_le_bytes());
        assert_eq!(&resolved[24 + 16..24 + 20], &[32, 32, 32, 140]);
    }

    #[test]
    fn chrome_rejects_unknown_version() {
        let mut bytes = chrome_header(0, "", "");
        bytes[4..8].copy_from_slice(&2u32.to_le_bytes());
        assert_eq!(resolve_chrome_style(&bytes), Err(MarkStyleError::Version));
    }

    #[test]
    fn chrome_rejects_too_many_axes() {
        let bytes = chrome_header(3 << XYCH_N_AXES_SHIFT, "", "");
        assert_eq!(resolve_chrome_style(&bytes), Err(MarkStyleError::Limit));
    }
}
