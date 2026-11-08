//! Narrow, source-certified plain graph accounting; all other documents retain
//! the general envelope. No camera/fixture/host-dependent eligibility.
use super::wire::{Container, Dtype, Request};
use super::*;
use crate::graph_interaction_state::HighlightPlane;

#[inline(never)]
fn total(base: usize, parts: &[(usize, usize)]) -> Option<usize> {
    parts.iter().try_fold(base, |sum, &(count, width)| {
        sum.checked_add(count.checked_mul(width)?)
    })
}

#[derive(Clone, Copy, Debug)]
pub(super) struct Plain {
    pub(super) n: usize,
    pub(super) m: usize,
    pub(super) document: usize,
}
impl Plain {
    pub fn recognize(bytes: &[u8]) -> Option<Self> {
        let c = Container::decode(bytes, crate::graphforge::container::DOCUMENT_MAGIC).ok()?;
        for (name, index, _) in &c.sections {
            if *index != 0
                || !matches!(
                    *name,
                    "status"
                        | "kind"
                        | "composition.version"
                        | "node.uuid"
                        | "edge.uuid"
                        | "edge.derived"
                        | "edge.layer"
                        | "edge.order"
                        | "edge.path"
                        | "edge.source"
                        | "edge.target"
                        | "graph.directed"
                )
            {
                return None;
            }
        }
        if c.get("status", 0)?.dtype != Dtype::U32
            || c.get("status", 0)?.payload != [0, 0, 0, 0]
            || c.get("kind", 0)?.dtype != Dtype::Utf8
            || c.get("kind", 0)?.payload != b"graph"
            || c.get("composition.version", 0)?.dtype != Dtype::U32
            || c.get("composition.version", 0)?.payload != [2, 0, 0, 0]
        {
            return None;
        }
        let n = c.get("node.uuid", 0)?.count;
        let m = c.get("edge.uuid", 0)?.count;
        for (name, dtype, fill) in [
            ("edge.derived", Dtype::U8, 0),
            ("edge.layer", Dtype::U32, 255),
            ("edge.order", Dtype::I64, 255),
            ("edge.path", Dtype::U64, 255),
        ] {
            let s = c.get(name, 0)?;
            if s.dtype != dtype || s.count != m || s.payload.iter().any(|&b| b != fill) {
                return None;
            }
        }
        if c.get("node.uuid", 0)?.dtype != Dtype::Uuid
            || c.get("edge.uuid", 0)?.dtype != Dtype::Uuid
        {
            return None;
        }
        if c.get("graph.directed", 0)
            .is_some_and(|s| s.dtype != Dtype::U8 || s.payload != [0])
            || c.get("edge.derived", 0)?.payload.iter().any(|&v| v != 0)
        {
            return None;
        }
        let a = c.get("edge.source", 0)?;
        let b = c.get("edge.target", 0)?;
        if a.dtype != Dtype::U64
            || b.dtype != Dtype::U64
            || a.count != m
            || b.count != m
            || a.payload
                .chunks_exact(8)
                .zip(b.payload.chunks_exact(8))
                .any(|(a, b)| a == b)
        {
            return None;
        }
        Some(Self {
            n,
            m,
            document: bytes.len(),
        })
    }
    pub fn general_charge(self, watermarks: usize) -> Option<usize> {
        super::wire::WireSession::charge(self.document, self.n, self.m, watermarks, 0)?.checked_add(
            self.n
                .checked_add(self.m)?
                .min(MAX_GRAPH_SELECTION_REFS)
                .checked_mul(256)?
                .checked_add(8192)?,
        )
    }
    pub fn open_peak(self, request: &Request<'_>, length: usize) -> Option<usize> {
        // The preceding borrowed source certificate proves primitive widths.
        // Reuse the already validated ingress descriptors before owned decode.
        let input = &request.container;
        for (name, _, s) in &input.sections {
            let count = match *name {
                "load.x.f64" | "load.y.f64" | "load.pinned.u8" | "load.collapsed.u8" => self.n,
                "document.bytes" => self.document,
                _ => {
                    if s.payload.len() > 128 {
                        return None;
                    }
                    continue;
                }
            };
            if s.count != count {
                return None;
            }
        }
        let positions = ["load.x.f64", "load.y.f64"]
            .iter()
            .try_fold(0usize, |sum, name| {
                sum.checked_add(input.get(name, 0).map_or(0, |s| s.payload.len()))
            })?;
        let pins = input
            .get("load.pinned.u8", 0)
            .map_or(0, |s| s.payload.iter().filter(|&&v| v == 1).count());
        let slots = crate::index_slots::IndexSlots::capacity_bytes(self.n)?
            .checked_add(crate::index_slots::IndexSlots::capacity_bytes(self.m)?)?;
        let identity = total(slots, &[(self.n, 16), (self.m, 16)])?;
        // Identity decode owns the four temporary persisted-edge sentinel
        // planes. Later those die before endpoints/hierarchy/cache ownership.
        let decode = total(identity, &[(self.m, 21), (positions, 1), (self.n, 2)])?;
        let cache = total(
            identity,
            &[(self.n, 10), (self.m, 20), (positions, 1), (length, 1)],
        )?;
        // 4096 covers the default reducer reserve, two OPEN acknowledgements
        // and retry-record metadata in addition to the ordinary fixed owner.
        total(102_400, &[(decode.max(cache), 1), (pins, 1024)])
    }
    #[cfg_attr(target_arch = "wasm32", inline(never))]
    pub fn retained(self, s: &GraphSession) -> Option<usize> {
        let mut bytes = total(
            98_304,
            &[
                (s.source.identity.plain_retained_bytes()?, 1),
                (s.source.parent.capacity(), 8),
                (s.source.edge_source.capacity(), 8),
                (s.source.edge_target.capacity(), 8),
                (s.source.edge_ordinal.capacity(), 4),
                (s.source.parent_valid.capacity(), 1),
                (s.collapsed.capacity(), 1),
                (s.source.labels.capacity(), std::mem::size_of::<String>()),
                (s.source.node_style.retained_bytes()?, 1),
                (s.source.edge_style.retained_bytes()?, 1),
                (s.hover.nodes.capacity(), std::mem::size_of::<usize>()),
                (s.hover.edges.capacity(), std::mem::size_of::<usize>()),
                (s.coordination.gate.len(), 128),
            ],
        )?;
        for label in s.source.labels.iter() {
            bytes = bytes.checked_add(label.capacity())?;
        }
        if let Some((x, y)) = &s.positions {
            bytes = bytes.checked_add(x.capacity().checked_add(y.capacity())?.checked_mul(8)?)?;
        }
        if let Some(force) = &s.relayout {
            bytes = bytes.checked_add(force.retained_bytes(&s.source.parent)?)?;
        }
        if let Some(p) = &s.published {
            bytes = bytes.checked_add(publication_bytes(p)?)?;
        }
        if let Some((_, o)) = &s.last_op {
            bytes = bytes
                .checked_add(
                    o.changed
                        .capacity()
                        .checked_mul(std::mem::size_of::<ElementRef>())?,
                )?
                .checked_add(
                    o.positions
                        .capacity()
                        .checked_mul(std::mem::size_of::<NodePosition>())?,
                )?;
        }
        Some(bytes)
    }
    #[cfg_attr(target_arch = "wasm32", inline(never))]
    pub fn clone_peak(self, s: &GraphSession, r: &Request<'_>) -> Option<usize> {
        let state = match &s.slot {
            StateSlot::Owned(v) => super::wire::WireSession::uuid_state_charge(v)?,
            _ => return None,
        };
        let prior = s.last_op.as_ref().map_or(Some(0), |(_, o)| {
            o.changed
                .capacity()
                .checked_mul(std::mem::size_of::<ElementRef>())?
                .checked_add(
                    o.positions
                        .capacity()
                        .checked_mul(std::mem::size_of::<NodePosition>())?,
                )
        })?;
        let mut bytes = state
            .checked_mul(4)?
            .checked_add(prior)?
            .checked_add(
                s.pending_outbound()
                    .map_or(0, |e| e.refs.capacity())
                    .checked_mul(std::mem::size_of::<ElementRef>())?,
            )?
            .checked_add(s.coordination.gate.len().checked_mul(128)?)?
            .checked_add(if matches!(r.operation, 1 | 7) {
                self.n
                    .max(self.m)
                    .min(MAX_GRAPH_SELECTION_REFS)
                    .checked_mul(3 * 288 + 2 * std::mem::size_of::<ElementRef>())?
            } else {
                0
            })?
            .checked_add(s.collapsed.capacity())?
            .checked_add(
                s.hover
                    .nodes
                    .capacity()
                    .checked_add(s.hover.edges.capacity())?
                    .checked_mul(std::mem::size_of::<usize>())?,
            )?;
        if s.positions.is_none() {
            // First progressive publication retains source positions, mutable
            // force planes, active/pin maps and nonuniform components.
            bytes = bytes
                .checked_add(self.n.checked_mul(66)?)?
                .checked_add(self.m.checked_mul(16)?)?;
        } else if r.operation == 15 {
            bytes = bytes.checked_add(self.n.checked_mul(16)?)?;
            bytes = bytes.checked_add(if let Some(force) = &s.relayout {
                force.private_clone_bytes()?
            } else {
                self.n
                    .checked_mul(50)?
                    .checked_add(self.m.checked_mul(16)?)?
            })?;
        }
        if r.operation == 0 {
            bytes = bytes.checked_add(self.n.checked_mul(8)?)?;
        }
        Some(bytes)
    }
    #[cfg_attr(target_arch = "wasm32", inline(never))]
    pub fn force_peak(self, s: &GraphSession, r: &Request<'_>) -> Option<usize> {
        if s.positions.is_some() && r.operation != 15 {
            return Some(0);
        }
        if s.relayout.is_none() {
            // Source/force integration and original per-node adjacency/BFS.
            // Includes Vec headers, bounded growable neighbor/queue capacities,
            // joined parent-edge staging, and stable overlap rank scratch.
            // CoSE has no degree plane; installed root parents share.
            let word = std::mem::size_of::<usize>();
            total(
                0,
                &[
                    (self.n, 60 + 9 * word + std::mem::size_of::<Vec<usize>>()),
                    (self.m, 33 + 6 * word),
                ],
            )
        } else {
            // Private copy + one active/pin comparison + fx/fy, cell_of and
            // ordered rows; mass/sums/CSR cursors use <=512² cells.
            let word = std::mem::size_of::<usize>();
            total(
                self.clone_peak(s, r)?,
                &[
                    (self.n, 18 + 3 * word),
                    (self.m, 1),
                    (512 * 512, 24 + 2 * word),
                ],
            )
        }
    }
    #[cfg_attr(target_arch = "wasm32", inline(never))]
    pub fn kernel_peak(self, s: &GraphSession) -> Option<usize> {
        let rn = s.budgets.0.min(self.n as u64) as usize;
        let re = s.budgets.1.min(self.m as u64) as usize;
        // Caller output capacities + source flags/masks/collapse flags. Kernel
        // compaction arrays die before edge hash/list/membership construction.
        let outputs = total(0, &[(self.n, 21), (self.m, 13), (rn, 16), (re, 24)])?;
        let cluster = total(0, &[(self.n, 33), (rn, 48)])?;
        // Index-only buckets, source-bounded pair storage and slot indices.
        // The table is dropped before the CSR phase; compaction is disjoint.
        let hash = crate::index_slots::IndexSlots::capacity_bytes(self.m)?;
        let pairs = self.m.checked_mul(16)?;
        let edges = hash
            .checked_add(pairs)?
            .checked_add(self.m.checked_mul(8)?)?;
        outputs
            .checked_add(cluster.max(edges))?
            .checked_add(131_072)
    }
    pub fn retains(self, s: &GraphSession) -> bool {
        let StateSlot::Owned(state) = &s.slot else {
            return false;
        };
        s.pending_outbound()
            .is_none_or(|e| e.refs.iter().all(|r| !matches!(r, ElementRef::Derived(_))))
            && state.selection().derived.is_empty()
            && [
                HighlightPlane::Path,
                HighlightPlane::Community,
                HighlightPlane::External,
            ]
            .iter()
            .all(|p| state.highlight_set(*p).derived.is_empty())
            && !matches!(
                state.focus(),
                Some(crate::graph_interaction_state::Focus::Derived(_))
            )
            && s.last_op.as_ref().is_none_or(|(_, o)| {
                o.changed
                    .iter()
                    .all(|r| !matches!(r, ElementRef::Derived(_)))
            })
    }
    pub fn applies(self, s: &GraphSession, r: &Request<'_>) -> bool {
        self.retains(s)
            && s.collapsed.iter().all(|&v| v == 0)
            && matches!(r.operation, 0 | 1 | 4 | 5 | 6 | 7 | 8 | 15 | 17 | 21 | 22)
    }
}

pub(super) fn publication_bytes(p: &RenderOutput) -> Option<usize> {
    total(
        p.pick.retained_bytes(),
        &[
            (p.source_node_flags.capacity(), 4),
            (p.source_edge_flags.capacity(), 4),
            (p.node_x.capacity(), 8),
            (p.node_y.capacity(), 8),
            (p.member_of.capacity(), 8),
            (p.edge_source.capacity(), 8),
            (p.edge_target.capacity(), 8),
            (p.edge_member_offsets.capacity(), 8),
            (p.edge_members.capacity(), 8),
            (p.visual_states.capacity(), 1),
            (p.emphasis.capacity(), 1),
            (p.edge_visual_states.capacity(), 1),
            (p.edge_emphasis.capacity(), 1),
            (p.node_member_offsets.capacity(), 8),
            (p.node_members.capacity(), 8),
            (p.focus_node.capacity(), 8),
            (p.edge_render.capacity(), 8),
            (p.paint.nodes.capacity(), std::mem::size_of::<NodePaint>()),
            (
                p.paint.edge_styles.capacity(),
                std::mem::size_of::<crate::graph_style::ResolvedGraphStyle>(),
            ),
            (
                p.paint.edge_layers.capacity(),
                std::mem::size_of::<crate::graph_style::SemanticPaintLayers>(),
            ),
            (p.paint.pieces.capacity(), std::mem::size_of::<EdgePiece>()),
            (p.paint.frames.capacity(), std::mem::size_of::<FramePaint>()),
        ],
    )
}

pub(super) fn paint_peak(p: &RenderOutput, n: usize, m: usize) -> Option<usize> {
    let rn = p.node_count();
    let re = p.edge_count();
    let styles = if p.tier == crate::graph::LodTier::Aggregate {
        0
    } else {
        n.checked_add(m)?.checked_mul(28)?
    };
    let nodes = rn.checked_mul(2 * std::mem::size_of::<NodePaint>())?;
    let edges = re.checked_mul(2 * (28 + 32))?;
    let pieces = re.checked_mul(6 * std::mem::size_of::<EdgePiece>())?;
    let groups = crate::index_slots::IndexSlots::capacity_bytes(re)?
        .checked_add(re.checked_mul(3 * std::mem::size_of::<usize>())?)?;
    let route = total(
        0,
        &[
            (styles, 1),
            (rn, 9),
            (re, 3 * 12 * 8),
            (groups.max(pieces), 1),
        ],
    )?;
    let primitives = rn.checked_add(re.checked_mul(3)?)?;
    let grid = primitives
        .checked_mul(4096)?
        .min(MAX_GRAPH_PICK_GRID_ENTRIES)
        .checked_mul(4)?
        .checked_add(primitives.min(MAX_GRAPH_PICK_PRIMITIVES).checked_mul(32)?)?
        .checked_add(131_072)?;
    // Route/group scratch dies before pick CSR construction. Growable paint
    // owners persist; the piece capacity overlaps routing only after grouping.
    total(
        publication_bytes(p)?,
        &[
            (n, 9),
            (m, 5),
            (rn.checked_add(re)?, 4),
            (nodes, 1),
            (edges, 1),
            (route.max(pieces.checked_add(grid)?), 1),
        ],
    )
}
pub(super) fn serialized_bound(p: &RenderOutput, refs: usize) -> Option<usize> {
    let heads = p.paint.pieces.iter().filter(|p| p.head.is_some()).count();
    let bytes = total(
        131_072,
        &[
            (p.node_count(), 174),
            (p.edge_count(), 150),
            (p.paint.pieces.len(), 165),
            (heads, 28),
            (p.paint.frames.len(), 72),
            (p.member_of.len(), 20),
            (p.source_edge_flags.len(), 4),
            (p.edge_members.len(), 8),
            (refs, 256),
        ],
    )?;
    Some(bytes)
}
