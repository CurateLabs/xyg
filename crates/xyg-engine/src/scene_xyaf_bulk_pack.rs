//! Bulk XYAF v1 annotation pack (M2 Push 3A completion, ABI 324).
//!
//! Hosts marshal annotation observations (kind, text, geometry/style keys).
//! Rust owns kind dispatch, style allowlists, text/geometry validation, CSS
//! color resolve, dash/linecap admit, and concatenated XYAF record output.

use crate::css::color_rgba8;
use crate::kernels::{
    scene_annotation_style_admit, scene_dash_admit, scene_linecap_admit, scene_linecap_code,
    SceneDash, SceneLinecap,
};
use crate::scene_pack_orchestrate::scene_xyaf_annotation_dispatch_plan;
use crate::scene_xyaf_pack::{scene_xyaf_pack, XyafPackInput};

pub const SCENE_XYAF_BULK_PACK_MAX: usize = 1 << 22;
const MAX_ANNOTATIONS: usize = 128;

const XYAF_KIND_TEXT: u8 = 0;
const XYAF_KIND_ARROW: u8 = 1;
const XYAF_KIND_CALLOUT: u8 = 2;
const XYAF_KIND_RULE: u8 = 3;
const XYAF_KIND_BAND: u8 = 4;
const XYAF_KIND_MARKER: u8 = 5;

const FACT_HAS_WRAP: u32 = 1 << 0;
const FACT_HAS_TEXT: u32 = 1 << 1;
const FACT_HAS_DX: u32 = 1 << 3;
const FACT_HAS_DY: u32 = 1 << 4;
const FACT_HAS_X: u32 = 1 << 5;
const FACT_HAS_Y: u32 = 1 << 6;
const FACT_HAS_X0: u32 = 1 << 7;
const FACT_HAS_Y0: u32 = 1 << 8;
const FACT_HAS_X1: u32 = 1 << 9;
const FACT_HAS_Y1: u32 = 1 << 10;
const FACT_HAS_VALUE: u32 = 1 << 11;
const FACT_HAS_START: u32 = 1 << 12;
const FACT_HAS_END: u32 = 1 << 13;
const FACT_HAS_SIZE: u32 = 1 << 14;
const FACT_HAS_AXIS: u32 = 1 << 15;
const FACT_HAS_SYMBOL: u32 = 1 << 16;
const FACT_HAS_ANCHOR: u32 = 1 << 17;
const FACT_HAS_ROTATION: u32 = 1 << 18;

const STYLE_COLOR: u32 = 1 << 0;
const STYLE_OPACITY: u32 = 1 << 1;
const STYLE_WIDTH: u32 = 1 << 2;
const STYLE_DASH: u32 = 1 << 3;
const STYLE_LINECAP: u32 = 1 << 4;
const STYLE_STROKE_COLOR: u32 = 1 << 5;
const STYLE_STROKE_WIDTH: u32 = 1 << 6;
const STYLE_LABEL_COLOR: u32 = 1 << 7;
const STYLE_LABEL_OPACITY: u32 = 1 << 8;
const STYLE_LABEL_BACKGROUND: u32 = 1 << 9;
const STYLE_LABEL_BORDER_COLOR: u32 = 1 << 10;
const STYLE_LABEL_BORDER_WIDTH: u32 = 1 << 11;

const TYPOGRAPHY_KEYS: &[&str] = &[
    "font_family",
    "font_size",
    "font_weight",
    "font_style",
    "fontFamily",
    "fontSize",
    "fontWeight",
    "fontStyle",
];

const SYMBOL_NAMES: [&str; 19] = [
    "circle",
    "square",
    "diamond",
    "triangle",
    "cross",
    "hexagon",
    "pentagon",
    "star",
    "triangle_down",
    "triangle_left",
    "triangle_right",
    "x",
    "point",
    "pixel",
    "thin_diamond",
    "plus_line",
    "x_line",
    "horizontal_line",
    "vertical_line",
];

/// Why bulk XYAF packing failed. Discriminants are negated C-ABI return codes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum XyafBulkError {
    Invalid = 1,
    Output = 2,
    UnsupportedKind = 3,
    UnsupportedStyle = 4,
    Text = 5,
    Numeric = 6,
    ArrowText = 7,
    Dash = 8,
    Linecap = 9,
    Symbol = 10,
    Anchor = 11,
    LabelBorder = 12,
    Axis = 13,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct XyafBulkPackError {
    pub code: XyafBulkError,
    pub index: u32,
}

impl XyafBulkPackError {
    fn new(code: XyafBulkError, index: usize) -> Self {
        Self {
            code,
            index: index as u32,
        }
    }

    pub fn abi_code(self) -> i32 {
        -(self.code as i32)
    }
}

/// One style observation row for bulk XYAF pack.
#[derive(Clone, Debug, Default)]
pub struct XyafBulkStyleObs<'a> {
    pub color: Option<&'a str>,
    pub stroke_color: Option<&'a str>,
    pub label_color: Option<&'a str>,
    pub label_background: Option<&'a str>,
    pub label_border_color: Option<&'a str>,
    pub dash: Option<&'a str>,
    pub linecap: Option<&'a str>,
    pub opacity: Option<f64>,
    pub width: Option<f64>,
    pub stroke_width: Option<f64>,
    pub label_opacity: Option<f64>,
    pub label_border_width: Option<f64>,
    pub rotation: Option<f64>,
    pub extra_keys: &'a [String],
}

/// One annotation observation row for bulk XYAF pack.
#[derive(Clone, Debug)]
pub struct XyafBulkAnnotationObs<'a> {
    pub kind: &'a str,
    pub text: Option<&'a str>,
    pub x: Option<f64>,
    pub y: Option<f64>,
    pub x0: Option<f64>,
    pub y0: Option<f64>,
    pub x1: Option<f64>,
    pub y1: Option<f64>,
    pub value: Option<f64>,
    pub start: Option<f64>,
    pub end: Option<f64>,
    pub dx: Option<f64>,
    pub dy: Option<f64>,
    pub size: Option<f64>,
    pub wrap: Option<f64>,
    pub rotation: Option<f64>,
    pub anchor: Option<&'a str>,
    pub axis: Option<&'a str>,
    pub symbol: Option<&'a str>,
    pub record_index: Option<u32>,
    pub style: XyafBulkStyleObs<'a>,
}

fn kind_code(kind: &str) -> Option<u8> {
    match kind {
        "text" => Some(XYAF_KIND_TEXT),
        "arrow" => Some(XYAF_KIND_ARROW),
        "callout" => Some(XYAF_KIND_CALLOUT),
        "rule" => Some(XYAF_KIND_RULE),
        "band" => Some(XYAF_KIND_BAND),
        "marker" => Some(XYAF_KIND_MARKER),
        _ => None,
    }
}

fn is_typography_key(key: &str) -> bool {
    TYPOGRAPHY_KEYS.contains(&key)
}

fn take_num_at(value: Option<f64>, index: usize) -> Result<f64, XyafBulkPackError> {
    match value {
        Some(v) if v.is_finite() => Ok(v),
        _ => Err(XyafBulkPackError::new(XyafBulkError::Numeric, index)),
    }
}

fn annotation_color(css: &str, index: usize) -> Result<[u8; 4], XyafBulkPackError> {
    if css.trim().is_empty() {
        return Err(XyafBulkPackError::new(XyafBulkError::Numeric, index));
    }
    Ok(color_rgba8(css, 1.0))
}

fn symbol_code(name: &str, index: usize) -> Result<u8, XyafBulkPackError> {
    for (code, candidate) in SYMBOL_NAMES.iter().enumerate() {
        if name == *candidate {
            return Ok(code as u8);
        }
    }
    Err(XyafBulkPackError::new(XyafBulkError::Symbol, index))
}

fn anchor_code(name: &str, index: usize) -> Result<u8, XyafBulkPackError> {
    match name {
        "start" => Ok(0),
        "middle" => Ok(1),
        "end" => Ok(2),
        _ => Err(XyafBulkPackError::new(XyafBulkError::Anchor, index)),
    }
}

fn parse_dash_text(text: &str) -> Result<Option<Vec<f32>>, XyafBulkPackError> {
    match scene_dash_admit(text, &[], false) {
        Some(SceneDash::Solid) => Ok(None),
        Some(SceneDash::Pattern(values)) => Ok(Some(values.into_iter().map(|v| v as f32).collect())),
        None => Err(XyafBulkPackError::new(XyafBulkError::Dash, 0)),
    }
}

fn parse_linecap_text(text: &str) -> Result<Option<u8>, XyafBulkPackError> {
    match scene_linecap_admit(text) {
        Some(SceneLinecap::Round) => Ok(None),
        Some(cap) => Ok(Some(scene_linecap_code(cap))),
        None => Err(XyafBulkPackError::new(XyafBulkError::Linecap, 0)),
    }
}

fn pack_one(index: usize, obs: &XyafBulkAnnotationObs<'_>) -> Result<Vec<u8>, XyafBulkPackError> {
    let Some(kind_code) = kind_code(obs.kind) else {
        return Err(XyafBulkPackError::new(XyafBulkError::UnsupportedKind, index));
    };
    let kind = obs.kind;
    let mut rotation = obs.rotation;
    if matches!(kind, "text" | "marker") && rotation.is_none() {
        rotation = obs.style.rotation;
    }
    let authored_wrap = matches!(kind, "text" | "callout") && obs.wrap.is_some();
    let layout_text = kind == "text"
        && (obs.dx.is_some()
            || obs.dy.is_some()
            || obs.anchor.is_some()
            || rotation.is_some());
    let mut dispatch = crate::scene_pack_orchestrate::XyafAnnotationDispatchPlan {
        wrapped: 0,
        pack_rule_dash: 0,
        pack_rule_linecap: 0,
        pack_axis: 0,
        pack_symbol: 0,
    };
    if scene_xyaf_annotation_dispatch_plan(
        kind,
        i32::from(authored_wrap),
        i32::from(layout_text),
        &mut dispatch,
    ) == 0
    {
        return Err(XyafBulkPackError::new(XyafBulkError::Invalid, index));
    }
    let wrapped = dispatch.wrapped != 0;
    let labelled = obs
        .text
        .map(|text| !text.is_empty())
        .unwrap_or(false);
    if kind == "arrow" && labelled {
        return Err(XyafBulkPackError::new(XyafBulkError::ArrowText, index));
    }
    let text_bytes: &[u8] = if labelled {
        let text = obs.text.unwrap_or("");
        if text.contains('\0')
            || (wrapped && text.contains('\r'))
            || !text.is_empty() && text.len() > 4096
        {
            return Err(XyafBulkPackError::new(XyafBulkError::Text, index));
        }
        text.as_bytes()
    } else if matches!(kind, "text" | "callout") {
        return Err(XyafBulkPackError::new(XyafBulkError::Text, index));
    } else {
        &[]
    };
    for key in obs.style.extra_keys {
        if key == "markup" || is_typography_key(key) {
            continue;
        }
        if matches!(kind, "text" | "marker") && key == "rotation" {
            continue;
        }
        if scene_annotation_style_admit(kind, wrapped, labelled, key) {
            continue;
        }
        return Err(XyafBulkPackError::new(XyafBulkError::UnsupportedStyle, index));
    }
    let mut nums = [f64::NAN; 18];
    let mut facts = 0u32;
    let mut style_bits = 0u32;
    if labelled {
        facts |= FACT_HAS_TEXT;
    }
    if wrapped {
        facts |= FACT_HAS_WRAP;
        nums[8] = obs.wrap.unwrap_or(0.0);
    }
    let required: &[(&str, usize, u32)] = if wrapped {
        &[("x", 0, FACT_HAS_X), ("y", 1, FACT_HAS_Y)]
    } else {
        match kind {
            "arrow" => &[
                ("x0", 2, FACT_HAS_X0),
                ("y0", 3, FACT_HAS_Y0),
                ("x1", 4, FACT_HAS_X1),
                ("y1", 5, FACT_HAS_Y1),
            ],
            "callout" => &[("x", 0, FACT_HAS_X), ("y", 1, FACT_HAS_Y)],
            "text" => &[("x", 0, FACT_HAS_X), ("y", 1, FACT_HAS_Y)],
            "rule" => &[("value", 9, FACT_HAS_VALUE)],
            "band" => &[("start", 10, FACT_HAS_START), ("end", 11, FACT_HAS_END)],
            "marker" => &[("x", 0, FACT_HAS_X), ("y", 1, FACT_HAS_Y)],
            _ => &[],
        }
    };
    for (key, slot, flag) in required {
        let value = match *key {
            "x" => take_num_at(obs.x, index)?,
            "y" => take_num_at(obs.y, index)?,
            "x0" => take_num_at(obs.x0, index)?,
            "y0" => take_num_at(obs.y0, index)?,
            "x1" => take_num_at(obs.x1, index)?,
            "y1" => take_num_at(obs.y1, index)?,
            "value" => take_num_at(obs.value, index)?,
            "start" => take_num_at(obs.start, index)?,
            "end" => take_num_at(obs.end, index)?,
            _ => return Err(XyafBulkPackError::new(XyafBulkError::Invalid, index)),
        };
        nums[*slot] = value;
        facts |= flag;
    }
    if let Some(value) = obs.dx {
        nums[6] = take_num_at(Some(value), index)?;
        facts |= FACT_HAS_DX;
    }
    if let Some(value) = obs.dy {
        nums[7] = take_num_at(Some(value), index)?;
        facts |= FACT_HAS_DY;
    }
    if let Some(value) = obs.size {
        nums[12] = take_num_at(Some(value), index)?;
        facts |= FACT_HAS_SIZE;
    }
    if kind == "text" {
        if let Some(value) = rotation {
            nums[15] = take_num_at(Some(value), index)?;
            facts |= FACT_HAS_ROTATION;
            if !nums[15].is_finite() {
                return Err(XyafBulkPackError::new(XyafBulkError::Numeric, index));
            }
        }
    }
    if kind == "marker" {
        if let Some(value) = rotation {
            nums[8] = take_num_at(Some(value), index)?;
            facts |= FACT_HAS_ROTATION;
            if !nums[8].is_finite() {
                return Err(XyafBulkPackError::new(XyafBulkError::Numeric, index));
            }
        }
    }
    let mut axis_code = 0u8;
    if matches!(kind, "rule" | "band") {
        let axis_name = obs.axis.unwrap_or("");
        axis_code = match axis_name {
            "x" => 1,
            "y" => 2,
            _ => return Err(XyafBulkPackError::new(XyafBulkError::Axis, index)),
        };
        facts |= FACT_HAS_AXIS;
    }
    let mut symbol = 0u8;
    if kind == "marker" {
        let symbol_name = obs.symbol.unwrap_or("circle");
        symbol = symbol_code(symbol_name, index)?;
        if obs.symbol.is_some() {
            facts |= FACT_HAS_SYMBOL;
        }
        if obs.size.is_some() && (!nums[12].is_finite() || nums[12] <= 0.0) {
            return Err(XyafBulkPackError::new(XyafBulkError::Numeric, index));
        }
    }
    let mut anchor = 255u8;
    if obs.anchor.is_some() || kind == "callout" || wrapped {
        let anchor_name = obs.anchor.unwrap_or("start");
        anchor = anchor_code(anchor_name, index)?;
        facts |= FACT_HAS_ANCHOR;
    }
    if let Some(value) = obs.style.opacity {
        nums[13] = take_num_at(Some(value), index)?;
        style_bits |= STYLE_OPACITY;
        if !nums[13].is_finite() || !(0.0..=1.0).contains(&nums[13]) {
            return Err(XyafBulkPackError::new(XyafBulkError::Numeric, index));
        }
    }
    if let Some(value) = obs.style.width {
        nums[14] = take_num_at(Some(value), index)?;
        style_bits |= STYLE_WIDTH;
        if matches!(kind, "arrow" | "callout") && (!nums[14].is_finite() || nums[14] <= 0.0) {
            return Err(XyafBulkPackError::new(XyafBulkError::Numeric, index));
        }
        if kind == "rule" && (!nums[14].is_finite() || nums[14] <= 0.0) {
            return Err(XyafBulkPackError::new(XyafBulkError::Numeric, index));
        }
    }
    if let Some(value) = obs.style.stroke_width {
        nums[15] = take_num_at(Some(value), index)?;
        style_bits |= STYLE_STROKE_WIDTH;
        if !nums[15].is_finite() || nums[15] < 0.0 {
            return Err(XyafBulkPackError::new(XyafBulkError::Numeric, index));
        }
    }
    if let Some(value) = obs.style.label_opacity {
        nums[16] = take_num_at(Some(value), index)?;
        style_bits |= STYLE_LABEL_OPACITY;
        if !nums[16].is_finite() || !(0.0..=1.0).contains(&nums[16]) {
            return Err(XyafBulkPackError::new(XyafBulkError::Numeric, index));
        }
    }
    if let Some(value) = obs.style.label_border_width {
        nums[17] = take_num_at(Some(value), index)?;
        style_bits |= STYLE_LABEL_BORDER_WIDTH;
        if !nums[17].is_finite() || nums[17] <= 0.0 {
            return Err(XyafBulkPackError::new(XyafBulkError::Numeric, index));
        }
    }
    let mut color = [0u8; 4];
    let mut stroke = [0u8; 4];
    let mut label_color = [0u8; 4];
    let mut label_fill = [0u8; 4];
    let mut label_border = [0u8; 4];
    if let Some(css) = obs.style.color {
        color = annotation_color(css, index)?;
        style_bits |= STYLE_COLOR;
    }
    if let Some(css) = obs.style.stroke_color {
        stroke = annotation_color(css, index)?;
        style_bits |= STYLE_STROKE_COLOR;
    }
    if let Some(css) = obs.style.label_color {
        label_color = annotation_color(css, index)?;
        style_bits |= STYLE_LABEL_COLOR;
    }
    if let Some(css) = obs.style.label_background {
        label_fill = annotation_color(css, index)?;
        style_bits |= STYLE_LABEL_BACKGROUND;
    }
    if let Some(css) = obs.style.label_border_color {
        label_border = annotation_color(css, index)?;
        style_bits |= STYLE_LABEL_BORDER_COLOR;
    }
    let border_color_present = obs.style.label_border_color.is_some();
    let border_width_present = obs.style.label_border_width.is_some();
    if border_color_present != border_width_present {
        return Err(XyafBulkPackError::new(XyafBulkError::LabelBorder, index));
    }
    let mut parsed_dash: Option<Vec<f32>> = None;
    let mut parsed_cap: Option<u8> = None;
    if dispatch.pack_rule_dash != 0 || dispatch.pack_rule_linecap != 0 {
        if let Some(text) = obs.style.dash {
            parsed_dash = parse_dash_text(text).map_err(|mut err| {
                err.index = index as u32;
                err
            })?;
            if parsed_dash.is_some() {
                style_bits |= STYLE_DASH;
            }
        }
        if let Some(text) = obs.style.linecap {
            parsed_cap = parse_linecap_text(text).map_err(|mut err| {
                err.index = index as u32;
                err
            })?;
            if parsed_cap.is_some() {
                style_bits |= STYLE_LINECAP;
            }
        }
    }
    let mut dash = [0.0f32; 8];
    let dash_count = parsed_dash.as_ref().map(|values| values.len()).unwrap_or(0);
    if let Some(values) = parsed_dash {
        for (slot, value) in values.into_iter().enumerate() {
            dash[slot] = value;
        }
    }
    let linecap = parsed_cap.unwrap_or(255);
    let record_index = obs.record_index.unwrap_or(index as u32);
    scene_xyaf_pack(&XyafPackInput {
        index: record_index,
        kind_code,
        axis_code,
        symbol,
        anchor,
        facts,
        style_bits,
        linecap,
        dash_count: dash_count as u8,
        nums,
        color,
        stroke,
        label_color,
        label_fill,
        label_border,
        dash,
        text: text_bytes,
    })
    .map_err(|_| XyafBulkPackError::new(XyafBulkError::Invalid, index))
}

/// Pack all annotation observations into concatenated XYAF v1 records.
pub fn scene_xyaf_bulk_pack(annotations: &[XyafBulkAnnotationObs<'_>]) -> Result<Vec<u8>, XyafBulkPackError> {
    if annotations.len() > MAX_ANNOTATIONS {
        return Err(XyafBulkPackError::new(XyafBulkError::Invalid, 0));
    }
    let mut out = Vec::new();
    for (index, obs) in annotations.iter().enumerate() {
        let packed = pack_one(index, obs)?;
        if out.len().saturating_add(packed.len()) > SCENE_XYAF_BULK_PACK_MAX {
            return Err(XyafBulkPackError::new(XyafBulkError::Output, index));
        }
        out.extend_from_slice(&packed);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn text_obs<'a>(text: &'a str, x: f64, y: f64, color: &'a str) -> XyafBulkAnnotationObs<'a> {
        XyafBulkAnnotationObs {
            kind: "text",
            text: Some(text),
            x: Some(x),
            y: Some(y),
            x0: None,
            y0: None,
            x1: None,
            y1: None,
            value: None,
            start: None,
            end: None,
            dx: None,
            dy: None,
            size: None,
            wrap: None,
            rotation: None,
            anchor: None,
            axis: None,
            symbol: None,
            record_index: None,
            style: XyafBulkStyleObs {
                color: Some(color),
                ..Default::default()
            },
        }
    }

    #[test]
    fn packs_text_annotation() {
        let packed = scene_xyaf_bulk_pack(&[text_obs("hello", 0.5, 0.25, "#667085")]).unwrap();
        assert_eq!(&packed[..4], b"XYAF");
        assert_eq!(&packed[232..], b"hello");
    }

    #[test]
    fn rejects_deferred_kind() {
        let obs = XyafBulkAnnotationObs {
            kind: "polygon",
            text: None,
            x: None,
            y: None,
            x0: None,
            y0: None,
            x1: None,
            y1: None,
            value: None,
            start: None,
            end: None,
            dx: None,
            dy: None,
            size: None,
            wrap: None,
            rotation: None,
            anchor: None,
            axis: None,
            symbol: None,
            record_index: None,
            style: XyafBulkStyleObs::default(),
        };
        assert_eq!(
            scene_xyaf_bulk_pack(&[obs]).unwrap_err().code,
            XyafBulkError::UnsupportedKind
        );
    }
}
