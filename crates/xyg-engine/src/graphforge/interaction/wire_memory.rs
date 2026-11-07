//! Narrow, source-certified plain graph accounting; all other documents retain
//! the general envelope. No camera/fixture/host-dependent eligibility.
use super::wire::{Container, Dtype, Request};
use super::*;
use crate::graph_interaction_state::HighlightPlane;

#[derive(Clone, Copy, Debug)]
pub(super) struct Plain {
    n: usize,
    m: usize,
    document: usize,
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
        let n = c.get("node.uuid", 0)?.count;
        let m = c.get("edge.uuid", 0)?.count;
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
    pub fn source(self, watermarks: usize) -> Option<usize> {
        // Keep the predecessor's complete 48D source/identity/decoding envelope.
        // It includes both speculative source copies and retained CoSE arrays.
        98_304usize
            .checked_add(self.document.checked_mul(48)?)?
            .checked_add(watermarks.checked_mul(128)?)
    }
    pub fn retains(self, s: &GraphSession) -> bool {
        let StateSlot::Owned(state) = &s.slot else {
            return false;
        };
        s.pending_outbound().is_none_or(|e| e.refs.iter().all(|r| !matches!(r, ElementRef::Derived(_)))) &&
        state.selection().derived.is_empty()
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
            && s.budgets.0 >= self.n as u64
            && s.budgets.1 >= self.m as u64
            && matches!(r.operation, 0 | 1 | 4 | 5 | 6 | 7 | 8 | 15 | 17 | 21 | 22)
    }
    pub fn work(self, r: &Request<'_>) -> Option<usize> {
        // Flat neutral non-loop graph: <= n nodes, m single shafts, no heads,
        // frames, label pools or result/projection planes. Layout and renderer
        // policy are unchanged. Reserve growable row vectors at twice length.
        let node = 2 * std::mem::size_of::<NodePaint>()
            + 4 * std::mem::size_of::<crate::graph_style::ResolvedGraphStyle>()
            + 80 * 8;
        let edge = 2 * std::mem::size_of::<EdgePiece>()
            + 4 * (std::mem::size_of::<crate::graph_style::ResolvedGraphStyle>()
                + std::mem::size_of::<crate::graph_style::SemanticPaintLayers>())
            + 3 * (5 + crate::edge_route::EDGE_ENDS_STRIDE) * 8
            + 48 * 8;
        let rows = self
            .n
            .checked_mul(node)?
            .checked_add(self.m.checked_mul(edge)?)?;
        // GPU-v1 + CPU snapshot + membership/state columns: <=208 bytes/node,
        // <=336 bytes/single shaft. Three concurrent builder/final/scratch
        // capacities; actual preceding replies are charged separately.
        let output = 131_072usize
            .checked_add(self.n.checked_mul(208)?)?
            .checked_add(self.m.checked_mul(336)?)?;
        // CSR always allocates exactly entries, never growing cell Vecs. The
        // preceding immutable grid is charged by its actual retained capacity.
        let entries = self
            .n
            .checked_add(self.m)?
            .checked_mul(4096)?
            .min(MAX_GRAPH_PICK_GRID_ENTRIES);
        let grid = entries.checked_mul(4)?.checked_add(2 * 4097 * 4)?;
        // Point/focused selection can add one source identity; clear/focus/
        // continuation do not expand any identity plane. Larger operations use
        // the general envelope before mutation.
        let state = if matches!(r.operation, 1 | 7) {
            1024
        } else {
            0
        };
        rows.checked_add(output.checked_mul(3)?)?
            .checked_add(grid)?
            .checked_add(state)
    }
}

pub(super) fn publication_bytes(p: &RenderOutput) -> Option<usize> {
    fn bytes<T>(v: &Vec<T>) -> usize {
        v.capacity() * std::mem::size_of::<T>()
    }
    let mut total = p.pick.retained_bytes();
    macro_rules! add { ($($v:expr),* $(,)?) => { $(total = total.checked_add(bytes($v))?;)* }; }
    add!(
        &p.source_node_flags,
        &p.source_edge_flags,
        &p.node_x,
        &p.node_y,
        &p.member_of,
        &p.edge_source,
        &p.edge_target,
        &p.edge_member_offsets,
        &p.edge_members,
        &p.visual_states,
        &p.emphasis,
        &p.edge_visual_states,
        &p.edge_emphasis,
        &p.node_member_offsets,
        &p.node_members,
        &p.focus_node,
        &p.edge_render,
        &p.paint.nodes,
        &p.paint.edge_styles,
        &p.paint.edge_layers,
        &p.paint.pieces,
        &p.paint.frames
    );
    Some(total)
}
