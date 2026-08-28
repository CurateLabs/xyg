//! Compact Figure→Scene trace-sidecar packing (M2 #271).
//!
//! Hosts pack authored legend names as XYNM v1 against an XYTT attach
//! bundle. Rust owns legend-name gating (`legend_include` and a nonempty
//! name), heatmap-vs-density paint-plane selection, and per-trace
//! style/dash/linecap/marker/gradient extraction so Python and Node cannot
//! drift. Encoded Scene v31 is unchanged. ABI 158 packs XYSS from XYSD plus
//! XYAO; ABI 159 splices annotation styles and mark rows into XYAS. ABI 161
//! unpacks XYSD legend paints and heatmap/density planes so hosts do not
//! inspect sidecar contents on the product path. ABI 166 copies cartesian
//! bar/column/histogram `corner_radius` from the XYTO reserved trailer into
//! an optional XYSD radius blob so encode can tessellate rounded Rects.

use crate::scene_trace_attach::{XYTT_HEADER_BYTES, XYTT_MAGIC, XYTT_PREFIX_BYTES, XYTT_VERSION};
use crate::scene_trace_compile::XYTO_MAGIC;

pub const XYNM_MAGIC: &[u8; 4] = b"XYNM";
pub const XYNM_VERSION: u32 = 1;
pub const XYNM_HEADER_BYTES: usize = 16;
pub const XYSD_MAGIC: &[u8; 4] = b"XYSD";
pub const XYSD_VERSION: u32 = 1;
pub const XYSD_HEADER_BYTES: usize = 16;
pub const XYSD_PREFIX_BYTES: usize = 48;
pub const XYSD_RADIUS_BYTES: usize = 24;

const MAX_TRACES: usize = 4_096;
const MAX_NAME: usize = 4_096;

/// Why an XYNM sidecar-pack request was rejected. Discriminants are the
/// C-ABI error codes (returned negated by `xyg_scene_pack_trace_sidecars`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TraceSidecarsCode {
    Length = 1,
    Version = 2,
    Limit = 3,
    Output = 4,
    TraceCount = 5,
    Name = 6,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TraceSidecarsError {
    pub code: TraceSidecarsCode,
    pub index: u32,
}

impl TraceSidecarsError {
    fn new(code: TraceSidecarsCode, index: usize) -> Self {
        Self {
            code,
            index: index as u32,
        }
    }
}

struct AttachedSidecar {
    fill: [u8; 4],
    stroke: [u8; 4],
    stroke_width: f64,
    legend_kind: u8,
    legend_include: bool,
    legend_symbol: u16,
    linecap: u8,
    dash: Vec<u8>,
    marker: Vec<u8>,
    gradient: Vec<u8>,
    plane: Vec<u8>,
    r_tip: f64,
    r_base: f64,
    tip_policy: u8,
}

fn read_u16(bytes: &[u8], offset: usize) -> Result<u16, TraceSidecarsError> {
    Ok(u16::from_le_bytes(
        bytes
            .get(offset..offset + 2)
            .ok_or(TraceSidecarsError::new(TraceSidecarsCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, 0))?,
    ))
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32, TraceSidecarsError> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or(TraceSidecarsError::new(TraceSidecarsCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, 0))?,
    ))
}

fn read_f64(bytes: &[u8], offset: usize) -> Result<f64, TraceSidecarsError> {
    Ok(f64::from_le_bytes(
        bytes
            .get(offset..offset + 8)
            .ok_or(TraceSidecarsError::new(TraceSidecarsCode::Length, 0))?
            .try_into()
            .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, 0))?,
    ))
}

fn read_rgba(bytes: &[u8], offset: usize) -> Result<[u8; 4], TraceSidecarsError> {
    Ok(bytes
        .get(offset..offset + 4)
        .ok_or(TraceSidecarsError::new(TraceSidecarsCode::Length, 0))?
        .try_into()
        .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, 0))?)
}

fn take(rest: &mut &[u8], n: usize, index: usize) -> Result<Vec<u8>, TraceSidecarsError> {
    if rest.len() < n {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Length, index));
    }
    let (head, tail) = rest.split_at(n);
    *rest = tail;
    Ok(head.to_vec())
}

fn encode_radius_blob(r_tip: f64, r_base: f64, tip_policy: u8) -> Vec<u8> {
    if r_tip == 0.0 && r_base == 0.0 {
        return Vec::new();
    }
    let mut out = vec![0u8; XYSD_RADIUS_BYTES];
    out[0..8].copy_from_slice(&r_tip.to_le_bytes());
    out[8..16].copy_from_slice(&r_base.to_le_bytes());
    out[16] = tip_policy;
    out
}

fn parse_radius_blob(blob: &[u8], index: usize) -> Result<(f64, f64, u8), TraceSidecarsError> {
    if blob.is_empty() {
        return Ok((0.0, 0.0, 0));
    }
    if blob.len() != XYSD_RADIUS_BYTES {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Length, index));
    }
    let r_tip = f64::from_le_bytes(
        blob[0..8]
            .try_into()
            .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, index))?,
    );
    let r_base = f64::from_le_bytes(
        blob[8..16]
            .try_into()
            .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, index))?,
    );
    if !r_tip.is_finite() || !r_base.is_finite() || r_tip < 0.0 || r_base < 0.0 {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Length, index));
    }
    Ok((r_tip, r_base, blob[16]))
}

fn parse_xytt(bytes: &[u8]) -> Result<Vec<AttachedSidecar>, TraceSidecarsError> {
    if bytes.len() < XYTT_HEADER_BYTES || bytes.get(..4) != Some(&XYTT_MAGIC[..]) {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Length, 0));
    }
    if read_u32(bytes, 4)? != XYTT_VERSION {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Version, 0));
    }
    let n_traces = read_u32(bytes, 8)? as usize;
    if n_traces > MAX_TRACES {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Limit, 0));
    }
    let mut rest = bytes
        .get(XYTT_HEADER_BYTES..)
        .ok_or(TraceSidecarsError::new(TraceSidecarsCode::Length, 0))?;
    let mut traces = Vec::with_capacity(n_traces);
    for index in 0..n_traces {
        if rest.len() < XYTT_PREFIX_BYTES {
            return Err(TraceSidecarsError::new(TraceSidecarsCode::Length, index));
        }
        if rest.get(..4) != Some(&XYTO_MAGIC[..]) {
            return Err(TraceSidecarsError::new(TraceSidecarsCode::Length, index));
        }
        let fill = read_rgba(rest, 8)?;
        let stroke = read_rgba(rest, 12)?;
        let stroke_width = read_f64(rest, 16)?;
        let legend_kind = rest[34];
        let legend_include = rest[35] != 0;
        let legend_symbol = read_u16(rest, 36)?;
        let dash_count = read_u32(rest, 44)? as usize;
        let linecap = rest[48];
        let has_marker = rest[49] != 0;
        let has_gradient = rest[50] != 0;
        let marker_len = read_u32(rest, 52)? as usize;
        let gradient_len = read_u32(rest, 56)? as usize;
        let heatmap_len = read_u32(rest, 160)? as usize;
        let density_len = read_u32(rest, 164)? as usize;
        let r_tip = read_f64(rest, 76)?;
        let r_base = read_f64(rest, 84)?;
        let tip_policy = rest[92];
        rest = &rest[XYTT_PREFIX_BYTES..];
        let dash_bytes = dash_count
            .checked_mul(8)
            .ok_or(TraceSidecarsError::new(TraceSidecarsCode::Limit, index))?;
        let dash = take(&mut rest, dash_bytes, index)?;
        let marker_raw = take(&mut rest, marker_len, index)?;
        let gradient_raw = take(&mut rest, gradient_len, index)?;
        let heatmap = take(&mut rest, heatmap_len, index)?;
        let density = take(&mut rest, density_len, index)?;
        let marker = if has_marker { marker_raw } else { Vec::new() };
        let gradient = if has_gradient {
            gradient_raw
        } else {
            Vec::new()
        };
        let plane = if !heatmap.is_empty() {
            heatmap
        } else {
            density
        };
        traces.push(AttachedSidecar {
            fill,
            stroke,
            stroke_width,
            legend_kind,
            legend_include,
            legend_symbol,
            linecap,
            dash,
            marker,
            gradient,
            plane,
            r_tip,
            r_base,
            tip_policy,
        });
    }
    if !rest.is_empty() {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Length, 0));
    }
    Ok(traces)
}

fn parse_xynm(bytes: &[u8]) -> Result<Vec<Vec<u8>>, TraceSidecarsError> {
    if bytes.len() < XYNM_HEADER_BYTES || bytes.get(..4) != Some(&XYNM_MAGIC[..]) {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Length, 0));
    }
    if read_u32(bytes, 4)? != XYNM_VERSION {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Version, 0));
    }
    let n_traces = read_u32(bytes, 8)? as usize;
    if n_traces > MAX_TRACES {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Limit, 0));
    }
    let mut rest = bytes
        .get(XYNM_HEADER_BYTES..)
        .ok_or(TraceSidecarsError::new(TraceSidecarsCode::Length, 0))?;
    let mut names = Vec::with_capacity(n_traces);
    for index in 0..n_traces {
        if rest.len() < 2 {
            return Err(TraceSidecarsError::new(TraceSidecarsCode::Length, index));
        }
        let name_len = u16::from_le_bytes(rest[..2].try_into().unwrap()) as usize;
        rest = &rest[2..];
        if name_len > MAX_NAME {
            return Err(TraceSidecarsError::new(TraceSidecarsCode::Limit, index));
        }
        let raw = take(&mut rest, name_len, index)?;
        if std::str::from_utf8(&raw).is_err() {
            return Err(TraceSidecarsError::new(TraceSidecarsCode::Name, index));
        }
        names.push(raw);
    }
    if !rest.is_empty() {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Length, 0));
    }
    Ok(names)
}

/// One XYSD v1 per-trace record used by ABI 161 chrome/extras packing.
#[derive(Clone, Debug)]
pub struct XySdRecord {
    pub fill: [u8; 4],
    pub stroke: [u8; 4],
    pub stroke_width: f64,
    pub linecap: u8,
    pub legend_kind: u8,
    pub legend_symbol: u16,
    pub dash: Vec<u8>,
    pub marker: Vec<u8>,
    pub gradient: Vec<u8>,
    pub plane: Vec<u8>,
    pub name: Vec<u8>,
    pub r_tip: f64,
    pub r_base: f64,
    pub tip_policy: u8,
}

/// Parse packed `XYSD` v1 into per-trace style, plane, and legend-name records.
pub fn parse_xysd_records(bytes: &[u8]) -> Result<Vec<XySdRecord>, TraceSidecarsError> {
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if bytes.len() < XYSD_HEADER_BYTES || bytes.get(..4) != Some(&XYSD_MAGIC[..]) {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Length, 0));
    }
    if read_u32(bytes, 4)? != XYSD_VERSION {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Version, 0));
    }
    let n_traces = read_u32(bytes, 8)? as usize;
    if n_traces > MAX_TRACES {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Limit, 0));
    }
    let mut rest = bytes
        .get(XYSD_HEADER_BYTES..)
        .ok_or(TraceSidecarsError::new(TraceSidecarsCode::Length, 0))?;
    let mut records = Vec::with_capacity(n_traces);
    for index in 0..n_traces {
        let prefix = take(&mut rest, XYSD_PREFIX_BYTES, index)?;
        let fill: [u8; 4] = prefix[0..4]
            .try_into()
            .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, index))?;
        let stroke: [u8; 4] = prefix[4..8]
            .try_into()
            .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, index))?;
        let stroke_width = f64::from_le_bytes(
            prefix[8..16]
                .try_into()
                .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, index))?,
        );
        let linecap = prefix[16];
        let legend_kind = prefix[17];
        let legend_symbol = u16::from_le_bytes(
            prefix[18..20]
                .try_into()
                .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, index))?,
        );
        let dash_len = u32::from_le_bytes(
            prefix[20..24]
                .try_into()
                .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, index))?,
        ) as usize;
        let marker_len = u32::from_le_bytes(
            prefix[24..28]
                .try_into()
                .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, index))?,
        ) as usize;
        let gradient_len = u32::from_le_bytes(
            prefix[28..32]
                .try_into()
                .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, index))?,
        ) as usize;
        let plane_len = u32::from_le_bytes(
            prefix[32..36]
                .try_into()
                .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, index))?,
        ) as usize;
        let name_len = u32::from_le_bytes(
            prefix[36..40]
                .try_into()
                .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, index))?,
        ) as usize;
        let radius_len = u32::from_le_bytes(
            prefix[40..44]
                .try_into()
                .map_err(|_| TraceSidecarsError::new(TraceSidecarsCode::Length, index))?,
        ) as usize;
        let dash = take(&mut rest, dash_len, index)?;
        let marker = take(&mut rest, marker_len, index)?;
        let gradient = take(&mut rest, gradient_len, index)?;
        let plane = take(&mut rest, plane_len, index)?;
        let name = take(&mut rest, name_len, index)?;
        let radius = take(&mut rest, radius_len, index)?;
        let (r_tip, r_base, tip_policy) = parse_radius_blob(&radius, index)?;
        records.push(XySdRecord {
            fill,
            stroke,
            stroke_width,
            linecap,
            legend_kind,
            legend_symbol,
            dash,
            marker,
            gradient,
            plane,
            name,
            r_tip,
            r_base,
            tip_policy,
        });
    }
    if !rest.is_empty() {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::Length, 0));
    }
    Ok(records)
}

fn write_sidecar(out: &mut Vec<u8>, attached: &AttachedSidecar, name: &[u8]) {
    let legend_name = if attached.legend_include && !name.is_empty() {
        name
    } else {
        &[]
    };
    let mut prefix = vec![0u8; XYSD_PREFIX_BYTES];
    prefix[0..4].copy_from_slice(&attached.fill);
    prefix[4..8].copy_from_slice(&attached.stroke);
    prefix[8..16].copy_from_slice(&attached.stroke_width.to_le_bytes());
    prefix[16] = attached.linecap;
    prefix[17] = attached.legend_kind;
    prefix[18..20].copy_from_slice(&attached.legend_symbol.to_le_bytes());
    prefix[20..24].copy_from_slice(&(attached.dash.len() as u32).to_le_bytes());
    prefix[24..28].copy_from_slice(&(attached.marker.len() as u32).to_le_bytes());
    prefix[28..32].copy_from_slice(&(attached.gradient.len() as u32).to_le_bytes());
    prefix[32..36].copy_from_slice(&(attached.plane.len() as u32).to_le_bytes());
    prefix[36..40].copy_from_slice(&(legend_name.len() as u32).to_le_bytes());
    let radius = encode_radius_blob(attached.r_tip, attached.r_base, attached.tip_policy);
    prefix[40..44].copy_from_slice(&(radius.len() as u32).to_le_bytes());
    out.extend_from_slice(&prefix);
    out.extend_from_slice(&attached.dash);
    out.extend_from_slice(&attached.marker);
    out.extend_from_slice(&attached.gradient);
    out.extend_from_slice(&attached.plane);
    out.extend_from_slice(legend_name);
    out.extend_from_slice(&radius);
}

/// Pack attached `XYTT` v1 plus authored `XYNM` v1 names into `XYSD` v1.
pub fn pack_trace_sidecars(attached: &[u8], names: &[u8]) -> Result<Vec<u8>, TraceSidecarsError> {
    let traces = parse_xytt(attached)?;
    let labels = parse_xynm(names)?;
    if traces.len() != labels.len() {
        return Err(TraceSidecarsError::new(TraceSidecarsCode::TraceCount, 0));
    }
    let mut out = Vec::new();
    out.extend_from_slice(XYSD_MAGIC);
    out.extend_from_slice(&XYSD_VERSION.to_le_bytes());
    out.extend_from_slice(&(traces.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for (trace, name) in traces.iter().zip(labels.iter()) {
        write_sidecar(&mut out, trace, name);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    const LINECAP_NONE: u8 = 255;

    fn xynm(names: &[&str]) -> Vec<u8> {
        let mut out = vec![0u8; XYNM_HEADER_BYTES];
        out[..4].copy_from_slice(XYNM_MAGIC);
        out[4..8].copy_from_slice(&XYNM_VERSION.to_le_bytes());
        out[8..12].copy_from_slice(&(names.len() as u32).to_le_bytes());
        for name in names {
            let raw = name.as_bytes();
            out.extend_from_slice(&(raw.len() as u16).to_le_bytes());
            out.extend_from_slice(raw);
        }
        out
    }

    fn empty_xytt() -> Vec<u8> {
        let mut out = vec![0u8; XYTT_HEADER_BYTES];
        out[..4].copy_from_slice(XYTT_MAGIC);
        out[4..8].copy_from_slice(&XYTT_VERSION.to_le_bytes());
        out
    }

    #[allow(clippy::too_many_arguments)]
    fn pack_xytt_one(
        fill: [u8; 4],
        stroke: [u8; 4],
        stroke_width: f64,
        legend_kind: u8,
        legend_include: u8,
        legend_symbol: u16,
        dash: &[f64],
        linecap: u8,
        marker: &[u8],
        gradient: &[u8],
        heatmap: &[u8],
        density: &[u8],
    ) -> Vec<u8> {
        let mut prefix = vec![0u8; XYTT_PREFIX_BYTES];
        prefix[..4].copy_from_slice(XYTO_MAGIC);
        prefix[4..6].copy_from_slice(&1u16.to_le_bytes());
        prefix[8..12].copy_from_slice(&fill);
        prefix[12..16].copy_from_slice(&stroke);
        prefix[16..24].copy_from_slice(&stroke_width.to_le_bytes());
        prefix[34] = legend_kind;
        prefix[35] = legend_include;
        prefix[36..38].copy_from_slice(&legend_symbol.to_le_bytes());
        prefix[44..48].copy_from_slice(&(dash.len() as u32).to_le_bytes());
        prefix[48] = linecap;
        prefix[49] = u8::from(!marker.is_empty());
        prefix[50] = u8::from(!gradient.is_empty());
        prefix[52..56].copy_from_slice(&(marker.len() as u32).to_le_bytes());
        prefix[56..60].copy_from_slice(&(gradient.len() as u32).to_le_bytes());
        prefix[160..164].copy_from_slice(&(heatmap.len() as u32).to_le_bytes());
        prefix[164..168].copy_from_slice(&(density.len() as u32).to_le_bytes());
        let mut out = vec![0u8; XYTT_HEADER_BYTES];
        out[..4].copy_from_slice(XYTT_MAGIC);
        out[4..8].copy_from_slice(&XYTT_VERSION.to_le_bytes());
        out[8..12].copy_from_slice(&1u32.to_le_bytes());
        out.extend_from_slice(&prefix);
        for value in dash {
            out.extend_from_slice(&value.to_le_bytes());
        }
        out.extend_from_slice(marker);
        out.extend_from_slice(gradient);
        out.extend_from_slice(heatmap);
        out.extend_from_slice(density);
        out
    }

    fn plane_of(packed: &[u8]) -> Vec<u8> {
        let dash_len = u32::from_le_bytes(packed[16 + 20..16 + 24].try_into().unwrap()) as usize;
        let marker_len = u32::from_le_bytes(packed[16 + 24..16 + 28].try_into().unwrap()) as usize;
        let gradient_len =
            u32::from_le_bytes(packed[16 + 28..16 + 32].try_into().unwrap()) as usize;
        let plane_len = u32::from_le_bytes(packed[16 + 32..16 + 36].try_into().unwrap()) as usize;
        let start = 16 + XYSD_PREFIX_BYTES + dash_len + marker_len + gradient_len;
        packed[start..start + plane_len].to_vec()
    }

    fn name_of(packed: &[u8]) -> Vec<u8> {
        let dash_len = u32::from_le_bytes(packed[16 + 20..16 + 24].try_into().unwrap()) as usize;
        let marker_len = u32::from_le_bytes(packed[16 + 24..16 + 28].try_into().unwrap()) as usize;
        let gradient_len =
            u32::from_le_bytes(packed[16 + 28..16 + 32].try_into().unwrap()) as usize;
        let plane_len = u32::from_le_bytes(packed[16 + 32..16 + 36].try_into().unwrap()) as usize;
        let name_len = u32::from_le_bytes(packed[16 + 36..16 + 40].try_into().unwrap()) as usize;
        let start = 16 + XYSD_PREFIX_BYTES + dash_len + marker_len + gradient_len + plane_len;
        packed[start..start + name_len].to_vec()
    }

    #[test]
    fn empty_sidecars_emit_xysd() {
        let packed = pack_trace_sidecars(&empty_xytt(), &xynm(&[])).unwrap();
        assert_eq!(&packed[..4], XYSD_MAGIC);
        assert_eq!(u32::from_le_bytes(packed[8..12].try_into().unwrap()), 0);
        assert_eq!(packed.len(), XYSD_HEADER_BYTES);
    }

    #[test]
    fn scatter_copies_style_dash_and_legend() {
        let attached = pack_xytt_one(
            [0x11, 0x22, 0x33, 0xff],
            [0x44, 0x55, 0x66, 0xff],
            2.5,
            1,
            1,
            3,
            &[1.0, 2.0],
            1,
            b"M0 0",
            &[0xab; 16],
            &[],
            &[],
        );
        let packed = pack_trace_sidecars(&attached, &xynm(&["alpha"])).unwrap();
        assert_eq!(&packed[..4], XYSD_MAGIC);
        assert_eq!(u32::from_le_bytes(packed[8..12].try_into().unwrap()), 1);
        assert_eq!(&packed[16..20], &[0x11, 0x22, 0x33, 0xff]);
        assert_eq!(&packed[20..24], &[0x44, 0x55, 0x66, 0xff]);
        assert_eq!(f64::from_le_bytes(packed[24..32].try_into().unwrap()), 2.5);
        assert_eq!(packed[32], 1);
        assert_eq!(packed[33], 1);
        assert_eq!(u16::from_le_bytes(packed[34..36].try_into().unwrap()), 3);
        assert_eq!(name_of(&packed), b"alpha");
        let dash_len = u32::from_le_bytes(packed[36..40].try_into().unwrap());
        assert_eq!(dash_len, 16);
        let records = parse_xysd_records(&packed).unwrap();
        assert_eq!(records.len(), 1);
        assert_eq!(records[0].fill, [0x11, 0x22, 0x33, 0xff]);
        assert_eq!(records[0].stroke, [0x44, 0x55, 0x66, 0xff]);
        assert_eq!(records[0].legend_kind, 1);
        assert_eq!(records[0].legend_symbol, 3);
        assert_eq!(records[0].name, b"alpha");
    }

    #[test]
    fn legend_include_requires_nonempty_name() {
        let attached = pack_xytt_one(
            [0, 0, 0, 255],
            [0, 0, 0, 255],
            1.0,
            1,
            1,
            0,
            &[],
            LINECAP_NONE,
            &[],
            &[],
            &[],
            &[],
        );
        let empty = pack_trace_sidecars(&attached, &xynm(&[""])).unwrap();
        assert!(name_of(&empty).is_empty());
        let excluded = pack_xytt_one(
            [0, 0, 0, 255],
            [0, 0, 0, 255],
            1.0,
            1,
            0,
            0,
            &[],
            LINECAP_NONE,
            &[],
            &[],
            &[],
            &[],
        );
        let gated = pack_trace_sidecars(&excluded, &xynm(&["alpha"])).unwrap();
        assert!(name_of(&gated).is_empty());
    }

    #[test]
    fn heatmap_plane_preferred_over_density() {
        let attached = pack_xytt_one(
            [0, 0, 0, 255],
            [0, 0, 0, 255],
            1.0,
            0,
            0,
            0,
            &[],
            LINECAP_NONE,
            &[],
            &[],
            &[1, 2, 3, 4],
            &[9, 9, 9, 9, 9, 9, 9, 9],
        );
        let packed = pack_trace_sidecars(&attached, &xynm(&[""])).unwrap();
        assert_eq!(plane_of(&packed), vec![1, 2, 3, 4]);
        let density_only = pack_xytt_one(
            [0, 0, 0, 255],
            [0, 0, 0, 255],
            1.0,
            0,
            0,
            0,
            &[],
            LINECAP_NONE,
            &[],
            &[],
            &[],
            &[9, 8, 7, 6],
        );
        let packed = pack_trace_sidecars(&density_only, &xynm(&[""])).unwrap();
        assert_eq!(plane_of(&packed), vec![9, 8, 7, 6]);
    }

    #[test]
    fn names_count_mismatch_is_trace_count() {
        let err = pack_trace_sidecars(&empty_xytt(), &xynm(&["alpha"])).unwrap_err();
        assert_eq!(err.code, TraceSidecarsCode::TraceCount);
    }

    #[test]
    fn version_mismatch_is_version() {
        let mut names = xynm(&[]);
        names[4..8].copy_from_slice(&2u32.to_le_bytes());
        let err = pack_trace_sidecars(&empty_xytt(), &names).unwrap_err();
        assert_eq!(err.code, TraceSidecarsCode::Version);
    }
}
