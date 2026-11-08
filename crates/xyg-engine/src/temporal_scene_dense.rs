//! Screen-bounded temporal scan. Each step does at most STEP source/cell units.
use super::{TemporalError as E, MAX_BYTES};
use std::collections::HashSet;
use std::sync::Arc;
const STEP: usize = 16_384;
#[cfg_attr(target_arch = "wasm32", inline(never))]
pub(super) fn u(b: &[u8], i: usize) -> u32 {
    u32::from_le_bytes(b[i..i + 4].try_into().unwrap())
}
#[cfg_attr(target_arch = "wasm32", inline(never))]
pub(super) fn t(b: &[u8], i: usize) -> i64 {
    i64::from_le_bytes(b[i..i + 8].try_into().unwrap())
}
pub(super) fn f(b: &[u8], i: usize) -> f64 {
    f64::from_bits(t(b, i) as u64)
}
fn fold(h: u64, b: &[u8]) -> u64 {
    b.iter()
        .fold(h, |h, b| (h ^ *b as u64).wrapping_mul(0x100000001b3))
}
fn hash(b: &[u8]) -> u64 {
    fold(0xcbf29ce484222325, b)
}
fn base(b: &[u8]) -> usize {
    128 + u(b, 56) as usize + u(b, 60) as usize
}
#[derive(Default)]
struct Validation {
    ids: HashSet<u64>,
    previous: Option<i64>,
    min: f64,
    max: f64,
    hash: u64,
}
impl Validation {
    fn new(n: usize) -> Self {
        Self {
            ids: HashSet::with_capacity(n),
            max: 1.,
            hash: 0xcbf29ce484222325,
            ..Self::default()
        }
    }
    fn row(&mut self, row: &[u8], kind: u32) -> Result<(), E> {
        let start = t(row, 0);
        let value = f(row, 16);
        let id = t(row, 24) as u64;
        if row[32] > 1
            || row[33] > 1
            || row[34..].iter().any(|&v| v != 0)
            || !value.is_finite()
            || !self.ids.insert(id)
        {
            return Err(E::InvalidArgument);
        }
        if (kind == 1 || kind == 2) && row[32] != 0 && row[33] != 0 && start >= t(row, 8) {
            return Err(E::ReversedInterval);
        }
        if kind == 3 && row[32] != 0 {
            if self.previous.is_some_and(|v| start < v) {
                return Err(E::InvalidArgument);
            }
            self.previous = Some(start);
        }
        self.min = self.min.min(value);
        self.max = self.max.max(value);
        self.hash = fold(self.hash, row);
        Ok(())
    }
}
pub(super) fn validate(b: &[u8]) -> Result<(f64, f64), E> {
    let mut v = Validation::new(u(b, 12) as usize);
    for row in b[base(b)..].chunks_exact(40) {
        v.row(row, u(b, 8))?;
    }
    Ok((v.min, v.max))
}
#[derive(Clone, Default)]
struct Cell {
    count: u64,
    hash: u64,
    min: f64,
    max: f64,
    supports: u64,
    support_hash: u64,
    low: f64,
    high: f64,
}
pub struct Job {
    pub source: Arc<[u8]>,
    old: Option<Arc<[u8]>>,
    validation: Validation,
    grid: Vec<Cell>,
    members: Vec<u8>,
    phase: u32,
    row: usize,
    column: Option<usize>,
    columns: usize,
    lanes: usize,
    admitted: usize,
    work: usize,
    total: u32,
}
impl Job {
    #[inline(never)]
    pub fn new(b: &[u8], budget: usize, old: Option<Arc<[u8]>>) -> Result<Self, E> {
        super::check(b, budget)?;
        let (columns, lanes, admitted) = Self::preview(b, budget)?;
        let n = u(b, 12) as usize;
        if old
            .as_ref()
            .is_some_and(|old| old[8..16] != b[8..16] || old[64..68] != b[64..68])
        {
            return Err(E::InvalidArgument);
        }
        Ok(Self {
            source: Arc::from(b),
            old,
            validation: Validation::new(n),
            grid: Vec::new(),
            members: Vec::new(),
            phase: 0,
            row: 0,
            column: None,
            columns,
            lanes,
            admitted,
            work: 0,
            total: 0,
        })
    }
    pub fn preview(b: &[u8], budget: usize) -> Result<(usize, usize, usize), E> {
        if b.len() < 128 {
            return Err(E::InvalidArgument);
        }
        let prefix = 128usize
            .checked_add(u(b, 56) as usize)
            .and_then(|v| v.checked_add(u(b, 60) as usize))
            .ok_or(E::BudgetExceeded)?;
        let wire_len = prefix
            .checked_add(
                (u(b, 12) as usize)
                    .checked_mul(40)
                    .ok_or(E::BudgetExceeded)?,
            )
            .ok_or(E::BudgetExceeded)?;
        super::check_frame(b, budget, wire_len)?;
        if b.len() < base(b) {
            return Err(E::InvalidArgument);
        }

        if u(b, 4) != 2 {
            return Err(E::InvalidArgument);
        }
        let n = u(b, 12) as usize;
        let op = u(b, 88);
        let columns = ((f(b, 16) as usize - 89) / 4).max(1);
        let lanes = if u(b, 8) == 3 || u(b, 8) == 4 { 1 } else { 16 };
        let admitted = wire_len
            .checked_mul(6)
            .and_then(|v| v.checked_add(n.checked_mul(32)?))
            .and_then(|v| v.checked_add(columns * lanes * 4096 + 131072))
            .ok_or(E::BudgetExceeded)?;
        if admitted > budget || budget > MAX_BYTES {
            return Err(E::BudgetExceeded);
        }
        if op > 3
            || u(b, 100) > 256
            || b[120..].get(..8).is_none_or(|s| s.iter().any(|&v| v != 0))
            || ((op == 1 || op == 3) && (u(b, 92) as usize >= columns * lanes || u(b, 100) == 0))
        {
            return Err(E::InvalidArgument);
        }
        if &b[128..128 + u(b, 56) as usize] != b"UTC" {
            return Err(E::UnitUnsupported);
        }
        std::str::from_utf8(&b[128 + u(b, 56) as usize..base(b)])
            .map_err(|_| E::InvalidArgument)?;
        Ok((columns, lanes, admitted))
    }
    pub fn owned_bytes(&self) -> usize {
        self.source.len()
            + self.validation.ids.capacity() * 16
            + self.grid.capacity() * std::mem::size_of::<Cell>()
            + self.members.capacity()
    }
    pub fn progress(&self) -> (u32, usize, usize) {
        (self.phase, self.row, self.work)
    }
    #[inline(never)]
    pub fn step(&mut self, cancel: &dyn Fn() -> bool) -> Result<bool, E> {
        let n = u(&self.source, 12) as usize;
        let kind = u(&self.source, 8);
        for _ in 0..STEP {
            if cancel() {
                return Err(E::Cancelled);
            }
            if self.phase == 0 {
                if self.row == n {
                    let b = &self.source;
                    let op = u(b, 88);
                    if (op == 1 || op == 3)
                        && (b[104..112] != self.validation.hash.to_le_bytes()
                            || b[112..120] != hash(&b[8..88]).to_le_bytes())
                    {
                        return Err(E::StaleRevision);
                    }
                    self.validation.ids = HashSet::new();
                    self.old = None;
                    self.grid = vec![Cell::default(); self.columns * self.lanes];
                    self.phase = 1;
                    self.row = 0;
                    continue;
                }
                let b = &self.source;
                let at = base(b) + self.row * 40;
                let row = &b[at..at + 40];
                if self.old.as_ref().is_some_and(|old| {
                    old[base(old) + self.row * 40..base(old) + (self.row + 1) * 40] != *row
                }) {
                    return Err(E::InvalidArgument);
                }
                self.validation.row(row, kind)?;
                self.row += 1;
                continue;
            }
            if self.row == n {
                self.phase = 2;
                return Ok(true);
            }
            let b = &self.source;
            let at = base(b) + self.row * 40;
            let row = &b[at..at + 40];
            let lo = t(b, 32) as i128;
            let hi = t(b, 40) as i128;
            let span = hi - lo;
            let start = t(row, 0) as i128;
            let interval = kind == 1 || kind == 2;
            let line = kind == 3;
            let left = if interval && row[32] == 0 {
                lo
            } else if line && self.row > 0 && b[at - 40 + 32] != 0 {
                t(b, at - 40) as i128
            } else {
                start
            };
            let right = if interval {
                if row[33] == 0 {
                    hi
                } else {
                    t(row, 8) as i128
                }
            } else if line && self.row + 1 < n && b[at + 40 + 32] != 0 {
                t(b, at + 40) as i128
            } else {
                start
            };
            if (!interval && row[32] == 0)
                || right < lo
                || left >= hi
                || (interval && right == lo)
                || (!interval && !line && (start < lo || start >= hi))
            {
                self.row += 1;
                self.column = None;
                continue;
            }
            let first = (((left.max(lo) - lo) * self.columns as i128) / span) as usize;
            let last = if line {
                ((((right.min(hi) - lo) * self.columns as i128) / span) as usize)
                    .min(self.columns - 1)
            } else if interval {
                (((right.min(hi) - lo) * self.columns as i128 - 1).max(0) / span) as usize
            } else {
                first
            };
            let col = self.column.unwrap_or(first);
            let cell_lo = lo * self.columns as i128 + col as i128 * span;
            let cell_hi = cell_lo + span;
            let value = f(row, 16);
            let lane =
                ((crate::scene::linear_fraction(value, self.validation.min, self.validation.max)
                    * self.lanes as f64) as usize)
                    .min(self.lanes - 1);
            let index = col * self.lanes + lane;
            let sample = start >= lo
                && start < hi
                && (start - lo) * self.columns as i128 / span == col as i128;
            let ph = f(b, 24) - 96.;
            let y = |v: f64| {
                crate::scene::linear_fraction(-v, -self.validation.max, -self.validation.min) * ph
            };
            let mut low = f64::INFINITY;
            let mut high = f64::NEG_INFINITY;
            if line {
                if sample {
                    low = y(value);
                    high = low;
                }
                for neighbor in [
                    self.row.checked_sub(1),
                    self.row.checked_add(1).filter(|&i| i < n),
                ]
                .into_iter()
                .flatten()
                {
                    let other = base(b) + neighbor * 40;
                    if b[other + 32] == 0 {
                        continue;
                    }
                    let (a, z) = if neighbor < self.row {
                        (other, at)
                    } else {
                        (at, other)
                    };
                    let ta = t(b, a) as i128 * self.columns as i128;
                    let tz = t(b, z) as i128 * self.columns as i128;
                    if tz < cell_lo || ta >= cell_hi {
                        continue;
                    }
                    let ya = y(f(b, a + 16));
                    let yz = y(f(b, z + 16));
                    let one = super::interpolate(ta, tz, ya, yz, cell_lo.max(ta));
                    let two = if ta == tz {
                        yz
                    } else {
                        super::interpolate(ta, tz, ya, yz, cell_hi.min(tz))
                    };
                    low = low.min(one).min(two);
                    high = high.max(one).max(two);
                }
            }
            self.work += 1;
            if self.work > 64 * 1024 * 1024 {
                return Err(E::BudgetExceeded);
            }
            if !line || low.is_finite() {
                let c = &mut self.grid[index];
                let supports = line && !sample;
                if c.count + c.supports == 0 {
                    c.low = low;
                    c.high = high;
                } else {
                    c.low = c.low.min(low);
                    c.high = c.high.max(high);
                }
                if !supports {
                    if c.count == 0 {
                        c.min = value;
                        c.max = value;
                    }
                    c.min = c.min.min(value);
                    c.max = c.max.max(value);
                }
                let (count, membership_hash) = if supports {
                    (&mut c.supports, &mut c.support_hash)
                } else {
                    (&mut c.count, &mut c.hash)
                };
                *count += 1;
                *membership_hash =
                    (*membership_hash ^ hash(&row[24..32])).wrapping_mul(0x100000001b3);
                let op = u(b, 88);
                if (op == 1 && !supports || op == 3 && supports) && index == u(b, 92) as usize {
                    if self.total >= u(b, 96) && self.members.len() / 8 < (u(b, 100) as usize) {
                        self.members.extend_from_slice(&row[24..32]);
                    }
                    self.total += 1;
                }
            }
            if col >= last {
                self.row += 1;
                self.column = None;
            } else {
                self.column = Some(col + 1);
            }
        }
        Ok(false)
    }
    #[inline(never)]
    pub fn finish(&self, budget: usize) -> Result<Vec<u8>, E> {
        if self.phase != 2 {
            return Err(E::InvalidArgument);
        }
        let b = &self.source;
        let op = u(b, 88);
        let line = u(b, 8) == 3;
        if op != 0 {
            let mut out = vec![0; 64];
            out[..4].copy_from_slice(b"XYTL");
            for (at, v) in [
                (4, if line { 3u64 } else { 2 }),
                (12, op as u64),
                (20, self.validation.hash),
                (28, hash(&b[8..88])),
                (36, self.admitted as u64),
                (44, u(b, 12) as u64),
                (52, self.grid.len() as u64),
            ] {
                out[at..at + 8].copy_from_slice(&v.to_le_bytes());
            }
            if op == 1 || op == 3 {
                out[60..64].copy_from_slice(&self.total.to_le_bytes());
                out.extend_from_slice(&self.members);
            } else {
                out[60..64].copy_from_slice(&(if line { 72u32 } else { 40 }).to_le_bytes());
                for (i, c) in self
                    .grid
                    .iter()
                    .enumerate()
                    .filter(|(_, c)| c.count + c.supports != 0)
                {
                    for v in [i as u64, c.count, c.hash, c.min.to_bits(), c.max.to_bits()] {
                        out.extend_from_slice(&v.to_le_bytes());
                    }
                    if line {
                        for v in [
                            c.supports,
                            c.support_hash,
                            c.low.to_bits(),
                            c.high.to_bits(),
                        ] {
                            out.extend_from_slice(&v.to_le_bytes());
                        }
                    }
                }
            }
            return Ok(out);
        }
        let mut kinds = Vec::new();
        let mut ids = Vec::new();
        let mut x0 = Vec::new();
        let mut x1 = Vec::new();
        let mut y0 = Vec::new();
        let mut y1 = Vec::new();
        let ph = f(b, 24) - 96.;
        let pw = f(b, 16) - 89.;
        let y = |v: f64| {
            crate::scene::linear_fraction(-v, -self.validation.max, -self.validation.min) * ph
        };
        for (i, c) in self
            .grid
            .iter()
            .enumerate()
            .filter(|(_, c)| c.count + c.supports != 0)
        {
            kinds.push(2);
            ids.push(i as u64);
            x0.push((i / self.lanes) as f64 / self.columns as f64 * pw);
            x1.push((i / self.lanes + 1) as f64 / self.columns as f64 * pw);
            let (mut a, mut z) = if line {
                (c.low, c.high)
            } else if u(b, 8) == 4 {
                (y(c.max).min(y(0.)), y(c.min).max(y(0.)))
            } else {
                (
                    ph - (i % self.lanes + 1) as f64 / self.lanes as f64 * ph,
                    ph - (i % self.lanes) as f64 / self.lanes as f64 * ph,
                )
            };
            if a == z {
                a = (a - 1.).clamp(0., ph - 2.);
                z = a + 2.;
            }
            y0.push(a);
            y1.push(z);
        }
        super::paint(
            b,
            budget,
            &kinds,
            &ids,
            &vec![0; kinds.len()],
            &vec![0.; kinds.len()],
            &x0,
            &y0,
            &x1,
            &y1,
        )
    }
}
pub(super) fn compile(b: &[u8], budget: usize) -> Result<Vec<u8>, E> {
    let mut job = Job::new(b, budget, None)?;
    while !job.step(&|| false)? {}
    job.finish(budget)
}
