//! Ordinary linked density extension of XYFC v1. Counts share the same cumulative
//! slabs, canonical source, revision gate, and atomic publication as 1D sessions.
use super::*;

#[derive(Debug)]
pub(super) struct Grid {
    pub x: usize,
    pub y: usize,
    pub width: usize,
    pub height: usize,
    pub range: [f64; 4],
    pub colors: [u8; 8],
}
// A checked singleton slice keeps View within its historical 64-byte logical
// slot on native/WASM. No infallible per-view Box allocation is introduced.
#[derive(Debug)]
pub(super) struct GridHandle(Box<[Grid]>);
impl GridHandle {
    fn new(grid: Grid) -> Result<Self> {
        let mut values = Vec::new();
        values.try_reserve_exact(1).map_err(|_| Error::Allocation)?;
        values.push(grid);
        Ok(Self(values.into_boxed_slice()))
    }
}
impl std::ops::Deref for GridHandle {
    type Target = Grid;
    fn deref(&self) -> &Grid {
        &self.0[0]
    }
}
impl Grid {
    pub fn cell(&self, source: &Source, row: usize) -> Option<usize> {
        let x = source.columns[self.x][row];
        let y = source.columns[self.y][row];
        let [x0, x1, y0, y1] = self.range;
        if !x.is_finite() || !y.is_finite() || x < x0 || x >= x1 || y < y0 || y >= y1 {
            return None;
        }
        let cx = (((x - x0) * (self.width as f64 / (x1 - x0))) as usize).min(self.width - 1);
        let cy = (((y - y0) * (self.height as f64 / (y1 - y0))) as usize).min(self.height - 1);
        Some(cy * self.width + cx)
    }
}
#[derive(Clone, Copy, Debug)]
pub(super) struct Clause {
    id: u64,
    dim: usize,
    bounds: [f64; 2],
}
impl Clause {
    fn matches(self, s: &Source, row: usize) -> bool {
        let x = s.columns[self.dim][row];
        x.is_finite() && x >= self.bounds[0] && x <= self.bounds[1]
    }
}
#[derive(Debug, Default)]
pub(super) struct Linked {
    clauses: Vec<Clause>,
    base: Vec<Clause>,
    mask: Vec<u8>,
    mask_digest: [u8; 8],
    edit: Option<Vec<Clause>>,
}
fn copy<T: Clone>(v: &[T]) -> Result<Vec<T>> {
    let mut out = Vec::new();
    out.try_reserve_exact(v.len())
        .map_err(|_| Error::Allocation)?;
    out.extend_from_slice(v);
    Ok(out)
}
impl Linked {
    fn duplicate(&self) -> Result<Self> {
        Ok(Self {
            clauses: copy(&self.clauses)?,
            base: copy(&self.base)?,
            mask: copy(&self.mask)?,
            mask_digest: self.mask_digest,
            edit: self.edit.as_ref().map(|v| copy(v)).transpose()?,
        })
    }
    pub fn has_intent(&self) -> bool {
        !self.clauses.is_empty() || !self.base.is_empty() || !self.mask.is_empty()
    }
    pub fn bytes(&self) -> usize {
        (self.clauses.capacity()
            + self.base.capacity()
            + self.edit.as_ref().map_or(0, Vec::capacity))
            * 32
            + self.mask.capacity()
    }
    pub fn matches(&self, source: &Source, row: usize) -> bool {
        (self.mask.is_empty()
            || self
                .mask
                .get(row / 8)
                .is_some_and(|b| b & (1 << (row % 8)) != 0))
            && self
                .base
                .iter()
                .chain(&self.clauses)
                .all(|c| c.matches(source, row))
    }
    fn all(&self, cfg: &Config, intent: Option<[f64; 2]>) -> Result<Vec<Clause>> {
        let mut v = Vec::new();
        v.try_reserve_exact(self.clauses.len() + usize::from(intent.is_some()))
            .map_err(|_| Error::Allocation)?;
        v.extend_from_slice(&self.clauses);
        if let Some(bounds) = intent {
            v.push(Clause {
                id: cfg.active_id,
                dim: cfg.active.dimension,
                bounds,
            });
        }
        if v.len() > MAX_VIEWS {
            return Err(Error::Budget);
        }
        v.sort_unstable_by_key(|c| (c.id, c.dim));
        Ok(v)
    }
    pub fn fingerprint(
        &self,
        source: Option<&Source>,
        cfg: Option<&Config>,
        intent: Option<[f64; 2]>,
    ) -> u64 {
        let mut h = crate::transition::Blake2s8::domain(*b"xyfilt02");
        if let Some(s) = source {
            for v in [s.id, s.epoch, s.revision, s.first, s.rows as u64] {
                h.update(&v.to_le_bytes());
            }
        }
        // Iterate canonical key order without allocating during error publication.
        for base in [true, false] {
            h.update(&[u8::from(base)]);
            h.update(
                &((if base {
                    self.base.len()
                } else {
                    self.clauses.len() + usize::from(intent.is_some())
                }) as u64)
                    .to_le_bytes(),
            );
            let clauses = if base { &self.base } else { &self.clauses };
            let active = cfg.and_then(|c| {
                intent.map(|bounds| Clause {
                    id: c.active_id,
                    dim: c.active.dimension,
                    bounds,
                })
            });
            let active = if base { None } else { active };
            let mut previous = None;
            for _ in 0..clauses.len() + usize::from(active.is_some()) {
                let next = clauses
                    .iter()
                    .copied()
                    .chain(active)
                    .filter(|c| previous.is_none_or(|p| (c.id, c.dim) > p))
                    .min_by_key(|c| (c.id, c.dim));
                if let Some(c) = next {
                    previous = Some((c.id, c.dim));
                    h.update(&c.id.to_le_bytes());
                    h.update(&(c.dim as u64).to_le_bytes());
                    for x in c.bounds {
                        h.update(&(if x == 0. { 0. } else { x }).to_bits().to_le_bytes());
                    }
                }
            }
        }
        h.update(&(self.mask.len() as u64).to_le_bytes());
        h.update(&self.mask_digest);
        u64::from_le_bytes(h.finish())
    }
}
impl Config {
    fn read_density(b: &[u8], source: &Source) -> Result<Self> {
        let active_id = u64_at(b, 56)?;
        let dimension = usize_at(b, 64)?;
        let n = usize_at(b, 72)?;
        if active_id == 0 || n == 0 || n > MAX_VIEWS {
            return Err(Error::Malformed);
        }
        let mut at = HEADER;
        let active = Axis::read(b, &mut at, dimension, source.columns.len())?;
        if add(at, mul(n, 80)?)? != b.len() {
            return Err(Error::Malformed);
        }
        let mut views = Vec::new();
        views.try_reserve_exact(n).map_err(|_| Error::Allocation)?;
        let mut width = 1;
        for _ in 0..n {
            let id = u64_at(b, at)?;
            let x = usize_at(b, at + 8)?;
            let y = usize_at(b, at + 16)?;
            let w = u32_at(b, at + 24)? as usize;
            let h = u32_at(b, at + 28)? as usize;
            let mut range = [0.; 4];
            for (i, v) in range.iter_mut().enumerate() {
                *v = f64_at(b, at + 32 + i * 8)?;
            }
            if id == 0
                || views.iter().any(|v: &View| v.id == id)
                || x >= source.columns.len()
                || y >= source.columns.len()
                || w == 0
                || h == 0
                || range.iter().any(|v| !v.is_finite())
            {
                return Err(Error::Malformed);
            }
            for pair in range.chunks_exact_mut(2) {
                if pair[0] > pair[1] {
                    pair.swap(0, 1);
                }
                if pair[0] == pair[1]
                    || !(pair[1] - pair[0]).is_finite()
                    || !(pair[0] as f32).is_finite()
                    || !(pair[1] as f32).is_finite()
                    || pair[0] as f32 == pair[1] as f32
                {
                    return Err(Error::Malformed);
                }
            }
            if !(w as f64 / (range[1] - range[0])).is_finite()
                || !(h as f64 / (range[3] - range[2])).is_finite()
            {
                return Err(Error::Malformed);
            }
            let bins = mul(w, h)?;
            let offset = width;
            width = add(width, bins)?;
            if width > MAX_BINS {
                return Err(Error::Budget);
            }
            let color_flags = u32_at(b, at + 72)?;
            if color_flags > 1 || u32_at(b, at + 76)? != 0 {
                return Err(Error::Malformed);
            }
            let mut colors = [57, 135, 229, 255, 239, 105, 45, 255];
            if color_flags == 1 {
                colors.copy_from_slice(&b[at + 64..at + 72]);
            }
            views.push(View {
                id,
                axis: Axis {
                    dimension: x,
                    cuts: Vec::new(),
                },
                offset,
                grid: Some(GridHandle::new(Grid {
                    x,
                    y,
                    width: w,
                    height: h,
                    range,
                    colors,
                })?),
            });
            at += 80;
        }
        if !views.iter().any(|v| {
            v.id == active_id
                && v.grid
                    .as_ref()
                    .is_some_and(|g| dimension == g.x || dimension == g.y)
        }) {
            return Err(Error::Source);
        }
        Ok(Self {
            active_id,
            active,
            views,
            width,
        })
    }
    fn paint_bytes(&self) -> Result<usize> {
        add(
            16,
            add(mul(self.views.len(), 56)?, mul(self.width - 1, 16)?)?,
        )
    }
}
impl FilterTierCSession {
    pub(super) fn prepare_linked(
        &mut self,
        b: &[u8],
        capacity: usize,
        cancelled: &impl Fn() -> bool,
        op: u32,
        flags: u32,
        seq: u64,
        budget: usize,
    ) -> std::result::Result<Vec<u8>, PrepareError> {
        let source = self.source.as_ref().ok_or(Error::Missing)?;
        let modifying = matches!(op, 7 | 10 | 12..=15);
        // Old and replacement state coexist. Admission precedes even configuration
        // parsing, predicate cloning and active×passive slab allocation.
        let mut peak = self.admit(
            if modifying {
                add(self.linked.bytes() * 2, add(b.len(), MAX_VIEWS * 192)?)?
            } else {
                0
            },
            b.len(),
            REPLY_HEADER + MAX_VIEWS * 16,
            budget,
        )?;
        let mut state = if modifying {
            Some(self.linked.duplicate()?)
        } else {
            None
        };
        let mut intent = self.intent;
        let mut new_config = None;
        let mut invalidate = false;
        let mut build = matches!(op, 4 | 10);
        if op != 10 && self.config.as_ref().is_none_or(|c| !c.linked()) {
            return Err(Error::Missing.into());
        }
        match op {
            3 => return Err(Error::Malformed.into()),
            10 => {
                let cfg = Config::read_density(b, source)?;
                let st = state.as_mut().unwrap();
                if let Some(old) = &self.config {
                    if !old.linked() && self.intent.is_some() {
                        return Err(Error::Source.into());
                    }
                    st.clauses = st.all(old, self.intent)?;
                }
                intent = st
                    .clauses
                    .iter()
                    .find(|c| c.id == cfg.active_id && c.dim == cfg.active.dimension)
                    .map(|c| c.bounds);
                st.clauses
                    .retain(|c| !(c.id == cfg.active_id && c.dim == cfg.active.dimension));
                new_config = Some(cfg);
            }
            7 => {
                state.as_mut().unwrap().clauses.clear();
                intent = None;
                build = true;
            }
            12 => {
                let n = usize_at(b, 56)?;
                let m = usize_at(b, 64)?;
                if n > MAX_DIMS
                    || m != 0 && m != source.rows.div_ceil(8)
                    || b.len() != add(HEADER, add(mul(n, 24)?, m)?)?
                {
                    return Err(Error::Malformed.into());
                }
                if m > 0 && source.rows % 8 != 0 && b[b.len() - 1] >> (source.rows % 8) != 0 {
                    return Err(Error::Malformed.into());
                }
                let st = state.as_mut().unwrap();
                let mut base = Vec::new();
                base.try_reserve_exact(n).map_err(|_| Error::Allocation)?;
                for i in 0..n {
                    let at = HEADER + i * 24;
                    let dim = usize_at(b, at)?;
                    let lo = f64_at(b, at + 8)?;
                    let hi = f64_at(b, at + 16)?;
                    if dim >= source.columns.len()
                        || !lo.is_finite()
                        || !hi.is_finite()
                        || base.iter().any(|c: &Clause| c.dim == dim)
                    {
                        return Err(Error::Malformed.into());
                    }
                    base.push(Clause {
                        id: 0,
                        dim,
                        bounds: [lo.min(hi), lo.max(hi)],
                    });
                }
                st.base = base;
                st.mask = copy(&b[HEADER + n * 24..])?;
                st.mask_digest = if st.mask.is_empty() {
                    [0; 8]
                } else {
                    let mut digest = crate::transition::Blake2s8::domain(*b"xyfmsk01");
                    for chunk in st.mask.chunks(4096) {
                        if cancelled() {
                            return Err(Error::Cancelled.into());
                        }
                        digest.update(chunk);
                    }
                    digest.finish()
                };
                invalidate = true;
            }
            13 => {
                let st = state.as_mut().unwrap();
                if st.edit.is_some() {
                    return Err(Error::Malformed.into());
                }
                st.edit = Some(st.all(self.config.as_ref().unwrap(), intent)?);
            }
            14 => {
                let st = state.as_mut().unwrap();
                let cfg = self.config.as_ref().unwrap();
                let all = st.edit.take().ok_or(Error::Missing)?;
                st.clauses = all;
                intent = st
                    .clauses
                    .iter()
                    .find(|c| c.id == cfg.active_id && c.dim == cfg.active.dimension)
                    .map(|c| c.bounds);
                st.clauses
                    .retain(|c| !(c.id == cfg.active_id && c.dim == cfg.active.dimension));
                invalidate = true;
            }
            15 => {
                if state.as_mut().unwrap().edit.take().is_none() {
                    return Err(Error::Missing.into());
                }
            }
            4 | 5 | 11 => {}
            _ => return Err(Error::Malformed.into()),
        }
        if op != 10 && op != 12 && b.len() != HEADER {
            return Err(Error::Malformed.into());
        }
        let cfg = new_config
            .as_ref()
            .or(self.config.as_ref())
            .ok_or(Error::Missing)?;
        let st = state.as_ref().unwrap_or(&self.linked);
        if op == 5 {
            let lo = f64_at(b, 80)?;
            let hi = f64_at(b, 88)?;
            if !lo.is_finite() || !hi.is_finite() {
                return Err(Error::Malformed.into());
            }
            intent = Some([lo.min(hi), lo.max(hi)]);
        }
        // The active range consumes the same C-clause budget as retained ranges.
        // Refuse before building an index or publishing any replacement intent.
        if st.clauses.len() + usize::from(intent.is_some()) > MAX_VIEWS {
            return Err(Error::Budget.into());
        }
        let query = matches!(op, 5 | 7 | 11);
        build |= query && self.index.is_none();
        let output = add(
            cfg.reply_bytes(query),
            if op == 11 { cfg.paint_bytes()? } else { 0 },
        )?;
        if capacity < output {
            return Err(PrepareError::Capacity(output));
        }
        let scratch = if query { mul(cfg.width, 8)? } else { 0 };
        let paint_scratch = if op == 11 {
            mul(cfg.views.iter().map(View::bins).max().unwrap_or(0), 8)?
        } else {
            0
        };
        let extra = add(
            add(scratch, paint_scratch)?,
            add(
                if build { cfg.index_bytes()? } else { 0 },
                add(
                    new_config.as_ref().map_or(0, Config::bytes),
                    state.as_ref().map_or(0, Linked::bytes),
                )?,
            )?,
        )?;
        peak = peak.max(self.admit(extra, b.len(), output, budget)?);
        let replacement = if build {
            Some(Index::build(source, cfg, st, cancelled)?)
        } else {
            None
        };
        let mut rows = if build { source.rows as u64 } else { 0 };
        let mut fallback = if build { 4 } else { 0 };
        let mut reads = 0;
        let mut result = None;
        if query {
            let index = replacement
                .as_ref()
                .or(self.index.as_ref())
                .ok_or(Error::Missing)?;
            let mut counts = alloc::<u64>(cfg.width)?;
            if let Some(bounds) = intent {
                match index.interval(bounds) {
                    Ok((first, end)) => {
                        for (i, v) in counts.iter_mut().enumerate() {
                            *v = index.prefix[end * cfg.width + i]
                                - index.prefix[first * cfg.width + i];
                        }
                        reads = (cfg.width * 2) as u64;
                    }
                    Err(Error::Boundary) if flags == 1 => {
                        fallback |= 1;
                        for row in 0..source.rows {
                            if row % 4096 == 0 && cancelled() {
                                return Err(Error::Cancelled.into());
                            }
                            rows += 1;
                            let x = source.columns[cfg.active.dimension][row];
                            if !st.matches(source, row)
                                || !x.is_finite()
                                || x < bounds[0]
                                || x > bounds[1]
                            {
                                continue;
                            }
                            counts[0] += 1;
                            for v in &cfg.views {
                                if let Some(cell) = v.cell(source, row) {
                                    counts[v.offset + cell] += 1;
                                }
                            }
                        }
                    }
                    Err(e) => return Err(e.into()),
                }
            } else {
                counts.copy_from_slice(&index.base);
            }
            result = Some(counts);
        }
        let mut buffer = alloc::<u8>(output)?;
        if op == 11 {
            let index = replacement
                .as_ref()
                .or(self.index.as_ref())
                .ok_or(Error::Missing)?;
            let counts = result.as_ref().unwrap();
            let mut at = cfg.reply_bytes(true);
            buffer[at..at + 4].copy_from_slice(b"XYFP");
            buffer[at + 4..at + 8].copy_from_slice(&1u32.to_le_bytes());
            put(&mut buffer, at + 8, cfg.views.len() as u64);
            at += 16;
            let filtered = intent.is_some()
                || !st.clauses.is_empty()
                || !st.base.is_empty()
                || !st.mask.is_empty();
            for v in &cfg.views {
                if cancelled() {
                    return Err(Error::Cancelled.into());
                }
                let g = v.grid.as_ref().unwrap();
                let n = v.bins();
                put(&mut buffer, at, v.id);
                buffer[at + 8..at + 12].copy_from_slice(&(g.width as u32).to_le_bytes());
                buffer[at + 12..at + 16].copy_from_slice(&(g.height as u32).to_le_bytes());
                for (i, x) in g.range.iter().enumerate() {
                    put(&mut buffer, at + 16 + i * 8, x.to_bits());
                }
                at += 56;
                let totals = &index.totals[v.offset..v.offset + n];
                for (i, x) in totals.iter().enumerate() {
                    put(&mut buffer, at + i * 8, *x);
                }
                at += n * 8;
                for (i, x) in totals.iter().enumerate() {
                    buffer[at + i * 4..at + i * 4 + 4].copy_from_slice(&(*x as f32).to_le_bytes());
                }
                at += n * 4;
                let values: Vec<f64> = {
                    let mut x = alloc(n)?;
                    for (i, v) in totals.iter().enumerate() {
                        x[i] = *v as f64;
                    }
                    x
                };
                let maximum = values.iter().copied().fold(0., f64::max);
                let descriptor = at - n * 12 - 56;
                put(&mut buffer, descriptor + 48, maximum.to_bits());
                crate::kernels::density_rgba_linear_into(
                    &values,
                    g.width,
                    g.height,
                    maximum,
                    &[[g.colors[0], g.colors[1], g.colors[2]]],
                    if filtered {
                        1.
                    } else {
                        g.colors[3] as f64 / 255.
                    },
                    &mut buffer[at..at + n * 4],
                );
                if filtered {
                    for (i, total) in totals.iter().enumerate() {
                        let f = if *total == 0 {
                            0.
                        } else {
                            counts[v.offset + i] as f64 / *total as f64
                        };
                        let dest = ((g.height - 1 - i / g.width) * g.width + i % g.width) * 4 + at;
                        for c in 0..3 {
                            buffer[dest + c] = ((g.colors[c] as f64) * (1. - f)
                                + g.colors[4 + c] as f64 * f)
                                .round() as u8;
                        }
                        buffer[dest + 3] = (buffer[dest + 3] as f64
                            * ((1. - f) * 0.18 * g.colors[3] as f64 / 255.
                                + f * g.colors[7] as f64 / 255.))
                            .round() as u8;
                    }
                }
                // The shared image colormap kernel writes top-first. Ordinary
                // WebGL density textures use bottom-first, like exact count bins.
                // Lower that orientation here without a second paint path.
                for row in 0..g.height / 2 {
                    for byte in 0..g.width * 4 {
                        buffer.swap(
                            at + row * g.width * 4 + byte,
                            at + (g.height - 1 - row) * g.width * 4 + byte,
                        );
                    }
                }
                at += n * 4;
            }
        }
        if cancelled() {
            return Err(Error::Cancelled.into());
        }
        // Every fallible allocation, capacity check and scan precedes publication.
        if let Some(cfg) = new_config {
            self.config = Some(cfg);
        }
        if let Some(st) = state {
            self.linked = st;
        }
        if invalidate {
            self.index = None;
        }
        if let Some(index) = replacement {
            self.index = Some(index);
        }
        self.intent = intent;
        self.revision = seq;
        let selected = result.as_ref().map_or(0, |c| c[0]);
        let tier = if query {
            if fallback == 0 {
                3
            } else {
                2
            }
        } else {
            0
        };
        let mut reply = self.reply(
            seq,
            0,
            tier,
            fallback,
            rows,
            reads,
            peak,
            selected,
            result.as_deref(),
            &[],
            0,
            Some(buffer),
        )?;
        if op == 11 {
            reply[12..16].copy_from_slice(&1u32.to_le_bytes());
        }
        put(
            &mut reply,
            184,
            u64::from(self.intent.is_some() || self.linked.has_intent()),
        );
        Ok(reply)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn filter_tier_c_density_complete_shared_packets() {
        let b = include_bytes!("../../../tests/fixtures/filter_tier_c/density.bin");
        let mut s = FilterTierCSession::default();
        let mut at = 0;
        let mut ncases = 0;
        while at < b.len() {
            let n = u32_at(b, at).unwrap() as usize;
            let cap = u32_at(b, at + 4).unwrap() as usize;
            let code = u32_at(b, at + 8).unwrap() as i32;
            let size = u32_at(b, at + 12).unwrap() as usize;
            let needed = u64_at(b, at + 16).unwrap();
            at += 24;
            let input = &b[at..at + n];
            at += n;
            let expected = &b[at..at + size];
            at += size;
            match s.execute(input, cap, || false) {
                Ok(actual) => {
                    assert_eq!(code, 0);
                    assert_eq!(actual, expected, "case {ncases}");
                }
                Err(n) => {
                    assert_eq!(code, -4);
                    assert_eq!(n as u64, needed);
                }
            }
            ncases += 1;
        }
        assert_eq!(ncases, 57);
    }
    #[test]
    fn filter_tier_c_indexed_queries_do_not_read_canonical_or_mask_rows() {
        let b = include_bytes!("../../../tests/fixtures/filter_tier_c/density.bin");
        let mut session = FilterTierCSession::default();
        let mut at = 0;
        loop {
            let n = u32_at(b, at).unwrap() as usize;
            let cap = u32_at(b, at + 4).unwrap() as usize;
            let out = u32_at(b, at + 12).unwrap() as usize;
            at += 24;
            let input = &b[at..at + n];
            at += n + out;
            session.execute(input, cap, || false).unwrap();
            if !session.linked.mask.is_empty() && session.index.is_some() {
                break;
            }
        }
        let mut query = vec![0; HEADER];
        query[..4].copy_from_slice(b"XYFC");
        query[4..8].copy_from_slice(&1u32.to_le_bytes());
        query[8..12].copy_from_slice(&5u32.to_le_bytes());
        for (at, value) in [
            (16, session.newest + 1),
            (24, 112),
            (32, 7),
            (40, 1),
            (48, 1 << 20),
            (80, 0f64.to_bits()),
            (88, 0.5f64.to_bits()),
        ] {
            put(&mut query, at, value);
        }
        let before = session.execute(&query, 1 << 20, || false).unwrap();
        assert_eq!(u64_at(&before, 128), Ok(4));
        // Poison private backing arrays to detect row scans or mask rehashing.
        // The resident index and admitted mask digest remain the warm snapshot.
        for column in &mut session.source.as_mut().unwrap().columns {
            column.fill(f64::NAN);
        }
        session.linked.mask.fill(0);
        put(&mut query, 16, session.newest + 1);
        let after = session.execute(&query, 1 << 20, || false).unwrap();
        assert_eq!(u64_at(&after, 64), Ok(3));
        assert_eq!(u64_at(&after, 96), Ok(0));
        assert_eq!(u64_at(&after, 128), Ok(4));
        assert_eq!(u64_at(&after, 56), u64_at(&before, 56));
    }
    #[test]
    fn filter_tier_c_density_cancel_before_publication() {
        let b = include_bytes!("../../../tests/fixtures/filter_tier_c/density.bin");
        let mut s = FilterTierCSession::default();
        let mut at = 0;
        for _ in 0..2 {
            let n = u32_at(b, at).unwrap() as usize;
            let out = u32_at(b, at + 12).unwrap() as usize;
            at += 24;
            s.execute(&b[at..at + n], 1 << 20, || false).unwrap();
            at += n + out;
        }
        let before = (s.revision, s.fingerprint(), s.retained_bytes());
        let mut q = vec![0; HEADER];
        q[..4].copy_from_slice(b"XYFC");
        q[4..8].copy_from_slice(&1u32.to_le_bytes());
        q[8..12].copy_from_slice(&5u32.to_le_bytes());
        q[12..16].copy_from_slice(&1u32.to_le_bytes());
        for (at, v) in [
            (16, 10),
            (24, 112),
            (32, 7),
            (40, 1),
            (48, 1 << 20),
            (80, 0.1f64.to_bits()),
            (88, 0.6f64.to_bits()),
        ] {
            put(&mut q, at, v);
        }
        let calls = Cell::new(0);
        let result = s
            .execute(&q, 1 << 20, || {
                calls.set(calls.get() + 1);
                calls.get() >= 3
            })
            .unwrap();
        assert_eq!(u32_at(&result, 8), Ok(Error::Cancelled as u32));
        assert_eq!(before, (s.revision, s.fingerprint(), s.retained_bytes()));
    }
}
