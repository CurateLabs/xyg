//! Versioned, bounded canonical scene records and deterministic SVG emission.
//!
//! This first vertical slice owns the built-in scatter-mark scene. Hosts still
//! coerce author input and resolve paint channels, but marker geometry,
//! stroke-inclusive sizing, validation, bounds, and SVG construction live here.

use crate::css;
use crate::svg::push_num;
use std::fmt::Write;

pub const SCENE_VERSION: u32 = 3;
pub const MAX_SCENE_MARKS: usize = 2_000_000;
pub const MAX_AXIS_TICKS: usize = 200;
pub const MAX_SCENE_STYLES: usize = 65_536;
pub const SCENE_BATCH_HEADER_BYTES: usize = 160;
pub const SCENE_STYLE_RECORD_BYTES: usize = 16;
pub const SCENE_BATCH_RECORD_BYTES: usize = 56;

#[derive(Clone, Debug, PartialEq)]
pub struct AxisTicks {
    pub ticks: Vec<f64>,
    pub labeled: Vec<f64>,
    pub step: f64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ScaleKind {
    Linear,
    Log,
    SymLog,
}

#[derive(Clone, Copy, Debug)]
pub struct AxisScale {
    kind: ScaleKind,
    px0: f64,
    coord_lo: f64,
    coord_span: f64,
    px_delta: f64,
    constant: f64,
    mask_nonpositive: bool,
}

impl AxisScale {
    pub fn new(
        kind: ScaleKind,
        lo: f64,
        hi: f64,
        px0: f64,
        px1: f64,
        constant: f64,
        mask_nonpositive: bool,
    ) -> Result<Self, SceneError> {
        if [lo, hi, px0, px1, constant]
            .iter()
            .any(|value| !value.is_finite())
            || constant <= 0.0
        {
            return Err(SceneError::NonFinite);
        }
        let mut scale = Self {
            kind,
            px0,
            coord_lo: 0.0,
            coord_span: 1.0,
            px_delta: px1 - px0,
            constant,
            mask_nonpositive,
        };
        let coord_lo = scale.coord(lo);
        let coord_hi = scale.coord(hi);
        if !coord_lo.is_finite() || !coord_hi.is_finite() {
            return Err(SceneError::NonFinite);
        }
        scale.coord_lo = coord_lo;
        scale.coord_span = if coord_hi == coord_lo {
            1.0
        } else {
            coord_hi - coord_lo
        };
        Ok(scale)
    }

    pub fn coord(self, value: f64) -> f64 {
        if value.is_nan() {
            return f64::NAN;
        }
        match self.kind {
            ScaleKind::Linear => value,
            ScaleKind::Log if value > 0.0 => value.log10(),
            ScaleKind::Log if self.mask_nonpositive => f64::NAN,
            ScaleKind::Log => 1e-300_f64.log10(),
            ScaleKind::SymLog => value.signum() * (value.abs() / self.constant).ln_1p(),
        }
    }

    pub fn value(self, coord: f64) -> f64 {
        match self.kind {
            ScaleKind::Linear => coord,
            ScaleKind::Log => 10_f64.powf(coord),
            ScaleKind::SymLog => coord.signum() * self.constant * coord.abs().exp_m1(),
        }
    }

    pub fn pixel(self, value: f64) -> f64 {
        self.px0 + (self.coord(value) - self.coord_lo) / self.coord_span * self.px_delta
    }
}

pub fn linear_ticks(lo: f64, hi: f64, target: usize) -> Result<AxisTicks, SceneError> {
    if !lo.is_finite() || !hi.is_finite() || target == 0 || target > MAX_AXIS_TICKS {
        return Err(SceneError::NonFinite);
    }
    let (a, b) = if lo <= hi { (lo, hi) } else { (hi, lo) };
    if a == b {
        return Ok(AxisTicks {
            ticks: vec![a],
            labeled: vec![a],
            step: 1.0,
        });
    }
    let rough = (b - a) / target as f64;
    let magnitude = 10_f64.powf(rough.abs().log10().floor());
    let step = [1.0, 2.0, 2.5, 5.0, 10.0]
        .into_iter()
        .map(|m| m * magnitude)
        .find(|candidate| rough <= candidate * (1.0 + 1e-12))
        .unwrap_or(10.0 * magnitude);
    let mut value = (a / step).ceil() * step;
    let mut ticks = Vec::with_capacity(target.saturating_add(2).min(MAX_AXIS_TICKS));
    while value <= b + step * 1e-9 && ticks.len() < MAX_AXIS_TICKS {
        ticks.push(if value.abs() < step * 1e-9 {
            0.0
        } else {
            value
        });
        value += step;
    }
    Ok(AxisTicks {
        labeled: ticks.clone(),
        ticks,
        step,
    })
}

pub fn log_ticks(lo: f64, hi: f64, target: usize) -> Result<AxisTicks, SceneError> {
    if !lo.is_finite()
        || !hi.is_finite()
        || lo <= 0.0
        || hi <= 0.0
        || target == 0
        || target > MAX_AXIS_TICKS
    {
        return Err(SceneError::NonFinite);
    }
    let (a, b) = if lo <= hi { (lo, hi) } else { (hi, lo) };
    let e0 = a.log10().floor() as i32;
    let e1 = b.log10().ceil() as i32;
    let multipliers: &[f64] = if (e1 - e0).max(1) <= (target as i32).max(2) {
        &[1.0, 2.0, 5.0]
    } else {
        &[1.0]
    };
    let label_every = (((e1 - e0 + 1) as f64 / target as f64).ceil() as i32).max(1);
    let mut ticks = Vec::new();
    let mut labeled = Vec::new();
    'outer: for exponent in e0..=e1 {
        let base = 10_f64.powi(exponent);
        for multiplier in multipliers {
            let value = multiplier * base;
            if value >= a * (1.0 - 1e-12) && value <= b * (1.0 + 1e-12) {
                ticks.push(value);
                if *multiplier == 1.0 && (exponent - e0) % label_every == 0 {
                    labeled.push(value);
                }
            }
            if ticks.len() >= MAX_AXIS_TICKS {
                break 'outer;
            }
        }
    }
    if labeled.is_empty() {
        labeled.clone_from(&ticks);
    }
    Ok(AxisTicks {
        ticks,
        labeled,
        step: 1.0,
    })
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum ScatterSymbol {
    Circle = 0,
    Square = 1,
    Diamond = 2,
    Triangle = 3,
    Cross = 4,
    Hexagon = 5,
    Pentagon = 6,
    Star = 7,
    TriangleDown = 8,
    TriangleLeft = 9,
    TriangleRight = 10,
    Point = 11,
    Pixel = 12,
    ThinDiamond = 13,
    PlusLine = 14,
    XLine = 15,
    HorizontalLine = 16,
    VerticalLine = 17,
    X = 18,
}

impl ScatterSymbol {
    fn from_code(value: u8) -> Self {
        match value {
            1 => Self::Square,
            2 => Self::Diamond,
            3 => Self::Triangle,
            4 => Self::Cross,
            5 => Self::Hexagon,
            6 => Self::Pentagon,
            7 => Self::Star,
            8 => Self::TriangleDown,
            9 => Self::TriangleLeft,
            10 => Self::TriangleRight,
            11 => Self::Point,
            12 => Self::Pixel,
            13 => Self::ThinDiamond,
            14 => Self::PlusLine,
            15 => Self::XLine,
            16 => Self::HorizontalLine,
            17 => Self::VerticalLine,
            18 => Self::X,
            _ => Self::Circle,
        }
    }

    fn is_line(self) -> bool {
        matches!(
            self,
            Self::PlusLine | Self::XLine | Self::HorizontalLine | Self::VerticalLine
        )
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct MarkerGeometry {
    radius: f64,
    stroke_width: f64,
    extent_x: f64,
    extent_y: f64,
}

impl MarkerGeometry {
    /// Canonical built-in marker geometry shared by Scene v1 SVG and v3
    /// clipping. `diameter` is the authored outer size. Line-only symbols get
    /// the historical implicit 1px stroke when the authored stroke is zero.
    fn new(symbol: ScatterSymbol, diameter: f64, authored_stroke: f64) -> Self {
        let stroke_width = if symbol.is_line() && authored_stroke <= 0.0 {
            1.0
        } else {
            authored_stroke
        };
        let radius = (diameter / 2.0 - stroke_width / 2.0).max(0.0);
        let (path_x, path_y) = match symbol {
            ScatterSymbol::Diamond => {
                let extent = std::f64::consts::SQRT_2 * radius;
                (extent, extent)
            }
            ScatterSymbol::ThinDiamond => (
                std::f64::consts::SQRT_2 * radius * 0.6,
                std::f64::consts::SQRT_2 * radius,
            ),
            ScatterSymbol::XLine => {
                let extent = 0.707 * radius;
                (extent, extent)
            }
            ScatterSymbol::HorizontalLine => (radius, 0.0),
            ScatterSymbol::VerticalLine => (0.0, radius),
            _ => (radius, radius),
        };
        let stroke_extent = stroke_width / 2.0;
        Self {
            radius,
            stroke_width,
            extent_x: path_x + stroke_extent,
            extent_y: path_y + stroke_extent,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SceneError {
    Length,
    Limit,
    NonFinite,
    NegativeSize,
    InvalidPaint,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PlotLayout {
    pub viewport_width: f64,
    pub viewport_height: f64,
    pub left: f64,
    pub top: f64,
    pub right: f64,
    pub bottom: f64,
}

impl PlotLayout {
    pub fn new(
        viewport_width: f64,
        viewport_height: f64,
        margin_left: f64,
        margin_right: f64,
        margin_top: f64,
        margin_bottom: f64,
    ) -> Result<Self, SceneError> {
        if [
            viewport_width,
            viewport_height,
            margin_left,
            margin_right,
            margin_top,
            margin_bottom,
        ]
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0)
            || viewport_width <= margin_left + margin_right
            || viewport_height <= margin_top + margin_bottom
        {
            return Err(SceneError::NonFinite);
        }
        Ok(Self {
            viewport_width,
            viewport_height,
            left: margin_left,
            top: margin_top,
            right: viewport_width - margin_right,
            bottom: viewport_height - margin_bottom,
        })
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum SceneRecordKind {
    Scatter = 0,
    Polyline = 1,
    Rect = 2,
}

impl SceneRecordKind {
    fn from_code(value: u8) -> Result<Self, SceneError> {
        match value {
            0 => Ok(Self::Scatter),
            1 => Ok(Self::Polyline),
            2 => Ok(Self::Rect),
            _ => Err(SceneError::Length),
        }
    }
}

pub struct SceneBatch<'a> {
    layout: PlotLayout,
    x_axis_id: u64,
    y_axis_id: u64,
    x_scale: AxisScale,
    y_scale: AxisScale,
    kinds: &'a [u8],
    stable_ids: &'a [u64],
    style_refs: &'a [u32],
    fill_rgba: &'a [u8],
    stroke_rgba: &'a [u8],
    stroke_width: &'a [f64],
    diameter: &'a [f64],
    symbols: &'a [u8],
    x0: &'a [f64],
    y0: &'a [f64],
    x1: &'a [f64],
    y1: &'a [f64],
}

impl<'a> SceneBatch<'a> {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        layout: PlotLayout,
        x_axis_id: u64,
        y_axis_id: u64,
        x_scale: AxisScale,
        y_scale: AxisScale,
        kinds: &'a [u8],
        stable_ids: &'a [u64],
        style_refs: &'a [u32],
        fill_rgba: &'a [u8],
        stroke_rgba: &'a [u8],
        stroke_width: &'a [f64],
        diameter: &'a [f64],
        symbols: &'a [u8],
        x0: &'a [f64],
        y0: &'a [f64],
        x1: &'a [f64],
        y1: &'a [f64],
    ) -> Result<Self, SceneError> {
        let len = kinds.len();
        if len > MAX_SCENE_MARKS {
            return Err(SceneError::Limit);
        }
        let style_count = stroke_width.len();
        if style_count > MAX_SCENE_STYLES
            || fill_rgba.len() != style_count.saturating_mul(4)
            || stroke_rgba.len() != style_count.saturating_mul(4)
        {
            return Err(SceneError::Limit);
        }
        if [
            stable_ids.len(),
            style_refs.len(),
            diameter.len(),
            symbols.len(),
            x0.len(),
            y0.len(),
            x1.len(),
            y1.len(),
        ]
        .into_iter()
        .any(|value| value != len)
            || kinds
                .iter()
                .any(|kind| SceneRecordKind::from_code(*kind).is_err())
        {
            return Err(SceneError::Length);
        }
        for (index, kind) in kinds.iter().enumerate() {
            let kind = SceneRecordKind::from_code(*kind)?;
            if style_refs[index] as usize >= style_count
                || (kind == SceneRecordKind::Scatter && symbols[index] > ScatterSymbol::X as u8)
                || (kind != SceneRecordKind::Scatter
                    && (diameter[index] != 0.0 || symbols[index] != 0))
            {
                return Err(SceneError::Length);
            }
        }
        if kinds.iter().enumerate().any(|(index, kind)| {
            !x0[index].is_finite()
                || !y0[index].is_finite()
                || (SceneRecordKind::from_code(*kind) == Ok(SceneRecordKind::Rect)
                    && (!x1[index].is_finite() || !y1[index].is_finite()))
        }) || diameter
            .iter()
            .chain(stroke_width)
            .any(|value| !value.is_finite() || *value < 0.0)
        {
            return Err(SceneError::NonFinite);
        }
        Ok(Self {
            layout,
            x_axis_id,
            y_axis_id,
            x_scale,
            y_scale,
            kinds,
            stable_ids,
            style_refs,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            diameter,
            symbols,
            x0,
            y0,
            x1,
            y1,
        })
    }

    pub fn encode(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(
            SCENE_BATCH_HEADER_BYTES
                + self.stroke_width.len() * SCENE_STYLE_RECORD_BYTES
                + self.kinds.len() * SCENE_BATCH_RECORD_BYTES,
        );
        out.extend_from_slice(b"XYGS");
        out.extend_from_slice(&SCENE_VERSION.to_le_bytes());
        out.extend_from_slice(&(SCENE_BATCH_HEADER_BYTES as u32).to_le_bytes());
        out.extend_from_slice(&(SCENE_BATCH_RECORD_BYTES as u32).to_le_bytes());
        out.extend_from_slice(&(self.kinds.len() as u64).to_le_bytes());
        out.extend_from_slice(&(self.stroke_width.len() as u64).to_le_bytes());
        for value in [
            self.layout.viewport_width,
            self.layout.viewport_height,
            self.layout.left,
            self.layout.top,
            self.layout.right,
            self.layout.bottom,
        ] {
            out.extend_from_slice(&value.to_le_bytes());
        }
        out.extend_from_slice(&self.x_axis_id.to_le_bytes());
        out.extend_from_slice(&self.y_axis_id.to_le_bytes());
        // AxisScene records: kind/mask, transformed domain, and symlog constant.
        out.push(self.x_scale.kind as u8);
        out.push(u8::from(self.x_scale.mask_nonpositive));
        out.extend_from_slice(&[0; 6]);
        out.push(self.y_scale.kind as u8);
        out.push(u8::from(self.y_scale.mask_nonpositive));
        out.extend_from_slice(&[0; 6]);
        out.extend_from_slice(&self.x_scale.coord_lo.to_le_bytes());
        out.extend_from_slice(&(self.x_scale.coord_lo + self.x_scale.coord_span).to_le_bytes());
        out.extend_from_slice(&self.y_scale.coord_lo.to_le_bytes());
        out.extend_from_slice(&(self.y_scale.coord_lo + self.y_scale.coord_span).to_le_bytes());
        out.extend_from_slice(&self.x_scale.constant.to_le_bytes());
        out.extend_from_slice(&self.y_scale.constant.to_le_bytes());
        debug_assert_eq!(out.len(), SCENE_BATCH_HEADER_BYTES);

        for index in 0..self.stroke_width.len() {
            out.extend_from_slice(&self.fill_rgba[index * 4..index * 4 + 4]);
            out.extend_from_slice(&self.stroke_rgba[index * 4..index * 4 + 4]);
            out.extend_from_slice(&self.stroke_width[index].to_le_bytes());
        }

        for index in 0..self.kinds.len() {
            let kind = SceneRecordKind::from_code(self.kinds[index]).expect("validated kind");
            let mapped = match kind {
                SceneRecordKind::Scatter | SceneRecordKind::Polyline => [
                    self.x_scale.pixel(self.x0[index]),
                    self.y_scale.pixel(self.y0[index]),
                    0.0,
                    0.0,
                ],
                SceneRecordKind::Rect => [
                    self.x_scale.pixel(self.x0[index]),
                    self.y_scale.pixel(self.y0[index]),
                    self.x_scale.pixel(self.x1[index]),
                    self.y_scale.pixel(self.y1[index]),
                ],
            };
            let visible = mapped.iter().all(|value| value.is_finite())
                && match kind {
                    SceneRecordKind::Polyline => true,
                    SceneRecordKind::Scatter => {
                        let style = self.style_refs[index] as usize;
                        let geometry = MarkerGeometry::new(
                            ScatterSymbol::from_code(self.symbols[index]),
                            self.diameter[index],
                            self.stroke_width[style],
                        );
                        mapped[0] + geometry.extent_x >= self.layout.left
                            && mapped[0] - geometry.extent_x <= self.layout.right
                            && mapped[1] + geometry.extent_y >= self.layout.top
                            && mapped[1] - geometry.extent_y <= self.layout.bottom
                    }
                    SceneRecordKind::Rect => {
                        mapped[0].min(mapped[2]) <= self.layout.right
                            && mapped[0].max(mapped[2]) >= self.layout.left
                            && mapped[1].min(mapped[3]) <= self.layout.bottom
                            && mapped[1].max(mapped[3]) >= self.layout.top
                    }
                };
            out.push(kind as u8);
            out.push(u8::from(visible));
            out.push(self.symbols[index]);
            out.push(0);
            out.extend_from_slice(&self.style_refs[index].to_le_bytes());
            out.extend_from_slice(&self.stable_ids[index].to_le_bytes());
            let record_coordinates = if !visible {
                [0.0; 4]
            } else {
                match kind {
                    SceneRecordKind::Scatter | SceneRecordKind::Polyline => {
                        [mapped[0], mapped[1], 0.0, 0.0]
                    }
                    SceneRecordKind::Rect => [
                        mapped[0].min(mapped[2]),
                        mapped[1].min(mapped[3]),
                        mapped[0].max(mapped[2]),
                        mapped[1].max(mapped[3]),
                    ],
                }
            };
            for value in record_coordinates {
                out.extend_from_slice(&value.to_le_bytes());
            }
            out.extend_from_slice(&self.diameter[index].to_le_bytes());
        }
        out
    }
}

#[derive(Clone, Copy)]
struct EncodedStyle {
    fill: [u8; 4],
    stroke: [u8; 4],
    stroke_width: f64,
}

#[derive(Clone, Copy)]
struct EncodedRecord {
    kind: SceneRecordKind,
    visible: bool,
    symbol: u8,
    style_ref: usize,
    stable_id: u64,
    coordinates: [f64; 4],
    diameter: f64,
}

/// Validated, owned Scene v3 document consumed identically by vector and
/// raster export. Hosts never reinterpret record geometry after encoding.
pub struct SceneDocument {
    layout: PlotLayout,
    styles: Vec<EncodedStyle>,
    records: Vec<EncodedRecord>,
}

impl SceneDocument {
    pub fn decode(bytes: &[u8]) -> Result<Self, SceneError> {
        if bytes.len() < SCENE_BATCH_HEADER_BYTES || &bytes[..4] != b"XYGS" {
            return Err(SceneError::Length);
        }
        let u32_at = |offset| {
            u32::from_le_bytes(
                bytes[offset..offset + 4]
                    .try_into()
                    .expect("bounded header"),
            )
        };
        let u64_at = |offset| {
            u64::from_le_bytes(
                bytes[offset..offset + 8]
                    .try_into()
                    .expect("bounded header"),
            )
        };
        let f64_at = |offset| {
            f64::from_le_bytes(
                bytes[offset..offset + 8]
                    .try_into()
                    .expect("bounded header"),
            )
        };
        if u32_at(4) != SCENE_VERSION
            || u32_at(8) as usize != SCENE_BATCH_HEADER_BYTES
            || u32_at(12) as usize != SCENE_BATCH_RECORD_BYTES
        {
            return Err(SceneError::Length);
        }
        let record_count = usize::try_from(u64_at(16)).map_err(|_| SceneError::Limit)?;
        let style_count = usize::try_from(u64_at(24)).map_err(|_| SceneError::Limit)?;
        if record_count > MAX_SCENE_MARKS || style_count > MAX_SCENE_STYLES {
            return Err(SceneError::Limit);
        }
        let required = SCENE_BATCH_HEADER_BYTES
            .checked_add(
                style_count
                    .checked_mul(SCENE_STYLE_RECORD_BYTES)
                    .ok_or(SceneError::Limit)?,
            )
            .and_then(|value| {
                value.checked_add(record_count.checked_mul(SCENE_BATCH_RECORD_BYTES)?)
            })
            .ok_or(SceneError::Limit)?;
        if bytes.len() != required {
            return Err(SceneError::Length);
        }
        let viewport_width = f64_at(32);
        let viewport_height = f64_at(40);
        let left = f64_at(48);
        let top = f64_at(56);
        let right = f64_at(64);
        let bottom = f64_at(72);
        let layout = PlotLayout::new(
            viewport_width,
            viewport_height,
            left,
            viewport_width - right,
            top,
            viewport_height - bottom,
        )?;
        if bytes[96] > ScaleKind::SymLog as u8
            || bytes[104] > ScaleKind::SymLog as u8
            || !matches!(bytes[97], 0 | 1)
            || !matches!(bytes[105], 0 | 1)
            || bytes[98..104] != [0; 6]
            || bytes[106..112] != [0; 6]
            || (112..160)
                .step_by(8)
                .any(|offset| !f64_at(offset).is_finite())
            || f64_at(144) <= 0.0
            || f64_at(152) <= 0.0
        {
            return Err(SceneError::NonFinite);
        }
        let mut styles = Vec::with_capacity(style_count);
        let mut offset = SCENE_BATCH_HEADER_BYTES;
        for _ in 0..style_count {
            let stroke_width = f64::from_le_bytes(
                bytes[offset + 8..offset + 16]
                    .try_into()
                    .expect("bounded style"),
            );
            if !stroke_width.is_finite() || stroke_width < 0.0 {
                return Err(SceneError::NonFinite);
            }
            styles.push(EncodedStyle {
                fill: bytes[offset..offset + 4].try_into().expect("bounded style"),
                stroke: bytes[offset + 4..offset + 8]
                    .try_into()
                    .expect("bounded style"),
                stroke_width,
            });
            offset += SCENE_STYLE_RECORD_BYTES;
        }
        let mut records = Vec::with_capacity(record_count);
        for _ in 0..record_count {
            let kind = SceneRecordKind::from_code(bytes[offset])?;
            let visible = match bytes[offset + 1] {
                0 => false,
                1 => true,
                _ => return Err(SceneError::Length),
            };
            let symbol = bytes[offset + 2];
            if bytes[offset + 3] != 0
                || (kind == SceneRecordKind::Scatter && symbol > ScatterSymbol::X as u8)
                || (kind != SceneRecordKind::Scatter && symbol != 0)
            {
                return Err(SceneError::Length);
            }
            let style_ref = u32::from_le_bytes(
                bytes[offset + 4..offset + 8]
                    .try_into()
                    .expect("bounded record"),
            ) as usize;
            if style_ref >= styles.len() {
                return Err(SceneError::Length);
            }
            let stable_id = u64::from_le_bytes(
                bytes[offset + 8..offset + 16]
                    .try_into()
                    .expect("bounded record"),
            );
            let mut coordinates = [0.0; 4];
            for (index, value) in coordinates.iter_mut().enumerate() {
                *value = f64::from_le_bytes(
                    bytes[offset + 16 + index * 8..offset + 24 + index * 8]
                        .try_into()
                        .expect("bounded record"),
                );
            }
            let diameter = f64::from_le_bytes(
                bytes[offset + 48..offset + 56]
                    .try_into()
                    .expect("bounded record"),
            );
            if coordinates.iter().any(|value| !value.is_finite())
                || !diameter.is_finite()
                || diameter < 0.0
                || (kind != SceneRecordKind::Scatter && diameter != 0.0)
                || (kind != SceneRecordKind::Rect && coordinates[2..] != [0.0, 0.0])
                || (visible
                    && kind == SceneRecordKind::Rect
                    && (coordinates[0] > coordinates[2] || coordinates[1] > coordinates[3]))
                || (!visible && coordinates != [0.0; 4])
            {
                return Err(SceneError::NonFinite);
            }
            records.push(EncodedRecord {
                kind,
                visible,
                symbol,
                style_ref,
                stable_id,
                coordinates,
                diameter,
            });
            offset += SCENE_BATCH_RECORD_BYTES;
        }
        Ok(Self {
            layout,
            styles,
            records,
        })
    }

    pub fn to_svg(&self) -> String {
        let mut out = String::with_capacity(self.records.len().saturating_mul(96));
        out.push_str("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"");
        push_num(&mut out, self.layout.viewport_width);
        out.push_str("\" height=\"");
        push_num(&mut out, self.layout.viewport_height);
        out.push_str("\" viewBox=\"0 0 ");
        push_num(&mut out, self.layout.viewport_width);
        out.push(' ');
        push_num(&mut out, self.layout.viewport_height);
        out.push_str("\"><defs><clipPath id=\"xy-scene-plot\"><rect x=\"");
        push_num(&mut out, self.layout.left);
        out.push_str("\" y=\"");
        push_num(&mut out, self.layout.top);
        out.push_str("\" width=\"");
        push_num(&mut out, self.layout.right - self.layout.left);
        out.push_str("\" height=\"");
        push_num(&mut out, self.layout.bottom - self.layout.top);
        out.push_str("\"/></clipPath></defs><g clip-path=\"url(#xy-scene-plot)\">");
        let mut index = 0;
        while index < self.records.len() {
            let record = self.records[index];
            if !record.visible {
                index += 1;
                continue;
            }
            let style = self.styles[record.style_ref];
            match record.kind {
                SceneRecordKind::Scatter => {
                    let symbol = ScatterSymbol::from_code(record.symbol);
                    let geometry = MarkerGeometry::new(symbol, record.diameter, style.stroke_width);
                    push_symbol(
                        &mut out,
                        symbol,
                        record.coordinates[0],
                        record.coordinates[1],
                        geometry.radius,
                    );
                    if symbol.is_line() {
                        out.push_str(" fill=\"none\"");
                    } else {
                        push_paint(&mut out, "fill", style.fill, None);
                    }
                    if geometry.stroke_width > 0.0 || symbol.is_line() {
                        push_paint(&mut out, "stroke", style.stroke, None);
                        out.push_str(" stroke-width=\"");
                        push_num(&mut out, geometry.stroke_width);
                        out.push('"');
                    }
                    out.push_str("/>");
                    index += 1;
                }
                SceneRecordKind::Rect => {
                    out.push_str("<rect x=\"");
                    push_num(&mut out, record.coordinates[0]);
                    out.push_str("\" y=\"");
                    push_num(&mut out, record.coordinates[1]);
                    out.push_str("\" width=\"");
                    push_num(&mut out, record.coordinates[2] - record.coordinates[0]);
                    out.push_str("\" height=\"");
                    push_num(&mut out, record.coordinates[3] - record.coordinates[1]);
                    out.push('"');
                    push_paint(&mut out, "fill", style.fill, None);
                    if style.stroke_width > 0.0 {
                        push_paint(&mut out, "stroke", style.stroke, None);
                        out.push_str(" stroke-width=\"");
                        push_num(&mut out, style.stroke_width);
                        out.push('"');
                    }
                    out.push_str("/>");
                    index += 1;
                }
                SceneRecordKind::Polyline => {
                    out.push_str("<polyline points=\"");
                    let id = record.stable_id;
                    let style_ref = record.style_ref;
                    while index < self.records.len() {
                        let point = self.records[index];
                        if point.kind != SceneRecordKind::Polyline
                            || point.stable_id != id
                            || point.style_ref != style_ref
                            || !point.visible
                        {
                            break;
                        }
                        if index > 0 {
                            out.push(' ');
                        }
                        push_num(&mut out, point.coordinates[0]);
                        out.push(',');
                        push_num(&mut out, point.coordinates[1]);
                        index += 1;
                    }
                    out.push_str("\" fill=\"none\"");
                    push_paint(&mut out, "stroke", style.stroke, None);
                    out.push_str(" stroke-width=\"");
                    push_num(&mut out, style.stroke_width);
                    out.push_str("\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/>");
                }
            }
        }
        out.push_str("</g><g><path fill=\"none\" stroke=\"rgb(0,0,0)\" stroke-width=\"1\" d=\"M ");
        push_num(&mut out, self.layout.left);
        out.push(' ');
        push_num(&mut out, self.layout.bottom);
        out.push_str(" H ");
        push_num(&mut out, self.layout.right);
        out.push_str("\"/><path fill=\"none\" stroke=\"rgb(0,0,0)\" stroke-width=\"1\" d=\"M ");
        push_num(&mut out, self.layout.left);
        out.push(' ');
        push_num(&mut out, self.layout.top);
        out.push_str(" V ");
        push_num(&mut out, self.layout.bottom);
        out.push_str("\"/></g></svg>");
        out
    }

    pub fn to_raster_commands(&self, scale: f64) -> Result<Vec<u8>, SceneError> {
        if !scale.is_finite() || scale <= 0.0 {
            return Err(SceneError::NonFinite);
        }
        let mut out = Vec::with_capacity(self.records.len().saturating_mul(40));
        let f32_push = |out: &mut Vec<u8>, value: f64| {
            out.extend_from_slice(&((value * scale) as f32).to_le_bytes())
        };
        out.push(0);
        f32_push(&mut out, self.layout.left);
        f32_push(&mut out, self.layout.top);
        f32_push(&mut out, self.layout.right - self.layout.left);
        f32_push(&mut out, self.layout.bottom - self.layout.top);
        let mut index = 0;
        while index < self.records.len() {
            let record = self.records[index];
            if !record.visible {
                index += 1;
                continue;
            }
            let style = self.styles[record.style_ref];
            match record.kind {
                SceneRecordKind::Scatter => {
                    let geometry = MarkerGeometry::new(
                        ScatterSymbol::from_code(record.symbol),
                        record.diameter,
                        style.stroke_width,
                    );
                    out.push(4);
                    f32_push(&mut out, record.coordinates[0]);
                    f32_push(&mut out, record.coordinates[1]);
                    f32_push(&mut out, geometry.radius);
                    out.push(record.symbol);
                    out.extend_from_slice(&style.fill);
                    f32_push(&mut out, geometry.stroke_width);
                    out.extend_from_slice(&style.stroke);
                    index += 1;
                }
                SceneRecordKind::Rect => {
                    let points = [
                        (record.coordinates[0], record.coordinates[1]),
                        (record.coordinates[2], record.coordinates[1]),
                        (record.coordinates[2], record.coordinates[3]),
                        (record.coordinates[0], record.coordinates[3]),
                    ];
                    out.push(1);
                    out.extend_from_slice(&4u32.to_le_bytes());
                    for (x, y) in points {
                        f32_push(&mut out, x);
                        f32_push(&mut out, y);
                    }
                    out.extend_from_slice(&style.fill);
                    if style.stroke_width > 0.0 {
                        out.push(3);
                        out.extend_from_slice(&4u32.to_le_bytes());
                        for (x, y) in points {
                            f32_push(&mut out, x);
                            f32_push(&mut out, y);
                        }
                        f32_push(&mut out, style.stroke_width);
                        out.extend_from_slice(&style.stroke);
                        out.push(1);
                        out.extend_from_slice(&0u32.to_le_bytes());
                        out.push(1);
                    }
                    index += 1;
                }
                SceneRecordKind::Polyline => {
                    let start = index;
                    let id = record.stable_id;
                    let style_ref = record.style_ref;
                    while index < self.records.len() {
                        let point = self.records[index];
                        if point.kind != SceneRecordKind::Polyline
                            || point.stable_id != id
                            || point.style_ref != style_ref
                            || !point.visible
                        {
                            break;
                        }
                        index += 1;
                    }
                    let count = index - start;
                    if count >= 2 && style.stroke_width > 0.0 {
                        out.push(3);
                        out.extend_from_slice(&(count as u32).to_le_bytes());
                        for point in &self.records[start..index] {
                            f32_push(&mut out, point.coordinates[0]);
                            f32_push(&mut out, point.coordinates[1]);
                        }
                        f32_push(&mut out, style.stroke_width);
                        out.extend_from_slice(&style.stroke);
                        out.push(0);
                        out.extend_from_slice(&0u32.to_le_bytes());
                        out.push(1);
                    }
                }
            }
        }
        // Reset the plot clip before chrome, then draw the canonical bottom
        // and left axes through the same display-list primitive as line marks.
        out.push(0);
        for value in [
            0.0,
            0.0,
            self.layout.viewport_width,
            self.layout.viewport_height,
        ] {
            f32_push(&mut out, value);
        }
        for points in [
            [
                (self.layout.left, self.layout.bottom),
                (self.layout.right, self.layout.bottom),
            ],
            [
                (self.layout.left, self.layout.top),
                (self.layout.left, self.layout.bottom),
            ],
        ] {
            out.push(3);
            out.extend_from_slice(&2u32.to_le_bytes());
            for (x, y) in points {
                f32_push(&mut out, x);
                f32_push(&mut out, y);
            }
            f32_push(&mut out, 1.0);
            out.extend_from_slice(&[0, 0, 0, 255]);
            out.push(0);
            out.extend_from_slice(&0u32.to_le_bytes());
            out.push(1);
        }
        Ok(out)
    }
}

pub struct ScatterScene<'a> {
    x: &'a [f64],
    y: &'a [f64],
    diameter: &'a [f64],
    fill_rgba: &'a [u8],
    stroke_rgba: &'a [u8],
    stroke_width: &'a [f64],
    symbols: &'a [u8],
    visible: Option<&'a [u8]>,
    fill_css: Option<&'a str>,
    stroke_css: Option<&'a str>,
}

impl<'a> ScatterScene<'a> {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        x: &'a [f64],
        y: &'a [f64],
        diameter: &'a [f64],
        fill_rgba: &'a [u8],
        stroke_rgba: &'a [u8],
        stroke_width: &'a [f64],
        symbols: &'a [u8],
        visible: Option<&'a [u8]>,
        fill_css: Option<&'a str>,
        stroke_css: Option<&'a str>,
    ) -> Result<Self, SceneError> {
        let len = x.len();
        if len > MAX_SCENE_MARKS {
            return Err(SceneError::Limit);
        }
        let rgba_len = len.checked_mul(4).ok_or(SceneError::Limit)?;
        if y.len() != len
            || diameter.len() != len
            || fill_rgba.len() != rgba_len
            || stroke_rgba.len() != rgba_len
            || stroke_width.len() != len
            || symbols.len() != len
            || visible.is_some_and(|items| items.len() != len)
        {
            return Err(SceneError::Length);
        }
        if x.iter()
            .chain(y)
            .chain(diameter)
            .chain(stroke_width)
            .any(|value| !value.is_finite())
        {
            return Err(SceneError::NonFinite);
        }
        if diameter.iter().any(|value| *value < 0.0)
            || stroke_width.iter().any(|value| *value < 0.0)
        {
            return Err(SceneError::NegativeSize);
        }
        if fill_css.is_some_and(|value| css::parse_color(value).is_err())
            || stroke_css.is_some_and(|value| css::parse_color(value).is_err())
        {
            return Err(SceneError::InvalidPaint);
        }
        Ok(Self {
            x,
            y,
            diameter,
            fill_rgba,
            stroke_rgba,
            stroke_width,
            symbols,
            visible,
            fill_css,
            stroke_css,
        })
    }

    pub fn to_svg(&self) -> String {
        let mut out = String::with_capacity(self.x.len().saturating_mul(112));
        out.push_str("<g>");
        for index in 0..self.x.len() {
            if self.visible.is_some_and(|items| items[index] == 0) {
                continue;
            }
            let symbol = ScatterSymbol::from_code(self.symbols[index]);
            let geometry =
                MarkerGeometry::new(symbol, self.diameter[index], self.stroke_width[index]);
            push_symbol(
                &mut out,
                symbol,
                self.x[index],
                self.y[index],
                geometry.radius,
            );
            let fill = rgba_at(self.fill_rgba, index);
            let stroke = rgba_at(self.stroke_rgba, index);
            if symbol.is_line() {
                out.push_str(" fill=\"none\"");
            } else {
                push_paint(&mut out, "fill", fill, self.fill_css);
            }
            if geometry.stroke_width > 0.0 || symbol.is_line() {
                push_paint(&mut out, "stroke", stroke, self.stroke_css);
                out.push_str(" stroke-width=\"");
                push_num(&mut out, geometry.stroke_width);
                out.push('"');
            }
            out.push_str("/>");
        }
        out.push_str("</g>");
        out
    }
}

fn rgba_at(values: &[u8], index: usize) -> [u8; 4] {
    let offset = index * 4;
    [
        values[offset],
        values[offset + 1],
        values[offset + 2],
        values[offset + 3],
    ]
}

fn push_paint(out: &mut String, name: &str, rgba: [u8; 4], css: Option<&str>) {
    write!(out, " {name}=\"").expect("writing to String cannot fail");
    if let Some(value) = css {
        push_escaped_attribute(out, value);
    } else {
        write!(out, "rgb({},{},{})", rgba[0], rgba[1], rgba[2])
            .expect("writing to String cannot fail");
    }
    out.push('"');
    if rgba[3] < 255 {
        write!(out, " {name}-opacity=\"").expect("writing to String cannot fail");
        push_num(out, f64::from(rgba[3]) / 255.0);
        out.push('"');
    }
}

fn push_escaped_attribute(out: &mut String, value: &str) {
    for character in value.chars() {
        match character {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            _ => out.push(character),
        }
    }
}

fn point(out: &mut String, x: f64, y: f64) {
    push_num(out, x);
    out.push(' ');
    push_num(out, y);
}

fn push_symbol(out: &mut String, symbol: ScatterSymbol, cx: f64, cy: f64, radius: f64) {
    match symbol {
        ScatterSymbol::Circle | ScatterSymbol::Point => {
            out.push_str("<circle cx=\"");
            push_num(out, cx);
            out.push_str("\" cy=\"");
            push_num(out, cy);
            out.push_str("\" r=\"");
            push_num(out, radius);
            out.push('"');
        }
        ScatterSymbol::Square | ScatterSymbol::Pixel => {
            out.push_str("<rect x=\"");
            push_num(out, cx - radius);
            out.push_str("\" y=\"");
            push_num(out, cy - radius);
            out.push_str("\" width=\"");
            push_num(out, radius * 2.0);
            out.push_str("\" height=\"");
            push_num(out, radius * 2.0);
            out.push('"');
        }
        ScatterSymbol::Diamond | ScatterSymbol::ThinDiamond => {
            let dx = std::f64::consts::SQRT_2
                * radius
                * if symbol == ScatterSymbol::ThinDiamond {
                    0.6
                } else {
                    1.0
                };
            let dy = std::f64::consts::SQRT_2 * radius;
            out.push_str("<path d=\"M ");
            point(out, cx, cy - dy);
            out.push_str(" L ");
            point(out, cx + dx, cy);
            out.push_str(" L ");
            point(out, cx, cy + dy);
            out.push_str(" L ");
            point(out, cx - dx, cy);
            out.push_str(" Z\"");
        }
        ScatterSymbol::Triangle
        | ScatterSymbol::TriangleDown
        | ScatterSymbol::TriangleLeft
        | ScatterSymbol::TriangleRight => push_triangle(out, symbol, cx, cy, radius),
        ScatterSymbol::Cross => push_cross(out, cx, cy, radius),
        ScatterSymbol::X => push_x(out, cx, cy, radius),
        ScatterSymbol::PlusLine => {
            out.push_str("<path d=\"M ");
            point(out, cx - radius, cy);
            out.push_str(" H ");
            push_num(out, cx + radius);
            out.push_str(" M ");
            point(out, cx, cy - radius);
            out.push_str(" V ");
            push_num(out, cy + radius);
            out.push('"');
        }
        ScatterSymbol::XLine => {
            let delta = 0.707 * radius;
            out.push_str("<path d=\"M ");
            point(out, cx - delta, cy - delta);
            out.push_str(" L ");
            point(out, cx + delta, cy + delta);
            out.push_str(" M ");
            point(out, cx + delta, cy - delta);
            out.push_str(" L ");
            point(out, cx - delta, cy + delta);
            out.push('"');
        }
        ScatterSymbol::HorizontalLine | ScatterSymbol::VerticalLine => {
            out.push_str("<path d=\"M ");
            if symbol == ScatterSymbol::HorizontalLine {
                point(out, cx - radius, cy);
                out.push_str(" H ");
                push_num(out, cx + radius);
            } else {
                point(out, cx, cy - radius);
                out.push_str(" V ");
                push_num(out, cy + radius);
            }
            out.push('"');
        }
        ScatterSymbol::Pentagon => push_regular_polygon(out, cx, cy, radius, 5, -90.0, 1.0),
        ScatterSymbol::Hexagon => push_regular_polygon(out, cx, cy, radius, 6, -90.0, 1.0),
        ScatterSymbol::Star => push_regular_polygon(out, cx, cy, radius, 10, -90.0, 0.45),
    }
}

fn push_triangle(out: &mut String, symbol: ScatterSymbol, cx: f64, cy: f64, r: f64) {
    let points = match symbol {
        ScatterSymbol::Triangle => [(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)],
        ScatterSymbol::TriangleDown => [(cx, cy + r), (cx + r, cy - r), (cx - r, cy - r)],
        ScatterSymbol::TriangleLeft => [(cx - r, cy), (cx + r, cy - r), (cx + r, cy + r)],
        _ => [(cx + r, cy), (cx - r, cy - r), (cx - r, cy + r)],
    };
    out.push_str("<path d=\"M ");
    point(out, points[0].0, points[0].1);
    for item in &points[1..] {
        out.push_str(" L ");
        point(out, item.0, item.1);
    }
    out.push_str(" Z\"");
}

fn push_cross(out: &mut String, cx: f64, cy: f64, r: f64) {
    let d = 0.34 * r;
    out.push_str("<path d=\"M ");
    point(out, cx - d, cy - r);
    write!(out, " H ").expect("writing to String cannot fail");
    push_num(out, cx + d);
    out.push_str(" V ");
    push_num(out, cy - d);
    out.push_str(" H ");
    push_num(out, cx + r);
    out.push_str(" V ");
    push_num(out, cy + d);
    out.push_str(" H ");
    push_num(out, cx + d);
    out.push_str(" V ");
    push_num(out, cy + r);
    out.push_str(" H ");
    push_num(out, cx - d);
    out.push_str(" V ");
    push_num(out, cy + d);
    out.push_str(" H ");
    push_num(out, cx - r);
    out.push_str(" V ");
    push_num(out, cy - d);
    out.push_str(" H ");
    push_num(out, cx - d);
    out.push_str(" Z\"");
}

fn push_x(out: &mut String, cx: f64, cy: f64, r: f64) {
    let outer = 0.72 * r;
    let inner = 0.28 * r;
    let points = [
        (cx - outer, cy - r),
        (cx, cy - inner),
        (cx + outer, cy - r),
        (cx + r, cy - outer),
        (cx + inner, cy),
        (cx + r, cy + outer),
        (cx + outer, cy + r),
        (cx, cy + inner),
        (cx - outer, cy + r),
        (cx - r, cy + outer),
        (cx - inner, cy),
        (cx - r, cy - outer),
    ];
    out.push_str("<path d=\"M ");
    point(out, points[0].0, points[0].1);
    for item in &points[1..] {
        out.push_str(" L ");
        point(out, item.0, item.1);
    }
    out.push_str(" Z\"");
}

fn push_regular_polygon(
    out: &mut String,
    cx: f64,
    cy: f64,
    radius: f64,
    vertices: usize,
    start_degrees: f64,
    inner_ratio: f64,
) {
    out.push_str("<path d=\"M ");
    for index in 0..vertices {
        if index != 0 {
            out.push_str(" L ");
        }
        let point_radius = if inner_ratio < 1.0 && index % 2 == 1 {
            radius * inner_ratio
        } else {
            radius
        };
        let angle = (start_degrees + index as f64 * 360.0 / vertices as f64).to_radians();
        point(
            out,
            cx + point_radius * angle.cos(),
            cy + point_radius * angle.sin(),
        );
    }
    out.push_str(" Z\"");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scatter_scene_is_versioned_bounded_and_deterministic() {
        let scene = ScatterScene::new(
            &[10.0, 20.0],
            &[11.0, 21.0],
            &[8.0, 10.0],
            &[37, 99, 235, 255, 239, 68, 68, 128],
            &[0, 0, 0, 255, 17, 24, 39, 64],
            &[2.0, 0.0],
            &[ScatterSymbol::Circle as u8, ScatterSymbol::PlusLine as u8],
            None,
            None,
            None,
        )
        .unwrap();
        assert_eq!(SCENE_VERSION, 3);
        assert_eq!(
            scene.to_svg(),
            "<g><circle cx=\"10\" cy=\"11\" r=\"3\" fill=\"rgb(37,99,235)\" stroke=\"rgb(0,0,0)\" stroke-width=\"2\"/><path d=\"M 15.5 21 H 24.5 M 20 16.5 V 25.5\" fill=\"none\" stroke=\"rgb(17,24,39)\" stroke-opacity=\"0.25\" stroke-width=\"1\"/></g>"
        );
    }

    #[test]
    fn scene_v3_batch_encodes_layout_axes_and_all_core_record_kinds() {
        let layout = PlotLayout::new(640.0, 480.0, 40.0, 20.0, 10.0, 30.0).unwrap();
        let x_scale =
            AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 40.0, 620.0, 1.0, false).unwrap();
        let y_scale =
            AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 450.0, 10.0, 1.0, false).unwrap();
        let batch = SceneBatch::new(
            layout,
            11,
            12,
            x_scale,
            y_scale,
            &[0, 1, 1, 2],
            &[101, 201, 201, 301],
            &[1, 2, 2, 3],
            &[0; 16],
            &[0; 16],
            &[0.0, 2.0, 1.0, 0.0],
            &[16.0, 0.0, 0.0, 0.0],
            &[ScatterSymbol::Diamond as u8, 0, 0, 0],
            &[-0.1, -1.0, 10.0, 2.0],
            &[5.0, 1.0, 9.0, 3.0],
            &[-0.1, -1.0, 10.0, 4.0],
            &[5.0, 1.0, 9.0, 7.0],
        )
        .unwrap();
        let encoded = batch.encode();
        assert_eq!(&encoded[..4], b"XYGS");
        assert_eq!(u32::from_le_bytes(encoded[4..8].try_into().unwrap()), 3);
        assert_eq!(u64::from_le_bytes(encoded[16..24].try_into().unwrap()), 4);
        assert_eq!(
            encoded.len(),
            SCENE_BATCH_HEADER_BYTES + 4 * SCENE_STYLE_RECORD_BYTES + 4 * SCENE_BATCH_RECORD_BYTES
        );
        assert_eq!(u64::from_le_bytes(encoded[24..32].try_into().unwrap()), 4);
        assert_eq!(u64::from_le_bytes(encoded[80..88].try_into().unwrap()), 11);
        assert_eq!(u64::from_le_bytes(encoded[88..96].try_into().unwrap()), 12);
        let records = SCENE_BATCH_HEADER_BYTES + 4 * SCENE_STYLE_RECORD_BYTES;
        // The diamond center maps left of the plot, but its canonical
        // symbol-specific extent overlaps and must remain renderable.
        assert_eq!(encoded[records + 1], 1);
        assert_eq!(encoded[records + 2], ScatterSymbol::Diamond as u8);
        assert_eq!(
            f64::from_le_bytes(encoded[records + 48..records + 56].try_into().unwrap()),
            16.0
        );
        assert_eq!(encoded[records + SCENE_BATCH_RECORD_BYTES + 1], 1);
        assert_eq!(&encoded[records + 32..records + 48], &[0; 16]);
        let line0 = records + SCENE_BATCH_RECORD_BYTES;
        let line1 = line0 + SCENE_BATCH_RECORD_BYTES;
        assert_eq!(
            u64::from_le_bytes(encoded[line0 + 8..line0 + 16].try_into().unwrap()),
            201
        );
        assert_eq!(
            u64::from_le_bytes(encoded[line1 + 8..line1 + 16].try_into().unwrap()),
            201
        );
        assert_eq!(&encoded[line0 + 32..line0 + 48], &[0; 16]);
        let rect = line1 + SCENE_BATCH_RECORD_BYTES;
        let rect_coords: Vec<f64> = (0..4)
            .map(|slot| {
                f64::from_le_bytes(
                    encoded[rect + 16 + slot * 8..rect + 24 + slot * 8]
                        .try_into()
                        .unwrap(),
                )
            })
            .collect();
        assert_eq!(rect_coords, vec![156.0, 142.0, 272.0, 318.0]);
    }

    #[test]
    fn scene_v3_document_drives_svg_and_raster_from_same_records() {
        let layout = PlotLayout::new(120.0, 100.0, 10.0, 10.0, 10.0, 10.0).unwrap();
        let sx = AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 10.0, 110.0, 1.0, false).unwrap();
        let sy = AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 90.0, 10.0, 1.0, false).unwrap();
        let encoded = SceneBatch::new(
            layout,
            1,
            2,
            sx,
            sy,
            &[0, 1, 1, 2],
            &[10, 20, 20, 30],
            &[0, 1, 1, 2],
            &[57, 135, 229, 255, 0, 0, 0, 0, 57, 135, 229, 180],
            &[0, 0, 0, 255, 239, 68, 68, 255, 0, 0, 0, 255],
            &[1.0, 2.0, 1.0],
            &[8.0, 0.0, 0.0, 0.0],
            &[2, 0, 0, 0],
            &[2.0, 1.0, 8.0, 4.0],
            &[3.0, 2.0, 7.0, 1.0],
            &[0.0, 0.0, 0.0, 6.0],
            &[0.0, 0.0, 0.0, 5.0],
        )
        .unwrap()
        .encode();
        let document = SceneDocument::decode(&encoded).unwrap();
        let svg = document.to_svg();
        assert!(svg.starts_with("<svg "));
        assert!(
            svg.contains("<path d=\"M ")
                && svg.contains("<polyline points=\"")
                && svg.contains("<rect x=\"")
        );
        let commands = document.to_raster_commands(2.0).unwrap();
        assert!(commands.contains(&4)); // point
        assert!(commands.contains(&3)); // polyline + axes
        assert!(commands.contains(&1)); // rectangle fill
        assert!(crate::raster::rasterize_into(
            &commands,
            240,
            200,
            &mut vec![0; 240 * 200 * 4]
        ));

        let mut malformed = encoded;
        malformed[4] = 99;
        assert!(SceneDocument::decode(&malformed).is_err());
        let mut bad_reserved = malformed.clone();
        bad_reserved[4..8].copy_from_slice(&SCENE_VERSION.to_le_bytes());
        bad_reserved[98] = 1;
        assert!(SceneDocument::decode(&bad_reserved).is_err());
        let mut bad_kind = bad_reserved.clone();
        bad_kind[98] = 0;
        bad_kind[SCENE_BATCH_HEADER_BYTES + 3 * SCENE_STYLE_RECORD_BYTES] = 9;
        assert!(SceneDocument::decode(&bad_kind).is_err());
        assert!(SceneDocument::decode(&bad_kind[..bad_kind.len() - 1]).is_err());
    }

    #[test]
    fn canonical_symbol_extents_drive_scene_clipping() {
        let layout = PlotLayout::new(100.0, 100.0, 10.0, 10.0, 10.0, 10.0).unwrap();
        let scale = AxisScale::new(ScaleKind::Linear, 0.0, 80.0, 10.0, 90.0, 1.0, false).unwrap();
        let batch = SceneBatch::new(
            layout,
            1,
            2,
            scale,
            scale,
            &[0, 0, 0, 0],
            &[1, 2, 3, 4],
            &[0; 4],
            &[0; 4],
            &[0; 4],
            &[0.0],
            &[20.0; 4],
            &[
                ScatterSymbol::Diamond as u8,
                ScatterSymbol::Diamond as u8,
                ScatterSymbol::ThinDiamond as u8,
                ScatterSymbol::ThinDiamond as u8,
            ],
            &[-12.0, -14.2, 40.0, 40.0],
            &[40.0, 40.0, -12.0, -14.2],
            &[0.0; 4],
            &[0.0; 4],
        )
        .unwrap();
        let encoded = batch.encode();
        let records = SCENE_BATCH_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES;
        assert_eq!(encoded[records + 1], 1);
        assert_eq!(encoded[records + SCENE_BATCH_RECORD_BYTES + 1], 0);
        assert_eq!(encoded[records + 2 * SCENE_BATCH_RECORD_BYTES + 1], 1);
        assert_eq!(encoded[records + 3 * SCENE_BATCH_RECORD_BYTES + 1], 0);

        let line = MarkerGeometry::new(ScatterSymbol::PlusLine, 0.0, 0.0);
        assert_eq!(line.radius, 0.0);
        assert_eq!(line.stroke_width, 1.0);
        assert_eq!(line.extent_x, 0.5);
        assert_eq!(line.extent_y, 0.5);
    }

    #[test]
    fn log_mask_maps_only_coordinates_used_by_each_record_kind() {
        let layout = PlotLayout::new(100.0, 100.0, 10.0, 10.0, 10.0, 10.0).unwrap();
        let scale = AxisScale::new(ScaleKind::Log, 1.0, 10.0, 10.0, 90.0, 1.0, true).unwrap();
        let batch = SceneBatch::new(
            layout,
            1,
            2,
            scale,
            scale,
            &[0, 1, 1, 1, 2, 2],
            &[1, 20, 20, 20, 30, 31],
            &[0; 6],
            &[0; 4],
            &[0; 4],
            &[0.0],
            &[6.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            &[0; 6],
            &[2.0, 2.0, 0.0, 4.0, 2.0, 2.0],
            &[2.0; 6],
            &[0.0, 0.0, 0.0, 0.0, 8.0, 0.0],
            &[0.0, 0.0, 0.0, 0.0, 8.0, 8.0],
        )
        .unwrap();
        let encoded = batch.encode();
        let records = SCENE_BATCH_HEADER_BYTES + SCENE_STYLE_RECORD_BYTES;
        let flags: Vec<u8> = (0..6)
            .map(|index| encoded[records + index * SCENE_BATCH_RECORD_BYTES + 1])
            .collect();
        assert_eq!(flags, vec![1, 1, 0, 1, 1, 0]);
        // Reserved zeros never enter log-mask mapping and are always emitted
        // as zero. The masked middle vertex breaks the stable-id 20 run.
        for index in [0, 1, 3] {
            let record = records + index * SCENE_BATCH_RECORD_BYTES;
            assert_eq!(&encoded[record + 32..record + 48], &[0; 16]);
        }
        assert_eq!(
            &encoded[records + 2 * SCENE_BATCH_RECORD_BYTES + 16
                ..records + 2 * SCENE_BATCH_RECORD_BYTES + 48],
            &[0; 32]
        );
    }

    #[test]
    fn scene_v3_batch_rejects_bad_bounds_lengths_kinds_and_nonfinite_input() {
        assert_eq!(
            PlotLayout::new(10.0, 10.0, 6.0, 4.0, 0.0, 0.0),
            Err(SceneError::NonFinite)
        );
        let layout = PlotLayout::new(10.0, 10.0, 1.0, 1.0, 1.0, 1.0).unwrap();
        let scale = AxisScale::new(ScaleKind::Linear, 0.0, 1.0, 1.0, 9.0, 1.0, false).unwrap();
        assert_eq!(
            SceneBatch::new(
                layout,
                1,
                2,
                scale,
                scale,
                &[9],
                &[1],
                &[0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[1.0],
                &[0],
                &[0.0],
                &[0.0],
                &[0.0],
                &[0.0]
            )
            .err(),
            Some(SceneError::Length)
        );
        assert_eq!(
            SceneBatch::new(
                layout,
                1,
                2,
                scale,
                scale,
                &[0],
                &[],
                &[0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[1.0],
                &[0],
                &[0.0],
                &[0.0],
                &[0.0],
                &[0.0]
            )
            .err(),
            Some(SceneError::Length)
        );
        assert_eq!(
            SceneBatch::new(
                layout,
                1,
                2,
                scale,
                scale,
                &[0],
                &[1],
                &[0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[1.0],
                &[0],
                &[f64::NAN],
                &[0.0],
                &[0.0],
                &[0.0]
            )
            .err(),
            Some(SceneError::NonFinite)
        );
        let invalid_record = |style_ref, diameter, symbol| {
            SceneBatch::new(
                layout,
                1,
                2,
                scale,
                scale,
                &[0],
                &[1],
                &[style_ref],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[diameter],
                &[symbol],
                &[0.0],
                &[0.0],
                &[0.0],
                &[0.0],
            )
            .err()
        };
        assert_eq!(invalid_record(1, 1.0, 0), Some(SceneError::Length));
        assert_eq!(invalid_record(0, 1.0, 19), Some(SceneError::Length));
        assert_eq!(invalid_record(0, -1.0, 0), Some(SceneError::NonFinite));
        assert_eq!(
            SceneBatch::new(
                layout,
                1,
                2,
                scale,
                scale,
                &[],
                &[],
                &[],
                &[],
                &[],
                &vec![0.0; MAX_SCENE_STYLES + 1],
                &[],
                &[],
                &[],
                &[],
                &[],
                &[],
            )
            .err(),
            Some(SceneError::Limit)
        );
    }

    #[test]
    fn scatter_scene_rejects_bad_lengths_nonfinite_and_negative_sizes() {
        assert_eq!(
            ScatterScene::new(
                &[1.0],
                &[],
                &[1.0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[0],
                None,
                None,
                None,
            )
            .err(),
            Some(SceneError::Length)
        );
        assert_eq!(
            ScatterScene::new(
                &[f64::NAN],
                &[1.0],
                &[1.0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[0],
                None,
                None,
                None,
            )
            .err(),
            Some(SceneError::NonFinite)
        );
        assert_eq!(
            ScatterScene::new(
                &[1.0],
                &[1.0],
                &[-1.0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[0],
                None,
                None,
                None,
            )
            .err(),
            Some(SceneError::NegativeSize)
        );
    }

    #[test]
    fn scatter_scene_rejects_limit_and_invalid_paint() {
        let too_many = vec![0.0; MAX_SCENE_MARKS + 1];
        assert_eq!(
            ScatterScene::new(&too_many, &[], &[], &[], &[], &[], &[], None, None, None,).err(),
            Some(SceneError::Limit)
        );
        assert_eq!(
            ScatterScene::new(
                &[1.0],
                &[1.0],
                &[1.0],
                &[0; 4],
                &[0; 4],
                &[0.0],
                &[0],
                None,
                Some("not-a-color"),
                None,
            )
            .err(),
            Some(SceneError::InvalidPaint)
        );
    }

    #[test]
    fn scatter_scene_hides_marks_and_preserves_constant_css_paint() {
        let scene = ScatterScene::new(
            &[10.0, 20.0],
            &[11.0, 21.0],
            &[8.0, 10.0],
            &[37, 99, 235, 255, 239, 68, 68, 128],
            &[0; 8],
            &[0.0, 0.0],
            &[ScatterSymbol::Circle as u8, ScatterSymbol::Circle as u8],
            Some(&[0, 1]),
            Some("var(--brand)"),
            None,
        )
        .unwrap();
        assert_eq!(
            scene.to_svg(),
            "<g><circle cx=\"20\" cy=\"21\" r=\"5\" fill=\"var(--brand)\" fill-opacity=\"0.5\"/></g>"
        );

        let mut escaped = String::new();
        push_escaped_attribute(&mut escaped, "&<>\"");
        assert_eq!(escaped, "&amp;&lt;&gt;&quot;");
    }

    #[test]
    fn symbol_shape_families_have_deterministic_svg() {
        let mut outputs = Vec::new();
        for symbol in [
            ScatterSymbol::Square,
            ScatterSymbol::Diamond,
            ScatterSymbol::Triangle,
            ScatterSymbol::Cross,
            ScatterSymbol::X,
            ScatterSymbol::Pentagon,
            ScatterSymbol::Star,
        ] {
            let mut output = String::new();
            push_symbol(&mut output, symbol, 10.0, 20.0, 2.0);
            outputs.push(output);
        }
        assert!(outputs.iter().map(String::as_str).eq([
            "<rect x=\"8\" y=\"18\" width=\"4\" height=\"4\"",
            "<path d=\"M 10 17.17 L 12.83 20 L 10 22.83 L 7.17 20 Z\"",
            "<path d=\"M 10 18 L 12 22 L 8 22 Z\"",
            "<path d=\"M 9.32 18 H 10.68 V 19.32 H 12 V 20.68 H 10.68 V 22 H 9.32 V 20.68 H 8 V 19.32 H 9.32 Z\"",
            "<path d=\"M 8.56 18 L 10 19.44 L 11.44 18 L 12 18.56 L 10.56 20 L 12 21.44 L 11.44 22 L 10 20.56 L 8.56 22 L 8 21.44 L 9.44 20 L 8 18.56 Z\"",
            "<path d=\"M 10 18 L 11.9 19.38 L 11.18 21.62 L 8.82 21.62 L 8.1 19.38 Z\"",
            "<path d=\"M 10 18 L 10.53 19.27 L 11.9 19.38 L 10.86 20.28 L 11.18 21.62 L 10 20.9 L 8.82 21.62 L 9.14 20.28 L 8.1 19.38 L 9.47 19.27 Z\"",
        ]));
    }

    #[test]
    fn canonical_linear_and_log_ticks_match_public_policy() {
        assert_eq!(
            linear_ticks(-0.9, 5.1, 6).unwrap(),
            AxisTicks {
                ticks: vec![0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                labeled: vec![0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                step: 1.0,
            }
        );
        let log = log_ticks(0.1, 100.0, 6).unwrap();
        assert_eq!(
            log.ticks,
            vec![0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0]
        );
        assert_eq!(log.labeled, vec![0.1, 1.0, 10.0, 100.0]);
        assert_eq!(log.step, 1.0);
    }

    #[test]
    fn canonical_axis_scales_map_and_invert_all_numeric_kinds() {
        let linear = AxisScale::new(ScaleKind::Linear, 0.0, 10.0, 20.0, 120.0, 1.0, false).unwrap();
        assert_eq!(linear.pixel(5.0), 70.0);
        let log = AxisScale::new(ScaleKind::Log, 0.1, 100.0, 0.0, 300.0, 1.0, false).unwrap();
        assert_eq!(log.pixel(1.0), 100.0);
        assert_eq!(log.coord(-1.0), -300.0);
        let masked = AxisScale::new(ScaleKind::Log, 0.1, 100.0, 0.0, 300.0, 1.0, true).unwrap();
        assert!(masked.coord(0.0).is_nan());
        let symlog =
            AxisScale::new(ScaleKind::SymLog, -10.0, 10.0, 0.0, 100.0, 2.0, false).unwrap();
        let coordinate = symlog.coord(-4.0);
        assert!((symlog.value(coordinate) + 4.0).abs() < 1e-12);
        assert!((symlog.pixel(0.0) - 50.0).abs() < 1e-12);
    }

    #[test]
    fn precomputed_pixel_invariants_preserve_reference_mapping() {
        for (kind, lo, hi, px0, px1, constant, mask, values) in [
            (
                ScaleKind::Linear,
                10.0,
                -2.0,
                700.0,
                20.0,
                1.0,
                false,
                vec![-2.0, 0.0, 10.0, f64::NAN],
            ),
            (
                ScaleKind::Linear,
                4.0,
                4.0,
                8.0,
                18.0,
                1.0,
                false,
                vec![4.0, 5.0],
            ),
            (
                ScaleKind::Log,
                0.1,
                100.0,
                0.0,
                300.0,
                1.0,
                false,
                vec![-1.0, 0.1, 1.0, 100.0, f64::NAN],
            ),
            (
                ScaleKind::Log,
                0.1,
                100.0,
                300.0,
                0.0,
                1.0,
                true,
                vec![0.0, 0.1, 10.0],
            ),
            (
                ScaleKind::SymLog,
                -20.0,
                20.0,
                5.0,
                405.0,
                2.0,
                false,
                vec![-20.0, -1.0, 0.0, 7.0, 20.0],
            ),
        ] {
            let scale = AxisScale::new(kind, lo, hi, px0, px1, constant, mask).unwrap();
            let low = scale.coord(lo);
            let high = scale.coord(hi);
            let span = if high == low { 1.0 } else { high - low };
            for value in values {
                let expected = px0 + (scale.coord(value) - low) / span * (px1 - px0);
                let actual = scale.pixel(value);
                assert!(
                    (expected.is_nan() && actual.is_nan())
                        || expected.to_bits() == actual.to_bits(),
                    "{kind:?} value {value}: expected {expected:?}, got {actual:?}"
                );
            }
        }
    }
}
