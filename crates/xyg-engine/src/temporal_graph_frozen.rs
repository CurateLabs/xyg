//! Immutable temporal graph acquisition and canonical XYFG v1 codec (§27/29).
//! This is provenance/publication storage, not rendered-export acceptance.
use crate::graphforge::container::{Builder, Container, Dtype};
use crate::graphforge::interaction::Camera;
use crate::temporal::{CancelFlag, TemporalError};
use crate::temporal_graph::{GraphEntity, TemporalGraph, TemporalGraphFrame};
use crate::transition::Blake2s8;
use std::collections::HashSet;

type Result<T> = std::result::Result<T, TemporalError>;
pub const MAX_BYTES: usize = 24 * 1024 * 1024;
pub const MAX_PEAK: usize = 384 * 1024 * 1024;
const MAGIC: &[u8; 4] = b"XYFG";

/// Owned encoded snapshot. Imported snapshots are offline data, never live handles.
#[derive(Debug)]
pub struct FrozenTemporalGraph {
    bytes: Vec<u8>,
}

/// Borrowed, issuer-validated retained publication; only WireSession can issue it.
pub struct Publication<'a> {
    pub(crate) document: &'a [u8],
    pub(crate) reply: &'a [u8],
    pub(crate) instance: u64,
    pub(crate) revision: u32,
    pub(crate) camera: [f64; 7],
    pub(crate) graph_token: u64,
    pub(crate) temporal_revision: u64,
    pub(crate) resident_bytes: usize,
}
// Validate the source/render correspondence before an offline publication is
// retained. Paint/GPU decoders validate their own planes, not these CPU maps.
fn validate_publication(
    reply: &Container<'_>,
    node_visibility: &[u8],
    edge_visibility: &[u8],
    source: &[u64],
    target: &[u64],
    camera: &Camera,
) -> Result<()> {
    let invalid = || TemporalError::InvalidArgument;
    let read = |name| {
        reply
            .get(name, 0)
            .ok_or_else(invalid)?
            .as_u64(name)
            .map_err(|_| invalid())
    };
    let positions = |name| {
        reply
            .get(name, 0)
            .ok_or_else(invalid)?
            .as_f64(name)
            .map_err(|_| invalid())
    };
    let x = positions("render.node_x.f64")?;
    let y = positions("render.node_y.f64")?;
    let centers = positions("paint.node.center.f64")?;
    let node_count = x.len();
    let edge_source = read("render.edge_source.u64")?;
    let edge_target = read("render.edge_target.u64")?;
    let edge_count = edge_source.len();
    let member_of = read("render.member_of.u64")?;
    let node_offsets = read("render.node_member_offsets.u64")?;
    let node_members = read("render.node_members.u64")?;
    let edge_offsets = read("render.edge_member_offsets.u64")?;
    let edge_members = read("render.edge_members.u64")?;
    let valid_offsets = |offsets: &[u64], rows: usize, members: usize| {
        rows.checked_add(1) == Some(offsets.len())
            && offsets.first() == Some(&0)
            && offsets.last() == Some(&(members as u64))
            && offsets.windows(2).all(|pair| pair[0] < pair[1])
    };
    if y.len() != node_count
        || node_count.checked_mul(2) != Some(centers.len())
        || x.iter()
            .zip(&y)
            .zip(centers.chunks_exact(2))
            .any(|((&x, &y), center)| {
                camera
                    .project(x, y)
                    .iter()
                    .zip(center)
                    .any(|(a, b)| a.to_bits() != b.to_bits())
            })
        || x.iter().chain(&y).any(|v| !v.is_finite())
        || edge_target.len() != edge_count
        || edge_source
            .iter()
            .chain(&edge_target)
            .any(|&i| i >= node_count as u64)
        || member_of.len() != node_visibility.len()
        || member_of
            .iter()
            .zip(node_visibility)
            .any(|(&r, &visible)| r != u64::MAX && (r >= node_count as u64 || visible == 0))
        || !valid_offsets(&node_offsets, node_count, node_members.len())
        || !valid_offsets(&edge_offsets, edge_count, edge_members.len())
        || member_of.iter().filter(|&&r| r != u64::MAX).count() != node_members.len()
    {
        return Err(invalid());
    }
    for (render, pair) in node_offsets.windows(2).enumerate() {
        let members = &node_members[pair[0] as usize..pair[1] as usize];
        if members.windows(2).any(|p| p[0] >= p[1])
            || members
                .iter()
                .any(|&s| s >= member_of.len() as u64 || member_of[s as usize] != render as u64)
        {
            return Err(invalid());
        }
    }
    // Node maps are bijective via their inverse and sorted slices. Edges have
    // no serialized inverse, so track each source edge once across CSR rows.
    let mut seen_edges = vec![false; edge_visibility.len()];
    for (render, pair) in edge_offsets.windows(2).enumerate() {
        let members = &edge_members[pair[0] as usize..pair[1] as usize];
        if members.windows(2).any(|p| p[0] >= p[1]) {
            return Err(invalid());
        }
        for &s in members {
            let s = usize::try_from(s).map_err(|_| invalid())?;
            if s >= edge_visibility.len()
                || edge_visibility[s] == 0
                || seen_edges[s]
                || member_of[source[s] as usize] != edge_source[render]
                || member_of[target[s] as usize] != edge_target[render]
            {
                return Err(invalid());
            }
            seen_edges[s] = true;
        }
    }
    for (name, count) in [
        ("render.visual_states.u8", node_count),
        ("render.emphasis.u8", node_count),
        ("render.edge_visual_states.u8", edge_count),
        ("render.edge_emphasis.u8", edge_count),
    ] {
        let section = reply.get(name, 0).ok_or_else(invalid)?;
        if section.dtype != Dtype::U8 || section.payload.len() != count {
            return Err(invalid());
        }
    }
    if read("render.edges_kept.u64")? != [edge_count as u64] {
        return Err(invalid());
    }
    Ok(())
}

impl FrozenTemporalGraph {
    pub fn bytes(&self) -> &[u8] {
        &self.bytes
    }
    /// Conservative envelope covers typed decode, builder/final copies and hashes.
    pub fn required_peak(encoded: usize) -> Result<usize> {
        if encoded > MAX_BYTES {
            return Err(TemporalError::CapacityExceeded);
        }
        encoded
            .checked_mul(16)
            .and_then(|n| n.checked_add(65536))
            .filter(|&n| n <= MAX_PEAK)
            .ok_or(TemporalError::CapacityExceeded)
    }
    fn admit(encoded: usize, budget: usize) -> Result<()> {
        if budget > MAX_PEAK || Self::required_peak(encoded)? > budget {
            return Err(TemporalError::BudgetExceeded);
        }
        Ok(())
    }
    pub fn acquisition_bound(
        graph: &TemporalGraph,
        publication: Option<&Publication<'_>>,
    ) -> Result<usize> {
        let n = graph.node_ids().len();
        let m = graph.edge_ids().len();
        let bound = n
            .checked_mul(128)
            .and_then(|v| v.checked_add(m.checked_mul(128)?))
            .and_then(|v| {
                v.checked_add(publication.map_or(0, |p| p.document.len() + p.reply.len()))
            })
            .and_then(|v| v.checked_add(8192))
            .ok_or(TemporalError::CapacityExceeded)?;
        Ok(bound)
    }
    pub fn acquisition_peak(
        graph: &TemporalGraph,
        publication: Option<&Publication<'_>>,
    ) -> Result<usize> {
        Self::required_peak(Self::acquisition_bound(graph, publication)?)?
            .checked_add(publication.map_or(0, |p| p.resident_bytes))
            .filter(|&n| n <= MAX_PEAK)
            .ok_or(TemporalError::BudgetExceeded)
    }
    pub fn acquire(
        graph: &TemporalGraph,
        frame: &TemporalGraphFrame,
        window: Option<(i64, i64)>,
        timezone: &str,
        publication: Option<Publication<'_>>,
        cancel: &CancelFlag,
        budget: usize,
    ) -> Result<Self> {
        if cancel.is_cancelled() {
            return Err(TemporalError::Cancelled);
        }
        if publication.as_ref().is_some_and(|p| {
            p.graph_token != graph.instance_token() || p.temporal_revision != frame.revision()
        }) {
            return Err(TemporalError::InvalidArgument);
        }
        crate::temporal::validate_timezone(timezone)?;
        if timezone.chars().any(char::is_control) {
            return Err(TemporalError::TimezoneRequired);
        }
        if window
            .is_some_and(|(a, b)| a >= b || frame.cursor_micros() < a || frame.cursor_micros() >= b)
        {
            return Err(TemporalError::InvalidArgument);
        }
        // Admit before freeze clones state or allocates any typed/builder output.
        if budget > MAX_PEAK || Self::acquisition_peak(graph, publication.as_ref())? > budget {
            return Err(TemporalError::BudgetExceeded);
        }
        let state = graph.freeze(frame)?;
        let mut b = Builder::new(MAGIC);
        b.u32s("version", 0, &[1]);
        b.u64s("identity", 0, &[graph.instance_token(), state.revision]);
        b.i64s(
            "time",
            0,
            &[
                state.cursor_micros,
                state.range_start_micros,
                state.range_end_micros,
            ],
        );
        let (kind, start, end) = window.map_or((0, 0, 0), |(a, b)| (1, a, b));
        b.u32s("window.kind", 0, &[kind]);
        b.i64s("window", 0, &[start, end]);
        b.utf8("timezone", 0, timezone);
        b.uuids("node.uuid", 0, graph.node_ids());
        b.uuids("edge.uuid", 0, graph.edge_ids());
        let (source, target): (Vec<_>, Vec<_>) = graph.edge_endpoints().unzip();
        b.u64s("edge.source", 0, &source);
        b.u64s("edge.target", 0, &target);
        b.u8s("node.visibility", 0, frame.node_visibility());
        b.u8s("edge.visibility", 0, frame.edge_visibility());
        b.uuids("visible.node.uuid", 0, &state.visible_node_ids);
        b.uuids("visible.edge.uuid", 0, &state.visible_edge_ids);
        b.uuids("selected.node.uuid", 0, &state.selected_node_ids);
        b.uuids("selected.edge.uuid", 0, &state.selected_edge_ids);
        b.uuids("pinned.node.uuid", 0, &state.pinned_node_ids);
        let (kind, id) = match state.focused {
            None => (0, [0; 16]),
            Some(GraphEntity::Node(id)) => (1, id),
            Some(GraphEntity::Edge(id)) => (2, id),
        };
        b.u32s("focus.kind", 0, &[kind]);
        b.uuids("focus.uuid", 0, &[id]);
        let camera = publication.as_ref().map(|p| p.camera);
        let (document, reply, instance, revision) = publication
            .map_or((&[][..], &[][..], 0, 0), |p| {
                (p.document, p.reply, p.instance, p.revision)
            });
        b.u64s("render.identity", 0, &[instance, revision as u64]);
        b.f64s(
            "render.camera",
            0,
            camera.as_ref().map_or(&[][..], |v| &v[..]),
        );
        b.bytes("render.document", 0, document);
        b.bytes("render.publication", 0, reply);
        let body = b.finish();
        let mut hash = Blake2s8::new();
        hash.update(b"xyg-frozen-temporal-v1");
        hash.update(&body);
        let mut bytes = body;
        bytes.extend(hash.finish());
        Self::validate(&bytes, budget)?;
        cancel.publish_if_active(|| Self { bytes })
    }
    pub fn decode(bytes: &[u8], budget: usize) -> Result<Self> {
        Self::validate(bytes, budget)?;
        Ok(Self {
            bytes: bytes.to_vec(),
        })
    }
    pub fn validate(bytes: &[u8], budget: usize) -> Result<()> {
        Self::admit(bytes.len(), budget)?;
        if bytes.len() < 40 {
            return Err(TemporalError::InvalidArgument);
        }
        let (body, digest) = bytes.split_at(bytes.len() - 8);
        let mut hash = Blake2s8::new();
        hash.update(b"xyg-frozen-temporal-v1");
        hash.update(body);
        if hash.finish() != digest {
            return Err(TemporalError::InvalidArgument);
        }
        let invalid = || TemporalError::InvalidArgument;
        let c = Container::decode(body, MAGIC).map_err(|_| invalid())?;
        let get = |name, dtype| {
            c.get(name, 0)
                .filter(|s| s.dtype == dtype)
                .ok_or_else(invalid)
        };
        let u64s = |name| get(name, Dtype::U64)?.as_u64(name).map_err(|_| invalid());
        let u32s = |name| get(name, Dtype::U32)?.as_u32(name).map_err(|_| invalid());
        let uuids = |name| {
            get(name, Dtype::Uuid)?
                .as_uuids(name)
                .map_err(|_| invalid())
        };
        let time = get("time", Dtype::I64)?
            .as_i64("time")
            .map_err(|_| invalid())?;
        let window = get("window", Dtype::I64)?
            .as_i64("window")
            .map_err(|_| invalid())?;
        let identity = u64s("identity")?;
        let render = u64s("render.identity")?;
        let kind = u32s("window.kind")?;
        let focus = u32s("focus.kind")?;
        let tz = get("timezone", Dtype::Utf8)?
            .as_utf8("timezone")
            .map_err(|_| invalid())?;
        crate::temporal::validate_timezone(tz)?;
        if tz.chars().any(char::is_control)
            || u32s("version")? != [1]
            || identity.len() != 2
            || identity.contains(&0)
            || time.len() != 3
            || time[1] >= time[2]
            || time[0] < time[1]
            || time[0] >= time[2]
            || window.len() != 2
            || kind.len() != 1
            || kind[0] > 1
            || (kind[0] == 0 && window != [0, 0])
            || (kind[0] == 1
                && (window[0] >= window[1] || time[0] < window[0] || time[0] >= window[1]))
            || render.len() != 2
            || focus.len() != 1
            || focus[0] > 2
        {
            return Err(invalid());
        }
        let nodes = uuids("node.uuid")?;
        let edges = uuids("edge.uuid")?;
        for ids in [&nodes, &edges] {
            let mut set = HashSet::new();
            if ids.iter().any(|id| *id == [0; 16] || !set.insert(*id)) {
                return Err(invalid());
            }
        }
        let nv = get("node.visibility", Dtype::U8)?.payload;
        let ev = get("edge.visibility", Dtype::U8)?.payload;
        let source = u64s("edge.source")?;
        let target = u64s("edge.target")?;
        if nv.len() != nodes.len()
            || ev.len() != edges.len()
            || nv.iter().chain(ev).any(|&v| v > 1)
            || source.len() != edges.len()
            || target.len() != edges.len()
        {
            return Err(invalid());
        }
        for (i, (&s, &t)) in source.iter().zip(&target).enumerate() {
            if s >= nodes.len() as u64
                || t >= nodes.len() as u64
                || (ev[i] == 1 && (nv[s as usize] != 1 || nv[t as usize] != 1))
            {
                return Err(invalid());
            }
        }
        for (name, ids, vis) in [
            ("visible.node.uuid", &nodes, nv),
            ("visible.edge.uuid", &edges, ev),
        ] {
            let expected: Vec<_> = ids
                .iter()
                .zip(vis)
                .filter_map(|(&id, &v)| (v == 1).then_some(id))
                .collect();
            if uuids(name)? != expected {
                return Err(invalid());
            }
        }
        for (name, ids) in [
            ("selected.node.uuid", &nodes),
            ("selected.edge.uuid", &edges),
            ("pinned.node.uuid", &nodes),
        ] {
            let selected = uuids(name)?;
            let mut cursor = 0;
            for id in ids {
                if selected.get(cursor) == Some(id) {
                    cursor += 1;
                }
            }
            if cursor != selected.len() {
                return Err(invalid());
            }
        }
        if uuids("selected.node.uuid")?.len() + uuids("selected.edge.uuid")?.len() > 10_000 {
            return Err(TemporalError::SelectionTooLarge);
        }
        let focused = uuids("focus.uuid")?;
        if focused.len() != 1
            || match focus[0] {
                0 => focused[0] != [0; 16],
                1 => !nodes.contains(&focused[0]),
                _ => !edges.contains(&focused[0]),
            }
        {
            return Err(invalid());
        }
        let document = get("render.document", Dtype::Bytes)?.payload;
        let publication = get("render.publication", Dtype::Bytes)?.payload;
        let camera = get("render.camera", Dtype::F64)?
            .as_f64("render.camera")
            .map_err(|_| invalid())?;
        if render == [0, 0] {
            if !document.is_empty() || !publication.is_empty() || !camera.is_empty() {
                return Err(invalid());
            }
        } else {
            if camera.len() != 7
                || camera.iter().any(|v| !v.is_finite())
                || camera[0] == 0.0
                || camera[1] == 0.0
                || camera[4] <= 0.0
                || camera[5] <= 0.0
                || camera[6] <= 0.0
            {
                return Err(invalid());
            }
            if render.contains(&0) || render[1] > u32::MAX as u64 {
                return Err(invalid());
            }
            let doc = crate::graphforge::composed::ComposedDocument::decode(document)
                .map_err(|_| invalid())?;
            if doc.uuids("node.uuid").map_err(|_| invalid())? != nodes
                || doc.uuids("edge.uuid").map_err(|_| invalid())? != edges
                || doc.u64s("edge.source").map_err(|_| invalid())? != source
                || doc.u64s("edge.target").map_err(|_| invalid())? != target
            {
                return Err(invalid());
            }
            let reply = Container::decode(publication, b"XYGR").map_err(|_| invalid())?;
            let header = reply
                .get("header.u32", 0)
                .ok_or_else(invalid)?
                .as_u32("header.u32")
                .map_err(|_| invalid())?;
            if header.first().copied() != Some(render[1] as u32) {
                return Err(invalid());
            }
            let view = Camera {
                scale_x: camera[0],
                scale_y: camera[1],
                offset_x: camera[2],
                offset_y: camera[3],
                viewport_width: camera[4],
                viewport_height: camera[5],
                dpr: camera[6],
            };
            validate_publication(&reply, nv, ev, &source, &target, &view)?;
            crate::graphforge::interaction::wire::decode_paint(publication)
                .map_err(|_| invalid())?;
            crate::graphforge::interaction::wire::validate_gpu(publication)
                .map_err(|_| invalid())?;
        }
        // Canonical container: exact section order, types, payloads and padding.
        let names = [
            "version",
            "identity",
            "time",
            "window.kind",
            "window",
            "timezone",
            "node.uuid",
            "edge.uuid",
            "edge.source",
            "edge.target",
            "node.visibility",
            "edge.visibility",
            "visible.node.uuid",
            "visible.edge.uuid",
            "selected.node.uuid",
            "selected.edge.uuid",
            "pinned.node.uuid",
            "focus.kind",
            "focus.uuid",
            "render.identity",
            "render.camera",
            "render.document",
            "render.publication",
        ];
        if c.sections.len() != names.len()
            || c.sections
                .iter()
                .zip(names)
                .any(|((name, index, _), expected)| *name != expected || *index != 0)
        {
            return Err(invalid());
        }
        let mut b = Builder::new(MAGIC);
        for (name, index, s) in &c.sections {
            b.push(name, *index as usize, s.dtype, s.count, s.payload.to_vec());
        }
        if b.finish() != body {
            return Err(invalid());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::projection::GraphProjection;
    use crate::temporal_graph::TemporalBindingInput;
    fn graph() -> TemporalGraph {
        let p = GraphProjection::new(
            &[[1; 16], [2; 16]],
            &[[3; 16]],
            &[[1; 16]],
            &[[2; 16]],
            None,
            true,
        )
        .unwrap();
        TemporalGraph::bind(
            &p,
            TemporalBindingInput::default(),
            TemporalBindingInput::default(),
        )
        .unwrap()
    }
    #[test]
    fn retained_codec_rejects_rechecksummed_cpu_maps() {
        let bytes = include_bytes!(
            "../../../spec/performance/temporal-graph-freeze-2026-11-07/retained.xyfg"
        );
        assert!(FrozenTemporalGraph::decode(bytes, MAX_PEAK).is_ok());
        let body_len = bytes.len() - 8;
        let frozen = Container::decode(&bytes[..body_len], MAGIC).unwrap();
        let publication = frozen.get("render.publication", 0).unwrap();
        let reply = Container::decode(publication.payload, b"XYGR").unwrap();
        for (name, index, value) in [
            ("render.edge_target.u64", 0, 999999),
            ("render.edge_source.u64", 0, 1),
            ("render.member_of.u64", 0, 999999),
            ("render.node_member_offsets.u64", 0, 999999),
            ("render.node_member_offsets.u64", 1, 0),
            ("render.node_members.u64", 1, 0),
            ("render.edge_member_offsets.u64", 0, 1),
            ("render.edge_member_offsets.u64", 1, 0),
            ("render.edge_members.u64", 1, 0),
            ("render.node_y.f64", 0, f64::NAN.to_bits()),
            ("render.node_y.f64", 0, 1.0f64.to_bits()),
            ("render.node_x.f64", 0, 1.0f64.to_bits()),
            ("render.node_x.f64", 0, f64::INFINITY.to_bits()),
        ] {
            let section = reply.get(name, 0).unwrap();
            let at = section.payload.as_ptr() as usize - bytes.as_ptr() as usize + index * 8;
            let mut bad = bytes.to_vec();
            bad[at..at + 8].copy_from_slice(&value.to_le_bytes());
            let mut hash = Blake2s8::new();
            hash.update(b"xyg-frozen-temporal-v1");
            hash.update(&bad[..body_len]);
            bad[body_len..].copy_from_slice(&hash.finish());
            assert_eq!(
                FrozenTemporalGraph::decode(&bad, MAX_PEAK).unwrap_err(),
                TemporalError::InvalidArgument,
                "{name} #{index}"
            );
        }
    }

    #[test]
    fn publication_validation_accepts_aggregate_inverse_and_edge_members() {
        let mut b = Builder::new(b"XYGR");
        b.f64s("render.node_x.f64", 0, &[0., 1.]);
        b.f64s("render.node_y.f64", 0, &[0., 1.]);
        b.f64s("paint.node.center.f64", 0, &[0., 0., 1., 1.]);
        b.u64s("render.member_of.u64", 0, &[0, 0, 1]);
        b.u64s("render.node_member_offsets.u64", 0, &[0, 2, 3]);
        b.u64s("render.node_members.u64", 0, &[0, 1, 2]);
        b.u64s("render.edge_source.u64", 0, &[0, 1]);
        b.u64s("render.edge_target.u64", 0, &[1, 0]);
        b.u64s("render.edge_member_offsets.u64", 0, &[0, 2, 3]);
        b.u64s("render.edge_members.u64", 0, &[0, 1, 2]);
        b.u64s("render.edges_kept.u64", 0, &[2]);
        for name in [
            "render.visual_states.u8",
            "render.emphasis.u8",
            "render.edge_visual_states.u8",
            "render.edge_emphasis.u8",
        ] {
            b.u8s(name, 0, &[0, 0]);
        }
        let bytes = b.finish();
        let reply = Container::decode(&bytes, b"XYGR").unwrap();
        let camera = Camera {
            scale_x: 1.,
            scale_y: 1.,
            offset_x: 0.,
            offset_y: 0.,
            viewport_width: 1.,
            viewport_height: 1.,
            dpr: 2.,
        };
        assert!(validate_publication(
            &reply,
            &[1, 1, 1],
            &[1, 1, 1],
            &[0, 1, 2],
            &[2, 2, 0],
            &camera
        )
        .is_ok());
        assert_eq!(
            validate_publication(
                &reply,
                &[1, 1, 1],
                &[1, 1, 1],
                &[0, 1, 2],
                &[2, 1, 0],
                &camera
            ),
            Err(TemporalError::InvalidArgument)
        );
    }

    #[test]
    fn acquisition_is_immutable_and_cross_instance_stale_budget_cancel_are_atomic() {
        let mut g = graph();
        let other = graph();
        let cancel = CancelFlag::new();
        g.set_selection([[2; 16]], [[3; 16]]).unwrap();
        g.set_focus(Some(GraphEntity::Node([2; 16]))).unwrap();
        g.set_pinned_nodes([[2; 16]]).unwrap();
        let frame = g
            .frame(1, 5, 0, 10, &cancel, g.required_budget().unwrap())
            .unwrap();
        let snapshot =
            FrozenTemporalGraph::acquire(&g, &frame, Some((0, 10)), "UTC", None, &cancel, MAX_PEAK)
                .unwrap();
        assert_eq!(
            FrozenTemporalGraph::decode(snapshot.bytes(), MAX_PEAK)
                .unwrap()
                .bytes(),
            snapshot.bytes()
        );
        assert_eq!(
            FrozenTemporalGraph::acquire(&other, &frame, None, "UTC", None, &cancel, MAX_PEAK)
                .unwrap_err(),
            TemporalError::InvalidArgument
        );
        assert_eq!(
            FrozenTemporalGraph::acquire(&g, &frame, None, "UTC", None, &cancel, 1).unwrap_err(),
            TemporalError::BudgetExceeded
        );
        let cancelled = CancelFlag::new();
        cancelled.cancel();
        assert_eq!(
            FrozenTemporalGraph::acquire(&g, &frame, None, "UTC", None, &cancelled, MAX_PEAK)
                .unwrap_err(),
            TemporalError::Cancelled
        );
        let foreign = Publication {
            document: &[],
            reply: &[],
            instance: 1,
            revision: 1,
            camera: [1.0; 7],
            graph_token: other.instance_token(),
            temporal_revision: frame.revision(),
            resident_bytes: 0,
        };
        assert_eq!(
            FrozenTemporalGraph::acquire(&g, &frame, None, "UTC", Some(foreign), &cancel, MAX_PEAK)
                .unwrap_err(),
            TemporalError::InvalidArgument
        );
        let bytes = snapshot.bytes().to_vec();
        g.frame(2, 6, 0, 10, &cancel, g.required_budget().unwrap())
            .unwrap();
        assert_eq!(
            FrozenTemporalGraph::acquire(&g, &frame, None, "UTC", None, &cancel, MAX_PEAK)
                .unwrap_err(),
            TemporalError::StaleRevision
        );
        drop(g);
        assert_eq!(snapshot.bytes(), bytes);
    }
    #[test]
    fn codec_rejects_corruption_trailing_bytes_and_exact_under_budget() {
        let mut g = graph();
        let cancel = CancelFlag::new();
        let frame = g
            .frame(1, 5, 0, 10, &cancel, g.required_budget().unwrap())
            .unwrap();
        let snapshot =
            FrozenTemporalGraph::acquire(&g, &frame, None, "UTC", None, &cancel, MAX_PEAK).unwrap();
        let peak = FrozenTemporalGraph::required_peak(snapshot.bytes().len()).unwrap();
        assert_eq!(
            FrozenTemporalGraph::decode(snapshot.bytes(), peak - 1).unwrap_err(),
            TemporalError::BudgetExceeded
        );
        assert!(FrozenTemporalGraph::decode(snapshot.bytes(), peak).is_ok());
        for at in 0..snapshot.bytes().len() {
            let mut bad = snapshot.bytes().to_vec();
            bad[at] ^= 1;
            assert!(
                FrozenTemporalGraph::decode(&bad, MAX_PEAK).is_err(),
                "byte {at}"
            );
        }
        let mut bad = snapshot.bytes().to_vec();
        bad.push(0);
        assert!(FrozenTemporalGraph::decode(&bad, MAX_PEAK).is_err());
    }
}
