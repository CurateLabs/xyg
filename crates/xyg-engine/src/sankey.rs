//! Sankey flow layout — layering, alignment, barycentre crossing
//! minimisation, value-proportional placement, and ribbon endpoint stacking.
//!
//! Hosts resolve names to dense u64 indices and assemble error *text*; this
//! module owns every placement decision so Python and Node stay bit-identical
//! ([host-parity.md](../../spec/design/host-parity.md)).

use std::collections::{HashSet, VecDeque};

/// Flush sinks to the last layer (d3-sankey default).
pub const ALIGN_JUSTIFY: u32 = 0;
/// Keep longest-path layering as assigned.
pub const ALIGN_LEFT: u32 = 1;
/// Hang every node by its distance to a sink.
pub const ALIGN_RIGHT: u32 = 2;
/// Move source-only nodes just left of their nearest target.
pub const ALIGN_CENTER: u32 = 3;

/// Layout refusal / argument failure. Hosts map these to typed errors.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum LayoutError {
    /// Null/mismatched lengths, out-of-range indices, bad align, empty graph,
    /// non-finite/negative values, self-links, duplicates, or bad geometry params.
    Invalid,
    /// Acyclic layering failed; indices are the nodes that lie on a cycle
    /// (Tarjan SCCs with size > 1), unsorted — host sorts names for the message.
    Cycle(Vec<u64>),
    /// `node_padding` leaves no positive room in `layer` (which holds `count` nodes).
    Padding { layer: u32, count: u32 },
}

/// Placed Sankey in a 0..1 × 0..1 box. All vectors are dense by node/link index.
#[derive(Clone, Debug)]
pub struct Layout {
    pub x0: Vec<f64>,
    pub y0: Vec<f64>,
    pub x1: Vec<f64>,
    pub y1: Vec<f64>,
    pub layer: Vec<u32>,
    pub value: Vec<f64>,
    pub source_y0: Vec<f64>,
    pub source_y1: Vec<f64>,
    pub target_y0: Vec<f64>,
    pub target_y1: Vec<f64>,
    /// Number of columns (= max layer + 1).
    pub layers: u32,
}

#[derive(Clone)]
struct Node {
    layer: u32,
    order: u32,
    value: f64,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    incoming: Vec<usize>,
    outgoing: Vec<usize>,
}

#[derive(Clone)]
struct Link {
    source: usize,
    target: usize,
    value: f64,
    index: usize,
    source_y0: f64,
    source_y1: f64,
    target_y0: f64,
    target_y1: f64,
}

/// Place a Sankey given dense u64 endpoint indices and f64 link weights.
///
/// `sources`, `targets`, and `values` must share length `n_links`. Node indices
/// must be in `0..n_nodes`. `align` is one of [`ALIGN_JUSTIFY`]…[`ALIGN_CENTER`].
pub fn compute_layout(
    n_nodes: usize,
    sources: &[u64],
    targets: &[u64],
    values: &[f64],
    node_width: f64,
    node_padding: f64,
    align: u32,
    iterations: u32,
) -> Result<Layout, LayoutError> {
    let n_links = sources.len();
    if targets.len() != n_links || values.len() != n_links {
        return Err(LayoutError::Invalid);
    }
    if n_links == 0 || n_nodes == 0 {
        return Err(LayoutError::Invalid);
    }
    if !(align <= ALIGN_CENTER) {
        return Err(LayoutError::Invalid);
    }
    if !(node_width > 0.0 && node_width < 1.0 && node_width.is_finite()) {
        return Err(LayoutError::Invalid);
    }
    if !(node_padding >= 0.0 && node_padding < 1.0 && node_padding.is_finite()) {
        return Err(LayoutError::Invalid);
    }

    let mut nodes: Vec<Node> = (0..n_nodes)
        .map(|_| Node {
            layer: 0,
            order: 0,
            value: 0.0,
            x0: 0.0,
            x1: 0.0,
            y0: 0.0,
            y1: 0.0,
            incoming: Vec::new(),
            outgoing: Vec::new(),
        })
        .collect();
    let mut links: Vec<Link> = Vec::with_capacity(n_links);
    let mut seen: HashSet<(usize, usize)> = HashSet::with_capacity(n_links);

    for i in 0..n_links {
        let s = sources[i];
        let t = targets[i];
        if s >= n_nodes as u64 || t >= n_nodes as u64 {
            return Err(LayoutError::Invalid);
        }
        let si = s as usize;
        let ti = t as usize;
        if si == ti {
            return Err(LayoutError::Invalid);
        }
        let weight = values[i];
        if !weight.is_finite() || weight < 0.0 {
            return Err(LayoutError::Invalid);
        }
        if !seen.insert((si, ti)) {
            return Err(LayoutError::Invalid);
        }
        let index = links.len();
        nodes[si].outgoing.push(index);
        nodes[ti].incoming.push(index);
        links.push(Link {
            source: si,
            target: ti,
            value: weight,
            index,
            source_y0: 0.0,
            source_y1: 0.0,
            target_y0: 0.0,
            target_y1: 0.0,
        });
    }

    let layers = assign_layers(&mut nodes, &links)?;
    align_nodes(&mut nodes, &links, layers, align);
    for node in &mut nodes {
        let inflow: f64 = node.incoming.iter().map(|&i| links[i].value).sum();
        let outflow: f64 = node.outgoing.iter().map(|&i| links[i].value).sum();
        node.value = inflow.max(outflow);
    }
    let columns = order_layers(&mut nodes, &links, layers, iterations);
    place(&mut nodes, &columns, layers, node_width, node_padding)?;
    stack_endpoints(&nodes, &mut links);

    Ok(Layout {
        x0: nodes.iter().map(|n| n.x0).collect(),
        y0: nodes.iter().map(|n| n.y0).collect(),
        x1: nodes.iter().map(|n| n.x1).collect(),
        y1: nodes.iter().map(|n| n.y1).collect(),
        layer: nodes.iter().map(|n| n.layer).collect(),
        value: nodes.iter().map(|n| n.value).collect(),
        source_y0: links.iter().map(|l| l.source_y0).collect(),
        source_y1: links.iter().map(|l| l.source_y1).collect(),
        target_y0: links.iter().map(|l| l.target_y0).collect(),
        target_y1: links.iter().map(|l| l.target_y1).collect(),
        layers,
    })
}

/// Names of the nodes that actually lie on a cycle (Tarjan SCCs).
fn cyclic_nodes(nodes: &[Node], links: &[Link]) -> Vec<u64> {
    let n = nodes.len();
    let mut order = vec![-1i32; n];
    let mut low = vec![0i32; n];
    let mut on_stack = vec![false; n];
    let mut stack: Vec<usize> = Vec::new();
    let mut count = 0i32;
    let mut cyclic: Vec<u64> = Vec::new();

    for root in 0..n {
        if order[root] != -1 {
            continue;
        }
        let mut work: Vec<(usize, usize)> = vec![(root, 0)];
        while let Some((current, mut edge)) = work.pop() {
            if edge == 0 {
                order[current] = count;
                low[current] = count;
                count += 1;
                stack.push(current);
                on_stack[current] = true;
            }
            let mut descended = false;
            let outgoing = &nodes[current].outgoing;
            while edge < outgoing.len() {
                let child = links[outgoing[edge]].target;
                edge += 1;
                if order[child] == -1 {
                    work.push((current, edge));
                    work.push((child, 0));
                    descended = true;
                    break;
                }
                if on_stack[child] {
                    low[current] = low[current].min(order[child]);
                }
            }
            if descended {
                continue;
            }
            if low[current] == order[current] {
                let mut component: Vec<usize> = Vec::new();
                loop {
                    let member = stack.pop().expect("SCC stack non-empty");
                    on_stack[member] = false;
                    component.push(member);
                    if member == current {
                        break;
                    }
                }
                if component.len() > 1 {
                    cyclic.extend(component.into_iter().map(|m| m as u64));
                }
            }
            if let Some(&(parent, _)) = work.last() {
                low[parent] = low[parent].min(low[current]);
            }
        }
    }
    cyclic
}

fn assign_layers(nodes: &mut [Node], links: &[Link]) -> Result<u32, LayoutError> {
    let n = nodes.len();
    let mut indegree = vec![0u32; n];
    for link in links {
        indegree[link.target] += 1;
    }
    let mut queue: VecDeque<usize> = (0..n).filter(|&i| indegree[i] == 0).collect();
    let mut placed = 0usize;
    while let Some(current) = queue.pop_front() {
        placed += 1;
        let layer = nodes[current].layer;
        // Collect targets first so we do not hold a borrow across mutation.
        let outs: Vec<(usize, u32)> = nodes[current]
            .outgoing
            .iter()
            .map(|&li| (links[li].target, layer + 1))
            .collect();
        for (target, candidate) in outs {
            if nodes[target].layer < candidate {
                nodes[target].layer = candidate;
            }
            indegree[target] -= 1;
            if indegree[target] == 0 {
                queue.push_back(target);
            }
        }
    }
    if placed != n {
        return Err(LayoutError::Cycle(cyclic_nodes(nodes, links)));
    }
    let max_layer = nodes.iter().map(|n| n.layer).max().unwrap_or(0);
    Ok(max_layer + 1)
}

fn heights(nodes: &[Node], links: &[Link]) -> Vec<u32> {
    let n = nodes.len();
    let mut outdegree: Vec<u32> = nodes.iter().map(|n| n.outgoing.len() as u32).collect();
    let mut height = vec![0u32; n];
    let mut queue: VecDeque<usize> = (0..n).filter(|&i| outdegree[i] == 0).collect();
    while let Some(current) = queue.pop_front() {
        let h = height[current];
        let ins: Vec<usize> = nodes[current]
            .incoming
            .iter()
            .map(|&li| links[li].source)
            .collect();
        for source in ins {
            let candidate = h + 1;
            if height[source] < candidate {
                height[source] = candidate;
            }
            outdegree[source] -= 1;
            if outdegree[source] == 0 {
                queue.push_back(source);
            }
        }
    }
    height
}

fn align_nodes(nodes: &mut [Node], links: &[Link], layers: u32, alignment: u32) {
    if alignment == ALIGN_LEFT || layers < 2 {
        return;
    }
    match alignment {
        ALIGN_JUSTIFY => {
            for node in nodes.iter_mut() {
                if node.outgoing.is_empty() {
                    node.layer = layers - 1;
                }
            }
        }
        ALIGN_RIGHT => {
            let height = heights(nodes, links);
            for (i, node) in nodes.iter_mut().enumerate() {
                node.layer = layers - 1 - height[i];
            }
        }
        ALIGN_CENTER => {
            for i in 0..nodes.len() {
                if nodes[i].incoming.is_empty() && !nodes[i].outgoing.is_empty() {
                    let nearest = nodes[i]
                        .outgoing
                        .iter()
                        .map(|&li| nodes[links[li].target].layer)
                        .min()
                        .unwrap_or(0);
                    nodes[i].layer = nearest.saturating_sub(1);
                }
            }
        }
        _ => {}
    }
}

fn order_layers(
    nodes: &mut [Node],
    links: &[Link],
    layers: u32,
    iterations: u32,
) -> Vec<Vec<usize>> {
    let layers = layers as usize;
    let mut columns: Vec<Vec<usize>> = vec![Vec::new(); layers];
    for (i, node) in nodes.iter().enumerate() {
        columns[node.layer as usize].push(i);
    }
    for column in &mut columns {
        column.sort_unstable();
    }

    let positions = |columns: &[Vec<usize>]| -> Vec<f64> {
        let mut ranks = vec![0.0; nodes.len()];
        for column in columns {
            for (rank, &index) in column.iter().enumerate() {
                ranks[index] = rank as f64;
            }
        }
        ranks
    };

    for sweep in 0..iterations {
        let forward = sweep % 2 == 0;
        let order: Vec<usize> = if forward {
            (1..layers).collect()
        } else {
            (0..layers.saturating_sub(1)).rev().collect()
        };
        let mut pos = positions(&columns);
        for layer in order {
            let incoming = forward;
            columns[layer].sort_by(|&a, &b| {
                let ba = barycentre(a, incoming, nodes, links, &pos);
                let bb = barycentre(b, incoming, nodes, links, &pos);
                ba.partial_cmp(&bb).unwrap_or(std::cmp::Ordering::Equal)
            });
            pos = positions(&columns);
        }
    }
    for column in &columns {
        for (rank, &index) in column.iter().enumerate() {
            nodes[index].order = rank as u32;
        }
    }
    columns
}

fn barycentre(index: usize, incoming: bool, nodes: &[Node], links: &[Link], ranks: &[f64]) -> f64 {
    let related = if incoming {
        &nodes[index].incoming
    } else {
        &nodes[index].outgoing
    };
    if related.is_empty() {
        return ranks.get(index).copied().unwrap_or(0.0);
    }
    let mut sum = 0.0;
    for &li in related {
        let other = if incoming {
            links[li].source
        } else {
            links[li].target
        };
        sum += ranks.get(other).copied().unwrap_or(0.0);
    }
    sum / related.len() as f64
}

fn place(
    nodes: &mut [Node],
    columns: &[Vec<usize>],
    layers: u32,
    node_width: f64,
    node_padding: f64,
) -> Result<(), LayoutError> {
    let mut spans: Vec<(f64, usize)> = Vec::new();
    for (layer, column) in columns.iter().enumerate() {
        if column.is_empty() {
            continue;
        }
        let room = 1.0 - node_padding * (column.len() as f64 - 1.0);
        if room <= 0.0 {
            return Err(LayoutError::Padding {
                layer: layer as u32,
                count: column.len() as u32,
            });
        }
        let total: f64 = column.iter().map(|&i| nodes[i].value).sum();
        spans.push((total, column.len()));
    }
    if spans.is_empty() {
        return Ok(());
    }
    let mut scale = f64::INFINITY;
    for &(total, count) in &spans {
        let room = 1.0 - node_padding * (count as f64 - 1.0);
        let candidate = if total > 0.0 {
            room / total
        } else {
            f64::INFINITY
        };
        if candidate < scale {
            scale = candidate;
        }
    }
    if !scale.is_finite() {
        scale = 0.0;
    }

    let step = if layers <= 1 {
        1.0
    } else {
        (1.0 - node_width) / (layers as f64 - 1.0)
    };
    for (layer, column) in columns.iter().enumerate() {
        if column.is_empty() {
            continue;
        }
        let heights: Vec<f64> = column.iter().map(|&i| nodes[i].value * scale).collect();
        let extent: f64 = heights.iter().sum::<f64>() + node_padding * (column.len() as f64 - 1.0);
        let mut cursor = (1.0 - extent) / 2.0;
        for (&index, &height) in column.iter().zip(heights.iter()) {
            let node = &mut nodes[index];
            node.x0 = layer as f64 * step;
            node.x1 = node.x0 + node_width;
            node.y0 = cursor;
            node.y1 = cursor + height;
            cursor = node.y1 + node_padding;
        }
    }
    Ok(())
}

fn stack_endpoints(nodes: &[Node], links: &mut [Link]) {
    for node in nodes {
        let mut outgoing = node.outgoing.clone();
        outgoing.sort_by(|&a, &b| {
            let ya = nodes[links[a].target].y0;
            let yb = nodes[links[b].target].y0;
            ya.partial_cmp(&yb)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| links[a].index.cmp(&links[b].index))
        });
        let mut cursor = node.y0;
        for &link_index in &outgoing {
            let height = if node.value > 0.0 {
                (node.y1 - node.y0) * (links[link_index].value / node.value)
            } else {
                0.0
            };
            links[link_index].source_y0 = cursor;
            links[link_index].source_y1 = cursor + height;
            cursor = links[link_index].source_y1;
        }

        let mut incoming = node.incoming.clone();
        incoming.sort_by(|&a, &b| {
            let ya = nodes[links[a].source].y0;
            let yb = nodes[links[b].source].y0;
            ya.partial_cmp(&yb)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| links[a].index.cmp(&links[b].index))
        });
        cursor = node.y0;
        for &link_index in &incoming {
            let height = if node.value > 0.0 {
                (node.y1 - node.y0) * (links[link_index].value / node.value)
            } else {
                0.0
            };
            links[link_index].target_y0 = cursor;
            links[link_index].target_y1 = cursor + height;
            cursor = links[link_index].target_y1;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn three_node_chain_layers_and_values() {
        // a -> b (5), b -> c (9): b's value is max(5, 9) = 9.
        let sources = [0u64, 1];
        let targets = [1u64, 2];
        let values = [5.0, 9.0];
        let layout = compute_layout(3, &sources, &targets, &values, 0.02, 0.02, ALIGN_JUSTIFY, 6)
            .expect("layout");
        assert_eq!(layout.layers, 3);
        assert_eq!(layout.layer, vec![0, 1, 2]);
        assert_eq!(layout.value[0], 5.0);
        assert_eq!(layout.value[1], 9.0);
        assert_eq!(layout.value[2], 9.0);
        // Node rectangles are non-degenerate and ordered left-to-right.
        assert!(layout.x0[0] < layout.x0[1] && layout.x0[1] < layout.x0[2]);
        assert!(layout.y1[1] - layout.y0[1] > layout.y1[0] - layout.y0[0]);
        // Ribbon widths match at both ends.
        for i in 0..2 {
            let sh = layout.source_y1[i] - layout.source_y0[i];
            let th = layout.target_y1[i] - layout.target_y0[i];
            assert!((sh - th).abs() < 1e-12);
        }
    }

    #[test]
    fn cycle_returns_cycle_members() {
        let sources = [0u64, 1];
        let targets = [1u64, 0];
        let values = [1.0, 1.0];
        match compute_layout(2, &sources, &targets, &values, 0.02, 0.02, ALIGN_LEFT, 6) {
            Err(LayoutError::Cycle(ids)) => {
                let mut ids = ids;
                ids.sort_unstable();
                assert_eq!(ids, vec![0, 1]);
            }
            other => panic!("expected cycle, got {other:?}"),
        }
    }

    #[test]
    fn padding_refusal_names_layer() {
        // Three mid-layer nodes with padding 0.6 leave no room.
        let sources = [0u64, 0, 0, 1, 1, 2, 2, 3];
        let targets = [1u64, 2, 3, 4, 5, 5, 6, 6];
        let values = [
            78000.0, 46000.0, 24000.0, 61000.0, 17000.0, 28000.0, 18000.0, 24000.0,
        ];
        match compute_layout(7, &sources, &targets, &values, 0.02, 0.6, ALIGN_JUSTIFY, 6) {
            Err(LayoutError::Padding { layer, count }) => {
                assert_eq!(layer, 1);
                assert_eq!(count, 3);
            }
            other => panic!("expected padding error, got {other:?}"),
        }
    }
}
