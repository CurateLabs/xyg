//! Publication geometry, shared by typed picking and the S4 resolved CPU publication seam.
//! No Scene compiler and no second topology/layout/LOD path (§27–29).
use super::*;
use crate::edge_route::{self, NodeShape};
use crate::graph_style::{self, ResolvedGraphStyle, SemanticPaintLayers, SemanticStyleInput};

#[derive(Clone)]
pub(super) struct SourceStyle {
    class: Vec<u8>,
    epistemic: Vec<u8>,
    status: Vec<u8>,
    metric: Vec<f64>,
    pub flags: Vec<u32>,
    semantic: bool,
}

impl SourceStyle {
    pub fn read(
        doc: &ComposedDocument<'_>,
        side: &str,
        n: usize,
    ) -> Result<Self, InteractionStatus> {
        let read = |key: &str| -> Result<Vec<u8>, InteractionStatus> {
            let values = doc
                .optional_u8s(&format!("{side}.{key}"))
                .map_err(|_| InteractionStatus::Invalid)?
                .map_or_else(|| vec![0; n], <[u8]>::to_vec);
            if values.len() != n || values.iter().any(|&v| v > graph_style::MAX_SEMANTIC_CODE) {
                return invalid();
            }
            Ok(values)
        };
        let metric = doc
            .optional_f64s(&format!("{side}.metric"))
            .map_err(|_| InteractionStatus::Invalid)?
            .unwrap_or_else(|| vec![f64::NAN; n]);
        let flags = doc
            .optional_u32s(&format!("{side}.flags"))
            .map_err(|_| InteractionStatus::Invalid)?
            .unwrap_or_else(|| vec![0; n]);
        if metric.len() != n
            || flags.len() != n
            || flags
                .iter()
                .any(|f| f & !graph_style::KNOWN_STATE_FLAGS != 0)
        {
            return invalid();
        }
        Ok(Self {
            class: read("class")?,
            epistemic: read("epistemic")?,
            status: read("status")?,
            metric,
            flags,
            semantic: doc
                .optional_u8s(&format!("{side}.status"))
                .map_err(|_| InteractionStatus::Invalid)?
                .is_some(),
        })
    }

    pub fn resolve(
        &self,
        flags: &[u32],
        edge: bool,
    ) -> Result<Vec<ResolvedGraphStyle>, InteractionStatus> {
        let mut out = vec![neutral(); self.class.len()];
        let flags: Vec<_> = flags
            .iter()
            .map(|f| f & graph_style::KNOWN_STATE_FLAGS)
            .collect();
        graph_style::resolve_semantic_styles(
            SemanticStyleInput {
                classes: &self.class,
                epistemic: &self.epistemic,
                statuses: &self.status,
                metric: &self.metric,
                flags: &flags,
                edge,
                theme: graph_style::THEME_LIGHT,
            },
            &mut out,
        )
        .ok_or(InteractionStatus::Invalid)?;
        Ok(out)
    }
}

fn neutral() -> ResolvedGraphStyle {
    ResolvedGraphStyle {
        fill: [0; 4],
        stroke: [0; 4],
        halo: [0; 4],
        size: 0.,
        width: 0.,
        opacity: 1.,
        shape: 0,
        dash: 0,
        arrow: 0,
        state: 0,
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct NodePaint {
    pub center: [f64; 2],
    /// Outer diameter; stroke is inset, as the point painter's marker contract.
    pub style: ResolvedGraphStyle,
    pub layers: SemanticPaintLayers,
}

#[derive(Clone, Debug, PartialEq)]
pub struct EdgePiece {
    pub edge: usize,
    pub single_piece: bool,
    pub start: [f64; 2],
    pub end: [f64; 2],
    pub half_width: f64,
    pub dash: (f64, f64),
    /// Dash origin measured from the untrimmed routed piece start.
    pub dash_offset: f64,
    pub head: Option<[[f64; 2]; 3]>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct FramePaint {
    pub node: usize,
    pub bounds: [f64; 4],
    pub half_width: f64,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct PaintGeometry {
    pub nodes: Vec<NodePaint>,
    pub edge_styles: Vec<ResolvedGraphStyle>,
    pub edge_layers: Vec<SemanticPaintLayers>,
    pub pieces: Vec<EdgePiece>,
    pub frames: Vec<FramePaint>,
}

/// Admit the arithmetic used by the canonical outline kernel before clipping
/// can mistake a NaN comparison for a miss (§19). This is session admission,
/// not a replacement span algorithm: legacy painters keep their kernel contract.
fn admit_outline_span(
    shape: NodeShape,
    radius: f64,
    a: (f64, f64),
    d: (f64, f64),
    c: (f64, f64),
) -> Result<(), InteractionStatus> {
    if radius <= 0. {
        return Ok(()); // Canonical no-outline path.
    }
    let (px, py) = (a.0 - c.0, a.1 - c.1);
    if !radius.is_finite() || !px.is_finite() || !py.is_finite() {
        return invalid();
    }
    match shape {
        NodeShape::Circle => {
            // Same operation order as edge_route::node_shape_span, including
            // overflow that could otherwise turn a non-finite discriminant
            // into None or Some((NaN, NaN)).
            let qa = d.0 * d.0 + d.1 * d.1;
            if !qa.is_finite() {
                return invalid();
            }
            if qa <= 0. {
                return Ok(());
            }
            let qb = 2. * (d.0 * px + d.1 * py);
            let qc = px * px + py * py - radius * radius;
            let disc = qb * qb - 4. * qa * qc;
            if [qb, qc, disc, 2. * qa].iter().any(|v| !v.is_finite()) {
                return invalid();
            }
        }
        NodeShape::Square | NodeShape::Diamond => {
            let (normals, limit) = if shape == NodeShape::Square {
                ([(1., 0.), (-1., 0.), (0., 1.), (0., -1.)], radius)
            } else {
                (
                    [(1., 1.), (1., -1.), (-1., 1.), (-1., -1.)],
                    std::f64::consts::SQRT_2 * radius,
                )
            };
            if !limit.is_finite() {
                return invalid();
            }
            for (nx, ny) in normals {
                let base = nx * px + ny * py - limit;
                let slope: f64 = nx * d.0 + ny * d.1;
                if !base.is_finite() || !slope.is_finite() {
                    return invalid();
                }
                if slope.abs() < 1e-12 {
                    if base > 0. {
                        return Ok(()); // Finite canonical early miss.
                    }
                } else if !(-base / slope).is_finite() {
                    return invalid();
                }
            }
        }
    }
    if let Some((lo, hi)) = edge_route::node_shape_span(shape, radius, a, d, c) {
        // Polygon half-plane bounds use ±infinity as unbounded sentinels when
        // every slope is below the canonical parallel tolerance. Those valid
        // occluded tiny chords must remain admitted; divisions above are finite.
        if lo.is_nan()
            || hi.is_nan()
            || (shape == NodeShape::Circle && (!lo.is_finite() || !hi.is_finite()))
        {
            return invalid();
        }
    }
    Ok(())
}

pub(super) fn build(
    session: &GraphSession,
    output: &RenderOutput,
    camera: Option<Camera>,
    node_flags: &[u32],
    edge_flags: &[u32],
    source_node_flags: &[u32],
    source_edge_flags: &[u32],
    visible: &super::render::Visible,
) -> Result<PaintGeometry, InteractionStatus> {
    let source_nodes = session.node_style.resolve(source_node_flags, false)?;
    let source_edges = session.edge_style.resolve(source_edge_flags, true)?;
    let map = |x: f64, y: f64| {
        if let Some(c) = camera {
            [x * c.scale_x + c.offset_x, y * c.scale_y + c.offset_y]
        } else {
            [x, y]
        }
    };
    let mut paint = PaintGeometry::default();
    let aggregate_tier = output.tier == crate::graph::LodTier::Aggregate;
    // Aggregate paint deliberately omits source semantic summaries (§28), using
    // the same resolver's neutral aggregate row, never an arbitrary member.
    let aggregate = |edge: bool, flags: u32| {
        let mut result = [neutral()];
        graph_style::resolve_semantic_styles(
            SemanticStyleInput {
                classes: &[0],
                epistemic: &[0],
                statuses: &[0],
                metric: &[f64::NAN],
                flags: &[flags & graph_style::KNOWN_STATE_FLAGS],
                edge,
                theme: graph_style::THEME_LIGHT,
            },
            &mut result,
        )
        .expect("closed aggregate style");
        result[0]
    };
    for (r, &flags) in node_flags.iter().enumerate() {
        let source = output.focus_node[r] as usize;
        let style = if aggregate_tier {
            aggregate(false, flags)
        } else {
            source_nodes[source]
        };
        let (class, epistemic) = if aggregate_tier {
            (0, 0)
        } else {
            (
                session.node_style.class[source],
                session.node_style.epistemic[source],
            )
        };
        paint.nodes.push(NodePaint {
            center: map(output.node_x[r], output.node_y[r]),
            style,
            layers: graph_style::semantic_paint_layers(&style, class, epistemic, false),
        });
    }
    for (r, &flags) in edge_flags.iter().enumerate() {
        let source = output.members_of_edge(r)[0] as usize;
        let style = if aggregate_tier {
            aggregate(true, flags)
        } else {
            source_edges[source]
        };
        let (class, epistemic) = if aggregate_tier {
            (0, 0)
        } else {
            (
                session.edge_style.class[source],
                session.edge_style.epistemic[source],
            )
        };
        paint.edge_styles.push(style);
        paint.edge_layers.push(graph_style::semantic_paint_layers(
            &style, class, epistemic, true,
        ));
    }
    let radii: Vec<_> = paint
        .nodes
        .iter()
        .map(|n| f64::from(n.style.size) * 0.5)
        .collect();
    let symbols: Vec<_> = paint.nodes.iter().map(|n| n.style.shape).collect();
    // The shared routing kernel skips non-finite geometry. Validate its chord
    // arithmetic here so a session cannot publish that omission as valid (§19).
    for (&s, &t) in output.edge_source.iter().zip(&output.edge_target) {
        let (s, t) = (s as usize, t as usize);
        let dx = output.node_x[t] - output.node_x[s];
        let dy = output.node_y[t] - output.node_y[s];
        if !dx.is_finite() || !dy.is_finite() || !dx.hypot(dy).is_finite() {
            return Err(InteractionStatus::Invalid);
        }
    }
    let cap = output
        .edge_count()
        .checked_mul(edge_route::edge_route_segments_per_edge(false))
        .ok_or(InteractionStatus::Budget)?;
    let (mut x0, mut y0, mut x1, mut y1, mut indices, mut ends) = (
        vec![0.; cap],
        vec![0.; cap],
        vec![0.; cap],
        vec![0.; cap],
        vec![0; cap],
        vec![0.; cap * edge_route::EDGE_ENDS_STRIDE],
    );
    let count = edge_route::edge_route_segments_with_ends(
        output.node_count() as u64,
        &output.node_x,
        &output.node_y,
        &output.edge_source,
        &output.edge_target,
        session.directed,
        0.08,
        0.35,
        false,
        &radii,
        &symbols,
        &mut x0,
        &mut y0,
        &mut x1,
        &mut y1,
        &mut indices,
        &mut ends,
    )
    .ok_or(InteractionStatus::Invalid)? as usize;
    for i in 0..count {
        let edge = indices[i] as usize;
        let (s, t) = (
            output.edge_source[edge] as usize,
            output.edge_target[edge] as usize,
        );
        let (a, b) = (map(x0[i], y0[i]), map(x1[i], y1[i]));
        let d = [b[0] - a[0], b[1] - a[1]];
        let length = (d[0] * d[0] + d[1] * d[1]).sqrt();
        if a.iter().chain(&b).chain(&d).any(|v| !v.is_finite()) || !length.is_finite() {
            return Err(InteractionStatus::Invalid);
        }
        if length <= 0. {
            continue;
        }
        let layers = paint.edge_layers[edge];
        let head = if session.edge_style.semantic {
            layers.head
        } else {
            session.directed
        };
        let flags = ends[i * edge_route::EDGE_ENDS_STRIDE + 6] as u8;
        for node in [s, t] {
            admit_outline_span(
                NodeShape::from_symbol_code(symbols[node]),
                radii[node],
                (a[0], a[1]),
                (d[0], d[1]),
                (paint.nodes[node].center[0], paint.nodes[node].center[1]),
            )?;
        }
        let Some((lo, hi, tip)) = edge_route::clip_edge_piece(
            (a[0], a[1]),
            (b[0], b[1]),
            (paint.nodes[s].center[0], paint.nodes[s].center[1]),
            radii[s],
            NodeShape::from_symbol_code(symbols[s]),
            (paint.nodes[t].center[0], paint.nodes[t].center[1]),
            radii[t],
            NodeShape::from_symbol_code(symbols[t]),
            head,
            flags & edge_route::EDGE_END_TERMINAL != 0,
        ) else {
            continue;
        };
        let at = |v: f64| [a[0] + v * d[0], a[1] + v * d[1]];
        let head = tip.map(|tip| {
            let tip = at(tip);
            let base = [
                tip[0] - d[0] / length * edge_route::GRAPH_EDGE_HEAD_LENGTH_PX,
                tip[1] - d[1] / length * edge_route::GRAPH_EDGE_HEAD_LENGTH_PX,
            ];
            let side = [
                -d[1] / length * edge_route::GRAPH_EDGE_HEAD_HALF_WIDTH_PX,
                d[0] / length * edge_route::GRAPH_EDGE_HEAD_HALF_WIDTH_PX,
            ];
            [
                tip,
                [base[0] + side[0], base[1] + side[1]],
                [base[0] - side[0], base[1] - side[1]],
            ]
        });
        let shaft_hi = if head.is_some() {
            (hi - edge_route::GRAPH_EDGE_HEAD_LENGTH_PX / length).max(lo)
        } else {
            hi
        };
        let width = f64::from(
            paint.edge_styles[edge]
                .width
                .max(if layers.body[3] > 0 {
                    layers.body_width
                } else {
                    0.
                })
                .max(if layers.halo[3] > 0 {
                    layers.halo_extent
                } else {
                    0.
                }),
        );
        paint.pieces.push(EdgePiece {
            edge,
            single_piece: s != t,
            start: at(lo),
            end: at(shaft_hi),
            half_width: width * 0.5,
            dash: (f64::from(layers.dash.0), f64::from(layers.dash.1)),
            dash_offset: lo * length,
            head,
        });
    }
    if output.tier != crate::graph::LodTier::Aggregate && session.parent_valid.contains(&1) {
        let (x, y) = session
            .positions
            .as_ref()
            .ok_or(InteractionStatus::Invalid)?;
        let hierarchy = session.surviving_hierarchy(&visible.node);
        let mask = |v: &[f64]| {
            v.iter()
                .zip(&visible.node)
                .map(|(&v, &on)| if on == 1 { v } else { f64::NAN })
                .collect::<Vec<_>>()
        };
        let frames = graph_style::compound_frames(
            &mask(x),
            &mask(y),
            &source_nodes
                .iter()
                .map(|n| f64::from(n.size) * 0.5)
                .collect::<Vec<_>>(),
            &hierarchy.parent,
            &hierarchy.valid,
            &hierarchy.collapsed,
            &source_nodes.iter().map(|n| n.stroke).collect::<Vec<_>>(),
            &source_nodes.iter().map(|n| n.opacity).collect::<Vec<_>>(),
            graph_style::THEME_LIGHT,
        )
        .ok_or(InteractionStatus::Invalid)?;
        for frame in frames {
            let node = output.member_of[frame.node];
            if node == NOT_RENDERED {
                continue;
            }
            let a = map(frame.bounds[0], frame.bounds[2]);
            let b = map(frame.bounds[1], frame.bounds[3]);
            paint.frames.push(FramePaint {
                node: node as usize,
                bounds: [
                    a[0].min(b[0]) - frame.pad_px,
                    a[1].min(b[1]) - frame.pad_px,
                    a[0].max(b[0]) + frame.pad_px,
                    a[1].max(b[1]) + frame.pad_px,
                ],
                half_width: frame.width_px * 0.5,
            });
        }
    }
    if paint
        .nodes
        .iter()
        .flat_map(|node| node.center)
        .any(|v| !v.is_finite())
        || paint.pieces.iter().any(|piece| {
            piece
                .start
                .iter()
                .chain(&piece.end)
                .chain(piece.head.iter().flatten().flatten())
                .any(|v| !v.is_finite())
        })
        || paint
            .frames
            .iter()
            .flat_map(|frame| frame.bounds)
            .any(|v| !v.is_finite())
    {
        return Err(InteractionStatus::Invalid);
    }
    Ok(paint)
}

#[cfg(test)]
mod outline_admission_tests {
    use super::*;

    #[test]
    fn all_canonical_outlines_admit_real_misses_and_tiny_unbounded_occlusion() {
        for shape in [NodeShape::Circle, NodeShape::Square, NodeShape::Diamond] {
            for (a, d) in [((0., 20.), (1., 0.)), ((20., 20.), (1e-13, 0.))] {
                assert_eq!(edge_route::node_shape_span(shape, 8., a, d, (0., 0.)), None);
                assert_eq!(admit_outline_span(shape, 8., a, d, (0., 0.)), Ok(()));
            }
            assert_eq!(
                admit_outline_span(shape, 0., (0., 0.), (1., 0.), (0., 0.)),
                Ok(())
            );
            let a = (0., 0.);
            let b = (1e-13, 0.);
            assert_eq!(admit_outline_span(shape, 8., a, b, a), Ok(()));
            assert_eq!(admit_outline_span(shape, 8., a, b, b), Ok(()));
            assert_eq!(
                edge_route::clip_edge_piece(a, b, a, 8., shape, b, 8., shape, true, true),
                None
            );
            // A finite line missing both outlines keeps the terminal head.
            assert_eq!(
                admit_outline_span(shape, 8., (0., 20.), (100., 0.), a),
                Ok(())
            );
            assert_eq!(
                admit_outline_span(shape, 8., (0., 20.), (100., 0.), (100., 0.)),
                Ok(())
            );
            assert_eq!(
                edge_route::clip_edge_piece(
                    (0., 20.),
                    (100., 20.),
                    a,
                    8.,
                    shape,
                    (100., 0.),
                    8.,
                    shape,
                    true,
                    true
                ),
                Some((0., 1., Some(1.)))
            );
        }
    }

    #[test]
    fn nonfinite_circle_discriminants_are_invalid_even_when_the_kernel_returns_none() {
        let shape = NodeShape::Circle;
        // +infinity - infinity: a Some((NaN, NaN)) comparison must not hide a head.
        assert_eq!(
            admit_outline_span(shape, 8., (0., 0.), (1e80, 0.), (1e80, 0.)),
            Err(InteractionStatus::Invalid)
        );
        // Negative-infinite discriminant otherwise masquerades as a true miss.
        assert_eq!(
            edge_route::node_shape_span(shape, 8., (0., 1e80), (1e80, 0.), (0., 0.)),
            None
        );
        assert_eq!(
            admit_outline_span(shape, 8., (0., 1e80), (1e80, 0.), (0., 0.)),
            Err(InteractionStatus::Invalid)
        );
    }

    #[test]
    fn polygon_offset_half_plane_and_division_overflow_are_invalid() {
        for shape in [NodeShape::Square, NodeShape::Diamond] {
            assert_eq!(
                admit_outline_span(shape, 8., (-f64::MAX, 0.), (1., 0.), (f64::MAX, 0.)),
                Err(InteractionStatus::Invalid)
            );
            assert_eq!(
                admit_outline_span(shape, 8., (1e308, 0.), (1e-12, 0.), (0., 0.)),
                Err(InteractionStatus::Invalid)
            );
        }
        assert_eq!(
            admit_outline_span(NodeShape::Diamond, 8., (1e308, 1e308), (1., 0.), (0., 0.)),
            Err(InteractionStatus::Invalid)
        );
    }
}
