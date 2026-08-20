//! Phase-4 disk-resident tile store (LOD doc §4 items 10–12, dossier §32b,
//! roadmap locked decisions D1–D7).
//!
//! A [`TileStore`] snapshots a built [`tiles::Pyramid`] into `(level, tx, ty)`
//! 256²-cell tiles inside **one spill file per pyramid** (D1: magic `XYTS`,
//! versioned header, dense count region then optional color region, coarsest
//! level first, row-major `(ty, tx)` within a level, every slab a fixed
//! zero-padded 256² block so offsets are closed-form arithmetic, native
//! endianness). The file is a §27 derived, rebuildable, per-process cache —
//! process-scoped temp, deleted on free/exit, never an interchange format.
//!
//! **Slab I/O realization:** the repo vendors no mmap crate and crates.io is
//! unreachable from the dev sandbox (rust-engine dependency policy), so the
//! mmap-slab *layout* of D1 is realized with positioned `File` reads/writes
//! (`pread`/`pwrite`-style, page-aligned offsets). Same on-disk bytes, same
//! O(1) offset arithmetic; a literal `mmap(2)` can replace the read path
//! without a format change. Recorded in the roadmap WP1 notes.
//!
//! Residency is an LRU over whole tiles (count + color slabs evict together,
//! D3) under the process-wide byte budget (`PYRAMID_RESIDENT_BYTES`
//! semantics, D2 — default 512 MiB across all stores). The tiles serving the
//! current compose are pinned for the call; a frame never fails for budget
//! reasons — if the pinned working set alone exceeds the budget the compose
//! proceeds and the condition is recorded (`over_budget`, §28), then
//! eviction returns residency to budget once the pins release.
//!
//! Compose-from-tiles gathers the exact cell rect the window touches into a
//! contiguous scratch and runs [`tiles::compose_level`] /
//! [`tiles::compose_color_level`] — the *same* bodies the in-RAM compose
//! runs — so tile-served grids are bit-identical to Phase-3 grids by
//! construction. NaN never reaches tiles: cells come from the pyramid build
//! (`bin_2d_counts` parity, §19) and the append path skips non-finite pairs
//! exactly like [`tiles::append`].
//!
//! No unsafe here; the C-ABI shell in `xyg-core` owns marshaling (engine doc
//! §3.3 handle discipline, same as tiles.rs).

use std::collections::HashMap;
use std::fs::{self, File, OpenOptions};
use std::io;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

use crate::tiles::{self, LevelView, Pyramid};

/// Cells per tile side (D1). Re-export of [`tiles::TILE_DIM`] for ABI sizing.
pub use crate::tiles::TILE_DIM;
const TILE_CELLS: usize = TILE_DIM * TILE_DIM;
const COUNT_SLAB_BYTES: u64 = (TILE_CELLS * 4) as u64;
const COLOR_SLAB_BYTES: u64 = (TILE_CELLS * 8) as u64;
/// One page reserved for the header; slab 0 starts page-aligned.
const HEADER_BYTES: u64 = 4096;
const MAGIC: [u8; 4] = *b"XYTS";
const FORMAT_VERSION: u32 = 1;

/// Default process-wide resident-tile byte budget (D2: 512 MiB). Hosts set
/// it from `PYRAMID_RESIDENT_BYTES` via `xyg_tile_budget_set` (WP2 wires the
/// config knob; the kernel default matches the locked spec value).
pub const DEFAULT_RESIDENT_BUDGET_BYTES: u64 = 512 * (1 << 20);

/// Estimated per-resident-tile index/bookkeeping overhead, counted into the
/// resident-byte report so directory metadata is never invisible (§27 —
/// "if a byte isn't in the report, it isn't real").
const TILE_INDEX_ENTRY_BYTES: u64 = 96;

static RESIDENT_BUDGET: AtomicU64 = AtomicU64::new(DEFAULT_RESIDENT_BUDGET_BYTES);
/// RAM-resident tile bytes across every live store (D2: the budget is
/// process-wide — multi-trace apps share one pool).
static GLOBAL_RESIDENT: AtomicU64 = AtomicU64::new(0);
static SPILL_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Set the process-wide resident budget; `0` restores the default.
pub fn budget_set(bytes: u64) {
    let value = if bytes == 0 {
        DEFAULT_RESIDENT_BUDGET_BYTES
    } else {
        bytes
    };
    RESIDENT_BUDGET.store(value, Ordering::Relaxed);
}

pub fn budget_get() -> u64 {
    RESIDENT_BUDGET.load(Ordering::Relaxed)
}

fn global_resident() -> u64 {
    GLOBAL_RESIDENT.load(Ordering::Relaxed)
}

// -- positioned file I/O (unix pread/pwrite; windows seek_read/seek_write) ---

#[cfg(unix)]
fn read_exact_at(file: &File, buf: &mut [u8], offset: u64) -> io::Result<()> {
    use std::os::unix::fs::FileExt;
    file.read_exact_at(buf, offset)
}

#[cfg(unix)]
fn write_all_at(file: &File, buf: &[u8], offset: u64) -> io::Result<()> {
    use std::os::unix::fs::FileExt;
    file.write_all_at(buf, offset)
}

#[cfg(windows)]
fn read_exact_at(file: &File, mut buf: &mut [u8], mut offset: u64) -> io::Result<()> {
    use std::os::windows::fs::FileExt;
    while !buf.is_empty() {
        let n = file.seek_read(buf, offset)?;
        if n == 0 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "tile slab read past end of spill file",
            ));
        }
        buf = &mut buf[n..];
        offset += n as u64;
    }
    Ok(())
}

#[cfg(windows)]
fn write_all_at(file: &File, mut buf: &[u8], mut offset: u64) -> io::Result<()> {
    use std::os::windows::fs::FileExt;
    while !buf.is_empty() {
        let n = file.seek_write(buf, offset)?;
        buf = &buf[n..];
        offset += n as u64;
    }
    Ok(())
}

// -- store -------------------------------------------------------------------

/// One resident tile: fixed 256²-cell planes (zero-padded when the level is
/// smaller than a tile). `dirty` marks RAM newer than the disk slab (append
/// landed since the last write-back); dirty tiles write back on eviction, so
/// the file always converges to the appended truth.
struct Tile {
    counts: Box<[u32]>,
    color: Option<Box<[[u16; 4]]>>,
    last_used: u64,
    dirty: bool,
}

pub struct TileStore {
    file: File,
    path: PathBuf,
    /// Per level (index 0 = finest, matching `Pyramid`), the level's grid
    /// dim, tiles per side, and the level's first slab index in the file's
    /// coarsest-first region order — everything an offset needs, O(levels)
    /// metadata, no per-tile directory (D1).
    dims: Vec<usize>,
    tiles_per_side: Vec<u32>,
    slab_base: Vec<u64>,
    total_slabs: u64,
    has_color: bool,
    x0: f64,
    x1: f64,
    y0: f64,
    y1: f64,
    resident: HashMap<(u32, u32, u32), Tile>,
    tick: u64,
    hits: u64,
    misses: u64,
    /// Recorded per D3: true when the last compose could not fit its pinned
    /// working set (plus everything unevictable) under the budget.
    over_budget: bool,
}

/// §28 residency stats for one reply: `(hit, miss, resident_bytes,
/// spilled_bytes, budget_bytes, over_budget)`. `resident_bytes` is the
/// process-wide total the budget governs; `spilled_bytes` is this store's
/// spill-file size; hit/miss are this store's cumulative fetch counters.
pub type Stats = (u64, u64, u64, u64, u64, bool);

impl TileStore {
    /// Snapshot a built pyramid into a spill file. Nothing is resident
    /// afterwards; tiles fault in on demand. The pyramid handle stays live
    /// and independent — the host frees it to actually reclaim the RAM.
    pub fn spill(p: &Pyramid) -> io::Result<TileStore> {
        let dims: Vec<usize> = p.level_dims().to_vec();
        let has_color = p.has_color();
        let (x0, x1, y0, y1) = p.domain();

        let mut tiles_per_side = Vec::with_capacity(dims.len());
        for &dim in &dims {
            tiles_per_side.push(dim.div_ceil(TILE_DIM) as u32);
        }
        // Slab order is coarsest level first (D1), so walk dims reversed to
        // assign bases, then store them per pyramid-level index.
        let mut slab_base = vec![0u64; dims.len()];
        let mut next = 0u64;
        for level in (0..dims.len()).rev() {
            slab_base[level] = next;
            next += u64::from(tiles_per_side[level]) * u64::from(tiles_per_side[level]);
        }
        let total_slabs = next;

        let path = std::env::temp_dir().join(format!(
            "xy-tiles-{}-{}.xyts",
            std::process::id(),
            SPILL_COUNTER.fetch_add(1, Ordering::Relaxed),
        ));
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(&path)?;

        // Header: magic, format version, base dim, level count, plane flags.
        let mut header = vec![0u8; HEADER_BYTES as usize];
        header[0..4].copy_from_slice(&MAGIC);
        header[4..8].copy_from_slice(&FORMAT_VERSION.to_ne_bytes());
        header[8..12].copy_from_slice(&(dims[0] as u32).to_ne_bytes());
        header[12..16].copy_from_slice(&(dims.len() as u32).to_ne_bytes());
        header[16..20].copy_from_slice(&u32::from(has_color).to_ne_bytes());
        write_all_at(&file, &header, 0)?;

        let store = TileStore {
            file,
            path,
            dims,
            tiles_per_side,
            slab_base,
            total_slabs,
            has_color,
            x0,
            x1,
            y0,
            y1,
            resident: HashMap::new(),
            tick: 0,
            hits: 0,
            misses: 0,
            over_budget: false,
        };

        let mut count_buf = vec![0u8; COUNT_SLAB_BYTES as usize];
        let mut color_buf = vec![0u8; COLOR_SLAB_BYTES as usize];
        for level in 0..store.dims.len() {
            let dim = store.dims[level];
            let counts = p.level_counts(level);
            let color = p.level_color(level);
            let tps = store.tiles_per_side[level] as usize;
            for ty in 0..tps {
                for tx in 0..tps {
                    pack_count_slab(counts, dim, tx, ty, &mut count_buf);
                    write_all_at(
                        &store.file,
                        &count_buf,
                        store.count_offset(level, tx as u32, ty as u32),
                    )?;
                    if let Some(color) = color {
                        pack_color_slab(color, dim, tx, ty, &mut color_buf);
                        write_all_at(
                            &store.file,
                            &color_buf,
                            store.color_offset(level, tx as u32, ty as u32),
                        )?;
                    }
                }
            }
        }
        Ok(store)
    }

    fn slab_index(&self, level: usize, tx: u32, ty: u32) -> u64 {
        self.slab_base[level] + u64::from(ty) * u64::from(self.tiles_per_side[level]) + u64::from(tx)
    }

    fn count_offset(&self, level: usize, tx: u32, ty: u32) -> u64 {
        HEADER_BYTES + self.slab_index(level, tx, ty) * COUNT_SLAB_BYTES
    }

    fn color_offset(&self, level: usize, tx: u32, ty: u32) -> u64 {
        HEADER_BYTES
            + self.total_slabs * COUNT_SLAB_BYTES
            + self.slab_index(level, tx, ty) * COLOR_SLAB_BYTES
    }

    /// Bytes one resident tile costs (both planes plus index entry, D3:
    /// count and color evict together).
    fn tile_bytes(&self) -> u64 {
        COUNT_SLAB_BYTES
            + if self.has_color { COLOR_SLAB_BYTES } else { 0 }
            + TILE_INDEX_ENTRY_BYTES
    }

    pub fn spilled_bytes(&self) -> u64 {
        HEADER_BYTES
            + self.total_slabs
                * (COUNT_SLAB_BYTES + if self.has_color { COLOR_SLAB_BYTES } else { 0 })
    }

    pub fn stats(&self) -> Stats {
        (
            self.hits,
            self.misses,
            global_resident(),
            self.spilled_bytes(),
            budget_get(),
            self.over_budget,
        )
    }

    fn valid_key(&self, level: u32, tx: u32, ty: u32) -> bool {
        (level as usize) < self.dims.len()
            && tx < self.tiles_per_side[level as usize]
            && ty < self.tiles_per_side[level as usize]
    }

    /// Oldest unpinned resident key, if any. Linear scan: resident counts
    /// are budget-bounded (≤ ~2k tiles at the 512 MiB default) and eviction
    /// is off the per-pixel path, so an ordered structure isn't warranted.
    fn lru_victim(&self, pinned: &[(u32, u32, u32)]) -> Option<(u32, u32, u32)> {
        self.resident
            .iter()
            .filter(|(k, _)| !pinned.contains(k))
            .min_by_key(|(_, t)| t.last_used)
            .map(|(k, _)| *k)
    }

    fn evict(&mut self, key: (u32, u32, u32)) -> io::Result<()> {
        let Some(tile) = self.resident.remove(&key) else {
            return Ok(());
        };
        if tile.dirty {
            let (level, tx, ty) = key;
            let mut buf = vec![0u8; COUNT_SLAB_BYTES as usize];
            for (chunk, v) in buf.chunks_exact_mut(4).zip(tile.counts.iter()) {
                chunk.copy_from_slice(&v.to_ne_bytes());
            }
            write_all_at(&self.file, &buf, self.count_offset(level as usize, tx, ty))?;
            // Colored stores refuse appends (D4), so a dirty color plane is
            // unreachable; write-back covers counts only by construction.
        }
        GLOBAL_RESIDENT.fetch_sub(self.tile_bytes(), Ordering::Relaxed);
        Ok(())
    }

    /// Evict own unpinned LRU tiles until the process-wide total fits the
    /// budget (or nothing evictable remains). Victim selection is per-store
    /// in WP1 — an idle sibling store's bytes are reclaimed when *it* next
    /// admits or frees; cross-store reclaim arrives with WP2 host
    /// engagement (recorded in the roadmap WP1 notes).
    fn evict_to_budget(&mut self, headroom: u64, pinned: &[(u32, u32, u32)]) -> io::Result<()> {
        while global_resident() + headroom > budget_get() {
            match self.lru_victim(pinned) {
                Some(victim) => self.evict(victim)?,
                None => break,
            }
        }
        Ok(())
    }

    /// Make the tile resident (faulting its slabs in from disk on miss) and
    /// return it, charging the budget and evicting LRU tiles as needed.
    fn fetch(
        &mut self,
        level: u32,
        tx: u32,
        ty: u32,
        pinned: &[(u32, u32, u32)],
    ) -> io::Result<&Tile> {
        let key = (level, tx, ty);
        self.tick += 1;
        let tick = self.tick;
        if self.resident.contains_key(&key) {
            self.hits += 1;
            let tile = self.resident.get_mut(&key).expect("resident tile");
            tile.last_used = tick;
            return Ok(&self.resident[&key]);
        }
        self.misses += 1;
        let bytes = self.tile_bytes();
        self.evict_to_budget(bytes, pinned)?;
        if global_resident() + bytes > budget_get() {
            // Nothing evictable is left and the admit still overflows: the
            // pinned working set (plus unevictable siblings) exceeds the
            // budget. Proceed — a frame never fails for budget reasons —
            // and record the condition for the §28 reply (D3).
            self.over_budget = true;
        }

        let mut buf = vec![0u8; COUNT_SLAB_BYTES as usize];
        read_exact_at(
            &self.file,
            &mut buf,
            self.count_offset(level as usize, tx, ty),
        )?;
        let mut counts = vec![0u32; TILE_CELLS].into_boxed_slice();
        for (v, chunk) in counts.iter_mut().zip(buf.chunks_exact(4)) {
            *v = u32::from_ne_bytes(chunk.try_into().expect("4-byte chunk"));
        }
        let color = if self.has_color {
            let mut cbuf = vec![0u8; COLOR_SLAB_BYTES as usize];
            read_exact_at(
                &self.file,
                &mut cbuf,
                self.color_offset(level as usize, tx, ty),
            )?;
            let mut cells = vec![[0u16; 4]; TILE_CELLS].into_boxed_slice();
            for (cell, chunk) in cells.iter_mut().zip(cbuf.chunks_exact(8)) {
                for (c, pair) in cell.iter_mut().zip(chunk.chunks_exact(2)) {
                    *c = u16::from_ne_bytes(pair.try_into().expect("2-byte chunk"));
                }
            }
            Some(cells)
        } else {
            None
        };
        GLOBAL_RESIDENT.fetch_add(bytes, Ordering::Relaxed);
        self.resident.insert(
            key,
            Tile {
                counts,
                color,
                last_used: tick,
                dirty: false,
            },
        );
        Ok(&self.resident[&key])
    }

    /// Copy one tile's planes into caller buffers (`out_color` may be `None`
    /// for count-only reads). Serves the WP2 hosts' tile-keyed transfers and
    /// the ABI smoke test; residency/accounting behave exactly like a
    /// compose-driven fetch.
    pub fn fetch_into(
        &mut self,
        level: u32,
        tx: u32,
        ty: u32,
        out_counts: &mut [u32],
        out_color: Option<&mut [[u16; 4]]>,
    ) -> io::Result<bool> {
        if !self.valid_key(level, tx, ty) || out_counts.len() != TILE_CELLS {
            return Ok(false);
        }
        if let Some(ref oc) = out_color {
            if !self.has_color || oc.len() != TILE_CELLS {
                return Ok(false);
            }
        }
        self.begin_frame();
        let tile = self.fetch(level, tx, ty, &[])?;
        out_counts.copy_from_slice(&tile.counts);
        if let Some(oc) = out_color {
            oc.copy_from_slice(tile.color.as_ref().expect("colored store"));
        }
        self.finish_frame()?;
        Ok(true)
    }

    /// Reset the per-frame over-budget record; every ABI-visible operation
    /// (compose / fetch / append) is one "frame" for D3 recording purposes.
    fn begin_frame(&mut self) {
        self.over_budget = false;
    }

    /// After a frame's pins release, return residency to the configured
    /// budget (D3). The over-budget record set during the frame stands
    /// until the next frame overwrites it.
    fn finish_frame(&mut self) -> io::Result<()> {
        self.evict_to_budget(0, &[])
    }

    /// The cell rect `[gx0, gx1) × [gy0, gy1)` of `level` that a compose of
    /// this window will read, derived with the *same* per-pixel / per-range
    /// arithmetic `compose_level` uses so the gathered view provably covers
    /// every access. `None` when the window reads no cells (compose still
    /// succeeds — the grid is all zeros).
    #[allow(clippy::too_many_arguments)]
    fn needed_rect(
        &self,
        level: usize,
        lo_x: f64,
        hi_x: f64,
        lo_y: f64,
        hi_y: f64,
        w: usize,
        h: usize,
    ) -> Option<(usize, usize, usize, usize)> {
        let dim = self.dims[level];
        let (cx0, cx1) = tiles::center_range(lo_x, hi_x, self.x0, self.x1, dim);
        let (cy0, cy1) = tiles::center_range(lo_y, hi_y, self.y0, self.y1, dim);
        let upsampling = (cx1 - cx0) < w || (cy1 - cy0) < h;
        if !upsampling {
            if cx0 >= cx1 || cy0 >= cy1 {
                return None;
            }
            return Some((cx0, cx1, cy0, cy1));
        }
        // Upsample pulls the source cell under each output pixel; replicate
        // the pixel→cell mapping to bound the touched cells exactly.
        let cell_x = (self.x1 - self.x0) / dim as f64;
        let cell_y = (self.y1 - self.y0) / dim as f64;
        let sx = w as f64 / (hi_x - lo_x);
        let sy = h as f64 / (hi_y - lo_y);
        let inv_cell_x = 1.0 / cell_x;
        let inv_cell_y = 1.0 / cell_y;
        let mut gx: Option<(usize, usize)> = None;
        for ox in 0..w {
            let xdata = lo_x + (ox as f64 + 0.5) / sx;
            let cx = ((xdata - self.x0) * inv_cell_x) as isize;
            if cx >= 0 && (cx as usize) < dim {
                let cx = cx as usize;
                gx = Some(match gx {
                    Some((lo, hi)) => (lo.min(cx), hi.max(cx)),
                    None => (cx, cx),
                });
            }
        }
        let mut gy: Option<(usize, usize)> = None;
        for oy in 0..h {
            let ydata = lo_y + (oy as f64 + 0.5) / sy;
            let cy = ((ydata - self.y0) * inv_cell_y) as isize;
            if cy >= 0 && (cy as usize) < dim {
                let cy = cy as usize;
                gy = Some(match gy {
                    Some((lo, hi)) => (lo.min(cy), hi.max(cy)),
                    None => (cy, cy),
                });
            }
        }
        let ((gx0, gx1), (gy0, gy1)) = (gx?, gy?);
        Some((gx0, gx1 + 1, gy0, gy1 + 1))
    }

    /// Gather the rect's cells from resident tiles into contiguous scratch
    /// planes (row-major, stride `gx1 - gx0`), pinning the working set.
    #[allow(clippy::type_complexity)]
    fn gather_rect(
        &mut self,
        level: usize,
        (gx0, gx1, gy0, gy1): (usize, usize, usize, usize),
        want_color: bool,
    ) -> io::Result<(Vec<u32>, Option<Vec<[u16; 4]>>, Vec<(u32, u32, u32)>)> {
        let stride = gx1 - gx0;
        let rows = gy1 - gy0;
        let mut counts = vec![0u32; stride * rows];
        let mut color = if want_color {
            Some(vec![[0u16; 4]; stride * rows])
        } else {
            None
        };
        // Pinned working set: every tile intersecting the rect — the
        // ≤ ceil(w/256+1) × ceil(h/256+1) frame set of D3.
        let tx_lo = gx0 / TILE_DIM;
        let tx_hi = (gx1 - 1) / TILE_DIM;
        let ty_lo = gy0 / TILE_DIM;
        let ty_hi = (gy1 - 1) / TILE_DIM;
        let mut pinned = Vec::with_capacity((tx_hi - tx_lo + 1) * (ty_hi - ty_lo + 1));
        for ty in ty_lo..=ty_hi {
            for tx in tx_lo..=tx_hi {
                pinned.push((level as u32, tx as u32, ty as u32));
            }
        }
        for &(lv, tx, ty) in pinned.clone().iter() {
            let tile_x0 = tx as usize * TILE_DIM;
            let tile_y0 = ty as usize * TILE_DIM;
            // Rect rows/cols this tile contributes.
            let cx_a = gx0.max(tile_x0);
            let cx_b = gx1.min(tile_x0 + TILE_DIM);
            let cy_a = gy0.max(tile_y0);
            let cy_b = gy1.min(tile_y0 + TILE_DIM);
            let tile = self.fetch(lv, tx, ty, &pinned)?;
            for cy in cy_a..cy_b {
                let src_base = (cy - tile_y0) * TILE_DIM + (cx_a - tile_x0);
                let dst_base = (cy - gy0) * stride + (cx_a - gx0);
                counts[dst_base..dst_base + (cx_b - cx_a)]
                    .copy_from_slice(&tile.counts[src_base..src_base + (cx_b - cx_a)]);
                if let Some(ref mut color) = color {
                    color[dst_base..dst_base + (cx_b - cx_a)].copy_from_slice(
                        &tile.color.as_ref().expect("colored store")
                            [src_base..src_base + (cx_b - cx_a)],
                    );
                }
            }
        }
        Ok((counts, color, pinned))
    }

    /// Compose the window from tiles. Same contract as
    /// [`tiles::compose`]: `Some(level)` on success (grid filled),
    /// `None` when the window outresolves the store at `max_upsample`.
    /// Grids are bit-identical to the in-RAM compose of the same pyramid.
    #[allow(clippy::too_many_arguments)]
    pub fn compose(
        &mut self,
        lo_x: f64,
        hi_x: f64,
        lo_y: f64,
        hi_y: f64,
        w: usize,
        h: usize,
        max_upsample: usize,
        out: &mut [f32],
    ) -> io::Result<Option<usize>> {
        if w == 0 || h == 0 || out.len() != w * h {
            return Ok(None);
        }
        if !(hi_x > lo_x && hi_y > lo_y) {
            return Ok(None);
        }
        let domain = (self.x0, self.x1, self.y0, self.y1);
        let Some(level) = tiles::choose_level_dims(
            &self.dims,
            domain,
            lo_x,
            hi_x,
            lo_y,
            hi_y,
            w,
            h,
            max_upsample,
        ) else {
            return Ok(None);
        };
        self.begin_frame();
        let dim = self.dims[level];
        match self.needed_rect(level, lo_x, hi_x, lo_y, hi_y, w, h) {
            None => {
                out.fill(0.0);
                self.finish_frame()?;
                Ok(Some(level))
            }
            Some(rect) => {
                let (counts, _, _pinned) = self.gather_rect(level, rect, false)?;
                let view =
                    LevelView::window(&counts, None, rect.0, rect.2, rect.1 - rect.0, rect.3 - rect.2);
                tiles::compose_level(domain, dim, &view, lo_x, hi_x, lo_y, hi_y, w, h, out);
                self.finish_frame()?;
                Ok(Some(level))
            }
        }
    }

    /// [`Self::compose`] plus the mean-color plane; contract of
    /// [`tiles::compose_color`] (refuses count-only stores).
    #[allow(clippy::too_many_arguments)]
    pub fn compose_color(
        &mut self,
        lo_x: f64,
        hi_x: f64,
        lo_y: f64,
        hi_y: f64,
        w: usize,
        h: usize,
        max_upsample: usize,
        out: &mut [f32],
        out_rgba: &mut [u8],
    ) -> io::Result<Option<usize>> {
        if !self.has_color {
            return Ok(None);
        }
        let Some(quads) = w.checked_mul(h).and_then(|n| n.checked_mul(4)) else {
            return Ok(None);
        };
        if out_rgba.len() != quads || w == 0 || h == 0 || out.len() != w * h {
            return Ok(None);
        }
        if !(hi_x > lo_x && hi_y > lo_y) {
            return Ok(None);
        }
        let domain = (self.x0, self.x1, self.y0, self.y1);
        let Some(level) = tiles::choose_level_dims(
            &self.dims,
            domain,
            lo_x,
            hi_x,
            lo_y,
            hi_y,
            w,
            h,
            max_upsample,
        ) else {
            return Ok(None);
        };
        self.begin_frame();
        let dim = self.dims[level];
        match self.needed_rect(level, lo_x, hi_x, lo_y, hi_y, w, h) {
            None => {
                out.fill(0.0);
                out_rgba.fill(0);
                self.finish_frame()?;
                Ok(Some(level))
            }
            Some(rect) => {
                let (counts, color, _pinned) = self.gather_rect(level, rect, true)?;
                let color = color.expect("colored gather");
                let view = LevelView::window(
                    &counts,
                    Some(&color),
                    rect.0,
                    rect.2,
                    rect.1 - rect.0,
                    rect.3 - rect.2,
                );
                tiles::compose_level(domain, dim, &view, lo_x, hi_x, lo_y, hi_y, w, h, out);
                tiles::compose_color_level(
                    domain, dim, &view, lo_x, hi_x, lo_y, hi_y, w, h, out_rgba,
                );
                self.finish_frame()?;
                Ok(Some(level))
            }
        }
    }

    /// Count-only dirty-tile append (D4). Every finite pair must stay inside
    /// the original domain (validated before the first write, so a rejected
    /// batch never partially mutates — same atomicity as [`tiles::append`]);
    /// non-finite pairs are skipped (§19 parity with `bin_2d_counts`).
    /// Touched tiles fault in, increment in RAM, and are marked dirty; the
    /// disk slab converges on eviction write-back. The composed result is
    /// bit-identical to a from-scratch rebuild because per-cell integer
    /// increments are exact and order-independent. Colored stores refuse
    /// (the batch's colors are unknown; the caller invalidates and rebuilds
    /// lazily — recorded, D4). Domain growth must be handled by the caller
    /// invalidating the whole store (a grown domain re-keys every tile).
    pub fn append(&mut self, x: &[f64], y: &[f64]) -> io::Result<bool> {
        if x.len() != y.len() || self.has_color {
            return Ok(false);
        }
        for (&xv, &yv) in x.iter().zip(y) {
            if (xv.is_finite() && yv.is_finite())
                && (xv < self.x0 || xv >= self.x1 || yv < self.y0 || yv >= self.y1)
            {
                return Ok(false);
            }
        }
        self.begin_frame();
        let base_dim = self.dims[0];
        let sx = base_dim as f64 / (self.x1 - self.x0);
        let sy = base_dim as f64 / (self.y1 - self.y0);
        for (&xv, &yv) in x.iter().zip(y) {
            if !xv.is_finite() || !yv.is_finite() {
                continue;
            }
            let mut cx = (((xv - self.x0) * sx) as usize).min(base_dim - 1);
            let mut cy = (((yv - self.y0) * sy) as usize).min(base_dim - 1);
            for level in 0..self.dims.len() {
                let (tx, ty) = ((cx / TILE_DIM) as u32, (cy / TILE_DIM) as u32);
                let key = (level as u32, tx, ty);
                self.fetch(level as u32, tx, ty, &[key])?;
                let tile = self.resident.get_mut(&key).expect("fetched tile");
                let cell = &mut tile.counts[(cy % TILE_DIM) * TILE_DIM + (cx % TILE_DIM)];
                *cell = cell.saturating_add(1);
                tile.dirty = true;
                cx >>= 1;
                cy >>= 1;
            }
        }
        self.finish_frame()?;
        Ok(true)
    }
}

impl Drop for TileStore {
    fn drop(&mut self) {
        let bytes = self.tile_bytes() * self.resident.len() as u64;
        GLOBAL_RESIDENT.fetch_sub(bytes, Ordering::Relaxed);
        let _ = fs::remove_file(&self.path);
    }
}

/// Copy the `(tx, ty)` tile of a contiguous `dim`² level into a fixed 256²
/// slab, zero-padding rows/cols past the level edge (levels smaller than a
/// tile occupy the slab's top-left corner, D1).
fn pack_count_slab(level: &[u32], dim: usize, tx: usize, ty: usize, out: &mut [u8]) {
    out.fill(0);
    let x0 = tx * TILE_DIM;
    let y0 = ty * TILE_DIM;
    let cols = TILE_DIM.min(dim.saturating_sub(x0));
    let rows = TILE_DIM.min(dim.saturating_sub(y0));
    for r in 0..rows {
        let src = &level[(y0 + r) * dim + x0..(y0 + r) * dim + x0 + cols];
        let dst = &mut out[r * TILE_DIM * 4..r * TILE_DIM * 4 + cols * 4];
        for (chunk, v) in dst.chunks_exact_mut(4).zip(src.iter()) {
            chunk.copy_from_slice(&v.to_ne_bytes());
        }
    }
}

fn pack_color_slab(level: &[[u16; 4]], dim: usize, tx: usize, ty: usize, out: &mut [u8]) {
    out.fill(0);
    let x0 = tx * TILE_DIM;
    let y0 = ty * TILE_DIM;
    let cols = TILE_DIM.min(dim.saturating_sub(x0));
    let rows = TILE_DIM.min(dim.saturating_sub(y0));
    for r in 0..rows {
        let src = &level[(y0 + r) * dim + x0..(y0 + r) * dim + x0 + cols];
        let dst = &mut out[r * TILE_DIM * 8..r * TILE_DIM * 8 + cols * 8];
        for (chunk, cell) in dst.chunks_exact_mut(8).zip(src.iter()) {
            for (pair, c) in chunk.chunks_exact_mut(2).zip(cell.iter()) {
                pair.copy_from_slice(&c.to_ne_bytes());
            }
        }
    }
}

// -- handle registry (engine doc §3.3) ----------------------------------------

// Stores mutate on every fetch (LRU ticks), so unlike the read-mostly
// pyramid registry each entry is `Arc<Mutex<TileStore>>`: lookups clone the
// Arc and drop the registry lock, then lock only their own store — one
// store's disk fault never serializes another store's compose.
type Registry = (u64, HashMap<u64, Arc<Mutex<TileStore>>>);

static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();

fn registry() -> &'static Mutex<Registry> {
    REGISTRY.get_or_init(|| Mutex::new((0, HashMap::new())))
}

pub fn reg_insert(s: TileStore) -> u64 {
    let mut g = registry().lock().expect("tile store registry poisoned");
    g.0 += 1;
    let h = g.0;
    g.1.insert(h, Arc::new(Mutex::new(s)));
    h
}

pub fn reg_with<R>(h: u64, f: impl FnOnce(&mut TileStore) -> R) -> Option<R> {
    let s = {
        let g = registry().lock().expect("tile store registry poisoned");
        g.1.get(&h).cloned()
    }; // registry lock dropped — only this store's mutex is held for the work
    s.map(|s| f(&mut s.lock().expect("tile store poisoned")))
}

pub fn reg_remove(h: u64) -> bool {
    let mut g = registry().lock().expect("tile store registry poisoned");
    g.1.remove(&h).is_some()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::kernels;

    /// The budget and resident counter are process-wide (D2), so
    /// budget-sensitive assertions serialize on one lock; a poisoned lock
    /// (failed sibling test) is recovered because the state it guards is
    /// re-established by `budget_set` in every test.
    static TEST_LOCK: Mutex<()> = Mutex::new(());

    fn lock_budget() -> std::sync::MutexGuard<'static, ()> {
        TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner())
    }

    /// Deterministic scattered points in [0,100)² (same xorshift as the
    /// tiles.rs fixtures).
    fn scattered(n: usize) -> (Vec<f64>, Vec<f64>) {
        let mut x = Vec::with_capacity(n);
        let mut y = Vec::with_capacity(n);
        let mut s = 0x5EED_1234_u64;
        for _ in 0..n {
            s ^= s << 13;
            s ^= s >> 7;
            s ^= s << 17;
            x.push((s % 10_000) as f64 / 100.0);
            s ^= s << 13;
            s ^= s >> 7;
            s ^= s << 17;
            y.push((s % 10_000) as f64 / 100.0);
        }
        (x, y)
    }

    /// Windows spanning both compose regimes: aligned full-domain, an
    /// unaligned sub-window (downsample banding regime), a pan-adjacent
    /// window, and a deep window served only by upsampling.
    const WINDOWS: [(f64, f64, f64, f64, usize, usize, usize); 4] = [
        (0.0, 100.0, 0.0, 100.0, 512, 384, 2),
        (13.7, 87.1, 22.4, 61.9, 300, 200, 2),
        (40.0, 90.0, 10.0, 60.0, 256, 256, 2),
        (49.0, 51.0, 49.0, 51.0, 256, 256, 1 << 20),
    ];

    #[test]
    fn spill_fetch_and_compose_match_in_ram_bit_for_bit() {
        let _g = lock_budget();
        budget_set(0);
        let (x, y) = scattered(60_000);
        let p = tiles::build(&x, &y, 0.0, 100.0, 0.0, 100.0, 1024).unwrap();
        let mut store = TileStore::spill(&p).unwrap();

        // Tile fetch reproduces the exact level cells (finest level has 4×4
        // tiles at base 1024).
        let mut tile = vec![0u32; TILE_CELLS];
        assert!(store.fetch_into(0, 3, 2, &mut tile, None).unwrap());
        let lvl = p.level_counts(0);
        for r in 0..TILE_DIM {
            assert_eq!(
                &tile[r * TILE_DIM..(r + 1) * TILE_DIM],
                &lvl[(2 * TILE_DIM + r) * 1024 + 3 * TILE_DIM..(2 * TILE_DIM + r) * 1024 + 4 * TILE_DIM],
                "fetched tile row {r} must equal the level slice"
            );
        }
        // Out-of-range keys and color requests on a count-only store refuse.
        assert!(!store.fetch_into(99, 0, 0, &mut tile, None).unwrap());
        assert!(!store.fetch_into(0, 4, 0, &mut tile, None).unwrap());
        let mut color = vec![[0u16; 4]; TILE_CELLS];
        assert!(!store.fetch_into(0, 0, 0, &mut tile, Some(&mut color)).unwrap());

        for &(lo_x, hi_x, lo_y, hi_y, w, h, up) in &WINDOWS {
            let mut in_ram = vec![0.0f32; w * h];
            let mut tiled = vec![7.0f32; w * h];
            let expect = tiles::compose(&p, lo_x, hi_x, lo_y, hi_y, w, h, up, &mut in_ram);
            let got = store
                .compose(lo_x, hi_x, lo_y, hi_y, w, h, up, &mut tiled)
                .unwrap();
            assert_eq!(got, expect, "level choice must match for {lo_x}..{hi_x}");
            assert!(got.is_some());
            assert_eq!(tiled, in_ram, "tile compose must be bit-identical");
        }
        // Outresolving windows refuse identically (caller re-bins, §28).
        let mut tiny = vec![0.0f32; 512 * 512];
        assert_eq!(
            store
                .compose(50.0, 50.01, 50.0, 50.01, 512, 512, 2, &mut tiny)
                .unwrap(),
            None
        );
    }

    #[test]
    fn colored_spill_composes_bit_for_bit_and_refuses_append() {
        let _g = lock_budget();
        budget_set(0);
        let (x, y) = scattered(30_000);
        let idx: Vec<u8> = x.iter().map(|&v| u8::from(v >= 50.0)).collect();
        let lut: [[u8; 4]; 2] = [[255, 0, 0, 255], [0, 0, 255, 255]];
        let colors = kernels::BinColorSource::Indexed {
            idx: &idx,
            lut: &lut,
        };
        let p = tiles::build_color(&x, &y, &colors, 0.0, 100.0, 0.0, 100.0, 512).unwrap();
        let mut store = TileStore::spill(&p).unwrap();
        for &(lo_x, hi_x, lo_y, hi_y, w, h, up) in &WINDOWS {
            let mut counts_ram = vec![0.0f32; w * h];
            let mut rgba_ram = vec![0u8; w * h * 4];
            let mut counts_tiled = vec![0.0f32; w * h];
            let mut rgba_tiled = vec![9u8; w * h * 4];
            let expect = tiles::compose_color(
                &p,
                lo_x,
                hi_x,
                lo_y,
                hi_y,
                w,
                h,
                up,
                &mut counts_ram,
                &mut rgba_ram,
            );
            let got = store
                .compose_color(
                    lo_x,
                    hi_x,
                    lo_y,
                    hi_y,
                    w,
                    h,
                    up,
                    &mut counts_tiled,
                    &mut rgba_tiled,
                )
                .unwrap();
            assert_eq!(got, expect);
            assert!(got.is_some());
            assert_eq!(counts_tiled, counts_ram, "counts bit-identical");
            assert_eq!(rgba_tiled, rgba_ram, "mean colors bit-identical");
        }
        // Colored stores refuse appends (D4): the batch's colors are unknown.
        assert!(!store.append(&[50.0], &[50.0]).unwrap());
        // A count-only store refuses color composition, like the pyramid.
        let (px, py) = scattered(1000);
        let plain = tiles::build(&px, &py, 0.0, 100.0, 0.0, 100.0, 512).unwrap();
        let mut plain_store = TileStore::spill(&plain).unwrap();
        let mut c = vec![0.0f32; 16];
        let mut q = vec![0u8; 64];
        assert_eq!(
            plain_store
                .compose_color(0.0, 100.0, 0.0, 100.0, 4, 4, 2, &mut c, &mut q)
                .unwrap(),
            None
        );
    }

    #[test]
    fn lru_keeps_resident_bytes_at_budget_and_records_over_budget() {
        let _g = lock_budget();
        assert_eq!(global_resident(), 0, "no resident tiles leak across tests");
        let (x, y) = scattered(60_000);
        let p = tiles::build(&x, &y, 0.0, 100.0, 0.0, 100.0, 1024).unwrap();
        let mut store = TileStore::spill(&p).unwrap();
        // Room for six tiles: every 300×200 deep window below needs a
        // working set of at most four finest-level tiles.
        let budget = 6 * (COUNT_SLAB_BYTES + TILE_INDEX_ENTRY_BYTES);
        budget_set(budget);
        // Sweep windows across the extent at the finest level (large
        // max_upsample keeps level 0 serving), forcing tile turnover.
        for step in 0..8 {
            let lo = step as f64 * 10.0;
            let mut g = vec![0.0f32; 300 * 200];
            let got = store
                .compose(lo, lo + 22.0, lo, lo + 15.0, 300, 200, 1 << 20, &mut g)
                .unwrap();
            assert!(got.is_some());
            let (_, _, resident, _, stat_budget, over) = store.stats();
            assert_eq!(stat_budget, budget);
            assert!(
                resident <= budget,
                "resident {resident} must return to budget {budget} after pins release"
            );
            assert!(!over, "a working set under budget never records over_budget");
        }
        let (hits, misses, ..) = store.stats();
        assert!(misses > 0, "the sweep must fault tiles in");
        // Re-composing the last window immediately is served from residency.
        let mut g = vec![0.0f32; 300 * 200];
        store
            .compose(70.0, 92.0, 70.0, 85.0, 300, 200, 1 << 20, &mut g)
            .unwrap();
        let (hits_after, ..) = store.stats();
        assert!(hits_after > hits, "an immediate pan re-uses resident tiles");

        // A budget below one tile: the frame still composes correctly and
        // the condition is recorded, never a silent degrade (D3).
        budget_set(1);
        let mut over_grid = vec![0.0f32; 300 * 200];
        let got = store
            .compose(0.0, 22.0, 0.0, 15.0, 300, 200, 1 << 20, &mut over_grid)
            .unwrap();
        assert!(got.is_some());
        let mut expect = vec![0.0f32; 300 * 200];
        tiles::compose(&p, 0.0, 22.0, 0.0, 15.0, 300, 200, 1 << 20, &mut expect);
        assert_eq!(over_grid, expect, "over-budget frames stay bit-identical");
        let (.., over) = store.stats();
        assert!(over, "working set above budget is recorded, not silent");
        budget_set(0);
    }

    #[test]
    fn append_equals_full_rebuild_and_rejections_are_atomic() {
        let _g = lock_budget();
        let (x, y) = scattered(40_000);
        let p = tiles::build(&x, &y, 0.0, 100.0, 0.0, 100.0, 1024).unwrap();
        let mut store = TileStore::spill(&p).unwrap();
        // A tiny budget forces dirty write-backs between the appends and the
        // composes, exercising disk convergence (D4).
        budget_set(2 * (COUNT_SLAB_BYTES + TILE_INDEX_ENTRY_BYTES));

        let tail_x = vec![10.0, 10.0, 50.0, 99.99, f64::NAN, 3.0];
        let tail_y = vec![20.0, 20.0, 50.0, 0.01, 10.0, f64::NAN];
        assert!(store.append(&tail_x, &tail_y).unwrap());

        let mut all_x = x.clone();
        let mut all_y = y.clone();
        all_x.extend_from_slice(&tail_x);
        all_y.extend_from_slice(&tail_y);
        let rebuilt = tiles::build(&all_x, &all_y, 0.0, 100.0, 0.0, 100.0, 1024).unwrap();
        for &(lo_x, hi_x, lo_y, hi_y, w, h, up) in &WINDOWS {
            let mut expect = vec![0.0f32; w * h];
            let mut got = vec![0.0f32; w * h];
            let lvl_expect = tiles::compose(&rebuilt, lo_x, hi_x, lo_y, hi_y, w, h, up, &mut expect);
            let lvl_got = store
                .compose(lo_x, hi_x, lo_y, hi_y, w, h, up, &mut got)
                .unwrap();
            assert_eq!(lvl_got, lvl_expect);
            assert_eq!(got, expect, "dirty-tile append equals a from-scratch rebuild");
        }

        // Domain growth refuses atomically: the store composes exactly as
        // before the rejected batch (the caller invalidates and respills).
        let mut before = vec![0.0f32; 512 * 384];
        store
            .compose(0.0, 100.0, 0.0, 100.0, 512, 384, 2, &mut before)
            .unwrap();
        assert!(!store.append(&[50.0, 100.0], &[50.0, 50.0]).unwrap());
        let mut after = vec![0.0f32; 512 * 384];
        store
            .compose(0.0, 100.0, 0.0, 100.0, 512, 384, 2, &mut after)
            .unwrap();
        assert_eq!(after, before, "rejected append must not partially mutate");
        budget_set(0);
    }

    #[test]
    fn registry_roundtrip_and_spill_file_lifecycle() {
        let _g = lock_budget();
        budget_set(0);
        let (x, y) = scattered(500);
        let p = tiles::build(&x, &y, 0.0, 100.0, 0.0, 100.0, 64).unwrap();
        let store = TileStore::spill(&p).unwrap();
        let path = store.path.clone();
        assert!(path.exists(), "spill file exists while the store lives");
        let (_, _, _, spilled, ..) = store.stats();
        assert_eq!(
            spilled,
            HEADER_BYTES + store.total_slabs * COUNT_SLAB_BYTES,
            "spilled_bytes reports the whole file"
        );
        let h = reg_insert(store);
        assert!(h > 0);
        let total = reg_with(h, |s| {
            let mut g = vec![0.0f32; 64 * 64];
            s.compose(0.0, 100.0, 0.0, 100.0, 64, 64, 2, &mut g).unwrap();
            g.iter().map(|&c| c as f64).sum::<f64>()
        })
        .unwrap();
        assert_eq!(total, 500.0, "full-window compose conserves the count");
        assert!(reg_remove(h));
        assert!(!reg_remove(h), "double free is an error, not UB");
        assert!(reg_with(h, |_| ()).is_none(), "stale handle is refused");
        assert!(
            !path.exists(),
            "the spill file is deleted with the store (§27 cache lifecycle)"
        );
        assert_eq!(global_resident(), 0, "drop returns every resident byte");
    }
}
