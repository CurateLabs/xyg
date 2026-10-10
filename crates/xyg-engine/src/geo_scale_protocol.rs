//! Host-neutral retained geographic lifecycle framing (#50, §27/§29).
//! Mutations return a fixed 256-byte reply: native hosts never execute a
//! mutation twice to discover output length. Data reads are pure and bind sequence.
#[path = "geo_hierarchy_protocol.rs"]
mod hierarchy;
#[path = "geo_linked_state_protocol.rs"]
mod linked_state;
#[path = "geo_temporal_overview_protocol.rs"]
mod overview;
#[path = "geo_overview_membership_protocol.rs"]
mod overview_members;
#[path = "geo_allocation_recovery.rs"]
mod recovery;
use crate::geo::{GeoCrs, GeoGeometry, column_from_descriptor_bytes};
use crate::geo_indexed_query_session::{
    GeoIndexedQuerySession, GeoIndexedQueryStep, GeoIndexedReadTicket, GeoIndexedResult,
    estimate_work,
};
use crate::geo_layers::GeoStyle;
use crate::geo_lod::{
    GeoCellCursor, GeoLodIdentity, GeoLodKey, GeoLodOptions, GeoPointLod, GeoPointOutput,
    GeoPointResult, GeoReducedKind,
};
use crate::geo_membership_session::{GeoMembershipSession, GeoPublishedMembership};
use crate::geo_rows_session::{GeoPublishedRows, GeoRowsCursor, GeoRowsKey, GeoRowsSession};
use crate::geo_source::{
    GeoChunk, GeoIntervals, GeoManifestBuilder, GeoSourceManifest, MAX_CHUNK_BYTES,
    MAX_MANIFEST_BYTES, MAX_PROCESSOR_BYTES, QueryBudget, QueryCursor, QuerySpec, ReadRequest,
    SourceError, TimePredicate,
};
use crate::geo_source_session::{
    GeoOperationSnapshot, GeoProcessorLease, GeoReadTicket, GeoSessionStep, GeoSourceSession,
};
use crate::geo_spatial_build_session::{
    GeoIndexReadTicket, GeoIndexWriteTicket, GeoSpatialBuildSession, GeoSpatialBuildStep,
};
use crate::geo_spatial_index::{
    GeoSpatialOptions, GeoSpatialRead, PAGE_BYTES, ValidatedGeoSpatialIndex,
};
use crate::geo_tile_cache::{GeoDerivedLease, GeoTileCache, GeoTileLimits};
use crate::geo_viewport::{GeoViewport, GeoViewportRebuildKey};
use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

pub const HEADER: usize = 256;
pub const MAX_HANDLES: usize = 16;
pub const MAX_SESSIONS: usize = 8;
pub const MAX_DATA_HANDLES: usize = 8;
pub const MAX_DATA: usize = 32 * 1024 * 1024;
type Result<T> = std::result::Result<T, SourceError>;
struct GeoSceneSemantic {
    source: GeoSourceManifest,
    result: GeoPointResult,
    style: [u8; 48],
    sequence: u64,
    scope: Option<Arc<linked_state::Scope>>,
    _lease: GeoProcessorLease,
}
struct GeoRowsAuthority {
    source: GeoSourceManifest,
    key: GeoRowsKey,
    cursor: Option<GeoRowsCursor>,
    sequence: u64,
    scope: Option<Arc<linked_state::Scope>>,
    state: Option<Arc<crate::geo_linked_state::GeoLinkedState>>,
    _lease: GeoProcessorLease,
}
struct SourceOwner {
    value: Box<GeoSourceSession>,
    scope: Option<Arc<linked_state::Scope>>,
}
impl std::ops::Deref for SourceOwner {
    type Target = GeoSourceSession;
    fn deref(&self) -> &Self::Target {
        &self.value
    }
}
impl std::ops::DerefMut for SourceOwner {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.value
    }
}
struct RowsOwner {
    value: Box<GeoRowsSession>,
    scope: Option<Arc<linked_state::Scope>>,
}
impl std::ops::Deref for RowsOwner {
    type Target = GeoRowsSession;
    fn deref(&self) -> &Self::Target {
        &self.value
    }
}
impl std::ops::DerefMut for RowsOwner {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.value
    }
}
struct IndexOwner {
    index: Arc<ValidatedGeoSpatialIndex>,
    creation_sequence: u64,
    scope: Mutex<Option<Arc<linked_state::Scope>>>,
    painted: Mutex<(u64, [u8; 48])>,
    transition: Mutex<(u64, GeoOperationSnapshot)>,
    _lease: GeoProcessorLease,
}
struct IndexBuild {
    scope: Option<Arc<linked_state::Scope>>,
    session: Option<GeoSpatialBuildSession>,
    sequence: u64,
    painted: (u64, [u8; 48]),
    snapshot: GeoOperationSnapshot,
    write: Option<(GeoIndexWriteTicket, AtomicU8)>,
    _lease: GeoProcessorLease,
}
struct IndexQuery {
    owner: Arc<IndexOwner>,
    scope: Option<Arc<linked_state::Scope>>,
    selected_replacement: bool,
    session: Option<GeoIndexedQuerySession>,
    published: Option<GeoIndexedResult>,
    sequence: u64,
    snapshot: GeoOperationSnapshot,
    _lease: GeoProcessorLease,
}
enum Entry {
    Hierarchy(hierarchy::Owned),
    Scope(Arc<linked_state::Scope>),
    State(linked_state::State),
    Overview(overview::Owned),
    OverviewMembers(overview_members::Owned),
    Builder {
        value: GeoManifestBuilder,
        _lease: GeoProcessorLease,
    },
    Manifest {
        bytes: Vec<u8>,
        _lease: GeoProcessorLease,
    },
    Session(SourceOwner),
    Members(Box<GeoMembershipSession>),
    Rows(RowsOwner),
    IndexBuild(Box<IndexBuild>),
    Index(Arc<IndexOwner>),
    Indexed(Box<IndexQuery>),
    Data {
        bytes: Vec<u8>,
        _lease: GeoDerivedLease,
        reads: AtomicU8,
        semantic: Option<Arc<GeoSceneSemantic>>,
        rows: Option<Box<GeoRowsAuthority>>,
        overview: Option<Box<overview::Semantic>>,
    },
}
struct Registry {
    recovery: recovery::Bank,
    next: u64,
    entries: Vec<(u64, Entry)>,
    data_cache: Option<GeoTileCache>,
}
static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();
fn registry() -> &'static Mutex<Registry> {
    REGISTRY.get_or_init(|| {
        Mutex::new(Registry {
            recovery: recovery::Bank::default(),
            next: 1,
            entries: Vec::new(),
            data_cache: None,
        })
    })
}
fn u32at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}
fn u64at(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}
fn put32(b: &mut [u8], at: usize, value: u32) {
    b[at..at + 4].copy_from_slice(&value.to_le_bytes());
}
fn put64(b: &mut [u8], at: usize, value: u64) {
    b[at..at + 8].copy_from_slice(&value.to_le_bytes());
}
fn frame(b: &[u8]) -> Result<u32> {
    if b.len() < HEADER
        || &b[..4] != b"XYGQ"
        || u32at(b, 4) != 1
        || u64at(b, 232) != (b.len() - HEADER) as u64
        || b[248..256].iter().any(|&v| v != 0)
        || (u64at(b, 240) != 0 && !matches!(u32at(b, 8), 26..=29 | 35 | 36 | 45 | 47))
        || b.len() > MAX_DATA
        || u32at(b, 204) != 0
    {
        return Err(SourceError::InvalidFrame);
    }
    let command = u32at(b, 8);
    if !matches!(command, 1..=21 | 23..=47) {
        return Err(SourceError::InvalidFrame);
    }
    // Budget words are shared on every operation. Other fields are admitted
    // only where they carry meaning; reserved bits never acquire policy later.
    if b[32..64].iter().any(|&v| v != 0) {
        budget(b)?;
    }
    let zero = |start, end| b[start..end].iter().all(|&v| v == 0);
    if (!matches!(command, 5 | 18 | 28 | 35 | 36 | 38 | 43)
        && (!zero(12, 16) || !zero(64, 144) || !zero(152, 232)))
        || (!matches!(command, 3 | 5 | 18 | 28 | 35 | 36 | 38 | 43) && !zero(144, 152))
        || (!matches!(
            command,
            5 | 6
                | 7
                | 8
                | 9
                | 10
                | 11
                | 12
                | 13
                | 14
                | 15
                | 16
                | 17
                | 18
                | 19
                | 23
                | 24
                | 25
                | 26
                | 27..=47
        ) && !zero(24, 32))
    {
        return Err(SourceError::InvalidFrame);
    }
    Ok(command)
}
fn budget(b: &[u8]) -> Result<QueryBudget> {
    let v = QueryBudget {
        processor_bytes: usize::try_from(u64at(b, 32)).map_err(|_| SourceError::ResourceLimit)?,
        max_rows_examined: u64at(b, 40),
        max_read_bytes: u64at(b, 48),
        max_chunks: u32at(b, 56) as usize,
        page_rows: u32at(b, 60) as usize,
    };
    v.validate()?;
    Ok(v)
}
fn time(b: &[u8]) -> Result<TimePredicate> {
    let t = match u32at(b, 200) {
        0 => {
            if u64at(b, 208) != 0 || u64at(b, 216) != 0 {
                return Err(SourceError::InvalidFrame);
            }
            TimePredicate::All
        }
        1 => {
            if u64at(b, 216) != 0 {
                return Err(SourceError::InvalidFrame);
            }
            TimePredicate::Instant(u64at(b, 208) as i64)
        }
        2 => TimePredicate::Window {
            start: u64at(b, 208) as i64,
            end: u64at(b, 216) as i64,
        },
        _ => return Err(SourceError::InvalidFrame),
    };
    t.validate()?;
    Ok(t)
}
fn camera(b: &[u8]) -> Result<GeoViewport> {
    let crs = GeoCrs::from_u32(u32at(b, 64)).ok_or(SourceError::InvalidFrame)?;
    let f = |at| f64::from_bits(u64at(b, at));
    Ok(GeoViewport::new(
        crs,
        f(80),
        f(88),
        f(96),
        f(104),
        f(112),
        f(120),
        f(128),
        u32at(b, 12) == 1,
    )?)
}
fn ticket(b: &[u8]) -> Result<GeoReadTicket> {
    if b.len() < 96 || b[28..32].iter().any(|&v| v != 0) || b[72..96].iter().any(|&v| v != 0) {
        return Err(SourceError::InvalidFrame);
    }
    Ok(GeoReadTicket {
        session_id: u64at(b, 0),
        read_id: u64at(b, 8),
        sequence: u64at(b, 16),
        pass: u32at(b, 24),
        request: ReadRequest {
            generation: u64at(b, 32),
            chunk_index: u32at(b, 40),
            rows: u32at(b, 44),
            first_row: u64at(b, 48),
            encoded_bytes: usize::try_from(u64at(b, 56)).map_err(|_| SourceError::ResourceLimit)?,
            digest: b[64..72].try_into().unwrap(),
        },
    })
}
fn write_ticket(b: &mut [u8], t: GeoReadTicket) {
    put64(b, 0, t.session_id);
    put64(b, 8, t.read_id);
    put64(b, 16, t.sequence);
    put32(b, 24, t.pass);
    put64(b, 32, t.request.generation);
    put32(b, 40, t.request.chunk_index);
    put32(b, 44, t.request.rows);
    put64(b, 48, t.request.first_row);
    put64(b, 56, t.request.encoded_bytes as u64);
    b[64..72].copy_from_slice(&t.request.digest);
}
fn reply(handle: u64, sequence: u64) -> [u8; HEADER] {
    let mut b = [0; HEADER];
    b[..4].copy_from_slice(b"XYGZ");
    put32(&mut b, 4, 1);
    put64(&mut b, 16, handle);
    put64(&mut b, 24, sequence);
    b
}
fn insert(r: &mut Registry, value: Entry) -> Result<u64> {
    if r.entries.len() == MAX_HANDLES {
        return Err(SourceError::ResourceLimit);
    }
    let id = r.next;
    r.next = r.next.checked_add(1).ok_or(SourceError::ResourceLimit)?;
    r.entries.push((id, value));
    Ok(id)
}
fn session(entry: &mut Entry) -> Result<&mut GeoSourceSession> {
    match entry {
        Entry::Session(s) => Ok(s),
        _ => Err(SourceError::InvalidFrame),
    }
}

/// Fixed-output mutation. Caller must reserve HEADER output bytes before this call.
pub fn execute(request: &[u8]) -> Result<[u8; HEADER]> {
    let command = frame(request)?;
    let mut r = registry().lock().map_err(|_| SourceError::ResourceLimit)?;
    let out = if command == 47 || u64at(request, 240) != 0 {
        recovery::execute(&mut r, request)
    } else {
        execute_locked(&mut r, request)
    };
    recovery::collect(&mut r);
    out
}
fn execute_locked(r: &mut Registry, request: &[u8]) -> Result<[u8; HEADER]> {
    let command = u32at(request, 8);
    let handle = u64at(request, 16);
    let sequence = u64at(request, 24);
    let payload = &request[HEADER..];
    if matches!(
        command,
        1 | 4
            | 11
            | 12
            | 13
            | 14
            | 15
            | 16
            | 17
            | 18
            | 19
            | 26
            | 27
            | 28
            | 29
            | 32
            | 33
            | 34
            | 39
            | 45
    ) && !(command == 33 && sequence != 0)
        && !(command == 29 && u64at(request, 240) != 0)
        && r.entries.len() >= MAX_HANDLES
        && !(command == 19
            && r.entries.iter().any(|(id, e)| {
                *id == handle && matches!(e,Entry::Indexed(q) if q.selected_replacement)
            }))
    {
        return Err(SourceError::ResourceLimit);
    }
    if matches!(command, 45 | 46) {
        return overview_members::start(r, request);
    }
    if matches!(command, 37 | 38 | 42 | 43) {
        return hierarchy::start(r, request);
    }
    if matches!(command, 32..=36) {
        return linked_state::start(r, request);
    }
    if matches!(command, 27..=29) {
        return overview::start(r, request);
    }
    if command == 6 {
        if let Some((_, Entry::Index(owner))) = r.entries.iter().find(|(id, _)| *id == handle) {
            if !payload.is_empty() {
                return Err(SourceError::InvalidFrame);
            }
            if sequence != owner.creation_sequence {
                return Err(SourceError::StaleSource);
            }
            let mut out = reply(handle, sequence);
            put32(&mut out, 8, 11);
            put64(&mut out, 32, owner.index.page_count() as u64);
            return Ok(out);
        }
    }
    if matches!(command, 17 | 18) {
        if r.entries
            .iter()
            .filter(|(_, e)| overview::is_session(e))
            .count()
            >= MAX_SESSIONS
        {
            return Err(SourceError::ResourceLimit);
        }
        let entry = &r
            .entries
            .iter()
            .find(|&&(id, _)| id == handle)
            .ok_or(SourceError::StaleSource)?
            .1;
        if command == 17 {
            if payload.len() != 16 || payload[4..8].iter().any(|&v| v != 0) {
                return Err(SourceError::InvalidFrame);
            }
            let Entry::Data {
                semantic: Some(semantic),
                ..
            } = entry
            else {
                return Err(SourceError::InvalidFrame);
            };
            if sequence == 0 || sequence != semantic.sequence {
                return Err(SourceError::StaleSource);
            }
            let lease = GeoProcessorLease::acquire(4096)?;
            let session = GeoSpatialBuildSession::new(
                &semantic.source,
                GeoSpatialOptions {
                    grid: u32at(payload, 0),
                },
                budget(request)?,
                u64at(payload, 8),
            )?;
            let painted = (semantic.result.key.identity.style_revision, semantic.style);
            let snapshot = data_snapshot(entry)?;
            let scope = semantic.scope.clone();
            let id = insert(
                r,
                Entry::IndexBuild(Box::new(IndexBuild {
                    session: Some(session),
                    scope,
                    sequence,
                    painted,
                    snapshot,
                    write: None,
                    _lease: lease,
                })),
            )?;
            return Ok(reply(id, sequence));
        }
        if !payload.is_empty() || sequence == 0 || u32at(request, 12) > 1 || u32at(request, 76) > 1
        {
            return Err(SourceError::InvalidFrame);
        }
        let Entry::Index(owner) = entry else {
            return Err(SourceError::InvalidFrame);
        };
        let owner = owner.clone();
        if owner
            .scope
            .lock()
            .map_err(|_| SourceError::ResourceLimit)?
            .is_some()
        {
            return Err(SourceError::StaleSource);
        }
        let snapshot = index_snapshot(request)?;
        let mut transition = owner
            .transition
            .lock()
            .map_err(|_| SourceError::ResourceLimit)?;
        if sequence <= transition.0 || snapshot.precedes(transition.1) {
            return Err(SourceError::StaleSource);
        }
        if snapshot.source_digest != owner.index.source().digest()
            || snapshot.generation != owner.index.source().generation()
        {
            return Err(SourceError::StaleSource);
        }
        if snapshot.style_revision
            < owner
                .painted
                .lock()
                .map_err(|_| SourceError::ResourceLimit)?
                .0
        {
            return Err(SourceError::StaleSource);
        }
        let estimate = estimate_work(&owner.index, &camera(request)?, snapshot.time)?;
        let fallback_reason = if estimate.leaf_streams > crate::geo_spatial_index::MAX_FRONTIER {
            1
        } else if estimate.leaf_reads > budget(request)?.max_chunks as u64 {
            2
        } else {
            0
        };
        if fallback_reason != 0 {
            let mut out = reply(handle, sequence);
            put32(&mut out, 8, 10);
            put32(&mut out, 48, fallback_reason);
            return Ok(out);
        }
        let lease = GeoProcessorLease::acquire(4096)?;
        let Some(mut session) = GeoIndexedQuerySession::new(
            owner.index.clone(),
            camera(request)?,
            snapshot.time,
            GeoLodOptions {
                kind: match u32at(request, 68) {
                    0 => GeoReducedKind::Cluster,
                    1 => GeoReducedKind::Density,
                    _ => return Err(SourceError::InvalidFrame),
                },
                previous_direct: u32at(request, 76) == 1,
                max_cells: u32at(request, 72) as usize,
                processor_bytes: budget(request)?.processor_bytes,
                max_projected_vertices: u64at(request, 224),
            },
            snapshot.layer_id,
            snapshot.style_revision,
            snapshot.state_revision,
            budget(request)?.max_read_bytes,
        )?
        else {
            let mut out = reply(handle, sequence);
            put32(&mut out, 8, 10);
            put32(&mut out, 48, 1);
            return Ok(out);
        };
        session.set_work_limits(
            budget(request)?.max_rows_examined,
            budget(request)?.max_chunks as u64,
        )?;
        let id = insert(
            r,
            Entry::Indexed(Box::new(IndexQuery {
                owner: owner.clone(),
                scope: None,
                selected_replacement: false,
                session: Some(session),
                published: None,
                sequence,
                snapshot,
                _lease: lease,
            })),
        )?;
        *transition = (sequence, snapshot);
        return Ok(reply(id, sequence));
    }
    if command == 1 {
        // new source-manifest builder
        if handle != 0 || !payload.is_empty() {
            return Err(SourceError::InvalidFrame);
        }
        let lease = GeoProcessorLease::acquire(MAX_MANIFEST_BYTES)?;
        let id = insert(
            r,
            Entry::Builder {
                value: GeoManifestBuilder::new(),
                _lease: lease,
            },
        )?;
        return Ok(reply(id, 0));
    }
    if command == 4 {
        if r.entries
            .iter()
            .filter(|(_, e)| overview::is_session(e))
            .count()
            >= MAX_SESSIONS
        {
            return Err(SourceError::ResourceLimit);
        }
        // create retained session from untrusted persisted manifest
        if handle != 0 {
            return Err(SourceError::InvalidFrame);
        }
        let s = GeoSourceSession::create(payload, budget(request)?)?;
        let id = insert(
            r,
            Entry::Session(SourceOwner {
                value: Box::new(s),
                scope: None,
            }),
        )?;
        return Ok(reply(id, 0));
    }
    if command == 15 {
        if !payload.is_empty() {
            return Err(SourceError::InvalidFrame);
        }
        if r.entries
            .iter()
            .filter(|(_, e)| overview::is_session(e))
            .count()
            >= MAX_SESSIONS
        {
            return Err(SourceError::ResourceLimit);
        }
        let entry = &r
            .entries
            .iter()
            .find(|&&(id, _)| id == handle)
            .ok_or(SourceError::StaleSource)?
            .1;
        let (source, key, cursor) = row_authority(entry, sequence)?;
        let scope = linked_state::scope(entry);
        let state = match entry {
            Entry::Data {
                semantic: Some(s), ..
            } => s.result.selection.as_ref().map(|s| s.state().clone()),
            Entry::Data { rows: Some(s), .. } => s.state.clone(),
            _ => None,
        };
        let rows = GeoRowsSession::create_with_state(
            source,
            sequence,
            key,
            cursor,
            budget(request)?,
            state,
        )?;
        let id = insert(
            r,
            Entry::Rows(RowsOwner {
                value: Box::new(rows),
                scope,
            }),
        )?;
        return Ok(reply(id, sequence));
    }
    if command == 16 {
        if !payload.is_empty() {
            return Err(SourceError::InvalidFrame);
        }
        let operation_budget = budget(request)?;
        admit_data_slot(r)?;
        let entry = &r
            .entries
            .iter()
            .find(|&&(id, _)| id == handle)
            .ok_or(SourceError::StaleSource)?
            .1;
        let Entry::Rows(rows) = entry else {
            return Err(SourceError::InvalidFrame);
        };
        let published = rows.published().ok_or(SourceError::StaleSource)?;
        if published.sequence != sequence {
            return Err(SourceError::StaleSource);
        }
        let source = rows.source().ok_or(SourceError::StaleSource)?;
        let semantic_bytes = source
            .clone_reserved_bytes()
            .checked_add(std::mem::size_of::<GeoRowsAuthority>())
            .ok_or(SourceError::ResourceLimit)?;
        // Original serialized storage, two transfer copies, typed host page and
        // framing scratch all remain charged while the Data authority is live.
        let selection_bytes = published
            .state
            .as_ref()
            .map(|s| linked_state::footer_bytes(s, &[]))
            .transpose()?
            .unwrap_or(0);
        let reserve = published
            .page
            .records
            .len()
            .checked_mul(2048)
            .and_then(|n| n.checked_add(8192))
            .and_then(|n| {
                selection_bytes
                    .checked_mul(4)
                    .and_then(|s| n.checked_add(s))
            })
            .ok_or(SourceError::ResourceLimit)?;
        if reserve
            .checked_add(semantic_bytes)
            .is_none_or(|n| n > operation_budget.processor_bytes)
        {
            return Err(SourceError::ResourceLimit);
        }
        let semantic_lease = GeoProcessorLease::acquire(semantic_bytes)?;
        let authority = Box::new(GeoRowsAuthority {
            source: source.clone_validated(),
            key: published.key,
            cursor: published.page.next.clone(),
            scope: rows.scope.clone(),
            state: published.state.clone(),
            sequence,
            _lease: semantic_lease,
        });
        let lease = reserve_data(r, reserve)?;
        let entry = &r.entries.iter().find(|&&(id, _)| id == handle).unwrap().1;
        let Entry::Rows(rows) = entry else {
            unreachable!()
        };
        let bytes = render_rows(rows.published().unwrap(), handle)?;
        let len = bytes.len();
        let id = insert(
            r,
            Entry::Data {
                bytes,
                _lease: lease,
                reads: AtomicU8::new(0),
                semantic: None,
                rows: Some(authority),
                overview: None,
            },
        )?;
        let mut out = reply(id, sequence);
        put64(&mut out, 32, len as u64);
        put64(&mut out, 40, handle);
        return Ok(out);
    }
    if command == 12 {
        if r.entries
            .iter()
            .filter(|(_, e)| overview::is_session(e))
            .count()
            >= MAX_SESSIONS
        {
            return Err(SourceError::ResourceLimit);
        }
        if payload.len() < 16
            || u32at(payload, 4) > 1
            || payload.len() != 16 + (u32at(payload, 4) as usize) * MEMBER_CURSOR_BYTES
        {
            return Err(SourceError::InvalidFrame);
        }
        let entry = &r
            .entries
            .iter()
            .find(|&&(id, _)| id == handle)
            .ok_or(SourceError::StaleSource)?
            .1;
        let (source, result) = semantic_authority(entry, sequence)?;
        let cursor = if u32at(payload, 4) == 1 {
            Some(read_member_cursor(&payload[16..])?)
        } else {
            None
        };
        let member = GeoMembershipSession::create(
            source,
            sequence,
            result.key,
            u32at(payload, 0),
            cursor,
            budget(request)?,
            u64at(payload, 8),
        )?;
        let id = insert(r, Entry::Members(Box::new(member)))?;
        return Ok(reply(id, sequence));
    }
    if command == 14 {
        if payload.len() != 80 {
            return Err(SourceError::InvalidFrame);
        }
        let style = read_uniform_style(&payload[..48])?;
        let query = crate::geo_lod_hit::GeoLodHitQuery {
            x: f64::from_bits(u64at(payload, 48)),
            y: f64::from_bits(u64at(payload, 56)),
            tolerance: f64::from_bits(u64at(payload, 64)),
            mode: match u32at(payload, 72) {
                0 => crate::geo_lod_hit::GeoLodHitMode::Topmost,
                1 => crate::geo_lod_hit::GeoLodHitMode::All,
                _ => return Err(SourceError::InvalidFrame),
            },
            max_hits: u32at(payload, 76) as usize,
        };
        crate::geo_lod_hit::reservation_bytes(query)?;
        admit_data_slot(r)?;
        let entry = &r
            .entries
            .iter()
            .find(|&&(id, _)| id == handle)
            .ok_or(SourceError::StaleSource)?
            .1;
        semantic_authority(entry, sequence)?;
        let style_bytes: &[u8; 48] = payload[..48].try_into().unwrap();
        match entry {
            Entry::Session(source) => source.validate_painted_style(style_bytes, true)?,
            Entry::Data {
                semantic: Some(snapshot),
                ..
            } if snapshot.style == *style_bytes => {}
            _ => return Err(SourceError::StaleSource),
        }
        let reserve = query
            .max_hits
            .checked_mul(512)
            .and_then(|n| n.checked_add(8192))
            .ok_or(SourceError::ResourceLimit)?;
        let processor_bytes = budget(request)?.processor_bytes;
        if reserve > processor_bytes {
            return Err(SourceError::ResourceLimit);
        }
        let lease = reserve_data(r, reserve)?;
        let entry = &r.entries.iter().find(|&&(id, _)| id == handle).unwrap().1;
        let (_, result) = semantic_authority(entry, sequence)?;
        let hits = match crate::geo_lod_hit::hit(result, style, query, processor_bytes) {
            Ok(hits) => hits,
            Err(error) => {
                drop(lease);
                if !r.entries.iter().any(|(_, e)| is_data_entry(e)) {
                    r.data_cache = None;
                }
                return Err(error);
            }
        };
        let mut bytes = vec![0; HEADER + hits.hits.len() * 48];
        bytes[..HEADER].copy_from_slice(&reply(handle, sequence));
        put32(&mut bytes, 8, 3);
        put64(&mut bytes, 32, hits.hits.len() as u64);
        put32(&mut bytes, 40, u32at(payload, 72));
        put32(&mut bytes, 44, query.max_hits as u32);
        for at in [48, 56, 64] {
            put64(&mut bytes, at, u64at(payload, at));
        }
        put64(&mut bytes, 80, handle);
        write_member_key(&mut bytes[88..248], hits.key);
        for (i, hit) in hits.hits.iter().enumerate() {
            let at = HEADER + i * 48;
            match hit {
                crate::geo_lod_hit::GeoLodHit::Direct(p) => {
                    put32(&mut bytes, at + 4, p.vertex);
                    put64(&mut bytes, at + 8, p.identity.feature_id);
                    put64(&mut bytes, at + 16, p.identity.source_row);
                    put32(&mut bytes, at + 24, p.identity.chunk_index);
                    put32(&mut bytes, at + 28, p.identity.row);
                }
                crate::geo_lod_hit::GeoLodHit::Cell { ordinal, count } => {
                    put32(&mut bytes, at, 1);
                    put32(&mut bytes, at + 32, *ordinal);
                    put64(&mut bytes, at + 40, *count);
                }
            }
        }
        let len = bytes.len();
        let id = insert(
            r,
            Entry::Data {
                bytes,
                _lease: lease,
                reads: AtomicU8::new(0),
                semantic: None,
                rows: None,
                overview: None,
            },
        )?;
        let mut out = reply(id, sequence);
        put64(&mut out, 32, len as u64);
        put64(&mut out, 40, handle);
        return Ok(out);
    }
    if command == 13 {
        if !payload.is_empty() {
            return Err(SourceError::InvalidFrame);
        }
        admit_data_slot(r)?;
        let entry = &r
            .entries
            .iter()
            .find(|&&(id, _)| id == handle)
            .ok_or(SourceError::StaleSource)?
            .1;
        let Entry::Members(s) = entry else {
            return Err(SourceError::InvalidFrame);
        };
        let published = s.published().ok_or(SourceError::StaleSource)?;
        if published.sequence != sequence {
            return Err(SourceError::StaleSource);
        }
        let reserve = published
            .membership
            .page
            .features
            .len()
            .checked_mul(256)
            .and_then(|n| n.checked_add(8192))
            .ok_or(SourceError::ResourceLimit)?;
        if reserve > budget(request)?.processor_bytes {
            return Err(SourceError::ResourceLimit);
        }
        let lease = reserve_data(r, reserve)?;
        let entry = &r.entries.iter().find(|&&(id, _)| id == handle).unwrap().1;
        let Entry::Members(s) = entry else {
            unreachable!()
        };
        let bytes = render_members(s.published().unwrap(), handle);
        let len = bytes.len();
        let id = insert(
            r,
            Entry::Data {
                bytes,
                _lease: lease,
                reads: AtomicU8::new(0),
                semantic: None,
                rows: None,
                overview: None,
            },
        )?;
        let mut out = reply(id, sequence);
        put64(&mut out, 32, len as u64);
        put64(&mut out, 40, handle);
        return Ok(out);
    }
    // Duplicate only trusted immutable SceneData. Its canonical semantic
    // authority and existing CPU lease are shared; each packet/copy allowance
    // is separately admitted under the derived ledger (§27/§29).
    if command == 26 {
        if !payload.is_empty() {
            return Err(SourceError::InvalidFrame);
        }
        admit_data_slot(r)?;
        let entry = &r
            .entries
            .iter()
            .find(|(id, _)| *id == handle)
            .ok_or(SourceError::StaleSource)?
            .1;
        if let Entry::Data {
            bytes,
            overview: Some(authority),
            ..
        } = entry
        {
            if sequence == 0 || sequence != authority.sequence {
                return Err(SourceError::StaleSource);
            }
            let reserve = crate::geo_temporal_overview_scene::DATA_CREDIT;
            if reserve > budget(request)?.processor_bytes {
                return Err(SourceError::ResourceLimit);
            }
            let len = bytes.len();
            let result = Arc::clone(&authority.result);
            let camera = authority.camera;
            let sequence = authority.sequence;
            let lease = reserve_data(r, reserve)?;
            let authority = Box::new(overview::Semantic {
                result,
                camera,
                sequence,
            });
            let Entry::Data { bytes, .. } =
                &r.entries.iter().find(|(id, _)| *id == handle).unwrap().1
            else {
                unreachable!()
            };
            let mut bytes = bytes.clone();
            put64(&mut bytes, 16, handle);
            let id = insert(
                r,
                Entry::Data {
                    bytes,
                    _lease: lease,
                    reads: AtomicU8::new(0),
                    semantic: None,
                    rows: None,
                    overview: Some(authority),
                },
            )?;
            let mut out = reply(id, sequence);
            put64(&mut out, 32, len as u64);
            put64(&mut out, 40, handle);
            return Ok(out);
        }
        let Entry::Data {
            bytes,
            semantic: Some(authority),
            ..
        } = entry
        else {
            return Err(SourceError::InvalidFrame);
        };
        if sequence != authority.sequence {
            return Err(SourceError::StaleSource);
        }
        let len = bytes.len();
        let reserve = len
            .checked_mul(4)
            .and_then(|n| n.checked_add(std::mem::size_of::<Entry>() + 256))
            .ok_or(SourceError::ResourceLimit)?;
        if reserve > budget(request)?.processor_bytes {
            return Err(SourceError::ResourceLimit);
        }
        let authority = Arc::clone(authority);
        let lease = reserve_data(r, reserve)?;
        let Entry::Data { bytes, .. } = &r.entries.iter().find(|(id, _)| *id == handle).unwrap().1
        else {
            unreachable!()
        };
        let mut bytes = bytes.clone();
        // New packet addresses the prior immutable Data owner, never a
        // disposed query session. Every numeric/Scene/provenance byte survives.
        put64(&mut bytes, 16, handle);
        let id = insert(
            r,
            Entry::Data {
                bytes,
                _lease: lease,
                reads: AtomicU8::new(0),
                semantic: Some(authority),
                rows: None,
                overview: None,
            },
        )?;
        let mut out = reply(id, sequence);
        put64(&mut out, 32, len as u64);
        put64(&mut out, 40, handle);
        return Ok(out);
    }
    if matches!(command, 11 | 19 | 39 | 44) {
        admit_data_slot(r)?;
        let entry = &r
            .entries
            .iter()
            .find(|&&(id, _)| id == handle)
            .ok_or(SourceError::StaleSource)?
            .1;
        if (command == 11 && !matches!(entry, Entry::Session(_)))
            || (command == 19 && !matches!(entry, Entry::Indexed(_)))
            || (matches!(command, 39 | 44) && !matches!(entry, Entry::Hierarchy(_)))
        {
            return Err(SourceError::InvalidFrame);
        }
        if command == 44 && !hierarchy::selected_complete(entry) {
            return Err(SourceError::InvalidFrame);
        }
        let phase_budget = if matches!(command, 39 | 44) {
            hierarchy::data_budget(entry, budget(request)?.processor_bytes)?
        } else {
            budget(request)?.processor_bytes
        };
        let (source, result) = semantic_authority(entry, sequence)?;
        read_uniform_style(payload)?;
        let style_bytes: [u8; 48] = payload.try_into().map_err(|_| SourceError::InvalidFrame)?;
        validate_entry_style(entry, &style_bytes)?;
        let count = match &result.output {
            GeoPointOutput::Direct(v) => v.len(),
            GeoPointOutput::Reduced(v) => v.len(),
        };
        let unit = if !result.key.direct && result.key.kind == GeoReducedKind::Density {
            256
        } else {
            1024
        };
        let selection_bytes = result
            .selection
            .as_ref()
            .map(|s| linked_state::footer_bytes(s.state(), s.selected_counts()))
            .transpose()?
            .unwrap_or(0);
        let reserve = count
            .checked_mul(unit)
            .and_then(|n| n.checked_add(8192))
            .and_then(|n| {
                selection_bytes
                    .checked_mul(4)
                    .and_then(|s| n.checked_add(s))
            })
            .ok_or(SourceError::ResourceLimit)?;
        if reserve > phase_budget {
            return Err(SourceError::ResourceLimit);
        }

        let semantic_bytes = source
            .clone_reserved_bytes()
            .checked_add(GeoPointLod::output_bytes(result))
            .and_then(|n| {
                n.checked_add(
                    std::mem::size_of::<GeoSceneSemantic>() + 2 * std::mem::size_of::<usize>(),
                )
            })
            .ok_or(SourceError::ResourceLimit)?;
        if semantic_bytes
            .checked_add(reserve)
            .is_none_or(|n| n > phase_budget)
        {
            return Err(SourceError::ResourceLimit);
        }
        let semantic_lease = GeoProcessorLease::acquire(semantic_bytes)?;

        let semantic = Arc::new(GeoSceneSemantic {
            source: source.clone_validated(),
            result: GeoPointResult {
                key: result.key,
                output: match &result.output {
                    GeoPointOutput::Direct(v) => GeoPointOutput::Direct(v.clone()),
                    GeoPointOutput::Reduced(v) => GeoPointOutput::Reduced(v.clone()),
                },
                visible_vertices: result.visible_vertices,
                projected_vertices: result.projected_vertices,
                grid_capped: result.grid_capped,
                selection: result.selection.clone(),
            },
            style: style_bytes,
            scope: linked_state::scope(entry),
            sequence,
            _lease: semantic_lease,
        });
        let lease = reserve_data(r, reserve)?;
        let entry = &r
            .entries
            .iter()
            .find(|&&(id, _)| id == handle)
            .ok_or(SourceError::StaleSource)?
            .1;
        let bytes = match render_entry(
            entry,
            request,
            if matches!(command, 39 | 44) {
                phase_budget
                    .checked_sub(semantic_bytes)
                    .ok_or(SourceError::ResourceLimit)?
            } else {
                phase_budget
            },
        ) {
            Ok(bytes) => bytes,
            Err(error) => {
                drop(lease);
                if !r.entries.iter().any(|(_, e)| is_data_entry(e)) {
                    r.data_cache = None;
                }
                return Err(error);
            }
        };
        let len = bytes.len();
        let position = r.entries.iter().position(|(id, _)| *id == handle).unwrap();
        let replacement = command == 44
            || matches!(&r.entries[position].1,Entry::Indexed(q) if q.selected_replacement);
        commit_entry_style(&mut r.entries[position].1, style_bytes)?;
        let data = Entry::Data {
            bytes,
            _lease: lease,
            reads: AtomicU8::new(0),
            semantic: Some(semantic),
            rows: None,
            overview: None,
        };
        let id = if replacement {
            r.entries[position].1 = data;
            handle
        } else {
            insert(r, data)?
        };
        let mut out = reply(id, sequence);
        put64(&mut out, 32, len as u64);
        put64(&mut out, 40, handle);
        return Ok(out);
    }
    let index = r
        .entries
        .iter()
        .position(|&(id, _)| id == handle)
        .ok_or(SourceError::StaleSource)?;
    if matches!(command, 7 | 8 | 10)
        && sequence != 0
        && !matches!(
            r.entries[index].1,
            Entry::Overview(_) | Entry::Hierarchy(_) | Entry::OverviewMembers(_)
        )
    {
        return Err(SourceError::InvalidFrame);
    }
    if matches!(r.entries[index].1, Entry::IndexBuild(_) | Entry::Indexed(_))
        && matches!(command, 6..=10 | 24)
    {
        return execute_index_operation(r, index, request);
    }
    if matches!(r.entries[index].1, Entry::OverviewMembers(_)) {
        return overview_members::operation(r, index, request);
    }
    if matches!(r.entries[index].1, Entry::Hierarchy(_)) {
        return hierarchy::operation(r, index, request);
    }
    if matches!(r.entries[index].1, Entry::Overview(_)) {
        return overview::operation(r, index, request);
    }
    let entry = &mut r.entries[index].1;
    let mut out = reply(handle, sequence);
    match command {
        2 => {
            // builder push: chunk authenticated by shared parser
            if payload.len() > MAX_CHUNK_BYTES {
                return Err(SourceError::ResourceLimit);
            }
            let _scratch = GeoProcessorLease::acquire(
                payload
                    .len()
                    .checked_mul(6)
                    .and_then(|n| n.checked_add(32768))
                    .ok_or(SourceError::ResourceLimit)?,
            )?;
            let c = GeoChunk::parse(
                payload,
                _scratch.bytes().min(crate::geo_source::MAX_CHUNK_PEAK),
            )?;
            let Entry::Builder { value, .. } = entry else {
                return Err(SourceError::InvalidFrame);
            };
            value.push(&c)?;
        }
        3 => {
            // finish builder once; pure data command21 reads resulting manifest
            if !payload.is_empty() || u64at(request, 144) == 0 {
                return Err(SourceError::InvalidFrame);
            }
            let Entry::Builder { value, _lease } = entry else {
                return Err(SourceError::InvalidFrame);
            };
            let _candidate = GeoProcessorLease::acquire(MAX_MANIFEST_BYTES)?;
            let manifest = value.clone().finish(u64at(request, 144))?;
            let bytes = manifest.encode()?;
            let n = bytes
                .capacity()
                .checked_mul(3)
                .and_then(|n| n.checked_add(8192))
                .ok_or(SourceError::ResourceLimit)?;
            _lease.resize(n)?;
            let lease = std::mem::replace(_lease, GeoProcessorLease::acquire(0)?);
            *entry = Entry::Manifest {
                bytes,
                _lease: lease,
            };
        }
        5 => {
            if matches!(entry,Entry::Session(s) if s.scope.is_some()) {
                return Err(SourceError::StaleSource);
            }
            // begin one time-first camera/layer operation
            if !payload.is_empty() || u32at(request, 12) > 1 || u32at(request, 76) > 1 {
                return Err(SourceError::InvalidFrame);
            }
            let camera = camera(request)?;
            let time = time(request)?;
            let snapshot = GeoOperationSnapshot {
                source_digest: request[136..144].try_into().unwrap(),
                generation: u64at(request, 144),
                camera: camera.rebuild_key()?,
                time,
                camera_revision: u64at(request, 160),
                time_revision: u64at(request, 168),
                layer_id: u64at(request, 152),
                layer_revision: u64at(request, 176),
                style_revision: u64at(request, 184),
                state_revision: u64at(request, 192),
            };
            let kind = match u32at(request, 68) {
                0 => GeoReducedKind::Cluster,
                1 => GeoReducedKind::Density,
                _ => return Err(SourceError::InvalidFrame),
            };
            session(entry)?.begin(
                sequence,
                snapshot,
                camera,
                QuerySpec { bounds: None, time },
                GeoLodOptions {
                    kind,
                    previous_direct: u32at(request, 76) == 1,
                    max_cells: u32at(request, 72) as usize,
                    processor_bytes: budget(request)?.processor_bytes,
                    max_projected_vertices: u64at(request, 224),
                },
            )?;
        }
        6 => {
            // step: no host I/O occurs in Rust
            if !payload.is_empty() {
                return Err(SourceError::InvalidFrame);
            }
            let step = match entry {
                Entry::Session(s) => {
                    if sequence != s.current_sequence() {
                        return Err(SourceError::StaleSource);
                    }
                    s.step()?
                }
                Entry::Members(s) => {
                    if sequence != s.current_sequence() {
                        return Err(SourceError::StaleSource);
                    }
                    s.step()?
                }
                Entry::Rows(s) => {
                    if sequence != s.current_sequence() {
                        return Err(SourceError::StaleSource);
                    }
                    s.step()?
                }
                _ => return Err(SourceError::InvalidFrame),
            };
            let code = match step {
                GeoSessionStep::NeedRead(t) => {
                    write_ticket(&mut out[64..160], t);
                    1
                }
                GeoSessionStep::AwaitRelease(t) => {
                    write_ticket(&mut out[64..160], t);
                    2
                }
                GeoSessionStep::SourceReady => 3,
                GeoSessionStep::Complete => 4,
                GeoSessionStep::Idle => 5,
                GeoSessionStep::Disposed => 6,
            };
            put32(&mut out, 8, code);
            if let Entry::Session(s) = entry {
                if let Some(source) = s.source() {
                    put64(&mut out, 32, source.generation());
                    out[40..48].copy_from_slice(&source.digest());
                    put64(&mut out, 48, source.rows());
                    put32(&mut out, 56, source.geometry() as u32);
                    put32(&mut out, 60, source.crs() as u32);
                }
            }
            if let Entry::Members(s) = entry {
                let key = s.key();
                put64(&mut out, 32, key.identity.generation);
                out[40..48].copy_from_slice(&key.identity.source_digest);
                put64(&mut out, 48, key.identity.source_rows);
                put32(&mut out, 56, key.identity.geometry as u32);
                put32(&mut out, 60, key.identity.crs as u32);
                if let Some(p) = s.published() {
                    put64(&mut out, 160, p.membership.page.features.len() as u64);
                    put32(&mut out, 168, u32::from(p.membership.next.is_some()));
                    put32(&mut out, 172, p.cell);
                }
            }
            if let Entry::Rows(s) = entry {
                let key = s.key();
                put64(&mut out, 32, key.generation);
                out[40..48].copy_from_slice(&key.source_digest);
                put64(&mut out, 48, key.source_rows);
                put32(&mut out, 56, key.geometry as u32);
                put32(&mut out, 60, key.crs as u32);
                if let Some(p) = s.published() {
                    put64(&mut out, 160, p.page.records.len() as u64);
                    put32(&mut out, 168, u32::from(p.page.next.is_some()));
                }
            }
        }
        7 => {
            if payload.len() < 96 {
                return Err(SourceError::InvalidFrame);
            }
            let t = ticket(payload)?;
            match entry {
                Entry::Session(s) => s.supply(t, &payload[96..], &mut || false)?,
                Entry::Members(s) => s.supply(t, &payload[96..], &mut || false)?,
                Entry::Rows(s) => s.supply(t, &payload[96..], &mut || false)?,
                _ => return Err(SourceError::InvalidFrame),
            }
        }
        8 => {
            if payload.len() != 96 {
                return Err(SourceError::InvalidFrame);
            }
            let t = ticket(payload)?;
            match entry {
                Entry::Session(s) => s.release_read(t)?,
                Entry::Members(s) => s.release_read(t)?,
                Entry::Rows(s) => s.release_read(t)?,
                _ => return Err(SourceError::InvalidFrame),
            }
        }
        9 => {
            if !payload.is_empty() {
                return Err(SourceError::InvalidFrame);
            }
            match entry {
                Entry::Session(s) => s.cancel(sequence)?,
                Entry::Members(s) => s.cancel(sequence)?,
                Entry::Rows(s) => s.cancel(sequence)?,
                _ => return Err(SourceError::InvalidFrame),
            }
        }
        10 => {
            // dispose session; keep its retired read charges until acknowledgements
            if !payload.is_empty() {
                return Err(SourceError::InvalidFrame);
            }
            if let Entry::Session(s) = entry {
                s.dispose()?;
                if s.has_outstanding_reads() {
                    put32(&mut out, 8, 2);
                    return Ok(out);
                }
            }
            if let Entry::Members(s) = entry {
                s.dispose()?;
                if s.has_outstanding_reads() {
                    put32(&mut out, 8, 2);
                    return Ok(out);
                }
            }
            if let Entry::Rows(s) = entry {
                s.dispose()?;
                if s.has_outstanding_reads() {
                    put32(&mut out, 8, 2);
                    return Ok(out);
                }
            }
            if matches!(entry,Entry::Scope(s) if Arc::strong_count(s)>1) {
                return Err(SourceError::ResourceLimit);
            }
            r.entries.remove(index);
            if !r.entries.iter().any(|(_, e)| is_data_entry(e)) {
                r.data_cache = None;
            }
        }
        _ => return Err(SourceError::InvalidFrame),
    }
    Ok(out)
}

// Publication-only check shared by every immutable Data producer. Keep one
// body in the constrained WASM artifact; this is outside row/vertex hot loops.
#[inline(never)]
fn is_data_entry(e: &Entry) -> bool {
    matches!(e, Entry::Data { .. }) || matches!(e,Entry::OverviewMembers(o) if o.is_data())
}
#[inline(never)]
fn admit_data_slot(r: &Registry) -> Result<()> {
    if r.entries.iter().filter(|(_, e)| is_data_entry(e)).count() >= MAX_DATA_HANDLES {
        return Err(SourceError::ResourceLimit);
    }
    Ok(())
}

/// Pure bounded authoring/read operation. Native two-call length discovery is safe.
/// Commands20/21/23 encode a canonical chunk/read a finished manifest/read an
/// immutable leased Scene or membership packet. Publication sequence cannot change silently.
pub fn read_data(request: &[u8], budget: usize) -> Result<Vec<u8>> {
    let command = frame(request)?;
    if budget > MAX_PROCESSOR_BYTES || request.len() > budget {
        return Err(SourceError::ResourceLimit);
    }
    let payload = &request[HEADER..];
    if command == 20 {
        return encode_chunk(payload, budget);
    }
    let r = registry().lock().map_err(|_| SourceError::ResourceLimit)?;
    let entry = &r
        .entries
        .iter()
        .find(|&&(id, _)| id == u64at(request, 16))
        .ok_or(SourceError::StaleSource)?
        .1;
    if command == 40 {
        let (bytes, reads) = hierarchy::write_bytes(entry, request, budget)?;
        reads
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |n| {
                (n < 2).then_some(n + 1)
            })
            .map_err(|_| SourceError::ResourceLimit)?;
        return Ok(bytes.to_vec());
    }
    if command == 30 {
        let (bytes, reads) = overview::write_bytes(entry, request, budget)?;
        reads
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |n| {
                (n < 2).then_some(n + 1)
            })
            .map_err(|_| SourceError::ResourceLimit)?;
        return Ok(bytes.to_vec());
    }
    if command == 25 {
        let (bytes, reads) = index_write_bytes(entry, request, budget)?;
        reads
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |n| {
                (n < 2).then_some(n + 1)
            })
            .map_err(|_| SourceError::ResourceLimit)?;
        return Ok(bytes.to_vec());
    }
    if command == 21 {
        if !payload.is_empty() {
            return Err(SourceError::InvalidFrame);
        }
        let Entry::Manifest { bytes, .. } = entry else {
            return Err(SourceError::InvalidFrame);
        };
        if bytes.len().checked_mul(3).is_none_or(|n| n > budget) {
            return Err(SourceError::ResourceLimit);
        }
        return Ok(bytes.clone());
    }
    if command == 23 && matches!(entry, Entry::OverviewMembers(_)) {
        let (bytes, reads) = overview_members::read_bytes(entry, request, budget)?;
        reads
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |n| {
                (n < 2).then_some(n + 1)
            })
            .map_err(|_| SourceError::ResourceLimit)?;
        return Ok(bytes.to_vec());
    }
    if command == 23 {
        if u64at(request, 24) != 0
            && !matches!(
                entry,
                Entry::Data {
                    overview: Some(_),
                    ..
                }
            )
        {
            return Err(SourceError::InvalidFrame);
        }
        if let Entry::Data {
            overview: Some(s), ..
        } = entry
        {
            if u64at(request, 24) != s.sequence {
                return Err(SourceError::StaleSource);
            }
        }
        if !payload.is_empty() {
            return Err(SourceError::InvalidFrame);
        }
        let Entry::Data { bytes, reads, .. } = entry else {
            return Err(SourceError::InvalidFrame);
        };
        if bytes.len().checked_mul(4).is_none_or(|n| n > budget) {
            return Err(SourceError::ResourceLimit);
        }
        reads
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |n| {
                (n < 2).then_some(n + 1)
            })
            .map_err(|_| SourceError::ResourceLimit)?;
        return Ok(bytes.clone());
    }
    Err(SourceError::InvalidFrame)
}

/// Size discovery never consumes a retained transfer-copy slot.
pub fn data_len(request: &[u8], budget: usize) -> Result<usize> {
    let command = frame(request)?;
    if budget > MAX_PROCESSOR_BYTES || request.len() > budget {
        return Err(SourceError::ResourceLimit);
    }
    if command == 20 {
        return Ok(encode_chunk(&request[HEADER..], budget)?.len());
    }
    if !matches!(command, 21 | 23 | 25 | 30 | 40)
        || (!matches!(command, 25 | 30 | 40) && request.len() != HEADER)
    {
        return Err(SourceError::InvalidFrame);
    }
    let r = registry().lock().map_err(|_| SourceError::ResourceLimit)?;
    let entry = &r
        .entries
        .iter()
        .find(|&&(id, _)| id == u64at(request, 16))
        .ok_or(SourceError::StaleSource)?
        .1;
    if command == 40 {
        return Ok(hierarchy::write_bytes(entry, request, budget)?.0.len());
    }
    if command == 30 {
        return Ok(overview::write_bytes(entry, request, budget)?.0.len());
    }
    if command == 25 {
        return Ok(index_write_bytes(entry, request, budget)?.0.len());
    }
    if command == 23 && matches!(entry, Entry::OverviewMembers(_)) {
        return Ok(overview_members::read_bytes(entry, request, budget)?
            .0
            .len());
    }
    if command == 23 {
        if u64at(request, 24) != 0
            && !matches!(
                entry,
                Entry::Data {
                    overview: Some(_),
                    ..
                }
            )
        {
            return Err(SourceError::InvalidFrame);
        }
        if let Entry::Data {
            overview: Some(s), ..
        } = entry
        {
            if u64at(request, 24) != s.sequence {
                return Err(SourceError::StaleSource);
            }
        }
    }
    let (bytes, copies) = match (command, entry) {
        (21, Entry::Manifest { bytes, .. }) => (bytes, 3),
        (23, Entry::Data { bytes, .. }) => (bytes, 4),
        _ => return Err(SourceError::InvalidFrame),
    };
    if bytes.len().checked_mul(copies).is_none_or(|n| n > budget) {
        return Err(SourceError::ResourceLimit);
    }
    Ok(bytes.len())
}

fn render_entry(entry: &Entry, request: &[u8], budget: usize) -> Result<Vec<u8>> {
    let payload = &request[HEADER..];
    if payload.len() != 48 {
        return Err(SourceError::InvalidFrame);
    }
    let (result, snapshot, sequence) = match entry {
        Entry::Session(s) => {
            let p = s.published().ok_or(SourceError::StaleSource)?;
            (&p.result, p.snapshot, p.sequence)
        }
        Entry::Indexed(q) => (
            &q.published.as_ref().ok_or(SourceError::StaleSource)?.result,
            q.snapshot,
            q.sequence,
        ),
        Entry::Hierarchy(_) => {
            let (_, result, snapshot) = hierarchy::authority(entry, u64at(request, 24))?;
            (result, snapshot, u64at(request, 24))
        }
        _ => return Err(SourceError::InvalidFrame),
    };
    if sequence != u64at(request, 24) {
        return Err(SourceError::StaleSource);
    }
    let style = read_uniform_style(payload)?;
    let scene = crate::geo_lod_scene::compile(result, style, budget)?;
    let metadata = match &result.output {
        GeoPointOutput::Direct(v) => v.len() * 40,
        GeoPointOutput::Reduced(v) => v.len() * 24,
    };
    let footer = result
        .selection
        .as_ref()
        .map(|s| {
            s.validate_result(result)?;
            linked_state::footer_bytes(s.state(), s.selected_counts())
        })
        .transpose()?
        .unwrap_or(0);
    let total = HEADER
        .checked_add(scene.scene.len())
        .and_then(|n| n.checked_add(metadata))
        .and_then(|n| n.checked_add(footer))
        .ok_or(SourceError::ResourceLimit)?;
    if total > MAX_DATA || total.checked_mul(4).is_none_or(|n| n > budget) {
        return Err(SourceError::ResourceLimit);
    }
    let mut out = reply(u64at(request, 16), sequence).to_vec();
    put32(&mut out, 8, if scene.aggregate { 1 } else { 0 });
    put32(&mut out, 12, scene.dropped_channels);
    put64(&mut out, 32, scene.scene.len() as u64);
    put64(&mut out, 40, metadata as u64);
    put64(&mut out, 48, result.visible_vertices);
    put64(&mut out, 56, result.projected_vertices);
    put32(&mut out, 64, result.key.columns);
    put32(&mut out, 68, result.key.rows);
    put32(&mut out, 72, if result.grid_capped { 1 } else { 0 });
    put32(&mut out, 80, snapshot.camera.crs as u32);
    put32(&mut out, 84, if snapshot.camera.world_wrap { 1 } else { 0 });
    for (index, bits) in [
        snapshot.camera.center_x_bits,
        snapshot.camera.center_y_bits,
        snapshot.camera.zoom_bits,
        snapshot.camera.width_bits,
        snapshot.camera.height_bits,
        snapshot.camera.bearing_deg_bits,
        snapshot.camera.pitch_deg_bits,
    ]
    .into_iter()
    .enumerate()
    {
        put64(&mut out, 88 + index * 8, bits);
    }
    out[144..152].copy_from_slice(&snapshot.source_digest);
    put64(&mut out, 152, snapshot.generation);
    put64(&mut out, 160, snapshot.layer_id);
    put64(&mut out, 168, snapshot.camera_revision);
    put64(&mut out, 176, snapshot.time_revision);
    put64(&mut out, 184, snapshot.layer_revision);
    put64(&mut out, 192, snapshot.style_revision);
    put64(&mut out, 200, snapshot.state_revision);
    match snapshot.time {
        TimePredicate::All => {}
        TimePredicate::Instant(t) => {
            put32(&mut out, 208, 1);
            put64(&mut out, 216, t as u64);
        }
        TimePredicate::Window { start, end } => {
            put32(&mut out, 208, 2);
            put64(&mut out, 216, start as u64);
            put64(&mut out, 224, end as u64);
        }
    }
    put32(
        &mut out,
        212,
        if result.key.kind == GeoReducedKind::Cluster {
            0
        } else {
            1
        },
    );
    put64(&mut out, 232, result.key.identity.source_rows);
    put32(&mut out, 240, result.key.identity.geometry as u32);
    put32(&mut out, 244, result.key.identity.crs as u32);
    out.extend(scene.scene);
    match &result.output {
        GeoPointOutput::Direct(points) => {
            for p in points {
                out.extend(p.identity.feature_id.to_le_bytes());
                out.extend(p.identity.source_row.to_le_bytes());
                out.extend(p.identity.chunk_index.to_le_bytes());
                out.extend(p.identity.row.to_le_bytes());
                out.extend(p.vertex.to_le_bytes());
                out.extend(0u32.to_le_bytes());
                out.extend(0u64.to_le_bytes());
            }
        }
        GeoPointOutput::Reduced(cells) => {
            for cell in cells {
                out.extend(cell.count.to_le_bytes());
                out.extend(cell.x.to_le_bytes());
                out.extend(cell.y.to_le_bytes());
            }
        }
    }
    if let Some(selection) = &result.selection {
        linked_state::append_footer(
            &mut out,
            selection.state(),
            selection.selected_counts(),
            Some(selection.visible_selected_vertices()),
            result.key.identity,
        )?;
    }
    Ok(out)
}

fn encode_chunk(b: &[u8], budget: usize) -> Result<Vec<u8>> {
    if b.len() < 32
        || b.len() > MAX_CHUNK_BYTES
        || b[12..16].iter().any(|&v| v != 0)
        || b[24..32].iter().any(|&v| v != 0)
    {
        return Err(SourceError::InvalidFrame);
    }
    let len = usize::try_from(u64at(b, 0)).map_err(|_| SourceError::ResourceLimit)?;
    let rows = usize::try_from(u64at(b, 16)).map_err(|_| SourceError::ResourceLimit)?;
    let flags = u32at(b, 8);
    if flags > 3 || rows > crate::geo_source::MAX_CHUNK_ROWS {
        return Err(SourceError::InvalidFrame);
    }
    let expected = 32usize
        .checked_add(len)
        .and_then(|n| {
            rows.checked_mul(if flags & 1 != 0 { 18 } else { 0 })
                .and_then(|t| n.checked_add(t))
        })
        .and_then(|n| {
            rows.checked_mul(if flags & 2 != 0 { 8 } else { 0 })
                .and_then(|t| n.checked_add(t))
        })
        .ok_or(SourceError::ResourceLimit)?;
    if expected != b.len()
        || b.len()
            .checked_mul(6)
            .and_then(|n| n.checked_add(32768))
            .is_none_or(|n| n > budget)
    {
        return Err(SourceError::ResourceLimit);
    }
    let _lease = GeoProcessorLease::acquire(b.len() * 6 + 32768)?;
    let column = column_from_descriptor_bytes(&b[32..32 + len], _lease.bytes())?;
    if column.len() != rows {
        return Err(SourceError::InvalidFrame);
    }
    let mut at = 32 + len;
    let mut starts = Vec::new();
    let mut ends = Vec::new();
    let mut sv = &[][..];
    let mut ev = &[][..];
    if flags & 1 != 0 {
        starts = b[at..at + rows * 8]
            .chunks_exact(8)
            .map(|v| i64::from_le_bytes(v.try_into().unwrap()))
            .collect();
        at += rows * 8;
        ends = b[at..at + rows * 8]
            .chunks_exact(8)
            .map(|v| i64::from_le_bytes(v.try_into().unwrap()))
            .collect();
        at += rows * 8;
        sv = &b[at..at + rows];
        at += rows;
        ev = &b[at..at + rows];
        at += rows;
    }
    let values: Vec<f64> = if flags & 2 != 0 {
        b[at..]
            .chunks_exact(8)
            .map(|v| f64::from_le_bytes(v.try_into().unwrap()))
            .collect()
    } else {
        Vec::new()
    };
    GeoChunk::encode_with_values(
        &column,
        if flags & 1 != 0 {
            Some(GeoIntervals {
                starts: &starts,
                ends: &ends,
                start_validity: sv,
                end_validity: ev,
            })
        } else {
            None
        },
        if flags & 2 != 0 { Some(&values) } else { None },
    )
}

const MEMBER_KEY_BYTES: usize = 160;
const MEMBER_CURSOR_BYTES: usize = 208;
fn reserve_data(registry: &mut Registry, bytes: usize) -> Result<GeoDerivedLease> {
    if registry.data_cache.is_none() {
        registry.data_cache = Some(GeoTileCache::new(GeoTileLimits::default(), 0)?);
    }
    match registry.data_cache.as_ref().unwrap().reserve_derived(bytes) {
        Ok(lease) => Ok(lease),
        Err(error) => {
            // A rejected first snapshot must not retain an empty cache's fixed
            // process charge. Existing successful data retains its owner cache.
            if !registry.entries.iter().any(|(_, e)| is_data_entry(e)) {
                registry.data_cache = None;
            }
            Err(error.into())
        }
    }
}
fn write_member_key(b: &mut [u8], key: GeoLodKey) {
    b[..8].copy_from_slice(&key.identity.source_digest);
    for (at, n) in [
        (8, key.identity.generation),
        (16, key.identity.source_rows),
        (32, key.identity.layer_id),
        (40, key.identity.style_revision),
        (48, key.identity.state_revision),
    ] {
        put64(b, at, n);
    }
    put32(b, 24, key.identity.crs as u32);
    put32(b, 28, key.identity.geometry as u32);
    put32(b, 56, key.camera.crs as u32);
    put32(b, 60, u32::from(key.camera.world_wrap));
    for (i, n) in [
        key.camera.center_x_bits,
        key.camera.center_y_bits,
        key.camera.zoom_bits,
        key.camera.width_bits,
        key.camera.height_bits,
        key.camera.bearing_deg_bits,
        key.camera.pitch_deg_bits,
    ]
    .into_iter()
    .enumerate()
    {
        put64(b, 64 + i * 8, n);
    }
    match key.time {
        TimePredicate::All => {}
        TimePredicate::Instant(t) => {
            put32(b, 120, 1);
            put64(b, 128, t as u64);
        }
        TimePredicate::Window { start, end } => {
            put32(b, 120, 2);
            put64(b, 128, start as u64);
            put64(b, 136, end as u64);
        }
    }
    put32(
        b,
        124,
        if key.kind == GeoReducedKind::Cluster {
            0
        } else {
            1
        },
    );
    put32(b, 144, u32::from(key.direct));
    put32(b, 148, key.columns);
    put32(b, 152, key.rows);
}
fn read_member_cursor(b: &[u8]) -> Result<GeoCellCursor> {
    if b.len() != MEMBER_CURSOR_BYTES
        || b[156..160]
            .iter()
            .chain(&b[164..168])
            .chain(&b[200..208])
            .any(|&v| v != 0)
        || u32at(b, 60) > 1
        || u32at(b, 144) > 1
    {
        return Err(SourceError::InvalidFrame);
    }
    let crs = |at| GeoCrs::from_u32(u32at(b, at)).ok_or(SourceError::InvalidFrame);
    let time = match u32at(b, 120) {
        0 if u64at(b, 128) == 0 && u64at(b, 136) == 0 => TimePredicate::All,
        1 if u64at(b, 136) == 0 => TimePredicate::Instant(u64at(b, 128) as i64),
        2 => TimePredicate::Window {
            start: u64at(b, 128) as i64,
            end: u64at(b, 136) as i64,
        },
        _ => return Err(SourceError::InvalidFrame),
    };
    time.validate()?;
    let key = GeoLodKey {
        identity: GeoLodIdentity {
            source_digest: b[..8].try_into().unwrap(),
            generation: u64at(b, 8),
            source_rows: u64at(b, 16),
            crs: crs(24)?,
            geometry: GeoGeometry::from_u32(u32at(b, 28)).ok_or(SourceError::InvalidFrame)?,
            layer_id: u64at(b, 32),
            style_revision: u64at(b, 40),
            state_revision: u64at(b, 48),
        },
        camera: GeoViewportRebuildKey {
            crs: crs(56)?,
            world_wrap: u32at(b, 60) == 1,
            center_x_bits: u64at(b, 64),
            center_y_bits: u64at(b, 72),
            zoom_bits: u64at(b, 80),
            width_bits: u64at(b, 88),
            height_bits: u64at(b, 96),
            bearing_deg_bits: u64at(b, 104),
            pitch_deg_bits: u64at(b, 112),
        },
        time,
        kind: match u32at(b, 124) {
            0 => GeoReducedKind::Cluster,
            1 => GeoReducedKind::Density,
            _ => return Err(SourceError::InvalidFrame),
        },
        direct: u32at(b, 144) == 1,
        columns: u32at(b, 148),
        rows: u32at(b, 152),
    };
    Ok(GeoCellCursor {
        key,
        cell: u32at(b, 160),
        source: QueryCursor {
            generation: u64at(b, 168),
            source_digest: b[176..184].try_into().unwrap(),
            query_digest: b[184..192].try_into().unwrap(),
            chunk_index: u32at(b, 192),
            row: u32at(b, 196),
        },
    })
}
fn write_member_cursor(b: &mut [u8], cursor: GeoCellCursor) {
    write_member_key(&mut b[..MEMBER_KEY_BYTES], cursor.key);
    put32(b, 160, cursor.cell);
    put64(b, 168, cursor.source.generation);
    b[176..184].copy_from_slice(&cursor.source.source_digest);
    b[184..192].copy_from_slice(&cursor.source.query_digest);
    put32(b, 192, cursor.source.chunk_index);
    put32(b, 196, cursor.source.row);
}
fn render_members(published: &GeoPublishedMembership, owner: u64) -> Vec<u8> {
    let members = &published.membership;
    let cursor_bytes = if members.next.is_some() {
        MEMBER_CURSOR_BYTES
    } else {
        0
    };
    let mut out = vec![0; HEADER + cursor_bytes + members.page.features.len() * 32];
    out[..HEADER].copy_from_slice(&reply(owner, published.sequence));
    put32(&mut out, 8, 2);
    put32(&mut out, 12, published.cell);
    put64(&mut out, 32, members.page.features.len() as u64);
    put64(&mut out, 40, members.projected_vertices);
    put64(&mut out, 48, members.page.rows_examined);
    put64(&mut out, 56, members.page.bytes_read);
    put32(&mut out, 64, members.page.chunks_read as u32);
    put32(&mut out, 68, members.page.chunks_considered as u32);
    put32(&mut out, 72, u32::from(members.next.is_some()));
    put32(&mut out, 76, cursor_bytes as u32);
    put64(&mut out, 80, owner);
    write_member_key(&mut out[88..248], published.key);
    if let Some(cursor) = members.next {
        write_member_cursor(&mut out[HEADER..HEADER + cursor_bytes], cursor);
    }
    for (i, f) in members.page.features.iter().enumerate() {
        let at = HEADER + cursor_bytes + i * 32;
        put64(&mut out, at, f.feature_id);
        put64(&mut out, at + 8, f.source_row);
        put32(&mut out, at + 16, f.chunk_index);
        put32(&mut out, at + 20, f.row);
    }
    out
}

fn row_authority(
    entry: &Entry,
    sequence: u64,
) -> Result<(&GeoSourceManifest, GeoRowsKey, Option<GeoRowsCursor>)> {
    match entry {
        Entry::Data {
            rows: Some(authority),
            overview: None,
            ..
        } => {
            if sequence != authority.sequence {
                return Err(SourceError::StaleSource);
            }
            let cursor = authority.cursor.clone().ok_or(SourceError::InvalidFrame)?;
            Ok((&authority.source, authority.key, Some(cursor)))
        }
        Entry::Data {
            bytes,
            semantic: Some(authority),
            ..
        } => {
            if sequence != authority.sequence {
                return Err(SourceError::StaleSource);
            }
            let identity = authority.result.key.identity;
            Ok((
                &authority.source,
                GeoRowsKey {
                    source_digest: identity.source_digest,
                    generation: identity.generation,
                    source_rows: identity.source_rows,
                    geometry: identity.geometry,
                    crs: identity.crs,
                    layer_id: identity.layer_id,
                    layer_revision: u64at(bytes, 184),
                    state_revision: identity.state_revision,
                    time_revision: u64at(bytes, 176),
                    time: authority.result.key.time,
                },
                None,
            ))
        }
        _ => Err(SourceError::InvalidFrame),
    }
}

fn render_rows(published: &GeoPublishedRows, owner: u64) -> Result<Vec<u8>> {
    let page = &published.page;
    let key = published.key;
    let mut out = vec![0; HEADER + page.records.len() * 64];
    out[..HEADER].copy_from_slice(&reply(owner, published.sequence));
    put32(&mut out, 8, 4);
    put64(&mut out, 32, page.records.len() as u64);
    put32(&mut out, 40, u32::from(page.next.is_some()));
    put64(&mut out, 48, page.rows_examined);
    put64(&mut out, 56, page.bytes_read);
    put32(&mut out, 64, page.chunks_read as u32);
    put32(&mut out, 68, page.chunks_considered as u32);
    put64(&mut out, 80, owner);
    out[88..96].copy_from_slice(&key.source_digest);
    put64(&mut out, 96, key.generation);
    put64(&mut out, 104, key.source_rows);
    put32(&mut out, 112, key.geometry as u32);
    put32(&mut out, 116, key.crs as u32);
    put64(&mut out, 120, key.layer_id);
    put64(&mut out, 128, key.layer_revision);
    put64(&mut out, 136, key.state_revision);
    put64(&mut out, 144, key.time_revision);
    match key.time {
        TimePredicate::All => {}
        TimePredicate::Instant(t) => {
            put32(&mut out, 152, 1);
            put64(&mut out, 160, t as u64);
        }
        TimePredicate::Window { start, end } => {
            put32(&mut out, 152, 2);
            put64(&mut out, 160, start as u64);
            put64(&mut out, 168, end as u64);
        }
    }
    for (i, row) in page.records.iter().enumerate() {
        let at = HEADER + i * 64;
        put64(&mut out, at, row.feature.feature_id);
        put64(&mut out, at + 8, row.feature.source_row);
        put32(&mut out, at + 16, row.feature.chunk_index);
        put32(&mut out, at + 20, row.feature.row);
        let flags = u32::from(row.geometry_null)
            | (u32::from(row.time_eligible) << 1)
            | (u32::from(row.eligible) << 2)
            | (u32::from(row.intervals_present) << 3)
            | (u32::from(row.interval_start.is_some()) << 4)
            | (u32::from(row.interval_end.is_some()) << 5)
            | (u32::from(row.value.is_some()) << 6)
            | (u32::from(row.selected) << 7);
        put32(&mut out, at + 24, flags);
        put64(&mut out, at + 32, row.interval_start.unwrap_or(0) as u64);
        put64(&mut out, at + 40, row.interval_end.unwrap_or(0) as u64);
        put64(&mut out, at + 48, row.value.map_or(0, f64::to_bits));
    }
    if let Some(state) = &published.state {
        linked_state::append_footer(
            &mut out,
            state,
            &[],
            None,
            GeoLodIdentity {
                source_digest: key.source_digest,
                generation: key.generation,
                source_rows: key.source_rows,
                geometry: key.geometry,
                crs: key.crs,
                layer_id: key.layer_id,
                style_revision: 0,
                state_revision: key.state_revision,
            },
        )?;
    }
    Ok(out)
}

#[cfg(test)]
#[path = "geo_membership_protocol_tests.rs"]
mod membership_protocol_tests;

fn read_uniform_style(payload: &[u8]) -> Result<GeoStyle> {
    if payload.len() != 48 {
        return Err(SourceError::InvalidFrame);
    }
    if payload[33..48].iter().any(|&v| v != 0) {
        return Err(SourceError::InvalidFrame);
    }
    Ok(GeoStyle {
        fill: payload[..4].try_into().unwrap(),
        stroke: payload[4..8].try_into().unwrap(),
        stroke_width: f64::from_bits(u64at(payload, 8)),
        diameter: f64::from_bits(u64at(payload, 16)),
        opacity: f64::from_bits(u64at(payload, 24)),
        symbol: payload[32],
    })
}

fn semantic_authority(
    entry: &Entry,
    sequence: u64,
) -> Result<(&GeoSourceManifest, &GeoPointResult)> {
    match entry {
        Entry::Hierarchy(_) => {
            let (source, result, _) = hierarchy::authority(entry, sequence)?;
            Ok((source, result))
        }
        Entry::Session(s) => {
            let p = s.published().ok_or(SourceError::StaleSource)?;
            if p.sequence != sequence {
                return Err(SourceError::StaleSource);
            }
            Ok((s.source().ok_or(SourceError::StaleSource)?, &p.result))
        }
        Entry::Indexed(q) if q.sequence == sequence => Ok((
            q.owner.index.source(),
            &q.published.as_ref().ok_or(SourceError::StaleSource)?.result,
        )),
        Entry::Indexed(_) => Err(SourceError::StaleSource),
        Entry::Data {
            semantic: Some(s), ..
        } if s.sequence == sequence => Ok((&s.source, &s.result)),
        Entry::Data {
            semantic: Some(_), ..
        } => Err(SourceError::StaleSource),
        _ => Err(SourceError::InvalidFrame),
    }
}

/// Read-only immutable painted-frame authority for frozen export. The registry
/// mutex remains held throughout the callback: it MUST NOT reenter this registry.
/// Snapshot callers acquire their own registry before this lock and never call
/// source operations from the callback. All references end before the lock drops.
pub struct GeoSceneDataBorrow<'a> {
    pub scene: &'a [u8],
    pub source: &'a GeoSourceManifest,
    pub result: &'a GeoPointResult,
    pub style: &'a [u8; 48],
    pub snapshot: GeoOperationSnapshot,
}
pub fn with_scene_data<T>(
    handle: u64,
    sequence: u64,
    callback: impl FnOnce(GeoSceneDataBorrow<'_>) -> T,
) -> Result<T> {
    let r = registry().lock().map_err(|_| SourceError::ResourceLimit)?;
    let entry = &r
        .entries
        .iter()
        .find(|&&(id, _)| id == handle)
        .ok_or(SourceError::StaleSource)?
        .1;
    let Entry::Data {
        bytes,
        semantic: Some(value),
        ..
    } = entry
    else {
        return Err(SourceError::StaleSource);
    };
    if sequence == 0 || sequence != value.sequence {
        return Err(SourceError::StaleSource);
    }
    let snapshot = data_snapshot(entry)?;
    let scene_len = usize::try_from(u64at(bytes, 32)).map_err(|_| SourceError::ResourceLimit)?;
    let scene = bytes
        .get(
            HEADER
                ..HEADER
                    .checked_add(scene_len)
                    .ok_or(SourceError::ResourceLimit)?,
        )
        .ok_or(SourceError::InvalidFrame)?;
    Ok(callback(GeoSceneDataBorrow {
        scene,
        source: &value.source,
        result: &value.result,
        style: &value.style,
        snapshot,
    }))
}

fn index_snapshot(request: &[u8]) -> Result<GeoOperationSnapshot> {
    Ok(GeoOperationSnapshot {
        source_digest: request[136..144].try_into().unwrap(),
        generation: u64at(request, 144),
        camera: camera(request)?.rebuild_key()?,
        time: time(request)?,
        camera_revision: u64at(request, 160),
        time_revision: u64at(request, 168),
        layer_id: u64at(request, 152),
        layer_revision: u64at(request, 176),
        style_revision: u64at(request, 184),
        state_revision: u64at(request, 192),
    })
}
fn validate_entry_style(entry: &Entry, style: &[u8; 48]) -> Result<()> {
    match entry {
        Entry::Hierarchy(_) => hierarchy::validate_style(entry, style),
        Entry::Session(s) => s.validate_painted_style(style, false),
        Entry::Indexed(q) => {
            if q.owner
                .transition
                .lock()
                .map_err(|_| SourceError::ResourceLimit)?
                .0
                != q.sequence
            {
                return Err(SourceError::StaleSource);
            }
            let painted = q
                .owner
                .painted
                .lock()
                .map_err(|_| SourceError::ResourceLimit)?;
            if q.snapshot.style_revision < painted.0
                || (q.snapshot.style_revision == painted.0 && *style != painted.1)
            {
                return Err(SourceError::StaleSource);
            }
            Ok(())
        }
        _ => Err(SourceError::InvalidFrame),
    }
}
fn commit_entry_style(entry: &mut Entry, style: [u8; 48]) -> Result<()> {
    match entry {
        Entry::Hierarchy(_) => hierarchy::commit_style(entry, style)?,
        Entry::Session(s) => s.commit_painted_style(style),
        Entry::Indexed(q) => {
            *q.owner
                .painted
                .lock()
                .map_err(|_| SourceError::ResourceLimit)? = (q.snapshot.style_revision, style)
        }
        _ => return Err(SourceError::InvalidFrame),
    }
    Ok(())
}
fn write_index_source_ticket(bytes: &mut [u8], ticket: GeoIndexReadTicket, sequence: u64) {
    write_ticket(
        bytes,
        GeoReadTicket {
            session_id: ticket.session,
            read_id: ticket.request.chunk_index as u64,
            sequence,
            pass: 0,
            request: ticket.request,
        },
    );
    put32(bytes, 28, 1);
}
fn write_index_leaf_ticket(
    bytes: &mut [u8],
    session: u64,
    sequence: u64,
    pass: u32,
    kind: u32,
    request: GeoSpatialRead,
) {
    put64(bytes, 0, session);
    put64(bytes, 8, request.page);
    put64(bytes, 16, sequence);
    put32(bytes, 24, pass);
    put32(bytes, 28, kind);
    put64(bytes, 56, request.encoded_bytes as u64);
    bytes[64..72].copy_from_slice(&request.digest);
}
fn index_ticket_frame(bytes: &[u8], sequence: u64, kind: u32) -> Result<()> {
    if bytes.len() < 96
        || u64at(bytes, 16) != sequence
        || u32at(bytes, 28) != kind
        || bytes[72..96].iter().any(|&v| v != 0)
    {
        return Err(SourceError::StaleSource);
    }
    Ok(())
}
fn index_source_ticket(bytes: &[u8], sequence: u64) -> Result<GeoIndexReadTicket> {
    index_ticket_frame(bytes, sequence, 1)?;
    if u32at(bytes, 24) != 0 || u64at(bytes, 8) != u32at(bytes, 40) as u64 {
        return Err(SourceError::InvalidFrame);
    }
    Ok(GeoIndexReadTicket {
        session: u64at(bytes, 0),
        request: ReadRequest {
            generation: u64at(bytes, 32),
            chunk_index: u32at(bytes, 40),
            rows: u32at(bytes, 44),
            first_row: u64at(bytes, 48),
            encoded_bytes: usize::try_from(u64at(bytes, 56))
                .map_err(|_| SourceError::ResourceLimit)?,
            digest: bytes[64..72].try_into().unwrap(),
        },
    })
}
fn index_leaf_ticket(bytes: &[u8], sequence: u64, kind: u32) -> Result<(u64, u32, GeoSpatialRead)> {
    index_ticket_frame(bytes, sequence, kind)?;
    if bytes[32..56].iter().any(|&v| v != 0) {
        return Err(SourceError::InvalidFrame);
    }
    Ok((
        u64at(bytes, 0),
        u32at(bytes, 24),
        GeoSpatialRead {
            page: u64at(bytes, 8),
            encoded_bytes: usize::try_from(u64at(bytes, 56))
                .map_err(|_| SourceError::ResourceLimit)?,
            digest: bytes[64..72].try_into().unwrap(),
        },
    ))
}
fn index_write_ticket(bytes: &[u8], sequence: u64) -> Result<GeoIndexWriteTicket> {
    let (session, pass, request) = index_leaf_ticket(bytes, sequence, 3)?;
    if pass != 0 {
        return Err(SourceError::InvalidFrame);
    }
    Ok(GeoIndexWriteTicket { session, request })
}
fn execute_index_operation(r: &mut Registry, index: usize, request: &[u8]) -> Result<[u8; HEADER]> {
    let command = u32at(request, 8);
    let handle = u64at(request, 16);
    let sequence = u64at(request, 24);
    let payload = &request[HEADER..];
    let entry = &mut r.entries[index].1;
    let mut out = reply(handle, sequence);
    match entry {
        Entry::IndexBuild(build) => {
            if matches!(command, 6 | 9 | 24) && sequence != build.sequence {
                return Err(SourceError::StaleSource);
            }
            let s = build.session.as_mut().ok_or(SourceError::StaleSource)?;
            match command {
                6 => {
                    if !payload.is_empty() {
                        return Err(SourceError::InvalidFrame);
                    }
                    let state = s.step()?;
                    match state {
                        GeoSpatialBuildStep::NeedRead(t) => {
                            put32(&mut out, 8, 1);
                            write_index_source_ticket(&mut out[64..160], t, build.sequence);
                        }
                        GeoSpatialBuildStep::AwaitReadRelease(t) => {
                            put32(&mut out, 8, 2);
                            write_index_source_ticket(&mut out[64..160], t, build.sequence);
                        }
                        GeoSpatialBuildStep::NeedWrite(t)
                        | GeoSpatialBuildStep::AwaitWriteRelease(t) => {
                            if build.write.as_ref().is_none_or(|(old, _)| *old != t) {
                                build.write = Some((t, AtomicU8::new(0)));
                            }
                            put32(
                                &mut out,
                                8,
                                if matches!(state, GeoSpatialBuildStep::NeedWrite(_)) {
                                    7
                                } else {
                                    8
                                },
                            );
                            write_index_leaf_ticket(
                                &mut out[64..160],
                                t.session,
                                build.sequence,
                                0,
                                3,
                                t.request,
                            );
                        }
                        GeoSpatialBuildStep::Complete => {
                            let validated = Arc::new(s.finish()?);
                            let pages = validated.page_count();
                            let lease = std::mem::replace(
                                &mut build._lease,
                                GeoProcessorLease::acquire(0)?,
                            );
                            let painted = build.painted;
                            let transition = (build.sequence, build.snapshot);
                            *entry = Entry::Index(Arc::new(IndexOwner {
                                index: validated,
                                creation_sequence: transition.0,
                                scope: Mutex::new(build.scope.clone()),
                                painted: Mutex::new(painted),
                                transition: Mutex::new(transition),
                                _lease: lease,
                            }));
                            put32(&mut out, 8, 11);
                            put64(&mut out, 32, pages as u64);
                        }
                        GeoSpatialBuildStep::Cancelled => put32(&mut out, 8, 9),
                    }
                }
                7 => {
                    let t = index_source_ticket(payload, build.sequence)?;
                    s.supply(t, &payload[96..], &mut || false)?;
                }
                8 => {
                    if payload.len() != 96 {
                        return Err(SourceError::InvalidFrame);
                    }
                    s.release_read(index_source_ticket(payload, build.sequence)?)?;
                }
                24 => {
                    if payload.len() != 96 {
                        return Err(SourceError::InvalidFrame);
                    }
                    s.acknowledge_write(index_write_ticket(payload, build.sequence)?)?;
                    build.write = None;
                }
                9 => {
                    if !payload.is_empty() {
                        return Err(SourceError::InvalidFrame);
                    }
                    s.cancel();
                }
                10 => {
                    if !payload.is_empty() {
                        return Err(SourceError::InvalidFrame);
                    }
                    s.cancel();
                    if s.has_outstanding_io() {
                        put32(&mut out, 8, 2);
                        return Ok(out);
                    }
                    r.entries.remove(index);
                }
                _ => return Err(SourceError::InvalidFrame),
            }
        }
        Entry::Indexed(query) => {
            if command == 6
                && query
                    .owner
                    .transition
                    .lock()
                    .map_err(|_| SourceError::ResourceLimit)?
                    .0
                    != query.sequence
            {
                return Err(SourceError::StaleSource);
            }
            if matches!(command, 6 | 9) && sequence != query.sequence {
                return Err(SourceError::StaleSource);
            }
            match command {
                6 => {
                    if !payload.is_empty() {
                        return Err(SourceError::InvalidFrame);
                    }
                    if query.published.is_none() {
                        let s = query.session.as_mut().ok_or(SourceError::StaleSource)?;
                        let state = s.step()?;
                        match state {
                            GeoIndexedQueryStep::NeedRead(t)
                            | GeoIndexedQueryStep::AwaitRelease(t) => {
                                put32(
                                    &mut out,
                                    8,
                                    if matches!(state, GeoIndexedQueryStep::NeedRead(_)) {
                                        1
                                    } else {
                                        2
                                    },
                                );
                                write_index_leaf_ticket(
                                    &mut out[64..160],
                                    t.session,
                                    query.sequence,
                                    t.pass,
                                    2,
                                    t.request,
                                );
                            }
                            GeoIndexedQueryStep::Complete => {
                                query.published = Some(s.finish()?);
                                query.session = None;
                                put32(&mut out, 8, 12);
                            }
                            GeoIndexedQueryStep::Cancelled => put32(&mut out, 8, 9),
                        }
                    }
                    if let Some(p) = &query.published {
                        put32(&mut out, 8, 12);
                        put64(&mut out, 160, p.stats.pages_read);
                        put64(&mut out, 168, p.stats.bytes_read);
                        put64(&mut out, 176, p.stats.candidate_vertices);
                        put32(&mut out, 184, p.stats.passes);
                    }
                }
                7 | 8 => {
                    if command == 8 && payload.len() != 96 {
                        return Err(SourceError::InvalidFrame);
                    }
                    let (session, pass, request) = index_leaf_ticket(payload, query.sequence, 2)?;
                    let t = GeoIndexedReadTicket {
                        session,
                        pass,
                        request,
                    };
                    let s = query.session.as_mut().ok_or(SourceError::StaleSource)?;
                    if command == 7 {
                        s.supply(t, &payload[96..], &mut || false)?;
                    } else {
                        s.release_read(t)?;
                    }
                }
                9 => {
                    if !payload.is_empty() {
                        return Err(SourceError::InvalidFrame);
                    }
                    if let Some(s) = &mut query.session {
                        s.cancel();
                    }
                    query.published = None;
                }
                10 => {
                    if !payload.is_empty() {
                        return Err(SourceError::InvalidFrame);
                    }
                    if let Some(s) = &mut query.session {
                        s.cancel();
                        if s.has_outstanding_io() {
                            put32(&mut out, 8, 2);
                            return Ok(out);
                        }
                    }
                    r.entries.remove(index);
                }
                _ => return Err(SourceError::InvalidFrame),
            }
        }
        _ => return Err(SourceError::InvalidFrame),
    }
    Ok(out)
}
fn index_write_bytes<'a>(
    entry: &'a Entry,
    request: &[u8],
    budget: usize,
) -> Result<(&'a [u8], &'a AtomicU8)> {
    let Entry::IndexBuild(build) = entry else {
        return Err(SourceError::InvalidFrame);
    };
    if request.len() != HEADER + 96 || u64at(request, 24) != build.sequence {
        return Err(SourceError::StaleSource);
    }
    let ticket = index_write_ticket(&request[HEADER..], build.sequence)?;
    let (pending, reads) = build.write.as_ref().ok_or(SourceError::StaleSource)?;
    if *pending != ticket {
        return Err(SourceError::StaleSource);
    }
    let bytes = build
        .session
        .as_ref()
        .ok_or(SourceError::StaleSource)?
        .write_bytes(ticket)?;
    if bytes.len().checked_mul(3).is_none_or(|n| n > budget) || bytes.len() > PAGE_BYTES {
        return Err(SourceError::ResourceLimit);
    }
    Ok((bytes, reads))
}

fn data_snapshot(entry: &Entry) -> Result<GeoOperationSnapshot> {
    let Entry::Data {
        bytes,
        semantic: Some(value),
        ..
    } = entry
    else {
        return Err(SourceError::InvalidFrame);
    };
    let key = value.result.key;
    Ok(GeoOperationSnapshot {
        source_digest: key.identity.source_digest,
        generation: key.identity.generation,
        camera: key.camera,
        time: key.time,
        camera_revision: u64at(bytes, 168),
        time_revision: u64at(bytes, 176),
        layer_id: key.identity.layer_id,
        layer_revision: u64at(bytes, 184),
        style_revision: key.identity.style_revision,
        state_revision: key.identity.state_revision,
    })
}

#[cfg(test)]
#[path = "geo_index_protocol_tests.rs"]
mod index_protocol_tests;

/// Private retained painter dispatch; a numeric handle does not identify a tier.
pub(crate) fn is_overview_data(handle: u64, sequence: u64) -> Result<bool> {
    let r = registry().lock().map_err(|_| SourceError::ResourceLimit)?;
    let entry = &r
        .entries
        .iter()
        .find(|(id, _)| *id == handle)
        .ok_or(SourceError::StaleSource)?
        .1;
    match entry {
        Entry::Data {
            overview: Some(value),
            ..
        } if sequence != 0 && sequence == value.sequence => Ok(true),
        Entry::Data {
            semantic: Some(value),
            ..
        } if sequence != 0 && sequence == value.sequence => Ok(false),
        _ => Err(SourceError::StaleSource),
    }
}

/// Borrow immutable overview Scene/count authority. The callback runs under the
/// registry lock and must not reenter this registry. Source-feature interaction
/// is intentionally unavailable for these explicitly coarse domain cells.
pub fn with_overview_data<T>(
    handle: u64,
    sequence: u64,
    callback: impl FnOnce(
        &[u8],
        &crate::geo_temporal_overview::GeoOverviewResult,
        GeoViewport,
    ) -> Result<T>,
) -> Result<T> {
    let r = registry().lock().map_err(|_| SourceError::ResourceLimit)?;
    let Entry::Data {
        bytes,
        overview: Some(s),
        ..
    } = &r
        .entries
        .iter()
        .find(|(id, _)| *id == handle)
        .ok_or(SourceError::StaleSource)?
        .1
    else {
        return Err(SourceError::InvalidFrame);
    };
    let snapshot = s.result.snapshot();
    if sequence == 0
        || sequence != s.sequence
        || snapshot.camera != s.camera.rebuild_key()?
        || snapshot.source_digest != s.result.source().digest()
        || snapshot.generation != s.result.source().generation()
        || !s.result.temporal_exact()
        || !s.result.data_space()
        || s.result.final_result()
    {
        return Err(SourceError::StaleSource);
    }
    callback(&bytes[HEADER + 2048..], &s.result, s.camera)
}

#[cfg(test)]
#[path = "geo_hierarchy_protocol_tests.rs"]
mod hierarchy_protocol_tests;

#[cfg(test)]
#[path = "geo_overview_painter_snapshot_tests.rs"]
mod overview_painter_snapshot_tests;

#[cfg(test)]
#[path = "geo_overview_membership_protocol_tests.rs"]
mod overview_membership_protocol_tests;
