//! S5a: lower the complete published geometry, never source/layout policy.
//! XYGR GPU v1 is specified in graph-interaction.md; all float uploads are
//! offset-f32 columns (§4/16/29). The CPU snapshot and pick index stay f64.
use super::wire::{bad, gf, Builder, Container, Dtype, Result, RESULT_MAGIC};
use super::{InteractionStatus, RenderOutput};
use crate::graph_style::{ResolvedGraphStyle, SemanticPaintLayers};
use crate::kernels::{encode_f32, f32_safe_scale, geometry_offset};

fn transform(values: impl Iterator<Item = f64>) -> Result<[f64; 2]> {
    let (mut lo, mut hi) = (f64::INFINITY, f64::NEG_INFINITY);
    for v in values {
        if !v.is_finite() {
            return bad();
        }
        lo = lo.min(v);
        hi = hi.max(v);
    }
    if lo > hi {
        return Ok([0., 1.]);
    }
    // The kernel midpoint may overflow for extreme same-sign finite domains.
    // Its pin-zero mode is also the established finite offset convention.
    let mut offset = geometry_offset(false, lo, hi);
    if !offset.is_finite() {
        offset = geometry_offset(true, lo, hi);
    }
    let scale = f32_safe_scale(offset, lo, hi);
    if !scale.is_finite() || scale <= 0. {
        return bad();
    }
    Ok([offset, scale])
}

fn column(
    b: &mut Builder,
    name: &str,
    index: usize,
    values: impl Iterator<Item = f64>,
    [offset, scale]: [f64; 2],
) -> Result<()> {
    let values: Vec<_> = values.collect();
    let mut encoded = Vec::new();
    encode_f32(&values, offset, scale, &mut encoded);
    if values.iter().any(|v| !v.is_finite()) || encoded.iter().any(|v| !v.is_finite()) {
        return bad();
    }
    b.bytes(
        name,
        index,
        &encoded
            .iter()
            .flat_map(|v| v.to_le_bytes())
            .collect::<Vec<_>>(),
    );
    Ok(())
}

// Same resolved 60-byte f32/u8 attribute stride as the CPU inspection snapshot.
// No resolving, recoloring, size normalization or host narrowing is involved.
fn style(s: &ResolvedGraphStyle, l: &SemanticPaintLayers, out: &mut Vec<u8>) {
    out.extend(s.fill);
    out.extend(s.stroke);
    out.extend(s.halo);
    for v in [s.size, s.width, s.opacity] {
        out.extend(v.to_le_bytes());
    }
    out.extend([s.shape, s.dash, s.arrow, s.state]);
    out.extend(l.halo);
    out.extend(l.body);
    out.extend(l.stroke);
    for v in [l.halo_extent, l.body_width, l.dash.0, l.dash.1] {
        out.extend(v.to_le_bytes());
    }
    out.extend([u8::from(l.head), 0, 0, 0]);
}

pub(super) fn encode(b: &mut Builder, r: &RenderOutput) -> Result<()> {
    let p = &r.paint;
    let counts = [
        p.nodes.len(),
        p.edge_styles.len(),
        p.pieces.len(),
        p.pieces.iter().filter(|p| p.head.is_some()).count(),
        p.frames.len(),
    ];
    let mut header = vec![1, 0];
    for count in counts {
        header.push(count.try_into().map_err(|_| InteractionStatus::Budget)?);
    }
    header.push(0);
    b.u32s("gpu.header.u32", 0, &header);
    let mut transforms = [[0., 1.]; 3];
    for (axis, t) in transforms[..2].iter_mut().enumerate() {
        *t = transform(
            p.nodes
                .iter()
                .map(|n| n.center[axis])
                .chain(p.pieces.iter().flat_map(|p| [p.start[axis], p.end[axis]]))
                .chain(
                    p.pieces
                        .iter()
                        .filter_map(|p| p.head)
                        .flat_map(|h| h.map(|v| v[axis])),
                )
                .chain(
                    p.frames
                        .iter()
                        .flat_map(|f| [f.bounds[axis], f.bounds[axis + 2]]),
                ),
        )?;
    }
    transforms[2] = transform(p.pieces.iter().map(|p| p.dash_offset))?;
    for (i, t) in transforms.iter().enumerate() {
        b.f64s("gpu.transform.f64", i, t);
    }
    for axis in 0..2 {
        column(
            b,
            "gpu.node.coord.bytes",
            axis,
            p.nodes.iter().map(|n| n.center[axis]),
            transforms[axis],
        )?;
    }
    for i in 0..4 {
        column(
            b,
            "gpu.shaft.coord.bytes",
            i,
            p.pieces
                .iter()
                .map(|p| [p.start[0], p.start[1], p.end[0], p.end[1]][i]),
            transforms[i % 2],
        )?;
        column(
            b,
            "gpu.frame.coord.bytes",
            i,
            p.frames.iter().map(|f| f.bounds[i]),
            transforms[i % 2],
        )?;
        column(
            b,
            "gpu.shaft.attr.bytes",
            i,
            p.pieces
                .iter()
                .map(|p| [p.half_width, p.dash.0, p.dash.1, p.dash_offset][i]),
            if i == 3 { transforms[2] } else { [0., 1.] },
        )?;
    }
    for i in 0..6 {
        column(
            b,
            "gpu.head.coord.bytes",
            i,
            p.pieces
                .iter()
                .filter_map(|p| p.head)
                .map(|h| h[i / 2][i % 2]),
            transforms[i % 2],
        )?;
    }
    column(
        b,
        "gpu.frame.width.bytes",
        0,
        p.frames.iter().map(|f| f.half_width),
        [0., 1.],
    )?;
    b.u32s(
        "gpu.shaft.edge.u32",
        0,
        &p.pieces.iter().map(|p| p.edge as u32).collect::<Vec<_>>(),
    );
    b.u8s(
        "gpu.shaft.flags.u8",
        0,
        &p.pieces
            .iter()
            .map(|p| u8::from(p.single_piece))
            .collect::<Vec<_>>(),
    );
    b.u32s(
        "gpu.head.piece.u32",
        0,
        &p.pieces
            .iter()
            .enumerate()
            .filter(|(_, p)| p.head.is_some())
            .map(|(i, _)| i as u32)
            .collect::<Vec<_>>(),
    );
    b.u32s(
        "gpu.frame.node.u32",
        0,
        &p.frames.iter().map(|f| f.node as u32).collect::<Vec<_>>(),
    );
    let mut styles = Vec::new();
    for n in &p.nodes {
        style(&n.style, &n.layers, &mut styles);
    }
    b.bytes("gpu.node.style.bytes", 0, &styles);
    styles.clear();
    for (s, l) in p.edge_styles.iter().zip(&p.edge_layers) {
        style(s, l, &mut styles);
    }
    b.bytes("gpu.edge.style.bytes", 0, &styles);
    for node in [true, false] {
        let (visual, emphasis, source) = if node {
            (&r.visual_states, &r.emphasis, &r.source_node_flags)
        } else {
            (
                &r.edge_visual_states,
                &r.edge_emphasis,
                &r.source_edge_flags,
            )
        };
        let mut state = Vec::new();
        for (i, (&v, &e)) in visual.iter().zip(emphasis).enumerate() {
            let members = if node {
                r.members_of_node(i)
            } else {
                r.members_of_edge(i)
            };
            // Lossless simultaneous hover/selected/neighbor/pin bits. These are
            // publication membership projection, not another priority resolver.
            let flags = members
                .iter()
                .fold(0, |flags, &m| flags | source[m as usize])
                & 0x17;
            state.extend([v, e, flags as u8, 0]);
        }
        b.u8s(
            if node {
                "gpu.node.state.u8"
            } else {
                "gpu.edge.state.u8"
            },
            0,
            &state,
        );
    }
    Ok(())
}

/// Fail-closed structural validation for a complete GPU v1 view. Does not
/// evaluate graph policy or accept a partial publication. S5b must perform the
/// same validation before constructing/uploading views in its host boundary.
pub fn validate(bytes: &[u8]) -> Result<()> {
    let c = gf(Container::decode(bytes, RESULT_MAGIC))?;
    let get = |name, index, dtype, count| {
        let s = c.get(name, index).ok_or(InteractionStatus::Invalid)?;
        if s.dtype != dtype || s.count != count {
            return bad();
        }
        Ok(s)
    };
    let h = gf(get("gpu.header.u32", 0, Dtype::U32, 8)?.as_u32("gpu.header.u32"))?;
    if h[0] != 1 || h[1] != 0 || h[7] != 0 {
        return bad();
    }
    let [n, m, p, heads, f] = [
        h[2] as usize,
        h[3] as usize,
        h[4] as usize,
        h[5] as usize,
        h[6] as usize,
    ];
    let size =
        |count: usize, stride: usize| count.checked_mul(stride).ok_or(InteractionStatus::Invalid);
    for i in 0..3 {
        let t = gf(get("gpu.transform.f64", i, Dtype::F64, 2)?.as_f64("gpu.transform.f64"))?;
        if !t[0].is_finite() || !t[1].is_finite() || t[1] <= 0. {
            return bad();
        }
    }
    for (name, columns, count) in [
        ("gpu.node.coord.bytes", 2, n),
        ("gpu.shaft.coord.bytes", 4, p),
        ("gpu.shaft.attr.bytes", 4, p),
        ("gpu.head.coord.bytes", 6, heads),
        ("gpu.frame.coord.bytes", 4, f),
        ("gpu.frame.width.bytes", 1, f),
    ] {
        for i in 0..columns {
            let s = get(name, i, Dtype::Bytes, size(count, 4)?)?;
            if s.payload
                .chunks_exact(4)
                .any(|v| !f32::from_le_bytes(v.try_into().unwrap()).is_finite())
            {
                return bad();
            }
        }
    }
    for (name, count, limit) in [
        ("gpu.shaft.edge.u32", p, m),
        ("gpu.head.piece.u32", heads, p),
        ("gpu.frame.node.u32", f, n),
    ] {
        let v = gf(get(name, 0, Dtype::U32, count)?.as_u32(name))?;
        if v.iter().any(|&i| i as usize >= limit)
            || (name == "gpu.head.piece.u32" && v.windows(2).any(|w| w[0] >= w[1]))
        {
            return bad();
        }
    }
    if get("gpu.shaft.flags.u8", 0, Dtype::U8, p)?
        .payload
        .iter()
        .any(|v| *v > 1)
    {
        return bad();
    }
    for (style_name, state_name, count) in [
        ("gpu.node.style.bytes", "gpu.node.state.u8", n),
        ("gpu.edge.style.bytes", "gpu.edge.state.u8", m),
    ] {
        let styles = get(style_name, 0, Dtype::Bytes, size(count, 60)?)?;
        for s in styles.payload.chunks_exact(60) {
            if s[24] > 5
                || s[25] > 3
                || s[26] > 1
                || s[27] > crate::graph_style::STATE_DISABLED
                || s[56] > 1
                || s[57..] != [0; 3]
                || [12, 16, 20, 40, 44, 48, 52]
                    .iter()
                    .any(|&i| !f32::from_le_bytes(s[i..i + 4].try_into().unwrap()).is_finite())
            {
                return bad();
            }
        }
        if get(state_name, 0, Dtype::U8, size(count, 4)?)?
            .payload
            .chunks_exact(4)
            .any(|s| s[0] > 7 || s[1] & !15 != 0 || s[2] & !0x17 != 0 || s[3] != 0)
        {
            return bad();
        }
    }
    // Reject unknown/index-mismatched GPU planes rather than silently accepting
    // extensions under the same contract version.
    if c.sections
        .iter()
        .filter(|(name, _, _)| name.starts_with("gpu."))
        .count()
        != 33
    {
        return bad();
    }
    if c.get("render.node_x.f64", 0).is_none_or(|s| s.count != n)
        || c.get("render.edge_source.u64", 0)
            .is_none_or(|s| s.count != m)
    {
        return bad();
    }
    Ok(())
}
