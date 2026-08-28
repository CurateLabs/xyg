//! Compact Figure→Scene chrome packing (M2 #271).
//!
//! Hosts pack authored title/labels, axis descriptors, ticks, XYCH, legend
//! loc/entries, colorbar literals, viewport, and optional padding/margins as
//! XYCF v1. Rust owns plot-layout vs authored margins, format suppression
//! when tick labels are present, chrome-style resolve, legend loc default and
//! allowlists, colorbar flags/framing, and XYTL tick-label framing so Python
//! and Node cannot drift on the encode-ready chrome bundle. Encoded Scene v31
//! is unchanged.

use crate::scene::{
    cartesian_scene_margins, encode_tick_labels, CartesianLayoutRequest, ColorbarSide, ScaleKind,
    SceneChromeStyle, MAX_AXIS_TICKS, MAX_SCENE_TEXT_BYTES, SCENE_CHROME_STYLE_INPUT_BYTES,
};
use crate::scene_colorbar::{self, ColorbarError, ColorbarFrameInput, ColorbarStop};
use crate::scene_legend::{self, LegendError, LegendFrameInput, LEGEND_META_BYTES};
use crate::scene_style::{self, MarkStyleError};

pub const XYCF_MAGIC: &[u8; 4] = b"XYCF";
pub const XYCF_VERSION: u32 = 1;
pub const XYCF_HEADER_BYTES: usize = 288;
pub const XYCC_MAGIC: &[u8; 4] = b"XYCC";
pub const XYCC_VERSION: u32 = 1;
pub const XYCC_HEADER_BYTES: usize = 160;

pub const FLAG_AUTHORED_MARGINS: u32 = 1 << 0;
pub const FLAG_PADDING: u32 = 1 << 1;
pub const FLAG_X_MAJOR_AUTO: u32 = 1 << 2;
pub const FLAG_Y_MAJOR_AUTO: u32 = 1 << 3;
pub const FLAG_X_TICK_LABELS: u32 = 1 << 4;
pub const FLAG_Y_TICK_LABELS: u32 = 1 << 5;
pub const FLAG_HAS_CHROME: u32 = 1 << 6;
pub const FLAG_HAS_LEGEND: u32 = 1 << 7;
pub const FLAG_HAS_COLORBAR: u32 = 1 << 8;

const LEGEND_AUTHORED_LOC: u32 = 1 << 0;
#[allow(dead_code)]
const LEGEND_AUTHORED_FONT: u32 = 1 << 1;
#[allow(dead_code)]
const LEGEND_AUTHORED_TITLE_FONT: u32 = 1 << 2;
#[allow(dead_code)]
const LEGEND_AUTHORED_COLOR: u32 = 1 << 3;
#[allow(dead_code)]
const LEGEND_AUTHORED_BACKGROUND: u32 = 1 << 4;
const LEGEND_UNSUPPORTED_KEYS: u32 = 1 << 5;
const LEGEND_TOGGLE: u32 = 1 << 6;
const LEGEND_HIGHLIGHT: u32 = 1 << 7;
const LEGEND_SHOW: u32 = 1 << 8;
const LEGEND_UNSUPPORTED_STYLE: u32 = 1 << 9;

const CB_HORIZONTAL: u32 = 1 << 1;
const CB_MINOR: u32 = 1 << 2;
const CB_UNSUPPORTED: u32 = 1 << 3;
const CB_INVALID_SIDE: u32 = 1 << 4;

const LEGEND_PACK_AUTHORED_LOC: u8 = 1 << 0;
const LEGEND_PACK_AUTHORED_FONT: u8 = 1 << 1;
const LEGEND_PACK_AUTHORED_TITLE_FONT: u8 = 1 << 2;
const LEGEND_PACK_AUTHORED_COLOR: u8 = 1 << 3;
const LEGEND_PACK_AUTHORED_BACKGROUND: u8 = 1 << 4;

/// Why an XYCF chrome request was rejected. Discriminants are the C-ABI
/// error codes (returned negated by `xyg_scene_pack_figure_chrome`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChromePackError {
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
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32, ChromePackError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(ChromePackError::Length)?
            .try_into()
            .map_err(|_| ChromePackError::Length)?,
    ))
}

fn read_f64(bytes: &[u8], offset: usize) -> Result<f64, ChromePackError> {
    Ok(f64::from_le_bytes(
        bytes
            .get(offset..offset + 8)
            .ok_or(ChromePackError::Length)?
            .try_into()
            .map_err(|_| ChromePackError::Length)?,
    ))
}

fn read_u8(bytes: &[u8], offset: usize) -> Result<u8, ChromePackError> {
    bytes.get(offset).copied().ok_or(ChromePackError::Length)
}

fn take<'a>(bytes: &'a [u8], at: &mut usize, len: usize) -> Result<&'a [u8], ChromePackError> {
    let start = *at;
    let end = start.checked_add(len).ok_or(ChromePackError::Limit)?;
    let slice = bytes.get(start..end).ok_or(ChromePackError::Length)?;
    *at = end;
    Ok(slice)
}

fn take_f64s(bytes: &[u8], at: &mut usize, count: usize) -> Result<Vec<f64>, ChromePackError> {
    if count > MAX_AXIS_TICKS {
        return Err(ChromePackError::Limit);
    }
    let raw = take(bytes, at, count.saturating_mul(8))?;
    let mut values = Vec::with_capacity(count);
    for chunk in raw.chunks_exact(8) {
        values.push(f64::from_le_bytes(chunk.try_into().unwrap()));
    }
    Ok(values)
}

fn take_labels(bytes: &[u8], at: &mut usize, count: usize) -> Result<Vec<String>, ChromePackError> {
    if count > MAX_AXIS_TICKS {
        return Err(ChromePackError::Limit);
    }
    let mut labels = Vec::with_capacity(count);
    for _ in 0..count {
        let len = u32::from_le_bytes(
            take(bytes, at, 4)?
                .try_into()
                .map_err(|_| ChromePackError::Length)?,
        ) as usize;
        if len == 0 || len > MAX_SCENE_TEXT_BYTES {
            return Err(ChromePackError::Limit);
        }
        let raw = take(bytes, at, len)?;
        let text = std::str::from_utf8(raw).map_err(|_| ChromePackError::Length)?;
        if text.contains('\0') {
            return Err(ChromePackError::Limit);
        }
        labels.push(text.to_owned());
    }
    Ok(labels)
}

fn utf8<'a>(bytes: &'a [u8]) -> Result<&'a str, ChromePackError> {
    std::str::from_utf8(bytes).map_err(|_| ChromePackError::Length)
}

fn scale_kind(code: u32) -> Result<ScaleKind, ChromePackError> {
    match code {
        0 => Ok(ScaleKind::Linear),
        1 => Ok(ScaleKind::Log),
        2 => Ok(ScaleKind::SymLog),
        _ => Err(ChromePackError::Payload),
    }
}

fn legend_loc(name: &[u8], authored: bool) -> Result<u8, ChromePackError> {
    if name.is_empty() {
        if authored {
            return Err(ChromePackError::LegendLoc);
        }
        return Ok(0);
    }
    let text = utf8(name)?;
    Ok(match text {
        "upper right" => 0,
        "upper left" => 1,
        "lower left" => 2,
        "lower right" => 3,
        "center right" => 4,
        "center left" => 5,
        "upper center" => 6,
        "lower center" => 7,
        "center" => 8,
        _ => return Err(ChromePackError::LegendLoc),
    })
}

fn resolve_chrome(bytes: &[u8]) -> Result<[u8; SCENE_CHROME_STYLE_INPUT_BYTES], ChromePackError> {
    if bytes.is_empty() {
        let default = SceneChromeStyle::default_style().style_input();
        let mut out = [0u8; SCENE_CHROME_STYLE_INPUT_BYTES];
        out.copy_from_slice(&default);
        return Ok(out);
    }
    if bytes.len() == SCENE_CHROME_STYLE_INPUT_BYTES && bytes.get(..4) != Some(&b"XYCH"[..]) {
        let mut out = [0u8; SCENE_CHROME_STYLE_INPUT_BYTES];
        out.copy_from_slice(bytes);
        return Ok(out);
    }
    match scene_style::resolve_chrome_style(bytes) {
        Ok(style) => Ok(style),
        Err(MarkStyleError::Version) => Err(ChromePackError::Version),
        Err(MarkStyleError::Limit) => Err(ChromePackError::Limit),
        Err(_) => Err(ChromePackError::Length),
    }
}

fn rgba4(bytes: &[u8]) -> Result<[u8; 4], ChromePackError> {
    bytes
        .try_into()
        .map_err(|_| ChromePackError::Length)
}

/// Pack authored XYCF v1 chrome facts into the XYCC v1 encode-ready bundle.
pub fn pack_figure_chrome(facts: &[u8]) -> Result<Vec<u8>, ChromePackError> {
    if facts.len() < XYCF_HEADER_BYTES {
        return Err(ChromePackError::Length);
    }
    if facts.get(..4) != Some(&XYCF_MAGIC[..]) {
        return Err(ChromePackError::Length);
    }
    if read_u32(facts, 4)? != XYCF_VERSION {
        return Err(ChromePackError::Version);
    }
    let flags = read_u32(facts, 8)?;
    let viewport_width = read_f64(facts, 16)?;
    let viewport_height = read_f64(facts, 24)?;
    let authored_margins = [
        read_f64(facts, 32)?,
        read_f64(facts, 40)?,
        read_f64(facts, 48)?,
        read_f64(facts, 56)?,
    ];
    let padding = [
        read_f64(facts, 64)?,
        read_f64(facts, 72)?,
        read_f64(facts, 80)?,
        read_f64(facts, 88)?,
    ];
    let x_kind = scale_kind(read_u32(facts, 96)?)?;
    let y_kind = scale_kind(read_u32(facts, 100)?)?;
    let x_lo = read_f64(facts, 104)?;
    let x_hi = read_f64(facts, 112)?;
    let x_constant = read_f64(facts, 120)?;
    let y_lo = read_f64(facts, 128)?;
    let y_hi = read_f64(facts, 136)?;
    let y_constant = read_f64(facts, 144)?;
    let x_mask = read_u8(facts, 152)? != 0;
    let y_mask = read_u8(facts, 153)? != 0;
    let title_len = read_u32(facts, 156)? as usize;
    let xlabel_len = read_u32(facts, 160)? as usize;
    let ylabel_len = read_u32(facts, 164)? as usize;
    let x_format_len = read_u32(facts, 168)? as usize;
    let y_format_len = read_u32(facts, 172)? as usize;
    let x_major_count = read_u32(facts, 176)? as usize;
    let x_minor_count = read_u32(facts, 180)? as usize;
    let y_major_count = read_u32(facts, 184)? as usize;
    let y_minor_count = read_u32(facts, 188)? as usize;
    let x_label_count = read_u32(facts, 192)? as usize;
    let y_label_count = read_u32(facts, 196)? as usize;
    let chrome_len = read_u32(facts, 200)? as usize;
    let legend_loc_len = read_u32(facts, 204)? as usize;
    let legend_title_len = read_u32(facts, 208)? as usize;
    let legend_ncols = read_u32(facts, 212)?;
    let legend_font_size = read_f64(facts, 216)?;
    let legend_title_font_size = read_f64(facts, 224)?;
    let legend_flags = read_u32(facts, 232)?;
    let legend_entry_count = read_u32(facts, 236)? as usize;
    let legend_text_rgba = rgba4(facts.get(240..244).ok_or(ChromePackError::Length)?)?;
    let legend_frame_rgba = rgba4(facts.get(244..248).ok_or(ChromePackError::Length)?)?;
    let colorbar_obs = read_u32(facts, 248)?;
    let colorbar_stop_count = read_u32(facts, 252)? as usize;
    let colorbar_tick_count = read_u32(facts, 256)? as usize;
    let colorbar_title_len = read_u32(facts, 260)? as usize;
    let colorbar_lo = read_f64(facts, 264)?;
    let colorbar_hi = read_f64(facts, 272)?;
    let colorbar_text_rgba = rgba4(facts.get(280..284).ok_or(ChromePackError::Length)?)?;

    if title_len > MAX_SCENE_TEXT_BYTES
        || xlabel_len > MAX_SCENE_TEXT_BYTES
        || ylabel_len > MAX_SCENE_TEXT_BYTES
        || x_format_len > 256
        || y_format_len > 256
    {
        return Err(ChromePackError::Limit);
    }
    if x_major_count > MAX_AXIS_TICKS
        || x_minor_count > MAX_AXIS_TICKS
        || y_major_count > MAX_AXIS_TICKS
        || y_minor_count > MAX_AXIS_TICKS
    {
        return Err(ChromePackError::Ticks);
    }

    let mut at = XYCF_HEADER_BYTES;
    let title = take(facts, &mut at, title_len)?;
    let xlabel = take(facts, &mut at, xlabel_len)?;
    let ylabel = take(facts, &mut at, ylabel_len)?;
    let x_format = take(facts, &mut at, x_format_len)?;
    let y_format = take(facts, &mut at, y_format_len)?;
    let x_major = take_f64s(facts, &mut at, x_major_count)?;
    let x_minor = take_f64s(facts, &mut at, x_minor_count)?;
    let y_major = take_f64s(facts, &mut at, y_major_count)?;
    let y_minor = take_f64s(facts, &mut at, y_minor_count)?;
    let x_tick_labels = if flags & FLAG_X_TICK_LABELS != 0 {
        Some(take_labels(facts, &mut at, x_label_count)?)
    } else {
        let _ = take_labels(facts, &mut at, x_label_count)?;
        None
    };
    let y_tick_labels = if flags & FLAG_Y_TICK_LABELS != 0 {
        Some(take_labels(facts, &mut at, y_label_count)?)
    } else {
        let _ = take_labels(facts, &mut at, y_label_count)?;
        None
    };
    let chrome_bytes = take(facts, &mut at, chrome_len)?;
    let legend_loc_bytes = take(facts, &mut at, legend_loc_len)?;
    let legend_title = take(facts, &mut at, legend_title_len)?;
    let legend_meta = take(
        facts,
        &mut at,
        legend_entry_count.saturating_mul(LEGEND_META_BYTES),
    )?;
    let mut legend_lens = Vec::with_capacity(legend_entry_count);
    let mut labels_len = 0usize;
    for _ in 0..legend_entry_count {
        let len = u32::from_le_bytes(
            take(facts, &mut at, 4)?
                .try_into()
                .map_err(|_| ChromePackError::Length)?,
        );
        labels_len = labels_len
            .checked_add(len as usize)
            .ok_or(ChromePackError::Limit)?;
        legend_lens.push(len);
    }
    let legend_labels = take(facts, &mut at, labels_len)?;
    let mut colorbar_stops = Vec::with_capacity(colorbar_stop_count);
    for _ in 0..colorbar_stop_count {
        let value = f64::from_le_bytes(
            take(facts, &mut at, 8)?
                .try_into()
                .map_err(|_| ChromePackError::Length)?,
        );
        let rgba = rgba4(take(facts, &mut at, 4)?)?;
        colorbar_stops.push(ColorbarStop { value, rgba });
    }
    let colorbar_ticks = take_f64s(facts, &mut at, colorbar_tick_count)?;
    let colorbar_title = take(facts, &mut at, colorbar_title_len)?;
    if at != facts.len() {
        return Err(ChromePackError::Length);
    }

    let title_text = utf8(title)?;
    let xlabel_text = utf8(xlabel)?;
    let ylabel_text = utf8(ylabel)?;
    if title_text.contains('\0') || xlabel_text.contains('\0') || ylabel_text.contains('\0') {
        return Err(ChromePackError::Limit);
    }
    let x_format_text = if x_format.is_empty() {
        None
    } else {
        let text = utf8(x_format)?;
        if text.contains('\0') {
            return Err(ChromePackError::Limit);
        }
        Some(text)
    };
    let y_format_text = if y_format.is_empty() {
        None
    } else {
        let text = utf8(y_format)?;
        if text.contains('\0') {
            return Err(ChromePackError::Limit);
        }
        Some(text)
    };

    let colorbar_side = if flags & FLAG_HAS_COLORBAR != 0 {
        if colorbar_obs & CB_UNSUPPORTED != 0 {
            return Err(ChromePackError::ColorbarKeys);
        }
        if colorbar_obs & CB_INVALID_SIDE != 0 {
            return Err(ChromePackError::ColorbarSide);
        }
        if colorbar_obs & CB_HORIZONTAL != 0 {
            ColorbarSide::Bottom
        } else {
            ColorbarSide::Right
        }
    } else {
        ColorbarSide::None
    };

    let margins = if flags & FLAG_AUTHORED_MARGINS != 0 {
        authored_margins
    } else {
        let layout_x_format = if flags & FLAG_X_TICK_LABELS != 0 {
            None
        } else {
            x_format_text
        };
        let layout_y_format = if flags & FLAG_Y_TICK_LABELS != 0 {
            None
        } else {
            y_format_text
        };
        let layout = cartesian_scene_margins(CartesianLayoutRequest {
            viewport_width,
            viewport_height,
            authored_padding: if flags & FLAG_PADDING != 0 {
                Some(padding)
            } else {
                None
            },
            title: title_text,
            x_label: xlabel_text,
            y_label: ylabel_text,
            x_kind,
            x_lo,
            x_hi,
            x_constant,
            x_mask_nonpositive: x_mask,
            x_format: layout_x_format,
            y_kind,
            y_lo,
            y_hi,
            y_constant,
            y_mask_nonpositive: y_mask,
            y_format: layout_y_format,
            colorbar_side,
        })
        .map_err(|_| ChromePackError::Layout)?;
        [layout.0, layout.1, layout.2, layout.3]
    };

    let chrome_style = if flags & FLAG_HAS_CHROME != 0 {
        resolve_chrome(chrome_bytes)?
    } else {
        resolve_chrome(&[])?
    };
    let x_labels = encode_tick_labels(x_tick_labels.as_deref()).map_err(|_| ChromePackError::Limit)?;
    let y_labels = encode_tick_labels(y_tick_labels.as_deref()).map_err(|_| ChromePackError::Limit)?;

    let legend = if flags & FLAG_HAS_LEGEND != 0
        && legend_flags & LEGEND_SHOW != 0
        && legend_entry_count > 0
    {
        if legend_flags & LEGEND_UNSUPPORTED_KEYS != 0 || legend_ncols != 1 {
            return Err(ChromePackError::LegendKeys);
        }
        if legend_flags & (LEGEND_TOGGLE | LEGEND_HIGHLIGHT) != 0 {
            return Err(ChromePackError::LegendStatic);
        }
        if legend_flags & LEGEND_UNSUPPORTED_STYLE != 0 {
            return Err(ChromePackError::LegendStyle);
        }
        let loc = legend_loc(legend_loc_bytes, legend_flags & LEGEND_AUTHORED_LOC != 0)?;
        let entries = scene_legend::entries_from_meta(legend_meta, &legend_lens, legend_labels)
            .map_err(|_| ChromePackError::Length)?;
        let pack_flags = (legend_flags & 0x1f) as u8
            & (LEGEND_PACK_AUTHORED_LOC
                | LEGEND_PACK_AUTHORED_FONT
                | LEGEND_PACK_AUTHORED_TITLE_FONT
                | LEGEND_PACK_AUTHORED_COLOR
                | LEGEND_PACK_AUTHORED_BACKGROUND);
        match scene_legend::pack_legend(LegendFrameInput {
            loc,
            flags: pack_flags,
            font_size: legend_font_size,
            title_font_size: legend_title_font_size,
            text_rgba: legend_text_rgba,
            frame_fill_rgba: legend_frame_rgba,
            title: legend_title,
            entries: &entries,
        }) {
            Ok(bytes) => bytes,
            Err(LegendError::Font) => return Err(ChromePackError::LegendFont),
            Err(LegendError::Location) => return Err(ChromePackError::LegendLoc),
            Err(LegendError::Limit) => return Err(ChromePackError::Limit),
            Err(_) => return Err(ChromePackError::Length),
        }
    } else {
        Vec::new()
    };

    let colorbar = if flags & FLAG_HAS_COLORBAR != 0 {
        if colorbar_stop_count < 2 || colorbar_stop_count > 16 {
            return Err(ChromePackError::ColorbarShape);
        }
        let mut flags = 0u8;
        if colorbar_obs & CB_HORIZONTAL != 0 {
            flags |= 1;
        }
        if colorbar_obs & CB_MINOR != 0 {
            flags |= 1 << 2;
        }
        match scene_colorbar::pack_colorbar(ColorbarFrameInput {
            flags,
            lo: colorbar_lo,
            hi: colorbar_hi,
            text_rgba: colorbar_text_rgba,
            title: colorbar_title,
            stops: &colorbar_stops,
            ticks: &colorbar_ticks,
        }) {
            Ok(bytes) => bytes,
            Err(ColorbarError::NonFinite | ColorbarError::Order) => {
                return Err(ChromePackError::ColorbarShape)
            }
            Err(ColorbarError::Ticks) => return Err(ChromePackError::Limit),
            Err(ColorbarError::Limit) => return Err(ChromePackError::Limit),
            Err(_) => return Err(ChromePackError::Length),
        }
    } else {
        Vec::new()
    };

    let x_major_auto = u32::from(flags & FLAG_X_MAJOR_AUTO != 0);
    let y_major_auto = u32::from(flags & FLAG_Y_MAJOR_AUTO != 0);
    let total = XYCC_HEADER_BYTES
        .checked_add(SCENE_CHROME_STYLE_INPUT_BYTES)
        .and_then(|value| value.checked_add(title_len))
        .and_then(|value| value.checked_add(xlabel_len))
        .and_then(|value| value.checked_add(ylabel_len))
        .and_then(|value| value.checked_add(x_major.len().saturating_mul(8)))
        .and_then(|value| value.checked_add(x_minor.len().saturating_mul(8)))
        .and_then(|value| value.checked_add(y_major.len().saturating_mul(8)))
        .and_then(|value| value.checked_add(y_minor.len().saturating_mul(8)))
        .and_then(|value| value.checked_add(x_labels.len()))
        .and_then(|value| value.checked_add(y_labels.len()))
        .and_then(|value| value.checked_add(x_format_len))
        .and_then(|value| value.checked_add(y_format_len))
        .and_then(|value| value.checked_add(legend.len()))
        .and_then(|value| value.checked_add(colorbar.len()))
        .ok_or(ChromePackError::Limit)?;
    let mut out = vec![0u8; total];
    out[..4].copy_from_slice(XYCC_MAGIC);
    out[4..8].copy_from_slice(&XYCC_VERSION.to_le_bytes());
    out[16..24].copy_from_slice(&margins[0].to_le_bytes());
    out[24..32].copy_from_slice(&margins[1].to_le_bytes());
    out[32..40].copy_from_slice(&margins[2].to_le_bytes());
    out[40..48].copy_from_slice(&margins[3].to_le_bytes());
    let lens: [u32; 16] = [
        SCENE_CHROME_STYLE_INPUT_BYTES as u32,
        title_len as u32,
        xlabel_len as u32,
        ylabel_len as u32,
        x_major.len() as u32,
        x_major_auto,
        x_minor.len() as u32,
        y_major.len() as u32,
        y_major_auto,
        y_minor.len() as u32,
        x_labels.len() as u32,
        y_labels.len() as u32,
        x_format_len as u32,
        y_format_len as u32,
        legend.len() as u32,
        colorbar.len() as u32,
    ];
    for (index, value) in lens.iter().enumerate() {
        let at = 48 + index * 4;
        out[at..at + 4].copy_from_slice(&value.to_le_bytes());
    }
    let mut write = XYCC_HEADER_BYTES;
    out[write..write + SCENE_CHROME_STYLE_INPUT_BYTES].copy_from_slice(&chrome_style);
    write += SCENE_CHROME_STYLE_INPUT_BYTES;
    out[write..write + title_len].copy_from_slice(title);
    write += title_len;
    out[write..write + xlabel_len].copy_from_slice(xlabel);
    write += xlabel_len;
    out[write..write + ylabel_len].copy_from_slice(ylabel);
    write += ylabel_len;
    for value in x_major.iter().chain(&x_minor).chain(&y_major).chain(&y_minor) {
        out[write..write + 8].copy_from_slice(&value.to_le_bytes());
        write += 8;
    }
    out[write..write + x_labels.len()].copy_from_slice(&x_labels);
    write += x_labels.len();
    out[write..write + y_labels.len()].copy_from_slice(&y_labels);
    write += y_labels.len();
    out[write..write + x_format_len].copy_from_slice(x_format);
    write += x_format_len;
    out[write..write + y_format_len].copy_from_slice(y_format);
    write += y_format_len;
    out[write..write + legend.len()].copy_from_slice(&legend);
    write += legend.len();
    out[write..write + colorbar.len()].copy_from_slice(&colorbar);
    write += colorbar.len();
    debug_assert_eq!(write, total);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn header(
        flags: u32,
        width: f64,
        height: f64,
        x_kind: u32,
        y_kind: u32,
    ) -> Vec<u8> {
        let mut out = vec![0u8; XYCF_HEADER_BYTES];
        out[..4].copy_from_slice(XYCF_MAGIC);
        out[4..8].copy_from_slice(&XYCF_VERSION.to_le_bytes());
        out[8..12].copy_from_slice(&flags.to_le_bytes());
        out[16..24].copy_from_slice(&width.to_le_bytes());
        out[24..32].copy_from_slice(&height.to_le_bytes());
        out[96..100].copy_from_slice(&x_kind.to_le_bytes());
        out[100..104].copy_from_slice(&y_kind.to_le_bytes());
        out[104..112].copy_from_slice(&0.0f64.to_le_bytes());
        out[112..120].copy_from_slice(&1.0f64.to_le_bytes());
        out[120..128].copy_from_slice(&1.0f64.to_le_bytes());
        out[128..136].copy_from_slice(&0.0f64.to_le_bytes());
        out[136..144].copy_from_slice(&1.0f64.to_le_bytes());
        out[144..152].copy_from_slice(&1.0f64.to_le_bytes());
        out[212..216].copy_from_slice(&1u32.to_le_bytes());
        out
    }

    #[test]
    fn empty_chrome_facts_emit_xycc_and_rust_margins() {
        let facts = header(FLAG_X_MAJOR_AUTO | FLAG_Y_MAJOR_AUTO, 400.0, 300.0, 0, 0);
        let packed = pack_figure_chrome(&facts).unwrap();
        assert_eq!(&packed[..4], XYCC_MAGIC);
        assert_eq!(u32::from_le_bytes(packed[4..8].try_into().unwrap()), 1);
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
        assert_eq!(f64::from_le_bytes(packed[16..24].try_into().unwrap()), expected.0);
        assert_eq!(f64::from_le_bytes(packed[24..32].try_into().unwrap()), expected.1);
        assert_eq!(f64::from_le_bytes(packed[32..40].try_into().unwrap()), expected.2);
        assert_eq!(f64::from_le_bytes(packed[40..48].try_into().unwrap()), expected.3);
        assert_eq!(
            u32::from_le_bytes(packed[48..52].try_into().unwrap()) as usize,
            SCENE_CHROME_STYLE_INPUT_BYTES
        );
        assert_eq!(u32::from_le_bytes(packed[68..72].try_into().unwrap()), 1);
        assert_eq!(u32::from_le_bytes(packed[80..84].try_into().unwrap()), 1);
    }

    #[test]
    fn authored_margins_bypass_layout() {
        let mut facts = header(
            FLAG_AUTHORED_MARGINS | FLAG_X_MAJOR_AUTO | FLAG_Y_MAJOR_AUTO,
            200.0,
            120.0,
            0,
            0,
        );
        facts[32..40].copy_from_slice(&11.0f64.to_le_bytes());
        facts[40..48].copy_from_slice(&12.0f64.to_le_bytes());
        facts[48..56].copy_from_slice(&13.0f64.to_le_bytes());
        facts[56..64].copy_from_slice(&14.0f64.to_le_bytes());
        let packed = pack_figure_chrome(&facts).unwrap();
        assert_eq!(f64::from_le_bytes(packed[16..24].try_into().unwrap()), 11.0);
        assert_eq!(f64::from_le_bytes(packed[24..32].try_into().unwrap()), 12.0);
        assert_eq!(f64::from_le_bytes(packed[32..40].try_into().unwrap()), 13.0);
        assert_eq!(f64::from_le_bytes(packed[40..48].try_into().unwrap()), 14.0);
    }

    #[test]
    fn unknown_legend_loc_is_payload() {
        let mut facts = header(
            FLAG_HAS_LEGEND | FLAG_X_MAJOR_AUTO | FLAG_Y_MAJOR_AUTO,
            200.0,
            120.0,
            0,
            0,
        );
        facts[204..208].copy_from_slice(&4u32.to_le_bytes());
        facts[232..236].copy_from_slice(&(LEGEND_SHOW | LEGEND_AUTHORED_LOC).to_le_bytes());
        facts[236..240].copy_from_slice(&1u32.to_le_bytes());
        let mut payload = facts;
        payload.extend_from_slice(b"best");
        payload.extend_from_slice(&[0u8; LEGEND_META_BYTES]);
        payload.extend_from_slice(&1u32.to_le_bytes());
        payload.extend_from_slice(b"a");
        assert_eq!(
            pack_figure_chrome(&payload),
            Err(ChromePackError::LegendLoc)
        );
    }

    #[test]
    fn empty_authored_legend_loc_is_rejected() {
        let mut facts = header(
            FLAG_HAS_LEGEND | FLAG_X_MAJOR_AUTO | FLAG_Y_MAJOR_AUTO,
            200.0,
            120.0,
            0,
            0,
        );
        facts[232..236].copy_from_slice(&(LEGEND_SHOW | LEGEND_AUTHORED_LOC).to_le_bytes());
        facts[236..240].copy_from_slice(&1u32.to_le_bytes());
        let mut payload = facts;
        payload.extend_from_slice(&[0u8; LEGEND_META_BYTES]);
        payload.extend_from_slice(&1u32.to_le_bytes());
        payload.extend_from_slice(b"a");
        assert_eq!(
            pack_figure_chrome(&payload),
            Err(ChromePackError::LegendLoc)
        );
    }

    #[test]
    fn axis_tick_overflow_is_ticks() {
        let mut facts = header(FLAG_Y_MAJOR_AUTO, 200.0, 120.0, 0, 0);
        facts[176..180].copy_from_slice(&201u32.to_le_bytes());
        assert_eq!(pack_figure_chrome(&facts), Err(ChromePackError::Ticks));
    }

    #[test]
    fn extra_legend_keys_fail_closed() {
        let mut facts = header(
            FLAG_HAS_LEGEND | FLAG_X_MAJOR_AUTO | FLAG_Y_MAJOR_AUTO,
            200.0,
            120.0,
            0,
            0,
        );
        facts[232..236].copy_from_slice(&(LEGEND_SHOW | LEGEND_UNSUPPORTED_KEYS).to_le_bytes());
        facts[236..240].copy_from_slice(&1u32.to_le_bytes());
        let mut payload = facts;
        payload.extend_from_slice(&[0u8; LEGEND_META_BYTES]);
        payload.extend_from_slice(&1u32.to_le_bytes());
        payload.extend_from_slice(b"a");
        assert_eq!(
            pack_figure_chrome(&payload),
            Err(ChromePackError::LegendKeys)
        );
    }
}
