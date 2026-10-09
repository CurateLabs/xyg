//! Bounded cross-chunk spatial leaf construction; no host I/O (§27/§28).
use crate::geo::GeoGeometry;
use crate::geo_source::{
    FeatureRef, GeoChunk, GeoSourceManifest, QueryBudget, ReadRequest, SourceError,
    parse_authenticated,
};
use crate::geo_source_session::{GeoProcessorLease, next_session_identity};
use crate::geo_spatial_index::*;
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoIndexReadTicket {
    pub session: u64,
    pub request: ReadRequest,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoIndexWriteTicket {
    pub session: u64,
    pub request: GeoSpatialRead,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GeoSpatialBuildStep {
    NeedRead(GeoIndexReadTicket),
    AwaitReadRelease(GeoIndexReadTicket),
    NeedWrite(GeoIndexWriteTicket),
    AwaitWriteRelease(GeoIndexWriteTicket),
    Complete,
    Cancelled,
}
#[derive(Default)]
struct CellBuffer {
    bytes: Vec<u8>,
    count: u32,
    first: u64,
    last: u64,
    start: Option<i64>,
    end: Option<i64>,
}
impl CellBuffer {
    fn push(&mut self, v: Vertex) {
        if self.count == 0 {
            self.bytes = Vec::with_capacity(PAGE_BYTES);
            self.bytes.resize(PAGE_HEADER, 0);
            self.first = v.identity.source_row;
            self.start = v.start;
            self.end = v.end;
        } else {
            self.start = match (self.start, v.start) {
                (Some(a), Some(b)) => Some(a.min(b)),
                _ => None,
            };
            self.end = match (self.end, v.end) {
                (Some(a), Some(b)) => Some(a.max(b)),
                _ => None,
            };
        }
        let a = self.bytes.len();
        self.bytes.resize(a + RECORD_BYTES, 0);
        write_vertex(&mut self.bytes, a, v);
        self.count += 1;
        self.last = v.identity.source_row;
    }
}
/// Private tentative buffers and input/output loans remain leased through ACK.
/// Partial cell pages span canonical chunks, preserving source/vertex order.
pub struct GeoSpatialBuildSession {
    source: Option<GeoSourceManifest>,
    options: GeoSpatialOptions,
    budget: QueryBudget,
    session: u64,
    next_chunk: usize,
    max_vertices: u64,
    vertices: u64,
    read_bytes: u64,
    current: Option<GeoChunk>,
    current_request: Option<ReadRequest>,
    row: usize,
    vertex: usize,
    cells: Vec<CellBuffer>,
    flush_cell: usize,
    pages: Vec<Page>,
    pending_read: Option<(GeoIndexReadTicket, bool)>,
    pending_write: Option<(Page, Vec<u8>)>,
    cancelled: bool,
    failed: bool,
    workspace: Option<GeoProcessorLease>,
    write_lease: Option<GeoProcessorLease>,
    metadata: GeoProcessorLease,
}
impl GeoSpatialBuildSession {
    pub fn new(
        source: &GeoSourceManifest,
        options: GeoSpatialOptions,
        budget: QueryBudget,
        max_vertices: u64,
    ) -> Result<Self> {
        supported(source)?;
        options.validate()?;
        budget.validate()?;
        if max_vertices == 0
            || source.rows() > budget.max_rows_examined
            || source.chunks().len() > budget.max_chunks
        {
            return Err(SourceError::ResourceLimit);
        }
        let count = (options.grid as usize)
            .checked_mul(options.grid as usize)
            .and_then(|n| n.checked_add(1))
            .ok_or(SourceError::ResourceLimit)?;
        let reserve = source
            .clone_reserved_bytes()
            .checked_add(count * (PAGE_BYTES + std::mem::size_of::<CellBuffer>()) + 16_384)
            .ok_or(SourceError::ResourceLimit)?;
        if reserve > budget.processor_bytes {
            return Err(SourceError::ResourceLimit);
        }
        let metadata = GeoProcessorLease::acquire(reserve)?;
        let cells = (0..count).map(|_| CellBuffer::default()).collect();
        Ok(Self {
            source: Some(source.clone_validated()),
            options,
            budget,
            session: next_session_identity()?,
            next_chunk: 0,
            max_vertices,
            vertices: 0,
            read_bytes: 0,
            current: None,
            current_request: None,
            row: 0,
            vertex: 0,
            cells,
            flush_cell: 0,
            pages: Vec::new(),
            pending_read: None,
            pending_write: None,
            cancelled: false,
            failed: false,
            workspace: None,
            write_lease: None,
            metadata,
        })
    }
    pub fn step(&mut self) -> Result<GeoSpatialBuildStep> {
        self.step_with_cancel(&mut || false)
    }
    pub fn step_with_cancel(
        &mut self,
        cancel: &mut dyn FnMut() -> bool,
    ) -> Result<GeoSpatialBuildStep> {
        if cancel() {
            self.cancel();
        }
        let result = self.step_inner(cancel);
        if result.is_err() {
            self.failed = true;
            self.current = None;
            self.cells = Vec::new();
        }
        result
    }
    fn step_inner(&mut self, cancel: &mut dyn FnMut() -> bool) -> Result<GeoSpatialBuildStep> {
        if let Some((t, consumed)) = self.pending_read {
            return Ok(if consumed || self.cancelled || self.failed {
                GeoSpatialBuildStep::AwaitReadRelease(t)
            } else {
                GeoSpatialBuildStep::NeedRead(t)
            });
        }
        if let Some((p, _)) = &self.pending_write {
            let t = GeoIndexWriteTicket {
                session: self.session,
                request: p.read,
            };
            return Ok(if self.cancelled || self.failed {
                GeoSpatialBuildStep::AwaitWriteRelease(t)
            } else {
                GeoSpatialBuildStep::NeedWrite(t)
            });
        }
        if self.cancelled || self.failed {
            return Ok(GeoSpatialBuildStep::Cancelled);
        }
        if self.source.is_none() {
            return Err(SourceError::StaleSource);
        }
        while let Some(c) = self.current.as_ref() {
            if cancel() {
                return Err(SourceError::Cancelled);
            }
            let column = c.column();
            if self.row == column.len() {
                self.current = None;
                self.current_request = None;
                self.workspace = None;
                break;
            }
            if column.validity()[self.row] == 0 {
                self.row += 1;
                continue;
            }
            let end = if column.geometry() == GeoGeometry::Point {
                self.vertex + 1
            } else {
                column.offsets0()[self.row + 1] as usize
            };
            if self.vertex >= end {
                self.row += 1;
                continue;
            }
            let (start, finish) = c.intervals().map_or((None, None), |t| {
                (
                    (t.start_validity[self.row] == 1).then(|| t.starts[self.row]),
                    (t.end_validity[self.row] == 1).then(|| t.ends[self.row]),
                )
            });
            let req = self.current_request.unwrap();
            let xy = [
                column.xy()[self.vertex * 2],
                column.xy()[self.vertex * 2 + 1],
            ];
            let cell = cell(column.crs(), xy, self.options);
            let r = Vertex {
                identity: FeatureRef {
                    chunk_index: req.chunk_index,
                    row: self.row as u32,
                    source_row: req.first_row + self.row as u64,
                    feature_id: column.feature_ids()[self.row],
                },
                vertex: self.vertex as u32,
                xy,
                start,
                end: finish,
                value: c.values().map(|v| v[self.row]),
            };
            self.vertex += 1;
            if column.geometry() == GeoGeometry::Point {
                self.row += 1;
            }
            let i = if cell == u32::MAX {
                self.cells.len() - 1
            } else {
                cell as usize
            };
            self.cells[i].push(r);
            if self.cells[i].count as usize == PAGE_RECORDS {
                self.flush(i)?;
                return self.step_inner(cancel);
            }
        }
        let source = self.source.as_ref().unwrap();
        if self.next_chunk == source.chunks().len() {
            while self.flush_cell < self.cells.len() {
                if cancel() {
                    return Err(SourceError::Cancelled);
                }
                let cell = self.flush_cell;
                self.flush_cell += 1;
                if self.cells[cell].count != 0 {
                    self.flush(cell)?;
                    return self.step_inner(cancel);
                }
            }
            return Ok(GeoSpatialBuildStep::Complete);
        }
        let req = source.read_request(self.next_chunk)?;
        let total = self
            .read_bytes
            .checked_add(req.encoded_bytes as u64)
            .ok_or(SourceError::ResourceLimit)?;
        let reserve = req
            .encoded_bytes
            .checked_mul(8)
            .and_then(|n| n.checked_add(16_384))
            .ok_or(SourceError::ResourceLimit)?;
        if total > self.budget.max_read_bytes
            || self
                .metadata
                .bytes()
                .checked_add(reserve)
                .is_none_or(|n| n > self.budget.processor_bytes)
        {
            return Err(SourceError::ResourceLimit);
        }
        self.workspace = Some(GeoProcessorLease::acquire(reserve)?);
        self.pending_read = Some((
            GeoIndexReadTicket {
                session: self.session,
                request: req,
            },
            false,
        ));
        self.read_bytes = total;
        self.step_inner(cancel)
    }
    fn base_bytes(&self) -> usize {
        self.source
            .as_ref()
            .map_or(0, GeoSourceManifest::metadata_bytes)
            + self.cells.len() * (PAGE_BYTES + std::mem::size_of::<CellBuffer>())
            + 16_384
    }
    fn flush(&mut self, i: usize) -> Result<()> {
        if HEADER + (self.pages.len() + 1) * ENTRY_BYTES > DIRECTORY_BYTES {
            return Err(SourceError::ResourceLimit);
        }
        if self.pages.len() == self.pages.capacity() {
            let capacity =
                (self.pages.capacity().max(128) * 2).min((DIRECTORY_BYTES - HEADER) / ENTRY_BYTES);
            let peak = self.base_bytes()
                + (self.pages.capacity() + capacity) * std::mem::size_of::<Page>();
            if peak + self.workspace.as_ref().map_or(0, GeoProcessorLease::bytes) + 3 * PAGE_BYTES
                > self.budget.processor_bytes
            {
                return Err(SourceError::ResourceLimit);
            }
            self.metadata.resize(peak)?;
            self.pages
                .try_reserve_exact(capacity - self.pages.len())
                .map_err(|_| SourceError::ResourceLimit)?;
            self.metadata
                .resize(self.base_bytes() + self.pages.capacity() * std::mem::size_of::<Page>())?;
        }
        if self.metadata.bytes()
            + self.workspace.as_ref().map_or(0, GeoProcessorLease::bytes)
            + 3 * PAGE_BYTES
            > self.budget.processor_bytes
        {
            return Err(SourceError::ResourceLimit);
        }
        self.write_lease = Some(GeoProcessorLease::acquire(3 * PAGE_BYTES)?);
        let mut cell = std::mem::take(&mut self.cells[i]);
        let id = self.pages.len() as u64;
        cell.bytes[..4].copy_from_slice(b"XYIP");
        put32(&mut cell.bytes, 4, 1);
        put64(&mut cell.bytes, 8, id);
        put32(&mut cell.bytes, 16, u32::MAX);
        let code = if i == self.cells.len() - 1 {
            u32::MAX
        } else {
            i as u32
        };
        put32(&mut cell.bytes, 20, code);
        put32(&mut cell.bytes, 24, cell.count);
        let p = Page {
            read: GeoSpatialRead {
                page: id,
                encoded_bytes: cell.bytes.len(),
                digest: hash(&cell.bytes),
            },
            chunk: u32::MAX,
            cell: code,
            count: cell.count,
            first: cell.first,
            last: cell.last,
            start: cell.start,
            end: cell.end,
        };
        self.pending_write = Some((p, cell.bytes));
        Ok(())
    }
    pub fn supply(
        &mut self,
        ticket: GeoIndexReadTicket,
        bytes: &[u8],
        cancel: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        if self.cancelled || self.failed || self.pending_read != Some((ticket, false)) {
            return Err(SourceError::StaleSource);
        }
        let result = (|| {
            if cancel() {
                return Err(SourceError::Cancelled);
            }
            let c = parse_authenticated(
                ticket.request,
                bytes,
                self.workspace.as_ref().unwrap().bytes(),
            )?;
            let total = self
                .vertices
                .checked_add(c.column().vertex_count() as u64)
                .ok_or(SourceError::ResourceLimit)?;
            if total > self.max_vertices {
                return Err(SourceError::ResourceLimit);
            }
            if cancel() {
                return Err(SourceError::Cancelled);
            }
            self.vertices = total;
            self.current = Some(c);
            self.current_request = Some(ticket.request);
            self.row = 0;
            self.vertex = 0;
            self.next_chunk += 1;
            self.pending_read = Some((ticket, true));
            Ok(())
        })();
        if result.is_err() {
            self.failed = true;
            self.current = None;
            self.cells = Vec::new();
        }
        result
    }
    pub fn release_read(&mut self, ticket: GeoIndexReadTicket) -> Result<()> {
        if self.pending_read.map(|p| p.0) != Some(ticket)
            || (!self.cancelled && !self.failed && self.pending_read != Some((ticket, true)))
        {
            return Err(SourceError::StaleSource);
        }
        self.pending_read = None;
        if self.cancelled || self.failed {
            self.workspace = None;
        }
        Ok(())
    }
    pub fn write_bytes(&self, ticket: GeoIndexWriteTicket) -> Result<&[u8]> {
        let (p, b) = self
            .pending_write
            .as_ref()
            .ok_or(SourceError::StaleSource)?;
        if ticket.session != self.session || ticket.request != p.read {
            return Err(SourceError::StaleSource);
        }
        Ok(b)
    }
    pub fn acknowledge_write(&mut self, ticket: GeoIndexWriteTicket) -> Result<()> {
        let p = self
            .pending_write
            .as_ref()
            .map(|p| p.0)
            .ok_or(SourceError::StaleSource)?;
        if ticket.session != self.session || ticket.request != p.read {
            return Err(SourceError::StaleSource);
        }
        self.pending_write = None;
        self.write_lease = None;
        if !self.cancelled && !self.failed {
            self.pages.push(p);
        } else {
            self.workspace = None;
        }
        Ok(())
    }
    pub fn cancel(&mut self) {
        self.cancelled = true;
        self.current = None;
        self.cells = Vec::new();
        self.pages = Vec::new();
    }
    pub fn has_outstanding_io(&self) -> bool {
        self.pending_read.is_some() || self.pending_write.is_some()
    }
    pub fn finish(&mut self) -> Result<ValidatedGeoSpatialIndex> {
        if self.step()? != GeoSpatialBuildStep::Complete {
            return Err(SourceError::StaleSource);
        }
        self.pages.sort_unstable_by_key(|p| (p.cell, p.read.page));
        self.cells = Vec::new();
        let source = self.source.take().unwrap();
        self.metadata.resize(
            source.metadata_bytes() + self.pages.capacity() * std::mem::size_of::<Page>() + 16_384,
        )?;
        Ok(ValidatedGeoSpatialIndex {
            source,
            options: self.options,
            pages: std::mem::take(&mut self.pages),
            lease: std::mem::replace(&mut self.metadata, GeoProcessorLease::acquire(0)?),
        })
    }
}
/// Synchronous native/conformance adapter; callbacks perform no product policy.
/// Read vectors and writer temporaries must be dropped before their ACKs.
pub fn build<
    R: crate::geo_source::GeoChunkReader,
    W: FnMut(GeoIndexWriteTicket, &[u8]) -> Result<()>,
>(
    source: &GeoSourceManifest,
    reader: &mut R,
    writer: &mut W,
    options: GeoSpatialOptions,
    budget: QueryBudget,
    max_vertices: u64,
    cancel: &mut dyn FnMut() -> bool,
) -> Result<ValidatedGeoSpatialIndex> {
    let mut s = GeoSpatialBuildSession::new(source, options, budget, max_vertices)?;
    loop {
        if cancel() {
            s.cancel();
            return Err(SourceError::Cancelled);
        }
        match s.step_with_cancel(cancel)? {
            GeoSpatialBuildStep::NeedRead(t) => {
                let bytes = reader.read_chunk(t.request)?;
                if bytes.capacity() > t.request.encoded_bytes {
                    s.cancel();
                    return Err(SourceError::ResourceLimit);
                }
                s.supply(t, &bytes, cancel)?;
                drop(bytes);
                s.release_read(t)?;
            }
            GeoSpatialBuildStep::NeedWrite(t) => {
                writer(t, s.write_bytes(t)?)?;
                s.acknowledge_write(t)?;
            }
            GeoSpatialBuildStep::Complete => return s.finish(),
            _ => return Err(SourceError::StaleSource),
        }
    }
}
/// Imported directories do not authorize pruning. Rebuild from authenticated
/// canonical chunks and compare EVERY leaf byte and the complete directory.
/// This also proves no omitted/duplicated records, false bounds or fake time zones.
pub fn validate_import<R: crate::geo_source::GeoChunkReader, I: GeoSpatialReader>(
    source: &GeoSourceManifest,
    directory: &[u8],
    canonical: &mut R,
    leaves: &mut I,
    budget: QueryBudget,
    max_vertices: u64,
    cancel: &mut dyn FnMut() -> bool,
) -> Result<ValidatedGeoSpatialIndex> {
    if directory.len() < HEADER
        || directory.len() > DIRECTORY_BYTES
        || &directory[..4] != b"XYIX"
        || get32(directory, 4) != 1
    {
        return Err(SourceError::InvalidFrame);
    }
    let count = usize::try_from(get64(directory, 48)).map_err(|_| SourceError::ResourceLimit)?;
    let expected = count
        .checked_mul(ENTRY_BYTES)
        .and_then(|n| n.checked_add(HEADER))
        .ok_or(SourceError::ResourceLimit)?;
    if expected != directory.len()
        || get32(directory, 12) != source.crs() as u32
        || get32(directory, 16) != source.geometry() as u32
        || get64(directory, 24) != source.generation()
        || get64(directory, 32) != source.rows()
        || directory[40..48] != source.digest()
        || directory[20..24]
            .iter()
            .chain(directory[56..128].iter())
            .any(|&n| n != 0)
    {
        return Err(SourceError::StaleSource);
    }
    let _input = GeoProcessorLease::acquire(
        directory
            .len()
            .checked_mul(3)
            .ok_or(SourceError::ResourceLimit)?,
    )?;
    let mut build_budget = budget;
    build_budget.processor_bytes = budget
        .processor_bytes
        .checked_sub(_input.bytes())
        .ok_or(SourceError::ResourceLimit)?;
    let options = GeoSpatialOptions {
        grid: get32(directory, 8),
    };
    let index = build(
        source,
        canonical,
        &mut |t, b| {
            let returned = leaves.read(t.request)?;
            if returned.len() != b.len()
                || returned.capacity() > PAGE_BYTES
                || returned.as_slice() != b
            {
                return Err(SourceError::StaleSource);
            }
            Ok(())
        },
        options,
        build_budget,
        max_vertices,
        cancel,
    )?;
    if index
        .reserved_bytes()
        .checked_add(_input.bytes())
        .and_then(|n| n.checked_add(3 * index.encoded_len()))
        .is_none_or(|n| n > budget.processor_bytes)
    {
        return Err(SourceError::ResourceLimit);
    }
    if index.encode()?.as_slice() != directory {
        return Err(SourceError::StaleSource);
    }
    Ok(index)
}
