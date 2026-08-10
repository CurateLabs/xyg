//! Graph display layouts, CSR, force ticks, and LOD helpers.
//!
//! Analysis algorithms stay in GraphForge; this module only positions and
//! aggregates for visualization ([graph-mark.md]). Element indices are u64.

use std::collections::{HashMap, VecDeque};
use std::sync::{Mutex, OnceLock};

/// Layout algorithm ids for the C ABI (`layout=` names map in the host).
pub const LAYOUT_PRESET: u32 = 0;
pub const LAYOUT_GRID: u32 = 1;
pub const LAYOUT_CIRCLE: u32 = 2;
pub const LAYOUT_FORCE: u32 = 3;
pub const LAYOUT_BREADTHFIRST: u32 = 4;
pub const LAYOUT_AUTO: u32 = 5;
pub const LAYOUT_RADIAL: u32 = 6;
pub const LAYOUT_CONCENTRIC: u32 = 7;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LodTier {
    Direct = 0,
    EdgeSample = 1,
    Aggregate = 2,
}

/// Recorded graph LOD decision (§28).
#[derive(Clone, Copy, Debug)]
pub struct LodDecision {
    pub tier: LodTier,
    pub n_nodes: u64,
    pub n_edges: u64,
    pub edge_budget: u64,
    pub node_budget: u64,
    pub edges_kept: u64,
}

pub fn lod_decide(n_nodes: u64, n_edges: u64, node_budget: u64, edge_budget: u64) -> LodDecision {
    let node_budget = node_budget.max(1);
    let edge_budget = edge_budget.max(1);
    if n_nodes > node_budget {
        LodDecision {
            tier: LodTier::Aggregate,
            n_nodes,
            n_edges,
            edge_budget,
            node_budget,
            edges_kept: n_edges.min(edge_budget),
        }
    } else if n_edges > edge_budget {
        LodDecision {
            tier: LodTier::EdgeSample,
            n_nodes,
            n_edges,
            edge_budget,
            node_budget,
            edges_kept: edge_budget,
        }
    } else {
        LodDecision {
            tier: LodTier::Direct,
            n_nodes,
            n_edges,
            edge_budget,
            node_budget,
            edges_kept: n_edges,
        }
    }
}

/// Build CSR offsets (len = n_nodes+1) and flat neighbor list (undirected
/// doubles edges). `sources`/`targets` are dense u64 node indices.
pub fn build_csr(
    n_nodes: u64,
    sources: &[u64],
    targets: &[u64],
    directed: bool,
) -> Option<(Vec<u64>, Vec<u64>)> {
    if sources.len() != targets.len() {
        return None;
    }
    let n = n_nodes as usize;
    if n_nodes > (usize::MAX as u64) {
        return None;
    }
    let mut deg = vec![0u64; n];
    for (&s, &t) in sources.iter().zip(targets.iter()) {
        if s >= n_nodes || t >= n_nodes {
            return None;
        }
        deg[s as usize] = deg[s as usize].saturating_add(1);
        if !directed && s != t {
            deg[t as usize] = deg[t as usize].saturating_add(1);
        }
    }
    let mut offsets = vec![0u64; n + 1];
    for i in 0..n {
        offsets[i + 1] = offsets[i].saturating_add(deg[i]);
    }
    let total = offsets[n] as usize;
    let mut neighbors = vec![0u64; total];
    let mut cursor = offsets[..n].to_vec();
    for (&s, &t) in sources.iter().zip(targets.iter()) {
        let si = s as usize;
        let slot = cursor[si] as usize;
        neighbors[slot] = t;
        cursor[si] = cursor[si].saturating_add(1);
        if !directed && s != t {
            let ti = t as usize;
            let slot = cursor[ti] as usize;
            neighbors[slot] = s;
            cursor[ti] = cursor[ti].saturating_add(1);
        }
    }
    Some((offsets, neighbors))
}

pub fn layout_grid(n: usize, out_x: &mut [f64], out_y: &mut [f64]) {
    let cols = (n as f64).sqrt().ceil().max(1.0) as usize;
    for i in 0..n {
        out_x[i] = (i % cols) as f64;
        out_y[i] = (i / cols) as f64;
    }
}

pub fn layout_circle(n: usize, out_x: &mut [f64], out_y: &mut [f64]) {
    if n == 0 {
        return;
    }
    let r = (n as f64).max(1.0);
    for i in 0..n {
        let a = std::f64::consts::TAU * (i as f64) / (n as f64);
        out_x[i] = r * a.cos();
        out_y[i] = r * a.sin();
    }
}

pub fn layout_preset(x: &[f64], y: &[f64], out_x: &mut [f64], out_y: &mut [f64]) -> bool {
    if x.len() != out_x.len() || y.len() != out_y.len() || x.len() != y.len() {
        return false;
    }
    out_x.copy_from_slice(x);
    out_y.copy_from_slice(y);
    true
}

pub fn layout_breadthfirst(
    n_nodes: u64,
    sources: &[u64],
    targets: &[u64],
    roots: &[u64],
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> bool {
    let n = n_nodes as usize;
    if out_x.len() != n || out_y.len() != n {
        return false;
    }
    let Some((offsets, neighbors)) = build_csr(n_nodes, sources, targets, false) else {
        return false;
    };
    let mut layer = vec![-1i32; n];
    let mut q = VecDeque::new();
    let seed_roots: Vec<u64> = if roots.is_empty() {
        vec![0]
    } else {
        roots.to_vec()
    };
    for &r in &seed_roots {
        if r >= n_nodes {
            return false;
        }
        let ri = r as usize;
        if layer[ri] < 0 {
            layer[ri] = 0;
            q.push_back(r);
        }
    }
    while let Some(u) = q.pop_front() {
        let ui = u as usize;
        let start = offsets[ui] as usize;
        let end = offsets[ui + 1] as usize;
        for &v in &neighbors[start..end] {
            let vi = v as usize;
            if layer[vi] < 0 {
                layer[vi] = layer[ui] + 1;
                q.push_back(v);
            }
        }
    }
    // Unreachable nodes get a late layer.
    let mut max_layer = 0i32;
    for layer_slot in layer.iter_mut() {
        if *layer_slot < 0 {
            *layer_slot = i32::MAX / 4;
        }
        max_layer = max_layer.max(*layer_slot);
    }
    let mut per_layer: HashMap<i32, u64> = HashMap::new();
    for &layer_id in &layer {
        *per_layer.entry(layer_id).or_insert(0) += 1;
    }
    let mut seen: HashMap<i32, u64> = HashMap::new();
    for i in 0..n {
        let layer_id = layer[i];
        let idx = *seen.get(&layer_id).unwrap_or(&0);
        *seen.entry(layer_id).or_insert(0) += 1;
        let count = *per_layer.get(&layer_id).unwrap_or(&1);
        out_x[i] = if count <= 1 {
            0.0
        } else {
            (idx as f64) - 0.5 * ((count - 1) as f64)
        };
        out_y[i] = -(layer_id as f64);
    }
    let _ = max_layer;
    true
}

/// Seeded Fruchterman–Reingold state for progressive ticks.
pub struct ForceState {
    pub n: usize,
    pub edges: Vec<(u64, u64)>,
    pub x: Vec<f64>,
    pub y: Vec<f64>,
    pub vx: Vec<f64>,
    pub vy: Vec<f64>,
    pub alpha: f64,
    pub area: f64,
    pub k: f64,
    pub seed: u64,
    pub rng: u64,
}

fn splitmix64(state: &mut u64) -> u64 {
    *state = state.wrapping_add(0x9E3779B97F4A7C15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
    z ^ (z >> 31)
}

fn rand01(state: &mut u64) -> f64 {
    (splitmix64(state) as f64) / (u64::MAX as f64)
}

impl ForceState {
    pub fn new(
        n_nodes: u64,
        sources: &[u64],
        targets: &[u64],
        init_x: Option<&[f64]>,
        init_y: Option<&[f64]>,
        seed: u64,
    ) -> Option<Self> {
        let n = n_nodes as usize;
        if sources.len() != targets.len() || n_nodes > (usize::MAX as u64) {
            return None;
        }
        for (&s, &t) in sources.iter().zip(targets.iter()) {
            if s >= n_nodes || t >= n_nodes {
                return None;
            }
        }
        let mut rng = seed | 1;
        let mut x = vec![0.0; n];
        let mut y = vec![0.0; n];
        if let (Some(ix), Some(iy)) = (init_x, init_y) {
            if ix.len() != n || iy.len() != n {
                return None;
            }
            x.copy_from_slice(ix);
            y.copy_from_slice(iy);
        } else {
            layout_circle(n, &mut x, &mut y);
            for i in 0..n {
                x[i] += 0.01 * (rand01(&mut rng) - 0.5);
                y[i] += 0.01 * (rand01(&mut rng) - 0.5);
            }
        }
        let edges: Vec<(u64, u64)> = sources
            .iter()
            .zip(targets.iter())
            .map(|(&s, &t)| (s, t))
            .collect();
        let area = (n as f64).max(1.0);
        let k = (area / (n as f64).max(1.0)).sqrt();
        Some(Self {
            n,
            edges,
            x,
            y,
            vx: vec![0.0; n],
            vy: vec![0.0; n],
            alpha: 1.0,
            area,
            k,
            seed,
            rng,
        })
    }

    pub fn tick(&mut self, steps: u32) {
        let n = self.n;
        if n == 0 {
            return;
        }
        for _ in 0..steps {
            if self.alpha < 0.001 {
                break;
            }
            let mut fx = vec![0.0; n];
            let mut fy = vec![0.0; n];
            // Repulsion
            for i in 0..n {
                for j in (i + 1)..n {
                    let dx = self.x[i] - self.x[j];
                    let dy = self.y[i] - self.y[j];
                    let dist2 = dx * dx + dy * dy + 1e-8;
                    let dist = dist2.sqrt();
                    let force = (self.k * self.k) / dist;
                    let fx_i = force * dx / dist;
                    let fy_i = force * dy / dist;
                    fx[i] += fx_i;
                    fy[i] += fy_i;
                    fx[j] -= fx_i;
                    fy[j] -= fy_i;
                }
            }
            // Attraction along edges
            for &(s, t) in &self.edges {
                let i = s as usize;
                let j = t as usize;
                let dx = self.x[i] - self.x[j];
                let dy = self.y[i] - self.y[j];
                let dist = (dx * dx + dy * dy).sqrt().max(1e-8);
                let force = (dist * dist) / self.k;
                let fx_i = force * dx / dist;
                let fy_i = force * dy / dist;
                fx[i] -= fx_i;
                fy[i] -= fy_i;
                fx[j] += fx_i;
                fy[j] += fy_i;
            }
            let temp = self.alpha * (self.area.sqrt());
            for i in 0..n {
                let mut dx = fx[i];
                let mut dy = fy[i];
                let mag = (dx * dx + dy * dy).sqrt();
                if mag > temp && mag > 0.0 {
                    dx = dx / mag * temp;
                    dy = dy / mag * temp;
                }
                self.x[i] += dx;
                self.y[i] += dy;
            }
            self.alpha *= 0.99;
        }
    }
}

static FORCE_HANDLES: OnceLock<Mutex<HashMap<u64, ForceState>>> = OnceLock::new();
static FORCE_NEXT: OnceLock<Mutex<u64>> = OnceLock::new();

fn force_map() -> &'static Mutex<HashMap<u64, ForceState>> {
    FORCE_HANDLES.get_or_init(|| Mutex::new(HashMap::new()))
}

fn next_handle() -> u64 {
    let lock = FORCE_NEXT.get_or_init(|| Mutex::new(1));
    let mut g = lock.lock().unwrap_or_else(|e| e.into_inner());
    let id = *g;
    *g = g.saturating_add(1).max(1);
    id
}

pub fn force_create(
    n_nodes: u64,
    sources: &[u64],
    targets: &[u64],
    init_x: Option<&[f64]>,
    init_y: Option<&[f64]>,
    seed: u64,
) -> Option<u64> {
    let state = ForceState::new(n_nodes, sources, targets, init_x, init_y, seed)?;
    let id = next_handle();
    force_map()
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .insert(id, state);
    Some(id)
}

pub fn force_tick(handle: u64, steps: u32, out_x: &mut [f64], out_y: &mut [f64]) -> Option<f64> {
    let mut map = force_map().lock().unwrap_or_else(|e| e.into_inner());
    let state = map.get_mut(&handle)?;
    if out_x.len() != state.n || out_y.len() != state.n {
        return None;
    }
    state.tick(steps);
    out_x.copy_from_slice(&state.x);
    out_y.copy_from_slice(&state.y);
    Some(state.alpha)
}

pub fn force_destroy(handle: u64) -> bool {
    force_map()
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .remove(&handle)
        .is_some()
}

/// Deterministic edge sample: keep first `budget` edges after stride.
pub fn sample_edges(n_edges: u64, budget: u64, out_indices: &mut [u64]) -> u64 {
    if budget == 0 || n_edges == 0 || out_indices.is_empty() {
        return 0;
    }
    let keep = budget.min(n_edges).min(out_indices.len() as u64);
    if keep >= n_edges {
        for i in 0..n_edges {
            out_indices[i as usize] = i;
        }
        return n_edges;
    }
    let stride = (n_edges as f64 / keep as f64).max(1.0);
    for i in 0..keep {
        let idx = ((i as f64) * stride).floor() as u64;
        out_indices[i as usize] = idx.min(n_edges - 1);
    }
    keep
}

/// Deterministic grid-hash node clustering for over-budget graph LOD.
///
/// When `n_nodes <= budget`, copies positions through (identity membership).
/// When over budget, bins into a near-square grid and emits cell centroids.
pub fn cluster_positions(
    n_nodes: u64,
    x: &[f64],
    y: &[f64],
    budget: u64,
    out_x: &mut [f64],
    out_y: &mut [f64],
    out_count: &mut u64,
    out_member_of: &mut [u64],
) -> bool {
    let Ok(n) = usize::try_from(n_nodes) else {
        return false;
    };
    if x.len() != n || y.len() != n || out_member_of.len() < n {
        return false;
    }
    if n_nodes <= budget {
        if out_x.len() < n || out_y.len() < n {
            return false;
        }
        out_x[..n].copy_from_slice(x);
        out_y[..n].copy_from_slice(y);
        for (i, member) in out_member_of.iter_mut().take(n).enumerate() {
            *member = i as u64;
        }
        *out_count = n_nodes;
        return true;
    }

    let Ok(budget_usize) = usize::try_from(budget) else {
        return false;
    };
    if budget_usize == 0 || out_x.len() < budget_usize || out_y.len() < budget_usize {
        return false;
    }

    let mut min_x = f64::INFINITY;
    let mut max_x = f64::NEG_INFINITY;
    let mut min_y = f64::INFINITY;
    let mut max_y = f64::NEG_INFINITY;
    for (&xi, &yi) in x.iter().zip(y.iter()) {
        if !xi.is_finite() || !yi.is_finite() {
            return false;
        }
        min_x = min_x.min(xi);
        max_x = max_x.max(xi);
        min_y = min_y.min(yi);
        max_y = max_y.max(yi);
    }

    let rows = (budget_usize as f64).sqrt().floor().max(1.0) as usize;
    let cols = (budget_usize / rows).max(1);
    let cells = rows * cols;
    let span_x = max_x - min_x;
    let span_y = max_y - min_y;
    let mut sum_x = vec![0.0f64; cells];
    let mut sum_y = vec![0.0f64; cells];
    let mut counts = vec![0u64; cells];

    let bin = |value: f64, min: f64, span: f64, bins: usize| -> usize {
        if span <= 0.0 {
            0
        } else {
            let scaled = ((value - min) / span) * (bins as f64);
            (scaled.floor() as usize).min(bins - 1)
        }
    };
    for i in 0..n {
        let col = bin(x[i], min_x, span_x, cols);
        let row = bin(y[i], min_y, span_y, rows);
        let cell = row * cols + col;
        sum_x[cell] += x[i];
        sum_y[cell] += y[i];
        counts[cell] += 1;
    }

    let mut cell_to_cluster = vec![u64::MAX; cells];
    let mut cluster_count = 0usize;
    for cell in 0..cells {
        let count = counts[cell];
        if count == 0 {
            continue;
        }
        cell_to_cluster[cell] = cluster_count as u64;
        out_x[cluster_count] = sum_x[cell] / (count as f64);
        out_y[cluster_count] = sum_y[cell] / (count as f64);
        cluster_count += 1;
    }

    for i in 0..n {
        let col = bin(x[i], min_x, span_x, cols);
        let row = bin(y[i], min_y, span_y, rows);
        out_member_of[i] = cell_to_cluster[row * cols + col];
    }
    *out_count = cluster_count as u64;
    true
}

/// Cluster LOD aggregate: grid/hash centroids when `|V|` exceeds `node_budget`,
/// plus a recorded §28 [`LodDecision`] (tier / edges_kept).
///
/// Under budget this is identity (direct or edge-sample tier from `lod_decide`);
/// over budget it writes at most `node_budget` centroids and Aggregate tier.
pub fn cluster_aggregate(
    n_nodes: u64,
    n_edges: u64,
    x: &[f64],
    y: &[f64],
    node_budget: u64,
    edge_budget: u64,
    out_x: &mut [f64],
    out_y: &mut [f64],
    out_count: &mut u64,
    out_member_of: &mut [u64],
) -> Option<LodDecision> {
    let decision = lod_decide(n_nodes, n_edges, node_budget, edge_budget);
    if !cluster_positions(
        n_nodes,
        x,
        y,
        node_budget,
        out_x,
        out_y,
        out_count,
        out_member_of,
    ) {
        return None;
    }
    Some(decision)
}

pub fn layout_auto(
    n_nodes: u64,
    sources: &[u64],
    targets: &[u64],
    out_x: &mut [f64],
    out_y: &mut [f64],
    seed: u64,
) -> bool {
    let n = n_nodes as usize;
    if n <= 32 {
        layout_circle(n, out_x, out_y);
        return true;
    }
    // Prefer BFS when edges ≈ nodes (tree/DAG-ish).
    if !sources.is_empty() && sources.len() as u64 <= n_nodes.saturating_mul(2) {
        return layout_breadthfirst(n_nodes, sources, targets, &[], out_x, out_y);
    }
    let Some(mut state) = ForceState::new(n_nodes, sources, targets, None, None, seed) else {
        return false;
    };
    state.tick(80);
    out_x.copy_from_slice(&state.x);
    out_y.copy_from_slice(&state.y);
    true
}

pub fn layout_radial(
    n_nodes: u64,
    sources: &[u64],
    targets: &[u64],
    root: u64,
    out_x: &mut [f64],
    out_y: &mut [f64],
) -> bool {
    let n = n_nodes as usize;
    if out_x.len() != n || out_y.len() != n || root >= n_nodes {
        return false;
    }
    let Some((offsets, neighbors)) = build_csr(n_nodes, sources, targets, false) else {
        return false;
    };
    let mut dist = vec![-1i32; n];
    let mut q = VecDeque::new();
    dist[root as usize] = 0;
    q.push_back(root);
    while let Some(u) = q.pop_front() {
        let ui = u as usize;
        let start = offsets[ui] as usize;
        let end = offsets[ui + 1] as usize;
        for &v in &neighbors[start..end] {
            let vi = v as usize;
            if dist[vi] < 0 {
                dist[vi] = dist[ui] + 1;
                q.push_back(v);
            }
        }
    }
    let mut ring: HashMap<i32, Vec<usize>> = HashMap::new();
    for (i, &d) in dist.iter().enumerate() {
        let key = if d < 0 { 9999 } else { d };
        ring.entry(key).or_default().push(i);
    }
    for (d, nodes) in ring {
        let r = (d as f64).max(0.0);
        let m = nodes.len();
        for (k, &i) in nodes.iter().enumerate() {
            let a = std::f64::consts::TAU * (k as f64) / (m as f64).max(1.0);
            out_x[i] = r * a.cos();
            out_y[i] = r * a.sin();
        }
    }
    out_x[root as usize] = 0.0;
    out_y[root as usize] = 0.0;
    true
}

pub fn layout_concentric(n: usize, degrees: &[u64], out_x: &mut [f64], out_y: &mut [f64]) -> bool {
    if degrees.len() != n || out_x.len() != n || out_y.len() != n {
        return false;
    }
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by_key(|&i| std::cmp::Reverse(degrees[i]));
    let rings = ((n as f64).sqrt().ceil() as usize).max(1);
    let mut idx = 0;
    for ring in 0..rings {
        let r = (ring as f64) + 1.0;
        let remaining_rings = rings - ring;
        let take = ((n - idx) / remaining_rings).max(1);
        let end = (idx + take).min(n);
        let slice = &order[idx..end];
        let m = slice.len();
        for (k, &i) in slice.iter().enumerate() {
            let a = std::f64::consts::TAU * (k as f64) / (m as f64).max(1.0);
            out_x[i] = r * a.cos();
            out_y[i] = r * a.sin();
        }
        idx = end;
        if idx >= n {
            break;
        }
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn circle_layout_places_origin_ring() {
        let mut x = [0.0; 4];
        let mut y = [0.0; 4];
        layout_circle(4, &mut x, &mut y);
        let r0 = (x[0] * x[0] + y[0] * y[0]).sqrt();
        assert!((r0 - 4.0).abs() < 1e-9);
    }

    #[test]
    fn force_is_seeded_deterministic() {
        let sources = [0u64, 1, 2];
        let targets = [1u64, 2, 0];
        let mut a = ForceState::new(3, &sources, &targets, None, None, 7).unwrap();
        let mut b = ForceState::new(3, &sources, &targets, None, None, 7).unwrap();
        a.tick(20);
        b.tick(20);
        assert_eq!(a.x, b.x);
        assert_eq!(a.y, b.y);
    }

    #[test]
    fn csr_undirected_symmetric() {
        let (off, nei) = build_csr(3, &[0, 1], &[1, 2], false).unwrap();
        assert_eq!(off, vec![0, 1, 3, 4]);
        assert!(nei.contains(&1));
    }

    #[test]
    fn lod_edges_sample() {
        let d = lod_decide(100, 10_000, 50_000, 1_000);
        assert_eq!(d.tier, LodTier::EdgeSample);
        assert_eq!(d.edges_kept, 1_000);
    }

    #[test]
    fn cluster_positions_centroids_over_budget() {
        let x = [0.0, 1.0, 0.0, 100.0, 101.0, 100.0];
        let y = [0.0, 0.0, 1.0, 100.0, 100.0, 101.0];
        let mut out_x = [0.0; 2];
        let mut out_y = [0.0; 2];
        let mut out_count = 0;
        let mut member_of = [u64::MAX; 6];

        assert!(cluster_positions(
            6,
            &x,
            &y,
            2,
            &mut out_x,
            &mut out_y,
            &mut out_count,
            &mut member_of,
        ));

        assert_eq!(out_count, 2);
        assert_eq!(member_of, [0, 0, 0, 1, 1, 1]);
        assert!((out_x[0] - (1.0 / 3.0)).abs() < 1e-12);
        assert!((out_y[0] - (1.0 / 3.0)).abs() < 1e-12);
        assert!((out_x[1] - (301.0 / 3.0)).abs() < 1e-12);
        assert!((out_y[1] - (301.0 / 3.0)).abs() < 1e-12);
    }

    #[test]
    fn cluster_aggregate_records_aggregate_tier() {
        let x = [0.0, 1.0, 0.0, 100.0, 101.0, 100.0];
        let y = [0.0, 0.0, 1.0, 100.0, 100.0, 101.0];
        let mut out_x = [0.0; 2];
        let mut out_y = [0.0; 2];
        let mut out_count = 0;
        let mut member_of = [u64::MAX; 6];

        let d = cluster_aggregate(
            6,
            3,
            &x,
            &y,
            2,
            500,
            &mut out_x,
            &mut out_y,
            &mut out_count,
            &mut member_of,
        )
        .expect("cluster_aggregate");
        assert_eq!(d.tier, LodTier::Aggregate);
        assert_eq!(d.n_nodes, 6);
        assert_eq!(d.node_budget, 2);
        assert_eq!(out_count, 2);
        assert_eq!(member_of, [0, 0, 0, 1, 1, 1]);
    }
}
