//! Shared XYGI/XYGR boundary (§3). Hosts own only lifetime, staging and copies.
use super::*;
use crate::graph_interaction_state::HighlightPlane;
use crate::graphforge::container::{Builder, Container, Dtype, Section};
use crate::graphforge::identity::{AggregateRef, DerivedRef, ResultRef};

pub const REQUEST_MAGIC: &[u8; 4] = b"XYGI";
pub const RESULT_MAGIC: &[u8; 4] = b"XYGR";
pub const DEFAULT_MAX_BYTES: usize = 384 * 1024 * 1024;
pub const OPEN: u32 = 19;
pub const UPDATE: u32 = 20;
pub const RENDER: u32 = 21;
pub const POLL: u32 = 22;
const REF_BYTES: usize = 56;

type Result<T> = std::result::Result<T, InteractionStatus>;

impl InteractionStatus {
    pub fn number(self) -> i32 {
        match self {
            Self::Stale => -1,
            Self::Unlinked => -2,
            Self::Invalid => -3,
            Self::Budget => -4,
            Self::Capacity => -5,
            Self::SelfEcho => -6,
            Self::StaleRemote => -7,
            Self::SelectionTooLarge => -8,
            Self::CompoundTooLarge => -9,
            Self::Unbound => -10,
            Self::RevisionExhausted => -11,
        }
    }
}
fn bad<T>() -> Result<T> {
    Err(InteractionStatus::Invalid)
}
fn gf<T>(r: crate::graphforge::GfResult<T>) -> Result<T> {
    r.map_err(|_| InteractionStatus::Invalid)
}
fn u32_at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(b[at..at + 4].try_into().unwrap())
}
fn u64_at(b: &[u8], at: usize) -> u64 {
    u64::from_le_bytes(b[at..at + 8].try_into().unwrap())
}

/// Fixed records plus a contiguous exact-id pool; no receiver-local identity.
pub fn decode_refs(bytes: &[u8]) -> Result<Vec<ElementRef>> {
    if bytes.len() < 8 {
        return bad();
    }
    let n = u32_at(bytes, 0) as usize;
    if n > MAX_GRAPH_SELECTION_REFS {
        return Err(InteractionStatus::SelectionTooLarge);
    }
    let start = n
        .checked_mul(REF_BYTES)
        .and_then(|v| v.checked_add(8))
        .ok_or(InteractionStatus::Invalid)?;
    let end = start
        .checked_add(u32_at(bytes, 4) as usize)
        .ok_or(InteractionStatus::Invalid)?;
    if end != bytes.len() {
        return bad();
    }
    let mut out = Vec::with_capacity(n);
    let mut cursor = 0;
    for record in bytes[8..start].chunks_exact(REF_BYTES) {
        let kind = u32_at(record, 0);
        let id: Uuid = record[8..24].try_into().unwrap();
        let (layer, revision, path, order, off, len) = (
            u32_at(record, 24),
            u32_at(record, 28),
            u64_at(record, 32),
            u64_at(record, 40),
            u32_at(record, 48),
            u32_at(record, 52),
        );
        if u32_at(record, 4) != 0 {
            return bad();
        }
        out.push(match kind {
            0 | 1 => {
                if id == [0; 16]
                    || layer != 0
                    || revision != 0
                    || path != 0
                    || order != 0
                    || off != 0
                    || len != 0
                {
                    return bad();
                }
                if kind == 0 {
                    ElementRef::Node(id)
                } else {
                    ElementRef::Edge(id)
                }
            }
            2 => {
                if id != [0; 16] || revision != 0 {
                    return bad();
                }
                let exact = if off == u32::MAX && len == 0 {
                    None
                } else {
                    if off as usize != cursor || len == 0 || len > 128 {
                        return bad();
                    }
                    let end = cursor
                        .checked_add(len as usize)
                        .ok_or(InteractionStatus::Invalid)?;
                    let text = bytes
                        .get(start + cursor..start + end)
                        .ok_or(InteractionStatus::Invalid)?;
                    if !text
                        .iter()
                        .all(|b| b.is_ascii_alphanumeric() || b"._:-".contains(b))
                    {
                        return bad();
                    }
                    cursor = end;
                    Some(
                        std::str::from_utf8(text)
                            .map_err(|_| InteractionStatus::Invalid)?
                            .into(),
                    )
                };
                ElementRef::Derived(DerivedRef {
                    result: ResultRef::Exact(exact),
                    layer,
                    path,
                    order,
                })
            }
            3 => {
                if id != [0; 16] || path != 0 || order != 0 || off != 0 || len != 0 {
                    return bad();
                }
                ElementRef::Aggregate(AggregateRef {
                    render_revision: revision,
                    index: layer,
                })
            }
            _ => return bad(),
        });
    }
    if cursor != bytes.len() - start {
        return bad();
    }
    Ok(out)
}

pub fn encode_refs(refs: &[ElementRef]) -> Result<Vec<u8>> {
    if refs.len() > MAX_GRAPH_SELECTION_REFS * 2 {
        return Err(InteractionStatus::SelectionTooLarge);
    }
    let mut records = vec![0; 8 + refs.len() * REF_BYTES];
    records[..4].copy_from_slice(&(refs.len() as u32).to_le_bytes());
    let mut pool = Vec::new();
    for (i, element) in refs.iter().enumerate() {
        let r = &mut records[8 + i * REF_BYTES..8 + (i + 1) * REF_BYTES];
        match element {
            ElementRef::Node(id) | ElementRef::Edge(id) => {
                r[..4].copy_from_slice(
                    &u32::from(matches!(element, ElementRef::Edge(_))).to_le_bytes(),
                );
                r[8..24].copy_from_slice(id);
            }
            ElementRef::Derived(d) => {
                r[..4].copy_from_slice(&2u32.to_le_bytes());
                r[24..28].copy_from_slice(&d.layer.to_le_bytes());
                r[32..40].copy_from_slice(&d.path.to_le_bytes());
                r[40..48].copy_from_slice(&d.order.to_le_bytes());
                let ResultRef::Exact(id) = &d.result else {
                    return bad();
                };
                let (off, len) = match id {
                    None => (u32::MAX, 0),
                    Some(id) => {
                        if id.is_empty()
                            || id.len() > 128
                            || !id
                                .bytes()
                                .all(|b| b.is_ascii_alphanumeric() || b"._:-".contains(&b))
                        {
                            return bad();
                        }
                        let off = pool.len() as u32;
                        pool.extend_from_slice(id.as_bytes());
                        (off, id.len() as u32)
                    }
                };
                r[48..52].copy_from_slice(&off.to_le_bytes());
                r[52..56].copy_from_slice(&len.to_le_bytes());
            }
            ElementRef::Aggregate(a) => {
                r[..4].copy_from_slice(&3u32.to_le_bytes());
                r[24..28].copy_from_slice(&a.index.to_le_bytes());
                r[28..32].copy_from_slice(&a.render_revision.to_le_bytes());
            }
        }
    }
    records[4..8].copy_from_slice(&(pool.len() as u32).to_le_bytes());
    records.extend(pool);
    Ok(records)
}

pub struct Request<'a> {
    pub instance: u64,
    pub group: u64,
    pub sequence: u64,
    pub operation: u32,
    words: [u32; 9],
    pub header: OpHeader,
    container: Container<'a>,
}
impl<'a> Request<'a> {
    pub fn decode(bytes: &'a [u8]) -> Result<Self> {
        let c = gf(Container::decode(bytes, REQUEST_MAGIC))?;
        let get = |name| c.get(name, 0).ok_or(InteractionStatus::Invalid);
        let h = gf(get("header.u64")?.as_u64("header.u64"))?;
        let w = gf(get("header.u32")?.as_u32("header.u32"))?;
        if h.len() != 3 || w.len() != 9 || h[0] == 0 || h[2] == 0 || w[1] > POLL {
            return bad();
        }
        let operation = w[1];
        let mut used = [false; 9];
        used[0] = true;
        used[1] = true;
        for i in match operation {
            1 | 7 | 10 | 11 => &[2][..],
            2 | 3 => &[2, 3],
            5 | 8 => &[5],
            9 | 13 => &[5],
            12 => &[2, 4],
            14 => &[6, 8],
            15 => &[7],
            _ => &[],
        } {
            used[*i] = true;
        }
        if w.iter().enumerate().any(|(i, v)| !used[i] && *v != 0)
            || (used[2] && w[2] > 2)
            || (used[3] && w[3] > 2)
            || (used[4] && w[4] > 2)
            || (matches!(operation, 5 | 8) && w[5] != 1 && w[5] != u32::MAX)
            || (operation == 9 && w[5] > 2)
            || (operation == 13 && w[5] > 1)
            || (operation == 14 && (w[6] > 2 || w[8] > 1))
            || (operation == 15 && (w[7] == 0 || w[7] > 64))
        {
            return bad();
        }
        for (name, index, s) in &c.sections {
            let expected = match *name {
                "header.u64" => Some(Dtype::U64),
                "header.u32" => Some(Dtype::U32),
                "camera.f64" if operation == RENDER => Some(Dtype::F64),
                "coordinates.f64" if operation <= 3 || operation == 14 => Some(Dtype::F64),
                "refs.bytes" if matches!(operation, 6 | 9 | 11 | 12 | 13 | 14) => {
                    Some(Dtype::Bytes)
                }
                "uuids.uuid" if operation == 10 => Some(Dtype::Uuid),
                "remote.bytes" if operation == 16 => Some(Dtype::Bytes),
                "companion.u32" if matches!(operation, 17 | RENDER) => Some(Dtype::U32),
                "temporal.u64" if operation == 18 => Some(Dtype::U64),
                "document.bytes" if matches!(operation, OPEN | UPDATE) => Some(Dtype::Bytes),
                "load.x.f64" | "load.y.f64" if matches!(operation, OPEN | UPDATE) => {
                    Some(Dtype::F64)
                }
                "load.collapsed.u8" | "load.pinned.u8" if matches!(operation, OPEN | UPDATE) => {
                    Some(Dtype::U8)
                }
                "load.budgets.u64" | "load.seed.u64" if matches!(operation, OPEN | UPDATE) => {
                    Some(Dtype::U64)
                }
                _ => None,
            };
            if *index != 0 || expected != Some(s.dtype) {
                return bad();
            }
        }
        let r = Self {
            instance: h[0],
            group: h[1],
            sequence: h[2],
            operation,
            words: w.clone().try_into().unwrap(),
            header: OpHeader {
                stamp: Stamp {
                    instance_id: h[0],
                    render_revision: w[0],
                },
                op_seq: h[2],
            },
            container: c,
        };
        // Validate all optional payloads before any retry or owner lookup.
        if let Some(s) = r.container.get("refs.bytes", 0) {
            decode_refs(s.payload)?;
        }
        if let Some(s) = r.container.get("remote.bytes", 0) {
            decode_event(s.payload)?;
        }
        if let Some(s) = r.container.get("coordinates.f64", 0) {
            let v = gf(s.as_f64("coordinates.f64"))?;
            if v.iter().any(|v| !v.is_finite()) {
                return bad();
            }
        }
        r.page()?;
        Ok(r)
    }
    fn section(&self, name: &str) -> Result<Section<'a>> {
        self.container
            .get(name, 0)
            .ok_or(InteractionStatus::Invalid)
    }
    pub fn document(&self) -> Result<&'a [u8]> {
        Ok(self.section("document.bytes")?.payload)
    }
    pub fn load(&self) -> Result<SessionLoad> {
        let f64s = |name| {
            self.container
                .get(name, 0)
                .map(|s| gf(s.as_f64(name)))
                .transpose()
        };
        let flags = |name| self.container.get(name, 0).map(|s| s.payload.to_vec());
        let budgets = self
            .container
            .get("load.budgets.u64", 0)
            .map(|s| {
                let v = gf(s.as_u64("load.budgets.u64"))?;
                if v.len() != 2 {
                    return bad();
                }
                Ok((v[0], v[1]))
            })
            .transpose()?;
        let seed = self
            .container
            .get("load.seed.u64", 0)
            .map(|s| {
                let v = gf(s.as_u64("load.seed.u64"))?;
                if v.len() != 1 {
                    return bad();
                }
                Ok(v[0])
            })
            .transpose()?
            .unwrap_or(0);
        Ok(SessionLoad {
            x: f64s("load.x.f64")?,
            y: f64s("load.y.f64")?,
            collapsed: flags("load.collapsed.u8"),
            pinned: flags("load.pinned.u8"),
            budgets,
            seed,
        })
    }
    pub fn temporal(&self) -> Result<u64> {
        let v = gf(self.section("temporal.u64")?.as_u64("temporal.u64"))?;
        if v.len() != 1 {
            return bad();
        }
        Ok(v[0])
    }
    fn page(&self) -> Result<(usize, usize)> {
        let Some(s) = self.container.get("companion.u32", 0) else {
            return Ok((0, 50));
        };
        let v = gf(s.as_u32("companion.u32"))?;
        if v.len() != 2 || v[1] == 0 || v[1] > 200 {
            return bad();
        }
        // A wire page must have the same meaning on native and wasm32.
        v[0].checked_mul(v[1]).ok_or(InteractionStatus::Invalid)?;
        Ok((v[0] as usize, v[1] as usize))
    }
    fn camera(&self) -> Result<Option<Camera>> {
        let Some(s) = self.container.get("camera.f64", 0) else {
            return Ok(None);
        };
        let v = gf(s.as_f64("camera.f64"))?;
        if v.len() != 7 {
            return bad();
        }
        let c = Camera {
            scale_x: v[0],
            scale_y: v[1],
            offset_x: v[2],
            offset_y: v[3],
            viewport_width: v[4],
            viewport_height: v[5],
            dpr: v[6],
        };
        c.validate()?;
        Ok(Some(c))
    }
    fn refs(&self) -> Result<Vec<ElementRef>> {
        decode_refs(self.section("refs.bytes")?.payload)
    }
}

pub fn encode_event(event: &GraphCoordinationEvent) -> Result<Vec<u8>> {
    event.validate()?;
    let mut b = Builder::new(REQUEST_MAGIC);
    b.u64s(
        "remote.u64",
        0,
        &[event.group_id, event.source_instance, event.revision],
    );
    if let Some(g) = event.generation {
        b.uuids("remote.generation.uuid", 0, &[g]);
    }
    b.bytes("refs.bytes", 0, &encode_refs(&event.refs)?);
    Ok(b.finish())
}
pub fn decode_event(bytes: &[u8]) -> Result<GraphCoordinationEvent> {
    let c = gf(Container::decode(bytes, REQUEST_MAGIC))?;
    for (n, i, s) in &c.sections {
        if *i != 0
            || !matches!(
                (*n, s.dtype),
                ("remote.u64", Dtype::U64)
                    | ("remote.generation.uuid", Dtype::Uuid)
                    | ("refs.bytes", Dtype::Bytes)
            )
        {
            return bad();
        }
    }
    let h = gf(c
        .get("remote.u64", 0)
        .ok_or(InteractionStatus::Invalid)?
        .as_u64("remote.u64"))?;
    if h.len() != 3 {
        return bad();
    }
    let generation = c
        .get("remote.generation.uuid", 0)
        .map(|s| {
            let v = gf(s.as_uuids("remote.generation.uuid"))?;
            if v.len() != 1 {
                return bad();
            }
            Ok(v[0])
        })
        .transpose()?;
    let event = GraphCoordinationEvent {
        group_id: h[0],
        source_instance: h[1],
        revision: h[2],
        generation,
        refs: decode_refs(
            c.get("refs.bytes", 0)
                .ok_or(InteractionStatus::Invalid)?
                .payload,
        )?,
    };
    event.validate()?;
    Ok(event)
}

/// Retained serialized retry cache. `GraphSession` typed outcomes remain private
/// to the candidate; only this complete reply is observable across the boundary.
pub struct WireSession {
    session: GraphSession,
    document: Vec<u8>,
    opening: Vec<u8>,
    open_reply: Vec<u8>,
    last_request: Vec<u8>,
    last_reply: Vec<u8>,
    last_sequence: u64,
    pub max_bytes: usize,
}
impl std::fmt::Debug for WireSession {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("WireSession")
            .field("instance", &self.session.instance_id)
            .field("sequence", &self.last_sequence)
            .finish_non_exhaustive()
    }
}
impl WireSession {
    pub fn session(&self) -> &GraphSession {
        &self.session
    }
    /// Charge peak, including candidate, hash/tree overhead, grid duplication,
    /// multiple codec buffers and temporary render/layout arrays. Checked before
    /// allocation. Factor 48 covers all decoded style/identity/text copies.
    fn charge(
        document: usize,
        n: usize,
        m: usize,
        watermarks: usize,
        state: usize,
    ) -> Option<usize> {
        let primitives = n.checked_add(m.checked_mul(11)?)?;
        98_304usize
            .checked_add(document.checked_mul(48)?)?
            .checked_add(n.checked_add(m)?.checked_mul(8192)?)?
            .checked_add(
                primitives
                    .checked_mul(4096)?
                    .min(MAX_GRAPH_PICK_GRID_ENTRIES)
                    .checked_mul(16)?,
            )?
            .checked_add(watermarks.checked_mul(128)?)?
            .checked_add(state.checked_mul(1024)?)
    }
    pub fn retained_budget(&self) -> usize {
        Self::charge(
            self.document.len(),
            self.session.identity.node_count(),
            self.session.identity.edge_count(),
            self.session.coordination.gate.len(),
            MAX_GRAPH_SELECTION_REFS * 5,
        )
        .and_then(|n| n.checked_add(self.last_request.len() * 3))
        .and_then(|n| n.checked_add(self.opening.len() * 3))
        .and_then(|n| n.checked_add(self.open_reply.len() * 3))
        .and_then(|n| n.checked_add(self.last_reply.len() * 3))
        .unwrap_or(usize::MAX)
    }
    fn admit(&self, request: &[u8], external: usize) -> Result<()> {
        let r = Request::decode(request)?;
        let doc = r
            .container
            .get("document.bytes", 0)
            .map_or(0, |s| s.payload.len());
        let replacement = if r.operation == UPDATE {
            let c = gf(Container::decode(
                r.document()?,
                crate::graphforge::container::DOCUMENT_MAGIC,
            ))?;
            Self::charge(
                doc,
                c.get("node.uuid", 0)
                    .ok_or(InteractionStatus::Invalid)?
                    .count,
                c.get("edge.uuid", 0)
                    .ok_or(InteractionStatus::Invalid)?
                    .count,
                0,
                MAX_GRAPH_SELECTION_REFS * 5,
            )
            .ok_or(InteractionStatus::Budget)?
        } else {
            0
        };
        let charge = self
            .retained_budget()
            .checked_add(
                request
                    .len()
                    .checked_mul(8)
                    .ok_or(InteractionStatus::Budget)?,
            )
            .and_then(|v| v.checked_add(external))
            .and_then(|v| v.checked_add(replacement))
            .ok_or(InteractionStatus::Budget)?;
        if charge > self.max_bytes {
            return Err(InteractionStatus::Budget);
        }
        Ok(())
    }
    pub fn open(bytes: &[u8], max_bytes: usize, external: usize) -> Result<Self> {
        let r = Request::decode(bytes)?;
        if r.operation != OPEN || r.words[0] != 0 {
            return bad();
        }
        let document = r.document()?;
        // Count planes without expanding them; document validation follows admission.
        let c = gf(Container::decode(
            document,
            crate::graphforge::container::DOCUMENT_MAGIC,
        ))?;
        let n = c
            .get("node.uuid", 0)
            .ok_or(InteractionStatus::Invalid)?
            .count;
        let m = c
            .get("edge.uuid", 0)
            .ok_or(InteractionStatus::Invalid)?
            .count;
        let charge = Self::charge(document.len(), n, m, 0, MAX_GRAPH_SELECTION_REFS * 5)
            .and_then(|v| v.checked_add(bytes.len().checked_mul(8)?))
            .and_then(|v| v.checked_add(external))
            .ok_or(InteractionStatus::Budget)?;
        if charge > max_bytes {
            return Err(InteractionStatus::Budget);
        }
        let session = GraphSession::create_linked(document, r.load()?, r.instance, r.group)?;
        let mut out = Self {
            session,
            document: document.to_vec(),
            opening: bytes.to_vec(),
            open_reply: Vec::new(),
            last_request: bytes.to_vec(),
            last_reply: Vec::new(),
            last_sequence: r.sequence,
            max_bytes,
        };
        // Open only acknowledges ingress; initial layout remains lazy, as S1–S3.
        let mut b = Builder::new(RESULT_MAGIC);
        b.u32s("status.u32", 0, &[0]);
        b.u32s("header.u32", 0, &[0, 0, 0, 0]);
        out.last_reply = b.finish();
        out.open_reply = out.last_reply.clone();
        Ok(out)
    }
    pub fn opening_matches(&self, bytes: &[u8]) -> bool {
        self.opening == bytes
    }
    pub fn opening_reply(&self) -> &[u8] {
        &self.open_reply
    }
    pub fn reply(&self) -> &[u8] {
        &self.last_reply
    }
    pub fn check_live(&self) -> Result<()> {
        self.session.read_state(|_| ())
    }
    fn retry(&self, r: &Request<'_>, bytes: &[u8]) -> Result<bool> {
        if r.instance != self.session.instance_id || r.group != self.session.group_id() {
            return bad();
        }
        if r.sequence < self.last_sequence {
            return bad();
        }
        if r.sequence == self.last_sequence {
            if bytes != self.last_request {
                return bad();
            }
            if !(r.operation == 18 && r.temporal()? == 0) {
                self.check_live()?;
            }
            return Ok(true);
        }
        Ok(false)
    }
    /// Apply and capture one reply inside one temporal world lock. The bounded
    /// candidate holds Owned speculative state, so typed calls never re-enter
    /// the temporal host. Commit only after serialization and size admission.
    pub fn execute(
        &mut self,
        bytes: &[u8],
        external: usize,
        bind: Option<(Arc<dyn TemporalHost>, TemporalHandle)>,
    ) -> Result<&[u8]> {
        let r = Request::decode(bytes)?;
        if self.retry(&r, bytes)? {
            return Ok(&self.last_reply);
        }
        if r.operation == OPEN || r.operation == POLL {
            return bad();
        }
        self.admit(bytes, external)?;
        if r.operation == 18 && r.temporal()? != 0 {
            self.check_live()?;
        }
        // Bind changes owners. Validate candidate against the new owner before
        // installing it; no state mutation occurs in that owner.
        let max_bytes = self.max_bytes;
        let result = if r.operation == 18 {
            let mut next = self.session.clone();
            if r.header.stamp
                != (Stamp {
                    instance_id: next.instance_id,
                    render_revision: next.render_revision,
                })
            {
                return Err(InteractionStatus::Stale);
            }
            let (candidate, reply) = if r.temporal()? == 0 {
                next.unbind()?;
                Self::finish(next, &r, OpOutcome::default())?
            } else {
                let (host, handle) = bind.ok_or(InteractionStatus::Unbound)?;
                let (mut next, mut output) = (Some(next), None);
                let found = host.with_graph(handle, &mut |graph| {
                    let mut next = next.take().expect("one owner access");
                    output = Some((|| {
                        if next.identity.node_uuids() != graph.node_ids()
                            || !next
                                .identity
                                .persisted_edge_uuids()
                                .eq(graph.edge_ids().iter().copied())
                        {
                            return bad();
                        }
                        next.reserve_revision()?;
                        let (state, visibility, temporal_revision) = graph.world_parts();
                        next.seen_temporal = temporal_revision;
                        next.relayout = None;
                        next.bump();
                        let candidate = next.candidate(&World {
                            state,
                            visibility,
                            temporal_revision,
                        });
                        let (mut candidate, reply) =
                            Self::finish(candidate, &r, OpOutcome::default())?;
                        candidate.slot = StateSlot::Bound {
                            host: Arc::clone(&host),
                            handle,
                        };
                        Ok((candidate, reply))
                    })());
                });
                if !found {
                    return Err(InteractionStatus::Unbound);
                }
                output.ok_or(InteractionStatus::Unbound)??
            };
            if reply
                .len()
                .checked_mul(3)
                .and_then(|v| v.checked_add(external))
                .is_none_or(|v| v > max_bytes)
            {
                return Err(InteractionStatus::Budget);
            }
            self.session = candidate;
            reply
        } else {
            self.session.locked_validated(
                |_, graph| {
                    if r.operation == UPDATE {
                        let next = GraphSession::create(r.document()?, r.load()?, r.instance)?;
                        if !next.matches_temporal(graph) {
                            return bad();
                        }
                    }
                    Ok(())
                },
                |session, world| {
                    let mut next = session.candidate(&world);
                    let outcome = apply(&mut next, &r)?;
                    let (mut next, reply) = Self::finish(next, &r, outcome)?;
                    if reply
                        .len()
                        .checked_mul(3)
                        .and_then(|v| v.checked_add(external))
                        .is_none_or(|v| v > max_bytes)
                    {
                        return Err(InteractionStatus::Budget);
                    }
                    let StateSlot::Owned(state) =
                        std::mem::replace(&mut next.slot, StateSlot::Owned(Box::default()))
                    else {
                        return bad();
                    };
                    *world.state = *state;
                    std::mem::swap(&mut next.slot, &mut session.slot);
                    *session = next;
                    Ok(reply)
                },
            )??
        };
        self.last_reply = result;
        if r.operation == UPDATE {
            self.document = r.document()?.to_vec();
        }
        self.last_request = bytes.to_vec();
        self.last_sequence = r.sequence;
        Ok(&self.last_reply)
    }
    fn finish(
        mut next: GraphSession,
        r: &Request<'_>,
        outcome: OpOutcome,
    ) -> Result<(GraphSession, Vec<u8>)> {
        let camera = if r.operation == RENDER {
            r.camera()?
        } else {
            next.camera
        };
        next.render(camera)?;
        let reply = serialize(&mut next, r, &outcome)?;
        next.transaction_world = None;
        Ok((next, reply))
    }
    /// Poll computes complete bytes and checks capacity before consuming. A
    /// rejected capacity never overwrites the successful command retry cache.
    pub fn poll(&mut self, bytes: &[u8], capacity: usize, external: usize) -> Result<usize> {
        let r = Request::decode(bytes)?;
        if r.operation != POLL {
            return bad();
        }
        if self.retry(&r, bytes)? {
            return Ok(self.last_reply.len());
        }
        self.check_live()?;
        self.admit(bytes, external)?;
        let mut b = Builder::new(RESULT_MAGIC);
        b.u32s("status.u32", 0, &[0]);
        if let Some(event) = self.session.pending_outbound() {
            b.bytes("outbound.bytes", 0, &encode_event(event)?);
        }
        let reply = b.finish();
        let len = reply.len();
        if len > capacity {
            return Ok(len);
        }
        self.session.take_outbound();
        self.last_reply = reply;
        self.last_request = bytes.to_vec();
        self.last_sequence = r.sequence;
        Ok(len)
    }
}
impl GraphSession {
    fn candidate(&self, world: &World<'_>) -> Self {
        let mut next = self.clone();
        next.slot = StateSlot::Owned(Box::new(world.state.clone()));
        next.transaction_world = Some(world.visibility.map_or(
            (Vec::new(), Vec::new(), world.temporal_revision),
            |(n, e)| (n.to_vec(), e.to_vec(), world.temporal_revision),
        ));
        if world.visibility.is_none() {
            next.transaction_world = None;
        }
        next
    }
}

fn apply(s: &mut GraphSession, r: &Request<'_>) -> Result<OpOutcome> {
    let h = r.header;
    let mode = match r.words[2] {
        0 => SelectMode::Replace,
        1 => SelectMode::Add,
        _ => SelectMode::Toggle,
    };
    let policy = match r.words[3] {
        0 => SelectionPolicy::Nodes,
        1 => SelectionPolicy::Edges,
        _ => SelectionPolicy::NodesAndInducedEdges,
    };
    let coordinates =
        || -> Result<Vec<f64>> { gf(r.section("coordinates.f64")?.as_f64("coordinates.f64")) };
    let pair = || -> Result<(f64, f64)> {
        let v = coordinates()?;
        if v.len() != 2 {
            return bad();
        }
        Ok((v[0], v[1]))
    };
    let one = || -> Result<ElementRef> {
        let v = r.refs()?;
        if v.len() != 1 {
            return bad();
        }
        Ok(v[0].clone())
    };
    match r.operation {
        0 => {
            let (x, y) = pair()?;
            s.hover_at(h, x, y)
        }
        1 => {
            let (x, y) = pair()?;
            s.select_at(h, x, y, mode)
        }
        2 => {
            let v = coordinates()?;
            if v.len() != 4 {
                return bad();
            }
            s.brush(h, [v[0], v[1], v[2], v[3]], mode, policy)
        }
        3 => {
            let v = coordinates()?;
            if v.len() % 2 != 0 || v.len() > MAX_GRAPH_INTERACTION_WORK as usize {
                return bad();
            }
            let p: Vec<_> = v.chunks_exact(2).map(|v| [v[0], v[1]]).collect();
            s.lasso(h, &p, mode, policy)
        }
        4 => s.clear(h),
        5 => s.focus_step(h, r.words[5] as i32),
        6 => {
            let v = r.refs()?;
            if v.len() > 1 {
                return bad();
            }
            s.focus_ref(h, v.first())
        }
        7 => s.select_focused(h, mode),
        8 => s.focus_ring(h, r.words[5] as i32),
        9 => s.toggle_disclosure(
            h,
            &one()?,
            match r.words[5] {
                0 => DisclosureAction::Toggle,
                1 => DisclosureAction::Collapse,
                _ => DisclosureAction::Expand,
            },
        ),
        10 => s.select_uuids(
            h,
            &gf(r.section("uuids.uuid")?.as_uuids("uuids.uuid"))?,
            mode,
        ),
        11 => s.select_refs(h, &r.refs()?, mode),
        12 => s.set_highlight(
            h,
            match r.words[4] {
                0 => HighlightPlane::Path,
                1 => HighlightPlane::Community,
                _ => HighlightPlane::External,
            },
            &r.refs()?,
            mode,
        ),
        13 => s.pin(h, &one()?, r.words[5] == 1),
        14 => s.move_node(
            h,
            &one()?,
            pair()?,
            if r.words[8] == 0 {
                MoveSpace::Data
            } else {
                MoveSpace::ScreenDelta
            },
            match r.words[6] {
                0 => MoveCommit::Preview,
                1 => MoveCommit::Commit,
                _ => MoveCommit::Cancel,
            },
        ),
        15 => s.relayout_step(h, r.words[7]),
        16 => s.apply_remote(h, &decode_event(r.section("remote.bytes")?.payload)?),
        17 | RENDER => {
            // Read/publication commands consume their wire sequence but never
            // re-use a typed mutation outcome. Stamp is still checked.
            s.locked(|session, w| {
                session.sync_world(&w)?;
                if r.operation != RENDER
                    && h.stamp
                        != (Stamp {
                            instance_id: session.instance_id,
                            render_revision: session.render_revision,
                        })
                {
                    return Err(InteractionStatus::Stale);
                }
                Ok(session.outcome(&w, false))
            })?
        }
        UPDATE => s.update(h, r.document()?, r.load()?),
        _ => bad(),
    }
}

fn escaped(text: &str) -> String {
    text.replace('\\', "\\\\")
        .replace('\t', "\\t")
        .replace('\n', "\\n")
}
fn uuid_text(id: &Uuid) -> String {
    id.iter().map(|v| format!("{v:02x}")).collect()
}
fn transport(s: &GraphSession, refs: &[ElementRef]) -> Result<Vec<ElementRef>> {
    refs.iter()
        .map(|r| {
            s.identity
                .to_transport(r)
                .or_else(|| matches!(r, ElementRef::Aggregate(_)).then(|| r.clone()))
                .ok_or(InteractionStatus::Invalid)
        })
        .collect()
}
fn serialize(s: &mut GraphSession, r: &Request<'_>, out: &OpOutcome) -> Result<Vec<u8>> {
    let mut b = Builder::new(RESULT_MAGIC);
    b.u32s("status.u32", 0, &[0]);
    let render = s.published().ok_or(InteractionStatus::Stale)?;
    b.u32s(
        "header.u32",
        0,
        &[
            render.revision,
            u32::from(render.pick.degraded),
            out.unmatched,
            out.dropped,
        ],
    );
    b.u32s("render.tier.u32", 0, &[render.tier as u32]);
    b.u64s("render.edges_kept.u64", 0, &[render.edges_kept]);
    b.f64s("render.node_x.f64", 0, &render.node_x);
    b.f64s("render.node_y.f64", 0, &render.node_y);
    for (name, v) in [
        ("render.member_of.u64", &render.member_of),
        ("render.edge_source.u64", &render.edge_source),
        ("render.edge_target.u64", &render.edge_target),
        (
            "render.edge_member_offsets.u64",
            &render.edge_member_offsets,
        ),
        ("render.edge_members.u64", &render.edge_members),
        (
            "render.node_member_offsets.u64",
            &render.node_member_offsets,
        ),
        ("render.node_members.u64", &render.node_members),
    ] {
        b.u64s(name, 0, v);
    }
    for (name, v) in [
        ("render.visual_states.u8", &render.visual_states),
        ("render.emphasis.u8", &render.emphasis),
        ("render.edge_visual_states.u8", &render.edge_visual_states),
        ("render.edge_emphasis.u8", &render.edge_emphasis),
    ] {
        b.u8s(name, 0, v);
    }
    b.u32s("node.flags.u32", 0, &render.source_node_flags);
    b.u32s("edge.flags.u32", 0, &render.source_edge_flags);
    let state = s.read_state(Clone::clone)?;
    let focus = s.focus()?.into_iter().collect::<Vec<_>>();
    b.bytes("focus.bytes", 0, &encode_refs(&transport(s, &focus)?)?);
    b.bytes(
        "changed.refs.bytes",
        0,
        &encode_refs(&transport(s, &out.changed)?)?,
    );
    let (page, size) = r.page()?;
    let start = page.checked_mul(size).ok_or(InteractionStatus::Invalid)?;
    let total = s
        .identity
        .node_count()
        .checked_add(s.identity.edge_count())
        .ok_or(InteractionStatus::Budget)?;
    let mut candidates = Vec::new();
    let mut rows = Vec::new();
    for i in start..start.saturating_add(size).min(total) {
        let (kind, index) = if i < s.identity.node_count() {
            ("Node", ElementIndex::Node(i))
        } else {
            ("Edge", ElementIndex::Edge(i - s.identity.node_count()))
        };
        let reference = match index {
            ElementIndex::Node(i) => s.identity.node_ref(i),
            ElementIndex::Edge(i) => s.identity.edge_ref(i),
        };
        let exact = s
            .identity
            .to_transport(&reference)
            .ok_or(InteractionStatus::Invalid)?;
        let id = match &exact {
            ElementRef::Node(id) | ElementRef::Edge(id) => uuid_text(id),
            ElementRef::Derived(d) => format!("{:?}:{}:{}:{}", d.result, d.layer, d.path, d.order),
            _ => unreachable!(),
        };
        let selected = match &reference {
            ElementRef::Node(id) => state.selection().nodes.contains(id),
            ElementRef::Edge(id) => state.selection().edges.contains(id),
            _ => s.identity.resolve(&reference).ok().is_some_and(|idx| {
                let mut set = ElementSet::default();
                s.identity.insert_into(&mut set, idx);
                set.derived
                    .iter()
                    .any(|k| state.selection().derived.contains(k))
            }),
        };
        let label = s.labels.get(i).map(String::as_str).unwrap_or("");
        let relation = match index {
            ElementIndex::Node(n) => format!(
                "{} relationships",
                s.edge_source
                    .iter()
                    .zip(&s.edge_target)
                    .filter(|(a, b)| **a == n as u64 || **b == n as u64)
                    .count()
            ),
            ElementIndex::Edge(e) => format!("{} to {}", s.edge_source[e], s.edge_target[e]),
        };
        rows.push(format!(
            "{kind}\t{}\t{}\t{}\t{}",
            escaped(&id),
            escaped(label),
            escaped(&relation),
            if selected { "selected" } else { "not selected" }
        ));
        candidates.push(exact);
    }
    b.bytes("candidates.bytes", 0, &encode_refs(&candidates)?);
    b.u32s(
        "candidates.total.u32",
        0,
        &[total.try_into().map_err(|_| InteractionStatus::Budget)?],
    );
    b.utf8("companion.text.utf8", 0, &rows.join("\n"));
    b.u32s("companion.total.u32", 0, &[total as u32]);
    let mut ring = Vec::new();
    let published = s.published().ok_or(InteractionStatus::Stale)?;
    let anchor = s.ring_anchor.or_else(|| {
        s.stop_of(published, state.focus()).map(|stop| match stop {
            walk::Stop::Node(n) => n,
            walk::Stop::Edge(e) => published.edge_source[e as usize],
        })
    });
    if let Some(anchor) = anchor {
        for stop in GraphSession::ring(published, anchor)
            .into_iter()
            .skip(start)
            .take(size)
        {
            match stop {
                walk::Stop::Node(n) => ring.extend([0, n as u32]),
                walk::Stop::Edge(e) => ring.extend([1, e as u32]),
            };
        }
    }
    b.u32s("focus.ring.u32", 0, &ring);
    let summary = if let Some(report) = out.relayout {
        if report.done {
            "relayout settled".to_string()
        } else {
            format!("relayout, alpha {}", report.alpha)
        }
    } else if let Some(f) = focus.first() {
        summary(s, &state, f)?
    } else {
        format!(
            "Graph, {} nodes, {} edges, {} selected",
            s.identity.node_count(),
            s.identity.edge_count(),
            state.selection().len()
        )
    };
    b.utf8("summary.text.utf8", 0, &summary);
    let mut positions = Vec::new();
    for p in &out.positions {
        let encoded = encode_refs(std::slice::from_ref(&p.node))?;
        positions.extend_from_slice(&encoded[8..64]);
        positions.extend_from_slice(&p.x.to_le_bytes());
        positions.extend_from_slice(&p.y.to_le_bytes());
        positions.extend_from_slice(&u32::from(p.pinned).to_le_bytes());
        positions.extend_from_slice(&0u32.to_le_bytes());
    }
    b.bytes("positions.changed.bytes", 0, &positions);
    if let Some(report) = out.relayout {
        b.f64s("relayout.alpha.f64", 0, &[report.alpha]);
        b.u8s("relayout.done.u8", 0, &[u8::from(report.done)]);
    }
    if let Some(event) = s.pending_outbound() {
        b.bytes("outbound.bytes", 0, &encode_event(event)?);
    }
    Ok(b.finish())
}
fn summary(s: &GraphSession, state: &GraphInteractionState, f: &ElementRef) -> Result<String> {
    let index = s
        .identity
        .resolve(f)
        .map_err(|_| InteractionStatus::Invalid)?;
    let (kind, i, ordinal, selected, relationship) = match index {
        ElementIndex::Node(i) => (
            if s.parent.iter().any(|p| *p == i as u64) {
                "Group"
            } else {
                "Node"
            },
            i,
            i + 1,
            state
                .selection()
                .nodes
                .contains(&s.identity.node_uuids()[i]),
            format!(
                "{} relationships",
                s.edge_source
                    .iter()
                    .zip(&s.edge_target)
                    .filter(|(a, b)| **a == i as u64 || **b == i as u64)
                    .count()
            ),
        ),
        ElementIndex::Edge(i) => (
            "Edge",
            s.identity.node_count() + i,
            i + 1,
            match s.identity.edge_ref(i) {
                ElementRef::Edge(id) => state.selection().edges.contains(&id),
                _ => state
                    .selection()
                    .derived
                    .iter()
                    .any(|k| s.identity.resolve_derived_key(k) == Some(i)),
            },
            format!("{} to {}", s.edge_source[i], s.edge_target[i]),
        ),
    };
    let mut text = format!(
        "{kind} {}, {relationship}, {}, {ordinal} of {}",
        s.labels.get(i).map(String::as_str).unwrap_or(""),
        if selected { "selected" } else { "not selected" },
        if kind == "Edge" {
            s.identity.edge_count()
        } else {
            s.identity.node_count()
        }
    );
    if s.move_origin.is_some() {
        if let (ElementIndex::Node(n), Some((x, y))) = (index, s.positions()) {
            text.push_str(&format!(", moving, {} {}", x[n], y[n]));
        }
    }
    Ok(text)
}
