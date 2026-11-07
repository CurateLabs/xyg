//! Retained temporal paint -> canonical Scene. No layout, routing or style resolution.
use crate::graph_scene::Columns;
use crate::graphforge::{container::Container, interaction::wire::decode_paint};
use crate::scene::*;
use crate::temporal::TemporalError as E;
use crate::temporal_graph_frozen::{FrozenTemporalGraph, MAX_PEAK};
type Result<T> = std::result::Result<T, E>;
fn bad<T>(_: T) -> E {
    E::InvalidArgument
}

fn segment(
    c: &mut Columns,
    id: u64,
    a: [f64; 2],
    b: [f64; 2],
    color: [u8; 4],
    width: f64,
) -> Result<()> {
    if color[3] == 0 || width <= 0. {
        return Ok(());
    }
    let s = c.capped_style([0; 4], color, width, true);
    for p in [a, b] {
        c.row(SceneRecordKind::Segment, id, s, 0., 0, p[0], p[1], 0., 0.)
            .map_err(bad)?;
    }
    Ok(())
}
fn marker(
    c: &mut Columns,
    id: u64,
    p: [f64; 2],
    size: f64,
    shape: u8,
    fill: [u8; 4],
    stroke: [u8; 4],
    width: f64,
) -> Result<()> {
    let s = c.style(fill, stroke, width);
    c.row(
        SceneRecordKind::Scatter,
        id,
        s,
        size,
        shape,
        p[0],
        p[1],
        0.,
        0.,
    )
    .map_err(bad)
}
fn frame(c: &mut Columns, id: u64, b: [f64; 4], color: [u8; 4], half: f64) -> Result<()> {
    let style = c.style([0; 4], color, half * 2.);
    c.row(
        SceneRecordKind::Rect,
        id,
        style,
        0.,
        0,
        b[0],
        b[1],
        b[2],
        b[3],
    )
    .map_err(bad)
}
// Count and split the same phase-aware CSS distance interval before allocating columns.
fn intervals(
    length: f64,
    on: f64,
    off: f64,
    phase: f64,
    mut emit: impl FnMut(f64, f64) -> Result<()>,
) -> Result<()> {
    if on == 0. || off == 0. {
        return emit(0., length);
    }
    let period = on + off;
    let mut x = 0.;
    let mut count = 0usize;
    while x < length {
        count += 1;
        if count > MAX_SCENE_MARKS / 12 {
            return Err(E::CapacityExceeded);
        }
        let p = (phase + x).rem_euclid(period);
        let remaining = if p < on { on - p } else { period - p };
        let end = (x + remaining).min(length);
        if end <= x {
            return Err(E::CapacityExceeded);
        }
        if p < on {
            emit(x, end)?;
        }
        x = end;
    }
    Ok(())
}
/// Literal IDs map nodes to 1+render ordinal, edges to 2^48+ordinal,
/// frames to 3*2^48+node ordinal. Exact UUID/CSR maps remain in XYFG.
/// Focus RGBA is an explicit export override: v1 never captured browser CSS.
pub fn canonical_scene(bytes: &[u8], focus: [u8; 4], budget: usize) -> Result<Vec<u8>> {
    let frozen = FrozenTemporalGraph::decode(bytes, budget)?;
    let source = Container::decode(&frozen.bytes()[..bytes.len() - 8], b"XYFG").map_err(bad)?;
    let get = |name| source.get(name, 0).ok_or(E::InvalidArgument);
    let camera = get("render.camera")?.as_f64("render.camera").map_err(bad)?;
    if camera.len() != 7 {
        return Err(E::InvalidArgument);
    }
    let reply = get("render.publication")?.payload;
    let paint = decode_paint(reply).map_err(bad)?;
    let r = Container::decode(reply, b"XYGR").map_err(bad)?;
    let nf = r
        .get("render.emphasis.u8", 0)
        .ok_or(E::InvalidArgument)?
        .payload;
    let ef = r
        .get("render.edge_emphasis.u8", 0)
        .ok_or(E::InvalidArgument)?
        .payload;
    if paint
        .nodes
        .iter()
        .enumerate()
        .any(|(i, n)| nf[i] & 1 != 0 && n.style.shape > 1)
    {
        // v1 Scene markers cannot express a constant SDF offset for every symbol.
        // Refuse rather than substitute a scaled symbol and claim exact focus.
        return Err(E::InvalidArgument);
    }
    // Reserve columns, prepared records, Scene, painter and encode slack before expansion.
    let mut records = paint
        .nodes
        .len()
        .checked_mul(3)
        .and_then(|n| n.checked_add(paint.frames.len() * 16))
        .ok_or(E::CapacityExceeded)?;
    for p in &paint.pieces {
        let length = (p.end[0] - p.start[0]).hypot(p.end[1] - p.start[1]);
        intervals(length, p.dash.0, p.dash.1, p.dash_offset, |_, _| {
            records = records.checked_add(14).ok_or(E::CapacityExceeded)?;
            Ok(())
        })?;
        records = records.checked_add(3).ok_or(E::CapacityExceeded)?;
    }
    let peak = FrozenTemporalGraph::required_peak(bytes.len())?
        .checked_add(records.checked_mul(1024).ok_or(E::CapacityExceeded)?)
        .ok_or(E::CapacityExceeded)?;
    if records > MAX_SCENE_MARKS || peak > budget || budget > MAX_PEAK {
        return Err(E::BudgetExceeded);
    }
    let mut styles = std::collections::HashSet::new();
    let mut admit_style = |fill: [u8; 4], stroke: [u8; 4], width: f64, butt: bool| -> Result<()> {
        styles.insert((fill, stroke, width.to_bits(), butt));
        if styles.len() > 1024 {
            return Err(E::CapacityExceeded);
        }
        Ok(())
    };
    for (i, n) in paint.nodes.iter().enumerate() {
        admit_style(n.layers.halo, [0; 4], 0., false)?;
        admit_style(n.layers.body, n.layers.stroke, n.style.width as f64, false)?;
        if nf[i] & 1 != 0 {
            admit_style([0; 4], focus, 2., false)?;
        }
    }
    for f in &paint.frames {
        admit_style(
            [0; 4],
            paint.nodes[f.node].layers.stroke,
            f.half_width * 2.,
            false,
        )?;
        if nf[f.node] & 1 != 0 {
            admit_style([0; 4], focus, (f.half_width + 2.) * 2., false)?;
        }
    }
    for p in &paint.pieces {
        let l = paint.edge_layers[p.edge];
        let st = paint.edge_styles[p.edge];
        for (color, width) in [
            (l.halo, l.halo_extent as f64),
            (l.body, l.body_width as f64),
            (l.stroke, st.width as f64),
        ] {
            if color[3] != 0 && width > 0. {
                admit_style([0; 4], color, width, true)?;
            }
        }
        if p.head.is_some() {
            admit_style(l.stroke, [0; 4], 0., false)?;
        }
        if ef[p.edge] & 1 != 0 {
            admit_style([0; 4], focus, 2., true)?;
        }
    }
    let mut c = Columns::default();
    for f in &paint.frames {
        frame(
            &mut c,
            (3 << 48) + f.node as u64,
            f.bounds,
            paint.nodes[f.node].layers.stroke,
            f.half_width,
        )?;
    }
    for p in &paint.pieces {
        let id = (2 << 48) + p.edge as u64;
        let l = paint.edge_layers[p.edge];
        let s = paint.edge_styles[p.edge];
        let d = [p.end[0] - p.start[0], p.end[1] - p.start[1]];
        let length = d[0].hypot(d[1]);
        if length == 0. {
            continue;
        }
        intervals(length, p.dash.0, p.dash.1, p.dash_offset, |a, b| {
            let at = |t: f64| {
                [
                    p.start[0] + d[0] * t / length,
                    p.start[1] + d[1] * t / length,
                ]
            };
            for (color, width) in [
                (l.halo, l.halo_extent as f64),
                (l.body, l.body_width as f64),
                (l.stroke, s.width as f64),
            ] {
                segment(&mut c, id, at(a), at(b), color, width)?;
            }
            Ok(())
        })?;
    }
    for p in &paint.pieces {
        if let Some(head) = p.head {
            let s = c.style(paint.edge_layers[p.edge].stroke, [0; 4], 0.);
            for v in head {
                c.row(
                    SceneRecordKind::Triangle,
                    (2 << 48) + p.edge as u64,
                    s,
                    0.,
                    0,
                    v[0],
                    v[1],
                    0.,
                    0.,
                )
                .map_err(bad)?;
            }
        }
    }
    for (i, n) in paint.nodes.iter().enumerate() {
        marker(
            &mut c,
            1 + i as u64,
            n.center,
            n.layers.halo_extent as f64,
            0,
            n.layers.halo,
            [0; 4],
            0.,
        )?;
        marker(
            &mut c,
            1 + i as u64,
            n.center,
            n.style.size as f64,
            n.style.shape,
            n.layers.body,
            n.layers.stroke,
            n.style.width as f64,
        )?;
    }
    for f in &paint.frames {
        if nf[f.node] & 1 != 0 {
            frame(
                &mut c,
                (3 << 48) + f.node as u64,
                f.bounds,
                focus,
                f.half_width + 2.,
            )?;
        }
    }
    for p in &paint.pieces {
        if ef[p.edge] & 1 != 0 {
            let d = [p.end[0] - p.start[0], p.end[1] - p.start[1]];
            let length = d[0].hypot(d[1]);
            if length == 0. {
                continue;
            }
            intervals(length, p.dash.0, p.dash.1, p.dash_offset, |a, b| {
                for sign in [-1., 1.] {
                    let offset = (p.half_width + 1.) * sign;
                    let at = |t: f64| {
                        [
                            p.start[0] + d[0] * t / length - d[1] / length * offset,
                            p.start[1] + d[1] * t / length + d[0] / length * offset,
                        ]
                    };
                    segment(&mut c, (2 << 48) + p.edge as u64, at(a), at(b), focus, 2.)?;
                }
                Ok(())
            })?;
        }
    }
    for (i, n) in paint.nodes.iter().enumerate() {
        if nf[i] & 1 != 0 {
            // Scene's marker outlines are inset; outer extent is three CSS px beyond body.
            marker(
                &mut c,
                1 + i as u64,
                n.center,
                n.style.size as f64 + 6.,
                n.style.shape,
                [0; 4],
                focus,
                2.,
            )?;
        }
    }
    if c.style_count > 1024 {
        return Err(E::CapacityExceeded);
    }
    let layout = PlotLayout::new(camera[4], camera[5], 0., 0., 0., 0.).map_err(bad)?;
    let axis =
        |extent| AxisScale::new(ScaleKind::Linear, 0., extent, 0., extent, 1., false).map_err(bad);
    let mut chrome = SceneChromeStyle {
        x_major_ticks: Some(vec![]),
        y_major_ticks: Some(vec![]),
        ..SceneChromeStyle::default()
    };
    for a in [&mut chrome.x_axis, &mut chrome.y_axis] {
        a.tick_sides = 0;
        a.tick_label_sides = 0;
        a.axis_rgba = [0; 4];
    }
    chrome.label_rgba = [0; 4];
    let batch = SceneBatch::new_with_chrome_literal_ids(
        layout,
        1,
        2,
        axis(camera[4])?,
        axis(camera[5])?,
        chrome,
        SceneChromeText::default(),
        &c.kinds,
        &c.stable_ids,
        &c.style_refs,
        &c.fill,
        &c.stroke,
        &c.stroke_width,
        &c.diameter,
        &c.symbols,
        &c.x0,
        &c.y0,
        &c.x1,
        &c.y1,
    )
    .map_err(bad)?;
    Ok(batch
        .with_dashes(&encode_butt_caps(&c.butt_styles).map_err(bad)?)
        .map_err(bad)?
        .encode())
}

const PREFIX: &str = "<metadata id=\"xyg-frozen-v1\">";
const SUFFIX: &str = "</metadata>";
fn hex(bytes: &[u8]) -> String {
    const H: &[u8] = b"0123456789abcdef";
    let mut s = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        s.push(H[(b >> 4) as usize] as char);
        s.push(H[(b & 15) as usize] as char);
    }
    s
}
fn unhex(s: &[u8]) -> Result<Vec<u8>> {
    if s.len() % 2 != 0 {
        return Err(E::InvalidArgument);
    }
    let nib = |b| match b {
        b'0'..=b'9' => Ok(b - b'0'),
        b'a'..=b'f' => Ok(b - b'a' + 10),
        _ => Err(E::InvalidArgument),
    };
    s.chunks_exact(2)
        .map(|v| Ok(nib(v[0])? * 16 + nib(v[1])?))
        .collect()
}
fn crc(bytes: &[u8]) -> u32 {
    let mut c = !0u32;
    for &b in bytes {
        c ^= b as u32;
        for _ in 0..8 {
            c = (c >> 1) ^ (0xedb88320u32.wrapping_mul(c & 1));
        }
    }
    !c
}
fn chunk(kind: &[u8; 4], body: &[u8]) -> Result<Vec<u8>> {
    let n = u32::try_from(body.len()).map_err(bad)?;
    let mut v = Vec::with_capacity(body.len() + 12);
    v.extend(n.to_be_bytes());
    v.extend(kind);
    v.extend(body);
    let c = crc(&v[4..]);
    v.extend(c.to_be_bytes());
    Ok(v)
}
/// Format 0 SVG, 1 PNG, 2 offline HTML (inline canonical SVG), 3 Scene, 4 XYPB.
/// Raster backing pixels = round(CSS extent * camera DPR * scale).
pub fn export(
    bytes: &[u8],
    format: u32,
    scale: f64,
    focus: [u8; 4],
    budget: usize,
) -> Result<Vec<u8>> {
    if format > 4 || !scale.is_finite() || scale <= 0. || scale > 8. || budget > MAX_PEAK {
        return Err(E::InvalidArgument);
    }
    FrozenTemporalGraph::validate(bytes, budget)?;
    let source = Container::decode(&bytes[..bytes.len() - 8], b"XYFG").map_err(bad)?;
    let camera = source
        .get("render.camera", 0)
        .ok_or(E::InvalidArgument)?
        .as_f64("render.camera")
        .map_err(bad)?;
    if camera.len() != 7 {
        return Err(E::InvalidArgument);
    }
    let resolution = scale * camera[6];
    let w = (camera[4] * resolution).round();
    let h = (camera[5] * resolution).round();
    if w < 1. || h < 1. || w > 32768. || h > 32768. {
        return Err(E::CapacityExceeded);
    }
    let reserved = bytes
        .len()
        .checked_mul(8)
        .and_then(|n| {
            n.checked_add(if format == 1 {
                (w as usize).checked_mul(h as usize)?.checked_mul(32)?
            } else {
                65536
            })
        })
        .ok_or(E::CapacityExceeded)?;
    if reserved >= budget {
        return Err(E::BudgetExceeded);
    }
    let scene = canonical_scene(bytes, focus, budget - reserved)?;
    if format == 3 {
        return Ok(scene);
    }
    if format == 4 {
        return browser_painter_from_scene(&scene, budget - reserved).map_err(bad);
    }
    let body = crate::scene_static::scene_static_export(
        &scene,
        if format == 1 {
            crate::scene_static::SceneStaticFormat::Png
        } else {
            crate::scene_static::SceneStaticFormat::Svg
        },
        resolution,
        w as usize,
        h as usize,
        90,
    )
    .map_err(bad)?;
    if body
        .len()
        .checked_mul(4)
        .and_then(|n| n.checked_add(reserved))
        .is_none_or(|n| n > budget)
    {
        return Err(E::BudgetExceeded);
    }
    let mut carrier = Vec::with_capacity(bytes.len() + 24);
    carrier.extend(b"XYFE");
    carrier.extend(1u32.to_le_bytes());
    carrier.extend(format.to_le_bytes());
    carrier.extend(scale.to_le_bytes());
    carrier.extend(focus);
    carrier.extend(bytes);
    if format == 1 {
        if body.len() < 12 {
            return Err(E::InvalidArgument);
        }
        let mut field = b"xyg-frozen-v1\0\0\0\0\0".to_vec();
        field.extend(hex(&carrier).as_bytes());
        let metadata = chunk(b"iTXt", &field)?;
        let split = body.len() - 12;
        let mut out = Vec::with_capacity(body.len() + metadata.len());
        out.extend(&body[..split]);
        out.extend(metadata);
        out.extend(&body[split..]);
        Ok(out)
    } else {
        let svg = std::str::from_utf8(&body).map_err(bad)?;
        let end = svg.rfind("</svg>").ok_or(E::InvalidArgument)?;
        let rendered = format!(
            "{}{}{}{}{}",
            &svg[..end],
            PREFIX,
            hex(&carrier),
            SUFFIX,
            &svg[end..]
        );
        Ok(if format == 2 {
            format!("<!doctype html><meta charset=\"utf-8\"><title>Frozen temporal graph</title>{rendered}").into_bytes()
        } else {
            rendered.into_bytes()
        })
    }
}
/// Recovery regenerates and compares the entire visible artifact, including PNG
/// chunk order/CRC, rejecting duplicate carriers and body mutations. Integrity,
/// not authenticity: callers can produce a new consistent export themselves.
pub fn recover(artifact: &[u8], budget: usize) -> Result<Vec<u8>> {
    if budget > MAX_PEAK || artifact.len() > budget / 4 {
        return Err(E::BudgetExceeded);
    }
    let mut carriers = Vec::new();
    if artifact.starts_with(b"\x89PNG\r\n\x1a\n") {
        let mut at = 8usize;
        while at < artifact.len() {
            let head = artifact.get(at..at + 8).ok_or(E::InvalidArgument)?;
            let n = u32::from_be_bytes(head[..4].try_into().unwrap()) as usize;
            let end = at
                .checked_add(n)
                .and_then(|v| v.checked_add(12))
                .filter(|&v| v <= artifact.len())
                .ok_or(E::InvalidArgument)?;
            let data = &artifact[at + 8..end - 4];
            if &head[4..] == b"iTXt" && data.starts_with(b"xyg-frozen-v1\0\0\0\0\0") {
                carriers.push(&data[18..]);
            }
            at = end;
        }
    } else {
        let s = std::str::from_utf8(artifact).map_err(bad)?;
        let mut rest = s;
        while let Some(start) = rest.find(PREFIX) {
            rest = &rest[start + PREFIX.len()..];
            let end = rest.find(SUFFIX).ok_or(E::InvalidArgument)?;
            carriers.push(rest[..end].as_bytes());
            rest = &rest[end + SUFFIX.len()..];
        }
    }
    if carriers.len() != 1 || carriers[0].len() > 2 * (crate::temporal_graph_frozen::MAX_BYTES + 24)
    {
        return Err(E::InvalidArgument);
    }
    let raw = unhex(carriers[0])?;
    if raw.len() < 24 || &raw[..4] != b"XYFE" || raw[4..8] != 1u32.to_le_bytes() {
        return Err(E::InvalidArgument);
    }
    let format = u32::from_le_bytes(raw[8..12].try_into().unwrap());
    if format > 2 {
        return Err(E::InvalidArgument);
    }
    let scale = f64::from_le_bytes(raw[12..20].try_into().unwrap());
    let focus = raw[20..24].try_into().unwrap();
    let bytes = &raw[24..];
    if export(bytes, format, scale, focus, budget)? != artifact {
        return Err(E::InvalidArgument);
    }
    Ok(bytes.to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn retained_dash_phase_survives_trimming() {
        let mut pieces = Vec::new();
        intervals(12., 3., 2., 4., |a, b| {
            pieces.push((a, b));
            Ok(())
        })
        .unwrap();
        assert_eq!(pieces, [(1., 4.), (6., 9.), (11., 12.)]);
        pieces.clear();
        intervals(12., 3., 0., 4., |a, b| {
            pieces.push((a, b));
            Ok(())
        })
        .unwrap();
        assert_eq!(pieces, [(0., 12.)]);
    }
}
