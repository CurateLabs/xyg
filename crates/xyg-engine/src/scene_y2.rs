//! Scene v33 secondary right-hand y axis (`y2`, twinx) block.
//!
//! One `XYY2` payload describes a complete secondary y axis: its scale, the
//! same 88-byte axis chrome record the primary axes use, the resolved XYCO
//! typography/paint facts, tick policy, authored ticks and labels, title, and
//! numeric-format grammar. The identical payload is the Scene v33 trailer block
//! (domain stored in transformed coordinates, exactly like the x/y records so
//! encode -> decode -> encode is byte-identical) and the `XYCF` ingress sidecar
//! (domain stored as data values). Layout (little endian):
//!
//! ```text
//!   0  "XYY2"
//!   4  scale kind u32 | lo f64 | hi f64 | constant f64 | mask u8 | pad[3]   (32)
//!  36  axis chrome record                                                    (88)
//! 124  tick_label_size f64 | label_size f64 | tick_padding f64
//!      text_flags u32 (bits 0..1 tick labels, 2..3 title; bit 0 italic, 1 bold)
//!      tick_rgba [4] | title_rgba [4] | present u8 (bit 0 metrics, 1 tick
//!      paint, 2 title paint) | pad[3]                                         (40)
//! 164  tick_strategy u8 | tick_anchor u8 | anchor_authored u8 | category u8
//!      min_gap f64 | angle f64 (NaN = none)                                   (20)
//! 184  major_count u32 (u32::MAX = auto) | minor_count u32 | labels_len u32
//!      title_len u32 | format_len u32                                         (20)
//! 204  major f64[] | minor f64[] | labels blob | title | format
//! ```
//!
//! The axis is right-only: the chrome record's side is High and its tick and
//! label sides are confined to the right edge.

use crate::scene::{
    decode_tick_labels, encode_tick_labels, read_axis_chrome_style, write_axis_chrome_style,
    AxisScale, AxisSide, ScaleKind, SceneAxisChromeStyle, SceneChromeStyle, SceneError,
    StaticAxisText, MAX_AXIS_TICKS, MAX_SCENE_AXIS_FORMAT_BYTES, MAX_SCENE_CHROME_LENGTH,
    MAX_SCENE_TEXT_BYTES,
};
use crate::tick_layout;

pub const SCENE_Y2_MAGIC: &[u8; 4] = b"XYY2";
pub const SCENE_Y2_FIXED_BYTES: usize = 204;

const SCALE_AT: usize = 4;
const CHROME_AT: usize = 36;
const METRICS_AT: usize = 124;
const POLICY_AT: usize = 164;
const COUNTS_AT: usize = 184;

const PRESENT_METRICS: u8 = 1 << 0;
const PRESENT_TICK_PAINT: u8 = 1 << 1;
const PRESENT_TITLE_PAINT: u8 = 1 << 2;
const AUTO_COUNT: u32 = u32::MAX;

/// Which space the scale record's `lo`/`hi` are expressed in.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SceneY2Domain {
    /// Transformed (post-scale) coordinates: the Scene trailer wire.
    Coordinates,
    /// Data values: the `XYCF` ingress sidecar.
    Data,
}

/// Decoded secondary y axis. Typography and paints live on `axis`
/// (`static_*` / `static_text`) exactly as for the primary axes.
#[derive(Clone, Debug)]
pub struct SceneY2Axis {
    pub scale: AxisScale,
    pub axis: SceneAxisChromeStyle,
    pub major_ticks: Option<Vec<f64>>,
    pub minor_ticks: Vec<f64>,
    pub tick_labels: Option<Vec<String>>,
    pub title: String,
    pub format: String,
    pub tick_strategy: u8,
    pub tick_anchor: u8,
    pub tick_anchor_authored: bool,
    pub tick_category: bool,
    pub tick_min_gap: f64,
    pub tick_angle: Option<f64>,
}

fn u32_at(bytes: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(bytes[at..at + 4].try_into().expect("bounded y2 field"))
}

fn f64_at(bytes: &[u8], at: usize) -> f64 {
    f64::from_le_bytes(bytes[at..at + 8].try_into().expect("bounded y2 field"))
}

fn flag(byte: u8) -> Result<bool, SceneError> {
    match byte {
        0 => Ok(false),
        1 => Ok(true),
        _ => Err(SceneError::Length),
    }
}

impl SceneY2Axis {
    /// Right-only, bounded, canonical-form validation shared by decode and
    /// every constructor path.
    pub fn validated(self) -> Result<Self, SceneError> {
        if self.axis.side != AxisSide::High
            || self.axis.tick_sides & !0b10 != 0
            || self.axis.tick_label_sides & !0b10 != 0
        {
            return Err(SceneError::Length);
        }
        if self.tick_strategy > tick_layout::STRATEGY_OFF as u8
            || self.tick_anchor > tick_layout::ANCHOR_END as u8
            || (!self.tick_anchor_authored && self.tick_anchor != tick_layout::ANCHOR_CENTER as u8)
        {
            return Err(SceneError::Length);
        }
        if !self.tick_min_gap.is_finite()
            || self.tick_min_gap < 0.0
            || self.tick_angle.is_some_and(|angle| !angle.is_finite())
        {
            return Err(SceneError::NonFinite);
        }
        if self.title.len() > MAX_SCENE_TEXT_BYTES
            || self.title.contains('\0')
            || self.format.len() > MAX_SCENE_AXIS_FORMAT_BYTES
            || self.format.contains('\0')
        {
            return Err(SceneError::Limit);
        }
        let axis = self.axis;
        for size in [axis.static_tick_label_size, axis.static_label_size]
            .into_iter()
            .flatten()
        {
            if !size.is_finite() || !(1.0..=MAX_SCENE_CHROME_LENGTH).contains(&size) {
                return Err(SceneError::NonFinite);
            }
        }
        if axis.static_tick_label_size.is_some() != axis.static_label_size.is_some()
            || axis.static_tick_label_size.is_some() != axis.static_tick_padding.is_some()
        {
            return Err(SceneError::Length);
        }
        if let Some(padding) = axis.static_tick_padding {
            if !padding.is_finite()
                || !(-MAX_SCENE_CHROME_LENGTH..=MAX_SCENE_CHROME_LENGTH).contains(&padding)
            {
                return Err(SceneError::NonFinite);
            }
        }
        if axis.static_text.tick_label_flags > 3 || axis.static_text.title_flags > 3 {
            return Err(SceneError::Length);
        }
        // Tick and label bounds, uniqueness and label shape are the primary y
        // axis rules; reuse them rather than restating them.
        SceneChromeStyle {
            y_axis: axis,
            y_major_ticks: self.major_ticks.clone(),
            y_minor_ticks: self.minor_ticks.clone(),
            y_tick_labels: self.tick_labels.clone(),
            ..SceneChromeStyle::default_style()
        }
        .validated()?;
        Ok(self)
    }

    /// Serialize the payload with the scale domain in the requested space.
    pub fn encode(&self, domain: SceneY2Domain) -> Vec<u8> {
        let (kind, lo, hi, constant, mask) = self.scale.wire_scale(domain == SceneY2Domain::Data);
        let labels = encode_tick_labels(self.tick_labels.as_deref()).expect("validated y2 labels");
        let majors = self.major_ticks.as_deref().unwrap_or(&[]);
        let mut out = Vec::with_capacity(
            SCENE_Y2_FIXED_BYTES
                + (majors.len() + self.minor_ticks.len()) * 8
                + labels.len()
                + self.title.len()
                + self.format.len(),
        );
        out.extend_from_slice(SCENE_Y2_MAGIC);
        out.extend_from_slice(&(kind as u32).to_le_bytes());
        out.extend_from_slice(&lo.to_le_bytes());
        out.extend_from_slice(&hi.to_le_bytes());
        out.extend_from_slice(&constant.to_le_bytes());
        out.push(u8::from(mask));
        out.extend_from_slice(&[0; 3]);
        write_axis_chrome_style(&mut out, &self.axis);
        let axis = &self.axis;
        let metrics = axis.static_tick_label_size.is_some();
        let present = (u8::from(metrics) * PRESENT_METRICS)
            | (u8::from(axis.static_text.tick_label_rgba.is_some()) * PRESENT_TICK_PAINT)
            | (u8::from(axis.static_text.title_rgba.is_some()) * PRESENT_TITLE_PAINT);
        for value in [
            axis.static_tick_label_size.unwrap_or(0.0),
            axis.static_label_size.unwrap_or(0.0),
            axis.static_tick_padding.unwrap_or(0.0),
        ] {
            out.extend_from_slice(&value.to_le_bytes());
        }
        let text_flags = u32::from(axis.static_text.tick_label_flags)
            | (u32::from(axis.static_text.title_flags) << 2);
        out.extend_from_slice(&text_flags.to_le_bytes());
        out.extend_from_slice(&axis.static_text.tick_label_rgba.unwrap_or([0; 4]));
        out.extend_from_slice(&axis.static_text.title_rgba.unwrap_or([0; 4]));
        out.push(present);
        out.extend_from_slice(&[0; 3]);
        out.push(self.tick_strategy);
        out.push(if self.tick_anchor_authored {
            self.tick_anchor
        } else {
            0
        });
        out.push(u8::from(self.tick_anchor_authored));
        out.push(u8::from(self.tick_category));
        out.extend_from_slice(&self.tick_min_gap.to_le_bytes());
        out.extend_from_slice(&self.tick_angle.unwrap_or(f64::NAN).to_le_bytes());
        out.extend_from_slice(
            &(if self.major_ticks.is_none() {
                AUTO_COUNT
            } else {
                majors.len() as u32
            })
            .to_le_bytes(),
        );
        out.extend_from_slice(&(self.minor_ticks.len() as u32).to_le_bytes());
        out.extend_from_slice(&(labels.len() as u32).to_le_bytes());
        out.extend_from_slice(&(self.title.len() as u32).to_le_bytes());
        out.extend_from_slice(&(self.format.len() as u32).to_le_bytes());
        debug_assert_eq!(out.len(), SCENE_Y2_FIXED_BYTES);
        for value in majors.iter().chain(&self.minor_ticks) {
            out.extend_from_slice(&value.to_le_bytes());
        }
        out.extend_from_slice(&labels);
        out.extend_from_slice(self.title.as_bytes());
        out.extend_from_slice(self.format.as_bytes());
        out
    }

    /// Parse one payload. `px0`/`px1` are the pixel positions of the domain's
    /// low and high ends (the plot bottom and top).
    pub fn decode(
        bytes: &[u8],
        domain: SceneY2Domain,
        px0: f64,
        px1: f64,
    ) -> Result<Self, SceneError> {
        if bytes.len() < SCENE_Y2_FIXED_BYTES || &bytes[..4] != SCENE_Y2_MAGIC {
            return Err(SceneError::Length);
        }
        let kind = match u32_at(bytes, SCALE_AT) {
            0 => ScaleKind::Linear,
            1 => ScaleKind::Log,
            2 => ScaleKind::SymLog,
            _ => return Err(SceneError::Length),
        };
        let (lo, hi, constant) = (
            f64_at(bytes, SCALE_AT + 4),
            f64_at(bytes, SCALE_AT + 12),
            f64_at(bytes, SCALE_AT + 20),
        );
        let mask = flag(bytes[SCALE_AT + 28])?;
        if bytes[SCALE_AT + 29..SCALE_AT + 32] != [0; 3] {
            return Err(SceneError::Length);
        }
        let scale = match domain {
            SceneY2Domain::Data => AxisScale::new(kind, lo, hi, px0, px1, constant, mask)?,
            SceneY2Domain::Coordinates => {
                AxisScale::from_wire_coords(kind, lo, hi, px0, px1, constant, mask)?
            }
        };
        let mut axis = read_axis_chrome_style(bytes, CHROME_AT)?;
        let present = bytes[METRICS_AT + 36];
        if present & !0b111 != 0 || bytes[METRICS_AT + 37..METRICS_AT + 40] != [0; 3] {
            return Err(SceneError::Length);
        }
        let metrics = [
            f64_at(bytes, METRICS_AT),
            f64_at(bytes, METRICS_AT + 8),
            f64_at(bytes, METRICS_AT + 16),
        ];
        if present & PRESENT_METRICS != 0 {
            axis.static_tick_label_size = Some(metrics[0]);
            axis.static_label_size = Some(metrics[1]);
            axis.static_tick_padding = Some(metrics[2]);
        } else if metrics != [0.0; 3] {
            return Err(SceneError::Length);
        }
        let text_flags = u32_at(bytes, METRICS_AT + 24);
        if text_flags & !0xf != 0 {
            return Err(SceneError::Length);
        }
        let tick_rgba: [u8; 4] = bytes[METRICS_AT + 28..METRICS_AT + 32].try_into().unwrap();
        let title_rgba: [u8; 4] = bytes[METRICS_AT + 32..METRICS_AT + 36].try_into().unwrap();
        if (present & PRESENT_TICK_PAINT == 0 && tick_rgba != [0; 4])
            || (present & PRESENT_TITLE_PAINT == 0 && title_rgba != [0; 4])
        {
            return Err(SceneError::Length);
        }
        axis.static_text = StaticAxisText {
            tick_label_rgba: (present & PRESENT_TICK_PAINT != 0).then_some(tick_rgba),
            title_rgba: (present & PRESENT_TITLE_PAINT != 0).then_some(title_rgba),
            tick_label_flags: (text_flags & 3) as u8,
            title_flags: ((text_flags >> 2) & 3) as u8,
        };
        let anchor_authored = flag(bytes[POLICY_AT + 2])?;
        let angle = f64_at(bytes, POLICY_AT + 12);
        let major_count = u32_at(bytes, COUNTS_AT);
        let (minor_count, labels_len, title_len, format_len) = (
            u32_at(bytes, COUNTS_AT + 4) as usize,
            u32_at(bytes, COUNTS_AT + 8) as usize,
            u32_at(bytes, COUNTS_AT + 12) as usize,
            u32_at(bytes, COUNTS_AT + 16) as usize,
        );
        let automatic = major_count == AUTO_COUNT;
        let majors = if automatic { 0 } else { major_count as usize };
        if majors > MAX_AXIS_TICKS
            || minor_count > MAX_AXIS_TICKS
            || labels_len > MAX_SCENE_TEXT_BYTES + MAX_AXIS_TICKS * 4 + 12
            || title_len > MAX_SCENE_TEXT_BYTES
            || format_len > MAX_SCENE_AXIS_FORMAT_BYTES
        {
            return Err(SceneError::Limit);
        }
        let values_end = SCENE_Y2_FIXED_BYTES + (majors + minor_count) * 8;
        let labels_end = values_end + labels_len;
        let title_end = labels_end + title_len;
        if bytes.len() != title_end + format_len {
            return Err(SceneError::Length);
        }
        let values = |from: usize, count: usize| -> Result<Vec<f64>, SceneError> {
            (0..count)
                .map(|index| {
                    let value = f64_at(bytes, from + index * 8);
                    value
                        .is_finite()
                        .then_some(value)
                        .ok_or(SceneError::NonFinite)
                })
                .collect()
        };
        let major_ticks = if automatic {
            None
        } else {
            Some(values(SCENE_Y2_FIXED_BYTES, majors)?)
        };
        let utf8 = |slice: &[u8]| {
            std::str::from_utf8(slice)
                .map(str::to_owned)
                .map_err(|_| SceneError::Length)
        };
        Self {
            scale,
            axis,
            major_ticks,
            minor_ticks: values(SCENE_Y2_FIXED_BYTES + majors * 8, minor_count)?,
            tick_labels: decode_tick_labels(&bytes[values_end..labels_end])?,
            title: utf8(&bytes[labels_end..title_end])?,
            format: utf8(&bytes[title_end..])?,
            tick_strategy: bytes[POLICY_AT],
            tick_anchor: if anchor_authored {
                bytes[POLICY_AT + 1]
            } else if bytes[POLICY_AT + 1] == 0 {
                tick_layout::ANCHOR_CENTER as u8
            } else {
                return Err(SceneError::Length);
            },
            tick_anchor_authored: anchor_authored,
            tick_category: flag(bytes[POLICY_AT + 3])?,
            tick_min_gap: f64_at(bytes, POLICY_AT + 4),
            tick_angle: angle.is_finite().then_some(angle),
        }
        .validated()
    }
}
