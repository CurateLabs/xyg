//! S5a: lower the complete published geometry, never source/layout policy.
//! XYGR GPU v1 is specified in graph-interaction.md; all float uploads are
//! offset-f32 columns (§4/16/29). The CPU snapshot and pick index stay f64.
use super::wire::{bad, gf, Builder, Container, Dtype, Result, RESULT_MAGIC};
use super::{InteractionStatus, RenderOutput};
use crate::kernels::{f32_safe_scale, geometry_offset, offset_f32};

fn transform([lo, hi]: [f64; 2]) -> Result<[f64; 2]> {
    if lo > hi {
        return Ok([0., 1.]);
    }
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
fn extent(b: &mut [f64; 2], v: f64) -> Result<()> {
    if !v.is_finite() {
        return bad();
    }
    b[0] = b[0].min(v);
    b[1] = b[1].max(v);
    Ok(())
}
fn transforms(p: &super::PaintGeometry) -> Result<[[f64; 2]; 3]> {
    let mut bounds = [[f64::INFINITY, f64::NEG_INFINITY]; 3];
    // Preserve each axis's original visitation order and arithmetic, using
    // one domain pass instead of specialized chained iterator state machines.
    for n in &p.nodes {
        for axis in 0..2 {
            extent(&mut bounds[axis], n.center[axis])?;
        }
    }
    for piece in &p.pieces {
        for axis in 0..2 {
            extent(&mut bounds[axis], piece.start[axis])?;
            extent(&mut bounds[axis], piece.end[axis])?;
        }
    }
    for piece in &p.pieces {
        if let Some(head) = piece.head {
            for point in head {
                for axis in 0..2 {
                    extent(&mut bounds[axis], point[axis])?;
                }
            }
        }
    }
    for frame in &p.frames {
        for axis in 0..2 {
            extent(&mut bounds[axis], frame.bounds[axis])?;
            extent(&mut bounds[axis], frame.bounds[axis + 2])?;
        }
    }
    for piece in &p.pieces {
        extent(&mut bounds[2], piece.dash_offset)?;
    }
    Ok([
        transform(bounds[0])?,
        transform(bounds[1])?,
        transform(bounds[2])?,
    ])
}

#[cfg_attr(target_arch = "wasm32", inline(never))]
fn column(
    b: &mut Builder,
    name: &str,
    index: usize,
    values: &mut dyn Iterator<Item = f64>,
    [offset, scale]: [f64; 2],
) -> Result<()> {
    // Lower directly into the packet-owned column. Both public encoders use
    // the same scalar kernel; no intermediate f64/f32 vectors overlap it.
    let mut encoded = Vec::with_capacity(
        values
            .size_hint()
            .0
            .checked_mul(4)
            .ok_or(InteractionStatus::Budget)?,
    );
    for value in values {
        let lowered = offset_f32(value, offset, scale);
        if !value.is_finite() || !lowered.is_finite() {
            return bad();
        }
        encoded.extend_from_slice(&lowered.to_le_bytes());
    }
    b.push(name, index, Dtype::Bytes, encoded.len(), encoded);
    Ok(())
}

#[cfg_attr(target_arch = "wasm32", inline(never))]
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
    let transforms = transforms(p)?;
    for (i, t) in transforms.iter().enumerate() {
        b.f64s("gpu.transform.f64", i, t);
    }
    for axis in 0..2 {
        column(
            b,
            "gpu.node.coord.bytes",
            axis,
            &mut p.nodes.iter().map(|n| n.center[axis]),
            transforms[axis],
        )?;
    }
    for i in 0..4 {
        column(
            b,
            "gpu.shaft.coord.bytes",
            i,
            &mut p
                .pieces
                .iter()
                .map(|p| [p.start[0], p.start[1], p.end[0], p.end[1]][i]),
            transforms[i % 2],
        )?;
        column(
            b,
            "gpu.frame.coord.bytes",
            i,
            &mut p.frames.iter().map(|f| f.bounds[i]),
            transforms[i % 2],
        )?;
        column(
            b,
            "gpu.shaft.attr.bytes",
            i,
            &mut p
                .pieces
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
            &mut p
                .pieces
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
        &mut p.frames.iter().map(|f| f.half_width),
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
    super::wire_paint::styles(b, "gpu.node.style.bytes", p.nodes.len(), &|i| {
        (&p.nodes[i].style, &p.nodes[i].layers)
    });
    super::wire_paint::styles(b, "gpu.edge.style.bytes", p.edge_styles.len(), &|i| {
        (&p.edge_styles[i], &p.edge_layers[i])
    });
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
