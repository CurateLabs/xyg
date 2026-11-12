//! Host-neutral XYGC layout validation. Transport supplies bytes; Rust validates
//! extents and metadata incrementally, without materializing numeric columns.

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ChunkMeta {
    pub row_start: u64,
    pub row_count: u32,
    pub x_min: f64,
    pub x_max: f64,
    pub y_min: f64,
    pub y_max: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct Header {
    pub rows: u64,
    pub chunk_rows: u32,
    pub chunk_count: u32,
    pub data_offset: u64,
    pub overview_offset: u64,
    pub overview_count: u32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct OverviewPoint {
    pub row: u64,
    pub x: f64,
    pub y: f64,
}

#[derive(Clone, Copy)]
pub struct OverviewValidator {
    rows: u64,
    expected: u32,
    seen: u32,
    previous: Option<u64>,
}
impl OverviewValidator {
    pub fn new(header: Header) -> Self {
        Self {
            rows: header.rows,
            expected: header.overview_count,
            seen: 0,
            previous: None,
        }
    }
    pub fn read(&mut self, b: &[u8]) -> Result<OverviewPoint, &'static str> {
        if b.len() != 24 || self.seen == self.expected {
            return Err("invalid overview extent");
        }
        let point = OverviewPoint {
            row: u64::from_le_bytes(b[..8].try_into().unwrap()),
            x: f64::from_le_bytes(b[8..16].try_into().unwrap()),
            y: f64::from_le_bytes(b[16..].try_into().unwrap()),
        };
        if point.row >= self.rows
            || !point.x.is_finite()
            || !point.y.is_finite()
            || self.previous.is_some_and(|row| row >= point.row)
        {
            return Err("invalid overview point");
        }
        self.previous = Some(point.row);
        self.seen += 1;
        Ok(point)
    }
    pub fn finish(&self) -> Result<(), &'static str> {
        if self.seen != self.expected {
            return Err("invalid overview extent");
        }
        Ok(())
    }
}
impl Header {
    pub fn decode(b: &[u8], file_len: u64) -> Result<Self, &'static str> {
        if b.len() != 64 {
            return Err("short header");
        }
        if &b[..4] != b"XYGC" {
            return Err("bad magic");
        }
        let u32_at = |at| u32::from_le_bytes(b[at..at + 4].try_into().unwrap());
        let u64_at = |at| u64::from_le_bytes(b[at..at + 8].try_into().unwrap());
        let version = u32_at(4);
        if version != 1 && version != 2 {
            return Err("unsupported version");
        }
        if b[if version == 1 { 32 } else { 44 }..]
            .iter()
            .any(|v| *v != 0)
        {
            return Err("nonzero reserved header bytes");
        }
        let rows = u64_at(8);
        let chunk_rows = u32_at(16);
        let chunk_count = u32_at(20);
        let data_offset = u64_at(24);
        if chunk_rows == 0 || data_offset != 64 + 48 * u64::from(chunk_count) {
            return Err("inconsistent header");
        }
        let rows_end = rows
            .checked_mul(16)
            .and_then(|n| data_offset.checked_add(n))
            .ok_or("size overflow")?;
        let (overview_offset, overview_count) = if version == 2 {
            (u64_at(32), u32_at(40))
        } else {
            (rows_end, 0)
        };
        if overview_count > 2048 || u64::from(overview_count) > rows {
            return Err("invalid overview count");
        }
        if overview_offset != rows_end {
            return Err("inconsistent overview offset");
        }
        let expected = overview_offset
            .checked_add(u64::from(overview_count) * 24)
            .ok_or("size overflow")?;
        if expected != file_len {
            return Err("file length does not match header");
        }
        Ok(Self {
            rows,
            chunk_rows,
            chunk_count,
            data_offset,
            overview_offset,
            overview_count,
        })
    }
}

#[derive(Clone, Copy)]
pub struct MetadataValidator {
    header: Header,
    next_row: u64,
    chunks: u32,
    previous_max: f64,
}
impl MetadataValidator {
    pub fn new(header: Header) -> Self {
        Self {
            header,
            next_row: 0,
            chunks: 0,
            previous_max: f64::NEG_INFINITY,
        }
    }
    pub fn read(&mut self, b: &[u8]) -> Result<ChunkMeta, &'static str> {
        if b.len() != 48 || self.chunks == self.header.chunk_count {
            return Err("invalid metadata extent");
        }
        if b[12..16] != [0; 4] {
            return Err("nonzero reserved metadata bytes");
        }
        let u64_at = |at| u64::from_le_bytes(b[at..at + 8].try_into().unwrap());
        let meta = ChunkMeta {
            row_start: u64_at(0),
            row_count: u32::from_le_bytes(b[8..12].try_into().unwrap()),
            x_min: f64::from_bits(u64_at(16)),
            x_max: f64::from_bits(u64_at(24)),
            y_min: f64::from_bits(u64_at(32)),
            y_max: f64::from_bits(u64_at(40)),
        };
        let next = meta.row_start.checked_add(u64::from(meta.row_count));
        if meta.row_start != self.next_row
            || meta.row_count == 0
            || meta.row_count > self.header.chunk_rows
            || !meta.x_min.is_finite()
            || !meta.x_max.is_finite()
            || !meta.y_min.is_finite()
            || !meta.y_max.is_finite()
            || meta.x_min > meta.x_max
            || meta.y_min > meta.y_max
            || meta.x_min < self.previous_max
            || next.is_none_or(|n| n > self.header.rows)
        {
            return Err("invalid or unordered chunk metadata");
        }
        self.next_row = next.unwrap();
        self.previous_max = meta.x_max;
        self.chunks += 1;
        Ok(meta)
    }
    pub fn finish(&self) -> Result<(), &'static str> {
        if self.next_row != self.header.rows || self.chunks != self.header.chunk_count {
            return Err("chunk rows do not sum to row count");
        }
        Ok(())
    }
}

pub const MAX_CANONICAL_PAGE_ROWS: u32 = 65_536;
pub const CANONICAL_PAGE_OVERHEAD: u64 = 96;

#[derive(Debug)]
pub struct CanonicalRows {
    pub first_row: u64,
    pub x: Vec<f64>,
    pub y: Vec<f64>,
    pub bytes_read: u64,
    pub peak_bytes: u64,
}

#[derive(Debug, PartialEq)]
pub enum PageError {
    InvalidRange,
    Corrupt(&'static str),
    BudgetExceeded { needed: u64, budget: u64 },
    Cancelled,
    Allocation,
}

/// Transport may read only the byte interval requested by the owning reader.
/// The serial belongs to that reader, not to a native file-handle registry.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ReadTicket {
    pub serial: u64,
    pub offset: u64,
    pub length: u32,
}

pub const MAX_LAYOUT_READ_BYTES: u32 = 65_536;
const LAYOUT_READER_BYTES: u64 = 512;

#[derive(Clone, Copy)]
enum LayoutPhase {
    Header,
    Metadata(MetadataValidator),
    Overview(OverviewValidator),
    Complete,
}

/// Incremental layout acquisition shared by positioned native reads and a
/// future portable byte transport. No canonical numeric rows are requested.
pub struct LayoutReader {
    file_len: u64,
    budget: u64,
    header: Option<Header>,
    metadata: Vec<ChunkMeta>,
    overview: Vec<OverviewPoint>,
    phase: LayoutPhase,
    ticket: Option<ReadTicket>,
}
const _: () = assert!(std::mem::size_of::<LayoutReader>() <= LAYOUT_READER_BYTES as usize);

pub struct CanonicalLayout {
    pub header: Header,
    pub metadata: Vec<ChunkMeta>,
    pub overview: Vec<OverviewPoint>,
}

fn layout_admit(metadata: usize, overview: usize, raw: u64, budget: u64) -> Result<u64, PageError> {
    let needed = (metadata as u64)
        .checked_mul(48)
        .and_then(|n| n.checked_add((overview as u64).checked_mul(24)?))
        .and_then(|n| n.checked_add(LAYOUT_READER_BYTES))
        .and_then(|n| n.checked_add(raw))
        .ok_or(PageError::InvalidRange)?;
    if needed > budget {
        return Err(PageError::BudgetExceeded { needed, budget });
    }
    Ok(needed)
}

impl LayoutReader {
    pub fn new(file_len: u64, budget: u64) -> Result<Self, PageError> {
        if file_len < 64 {
            return Err(PageError::Corrupt("short header"));
        }
        layout_admit(0, 0, 64, budget)?;
        Ok(Self {
            file_len,
            budget,
            header: None,
            metadata: Vec::new(),
            overview: Vec::new(),
            phase: LayoutPhase::Header,
            ticket: Some(ReadTicket {
                serial: 1,
                offset: 0,
                length: 64,
            }),
        })
    }
    pub fn ticket(&self) -> Option<ReadTicket> {
        self.ticket
    }
    pub fn retained_bytes(&self) -> u64 {
        LAYOUT_READER_BYTES
            + self.metadata.capacity() as u64 * 48
            + self.overview.capacity() as u64 * 24
    }
    /// Refused, malformed, cancelled or stale fulfilments leave the ticket and
    /// accepted prefix unchanged. Admission precedes any metadata allocation.
    pub fn fulfil(
        &mut self,
        ticket: ReadTicket,
        raw: &[u8],
        raw_capacity: u64,
        mut is_current: impl FnMut() -> bool,
    ) -> Result<(), PageError> {
        if self.ticket != Some(ticket) {
            return Err(PageError::InvalidRange);
        }
        if raw.len() != ticket.length as usize || raw_capacity < raw.len() as u64 {
            return Err(PageError::Corrupt("read ticket extent mismatch"));
        }
        let serial = ticket
            .serial
            .checked_add(1)
            .ok_or(PageError::InvalidRange)?;
        layout_admit(
            self.metadata.capacity(),
            self.overview.capacity(),
            raw_capacity,
            self.budget,
        )?;
        if !is_current() {
            return Err(PageError::Cancelled);
        }
        match self.phase {
            LayoutPhase::Header => {
                let header = Header::decode(raw, self.file_len).map_err(PageError::Corrupt)?;
                // Reserve the complete layout and the largest future ticket,
                // including coexistence with the current transport buffer.
                let metadata_window =
                    u64::from(header.chunk_count.min(MAX_LAYOUT_READ_BYTES / 48)) * 48;
                let overview_window =
                    u64::from(header.overview_count.min(MAX_LAYOUT_READ_BYTES / 24)) * 24;
                let window = raw_capacity.max(metadata_window).max(overview_window);
                layout_admit(
                    header.chunk_count as usize,
                    header.overview_count as usize,
                    window,
                    self.budget,
                )?;
                let mut metadata = Vec::new();
                let mut overview = Vec::new();
                metadata
                    .try_reserve_exact(header.chunk_count as usize)
                    .map_err(|_| PageError::Allocation)?;
                overview
                    .try_reserve_exact(header.overview_count as usize)
                    .map_err(|_| PageError::Allocation)?;
                layout_admit(
                    metadata.capacity(),
                    overview.capacity(),
                    window,
                    self.budget,
                )?;
                let phase = Self::phase_after_metadata(header, MetadataValidator::new(header))?;
                let next = Self::next_ticket(header, phase, 0, 0, serial);
                if !is_current() {
                    return Err(PageError::Cancelled);
                }
                self.header = Some(header);
                self.metadata = metadata;
                self.overview = overview;
                self.phase = phase;
                self.ticket = next;
            }
            LayoutPhase::Metadata(mut validator) => {
                // Validate against a copied cursor before changing either the
                // accepted vectors or their cursor. A bad late record is atomic.
                let mut checked = validator;
                for (i, record) in raw.chunks_exact(48).enumerate() {
                    if i % 64 == 0 && !is_current() {
                        return Err(PageError::Cancelled);
                    }
                    checked.read(record).map_err(PageError::Corrupt)?;
                }
                let header = self.header.unwrap();
                let phase = Self::phase_after_metadata(header, checked)?;
                let next = Self::next_ticket(
                    header,
                    phase,
                    self.metadata.len() + raw.len() / 48,
                    self.overview.len(),
                    serial,
                );
                if !is_current() {
                    return Err(PageError::Cancelled);
                }
                // Pure, bounded commit after the final cancellation check.
                for record in raw.chunks_exact(48) {
                    self.metadata.push(validator.read(record).unwrap());
                }
                self.phase = phase;
                self.ticket = next;
            }
            LayoutPhase::Overview(mut validator) => {
                let mut checked = validator;
                for (i, record) in raw.chunks_exact(24).enumerate() {
                    if i % 64 == 0 && !is_current() {
                        return Err(PageError::Cancelled);
                    }
                    checked.read(record).map_err(PageError::Corrupt)?;
                }
                let header = self.header.unwrap();
                let n = self.overview.len() + raw.len() / 24;
                let phase = if n == header.overview_count as usize {
                    checked.finish().map_err(PageError::Corrupt)?;
                    LayoutPhase::Complete
                } else {
                    LayoutPhase::Overview(checked)
                };
                let next = Self::next_ticket(header, phase, self.metadata.len(), n, serial);
                if !is_current() {
                    return Err(PageError::Cancelled);
                }
                for record in raw.chunks_exact(24) {
                    self.overview.push(validator.read(record).unwrap());
                }
                self.phase = phase;
                self.ticket = next;
            }
            LayoutPhase::Complete => return Err(PageError::InvalidRange),
        }
        Ok(())
    }
    fn phase_after_metadata(
        header: Header,
        validator: MetadataValidator,
    ) -> Result<LayoutPhase, PageError> {
        if validator.chunks != header.chunk_count {
            return Ok(LayoutPhase::Metadata(validator));
        }
        validator.finish().map_err(PageError::Corrupt)?;
        let overview = OverviewValidator::new(header);
        if header.overview_count == 0 {
            overview.finish().map_err(PageError::Corrupt)?;
            Ok(LayoutPhase::Complete)
        } else {
            Ok(LayoutPhase::Overview(overview))
        }
    }
    fn next_ticket(
        header: Header,
        phase: LayoutPhase,
        metadata: usize,
        overview: usize,
        serial: u64,
    ) -> Option<ReadTicket> {
        match phase {
            LayoutPhase::Metadata(_) => Some(ReadTicket {
                serial,
                offset: 64 + metadata as u64 * 48,
                length: (header.chunk_count - metadata as u32).min(MAX_LAYOUT_READ_BYTES / 48) * 48,
            }),
            LayoutPhase::Overview(_) => Some(ReadTicket {
                serial,
                offset: header.overview_offset + overview as u64 * 24,
                length: (header.overview_count - overview as u32).min(MAX_LAYOUT_READ_BYTES / 24)
                    * 24,
            }),
            _ => None,
        }
    }
    pub fn finish(self) -> Result<CanonicalLayout, PageError> {
        if !matches!(self.phase, LayoutPhase::Complete) {
            return Err(PageError::Corrupt("incomplete layout acquisition"));
        }
        Ok(CanonicalLayout {
            header: self.header.unwrap(),
            metadata: self.metadata,
            overview: self.overview,
        })
    }
}

pub fn canonical_page_workspace(
    rows: u64,
    first: u64,
    count: u32,
    budget: u64,
) -> Result<u64, PageError> {
    if count > MAX_CANONICAL_PAGE_ROWS
        || first
            .checked_add(u64::from(count))
            .is_none_or(|end| end > rows)
    {
        return Err(PageError::InvalidRange);
    }
    canonical_buffer_workspace(count, u64::from(count) * 16, budget)
}

pub(crate) fn canonical_buffer_workspace(
    count: u32,
    raw_capacity: u64,
    budget: u64,
) -> Result<u64, PageError> {
    if raw_capacity < u64::from(count) * 16 {
        return Err(PageError::InvalidRange);
    }
    let needed = raw_capacity
        .checked_add(u64::from(count) * 16)
        .and_then(|n| n.checked_add(CANONICAL_PAGE_OVERHEAD))
        .ok_or(PageError::InvalidRange)?;
    if needed > budget {
        return Err(PageError::BudgetExceeded { needed, budget });
    }
    Ok(needed)
}

/// Decode a canonical interval. Both native positioned reads and browser read
/// tickets use this validation; transport never filters, renumbers or bins rows.
pub fn decode_canonical_rows(
    metadata: &[ChunkMeta],
    rows: u64,
    first: u64,
    raw: &[u8],
    raw_capacity: u64,
    budget: u64,
    mut is_current: impl FnMut() -> bool,
) -> Result<CanonicalRows, PageError> {
    if !raw.len().is_multiple_of(16) || raw_capacity < raw.len() as u64 {
        return Err(PageError::Corrupt("invalid canonical page extent"));
    }
    let count = u32::try_from(raw.len() / 16).map_err(|_| PageError::InvalidRange)?;
    canonical_page_workspace(rows, first, count, budget)?;
    let needed = canonical_buffer_workspace(count, raw_capacity, budget)?;
    if !is_current() {
        return Err(PageError::Cancelled);
    }
    let mut result = CanonicalRows {
        first_row: first,
        x: Vec::new(),
        y: Vec::new(),
        bytes_read: raw.len() as u64,
        peak_bytes: needed,
    };
    result
        .x
        .try_reserve_exact(count as usize)
        .map_err(|_| PageError::Allocation)?;
    result
        .y
        .try_reserve_exact(count as usize)
        .map_err(|_| PageError::Allocation)?;
    result.peak_bytes = (result.x.capacity() as u64 + result.y.capacity() as u64)
        .checked_mul(8)
        .and_then(|n| n.checked_add(raw_capacity))
        .and_then(|n| n.checked_add(CANONICAL_PAGE_OVERHEAD))
        .ok_or(PageError::InvalidRange)?;
    if result.peak_bytes > budget {
        return Err(PageError::BudgetExceeded {
            needed: result.peak_bytes,
            budget,
        });
    }
    if count != 0 {
        let mut chunk = metadata
            .partition_point(|meta| meta.row_start <= first)
            .checked_sub(1)
            .ok_or(PageError::Corrupt("canonical page has no metadata"))?;
        let mut previous_x = f64::NEG_INFINITY;
        for (offset, bytes) in raw.chunks_exact(16).enumerate() {
            if offset % 4096 == 0 && !is_current() {
                return Err(PageError::Cancelled);
            }
            let row = first + offset as u64;
            loop {
                let meta = metadata
                    .get(chunk)
                    .ok_or(PageError::Corrupt("canonical page exceeds metadata"))?;
                let end = meta
                    .row_start
                    .checked_add(u64::from(meta.row_count))
                    .ok_or(PageError::Corrupt("canonical metadata row overflow"))?;
                if row < meta.row_start || end > rows || meta.row_count == 0 {
                    return Err(PageError::Corrupt("invalid canonical metadata interval"));
                }
                if row < end {
                    break;
                }
                chunk += 1;
                previous_x = f64::NEG_INFINITY;
            }
            let meta = &metadata[chunk];
            let x = f64::from_le_bytes(bytes[..8].try_into().unwrap());
            let y = f64::from_le_bytes(bytes[8..].try_into().unwrap());
            if x.is_finite() {
                if x < previous_x || x < meta.x_min || x > meta.x_max {
                    return Err(PageError::Corrupt("canonical x page differs from metadata"));
                }
                previous_x = x;
            }
            if y.is_finite() && (y < meta.y_min || y > meta.y_max) {
                return Err(PageError::Corrupt("canonical y page differs from metadata"));
            }
            result.x.push(x);
            result.y.push(y);
        }
    }
    if !is_current() {
        return Err(PageError::Cancelled);
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn layout_fixture(chunks: u32, with_overview: bool) -> Vec<u8> {
        let rows = u64::from(chunks);
        let overview = if with_overview && chunks > 1 { 2 } else { 0 };
        let data = 64 + u64::from(chunks) * 48;
        let end = data + rows * 16;
        let mut b = vec![0; (end + overview * 24) as usize];
        b[..4].copy_from_slice(b"XYGC");
        b[4..8].copy_from_slice(&(if with_overview { 2u32 } else { 1 }).to_le_bytes());
        b[8..16].copy_from_slice(&rows.to_le_bytes());
        b[16..20].copy_from_slice(&1u32.to_le_bytes());
        b[20..24].copy_from_slice(&chunks.to_le_bytes());
        b[24..32].copy_from_slice(&data.to_le_bytes());
        if with_overview {
            b[32..40].copy_from_slice(&end.to_le_bytes());
            b[40..44].copy_from_slice(&(overview as u32).to_le_bytes());
        }
        for i in 0..chunks as usize {
            let at = 64 + i * 48;
            b[at..at + 8].copy_from_slice(&(i as u64).to_le_bytes());
            b[at + 8..at + 12].copy_from_slice(&1u32.to_le_bytes());
            for (j, value) in [i as f64, i as f64, -(i as f64), -(i as f64)]
                .iter()
                .enumerate()
            {
                b[at + 16 + j * 8..at + 24 + j * 8].copy_from_slice(&value.to_le_bytes());
            }
            let at = data as usize + i * 16;
            b[at..at + 8].copy_from_slice(&(i as f64).to_le_bytes());
            b[at + 8..at + 16].copy_from_slice(&(-(i as f64)).to_le_bytes());
        }
        if overview != 0 {
            for (j, i) in [0, rows - 1].iter().enumerate() {
                let at = end as usize + j * 24;
                b[at..at + 8].copy_from_slice(&i.to_le_bytes());
                b[at + 8..at + 16].copy_from_slice(&(*i as f64).to_le_bytes());
                b[at + 16..at + 24].copy_from_slice(&(-(*i as f64)).to_le_bytes());
            }
        }
        b
    }
    fn ticket_bytes(b: &[u8], ticket: ReadTicket) -> &[u8] {
        &b[ticket.offset as usize..ticket.offset as usize + ticket.length as usize]
    }
    #[test]
    fn portable_layout_tickets_skip_canonical_rows_and_bound_reads_for_both_versions() {
        for version2 in [false, true] {
            let b = layout_fixture(1400, version2);
            let data = 64 + 1400 * 48;
            let end = data + 1400 * 16;
            let mut reader = LayoutReader::new(b.len() as u64, 1 << 20).unwrap();
            let mut serial = 0;
            let mut bytes = 0;
            while let Some(ticket) = reader.ticket() {
                assert_eq!(ticket.serial, serial + 1);
                assert!(ticket.length <= MAX_LAYOUT_READ_BYTES);
                assert!(ticket.offset + u64::from(ticket.length) <= data || ticket.offset >= end);
                serial = ticket.serial;
                bytes += u64::from(ticket.length);
                let raw = ticket_bytes(&b, ticket);
                reader
                    .fulfil(ticket, raw, raw.len() as u64, || true)
                    .unwrap();
            }
            let result = reader.finish().unwrap();
            assert_eq!(bytes, 64 + 1400 * 48 + if version2 { 48 } else { 0 });
            assert_eq!(serial, if version2 { 4 } else { 3 });
            assert_eq!(result.header.rows, 1400);
            assert_eq!(result.metadata.len(), 1400);
            for (i, meta) in result.metadata.iter().enumerate() {
                assert_eq!((meta.row_start, meta.row_count), (i as u64, 1));
                assert_eq!(meta.x_min.to_bits(), (i as f64).to_bits());
                assert_eq!(meta.y_max.to_bits(), (-(i as f64)).to_bits());
            }
            assert_eq!(result.overview.len(), if version2 { 2 } else { 0 });
            if version2 {
                assert_eq!(result.overview[1].row, 1399);
            }
        }
        for version2 in [false, true] {
            let b = layout_fixture(0, version2);
            let mut reader = LayoutReader::new(64, 576).unwrap();
            reader
                .fulfil(reader.ticket().unwrap(), &b, 64, || true)
                .unwrap();
            assert!(reader.ticket().is_none());
            assert_eq!(reader.finish().unwrap().header.rows, 0);
        }
    }
    #[test]
    fn portable_layout_admission_precedes_metadata_reservation_and_preserves_ticket() {
        let b = layout_fixture(1400, true);
        let need = 512 + 1400 * 48 + 2 * 24 + 1365 * 48;
        assert!(matches!(
            LayoutReader::new(b.len() as u64, 575),
            Err(PageError::BudgetExceeded { needed: 576, .. })
        ));
        let mut reader = LayoutReader::new(b.len() as u64, need - 1).unwrap();
        let header = reader.ticket().unwrap();
        assert_eq!(
            reader.fulfil(header, &b[..64], 64, || true),
            Err(PageError::BudgetExceeded {
                needed: need,
                budget: need - 1
            })
        );
        assert_eq!(reader.ticket(), Some(header));
        assert_eq!(reader.retained_bytes(), LAYOUT_READER_BYTES);
        let mut reader = LayoutReader::new(b.len() as u64, need).unwrap();
        reader.fulfil(header, &b[..64], 64, || true).unwrap();
        let ticket = reader.ticket().unwrap();
        let before = reader.retained_bytes();
        assert!(matches!(
            reader.fulfil(ticket, ticket_bytes(&b, ticket), need, || true),
            Err(PageError::BudgetExceeded { .. })
        ));
        assert_eq!(reader.ticket(), Some(ticket));
        assert_eq!(reader.retained_bytes(), before);
        assert!(reader.metadata.is_empty());
        assert!(reader.overview.is_empty());
    }
    #[test]
    fn portable_layout_bad_late_records_cancellation_and_stale_tickets_are_atomic() {
        let b = layout_fixture(1400, true);
        let mut reader = LayoutReader::new(b.len() as u64, 1 << 20).unwrap();
        let header = reader.ticket().unwrap();
        reader.fulfil(header, &b[..64], 64, || true).unwrap();
        let ticket = reader.ticket().unwrap();
        let raw = ticket_bytes(&b, ticket);
        for wrong in [
            ReadTicket {
                serial: ticket.serial + 1,
                ..ticket
            },
            ReadTicket {
                offset: ticket.offset + 48,
                ..ticket
            },
            ReadTicket {
                length: ticket.length - 48,
                ..ticket
            },
        ] {
            assert_eq!(
                reader.fulfil(wrong, raw, raw.len() as u64, || true),
                Err(PageError::InvalidRange)
            );
        }
        assert!(matches!(
            reader.fulfil(ticket, &raw[..raw.len() - 1], raw.len() as u64, || true),
            Err(PageError::Corrupt(_))
        ));
        let mut corrupt = raw.to_vec();
        let last = corrupt.len() - 48;
        corrupt[last + 32..last + 40].copy_from_slice(&f64::NAN.to_le_bytes());
        assert!(matches!(
            reader.fulfil(ticket, &corrupt, corrupt.capacity() as u64, || true),
            Err(PageError::Corrupt(_))
        ));
        let mut checks = 0;
        assert_eq!(
            reader.fulfil(ticket, raw, raw.len() as u64, || {
                checks += 1;
                checks < 5
            }),
            Err(PageError::Cancelled)
        );
        let before = reader.retained_bytes();
        let mut checks = 0;
        let panic = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            reader.fulfil(ticket, raw, raw.len() as u64, || {
                checks += 1;
                assert!(checks < 5, "cancel observer");
                true
            })
        }));
        assert!(panic.is_err());
        assert!(reader.metadata.is_empty());
        assert_eq!(reader.retained_bytes(), before);
        assert_eq!(reader.ticket(), Some(ticket));
        reader
            .fulfil(ticket, raw, raw.len() as u64, || true)
            .unwrap();
        assert_eq!(
            reader.fulfil(ticket, raw, raw.len() as u64, || true),
            Err(PageError::InvalidRange)
        );
        let next = reader.ticket().unwrap();
        let raw = ticket_bytes(&b, next);
        reader.fulfil(next, raw, raw.len() as u64, || true).unwrap();
        let overview = reader.ticket().unwrap();
        let raw = ticket_bytes(&b, overview);
        let mut corrupt = raw.to_vec();
        corrupt[24..32].copy_from_slice(&0u64.to_le_bytes());
        assert!(matches!(
            reader.fulfil(overview, &corrupt, corrupt.len() as u64, || true),
            Err(PageError::Corrupt(_))
        ));
        assert!(reader.overview.is_empty());
        assert_eq!(reader.ticket(), Some(overview));
        reader
            .fulfil(overview, raw, raw.len() as u64, || true)
            .unwrap();
        assert_eq!(reader.finish().unwrap().overview[1].row, 1399);
    }

    #[test]
    fn portable_canonical_page_preserves_bits_and_refuses_bad_extent_budget_and_metadata() {
        let nan = f64::from_bits(0x7ff8_0000_0000_4321);
        let values = [(-0., nan), (0., f64::INFINITY), (1., -0.)];
        let raw: Vec<u8> = values
            .iter()
            .flat_map(|(x, y): &(f64, f64)| x.to_le_bytes().into_iter().chain(y.to_le_bytes()))
            .collect();
        let meta = [ChunkMeta {
            row_start: 0,
            row_count: 3,
            x_min: -0.,
            x_max: 1.,
            y_min: -0.,
            y_max: 0.,
        }];
        let budget = 3 * 32 + CANONICAL_PAGE_OVERHEAD;
        let page = decode_canonical_rows(&meta, 3, 0, &raw, 48, budget, || true).unwrap();
        assert_eq!(page.peak_bytes, budget);
        for (i, &(x, y)) in values.iter().enumerate() {
            assert_eq!(page.x[i].to_bits(), x.to_bits());
            assert_eq!(page.y[i].to_bits(), y.to_bits());
        }
        assert!(matches!(
            decode_canonical_rows(&meta, 3, 0, &raw, 48, budget - 1, || true),
            Err(PageError::BudgetExceeded { .. })
        ));
        assert!(matches!(
            decode_canonical_rows(&meta, 3, 0, &raw[..47], 48, budget, || true),
            Err(PageError::Corrupt(_))
        ));
        assert!(matches!(
            decode_canonical_rows(&meta, 3, 0, &raw, 47, budget, || true),
            Err(PageError::Corrupt(_))
        ));
        assert!(matches!(
            decode_canonical_rows(&meta, 3, 1, &raw, 48, budget, || true),
            Err(PageError::InvalidRange)
        ));
        assert!(matches!(
            decode_canonical_rows(&meta, u64::MAX, u64::MAX, &raw, 48, budget, || true),
            Err(PageError::InvalidRange)
        ));
        assert!(matches!(
            decode_canonical_rows(&meta, 3, 0, &raw, u64::MAX, u64::MAX, || true),
            Err(PageError::InvalidRange)
        ));
        assert!(matches!(
            decode_canonical_rows(&meta, 3, 0, &raw, 48, budget, || false),
            Err(PageError::Cancelled)
        ));
        let gap = [
            ChunkMeta {
                row_count: 1,
                ..meta[0]
            },
            ChunkMeta {
                row_start: 2,
                row_count: 1,
                ..meta[0]
            },
        ];
        assert!(matches!(
            decode_canonical_rows(&gap, 3, 0, &raw, 48, budget, || true),
            Err(PageError::Corrupt(_))
        ));
        let empty =
            decode_canonical_rows(&[], 7, 7, &[], 0, CANONICAL_PAGE_OVERHEAD, || true).unwrap();
        assert!(empty.x.is_empty() && empty.y.is_empty());
        assert_eq!(empty.first_row, 7);
    }
}
