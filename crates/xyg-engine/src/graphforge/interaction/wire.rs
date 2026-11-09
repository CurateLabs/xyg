//! Shared XYGI/XYGR boundary (§3). Hosts own only lifetime, staging and copies.
pub use super::gpu::validate as validate_gpu;
pub use super::wire_paint::decode as decode_paint;
use super::*;
use crate::graph_interaction_state::HighlightPlane;
pub(super) use crate::graphforge::container::{Builder, Container, Dtype, Section};
use crate::graphforge::identity::{AggregateRef, DerivedRef, ResultRef};

pub const REQUEST_MAGIC: &[u8; 4] = b"XYGI";
pub const RESULT_MAGIC: &[u8; 4] = b"XYGR";
pub const DEFAULT_MAX_BYTES: usize = 384 * 1024 * 1024;
pub const OPEN: u32 = 19;
pub const UPDATE: u32 = 20;
pub const RENDER: u32 = 21;
pub const POLL: u32 = 22;
const REF_BYTES: usize = 56;

pub(super) type Result<T> = std::result::Result<T, InteractionStatus>;

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
pub(super) fn bad<T>() -> Result<T> {
    Err(InteractionStatus::Invalid)
}
pub(super) fn gf<T>(r: crate::graphforge::GfResult<T>) -> Result<T> {
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
    refs_impl(bytes, true)
}
fn refs_impl(bytes: &[u8], collect: bool) -> Result<Vec<ElementRef>> {
    if bytes.len() < 8 {
        return bad();
    }
    let n = u32_at(bytes, 0) as usize;
    if n > MAX_GRAPH_SELECTION_REFS * 2 {
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
    let mut out = Vec::with_capacity(if collect { n } else { 0 });
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
        let element = match kind {
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
                    if off as usize != cursor {
                        return bad();
                    }
                    let end = cursor
                        .checked_add(len as usize)
                        .ok_or(InteractionStatus::Invalid)?;
                    let text = bytes
                        .get(start + cursor..start + end)
                        .ok_or(InteractionStatus::Invalid)?;
                    cursor = end;
                    let text = std::str::from_utf8(text).map_err(|_| InteractionStatus::Invalid)?;
                    collect.then(|| text.into())
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
        };
        if collect {
            out.push(element);
        }
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
                        let off =
                            u32::try_from(pool.len()).map_err(|_| InteractionStatus::Budget)?;
                        let len = u32::try_from(id.len()).map_err(|_| InteractionStatus::Budget)?;
                        pool.len()
                            .checked_add(id.len())
                            .filter(|n| *n < u32::MAX as usize)
                            .ok_or(InteractionStatus::Budget)?;
                        pool.extend_from_slice(id.as_bytes());
                        (off, len)
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
    pub(super) container: Container<'a>,
}
impl<'a> Request<'a> {
    pub fn decode(bytes: &'a [u8]) -> Result<Self> {
        let c = gf(Container::decode(bytes, REQUEST_MAGIC))?;
        let get = |name| c.get(name, 0).ok_or(InteractionStatus::Invalid);
        if get("header.u64")?.count != 3 || get("header.u32")?.count != 9 {
            return bad();
        }
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
            0 | 5 | 8 => &[5],
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
            || (matches!(operation, 0 | 13) && w[5] > 1)
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
                "coordinates.f64"
                    if (operation == 0 && w[5] == 0) || matches!(operation, 1..=3 | 14) =>
                {
                    Some(Dtype::F64)
                }
                "refs.bytes" if matches!(operation, 6 | 9 | 11 | 12 | 13 | 14) => {
                    Some(Dtype::Bytes)
                }
                "uuids.uuid" if operation == 10 => Some(Dtype::Uuid),
                "remote.bytes" if operation == 16 => Some(Dtype::Bytes),
                "companion.u32" if matches!(operation, 17 | RENDER) => Some(Dtype::U32),
                "temporal.u64" if operation == 18 => Some(Dtype::U64),
                "document.bytes" if matches!(operation, OPEN | UPDATE) => Some(Dtype::Bytes),
                "load.x.f64" | "load.y.f64" | "load.cose.f64" | "load.cose.bounds.f64"
                    if matches!(operation, OPEN | UPDATE) =>
                {
                    Some(Dtype::F64)
                }
                "load.collapsed.u8" | "load.pinned.u8" | "load.progressive.u8"
                    if matches!(operation, OPEN | UPDATE) =>
                {
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
            refs_impl(s.payload, false)?;
            if u32_at(s.payload, 0) as usize > MAX_GRAPH_SELECTION_REFS {
                return Err(InteractionStatus::SelectionTooLarge);
            }
        }
        if let Some(s) = r.container.get("remote.bytes", 0) {
            validate_event(s.payload)?;
        }
        if let Some(s) = r.container.get("coordinates.f64", 0) {
            if s.payload
                .chunks_exact(8)
                .any(|v| !f64::from_le_bytes(v.try_into().unwrap()).is_finite())
            {
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
        let progressive = match self
            .container
            .get("load.progressive.u8", 0)
            .map(|s| s.payload)
        {
            None | Some([0]) => false,
            Some([1]) => true,
            _ => return bad(),
        };
        let mut cose = crate::graph::CoseOptions::default();
        if let Some(values) = f64s("load.cose.f64")? {
            let [ideal_edge_length, repulsion_strength, gravity_strength, cooling_factor, overlap_padding, component_spacing] =
                values.as_slice()
            else {
                return bad();
            };
            cose = crate::graph::CoseOptions {
                ideal_edge_length: *ideal_edge_length,
                repulsion_strength: *repulsion_strength,
                gravity_strength: *gravity_strength,
                cooling_factor: *cooling_factor,
                overlap_padding: *overlap_padding,
                component_spacing: *component_spacing,
                bounds: None,
            };
        }
        if let Some(values) = f64s("load.cose.bounds.f64")? {
            cose.bounds = Some(values.try_into().map_err(|_| InteractionStatus::Invalid)?);
        }
        if !cose.is_valid() {
            return bad();
        }
        Ok(SessionLoad {
            x: f64s("load.x.f64")?,
            y: f64s("load.y.f64")?,
            collapsed: flags("load.collapsed.u8"),
            pinned: flags("load.pinned.u8"),
            budgets,
            seed,
            progressive,
            cose,
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
        if s.count != 2 {
            return bad();
        }
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
// Validate transport identities and canonical ordering by borrowed UTF-8 slices;
// no arbitrary string is cloned before resource admission.
fn validate_event(bytes: &[u8]) -> Result<()> {
    let c = gf(Container::decode(bytes, REQUEST_MAGIC))?;
    for (name, index, s) in &c.sections {
        if *index != 0
            || !matches!(
                (*name, s.dtype),
                ("remote.u64", Dtype::U64)
                    | ("remote.generation.uuid", Dtype::Uuid)
                    | ("refs.bytes", Dtype::Bytes)
            )
        {
            return bad();
        }
    }
    let h = c.get("remote.u64", 0).ok_or(InteractionStatus::Invalid)?;
    if h.count != 3 || u64_at(h.payload, 8) == 0 || u64_at(h.payload, 16) == 0 {
        return bad();
    }
    if c.get("remote.generation.uuid", 0)
        .is_some_and(|s| s.count != 1)
    {
        return bad();
    }
    let b = c
        .get("refs.bytes", 0)
        .ok_or(InteractionStatus::Invalid)?
        .payload;
    refs_impl(b, false)?;
    let n = u32_at(b, 0) as usize;
    if n > MAX_GRAPH_SELECTION_REFS {
        return Err(InteractionStatus::SelectionTooLarge);
    }
    let pool = &b[8 + n * REF_BYTES..];
    let mut previous = None;
    for r in b[8..8 + n * REF_BYTES].chunks_exact(REF_BYTES) {
        let kind = u32_at(r, 0);
        if kind == 3 {
            return bad();
        }
        let id = if kind == 2 {
            let off = u32_at(r, 48);
            let len = u32_at(r, 52) as usize;
            if off == u32::MAX {
                None
            } else {
                Some(&pool[off as usize..off as usize + len])
            }
        } else {
            None
        };
        let key = (
            kind,
            &r[8..24],
            id,
            u32_at(r, 24),
            u64_at(r, 32),
            u64_at(r, 40),
        );
        if previous.is_some_and(|p| p >= key) {
            return bad();
        }
        previous = Some(key);
    }
    Ok(())
}
pub fn decode_event(bytes: &[u8]) -> Result<GraphCoordinationEvent> {
    validate_event(bytes)?;
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
pub use super::wire_packet::RetryPacket;
pub struct WireSession {
    session: GraphSession,
    plain: Option<super::wire_memory::Plain>,
    document: Vec<u8>,
    opening: Arc<RetryPacket>,
    document_range: std::ops::Range<usize>,
    open_reply: Vec<u8>,
    last_request: Arc<RetryPacket>,
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
    /// Borrow only an actually published frame from this exact temporal owner.
    /// The native caller holds session -> temporal locks in that order.
    pub fn frozen_publication(
        &self,
        owner: usize,
        handle: TemporalHandle,
        frame_revision: u64,
        render_revision: u32,
    ) -> Result<crate::temporal_graph_frozen::Publication<'_>> {
        match &self.session.slot {
            StateSlot::Bound {
                host,
                handle: bound,
            } if *bound == handle && host.owner_identity() == owner => {}
            _ => return Err(InteractionStatus::Invalid),
        }
        let render = self.session.published().ok_or(InteractionStatus::Stale)?;
        if self.session.seen_temporal != frame_revision || render.revision != render_revision {
            return Err(InteractionStatus::Stale);
        }
        let c = gf(Container::decode(&self.last_reply, RESULT_MAGIC))?;
        let h = gf(c
            .get("header.u32", 0)
            .ok_or(InteractionStatus::Stale)?
            .as_u32("header.u32"))?;
        if h.first().copied() != Some(render_revision) {
            return Err(InteractionStatus::Stale);
        }
        let mut authority = None;
        if let StateSlot::Bound { host, handle } = &self.session.slot {
            host.with_graph(*handle, &mut |g| {
                if g.applied_revision() == frame_revision {
                    authority = Some(g.instance_token());
                }
            });
        }
        let graph_token = authority.ok_or(InteractionStatus::Stale)?;
        let c = self.session.camera.ok_or(InteractionStatus::Invalid)?;
        Ok(crate::temporal_graph_frozen::Publication {
            resident_bytes: self.retained_budget(),
            graph_token,
            temporal_revision: frame_revision,
            camera: [
                c.scale_x,
                c.scale_y,
                c.offset_x,
                c.offset_y,
                c.viewport_width,
                c.viewport_height,
                c.dpr,
            ],
            document: &self.document,
            reply: &self.last_reply,
            instance: self.session.instance_id,
            revision: render_revision,
        })
    }
    pub fn session(&self) -> &GraphSession {
        &self.session
    }
    // Peak envelope, not an RSS measurement. Row reservation includes old/new
    // source/publication/route/layout arrays; grid includes compound bands.
    pub(super) fn charge(
        document: usize,
        n: usize,
        m: usize,
        watermarks: usize,
        text: usize,
    ) -> Option<usize> {
        let rows = n.checked_add(m)?;
        let state = rows
            .min(MAX_GRAPH_SELECTION_REFS)
            .checked_mul(4)?
            .checked_add(n)?
            .checked_add(1)?;
        let primitives = n.checked_mul(2)?.checked_add(m.checked_mul(11)?)?;
        98_304usize
            // S5a GPU columns: old/new output, builder/final/cached copies,
            // f64/f32/byte column scratch and focused reducer facts. At most
            // one frame/node and eleven shafts+heads/source edge. Reserve
            // BEFORE cloning a candidate, including Update's new envelope.
            .checked_add(16_384)?
            .checked_add(n.checked_mul(2048)?)?
            .checked_add(m.checked_mul(8192)?)?
            .checked_add(document.checked_mul(48)?)?
            .checked_add(rows.checked_mul(8192)?)?
            .checked_add(
                primitives
                    .checked_mul(4096)?
                    .min(MAX_GRAPH_PICK_GRID_ENTRIES)
                    .checked_mul(16)?,
            )?
            .checked_add(watermarks.checked_mul(128)?)?
            .checked_add(state.checked_mul(1024)?)?
            .checked_add(text.checked_mul(128)?)
    }
    // Scan borrowed document text BEFORE identity/label expansion. TextList is
    // already expanded per row, including labels compiled from dictionaries.
    fn document_charge(bytes: &[u8], watermarks: usize) -> Result<usize> {
        let c = gf(Container::decode(
            bytes,
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
        let mut text = 0usize;
        let mut longest = 0usize;
        for (name, _, s) in &c.sections {
            let len = if *name == "layer.result_id" {
                let len = gf(s.as_utf8(name))?.len();
                longest = longest.max(len);
                len
            } else if matches!(*name, "node.label" | "edge.label") {
                if s.dtype != Dtype::TextList {
                    return bad();
                }
                // Validated monotonic offsets partition this entire UTF-8 pool.
                let head = s
                    .count
                    .checked_add(1)
                    .and_then(|v| v.checked_mul(8))
                    .ok_or(InteractionStatus::Budget)?;
                let pool = s.payload.get(head..).ok_or(InteractionStatus::Invalid)?;
                std::str::from_utf8(pool).map_err(|_| InteractionStatus::Invalid)?;
                pool.len()
            } else {
                0
            };
            text = text.checked_add(len).ok_or(InteractionStatus::Budget)?;
        }
        // Every edge may repeat the longest ID in state/changed/event pools.
        text = text
            .checked_add(m.checked_mul(longest).ok_or(InteractionStatus::Budget)?)
            .ok_or(InteractionStatus::Budget)?;
        let mut projection = n
            .checked_add(m)
            .ok_or(InteractionStatus::Budget)?
            .min(MAX_GRAPH_SELECTION_REFS)
            .checked_mul(256)
            .and_then(|v| v.checked_add(8192))
            .ok_or(InteractionStatus::Budget)?;
        // Reserve all new tables/scratch BEFORE cloning the candidate. No
        // source-sized row Vec: each plane contributes at most the selection cap.
        for (name, _, section) in &c.sections {
            if matches!(*name, "layer.node_rows" | "layer.edge_rows") {
                let count = if *name == "layer.node_rows" { n } else { m };
                if section.dtype != Dtype::U64 || section.count != count {
                    return bad();
                }
                projection = projection
                    .checked_add(
                        count
                            .min(MAX_GRAPH_SELECTION_REFS)
                            .checked_add(1)
                            .ok_or(InteractionStatus::Budget)?
                            .checked_mul(128)
                            .ok_or(InteractionStatus::Budget)?,
                    )
                    .ok_or(InteractionStatus::Budget)?;
            } else if *name == "layer.schema" {
                projection = projection
                    .checked_add(256)
                    .ok_or(InteractionStatus::Budget)?;
            }
        }
        Self::charge(bytes.len(), n, m, watermarks, text)
            .and_then(|v| v.checked_add(projection))
            .ok_or(InteractionStatus::Budget)
    }
    pub(super) fn state_charge(state: &GraphInteractionState) -> Option<usize> {
        Self::state_charge_width(state, 1024)
    }
    pub(super) fn uuid_state_charge(state: &GraphInteractionState) -> Option<usize> {
        Self::state_charge_width(state, 288)?.checked_add(736)
    }
    #[cfg_attr(target_arch = "wasm32", inline(never))]
    fn state_charge_width(state: &GraphInteractionState, width: usize) -> Option<usize> {
        let mut count = state.pinned_nodes().len().checked_add(1)?;
        let mut text = 0usize;
        for set in std::iter::once(state.selection()).chain(
            [
                HighlightPlane::Path,
                HighlightPlane::Community,
                HighlightPlane::External,
            ]
            .iter()
            .map(|p| state.highlight_set(*p)),
        ) {
            count = count.checked_add(set.len())?;
            for key in &set.derived {
                text = text.checked_add(key.result_id.as_ref().map_or(0, |s| s.len()))?;
            }
        }
        if let Some(crate::graph_interaction_state::Focus::Derived(key)) = state.focus() {
            text = text.checked_add(key.result_id.as_ref().map_or(0, |s| s.len()))?;
        }
        count
            .checked_mul(width)?
            .checked_add(text.checked_mul(128)?)
    }
    pub fn retained_budget(&self) -> usize {
        self.plain
            .filter(|p| p.retains(&self.session))
            .and_then(|p| self.physical_retained(p))
            .unwrap_or_else(|| self.general_retained())
    }
    /// Requested-byte capacities by owner, with conservative reducer reserves.
    /// Native allocator overhead/RSS and WASM linear free lists are separate.
    /// Order: fixed, identity, source/auxiliary, positions, force, publication,
    /// retry packets, encoded replies, state/events. Their sum is retained_budget.
    pub fn ownership_bytes(&self) -> Result<[usize; 9]> {
        let p = self
            .plain
            .filter(|p| p.retains(&self.session))
            .ok_or(InteractionStatus::Invalid)?;
        let s = &self.session;
        let identity = s
            .source
            .identity
            .plain_retained_bytes()
            .ok_or(InteractionStatus::Budget)?;
        let positions = s
            .positions
            .as_ref()
            .map_or(Some(0), |(x, y)| {
                x.capacity().checked_add(y.capacity())?.checked_mul(8)
            })
            .ok_or(InteractionStatus::Budget)?;
        let force = s
            .relayout
            .as_ref()
            .map_or(Some(0), |r| r.retained_bytes(&s.source.parent))
            .ok_or(InteractionStatus::Budget)?;
        let publication = s
            .published
            .as_ref()
            .map_or(Some(0), |r| super::wire_memory::publication_bytes(r))
            .ok_or(InteractionStatus::Budget)?;
        let known = [98_304, identity, positions, force, publication]
            .into_iter()
            .try_fold(0usize, usize::checked_add)
            .ok_or(InteractionStatus::Budget)?;
        let source = p
            .retained(s)
            .and_then(|n| n.checked_sub(known))
            .ok_or(InteractionStatus::Budget)?;
        let mut packets = self
            .opening
            .owned_bytes(s)
            .ok_or(InteractionStatus::Budget)?;
        if !Arc::ptr_eq(&self.opening, &self.last_request) {
            packets = packets
                .checked_add(
                    self.last_request
                        .owned_bytes(s)
                        .ok_or(InteractionStatus::Budget)?,
                )
                .ok_or(InteractionStatus::Budget)?;
        }
        packets = packets
            .checked_add(self.document.capacity())
            .ok_or(InteractionStatus::Budget)?;
        let replies = self
            .open_reply
            .capacity()
            .checked_add(self.last_reply.capacity())
            .ok_or(InteractionStatus::Budget)?;
        let state = (match &s.slot {
            StateSlot::Owned(st) => Self::uuid_state_charge(st).ok_or(InteractionStatus::Budget)?,
            _ => 0,
        })
        .checked_add(
            s.pending_outbound()
                .map_or(0, |e| e.refs.capacity())
                .checked_mul(std::mem::size_of::<ElementRef>())
                .ok_or(InteractionStatus::Budget)?,
        )
        .ok_or(InteractionStatus::Budget)?;
        Ok([
            98_304,
            identity,
            source,
            positions,
            force,
            publication,
            packets,
            replies,
            state,
        ])
    }
    pub fn preflight_bytes(&self, request: &[u8], external: usize) -> Result<usize> {
        self.admit(request, external)
    }
    fn physical_retained(&self, plain: super::wire_memory::Plain) -> Option<usize> {
        let mut n = plain
            .retained(&self.session)?
            .checked_add(self.document.capacity())?
            .checked_add(self.opening.owned_bytes(&self.session)?)?
            .checked_add(self.open_reply.capacity())?
            .checked_add(self.last_reply.capacity())?;
        if !Arc::ptr_eq(&self.opening, &self.last_request) {
            n = n.checked_add(self.last_request.owned_bytes(&self.session)?)?;
        }
        if let StateSlot::Owned(state) = &self.session.slot {
            n = n.checked_add(Self::uuid_state_charge(state)?)?;
        }
        n = n.checked_add(
            self.session
                .pending_outbound()
                .map_or(0, |e| e.refs.capacity())
                .checked_mul(std::mem::size_of::<ElementRef>())?,
        )?;
        Some(n)
    }
    fn general_retained(&self) -> usize {
        (if self.document.is_empty() {
            self.plain
                .and_then(|p| p.general_charge(self.session.coordination.gate.len()))
        } else {
            Self::document_charge(&self.document, self.session.coordination.gate.len()).ok()
        })
        .and_then(|n| {
            n.checked_add(match &self.session.slot {
                StateSlot::Owned(state) => Self::state_charge(state)?,
                _ => 0,
            })
        })
        .and_then(|n| {
            let text = self.session.pending_outbound().map_or(Some(0), |e| {
                e.refs
                    .iter()
                    .map(|r| match r {
                        ElementRef::Derived(d) => match &d.result {
                            ResultRef::Exact(Some(s)) => s.len(),
                            _ => 0,
                        },
                        _ => 0,
                    })
                    .try_fold(0usize, |sum, len| sum.checked_add(len))
            })?;
            n.checked_add(text.checked_mul(128)?)
        })
        .and_then(|n| n.checked_add(self.last_request.len().checked_mul(3)?))
        .and_then(|n| n.checked_add(self.opening.len().checked_mul(3)?))
        .and_then(|n| n.checked_add(self.open_reply.len().checked_mul(3)?))
        .and_then(|n| n.checked_add(self.last_reply.len().checked_mul(3)?))
        .unwrap_or(usize::MAX)
    }
    // OPEN/UPDATE borrow document.bytes throughout decoding. Its expansions
    // (including labels and repeated derived IDs) are reserved by document_charge,
    // not by the generic event/ref text envelope. The only additional document
    // ownership is serialized retry caches: OPEN retains opening + last_request;
    // UPDATE replaces last_request. Reserve both, at the existing 3x cache bound.
    fn request_charge(request_bytes: usize, document_bytes: usize) -> Result<usize> {
        request_bytes
            .checked_mul(128)
            .and_then(|v| v.checked_sub(document_bytes.checked_mul(122)?))
            .ok_or(InteractionStatus::Budget)
    }
    fn admit(&self, request: &[u8], external: usize) -> Result<usize> {
        let r = Request::decode(request)?;
        let (replacement, document_bytes) = if r.operation == UPDATE {
            let document = r.document()?;
            (Self::document_charge(document, 0)?, document.len())
        } else {
            (0, 0)
        };
        let plain = self.plain.filter(|p| p.applies(&self.session, &r));
        let request_charge = Self::request_charge(request.len(), document_bytes)?;
        let charge = if let Some(p) = plain {
            let old = self.physical_retained(p).ok_or(InteractionStatus::Budget)?;
            let private = p
                .clone_peak(&self.session, &r)
                .ok_or(InteractionStatus::Budget)?;
            let work = private
                .checked_add(
                    p.kernel_peak(&self.session)
                        .ok_or(InteractionStatus::Budget)?,
                )
                .ok_or(InteractionStatus::Budget)?
                .max(
                    p.force_peak(&self.session, &r)
                        .ok_or(InteractionStatus::Budget)?,
                )
                .max(if matches!(r.operation, 0 | 1 | 5 | 6 | 7 | 8) {
                    private
                        .checked_add(
                            // A point/focus target expands one source kind.
                            // The retained index bounds candidate storage: u32
                            // B-tree nodes <=160 bytes plus growable Primitive
                            // rows <=32 bytes, including the cap+1 refusal.
                            p.n.max(p.m).min(MAX_GRAPH_SELECTION_REFS) * 1024
                                + self.session.published().map_or(0, |v| {
                                    v.pick.primitive_count().min(MAX_GRAPH_PICK_CANDIDATES + 1)
                                        * 192
                                }),
                        )
                        .ok_or(InteractionStatus::Budget)?
                } else {
                    0
                });
            old.checked_add(work)
                .and_then(|v| v.checked_add(request_charge))
                .and_then(|v| v.checked_add(external))
        } else {
            self.general_retained()
                .checked_add(request_charge)
                .and_then(|v| v.checked_add(external))
                .and_then(|v| v.checked_add(replacement))
        }
        .ok_or(InteractionStatus::Budget)?;
        if charge > self.max_bytes {
            return Err(InteractionStatus::Budget);
        }
        Ok(charge)
    }
    pub fn open(bytes: &[u8], max_bytes: usize, external: usize) -> Result<Self> {
        let r = Request::decode(bytes)?;
        if r.operation != OPEN || r.words[0] != 0 {
            return bad();
        }
        let document = r.document()?;
        let certified = super::wire_memory::Plain::recognize(document)
            .and_then(|p| p.open_peak(&r, bytes.len()).map(|charge| (p, charge)));
        let charge = if let Some((_, charge)) = certified {
            charge
                .checked_add(external)
                .ok_or(InteractionStatus::Budget)?
        } else {
            Self::document_charge(document, 0)?
                .checked_add(Self::request_charge(bytes.len(), document.len())?)
                .and_then(|v| v.checked_add(external))
                .ok_or(InteractionStatus::Budget)?
        };
        let plain = certified.map(|(p, _)| p);
        if charge > max_bytes {
            return Err(InteractionStatus::Budget);
        }
        let session = GraphSession::create_linked(document, r.load()?, r.instance, r.group)?;
        let start = document.as_ptr() as usize - bytes.as_ptr() as usize;
        let opening = if plain.is_some() {
            RetryPacket::certified(bytes, &r, &session)
        } else {
            RetryPacket::raw(bytes)
        };
        let mut out = Self {
            session,
            plain,
            document: if plain.is_some() {
                Vec::new()
            } else {
                document.to_vec()
            },
            document_range: start..start + document.len(),
            opening: Arc::clone(&opening),
            open_reply: Vec::new(),
            last_request: opening,
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
        self.opening.matches(bytes)
    }
    pub fn opening_record(&self) -> Arc<RetryPacket> {
        Arc::clone(&self.opening)
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
            if !self.last_request.matches(bytes) {
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
        let admitted = self.admit(bytes, external)?;
        let transaction_bytes = if let Some(p) = self.plain.filter(|p| p.applies(&self.session, &r))
        {
            Some(
                (|| {
                    self.physical_retained(p)?
                        .checked_add(Self::request_charge(bytes.len(), 0).ok()?)?
                        .checked_add(external)?
                        .checked_add(p.clone_peak(&self.session, &r)?)
                        .and_then(|v| self.max_bytes.checked_sub(v))
                })()
                .ok_or(InteractionStatus::Budget)?,
            )
        } else {
            None
        };
        // Bind changes owners. Validate candidate against the new owner before
        // installing it; no state mutation occurs in that owner.
        let max_bytes = self.max_bytes;
        let restored_document = if r.operation == 18 && self.document.is_empty() {
            Some(self.opening.range(self.document_range.clone()))
        } else {
            None
        };
        let document = restored_document.as_deref().unwrap_or(&self.document);
        let result = if r.operation == 18 {
            let mut next = self.session.clone();
            let same_owner = r.temporal()? != 0
                && match (&self.session.slot, &bind) {
                    (StateSlot::Bound { host, handle }, Some((new_host, new_handle))) => {
                        host.owner_identity() == new_host.owner_identity() && handle == new_handle
                    }
                    _ => false,
                };
            let (candidate, reply) = if r.temporal()? == 0 {
                next.unbind()?;
                let (candidate, reply) = Self::finish(next, &r, OpOutcome::default(), document)?;
                (Some(candidate), reply)
            } else {
                let (host, handle) = bind.ok_or(InteractionStatus::Unbound)?;
                let (mut next, mut output) = (Some(next), None);
                let found = host.with_graph(handle, &mut |graph| {
                    let mut next = next.take().expect("one owner access");
                    output = Some((|| {
                        if same_owner {
                            Self::validate_owner_stamp(
                                &next,
                                r.header.stamp,
                                graph.applied_revision(),
                            )?;
                        }
                        if Self::state_charge(graph.interaction_state())
                            .and_then(|v| v.checked_add(admitted))
                            .is_none_or(|v| v > max_bytes)
                        {
                            return Err(InteractionStatus::Budget);
                        }
                        if next.source.identity.node_uuids() != graph.node_ids()
                            || !next
                                .source
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
                        let outcome = OpOutcome {
                            selected: state.selection().len(),
                            ..OpOutcome::default()
                        };
                        let (mut candidate, reply) =
                            Self::finish(candidate, &r, outcome, document)?;
                        candidate.slot = StateSlot::Bound {
                            host: Arc::clone(&host),
                            handle,
                        };
                        if reply
                            .len()
                            .checked_mul(3)
                            .and_then(|v| v.checked_add(external))
                            .is_none_or(|v| v > max_bytes)
                        {
                            return Err(InteractionStatus::Budget);
                        }
                        if same_owner {
                            self.session = candidate;
                            Ok((None, reply))
                        } else {
                            Ok((Some(candidate), reply))
                        }
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
            if !same_owner {
                // Build the destination snapshot first, release its lock, then
                // validate the current owner and install under that one lock.
                // Never nest old/new owner locks, including cross-owner binds.
                let mut candidate = candidate;
                let was_owned = matches!(self.session.slot, StateSlot::Owned(_));
                let installed = self.session.locked(|session, world| {
                    Self::validate_owner_stamp(session, r.header.stamp, world.temporal_revision)?;
                    if !was_owned {
                        *session = candidate.take().expect("one commit");
                    }
                    Ok::<(), InteractionStatus>(())
                });
                match installed {
                    Ok(result) => {
                        result?;
                        if was_owned {
                            self.session = candidate.take().expect("owned commit");
                        }
                    }
                    Err(InteractionStatus::Unbound) if r.temporal()? == 0 => {
                        Self::validate_owner_stamp(
                            &self.session,
                            r.header.stamp,
                            self.session.seen_temporal,
                        )?;
                        self.session = candidate.take().expect("disposed owner recovery");
                    }
                    Err(error) => return Err(error),
                }
            }
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
                    if (if transaction_bytes.is_some() {
                        Some(0)
                    } else {
                        Self::state_charge(world.state)
                    })
                    .and_then(|v| v.checked_add(admitted))
                    .is_none_or(|v| v > max_bytes)
                    {
                        return Err(InteractionStatus::Budget);
                    }
                    let mut next = session.candidate(&world);
                    next.transaction_bytes = transaction_bytes;
                    let outcome = apply(&mut next, &r)?;
                    let (mut next, reply) = Self::finish(next, &r, outcome, document)?;
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
        if let Some(document) = restored_document {
            self.document = document;
        }
        if r.operation == UPDATE {
            self.document = r.document()?.to_vec();
            self.plain = super::wire_memory::Plain::recognize(&self.document);
        }
        self.last_request = RetryPacket::raw(bytes);
        self.last_sequence = r.sequence;
        Ok(&self.last_reply)
    }
    fn validate_owner_stamp(
        session: &GraphSession,
        stamp: Stamp,
        temporal_revision: u64,
    ) -> Result<()> {
        if stamp.instance_id != session.instance_id
            || stamp.render_revision != session.render_revision
            || temporal_revision != session.seen_temporal
        {
            return Err(InteractionStatus::Stale);
        }
        Ok(())
    }
    fn finish(
        mut next: GraphSession,
        r: &Request<'_>,
        outcome: OpOutcome,
        document: &[u8],
    ) -> Result<(GraphSession, Vec<u8>)> {
        let camera = if r.operation == RENDER {
            r.camera()?
        } else {
            next.camera
        };
        next.render(camera)?;
        let capacity = if let Some(available) = next.transaction_bytes {
            let p = next.published().ok_or(InteractionStatus::Stale)?;
            let refs = next
                .read_state(|s| s.selection().len() + s.pinned_nodes().len())?
                .checked_add(outcome.changed.len())
                .and_then(|n| n.checked_add(next.pending_outbound().map_or(0, |e| e.refs.len())))
                .ok_or(InteractionStatus::Budget)?;
            let bound =
                super::wire_memory::serialized_bound(p, refs).ok_or(InteractionStatus::Budget)?;
            let bytes = super::wire_memory::publication_bytes(p)
                .and_then(|n| n.checked_add(bound.checked_mul(2)?))
                .ok_or(InteractionStatus::Budget)?;
            if bytes > available {
                return Err(InteractionStatus::Budget);
            }
            Some(bound)
        } else {
            None
        };
        let reply = serialize(
            &mut next,
            r,
            &outcome,
            capacity,
            if r.operation == UPDATE {
                r.document()?
            } else {
                document
            },
        )?;
        next.transaction_world = None;
        next.transaction_bytes = None;
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
        self.last_request = RetryPacket::raw(bytes);
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
        0 if r.words[5] == 1 => s.hover_leave(h),
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
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut text = String::with_capacity(32);
    for &byte in id {
        text.push(char::from(HEX[usize::from(byte >> 4)]));
        text.push(char::from(HEX[usize::from(byte & 15)]));
    }
    text
}
fn transport(s: &GraphSession, refs: &[ElementRef]) -> Result<Vec<ElementRef>> {
    refs.iter()
        .map(|r| {
            s.source
                .identity
                .to_transport(r)
                .or_else(|| matches!(r, ElementRef::Aggregate(_)).then(|| r.clone()))
                .ok_or(InteractionStatus::Invalid)
        })
        .collect()
}
// Complete snapshot, independent of changed.refs and coordination. Work is
// O(layers * selected), with borrowed row planes and exact u64 source rows.
#[cfg_attr(target_arch = "wasm32", inline(never))]
fn selection_projection(
    b: &mut Builder,
    s: &GraphSession,
    state: &GraphInteractionState,
    bytes: &[u8],
    pick: Option<&PickReceipt>,
) -> Result<()> {
    let doc = if bytes.is_empty() {
        None
    } else {
        Some(gf(ComposedDocument::decode(bytes))?)
    };
    let refs = transport(s, &s.source.identity.refs_of(state.selection()))?;
    // The temporal owner may retain derived keys belonging to another
    // composition. refs_of deliberately omits those without mutating the owner.
    if refs.len() > MAX_GRAPH_SELECTION_REFS {
        return bad();
    }
    // Canonical state trees already use exactly the transport comparator:
    // node UUID, edge UUID, then exact result ID/layer/path/order. Filtering
    // foreign derived keys preserves order; no copied sort buffer is needed.
    debug_assert!(refs
        .windows(2)
        .all(|p| super::coordination::compare(&p[0], &p[1]) == std::cmp::Ordering::Less));
    let picked_source = pick.and_then(|p| p.source.as_ref());
    let selected = refs.len();
    let targets = selected + usize::from(picked_source.is_some());
    let work = if let Some(doc) = &doc {
        doc.projection_work(targets)
            .ok_or(InteractionStatus::Budget)?
    } else {
        0
    };
    if work as u64 > MAX_GRAPH_INTERACTION_WORK {
        return Err(InteractionStatus::Budget);
    }
    #[cfg(test)]
    projection_probe::admit(targets);
    // Admit both sparse passes before allocating combined projection scratch.
    // The optional source is deliberately duplicated even if already selected.
    let mut resolved = Vec::with_capacity(targets);
    for reference in &refs {
        resolved.push(
            s.source
                .identity
                .resolve(reference)
                .map_err(|_| InteractionStatus::Invalid)?,
        );
    }
    if let Some((index, _)) = picked_source {
        resolved.push(*index);
    }
    let planes = if let Some(doc) = &doc {
        gf(doc.projection_layers(
            s.source.identity.node_count(),
            s.source.identity.edge_count(),
        ))?
    } else {
        Vec::new()
    };
    #[cfg(test)]
    projection_probe::borrow();
    let row = |index: ElementIndex, layer: usize| -> Option<u64> {
        #[cfg(test)]
        projection_probe::row();
        let (plane, i) = match index {
            ElementIndex::Node(i) => (planes[layer].node_rows?, i),
            ElementIndex::Edge(i) => (planes[layer].edge_rows?, i),
        };
        let value = u64_at(plane, i * 8);
        (value != u64::MAX).then_some(value)
    };
    // Count the actual sparse output before allocating it. Reservation above
    // includes builder/final/retry copies (existing cache charge is 3x bytes).
    let count = resolved
        .iter()
        .try_fold(0usize, |sum, &index| {
            sum.checked_add(
                (0..planes.len())
                    .filter(|&layer| row(index, layer).is_some())
                    .count(),
            )
        })
        .ok_or(InteractionStatus::Budget)?;
    #[cfg(test)]
    projection_probe::output(count);
    let mut indices = Vec::with_capacity(targets);
    let mut offsets = Vec::with_capacity(targets + 1);
    let mut layers = Vec::with_capacity(count);
    let mut rows = Vec::with_capacity(count);
    offsets.push(0);
    for index in resolved {
        indices.push(match index {
            ElementIndex::Node(i) | ElementIndex::Edge(i) => i as u64,
        });
        for layer in 0..planes.len() {
            if let Some(value) = row(index, layer) {
                layers.push(layer as u32);
                rows.push(value);
            }
        }
        offsets.push(rows.len() as u64);
    }
    let texts = planes
        .iter()
        .map(|layer| layer.result_id.unwrap_or(""))
        .collect::<Vec<_>>();
    let valid = planes
        .iter()
        .map(|layer| u8::from(layer.result_id.is_some()))
        .collect::<Vec<_>>();
    b.bytes("selection.refs.bytes", 0, &encode_refs(&refs)?);
    let boundary = offsets[selected] as usize;
    b.u64s("selection.indices.u64", 0, &indices[..selected]);
    b.u64s("selection.layer_offsets.u64", 0, &offsets[..=selected]);
    b.u32s("selection.layers.u32", 0, &layers[..boundary]);
    b.u64s("selection.rows.u64", 0, &rows[..boundary]);
    b.texts("selection.result_ids.texts", 0, &texts);
    b.u8s("selection.result_ids.valid.u8", 0, &valid);
    if let Some(pick) = pick {
        let (kind, render_index) = match pick.target {
            None => (0, 0),
            Some(PickTarget::Node(i)) => (1, i as u64),
            Some(PickTarget::Edge(i)) => (2, i as u64),
        };
        let form = if kind == 0 {
            0
        } else if pick.source.is_some() {
            1
        } else {
            2
        };
        let (source_index, pick_refs) = match picked_source {
            Some((ElementIndex::Node(i) | ElementIndex::Edge(i), reference)) => {
                (*i as u64, std::slice::from_ref(reference))
            }
            None => (0, &[][..]),
        };
        b.u32s(
            "pick.header.u32",
            0,
            &[
                1,
                pick.operation,
                pick.action,
                pick.header.stamp.render_revision,
                kind,
                form,
                0,
                0,
            ],
        );
        b.u64s(
            "pick.query.u64",
            0,
            &[
                pick.header.stamp.instance_id,
                pick.header.op_seq,
                render_index,
                pick.member_count,
                source_index,
            ],
        );
        b.bytes("pick.ref.bytes", 0, &encode_refs(pick_refs)?);
        b.u32s("pick.layers.u32", 0, &layers[boundary..]);
        b.u64s("pick.rows.u64", 0, &rows[boundary..]);
    }
    Ok(())
}

fn serialize(
    s: &mut GraphSession,
    r: &Request<'_>,
    out: &OpOutcome,
    capacity: Option<usize>,
    document: &[u8],
) -> Result<Vec<u8>> {
    let mut b = Builder::with_capacity(RESULT_MAGIC, capacity.unwrap_or(0));
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
    super::wire_paint::encode(&mut b, &render.paint);
    super::gpu::encode(&mut b, render)?;
    b.u32s(
        "outcome.u32",
        0,
        &[
            1,
            u32::from(out.state_changed),
            out.selected
                .try_into()
                .map_err(|_| InteractionStatus::Budget)?,
            u32::from(out.disclosure.is_some()),
        ],
    );
    let disclosure = out
        .disclosure
        .as_ref()
        .map(|d| d.node.clone())
        .into_iter()
        .collect::<Vec<_>>();
    b.bytes(
        "disclosure.ref.bytes",
        0,
        &encode_refs(&transport(s, &disclosure)?)?,
    );
    b.u8s(
        "disclosure.collapsed.u8",
        0,
        &out.disclosure
            .as_ref()
            .map(|d| u8::from(d.collapsed))
            .into_iter()
            .collect::<Vec<_>>(),
    );
    b.u32s("node.flags.u32", 0, &render.source_node_flags);
    b.u32s("edge.flags.u32", 0, &render.source_edge_flags);
    let state = s.read_state(Clone::clone)?;
    b.u32s("clear.action.u32", 0, &[1, u32::from(state.can_clear())]);
    selection_projection(&mut b, s, &state, document, out.pick.as_ref())?;
    let focus = s.focus()?.into_iter().collect::<Vec<_>>();
    b.bytes("focus.bytes", 0, &encode_refs(&transport(s, &focus)?)?);
    focus_actions(&mut b, s, &state)?;
    b.bytes(
        "changed.refs.bytes",
        0,
        &encode_refs(&transport(s, &out.changed)?)?,
    );
    let (page, size) = r.page()?;
    let start = page.checked_mul(size).ok_or(InteractionStatus::Invalid)?;
    let total = s
        .source
        .identity
        .node_count()
        .checked_add(s.source.identity.edge_count())
        .ok_or(InteractionStatus::Budget)?;
    let mut candidates = Vec::new();
    let mut rows = Vec::new();
    for i in start..start.saturating_add(size).min(total) {
        let (kind, index) = if i < s.source.identity.node_count() {
            ("Node", ElementIndex::Node(i))
        } else {
            (
                "Edge",
                ElementIndex::Edge(i - s.source.identity.node_count()),
            )
        };
        let reference = match index {
            ElementIndex::Node(i) => s.source.identity.node_ref(i),
            ElementIndex::Edge(i) => s.source.identity.edge_ref(i),
        };
        let exact = s
            .source
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
            _ => s
                .source
                .identity
                .resolve(&reference)
                .ok()
                .is_some_and(|idx| {
                    let mut set = ElementSet::default();
                    s.source.identity.insert_into(&mut set, idx);
                    set.derived
                        .iter()
                        .any(|k| state.selection().derived.contains(k))
                }),
        };
        let label = s.source.labels.get(i).map(String::as_str).unwrap_or("");
        let relation = match index {
            ElementIndex::Node(n) => format!(
                "{} relationships",
                s.source
                    .edge_source
                    .iter()
                    .zip(s.source.edge_target.iter())
                    .filter(|(a, b)| **a == n as u64 || **b == n as u64)
                    .count()
            ),
            ElementIndex::Edge(e) => {
                format!("{} to {}", s.source.edge_source[e], s.source.edge_target[e])
            }
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
            s.source.identity.node_count(),
            s.source.identity.edge_count(),
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
    if s.progressive {
        b.u32s(
            "relayout.admission.u32",
            0,
            &[1, s.continuation_step_limit()],
        );
    }
    if let Some(report) = out.relayout.or_else(|| {
        if s.progressive {
            s.relayout.as_ref().map(|r| r.report())
        } else {
            None
        }
    }) {
        b.u64s("relayout.steps.u64", 0, &[report.completed_steps]);
        b.f64s("relayout.alpha.f64", 0, &[report.alpha]);
        b.u8s("relayout.done.u8", 0, &[u8::from(report.done)]);
    }
    if let Some(event) = s.pending_outbound() {
        b.bytes("outbound.bytes", 0, &encode_event(event)?);
    }
    Ok(b.finish())
}

// Facts about the displayed focus, rather than its UUID state stand-in. Reuse
// the same stop resolver and disclosure reducer as operations; never advertise
// an aggregate (even a singleton) as an individually movable source node.
fn focus_actions(b: &mut Builder, s: &GraphSession, state: &GraphInteractionState) -> Result<()> {
    use crate::graph_style::{
        compound_collapse_transition, COMPOUND_ACTION_TOGGLE, MAX_COMPOUND_TRANSITION_NODES,
    };
    let render = s.published().ok_or(InteractionStatus::Stale)?;
    let mut refs = Vec::new();
    let mut facts = [1, 0, 0, 0, 0, 0, 0, 0];
    if let Some(walk::Stop::Node(r)) = s.stop_of(render, state.focus()) {
        let reference = if render.tier == crate::graph::LodTier::Aggregate {
            ElementRef::Aggregate(AggregateRef {
                render_revision: render.revision,
                index: r as u32,
            })
        } else {
            s.source
                .identity
                .node_ref(render.focus_node[r as usize] as usize)
        };
        if let render::Resolved::Element(ElementIndex::Node(node)) = s.resolve(&reference)? {
            facts[2] = u32::from(s.collapsed[node] == 1);
            facts[3] = 1;
            facts[4] = u32::from(
                state
                    .pinned_nodes()
                    .contains(&s.source.identity.node_uuids()[node]),
            );
            facts[5] = 1;
            let n = s.source.identity.node_count();
            if n <= MAX_COMPOUND_TRANSITION_NODES {
                let ids: Vec<_> = (0..n as u64).collect();
                let mut next = vec![0; n];
                facts[1] = u32::from(
                    compound_collapse_transition(
                        &ids,
                        &s.source.parent,
                        &s.source.parent_valid,
                        &s.collapsed,
                        node as u64,
                        COMPOUND_ACTION_TOGGLE,
                        render.tier as u8,
                        &mut next,
                    )
                    .is_some(),
                );
            }
        }
        refs.push(reference);
    }
    b.bytes(
        "focus.action.ref.bytes",
        0,
        &encode_refs(&transport(s, &refs)?)?,
    );
    b.u32s("focus.action.u32", 0, &facts);
    Ok(())
}
fn summary(s: &GraphSession, state: &GraphInteractionState, f: &ElementRef) -> Result<String> {
    let index = s
        .source
        .identity
        .resolve(f)
        .map_err(|_| InteractionStatus::Invalid)?;
    let (mut kind, i, ordinal, mut selected, mut relationship) = match index {
        ElementIndex::Node(i) => (
            if s.source.parent.iter().any(|p| *p == i as u64) {
                "Group"
            } else {
                "Node"
            },
            i,
            i + 1,
            state
                .selection()
                .nodes
                .contains(&s.source.identity.node_uuids()[i]),
            format!(
                "{} relationships",
                s.source
                    .edge_source
                    .iter()
                    .zip(s.source.edge_target.iter())
                    .filter(|(a, b)| **a == i as u64 || **b == i as u64)
                    .count()
            ),
        ),
        ElementIndex::Edge(i) => (
            "Edge",
            s.source.identity.node_count() + i,
            i + 1,
            match s.source.identity.edge_ref(i) {
                ElementRef::Edge(id) => state.selection().edges.contains(&id),
                _ => state
                    .selection()
                    .derived
                    .iter()
                    .any(|k| s.source.identity.resolve_derived_key(k) == Some(i)),
            },
            format!("{} to {}", s.source.edge_source[i], s.source.edge_target[i]),
        ),
    };
    if let (ElementIndex::Node(node), Some(render)) = (index, s.published()) {
        let group = render.member_of[node];
        if group != NOT_RENDERED {
            let members = render.members_of_node(group as usize);
            if members.len() > 1 {
                kind = "Group";
                selected = members.iter().any(|&n| {
                    state
                        .selection()
                        .nodes
                        .contains(&s.source.identity.node_uuids()[n as usize])
                });
                relationship = format!("group of {}, {relationship}", members.len());
            }
        }
    }
    let mut text = format!(
        "{kind} {}, {relationship}, {}, {ordinal} of {}",
        s.source.labels.get(i).map(String::as_str).unwrap_or(""),
        if selected { "selected" } else { "not selected" },
        if kind == "Edge" {
            s.source.identity.edge_count()
        } else {
            s.source.identity.node_count()
        }
    );
    if s.move_origin.is_some() {
        if let (ElementIndex::Node(n), Some((x, y))) = (index, s.positions()) {
            text.push_str(&format!(", moving, {} {}", x[n], y[n]));
        }
    }
    Ok(text)
}

#[cfg(test)]
#[path = "tests/wire/projection_reuse.rs"]
mod projection_reuse_tests;

#[cfg(test)]
#[path = "tests/wire/projection_probe.rs"]
pub(super) mod projection_probe;

#[cfg(test)]
mod plain_memory_tests {
    use super::*;
    fn document(n: usize, extra: impl FnOnce(&mut Builder)) -> Vec<u8> {
        let ids = |offset: u32| {
            (0..n)
                .map(|i| {
                    let mut id = [0; 16];
                    id[..4].copy_from_slice(&(i as u32 + offset).to_le_bytes());
                    id
                })
                .collect::<Vec<_>>()
        };
        let mut b = Builder::new(b"XYGF");
        b.u32s("status", 0, &[0]);
        b.utf8("kind", 0, "graph");
        b.u32s("composition.version", 0, &[2]);
        b.uuids("node.uuid", 0, &ids(1));
        b.uuids("edge.uuid", 0, &ids(10001));
        b.u8s("edge.derived", 0, &vec![0; n]);
        b.u32s("edge.layer", 0, &vec![u32::MAX; n]);
        b.i64s("edge.order", 0, &vec![-1; n]);
        b.u64s("edge.path", 0, &vec![u64::MAX; n]);
        b.u64s("edge.source", 0, &(0..n as u64).collect::<Vec<_>>());
        b.u64s(
            "edge.target",
            0,
            &(0..n as u64)
                .map(|i| (i + 1) % n as u64)
                .collect::<Vec<_>>(),
        );
        extra(&mut b);
        b.finish()
    }
    fn request(seq: u64, rev: u32, op: u32, doc: Option<&[u8]>) -> Vec<u8> {
        let mut b = Builder::new(REQUEST_MAGIC);
        b.u64s("header.u64", 0, &[77, 0, seq]);
        b.u32s(
            "header.u32",
            0,
            &[rev, op, 0, 0, 0, 0, 0, if op == 15 { 8 } else { 0 }, 0],
        );
        if let Some(d) = doc {
            b.bytes("document.bytes", 0, d);
            b.u8s("load.progressive.u8", 0, &[1]);
        }
        if op == RENDER {
            b.f64s("camera.f64", 0, &[0.25, 0.25, 320., 160., 640., 320., 1.]);
        }
        b.finish()
    }
    #[test]
    fn plain_open_and_repeated_publication_exact_boundaries() {
        let doc = document(1000, |_| {});
        let open = request(1, 0, OPEN, Some(&doc));
        let external = 8192;
        // Complete UUID/index source + roots/endpoints, raw cache upper bound,
        // and fixed OPEN/reducer owners; no document multiplier.
        let limit = 102_400 + 78_384 + open.len() + external;
        assert!(matches!(
            WireSession::open(&open, limit - 1, external),
            Err(InteractionStatus::Budget)
        ));
        let mut s = WireSession::open(&open, limit, external).unwrap();
        assert!(s.opening_matches(&open));
        let mut changed = open.clone();
        *changed.last_mut().unwrap() ^= 1;
        assert!(!s.opening_matches(&changed));
        for seq in 2..5 {
            let req = request(seq, s.session.render_revision, RENDER, None);
            let prior = s.reply().to_vec();
            let rev = s.session.render_revision;
            let work = s.session.work();
            // Refuse one byte below preflight, before cloning any candidate.
            s.max_bytes = DEFAULT_MAX_BYTES;
            let preflight = s.admit(&req, external).unwrap();
            s.max_bytes = preflight - 1;
            assert_eq!(
                s.execute(&req, external, None),
                Err(InteractionStatus::Budget)
            );
            assert_eq!(s.reply(), prior);
            assert_eq!(s.session.render_revision, rev);
            assert_eq!(s.session.work(), work);
            s.max_bytes = 16 << 20;
            let accepted = s.execute(&req, external, None).unwrap().to_vec();
            assert_eq!(s.execute(&req, usize::MAX, None).unwrap(), accepted);
        }
    }
    #[test]
    fn complex_documents_and_large_mutations_keep_general_reservation() {
        for doc in [
            document(1000, |b| b.texts("node.label", 0, &vec!["\n\\λ"; 1000])),
            document(1000, |b| b.u8s("node.status", 0, &vec![1; 1000])),
            document(1000, |b| b.u32s("node.parent", 0, &vec![0; 1000])),
            document(1000, |b| b.bytes("unknown", 0, &[0; 16])),
        ] {
            assert!(super::super::wire_memory::Plain::recognize(&doc).is_none());
            assert!(matches!(
                WireSession::open(&request(1, 0, OPEN, Some(&doc)), 16 << 20, 0),
                Err(InteractionStatus::Budget)
            ));
        }
        let doc = document(1000, |_| {});
        let mut s = WireSession::open(&request(1, 0, OPEN, Some(&doc)), 16 << 20, 0).unwrap();
        let prior = s.reply().to_vec();
        for op in [2, 3, 9, 10, 11, 12, 13, 14, 16, 18, UPDATE] {
            // Invalid payloads can reject even before budget; never mutate.
            assert!(s.execute(&request(2, 0, op, None), 0, None).is_err());
            assert_eq!(s.reply(), prior);
        }
    }
    #[test]
    fn authored_collapse_masks_keep_general_failure_atomic_admission() {
        let doc = document(1000, |_| {});
        let base = request(1, 0, OPEN, Some(&doc));
        let mut b = Builder::new(REQUEST_MAGIC);
        b.extend_from(&Container::decode(&base, REQUEST_MAGIC).unwrap());
        b.u8s("load.collapsed.u8", 0, &vec![1; 1000]);
        let open = b.finish();
        let mut s = WireSession::open(&open, 16 << 20, 0).unwrap();
        let prior = s.reply().to_vec();
        assert_eq!(
            s.execute(&request(2, 0, RENDER, None), 0, None),
            Err(InteractionStatus::Budget)
        );
        assert_eq!(s.reply(), prior);
        assert_eq!(s.session.render_revision(), 0);
        assert!(s.opening_matches(&open));
    }
    #[test]
    fn default_thousand_converging_point_input_uses_actual_index_capacity() {
        let doc = document(1000, |_| {});
        let mut s = WireSession::open(&request(1, 0, OPEN, Some(&doc)), 16 << 20, 69992).unwrap();
        s.execute(&request(2, 0, RENDER, None), 69992, None)
            .unwrap();
        for seq in 3..12 {
            let r = request(seq, s.session.render_revision(), 15, None);
            s.execute(&r, 69992, None).unwrap();
        }
        let center = s.session.published().unwrap().paint.nodes[0].center;
        let base = request(12, s.session.render_revision(), 1, None);
        let mut b = Builder::new(REQUEST_MAGIC);
        b.extend_from(&Container::decode(&base, REQUEST_MAGIC).unwrap());
        b.f64s("coordinates.f64", 0, &center);
        let pick = b.finish();
        let reply = s.execute(&pick, 69992, None).unwrap().to_vec();
        assert_eq!(s.execute(&pick, usize::MAX, None).unwrap(), reply);
        assert!(s.session.published().unwrap().node_count() > 0);
    }
    #[test]
    fn cooperative_step_admission_has_exact_checked_boundaries() {
        use super::super::layout::continuation_work_limit as limit;
        for (n, m, expected) in [
            (0, 0, 64),
            (1000, 1000, 64),
            (100000, 100000, 20),
            (1000000, 1000000, 2),
            (2000000, 2000000, 1),
            (4000001, 0, 0),
            (u64::MAX, 1, 0),
        ] {
            assert_eq!(limit(n, m), expected);
            if n.checked_add(m).is_some_and(|w| w < 4_000_000) && expected < 64 {
                assert!((expected as u64 + 1) * (n + m) > 4_000_000);
            }
        }
        let doc = document(64, |_| {});
        let open = request(1, 0, OPEN, Some(&doc));
        let mut s = WireSession::open(&open, 16 << 20, 0).unwrap();
        let r = request(2, 0, RENDER, None);
        let reply = s.execute(&r, 0, None).unwrap().to_vec();
        let c = Container::decode(&reply, RESULT_MAGIC).unwrap();
        assert_eq!(
            c.get("relayout.admission.u32", 0)
                .unwrap()
                .as_u32("fact")
                .unwrap(),
            [1, 64]
        );
        let stale = request(3, s.session.render_revision + 1, 4, None);
        assert_eq!(s.execute(&stale, 0, None), Err(InteractionStatus::Stale));
        assert_eq!(s.reply(), reply);
        assert_eq!(s.execute(&r, usize::MAX, None).unwrap(), reply);
    }
    #[test]
    fn replay_certifies_every_byte_and_retains_initial_columns_after_copy_on_write() {
        let doc = document(64, |_| {});
        let base = request(1, 0, OPEN, Some(&doc));
        let mut b = Builder::new(REQUEST_MAGIC);
        b.extend_from(&Container::decode(&base, REQUEST_MAGIC).unwrap());
        b.f64s(
            "load.x.f64",
            0,
            &(0..64).map(|i| i as f64 * 20.).collect::<Vec<_>>(),
        );
        b.f64s("load.y.f64", 0, &vec![-0.0; 64]);
        let open = b.finish();
        let mut s = WireSession::open(&open, DEFAULT_MAX_BYTES, 0).unwrap();
        for i in 0..open.len() {
            let mut changed = open.clone();
            changed[i] ^= 1;
            assert!(!s.opening_matches(&changed), "byte {i}");
        }
        assert!(s.opening_matches(&open));
        s.execute(&request(2, 0, RENDER, None), 0, None).unwrap();
        s.execute(&request(3, s.session.render_revision, 15, None), 0, None)
            .unwrap();
        assert!(s.opening_matches(&open));
        assert_eq!(
            s.ownership_bytes().unwrap().into_iter().sum::<usize>(),
            s.retained_budget()
        );
        // Wrong-sized typed loads use the safe general refusal before decoding.
        let mut b = Builder::new(REQUEST_MAGIC);
        b.extend_from(&Container::decode(&base, REQUEST_MAGIC).unwrap());
        b.f64s("load.x.f64", 0, &vec![0.; 32768]);
        b.f64s("load.y.f64", 0, &[0.; 64]);
        assert!(matches!(
            WireSession::open(&b.finish(), 16 << 20, 0),
            Err(InteractionStatus::Budget)
        ));
        let overflow = super::super::wire_memory::Plain {
            n: usize::MAX,
            m: 1,
            document: 0,
        };
        assert!(overflow.kernel_peak(&s.session).is_none());
    }
    #[test]
    fn late_phase_refusal_is_atomic_at_one_byte_boundary() {
        let doc = document(6, |_| {});
        let base = request(1, 0, OPEN, Some(&doc));
        let mut b = Builder::new(REQUEST_MAGIC);
        b.extend_from(&Container::decode(&base, REQUEST_MAGIC).unwrap());
        b.f64s("load.x.f64", 0, &[-200., -120., -40., 40., 120., 200.]);
        b.f64s("load.y.f64", 0, &[0.; 6]);
        let open = b.finish();
        let r = request(2, 0, RENDER, None);
        let attempt = |cap| {
            let mut s = WireSession::open(&open, 16 << 20, 0).unwrap();
            s.max_bytes = cap;
            let before = s.reply().to_vec();
            let value = s.execute(&r, 0, None).map(|r| r.to_vec());
            if value.is_err() {
                assert_eq!(s.reply(), before);
                assert_eq!(s.session.render_revision, 0);
                assert_eq!(s.session.work(), 0);
            }
            value
        };
        let (mut low, mut high) = (0, 16 << 20);
        while high - low > 1 {
            let mid = (low + high) / 2;
            if attempt(mid).is_ok() {
                high = mid;
            } else {
                low = mid;
            }
        }
        assert_eq!(attempt(high - 1), Err(InteractionStatus::Budget));
        assert!(attempt(high).is_ok());
        println!("closed-schema publication exact phase boundary={high}");
    }
    #[test]
    fn plain_update_keeps_both_whole_document_envelopes() {
        let old = document(1000, |_| {});
        let new = document(3, |_| {});
        let mut s =
            WireSession::open(&request(1, 0, OPEN, Some(&old)), DEFAULT_MAX_BYTES, 0).unwrap();
        let before = s
            .execute(&request(2, 0, RENDER, None), 0, None)
            .unwrap()
            .to_vec();
        let r = request(3, s.session.render_revision, UPDATE, Some(&new));
        let general = |d: usize, n: usize, m: usize| {
            98_304
                + 16_384
                + 2048 * n
                + 8192 * m
                + 48 * d
                + 8192 * (n + m)
                + 16 * ((2 * n + 11 * m) * 4096).min(1_048_576)
                + 1024 * (4 * (n + m).min(10_000) + n + 1)
                + 256 * (n + m).min(10_000)
                + 8192
        };
        let replacement = general(new.len(), 3, 3);
        let old_envelope = general(old.len(), 1000, 1000)
            + 1024
            + 3 * (s.last_request.len()
                + s.opening.len()
                + s.open_reply.len()
                + s.last_reply.len());
        let limit =
            old_envelope + replacement + 128 * (r.len() - new.len()) + 6 * new.len() + 4096 + 1024;
        for omitted in [1, replacement, 48 * old.len()] {
            s.max_bytes = limit - omitted;
            assert_eq!(s.execute(&r, 4096, None), Err(InteractionStatus::Budget));
            assert_eq!(s.reply(), before);
            assert_eq!(s.session.source.identity.node_count(), 1000);
        }
        s.max_bytes = limit;
        let after = s.execute(&r, 4096, None).unwrap().to_vec();
        assert_eq!(s.session.source.identity.node_count(), 3);
        assert_eq!(s.execute(&r, usize::MAX, None).unwrap(), after);
    }
}
