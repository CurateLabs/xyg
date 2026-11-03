//! Property-only presentation from the existing public graph authorities.
use super::*;
use crate::graph_scene::{graph_home_domain, ComposedGraphPlanes, GraphHomeLayout};

pub(super) struct PropertyPresentation {
    pub domain: [f64; 4],
    pub layout: PlotLayout,
    pub x: Vec<f64>,
    pub y: Vec<f64>,
    pub plan: Vec<GraphLabelPlan>,
    pub texts: Vec<String>,
}

type Route = (f64, f64, f64, f64);

pub(super) fn property_graph_presentation(
    input: &SemanticGraphSceneInput<'_>,
    nodes: &[ResolvedGraphStyle],
    edges: &[ResolvedGraphStyle],
    routes: &[Vec<Route>],
    priorities: (&[f64], &[f64]),
) -> Result<PropertyPresentation, SceneError> {
    let n = nodes.len();
    let e = edges.len();
    if priorities.0.len() != n || priorities.1.len() != e {
        return Err(SceneError::Length);
    }
    let mut x = input.x.to_vec();
    let mut y = input.y.to_vec();
    let mut x0 = Vec::new();
    let mut y0 = Vec::new();
    let mut x1 = Vec::new();
    let mut y1 = Vec::new();
    let mut widths = Vec::new();
    let mut anchors = Vec::new();
    for (i, pieces) in routes.iter().enumerate() {
        anchors.push(x0.len() + pieces.len() / 2);
        let mid = pieces
            .get(pieces.len() / 2)
            .copied()
            .unwrap_or((0.0, 0.0, 0.0, 0.0));
        x.push((mid.0 + mid.2) * 0.5);
        y.push((mid.1 + mid.3) * 0.5);
        for &(a, b, c, d) in pieces {
            x0.push(a);
            y0.push(b);
            x1.push(c);
            y1.push(d);
            widths.push(f64::from(edges[i].width));
        }
    }
    let mut kinds = vec![GRAPH_LABEL_KIND_NODE; n];
    kinds.extend(vec![GRAPH_LABEL_KIND_EDGE; e]);
    let mut radius: Vec<f64> = nodes.iter().map(|s| f64::from(s.size) * 0.5).collect();
    radius.resize(n + e, 0.0);
    let labels: Vec<&str> = input
        .node_labels
        .iter()
        .chain(input.edge_labels)
        .copied()
        .collect();
    let chars: Vec<u32> = labels.iter().map(|s| s.chars().count() as u32).collect();
    let mut states: Vec<u8> = nodes.iter().map(|s| s.state).collect();
    // The public graph uses normal state for relationship-label candidates.
    states.resize(n + e, STATE_NORMAL);
    let priorities: Vec<f64> = priorities.0.iter().chain(priorities.1).copied().collect();
    let mut plan = vec![
        GraphLabelPlan {
            keep: 0,
            threshold: f64::INFINITY,
            offset_x: 0.0,
            offset_y: 0.0,
            width: 0.0,
            font_px: 0.0
        };
        n + e
    ];
    graph_label_plan(
        &GraphLabelPlanInput {
            kinds: &kinds,
            x: &x,
            y: &y,
            radius_px: &radius,
            chars: &chars,
            states: &states,
            priorities: &priorities,
            budget: 64,
            floor: f64::NEG_INFINITY,
        },
        &mut plan,
    )
    .ok_or(SceneError::Length)?;
    let texts: Vec<String> = labels
        .iter()
        .zip(&plan)
        .map(|(full, p)| {
            let mut text: String = full.chars().take(p.keep as usize).collect();
            if p.keep > 0 && (p.keep as usize) < full.chars().count() {
                text.push('…');
            }
            text
        })
        .collect();
    let rows: Vec<f64> = plan
        .iter()
        .flat_map(|p| {
            [
                if p.keep > 0 && p.threshold.is_finite() {
                    p.threshold
                } else {
                    -1.0
                },
                p.offset_x,
                p.offset_y,
                p.width,
                p.font_px,
            ]
        })
        .collect();
    let node_texts: Vec<Option<&str>> = texts[..n]
        .iter()
        .map(|s| (!s.is_empty()).then_some(s.as_str()))
        .collect();
    let mut edge_rows = vec![0.0; x0.len() * 5];
    let mut edge_texts = vec![None; x0.len()];
    for (i, &anchor) in anchors.iter().enumerate() {
        if routes[i].is_empty() {
            continue;
        }
        edge_rows[anchor * 5..anchor * 5 + 5].copy_from_slice(&rows[(n + i) * 5..(n + i + 1) * 5]);
        edge_texts[anchor] = (!texts[n + i].is_empty()).then_some(texts[n + i].as_str());
    }
    let diameter: Vec<f64> = nodes.iter().map(|s| f64::from(s.size)).collect();
    let stroke: Vec<f64> = nodes.iter().map(|s| f64::from(s.width)).collect();
    let symbols: Vec<u8> = nodes.iter().map(|s| s.shape).collect();
    let bounds = |values: &[f64], starts: &[f64], ends: &[f64]| {
        let (lo, hi) = metric_domain(
            &values
                .iter()
                .chain(starts)
                .chain(ends)
                .copied()
                .collect::<Vec<_>>(),
        );
        crate::autorange::default_linear_domain(lo, hi)
    };
    let shell = GraphHomeLayout {
        viewport_width: input.width,
        viewport_height: input.height,
        padding: None,
        title: input.title,
        base_x: bounds(input.x, &x0, &x1),
        base_y: bounds(input.y, &y0, &y1),
    };
    let planes = ComposedGraphPlanes {
        x: input.x,
        y: input.y,
        diameter: &diameter,
        symbol: &symbols,
        stroke_width: &stroke,
        node_label_plan: &rows[..n * 5],
        node_labels: &node_texts,
        x0: &x0,
        y0: &y0,
        x1: &x1,
        y1: &y1,
        segment_width: &widths,
        segment_label_plan: &edge_rows,
        segment_labels: &edge_texts,
        ..ComposedGraphPlanes::default()
    };
    let domain = graph_home_domain(&planes, &shell).unwrap_or([
        shell.base_x.0,
        shell.base_x.1,
        shell.base_y.0,
        shell.base_y.1,
    ]);
    let layout = shell.plot(domain)?;
    Ok(PropertyPresentation {
        domain,
        layout,
        x,
        y,
        plan,
        texts,
    })
}
