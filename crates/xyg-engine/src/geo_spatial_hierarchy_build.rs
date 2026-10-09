//! Canonical source → bounded external sort → paged two-level directory.
use crate::geo_source::{
    FeatureRef, GeoChunk, GeoSourceManifest, QueryBudget, SourceError, parse_authenticated,
};
use crate::geo_source_session::GeoProcessorLease;
use crate::geo_spatial_hierarchy::*;
use crate::geo_spatial_index::{self as flat, Vertex};
use crate::transition::Blake2s8;
use std::sync::Arc;
const SORT_RECORDS: usize = 262_144;
const MAX_RUNS: usize = 8192;
#[derive(Clone, Copy)]
struct Run {
    start: u64,
    pages: u64,
    records: u64,
    digest: [u8; 8],
}
struct Accum {
    start: u64,
    pages: u64,
    records: u64,
    hash: Blake2s8,
}
struct Head {
    run: Run,
    next: u64,
    records: u64,
    hash: Blake2s8,
    buffer: Vec<Record>,
    at: usize,
    last: Option<(u32, u64, u32)>,
}
impl Head {
    fn new(run: Run) -> Self {
        Self {
            run,
            next: 0,
            records: 0,
            hash: run_hash(),
            buffer: Vec::new(),
            at: 0,
            last: None,
        }
    }
}
#[derive(Clone, Copy, PartialEq)]
enum Phase {
    Source,
    Merge,
    Final,
    Ready,
}
#[derive(Clone, Copy)]
enum Target {
    Leaf,
    Outer,
}
enum WriteAction {
    Temp,
    Node(Target, usize, Node),
}
enum ReadAction {
    Source,
    Head(usize),
    Final,
}
struct PendingRead {
    ticket: GeoHierarchyTicket,
    action: ReadAction,
    accepted: bool,
}
struct PendingWrite {
    bytes: Vec<u8>,
    ticket: GeoHierarchyTicket,
    action: WriteAction,
}
pub struct GeoHierarchyBuildSession {
    source: Option<GeoSourceManifest>,
    options: GeoHierarchyOptions,
    budget: QueryBudget,
    vertex_limit: u64,
    owner: u64,
    serial: u64,
    next_id: u64,
    phase: Phase,
    chunk: usize,
    current: Option<GeoChunk>,
    current_credit: Option<Arc<GeoProcessorLease>>,
    row: usize,
    vertex: usize,
    point_vertex: usize,
    sort: Vec<Record>,
    flush: Option<usize>,
    runs: Vec<Run>,
    next_runs: Vec<Run>,
    accum: Option<Accum>,
    group: usize,
    heads: Vec<Head>,
    output: Vec<Record>,
    final_head: Option<Head>,
    active_cell: Option<u32>,
    leaf: Vec<Vertex>,
    leaf_levels: Vec<Vec<Node>>,
    outer_levels: Vec<Vec<Node>>,
    node_ready: Option<(Target, usize, Node)>,
    pending_read: Option<PendingRead>,
    pending_write: Option<PendingWrite>,
    vertices: u64,
    read_bytes: u64,
    write_bytes: u64,
    max_write_bytes: u64,
    cancelled: bool,
    failed: bool,
    expected: Option<[u8; 8]>,
    published: Option<Arc<ValidatedGeoHierarchy>>,
    credit: Option<GeoProcessorLease>,
    base_bytes: usize,
}
fn temp_bytes(id: u64, r: &[Record]) -> Vec<u8> {
    let mut b = vec![0; PAGE_BYTES];
    b[..4].copy_from_slice(b"XYHR");
    put32(&mut b, 4, 1);
    put64(&mut b, 8, id);
    put32(&mut b, 16, r.len() as u32);
    for (i, &r) in r.iter().enumerate() {
        let a = 64 + i * 96;
        put32(&mut b, a, r.cell);
        flat::write_vertex(&mut b, a + 16, r.value);
    }
    b
}
fn temp_records(b: &[u8], id: u64, options: GeoHierarchyOptions, rows: u64) -> Result<Vec<Record>> {
    if b.len() != PAGE_BYTES
        || &b[..4] != b"XYHR"
        || get32(b, 4) != 1
        || get64(b, 8) != id
        || b[20..64].iter().any(|v| *v != 0)
    {
        return invalid();
    }
    let count = get32(b, 16) as usize;
    if count == 0 || count > RUN_RECORDS || b[64 + count * 96..].iter().any(|v| *v != 0) {
        return invalid();
    }
    let mut out = Vec::with_capacity(count);
    for r in b[64..64 + count * 96].chunks_exact(96) {
        let cell = get32(r, 0);
        let value = decode_vertex(&r[16..])?;
        if (cell >= options.grid * options.grid && cell != u32::MAX)
            || r[4..16].iter().any(|v| *v != 0)
            || value.identity.source_row >= rows
        {
            return invalid();
        }
        out.push(Record { cell, value });
    }
    if out
        .windows(2)
        .any(|p| p[0].key(options.grid) >= p[1].key(options.grid))
    {
        return invalid();
    }
    Ok(out)
}
impl GeoHierarchyBuildSession {
    pub fn new(
        source: &GeoSourceManifest,
        options: GeoHierarchyOptions,
        budget: QueryBudget,
        max_vertices: u64,
        max_write_bytes: u64,
    ) -> Result<Self> {
        Self::create(source, options, budget, max_vertices, max_write_bytes, None)
    }
    /// Import verification rebuilds all canonical records; a checksum alone is not authority.
    pub fn verify(
        source: &GeoSourceManifest,
        options: GeoHierarchyOptions,
        budget: QueryBudget,
        max_vertices: u64,
        max_write_bytes: u64,
        expected: [u8; 8],
    ) -> Result<Self> {
        Self::create(
            source,
            options,
            budget,
            max_vertices,
            max_write_bytes,
            Some(expected),
        )
    }
    fn create(
        source: &GeoSourceManifest,
        options: GeoHierarchyOptions,
        budget: QueryBudget,
        max_vertices: u64,
        max_write_bytes: u64,
        expected: Option<[u8; 8]>,
    ) -> Result<Self> {
        flat::supported(source)?;
        options.validate()?;
        budget.validate()?;
        if max_write_bytes == 0
            || max_vertices == 0
            || max_vertices > 2_000_000_000
            || source.rows() > budget.max_rows_examined
            || source.chunks().len() > budget.max_chunks
        {
            return limit();
        }
        let base = source
            .clone_reserved_bytes()
            .checked_add(SORT_RECORDS * 128 + MAX_RUNS * 64 * 2 + 4 * 1024 * 1024)
            .ok_or(SourceError::ResourceLimit)?;
        if base > budget.processor_bytes {
            return limit();
        }
        let credit = GeoProcessorLease::acquire(base)?;
        Ok(Self {
            source: Some(source.clone_validated()),
            options,
            budget,
            vertex_limit: max_vertices,
            owner: nonce()?,
            serial: 0,
            next_id: 1,
            phase: Phase::Source,
            chunk: 0,
            current: None,
            current_credit: None,
            row: 0,
            vertex: 0,
            point_vertex: 0,
            sort: Vec::with_capacity(SORT_RECORDS),
            flush: None,
            runs: Vec::with_capacity(MAX_RUNS),
            next_runs: Vec::with_capacity(MAX_RUNS),
            accum: None,
            group: 0,
            heads: Vec::with_capacity(8),
            output: Vec::with_capacity(RUN_RECORDS),
            final_head: None,
            active_cell: None,
            leaf: Vec::with_capacity(DATA_RECORDS),
            leaf_levels: (0..LEVELS).map(|_| Vec::with_capacity(FANOUT)).collect(),
            outer_levels: (0..LEVELS).map(|_| Vec::with_capacity(FANOUT)).collect(),
            node_ready: None,
            pending_read: None,
            pending_write: None,
            vertices: 0,
            read_bytes: 0,
            write_bytes: 0,
            max_write_bytes,
            cancelled: false,
            failed: false,
            expected,
            published: None,
            credit: Some(credit),
            base_bytes: base,
        })
    }
    pub fn storage_namespace(&self) -> u64 {
        self.owner
    }
    pub fn reserved_bytes(&self) -> usize {
        self.credit.as_ref().map_or(0, GeoProcessorLease::bytes)
    }
    pub fn has_outstanding_io(&self) -> bool {
        self.pending_read.is_some() || self.pending_write.is_some()
    }
    pub fn step(&mut self) -> Result<GeoHierarchyStep> {
        self.step_with_cancel(&mut || false)
    }
    pub fn step_with_cancel(
        &mut self,
        cancel: &mut dyn FnMut() -> bool,
    ) -> Result<GeoHierarchyStep> {
        if cancel() {
            self.cancel();
        }
        let result = self.advance(cancel);
        if result.is_err() {
            self.failed = true;
        }
        result
    }
    fn advance(&mut self, cancel: &mut dyn FnMut() -> bool) -> Result<GeoHierarchyStep> {
        if let Some(p) = &self.pending_read {
            return Ok(if p.accepted || self.failed || self.cancelled {
                GeoHierarchyStep::AwaitRelease
            } else {
                GeoHierarchyStep::NeedRead(p.ticket.clone())
            });
        }
        if let Some(p) = &self.pending_write {
            return Ok(if self.failed || self.cancelled {
                GeoHierarchyStep::AwaitRelease
            } else {
                GeoHierarchyStep::NeedWrite(p.ticket.clone())
            });
        }
        if self.cancelled || self.failed {
            return Ok(GeoHierarchyStep::Cancelled);
        }
        if self.published.is_some() {
            return Ok(GeoHierarchyStep::Complete);
        }
        loop {
            if cancel() {
                self.cancel();
                return Ok(GeoHierarchyStep::Cancelled);
            }
            if let Some((target, level, node)) = self.node_ready.take() {
                if level >= LEVELS {
                    return limit();
                }
                self.levels(target)[level].push(node);
            }
            for target in [Target::Leaf, Target::Outer] {
                if let Some(level) = self.levels(target).iter().position(|v| v.len() == FANOUT) {
                    return self.write_node(target, level);
                }
            }
            match self.phase {
                Phase::Source => {
                    if let Some(at) = self.flush {
                        if at < self.sort.len() {
                            let end = (at + RUN_RECORDS).min(self.sort.len());
                            let id = self.next_id;
                            let t = self.prepare_write(PAGE_BYTES)?;
                            let bytes = temp_bytes(id, &self.sort[at..end]);
                            self.flush = Some(end);
                            return self.write(t, bytes, WriteAction::Temp);
                        }
                        self.finish_run(false)?;
                        self.sort.clear();
                        self.flush = None;
                        continue;
                    }
                    if self.sort.len() == SORT_RECORDS {
                        self.begin_sort();
                        continue;
                    }
                    if self.current.is_some() {
                        if self.feed_one()? {
                            continue;
                        }
                        self.current = None;
                        self.current_credit = None;
                        self.chunk += 1;
                        continue;
                    }
                    let source = self.source.as_ref().unwrap();
                    if self.chunk < source.chunks().len() {
                        let r = source.read_request(self.chunk)?;
                        return self.read(
                            1,
                            Ref {
                                id: self.chunk as u64,
                                len: r.encoded_bytes,
                                digest: r.digest,
                            },
                            Some(r),
                            ReadAction::Source,
                        );
                    }
                    if !self.sort.is_empty() {
                        self.begin_sort();
                        continue;
                    }
                    self.sort = Vec::new();
                    self.group = 0;
                    self.phase = if self.runs.len() > 1 {
                        Phase::Merge
                    } else {
                        Phase::Final
                    };
                    continue;
                }
                Phase::Merge => {
                    if self.heads.is_empty() {
                        if self.group == self.runs.len() {
                            self.runs.clear();
                            std::mem::swap(&mut self.runs, &mut self.next_runs);
                            self.group = 0;
                            if self.runs.len() <= 1 {
                                self.phase = Phase::Final;
                            }
                            continue;
                        }
                        let end = (self.group + 8).min(self.runs.len());
                        for &r in &self.runs[self.group..end] {
                            self.heads.push(Head::new(r));
                        }
                        self.group = end;
                        self.begin_run();
                    }
                    for i in 0..self.heads.len() {
                        let h = &self.heads[i];
                        if h.at == h.buffer.len() && h.next < h.run.pages {
                            return self.read(
                                2,
                                Ref {
                                    id: h.run.start + h.next,
                                    len: PAGE_BYTES,
                                    digest: h.run.digest,
                                },
                                None,
                                ReadAction::Head(i),
                            );
                        }
                    }
                    if self.output.len() == RUN_RECORDS {
                        let t = self.prepare_write(PAGE_BYTES)?;
                        let bytes = temp_bytes(self.next_id, &self.output);
                        self.output.clear();
                        return self.write(t, bytes, WriteAction::Temp);
                    }
                    let selected = self
                        .heads
                        .iter()
                        .enumerate()
                        .filter(|(_, h)| h.at < h.buffer.len())
                        .min_by_key(|(_, h)| h.buffer[h.at].key(self.options.grid))
                        .map(|(i, _)| i);
                    if let Some(i) = selected {
                        let h = &mut self.heads[i];
                        self.output.push(h.buffer[h.at]);
                        h.at += 1;
                        continue;
                    }
                    if !self.output.is_empty() {
                        let t = self.prepare_write(PAGE_BYTES)?;
                        let bytes = temp_bytes(self.next_id, &self.output);
                        self.output.clear();
                        return self.write(t, bytes, WriteAction::Temp);
                    }
                    self.finish_run(true)?;
                    self.heads.clear();
                    continue;
                }
                Phase::Final => {
                    if self.final_head.is_none() && !self.runs.is_empty() {
                        self.final_head = Some(Head::new(self.runs[0]));
                    }
                    let incoming = self
                        .final_head
                        .as_ref()
                        .and_then(|h| h.buffer.get(h.at))
                        .copied();
                    if incoming.is_none() {
                        if let Some(h) = &self.final_head {
                            if h.next < h.run.pages {
                                return self.read(
                                    2,
                                    Ref {
                                        id: h.run.start + h.next,
                                        len: PAGE_BYTES,
                                        digest: h.run.digest,
                                    },
                                    None,
                                    ReadAction::Final,
                                );
                            }
                        }
                    }
                    let incoming = self
                        .final_head
                        .as_ref()
                        .and_then(|h| h.buffer.get(h.at))
                        .copied();
                    if self.active_cell.is_some()
                        && (incoming.is_none()
                            || incoming.is_some_and(|r| Some(r.cell) != self.active_cell))
                    {
                        if !self.leaf.is_empty() {
                            return self.write_leaf();
                        }
                        if let Some(step) = self.close_tree(Target::Leaf)? {
                            return Ok(step);
                        }
                        let root = self
                            .take_tree_root(Target::Leaf)
                            .ok_or(SourceError::InvalidFrame)?;
                        let t = self.prepare_write(64 + DESC)?;
                        let bytes = node_bytes(self.next_id, 3, &[root]);
                        let read = Ref {
                            id: self.next_id,
                            len: bytes.len(),
                            digest: hash(&bytes),
                        };
                        let node = combine(read, 3, &[root])?;
                        self.active_cell = None;
                        return self.write(t, bytes, WriteAction::Node(Target::Outer, 0, node));
                    }
                    if let Some(r) = incoming {
                        if self.active_cell.is_none() {
                            self.active_cell = Some(r.cell);
                        }
                        if self.leaf.len() == DATA_RECORDS {
                            return self.write_leaf();
                        }
                        self.leaf.push(r.value);
                        self.final_head.as_mut().unwrap().at += 1;
                        continue;
                    }
                    if let Some(step) = self.close_tree(Target::Outer)? {
                        return Ok(step);
                    }
                    let root = self.take_tree_root(Target::Outer);
                    if cancel() {
                        self.cancel();
                        return Ok(GeoHierarchyStep::Cancelled);
                    }
                    self.publish(root)?;
                    self.phase = Phase::Ready;
                    return Ok(GeoHierarchyStep::Complete);
                }
                Phase::Ready => return Ok(GeoHierarchyStep::Complete),
            }
        }
    }
    fn levels(&mut self, t: Target) -> &mut Vec<Vec<Node>> {
        match t {
            Target::Leaf => &mut self.leaf_levels,
            Target::Outer => &mut self.outer_levels,
        }
    }
    fn close_tree(&mut self, t: Target) -> Result<Option<GeoHierarchyStep>> {
        let levels = self.levels(t);
        let nonempty = levels.iter().filter(|l| !l.is_empty()).count();
        if nonempty == 0 {
            return Ok(None);
        }
        let level = levels.iter().position(|l| !l.is_empty()).unwrap();
        if nonempty == 1 && levels[level].len() == 1 {
            return Ok(None);
        }
        Ok(Some(self.write_node(t, level)?))
    }
    fn take_tree_root(&mut self, t: Target) -> Option<Node> {
        self.levels(t)
            .iter_mut()
            .find(|l| !l.is_empty())
            .and_then(Vec::pop)
    }
    fn write_node(&mut self, t: Target, level: usize) -> Result<GeoHierarchyStep> {
        if level + 1 >= LEVELS {
            return limit();
        }
        let encoded = 64 + self.levels(t)[level].len() * DESC;
        let loan = self.prepare_write(encoded)?;
        let c = std::mem::replace(&mut self.levels(t)[level], Vec::with_capacity(FANOUT));
        let kind = match t {
            Target::Leaf => 2,
            Target::Outer => 4,
        };
        let bytes = node_bytes(self.next_id, kind, &c);
        let node = combine(
            Ref {
                id: self.next_id,
                len: bytes.len(),
                digest: hash(&bytes),
            },
            kind,
            &c,
        )?;
        self.write(loan, bytes, WriteAction::Node(t, level + 1, node))
    }
    fn write_leaf(&mut self) -> Result<GeoHierarchyStep> {
        let cell = self.active_cell.unwrap();
        let t = self.prepare_write(64 + self.leaf.len() * 80)?;
        let bytes = data_bytes(self.next_id, cell, &self.leaf);
        let read = Ref {
            id: self.next_id,
            len: bytes.len(),
            digest: hash(&bytes),
        };
        let n = summarize(read, morton(cell, self.options.grid), &self.leaf)?;
        self.leaf.clear();
        self.write(t, bytes, WriteAction::Node(Target::Leaf, 0, n))
    }
    fn begin_sort(&mut self) {
        let grid = self.options.grid;
        self.sort.sort_unstable_by_key(|r| r.key(grid));
        self.flush = Some(0);
        self.begin_run();
    }
    fn begin_run(&mut self) {
        self.accum = Some(Accum {
            start: self.next_id,
            pages: 0,
            records: 0,
            hash: run_hash(),
        });
    }
    fn finish_run(&mut self, next: bool) -> Result<()> {
        let a = self.accum.take().ok_or(SourceError::InvalidFrame)?;
        if a.pages == 0 {
            return invalid();
        }
        let r = Run {
            start: a.start,
            pages: a.pages,
            records: a.records,
            digest: a.hash.finish(),
        };
        let target = if next {
            &mut self.next_runs
        } else {
            &mut self.runs
        };
        if target.len() == MAX_RUNS {
            return limit();
        }
        target.push(r);
        Ok(())
    }
    fn feed_one(&mut self) -> Result<bool> {
        let chunk = self.current.as_ref().unwrap();
        let col = chunk.column();
        if self.row == col.len() {
            return Ok(false);
        }
        if col.validity()[self.row] == 0 {
            self.row += 1;
            return Ok(true);
        }
        let (a, z) = if col.geometry() == crate::geo::GeoGeometry::Point {
            (self.point_vertex, self.point_vertex + 1)
        } else {
            (
                col.offsets0()[self.row] as usize,
                col.offsets0()[self.row + 1] as usize,
            )
        };
        self.vertex = self.vertex.max(a);
        if self.vertex >= z {
            self.row += 1;
            if col.geometry() == crate::geo::GeoGeometry::Point {
                self.point_vertex = z;
            }
            return Ok(true);
        }
        let xy = [col.xy()[self.vertex * 2], col.xy()[self.vertex * 2 + 1]];
        let cell = flat::cell(
            col.crs(),
            xy,
            flat::GeoSpatialOptions {
                grid: self.options.grid,
            },
        );
        let summary = &self.source.as_ref().unwrap().chunks()[self.chunk];
        let intervals = chunk.intervals();
        let value = Vertex {
            identity: FeatureRef {
                chunk_index: self.chunk as u32,
                row: self.row as u32,
                source_row: summary.first_row + self.row as u64,
                feature_id: col.feature_ids()[self.row],
            },
            vertex: self.vertex as u32,
            xy,
            start: intervals
                .and_then(|i| (i.start_validity[self.row] == 1).then(|| i.starts[self.row])),
            end: intervals.and_then(|i| (i.end_validity[self.row] == 1).then(|| i.ends[self.row])),
            value: chunk.values().map(|v| v[self.row]),
        };
        self.vertices = self
            .vertices
            .checked_add(1)
            .ok_or(SourceError::ResourceLimit)?;
        if self.vertices > self.vertex_limit {
            return limit();
        }
        self.sort.push(Record { cell, value });
        self.vertex += 1;
        Ok(true)
    }
    fn admitted(&self, len: usize, kind: u8) -> Result<usize> {
        let charge = len
            .checked_mul(if kind == 1 { 6 } else { 4 })
            .and_then(|n| n.checked_add(65536))
            .ok_or(SourceError::ResourceLimit)?;
        if self
            .base_bytes
            .checked_add(self.current_credit.as_ref().map_or(0, |c| c.bytes()))
            .and_then(|n| n.checked_add(charge))
            .is_none_or(|n| n > self.budget.processor_bytes)
        {
            return limit();
        }
        Ok(charge)
    }
    fn read(
        &mut self,
        kind: u8,
        r: Ref,
        source: Option<crate::geo_source::ReadRequest>,
        action: ReadAction,
    ) -> Result<GeoHierarchyStep> {
        self.admitted(r.len, kind)?;
        let total = self
            .read_bytes
            .checked_add(r.len as u64)
            .ok_or(SourceError::ResourceLimit)?;
        if total > self.budget.max_read_bytes {
            return limit();
        }
        let serial = self
            .serial
            .checked_add(1)
            .ok_or(SourceError::ResourceLimit)?;
        let t = ticket(self.owner, self.owner, serial, kind, r, source)?;
        self.serial = serial;
        self.read_bytes = total;
        self.pending_read = Some(PendingRead {
            ticket: t.clone(),
            action,
            accepted: false,
        });
        Ok(GeoHierarchyStep::NeedRead(t))
    }
    fn admitted_write_bytes(&self, len: usize) -> Result<u64> {
        let total = self
            .write_bytes
            .checked_add(len as u64)
            .ok_or(SourceError::ResourceLimit)?;
        if total > self.max_write_bytes {
            return limit();
        }
        Ok(total)
    }
    /// Includes all issued temporary/final pages, even if subsequently cancelled.
    pub fn written_bytes(&self) -> u64 {
        self.write_bytes
    }
    fn prepare_write(&self, len: usize) -> Result<GeoHierarchyTicket> {
        self.admitted_write_bytes(len)?;
        self.admitted(len, 3)?;
        self.next_id
            .checked_add(1)
            .ok_or(SourceError::ResourceLimit)?;
        let serial = self
            .serial
            .checked_add(1)
            .ok_or(SourceError::ResourceLimit)?;
        ticket(
            self.owner,
            self.owner,
            serial,
            3,
            Ref {
                id: self.next_id,
                len,
                digest: [0; 8],
            },
            None,
        )
    }
    fn write(
        &mut self,
        mut t: GeoHierarchyTicket,
        bytes: Vec<u8>,
        action: WriteAction,
    ) -> Result<GeoHierarchyStep> {
        if bytes.len() != t.read.len {
            return invalid();
        }
        let total = self.admitted_write_bytes(bytes.len())?;
        t.read.digest = hash(&bytes);
        self.write_bytes = total;
        self.next_id += 1;
        self.serial = t.serial;
        self.pending_write = Some(PendingWrite {
            bytes,
            ticket: t.clone(),
            action,
        });
        Ok(GeoHierarchyStep::NeedWrite(t))
    }

    pub fn write_bytes(&self, t: &GeoHierarchyTicket) -> Result<&[u8]> {
        let p = self
            .pending_write
            .as_ref()
            .ok_or(SourceError::StaleSource)?;
        if !p.ticket.same(t) {
            return Err(SourceError::StaleSource);
        }
        Ok(&p.bytes)
    }
    pub fn acknowledge_write(&mut self, t: &GeoHierarchyTicket) -> Result<()> {
        let p = self
            .pending_write
            .as_ref()
            .ok_or(SourceError::StaleSource)?;
        if !p.ticket.same(t) {
            return Err(SourceError::StaleSource);
        }
        let p = self.pending_write.take().unwrap();
        let result = (|| {
            if !self.cancelled && !self.failed {
                match p.action {
                    WriteAction::Temp => {
                        let a = self.accum.as_mut().ok_or(SourceError::InvalidFrame)?;
                        a.pages = a.pages.checked_add(1).ok_or(SourceError::ResourceLimit)?;
                        a.records = a
                            .records
                            .checked_add(get32(&p.bytes, 16) as u64)
                            .ok_or(SourceError::ResourceLimit)?;
                        a.hash.update(&p.bytes);
                    }
                    WriteAction::Node(t, l, n) => self.node_ready = Some((t, l, n)),
                }
            }
            Ok(())
        })();
        if result.is_err() {
            self.failed = true;
        }
        result
    }
    pub fn supply(&mut self, t: &GeoHierarchyTicket, b: &[u8]) -> Result<()> {
        let p = self.pending_read.as_ref().ok_or(SourceError::StaleSource)?;
        if !p.ticket.same(t) || p.accepted {
            return Err(SourceError::StaleSource);
        }
        let result = self.consume(b);
        if result.is_err() {
            self.failed = true;
        }
        self.pending_read.as_mut().unwrap().accepted = true;
        result
    }
    fn consume(&mut self, b: &[u8]) -> Result<()> {
        if self.cancelled || self.failed {
            return Err(SourceError::Cancelled);
        }
        let p = self.pending_read.as_ref().unwrap();
        if b.len() != p.ticket.read.len {
            return invalid();
        }
        match p.action {
            ReadAction::Source => {
                let r = p.ticket.source.unwrap();
                let c = parse_authenticated(
                    r,
                    b,
                    p.ticket
                        .credit
                        .bytes()
                        .min(crate::geo_source::MAX_CHUNK_PEAK),
                )?;
                self.current_credit = Some(Arc::clone(&p.ticket.credit));
                self.current = Some(c);
                self.row = 0;
                self.vertex = 0;
                self.point_vertex = 0;
            }
            ReadAction::Head(i) => {
                let source_rows = self.source.as_ref().unwrap().rows();
                Self::consume_head(&mut self.heads[i], b, self.options, source_rows)?;
            }
            ReadAction::Final => {
                let source_rows = self.source.as_ref().unwrap().rows();
                Self::consume_head(
                    self.final_head.as_mut().unwrap(),
                    b,
                    self.options,
                    source_rows,
                )?;
            }
        }
        Ok(())
    }
    fn consume_head(h: &mut Head, b: &[u8], options: GeoHierarchyOptions, rows: u64) -> Result<()> {
        let records = temp_records(b, h.run.start + h.next, options, rows)?;
        if h.last
            .is_some_and(|last| last >= records[0].key(options.grid))
        {
            return invalid();
        }
        h.last = records.last().map(|r| r.key(options.grid));
        h.hash.update(b);
        h.next += 1;
        h.records = h
            .records
            .checked_add(records.len() as u64)
            .ok_or(SourceError::ResourceLimit)?;
        if h.next == h.run.pages {
            let hash = std::mem::replace(&mut h.hash, run_hash()).finish();
            if hash != h.run.digest || h.records != h.run.records {
                return Err(SourceError::StaleSource);
            }
        }
        h.buffer = records;
        h.at = 0;
        Ok(())
    }
    pub fn release_read(&mut self, t: &GeoHierarchyTicket) -> Result<()> {
        let p = self.pending_read.as_ref().ok_or(SourceError::StaleSource)?;
        if !p.ticket.same(t) || (!p.accepted && !self.cancelled && !self.failed) {
            return Err(SourceError::StaleSource);
        }
        self.pending_read = None;
        Ok(())
    }
    pub fn cancel(&mut self) {
        self.cancelled = true;
    }
    fn publish(&mut self, root: Option<Node>) -> Result<()> {
        let source = self.source.take().unwrap();
        let digest = root_digest(&source, self.options, root);
        if self.expected.is_some_and(|d| d != digest) {
            return Err(SourceError::StaleSource);
        }
        self.sort = Vec::new();
        self.runs = Vec::new();
        self.next_runs = Vec::new();
        self.heads = Vec::new();
        self.final_head = None;
        self.output = Vec::new();
        self.leaf = Vec::new();
        self.leaf_levels = Vec::new();
        self.outer_levels = Vec::new();
        let mut credit = self.credit.take().unwrap();
        credit.resize(source.clone_reserved_bytes() + 65536)?;
        self.published = Some(Arc::new(ValidatedGeoHierarchy {
            source,
            options: self.options,
            root,
            namespace: self.owner,
            digest,
            credit,
        }));
        Ok(())
    }
    pub fn finish(&mut self) -> Result<Arc<ValidatedGeoHierarchy>> {
        if self.cancelled || self.failed || self.has_outstanding_io() {
            return Err(SourceError::Cancelled);
        }
        self.published.take().ok_or(SourceError::StaleSource)
    }
}
