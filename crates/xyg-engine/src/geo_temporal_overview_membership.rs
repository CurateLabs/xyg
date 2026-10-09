//! Exact data-domain cell membership, dossier §27/§28.
//! This scans authenticated canonical rows; it never substitutes viewport bins.
use crate::geo_source::{
    FeatureRef, FeatureView, QueryBudget, QueryCursor, QuerySpec, ReadRequest, ScanStats,
    SourceError,
};
use crate::geo_source_membership_driver::{SourceMatcher, SourceMembershipDriver};
use crate::geo_source_session::{
    GeoOperationSnapshot, GeoProcessorLease, GeoReadTicket, GeoSessionStep,
};
use crate::geo_spatial_index::{GeoSpatialOptions, cell};
use crate::geo_temporal_overview::GeoOverviewResult;
use std::sync::Arc;
type Result<T> = std::result::Result<T, SourceError>;
const MAX_VERTICES: u64 = 2_000_000_000;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GeoOverviewMember {
    pub feature: FeatureRef,
    pub matched_vertices: u64,
}
/// Private issuance and owning credit survive cancellation/session drop until ACK.
#[derive(Clone)]
pub struct GeoOverviewMembershipTicket {
    ticket: GeoReadTicket,
    _credit: Arc<GeoProcessorLease>,
}
impl GeoOverviewMembershipTicket {
    pub fn request(&self) -> ReadRequest {
        self.ticket.request
    }
    pub fn owner(&self) -> u64 {
        self.ticket.session_id
    }
    pub fn serial(&self) -> u64 {
        self.ticket.read_id
    }
    pub fn sequence(&self) -> u64 {
        self.ticket.sequence
    }
    pub fn reserved_bytes(&self) -> usize {
        self._credit.bytes()
    }
}
pub enum GeoOverviewMembershipStep {
    NeedRead(GeoOverviewMembershipTicket),
    AwaitRelease(GeoOverviewMembershipTicket),
    Complete,
    Cancelled,
    Disposed,
}
/// Immutable page; continuation authority cannot be made from wire cursor bytes.
/// Records and retained authority are dropped before their processor credit.
pub struct GeoPublishedOverviewMembership {
    result: Arc<GeoOverviewResult>,
    sequence: u64,
    cell: u16,
    records: Vec<GeoOverviewMember>,
    next: Option<QueryCursor>,
    cumulative_vertices: u64,
    stats: ScanStats,
    _credit: GeoProcessorLease,
}
impl GeoPublishedOverviewMembership {
    pub fn records(&self) -> &[GeoOverviewMember] {
        &self.records
    }
    pub fn sequence(&self) -> u64 {
        self.sequence
    }
    pub fn cell(&self) -> u16 {
        self.cell
    }
    pub fn snapshot(&self) -> GeoOperationSnapshot {
        self.result.snapshot()
    }
    pub fn overview_digest(&self) -> [u8; 8] {
        self.result.overview_digest()
    }
    pub fn complete(&self) -> bool {
        self.next.is_none()
    }
    pub fn cumulative_vertices(&self) -> u64 {
        self.cumulative_vertices
    }
    pub fn stats(&self) -> ScanStats {
        self.stats
    }
    pub fn reserved_bytes(&self) -> usize {
        self._credit.bytes() + self.result.retained_bytes()
    }
}
struct Matcher {
    query: QuerySpec,
    cell: u16,
    expected: u64,
    cumulative: u64,
    examined_vertices: u64,
    max_vertices: u64,
}
impl SourceMatcher for Matcher {
    type Record = GeoOverviewMember;
    fn query_spec(&self) -> QuerySpec {
        self.query
    }
    fn matches(
        &mut self,
        f: &FeatureView<'_>,
        request: ReadRequest,
        cancelled: &mut dyn FnMut() -> bool,
    ) -> Result<Option<Self::Record>> {
        // Driver checks this first too: direct matcher calls never touch excluded geometry.
        if !self.query.time.matches(f.interval_start, f.interval_end) {
            return Ok(None);
        }
        let n = f.vertices.len() as u64;
        let work = self
            .examined_vertices
            .checked_add(n)
            .ok_or(SourceError::ResourceLimit)?;
        if work > self.max_vertices {
            return Err(SourceError::ResourceLimit);
        }
        let mut matched = 0u64;
        for xy in f.column.xy()[f.vertices.start * 2..f.vertices.end * 2].chunks_exact(2) {
            if cancelled() {
                return Err(SourceError::Cancelled);
            }
            let c = cell(
                f.column.crs(),
                [xy[0], xy[1]],
                GeoSpatialOptions { grid: 16 },
            );
            if c == u32::MAX {
                return Err(SourceError::InvalidFrame);
            }
            if c == self.cell as u32 {
                matched += 1;
            }
        }
        if cancelled() {
            return Err(SourceError::Cancelled);
        }
        let cumulative = self
            .cumulative
            .checked_add(matched)
            .ok_or(SourceError::ResourceLimit)?;
        if cumulative > self.expected {
            return Err(SourceError::InvalidFrame);
        }
        self.examined_vertices = work;
        self.cumulative = cumulative;
        Ok((matched != 0).then(|| GeoOverviewMember {
            feature: FeatureRef {
                chunk_index: request.chunk_index,
                row: f.row as u32,
                source_row: request.first_row + f.row as u64,
                feature_id: f.column.feature_ids()[f.row],
            },
            matched_vertices: matched,
        }))
    }
    fn finish(&mut self, exhausted: bool) -> Result<()> {
        if exhausted && self.cumulative != self.expected {
            Err(SourceError::InvalidFrame)
        } else {
            Ok(())
        }
    }
}
pub struct GeoOverviewMembershipSession {
    driver: SourceMembershipDriver<Matcher>,
    result: Arc<GeoOverviewResult>,
    cell: u16,
    published: Option<GeoPublishedOverviewMembership>,
    disposed: bool,
    cancelled: bool,
}
impl GeoOverviewMembershipSession {
    pub fn create(
        result: Arc<GeoOverviewResult>,
        cell: u16,
        sequence: u64,
        previous: Option<&GeoPublishedOverviewMembership>,
        budget: QueryBudget,
        max_vertices: u64,
    ) -> Result<Self> {
        if cell >= 256 || max_vertices == 0 || max_vertices > MAX_VERTICES {
            return Err(SourceError::InvalidFrame);
        }
        let (resume, cumulative, previous_bytes) = if let Some(p) = previous {
            if !Arc::ptr_eq(&p.result, &result) || p.cell != cell || sequence <= p.sequence {
                return Err(SourceError::StaleSource);
            }
            (
                Some(p.next.ok_or(SourceError::StaleSource)?),
                p.cumulative_vertices,
                p._credit.bytes(),
            )
        } else {
            (None, 0, 0)
        };
        let matcher = Matcher {
            query: QuerySpec {
                bounds: None,
                time: result.snapshot().time,
            },
            cell,
            expected: result.counts()[cell as usize],
            cumulative,
            examined_vertices: 0,
            max_vertices,
        };
        let retained = result
            .retained_bytes()
            .checked_add(previous_bytes)
            .ok_or(SourceError::ResourceLimit)?;
        let driver = SourceMembershipDriver::create(
            result.source(),
            sequence,
            matcher,
            resume,
            retained,
            budget,
        )?;
        Ok(Self {
            driver,
            result,
            cell,
            published: None,
            disposed: false,
            cancelled: false,
        })
    }
    pub fn published(&self) -> Option<&GeoPublishedOverviewMembership> {
        self.published.as_ref()
    }
    pub fn take_page(&mut self) -> Option<GeoPublishedOverviewMembership> {
        self.published.take()
    }
    pub fn current_sequence(&self) -> u64 {
        self.driver.current_sequence()
    }
    pub fn has_outstanding_reads(&self) -> bool {
        self.driver.has_outstanding_reads()
    }
    fn ticket(&self, ticket: GeoReadTicket) -> Result<GeoOverviewMembershipTicket> {
        Ok(GeoOverviewMembershipTicket {
            ticket,
            _credit: self.driver.read_credit(ticket)?,
        })
    }
    pub fn step(&mut self) -> Result<GeoOverviewMembershipStep> {
        self.step_with_cancel(&mut || false)
    }
    pub fn step_with_cancel(
        &mut self,
        cancelled: &mut dyn FnMut() -> bool,
    ) -> Result<GeoOverviewMembershipStep> {
        if cancelled() {
            self.cancel(self.current_sequence())?;
            return Ok(GeoOverviewMembershipStep::Cancelled);
        }
        let step = self.driver.step()?;
        if matches!(step, GeoSessionStep::Complete) && cancelled() {
            drop(self.driver.take_published());
            self.cancel(self.current_sequence())?;
            return Ok(GeoOverviewMembershipStep::Cancelled);
        }
        if let Some(out) = self.driver.take_published() {
            let p = out.page;
            let features_visited = p.features.len();
            self.published = Some(GeoPublishedOverviewMembership {
                result: Arc::clone(&self.result),
                sequence: self.current_sequence(),
                cell: self.cell,
                records: p.features,
                next: p.next,
                cumulative_vertices: self.driver.matcher().cumulative,
                stats: ScanStats {
                    chunks_considered: p.chunks_considered,
                    chunks_read: p.chunks_read,
                    bytes_read: p.bytes_read,
                    rows_examined: p.rows_examined,
                    features_visited,
                },
                _credit: out.lease,
            });
        }
        Ok(match step {
            GeoSessionStep::NeedRead(t) => GeoOverviewMembershipStep::NeedRead(self.ticket(t)?),
            GeoSessionStep::AwaitRelease(t) => {
                GeoOverviewMembershipStep::AwaitRelease(self.ticket(t)?)
            }
            GeoSessionStep::Complete => GeoOverviewMembershipStep::Complete,
            GeoSessionStep::Disposed => GeoOverviewMembershipStep::Disposed,
            GeoSessionStep::Idle if self.disposed => GeoOverviewMembershipStep::Disposed,
            GeoSessionStep::Idle if self.cancelled => GeoOverviewMembershipStep::Cancelled,
            _ => return Err(SourceError::InvalidFrame),
        })
    }
    pub fn supply(
        &mut self,
        ticket: &GeoOverviewMembershipTicket,
        bytes: &[u8],
        cancelled: &mut dyn FnMut() -> bool,
    ) -> Result<()> {
        let result = self.driver.supply(ticket.ticket, bytes, cancelled);
        if result == Err(SourceError::Cancelled) {
            self.cancelled = true;
        }
        result
    }
    pub fn release_read(&mut self, ticket: &GeoOverviewMembershipTicket) -> Result<()> {
        self.driver.release_read(ticket.ticket)
    }
    pub fn cancel(&mut self, through: u64) -> Result<()> {
        self.driver.cancel(through)?;
        if through >= self.current_sequence() {
            self.cancelled = true;
        }
        Ok(())
    }
    pub fn dispose(&mut self) -> Result<()> {
        self.driver.dispose()?;
        self.published = None;
        self.disposed = true;
        Ok(())
    }
}

#[cfg(test)]
#[path = "geo_temporal_overview_membership_tests.rs"]
mod tests;
