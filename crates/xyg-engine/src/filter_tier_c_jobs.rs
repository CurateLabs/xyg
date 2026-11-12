//! Bounded private filter work. Public packets cannot supply completed work or
//! reuse a consumed revision; only an instance-owned continuation can do so.
use super::*;
const WORK: usize = 16_384;
const JOB_BYTES: usize = 2048;

/// One framing authority serves execution and the native concurrent gate.
pub(super) fn admitted_control(b: &[u8]) -> Result<(u32, u64)> {
    if b.len() < 32
        || b.len() > MAX_PACKET + 32
        || b.get(..4) != Some(b"XYFJ")
        || u32_at(b, 4)? != 1
        || u32_at(b, 12)? != 0
        || u64_at(b, 24)? != 0
    {
        return Err(Error::Malformed);
    }
    let op = u32_at(b, 8)?;
    let token = u64_at(b, 16)?;
    let valid = match op {
        1 => token == 0 && b.len() > 32,
        2 | 3 => token != 0 && b.len() == 32,
        _ => false,
    };
    if valid {
        Ok((op, token))
    } else {
        Err(Error::Malformed)
    }
}

#[derive(Debug)]
pub enum CooperativeReply {
    Complete(Vec<u8>),
    Pending {
        token: u64,
        rows: u64,
        total_rows: u64,
    },
}
#[derive(Debug, Default)]
pub(super) struct Completed {
    index: Option<Index>,
    counts: Option<Vec<u64>>,
    membership: Option<(Vec<u8>, u64)>,
}
impl Index {
    fn bytes(&self) -> usize {
        (self.prefix.capacity() + self.totals.capacity() + self.base.capacity()) * 8
            + self.extrema.capacity() * 16
    }
}
impl Completed {
    fn bytes(&self) -> usize {
        self.index.as_ref().map_or(0, Index::bytes)
            + self.counts.as_ref().map_or(0, |v| v.capacity() * 8)
            + self.membership.as_ref().map_or(0, |(v, _)| v.capacity())
    }
}
#[derive(Debug)]
pub(super) enum BuildMode {
    Sync,
    Defer,
    Complete(Completed),
}
impl BuildMode {
    pub(super) fn is_completion(&self) -> bool {
        matches!(self, Self::Complete(_))
    }
}
#[derive(Debug)]
enum Work {
    Build {
        index: Index,
        prefix: usize,
    },
    Counts {
        values: Vec<u64>,
        bounds: [f64; 2],
        linked: bool,
    },
    Membership {
        bits: Vec<u8>,
        first: usize,
        bounds: Option<[f64; 2]>,
        selected: u64,
    },
}
impl Work {
    fn bytes(&self) -> usize {
        match self {
            Self::Build { index, .. } => index.bytes(),
            Self::Counts { values, .. } => values.capacity() * 8,
            Self::Membership { bits, .. } => bits.capacity(),
        }
    }
}
#[derive(Debug)]
struct State {
    source: Arc<Source>,
    config: Option<Config>,
    linked: Option<Linked>,
    work: Work,
    ready: Completed,
    packet: Vec<u8>,
    revision: u64,
    token: u64,
    output: usize,
    row: usize,
    start: usize,
    end: usize,
    peak: usize,
}
const _: () =
    assert!(std::mem::size_of::<State>() + std::mem::size_of::<PendingWork>() <= JOB_BYTES);
/// A checked singleton allocation avoids infallible boxed-control allocation.
#[derive(Debug)]
pub(super) struct PendingWork(Box<[State]>);
impl PendingWork {
    pub(super) fn bytes(&self) -> usize {
        let p = &self.0[0];
        JOB_BYTES
            + p.config.as_ref().map_or(0, Config::bytes)
            + p.linked.as_ref().map_or(0, Linked::bytes)
            + p.packet.capacity()
            + p.work.bytes()
            + p.ready.bytes()
    }
    fn progress(&self) -> CooperativeReply {
        let p = &self.0[0];
        CooperativeReply::Pending {
            token: p.token,
            rows: (p.row - p.start) as u64,
            total_rows: (p.end - p.start) as u64,
        }
    }
}
// One row/cumulative dispatcher serves both synchronous WASM and yielded jobs.
// This keeps exact row kernels shared instead of outlining a second full scan
// for each mode. Cancellation is checked between bounded units and in visit.
fn step_work(
    source: &Source,
    config: Option<&Config>,
    linked: &Linked,
    work: &mut Work,
    row: &mut usize,
    end: usize,
    cancelled: &dyn Fn() -> bool,
) -> Result<bool> {
    if cancelled() {
        return Err(Error::Cancelled);
    }
    let quota = (WORK / (1 + config.map_or(0, |c| c.views.len()) + linked.work_per_row())).max(1);
    let next = row.saturating_add(quota).min(end);
    let done = match work {
        Work::Build { index, prefix } => {
            let cfg = config.ok_or(Error::Missing)?;
            source.visit(*row, next, cancelled, &mut BuildRows { index, cfg, linked })?;
            if next == end {
                *prefix = index.prefix_step(cfg, *prefix, WORK);
            }
            next == end && *prefix == index.prefix.len()
        }
        Work::Counts {
            values,
            bounds,
            linked: use_linked,
        } => {
            source.visit(
                *row,
                next,
                cancelled,
                &mut CountRows {
                    cfg: config.ok_or(Error::Missing)?,
                    linked: if *use_linked { Some(linked) } else { None },
                    bounds: *bounds,
                    counts: values,
                    visited: &mut 0,
                },
            )?;
            next == end
        }
        Work::Membership {
            bits,
            first,
            bounds,
            selected,
        } => {
            source.visit(
                *row,
                next,
                cancelled,
                &mut MembershipRows {
                    cfg: config,
                    linked,
                    bounds: *bounds,
                    first: *first,
                    bits,
                    selected,
                },
            )?;
            next == end
        }
    };
    *row = next;
    if cancelled() {
        Err(Error::Cancelled)
    } else {
        Ok(done)
    }
}
#[cfg(target_family = "wasm")]
fn finish_work(
    source: &Source,
    config: Option<&Config>,
    linked: &Linked,
    mut work: Work,
    start: usize,
    end: usize,
    cancelled: &dyn Fn() -> bool,
) -> Result<Work> {
    let mut row = start;
    while !step_work(source, config, linked, &mut work, &mut row, end, cancelled)? {}
    Ok(work)
}
impl FilterTierCSession {
    /// C ABI adapters, including Emscripten, keep the raw compatibility path
    /// and share the Worker
    /// continuation protocol. The wrapper's live32 bytes are additional to
    /// the inner request or retained private packet admitted by the engine.
    pub fn execute_transport(
        &mut self,
        b: &[u8],
        capacity: usize,
        superseded: impl Fn() -> bool,
    ) -> std::result::Result<Vec<u8>, usize> {
        if b.get(..4) == Some(b"XYFJ") {
            self.execute_cooperative_with_external(b, capacity, 32, superseded)
        } else {
            self.execute(b, capacity, superseded)
        }
    }

    pub fn execute_cooperative_with_external(
        &mut self,
        b: &[u8],
        capacity: usize,
        external: usize,
        superseded: impl Fn() -> bool,
    ) -> std::result::Result<Vec<u8>, usize> {
        self.external_bytes = external;
        let result = self.execute_cooperative_packet(b, capacity, superseded);
        self.external_bytes = 0;
        result
    }
    /// XYFJ v1 frames private Worker continuations through the existing filter
    /// export. Header32: magic/version/op/reserved/token/reserved; begin carries
    /// an unchanged XYFC packet, advance/cancel carry no payload. Replies are
    /// either unchanged XYFR or32-byte XYFJ progress(token/rows/end).
    pub fn execute_cooperative_packet(
        &mut self,
        b: &[u8],
        capacity: usize,
        superseded: impl Fn() -> bool,
    ) -> std::result::Result<Vec<u8>, usize> {
        let (op, token) = match admitted_control(b) {
            Ok(header) => header,
            Err(error) => {
                return self.error_reply(u64_at(b, 16).unwrap_or(0), error, capacity);
            }
        };
        let result = match op {
            1 => self.begin_cooperative(&b[32..], capacity, superseded),
            2 => self.advance_cooperative(token, capacity, superseded),
            3 => {
                let needed = self
                    .config
                    .as_ref()
                    .map_or(REPLY_HEADER, |c| c.reply_bytes(false));
                if capacity < needed {
                    return Err(needed);
                }
                if self.pending.as_ref().is_some_and(|p| p.0[0].token == token) {
                    self.pending = None;
                    self.error_reply(token, Error::Cancelled, capacity)
                        .map(CooperativeReply::Complete)
                } else {
                    self.error_reply(token, Error::Stale, capacity)
                        .map(CooperativeReply::Complete)
                }
            }
            _ => return self.error_reply(token, Error::Malformed, capacity),
        }?;
        match result {
            CooperativeReply::Complete(b) => Ok(b),
            CooperativeReply::Pending {
                token,
                rows,
                total_rows,
            } => {
                let mut out = alloc::<u8>(32).map_err(|_| 32usize)?;
                out[..4].copy_from_slice(b"XYFJ");
                out[4..8].copy_from_slice(&1u32.to_le_bytes());
                put(&mut out, 8, token);
                put(&mut out, 16, rows);
                put(&mut out, 24, total_rows);
                Ok(out)
            }
        }
    }
    pub(super) fn cancel_pending_for(&mut self, b: &[u8]) {
        if admitted_header(b).is_ok_and(|(_, _, seq)| seq > self.newest && seq > self.cancelled) {
            self.pending = None;
        }
    }
    /// Accepted source/configuration/index/intent survive until publication.
    pub fn begin_cooperative(
        &mut self,
        b: &[u8],
        capacity: usize,
        superseded: impl Fn() -> bool,
    ) -> std::result::Result<CooperativeReply, usize> {
        self.cancel_pending_for(b);
        self.peak_observed
            .set(self.retained_bytes().saturating_add(self.external_bytes));
        let result = self.prepare(b, capacity, &superseded, &mut BuildMode::Defer);
        self.cooperative_result(u64_at(b, 16).unwrap_or(0), capacity, result)
    }
    fn cooperative_result(
        &mut self,
        token: u64,
        capacity: usize,
        result: std::result::Result<Vec<u8>, PrepareError>,
    ) -> std::result::Result<CooperativeReply, usize> {
        match result {
            Ok(b) => Ok(CooperativeReply::Complete(b)),
            Err(PrepareError::Capacity(n)) => Err(n),
            Err(PrepareError::Policy(e)) => self
                .error_reply(token, e, capacity)
                .map(CooperativeReply::Complete),
            Err(PrepareError::Deferred(p)) => {
                let reply = p.progress();
                self.pending = Some(p);
                Ok(reply)
            }
        }
    }
    /// Wrong tokens/short capacities retain the candidate. Cancellation drops it
    /// before returning. A continuation performs a fixed Rust work quota.
    pub fn advance_cooperative(
        &mut self,
        token: u64,
        capacity: usize,
        superseded: impl Fn() -> bool,
    ) -> std::result::Result<CooperativeReply, usize> {
        let Some(p) = self.pending.as_ref().map(|p| &p.0[0]) else {
            return self
                .error_reply(token, Error::Missing, capacity)
                .map(CooperativeReply::Complete);
        };
        if token != p.token {
            return self
                .error_reply(token, Error::Stale, capacity)
                .map(CooperativeReply::Complete);
        }
        if capacity < p.output {
            return Err(p.output);
        }
        // Other malformed/stale requests have their own diagnostics. Restore
        // this transaction's high-water mark before admitting its next turn.
        self.peak_observed.set(p.peak);
        // The adapter may stage a continuation inside a larger arena. Charge
        // its actual slack on every turn, not only when the job was captured.
        let extra = p.source.workspace(p.end - p.row);
        let admitted = extra.and_then(|extra| self.admit(extra, 0, p.output, self.budget));
        if let Err(error) = admitted {
            self.pending = None;
            return self
                .error_reply(token, error, capacity)
                .map(CooperativeReply::Complete);
        }
        let mut pending = self.pending.take().unwrap();
        let p = &mut pending.0[0];
        let current = p.token == self.newest
            && p.token > self.cancelled
            && p.revision == self.revision
            && self
                .source
                .as_ref()
                .is_some_and(|s| Arc::ptr_eq(s, &p.source));
        let result = if !current || superseded() {
            Err(Error::Cancelled)
        } else {
            step_work(
                &p.source,
                p.config.as_ref().or(self.config.as_ref()),
                p.linked.as_ref().unwrap_or(&self.linked),
                &mut p.work,
                &mut p.row,
                p.end,
                &superseded,
            )
        };
        match result {
            Err(e) => {
                drop(pending);
                self.error_reply(token, e, capacity)
                    .map(CooperativeReply::Complete)
            }
            Ok(false) => {
                pending.0[0].peak = self.peak_observed.get();
                let reply = pending.progress();
                self.pending = Some(pending);
                Ok(reply)
            }
            Ok(true) => {
                let State {
                    packet,
                    work,
                    mut ready,
                    ..
                } = pending.0.into_vec().pop().unwrap();
                match work {
                    Work::Build { index, .. } => ready.index = Some(index),
                    Work::Counts { values, .. } => ready.counts = Some(values),
                    Work::Membership { bits, selected, .. } => {
                        ready.membership = Some((bits, selected))
                    }
                }
                // Drop captured private proposals before reparse; preserve private
                // completed work across multiple phases of the same transaction.
                let result = self.prepare(
                    &packet,
                    capacity,
                    &superseded,
                    &mut BuildMode::Complete(ready),
                );
                self.cooperative_result(token, capacity, result)
            }
        }
    }
    /// Move only private replacements into a suspended transaction. Unchanged
    /// configuration/predicates remain in the accepted owner and are borrowed
    /// only after continuation revision/source guards. No capture-only clones.
    pub(super) fn finish_capture(
        &self,
        result: std::result::Result<Vec<u8>, PrepareError>,
        config: Option<Config>,
        linked: Option<Linked>,
        packet: &[u8],
        cancelled: &impl Fn() -> bool,
    ) -> std::result::Result<Vec<u8>, PrepareError> {
        match result {
            Err(PrepareError::Deferred(mut pending)) => {
                let p = &mut pending.0[0];
                p.config = config;
                p.linked = linked;
                // Re-admit actual capacities after ownership transfer, before
                // the job becomes visible even as private continuation state.
                self.admit(
                    add(
                        pending.bytes(),
                        pending.0[0]
                            .source
                            .workspace(pending.0[0].end - pending.0[0].start)?,
                    )?,
                    packet.len(),
                    pending.0[0].output,
                    self.budget,
                )?;
                pending.0[0].peak = self.peak_observed.get();
                if cancelled() {
                    return Err(Error::Cancelled.into());
                }
                Err(PrepareError::Deferred(pending))
            }
            other => other,
        }
    }
    fn capture_work(
        &self,
        packet: &[u8],
        output: usize,
        extra: usize,
        work: Work,
        ready: Completed,
        start: usize,
        end: usize,
        cancelled: &impl Fn() -> bool,
    ) -> Result<PendingWork> {
        let source = self.source.as_ref().ok_or(Error::Missing)?;
        // Candidate work and proposals fit the caller's admission. Admit the
        // control slot and saved packet before allocating either. The prepare
        // boundary transfers proposals and rechecks their actual capacities.
        let capture = add(JOB_BYTES, packet.len())?;
        self.admit(add(extra, capture)?, packet.len(), output, self.budget)?;
        let mut slot = Vec::new();
        slot.try_reserve_exact(1).map_err(|_| Error::Allocation)?;
        let mut saved = alloc(packet.len())?;
        saved.copy_from_slice(packet);
        slot.push(State {
            source: Arc::clone(source),
            config: None,
            linked: None,
            work,
            ready,
            packet: saved,
            revision: self.revision,
            token: u64_at(packet, 16)?,
            output,
            row: start,
            start,
            end,
            peak: 0,
        });
        let pending = PendingWork(slot.into_boxed_slice());
        if cancelled() {
            return Err(Error::Cancelled);
        }
        Ok(pending)
    }
    pub(super) fn build_index(
        &self,
        mode: &mut BuildMode,
        packet: &[u8],
        capacity: usize,
        output: usize,
        config: &Config,
        linked: &Linked,
        extra: usize,
        cancelled: &impl Fn() -> bool,
    ) -> std::result::Result<Index, PrepareError> {
        let source = self.source.as_ref().ok_or(Error::Missing)?;
        if let BuildMode::Complete(ready) = mode {
            return ready.index.take().ok_or(Error::Missing.into());
        }
        #[cfg(not(target_family = "wasm"))]
        if matches!(mode, BuildMode::Sync) {
            return Index::build(source, config, linked, cancelled).map_err(Into::into);
        }
        if matches!(mode, BuildMode::Defer) && capacity < output {
            return Err(PrepareError::Capacity(output));
        }
        // One construction path: the same candidate allocation is either run
        // synchronously or captured. Do not inline two complete vector builders.
        let work = Work::Build {
            index: Index::empty(config)?,
            prefix: config.width,
        };
        #[cfg(target_family = "wasm")]
        if matches!(mode, BuildMode::Sync) {
            return match finish_work(
                source,
                Some(config),
                linked,
                work,
                0,
                source.rows,
                cancelled,
            )? {
                Work::Build { index, .. } => Ok(index),
                _ => unreachable!(),
            };
        }
        Err(PrepareError::Deferred(self.capture_work(
            packet,
            output,
            extra,
            work,
            Completed::default(),
            0,
            source.rows,
            cancelled,
        )?))
    }

    pub(super) fn scan_counts(
        &self,
        mode: &mut BuildMode,
        packet: &[u8],
        output: usize,
        config: &Config,
        linked: Option<&Linked>,
        bounds: [f64; 2],
        built: &mut Option<Index>,
        extra: usize,
        cancelled: &impl Fn() -> bool,
    ) -> std::result::Result<Vec<u64>, PrepareError> {
        if let BuildMode::Complete(ready) = mode {
            if let Some(values) = ready.counts.take() {
                return Ok(values);
            }
        }
        let source = self.source.as_ref().ok_or(Error::Missing)?;
        let values = alloc(config.width)?;
        if matches!(mode, BuildMode::Sync) {
            #[cfg(not(target_family = "wasm"))]
            {
                let mut values = values;
                source.visit(
                    0,
                    source.rows,
                    cancelled,
                    &mut CountRows {
                        cfg: config,
                        linked,
                        bounds,
                        counts: &mut values,
                        visited: &mut 0,
                    },
                )?;
                return Ok(values);
            }
            #[cfg(target_family = "wasm")]
            {
                match finish_work(
                    source,
                    Some(config),
                    linked.unwrap_or(&self.linked),
                    Work::Counts {
                        values,
                        bounds,
                        linked: linked.is_some(),
                    },
                    0,
                    source.rows,
                    cancelled,
                )? {
                    Work::Counts { values, .. } => return Ok(values),
                    _ => unreachable!(),
                }
            }
        }

        let ready = Completed {
            index: built.take(),
            ..Completed::default()
        };
        Err(PrepareError::Deferred(self.capture_work(
            packet,
            output,
            extra,
            Work::Counts {
                values,
                bounds,
                linked: linked.is_some(),
            },
            ready,
            0,
            source.rows,
            cancelled,
        )?))
    }
    pub(super) fn scan_membership(
        &self,
        mode: &mut BuildMode,
        packet: &[u8],
        output: usize,
        start: usize,
        n: usize,
        extra: usize,
        cancelled: &impl Fn() -> bool,
    ) -> std::result::Result<(Vec<u8>, u64), PrepareError> {
        if let BuildMode::Complete(ready) = mode {
            if let Some(done) = ready.membership.take() {
                return Ok(done);
            }
        }
        let source = self.source.as_ref().ok_or(Error::Missing)?;
        let bits = alloc(n.div_ceil(8))?;
        if matches!(mode, BuildMode::Sync) {
            #[cfg(not(target_family = "wasm"))]
            {
                let mut bits = bits;
                let mut selected = 0;
                source.visit(
                    start,
                    start + n,
                    cancelled,
                    &mut MembershipRows {
                        cfg: self.config.as_ref(),
                        linked: &self.linked,
                        bounds: self.intent,
                        first: start,
                        bits: &mut bits,
                        selected: &mut selected,
                    },
                )?;
                return Ok((bits, selected));
            }
            #[cfg(target_family = "wasm")]
            {
                match finish_work(
                    source,
                    self.config.as_ref(),
                    &self.linked,
                    Work::Membership {
                        bits,
                        first: start,
                        bounds: self.intent,
                        selected: 0,
                    },
                    start,
                    start + n,
                    cancelled,
                )? {
                    Work::Membership { bits, selected, .. } => return Ok((bits, selected)),
                    _ => unreachable!(),
                }
            }
        }

        Err(PrepareError::Deferred(self.capture_work(
            packet,
            output,
            extra,
            Work::Membership {
                bits,
                first: start,
                bounds: self.intent,
                selected: 0,
            },
            Completed::default(),
            start,
            start + n,
            cancelled,
        )?))
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    const CAP: usize = 1 << 20;
    const BUDGET: u64 = 32 << 20;
    fn request(op: u32, seq: u64, args: [u64; 3], payload: &[u8]) -> Vec<u8> {
        let mut b = vec![0; HEADER];
        b[..4].copy_from_slice(b"XYFC");
        b[4..8].copy_from_slice(&1u32.to_le_bytes());
        b[8..12].copy_from_slice(&op.to_le_bytes());
        for (i, value) in [seq, 1, 2, 1, BUDGET, args[0], args[1], args[2]]
            .iter()
            .enumerate()
        {
            put(&mut b, 16 + 8 * i, *value);
        }
        b.extend_from_slice(payload);
        b
    }
    fn source() -> FilterTierCSession {
        let mut s = FilterTierCSession::default();
        let mut columns = Vec::new();
        for d in 0..2 {
            for i in 0..50_003 {
                columns.extend_from_slice(&((i % 37) as f64 - d as f64 * 5.).to_le_bytes());
            }
        }
        let reply = s
            .execute(&request(1, 1, [2, 50_003, 99], &columns), CAP, || false)
            .unwrap();
        assert_eq!(u32_at(&reply, 8), Ok(0));
        s
    }
    fn config(seq: u64, linked: bool) -> Vec<u8> {
        let mut b = Vec::new();
        for x in [2, 0f64.to_bits(), 18f64.to_bits()] {
            b.extend_from_slice(&x.to_le_bytes());
        }
        for id in 1..=2u64 {
            for x in [id, id - 1] {
                b.extend_from_slice(&x.to_le_bytes());
            }
            if linked {
                b.extend_from_slice(&0u64.to_le_bytes());
                b.extend_from_slice(&4u32.to_le_bytes());
                b.extend_from_slice(&4u32.to_le_bytes());
                for x in [-6f64, 38., -6., 38.] {
                    b.extend_from_slice(&x.to_le_bytes());
                }
                b.extend_from_slice(&[0; 16]);
            } else {
                for x in [1, 10f64.to_bits()] {
                    b.extend_from_slice(&x.to_le_bytes());
                }
            }
        }
        request(if linked { 10 } else { 3 }, seq, [1, 0, 2], &b)
    }
    fn complete(s: &mut FilterTierCSession, mut r: CooperativeReply) -> (Vec<u8>, usize) {
        let mut turns = 0;
        loop {
            match r {
                CooperativeReply::Complete(b) => return (b, turns),
                CooperativeReply::Pending {
                    token,
                    rows,
                    total_rows,
                } => {
                    assert!(rows <= total_rows);
                    assert_eq!(s.revision, 1);
                    assert!(Arc::strong_count(s.source.as_ref().unwrap()) >= 2);
                    r = s.advance_cooperative(token, CAP, || false).unwrap();
                    turns += 1;
                }
            }
        }
    }
    #[test]
    fn filter_tier_c_cooperative_matches_both_sync_builds_with_bounded_turns() {
        for linked in [false, true] {
            let mut sync = source();
            let mut coop = source();
            let b = config(2, linked);
            let mut expected = sync.execute(&b, CAP, || false).unwrap();
            let begin = coop.begin_cooperative(&b, CAP, || false).unwrap();
            assert_eq!(coop.revision, 1);
            assert!(coop.config.is_none());
            assert!(coop.index.is_none());
            let (mut actual, turns) = complete(&mut coop, begin);
            assert!(turns > 8);
            // Cooperative captures/scratch have a separately observable peak.
            expected[88..96].fill(0);
            actual[88..96].fill(0);
            assert_eq!(actual, expected);
            assert!(coop.pending.is_none());
            assert_eq!(Arc::strong_count(coop.source.as_ref().unwrap()), 1);
            let mut query = request(5, 3, [0; 3], &[]);
            put(&mut query, 80, 0f64.to_bits());
            put(&mut query, 88, 17f64.to_bits());
            assert_eq!(
                coop.execute(&query, CAP, || false),
                sync.execute(&query, CAP, || false)
            );
        }
    }
    fn finish(s: &mut FilterTierCSession, mut r: CooperativeReply) -> (Vec<u8>, usize) {
        let mut turns = 0;
        loop {
            match r {
                CooperativeReply::Complete(b) => return (b, turns),
                CooperativeReply::Pending { token, .. } => {
                    r = s.advance_cooperative(token, CAP, || false).unwrap();
                    turns += 1;
                    assert!(turns < 1000);
                }
            }
        }
    }
    fn semantic(mut a: Vec<u8>, mut b: Vec<u8>) {
        a[88..96].fill(0);
        b[88..96].fill(0);
        assert_eq!(a, b);
    }
    #[test]
    fn filter_tier_c_cooperative_exact_scans_and_membership_match_complete_sync_replies() {
        for linked in [false, true] {
            let mut a = source();
            let mut b = source();
            let config = config(2, linked);
            a.execute(&config, CAP, || false).unwrap();
            b.execute(&config, CAP, || false).unwrap();
            // Partial cut bins require explicit exact fallback; these scans now
            // yield while accepted intent/hash and index stay unchanged.
            let mut q = request(5, 3, [0; 3], &[]);
            q[12..16].copy_from_slice(&1u32.to_le_bytes());
            put(&mut q, 80, 4f64.to_bits());
            put(&mut q, 88, 12f64.to_bits());
            let expected = a.execute(&q, CAP, || false).unwrap();
            let old = b.fingerprint();
            let r = b.begin_cooperative(&q, CAP, || false).unwrap();
            assert!(matches!(r, CooperativeReply::Pending { .. }));
            assert_eq!(b.fingerprint(), old);
            assert_eq!(b.revision, 2);
            let (actual, turns) = finish(&mut b, r);
            assert!(turns > 8);
            semantic(actual, expected);
            let q = request(9, 4, [99 + 1000, 40_001, 0], &[]);
            let expected = a.execute(&q, CAP, || false).unwrap();
            let r = b.begin_cooperative(&q, CAP, || false).unwrap();
            let (actual, turns) = finish(&mut b, r);
            assert!(turns > 5);
            semantic(actual, expected);
            assert!(b.pending.is_none());
            assert_eq!(Arc::strong_count(b.source.as_ref().unwrap()), 1);
        }
    }
    #[test]
    fn filter_tier_c_cooperative_build_then_scan_is_one_atomic_transaction() {
        let mut a = source();
        let mut b = source();
        let c = config(2, true);
        a.execute(&c, CAP, || false).unwrap();
        b.execute(&c, CAP, || false).unwrap();
        let mut q = request(5, 3, [0; 3], &[]);
        q[12..16].copy_from_slice(&1u32.to_le_bytes());
        put(&mut q, 80, 4f64.to_bits());
        put(&mut q, 88, 12f64.to_bits());
        a.execute(&q, CAP, || false).unwrap();
        b.execute(&q, CAP, || false).unwrap();
        let e = request(6, 4, [0; 3], &[]);
        a.execute(&e, CAP, || false).unwrap();
        b.execute(&e, CAP, || false).unwrap();
        let mut paint = request(11, 5, [0; 3], &[]);
        paint[12..16].copy_from_slice(&1u32.to_le_bytes());
        let expected = a.execute(&paint, CAP, || false).unwrap();
        let old = b.fingerprint();
        let mut r = b.begin_cooperative(&paint, CAP, || false).unwrap();
        let mut scans = 0;
        loop {
            match r {
                CooperativeReply::Complete(actual) => {
                    semantic(actual, expected);
                    break;
                }
                CooperativeReply::Pending { token, .. } => {
                    assert_eq!(b.revision, 4);
                    assert_eq!(b.fingerprint(), old);
                    assert!(b.index.is_none());
                    if matches!(b.pending.as_ref().unwrap().0[0].work, Work::Counts { .. }) {
                        scans += 1;
                    }
                    r = b.advance_cooperative(token, CAP, || false).unwrap();
                }
            }
        }
        assert!(scans > 8);
        assert!(b.index.is_some());
        assert_eq!(b.revision, 5);
        // A separate aborted second phase releases both the built index and scan
        // storage, without publishing either or changing the accepted predicate.
        b.execute(&request(6, 6, [0; 3], &[]), CAP, || false)
            .unwrap();
        put(&mut paint, 16, 7);
        b.begin_cooperative(&paint, CAP, || false).unwrap();
        loop {
            if matches!(b.pending.as_ref().unwrap().0[0].work, Work::Counts { .. }) {
                break;
            }
            b.advance_cooperative(7, CAP, || false).unwrap();
        }
        let r = b.advance_cooperative(7, CAP, || true).unwrap();
        assert!(
            matches!(r,CooperativeReply::Complete(ref b) if u32_at(b,8)==Ok(Error::Cancelled as u32))
        );
        assert_eq!(b.revision, 6);
        assert!(b.pending.is_none());
        assert!(b.index.is_none());
        assert_eq!(b.fingerprint(), old);
    }

    #[test]
    fn filter_tier_c_cooperative_keeps_capture_peak_across_other_refusals() {
        let mut s = source();
        let mut b = config(2, true);
        // Make the real candidate dominate the conservative parser envelope.
        for at in [144, 224] {
            b[at..at + 4].copy_from_slice(&32u32.to_le_bytes());
            b[at + 4..at + 8].copy_from_slice(&32u32.to_le_bytes());
        }
        let pending = s.begin_cooperative(&b, CAP, || false).unwrap();
        let capture_peak = s.peak_observed.get();
        let mut malformed = request(4, 99, [0; 3], &[]);
        malformed[4..8].copy_from_slice(&99u32.to_le_bytes());
        let refused = s.execute(&malformed, CAP, || false).unwrap();
        assert_eq!(u32_at(&refused, 8), Ok(Error::Malformed as u32));
        assert_eq!(s.newest, 2);
        assert!(s.pending.is_some());
        let (reply, _) = complete(&mut s, pending);
        assert!(
            u64_at(&reply, 88).unwrap() >= capture_peak as u64,
            "interleaved refusal erased the private transaction's admitted peak"
        );
    }
    #[test]
    fn filter_tier_c_cooperative_capacity_tokens_and_malformed_headers_preserve_candidate() {
        let mut s = source();
        let b = config(2, true);
        assert!(matches!(
            s.begin_cooperative(&b, CAP, || false),
            Ok(CooperativeReply::Pending { .. })
        ));
        let before = s.retained_bytes();
        assert!(s.advance_cooperative(2, 0, || false).is_err());
        assert_eq!(s.pending.as_ref().unwrap().0[0].row, 0);
        assert_eq!(s.retained_bytes(), before);
        let wrong = s.advance_cooperative(3, CAP, || false).unwrap();
        assert!(
            matches!(wrong,CooperativeReply::Complete(ref b) if u32_at(b,8)==Ok(Error::Stale as u32))
        );
        let mut bad = request(4, 99, [0; 3], &[]);
        bad[4..8].copy_from_slice(&99u32.to_le_bytes());
        s.execute(&bad, CAP, || false).unwrap();
        assert_eq!(s.newest, 2);
        assert!(s.pending.is_some());
        let r = s.advance_cooperative(2, CAP, || false).unwrap();
        complete(&mut s, r);
        assert_eq!(s.revision, 2);
        let stale = s.execute(&b, CAP, || false).unwrap();
        assert_eq!(u32_at(&stale, 8), Ok(Error::Stale as u32));
    }
    #[test]
    fn filter_tier_c_cooperative_cancellation_and_newer_refusal_release_private_owners() {
        for interrupt in [false, true] {
            let mut s = source();
            let prior = s.retained_bytes();
            let source = Arc::downgrade(s.source.as_ref().unwrap());
            s.begin_cooperative(&config(2, true), CAP, || false)
                .unwrap();
            s.advance_cooperative(2, CAP, || false).unwrap();
            if interrupt {
                // Valid newer header with invalid body consumes sequence and
                // retires old work, while accepted source/config remain intact.
                let mut b = request(10, 3, [1, 0, 2], &[]);
                b.push(0);
                let r = s.execute(&b, CAP, || false).unwrap();
                assert_eq!(u32_at(&r, 8), Ok(Error::Malformed as u32));
            } else {
                let r = s.advance_cooperative(2, CAP, || true).unwrap();
                assert!(
                    matches!(r,CooperativeReply::Complete(ref b) if u32_at(b,8)==Ok(Error::Cancelled as u32))
                );
            }
            assert_eq!(s.revision, 1);
            assert!(s.config.is_none());
            assert!(s.index.is_none());
            assert!(s.pending.is_none());
            assert_eq!(s.retained_bytes(), prior);
            assert_eq!(Arc::strong_count(s.source.as_ref().unwrap()), 1);
            drop(s);
            assert!(source.upgrade().is_none());
        }
    }
}
