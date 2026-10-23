//! Rust-owned tile painter replies (#10, dossier §28/§29).
//! Keys/retention/level/encoding stay here; the browser only uploads/draws.
use super::*;
use crate::kernels;
use std::collections::HashSet;

pub const PAINT_HEADER: usize = 128;
pub const PAINT_DESCRIPTOR: usize = 96;
pub const MAX_PAINT_KEYS: usize = 256;
pub const MAX_PAINT_BYTES: usize = 64 * 1024 * 1024;

/// Allocation bound only; no store reads or frame/residency decisions.
pub fn paint_capacity(width: usize, height: usize) -> Option<usize> {
    if !(16..=4096).contains(&width) || !(16..=4096).contains(&height) {
        return None;
    }
    Some(
        (PAINT_HEADER + MAX_PAINT_KEYS * PAINT_DESCRIPTOR + width * height * 4 * 4)
            .min(MAX_PAINT_BYTES),
    )
}

/// Bounded binary XYDC v1 observations. This is inventory, never policy.
pub struct PaintObservation {
    pub generation: u64,
    pub opacity: f64,
    pub level: i32,
    pub keys: Vec<u32>,
}
impl PaintObservation {
    pub fn decode(raw: &[u8]) -> Option<Self> {
        if raw.is_empty() {
            return Some(Self {
                generation: 0,
                opacity: -1.0,
                level: -1,
                keys: Vec::new(),
            });
        }
        if raw.len() < 32
            || &raw[..4] != b"XYDC"
            || u32::from_le_bytes(raw[4..8].try_into().ok()?) != 1
        {
            return None;
        }
        let count = u32::from_le_bytes(raw[28..32].try_into().ok()?) as usize;
        if count > MAX_PAINT_KEYS || raw.len() != 32 + count * 12 {
            return None;
        }
        let generation = u64::from_le_bytes(raw[8..16].try_into().ok()?);
        let opacity = f64::from_le_bytes(raw[16..24].try_into().ok()?);
        let level = i32::from_le_bytes(raw[24..28].try_into().ok()?);
        if !opacity.is_finite() || !(-1.0..=1.0).contains(&opacity) || !(-1..=31).contains(&level) {
            return None;
        }
        Some(Self {
            generation,
            opacity,
            level,
            keys: raw[32..]
                .chunks_exact(4)
                .map(|v| u32::from_le_bytes(v.try_into().unwrap()))
                .collect(),
        })
    }
}

pub struct PaintRequest<'a> {
    pub window: [f64; 4],
    pub width: usize,
    pub height: usize,
    pub opacity: f64,
    pub known_generation: u64,
    pub known_opacity: f64,
    pub previous_level: i32,
    /// Flattened (level, tx, ty) triples, newest frame first.
    pub known: &'a [u32],
}

fn put_u32(out: &mut [u8], offset: usize, value: u32) {
    out[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
}
fn put_f64(out: &mut [u8], offset: usize, value: f64) {
    out[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
}

impl TileStore {
    fn paint_shape(&self, key: (u32, u32, u32)) -> (usize, usize) {
        let dim = self.dims[key.0 as usize];
        (
            (dim - key.1 as usize * TILE_DIM).min(TILE_DIM) + 2,
            (dim - key.2 as usize * TILE_DIM).min(TILE_DIM) + 2,
        )
    }
    fn paint_bytes(&self, key: (u32, u32, u32)) -> usize {
        let (w, h) = self.paint_shape(key);
        w * h * if self.has_color { 4 } else { 1 }
    }
    fn paint_keys(&self, level: usize, window: [f64; 4]) -> Vec<(u32, u32, u32)> {
        let dim = self.dims[level];
        let [x0, x1, y0, y1] = window;
        if x1 <= self.x0 || x0 >= self.x1 || y1 <= self.y0 || y0 >= self.y1 {
            return Vec::new();
        }
        let axis = |lo: f64, hi: f64, a: f64, b: f64| {
            let start = (((lo - a) / (b - a) * dim as f64).floor().max(0.0) as usize).min(dim - 1);
            let end = (((hi - a) / (b - a) * dim as f64).ceil().max(1.0) as usize).min(dim);
            (start / TILE_DIM, (end - 1) / TILE_DIM)
        };
        let (tx0, tx1) = axis(x0, x1, self.x0, self.x1);
        let (ty0, ty1) = axis(y0, y1, self.y0, self.y1);
        (ty0..=ty1)
            .flat_map(|ty| (tx0..=tx1).map(move |tx| (level as u32, tx as u32, ty as u32)))
            .collect()
    }

    /// Screen-bounded paint frame. `None` refuses rather than allocating an
    /// unbounded frame; callers retain the existing truthful window compose.
    pub fn paint_frame(&mut self, req: &PaintRequest<'_>) -> io::Result<Option<Vec<u8>>> {
        let [x0, x1, y0, y1] = req.window;
        if !req.window.iter().all(|v| v.is_finite())
            || x1 <= x0
            || y1 <= y0
            || !(16..=4096).contains(&req.width)
            || !(16..=4096).contains(&req.height)
            || !req.opacity.is_finite()
            || !(0.0..=1.0).contains(&req.opacity)
            || req.known.len() % 3 != 0
            || req.known.len() / 3 > MAX_PAINT_KEYS
        {
            return Ok(None);
        }
        let budget = req.width * req.height * if self.has_color { 4 } else { 1 } * 8; // eight screen textures of this format
        let requested_target = tiles::choose_level_dims(
            &self.dims,
            (self.x0, self.x1, self.y0, self.y1),
            x0,
            x1,
            y0,
            y1,
            req.width,
            req.height,
            1_000_000,
        )
        .unwrap_or(0);
        let mut target = requested_target;
        loop {
            let keys = self.paint_keys(target, req.window);
            let bytes: usize = keys.iter().map(|&key| self.paint_bytes(key)).sum();
            if keys.len() <= MAX_PAINT_KEYS && bytes <= budget / 2 && bytes <= MAX_PAINT_BYTES / 2 {
                break;
            }
            if target + 1 >= self.dims.len() {
                return Ok(None);
            }
            target += 1;
        }
        let previous = usize::try_from(req.previous_level)
            .ok()
            .filter(|&l| l < self.dims.len());
        let mut level = match previous {
            Some(old) if req.known_generation == self.paint_generation => {
                target.clamp(old.saturating_sub(1), (old + 1).min(self.dims.len() - 1))
            }
            _ => target,
        };
        let mut active;
        loop {
            active = self.paint_keys(level, req.window);
            let bytes: usize = active.iter().map(|&k| self.paint_bytes(k)).sum();
            if active.len() <= MAX_PAINT_KEYS && bytes <= budget / 2 && bytes <= MAX_PAINT_BYTES / 2
            {
                break;
            }
            if level + 1 >= self.dims.len() {
                return Ok(None);
            }
            level += 1;
        }
        // Current frame is pinned; retained same/adjacent levels are selected
        // in Rust, deterministically, from the caller's actual texture inventory.
        let valid_known = req.known_generation == self.paint_generation
            && (!self.has_color || req.known_opacity.to_bits() == req.opacity.to_bits());
        let known: HashSet<_> = if valid_known {
            req.known
                .chunks_exact(3)
                .map(|k| (k[0], k[1], k[2]))
                .filter(|&(l, x, y)| self.valid_key(l, x, y))
                .collect()
        } else {
            HashSet::new()
        };
        let mut keys = active.clone();
        let mut gpu_bytes: usize = keys.iter().map(|&k| self.paint_bytes(k)).sum();
        let mut candidates: Vec<_> = known
            .iter()
            .copied()
            .filter(|k| !keys.contains(k) && k.0.abs_diff(level as u32) <= 1)
            .collect();
        candidates.sort_by_key(|k| {
            (
                u32::from(Some(k.0 as usize) != previous),
                req.known
                    .chunks_exact(3)
                    .position(|v| v == [k.0, k.1, k.2])
                    .unwrap_or(usize::MAX),
                k.2,
                k.1,
            )
        });
        for key in candidates {
            let bytes = self.paint_bytes(key);
            if keys.len() < MAX_PAINT_KEYS && gpu_bytes + bytes <= budget {
                keys.push(key);
                gpu_bytes += bytes;
            }
        }
        let missing = active.iter().filter(|k| !known.contains(k)).count();
        let total = PAINT_HEADER
            + keys.len() * PAINT_DESCRIPTOR
            + active
                .iter()
                .filter(|k| !known.contains(k))
                .map(|&k| self.paint_bytes(k))
                .sum::<usize>();
        if total > MAX_PAINT_BYTES {
            return Ok(None);
        }
        let mut out = vec![0u8; PAINT_HEADER + keys.len() * PAINT_DESCRIPTOR];
        out[..4].copy_from_slice(b"XYDT");
        put_u32(&mut out, 4, 1);
        put_u32(&mut out, 8, level as u32);
        let flags = u32::from(self.has_color)
            | (u32::from(level != target) << 1)
            | (u32::from(
                target != requested_target
                    || previous.is_some_and(|old| {
                        req.known_generation == self.paint_generation && old.abs_diff(level) > 1
                    }),
            ) << 2);
        put_u32(&mut out, 12, flags);
        put_u32(&mut out, 16, keys.len() as u32);
        put_u32(&mut out, 20, active.len() as u32);
        put_u32(&mut out, 24, missing as u32);
        put_u32(&mut out, 28, PAINT_DESCRIPTOR as u32);
        out[32..40].copy_from_slice(&self.paint_generation.to_le_bytes());
        put_f64(&mut out, 48, (self.paint_maxima[level] as f64).ln_1p());
        put_f64(&mut out, 56, req.opacity);
        put_u32(&mut out, 64, budget as u32);
        put_u32(&mut out, 68, gpu_bytes as u32);
        put_u32(&mut out, 72, req.width as u32);
        put_u32(&mut out, 76, req.height as u32);
        put_u32(&mut out, 80, missing as u32);
        put_u32(&mut out, 84, target as u32);
        for (i, v) in req.window.iter().enumerate() {
            put_f64(&mut out, 96 + i * 8, *v);
        }
        self.begin_frame();
        let dim = self.dims[level];
        let mut window_max = 0u32;
        for (index, &key) in keys.iter().enumerate() {
            let offset = PAINT_HEADER + index * PAINT_DESCRIPTOR;
            let (tw, th) = self.paint_shape(key);
            let kdim = self.dims[key.0 as usize];
            let cx = key.1 as usize * TILE_DIM;
            let cy = key.2 as usize * TILE_DIM;
            for (i, v) in [
                key.0,
                key.1,
                key.2,
                tw as u32,
                th as u32,
                0,
                0,
                u32::from(index < active.len()),
            ]
            .iter()
            .enumerate()
            {
                put_u32(&mut out, offset + i * 4, *v);
            }
            let dx = (self.x1 - self.x0) / kdim as f64;
            let dy = (self.y1 - self.y0) / kdim as f64;
            let clip = [
                self.x0 + cx as f64 * dx,
                self.x0 + (cx + tw - 2) as f64 * dx,
                self.y0 + cy as f64 * dy,
                self.y0 + (cy + th - 2) as f64 * dy,
            ];
            let ranges = [
                clip[0] - dx,
                clip[1] + dx,
                clip[2] - dy,
                clip[3] + dy,
                clip[0],
                clip[1],
                clip[2],
                clip[3],
            ];
            for (i, v) in ranges.iter().enumerate() {
                put_f64(&mut out, offset + 32 + i * 8, *v);
            }
            if index >= active.len() {
                continue;
            }
            // Read the active source cells for exact window exposure even when
            // their GPU textures are retained. This is host RAM work, no wire.
            let gx0 = cx.saturating_sub(1);
            let gy0 = cy.saturating_sub(1);
            let gx1 = (cx + tw - 1).min(dim);
            let gy1 = (cy + th - 1).min(dim);
            let (counts, colors, _pins) = self
                .gather_rect(level, (gx0, gx1, gy0, gy1), self.has_color)
                .map_err(|error| self.finish_failed_frame(error))?;
            let stride = gx1 - gx0;
            for sy in cy..(cy + th - 2) {
                for sx in cx..(cx + tw - 2) {
                    let left = self.x0 + sx as f64 * dx;
                    let bottom = self.y0 + sy as f64 * dy;
                    if left < x1 && left + dx > x0 && bottom < y1 && bottom + dy > y0 {
                        window_max = window_max.max(counts[(sy - gy0) * stride + sx - gx0]);
                    }
                }
            }
            if known.contains(&key) {
                continue;
            }
            let start = out.len();
            let denom = (self.paint_maxima[level] as f64).ln_1p();
            for oy in 0..th {
                for ox in 0..tw {
                    let sx = (cx as isize + ox as isize - 1).clamp(0, dim as isize - 1) as usize;
                    let sy = (cy as isize + oy as isize - 1).clamp(0, dim as isize - 1) as usize;
                    let at = (sy - gy0) * stride + sx - gx0;
                    let count = counts[at];
                    if let Some(colors) = &colors {
                        let [r, g, b, a] = colors[at];
                        let a8 = ((u32::from(a) + 128) / 257).min(255) as u8;
                        let alpha = (a8 as f64 / 255.0) * req.opacity;
                        let shaped = if count == 0 || alpha <= 0.0 {
                            0.0
                        } else if alpha >= 1.0 {
                            1.0
                        } else {
                            -((count as f64) * (-alpha).ln_1p()).exp_m1()
                        };
                        let a = if shaped > 0.0 {
                            (shaped * 255.0).round().clamp(1.0, 255.0) as u8
                        } else {
                            0
                        };
                        for c in [r, g, b] {
                            out.push(
                                (kernels::linear_u16_to_srgb_u8(c) as f64 * a as f64 / 255.0)
                                    .round() as u8,
                            );
                        }
                        out.push(a);
                    } else {
                        out.push(if count == 0 || denom <= 0.0 {
                            0
                        } else {
                            ((count as f64).ln_1p() / denom * 255.0)
                                .round()
                                .clamp(1.0, 255.0) as u8
                        });
                    }
                }
            }
            put_u32(&mut out, offset + 20, start as u32);
            let len = out.len() - start;
            put_u32(&mut out, offset + 24, len as u32);
        }
        put_f64(&mut out, 40, window_max as f64);
        self.finish_frame()?;
        Ok(Some(out))
    }
}
