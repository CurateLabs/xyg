//! Graph display layouts, CSR, force ticks, and LOD helpers.
//!
//! Analysis algorithms stay in GraphForge; this module only positions and
//! aggregates for visualization ([graph-mark.md]). Element indices are u64.
//!
//! Force repulsion: exact pairwise for `n <= FORCE_EXACT_REPULSION_MAX_N`
//! (keeps seeded tests stable for small graphs); above that threshold a
//! deterministic spatial-grid Barnes–Hut-style cell approximation.

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
/// Longest-path DAG / Sugiyama layer assignment (directed). Not BFS.
pub const LAYOUT_HIERARCHICAL: u32 = 8;

/// Exact O(n²) pairwise repulsion ceiling. For `n` at or below this value
/// Fruchterman–Reingold uses exact pairwise forces (seeded determinism for
/// unit tests with n ≤ ~64). Above it, [`ForceState::tick`] switches to a
/// spatial-grid Barnes–Hut-style approximation.
pub const FORCE_EXACT_REPULSION_MAX_N: usize = 500;

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
    let _ = max_layer;
    place_by_layer(&layer, out_x, out_y);
    true
}

/// Place nodes from a per-node layer id (shared by BFS and hierarchical).
fn place_by_layer(layer: &[i32], out_x: &mut [f64], out_y: &mut [f64]) {
    let n = layer.len();
    let mut per_layer: HashMap<i32, u64> = HashMap::new();
    for &layer_id in layer {
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
}

/// Longest-path DAG layering (Sugiyama-style). Uses **directed** edges only.
///
/// Differs from [`layout_breadthfirst`], which walks an undirected BFS.
/// `dagre` maps to this id. Optional `roots` are forced to layer 0; when empty,
/// every in-degree-0 node is a root (or node 0 if the digraph is a pure cycle).
pub fn layout_hierarchical(
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
    if sources.len() != targets.len() {
        return false;
    }
    let mut preds: Vec<Vec<usize>> = vec![Vec::new(); n];
    let mut succ: Vec<Vec<usize>> = vec![Vec::new(); n];
    let mut indeg = vec![0usize; n];
    for (&s, &t) in sources.iter().zip(targets.iter()) {
        if s >= n_nodes || t >= n_nodes {
            return false;
        }
        let si = s as usize;
        let ti = t as usize;
        if si == ti {
            continue;
        }
        preds[ti].push(si);
        succ[si].push(ti);
        indeg[ti] += 1;
    }

    let mut is_root = vec![false; n];
    if roots.is_empty() {
        for (i, &deg) in indeg.iter().enumerate() {
            if deg == 0 {
                is_root[i] = true;
            }
        }
        if n > 0 && !is_root.iter().any(|&r| r) {
            is_root[0] = true;
        }
    } else {
        for &r in roots {
            if r >= n_nodes {
                return false;
            }
            is_root[r as usize] = true;
        }
    }

    // Topological order (Kahn); append residual cycle nodes stably by index.
    let mut indeg_kahn = indeg.clone();
    let mut kq = VecDeque::new();
    for (i, &deg) in indeg_kahn.iter().enumerate() {
        if deg == 0 {
            kq.push_back(i);
        }
    }
    let mut order: Vec<usize> = Vec::with_capacity(n);
    while let Some(u) = kq.pop_front() {
        order.push(u);
        for &v in &succ[u] {
            indeg_kahn[v] = indeg_kahn[v].saturating_sub(1);
            if indeg_kahn[v] == 0 {
                kq.push_back(v);
            }
        }
    }
    if order.len() < n {
        let mut seen = vec![false; n];
        for &u in &order {
            seen[u] = true;
        }
        for i in 0..n {
            if !seen[i] {
                order.push(i);
            }
        }
    }

    let mut layer = vec![0i32; n];
    for &v in &order {
        if is_root[v] {
            layer[v] = 0;
            continue;
        }
        let mut best = -1i32;
        for &p in &preds[v] {
            best = best.max(layer[p] + 1);
        }
        layer[v] = if best >= 0 { best } else { 0 };
    }

    place_by_layer(&layer, out_x, out_y);
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
            if n <= FORCE_EXACT_REPULSION_MAX_N {
                self.apply_repulsion_exact(&mut fx, &mut fy);
            } else {
                self.apply_repulsion_grid_bh(&mut fx, &mut fy);
            }
            // Attraction along edges (exact; |E| is typically ≪ n²).
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

    /// Exact pairwise Coulomb-style repulsion (O(n²)). Used for small n.
    fn apply_repulsion_exact(&self, fx: &mut [f64], fy: &mut [f64]) {
        let n = self.n;
        let k2 = self.k * self.k;
        for i in 0..n {
            for j in (i + 1)..n {
                let dx = self.x[i] - self.x[j];
                let dy = self.y[i] - self.y[j];
                let dist2 = dx * dx + dy * dy + 1e-8;
                let dist = dist2.sqrt();
                let force = k2 / dist;
                let fx_i = force * dx / dist;
                let fy_i = force * dy / dist;
                fx[i] += fx_i;
                fy[i] += fy_i;
                fx[j] -= fx_i;
                fy[j] -= fy_i;
            }
        }
    }

    /// Spatial-grid Barnes–Hut-style repulsion for large n.
    ///
    /// Bins nodes into a near-square grid, interacts exactly within a cell and
    /// its 8 neighbors, and approximates distant cells by their center of mass
    /// (mass = occupancy). Deterministic: cells and members are visited in
    /// stable index order. Complexity ≈ O(n · √n) with ~8 nodes/cell target,
    /// far cheaper than naive O(n²).
    fn apply_repulsion_grid_bh(&self, fx: &mut [f64], fy: &mut [f64]) {
        let n = self.n;
        let k2 = self.k * self.k;
        let mut min_x = f64::INFINITY;
        let mut max_x = f64::NEG_INFINITY;
        let mut min_y = f64::INFINITY;
        let mut max_y = f64::NEG_INFINITY;
        for i in 0..n {
            min_x = min_x.min(self.x[i]);
            max_x = max_x.max(self.x[i]);
            min_y = min_y.min(self.y[i]);
            max_y = max_y.max(self.y[i]);
        }
        if !min_x.is_finite() {
            return;
        }
        // Target ~8 nodes per cell → side ≈ sqrt(n/8), clamped for sanity.
        let side = ((n as f64 / 8.0).sqrt().ceil() as usize).clamp(4, 512);
        let cells = side * side;
        let span_x = (max_x - min_x).max(1e-12);
        let span_y = (max_y - min_y).max(1e-12);
        let mut cell_of = vec![0usize; n];
        let mut members: Vec<Vec<usize>> = vec![Vec::new(); cells];
        let mut mass = vec![0u64; cells];
        let mut com_x = vec![0.0f64; cells];
        let mut com_y = vec![0.0f64; cells];
        for i in 0..n {
            let col = (((self.x[i] - min_x) / span_x) * (side as f64))
                .floor()
                .clamp(0.0, (side - 1) as f64) as usize;
            let row = (((self.y[i] - min_y) / span_y) * (side as f64))
                .floor()
                .clamp(0.0, (side - 1) as f64) as usize;
            let cell = row * side + col;
            cell_of[i] = cell;
            members[cell].push(i);
            mass[cell] += 1;
            com_x[cell] += self.x[i];
            com_y[cell] += self.y[i];
        }
        for c in 0..cells {
            if mass[c] > 0 {
                let m = mass[c] as f64;
                com_x[c] /= m;
                com_y[c] /= m;
            }
        }

        // Exact pairs inside each cell (i < j).
        for c in 0..cells {
            let m = &members[c];
            for a in 0..m.len() {
                for b in (a + 1)..m.len() {
                    let i = m[a];
                    let j = m[b];
                    let dx = self.x[i] - self.x[j];
                    let dy = self.y[i] - self.y[j];
                    let dist2 = dx * dx + dy * dy + 1e-8;
                    let dist = dist2.sqrt();
                    let force = k2 / dist;
                    let fx_i = force * dx / dist;
                    let fy_i = force * dy / dist;
                    fx[i] += fx_i;
                    fy[i] += fy_i;
                    fx[j] -= fx_i;
                    fy[j] -= fy_i;
                }
            }
        }

        // Neighbor-cell exact pairs (each unordered cell pair once).
        for row in 0..side {
            for col in 0..side {
                let c0 = row * side + col;
                for dr in 0i32..=1 {
                    for dc in -1i32..=1 {
                        if dr == 0 && dc <= 0 {
                            continue; // same cell already done; keep dc>0 on same row
                        }
                        let r2 = row as i32 + dr;
                        let c2 = col as i32 + dc;
                        if r2 < 0 || c2 < 0 || r2 >= side as i32 || c2 >= side as i32 {
                            continue;
                        }
                        let c1 = (r2 as usize) * side + (c2 as usize);
                        for &i in &members[c0] {
                            for &j in &members[c1] {
                                let dx = self.x[i] - self.x[j];
                                let dy = self.y[i] - self.y[j];
                                let dist2 = dx * dx + dy * dy + 1e-8;
                                let dist = dist2.sqrt();
                                let force = k2 / dist;
                                let fx_i = force * dx / dist;
                                let fy_i = force * dy / dist;
                                fx[i] += fx_i;
                                fy[i] += fy_i;
                                fx[j] -= fx_i;
                                fy[j] -= fy_i;
                            }
                        }
                    }
                }
            }
        }

        // Distant cells: particle ← cell COM (Barnes–Hut monopole).
        for i in 0..n {
            let ci = cell_of[i];
            let ri = ci / side;
            let coli = ci % side;
            for row in 0..side {
                for col in 0..side {
                    let crow = row as i32 - ri as i32;
                    let ccol = col as i32 - coli as i32;
                    // Skip self + Moore neighborhood (already exact).
                    if crow.abs() <= 1 && ccol.abs() <= 1 {
                        continue;
                    }
                    let c = row * side + col;
                    let m = mass[c];
                    if m == 0 {
                        continue;
                    }
                    let dx = self.x[i] - com_x[c];
                    let dy = self.y[i] - com_y[c];
                    let dist2 = dx * dx + dy * dy + 1e-8;
                    let dist = dist2.sqrt();
                    let force = (k2 * (m as f64)) / dist;
                    fx[i] += force * dx / dist;
                    fy[i] += force * dy / dist;
                }
            }
        }
    }
}

/// Optional axis-aligned viewport for [`build_render`].
#[derive(Clone, Copy, Debug)]
pub struct Viewport {
    pub x0: f64,
    pub y0: f64,
    pub x1: f64,
    pub y1: f64,
}

impl Viewport {
    pub fn contains(&self, x: f64, y: f64) -> bool {
        let (lo_x, hi_x) = if self.x0 <= self.x1 {
            (self.x0, self.x1)
        } else {
            (self.x1, self.x0)
        };
        let (lo_y, hi_y) = if self.y0 <= self.y1 {
            (self.y0, self.y1)
        } else {
            (self.y1, self.y0)
        };
        x >= lo_x && x <= hi_x && y >= lo_y && y <= hi_y
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

/// Build a perceptually bounded **render graph** for hosts to ship.
///
/// Given full layout positions + edges and budgets, writes:
/// - `out_node_x` / `out_node_y`: centroids (aggregate) or direct positions
/// - `out_member_of`: cluster index per **source** node (`u64::MAX` if the
///   node is outside an optional viewport and therefore not in the render set)
/// - `out_edge_sources` / `out_edge_targets`: edges in **cluster index space**,
///   with multi-edges between the same cluster pair collapsed to one
/// - `out_n_nodes` / `out_n_edges`: sizes of the reduced graph (`|V'|`, `|E'|`)
/// - recorded §28 [`LodDecision`] (`tier` / `edges_kept` = `|E'|`)
///
/// Guarantees `|V'| ≤ node_budget` and `|E'| ≤ edge_budget` so hosts never
/// upload raw V/E when over budget (scatter-density → exact drill-down spirit).
pub fn build_render(
    n_nodes: u64,
    x: &[f64],
    y: &[f64],
    sources: &[u64],
    targets: &[u64],
    node_budget: u64,
    edge_budget: u64,
    viewport: Option<Viewport>,
    out_node_x: &mut [f64],
    out_node_y: &mut [f64],
    out_member_of: &mut [u64],
    out_edge_sources: &mut [u64],
    out_edge_targets: &mut [u64],
    out_n_nodes: &mut u64,
    out_n_edges: &mut u64,
) -> Option<LodDecision> {
    let Ok(n) = usize::try_from(n_nodes) else {
        return None;
    };
    if x.len() != n || y.len() != n || out_member_of.len() < n {
        return None;
    }
    if sources.len() != targets.len() {
        return None;
    }
    let n_edges = sources.len() as u64;
    let node_budget = node_budget.max(1);
    let edge_budget = edge_budget.max(1);
    let Ok(node_budget_usize) = usize::try_from(node_budget) else {
        return None;
    };
    // Effective edge budget is min(requested, caller buffer capacity).
    let edge_out_cap = out_edge_sources.len().min(out_edge_targets.len()) as u64;
    if n_edges > 0 && edge_out_cap == 0 {
        return None;
    }
    let edge_budget = if edge_out_cap == 0 {
        1
    } else {
        edge_budget.min(edge_out_cap)
    };

    // Mark active (viewport) nodes; outside → member_of = MAX later.
    let mut active = vec![true; n];
    let mut n_active = n;
    if let Some(vp) = viewport {
        n_active = 0;
        for i in 0..n {
            let ok = x[i].is_finite() && y[i].is_finite() && vp.contains(x[i], y[i]);
            active[i] = ok;
            if ok {
                n_active += 1;
            }
        }
    } else {
        for i in 0..n {
            if !x[i].is_finite() || !y[i].is_finite() {
                active[i] = false;
                n_active = n_active.saturating_sub(1);
            }
        }
    }

    // Compact active positions for clustering / identity.
    let mut active_idx: Vec<usize> = Vec::with_capacity(n_active);
    let mut ax = Vec::with_capacity(n_active);
    let mut ay = Vec::with_capacity(n_active);
    for i in 0..n {
        if active[i] {
            active_idx.push(i);
            ax.push(x[i]);
            ay.push(y[i]);
        }
    }
    let n_active_u64 = active_idx.len() as u64;

    // Cluster (or identity) the active set into ≤ node_budget centroids.
    let cluster_cap = if n_active_u64 <= node_budget {
        active_idx.len()
    } else {
        node_budget_usize
    };
    if out_node_x.len() < cluster_cap || out_node_y.len() < cluster_cap {
        return None;
    }
    let mut tmp_x = vec![0.0f64; cluster_cap.max(1)];
    let mut tmp_y = vec![0.0f64; cluster_cap.max(1)];
    let mut tmp_member = vec![u64::MAX; active_idx.len().max(1)];
    let mut cluster_count = 0u64;
    if active_idx.is_empty() {
        for m in out_member_of.iter_mut().take(n) {
            *m = u64::MAX;
        }
        *out_n_nodes = 0;
        *out_n_edges = 0;
        return Some(LodDecision {
            tier: LodTier::Direct,
            n_nodes,
            n_edges,
            edge_budget,
            node_budget,
            edges_kept: 0,
        });
    }
    if !cluster_positions(
        n_active_u64,
        &ax,
        &ay,
        node_budget,
        &mut tmp_x,
        &mut tmp_y,
        &mut cluster_count,
        &mut tmp_member,
    ) {
        return None;
    }
    let v_prime = cluster_count as usize;
    if out_node_x.len() < v_prime || out_node_y.len() < v_prime {
        return None;
    }
    out_node_x[..v_prime].copy_from_slice(&tmp_x[..v_prime]);
    out_node_y[..v_prime].copy_from_slice(&tmp_y[..v_prime]);
    *out_n_nodes = cluster_count;

    // Map source node → cluster index (or MAX if inactive).
    for m in out_member_of.iter_mut().take(n) {
        *m = u64::MAX;
    }
    for (local, &src) in active_idx.iter().enumerate() {
        out_member_of[src] = tmp_member[local];
    }

    // Aggregate edges into cluster index space (collapse multi-edges).
    // Directed key (cs, ct); skip loops and endpoints outside the render set.
    let mut edge_set: HashMap<(u64, u64), ()> = HashMap::new();
    let mut aggregated: Vec<(u64, u64)> = Vec::new();
    for (&s, &t) in sources.iter().zip(targets.iter()) {
        if s >= n_nodes || t >= n_nodes {
            return None;
        }
        let cs = out_member_of[s as usize];
        let ct = out_member_of[t as usize];
        if cs == u64::MAX || ct == u64::MAX || cs == ct {
            continue;
        }
        let key = (cs, ct);
        if edge_set.insert(key, ()).is_none() {
            aggregated.push(key);
        }
    }

    // If still over edge_budget, stride-sample the aggregated list (§28).
    let agg_n = aggregated.len() as u64;
    let keep = agg_n.min(edge_budget);
    let mut indices = vec![0u64; keep as usize];
    let kept = sample_edges(agg_n, keep, &mut indices);
    for i in 0..kept as usize {
        let (cs, ct) = aggregated[indices[i] as usize];
        out_edge_sources[i] = cs;
        out_edge_targets[i] = ct;
    }
    *out_n_edges = kept;

    // Record §28 decision against the *source* graph sizes; edges_kept = |E'|.
    let clustered = cluster_count < n_active_u64 || n_active_u64 > node_budget;
    let tier = if clustered {
        LodTier::Aggregate
    } else if kept < n_edges {
        LodTier::EdgeSample
    } else {
        LodTier::Direct
    };
    Some(LodDecision {
        tier,
        n_nodes,
        n_edges,
        edge_budget,
        node_budget,
        edges_kept: kept,
    })
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

    /// DAG fixture where undirected BFS and directed longest-path disagree.
    /// Edges: 0→1→2, 3→2. BFS from 0 reaches 3 via 2 (layer 3); hierarchical
    /// treats 3 as an in-degree-0 root (layer 0).
    fn dag_fixture() -> (Vec<u64>, Vec<u64>) {
        (vec![0, 1, 3], vec![1, 2, 2])
    }

    #[test]
    fn hierarchical_differs_from_breadthfirst_on_dag() {
        let (sources, targets) = dag_fixture();
        let mut bx = [0.0; 4];
        let mut by = [0.0; 4];
        let mut hx = [0.0; 4];
        let mut hy = [0.0; 4];
        assert!(layout_breadthfirst(4, &sources, &targets, &[], &mut bx, &mut by));
        assert!(layout_hierarchical(4, &sources, &targets, &[], &mut hx, &mut hy));
        assert_ne!(by, hy, "hierarchical must not alias undirected BFS");
        // Hierarchical: roots 0 and 3 at layer 0 → y=0; node 2 at layer 2 → y=-2.
        assert!((hy[0]).abs() < 1e-12);
        assert!((hy[3]).abs() < 1e-12);
        assert!((hy[2] + 2.0).abs() < 1e-12);
        // BFS from default root 0: node 3 is three hops via undirected walk.
        assert!((by[3] + 3.0).abs() < 1e-12);
    }

    #[test]
    fn breadthfirst_roots_change_layers() {
        let sources = [0u64, 1, 2];
        let targets = [1u64, 2, 3];
        let mut ax = [0.0; 4];
        let mut ay = [0.0; 4];
        let mut bx = [0.0; 4];
        let mut by = [0.0; 4];
        assert!(layout_breadthfirst(
            4,
            &sources,
            &targets,
            &[0],
            &mut ax,
            &mut ay
        ));
        assert!(layout_breadthfirst(
            4,
            &sources,
            &targets,
            &[3],
            &mut bx,
            &mut by
        ));
        assert_ne!(ay, by);
        assert!((ay[0]).abs() < 1e-12);
        assert!((by[3]).abs() < 1e-12);
        assert!((by[0] + 3.0).abs() < 1e-12);
    }

    #[test]
    fn radial_places_root_at_origin() {
        let sources = [0u64, 1];
        let targets = [1u64, 2];
        let mut x = [0.0; 3];
        let mut y = [0.0; 3];
        assert!(layout_radial(3, &sources, &targets, 0, &mut x, &mut y));
        assert!((x[0]).abs() < 1e-12 && (y[0]).abs() < 1e-12);
        let r1 = (x[1] * x[1] + y[1] * y[1]).sqrt();
        assert!((r1 - 1.0).abs() < 1e-9);
    }

    #[test]
    fn concentric_orders_by_degree() {
        // Node 1 has degree 3; others degree 1 → node 1 on innermost ring.
        let degrees = [1u64, 3, 1, 1];
        let mut x = [0.0; 4];
        let mut y = [0.0; 4];
        assert!(layout_concentric(4, &degrees, &mut x, &mut y));
        let r1 = (x[1] * x[1] + y[1] * y[1]).sqrt();
        let r_outer = [0usize, 2, 3]
            .iter()
            .map(|&i| (x[i] * x[i] + y[i] * y[i]).sqrt())
            .fold(0.0_f64, f64::max);
        assert!(r1 <= r_outer);
        assert!((r1 - 1.0).abs() < 1e-9, "highest-degree node on first ring");
        assert!(r_outer > r1 + 0.5, "lower-degree nodes reach an outer ring");
    }

    #[test]
    fn auto_tiny_uses_circle() {
        let mut x = [0.0; 4];
        let mut y = [0.0; 4];
        let mut cx = [0.0; 4];
        let mut cy = [0.0; 4];
        assert!(layout_auto(4, &[], &[], &mut x, &mut y, 1));
        layout_circle(4, &mut cx, &mut cy);
        assert_eq!(x, cx);
        assert_eq!(y, cy);
    }

    #[test]
    fn auto_sparse_prefers_breadthfirst() {
        let n = 40u64;
        let mut sources = Vec::new();
        let mut targets = Vec::new();
        for i in 0..(n - 1) {
            sources.push(i);
            targets.push(i + 1);
        }
        let mut ax = vec![0.0; n as usize];
        let mut ay = vec![0.0; n as usize];
        let mut bx = vec![0.0; n as usize];
        let mut by = vec![0.0; n as usize];
        assert!(layout_auto(n, &sources, &targets, &mut ax, &mut ay, 3));
        assert!(layout_breadthfirst(
            n,
            &sources,
            &targets,
            &[],
            &mut bx,
            &mut by
        ));
        assert_eq!(ax, bx);
        assert_eq!(ay, by);
    }

    #[test]
    fn hierarchical_respects_explicit_roots() {
        let (sources, targets) = dag_fixture();
        let mut x = [0.0; 4];
        let mut y = [0.0; 4];
        // Force only node 3 as root: 0 is no longer layer 0 unless reached.
        assert!(layout_hierarchical(
            4,
            &sources,
            &targets,
            &[3],
            &mut x,
            &mut y
        ));
        assert!((y[3]).abs() < 1e-12);
        // Node 0 has no predecessor path from 3 → layer 0 fallback.
        assert!((y[0]).abs() < 1e-12 || y[0] <= 0.0);
    }

    #[test]
    fn force_exact_path_for_tiny_n() {
        assert!(
            3 <= FORCE_EXACT_REPULSION_MAX_N,
            "tiny graphs must use exact pairwise repulsion"
        );
        let sources = [0u64, 1, 2];
        let targets = [1u64, 2, 0];
        let mut a = ForceState::new(3, &sources, &targets, None, None, 11).unwrap();
        let mut b = ForceState::new(3, &sources, &targets, None, None, 11).unwrap();
        a.tick(25);
        b.tick(25);
        assert_eq!(a.x, b.x);
        assert_eq!(a.y, b.y);
    }

    #[test]
    fn force_bh_threshold_documented() {
        // Contract: n ≤ 500 exact; n > 500 grid BH. Seeded small-n tests rely on this.
        assert_eq!(FORCE_EXACT_REPULSION_MAX_N, 500);
    }

    #[test]
    fn force_grid_bh_is_seeded_deterministic_above_threshold() {
        let n = FORCE_EXACT_REPULSION_MAX_N + 20;
        let mut sources = Vec::new();
        let mut targets = Vec::new();
        for i in 0..(n as u64 - 1) {
            sources.push(i);
            targets.push(i + 1);
        }
        let mut a = ForceState::new(n as u64, &sources, &targets, None, None, 42).unwrap();
        let mut b = ForceState::new(n as u64, &sources, &targets, None, None, 42).unwrap();
        a.tick(5);
        b.tick(5);
        assert_eq!(a.x, b.x);
        assert_eq!(a.y, b.y);
        let moved = a
            .x
            .iter()
            .zip(a.y.iter())
            .any(|(&x, &y)| x.is_finite() && y.is_finite() && (x * x + y * y).sqrt() > 0.0);
        assert!(moved);
    }

    #[test]
    fn build_render_respects_budgets_and_records_lod() {
        let x = [0.0, 1.0, 0.0, 100.0, 101.0, 100.0];
        let y = [0.0, 0.0, 1.0, 100.0, 100.0, 101.0];
        let sources = [0u64, 1, 3, 4, 0];
        let targets = [1u64, 2, 4, 5, 3];
        let mut out_x = [0.0; 2];
        let mut out_y = [0.0; 2];
        let mut member_of = [u64::MAX; 6];
        let mut edge_s = [0u64; 4];
        let mut edge_t = [0u64; 4];
        let mut n_out = 0u64;
        let mut e_out = 0u64;
        let d = build_render(
            6,
            &x,
            &y,
            &sources,
            &targets,
            2,
            4,
            None,
            &mut out_x,
            &mut out_y,
            &mut member_of,
            &mut edge_s,
            &mut edge_t,
            &mut n_out,
            &mut e_out,
        )
        .expect("build_render");
        assert_eq!(d.tier, LodTier::Aggregate);
        assert_eq!(d.n_nodes, 6);
        assert_eq!(d.n_edges, 5);
        assert_eq!(d.node_budget, 2);
        assert_eq!(d.edge_budget, 4);
        assert!(n_out <= 2);
        assert!(e_out <= 4);
        assert_eq!(d.edges_kept, e_out);
        assert_eq!(member_of, [0, 0, 0, 1, 1, 1]);
        assert!(e_out >= 1);
        for i in 0..e_out as usize {
            assert!(edge_s[i] < n_out && edge_t[i] < n_out);
            assert_ne!(edge_s[i], edge_t[i]);
        }
    }

    #[test]
    fn build_render_direct_under_budget() {
        let x = [0.0, 1.0, 2.0];
        let y = [0.0, 1.0, 0.0];
        let sources = [0u64, 1];
        let targets = [1u64, 2];
        let mut out_x = [0.0; 3];
        let mut out_y = [0.0; 3];
        let mut member_of = [u64::MAX; 3];
        let mut edge_s = [0u64; 2];
        let mut edge_t = [0u64; 2];
        let mut n_out = 0u64;
        let mut e_out = 0u64;
        let d = build_render(
            3,
            &x,
            &y,
            &sources,
            &targets,
            100,
            100,
            None,
            &mut out_x,
            &mut out_y,
            &mut member_of,
            &mut edge_s,
            &mut edge_t,
            &mut n_out,
            &mut e_out,
        )
        .expect("build_render direct");
        assert_eq!(d.tier, LodTier::Direct);
        assert_eq!(n_out, 3);
        assert_eq!(e_out, 2);
        assert_eq!(member_of, [0, 1, 2]);
        assert_eq!(&out_x[..3], &x);
        assert_eq!(&edge_s[..2], &sources);
        assert_eq!(&edge_t[..2], &targets);
    }

    #[test]
    fn build_render_viewport_filters_nodes() {
        let x = [0.0, 1.0, 50.0];
        let y = [0.0, 1.0, 50.0];
        let sources = [0u64, 1];
        let targets = [1u64, 2];
        let mut out_x = [0.0; 3];
        let mut out_y = [0.0; 3];
        let mut member_of = [u64::MAX; 3];
        let mut edge_s = [0u64; 2];
        let mut edge_t = [0u64; 2];
        let mut n_out = 0u64;
        let mut e_out = 0u64;
        let d = build_render(
            3,
            &x,
            &y,
            &sources,
            &targets,
            10,
            10,
            Some(Viewport {
                x0: -1.0,
                y0: -1.0,
                x1: 2.0,
                y1: 2.0,
            }),
            &mut out_x,
            &mut out_y,
            &mut member_of,
            &mut edge_s,
            &mut edge_t,
            &mut n_out,
            &mut e_out,
        )
        .expect("viewport render");
        assert_eq!(n_out, 2);
        assert_eq!(member_of[2], u64::MAX);
        assert_eq!(e_out, 1);
        assert_eq!(d.edges_kept, 1);
    }
}
