//! Programmatic Filter Tier C session (§34). XYFC/XYFR v1 is shared by all hosts.
//! Prefix slabs contain counts only, never active-cells × canonical-row masks.
#[path = "filter_tier_c_linked.rs"]
mod linked;
use linked::{GridHandle, Linked};
use std::cell::Cell;
use std::sync::atomic::{AtomicU64, Ordering};

pub const HEADER: usize = 96;
pub const REPLY_HEADER: usize = 192;
pub const MAX_PACKET: usize = 256 << 20;
const MAX_DIMS: usize = 64;
const MAX_VIEWS: usize = 64;
const MAX_CUTS: usize = 4096;
const MAX_BINS: usize = 65536;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u32)]
pub enum Error {
    Malformed = 1,
    Budget = 2,
    Stale = 3,
    Cancelled = 4,
    Missing = 5,
    Boundary = 6,
    Source = 7,
    Allocation = 8,
}
type Result<T> = std::result::Result<T, Error>;
fn add(a: usize, b: usize) -> Result<usize> {
    a.checked_add(b)
        .filter(|v| *v <= u32::MAX as usize)
        .ok_or(Error::Budget)
}
fn mul(a: usize, b: usize) -> Result<usize> {
    a.checked_mul(b)
        .filter(|v| *v <= u32::MAX as usize)
        .ok_or(Error::Budget)
}
fn alloc<T: Default + Clone>(n: usize) -> Result<Vec<T>> {
    let mut v = Vec::new();
    v.try_reserve_exact(n).map_err(|_| Error::Allocation)?;
    v.resize(n, T::default());
    Ok(v)
}
fn u64_at(b: &[u8], at: usize) -> Result<u64> {
    Ok(u64::from_le_bytes(
        b.get(at..at + 8)
            .ok_or(Error::Malformed)?
            .try_into()
            .unwrap(),
    ))
}
fn u32_at(b: &[u8], at: usize) -> Result<u32> {
    Ok(u32::from_le_bytes(
        b.get(at..at + 4)
            .ok_or(Error::Malformed)?
            .try_into()
            .unwrap(),
    ))
}
fn usize_at(b: &[u8], at: usize) -> Result<usize> {
    u32::try_from(u64_at(b, at)?)
        .map(|v| v as usize)
        .map_err(|_| Error::Budget)
}
fn f64_at(b: &[u8], at: usize) -> Result<f64> {
    Ok(f64::from_bits(u64_at(b, at)?))
}
fn put(b: &mut [u8], at: usize, v: u64) {
    b[at..at + 8].copy_from_slice(&v.to_le_bytes());
}

#[derive(Debug)]
struct Source {
    id: u64,
    epoch: u64,
    revision: u64,
    first: u64,
    rows: usize,
    columns: Vec<Vec<f64>>,
}
impl Source {
    fn bytes(&self) -> usize {
        self.columns.iter().map(|c| c.capacity() * 8).sum::<usize>() + self.columns.capacity() * 24
    }
}
#[derive(Debug)]
struct Axis {
    dimension: usize,
    cuts: Vec<f64>,
}
impl Axis {
    fn cell(&self, x: f64) -> usize {
        self.cuts.partition_point(|v| *v <= x)
    }
    fn read(b: &[u8], cursor: &mut usize, dimension: usize, dims: usize) -> Result<Self> {
        let n = usize_at(b, *cursor)?;
        *cursor = add(*cursor, 8)?;
        if dimension >= dims || n > MAX_CUTS {
            return Err(Error::Malformed);
        }
        let end = add(*cursor, mul(n, 8)?)?;
        if end > b.len() {
            return Err(Error::Malformed);
        }
        let mut cuts = alloc(n)?;
        for (i, v) in cuts.iter_mut().enumerate() {
            *v = f64_at(b, *cursor + i * 8)?;
        }
        if cuts.iter().any(|x| !x.is_finite()) || cuts.windows(2).any(|p| p[0] >= p[1]) {
            return Err(Error::Malformed);
        }
        *cursor = end;
        Ok(Self { dimension, cuts })
    }
}
#[derive(Debug)]
struct View {
    id: u64,
    axis: Axis,
    offset: usize,
    grid: Option<GridHandle>,
}
#[derive(Debug)]
struct Config {
    active_id: u64,
    active: Axis,
    views: Vec<View>,
    width: usize,
}
impl View {
    fn bins(&self) -> usize {
        self.grid
            .as_ref()
            .map_or(self.axis.cuts.len() + 1, |g| g.width * g.height)
    }
    fn cell(&self, s: &Source, row: usize) -> Option<usize> {
        if let Some(g) = &self.grid {
            g.cell(s, row)
        } else {
            let x = s.columns[self.axis.dimension][row];
            x.is_finite().then(|| self.axis.cell(x))
        }
    }
}
impl Config {
    fn linked(&self) -> bool {
        self.views.first().is_some_and(|v| v.grid.is_some())
    }
    fn read(b: &[u8], source: &Source) -> Result<Self> {
        let active_id = u64_at(b, 56)?;
        let dimension = usize_at(b, 64)?;
        let n = usize_at(b, 72)?;
        if active_id == 0 || n == 0 || n > MAX_VIEWS {
            return Err(Error::Malformed);
        }
        let mut cursor = HEADER;
        let active = Axis::read(b, &mut cursor, dimension, source.columns.len())?;
        let mut views = Vec::<View>::new();
        views.try_reserve_exact(n).map_err(|_| Error::Allocation)?;
        let mut width = 1; // separate exact selected total; passive nonfinite values are excluded
        for _ in 0..n {
            let id = u64_at(b, cursor)?;
            let dimension = usize_at(b, cursor + 8)?;
            cursor += 16;
            if id == 0 || views.iter().any(|v| v.id == id) {
                return Err(Error::Malformed);
            }
            let axis = Axis::read(b, &mut cursor, dimension, source.columns.len())?;
            let offset = width;
            width = add(width, axis.cuts.len() + 1)?;
            if width > MAX_BINS {
                return Err(Error::Budget);
            }
            views.push(View {
                id,
                axis,
                offset,
                grid: None,
            });
        }
        if cursor != b.len() {
            return Err(Error::Malformed);
        }
        Ok(Self {
            active_id,
            active,
            views,
            width,
        })
    }
    fn bytes(&self) -> usize {
        self.views.iter().filter(|v| v.grid.is_some()).count() * 96
            + self.active.cuts.capacity() * 8
            + self.views.capacity() * 64
            + self
                .views
                .iter()
                .map(|v| v.axis.cuts.capacity() * 8)
                .sum::<usize>()
    }
    fn index_bytes(&self) -> Result<usize> {
        add(
            mul(mul(self.active.cuts.len() + 2, self.width)?, 8)?,
            add(
                mul(self.width, if self.linked() { 16 } else { 8 })?,
                mul(self.active.cuts.len() + 1, 16)?,
            )?,
        )
    }
    fn reply_bytes(&self, counts: bool) -> usize {
        REPLY_HEADER + self.views.len() * 16 + if counts { (self.width - 1) * 8 } else { 0 }
    }
}
#[derive(Debug)]
struct Index {
    prefix: Vec<u64>,
    totals: Vec<u64>,
    extrema: Vec<[f64; 2]>,
    base: Vec<u64>,
}
impl Index {
    fn build(
        source: &Source,
        cfg: &Config,
        linked: &Linked,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Self> {
        let cells = cfg.active.cuts.len() + 1;
        let mut prefix = alloc::<u64>((cells + 1) * cfg.width)?;
        let mut totals = alloc::<u64>(cfg.width)?;
        let mut base = alloc::<u64>(if cfg.linked() { cfg.width } else { 0 })?;
        let mut extrema = alloc::<[f64; 2]>(cells)?;
        extrema.fill([f64::INFINITY, f64::NEG_INFINITY]);
        for row in 0..source.rows {
            if row % 4096 == 0 && cancelled() {
                return Err(Error::Cancelled);
            }
            totals[0] += 1;
            let eligible = !cfg.linked() || linked.matches(source, row);
            if eligible && cfg.linked() {
                base[0] += 1;
            }
            let x = source.columns[cfg.active.dimension][row];
            let cell = if eligible && x.is_finite() {
                Some(cfg.active.cell(x))
            } else {
                None
            };
            if let Some(c) = cell {
                extrema[c][0] = extrema[c][0].min(x);
                extrema[c][1] = extrema[c][1].max(x);
                prefix[(c + 1) * cfg.width] += 1;
            }
            for v in &cfg.views {
                if let Some(cbin) = v.cell(source, row) {
                    let bin = v.offset + cbin;
                    totals[bin] += 1;
                    if eligible && cfg.linked() {
                        base[bin] += 1;
                    }
                    if let Some(c) = cell {
                        prefix[(c + 1) * cfg.width + bin] += 1;
                    }
                }
            }
        }
        for cell in 1..=cells {
            if cancelled() {
                return Err(Error::Cancelled);
            }
            for b in 0..cfg.width {
                prefix[cell * cfg.width + b] += prefix[(cell - 1) * cfg.width + b];
            }
        }
        Ok(Self {
            prefix,
            totals,
            extrema,
            base,
        })
    }
    fn interval(&self, bounds: [f64; 2]) -> Result<(usize, usize)> {
        let mut first = None;
        let mut end = 0;
        for (i, [min, max]) in self.extrema.iter().copied().enumerate() {
            if min > max || max < bounds[0] || min > bounds[1] {
                continue;
            }
            if min < bounds[0] || max > bounds[1] {
                return Err(Error::Boundary);
            }
            first.get_or_insert(i);
            end = i + 1;
        }
        Ok((first.unwrap_or(0), end))
    }
}

/// Owns canonical source, persistent predicate intent, and one disposable active index.
/// No materialized row-mask prefix or cached result is retained.
#[derive(Debug)]
pub struct FilterTierCSession {
    source: Option<Source>,
    config: Option<Config>,
    index: Option<Index>,
    intent: Option<[f64; 2]>,
    revision: u64,
    newest: u64,
    cancelled: u64,
    budget: usize,
    peak_observed: Cell<usize>,
    limit: usize,
    linked: Linked,
}
impl Default for FilterTierCSession {
    fn default() -> Self {
        Self {
            source: None,
            config: None,
            index: None,
            intent: None,
            revision: 0,
            newest: 0,
            cancelled: 0,
            budget: 0,
            peak_observed: Cell::new(0),
            limit: MAX_PACKET,
            linked: Linked::default(),
        }
    }
}
impl FilterTierCSession {
    pub fn with_limit(limit: usize) -> Self {
        Self {
            limit: limit.min(MAX_PACKET),
            ..Self::default()
        }
    }
    pub fn retained_bytes(&self) -> usize {
        512 + self.linked.bytes()
            + self.source.as_ref().map_or(0, Source::bytes)
            + self.config.as_ref().map_or(0, Config::bytes)
            + if self.index.is_some() {
                self.config.as_ref().unwrap().index_bytes().unwrap()
            } else {
                0
            }
    }
    fn admit(&self, extra: usize, input: usize, output: usize, budget: usize) -> Result<usize> {
        let peak = add(add(self.retained_bytes(), extra)?, add(input, output)?)?;
        if peak > budget {
            return Err(Error::Budget);
        }
        self.peak_observed.set(self.peak_observed.get().max(peak));
        Ok(peak)
    }
    fn fingerprint(&self) -> u64 {
        if self.config.as_ref().is_some_and(Config::linked) {
            return self.linked.fingerprint(
                self.source.as_ref(),
                self.config.as_ref(),
                self.intent,
            );
        }
        let mut h = crate::transition::Blake2s8::domain(*b"xyfilt01");
        if let Some(s) = &self.source {
            h.update(&s.id.to_le_bytes());
            h.update(&s.epoch.to_le_bytes());
            h.update(&s.revision.to_le_bytes());
        }
        h.update(
            &self
                .config
                .as_ref()
                .map_or(u64::MAX, |c| c.active.dimension as u64)
                .to_le_bytes(),
        );
        h.update(&[u8::from(self.intent.is_some())]);
        if let Some(bounds) = self.intent {
            for x in bounds {
                h.update(&(if x == 0. { 0. } else { x }).to_bits().to_le_bytes());
            }
        }
        u64::from_le_bytes(h.finish())
    }
    fn reply(
        &self,
        requested: u64,
        status: u32,
        tier: u64,
        fallback: u64,
        rows: u64,
        reads: u64,
        peak: usize,
        selected: u64,
        counts: Option<&[u64]>,
        membership: &[u8],
        page_first: u64,
        buffer: Option<Vec<u8>>,
    ) -> Result<Vec<u8>> {
        let cfg = self.config.as_ref();
        let len = add(
            cfg.map_or(REPLY_HEADER, |c| c.reply_bytes(counts.is_some())),
            membership.len(),
        )?;
        let mut b = match buffer {
            Some(b) => b,
            None => alloc::<u8>(len)?,
        };
        b[..4].copy_from_slice(b"XYFR");
        b[4..8].copy_from_slice(&1u32.to_le_bytes());
        b[8..12].copy_from_slice(&status.to_le_bytes());
        let s = self.source.as_ref();
        for (at, v) in [
            (16, requested),
            (24, self.revision),
            (32, s.map_or(0, |s| s.id)),
            (40, s.map_or(0, |s| s.epoch)),
            (48, s.map_or(0, |s| s.revision)),
            (56, self.fingerprint()),
            (64, tier),
            (
                72,
                if self.index.is_some() {
                    cfg.unwrap().index_bytes()? as u64
                } else {
                    0
                },
            ),
            (80, self.retained_bytes() as u64),
            (88, peak as u64),
            (96, rows),
            (104, reads),
            (112, fallback),
            (120, cfg.map_or(0, |c| c.active_id)),
            (128, selected),
            (136, cfg.map_or(0, |c| c.views.len() as u64)),
            (144, self.newest),
            (152, s.map_or(0, |s| s.first)),
            (160, s.map_or(0, |s| s.rows as u64)),
            (168, page_first),
            (176, membership.len() as u64),
            (
                184,
                u64::from(
                    self.intent.is_some()
                        || cfg.is_some_and(Config::linked) && self.linked.has_intent(),
                ),
            ),
        ] {
            put(&mut b, at, v);
        }
        let mut at = REPLY_HEADER;
        if let Some(c) = cfg {
            for v in &c.views {
                put(&mut b, at, v.id);
                let n = if counts.is_some() { v.bins() } else { 0 };
                put(&mut b, at + 8, n as u64);
                at += 16;
                if let Some(counts) = counts {
                    for x in &counts[v.offset..v.offset + n] {
                        put(&mut b, at, *x);
                        at += 8;
                    }
                }
            }
        }
        b[at..at + membership.len()].copy_from_slice(membership);
        Ok(b)
    }

    /// Capacity failure returns required bytes and publishes nothing. Structurally
    /// valid request revisions are consumed even on refusal; retry with a newer revision.
    pub fn execute(
        &mut self,
        b: &[u8],
        capacity: usize,
        superseded: impl Fn() -> bool,
    ) -> std::result::Result<Vec<u8>, usize> {
        self.peak_observed.set(self.retained_bytes());
        let requested = u64_at(b, 16).unwrap_or(0);
        let error = match self.prepare(b, capacity, &superseded) {
            Ok(reply) => return Ok(reply),
            Err(PrepareError::Capacity(n)) => return Err(n),
            Err(PrepareError::Policy(e)) => e,
        };
        let reply = self
            .reply(
                requested,
                error as u32,
                0,
                if error == Error::Boundary { 1 } else { 0 },
                0,
                0,
                self.peak_observed.get(),
                0,
                None,
                &[],
                0,
                None,
            )
            .unwrap_or_default();
        if reply.len() > capacity {
            Err(reply.len())
        } else {
            Ok(reply)
        }
    }
    fn prepare(
        &mut self,
        b: &[u8],
        capacity: usize,
        superseded: &impl Fn() -> bool,
    ) -> std::result::Result<Vec<u8>, PrepareError> {
        if b.len() < HEADER || b.len() > MAX_PACKET || &b[..4] != b"XYFC" || u32_at(b, 4)? != 1 {
            return Err(Error::Malformed.into());
        }
        let op = u32_at(b, 8)?;
        let flags = u32_at(b, 12)?;
        let seq = u64_at(b, 16)?;
        if !(1..=15).contains(&op) || flags > 1 || (flags != 0 && op != 5 && op != 11) || seq == 0 {
            return Err(Error::Malformed.into());
        }
        if seq <= self.cancelled {
            return Err(Error::Cancelled.into());
        }
        if seq <= self.newest {
            return Err(Error::Stale.into());
        }
        self.newest = seq;
        let budget = if op == 1 {
            usize_at(b, 48)?
        } else {
            self.budget
        };
        if budget > self.limit {
            return Err(Error::Budget.into());
        }
        if op != 1 {
            let s = self.source.as_ref().ok_or(Error::Missing)?;
            if u64_at(b, 24)? != s.id
                || u64_at(b, 32)? != s.epoch
                || u64_at(b, 40)? != s.revision
                || usize_at(b, 48)? != self.budget
            {
                return Err(Error::Source.into());
            }
        }
        let cancelled = || superseded();
        if cancelled() {
            return Err(Error::Cancelled.into());
        }
        if op >= 10 || self.config.as_ref().is_some_and(Config::linked) && matches!(op, 3..=5 | 7) {
            return self.prepare_linked(b, capacity, superseded, op, flags, seq, budget);
        }
        let mut new_source = None;
        let mut new_config = None;
        let mut new_index = None;
        let mut evict = false;
        let mut cancel = false;
        let mut intent = None;
        let mut counts = None;
        let mut membership = Vec::new();
        let mut rows = 0;
        let mut reads = 0;
        let mut selected = 0;
        let mut tier = 0;
        let mut fallback = 0;
        let mut page_first = 0;
        let mut peak = self.admit(0, b.len(), REPLY_HEADER + MAX_VIEWS * 16, budget)?;
        match op {
            1 | 2 => {
                if op == 1 && self.source.is_some() {
                    return Err(Error::Source.into());
                }
                let dims = usize_at(b, 56)?;
                let n = usize_at(b, 64)?;
                let first = u64_at(b, 72)?;
                if dims == 0
                    || dims > MAX_DIMS
                    || u64_at(b, 24)? == 0
                    || u64_at(b, 32)? == 0
                    || (op == 1 && u64_at(b, 40)? != 1)
                    || b.len() != add(HEADER, mul(mul(dims, n)?, 8)?)?
                {
                    return Err(Error::Malformed.into());
                }
                let old = if op == 2 { self.source.as_ref() } else { None };
                let old_rows = old.map_or(0, |s| s.rows);
                if let Some(s) = old {
                    if dims != s.columns.len()
                        || first != s.first.checked_add(s.rows as u64).ok_or(Error::Malformed)?
                    {
                        return Err(Error::Source.into());
                    }
                }
                let total = add(old_rows, n)?;
                let source_first = old.map_or(first, |s| s.first);
                source_first
                    .checked_add(total as u64)
                    .ok_or(Error::Malformed)?;
                let rev = if let Some(s) = old {
                    s.revision.checked_add(1).ok_or(Error::Malformed)?
                } else {
                    1
                };
                let bytes = add(mul(mul(dims, total)?, 8)?, mul(dims, 24)?)?;
                peak = self.admit(bytes, b.len(), REPLY_HEADER + MAX_VIEWS * 16, budget)?;
                let mut columns = Vec::new();
                columns
                    .try_reserve_exact(dims)
                    .map_err(|_| Error::Allocation)?;
                for d in 0..dims {
                    let mut column = alloc::<f64>(total)?;
                    if let Some(s) = old {
                        column[..old_rows].copy_from_slice(&s.columns[d]);
                    }
                    for row in 0..n {
                        if row % 4096 == 0 && cancelled() {
                            return Err(Error::Cancelled.into());
                        }
                        column[old_rows + row] = f64_at(b, HEADER + (d * n + row) * 8)?;
                    }
                    columns.push(column);
                }
                rows = n as u64;
                new_source = Some(Source {
                    id: u64_at(b, 24)?,
                    epoch: u64_at(b, 32)?,
                    revision: rev,
                    first: source_first,
                    rows: total,
                    columns,
                });
                evict = true;
            }
            3 | 4 => {
                let source = self.source.as_ref().ok_or(Error::Missing)?;
                if op == 3 {
                    self.admit(
                        add(b.len(), mul(usize_at(b, 72)?.min(MAX_VIEWS), 64)?)?,
                        b.len(),
                        REPLY_HEADER + MAX_VIEWS * 16,
                        budget,
                    )?;
                    new_config = Some(Config::read(b, source)?);
                    if self.intent.is_some()
                        && self.config.as_ref().is_some_and(|c| {
                            c.active.dimension != new_config.as_ref().unwrap().active.dimension
                        })
                    {
                        return Err(Error::Malformed.into());
                    }
                } else if b.len() != HEADER {
                    return Err(Error::Malformed.into());
                }
                let cfg = new_config
                    .as_ref()
                    .or(self.config.as_ref())
                    .ok_or(Error::Missing)?;
                let extra = add(
                    cfg.index_bytes()?,
                    new_config.as_ref().map_or(0, Config::bytes),
                )?;
                peak = self.admit(extra, b.len(), cfg.reply_bytes(false), budget)?;
                new_index = Some(Index::build(source, cfg, &self.linked, &cancelled)?);
                rows = source.rows as u64;
            }
            5 | 7 => {
                if b.len() != HEADER {
                    return Err(Error::Malformed.into());
                }
                let source = self.source.as_ref().ok_or(Error::Missing)?;
                let cfg = self.config.as_ref().ok_or(Error::Missing)?;
                let index = self.index.as_ref().ok_or(Error::Missing)?;
                peak = self.admit(mul(cfg.width, 8)?, b.len(), cfg.reply_bytes(true), budget)?;
                let mut result = alloc::<u64>(cfg.width)?;
                tier = 3;
                if op == 7 {
                    result.copy_from_slice(&index.totals);
                    intent = Some(None);
                } else {
                    let lo = f64_at(b, 80)?;
                    let hi = f64_at(b, 88)?;
                    if !lo.is_finite() || !hi.is_finite() {
                        return Err(Error::Malformed.into());
                    }
                    let bounds = [lo.min(hi), lo.max(hi)];
                    match index.interval(bounds) {
                        Ok((first, end)) => {
                            for (i, v) in result.iter_mut().enumerate() {
                                *v = index.prefix[end * cfg.width + i]
                                    - index.prefix[first * cfg.width + i];
                            }
                            reads = (2 * cfg.width) as u64;
                        }
                        Err(Error::Boundary) if flags == 1 => {
                            tier = 2;
                            fallback = 1;
                            for row in 0..source.rows {
                                if row % 4096 == 0 && cancelled() {
                                    return Err(Error::Cancelled.into());
                                }
                                let x = source.columns[cfg.active.dimension][row];
                                rows += 1;
                                if !x.is_finite() || x < bounds[0] || x > bounds[1] {
                                    continue;
                                }
                                result[0] += 1;
                                for v in &cfg.views {
                                    let x = source.columns[v.axis.dimension][row];
                                    if x.is_finite() {
                                        result[v.offset + v.axis.cell(x)] += 1;
                                    }
                                }
                            }
                        }
                        Err(e) => return Err(e.into()),
                    }
                    intent = Some(Some(bounds));
                }
                selected = result[0];
                counts = Some(result);
            }
            6 => {
                if b.len() != HEADER {
                    return Err(Error::Malformed.into());
                }
                evict = true;
            }
            8 => {
                if b.len() != HEADER {
                    return Err(Error::Malformed.into());
                }
                cancel = true;
            }
            9 => {
                if b.len() != HEADER {
                    return Err(Error::Malformed.into());
                }
                let s = self.source.as_ref().ok_or(Error::Missing)?;
                let start = u64_at(b, 56)?;
                let n = usize_at(b, 64)?;
                let offset = u32::try_from(start.checked_sub(s.first).ok_or(Error::Source)?)
                    .map_err(|_| Error::Source)? as usize;
                if n > 65536 || add(offset, n)? > s.rows {
                    return Err(Error::Malformed.into());
                }
                page_first = start;
                let membership_len = n.div_ceil(8);
                rows = n as u64;
                tier = 2;
                fallback = 2;
                peak = self.admit(
                    membership_len,
                    b.len(),
                    self.config
                        .as_ref()
                        .map_or(REPLY_HEADER, |c| c.reply_bytes(false))
                        + membership_len,
                    budget,
                )?;
                membership = alloc::<u8>(membership_len)?;
                for i in 0..n {
                    if i % 4096 == 0 && cancelled() {
                        return Err(Error::Cancelled.into());
                    }
                    let yes = self.linked.matches(s, offset + i)
                        && if let Some([lo, hi]) = self.intent {
                            let cfg = self.config.as_ref().ok_or(Error::Missing)?;
                            let x = s.columns[cfg.active.dimension][offset + i];
                            x.is_finite() && x >= lo && x <= hi
                        } else {
                            true
                        };
                    if yes {
                        membership[i / 8] |= 1 << (i % 8);
                        selected += 1;
                    }
                }
            }
            _ => unreachable!(),
        }
        // Capacity is checked before any source/config/index/intent publication.
        let cfg = new_config.as_ref().or(self.config.as_ref());
        let len = cfg.map_or(REPLY_HEADER, |c| c.reply_bytes(counts.is_some())) + membership.len();
        if capacity < len {
            return Err(PrepareError::Capacity(len));
        }
        let buffer = alloc::<u8>(len)?;
        if cancelled() {
            return Err(Error::Cancelled.into());
        }
        if cancel {
            self.cancelled = seq;
        }
        if let Some(s) = new_source {
            self.source = Some(s);
            self.budget = budget;
        }
        if let Some(c) = new_config {
            self.config = Some(c);
        }
        if evict {
            self.index = None;
        }
        if let Some(i) = new_index {
            self.index = Some(i);
        }
        if let Some(i) = intent {
            self.intent = i;
        }
        self.revision = seq;
        self.reply(
            seq,
            0,
            tier,
            fallback,
            rows,
            reads,
            self.peak_observed.get().max(peak),
            selected,
            counts.as_deref(),
            &membership,
            page_first,
            Some(buffer),
        )
        .map_err(PrepareError::Policy)
    }
}
#[derive(Debug)]
enum PrepareError {
    Policy(Error),
    Capacity(usize),
}
impl From<Error> for PrepareError {
    fn from(e: Error) -> Self {
        Self::Policy(e)
    }
}

/// Adapter-owned concurrent request/cancellation watermarks. Newer native work
/// supersedes a scan before it can publish; WASM commands are serialized.
#[derive(Debug, Default)]
pub struct RequestGate {
    newest: AtomicU64,
    cancelled: AtomicU64,
}
impl RequestGate {
    pub fn enter(&self, b: &[u8]) -> u64 {
        let seq = u64_at(b, 16).unwrap_or(0);
        let op = u32_at(b, 8).unwrap_or(0);
        let flags = u32_at(b, 12).unwrap_or(u32::MAX);
        // Match prepare's structural admission before consuming a watermark.
        // Body refusals consume revisions; invalid headers do not.
        if (HEADER..=MAX_PACKET).contains(&b.len())
            && b.get(..4) == Some(b"XYFC")
            && u32_at(b, 4) == Ok(1)
            && (1..=15).contains(&op)
            && flags <= 1
            && (flags == 0 || op == 5 || op == 11)
            && seq != 0
        {
            self.newest.fetch_max(seq, Ordering::AcqRel);
        }
        seq
    }
    pub fn cancel(&self, seq: u64) {
        self.cancelled.fetch_max(seq, Ordering::AcqRel);
    }
    pub fn obsolete(&self, seq: u64) -> bool {
        self.newest.load(Ordering::Acquire) > seq || self.cancelled.load(Ordering::Acquire) >= seq
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn filter_tier_c_complete_shared_protocol_packets() {
        let fixture = include_bytes!("../../../tests/fixtures/filter_tier_c/session.bin");
        let mut at = 0;
        let mut state = FilterTierCSession::default();
        let mut cases = 0;
        while at < fixture.len() {
            let n = u32_at(fixture, at).unwrap() as usize;
            let cap = u32_at(fixture, at + 4).unwrap() as usize;
            let status = i32::from_le_bytes(fixture[at + 8..at + 12].try_into().unwrap());
            let reply_n = u32_at(fixture, at + 12).unwrap() as usize;
            let required = u64_at(fixture, at + 16).unwrap();
            at += 24;
            let request = &fixture[at..at + n];
            at += n;
            let expected = &fixture[at..at + reply_n];
            at += reply_n;
            match state.execute(request, cap, || false) {
                Ok(reply) => {
                    assert_eq!(status, 0, "case {cases}");
                    assert_eq!(reply, expected, "case {cases}");
                }
                Err(n) => {
                    assert_eq!(status, -4);
                    assert_eq!(n as u64, required);
                }
            }
            cases += 1;
        }
        assert_eq!(cases, 47);
    }
    #[test]
    fn filter_tier_c_checked_products_and_concurrent_gate() {
        assert_eq!(mul(usize::MAX, 2), Err(Error::Budget));
        assert_eq!(add(usize::MAX, 1), Err(Error::Budget));
        let gate = RequestGate::default();
        let mut input = vec![0; HEADER];
        input[..4].copy_from_slice(b"XYFC");
        input[4..8].copy_from_slice(&1u32.to_le_bytes());
        input[8..12].copy_from_slice(&5u32.to_le_bytes());
        put(&mut input, 16, 7);
        assert_eq!(gate.enter(&input), 7);
        assert!(!gate.obsolete(7));
        put(&mut input, 16, 8);
        gate.enter(&input);
        assert!(gate.obsolete(7));
        gate.cancel(8);
        assert!(gate.obsolete(8));
    }
}

#[cfg(test)]
mod publication_tests {
    use super::*;
    #[test]
    fn filter_tier_c_newer_request_cannot_publish_older_prepared_intent() {
        let fixture = include_bytes!("../../../tests/fixtures/filter_tier_c/session.bin");
        let mut state = FilterTierCSession::default();
        let mut at = 0;
        for _ in 0..2 {
            let n = u32_at(fixture, at).unwrap() as usize;
            let reply_n = u32_at(fixture, at + 12).unwrap() as usize;
            let start = at + 24;
            state
                .execute(&fixture[start..start + n], 1 << 20, || false)
                .unwrap();
            at = start + n + reply_n;
        }
        let n = u32_at(fixture, at).unwrap() as usize;
        let query = &fixture[at + 24..at + 24 + n];
        let gate = RequestGate::default();
        let seq = gate.enter(query);
        let mut newer = query.to_vec();
        put(&mut newer, 16, seq + 1);
        let checks = Cell::new(0);
        let response = state
            .execute(query, 1 << 20, || {
                let count = checks.get() + 1;
                checks.set(count);
                if count == 2 {
                    gate.enter(&newer);
                }
                gate.obsolete(seq)
            })
            .unwrap();
        assert_eq!(u32_at(&response, 8), Ok(Error::Cancelled as u32));
        assert_eq!(state.revision, 2);
        assert_eq!(state.intent, None);
        let response = state.execute(&newer, 1 << 20, || false).unwrap();
        assert_eq!(u32_at(&response, 8), Ok(0));
        assert_eq!(state.revision, seq + 1);
        assert_eq!(state.intent, Some([0., 0.5]));
        let stale = state.execute(query, 1 << 20, || false).unwrap();
        assert_eq!(u32_at(&stale, 8), Ok(Error::Stale as u32));
    }
}

#[cfg(test)]
mod budget_tests {
    use super::*;
    #[test]
    fn filter_tier_c_session_cannot_enlarge_owner_budget() {
        let fixture = include_bytes!("../../../tests/fixtures/filter_tier_c/session.bin");
        let n = u32_at(fixture, 0).unwrap() as usize;
        let mut state = FilterTierCSession::with_limit(1024);
        let reply = state
            .execute(&fixture[24..24 + n], 1 << 20, || false)
            .unwrap();
        assert_eq!(u32_at(&reply, 8), Ok(Error::Budget as u32));
        assert!(state.source.is_none());
        assert_eq!(state.revision, 0);
    }
}
