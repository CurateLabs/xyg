//! Resolved CPU publication snapshot. These f64 records are not GPU uploads;
//! subsequent generic offset-f32 lowering remains Rust-owned (§29).
use super::paint::{EdgePiece, FramePaint, NodePaint, PaintGeometry};
use super::wire::*;
use super::InteractionStatus;
use crate::graph_style::{ResolvedGraphStyle, SemanticPaintLayers};

fn style_bytes(style: &ResolvedGraphStyle, layers: &SemanticPaintLayers, out: &mut Vec<u8>) {
    out.extend(style.fill);
    out.extend(style.stroke);
    out.extend(style.halo);
    for v in [style.size, style.width, style.opacity] {
        out.extend(v.to_le_bytes());
    }
    out.extend([style.shape, style.dash, style.arrow, style.state]);
    out.extend(layers.halo);
    out.extend(layers.body);
    out.extend(layers.stroke);
    for v in [
        layers.halo_extent,
        layers.body_width,
        layers.dash.0,
        layers.dash.1,
    ] {
        out.extend(v.to_le_bytes());
    }
    out.extend([u8::from(layers.head), 0, 0, 0]);
}
pub(super) fn encode(b: &mut Builder, p: &PaintGeometry) {
    b.f64s(
        "paint.node.center.f64",
        0,
        &p.nodes.iter().flat_map(|n| n.center).collect::<Vec<_>>(),
    );
    let mut nodes = Vec::new();
    for n in &p.nodes {
        style_bytes(&n.style, &n.layers, &mut nodes);
    }
    b.bytes("paint.node.style.bytes", 0, &nodes);
    let mut edges = Vec::new();
    for (s, l) in p.edge_styles.iter().zip(&p.edge_layers) {
        style_bytes(s, l, &mut edges);
    }
    b.bytes("paint.edge.style.bytes", 0, &edges);
    b.u64s(
        "paint.piece.index.u64",
        0,
        &p.pieces
            .iter()
            .flat_map(|p| {
                [
                    p.edge as u64,
                    u64::from(p.single_piece) | (u64::from(p.head.is_some()) << 1),
                ]
            })
            .collect::<Vec<_>>(),
    );
    b.f64s(
        "paint.piece.geometry.f64",
        0,
        &p.pieces
            .iter()
            .flat_map(|p| {
                let h = p.head.unwrap_or([[0.; 2]; 3]);
                [
                    p.start[0],
                    p.start[1],
                    p.end[0],
                    p.end[1],
                    p.half_width,
                    p.dash.0,
                    p.dash.1,
                    p.dash_offset,
                    h[0][0],
                    h[0][1],
                    h[1][0],
                    h[1][1],
                    h[2][0],
                    h[2][1],
                ]
            })
            .collect::<Vec<_>>(),
    );
    b.u64s(
        "paint.frame.node.u64",
        0,
        &p.frames.iter().map(|f| f.node as u64).collect::<Vec<_>>(),
    );
    b.f64s(
        "paint.frame.geometry.f64",
        0,
        &p.frames
            .iter()
            .flat_map(|f| {
                [
                    f.bounds[0],
                    f.bounds[1],
                    f.bounds[2],
                    f.bounds[3],
                    f.half_width,
                ]
            })
            .collect::<Vec<_>>(),
    );
}

fn read_style(v: &[u8]) -> Result<(ResolvedGraphStyle, SemanticPaintLayers)> {
    let f = |at| f32::from_le_bytes(v[at..at + 4].try_into().unwrap());
    if v[56] > 1
        || v[57..60] != [0; 3]
        || [12, 16, 20, 40, 44, 48, 52]
            .iter()
            .any(|&i| !f(i).is_finite())
    {
        return bad();
    }
    Ok((
        ResolvedGraphStyle {
            fill: v[0..4].try_into().unwrap(),
            stroke: v[4..8].try_into().unwrap(),
            halo: v[8..12].try_into().unwrap(),
            size: f(12),
            width: f(16),
            opacity: f(20),
            shape: v[24],
            dash: v[25],
            arrow: v[26],
            state: v[27],
        },
        SemanticPaintLayers {
            halo: v[28..32].try_into().unwrap(),
            body: v[32..36].try_into().unwrap(),
            stroke: v[36..40].try_into().unwrap(),
            halo_extent: f(40),
            body_width: f(44),
            dash: (f(48), f(52)),
            head: v[56] != 0,
        },
    ))
}
/// Decode without consulting source semantics, layout, router, or Scene.
/// Container bounds/types and cross-plane counts are validated before indexing.
pub fn decode(bytes: &[u8]) -> Result<PaintGeometry> {
    let c = gf(Container::decode(bytes, RESULT_MAGIC))?;
    let get = |name| c.get(name, 0).ok_or(InteractionStatus::Invalid);
    let floats = |name| -> Result<Vec<f64>> {
        let v = gf(get(name)?.as_f64(name))?;
        if v.iter().any(|f| !f.is_finite()) {
            return bad();
        }
        Ok(v)
    };
    let nodes = floats("paint.node.center.f64")?;
    let ns = get("paint.node.style.bytes")?;
    let es = get("paint.edge.style.bytes")?;
    if ns.dtype != Dtype::Bytes
        || es.dtype != Dtype::Bytes
        || nodes.len() % 2 != 0
        || ns.payload.len() / 60 != nodes.len() / 2
        || ns.payload.len() % 60 != 0
        || es.payload.len() % 60 != 0
    {
        return bad();
    }
    let mut p = PaintGeometry::default();
    for (v, center) in ns.payload.chunks_exact(60).zip(nodes.chunks_exact(2)) {
        let (style, layers) = read_style(v)?;
        p.nodes.push(NodePaint {
            center: [center[0], center[1]],
            style,
            layers,
        });
    }
    for v in es.payload.chunks_exact(60) {
        let (s, l) = read_style(v)?;
        p.edge_styles.push(s);
        p.edge_layers.push(l);
    }
    let index = gf(get("paint.piece.index.u64")?.as_u64("paint.piece.index.u64"))?;
    let geometry = floats("paint.piece.geometry.f64")?;
    if index.len() % 2 != 0 || geometry.len() % 14 != 0 || index.len() / 2 != geometry.len() / 14 {
        return bad();
    }
    for (i, g) in index.chunks_exact(2).zip(geometry.chunks_exact(14)) {
        if i[0] >= p.edge_styles.len() as u64
            || i[1] & !3 != 0
            || (i[1] & 2 == 0 && g[8..] != [0.; 6])
        {
            return bad();
        }
        p.pieces.push(EdgePiece {
            edge: i[0] as usize,
            single_piece: i[1] & 1 != 0,
            start: [g[0], g[1]],
            end: [g[2], g[3]],
            half_width: g[4],
            dash: (g[5], g[6]),
            dash_offset: g[7],
            head: (i[1] & 2 != 0).then_some([[g[8], g[9]], [g[10], g[11]], [g[12], g[13]]]),
        });
    }
    let index = gf(get("paint.frame.node.u64")?.as_u64("paint.frame.node.u64"))?;
    let geometry = floats("paint.frame.geometry.f64")?;
    if geometry.len() % 5 != 0 || geometry.len() / 5 != index.len() {
        return bad();
    }
    for (&i, g) in index.iter().zip(geometry.chunks_exact(5)) {
        if i >= p.nodes.len() as u64 {
            return bad();
        }
        p.frames.push(FramePaint {
            node: i as usize,
            bounds: [g[0], g[1], g[2], g[3]],
            half_width: g[4],
        });
    }
    if get("render.node_x.f64")?.count != p.nodes.len()
        || get("render.edge_source.u64")?.count != p.edge_styles.len()
    {
        return bad();
    }
    Ok(p)
}
