//! Compact Figure→Scene assembled encode (M2 #271).
//!
//! Hosts pass packed `XYAS` v1 (ABI 159), `XYCC` v1 chrome (ABI 153), wrapped
//! extras bytes (ABI 150), viewport, and axis scalars to `encode_assembled`.
//! ABI 162 `encode_assembled_from_sidecars` additionally owns XYCC packing
//! from `XYCF` plus `XYSD`, extras packing from polar plus `XYSD` plus `XYSS`,
//! and viewport/axis scalars from the `XYCF` header (axis ids 1 and 2) so
//! hosts do not pack chrome/extras or re-derive axes on the product path.
//! ABI 163 `encode_product` owns the remaining product-path orchestration
//! (compile, attach, sidecars, rows, annotation facts, style sidecars, splice,
//! then sidecar assembled encode) so hosts pack authored blobs once.
//! ABI 165 additionally owns the figure-compile support probe from packed
//! `XYFS` so product-path hosts do not call `scene_figure_support_reason`
//! separately. Empty `XYFS` skips the probe (stepwise ABI 163 callers).
//! ABI 189 consults packed XYTA during that probe so heatmap/hexbin cell-fill
//! tessellation eligibility is Rust-owned.
//! ABI 197 settles authored `loc="best"` from packed XYCL/XYNM plus XYCF
//! domains so hosts do not walk traces on the product path.
//! ABI 194 admits polar hexbin, custom host reducers, and categorical /
//! `direct_rgba` hexbin on that same HexCell intern.
//! ABI 190 intern per-item two-ended ribbon `color2_ch` from packed XYHP kind 5
//! onto Band `style_ref`s plus XYGR mark-space `dir=right`.
//! ABI 166 tessellates cartesian bar/column/histogram `corner_radius` from
//! packed XYSD radius blobs after pixel mapping. ABI 167 applies polar
//! `wedge_gap` from that same blob during `polar_wedge_points`. ABI 168
//! tessellates polar bar/column/histogram `corner_radius` from those same
//! packed radii when the inner radius is positive. ABI 173 tessellates heatmap
//! `corner_radius` from that same blob (cartesian rounded Rects / polar wedges).
//! ABI 174 tessellates violin/box `corner_radius` from that same blob.
//! ABI 175 admits violin/box `fill_opacity` / `stroke_opacity` from packed XYTC.
//! ABI 176 admits bar/column/histogram `fill_opacity` / `stroke_opacity` from that same packing.
//! ABI 177 admits heatmap `fill_opacity` from that same packing.
//! ABI 178 admits scatter `fill_opacity` / `stroke_opacity` from that same packing.
//! ABI 179 admits hexbin `fill_opacity` from that same packing.
//! ABI 180 admits triangle_mesh `fill_opacity` / constant stroke from that same packing.
//! ABI 186 admits cartesian colormap hexbin as a 1×N XYHP plane interned onto
//! HexCell PolyFills during expansion.
//! Encoded Scene v31 is
//! unchanged.

use crate::scene::{
    decode_tick_labels, expand_scene_records_painted, merge_dash_gradients,
    resolve_numeric_tick_formats, scene_text_advance, split_scene_extras, AxisScale, PlotLayout,
    ScaleKind, SceneBatch, SceneChromeStyle, SceneChromeText, SceneColorbar, SceneCornerRadius,
    SceneError, SceneExpansionInput, SceneLegend, MAX_AUTHORED_TEXT_ANNOTATIONS, MAX_AXIS_TICKS,
    MAX_SCENE_AXIS_FORMAT_BYTES, MAX_SCENE_COLORBAR_INPUT_BYTES, MAX_SCENE_LABEL_TEXT_BYTES,
    MAX_SCENE_LEGEND_ENTRIES, MAX_SCENE_LEGEND_TEXT_BYTES, MAX_SCENE_MARKS, MAX_SCENE_STYLES,
    MAX_SCENE_TEXT_BYTES, SCENE_CHROME_STYLE_INPUT_BYTES, SCENE_STYLE_RECORD_BYTES,
};
use crate::scene_annotation_splice::{
    splice_annotations, XYAS_HEADER_BYTES, XYAS_MAGIC, XYAS_VERSION,
};
use crate::scene_annotations::pack_annotation_facts;
use crate::scene_chrome::{
    pack_figure_chrome_with_polar, settle_legend_best_loc, ChromePackError, XYCC_HEADER_BYTES,
    XYCC_MAGIC, XYCC_VERSION, XYCF_HEADER_BYTES, XYCF_MAGIC,
};
use crate::scene_extras::{pack_scene_extras_from_sidecars, ExtrasError};
use crate::scene_pack::{PackedSceneRow, PACKED_SCENE_ROW_BYTES};
use crate::scene_style_sidecars::pack_style_sidecars;
use crate::scene_trace_attach::pack_trace_attach;
use crate::scene_trace_compile::pack_trace_compile;
use crate::scene_trace_rows::pack_trace_rows;
use crate::scene_trace_sidecars::{pack_trace_sidecars, parse_xysd_records};

/// Why an assembled-encode request was rejected. Discriminants are the
/// C-ABI error codes (returned negated by `xyg_scene_encode_assembled`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EncodeAssembledCode {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    Payload = 5,
    Encode = 6,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EncodeAssembledError {
    pub code: EncodeAssembledCode,
    pub index: u32,
}

impl EncodeAssembledError {
    fn new(code: EncodeAssembledCode, index: usize) -> Self {
        Self {
            code,
            index: index as u32,
        }
    }
}

/// Why an ABI 162 sidecar-assembled encode was rejected. Chrome failures keep
/// discriminants 1–15; encode failures except `Output` collapse to `Encode=16`;
/// extras failures except `Output` occupy 17–21 so they cannot alias chrome
/// `Version`/`Limit`/`Layout`/`Payload`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EncodeSidecarsCode {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    Layout = 5,
    Payload = 6,
    LegendKeys = 7,
    LegendStatic = 8,
    LegendLoc = 9,
    LegendFont = 10,
    LegendStyle = 11,
    ColorbarKeys = 12,
    ColorbarShape = 13,
    ColorbarSide = 14,
    Ticks = 15,
    Encode = 16,
    ExtrasLength = 17,
    ExtrasVersion = 18,
    ExtrasLimit = 19,
    ExtrasShape = 20,
    ExtrasPayload = 21,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EncodeSidecarsError {
    pub code: EncodeSidecarsCode,
    pub index: u32,
}

impl EncodeSidecarsError {
    fn new(code: EncodeSidecarsCode, index: u32) -> Self {
        Self { code, index }
    }
}

fn map_chrome(error: ChromePackError) -> EncodeSidecarsError {
    EncodeSidecarsError::new(
        match error {
            ChromePackError::Length => EncodeSidecarsCode::Length,
            ChromePackError::Version => EncodeSidecarsCode::Version,
            ChromePackError::Limit => EncodeSidecarsCode::Limit,
            ChromePackError::Output => EncodeSidecarsCode::Output,
            ChromePackError::Layout => EncodeSidecarsCode::Layout,
            ChromePackError::Payload => EncodeSidecarsCode::Payload,
            ChromePackError::LegendKeys => EncodeSidecarsCode::LegendKeys,
            ChromePackError::LegendStatic => EncodeSidecarsCode::LegendStatic,
            ChromePackError::LegendLoc => EncodeSidecarsCode::LegendLoc,
            ChromePackError::LegendFont => EncodeSidecarsCode::LegendFont,
            ChromePackError::LegendStyle => EncodeSidecarsCode::LegendStyle,
            ChromePackError::ColorbarKeys => EncodeSidecarsCode::ColorbarKeys,
            ChromePackError::ColorbarShape => EncodeSidecarsCode::ColorbarShape,
            ChromePackError::ColorbarSide => EncodeSidecarsCode::ColorbarSide,
            ChromePackError::Ticks => EncodeSidecarsCode::Ticks,
        },
        0,
    )
}

fn map_extras(error: ExtrasError) -> EncodeSidecarsError {
    EncodeSidecarsError::new(
        match error {
            ExtrasError::Length => EncodeSidecarsCode::ExtrasLength,
            ExtrasError::Version => EncodeSidecarsCode::ExtrasVersion,
            ExtrasError::Limit => EncodeSidecarsCode::ExtrasLimit,
            ExtrasError::Output => EncodeSidecarsCode::Output,
            ExtrasError::Shape => EncodeSidecarsCode::ExtrasShape,
            ExtrasError::Payload => EncodeSidecarsCode::ExtrasPayload,
        },
        0,
    )
}

fn map_encode(error: EncodeAssembledError) -> EncodeSidecarsError {
    EncodeSidecarsError::new(
        match error.code {
            EncodeAssembledCode::Output => EncodeSidecarsCode::Output,
            _ => EncodeSidecarsCode::Encode,
        },
        error.index,
    )
}

/// Stage offsets for ABI 163 product-encode error codes. Encode-sidecar
/// failures keep discriminants 1–21 (including shared `Output=4` retry);
/// other stages occupy `base + original` except `Output`, which stays 4.
pub const PRODUCT_STAGE_COMPILE: i32 = 100;
pub const PRODUCT_STAGE_ATTACH: i32 = 200;
pub const PRODUCT_STAGE_SIDECARS: i32 = 300;
pub const PRODUCT_STAGE_ROWS: i32 = 400;
pub const PRODUCT_STAGE_ANNOTATION: i32 = 500;
pub const PRODUCT_STAGE_STYLE: i32 = 600;
pub const PRODUCT_STAGE_SPLICE: i32 = 700;
pub const PRODUCT_STAGE_SUPPORT: i32 = 800;
/// Non-empty figure-compile diagnostic; UTF-8 reason follows a u32 length in `out`.
pub const PRODUCT_SUPPORT_UNSUPPORTED: i32 = 801;
/// Malformed or version-mismatched XYFS envelope.
pub const PRODUCT_SUPPORT_ENVELOPE: i32 = 802;

/// Why an ABI 163 product encode was rejected. Discriminants are the C-ABI
/// error codes (returned negated by `xyg_scene_encode_product`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProductEncodeError {
    pub code: i32,
    pub index: u32,
    pub reason: Vec<u8>,
}

fn map_stage(base: i32, code: i32, index: u32) -> ProductEncodeError {
    ProductEncodeError {
        code: if code == EncodeSidecarsCode::Output as i32 {
            EncodeSidecarsCode::Output as i32
        } else {
            base + code
        },
        index,
        reason: Vec::new(),
    }
}

/// Host axis scalars that `XYCC` does not carry. ABI 162 reads them from `XYCF`.
#[derive(Clone, Copy, Debug)]
pub struct EncodeAssembledAxis {
    pub id: u64,
    pub kind: u32,
    pub lo: f64,
    pub hi: f64,
    pub constant: f64,
    pub mask_nonpositive: i32,
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32, EncodeAssembledError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(EncodeAssembledError::new(EncodeAssembledCode::Length, 0))?
            .try_into()
            .map_err(|_| EncodeAssembledError::new(EncodeAssembledCode::Length, 0))?,
    ))
}

fn read_f64(bytes: &[u8], offset: usize) -> Result<f64, EncodeAssembledError> {
    Ok(f64::from_le_bytes(
        bytes
            .get(offset..offset + 8)
            .ok_or(EncodeAssembledError::new(EncodeAssembledCode::Length, 0))?
            .try_into()
            .map_err(|_| EncodeAssembledError::new(EncodeAssembledCode::Length, 0))?,
    ))
}

fn take<'a>(rest: &mut &'a [u8], n: usize, index: usize) -> Result<&'a [u8], EncodeAssembledError> {
    if rest.len() < n {
        return Err(EncodeAssembledError::new(
            EncodeAssembledCode::Length,
            index,
        ));
    }
    let (head, tail) = rest.split_at(n);
    *rest = tail;
    Ok(head)
}

fn map_scene(error: SceneError) -> EncodeAssembledError {
    EncodeAssembledError::new(
        match error {
            SceneError::Length => EncodeAssembledCode::Length,
            SceneError::Version => EncodeAssembledCode::Version,
            SceneError::Limit | SceneError::PainterTraceLimit => EncodeAssembledCode::Limit,
            SceneError::NonFinite | SceneError::NegativeSize | SceneError::InvalidPaint => {
                EncodeAssembledCode::Encode
            }
        },
        0,
    )
}

fn scale_kind(value: u32) -> Result<ScaleKind, EncodeAssembledError> {
    match value {
        0 => Ok(ScaleKind::Linear),
        1 => Ok(ScaleKind::Log),
        2 => Ok(ScaleKind::SymLog),
        _ => Err(EncodeAssembledError::new(EncodeAssembledCode::Length, 0)),
    }
}

fn utf8<'a>(bytes: &'a [u8]) -> Result<&'a str, EncodeAssembledError> {
    let value = std::str::from_utf8(bytes)
        .map_err(|_| EncodeAssembledError::new(EncodeAssembledCode::Length, 0))?;
    if value.contains('\0') {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Limit, 0));
    }
    Ok(value)
}

fn axis_format(bytes: &[u8]) -> Result<Option<&str>, EncodeAssembledError> {
    if bytes.len() > MAX_SCENE_AXIS_FORMAT_BYTES {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Limit, 0));
    }
    if bytes.is_empty() {
        return Ok(None);
    }
    Ok(Some(utf8(bytes)?))
}

struct ParsedXyAs {
    fill_rgba: Vec<u8>,
    stroke_rgba: Vec<u8>,
    stroke_width: Vec<f64>,
    kinds: Vec<u8>,
    symbols: Vec<u8>,
    expansion_modes: Vec<u8>,
    style_refs: Vec<u32>,
    stable_ids: Vec<u64>,
    diameter: Vec<f64>,
    x0: Vec<f64>,
    y0: Vec<f64>,
    x1: Vec<f64>,
    y1: Vec<f64>,
    xyad: Vec<u8>,
}

fn parse_xyas(bytes: &[u8]) -> Result<ParsedXyAs, EncodeAssembledError> {
    if bytes.len() < XYAS_HEADER_BYTES || bytes.get(..4) != Some(&XYAS_MAGIC[..]) {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Length, 0));
    }
    if read_u32(bytes, 4)? != XYAS_VERSION {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Version, 0));
    }
    let n_styles = read_u32(bytes, 8)? as usize;
    let n_rows = read_u32(bytes, 12)? as usize;
    let xyad_len = read_u32(bytes, 16)? as usize;
    if n_styles > MAX_SCENE_STYLES || n_rows > MAX_SCENE_MARKS {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Limit, 0));
    }
    let style_bytes = n_styles
        .checked_mul(SCENE_STYLE_RECORD_BYTES)
        .ok_or(EncodeAssembledError::new(EncodeAssembledCode::Limit, 0))?;
    let row_bytes = n_rows
        .checked_mul(PACKED_SCENE_ROW_BYTES)
        .ok_or(EncodeAssembledError::new(EncodeAssembledCode::Limit, 0))?;
    let mut rest = bytes
        .get(XYAS_HEADER_BYTES..)
        .ok_or(EncodeAssembledError::new(EncodeAssembledCode::Length, 0))?;
    let styles = take(&mut rest, style_bytes, 0)?;
    let rows = take(&mut rest, row_bytes, 0)?;
    let xyad = take(&mut rest, xyad_len, 0)?.to_vec();
    if !rest.is_empty() {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Payload, 0));
    }
    let max_xyad = MAX_SCENE_LABEL_TEXT_BYTES
        + MAX_AUTHORED_TEXT_ANNOTATIONS * 24
        + 44
        + 20
        + MAX_SCENE_AXIS_FORMAT_BYTES * 2;
    if xyad.len() > max_xyad {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Limit, 0));
    }
    let mut fill_rgba = Vec::with_capacity(n_styles.saturating_mul(4));
    let mut stroke_rgba = Vec::with_capacity(n_styles.saturating_mul(4));
    let mut stroke_width = Vec::with_capacity(n_styles);
    for index in 0..n_styles {
        let at = index * SCENE_STYLE_RECORD_BYTES;
        fill_rgba.extend_from_slice(&styles[at..at + 4]);
        stroke_rgba.extend_from_slice(&styles[at + 4..at + 8]);
        stroke_width.push(f64::from_le_bytes(
            styles[at + 8..at + 16]
                .try_into()
                .map_err(|_| EncodeAssembledError::new(EncodeAssembledCode::Length, index))?,
        ));
    }
    let mut kinds = Vec::with_capacity(n_rows);
    let mut symbols = Vec::with_capacity(n_rows);
    let mut expansion_modes = Vec::with_capacity(n_rows);
    let mut style_refs = Vec::with_capacity(n_rows);
    let mut stable_ids = Vec::with_capacity(n_rows);
    let mut diameter = Vec::with_capacity(n_rows);
    let mut x0 = Vec::with_capacity(n_rows);
    let mut y0 = Vec::with_capacity(n_rows);
    let mut x1 = Vec::with_capacity(n_rows);
    let mut y1 = Vec::with_capacity(n_rows);
    for index in 0..n_rows {
        let at = index * PACKED_SCENE_ROW_BYTES;
        let row = PackedSceneRow::from_bytes(&rows[at..at + PACKED_SCENE_ROW_BYTES]).ok_or(
            EncodeAssembledError::new(EncodeAssembledCode::Length, index),
        )?;
        kinds.push(row.kind);
        symbols.push(row.symbol);
        expansion_modes.push(row.expansion_mode);
        style_refs.push(row.style_ref);
        stable_ids.push(row.stable_id);
        diameter.push(row.diameter);
        x0.push(row.x0);
        y0.push(row.y0);
        x1.push(row.x1);
        y1.push(row.y1);
    }
    Ok(ParsedXyAs {
        fill_rgba,
        stroke_rgba,
        stroke_width,
        kinds,
        symbols,
        expansion_modes,
        style_refs,
        stable_ids,
        diameter,
        x0,
        y0,
        x1,
        y1,
        xyad,
    })
}

struct ParsedXyCc<'a> {
    margin_left: f64,
    margin_right: f64,
    margin_top: f64,
    margin_bottom: f64,
    chrome_style: &'a [u8],
    title: &'a str,
    x_label: &'a str,
    y_label: &'a str,
    x_major: Option<Vec<f64>>,
    x_minor: Vec<f64>,
    y_major: Option<Vec<f64>>,
    y_minor: Vec<f64>,
    x_tick_labels: Option<Vec<String>>,
    y_tick_labels: Option<Vec<String>>,
    x_format: Option<&'a str>,
    y_format: Option<&'a str>,
    legend: &'a [u8],
    colorbar: &'a [u8],
}

fn take_f64s(rest: &mut &[u8], count: usize) -> Result<Vec<f64>, EncodeAssembledError> {
    if count > MAX_AXIS_TICKS {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Limit, 0));
    }
    let raw = take(rest, count.saturating_mul(8), 0)?;
    let mut values = Vec::with_capacity(count);
    for chunk in raw.chunks_exact(8) {
        values.push(f64::from_le_bytes(chunk.try_into().map_err(|_| {
            EncodeAssembledError::new(EncodeAssembledCode::Length, 0)
        })?));
    }
    Ok(values)
}

fn parse_xycc(bytes: &[u8]) -> Result<ParsedXyCc<'_>, EncodeAssembledError> {
    if bytes.len() < XYCC_HEADER_BYTES || bytes.get(..4) != Some(&XYCC_MAGIC[..]) {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Length, 0));
    }
    if read_u32(bytes, 4)? != XYCC_VERSION {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Version, 0));
    }
    let margin_left = read_f64(bytes, 16)?;
    let margin_right = read_f64(bytes, 24)?;
    let margin_top = read_f64(bytes, 32)?;
    let margin_bottom = read_f64(bytes, 40)?;
    let chrome_len = read_u32(bytes, 48)? as usize;
    let title_len = read_u32(bytes, 52)? as usize;
    let xlabel_len = read_u32(bytes, 56)? as usize;
    let ylabel_len = read_u32(bytes, 60)? as usize;
    let x_major_count = read_u32(bytes, 64)? as usize;
    let x_major_auto = read_u32(bytes, 68)?;
    let x_minor_count = read_u32(bytes, 72)? as usize;
    let y_major_count = read_u32(bytes, 76)? as usize;
    let y_major_auto = read_u32(bytes, 80)?;
    let y_minor_count = read_u32(bytes, 84)? as usize;
    let x_labels_len = read_u32(bytes, 88)? as usize;
    let y_labels_len = read_u32(bytes, 92)? as usize;
    let x_format_len = read_u32(bytes, 96)? as usize;
    let y_format_len = read_u32(bytes, 100)? as usize;
    let legend_len = read_u32(bytes, 104)? as usize;
    let colorbar_len = read_u32(bytes, 108)? as usize;
    if chrome_len != SCENE_CHROME_STYLE_INPUT_BYTES
        || !matches!(x_major_auto, 0 | 1)
        || !matches!(y_major_auto, 0 | 1)
        || (x_major_auto == 1 && x_major_count != 0)
        || (y_major_auto == 1 && y_major_count != 0)
    {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Length, 0));
    }
    if title_len > MAX_SCENE_TEXT_BYTES
        || xlabel_len > MAX_SCENE_TEXT_BYTES
        || ylabel_len > MAX_SCENE_TEXT_BYTES
        || x_format_len > MAX_SCENE_AXIS_FORMAT_BYTES
        || y_format_len > MAX_SCENE_AXIS_FORMAT_BYTES
        || [x_major_count, x_minor_count, y_major_count, y_minor_count]
            .into_iter()
            .any(|count| count > MAX_AXIS_TICKS)
        || x_labels_len > MAX_SCENE_TEXT_BYTES + MAX_AXIS_TICKS * 4 + 12
        || y_labels_len > MAX_SCENE_TEXT_BYTES + MAX_AXIS_TICKS * 4 + 12
        || legend_len > MAX_SCENE_LEGEND_TEXT_BYTES + MAX_SCENE_LEGEND_ENTRIES * 24 + 48
        || colorbar_len > MAX_SCENE_COLORBAR_INPUT_BYTES
    {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Limit, 0));
    }
    let mut rest = bytes
        .get(XYCC_HEADER_BYTES..)
        .ok_or(EncodeAssembledError::new(EncodeAssembledCode::Length, 0))?;
    let chrome_style = take(&mut rest, chrome_len, 0)?;
    let title = utf8(take(&mut rest, title_len, 0)?)?;
    let x_label = utf8(take(&mut rest, xlabel_len, 0)?)?;
    let y_label = utf8(take(&mut rest, ylabel_len, 0)?)?;
    let x_major_values = take_f64s(&mut rest, x_major_count)?;
    let x_minor = take_f64s(&mut rest, x_minor_count)?;
    let y_major_values = take_f64s(&mut rest, y_major_count)?;
    let y_minor = take_f64s(&mut rest, y_minor_count)?;
    let x_tick_labels = decode_tick_labels(take(&mut rest, x_labels_len, 0)?).map_err(map_scene)?;
    let y_tick_labels = decode_tick_labels(take(&mut rest, y_labels_len, 0)?).map_err(map_scene)?;
    let x_format = axis_format(take(&mut rest, x_format_len, 0)?)?;
    let y_format = axis_format(take(&mut rest, y_format_len, 0)?)?;
    let legend = take(&mut rest, legend_len, 0)?;
    let colorbar = take(&mut rest, colorbar_len, 0)?;
    if !rest.is_empty() {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Payload, 0));
    }
    Ok(ParsedXyCc {
        margin_left,
        margin_right,
        margin_top,
        margin_bottom,
        chrome_style,
        title,
        x_label,
        y_label,
        x_major: (x_major_auto == 0).then_some(x_major_values),
        x_minor,
        y_major: (y_major_auto == 0).then_some(y_major_values),
        y_minor,
        x_tick_labels,
        y_tick_labels,
        x_format,
        y_format,
        legend,
        colorbar,
    })
}

fn visible_label_indices(values: &[f64], lo: f64, hi: f64) -> Vec<usize> {
    let low = lo.min(hi);
    let high = lo.max(hi);
    values
        .iter()
        .enumerate()
        .filter_map(|(index, value)| (*value >= low && *value <= high).then_some(index))
        .collect()
}

fn widen_gutters(
    chrome: &ParsedXyCc<'_>,
    x_axis: EncodeAssembledAxis,
    y_axis: EncodeAssembledAxis,
) -> (f64, f64, f64) {
    let mut margin_left = chrome.margin_left;
    let mut margin_right = chrome.margin_right;
    let mut margin_bottom = chrome.margin_bottom;
    if let Some(labels) = &chrome.y_tick_labels {
        let indices = visible_label_indices(
            chrome.y_major.as_deref().unwrap_or(&[]),
            y_axis.lo,
            y_axis.hi,
        );
        let widest = indices
            .iter()
            .filter_map(|index| labels.get(*index))
            .map(|label| scene_text_advance(label, 12.0))
            .fold(0.0, f64::max);
        margin_left = margin_left.max(8.0 + widest);
    }
    if let Some(labels) = &chrome.x_tick_labels {
        let indices = visible_label_indices(
            chrome.x_major.as_deref().unwrap_or(&[]),
            x_axis.lo,
            x_axis.hi,
        );
        margin_bottom = margin_bottom.max(24.0);
        if let Some(first) = indices.first().and_then(|index| labels.get(*index)) {
            margin_left = margin_left.max(8.0 + scene_text_advance(first, 12.0) * 0.5);
        }
        if let Some(last) = indices.last().and_then(|index| labels.get(*index)) {
            margin_right = margin_right.max(8.0 + scene_text_advance(last, 12.0) * 0.5);
        }
    }
    (margin_left, margin_right, margin_bottom)
}

/// Encode packed XYAS + XYCC + extras into a canonical Scene v31 batch.
pub fn encode_assembled(
    xyas: &[u8],
    chrome: &[u8],
    extras: &[u8],
    viewport_width: f64,
    viewport_height: f64,
    x_axis: EncodeAssembledAxis,
    y_axis: EncodeAssembledAxis,
) -> Result<Vec<u8>, EncodeAssembledError> {
    encode_assembled_with_radii(
        xyas,
        chrome,
        extras,
        viewport_width,
        viewport_height,
        x_axis,
        y_axis,
        Vec::new(),
    )
}

#[allow(clippy::too_many_arguments)] // assembled encode plus optional radii
fn encode_assembled_with_radii(
    xyas: &[u8],
    chrome: &[u8],
    extras: &[u8],
    viewport_width: f64,
    viewport_height: f64,
    x_axis: EncodeAssembledAxis,
    y_axis: EncodeAssembledAxis,
    corner_radii: Vec<Option<SceneCornerRadius>>,
) -> Result<Vec<u8>, EncodeAssembledError> {
    if !matches!(x_axis.mask_nonpositive, 0 | 1) || !matches!(y_axis.mask_nonpositive, 0 | 1) {
        return Err(EncodeAssembledError::new(EncodeAssembledCode::Length, 0));
    }
    let parsed = parse_xyas(xyas)?;
    let chrome = parse_xycc(chrome)?;
    let (polar_bytes, paint_bytes, dash_bytes) = split_scene_extras(extras)
        .ok_or(EncodeAssembledError::new(EncodeAssembledCode::Payload, 0))?;
    let x_kind = scale_kind(x_axis.kind)?;
    let y_kind = scale_kind(y_axis.kind)?;
    let (margin_left, margin_right, margin_bottom) = widen_gutters(&chrome, x_axis, y_axis);
    let layout = PlotLayout::new(
        viewport_width,
        viewport_height,
        margin_left,
        margin_right,
        chrome.margin_top,
        margin_bottom,
    )
    .map_err(map_scene)?;
    let x_scale = AxisScale::new(
        x_kind,
        x_axis.lo,
        x_axis.hi,
        layout.left,
        layout.right,
        x_axis.constant,
        x_axis.mask_nonpositive != 0,
    )
    .map_err(map_scene)?;
    let y_scale = AxisScale::new(
        y_kind,
        y_axis.lo,
        y_axis.hi,
        layout.bottom,
        layout.top,
        y_axis.constant,
        y_axis.mask_nonpositive != 0,
    )
    .map_err(map_scene)?;
    let (records, painted_styles, images) = expand_scene_records_painted(
        SceneExpansionInput {
            kinds: &parsed.kinds,
            stable_ids: &parsed.stable_ids,
            style_refs: &parsed.style_refs,
            diameter: &parsed.diameter,
            symbols: &parsed.symbols,
            x0: &parsed.x0,
            y0: &parsed.y0,
            x1: &parsed.x1,
            y1: &parsed.y1,
            expansion_modes: &parsed.expansion_modes,
        },
        x_scale,
        y_scale,
        &parsed.fill_rgba,
        &parsed.stroke_rgba,
        &parsed.stroke_width,
        paint_bytes,
        !polar_bytes.is_empty(),
    )
    .map_err(map_scene)?;
    let (fill_rgba, stroke_rgba, stroke_width) = match &painted_styles {
        Some(styles) => (
            styles.fill_rgba.as_slice(),
            styles.stroke_rgba.as_slice(),
            styles.stroke_width.as_slice(),
        ),
        None => (
            parsed.fill_rgba.as_slice(),
            parsed.stroke_rgba.as_slice(),
            parsed.stroke_width.as_slice(),
        ),
    };
    let dash_merged = match &painted_styles {
        Some(styles) if !styles.extra_xygr.is_empty() => {
            merge_dash_gradients(dash_bytes, &styles.extra_xygr).map_err(map_scene)?
        }
        _ => dash_bytes.to_vec(),
    };
    let text = SceneChromeText::from_parts(chrome.title, chrome.x_label, chrome.y_label)
        .map_err(map_scene)?;
    let legend =
        SceneLegend::from_input(chrome.legend, parsed.stroke_width.len()).map_err(map_scene)?;
    let colorbar = SceneColorbar::from_input(chrome.colorbar).map_err(map_scene)?;
    let mut style = SceneChromeStyle::from_style_input(
        chrome.chrome_style,
        chrome.x_major.clone(),
        chrome.x_minor.clone(),
        chrome.y_major.clone(),
        chrome.y_minor.clone(),
    )
    .map_err(map_scene)?;
    style.x_tick_labels = chrome.x_tick_labels.clone();
    style.y_tick_labels = chrome.y_tick_labels.clone();
    resolve_numeric_tick_formats(
        layout,
        x_scale,
        y_scale,
        &mut style,
        chrome.x_format,
        chrome.y_format,
    )
    .map_err(map_scene)?;
    let style = style.validated().map_err(map_scene)?;
    let batch = SceneBatch::new_with_decorations_colorbar(
        layout,
        x_axis.id,
        y_axis.id,
        x_scale,
        y_scale,
        style,
        text,
        legend,
        colorbar,
        Vec::new(),
        &records.kinds,
        &records.stable_ids,
        &records.style_refs,
        fill_rgba,
        stroke_rgba,
        stroke_width,
        &records.diameter,
        &records.symbols,
        &records.x0,
        &records.y0,
        &records.x1,
        &records.y1,
    )
    .map_err(map_scene)?;
    Ok(batch
        .with_images(images)
        .map_err(map_scene)?
        .with_dashes(&dash_merged)
        .map_err(map_scene)?
        .with_polar(polar_bytes)
        .map_err(map_scene)?
        .with_authored_annotations(&parsed.xyad)
        .map_err(map_scene)?
        .with_corner_radii(corner_radii)
        .map_err(map_scene)?
        .encode())
}

fn axes_from_chrome_facts(
    facts: &[u8],
) -> Result<(f64, f64, EncodeAssembledAxis, EncodeAssembledAxis), EncodeSidecarsError> {
    if facts.len() < XYCF_HEADER_BYTES || facts.get(..4) != Some(&XYCF_MAGIC[..]) {
        return Err(EncodeSidecarsError::new(EncodeSidecarsCode::Length, 0));
    }
    let length = EncodeSidecarsError::new(EncodeSidecarsCode::Length, 0);
    let viewport_width = read_f64(facts, 16).map_err(|_| length)?;
    let viewport_height = read_f64(facts, 24).map_err(|_| length)?;
    Ok((
        viewport_width,
        viewport_height,
        EncodeAssembledAxis {
            id: 1,
            kind: read_u32(facts, 96).map_err(|_| length)?,
            lo: read_f64(facts, 104).map_err(|_| length)?,
            hi: read_f64(facts, 112).map_err(|_| length)?,
            constant: read_f64(facts, 120).map_err(|_| length)?,
            mask_nonpositive: i32::from(*facts.get(152).ok_or(length)? != 0),
        },
        EncodeAssembledAxis {
            id: 2,
            kind: read_u32(facts, 100).map_err(|_| length)?,
            lo: read_f64(facts, 128).map_err(|_| length)?,
            hi: read_f64(facts, 136).map_err(|_| length)?,
            constant: read_f64(facts, 144).map_err(|_| length)?,
            mask_nonpositive: i32::from(*facts.get(153).ok_or(length)? != 0),
        },
    ))
}

/// Encode packed XYAS from XYCF + XYSD + polar + XYSS.
///
/// Rust packs XYCC and extras, reads viewport/axes from XYCF (ids 1 and 2),
/// then runs `encode_assembled` so hosts do not re-derive those scalars.
pub fn encode_assembled_from_sidecars(
    xyas: &[u8],
    chrome_facts: &[u8],
    xysd: &[u8],
    polar: &[u8],
    extras_facts: &[u8],
) -> Result<Vec<u8>, EncodeSidecarsError> {
    let chrome = pack_figure_chrome_with_polar(chrome_facts, xysd, polar).map_err(map_chrome)?;
    let extras = pack_scene_extras_from_sidecars(polar, xysd, extras_facts).map_err(map_extras)?;
    let (viewport_width, viewport_height, x_axis, y_axis) = axes_from_chrome_facts(chrome_facts)?;
    let corner_radii = corner_radii_from_xysd(xysd).map_err(map_encode)?;
    encode_assembled_with_radii(
        xyas,
        &chrome,
        &extras,
        viewport_width,
        viewport_height,
        x_axis,
        y_axis,
        corner_radii,
    )
    .map_err(map_encode)
}

fn corner_radii_from_xysd(
    xysd: &[u8],
) -> Result<Vec<Option<SceneCornerRadius>>, EncodeAssembledError> {
    if xysd.is_empty() {
        return Ok(Vec::new());
    }
    let records = parse_xysd_records(xysd).map_err(|error| {
        EncodeAssembledError::new(EncodeAssembledCode::Payload, error.index as usize)
    })?;
    Ok(records
        .into_iter()
        .map(|record| {
            if record.r_tip == 0.0 && record.r_base == 0.0 && record.wedge_gap == 0.0 {
                None
            } else {
                Some(SceneCornerRadius {
                    r_tip: record.r_tip,
                    r_base: record.r_base,
                    force_tip_top: record.tip_policy != 0,
                    wedge_gap: record.wedge_gap,
                })
            }
        })
        .collect())
}

/// Encode a product Scene from packed authored blobs.
///
/// Rust owns compile, attach, sidecar, row, annotation, style-sidecar, splice,
/// and sidecar assembled encode so hosts pack XYTC/XYTA/XYNM/XYCL/XYAF/XYCF/
/// polar once. ABI 165 also owns the figure-compile support probe from packed
/// XYFS; empty XYFS skips that probe. Encoded Scene v31 is unchanged.
#[allow(clippy::too_many_arguments)] // authored blob list is the ABI 165 contract
pub fn encode_product(
    xytc: &[u8],
    xyta: &[u8],
    xynm: &[u8],
    xycl: &[u8],
    xyaf: &[u8],
    style_ref_base: u32,
    x_lo: f64,
    x_hi: f64,
    y_lo: f64,
    y_hi: f64,
    xycf: &[u8],
    polar: &[u8],
    xyfs: &[u8],
) -> Result<Vec<u8>, ProductEncodeError> {
    if !xyfs.is_empty() {
        match crate::scene_figure_support_reason_with_attach(xyfs, xyta) {
            Ok(reason) if !reason.is_empty() => {
                return Err(ProductEncodeError {
                    code: PRODUCT_SUPPORT_UNSUPPORTED,
                    index: 0,
                    reason: reason.into_bytes(),
                });
            }
            Ok(_) => {}
            Err(_) => {
                return Err(ProductEncodeError {
                    code: PRODUCT_SUPPORT_ENVELOPE,
                    index: 0,
                    reason: Vec::new(),
                });
            }
        }
    }
    let compiled = pack_trace_compile(xytc)
        .map_err(|error| map_stage(PRODUCT_STAGE_COMPILE, error.code as i32, error.index))?;
    let attached = pack_trace_attach(&compiled, xyta)
        .map_err(|error| map_stage(PRODUCT_STAGE_ATTACH, error.code as i32, error.index))?;
    let sidecars = pack_trace_sidecars(&attached, xynm)
        .map_err(|error| map_stage(PRODUCT_STAGE_SIDECARS, error.code as i32, error.index))?;
    let packed_rows = pack_trace_rows(&attached, xycl)
        .map_err(|error| map_stage(PRODUCT_STAGE_ROWS, error.code as i32, error.index))?;
    let mut row_bytes = Vec::with_capacity(packed_rows.len() * PACKED_SCENE_ROW_BYTES);
    for row in packed_rows {
        row_bytes.extend_from_slice(&row.to_bytes());
    }
    let annotations = pack_annotation_facts(xyaf, style_ref_base, x_lo, x_hi, y_lo, y_hi)
        .map_err(|error| map_stage(PRODUCT_STAGE_ANNOTATION, error as i32, 0))?;
    let extras_facts = pack_style_sidecars(&sidecars, &annotations)
        .map_err(|error| map_stage(PRODUCT_STAGE_STYLE, error.code as i32, error.index))?;
    let xyas = splice_annotations(&row_bytes, &sidecars, &annotations)
        .map_err(|error| map_stage(PRODUCT_STAGE_SPLICE, error.code as i32, error.index))?;
    let xycf = settle_legend_best_loc(xycf, xycl, xynm).map_err(|error| ProductEncodeError {
        code: map_chrome(error).code as i32,
        index: 0,
        reason: Vec::new(),
    })?;
    encode_assembled_from_sidecars(&xyas, &xycf, &sidecars, polar, &extras_facts).map_err(|error| {
        ProductEncodeError {
            code: error.code as i32,
            index: error.index,
            reason: Vec::new(),
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scene::{cartesian_scene_margins, CartesianLayoutRequest, ColorbarSide};
    use crate::scene_annotation_splice::{splice_annotations, XYAS_HEADER_BYTES};
    use crate::scene_chrome::{
        pack_figure_chrome, FLAG_X_MAJOR_AUTO, FLAG_Y_MAJOR_AUTO, XYCC_MAGIC, XYCF_HEADER_BYTES,
        XYCF_MAGIC, XYCF_VERSION,
    };
    use crate::scene_trace_attach::{XYTA_HEADER_BYTES, XYTA_MAGIC, XYTA_VERSION};
    use crate::scene_trace_compile::{XYTC_HEADER_BYTES, XYTC_MAGIC, XYTC_VERSION};
    use crate::scene_trace_rows::{XYCL_HEADER_BYTES, XYCL_MAGIC, XYCL_VERSION};
    use crate::scene_trace_sidecars::{
        pack_trace_sidecars, XYNM_HEADER_BYTES, XYNM_MAGIC, XYNM_VERSION,
    };

    fn empty_xysd() -> Vec<u8> {
        let mut xytt = vec![0u8; 16];
        xytt[..4].copy_from_slice(b"XYTT");
        xytt[4..8].copy_from_slice(&1u32.to_le_bytes());
        let mut xynm = vec![0u8; XYNM_HEADER_BYTES];
        xynm[..4].copy_from_slice(XYNM_MAGIC);
        xynm[4..8].copy_from_slice(&XYNM_VERSION.to_le_bytes());
        pack_trace_sidecars(&xytt, &xynm).unwrap()
    }

    fn empty_chrome_facts() -> Vec<u8> {
        let mut facts = vec![0u8; XYCF_HEADER_BYTES];
        facts[..4].copy_from_slice(XYCF_MAGIC);
        facts[4..8].copy_from_slice(&XYCF_VERSION.to_le_bytes());
        facts[8..12].copy_from_slice(&(FLAG_X_MAJOR_AUTO | FLAG_Y_MAJOR_AUTO).to_le_bytes());
        facts[16..24].copy_from_slice(&400.0f64.to_le_bytes());
        facts[24..32].copy_from_slice(&300.0f64.to_le_bytes());
        facts[112..120].copy_from_slice(&1.0f64.to_le_bytes());
        facts[120..128].copy_from_slice(&1.0f64.to_le_bytes());
        facts[136..144].copy_from_slice(&1.0f64.to_le_bytes());
        facts[144..152].copy_from_slice(&1.0f64.to_le_bytes());
        facts[212..216].copy_from_slice(&1u32.to_le_bytes());
        facts
    }

    fn empty_chrome() -> Vec<u8> {
        pack_figure_chrome(&empty_chrome_facts()).unwrap()
    }

    fn linear_axis() -> EncodeAssembledAxis {
        EncodeAssembledAxis {
            id: 1,
            kind: 0,
            lo: 0.0,
            hi: 1.0,
            constant: 1.0,
            mask_nonpositive: 0,
        }
    }

    #[test]
    fn empty_xyas_and_chrome_encode_scene() {
        let xyas = splice_annotations(&[], &empty_xysd(), &[]).unwrap();
        assert_eq!(xyas.len(), XYAS_HEADER_BYTES);
        let chrome = empty_chrome();
        assert_eq!(&chrome[..4], XYCC_MAGIC);
        let encoded = encode_assembled(
            &xyas,
            &chrome,
            &[],
            400.0,
            300.0,
            EncodeAssembledAxis {
                id: 1,
                ..linear_axis()
            },
            EncodeAssembledAxis {
                id: 2,
                ..linear_axis()
            },
        )
        .unwrap();
        assert_eq!(&encoded[..4], b"XYGS");
        assert_eq!(u32::from_le_bytes(encoded[4..8].try_into().unwrap()), 31);
        let expected = cartesian_scene_margins(CartesianLayoutRequest {
            viewport_width: 400.0,
            viewport_height: 300.0,
            authored_padding: None,
            title: "",
            x_label: "",
            y_label: "",
            x_kind: ScaleKind::Linear,
            x_lo: 0.0,
            x_hi: 1.0,
            x_constant: 1.0,
            x_mask_nonpositive: false,
            x_format: None,
            y_kind: ScaleKind::Linear,
            y_lo: 0.0,
            y_hi: 1.0,
            y_constant: 1.0,
            y_mask_nonpositive: false,
            y_format: None,
            colorbar_side: ColorbarSide::None,
        })
        .unwrap();
        assert!(expected.0 >= 0.0 && expected.1 >= 0.0);
    }

    #[test]
    fn unknown_xyas_version_is_version() {
        let mut xyas = splice_annotations(&[], &empty_xysd(), &[]).unwrap();
        xyas[4..8].copy_from_slice(&2u32.to_le_bytes());
        let error = encode_assembled(
            &xyas,
            &empty_chrome(),
            &[],
            400.0,
            300.0,
            linear_axis(),
            EncodeAssembledAxis {
                id: 2,
                ..linear_axis()
            },
        )
        .unwrap_err();
        assert_eq!(error.code, EncodeAssembledCode::Version);
    }

    #[test]
    fn packed_row_round_trips() {
        let row = PackedSceneRow {
            kind: 1,
            symbol: 0,
            expansion_mode: 11,
            style_ref: 3,
            stable_id: 9,
            diameter: 0.0,
            x0: 1.0,
            y0: 2.0,
            x1: 3.0,
            y1: 4.0,
        };
        assert_eq!(PackedSceneRow::from_bytes(&row.to_bytes()), Some(row));
    }

    #[test]
    fn sidecars_match_packed_encode() {
        let xyas = splice_annotations(&[], &empty_xysd(), &[]).unwrap();
        let xysd = empty_xysd();
        let packed = encode_assembled(
            &xyas,
            &empty_chrome(),
            &[],
            400.0,
            300.0,
            EncodeAssembledAxis {
                id: 1,
                ..linear_axis()
            },
            EncodeAssembledAxis {
                id: 2,
                ..linear_axis()
            },
        )
        .unwrap();
        let from_sidecars =
            encode_assembled_from_sidecars(&xyas, &empty_chrome_facts(), &xysd, &[], &[]).unwrap();
        assert_eq!(from_sidecars, packed);
    }

    #[test]
    fn sidecars_invalid_polar_is_extras_shape() {
        let xyas = splice_annotations(&[], &empty_xysd(), &[]).unwrap();
        let error = encode_assembled_from_sidecars(
            &xyas,
            &empty_chrome_facts(),
            &empty_xysd(),
            &[0u8; 8],
            &[],
        )
        .unwrap_err();
        assert_eq!(error.code, EncodeSidecarsCode::ExtrasShape);
    }

    #[test]
    fn sidecars_short_chrome_is_length() {
        let xyas = splice_annotations(&[], &empty_xysd(), &[]).unwrap();
        let error =
            encode_assembled_from_sidecars(&xyas, &[0u8; 2], &empty_xysd(), &[], &[]).unwrap_err();
        assert_eq!(error.code, EncodeSidecarsCode::Length);
    }

    #[test]
    fn sidecars_unknown_xyas_version_is_encode() {
        let mut xyas = splice_annotations(&[], &empty_xysd(), &[]).unwrap();
        xyas[4..8].copy_from_slice(&2u32.to_le_bytes());
        let error =
            encode_assembled_from_sidecars(&xyas, &empty_chrome_facts(), &empty_xysd(), &[], &[])
                .unwrap_err();
        assert_eq!(error.code, EncodeSidecarsCode::Encode);
    }

    fn empty_header(magic: &[u8; 4], version: u32, bytes: usize) -> Vec<u8> {
        let mut header = vec![0u8; bytes];
        header[..4].copy_from_slice(magic);
        header[4..8].copy_from_slice(&version.to_le_bytes());
        header
    }

    #[test]
    fn product_matches_sidecar_encode() {
        let xytc = empty_header(XYTC_MAGIC, XYTC_VERSION, XYTC_HEADER_BYTES);
        let xyta = empty_header(XYTA_MAGIC, XYTA_VERSION, XYTA_HEADER_BYTES);
        let xynm = empty_header(XYNM_MAGIC, XYNM_VERSION, XYNM_HEADER_BYTES);
        let xycl = empty_header(XYCL_MAGIC, XYCL_VERSION, XYCL_HEADER_BYTES);
        let compiled = pack_trace_compile(&xytc).unwrap();
        let attached = pack_trace_attach(&compiled, &xyta).unwrap();
        let sidecars = pack_trace_sidecars(&attached, &xynm).unwrap();
        let packed_rows = pack_trace_rows(&attached, &xycl).unwrap();
        let mut row_bytes = Vec::new();
        for row in packed_rows {
            row_bytes.extend_from_slice(&row.to_bytes());
        }
        let xyas = splice_annotations(&row_bytes, &sidecars, &[]).unwrap();
        let packed =
            encode_assembled_from_sidecars(&xyas, &empty_chrome_facts(), &sidecars, &[], &[])
                .unwrap();
        let product = encode_product(
            &xytc,
            &xyta,
            &xynm,
            &xycl,
            &[],
            0,
            0.0,
            1.0,
            0.0,
            1.0,
            &empty_chrome_facts(),
            &[],
            &[],
        )
        .unwrap();
        assert_eq!(product, packed);
        assert_eq!(&product[..4], b"XYGS");
    }

    #[test]
    fn product_invalid_polar_is_extras_shape() {
        let xytc = empty_header(XYTC_MAGIC, XYTC_VERSION, XYTC_HEADER_BYTES);
        let xyta = empty_header(XYTA_MAGIC, XYTA_VERSION, XYTA_HEADER_BYTES);
        let xynm = empty_header(XYNM_MAGIC, XYNM_VERSION, XYNM_HEADER_BYTES);
        let xycl = empty_header(XYCL_MAGIC, XYCL_VERSION, XYCL_HEADER_BYTES);
        let error = encode_product(
            &xytc,
            &xyta,
            &xynm,
            &xycl,
            &[],
            0,
            0.0,
            1.0,
            0.0,
            1.0,
            &empty_chrome_facts(),
            &[0u8; 8],
            &[],
        )
        .unwrap_err();
        assert_eq!(error.code, EncodeSidecarsCode::ExtrasShape as i32);
    }

    #[test]
    fn product_unknown_xytc_version_is_compile() {
        let mut xytc = empty_header(XYTC_MAGIC, XYTC_VERSION, XYTC_HEADER_BYTES);
        xytc[4..8].copy_from_slice(&2u32.to_le_bytes());
        let xyta = empty_header(XYTA_MAGIC, XYTA_VERSION, XYTA_HEADER_BYTES);
        let xynm = empty_header(XYNM_MAGIC, XYNM_VERSION, XYNM_HEADER_BYTES);
        let xycl = empty_header(XYCL_MAGIC, XYCL_VERSION, XYCL_HEADER_BYTES);
        let error = encode_product(
            &xytc,
            &xyta,
            &xynm,
            &xycl,
            &[],
            0,
            0.0,
            1.0,
            0.0,
            1.0,
            &empty_chrome_facts(),
            &[],
            &[],
        )
        .unwrap_err();
        assert_eq!(
            error.code,
            PRODUCT_STAGE_COMPILE + crate::scene_trace_compile::TraceCompileCode::Version as i32
        );
    }

    fn xyfs_v2(flags: u32, traces: &[(u16, &str)]) -> Vec<u8> {
        let mut buf = Vec::from(*b"XYFS");
        buf.extend_from_slice(&2u32.to_le_bytes());
        buf.extend_from_slice(&flags.to_le_bytes());
        buf.extend_from_slice(&2u32.to_le_bytes());
        buf.extend_from_slice(&(traces.len() as u32).to_le_bytes());
        buf.extend_from_slice(&[0, 0, 0, 0]);
        buf.extend_from_slice(&0u32.to_le_bytes());
        buf.extend_from_slice(&[1, 0, 0, 0]);
        buf.extend_from_slice(&0u32.to_le_bytes());
        for (trace_flags, kind) in traces {
            buf.extend_from_slice(&trace_flags.to_le_bytes());
            buf.push(kind.len() as u8);
            buf.push(0);
            buf.extend_from_slice(&0u32.to_le_bytes());
            buf.extend_from_slice(kind.as_bytes());
        }
        buf
    }

    fn empty_product_blobs() -> (Vec<u8>, Vec<u8>, Vec<u8>, Vec<u8>, Vec<u8>) {
        (
            empty_header(XYTC_MAGIC, XYTC_VERSION, XYTC_HEADER_BYTES),
            empty_header(XYTA_MAGIC, XYTA_VERSION, XYTA_HEADER_BYTES),
            empty_header(XYNM_MAGIC, XYNM_VERSION, XYNM_HEADER_BYTES),
            empty_header(XYCL_MAGIC, XYCL_VERSION, XYCL_HEADER_BYTES),
            empty_chrome_facts(),
        )
    }

    #[test]
    fn product_empty_xyfs_skips_support_probe() {
        let (xytc, xyta, xynm, xycl, xycf) = empty_product_blobs();
        let encoded = encode_product(
            &xytc,
            &xyta,
            &xynm,
            &xycl,
            &[],
            0,
            0.0,
            1.0,
            0.0,
            1.0,
            &xycf,
            &[],
            &[],
        )
        .unwrap();
        assert_eq!(&encoded[..4], b"XYGS");
    }

    #[test]
    fn product_supported_xyfs_encodes() {
        let (xytc, xyta, xynm, xycl, xycf) = empty_product_blobs();
        let encoded = encode_product(
            &xytc,
            &xyta,
            &xynm,
            &xycl,
            &[],
            0,
            0.0,
            1.0,
            0.0,
            1.0,
            &xycf,
            &[],
            &xyfs_v2(0, &[(0, "scatter")]),
        )
        .unwrap();
        assert_eq!(&encoded[..4], b"XYGS");
    }

    #[test]
    fn product_unsupported_xyfs_is_support_stage() {
        let (xytc, xyta, xynm, xycl, xycf) = empty_product_blobs();
        let error = encode_product(
            &xytc,
            &xyta,
            &xynm,
            &xycl,
            &[],
            0,
            0.0,
            1.0,
            0.0,
            1.0,
            &xycf,
            &[],
            &xyfs_v2(1, &[(1, "stem")]),
        )
        .unwrap_err();
        assert_eq!(error.code, PRODUCT_SUPPORT_UNSUPPORTED);
        let reason = std::str::from_utf8(&error.reason).unwrap();
        assert!(reason.contains("XYG_SCENE_UNSUPPORTED_POLAR"));
    }

    #[test]
    fn product_malformed_xyfs_is_support_envelope() {
        let (xytc, xyta, xynm, xycl, xycf) = empty_product_blobs();
        let error = encode_product(
            &xytc,
            &xyta,
            &xynm,
            &xycl,
            &[],
            0,
            0.0,
            1.0,
            0.0,
            1.0,
            &xycf,
            &[],
            b"XYFS",
        )
        .unwrap_err();
        assert_eq!(error.code, PRODUCT_SUPPORT_ENVELOPE);
        assert!(error.reason.is_empty());
    }
}
